// =====================================
// CONFIGURAÇÕES (vêm do config.js)
// =====================================

const API = RIFA_CONFIG.API_URL;


// =====================================================================
// AUTENTICAÇÃO DO PAINEL
// =====================================================================
// Se não tiver um token de login guardado (feito na tela inicial),
// manda a pessoa de volta pro site em vez de mostrar o painel.
// =====================================================================

const TOKEN_ADMIN = sessionStorage.getItem("rifaAdminToken");
const USUARIO_ADMIN_LOGADO = sessionStorage.getItem("rifaAdminUsuario");

if (!TOKEN_ADMIN) {

    window.location.href = "index.html";

}


function cabecalhosAdmin(extras) {

    return Object.assign(
        { "Authorization": "Bearer " + TOKEN_ADMIN },
        extras || {}
    );

}


// Fetch que já inclui o token de login e trata sessão expirada
// (manda pra tela inicial se o backend responder 401).

async function fetchAdmin(url, opcoes) {

    const opcoesFinais = Object.assign({}, opcoes);

    opcoesFinais.headers = cabecalhosAdmin(opcoesFinais.headers);

    const resposta = await fetch(url, opcoesFinais);

    if (resposta.status === 401) {

        sessionStorage.removeItem("rifaAdminToken");
        sessionStorage.removeItem("rifaAdminUsuario");

        alert("Sua sessão expirou. Faça login novamente.");

        window.location.href = "index.html";

        throw new Error("Sessão expirada.");

    }

    return resposta;

}


// =====================================
// USUÁRIO LOGADO E SAIR
// =====================================

const usuarioLogadoTexto = document.getElementById("usuarioLogadoTexto");
const sairAdmin = document.getElementById("sairAdmin");

if (usuarioLogadoTexto && USUARIO_ADMIN_LOGADO) {

    usuarioLogadoTexto.textContent = "Logado como: " + USUARIO_ADMIN_LOGADO;

}

if (sairAdmin) {

    sairAdmin.addEventListener("click", async () => {

        try {

            await fetch(`${API}/api/admin/logout`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: TOKEN_ADMIN })
            });

        } catch (erro) {

            console.error("Erro ao sair:", erro);

        } finally {

            sessionStorage.removeItem("rifaAdminToken");
            sessionStorage.removeItem("rifaAdminUsuario");

            window.location.href = "index.html";

        }

    });

}


// =====================================================================
// NOTIFICAÇÃO DE NOVOS COMPROVANTES
// =====================================================================
// Enquanto esta aba estiver aberta, toca um som e mostra uma
// notificação do navegador quando um novo comprovante chega.
// (Isso não substitui olhar o painel de vez em quando — é um aviso
// extra, não uma garantia de que você vai ver na hora.)
// =====================================================================

let tokensComprovanteNotificados = new Set(
    JSON.parse(sessionStorage.getItem("rifaAdminNotificados") || "[]")
);

let primeiraCargaCompras = true;

if (typeof Notification !== "undefined" && Notification.permission === "default") {

    Notification.requestPermission();

}


function salvarTokensNotificados() {

    sessionStorage.setItem(
        "rifaAdminNotificados",
        JSON.stringify([...tokensComprovanteNotificados])
    );

}


function tocarSomNotificacao() {

    try {

        const ContextoAudio = window.AudioContext || window.webkitAudioContext;

        if (!ContextoAudio) {
            return;
        }

        const contexto = new ContextoAudio();
        const agora = contexto.currentTime;

        [880, 1046].forEach((frequencia, indice) => {

            const oscilador = contexto.createOscillator();
            const ganho = contexto.createGain();

            oscilador.connect(ganho);
            ganho.connect(contexto.destination);

            oscilador.type = "sine";
            oscilador.frequency.value = frequencia;

            const inicio = agora + indice * 0.18;

            ganho.gain.setValueAtTime(0.001, inicio);
            ganho.gain.exponentialRampToValueAtTime(0.2, inicio + 0.02);
            ganho.gain.exponentialRampToValueAtTime(0.001, inicio + 0.15);

            oscilador.start(inicio);
            oscilador.stop(inicio + 0.16);

        });

    } catch (erro) {

        console.error("Não foi possível tocar o som de notificação:", erro);

    }

}


