import unittest
from datetime import datetime, timedelta
from pathlib import Path

from backtest import (
    AvaliadorBacktest,
    calcular_metricas,
    liquidar_over_asiatico,
    metricas_segmentadas,
    reabrir_resultados_provisorios,
)
from banco import BancoMonitor
from contrafactual_protecoes import converter_em_contrafactual


class BacktestTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_backtest.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.avaliador = AvaliadorBacktest(self.banco)
        self.inicio = datetime(2026, 7, 20, 12, 0, 0)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def registro(self, instante, placar, escanteios, status="60 '"):
        return {
            "coletado_em": instante,
            "url": "https://packball.com/match/1/live",
            "mandante": "A",
            "visitante": "B",
            "placar": placar,
            "status": status,
            "estatisticas": {"Escanteios": escanteios},
        }

    def candidato(self, mercado, linha=None, odd=2.0):
        return {
            "mercado": mercado,
            "linha": linha,
            "odd": odd,
            "pontuacao_tecnica": 80,
            "probabilidade_calibrada": None,
            "regra_versao": "sinais-v1",
            "motivos": [],
            "bloqueios": [],
            "status": "aprovado",
        }

    def test_resolve_green_de_gol_somente_no_encerramento(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(inicial, [self.candidato("gol_ft")])
        posterior = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-0", "1-1", status="Finalizado",
            )
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 1)
        self.assertEqual(self.avaliador.metricas()["greens"], 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT snapshot_id_liquidacao, fonte_resultado
            FROM resultados_sinais
            """
        ).fetchone()
        self.assertEqual(tuple(resultado), (posterior, "packball"))

    def test_simulacao_liquida_sem_inflar_amostra_oficial(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        ids = self.banco.salvar_candidatos(
            inicial,
            [self.candidato("gol_ft"), self.candidato("gol_ft")],
        )
        self.assertTrue(self.banco.marcar_sinal_como_simulacao(ids[1]))
        posterior = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-0", "1-1", status="Finalizado",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 2)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT resultado FROM resultados_sinais WHERE sinal_id=?",
                (ids[1],),
            ).fetchone()[0],
            "green",
        )
        metricas = self.avaliador.metricas()
        self.assertEqual(metricas["amostra"], 1)
        self.assertEqual(metricas["greens"], 1)

    def test_contrafactual_liquida_sem_entrar_na_calibracao_oficial(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        candidato = self.candidato("gol_ht", linha=0.5, odd=1.80)
        self.assertTrue(
            converter_em_contrafactual(
                candidato,
                "protecao_tendencias_packball",
                "amostra_packball_insuficiente",
            )
        )
        sinal_id = self.banco.salvar_candidatos(
            inicial, [candidato]
        )[0]
        posterior = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-0", "1-1", status="Intervalo",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 1)
        resultado = self.banco.conexao.execute(
            "SELECT resultado FROM resultados_sinais WHERE sinal_id=?",
            (sinal_id,),
        ).fetchone()[0]
        self.assertEqual(resultado, "green")
        self.assertEqual(self.avaliador.metricas("gol_ht")["amostra"], 0)

    def test_resolve_red_ao_final_sem_cruzar_linha(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "1-0", "3-2")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("proximo_escanteio", linha=8.5)]
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-0",
                "4-3",
                status="Finalizado",
            )
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(final), 1)
        self.assertEqual(self.avaliador.metricas()["reds"], 1)

    def test_nao_registra_red_antes_do_encerramento(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=2.5)]
        )
        posterior = self.banco.salvar_registro(
            self.registro(self.inicio + timedelta(minutes=2), "1-0", "1-1")
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 0)
        self.assertEqual(self.avaliador.metricas()["amostra"], 0)

    def test_confirma_green_ao_vivo_sem_liquidar_resultado_oficial(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        sinal_id = self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=1.5, odd=1.8)]
        )[0]
        atual = self.registro(
            self.inicio + timedelta(minutes=5), "1-1", "1-1", status="65 '"
        )
        atual["qualidade"] = {
            "pontuacao": 100,
            "fontes": ["packball"],
            "apto_para_liquidacao": True,
        }
        snapshot_atual = self.banco.salvar_registro(atual)

        confirmacao = self.avaliador.confirmar_green_irreversivel(sinal_id)

        self.assertEqual(confirmacao["snapshot_id"], snapshot_atual)
        self.assertEqual(confirmacao["placar"], "1-1")
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM resultados_sinais"
            ).fetchone()[0],
            0,
        )

    def test_meio_green_asiatico_nao_vira_green_antecipado(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        sinal_id = self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=2.75, odd=1.8)]
        )[0]
        atual = self.registro(
            self.inicio + timedelta(minutes=5), "2-1", "1-1", status="65 '"
        )
        atual["qualidade"] = {
            "pontuacao": 100,
            "fontes": ["packball"],
            "apto_para_liquidacao": True,
        }
        self.banco.salvar_registro(atual)

        self.assertIsNone(
            self.avaliador.confirmar_green_irreversivel(sinal_id)
        )

        atual["coletado_em"] = self.inicio + timedelta(minutes=6)
        atual["placar"] = "3-1"
        self.banco.salvar_registro(atual)
        self.assertIsNotNone(
            self.avaliador.confirmar_green_irreversivel(sinal_id)
        )

    def test_leitura_parcial_nao_confirma_green_antecipado(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        sinal_id = self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=0.5, odd=1.8)]
        )[0]
        atual = self.registro(
            self.inicio + timedelta(minutes=5), "1-0", "1-1", status="65 '"
        )
        atual["qualidade"] = {
            "pontuacao": 40,
            "fontes": ["packball"],
            "apto_para_liquidacao": False,
        }
        self.banco.salvar_registro(atual)

        self.assertIsNone(
            self.avaliador.confirmar_green_irreversivel(sinal_id)
        )

    def test_leitura_com_fonte_incompleta_nao_altera_green_red(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=0.5)]
        )
        registro_final = self.registro(
            self.inicio + timedelta(minutes=30),
            "1-0", "1-1", status="Finalizado",
        )
        registro_final["qualidade"] = {
            "pontuacao": 40,
            "fontes": ["packball"],
            "apto_para_liquidacao": False,
            "integridade_fontes": {
                "saudavel": False,
                "motivos": ["api_football_indisponivel"],
            },
        }
        snapshot_final = self.banco.salvar_registro(registro_final)

        self.assertEqual(
            self.avaliador.avaliar_snapshot(snapshot_final), 0
        )
        self.assertEqual(self.avaliador.metricas()["amostra"], 0)

    def test_nao_registra_green_de_gol_provisorio_que_regrediu(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "1-1", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=2.5, odd=1.8)]
        )
        provisorio = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=2), "1-2", "1-1"
            )
        )
        corrigido = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-1", "1-1", status="Finalizado",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(provisorio), 0)
        self.assertEqual(self.avaliador.avaliar_snapshot(corrigido), 1)
        resultado = self.banco.conexao.execute(
            "SELECT resultado FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(resultado, "red")

    def test_reabre_resultado_historico_liquidado_antes_do_final(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "1-1", "1-1")
        )
        sinal_id = self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=2.5, odd=1.8)]
        )[0]
        provisorio_em = self.inicio + timedelta(minutes=2)
        self.banco.salvar_registro(
            self.registro(provisorio_em, "1-2", "1-1")
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    retorno_unidades, observacao
                ) VALUES (?, ?, 'green', 0.8, 'resultado provisório')
                """,
                (sinal_id, provisorio_em.isoformat()),
            )
            self.banco.conexao.execute(
                """
                INSERT INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, tentativas
                ) VALUES (?, 'gols:teste:resultado', ?, ?, 'entregue', 1)
                """,
                (sinal_id, provisorio_em.isoformat(), provisorio_em.isoformat()),
            )

        primeiro = reabrir_resultados_provisorios(self.banco)
        segundo = reabrir_resultados_provisorios(self.banco)

        self.assertEqual(primeiro["sinais"], [sinal_id])
        self.assertEqual(segundo["quantidade"], 0)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM resultados_sinais"
            ).fetchone()[0],
            0,
        )
        revisao = self.banco.conexao.execute(
            """
            SELECT resultado_anterior, notificacao_status
            FROM revisoes_resultados
            """
        ).fetchone()
        self.assertEqual(tuple(revisao), ("green", "pendente"))
        status_entrega = self.banco.conexao.execute(
            "SELECT status FROM entregas_alertas"
        ).fetchone()[0]
        self.assertEqual(status_entrega, "corrigido")

    def test_nao_reabre_encerramento_sem_dado(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "3-0", "1-0", status="24 '")
        )
        sinal_id = self.banco.salvar_candidatos(
            inicial,
            [self.candidato("gol_ht", linha=3.5, odd=2.0)],
        )[0]
        encerrado_em = (self.inicio + timedelta(hours=24)).isoformat()
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    retorno_unidades, observacao,
                    snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, 'sem_dado', NULL, ?, NULL, 'sem_dado')
                """,
                (
                    sinal_id,
                    encerrado_em,
                    "resultado não avaliável após tentativas nas fontes",
                ),
            )

        revisao = reabrir_resultados_provisorios(self.banco)

        self.assertEqual(revisao, {"quantidade": 0, "sinais": []})
        resultado = self.banco.conexao.execute(
            """
            SELECT resultado, fonte_resultado
            FROM resultados_sinais WHERE sinal_id=?
            """,
            (sinal_id,),
        ).fetchone()
        self.assertEqual(tuple(resultado), ("sem_dado", "sem_dado"))
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM revisoes_resultados WHERE sinal_id=?",
                (sinal_id,),
            ).fetchone()[0],
            0,
        )

    def test_nao_reabre_void_de_invalidacao_operacional(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "4-4", status="63 '")
        )
        sinal_id = self.banco.salvar_candidatos(
            inicial,
            [self.candidato(
                "escanteios_ft_asiatico", linha=9.5, odd=1.825,
            )],
        )[0]
        encerrado_em = (self.inicio + timedelta(minutes=1)).isoformat()
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, fonte_resultado
                ) VALUES (?, ?, 'void', 0.0, ?, ?)
                """,
                (
                    sinal_id,
                    encerrado_em,
                    "linha substituida antes do envio",
                    "invalidacao_operacional_odds",
                ),
            )

        revisao = reabrir_resultados_provisorios(self.banco)

        self.assertEqual(revisao, {"quantidade": 0, "sinais": []})
        resultado = self.banco.conexao.execute(
            """
            SELECT resultado, retorno_unidades, fonte_resultado
            FROM resultados_sinais WHERE sinal_id=?
            """,
            (sinal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(resultado),
            ("void", 0.0, "invalidacao_operacional_odds"),
        )
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM revisoes_resultados WHERE sinal_id=?",
                (sinal_id,),
            ).fetchone()[0],
            0,
        )

    def test_proximo_gol_do_outro_lado_resolve_no_encerramento(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.8)],
        )
        posterior = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "0-1", "1-1", status="Finalizado",
            )
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 1)
        self.assertEqual(self.avaliador.metricas()["reds"], 1)

    def test_proximo_gol_provisorio_anulado_aguarda_resultado_final(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.8)],
        )
        provisorio = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=2), "1-0", "1-1"
            )
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "0-0", "1-1", status="Finalizado",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(provisorio), 0)
        self.assertEqual(self.avaliador.avaliar_snapshot(final), 1)
        resultado = self.banco.conexao.execute(
            "SELECT resultado FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(resultado, "red")

    def test_dois_gols_entre_snapshots_sem_eventos_ficam_pendentes(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.8)],
        )
        posterior = self.banco.salvar_registro(
            self.registro(self.inicio + timedelta(minutes=2), "1-1", "1-1")
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 0)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM resultados_sinais"
            ).fetchone()[0],
            0,
        )

    def test_historico_prova_proximo_gol_sem_eventos_da_api(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "1-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.8)],
        )
        intermediario = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=4), "2-0", "1-1"
            )
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "3-2", "1-1", status="Finalizado",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(intermediario), 0)
        self.assertEqual(self.avaliador.avaliar_snapshot(final), 1)
        resultado = self.banco.conexao.execute(
            "SELECT resultado FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(resultado, "green")

    def test_historico_nao_inventa_ordem_quando_pula_dois_gols(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.8)],
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-1", "1-1", status="Finalizado",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(final), 0)
        quantidade = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(quantidade, 0)

    def test_eventos_comprovam_que_visitante_fez_o_proximo_gol(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.8)],
        )
        registro = self.registro(
            self.inicio + timedelta(minutes=30),
            "1-1", "1-1", status="Finalizado",
        )
        registro["confirmacao_api"] = {
            "fixture_id": 10,
            "times": {"home": {"id": 1}, "away": {"id": 2}},
            "eventos": [
                {
                    "time": {"elapsed": 61},
                    "team": {"id": 2},
                    "type": "Goal",
                    "detail": "Normal Goal",
                },
                {
                    "time": {"elapsed": 62},
                    "team": {"id": 1},
                    "type": "Goal",
                    "detail": "Normal Goal",
                },
            ],
        }
        posterior = self.banco.salvar_registro(registro)
        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 1)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT resultado FROM resultados_sinais"
            ).fetchone()[0],
            "red",
        )

    def test_eventos_comprovam_que_casa_fez_o_proximo_gol(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.8)],
        )
        registro = self.registro(
            self.inicio + timedelta(minutes=30),
            "1-1", "1-1", status="Finalizado",
        )
        registro["confirmacao_api"] = {
            "fixture_id": 10,
            "times": {"home": {"id": 1}, "away": {"id": 2}},
            "eventos": [
                {
                    "time": {"elapsed": 61},
                    "team": {"id": 1},
                    "type": "Goal",
                    "detail": "Normal Goal",
                },
                {
                    "time": {"elapsed": 62},
                    "team": {"id": 2},
                    "type": "Goal",
                    "detail": "Normal Goal",
                },
            ],
        }
        posterior = self.banco.salvar_registro(registro)
        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 1)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT resultado FROM resultados_sinais"
            ).fetchone()[0],
            "green",
        )

    def test_divergencia_de_placar_atribui_resultado_ao_packball(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="visitante", odd=1.8)],
        )
        registro = self.registro(
            self.inicio + timedelta(minutes=30),
            "1-0", "1-1", status="Finalizado",
        )
        registro["confirmacao_api"] = {
            "fixture_id": 10,
            "placar": [0, 0],
            "times": {"home": {"id": 1}, "away": {"id": 2}},
            "eventos": [{
                "team": {"id": 1},
                "type": "Goal",
                "detail": "Missed Penalty",
            }],
        }
        final = self.banco.salvar_registro(registro)

        self.assertEqual(self.avaliador.avaliar_snapshot(final), 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT resultado, fonte_resultado
            FROM resultados_sinais
            """
        ).fetchone()
        self.assertEqual(tuple(resultado), ("red", "packball"))

    def test_placar_api_concordante_atribui_resultado_a_api(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.8)],
        )
        registro = self.registro(
            self.inicio + timedelta(minutes=30),
            "1-0", "1-1", status="Finalizado",
        )
        registro["confirmacao_api"] = {
            "fixture_id": 10,
            "placar": [1, 0],
            "times": {"home": {"id": 1}, "away": {"id": 2}},
            "eventos": [],
        }
        final = self.banco.salvar_registro(registro)

        self.assertEqual(self.avaliador.avaliar_snapshot(final), 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT resultado, fonte_resultado
            FROM resultados_sinais
            """
        ).fetchone()
        self.assertEqual(tuple(resultado), ("green", "api_football"))

    def test_gol_ht_nao_usa_gol_ocorrido_no_segundo_tempo(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1", status="40 '")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ht", linha=0.5, odd=1.8)]
        )
        segundo_tempo = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=8),
                "1-0",
                "1-1",
                status="48 '",
            )
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(segundo_tempo), 0)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM resultados_sinais"
            ).fetchone()[0],
            0,
        )

    def test_gol_ht_resolve_com_placar_do_intervalo(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1", status="40 '")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ht", linha=0.5, odd=1.8)]
        )
        intervalo = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=6),
                "1-0",
                "1-1",
                status="Intervalo",
            )
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(intervalo), 1)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT resultado FROM resultados_sinais"
            ).fetchone()[0],
            "green",
        )

    def test_recupera_gol_ht_com_status_packball_ht_apostrofo(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1", status="15 '")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ht", linha=0.5, odd=1.8)]
        )
        self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=35),
                "0-1", "2-4", status="HT '",
            )
        )

        self.assertEqual(
            self.avaliador.reavaliar_snapshots_conclusivos_pendentes(), 1
        )
        resultado = self.banco.conexao.execute(
            "SELECT resultado, fonte_resultado FROM resultados_sinais"
        ).fetchone()
        self.assertEqual(tuple(resultado), ("green", "packball"))

    def test_escanteios_1t_resolve_somente_no_intervalo(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-2", status="35 '")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("escanteios_1t", linha=4.5, odd=1.8)],
        )
        intervalo = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=10),
                "0-0", "3-2", status="Intervalo",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(intervalo), 1)
        resultado = self.banco.conexao.execute(
            "SELECT resultado FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(resultado, "green")

    def test_escanteios_1t_nao_usa_total_do_final(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1", status="35 '")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("escanteios_1t", linha=4.5, odd=1.8)],
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=60),
                "1-0", "6-5", status="Finalizado",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(final), 0)

    def test_escanteios_2t_desconta_baseline_comprovado_do_intervalo(self):
        self.banco.salvar_registro(
            self.registro(
                self.inicio, "0-0", "2-1", status="Intervalo"
            )
        )
        inicial = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=10),
                "0-0", "3-1", status="55 '",
            )
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("escanteios_2t", linha=5.5, odd=1.8)],
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=50),
                "1-0", "5-4", status="Finalizado",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(final), 1)
        resultado = self.banco.conexao.execute(
            "SELECT resultado FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(resultado, "green")

    def test_escanteios_2t_sem_baseline_do_intervalo_fica_pendente(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "3-1", status="55 '")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("escanteios_2t", linha=5.5, odd=1.8)],
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=40),
                "1-0", "6-5", status="Finalizado",
            )
        )

        self.assertEqual(self.avaliador.avaliar_snapshot(final), 0)

    def test_resultado_fora_da_faixa_nao_contamina_metricas_publicas(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial,
            [self.candidato("proximo_gol", linha="casa", odd=1.28)],
        )
        posterior = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-0", "1-1", status="Finalizado",
            )
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(posterior), 1)
        total_bruto = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(total_bruto, 1)
        self.assertEqual(self.avaliador.metricas()["amostra"], 0)
        self.assertNotIn(
            "proximo_gol", metricas_segmentadas(self.banco)["mercado"]
        )

    def test_metricas_calculam_roi_drawdown_e_sequencia(self):
        resultados = [
            {"resultado": "green", "retorno_unidades": 1.0},
            {"resultado": "red", "retorno_unidades": -1.0},
            {"resultado": "red", "retorno_unidades": -1.0},
        ]
        metricas = calcular_metricas(resultados)
        self.assertEqual(metricas["taxa_acerto"], 0.3333)
        self.assertEqual(metricas["roi"], -0.3333)
        self.assertEqual(metricas["drawdown_maximo"], 2.0)
        self.assertEqual(metricas["maior_sequencia_reds"], 2)
        self.assertEqual(metricas["estado_amostra"], "inconclusiva")
        self.assertLess(
            metricas["intervalo_acerto_95"][0], metricas["taxa_acerto"]
        )
        self.assertGreater(
            metricas["intervalo_acerto_95"][1], metricas["taxa_acerto"]
        )

    def test_roi_conta_void_como_exposicao_de_retorno_zero(self):
        metricas = calcular_metricas([
            {"resultado": "green", "retorno_unidades": 1.0},
            {"resultado": "void", "retorno_unidades": 0.0},
        ])

        self.assertEqual(metricas["amostra"], 1)
        self.assertEqual(metricas["exposicoes_liquidadas"], 2)
        self.assertEqual(metricas["taxa_acerto"], 1.0)
        self.assertEqual(metricas["lucro_unidades"], 1.0)
        self.assertEqual(metricas["roi"], 0.5)

    def test_metricas_auditam_se_nota_ordena_green_acima_de_red(self):
        resultados = [
            {
                "resultado": "green", "retorno_unidades": 0.8,
                "pontuacao_tecnica": 90,
            },
            {
                "resultado": "red", "retorno_unidades": -1.0,
                "pontuacao_tecnica": 70,
            },
        ]

        metricas = calcular_metricas(resultados)

        self.assertEqual(metricas["discriminacao_pontuacao"]["auc"], 1.0)

    def test_dado_final_ausente_permanece_pendente(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "2-1")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("proximo_escanteio", linha=8.5)]
        )
        final = self.banco.salvar_registro(
            {
                **self.registro(
                    self.inicio + timedelta(minutes=30),
                    "0-0",
                    None,
                    status="Finalizado",
                ),
                "estatisticas": {},
            }
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(final), 0)
        quantidade = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(quantidade, 0)

    def test_partida_anulada_vira_void_mesmo_sem_estatisticas(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "2-1")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("proximo_escanteio", linha=8.5)]
        )
        anulado = self.banco.salvar_registro(
            {
                **self.registro(
                    self.inicio + timedelta(minutes=30),
                    "",
                    None,
                    status="Anulado",
                ),
                "estatisticas": {},
            }
        )
        self.assertEqual(self.avaliador.avaliar_snapshot(anulado), 1)
        resultado = self.banco.conexao.execute(
            "SELECT resultado, retorno_unidades FROM resultados_sinais"
        ).fetchone()
        self.assertEqual(tuple(resultado), ("void", 0.0))

    def test_relatorio_segmenta_mercado_minuto_e_odd(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "0-0", "1-1", status="67 '")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=0.5, odd=1.8)]
        )
        posterior = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-0", "1-1", status="Finalizado",
            )
        )
        self.avaliador.avaliar_snapshot(posterior)
        relatorio = metricas_segmentadas(self.banco)
        self.assertEqual(relatorio["mercado"]["gol_ft"]["greens"], 1)
        self.assertEqual(relatorio["minuto"]["60-74"]["amostra"], 1)
        self.assertEqual(relatorio["odd"]["1.50-1.99"]["roi"], 0.8)
        somente_v1 = metricas_segmentadas(self.banco, "sinais-v1")
        somente_v2 = metricas_segmentadas(self.banco, "sinais-v2")
        self.assertEqual(somente_v1["mercado"]["gol_ft"]["amostra"], 1)
        self.assertNotIn("gol_ft", somente_v2["mercado"])

    def test_linha_inteira_igual_ao_total_devolve_aposta(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "1-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=2.0, odd=1.9)]
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-1",
                "1-1",
                status="Finalizado",
            )
        )
        self.avaliador.avaliar_snapshot(final)
        resultado = self.banco.conexao.execute(
            "SELECT resultado, retorno_unidades FROM resultados_sinais"
        ).fetchone()
        self.assertEqual(resultado["resultado"], "void")
        self.assertEqual(resultado["retorno_unidades"], 0)
        metricas = self.avaliador.metricas("gol_ft", "sinais-v1")
        self.assertEqual(metricas["amostra"], 0)
        self.assertEqual(metricas["observacoes_void"], 1)
        self.assertEqual(metricas["exposicoes_liquidadas"], 1)
        self.assertEqual(metricas["roi"], 0.0)

    def test_metricas_nao_substituem_primeira_exposicao_void_por_green(self):
        inicial = self.banco.salvar_registro(
            self.registro(self.inicio, "1-0", "1-1")
        )
        self.banco.salvar_candidatos(
            inicial, [self.candidato("gol_ft", linha=2.0, odd=1.9)]
        )
        posterior = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=10),
                "1-0", "1-1", status="70 '",
            )
        )
        self.banco.salvar_candidatos(
            posterior, [self.candidato("gol_ft", linha=0.5, odd=1.8)]
        )
        final = self.banco.salvar_registro(
            self.registro(
                self.inicio + timedelta(minutes=30),
                "1-1", "1-1", status="Finalizado",
            )
        )
        self.avaliador.avaliar_snapshot(final)

        metricas = self.avaliador.metricas("gol_ft", "sinais-v1")

        self.assertEqual(metricas["amostra"], 0)
        self.assertEqual(metricas["exposicoes_liquidadas"], 1)
        self.assertEqual(metricas["observacoes_void"], 1)
        self.assertEqual(metricas["roi"], 0.0)

    def test_liquidacao_de_quartos_calcula_meios_resultados(self):
        self.assertEqual(
            liquidar_over_asiatico(3, 2.75, 2.0),
            ("half_green", 0.5),
        )
        self.assertEqual(
            liquidar_over_asiatico(2, 2.25, 2.0),
            ("half_red", -0.5),
        )
        self.assertEqual(
            liquidar_over_asiatico(2, 2.0, 1.9),
            ("void", 0.0),
        )

    def test_metricas_incluem_meia_vitoria_e_meia_derrota(self):
        metricas = calcular_metricas(
            [
                {"resultado": "half_green", "retorno_unidades": 0.45},
                {"resultado": "half_red", "retorno_unidades": -0.5},
            ]
        )
        self.assertEqual(metricas["amostra"], 2)
        self.assertEqual(metricas["half_greens"], 1)
        self.assertEqual(metricas["half_reds"], 1)
        self.assertEqual(metricas["roi"], -0.025)


if __name__ == "__main__":
    unittest.main()
