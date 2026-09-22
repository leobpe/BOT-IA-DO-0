"""Versão prospectiva isolada do challenger balanceado de Próximo Gol.

O arquivo separado preserva o hash imutável da política V10f já coletada.
"""

from versoes_challengers_preciso import (
    versoes_regras_operacionais as versoes_regras_operacionais_anteriores,
)


VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA_V10I = (
    "sinais-v10i-proximo-gol-balanceado-teste-q100-p55-c1-d10-s60-oddmax159"
)
VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA = (
    "sinais-v10j-proximo-gol-balanceado-teste-q95-p50-c1-d10-s60-oddmax164"
)


def versoes_regras_operacionais():
    return tuple(dict.fromkeys((
        *versoes_regras_operacionais_anteriores(),
        VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA_V10I,
        VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
    )))
