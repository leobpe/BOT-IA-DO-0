import copy
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from test_seletor_pre_live import contexto_completo


def carregar(perfil):
    with patch.dict(
        os.environ, {"PRELIVE_PERFIL_SELECAO": perfil}, clear=True
    ):
        spec = importlib.util.spec_from_file_location(
            "seletor_isolado_" + perfil, Path(__file__).with_name("seletor_pre_live.py")
        )
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo


def avaliacao(fixture=1, odd=1.50, probabilidade=0.90, score=5, confirmada=True):
    perna = {
        "fixture_id": fixture, "bookmaker_id": 7, "bookmaker": "Casa A",
        "mercado": "total_gols", "selecao": "over_1.5", "odd": odd,
        "probabilidade_modelo": probabilidade,
        "edge_modelo": round(probabilidade - 1 / odd, 4),
        "probabilidade_conservadora": 0.60, "edge_conservador": -0.10,
        "score_valor": score, "qualidade_contexto": 83.0,
        "modelo": {"jogadores": {
            lado: {"escalacao_confirmada": confirmada}
            for lado in ("mandante", "visitante")
        }},
    }
    return {"jogo": {"fixture_id": fixture}, "avaliacao": {"elegiveis": [perna]}}


class RetornoPreLiveDia30Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legado = carregar("dia30_v7")
        cls.atual = carregar("v11")

    def test_perfil_e_linhagem_separados_sem_rotular_como_v7_original(self):
        self.assertTrue(self.legado.RETORNO_DIA30)
        self.assertEqual("seletor-pre-live-retorno-dia30-odd150-v12", self.legado.VERSAO)
        self.assertNotEqual(self.legado.LINHAGEM, self.atual.LINHAGEM)
        self.assertEqual("58032183ddd41b72b4bdd0a43a8edd599ad9e84d9ea4ae5e10e2ff7193135d41", self.atual.LINHAGEM)
        with self.assertRaises(ValueError):
            carregar("perfil_inexistente")

    def test_ranking_volta_a_probabilidade_sem_corte_relativo_de_score(self):
        entrada = [avaliacao(1, probabilidade=0.95, score=1), avaliacao(2, probabilidade=0.85, score=10)]
        antes = copy.deepcopy(entrada)
        bilhetes = self.legado.montar_bilhetes_pre_live(entrada)
        self.assertEqual([1, 2], [b["pernas"][0]["fixture_id"] for b in bilhetes])
        self.assertEqual(antes, entrada)
        self.assertEqual(1, len(self.legado.montar_bilhetes_pre_live(entrada, maximo=1)))
        self.assertEqual([], self.legado.montar_bilhetes_pre_live(entrada, maximo=0))

    def test_odd_minima_150_preservada(self):
        for odd, quantidade in ((1.45, 0), (1.49, 0), (1.50, 1), (1.60, 1)):
            with self.subTest(odd=odd):
                self.assertEqual(quantidade, len(self.legado.montar_bilhetes_pre_live([avaliacao(odd=odd)])))

    def test_consenso_passa_a_diagnostico_sem_veto_nem_restricao_de_casa(self):
        ofertas = [{
            "fixture_id": 10, "bookmaker_id": indice, "bookmaker": "Casa " + str(indice),
            "mercado": "chance_dupla", "selecao": "mandante_ou_empate",
            "grupo_precificacao": "chance_dupla", "odd": odd,
            "probabilidade_mercado_sem_margem": 0.60, "fonte": "teste",
        } for indice, odd in ((1, 1.55), (2, 1.60))]
        resultado = self.legado.avaliar_ofertas_pre_live(copy.deepcopy(ofertas), contexto_completo(), qualidade=90)
        self.assertEqual(2, len(resultado["elegiveis"]))
        self.assertTrue(all(i["consenso_disponivel"] for i in resultado["elegiveis"]))
        self.assertTrue(all(i["divergencia_modelo_consenso"] > 0.12 for i in resultado["elegiveis"]))
        atual = self.atual.avaliar_ofertas_pre_live(copy.deepcopy(ofertas), contexto_completo(), qualidade=90)
        self.assertEqual([], atual["elegiveis"])

    def test_qualidade_e_historico_ainda_obrigatorios(self):
        oferta = {"fixture_id": 10, "bookmaker_id": 7, "bookmaker": "A", "mercado": "chance_dupla",
                  "selecao": "mandante_ou_empate", "grupo_precificacao": "chance_dupla", "odd": 1.5}
        for contexto, qualidade in (({}, 90), (contexto_completo(), 69)):
            self.assertEqual([], self.legado.avaliar_ofertas_pre_live([dict(oferta)], contexto, qualidade)["elegiveis"])

    def test_multipla_confirmada_volta_a_ficar_apta_sem_veto_v11(self):
        entrada = [avaliacao(1, odd=1.23), avaliacao(2, odd=1.23)]
        bilhetes = self.legado.montar_bilhetes_pre_live(entrada, aplicacao_automatica=True)
        self.assertEqual(1, len(bilhetes))
        self.assertEqual("multipla_dois_jogos", bilhetes[0]["tipo"])
        self.assertEqual("apto_envio_automatico", bilhetes[0]["estado"])
        self.assertTrue(bilhetes[0]["telegram"])
        self.assertEqual("retorno-dia30-v7-odd150", bilhetes[0]["politica_oficial"])
        self.assertEqual([], self.atual.montar_bilhetes_pre_live(entrada, aplicacao_automatica=True))

    def test_tripla_com_jogos_diferentes_e_mesma_casa(self):
        entrada = [avaliacao(i, odd=1.15, probabilidade=0.94) for i in (1, 2, 3)]
        bilhetes = self.legado.montar_bilhetes_pre_live(entrada, aplicacao_automatica=True)
        self.assertEqual(1, len(bilhetes))
        self.assertEqual("multipla_tres_jogos", bilhetes[0]["tipo"])
        self.assertAlmostEqual(1.5209, bilhetes[0]["odd_total"])
        self.assertTrue(bilhetes[0]["telegram"])
        entrada[2]["avaliacao"]["elegiveis"][0]["bookmaker_id"] = 9
        self.assertEqual([], self.legado.montar_bilhetes_pre_live(entrada))

    def test_sem_escalacao_nao_finge_confirmacao(self):
        bilhete = self.legado.montar_bilhetes_pre_live([avaliacao(confirmada=False)], aplicacao_automatica=True)[0]
        self.assertEqual("preliminar_aguardando_escalacao", bilhete["estado"])
        self.assertFalse(bilhete["telegram"])
        self.assertFalse(bilhete["criterios_oficiais_v11"]["escalacoes_confirmadas"])

    def test_faixa_estendida_e_correlacao_continuam_protegidas(self):
        self.assertEqual([], self.legado.montar_bilhetes_pre_live([avaliacao(odd=1.65)]))
        duplicadas = [avaliacao(1, odd=1.23), avaliacao(1, odd=1.23)]
        self.assertEqual([], self.legado.montar_bilhetes_pre_live(duplicadas))

    def test_revalidacao_usa_perfil_sem_reescrever_identidade_publicada(self):
        original = self.legado.montar_bilhetes_pre_live([avaliacao(confirmada=False)])[0]
        original["versao"] = "versao-original"
        original["linhagem_sha256"] = "linhagem-original"
        novo = self.legado.revalidar_bilhetes_publicados_pre_live([original], [avaliacao()], aplicacao_automatica=True)
        self.assertEqual(1, len(novo))
        self.assertEqual("versao-original", novo[0]["versao"])
        self.assertEqual("linhagem-original", novo[0]["linhagem_sha256"])
        self.assertEqual("apto_envio_automatico", novo[0]["estado"])
        self.assertTrue(novo[0]["revalidado_sem_republicar"])


if __name__ == "__main__":
    unittest.main()
