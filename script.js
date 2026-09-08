// =====================================
// CONFIGURAÇÕES (vêm do config.js)
// =====================================

const API = RIFA_CONFIG.API_URL;
const PRECO = RIFA_CONFIG.PRECO;


// =====================================
// SELEÇÃO DO USUÁRIO
// =====================================

let selecionados =
    JSON.parse(
        localStorage.getItem("rifaSelecionados")
    ) || [];

selecionados = selecionados
    .map(Number)
    .filter(Number.isInteger);


// =====================================
// ELEMENTOS
// =====================================

const grade = document.getElementById("numeros");
const barraNumeros = document.getElementById("numerosSelecionados");
const quantidade = document.getElementById("quantidadeSelecionada");
const valor = document.getElementById("valorTotal");
const confirmar = document.getElementById("confirmar");
const modal = document.getElementById("confirmacao");
const listaModal = document.getElementById("listaConfirmacao");
const quantidadeModal = document.getElementById("quantidadeConfirmacao");
const totalModal = document.getElementById("totalConfirmacao");
const continuarSelecionando = document.getElementById("continuarSelecionando");
const continuarPagamento = document.getElementById("continuarPagamento");
const instrucaoPreco = document.getElementById("instrucaoPreco");

const avisoCompraAndamento = document.getElementById("avisoCompraAndamento");
const continuarCompraAndamento = document.getElementById("continuarCompraAndamento");
const descartarCompraAndamento = document.getElementById("descartarCompraAndamento");


// =====================================
// LOGIN DO ADMINISTRADOR
// =====================================

const botaoAdmin = document.getElementById("botaoAdmin");
const modalLoginAdmin = document.getElementById("modalLoginAdmin");
const fecharLoginAdmin = document.getElementById("fecharLoginAdmin");
const formularioLoginAdmin = document.getElementById("formularioLoginAdmin");
const usuarioAdmin = document.getElementById("usuarioAdmin");
const senhaAdmin = document.getElementById("senhaAdmin");
const erroLoginAdmin = document.getElementById("erroLoginAdmin");
const botaoEntrarAdmin = document.getElementById("botaoEntrarAdmin");

if (botaoAdmin) {

    botaoAdmin.addEventListener("click", () => {

        erroLoginAdmin.style.display = "none";
        modalLoginAdmin.style.display = "flex";
        usuarioAdmin.focus();

    });

}

if (fecharLoginAdmin) {

    fecharLoginAdmin.addEventListener("click", () => {
        modalLoginAdmin.style.display = "none";
    });

}

if (modalLoginAdmin) {

    modalLoginAdmin.addEventListener("click", evento => {

        if (evento.target === modalLoginAdmin) {
            modalLoginAdmin.style.display = "none";
        }

    });

}

