// =====================================
// CONFIGURAÇÕES (vêm do config.js)
// =====================================

const API = RIFA_CONFIG.API_URL;
const PRECO = RIFA_CONFIG.PRECO;


// =====================================
// PEGAR TOKEN
// =====================================

const parametros = new URLSearchParams(window.location.search);

let token = parametros.get("token");

if (!token) {
    token = localStorage.getItem("rifaCompraToken");
}


// =====================================
// ELEMENTOS
// =====================================

const listaPagamento = document.getElementById("listaPagamento");
const quantidadePagamento = document.getElementById("quantidadePagamento");
const totalPagamento = document.getElementById("totalPagamento");
const valorPix = document.getElementById("valorPix");
const codigoPix = document.getElementById("codigoPix");
const copiarPix = document.getElementById("copiarPix");
const timerElemento = document.getElementById("timer");
const mensagemTimer = document.getElementById("mensagemTimer");
const cancelar = document.getElementById("cancelar");
const voltarSelecionar = document.getElementById("voltarSelecionar");
const pagamentoRealizado = document.getElementById("pagamentoRealizado");

const areaRedirecionamento = document.getElementById("areaRedirecionamento");
const linkFormulario = document.getElementById("linkFormulario");
const textoRedirecionamento = document.getElementById("textoRedirecionamento");

const qrDuvidasWhatsapp = document.getElementById("qrDuvidasWhatsapp");
const linkDuvidasWhatsapp = document.getElementById("linkDuvidasWhatsapp");


// =====================================
// PREENCHER VALORES FIXOS DO CONFIG
// =====================================

if (codigoPix) {
    codigoPix.value = RIFA_CONFIG.PIX_COPIA_COLA;
}


// =====================================
// QR CODE DE DÚVIDAS (WHATSAPP)
// =====================================
// Usa um serviço público e gratuito de geração de QR Code a partir
// de uma imagem. Se preferir não depender dele, gere seu próprio QR
// Code e substitua o <img> em pagamento.html por um arquivo local.

if (qrDuvidasWhatsapp && RIFA_CONFIG.WHATSAPP) {

    const mensagemDuvida = encodeURIComponent(
        "Olá! Tenho uma dúvida sobre a rifa do Palmeiras."
    );

    const linkWhatsapp =
        "https://wa.me/" + RIFA_CONFIG.WHATSAPP + "?text=" + mensagemDuvida;

    qrDuvidasWhatsapp.src =
        "https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=" +
        encodeURIComponent(linkWhatsapp);

    if (linkDuvidasWhatsapp) {
        linkDuvidasWhatsapp.href = linkWhatsapp;
    }

}


// =====================================
// VARIÁVEIS
// =====================================

let numeros = [];
let compra = null;
let timerInterval = null;
let pagamentoRealizadoFlag = false;
let pagamentoConfirmadoFlag = false;

// Quando true, o botão "voltar" do navegador pode sair
// livremente da página, sem cancelar a reserva.
let podeSairLivremente = false;


// =====================================
// FORMATAR DATA DO SERVIDOR
// =====================================

function converterData(texto) {

    if (!texto) {
        return null;
    }

    return new Date(texto.replace(" ", "T"));

}


// =====================================
// PROTEÇÃO CONTRA O BOTÃO "VOLTAR" DO NAVEGADOR
// =====================================
// Antes, quem usava o botão voltar do navegador (em vez do botão
// da própria página) saía sem cancelar a reserva: os números
// ficavam presos como "pendente" por até 5 minutos e a pessoa
// via os próprios números travados no index, sem entender o motivo.
//
// Agora: criamos uma "trava" no histórico do navegador. Se a
// pessoa apertar voltar antes de finalizar, perguntamos se ela
// quer cancelar a reserva (liberando os números na hora) ou
// continuar na página.
// =====================================

function ativarProtecaoSaida() {

    history.pushState({ rifaProtecao: true }, "", window.location.href);

}


window.addEventListener("popstate", () => {

    if (podeSairLivremente) {
        return;
    }

    // Repõe a trava antes de perguntar, para a pessoa não
    // sair acidentalmente enquanto decide.
    ativarProtecaoSaida();

    const confirmarSaida = confirm(
        "Se você sair agora, sua reserva destes números será " +
        "cancelada e eles ficarão disponíveis para outras pessoas.\n\n" +
        "Deseja realmente sair e cancelar a compra?"
    );

    if (confirmarSaida) {
        cancelarECair();
    }

});


ativarProtecaoSaida();


// =====================================
// CANCELAR E SAIR (usado pelo botão voltar do navegador
// e pelo botão "Cancelar compra")
// =====================================

async function cancelarECair(mensagemFinal) {

    podeSairLivremente = true;

    pararTimer();

    try {

        if (token) {

            await fetch(`${API}/api/liberar`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: token })
            });

        }

    } catch (erro) {

        console.error("Erro ao liberar números:", erro);

    } finally {

        localStorage.removeItem("rifaCompraToken");
        localStorage.removeItem("rifaSelecionados");

        if (mensagemFinal) {
            alert(mensagemFinal);
        }

        window.location.href = "index.html";

    }

}


