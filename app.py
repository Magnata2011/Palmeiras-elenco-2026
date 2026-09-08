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
# BANCO DE DADOS: SQLITE (local) OU POSTGRESQL (produção)
# ============================================================
# No seu computador, sem configurar nada, o site continua usando
# SQLite (um arquivo, "rifa.db") — simples pra testar.
#
# Em produção, o Render (e a maioria dos serviços de hospedagem)
# apaga os arquivos locais toda vez que o servidor reinicia, dorme
# ou recebe um novo deploy — incluindo o rifa.db. Isso faz números
# vendidos "voltarem a ficar disponíveis" sozinhos depois de um
# tempo sem acessos.
#
# Por isso, quando existir a variável de ambiente DATABASE_URL
# (o Render Postgres já fornece isso), o site troca automaticamente
# para PostgreSQL — que é um banco separado, e não é apagado nesses
# casos. Veja o README para o passo a passo de criar esse banco.
# ============================================================

MODO_POSTGRES = bool(os.environ.get("DATABASE_URL"))

if MODO_POSTGRES:

    import psycopg2
    import psycopg2.extras


class CursorCompativel:
    """
    Envolve o cursor do PostgreSQL para que o resto do código — que
    foi escrito pensando no SQLite — continue funcionando sem
    precisar reescrever cada consulta. Faz duas traduções:

    1. Os "?" usados como marcador de valor no SQLite viram "%s",
       que é o que o PostgreSQL espera.

    2. "cursor.execute(...).fetchone()" (encadeado, como o SQLite
       permite) volta a funcionar — o psycopg2 sozinho não permite
       encadear porque seu ".execute()" não devolve o cursor.
    """

    def __init__(self, cursor_real):
        self._cursor = cursor_real

    def execute(self, sql, parametros=()):

        sql_convertido = sql.replace("?", "%s")

        self._cursor.execute(sql_convertido, parametros)

        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __getattr__(self, nome):
        return getattr(self._cursor, nome)


class ConexaoCompativel:
    """
    Só existe para o .cursor() devolver o CursorCompativel acima, e
    para reproduzir o atalho "conexao.execute(...)" que o SQLite
    permite (cria um cursor sozinho) mas o psycopg2 não tem.
    """

    def __init__(self, conexao_real):
        self._conexao = conexao_real

    def cursor(self):
        return CursorCompativel(self._conexao.cursor())

    def execute(self, sql, parametros=()):
        return self.cursor().execute(sql, parametros)

    def __getattr__(self, nome):
        return getattr(self._conexao, nome)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)


# ------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------
# Em produção, defina a variável de ambiente ORIGENS_PERMITIDAS com
# o(s) endereço(s) do seu site no GitHub Pages, separados por vírgula.
# Exemplo (no painel do Render, em "Environment"):
#
#   ORIGENS_PERMITIDAS=https://seu-usuario.github.io
#
# Se a variável não for definida, libera geral (bom só para testar
# localmente).
# ------------------------------------------------------------------

origens_env = os.environ.get("ORIGENS_PERMITIDAS")

if origens_env:

    origens_permitidas = [
        origem.strip()
        for origem in origens_env.split(",")
        if origem.strip()
    ]

    CORS(
        app,
        origins=origens_permitidas,
        allow_headers=["Content-Type", "Authorization"]
    )

else:

    CORS(
        app,
        allow_headers=["Content-Type", "Authorization"]
    )

DATABASE = "rifa.db"


# Tempo máximo para o admin confirmar depois que a pessoa marca
# "já paguei" (ela é redirecionada pro formulário do Google nesse
# meio tempo)

HORAS_EXPIRACAO = 24


# Preço de cada número (usado só para calcular o total arrecadado
# nas estatísticas do admin). Mantenha igual ao PRECO do config.js.

PRECO_NUMERO = float(
    os.environ.get("PRECO_NUMERO", "30")
)


# Quantidade total de números da rifa (mantenha igual ao
# TOTAL_NUMEROS do config.js do site)

