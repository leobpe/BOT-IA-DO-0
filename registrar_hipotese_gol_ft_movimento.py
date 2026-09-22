import json
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from hipoteses_sombra import registrar_hipotese_composta_sombra


IDENTIFICADOR = "gol_ft_movimento_delta031_odd200_v1_20260808"
REGRA_VERSAO = "sinais-v6"
MERCADO = "gol_ft"
CRITERIOS = [
    {
        "feature": "movimento_gols.delta",
        "operador": "menor_igual",
        "limiar": 0.31,
    },
    {
        "feature": "movimento_gols.odd_atual",
        "operador": "menor_igual",
        "limiar": 2.0,
    },
]
EVIDENCIA_HISTORICA = {
    "amostra_total_independente": 276,
    "metodo": "desenvolvimento_cronologico_246_mais_validacao_final_30",
    "desenvolvimento": {
        "n_selecionado": 76,
        "greens": 51,
        "acerto": 0.671,
        "roi": 0.05,
        "fatias_temporais_positivas": 3,
        "fatias_temporais_observadas": 3,
    },
    "validacao_final_nao_usada_no_ajuste": {
        "n_selecionado": 11,
        "greens": 10,
        "acerto": 0.909,
        "roi": 0.424,
    },
    "busca_exploratoria_multiplos_cortes": True,
    "uso": "somente_geracao_de_hipotese",
    "observacao": (
        "A seleção histórica possui risco de múltiplos testes. Somente "
        "resultados posteriores ao registro podem confirmar a hipótese."
    ),
}
MINIMO_RESULTADOS = 30


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
