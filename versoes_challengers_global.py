"""Nova coorte de proximo gol sem alterar a linhagem v10b congelada."""

from versoes_challengers import (
    VERSAO_PROXIMO_GOL_ODD_166_MAX_75,
    VERSOES_CHALLENGERS_POR_MERCADO as VERSOES_ANTERIORES_POR_MERCADO,
    versao_regra_operacional as versao_regra_operacional_anterior,
    versoes_regras_operacionais as versoes_regras_operacionais_anteriores,
)


VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75 = (
    "sinais-v10e-proximo-gol-faixa-global-max75"
)
VERSOES_CHALLENGERS_POR_MERCADO = {
    **VERSOES_ANTERIORES_POR_MERCADO,
    "proximo_gol": VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
}
VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO = (
    VERSOES_CHALLENGERS_POR_MERCADO
)


def versao_regra_operacional(mercado):
    return VERSOES_CHALLENGERS_POR_MERCADO.get(
        mercado, versao_regra_operacional_anterior(mercado)
    )


def versoes_regras_operacionais():
    return tuple(dict.fromkeys((
        *versoes_regras_operacionais_anteriores(),
        *VERSOES_CHALLENGERS_POR_MERCADO.values(),
    )))
