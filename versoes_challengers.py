"""Sobreposição prospectiva sem alterar versões já vinculadas no banco."""

from versoes_operacionais import (
    VERSAO_GOL_HT_MAX_28,
    VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO,
    versao_regra_operacional as versao_regra_operacional_anterior,
    versoes_regras_operacionais as versoes_regras_operacionais_anteriores,
)


VERSAO_PROXIMO_GOL_ODD_166_MAX_75 = (
    "sinais-v10b-proximo-gol-odd166-max75"
)
VERSOES_CHALLENGERS_POR_MERCADO = {
    **VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO,
    "proximo_gol": VERSAO_PROXIMO_GOL_ODD_166_MAX_75,
}


def versao_regra_operacional(mercado):
    return VERSOES_CHALLENGERS_POR_MERCADO.get(
        mercado, versao_regra_operacional_anterior(mercado)
    )


def versoes_regras_operacionais():
    return tuple(dict.fromkeys((
        *versoes_regras_operacionais_anteriores(),
        *VERSOES_CHALLENGERS_POR_MERCADO.values(),
    )))
