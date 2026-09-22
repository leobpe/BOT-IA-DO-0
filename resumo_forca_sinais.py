"""Apresenta probabilidades já calculadas, sem mudar modelos ou decisões.

Uma estimativa bruta não é calibração. A nova estimativa histórica é rotulada
separadamente: não é chance específica da partida, nota ou inverso da odd.
"""

import json
import math
import os

from probabilidade_por_acertos import (
    CAMPO,
    MIN_AMOSTRA,
    MIN_AMOSTRA_ROBUSTA,
    VERSAO,
    ativo,
)
from valor_mercado import (
    avaliar_margem_bookmaker,
    odd_oposta_sincronizada,
    referencia_tres_vias_sincronizada,
)


def _dict(valor):
    if isinstance(valor, dict):
        return valor
    try:
        resultado = json.loads(valor or "{}")
        return resultado if isinstance(resultado, dict) else {}
    except (ValueError, TypeError):
        return {}


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _percentual(valor, casas=1):
    return f"{100 * valor:.{casas}f}%".replace(".", ",")


def _percentual_com_sinal(valor, casas=1):
    return f"{100 * valor:+.{casas}f}%".replace(".", ",")


def _resumo_referencia_mercado_sem_vig(candidato):
    """Expõe somente uma referência completa e sincronizada da entrada.

    A informação é individual da fotografia de mercado, mas continua sendo
    preço implícito — não previsão do bot. Pares/trios incompletos, misturados
    ou com margem implausível permanecem invisíveis.
    """
    candidato = candidato or {}
    tres_vias = referencia_tres_vias_sincronizada(candidato)
    if tres_vias:
        odds = [
            _numero(tres_vias["odds"].get(chave))
            for chave in ("casa", "visitante", "sem_gol")
        ]
        selecao = tres_vias.get("selecao")
        selecionada = _numero(tres_vias["odds"].get(selecao))
        tipo = "tres_vias"
        rotulo_margem = "mercado"
    else:
        odd = _numero(candidato.get("odd"))
        oposta = odd_oposta_sincronizada(candidato)
        if odd is None or oposta is None:
            return ""
        odds = [odd, oposta]
        selecionada = odd
        tipo = "binaria"
        rotulo_margem = "par"
    qualidade = avaliar_margem_bookmaker(tipo, odds)
    if not qualidade.get("plausivel") or selecionada is None:
        return ""
    soma_implicita = sum(1 / odd for odd in odds)
    if soma_implicita <= 0:
        return ""
    probabilidade = (1 / selecionada) / soma_implicita
    return (
        "Probabilidade implícita desta partida, sem margem: "
        f"{_percentual(probabilidade)}\n"
        f"Margem da casa no {rotulo_margem}: "
        f"{_percentual(qualidade['margem_bookmaker'])}\n"
        "⚠️ Referência do preço neste instante; não é previsão nem garantia."
    )


def _com_referencia_mercado(texto, candidato):
    if not texto:
        return ""
    referencia = _resumo_referencia_mercado_sem_vig(candidato)
    return texto + (f"\n{referencia}" if referencia else "")


