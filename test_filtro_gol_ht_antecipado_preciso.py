import json
import unittest

from filtro_gol_ht_antecipado_preciso import (
    METODO,
    ROLLBACK,
    VERSAO,
    avaliar_filtro_gol_ht_antecipado,
)


class FiltroGolHtAntecipadoPrecisoTest(unittest.TestCase):
    def candidato(self, **alteracoes):
        candidato = {
            "mercado": "gol_ht",
            "odd": 1.80,
            "features": {
                "exploracao_sombra": {"versao": METODO},
                "gol_antecipado": {"minuto": 20},
                "gol_antecipado_ht": {
                    "confirmado": True,
                    "total_gols_amostra_faixa": 12,
                },
                "qualidade_dados": 100,
                "odds_cache": False,
                "idade_odds_segundos": 10,
                "chutes_no_gol": [1, 1],
                "chutes_no_gol_total": 2,
                "janelas": {"5": {
                    "disponivel": True,
                    "duracao_real_minutos": 5,
                    "resets_detectados": [],
                    "chutes": [1, 1],
                    "chutes_total": 2,
                }},
            },
        }
        for chave, valor in alteracoes.items():
            if chave == "minuto":
                candidato["features"]["gol_antecipado"]["minuto"] = valor
            elif chave == "gols_faixa":
                candidato["features"]["gol_antecipado_ht"][
                    "total_gols_amostra_faixa"
                ] = valor
            elif chave == "chutes_5":
                candidato["features"]["janelas"]["5"]["chutes"] = [
                    valor, 0
                ]
                candidato["features"]["janelas"]["5"][
                    "chutes_total"
                ] = valor
            elif chave == "sot":
                candidato["features"]["chutes_no_gol"] = [valor, 0]
                candidato["features"]["chutes_no_gol_total"] = valor
            elif chave in candidato:
                candidato[chave] = valor
            else:
                candidato["features"][chave] = valor
        return candidato

    def avaliar(self, candidato):
        return avaliar_filtro_gol_ht_antecipado(
            candidato, {ROLLBACK: "1"}
        )

    def test_aprova_somente_recorte_completo(self):
        resultado = self.avaliar(self.candidato())
        self.assertEqual(VERSAO, resultado["versao"])
        self.assertTrue(resultado["aprovada"])

    def test_janela_e_odd_possuem_limites_fechados(self):
        self.assertFalse(self.avaliar(self.candidato(minuto=9))["aprovada"])
        self.assertTrue(self.avaliar(self.candidato(minuto=10))["aprovada"])
        self.assertTrue(self.avaliar(self.candidato(minuto=28))["aprovada"])
        self.assertFalse(self.avaliar(self.candidato(minuto=29))["aprovada"])
        self.assertTrue(self.avaliar(self.candidato(odd=1.40))["aprovada"])
        self.assertTrue(self.avaliar(self.candidato(odd=2.00))["aprovada"])
        self.assertFalse(self.avaliar(self.candidato(odd=2.01))["aprovada"])

    def test_exige_atividade_e_historico_objetivos(self):
        self.assertFalse(
            self.avaliar(self.candidato(chutes_5=1))["aprovada"]
        )
        self.assertFalse(self.avaliar(self.candidato(sot=1))["aprovada"])
        self.assertFalse(
            self.avaliar(self.candidato(gols_faixa=11))["aprovada"]
        )

    def test_dado_inconsistente_e_odd_sem_frescor_falham_fechado(self):
        inconsistente = self.candidato()
        inconsistente["features"]["chutes_no_gol_total"] = 3
        self.assertEqual(
            "chutes_no_gol_inconsistentes",
            self.avaliar(inconsistente)["motivo"],
        )
        self.assertFalse(
            self.avaliar(self.candidato(odds_cache=True))["aprovada"]
        )
        self.assertFalse(
            self.avaliar(self.candidato(idade_odds_segundos=121))[
                "aprovada"
            ]
        )

    def test_aceita_features_json_e_nao_veta_outro_metodo(self):
        candidato = self.candidato()
        candidato["features_json"] = json.dumps(candidato.pop("features"))
        self.assertTrue(self.avaliar(candidato)["aprovada"])
        candidato = self.candidato()
        candidato["features"]["exploracao_sombra"]["versao"] = "outro"
        resultado = self.avaliar(candidato)
        self.assertFalse(resultado["aplicavel"])
        self.assertTrue(resultado["aprovada"])

    def test_rollback_desliga_veto_sem_promover(self):
        resultado = avaliar_filtro_gol_ht_antecipado(
            self.candidato(chutes_5=0), {ROLLBACK: "0"}
        )
        self.assertTrue(resultado["aprovada"])
        self.assertEqual("desativado", resultado["motivo"])
        self.assertFalse(resultado["promocao_automatica"])


if __name__ == "__main__":
    unittest.main()