function notificarNovoComprovante(compra) {

    tocarSomNotificacao();

    if (
        typeof Notification !== "undefined" &&
        Notification.permission === "granted"
    ) {

        new Notification("💰 Novo comprovante recebido!", {
            body:
                "Compra " + compra.token +
                " está aguardando confirmação."
        });

    }

}


function verificarNovasCompras(compras) {

    const comprovantesEnviados = compras.filter(
        compra => compra.status === "comprovante_enviado"
    );

    if (primeiraCargaCompras) {

        // Na primeira vez que o painel carrega, só marca o que já
        // existe como "visto" — não notifica retroativamente.

        comprovantesEnviados.forEach(compra => {
            tokensComprovanteNotificados.add(compra.token);
        });

        salvarTokensNotificados();

        primeiraCargaCompras = false;

        return;

    }

    let houveNovidade = false;

    comprovantesEnviados.forEach(compra => {

        if (!tokensComprovanteNotificados.has(compra.token)) {

            notificarNovoComprovante(compra);

            tokensComprovanteNotificados.add(compra.token);

            houveNovidade = true;

        }

    });

    if (houveNovidade) {
        salvarTokensNotificados();
    }

}


// =====================================
// ELEMENTOS
// =====================================

const numeroPesquisa =
    document.getElementById(
        "numeroPesquisa"
    );

const buscarNumero =
    document.getElementById(
        "buscarNumero"
    );

const resultadoNumero =
    document.getElementById(
        "resultadoNumero"
    );

const numeroResultado =
    document.getElementById(
        "numeroResultado"
    );

const statusResultado =
    document.getElementById(
        "statusResultado"
    );

const mensagem =
    document.getElementById(
        "mensagem"
    );

const listaNumeros =
    document.getElementById(
        "listaNumeros"
    );

const atualizar =
    document.getElementById(
        "atualizar"
    );

const totalDisponiveis =
    document.getElementById(
        "totalDisponiveis"
    );

const totalPendentes =
    document.getElementById(
        "totalPendentes"
    );

const totalIndisponiveis =
    document.getElementById(
        "totalIndisponiveis"
    );

const totalNumeros =
    document.getElementById(
        "totalNumeros"
    );

const marcarDisponivel =
    document.getElementById(
        "marcarDisponivel"
    );

const marcarPendente =
    document.getElementById(
        "marcarPendente"
    );

const marcarIndisponivel =
    document.getElementById(
        "marcarIndisponivel"
    );


// =====================================
// VARIÁVEL ATUAL
// =====================================

let numeroAtual =
    null;


// =====================================
// FORMATAR NÚMERO
// =====================================

function formatarNumero(
    numero
) {

    return String(numero)
        .padStart(3, "0");

}


// =====================================
// NOME DO STATUS
// =====================================

function nomeStatus(
    status
) {

    if (
        status === "disponivel"
    ) {

        return "🟢 Disponível";

    }


    if (
        status === "pendente"
    ) {

        return "🟠 Pendente";

    }


    if (
        status === "indisponivel"
    ) {

        return "🔴 Comprado";

    }


    return status;

}


// =====================================
// CARREGAR NÚMEROS
// =====================================

async function carregarNumeros() {

    try {

        const resposta =
            await fetch(
                `${API}/api/numeros`
            );


        if (
            !resposta.ok
        ) {

            throw new Error(
                "Erro ao buscar números."
            );

        }


        const dados =
            await resposta.json();


        renderizarNumeros(
            dados
        );


        atualizarEstatisticas(
            dados
        );

    }

    catch (erro) {

        console.error(
            erro
        );

        mensagem.textContent =
            "Erro ao conectar com o servidor.";

    }

}


// =====================================
// RENDERIZAR NÚMEROS
// =====================================

function renderizarNumeros(
    dados
) {

    listaNumeros.innerHTML =
        "";


    dados
        .sort(
            (a, b) =>
                Number(a.numero) -
                Number(b.numero)
        )
        .forEach(
            item => {

                const numero =
                    Number(
                        item.numero
                    );


                const botao =
                    document.createElement(
                        "button"
                    );


                botao.type =
                    "button";


                botao.className =
                    "numero-admin " +
                    item.status;


                botao.textContent =
                    formatarNumero(
                        numero
                    );


                botao.title =
                    nomeStatus(
                        item.status
                    );


                botao.addEventListener(
                    "click",
                    () => {

                        selecionarNumero(
                            numero
                        );

                    }
                );


                listaNumeros.appendChild(
                    botao
                );

            }
        );

}