// =====================================
// CARREGAR COMPRA
// =====================================

async function carregarCompra() {

    if (!token) {
        mostrarErroCompra();
        return;
    }

    try {

        const resposta = await fetch(
            `${API}/api/compras/${encodeURIComponent(token)}`,
            { cache: "no-store" }
        );

        const resultado = await resposta.json();

        if (!resposta.ok || !resultado.sucesso) {
            throw new Error(resultado.erro || "Não foi possível identificar a compra.");
        }

        compra = resultado.compra;

        numeros = Array.isArray(compra.numeros) ? compra.numeros : [];
        numeros = numeros.map(Number).sort((a, b) => a - b);

        localStorage.setItem("rifaCompraToken", token);
        localStorage.setItem("rifaSelecionados", JSON.stringify(numeros));

        mostrarNumeros();
        atualizarValores();

        if (compra.status === "expirada") {
            podeSairLivremente = true;
            bloquearPagina("O prazo desta compra expirou. Os números foram liberados.");
            return;
        }

        if (compra.status === "cancelada") {
            podeSairLivremente = true;
            bloquearPagina("Esta compra foi cancelada.");
            return;
        }

        if (compra.status === "confirmada") {
            podeSairLivremente = true;
            bloquearPagina("Esta compra já foi confirmada. Obrigado!");
            return;
        }

        if (compra.status === "comprovante_enviado") {

            pagamentoConfirmadoFlag = true;
            podeSairLivremente = true;

            pararTimer();

            if (mensagemTimer) {
                mensagemTimer.textContent =
                    "Pagamento já marcado como realizado. " +
                    "Aguardando confirmação.";
            }

            pagamentoRealizado.style.display = "none";
            cancelar.style.display = "none";

            // Já marcou antes: mostra o link, mas não força o
            // redirecionamento automático de novo (evita loop
            // caso a pessoa volte nesta página).
            mostrarRedirecionamento(false);

            return;

        }

        // Ainda pendente de pagamento: mantém a proteção de saída
        // e liga o cronômetro de 5 minutos.
        iniciarTimer(compra.expira_em);

    } catch (erro) {

        console.error("Erro ao carregar compra:", erro);
        mostrarErroCompra();

    }

}


// =====================================
// ERRO DE COMPRA
// =====================================

function mostrarErroCompra() {

    podeSairLivremente = true;

    alert("Não foi possível identificar a compra.");

    window.location.href = "index.html";

}


// =====================================
// MOSTRAR NÚMEROS
// =====================================

function mostrarNumeros() {

    listaPagamento.innerHTML = "";

    if (numeros.length === 0) {
        listaPagamento.textContent = "Nenhum número selecionado.";
        return;
    }

    numeros.forEach(numero => {

        const span = document.createElement("span");
        span.className = "numero-pagamento";
        span.textContent = String(numero).padStart(3, "0");
        listaPagamento.appendChild(span);

    });

}


// =====================================
// ATUALIZAR VALORES
// =====================================

function atualizarValores() {

    const quantidade = numeros.length;
    const total = quantidade * PRECO;

    quantidadePagamento.textContent =
        quantidade + (quantidade === 1 ? " número" : " números");

    totalPagamento.textContent = formatarValor(total);
    valorPix.textContent = formatarValor(total);

}


// =====================================
// TIMER
// =====================================

function iniciarTimer(dataExpiracao) {

    pararTimer();

    if (!dataExpiracao) {
        return;
    }

    const expiracao = converterData(dataExpiracao);

    if (!expiracao) {
        return;
    }

    function atualizarTimer() {

        const agora = new Date();
        const diferenca = expiracao.getTime() - agora.getTime();

        if (diferenca <= 0) {

            timerElemento.textContent = "00:00";
            pararTimer();
            podeSairLivremente = true;
            bloquearPorExpiracao();
            return;

        }

        const totalSegundos = Math.floor(diferenca / 1000);
        const minutos = Math.floor(totalSegundos / 60);
        const segundos = totalSegundos % 60;

        timerElemento.textContent =
            String(minutos).padStart(2, "0") + ":" +
            String(segundos).padStart(2, "0");

        // Aviso visual quando faltar menos de 1 minuto
        if (totalSegundos <= 60) {
            timerElemento.classList.add("timer-urgente");
        }

    }

    atualizarTimer();

    timerInterval = setInterval(atualizarTimer, 1000);

}


// =====================================
// PARAR TIMER
// =====================================

function pararTimer() {

    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }

}


// =====================================
// EXPIRAÇÃO
// =====================================

function bloquearPorExpiracao() {

    localStorage.removeItem("rifaCompraToken");
    localStorage.removeItem("rifaSelecionados");

    alert("O tempo para pagamento acabou. Os números foram liberados.");

    window.location.href = "index.html";

}


// =====================================
// BLOQUEAR PÁGINA
// =====================================

