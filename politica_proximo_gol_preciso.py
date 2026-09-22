"""Filtro prospectivo de Próximo Gol baseado na análise até 26/08/2026."""

from configuracao import obter_limites_risco
from politica_proximo_gol_faixa_global import (
    aplicar_politica_proximo_gol as aplicar_politica_anterior,
)
from versoes_challengers_preciso import (
    PROXIMO_GOL_FILTRO_PRECISO_ATIVO,
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)


MERCADO = "proximo_gol"
MINUTO_MAXIMO = 75
ODD_MAXIMA_EXCLUSIVA = 2.0
QUALIDADE_MINIMA = 100.0
PRESSAO_PICO_5_MIN_MINIMA = 70.0
MOTIVO_ODD = "odd_proximo_gol_fora_144_199"
MOTIVO_MINUTO = "fora_da_janela_proximo_gol_max_75"
MOTIVO_QUALIDADE = "qualidade_proximo_gol_abaixo_100"
MOTIVO_PRESSAO = "pressao_pico_dominante_5min_abaixo_70"


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def avaliar_criterios_precisos(candidato):
    if candidato.get("mercado") != MERCADO:
        return []
    features = candidato.get("features") or {}
    bloqueios = []
    odd = _numero(candidato.get("odd"))
    minuto = _numero(features.get("minuto"))
    qualidade = _numero(features.get("qualidade_dados"))
    lado = features.get("lado_dominante")
    indice = 0 if lado == "casa" else 1 if lado == "visitante" else None
    picos = (((features.get("janelas") or {}).get("5") or {}).get(
        "pressao_pico"
    ) or [])
    pico = None
    if indice is not None and len(picos) > indice:
        pico = _numero(picos[indice])

    limites = obter_limites_risco()
    if odd is None or not limites.odd_minima <= odd < ODD_MAXIMA_EXCLUSIVA:
        bloqueios.append(MOTIVO_ODD)
    if minuto is None or minuto > MINUTO_MAXIMO:
        bloqueios.append(MOTIVO_MINUTO)
    if qualidade is None or qualidade < QUALIDADE_MINIMA:
        bloqueios.append(MOTIVO_QUALIDADE)
    if pico is None or pico < PRESSAO_PICO_5_MIN_MINIMA:
        bloqueios.append(MOTIVO_PRESSAO)
    return bloqueios


def aplicar_politica_proximo_gol(candidato):
    if candidato.get("mercado") != MERCADO:
        return candidato
    if not PROXIMO_GOL_FILTRO_PRECISO_ATIVO:
        return aplicar_politica_anterior(candidato)

    candidato["regra_versao"] = VERSAO_PROXIMO_GOL_FILTRO_PRECISO
    bloqueios = list(candidato.get("bloqueios") or [])
    for motivo in avaliar_criterios_precisos(candidato):
        if motivo not in bloqueios:
            bloqueios.append(motivo)
    candidato["bloqueios"] = bloqueios

    motivos = list(candidato.get("motivos") or [])
    for motivo in (
        "regra_prospectiva_odd_abaixo_2",
        "regra_prospectiva_qualidade_100",
        "regra_prospectiva_pressao_pico_5min_min70",
        "regra_prospectiva_minuto_maximo_75",
    ):
        if motivo not in motivos:
            motivos.append(motivo)
    candidato["motivos"] = motivos
    features = candidato.setdefault("features", {})
    features["filtro_proximo_gol_preciso"] = {
        "versao": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
        "odd_maxima_exclusiva": ODD_MAXIMA_EXCLUSIVA,
        "qualidade_minima": QUALIDADE_MINIMA,
        "pressao_pico_5min_minima": PRESSAO_PICO_5_MIN_MINIMA,
        "minuto_maximo": MINUTO_MAXIMO,
        "rollback": "PROXIMO_GOL_FILTRO_PRECISO_ATIVO=0",
    }
    if bloqueios:
        candidato["status"] = "rejeitado"
    return candidato