def _resumo_preco_historico(candidato, historico, probabilidade):
    """Mostra lucro realizado sem confundir acerto antigo com odd atual."""
    n = _numero(historico.get("amostra"))
    roi = _numero(historico.get("roi"))
    retorno_total = _numero(historico.get("retorno_unidades_total"))
    odd_media = _numero(historico.get("odd_media_executada"))
    intervalo_roi = historico.get("intervalo_roi_95")
    intervalo_dia = historico.get("intervalo_roi_95_agrupado_dia")
    dias = _numero(historico.get("dias_distintos"))
    ligas = _numero(historico.get("ligas_distintas"))
    roi_antigo = _numero(historico.get("roi_metade_antiga"))
    roi_recente = _numero(historico.get("roi_metade_recente"))
    drawdown = _numero(historico.get("drawdown_maximo_unidades"))
    sequencia_red = _numero(historico.get("maior_sequencia_red"))
    estado_vantagem = historico.get("estado_vantagem")
    vantagem_robusta = historico.get("vantagem_historica_robusta")
    if (
        n is None or n <= 0 or roi is None or retorno_total is None
        or odd_media is None or odd_media <= 1.0
        or abs(roi - retorno_total / n) > 1e-9
        or not isinstance(intervalo_roi, (list, tuple))
        or len(intervalo_roi) != 2
        or dias is None or dias < 1 or dias > n
        or ligas is None or ligas < 1 or ligas > n
        or drawdown is None or drawdown < 0
        or sequencia_red is None or sequencia_red < 0
        or vantagem_robusta not in {True, False}
        or estado_vantagem not in {
            "amostra_inicial", "vantagem_historica_robusta",
            "historico_desfavoravel", "historico_inconclusivo",
        }
    ):
        return ""
    inferior_roi = _numero(intervalo_roi[0])
    superior_roi = _numero(intervalo_roi[1])
    if inferior_roi is None or superior_roi is None or inferior_roi > superior_roi:
        return ""
    inferior_dia = superior_dia = None
    if isinstance(intervalo_dia, (list, tuple)) and len(intervalo_dia) == 2:
        inferior_dia = _numero(intervalo_dia[0])
        superior_dia = _numero(intervalo_dia[1])
        if not (
            inferior_dia is not None and superior_dia is not None
            and inferior_dia <= superior_dia
        ):
            return ""
    elif intervalo_dia is not None:
        return ""

    sinal_retorno = "+" if retorno_total >= 0 else ""
    linhas = [
        "ROI histórico executável (1 un./entrada): "
        f"{_percentual_com_sinal(roi)}.",
        f"Retorno acumulado: {sinal_retorno}"
        f"{retorno_total:.2f}".replace(".", ",")
        + f" un. em {int(n)} entradas.",
        "Odd média realmente executada: "
        + f"{odd_media:.2f}".replace(".", ",") + ".",
        "IC95 do ROI: "
        f"{_percentual_com_sinal(inferior_roi)}–"
        f"{_percentual_com_sinal(superior_roi)}.",
        f"Robustez temporal: {int(dias)} dias / {int(ligas)} ligas.",
    ]
    if inferior_dia is not None:
        linhas.append(
            "IC95 do ROI agrupado por dia: "
            f"{_percentual_com_sinal(inferior_dia)}–"
            f"{_percentual_com_sinal(superior_dia)}."
        )
    if roi_antigo is not None and roi_recente is not None:
        linhas.append(
            "Consistência temporal (metade antiga/recente): "
            f"{_percentual_com_sinal(roi_antigo)} / "
            f"{_percentual_com_sinal(roi_recente)}."
        )
    linhas.append(
        "Risco observado: drawdown máximo "
        f"{drawdown:.2f}".replace(".", ",")
        + f" un.; maior sequência de reds {int(sequencia_red)}."
    )
    if n < MIN_AMOSTRA_ROBUSTA or estado_vantagem == "amostra_inicial":
        linhas.append(
            "⚠️ Amostra inicial; resultado financeiro ainda inconclusivo."
        )
    elif vantagem_robusta is True and estado_vantagem == "vantagem_historica_robusta":
        linhas.append(
            "⚠️ Vantagem histórica robusta nas provas atuais; ainda não é "
            "edge individual calibrado."
        )
    elif estado_vantagem == "historico_desfavoravel":
        linhas.append("⚠️ Histórico executável sem vantagem financeira.")
    else:
        linhas.append(
            "⚠️ Resultado financeiro inconclusivo: o intervalo inclui zero."
        )

    odd = _numero(candidato.get("odd"))
    if odd is not None and odd > 1:
        linhas.append(
            f"Equilíbrio da odd atual {odd:.2f}: "
            f"{_percentual(1 / odd)} (apenas referência deste preço)."
        )
    intervalo = historico.get("intervalo_wilson95")
    inferior = superior = None
    if isinstance(intervalo, (list, tuple)) and len(intervalo) == 2:
        inferior = _numero(intervalo[0])
        superior = _numero(intervalo[1])
        if not (
            inferior is not None
            and superior is not None
            and 0 <= inferior <= superior <= 1
        ):
            inferior = superior = None

    if inferior is not None and superior is not None:
        linhas.append(
            "Faixa de acerto observada de 95%: "
            f"{_percentual(inferior)}–{_percentual(superior)}."
        )
    return "\n".join(linhas)


