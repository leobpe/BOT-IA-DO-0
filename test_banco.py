import hashlib
import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from banco import (
    BancoMonitor,
    GATILHOS_OBRIGATORIOS,
    INDICES_OBRIGATORIOS,
    auditar_compatibilidade,
    auditar_historico_drift_simulacoes,
    extrair_packball_id,
    normalizar_texto,
    registrar_historico_drift_simulacoes,
    resumir_historico_drift_simulacoes,
)
from auditoria_ligas_sombra import (
    registrar_ou_obter_validacao_prospectiva_ligas,
)
from custodia_estimativa_historica import (
    GATILHOS_SQL as GATILHOS_ESTIMATIVA_HISTORICA,
    PREFIXO_CHAVE as PREFIXO_ESTIMATIVA_HISTORICA,
    auditar_gatilhos as auditar_gatilhos_estimativa_historica,
)
from avaliacao_contexto import registrar_ou_obter_ancoras_contexto
from relatorio_simulacoes import (
    registrar_ou_obter_conclusao_experimento_filtro,
    registrar_ou_obter_experimento_filtro,
)


def identidade_evento_teste(
    placar="0-0",
    fonte="betsapi",
    evento_externo_id="evento-123",
    orientacao="direta",
):
    return {
        "schema": "identidade-evento-odd-v1",
        "confirmada": True,
        "fonte": fonte,
        "evento_externo_id": evento_externo_id,
        "orientacao": orientacao,
        "similaridade": 0.95,
        "mandante_normalizado": "Time A",
        "visitante_normalizado": "Time B",
        "placar_normalizado": placar,
        "metodo": "teste",
    }


def origem_mercado_teste(
    linha=0.5, fonte="betsapi", lados=("over", "under"),
):
    return {
        "schema": "origem-mercado-odd-v1",
        "fonte": fonte,
        "identificador": "mercado-123",
        "nome": "Match Goals",
        "linha": linha,
        "lados": list(lados),
        "bookmaker": "bet365",
    }


class BancoMonitorTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_banco_monitor.db"
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

    def registro(self):
        return {
            "coletado_em": datetime.now().replace(microsecond=0).isoformat(),
            "url": "https://packball.com/pt/matches/1/match/a-vs-b/live",
            "mandante": "Time A",
            "visitante": "Time B",
            "placar": "1-0",
            "status": "55 '",
            "estatisticas": {
                "Índice de pressão": "60-40",
                "Chutes": "10-5",
                "Escanteios": "4-2",
            },
            "evolucao": {"5": None, "10": None, "15": None},
            "odds": {
                "ao_vivo": [
                    {
                        "mercado": "Total Gols",
                        "dados": "Over Under 2.5 1.80 1.90",
                    }
                ],
                "pre_jogo": [],
            },
            "confirmacao_api": {
                "fixture_id": 123,
                "orientacao": "direta",
            },
        }

    def test_compara_odds_exatas_entre_snapshots_dentro_de_60s(self):
        primeiro = self.registro()
        primeiro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0",
            "status": "25 '",
            "odds": {"pre_jogo": [], "ao_vivo": [{
                "mercado": "Total Gols",
                "dados": "Match Goals",
                "categoria": "gols",
                "escopo": "total",
                "fonte": "packball",
                "coletado_em": "2026-09-01T12:00:00",
                "ofertas": [{
                    "linha": 2.5, "over": 1.50, "under": 2.40,
                }],
            }]},
        })
        segundo = self.registro()
        segundo.update({
            "coletado_em": "2026-09-01T12:00:20",
            "placar": "0-0",
            "status": "25 '",
            "odds": {"pre_jogo": [], "ao_vivo": [{
                "mercado": "Total Gols",
                "dados": "Match Goals",
                "categoria": "gols",
                "escopo": "total",
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "coletado_em": "2026-09-01T12:00:20",
                "ofertas": [{
                    "linha": 2.5, "over": 1.65, "under": 2.20,
                }],
            }]},
        })

        snapshot_a = self.banco.salvar_registro(primeiro)
        snapshot_b = self.banco.salvar_registro(segundo)
        linhas = self.banco.conexao.execute(
            """
            SELECT selecao, estado, snapshot_fonte_a, snapshot_fonte_b,
                   placar_fonte_a, placar_fonte_b,
                   motivos_json, intervalo_fontes_segundos
            FROM comparacoes_odds_fontes
            WHERE snapshot_id=?
            ORDER BY selecao
            """,
            (snapshot_b,),
        ).fetchall()

        self.assertEqual(2, len(linhas))
        self.assertEqual(
            {snapshot_a, snapshot_b},
            {linhas[0]["snapshot_fonte_a"], linhas[0]["snapshot_fonte_b"]},
        )
        self.assertEqual(20.0, linhas[0]["intervalo_fontes_segundos"])
        self.assertEqual("0-0", linhas[0]["placar_fonte_a"])
        self.assertEqual("0-0", linhas[0]["placar_fonte_b"])
        self.assertIn(
            "fontes_em_snapshots_temporais_distintos",
            json.loads(linhas[0]["motivos_json"]),
        )
        self.assertIn(
            "desajuste_candidato", {linha["estado"] for linha in linhas}
        )

    def test_referencia_sombra_e_persistida_sem_virar_odd_operacional(self):
        instante = "2026-09-11T01:00:00"
        registro = self.registro()
        registro.update({
            "coletado_em": instante,
            "placar": "0-0",
            "status": "25 '",
            "odds": {"pre_jogo": [], "ao_vivo": [{
                "categoria": "gols", "escopo": "total",
                "tipo_mercado": "total", "formato": "duas_opcoes",
                "fonte": "betsapi", "bookmaker": "bet365",
                "coletado_em": instante, "cache": False,
                "idade_segundos": 0.0,
                "ofertas": [{
                    "linha": 2.5, "over": 1.70, "under": 2.20,
                    "fonte": "betsapi", "bookmaker": "bet365",
                    "coletado_em": instante,
                }],
            }]},
            "odds_referencia_sombra": {
                "pre_jogo": [], "ao_vivo": [{
                    "categoria": "gols", "escopo": "total",
                    "tipo_mercado": "total", "formato": "duas_opcoes",
                    "fonte": "the_odds_api", "bookmaker": "pinnacle",
                    "coletado_em": instante, "cache": False,
                    "idade_segundos": 0.0,
                    "ofertas": [{
                        "linha": 2.5, "over": 1.50, "under": 2.50,
                        "fonte": "the_odds_api", "bookmaker": "pinnacle",
                        "coletado_em": instante,
                    }],
                }],
            },
        })

        snapshot_id = self.banco.salvar_registro(registro)
        tipos = {
            linha["tipo"]: linha["total"]
            for linha in self.banco.conexao.execute(
                "SELECT tipo, COUNT(*) total FROM odds "
                "WHERE snapshot_id=? GROUP BY tipo",
                (snapshot_id,),
            ).fetchall()
        }
        comparacoes = self.banco.conexao.execute(
            "SELECT selecao, fonte_a, fonte_b FROM comparacoes_odds_fontes "
            "WHERE snapshot_id=? ORDER BY selecao",
            (snapshot_id,),
        ).fetchall()

        self.assertEqual({"ao_vivo": 1, "referencia_sombra": 1}, tipos)
        self.assertEqual(1, len(registro["odds"]["ao_vivo"]))
        self.assertEqual(2, len(comparacoes))
        self.assertTrue(all(
            {linha["fonte_a"], linha["fonte_b"]}
            == {"betsapi", "the_odds_api"}
            for linha in comparacoes
        ))

    def test_descarta_gap_temporal_quando_placar_mudou(self):
        primeiro = self.registro()
        primeiro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0",
            "status": "25 '",
            "odds": {"pre_jogo": [], "ao_vivo": [{
                "mercado": "Total Gols", "dados": "Match Goals",
                "categoria": "gols", "escopo": "total",
                "fonte": "packball",
                "coletado_em": "2026-09-01T12:00:00",
                "ofertas": [{
                    "linha": 2.5, "over": 1.50, "under": 2.40,
                }],
            }]},
        })
        segundo = self.registro()
        segundo.update({
            "coletado_em": "2026-09-01T12:00:20",
            "placar": "1-0",
            "status": "26 '",
            "odds": {"pre_jogo": [], "ao_vivo": [{
                "mercado": "Total Gols", "dados": "Match Goals",
                "categoria": "gols", "escopo": "total",
                "fonte": "betsapi", "bookmaker": "bet365",
                "coletado_em": "2026-09-01T12:00:20",
                "ofertas": [{
                    "linha": 2.5, "over": 2.20, "under": 1.60,
                }],
            }]},
        })

        self.banco.salvar_registro(primeiro)
        snapshot = self.banco.salvar_registro(segundo)
        linhas = self.banco.conexao.execute(
            """
            SELECT estado, motivos_json, placar_fonte_a, placar_fonte_b
            FROM comparacoes_odds_fontes WHERE snapshot_id=?
            """,
            (snapshot,),
        ).fetchall()

        self.assertEqual(2, len(linhas))
        self.assertTrue(all(
            linha["estado"] == "descartado_estado_jogo_divergente"
            for linha in linhas
        ))
        self.assertTrue(all(
            "placar_mudou_entre_as_fontes"
            in json.loads(linha["motivos_json"])
            for linha in linhas
        ))
        self.assertEqual(
            {"0-0", "1-0"},
            {linhas[0]["placar_fonte_a"], linhas[0]["placar_fonte_b"]},
        )

    def test_fila_rapida_persiste_comparacao_sem_nova_chamada_api(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0",
            "status": "46 '",
            "odds": {"pre_jogo": [], "ao_vivo": [{
                "mercado": "Total Gols", "dados": "Match Goals",
                "categoria": "gols", "escopo": "total",
                "fonte": "packball",
                "coletado_em": "2026-09-01T12:00:00",
                "ofertas": [{"linha": 2.5, "over": 1.30}],
            }]},
        })
        snapshot_id = self.banco.salvar_registro(registro)
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()[0]
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO sinais (
                    partida_id, snapshot_id, criado_em, mercado, linha, odd,
                    pontuacao_tecnica, regra_versao, motivos_json,
                    features_json, status
                ) VALUES (?, ?, '2026-09-01T12:00:00', 'gol_ft', '2.5',
                          1.30, 85, 'teste', '[]', ?, 'rejeitado')
                """,
                (partida_id, snapshot_id, json.dumps({
                    "fonte_odds": "packball",
                    "bookmaker_odds": "",
                    "coletado_em_odds": "2026-09-01T12:00:00",
                })),
            )
        resultado = self.banco.registrar_comparacao_acompanhamento_odd_api(
            cursor.lastrowid,
            {
                "linha": 2.5, "odd": 1.50, "fonte": "betsapi",
                "bookmaker": "bet365",
                "coletado_em": "2026-09-01T12:00:10",
                "idade_segundos": 0.0, "cache": False,
            },
            {"placar": "0-0", "status": "46'", "minuto": 46},
            consultado_em="2026-09-01T12:00:10",
        )
        repetido = self.banco.registrar_comparacao_acompanhamento_odd_api(
            cursor.lastrowid,
            {
                "linha": 2.5, "odd": 1.50, "fonte": "betsapi",
                "bookmaker": "bet365",
                "coletado_em": "2026-09-01T12:00:10",
            },
            {"placar": "0-0", "status": "46'", "minuto": 46},
            consultado_em="2026-09-01T12:00:10",
        )
        linha = self.banco.conexao.execute(
            """
            SELECT estado, minuto_fonte_a, minuto_fonte_b,
                   diferenca_minutos, versao
            FROM comparacoes_odds_fontes
            WHERE snapshot_id=? AND selecao='over'
            """,
            (snapshot_id,),
        ).fetchone()

        self.assertEqual(1, resultado["persistidos"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertEqual(0, resultado["chamadas_api_adicionais"])
        self.assertEqual(0, repetido["persistidos"])
        self.assertEqual("desajuste_candidato", linha["estado"])
        self.assertEqual(46.0, linha["minuto_fonte_a"])
        self.assertEqual(46.0, linha["minuto_fonte_b"])
        self.assertEqual(0.0, linha["diferenca_minutos"])
        self.assertIn("estado-minuto-v4", linha["versao"])

    def test_alvo_congela_corroboracao_betsapi_api_football_sem_gating(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0",
            "status": "46 '",
        })
        snapshot_id = self.banco.salvar_registro(registro)
        sinal_id = self.banco.salvar_candidatos(snapshot_id, [{
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": 1.30,
            "pontuacao_tecnica": 90,
            "regra_versao": "teste-corroboracao-multifonte-v1",
            "status": "rejeitado",
        }])[0]
        instante = "2026-09-01T12:00:10"

        def mercado(fonte, over, under, evento_id):
            return {
                "categoria": "gols",
                "escopo": "total",
                "tipo_mercado": "total",
                "formato": "duas_opcoes",
                "fonte": fonte,
                "bookmaker": "bet365",
                "coletado_em": instante,
                "idade_segundos": 0.0,
                "cache": False,
                "identidade_evento": identidade_evento_teste(
                    "0-0", fonte=fonte, evento_externo_id=evento_id,
                ),
                "ofertas": [{
                    "linha": 2.5,
                    "over": over,
                    "under": under,
                    "fonte": fonte,
                    "bookmaker": "bet365",
                    "coletado_em": instante,
                    "idade_segundos": 0.0,
                    "cache": False,
                    "origem_mercado": origem_mercado_teste(
                        2.5, fonte=fonte,
                    ),
                }],
                "ofertas_ht": [],
            }

        resultado = (
            self.banco.registrar_corroboracao_acompanhamento_odd_api(
                sinal_id,
                {"ao_vivo": [
                    mercado("betsapi", 1.40, 2.80, "bets-123"),
                    mercado("api_football", 1.42, 2.76, "123"),
                ]},
                {"placar": "0-0", "minuto": 46, "status": "46 '"},
                consultado_em=instante,
            )
        )
        linhas = self.banco.conexao.execute(
            """
            SELECT fonte_a, fonte_b, selecao, motivos_json, versao
            FROM comparacoes_odds_fontes
            WHERE snapshot_id=?
              AND motivos_json LIKE '%corroboracao_odd_entrada_rapida%'
            ORDER BY selecao
            """,
            (snapshot_id,),
        ).fetchall()
        status_sinal = self.banco.conexao.execute(
            "SELECT status FROM sinais WHERE id=?", (sinal_id,)
        ).fetchone()[0]

        self.assertEqual("corroboracao_registrada", resultado["estado"])
        self.assertEqual(2, resultado["persistidos"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["promocao_automatica"])
        self.assertEqual(["api_football", "betsapi"], resultado["fontes_validas"])
        self.assertEqual(2, len(linhas))
        self.assertEqual({"over", "under"}, {linha["selecao"] for linha in linhas})
        self.assertTrue(all(
            {linha["fonte_a"], linha["fonte_b"]}
            == {"betsapi", "api_football"}
            for linha in linhas
        ))
        self.assertTrue(all(
            "corroboracao_odd_entrada_rapida"
            in json.loads(linha["motivos_json"])
            for linha in linhas
        ))
        self.assertTrue(all("estado-minuto-v4" in linha["versao"] for linha in linhas))
        self.assertEqual("rejeitado", status_sinal)

    def test_corroboracao_descarta_fonte_com_identidade_divergente(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0",
            "status": "46 '",
        })
        snapshot_id = self.banco.salvar_registro(registro)
        sinal_id = self.banco.salvar_candidatos(snapshot_id, [{
            "mercado": "gol_ft", "linha": 2.5, "odd": 1.30,
            "regra_versao": "teste-corroboracao-rejeicao-v1",
            "status": "rejeitado",
        }])[0]
        instante = "2026-09-01T12:00:10"

        def mercado(fonte, placar):
            return {
                "categoria": "gols", "escopo": "total",
                "tipo_mercado": "total", "formato": "duas_opcoes",
                "fonte": fonte, "bookmaker": "bet365",
                "coletado_em": instante, "idade_segundos": 0.0,
                "cache": False,
                "identidade_evento": identidade_evento_teste(
                    placar, fonte=fonte, evento_externo_id=fonte,
                ),
                "ofertas": [{
                    "linha": 2.5, "over": 1.40, "under": 2.80,
                    "fonte": fonte, "bookmaker": "bet365",
                    "coletado_em": instante, "idade_segundos": 0.0,
                    "cache": False,
                    "origem_mercado": origem_mercado_teste(2.5, fonte),
                }],
                "ofertas_ht": [],
            }

        resultado = (
            self.banco.registrar_corroboracao_acompanhamento_odd_api(
                sinal_id,
                {"ao_vivo": [
                    mercado("betsapi", "0-0"),
                    mercado("api_football", "1-0"),
                ]},
                {"placar": "0-0", "minuto": 46, "status": "46 '"},
                consultado_em=instante,
            )
        )

        self.assertEqual("fontes_independentes_insuficientes", resultado["estado"])
        self.assertEqual(0, resultado["persistidos"])
        self.assertEqual(["betsapi"], resultado["fontes_validas"])
        self.assertIn("evento_odd_placar_divergente", resultado["descartes"])
        self.assertEqual(0, self.banco.conexao.execute(
            "SELECT COUNT(*) FROM comparacoes_odds_fontes "
            "WHERE motivos_json LIKE '%corroboracao_odd_entrada_rapida%'"
        ).fetchone()[0])

    def test_persiste_taxas_sazonais_de_ligas_sem_apagar_anos(self):
        base = {
            "league_id": 651,
            "pais": "Brazil",
            "liga": "Serie B",
            "liga_normalizada": "serie b",
            "periodo": "2t",
            "jogos_realizados": 200,
            "jogos_previstos": 384,
            "jogos_com_stats": 200,
            "over_0_5": 0.75,
            "over_1_5": 0.37,
            "over_2_5": 0.12,
            "fonte": "packball_ligas_sazonal",
            "versao": "teste",
        }
        atual = {
            **base,
            "temporada": "2026",
            "coletado_em": "2026-09-01T10:00:00",
        }
        anterior = {
            **base,
            "temporada": "2025",
            "coletado_em": "2025-09-01T10:00:00",
        }

        resultado = self.banco.salvar_taxas_ligas_gols([anterior, atual])
        linhas = self.banco.conexao.execute(
            "SELECT temporada FROM taxas_ligas_gols_packball ORDER BY temporada"
        ).fetchall()

        self.assertEqual(2, resultado["recebidos"])
        self.assertEqual(2, resultado["historico_inseridos"])
        self.assertEqual(["2025", "2026"], [linha[0] for linha in linhas])
        self.assertEqual(
            2,
            self.banco.resumir_historico_taxas_ligas_gols()["registros"],
        )
        carregadas = self.banco.carregar_taxas_ligas_gols()
        self.assertEqual("2026", carregadas[0]["temporada"])
        self.assertEqual(
            "2026-09-01T10:00:00",
            self.banco.ultima_coleta_taxas_ligas_gols()["coletado_em"],
        )

    def test_historico_taxas_ligas_preserva_drifts_e_e_imutavel(self):
        base = {
            "league_id": 651,
            "pais": "Brazil",
            "liga": "Serie B",
            "liga_normalizada": "serie b",
            "temporada": "2026",
            "periodo": "2t",
            "jogos_realizados": 200,
            "jogos_previstos": 384,
            "jogos_com_stats": 200,
            "over_0_5": 0.75,
            "over_1_5": 0.37,
            "over_2_5": 0.12,
            "fonte": "packball_ligas_sazonal",
            "versao": "teste",
        }
        primeira = {
            **base,
            "coletado_em": "2026-09-01T10:00:00",
        }
        segunda = {
            **base,
            "jogos_realizados": 204,
            "jogos_com_stats": 204,
            "over_0_5": 0.78,
            "coletado_em": "2026-09-01T16:00:00",
        }

        self.banco.salvar_taxas_ligas_gols([primeira])
        self.banco.salvar_taxas_ligas_gols([segunda])
        historico = self.banco.conexao.execute(
            """
            SELECT id, coletado_em, over_0_5
            FROM historico_taxas_ligas_gols_packball
            ORDER BY coletado_em
            """
        ).fetchall()
        atual = self.banco.conexao.execute(
            "SELECT coletado_em, over_0_5 FROM taxas_ligas_gols_packball"
        ).fetchone()

        self.assertEqual(2, len(historico))
        self.assertEqual(0.75, historico[0]["over_0_5"])
        self.assertEqual(0.78, historico[1]["over_0_5"])
        self.assertEqual("2026-09-01T16:00:00", atual["coletado_em"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.conexao.execute(
                """
                UPDATE historico_taxas_ligas_gols_packball
                SET over_0_5=0.10
                WHERE id=?
                """,
                (historico[0]["id"],),
            )

    def test_persiste_auditoria_da_fila_com_retencao_e_idempotencia(self):
        agora = datetime(2026, 9, 1, 14, 0, 0)
        registro = {
            "ciclo_em": agora.isoformat(),
            "packball_url": "https://packball.com/jogo/1",
            "mandante": "Time A",
            "visitante": "Time B",
            "liga": "Liga Teste",
            "minuto": 55,
            "posicao": 1,
            "processada": True,
            "acionavel": True,
            "fila_operacional": "urgente",
            "idade_segundos": 320,
            "atraso_segundos": 20,
            "em_foco": True,
            "scanner_prioritario": False,
            "pre_live_prioritario": True,
            "prioridade_liga_gols": 68.5,
            "prioridade_indicadores_lista": 72,
            "prioridade_api_lote": 18,
            "janelas_temporais": [10, 5, 10],
            "motivo": "processada",
        }
        self.banco.conexao.execute(
            """
            INSERT INTO auditoria_fila_packball (
                ciclo_em, registrado_em, packball_url, posicao,
                processada, acionavel, motivo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (agora - timedelta(days=8)).isoformat(),
                (agora - timedelta(days=8)).isoformat(),
                "https://packball.com/antigo",
                1, 0, 0, "orcamento_ciclo",
            ),
        )
        self.banco.conexao.commit()

        primeira = self.banco.salvar_auditoria_fila_packball(
            [registro], agora=agora, retencao_dias=7
        )
        segunda = self.banco.salvar_auditoria_fila_packball(
            [registro], agora=agora, retencao_dias=7
        )
        linha = self.banco.conexao.execute(
            "SELECT * FROM auditoria_fila_packball"
        ).fetchone()

        self.assertEqual(1, primeira["inseridos"])
        self.assertEqual(1, primeira["removidos_retencao"])
        self.assertEqual(0, segunda["inseridos"])
        self.assertEqual(1, segunda["duplicados"])
        self.assertEqual(1, linha["processada"])
        self.assertEqual(1, linha["acionavel"])
        self.assertEqual("[5, 10]", linha["janelas_temporais_json"])
        self.assertEqual("processada", linha["motivo"])

    def test_exploracao_sombra_e_unica_por_partida_mercado(self):
        snapshot = self.banco.salvar_registro(self.registro())
        self.assertFalse(self.banco.exploracao_sombra_ja_registrada(
            snapshot, "gol_ft", "sinais-v6"
        ))
        self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.8,
            "pontuacao_tecnica": 68,
            "regra_versao": "sinais-v6",
            "status": "simulacao",
            "features": {"exploracao_sombra": {"versao": "v1"}},
        }])

        self.assertTrue(self.banco.exploracao_sombra_ja_registrada(
            snapshot, "gol_ft", "sinais-v6"
        ))
        self.assertTrue(self.banco.exploracao_sombra_ja_registrada(
            snapshot, "gol_ft", "sinais-v6", "v1"
        ))
        self.assertFalse(self.banco.exploracao_sombra_ja_registrada(
            snapshot, "gol_ft", "sinais-v6", "v2"
        ))
        self.assertFalse(self.banco.exploracao_sombra_ja_registrada(
            snapshot, "gol_ht", "sinais-v6"
        ))
        repetido = {
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.8,
            "pontuacao_tecnica": 68,
            "regra_versao": "sinais-v6",
            "status": "simulacao",
            "features": {"exploracao_sombra": {"versao": "v1"}},
        }
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.salvar_candidatos(snapshot, [repetido])

        nova_versao = dict(repetido)
        nova_versao["features"] = {
            "exploracao_sombra": {"versao": "v2"}
        }
        ids = self.banco.salvar_candidatos(snapshot, [nova_versao])
        self.assertEqual(len(ids), 1)
        self.assertTrue(self.banco.exploracao_sombra_ja_registrada(
            snapshot, "gol_ft", "sinais-v6", "v2"
        ))

        primeiro_id = self.banco.conexao.execute(
            """SELECT MIN(id) FROM sinais
               WHERE json_extract(
                   features_json, '$.exploracao_sombra.versao'
               )='v1'"""
        ).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.conexao.execute(
                "UPDATE sinais SET odd=2.1 WHERE id=?", (primeiro_id,)
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.conexao.execute(
                "DELETE FROM sinais WHERE id=?", (primeiro_id,)
            )

    def test_auditoria_bloqueio_deduplica_por_partida_e_motivo(self):
        snapshot = self.banco.salvar_registro(self.registro())
        chave = "atividade_recente_insuficiente_gols"
        self.assertFalse(self.banco.auditoria_bloqueio_ja_registrada(
            snapshot, "gol_ft", "sinais-v6", "auditoria-v1", chave
        ))
        self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": 1.55,
            "pontuacao_tecnica": 72,
            "regra_versao": "sinais-v6",
            "status": "auditoria",
            "features": {"auditoria_bloqueio": {
                "versao": "auditoria-v1",
                "bloqueios_chave": chave,
            }},
        }])

        self.assertTrue(self.banco.auditoria_bloqueio_ja_registrada(
            snapshot, "gol_ft", "sinais-v6", "auditoria-v1", chave
        ))
        self.assertFalse(self.banco.auditoria_bloqueio_ja_registrada(
            snapshot, "gol_ft", "sinais-v6", "auditoria-v1",
            "historico_5min_insuficiente",
        ))
    def test_persiste_auditoria_da_the_odds_api_com_oferta(self):
        registro = self.registro()
        registro["qualidade"] = {
            "the_odds_api": {
                "ativa": True,
                "pareado": True,
                "motivo": "oferta_anexada",
                "evento_externo_id": "evt-1",
                "mandante_observado": "Time A",
                "visitante_observado": "Time B",
                "consultados": ["alternate_totals"],
                "anexados": ["gol_ft"],
            }
        }
        registro["odds"]["ao_vivo"][0].update({
            "categoria": "gols",
            "tipo_mercado": "total",
            "ofertas": [{
                "linha": 2.5, "over": 1.8, "under": 2.0,
                "fonte": "the_odds_api", "bookmaker": "pinnacle",
            }],
        })

        snapshot = self.banco.salvar_registro(registro)
        linha = self.banco.conexao.execute(
            "SELECT * FROM observacoes_fontes_odds "
            "WHERE fonte='the_odds_api'"
        ).fetchone()

        self.assertEqual(linha["estado"], "oferta_disponivel")
        self.assertEqual(linha["evento_externo_id"], "evt-1")
        self.assertEqual(linha["mercado"], "alternate_totals")
        self.assertEqual(linha["evidencia_referencia"], f"snapshot:{snapshot}")
        self.assertEqual(
            json.loads(linha["oferta_json"])[0]["oferta"]["over"], 1.8
        )

    def test_persiste_motivo_sem_cobertura_sem_inventar_oferta(self):
        registro = self.registro()
        registro["qualidade"] = {
            "the_odds_api": {
                "ativa": True,
                "pareado": False,
                "motivo": "competicao_nao_coberta",
                "consultados": [],
                "anexados": [],
            }
        }

        self.banco.salvar_registro(registro)
        linha = self.banco.conexao.execute(
            "SELECT estado, oferta_json FROM observacoes_fontes_odds"
        ).fetchone()

        self.assertEqual(linha["estado"], "competicao_nao_coberta")
        self.assertIsNone(linha["oferta_json"])

    def test_audita_amostragem_sombra_sem_misturar_odd_operacional(self):
        registro = self.registro()
        registro["odds"]["ao_vivo"].append({
            "categoria": "gols",
            "tipo_mercado": "total",
            "fonte": "the_odds_api",
            "ofertas": [{
                "linha": 2.5,
                "over": 1.80,
                "under": 2.00,
                "fonte": "the_odds_api",
                "bookmaker": "pinnacle",
            }],
        })
        registro["odds_referencia_sombra"] = {
            "pre_jogo": [], "ao_vivo": [],
        }
        registro["qualidade"] = {
            "the_odds_api": {
                "ativa": True,
                "pareado": True,
                "motivo": "oferta_anexada",
                "consultados": ["alternate_totals"],
                "amostragem_referencia_sombra": {
                    "ativa": True,
                    "pareado": False,
                    "motivo": "evento_nao_encontrado",
                    "consultados": [],
                    "reserva": {
                        "autorizada": True,
                        "tipo_amostra": "recuperacao_coorte_resultado",
                        "uso_dia": 3,
                        "uso_jogo_dia": 3,
                        "jogos_distintos_dia": 2,
                        "limite_efetivo_jogo_dia": 3,
                        "recuperacao_coorte_aplicada": True,
                    },
                    "recuperacao_coorte_solicitada": True,
                    "auditoria_amostragem": {
                        "versao": (
                            "amostragem-referencia-sombra-auditoria-v5"
                        ),
                        "ciclo_em": "2026-09-11T02:35:00",
                        "posicao_fila": 3,
                        "tarefas_ciclo": 8,
                        "fila_operacional": "exploracao",
                        "liga": "Liga Teste",
                        "minuto": 54,
                    },
                },
            }
        }

        self.banco.salvar_registro(registro)
        linha = self.banco.conexao.execute(
            "SELECT estado, metodo_coleta, metadados_json, oferta_json "
            "FROM observacoes_fontes_odds WHERE fonte='the_odds_api'"
        ).fetchone()
        metadados = json.loads(linha["metadados_json"])

        self.assertEqual("evento_nao_encontrado", linha["estado"])
        self.assertEqual(
            "amostragem_referencia_sombra", linha["metodo_coleta"]
        )
        self.assertIsNone(linha["oferta_json"])
        self.assertEqual(
            "recuperacao_coorte_resultado", metadados["tipo_amostra"]
        )
        self.assertEqual(
            "amostragem-referencia-sombra-auditoria-v5",
            metadados["versao"],
        )
        self.assertTrue(metadados["recuperacao_coorte_solicitada"])
        self.assertTrue(metadados["recuperacao_coorte_aplicada"])
        self.assertEqual(3, metadados["limite_efetivo_jogo_dia"])
        self.assertEqual(3, metadados["posicao_fila"])
        self.assertEqual(8, metadados["tarefas_ciclo"])
        self.assertEqual("Liga Teste", metadados["liga"])
        self.assertTrue(metadados["selecao_antes_resultado"])
        self.assertFalse(metadados["aplicacao_sinais"])

    def test_persiste_preselecao_sem_consumir_reserva_de_referencia(self):
        registro = self.registro()
        registro["qualidade"] = {
            "the_odds_api": {
                "ativa": True,
                "motivo": "sem_mercado_compativel",
                "amostragem_referencia_sombra": {
                    "ativa": True,
                    "elegivel_betsapi": True,
                    "motivo": "competicao_nao_coberta_pre_reserva",
                    "motivo_cobertura": "competicao_nao_coberta",
                    "reserva_consumida": False,
                    "preselecao_cobertura": {
                        "versao": "preselecao-cobertura-the-odds-api-v1",
                        "executada": True,
                        "coberta": False,
                        "esportes_candidatos": [],
                    },
                    "auditoria_amostragem": {
                        "versao": "amostragem-referencia-sombra-auditoria-v4",
                        "ciclo_em": "2026-09-11T14:00:00",
                        "posicao_fila": 2,
                        "tarefas_ciclo": 7,
                        "fila_operacional": "exploracao",
                        "liga": "Liga sem cobertura",
                        "minuto": 31,
                    },
                },
            }
        }

        self.banco.salvar_registro(registro)
        linha = self.banco.conexao.execute(
            "SELECT estado, metodo_coleta, metadados_json, oferta_json "
            "FROM observacoes_fontes_odds WHERE fonte='the_odds_api'"
        ).fetchone()
        metadados = json.loads(linha["metadados_json"])

        self.assertEqual(
            "competicao_nao_coberta_pre_reserva", linha["estado"]
        )
        self.assertEqual(
            "amostragem_referencia_preselecao", linha["metodo_coleta"]
        )
        self.assertIsNone(linha["oferta_json"])
        self.assertFalse(metadados["competicao_coberta"])
        self.assertFalse(metadados["reserva_consumida"])
        self.assertTrue(metadados["preselecao_executada"])
        self.assertEqual(
            "preselecao-cobertura-the-odds-api-v1",
            metadados["preselecao_cobertura_versao"],
        )
        self.assertFalse(metadados["aplicacao_sinais"])

    def test_persiste_preselecao_de_evento_sem_consumir_reserva(self):
        registro = self.registro()
        registro["qualidade"] = {
            "the_odds_api": {
                "ativa": True,
                "motivo": "sem_mercado_compativel",
                "amostragem_referencia_sombra": {
                    "ativa": True,
                    "elegivel_betsapi": True,
                    "motivo": "evento_nao_encontrado_pre_reserva",
                    "reserva_consumida": False,
                    "preselecao_cobertura": {
                        "versao": "preselecao-cobertura-the-odds-api-v1",
                        "executada": True,
                        "coberta": True,
                        "esportes_candidatos": [
                            "soccer_brazil_campeonato"
                        ],
                    },
                    "preselecao_evento": {
                        "versao": "preselecao-evento-the-odds-api-v1",
                        "executada": True,
                        "pareado": False,
                        "consulta_eventos": True,
                        "consulta_odds": False,
                    },
                    "auditoria_amostragem": {
                        "versao": "amostragem-referencia-sombra-auditoria-v4",
                        "ciclo_em": "2026-09-11T14:10:00",
                        "posicao_fila": 4,
                        "tarefas_ciclo": 9,
                    },
                },
            }
        }

        self.banco.salvar_registro(registro)
        linha = self.banco.conexao.execute(
            "SELECT estado, metodo_coleta, metadados_json, oferta_json "
            "FROM observacoes_fontes_odds WHERE fonte='the_odds_api'"
        ).fetchone()
        metadados = json.loads(linha["metadados_json"])

        self.assertEqual(
            "evento_nao_encontrado_pre_reserva", linha["estado"]
        )
        self.assertEqual(
            "amostragem_referencia_preselecao", linha["metodo_coleta"]
        )
        self.assertIsNone(linha["oferta_json"])
        self.assertTrue(metadados["competicao_coberta"])
        self.assertTrue(metadados["preselecao_evento_executada"])
        self.assertFalse(metadados["evento_pareado_pre_reserva"])
        self.assertTrue(metadados["consulta_eventos_sem_custo"])
        self.assertFalse(metadados["reserva_consumida"])
        self.assertEqual(
            "amostragem-referencia-sombra-auditoria-v4",
            metadados["versao"],
        )

    def test_audita_referencia_sombra_sincronizada_da_fila_rapida(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": 1.55,
            "pontuacao_tecnica": 80,
            "regra_versao": "teste-referencia-rapida-v1",
            "status": "rejeitado",
            "features": {},
        }])[0]
        odds_referencia = {"pre_jogo": [], "ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "fonte": "the_odds_api",
            "ofertas": [{
                "linha": 2.5,
                "over": 1.62,
                "under": 2.28,
                "fonte": "the_odds_api",
                "bookmaker": "pinnacle",
            }],
        }]}
        diagnostico = {
            "ativa": True,
            "pareado": True,
            "motivo": "oferta_anexada",
            "evento_externo_id": "odds-123",
            "mandante_observado": "Time A",
            "visitante_observado": "Time B",
            "consultados": ["alternate_totals"],
            "anexados": ["gol_ft"],
            "reserva_consumida": True,
            "custo_estimado_creditos": 1,
            "reserva": {
                "autorizada": True,
                "tipo_amostra": "nova_partida",
                "uso_dia": 4,
                "uso_jogo_dia": 1,
            },
            "auditoria_amostragem": {
                "versao": "amostragem-referencia-sombra-auditoria-v4",
            },
        }

        resultado = (
            self.banco.registrar_referencia_sombra_acompanhamento_odd(
                sinal_id,
                odds_referencia,
                diagnostico,
                {"placar": "1-0", "minuto": 55, "status": "55 '"},
                consultado_em="2026-09-11T15:20:00",
                origem_sinal_id=sinal_id,
            )
        )
        linha = self.banco.conexao.execute(
            "SELECT * FROM observacoes_fontes_odds "
            "WHERE fonte='the_odds_api' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        metadados = json.loads(linha["metadados_json"])

        self.assertTrue(resultado["persistido"])
        self.assertEqual("oferta_disponivel", linha["estado"])
        self.assertEqual(
            "amostragem_referencia_sombra", linha["metodo_coleta"]
        )
        self.assertEqual("monitor_odd_rapido", metadados["origem_coleta"])
        self.assertEqual(sinal_id, metadados["sinal_origem_id"])
        self.assertEqual(sinal_id, metadados["sinal_tecnico_id"])
        self.assertEqual("gol_ft", metadados["mercado_alvo"])
        self.assertEqual(2.5, metadados["linha_alvo"])
        self.assertEqual("bet365", metadados["bookmaker_alvo"])
        self.assertFalse(metadados["aplicacao_sinais"])
        self.assertFalse(resultado["telegram"])

    def test_trajetoria_odd_rapida_deduplica_e_recupera_ultima_pre_gol(self):
        origem = self.registro()
        origem.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0",
            "status": "46 '",
        })
        snapshot_origem = self.banco.salvar_registro(origem)
        sinal_id = self.banco.salvar_candidatos(snapshot_origem, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.22,
            "pontuacao_tecnica": 90,
            "regra_versao": "teste-acompanhamento-v1",
            "status": "rejeitado",
            "features": {
                "fonte_odds": "packball",
                "acompanhamento_odd": {"elegivel_aviso": True},
            },
        }])[0]

        def registrar(
            odd, instante, placar="0-0", minuto=50, odd_oposta=2.50,
            evento_externo_id="evento-123",
        ):
            return self.banco.registrar_observacao_acompanhamento_odd(
                sinal_id,
                {
                    "odd": odd,
                    "odd_oposta": odd_oposta,
                    "linha": 0.5,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "idade_segundos": 0.0,
                    "coletado_em": instante,
                    "cache": False,
                    "origem_mercado": origem_mercado_teste(),
                    "identidade_evento": identidade_evento_teste(
                        placar,
                        evento_externo_id=evento_externo_id,
                    ),
                },
                {
                    "placar": placar,
                    "minuto": minuto,
                    "status": f"{minuto} '",
                },
                consultado_em=instante,
            )

        primeira = registrar(1.30, "2026-09-01T12:01:00")
        repetida = registrar(1.30, "2026-09-01T12:02:00")
        oposta_alterada = registrar(
            1.30, "2026-09-01T12:02:30", odd_oposta=2.40
        )
        alterada = registrar(1.39, "2026-09-01T12:03:00")
        evento_trocado = registrar(
            1.41,
            "2026-09-01T12:03:30",
            evento_externo_id="evento-999",
        )
        fora_de_ordem = registrar(1.50, "2026-09-01T12:02:45")
        self.assertTrue(primeira["nova_linha"])
        self.assertTrue(repetida["nova_linha"])
        self.assertFalse(repetida["mudanca_material"])
        self.assertTrue(oposta_alterada["nova_linha"])
        self.assertTrue(oposta_alterada["mudanca_material"])
        self.assertTrue(alterada["nova_linha"])
        self.assertFalse(evento_trocado["persistido"])
        self.assertEqual(
            evento_trocado["estado"], "identidade_evento_alterada"
        )
        self.assertEqual(
            evento_trocado["motivo"],
            "evento_externo_trocado_na_mesma_fonte",
        )
        self.assertEqual(
            "nova_observacao_fora_de_ordem", fora_de_ordem["estado"]
        )
        self.assertFalse(fora_de_ordem["ordem_temporal_valida"])
        self.assertFalse(fora_de_ordem["mudanca_material"])
        self.assertEqual(self.banco.conexao.execute(
            "SELECT COUNT(*) FROM observacoes_fontes_odds "
            "WHERE evidencia_referencia=?",
            (f"acompanhamento_odd:{sinal_id}",),
        ).fetchone()[0], 5)
        primeira_linha = self.banco.conexao.execute(
            """
            SELECT evento_externo_id, mandante_observado,
                   visitante_observado
            FROM observacoes_fontes_odds
            WHERE id=?
            """,
            (primeira["observacao_id"],),
        ).fetchone()
        self.assertEqual(primeira_linha["evento_externo_id"], "evento-123")
        self.assertEqual(primeira_linha["mandante_observado"], "Time A")
        self.assertEqual(primeira_linha["visitante_observado"], "Time B")
        invalida = self.banco.registrar_observacao_acompanhamento_odd(
            sinal_id,
            {
                "odd": 1.45, "odd_oposta": 2.40, "linha": 0.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(),
            },
            {"placar": "0-0", "minuto": 50, "status": "50 '"},
            consultado_em="2026-09-01T12:04:00",
        )
        self.assertEqual(invalida["estado"], "oferta_temporal_invalida")
        self.assertFalse(invalida["persistido"])
        self.assertEqual(self.banco.conexao.execute(
            "SELECT COUNT(*) FROM observacoes_fontes_odds "
            "WHERE evidencia_referencia=?",
            (f"acompanhamento_odd:{sinal_id}",),
        ).fetchone()[0], 5)
        odd_nao_finita = self.banco.registrar_observacao_acompanhamento_odd(
            sinal_id,
            {
                "odd": "nan", "odd_oposta": 2.40, "linha": 0.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T12:04:00",
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(),
            },
            {"placar": "0-0", "minuto": 50, "status": "50 '"},
            consultado_em="2026-09-01T12:04:00",
        )
        self.assertEqual(odd_nao_finita["estado"], "odd_invalida")
        self.assertFalse(odd_nao_finita["persistido"])
        sem_oposta = self.banco.registrar_observacao_acompanhamento_odd(
            sinal_id,
            {
                "odd": 1.45, "linha": 0.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T12:04:00",
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(),
            },
            {"placar": "0-0", "minuto": 50, "status": "50 '"},
            consultado_em="2026-09-01T12:04:00",
        )
        self.assertEqual(
            sem_oposta["estado"], "contrato_mercado_incompleto"
        )
        self.assertFalse(sem_oposta["persistido"])
        sem_identidade = self.banco.registrar_observacao_acompanhamento_odd(
            sinal_id,
            {
                "odd": 1.45, "odd_oposta": 2.40, "linha": 0.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T12:04:00",
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
            },
            {"placar": "0-0", "minuto": 50, "status": "50 '"},
            consultado_em="2026-09-01T12:04:00",
        )
        self.assertEqual(sem_identidade["estado"], "identidade_evento_invalida")
        self.assertEqual(sem_identidade["motivo"], "identidade_evento_ausente")
        self.assertFalse(sem_identidade["persistido"])

        primeira_observacao_id = primeira["observacao_id"]
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            self.banco.conexao.execute(
                """
                UPDATE observacoes_fontes_odds
                SET consultado_em='2030-01-01T00:00:00'
                WHERE id=?
                """,
                (primeira_observacao_id,),
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            self.banco.conexao.execute(
                "DELETE FROM observacoes_fontes_odds WHERE id=?",
                (primeira_observacao_id,),
            )

        snapshot_gol = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:04:00",
            "url": origem["url"],
            "mandante": origem["mandante"],
            "visitante": origem["visitante"],
            "placar": "1-0",
            "status": "55 '",
            "confirmacao_api": {
                "fixture_id": 123,
                "status": {"short": "2H"},
            },
            "contexto_api": {
                "acompanhamento_odd_api_rapido": {
                    "estado_decisivo": True,
                },
            },
            "qualidade": {
                "pontuacao": 100,
                "fontes": ["api_football"],
                "versao": "resultado-api-v1",
            },
        })
        registrar(1.80, "2026-09-01T12:05:00", placar="1-0", minuto=56)

        ultima = self.banco.ultima_odd_acompanhamento_odd(
            sinal_id, snapshot_gol
        )
        self.assertEqual(ultima["odd"], 1.39)
        self.assertEqual(ultima["fonte"], "betsapi")
        self.assertEqual(ultima["consultado_em"], "2026-09-01T12:03:00")
        self.assertEqual(ultima["metodo_coleta"], "api_rapida_sem_packball")
        self.assertTrue(
            self.banco.estado_acompanhamento_odd_api_ja_registrado(
                sinal_id, "1-0", "2H"
            )
        )
        self.assertFalse(
            self.banco.estado_acompanhamento_odd_api_ja_registrado(
                sinal_id, "2-0", "2H"
            )
        )

    def test_proximo_gol_registra_trio_e_detecta_mudanca_na_outra_selecao(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0", "status": "25 '",
        })
        snapshot = self.banco.salvar_registro(registro)
        sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "proximo_gol", "linha": "casa", "odd": 1.30,
            "pontuacao_tecnica": 90,
            "regra_versao": "teste-proximo-contrato-v1",
            "status": "rejeitado",
        }])[0]

        def registrar(instante, visitante):
            return self.banco.registrar_observacao_acompanhamento_odd(
                sinal_id,
                {
                    "odd": 1.70, "linha": "casa",
                    "selecao_mercado": "casa",
                    "odds_mercado_sincronizadas": {
                        "casa": 1.70,
                        "visitante": visitante,
                        "sem_gol": 6.00,
                    },
                    "mercado_odds_sincronizado": True,
                    "fonte": "betsapi", "bookmaker": "bet365",
                    "idade_segundos": 0.0,
                    "coletado_em": instante, "cache": False,
                    "origem_mercado": origem_mercado_teste(
                        3,
                        lados=("casa", "visitante", "sem_gol"),
                    ),
                    "identidade_evento": identidade_evento_teste(),
                },
                {"placar": "0-0", "minuto": 25, "status": "25 '"},
                consultado_em=instante,
            )

        primeira = registrar("2026-09-01T12:01:00", 4.20)
        repetida = registrar("2026-09-01T12:01:10", 4.20)
        outra_selecao_mudou = registrar("2026-09-01T12:01:20", 4.00)

        self.assertTrue(primeira["mudanca_material"])
        self.assertFalse(repetida["mudanca_material"])
        self.assertTrue(outra_selecao_mudou["mudanca_material"])
        payload = json.loads(self.banco.conexao.execute(
            "SELECT oferta_json FROM observacoes_fontes_odds WHERE id=?",
            (outra_selecao_mudou["observacao_id"],),
        ).fetchone()[0])
        self.assertEqual(payload["schema"], "oferta-monitorada-odd-v4")
        self.assertEqual(
            payload["odds_mercado_sincronizadas"]["visitante"], 4.00
        )

    def test_curva_impossivel_vira_evidencia_append_only_e_nao_oferta(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0", "status": "20 '",
        })
        snapshot = self.banco.salvar_registro(registro)
        sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft", "linha": 1.5, "odd": 1.30,
            "regra_versao": "teste-anomalia-curva-v1",
            "status": "rejeitado",
        }])[0]
        instante = "2026-09-01T12:01:00"
        selecionada = {
            "odd": 1.80, "odd_oposta": 2.00, "linha": 1.5,
            "fonte": "betsapi", "bookmaker": "bet365",
            "idade_segundos": 0.0, "coletado_em": instante,
            "cache": False,
            "origem_mercado": origem_mercado_teste(1.5),
            "identidade_evento": identidade_evento_teste(),
        }
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "tipo_mercado": "total", "formato": "duas_opcoes",
            "ofertas": [
                {
                    "linha": 0.5, "over": 2.00, "under": 1.70,
                    "origem_mercado": origem_mercado_teste(0.5),
                },
                {
                    "linha": 1.5, "over": 1.80, "under": 2.00,
                    "origem_mercado": origem_mercado_teste(1.5),
                },
            ],
            "ofertas_ht": [],
        }]}

        resultado = self.banco.registrar_observacao_acompanhamento_odd(
            sinal_id,
            selecionada,
            {"placar": "0-0", "minuto": 20, "status": "20 '"},
            consultado_em=instante,
            odds=odds,
        )

        self.assertTrue(resultado["persistido"])
        self.assertFalse(resultado["autorizada"])
        self.assertEqual("anomalia_curva_odd", resultado["estado"])
        self.assertEqual("curva_linhas_odd_incoerente", resultado["motivo"])
        linha = self.banco.conexao.execute(
            """
            SELECT estado, motivo, oferta_json, evidencia_sha256
            FROM observacoes_fontes_odds WHERE id=?
            """,
            (resultado["observacao_id"],),
        ).fetchone()
        payload = json.loads(linha["oferta_json"])
        self.assertEqual("anomalia_curva_odd", linha["estado"])
        self.assertEqual("anomalia-curva-odd-v1", payload["schema"])
        self.assertEqual(
            hashlib.sha256(linha["oferta_json"].encode("utf-8")).hexdigest(),
            linha["evidencia_sha256"],
        )
        self.assertEqual(2, len(
            payload["coerencia_curva_odds"]["ofertas_curva"]
        ))
        self.assertEqual(0, self.banco.conexao.execute(
            """
            SELECT COUNT(*) FROM observacoes_fontes_odds
            WHERE evidencia_referencia=? AND estado='oferta_monitorada'
            """,
            (f"acompanhamento_odd:{sinal_id}",),
        ).fetchone()[0])

    def test_trigger_bloqueia_troca_de_evento_da_mesma_fonte(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0", "status": "50 '",
        })
        snapshot = self.banco.salvar_registro(registro)
        sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.30,
            "regra_versao": "teste-vinculo-evento-v1",
            "status": "rejeitado",
        }])[0]
        primeira = self.banco.registrar_observacao_acompanhamento_odd(
            sinal_id,
            {
                "odd": 1.40, "odd_oposta": 2.80, "linha": 0.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T12:01:00",
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(),
            },
            {"placar": "0-0", "minuto": 50, "status": "50 '"},
            consultado_em="2026-09-01T12:01:00",
        )
        linha = self.banco.conexao.execute(
            """
            SELECT partida_id, mercado, evidencia_referencia, oferta_json
            FROM observacoes_fontes_odds WHERE id=?
            """,
            (primeira["observacao_id"],),
        ).fetchone()
        payload = json.loads(linha["oferta_json"])
        payload["identidade_evento"]["evento_externo_id"] = "evento-999"
        oferta_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        evidencia = hashlib.sha256(
            oferta_json.encode("utf-8")
        ).hexdigest()

        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "identidade externa",
        ):
            self.banco.conexao.execute(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado,
                    evento_externo_id, mercado, oferta_json,
                    metodo_coleta, evidencia_sha256, evidencia_referencia
                ) VALUES (?, 'betsapi', '2026-09-01T12:02:00',
                          'oferta_monitorada', 'evento-999', ?, ?,
                          'api_rapida_sem_packball', ?, ?)
                """,
                (
                    linha["partida_id"], linha["mercado"], oferta_json,
                    evidencia, linha["evidencia_referencia"],
                ),
            )
        self.banco.conexao.rollback()

    def test_entrada_oficial_de_outra_linha_nao_fecha_acompanhamento(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-2",
            "status": "46 '",
        })
        snapshot_origem = self.banco.salvar_registro(registro)
        origem = self.banco.salvar_candidatos(snapshot_origem, [{
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": 1.22,
            "pontuacao_tecnica": 90,
            "regra_versao": "teste-espera-linha-v1",
            "status": "rejeitado",
            "features": {"acompanhamento_odd": {
                "elegivel_aviso": True,
                "conversao_confirmada": True,
                "tendencia_packball_confirmada": True,
                "odd_alvo": 1.40,
                "odd_maxima_operacional": 2.50,
            }},
        }])[0]
        self.banco.registrar_entrega_alerta(
            origem, "-100123:aguardar_odd", "entregue"
        )

        def oficial(linha, instante, versao, *, vinculado):
            novo = {**registro, "coletado_em": instante}
            snapshot = self.banco.salvar_registro(novo)
            features = {}
            if vinculado:
                features["acompanhamento_odd_rapido"] = {
                    "versao": "acompanhamento-odd-api-rapido-v1",
                    "origem_sinal_id": origem,
                    "leitura_tecnica_sinal_id": origem,
                }
            sinal = self.banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft",
                "linha": linha,
                "odd": 1.50,
                "pontuacao_tecnica": 90,
                "probabilidade_calibrada": 0.80,
                "regra_versao": versao,
                "status": "aprovado",
                "features": features,
            }])[0]
            self.banco.registrar_entrega_alerta(
                sinal, "-100123", "entregue", provedor="telegram",
                provedor_mensagem_id=str(sinal),
            )
            return sinal

        diferente = oficial(
            3.5, "2026-09-01T12:01:00", "teste-oficial-35-v1",
            vinculado=True,
        )
        pendentes = self.banco.acompanhamentos_odd_para_rechecagem_api()
        self.assertEqual([item["origem_sinal_id"] for item in pendentes], [origem])
        self.assertIsNone(
            self.banco.entrada_oficial_apos_acompanhamento(
                origem, "-100123"
            )
        )

        comum = oficial(
            2.5, "2026-09-01T12:02:00", "teste-oficial-comum-25-v1",
            vinculado=False,
        )
        self.assertEqual(
            [item["origem_sinal_id"] for item in
             self.banco.acompanhamentos_odd_para_rechecagem_api()],
            [origem],
        )
        self.assertIsNone(
            self.banco.entrada_oficial_apos_acompanhamento(
                origem, "-100123"
            )
        )

        exato = oficial(
            2.5, "2026-09-01T12:03:00", "teste-oficial-25-v1",
            vinculado=True,
        )
        self.assertEqual(
            self.banco.acompanhamentos_odd_para_rechecagem_api(), []
        )
        convertido = self.banco.entrada_oficial_apos_acompanhamento(
            origem, "-100123"
        )
        self.assertEqual(convertido["sinal_id"], exato)
        self.assertNotEqual(convertido["sinal_id"], diferente)
        self.assertNotEqual(convertido["sinal_id"], comum)

    def test_proximo_gol_casa_nao_confunde_com_visitante(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-01T12:00:00",
            "placar": "0-0",
            "status": "60 '",
        })
        snapshot = self.banco.salvar_registro(registro)
        origem = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 1.30,
            "pontuacao_tecnica": 90,
            "regra_versao": "teste-proximo-espera-v1",
            "status": "rejeitado",
            "features": {"acompanhamento_odd": {
                "elegivel_aviso": True,
                "conversao_confirmada": True,
                "tendencia_packball_confirmada": True,
                "odd_alvo": 1.40,
                "odd_maxima_operacional": 2.50,
            }},
        }])[0]
        self.banco.registrar_entrega_alerta(
            origem, "-100123:aguardar_odd", "entregue"
        )

        def oficial(lado, instante):
            novo = {**registro, "coletado_em": instante}
            novo_snapshot = self.banco.salvar_registro(novo)
            sinal = self.banco.salvar_candidatos(novo_snapshot, [{
                "mercado": "proximo_gol",
                "linha": lado,
                "odd": 1.50,
                "pontuacao_tecnica": 90,
                "probabilidade_calibrada": 0.80,
                "regra_versao": f"teste-proximo-{lado}-v1",
                "status": "aprovado",
                "features": {"acompanhamento_odd_rapido": {
                    "versao": "acompanhamento-odd-api-rapido-v1",
                    "origem_sinal_id": origem,
                    "leitura_tecnica_sinal_id": origem,
                }},
            }])[0]
            self.banco.registrar_entrega_alerta(
                sinal, "-100123", "entregue", provedor="telegram",
                provedor_mensagem_id=str(sinal),
            )
            return sinal

        oficial("visitante", "2026-09-01T12:01:00")
        self.assertEqual(
            len(self.banco.acompanhamentos_odd_para_rechecagem_api()), 1
        )
        self.assertIsNone(
            self.banco.entrada_oficial_apos_acompanhamento(
                origem, "-100123"
            )
        )
        casa = oficial("casa", "2026-09-01T12:02:00")
        convertido = self.banco.entrada_oficial_apos_acompanhamento(
            origem, "-100123"
        )
        self.assertEqual(convertido["sinal_id"], casa)
        self.assertEqual(
            self.banco.acompanhamentos_odd_para_rechecagem_api(), []
        )

    def test_fila_silenciosa_separa_metodo_e_linha_e_renova_leitura_certa(self):
        registro = self.registro()
        snapshot = self.banco.salvar_registro(registro)

        def salvar(metodo, linha=0.5, registrar=False):
            features = {"acompanhamento_odd": {"elegivel_aviso": True}}
            if metodo:
                features["acompanhamento_metodo_gols"] = {"metodo": metodo}
            sinal = self.banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": linha, "odd": 1.20,
                "regra_versao": "teste", "status": "rejeitado", "features": features,
            }])[0]
            existe = self.banco.acompanhamento_odd_ja_entregue_na_partida(sinal, "chat:aguardar_odd")
            if registrar:
                self.banco.registrar_entrega_alerta(sinal, "chat:aguardar_odd", "monitoramento_silencioso")
            return sinal, existe

        antigo, _ = salvar(None, registrar=True)
        metodo_a, existe = salvar("a", registrar=True)
        self.assertFalse(existe)
        metodo_b, existe = salvar("b", registrar=True)
        self.assertFalse(existe)
        nova_linha, existe = salvar("a", linha=1.5, registrar=True)
        self.assertFalse(existe)
        atualizado, existe = salvar("a")
        self.assertTrue(existe)
        fila = {x["origem_sinal_id"]: x["sinal_id"] for x in self.banco.acompanhamentos_odd_para_rechecagem_api()}
        self.assertEqual(fila, {antigo: antigo, metodo_a: atualizado, metodo_b: metodo_b, nova_linha: nova_linha})

    def test_espera_odd_nao_reutiliza_aprovacao_anterior_a_reprovacao(self):
        registro = self.registro()
        registro["coletado_em"] = (datetime.now() - timedelta(seconds=20)).isoformat()
        snapshot = self.banco.salvar_registro(registro)
        def leitura(aprovada):
            return self.banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.25,
                "regra_versao": "teste-espera", "status": "rejeitado",
                "features": {
                    "acompanhamento_metodo_gols": {"metodo": "teste-metodo"},
                    "acompanhamento_odd": {"elegivel_aviso": aprovada},
                },
            }])[0]
        origem = leitura(True)
        self.banco.registrar_entrega_alerta(origem, "chat:aguardar_odd", "monitoramento_silencioso")
        self.assertEqual(len(self.banco.acompanhamentos_odd_para_rechecagem_api()), 1)
        leitura(False)
        self.assertEqual(self.banco.acompanhamentos_odd_para_rechecagem_api(), [])
        nova = leitura(True)
        fila = self.banco.acompanhamentos_odd_para_rechecagem_api()
        self.assertEqual([(x["origem_sinal_id"], x["sinal_id"]) for x in fila], [(origem, nova)])

    def test_analise_tecnica_substitui_espera_mas_consulta_de_preco_nao(self):
        registro = self.registro()
        instante = datetime.now() - timedelta(seconds=60)
        registro.update({
            "coletado_em": instante.isoformat(),
            "_analise_tecnica_acompanhamento_odd": True,
        })
        snapshot = self.banco.salvar_registro(registro)
        candidato = {
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.25,
            "regra_versao": "teste-espera", "status": "rejeitado",
            "features": {
                "acompanhamento_metodo_gols": {"metodo": "teste-metodo"},
                "acompanhamento_odd": {"elegivel_aviso": True},
            },
        }
        origem = self.banco.salvar_candidatos(snapshot, [candidato])[0]
        self.banco.registrar_entrega_alerta(origem, "chat:aguardar_odd", "monitoramento_silencioso")
        qualidade_copiada = {"analise_tecnica_acompanhamento_odd": True}
        consulta = {**registro,
            "coletado_em": (instante + timedelta(seconds=20)).isoformat(),
            "qualidade": qualidade_copiada, "_nao_atualizar_ultima_coleta": True,
        }
        quote_snapshot = self.banco.salvar_registro(consulta)
        qualidade_salva = json.loads(self.banco.conexao.execute(
            "SELECT qualidade_json FROM snapshots WHERE id=?", (quote_snapshot,),
        ).fetchone()[0])
        self.assertNotIn("analise_tecnica_acompanhamento_odd", qualidade_salva)
        self.assertTrue(qualidade_copiada["analise_tecnica_acompanhamento_odd"])
        self.assertTrue(self.banco.acompanhamento_odd_leitura_vigente(origem))

        convertido = self.banco.salvar_candidatos(quote_snapshot, [{
            **candidato, "odd": 1.45, "status": "aprovado", "features": {
                "acompanhamento_odd_rapido": {"leitura_tecnica_sinal_id": origem},
            },
        }])[0]
        token = self.banco.reservar_entrega_alerta(convertido, "chat:teste")
        self.assertTrue(token)
        self.assertTrue(self.banco.reserva_entrega_valida(convertido, "chat:teste", token))

        # A leitura começou antes da consulta de preço, mas terminou depois.
        # Só olhar o timestamp do último snapshot perderia essa reprovação.
        self.banco.salvar_registro({**registro,
            "coletado_em": (instante + timedelta(seconds=10)).isoformat(),
        })
        self.assertFalse(self.banco.acompanhamento_odd_leitura_vigente(origem))
        self.assertEqual(self.banco.acompanhamentos_odd_para_rechecagem_api(), [])
        self.assertFalse(self.banco.reserva_entrega_valida(convertido, "chat:teste", token))
        outro = self.banco.salvar_candidatos(quote_snapshot, [{
            **candidato, "status": "simulacao", "features": {
                "acompanhamento_odd_rapido": {"leitura_tecnica_sinal_id": origem},
            },
        }])[0]
        self.assertIsNone(self.banco.reservar_entrega_alerta(outro, "chat:teste", permitir_simulacao=True))

        renovado = self.banco.salvar_registro({**registro,
            "coletado_em": (instante + timedelta(seconds=30)).isoformat(),
        })
        nova_leitura = self.banco.salvar_candidatos(renovado, [candidato])[0]
        fila = self.banco.acompanhamentos_odd_para_rechecagem_api()
        self.assertEqual([(x["origem_sinal_id"], x["sinal_id"]) for x in fila], [(origem, nova_leitura)])
        self.assertTrue(self.banco.acompanhamento_odd_leitura_vigente(nova_leitura))

    def test_conversao_odd_preserva_unica_decisao_da_exploracao(self):
        snapshot = self.banco.salvar_registro(self.registro())
        base = {
            "mercado": "gol_ft", "linha": 2.5, "odd": 1.22,
            "pontuacao_tecnica": 90, "regra_versao": "teste-v1",
            "status": "rejeitado",
            "features": {
                "exploracao_sombra": {"versao": "teste-coorte-unica-v1"},
                "acompanhamento_odd": {"elegivel_aviso": True},
            },
        }
        origem = self.banco.salvar_candidatos(snapshot, [base])[0]
        nova = {**base, "odd": 1.44, "status": "simulacao"}
        with self.assertRaisesRegex(sqlite3.IntegrityError, "repetida"):
            self.banco.salvar_candidatos(snapshot, [nova])

        nova["features"] = {
            **base["features"],
            "acompanhamento_odd_rapido": {"leitura_tecnica_sinal_id": origem},
        }
        convertido = self.banco.salvar_candidatos(snapshot, [nova])[0]
        self.assertNotEqual(origem, convertido)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "repetida"):
            self.banco.salvar_candidatos(snapshot, [nova])
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            self.banco.conexao.execute("UPDATE sinais SET odd=1.44 WHERE id=?", (origem,))
        self.assertEqual(self.banco.conexao.execute(
            "SELECT odd FROM sinais WHERE id=?", (origem,),
        ).fetchone()["odd"], 1.22)

    def test_migracao_independencia_preserva_nome_backup_e_historico(self):
        snapshot = self.banco.salvar_registro(self.registro())
        self.banco.conexao.execute(
            "DROP TRIGGER trg_sinais_exploracao_sombra_independente"
        )
        self.banco.conexao.execute("""
            CREATE TRIGGER trg_sinais_exploracao_sombra_independente
            BEFORE INSERT ON sinais
            WHEN json_extract(NEW.features_json, '$.exploracao_sombra.versao') IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM sinais antigo
                WHERE antigo.partida_id=NEW.partida_id AND antigo.mercado=NEW.mercado
                  AND json_extract(antigo.features_json, '$.exploracao_sombra.versao')
                      =json_extract(NEW.features_json, '$.exploracao_sombra.versao')
              )
            BEGIN SELECT RAISE(ABORT, 'exploracao sombra repetida para partida e mercado'); END
        """)
        self.banco.conexao.commit()
        self.assertTrue(auditar_compatibilidade(self.banco.conexao)["compativel"])
        self.banco.fechar()
        self.banco = BancoMonitor(self.caminho)
        definicao = self.banco.conexao.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='trg_sinais_exploracao_sombra_independente'"
        ).fetchone()["sql"]
        self.assertIn("leitura_tecnica_sinal_id", definicao)
        self.assertEqual(self.banco.conexao.execute(
            "SELECT id FROM snapshots WHERE id=?", (snapshot,),
        ).fetchone()["id"], snapshot)
        self.assertTrue(auditar_compatibilidade(self.banco.conexao)["compativel"])

    def test_observacao_ja_resolvida_nao_libera_nova_exploracao(self):
        snapshot = self.banco.salvar_registro(self.registro())
        base = {
            "mercado": "gol_ht", "linha": 0.5, "odd": 1.22,
            "pontuacao_tecnica": 90, "regra_versao": "teste-v1",
            "status": "rejeitado",
            "features": {
                "exploracao_sombra": {"versao": "teste-ja-resolvida-v1"},
                "acompanhamento_odd": {"elegivel_aviso": True},
            },
        }
        origem = self.banco.salvar_candidatos(snapshot, [base])[0]
        self.banco.conexao.execute(
            "INSERT INTO resultados_sinais (sinal_id, encerrado_em, resultado, retorno_unidades) VALUES (?, ?, 'green', 0.22)",
            (origem, datetime.now().isoformat()),
        )
        self.banco.conexao.commit()
        nova = {**base, "odd": 1.44, "status": "simulacao", "features": {
            **base["features"],
            "acompanhamento_odd_rapido": {"leitura_tecnica_sinal_id": origem},
        }}
        with self.assertRaisesRegex(sqlite3.IntegrityError, "repetida"):
            self.banco.salvar_candidatos(snapshot, [nova])

    def test_fila_odd_rapida_prioriza_recente_menos_consultado(self):
        def criar_aviso(indice, coletado_em):
            registro = self.registro()
            registro.update({
                "coletado_em": coletado_em,
                "url": f"https://packball.com/match/fila-{indice}",
                "mandante": f"Casa {indice}",
                "visitante": f"Fora {indice}",
                "placar": "0-0",
                "status": "50 '",
            })
            snapshot = self.banco.salvar_registro(registro)
            sinal = self.banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.25,
                "pontuacao_tecnica": 85,
                "regra_versao": f"teste-fila-odd-{indice}",
                "status": "rejeitado",
                "features": {"acompanhamento_odd": {
                    "elegivel_aviso": True,
                    "conversao_confirmada": True,
                    "tendencia_packball_confirmada": True,
                    "odd_alvo": 1.40,
                    "odd_maxima_operacional": 2.50,
                }},
            }])[0]
            self.banco.registrar_entrega_alerta(
                sinal, f"-100{indice}:aguardar_odd", "entregue"
            )
            return sinal

        recente_mais_consultado = criar_aviso(
            1, "2026-09-01T12:00:00"
        )
        recente_menos_consultado = criar_aviso(
            2, "2026-09-01T12:01:00"
        )
        criar_aviso(3, "2026-09-01T11:00:00")
        self.banco.registrar_consulta_acompanhamento_odd_api(
            recente_mais_consultado,
            consultado_em="2026-09-01T12:10:00",
        )
        self.banco.registrar_consulta_acompanhamento_odd_api(
            recente_menos_consultado,
            consultado_em="2026-09-01T12:05:00",
        )

        fila = self.banco.acompanhamentos_odd_para_rechecagem_api(
            2, snapshot_desde="2026-09-01T11:59:00"
        )

        self.assertEqual(
            [item["origem_sinal_id"] for item in fila],
            [recente_menos_consultado, recente_mais_consultado],
        )
        self.assertEqual(fila[0]["fila_total"], 3)
        self.assertEqual(fila[0]["fila_tecnica_recente_total"], 2)
        self.assertEqual(fila[0]["fila_tecnica_dormente_total"], 1)
        self.assertEqual(fila[0]["fila_recente_nunca_consultada"], 0)

        primeira = self.banco.registrar_consulta_acompanhamento_odd_api(
            recente_menos_consultado,
            consultado_em="2026-09-01T12:11:00",
        )
        self.assertEqual(primeira["estado"], "consulta_atualizada")
        quantidade = self.banco.conexao.execute(
            """
            SELECT COUNT(*) AS total FROM observacoes_fontes_odds
            WHERE evidencia_referencia=?
              AND estado='consulta_monitoramento'
            """,
            (f"acompanhamento_odd:{recente_menos_consultado}",),
        ).fetchone()["total"]
        self.assertEqual(quantidade, 1)

    def test_retencao_preserva_exploracao_sombra_e_snapshot(self):
        snapshot = self.banco.salvar_registro(self.registro())
        antigo = (datetime.now() - timedelta(days=400)).isoformat()
        sinal_id = self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "gol_ft",
                "odd": 1.8,
                "pontuacao_tecnica": 70,
                "regra_versao": "sinais-v6",
                "status": "simulacao",
                "features": {
                    "exploracao_sombra": {"versao": "validacao-v2"}
                },
            }],
            criado_em=antigo,
        )[0]

        self.banco.limpar_dados_antigos(dias=180)

        self.assertIsNotNone(self.banco.conexao.execute(
            "SELECT 1 FROM sinais WHERE id=?", (sinal_id,)
        ).fetchone())
        self.assertIsNotNone(self.banco.conexao.execute(
            "SELECT 1 FROM snapshots WHERE id=?", (snapshot,)
        ).fetchone())

    def test_esquema_preserva_historico_de_calibracoes(self):
        colunas = {
            item[1] for item in self.banco.conexao.execute(
                "PRAGMA table_info(historico_calibracoes)"
            ).fetchall()
        }
        self.assertTrue({
            "modelo_hash", "modelo_json", "amostra_fingerprint", "ativa"
        }.issubset(colunas))
        colunas_sinais = {
            item[1] for item in self.banco.conexao.execute(
                "PRAGMA table_info(sinais)"
            ).fetchall()
        }
        self.assertIn("regra_fingerprint", colunas_sinais)
        gatilhos = {
            item[0] for item in self.banco.conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        self.assertTrue(GATILHOS_OBRIGATORIOS.issubset(gatilhos))
        indices = {
            item[0] for item in self.banco.conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        self.assertTrue(INDICES_OBRIGATORIOS.issubset(indices))

    def test_esquema_protege_estimativa_historica_congelada(self):
        conexao = self.banco.conexao
        custodia = auditar_gatilhos_estimativa_historica(conexao)
        self.assertTrue(custodia["saudavel"])
        self.assertEqual(
            custodia["presentes"], len(GATILHOS_ESTIMATIVA_HISTORICA)
        )
        chave = PREFIXO_ESTIMATIVA_HISTORICA + "123"
        conexao.execute(
            "INSERT INTO metadados(chave,valor) VALUES(?,?)",
            (chave, '{"congelada":true}'),
        )
        for sql, parametros in (
            ("UPDATE metadados SET valor=? WHERE chave=?", ("{}", chave)),
            ("DELETE FROM metadados WHERE chave=?", (chave,)),
            ("INSERT OR REPLACE INTO metadados(chave,valor) VALUES(?,?)",
             (chave, "{}")),
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                conexao.execute(sql, parametros)
        self.assertEqual(
            conexao.execute(
                "SELECT valor FROM metadados WHERE chave=?", (chave,)
            ).fetchone()[0],
            '{"congelada":true}',
        )

    def test_historico_drift_e_idempotente_por_resultado_e_mercado(self):
        validacao = {
            "regra_versao": "sinais-v4",
            "drift_simulacoes": {
                "regra_versao": "sinais-v4",
                "mercados": {
                    "gol_ft": {
                        "estado": "degradado",
                        "avaliavel": True,
                        "amostra_recente": 30,
                        "amostra_base": 60,
                        "roi_recente": -0.2,
                        "roi_base": 0.1,
                        "delta_roi": -0.3,
                        "intervalo_delta_roi_95": [-0.5, -0.1],
                        "taxa_acerto_recente": 0.4,
                        "taxa_acerto_base": 0.6,
                        "ultima_decisao_id": 100,
                        "ultimo_resultado_em": "2026-07-25T20:00:00",
                    },
                    "proximo_gol": {
                        "estado": "formando_base",
                        "avaliavel": False,
                        "amostra_recente": 10,
                        "amostra_base": 0,
                        "ultima_decisao_id": 90,
                        "ultimo_resultado_em": "2026-07-25T19:00:00",
                    },
                },
            },
            "drift_simulacoes_confirmacoes": {
                "gol_ft": {"quantidade": 2, "ultima_decisao_id": 100}
            },
            "drift_simulacoes_mercados_confirmados": ["gol_ft"],
        }
        instante = datetime(2026, 7, 25, 20, 1)

        with self.banco.conexao:
            primeiro = registrar_historico_drift_simulacoes(
                self.banco.conexao, validacao, instante
            )
            repetido = registrar_historico_drift_simulacoes(
                self.banco.conexao, validacao, instante + timedelta(minutes=1)
            )

        self.assertEqual(primeiro["inseridos"], 2)
        self.assertEqual(repetido["inseridos"], 0)
        self.assertEqual(repetido["ignorados"], 2)
        resumo = resumir_historico_drift_simulacoes(
            self.banco.conexao, "sinais-v4"
        )
        self.assertEqual(resumo["total"], 2)
        self.assertEqual(resumo["mercados"], 2)
        linha = self.banco.conexao.execute(
            """
            SELECT confirmacoes, confirmado, intervalo_delta_min,
                   intervalo_delta_max
            FROM historico_drift_simulacoes
            WHERE mercado='gol_ft'
            """
        ).fetchone()
        self.assertEqual(linha["confirmacoes"], 2)
        self.assertEqual(linha["confirmado"], 1)
        self.assertEqual(linha["intervalo_delta_min"], -0.5)
        self.assertEqual(linha["intervalo_delta_max"], -0.1)
        auditoria = auditar_historico_drift_simulacoes(
            self.banco.conexao,
            validacao["drift_simulacoes"],
            "sinais-v4",
        )
        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["estado"], "integro")
        self.assertEqual(auditoria["chaves_atuais"], 2)

        validacao["drift_simulacoes"]["mercados"]["gol_ft"][
            "ultima_decisao_id"
        ] = 101
        atrasado = auditar_historico_drift_simulacoes(
            self.banco.conexao,
            validacao["drift_simulacoes"],
            "sinais-v4",
        )
        self.assertFalse(atrasado["saudavel"])
        self.assertEqual(
            atrasado["chaves_atuais_ausentes"], ["gol_ft:101"]
        )

    def test_historico_drift_persiste_versao_ativa_de_cada_mercado(self):
        validacao = {
            "drift_simulacoes": {
                "regra_versao": "versoes-ativas-por-mercado",
                "regra_versoes_por_mercado": {
                    "gol_ft": "sinais-v6",
                    "escanteios_ft_asiatico": "sinais-v7-ft-asiatico",
                },
                "mercados": {
                    "gol_ft": {
                        "regra_versao": "sinais-v6",
                        "ultima_decisao_id": 201,
                        "estado": "formando_base",
                    },
                    "escanteios_ft_asiatico": {
                        "regra_versao": "sinais-v7-ft-asiatico",
                        "ultima_decisao_id": 202,
                        "estado": "formando_base",
                    },
                },
            },
        }

        with self.banco.conexao:
            resultado = registrar_historico_drift_simulacoes(
                self.banco.conexao, validacao
            )

        versoes = {
            linha["mercado"]: linha["regra_versao"]
            for linha in self.banco.conexao.execute(
                """
                SELECT mercado, regra_versao
                FROM historico_drift_simulacoes
                """
            )
        }
        self.assertEqual(resultado["inseridos"], 2)
        self.assertEqual(versoes["gol_ft"], "sinais-v6")
        self.assertEqual(
            versoes["escanteios_ft_asiatico"],
            "sinais-v7-ft-asiatico",
        )
        resumo = resumir_historico_drift_simulacoes(
            self.banco.conexao,
            regras_por_mercado=validacao["drift_simulacoes"][
                "regra_versoes_por_mercado"
            ],
        )
        auditoria = auditar_historico_drift_simulacoes(
            self.banco.conexao,
            validacao["drift_simulacoes"],
        )
        self.assertEqual(resumo["total"], 2)
        self.assertTrue(auditoria["saudavel"])

    def test_historico_drift_preserva_evidencia_imutavel(self):
        validacao = {
            "regra_versao": "sinais-v4",
            "drift_simulacoes": {
                "mercados": {
                    "gol_ft": {
                        "estado": "estavel",
                        "avaliavel": True,
                        "amostra_recente": 30,
                        "amostra_base": 60,
                        "ultima_decisao_id": 100,
                    }
                }
            },
        }
        with self.banco.conexao:
            registrar_historico_drift_simulacoes(
                self.banco.conexao, validacao
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    """
                    UPDATE historico_drift_simulacoes
                    SET estado='degradado'
                    """
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "DELETE FROM historico_drift_simulacoes"
                )

    def test_marco_do_experimento_de_filtro_e_imutavel(self):
        marco = registrar_ou_obter_experimento_filtro(
            self.banco.conexao,
            "sinais-v4",
            80,
            80,
            datetime(2026, 7, 22, 18, 10, 8),
        )
        linha = self.banco.conexao.execute(
            """
            SELECT chave FROM metadados
            WHERE chave LIKE 'experimento_filtro_teste:%'
            """
        ).fetchone()

        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor='{}' WHERE chave=?",
                    (linha["chave"],),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "DELETE FROM metadados WHERE chave=?",
                    (linha["chave"],),
                )

        repetido = registrar_ou_obter_experimento_filtro(
            self.banco.conexao,
            "sinais-v4",
            80,
            80,
            datetime(2026, 7, 23, 12, 0, 0),
        )
        novo_limiar = registrar_ou_obter_experimento_filtro(
            self.banco.conexao,
            "sinais-v4",
            85,
            80,
            datetime(2026, 7, 23, 12, 0, 0),
        )
        self.assertEqual(repetido, marco)
        self.assertNotEqual(novo_limiar["iniciado_em"], marco["iniciado_em"])
        self.assertEqual(
            self.banco.conexao.execute(
                """
                SELECT COUNT(*) FROM metadados
                WHERE chave LIKE 'experimento_filtro_teste:%'
                """
            ).fetchone()[0],
            2,
        )

    def test_conclusao_do_experimento_de_filtro_e_imutavel(self):
        registrar_ou_obter_experimento_filtro(
            self.banco.conexao,
            "sinais-v4",
            80,
            80,
            datetime(2026, 7, 22, 18, 10, 8),
        )
        conclusao = registrar_ou_obter_conclusao_experimento_filtro(
            self.banco.conexao,
            "sinais-v4",
            80,
            80,
            "fp-atual",
            {
                "comparacao": {
                    "geral": {
                        "estado": "avaliavel",
                        "decisao": "nao_comprovado",
                        "amostra_enviadas": 30,
                        "amostra_filtradas": 30,
                    }
                }
            },
            datetime(2026, 7, 24, 10, 0, 0),
        )
        linha = self.banco.conexao.execute(
            """
            SELECT chave FROM metadados
            WHERE chave LIKE 'conclusao_experimento_filtro:%'
            """
        ).fetchone()

        self.assertEqual(conclusao["decisao"], "nao_comprovado")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor='{}' WHERE chave=?",
                    (linha["chave"],),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "DELETE FROM metadados WHERE chave=?",
                    (linha["chave"],),
                )

    def test_definicao_da_hipotese_sombra_e_imutavel(self):
        chave = "hipotese_sombra:teste"
        with self.banco.conexao:
            self.banco.conexao.execute(
                "INSERT INTO metadados (chave, valor) VALUES (?, '{}')",
                (chave,),
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor='[]' WHERE chave=?",
                    (chave,),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "DELETE FROM metadados WHERE chave=?",
                    (chave,),
                )

    def test_ancora_prospectiva_de_ligas_e_imutavel(self):
        registrar_ou_obter_validacao_prospectiva_ligas(
            self.banco.conexao,
            "gol_ft",
            "regra-v1",
            "fp-v1",
            ["liga_ruim"],
            "2026-08-25T10:00:00",
        )
        linha = self.banco.conexao.execute(
            """
            SELECT chave FROM metadados
            WHERE chave LIKE 'auditoria_ligas_prospectiva:%'
            """
        ).fetchone()

        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor='{}' WHERE chave=?",
                    (linha["chave"],),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "DELETE FROM metadados WHERE chave=?",
                    (linha["chave"],),
                )

    def test_ancora_prospectiva_de_contexto_e_imutavel(self):
        ancoras = registrar_ou_obter_ancoras_contexto(
            self.banco.conexao,
            {"gol_ft": "regra-contexto-v1"},
            registrado_em="2026-09-10T00:00:00",
        )
        repetida = registrar_ou_obter_ancoras_contexto(
            self.banco.conexao,
            {"gol_ft": "regra-contexto-v1"},
            registrado_em="2026-09-10T01:00:00",
        )
        linha = self.banco.conexao.execute(
            """
            SELECT chave FROM metadados
            WHERE chave LIKE 'avaliacao_contexto:causal_v6:%'
            """
        ).fetchone()

        self.assertEqual("2026-09-10T00:00:00", ancoras["gol_ft"])
        self.assertEqual(ancoras, repetida)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE metadados SET valor='alterado' WHERE chave=?",
                    (linha["chave"],),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "DELETE FROM metadados WHERE chave=?",
                    (linha["chave"],),
                )

    def test_definicao_e_previsao_probabilidade_individual_sao_imutaveis(self):
        for chave in (
            "avaliacao_probabilidade_individual:v2:definicao:gol_ft",
            "avaliacao_probabilidade_individual:v2:previsao:gol_ft:123",
        ):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "INSERT INTO metadados(chave,valor) VALUES (?, '{}')",
                    (chave,),
                )
            with self.assertRaisesRegex(
                sqlite3.IntegrityError, "probabilidade individual"
            ):
                with self.banco.conexao:
                    self.banco.conexao.execute(
                        "UPDATE metadados SET valor='[]' WHERE chave=?",
                        (chave,),
                    )
            with self.assertRaisesRegex(
                sqlite3.IntegrityError, "probabilidade individual"
            ):
                with self.banco.conexao:
                    self.banco.conexao.execute(
                        "DELETE FROM metadados WHERE chave=?", (chave,)
                    )

    def test_prova_telegram_e_imutavel_e_nao_pode_ser_reutilizada(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinais = self.banco.salvar_candidatos(snapshot, [
            {"mercado": "gol_ft", "regra_versao": "sinais-v1"},
            {"mercado": "gol_ht", "regra_versao": "sinais-v1"},
        ])
        prova = {
            "provedor": "telegram",
            "ok": True,
            "message_id": 123,
        }
        self.banco.registrar_entrega_alerta(
            sinais[0], "chat:teste", "entregue",
            provedor="telegram",
            provedor_destino_id="chat",
            provedor_mensagem_id="123",
            confirmacao=prova,
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
            self.banco.registrar_entrega_alerta(
                sinais[1], "chat:teste", "entregue",
                provedor="telegram",
                provedor_destino_id="chat",
                provedor_mensagem_id="123",
                confirmacao=prova,
            )
        entrega = self.banco.conexao.execute(
            "SELECT id FROM entregas_alertas WHERE sinal_id=?",
            (sinais[0],),
        ).fetchone()[0]
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    """
                    UPDATE entregas_alertas
                    SET provedor_mensagem_id='999' WHERE id=?
                    """,
                    (entrega,),
                )

    def test_entrada_entregue_congela_tempo_e_evidencia_da_coorte_clv(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.8,
            "regra_versao": "sinais-v1",
            "status": "aprovado",
            "features": {
                "fonte_odds": "packball",
                "cotacao_entrada_clv_estado": "congelada_v1",
            },
        }])[0]
        primeiro_instante = "2026-09-10T10:00:00"
        prova = {"provedor": "telegram", "ok": True, "message_id": 321}
        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue", instante=primeiro_instante,
            provedor="telegram", provedor_destino_id="chat",
            provedor_mensagem_id="321", confirmacao=prova,
        )

        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue",
            instante="2026-09-10T10:05:00",
            provedor="telegram", provedor_destino_id="chat",
            provedor_mensagem_id="321", confirmacao=prova,
        )
        entrega = self.banco.conexao.execute(
            """
            SELECT id,tentado_em,entregue_em,tentativas
            FROM entregas_alertas
            WHERE sinal_id=? AND canal='chat:teste' AND status='entregue'
            """,
            (sinal,),
        ).fetchone()
        self.assertEqual(primeiro_instante, entrega["tentado_em"])
        self.assertEqual(primeiro_instante, entrega["entregue_em"])
        self.assertEqual(2, entrega["tentativas"])

        for comando in (
            "UPDATE entregas_alertas SET entregue_em='2030-01-01' WHERE id=?",
            "UPDATE entregas_alertas SET status='apagado' WHERE id=?",
            "DELETE FROM entregas_alertas WHERE id=?",
        ):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
                with self.banco.conexao:
                    self.banco.conexao.execute(comando, (entrega["id"],))

        for comando in (
            "UPDATE sinais SET criado_em='2030-01-01' WHERE id=?",
            "UPDATE sinais SET features_json='{}' WHERE id=?",
            "DELETE FROM sinais WHERE id=?",
        ):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
                with self.banco.conexao:
                    self.banco.conexao.execute(comando, (sinal,))

        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste:resultado", "entregue",
            instante="2026-09-10T11:00:00",
        )
        with self.banco.conexao:
            alterados = self.banco.conexao.execute(
                """
                UPDATE entregas_alertas SET status='corrigido'
                WHERE sinal_id=? AND canal='chat:teste:resultado'
                """,
                (sinal,),
            ).rowcount
        self.assertEqual(1, alterados)

    def test_clv_pos_alerta_seleciona_janela_e_congela_estado_sem_efeitos(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-12T12:00:00",
            "placar": "0-0",
            "status": "20 '",
        })
        snapshot = self.banco.salvar_registro(registro)
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.80,
            "regra_versao": "teste-clv-pos-alerta-v1",
            "status": "aprovado",
            "features": {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "decisao_em": "2026-09-12T12:00:00",
                "cotacao_entrada_clv_estado": "congelada_v1",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v1",
                    "mercado": "gol_ft", "tipo": "binaria",
                    "linha": 0.5, "over": 1.80, "under": 2.15,
                    "odd_selecionada": 1.80,
                    "fonte": "betsapi", "bookmaker": "bet365",
                    "coletado_em": "2026-09-12T12:00:00",
                    "idade_segundos": 0.0, "cache": False,
                },
            },
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat", "entregue", instante="2026-09-12T12:00:00",
            provedor="telegram", provedor_destino_id="chat",
            provedor_mensagem_id="clv-1",
            confirmacao={
                "provedor": "telegram", "ok": True,
                "message_id": "clv-1",
            },
        )

        self.assertEqual([], self.banco.sinais_entregues_para_clv_pos_alerta(
            agora="2026-09-12T12:01:59"
        ))
        elegiveis = self.banco.sinais_entregues_para_clv_pos_alerta(
            agora="2026-09-12T12:02:10"
        )
        self.assertEqual([sinal], [item["sinal_id"] for item in elegiveis])
        self.assertEqual([], self.banco.sinais_entregues_para_clv_pos_alerta(
            agora="2026-09-12T12:10:01"
        ))

        resultado = self.banco.registrar_estado_clv_pos_alerta(
            sinal,
            {
                "evento_externo_id": 123,
                "placar": "0-0",
                "minuto": 22,
                "status_codigo": "1H",
            },
            consultado_em="2026-09-12T12:02:10",
        )
        self.assertTrue(resultado["persistido"])
        linha = self.banco.conexao.execute(
            "SELECT * FROM observacoes_fontes_odds WHERE id=?",
            (resultado["observacao_id"],),
        ).fetchone()
        payload = json.loads(linha["oferta_json"])
        self.assertEqual("clv_pos_alerta", linha["estado"])
        self.assertEqual("estado-clv-pos-alerta-v3", payload["schema"])
        self.assertEqual(130.0, payload["idade_apos_entrega_segundos"])
        self.assertFalse(payload["oferta_exata_disponivel"])
        self.assertFalse(payload["aplicacao_sinais"])
        self.assertFalse(payload["telegram"])
        self.assertEqual(
            hashlib.sha256(linha["oferta_json"].encode("utf-8")).hexdigest(),
            linha["evidencia_sha256"],
        )
        self.assertEqual([], self.banco.sinais_entregues_para_clv_pos_alerta(
            agora="2026-09-12T12:03:00"
        ))
        repetido = self.banco.registrar_estado_clv_pos_alerta(
            sinal,
            {
                "evento_externo_id": 123,
                "placar": "0-0",
                "minuto": 23,
                "status_codigo": "1H",
            },
            consultado_em="2026-09-12T12:03:00",
        )
        self.assertEqual("ja_persistido", repetido["estado"])
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE observacoes_fontes_odds SET motivo='x' WHERE id=?",
                    (resultado["observacao_id"],),
                )

    def test_clv_pos_alerta_packball_persiste_somente_estado(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-13T12:00:00",
            "placar": "0-0",
            "status": "20 '",
        })
        snapshot = self.banco.salvar_registro(registro)
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.60,
            "regra_versao": "teste-clv-packball-estado-v1",
            "status": "aprovado",
            "features": {
                "fonte_odds": "packball",
                "bookmaker_odds": None,
                "decisao_em": "2026-09-13T12:00:00",
                "cotacao_entrada_clv_estado": "congelada_v1",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v1",
                    "mercado": "gol_ft", "tipo": "binaria",
                    "linha": 0.5, "over": 1.60, "under": 2.40,
                    "odd_selecionada": 1.60,
                    "fonte": "packball", "bookmaker": None,
                    "coletado_em": "2026-09-13T12:00:00",
                    "idade_segundos": 0.0, "cache": False,
                },
            },
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat", "entregue", instante="2026-09-13T12:00:00",
            provedor="telegram", provedor_destino_id="chat",
            provedor_mensagem_id="clv-packball-1",
            confirmacao={
                "provedor": "telegram", "ok": True,
                "message_id": "clv-packball-1",
            },
        )

        elegiveis = self.banco.sinais_entregues_para_clv_pos_alerta(
            agora="2026-09-13T12:02:10"
        )
        self.assertEqual([sinal], [item["sinal_id"] for item in elegiveis])
        self.assertEqual("packball", elegiveis[0]["fonte_odds"])
        resultado = self.banco.registrar_estado_clv_pos_alerta(
            sinal,
            {
                "evento_externo_id": 123,
                "placar": "1-0",
                "minuto": 22,
                "status_codigo": "1H",
            },
            consultado_em="2026-09-13T12:02:10",
        )

        self.assertTrue(resultado["persistido"], resultado)
        linha = self.banco.conexao.execute(
            "SELECT oferta_json FROM observacoes_fontes_odds WHERE id=?",
            (resultado["observacao_id"],),
        ).fetchone()
        payload = json.loads(linha["oferta_json"])
        self.assertEqual("estado-clv-pos-alerta-v3", payload["schema"])
        self.assertEqual("packball", payload["fonte_entrada"])
        self.assertIsNone(payload["bookmaker_entrada"])
        self.assertEqual("somente_estado", payload["modo_coleta"])
        self.assertFalse(payload["oferta_exata_disponivel"])
        self.assertFalse(payload["aplicacao_sinais"])
        self.assertFalse(payload["telegram"])

    def test_clv_pos_alerta_recusa_rotulo_sem_cotacao_congelada_valida(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-13T13:00:00",
            "placar": "0-0", "status": "20 '",
        })
        snapshot = self.banco.salvar_registro(registro)
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.60,
            "regra_versao": "teste-clv-rotulo-invalido-v1",
            "status": "aprovado",
            "features": {
                "fonte_odds": "packball", "bookmaker_odds": None,
                "cotacao_entrada_clv_estado": "congelada_v1",
            },
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat", "entregue", instante="2026-09-13T13:00:00",
            provedor="telegram", provedor_destino_id="chat",
            provedor_mensagem_id="clv-rotulo-invalido-1",
            confirmacao={
                "provedor": "telegram", "ok": True,
                "message_id": "clv-rotulo-invalido-1",
            },
        )

        self.assertEqual(
            [],
            self.banco.sinais_entregues_para_clv_pos_alerta(
                agora="2026-09-13T13:02:10"
            ),
        )
        resultado = self.banco.registrar_estado_clv_pos_alerta(
            sinal,
            {
                "evento_externo_id": 123, "placar": "1-0",
                "minuto": 22, "status_codigo": "1H",
            },
            consultado_em="2026-09-13T13:02:10",
        )
        self.assertEqual("cotacao_entrada_clv_invalida", resultado["estado"])
        self.assertFalse(resultado["persistido"])

    def test_clv_pos_alerta_inclui_escanteio_asiatico_bet365(self):
        registro = self.registro()
        registro.update({
            "coletado_em": "2026-09-12T12:00:00",
            "placar": "0-0",
            "status": "60 '",
        })
        snapshot = self.banco.salvar_registro(registro)
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "escanteios_ft_asiatico",
            "linha": 8.5,
            "odd": 1.84,
            "regra_versao": "teste-clv-escanteio-asiatico-v1",
            "status": "aprovado",
            "features": {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "decisao_em": "2026-09-12T12:00:00",
                "cotacao_entrada_clv_estado": "congelada_v1",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v1",
                    "mercado": "escanteios_ft_asiatico",
                    "tipo": "binaria", "linha": 8.5,
                    "over": 1.84, "under": 2.02,
                    "odd_selecionada": 1.84,
                    "fonte": "betsapi", "bookmaker": "bet365",
                    "coletado_em": "2026-09-12T12:00:00",
                    "idade_segundos": 0.0, "cache": False,
                },
            },
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat", "entregue", instante="2026-09-12T12:00:00",
            provedor="telegram", provedor_destino_id="chat",
            provedor_mensagem_id="clv-corner-1",
            confirmacao={
                "provedor": "telegram", "ok": True,
                "message_id": "clv-corner-1",
            },
        )

        elegiveis = self.banco.sinais_entregues_para_clv_pos_alerta(
            agora="2026-09-12T12:02:10"
        )
        self.assertEqual([sinal], [item["sinal_id"] for item in elegiveis])
        resultado = self.banco.registrar_estado_clv_pos_alerta(
            sinal,
            {
                "evento_externo_id": 123,
                "placar": "0-0",
                "minuto": 62,
                "status_codigo": "2H",
                "escanteios": {"mandante": 4, "visitante": 3},
            },
            consultado_em="2026-09-12T12:02:10",
        )

        self.assertTrue(resultado["persistido"])
        linha = self.banco.conexao.execute(
            "SELECT periodo,mercado,oferta_json FROM observacoes_fontes_odds "
            "WHERE id=?",
            (resultado["observacao_id"],),
        ).fetchone()
        payload = json.loads(linha["oferta_json"])
        self.assertEqual("FT", linha["periodo"])
        self.assertEqual("escanteios_ft_asiatico", linha["mercado"])
        self.assertEqual("escanteios_ft_asiatico", payload["mercado"])
        self.assertEqual(
            {"mandante": 4, "visitante": 3}, payload["escanteios"]
        )
        self.assertFalse(payload["aplicacao_sinais"])
        self.assertFalse(payload["telegram"])

    def test_retencao_preserva_snapshot_e_odds_do_horizonte_clv(self):
        entrada = self.registro()
        entrada["coletado_em"] = "2020-01-01T10:00:00"
        snapshot_entrada = self.banco.salvar_registro(entrada)
        sinal = self.banco.salvar_candidatos(snapshot_entrada, [{
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.8,
            "regra_versao": "sinais-v1",
            "status": "aprovado",
            "features": {
                "fonte_odds": "packball",
                "cotacao_entrada_clv_estado": "congelada_v1",
            },
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue",
            instante="2020-01-01T10:00:30",
        )
        futuro = self.registro()
        futuro["coletado_em"] = "2020-01-01T10:02:40"
        snapshot_futuro = self.banco.salvar_registro(futuro)
        fora_horizonte = self.registro()
        fora_horizonte["coletado_em"] = "2020-01-01T10:20:00"
        snapshot_fora = self.banco.salvar_registro(fora_horizonte)
        odd_futura = self.banco.conexao.execute(
            "SELECT id FROM odds WHERE snapshot_id=? LIMIT 1",
            (snapshot_futuro,),
        ).fetchone()["id"]

        for comando, identificador in (
            ("UPDATE snapshots SET placar='9-9' WHERE id=?", snapshot_futuro),
            ("UPDATE odds SET estrutura_json='{}' WHERE id=?", odd_futura),
            ("DELETE FROM odds WHERE id=?", odd_futura),
            ("DELETE FROM snapshots WHERE id=?", snapshot_futuro),
        ):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "imutave"):
                with self.banco.conexao:
                    self.banco.conexao.execute(comando, (identificador,))

        removidos = self.banco.limpar_dados_antigos(dias=1)

        self.assertGreaterEqual(removidos["snapshots"], 1)
        self.assertIsNotNone(self.banco.conexao.execute(
            "SELECT 1 FROM snapshots WHERE id=?", (snapshot_futuro,)
        ).fetchone())
        self.assertIsNotNone(self.banco.conexao.execute(
            "SELECT 1 FROM odds WHERE id=?", (odd_futura,)
        ).fetchone())
        self.assertIsNone(self.banco.conexao.execute(
            "SELECT 1 FROM snapshots WHERE id=?", (snapshot_fora,)
        ).fetchone())

    def test_linhagem_persistida_do_sinal_e_imutavel(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]

        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutaveis"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE sinais SET regra_fingerprint=? WHERE id=?",
                    ("f" * 64, sinal),
                )

    def test_carrega_contexto_pre_envio_com_origem_e_snapshot_recente(self):
        origem = self.registro()
        origem["coletado_em"] = "2026-08-13T10:00:00"
        snapshot_origem = self.banco.salvar_registro(origem)
        sinal_id = self.banco.salvar_candidatos(
            snapshot_origem,
            [{
                "mercado": "proximo_gol",
                "linha": "casa",
                "odd": 1.8,
                "pontuacao_tecnica": 81,
                "regra_versao": "sinais-v10e",
                "motivos": ["chutes_5min=4"],
                "features": {"minuto": 55, "fonte_odds": "api_football"},
                "status": "aprovado",
            }],
            criado_em="2026-08-13T10:00:01",
        )[0]
        recente = self.registro()
        recente["coletado_em"] = "2026-08-13T10:01:00"
        recente["placar"] = "1-1"
        recente["status"] = "56 '"
        snapshot_recente = self.banco.salvar_registro(recente)

        contexto = self.banco.carregar_contexto_pre_envio(sinal_id)

        self.assertEqual(contexto["sinal"]["criado_em"], "2026-08-13T10:00:01")
        self.assertEqual(contexto["sinal"]["motivos"], ["chutes_5min=4"])
        self.assertEqual(contexto["sinal"]["features"]["minuto"], 55)
        self.assertEqual(contexto["snapshot_origem"]["id"], snapshot_origem)
        self.assertEqual(
            contexto["snapshot_mais_recente"]["id"], snapshot_recente
        )
        self.assertEqual(contexto["snapshot_mais_recente"]["placar"], "1-1")
        self.assertEqual(contexto["partida"]["mandante"], "Time A")
        self.assertFalse(contexto["resolvido"])
        self.assertFalse(contexto["entrega_ja_entregue"])

        self.banco.registrar_entrega_alerta(
            sinal_id, "chat:teste", "entregue"
        )
        contexto_entregue = self.banco.carregar_contexto_pre_envio(sinal_id)
        self.assertTrue(contexto_entregue["entrega_ja_entregue"])
        self.assertIsNone(self.banco.carregar_contexto_pre_envio(999999))

    def test_uma_exposicao_de_gol_aberta_por_partida(self):
        snapshot = self.banco.salvar_registro(self.registro())
        primeiro, segundo, canto = self.banco.salvar_candidatos(snapshot, [
            {"mercado": "proximo_gol", "regra_versao": "v1", "status": "aprovado"},
            {"mercado": "gol_ft", "regra_versao": "v2", "status": "simulacao"},
            {"mercado": "escanteios_ft", "regra_versao": "v1", "status": "aprovado"},
        ])
        self.banco.registrar_entrega_alerta(
            primeiro, "chat:teste", "entregue"
        )
        self.assertTrue(
            self.banco.existe_exposicao_gol_aberta_na_partida(segundo)
        )
        self.assertFalse(
            self.banco.existe_exposicao_gol_aberta_na_partida(canto)
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais(
                    sinal_id, encerrado_em, resultado, retorno_unidades
                ) VALUES (?, ?, 'green', 0.8)
                """,
                (primeiro, datetime.now().replace(microsecond=0).isoformat()),
            )
        self.assertFalse(
            self.banco.existe_exposicao_gol_aberta_na_partida(segundo)
        )

    def test_aviso_aguardar_odd_nao_cria_exposicao_oficial(self):
        snapshot = self.banco.salvar_registro(self.registro())
        acompanhamento, oficial = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.30,
            "regra_versao": "monitoramento-v1",
            "status": "rejeitado",
        }, {
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.44,
            "regra_versao": "oficial-v1",
            "status": "simulacao",
        }])
        self.banco.registrar_entrega_alerta(
            acompanhamento, "chat:aguardar_odd", "entregue"
        )

        self.assertFalse(
            self.banco.existe_exposicao_gol_aberta_na_partida(oficial)
        )

    def test_intervalo_teste_separa_familias_gol_e_escanteio(self):
        snapshot = self.banco.salvar_registro(self.registro())
        gol, canto, outro_gol = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft", "linha": 1.5, "odd": 1.8,
            "pontuacao_tecnica": 80, "regra_versao": "sinais-v6",
            "status": "aprovado",
        }, {
            "mercado": "escanteios_ft_asiatico", "linha": 8.5,
            "odd": 1.9, "pontuacao_tecnica": 82,
            "regra_versao": "sinais-v9d-ft-asiatico-max86",
            "status": "simulacao",
        }, {
            "mercado": "proximo_gol", "linha": "casa", "odd": 1.7,
            "pontuacao_tecnica": 84, "regra_versao": "sinais-v10",
            "status": "aprovado",
        }])
        self.banco.registrar_entrega_alerta(
            gol, "-100:teste", "entregue"
        )

        self.assertFalse(self.banco.alerta_teste_recente_na_partida(canto))
        self.assertTrue(
            self.banco.alerta_teste_recente_na_partida(outro_gol)
        )

    def test_ht_pendente_nao_bloqueia_nova_analise_do_segundo_tempo(self):
        registro_ht = self.registro()
        registro_ht["coletado_em"] = "2026-08-28T10:24:00"
        registro_ht["status"] = "24 '"
        snapshot_ht = self.banco.salvar_registro(registro_ht)
        sinal_ht = self.banco.salvar_candidatos(snapshot_ht, [{
            "mercado": "gol_ht",
            "regra_versao": "ht-v1",
            "status": "simulacao",
            "features": {"minuto": 24, "periodo": "primeiro_tempo"},
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal_ht, "chat:teste", "entregue"
        )

        registro_ft = self.registro()
        registro_ft["coletado_em"] = "2026-08-28T10:52:00"
        registro_ft["status"] = "52 '"
        snapshot_ft = self.banco.salvar_registro(registro_ft)
        sinal_ft = self.banco.salvar_candidatos(snapshot_ft, [{
            "mercado": "gol_ft",
            "regra_versao": "ft-v1",
            "status": "simulacao",
            "features": {"minuto": 52, "periodo": "segundo_tempo"},
        }])[0]

        self.assertFalse(
            self.banco.existe_exposicao_gol_aberta_na_partida(sinal_ft)
        )

        sinal_sobreposto = self.banco.salvar_candidatos(snapshot_ht, [{
            "mercado": "gol_ft",
            "regra_versao": "ft-v2",
            "status": "simulacao",
            "features": {"minuto": 24, "periodo": "primeiro_tempo"},
        }])[0]
        self.assertTrue(
            self.banco.existe_exposicao_gol_aberta_na_partida(
                sinal_sobreposto
            )
        )

    def test_expira_pre_envio_sem_bloquear_nova_decisao_independente(self):
        snapshot = self.banco.salvar_registro(self.registro())
        antigo = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
            "motivos": ["janela_ft"],
        }])[0]

        self.assertTrue(self.banco.expirar_sinal_pre_envio(
            antigo, "leitura_envelhecida"
        ))
        expirado = self.banco.conexao.execute(
            "SELECT status, motivos_json FROM sinais WHERE id=?", (antigo,)
        ).fetchone()
        self.assertEqual(expirado["status"], "rejeitado")
        self.assertEqual(
            json.loads(expirado["motivos_json"]),
            ["janela_ft", "bloqueio:leitura_envelhecida"],
        )
        self.assertFalse(self.banco.expirar_sinal_pre_envio(
            antigo, "leitura_envelhecida"
        ))

        novo = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]
        self.assertTrue(
            self.banco.sinal_e_primeira_decisao_independente(novo)
        )

    def test_reserva_entrega_e_atomica_entre_duas_conexoes(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]
        concorrente = BancoMonitor(self.caminho)
        try:
            primeira = self.banco.reservar_entrega_alerta(
                sinal, "chat:teste"
            )
            segunda = concorrente.reservar_entrega_alerta(
                sinal, "chat:teste"
            )

            self.assertTrue(primeira)
            self.assertIsNone(segunda)
            self.assertTrue(self.banco.reserva_entrega_valida(
                sinal, "chat:teste", primeira
            ))
            self.assertFalse(concorrente.reserva_entrega_valida(
                sinal, "chat:teste", "token-estranho"
            ))
            registros = self.banco.conexao.execute(
                """
                SELECT status, reserva_token FROM entregas_alertas
                WHERE sinal_id=? AND canal=?
                """,
                (sinal, "chat:teste"),
            ).fetchall()
            self.assertEqual(len(registros), 1)
            self.assertEqual(registros[0]["status"], "enviando")
            self.assertEqual(registros[0]["reserva_token"], primeira)
        finally:
            concorrente.fechar()

    def test_reserva_recusa_sinal_resolvido_ou_snapshot_substituido(self):
        snapshot = self.banco.salvar_registro(self.registro())
        obsoleto = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]
        novo = self.registro()
        novo["coletado_em"] = (
            datetime.now().replace(microsecond=0) + timedelta(seconds=1)
        ).isoformat()
        novo["placar"] = "2-0"
        self.banco.salvar_registro(novo)
        self.assertIsNone(self.banco.reservar_entrega_alerta(
            obsoleto, "chat:obsoleto"
        ))

        registro_resolvido = self.registro()
        registro_resolvido["url"] = (
            "https://packball.com/pt/matches/999/match/a-vs-b/live"
        )
        snapshot_resolvido = self.banco.salvar_registro(registro_resolvido)
        resolvido = self.banco.salvar_candidatos(snapshot_resolvido, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-07-20T13:00:00', 'red', -1, ?, 'packball')
                """,
                (resolvido, snapshot_resolvido),
            )
        self.assertIsNone(self.banco.reservar_entrega_alerta(
            resolvido, "chat:resolvido"
        ))

    def test_expiracao_pre_envio_preserva_entregue_resolvido_e_simulacao(self):
        def novo_sinal(indice, status="aprovado"):
            registro = self.registro()
            registro["url"] = (
                f"https://packball.com/pt/matches/{indice}/match/a-vs-b/live"
            )
            snapshot = self.banco.salvar_registro(registro)
            sinal = self.banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft",
                "regra_versao": "sinais-v1",
                "status": status,
            }])[0]
            return snapshot, sinal

        _, entregue = novo_sinal(201)
        self.banco.registrar_entrega_alerta(entregue, "chat:teste", "entregue")
        self.assertFalse(self.banco.expirar_sinal_pre_envio(entregue, "velho"))

        snapshot_resolvido, resolvido = novo_sinal(202)
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-08-13T10:05:00', 'red', ?, 'packball')
                """,
                (resolvido, snapshot_resolvido),
            )
        self.assertFalse(self.banco.expirar_sinal_pre_envio(
            resolvido, "velho"
        ))

        _, simulacao = novo_sinal(203, "simulacao")
        self.assertFalse(self.banco.expirar_sinal_pre_envio(
            simulacao, "velho"
        ))

        estados = dict(self.banco.conexao.execute(
            "SELECT id, status FROM sinais WHERE id IN (?, ?, ?)",
            (entregue, resolvido, simulacao),
        ).fetchall())
        self.assertEqual(estados[entregue], "aprovado")
        self.assertEqual(estados[resolvido], "aprovado")
        self.assertEqual(estados[simulacao], "simulacao")

    def test_resultado_so_pode_ser_reaberto_com_revisao_correspondente(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]
        encerrado_em = self.banco.conexao.execute(
            "SELECT coletado_em FROM snapshots WHERE id=?", (snapshot,)
        ).fetchone()[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, 'green', 0.8, 'evidencia', ?, 'packball')
                """,
                (sinal, encerrado_em, snapshot),
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutaveis"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE resultados_sinais SET resultado='red' "
                    "WHERE sinal_id=?",
                    (sinal,),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "exige revisao"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "DELETE FROM resultados_sinais WHERE sinal_id=?",
                    (sinal,),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "nao corresponde"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    """
                    INSERT INTO revisoes_resultados (
                        sinal_id, revisado_em, encerrado_em_anterior,
                        resultado_anterior, retorno_anterior,
                        observacao_anterior, snapshot_id_liquidacao_anterior,
                        fonte_resultado_anterior, motivo
                    ) VALUES (?, ?, ?, 'red', -1, 'evidencia', ?,
                              'packball', 'revisao incoerente')
                    """,
                    (sinal, encerrado_em, encerrado_em, snapshot),
                )

        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior,
                    observacao_anterior, snapshot_id_liquidacao_anterior,
                    fonte_resultado_anterior, motivo
                ) VALUES (?, ?, ?, 'green', 0.8, 'evidencia', ?,
                          'packball', 'resultado provisorio')
                """,
                (sinal, encerrado_em, encerrado_em, snapshot),
            )
            revisao = cursor.lastrowid
            self.banco.conexao.execute(
                "DELETE FROM resultados_sinais WHERE sinal_id=?", (sinal,)
            )
            self.banco.conexao.execute(
                """
                UPDATE revisoes_resultados SET notificacao_status='entregue'
                WHERE id=?
                """,
                (revisao,),
            )

        self.assertIsNone(self.banco.conexao.execute(
            "SELECT 1 FROM resultados_sinais WHERE sinal_id=?", (sinal,)
        ).fetchone())
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "UPDATE revisoes_resultados SET motivo='alterado' "
                    "WHERE id=?",
                    (revisao,),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "imutaveis"):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    "DELETE FROM revisoes_resultados WHERE id=?", (revisao,)
                )

    def test_historico_de_calibracao_nao_aceita_update_nem_delete(self):
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO historico_calibracoes (
                    mercado, regra_versao, registrado_em, amostra, ativa,
                    amostra_fingerprint, modelo_hash, modelo_json
                ) VALUES ('gol_ft', 'sinais-v1', ?, 0, 0, '', ?, '{}')
                """,
                (datetime.now().isoformat(), "a" * 64),
            )
        for comando in (
            "UPDATE historico_calibracoes SET amostra=1",
            "DELETE FROM historico_calibracoes",
        ):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "imutavel"):
                with self.banco.conexao:
                    self.banco.conexao.execute(comando)

    def test_migra_calibracao_atual_para_historico_sem_duplicar(self):
        modelo = {
            "amostra": 23,
            "amostra_fingerprint": "f" * 64,
            "ativa": False,
            "motivo": "amostra_insuficiente",
        }
        self.banco.conexao.execute(
            """
            INSERT INTO calibracoes (
                mercado, regra_versao, atualizado_em,
                amostra, ativa, modelo_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "gol_ft", "sinais-v4", "2026-07-21T12:00:00",
                23, 0, json.dumps(modelo),
            ),
        )
        self.banco.conexao.commit()

        self.banco._criar_esquema()
        self.banco._criar_esquema()

        historico = self.banco.conexao.execute(
            """
            SELECT COUNT(*) AS total, modelo_hash, amostra_fingerprint,
                   motivo
            FROM historico_calibracoes
            WHERE mercado='gol_ft' AND regra_versao='sinais-v4'
            """
        ).fetchone()
        self.assertEqual(historico["total"], 1)
        self.assertEqual(len(historico["modelo_hash"]), 64)
        self.assertEqual(historico["amostra_fingerprint"], "f" * 64)
        self.assertEqual(historico["motivo"], "amostra_insuficiente")

    def test_indices_persistentes_cobrem_consultas_criticas_de_sinais(self):
        indices = {
            item["name"]
            for item in self.banco.conexao.execute(
                "PRAGMA index_list(sinais)"
            ).fetchall()
        }
        self.assertTrue({
            "idx_sinais_partida_status",
            "idx_sinais_grupo_independente",
            "idx_sinais_snapshot",
            "idx_sinais_linhagem_calibracao",
        }.issubset(indices))

        plano_pendentes = self.banco.conexao.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT s.id
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.partida_id=?
              AND s.status IN ('aprovado', 'simulacao')
              AND r.sinal_id IS NULL
            """,
            (1,),
        ).fetchall()
        detalhes = " ".join(item["detail"] for item in plano_pendentes)
        self.assertIn("idx_sinais_partida_status", detalhes)
        self.assertNotIn("AUTOMATIC", detalhes)

        plano_grupo = self.banco.conexao.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT 1 FROM sinais
            WHERE partida_id=? AND mercado=? AND regra_versao=?
              AND status='aprovado' AND id<?
            """,
            (1, "gol_ft", "sinais-v4", 100),
        ).fetchall()
        detalhes_grupo = " ".join(item["detail"] for item in plano_grupo)
        self.assertIn("idx_sinais_grupo_independente", detalhes_grupo)

        plano_snapshot = self.banco.conexao.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM sinais WHERE snapshot_id=?",
            (1,),
        ).fetchall()
        detalhes_snapshot = " ".join(
            item["detail"] for item in plano_snapshot
        )
        self.assertIn("idx_sinais_snapshot", detalhes_snapshot)

    def test_salva_snapshot_e_odds(self):
        self.assertTrue(self.banco.salvar_registro(self.registro()))
        self.assertEqual(
            self.banco.contagens(),
            {
                "partidas": 1,
                "snapshots": 1,
                "odds": 1,
                "eventos": 0,
                "sinais": 0,
            },
        )
        partida = self.banco.conexao.execute(
            "SELECT api_fixture_id, api_orientacao FROM partidas"
        ).fetchone()
        self.assertEqual(tuple(partida), (123, "direta"))

    def test_cache_de_odds_preserva_instante_original(self):
        registro = self.registro()
        origem = "2026-07-20T12:00:00"
        registro["odds"]["ao_vivo"][0]["coletado_em"] = origem
        self.banco.salvar_registro(registro)

        cache = self.banco.carregar_ultimas_odds(registro["url"])
        segundo = self.registro()
        segundo["coletado_em"] = (
            datetime.now().replace(microsecond=0) + timedelta(minutes=1)
        ).isoformat()
        segundo["odds"] = cache
        self.banco.salvar_registro(segundo)

        recarregado = self.banco.carregar_ultimas_odds(registro["url"])
        self.assertEqual(
            recarregado["_metadados"]["coletado_em"], origem
        )
        self.assertEqual(
            recarregado["ao_vivo"][0]["coletado_em"], origem
        )
        self.assertGreater(
            recarregado["_metadados"]["idade_segundos"], 360
        )

    def test_carrega_instantes_reais_para_restaurar_agendamento(self):
        registro = self.registro()
        registro["coletado_em"] = "2026-07-21T12:10:00"
        registro["odds"]["ao_vivo"][0]["coletado_em"] = (
            "2026-07-21T12:05:00"
        )
        self.banco.salvar_registro(registro)
        segundo = self.registro()
        segundo["coletado_em"] = "2026-07-21T12:11:00"
        segundo["odds"] = self.banco.carregar_ultimas_odds(registro["url"])
        self.banco.salvar_registro(segundo)

        estado = self.banco.carregar_instantes_agendamento([
            registro["url"]
        ])

        self.assertEqual(
            estado[registro["url"]]["ultima_coleta"],
            "2026-07-21T12:11:00",
        )
        self.assertEqual(
            estado[registro["url"]]["ultima_odds"],
            "2026-07-21T12:05:00",
        )
        self.assertEqual(self.banco.carregar_instantes_agendamento([]), {})

    def test_nao_duplica_snapshot(self):
        registro = self.registro()
        self.assertTrue(self.banco.salvar_registro(registro))
        self.assertFalse(self.banco.salvar_registro(registro))
        self.assertEqual(self.banco.contagens()["snapshots"], 1)
        self.assertEqual(self.banco.contagens()["odds"], 1)

    def test_restaura_historico_recente(self):
        registro = self.registro()
        self.banco.salvar_registro(registro)
        historico = self.banco.carregar_historico_recente()
        self.assertIn(registro["url"], historico)
        self.assertEqual(
            historico[registro["url"]][0]["estatisticas"]["Chutes"],
            "10-5",
        )

    def test_salva_candidatos_aprovados_e_rejeitados(self):
        snapshot_id = self.banco.salvar_registro(self.registro())
        ids = self.banco.salvar_candidatos(
            snapshot_id,
            [
                {
                    "mercado": "gol_ft",
                    "pontuacao_tecnica": 82,
                    "probabilidade_calibrada": None,
                    "regra_versao": "sinais-v1",
                    "motivos": ["pressão alta"],
                    "bloqueios": [],
                    "features": {
                        "schema_versao": "features-temporais-v2",
                        "janelas": {"5": {"chutes_por_minuto": 1.2}},
                    },
                    "status": "aprovado",
                },
                {
                    "mercado": "proximo_escanteio",
                    "pontuacao_tecnica": 40,
                    "probabilidade_calibrada": None,
                    "regra_versao": "sinais-v1",
                    "motivos": [],
                    "bloqueios": ["historico_5min_insuficiente"],
                    "status": "rejeitado",
                },
            ],
        )
        self.assertEqual(len(ids), 2)
        self.assertEqual(self.banco.contagens()["sinais"], 2)
        features = self.banco.conexao.execute(
            "SELECT features_json FROM sinais WHERE id=?", (ids[0],)
        ).fetchone()[0]
        self.assertEqual(
            json.loads(features)["schema_versao"],
            "features-temporais-v2",
        )

    def test_migra_tabela_sinais_antiga_sem_perder_registros(self):
        self.banco.fechar()
        conexao = sqlite3.connect(self.caminho)
        conexao.execute("DROP TABLE sinais")
        conexao.execute(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partida_id INTEGER NOT NULL,
                snapshot_id INTEGER NOT NULL,
                criado_em TEXT NOT NULL,
                mercado TEXT NOT NULL,
                linha REAL,
                odd REAL,
                pontuacao_tecnica REAL,
                probabilidade_calibrada REAL,
                regra_versao TEXT NOT NULL,
                motivos_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL
            )
            """
        )
        conexao.execute(
            """
            INSERT INTO sinais (
                partida_id, snapshot_id, criado_em, mercado,
                regra_versao, status
            ) VALUES (1, 1, '2026-07-20T12:00:00', 'gol_ft',
                      'sinais-v4', 'rejeitado')
            """
        )
        conexao.commit()
        conexao.close()

        self.banco = BancoMonitor(self.caminho)

        colunas = {
            linha["name"]
            for linha in self.banco.conexao.execute(
                "PRAGMA table_info(sinais)"
            ).fetchall()
        }
        self.assertIn("features_json", colunas)
        registro = self.banco.conexao.execute(
            "SELECT features_json FROM sinais"
        ).fetchone()
        self.assertEqual(registro[0], "{}")

    def test_isola_sinal_aprovado_repetido_enquanto_primeiro_esta_aberto(self):
        primeiro = self.banco.salvar_registro(self.registro())
        candidato = {
            "mercado": "gol_ft",
            "linha": 1.5,
            "pontuacao_tecnica": 82,
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }
        self.banco.salvar_candidatos(primeiro, [candidato.copy()])
        registro = self.registro()
        registro["coletado_em"] = "2099-01-01T00:01:00"
        segundo = self.banco.salvar_registro(registro)
        repetido = candidato.copy()
        self.banco.salvar_candidatos(segundo, [repetido])
        estados = self.banco.conexao.execute(
            "SELECT status FROM sinais ORDER BY id"
        ).fetchall()
        self.assertEqual([item[0] for item in estados], ["aprovado", "duplicado"])
        self.assertEqual(repetido["_status_persistido"], "duplicado")

    def test_normaliza_repeticoes_antigas_sem_apagar_historico(self):
        snapshot = self.banco.salvar_registro(self.registro())
        with self.banco.conexao:
            for _ in range(2):
                self.banco.conexao.execute(
                    """
                    INSERT INTO sinais (
                        partida_id, snapshot_id, criado_em, mercado,
                        regra_versao, status
                    ) SELECT partida_id, id, coletado_em, 'gol_ft',
                             'sinais-v1', 'aprovado'
                      FROM snapshots WHERE id=?
                    """,
                    (snapshot,),
                )
        self.assertEqual(self.banco.normalizar_sinais_duplicados(), 1)
        estados = self.banco.conexao.execute(
            "SELECT status FROM sinais ORDER BY id"
        ).fetchall()
        self.assertEqual([item[0] for item in estados], ["aprovado", "duplicado"])

    def test_normaliza_times_e_extrai_id_estavel(self):
        self.banco.salvar_registro(self.registro())
        partida = self.banco.conexao.execute(
            "SELECT * FROM partidas"
        ).fetchone()
        self.assertEqual(partida["mandante_normalizado"], "timea")
        self.assertEqual(partida["packball_partida_id"], 1)
        self.assertEqual(normalizar_texto("São Gonçalo"), "saogoncalo")
        self.assertEqual(
            extrair_packball_id("https://packball.com/pt/matches/197/live"),
            197,
        )

    def test_recupera_ultimas_odds_para_fila_rapida(self):
        registro = self.registro()
        registro["odds"]["ao_vivo"][0].update(
            {
                "categoria": "gols",
                "escopo": "total",
                "formato": "duas_opcoes",
                "ofertas": [{"linha": 2.5, "over": 1.8, "under": 2.0}],
                "ofertas_exatamente": [],
                "ofertas_periodos": {
                    "1T": {
                        "formato": "duas_opcoes",
                        "ofertas": [
                            {"linha": 0.5, "over": 1.5, "under": 2.4}
                        ],
                    }
                },
                "fonte": "packball",
                "coletado_em": registro["coletado_em"],
                "cache": False,
            }
        )
        self.banco.salvar_registro(registro)
        odds = self.banco.carregar_ultimas_odds(registro["url"])
        self.assertEqual(odds["ao_vivo"][0]["ofertas"][0]["over"], 1.8)
        self.assertEqual(odds["ao_vivo"][0]["escopo"], "total")
        self.assertEqual(odds["ao_vivo"][0]["formato"], "duas_opcoes")
        self.assertEqual(
            odds["ao_vivo"][0]["ofertas_periodos"]["1T"]["ofertas"][0]["linha"],
            0.5,
        )
        self.assertTrue(odds["ao_vivo"][0]["cache"])

    def test_cache_nao_fabrica_proveniencia_ausente(self):
        registro = self.registro()
        self.banco.salvar_registro(registro)

        odds = self.banco.carregar_ultimas_odds(registro["url"])

        mercado = odds["ao_vivo"][0]
        self.assertIsNone(mercado["fonte"])
        self.assertIsNone(mercado["coletado_em"])
        self.assertIsNone(mercado["cache"])

    def test_retencao_remove_descartados_mas_preserva_sinal_aprovado(self):
        antigo = self.registro()
        antigo["coletado_em"] = "2020-01-01T00:00:00"
        snapshot_antigo = self.banco.salvar_registro(antigo)
        self.banco.salvar_candidatos(
            snapshot_antigo,
            [{
                "mercado": "gol_ft",
                "pontuacao_tecnica": 20,
                "regra_versao": "sinais-v1",
                "status": "rejeitado",
            }],
            "2020-01-01T00:00:00",
        )
        aprovado = self.registro()
        aprovado["coletado_em"] = "2020-01-01T00:01:00"
        snapshot_aprovado = self.banco.salvar_registro(aprovado)
        self.banco.salvar_candidatos(
            snapshot_aprovado,
            [{
                "mercado": "gol_ht",
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }],
            "2020-01-01T00:01:00",
        )
        resultado = self.banco.limpar_dados_antigos(dias=180)
        self.assertEqual(resultado["sinais_descartados"], 1)
        self.assertEqual(resultado["snapshots"], 1)
        snapshots = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id"
        ).fetchall()
        self.assertEqual([item[0] for item in snapshots], [snapshot_aprovado])

    def test_checkpoint_wal_e_seguro(self):
        self.banco.salvar_registro(self.registro())
        resultado = self.banco.checkpoint_wal()
        self.assertEqual(
            set(resultado),
            {"ocupado", "paginas", "checkpoint"},
        )
        self.assertTrue(
            all(isinstance(valor, int) for valor in resultado.values())
        )

    def test_resume_green_red_e_risco_apenas_de_alertas_oficiais(self):
        def adicionar(indice, resultado, retorno, encerrado_em, canal="123"):
            registro = self.registro()
            registro["url"] = (
                f"https://packball.com/pt/matches/{indice}/match/a-vs-b/live"
            )
            snapshot = self.banco.salvar_registro(registro)
            sinal_id = self.banco.salvar_candidatos(
                snapshot,
                [{
                    "mercado": "gol_ft",
                    "regra_versao": "sinais-v4",
                    "status": "aprovado",
                }],
            )[0]
            self.banco.registrar_entrega_alerta(
                sinal_id, canal, "entregue"
            )
            with self.banco.conexao:
                self.banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, observacao
                    ) VALUES (?, ?, ?, ?, 'teste')
                    """,
                    (sinal_id, encerrado_em, resultado, retorno),
                )

        adicionar(1, "green", 0.8, "2026-07-20T10:00:00")
        adicionar(2, "half_green", 0.4, "2026-07-21T09:00:00")
        adicionar(3, "red", -1.0, "2026-07-21T10:00:00")
        adicionar(4, "half_red", -0.5, "2026-07-21T11:00:00")
        adicionar(5, "green", 0.9, "2026-07-21T11:30:00", "123:teste")

        resumo = self.banco.resumir_risco_alertas_oficiais(
            datetime(2026, 7, 21, 12, 0)
        )

        self.assertEqual(resumo["resultados_oficiais"], 4)
        self.assertEqual(resumo["greens_total"], 2)
        self.assertEqual(resumo["reds_total"], 2)
        self.assertEqual(resumo["greens_hoje"], 1)
        self.assertEqual(resumo["reds_hoje"], 2)
        self.assertEqual(resumo["reds_consecutivos_24h"], 2)
        self.assertAlmostEqual(resumo["retorno_realizado_hoje"], -1.1)
        self.assertAlmostEqual(resumo["perda_realizada_hoje"], 1.1)
        placar_oficial = self.banco.resumir_placar_por_mercado()
        placar_simulado = self.banco.resumir_placar_por_mercado(
            simulacoes=True
        )
        placar_simulado_v4 = self.banco.resumir_placar_por_mercado(
            simulacoes=True, regra_versao="sinais-v4"
        )
        placar_simulado_futuro = self.banco.resumir_placar_por_mercado(
            simulacoes=True,
            regra_versao="sinais-v4",
            iniciado_em="9999-01-01T00:00:00",
        )
        self.assertEqual(
            placar_oficial["gol_ft"],
            {"greens": 2, "reds": 2, "pendentes": 0},
        )
        self.assertEqual(
            placar_simulado["gol_ft"],
            {"greens": 1, "reds": 0, "pendentes": 0},
        )
        self.assertEqual(
            placar_simulado_v4["gol_ft"],
            {"greens": 1, "reds": 0, "pendentes": 0},
        )
        self.assertEqual(placar_simulado_futuro, {})

    def test_registra_e_consulta_cooldown_de_finalizacao(self):
        snapshot = self.banco.salvar_registro(self.registro())
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot,)
        ).fetchone()[0]
        agora = datetime(2026, 7, 20, 12, 0)
        self.banco.registrar_consulta_finalizacao(
            partida_id,
            "packball",
            "em_andamento",
            status_observado="status-2",
            instante=agora,
        )
        self.assertTrue(
            self.banco.consulta_finalizacao_recente(
                partida_id, "packball", agora=agora
            )
        )

    def test_claim_resultado_e_atomico_e_sobrevive_reinicio(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.8,
            "regra_versao": "sinais-v1",
            "status": "simulacao",
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue"
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, '2026-08-13T20:00:00', 'green', 0.8,
                          ?, 'packball')
                """,
                (sinal, snapshot),
            )
        resultado = self.banco.conexao.execute(
            "SELECT * FROM resultados_sinais WHERE sinal_id=?", (sinal,)
        ).fetchone()
        concorrente = BancoMonitor(self.caminho)
        try:
            token = self.banco.reservar_notificacao_resultado(
                sinal, "chat:teste", resultado
            )
            self.assertTrue(token)
            self.assertIsNone(concorrente.reservar_notificacao_resultado(
                sinal, "chat:teste", resultado
            ))
        finally:
            concorrente.fechar()

        reiniciado = BancoMonitor(self.caminho)
        try:
            self.assertIsNone(reiniciado.reservar_notificacao_resultado(
                sinal, "chat:teste", resultado
            ))
            self.assertTrue(reiniciado.reserva_notificacao_resultado_valida(
                sinal, "chat:teste", token, resultado
            ))
            self.assertFalse(reiniciado.reserva_notificacao_resultado_valida(
                sinal, "chat:teste", "token-alheio", resultado
            ))
            divergente = dict(resultado)
            divergente["resultado"] = "red"
            self.assertFalse(reiniciado.reserva_notificacao_resultado_valida(
                sinal, "chat:teste", token, divergente
            ))
            self.assertEqual(
                reiniciado.resultados_simulacoes_nao_notificados(), []
            )
            self.assertFalse(reiniciado.finalizar_notificacao_alerta(
                sinal, "chat:teste:resultado", "token-alheio", "entregue"
            ))
            self.assertTrue(reiniciado.finalizar_notificacao_alerta(
                sinal,
                "chat:teste:resultado",
                token,
                "entregue",
                provedor="telegram",
                provedor_destino_id="chat",
                provedor_mensagem_id="9001",
                confirmacao={
                    "provedor": "telegram", "ok": True,
                    "message_id": 9001,
                },
            ))
        finally:
            reiniciado.fechar()

    def test_claim_cancelamento_reconfere_sinal_pendente(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])[0]
        self.banco.registrar_entrega_alerta(sinal, "chat", "entregue")
        concorrente = BancoMonitor(self.caminho)
        try:
            token = self.banco.reservar_notificacao_cancelamento(
                sinal, "chat"
            )
            self.assertTrue(token)
            self.assertIsNone(
                concorrente.reservar_notificacao_cancelamento(sinal, "chat")
            )
            self.assertTrue(
                self.banco.reserva_notificacao_cancelamento_valida(
                    sinal, "chat", token
                )
            )
            with concorrente.conexao:
                concorrente.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado, retorno_unidades
                    ) VALUES (?, '2026-08-13T20:00:00', 'red', -1.0)
                    """,
                    (sinal,),
                )
            self.assertFalse(
                self.banco.reserva_notificacao_cancelamento_valida(
                    sinal, "chat", token
                )
            )
            self.assertTrue(self.banco.finalizar_notificacao_alerta(
                sinal, "chat:cancelamento", token, "cancelado",
                "resultado_registrado_antes_do_post",
            ))
        finally:
            concorrente.fechar()

    def test_claim_correcao_finaliza_claim_e_revisao_atomicamente(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.8,
            "regra_versao": "sinais-v1",
            "status": "simulacao",
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue"
        )
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior, motivo
                ) VALUES (?, '2026-08-13T20:01:00',
                          '2026-08-13T20:00:00', 'green', 0.8,
                          'resultado provisorio')
                """,
                (sinal,),
            )
        revisao = cursor.lastrowid
        concorrente = BancoMonitor(self.caminho)
        try:
            token = self.banco.reservar_notificacao_correcao(
                revisao, sinal, "chat:teste"
            )
            self.assertTrue(token)
            self.assertIsNone(concorrente.reservar_notificacao_correcao(
                revisao, sinal, "chat:teste"
            ))
            self.assertTrue(self.banco.reserva_notificacao_correcao_valida(
                revisao, sinal, "chat:teste", token
            ))
            self.assertFalse(self.banco.finalizar_notificacao_correcao(
                revisao, sinal, "chat:teste", "token-alheio", "entregue"
            ))
            self.assertTrue(self.banco.finalizar_notificacao_correcao(
                revisao,
                sinal,
                "chat:teste",
                token,
                "entregue",
                provedor="telegram",
                provedor_destino_id="chat",
                provedor_mensagem_id="9002",
                confirmacao={
                    "provedor": "telegram", "ok": True,
                    "message_id": 9002,
                },
            ))
            estados = self.banco.conexao.execute(
                """
                SELECT rev.notificacao_status, aviso.status AS claim_status
                FROM revisoes_resultados rev
                JOIN entregas_alertas aviso ON aviso.sinal_id=rev.sinal_id
                WHERE rev.id=? AND aviso.canal=?
                """,
                (revisao, f"chat:teste:correcao:{revisao}"),
            ).fetchone()
            self.assertEqual(estados["notificacao_status"], "entregue")
            self.assertEqual(estados["claim_status"], "controle_entregue")
            self.assertEqual(
                self.banco.revisoes_simulacoes_nao_notificadas(), []
            )
        finally:
            concorrente.fechar()

    def test_revisao_entregue_nao_gera_segundo_aviso_de_resultado(self):
        snapshot = self.banco.salvar_registro(self.registro())
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "escanteios_ft_asiatico",
            "linha": 9.5,
            "odd": 1.825,
            "regra_versao": "sinais-v1",
            "status": "simulacao",
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue"
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    fonte_resultado
                ) VALUES (?, '2026-08-13T19:59:00', 'red', -1.0,
                          'packball')
                """,
                (sinal,),
            )
            self.banco.conexao.execute(
                """
                INSERT INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior, motivo,
                    fonte_resultado_anterior, notificacao_status
                ) VALUES (?, '2026-08-13T20:01:00',
                          '2026-08-13T19:59:00', 'red', -1.0,
                          'odd substituida antes do envio', 'packball',
                          'pendente')
                """,
                (sinal,),
            )
            self.banco.conexao.execute(
                "DELETE FROM resultados_sinais WHERE sinal_id=?",
                (sinal,),
            )
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    fonte_resultado
                ) VALUES (?, '2026-08-13T20:00:00', 'void', 0.0,
                          'invalidacao_operacional_odds')
                """,
                (sinal,),
            )
            self.banco.conexao.execute(
                """
                UPDATE revisoes_resultados
                SET notificacao_status='entregue'
                WHERE sinal_id=?
                """,
                (sinal,),
            )

        self.assertEqual(
            self.banco.resultados_simulacoes_nao_notificados(), []
        )

    def test_esquema_thestatsapi_e_auditavel_e_usa_match_id_texto(self):
        auditoria = auditar_compatibilidade(self.banco.conexao)
        self.assertTrue(auditoria["compativel"], auditoria)
        self.assertFalse(auditoria["tabelas_ausentes"])
        self.assertFalse(auditoria["indices_ausentes"])

        for tabela in (
            "pareamentos_thestatsapi",
            "historico_thestatsapi_live",
            "odds_thestatsapi_live",
        ):
            colunas = {
                linha["name"]: linha["type"]
                for linha in self.banco.conexao.execute(
                    f'PRAGMA table_info("{tabela}")'
                ).fetchall()
            }
            self.assertEqual(colunas["match_id"], "TEXT")
            self.assertIn("aplicacao_sinais", colunas)

        migracao = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            ("migracao_schema:thestatsapi_sombra:v1",),
        ).fetchone()
        self.assertIsNotNone(migracao)
        self.assertFalse(json.loads(migracao["valor"])["aplicacao_sinais"])

    def test_pareamento_thestatsapi_preserva_id_texto_e_e_idempotente(self):
        agora = datetime(2026, 8, 13, 12, 0)
        pareamento = {
            "packball_url": "https://packball.com/pt/matches/51/live",
            "match_id": "mt_01J8ABC_xyz",
            "orientacao": "direta",
            "similaridade": 0.97,
            "margem": 0.11,
            "mandante_api": "Time API A",
            "visitante_api": "Time API B",
            "diagnostico": {"segundo_colocado": 0.86},
        }
        primeiro = self.banco.salvar_pareamento_thestatsapi(
            pareamento, agora=agora
        )
        segundo = self.banco.salvar_pareamento_thestatsapi(
            pareamento, agora=agora
        )

        self.assertEqual(primeiro["estado"], "inserido")
        self.assertEqual(segundo["estado"], "inalterado")
        self.assertFalse(segundo["aplicacao_sinais"])
        salvo = self.banco.obter_pareamento_thestatsapi(
            packball_url=pareamento["packball_url"]
        )
        self.assertEqual(salvo["match_id"], "mt_01J8ABC_xyz")
        self.assertEqual(salvo["diagnostico"]["segundo_colocado"], 0.86)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM pareamentos_thestatsapi"
            ).fetchone()[0],
            1,
        )

        alterado = dict(pareamento, similaridade=0.99)
        resultado = self.banco.salvar_pareamento_thestatsapi(
            alterado, agora=agora + timedelta(minutes=1)
        )
        self.assertEqual(resultado["estado"], "atualizado")
        self.assertEqual(
            self.banco.obter_pareamento_thestatsapi(
                match_id="mt_01J8ABC_xyz"
            )["similaridade"],
            0.99,
        )

    def test_historico_thestatsapi_e_idempotente_e_aplica_retencao(self):
        agora = datetime(2026, 8, 13, 12, 0)
        url = "https://packball.com/pt/matches/52/live"
        recente = {
            "match_id": "mt_live_52",
            "packball_url": url,
            "coletado_em": "2026-08-13T11:59:00",
            "minuto": 57,
            "periodo": "2T",
            "placar": [1, 0],
            "orientacao": "direta",
            "chutes_mandante": 12,
            "chutes_visitante": 6,
            "chutes_gol_mandante": 5,
            "chutes_gol_visitante": 2,
            "escanteios_mandante": 7,
            "escanteios_visitante": 3,
            "xg_mandante": 1.42,
            "xg_visitante": 0.51,
            "completo": True,
        }
        antigo = dict(
            recente,
            coletado_em="2026-07-01T10:00:00",
            minuto=10,
        )
        resultado = self.banco.salvar_historico_thestatsapi_live(
            [antigo, recente], agora=agora, retencao_dias=30
        )
        self.assertEqual(resultado["inseridos"], 2)
        self.assertEqual(resultado["removidos_retencao"], 1)
        self.assertFalse(resultado["aplicacao_sinais"])

        repetido = dict(recente, chutes_mandante=13)
        repeticao = self.banco.salvar_historico_thestatsapi_live(
            [repetido], agora=agora
        )
        self.assertEqual(repeticao["inseridos"], 0)
        self.assertEqual(repeticao["atualizados"], 1)
        serie = self.banco.carregar_serie_thestatsapi_recente(
            match_id="mt_live_52", agora=agora
        )
        self.assertEqual(len(serie), 1)
        self.assertEqual(serie[0]["match_id"], "mt_live_52")
        self.assertEqual(serie[0]["placar"], "1-0")
        self.assertEqual(serie[0]["placar_mandante"], 1)
        self.assertEqual(serie[0]["chutes_mandante"], 13)
        self.assertEqual(serie[0]["fonte"], "thestatsapi")
        self.assertFalse(serie[0]["aplicacao_sinais"])

    def test_odds_thestatsapi_aceita_envelope_sem_perder_taxonomia(self):
        agora = datetime(2026, 8, 13, 12, 0)
        url = "https://packball.com/pt/matches/53/live"
        envelope = {
            "match_id": "mt_odds_53",
            "packball_url": url,
            "coletado_em": "2026-08-13T11:59:30",
            "ofertas": [
                {
                    "bookmaker": "Bet365",
                    "mercado_original": "Asian Corners",
                    "categoria": "escanteios",
                    "tipo_mercado": "asiatico",
                    "periodo": "FT",
                    "linha": 9.5,
                    "over": 1.91,
                    "under": 1.83,
                },
                {
                    "bookmaker": "Pinnacle",
                    "mercado_original": "Total Goals",
                    "categoria": "gols",
                    "tipo_mercado": "total",
                    "periodo": "FT",
                    "linha": 2.5,
                    "over": 1.88,
                    "under": 1.96,
                },
            ],
        }
        salvo = self.banco.salvar_odds_thestatsapi_live(
            [envelope], agora=agora
        )
        self.assertEqual(salvo["recebidos"], 2)
        self.assertEqual(salvo["inseridos"], 2)
        self.assertEqual(salvo["retencao_dias"], 14)

        alterado = json.loads(json.dumps(envelope))
        alterado["ofertas"][0]["over"] = 1.95
        repetido = self.banco.salvar_odds_thestatsapi_live(
            [alterado], agora=agora
        )
        self.assertEqual(repetido["inseridos"], 0)
        self.assertEqual(repetido["atualizados"], 2)
        odds = self.banco.carregar_odds_thestatsapi_recentes(
            packball_url=url, agora=agora
        )
        self.assertEqual(len(odds), 2)
        asiatica = next(
            item for item in odds if item["categoria"] == "escanteios"
        )
        self.assertEqual(asiatica["tipo_mercado"], "asiatico")
        self.assertEqual(asiatica["mercado_origem"], "Asian Corners")
        self.assertEqual(asiatica["odd_over"], 1.95)
        self.assertFalse(asiatica["aplicacao_sinais"])

        resumo = self.banco.resumir_cobertura_thestatsapi(
            agora=agora
        )
        self.assertEqual(resumo["jogos_com_odds"], 1)
        self.assertEqual(resumo["ofertas_odds"], 2)
        self.assertEqual(resumo["bookmakers"], 2)
        self.assertEqual(resumo["mercados"], 2)
        self.assertFalse(resumo["aplicacao_sinais"])

    def test_thestatsapi_banco_impede_fonte_ou_uso_em_sinais(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    """
                    INSERT INTO historico_thestatsapi_live (
                        match_id, packball_url, coletado_em,
                        fonte, aplicacao_sinais
                    ) VALUES ('mt_1', 'https://packball/1',
                              '2026-08-13T12:00:00', 'outra', 0)
                    """
                )

    def test_localiza_ht_red_entregue_para_challenger_segundo_tempo(self):
        registro = self.registro()
        registro.update({"placar": "0-0", "status": "22 '"})
        snapshot = self.banco.salvar_registro(registro)
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ht",
            "linha": 0.5,
            "odd": 1.83,
            "pontuacao_tecnica": 84.0,
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "status": "simulacao",
            "features": {"gol_ht_00_min20": {"forte": True}},
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue"
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais(
                    sinal_id, encerrado_em, resultado, retorno_unidades
                ) VALUES (?, '2026-08-28T12:00:00', 'red', -1)
                """,
                (sinal,),
            )

        tendencia = self.banco.obter_tendencia_ht_red_para_2t(
            registro["url"], "gol-ft-2t-pos-ht-red-odd144-v1"
        )

        self.assertTrue(tendencia["identificada"])
        self.assertTrue(tendencia["entrega_teste"])
        self.assertFalse(tendencia["ja_registrado"])
        self.assertEqual(sinal, tendencia["sinal_id"])

        self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.44,
            "pontuacao_tecnica": 80.0,
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "status": "simulacao",
            "features": {"exploracao_sombra": {
                "versao": "gol-ft-2t-pos-ht-red-odd144-v1"
            }},
        }])
        repetida = self.banco.obter_tendencia_ht_red_para_2t(
            registro["url"], "gol-ft-2t-pos-ht-red-odd144-v1"
        )
        self.assertTrue(repetida["ja_registrado"])
        with self.assertRaises(sqlite3.IntegrityError):
            with self.banco.conexao:
                self.banco.conexao.execute(
                    """
                    INSERT INTO historico_thestatsapi_live (
                        match_id, packball_url, coletado_em,
                        fonte, aplicacao_sinais
                    ) VALUES ('mt_1', 'https://packball/1',
                              '2026-08-13T12:00:00', 'thestatsapi', 1)
                    """
                )


if __name__ == "__main__":
    unittest.main()
