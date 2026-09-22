"""Pre-registra o challenger de estado para Proximo Gol somente em sombra.

O historico abaixo serve apenas para gerar a hipotese. A avaliacao considera
exclusivamente sinais criados depois de ``iniciado_em`` e nunca promove nem
envia o challenger automaticamente.
"""

import json
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from hipoteses_sombra import registrar_hipotese_composta_sombra
from versoes_challengers_global import (
    VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
)


IDENTIFICADOR = (
    "proximo_gol_max70_sem_vantagem_2mais_v1_20260813"
)
REGRA_VERSAO = VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75
MERCADO = "proximo_gol"
CRITERIOS = [
    {
        "feature": "minuto",
        "operador": "menor_igual",
        "limiar": 70.0,
    },
    {
        "feature": "saldo_alvo_proximo_gol",
        "operador": "menor_igual",
        "limiar": 1.0,
    },
]
MINIMO_RESULTADOS = 60
EVIDENCIA_HISTORICA = {
    "regra_origem": VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
    "metodo": "primeira_decisao_independente_por_partida",
    "baseline": {
        "resultados_validos": 72,
        "greens": 44,
        "reds": 28,
        "lucro_unidades": 6.129,
        "roi": 0.0851,
    },
    "corte_exploratorio": {
        "descricao": (
            "minuto<=70 e saldo do lado escolhido para o proximo gol<=1"
        ),
        "resultados_validos": 58,
        "greens": 38,
        "reds": 20,
        "lucro_unidades": 9.149,
        "roi": 0.1577,
    },
    "controle_excluido": {
        "resultados_validos": 14,
        "greens": 6,
        "reds": 8,
        "lucro_unidades": -3.02,
        "roi": -0.2157,
    },
    "busca_exploratoria_multiplos_cortes": True,
    "uso": "somente_geracao_de_hipotese",
    "observacao": (
        "Os numeros historicos nao entram na confirmacao. Somente resultados "
        "prospectivos posteriores ao registro, comparados ao controle "
        "contemporaneo com IC95, podem comprovar superioridade."
    ),
}


def registrar(conexao, iniciado_em=None):
    return registrar_hipotese_composta_sombra(
        conexao,
        IDENTIFICADOR,
        REGRA_VERSAO,
        MERCADO,
        CRITERIOS,
        EVIDENCIA_HISTORICA,
        minimo_resultados=MINIMO_RESULTADOS,
        iniciado_em=iniciado_em,
    )


def main():
    banco = BancoMonitor(Path(__file__).parent / "monitor_packball.db")
    try:
        hipotese = registrar(banco.conexao, iniciado_em=datetime.now())
    finally:
        banco.fechar()
    print(json.dumps(hipotese, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
