import unicodedata
from datetime import datetime

from normalizador_odds import estruturar_odds


MERCADOS_PACKBALL_AO_VIVO_PERMITIDOS = {
    "marcar o proximo gol",
    "total gols",
    "gols time da casa",
    "gols time visitante",
    "escanteios 2 opcoes",
    "escanteios exactly",
    "corrida de escanteios",
}


def _normalizar_titulo_mercado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return " ".join(
        "".join(
            caractere if caractere.isalnum() else " "
            for caractere in texto
            if not unicodedata.combining(caractere)
        ).lower().split()
    )


def filtrar_mercados_packball_ao_vivo(itens):
    """Aceita somente os títulos PackBall explicitamente mapeados.

    A API-Football é anexada depois desta etapa e valida seus próprios bet IDs.
    Assim, um título novo como ShotOnGoal ou Goal Kicks nunca herda a semântica
    de gols apenas por conter a palavra ``Goal``.
    """
    return [
        item for item in itens or []
        if isinstance(item, dict)
        and _normalizar_titulo_mercado(item.get("mercado"))
        in MERCADOS_PACKBALL_AO_VIVO_PERMITIDOS
    ]


SCRIPT_MERCADOS = """
    () => Array.from(
        document.querySelectorAll("article.item.all-odds")
    ).map(artigo => {
        const limpar = texto =>
            (texto || "").replace(/\\s+/g, " ").trim();
        const titulo = limpar(
            artigo.querySelector(".title-market")?.innerText ||
            artigo.querySelector("section")?.innerText
        );
        return {mercado: titulo, dados: limpar(artigo.innerText)};
    }).filter(item => /gol|goal|escanteio|corner/i.test(item.mercado))
"""


SCRIPT_MERCADOS_AO_VIVO = """
    () => {
        const limpar = texto =>
            (texto || "").replace(/\\s+/g, " ").trim();
        const corpo = limpar(document.body.innerText);
        const inicio = corpo.indexOf("ODDS AO VIVO");
        const fim = corpo.indexOf("SOBRE", inicio);
        if (inicio < 0) return [];

        const trecho = corpo.slice(
            inicio + "ODDS AO VIVO".length,
            fim > inicio ? fim : corpo.length
        );
        const titulos = [
            "Marcar O Próximo Gol",
            "Total Gols",
            "Gols Time Da Casa",
            "Gols Time Visitante",
            "Escanteios - 2 Opções",
            "Escanteios Exactly",
            "Corrida De Escanteios"
        ];
        const encontrados = titulos.map(titulo => ({
            titulo,
            posicao: trecho.indexOf(titulo)
        })).filter(item => item.posicao >= 0)
          .sort((a, b) => a.posicao - b.posicao);

        return encontrados.map((item, indice) => {
            const proximo = encontrados[indice + 1];
            const final = proximo ? proximo.posicao : trecho.length;
            return {
                mercado: item.titulo,
                dados: limpar(trecho.slice(item.posicao, final))
            };
        }).filter(item => /gol|escanteio|corner/i.test(item.mercado));
    }
"""


def _aguardar_renderizacao(
    pagina, condicao_javascript, timeout_ms, fallback_ms
):
    esperar = getattr(pagina, "wait_for_function", None)
    if esperar is None:
        pagina.wait_for_timeout(fallback_ms)
        return False
    try:
        esperar(condicao_javascript, timeout=timeout_ms)
        return True
    except Exception:
        return False


def coletar_odds(pagina, jogo, controle_acesso=None):
    url_odds = jogo["url"].rsplit("/", 1)[0] + "/odds"
    if controle_acesso is not None:
        controle_acesso.antes_navegacao()
    pagina.goto(
        url_odds,
        wait_until="domcontentloaded",
        timeout=30000,
    )
    if controle_acesso is not None:
        controle_acesso.validar_pagina(pagina)
    _aguardar_renderizacao(
        pagina,
        """() => Boolean(
            document.querySelector('article.item.all-odds')
        )""",
        timeout_ms=4000,
        fallback_ms=4000,
    )

    pre_jogo = pagina.evaluate(SCRIPT_MERCADOS)
    botao_ao_vivo = pagina.locator('[title="Odds ao vivo"]')
    clicou_ao_vivo = botao_ao_vivo.count() == 1
    if clicou_ao_vivo:
        botao_ao_vivo.click(timeout=5000)

    ao_vivo = []
    if clicou_ao_vivo:
        # Dá tempo mínimo para a troca de aba iniciar. A condição abaixo só
        # antecipa a coleta quando o próprio controle confirma seleção.
        pagina.wait_for_timeout(500)
        _aguardar_renderizacao(
            pagina,
            """() => {
                const botao = document.querySelector('[title="Odds ao vivo"]');
                const classes = `${botao?.className || ''} ${
                    botao?.parentElement?.className || ''
                }`.toLowerCase();
                const selecionado = botao?.getAttribute('aria-selected') === 'true'
                    || /active|selected|current/.test(classes);
                return selecionado && /Total Gols|Escanteios|Pr.ximo Gol/i.test(
                    document.body?.innerText || ''
                );
            }""",
            timeout_ms=2500,
            fallback_ms=2500,
        )
        ao_vivo = pagina.evaluate(SCRIPT_MERCADOS_AO_VIVO)

    odds = estruturar_odds({
        "pre_jogo": pre_jogo or [],
        "ao_vivo": filtrar_mercados_packball_ao_vivo(ao_vivo),
    })
    coletado_em = datetime.now().replace(microsecond=0).isoformat()
    for mercado in odds.get("ao_vivo") or []:
        mercado.update({
            "fonte": "packball",
            "cache": False,
            "coletado_em": coletado_em,
            "idade_segundos": 0.0,
        })
    return odds