TOTAL_NUMEROS = int(
    os.environ.get("TOTAL_NUMEROS", "1000")
)


# ============================================================
# NOTIFICAÇÃO POR E-MAIL (OPCIONAL)
# ============================================================
# Além da notificação sonora/no navegador que já aparece no painel
# admin quando ele está aberto, dá pra receber um e-mail avisando de
# reservas e comprovantes — útil pra quando ninguém está de olho no
# painel. É opcional: se as variáveis de ambiente abaixo não forem
# configuradas, essa função simplesmente não faz nada (sem erro).
#
# Pra usar com Gmail: crie uma "Senha de app" em
# https://myaccount.google.com/apppasswords (precisa da verificação
# em duas etapas ativada) e configure no Render:
#
#   SMTP_HOST=smtp.gmail.com
#   SMTP_PORT=465
#   SMTP_USUARIO=seuemail@gmail.com
#   SMTP_SENHA=a senha de app gerada (não é a senha normal do Gmail)
#   EMAIL_NOTIFICACAO_ADMIN=seuemail@gmail.com (pode ser o mesmo)
# ============================================================

import smtplib
from email.mime.text import MIMEText


def enviar_email_notificacao(assunto, corpo):

    host = os.environ.get("SMTP_HOST")
    porta = os.environ.get("SMTP_PORT")
    usuario_smtp = os.environ.get("SMTP_USUARIO")
    senha_smtp = os.environ.get("SMTP_SENHA")
    destino = os.environ.get("EMAIL_NOTIFICACAO_ADMIN")

    if not all([host, porta, usuario_smtp, senha_smtp, destino]):
        # Notificação por e-mail não configurada — não faz nada.
        return

    try:

        mensagem = MIMEText(corpo, "plain", "utf-8")
        mensagem["Subject"] = assunto
        mensagem["From"] = usuario_smtp
        mensagem["To"] = destino

        with smtplib.SMTP_SSL(host, int(porta)) as servidor:
            servidor.login(usuario_smtp, senha_smtp)
            servidor.sendmail(usuario_smtp, [destino], mensagem.as_string())

    except Exception as erro:

        # Nunca deixa a compra falhar por causa do e-mail —
        # só registra no log do servidor.
        print("Erro ao enviar e-mail de notificação:", erro)


# ============================================================
# LOGIN DO ADMINISTRADOR
# ============================================================
# As credenciais podem ser trocadas sem mexer no código, definindo
# as variáveis de ambiente ADMIN_USUARIO_1 / ADMIN_SENHA_1 e
# ADMIN_USUARIO_2 / ADMIN_SENHA_2 (por exemplo, no painel do Render).
# Se não forem definidas, usa os valores abaixo como padrão.
# ============================================================

def _var_ambiente_limpa(nome, padrao):
    """
    Lê uma variável de ambiente e remove espaços/quebras de linha
    acidentais nas pontas (comuns ao colar no painel do Render,
    e que antes faziam o login falhar mesmo com a senha "certa").
    """

    valor = os.environ.get(nome, padrao)

    return valor.strip() if valor is not None else valor


ADMIN_USUARIOS = {
    _var_ambiente_limpa("ADMIN_USUARIO_1", "jmagno2011"):
        _var_ambiente_limpa("ADMIN_SENHA_1", "JM2011"),

    _var_ambiente_limpa("ADMIN_USUARIO_2", "admin"):
        _var_ambiente_limpa("ADMIN_SENHA_2", "admin123"),
}