// =====================================
// ESTATÍSTICAS
// =====================================

function atualizarEstatisticas(
    dados
) {

    let disponiveis = 0;

    let pendentes = 0;

    let indisponiveis = 0;


    dados.forEach(
        item => {

            if (
                item.status ===
                "disponivel"
            ) {

                disponiveis++;

            }


            if (
                item.status ===
                "pendente"
            ) {

                pendentes++;

            }


            if (
                item.status ===
                "indisponivel"
            ) {

                indisponiveis++;

            }

        }
    );


    totalDisponiveis.textContent =
        disponiveis;


    totalPendentes.textContent =
        pendentes;


    totalIndisponiveis.textContent =
        indisponiveis;


    totalNumeros.textContent =
        dados.length;

}


// =====================================
// SELECIONAR NÚMERO
// =====================================

async function selecionarNumero(
    numero
) {

    numeroAtual =
        numero;


    numeroResultado.textContent =
        formatarNumero(
            numero
        );


    resultadoNumero.style.display =
        "block";


    mensagem.textContent =
        "Carregando status...";


    try {

        const resposta =
            await fetch(
                `${API}/api/numeros/${numero}`
            );


        if (
            !resposta.ok
        ) {

            throw new Error(
                "Número não encontrado."
            );

        }


        const dados =
            await resposta.json();


        statusResultado.textContent =
            nomeStatus(
                dados.status
            );


        mensagem.textContent =
            "";


    }

    catch (erro) {

        console.error(
            erro
        );


        mensagem.textContent =
            "Não foi possível consultar este número.";

    }

}


// =====================================
// BUSCAR
// =====================================

buscarNumero.addEventListener(
    "click",
    () => {

        const numero =
            Number(
                numeroPesquisa.value
            );


        if (
            !Number.isInteger(numero) ||
            numero < 1 ||
            numero > 1000
        ) {

            mensagem.textContent =
                "Digite um número entre 1 e 1000.";

            resultadoNumero.style.display =
                "none";

            return;

        }


        selecionarNumero(
            numero
        );

    }
);


// =====================================
// ENTER NA PESQUISA
// =====================================

numeroPesquisa.addEventListener(
    "keydown",
    evento => {

        if (
            evento.key === "Enter"
        ) {

            buscarNumero.click();

        }

    }
);


// =====================================
// ALTERAR STATUS
// =====================================

async function alterarStatus(
    status
) {

    if (
        numeroAtual === null
    ) {

        alert(
            "Selecione um número primeiro."
        );

        return;

    }


    const botoes =
        [
            marcarDisponivel,
            marcarPendente,
            marcarIndisponivel
        ];


    botoes.forEach(
        botao => {

            botao.disabled =
                true;

        }
    );


    try {

        const resposta =
            await fetchAdmin(
                `${API}/api/admin/numeros/${numeroAtual}`,
                {
                    method: "PUT",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            status:
                                status
                        })
                }
            );


        const dados =
            await resposta.json();


        if (
            !resposta.ok
        ) {

            throw new Error(
                dados.erro ||
                "Não foi possível alterar o status."
            );

        }


        statusResultado.textContent =
            nomeStatus(
                dados.status
            );


        mensagem.textContent =
            `Número ${formatarNumero(numeroAtual)} atualizado com sucesso.`;


        await carregarNumeros();

    }

    catch (erro) {

        console.error(
            erro
        );


        mensagem.textContent =
            erro.message;

    }


    finally {

        botoes.forEach(
            botao => {

                botao.disabled =
                    false;

            }
        );

    }

}


// =====================================
// BOTÕES DE STATUS
// =====================================

marcarDisponivel.addEventListener(
    "click",
    () => {

        alterarStatus(
            "disponivel"
        );

    }
);


marcarPendente.addEventListener(
    "click",
    () => {

        alterarStatus(
            "pendente"
        );

    }
);


marcarIndisponivel.addEventListener(
    "click",
    () => {

        alterarStatus(
            "indisponivel"
        );

    }
);


// =====================================
// ATUALIZAR
// =====================================

