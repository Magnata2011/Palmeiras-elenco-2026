from flask import Flask, jsonify, request
from flask_cors import CORS

import sqlite3
import os
import uuid
import json
import threading
import time
import secrets
from functools import wraps
from datetime import datetime, timedelta

# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

# ============================================================
# CORS
# ============================================================

origens_env = os.environ.get("ORIGENS_PERMITIDAS", "").strip()

if origens_env:

    origens_permitidas = [
        origem.strip().rstrip("/")
        for origem in origens_env.split(",")
        if origem.strip()
    ]

    CORS(
        app,
        origins=origens_permitidas,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "OPTIONS"]
    )

else:

    # Desenvolvimento local
    CORS(
        app,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "OPTIONS"]
    )


# ============================================================
# BANCO
# ============================================================

DATABASE = "rifa.db"

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

USANDO_POSTGRES = bool(DATABASE_URL)

if USANDO_POSTGRES:

    import psycopg2
    import psycopg2.extras

    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = (
            "postgresql://"
            + DATABASE_URL[len("postgres://"):]
        )


# ============================================================
# COMPATIBILIDADE SQLITE / POSTGRESQL
# ============================================================

class _CursorCompat:

    def __init__(self, cursor_real):

        self._cursor = cursor_real
        self._lastrowid = None

    def execute(self, sql, parametros=()):

        sql_final = sql

        if USANDO_POSTGRES:
            sql_final = sql_final.replace("?", "%s")

        self._cursor.execute(
            sql_final,
            parametros
        )

        if (
            USANDO_POSTGRES
            and "RETURNING ID" in sql_final.upper()
        ):

            try:

                linha = self._cursor.fetchone()

                if linha:
                    self._lastrowid = linha["id"]

            except Exception:

                self._lastrowid = None

        return self

    def fetchone(self):

        return self._cursor.fetchone()

    def fetchall(self):

        return self._cursor.fetchall()

    @property
    def lastrowid(self):

        if USANDO_POSTGRES:
            return self._lastrowid

        return self._cursor.lastrowid

    @property
    def rowcount(self):

        return self._cursor.rowcount


class _ConexaoCompat:

    def __init__(self, conexao_real):

        self._conexao = conexao_real

    def cursor(self):

        if USANDO_POSTGRES:

            cursor_real = self._conexao.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            )

        else:

            cursor_real = self._conexao.cursor()

        return _CursorCompat(cursor_real)

    def execute(self, sql, parametros=()):

        return self.cursor().execute(
            sql,
            parametros
        )

    def commit(self):

        return self._conexao.commit()

    def rollback(self):

        return self._conexao.rollback()

    def close(self):

        return self._conexao.close()


# ============================================================
# CONFIGURAÇÕES DA RIFA
# ============================================================

PRECO_NUMERO = float(
    os.environ.get(
        "PRECO_NUMERO",
        "30"
    )
)

TOTAL_NUMEROS = int(
    os.environ.get(
        "TOTAL_NUMEROS",
        "1000"
    )
)


# ============================================================
# E-MAIL
# ============================================================

import smtplib
from email.mime.text import MIMEText


def enviar_email_notificacao(assunto, corpo):

    host = os.environ.get("SMTP_HOST")
    porta = os.environ.get("SMTP_PORT")
    usuario_smtp = os.environ.get("SMTP_USUARIO")
    senha_smtp = os.environ.get("SMTP_SENHA")
    destino = os.environ.get("EMAIL_NOTIFICACAO_ADMIN")

    if not all([
        host,
        porta,
        usuario_smtp,
        senha_smtp,
        destino
    ]):

        return

    try:

        mensagem = MIMEText(
            corpo,
            "plain",
            "utf-8"
        )

        mensagem["Subject"] = assunto
        mensagem["From"] = usuario_smtp
        mensagem["To"] = destino

        with smtplib.SMTP_SSL(
            host,
            int(porta)
        ) as servidor:

            servidor.login(
                usuario_smtp,
                senha_smtp
            )

            servidor.sendmail(
                usuario_smtp,
                [destino],
                mensagem.as_string()
            )

    except Exception as erro:

        print(
            "Erro ao enviar e-mail de notificação:",
            erro
        )


# ============================================================
# LOGIN ADMIN
# ============================================================

def _var_ambiente_limpa(nome, padrao):

    valor = os.environ.get(nome)

    if valor is None:
        return padrao

    valor = valor.strip()

    if (
        len(valor) >= 2
        and valor[0] == valor[-1]
        and valor[0] in ("'", '"')
    ):

        valor = valor[1:-1].strip()

    return valor if valor else padrao


