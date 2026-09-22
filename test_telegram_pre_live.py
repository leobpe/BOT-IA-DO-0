import shutil
import os
import unittest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from controle_pre_live_preciso import suspender
from repositorio_pre_live import RepositorioPreLive
from telegram_pre_live import (
    editar_resultados_listas_pre_live,
    editar_resultados_pre_live,
    enviar_confirmados_pre_live,
    mensagem_bilhete_pre_live,
    mensagem_lista_preliminar_com_resultados,
    mensagem_lista_preliminar_pre_live,
    publicar_lista_preliminar_pre_live,
)


class TelegramPreLiveTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / f".teste_telegram_pre_live_{uuid4().hex}"
        self.pasta.mkdir()
        self.repo = RepositorioPreLive(self.pasta / "pre_live.db")
        self.bilhete = {
            "tipo": "simples",
            "bookmaker": "Bet365",
            "odd_total": 1.50,
            "probabilidade_modelo": 0.80,
            "edge_modelo": 0.13,
            "estado": "apto_sombra_confirmado",
            "versao": "teste-v1",
            "linhagem_sha256": "linhagem",
            "pernas": [{
                "fixture_id": 10,
                "jogo": {
                    "mandante": "Casa",
                    "visitante": "Fora",
                    "liga": "Liga",
                    "inicio": "2026-08-27T14:30:00-04:00",
                },
                "mercado": "chance_dupla",
                "selecao": "mandante_ou_empate",
                "odd": 1.50,
                "bookmaker": "Bet365",
                "qualidade_contexto": 90.0,
            }],
        }

    def tearDown(self):
        self.repo.fechar()
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_mensagem_compacta_contem_dados_essenciais(self):
        mensagem = mensagem_bilhete_pre_live(self.bilhete)
        self.assertIn("Casa x Fora", mensagem)
        self.assertIn("Chance dupla", mensagem)
        self.assertIn("Odd final: 1.50", mensagem)
        self.assertNotIn("probabilidade_modelo", mensagem)

    def test_lista_preliminar_resume_top_e_elencos_pendentes(self):
        resumo = {
            "data_alvo": "2026-08-27",
            "jogos_calendario": 134,
            "jogos_com_odds_utilizaveis": 99,
            "jogos_analisados": 60,
            "candidatos_elegiveis": 83,
            "cobertura_analise": 0.7229,
            "bilhetes": 20,
        }
        mensagem = mensagem_lista_preliminar_pre_live(
            resumo, [self.bilhete], limite=10
        )
        self.assertIn("PRÉ-LIVE — MELHORES DO DIA", mensagem)
        self.assertIn("134 jogos", mensagem)
        self.assertIn("Casa x Fora", mensagem)
        self.assertIn("🎯 Chance dupla: casa ou empate", mensagem)
        self.assertIn("📈 Odd 1.50 | Bet365", mensagem)
        self.assertIn("Odd final: 1.50", mensagem)
        self.assertIn("Aguardando escalações e contexto", mensagem)
        self.assertIn("Escalações confirmadas: 0/1", mensagem)
        self.assertIn("Confirmadas agora: 0/1", mensagem)
        self.assertIn("permanecem visíveis aguardando confirmação", mensagem)
        self.assertNotIn("publicadas separadamente", mensagem)

    def test_lista_preliminar_envia_uma_vez_por_horario_sem_editar(self):
        resumo = {
            "data_alvo": "2026-08-27",
            "slot_publicacao": "09:00",
            "jogos_calendario": 134,
            "jogos_com_odds_utilizaveis": 99,
            "jogos_analisados": 60,
            "candidatos_elegiveis": 83,
            "cobertura_analise": 0.7229,
            "bilhetes": 20,
        }
        chamadas = []

        def transporte(url, dados):
            chamadas.append((url, dados))
            return {
                "ok": True,
                "result": {
                    "message_id": 90 + len(chamadas),
                    "chat": {"id": -1002},
                },
            }

        bilhete_novo = deepcopy(self.bilhete)
        bilhete_novo["pernas"][0]["fixture_id"] = 11
        bilhete_novo["pernas"][0]["jogo"]["mandante"] = "Nova Casa"
        self.repo.registrar_bilhetes(
            [self.bilhete, bilhete_novo], "2026-08-27"
        )

        primeiro = publicar_lista_preliminar_pre_live(
            self.repo, resumo, [self.bilhete], "token", "-1002",
            transporte=transporte,
        )
        repetido = publicar_lista_preliminar_pre_live(
            self.repo, resumo, [self.bilhete], "token", "-1002",
            transporte=transporte,
        )
        resumo["jogos_calendario"] = 135
        mesmo_horario = publicar_lista_preliminar_pre_live(
            self.repo, resumo, [self.bilhete], "token", "-1002",
            transporte=transporte,
        )
        resumo["slot_publicacao"] = "12:00"
        proximo_horario = publicar_lista_preliminar_pre_live(
            self.repo, resumo, [self.bilhete, bilhete_novo], "token", "-1002",
            transporte=transporte,
        )

        self.assertEqual("enviada", primeiro["estado"])
        self.assertEqual("ja_enviada_no_horario", repetido["estado"])
        self.assertEqual("ja_enviada_no_horario", mesmo_horario["estado"])
        self.assertEqual("enviada", proximo_horario["estado"])
        self.assertEqual(1, proximo_horario["itens"])
        self.assertEqual(1, proximo_horario["ignorados_repetidos"])
        self.assertEqual(2, len(chamadas))
        self.assertIn("sendMessage", chamadas[0][0])
        self.assertIn("sendMessage", chamadas[1][0])
        self.assertNotIn("⚽ Casa x Fora\n", chamadas[1][1]["text"])
        self.assertIn("Nova Casa x Fora", chamadas[1][1]["text"])

        resumo["slot_publicacao"] = "15:00"
        sem_novos = publicar_lista_preliminar_pre_live(
            self.repo, resumo, [self.bilhete, bilhete_novo], "token", "-1002",
            transporte=transporte,
        )
        self.assertEqual("sem_jogos_novos_no_dia", sem_novos["estado"])
        self.assertEqual(2, len(chamadas))

    def test_lista_so_e_editada_quando_surje_resultado(self):
        self.repo.registrar_bilhetes([self.bilhete], "2026-08-27")
        resumo = {
            "data_alvo": "2026-08-27",
            "slot_publicacao": "09:00",
            "jogos_calendario": 10,
            "jogos_com_odds_utilizaveis": 8,
            "jogos_analisados": 5,
            "candidatos_elegiveis": 4,
            "cobertura_analise": 1.0,
            "bilhetes": 1,
        }

        def enviar(_url, _dados):
            return {
                "ok": True,
                "result": {"message_id": 91, "chat": {"id": -1002}},
            }

        publicar_lista_preliminar_pre_live(
            self.repo, resumo, [self.bilhete], "token", "-1002",
            transporte=enviar,
        )
        bilhete_id = self.repo.listar_bilhetes_pendentes()[0]["id"]
        self.repo.finalizar_bilhete(bilhete_id, "green", 0.5)
        chamadas = []

        def editar(url, dados):
            chamadas.append((url, dados))
            return {"ok": True, "result": {"message_id": 91}}

        primeiro = editar_resultados_listas_pre_live(
            self.repo, "token", transporte=editar
        )
        repetido = editar_resultados_listas_pre_live(
            self.repo, "token", transporte=editar
        )

        self.assertEqual(1, primeiro["editados"])
        self.assertEqual(0, repetido["editados"])
        self.assertEqual(1, len(chamadas))
        self.assertIn("editMessageText", chamadas[0][0])
        self.assertIn("✅ GREEN", chamadas[0][1]["text"])
        self.assertIn("Odd 1.50", chamadas[0][1]["text"])

    def test_resultado_da_lista_mantem_pendentes_visiveis(self):
        texto = mensagem_lista_preliminar_com_resultados(
            "LISTA ORIGINAL",
            [
                {"posicao": 1, "resultado": "red"},
                {"posicao": 2, "resultado": None},
            ],
        )
        self.assertIn("1. ❌ RED", texto)
        self.assertIn("2. ⏳ PENDENTE", texto)
        self.assertIn("✅ 0 acertos | ❌ 1 erros", texto)
        self.assertIn("⏳ 1 pendente(s)", texto)
        self.assertIn("🎯 0.0%", texto)

    def test_resultado_da_lista_mostra_cada_perna_da_multipla(self):
        texto = mensagem_lista_preliminar_com_resultados(
            "LISTA ORIGINAL",
            [{
                "posicao": 1,
                "resultado": "red",
                "pernas": [
                    {"posicao": 1, "resultado": "red"},
                    {"posicao": 2, "resultado": "pendente"},
                ],
            }],
        )
        self.assertIn("Pernas: 1❌ 2⏳", texto)

    def test_envia_confirmado_uma_unica_vez(self):
        oficial = deepcopy(self.bilhete)
        oficial["estado"] = "apto_envio_automatico"
        self.repo.registrar_bilhetes([oficial], "2026-08-27")
        chamadas = []

        def transporte(_url, dados):
            chamadas.append(dados)
            return {
                "ok": True,
                "result": {"message_id": 77, "chat": {"id": -1002}},
            }

        primeiro = enviar_confirmados_pre_live(
            self.repo, "2026-08-27", "token", "-1002",
            transporte=transporte,
        )
        segundo = enviar_confirmados_pre_live(
            self.repo, "2026-08-27", "token", "-1002",
            transporte=transporte,
        )

        self.assertEqual(1, primeiro["enviados"])
        self.assertEqual(0, segundo["enviados"])
        self.assertEqual(1, len(chamadas))

    def test_modo_sombra_nao_envia(self):
        self.repo.registrar_bilhetes([self.bilhete], "2026-08-27")
        chamadas = []

        resultado = enviar_confirmados_pre_live(
            self.repo,
            "2026-08-27",
            "token",
            "-1002",
            transporte=lambda *_: chamadas.append(True),
            aplicacao_automatica=False,
        )

        self.assertEqual("desativado_modo_sombra", resultado["estado"])
        self.assertEqual(0, resultado["enviados"])
        self.assertEqual([], chamadas)

    def test_circuit_breaker_preciso_bloqueia_envio_sem_apagar_bilhete(self):
        oficial = deepcopy(self.bilhete)
        oficial["estado"] = "apto_envio_automatico"
        self.repo.registrar_bilhetes([oficial], "2026-08-27")
        suspender(
            "teste|ancora|sha",
            "checkpoint_negativo",
            caminho=self.pasta / "pre_live_preciso_estado.json",
        )
        chamadas = []

        with patch.dict(
            os.environ, {"PRELIVE_FILTRO_PRECISO_ATIVO": "1"}, clear=False
        ):
            resultado = enviar_confirmados_pre_live(
                self.repo,
                "2026-08-27",
                "token",
                "-1002",
                transporte=lambda *_: chamadas.append(True),
            )

        self.assertEqual(0, resultado["enviados"])
        self.assertEqual([], chamadas)
        self.assertEqual(
            {"circuit_breaker_pre_live_preciso": 1},
            resultado["ignorados_filtro_preciso"],
        )
        self.assertEqual(1, len(self.repo.listar_bilhetes_pendentes()))

    def test_edita_a_mensagem_original_com_resultado(self):
        self.repo.registrar_bilhetes([self.bilhete], "2026-08-27")
        pendente = self.repo.listar_bilhetes_pendentes()[0]
        self.repo.registrar_entrega(pendente["id"], "-1002", 77)
        self.repo.finalizar_bilhete(pendente["id"], "green", 0.5)
        chamadas = []

        def transporte(url, dados):
            chamadas.append((url, dados))
            return {"ok": True, "result": {"message_id": 77}}

        resultado = editar_resultados_pre_live(
            self.repo, "token", transporte=transporte
        )

        self.assertEqual(1, resultado["editados"])
        self.assertIn("editMessageText", chamadas[0][0])
        self.assertIn("✅ GREEN — PRÉ-LIVE", chamadas[0][1]["text"])
        self.assertEqual([], self.repo.listar_entregas_para_editar())

    def test_edicao_individual_mostra_resultado_de_cada_perna(self):
        multipla = deepcopy(self.bilhete)
        multipla["tipo"] = "multipla_dois_jogos"
        multipla["pernas"].append(deepcopy(multipla["pernas"][0]))
        multipla["pernas"][1]["fixture_id"] = 99
        multipla["pernas"][1]["jogo"] = {
            "mandante": "Outra Casa", "visitante": "Outra Fora"
        }
        self.repo.registrar_bilhetes([multipla], "2026-08-27")
        item = self.repo.listar_bilhetes_pendentes()[0]
        self.repo.registrar_entrega(item["id"], "-1002", 78)
        self.repo.registrar_resultados_pernas(
            item["id"], item["bilhete"], ["red", "pendente"]
        )
        self.repo.finalizar_bilhete(item["id"], "red", -1.0)
        chamadas = []

        resultado = editar_resultados_pre_live(
            self.repo,
            "token",
            transporte=lambda url, dados: (
                chamadas.append((url, dados))
                or {"ok": True, "result": {"message_id": 78}}
            ),
        )

        self.assertEqual(1, resultado["editados"])
        self.assertIn("❌ ⚽ 1.", chamadas[0][1]["text"])
        self.assertIn("⏳ ⚽ 2.", chamadas[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
