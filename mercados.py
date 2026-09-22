import os


MERCADOS_GOLS = (
    "gol_ft",
    "gol_ht",
    "proximo_gol",
)

MERCADOS_ESCANTEIOS = (
    "proximo_escanteio",
    "escanteios_ft_asiatico",
    "escanteios_1t",
    "escanteios_2t",
)

MERCADOS_CALIBRADOS = MERCADOS_GOLS + MERCADOS_ESCANTEIOS

MERCADOS_ASIATICOS_POR_TEMPO = (
    "escanteios_1t",
    "escanteios_2t",
)

MERCADOS_PRIMEIRO_TEMPO = (
    "gol_ht",
    "escanteios_1t",
)

ROTULOS_MERCADOS = {
    "gol_ft": "Over de gols FT",
    "gol_ht": "Gol no primeiro tempo",
    "proximo_gol": "Próximo gol",
    "proximo_escanteio": "Escanteio normal — próximo escanteio",
    "escanteios_ft_asiatico": "Over de Escanteios Asiáticos — jogo inteiro",
    "escanteios_1t": "Over de Escanteios Asiáticos — 1º tempo",
    "escanteios_2t": "Over de Escanteios Asiáticos — 2º tempo",
}


def escanteios_asiaticos_periodos_ativos(environ=None):
    """Ativa 1T/2T somente mediante decisão operacional explícita."""
    ambiente = os.environ if environ is None else environ
    return (
        str(
            ambiente.get(
                "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS",
                "0",
            )
        ).strip()
        == "1"
    )


def mercados_calibrados_operacionais(environ=None):
    """Mercados exigidos na operacao, preservando os suspensos no historico."""
    if escanteios_asiaticos_periodos_ativos(environ):
        return MERCADOS_CALIBRADOS
    suspensos = set(MERCADOS_ASIATICOS_POR_TEMPO)
    return tuple(
        mercado for mercado in MERCADOS_CALIBRADOS
        if mercado not in suspensos
    )


def filtrar_mercados_operacionais(candidatos, environ=None):
    """Remove somente novas decisões de mercados suspensos."""
    itens = list(candidatos or [])
    if escanteios_asiaticos_periodos_ativos(environ):
        return itens
    suspensos = set(MERCADOS_ASIATICOS_POR_TEMPO)
    return [
        candidato
        for candidato in itens
        if candidato.get("mercado") not in suspensos
    ]
