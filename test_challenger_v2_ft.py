import unittest

from banco import BancoMonitor
from challenger_v2_ft import (
    VERSAO_CHALLENGER_V2_FT,
    criar_challenger_v2_ft,
    registrar_ou_validar_challenger_v2_ft,
    resumir_challenger_v2_ft,
)


class ChallengerV2FtTest(unittest.TestCase):
    def controle(self, odd=1.65, pico=(60, 55)):
        return {
            "mercado": "gol_ft",
            "status": "simulacao",
            "odd": odd,
            "motivos": [],
            "features": {
                "janelas": {"5": {"pressao_pico": list(pico)}},
                "exploracao_sombra": {
                    "versao": (
                        "exploracao-atividade-gol-ft-v2-controle-futuro-v1"
                    ),
                    "telegram_oficial": False,
                    "aplicacao_automatica": False,
                },
            },
        }

    def test_aceita_limites_e_permanece_sombra(self):
        item = criar_challenger_v2_ft(self.controle())
        self.assertIsNotNone(item)
        self.assertEqual(item["status"], "simulacao")
        self.assertEqual(
            item["features"]["exploracao_sombra"]["versao"],
            VERSAO_CHALLENGER_V2_FT,
        )
        self.assertFalse(
            item["features"]["exploracao_sombra"]["telegram_oficial"]
        )

    def test_rejeita_odd_alta_ou_pressao_fraca(self):
        self.assertIsNone(criar_challenger_v2_ft(self.controle(odd=1.66)))
        self.assertIsNone(
            criar_challenger_v2_ft(self.controle(pico=(59.9, 58)))
        )

    def test_ancora_e_idempotente(self):
        banco = BancoMonitor(":memory:")
        try:
            primeira = registrar_ou_validar_challenger_v2_ft(
                banco.conexao, registrado_em=__import__("datetime").datetime(
                    2026, 8, 20, 12, 0
                )
            )
            segunda = registrar_ou_validar_challenger_v2_ft(
                banco.conexao, registrado_em=__import__("datetime").datetime(
                    2099, 1, 1
                )
            )
            self.assertEqual(
                primeira["definicao"]["registrado_em"],
                segunda["definicao"]["registrado_em"],
            )
        finally:
            banco.fechar()

    def test_contagem_persistida_da_versao_comeca_em_zero(self):
        banco = BancoMonitor(":memory:")
        try:
            self.assertEqual(
                banco.contar_exploracao_sombra_versao(
                    VERSAO_CHALLENGER_V2_FT
                ),
                0,
            )
        finally:
            banco.fechar()

    def test_resumo_vazio_respeita_coorte_fixa(self):
        banco = BancoMonitor(":memory:")
        try:
            registrar_ou_validar_challenger_v2_ft(banco.conexao)
            resumo = resumir_challenger_v2_ft(banco.conexao)
            self.assertEqual(resumo["candidatos_coorte"], 0)
            self.assertEqual(resumo["faltam_candidatos"], 75)
            self.assertEqual(resumo["faltam_validos"], 70)
            self.assertEqual(
                resumo["decisao_estatistica"],
                "aguardando_amostra_futura",
            )
            self.assertFalse(resumo["telegram"])
            self.assertFalse(resumo["aplicacao_automatica"])
        finally:
            banco.fechar()


if __name__ == "__main__":
    unittest.main()
