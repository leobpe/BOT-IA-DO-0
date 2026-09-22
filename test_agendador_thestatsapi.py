import unittest

from agendador_thestatsapi import (
    MAXIMO_JOGOS_PADRAO,
    planejar_coleta_thestatsapi,
)


def _par(numero, status="35 '"):
    url = f"https://packball.com/match/{numero}/live"
    return {
        "jogo": {"url": url, "status": status},
        "associacao": {"match_id": f"mt_{numero}"},
    }


def _consumo(restante_dia=100, usadas_minuto=0, provedor=30):
    return {
        "contador_saudavel": True,
        "restante_local_seguro": restante_dia,
        "limite_local_minuto": 25,
        "chamadas_ultimo_minuto": usadas_minuto,
        "provedor": {"restante": provedor},
    }


class AgendadorTheStatsAPITest(unittest.TestCase):
    def test_teto_padrao_growth_permite_dezessete_jogos(self):
        self.assertEqual(MAXIMO_JOGOS_PADRAO, 17)

    def test_quatro_jogos_recebem_stats_no_mesmo_ciclo(self):
        pares = [_par(numero) for numero in range(1, 5)]
        tarefas = [
            {"jogo": par["jogo"], "acionavel_fila_detalhada": True}
            for par in pares
        ]

        planos, resumo = planejar_coleta_thestatsapi(
            pares, tarefas, {}, _consumo(), maximo_jogos=6
        )

        self.assertEqual(len(planos), 4)
        self.assertTrue(all(plano.consultar_stats for plano in planos))
        self.assertEqual(resumo["jogos_na_lista_sem_detalhe"], 0)
        self.assertTrue(resumo["acompanha_lista_completa"])

    def test_odds_usam_somente_capacidade_apos_stats(self):
        pares = [_par(numero) for numero in range(1, 5)]
        tarefas = [
            {
                "jogo": par["jogo"],
                "acionavel_fila_detalhada": True,
                "em_foco": indice == 2,
            }
            for indice, par in enumerate(pares)
        ]
        consumo = _consumo(usadas_minuto=17, provedor=6)

        planos, resumo = planejar_coleta_thestatsapi(
            pares, tarefas, {}, consumo, maximo_jogos=6
        )

        self.assertEqual(resumo["capacidade_detalhes"], 6)
        self.assertEqual(resumo["stats_planejados"], 4)
        self.assertEqual(resumo["odds_planejadas"], 2)
        self.assertEqual(sum(p.consultar_odds for p in planos), 2)

    def test_sem_capacidade_nao_executa_detalhes(self):
        planos, resumo = planejar_coleta_thestatsapi(
            [_par(1)], [], {}, _consumo(restante_dia=0)
        )
        self.assertEqual(planos, [])
        self.assertEqual(resumo["estado"], "sem_capacidade")
        self.assertFalse(resumo["aplicacao_sinais"])

    def test_contador_inseguro_falha_fechado(self):
        consumo = _consumo()
        consumo["contador_saudavel"] = False
        planos, _ = planejar_coleta_thestatsapi([_par(1)], [], {}, consumo)
        self.assertEqual(planos, [])

    def test_rodizio_prioriza_menos_consultado(self):
        pares = [_par(1), _par(2), _par(3)]
        tarefas = [
            {"jogo": par["jogo"], "acionavel_fila_detalhada": True}
            for par in pares
        ]
        consumo = _consumo(usadas_minuto=21, provedor=2)
        contagens = {
            pares[0]["jogo"]["url"]: 5,
            pares[1]["jogo"]["url"]: 2,
            pares[2]["jogo"]["url"]: 0,
        }

        planos, _ = planejar_coleta_thestatsapi(
            pares,
            tarefas,
            {},
            consumo,
            contagens_stats=contagens,
        )

        self.assertEqual(len(planos), 2)
        self.assertEqual(
            [plano.par["associacao"]["match_id"] for plano in planos],
            ["mt_3", "mt_2"],
        )

    def test_match_id_invalido_e_ignorado(self):
        par = _par(1)
        par["associacao"]["match_id"] = "1"
        planos, resumo = planejar_coleta_thestatsapi(
            [par], [], {}, _consumo()
        )
        self.assertEqual(planos, [])
        self.assertEqual(resumo["jogos_pareados"], 0)


if __name__ == "__main__":
    unittest.main()
