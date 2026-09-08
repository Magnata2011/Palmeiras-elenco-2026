# Ação Solidária Marcelo Nunes — Rifa do Palmeiras

Site de rifa com backend próprio (reserva de números, timer, painel
administrativo com login, confirmação de pagamento e formulário do
Google para o comprovante).

Este projeto tem duas partes publicadas **separadamente**:

1. **Backend** (`app.py`) — guarda as reservas, controla os prazos e o
   login do admin. É um programa Python, hospedado no **Render**.
2. **Frontend** (`index.html`, `pagamento.html`, `Admin.html` e os
   arquivos `.css`/`.js`/`imagens/`) — hospedado de graça no
   **GitHub Pages**.

---

## Testando no seu computador

**Terminal 1 — Backend:**

```bash
python -m venv venv
source venv/bin/activate      # no Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Sem nenhuma configuração extra, ele usa um arquivo local (`rifa.db`,
SQLite) — perfeito pra testar. Fica em `http://127.0.0.1:5000`.

**Terminal 2 — Frontend:**

```bash
python -m http.server 8000
```

Acesse `http://localhost:8000/index.html`.

---

## Publicando de verdade (Render + GitHub Pages)

### Passo 1 — Criar o banco de dados PostgreSQL (importante!)

⚠️ **Não pule esta parte.** O Render apaga o sistema de arquivos do
backend (incluindo um banco SQLite comum) toda vez que o serviço
recebe um deploy novo, reinicia ou "dorme" por inatividade — o que
faria números vendidos voltarem a ficar "disponíveis" sozinhos. Por
isso o backend já vem pronto para usar PostgreSQL em produção, que é
um banco separado e não some nesses casos.

1. No painel do Render: **New +** → **PostgreSQL**.
2. Dê um nome (ex: `rifa-banco`), plano **Free**, crie.
3. Espere ficar "Available" e copie o campo **Internal Database URL**
   (começa com `postgresql://...`).

> No plano gratuito, esse banco Postgres expira automaticamente 30
> dias após a criação. Perto da data, o Render avisa por e-mail —
> quando isso acontecer, crie um novo banco gratuito e atualize a
> variável `DATABASE_URL` (Passo 3) com a nova URL, ou mude o serviço
> para o plano pago (a partir de ~US$6/mês) pra não precisar repetir
> isso. Pra uma campanha de alguns meses, o plano grátis com renovação
> a cada 30 dias resolve tranquilo.

### Passo 2 — Publicar o backend

