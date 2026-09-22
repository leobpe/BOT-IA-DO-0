import unittest
from datetime import datetime
from pathlib import Path

from avaliacao_prioridade_ligas_gols import (
    CHAVE_ANCORA,
    CHAVE_ANCORA_LEGADA,
    VERSAO,
    avaliar_prioridade_ligas_gols,
)
from banco import BancoMonitor


class AvaliacaoPrioridadeLigasGolsTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_avaliacao_prioridade_ligas.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    def registrar_ciclo(self, horario, itens):
        registros = []
        for posicao, item in enumerate(itens, start=1):
            registros.append({
                "ciclo_em": horario.isoformat(),
                "packball_url": item["url"],
                "liga": item.get("liga", item["url"]),
                "posicao": posicao,
                "processada": item.get("processada", False),
                "acionavel": True,
                "fila_operacional": "exploracao",
                "prioridade_liga_gols": item["score"],
                "janelas_temporais": [],
                "motivo": (
                    "processada" if item.get("processada")
                    else "limite_detalhes"
                ),
            })
        self.banco.salvar_auditoria_fila_packball(
            registros,
            agora=horario.replace(minute=horario.minute + 5),
        )

    def test_separa_maior_score_do_controle_e_mede_processamento(self):
        self.registrar_ciclo(datetime(2026, 9, 1, 12, 0), [
            {"url": "alta-1", "score": 70, "processada": True},
            {"url": "controle-1", "score": 40, "processada": False},
        ])
        self.registrar_ciclo(datetime(2026, 9, 1, 12, 10), [
            {"url": "alta-2", "score": 65, "processada": True},
            {"url": "controle-2", "score": 45, "processada": True},
        ])

        resultado = avaliar_prioridade_ligas_gols(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
        )

        self.assertEqual("concluida", resultado["estado_execucao"])
        self.assertEqual(
            "custodia-execucao-avaliacao-v3",
            resultado["custodia_execucao_versao"],
        )
        alta = resultado["por_grupo"]["prioridade_maxima"]
        controle = resultado["por_grupo"]["controle_pontuado"]
        self.assertEqual(2, resultado["ciclos"])
        self.assertEqual(4, resultado["unidades_independentes"])
        self.assertEqual(2, alta["processadas"])
        self.assertEqual(1.0, alta["taxa_processamento"])
        self.assertEqual(1, controle["processadas"])
        self.assertEqual(0.5, controle["taxa_processamento"])
        self.assertFalse(resultado["altera_prioridade"])
        self.assertFalse(resultado["promocao_automatica"])
        self.assertFalse(
            resultado["ancora_metodologia_v2_pre_registrada"]
        )

    def test_candidato_de_gol_e_atribuido_ao_detalhe_do_ciclo(self):
        horario = datetime(2026, 9, 1, 12, 0)
        url = "https://packball.com/pt/matches/1/match/a-b/live"
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:01:00",
            "url": url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "55 '",
            "qualidade": {"pontuacao": 90},
        })
        self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.50,
            "pontuacao_tecnica": 80,
            "regra_versao": "teste-prioridade-v1",
            "status": "aprovado",
            "features": {},
        }], criado_em=datetime(2026, 9, 1, 12, 1))
        self.registrar_ciclo(horario, [
            {"url": url, "score": 70, "processada": True},
            {"url": "controle", "score": 40, "processada": False},
        ])

        resultado = avaliar_prioridade_ligas_gols(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
        )

        alta = resultado["por_grupo"]["prioridade_maxima"]
        self.assertEqual(1, alta["candidatos_gol"])
        self.assertEqual(1, alta["detalhes_com_candidato_gol"])
        self.assertEqual(1.0, alta["rendimento_candidato_por_detalhe"])
        self.assertEqual(1, alta["detalhes_com_oportunidade_gol"])
        self.assertEqual(1.0, alta["rendimento_oportunidade_por_detalhe"])

    def test_repeticoes_do_mesmo_jogo_nao_inflam_amostra(self):
        self.registrar_ciclo(datetime(2026, 9, 1, 12, 0), [
            {"url": "alta", "score": 70, "processada": True},
            {"url": "controle-1", "score": 40, "processada": False},
        ])
        self.registrar_ciclo(datetime(2026, 9, 1, 12, 10), [
            {"url": "alta", "score": 70, "processada": True},
            {"url": "controle-2", "score": 40, "processada": False},
        ])

        resultado = avaliar_prioridade_ligas_gols(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
        )
        alta = resultado["por_grupo"]["prioridade_maxima"]

        self.assertEqual(4, resultado["decisoes_brutas"])
        self.assertEqual(3, resultado["unidades_independentes"])
        self.assertEqual(1, alta["unidades_independentes"])
        self.assertEqual(2, alta["decisoes_brutas"])
        self.assertEqual(1, alta["processadas"])

    def test_limite_preserva_ciclo_inteiro(self):
        self.registrar_ciclo(datetime(2026, 9, 1, 12, 0), [
            {"url": "alta", "score": 70, "processada": True},
            {"url": "controle-1", "score": 40, "processada": False},
            {"url": "controle-2", "score": 30, "processada": False},
        ])
        self.registrar_ciclo(datetime(2026, 9, 1, 12, 10), [
            {"url": "fora-do-limite", "score": 80, "processada": True},
        ])

        resultado = avaliar_prioridade_ligas_gols(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
            limite=1,
        )

        self.assertEqual(1, resultado["ciclos"])
        self.assertEqual(3, resultado["decisoes_brutas"])
        self.assertEqual(3, resultado["unidades_independentes"])

    def test_aprovado_com_aviso_e_uma_unica_oportunidade(self):
        horario = datetime(2026, 9, 1, 12, 0)
        url = "https://packball.com/pt/matches/1/match/a-b/live"
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:01:00",
            "url": url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "55 '",
            "qualidade": {"pontuacao": 90},
        })
        [sinal_id] = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.50,
            "pontuacao_tecnica": 80,
            "regra_versao": "teste-prioridade-v1",
            "status": "aprovado",
            "features": {},
        }], criado_em=datetime(2026, 9, 1, 12, 1))
        self.banco.registrar_entrega_alerta(
            sinal_id,
            "telegram:aguardar_odd",
            "entregue",
            instante=datetime(2026, 9, 1, 12, 2),
        )
        self.registrar_ciclo(horario, [
            {"url": url, "score": 70, "processada": True},
            {"url": "controle", "score": 40, "processada": False},
        ])

        resultado = avaliar_prioridade_ligas_gols(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
        )
        alta = resultado["por_grupo"]["prioridade_maxima"]

        self.assertEqual(1, alta["candidatos_gol_aprovados"])
        self.assertEqual(1, alta["avisos_aguardar_odd"])
        self.assertEqual(1, alta["oportunidades_gol_acionaveis"])
        self.assertEqual(1, alta["jogos_com_oportunidade_gol"])

    def test_roi_exclui_resultados_de_candidatos_nao_acionaveis(self):
        horario = datetime(2026, 9, 1, 12, 0)
        url = "https://packball.com/pt/matches/2/match/c-d/live"
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-09-01T12:01:00",
            "url": url,
            "mandante": "C",
            "visitante": "D",
            "placar": "0-0",
            "status": "60 '",
            "qualidade": {"pontuacao": 90},
        })
        ids = self.banco.salvar_candidatos(snapshot, [
            {
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.50,
                "pontuacao_tecnica": 80,
                "regra_versao": "teste-prioridade-v1",
                "status": "aprovado",
                "features": {},
            },
            {
                "mercado": "gol_ht",
                "linha": 0.5,
                "odd": 2.00,
                "pontuacao_tecnica": 60,
                "regra_versao": "teste-prioridade-v1",
                "status": "auditoria",
                "features": {},
            },
        ], criado_em=datetime(2026, 9, 1, 12, 1))
        with self.banco.conexao:
            self.banco.conexao.executemany(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    retorno_unidades, fonte_resultado
                ) VALUES (?, '2026-09-01T14:00:00', ?, ?, 'teste')
                """,
                (
                    (ids[0], "green", 0.5),
                    (ids[1], "red", -1.0),
                ),
            )
        self.registrar_ciclo(horario, [
            {"url": url, "score": 70, "processada": True},
            {"url": "controle", "score": 40, "processada": False},
        ])

        resultado = avaliar_prioridade_ligas_gols(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
        )
        alta = resultado["por_grupo"]["prioridade_maxima"]

        self.assertEqual(2, alta["candidatos_gol"])
        self.assertEqual(1, alta["oportunidades_gol_acionaveis"])
        self.assertEqual(1, alta["resultados_gol"])
        self.assertEqual(0.5, alta["retorno_unidades"])
        self.assertEqual(0.5, alta["roi_resultados"])

    def test_ancora_nao_reclassifica_decisoes_antigas(self):
        self.registrar_ciclo(datetime(2026, 9, 1, 12, 0), [
            {"url": "antiga", "score": 70, "processada": True},
        ])

        resultado = avaliar_prioridade_ligas_gols(
            self.banco,
            ancora_prospectiva="2026-09-01T13:00:00",
        )

        self.assertEqual(0, resultado["decisoes"])
        self.assertEqual(0, resultado["ciclos"])

    def test_v2_cria_ancora_nova_idempotente_e_ignora_ancora_v1(self):
        with self.banco.conexao:
            self.banco.conexao.execute(
                "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
                (CHAVE_ANCORA_LEGADA, "2026-09-01T10:00:00"),
            )

        primeira = avaliar_prioridade_ligas_gols(self.banco)
        segunda = avaliar_prioridade_ligas_gols(self.banco)
        persistida = self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (CHAVE_ANCORA,)
        ).fetchone()["valor"]

        self.assertEqual(VERSAO, primeira["versao"])
        self.assertTrue(
            primeira["ancora_metodologia_v2_pre_registrada"]
        )
        self.assertNotEqual(
            "2026-09-01T10:00:00", primeira["ancora_prospectiva_em"]
        )
        self.assertEqual(
            primeira["ancora_prospectiva_em"],
            segunda["ancora_prospectiva_em"],
        )
        self.assertEqual(primeira["ancora_prospectiva_em"], persistida)


if __name__ == "__main__":
    unittest.main()