# Sessões ativas do admin: token -> {"usuario":..., "expira_em":...}
# Fica em memória (não precisa de tabela no banco); se o servidor
# reiniciar, o admin só precisa logar de novo.

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
    """
    Decorador: protege uma rota exigindo um cabeçalho
    "Authorization: Bearer <token>" válido, obtido em /api/admin/login.
    """

    @wraps(funcao)
    def decorada(*args, **kwargs):

        limpar_sessoes_expiradas()

        cabecalho = request.headers.get("Authorization", "")

        if not cabecalho.startswith("Bearer "):

            return jsonify({
                "sucesso": False,
                "erro": "Login necessário."
            }), 401

        token_sessao = cabecalho[len("Bearer "):]

        with SESSOES_LOCK:
            sessao_valida = token_sessao in SESSOES_ADMIN

        if not sessao_valida:

            return jsonify({
                "sucesso": False,
                "erro": "Sessão inválida ou expirada. Faça login novamente."
            }), 401

        return funcao(*args, **kwargs)

    return decorada


# ============================================================
# BANCO DE DADOS
# ============================================================

def conectar():

    if MODO_POSTGRES:

        conexao_real = psycopg2.connect(
            os.environ["DATABASE_URL"],
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        return ConexaoCompativel(conexao_real)


    conexao = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    conexao.row_factory = sqlite3.Row

    return conexao


# ============================================================
# DATA/HORA
# ============================================================

def agora():

    return datetime.now()


def agora_texto():

    return agora().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def data_para_json(valor):
    """
    Formata uma data para mandar pro navegador, deixando explícito
    que é UTC (o servidor roda em UTC, seja local ou no Render).

    Sem isso, o navegador interpretava a data como se already fosse
    no fuso horário local da pessoa (ex: Brasil, UTC-3), fazendo o
    cronômetro de pagamento mostrar quase 3 horas em vez dos 5
    minutos reais.

    Aceita tanto um objeto datetime quanto o texto já salvo no
    banco (formato "AAAA-MM-DD HH:MM:SS").
    """

    if valor is None:
        return None

    if isinstance(valor, str):
        return valor.replace(" ", "T") + "Z"

    return valor.strftime("%Y-%m-%dT%H:%M:%SZ")


def hora_brasilia_texto(dt):
    """
    Só para textos lidos por humanos (e-mails de notificação) —
    nunca usar o resultado disso em cálculos ou comparações, é
    apenas um ajuste de exibição (o servidor roda em UTC).
    """

    if dt is None:
        return "-"

    ajustada = dt - timedelta(hours=3)

    return ajustada.strftime("%d/%m/%Y %H:%M:%S") + " (horário de Brasília)"


def texto_para_data(valor):

    if not valor:
        return None

    try:

        return datetime.strptime(
            valor,
            "%Y-%m-%d %H:%M:%S"
        )

    except ValueError:

        return None


# ============================================================
# CRIAÇÃO DO BANCO
# ============================================================

def criar_banco():

    conexao = conectar()

    cursor = conexao.cursor()


    # --------------------------------------------------------
    # TABELA DOS NÚMEROS
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS numeros (

            numero INTEGER PRIMARY KEY,

            status TEXT NOT NULL
                DEFAULT 'disponivel'

        )
    """)


    # --------------------------------------------------------
    # TABELA DAS COMPRAS
    # --------------------------------------------------------

    id_auto_incremento = (
        "id SERIAL PRIMARY KEY"
        if MODO_POSTGRES else
        "id INTEGER PRIMARY KEY AUTOINCREMENT"
    )

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS compras (

            {id_auto_incremento},

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


    # --------------------------------------------------------
    # CRIAR OS 1000 NÚMEROS
    # --------------------------------------------------------
    # "INSERT OR IGNORE" é exclusivo do SQLite — no PostgreSQL o
    # equivalente é "ON CONFLICT ... DO NOTHING".
    # --------------------------------------------------------

    if MODO_POSTGRES:

        sql_inserir_numero = """
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
            ON CONFLICT (numero) DO NOTHING
        """

    else:

        sql_inserir_numero = """
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
        """

    for numero in range(1, TOTAL_NUMEROS + 1):

        cursor.execute(
            sql_inserir_numero,
            (numero,)
        )


    conexao.commit()

    conexao.close()


# ============================================================
# EXPIRAR COMPRAS
# ============================================================

def expirar_compras():

    conexao = conectar()

    cursor = conexao.cursor()


    compras = cursor.execute("""
        SELECT
            id,
            token,
            numeros,
            status,
            expira_em
        FROM compras
        WHERE status IN (
            'pendente_pagamento',
            'comprovante_enviado'
        )
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


            # ---------------------------------------------
            # LIBERAR SOMENTE NÚMEROS PENDENTES
            # ---------------------------------------------

            for numero in numeros:

                cursor.execute("""
                    UPDATE numeros

                    SET status = 'disponivel'

                    WHERE numero = ?

                    AND status = 'pendente'
                """, (numero,))


            # ---------------------------------------------
            # MARCAR COMPRA COMO EXPIRADA
            # ---------------------------------------------

            cursor.execute("""
                UPDATE compras

                SET status = 'expirada'

                WHERE id = ?
            """, (compra["id"],))


    conexao.commit()

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


            # Verifica a cada 30 segundos

            time.sleep(30)


    thread = threading.Thread(
        target=verificar,
        daemon=True
    )

    thread.start()


# ============================================================
# VERIFICAÇÃO (usado pela hospedagem para checar se está no ar)
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def verificacao():

    return jsonify({
        "sucesso": True,
        "mensagem": "API da rifa está no ar."
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

    numeros = conexao.execute("""
        SELECT
            numero,
            status
        FROM numeros
        ORDER BY numero
    """).fetchall()

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

    resultado = conexao.execute("""
        SELECT
            numero,
            status
        FROM numeros
        WHERE numero = ?
    """, (numero,)).fetchone()

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


    if not isinstance(
        numeros,
        list
    ) or not numeros:

        return jsonify({
            "sucesso": False,
            "erro": "Nenhum número enviado."
        }), 400


    # --------------------------------------------------------
    # NORMALIZAR NÚMEROS
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # VALIDAR QUANTIDADE
    # --------------------------------------------------------

    if len(numeros) > TOTAL_NUMEROS:

        return jsonify({
            "sucesso": False,
            "erro": "Quantidade de números inválida."
        }), 400


    conexao = conectar()

    cursor = conexao.cursor()


    try:

        # ----------------------------------------------------
        # VERIFICAR TODOS
        # ----------------------------------------------------

        for numero in numeros:

            resultado = cursor.execute("""
                SELECT
                    status
                FROM numeros
                WHERE numero = ?
            """, (numero,)).fetchone()


            if resultado is None:

                conexao.rollback()
                conexao.close()

                return jsonify({
                    "sucesso": False,
                    "erro":
                        f"O número {numero} não existe."
                }), 404


            status = resultado["status"]


            if status != "disponivel":

                conexao.rollback()
                conexao.close()


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


        # ----------------------------------------------------
        # GERAR TOKEN DA COMPRA
        # ----------------------------------------------------

        token = str(
            uuid.uuid4()
        )


        criado_em = agora()


        # ----------------------------------------------------
        # PRAZO INICIAL
        #
        # 5 minutos para efetuar o pagamento.
        # ----------------------------------------------------

        expira_em = criado_em + timedelta(
            minutes=10
        )


        # ----------------------------------------------------
        # CRIAR COMPRA
        # ----------------------------------------------------
        # O "RETURNING id" só é necessário (e só funciona) no
        # PostgreSQL — o SQLite devolve o id inserido por
        # "cursor.lastrowid" em vez disso.
        # ----------------------------------------------------

        sql_criar_compra = """
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

        if MODO_POSTGRES:
            sql_criar_compra += " RETURNING id"

        cursor.execute(sql_criar_compra, (
            token,
            json.dumps(numeros),
            criado_em.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            expira_em.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))


        if MODO_POSTGRES:
            compra_id = cursor.fetchone()["id"]
        else:
            compra_id = cursor.lastrowid


        # ----------------------------------------------------
        # RESERVAR NÚMEROS
        # ----------------------------------------------------

        for numero in numeros:

            cursor.execute("""
                UPDATE numeros

                SET status = 'pendente'

                WHERE numero = ?

                AND status = 'disponivel'
            """, (numero,))


            if cursor.rowcount != 1:

                conexao.rollback()
                conexao.close()

                return jsonify({
                    "sucesso": False,
                    "erro":
                        f"O número {numero} acabou de ser reservado."
                }), 409


        conexao.commit()

        conexao.close()


        numeros_texto = ", ".join(
            str(numero).zfill(3) for numero in numeros
        )

        enviar_email_notificacao(
            "🎟️ Nova reserva na rifa",
            "Alguém acabou de reservar números e tem 5 minutos "
            "para pagar.\n\n"
            f"Código da compra: {token}\n"
            f"Números: {numeros_texto}\n"
            f"Quantidade: {len(numeros)}\n"
            f"Expira em: {hora_brasilia_texto(expira_em)}"
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


    except Exception as erro:

        conexao.rollback()
        conexao.close()

        print(
            "Erro ao reservar:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Erro interno ao reservar os números."
        }), 500


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
                data_para_json(compra["criado_em"]),

            "comprovante":
                compra["comprovante"],

            "comprovante_enviado_em":
                data_para_json(compra["comprovante_enviado_em"]),

            "expira_em":
                data_para_json(compra["expira_em"]),

            "confirmado_em":
                data_para_json(compra["confirmado_em"])

        }

    })


# ============================================================
# CONFIRMAR "JÁ REALIZEI O PAGAMENTO"
# ============================================================
# O comprovante em si não é mais enviado pelo site — a pessoa é
# redirecionada para o formulário do Google, que é onde o
# comprovante de verdade fica. Aqui só registramos que ela marcou
# como pago, e abrimos a janela de 24h para o admin conferir e
# confirmar no formulário.
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


    compra = cursor.execute("""
        SELECT
            id,
            numeros,
            status
        FROM compras
        WHERE token = ?
    """, (token,)).fetchone()


    if compra is None:

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro":
                "Compra não encontrada."
        }), 404


    if compra["status"] == "expirada":

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro":
                "O prazo desta compra expirou. "
                "Os números foram liberados."
        }), 410


    if compra["status"] == "confirmada":

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro":
                "Esta compra já foi confirmada."
        }), 409


    try:

        confirmado_em = agora()

        expira_em = confirmado_em + timedelta(
            hours=HORAS_EXPIRACAO
        )


        cursor.execute("""
            UPDATE compras

            SET

                status =
                    'comprovante_enviado',

                comprovante_enviado_em =
                    ?,

                expira_em =
                    ?

            WHERE token = ?
        """, (
            confirmado_em.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            expira_em.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            token
        ))


        conexao.commit()

        conexao.close()


        try:
            numeros_da_compra = json.loads(compra["numeros"])
            numeros_texto = ", ".join(
                str(numero).zfill(3) for numero in numeros_da_compra
            )
        except Exception:
            numeros_texto = "?"

        enviar_email_notificacao(
            "💰 Pagamento marcado como realizado",
            "Alguém marcou o pagamento como realizado e foi "
            "redirecionado para o formulário do Google. Confira "
            "lá a confirmação e o comprovante.\n\n"
            f"Código da compra: {token}\n"
            f"Números: {numeros_texto}"
        )


        return jsonify({

            "sucesso": True,

            "mensagem":
                "Pagamento marcado como realizado.",

            "expira_em":
                data_para_json(expira_em)

        })


    except Exception as erro:

        conexao.rollback()
        conexao.close()

        print(
            "Erro ao marcar pagamento como realizado:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro":
                "Não foi possível registrar a confirmação."
        }), 500


# ============================================================
# LIBERAR COMPRA
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


    token = dados.get(
        "token"
    )


    numeros = dados.get(
        "numeros",
        []
    )


    # --------------------------------------------------------
    # SE TIVER TOKEN, USAR A COMPRA
    # --------------------------------------------------------

    if token:

        conexao = conectar()

        cursor = conexao.cursor()


        compra = cursor.execute("""
            SELECT
                id,
                numeros,
                status
            FROM compras
            WHERE token = ?
        """, (token,)).fetchone()


        if compra is None:

            conexao.close()

            return jsonify({
                "sucesso": False,
                "erro": "Compra não encontrada."
            }), 404


        if compra["status"] == "confirmada":

            conexao.close()

            return jsonify({
                "sucesso": False,
                "erro":
                    "Esta compra já foi confirmada e não pode ser cancelada."
            }), 409


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

            SET status = 'cancelada'

            WHERE id = ?
        """, (compra["id"],))


        conexao.commit()

        conexao.close()


        return jsonify({

            "sucesso": True,

            "mensagem":
                "Compra cancelada e números liberados.",

            "liberados":
                numeros

        })


    # --------------------------------------------------------
    # COMPATIBILIDADE COM O SISTEMA ANTIGO
    # --------------------------------------------------------

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

                liberados.append(
                    numero
                )

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
                    f"Status atual: {resultado['status']}"
            })


    conexao.commit()

    conexao.close()


    return jsonify({

        "sucesso": True,

        "liberados":
            liberados,

        "nao_liberados":
            nao_liberados

    })


