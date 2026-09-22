import unittest

from analisar_erros_gol_ft import (
    _analisar_competicoes,
    auditar_sobreajuste,
    _controle_multiplas_comparacoes,
    _controle_multiplas_comparacoes_compostos,
    _feature_modelavel,
    _metricas,
    _teste_roi_positivo,
)


class AnaliseErrosGolFTTest(unittest.TestCase):
    def test_identificadores_nao_entram_na_pesquisa_de_cortes(self):
        self.assertFalse(_feature_modelavel("contexto.fixture_id"))
        self.assertFalse(
            _feature_modelavel("contexto.times.mandante.time_id")
        )
        self.assertFalse(
            _feature_modelavel(
                "contexto.estatisticas_temporada.mandante.liga_id"
            )
        )
        self.assertTrue(_feature_modelavel("movimento_gols.odd_atual"))

    def test_competicao_combina_pais_e_liga(self):
        desenvolvimento = [
            {
                "pais": "A", "liga": "primeira", "resultado": "green",
                "retorno_unidades": 0.8,
            }
            for _ in range(5)
        ] + [
            {
                "pais": "B", "liga": "primeira", "resultado": "red",
                "retorno_unidades": -1,
            }
            for _ in range(5)
        ]
        linhas = _analisar_competicoes(desenvolvimento, [])
        self.assertEqual(len(linhas), 2)
        self.assertEqual({item["pais"] for item in linhas}, {"A", "B"})
        self.assertGreater(_metricas(desenvolvimento[:5])[2], 0)
        self.assertLess(_metricas(desenvolvimento[5:])[2], 0)

    def test_teste_roi_distingue_retorno_positivo_constante(self):
        itens = [
            {"resultado": "green", "retorno_unidades": 0.7}
            for _ in range(30)
        ]
        teste = _teste_roi_positivo(itens)
        self.assertEqual(teste["n"], 30)
        self.assertAlmostEqual(teste["roi"], 0.7)
        self.assertEqual(teste["p_unilateral"], 0.0)
        self.assertGreater(teste["limite_inferior_95"], 0)

    def test_correcao_nunca_melhora_p_nominal(self):
        itens = []
        for indice in range(40):
            itens.append({
                "resultado": "green" if indice % 2 == 0 else "red",
                "retorno_unidades": 0.7 if indice % 2 == 0 else -1.0,
                "features": {"pressao": float(indice)},
            })
        candidatos = [
            {
                "chave": "pressao", "operador": ">=", "corte": corte,
                "n_dev": 40, "acerto_dev": 0.5, "roi_dev": -0.15,
            }
            for corte in (0.0, 5.0, 10.0)
        ]
        controle = _controle_multiplas_comparacoes(itens, candidatos)
        self.assertEqual(controle["total_testes"], 3)
        self.assertEqual(controle["aprovados_bonferroni"], 0)
        for item in controle["avaliacoes"]:
            self.assertGreaterEqual(
                item["p_bonferroni"], item["p_unilateral"]
            )
            self.assertGreaterEqual(item["q_bh"], item["p_unilateral"])

    def test_auditoria_curta_exige_validacao_prospectiva(self):
        itens = [
            {
                "resultado": "green", "retorno_unidades": 0.7,
                "features": {},
            }
            for _ in range(20)
        ]
        resultado = auditar_sobreajuste(itens=itens)
        self.assertEqual(resultado["estado"], "amostra_insuficiente")
        self.assertFalse(resultado["promocao_retroativa_permitida"])
        self.assertTrue(resultado["exige_validacao_prospectiva"])

    def test_combinacoes_entram_na_mesma_familia_de_testes(self):
        itens = []
        for indice in range(120):
            green = indice % 3 != 0
            itens.append({
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.7 if green else -1.0,
                "features": {
                    "pressao": float(indice % 20),
                    "chutes": float((indice * 3) % 17),
                    "xg": float((indice * 7) % 13) / 10,
                },
            })

        controle = _controle_multiplas_comparacoes_compostos(itens)

        self.assertGreater(controle["total_simples"], 0)
        self.assertGreater(controle["total_compostos"], 0)
        self.assertEqual(
            controle["total_familia"],
            controle["total_simples"] + controle["total_compostos"],
        )
        for item in controle["avaliacoes_compostas"]:
            self.assertGreaterEqual(
                item["p_bonferroni"], item["p_unilateral"]
            )
            self.assertGreaterEqual(item["q_bh"], item["p_unilateral"])


if __name__ == "__main__":
    unittest.main()
