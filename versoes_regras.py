"""Versões prospectivas ativas por mercado.

A regra padrão permanece estável para não reiniciar mercados não afetados por
uma correção localizada. Toda exceção precisa de versão própria e linhagem.
"""

VERSAO_REGRAS_PADRAO = "sinais-v6"
VERSAO_ESCANTEIOS_FT_ASIATICO = "sinais-v7-ft-asiatico"
VERSAO_PROXIMO_ESCANTEIO_MAX_86 = (
    "sinais-v9c-proximo-escanteio-max86"
)
VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86 = (
    "sinais-v9d-ft-asiatico-max86"
)

VERSOES_REGRAS_POR_MERCADO = {
    "proximo_escanteio": VERSAO_PROXIMO_ESCANTEIO_MAX_86,
    "escanteios_ft_asiatico": (
        VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86
    ),
}


def versao_regra_para_mercado(mercado):
    return VERSOES_REGRAS_POR_MERCADO.get(
        mercado, VERSAO_REGRAS_PADRAO
    )


def versoes_regras_ativas():
    return tuple(dict.fromkeys((
        VERSAO_REGRAS_PADRAO,
        *VERSOES_REGRAS_POR_MERCADO.values(),
    )))
