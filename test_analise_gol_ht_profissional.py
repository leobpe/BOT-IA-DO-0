import json
import unittest

from analise_gol_ht_profissional import normalizar_linha, selecionar


class AnaliseGolHTProfissionalTest(unittest.TestCase):
    def _linha(self):
        return {
            "id": 1,
            "partida_id": 10,
            "criado_em": "2026-09-08T10:00:00",
            "odd": 1.75,
            "resultado": "green",
            "retorno_unidades": 0.75,
            "features_json": json.dumps({
                "minuto": 22,
                "qualidade_dados": 100,
                "chutes_no_gol_total": 4,
                "janelas": {
                    "5": {
                        "chutes_total": 2,
                        "pressao_pico": [72, 40],
                    },
                },
            }),
            "contexto_api_json": json.dumps({
                "estatisticas_ao_vivo": {
                    "times": {
                        "mandante": {"xg": 0.5},
                        "visitante": {"xg": 0.4},
                    },
                },
            }),
        }

    def test_normaliza_medidas_sem_inventar_dado(self):
        item = normalizar_linha(self._linha())
        self.assertEqual(2.0, item["chutes_5min"])
        self.assertEqual(72.0, item["pressao_pico_5min"])
        self.assertAlmostEqual(0.9, item["xg_total"])

    def test_grade_aplica_todos_os_limites_antes_de_selecionar(self):
        item = normalizar_linha(self._linha())
        perfil = ("teste", 24, 1.80, 2, 4, 70, 0.8)
        self.assertEqual([item], selecionar([item], perfil))
        bloqueado = {**item, "odd": 1.80}
        self.assertEqual([], selecionar([bloqueado], perfil))


if __name__ == "__main__":
    unittest.main()
