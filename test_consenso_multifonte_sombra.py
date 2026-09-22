import unittest
import sqlite3
from datetime import datetime, timezone

from consenso_multifonte_sombra import (
    VERSAO_CONSENSO_MULTIFONTE_SOMBRA,
    estatisticas_do_consenso,
    isolar_candidatos_consenso,
    registrar_ou_validar_consenso_multifonte,
    validar_consenso_multifonte,
)


class ConsensoMultifonteSombraTest(unittest.TestCase):
    def setUp(self):
        self.agora = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)
        self.jogo = {
            "url": "https://packball.test/jogo-1",
            "placar": "1-0",
            "status": "62'",
        }
        self.fixture = {"goals": {"home": 1, "away": 0}}
        self.api = {
            "packball_url": self.jogo["url"],
            "coletado_em": "2026-08-20T14:59:40+00:00",
            "minuto": 62,
            "periodo": "2T",
            "orientacao": "direta",
            "chutes_mandante": 10,
            "chutes_visitante": 7,
            "chutes_gol_mandante": 4,
            "chutes_gol_visitante": 2,
            "escanteios_mandante": 5,
            "escanteios_visitante": 3,
            "completo": True,
        }
        self.ts = {
            "fonte": "thestatsapi",
            "packball_url": self.jogo["url"],
            "coletado_em": "2026-08-20T14:59:45+00:00",
            "placar": [1, 0],
            "minuto": 63,
            "periodo": "2T",
            "chutes_mandante": 11,
            "chutes_visitante": 7,
            "chutes_gol_mandante": 4,
            "chutes_gol_visitante": 3,
            "escanteios_mandante": 5,
            "escanteios_visitante": 3,
            "xg_mandante": 1.42,
            "xg_visitante": 0.61,
        }

    def test_consenso_valido_permanece_sem_autorizacao(self):
        resultado = validar_consenso_multifonte(
            self.jogo, self.fixture, self.api, self.ts, agora=self.agora
        )

        self.assertTrue(resultado["valido"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["telegram"])
        self.assertFalse(resultado["calibracao"])
        self.assertFalse(resultado["promocao_automatica"])

    def test_divergencia_de_placar_bloqueia_consenso(self):
        self.ts["placar"] = [1, 1]
        resultado = validar_consenso_multifonte(
            self.jogo, self.fixture, self.api, self.ts, agora=self.agora
        )
        self.assertFalse(resultado["valido"])
        self.assertEqual(resultado["motivo"], "placar_divergente")

    def test_divergencia_de_chutes_bloqueia_consenso(self):
        self.ts["chutes_mandante"] = 14
        resultado = validar_consenso_multifonte(
            self.jogo, self.fixture, self.api, self.ts, agora=self.agora
        )
        self.assertFalse(resultado["valido"])
        self.assertEqual(resultado["motivo"], "metricas_divergentes")
        self.assertIn("chutes", resultado["conflitos"])

    def test_estatisticas_nao_inventam_pressao(self):
        estatisticas = estatisticas_do_consenso(self.api, self.ts)
        self.assertEqual(estatisticas["Chutes"], "10 - 7")
        self.assertNotIn("Índice de pressão", estatisticas)
        self.assertEqual(estatisticas["xG TheStats"], "1.42 - 0.61")

    def test_aprovado_vira_somente_simulacao(self):
        diagnostico = validar_consenso_multifonte(
            self.jogo, self.fixture, self.api, self.ts, agora=self.agora
        )
        candidatos = isolar_candidatos_consenso(
            [{
                "mercado": "gol_ft",
                "linha": 1.5,
                "odd": 1.70,
                "status": "aprovado",
                "features": {},
                "motivos": [],
            }],
            diagnostico,
        )
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["status"], "simulacao")
        sombra = candidatos[0]["features"]["exploracao_sombra"]
        self.assertEqual(
            sombra["versao"], VERSAO_CONSENSO_MULTIFONTE_SOMBRA
        )
        self.assertFalse(sombra["telegram_oficial"])
        self.assertFalse(sombra["grupo_teste"])

    def test_rejeitado_nunca_e_promovido_para_sombra(self):
        self.assertEqual(isolar_candidatos_consenso(
            [{"mercado": "gol_ft", "status": "rejeitado"}], {}
        ), [])

    def test_definicao_e_ancorada_e_idempotente(self):
        conexao = sqlite3.connect(":memory:")
        try:
            conexao.execute(
                "CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT)"
            )
            primeira = registrar_ou_validar_consenso_multifonte(
                conexao, "2026-08-20T12:00:00"
            )
            segunda = registrar_ou_validar_consenso_multifonte(
                conexao, "2099-01-01T00:00:00"
            )
            self.assertEqual(primeira, segunda)
            self.assertEqual(primeira["minimo_resultados_futuros"], 70)
            self.assertFalse(primeira["promocao_automatica"])
        finally:
            conexao.close()


if __name__ == "__main__":
    unittest.main()
