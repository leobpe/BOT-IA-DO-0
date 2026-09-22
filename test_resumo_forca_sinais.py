import copy
import json
import unittest
from unittest.mock import patch

from resumo_forca_sinais import resumo_forca_ao_vivo, resumo_forca_pre_live
from probabilidade_por_acertos import VERSAO as VERSAO_ACERTOS
from telegram_alertas import AlertasTelegram
from telegram_pre_live import mensagem_bilhete_pre_live, mensagem_lista_preliminar_pre_live


class ResumoForcaTest(unittest.TestCase):
    def setUp(self):
        self.candidato = {
            "mercado": "gol_ft", "linha": 1.5, "odd": 1.50,
            "pontuacao_tecnica": 100.0, "qualidade_dados": 90,
            "features": {
                "exploracao_sombra": {"versao": "gol-ft-capacidade-contextual-v2b"},
                "protecao_conversao_gols": {"ativa": True, "aprovada": True,
                                            "motivo": "apoio_da_linha_confirmado"},
                "protecao_tendencias_packball": {"ativa": True, "aprovada": True,
                                                "motivo": "tendencia_packball_confirmada"},
                "gol_capacidade_contextual_v2": {"evidencia_recente": {"forte": True},
                                                "probabilidade_estimada_nao_calibrada": 0.782},
            },
        }
        self.jogo = {"mandante": "Casa", "visitante": "Fora", "liga": "Liga",
                     "status": "55", "placar": "1-0"}
        perna = {
            "jogo": self.jogo, "mercado": "total_gols", "selecao": "over_1.5",
            "odd": 1.50, "qualidade_contexto": 90,
            "modelo": {
                "amostras": {"mandante_geral": 15, "visitante_geral": 15,
                             "mandante_mando": 7, "visitante_mando": 6},
                "jogadores": {k: {"escalacao_confirmada": True}
                              for k in ("mandante", "visitante")},
            },
        }
        self.bilhete = {"pernas": [perna], "odd_total": 1.50, "probabilidade_modelo": 0.732,
                        "criterios_oficiais_v11": {"atendidos": True}}

    def test_probabilidade_do_modelo_aparece_com_ressalva(self):
        texto = resumo_forca_ao_vivo(self.candidato)
        self.assertIn("Probabilidade estimada: 78,2%", texto)
        self.assertNotIn("Evidências", texto)
        self.assertIn("Modelo não calibrado", texto)
        self.assertNotIn("100", texto)

    def test_nota_alta_odd_baixa_e_probabilidade_bruta_nao_bastam(self):
        texto = resumo_forca_ao_vivo({"pontuacao_tecnica": 100, "odd": 1.10,
                                    "probabilidade_modelo": 0.99})
        self.assertIn("indisponível", texto)
        self.assertNotIn("99", texto)

    def test_fallback_nao_aumenta_percentual(self):
        self.candidato["features"]["protecao_tendencias_packball"]["motivo"] = "fallback_historico_metodo_confirmado"
        texto = resumo_forca_ao_vivo(self.candidato)
        self.assertIn("78,2%", texto)

    def test_modelo_de_outra_rota_nao_e_usado(self):
        self.candidato["features"]["exploracao_sombra"]["versao"] = "gol-ht-00-min20-over25-ou-btts-odd144-red-ok-v3"
        texto = resumo_forca_ao_vivo(self.candidato)
        self.assertIn("indisponível", texto)
        self.assertNotIn("78,2%", texto)

    def test_chute_recente_nao_vira_probabilidade(self):
        self.candidato["features"]["gol_capacidade_contextual_v2"] = {}
        self.candidato["features"]["janelas"] = {"5": {"disponivel": True, "chutes_total": 1}}
        texto = resumo_forca_ao_vivo(self.candidato)
        self.assertIn("indisponível", texto)

    def test_qualidade_nao_altera_probabilidade(self):
        self.candidato.pop("qualidade_dados")
        self.assertIn("78,2%", resumo_forca_ao_vivo(self.candidato))

    def test_calibracao_so_aparece_na_rota_calibrada(self):
        self.candidato["probabilidade_calibrada"] = 0.85
        self.assertNotIn("85", resumo_forca_ao_vivo(self.candidato))
        self.assertIn("85,0%", resumo_forca_ao_vivo(self.candidato, calibrado=True))

    def test_probabilidade_invalida_nao_aparece(self):
        for valor in (float("nan"), float("inf"), 2, -1, "ruim", True, 0, 1):
            self.candidato["probabilidade_calibrada"] = valor
            self.assertIn("indisponível", resumo_forca_ao_vivo(self.candidato, calibrado=True))

    def test_nao_muda_candidato_e_resultado_nao_muda_classificacao(self):
        original = copy.deepcopy(self.candidato)
        texto = resumo_forca_ao_vivo(self.candidato)
        self.assertEqual(original, self.candidato)
        self.candidato["resultado"] = "red"
        self.assertEqual(texto, resumo_forca_ao_vivo(self.candidato))

    def test_features_persistidas_mantem_classificacao(self):
        esperado = resumo_forca_ao_vivo(self.candidato)
        self.candidato["features_json"] = json.dumps(self.candidato.pop("features"))
        self.assertEqual(esperado, resumo_forca_ao_vivo(self.candidato))

    def test_mensagem_compacta_troca_nota_por_resumo(self):
        texto = AlertasTelegram._mensagem_teste(self.candidato, self.jogo)
        self.assertIn("78,2%", texto)
        self.assertIn("@ 1.50", texto)
        self.assertNotIn("Nota:", texto)
        self.assertIn("não calibrado", texto)
        self.assertIn("ANÁLISE EXPERIMENTAL — NÃO É ENTRADA", texto)

    def test_historico_com_odd_expoe_incerteza_e_nao_finge_edge(self):
        self.candidato["estimativa_historica_acertos"] = {
            "versao": VERSAO_ACERTOS,
            "amostra": 71,
            "greens": 48,
            "reds": 23,
            "probabilidade": 49 / 73,
            "intervalo_wilson95": [0.560609, 0.773429],
            "retorno_unidades_total": 3.55,
            "roi": 0.05,
            "odd_media_executada": 1.55,
            "intervalo_roi_95": [-0.10, 0.20],
            "dias_distintos": 35,
            "ligas_distintas": 8,
            "concentracao_maior_liga": 0.25,
            "intervalo_roi_95_agrupado_dia": [-0.12, 0.22],
            "roi_metade_antiga": 0.07,
            "roi_metade_recente": 0.03,
            "maior_sequencia_red": 4,
            "drawdown_maximo_unidades": 5.5,
            "criterios_vantagem_robusta": {
                "amostra_minima": True,
                "dias_minimos": True,
                "ic95_t_inferior_positivo": False,
                "ic95_agrupado_dia_inferior_positivo": False,
                "duas_metades_positivas": True,
            },
            "vantagem_historica_robusta": False,
            "estado_vantagem": "historico_inconclusivo",
        }

        texto = resumo_forca_ao_vivo(self.candidato)

        self.assertIn("Taxa histórica executável do método: 67,1%", texto)
        self.assertIn("Base Bet365: 48 greens / 23 reds", texto)
        self.assertIn("não é a chance deste jogo", texto)
        self.assertIn("ROI histórico executável (1 un./entrada): +5,0%", texto)
        self.assertIn("Retorno acumulado: +3,55 un. em 71 entradas", texto)
        self.assertIn("Odd média realmente executada: 1,55", texto)
        self.assertIn("IC95 do ROI: -10,0%–+20,0%", texto)
        self.assertIn("Robustez temporal: 35 dias / 8 ligas", texto)
        self.assertIn("IC95 do ROI agrupado por dia: -12,0%–+22,0%", texto)
        self.assertIn("metade antiga/recente): +7,0% / +3,0%", texto)
        self.assertIn("drawdown máximo 5,50 un.; maior sequência de reds 4", texto)
        self.assertIn("Equilíbrio da odd atual 1.50: 66,7%", texto)
        self.assertIn("Faixa de acerto observada de 95%: 56,1%–77,3%", texto)
        self.assertIn("Resultado financeiro inconclusivo", texto)

    def test_historico_sem_roi_executavel_nao_finge_vantagem(self):
        self.candidato["estimativa_historica_acertos"] = {
            "versao": VERSAO_ACERTOS,
            "amostra": 30,
            "greens": 25,
            "reds": 5,
            "probabilidade": 26 / 32,
            "intervalo_wilson95": [0.66, 0.93],
        }
        texto = resumo_forca_ao_vivo(self.candidato)
        self.assertNotIn("Taxa histórica executável", texto)
        self.assertNotIn("vantagem", texto.casefold())

    def test_expoe_referencia_binaria_sem_vig_da_mesma_fotografia(self):
        self.candidato.update({
            "odd_oposta": 2.10,
            "odd_par_sincronizado": True,
        })

        texto = resumo_forca_ao_vivo(self.candidato)

        self.assertIn(
            "Probabilidade implícita desta partida, sem margem: 58,3%",
            texto,
        )
        self.assertIn("Margem da casa no par: 14,3%", texto)
        self.assertIn("não é previsão nem garantia", texto)

    def test_nao_expoe_referencia_sem_prova_de_sincronia(self):
        self.candidato["odd_oposta"] = 2.10

        texto = resumo_forca_ao_vivo(self.candidato)

        self.assertNotIn("implícita desta partida", texto)
        self.assertNotIn("Margem da casa no par", texto)

    def test_expoe_referencia_tres_vias_de_proximo_gol(self):
        self.candidato.update({
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 1.80,
            "features": {
                "mercado_odds_sincronizado": True,
                "selecao_mercado": "casa",
                "odds_mercado_sincronizadas": {
                    "casa": 1.80,
                    "visitante": 3.60,
                    "sem_gol": 6.00,
                },
            },
        })

        texto = resumo_forca_ao_vivo(self.candidato)

        self.assertIn(
            "Probabilidade implícita desta partida, sem margem: 55,6%",
            texto,
        )
        self.assertIn("Margem da casa no mercado: 0,0%", texto)

    def test_pre_live_confirmada_completa(self):
        self.assertIn("73,2%", mensagem_bilhete_pre_live(self.bilhete))
        self.assertIn("não calibrado", mensagem_bilhete_pre_live(self.bilhete))

    def test_pre_live_pendente_preserva_aviso(self):
        self.bilhete["pernas"][0]["modelo"]["jogadores"] = {}
        texto = mensagem_lista_preliminar_pre_live({}, [self.bilhete])
        self.assertIn("Aguardando escalações", texto)
        self.assertIn("73,2% (não calibrada)", texto)
        self.assertNotIn("Evidências fortes", texto)

    def test_resumo_da_lista_e_curto(self):
        resumo = resumo_forca_pre_live(self.bilhete, compacto=True)
        self.assertEqual(len(resumo.splitlines()), 1)
        self.assertLess(len(resumo), 100)

    def test_multipla_usa_probabilidade_do_bilhete_inteiro(self):
        outra = copy.deepcopy(self.bilhete["pernas"][0])
        outra["modelo"]["amostras"]["visitante_mando"] = 1
        self.bilhete["pernas"].append(outra)
        outra["probabilidade_modelo"] = 0.999
        self.bilhete["pernas"][0]["probabilidade_modelo"] = 0.999
        self.assertIn("73,2%", resumo_forca_pre_live(self.bilhete))
        self.bilhete.pop("probabilidade_modelo")
        self.assertIn("indisponível", resumo_forca_pre_live(self.bilhete))

    def test_arredondamento_nao_promete_certeza(self):
        self.candidato["features"]["gol_capacidade_contextual_v2"]["probabilidade_estimada_nao_calibrada"] = 0.99999
        texto = resumo_forca_ao_vivo(self.candidato)
        self.assertIn(">99,9%", texto)
        self.assertNotIn("100,0%", texto)

    def test_poisson_v1_usa_estimativa_sem_chamar_de_calibracao(self):
        self.candidato["features"]["exploracao_sombra"]["versao"] = "gol-ft-capacidade-times-poisson-v1"
        self.candidato["features"]["gol_capacidade_times"] = {"modelo": {"probabilidade_mais_um_gol": 0.76}}
        texto = resumo_forca_ao_vivo(self.candidato)
        self.assertIn("76,0%", texto)
        self.assertIn("Modelo não calibrado", texto)

    def test_rollback_do_resumo(self):
        with patch.dict("os.environ", {"RESUMO_FORCA_SINAIS_ATIVO": "0"}):
            self.assertEqual("", resumo_forca_ao_vivo(self.candidato))
            self.assertEqual("", resumo_forca_pre_live(self.bilhete))


if __name__ == "__main__":
    unittest.main()
