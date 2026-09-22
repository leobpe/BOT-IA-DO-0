"""Filtro reversível do Gol FT antecipado no segundo tempo.

O gerador original continua produzindo toda a população em sombra. A entrega
usa uma janela inicial do segundo tempo, preço fresco, histórico mínimo e
atividade recente verificável. O histórico só gera a hipótese; uma coorte
futura separada decide se existe vantagem.
"""

import json
import math
import os


VERSAO = "filtro-gol-ft-antecipado-preciso-v2"
METODO = "gol-ft-antecipado-2t-faixa-historica-v1"
ROLLBACK = "FILTRO_GOL_FT_ANTECIPADO_PRECISO_ATIVO"

MINUTO_MINIMO = 46.0
MINUTO_MAXIMO = 60.0
ODD_MINIMA = 1.40
ODD_MAXIMA_EXCLUSIVA = 1.90
QUALIDADE_MINIMA = 80.0
IDADE_ODD_MAXIMA_SEGUNDOS = 120.0
EVIDENCIAS_LIVE_MINIMAS = 2
GOLS_HISTORICOS_FAIXA_MINIMOS = 12
CHUTES_RECENTES_MINIMOS = 1.0


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _features(candidato):
    features = candidato.get("features")
    if isinstance(features, dict):
        return features
    try:
        features = json.loads(candidato.get("features_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return features if isinstance(features, dict) else {}


def _par_consistente(par, total):
    if not isinstance(par, (list, tuple)) or len(par) != 2:
        return False
    numeros = [_numero(valor) for valor in par]
    total = _numero(total)
    return bool(
        total is not None
        and all(valor is not None and valor >= 0 for valor in numeros)
        and abs(sum(numeros) - total) <= 0.001
    )


def avaliar_filtro_gol_ft_antecipado(candidato, env=None):
    """Retorna decisão pura; nunca promove candidato nem consulta rede."""
    env = os.environ if env is None else env
    features = _features(candidato)
    metodo = (features.get("exploracao_sombra") or {}).get("versao")
    aplicavel = bool(
        candidato.get("mercado") == "gol_ft" and metodo == METODO
    )
    base = {
        "versao": VERSAO,
        "aplicavel": aplicavel,
        "aprovada": True,
        "motivo": "outro_metodo",
        "rollback": f"{ROLLBACK}=0",
    }
    if not aplicavel:
        return base
    if str(env.get(ROLLBACK, "0")).strip() != "1":
        return {**base, "motivo": "desativado"}

    antecipado = features.get("gol_antecipado") or {}
    antecipado_2t = features.get("gol_antecipado_2t") or {}
    janela_5 = (features.get("janelas") or {}).get("5") or {}
    minuto = _numero(antecipado.get("minuto"))
    odd = _numero(candidato.get("odd"))
    qualidade = _numero(features.get("qualidade_dados"))
    idade_odd = _numero(features.get("idade_odds_segundos"))
    evidencias = antecipado.get("evidencias_ao_vivo") or []
    if not isinstance(evidencias, (list, tuple, set)):
        evidencias = []
    evidencias = len(set(map(str, evidencias)))
    historico = _numero(
        antecipado_2t.get("total_gols_amostra_faixa")
    )
    chutes_5 = _numero(janela_5.get("chutes_total"))
    chutes_no_gol = _numero(features.get("chutes_no_gol_total"))
    chutes_5_consistentes = _par_consistente(
        janela_5.get("chutes"), chutes_5
    )
    chutes_no_gol_consistentes = _par_consistente(
        features.get("chutes_no_gol"), chutes_no_gol
    )
    medidas = {
        "minuto": minuto,
        "odd": odd,
        "qualidade_dados": qualidade,
        "idade_odds_segundos": idade_odd,
        "odds_cache": features.get("odds_cache"),
        "evidencias_live": evidencias,
        "historico_confirmado": antecipado_2t.get("confirmado"),
        "gols_historicos_faixa": historico,
        "janela_5_disponivel": janela_5.get("disponivel"),
        "janela_5_resets": list(janela_5.get("resets_detectados") or []),
        "chutes_5min": chutes_5,
        "chutes_5min_consistentes": chutes_5_consistentes,
        "chutes_no_gol_total": chutes_no_gol,
        "chutes_no_gol_consistentes": chutes_no_gol_consistentes,
    }

    if minuto is None or not MINUTO_MINIMO <= minuto <= MINUTO_MAXIMO:
        return {
            **base, "aprovada": False,
            "motivo": "minuto_fora_da_janela", "medidas": medidas,
        }
    if odd is None or not ODD_MINIMA <= odd < ODD_MAXIMA_EXCLUSIVA:
        return {
            **base, "aprovada": False,
            "motivo": "odd_fora_da_faixa_precisa", "medidas": medidas,
        }
    if qualidade is None or qualidade < QUALIDADE_MINIMA:
        return {
            **base, "aprovada": False,
            "motivo": "qualidade_dados_insuficiente", "medidas": medidas,
        }
    if features.get("odds_cache") is not False:
        return {
            **base, "aprovada": False,
            "motivo": "odd_cache_ou_origem_incerta", "medidas": medidas,
        }
    if (
        idade_odd is None
        or idade_odd < 0
        or idade_odd > IDADE_ODD_MAXIMA_SEGUNDOS
    ):
        return {
            **base, "aprovada": False,
            "motivo": "odd_desatualizada_ou_sem_idade", "medidas": medidas,
        }
    if evidencias < EVIDENCIAS_LIVE_MINIMAS:
        return {
            **base, "aprovada": False,
            "motivo": "evidencias_live_insuficientes", "medidas": medidas,
        }
    if antecipado_2t.get("confirmado") is not True:
        return {
            **base, "aprovada": False,
            "motivo": "historico_faixa_nao_confirmado", "medidas": medidas,
        }
    if (
        historico is None
        or historico < GOLS_HISTORICOS_FAIXA_MINIMOS
    ):
        return {
            **base, "aprovada": False,
            "motivo": "historico_faixa_insuficiente", "medidas": medidas,
        }
    if (
        janela_5.get("disponivel") is not True
        or bool(janela_5.get("resets_detectados"))
    ):
        return {
            **base, "aprovada": False,
            "motivo": "janela_5min_invalida", "medidas": medidas,
        }
    if chutes_5 is None or chutes_5 < CHUTES_RECENTES_MINIMOS:
        return {
            **base, "aprovada": False,
            "motivo": "atividade_recente_insuficiente", "medidas": medidas,
        }
    if not chutes_5_consistentes:
        return {
            **base, "aprovada": False,
            "motivo": "chutes_5min_inconsistentes", "medidas": medidas,
        }
    if not chutes_no_gol_consistentes:
        return {
            **base, "aprovada": False,
            "motivo": "chutes_no_gol_inconsistentes", "medidas": medidas,
        }
    return {
        **base,
        "aprovada": True,
        "motivo": "criterios_precisos_confirmados",
        "medidas": medidas,
        "limites": {
            "minuto": [MINUTO_MINIMO, MINUTO_MAXIMO],
            "odd_minima": ODD_MINIMA,
            "odd_maxima_exclusiva": ODD_MAXIMA_EXCLUSIVA,
            "qualidade_minima": QUALIDADE_MINIMA,
            "idade_odd_maxima_segundos": IDADE_ODD_MAXIMA_SEGUNDOS,
            "evidencias_live_minimas": EVIDENCIAS_LIVE_MINIMAS,
            "gols_historicos_faixa_minimos": (
                GOLS_HISTORICOS_FAIXA_MINIMOS
            ),
            "chutes_recentes_minimos": CHUTES_RECENTES_MINIMOS,
        },
    }
