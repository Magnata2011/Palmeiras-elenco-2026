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
        : "https://palmeiras-elenco-2026.onrender.com",


    // -----------------------------------------------------------
    // PREÇO DE CADA NÚMERO (em reais)
    // -----------------------------------------------------------

    PRECO: 10,


    // -----------------------------------------------------------
    // QUANTIDADE TOTAL DE NÚMEROS DA RIFA
    // -----------------------------------------------------------

    TOTAL_NUMEROS: 1000,


    // -----------------------------------------------------------
    // TEMPO PARA PAGAR (deve bater com MINUTOS do app.py)
    // -----------------------------------------------------------
    // Depois que a pessoa marca "já realizei o pagamento", não há
    // mais prazo nenhum: a confirmação do admin passou a ser 100%
    // manual, sem expiração automática.

    MINUTOS_PARA_PAGAR: 5,


    // -----------------------------------------------------------
    // CONTATO (usado só pra exibir/copiar se você precisar)
    // -----------------------------------------------------------
    // WHATSAPP: código do país + DDD + número, sem espaços,
    // parênteses ou traços. Ex: 55 11 99999-9999 -> "5511999999999"

    WHATSAPP: "5511976656188",

    EMAIL: "seuemail@gmail.com",


    // -----------------------------------------------------------
    // CÓDIGO PIX "COPIA E COLA"
    // -----------------------------------------------------------

    PIX_COPIA_COLA: "00020126450014br.gov.bcb.pix0123nunesmarrey@hotmail.com5204000053039865802BR5915MARCELO NUNESGP6009Sao Paulo610901227-20062220518daqr42027295449593630422E0"

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
// MONTAR O LINK DO WHATSAPP PARA ENVIO DO COMPROVANTE
// =====================================================================
// Em vez de ir para um formulário do Google, a pessoa é mandada
// direto para uma conversa no WhatsApp (RIFA_CONFIG.WHATSAPP) já
// com uma mensagem pronta, pedindo o comprovante. O WhatsApp usa
// um único asterisco (*texto*) para deixar em negrito — por isso o
// "envie aqui o comprovante" abaixo usa *um* asterisco de cada lado,
// não dois.

function montarLinkComprovanteWhatsapp(dados) {

    const linhas = [
        "Olá! Já realizei o pagamento da rifa do Palmeiras.",
        "",
        "Código da compra: " + (dados.token || "-"),
        "Números: " + (dados.numeros || "-"),
        "Quantidade: " + (dados.quantidade !== undefined ? dados.quantidade : "-"),
        "Valor: " + (dados.valor || "-"),
        "",
        "*envie aqui o comprovante* 📎"
    ];

    const mensagem = encodeURIComponent(linhas.join("\n"));

    return "https://wa.me/" + RIFA_CONFIG.WHATSAPP + "?text=" + mensagem;

}
