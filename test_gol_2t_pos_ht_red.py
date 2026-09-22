import unittest

from gol_2t_pos_ht_red import gerar_gol_2t_pos_ht_red


def candidato_base(odd=1.44, linha=0.5):
    return {
        "mercado": "gol_ft",
        "linha": linha,
        "odd": odd,
        "status": "aprovado",
        "bloqueios": [],
        "pontuacao_tecnica": 72.0,
        "probabilidade_calibrada": None,
        "features": {
            "janelas": {"5": {
                "chutes_total": 2.0,
                "pressao_pico": [70.0, 45.0],
            }},
            "chutes_no_gol_total": 1.0,
            "aceleracao_5_vs_5": {"chutes": [1.0, 0.0]},
        },
    }


class Gol2TPosHTRedTest(unittest.TestCase):
    def setUp(self):
        self.jogo = {"status": "52 '", "placar": "0-0"}
        self.qualidade = {"pontuacao": 90.0, "divergencia_critica": False}
        self.tendencia = {
            "identificada": True,
            "resultado": "red",
            "entrega_teste": True,
            "ja_registrado": False,
            "sinal_id": 10,
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "pontuacao_tecnica": 84.0,
        }

    def test_gera_somente_challenger_sem_telegram(self):
        itens = gerar_gol_2t_pos_ht_red(
            self.jogo, [candidato_base()], self.qualidade, self.tendencia
        )
        self.assertEqual(1, len(itens))
        item = itens[0]
        self.assertEqual("simulacao", item["status"])
        self.assertFalse(item["features"]["exploracao_sombra"]["telegram_oficial"])
        self.assertEqual(
            10, item["features"]["gol_2t_pos_ht_red"]["sinal_ht_origem_id"]
        )

    def test_rejeita_odd_abaixo_de_144(self):
        self.assertEqual([], gerar_gol_2t_pos_ht_red(
            self.jogo, [candidato_base(1.43)], self.qualidade, self.tendencia
        ))

    def test_rejeita_fora_da_janela(self):
        self.jogo["status"] = "66 '"
        self.assertEqual([], gerar_gol_2t_pos_ht_red(
            self.jogo, [candidato_base()], self.qualidade, self.tendencia
        ))

    def test_rejeita_sem_continuidade_live(self):
        base = candidato_base()
        base["features"]["janelas"]["5"] = {
            "chutes_total": 0.0, "pressao_pico": [40.0, 35.0]
        }
        base["features"]["chutes_no_gol_total"] = 0.0
        base["features"]["aceleracao_5_vs_5"] = {"chutes": [0.0, 0.0]}
        self.assertEqual([], gerar_gol_2t_pos_ht_red(
            self.jogo, [base], self.qualidade, self.tendencia
        ))

    def test_rejeita_quando_ja_foi_registrado(self):
        self.tendencia["ja_registrado"] = True
        self.assertEqual([], gerar_gol_2t_pos_ht_red(
            self.jogo, [candidato_base()], self.qualidade, self.tendencia
        ))


if __name__ == "__main__":
    unittest.main()
