import unittest
from unittest.mock import patch

from protecao_conversao_gols import aplicar_protecao_conversao_gols
from telegram_alertas import motivo_suspensao_simulacao


def _contexto(ft_25=0.60, ht_05=0.70, marcou=0.75, sofreu=0.70):
    linhas = {}
    capacidade = {}
    for lado in ("mandante", "visitante"):
        geral = {"jogos": 15, "jogos_ht": 15}
        mando = {"jogos": 7, "jogos_ht": 7}
        for item in (geral, mando):
            item.update({
                "over_0_5_taxa": 0.90,
                "over_1_5_taxa": 0.70,
                "over_2_5_taxa": ft_25,
                "ht_over_0_5_taxa": ht_05,
                "ht_over_1_5_taxa": 0.40,
            })
        linhas[lado] = {"geral": geral, "mando": mando}
        capacidade[lado] = {
            "mando": {
                "jogos": 7, "marcou_taxa": marcou, "sofreu_taxa": sofreu,
            }
        }
    return {
        "tendencia_linhas_gols_v1": {"recentes": linhas},
        "capacidade_times_v2": {"recentes": capacidade},
    }


def _candidato(mercado, linha, status="aprovado"):
    return {
        "mercado": mercado, "linha": linha, "status": status,
        "features": {"lado_dominante": "mandante"},
        "bloqueios": [], "motivos": [],
    }


class ProtecaoConversaoGolsTest(unittest.TestCase):
    def test_ft_usa_linha_que_ainda_precisa_bater(self):
        item = _candidato("gol_ft", 2.5)
        resumo = aplicar_protecao_conversao_gols([item], _contexto(ft_25=0.20))
        self.assertEqual("simulacao", item["status"])
        self.assertEqual(1, resumo["bloqueados"])
        self.assertEqual(
            "apoio_da_linha_fraco",
            item["features"]["protecao_conversao_gols"]["motivo"],
        )
        contrafactual = item["features"]["avaliacao_contrafactual"]
        self.assertEqual("protecao_conversao_gols", contrafactual["protecao"])
        self.assertFalse(contrafactual["telegram"])
        self.assertFalse(contrafactual["calibracao_oficial"])
        self.assertTrue(
            motivo_suspensao_simulacao(item).startswith(
                "protecao_conversao_gols:"
            )
        )

    def test_ht_usa_distribuicao_do_primeiro_tempo(self):
        item = _candidato("gol_ht", 0.5)
        aplicar_protecao_conversao_gols([item], _contexto(ht_05=0.30))
        self.assertEqual("simulacao", item["status"])

    def test_proximo_gol_exige_ataque_e_defesa_compativeis(self):
        item = _candidato("proximo_gol", "casa")
        aplicar_protecao_conversao_gols(
            [item], _contexto(marcou=0.40, sofreu=0.35)
        )
        self.assertEqual("simulacao", item["status"])

    def test_simulacao_e_registrada_mas_nao_enviada_quando_reprovada(self):
        item = _candidato("gol_ft", 2.5, "simulacao")
        item["features"]["exploracao_sombra"] = {"versao": "qualquer"}
        aplicar_protecao_conversao_gols([item], _contexto(ft_25=0.20))
        self.assertEqual("simulacao", item["status"])
        self.assertTrue(
            motivo_suspensao_simulacao(item).startswith(
                "protecao_conversao_gols:"
            )
        )

    def test_perfil_compativel_permanece_aprovado(self):
        itens = [
            _candidato("gol_ft", 2.5),
            _candidato("gol_ht", 0.5),
            _candidato("proximo_gol", "casa"),
        ]
        resumo = aplicar_protecao_conversao_gols(itens, _contexto())
        self.assertEqual(3, resumo["aprovados"])
        self.assertTrue(all(x["status"] == "aprovado" for x in itens))
        avaliacao = itens[0]["features"]["protecao_conversao_gols"]
        self.assertEqual([15, 15], avaliacao["amostras_gerais"])
        self.assertEqual([7, 7], avaliacao["amostras_mando"])

    def test_rollback_restaura_rejeicao_sem_contrafactual(self):
        item = _candidato("gol_ht", 0.5)
        with patch("contrafactual_protecoes.ATIVO", False):
            aplicar_protecao_conversao_gols(
                [item], _contexto(ht_05=0.30)
            )

        self.assertEqual("rejeitado", item["status"])
        self.assertNotIn("avaliacao_contrafactual", item["features"])


if __name__ == "__main__":
    unittest.main()
