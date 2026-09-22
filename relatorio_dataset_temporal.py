import json
import sqlite3
from pathlib import Path

from dataset_temporal import (
    avaliar_corte_sombra,
    avaliar_discriminacao_temporal,
    construir_dataset_temporal,
    dividir_cronologicamente,
)
from mercados import MERCADOS_CALIBRADOS
from versoes_regras import versao_regra_para_mercado


PASTA = Path(__file__).parent


def main():
    caminho = PASTA / "monitor_packball.db"
    conexao = sqlite3.connect(
        f"file:{caminho.resolve().as_posix()}?mode=ro", uri=True
    )
    conexao.row_factory = sqlite3.Row
    try:
        saida = {}
        for mercado in MERCADOS_CALIBRADOS:
            dataset = construir_dataset_temporal(
                conexao,
                mercado,
                regra_versao=versao_regra_para_mercado(mercado),
            )
            desenvolvimento, validacao = dividir_cronologicamente(
                dataset["registros"]
            )
            saida[mercado] = {
                chave: valor for chave, valor in dataset.items()
                if chave != "registros"
            }
            saida[mercado]["desenvolvimento"] = len(desenvolvimento)
            saida[mercado]["validacao_cronologica"] = len(validacao)
            saida[mercado]["avaliacao_sombra"] = (
                avaliar_discriminacao_temporal(dataset["registros"])
            )
            saida[mercado]["corte_sombra"] = avaliar_corte_sombra(
                dataset["registros"]
            )
    finally:
        conexao.close()
    print(json.dumps(saida, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
