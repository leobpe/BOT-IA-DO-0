"""Políticas prospectivas isoladas para os mercados de cantos ativos."""

from versoes_regras import versao_regra_para_mercado


MERCADOS = frozenset({
    "proximo_escanteio",
    "escanteios_ft_asiatico",
})
MERCADO_ASIATICO = "escanteios_ft_asiatico"
LIMIAR_APROVACAO = 75
ODDS_MAX_IDADE_SEGUNDOS = 360
MINUTO_MAXIMO = 86
MOTIVO_MINUTO = "fora_da_janela_escanteios_max_86"


def aplicar_politica_escanteios_ft(candidato):
    """Bloqueia 87+ e preserva a correção de idade do asiático FT."""
    mercado = candidato.get("mercado")
    if mercado not in MERCADOS:
        return candidato
    candidato["regra_versao"] = versao_regra_para_mercado(mercado)
    bloqueios = list(candidato.get("bloqueios") or [])
    minuto = (candidato.get("features") or {}).get("minuto")
    try:
        minuto = float(minuto) if minuto is not None else None
    except (TypeError, ValueError):
        minuto = None
    if (
        (minuto is None or minuto > MINUTO_MAXIMO)
        and MOTIVO_MINUTO not in bloqueios
    ):
        bloqueios.append(MOTIVO_MINUTO)
    idade = candidato.get("idade_odds_segundos")
    try:
        idade = float(idade) if idade is not None else None
    except (TypeError, ValueError):
        idade = None
    if (
        mercado == MERCADO_ASIATICO
        and
        idade is not None
        and idade <= ODDS_MAX_IDADE_SEGUNDOS
        and "odds_desatualizadas" in bloqueios
    ):
        bloqueios = [
            item for item in bloqueios
            if item != "odds_desatualizadas"
        ]
    candidato["bloqueios"] = bloqueios
    if mercado == MERCADO_ASIATICO:
        candidato["status"] = (
            "aprovado"
            if (
                candidato.get("odd") is not None
                and float(candidato.get("pontuacao_tecnica") or 0)
                >= LIMIAR_APROVACAO
                and not bloqueios
            )
            else "rejeitado"
        )
    elif bloqueios:
        candidato["status"] = "rejeitado"
    return candidato


def aplicar_politicas_por_mercado(candidatos):
    for candidato in candidatos:
        aplicar_politica_escanteios_ft(candidato)
    return candidatos
