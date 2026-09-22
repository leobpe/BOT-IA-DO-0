"""Exceções prospectivas sem alterar a linhagem das versões preservadas."""

from versoes_regras import (
    VERSOES_REGRAS_POR_MERCADO as VERSOES_REGRAS_LEGADAS_POR_MERCADO,
    versao_regra_para_mercado as versao_regra_legada,
    versoes_regras_ativas as versoes_regras_legadas_ativas,
)


VERSAO_GOL_HT_MAX_28 = "sinais-v8b-gol-ht-max28"
VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO = {
    **VERSOES_REGRAS_LEGADAS_POR_MERCADO,
    "gol_ht": VERSAO_GOL_HT_MAX_28,
}


def versao_regra_operacional(mercado):
    return VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO.get(
        mercado, versao_regra_legada(mercado)
    )


def versoes_regras_operacionais():
    return tuple(dict.fromkeys((
        *versoes_regras_legadas_ativas(),
        *VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO.values(),
    )))
