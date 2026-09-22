"""Politica prospectiva de proximo gol com a faixa global de odds."""

from configuracao import obter_limites_risco
from versoes_challengers_global import VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75


MERCADO = "proximo_gol"
MINUTO_MAXIMO = 75
MOTIVO_ODD = "fora_da_faixa_operacional_global"
MOTIVO_MINUTO = "fora_da_janela_proximo_gol_max_75"


def aplicar_politica_proximo_gol(candidato):
    """Aplica a mesma faixa de odds dos demais mercados e preserva max 75."""
    if candidato.get("mercado") != MERCADO:
        return candidato

    candidato["regra_versao"] = VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75
    bloqueios = list(candidato.get("bloqueios") or [])
    try:
        odd = float(candidato.get("odd"))
    except (TypeError, ValueError):
        odd = None
    minuto = (candidato.get("features") or {}).get("minuto")
    try:
        minuto = float(minuto)
    except (TypeError, ValueError):
        minuto = None

    limites = obter_limites_risco()
    if (
        odd is not None
        and not limites.odd_minima <= odd <= limites.odd_maxima
        and MOTIVO_ODD not in bloqueios
    ):
        bloqueios.append(MOTIVO_ODD)
    if (
        minuto is not None
        and minuto > MINUTO_MAXIMO
        and MOTIVO_MINUTO not in bloqueios
    ):
        bloqueios.append(MOTIVO_MINUTO)

    candidato["bloqueios"] = bloqueios
    motivos = list(candidato.get("motivos") or [])
    for motivo in (
        "regra_prospectiva_faixa_odd_operacional_global",
        "regra_prospectiva_minuto_maximo_75",
    ):
        if motivo not in motivos:
            motivos.append(motivo)
    candidato["motivos"] = motivos
    if bloqueios:
        candidato["status"] = "rejeitado"
    return candidato