ADMIN_USUARIOS = {

    _var_ambiente_limpa(
        "ADMIN_USUARIO_1",
        "jmagno2011"
    ):

    _var_ambiente_limpa(
        "ADMIN_SENHA_1",
        "JM2011"
    ),

    _var_ambiente_limpa(
        "ADMIN_USUARIO_2",
        "admin"
    ):

    _var_ambiente_limpa(
        "ADMIN_SENHA_2",
        "admin123"
    )

}


print(
    "[admin] Usuários administradores carregados: "
    + repr(list(ADMIN_USUARIOS.keys()))
)


SESSOES_ADMIN = {}

SESSOES_LOCK = threading.Lock()

DURACAO_SESSAO_HORAS = 12


def limpar_sessoes_expiradas():

    agora_atual = datetime.now()

    with SESSOES_LOCK:

        expiradas = [
            token
            for token, dados in SESSOES_ADMIN.items()
            if dados["expira_em"] <= agora_atual
        ]

        for token in expiradas:

            del SESSOES_ADMIN[token]


def exigir_login_admin(funcao):

    @wraps(funcao)
    def decorada(*args, **kwargs):

        limpar_sessoes_expiradas()

        cabecalho = request.headers.get(
            "Authorization",
            ""
        )

        if not cabecalho.startswith("Bearer "):

            return jsonify({
                "sucesso": False,
                "erro": "Login necessário."
            }), 401

        token_sessao = cabecalho[
            len("Bearer "):
        ]

        with SESSOES_LOCK:

            sessao_valida = (
                token_sessao
                in SESSOES_ADMIN
            )

        if not sessao_valida:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Sessão inválida ou expirada. "
                    "Faça login novamente."
            }), 401

        return funcao(
            *args,
            **kwargs
        )

    return decorada


# ============================================================
# CONEXÃO
# ============================================================

def conectar():

    if USANDO_POSTGRES:

        conexao_real = psycopg2.connect(
            DATABASE_URL
        )

        return _ConexaoCompat(
            conexao_real
        )

    conexao_real = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    conexao_real.row_factory = sqlite3.Row

    return _ConexaoCompat(
        conexao_real
    )


# ============================================================
# DATA / HORA
# ============================================================

def agora():

    return datetime.now()


def agora_texto():

    return agora().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def data_para_json(valor):

    if valor is None:
        return None

    if isinstance(valor, str):

        # Se já vier em formato ISO com Z
        if valor.endswith("Z"):
            return valor

        return (
            valor.replace(" ", "T")
            + "Z"
        )

    return (
        valor.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )


def hora_brasilia_texto(dt):

    if dt is None:
        return "-"

    ajustada = dt - timedelta(
        hours=3
    )

    return (
        ajustada.strftime(
            "%d/%m/%Y %H:%M:%S"
        )
        + " (horário de Brasília)"
    )


def texto_para_data(valor):

    if not valor:
        return None

    if isinstance(valor, datetime):
        return valor

    try:

        return datetime.strptime(
            str(valor),
            "%Y-%m-%d %H:%M:%S"
        )

    except ValueError:

        try:

            return datetime.fromisoformat(
                str(valor).replace(
                    "Z",
                    ""
                )
            )

        except Exception:

            return None


# ============================================================
# CRIAÇÃO DO BANCO
# ============================================================

