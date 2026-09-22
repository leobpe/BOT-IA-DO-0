"""Política prospectiva isolada para Gol HT até o minuto 28."""

from versoes_operacionais import VERSAO_GOL_HT_MAX_28


MERCADO = "gol_ht"
MINUTO_MAXIMO = 28


def aplicar_politica_gol_ht(candidato):
    if candidato.get("mercado") != MERCADO:
        return candidato
    candidato["regra_versao"] = VERSAO_GOL_HT_MAX_28
    bloqueios = list(candidato.get("bloqueios") or [])
    minuto = (candidato.get("features") or {}).get("minuto")
    try:
        minuto = float(minuto) if minuto is not None else None
    except (TypeError, ValueError):
        minuto = None
    if (
        minuto is not None
        and minuto > MINUTO_MAXIMO
        and "fora_da_janela_gol_ht_max_28" not in bloqueios
    ):
        bloqueios.append("fora_da_janela_gol_ht_max_28")
    candidato["bloqueios"] = bloqueios
    if bloqueios:
        candidato["status"] = "rejeitado"
    return candidato