# ============================================================
# LOGIN / LOGOUT DO ADMIN
# ============================================================

@app.route(
    "/api/admin/login",
    methods=["POST"]
)
def login_admin():

    dados = request.get_json() or {}

    usuario = str(dados.get("usuario", "")).strip()
    senha = str(dados.get("senha", "")).strip()

    senha_correta = ADMIN_USUARIOS.get(usuario)

    if senha_correta is None or senha != senha_correta:

        # Log de diagnóstico (aparece nos "Logs" do Render). Nunca
        # imprime a senha digitada nem a senha certa — só ajuda a
        # confirmar se o usuário digitado bate com algum dos
        # cadastrados nas variáveis de ambiente.
        print(
            "[login admin] Tentativa falhou. Usuário recebido: "
            + repr(usuario)
            + " | Usuários cadastrados no momento: "
            + repr(list(ADMIN_USUARIOS.keys()))
        )

        return jsonify({
            "sucesso": False,
            "erro": "Usuário ou senha incorretos."
        }), 401

    token_sessao = secrets.token_hex(32)

    with SESSOES_LOCK:

        SESSOES_ADMIN[token_sessao] = {
            "usuario": usuario,
            "expira_em": datetime.now() + timedelta(hours=DURACAO_SESSAO_HORAS)
        }

    return jsonify({
        "sucesso": True,
        "token": token_sessao,
        "usuario": usuario
    })


