import unittest
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from backtest import AvaliadorBacktest, reabrir_resultados_provisorios
from banco import BancoMonitor
from finalizador_resultados import (
    FinalizadorPendenciasSemDado,
    FinalizadorResultadosAPI,
    FinalizadorResultadosPackBall,
    _escanteios_api,
    _placar_intervalo_por_timeline_packball,
    _placar_intervalo_packball,
)


class APIFalsa:
    def partidas_por_ids(self, fixture_ids):
        caminho = Path(__file__).parent / "fixtures" / "api_fixture_final.json"
        item = json.loads(caminho.read_text(encoding="utf-8"))
        item["fixture"]["id"] = fixture_ids[0]
        return [item]

    def estatisticas(self, fixture_id):
        return []


class APIFalsaSemEstatisticas(APIFalsa):
    def __init__(self, estatisticas=None, status="FT"):
        self.estatisticas_finais = estatisticas
        self.status = status
        self.consultas_estatisticas = []

    def partidas_por_ids(self, fixture_ids):
        caminho = Path(__file__).parent / "fixtures" / "api_fixture_final.json"
        item = json.loads(caminho.read_text(encoding="utf-8"))
        item["fixture"]["id"] = fixture_ids[0]
        item["fixture"]["status"]["short"] = self.status
        item.pop("statistics", None)
        return [item]

    def estatisticas(self, fixture_id):
        self.consultas_estatisticas.append(fixture_id)
        return self.estatisticas_finais


class APIFalsaComIntervalo(APIFalsa):
    def partidas_por_ids(self, fixture_ids):
        itens = super().partidas_por_ids(fixture_ids)
        itens[0]["score"] = {"halftime": {"home": 1, "away": 0}}
        return itens


class APIFalsaComIntervaloEmAndamento(APIFalsaComIntervalo):
    def partidas_por_ids(self, fixture_ids):
        itens = super().partidas_por_ids(fixture_ids)
        itens[0]["fixture"]["status"]["short"] = "2H"
        return itens


class APIFalsaComPenaltis(APIFalsa):
    def partidas_por_ids(self, fixture_ids):
        itens = super().partidas_por_ids(fixture_ids)
        item = itens[0]
        item["fixture"]["status"]["short"] = "PEN"
        item["goals"] = {"home": 1, "away": 1}
        item["score"] = {"fulltime": {"home": 0, "away": 0}}
        item["events"] = [
            {
                "time": {"elapsed": 99},
                "team": {"id": 1},
                "type": "Goal",
                "detail": "Normal Goal",
            },
            {
                "time": {"elapsed": 110},
                "team": {"id": 2},
                "type": "Goal",
                "detail": "Normal Goal",
            },
        ]
        return itens


class APIFalsaRespostaInvalida(APIFalsa):
    def partidas_por_ids(self, fixture_ids):
        return [None, {}, {"fixture": {"id": 999999}}]


class APIFalsaCaptura:
    def __init__(self):
        self.consultas = []

    def partidas_por_ids(self, fixture_ids):
        self.consultas.append(list(fixture_ids))
        return []


class APIFalsaInvertida(APIFalsa):
    def partidas_por_ids(self, fixture_ids):
        itens = super().partidas_por_ids(fixture_ids)
        item = itens[0]
        item["teams"] = {
            "home": {"id": 2, "name": "B"},
            "away": {"id": 1, "name": "A"},
        }
        item["goals"] = {"home": 0, "away": 2}
        return itens


class APIFalsaTimesErrados(APIFalsa):
    def partidas_por_ids(self, fixture_ids):
        itens = super().partidas_por_ids(fixture_ids)
        itens[0]["teams"] = {
            "home": {"id": 91, "name": "Clube Desconhecido"},
            "away": {"id": 92, "name": "Outro Adversario"},
        }
        return itens


class PackBallFalso:
    def __init__(
        self, finalizado=True, com_estatisticas=True,
        placar="2-0", status_minuto="94 '", eventos_gols=None,
    ):
        self.finalizado = finalizado
        self.com_estatisticas = com_estatisticas
        self.placar = placar
        self.status_minuto = status_minuto
        self.eventos_gols = eventos_gols or []
        self.urls = []

    def coletar_estado_partida(self, pagina, jogo):
        self.urls.append(jogo["url"])
        return {
            "finalizado": self.finalizado,
            "placar": self.placar,
            "status_minuto": self.status_minuto,
            "estatisticas": (
                {"Escanteios": "6-3"} if self.com_estatisticas else {}
            ),
            "eventos_gols": self.eventos_gols,
        }


class FinalizadorResultadosTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_finalizador.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)
        snapshot = self.banco.salvar_registro(
            {
                "coletado_em": datetime(2026, 7, 20, 12, 0),
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "60 '",
                "estatisticas": {"Escanteios": "2-1"},
                "confirmacao_api": {"fixture_id": 123},
            }
        )
        self.banco.salvar_candidatos(
            snapshot,
            [
                {
                    "mercado": "gol_ft",
                    "linha": 1.5,
                    "odd": 1.9,
                    "pontuacao_tecnica": 80,
                    "regra_versao": "sinais-v1",
                    "status": "aprovado",
                },
                {
                    "mercado": "proximo_escanteio",
                    "linha": 8.5,
                    "odd": 1.8,
                    "pontuacao_tecnica": 80,
                    "regra_versao": "sinais-v1",
                    "status": "aprovado",
                },
            ],
        )

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def test_finaliza_sinais_pendentes_em_lote(self):
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                UPDATE sinais SET status='simulacao'
                WHERE mercado='proximo_escanteio'
                """
            )
        finalizador = FinalizadorResultadosAPI(
            self.banco, APIFalsa(), AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar()
        self.assertEqual(resumo["encerradas"], 1)
        self.assertEqual(resumo["resolvidos"], 2)
        resultados = self.banco.conexao.execute(
            "SELECT resultado FROM resultados_sinais ORDER BY sinal_id"
        ).fetchall()
        self.assertEqual([item[0] for item in resultados], ["green", "green"])
        proveniencia = self.banco.conexao.execute(
            """
            SELECT fonte_resultado, snapshot_id_liquidacao
            FROM resultados_sinais ORDER BY sinal_id
            """
        ).fetchall()
        self.assertTrue(all(item[0] == "api_football" for item in proveniencia))
        self.assertTrue(all(item[1] is not None for item in proveniencia))
        self.assertEqual(AvaliadorBacktest(self.banco).metricas()["amostra"], 1)
        consulta = self.banco.conexao.execute(
            "SELECT fonte, estado FROM consultas_finalizacao"
        ).fetchone()
        self.assertEqual(tuple(consulta), ("api_football", "finalizado"))

    def test_resposta_api_invalida_nao_quebra_e_aplica_cooldown(self):
        finalizador = FinalizadorResultadosAPI(
            self.banco,
            APIFalsaRespostaInvalida(),
            AvaliadorBacktest(self.banco),
        )

        primeiro = finalizador.executar()
        segundo = finalizador.executar()

        self.assertEqual(primeiro["consultadas"], 1)
        self.assertEqual(primeiro["respostas_ausentes"], 1)
        self.assertEqual(primeiro["respostas_invalidas"], 3)
        self.assertEqual(segundo["consultadas"], 0)
        consulta = self.banco.conexao.execute(
            """
            SELECT estado, erro FROM consultas_finalizacao
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        self.assertEqual(consulta["estado"], "resposta_ausente")
        self.assertIn("fixture 123", consulta["erro"])
        resultados = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM resultados_sinais"
        ).fetchone()[0]
        self.assertEqual(resultados, 0)

    def test_escanteio_nulo_na_api_nao_e_convertido_em_zero(self):
        item = {
            "teams": {"home": {"id": 1}, "away": {"id": 2}},
            "statistics": [
                {
                    "team": {"id": 1},
                    "statistics": [
                        {"type": "Corner Kicks", "value": None}
                    ],
                },
                {
                    "team": {"id": 2},
                    "statistics": [
                        {"type": "Corner Kicks", "value": 4}
                    ],
                },
            ],
        }
        self.assertIsNone(_escanteios_api(item))

    def test_busca_escanteios_no_endpoint_de_estatisticas(self):
        blocos = json.loads(
            (Path(__file__).parent / "fixtures" / "api_fixture_final.json")
            .read_text(encoding="utf-8")
        )["statistics"]
        api = APIFalsaSemEstatisticas(blocos)
        finalizador = FinalizadorResultadosAPI(
            self.banco, api, AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar()
        self.assertEqual(resumo["resolvidos"], 2)
        self.assertEqual(api.consultas_estatisticas, [123])

    def test_finalizacao_respeita_orientacao_invertida_da_api(self):
        finalizador = FinalizadorResultadosAPI(
            self.banco, APIFalsaInvertida(), AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar()
        self.assertEqual(resumo["resolvidos"], 2)
        snapshot = self.banco.conexao.execute(
            """
            SELECT placar, estatisticas_json, confirmacao_api_json
            FROM snapshots ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        self.assertEqual(snapshot["placar"], "2-0")
        self.assertEqual(
            json.loads(snapshot["estatisticas_json"])["Escanteios"], "6-3"
        )
        confirmacao = json.loads(snapshot["confirmacao_api_json"])
        self.assertEqual(confirmacao["orientacao"], "invertida")
        orientacao = self.banco.conexao.execute(
            "SELECT api_orientacao FROM partidas LIMIT 1"
        ).fetchone()[0]
        self.assertEqual(orientacao, "invertida")

    def test_fixture_persistida_com_times_errados_nao_contamina_backtest(self):
        finalizador = FinalizadorResultadosAPI(
            self.banco, APIFalsaTimesErrados(),
            AvaliadorBacktest(self.banco),
        )

        resumo = finalizador.executar()

        self.assertEqual(resumo["encerradas"], 0)
        self.assertEqual(resumo["resolvidos"], 0)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM resultados_sinais"
            ).fetchone()[0],
            0,
        )
        consulta = self.banco.conexao.execute(
            """
            SELECT estado, erro FROM consultas_finalizacao
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        self.assertEqual(consulta["estado"], "erro_associacao")
        self.assertIn("não confirmada", consulta["erro"])

    def test_nao_transforma_escanteio_ausente_em_void(self):
        api = APIFalsaSemEstatisticas(None)
        finalizador = FinalizadorResultadosAPI(
            self.banco, api, AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar()
        self.assertEqual(resumo["resolvidos"], 1)
        resultados = self.banco.conexao.execute(
            """
            SELECT s.mercado, r.resultado
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            ORDER BY s.id
            """
        ).fetchall()
        self.assertEqual(tuple(resultados[0]), ("gol_ft", "green"))
        self.assertEqual(tuple(resultados[1]), ("proximo_escanteio", None))

    def test_status_cancelado_anula_todos_os_mercados(self):
        api = APIFalsaSemEstatisticas(None, status="CANC")
        finalizador = FinalizadorResultadosAPI(
            self.banco, api, AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar()
        self.assertEqual(resumo["resolvidos"], 2)
        resultados = self.banco.conexao.execute(
            "SELECT resultado FROM resultados_sinais ORDER BY sinal_id"
        ).fetchall()
        self.assertEqual([item[0] for item in resultados], ["void", "void"])
        self.assertEqual(api.consultas_estatisticas, [])

    def test_gol_ht_usa_placar_do_intervalo_e_nao_o_final(self):
        snapshot = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.banco.salvar_candidatos(
            snapshot,
            [
                {
                    "mercado": "gol_ht",
                    "linha": 1.5,
                    "odd": 1.9,
                    "pontuacao_tecnica": 80,
                    "regra_versao": "sinais-v1",
                    "status": "aprovado",
                }
            ],
        )
        finalizador = FinalizadorResultadosAPI(
            self.banco, APIFalsaComIntervalo(), AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar()
        self.assertEqual(resumo["resolvidos"], 3)
        resultado_ht = self.banco.conexao.execute(
            """
            SELECT r.resultado
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            WHERE s.mercado='gol_ht'
            """
        ).fetchone()[0]
        self.assertEqual(resultado_ht, "red")

    def test_gol_ht_liquida_no_segundo_tempo_sem_esperar_apito_final(self):
        snapshot = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "gol_ht",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }],
        )
        finalizador = FinalizadorResultadosAPI(
            self.banco,
            APIFalsaComIntervaloEmAndamento(),
            AvaliadorBacktest(self.banco),
        )

        resumo = finalizador.executar()

        self.assertEqual(resumo["encerradas"], 0)
        self.assertEqual(resumo["resolvidos"], 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT r.resultado, r.fonte_resultado
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            WHERE s.mercado='gol_ht'
            """
        ).fetchone()
        self.assertEqual(tuple(resultado), ("green", "api_football"))

    def test_gol_ht_recupera_intervalo_api_ja_persistido(self):
        snapshot = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "gol_ht",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v1",
                "status": "simulacao",
            }],
        )
        self.banco.salvar_registro(
            {
                "coletado_em": datetime(2026, 7, 20, 13, 0),
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "1-0",
                "status": "60 '",
                "estatisticas": {},
                "confirmacao_api": {
                    "fixture_id": 123,
                    "status": {"short": "2H"},
                    "placar": [1, 0],
                    "placar_intervalo": [1, 0],
                    "times": {
                        "home": {"id": 1, "name": "A"},
                        "away": {"id": 2, "name": "B"},
                    },
                    "orientacao": "direta",
                },
                "qualidade": {
                    "pontuacao": 100,
                    "fontes": ["api_football"],
                },
            }
        )
        finalizador = FinalizadorResultadosAPI(
            self.banco,
            APIFalsaRespostaInvalida(),
            AvaliadorBacktest(self.banco),
        )

        resumo = finalizador.executar()

        self.assertEqual(resumo["intervalos_persistidos_recuperados"], 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT r.resultado, r.fonte_resultado
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            WHERE s.mercado='gol_ht'
            """
        ).fetchone()
        self.assertEqual(tuple(resultado), ("green", "api_football"))

    def test_extrai_placar_ht_do_resumo_final_packball(self):
        self.assertEqual(
            _placar_intervalo_packball("HT 0-2 3-2"),
            "0-2",
        )
        self.assertIsNone(_placar_intervalo_packball("Finalizado 3-2"))

    def test_reconstroi_placar_ht_somente_com_timeline_completa(self):
        eventos = [
            {"minuto": "9", "minuto_ordenacao": 9, "lado": "visitante"},
            {"minuto": "15", "minuto_ordenacao": 15, "lado": "casa"},
            {"minuto": "45+2", "minuto_ordenacao": 47, "lado": "casa"},
            {"minuto": "66", "minuto_ordenacao": 66, "lado": "casa"},
        ]
        self.assertEqual(
            _placar_intervalo_por_timeline_packball(eventos, "3-1"),
            "2-1",
        )
        self.assertIsNone(
            _placar_intervalo_por_timeline_packball(eventos[:-1], "3-1")
        )

    def test_recupera_sem_dado_gol_ht_por_timeline_auditada(self):
        inicial = self.banco.salvar_registro({
            "coletado_em": datetime(2026, 7, 20, 14, 20),
            "url": "https://packball.com/match/ht-timeline/live",
            "mandante": "C",
            "visitante": "D",
            "placar": "1-1",
            "status": "20 '",
            "estatisticas": {},
        })
        sinal = self.banco.salvar_candidatos(inicial, [{
            "mercado": "gol_ht",
            "linha": 2.5,
            "odd": 1.5,
            "pontuacao_tecnica": 80,
            "regra_versao": "sinais-v1",
            "status": "simulacao",
        }])[0]
        final = self.banco.salvar_registro({
            "coletado_em": datetime(2026, 7, 20, 16, 0),
            "url": "https://packball.com/match/ht-timeline/live",
            "mandante": "C",
            "visitante": "D",
            "placar": "3-1",
            "status": "Finalizado",
            "estatisticas": {
                "_eventos_gols_packball": [
                    {"minuto": "9", "minuto_ordenacao": 9,
                     "lado": "visitante"},
                    {"minuto": "15", "minuto_ordenacao": 15,
                     "lado": "casa"},
                    {"minuto": "36", "minuto_ordenacao": 36,
                     "lado": "casa"},
                    {"minuto": "66", "minuto_ordenacao": 66,
                     "lado": "casa"},
                ]
            },
            "qualidade": {"pontuacao": 90, "fontes": ["packball"]},
        })
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, 'sem_dado', NULL, ?, NULL, 'sem_dado')
                """,
                (sinal, datetime(2026, 7, 21, 16, 0).isoformat(), "sem fonte"),
            )

        resumo = FinalizadorPendenciasSemDado(self.banco).executar(
            datetime(2026, 7, 22, 16, 0)
        )

        self.assertEqual(resumo["recuperados_sem_dado"], 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT resultado, retorno_unidades, snapshot_id_liquidacao,
                   fonte_resultado
            FROM resultados_sinais WHERE sinal_id=?
            """,
            (sinal,),
        ).fetchone()
        self.assertEqual(resultado["resultado"], "green")
        self.assertEqual(resultado["retorno_unidades"], 0.5)
        self.assertEqual(resultado["snapshot_id_liquidacao"], final)
        self.assertEqual(resultado["fonte_resultado"], "packball")
        revisao = self.banco.conexao.execute(
            """
            SELECT resultado_anterior, fonte_resultado_anterior
            FROM revisoes_resultados WHERE sinal_id=?
            """,
            (sinal,),
        ).fetchone()
        self.assertEqual(tuple(revisao), ("sem_dado", "sem_dado"))

    def test_recupera_sem_dado_escanteios_apos_green_confirmado(self):
        inicial = self.banco.salvar_registro({
            "coletado_em": datetime(2026, 7, 20, 14, 0),
            "url": "https://packball.com/match/corners/live",
            "mandante": "E",
            "visitante": "F",
            "placar": "1-0",
            "status": "64 '",
            "estatisticas": {"Escanteios": "4-0"},
        })
        sinal = self.banco.salvar_candidatos(inicial, [{
            "mercado": "escanteios_ft_asiatico",
            "linha": 6.5,
            "odd": 1.825,
            "pontuacao_tecnica": 90,
            "regra_versao": "sinais-v1",
            "status": "simulacao",
        }])[0]
        atingiu = self.banco.salvar_registro({
            "coletado_em": datetime(2026, 7, 20, 14, 9),
            "url": "https://packball.com/match/corners/live",
            "mandante": "E",
            "visitante": "F",
            "placar": "1-0",
            "status": "73 '",
            "estatisticas": {"Escanteios": "6-1"},
            "qualidade": {
                "pontuacao": 100,
                "fontes": ["packball", "api_football"],
                "apto_para_liquidacao": True,
            },
        })
        fechamento = self.banco.salvar_registro({
            "coletado_em": datetime(2026, 7, 20, 14, 20),
            "url": "https://packball.com/match/corners/live",
            "mandante": "E",
            "visitante": "F",
            "placar": "1-1",
            "status": "PEN",
            "estatisticas": {"Escanteios": "6-2"},
            "qualidade": {"pontuacao": 90, "fontes": ["packball"]},
        })
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, 'sem_dado', NULL, ?, NULL, 'sem_dado')
                """,
                (sinal, datetime(2026, 7, 21, 14, 0).isoformat(), "sem fonte"),
            )

        resumo = FinalizadorPendenciasSemDado(self.banco).executar(
            datetime(2026, 7, 22, 14, 0)
        )

        self.assertEqual(resumo["recuperados_sem_dado"], 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT resultado, retorno_unidades, snapshot_id_liquidacao
            FROM resultados_sinais WHERE sinal_id=?
            """,
            (sinal,),
        ).fetchone()
        self.assertEqual(resultado["resultado"], "green")
        self.assertEqual(resultado["retorno_unidades"], 0.825)
        self.assertNotEqual(resultado["snapshot_id_liquidacao"], atingiu)
        self.assertEqual(resultado["snapshot_id_liquidacao"], fechamento)
        self.assertEqual(
            reabrir_resultados_provisorios(self.banco)["quantidade"], 0
        )
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT resultado FROM resultados_sinais WHERE sinal_id=?",
                (sinal,),
            ).fetchone()[0],
            "green",
        )

    def test_recupera_sem_dado_escanteios_total_estavel_desde_fim_regulamentar(self):
        entrada = self.banco.salvar_registro({
            "coletado_em": datetime(2026, 7, 20, 14, 0),
            "url": "https://packball.com/match/corners/stable",
            "mandante": "E",
            "visitante": "F",
            "placar": "0-0",
            "status": "84 '",
            "estatisticas": {"Escanteios": "4-8"},
            "qualidade": {
                "pontuacao": 100,
                "fontes": ["packball", "api_football"],
                "apto_para_liquidacao": True,
            },
        })
        sinal = self.banco.salvar_candidatos(entrada, [{
            "mercado": "escanteios_ft_asiatico",
            "linha": 12.0,
            "odd": 2.25,
            "pontuacao_tecnica": 90,
            "regra_versao": "sinais-v1",
            "status": "simulacao",
        }])[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, 'sem_dado', NULL, ?, NULL, 'sem_dado')
                """,
                (sinal, datetime(2026, 7, 21, 14, 0).isoformat(), "sem fonte"),
            )
        for minuto in (20, 31, 42):
            self.banco.salvar_registro({
                "coletado_em": datetime(2026, 7, 20, 14, minuto),
                "url": "https://packball.com/match/corners/stable",
                "mandante": "E",
                "visitante": "F",
                "placar": "0-0",
                "status": "PEN",
                "estatisticas": {"Escanteios": "4-8"},
                "qualidade": {
                    "pontuacao": 80,
                    "fontes": ["packball"],
                    "versao": "recuperacao-packball-v1",
                },
            })
        for minuto in (22, 44):
            self.banco.salvar_registro({
                "coletado_em": datetime(2026, 7, 20, 14, minuto),
                "url": "https://packball.com/match/corners/stable",
                "mandante": "E",
                "visitante": "F",
                "placar": "0-0",
                "status": "Finalizado",
                "estatisticas": {},
                "confirmacao_api": {
                    "fixture_id": 123,
                    "status": {"short": "PEN", "elapsed": 120},
                    "placar": [0, 0],
                },
                "qualidade": {
                    "pontuacao": 100,
                    "fontes": ["api_football"],
                    "apto_para_liquidacao": True,
                },
            })

        resumo = FinalizadorPendenciasSemDado(self.banco).recuperar_conclusivos(
            datetime(2026, 7, 22, 14, 0)
        )

        self.assertEqual(resumo["recuperados"], 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT resultado, retorno_unidades, fonte_resultado, observacao
            FROM resultados_sinais WHERE sinal_id=?
            """,
            (sinal,),
        ).fetchone()
        self.assertEqual(tuple(resultado[:3]), ("void", 0.0, "packball"))
        self.assertIn("permaneceu invariável", resultado["observacao"])
        self.assertEqual(
            reabrir_resultados_provisorios(self.banco),
            {"quantidade": 0, "sinais": []},
        )
        preservado = self.banco.conexao.execute(
            """
            SELECT resultado, retorno_unidades, fonte_resultado
            FROM resultados_sinais WHERE sinal_id=?
            """,
            (sinal,),
        ).fetchone()
        self.assertEqual(tuple(preservado), ("void", 0.0, "packball"))

    def test_nao_recupera_escanteios_se_total_mudou_apos_leitura_regulamentar(self):
        entrada = self.banco.salvar_registro({
            "coletado_em": datetime(2026, 7, 20, 15, 0),
            "url": "https://packball.com/match/corners/extra-time",
            "mandante": "G",
            "visitante": "H",
            "placar": "0-0",
            "status": "84 '",
            "estatisticas": {"Escanteios": "4-8"},
            "qualidade": {
                "pontuacao": 100,
                "fontes": ["packball", "api_football"],
                "apto_para_liquidacao": True,
            },
        })
        sinal = self.banco.salvar_candidatos(entrada, [{
            "mercado": "escanteios_ft_asiatico",
            "linha": 12.0,
            "odd": 2.25,
            "pontuacao_tecnica": 90,
            "regra_versao": "sinais-v1",
            "status": "simulacao",
        }])[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, 'sem_dado', NULL, ?, NULL, 'sem_dado')
                """,
                (sinal, datetime(2026, 7, 21, 15, 0).isoformat(), "sem fonte"),
            )
        for minuto in (20, 31, 42):
            self.banco.salvar_registro({
                "coletado_em": datetime(2026, 7, 20, 15, minuto),
                "url": "https://packball.com/match/corners/extra-time",
                "mandante": "G",
                "visitante": "H",
                "placar": "0-0",
                "status": "PEN",
                "estatisticas": {"Escanteios": "5-8"},
                "qualidade": {
                    "pontuacao": 80,
                    "fontes": ["packball"],
                },
            })
        for minuto in (22, 44):
            self.banco.salvar_registro({
                "coletado_em": datetime(2026, 7, 20, 15, minuto),
                "url": "https://packball.com/match/corners/extra-time",
                "mandante": "G",
                "visitante": "H",
                "placar": "0-0",
                "status": "Finalizado",
                "estatisticas": {},
                "confirmacao_api": {
                    "fixture_id": 124,
                    "status": {"short": "PEN", "elapsed": 120},
                },
                "qualidade": {
                    "pontuacao": 100,
                    "fontes": ["api_football"],
                    "apto_para_liquidacao": True,
                },
            })

        resumo = FinalizadorPendenciasSemDado(self.banco).recuperar_conclusivos(
            datetime(2026, 7, 22, 15, 0)
        )

        self.assertEqual(resumo["recuperados"], 0)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT resultado FROM resultados_sinais WHERE sinal_id=?",
                (sinal,),
            ).fetchone()[0],
            "sem_dado",
        )

    def test_packball_recupera_gol_ht_de_consulta_persistida(self):
        snapshot = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "gol_ht",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v1",
                "status": "simulacao",
            }],
        )
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot,)
        ).fetchone()[0]
        self.banco.registrar_consulta_finalizacao(
            partida_id,
            "packball",
            "finalizado_dados_incompletos",
            status_observado="HT 1-0 2-0",
            placar_observado="2-0",
        )
        finalizador = FinalizadorResultadosPackBall(
            self.banco,
            PackBallFalso(),
            AvaliadorBacktest(self.banco),
        )

        resumo = finalizador.executar(
            object(), {"https://packball.com/match/1/live"}
        )

        self.assertEqual(resumo["intervalos_persistidos_recuperados"], 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT r.resultado, r.fonte_resultado
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            WHERE s.mercado='gol_ht'
            """
        ).fetchone()
        self.assertEqual(tuple(resultado), ("green", "packball"))

    def test_api_pen_liquida_so_tempo_regulamentar(self):
        snapshot = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "proximo_gol",
                "linha": "casa",
                "odd": 2.0,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }],
        )
        finalizador = FinalizadorResultadosAPI(
            self.banco,
            APIFalsaComPenaltis(),
            AvaliadorBacktest(self.banco),
        )

        resumo = finalizador.executar()

        self.assertEqual(resumo["resolvidos"], 2)
        resultados = self.banco.conexao.execute(
            """
            SELECT s.mercado, r.resultado, r.fonte_resultado
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            ORDER BY s.id
            """
        ).fetchall()
        self.assertEqual(tuple(resultados[0]), ("gol_ft", "red", "api_football"))
        self.assertEqual(tuple(resultados[1]), ("proximo_escanteio", None, None))
        self.assertEqual(tuple(resultados[2]), ("proximo_gol", "red", "api_football"))
        final = self.banco.conexao.execute(
            """
            SELECT placar, estatisticas_json, confirmacao_api_json
            FROM snapshots ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        self.assertEqual(final["placar"], "0-0")
        self.assertEqual(json.loads(final["estatisticas_json"]), {})
        self.assertEqual(
            json.loads(final["confirmacao_api_json"])["eventos"], []
        )

    def test_cooldown_api_evitar_reconsulta_de_dado_incompleto(self):
        api = APIFalsaSemEstatisticas(None)
        primeiro = FinalizadorResultadosAPI(
            self.banco, api, AvaliadorBacktest(self.banco)
        )
        self.assertEqual(primeiro.executar()["resolvidos"], 1)
        segundo = FinalizadorResultadosAPI(
            self.banco, api, AvaliadorBacktest(self.banco)
        )
        self.assertEqual(segundo.executar()["consultadas"], 0)
        estado = self.banco.conexao.execute(
            """
            SELECT estado FROM consultas_finalizacao
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()[0]
        self.assertEqual(estado, "finalizado_dados_incompletos")

    def test_cooldown_api_prioriza_sinal_entregue_e_preserva_sombra(self):
        sinal_entregue = self.banco.conexao.execute(
            "SELECT id FROM sinais WHERE mercado='gol_ft' LIMIT 1"
        ).fetchone()[0]
        self.banco.registrar_entrega_alerta(
            sinal_entregue,
            "telegram:gols:teste",
            "entregue",
            provedor="telegram",
            provedor_destino_id="-1001",
            provedor_mensagem_id="101",
        )
        snapshot_sombra = self.banco.salvar_registro(
            {
                "coletado_em": datetime(2026, 7, 20, 12, 1),
                "url": "https://packball.com/match/2/live",
                "mandante": "C",
                "visitante": "D",
                "placar": "0-0",
                "status": "60 '",
                "estatisticas": {},
                "confirmacao_api": {"fixture_id": 456},
            }
        )
        self.banco.salvar_candidatos(
            snapshot_sombra,
            [{
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-sombra-v1",
                "status": "simulacao",
            }],
        )
        instante = datetime.now() - timedelta(minutes=5)
        for partida_id in self.banco.conexao.execute(
            "SELECT id FROM partidas ORDER BY id"
        ).fetchall():
            self.banco.registrar_consulta_finalizacao(
                partida_id[0], "api_football", "em_andamento",
                instante=instante,
            )
        api = APIFalsaCaptura()

        with patch.dict(
            os.environ,
            {"FINALIZACAO_API_COOLDOWN_ENTREGUE_MINUTOS": "3"},
        ):
            resumo = FinalizadorResultadosAPI(
                self.banco, api, AvaliadorBacktest(self.banco)
            ).executar()

        self.assertEqual(resumo["consultadas"], 1)
        self.assertEqual(api.consultas, [[123]])
        self.assertEqual(resumo["cooldown_entregue_minutos"], 3)
        self.assertEqual(resumo["cooldown_sombra_minutos"], 10)
        self.assertEqual(resumo["consultadas_entregues"], 1)
        self.assertEqual(resumo["suprimidas_cooldown_entregue"], 0)
        self.assertEqual(resumo["suprimidas_cooldown_sombra"], 1)
        self.assertEqual(
            resumo["rollback"],
            "FINALIZACAO_API_COOLDOWN_ENTREGUE_MINUTOS=10",
        )

    def test_cooldown_api_entregue_pode_regredir_para_dez_minutos(self):
        sinal_entregue = self.banco.conexao.execute(
            "SELECT id FROM sinais WHERE mercado='gol_ft' LIMIT 1"
        ).fetchone()[0]
        self.banco.registrar_entrega_alerta(
            sinal_entregue,
            "telegram:gols:teste",
            "entregue",
            provedor="telegram",
            provedor_destino_id="-1001",
            provedor_mensagem_id="102",
        )
        partida_id = self.banco.conexao.execute(
            "SELECT id FROM partidas LIMIT 1"
        ).fetchone()[0]
        self.banco.registrar_consulta_finalizacao(
            partida_id,
            "api_football",
            "em_andamento",
            instante=datetime.now() - timedelta(minutes=5),
        )
        api = APIFalsaCaptura()

        with patch.dict(
            os.environ,
            {"FINALIZACAO_API_COOLDOWN_ENTREGUE_MINUTOS": "10"},
        ):
            resumo = FinalizadorResultadosAPI(
                self.banco, api, AvaliadorBacktest(self.banco)
            ).executar()

        self.assertEqual(resumo["consultadas"], 0)
        self.assertEqual(api.consultas, [])
        self.assertEqual(resumo["cooldown_entregue_minutos"], 10)
        self.assertEqual(resumo["consultadas_entregues"], 0)
        self.assertEqual(resumo["suprimidas_cooldown_entregue"], 1)

    def test_expira_sem_dado_somente_apos_tempo_e_todas_as_fontes(self):
        partida_id = self.banco.conexao.execute(
            "SELECT id FROM partidas LIMIT 1"
        ).fetchone()[0]
        self.banco.registrar_consulta_finalizacao(
            partida_id,
            "api_football",
            "finalizado_dados_incompletos",
            instante=datetime(2026, 7, 20, 12, 0),
        )
        self.banco.registrar_consulta_finalizacao(
            partida_id,
            "api_football",
            "finalizado_dados_incompletos",
            instante=datetime(2026, 7, 20, 12, 10),
        )
        finalizador = FinalizadorPendenciasSemDado(
            self.banco, idade_horas=24, tentativas_minimas=3
        )
        antes = finalizador.executar(datetime(2026, 7, 21, 13, 0))
        self.assertEqual(antes["encerrados_sem_dado"], 0)

        self.banco.registrar_consulta_finalizacao(
            partida_id,
            "packball",
            "finalizado_dados_incompletos",
            instante=datetime(2026, 7, 20, 12, 20),
        )
        depois = finalizador.executar(datetime(2026, 7, 21, 13, 0))
        self.assertEqual(depois["encerrados_sem_dado"], 2)
        resultados = self.banco.conexao.execute(
            """
            SELECT resultado, retorno_unidades, observacao,
                   snapshot_id_liquidacao, fonte_resultado
            FROM resultados_sinais ORDER BY sinal_id
            """
        ).fetchall()
        self.assertEqual([item["resultado"] for item in resultados], [
            "sem_dado", "sem_dado"
        ])
        self.assertTrue(all(item["retorno_unidades"] is None for item in resultados))
        self.assertTrue(all("fontes=" in item["observacao"] for item in resultados))
        self.assertTrue(all(
            item["snapshot_id_liquidacao"] is None
            and item["fonte_resultado"] == "sem_dado"
            for item in resultados
        ))
        metricas = AvaliadorBacktest(self.banco).metricas()
        self.assertEqual(metricas["amostra"], 0)
        self.assertEqual(metricas["observacoes_sem_dado"], 2)

    def test_nao_expira_sem_dado_antes_de_24_horas(self):
        partida_id = self.banco.conexao.execute(
            "SELECT id FROM partidas LIMIT 1"
        ).fetchone()[0]
        for indice, fonte in enumerate(
            ("api_football", "packball", "api_football")
        ):
            self.banco.registrar_consulta_finalizacao(
                partida_id,
                fonte,
                "finalizado_dados_incompletos",
                instante=datetime(2026, 7, 20, 12, indice),
            )
        finalizador = FinalizadorPendenciasSemDado(self.banco)
        resumo = finalizador.executar(datetime(2026, 7, 20, 20, 0))
        self.assertEqual(resumo["encerrados_sem_dado"], 0)

    def test_expira_apos_72_horas_de_erros_em_todas_as_fontes(self):
        partida_id = self.banco.conexao.execute(
            "SELECT id FROM partidas LIMIT 1"
        ).fetchone()[0]
        fontes = (
            "api_football", "packball", "api_football",
            "packball", "api_football", "packball",
        )
        for indice, fonte in enumerate(fontes):
            self.banco.registrar_consulta_finalizacao(
                partida_id,
                fonte,
                "erro",
                erro="fonte indisponível",
                instante=datetime(2026, 7, 17, 12, indice),
            )
        finalizador = FinalizadorPendenciasSemDado(self.banco)

        resumo = finalizador.executar(datetime(2026, 7, 21, 13, 0))

        self.assertEqual(resumo["encerrados_sem_dado"], 2)
        self.assertEqual(resumo["encerrados_fallback"], 2)
        observacoes = self.banco.conexao.execute(
            "SELECT observacao FROM resultados_sinais"
        ).fetchall()
        self.assertTrue(all(
            "modo=fontes_indisponiveis" in item[0]
            for item in observacoes
        ))

    def test_finaliza_pelo_packball_quando_saiu_do_ao_vivo(self):
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                UPDATE sinais SET status='simulacao'
                WHERE mercado='proximo_escanteio'
                """
            )
        coletor = PackBallFalso()
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar(object(), set())
        self.assertEqual(resumo["encerradas"], 1)
        self.assertEqual(resumo["resolvidos"], 2)
        self.assertEqual(AvaliadorBacktest(self.banco).metricas()["amostra"], 1)
        self.assertEqual(coletor.urls, ["https://packball.com/match/1/live"])
        consulta = self.banco.conexao.execute(
            "SELECT fonte, estado, placar_observado FROM consultas_finalizacao"
        ).fetchone()
        self.assertEqual(
            tuple(consulta), ("packball", "finalizado", "2-0")
        )

    def test_packball_interrompe_entre_consultas_para_manutencao(self):
        segundo_snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:05:00",
            "url": "https://packball.com/match/2/live",
            "mandante": "C",
            "visitante": "D",
            "placar": "0-0",
            "status": "65 '",
            "estatisticas": {"Escanteios": "1-1"},
        })
        self.banco.salvar_candidatos(segundo_snapshot, [{
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.8,
            "pontuacao_tecnica": 80,
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])
        coletor = PackBallFalso(finalizado=False)
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco),
            limite_por_ciclo=2,
        )
        interromper = Mock(side_effect=[False, True])

        resumo = finalizador.executar(
            object(), set(), interromper_fn=interromper
        )

        self.assertTrue(resumo["interrompido_manutencao"])
        self.assertEqual(resumo["consultadas"], 1)
        self.assertEqual(len(coletor.urls), 1)

    def test_packball_limita_navegacoes_sem_mudar_limite_padrao(self):
        segundo_snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:05:00",
            "url": "https://packball.com/match/2/live",
            "mandante": "C",
            "visitante": "D",
            "placar": "0-0",
            "status": "65 '",
            "estatisticas": {"Escanteios": "1-1"},
        })
        self.banco.salvar_candidatos(segundo_snapshot, [{
            "mercado": "gol_ft",
            "linha": 1.5,
            "odd": 1.8,
            "pontuacao_tecnica": 80,
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])
        coletor = PackBallFalso(finalizado=False)
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco),
            limite_por_ciclo=3,
        )

        resumo = finalizador.executar(
            object(), set(), limite_navegacoes=1
        )

        self.assertEqual(resumo["limite_navegacoes"], 1)
        self.assertEqual(resumo["consultadas"], 1)
        self.assertEqual(len(coletor.urls), 1)

    def test_packball_pen_usa_snapshot_antes_da_prorrogacao(self):
        self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T13:30:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "89 '",
                "estatisticas": {"Escanteios": "8-4"},
            }
        )
        self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T13:32:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "BREAK '",
                "estatisticas": {"Escanteios": "8-4"},
            }
        )
        coletor = PackBallFalso(
            finalizado=False,
            placar="1-1",
            status_minuto="PEN",
        )
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )

        resumo = finalizador.executar(object(), set())

        self.assertEqual(resumo["encerradas"], 1)
        self.assertEqual(resumo["resolvidos"], 2)
        self.assertEqual(resumo["regulamentares_recuperadas"], 1)
        self.assertEqual(coletor.urls, [])
        resultados = self.banco.conexao.execute(
            """
            SELECT s.mercado, r.resultado, r.fonte_resultado
            FROM sinais s
            JOIN resultados_sinais r ON r.sinal_id=s.id
            ORDER BY s.id
            """
        ).fetchall()
        self.assertEqual(tuple(resultados[0]), ("gol_ft", "red", "packball"))
        self.assertEqual(
            tuple(resultados[1]),
            ("proximo_escanteio", "green", "packball"),
        )
        final = self.banco.conexao.execute(
            """
            SELECT placar, status, estatisticas_json
            FROM snapshots ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        self.assertEqual(final["placar"], "0-0")
        self.assertEqual(final["status"], "Finalizado (90min)")
        self.assertEqual(
            json.loads(final["estatisticas_json"])["Escanteios"], "8-4"
        )

    def test_packball_pen_sem_break_usa_ultimo_minuto_regulamentar(self):
        self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T13:30:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "93 '",
                "estatisticas": {"Escanteios": "8-4"},
            }
        )
        self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T13:45:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "1-0",
                "status": "106 '",
                "estatisticas": {"Escanteios": "9-4"},
            }
        )
        self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T14:10:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "1-1",
                "status": (
                    "Penaltis ao vivo porque na prorrogacao nao houve vencedor"
                ),
                "estatisticas": {"Escanteios": "10-5"},
            }
        )
        coletor = PackBallFalso(
            finalizado=False,
            placar="2-2",
            status_minuto="PEN",
        )
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )

        resumo = finalizador.executar(
            object(), {"https://packball.com/match/1/live"}
        )

        self.assertEqual(resumo["encerradas"], 1)
        self.assertEqual(resumo["regulamentares_recuperadas"], 1)
        self.assertEqual(coletor.urls, [])
        final = self.banco.conexao.execute(
            "SELECT placar, status FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(tuple(final), ("0-0", "Finalizado (90min)"))

    def test_nao_consulta_partida_que_continua_ao_vivo(self):
        coletor = PackBallFalso()
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar(
            object(), {"https://packball.com/match/1/live"}
        )
        self.assertEqual(resumo["consultadas"], 0)
        self.assertEqual(coletor.urls, [])

    def test_cooldown_de_finalizacao_persiste_entre_instancias(self):
        coletor = PackBallFalso(finalizado=False)
        primeiro = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )
        self.assertEqual(primeiro.executar(object(), set())["consultadas"], 1)
        segundo = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )
        self.assertEqual(segundo.executar(object(), set())["consultadas"], 0)
        self.assertEqual(len(coletor.urls), 1)
        estado = self.banco.conexao.execute(
            "SELECT estado FROM consultas_finalizacao"
        ).fetchone()[0]
        self.assertEqual(estado, "em_andamento")

    def test_prioriza_sinal_antigo_mesmo_com_snapshot_recente_da_api(self):
        segundo_snapshot = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:05:00",
                "url": "https://packball.com/match/2/live",
                "mandante": "C",
                "visitante": "D",
                "placar": "0-0",
                "status": "65 '",
                "estatisticas": {"Escanteios": "1-1"},
            }
        )
        self.banco.salvar_candidatos(
            segundo_snapshot,
            [{
                "mercado": "gol_ft",
                "linha": 1.5,
                "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }],
        )
        self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T13:00:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "2-0",
                "status": "Atualização API",
                "estatisticas": {},
            }
        )
        coletor = PackBallFalso()
        finalizador = FinalizadorResultadosPackBall(
            self.banco,
            coletor,
            AvaliadorBacktest(self.banco),
            limite_por_ciclo=1,
        )

        resumo = finalizador.executar(object(), set())

        self.assertEqual(resumo["consultadas"], 1)
        self.assertEqual(
            coletor.urls, ["https://packball.com/match/1/live"]
        )

    def test_partida_fora_da_lista_gera_snapshot_sem_fingir_final(self):
        snapshot = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "proximo_gol",
                "linha": "casa",
                "odd": 1.75,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }],
        )
        coletor = PackBallFalso(finalizado=False, placar="1-0")
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )

        resumo = finalizador.executar(object(), set())

        self.assertEqual(resumo["encerradas"], 0)
        self.assertEqual(resumo["snapshots_recuperados"], 1)
        resultado = self.banco.conexao.execute(
            """
            SELECT r.resultado, r.retorno_unidades
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            WHERE s.mercado='proximo_gol'
            """
        ).fetchone()
        self.assertIsNone(resultado)
        ultimo = self.banco.conexao.execute(
            "SELECT status FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        self.assertEqual(ultimo, "94 '")

    def test_packball_sem_escanteios_mantem_mercado_pendente(self):
        coletor = PackBallFalso(com_estatisticas=False)
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )
        resumo = finalizador.executar(object(), set())
        self.assertEqual(resumo["resolvidos"], 1)
        pendente = self.banco.conexao.execute(
            """
            SELECT COUNT(*)
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.mercado='proximo_escanteio' AND r.sinal_id IS NULL
            """
        ).fetchone()[0]
        self.assertEqual(pendente, 1)
        estado = self.banco.conexao.execute(
            "SELECT estado FROM consultas_finalizacao ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        self.assertEqual(estado, "finalizado_dados_incompletos")

    def test_packball_nao_revisita_final_incompleto_apos_tres_confirmacoes(self):
        partida_id = self.banco.conexao.execute(
            "SELECT id FROM partidas LIMIT 1"
        ).fetchone()[0]
        for indice in range(3):
            self.banco.registrar_consulta_finalizacao(
                partida_id,
                "packball",
                "finalizado_dados_incompletos",
                instante=datetime.now() - timedelta(minutes=40 + indice),
            )
        coletor = PackBallFalso()
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )

        resumo = finalizador.executar(object(), set())

        self.assertEqual(resumo["consultadas"], 0)
        self.assertEqual(resumo["suprimidas_final_incompleto"], 1)
        self.assertEqual(coletor.urls, [])

    def test_packball_timeline_resolve_proximo_gol_quando_placar_pulou(self):
        snapshot = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.banco.salvar_candidatos(snapshot, [{
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 2.5,
            "pontuacao_tecnica": 80,
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])
        coletor = PackBallFalso(
            placar="1-2",
            eventos_gols=[
                {"minuto": "18", "lado": "visitante"},
                {"minuto": "82", "lado": "visitante"},
                {"minuto": "83", "lado": "casa"},
            ],
        )
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )

        resumo = finalizador.executar(object(), set())
        resultado = self.banco.conexao.execute(
            """
            SELECT r.resultado, r.retorno_unidades, r.fonte_resultado
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            WHERE s.mercado='proximo_gol'
            ORDER BY s.id DESC LIMIT 1
            """
        ).fetchone()

        self.assertGreaterEqual(resumo["resolvidos"], 1)
        self.assertEqual(tuple(resultado), ("red", -1.0, "packball"))

    def test_packball_timeline_incompleta_nao_adivinha_proximo_gol(self):
        snapshot = self.banco.conexao.execute(
            "SELECT id FROM snapshots ORDER BY id LIMIT 1"
        ).fetchone()[0]
        self.banco.salvar_candidatos(snapshot, [{
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 2.5,
            "pontuacao_tecnica": 80,
            "regra_versao": "sinais-v1",
            "status": "aprovado",
        }])
        coletor = PackBallFalso(
            placar="1-2",
            eventos_gols=[
                {"minuto": "18", "lado": "visitante"},
                {"minuto": "83", "lado": "casa"},
            ],
        )
        finalizador = FinalizadorResultadosPackBall(
            self.banco, coletor, AvaliadorBacktest(self.banco)
        )

        resumo = finalizador.executar(object(), set())
        resultado = self.banco.conexao.execute(
            """
            SELECT r.resultado
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            WHERE s.mercado='proximo_gol'
            ORDER BY s.id DESC LIMIT 1
            """
        ).fetchone()

        self.assertEqual(resumo["resolvidos"], 2)
        self.assertIsNone(resultado)


if __name__ == "__main__":
    unittest.main()
