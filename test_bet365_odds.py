import json
import unittest
from datetime import datetime
from pathlib import Path

from bet365_odds import (
    auditar_observacoes_bet365,
    diagnosticar_mercado_escanteios_bet365,
    parear_partida_bet365,
    registrar_observacao_bet365,
    resumir_observacoes_bet365,
)
from banco import BancoMonitor


class Bet365OddsTest(unittest.TestCase):
    def test_pareia_somente_times_exatos_na_mesma_orientacao(self):
        eventos = [
            {
                "evento_id": "123",
                "mandante": "São José",
                "visitante": "União FC",
            }
        ]

        self.assertEqual(
            parear_partida_bet365(eventos, "Sao Jose", "Uniao FC")[
                "evento_id"
            ],
            "123",
        )
        self.assertIsNone(
            parear_partida_bet365(eventos, "União FC", "São José")
        )

    def test_rejeita_pareamento_duplicado(self):
        evento = {"mandante": "A", "visitante": "B"}
        self.assertIsNone(
            parear_partida_bet365([evento, dict(evento)], "A", "B")
        )

    def test_estrutura_linha_asiatica_total_com_dois_lados(self):
        mercado, motivo = diagnosticar_mercado_escanteios_bet365(
            "Total de Escanteios Asiáticos",
            [
                {"nome": "Mais de 9,5", "odd": "1,83"},
                {"nome": "Menos de 9,5", "odd": "1,90"},
            ],
            evento_id="EV123",
            url="https://www.bet365.bet.br/#/IP/EV123",
            coletado_em="2026-07-25T23:30:00",
        )

        self.assertIsNone(motivo)
        self.assertEqual(mercado["fonte"], "bet365_site")
        self.assertEqual(mercado["formato"], "duas_opcoes")
        self.assertEqual(
            mercado["ofertas"][0],
            {
                "linha": 9.5,
                "over": 1.83,
                "under": 1.9,
                "fonte": "bet365_site",
                "bookmaker": "Bet365",
            },
        )

    def test_estrutura_linha_de_primeiro_tempo_separadamente(self):
        mercado, motivo = diagnosticar_mercado_escanteios_bet365(
            "Escanteios Asiáticos - 1º Tempo",
            [
                {"lado": "over", "linha": 4.0, "odd": 1.75},
                {"lado": "under", "linha": 4.0, "odd": 2.0},
            ],
            periodo="1T",
        )

        self.assertIsNone(motivo)
        self.assertEqual(mercado["ofertas"], [])
        self.assertEqual(
            mercado["ofertas_periodos"]["1T"]["ofertas"][0]["linha"],
            4.0,
        )

    def test_estrutura_ofertas_observadas_na_tela_bet365(self):
        mercado_ft, motivo_ft = diagnosticar_mercado_escanteios_bet365(
            "Escanteios Asiáticos",
            [
                {"nome": "Mais de 8", "odd": "2.000"},
                {"nome": "Menos de 8", "odd": "1.800"},
            ],
        )
        mercado_1t, motivo_1t = diagnosticar_mercado_escanteios_bet365(
            "1º Tempo - Escanteios Asiáticos",
            [
                {"nome": "Mais de 3", "odd": "1.850"},
                {"nome": "Menos de 3", "odd": "1.950"},
            ],
            periodo="1T",
        )

        self.assertIsNone(motivo_ft)
        self.assertIsNone(motivo_1t)
        self.assertEqual(
            mercado_ft["ofertas"][0],
            {
                "linha": 8.0,
                "over": 2.0,
                "under": 1.8,
                "fonte": "bet365_site",
                "bookmaker": "Bet365",
            },
        )
        self.assertEqual(
            mercado_1t["ofertas_periodos"]["1T"]["ofertas"][0],
            {
                "linha": 3.0,
                "over": 1.85,
                "under": 1.95,
                "fonte": "bet365_site",
                "bookmaker": "Bet365",
            },
        )
        self.assertNotIn("2T", mercado_1t["ofertas_periodos"])

    def test_rejeita_exactly_mesmo_com_over_e_under(self):
        mercado, motivo = diagnosticar_mercado_escanteios_bet365(
            "Escanteios Exactly",
            [
                {"nome": "Over 9.5", "odd": 1.8},
                {"nome": "Under 9.5", "odd": 1.9},
            ],
        )

        self.assertIsNone(mercado)
        self.assertEqual(motivo, "mercado_nao_asiatico_de_duas_opcoes")

    def test_rejeita_linha_incompleta_ou_suspensa(self):
        mercado, motivo = diagnosticar_mercado_escanteios_bet365(
            "Total de Escanteios",
            [
                {"nome": "Mais de 8.5", "odd": 1.7},
                {
                    "nome": "Menos de 8.5",
                    "odd": 2.1,
                    "suspensa": True,
                },
            ],
        )

        self.assertIsNone(mercado)
        self.assertEqual(motivo, "over_under_incompleto_ou_suspenso")

    def test_rejeita_odd_linha_e_duplicidade_invalidas(self):
        for selecoes, motivo_esperado in (
            (
                [
                    {"nome": "Over 9.3", "odd": 1.8},
                    {"nome": "Under 9.3", "odd": 1.9},
                ],
                "over_under_incompleto_ou_suspenso",
            ),
            (
                [
                    {"nome": "Over 9.5", "odd": 1.8},
                    {"nome": "Over 9.5", "odd": 1.9},
                    {"nome": "Under 9.5", "odd": 2.0},
                ],
                "selecao_duplicada_ambigua",
            ),
        ):
            with self.subTest(motivo=motivo_esperado):
                mercado, motivo = diagnosticar_mercado_escanteios_bet365(
                    "Total de Escanteios Asiáticos", selecoes
                )
                self.assertIsNone(mercado)
                self.assertEqual(motivo, motivo_esperado)

    def test_persiste_oferta_valida_e_resume_telemetria(self):
        caminho = Path.cwd() / ".teste_bet365_observacoes.db"
        caminho.unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            mercado, motivo = diagnosticar_mercado_escanteios_bet365(
                "Escanteios Asiáticos - 2º Tempo",
                [
                    {"nome": "Over 5.0", "odd": 1.75},
                    {"nome": "Under 5.0", "odd": 2.0},
                ],
                periodo="2T",
                evento_id="EV456",
                url="https://www.bet365.bet.br/#/IP/EV456",
            )
            self.assertIsNone(motivo)
            registro_id = registrar_observacao_bet365(
                banco.conexao,
                "oferta_valida",
                evento_externo_id="EV456",
                mandante_observado="Time A",
                visitante_observado="Time B",
                periodo="2T",
                mercado=mercado["mercado"],
                oferta=mercado,
                url_origem=mercado["url_origem"],
                consultado_em="2026-07-25T20:10:00",
            )
            registrar_observacao_bet365(
                banco.conexao,
                "mercado_rejeitado",
                motivo="over_under_incompleto_ou_suspenso",
                consultado_em="2026-07-25T20:11:00",
            )

            linha = banco.conexao.execute(
                """
                SELECT * FROM observacoes_fontes_odds WHERE id=?
                """,
                (registro_id,),
            ).fetchone()
            resumo = resumir_observacoes_bet365(banco.conexao)

            self.assertEqual(linha["fonte"], "bet365_site")
            self.assertEqual(
                json.loads(linha["oferta_json"])["formato"],
                "duas_opcoes",
            )
            self.assertEqual(resumo["total"], 2)
            self.assertEqual(resumo["ofertas_validas"], 1)
            self.assertEqual(
                resumo["por_motivo"][
                    "over_under_incompleto_ou_suspenso"
                ],
                1,
            )
            self.assertFalse(resumo["ativa_no_monitor"])
            self.assertTrue(resumo["integridade"]["saudavel"])
            self.assertTrue(resumo["integridade"]["comprovada"])
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_nao_persiste_oferta_valida_sem_evidencia_compativel(self):
        caminho = Path.cwd() / ".teste_bet365_observacoes.db"
        caminho.unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            with self.assertRaises(ValueError):
                registrar_observacao_bet365(
                    banco.conexao,
                    "oferta_valida",
                    oferta={"fonte": "bet365_site", "formato": "duas_opcoes"},
                )
            with self.assertRaises(ValueError):
                registrar_observacao_bet365(
                    banco.conexao, "estado_inventado"
                )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_detecta_oferta_corrompida_e_payload_em_rejeicao(self):
        caminho = Path.cwd() / ".teste_bet365_integridade.db"
        caminho.unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            banco.conexao.execute(
                """
                INSERT INTO observacoes_fontes_odds (
                    fonte, consultado_em, estado, oferta_json
                ) VALUES
                    ('bet365_site', '2026-07-25T20:00:00',
                     'oferta_valida', '{'),
                    ('bet365_site', '2026-07-25T20:01:00',
                     'mercado_ausente', '{}')
                """
            )
            banco.conexao.commit()

            auditoria = auditar_observacoes_bet365(
                banco.conexao,
                agora=datetime(2026, 7, 25, 21, 0, 0),
            )

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual(auditoria["estado"], "inconsistente")
            self.assertEqual(auditoria["ofertas_validas_integras"], 0)
            self.assertEqual(auditoria["problemas"]["json_invalido"], 1)
            self.assertEqual(
                auditoria["problemas"]["oferta_valida_incompleta"], 1
            )
            self.assertEqual(
                auditoria["problemas"]["estado_negativo_com_oferta"], 1
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
