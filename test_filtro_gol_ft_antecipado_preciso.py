import json
import unittest

from filtro_gol_ft_antecipado_preciso import (
    METODO,
    ROLLBACK,
    avaliar_filtro_gol_ft_antecipado,
)


class FiltroGolFtAntecipadoPrecisoTest(unittest.TestCase):
    @staticmethod
    def candidato(**alteracoes):
        candidato = {
            "mercado": "gol_ft",
            "odd": 1.60,
            "features": {
                "exploracao_sombra": {"versao": METODO},
                "gol_antecipado": {
                    "minuto": 55,
                    "evidencias_ao_vivo": [
                        "chutes_5min", "chute_no_gol"
                    ],
                },
                "gol_antecipado_2t": {
                    "confirmado": True,
                    "total_gols_amostra_faixa": 12,
                },
                "qualidade_dados": 80,
                "odds_cache": False,
                "idade_odds_segundos": 120,
                "chutes_no_gol": [2, 1],
                "chutes_no_gol_total": 3,
                "janelas": {
                    "5": {
                        "disponivel": True,
                        "resets_detectados": [],
                        "chutes": [1, 0],
                        "chutes_total": 1,
                    },
                },
            },
        }
        for chave, valor in alteracoes.items():
            if chave in {"odd", "mercado"}:
                candidato[chave] = valor
            elif chave == "features_json":
                candidato = {
                    "mercado": "gol_ft",
                    "odd": 1.60,
                    "features_json": valor,
                }
            else:
                candidato["features"][chave] = valor
        return candidato

    @staticmethod
    def avaliar(candidato):
        return avaliar_filtro_gol_ft_antecipado(
            candidato, {ROLLBACK: "1"}
        )

    def test_candidato_completo_e_aprovado(self):
        resultado = self.avaliar(self.candidato())

        self.assertTrue(resultado["aplicavel"])
        self.assertTrue(resultado["aprovada"])
        self.assertEqual(
            "criterios_precisos_confirmados", resultado["motivo"]
        )

    def test_limites_de_minuto_e_odd(self):
        self.assertTrue(
            self.avaliar(self.candidato(
                gol_antecipado={
                    "minuto": 46,
                    "evidencias_ao_vivo": ["a", "b"],
                },
                odd=1.40,
            ))["aprovada"]
        )
        self.assertTrue(
            self.avaliar(self.candidato(
                gol_antecipado={
                    "minuto": 60,
                    "evidencias_ao_vivo": ["a", "b"],
                },
                odd=1.899,
            ))["aprovada"]
        )
        self.assertFalse(
            self.avaliar(self.candidato(
                gol_antecipado={
                    "minuto": 61,
                    "evidencias_ao_vivo": ["a", "b"],
                },
            ))["aprovada"]
        )
        self.assertFalse(self.avaliar(self.candidato(odd=1.90))["aprovada"])

    def test_exige_qualidade_odd_fresca_e_nao_cache(self):
        self.assertEqual(
            "qualidade_dados_insuficiente",
            self.avaliar(self.candidato(qualidade_dados=79))["motivo"],
        )
        self.assertEqual(
            "odd_cache_ou_origem_incerta",
            self.avaliar(self.candidato(odds_cache=True))["motivo"],
        )
        self.assertEqual(
            "odd_desatualizada_ou_sem_idade",
            self.avaliar(
                self.candidato(idade_odds_segundos=120.1)
            )["motivo"],
        )

    def test_exige_historico_e_atividade_recente(self):
        self.assertEqual(
            "historico_faixa_nao_confirmado",
            self.avaliar(self.candidato(
                gol_antecipado_2t={
                    "confirmado": False,
                    "total_gols_amostra_faixa": 12,
                },
            ))["motivo"],
        )
        self.assertEqual(
            "historico_faixa_insuficiente",
            self.avaliar(self.candidato(
                gol_antecipado_2t={
                    "confirmado": True,
                    "total_gols_amostra_faixa": 11,
                },
            ))["motivo"],
        )
        janela = {
            "5": {
                "disponivel": True,
                "resets_detectados": [],
                "chutes": [0, 0],
                "chutes_total": 0,
            },
        }
        self.assertEqual(
            "atividade_recente_insuficiente",
            self.avaliar(self.candidato(janelas=janela))["motivo"],
        )

    def test_rejeita_contadores_inconsistentes(self):
        janela = {
            "5": {
                "disponivel": True,
                "resets_detectados": [],
                "chutes": [1, 1],
                "chutes_total": 1,
            },
        }
        self.assertEqual(
            "chutes_5min_inconsistentes",
            self.avaliar(self.candidato(janelas=janela))["motivo"],
        )
        self.assertEqual(
            "chutes_no_gol_inconsistentes",
            self.avaliar(self.candidato(
                chutes_no_gol=[2, 2],
                chutes_no_gol_total=3,
            ))["motivo"],
        )

    def test_aceita_features_json_e_rollback_nao_cria_veto(self):
        original = self.candidato()
        serializado = json.dumps(original["features"])
        self.assertTrue(
            self.avaliar(self.candidato(features_json=serializado))[
                "aprovada"
            ]
        )
        self.assertTrue(
            avaliar_filtro_gol_ft_antecipado(
                original, {ROLLBACK: "0"}
            )["aprovada"]
        )
        original["features"]["exploracao_sombra"]["versao"] = "outro"
        resultado = self.avaliar(original)
        self.assertFalse(resultado["aplicavel"])
        self.assertTrue(resultado["aprovada"])


if __name__ == "__main__":
    unittest.main()