@app.route(
    "/api/admin/logout",
    methods=["POST"]
)
def logout_admin():

    dados = request.get_json() or {}

    token_sessao = dados.get("token")

    with SESSOES_LOCK:
        SESSOES_ADMIN.pop(token_sessao, None)

    return jsonify({"sucesso": True})


# ============================================================
# ADMIN - ALTERAR STATUS
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


    resultado = cursor.execute("""
        SELECT
            numero
        FROM numeros
        WHERE numero = ?
    """, (numero,)).fetchone()


    if resultado is None:

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro": "Número não encontrado."
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
                data_para_json(compra["criado_em"]),

            "comprovante":
                compra["comprovante"],

            "comprovante_enviado_em":
                data_para_json(compra["comprovante_enviado_em"]),

            "expira_em":
                data_para_json(compra["expira_em"]),

            "confirmado_em":
                data_para_json(compra["confirmado_em"])

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


    compra = cursor.execute("""
        SELECT
            id,
            numeros,
            status
        FROM compras
        WHERE token = ?
    """, (token,)).fetchone()


    if compra is None:

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro": "Compra não encontrada."
        }), 404


    if compra["status"] == "expirada":

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro":
                "Esta compra já expirou."
        }), 409


    if compra["status"] == "cancelada":

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro":
                "Esta compra foi cancelada."
        }), 409


    if compra["status"] == "confirmada":

        conexao.close()

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


    # --------------------------------------------------------
    # MARCAR OS NÚMEROS COMO INDISPONÍVEIS
    # --------------------------------------------------------

    for numero in numeros:

        cursor.execute("""
            UPDATE numeros

            SET status = 'indisponivel'

            WHERE numero = ?

            AND status = 'pendente'
        """, (numero,))


    # --------------------------------------------------------
    # CONFIRMAR COMPRA
    # --------------------------------------------------------

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

    conexao.close()


    return jsonify({

        "sucesso": True,

        "mensagem":
            "Pagamento confirmado.",

        "numeros":
            numeros

    })


