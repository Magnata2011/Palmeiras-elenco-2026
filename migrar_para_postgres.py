"""
Copia os dados de um rifa.db (SQLite) para o PostgreSQL.
O arquivo rifa.db é aberto SOMENTE PARA LEITURA (não é alterado).

Uso:
    pip install psycopg2-binary
    DATABASE_URL="postgresql://..." python migrar_para_postgres.py caminho/rifa.db

Use a "External Database URL" do Render (a Internal só funciona dentro do Render).
Pode rodar mais de uma vez: registros já existentes são ignorados.
"""
import os, sys, sqlite3
import psycopg2

if len(sys.argv) != 2 or not os.environ.get("DATABASE_URL"):
    sys.exit(__doc__)

origem = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
origem.row_factory = sqlite3.Row

pg = psycopg2.connect(os.environ["DATABASE_URL"])
cur = pg.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS numeros (
    numero INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'disponivel')""")
cur.execute("""CREATE TABLE IF NOT EXISTS compras (
    id SERIAL PRIMARY KEY, token TEXT NOT NULL UNIQUE, numeros TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente_pagamento', criado_em TEXT NOT NULL,
    comprovante TEXT, comprovante_enviado_em TEXT, expira_em TEXT, confirmado_em TEXT)""")

n = 0
for r in origem.execute("SELECT numero, status FROM numeros"):
    cur.execute("""INSERT INTO numeros (numero, status) VALUES (%s, %s)
                   ON CONFLICT (numero) DO UPDATE SET status = EXCLUDED.status""",
                (r["numero"], r["status"]))
    n += 1

c = 0
for r in origem.execute("SELECT * FROM compras ORDER BY id"):
    cur.execute("""INSERT INTO compras (id, token, numeros, status, criado_em, comprovante,
                   comprovante_enviado_em, expira_em, confirmado_em)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (r["id"], r["token"], r["numeros"], r["status"], r["criado_em"],
                 r["comprovante"], r["comprovante_enviado_em"], r["expira_em"], r["confirmado_em"]))
    c += 1

# ajusta o contador do id para não colidir com os ids copiados
cur.execute("SELECT setval(pg_get_serial_sequence('compras','id'), "
            "COALESCE((SELECT MAX(id) FROM compras), 1), (SELECT COUNT(*) FROM compras) > 0)")
pg.commit()
print(f"Migrados: {n} números, {c} compras.")
