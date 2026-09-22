import json
import os
import unittest
from io import BytesIO
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock, patch

from banco import BancoMonitor
from exploracao_sombra import (
    REGRA_FINGERPRINT_GOL_FT_V3,
    REGRA_VERSAO_GOL_FT_V3,
    VERSAO_EXPLORACAO_ASIATICA,
    VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
    VERSAO_EXPLORACAO_GOL_FT_V3,
)
from linhagem_regras import registrar_ou_validar_linhagem_regra
from telegram_alertas import (
    AlertasTelegram,
    REGRAS_SIMULACAO_GRUPO,
    _transporte_padrao,
    candidato_gol_2t_pos_ht_red_grupo_teste,
    candidato_proximo_gol_balanceado_grupo_teste,
    motivo_suspensao_simulacao,
)
from gol_ht_00_min20 import LINHAGEM as LINHAGEM_GOL_HT_00_MIN20
from gol_ht_00_min20 import VERSAO as VERSAO_GOL_HT_00_MIN20
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO as VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
)
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)
from versoes_regras import (
    VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
    VERSAO_PROXIMO_ESCANTEIO_MAX_86,
)
from valor_mercado import avaliar_valor_mercado


CONTADOR_MENSAGENS = count(1000)


def resposta_telegram():
    return {
        "ok": True,
        "result": {
            "message_id": next(CONTADOR_MENSAGENS),
            "date": 1784678400,
        },
    }


