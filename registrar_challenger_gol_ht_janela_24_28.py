"""Pre-registra a janela 24-28 de Gol HT somente em sombra.

O historico documentado abaixo gera a hipotese, mas nao participa da sua
confirmacao. A avaliacao usa apenas primeiras decisoes aprovadas e liquidadas
depois de ``iniciado_em``, na linhagem v8b exata, contra o controle
contemporaneo da mesma linhagem.
"""

import json
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from hipoteses_sombra import registrar_hipotese_composta_sombra
from versoes_operacionais import VERSAO_GOL_HT_MAX_28


IDENTIFICADOR = "gol_ht_janela_24_28_v1_20260813"
REGRA_VERSAO = VERSAO_GOL_HT_MAX_28
MERCADO = "gol_ht"
CRITERIOS = [
    {
        "feature": "minuto",
        "operador": "maior_igual",
        "limiar": 24.0,
    },
    {
        "feature": "minuto",
        "operador": "menor_igual",
        "limiar": 28.0,
    },
]
MINIMO_RESULTADOS = 40
EVIDENCIA_HISTORICA = {
    "metodo": "primeira_decisao_aprovada_por_partida",
    "periodos_disjuntos": [
        {
            "regra_origem": "sinais-v4",
            "resultados_validos": 11,
            "greens": 9,
            "reds": 2,
            "lucro_unidades": 5.61,
            "roi": 0.51,
        },
        {
            "regra_origem": "sinais-v6",
            "resultados_validos": 6,
            "greens": 4,
            "reds": 2,
            "lucro_unidades": 1.11,
            "roi": 0.185,
        },
        {
            "regra_origem": VERSAO_GOL_HT_MAX_28,
            "resultados_validos": 13,
            "greens": 8,
            "reds": 5,
            "lucro_unidades": 3.01,
            "roi": 0.2315,
        },
    ],
    "corte_exploratorio": {
        "descricao": "minuto entre 24 e 28, inclusive",
        "resultados_validos": 30,
        "greens": 21,
        "reds": 9,
        "lucro_unidades": 9.73,
        "roi": 0.3243,
    },
    "controle_excluido": {
        "descricao": "minuto anterior a 24 nas mesmas bases historicas",
        "resultados_validos": 55,
        "greens": 26,
        "reds": 29,
        "lucro_unidades": -11.78,
        "roi": -0.2142,
    },
    "busca_exploratoria_multiplos_cortes": True,
    "uso": "somente_geracao_de_hipotese",
    "criterio_confirmacao_futura": {
        "roi_selecionada_maior_que_zero": True,
        "limite_inferior_ic95_delta_roi_maior_que_zero": True,
        "controle_contemporaneo": True,
    },
    "observacao": (
        "Os numeros historicos nao entram na confirmacao. O corte permanece "
        "sem Telegram e sem promocao automatica; somente resultados futuros "
        "posteriores a ancora podem confirma-lo."
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
