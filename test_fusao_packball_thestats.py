import unittest
from datetime import datetime, timedelta

from fusao_packball_thestats import (
    VERSAO_EXPERIMENTO_FUSAO,
    fundir_estatisticas_packball_thestats,
    marcar_candidatos_dependentes_fusao,
)


class FusaoPackBallTheStatsTest(unittest.TestCase):
    def setUp(self):
        self.agora = datetime.now().astimezone().replace(microsecond=0)
        self.jogo = {"url": "https://pb/j/1", "placar": "1-0", "status": "63 '"}
        self.ts = {
            "fonte": "thestatsapi", "packball_url": self.jogo["url"],
            "coletado_em": self.agora.isoformat(), "placar": [1, 0],
            "minuto": 62, "chutes_mandante": 9, "chutes_visitante": 6,
            "chutes_gol_mandante": 4, "chutes_gol_visitante": 2,
            "escanteios_mandante": 5, "escanteios_visitante": 3,
            "xg_mandante": 1.42, "xg_visitante": 0.61,
        }

    def test_completa_lacunas_sem_substituir_pressao(self):
        pb = {"Índice de pressão": "78 - 43", "Chutes": "9 - 6"}
        unido, diag = fundir_estatisticas_packball_thestats(
            self.jogo, pb, self.ts, self.agora
        )
        self.assertTrue(diag["valida"])
        self.assertEqual(unido["Índice de pressão"], "78 - 43")
        self.assertEqual(unido["Chutes no gol"], "4 - 2")
        self.assertEqual(diag["xg"], [1.42, 0.61])

    def test_divergencia_bloqueia_e_nao_substitui(self):
        pb = {"Chutes": "2 - 1", "Índice de pressão": "60 - 40"}
        unido, diag = fundir_estatisticas_packball_thestats(
            self.jogo, pb, self.ts, self.agora
        )
        self.assertFalse(diag["valida"])
        self.assertEqual(diag["motivo"], "metricas_divergentes")
        self.assertEqual(unido, pb)

    def test_placar_minuto_ou_frescor_divergente_falha_fechado(self):
        for alteracao in (
            {"placar": [0, 1]}, {"minuto": 55},
            {"coletado_em": (self.agora - timedelta(seconds=91)).isoformat()},
        ):
            ts = {**self.ts, **alteracao}
            unido, diag = fundir_estatisticas_packball_thestats(
                self.jogo, {}, ts, self.agora
            )
            self.assertFalse(diag["valida"])
            self.assertEqual(unido, {})

    def test_somente_aprovacao_dependente_vira_experimento(self):
        base = [{"mercado": "gol_ft", "linha": 1.5,
                 "regra_versao": "r1", "status": "rejeitado"}]
        novo = [{"mercado": "gol_ft", "linha": 1.5,
                 "regra_versao": "r1", "status": "aprovado",
                 "features": {}, "motivos": []}]
        diag = {"valida": True, "complementou": ["Chutes"],
                "conflitos": [], "xg": [1.2, .4]}
        marcar_candidatos_dependentes_fusao(novo, base, diag)
        self.assertEqual(novo[0]["status"], "simulacao")
        self.assertEqual(
            novo[0]["features"]["exploracao_sombra"]["versao"],
            VERSAO_EXPERIMENTO_FUSAO,
        )

    def test_aprovacao_dependente_autorizada_permanece_oficial(self):
        base = [{"mercado": "gol_ft", "linha": 1.5,
                 "regra_versao": "r1", "status": "rejeitado"}]
        novo = [{"mercado": "gol_ft", "linha": 1.5,
                 "regra_versao": "r1", "status": "aprovado",
                 "features": {}, "motivos": []}]
        diag = {"valida": True, "complementou": ["Odds Bet365"],
                "conflitos": [], "xg": [1.2, .4]}
        marcar_candidatos_dependentes_fusao(
            novo, base, diag, aplicacao_sinais=True
        )
        self.assertEqual(novo[0]["status"], "aprovado")
        self.assertNotIn("exploracao_sombra", novo[0]["features"])
        self.assertTrue(
            novo[0]["features"]["fusao_fontes"]["aplicacao_sinais"]
        )
        self.assertIn(
            "complemento_oficial_confirmado_packball_thestats",
            novo[0]["motivos"],
        )


if __name__ == "__main__":
    unittest.main()