atualizar.addEventListener(
    "click",
    () => {

        carregarNumeros();

    }
);


// =====================================================================
// SEÇÃO: COMPRAS E COMPROVANTES
// =====================================================================

const listaCompras = document.getElementById("listaCompras");
const mensagemCompras = document.getElementById("mensagemCompras");
const totalArrecadado = document.getElementById("totalArrecadado");
const atualizarCompras = document.getElementById("atualizarCompras");
const botoesFiltro = document.querySelectorAll(".filtro-compra");

let filtroAtual = "pendentes";
let compraEmAcao = false;


// =====================================
// NOME DO STATUS DA COMPRA
// =====================================

function nomeStatusCompra(status) {

    const nomes = {
        pendente_pagamento: "Aguardando pagamento",
        comprovante_enviado: "Comprovante enviado",
        confirmada: "Confirmada",
        cancelada: "Cancelada",
        expirada: "Expirada"
    };

    return nomes[status] || status;

}


// =====================================
// CARREGAR COMPRAS
// =====================================

async function carregarCompras() {

    try {

        const resposta = await fetchAdmin(`${API}/api/admin/compras`, {
            cache: "no-store"
        });

        if (!resposta.ok) {
            throw new Error("Erro ao buscar compras.");
        }

        const dados = await resposta.json();

        verificarNovasCompras(dados.compras || []);

        renderizarCompras(dados.compras || []);

        mensagemCompras.textContent = "";

    } catch (erro) {

        console.error(erro);
        mensagemCompras.textContent =
            "Erro ao conectar com o servidor.";

    }


    try {

        const resposta = await fetchAdmin(`${API}/api/admin/estatisticas`, {
            cache: "no-store"
        });

        if (resposta.ok) {

            const dados = await resposta.json();

            if (typeof dados.total_arrecadado === "number") {

                totalArrecadado.textContent =
                    dados.total_arrecadado.toLocaleString("pt-BR", {
                        style: "currency",
                        currency: "BRL"
                    });

            }

        }

    } catch (erro) {

        console.error(erro);

    }

}


// =====================================
// RENDERIZAR COMPRAS
// =====================================

function renderizarCompras(compras) {

    // "Precisam de atenção" = status que exigem alguma ação do
    // administrador (comprovante recém-enviado, esperando análise).

    const filtradas = compras.filter(compra => {

        if (filtroAtual === "todas") {
            return true;
        }

        return compra.status === "comprovante_enviado";

    });


    listaCompras.innerHTML = "";


    if (filtradas.length === 0) {

        const vazio = document.createElement("p");

        vazio.className = "compra-vazio";

        vazio.textContent =
            filtroAtual === "pendentes"
                ? "Nenhum comprovante aguardando análise no momento."
                : "Nenhuma compra encontrada.";

        listaCompras.appendChild(vazio);

        return;

    }


    filtradas.forEach(compra => {

        listaCompras.appendChild(
            criarCartaoCompra(compra)
        );

    });

}


// =====================================
// CRIAR CARTÃO DE UMA COMPRA
// =====================================

