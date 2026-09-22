"""Tetos operacionais para mercados de gols, sem minuto minimo."""

MINUTO_MAXIMO_GOL_HT = 28
MINUTO_MAXIMO_GOL_FT = 82
VERSAO_POLITICA = "politica-gols-somente-teto-v1"


def aplicar_politica_gols_tempo(candidato):
    mercado = candidato.get("mercado")
    if mercado not in {"gol_ht", "gol_ft"}:
        return candidato
    minuto = (candidato.get("features") or {}).get("minuto")
    try:
        minuto = float(minuto) if minuto is not None else None
    except (TypeError, ValueError):
        minuto = None
    limite = MINUTO_MAXIMO_GOL_HT if mercado == "gol_ht" else MINUTO_MAXIMO_GOL_FT
    bloqueios = list(candidato.get("bloqueios") or [])
    if minuto is None:
        motivo = "minuto_indisponivel"
    elif minuto > limite:
        motivo = f"fora_da_janela_{mercado}_max_{limite}"
    else:
        motivo = None
    if motivo and motivo not in bloqueios:
        bloqueios.append(motivo)
    candidato["bloqueios"] = bloqueios
    if bloqueios:
        candidato["status"] = "rejeitado"
    candidato.setdefault("features", {})["politica_tempo_gols"] = {
        "versao": VERSAO_POLITICA,
        "somente_limite_final": True,
        "minuto_maximo": limite,
    }
    return candidato
