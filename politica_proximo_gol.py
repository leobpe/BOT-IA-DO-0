"""Política prospectiva auditável para o mercado de próximo gol."""

from versoes_challengers import VERSAO_PROXIMO_GOL_ODD_166_MAX_75


MERCADO = "proximo_gol"
ODD_MINIMA = 1.66
MINUTO_MAXIMO = 75
MOTIVO_ODD = "fora_da_faixa_proximo_gol_odd_min_166"
MOTIVO_MINUTO = "fora_da_janela_proximo_gol_max_75"


def aplicar_politica_proximo_gol(candidato):
    """Versiona e aplica somente a coorte prospectiva pré-registrada."""
    if candidato.get("mercado") != MERCADO:
        return candidato

    candidato["regra_versao"] = VERSAO_PROXIMO_GOL_ODD_166_MAX_75
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

    if odd is not None and odd < ODD_MINIMA and MOTIVO_ODD not in bloqueios:
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
        "regra_prospectiva_odd_minima_166",
        "regra_prospectiva_minuto_maximo_75",
    ):
        if motivo not in motivos:
            motivos.append(motivo)
    candidato["motivos"] = motivos
    if bloqueios:
        candidato["status"] = "rejeitado"
    return candidato
