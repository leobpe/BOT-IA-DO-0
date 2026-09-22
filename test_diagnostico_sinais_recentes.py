import json
import sqlite3
import unittest
from datetime import datetime

from diagnostico_sinais_recentes import (
    _categoria_bloqueio,
    _inicio_janela_local,
    comparar_fluxos_consecutivos,
    comparar_fluxos_mesmo_horario,
    diagnosticar_funil,
    resumir_fluxo_sinais,
)


class DiagnosticoSinaisRecentesTest(unittest.TestCase):
    def test_janela_recente_usa_relogio_local_dos_registros(self):
        self.assertEqual(
            _inicio_janela_local(3, datetime(2026, 8, 28, 17, 15, 42)),
            "2026-08-28 14:15:42",
        )

    def test_linha_incompativel_nao_e_classificada_como_falta_de_odd(self):
        self.assertEqual(
            _categoria_bloqueio(
                "linha_exige_multiplos_escanteios,odd_ao_vivo_indisponivel"
            ),
            "criterio_linha",
        )

    def test_linha_incompativel_nao_infla_gargalo_de_cobertura(self):
        motivos = json.dumps([
            "bloqueio:linha_exige_multiplos_escanteios",
            "bloqueio:odd_ao_vivo_indisponivel",
        ])
        self.conexao.execute(
            """INSERT INTO sinais (
                   mercado,status,partida_id,criado_em,motivos_json
               ) VALUES (?,?,?,?,?)""",
            ("proximo_escanteio", "rejeitado", 10,
             "2026-08-09T10:10:00", motivos),
        )

        resultado = diagnosticar_funil(
            self.conexao, "2026-08-09T10:00:00"
        )
        itens = resultado["gargalos_por_mercado"]["proximo_escanteio"]

        self.assertEqual(
            [item["motivo"] for item in itens],
            ["linha_exige_multiplos_escanteios"],
        )
        self.assertEqual(itens[0]["categoria"], "criterio_linha")

    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mercado TEXT, status TEXT, partida_id INTEGER,
                criado_em TEXT, motivos_json TEXT, regra_versao TEXT,
                pontuacao_tecnica REAL, probabilidade_calibrada REAL
            );
            CREATE TABLE entregas_alertas (
                sinal_id INTEGER, canal TEXT, tentado_em TEXT,
                status TEXT, erro TEXT
            );
            CREATE TABLE snapshots (
                partida_id INTEGER, coletado_em TEXT,
                qualidade_dados REAL, qualidade_json TEXT
            );
            """
        )

    def tearDown(self):
        self.conexao.close()

    def test_separa_bloqueios_reais_e_conta_partidas_unicas(self):
        motivos = json.dumps([
            "minuto_na_faixa_da_regra",
            "bloqueio:odd_ao_vivo_indisponivel",
        ])
        self.conexao.executemany(
            """INSERT INTO sinais (
                   mercado,status,partida_id,criado_em,motivos_json
               ) VALUES ('proximo_gol','rejeitado',?,?,?)""",
            [
                (10, "2026-08-09T10:01:00", motivos),
                (10, "2026-08-09T10:02:00", motivos),
                (11, "2026-08-09T10:03:00", motivos),
            ],
        )

        resultado = diagnosticar_funil(
            self.conexao, "2026-08-09T10:00:00"
        )
        item = resultado["gargalos_por_mercado"]["proximo_gol"][0]

        self.assertEqual(item["motivo"], "odd_ao_vivo_indisponivel")
        self.assertEqual(item["categoria"], "cobertura_odds")
        self.assertEqual(item["observacoes"], 2)
        self.assertEqual(item["partidas"], 2)
        self.assertEqual(len(resultado["candidatos"]), 1)

    def test_resume_decisao_de_entrega_por_mercado(self):
        self.conexao.execute(
            """INSERT INTO sinais (
                   mercado,status,partida_id,criado_em,motivos_json,
                   regra_versao
               ) VALUES ('proximo_gol','aprovado',10,?, '[]', ?)""",
            ("2026-08-09T10:01:00", "regra-prospectiva"),
        )
        sinal_id = self.conexao.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]
        self.conexao.execute(
            """INSERT INTO entregas_alertas (
                   sinal_id,canal,tentado_em,status,erro
               ) VALUES (?, 'teste', ?, 'filtrado', ?)""",
            (
                sinal_id,
                "2026-08-09T10:02:00",
                "pontuacao_teste_insuficiente",
            ),
        )

        resultado = diagnosticar_funil(
            self.conexao, "2026-08-09T10:00:00"
        )

        self.assertEqual(
            resultado["decisoes_entrega"],
            [{
                "mercado": "proximo_gol",
                "regra_versao": "regra-prospectiva",
                "status_sinal": "aprovado",
                "canal": "teste",
                "status_entrega": "filtrado",
                "motivo": "pontuacao_teste_insuficiente",
                "sinais": 1,
                "partidas": 1,
            }],
        )

    def test_classifica_rejeicoes_com_gargalo_sem_inflar_reavaliacoes(self):
        motivos = json.dumps([
            "bloqueio:odd_ao_vivo_indisponivel",
            "bloqueio:atividade_recente_insuficiente_gols",
        ])
        self.conexao.executemany(
            """INSERT INTO sinais (
                   mercado,status,partida_id,criado_em,motivos_json
               ) VALUES ('gol_ft','rejeitado',?,?,?)""",
            [
                (10, "2026-08-09T10:01:00", motivos),
                (10, "2026-08-09T10:02:00", motivos),
                (11, "2026-08-09T10:03:00", motivos),
            ],
        )
        bruto = diagnosticar_funil(
            self.conexao, "2026-08-09T10:00:00"
        )
        resumo = resumir_fluxo_sinais(bruto, {
            "snapshots_ao_vivo": 20,
            "cobertura_candidatos": 1.0,
            "cobertura_odds_estruturadas": 0.2,
        })

        self.assertEqual(resumo["estado"], "cobertura_odds_restritiva")
        self.assertEqual(resumo["observacoes"], 3)
        self.assertEqual(
            resumo["categorias_gargalo"]["cobertura_odds"]["partidas"],
            2,
        )
        self.assertFalse(resumo["altera_sinais"])
        self.assertFalse(resumo["envia_telegram"])

    def test_gargalo_operacional_usa_melhor_tentativa_dentro_da_janela(self):
        self.conexao.executemany(
            """INSERT INTO sinais (
                   mercado,status,partida_id,criado_em,motivos_json,
                   pontuacao_tecnica
               ) VALUES ('gol_ft','rejeitado',10,?,?,?)""",
            [
                (
                    "2026-08-09T10:01:00",
                    json.dumps([
                        "bloqueio:historico_5min_insuficiente",
                        "bloqueio:atividade_recente_insuficiente_gols",
                    ]),
                    40,
                ),
                (
                    "2026-08-09T10:02:00",
                    json.dumps(["bloqueio:odd_ao_vivo_indisponivel"]),
                    75,
                ),
                (
                    "2026-08-09T10:03:00",
                    json.dumps([
                        "bloqueio:fora_da_janela_gol_ft_max_82",
                        "bloqueio:historico_5min_insuficiente",
                    ]),
                    90,
                ),
            ],
        )

        resultado = diagnosticar_funil(
            self.conexao, "2026-08-09T10:00:00"
        )
        itens = resultado[
            "gargalos_operacionais_por_mercado"
        ]["gol_ft"]

        self.assertEqual(
            [item["motivo"] for item in itens],
            ["odd_ao_vivo_indisponivel"],
        )

    def test_gargalo_operacional_exclui_partida_que_gerou_sinal(self):
        self.conexao.executemany(
            """INSERT INTO sinais (
                   mercado,status,partida_id,criado_em,motivos_json,
                   pontuacao_tecnica
               ) VALUES ('gol_ft',?,?,?,?,?)""",
            [
                (
                    "rejeitado", 10, "2026-08-09T10:01:00",
                    json.dumps(["bloqueio:qualidade_insuficiente"]), 60,
                ),
                (
                    "aprovado", 10, "2026-08-09T10:02:00", "[]", 80,
                ),
            ],
        )

        resultado = diagnosticar_funil(
            self.conexao, "2026-08-09T10:00:00"
        )

        self.assertNotIn(
            "gol_ft", resultado["gargalos_operacionais_por_mercado"]
        )

    def test_classifica_aprovacao_sem_entrega(self):
        self.conexao.execute(
            """INSERT INTO sinais (
                   mercado,status,partida_id,criado_em,motivos_json,
                   regra_versao,probabilidade_calibrada
               ) VALUES ('gol_ft','aprovado',10,?, '[]', ?, 0.7)""",
            ("2026-08-09T10:01:00", "regra-ft"),
        )
        resumo = resumir_fluxo_sinais(
            diagnosticar_funil(
                self.conexao, "2026-08-09T10:00:00"
            ),
            {"snapshots_ao_vivo": 1},
        )

        self.assertEqual(resumo["estado"], "aprovacoes_sem_entrega")
        self.assertEqual(resumo["sem_registro_entrega"], 1)

    def test_aprovado_sem_calibracao_nao_parece_falha_do_telegram(self):
        self.conexao.execute(
            """INSERT INTO sinais (
                   mercado,status,partida_id,criado_em,motivos_json,
                   regra_versao,probabilidade_calibrada
               ) VALUES ('gol_ft','aprovado',10,?, '[]', ?, NULL)""",
            ("2026-08-09T10:01:00", "regra-ft"),
        )

        resultado = diagnosticar_funil(
            self.conexao, "2026-08-09T10:00:00"
        )
        resumo = resumir_fluxo_sinais(resultado, {"snapshots_ao_vivo": 1})

        self.assertEqual(resumo["estado"], "aprovacoes_sem_calibracao")
        self.assertEqual(resumo["sem_registro_entrega"], 0)
        self.assertEqual(resumo["nao_elegiveis_oficiais"], 1)
        self.assertEqual(
            resultado["decisoes_entrega"][0]["motivo"],
            "probabilidade_calibrada_ausente",
        )

    def test_comparacao_identifica_menos_partidas_com_mesma_conversao(self):
        for indice in range(10):
            self.conexao.execute(
                """INSERT INTO sinais (
                       mercado,status,partida_id,criado_em,motivos_json
                   ) VALUES ('gol_ft','aprovado',?,?, '[]')""",
                (100 + indice, "2026-08-08T12:00:00"),
            )
        for indice in range(4):
            self.conexao.execute(
                """INSERT INTO sinais (
                       mercado,status,partida_id,criado_em,motivos_json
                   ) VALUES ('gol_ft','aprovado',?,?, '[]')""",
                (200 + indice, "2026-08-09T12:00:00"),
            )

        comparacao = comparar_fluxos_consecutivos(
            self.conexao,
            horas=24,
            agora=datetime(2026, 8, 10, 10),
        )

        self.assertEqual(comparacao["causa_principal"], "menos_partidas_avaliadas")
        self.assertEqual(comparacao["anterior"]["partidas"], 10)
        self.assertEqual(comparacao["atual"]["partidas"], 4)
        self.assertEqual(comparacao["razao_conversao"], 1.0)
        self.assertFalse(comparacao["altera_sinais"])

    def test_comparacao_mesmo_horario_nao_mistura_periodo_intermediario(self):
        for indice in range(8):
            self.conexao.execute(
                """INSERT INTO sinais (
                       mercado,status,partida_id,criado_em,motivos_json
                   ) VALUES ('gol_ft','aprovado',?,?, '[]')""",
                (1000 + indice, "2026-08-09T19:00:00"),
            )
        # Esse volume ocorreu pela manha e nao pertence a nenhuma das duas
        # janelas noturnas alinhadas.
        for indice in range(20):
            self.conexao.execute(
                """INSERT INTO sinais (
                       mercado,status,partida_id,criado_em,motivos_json
                   ) VALUES ('gol_ft','aprovado',?,?, '[]')""",
                (1100 + indice, "2026-08-10T09:00:00"),
            )
        for indice in range(3):
            self.conexao.execute(
                """INSERT INTO sinais (
                       mercado,status,partida_id,criado_em,motivos_json
                   ) VALUES ('gol_ft','aprovado',?,?, '[]')""",
                (1200 + indice, "2026-08-10T19:00:00"),
            )

        comparacao = comparar_fluxos_mesmo_horario(
            self.conexao,
            horas=6,
            agora=datetime(2026, 8, 10, 23),
        )

        self.assertEqual(
            comparacao["tipo_comparacao"], "mesmo_horario_anterior"
        )
        self.assertEqual(comparacao["deslocamento_horas"], 24.0)
        self.assertEqual(comparacao["anterior"]["partidas"], 8)
        self.assertEqual(comparacao["atual"]["partidas"], 3)
        self.assertEqual(
            comparacao["causa_principal"], "menos_partidas_avaliadas"
        )
        self.assertIn(
            "menos_partidas_avaliadas",
            comparacao["causas_contribuintes"],
        )
        self.assertIsNone(
            comparacao["categoria_gargalo_com_maior_alta"]
        )

    def test_comparacao_identifica_queda_de_cobertura_de_odds(self):
        for indice in range(10):
            status = "aprovado" if indice < 5 else "rejeitado"
            motivos = (
                [] if status == "aprovado" else
                ["bloqueio:atividade_recente_insuficiente_gols"]
            )
            self.conexao.execute(
                """INSERT INTO sinais (
                       mercado,status,partida_id,criado_em,motivos_json,
                       pontuacao_tecnica
                   ) VALUES ('gol_ft',?,?,?,?,70)""",
                (
                    status, 300 + indice, "2026-08-08T12:00:00",
                    json.dumps(motivos),
                ),
            )
        for indice in range(10):
            status = "aprovado" if indice == 0 else "rejeitado"
            motivos = (
                [] if status == "aprovado" else
                ["bloqueio:odd_ao_vivo_indisponivel"]
            )
            self.conexao.execute(
                """INSERT INTO sinais (
                       mercado,status,partida_id,criado_em,motivos_json,
                       pontuacao_tecnica
                   ) VALUES ('gol_ft',?,?,?,?,70)""",
                (
                    status, 400 + indice, "2026-08-09T12:00:00",
                    json.dumps(motivos),
                ),
            )

        comparacao = comparar_fluxos_consecutivos(
            self.conexao,
            horas=24,
            agora=datetime(2026, 8, 10, 10),
        )

        self.assertEqual(comparacao["causa_principal"], "queda_cobertura_odds")
        self.assertEqual(comparacao["anterior"]["pares_com_oportunidade"], 5)
        self.assertEqual(comparacao["atual"]["pares_com_oportunidade"], 1)
        self.assertEqual(
            comparacao["categoria_gargalo_com_maior_alta"],
            "cobertura_odds",
        )

    def test_entregas_estaveis_nao_sao_chamadas_de_reducao(self):
        for dia, partida in ((8, 501), (9, 502)):
            cursor = self.conexao.execute(
                """INSERT INTO sinais (
                       mercado,status,partida_id,criado_em,motivos_json
                   ) VALUES ('gol_ft','aprovado',?,?, '[]')""",
                (partida, f"2026-08-{dia:02d}T12:00:00"),
            )
            self.conexao.execute(
                """INSERT INTO entregas_alertas (
                       sinal_id,canal,tentado_em,status
                   ) VALUES (?, 'teste', ?, 'entregue')""",
                (cursor.lastrowid, f"2026-08-{dia:02d}T12:00:05"),
            )

        comparacao = comparar_fluxos_consecutivos(
            self.conexao,
            horas=24,
            agora=datetime(2026, 8, 10, 10),
        )

        self.assertEqual(comparacao["metrica_volume"], "entregas")
        self.assertEqual(comparacao["delta_entregas"], 0)
        self.assertEqual(
            comparacao["causa_principal"], "sem_reducao_comprovada"
        )

    def test_comparacao_detalha_campos_ausentes_da_qualidade(self):
        self.conexao.executemany(
            "INSERT INTO snapshots VALUES (?, ?, ?, ?)",
            [
                (
                    1, "2026-08-09T12:00:00", 58,
                    json.dumps({
                        "campos_ausentes": [
                            "Chutes no gol", "Índice de pressão"
                        ],
                        "alertas": ["campos_essenciais_ausentes"],
                    }),
                ),
                (
                    1, "2026-08-09T12:03:00", 58,
                    json.dumps({
                        "campos_ausentes": [
                            "Chutes no gol", "Índice de pressão"
                        ],
                        "alertas": ["campos_essenciais_ausentes"],
                    }),
                ),
                (
                    2, "2026-08-09T12:04:00", 68,
                    json.dumps({
                        "campos_ausentes": ["Chutes no gol"],
                        "alertas": [
                            "campos_essenciais_ausentes",
                            "sem_confirmacao_api",
                        ],
                    }),
                ),
                (3, "2026-08-09T12:05:00", 90, "{}"),
            ],
        )

        comparacao = comparar_fluxos_consecutivos(
            self.conexao,
            horas=24,
            agora=datetime(2026, 8, 10, 10),
        )
        lacunas = comparacao["atual"]["lacunas_qualidade"]

        self.assertTrue(lacunas["disponivel"])
        self.assertEqual(lacunas["snapshots_abaixo_70"], 3)
        self.assertEqual(lacunas["partidas_distintas"], 2)
        self.assertEqual(
            lacunas["campos_ausentes"]["Chutes no gol"],
            {"observacoes": 3, "partidas": 2},
        )
        self.assertEqual(
            lacunas["campos_ausentes"]["Índice de pressão"]["partidas"],
            1,
        )
        self.assertEqual(
            lacunas["coleta_packball"]["diagnostico_ausente"],
            {"observacoes": 3, "partidas": 2},
        )


if __name__ == "__main__":
    unittest.main()
