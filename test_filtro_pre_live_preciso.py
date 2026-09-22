import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from controle_pre_live_preciso import suspender
from filtro_pre_live_preciso import (
    avaliar_bilhete_pre_live_preciso,
    avaliar_criterios_bilhete_pre_live_preciso,
    filtrar_bilhetes_pre_live_precisos,
)


def bilhete(**alteracoes):
    base = {
        "tipo": "simples",
        "edge_conservador": 0.05,
        "pernas": [{
            "mercado": "chance_dupla",
            "selecao": "mandante_ou_empate",
            "qualidade_contexto": 90.0,
        }],
    }
    base.update(alteracoes)
    return base


class FiltroPreLivePrecisoTest(unittest.TestCase):
    def setUp(self):
        self.caminho_controle = Path.cwd() / (
            f".teste_filtro_pre_live_controle_{uuid4().hex}.json"
        )
        self.ambiente = patch.dict(
            os.environ, {"PRELIVE_FILTRO_PRECISO_ATIVO": "1"}, clear=False
        )
        self.ambiente.start()

    def tearDown(self):
        self.ambiente.stop()
        self.caminho_controle.unlink(missing_ok=True)

    def test_aprova_bilhete_com_qualidade_e_edge(self):
        self.assertEqual(
            avaliar_bilhete_pre_live_preciso(bilhete()),
            (True, "aprovado"),
        )

    def test_bloqueia_mercado_de_gol_do_time(self):
        item = bilhete(pernas=[{
            "mercado": "time_marca_gol",
            "selecao": "mandante|sim",
            "qualidade_contexto": 95.0,
        }])
        self.assertEqual(
            avaliar_bilhete_pre_live_preciso(item),
            (False, "mercado_time_sem_edge_estavel"),
        )

    def test_bloqueia_multipla_pura_de_under(self):
        item = bilhete(tipo="multipla_dois_jogos", pernas=[
            {
                "mercado": "total_gols",
                "selecao": "under_4.5",
                "qualidade_contexto": 90.0,
            },
            {
                "mercado": "total_gols",
                "selecao": "under_3.5",
                "qualidade_contexto": 90.0,
            },
        ])
        self.assertEqual(
            avaliar_bilhete_pre_live_preciso(item),
            (False, "multipla_under_sem_edge_estavel"),
        )

    def test_exige_qualidade_e_edge_conservador(self):
        qualidade_baixa = bilhete(pernas=[{
            "mercado": "chance_dupla",
            "selecao": "mandante_ou_empate",
            "qualidade_contexto": 84.9,
        }])
        edge_baixo = bilhete(edge_conservador=0.0399)
        self.assertEqual(
            avaliar_bilhete_pre_live_preciso(qualidade_baixa)[1],
            "qualidade_contexto_abaixo_85",
        )
        self.assertEqual(
            avaliar_bilhete_pre_live_preciso(edge_baixo)[1],
            "edge_conservador_abaixo_4pct",
        )

    def test_retorna_contagem_dos_motivos(self):
        aprovados, motivos = filtrar_bilhetes_pre_live_precisos([
            bilhete(),
            bilhete(edge_conservador=0.01),
        ])
        self.assertEqual(len(aprovados), 1)
        self.assertEqual(motivos, {"edge_conservador_abaixo_4pct": 1})

    def test_circuit_breaker_bloqueia_entrega_mas_nao_avaliacao_pura(self):
        suspender(
            "teste", "checkpoint_negativo",
            caminho=self.caminho_controle,
        )
        self.assertEqual(
            (True, "aprovado"),
            avaliar_criterios_bilhete_pre_live_preciso(bilhete()),
        )
        self.assertEqual(
            (False, "circuit_breaker_pre_live_preciso"),
            avaliar_bilhete_pre_live_preciso(
                bilhete(), caminho_controle=self.caminho_controle
            ),
        )


if __name__ == "__main__":
    unittest.main()
