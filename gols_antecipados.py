"""Experimentos prospectivos de gol cedo com pré-jogo + confirmação live."""

import copy
import os
import re

from configuracao import odd_elegivel, obter_limites_risco
from linhagem_gols_antecipados import calcular_linhagem_gols_antecipados
from qualidade_dados import extrair_minuto, extrair_placar


VERSAO_GOL_HT_ANTECIPADO = "gol-ht-antecipado-faixa-historica-v2"
VERSAO_GOL_FT_ANTECIPADO = "gol-ft-antecipado-pre-live-v1"
VERSAO_GOL_FT_ANTECIPADO_2T = (
    "gol-ft-antecipado-2t-faixa-historica-v1"
)
VERSOES_GOLS_ANTECIPADOS = frozenset({
    VERSAO_GOL_HT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
})
VERSAO_POLITICA = "gols-antecipados-faixa-historica-v2"

# Capturado uma única vez durante o import do processo. Assim cada candidato
# representa exatamente a linhagem carregada em memória; uma edição no disco
# durante a execução não pode rebatizar silenciosamente a lógica antiga.
LINHAGEM_GOLS_ANTECIPADOS = calcular_linhagem_gols_antecipados()[
    "fingerprint"
]

MINUTO_MINIMO = 5
MINUTO_MAXIMO_HT = 28
MINUTO_MAXIMO_FT = 25
MINUTO_MINIMO_2T = 46
MINUTO_MAXIMO_2T = 82
QUALIDADE_MINIMA = 80.0
MINIMO_EVIDENCIAS_PRE = 2
MINIMO_EVIDENCIAS_LIVE = 2

_BLOQUEIOS_RELAXAVEIS = frozenset({
    "atividade_recente_insuficiente_gols",
})


def gols_antecipados_grupo_ativo(env=None):
    env = os.environ if env is None else env
    return env.get("GOLS_ANTECIPADOS_GRUPO_ATIVO", "1") == "1"


def elegivel_para_enriquecimento_antecipado(
    jogo, qualidade=None, candidatos=None
):
    """Autoriza buscar o contexto antes de existir candidato base aprovado."""
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    try:
        nota = float((qualidade or {}).get("pontuacao") or 0)
    except (TypeError, ValueError):
        nota = 0
    janela_valida = bool(
        minuto is not None
        and (
            (
                placar == [0, 0]
                and MINUTO_MINIMO <= minuto <= max(
                    MINUTO_MAXIMO_HT, MINUTO_MAXIMO_FT
                )
            )
            or (
                placar is not None
                and MINUTO_MINIMO_2T <= minuto <= MINUTO_MAXIMO_2T
            )
        )
        and nota >= 70
        and (qualidade or {}).get("divergencia_critica") is not True
    )
    if janela_valida and minuto is not None and minuto >= MINUTO_MINIMO_2T:
        janela_valida = any(
            item.get("mercado") == "gol_ft"
            and item.get("odd") is not None
            and (_numero(item.get("pontuacao_tecnica")) or 0) >= 65
            for item in candidatos or []
        )
    return janela_valida


def _numero(valor):
    if isinstance(valor, str):
        valor = valor.strip().replace("%", "").replace(",", ".")
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _soma_numeros(*valores):
    numeros = [_numero(valor) for valor in valores]
    numeros = [valor for valor in numeros if valor is not None]
    return sum(numeros) if numeros else None


