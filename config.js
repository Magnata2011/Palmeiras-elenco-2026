// =====================================================================
// CONFIGURAÇÃO GERAL DO SITE DA RIFA
// =====================================================================
//
// Este é o ÚNICO arquivo que você precisa editar para configurar
// o site depois de publicar. Todas as páginas (index, pagamento,
// admin) leem os valores daqui.
//
// =====================================================================

const RIFA_CONFIG = {

    // -----------------------------------------------------------
    // ENDEREÇO DO BACKEND (API)
    // -----------------------------------------------------------
    // Enquanto estiver testando no seu computador, deixe como está.
    // Quando publicar o backend (ex: Render, Railway, seu servidor),
    // troque pela URL pública dele, por exemplo:
    // "https://minha-rifa-api.onrender.com"
    //
    // IMPORTANTE: não coloque "/" no final da URL.

    API_URL: (
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1" ||
        window.location.hostname === "" ||             // abrindo o HTML direto (file://)
        window.location.protocol === "file:"
    )
        ? "http://127.0.0.1:5000"
        : "https://TROQUE-PELA-URL-DO-SEU-BACKEND.onrender.com",


    // -----------------------------------------------------------
    // PREÇO DE CADA NÚMERO (em reais)
    // -----------------------------------------------------------

    PRECO: 20,


    // -----------------------------------------------------------
    // QUANTIDADE TOTAL DE NÚMEROS DA RIFA
    // -----------------------------------------------------------

    TOTAL_NUMEROS: 1000,


    // -----------------------------------------------------------
    // TEMPO PARA PAGAR (deve bater com HORAS/MINUTOS do app.py)
    // -----------------------------------------------------------

    MINUTOS_PARA_PAGAR: 5,

    HORAS_PARA_ENVIAR_COMPROVANTE: 24,


    // -----------------------------------------------------------
    // CONTATO (usado só pra exibir/copiar se você precisar)
    // -----------------------------------------------------------
    // WHATSAPP: código do país + DDD + número, sem espaços,
    // parênteses ou traços. Ex: 55 11 99999-9999 -> "5511999999999"

    WHATSAPP: "5511999999999",

    EMAIL: "seuemail@gmail.com",


    // -----------------------------------------------------------
    // FORMULÁRIO GOOGLE PARA ENVIO DO COMPROVANTE
    // -----------------------------------------------------------
    // Depois de subir o comprovante no site, a pessoa é redirecionada
    // automaticamente para este formulário do Google (onde você recebe
    // a confirmação/arquivo do jeito que configurar por lá).
    //
    // Como pegar o link: no Google Forms, clique em "Enviar" (Send) e
    // copie o link do formulário.

    GOOGLE_FORM_URL:
        "https://forms.google.com/COLOQUE-O-LINK-DO-SEU-FORMULARIO-AQUI",


    // -----------------------------------------------------------
    // PREENCHER O FORMULÁRIO AUTOMATICAMENTE (opcional)
    // -----------------------------------------------------------
    // Se quiser que o código da compra, os números, a quantidade e o
    // valor já cheguem preenchidos no formulário, descubra o
    // "entry.XXXXXXXXX" de cada pergunta (veja o README, seção
    // "Descobrir o entry.XXXXX de uma pergunta do Google Forms") e
    // cole abaixo. Pode deixar null nos campos que não quiser
    // preencher automaticamente — o redirecionamento funciona do
    // mesmo jeito.

    GOOGLE_FORM_CAMPOS: {
        token: null,        // ex: "entry.111111111"
        numeros: null,      // ex: "entry.222222222"
        quantidade: null,   // ex: "entry.333333333"
        valor: null         // ex: "entry.444444444"
    },


    // -----------------------------------------------------------
    // CÓDIGO PIX "COPIA E COLA"
    // -----------------------------------------------------------

    PIX_COPIA_COLA: "COLOQUE-SEU-CODIGO-PIX-AQUI"

};


// =====================================================================
// FORMATAR DINHEIRO (usado em todas as páginas)
// =====================================================================

function formatarValor(valor) {

    return valor.toLocaleString(
        "pt-BR",
        {
            style: "currency",
            currency: "BRL"
        }
    );

}


// =====================================================================
// MONTAR O LINK DO FORMULÁRIO GOOGLE (com preenchimento automático,
// se configurado em GOOGLE_FORM_CAMPOS)
// =====================================================================

function montarLinkFormulario(dados) {

    const base = RIFA_CONFIG.GOOGLE_FORM_URL;
    const campos = RIFA_CONFIG.GOOGLE_FORM_CAMPOS || {};

    const parametros = new URLSearchParams();

    if (campos.token && dados.token) {
        parametros.set(campos.token, dados.token);
    }

    if (campos.numeros && dados.numeros) {
        parametros.set(campos.numeros, dados.numeros);
    }

    if (campos.quantidade && dados.quantidade !== undefined) {
        parametros.set(campos.quantidade, String(dados.quantidade));
    }

    if (campos.valor && dados.valor) {
        parametros.set(campos.valor, dados.valor);
    }

    const parametrosTexto = parametros.toString();

    if (!parametrosTexto) {
        return base;
    }

    const separador = base.includes("?") ? "&" : "?";

    return base + separador + parametrosTexto;

}
