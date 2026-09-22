"""Registra de forma idempotente o challenger prospectivo de Gol FT.

O registro apenas mede partidas futuras. Ele não altera a regra ativa nem
libera sinais automaticamente.
"""

import sqlite3
from pathlib import Path

from hipoteses_sombra import (
    registrar_hipotese_composta_sombra,
    registrar_hipotese_sombra,
)
from motor_sinais import VERSAO_REGRAS


BANCO = Path(__file__).with_name("monitor_packball.db")
IDENTIFICADOR = "gol_ft_odd_atual_min_166_v1_20260803"
IDENTIFICADOR_LIMITE_82 = "gol_ft_odd_166_minuto_max_82_v1_20260803"


def main():
    conexao = sqlite3.connect(BANCO)
    conexao.row_factory = sqlite3.Row
    try:
        hipotese = registrar_hipotese_sombra(
            conexao,
            identificador=IDENTIFICADOR,
            regra_versao=VERSAO_REGRAS,
            mercado="gol_ft",
            feature="movimento_gols.odd_atual",
            operador="maior_igual",
            limiar=1.66,
            minimo_resultados=30,
            evidencia_historica={
                "metodo": (
                    "desenvolvimento_cronologico_178_mais_"
                    "conferencia_secundaria_30"
                ),
                "amostra_total_independente": 208,
                "desenvolvimento": {
                    "n_selecionado": 53,
                    "roi": 0.050,
                    "acerto": 0.547,
                    "fatias_temporais_positivas": 2,
                    "fatias_temporais_observadas": 3,
                },
                "conferencia_secundaria": {
                    "n_selecionado": 7,
                    "roi": 0.064,
                    "acerto": 0.571,
                },
                "observacao": (
                    "Evidencia historica exploratoria; somente os resultados "
                    "posteriores ao registro podem confirmar o challenger."
                ),
            },
        )
        print(
            f"Challenger registrado: {hipotese['identificador']} | "
            f"início={hipotese['iniciado_em']} | "
            f"amostra futura={hipotese['minimo_resultados']}"
        )
        conservador = registrar_hipotese_composta_sombra(
            conexao,
            identificador=IDENTIFICADOR_LIMITE_82,
            regra_versao=VERSAO_REGRAS,
            mercado="gol_ft",
            criterios=[
                {
                    "feature": "movimento_gols.odd_atual",
                    "operador": "maior_igual",
                    "limiar": 1.66,
                },
                {
                    "feature": "minuto",
                    "operador": "menor_igual",
                    "limiar": 82,
                },
            ],
            minimo_resultados=30,
            evidencia_historica={
                "metodo": (
                    "desenvolvimento_cronologico_178_mais_"
                    "conferencia_secundaria_30"
                ),
                "amostra_total_independente": 208,
                "desenvolvimento": {
                    "n_selecionado": 50,
                    "roi": 0.0186,
                    "acerto": 0.54,
                },
                "conferencia_secundaria": {
                    "n_selecionado": 7,
                    "roi": 0.0643,
                    "acerto": 0.5714,
                },
                "total_selecionado": {
                    "n": 57,
                    "roi": 0.0242,
                    "acerto": 0.5439,
                },
                "observacao": (
                    "Versao conservadora solicitada para evitar entradas "
                    "depois do minuto 82; aplicacao automatica desligada."
                ),
            },
        )
        print(
            f"Challenger registrado: {conservador['identificador']} | "
            f"início={conservador['iniciado_em']} | "
            f"amostra futura={conservador['minimo_resultados']}"
        )
    finally:
        conexao.close()


if __name__ == "__main__":
    main()
