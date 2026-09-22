import json
import unittest
from datetime import datetime
from pathlib import Path

from auditoria_sistema import gerar_auditoria
from banco import BancoMonitor
from calibracao import hash_modelo_calibracao, serializar_modelo_calibracao


class AuditoriaSistemaTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_auditoria.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def test_mede_cobertura_pendencia_e_integridade(self):
        snapshot = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "20 '",
                "estatisticas": {"Chutes": "2-1"},
                "confirmacao_api": {"fixture_id": 7},
                "qualidade": {"pontuacao": 80},
            }
        )
        self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "gol_ft",
                "linha": 0.5,
                "pontuacao_tecnica": 75,
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }],
            datetime(2026, 7, 20, 12, 0),
        )
        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 30)
        )
        self.assertEqual(resultado["cobertura_api_percentual"], 100.0)
        self.assertEqual(resultado["ultimas_24h"]["snapshots"], 1)
        self.assertEqual(resultado["pendencias"][0]["idade_maxima_minutos"], 30)
        self.assertEqual(resultado["pendencias_acima_180_minutos"], 0)
        self.assertEqual(resultado["grupos_aprovados_repetidos"], 0)
        self.assertEqual(resultado["fila_telegram"], {})
        self.assertEqual(resultado["historico_entregas_telegram"], {})
        self.assertEqual(resultado["entregas_transitorias_superadas"], 0)
        self.assertTrue(resultado["integridade_telegram"]["saudavel"])
        self.assertEqual(resultado["linhas_asiaticas_aprovadas"]["meias"], 1)
        self.assertTrue(resultado["saudavel"])

    def test_fila_telegram_exibe_somente_estado_atual_da_tentativa(self):
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:00:00",
            "url": "https://packball.com/match/telegram/live",
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "20 '",
        })
        sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal_id, "chat:teste", "enviando",
            instante="2026-07-20T12:01:00",
        )
        self.banco.registrar_entrega_alerta(
            sinal_id,
            "chat:teste",
            "entregue",
            instante="2026-07-20T12:01:01",
            provedor="telegram",
            provedor_destino_id="chat",
            provedor_mensagem_id="123",
            confirmacao={"ok": True, "message_id": 123},
        )
        self.banco.registrar_entrega_alerta(
            sinal_id,
            "gateway:teste",
            "bloqueado",
            erro="operacao_oficial_inicializando",
            instante="2026-07-20T12:01:02",
        )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 2)
        )

        self.assertEqual(resultado["fila_telegram"], {"entregue": 1})
        self.assertEqual(
            resultado["historico_entregas_telegram"],
            {"enviando": 1, "entregue": 1},
        )
        self.assertEqual(resultado["entregas_transitorias_superadas"], 1)
        self.assertEqual(
            resultado["integridade_telegram"]["envios_incertos"], 0
        )
        self.assertEqual(resultado["decisoes_gateway"], {"bloqueado": 1})
        self.assertEqual(
            resultado["historico_decisoes_gateway"], {"bloqueado": 1}
        )

    def test_envio_incerto_degrada_auditoria_profissional(self):
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:00:00",
            "url": "https://packball.com/match/incerto/live",
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "20 '",
        })
        sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal_id,
            "chat:teste",
            "enviando",
            instante="2026-07-20T12:01:00",
        )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 10)
        )

        self.assertEqual(resultado["fila_telegram"], {"enviando": 1})
        self.assertEqual(resultado["entregas_transitorias_superadas"], 0)
        self.assertEqual(
            resultado["integridade_telegram"]["envios_incertos"], 1
        )
        self.assertEqual(
            resultado["integridade_telegram"]["envios_oficiais_incertos"], 0
        )
        self.assertEqual(
            resultado["integridade_telegram"]["envios_analise_incertos"], 1
        )
        self.assertFalse(resultado["integridade_telegram"]["saudavel"])
        self.assertFalse(resultado["saudavel"])

    def test_separa_snapshot_final_sem_estatistica_de_falha_ao_vivo(self):
        base = {
            "mandante": "A",
            "visitante": "B",
            "placar": "2-0",
            "estatisticas": {},
        }
        self.banco.salvar_registro({
            **base,
            "coletado_em": "2026-07-20T12:00:00",
            "url": "https://packball.com/match/final/live",
            "status": "Finalizado",
        })
        self.banco.salvar_registro({
            **base,
            "coletado_em": "2026-07-20T12:01:00",
            "url": "https://packball.com/match/live/live",
            "status": "65 '",
        })

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 2)
        )

        self.assertEqual(resultado["snapshots_sem_estatisticas"], 2)
        self.assertEqual(
            resultado["snapshots_sem_estatisticas_finalizacao"], 1
        )
        self.assertEqual(resultado["snapshots_ao_vivo_sem_estatisticas"], 1)
        self.assertEqual(resultado["ultimas_24h"]["sem_estatisticas"], 2)
        self.assertEqual(
            resultado["ultimas_24h"]["sem_estatisticas_finalizacao"], 1
        )
        self.assertEqual(
            resultado["ultimas_24h"]["ao_vivo_sem_estatisticas"], 1
        )

    def test_calibracao_ativa_legada_degrada_auditoria(self):
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO calibracoes (
                    mercado, regra_versao, atualizado_em,
                    amostra, ativa, modelo_json
                ) VALUES ('gol_ft', 'sinais-v1', ?, 100, 1, ?)
                """,
                (
                    "2026-07-20T12:00:00",
                    json.dumps({"ativa": True, "amostra": 100}),
                ),
            )
        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 30)
        )
        self.assertEqual(resultado["calibracoes_ativas_incompativeis"], 1)
        self.assertFalse(
            resultado["elegibilidade_calibracoes"]["gol_ft"]["compativel"]
        )
        self.assertFalse(resultado["saudavel"])

    def test_calibracao_atual_sem_historico_degrada_auditoria(self):
        modelo = {"ativa": False, "amostra": 0}
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO calibracoes (
                    mercado, regra_versao, atualizado_em,
                    amostra, ativa, modelo_json
                ) VALUES ('gol_ft', 'sinais-v4', ?, 0, 0, ?)
                """,
                (
                    "2026-07-20T12:00:00",
                    serializar_modelo_calibracao(modelo),
                ),
            )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 30)
        )

        self.assertEqual(resultado["calibracoes_atuais_sem_historico"], 1)
        self.assertEqual(resultado["calibracoes_estado_incoerente"], 0)
        self.assertFalse(resultado["saudavel"])

    def test_flag_atual_divergente_do_modelo_degrada_auditoria(self):
        modelo = {"ativa": False, "amostra": 0}
        modelo_json = serializar_modelo_calibracao(modelo)
        modelo_hash = hash_modelo_calibracao(modelo)
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO calibracoes (
                    mercado, regra_versao, atualizado_em,
                    amostra, ativa, modelo_json
                ) VALUES ('gol_ft', 'sinais-v4', ?, 0, 1, ?)
                """,
                ("2026-07-20T12:00:00", modelo_json),
            )
            self.banco.conexao.execute(
                """
                INSERT INTO historico_calibracoes (
                    mercado, regra_versao, registrado_em, amostra, ativa,
                    amostra_fingerprint, motivo, modelo_hash, modelo_json
                ) VALUES ('gol_ft', 'sinais-v4', ?, 0, 1, '', NULL, ?, ?)
                """,
                ("2026-07-20T12:00:00", modelo_hash, modelo_json),
            )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 30)
        )

        self.assertEqual(resultado["calibracoes_atuais_sem_historico"], 0)
        self.assertEqual(resultado["calibracoes_estado_incoerente"], 1)
        self.assertFalse(resultado["saudavel"])

    def test_resultado_ligado_a_snapshot_de_outro_jogo_degrada_auditoria(self):
        primeiro = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "60 '",
            }
        )
        outro = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:30:00",
                "url": "https://packball.com/match/2/live",
                "mandante": "C",
                "visitante": "D",
                "placar": "1-0",
                "status": "Finalizado",
            }
        )
        sinal = self.banco.salvar_candidatos(
            primeiro,
            [{
                "mercado": "gol_ft",
                "regra_versao": "sinais-v3",
                "status": "aprovado",
            }],
        )[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-07-20T12:30:00', 'red', ?, 'packball')
                """,
                (sinal, outro),
            )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 31)
        )

        proveniencia = resultado["proveniencia_resultados"]
        self.assertFalse(proveniencia["saudavel"])
        self.assertEqual(proveniencia["inconsistentes"], 1)
        self.assertEqual(proveniencia["partida_incorreta"], 1)
        self.assertFalse(resultado["saudavel"])

    def test_void_operacional_documentado_nao_exige_snapshot_final(self):
        inicial = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/void-operacional/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "60 '",
            }
        )
        sinal = self.banco.salvar_candidatos(
            inicial,
            [{
                "mercado": "escanteios_ft_asiatico",
                "regra_versao": "sinais-v9d",
                "status": "simulacao",
            }],
        )[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-07-20T12:01:00', 'void', 0,
                          'Linha substituida antes do envio.', NULL,
                          'invalidacao_operacional_odds')
                """,
                (sinal,),
            )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 2)
        )

        proveniencia = resultado["proveniencia_resultados"]
        self.assertTrue(proveniencia["saudavel"])
        self.assertEqual(proveniencia["inconsistentes"], 0)
        self.assertEqual(proveniencia["sem_snapshot"], 0)

    def test_void_operacional_sem_documentacao_degrada_auditoria(self):
        inicial = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/void-sem-prova/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "60 '",
            }
        )
        sinal = self.banco.salvar_candidatos(
            inicial,
            [{
                "mercado": "escanteios_ft_asiatico",
                "regra_versao": "sinais-v9d",
                "status": "simulacao",
            }],
        )[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-07-20T12:01:00', 'void', 0,
                          '', NULL, 'invalidacao_operacional_odds')
                """,
                (sinal,),
            )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 2)
        )

        proveniencia = resultado["proveniencia_resultados"]
        self.assertFalse(proveniencia["saudavel"])
        self.assertEqual(proveniencia["inconsistentes"], 1)
        self.assertEqual(proveniencia["sem_snapshot"], 1)

    def test_times_api_incompativeis_degradam_proveniencia(self):
        inicial = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/api-times/live",
                "mandante": "Clube Atletico Norte",
                "visitante": "Esporte Clube Sul",
                "placar": "0-0",
                "status": "60 '",
            }
        )
        sinal = self.banco.salvar_candidatos(
            inicial,
            [{
                "mercado": "gol_ft", "regra_versao": "sinais-v3",
                "status": "aprovado",
            }],
        )[0]
        final = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:30:00",
                "url": "https://packball.com/match/api-times/live",
                "mandante": "Clube Atletico Norte",
                "visitante": "Esporte Clube Sul",
                "placar": "1-0",
                "status": "Finalizado",
                "confirmacao_api": {
                    "fixture_id": 123,
                    "times": {
                        "home": {"name": "Time Desconhecido"},
                        "away": {"name": "Outro Adversario"},
                    },
                },
            }
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-07-20T12:30:00', 'green', ?,
                          'api_football')
                """,
                (sinal, final),
            )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 12, 31)
        )

        proveniencia = resultado["proveniencia_resultados"]
        self.assertFalse(proveniencia["saudavel"])
        self.assertEqual(proveniencia["api_times_incompativeis"], 1)
        self.assertEqual(proveniencia["inconsistentes"], 1)

    def test_hash_alterado_no_historico_de_calibracao_degrada_auditoria(self):
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO historico_calibracoes (
                    mercado, regra_versao, registrado_em, amostra, ativa,
                    amostra_fingerprint, motivo, modelo_hash, modelo_json
                ) VALUES (
                    'gol_ft', 'sinais-v4', '2026-07-21T12:00:00',
                    100, 0, '', 'teste', 'hash-incorreto', '{}'
                )
                """
            )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 21, 12, 1)
        )

        self.assertFalse(resultado["historico_calibracoes"]["saudavel"])
        self.assertEqual(
            resultado["historico_calibracoes"]["hashes_invalidos"], 1
        )
        self.assertFalse(resultado["saudavel"])

    def test_partida_longa_observada_recentemente_permanece_saudavel(self):
        inicial = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "20 '",
            }
        )
        self.banco.salvar_candidatos(
            inicial,
            [{
                "mercado": "gol_ft",
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }],
            datetime(2026, 7, 20, 12, 0),
        )
        self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T15:55:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "1-1",
                "status": "PEN",
            }
        )

        resultado = gerar_auditoria(
            self.banco, datetime(2026, 7, 20, 16, 0)
        )

        self.assertEqual(resultado["pendencias_acima_180_minutos"], 0)
        self.assertTrue(resultado["saudavel"])


if __name__ == "__main__":
    unittest.main()
