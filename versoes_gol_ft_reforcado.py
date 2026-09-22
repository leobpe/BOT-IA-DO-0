"""Roteamento prospectivo do Gol FT reforcado com rollback explicito."""

import os

from versoes_challengers_preciso import (
    VERSOES_CHALLENGERS_POR_MERCADO as VERSOES_ANTERIORES_POR_MERCADO,
    versao_regra_operacional as versao_regra_operacional_anterior,
)
from versoes_proximo_gol_balanceado import (
    versoes_regras_operacionais as versoes_regras_operacionais_anteriores,
)
from versoes_gol_ht_protegido import VERSAO_GOL_HT_PROTEGIDO


VERSAO_GOL_FT_REFORCADO_ANTERIOR = (
    "sinais-v11-gol-ft-reforcado-max70-xg15-pb375"
)
VERSAO_GOL_FT_REFORCADO = (
    "sinais-v11b-gol-ft-reforcado-sombra-prospectiva-75"
)


def gol_ft_reforcado_ativo(environ=None):
    ambiente = os.environ if environ is None else environ
    return str(
        ambiente.get("GOL_FT_REFORCADO_ATIVO", "1")
    ).strip().casefold() not in {"0", "false", "nao", "não", "off"}


def gol_ft_reforcado_oficial_ativo(environ=None):
    """Libera Telegram apenas por decisão operacional explícita.

    O padrão seguro é sombra porque as versões históricas de Gol FT ainda
    não demonstraram ROI positivo fora da amostra de desenvolvimento.
    """
    ambiente = os.environ if environ is None else environ
    return str(
        ambiente.get("GOL_FT_REFORCADO_OFICIAL_ATIVO", "0")
    ).strip().casefold() in {"1", "true", "sim", "yes", "on"}


VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO = {
    **VERSOES_ANTERIORES_POR_MERCADO,
    "gol_ht": VERSAO_GOL_HT_PROTEGIDO,
    "gol_ft": VERSAO_GOL_FT_REFORCADO,
}


def versao_regra_operacional(mercado):
    if mercado == "gol_ft" and not gol_ft_reforcado_ativo():
        return versao_regra_operacional_anterior(mercado)
    return VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO.get(
        mercado, versao_regra_operacional_anterior(mercado)
    )


def versoes_regras_operacionais():
    return tuple(dict.fromkeys((
        *versoes_regras_operacionais_anteriores(),
        VERSAO_GOL_HT_PROTEGIDO,
        VERSAO_GOL_FT_REFORCADO,
    )))