if (formularioLoginAdmin) {

    formularioLoginAdmin.addEventListener("submit", async evento => {

        evento.preventDefault();

        erroLoginAdmin.style.display = "none";
        botaoEntrarAdmin.disabled = true;
        botaoEntrarAdmin.textContent = "Entrando...";

        try {

            const resposta = await fetch(`${API}/api/admin/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    usuario: usuarioAdmin.value.trim(),
                    senha: senhaAdmin.value
                })
            });

            const resultado = await resposta.json();

            if (!resposta.ok || !resultado.sucesso) {
                throw new Error(resultado.erro || "Usuário ou senha incorretos.");
            }

            sessionStorage.setItem("rifaAdminToken", resultado.token);
            sessionStorage.setItem("rifaAdminUsuario", resultado.usuario);

            window.location.href = "Admin.html";

        } catch (erro) {

            erroLoginAdmin.textContent = erro.message;
            erroLoginAdmin.style.display = "block";

            botaoEntrarAdmin.disabled = false;
            botaoEntrarAdmin.textContent = "Entrar";

        }

    });

}


// =====================================
// TEXTO DE PREÇO (sempre igual ao config.js)
// =====================================

if (instrucaoPreco) {

    instrucaoPreco.textContent =
        "Cada número custa " +
        formatarValor(PRECO) +
        ".";

}


// =====================================
// STATUS DOS NÚMEROS
// =====================================

let statusNumeros = {};


// =====================================
// VERIFICAR COMPRA EM ANDAMENTO
// =====================================
// Se a pessoa já reservou números antes (e não cancelou nem
// pagou), mostramos um aviso para ela continuar ou descartar,
// em vez de deixá-la perdida vendo os números como "pendente"
// sem entender o motivo.
// =====================================

async function verificarCompraAndamento() {

    const tokenSalvo = localStorage.getItem("rifaCompraToken");

    if (!tokenSalvo) {
        return;
    }

    try {

        const resposta = await fetch(
            `${API}/api/compras/${encodeURIComponent(tokenSalvo)}`,
            { cache: "no-store" }
        );

        const resultado = await resposta.json();

        if (!resposta.ok || !resultado.sucesso) {
            limparCompraSalva();
            return;
        }

        const status = resultado.compra.status;

        // Só oferece "continuar" se ainda há algo a fazer
        if (
            status === "pendente_pagamento" ||
            status === "comprovante_enviado"
        ) {

            avisoCompraAndamento.style.display = "flex";

        } else {

            // confirmada, cancelada ou expirada: não faz sentido reoferecer
            limparCompraSalva();

        }

    } catch (erro) {

        console.error("Erro ao verificar compra em andamento:", erro);

    }

}


function limparCompraSalva() {

    localStorage.removeItem("rifaCompraToken");
    localStorage.removeItem("rifaSelecionados");

}


if (continuarCompraAndamento) {

    continuarCompraAndamento.addEventListener("click", () => {

        const tokenSalvo = localStorage.getItem("rifaCompraToken");

        window.location.href =
            "pagamento.html?token=" + encodeURIComponent(tokenSalvo);

    });

}


if (descartarCompraAndamento) {

    descartarCompraAndamento.addEventListener("click", async () => {

        const tokenSalvo = localStorage.getItem("rifaCompraToken");

        descartarCompraAndamento.disabled = true;

        try {

            if (tokenSalvo) {

                await fetch(`${API}/api/liberar`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ token: tokenSalvo })
                });

            }

        } catch (erro) {

            console.error("Erro ao descartar compra:", erro);

        } finally {

            limparCompraSalva();
            avisoCompraAndamento.style.display = "none";
            descartarCompraAndamento.disabled = false;
            selecionados = [];
            atualizarBarra();
            carregarNumeros();

        }

    });

}


// =====================================
// BUSCAR NÚMEROS
// =====================================

async function carregarNumeros() {

    try {

        const resposta = await fetch(`${API}/api/numeros`, { cache: "no-store" });

        if (!resposta.ok) {
            throw new Error("Erro ao consultar números.");
        }

        const dados = await resposta.json();

        statusNumeros = {};

        dados.forEach(item => {
            statusNumeros[Number(item.numero)] = item.status;
        });

        atualizarBotoes();

    } catch (erro) {

        console.error("Erro ao carregar números:", erro);

    }

}


// =====================================
// CRIAR OS BOTÕES (quantidade vem do config.js)
// =====================================

for (let i = 1; i <= RIFA_CONFIG.TOTAL_NUMEROS; i++) {

    const botao = document.createElement("button");

    botao.type = "button";
    botao.textContent = String(i).padStart(3, "0");
    botao.dataset.numero = i;

    botao.addEventListener("click", () => {
        selecionarNumero(i, botao);
    });

    grade.appendChild(botao);

}


// =====================================
// ATUALIZAR CORES
// =====================================

function atualizarBotoes() {

    const botoes = grade.querySelectorAll("button");

    botoes.forEach(botao => {

        const numero = Number(botao.dataset.numero);

        botao.classList.remove("selecionado", "pendente", "indisponivel");

        const status = statusNumeros[numero];

        if (status === "pendente") {

            // Se for um número que EU mesmo reservei (está na minha lista
            // local), eu mostro como "selecionado", não como travado —
            // assim quem sai e volta continua vendo seus próprios números.
            if (selecionados.includes(numero)) {
                botao.classList.add("selecionado");
                botao.title = "Seu número (reservado). Continue sua compra.";
            } else {
                botao.classList.add("pendente");
                botao.title = "Este número possui uma compra pendente.";
            }

            return;

        }

        if (status === "indisponivel") {
            botao.classList.add("indisponivel");
            botao.title = "Este número já foi comprado.";
            return;
        }

        if (selecionados.includes(numero)) {
            botao.classList.add("selecionado");
            botao.title = "Número selecionado.";
        }

    });

}


// =====================================
// SELECIONAR NÚMERO
// =====================================

function selecionarNumero(numero, botao) {

    const status = statusNumeros[numero];

    if (status === "pendente" && !selecionados.includes(numero)) {

        alert("Não é possível selecionar este número porque a compra dele está pendente.");
        return;

    }

    if (status === "indisponivel") {

        alert("Não é possível selecionar este número porque ele já foi comprado por outra pessoa.");
        return;

    }

    const indice = selecionados.indexOf(numero);

    if (indice !== -1) {
        selecionados.splice(indice, 1);
    } else {
        selecionados.push(numero);
    }

    salvarSelecao();
    atualizarBarra();
    atualizarBotoes();

}


// =====================================
// SALVAR SELEÇÃO
// =====================================

function salvarSelecao() {

    localStorage.setItem("rifaSelecionados", JSON.stringify(selecionados));

}


// =====================================
// ATUALIZAR BARRA
// =====================================

function atualizarBarra() {

    barraNumeros.innerHTML = "";

    selecionados
        .sort((a, b) => a - b)
        .forEach(numero => {

            const span = document.createElement("span");
            span.className = "numero-selecionado";
            span.textContent = String(numero).padStart(3, "0");
            barraNumeros.appendChild(span);

        });

    const qtd = selecionados.length;

    quantidade.textContent = qtd + (qtd === 1 ? " número" : " números");
    valor.textContent = formatarValor(qtd * PRECO);

}


// =====================================
// ABRIR MODAL
// =====================================

confirmar.addEventListener("click", () => {

    if (selecionados.length === 0) {
        alert("Selecione pelo menos um número.");
        return;
    }

    atualizarModal();
    modal.style.display = "flex";

});


// =====================================
// ATUALIZAR MODAL
// =====================================

function atualizarModal() {

    listaModal.innerHTML = "";

    selecionados
        .sort((a, b) => a - b)
        .forEach(numero => {

            const span = document.createElement("span");
            span.className = "numero-escolhido";
            span.textContent = String(numero).padStart(3, "0");
            listaModal.appendChild(span);

        });

    const qtd = selecionados.length;

    quantidadeModal.textContent = qtd + (qtd === 1 ? " número" : " números");
    totalModal.textContent = formatarValor(qtd * PRECO);

}


// =====================================
// CONTINUAR SELECIONANDO
// =====================================

continuarSelecionando.addEventListener("click", () => {

    modal.style.display = "none";

    // IMPORTANTE: Não reserva nada aqui.

    atualizarBarra();
    atualizarBotoes();

});


// =====================================
// IR PARA PAGAMENTO
// =====================================

continuarPagamento.addEventListener("click", async () => {

    if (selecionados.length === 0) {
        alert("Selecione pelo menos um número.");
        return;
    }

    continuarPagamento.disabled = true;
    continuarPagamento.textContent = "Reservando...";

    try {

        const numerosParaReservar = [...selecionados];

        const resposta = await fetch(`${API}/api/reservar`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ numeros: numerosParaReservar })
        });

        const resultado = await resposta.json();

        if (!resposta.ok) {

            alert(resultado.erro || "Não foi possível reservar os números.");
            await carregarNumeros();
            continuarPagamento.disabled = false;
            continuarPagamento.textContent = "Continuar a compra";
            return;

        }

        const token = resultado.token;

        if (!token) {
            throw new Error("O servidor não retornou o token da compra.");
        }

        localStorage.setItem("rifaCompraToken", token);
        localStorage.setItem("rifaSelecionados", JSON.stringify(numerosParaReservar));

        window.location.href = "pagamento.html?token=" + encodeURIComponent(token);

    } catch (erro) {

        console.error("Erro ao reservar:", erro);
        alert("Não foi possível conectar ao servidor.");
        continuarPagamento.disabled = false;
        continuarPagamento.textContent = "Continuar a compra";

    }

});


// =====================================
// INICIAR
// =====================================

atualizarBarra();
carregarNumeros();
verificarCompraAndamento();


// =====================================
// ATUALIZAÇÃO EM TEMPO REAL
// =====================================

setInterval(carregarNumeros, 3000);
