import json
import os
import sqlite3
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from api_football import (
    APIFootball,
    CACHE_DETALHE_SEGUNDOS,
    MERCADOS_ODDS_LIVE_ESPERADOS,
    auditar_cache_api_football,
    auditar_catalogo_odds_live,
    associar_jogo,
    diagnosticar_escanteios_asiaticos_1t_api,
    diagnosticar_gols_total_api,
    diagnosticar_gols_total_ht_api,
    diagnosticar_proximo_gol_api,
    diagnosticar_associacao,
    diagnosticar_capacidade_referencia_payload,
    estruturar_escanteios_asiaticos_1t_api,
    estruturar_escanteios_asiaticos_ft_api,
    estruturar_gols_total_api,
    estruturar_gols_total_ht_api,
    limpar_cache_api_football_expirado,
    verificar_contador_uso,
    verificar_catalogo_odds_live,
    verificar_capacidade_referencia_api,
    verificar_estado_odds_api,
)
from banco import BancoMonitor


def fixture(
    fixture_id=10,
    casa="Clube Atlético Norte",
    fora="Esporte Clube Sul",
    placar=(1, 0),
    minuto=55,
):
    return {
        "fixture": {"id": fixture_id, "status": {"elapsed": minuto}},
        "teams": {"home": {"name": casa}, "away": {"name": fora}},
        "goals": {"home": placar[0], "away": placar[1]},
        "events": [],
    }


def catalogo_odds_live_completo():
    return [
        {"id": bet_id, "name": nome}
        for bet_id, nome in MERCADOS_ODDS_LIVE_ESPERADOS.items()
    ]


class APIFootballTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_api_football"
        self.pasta.mkdir(exist_ok=True)

    def tearDown(self):
        for arquivo in self.pasta.glob("*"):
            arquivo.unlink()
        self.pasta.rmdir()

    def test_catalogo_live_confirma_ids_e_nao_inventa_asiatico_2t(self):
        estado = auditar_catalogo_odds_live([
            *catalogo_odds_live_completo(),
            {"id": 31, "name": "Total Corners (3way) (2nd Half)"},
        ], "2026-07-22T19:00:00")

        self.assertTrue(estado["saudavel"])
        self.assertFalse(estado["asiatico_2t_disponivel"])
        self.assertEqual(estado["candidatos_asiatico_2t"], [])

    def test_associacao_transporta_detalhes_embutidos_para_consumo_imediato(self):
        item = fixture()
        item["events"] = [{"type": "Goal"}]
        item["statistics"] = [{"team": {"id": 1}, "statistics": []}]
        item["players"] = [{"team": {"id": 1}, "players": []}]
        item["lineups"] = [{"team": {"id": 1}, "startXI": []}]

        associacao = diagnosticar_associacao(
            {
                "mandante": "Clube Atlético Norte",
                "visitante": "Esporte Clube Sul",
                "placar": "1-0",
                "status": "55 '",
            },
            [item],
        )["associacao"]

        self.assertEqual(associacao["eventos"], item["events"])
        self.assertEqual(
            associacao["_estatisticas_embutidas"], item["statistics"]
        )
        self.assertEqual(
            associacao["_jogadores_embutidos"], item["players"]
        )
        self.assertEqual(
            associacao["_escalacoes_embutidas"], item["lineups"]
        )

    def test_catalogo_live_detecta_drift_e_novo_asiatico_2t(self):
        catalogo = catalogo_odds_live_completo()
        catalogo = [
            item for item in catalogo if item["id"] not in (32, 51)
        ]
        estado = auditar_catalogo_odds_live([
            *catalogo,
            {"id": 32, "name": "Asian Corners Changed"},
            {"id": 51, "name": "Asian Corners (1st Half)"},
            {"id": 300, "name": "Asian Corners (2nd Half)"},
        ])

        self.assertFalse(estado["saudavel"])
        self.assertEqual(
            estado["divergencias"], ["bet_32_nome_divergente"]
        )
        self.assertTrue(estado["asiatico_2t_disponivel"])
        self.assertEqual(estado["candidatos_asiatico_2t"][0]["id"], 300)

    def test_estado_catalogo_live_reprova_evidencia_vencida(self):
        caminho = self.pasta / "catalogo.json"
        estado = auditar_catalogo_odds_live([
            {"id": 32, "name": "Asian Corners"},
            {"id": 51, "name": "Asian Corners (1st Half)"},
        ], "2026-07-20T10:00:00")
        caminho.write_text(json.dumps(estado), encoding="utf-8")

        auditoria = verificar_catalogo_odds_live(
            caminho, agora=datetime(2026, 7, 23, 10, 1)
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["estado"], "desatualizado")

    def test_catalogo_live_persiste_e_reutiliza_cache_diario(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        resposta = {"response": catalogo_odds_live_completo()}
        primeira = APIFootball(self.pasta)
        with patch.object(primeira, "_get", return_value=resposta) as chamada:
            estado = primeira.validar_catalogo_odds_ao_vivo()
        self.assertTrue(estado["saudavel"])
        chamada.assert_called_once_with("/odds/live/bets", {}, "catalogo")

        segunda = APIFootball(self.pasta)
        with patch.object(
            segunda, "_get",
            side_effect=AssertionError("não deveria consultar novamente"),
        ) as chamada_repetida:
            repetido = segunda.validar_catalogo_odds_ao_vivo()
        self.assertTrue(repetido["saudavel"])
        chamada_repetida.assert_not_called()
        self.assertEqual(segunda.cache_persistente_hits, 1)

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    @patch("api_football.urlopen", side_effect=URLError("sem rede"))
    def test_contabiliza_tentativa_que_falhou(self, _):
        api = APIFootball(self.pasta)
        self.assertIsNone(api._get("/fixtures", {"live": "all"}, "geral"))
        self.assertFalse(api.saude_operacional()["saudavel"])
        self.assertEqual(
            api.saude_operacional()["motivo"], "falha_api_no_ciclo"
        )
        consumo = api.consumo_atual()
        self.assertEqual(consumo["mes"], 1)
        self.assertEqual(consumo["dia"]["geral"], 1)
        self.assertTrue((self.pasta / "api_football_uso.json").exists())
        self.assertTrue((self.pasta / "api_football_uso.json.bak").exists())

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_saude_api_so_recupera_apos_resposta_valida(self):
        api = APIFootball(self.pasta)
        with patch(
            "api_football.urlopen", side_effect=URLError("sem rede")
        ):
            api._get("/fixtures", {"live": "all"}, "geral")

        api.iniciar_ciclo_saude()
        self.assertFalse(api.saude_operacional()["saudavel"])
        self.assertEqual(
            api.saude_operacional()["motivo"],
            "api_sem_recuperacao_confirmada",
        )

        resposta = MagicMock()
        resposta.__enter__.return_value = resposta
        resposta.read.return_value = b'{"response":[]}'
        resposta.headers = {}
        with patch("api_football.urlopen", return_value=resposta):
            api._get("/fixtures", {"live": "all"}, "geral")

        self.assertTrue(api.saude_operacional()["saudavel"])

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
            "API_LIMITE_DETALHES_DIARIO": "2000",
        },
        clear=False,
    )
    def test_bloqueia_no_limite_diario_seguro(self):
        api = APIFootball(self.pasta)
        dia = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        api.uso["dias"][dia] = {"geral": 6999, "detalhe": 0}
        self.assertTrue(api._pode_chamar("geral"))
        api.uso["dias"][dia]["geral"] = 7000
        self.assertFalse(api._pode_chamar("geral"))
        consumo = api.consumo_atual()
        self.assertEqual(consumo["limite_diario_plano"], 7500)
        self.assertEqual(consumo["limite_diario_seguro"], 7000)
        self.assertEqual(consumo["reserva_diaria"], 500)
        self.assertEqual(consumo["restante_seguro_dia"], 0)

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
            "API_LIMITE_DETALHES_DIARIO": "2000",
        },
        clear=False,
    )
    def test_acumulado_mensal_nao_bloqueia_franquia_diaria(self):
        api = APIFootball(self.pasta)
        agora = datetime.now(timezone.utc)
        api.uso["meses"][agora.strftime("%Y-%m")] = 999999
        api.uso["dias"][agora.strftime("%Y-%m-%d")] = {
            "geral": 10,
            "detalhe": 10,
        }
        self.assertTrue(api._pode_chamar("geral"))

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
            "API_LIMITE_DETALHES_DIARIO": "2000",
        },
        clear=False,
    )
    def test_reserva_cota_de_detalhes_sem_bloquear_consulta_geral(self):
        api = APIFootball(self.pasta)
        dia = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        api.uso["dias"][dia] = {"geral": 0, "detalhe": 2000}
        self.assertFalse(api._pode_chamar("detalhe"))
        self.assertTrue(api._pode_chamar("geral"))

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
        },
        clear=False,
    )
    def test_contador_corrompido_sem_backup_bloqueia_em_falha_fechada(self):
        arquivo = self.pasta / "api_football_uso.json"
        arquivo.write_text("{incompleto", encoding="utf-8")

        api = APIFootball(self.pasta)
        consumo = api.consumo_atual()

        self.assertFalse(api.controle_uso_saudavel)
        self.assertFalse(api._pode_chamar("geral"))
        self.assertEqual(consumo["total_dia"], 7000)
        self.assertEqual(consumo["restante_seguro_dia"], 0)
        self.assertEqual(
            verificar_contador_uso(arquivo)["estado"], "corrompido"
        )

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_recupera_contador_por_backup_sem_zerar_consumo(self):
        arquivo = self.pasta / "api_football_uso.json"
        backup = self.pasta / "api_football_uso.json.bak"
        dia = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mes = datetime.now(timezone.utc).strftime("%Y-%m")
        arquivo.write_text("json inválido", encoding="utf-8")
        backup.write_text(
            json.dumps({
                "meses": {mes: 41},
                "dias": {dia: {"geral": 31, "detalhe": 10}},
            }),
            encoding="utf-8",
        )

        api = APIFootball(self.pasta)

        self.assertTrue(api.controle_uso_saudavel)
        self.assertTrue(api.controle_uso_recuperado)
        self.assertEqual(api.consumo_atual()["total_dia"], 41)
        contador = verificar_contador_uso(arquivo)
        self.assertEqual(contador["estado"], "recuperavel")
        self.assertEqual(contador["consumo_dia"], 41)
        api._registrar_chamada("geral")
        self.assertEqual(api.consumo_atual()["total_dia"], 42)
        self.assertEqual(verificar_contador_uso(arquivo)["estado"], "valido")

    def test_contador_rejeita_quantidades_negativas(self):
        arquivo = self.pasta / "api_football_uso.json"
        arquivo.write_text(
            '{"meses":{"2026-07":-1},"dias":{}}', encoding="utf-8"
        )

        estado = verificar_contador_uso(arquivo)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["estado"], "corrompido")

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
        },
        clear=False,
    )
    def test_reconcilia_consumo_externo_sem_reduzir_contador_local(self):
        resposta = MagicMock()
        resposta.__enter__.return_value = resposta
        resposta.read.return_value = b'{"response":[]}'
        resposta.headers = {
            "x-ratelimit-requests-limit": "7500",
            "x-ratelimit-requests-remaining": "7390",
            "x-ratelimit-limit": "300",
            "x-ratelimit-remaining": "250",
        }
        api = APIFootball(self.pasta)

        with patch("api_football.urlopen", return_value=resposta):
            self.assertEqual(
                api._get("/fixtures", {"live": "all"}, "geral"),
                {"response": []},
            )

        consumo = api.consumo_atual()
        self.assertEqual(consumo["total_dia"], 110)
        self.assertEqual(consumo["dia"]["externo"], 109)
        self.assertEqual(consumo["mes"], 1)
        self.assertEqual(consumo["reconciliacoes_cota"], 1)
        self.assertEqual(consumo["cota_provedor"]["restante_diario"], 7390)

        dia = consumo["cota_provedor"]["dia"]
        api.uso["dias"][dia] = {"geral": 200, "detalhe": 0}
        api._reconciliar_cota_provedor(resposta.headers)
        self.assertEqual(sum(api.uso["dias"][dia].values()), 200)

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
        },
        clear=False,
    )
    def test_reconcilia_para_baixo_ajuste_externo_obsoleto(self):
        api = APIFootball(self.pasta)
        dia = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        api.uso["dias"][dia] = {
            "geral": 32,
            "detalhe": 138,
            "odds": 38,
            "externo": 1189,
        }
        cabecalhos = {
            "x-ratelimit-requests-limit": "7500",
            "x-ratelimit-requests-remaining": "7292",
            "x-ratelimit-limit": "300",
            "x-ratelimit-remaining": "299",
        }

        self.assertTrue(api._reconciliar_cota_provedor(cabecalhos))

        consumo = api.consumo_atual()
        self.assertEqual(consumo["total_dia"], 208)
        self.assertNotIn("externo", consumo["dia"])

        cabecalhos["x-ratelimit-requests-remaining"] = "7293"
        self.assertTrue(api._reconciliar_cota_provedor(cabecalhos))
        self.assertEqual(api.consumo_atual()["total_dia"], 208)

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
        },
        clear=False,
    )
    def test_limite_menor_do_provedor_e_bloqueio_minuto_prevalecem(self):
        api = APIFootball(self.pasta)
        cabecalhos = {
            "x-ratelimit-requests-limit": "1000",
            "x-ratelimit-requests-remaining": "600",
            "x-ratelimit-limit": "10",
            "x-ratelimit-remaining": "0",
        }
        with patch("api_football.time.time", return_value=1000.0):
            self.assertTrue(api._reconciliar_cota_provedor(cabecalhos))
            self.assertFalse(api._pode_chamar("geral"))
        self.assertEqual(api.consumo_atual()["limite_diario_seguro"], 500)

        with patch("api_football.time.time", return_value=1061.0):
            self.assertTrue(api._pode_chamar("geral"))
        dia = api.consumo_atual()["cota_provedor"]["dia"]
        api.uso["dias"][dia]["externo"] = 500
        api.uso["dias"][dia]["geral"] = 0
        api.uso["dias"][dia]["detalhe"] = 0
        self.assertFalse(api._pode_chamar("geral"))

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_cabecalho_invalido_nao_substitui_contador_conservador(self):
        resposta = MagicMock()
        resposta.__enter__.return_value = resposta
        resposta.read.return_value = b'{"response":[]}'
        resposta.headers = {
            "x-ratelimit-requests-limit": "7500",
            "x-ratelimit-requests-remaining": "invalido",
        }
        api = APIFootball(self.pasta)

        with patch("api_football.urlopen", return_value=resposta):
            resultado = api._get(
                "/fixtures", {"live": "all"}, "geral"
            )

        self.assertEqual(resultado, {"response": []})
        self.assertEqual(api.consumo_atual()["total_dia"], 1)
        self.assertEqual(api.cabecalhos_cota_invalidos, 1)
        self.assertNotIn("provedor", api.uso)

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_http_error_tambem_reconcilia_cota(self):
        api = APIFootball(self.pasta)
        erro = HTTPError(
            "https://exemplo",
            429,
            "limite",
            {
                "x-ratelimit-requests-limit": "7500",
                "x-ratelimit-requests-remaining": "7000",
                "x-ratelimit-limit": "10",
                "x-ratelimit-remaining": "0",
            },
            None,
        )

        with patch("api_football.urlopen", side_effect=erro):
            self.assertIsNone(
                api._get("/fixtures", {"live": "all"}, "geral")
            )
        erro.close()

        self.assertEqual(api.consumo_atual()["total_dia"], 500)
        self.assertEqual(api.reconciliacoes_cota, 1)

    def test_contador_usa_virada_do_dia_em_utc(self):
        arquivo = self.pasta / "api_football_uso.json"
        arquivo.write_text(
            json.dumps({
                "meses": {"2026-07": 3},
                "dias": {
                    "2026-07-21": {"geral": 1},
                    "2026-07-22": {"geral": 2},
                },
            }),
            encoding="utf-8",
        )
        instante_local = datetime(
            2026, 7, 21, 20, 30,
            tzinfo=timezone(timedelta(hours=-4)),
        )

        estado = verificar_contador_uso(arquivo, instante_local)

        self.assertEqual(estado["dia"], "2026-07-22")
        self.assertEqual(estado["consumo_dia"], 2)

    def test_contador_rejeita_estado_de_provedor_corrompido(self):
        arquivo = self.pasta / "api_football_uso.json"
        arquivo.write_text(
            json.dumps({
                "meses": {},
                "dias": {},
                "provedor": {
                    "dia": "2026-07-21",
                    "limite_diario": 100,
                    "restante_diario": 101,
                    "limite_minuto": None,
                    "restante_minuto": None,
                    "observado_em": 1000,
                },
            }),
            encoding="utf-8",
        )

        estado = verificar_contador_uso(arquivo)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["estado"], "corrompido")

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_status_gratuito_sincroniza_cota_sem_contar_chamada_local(self):
        resposta = MagicMock()
        resposta.__enter__.return_value = resposta
        resposta.headers = {}
        resposta.read.return_value = json.dumps({
            "response": {
                "requests": {"current": 42, "limit_day": 7500}
            }
        }).encode("utf-8")
        api = APIFootball(self.pasta)

        with patch("api_football.urlopen", return_value=resposta) as abrir:
            sincronizacao = api.sincronizar_cota_status()

        self.assertTrue(sincronizacao["sincronizado"])
        self.assertEqual(sincronizacao["consumo_dia"], 42)
        self.assertEqual(api.consumo_atual()["dia"]["externo"], 42)
        self.assertEqual(api.consumo_atual()["dia"]["geral"], 0)
        self.assertEqual(api.consumo_atual()["mes"], 0)
        self.assertTrue(api.saude_operacional()["saudavel"])
        requisicao = abrir.call_args.args[0]
        self.assertEqual(requisicao.full_url, "https://v3.football.api-sports.io/status")

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_recarrega_contador_compartilhado_sem_zerar_estado_valido(self):
        api = APIFootball(self.pasta)
        agora = datetime.now(timezone.utc)
        dia = agora.strftime("%Y-%m-%d")
        mes = agora.strftime("%Y-%m")
        api.uso["dias"][dia] = {"geral": 3, "detalhe": 0}

        api.arquivo_uso.write_text(json.dumps({
            "versao": 2,
            "meses": {mes: 42},
            "dias": {dia: {"geral": 42, "detalhe": 0}},
        }), encoding="utf-8")

        self.assertTrue(api.recarregar_uso_compartilhado())
        self.assertEqual(42, api.consumo_atual()["total_dia"])

        api.arquivo_uso.write_text("{invalido", encoding="utf-8")
        self.assertFalse(api.recarregar_uso_compartilhado())
        self.assertEqual(42, api.consumo_atual()["total_dia"])

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
            "API_FOOTBALL_COTA_RESSINCRONIZAR_SEGUNDOS": "60",
        },
        clear=False,
    )
    def test_get_ressincroniza_fotografia_externa_antiga_e_retoma(self):
        api = APIFootball(self.pasta)
        agora = datetime.now(timezone.utc)
        dia = agora.strftime("%Y-%m-%d")
        api.uso["dias"][dia] = {
            "geral": 0, "detalhe": 0, "externo": 7000,
        }
        api.uso["provedor"] = {
            "dia": dia,
            "limite_diario": 7500,
            "restante_diario": 500,
            "limite_minuto": 300,
            "restante_minuto": 299,
            "observado_em": time.time() - 120,
        }
        api._salvar_uso()

        def sincronizar_reset():
            api.uso["dias"][dia].pop("externo", None)
            api.uso["provedor"] = {
                "dia": dia,
                "limite_diario": 7500,
                "restante_diario": 7500,
                "limite_minuto": 300,
                "restante_minuto": 300,
                "observado_em": time.time(),
            }
            api._salvar_uso()
            return {
                "sincronizado": True,
                "motivo": None,
                "consumo_dia": 0,
                "limite_diario": 7500,
            }

        resposta = MagicMock()
        resposta.__enter__.return_value = resposta
        resposta.read.return_value = b'{"response":[]}'
        resposta.headers = {
            "x-ratelimit-requests-limit": "7500",
            "x-ratelimit-requests-remaining": "7499",
            "x-ratelimit-limit": "300",
            "x-ratelimit-remaining": "299",
        }
        with patch.object(
            api, "sincronizar_cota_status", side_effect=sincronizar_reset
        ) as sincronizar, patch(
            "api_football.urlopen", return_value=resposta
        ) as abrir:
            dados = api._get("/fixtures", {"live": "all"}, "geral")

        self.assertEqual({"response": []}, dados)
        sincronizar.assert_called_once()
        abrir.assert_called_once()
        self.assertEqual(1, api.consumo_atual()["total_dia"])
        self.assertEqual(1, api.ressincronizacoes_cota_bloqueada)

    @patch.dict(
        os.environ,
        {
            "API_FOOTBALL_KEY": "teste",
            "API_LIMITE_DIARIO": "7500",
            "API_RESERVA_DIARIA": "500",
            "API_FOOTBALL_COTA_RESSINCRONIZAR_SEGUNDOS": "60",
        },
        clear=False,
    )
    def test_get_nao_repete_status_enquanto_fotografia_esta_fresca(self):
        api = APIFootball(self.pasta)
        dia = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        api.uso["dias"][dia] = {
            "geral": 0, "detalhe": 0, "externo": 7000,
        }
        api.uso["provedor"] = {
            "dia": dia,
            "limite_diario": 7500,
            "restante_diario": 500,
            "limite_minuto": 300,
            "restante_minuto": 299,
            "observado_em": time.time(),
        }
        api._salvar_uso()

        with patch.object(
            api, "sincronizar_cota_status"
        ) as sincronizar, patch("api_football.urlopen") as abrir:
            dados = api._get("/fixtures", {"live": "all"}, "geral")

        self.assertIsNone(dados)
        sincronizar.assert_not_called()
        abrir.assert_not_called()

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_falha_do_status_mantem_contador_local_e_nao_impede_inicio(self):
        api = APIFootball(self.pasta)

        with patch(
            "api_football.urlopen", side_effect=URLError("offline")
        ):
            sincronizacao = api.sincronizar_cota_status()

        self.assertFalse(sincronizacao["sincronizado"])
        self.assertEqual(sincronizacao["motivo"], "URLError")
        self.assertEqual(api.consumo_atual()["total_dia"], 0)
        self.assertFalse(api.saude_operacional()["saudavel"])

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_migra_ajuste_mensal_duplicado_da_reconciliacao_v1(self):
        agora = datetime.now(timezone.utc)
        dia = agora.strftime("%Y-%m-%d")
        mes = agora.strftime("%Y-%m")
        (self.pasta / "api_football_uso.json").write_text(
            json.dumps({
                "meses": {mes: 1364},
                "dias": {dia: {
                    "geral": 0, "detalhe": 0, "externo": 210,
                }},
                "provedor": {
                    "dia": dia,
                    "limite_diario": 7500,
                    "restante_diario": 7290,
                    "limite_minuto": 300,
                    "restante_minuto": 299,
                    "observado_em": 1000.0,
                },
            }),
            encoding="utf-8",
        )

        api = APIFootball(self.pasta)

        self.assertEqual(api.uso["versao"], 2)
        self.assertEqual(api.consumo_atual()["mes"], 1154)
        self.assertEqual(api.consumo_atual()["total_dia"], 210)

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_eventos_sao_consultados_sob_demanda_e_usam_cache(self):
        api = APIFootball(self.pasta)
        resposta = {
            "response": [
                {
                    "time": {"elapsed": 60},
                    "team": {"id": 1},
                    "type": "Goal",
                }
            ]
        }
        with patch.object(api, "_get", return_value=resposta) as requisicao:
            primeiro = api.eventos(123)
            segundo = api.eventos(123)
        self.assertEqual(primeiro, resposta["response"])
        self.assertEqual(segundo, resposta["response"])
        requisicao.assert_called_once_with(
            "/fixtures/events", {"fixture": 123}, "detalhe"
        )

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_estatisticas_de_jogadores_ao_vivo_usam_cache_curto(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        api = APIFootball(self.pasta)
        resposta = {
            "response": [{
                "team": {"id": 1},
                "players": [{"player": {"id": 10}}],
            }]
        }

        with patch.object(api, "_get", return_value=resposta) as requisicao:
            primeiro = api.estatisticas_jogadores(123)
            segundo = api.estatisticas_jogadores(123)

        self.assertEqual(primeiro, resposta["response"])
        self.assertEqual(segundo, resposta["response"])
        requisicao.assert_called_once_with(
            "/fixtures/players",
            {"fixture": 123},
            "detalhe",
            timeout=4.0,
        )

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_detalhes_ao_vivo_agrupam_vinte_ids_e_reutilizam_cache(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        api = APIFootball(self.pasta)

        def resposta(_caminho, parametros, _categoria, timeout=20):
            ids = [int(item) for item in parametros["ids"].split("-")]
            return {
                "response": [
                    {
                        "fixture": {"id": fixture_id},
                        "events": [],
                        "lineups": [],
                        "statistics": [],
                        "players": [],
                    }
                    for fixture_id in ids
                ]
            }

        with patch.object(api, "_get", side_effect=resposta) as requisicao:
            primeira = api.fixtures_ao_vivo_detalhadas(range(1, 26))
            segunda = api.fixtures_ao_vivo_detalhadas(range(1, 26))

        self.assertEqual(len(primeira), 25)
        self.assertEqual(len(segunda), 25)
        self.assertEqual(requisicao.call_count, 2)
        self.assertTrue(all(
            chamada.args[0] == "/fixtures"
            and chamada.args[2] == "detalhe"
            and len(chamada.args[1]["ids"].split("-")) <= 20
            and chamada.kwargs["timeout"] == 6.0
            for chamada in requisicao.call_args_list
        ))
        self.assertEqual(api.cache_persistente_hits, 2)

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_calendario_diario_usa_timezone_e_cache_persistente(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        primeira = APIFootball(self.pasta)
        jogos = [fixture(101), fixture(102)]
        with patch("api_football.time.time", return_value=1000.0), patch.object(
            primeira, "_get", return_value={"response": jogos}
        ) as requisicao:
            self.assertEqual(
                jogos,
                primeira.jogos_por_data(
                    "2026-08-26", "America/New_York"
                ),
            )
        requisicao.assert_called_once_with(
            "/fixtures",
            {"date": "2026-08-26", "timezone": "America/New_York"},
            "geral",
            timeout=8.0,
        )

        segunda = APIFootball(self.pasta)
        with patch("api_football.time.time", return_value=1001.0), patch.object(
            segunda, "_get", side_effect=AssertionError("sem nova chamada")
        ) as requisicao:
            self.assertEqual(
                jogos,
                segunda.jogos_por_data(
                    "2026-08-26", "America/New_York"
                ),
            )
        requisicao.assert_not_called()

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_odds_do_dia_percorrem_todas_paginas_e_reusam_cache(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        primeira = APIFootball(self.pasta)

        def resposta(_caminho, parametros, _categoria, timeout=20):
            pagina = parametros["page"]
            return {
                "response": [{"fixture": {"id": pagina}}],
                "paging": {"current": pagina, "total": 2},
            }

        with patch("api_football.time.time", return_value=1000.0), patch.object(
            primeira, "_get", side_effect=resposta
        ) as requisicao:
            resultado = primeira.odds_pre_jogo_por_data("2026-08-26")
        self.assertTrue(resultado["completo"])
        self.assertEqual([1, 2], [
            item["fixture"]["id"] for item in resultado["itens"]
        ])
        self.assertEqual(2, requisicao.call_count)

        segunda = APIFootball(self.pasta)
        with patch("api_football.time.time", return_value=1001.0), patch.object(
            segunda, "_get", side_effect=AssertionError("sem nova chamada")
        ) as requisicao:
            repetido = segunda.odds_pre_jogo_por_data("2026-08-26")
        self.assertTrue(repetido["completo"])
        self.assertEqual(2, len(repetido["itens"]))
        requisicao.assert_not_called()

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_contexto_pre_jogo_inclui_classificacao_e_historico_detalhado(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        api = APIFootball(self.pasta)
        jogo_recente = {
            "fixture": {"id": 701},
            "teams": {
                "home": {"id": 1},
                "away": {"id": 2},
            },
            "goals": {"home": 2, "away": 1},
        }
        jogo_detalhado = {
            **jogo_recente,
            "statistics": [
                {
                    "team": {"id": 1},
                    "statistics": [
                        {"type": "Corner Kicks", "value": 7},
                    ],
                },
                {
                    "team": {"id": 2},
                    "statistics": [
                        {"type": "Corner Kicks", "value": 3},
                    ],
                },
            ],
        }

        def resposta(caminho, parametros, categoria, timeout=20):
            if caminho == "/fixtures/headtohead":
                return {"response": [jogo_recente]}
            if caminho == "/fixtures" and "team" in parametros:
                return {"response": [jogo_recente]}
            if caminho == "/fixtures" and "ids" in parametros:
                return {"response": [jogo_detalhado]}
            if caminho == "/standings":
                return {"response": [{
                    "league": {"standings": [[{
                        "rank": 1,
                        "team": {"id": 1},
                        "points": 30,
                        "all": {},
                    }]]}
                }]}
            if caminho == "/teams/statistics":
                return {
                    "response": {
                        "team": {"id": parametros["team"]},
                        "league": {"id": 10},
                        "season": 2026,
                    }
                }
            return {"response": []}

        with patch.object(api, "_get", side_effect=resposta) as requisicao:
            contexto = api.contexto_pre_jogo({
                "fixture_id": 999,
                "times": {
                    "home": {"id": 1},
                    "away": {"id": 2},
                },
                "liga": {"id": 10, "season": 2026},
            })

        self.assertEqual(contexto["versao"], "contexto-pre-jogo-v4")
        self.assertEqual(contexto["classificacao"]["mandante"]["posicao"], 1)
        self.assertEqual(
            contexto["historico_detalhado"]["mandante"][
                "escanteios_media"
            ],
            7.0,
        )
        self.assertTrue(any(
            chamada.args[0] == "/fixtures" and "ids" in chamada.args[1]
            for chamada in requisicao.call_args_list
        ))

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_odds_pre_jogo_usam_endpoint_proprio_e_cache_persistente(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        payload = [{
            "fixture": {"id": 123},
            "bookmakers": [{
                "id": 1,
                "name": "Casa",
                "bets": [],
            }],
        }]
        primeira = APIFootball(self.pasta)
        with patch("api_football.time.time", return_value=1000.0), patch.object(
            primeira,
            "_get",
            return_value={"response": payload},
        ) as requisicao:
            self.assertEqual(primeira.odds_pre_jogo(123), payload)
        requisicao.assert_called_once_with(
            "/odds",
            {"fixture": 123},
            "odds_pre_jogo",
            timeout=4.0,
        )

        segunda = APIFootball(self.pasta)
        with patch("api_football.time.time", return_value=1001.0), patch.object(
            segunda,
            "_get",
            side_effect=AssertionError("não deveria consumir a API"),
        ) as requisicao:
            self.assertEqual(segunda.odds_pre_jogo(123), payload)
        requisicao.assert_not_called()
        self.assertEqual(segunda.cache_persistente_hits, 1)

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_cache_persistente_sobrevive_reinicio_em_todos_endpoints(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        item_fixture = fixture(123)
        estatisticas = [{"team": {"id": 1}, "statistics": []}]
        eventos = [{"time": {"elapsed": 60}, "type": "Goal"}]
        odds = [{
            "fixture": {"id": 123},
            "odds": [{
                "id": 51,
                "name": "Asian Corners (1st Half)",
                "values": [
                    {"value": "Over", "odd": "1.8", "handicap": "3.5"},
                    {"value": "Under", "odd": "2", "handicap": "3.5"},
                ],
            }],
        }]

        def resposta(caminho, parametros, categoria):
            if caminho == "/fixtures/statistics":
                return {"response": estatisticas}
            if caminho == "/fixtures/events":
                return {"response": eventos}
            if caminho == "/odds/live":
                return {"response": odds}
            return {"response": [item_fixture]}

        primeira = APIFootball(self.pasta)
        with patch("api_football.time.time", return_value=1000.0), patch.object(
            primeira, "_get", side_effect=resposta
        ):
            self.assertEqual(primeira.jogos_ao_vivo(), [item_fixture])
            self.assertEqual(primeira.estatisticas(123), estatisticas)
            self.assertEqual(primeira.eventos(123), eventos)
            self.assertEqual(primeira.partidas_por_ids([123]), [item_fixture])
            self.assertIsNotNone(
                primeira.odds_escanteios_asiaticos_1t(123)
            )

        segunda = APIFootball(self.pasta)
        with patch("api_football.time.time", return_value=1001.0), patch.object(
            segunda,
            "_get",
            side_effect=AssertionError("não deveria consumir a API"),
        ) as requisicao:
            self.assertEqual(segunda.jogos_ao_vivo(), [item_fixture])
            self.assertEqual(segunda.estatisticas(123), estatisticas)
            self.assertEqual(segunda.eventos(123), eventos)
            self.assertEqual(segunda.partidas_por_ids([123]), [item_fixture])
            self.assertIsNotNone(
                segunda.odds_escanteios_asiaticos_1t(123)
            )

        requisicao.assert_not_called()
        self.assertEqual(segunda.cache_persistente_hits, 5)
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        try:
            self.assertEqual(
                banco.conexao.execute(
                    "SELECT COUNT(*) FROM cache_api_football"
                ).fetchone()[0],
                5,
            )
        finally:
            banco.fechar()

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_cache_persistente_expirado_ou_corrompido_nao_e_usado(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        primeira = APIFootball(self.pasta)
        with patch("api_football.time.time", return_value=1000.0), patch.object(
            primeira, "_get", return_value={"response": [{"valor": "antigo"}]}
        ):
            primeira.estatisticas(123)

        expirada = APIFootball(self.pasta)
        with patch(
            "api_football.time.time",
            return_value=1000.0 + CACHE_DETALHE_SEGUNDOS + 1,
        ), patch.object(
            expirada,
            "_get",
            return_value={"response": [{"valor": "novo"}]},
        ) as requisicao:
            self.assertEqual(
                expirada.estatisticas(123), [{"valor": "novo"}]
            )
        requisicao.assert_called_once()
        self.assertEqual(expirada.cache_persistente_descartes, 1)

        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    UPDATE cache_api_football SET dados_json='{invalido'
                    WHERE chave='fixtures:statistics:123'
                    """
                )
        finally:
            banco.fechar()
        corrompida = APIFootball(self.pasta)
        with patch(
            "api_football.time.time",
            return_value=1000.0 + CACHE_DETALHE_SEGUNDOS + 2,
        ), patch.object(
            corrompida,
            "_get",
            return_value={"response": [{"valor": "recuperado"}]},
        ) as requisicao:
            self.assertEqual(
                corrompida.estatisticas(123), [{"valor": "recuperado"}]
            )
        requisicao.assert_called_once()
        self.assertEqual(corrompida.cache_persistente_descartes, 1)

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_falha_sqlite_no_cache_nao_interrompe_consulta_api(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        api = APIFootball(self.pasta)

        with patch(
            "api_football.sqlite3.connect",
            side_effect=sqlite3.OperationalError("banco ocupado"),
        ), patch.object(
            api,
            "_get",
            return_value={"response": [{"valor": "rede"}]},
        ):
            resultado = api.estatisticas(123)

        self.assertEqual(resultado, [{"valor": "rede"}])
        self.assertEqual(api.cache_persistente_falhas, 2)
        self.assertEqual(api.cache_persistente_gravacoes, 0)

    def test_conexao_cache_fecha_apos_erro_de_leitura(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        banco.fechar()
        api = APIFootball(self.pasta)
        conexao = MagicMock()
        conexao.execute.side_effect = sqlite3.OperationalError("leitura")

        with patch("api_football.sqlite3.connect", return_value=conexao):
            resultado = api._ler_cache_persistente(
                "fixtures:statistics:123", "detalhe", 900, agora=1000
            )

        self.assertIsNone(resultado)
        conexao.close.assert_called_once_with()
        self.assertEqual(api.cache_persistente_falhas, 1)

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_categoria_incorreta_e_descartada_e_substituida(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO cache_api_football (
                        chave, categoria, armazenado_em, dados_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        "fixtures:statistics:123", "geral", 999.0,
                        '[{"valor":"errado"}]',
                    ),
                )
        finally:
            banco.fechar()
        api = APIFootball(self.pasta)

        with patch("api_football.time.time", return_value=1000.0), patch.object(
            api,
            "_get",
            return_value={"response": [{"valor": "correto"}]},
        ):
            resultado = api.estatisticas(123)

        self.assertEqual(resultado, [{"valor": "correto"}])
        self.assertEqual(api.cache_persistente_descartes, 1)
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        try:
            categoria = banco.conexao.execute(
                """
                SELECT categoria FROM cache_api_football
                WHERE chave='fixtures:statistics:123'
                """
            ).fetchone()[0]
            self.assertEqual(categoria, "detalhe")
        finally:
            banco.fechar()

    def test_auditoria_cache_detecta_payload_categoria_e_relogio_invalidos(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        try:
            with banco.conexao:
                banco.conexao.executemany(
                    """
                    INSERT INTO cache_api_football (
                        chave, categoria, armazenado_em, dados_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        ("valida", "geral", 999.0, "[]"),
                        ("corrompida", "detalhe", 999.0, "{invalido"),
                        ("categoria", "desconhecida", 999.0, "{}"),
                        ("futura", "eventos", 2000.0, "[]"),
                    ),
                )

            auditoria = auditar_cache_api_football(
                banco.conexao, agora=1000.0
            )

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual(auditoria["total"], 4)
            self.assertEqual(auditoria["payloads_invalidos"], 1)
            self.assertEqual(auditoria["categorias_invalidas"], 1)
            self.assertEqual(auditoria["relogios_futuros"], 1)
        finally:
            banco.fechar()

    def test_limpeza_cache_remove_apenas_categorias_realmente_expiradas(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        try:
            with banco.conexao:
                banco.conexao.executemany(
                    """
                    INSERT INTO cache_api_football (
                        chave, categoria, armazenado_em, dados_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        ("evento_expirado", "eventos", 900.0, "[]"),
                        ("evento_fresco", "eventos", 950.0, "[]"),
                        ("catalogo_fresco", "catalogo", 100.0, "[]"),
                    ),
                )

                removidos = limpar_cache_api_football_expirado(
                    banco.conexao, agora=1000.0
                )

            self.assertEqual(removidos, 1)
            chaves = {
                linha[0] for linha in banco.conexao.execute(
                    "SELECT chave FROM cache_api_football"
                ).fetchall()
            }
            self.assertEqual(
                chaves, {"evento_fresco", "catalogo_fresco"}
            )
        finally:
            banco.fechar()

    @patch.dict(os.environ, {"API_FOOTBALL_KEY": "teste"}, clear=False)
    def test_limpeza_automatica_do_cache_e_limitada_no_tempo(self):
        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO cache_api_football (
                        chave, categoria, armazenado_em, dados_json
                    ) VALUES ('antigo', 'eventos', 900, '[]')
                    """
                )
        finally:
            banco.fechar()
        api = APIFootball(self.pasta)

        self.assertTrue(api._salvar_cache_persistente(
            "novo_1", "geral", [], armazenado_em=1000.0
        ))
        self.assertEqual(api.cache_persistente_limpezas, 1)
        self.assertEqual(api.cache_persistente_descartes, 1)

        banco = BancoMonitor(self.pasta / "monitor_packball.db")
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO cache_api_football (
                        chave, categoria, armazenado_em, dados_json
                    ) VALUES ('outro_antigo', 'eventos', 1001, '[]')
                    """
                )
        finally:
            banco.fechar()

        self.assertTrue(api._salvar_cache_persistente(
            "novo_2", "geral", [], armazenado_em=1100.0
        ))
        self.assertEqual(api.cache_persistente_limpezas, 1)

        self.assertTrue(api._salvar_cache_persistente(
            "novo_3", "geral", [], armazenado_em=1301.0
        ))
        self.assertEqual(api.cache_persistente_limpezas, 2)
        self.assertGreaterEqual(api.cache_persistente_descartes, 2)

    def test_estrutura_apenas_asiatico_1t_com_over_e_under(self):
        item = {
            "fixture": {"id": 123},
            "odds": [{
                "id": 51,
                "name": "Asian Corners (1st Half)",
                "values": [
                    {"value": "Over", "odd": "1.82", "handicap": "4.5"},
                    {"value": "Under", "odd": "1.91", "handicap": "4.5"},
                    {"value": "Exactly", "odd": "5", "handicap": "4.5"},
                ],
            }],
        }

        mercado = estruturar_escanteios_asiaticos_1t_api(item, 12.4)

        periodo = mercado["ofertas_periodos"]["1T"]
        self.assertEqual(periodo["formato"], "duas_opcoes")
        self.assertEqual(len(periodo["ofertas"]), 1)
        self.assertEqual(periodo["ofertas"][0]["linha"], 4.5)
        self.assertEqual(periodo["ofertas"][0]["over"], 1.82)
        self.assertEqual(periodo["ofertas"][0]["under"], 1.91)
        self.assertEqual(periodo["ofertas"][0]["fonte"], "api_football")
        self.assertEqual(periodo["ofertas"][0]["idade_segundos"], 12.4)

    def test_estrutura_asiatico_ft_sem_confundir_com_exactly(self):
        item = {
            "fixture": {"id": 123},
            "odds": [{
                "id": 32,
                "name": "Asian Corners",
                "values": [
                    {"value": "Over", "odd": "1.84", "handicap": "8.5"},
                    {"value": "Under", "odd": "1.96", "handicap": "8.5"},
                    {"value": "Exactly", "odd": "4.5", "handicap": "8.5"},
                ],
            }],
        }

        mercado = estruturar_escanteios_asiaticos_ft_api(item, 8.2)

        self.assertEqual(mercado["formato"], "duas_opcoes")
        self.assertEqual(mercado["ofertas_periodos"], {})
        self.assertEqual(len(mercado["ofertas"]), 1)
        self.assertEqual(mercado["ofertas"][0]["linha"], 8.5)
        self.assertEqual(mercado["ofertas"][0]["over"], 1.84)
        self.assertEqual(mercado["ofertas"][0]["under"], 1.96)
        self.assertEqual(mercado["ofertas"][0]["idade_segundos"], 8.2)

    def test_rejeita_odd_suspensa_bloqueada_ou_sem_par(self):
        base = {
            "odds": [{
                "id": 51,
                "name": "Asian Corners (1st Half)",
                "values": [
                    {"value": "Over", "odd": "1.8", "handicap": "4.5"},
                    {
                        "value": "Under", "odd": "2.0", "handicap": "4.5",
                        "suspended": True,
                    },
                ],
            }],
        }
        self.assertIsNone(estruturar_escanteios_asiaticos_1t_api(base))
        bloqueada = dict(base, blocked=True)
        self.assertIsNone(
            estruturar_escanteios_asiaticos_1t_api(bloqueada)
        )
        bloqueada_aninhada = dict(base, status={"blocked": True})
        mercado, motivo = diagnosticar_escanteios_asiaticos_1t_api(
            bloqueada_aninhada
        )
        self.assertIsNone(mercado)
        self.assertEqual(motivo, "fixture_bloqueada")

    def test_estrutura_total_gols_da_api_com_linha_e_fonte(self):
        item = {
            "odds": [{
                "id": 25,
                "name": "Match Goals",
                "values": [
                    {"value": "Over", "odd": "1.82", "handicap": "2.5"},
                    {"value": "Under", "odd": "1.98", "handicap": "2.5"},
                ],
            }],
        }

        mercado = estruturar_gols_total_api(item, idade_segundos=7.5)

        self.assertEqual(mercado["categoria"], "gols")
        self.assertEqual(mercado["escopo"], "total")
        self.assertEqual(mercado["tipo_mercado"], "total")
        self.assertEqual(mercado["fonte"], "api_football")
        self.assertEqual(mercado["ofertas"][0]["linha"], 2.5)
        self.assertEqual(mercado["ofertas"][0]["idade_segundos"], 7.5)

    def test_estrutura_total_gols_ht_na_colecao_correta(self):
        item = {
            "odds": [{
                "id": 49,
                "name": "Over/Under (1st Half)",
                "values": [
                    {"value": "Over", "odd": "1.44", "handicap": "0.5"},
                    {"value": "Under", "odd": "2.70", "handicap": "0.5"},
                ],
            }],
        }

        mercado = estruturar_gols_total_ht_api(item, idade_segundos=4.0)

        self.assertEqual(mercado["categoria"], "gols")
        self.assertEqual(mercado["periodo"], "1T")
        self.assertEqual(mercado["ofertas"], [])
        self.assertEqual(mercado["ofertas_ht"][0]["linha"], 0.5)
        self.assertEqual(mercado["ofertas_ht"][0]["over"], 1.44)
        self.assertEqual(mercado["ofertas_ht"][0]["idade_segundos"], 4.0)
        diagnosticado, motivo = diagnosticar_gols_total_ht_api(item, 4.0)
        self.assertIsNone(motivo)
        self.assertEqual(diagnosticado["fonte"], "api_football")

    def test_estrutura_proximo_gol_com_tres_selecoes(self):
        item = {
            "odds": [{
                "id": 73,
                "name": "Which team will score the 1st goal?",
                "values": [
                    {"value": "Home", "odd": "1.9"},
                    {"value": "Away", "odd": "2.4"},
                    {"value": "No Goal", "odd": "4.2"},
                ],
            }],
        }

        mercado, motivo = diagnosticar_proximo_gol_api(
            item, 73, "Which team will score the 1st goal?", 3.0
        )

        self.assertIsNone(motivo)
        self.assertEqual(mercado["escopo"], "proximo")
        self.assertEqual(
            mercado["selecoes"],
            {"casa": 1.9, "visitante": 2.4, "sem_gol": 4.2},
        )
        self.assertEqual(mercado["idade_segundos"], 3.0)

    def test_proximo_gol_rejeita_selecao_incompleta(self):
        mercado, motivo = diagnosticar_proximo_gol_api(
            {
                "odds": [{
                    "id": 73,
                    "name": "Which team will score the 1st goal?",
                    "values": [
                        {"value": "Home", "odd": "1.9"},
                        {"value": "Away", "odd": "2.4"},
                    ],
                }],
            },
            73,
            "Which team will score the 1st goal?",
        )

        self.assertIsNone(mercado)
        self.assertEqual(motivo, "selecoes_incompletas_ou_suspensas")

    def test_odds_gols_e_proximo_gol_usam_bets_corretos(self):
        api = APIFootball(self.pasta)
        total = {
            "response": [{
                "fixture": {"id": 123},
                "odds": [{
                    "id": 25,
                    "name": "Match Goals",
                    "values": [
                        {"value": "Over", "odd": "1.8", "handicap": "2.5"},
                        {"value": "Under", "odd": "2", "handicap": "2.5"},
                    ],
                }],
            }],
        }
        proximo = {
            "response": [{
                "fixture": {"id": 123},
                "odds": [{
                    "id": 84,
                    "name": "Which team will score the 2nd goal?",
                    "values": [
                        {"value": "Home", "odd": "1.9"},
                        {"value": "Away", "odd": "2.4"},
                        {"value": "No Goal", "odd": "4.2"},
                    ],
                }],
            }],
        }
        total_ht = {
            "response": [{
                "fixture": {"id": 123},
                "odds": [{
                    "id": 49,
                    "name": "Over/Under (1st Half)",
                    "values": [
                        {"value": "Over", "odd": "1.44", "handicap": "0.5"},
                        {"value": "Under", "odd": "2.7", "handicap": "0.5"},
                    ],
                }],
            }],
        }
        with patch.object(
            api, "_get", side_effect=(total, total_ht, proximo)
        ) as requisicao:
            mercado_total = api.odds_gols_total_ft(123)
            mercado_total_ht = api.odds_gols_total_ht(123)
            mercado_proximo = api.odds_proximo_gol(123, 1)

        self.assertIsNotNone(mercado_total)
        self.assertIsNotNone(mercado_total_ht)
        self.assertIsNotNone(mercado_proximo)
        self.assertEqual(
            requisicao.call_args_list[0].args,
            ("/odds/live", {"bet": 25}, "odds"),
        )
        self.assertEqual(
            requisicao.call_args_list[1].args,
            ("/odds/live", {"bet": 49}, "odds"),
        )
        self.assertEqual(
            requisicao.call_args_list[2].args,
            ("/odds/live", {"bet": 84}, "odds"),
        )
        self.assertIsNone(api.odds_proximo_gol(123, 7))

    def test_referencia_independente_exclui_bet365_sem_escolher_maior_odd(self):
        api = APIFootball(self.pasta)

        def bookmaker(nome, over, under):
            return {
                "name": nome,
                "bets": [{
                    "id": 25,
                    "name": "Match Goals",
                    "values": [
                        {"value": "Over", "odd": str(over),
                         "handicap": "2.5"},
                        {"value": "Under", "odd": str(under),
                         "handicap": "2.5"},
                    ],
                }],
            }

        item = {
            "fixture": {"id": 123},
            "bookmakers": [
                bookmaker("Bet365", 1.80, 2.00),
                bookmaker("Pinnacle", 2.10, 1.75),
                bookmaker("1xBet", 1.90, 1.90),
            ],
        }
        with patch.object(
            api,
            "_carregar_itens_odds_ao_vivo",
            return_value=([item], 2.0),
        ) as carregar:
            mercados, diagnostico = api.odds_referencia_independente(
                123, "gol_ft", bookmaker_excluido="bet365"
            )

        carregar.assert_called_once_with(25)
        self.assertEqual(
            ["1xBet", "Pinnacle"],
            [mercado["bookmaker"] for mercado in mercados],
        )
        self.assertNotIn(
            "Bet365", diagnostico["bookmakers_independentes"]
        )
        self.assertEqual(
            "referencias_independentes_disponiveis",
            diagnostico["motivo"],
        )
        self.assertFalse(diagnostico["aplicacao_sinais"])
        self.assertFalse(diagnostico["telegram"])

    def test_capacidade_sem_identidade_suprime_consulta_e_reabre_por_sondagem(self):
        resposta_sem_identidade = {
            "response": [{
                "fixture": {"id": 123},
                "odds": [{
                    "id": 25,
                    "name": "Match Goals",
                    "values": [
                        {"value": "Over", "odd": "1.8",
                         "handicap": "2.5"},
                        {"value": "Under", "odd": "2.0",
                         "handicap": "2.5"},
                    ],
                }],
            }],
        }
        api = APIFootball(self.pasta)
        with patch.object(
            api, "_get", return_value=resposta_sem_identidade
        ) as requisicao:
            mercados, primeiro = api.odds_referencia_independente(
                123, "gol_ft"
            )

        self.assertEqual([], mercados)
        self.assertEqual(
            "fonte_live_sem_identidade_bookmaker", primeiro["motivo"]
        )
        self.assertTrue(primeiro["consulta_rede_realizada"])
        self.assertFalse(primeiro["consulta_rede_evitada"])
        requisicao.assert_called_once()
        estado = verificar_capacidade_referencia_api(
            self.pasta / "api_football_referencia_capacidade_estado.json"
        )
        self.assertTrue(estado["saudavel"])
        self.assertFalse(
            estado["por_bet"]["25"][
                "identidade_bookmaker_disponivel"
            ]
        )

        reiniciado = APIFootball(self.pasta)
        with patch.object(reiniciado, "_get") as requisicao:
            mercados, suprimido = reiniciado.odds_referencia_independente(
                123, "gol_ft"
            )

        self.assertEqual([], mercados)
        requisicao.assert_not_called()
        self.assertTrue(suprimido["consulta_rede_evitada"])
        self.assertFalse(suprimido["consulta_rede_realizada"])
        self.assertEqual(
            "fonte_live_sem_identidade_bookmaker", suprimido["motivo"]
        )

        bookmaker = {
            "name": "Pinnacle",
            "bets": [{
                "id": 25,
                "name": "Match Goals",
                "values": [
                    {"value": "Over", "odd": "1.91",
                     "handicap": "2.5"},
                    {"value": "Under", "odd": "1.93",
                     "handicap": "2.5"},
                ],
            }],
        }
        resposta_com_identidade = {
            "response": [{
                "fixture": {"id": 123},
                "bookmakers": [bookmaker],
            }],
        }
        sondagem = APIFootball(self.pasta)
        with patch.dict(
            os.environ,
            {"API_FOOTBALL_REFERENCIA_FORCAR_SONDAGEM": "1"},
        ), patch.object(
            sondagem, "_get", return_value=resposta_com_identidade
        ) as requisicao:
            mercados, recuperado = sondagem.odds_referencia_independente(
                123, "gol_ft"
            )

        requisicao.assert_called_once()
        self.assertEqual(["Pinnacle"], [
            mercado["bookmaker"] for mercado in mercados
        ])
        self.assertEqual(
            "referencias_independentes_disponiveis", recuperado["motivo"]
        )
        self.assertTrue(
            recuperado["capacidade_referencia"][
                "identidade_bookmaker_disponivel"
            ]
        )

    def test_diagnostico_capacidade_nao_confunde_odd_agregada_com_bookmaker(self):
        diagnostico = diagnosticar_capacidade_referencia_payload([{
            "fixture": {"id": 1},
            "odds": [{"id": 25, "name": "Match Goals"}],
        }])

        self.assertEqual(1, diagnostico["fixtures"])
        self.assertEqual(0, diagnostico["fixtures_com_bookmakers"])
        self.assertFalse(diagnostico["identidade_bookmaker_disponivel"])
        self.assertFalse(diagnostico["referencia_independente_possivel"])

    def test_odds_1t_filtram_fixture_e_compartilham_cache_global(self):
        api = APIFootball(self.pasta)
        resposta = {
            "response": [{
                "fixture": {"id": 123},
                "odds": [{
                    "id": 51,
                    "name": "Asian Corners (1st Half)",
                    "values": [
                        {"value": "Over", "odd": "1.8", "handicap": "3.5"},
                        {"value": "Under", "odd": "2", "handicap": "3.5"},
                    ],
                }],
            }],
        }
        with patch.object(api, "_get", return_value=resposta) as requisicao:
            encontrada = api.odds_escanteios_asiaticos_1t(123)
            ausente = api.odds_escanteios_asiaticos_1t(999)

        self.assertIsNotNone(encontrada)
        self.assertIsNone(ausente)
        requisicao.assert_called_once_with(
            "/odds/live", {"bet": 51}, "odds"
        )
        estado = verificar_estado_odds_api(
            self.pasta / "api_football_odds_estado.json"
        )
        self.assertEqual(estado["consultas"], 1)
        self.assertEqual(estado["com_ofertas_globais"], 1)
        self.assertEqual(estado["sem_ofertas_globais"], 0)
        self.assertEqual(estado["falhas"], 0)
        bet = estado["por_bet"]["51"]
        self.assertEqual(bet["consultas"], 1)
        self.assertEqual(bet["solicitacoes_fixture"], 2)
        self.assertEqual(bet["fixtures_correspondentes"], 1)
        self.assertEqual(bet["ofertas_anexadas"], 1)
        self.assertEqual(bet["ofertas_rejeitadas"], 0)

    def test_odds_ft_usam_bet_32_e_cache_separado_do_1t(self):
        api = APIFootball(self.pasta)
        resposta_ft = {
            "response": [{
                "fixture": {"id": 123},
                "odds": [{
                    "id": 32,
                    "name": "Asian Corners",
                    "values": [
                        {"value": "Over", "odd": "1.8", "handicap": "8.5"},
                        {"value": "Under", "odd": "2", "handicap": "8.5"},
                    ],
                }],
            }],
        }
        with patch.object(api, "_get", return_value=resposta_ft) as requisicao:
            encontrada = api.odds_escanteios_asiaticos_ft(123)
            repetida = api.odds_escanteios_asiaticos_ft(123)

        self.assertIsNotNone(encontrada)
        self.assertIsNotNone(repetida)
        requisicao.assert_called_once_with(
            "/odds/live", {"bet": 32}, "odds"
        )
        estado = verificar_estado_odds_api(
            self.pasta / "api_football_odds_estado.json"
        )
        self.assertEqual(estado["ultimo_bet_id"], 32)
        self.assertEqual(
            estado["bet_ids"], sorted(MERCADOS_ODDS_LIVE_ESPERADOS)
        )
        bet = estado["por_bet"]["32"]
        self.assertEqual(bet["consultas"], 1)
        self.assertEqual(bet["solicitacoes_fixture"], 2)
        self.assertEqual(bet["fixtures_correspondentes"], 2)
        self.assertEqual(bet["ofertas_anexadas"], 2)

    def test_lista_fixtures_asiatico_ft_filtra_ofertas_e_reusa_cache(self):
        api = APIFootball(self.pasta)
        resposta = {
            "response": [
                {
                    "fixture": {"id": 123},
                    "odds": [{
                        "id": 32,
                        "name": "Asian Corners",
                        "values": [
                            {"value": "Over", "odd": "1.8", "handicap": "8.5"},
                            {"value": "Under", "odd": "2", "handicap": "8.5"},
                        ],
                    }],
                },
                {
                    "fixture": {"id": 456},
                    "odds": [{
                        "id": 32,
                        "name": "Asian Corners",
                        "values": [
                            {"value": "Over", "odd": "1.9", "handicap": "9.5"},
                        ],
                    }],
                },
            ],
        }
        with patch.object(api, "_get", return_value=resposta) as requisicao:
            ofertas = api.ofertas_escanteios_asiaticos_ft_por_fixture()
            fixtures = api.fixtures_com_odds_escanteios_asiaticos_ft()
            mercado = api.odds_escanteios_asiaticos_ft(123)

        self.assertEqual(ofertas[123]["linha"], 8.5)
        self.assertEqual(ofertas[123]["over"], 1.8)
        self.assertEqual(fixtures, {123})
        self.assertIsNotNone(mercado)
        requisicao.assert_called_once_with(
            "/odds/live", {"bet": 32}, "odds"
        )

    def test_fixture_com_oferta_invalida_e_contada_como_rejeitada(self):
        api = APIFootball(self.pasta)
        resposta = {
            "response": [{
                "fixture": {"id": 123},
                "odds": [{
                    "id": 51,
                    "name": "Asian Corners (1st Half)",
                    "values": [
                        {"value": "Over", "odd": "1.8", "handicap": "3.5"},
                        {
                            "value": "Under", "odd": "2",
                            "handicap": "3.5", "suspended": True,
                        },
                    ],
                }],
            }],
        }
        with patch.object(api, "_get", return_value=resposta):
            mercado = api.odds_escanteios_asiaticos_1t(123)

        self.assertIsNone(mercado)
        estado = verificar_estado_odds_api(
            self.pasta / "api_football_odds_estado.json"
        )
        bet = estado["por_bet"]["51"]
        self.assertEqual(bet["fixtures_correspondentes"], 1)
        self.assertEqual(bet["ofertas_anexadas"], 0)
        self.assertEqual(bet["ofertas_rejeitadas"], 1)
        self.assertEqual(bet["rejeicoes_sem_diagnostico"], 0)
        self.assertEqual(
            bet["rejeicoes_por_motivo"],
            {"over_under_incompleto_ou_suspenso": 1},
        )
        self.assertEqual(
            bet["ultimo_motivo_rejeicao"],
            "over_under_incompleto_ou_suspenso",
        )

    def test_fixture_bloqueada_em_status_registra_motivo(self):
        api = APIFootball(self.pasta)
        resposta = {
            "response": [{
                "fixture": {"id": 123},
                "status": {"blocked": True},
                "odds": [{
                    "id": 32,
                    "name": "Asian Corners",
                    "values": [
                        {"value": "Over", "odd": "1.8", "handicap": "8.5"},
                        {"value": "Under", "odd": "2", "handicap": "8.5"},
                    ],
                }],
            }],
        }
        with patch.object(api, "_get", return_value=resposta):
            mercado = api.odds_escanteios_asiaticos_ft(123)

        self.assertIsNone(mercado)
        estado = verificar_estado_odds_api(
            self.pasta / "api_football_odds_estado.json"
        )
        bet = estado["por_bet"]["32"]
        self.assertEqual(bet["ofertas_rejeitadas"], 1)
        self.assertEqual(bet["rejeicoes_por_motivo"], {"fixture_bloqueada": 1})
        self.assertEqual(bet["rejeicoes_sem_diagnostico"], 0)

    def test_estado_odds_distingue_resposta_vazia_de_falha(self):
        api = APIFootball(self.pasta)
        with patch.object(
            api, "_get", side_effect=({"response": []}, None)
        ):
            api.odds_escanteios_asiaticos_1t(123)
            api.cache_odds_ao_vivo.clear()
            api.odds_escanteios_asiaticos_1t(123)

        estado = verificar_estado_odds_api(
            self.pasta / "api_football_odds_estado.json"
        )
        self.assertEqual(estado["consultas"], 2)
        self.assertEqual(estado["sem_ofertas_globais"], 1)
        self.assertEqual(estado["falhas"], 1)

    @patch.dict(
        os.environ,
        {
            "API_ODDS_1T_LIMITE_VAZIAS_CONSECUTIVAS": "2",
            "API_ODDS_1T_SUSPENSAO_SEGUNDOS": "3600",
        },
    )
    def test_suspende_temporariamente_odds_1t_sem_oferta_repetida(self):
        api = APIFootball(self.pasta)
        vazio = {"response": []}
        api._registrar_consulta_odds(vazio, 51)
        api._registrar_consulta_odds(vazio, 51)
        api.cache_odds_ao_vivo.clear()

        with patch.object(
            api, "_ler_cache_persistente", return_value=None
        ), patch.object(api, "_get") as requisicao:
            mercado = api.odds_escanteios_asiaticos_1t(123)

        self.assertIsNone(mercado)
        requisicao.assert_not_called()
        estado = verificar_estado_odds_api(
            self.pasta / "api_football_odds_estado.json"
        )
        bet = estado["por_bet"]["51"]
        self.assertEqual(bet["sem_ofertas_consecutivas"], 2)
        self.assertEqual(bet["suspensoes"], 1)
        self.assertEqual(bet["consultas_suprimidas"], 1)
        self.assertIsNotNone(bet["suspenso_ate"])

    @patch.dict(
        os.environ,
        {"API_ODDS_1T_LIMITE_VAZIAS_CONSECUTIVAS": "2"},
    )
    def test_oferta_1t_recuperada_remove_suspensao_adaptativa(self):
        api = APIFootball(self.pasta)
        api._registrar_consulta_odds({"response": []}, 51)
        api._registrar_consulta_odds({"response": []}, 51)
        api._registrar_consulta_odds(
            {"response": [{"fixture": {"id": 123}}]}, 51
        )

        bet = api.estado_odds["por_bet"]["51"]
        self.assertEqual(bet["sem_ofertas_consecutivas"], 0)
        self.assertIsNone(bet["suspenso_ate"])

    def test_estado_odds_corrompido_e_detectado(self):
        caminho = self.pasta / "api_football_odds_estado.json"
        caminho.write_text('{"consultas": -1}', encoding="utf-8")

        estado = verificar_estado_odds_api(caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["estado"], "corrompido")

    def test_estado_odds_antigo_e_migrado_sem_perder_contadores(self):
        caminho = self.pasta / "api_football_odds_estado.json"
        caminho.write_text(json.dumps({
            "versao": 1,
            "bet_id": 51,
            "consultas": 9,
            "com_ofertas_globais": 2,
            "sem_ofertas_globais": 6,
            "falhas": 1,
            "ultima_consulta_em": "2026-07-21T19:00:00",
            "ultima_oferta_em": "2026-07-21T18:00:00",
            "ultimo_total_fixtures": 0,
        }), encoding="utf-8")

        estado = verificar_estado_odds_api(caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["consultas"], 9)
        self.assertEqual(
            estado["bet_ids"], sorted(MERCADOS_ODDS_LIVE_ESPERADOS)
        )
        self.assertIsNone(estado["ultimo_bet_id"])
        self.assertEqual(estado["por_bet"]["32"]["consultas"], 0)
        self.assertEqual(estado["por_bet"]["51"]["consultas"], 0)

    def test_estado_odds_recusa_contador_negativo_por_bet(self):
        caminho = self.pasta / "api_football_odds_estado.json"
        caminho.write_text(json.dumps({
            "consultas": 1,
            "com_ofertas_globais": 0,
            "sem_ofertas_globais": 1,
            "falhas": 0,
            "por_bet": {"51": {"ofertas_anexadas": -1}},
        }), encoding="utf-8")

        estado = verificar_estado_odds_api(caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["estado"], "corrompido")

    def test_estado_odds_recusa_motivo_com_contador_negativo(self):
        caminho = self.pasta / "api_football_odds_estado.json"
        caminho.write_text(json.dumps({
            "consultas": 1,
            "com_ofertas_globais": 1,
            "sem_ofertas_globais": 0,
            "falhas": 0,
            "por_bet": {
                "32": {"rejeicoes_por_motivo": {"mercado_ausente": -1}}
            },
        }), encoding="utf-8")

        estado = verificar_estado_odds_api(caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["estado"], "corrompido")

    def test_estado_odds_recusa_motivos_acima_do_total(self):
        caminho = self.pasta / "api_football_odds_estado.json"
        caminho.write_text(json.dumps({
            "consultas": 1,
            "com_ofertas_globais": 1,
            "sem_ofertas_globais": 0,
            "falhas": 0,
            "por_bet": {"32": {
                "ofertas_rejeitadas": 1,
                "rejeicoes_por_motivo": {"mercado_ausente": 2},
                "ultimo_motivo_rejeicao": "mercado_ausente",
            }},
        }), encoding="utf-8")

        estado = verificar_estado_odds_api(caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["estado"], "corrompido")

    def test_estado_odds_preserva_rejeicao_legada_sem_inventar_motivo(self):
        caminho = self.pasta / "api_football_odds_estado.json"
        caminho.write_text(json.dumps({
            "consultas": 1,
            "com_ofertas_globais": 1,
            "sem_ofertas_globais": 0,
            "falhas": 0,
            "por_bet": {"32": {"ofertas_rejeitadas": 1}},
        }), encoding="utf-8")

        estado = verificar_estado_odds_api(caminho)

        self.assertTrue(estado["saudavel"])
        bet = estado["por_bet"]["32"]
        self.assertEqual(bet["rejeicoes_sem_diagnostico"], 1)
        self.assertEqual(bet["rejeicoes_por_motivo"], {})
        self.assertIsNone(bet["ultimo_motivo_rejeicao"])

    def test_associa_com_placar_e_minuto_compativeis(self):
        jogo = {
            "mandante": "Clube Atletico Norte",
            "visitante": "Esporte Clube Sul",
            "placar": "1-0",
            "status": "54 '",
        }
        associado = associar_jogo(jogo, [fixture()])
        self.assertEqual(associado["fixture_id"], 10)
        self.assertEqual(associado["orientacao"], "direta")
        self.assertEqual(associado["placar"], [1, 0])

    def test_corrige_orientacao_invertida(self):
        jogo = {
            "mandante": "Esporte Clube Sul",
            "visitante": "Clube Atletico Norte",
            "placar": "0-1",
            "status": "55 '",
        }
        associado = associar_jogo(jogo, [fixture()])
        self.assertEqual(associado["orientacao"], "invertida")
        self.assertEqual(associado["placar"], [0, 1])
        self.assertEqual(
            associado["times"]["home"]["name"], "Esporte Clube Sul"
        )

    def test_rejeita_nome_ou_minuto_incompativel(self):
        jogo = {
            "mandante": "Time Totalmente Diferente",
            "visitante": "Outro Time",
            "placar": "0-0",
            "status": "10 '",
        }
        self.assertIsNone(associar_jogo(jogo, [fixture()]))
        jogo.update(
            {
                "mandante": "Clube Atletico Norte",
                "visitante": "Esporte Clube Sul",
            }
        )
        self.assertIsNone(associar_jogo(jogo, [fixture(minuto=55)]))

    def test_rejeita_categoria_de_base_contra_sub_23(self):
        jogo = {
            "mandante": "Magic United U23",
            "visitante": "Olympic U23",
            "placar": "0-0",
            "status": "3 '",
        }
        candidato = fixture(
            casa="Magic United", fora="Olympic", minuto=3
        )

        diagnostico = diagnosticar_associacao(jogo, [candidato])

        self.assertIsNone(diagnostico["associacao"])
        self.assertEqual(
            diagnostico["motivo"], "categoria_equipes_incompativel"
        )
        self.assertEqual(diagnostico["rejeicoes_categoria"], 1)

    def test_permite_alias_dentro_da_mesma_categoria_sub_20(self):
        jogo = {
            "mandante": "Blacktown City U20",
            "visitante": "Sydney U20",
            "placar": "0-0",
            "status": "3 '",
        }
        candidato = fixture(
            casa="Blacktown City U20", fora="Sydney FC U20", minuto=3
        )

        associado = associar_jogo(jogo, [candidato])

        self.assertIsNotNone(associado)
        self.assertEqual(associado["fixture_id"], 10)

    def test_permite_siglas_explicitas_bate_e_mvv(self):
        casos = [
            (
                {
                    "mandante": "Baranovichi",
                    "visitante": "BATE",
                    "placar": "1-1",
                    "status": "67 '",
                },
                fixture(
                    fixture_id=1525935,
                    casa="Baranovichi",
                    fora="Bate Borisov",
                    placar=(1, 1),
                    minuto=67,
                ),
            ),
            (
                {
                    "mandante": "MVV Maastricht",
                    "visitante": "Jong FC Utrecht",
                    "placar": "1-1",
                    "status": "27 '",
                },
                fixture(
                    fixture_id=1551743,
                    casa="MVV",
                    fora="Jong Utrecht",
                    placar=(1, 1),
                    minuto=27,
                ),
            ),
        ]

        for jogo, candidato in casos:
            with self.subTest(jogo=jogo["mandante"]):
                associado = associar_jogo(jogo, [candidato])
                self.assertIsNotNone(associado)
                self.assertEqual(
                    associado["fixture_id"],
                    candidato["fixture"]["id"],
                )

    def test_nao_trata_palavra_comum_como_sigla_de_clube(self):
        jogo = {
            "mandante": "United",
            "visitante": "Rangers",
            "placar": "0-0",
            "status": "20 '",
        }
        candidato = fixture(
            casa="Manchester United",
            fora="Queens Park Rangers",
            placar=(0, 0),
            minuto=20,
        )

        diagnostico = diagnosticar_associacao(jogo, [candidato])

        self.assertIsNone(diagnostico["associacao"])
        self.assertEqual(diagnostico["motivo"], "nomes_incompativeis")

    def test_diagnostico_expoe_candidatos_sem_aprova_los(self):
        jogo = {
            "mandante": "Time Totalmente Diferente",
            "visitante": "Outro Time",
            "placar": "0-0",
            "status": "10 '",
        }
        candidato = fixture(
            fixture_id=99,
            casa="Time X",
            fora="Time Y",
            placar=(0, 0),
            minuto=10,
        )

        diagnostico = diagnosticar_associacao(jogo, [candidato])

        self.assertIsNone(diagnostico["associacao"])
        self.assertEqual(
            diagnostico["melhores_candidatos_nomes"][0]["fixture_id"],
            99,
        )
        self.assertIn(
            "nota_nomes", diagnostico["melhores_candidatos_nomes"][0]
        )

    def test_rejeita_time_feminino_contra_time_principal(self):
        jogo = {
            "mandante": "Western Springs W",
            "visitante": "West Coast Rangers W",
            "placar": "0-0",
            "status": "3 '",
        }
        candidato = fixture(
            casa="Western Springs", fora="West Coast Rangers", minuto=3
        )

        diagnostico = diagnosticar_associacao(jogo, [candidato])

        self.assertIsNone(diagnostico["associacao"])
        self.assertEqual(
            diagnostico["motivo"], "categoria_equipes_incompativel"
        )

    def test_rejeita_duas_fixtures_igualmente_compativeis(self):
        jogo = {
            "mandante": "Clube Atletico Norte",
            "visitante": "Esporte Clube Sul",
            "placar": "1-0",
            "status": "55 '",
        }
        primeira = fixture(fixture_id=10)
        segunda = fixture(fixture_id=11)

        self.assertIsNone(associar_jogo(jogo, [primeira, segunda]))
        diagnostico = diagnosticar_associacao(
            jogo, [primeira, segunda]
        )
        self.assertEqual(diagnostico["motivo"], "associacao_ambigua")
        self.assertEqual(diagnostico["candidatos_compativeis"], 2)

    def test_diagnostico_distingue_nome_e_minuto_incompativeis(self):
        jogo = {
            "mandante": "Clube Atletico Norte",
            "visitante": "Esporte Clube Sul",
            "placar": "0-0",
            "status": "10 '",
        }
        nomes = diagnosticar_associacao(
            jogo,
            [fixture(casa="Time X", fora="Time Y", minuto=10)],
        )
        minuto = diagnosticar_associacao(jogo, [fixture(minuto=55)])

        self.assertEqual(nomes["motivo"], "nomes_incompativeis")
        self.assertEqual(minuto["motivo"], "minuto_incompativel")

    def test_fixture_duplicada_na_resposta_nao_cria_falsa_ambiguidade(self):
        jogo = {
            "mandante": "Clube Atletico Norte",
            "visitante": "Esporte Clube Sul",
            "placar": "1-0",
            "status": "55 '",
        }
        duplicada = fixture(fixture_id=10)

        associado = associar_jogo(jogo, [duplicada, dict(duplicada)])

        self.assertEqual(associado["fixture_id"], 10)
        self.assertEqual(associado["candidatos_compativeis"], 1)
        self.assertIsNone(associado["margem_associacao"])


if __name__ == "__main__":
    unittest.main()
