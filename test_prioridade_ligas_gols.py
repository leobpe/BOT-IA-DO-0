import unittest

from prioridade_ligas_gols import (
    extrair_liga_id,
    limite_inferior_wilson,
    pontuar_taxa_liga,
    priorizar_tarefas_por_ligas,
)


def _taxa(league_id=651, periodo="2t", amostra=120, over_05=0.82):
    return {
        "league_id": league_id,
        "pais": "Brazil",
        "liga": "Serie B",
        "liga_normalizada": "serie b",
        "temporada": "2026",
        "periodo": periodo,
        "jogos_realizados": amostra,
        "jogos_previstos": 384,
        "jogos_com_stats": amostra,
        "over_0_5": over_05,
        "over_1_5": 0.48,
        "over_2_5": 0.22,
        "coletado_em": "2026-09-01T10:00:00",
        "versao": "teste",
    }


class PrioridadeLigasGolsTest(unittest.TestCase):
    def test_extrai_mesmo_id_de_links_de_jogos_e_ligas(self):
        self.assertEqual(
            651,
            extrair_liga_id(
                "https://packball.com/pt/matches/651/league/brazil-serie-b/summary"
            ),
        )
        self.assertEqual(
            651,
            extrair_liga_id(
                "https://packball.com/pt/leagues/651/league/brazil-serie-b/summary"
            ),
        )

    def test_wilson_penaliza_amostra_curta(self):
        self.assertLess(
            limite_inferior_wilson(0.80, 20),
            limite_inferior_wilson(0.80, 200),
        )
        self.assertIsNone(pontuar_taxa_liga(_taxa(amostra=9)))

    def test_carga_alta_anota_periodo_correto_sem_aprovar_sinal(self):
        tarefas = [{
            "jogo": {
                "url": "jogo-1",
                "status": "62 '",
                "liga_url": (
                    "https://packball.com/pt/matches/651/league/"
                    "brazil-serie-b/summary"
                ),
                "liga_nome": "Serie B",
            },
            "em_foco": False,
        }]
        tarefas.extend({
            "jogo": {"url": f"outro-{indice}", "status": "60 '"},
            "em_foco": False,
        } for indice in range(14))

        anotadas, diagnostico = priorizar_tarefas_por_ligas(
            tarefas, [_taxa()], limiar_carga=15
        )

        self.assertTrue(diagnostico["ativa"])
        self.assertFalse(diagnostico["altera_aprovacao_sinal"])
        self.assertGreater(anotadas[0]["prioridade_liga_gols"], 0)
        self.assertEqual("2t", anotadas[0]["taxa_liga_gols"]["periodo"])

    def test_abaixo_do_limiar_preserva_fila_sem_score(self):
        tarefas = [{
            "jogo": {
                "url": "jogo-1",
                "status": "20 '",
                "liga_nome": "Serie B",
            }
        }]
        anotadas, diagnostico = priorizar_tarefas_por_ligas(
            tarefas, [_taxa(periodo="1t")], limiar_carga=15
        )
        self.assertFalse(diagnostico["ativa"])
        self.assertIsNone(anotadas[0]["prioridade_liga_gols"])


if __name__ == "__main__":
    unittest.main()