# ============================================================
# ADMIN - REJEITAR / CANCELAR COMPRA
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


    compra = cursor.execute("""
        SELECT
            id,
            numeros,
            status
        FROM compras
        WHERE token = ?
    """, (token,)).fetchone()


    if compra is None:

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro": "Compra não encontrada."
        }), 404


    if compra["status"] == "confirmada":

        conexao.close()

        return jsonify({
            "sucesso": False,
            "erro":
                "Uma compra confirmada não pode ser rejeitada."
        }), 409


    try:

        numeros = json.loads(
            compra["numeros"]
        )

    except Exception:

        numeros = []


    # --------------------------------------------------------
    # LIBERAR NÚMEROS
    # --------------------------------------------------------

    for numero in numeros:

        cursor.execute("""
            UPDATE numeros

            SET status = 'disponivel'

            WHERE numero = ?

            AND status = 'pendente'
        """, (numero,))


    # --------------------------------------------------------
    # CANCELAR COMPRA
    # --------------------------------------------------------

    cursor.execute("""
        UPDATE compras

        SET status = 'cancelada'

        WHERE token = ?
    """, (token,))


    conexao.commit()

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

        quantidade = linha["quantidade"]


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
        ] = linha["quantidade"]


    total_arrecadado = (
        estatisticas_numeros["indisponiveis"] *
        PRECO_NUMERO
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
# ERRO DE ARQUIVO GRANDE
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
# ERROS GERAIS
# ============================================================

@app.errorhandler(500)
def erro_servidor(erro):

    return jsonify({

        "sucesso": False,

        "erro":
            "Erro interno do servidor."

    }), 500


# ============================================================
# INICIALIZAÇÃO (roda tanto com "python app.py" quanto com
# gunicorn/produção, já que nesse segundo caso o bloco
# "if __name__ == '__main__'" abaixo nunca é executado)
# ============================================================

criar_banco()


# --------------------------------------------------------
# INICIAR VERIFICADOR AUTOMÁTICO DE EXPIRAÇÃO
# --------------------------------------------------------
# O Flask debug (quando ligado) cria um processo principal e um
# processo "reloader". Para não duplicar a thread nesse caso:

if (
    os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    or os.environ.get("FLASK_DEBUG", "0") != "1"
):

    iniciar_expiracao_automatica()


# ============================================================
# INICIAR SERVIDOR (só quando executado diretamente, ex:
# "python app.py" — em produção quem inicia é o gunicorn,
# conforme o Procfile)
# ============================================================

if __name__ == "__main__":

    print()
    print("====================================")
    print("       SERVIDOR DA RIFA")
    print("====================================")
    print()

    print(
        "API: http://127.0.0.1:5000"
    )

    print()

    print("Endpoints:")
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
        "Upload máximo: 10 MB"
    )

    print(
        "Formatos: JPG, JPEG, PNG, WEBP, PDF"
    )

    print(
        "Expiração após comprovante: 24 horas"
    )

    print()


    porta = int(
        os.environ.get("PORT", 5000)
    )


    modo_debug = (
        os.environ.get("FLASK_DEBUG", "0") == "1"
    )


    app.run(

        host="0.0.0.0",

        port=porta,

        debug=modo_debug

    )
