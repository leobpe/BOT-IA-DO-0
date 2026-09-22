"""Filtro prospectivo de maior precisão para o Gol HT antecipado.

O gerador V2 continua registrando a população completa. Este módulo atua
somente no roteamento ao grupo de teste e exige preço fresco, atividade
recente objetiva e apoio histórico da faixa do primeiro tempo. O recorte foi
escolhido como hipótese; desempenho passado nunca o promove automaticamente.
"""

from __future__ import annotations

import json
import math
import os

from filtro_ht_chutes_recentes import validar_janela_chutes_recentes
from gols_antecipados import VERSAO_GOL_HT_ANTECIPADO


VERSAO = "filtro-gol-ht-antecipado-preciso-v1"
METODO = VERSAO_GOL_HT_ANTECIPADO
ROLLBACK = "FILTRO_GOL_HT_ANTECIPADO_PRECISO_ATIVO"

MINUTO_MINIMO = 10.0
MINUTO_MAXIMO = 28.0
ODD_MINIMA = 1.40
ODD_MAXIMA = 2.00
QUALIDADE_MINIMA = 80.0
IDADE_ODD_MAXIMA_SEGUNDOS = 120.0
CHUTES_RECENTES_MINIMOS = 2
CHUTES_NO_GOL_MINIMOS = 2
GOLS_HISTORICOS_FAIXA_MINIMOS = 12


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


def _total_chutes_no_gol(features):
    par = features.get("chutes_no_gol")
    total = _numero(features.get("chutes_no_gol_total"))
    if not isinstance(par, (list, tuple)) or len(par) != 2:
        return None
    valores = [_numero(valor) for valor in par]
    if any(
        valor is None or valor < 0 or not valor.is_integer()
        for valor in valores
    ):
        return None
    soma = sum(valores)
    if total is None or total < 0 or not total.is_integer():
        return None
    if not math.isclose(soma, total, abs_tol=1e-9):
        return None
    return int(total)


def avaliar_filtro_gol_ht_antecipado(candidato, env=None):
    """Decide o filtro sem rede, escrita, promoção ou consulta a resultado."""
    env = os.environ if env is None else env
    features = _features(candidato)
    metodo = (features.get("exploracao_sombra") or {}).get("versao")
    aplicavel = bool(
        candidato.get("mercado") == "gol_ht" and metodo == METODO
    )
    base = {
        "versao": VERSAO,
        "metodo": METODO,
        "aplicavel": aplicavel,
        "aprovada": True,
        "motivo": "outro_metodo",
        "rollback": f"{ROLLBACK}=0",
        "promocao_automatica": False,
    }
    if not aplicavel:
        return base
    if str(env.get(ROLLBACK, "0")).strip() != "1":
        return {**base, "motivo": "desativado"}

    antecipado = features.get("gol_antecipado") or {}
    antecipado_ht = features.get("gol_antecipado_ht") or {}
    minuto = _numero(antecipado.get("minuto"))
    odd = _numero(candidato.get("odd"))
    qualidade = _numero(features.get("qualidade_dados"))
    idade_odd = _numero(features.get("idade_odds_segundos"))
    chutes_recentes = validar_janela_chutes_recentes(
        ((features.get("janelas") or {}).get("5") or {})
    )
    chutes_no_gol = _total_chutes_no_gol(features)
    gols_faixa = _numero(
        antecipado_ht.get("total_gols_amostra_faixa")
    )
    medidas = {
        "minuto": minuto,
        "odd": odd,
        "qualidade_dados": qualidade,
        "idade_odds_segundos": idade_odd,
        "odds_cache": features.get("odds_cache"),
        "chutes_5min": (
            chutes_recentes.get("chutes_total")
            if chutes_recentes else None
        ),
        "chutes_no_gol_total": chutes_no_gol,
        "gols_historicos_faixa": gols_faixa,
        "faixa_confirmada": antecipado_ht.get("confirmado"),
    }

    def rejeitar(motivo):
        return {
            **base,
            "aprovada": False,
            "motivo": motivo,
            "medidas": medidas,
        }

    if minuto is None or not MINUTO_MINIMO <= minuto <= MINUTO_MAXIMO:
        return rejeitar("minuto_fora_da_janela_precisa")
    if odd is None or not ODD_MINIMA <= odd <= ODD_MAXIMA:
        return rejeitar("odd_fora_da_faixa_precisa")
    if qualidade is None or qualidade < QUALIDADE_MINIMA:
        return rejeitar("qualidade_dados_insuficiente")
    if (
        features.get("odds_cache") is not False
        or idade_odd is None
        or not 0 <= idade_odd <= IDADE_ODD_MAXIMA_SEGUNDOS
    ):
        return rejeitar("odd_sem_frescor_confirmado")
    if chutes_recentes is None:
        return rejeitar("janela_chutes_5min_invalida")
    if chutes_recentes["chutes_total"] < CHUTES_RECENTES_MINIMOS:
        return rejeitar("chutes_5min_insuficientes")
    if chutes_no_gol is None:
        return rejeitar("chutes_no_gol_inconsistentes")
    if chutes_no_gol < CHUTES_NO_GOL_MINIMOS:
        return rejeitar("chutes_no_gol_insuficientes")
    if antecipado_ht.get("confirmado") is not True:
        return rejeitar("faixa_historica_nao_confirmada")
    if (
        gols_faixa is None
        or gols_faixa < GOLS_HISTORICOS_FAIXA_MINIMOS
    ):
        return rejeitar("amostra_gols_faixa_insuficiente")
    return {
        **base,
        "aprovada": True,
        "motivo": "criterios_precisos_confirmados",
        "medidas": medidas,
        "limites": {
            "minuto": [MINUTO_MINIMO, MINUTO_MAXIMO],
            "odd": [ODD_MINIMA, ODD_MAXIMA],
            "qualidade_dados_minima": QUALIDADE_MINIMA,
            "idade_odd_maxima_segundos": IDADE_ODD_MAXIMA_SEGUNDOS,
            "chutes_5min_minimos": CHUTES_RECENTES_MINIMOS,
            "chutes_no_gol_minimos": CHUTES_NO_GOL_MINIMOS,
            "gols_historicos_faixa_minimos": (
                GOLS_HISTORICOS_FAIXA_MINIMOS
            ),
        },
    }