def _evidencias_pre_jogo(contexto):
    contexto = contexto or {}
    evidencias = []
    h2h = contexto.get("confrontos_diretos") or {}
    if (
        (_numero(h2h.get("jogos")) or 0) >= 3
        and (
            (_numero(h2h.get("media_gols")) or 0) >= 2.2
            or (_numero(h2h.get("taxa_over_1_5")) or 0) >= 0.6
        )
    ):
        evidencias.append("h2h_gols")

    forma = contexto.get("forma_recente") or {}
    casa, fora = forma.get("mandante") or {}, forma.get("visitante") or {}
    media_forma = _soma_numeros(
        casa.get("gols_pro_media"), casa.get("gols_contra_media"),
        fora.get("gols_pro_media"), fora.get("gols_contra_media"),
    )
    if (
        (_numero(casa.get("jogos")) or 0) >= 3
        and (_numero(fora.get("jogos")) or 0) >= 3
        and media_forma is not None and media_forma / 2 >= 2.2
    ):
        evidencias.append("forma_recente_gols")

    historico = contexto.get("historico_detalhado") or {}
    casa_h = historico.get("mandante") or {}
    fora_h = historico.get("visitante") or {}
    media_historica = _soma_numeros(
        casa_h.get("gols_pro_media"), casa_h.get("gols_contra_media"),
        fora_h.get("gols_pro_media"), fora_h.get("gols_contra_media"),
    )
    if (
        (_numero(casa_h.get("jogos")) or 0) >= 3
        and (_numero(fora_h.get("jogos")) or 0) >= 3
        and media_historica is not None and media_historica / 2 >= 2.2
    ):
        evidencias.append("historico_detalhado_gols")

    temporada = contexto.get("estatisticas_temporada") or {}
    casa_t = temporada.get("mandante") or {}
    fora_t = temporada.get("visitante") or {}
    media_temporada = _soma_numeros(
        casa_t.get("gols_pro_media"), casa_t.get("gols_contra_media"),
        fora_t.get("gols_pro_media"), fora_t.get("gols_contra_media"),
    )
    if media_temporada is not None and media_temporada / 2 >= 2.2:
        evidencias.append("temporada_gols")

    previsao = contexto.get("previsao_provedor") or {}
    texto_over = str(previsao.get("over_under") or "")
    numeros_over = [_numero(item) for item in re.findall(r"\d+(?:[.,]\d+)?", texto_over)]
    gols_esperados = previsao.get("gols_esperados") or {}
    soma_esperada = _soma_numeros(*gols_esperados.values())
    if (
        any(valor is not None and valor >= 1.5 for valor in numeros_over)
        or (soma_esperada is not None and soma_esperada >= 2.0)
    ):
        evidencias.append("previsao_provedor_gols")

    odds_pre = ((contexto.get("odds_pre_jogo") or {}).get("cobertura") or {})
    if odds_pre.get("gols_ft") is True:
        evidencias.append("consenso_odds_pre_jogo")
    return evidencias


def _evidencias_live(candidato, contexto):
    features = candidato.get("features") or {}
    janela5 = ((features.get("janelas") or {}).get("5") or {})
    evidencias = []
    if (_numero(janela5.get("chutes_total")) or 0) >= 2:
        evidencias.append("chutes_5min")
    if (_numero(features.get("chutes_no_gol_total")) or 0) >= 1:
        evidencias.append("chute_no_gol")
    picos = janela5.get("pressao_pico") or []
    if isinstance(picos, (int, float, str)):
        picos = [picos]
    if max([_numero(valor) or 0 for valor in picos] or [0]) >= 65:
        evidencias.append("pressao_5min")

    estatisticas_live = (contexto or {}).get("estatisticas_ao_vivo") or {}
    times = estatisticas_live.get("times") or {}
    xg_total = _soma_numeros(
        (times.get("mandante") or {}).get("xg"),
        (times.get("visitante") or {}).get("xg"),
    )
    if xg_total is not None and xg_total >= 0.20:
        evidencias.append("xg_ao_vivo")
    return evidencias, xg_total