function criarCartaoCompra(compra) {

    const card = document.createElement("div");

    card.className = "compra-card";


    // ---------- Topo: badge + data ----------

    const topo = document.createElement("div");

    topo.className = "compra-card-topo";


    const badge = document.createElement("span");

    badge.className = "compra-badge " + compra.status;

    badge.textContent = nomeStatusCompra(compra.status);

    topo.appendChild(badge);


    const dataInfo = document.createElement("span");

    dataInfo.className = "compra-info";

    dataInfo.textContent = "Criada em: " + (compra.criado_em || "-");

    topo.appendChild(dataInfo);

    card.appendChild(topo);


    // ---------- Números ----------

    const numerosDiv = document.createElement("div");

    numerosDiv.className = "compra-numeros-lista";

    (compra.numeros || []).forEach(numero => {

        const chip = document.createElement("span");

        chip.className = "compra-numero-chip";

        chip.textContent = String(numero).padStart(3, "0");

        numerosDiv.appendChild(chip);

    });

    card.appendChild(numerosDiv);


    // ---------- Informações ----------

    const quantidade = (compra.numeros || []).length;

    const total = quantidade * RIFA_CONFIG.PRECO;

    const info = document.createElement("div");

    info.className = "compra-info";

    info.innerHTML =
        "<strong>Código:</strong> " + compra.token + "<br>" +
        "<strong>Quantidade:</strong> " + quantidade +
        (quantidade === 1 ? " número" : " números") + "<br>" +
        "<strong>Valor:</strong> " +
        total.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) +
        (
            compra.comprovante_enviado_em
                ? "<br><strong>Comprovante enviado em:</strong> " +
                  compra.comprovante_enviado_em
                : ""
        );

    card.appendChild(info);


    // ---------- Ações ----------

    const acoes = document.createElement("div");

    acoes.className = "compra-acoes";


    // O acesso ao arquivo do comprovante pelo painel foi removido —
    // a confirmação do pagamento agora passa pelo formulário do
    // Google, então o admin não precisa mais abrir o arquivo aqui.


    if (compra.status === "comprovante_enviado") {

        const botaoConfirmar = document.createElement("button");

        botaoConfirmar.type = "button";

        botaoConfirmar.className = "botao-confirmar-compra";

        botaoConfirmar.textContent = "✔ Confirmar pagamento";

        botaoConfirmar.addEventListener("click", () => {
            confirmarCompraAdmin(compra.token);
        });

        acoes.appendChild(botaoConfirmar);


        const botaoRejeitar = document.createElement("button");

        botaoRejeitar.type = "button";

        botaoRejeitar.className = "botao-rejeitar-compra";

        botaoRejeitar.textContent = "✖ Rejeitar / liberar números";

        botaoRejeitar.addEventListener("click", () => {
            rejeitarCompraAdmin(compra.token);
        });

        acoes.appendChild(botaoRejeitar);

    }


    if (acoes.children.length > 0) {
        card.appendChild(acoes);
    }


    return card;

}


// =====================================
// CONFIRMAR COMPRA (ADMIN)
// =====================================

async function confirmarCompraAdmin(token) {

    if (compraEmAcao) {
        return;
    }

    const confirmarAcao = confirm(
        "Confirmar esta compra? Os números serão marcados como " +
        "comprados definitivamente."
    );

    if (!confirmarAcao) {
        return;
    }

    compraEmAcao = true;

    try {

        const resposta = await fetchAdmin(
            `${API}/api/admin/compras/${encodeURIComponent(token)}/confirmar`,
            { method: "PUT" }
        );

        const resultado = await resposta.json();

        if (!resposta.ok || !resultado.sucesso) {
            throw new Error(resultado.erro || "Não foi possível confirmar.");
        }

        await carregarCompras();
        await carregarNumeros();

    } catch (erro) {

        console.error(erro);
        alert(erro.message);

    } finally {

        compraEmAcao = false;

    }

}


// =====================================
// REJEITAR COMPRA (ADMIN)
// =====================================

async function rejeitarCompraAdmin(token) {

    if (compraEmAcao) {
        return;
    }

    const confirmarAcao = confirm(
        "Rejeitar esta compra? Os números voltarão a ficar " +
        "disponíveis para outras pessoas. Use isso quando o " +
        "comprovante enviado não for válido."
    );

    if (!confirmarAcao) {
        return;
    }

    compraEmAcao = true;

    try {

        const resposta = await fetchAdmin(
            `${API}/api/admin/compras/${encodeURIComponent(token)}/rejeitar`,
            { method: "PUT" }
        );

        const resultado = await resposta.json();

        if (!resposta.ok || !resultado.sucesso) {
            throw new Error(resultado.erro || "Não foi possível rejeitar.");
        }

        await carregarCompras();
        await carregarNumeros();

    } catch (erro) {

        console.error(erro);
        alert(erro.message);

    } finally {

        compraEmAcao = false;

    }

}


// =====================================
// FILTROS
// =====================================

botoesFiltro.forEach(botao => {

    botao.addEventListener("click", () => {

        botoesFiltro.forEach(b => b.classList.remove("ativo"));
        botao.classList.add("ativo");

        filtroAtual = botao.dataset.filtro;

        carregarCompras();

    });

});


atualizarCompras.addEventListener("click", () => {
    carregarCompras();
});


// =====================================
// INICIAR
// =====================================

carregarNumeros();
carregarCompras();

setInterval(carregarCompras, 15000);