def criar_banco():

    conexao = conectar()

    cursor = conexao.cursor()

    try:

        # ====================================================
        # NÚMEROS
        # ====================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS numeros (

                numero INTEGER PRIMARY KEY,

                status TEXT NOT NULL
                    DEFAULT 'disponivel'

            )
        """)

        # ====================================================
        # COMPRAS
        # ====================================================

        if USANDO_POSTGRES:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS compras (

                    id SERIAL PRIMARY KEY,

                    token TEXT NOT NULL UNIQUE,

                    numeros TEXT NOT NULL,

                    status TEXT NOT NULL
                        DEFAULT 'pendente_pagamento',

                    criado_em TEXT NOT NULL,

                    comprovante TEXT,

                    comprovante_enviado_em TEXT,

                    expira_em TEXT,

                    confirmado_em TEXT

                )
            """)

        else:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS compras (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    token TEXT NOT NULL UNIQUE,

                    numeros TEXT NOT NULL,

                    status TEXT NOT NULL
                        DEFAULT 'pendente_pagamento',

                    criado_em TEXT NOT NULL,

                    comprovante TEXT,

                    comprovante_enviado_em TEXT,

                    expira_em TEXT,

                    confirmado_em TEXT

                )
            """)

        # ====================================================
        # CRIAR NÚMEROS
        # ====================================================

        for numero in range(
            1,
            TOTAL_NUMEROS + 1
        ):

            if USANDO_POSTGRES:

                cursor.execute("""
                    INSERT INTO numeros
                    (
                        numero,
                        status
                    )
                    VALUES
                    (
                        ?,
                        'disponivel'
                    )
                    ON CONFLICT (numero)
                    DO NOTHING
                """, (numero,))

            else:

                cursor.execute("""
                    INSERT OR IGNORE INTO numeros
                    (
                        numero,
                        status
                    )
                    VALUES
                    (
                        ?,
                        'disponivel'
                    )
                """, (numero,))

        conexao.commit()

        print(
            "[banco] Banco inicializado com sucesso."
        )

    except Exception:

        conexao.rollback()

        raise

    finally:

        conexao.close()


# ============================================================
# EXPIRAR COMPRAS
# ============================================================
#
# IMPORTANTE:
#
# SOMENTE compras com:
#
#     status = pendente_pagamento
#
# podem expirar.
#
# Quando a pessoa clica em "Já realizei o pagamento":
#
#     status = comprovante_enviado
#     expira_em = NULL
#
# Portanto essa compra nunca mais é expirada automaticamente.
# ============================================================

def expirar_compras():

    conexao = conectar()

    cursor = conexao.cursor()

    try:

        compras = cursor.execute("""
            SELECT
                id,
                token,
                numeros,
                status,
                expira_em
            FROM compras
            WHERE status = 'pendente_pagamento'
            AND expira_em IS NOT NULL
        """).fetchall()

        agora_atual = agora()

        for compra in compras:

            data_expiracao = texto_para_data(
                compra["expira_em"]
            )

            if data_expiracao is None:
                continue

            if agora_atual >= data_expiracao:

                try:

                    numeros = json.loads(
                        compra["numeros"]
                    )

                except Exception:

                    numeros = []

                for numero in numeros:

                    cursor.execute("""
                        UPDATE numeros

                        SET status = 'disponivel'

                        WHERE numero = ?

                        AND status = 'pendente'
                    """, (numero,))

                cursor.execute("""
                    UPDATE compras

                    SET status = 'expirada'

                    WHERE id = ?
                """, (compra["id"],))

        conexao.commit()

    except Exception:

        conexao.rollback()

        raise

    finally:

        conexao.close()


# ============================================================
# THREAD DE EXPIRAÇÃO
# ============================================================

def iniciar_expiracao_automatica():

    def verificar():

        while True:

            try:

                expirar_compras()

            except Exception as erro:

                print(
                    "Erro ao verificar compras expiradas:",
                    erro
                )

            time.sleep(30)

    thread = threading.Thread(
        target=verificar,
        daemon=True
    )

    thread.start()


# ============================================================
# ROTA PRINCIPAL
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def verificacao():

    return jsonify({
        "sucesso": True,
        "mensagem": "API da rifa está no ar.",
        "banco":
            "postgresql"
            if USANDO_POSTGRES
            else "sqlite"
    })


# ============================================================
# LISTAR NÚMEROS
# ============================================================

@app.route(
    "/api/numeros",
    methods=["GET"]
)
def listar_numeros():

    expirar_compras()

    conexao = conectar()

    try:

        numeros = conexao.execute("""
            SELECT
                numero,
                status
            FROM numeros
            ORDER BY numero
        """).fetchall()

    finally:

        conexao.close()

    return jsonify([

        {
            "numero": numero["numero"],
            "status": numero["status"]
        }

        for numero in numeros

    ])


# ============================================================
# PEGAR UM NÚMERO
# ============================================================

@app.route(
    "/api/numeros/<int:numero>",
    methods=["GET"]
)
def pegar_numero(numero):

    expirar_compras()

    conexao = conectar()

    try:

        resultado = conexao.execute("""
            SELECT
                numero,
                status
            FROM numeros
            WHERE numero = ?
        """, (numero,)).fetchone()

    finally:

        conexao.close()

    if resultado is None:

        return jsonify({
            "sucesso": False,
            "erro": "Número não encontrado."
        }), 404

    return jsonify({
        "sucesso": True,
        "numero": resultado["numero"],
        "status": resultado["status"]
    })


# ============================================================
# RESERVAR NÚMEROS
# ============================================================

@app.route(
    "/api/reservar",
    methods=["POST"]
)
def reservar():

    expirar_compras()

    dados = request.get_json()

    if not dados:

        return jsonify({
            "sucesso": False,
            "erro": "Dados não enviados."
        }), 400

    numeros = dados.get(
        "numeros",
        []
    )

    if (
        not isinstance(numeros, list)
        or not numeros
    ):

        return jsonify({
            "sucesso": False,
            "erro": "Nenhum número enviado."
        }), 400

    try:

        numeros = sorted(
            set(
                int(numero)
                for numero in numeros
            )
        )

    except Exception:

        return jsonify({
            "sucesso": False,
            "erro": "Lista de números inválida."
        }), 400

    # Não permite 0, negativos ou números
    # acima do total configurado.

    if any(
        numero < 1
        or numero > TOTAL_NUMEROS
        for numero in numeros
    ):

        return jsonify({
            "sucesso": False,
            "erro": "Um ou mais números são inválidos."
        }), 400

    if len(numeros) > TOTAL_NUMEROS:

        return jsonify({
            "sucesso": False,
            "erro": "Quantidade de números inválida."
        }), 400

    conexao = conectar()

    cursor = conexao.cursor()

    try:

        # ====================================================
        # VERIFICAR NÚMEROS
        # ====================================================

        for numero in numeros:

            resultado = cursor.execute("""
                SELECT
                    status
                FROM numeros
                WHERE numero = ?
            """, (numero,)).fetchone()

            if resultado is None:

                conexao.rollback()

                return jsonify({
                    "sucesso": False,
                    "erro":
                        f"O número {numero} não existe."
                }), 404

            status = resultado["status"]

            if status != "disponivel":

                conexao.rollback()

                if status == "pendente":

                    mensagem = (
                        f"O número {numero} está "
                        "com uma compra pendente."
                    )

                else:

                    mensagem = (
                        f"O número {numero} "
                        "já foi comprado por outra pessoa."
                    )

                return jsonify({
                    "sucesso": False,
                    "erro": mensagem
                }), 409

        # ====================================================
        # TOKEN
        # ====================================================

        token = str(
            uuid.uuid4()
        )

        criado_em = agora()

        # ====================================================
        # PRAZO DE PAGAMENTO
        # ====================================================

        expira_em = (
            criado_em
            + timedelta(hours=24)
        )

        # ====================================================
        # CRIAR COMPRA
        # ====================================================

        sql_insert = """
            INSERT INTO compras
            (
                token,
                numeros,
                status,
                criado_em,
                expira_em
            )
            VALUES
            (
                ?,
                ?,
                'pendente_pagamento',
                ?,
                ?
            )
        """

        if USANDO_POSTGRES:

            sql_insert += " RETURNING id"

        cursor.execute(
            sql_insert,
            (
                token,
                json.dumps(numeros),
                criado_em.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                expira_em.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        compra_id = cursor.lastrowid

        # ====================================================
        # RESERVAR NÚMEROS
        # ====================================================

        for numero in numeros:

            cursor.execute("""
                UPDATE numeros

                SET status = 'pendente'

                WHERE numero = ?

                AND status = 'disponivel'
            """, (numero,))

            if cursor.rowcount != 1:

                conexao.rollback()

                return jsonify({
                    "sucesso": False,
                    "erro":
                        f"O número {numero} acabou de "
                        "ser reservado."
                }), 409

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        print(
            "Erro ao reservar:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Erro interno ao reservar os números."
        }), 500

    finally:

        conexao.close()

    numeros_texto = ", ".join(
        str(numero).zfill(3)
        for numero in numeros
    )

    enviar_email_notificacao(
        "🎟️ Nova reserva na rifa",
        "Alguém acabou de reservar números e tem "
        "24 horas para pagar.\n\n"
        f"Código da compra: {token}\n"
        f"Números: {numeros_texto}\n"
        f"Quantidade: {len(numeros)}\n"
        f"Expira em: "
        f"{hora_brasilia_texto(expira_em)}"
    )

    return jsonify({

        "sucesso": True,

        "mensagem":
            "Números reservados com sucesso.",

        "compra_id":
            compra_id,

        "token":
            token,

        "numeros":
            numeros,

        "expira_em":
            data_para_json(expira_em)

    })


# ============================================================
# CONSULTAR COMPRA
# ============================================================

@app.route(
    "/api/compras/<token>",
    methods=["GET"]
)
def consultar_compra(token):

    expirar_compras()

    conexao = conectar()

    try:

        compra = conexao.execute("""
            SELECT
                id,
                token,
                numeros,
                status,
                criado_em,
                comprovante,
                comprovante_enviado_em,
                expira_em,
                confirmado_em
            FROM compras
            WHERE token = ?
        """, (token,)).fetchone()

    finally:

        conexao.close()

    if compra is None:

        return jsonify({
            "sucesso": False,
            "erro": "Compra não encontrada."
        }), 404

    try:

        numeros = json.loads(
            compra["numeros"]
        )

    except Exception:

        numeros = []

    return jsonify({

        "sucesso": True,

        "compra": {

            "id":
                compra["id"],

            "token":
                compra["token"],

            "numeros":
                numeros,

            "status":
                compra["status"],

            "criado_em":
                data_para_json(
                    compra["criado_em"]
                ),

            "comprovante":
                compra["comprovante"],

            "comprovante_enviado_em":
                data_para_json(
                    compra["comprovante_enviado_em"]
                ),

            "expira_em":
                data_para_json(
                    compra["expira_em"]
                ),

            "confirmado_em":
                data_para_json(
                    compra["confirmado_em"]
                )

        }

    })


# ============================================================
# PAGAMENTO CONFIRMADO PELO CLIENTE
# ============================================================
#
# A pessoa clicou em "Já realizei o pagamento".
#
# NÃO confirma a compra.
#
# Apenas muda:
#
# pendente_pagamento
#        ↓
# comprovante_enviado
#
# E remove o prazo.
# ============================================================

@app.route(
    "/api/pagamento-confirmado",
    methods=["POST"]
)
def pagamento_confirmado():

    expirar_compras()

    dados = request.get_json() or {}

    token = dados.get("token")

    if not token:

        return jsonify({
            "sucesso": False,
            "erro":
                "Token da compra não enviado."
        }), 400

    conexao = conectar()

    cursor = conexao.cursor()

    try:

        compra = cursor.execute("""
            SELECT
                id,
                numeros,
                status
            FROM compras
            WHERE token = ?
        """, (token,)).fetchone()

        if compra is None:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Compra não encontrada."
            }), 404

        if compra["status"] == "expirada":

            return jsonify({
                "sucesso": False,
                "erro":
                    "O prazo desta compra expirou. "
                    "Os números foram liberados."
            }), 410

        if compra["status"] == "cancelada":

            return jsonify({
                "sucesso": False,
                "erro":
                    "Esta compra foi cancelada."
            }), 409

        if compra["status"] == "confirmada":

            return jsonify({
                "sucesso": False,
                "erro":
                    "Esta compra já foi confirmada."
            }), 409

        if compra["status"] == "comprovante_enviado":

            return jsonify({
                "sucesso": True,
                "mensagem":
                    "O pagamento já foi marcado como realizado.",
                "expira_em": None
            })

        confirmado_em = agora()

        # ====================================================
        # REMOVER PRAZO
        # ====================================================

        cursor.execute("""
            UPDATE compras

            SET
                status = 'comprovante_enviado',

                comprovante_enviado_em = ?,

                expira_em = NULL

            WHERE token = ?
        """, (
            confirmado_em.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            token
        ))

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        print(
            "Erro ao marcar pagamento como realizado:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Não foi possível registrar "
                "a confirmação."
        }), 500

    finally:

        conexao.close()

    try:

        numeros_da_compra = json.loads(
            compra["numeros"]
        )

        numeros_texto = ", ".join(
            str(numero).zfill(3)
            for numero in numeros_da_compra
        )

    except Exception:

        numeros_texto = "?"

    enviar_email_notificacao(
        "💰 Pagamento marcado como realizado",
        "Alguém marcou o pagamento como realizado "
        "e foi redirecionado para o WhatsApp para "
        "enviar o comprovante.\n\n"
        f"Código da compra: {token}\n"
        f"Números: {numeros_texto}\n\n"
        "A compra agora aguarda confirmação manual "
        "do administrador."
    )

    return jsonify({

        "sucesso": True,

        "mensagem":
            "Pagamento marcado como realizado.",

        # IMPORTANTE:
        # não existe mais prazo nessa etapa.
        "expira_em":
            None

    })


# ============================================================
# LIBERAR / CANCELAR COMPRA
# ============================================================

@app.route(
    "/api/liberar",
    methods=["POST"]
)
def liberar_numeros():

    expirar_compras()

    dados = request.get_json()

    if not dados:

        return jsonify({
            "sucesso": False,
            "erro": "Dados não enviados."
        }), 400

    token = dados.get("token")

    numeros = dados.get(
        "numeros",
        []
    )

    # ========================================================
    # USANDO TOKEN
    # ========================================================

    if token:

        conexao = conectar()

        cursor = conexao.cursor()

        try:

            compra = cursor.execute("""
                SELECT
                    id,
                    numeros,
                    status
                FROM compras
                WHERE token = ?
            """, (token,)).fetchone()

            if compra is None:

                return jsonify({
                    "sucesso": False,
                    "erro":
                        "Compra não encontrada."
                }), 404

            if compra["status"] == "confirmada":

                return jsonify({
                    "sucesso": False,
                    "erro":
                        "Esta compra já foi confirmada "
                        "e não pode ser cancelada."
                }), 409

            try:

                numeros_compra = json.loads(
                    compra["numeros"]
                )

            except Exception:

                numeros_compra = []

            # =================================================
            # LIBERAR APENAS NÚMEROS PENDENTES
            # =================================================

            for numero in numeros_compra:

                cursor.execute("""
                    UPDATE numeros

                    SET status = 'disponivel'

                    WHERE numero = ?

                    AND status = 'pendente'
                """, (numero,))

            cursor.execute("""
                UPDATE compras

                SET status = 'cancelada'

                WHERE id = ?
            """, (compra["id"],))

            conexao.commit()

            return jsonify({

                "sucesso": True,

                "mensagem":
                    "Compra cancelada e números liberados.",

                "liberados":
                    numeros_compra

            })

        except Exception as erro:

            conexao.rollback()

            print(
                "Erro ao liberar compra:",
                erro
            )

            return jsonify({
                "sucesso": False,
                "erro":
                    "Erro interno ao cancelar a compra."
            }), 500

        finally:

            conexao.close()

    # ========================================================
    # COMPATIBILIDADE ANTIGA
    # ========================================================

    if not numeros:

        return jsonify({
            "sucesso": False,
            "erro": "Nenhum número enviado."
        }), 400

    try:

        numeros = [
            int(numero)
            for numero in numeros
        ]

    except Exception:

        return jsonify({
            "sucesso": False,
            "erro": "Lista de números inválida."
        }), 400

    conexao = conectar()

    cursor = conexao.cursor()

    liberados = []
    nao_liberados = []

    try:

        for numero in numeros:

            resultado = cursor.execute("""
                SELECT
                    numero,
                    status
                FROM numeros
                WHERE numero = ?
            """, (numero,)).fetchone()

            if resultado is None:

                nao_liberados.append({
                    "numero": numero,
                    "motivo":
                        "Número não existe."
                })

                continue

            if resultado["status"] == "pendente":

                cursor.execute("""
                    UPDATE numeros

                    SET status = 'disponivel'

                    WHERE numero = ?

                    AND status = 'pendente'
                """, (numero,))

                if cursor.rowcount == 1:

                    liberados.append(numero)

                else:

                    nao_liberados.append({
                        "numero": numero,
                        "motivo":
                            "Não foi possível liberar."
                    })

            else:

                nao_liberados.append({
                    "numero": numero,
                    "motivo":
                        f"Status atual: "
                        f"{resultado['status']}"
                })

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        print(
            "Erro ao liberar números:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Erro interno ao liberar números."
        }), 500

    finally:

        conexao.close()

    return jsonify({

        "sucesso": True,

        "liberados":
            liberados,

        "nao_liberados":
            nao_liberados

    })


# ============================================================
# LOGIN ADMIN
# ============================================================

@app.route(
    "/api/admin/login",
    methods=["POST"]
)
def login_admin():

    dados = request.get_json() or {}

    usuario = str(
        dados.get(
            "usuario",
            ""
        )
    ).strip()

    senha = str(
        dados.get(
            "senha",
            ""
        )
    ).strip()

    senha_correta = ADMIN_USUARIOS.get(
        usuario
    )

    if (
        senha_correta is None
        or senha != senha_correta
    ):

        if senha_correta is None:

            motivo = (
                "usuário não está na lista "
                "de cadastrados"
            )

        else:

            motivo = (
                "usuário OK, senha não bate "
                "(comprimento diferente ou conteúdo "
                "incorreto)"
            )

        print(
            "[login admin] Tentativa falhou. "
            "Usuário recebido: "
            + repr(usuario)
            + " | Motivo: "
            + motivo
            + " | Usuários cadastrados: "
            + repr(
                list(
                    ADMIN_USUARIOS.keys()
                )
            )
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Usuário ou senha incorretos."
        }), 401

    token_sessao = secrets.token_hex(32)

    with SESSOES_LOCK:

        SESSOES_ADMIN[
            token_sessao
        ] = {

            "usuario":
                usuario,

            "expira_em":
                datetime.now()
                + timedelta(
                    hours=DURACAO_SESSAO_HORAS
                )

        }

    return jsonify({

        "sucesso": True,

        "token":
            token_sessao,

        "usuario":
            usuario

    })


# ============================================================
# LOGOUT ADMIN
# ============================================================

@app.route(
    "/api/admin/logout",
    methods=["POST"]
)
def logout_admin():

    dados = request.get_json() or {}

    token_sessao = dados.get(
        "token"
    )

    with SESSOES_LOCK:

        SESSOES_ADMIN.pop(
            token_sessao,
            None
        )

    return jsonify({
        "sucesso": True
    })


# ============================================================
# ADMIN - ALTERAR STATUS DE NÚMERO
# ============================================================

@app.route(
    "/api/admin/numeros/<int:numero>",
    methods=["PUT"]
)
@exigir_login_admin
def alterar_status(numero):

    dados = request.get_json()

    if not dados:

        return jsonify({
            "sucesso": False,
            "erro": "Dados não enviados."
        }), 400

    novo_status = dados.get(
        "status"
    )

    status_permitidos = [
        "disponivel",
        "pendente",
        "indisponivel"
    ]

    if novo_status not in status_permitidos:

        return jsonify({
            "sucesso": False,
            "erro": "Status inválido."
        }), 400

    conexao = conectar()

    cursor = conexao.cursor()

    try:

        resultado = cursor.execute("""
            SELECT
                numero
            FROM numeros
            WHERE numero = ?
        """, (numero,)).fetchone()

        if resultado is None:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Número não encontrado."
            }), 404

        cursor.execute("""
            UPDATE numeros

            SET status = ?

            WHERE numero = ?
        """, (
            novo_status,
            numero
        ))

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        print(
            "Erro ao alterar status:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Erro interno ao alterar o status."
        }), 500

    finally:

        conexao.close()

    return jsonify({

        "sucesso": True,

        "numero":
            numero,

        "status":
            novo_status

    })


# ============================================================
# ADMIN - LISTAR COMPRAS
# ============================================================

@app.route(
    "/api/admin/compras",
    methods=["GET"]
)
@exigir_login_admin
def admin_compras():

    expirar_compras()

    conexao = conectar()

    try:

        compras = conexao.execute("""
            SELECT
                id,
                token,
                numeros,
                status,
                criado_em,
                comprovante,
                comprovante_enviado_em,
                expira_em,
                confirmado_em
            FROM compras
            ORDER BY id DESC
        """).fetchall()

    finally:

        conexao.close()

    resultado = []

    for compra in compras:

        try:

            numeros = json.loads(
                compra["numeros"]
            )

        except Exception:

            numeros = []

        resultado.append({

            "id":
                compra["id"],

            "token":
                compra["token"],

            "numeros":
                numeros,

            "status":
                compra["status"],

            "criado_em":
                data_para_json(
                    compra["criado_em"]
                ),

            "comprovante":
                compra["comprovante"],

            "comprovante_enviado_em":
                data_para_json(
                    compra["comprovante_enviado_em"]
                ),

            "expira_em":
                data_para_json(
                    compra["expira_em"]
                ),

            "confirmado_em":
                data_para_json(
                    compra["confirmado_em"]
                )

        })

    return jsonify({

        "sucesso": True,

        "compras":
            resultado

    })


# ============================================================
# ADMIN - CONFIRMAR COMPRA
# ============================================================

@app.route(
    "/api/admin/compras/<token>/confirmar",
    methods=["PUT"]
)
@exigir_login_admin
def confirmar_compra(token):

    expirar_compras()

    conexao = conectar()

    cursor = conexao.cursor()

    try:

        compra = cursor.execute("""
            SELECT
                id,
                numeros,
                status
            FROM compras
            WHERE token = ?
        """, (token,)).fetchone()

        if compra is None:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Compra não encontrada."
            }), 404

        if compra["status"] == "expirada":

            return jsonify({
                "sucesso": False,
                "erro":
                    "Esta compra já expirou."
            }), 409

        if compra["status"] == "cancelada":

            return jsonify({
                "sucesso": False,
                "erro":
                    "Esta compra foi cancelada."
            }), 409

        if compra["status"] == "confirmada":

            return jsonify({
                "sucesso": True,
                "mensagem":
                    "Compra já estava confirmada."
            })

        try:

            numeros = json.loads(
                compra["numeros"]
            )

        except Exception:

            numeros = []

        # ====================================================
        # MARCAR NÚMEROS COMO INDISPONÍVEIS
        # ====================================================

        for numero in numeros:

            cursor.execute("""
                UPDATE numeros

                SET status = 'indisponivel'

                WHERE numero = ?

                AND status = 'pendente'
            """, (numero,))

        # ====================================================
        # CONFIRMAR
        # ====================================================

        cursor.execute("""
            UPDATE compras

            SET
                status = 'confirmada',

                confirmado_em = ?

            WHERE token = ?
        """, (
            agora_texto(),
            token
        ))

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        print(
            "Erro ao confirmar compra:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Erro interno ao confirmar a compra."
        }), 500

    finally:

        conexao.close()

    return jsonify({

        "sucesso": True,

        "mensagem":
            "Pagamento confirmado.",

        "numeros":
            numeros

    })


# ============================================================
# ADMIN - REJEITAR COMPRA
# ============================================================

@app.route(
    "/api/admin/compras/<token>/rejeitar",
    methods=["PUT"]
)
@exigir_login_admin
def rejeitar_compra(token):

    expirar_compras()

    conexao = conectar()

    cursor = conexao.cursor()

    try:

        compra = cursor.execute("""
            SELECT
                id,
                numeros,
                status
            FROM compras
            WHERE token = ?
        """, (token,)).fetchone()

        if compra is None:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Compra não encontrada."
            }), 404

        if compra["status"] == "confirmada":

            return jsonify({
                "sucesso": False,
                "erro":
                    "Uma compra confirmada não "
                    "pode ser rejeitada."
            }), 409

        try:

            numeros = json.loads(
                compra["numeros"]
            )

        except Exception:

            numeros = []

        # ====================================================
        # LIBERAR NÚMEROS
        # ====================================================

        for numero in numeros:

            cursor.execute("""
                UPDATE numeros

                SET status = 'disponivel'

                WHERE numero = ?

                AND status = 'pendente'
            """, (numero,))

        # ====================================================
        # CANCELAR COMPRA
        # ====================================================

        cursor.execute("""
            UPDATE compras

            SET status = 'cancelada'

            WHERE token = ?
        """, (token,))

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        print(
            "Erro ao rejeitar compra:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Erro interno ao rejeitar a compra."
        }), 500

    finally:

        conexao.close()

    return jsonify({

        "sucesso": True,

        "mensagem":
            "Compra rejeitada e números liberados.",

        "numeros":
            numeros

    })


# ============================================================
# ADMIN - ESTATÍSTICAS
# ============================================================

@app.route(
    "/api/admin/estatisticas",
    methods=["GET"]
)
@exigir_login_admin
def estatisticas():

    expirar_compras()

    conexao = conectar()

    try:

        resultado = conexao.execute("""
            SELECT
                status,
                COUNT(*) AS quantidade
            FROM numeros
            GROUP BY status
        """).fetchall()

        compras = conexao.execute("""
            SELECT
                status,
                COUNT(*) AS quantidade
            FROM compras
            GROUP BY status
        """).fetchall()

    finally:

        conexao.close()

    estatisticas_numeros = {

        "disponiveis":
            0,

        "pendentes":
            0,

        "indisponiveis":
            0

    }

    for linha in resultado:

        status = linha["status"]

        quantidade = int(
            linha["quantidade"]
        )

        if status == "disponivel":

            estatisticas_numeros[
                "disponiveis"
            ] = quantidade

        elif status == "pendente":

            estatisticas_numeros[
                "pendentes"
            ] = quantidade

        elif status == "indisponivel":

            estatisticas_numeros[
                "indisponiveis"
            ] = quantidade

    estatisticas_compras = {}

    for linha in compras:

        estatisticas_compras[
            linha["status"]
        ] = int(
            linha["quantidade"]
        )

    total_arrecadado = (
        estatisticas_numeros[
            "indisponiveis"
        ]
        * PRECO_NUMERO
    )

    return jsonify({

        "numeros":
            estatisticas_numeros,

        "compras":
            estatisticas_compras,

        "total_arrecadado":
            total_arrecadado

    })


# ============================================================
# ERRO 413
# ============================================================

@app.errorhandler(413)
def arquivo_muito_grande(erro):

    return jsonify({

        "sucesso": False,

        "erro":
            "O comprovante é muito grande. "
            "O limite máximo é de 10 MB."

    }), 413


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def erro_servidor(erro):

    print(
        "Erro 500:",
        erro
    )

    return jsonify({

        "sucesso": False,

        "erro":
            "Erro interno do servidor."

    }), 500


# ============================================================
# INICIALIZAÇÃO
# ============================================================

try:

    criar_banco()

except Exception as erro:

    print(
        "ERRO AO CRIAR/ABRIR O BANCO:",
        erro
    )

    raise


# ============================================================
# THREAD DE EXPIRAÇÃO
# ============================================================

if (
    os.environ.get(
        "WERKZEUG_RUN_MAIN"
    ) == "true"

    or

    os.environ.get(
        "FLASK_DEBUG",
        "0"
    ) != "1"
):

    iniciar_expiracao_automatica()


# ============================================================
# SERVIDOR
# ============================================================

if __name__ == "__main__":

    print()
    print(
        "===================================="
    )
    print(
        "       SERVIDOR DA RIFA"
    )
    print(
        "===================================="
    )
    print()

    print(
        "Banco:",
        "PostgreSQL"
        if USANDO_POSTGRES
        else "SQLite"
    )

    print()

    print(
        "API: http://127.0.0.1:5000"
    )

    print()

    print(
        "Endpoints:"
    )

    print(
        "GET  /api/numeros"
    )

    print(
        "GET  /api/numeros/<numero>"
    )

    print(
        "POST /api/reservar"
    )

    print(
        "GET  /api/compras/<token>"
    )

    print(
        "POST /api/pagamento-confirmado"
    )

    print(
        "POST /api/liberar"
    )

    print(
        "POST /api/admin/login"
    )

    print(
        "POST /api/admin/logout"
    )

    print(
        "PUT  /api/admin/numeros/<numero>"
    )

    print(
        "GET  /api/admin/compras"
    )

    print(
        "PUT  /api/admin/compras/<token>/confirmar"
    )

    print(
        "PUT  /api/admin/compras/<token>/rejeitar"
    )

    print(
        "GET  /api/admin/estatisticas"
    )

    print()

    print(
        "Prazo inicial: 24 horas"
    )

    print(
        "Após 'Já realizei o pagamento': sem expiração automática"
    )

    print()

    porta = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    modo_debug = (
        os.environ.get(
            "FLASK_DEBUG",
            "0"
        ) == "1"
    )

    app.run(
        host="0.0.0.0",
        port=porta,
        debug=modo_debug
    )