def _padrao_gols_por_faixa(contexto, faixa):
    """Confirma concentração de gols feitos/sofridos na faixa da temporada."""
    temporada = (contexto or {}).get("estatisticas_temporada") or {}
    evidencias = []
    totais = []
    for lado, adversario in (("mandante", "visitante"), ("visitante", "mandante")):
        time = temporada.get(lado) or {}
        rival = temporada.get(adversario) or {}
        try:
            jogos_time = int(time.get("jogos") or 0)
            jogos_rival = int(rival.get("jogos") or 0)
        except (TypeError, ValueError):
            continue
        if jogos_time < 5 or jogos_rival < 5:
            continue
        pro = ((time.get("gols_pro_por_minuto") or {}).get(faixa) or {})
        contra = ((rival.get("gols_contra_por_minuto") or {}).get(faixa) or {})
        total_pro = _numero(pro.get("total")) or 0
        total_contra = _numero(contra.get("total")) or 0
        percentual_pro = _numero(pro.get("percentual")) or 0
        percentual_contra = _numero(contra.get("percentual")) or 0
        for item in (total_pro, total_contra):
            if item:
                totais.append(item)
        if (
            total_pro + total_contra >= 4
            and max(percentual_pro, percentual_contra) >= 15
        ):
            evidencias.append(f"faixa_{faixa}_{lado}")
    return {
        "faixa": faixa,
        "evidencias": evidencias,
        "total_gols_amostra_faixa": int(sum(totais)),
        "confirmado": bool(evidencias),
    }


def _padrao_gols_primeiro_tempo(contexto, minuto):
    faixa = "0-15" if minuto <= 15 else "16-30"
    return _padrao_gols_por_faixa(contexto, faixa)


def _padrao_gols_segundo_tempo(contexto, minuto):
    if minuto <= 59:
        faixa = "46-60"
    elif minuto <= 75:
        faixa = "61-75"
    else:
        faixa = "76-90"
    return _padrao_gols_por_faixa(contexto, faixa)


def _clone_antecipado(base, versao, minuto, evidencias_pre, evidencias_live, xg_total):
    item = copy.deepcopy(base)
    bloqueios = [
        motivo for motivo in item.get("bloqueios") or []
        if motivo not in _BLOQUEIOS_RELAXAVEIS
    ]
    if bloqueios:
        return None
    item["status"] = "simulacao"
    item["bloqueios"] = []
    item["pontuacao_tecnica"] = round(min(
        100.0,
        70.0 + min(len(evidencias_pre), 4) * 3.5
        + min(len(evidencias_live), 4) * 4.0,
    ), 1)
    item["motivos"] = [
        "padrao_antecipado_pre_jogo_e_ao_vivo",
        f"evidencias_pre={len(evidencias_pre)}",
        f"evidencias_live={len(evidencias_live)}",
    ]
    features = copy.deepcopy(item.get("features") or {})
    features["exploracao_sombra"] = {
        "versao": versao,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
        "grupo_teste": gols_antecipados_grupo_ativo(),
    }
    features["gol_antecipado"] = {
        "versao": VERSAO_POLITICA,
        "linhagem_sha256": LINHAGEM_GOLS_ANTECIPADOS,
        "minuto": minuto,
        "placar_exigido": [0, 0],
        "evidencias_pre_jogo": list(evidencias_pre),
        "evidencias_ao_vivo": list(evidencias_live),
        "xg_ao_vivo_total": xg_total,
        "qualidade_minima": QUALIDADE_MINIMA,
        "odd_minima": obter_limites_risco().odd_minima,
        "odd_maxima": obter_limites_risco().odd_maxima,
        "somente_simulacao": True,
    }
    item["features"] = features
    return item


