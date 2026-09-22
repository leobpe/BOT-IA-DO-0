"""Roteamento do Próximo Gol preciso com rollback para a V10e."""

import os

from versoes_challengers_global import (
    VERSOES_CHALLENGERS_POR_MERCADO as VERSOES_ANTERIORES_POR_MERCADO,
    versao_regra_operacional as versao_regra_operacional_anterior,
    versoes_regras_operacionais as versoes_regras_operacionais_anteriores,
)


VERSAO_PROXIMO_GOL_FILTRO_PRECISO = (
    "sinais-v10f-proximo-gol-oddmax199-q100-p70-max75"
)
PROXIMO_GOL_FILTRO_PRECISO_ATIVO = os.getenv(
    "PROXIMO_GOL_FILTRO_PRECISO_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}

VERSOES_CHALLENGERS_POR_MERCADO = {
    **VERSOES_ANTERIORES_POR_MERCADO,
    "proximo_gol": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
}
VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO = (
    VERSOES_CHALLENGERS_POR_MERCADO
)


def versao_regra_operacional(mercado):
    if not PROXIMO_GOL_FILTRO_PRECISO_ATIVO:
        return versao_regra_operacional_anterior(mercado)
    return VERSOES_CHALLENGERS_POR_MERCADO.get(
        mercado, versao_regra_operacional_anterior(mercado)
    )


def versoes_regras_operacionais():
    return tuple(dict.fromkeys((
        *versoes_regras_operacionais_anteriores(),
        VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
    )))