function bloquearPagina(mensagem) {

    pararTimer();

    alert(mensagem);

    localStorage.removeItem("rifaCompraToken");
    localStorage.removeItem("rifaSelecionados");

    window.location.href = "index.html";

}


// =====================================
// COPIAR PIX
// =====================================

copiarPix.addEventListener("click", async () => {

    try {

        await navigator.clipboard.writeText(codigoPix.value);

        copiarPix.textContent = "Copiado!";

        setTimeout(() => {
            copiarPix.textContent = "Copiar";
        }, 2000);

    } catch (erro) {

        codigoPix.select();
        document.execCommand("copy");
        copiarPix.textContent = "Copiado!";

    }

});


// =====================================
// JÁ REALIZEI O PAGAMENTO
// =====================================
// A pessoa não envia mais comprovante pelo site: ao clicar aqui,
// avisamos o backend que o pagamento foi marcado como realizado
// (o que também estende o prazo para o admin conferir) e já
// mandamos ela direto para o formulário do Google, onde o
// comprovante de verdade é enviado.
// =====================================

pagamentoRealizado.addEventListener("click", async () => {

    if (!token) {
        alert("Compra não identificada.");
        return;
    }

    pagamentoRealizado.disabled = true;
    pagamentoRealizado.textContent = "Enviando...";

    try {

        const resposta = await fetch(`${API}/api/pagamento-confirmado`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: token })
        });

        const resultado = await resposta.json();

        if (!resposta.ok || !resultado.sucesso) {
            throw new Error(resultado.erro || "Não foi possível confirmar o pagamento.");
        }

        pagamentoRealizadoFlag = true;
        pagamentoConfirmadoFlag = true;

        // A partir daqui a pessoa já afirmou ter pago; não
        // cancelamos mais a reserva automaticamente se ela sair.
        podeSairLivremente = true;

        pararTimer();

        if (mensagemTimer) {
            mensagemTimer.textContent =
                "Pagamento marcado como realizado. " +
                "Aguardando confirmação.";
        }

        pagamentoRealizado.style.display = "none";
        cancelar.style.display = "none";

        mostrarRedirecionamento(true);

    } catch (erro) {

        console.error("Erro ao confirmar pagamento:", erro);

        alert(erro.message);

        pagamentoRealizado.disabled = false;
        pagamentoRealizado.textContent = "Já realizei o pagamento";

    }

});


// =====================================
// REDIRECIONAR PARA O FORMULÁRIO DO GOOGLE
// =====================================

function mostrarRedirecionamento(autoRedirecionar) {

    const quantidade = numeros.length;

    const url = montarLinkFormulario({
        token: token,
        numeros: numeros.map(n => String(n).padStart(3, "0")).join(", "),
        quantidade: quantidade,
        valor: formatarValor(quantidade * PRECO)
    });

    linkFormulario.href = url;

    areaRedirecionamento.style.display = "block";

    if (!autoRedirecionar) {

        if (textoRedirecionamento) {
            textoRedirecionamento.textContent =
                "Seu comprovante já foi recebido. Se ainda não " +
                "preencheu o formulário de confirmação, clique abaixo.";
        }

        return;

    }

    let segundos = 4;

    if (textoRedirecionamento) {

        const atualizarContagem = () => {

            textoRedirecionamento.textContent =
                "Você será redirecionado para o formulário em " +
                segundos + "s...";

        };

        atualizarContagem();

        const contagem = setInterval(() => {

            segundos -= 1;

            if (segundos <= 0) {
                clearInterval(contagem);
                return;
            }

            atualizarContagem();

        }, 1000);

    }

    setTimeout(() => {
        window.location.href = url;
    }, 4000);

}


// =====================================
// VOLTAR E SELECIONAR MAIS
// =====================================

voltarSelecionar.addEventListener("click", async () => {

    if (!token) {
        window.location.href = "index.html";
        return;
    }

    voltarSelecionar.disabled = true;
    voltarSelecionar.textContent = "Liberando...";

    try {

        const resposta = await fetch(`${API}/api/liberar`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: token })
        });

        const resultado = await resposta.json();

        if (!resposta.ok || !resultado.sucesso) {
            throw new Error(resultado.erro || "Não foi possível liberar a compra.");
        }

        podeSairLivremente = true;
        pararTimer();

        localStorage.removeItem("rifaCompraToken");
        localStorage.removeItem("rifaSelecionados");

        window.location.href = "index.html";

    } catch (erro) {

        console.error("Erro ao voltar:", erro);

        alert(erro.message);

        voltarSelecionar.disabled = false;
        voltarSelecionar.textContent = "← Voltar e selecionar mais";

    }

});


// =====================================
// CANCELAR
// =====================================

cancelar.addEventListener("click", () => {

    const confirmarCancelamento = confirm(
        "Tem certeza que deseja cancelar esta compra?"
    );

    if (!confirmarCancelamento) {
        return;
    }

    cancelar.disabled = true;
    cancelar.textContent = "Cancelando...";

    cancelarECair();

});


// =====================================
// INICIAR
// =====================================

carregarCompra();
