import json
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace

from avaliacao_desajuste_odds import (
    CHAVE_DEFINICAO_CONVERGENCIA,
    CHAVE_DEFINICAO_CONVERGENCIA_ESCANTEIOS,
    CHAVE_DEFINICAO_EDGE_SEM_VIG,
    CHAVE_DEFINICAO_REFERENCIA_POS_ENVIO,
    CHAVE_POLITICA_LIQUIDACAO_EDGE_SEM_VIG,
    ESTADO_EXECUCAO_CONCLUIDA,
    ESTADO_EXECUCAO_FALHA,
    _obter_ou_criar_definicao_convergencia,
    _obter_ou_criar_definicao_convergencia_escanteios,
    _obter_ou_criar_definicao_edge_sem_vig,
    _obter_ou_criar_definicao_referencia_pos_envio,
    _obter_ou_criar_politica_liquidacao_edge_sem_vig,
    _resumir_edge_sem_vig_multifonte,
    avaliar_desajustes_odds,
    construir_estado_execucao_nao_concluida,
)
from banco import BancoMonitor, auditar_compatibilidade
from desajuste_odds import (
    CAMPOS_EVIDENCIA_COMPARACAO,
    VERSAO as VERSAO_COMPARACAO,
)


class AvaliacaoDesajusteOddsTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_avaliacao_desajuste_odds.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    def salvar(
        self, horario, odd_packball, odd_betsapi,
        status="25 '", placar="0-0", motivo_comparacao=None,
    ):
        registro = {
            "coletado_em": horario,
            "url": "https://packball.com/pt/matches/42/match/a-b/live",
            "mandante": "A",
            "visitante": "B",
            "placar": placar,
            "status": status,
            "qualidade": {"pontuacao": 90},
            "odds": {"ao_vivo": [{
                "mercado": "Total Gols",
                "categoria": "gols",
                "escopo": "total",
                "fonte": "packball",
                "coletado_em": horario,
                "ofertas": [
                    {"linha": 0.5, "over": odd_packball, "under": 3.0},
                    {
                        "linha": 0.5, "over": odd_betsapi, "under": 3.0,
                        "fonte": "betsapi", "bookmaker": "bet365",
                        "coletado_em": horario,
                    },
                ],
            }]},
        }
        if motivo_comparacao:
            registro["_motivo_comparacao"] = motivo_comparacao
        return self.banco.salvar_registro(registro)

    def test_persiste_coorte_imutavel_e_avalia_seguimento(self):
        self.salvar("2026-09-01T12:00:00", 1.50, 1.70)
        self.salvar("2026-09-01T12:01:00", 1.62, 1.68)
        self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:02:00",
            "url": "https://packball.com/pt/matches/42/match/a-b/live",
            "mandante": "A", "visitante": "B", "placar": "2-0",
            "status": "Finalizado", "qualidade": {"pontuacao": 90},
        })

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
        )

        self.assertEqual(
            ESTADO_EXECUCAO_CONCLUIDA,
            resultado["estado_execucao"],
        )
        self.assertEqual(
            "custodia-execucao-avaliacao-v3",
            resultado["custodia_execucao_versao"],
        )
        self.assertGreaterEqual(resultado["comparacoes"], 2)
        self.assertEqual(1, resultado["candidatos_independentes"])
        self.assertEqual(1, resultado["com_seguimento_5m"])
        self.assertEqual(1, resultado["persistentes_5m"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["promocao_automatica"])
        integridade = resultado["integridade_comparacoes_odds"]
        self.assertTrue(integridade["saudavel"])
        self.assertEqual(0, integridade["comparacoes_invalidas"])
        self.assertEqual(
            integridade["comparacoes_persistidas"],
            integridade["comparacoes_validas"],
        )
        executavel = resultado["recorte_executavel_prospectivo"]
        self.assertEqual("bet365", executavel["bookmaker"])
        self.assertEqual(1, executavel["candidatos_independentes"])
        self.assertEqual(
            1, executavel["com_seguimento_mesma_bookmaker_5m"]
        )
        self.assertEqual(
            1, executavel["persistentes_mesma_bookmaker_5m"]
        )
        cobertura = executavel["cobertura_comparacao"]
        self.assertEqual(
            "candidatos_executaveis_detectados", cobertura["estado"]
        )
        self.assertGreaterEqual(cobertura["comparacoes_com_bookmaker"], 2)
        self.assertGreaterEqual(
            cobertura["desajustes_bookmaker_melhor"], 1
        )
        self.assertFalse(cobertura["altera_sinal"])
        self.assertFalse(executavel["aplicacao_sinais"])
        self.assertTrue(auditar_compatibilidade(
            self.banco.conexao
        )["compativel"])

        with self.assertRaises(sqlite3.IntegrityError):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE comparacoes_odds_fontes SET odd_melhor=9"
                )

    def test_estado_de_falha_nao_transporta_vantagem_anterior(self):
        estado = construir_estado_execucao_nao_concluida(
            ESTADO_EXECUCAO_FALHA,
            atualizado_em="2026-09-10T12:00:02",
            iniciado_em="2026-09-10T12:00:00",
            finalizado_em="2026-09-10T12:00:02",
            duracao_segundos=2.25,
            tipo_erro="RuntimeError",
            erro="falha controlada",
        )

        self.assertEqual(ESTADO_EXECUCAO_FALHA, estado["estado_execucao"])
        self.assertFalse(estado["aplicacao_sinais"])
        self.assertFalse(estado["promocao_automatica"])
        self.assertNotIn("persistencia_comprovada", estado)
        self.assertNotIn("recorte_executavel_prospectivo", estado)

    def test_relatorio_isola_corroboracao_de_entrada_sem_promover(self):
        self.salvar(
            "2026-09-01T12:00:00",
            1.50,
            1.52,
            motivo_comparacao="corroboracao_odd_entrada_rapida",
        )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
        )
        recorte = resultado["corroboracao_entrada_rapida"]

        self.assertEqual(
            "corroboracao_odd_entrada_rapida", recorte["marcador"]
        )
        self.assertEqual(2, recorte["comparacoes"])
        self.assertEqual(1, recorte["fotografias_independentes"])
        self.assertEqual(1, recorte["jogos_distintos"])
        self.assertEqual({"over": 1, "under": 1}, recorte["por_selecao"])
        self.assertFalse(recorte["pronta_para_analise"])
        self.assertFalse(recorte["aplicacao_sinais"])
        self.assertFalse(recorte["promocao_automatica"])
        self.assertEqual(
            "continuar_coleta_prospectiva", recorte["recomendacao"]
        )

    def test_referencia_pos_envio_vincula_sinal_real_sem_promover(self):
        snapshot_id = self.salvar(
            "2026-09-11T12:00:00+00:00", 1.70, 1.80
        )
        sinal_origem_id = self.banco.salvar_candidatos(snapshot_id, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.70,
            "pontuacao_tecnica": 70,
            "regra_versao": "teste-pos-envio-origem-v1",
            "status": "rejeitado",
        }], "2026-09-11T12:00:00+00:00")[0]
        sinal_tecnico_id = self.banco.salvar_candidatos(snapshot_id, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.75,
            "pontuacao_tecnica": 80,
            "regra_versao": "teste-pos-envio-tecnico-v1",
            "status": "rejeitado",
        }], "2026-09-11T12:00:00+00:00")[0]
        sinal_enviado_id = self.banco.salvar_candidatos(snapshot_id, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.80,
            "pontuacao_tecnica": 85,
            "regra_versao": "teste-pos-envio-enviado-v1",
            "status": "aprovado",
            "features": {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "odd_oposta": 2.10,
                "acompanhamento_odd_rapido": {
                    "versao": "acompanhamento-odd-api-rapido-v1",
                    "leitura_tecnica_sinal_id": sinal_tecnico_id,
                    "origem_sinal_id": sinal_origem_id,
                    "placar_confirmado": "0-0",
                    "minuto_confirmado": 25.0,
                    "linha_exata_confirmada": True,
                    "criterios_revalidados": [
                        "leitura_tecnica_ainda_valida",
                        "placar_inalterado",
                        "periodo_e_minuto_operacionais",
                        "linha_exata_disponivel",
                        "odd_atual_fresca",
                        "odd_dentro_da_faixa",
                        "mesmo_metodo_recalculado_na_odd_e_minuto_atuais",
                        "politica_envio_grupo_ativa",
                    ],
                },
            },
        }], "2026-09-11T12:00:00+00:00")[0]
        self.banco.registrar_entrega_alerta(
            sinal_enviado_id,
            "grupo:teste",
            "entregue",
            instante="2026-09-11T12:00:01+00:00",
            provedor="telegram",
            provedor_mensagem_id="123",
        )
        referencia = {"pre_jogo": [], "ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "fonte": "the_odds_api",
            "ofertas": [{
                "linha": 0.5,
                "over": 1.50,
                "under": 2.50,
                "fonte": "the_odds_api",
                "bookmaker": "pinnacle",
                "coletado_em": "2026-09-11T11:59:30+00:00",
                "recebido_em": "2026-09-11T12:00:03+00:00",
                "idade_segundos": 33.0,
                "identidade_evento": {
                    "confirmada": True,
                    "placar_normalizado": "0-0",
                },
            }],
            "ofertas_ht": [],
        }]}
        diagnostico = {
            "ativa": True,
            "pareado": True,
            "motivo": "oferta_anexada",
            "evento_externo_id": "odds-pos-envio-1",
            "mandante_observado": "A",
            "visitante_observado": "B",
            "consultados": ["alternate_totals"],
            "reserva_consumida": True,
            "reserva": {"autorizada": True},
            "auditoria_amostragem": {},
        }
        auditoria = self.banco.registrar_referencia_sombra_acompanhamento_odd(
            sinal_tecnico_id,
            referencia,
            diagnostico,
            {"placar": "0-0", "minuto": 25, "status": "25 '"},
            consultado_em="2026-09-11T12:00:02+00:00",
            origem_sinal_id=sinal_origem_id,
            sinal_enviado_id=sinal_enviado_id,
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, 'green', 0.8, 'teste', ?, 'api_football')
                """,
                (
                    sinal_enviado_id,
                    "2026-09-11T13:00:00+00:00",
                    snapshot_id,
                ),
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_referencia_pos_envio="2026-09-11T11:59:00+00:00",
        )
        recorte = resultado["recorte_referencia_pos_envio"]
        mercado = recorte["por_mercado"]["gol_ft"]
        linha_auditada = self.banco.conexao.execute(
            """
            SELECT metadados_json FROM observacoes_fontes_odds
            WHERE id=?
            """,
            (auditoria["observacao_id"],),
        ).fetchone()
        metadados = json.loads(linha_auditada["metadados_json"])

        self.assertTrue(auditoria["persistido"])
        self.assertEqual(
            "amostragem-referencia-sombra-auditoria-v6",
            metadados["versao"],
        )
        self.assertEqual(
            sinal_enviado_id, metadados["sinal_enviado_id"]
        )
        self.assertTrue(metadados["alerta_enviado_comprovado"])
        self.assertTrue(
            metadados["referencia_posterior_alerta"], metadados
        )
        self.assertTrue(metadados["linhagem_materializacao_comprovada"])
        self.assertTrue(metadados["criterios_materializacao_comprovados"])
        self.assertTrue(metadados["placar_materializacao_comprovado"])
        self.assertTrue(metadados["placar_referencia_contexto_comprovado"])
        self.assertTrue(metadados["timestamp_referencia_comprovado"])
        self.assertEqual(1, recorte["auditorias_pos_envio"])
        self.assertEqual(1, recorte["fotografias_elegiveis"], recorte)
        self.assertEqual(1, mercado["candidatos_edge"])
        self.assertEqual(1, mercado["coorte_edge"])
        self.assertEqual(1, mercado["total"]["resultados"])
        self.assertEqual(0.8, mercado["total"]["roi_real"])
        self.assertFalse(mercado["evidencia_completa"])
        self.assertFalse(recorte["vantagem_estatistica_para_revisao"])
        self.assertFalse(recorte["aplicacao_sinais"])
        self.assertFalse(recorte["promocao_automatica"])

    def test_referencia_pos_envio_exclui_linhagem_nao_comprovada(self):
        snapshot_id = self.salvar(
            "2026-09-11T12:00:00+00:00", 1.70, 1.80
        )
        sinal_tecnico_id = self.banco.salvar_candidatos(snapshot_id, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.75,
            "pontuacao_tecnica": 80,
            "regra_versao": "teste-pos-envio-tecnico-invalido-v1",
            "status": "rejeitado",
        }], "2026-09-11T12:00:00+00:00")[0]
        sinal_enviado_id = self.banco.salvar_candidatos(snapshot_id, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.80,
            "pontuacao_tecnica": 85,
            "regra_versao": "teste-pos-envio-enviado-invalido-v1",
            "status": "aprovado",
            "features": {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "odd_oposta": 2.10,
                "acompanhamento_odd_rapido": {
                    "versao": "acompanhamento-odd-api-rapido-v1",
                    "leitura_tecnica_sinal_id": sinal_tecnico_id + 999,
                    "origem_sinal_id": sinal_tecnico_id,
                    "placar_confirmado": "0-0",
                    "linha_exata_confirmada": True,
                    "criterios_revalidados": [
                        "placar_inalterado",
                        "linha_exata_disponivel",
                        "odd_atual_fresca",
                    ],
                },
            },
        }], "2026-09-11T12:00:00+00:00")[0]
        self.banco.registrar_entrega_alerta(
            sinal_enviado_id,
            "grupo:teste",
            "entregue",
            instante="2026-09-11T12:00:01+00:00",
            provedor="telegram",
            provedor_mensagem_id="124",
        )
        referencia = {"pre_jogo": [], "ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "fonte": "the_odds_api",
            "ofertas": [{
                "linha": 0.5,
                "over": 1.50,
                "under": 2.50,
                "fonte": "the_odds_api",
                "bookmaker": "pinnacle",
                "coletado_em": "2026-09-11T11:59:30+00:00",
                "recebido_em": "2026-09-11T12:00:03+00:00",
                "idade_segundos": 33.0,
                "identidade_evento": {
                    "confirmada": True,
                    "placar_normalizado": "0-0",
                },
            }],
            "ofertas_ht": [],
        }]}
        diagnostico = {
            "ativa": True,
            "pareado": True,
            "motivo": "oferta_anexada",
            "consultados": ["alternate_totals"],
            "reserva_consumida": True,
            "reserva": {"autorizada": True},
            "auditoria_amostragem": {},
        }
        auditoria = self.banco.registrar_referencia_sombra_acompanhamento_odd(
            sinal_tecnico_id,
            referencia,
            diagnostico,
            {"placar": "0-0", "minuto": 25, "status": "25 '"},
            consultado_em="2026-09-11T12:00:02+00:00",
            origem_sinal_id=sinal_tecnico_id,
            sinal_enviado_id=sinal_enviado_id,
        )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_referencia_pos_envio="2026-09-11T11:59:00+00:00",
        )
        recorte = resultado["recorte_referencia_pos_envio"]

        self.assertTrue(auditoria["persistido"])
        self.assertEqual(1, recorte["auditorias_pos_envio"])
        self.assertEqual(0, recorte["fotografias_elegiveis"])
        self.assertEqual(
            1,
            recorte["exclusoes"].get(
                "linhagem_materializacao_divergente", 0
            ),
            recorte,
        )
        self.assertFalse(recorte["aplicacao_sinais"])

    def test_definicao_referencia_pos_envio_e_imutavel(self):
        documento = _obter_ou_criar_definicao_referencia_pos_envio(
            self.banco
        )
        linha = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (CHAVE_DEFINICAO_REFERENCIA_POS_ENVIO,),
        ).fetchone()

        self.assertEqual(documento, json.loads(linha["valor"]))
        self.assertEqual(64, len(documento["definicao_sha256"]))
        self.assertFalse(documento["aplicacao_sinais"])
        self.assertFalse(documento["promocao_automatica"])

    def test_avaliacao_reutiliza_ancoras_em_sqlite_somente_leitura(self):
        self.salvar("2026-09-01T12:00:00", 1.50, 1.70)
        original = avaliar_desajustes_odds(self.banco)
        conexao_ro = sqlite3.connect(
            self.caminho.resolve().as_uri() + "?mode=ro",
            uri=True,
        )
        conexao_ro.row_factory = sqlite3.Row
        try:
            reavaliado = avaliar_desajustes_odds(
                SimpleNamespace(conexao=conexao_ro)
            )
        finally:
            conexao_ro.close()

        self.assertEqual(
            original["ancora_prospectiva_em"],
            reavaliado["ancora_prospectiva_em"],
        )
        self.assertEqual(original["comparacoes"], reavaliado["comparacoes"])
        self.assertFalse(reavaliado["aplicacao_sinais"])

    def test_evidencia_forjada_bloqueia_inferencia_estatistica(self):
        snapshot_id = self.salvar(
            "2026-09-01T12:00:00", 1.50, 1.70
        )
        linha = dict(self.banco.conexao.execute(
            """
            SELECT * FROM comparacoes_odds_fontes
            WHERE snapshot_id=? AND selecao='over'
            LIMIT 1
            """,
            (snapshot_id,),
        ).fetchone())
        linha["fonte_a"] = "fonte_forjada_a"
        linha["fonte_b"] = "fonte_forjada_b"
        if float(linha["odd_a"]) >= float(linha["odd_b"]):
            linha["fonte_melhor"] = linha["fonte_a"]
            linha["fonte_controle"] = linha["fonte_b"]
        else:
            linha["fonte_melhor"] = linha["fonte_b"]
            linha["fonte_controle"] = linha["fonte_a"]
        linha["evidencia_sha256"] = "f" * 64
        campos = (*CAMPOS_EVIDENCIA_COMPARACAO, "evidencia_sha256")
        marcadores = ", ".join("?" for _ in campos)
        with self.banco.conexao:
            self.banco.conexao.execute(
                f"""
                INSERT INTO comparacoes_odds_fontes (
                    {", ".join(campos)}
                ) VALUES ({marcadores})
                """,
                tuple(linha.get(campo) for campo in campos),
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
        )
        integridade = resultado["integridade_comparacoes_odds"]

        self.assertFalse(integridade["saudavel"])
        self.assertTrue(integridade["bloqueia_inferencia"])
        self.assertEqual(1, integridade["comparacoes_invalidas"])
        self.assertEqual(
            1,
            integridade["problemas"]["evidencia_sha256_divergente"],
        )
        self.assertEqual(1, resultado["comparacoes_excluidas_integridade"])
        self.assertFalse(resultado["pronto_para_revisao"])
        self.assertFalse(resultado["persistencia_comprovada"])
        self.assertEqual(
            "bloquear_inferencia_e_corrigir_integridade",
            resultado["recomendacao"],
        )
        self.assertTrue(
            resultado["recorte_executavel_prospectivo"][
                "bloqueado_por_integridade"
            ]
        )

    def test_exclui_comparacao_legada_sem_estado_das_fontes(self):
        snapshot_id = self.salvar(
            "2026-09-01T12:00:00", 1.50, 1.70
        )
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO comparacoes_odds_fontes (
                    snapshot_id, partida_id, observado_em, placar, status,
                    minuto, categoria, escopo, periodo, linha, selecao,
                    fonte_a, bookmaker_a, odd_a, coletado_em_a,
                    fonte_b, bookmaker_b, odd_b, coletado_em_b,
                    fonte_melhor, bookmaker_melhor, odd_melhor,
                    fonte_controle, bookmaker_controle, odd_controle,
                    delta_absoluto, delta_relativo,
                    intervalo_fontes_segundos, frescor_maximo_segundos,
                    compatibilidade_bookmaker, estado, motivos_json,
                    versao, evidencia_sha256
                ) VALUES (
                    ?, ?, '2026-09-01T12:00:00', '0-0', '25', 25,
                    'gols', 'total', 'FT', 1.5, 'over',
                    'packball', '', 1.50, '2026-09-01T12:00:00',
                    'betsapi', 'bet365', 1.70, '2026-09-01T12:00:00',
                    'betsapi', 'bet365', 1.70,
                    'packball', '', 1.50,
                    0.20, 0.1333, 0, 0,
                    'bookmaker_diferente', 'desajuste_candidato', '[]',
                    'comparacao-odds-multifonte-temporal-exata-v2',
                    'legado-sem-estado'
                )
                """,
                (snapshot_id, partida_id),
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
        )

        self.assertEqual(
            resultado["versao_comparacao_exigida"], VERSAO_COMPARACAO
        )
        self.assertEqual(
            resultado["comparacoes_excluidas_sem_estado_comprovado"], 1
        )
        self.assertEqual(resultado["candidatos_independentes"], 1)

    def test_outra_bookmaker_nao_prova_persistencia_executavel(self):
        self.salvar("2026-09-01T12:00:00", 1.50, 1.70)
        self.salvar("2026-09-01T12:01:00", 1.68, 1.40)

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
        )

        self.assertEqual(1, resultado["persistentes_5m"])
        executavel = resultado["recorte_executavel_prospectivo"]
        self.assertEqual(
            1, executavel["com_seguimento_mesma_bookmaker_5m"]
        )
        self.assertEqual(
            0, executavel["persistentes_mesma_bookmaker_5m"]
        )
        self.assertFalse(executavel["vantagem_executavel_comprovada"])

    def test_cobertura_distingue_observacao_sem_pareamento(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:00",
            "url": "https://packball.com/pt/matches/99/match/c-d/live",
            "mandante": "C", "visitante": "D", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (
                    ?, 'betsapi', '2026-09-01T12:00:00',
                    'oferta_monitorada', 'FT', 'gol_ft',
                    ?
                )
                """,
                (
                    partida_id,
                    '{"bookmaker":"bet365","placar":"0-0",'
                    '"minuto":25,"linha":0.5,"odd":1.70}',
                ),
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
        )
        cobertura = resultado[
            "recorte_executavel_prospectivo"
        ]["cobertura_comparacao"]
        self.assertEqual("sem_pareamento_multifonte", cobertura["estado"])
        self.assertEqual(1, cobertura["observacoes_bookmaker"])
        self.assertEqual(0, cobertura["comparacoes_com_bookmaker"])

    def test_recorte_observacional_pareia_fontes_assincronas(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:00",
            "url": "https://packball.com/pt/matches/77/match/e-f/live",
            "mandante": "E", "visitante": "F", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        ofertas = (
            (
                "betsapi", "2026-09-01T12:00:00",
                '{"bookmaker":"bet365","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.70}',
            ),
            (
                "api_football", "2026-09-01T12:00:20",
                '{"bookmaker":"api-football","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.50}',
            ),
            (
                "betsapi", "2026-09-01T12:02:00",
                '{"bookmaker":"bet365","placar":"0-0",'
                '"minuto":26,"linha":0.5,"odd":1.68}',
            ),
        )
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (?, ?, ?, 'oferta_monitorada', 'FT', 'gol_ft', ?)
                """,
                [
                    (partida_id, fonte, horario, oferta)
                    for fonte, horario, oferta in ofertas
                ],
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
        )
        recorte = resultado["recorte_observacional_executavel"]
        self.assertEqual(3, recorte["observacoes_validas"])
        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(
            1, recorte["com_seguimento_mesma_bookmaker_5m"]
        )
        self.assertEqual(
            1, recorte["persistentes_mesma_bookmaker_5m"]
        )
        self.assertFalse(recorte["aplicacao_sinais"])
        self.assertFalse(recorte["promocao_automatica"])

    def test_recorte_observacional_recupera_referencia_do_snapshot(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:00",
            "url": "https://packball.com/pt/matches/770/match/e1-f1/live",
            "mandante": "E1", "visitante": "F1", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:20",
            "url": "https://packball.com/pt/matches/770/match/e1-f1/live",
            "mandante": "E1", "visitante": "F1", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
            "odds": {"ao_vivo": [{
                "categoria": "gols",
                "escopo": "total",
                "formato": "duas_opcoes",
                "fonte": "api_football",
                "bookmaker": "api-football",
                "coletado_em": "2026-09-01T12:00:20",
                "ofertas": [{
                    "linha": 0.5,
                    "over": 1.50,
                    "under": 2.50,
                    "fonte": "api_football",
                    "bookmaker": "api-football",
                    "coletado_em": "2026-09-01T12:00:20",
                }],
            }]},
        })
        ofertas = (
            ("2026-09-01T12:00:00", 25, 1.70),
            ("2026-09-01T12:02:00", 26, 1.68),
        )
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (?, 'betsapi', ?, 'oferta_monitorada', 'FT',
                          'gol_ft', ?)
                """,
                [
                    (
                        partida_id,
                        horario,
                        json.dumps({
                            "bookmaker": "bet365",
                            "placar": "0-0",
                            "minuto": minuto,
                            "linha": 0.5,
                            "odd": odd,
                        }),
                    )
                    for horario, minuto, odd in ofertas
                ],
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
        )
        recorte = resultado["recorte_observacional_executavel"]

        self.assertEqual(1, recorte["pares_temporais"])
        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(1, recorte["com_seguimento_mesma_bookmaker_5m"])
        self.assertEqual(1, recorte["persistentes_mesma_bookmaker_5m"])
        self.assertEqual(1, recorte["fontes_observadas"]["api_football"])
        self.assertEqual(1, recorte["origens_observacoes"]["snapshots_odds"])
        self.assertTrue(recorte["contraparte_exige_fonte_independente"])

    def test_recorte_recupera_referencia_sombra_sem_executar_por_ela(self):
        instante = "2026-09-01T12:00:00"
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": instante,
            "url": "https://packball.com/pt/matches/779/match/e9-f9/live",
            "mandante": "E9", "visitante": "F9", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
            "odds_referencia_sombra": {
                "pre_jogo": [], "ao_vivo": [{
                    "categoria": "gols", "escopo": "total",
                    "formato": "duas_opcoes", "fonte": "the_odds_api",
                    "bookmaker": "pinnacle", "coletado_em": instante,
                    "cache": False, "idade_segundos": 0.0,
                    "ofertas": [{
                        "linha": 0.5, "over": 1.50, "under": 2.50,
                        "fonte": "the_odds_api", "bookmaker": "pinnacle",
                        "coletado_em": instante,
                    }],
                }],
            },
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (?, 'betsapi', ?, 'oferta_monitorada', 'FT',
                          'gol_ft', ?)
                """,
                [
                    (
                        partida_id, horario, json.dumps({
                            "bookmaker": "bet365", "placar": "0-0",
                            "minuto": minuto, "linha": 0.5, "odd": odd,
                        }),
                    )
                    for horario, minuto, odd in (
                        (instante, 25, 1.70),
                        ("2026-09-01T12:02:00", 26, 1.68),
                    )
                ],
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
        )
        recorte = resultado["recorte_observacional_executavel"]

        self.assertEqual(1, recorte["pares_temporais"])
        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(1, recorte["fontes_observadas"]["the_odds_api"])
        self.assertFalse(recorte["aplicacao_sinais"])
        self.assertFalse(recorte["promocao_automatica"])

    def test_recorte_observacional_rejeita_mesma_fonte_e_lado_oposto(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:00",
            "url": "https://packball.com/pt/matches/773/match/e4-f4/live",
            "mandante": "E4", "visitante": "F4", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        ofertas = (
            (
                "betsapi", "2026-09-01T12:00:00",
                {"bookmaker": "bet365", "placar": "0-0", "minuto": 25,
                 "linha": 0.5, "odd": 1.70, "selecao": "over"},
            ),
            (
                "betsapi", "2026-09-01T12:00:15",
                {"bookmaker": "pinnacle", "placar": "0-0", "minuto": 25,
                 "linha": 0.5, "odd": 1.50, "selecao": "over"},
            ),
            (
                "api_football", "2026-09-01T12:00:20",
                {"bookmaker": "api-football", "placar": "0-0", "minuto": 25,
                 "linha": 0.5, "odd": 1.50, "selecao": "under"},
            ),
        )
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (?, ?, ?, 'oferta_monitorada', 'FT', 'gol_ft', ?)
                """,
                [
                    (partida_id, fonte, horario, json.dumps(oferta))
                    for fonte, horario, oferta in ofertas
                ],
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
        )
        recorte = resultado["recorte_observacional_executavel"]

        self.assertEqual(0, recorte["pares_temporais"])
        self.assertEqual(0, recorte["candidatos_independentes"])
        self.assertGreaterEqual(
            recorte["exclusoes_pareamento"]["sem_referencia_mesma_linha"],
            1,
        )

    def test_recorte_observacional_nao_usa_cotacao_antes_da_deteccao(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:00",
            "url": "https://packball.com/pt/matches/771/match/e2-f2/live",
            "mandante": "E2", "visitante": "F2", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        ofertas = (
            (
                "betsapi", "2026-09-01T12:00:00",
                '{"bookmaker":"bet365","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.70}',
            ),
            (
                "betsapi", "2026-09-01T12:00:10",
                '{"bookmaker":"bet365","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.69}',
            ),
            (
                "api_football", "2026-09-01T12:00:20",
                '{"bookmaker":"api-football","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.50}',
            ),
        )
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (?, ?, ?, 'oferta_monitorada', 'FT', 'gol_ft', ?)
                """,
                [
                    (partida_id, fonte, horario, oferta)
                    for fonte, horario, oferta in ofertas
                ],
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
        )
        recorte = resultado["recorte_observacional_executavel"]

        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(0, recorte["com_seguimento_mesma_bookmaker_5m"])
        self.assertEqual(0, recorte["persistentes_mesma_bookmaker_5m"])
        self.assertTrue(
            recorte[
                "relogio_seguimento_inicia_quando_ambas_fontes_conhecidas"
            ]
        )

    def test_recortes_executaveis_usam_so_primeira_oportunidade_do_jogo(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:00",
            "url": "https://packball.com/pt/matches/772/match/e3-f3/live",
            "mandante": "E3", "visitante": "F3", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        ofertas = (
            ("betsapi", "2026-09-01T12:00:00", "bet365", "0-0", 25, 0.5, 1.70),
            ("api_football", "2026-09-01T12:00:20", "api-football", "0-0", 25, 0.5, 1.50),
            ("betsapi", "2026-09-01T12:00:40", "bet365", "0-0", 26, 0.5, 1.68),
            ("betsapi", "2026-09-01T12:04:00", "bet365", "1-0", 29, 1.5, 1.80),
            ("api_football", "2026-09-01T12:04:20", "api-football", "1-0", 29, 1.5, 1.60),
            ("betsapi", "2026-09-01T12:04:40", "bet365", "1-0", 30, 1.5, 1.78),
        )
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (?, ?, ?, 'oferta_monitorada', 'FT', 'gol_ft', ?)
                """,
                [
                    (
                        partida_id,
                        fonte,
                        horario,
                        json.dumps({
                            "bookmaker": bookmaker,
                            "placar": placar,
                            "minuto": minuto,
                            "linha": linha,
                            "odd": odd,
                        }),
                    )
                    for (
                        fonte, horario, bookmaker, placar, minuto, linha, odd
                    ) in ofertas
                ],
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
            ancora_convergencia="2026-09-01T11:59:00",
        )

        observacional = resultado["recorte_observacional_executavel"]
        convergencia = resultado[
            "recorte_convergencia_preco_prospectivo"
        ]
        self.assertGreaterEqual(observacional["candidatos_brutos"], 2)
        self.assertEqual(1, observacional["candidatos_independentes"])
        self.assertEqual(
            "primeiro_candidato_por_partida",
            observacional["unidade_independente"],
        )
        self.assertGreaterEqual(convergencia["candidatos_brutos"], 2)
        self.assertEqual(1, convergencia["candidatos_independentes"])
        self.assertTrue(convergencia["criterios"]["uma_entrada_por_partida"])

    def test_convergencia_captura_gap_menor_e_confirma_queda(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:00",
            "url": "https://packball.com/pt/matches/78/match/g-h/live",
            "mandante": "G", "visitante": "H", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        ofertas = (
            (
                "betsapi", "2026-09-01T12:00:00",
                '{"bookmaker":"bet365","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.70}',
            ),
            (
                "api_football", "2026-09-01T12:00:20",
                '{"bookmaker":"api-football","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.66}',
            ),
            (
                "betsapi", "2026-09-01T12:02:00",
                '{"bookmaker":"bet365","placar":"0-0",'
                '"minuto":26,"linha":0.5,"odd":1.67}',
            ),
        )
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (?, ?, ?, 'oferta_monitorada', 'FT', 'gol_ft', ?)
                """,
                [
                    (partida_id, fonte, horario, oferta)
                    for fonte, horario, oferta in ofertas
                ],
            )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
            ancora_convergencia="2026-09-01T11:59:00",
        )
        antigo = resultado["recorte_observacional_executavel"]
        self.assertEqual(0, antigo["candidatos_independentes"])
        recorte = resultado["recorte_convergencia_preco_prospectivo"]
        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(1, recorte["total"]["com_seguimento"])
        self.assertEqual(1, recorte["total"]["convergiram"])
        self.assertEqual("aguardando_coorte_futura", recorte["decisao"])
        self.assertFalse(recorte["vantagem_executavel_comprovada"])
        self.assertFalse(recorte["aplicacao_sinais"])
        self.assertFalse(recorte["telegram"])
        self.assertFalse(recorte["promocao_automatica"])

    def test_convergencia_inicia_apos_as_duas_fontes(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:00:00",
            "url": "https://packball.com/pt/matches/79/match/i-j/live",
            "mandante": "I", "visitante": "J", "placar": "0-0",
            "status": "25 '", "qualidade": {"pontuacao": 90},
        })
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        ofertas = (
            (
                "betsapi", "2026-09-01T12:00:00",
                '{"bookmaker":"bet365","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.70}',
            ),
            (
                "betsapi", "2026-09-01T12:00:10",
                '{"bookmaker":"bet365","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.70}',
            ),
            (
                "api_football", "2026-09-01T12:00:20",
                '{"bookmaker":"api-football","placar":"0-0",'
                '"minuto":25,"linha":0.5,"odd":1.66}',
            ),
        )
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado, periodo,
                    mercado, oferta_json
                ) VALUES (?, ?, ?, 'oferta_monitorada', 'FT', 'gol_ft', ?)
                """,
                [
                    (partida_id, fonte, horario, oferta)
                    for fonte, horario, oferta in ofertas
                ],
            )
        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
            ancora_convergencia="2026-09-01T11:59:00",
        )
        recorte = resultado["recorte_convergencia_preco_prospectivo"]
        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(0, recorte["total"]["com_seguimento"])

    def test_definicao_convergencia_e_ancorada_e_imutavel(self):
        primeira = _obter_ou_criar_definicao_convergencia(self.banco)
        segunda = _obter_ou_criar_definicao_convergencia(self.banco)
        self.assertEqual(primeira, segunda)
        self.assertEqual(
            "primeiro_candidato_por_partida", primeira["independencia"]
        )
        self.assertEqual(
            "convergencia-preco-bet365-prospectiva-v3",
            primeira["versao"],
        )
        linha = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (CHAVE_DEFINICAO_CONVERGENCIA,),
        ).fetchone()
        adulterada = json.loads(linha["valor"])
        adulterada["delta_relativo_minimo"] = 0.99
        with self.assertRaises(sqlite3.IntegrityError):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor=? WHERE chave=?",
                    (
                        json.dumps(adulterada),
                        CHAVE_DEFINICAO_CONVERGENCIA,
                    ),
                )
        self.assertEqual(
            primeira,
            _obter_ou_criar_definicao_convergencia(self.banco),
        )

    def salvar_escanteios(
        self, horario, odd_packball, odd_betsapi,
        *, horario_packball=None, horario_betsapi=None,
        status="60 '", placar="0-0",
    ):
        horario_packball = horario_packball or horario
        horario_betsapi = horario_betsapi or horario
        return self.banco.salvar_registro({
            "coletado_em": horario,
            "url": "https://packball.com/pt/matches/142/match/c-d/live",
            "mandante": "C", "visitante": "D",
            "placar": placar, "status": status,
            "qualidade": {"pontuacao": 90},
            "odds": {"ao_vivo": [{
                "mercado": "Escanteios asiaticos",
                "categoria": "escanteios",
                "escopo": "total",
                "tipo_mercado": "asiatico",
                "fonte": "packball",
                "coletado_em": horario_packball,
                "ofertas": [
                    {
                        "linha": 7.5, "over": odd_packball,
                        "under": 2.2,
                        "coletado_em": horario_packball,
                    },
                    {
                        "linha": 7.5, "over": odd_betsapi,
                        "under": 2.2, "fonte": "betsapi",
                        "bookmaker": "bet365",
                        "coletado_em": horario_betsapi,
                    },
                ],
            }]},
        })

    def test_convergencia_escanteios_usa_preco_e_resultado_futuros(self):
        self.salvar_escanteios(
            "2026-09-01T12:00:00", 1.50, 1.56
        )
        self.salvar_escanteios(
            "2026-09-01T12:02:00", 1.50, 1.52, status="62 '"
        )
        self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:30:00",
            "url": "https://packball.com/pt/matches/142/match/c-d/live",
            "mandante": "C", "visitante": "D", "placar": "1-0",
            "status": "Finalizado",
            "estatisticas": {"Escanteios": "5-3"},
            "qualidade": {"pontuacao": 90},
        })

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
            ancora_convergencia="2026-09-01T11:59:00",
            ancora_convergencia_escanteios="2026-09-01T11:59:00",
        )

        recorte = resultado[
            "recorte_convergencia_escanteios_prospectivo"
        ]
        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(1, recorte["total"]["com_seguimento"])
        self.assertEqual(1, recorte["total"]["convergiram"])
        self.assertGreaterEqual(recorte["registros_odds_temporais"], 2)
        self.assertEqual(
            1,
            recorte["total"]["resultados_escanteios_ft"]["resultados"],
        )
        self.assertEqual(
            0.56,
            recorte["total"]["resultados_escanteios_ft"][
                "roi_odd_melhor"
            ],
        )
        self.assertEqual("aguardando_coorte_futura", recorte["decisao"])
        self.assertFalse(recorte["aplicacao_sinais"])
        self.assertFalse(recorte["telegram"])
        self.assertFalse(recorte["promocao_automatica"])

    def test_convergencia_escanteios_inicia_apos_duas_fontes(self):
        self.salvar_escanteios(
            "2026-09-01T12:00:20", 1.50, 1.56,
            horario_packball="2026-09-01T12:00:20",
            horario_betsapi="2026-09-01T12:00:00",
        )
        self.salvar_escanteios(
            "2026-09-01T12:00:10", 1.50, 1.52,
            horario_packball="2026-09-01T12:00:10",
            horario_betsapi="2026-09-01T12:00:10",
            status="61 '",
        )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
            ancora_convergencia="2026-09-01T11:59:00",
            ancora_convergencia_escanteios="2026-09-01T11:59:00",
        )
        recorte = resultado[
            "recorte_convergencia_escanteios_prospectivo"
        ]

        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(0, recorte["total"]["com_seguimento"])

    def test_convergencia_escanteios_descarta_seguimento_antigo(self):
        self.salvar_escanteios(
            "2026-09-01T12:00:00", 1.50, 1.56
        )
        self.salvar_escanteios(
            "2026-09-01T12:06:00", 1.50, 1.52,
            horario_packball="2026-09-01T12:02:00",
            horario_betsapi="2026-09-01T12:02:00",
            status="66 '",
        )

        resultado = avaliar_desajustes_odds(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            ancora_executavel="2026-09-01T11:59:00",
            ancora_observacional="2026-09-01T11:59:00",
            ancora_convergencia="2026-09-01T11:59:00",
            ancora_convergencia_escanteios="2026-09-01T11:59:00",
        )
        recorte = resultado[
            "recorte_convergencia_escanteios_prospectivo"
        ]

        self.assertEqual(1, recorte["candidatos_independentes"])
        self.assertEqual(0, recorte["total"]["com_seguimento"])
        self.assertGreaterEqual(recorte["observacoes_invalidas"], 2)

    def test_definicao_convergencia_escanteios_e_imutavel(self):
        primeira = _obter_ou_criar_definicao_convergencia_escanteios(
            self.banco
        )
        segunda = _obter_ou_criar_definicao_convergencia_escanteios(
            self.banco
        )
        self.assertEqual(primeira, segunda)
        linha = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (CHAVE_DEFINICAO_CONVERGENCIA_ESCANTEIOS,),
        ).fetchone()
        adulterada = json.loads(linha["valor"])
        adulterada["delta_absoluto_minimo"] = 0.99
        with self.assertRaises(sqlite3.IntegrityError):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor=? WHERE chave=?",
                    (
                        json.dumps(adulterada),
                        CHAVE_DEFINICAO_CONVERGENCIA_ESCANTEIOS,
                    ),
                )

    @staticmethod
    def _comparacao_sem_vig(
        selecao, odd_a, odd_b, *, partida_id=10, snapshot_id=20,
        categoria="gols", periodo="FT", linha=2.5,
        observado_em="2026-09-01T12:00:20",
    ):
        return {
            "id": 1 if selecao == "over" else 2,
            "partida_id": partida_id,
            "snapshot_id": snapshot_id,
            "observado_em": observado_em,
            "categoria": categoria,
            "escopo": "total",
            "periodo": periodo,
            "linha": linha,
            "selecao": selecao,
            "fonte_a": "betsapi",
            "bookmaker_a": "bet365",
            "odd_a": odd_a,
            "coletado_em_a": "2026-09-01T12:00:00",
            "placar_fonte_a": "0-0",
            "minuto_fonte_a": 30.0,
            "fonte_b": "the_odds_api",
            "bookmaker_b": "pinnacle",
            "odd_b": odd_b,
            "coletado_em_b": "2026-09-01T12:00:10",
            "placar_fonte_b": "0-0",
            "minuto_fonte_b": 30.0,
            "estado": "desajuste_candidato",
        }

    def test_edge_sem_vig_exige_par_completo_e_remove_margens(self):
        documento = _obter_ou_criar_definicao_edge_sem_vig(
            self.banco, ancora="2026-09-01T11:59:00"
        )
        resultado = _resumir_edge_sem_vig_multifonte([
            self._comparacao_sem_vig("over", 2.10, 1.90),
            self._comparacao_sem_vig("under", 1.80, 1.95),
        ], documento)

        self.assertEqual(1, resultado["fotografias_completas"])
        self.assertEqual(1, resultado["candidatos_brutos"])
        self.assertEqual(1, resultado["coorte"])
        self.assertEqual(
            {"the_odds_api": 1}, resultado["por_fonte_controle"]
        )
        self.assertAlmostEqual(0.063636, resultado["ev_medio_candidatos"])
        self.assertTrue(resultado["selecao_antes_resultado"])
        self.assertFalse(resultado["vantagem_executavel_comprovada"])
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_edge_sem_vig_descarta_margem_implausivel(self):
        documento = _obter_ou_criar_definicao_edge_sem_vig(
            self.banco, ancora="2026-09-01T11:59:00"
        )
        resultado = _resumir_edge_sem_vig_multifonte([
            self._comparacao_sem_vig("over", 2.10, 1.90),
            self._comparacao_sem_vig("under", 1.20, 1.95),
        ], documento)

        self.assertEqual(0, resultado["fotografias_completas"])
        self.assertEqual(
            1,
            resultado["exclusoes"]["margem_executavel_implausivel"],
        )
        self.assertEqual(
            "aguardando_fotografias_completas", resultado["decisao"]
        )

    def test_definicao_edge_sem_vig_e_imutavel(self):
        primeira = _obter_ou_criar_definicao_edge_sem_vig(self.banco)
        segunda = _obter_ou_criar_definicao_edge_sem_vig(self.banco)
        self.assertEqual(primeira, segunda)
        linha = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (CHAVE_DEFINICAO_EDGE_SEM_VIG,),
        ).fetchone()
        adulterada = json.loads(linha["valor"])
        adulterada["ev_minimo"] = 0.99
        with self.assertRaises(sqlite3.IntegrityError):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor=? WHERE chave=?",
                    (
                        json.dumps(adulterada),
                        CHAVE_DEFINICAO_EDGE_SEM_VIG,
                    ),
                )

    def test_liquidacao_edge_sem_vig_gols_ft_mede_resultado_futuro(self):
        self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:30:00",
            "url": "https://packball.com/pt/matches/210/match/e-f/live",
            "mandante": "E", "visitante": "F", "placar": "2-1",
            "status": "Finalizado", "qualidade": {"pontuacao": 90},
        })
        partida_id = int(self.banco.conexao.execute(
            "SELECT id FROM partidas WHERE packball_url LIKE '%/210/%'"
        ).fetchone()[0])
        documento = _obter_ou_criar_definicao_edge_sem_vig(
            self.banco, ancora="2026-09-01T11:59:00"
        )
        politica = _obter_ou_criar_politica_liquidacao_edge_sem_vig(
            self.banco, registrado_em="2026-09-01T11:59:00"
        )

        resultado = _resumir_edge_sem_vig_multifonte([
            self._comparacao_sem_vig(
                "over", 2.10, 1.90, partida_id=partida_id
            ),
            self._comparacao_sem_vig(
                "under", 1.80, 1.95, partida_id=partida_id
            ),
        ], documento, banco=self.banco, politica_liquidacao=politica)

        liquidacao = resultado["liquidacao_resultados"]
        gols = liquidacao["por_mercado"]["gols:FT"]
        self.assertEqual(1, gols["coorte"])
        self.assertEqual(1, gols["total"]["resultados"])
        self.assertEqual(1, gols["total"]["greens"])
        self.assertAlmostEqual(1.1, gols["total"]["roi_real"])
        self.assertAlmostEqual(0.0636, gols["total"]["ev_previsto_medio"])
        self.assertFalse(gols["vantagem_resultados_comprovada"])
        self.assertFalse(liquidacao["vantagem_executavel_comprovada"])
        self.assertFalse(liquidacao["aplicacao_sinais"])

    def test_liquidacao_edge_sem_vig_separa_escanteios_ft(self):
        self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:30:00",
            "url": "https://packball.com/pt/matches/211/match/g-h/live",
            "mandante": "G", "visitante": "H", "placar": "1-0",
            "status": "Finalizado", "estatisticas": {"Escanteios": "5-3"},
            "qualidade": {"pontuacao": 90},
        })
        partida_id = int(self.banco.conexao.execute(
            "SELECT id FROM partidas WHERE packball_url LIKE '%/211/%'"
        ).fetchone()[0])
        documento = _obter_ou_criar_definicao_edge_sem_vig(
            self.banco, ancora="2026-09-01T11:59:00"
        )
        politica = _obter_ou_criar_politica_liquidacao_edge_sem_vig(
            self.banco, registrado_em="2026-09-01T11:59:00"
        )
        resultado = _resumir_edge_sem_vig_multifonte([
            self._comparacao_sem_vig(
                "over", 2.10, 1.90, partida_id=partida_id,
                categoria="escanteios", linha=7.5,
            ),
            self._comparacao_sem_vig(
                "under", 1.80, 1.95, partida_id=partida_id,
                categoria="escanteios", linha=7.5,
            ),
        ], documento, banco=self.banco, politica_liquidacao=politica)

        liquidacao = resultado["liquidacao_resultados"]
        cantos = liquidacao["por_mercado"]["escanteios:FT"]
        self.assertEqual(1, cantos["total"]["resultados"])
        self.assertEqual(1, cantos["total"]["greens"])
        self.assertEqual(0, liquidacao["por_mercado"]["gols:FT"]["coorte"])

    def test_liquidacao_edge_sem_vig_exclui_linha_com_push(self):
        documento = _obter_ou_criar_definicao_edge_sem_vig(
            self.banco, ancora="2026-09-01T11:59:00"
        )
        politica = _obter_ou_criar_politica_liquidacao_edge_sem_vig(
            self.banco, registrado_em="2026-09-01T11:59:00"
        )
        resultado = _resumir_edge_sem_vig_multifonte([
            self._comparacao_sem_vig("over", 2.10, 1.90, linha=2.25),
            self._comparacao_sem_vig("under", 1.80, 1.95, linha=2.25),
        ], documento, banco=self.banco, politica_liquidacao=politica)

        liquidacao = resultado["liquidacao_resultados"]
        self.assertEqual(0, liquidacao["candidatos_liquidaveis"])
        self.assertEqual(
            1, liquidacao["exclusoes"]["linha_com_push_ou_quarter_line"]
        )

    def test_liquidacao_edge_sem_vig_exclui_candidato_anterior_politica(self):
        documento = _obter_ou_criar_definicao_edge_sem_vig(
            self.banco, ancora="2026-09-01T11:59:00"
        )
        politica = _obter_ou_criar_politica_liquidacao_edge_sem_vig(
            self.banco, registrado_em="2026-09-01T12:01:00"
        )
        resultado = _resumir_edge_sem_vig_multifonte([
            self._comparacao_sem_vig("over", 2.10, 1.90),
            self._comparacao_sem_vig("under", 1.80, 1.95),
        ], documento, banco=self.banco, politica_liquidacao=politica)

        liquidacao = resultado["liquidacao_resultados"]
        self.assertEqual(0, liquidacao["candidatos_liquidaveis"])
        self.assertEqual(
            1,
            liquidacao["exclusoes"][
                "candidato_anterior_politica_liquidacao"
            ],
        )

    def test_liquidacao_edge_sem_vig_rejeita_resultado_anterior(self):
        self.banco.salvar_registro({
            "coletado_em": "2026-09-01T11:58:00",
            "url": "https://packball.com/pt/matches/212/match/i-j/live",
            "mandante": "I", "visitante": "J", "placar": "2-1",
            "status": "Finalizado", "qualidade": {"pontuacao": 90},
        })
        partida_id = int(self.banco.conexao.execute(
            "SELECT id FROM partidas WHERE packball_url LIKE '%/212/%'"
        ).fetchone()[0])
        documento = _obter_ou_criar_definicao_edge_sem_vig(
            self.banco, ancora="2026-09-01T11:59:00"
        )
        politica = _obter_ou_criar_politica_liquidacao_edge_sem_vig(
            self.banco, registrado_em="2026-09-01T11:59:00"
        )
        resultado = _resumir_edge_sem_vig_multifonte([
            self._comparacao_sem_vig(
                "over", 2.10, 1.90, partida_id=partida_id
            ),
            self._comparacao_sem_vig(
                "under", 1.80, 1.95, partida_id=partida_id
            ),
        ], documento, banco=self.banco, politica_liquidacao=politica)

        total = resultado["liquidacao_resultados"]["por_mercado"][
            "gols:FT"
        ]["total"]
        self.assertEqual(0, total["resultados"])
        self.assertEqual(1, total["pendentes"])
        self.assertEqual(1, total["cronologia_invalida"])
        self.assertFalse(total["resultado_posterior_selecao"])

    def test_politica_liquidacao_edge_sem_vig_e_imutavel(self):
        primeira = _obter_ou_criar_politica_liquidacao_edge_sem_vig(
            self.banco
        )
        segunda = _obter_ou_criar_politica_liquidacao_edge_sem_vig(
            self.banco
        )
        self.assertEqual(primeira, segunda)
        linha = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (CHAVE_POLITICA_LIQUIDACAO_EDGE_SEM_VIG,),
        ).fetchone()
        adulterada = json.loads(linha["valor"])
        adulterada["resultados_minimos"] = 1
        with self.assertRaises(sqlite3.IntegrityError):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor=? WHERE chave=?",
                    (
                        json.dumps(adulterada),
                        CHAVE_POLITICA_LIQUIDACAO_EDGE_SEM_VIG,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
