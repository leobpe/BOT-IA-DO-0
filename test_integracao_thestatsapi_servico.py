import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from banco import BancoMonitor
from configuracao import validar_configuracao
from observabilidade import Observabilidade
from servico_monitor import ServicoMonitor
from status_bot import (
    descrever_historico_api_live,
    descrever_thestatsapi_sombra,
)


def _jogo(numero):
    return {
        "url": f"https://packball.com/match/{numero}/live",
        "mandante": f"Casa {numero}",
        "visitante": f"Fora {numero}",
        "placar": "0-0",
        "status": "35 '",
    }


def _partida_api(numero):
    return {
        "id": f"mt_{numero}",
        "home_team": {"id": f"h{numero}", "name": f"Casa {numero}"},
        "away_team": {"id": f"a{numero}", "name": f"Fora {numero}"},
        "score": {"home": 0, "away": 0},
        "status": "first_half",
        "elapsed_minutes": 35,
    }


class TheStatsAPIFalsa:
    disponivel = True

    def __init__(self, quantidade=3, falhar_lista=False, falhar_detalhes=False):
        self.quantidade = quantidade
        self.falhar_lista = falhar_lista
        self.falhar_detalhes = falhar_detalhes
        self.chamadas = 0
        self.lista_chamadas = 0
        self.stats_ids = []
        self.odds_ids = []
        self._trava = threading.Lock()

    def _contar(self):
        with self._trava:
            self.chamadas += 1

    def consumo_atual(self):
        with self._trava:
            return {
                "usado_local_dia": self.chamadas,
                "restante_local_seguro": max(2250 - self.chamadas, 0),
                "limite_local_minuto": 25,
                "chamadas_ultimo_minuto": self.chamadas,
                "contador_saudavel": True,
                "provedor": {"restante": 30},
            }

    def jogos_ao_vivo(self, **_):
        self._contar()
        self.lista_chamadas += 1
        if self.falhar_lista:
            raise TimeoutError("falha isolada")
        return {
            "ok": True,
            "dados": [
                _partida_api(numero)
                for numero in range(1, self.quantidade + 1)
            ],
            "cache": False,
            "origem": "rede",
        }

    def estatisticas_ao_vivo(self, match_id):
        self._contar()
        self.stats_ids.append(match_id)
        if self.falhar_detalhes:
            return {
                "ok": False,
                "erro": {"codigo": "timeout"},
                "cache": False,
            }
        return {
            "ok": True,
            "dados": {
                "match_id": match_id,
                "meta": {
                    "elapsed_minutes": 35,
                    "match_status": "first_half",
                    "home_goals": 0,
                    "away_goals": 0,
                },
                "stats": {
                    "total_shots": {"home": 8, "away": 5},
                    "shots_on_target": {"home": 3, "away": 2},
                    "corner_kicks": {"home": 4, "away": 2},
                    "expected_goals": {"home": 0.8, "away": 0.4},
                },
            },
            "cache": False,
            "origem": "rede",
        }

    def odds_ao_vivo(self, match_id):
        self._contar()
        self.odds_ids.append(match_id)
        if self.falhar_detalhes:
            return {
                "ok": False,
                "erro": {"codigo": "erro_provedor"},
                "cache": False,
            }
        return {
            "ok": True,
            "dados": {
                "match_id": match_id,
                "bookmakers": [{
                    "bookmaker": "Bet365",
                    "markets": {
                        "Total Corners": {
                            "8": {
                                "over": {"live": 1.85},
                                "under": {"live": 1.95},
                            }
                        }
                    },
                }],
            },
            "cache": False,
            "origem": "rede",
        }


class IntegracaoTheStatsAPIServicoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_thestatsapi_servico.db"
        self.log = Path.cwd() / ".teste_thestatsapi_servico.jsonl"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        if self.log.exists():
            self.log.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.servico = object.__new__(ServicoMonitor)
        self.servico.banco = self.banco
        self.servico.thestatsapi_sombra_ativa = True
        self.servico.thestatsapi_max_jogos_ciclo = 2
        self.servico._thestatsapi_selecoes = {}
        self.servico._thestatsapi_selecoes_stats = {}
        self.servico._thestatsapi_selecoes_odds = {}
        self.servico._operacao_bloqueada_ciclo = False

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        if self.log.exists():
            self.log.unlink()

    @staticmethod
    def _tarefas(jogos):
        return [
            {
                "jogo": jogo,
                "em_foco": indice == 0,
                "rechecagem_pos_evento": False,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            }
            for indice, jogo in enumerate(jogos)
        ]

    def test_acompanha_todos_os_jogos_cobertos_quando_ha_capacidade(self):
        jogos = [_jogo(numero) for numero in range(1, 4)]
        self.servico.thestatsapi = TheStatsAPIFalsa(3)
        self.servico.thestatsapi_max_jogos_ciclo = 20

        resumo = self.servico._executar_thestatsapi_sombra(
            jogos,
            self._tarefas(jogos),
            {jogos[0]["url"]: 90, jogos[1]["url"]: 80},
        )

        self.assertEqual(self.servico.thestatsapi.lista_chamadas, 1)
        self.assertEqual(self.servico.thestatsapi.chamadas, 7)
        self.assertEqual(resumo["chamadas_rede"], 7)
        self.assertEqual(resumo["jogos_consultados"], 3)
        self.assertEqual(resumo["pareamentos"]["associados"], 3)
        self.assertEqual(resumo["stats"]["persistidos"], 3)
        self.assertEqual(resumo["odds"]["jogos_com_ofertas"], 3)
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["telegram"])
        self.assertFalse(resumo["calibracao"])
        self.assertFalse(resumo["substitui_packball"])
        self.assertEqual(self.banco.conexao.execute(
            "SELECT COUNT(DISTINCT packball_url) "
            "FROM historico_thestatsapi_live"
        ).fetchone()[0], 3)

    def test_detalhes_ficam_restritos_ao_lote_informado(self):
        jogos = [_jogo(numero) for numero in range(1, 4)]
        self.servico.thestatsapi = TheStatsAPIFalsa(3)
        self.servico.thestatsapi_max_jogos_ciclo = 20
        tarefas = self._tarefas(jogos)[:1]

        resumo = self.servico._executar_thestatsapi_sombra(
            jogos, tarefas, {}
        )

        self.assertEqual(resumo["pareamentos"]["associados"], 3)
        self.assertEqual(resumo["pares_elegiveis_no_lote"], 1)
        self.assertEqual(resumo["jogos_consultados"], 1)
        self.assertEqual(resumo["stats"]["persistidos"], 1)
        self.assertEqual(resumo["odds"]["jogos_com_ofertas"], 1)
        self.assertEqual(self.servico.thestatsapi.chamadas, 3)

    def test_rodizio_inclui_jogo_ainda_nao_consultado(self):
        jogos = [_jogo(numero) for numero in range(1, 4)]
        self.servico.thestatsapi = TheStatsAPIFalsa(3)
        tarefas = self._tarefas(jogos)

        self.servico._executar_thestatsapi_sombra(jogos, tarefas, {})
        primeira = set(self.servico.thestatsapi.stats_ids)
        self.servico._executar_thestatsapi_sombra(jogos, tarefas, {})
        segunda = set(self.servico.thestatsapi.stats_ids) - primeira

        self.assertIn("mt_3", segunda)
        self.assertEqual(self.servico.thestatsapi.lista_chamadas, 2)

    def test_falha_da_lista_nao_fecha_gate_packball(self):
        self.servico.thestatsapi = TheStatsAPIFalsa(1, falhar_lista=True)

        resumo = self.servico._executar_thestatsapi_sombra(
            [_jogo(1)], [], {}
        )

        self.assertEqual(resumo["estado"], "falha_isolada_lista")
        self.assertEqual(resumo["jogos_consultados"], 0)
        self.assertFalse(self.servico._operacao_bloqueada_ciclo)

    def test_sem_jogos_em_ambas_fontes_nao_simula_falha_pareamento(self):
        self.servico.thestatsapi = TheStatsAPIFalsa(0)

        resumo = self.servico._executar_thestatsapi_sombra([], [], {})

        self.assertEqual(resumo["estado"], "sem_jogos_ao_vivo")
        self.assertEqual(resumo["tentativas_pareamento"], 0)
        self.assertEqual(resumo["pareadas"], 0)

    def test_lista_thestats_vazia_com_packball_ativo_explica_cobertura(self):
        self.servico.thestatsapi = TheStatsAPIFalsa(0)

        resumo = self.servico._executar_thestatsapi_sombra(
            [_jogo(1)], self._tarefas([_jogo(1)]), {}
        )

        self.assertEqual(
            resumo["estado"], "thestatsapi_sem_jogos_ao_vivo"
        )
        self.assertEqual(resumo["tentativas_pareamento"], 1)
        self.assertEqual(resumo["pareadas"], 0)

    def test_falha_dos_detalhes_fica_apenas_na_telemetria_sombra(self):
        self.servico.thestatsapi = TheStatsAPIFalsa(
            1, falhar_detalhes=True
        )

        resumo = self.servico._executar_thestatsapi_sombra(
            [_jogo(1)], [], {}
        )

        self.assertEqual(resumo["estado"], "coleta_sombra_parcial")
        self.assertEqual(resumo["erros"], 2)
        self.assertFalse(self.servico._operacao_bloqueada_ciclo)
        self.assertEqual(
            self.banco.resumir_cobertura_thestatsapi()["snapshots_stats"],
            0,
        )

    def test_configuracao_ativa_por_padrao_quando_ha_chave(self):
        base = {
            "PACKBALL_EMAIL": "usuario",
            "PACKBALL_PASSWORD": "senha",
            "NOVA_FOOTBALL_API_KEY": "segredo",
        }

        ativa = validar_configuracao(base)
        desligada = validar_configuracao({
            **base, "THESTATSAPI_SOMBRA_ATIVA": "0"
        })
        invalida = validar_configuracao({
            **base, "THESTATSAPI_SOMBRA_ATIVA": "talvez"
        })
        limite_invalido = validar_configuracao({
            **base, "THESTATSAPI_MAX_JOGOS_CICLO": "18"
        })

        self.assertTrue(ativa["recursos"]["thestatsapi_sombra"])
        self.assertEqual(ativa["thestatsapi"]["maximo_jogos_ciclo"], 17)
        self.assertFalse(desligada["recursos"]["thestatsapi_sombra"])
        self.assertFalse(invalida["valida"])
        self.assertFalse(limite_invalido["valida"])
        self.assertNotIn("segredo", repr(ativa))

        oficial = validar_configuracao({
            **base,
            "THESTATSAPI_SOMBRA_ATIVA": "1",
            "THESTATSAPI_APLICACAO_SINAIS_ATIVA": "1",
        })
        oficial_sem_fonte = validar_configuracao({
            "PACKBALL_EMAIL": "usuario",
            "PACKBALL_PASSWORD": "senha",
            "THESTATSAPI_APLICACAO_SINAIS_ATIVA": "1",
        })
        self.assertTrue(oficial["valida"])
        self.assertTrue(oficial["thestatsapi"]["aplicacao_sinais"])
        self.assertEqual(
            oficial["thestatsapi"]["modo"],
            "complemento_oficial_fail_closed",
        )
        self.assertFalse(oficial_sem_fonte["valida"])

    def test_autorizacao_oficial_marca_mercado_e_oferta(self):
        contrato = {
            "ao_vivo": [{
                "aplicacao_sinais": False,
                "autoriza_sinal": False,
                "ofertas": [{
                    "linha": 1.5,
                    "over": 1.8,
                    "aplicacao_sinais": False,
                    "autoriza_sinal": False,
                }],
            }],
            "_metadados": {
                "aplicacao_sinais": False,
                "autoriza_sinal": False,
                "telegram": False,
            },
        }

        autorizado = ServicoMonitor._autorizar_contrato_odds_thestatsapi(
            contrato
        )

        mercado = autorizado["ao_vivo"][0]
        oferta = mercado["ofertas"][0]
        self.assertTrue(mercado["aplicacao_sinais"])
        self.assertTrue(mercado["autoriza_sinal"])
        self.assertTrue(oferta["aplicacao_sinais"])
        self.assertTrue(oferta["autoriza_sinal"])
        self.assertTrue(autorizado["_metadados"]["telegram"])
        self.assertEqual(
            autorizado["_metadados"]["rollback"],
            "THESTATSAPI_APLICACAO_SINAIS_ATIVA=0",
        )

    def _salvar_evidencia_scout(self, jogo, coletado_em):
        numero = jogo["url"].split("/")[-2]
        self.banco.salvar_pareamento_thestatsapi({
            "packball_url": jogo["url"],
            "match_id": f"mt_{numero}",
            "orientacao": "direta",
            "similaridade": 0.99,
            "margem": 0.2,
            "mandante_api": jogo["mandante"],
            "visitante_api": jogo["visitante"],
            "atualizado_em": coletado_em.isoformat(),
        }, agora=coletado_em)
        self.banco.salvar_historico_thestatsapi_live([{
            "packball_url": jogo["url"],
            "match_id": f"mt_{numero}",
            "orientacao": "direta",
            "coletado_em": coletado_em.isoformat(),
            "minuto": 35,
            "placar": [0, 0],
            "chutes_mandante": 5,
            "chutes_visitante": 3,
        }], agora=coletado_em)

    def test_scout_reserva_uma_vaga_sem_ultrapassar_prioridade_critica(self):
        agora = datetime(2026, 8, 13, 20, 0, 0)
        jogos = [_jogo(numero) for numero in range(1, 5)]
        scout = jogos[3]
        self._salvar_evidencia_scout(
            scout, agora - timedelta(seconds=30)
        )
        self.servico.thestatsapi = TheStatsAPIFalsa(4)
        tarefas = [
            {
                "jogo": jogos[0], "em_foco": True,
                "rechecagem_pos_evento": False,
                "prioridade": "rapida", "atraso_segundos": 0,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
            {
                "jogo": jogos[1], "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "atraso_segundos": 10,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
            {
                "jogo": jogos[2], "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "atraso_segundos": 60,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
            {
                "jogo": scout, "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "atraso_segundos": 30,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
        ]

        ordenadas, diagnostico = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], jogos[0]["url"])
        self.assertEqual(ordenadas[1]["jogo"]["url"], scout["url"])
        self.assertEqual(diagnostico["scout_disponiveis"], 1)
        self.assertTrue(diagnostico["scout_reservado"])
        self.assertTrue(diagnostico["scout_nas_quatro_primeiras"])
        self.assertTrue(diagnostico["sem_autorizacao_sinal"])
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM sinais"
            ).fetchone()[0],
            0,
        )

    def test_scout_nao_ultrapassa_tarefa_atrasada_mais_de_vinte_minutos(self):
        agora = datetime(2026, 8, 13, 20, 0, 0)
        jogos = [_jogo(numero) for numero in range(1, 4)]
        scout = jogos[2]
        self._salvar_evidencia_scout(scout, agora)
        self.servico.thestatsapi = TheStatsAPIFalsa(3)
        tarefas = [
            {
                "jogo": jogos[0], "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "atraso_segundos": 10,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
            {
                "jogo": jogos[1], "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "atraso_segundos": 1201,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
            {
                "jogo": scout, "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "atraso_segundos": 20,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
        ]

        ordenadas, diagnostico = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )

        self.assertLess(
            [item["jogo"]["url"] for item in ordenadas].index(
                jogos[1]["url"]
            ),
            [item["jogo"]["url"] for item in ordenadas].index(
                scout["url"]
            ),
        )
        self.assertTrue(diagnostico["scout_reservado"])

    def test_scout_respeita_idade_critica_mesmo_com_atraso_menor(self):
        agora = datetime(2026, 8, 13, 20, 0, 0)
        jogos = [_jogo(numero) for numero in range(1, 4)]
        scout = jogos[2]
        self._salvar_evidencia_scout(scout, agora)
        self.servico.thestatsapi = TheStatsAPIFalsa(3)
        tarefas = [
            {
                "jogo": jogos[0], "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "idade_segundos": 20,
                "atraso_segundos": 10,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
            {
                "jogo": jogos[1], "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "idade_segundos": 1300,
                "atraso_segundos": 940,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
            {
                "jogo": scout, "em_foco": False,
                "rechecagem_pos_evento": False,
                "prioridade": "lenta", "idade_segundos": 30,
                "atraso_segundos": 20,
                "acionavel_fila_detalhada": True,
                "janelas_temporais_projetadas": [],
            },
        ]

        ordenadas, diagnostico = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )
        urls = [item["jogo"]["url"] for item in ordenadas]

        self.assertLess(urls.index(jogos[1]["url"]), urls.index(scout["url"]))
        self.assertTrue(diagnostico["scout_reservado"])

    def test_scout_exclui_nao_acionavel_intervalo_minuto_desconhecido_e_87(self):
        agora = datetime(2026, 8, 13, 20, 0, 0)
        jogos = [_jogo(numero) for numero in range(1, 4)]
        jogos[1]["status"] = "Intervalo"
        jogos[2]["status"] = "87 '"
        for jogo in jogos:
            self._salvar_evidencia_scout(jogo, agora)
        self.servico.thestatsapi = TheStatsAPIFalsa(3)
        tarefas = self._tarefas(jogos)
        tarefas[0]["acionavel_fila_detalhada"] = False
        tarefas[0]["em_foco"] = False
        antes = [item["jogo"]["url"] for item in tarefas]

        ordenadas, diagnostico = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )

        self.assertEqual(
            [item["jogo"]["url"] for item in ordenadas], antes
        )
        self.assertEqual(diagnostico["scout_disponiveis"], 0)
        self.assertFalse(diagnostico["scout_reservado"])

    def test_scout_nao_ultrapassa_reserva_de_janela_temporal(self):
        agora = datetime(2026, 8, 13, 20, 0, 0)
        jogos = [_jogo(numero) for numero in range(1, 5)]
        scout = jogos[3]
        self._salvar_evidencia_scout(scout, agora)
        self.servico.thestatsapi = TheStatsAPIFalsa(4)
        tarefas = self._tarefas(jogos)
        for tarefa in tarefas:
            tarefa["em_foco"] = False
            tarefa["prioridade"] = "lenta"
            tarefa["atraso_segundos"] = 10
        tarefas[1]["janelas_temporais_projetadas"] = [5]

        ordenadas, diagnostico = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )
        urls = [item["jogo"]["url"] for item in ordenadas]

        self.assertLess(urls.index(jogos[1]["url"]), urls.index(scout["url"]))
        self.assertTrue(diagnostico["scout_reservado"])

    def test_circuito_aberto_ou_falha_local_preservam_ordem(self):
        agora = datetime(2026, 8, 13, 20, 0, 0)
        jogos = [_jogo(1), _jogo(2)]
        self._salvar_evidencia_scout(jogos[1], agora)
        tarefas = self._tarefas(jogos)
        for tarefa in tarefas:
            tarefa["em_foco"] = False
        cliente = TheStatsAPIFalsa(2)
        cliente.diagnostico = Mock(return_value={
            "circuito_aberto": True,
            "consumo": {
                "contador_saudavel": True,
                "restante_local_seguro": 10,
            },
        })
        self.servico.thestatsapi = cliente
        antes = [item["jogo"]["url"] for item in tarefas]

        circuito, diagnostico = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )

        self.assertEqual(
            [item["jogo"]["url"] for item in circuito], antes
        )
        self.assertEqual(diagnostico["estado"], "cliente_sem_capacidade")

        del cliente.diagnostico
        original = self.banco.obter_pareamento_thestatsapi
        self.banco.obter_pareamento_thestatsapi = Mock(
            side_effect=RuntimeError("falha local")
        )
        try:
            falha, diagnostico_falha = (
                self.servico._priorizar_packball_por_thestatsapi(
                    tarefas, agora=agora
                )
            )
        finally:
            self.banco.obter_pareamento_thestatsapi = original
        self.assertEqual(
            [item["jogo"]["url"] for item in falha], antes
        )
        self.assertFalse(diagnostico_falha["scout_reservado"])

    def test_execucao_distingue_scout_adiado_e_processado(self):
        self.servico.agendador = Mock()
        self.servico.observabilidade = Mock()
        self.servico._duracoes_tarefas_recentes = []
        self.servico.processar_jogo = Mock(return_value={
            "fixture_id": None,
            "odds_coletadas": False,
            "duracao_segundos": 10,
            "janelas_temporais": [],
        })
        tarefas = [
            {
                "jogo": _jogo(1), "coletar_odds": False,
                "em_foco": False, "idade_segundos": 10,
            },
            {
                "jogo": _jogo(2), "coletar_odds": False,
                "em_foco": False, "idade_segundos": 10,
                "_thestatsapi_scout": True,
            },
        ]
        instantes = iter((0, 181, 181))

        adiado = self.servico._processar_tarefas_detalhadas(
            None,
            tarefas,
            [],
            orcamento_segundos=180,
            relogio=lambda: next(instantes),
        )
        diagnostico_adiado = (
            self.servico._finalizar_diagnostico_scout_thestatsapi(
                {"scout_reservado": True, "ordem_alterada": True},
                adiado,
            )
        )

        self.assertFalse(adiado["thestatsapi_scout_processado"])
        self.assertFalse(
            diagnostico_adiado["amostra_coleta_influenciada"]
        )

        self.servico.processar_jogo.reset_mock()
        instantes = iter((0, 10))
        processado = self.servico._processar_tarefas_detalhadas(
            None,
            [tarefas[1]],
            [],
            orcamento_segundos=180,
            relogio=lambda: next(instantes),
        )
        diagnostico_processado = (
            self.servico._finalizar_diagnostico_scout_thestatsapi(
                {"scout_reservado": True, "ordem_alterada": True},
                processado,
            )
        )

        self.assertTrue(processado["thestatsapi_scout_processado"])
        self.assertTrue(
            diagnostico_processado["amostra_coleta_influenciada"]
        )

    def test_scout_expirado_nao_altera_ordem(self):
        agora = datetime(2026, 8, 13, 20, 0, 0)
        jogos = [_jogo(1), _jogo(2)]
        self._salvar_evidencia_scout(
            jogos[1], agora - timedelta(minutes=6)
        )
        self.servico.thestatsapi = TheStatsAPIFalsa(2)
        tarefas = self._tarefas(jogos)
        tarefas[0]["em_foco"] = False
        antes = [item["jogo"]["url"] for item in tarefas]

        ordenadas, diagnostico = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )

        self.assertEqual(
            [item["jogo"]["url"] for item in ordenadas], antes
        )
        self.assertFalse(diagnostico["scout_reservado"])

    def test_rollback_flag_ou_chave_ausente_zeram_chamadas_e_scout(self):
        jogo = _jogo(1)
        agora = datetime(2026, 8, 13, 20, 0, 0)
        self._salvar_evidencia_scout(jogo, agora)
        tarefas = self._tarefas([jogo])
        cliente = TheStatsAPIFalsa(1)
        self.servico.thestatsapi = cliente
        self.servico.thestatsapi_sombra_ativa = False

        resumo = self.servico._executar_thestatsapi_sombra(
            [jogo], tarefas, {}
        )
        ordenadas, scout = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )

        self.assertEqual(cliente.chamadas, 0)
        self.assertEqual(resumo["estado"], "desativada")
        self.assertFalse(scout["scout_reservado"])
        self.assertEqual(ordenadas, tarefas)
        self.assertFalse(self.servico._operacao_bloqueada_ciclo)

        cliente.disponivel = False
        self.servico.thestatsapi_sombra_ativa = True
        resumo_sem_chave = self.servico._executar_thestatsapi_sombra(
            [jogo], tarefas, {}
        )
        _, scout_sem_chave = (
            self.servico._priorizar_packball_por_thestatsapi(
                tarefas, agora=agora
            )
        )
        self.assertEqual(cliente.chamadas, 0)
        self.assertEqual(resumo_sem_chave["estado"], "sem_chave")
        self.assertFalse(scout_sem_chave["scout_reservado"])

    def test_observabilidade_e_status_expoem_apenas_medicao_sombra(self):
        observabilidade = Observabilidade(self.log)
        ciclo = {
            "estado": "coleta_sombra",
            "chamadas_rede": 5,
            "tentativas_pareamento": 3,
            "pareadas": 3,
            "stats_persistidos": 2,
            "partidas_com_odds": 2,
            "aplicacao_sinais": False,
        }
        registro = observabilidade.ciclo_sucesso(
            1,
            3,
            {"dia": {}, "total_dia": 0},
            {"thestatsapi_sombra": ciclo},
        )
        texto = descrever_thestatsapi_sombra(
            {"sombra_ativa": True},
            {
                "chave_configurada": True,
                "consumo": {"usado_local_dia": 5},
            },
            {
                "pareamentos_total": 749,
                "ultima_coleta_stats": "2026-08-24T22:11:33-04:00",
                "ultima_coleta_odds": "2026-08-24T22:11:33-04:00",
            },
            ciclo,
        )

        self.assertEqual(registro["thestatsapi_sombra"], ciclo)
        self.assertIn("chamadas ciclo/dia=5/5", texto)
        self.assertIn("pareamentos históricos=749", texto)
        self.assertIn(
            "última stats/odd=2026-08-24T22:11:33-04:00/"
            "2026-08-24T22:11:33-04:00",
            texto,
        )
        self.assertIn("uso nos sinais=nao", texto)

    def test_status_expoe_modo_oficial_e_rollback(self):
        texto = descrever_thestatsapi_sombra(
            {"sombra_ativa": True, "aplicacao_sinais": True},
            {"chave_configurada": True},
            {},
            {"estado": "coleta_oficial", "aplicacao_sinais": True},
        )

        self.assertIn("oficial fail-closed", texto)
        self.assertIn("uso nos sinais=sim, com gate", texto)
        self.assertIn("THESTATSAPI_APLICACAO_SINAIS_ATIVA=0", texto)

    def test_regressao_historico_api_saudavel_retorna_texto(self):
        texto = descrever_historico_api_live({
            "saudavel": True,
            "estado": "coletando",
            "snapshots": 2,
            "fixtures": 1,
            "cobertura_completa": 1.0,
            "janelas_disponiveis": {"5": 1, "10": 0, "15": 0},
            "comparacoes_packball_api": 1,
            "taxa_concordancia_packball_api": 1.0,
            "prontidao_revisao": {},
        })

        self.assertIsInstance(texto, str)
        self.assertIn("somente sombra", texto)


if __name__ == "__main__":
    unittest.main()