1. [render.com](https://render.com) → **New +** → **Web Service** →
   escolha o repositório do GitHub.
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `gunicorn app:app`
4. Em **Environment**, adicione:

   | Variável | Valor |
   |---|---|
   | `DATABASE_URL` | a Internal Database URL copiada no Passo 1 |
   | `ORIGENS_PERMITIDAS` | `https://SEU-DOMINIO` (veja Passo 5) |
   | `PRECO_NUMERO` | igual ao `PRECO` do `config.js` |
   | `TOTAL_NUMEROS` | igual ao `TOTAL_NUMEROS` do `config.js` |
   | `ADMIN_USUARIO_1` / `ADMIN_SENHA_1` | login 1 do painel admin |
   | `ADMIN_USUARIO_2` / `ADMIN_SENHA_2` | login 2 do painel admin |

5. Crie e espere terminar. Você recebe uma URL tipo
   `https://sua-rifa-api.onrender.com`.

### Passo 3 — Apontar o `config.js` pro backend

```js
API_URL: "https://sua-rifa-api.onrender.com",
```

### Passo 4 — Ativar o GitHub Pages

**Settings → Pages** → Source: branch `main`, pasta `/ (root)`.

### Passo 5 — Domínio próprio (`.com.br` do registro.br)

Você já tem o domínio registrado — falta só apontar ele pro GitHub
Pages e avisar o backend que esse domínio agora existe.

**5.1. No GitHub:**

No repositório, vá em **Settings → Pages → Custom domain** e digite:

```
acaosolidariamarcelonunes.com.br
```

Salve. Isso cria automaticamente um arquivo `CNAME` no repositório
com esse endereço dentro.

**5.2. No registro.br:**

1. Entre em [registro.br](https://registro.br) → **Painel** → seu
   domínio → **Editar Zona / DNS**.
2. Adicione estes registros (mantendo os que já existirem, se houver):

   | Tipo | Nome/Host | Valor/Aponta para |
   |---|---|---|
   | A | @ (ou em branco) | `185.199.108.153` |
   | A | @ (ou em branco) | `185.199.109.153` |
   | A | @ (ou em branco) | `185.199.110.153` |
   | A | @ (ou em branco) | `185.199.111.153` |
   | CNAME | www | `magnata2011.github.io.` (com ponto no final) |

   Os 4 registros **A** são os servidores do próprio GitHub Pages —
   sempre esses mesmos IPs, não muda de projeto pra projeto. O
   **CNAME** do `www` é opcional, mas deixa
   `www.acaosolidariamarcelonunes.com.br` funcionando também.

3. Salve. A propagação do DNS pode levar de alguns minutos até
   ~24-48 horas (geralmente é bem mais rápido).

**5.3. De volta no GitHub:**

Depois que o DNS propagar, volte em **Settings → Pages** e marque
**Enforce HTTPS** (pode demorar um pouco pra ficar disponível — o
GitHub precisa emitir o certificado SSL primeiro).

**5.4. MUITO IMPORTANTE — atualizar o Render:**

Assim que o domínio próprio estiver no ar, o "endereço" que o
navegador manda pro backend muda de
`https://magnata2011.github.io` para
`https://acaosolidariamarcelonunes.com.br`. Se você não atualizar o
Render, o **CORS vai bloquear tudo** (o site abre, mas nenhum botão
funciona — reservar, pagar, nada).

No Render, vá em **Environment** e atualize:

```
ORIGENS_PERMITIDAS=https://acaosolidariamarcelonunes.com.br,https://www.acaosolidariamarcelonunes.com.br,https://magnata2011.github.io
```

(Deixar o endereço antigo do GitHub Pages na lista, separado por
vírgula, não atrapalha — só garante que o site continua acessível
por ambos os endereços enquanto o domínio novo propaga.)

---

## Sobre o painel do administrador

Acessível pelo botão **Administrador** no canto do site principal.
Login verificado no backend (com sessão por token) — mesmo sendo um
site público, ninguém entra sem usuário/senha corretos.

**Credenciais padrão** (troque via `ADMIN_USUARIO_1/2` e
`ADMIN_SENHA_1/2` no Render, como no Passo 2):

| Usuário | Senha |
|---|---|
| `jmagno2011` | `JM2011` |
| `admin` | `admin123` |

As sessões de login ficam em memória — se o backend reiniciar (o que
o Render faz sozinho de vez em quando), o admin só precisa entrar de
novo. Isso não afeta os dados da rifa (números, compras), que agora
ficam salvos no PostgreSQL, não na memória.

---

## Notificações para o administrador

- **No navegador**: com o `Admin.html` aberto numa aba, toca um som e
  aparece uma notificação quando chega um novo pagamento marcado.
- **Por e-mail** (opcional): configure no Render `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USUARIO`, `SMTP_SENHA` (senha de app do Gmail,
  gerada em https://myaccount.google.com/apppasswords) e
  `EMAIL_NOTIFICACAO_ADMIN`.

---

## Como funciona o comprovante

A pessoa não envia mais o comprovante direto no site. Ao clicar em
"Já realizei o pagamento", o site avisa o backend (pra abrir a janela
de 24h) e redireciona automaticamente para o formulário do Google
configurado em `GOOGLE_FORM_URL` no `config.js` — é lá que o
comprovante de verdade é enviado.

## Imagens

- `historia-1.jpg` — Professor Marcelo Nunes (usada no banner
  principal).
- `banner-camisa.jpg` — ele segurando a camisa autografada (usada na
  caixa "Conheça a história").
- `fotocampo.jpg` — a camisa atrás da rede verde (banner 2).
- `qrcode.jpeg` — QR Code do Pix.

Pra trocar qualquer uma, é só substituir o arquivo mantendo o mesmo
nome, ou trocar o nome nas referências dentro do `index.html` /
`pagamento.html`.