class TelegramAlertasTest(unittest.TestCase):
    def setUp(self):
        self.validar_gate_original = (
            AlertasTelegram._validar_operacao_oficial
        )
        self.gate_operacao = patch(
            "telegram_alertas.AlertasTelegram._validar_operacao_oficial",
            return_value=None,
        )
        self.gate_operacao.start()
        self.aplicar_calibracao = patch(
            "telegram_alertas.CalibradorBacktest.aplicar",
            side_effect=lambda candidato: candidato,
        )
        self.mock_aplicar_calibracao = self.aplicar_calibracao.start()
        self.auditar_diversidade = patch(
            "telegram_alertas.auditar_diversidade_amostra_calibracao",
            return_value={"pronto": True, "estado": "aprovada"},
        )
        self.mock_auditar_diversidade = self.auditar_diversidade.start()
        self.caminho = Path.cwd() / ".teste_telegram.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.linhagem = registrar_ou_validar_linhagem_regra(
            self.banco.conexao,
            Path.cwd(),
            "sinais-v1",
            "features-v1",
        )
        agora = datetime.now().replace(microsecond=0).isoformat()
        snapshot = self.banco.salvar_registro(
            {
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "60 '",
                "qualidade_dados": 90,
            }
        )
        self.sinal_id = self.banco.salvar_candidatos(
            snapshot,
            [
                {
                    "mercado": "gol_ft",
                    "linha": 1.5,
                    "odd": 1.85,
                    "pontuacao_tecnica": 85,
                    "probabilidade_calibrada": 0.8,
                    "regra_versao": "sinais-v1",
                    "regra_fingerprint": self.linhagem["fingerprint_atual"],
                    "motivos": [
                        "chutes_5min=3",
                        "pico_pressao_5min=88",
                    ],
                    "features": {
                        "minuto": 60,
                        "decisao_em": agora,
                        "estado_observado_em": agora,
                        "idade_odds_segundos": 0.0,
                        "odd_oposta": 2.05,
                        "odd_par_sincronizado": True,
                        "valor_mercado_conservador": (
                            avaliar_valor_mercado(0.8, 1.85, 2.05)
                        ),
                    },
                    "status": "aprovado",
                }
            ],
        )[0]
        self.jogo = {
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "60 '",
        }

    def tearDown(self):
        self.auditar_diversidade.stop()
        self.gate_operacao.stop()
        self.aplicar_calibracao.stop()
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def candidato(self, probabilidade=0.8, status="aprovado"):
        candidato = {
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.85,
            "pontuacao_tecnica": 85,
            "probabilidade_calibrada": probabilidade,
            "regra_versao": "sinais-v1",
            "regra_fingerprint": self.linhagem["fingerprint_atual"],
            "qualidade_dados": 90,
            "motivos": ["chutes_5min=6"],
            "status": status,
        }
        if probabilidade is not None:
            candidato.update({
                "odd_oposta": 2.05,
                "odd_par_sincronizado": True,
                "features": {
                    "odd_oposta": 2.05,
                    "odd_par_sincronizado": True,
                },
            })
        else:
            candidato.update({
                "mercado": "proximo_gol",
                "linha": "casa",
                "regra_versao": (
                    VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75
                ),
                "features": {"minuto": 60},
            })
        return candidato

    def atualizar_probabilidade_e_rastro(
        self, probabilidade, odd_oposta=2.05
    ):
        linha = self.banco.conexao.execute(
            "SELECT features_json, odd FROM sinais WHERE id=?",
            (self.sinal_id,),
        ).fetchone()
        features = json.loads(linha["features_json"] or "{}")
        if odd_oposta is None:
            features.pop("odd_oposta", None)
            features.pop("odd_par_sincronizado", None)
        else:
            features["odd_oposta"] = odd_oposta
            features["odd_par_sincronizado"] = True
        features["valor_mercado_conservador"] = avaliar_valor_mercado(
            probabilidade, linha["odd"], odd_oposta
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                UPDATE sinais
                SET probabilidade_calibrada=?, features_json=?
                WHERE id=?
                """,
                (
                    probabilidade,
                    json.dumps(features, ensure_ascii=False),
                    self.sinal_id,
                ),
            )

    def test_acompanhamento_odd_avisa_uma_vez_sem_contar_como_sinal(self):
        snapshot_id = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        candidato = {
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.25,
            "pontuacao_tecnica": 84.0,
            "qualidade_dados": 90.0,
            "probabilidade_calibrada": None,
            "regra_versao": "sinais-v1-acompanhamento-odd",
            "status": "rejeitado",
            "bloqueios": ["odd_fora_da_faixa_operacional"],
            "features": {
                "acompanhamento_odd": {
                    "elegivel_aviso": True,
                    "odd_atual": 1.25,
                    "odd_alvo": 1.40,
                    "odd_maxima_operacional": 2.50,
                },
            },
        }
        sinal_id = self.banco.salvar_candidatos(
            snapshot_id, [candidato]
        )[0]
        transporte = Mock(return_value=resposta_telegram())
        with patch.dict(os.environ, {
            "AVISO_AGUARDAR_ODD_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS": "1",
            "TELEGRAM_BOT_TOKEN": "token-teste",
            "TELEGRAM_CHAT_ID_GOLS": "-100123",
        }):
            alerta = AlertasTelegram(self.banco, transporte=transporte)
            primeiro = alerta.enviar_acompanhamento_odd(
                sinal_id, candidato, self.jogo
            )
            segundo = alerta.enviar_acompanhamento_odd(
                sinal_id, candidato, self.jogo
            )
        self.assertEqual(primeiro, "acompanhamento_odd_entregue")
        self.assertEqual(segundo, "acompanhamento_odd_duplicado")
        transporte.assert_called_once()
        mensagem = transporte.call_args.args[1]["text"]
        self.assertIn("NÃO ENTRAR AINDA", mensagem)
        self.assertIn("1.25", mensagem)
        self.assertIn("1.40", mensagem)
        self.assertEqual(self.banco.total_alertas_entregues_hoje(), 0)

    def test_acompanhamento_odd_edita_green_com_ultima_odd_sem_contaminar_roi(self):
        snapshot_id = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        candidato = {
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.25,
            "pontuacao_tecnica": 84.0,
            "qualidade_dados": 90.0,
            "probabilidade_calibrada": None,
            "regra_versao": "sinais-v1-acompanhamento-odd",
            "status": "rejeitado",
            "bloqueios": ["odd_fora_da_faixa_operacional"],
            "features": {
                "fonte_odds": "api_football",
                "acompanhamento_odd": {
                    "elegivel_aviso": True,
                    "odd_atual": 1.25,
                    "odd_alvo": 1.40,
                    "odd_maxima_operacional": 2.50,
                },
            },
        }
        sinal_id = self.banco.salvar_candidatos(
            snapshot_id, [candidato]
        )[0]
        chamadas = []
        respostas = []

        def transporte(url, dados):
            resposta = resposta_telegram()
            chamadas.append((url, dados))
            respostas.append(resposta)
            return resposta

        with patch.dict(os.environ, {
            "AVISO_AGUARDAR_ODD_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS": "1",
            "TELEGRAM_BOT_TOKEN": "token-teste",
            "TELEGRAM_CHAT_ID_GOLS": "-100123",
        }):
            alerta = AlertasTelegram(self.banco, transporte=transporte)
            self.assertEqual(
                alerta.enviar_acompanhamento_odd(
                    sinal_id, candidato, self.jogo
                ),
                "acompanhamento_odd_entregue",
            )
            self.banco.salvar_registro({
                "coletado_em": "2026-07-20T12:05:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "1-0",
                "status": "Finalizado",
                "fontes": ["api_football"],
                "qualidade": {
                    "pontuacao": 100,
                    "fontes": ["api_football"],
                    "versao": "resultado-api-v1",
                },
            })
            resumo = alerta.atualizar_acompanhamentos_odd()
            repetido = alerta.atualizar_acompanhamentos_odd()

        self.assertEqual(resumo["conclusivos"], 1)
        self.assertEqual(resumo["entregues"], 1)
        self.assertEqual(repetido["consultados"], 0)
        self.assertTrue(chamadas[-1][0].endswith("/editMessageText"))
        self.assertEqual(
            chamadas[-1][1]["message_id"],
            respostas[0]["result"]["message_id"],
        )
        texto = chamadas[-1][1]["text"]
        self.assertIn("RESULTADO HIPOTÉTICO — SEM ENTRADA: GREEN", texto)
        self.assertIn("Última odd registrada antes do gol: 1.25", texto)
        self.assertIn("Odd mínima definida: 1.40", texto)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM resultados_sinais WHERE sinal_id=?",
                (sinal_id,),
            ).fetchone()[0],
            0,
        )

    def salvar_candidato_teste(self, candidato=None, snapshot_id=None):
        candidato = dict(candidato or self.candidato(None))
        agora = datetime.now().replace(microsecond=0).isoformat()
        features = dict(candidato.get("features") or {})
        features.update({
            "decisao_em": agora,
            "estado_observado_em": agora,
            "idade_odds_segundos": 0.0,
        })
        candidato["features"] = features
        candidato["status"] = "aprovado"
        if snapshot_id is None:
            snapshot_id = self.banco.conexao.execute(
                "SELECT snapshot_id FROM sinais WHERE id=?",
                (self.sinal_id,),
            ).fetchone()[0]
        sinal_id = self.banco.salvar_candidatos(
            snapshot_id, [candidato]
        )[0]
        return sinal_id, candidato

    def test_monitoramento_silencioso_consulta_api_sem_aviso_ou_hipotetico(self):
        snapshot_id = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        candidato = {
            **self.candidato(), "linha": 0.5, "odd": 1.20,
            "status": "rejeitado",
            "regra_versao": "sinais-v1-acompanhamento-odd",
            "probabilidade_calibrada": None,
            "features": {"acompanhamento_odd": {
                "elegivel_aviso": True, "odd_atual": 1.20,
                "odd_alvo": 1.40, "odd_maxima_operacional": 2.50,
            }},
        }
        sinal_id = self.banco.salvar_candidatos(
            snapshot_id, [candidato]
        )[0]
        transporte = Mock()
        with patch.dict(os.environ, {
            "AVISO_AGUARDAR_ODD_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS": "0",
            "TELEGRAM_BOT_TOKEN": "token-teste",
            "TELEGRAM_CHAT_ID_GOLS": "-100123",
        }):
            alerta = AlertasTelegram(self.banco, transporte=transporte)
            self.assertEqual(
                alerta.enviar_acompanhamento_odd(sinal_id, candidato, self.jogo),
                "acompanhamento_odd_silencioso",
            )
            fila = self.banco.acompanhamentos_odd_para_rechecagem_api()
            self.assertEqual([item["origem_sinal_id"] for item in fila], [sinal_id])
            self.assertEqual(
                alerta.enviar_acompanhamento_odd(sinal_id, candidato, self.jogo),
                "acompanhamento_odd_duplicado",
            )
            self.banco.salvar_registro({
                "coletado_em": "2026-07-20T12:05:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A", "visitante": "B", "placar": "1-0",
                "status": "Finalizado", "fontes": ["api_football"],
                "qualidade": {
                    "pontuacao": 100, "fontes": ["api_football"],
                    "versao": "resultado-api-v1",
                },
            })
            resumo = alerta.atualizar_acompanhamentos_odd()
        transporte.assert_not_called()
        self.assertEqual(resumo["suprimidos"], 1)
        self.assertEqual(resumo["entregues"], 0)
        self.assertEqual(self.banco.acompanhamentos_odd_para_rechecagem_api(), [])
        self.assertEqual(self.banco.total_alertas_entregues_hoje(), 0)
        registros = self.banco.conexao.execute(
            "SELECT status, entregue_em, provedor_mensagem_id FROM entregas_alertas WHERE sinal_id=?",
            (sinal_id,),
        ).fetchall()
        self.assertEqual(
            {item["status"] for item in registros},
            {"monitoramento_silencioso", "suprimido"},
        )
        self.assertTrue(all(item["entregue_em"] is None for item in registros))

    def test_preferencia_silenciosa_nao_edita_aviso_publicado_anteriormente(self):
        alerta = AlertasTelegram(self.banco, transporte=Mock())
        alerta.token = "token-teste"
        item = {
            "sinal_id": self.sinal_id, "canal_origem": "-100123:aguardar_odd",
            "mensagem_id_origem": "99",
        }
        with (
            patch.dict(os.environ, {"ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS": "0"}),
            patch.object(self.banco, "acompanhamentos_odd_pendentes", return_value=[item]),
            patch.object(alerta, "_desfecho_acompanhamento_odd", return_value={
                "resultado": "green", "snapshot_id": 99,
            }),
        ):
            resumo = alerta.atualizar_acompanhamentos_odd()
        alerta.transporte.assert_not_called()
        self.assertEqual(resumo["entregues"], 0)
        self.assertEqual(resumo["suprimidos"], 1)

    def candidato_teste_com_instante(
        self, instante, minuto=60, status_jogo=None
    ):
        candidato = self.candidato(None)
        candidato["features"].update({
            "minuto": minuto,
            "decisao_em": instante.isoformat(),
            "estado_observado_em": instante.isoformat(),
            "idade_odds_segundos": 0.0,
        })
        jogo = {
            **self.jogo,
            "status": status_jogo or f"{minuto} '",
        }
        return candidato, jogo

    def candidato_v2_controle(self):
        return {
            **self.candidato(None, status="simulacao"),
            "mercado": "gol_ft",
            "linha": 1.5,
            "regra_versao": REGRA_VERSAO_GOL_FT_V3,
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
            "features": {"exploracao_sombra": {
                "versao": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
                "telegram_oficial": False,
                "aplicacao_automatica": False,
            }},
            "motivos": [
                "alvo=mais_1_gol",
                "exploracao_sombra="
                f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}",
                "nao_enviar_telegram",
            ],
        }

    def test_gate_oficial_falha_fechado_sem_validador(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )

        self.assertEqual(
            self.validar_gate_original(alerta),
            "gate_operacao_oficial_indisponivel",
        )

    def test_gate_oficial_distingue_inicializacao_e_degradacao(self):
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: resposta_telegram(),
            validador_operacao_oficial=lambda: {
                "apto": False,
                "estado": "inicializando",
            },
        )
        self.assertEqual(
            self.validar_gate_original(alerta),
            "operacao_oficial_inicializando",
        )
        alerta.validador_operacao_oficial = lambda: {
            "apto": False,
            "estado": "degradado",
        }
        self.assertEqual(
            self.validar_gate_original(alerta),
            "operacao_oficial_degradada",
        )

    def test_gate_oficial_entrega_candidato_ao_validador_de_edge(self):
        recebidos = []

        def validar(*, candidato=None):
            recebidos.append(candidato)
            return {
                "apto": False,
                "estado": "bloqueado",
                "motivo": "edge_portfolio_nao_comprovado",
            }

        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: resposta_telegram(),
            validador_operacao_oficial=validar,
        )
        candidato = self.candidato()

        self.assertEqual(
            self.validar_gate_original(alerta, candidato),
            "edge_portfolio_nao_comprovado",
        )
        self.assertIs(recebidos[0], candidato)

    def test_gate_oficial_preserva_motivo_de_cotacao_nao_executavel(self):
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: resposta_telegram(),
            validador_operacao_oficial=lambda **_: {
                "apto": False,
                "estado": "bloqueado",
                "motivo": "cotacao_oficial_nao_executavel",
            },
        )

        self.assertEqual(
            self.validar_gate_original(alerta, self.candidato()),
            "cotacao_oficial_nao_executavel",
        )

    def test_gate_oficial_preserva_validador_legado_sem_argumento(self):
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: resposta_telegram(),
            validador_operacao_oficial=lambda: {
                "apto": True, "estado": "saudavel"
            },
        )

        self.assertIsNone(
            self.validar_gate_original(alerta, self.candidato())
        )

    def test_gateway_bloqueia_oficial_quando_operacao_nao_esta_pronta(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        with patch.object(
            alerta,
            "_validar_operacao_oficial",
            return_value="operacao_oficial_degradada",
        ):
            resultado = alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(), self.jogo
            )

        self.assertEqual(resultado, "operacao_oficial_degradada")
        entrega = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:oficial'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(entrega),
            ("bloqueado", "operacao_oficial_degradada"),
        )

    def test_gateway_oficial_exige_diversidade_da_amostra(self):
        self.mock_auditar_diversidade.return_value = {
            "pronto": False,
            "estado": "diversidade_temporal_insuficiente",
        }
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, self.candidato(), self.jogo
        )

        self.assertEqual(resultado, "diversidade_amostra_insuficiente")

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
        },
        clear=False,
    )
    def test_gateway_bloqueia_simulacao_quando_fontes_estao_degradadas(self):
        transporte = Mock(return_value=resposta_telegram())
        alerta = AlertasTelegram(self.banco, transporte=transporte)
        with patch.object(
            alerta,
            "_validar_operacao_oficial",
            return_value="operacao_oficial_degradada",
        ):
            resultado = alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(None), self.jogo
            )

        self.assertEqual(resultado, "operacao_oficial_degradada")
        transporte.assert_not_called()
        entrega = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:teste'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(entrega),
            ("bloqueado", "operacao_oficial_degradada"),
        )

    def test_mensagem_teste_apresenta_motivos_em_linguagem_clara(self):
        candidato = self.candidato(None)
        candidato["motivos"] = [
            "alvo=mais_1_gol",
            "chutes_5min=2",
            "chutes_no_gol_total=14",
            "pico_pressao_5min=90",
            "gols_atuais=6",
            "minuto_na_faixa_da_regra",
            "mercado_ao_vivo_disponivel",
        ]

        mensagem = AlertasTelegram._mensagem_teste(
            candidato, self.jogo
        )

        self.assertIn("🎯 MERCADO OBSERVADO", mensagem)
        self.assertIn("📈 LEITURA DO MOMENTO", mensagem)
        self.assertIn("📊 AVALIAÇÃO DO MODELO", mensagem)
        self.assertIn("Objetivo analisado: mais 1 gol", mensagem)
        self.assertIn("Chutes nos últimos 5 minutos: 2", mensagem)
        self.assertIn("Chutes no alvo na partida: 14", mensagem)
        self.assertIn(
            "Pico de pressão nos últimos 5 minutos: 90/100",
            mensagem,
        )
        self.assertNotIn("alvo=mais_1_gol", mensagem)
        self.assertNotIn("chutes_5min=2", mensagem)

    def test_mensagem_teste_formata_odd_com_duas_casas(self):
        candidato = self.candidato(None)
        candidato["odd"] = 1.909

        mensagem = AlertasTelegram._mensagem_teste(
            candidato, self.jogo
        )

        self.assertIn("Odd: 1.91", mensagem)
        self.assertNotIn("Odd: 1.909", mensagem)

    def test_challenger_pos_ht_red_recebe_rotulo_entrada_enviezada(self):
        candidato = self.candidato(None)
        candidato["status"] = "simulacao"
        candidato["mercado"] = "gol_ft"
        candidato["features"] = {
            "exploracao_sombra": {
                "versao": "gol-ft-2t-pos-ht-red-odd144-v1"
            },
            "gol_2t_pos_ht_red": {"linhagem_sha256": "abc"},
        }

        mensagem_teste = AlertasTelegram._mensagem_teste(
            candidato, self.jogo
        )
        candidato["probabilidade_calibrada"] = 0.8
        mensagem_oficial = AlertasTelegram._mensagem(
            candidato, self.jogo
        )

        self.assertTrue(mensagem_teste.startswith("⚠️ ENTRADA ENVIEZADA"))
        self.assertTrue(mensagem_oficial.startswith("⚠️ ENTRADA ENVIEZADA"))

        with patch.dict(
            os.environ, {"GOL_2T_POS_HT_RED_GRUPO_ATIVO": "1"}
        ):
            self.assertTrue(candidato_gol_2t_pos_ht_red_grupo_teste(candidato))

    def test_sinal_identifica_escanteio_asiatico_e_periodo(self):
        for mercado, periodo in (
            ("escanteios_ft_asiatico", "jogo inteiro"),
            ("escanteios_1t", "1º tempo"),
            ("escanteios_2t", "2º tempo"),
        ):
            with self.subTest(mercado=mercado):
                candidato = self.candidato(0.8)
                candidato["mercado"] = mercado
                candidato["linha"] = 4.0
                mensagem_oficial = AlertasTelegram._mensagem(
                    candidato,
                    self.jogo,
                )
                candidato["probabilidade_calibrada"] = None
                mensagem_teste = AlertasTelegram._mensagem_teste(
                    candidato,
                    self.jogo,
                )

                for mensagem in (mensagem_oficial, mensagem_teste):
                    self.assertIn("Escanteios Asiáticos", mensagem)
                    self.assertIn(periodo, mensagem)
                    self.assertIn("Linha: 4.0", mensagem)

    def test_sinal_normal_nao_e_rotulado_como_asiatico(self):
        candidato = self.candidato(0.8)
        candidato["mercado"] = "proximo_escanteio"
        candidato["linha"] = 8.5

        mensagem = AlertasTelegram._mensagem(candidato, self.jogo)

        self.assertIn("Escanteio normal", mensagem)
        self.assertNotIn("Escanteios Asiáticos", mensagem)

    def test_resultado_novo_edita_entrada_sem_repetir_relatorio(self):
        item = {
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": 1.82,
            "pontuacao_tecnica": 81.0,
            "probabilidade_calibrada": None,
            "regra_versao": "regra-teste",
            "qualidade_dados": 92,
            "motivos_json": '["chutes_5min=4"]',
            "features_json": "{}",
            "mandante": "Time A",
            "visitante": "Time B",
            "liga": "Liga Teste",
            "minuto_entrada": "60 '",
            "placar_entrada": "1-0",
            "resultado": "green",
            "retorno_unidades": 0.82,
            "placar_liquidacao": "2-1",
        }

        mensagem = AlertasTelegram._mensagem_entrada_finalizada(
            item, {}, simulacao=True
        )

        self.assertIn("🧪 ANÁLISE EXPERIMENTAL — NÃO É ENTRADA", mensagem)
        self.assertIn("✅✅✅ GREEN DA SIMULAÇÃO!", mensagem)
        self.assertIn(
            "Placar final: 2-1 | Retorno hipotético: +0.82u", mensagem
        )
        self.assertNotIn("RESULTADO DA ANÁLISE", mensagem)
        self.assertEqual(mensagem.count("GREEN"), 1)
        self.assertEqual(mensagem.count("Time A x Time B"), 1)

    @patch.dict(os.environ, {"SINAIS_TESTE_ATIVO": "0"}, clear=False)
    def test_nao_envia_sem_calibracao(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        self.assertEqual(
            alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(None), self.jogo
            ),
            "sem_calibracao",
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "10",
        },
        clear=False,
    )
    def test_modo_teste_envia_sem_fingir_calibracao(self):
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append(dados)
            or resposta_telegram(),
        )
        sinal_id, candidato = self.salvar_candidato_teste()

        self.assertEqual(
            alerta.avaliar_e_enviar(sinal_id, candidato, self.jogo),
            "teste_entregue",
        )
        self.assertIn(
            "ANÁLISE EXPERIMENTAL — NÃO É ENTRADA", chamadas[0]["text"]
        )
        self.assertNotIn("SINAL DE TESTE", chamadas[0]["text"])
        self.assertIn("não é probabilidade", chamadas[0]["text"])
        self.assertIn(
            f"Regra: {VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75}",
            chamadas[0]["text"],
        )
        self.assertEqual(self.banco.total_alertas_entregues_hoje(), 0)
        self.assertEqual(self.banco.total_alertas_teste_entregues_hoje(), 1)

        status = self.banco.conexao.execute(
            "SELECT status FROM sinais WHERE id=?", (sinal_id,)
        ).fetchone()[0]
        self.assertEqual(status, "aprovado")
        self.assertEqual(
            alerta.avaliar_e_enviar(sinal_id, candidato, self.jogo),
            "duplicado",
        )
        snapshot_final = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T13:00:00",
            "url": "https://packball.com/match/1/live",
            "mandante": "A",
            "visitante": "B",
            "placar": "2-0",
            "status": "Finalizado",
            "fontes": ["packball"],
        })
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    retorno_unidades, observacao,
                    snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-07-20T13:00:00', 'green', 0.85, 'teste',
                          ?, 'packball')
                """,
                (sinal_id, snapshot_final),
            )
        resumo = alerta.enviar_resultados_simulacoes()
        self.assertEqual(resumo["entregues"], 1)
        self.assertIn("RESULTADO DA ANÁLISE — GREEN", chamadas[-1]["text"])
        self.assertIn("Mercado: Próximo gol", chamadas[-1]["text"])
        self.assertIn(
            f"Regra: {VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75}",
            chamadas[-1]["text"],
        )
        self.assertIn(
            "LEITURA QUE ORIGINOU O SINAL", chamadas[-1]["text"]
        )
        self.assertIn("Minuto: 60 ' | Placar: 0-0", chamadas[-1]["text"])
        self.assertIn(
            "Chutes nos últimos 5 minutos: 6", chamadas[-1]["text"]
        )
        self.assertIn("Qualidade dos dados: 90.0/100", chamadas[-1]["text"])
        self.assertIn("PLACAR DAS ANÁLISES", chamadas[-1]["text"])
        self.assertIn(
            "Total: ✅ 1 GREEN / ❌ 0 RED — índice 100.0%",
            chamadas[-1]["text"],
        )
        self.assertIn(
            "Próximo gol: ✅ 1 GREEN / ❌ 0 RED — índice 100.0%",
            chamadas[-1]["text"],
        )
        self.assertIn("CONFIRMAÇÃO DO RESULTADO", chamadas[-1]["text"])
        self.assertIn("Placar na liquidação: 2-0", chamadas[-1]["text"])
        self.assertIn(
            "Situação na liquidação: Finalizado", chamadas[-1]["text"]
        )
        self.assertIn("Fonte do resultado: PackBall", chamadas[-1]["text"])
        self.assertIn(
            "Confirmado em: 20/07/2026 13:00", chamadas[-1]["text"]
        )
        self.assertEqual(
            alerta.enviar_resultados_simulacoes()["consultados"], 0
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "10",
            "LIMITE_GLOBAL_SINAIS_TESTE": "10",
        },
        clear=False,
    )
    def test_timeout_simulacao_fica_incerto_e_nao_reenvia_automaticamente(self):
        transporte = Mock(
            side_effect=TimeoutError("resposta nao recebida")
        )
        alerta = AlertasTelegram(self.banco, transporte=transporte)
        sinal_id, candidato = self.salvar_candidato_teste()

        primeiro = alerta.avaliar_e_enviar(
            sinal_id, candidato, self.jogo
        )
        segundo = alerta.avaliar_e_enviar(
            sinal_id, candidato, self.jogo
        )

        self.assertEqual(primeiro, "incerto")
        self.assertEqual(segundo, "entrega_teste_incerta")
        transporte.assert_called_once()
        estados = self.banco.conexao.execute(
            """
            SELECT status, reserva_token FROM entregas_alertas
            WHERE sinal_id=? AND canal='123:teste' ORDER BY id
            """,
            (sinal_id,),
        ).fetchall()
        self.assertEqual(
            [item["status"] for item in estados],
            ["incerto"],
        )
        self.assertTrue(estados[0]["reserva_token"])
        self.assertEqual(self.banco.total_alertas_teste_entregues_hoje(), 0)

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "100",
            "LIMITE_GLOBAL_SINAIS_TESTE": "100",
        },
        clear=False,
    )
    def test_claim_impede_post_duplicado_entre_instancias(self):
        sinal_id, candidato = self.salvar_candidato_teste()
        transporte = Mock(return_value=resposta_telegram())
        primeiro = AlertasTelegram(self.banco, transporte=transporte)
        concorrente = BancoMonitor(self.caminho)
        try:
            segundo = AlertasTelegram(concorrente, transporte=transporte)
            reserva = self.banco.reservar_entrega_alerta(
                sinal_id, "123:teste"
            )
            self.assertTrue(reserva)

            resultado = segundo.avaliar_e_enviar(
                sinal_id, dict(candidato), dict(self.jogo)
            )

            self.assertEqual(resultado, "entrega_teste_incerta")
            transporte.assert_not_called()
            self.assertTrue(primeiro.banco.reserva_entrega_valida(
                sinal_id, "123:teste", reserva
            ))
        finally:
            concorrente.fechar()

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_aviso_insuficiente_tambem_exige_claim_exclusivo(self):
        candidato = self.candidato(0.7)
        self.atualizar_probabilidade_e_rastro(0.7)
        reserva = self.banco.reservar_entrega_alerta(
            self.sinal_id, "123:insuficiente"
        )
        self.assertTrue(reserva)
        transporte = Mock(return_value=resposta_telegram())
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, candidato, dict(self.jogo)
        )

        self.assertEqual(resultado, "reserva_entrega_concorrente")
        transporte.assert_not_called()

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_timeout_no_aviso_insuficiente_fica_incerto_e_nao_reenvia(self):
        candidato = self.candidato(0.7)
        self.atualizar_probabilidade_e_rastro(0.7)
        transporte = Mock(side_effect=TimeoutError("resposta nao recebida"))
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        primeiro = alerta.avaliar_e_enviar(
            self.sinal_id, candidato, dict(self.jogo)
        )
        segundo = alerta.avaliar_e_enviar(
            self.sinal_id, candidato, dict(self.jogo)
        )

        self.assertEqual(primeiro, "incerto")
        self.assertEqual(segundo, "reserva_entrega_concorrente")
        transporte.assert_called_once()
        estados = self.banco.conexao.execute(
            """
            SELECT status, reserva_token FROM entregas_alertas
            WHERE sinal_id=? AND canal='123:insuficiente'
            ORDER BY id
            """,
            (self.sinal_id,),
        ).fetchall()
        self.assertEqual(
            [item["status"] for item in estados],
            ["incerto"],
        )
        self.assertTrue(estados[0]["reserva_token"])
        self.assertEqual(self.banco.alertas_com_erro_para_reenvio(), [])

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_oficial_reconfere_claim_imediatamente_antes_do_post(self):
        transporte = Mock(return_value=resposta_telegram())
        alerta = AlertasTelegram(self.banco, transporte=transporte)
        reserva = self.banco.reservar_entrega_alerta(self.sinal_id, "123")
        self.assertTrue(reserva)

        with patch.object(
            self.banco, "possui_entrega_oficial_incerta", return_value=False
        ):
            resultado = alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(), dict(self.jogo)
            )

        self.assertEqual(resultado, "reserva_entrega_concorrente")
        transporte.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "100",
            "LIMITE_GLOBAL_SINAIS_TESTE": "100",
        },
        clear=False,
    )
    def test_retry_controlado_recusa_token_que_nao_adquiriu(self):
        sinal_id, candidato = self.salvar_candidato_teste()
        reserva = self.banco.reservar_entrega_alerta(
            sinal_id, "123:teste"
        )
        self.assertTrue(reserva)
        transporte = Mock(return_value=resposta_telegram())
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(
            sinal_id,
            candidato,
            dict(self.jogo),
            reenvio_controlado=True,
            reserva_reenvio_token="token-de-outro-processo",
        )

        self.assertEqual(resultado, "reserva_reenvio_invalida")
        transporte.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "0",
        },
        clear=False,
    )
    def test_resultado_oficial_inclui_placar_e_nao_duplica(self):
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append(dados)
            or resposta_telegram(),
        )
        self.assertEqual(
            alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(), self.jogo
            ),
            "entregue",
        )
        snapshot_final = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T13:00:00",
            "url": "https://packball.com/match/1/live",
            "mandante": "A",
            "visitante": "B",
            "placar": "0-1",
            "status": "FT",
            "fontes": ["api_football"],
        })
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    retorno_unidades, observacao,
                    snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-07-20T13:00:00', 'red', -1.0, 'teste',
                          ?, 'api_football')
                """,
                (self.sinal_id, snapshot_final),
            )

        resumo = alerta.enviar_resultados_oficiais()

        self.assertEqual(resumo["entregues"], 1)
        self.assertIn("RESULTADO DA ENTRADA — RED", chamadas[-1]["text"])
        self.assertIn("Mercado: Over de gols FT", chamadas[-1]["text"])
        self.assertNotIn("Mercado: gol_ft", chamadas[-1]["text"])
        self.assertIn("PLACAR OFICIAL", chamadas[-1]["text"])
        self.assertIn(
            "Confiança histórica calibrada na entrada: 80.0%",
            chamadas[-1]["text"],
        )
        self.assertIn(
            "Chutes nos últimos 5 minutos: 3", chamadas[-1]["text"]
        )
        self.assertIn(
            "Total: ✅ 0 GREEN / ❌ 1 RED — índice 0.0%",
            chamadas[-1]["text"],
        )
        self.assertIn(
            "Over de gols FT: ✅ 0 GREEN / ❌ 1 RED — índice 0.0%",
            chamadas[-1]["text"],
        )
        self.assertIn("Placar na liquidação: 0-1", chamadas[-1]["text"])
        self.assertIn(
            "Situação na liquidação: Finalizado", chamadas[-1]["text"]
        )
        self.assertIn(
            "Fonte do resultado: API-Football", chamadas[-1]["text"]
        )
        self.assertEqual(
            alerta.enviar_resultados_oficiais()["consultados"], 0
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "0",
        },
        clear=False,
    )
    def test_green_antecipado_edita_a_entrada_sem_liquidar_o_banco(self):
        chamadas = []
        respostas = []

        def transporte(url, dados):
            resposta = resposta_telegram()
            chamadas.append((url, dados))
            respostas.append(resposta)
            return resposta

        alerta = AlertasTelegram(
            self.banco,
            transporte=transporte,
        )
        self.assertEqual(
            alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(), self.jogo
            ),
            "entregue",
        )
        atual = {
            "coletado_em": "2026-07-20T12:05:00",
            "url": "https://packball.com/match/1/live",
            "mandante": "A",
            "visitante": "B",
            "placar": "1-1",
            "status": "65 '",
            "fontes": ["packball"],
            "qualidade": {
                "pontuacao": 100,
                "fontes": ["packball"],
                "apto_para_liquidacao": True,
            },
        }
        self.banco.salvar_registro(atual)

        resumo = alerta.enviar_greens_antecipados()

        self.assertEqual(resumo["confirmados"], 1)
        self.assertEqual(resumo["entregues"], 1)
        self.assertTrue(chamadas[-1][0].endswith("/editMessageText"))
        self.assertEqual(
            chamadas[-1][1]["message_id"],
            respostas[0]["result"]["message_id"],
        )
        self.assertIn("✅✅✅ GREEN!", chamadas[-1][1]["text"])
        self.assertIn("Confirmado aos 65 '", chamadas[-1][1]["text"])
        self.assertNotIn("Placar final", chamadas[-1][1]["text"])
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM resultados_sinais"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            alerta.enviar_greens_antecipados()["entregues"], 0
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "SINAIS_TESTE_ATIVO": "0",
        },
        clear=False,
    )
    def test_resultados_e_correcoes_nao_saem_com_operacao_degradada(self):
        casos = (
            (
                "enviar_resultados_simulacoes",
                "resultados_simulacoes_nao_notificados",
            ),
            (
                "enviar_resultados_oficiais",
                "resultados_oficiais_nao_notificados",
            ),
            (
                "enviar_correcoes_resultados_simulacoes",
                "revisoes_simulacoes_nao_notificadas",
            ),
        )
        for metodo, consulta in casos:
            with self.subTest(metodo=metodo):
                banco = Mock()
                getattr(banco, consulta).return_value = [{"sinal_id": 1}]
                banco.resultados_edicoes_incertas.return_value = []
                transporte = Mock()
                alerta = AlertasTelegram(banco, transporte=transporte)
                alerta._validar_operacao_oficial = Mock(
                    return_value="operacao_oficial_degradada"
                )

                resumo = getattr(alerta, metodo)()

                self.assertEqual(resumo["consultados"], 1)
                self.assertEqual(resumo["entregues"], 0)
                self.assertEqual(resumo["bloqueados"], 1)
                self.assertEqual(
                    resumo["motivo_bloqueio"],
                    "operacao_oficial_degradada",
                )
                transporte.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "PONTUACAO_MINIMA_SINAL_TESTE": "90",
            "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE": "90",
            "QUALIDADE_MINIMA_SINAL_TESTE": "80",
        },
        clear=False,
    )
    def test_modo_teste_filtra_por_pontuacao_minima(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )

        self.assertEqual(
            alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(None), self.jogo
            ),
            "pontuacao_teste_insuficiente",
        )
        self.assertEqual(self.banco.total_alertas_teste_entregues_hoje(), 0)
        filtro = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:teste'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(filtro),
            ("filtrado", "pontuacao_teste_insuficiente"),
        )

    @patch.dict(
        os.environ,
        {
            "SINAIS_TESTE_ATIVO": "1",
            "PONTUACAO_MINIMA_SINAL_TESTE": "75",
            "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE": "70",
            "QUALIDADE_MINIMA_SINAL_TESTE": "80",
        },
        clear=False,
    )
    def test_proximo_gol_usa_limiar_isolado_sem_afrouxar_outros(self):
        alerta = AlertasTelegram(self.banco, transporte=Mock())
        proximo_gol = self.candidato(None)
        proximo_gol["pontuacao_tecnica"] = 70.5
        outro_mercado = {
            **proximo_gol,
            "mercado": "proximo_escanteio",
            "regra_versao": VERSAO_PROXIMO_ESCANTEIO_MAX_86,
        }

        self.assertIsNone(alerta.motivo_filtro_teste(proximo_gol))
        self.assertEqual(
            "pontuacao_teste_insuficiente",
            alerta.motivo_filtro_teste(outro_mercado),
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "PONTUACAO_MINIMA_SINAL_TESTE": "90",
            "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE": "90",
            "QUALIDADE_MINIMA_SINAL_TESTE": "80",
        },
        clear=False,
    )
    def test_registra_descarte_comparavel_sem_tentar_enviar(self):
        transporte = Mock()
        alerta = AlertasTelegram(self.banco, transporte=transporte)
        candidato = self.candidato(None)

        retorno = alerta.registrar_filtro_teste(
            self.sinal_id, candidato
        )

        self.assertEqual(retorno, "pontuacao_teste_insuficiente")
        transporte.assert_not_called()
        filtro = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:teste'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(filtro),
            ("filtrado", "pontuacao_teste_insuficiente"),
        )

    @patch.dict(
        os.environ,
        {"SINAIS_TESTE_ATIVO": "1"},
        clear=False,
    )
    def test_registra_aprovado_nao_selecionado_no_snapshot(self):
        transporte = Mock()
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        retorno = alerta.registrar_priorizacao_teste(self.sinal_id)

        self.assertEqual(
            retorno, "nao_selecionado_melhor_sinal_snapshot"
        )
        transporte.assert_not_called()
        filtro = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:priorizacao_teste'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(filtro),
            ("filtrado", "nao_selecionado_melhor_sinal_snapshot"),
        )

    @patch.dict(
        os.environ,
        {
            "SINAIS_TESTE_ATIVO": "1",
            "PONTUACAO_MINIMA_SINAL_TESTE": "75",
            "QUALIDADE_MINIMA_SINAL_TESTE": "80",
        },
        clear=False,
    )
    def test_suspende_aviso_gol_ft_v6_reprovado_mantendo_registro(self):
        alerta = AlertasTelegram(self.banco, transporte=Mock())
        candidato = {
            **self.candidato(None),
            "mercado": "gol_ft",
            "regra_versao": "sinais-v6",
            "pontuacao_tecnica": 95,
            "qualidade_dados": 99,
        }

        retorno = alerta.registrar_filtro_teste(
            self.sinal_id, candidato
        )

        self.assertEqual(
            retorno, "mercado_reprovado_validacao_gol_ft_v6"
        )
        filtro = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:validacao'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(filtro),
            ("filtrado", "mercado_reprovado_validacao_gol_ft_v6"),
        )

    @patch.dict(
        os.environ,
        {"SINAIS_TESTE_ATIVO": "1"},
        clear=False,
    )
    def test_registra_roteamento_bloqueado_em_leitura_posterior(self):
        snapshot_id = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        candidato = {
            **self.candidato(None),
            "mercado": "gol_ft",
            "regra_versao": "sinais-v6",
            "pontuacao_tecnica": 95,
            "qualidade_dados": 99,
        }
        primeiro = self.banco.salvar_candidatos(
            snapshot_id, [dict(candidato)]
        )[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                "UPDATE sinais SET status='simulacao' WHERE id=?",
                (primeiro,),
            )
        posterior = dict(candidato)
        sinal_posterior = self.banco.salvar_candidatos(
            snapshot_id, [posterior]
        )[0]
        alerta = AlertasTelegram(self.banco, transporte=Mock())

        retorno = alerta.registrar_filtro_teste(
            sinal_posterior, posterior
        )

        self.assertEqual(
            retorno, "mercado_reprovado_validacao_gol_ft_v6"
        )
        filtro = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:validacao'
            """,
            (sinal_posterior,),
        ).fetchone()
        self.assertEqual(
            tuple(filtro),
            ("filtrado", "mercado_reprovado_validacao_gol_ft_v6"),
        )

    def test_proximo_gol_aceita_odd_na_faixa_global(self):
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
            "odd": 1.65,
            "features": {"minuto": 60},
        }

        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            None,
        )

    def test_proximo_gol_rejeita_odd_abaixo_da_faixa_global(self):
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
            "odd": 1.39,
            "features": {"minuto": 60},
        }

        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            "filtro_proximo_gol_odd_fora_faixa_operacional",
        )

    def test_proximo_gol_bloqueia_depois_do_minuto_75(self):
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
            "odd": 1.66,
            "features": {"minuto": 76},
        }

        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            "filtro_proximo_gol_minuto_maximo_75",
        )

    def test_proximo_gol_odd166_minuto75_permanece_elegivel(self):
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
            "odd": 1.66,
            "features": {"minuto": 75},
        }

        self.assertIsNone(motivo_suspensao_simulacao(candidato))

    def test_allowlist_grupo_teste_contem_somente_tres_regras_ativas(self):
        self.assertEqual(
            REGRAS_SIMULACAO_GRUPO,
            frozenset({
                (
                    "proximo_gol",
                    VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
                ),
                (
                    "proximo_escanteio",
                    VERSAO_PROXIMO_ESCANTEIO_MAX_86,
                ),
                (
                    "escanteios_ft_asiatico",
                    VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
                ),
            }),
        )

    def test_regras_positivas_ativas_permanecem_no_grupo_teste(self):
        candidatos = (
            {
                "mercado": "proximo_gol",
                "regra_versao": VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
                "odd": 1.66,
                "features": {"minuto": 60},
            },
            {
                "mercado": "proximo_escanteio",
                "regra_versao": VERSAO_PROXIMO_ESCANTEIO_MAX_86,
            },
            {
                "mercado": "escanteios_ft_asiatico",
                "regra_versao": VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
            },
        )

        for candidato in candidatos:
            with self.subTest(mercado=candidato["mercado"]):
                self.assertIsNone(motivo_suspensao_simulacao(candidato))

    def _candidato_proximo_gol_balanceado(self):
        return {
            "status": "simulacao",
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            "odd": 1.55,
            "pontuacao_tecnica": 60,
            "features": {
                "exploracao_sombra": {
                    "versao": VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
                    "grupo_teste": True,
                    "telegram_oficial": False,
                    "aplicacao_automatica": False,
                },
                "proximo_gol_balanceado_sombra": {"elegivel": True},
            },
        }

    @patch("telegram_alertas.PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO", True)
    def test_proximo_gol_balanceado_e_liberado_so_no_grupo_teste(self):
        candidato = self._candidato_proximo_gol_balanceado()

        self.assertTrue(
            candidato_proximo_gol_balanceado_grupo_teste(candidato)
        )
        self.assertIsNone(motivo_suspensao_simulacao(candidato))

    @patch("telegram_alertas.PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO", False)
    def test_proximo_gol_balanceado_tem_rollback_imediato(self):
        candidato = self._candidato_proximo_gol_balanceado()

        self.assertFalse(
            candidato_proximo_gol_balanceado_grupo_teste(candidato)
        )
        self.assertEqual(
            "exploracao_sombra_fora_allowlist_simulacao_grupo",
            motivo_suspensao_simulacao(candidato),
        )

    @patch("telegram_alertas.PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO", True)
    @patch(
        "telegram_alertas.proximo_gol_balanceado_grupo_liberado",
        return_value=False,
    )
    def test_balanceado_respeita_circuit_breaker_persistente(
        self, _liberado
    ):
        candidato = self._candidato_proximo_gol_balanceado()

        self.assertFalse(
            candidato_proximo_gol_balanceado_grupo_teste(candidato)
        )
        self.assertEqual(
            "circuit_breaker_proximo_gol_balanceado",
            motivo_suspensao_simulacao(candidato),
        )

    @patch("telegram_alertas.PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO", True)
    def test_balanceado_usa_pontuacao_60_sem_relaxar_regra_principal(self):
        alertas = object.__new__(AlertasTelegram)
        alertas.pontuacao_minima_proximo_gol_teste = 70
        alertas.pontuacao_minima_teste = 70
        alertas.qualidade_minima_teste = 100
        candidato = self._candidato_proximo_gol_balanceado()
        candidato["qualidade_dados"] = 100

        self.assertIsNone(alertas.motivo_filtro_teste(candidato))
        candidato["pontuacao_tecnica"] = 59.9
        self.assertEqual(
            "pontuacao_teste_insuficiente",
            alertas.motivo_filtro_teste(candidato),
        )

    def _candidato_asiatico_ft_multiplos(self):
        return {
            "status": "simulacao",
            "mercado": "escanteios_ft_asiatico",
            "linha": 10.5,
            "odd": 1.90,
            "features": {
                "tipo_mercado_odds": "asiatico",
                "exploracao_sombra": {
                    "versao": VERSAO_EXPLORACAO_ASIATICA,
                    "bloqueios_originais": [
                        "linha_exige_multiplos_escanteios",
                        "odd_ao_vivo_indisponivel",
                    ],
                    "aplicacao_automatica": False,
                },
            },
        }

    @patch(
        "telegram_alertas.ESCANTEIOS_FT_ASIATICO_MULTIPLOS_GRUPO_ATIVO",
        True,
    )
    def test_asiatico_ft_multiplos_exige_ativacao_explicita_para_o_grupo(self):
        candidato = self._candidato_asiatico_ft_multiplos()

        self.assertIsNone(motivo_suspensao_simulacao(candidato))

    @patch(
        "telegram_alertas.ESCANTEIOS_FT_ASIATICO_MULTIPLOS_GRUPO_ATIVO",
        False,
    )
    def test_asiatico_ft_multiplos_regredido_permanece_em_sombra(self):
        candidato = self._candidato_asiatico_ft_multiplos()

        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            "exploracao_sombra_fora_allowlist_simulacao_grupo",
        )

    def test_asiatico_ft_multiplos_incompleto_permanece_em_sombra(self):
        candidato = {
            "status": "simulacao",
            "mercado": "escanteios_ft_asiatico",
            "features": {"exploracao_sombra": {
                "versao": VERSAO_EXPLORACAO_ASIATICA,
                "aplicacao_automatica": False,
            }},
        }

        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            "exploracao_sombra_fora_allowlist_simulacao_grupo",
        )

    def test_ht_e_regra_desconhecida_ficam_somente_em_sombra(self):
        for candidato in (
            {
                "mercado": "gol_ht",
                "regra_versao": "sinais-v8b-gol-ht-max28",
            },
            {
                "mercado": "proximo_gol",
                "regra_versao": "sinais-versao-futura",
                "odd": 1.80,
                "features": {"minuto": 60},
            },
        ):
            with self.subTest(candidato=candidato):
                self.assertEqual(
                    motivo_suspensao_simulacao(candidato),
                    "regra_fora_allowlist_simulacao_grupo",
                )

    @patch.dict(
        os.environ,
        {"GOL_HT_SEM_TENDENCIA_PACKBALL_GRUPO_ATIVO": "1"},
        clear=False,
    )
    @patch("telegram_alertas.GOL_HT_00_MIN20_GRUPO_ATIVO", True)
    def test_ht_v3_libera_tendencia_packball_indisponivel_com_conversao(self):
        candidato = {
            "status": "simulacao",
            "mercado": "gol_ht",
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "features": {
                "exploracao_sombra": {"versao": VERSAO_GOL_HT_00_MIN20},
                "gol_ht_00_min20": {
                    "linhagem_sha256": LINHAGEM_GOL_HT_00_MIN20,
                },
                "protecao_tendencias_packball": {
                    "ativa": True,
                    "aprovada": False,
                    "motivo": "tendencia_packball_indisponivel",
                },
                "protecao_conversao_gols": {
                    "ativa": True,
                    "aprovada": True,
                    "motivo": "apoio_da_linha_confirmado",
                },
            },
        }

        self.assertIsNone(motivo_suspensao_simulacao(candidato))

    @patch.dict(
        os.environ,
        {"GOL_HT_SEM_TENDENCIA_PACKBALL_GRUPO_ATIVO": "1"},
        clear=False,
    )
    def test_ht_v3_nao_libera_amostra_packball_insuficiente(self):
        candidato = {
            "status": "simulacao",
            "mercado": "gol_ht",
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "features": {
                "exploracao_sombra": {"versao": VERSAO_GOL_HT_00_MIN20},
                "gol_ht_00_min20": {
                    "linhagem_sha256": LINHAGEM_GOL_HT_00_MIN20,
                },
                "protecao_tendencias_packball": {
                    "ativa": True,
                    "aprovada": False,
                    "motivo": "amostra_packball_insuficiente",
                },
                "protecao_conversao_gols": {
                    "ativa": True,
                    "aprovada": True,
                    "motivo": "apoio_da_linha_confirmado",
                },
            },
        }

        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            "protecao_tendencias_packball:amostra_packball_insuficiente",
        )

    @patch.dict(
        os.environ,
        {"GOL_HT_SEM_TENDENCIA_PACKBALL_GRUPO_ATIVO": "1"},
        clear=False,
    )
    def test_ht_v3_nao_libera_sem_conversao_historica_confirmada(self):
        candidato = {
            "status": "simulacao",
            "mercado": "gol_ht",
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "features": {
                "exploracao_sombra": {"versao": VERSAO_GOL_HT_00_MIN20},
                "gol_ht_00_min20": {
                    "linhagem_sha256": LINHAGEM_GOL_HT_00_MIN20,
                },
                "protecao_tendencias_packball": {
                    "ativa": True,
                    "aprovada": False,
                    "motivo": "tendencia_packball_indisponivel",
                },
                "protecao_conversao_gols": {
                    "ativa": True,
                    "aprovada": False,
                    "motivo": "historico_da_linha_insuficiente",
                },
            },
        }

        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            "protecao_tendencias_packball:tendencia_packball_indisponivel",
        )

    @patch.dict(
        os.environ,
        {"GOL_HT_HISTORICO_INSUFICIENTE_COM_SOT_GRUPO_ATIVO": "1"},
        clear=False,
    )
    @patch("telegram_alertas.GOL_HT_00_MIN20_GRUPO_ATIVO", True)
    def test_ht_libera_historico_insuficiente_somente_com_dois_sot(self):
        candidato = {
            "status": "simulacao",
            "mercado": "gol_ht",
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "features": {
                "exploracao_sombra": {"versao": VERSAO_GOL_HT_00_MIN20},
                "gol_ht_00_min20": {
                    "linhagem_sha256": LINHAGEM_GOL_HT_00_MIN20,
                },
                "qualidade_dados": 80,
                "chutes_no_gol_total": 2,
                "protecao_tendencias_packball": {
                    "ativa": True,
                    "aprovada": True,
                    "motivo": "tendencia_packball_confirmada",
                },
                "protecao_conversao_gols": {
                    "ativa": True,
                    "aprovada": False,
                    "motivo": "historico_da_linha_insuficiente",
                },
            },
        }

        self.assertIsNone(motivo_suspensao_simulacao(candidato))
        candidato["features"]["chutes_no_gol_total"] = 1
        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            "protecao_conversao_gols:historico_da_linha_insuficiente",
        )

    @patch.dict(
        os.environ,
        {"GOL_HT_HISTORICO_INSUFICIENTE_COM_SOT_GRUPO_ATIVO": "1"},
        clear=False,
    )
    def test_ft_nao_herda_excecao_de_historico_insuficiente(self):
        candidato = {
            "status": "simulacao",
            "mercado": "gol_ft",
            "regra_versao": "sinais-v10e-gol-ft-faixa-global-max82",
            "features": {
                "qualidade_dados": 100,
                "chutes_no_gol_total": 5,
                "protecao_conversao_gols": {
                    "ativa": True,
                    "aprovada": False,
                    "motivo": "historico_da_linha_insuficiente",
                },
            },
        }

        self.assertEqual(
            motivo_suspensao_simulacao(candidato),
            "protecao_conversao_gols:historico_da_linha_insuficiente",
        )

    def test_v2_controle_e_v3_permanecem_sombra(self):
        v2 = self.candidato_v2_controle()
        v3 = {
            **v2,
            "features": {"exploracao_sombra": {
                "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
            }},
        }

        self.assertEqual(
            motivo_suspensao_simulacao(v2),
            "exploracao_sombra_fora_allowlist_simulacao_grupo",
        )
        self.assertEqual(
            motivo_suspensao_simulacao(v3),
            "exploracao_sombra_fora_allowlist_simulacao_grupo",
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "100",
            "LIMITE_GLOBAL_SINAIS_TESTE": "100",
        },
        clear=False,
    )
    def test_v2_controle_nao_envia_ao_grupo(self):
        candidato = self.candidato_v2_controle()
        agora = datetime.now().replace(microsecond=0)
        candidato["features"].update({
            "minuto": 70,
            "decisao_em": agora.isoformat(),
            "estado_observado_em": agora.isoformat(),
            "idade_odds_segundos": 0.0,
        })
        snapshot_id = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?",
            (self.sinal_id,),
        ).fetchone()[0]
        sinal_id = self.banco.salvar_candidatos(
            snapshot_id, [candidato]
        )[0]
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda _url, dados: chamadas.append(dados)
            or resposta_telegram(),
        )

        resultado = alerta.avaliar_e_enviar(
            sinal_id, candidato, self.jogo
        )

        self.assertEqual(
            resultado,
            "exploracao_sombra_fora_allowlist_simulacao_grupo",
        )
        self.assertEqual(self.banco.total_alertas_entregues_hoje(), 0)
        self.assertEqual(self.banco.total_alertas_teste_entregues_hoje(), 0)
        self.assertEqual(chamadas, [])

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "PONTUACAO_MINIMA_SINAL_TESTE": "80",
            "QUALIDADE_MINIMA_SINAL_TESTE": "95",
        },
        clear=False,
    )
    def test_modo_teste_filtra_por_qualidade_minima(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )

        self.assertEqual(
            alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(None), self.jogo
            ),
            "qualidade_teste_insuficiente",
        )
        self.assertEqual(self.banco.total_alertas_teste_entregues_hoje(), 0)
        filtro = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:teste'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(filtro),
            ("filtrado", "qualidade_teste_insuficiente"),
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "30",
        },
        clear=False,
    )
    def test_modo_teste_envia_uma_vez_por_grupo_independente(self):
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append(dados)
            or resposta_telegram(),
        )
        sinal_id, candidato = self.salvar_candidato_teste()
        self.assertEqual(
            alerta.avaliar_e_enviar(sinal_id, candidato, self.jogo),
            "teste_entregue",
        )
        posterior = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-21T12:10:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "70 '",
            }
        )
        repetido_candidato = self.candidato(None)
        repetido_candidato["features"]["minuto"] = 70
        repetido, repetido_candidato = self.salvar_candidato_teste(
            repetido_candidato, posterior
        )
        jogo_posterior = {**self.jogo, "status": "70 '"}

        retorno = alerta.avaliar_e_enviar(
            repetido, repetido_candidato, jogo_posterior
        )

        self.assertEqual(retorno, "duplicado_grupo_teste")
        self.assertEqual(len(chamadas), 1)
        prova = self.banco.conexao.execute(
            """
            SELECT provedor, provedor_destino_id, provedor_mensagem_id,
                   confirmacao_json
            FROM entregas_alertas
            WHERE sinal_id=? AND status='entregue'
            """,
            (sinal_id,),
        ).fetchone()
        confirmacao = json.loads(prova["confirmacao_json"])
        self.assertEqual(prova["provedor"], "telegram")
        self.assertEqual(prova["provedor_destino_id"], "123")
        self.assertGreater(int(prova["provedor_mensagem_id"]), 0)
        self.assertEqual(
            str(confirmacao["message_id"]), prova["provedor_mensagem_id"]
        )
        self.assertEqual(self.banco.total_alertas_teste_entregues_hoje(), 1)

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_resposta_ok_sem_message_id_nao_e_tratada_como_entrega(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: {"ok": True}
        )

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, self.candidato(), self.jogo
        )

        self.assertEqual(resultado, "incerto")
        erro = self.banco.conexao.execute(
            """
            SELECT erro FROM entregas_alertas
            WHERE sinal_id=? AND status='incerto'
            """,
            (self.sinal_id,),
        ).fetchone()[0]
        self.assertIn("sem retornar a mensagem", erro)

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "1",
            "LIMITE_GLOBAL_SINAIS_TESTE": "2",
        },
        clear=False,
    )
    def test_regra_nova_fica_em_sombra_e_nao_consume_cota(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        sinal_id, candidato = self.salvar_candidato_teste()
        self.assertEqual(
            alerta.avaliar_e_enviar(sinal_id, candidato, self.jogo),
            "teste_entregue",
        )

        def novo_sinal(indice, versao):
            snapshot = self.banco.salvar_registro({
                "coletado_em": f"2026-07-21T12:0{indice}:00",
                "url": f"https://packball.com/match/{indice}/live",
                "mandante": f"A{indice}", "visitante": f"B{indice}",
                "placar": "0-0", "status": "60 '",
            })
            candidato = {
                **self.candidato(None), "regra_versao": versao,
            }
            sinal_id = self.banco.salvar_candidatos(
                snapshot, [candidato]
            )[0]
            return sinal_id, candidato

        sinal_v2, candidato_v2 = novo_sinal(2, "sinais-versao-futura")
        self.assertEqual(
            alerta.avaliar_e_enviar(
                sinal_v2, candidato_v2,
                {**self.jogo, "mandante": "A2", "visitante": "B2"},
            ),
            "regra_fora_allowlist_simulacao_grupo",
        )
        self.assertEqual(self.banco.total_alertas_teste_entregues_hoje(), 1)

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "30",
            "LIMITE_GLOBAL_SINAIS_TESTE": "45",
        },
        clear=False,
    )
    def test_leitura_posterior_nao_substitui_primeira_decisao_no_teste(self):
        candidato = self.candidato(None)
        snapshot_inicial = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?",
            (self.sinal_id,),
        ).fetchone()[0]
        self.banco.salvar_candidatos(snapshot_inicial, [candidato])
        posterior = self.banco.salvar_registro({
            "coletado_em": "2026-07-21T12:10:00",
            "url": "https://packball.com/match/1/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": "70 '",
        })
        sinal_posterior = self.banco.salvar_candidatos(
            posterior, [candidato]
        )[0]
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *args: chamadas.append(args)
            or resposta_telegram(),
        )

        resultado = alerta.avaliar_e_enviar(
            sinal_posterior, candidato, self.jogo
        )

        self.assertEqual(resultado, "nao_primeira_decisao_teste")
        self.assertEqual(chamadas, [])
        self.assertFalse(
            self.banco.sinal_e_primeira_decisao_independente(
                sinal_posterior
            )
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
        },
        clear=False,
    )
    def test_notifica_correcao_de_resultado_provisorio_uma_vez(self):
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append((url, dados))
            or resposta_telegram(),
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                "UPDATE sinais SET status='simulacao' WHERE id=?",
                (self.sinal_id,),
            )
            self.banco.conexao.execute(
                """
                INSERT INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, tentativas, provedor,
                    provedor_destino_id, provedor_mensagem_id
                ) VALUES (?, '123:teste', '2026-07-21T12:00:00',
                          '2026-07-21T12:00:00', 'entregue', 1,
                          'telegram', '123', '987')
                """,
                (self.sinal_id,),
            )
            self.banco.conexao.execute(
                """
                INSERT INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior, motivo
                ) VALUES (?, '2026-07-21T12:10:00',
                          '2026-07-21T12:05:00', 'green', 0.85,
                          'placar provisório')
                """,
                (self.sinal_id,),
            )

        primeiro = alerta.enviar_correcoes_resultados_simulacoes()
        segundo = alerta.enviar_correcoes_resultados_simulacoes()

        self.assertEqual(primeiro["entregues"], 1)
        self.assertEqual(segundo["consultados"], 0)
        self.assertTrue(chamadas[0][0].endswith("/editMessageText"))
        self.assertEqual(chamadas[0][1]["message_id"], 987)
        self.assertIn("CORREÇÃO DA ANÁLISE", chamadas[0][1]["text"])
        self.assertIn("Mercado: Over de gols FT", chamadas[0][1]["text"])
        self.assertNotIn("Mercado: gol_ft", chamadas[0][1]["text"])
        self.assertIn("voltou a ficar pendente", chamadas[0][1]["text"])
        prova = self.banco.conexao.execute(
            """
            SELECT notificacao_provedor, notificacao_destino_id,
                   notificacao_mensagem_id, notificacao_confirmacao_json
            FROM revisoes_resultados
            """
        ).fetchone()
        self.assertEqual(prova["notificacao_provedor"], "telegram")
        self.assertEqual(prova["notificacao_destino_id"], "123")
        self.assertIsNone(prova["notificacao_mensagem_id"])
        self.assertEqual(
            json.loads(prova["notificacao_confirmacao_json"]),
            {
                "edicao": True,
                "message_id_origem": 987,
                "ok": True,
                "provedor": "telegram",
            },
        )

    def test_odd_fora_da_faixa_precede_calibracao(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        candidato = self.candidato(None)
        candidato["odd"] = 1.28
        self.assertEqual(
            alerta.avaliar_e_enviar(self.sinal_id, candidato, self.jogo),
            "odd_fora_da_faixa",
        )

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_entrega_calibrada_e_impede_duplicidade(self):
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append((url, dados))
            or resposta_telegram(),
        )
        candidato = self.candidato()
        candidato["odd_oposta"] = 2.05
        self.atualizar_probabilidade_e_rastro(0.8, 2.05)
        self.assertEqual(
            alerta.avaliar_e_enviar(self.sinal_id, candidato, self.jogo),
            "entregue",
        )
        self.assertEqual(
            alerta.avaliar_e_enviar(self.sinal_id, candidato, self.jogo),
            "duplicado",
        )
        self.assertEqual(len(chamadas), 1)
        self.assertIn("Odd justa conservadora", chamadas[0][1]["text"])
        self.assertIn("Valor esperado conservador", chamadas[0][1]["text"])
        self.assertIn(
            "Probabilidade de mercado sem vig", chamadas[0][1]["text"]
        )
        self.assertIn("Margem da casa no par", chamadas[0][1]["text"])
        self.assertIn(
            "Vantagem do modelo contra o mercado sem vig",
            chamadas[0][1]["text"],
        )

    def test_mensagem_proximo_gol_usa_mercado_tres_vias_sem_vig(self):
        candidato = self.candidato(0.75)
        candidato.update({
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 1.70,
            "features": {
                "selecao_mercado": "casa",
                "odds_mercado_sincronizadas": {
                    "casa": 1.70,
                    "visitante": 3.20,
                    "sem_gol": 5.00,
                },
                "mercado_odds_sincronizado": True,
            },
        })

        mensagem = AlertasTelegram._mensagem(candidato, self.jogo)

        self.assertIn("Probabilidade de mercado sem vig", mensagem)
        self.assertIn("Margem da casa no mercado", mensagem)
        self.assertNotIn("Margem da casa no par", mensagem)

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_bloqueia_preco_sem_valor_conservador(self):
        chamadas = []
        self.atualizar_probabilidade_e_rastro(0.50)
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append((url, dados))
            or resposta_telegram(),
        )

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, self.candidato(0.50), self.jogo
        )

        self.assertEqual(
            "valor_esperado_conservador_insuficiente", resultado
        )
        self.assertEqual([], chamadas)
        status = self.banco.conexao.execute(
            "SELECT status FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        self.assertEqual("rejeitado", status)

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_bloqueia_vantagem_sem_par_de_mercado(self):
        chamadas = []
        self.atualizar_probabilidade_e_rastro(0.80, None)
        candidato = self.candidato(0.80)
        candidato.pop("odd_oposta", None)
        candidato.pop("odd_par_sincronizado", None)
        candidato["features"] = {}
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append((url, dados))
            or resposta_telegram(),
        )

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, candidato, self.jogo
        )

        self.assertEqual("referencia_mercado_sem_vig_ausente", resultado)
        self.assertEqual([], chamadas)

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_recusa_calibracao_desativada_antes_do_envio(self):
        chamadas = []
        self.mock_aplicar_calibracao.side_effect = lambda candidato: {
            **candidato,
            "probabilidade_calibrada": None,
            "motivo_sem_calibracao": "modelo_inativo_ou_ausente",
        }
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append(dados)
            or resposta_telegram(),
        )

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, self.candidato(), self.jogo
        )

        self.assertEqual(resultado, "calibracao_atual_invalida")
        self.assertEqual(chamadas, [])

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_bloqueia_rastro_de_valor_adulterado(self):
        linha = self.banco.conexao.execute(
            "SELECT features_json FROM sinais WHERE id=?",
            (self.sinal_id,),
        ).fetchone()
        features = json.loads(linha["features_json"])
        features["valor_mercado_conservador"][
            "valor_esperado_conservador"
        ] = 9.0
        with self.banco.conexao:
            self.banco.conexao.execute(
                "UPDATE sinais SET features_json=? WHERE id=?",
                (json.dumps(features), self.sinal_id),
            )
        transporte = Mock(return_value=resposta_telegram())
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, self.candidato(), self.jogo
        )

        self.assertEqual("rastro_valor_mercado_divergente", resultado)
        transporte.assert_not_called()

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_bloqueia_rastro_de_valor_ausente(self):
        linha = self.banco.conexao.execute(
            "SELECT features_json FROM sinais WHERE id=?",
            (self.sinal_id,),
        ).fetchone()
        features = json.loads(linha["features_json"])
        features.pop("valor_mercado_conservador")
        with self.banco.conexao:
            self.banco.conexao.execute(
                "UPDATE sinais SET features_json=? WHERE id=?",
                (json.dumps(features), self.sinal_id),
            )
        transporte = Mock(return_value=resposta_telegram())
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, self.candidato(), self.jogo
        )

        self.assertEqual("rastro_valor_mercado_ausente", resultado)
        transporte.assert_not_called()

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_recusa_probabilidade_alterada_apos_decisao(self):
        self.mock_aplicar_calibracao.side_effect = lambda candidato: {
            **candidato, "probabilidade_calibrada": 0.76,
        }
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: self.fail("não deveria enviar"),
        )

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, self.candidato(0.80), self.jogo
        )

        self.assertEqual(resultado, "calibracao_alterada")

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_recusa_probabilidade_divergente_do_sqlite(self):
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: self.fail("não deveria enviar"),
        )

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, self.candidato(0.79), self.jogo
        )

        self.assertEqual(resultado, "sinal_persistido_divergente")
        self.mock_aplicar_calibracao.assert_not_called()

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_recusa_candidato_divergente_do_sqlite(self):
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: self.fail("não deveria enviar"),
        )
        candidato = self.candidato()
        candidato["linha"] = 2.5

        resultado = alerta.avaliar_e_enviar(
            self.sinal_id, candidato, self.jogo
        )

        self.assertEqual(resultado, "sinal_persistido_divergente")
        self.mock_aplicar_calibracao.assert_not_called()

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_gateway_recusa_sinal_persistido_sem_fingerprint(self):
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO sinais (
                    partida_id, snapshot_id, criado_em, mercado, linha, odd,
                    pontuacao_tecnica, probabilidade_calibrada,
                    regra_versao, status
                )
                SELECT partida_id, snapshot_id,
                       datetime(criado_em, '-1 second'), mercado, linha, odd,
                       pontuacao_tecnica, probabilidade_calibrada,
                       regra_versao, 'aprovado'
                FROM sinais WHERE id=?
                """,
                (self.sinal_id,),
            )
            sinal_legado_id = cursor.lastrowid
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: self.fail("não deveria enviar"),
        )

        resultado = alerta.avaliar_e_enviar(
            sinal_legado_id, self.candidato(), self.jogo
        )

        self.assertEqual(resultado, "sinal_sem_linhagem_valida")
        self.mock_aplicar_calibracao.assert_not_called()
        bloqueio = self.banco.conexao.execute(
            """
            SELECT erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:oficial' AND status='bloqueado'
            """,
            (sinal_legado_id,),
        ).fetchone()
        self.assertEqual(bloqueio["erro"], "sinal_sem_linhagem_valida")

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "LIMITE_REDS_CONSECUTIVOS_OFICIAIS": "3",
        },
        clear=False,
    )
    def test_circuit_breaker_bloqueia_oficial_apos_tres_reds(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        risco = {
            "reds_consecutivos_24h": 3,
            "perda_realizada_hoje": 2.0,
        }
        with patch.object(
            self.banco, "resumir_risco_alertas_oficiais", return_value=risco
        ):
            resultado = alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(), self.jogo
            )
        self.assertEqual(resultado, "circuit_breaker_reds")

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "LIMITE_PERDA_DIARIA_OFICIAL": "3",
        },
        clear=False,
    )
    def test_circuit_breaker_bloqueia_oficial_por_perda_diaria(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        risco = {
            "reds_consecutivos_24h": 1,
            "perda_realizada_hoje": 3.0,
        }
        with patch.object(
            self.banco, "resumir_risco_alertas_oficiais", return_value=risco
        ):
            resultado = alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(), self.jogo
            )
            self.assertEqual(resultado, "circuit_breaker_perda_diaria")

    def test_entrega_oficial_incerta_bloqueia_nova_exposicao(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "canal-oficial", "enviando"
        )
        transporte = Mock()
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "canal-oficial",
            "SINAIS_TESTE_ATIVO": "0",
        }):
            alertas = AlertasTelegram(
                self.banco, transporte=transporte
            )
            resultado = alertas.avaliar_e_enviar(
                self.sinal_id, self.candidato(), self.jogo
            )

        self.assertEqual(
            resultado, "circuit_breaker_entrega_incerta"
        )
        transporte.assert_not_called()

    def test_entrega_oficial_incerta_nao_bloqueia_simulacao(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "canal-oficial", "enviando"
        )
        transporte = Mock(return_value=resposta_telegram())
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "canal-teste",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "100",
            "LIMITE_GLOBAL_SINAIS_TESTE": "100",
        }):
            alertas = AlertasTelegram(
                self.banco, transporte=transporte
            )
            sinal_teste_id, candidato = self.salvar_candidato_teste()
            resultado = alertas.avaliar_e_enviar(
                sinal_teste_id, candidato, self.jogo
            )

        self.assertEqual(resultado, "teste_entregue")
        transporte.assert_called_once()

    def test_timeout_oficial_fica_incerto_sem_retry_automatico(self):
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "canal-oficial",
            "SINAIS_TESTE_ATIVO": "0",
        }):
            alertas = AlertasTelegram(
                self.banco,
                transporte=lambda *_: (_ for _ in ()).throw(
                    TimeoutError("resposta não recebida")
                ),
            )
            resultado = alertas.avaliar_e_enviar(
                self.sinal_id, self.candidato(), self.jogo
            )

        self.assertEqual(resultado, "incerto")
        estados = self.banco.conexao.execute(
            """
            SELECT status, reserva_token FROM entregas_alertas
            WHERE sinal_id=? ORDER BY id
            """,
            (self.sinal_id,),
        ).fetchall()
        self.assertEqual(
            [item["status"] for item in estados],
            ["incerto"],
        )
        self.assertTrue(estados[0]["reserva_token"])
        self.assertEqual(
            self.banco.alertas_com_erro_para_reenvio(), []
        )
        self.assertTrue(self.banco.possui_entrega_oficial_incerta())

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_nao_envia_abaixo_de_75_por_cento(self):
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append(dados)
            or resposta_telegram(),
        )
        self.atualizar_probabilidade_e_rastro(0.74)
        self.assertEqual(
            alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(0.74), self.jogo
            ),
            "aviso_insuficiente",
        )
        self.assertIn("NÃO É ENTRADA", chamadas[0]["text"])

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_bloqueia_repeticao_oficial_na_mesma_partida_e_regra(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        candidato = self.candidato()
        self.assertEqual(
            alerta.avaliar_e_enviar(self.sinal_id, candidato, self.jogo),
            "entregue",
        )
        snapshot = self.banco.salvar_registro(
            {
                "coletado_em": "2099-01-01T00:01:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "61 '",
            }
        )
        novo_id = self.banco.salvar_candidatos(snapshot, [candidato])[0]
        self.assertEqual(
            alerta.avaliar_e_enviar(novo_id, candidato, self.jogo),
            "sinal_persistido_nao_aprovado",
        )
        self.assertTrue(
            self.banco.alerta_oficial_ja_entregue_no_grupo_independente(
                novo_id
            )
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "LIMITE_DIARIO_SINAIS": "0",
        },
        clear=False,
    )
    def test_respeita_limite_diario(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        self.assertEqual(
            alerta.avaliar_e_enviar(
                self.sinal_id, self.candidato(), self.jogo
            ),
            "limite_diario",
        )

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_cartao_vermelho_cancela_sinal_pendente_entregue(self):
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append((url, dados))
            or resposta_telegram(),
        )
        candidato = self.candidato()
        alerta.avaliar_e_enviar(self.sinal_id, candidato, self.jogo)
        jogo = {**self.jogo, "url": "https://packball.com/match/1/live"}
        cancelados = alerta.cancelar_por_evento(
            jogo, {"cartao_vermelho": True}
        )
        self.assertEqual(cancelados, 1)
        self.assertTrue(chamadas[-1][0].endswith("/editMessageText"))
        self.assertGreater(int(chamadas[-1][1]["message_id"]), 0)
        self.assertIn("CENÁRIO INVALIDADO", chamadas[-1][1]["text"])

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_bloqueia_odd_fora_da_faixa_de_risco(self):
        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        candidato = self.candidato()
        candidato["odd"] = 4.0
        self.assertEqual(
            alerta.avaliar_e_enviar(self.sinal_id, candidato, self.jogo),
            "odd_fora_da_faixa",
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
        },
        clear=False,
    )
    def test_pre_envio_expirado_nao_transporta_nem_entra_no_backtest(self):
        instante = datetime.now().replace(microsecond=0) - timedelta(
            seconds=121
        )
        candidato, jogo = self.candidato_teste_com_instante(instante)
        snapshot_id = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        sinal_id = self.banco.salvar_candidatos(
            snapshot_id, [candidato]
        )[0]
        transporte = Mock()
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(sinal_id, candidato, jogo)

        self.assertEqual(resultado, "revalidacao_pre_envio_leitura_expirada")
        transporte.assert_not_called()
        sinal = self.banco.conexao.execute(
            "SELECT status, motivos_json FROM sinais WHERE id=?", (sinal_id,)
        ).fetchone()
        self.assertEqual(sinal["status"], "rejeitado")
        self.assertIn(
            "bloqueio:revalidacao_pre_envio_leitura_expirada",
            sinal["motivos_json"],
        )
        self.assertEqual(self.banco.conexao.execute(
            "SELECT COUNT(*) FROM resultados_sinais WHERE sinal_id=?",
            (sinal_id,),
        ).fetchone()[0], 0)

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
        },
        clear=False,
    )
    def test_pre_envio_asiatico_bloqueia_odd_com_mais_de_60_segundos(self):
        agora = datetime.now().replace(microsecond=0)
        candidato = {
            **self.candidato(None),
            "mercado": "escanteios_ft_asiatico",
            "linha": "10.5",
            "odd": 1.65,
            "regra_versao": VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
            "features": {
                "minuto": 60,
                "decisao_em": agora.isoformat(),
                "estado_observado_em": agora.isoformat(),
                "idade_odds_segundos": 61.0,
                "fonte_odds": "api_football",
            },
        }
        snapshot_id = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        sinal_id = self.banco.salvar_candidatos(snapshot_id, [candidato])[0]
        transporte = Mock()
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(
            sinal_id, candidato, self.jogo
        )

        self.assertEqual(resultado, "revalidacao_pre_envio_odds_expiradas")
        transporte.assert_not_called()

    def test_mensagem_asiatico_exibe_fonte_e_bookmaker_nao_informado(self):
        candidato = {
            **self.candidato(None),
            "mercado": "escanteios_ft_asiatico",
            "linha": "10.5",
            "odd": 1.65,
            "fonte_odds": "api_football",
            "bookmaker_odds": None,
        }
        mensagem = AlertasTelegram._mensagem_teste(candidato, {
            **self.jogo, "liga": "Eredivisie",
        })
        self.assertIn(
            "Fonte da odd: API-Football — bookmaker não informado",
            mensagem,
        )

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "100",
            "LIMITE_GLOBAL_SINAIS_TESTE": "100",
        },
        clear=False,
    )
    def test_nova_leitura_fresca_pode_substituir_decisao_expirada(self):
        instante_antigo = datetime.now().replace(microsecond=0) - timedelta(
            seconds=121
        )
        antigo, jogo_antigo = self.candidato_teste_com_instante(
            instante_antigo
        )
        snapshot_antigo = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        sinal_antigo = self.banco.salvar_candidatos(
            snapshot_antigo, [antigo]
        )[0]
        transporte = Mock(return_value=resposta_telegram())
        alerta = AlertasTelegram(self.banco, transporte=transporte)
        self.assertEqual(
            alerta.avaliar_e_enviar(sinal_antigo, antigo, jogo_antigo),
            "revalidacao_pre_envio_leitura_expirada",
        )

        agora = datetime.now().replace(microsecond=0)
        snapshot_novo = self.banco.salvar_registro({
            "coletado_em": (agora + timedelta(seconds=1)).isoformat(),
            "url": "https://packball.com/match/1/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": "61 '",
        })
        novo, jogo_novo = self.candidato_teste_com_instante(
            agora, minuto=61
        )
        sinal_novo = self.banco.salvar_candidatos(
            snapshot_novo, [novo]
        )[0]

        self.assertTrue(
            self.banco.sinal_e_primeira_decisao_independente(sinal_novo)
        )
        self.assertEqual(
            alerta.avaliar_e_enviar(sinal_novo, novo, jogo_novo),
            "teste_entregue",
        )
        transporte.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
        },
        clear=False,
    )
    def test_pre_envio_bloqueia_minuto_projetado_acima_do_limite(self):
        instante = datetime.now().replace(microsecond=0) - timedelta(
            seconds=61
        )
        snapshot = self.banco.salvar_registro({
            "coletado_em": instante.isoformat(),
            "url": "https://packball.com/match/2/live",
            "mandante": "C", "visitante": "D",
            "placar": "1-0", "status": "74 '",
        })
        candidato, jogo = self.candidato_teste_com_instante(
            instante, minuto=74, status_jogo="74 '"
        )
        sinal_id = self.banco.salvar_candidatos(snapshot, [candidato])[0]
        transporte = Mock()
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(sinal_id, candidato, {
            **jogo, "mandante": "C", "visitante": "D", "placar": "1-0",
        })

        self.assertEqual(resultado, "revalidacao_pre_envio_minuto_excedido")
        transporte.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
        },
        clear=False,
    )
    def test_pre_envio_snapshot_mais_novo_invalida_origem(self):
        agora = datetime.now().replace(microsecond=0)
        candidato, jogo = self.candidato_teste_com_instante(agora)
        snapshot_origem = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        sinal_id = self.banco.salvar_candidatos(
            snapshot_origem, [candidato]
        )[0]
        self.banco.salvar_registro({
            "coletado_em": (agora + timedelta(seconds=1)).isoformat(),
            "url": "https://packball.com/match/1/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": "61 '",
        })
        transporte = Mock()
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(sinal_id, candidato, jogo)

        self.assertEqual(
            resultado, "revalidacao_pre_envio_snapshot_substituido"
        )
        transporte.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
        },
        clear=False,
    )
    def test_pre_envio_recusa_identidade_de_partida_divergente(self):
        agora = datetime.now().replace(microsecond=0)
        candidato, jogo = self.candidato_teste_com_instante(agora)
        snapshot = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        sinal_id = self.banco.salvar_candidatos(snapshot, [candidato])[0]
        jogo["mandante"] = "Outro time"
        transporte = Mock()
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resultado = alerta.avaliar_e_enviar(sinal_id, candidato, jogo)

        self.assertEqual(
            resultado,
            "revalidacao_pre_envio_identidade_partida_divergente",
        )
        transporte.assert_not_called()
        self.assertEqual(self.banco.conexao.execute(
            "SELECT status FROM sinais WHERE id=?", (sinal_id,)
        ).fetchone()[0], "rejeitado")

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "QUALIDADE_MINIMA_SINAL_TESTE": "0",
            "LIMITE_DIARIO_SINAIS_TESTE": "100",
            "LIMITE_GLOBAL_SINAIS_TESTE": "100",
        },
        clear=False,
    )
    def test_mensagem_usa_candidato_e_partida_persistidos(self):
        agora = datetime.now().replace(microsecond=0)
        candidato, jogo = self.candidato_teste_com_instante(agora)
        snapshot = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        sinal_id = self.banco.salvar_candidatos(snapshot, [candidato])[0]
        motivos_persistidos = list(candidato["motivos"])
        candidato["motivos"] = ["conteudo_forjado"]
        candidato["qualidade_dados"] = 1
        capturado = {}

        def mensagem_autoridade(candidato_mensagem, jogo_mensagem):
            capturado["candidato"] = {
                **candidato_mensagem,
                "motivos": list(candidato_mensagem.get("motivos") or []),
                "features": dict(candidato_mensagem.get("features") or {}),
            }
            capturado["jogo"] = dict(jogo_mensagem)
            return "mensagem persistida"

        alerta = AlertasTelegram(
            self.banco, transporte=lambda *_: resposta_telegram()
        )
        with patch.object(
            AlertasTelegram,
            "_mensagem_teste",
            side_effect=mensagem_autoridade,
        ):
            resultado = alerta.avaliar_e_enviar(
                sinal_id, candidato, jogo
            )

        self.assertEqual(resultado, "teste_entregue")
        self.assertEqual(
            capturado["candidato"]["motivos"], motivos_persistidos
        )
        self.assertEqual(capturado["candidato"]["qualidade_dados"], 90)
        self.assertEqual(
            capturado["jogo"]["url"],
            "https://packball.com/match/1/live",
        )
        self.assertEqual(capturado["jogo"]["mandante"], "A")

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "123",
            "SINAIS_TESTE_ATIVO": "1",
        },
        clear=False,
    )
    def test_pre_envio_nao_declara_expiracao_se_update_falhou(self):
        agora = datetime.now().replace(microsecond=0)
        candidato, jogo = self.candidato_teste_com_instante(agora)
        snapshot = self.banco.conexao.execute(
            "SELECT snapshot_id FROM sinais WHERE id=?", (self.sinal_id,)
        ).fetchone()[0]
        sinal_id = self.banco.salvar_candidatos(snapshot, [candidato])[0]
        jogo["visitante"] = "Outro visitante"
        alerta = AlertasTelegram(self.banco, transporte=Mock())

        with patch.object(
            self.banco, "expirar_sinal_pre_envio", return_value=False
        ):
            resultado = alerta.avaliar_e_enviar(
                sinal_id, candidato, jogo
            )

        self.assertEqual(
            resultado, "revalidacao_pre_envio_expiracao_concorrente"
        )
        registro = self.banco.conexao.execute(
            """
            SELECT status, erro FROM entregas_alertas
            WHERE sinal_id=? AND canal='gateway:pre_envio'
            """,
            (sinal_id,),
        ).fetchone()
        self.assertEqual(registro["status"], "bloqueado")
        self.assertEqual(registro["erro"], resultado)
        self.assertEqual(self.banco.conexao.execute(
            "SELECT status FROM sinais WHERE id=?", (sinal_id,)
        ).fetchone()[0], "aprovado")

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_TESTE": "canal-teste",
            "SINAIS_TESTE_ATIVO": "1",
            "LIMITE_DIARIO_SINAIS_TESTE": "100",
            "LIMITE_GLOBAL_SINAIS_TESTE": "100",
        },
        clear=False,
    )
    def test_retry_teste_nao_se_autobloqueia_com_proprio_tentando(self):
        sinal_id, _ = self.salvar_candidato_teste()
        tentativa = (
            datetime.now().replace(microsecond=0) - timedelta(minutes=3)
        ).isoformat()
        self.banco.registrar_entrega_alerta(
            sinal_id,
            "canal-teste:teste",
            "erro",
            "falha_confirmada",
            tentativa,
        )
        transporte = Mock(return_value=resposta_telegram())
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        resumo = alerta.reenviar_pendentes()

        self.assertEqual(resumo["consultados"], 1)
        self.assertEqual(resumo["entregues"], 1, resumo)
        self.assertEqual(resumo["cancelados"], 0)
        transporte.assert_called_once()
        estados = self.banco.conexao.execute(
            """
            SELECT status FROM entregas_alertas
            WHERE sinal_id=? ORDER BY id
            """,
            (sinal_id,),
        ).fetchall()
        self.assertEqual(
            [item["status"] for item in estados],
            ["entregue"],
        )

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_reenvia_erro_persistente_e_marca_como_recuperado(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "123",
            "erro",
            "timeout",
            "2000-01-01T00:00:00",
        )
        chamadas = []
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda url, dados: chamadas.append(dados)
            or resposta_telegram(),
        )
        resumo = alerta.reenviar_pendentes()
        self.assertEqual(resumo["entregues"], 1, resumo)
        self.assertEqual(len(chamadas), 1)
        estados = self.banco.conexao.execute(
            "SELECT status FROM entregas_alertas ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [item[0] for item in estados],
            ["entregue"],
        )

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_retry_e_cancelado_se_calibracao_deixou_de_ser_valida(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "123", "erro", "timeout", "2000-01-01T00:00:00"
        )
        self.mock_aplicar_calibracao.side_effect = lambda candidato: {
            **candidato, "probabilidade_calibrada": None,
        }
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: self.fail("não deveria reenviar"),
        )

        resumo = alerta.reenviar_pendentes()

        self.assertEqual(resumo["cancelados"], 1)
        self.assertEqual(resumo["entregues"], 0)
        estado = self.banco.conexao.execute(
            "SELECT status FROM entregas_alertas WHERE sinal_id=?",
            (self.sinal_id,),
        ).fetchone()[0]
        self.assertEqual(estado, "cancelado")

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_timeout_durante_reenvio_para_retries_automaticos(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "123",
            "erro",
            "timeout",
            "2000-01-01T00:00:00",
        )
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: (_ for _ in ()).throw(TimeoutError()),
        )
        resumo = alerta.reenviar_pendentes()
        self.assertEqual(resumo["incertos"], 1, resumo)
        self.assertEqual(
            alerta.reenviar_pendentes()["consultados"], 0
        )
        estados = self.banco.conexao.execute(
            """
            SELECT status FROM entregas_alertas ORDER BY id
            """
        ).fetchall()
        self.assertEqual(
            [item["status"] for item in estados],
            ["incerto"],
        )

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_nao_reenvia_sinal_ja_resolvido(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "123",
            "erro",
            "timeout",
            "2000-01-01T00:00:00",
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades
                ) VALUES (?, datetime('now', 'localtime'), 'green', 0.8)
                """,
                (self.sinal_id,),
            )
        alerta = AlertasTelegram(
            self.banco,
            transporte=lambda *_: self.fail("não deveria reenviar"),
        )
        self.assertEqual(alerta.reenviar_pendentes()["consultados"], 0)

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_TESTE": "123"},
        clear=False,
    )
    def test_timeout_resultado_simulado_fica_incerto_sem_retry(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "123:teste", "entregue"
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    snapshot_id_liquidacao, fonte_resultado
                )
                SELECT ?, '2026-08-13T20:00:00', 'green', 0.85,
                       snapshot_id, 'packball'
                FROM sinais WHERE id=?
                """,
                (self.sinal_id, self.sinal_id),
            )
        transporte = Mock(side_effect=TimeoutError("resposta nao recebida"))
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        primeiro = alerta.enviar_resultados_simulacoes()
        segundo = alerta.enviar_resultados_simulacoes()

        self.assertEqual(primeiro["consultados"], 1)
        self.assertEqual(primeiro["erros"], 1)
        self.assertEqual(segundo["consultados"], 0)
        transporte.assert_called_once()
        claim = self.banco.conexao.execute(
            """
            SELECT status, reserva_token FROM entregas_alertas
            WHERE sinal_id=? AND canal='123:teste:resultado'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(claim["status"], "incerto")
        self.assertTrue(claim["reserva_token"])
        self.assertEqual(self.banco.alertas_com_erro_para_reenvio(), [])

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_TESTE": "123"},
        clear=False,
    )
    def test_timeout_edicao_resultado_reenvia_mesma_edicao_sem_duplicar(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id,
            "123:teste",
            "entregue",
            provedor="telegram",
            provedor_destino_id="123",
            provedor_mensagem_id="987",
            confirmacao={"ok": True, "message_id": 987},
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    snapshot_id_liquidacao, fonte_resultado
                )
                SELECT ?, '2026-08-13T20:00:00', 'green', 0.85,
                       snapshot_id, 'packball'
                FROM sinais WHERE id=?
                """,
                (self.sinal_id, self.sinal_id),
            )
        transporte = Mock(side_effect=[
            TimeoutError("resposta nao recebida"),
            resposta_telegram(),
        ])
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        primeiro = alerta.enviar_resultados_simulacoes()
        alerta._validar_operacao_oficial = Mock(
            return_value="operacao_oficial_degradada"
        )
        segundo = alerta.enviar_resultados_simulacoes()

        self.assertEqual(primeiro["erros"], 1)
        self.assertEqual(segundo["recuperados"], 1)
        self.assertEqual(segundo["consultados"], 0)
        alerta._validar_operacao_oficial.assert_not_called()
        self.assertEqual(transporte.call_count, 2)
        for chamada in transporte.call_args_list:
            self.assertTrue(chamada.args[0].endswith("/editMessageText"))
            self.assertEqual(chamada.args[1]["message_id"], 987)
        claim = self.banco.conexao.execute(
            """
            SELECT status, tentativas, provedor_mensagem_id,
                   confirmacao_json
            FROM entregas_alertas
            WHERE sinal_id=? AND canal='123:teste:resultado'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(claim["status"], "entregue")
        self.assertEqual(claim["tentativas"], 2)
        self.assertIsNone(claim["provedor_mensagem_id"])
        confirmacao = json.loads(claim["confirmacao_json"])
        self.assertTrue(confirmacao["edicao"])
        self.assertTrue(confirmacao["retry_idempotente"])
        self.assertEqual(confirmacao["message_id_origem"], 987)

    def test_transporte_aceita_edicao_telegram_ja_aplicada(self):
        corpo = BytesIO(json.dumps({
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: message is not modified",
        }).encode("utf-8"))
        erro = HTTPError(
            "https://api.telegram.org/botx/editMessageText",
            400,
            "Bad Request",
            hdrs=None,
            fp=corpo,
        )
        with patch("telegram_alertas.urlopen", side_effect=erro):
            resposta = _transporte_padrao(
                "https://api.telegram.org/botx/editMessageText",
                {"chat_id": "123", "message_id": 987, "text": "GREEN"},
            )
        erro.close()

        self.assertTrue(resposta["ok"])
        self.assertTrue(resposta["edicao_idempotente"])
        self.assertEqual(resposta["result"]["message_id"], 987)

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_timeout_resultado_oficial_fica_incerto_sem_retry(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "123", "entregue"
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    snapshot_id_liquidacao, fonte_resultado
                )
                SELECT ?, '2026-08-13T20:00:00', 'red', -1.0,
                       snapshot_id, 'api_football'
                FROM sinais WHERE id=?
                """,
                (self.sinal_id, self.sinal_id),
            )
        transporte = Mock(side_effect=TimeoutError("resposta nao recebida"))
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        primeiro = alerta.enviar_resultados_oficiais()
        segundo = alerta.enviar_resultados_oficiais()

        self.assertEqual(primeiro["consultados"], 1)
        self.assertEqual(primeiro["erros"], 1)
        self.assertEqual(segundo["consultados"], 0)
        transporte.assert_called_once()
        claim = self.banco.conexao.execute(
            """
            SELECT status, reserva_token FROM entregas_alertas
            WHERE sinal_id=? AND canal='123:resultado'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(claim["status"], "incerto")
        self.assertTrue(claim["reserva_token"])

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_GOLS": "123"},
        clear=False,
    )
    def test_timeout_cancelamento_fica_incerto_sem_retry(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "123", "entregue"
        )
        transporte = Mock(side_effect=TimeoutError("resposta nao recebida"))
        alerta = AlertasTelegram(self.banco, transporte=transporte)
        jogo = {
            **self.jogo,
            "url": "https://packball.com/match/1/live",
        }

        primeiro = alerta.cancelar_por_evento(
            jogo, {"cartao_vermelho": True}
        )
        segundo = alerta.cancelar_por_evento(
            jogo, {"cartao_vermelho": True}
        )

        self.assertEqual(primeiro, 0)
        self.assertEqual(segundo, 0)
        transporte.assert_called_once()
        claim = self.banco.conexao.execute(
            """
            SELECT status, reserva_token FROM entregas_alertas
            WHERE sinal_id=? AND canal='123:cancelamento'
            """,
            (self.sinal_id,),
        ).fetchone()
        self.assertEqual(claim["status"], "incerto")
        self.assertTrue(claim["reserva_token"])

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_TESTE": "123"},
        clear=False,
    )
    def test_timeout_correcao_fica_incerto_sem_retry(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "123:teste", "entregue"
        )
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior, motivo
                ) VALUES (?, '2026-08-13T20:01:00',
                          '2026-08-13T20:00:00', 'green', 0.85,
                          'resultado provisorio')
                """,
                (self.sinal_id,),
            )
        revisao_id = cursor.lastrowid
        transporte = Mock(side_effect=TimeoutError("resposta nao recebida"))
        alerta = AlertasTelegram(self.banco, transporte=transporte)

        primeiro = alerta.enviar_correcoes_resultados_simulacoes()
        segundo = alerta.enviar_correcoes_resultados_simulacoes()

        self.assertEqual(primeiro["consultados"], 1)
        self.assertEqual(primeiro["erros"], 1)
        self.assertEqual(segundo["consultados"], 0)
        transporte.assert_called_once()
        revisao = self.banco.conexao.execute(
            """
            SELECT notificacao_status, notificacao_erro
            FROM revisoes_resultados WHERE id=?
            """,
            (revisao_id,),
        ).fetchone()
        self.assertEqual(revisao["notificacao_status"], "incerto")
        self.assertIn("resposta nao recebida", revisao["notificacao_erro"])
        claim = self.banco.conexao.execute(
            """
            SELECT status, reserva_token FROM entregas_alertas
            WHERE sinal_id=? AND canal=?
            """,
            (
                self.sinal_id,
                f"123:teste:correcao:{revisao_id}",
            ),
        ).fetchone()
        self.assertEqual(claim["status"], "incerto")
        self.assertTrue(claim["reserva_token"])

    @patch.dict(
        os.environ,
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID_TESTE": "123"},
        clear=False,
    )
    def test_crash_apos_claim_resultado_nao_reenvia_no_reinicio(self):
        self.banco.registrar_entrega_alerta(
            self.sinal_id, "123:teste", "entregue"
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    snapshot_id_liquidacao, fonte_resultado
                )
                SELECT ?, '2026-08-13T20:00:00', 'green', 0.85,
                       snapshot_id, 'packball'
                FROM sinais WHERE id=?
                """,
                (self.sinal_id, self.sinal_id),
            )
        item = self.banco.resultados_simulacoes_nao_notificados()[0]
        processo_interrompido = BancoMonitor(self.caminho)
        try:
            token = processo_interrompido.reservar_notificacao_resultado(
                self.sinal_id, "123:teste", item
            )
            self.assertTrue(token)
        finally:
            processo_interrompido.fechar()

        reiniciado = BancoMonitor(self.caminho)
        transporte = Mock(return_value=resposta_telegram())
        try:
            alerta = AlertasTelegram(reiniciado, transporte=transporte)
            resumo = alerta.enviar_resultados_simulacoes()
            self.assertEqual(resumo["consultados"], 0)
            transporte.assert_not_called()
            claim = reiniciado.conexao.execute(
                """
                SELECT status FROM entregas_alertas
                WHERE sinal_id=? AND canal='123:teste:resultado'
                """,
                (self.sinal_id,),
            ).fetchone()
            self.assertEqual(claim["status"], "enviando")
        finally:
            reiniciado.fechar()


if __name__ == "__main__":
    unittest.main()