def gerar_gols_antecipados(jogo, candidatos, contexto_pre_jogo, qualidade):
    """Gera braços independentes HT/FT; nunca promove sinal oficial."""
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    try:
        nota_qualidade = float((qualidade or {}).get("pontuacao") or 0)
    except (TypeError, ValueError):
        nota_qualidade = 0
    if (
        placar is None or minuto is None
        or not (
            MINUTO_MINIMO <= minuto <= max(
                MINUTO_MAXIMO_HT, MINUTO_MAXIMO_FT
            )
            or MINUTO_MINIMO_2T <= minuto <= MINUTO_MAXIMO_2T
        )
        or nota_qualidade < QUALIDADE_MINIMA
        or (qualidade or {}).get("divergencia_critica") is True
        or not isinstance(contexto_pre_jogo, dict)
    ):
        return []
    evidencias_pre = _evidencias_pre_jogo(contexto_pre_jogo)
    if len(evidencias_pre) < MINIMO_EVIDENCIAS_PRE:
        return []
    por_mercado = {
        item.get("mercado"): item for item in candidatos or []
        if item.get("mercado") in {"gol_ht", "gol_ft"}
    }
    resultado = []
    if MINUTO_MINIMO_2T <= minuto <= MINUTO_MAXIMO_2T:
        base = por_mercado.get("gol_ft")
        padrao_2t = _padrao_gols_segundo_tempo(contexto_pre_jogo, minuto)
        if base is None or not padrao_2t["confirmado"]:
            return []
        try:
            linha = float(base.get("linha"))
            odd = float(base.get("odd"))
        except (TypeError, ValueError):
            return []
        gols_atuais = placar[0] + placar[1]
        if linha != gols_atuais + 0.5 or not odd_elegivel(
            odd, obter_limites_risco()
        ):
            return []
        evidencias_live, xg_total = _evidencias_live(
            base, contexto_pre_jogo
        )
        minimo_live = 3 if minuto > 75 else MINIMO_EVIDENCIAS_LIVE
        if len(evidencias_live) < minimo_live:
            return []
        item = _clone_antecipado(
            base, VERSAO_GOL_FT_ANTECIPADO_2T, minuto,
            evidencias_pre, evidencias_live, xg_total,
        )
        if item is not None:
            item["features"]["gol_antecipado_2t"] = {
                **padrao_2t,
                "janela_minuto": [MINUTO_MINIMO_2T, MINUTO_MAXIMO_2T],
                "evidencias_live_minimas": minimo_live,
                "linha_exige_mais_um_gol": True,
                "somente_simulacao": True,
            }
            resultado.append(item)
        return resultado

    if placar != [0, 0]:
        return []
    for mercado, versao, limite in (
        ("gol_ht", VERSAO_GOL_HT_ANTECIPADO, MINUTO_MAXIMO_HT),
        ("gol_ft", VERSAO_GOL_FT_ANTECIPADO, MINUTO_MAXIMO_FT),
    ):
        base = por_mercado.get(mercado)
        if base is None or minuto > limite:
            continue
        try:
            linha = float(base.get("linha"))
            odd = float(base.get("odd"))
        except (TypeError, ValueError):
            continue
        if linha != 0.5 or not odd_elegivel(odd, obter_limites_risco()):
            continue
        padrao_ht = None
        if mercado == "gol_ht":
            padrao_ht = _padrao_gols_primeiro_tempo(
                contexto_pre_jogo, minuto
            )
            if not padrao_ht["confirmado"]:
                continue
        evidencias_live, xg_total = _evidencias_live(base, contexto_pre_jogo)
        minimo_live = (
            3 if mercado == "gol_ht" and minuto > 25
            else MINIMO_EVIDENCIAS_LIVE
        )
        if len(evidencias_live) < minimo_live:
            continue
        item = _clone_antecipado(
            base, versao, minuto, evidencias_pre, evidencias_live, xg_total
        )
        if item is not None:
            if mercado == "gol_ht":
                item["features"]["gol_antecipado_ht"] = {
                    **padrao_ht,
                    "janela_minuto": [MINUTO_MINIMO, MINUTO_MAXIMO_HT],
                    "evidencias_live_minimas": minimo_live,
                    "linha_exige_primeiro_gol_ht": True,
                    "grupo_teste": gols_antecipados_grupo_ativo(),
                    "retorno_sombra_por_flag": True,
                }
            resultado.append(item)
    return resultado