def _texto(probabilidade=None, *, calibrado=False, compacto=False):
    if os.getenv("RESUMO_FORCA_SINAIS_ATIVO", "1").lower() in {"0", "false", "off", "nao"}:
        return ""
    p = _numero(probabilidade)
    if p is None or not 0 < p < 1:
        return "📊 Probabilidade: indisponível neste método."
    percentual = (
        ">99,9%" if p >= 0.9995 else
        "<0,1%" if p < 0.0005 else
        f"{100 * p:.1f}%".replace(".", ",")
    )
    if calibrado:
        return f"📊 Probabilidade calibrada: {percentual}\n⚠️ Não é garantia de acerto."
    if compacto:
        return f"📊 Prob. estimada: {percentual} (não calibrada)."
    return (
        f"📊 Probabilidade estimada: {percentual}\n"
        "⚠️ Modelo não calibrado; não é garantia de acerto."
    )


def resumo_forca_ao_vivo(candidato, *, calibrado=False):
    """Usa o modelo do método enviado, nunca um diagnóstico de outra rota."""
    if calibrado:
        return _texto(candidato.get("probabilidade_calibrada"), calibrado=True)
    historico = _dict(candidato.get(CAMPO))
    p_historico = _numero(historico.get("probabilidade"))
    n = _numero(historico.get("amostra"))
    greens = _numero(historico.get("greens"))
    reds = _numero(historico.get("reds"))
    resumo_preco = _resumo_preco_historico(
        candidato, historico, p_historico
    )
    if (ativo() and historico.get("versao") == VERSAO and n is not None
            and greens is not None and reds is not None and greens >= 0 and reds >= 0
            and n == greens + reds and n >= MIN_AMOSTRA
            and p_historico is not None and 0 < p_historico < 1
            and resumo_preco):
        if not _texto(p_historico):
            return ""
        percentual = _percentual(p_historico)
        ressalva = "Amostra inicial; " if n < 30 else ""
        texto = (
            f"📊 Taxa histórica executável do método: {percentual}\n"
            f"Base Bet365: {historico['greens']} greens / "
            f"{historico['reds']} reds.\n"
            f"⚠️ {ressalva}não é a chance deste jogo."
            + (f"\n{resumo_preco}" if resumo_preco else "")
        )
        return _com_referencia_mercado(texto, candidato)
    f = _dict(candidato.get("features") or candidato.get("features_json"))
    versao = _dict(f.get("exploracao_sombra")).get("versao")
    mercado = candidato.get("mercado")
    prefixo = {"gol_ht": "gol-ht-", "gol_ft": "gol-ft-"}.get(mercado)
    p = None
    if prefixo and versao == prefixo + "capacidade-contextual-v2b":
        p = _dict(f.get("gol_capacidade_contextual_v2")).get("probabilidade_estimada_nao_calibrada")
    elif prefixo and versao == prefixo + "capacidade-times-poisson-v1":
        p = _dict(_dict(f.get("gol_capacidade_times")).get("modelo")).get("probabilidade_mais_um_gol")
    if (ativo() and historico.get("versao") == VERSAO
            and historico.get("estado") == "cotacao_atual_nao_executavel"):
        return _com_referencia_mercado(
            "📊 Histórico comparável indisponível: a odd deste alerta não "
            "possui prova executável Bet365.",
            candidato,
        )
    if (p is None and ativo() and historico.get("versao") == VERSAO
            and n is not None and 0 <= n < MIN_AMOSTRA):
        if not _texto():
            return ""
        return (
            "📊 Histórico executável Bet365: amostra insuficiente "
            f"({int(n)}/{MIN_AMOSTRA})."
        )
    return _com_referencia_mercado(_texto(p), candidato)


def resumo_forca_pre_live(bilhete, *, compacto=False):
    """Estimativa do bilhete inteiro já calculada, não média das pernas."""
    return _texto(_dict(bilhete).get("probabilidade_modelo"), compacto=compacto)
