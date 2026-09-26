import hashlib
import json
import os
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from banco import BancoMonitor
from coletor_packball import PackBallListaNaoValidadaError
from controle_acesso_packball import (
    PackBallBloqueadoError,
    PackBallPausaPreventivaError,
)
from controle_sistema import solicitar_modo_manutencao
from custodia_avaliacao import EFEITOS_DESATIVADOS
from exploracao_sombra import (
    REGRA_FINGERPRINT_GOL_FT_V3,
    REGRA_VERSAO_GOL_FT_V3,
    VERSAO_EXPLORACAO_ASIATICA,
    VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
    VERSAO_EXPLORACAO_GOL_FT_V3,
)
from observabilidade import Observabilidade
from gol_ft_tendencia_mais_um import (
    LINHAGEM as LINHAGEM_GOL_FT_TENDENCIA,
    VERSAO as VERSAO_GOL_FT_TENDENCIA,
)
from normalizador_odds import (
    escolher_over_ao_vivo,
    escolher_over_ht,
    escolher_over_periodo,
)
from servico_monitor import ManutencaoSolicitadaError, ServicoMonitor, main
from top_criterios_gols import LINHAGEM as LINHAGEM_TOP, VERSAO_FT as VERSAO_TOP_FT
from versoes_challengers_preciso import versao_regra_operacional


class ServicoMonitorTest(unittest.TestCase):
    def setUp(self):
        self.periodos_asiaticos = patch.dict(
            "os.environ",
            {
                "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS": "1",
                "GOL_FT_REFORCADO_ATIVO": "0",
            },
        )
        self.periodos_asiaticos.start()
        self.caminho = Path.cwd() / ".teste_servico_monitor.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.servico = object.__new__(ServicoMonitor)
        self.servico.banco = self.banco
        self.servico.controle_packball = None
        self.url = "https://packball.com/match/1/live"

    def tearDown(self):
        self.banco.fechar()
        self.periodos_asiaticos.stop()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        log = Path.cwd() / ".teste_servico_monitor_eventos.jsonl"
        if log.exists():
            log.unlink()

    def test_clv_pos_alerta_fotografa_bet365_sem_criar_novo_sinal(self):
        entrada = self.banco.salvar_registro({
            "coletado_em": "2026-09-12T12:00:00",
            "url": self.url,
            "mandante": "Time A",
            "visitante": "Time B",
            "placar": "0-0",
            "status": "20 '",
            "estatisticas": {},
            "evolucao": {},
            "odds": {},
            "confirmacao_api": {
                "fixture_id": 123,
                "orientacao": "direta",
            },
        })
        sinal = self.banco.salvar_candidatos(entrada, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.80,
            "regra_versao": "teste-clv-rapido-v1",
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
            provedor_mensagem_id="clv-servico-1",
            confirmacao={
                "provedor": "telegram", "ok": True,
                "message_id": "clv-servico-1",
            },
        )
        self.servico.api = Mock()
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = [{
            "fixture": {"id": 123, "status": {
                "elapsed": 22, "extra": None, "short": "1H",
            }},
            "goals": {"home": 0, "away": 0},
            "teams": {
                "home": {"id": 1, "name": "Time A"},
                "away": {"id": 2, "name": "Time B"},
            },
            "statistics": [
                {"team": {"id": 1}, "statistics": [
                    {"type": "Corner Kicks", "value": 4},
                ]},
                {"team": {"id": 2}, "statistics": [
                    {"type": "Corner Kicks", "value": 3},
                ]},
            ],
        }]
        self.servico.betsapi = Mock()
        self.servico.betsapi.buscar_mercados.return_value = (
            {"ao_vivo": []}, {"pareado": True}
        )
        oferta = {
            "odd": 1.70,
            "odd_oposta": 2.15,
            "linha": 0.5,
            "fonte": "betsapi",
            "bookmaker": "bet365",
            "idade_segundos": 0.0,
            "coletado_em": "2026-09-12T12:02:10",
            "cache": False,
            "origem_mercado": {
                "schema": "origem-mercado-odd-v1",
                "fonte": "betsapi",
                "identificador": "mercado-123",
                "nome": "Match Goals",
                "linha": 0.5,
                "lados": ["over", "under"],
                "bookmaker": "bet365",
            },
            "identidade_evento": {
                "schema": "identidade-evento-odd-v1",
                "confirmada": True,
                "fonte": "betsapi",
                "evento_externo_id": "evento-123",
                "orientacao": "direta",
                "similaridade": 0.95,
                "mandante_normalizado": "Time A",
                "visitante_normalizado": "Time B",
                "placar_normalizado": "0-0",
                "metodo": "teste",
            },
        }
        self.servico.betsapi.buscar_mercados.return_value = ({
            "ao_vivo": [{
                "categoria": "gols",
                "escopo": "total",
                "tipo_mercado": "total",
                "formato": "duas_opcoes",
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "ofertas": [{
                    "linha": 0.5,
                    "over": 1.70,
                    "under": 2.15,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "origem_mercado": oferta["origem_mercado"],
                    "identidade_evento": oferta["identidade_evento"],
                }],
                "ofertas_ht": [],
            }],
        }, {"pareado": True})

        with (
            patch("servico_monitor.datetime") as relogio,
            patch(
                "servico_monitor.extrair_odd_exata_acompanhamento",
                return_value=oferta,
            ),
        ):
            relogio.now.return_value = datetime(2026, 9, 12, 12, 2, 10)
            resumo = self.servico._capturar_cotacoes_clv_pos_alerta_api()

        self.assertEqual("concluida", resumo["estado"])
        self.assertEqual(1, resumo["candidatos"])
        self.assertEqual(1, resumo["com_oferta_exata"], resumo)
        self.assertEqual(1, resumo["estados_persistidos"])
        self.assertEqual(0, resumo["falhas"])
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["telegram"])
        self.assertEqual(1, self.banco.conexao.execute(
            "SELECT COUNT(*) FROM sinais"
        ).fetchone()[0])
        estados = self.banco.conexao.execute(
            "SELECT estado,oferta_json FROM observacoes_fontes_odds "
            "ORDER BY id"
        ).fetchall()
        self.assertEqual(
            ["oferta_monitorada", "clv_pos_alerta"],
            [item["estado"] for item in estados],
        )
        payload = json.loads(estados[-1]["oferta_json"])
        self.assertTrue(payload["oferta_exata_disponivel"])
        self.assertFalse(payload["aplicacao_sinais"])
        self.assertFalse(payload["telegram"])

    def test_clv_pos_alerta_packball_coleta_estado_sem_misturar_preco(self):
        banco = Mock()
        banco.sinais_entregues_para_clv_pos_alerta.return_value = [{
            "sinal_id": 9,
            "api_fixture_id": 123,
            "api_orientacao": "direta",
            "packball_url": self.url,
            "mandante": "Time A",
            "visitante": "Time B",
            "mercado": "gol_ft",
            "linha": 0.5,
            "fonte_odds": "packball",
            "bookmaker_odds": "",
        }]
        banco.registrar_estado_clv_pos_alerta.return_value = {
            "persistido": True,
            "observacao_id": 46,
        }
        self.servico.banco = banco
        self.servico.api = Mock()
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = [{
            "fixture": {"id": 123, "status": {
                "elapsed": 22, "extra": None, "short": "1H",
            }},
            "goals": {"home": 1, "away": 0},
        }]
        self.servico.betsapi = None

        with patch("servico_monitor.datetime") as relogio:
            relogio.now.return_value = datetime(2026, 9, 13, 12, 2, 10)
            resumo = self.servico._capturar_cotacoes_clv_pos_alerta_api()

        self.assertEqual("concluida", resumo["estado"])
        self.assertEqual(1, resumo["consultados"])
        self.assertEqual(1, resumo["somente_estado"])
        self.assertEqual(0, resumo["com_oferta_exata"])
        self.assertEqual(1, resumo["sem_oferta_exata"])
        self.assertEqual(1, resumo["estados_persistidos"])
        self.assertEqual(0, resumo["falhas"])
        banco.registrar_observacao_acompanhamento_odd.assert_not_called()
        estado = banco.registrar_estado_clv_pos_alerta.call_args.args[1]
        self.assertEqual("1-0", estado["placar"])
        self.assertIsNone(
            banco.registrar_estado_clv_pos_alerta.call_args.kwargs[
                "observacao_oferta_id"
            ]
        )
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["telegram"])

    def test_clv_pos_alerta_falha_tecnica_nao_vira_ausencia_de_odd(self):
        banco = Mock()
        banco.sinais_entregues_para_clv_pos_alerta.return_value = [{
            "sinal_id": 7,
            "api_fixture_id": 123,
            "api_orientacao": "direta",
            "packball_url": self.url,
            "mandante": "Time A",
            "visitante": "Time B",
            "mercado": "gol_ft",
            "linha": 0.5,
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
        }]
        self.servico.banco = banco
        self.servico.api = Mock()
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = [{
            "fixture": {"id": 123, "status": {
                "elapsed": 22, "extra": None, "short": "1H",
            }},
            "goals": {"home": 0, "away": 0},
        }]
        self.servico.betsapi = Mock()
        self.servico.betsapi.buscar_mercados.side_effect = RuntimeError(
            "falha temporaria"
        )

        resumo = self.servico._capturar_cotacoes_clv_pos_alerta_api()

        self.assertEqual("degradada", resumo["estado"])
        self.assertEqual(1, resumo["candidatos"])
        self.assertEqual(0, resumo["consultados"])
        self.assertEqual(0, resumo["sem_oferta_exata"])
        self.assertEqual(1, resumo["falhas"])
        banco.registrar_estado_clv_pos_alerta.assert_not_called()
        banco.registrar_observacao_acompanhamento_odd.assert_not_called()

    def test_clv_pos_alerta_consulta_escanteio_asiatico_na_api_rapida(self):
        banco = Mock()
        banco.sinais_entregues_para_clv_pos_alerta.return_value = [{
            "sinal_id": 8,
            "api_fixture_id": 123,
            "api_orientacao": "direta",
            "packball_url": self.url,
            "mandante": "Time A",
            "visitante": "Time B",
            "mercado": "escanteios_ft_asiatico",
            "linha": 8.5,
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
        }]
        banco.registrar_observacao_acompanhamento_odd.return_value = {
            "persistido": True,
            "observacao_id": 44,
        }
        banco.registrar_estado_clv_pos_alerta.return_value = {
            "persistido": True,
            "observacao_id": 45,
        }
        self.servico.banco = banco
        self.servico.api = Mock()
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = [{
            "fixture": {"id": 123, "status": {
                "elapsed": 62, "extra": None, "short": "2H",
            }},
            "goals": {"home": 0, "away": 0},
            "teams": {
                "home": {"id": 1, "name": "Time A"},
                "away": {"id": 2, "name": "Time B"},
            },
            "statistics": [
                {"team": {"id": 1}, "statistics": [
                    {"type": "Corner Kicks", "value": 4},
                ]},
                {"team": {"id": 2}, "statistics": [
                    {"type": "Corner Kicks", "value": 3},
                ]},
            ],
        }]
        self.servico.betsapi = Mock()
        self.servico.betsapi.buscar_mercados.return_value = ({
            "ao_vivo": [{
                "categoria": "escanteios",
                "escopo": "total",
                "tipo_mercado": "asiatico",
                "formato": "duas_opcoes",
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "ofertas": [{
                    "linha": 8.5,
                    "over": 1.84,
                    "under": 2.02,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "idade_segundos": 0.0,
                    "coletado_em": "2026-09-12T12:02:10",
                    "recebido_em": "2026-09-12T12:02:10",
                    "cache": False,
                }],
            }],
        }, {"pareado": True})

        with patch("servico_monitor.datetime") as relogio:
            relogio.now.return_value = datetime(2026, 9, 12, 12, 2, 10)
            resumo = self.servico._capturar_cotacoes_clv_pos_alerta_api()

        self.assertEqual(
            "coleta-clv-pos-alerta-api-rapida-v5", resumo["versao"]
        )
        self.assertIn(
            "escanteios_ft_asiatico", resumo["mercados_api_rapida"]
        )
        self.assertEqual(
            ["proximo_escanteio"], resumo["mercados_somente_snapshot"]
        )
        self.assertEqual("concluida", resumo["estado"])
        self.assertEqual(1, resumo["com_oferta_exata"])
        self.assertEqual(1, resumo["estados_persistidos"])
        self.assertEqual(0, resumo["falhas"])
        mercados_solicitados = (
            self.servico.betsapi.buscar_mercados.call_args.args[1]
        )
        self.assertEqual({"escanteios_ft_asiatico"}, mercados_solicitados)
        banco.registrar_estado_clv_pos_alerta.assert_called_once()
        estado_rapido = banco.registrar_estado_clv_pos_alerta.call_args.args[1]
        self.assertEqual({"mandante": 4, "visitante": 3}, estado_rapido["escanteios"])
        self.assertEqual(
            44,
            banco.registrar_estado_clv_pos_alerta.call_args.kwargs[
                "observacao_oferta_id"
            ],
        )
        self.assertFalse(resumo["aplicacao_sinais"])
        self.assertFalse(resumo["telegram"])

    def test_gerador_rastreavel_entrega_referencia_separada_so_a_sombra(self):
        candidato = {
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": 1.80,
            "status": "aprovado",
            "bloqueios": [],
            "features": {
                "cotacao_entrada_clv": {
                    "odd_selecionada": 1.80,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "idade_segundos": 1,
                    "cache": False,
                },
            },
        }
        mercado_operacional = {
            "categoria": "gols",
            "escopo": "total",
            "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "fonte": "betsapi",
            "bookmaker": "bet365",
            "idade_segundos": 1,
            "cache": False,
            "ofertas": [{"linha": 2.5, "over": 1.80, "under": 2.05}],
        }
        mercado_referencia = {
            **mercado_operacional,
            "fonte": "the_odds_api",
            "bookmaker": "pinnacle",
            "ofertas": [{
                "linha": 2.5,
                "over": 1.92,
                "under": 1.94,
                "fonte": "the_odds_api",
                "bookmaker": "pinnacle",
                "idade_segundos": 1,
                "cache": False,
            }],
        }
        odds = {"ao_vivo": [mercado_operacional]}
        referencia = {"ao_vivo": [mercado_referencia]}

        with (
            patch("servico_monitor.gerar_candidatos", return_value=[candidato]),
            patch("servico_monitor.aplicar_proveniencia_odds"),
        ):
            resultado = self.servico._gerar_candidatos_rastreaveis(
                {}, {}, {}, odds, {}, odds_referencia_sombra=referencia
            )

        sombra = resultado[0]["features"]["melhor_preco_sombra"]
        self.assertEqual("comparacao_independente_exata", sombra["estado"])
        self.assertEqual("referencia_sombra", sombra[
            "melhor_alternativa_independente"
        ]["camada"])
        self.assertFalse(sombra["aplicacao_sinais"])
        self.assertFalse(sombra["telegram"])
        self.assertEqual(1.80, resultado[0]["odd"])
        self.assertEqual("aprovado", resultado[0]["status"])

    def test_prioriza_referencia_so_para_cotacao_liquidavel_sem_coorte(self):
        candidatos = [
            {
                "mercado": "gol_ft",
                "status": "aprovado",
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "features": {"cotacao_entrada_clv_estado": "congelada_v1"},
            },
            {
                "mercado": "gol_ht",
                "status": "rejeitado",
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "features": {"cotacao_entrada_clv_estado": "congelada_v1"},
            },
            {
                "mercado": "escanteios_ft_asiatico",
                "status": "simulacao",
                "fonte_odds": "packball",
                "bookmaker_odds": "bet365",
                "features": {"cotacao_entrada_clv_estado": "congelada_v1"},
            },
        ]
        with patch(
            "servico_monitor.mercados_com_candidato_sincronizado",
            return_value=set(),
        ) as consultar:
            mercados, diagnostico = (
                self.servico._priorizar_referencia_valor_justo(
                    {"url": self.url},
                    candidatos,
                    {"gol_ft", "gol_ht", "escanteios_ft_asiatico"},
                )
            )

        self.assertEqual({"gol_ft"}, mercados)
        self.assertEqual(["gol_ft"], diagnostico["mercados_priorizados"])
        self.assertEqual(1, diagnostico["exclusoes"]["status_nao_liquidavel"])
        self.assertEqual(
            1,
            diagnostico["exclusoes"][
                "cotacao_executavel_nao_e_betsapi_bet365"
            ],
        )
        self.assertFalse(diagnostico["aplicacao_sinais"])
        consultar.assert_called_once_with(
            self.banco.conexao, self.url, {"gol_ft"}
        )

        with patch(
            "servico_monitor.mercados_com_candidato_sincronizado",
            return_value={"gol_ft"},
        ):
            mercados_existentes, diagnostico_existente = (
                self.servico._priorizar_referencia_valor_justo(
                    {"url": self.url}, candidatos, {"gol_ft"}
                )
            )
        self.assertEqual(set(), mercados_existentes)
        self.assertEqual(
            ["gol_ft"],
            diagnostico_existente["mercados_coorte_ja_formada"],
        )

    def test_prioriza_referencia_para_auditoria_bloqueio_prevista(self):
        candidatos = [
            {
                "mercado": "gol_ft",
                "linha": 2.5,
                "odd": 1.55,
                "pontuacao_tecnica": 72,
                "regra_versao": "sinais-v6",
                "status": "rejeitado",
                "bloqueios": ["atividade_recente_insuficiente_gols"],
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "features": {
                    "cotacao_entrada_clv_estado": "congelada_v1"
                },
            },
            {
                "mercado": "gol_ht",
                "linha": 0.5,
                "odd": 1.65,
                "pontuacao_tecnica": 75,
                "regra_versao": "sinais-v8b-gol-ht-max28",
                "status": "rejeitado",
                "bloqueios": ["fora_da_janela"],
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "features": {
                    "cotacao_entrada_clv_estado": "congelada_v1"
                },
            },
        ]
        with (
            patch.dict(
                os.environ,
                {"AUDITORIA_BLOQUEIOS_PROMISSORES_ATIVA": "1"},
            ),
            patch(
                "servico_monitor.mercados_com_candidato_sincronizado",
                return_value=set(),
            ) as consultar,
        ):
            mercados, diagnostico = (
                self.servico._priorizar_referencia_valor_justo(
                    {"url": self.url},
                    candidatos,
                    {"gol_ft", "gol_ht"},
                )
            )

        self.assertEqual({"gol_ft"}, mercados)
        self.assertEqual(
            "priorizacao-referencia-valor-justo-v2",
            diagnostico["versao"],
        )
        self.assertEqual(
            1,
            diagnostico["origens_elegibilidade"][
                "auditoria_bloqueio_prevista"
            ],
        )
        self.assertEqual(
            1, diagnostico["exclusoes"]["status_nao_liquidavel"]
        )
        consultar.assert_called_once_with(
            self.banco.conexao, self.url, {"gol_ft"}
        )

    def test_falha_da_avaliacao_desajuste_substitui_estado_saudavel(self):
        self.servico.pasta = Path.cwd()
        self.servico.observabilidade = Mock()
        self.servico._ultima_avaliacao_desajuste_odds = 0.0

        with (
            patch(
                "servico_monitor.avaliar_desajustes_odds",
                side_effect=RuntimeError("token=segredo indisponivel"),
            ),
            patch("servico_monitor.gravar_json_atomico") as gravar,
        ):
            resultado = self.servico._avaliar_desajuste_odds_prospectivo(
                forcar=True
            )

        self.assertEqual(2, gravar.call_count)
        marcador = gravar.call_args_list[0].args[1]
        falha = gravar.call_args_list[1].args[1]
        self.assertEqual("em_execucao", marcador["estado_execucao"])
        self.assertEqual("falha", falha["estado_execucao"])
        self.assertEqual("falha_avaliacao", falha["estado"])
        self.assertNotIn("persistencia_comprovada", falha)
        self.assertIn("<redigido>", falha["erro"])
        self.assertEqual("confirmada", resultado["persistencia_estado"])

    def test_telemetria_nao_invalida_avaliacao_desajuste_concluida(self):
        self.servico.pasta = Path.cwd()
        self.servico.observabilidade = Mock()
        self.servico.observabilidade.ciclo_progresso.side_effect = (
            RuntimeError("telemetria indisponivel")
        )
        self.servico._ultima_avaliacao_desajuste_odds = 0.0
        avaliacao = {
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            "estado_execucao": "concluida",
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }

        with (
            patch(
                "servico_monitor.avaliar_desajustes_odds",
                return_value=avaliacao,
            ),
            patch("servico_monitor.gravar_json_atomico") as gravar,
        ):
            resultado = self.servico._avaliar_desajuste_odds_prospectivo(
                forcar=True
            )

        self.assertEqual(2, gravar.call_count)
        self.assertEqual("concluida", resultado["estado_execucao"])
        self.assertIn("duracao_segundos", resultado)
        self.assertNotEqual("falha_avaliacao", resultado.get("estado"))

    def test_custodia_comum_cobre_todos_os_avaliadores_periodicos(self):
        self.servico.pasta = Path.cwd()
        self.servico.observabilidade = Mock()
        casos = (
            (
                "_avaliar_acompanhamento_odd_prospectivo",
                "avaliar_estrategia_acompanhamento_odd",
                "avaliacao-aguardar-odd-prospectiva-v6",
                "avaliacao_acompanhamento_odd_estado.json",
            ),
            (
                "_avaliar_prioridade_ligas_gols_prospectiva",
                "avaliar_prioridade_ligas_gols",
                "avaliacao-prioridade-ligas-gols-prospectiva-v3",
                "avaliacao_prioridade_ligas_gols_estado.json",
            ),
            (
                "_avaliar_quarentena_fallback_ht_prospectiva",
                "avaliar_quarentena_fallback_ht",
                "avaliacao-quarentena-fallback-ht-prospectiva-v3",
                "avaliacao_quarentena_fallback_ht_estado.json",
            ),
            (
                "_avaliar_probabilidade_individual_prospectiva",
                "avaliar_probabilidade_individual",
                (
                    "avaliacao-probabilidade-individual-sem-vig-"
                    "prospectiva-v2"
                ),
                "avaliacao_probabilidade_individual_estado.json",
            ),
        )
        for metodo, avaliador, versao, arquivo in casos:
            with self.subTest(metodo=metodo):
                avaliacao = {
                    "versao": versao,
                    "custodia_execucao_versao": (
                        "custodia-execucao-avaliacao-v3"
                    ),
                    "estado_execucao": "concluida",
                    **{
                        chave: True for chave in EFEITOS_DESATIVADOS
                    },
                }
                with (
                    patch(
                        f"servico_monitor.{avaliador}",
                        return_value=avaliacao,
                    ),
                    patch("servico_monitor.gravar_json_atomico") as gravar,
                ):
                    resultado = getattr(self.servico, metodo)(forcar=True)

                self.assertEqual(2, gravar.call_count)
                self.assertEqual(
                    Path.cwd() / arquivo,
                    gravar.call_args_list[0].args[0],
                )
                self.assertEqual(
                    "em_execucao",
                    gravar.call_args_list[0].args[1]["estado_execucao"],
                )
                self.assertEqual("concluida", resultado["estado_execucao"])
                self.assertNotIn("detalhes", resultado)
                self.assertEqual(
                    "sem_ancora_prospectiva",
                    resultado["exposicao_coleta_prospectiva"]["estado"],
                )
                for chave in EFEITOS_DESATIVADOS:
                    self.assertIs(resultado[chave], False)
                    self.assertIs(
                        gravar.call_args_list[1].args[1][chave], False
                    )

    def test_api_nao_consulta_asiatico_1t_quando_suspenso(self):
        self.servico.api = Mock()
        odds = {"ao_vivo": []}
        jogo = {"status": "25 '"}
        confirmacao = {"fixture_id": 123}

        with patch.dict(
            "os.environ",
            {"ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS": "0"},
        ):
            adicionou = self.servico._complementar_odds_escanteios_1t_api(
                odds,
                jogo,
                confirmacao,
                coletar_odds_agora=True,
            )

        self.assertFalse(adicionou)
        self.servico.api.odds_escanteios_asiaticos_1t.assert_not_called()

    def test_metodo_especial_de_gol_exige_historico_sem_buscar_odd_api(self):
        precisa = self.servico._precisa_contexto_linhas_gols(
            [{
                "mercado": "gol_ht",
                "status": "rejeitado",
                "bloqueios": ["atividade_recente_insuficiente_gols"],
            }],
            set(),
            candidato_ht_00_min20=True,
        )

        self.assertTrue(precisa)

    def test_jogo_sem_candidato_de_gol_nao_consulta_historico_de_linhas(self):
        precisa = self.servico._precisa_contexto_linhas_gols(
            [{"mercado": "escanteios_ft", "status": "aprovado"}],
            set(),
        )

        self.assertFalse(precisa)

    def test_the_odds_api_complementa_mercado_compativel(self):
        self.servico.the_odds_api = Mock()
        self.servico.the_odds_api.buscar_mercados.return_value = (
            {"ao_vivo": [{
                "categoria": "gols",
                "escopo": "total",
                "tipo_mercado": "total",
                "formato": "duas_opcoes",
                "ofertas": [{
                    "linha": 2.5,
                    "over": 1.72,
                    "under": 2.10,
                    "fonte": "the_odds_api",
                    "bookmaker": "pinnacle",
                    "cache": False,
                    "coletado_em": "2026-08-24T17:25:00+00:00",
                }],
            }]},
            {"ativa": True, "pareado": True, "anexados": ["gol_ft"]},
        )
        self.servico.the_odds_api.diagnostico.return_value = {
            "ativa": True, "creditos_restantes": 19996,
        }
        odds = {"ao_vivo": []}

        diagnostico = self.servico._complementar_odds_the_odds_api(
            odds,
            {"mandante": "A", "visitante": "B"},
            {"gol_ft", "proximo_gol"},
        )

        self.assertEqual(odds["ao_vivo"][0]["categoria"], "gols")
        self.assertEqual(
            odds["ao_vivo"][0]["ofertas"][0]["fonte"],
            "the_odds_api",
        )
        self.assertTrue(diagnostico["pareado"])
        self.servico.the_odds_api.buscar_mercados.assert_called_once_with(
            {"mandante": "A", "visitante": "B"}, {"gol_ft"}
        )

    def test_the_odds_api_nao_confunde_proximo_gol(self):
        self.servico.the_odds_api = Mock()
        self.servico.the_odds_api.diagnostico.return_value = {
            "ativa": True,
        }
        odds = {"ao_vivo": []}

        diagnostico = self.servico._complementar_odds_the_odds_api(
            odds, {}, {"proximo_gol"}
        )

        self.assertEqual(odds["ao_vivo"], [])
        self.assertEqual(diagnostico["motivo"], "sem_mercado_compativel")
        self.servico.the_odds_api.buscar_mercados.assert_not_called()

    def test_amostra_referencia_ft_fica_fora_das_odds_operacionais(self):
        cliente = Mock()
        cliente.amostragem_referencia_ativa = True
        cliente.reservar_amostragem_referencia.return_value = {
            "autorizada": True,
            "motivo": "amostragem_reservada",
            "aplicacao_sinais": False,
        }
        cliente.buscar_mercados.return_value = (
            {"ao_vivo": [{
                "categoria": "gols", "escopo": "total",
                "tipo_mercado": "total", "formato": "duas_opcoes",
                "fonte": "the_odds_api", "cache": False,
                "ofertas": [{
                    "linha": 2.5, "over": 1.60, "under": 2.30,
                    "fonte": "the_odds_api", "bookmaker": "pinnacle",
                    "coletado_em": "2026-09-11T01:00:00+00:00",
                }],
            }]},
            {"ativa": True, "pareado": True, "consultados": [
                "alternate_totals"
            ], "anexados": ["gol_ft"], "motivo": "oferta_anexada"},
        )
        self.servico.the_odds_api = cliente
        self.servico.configuracao = {"the_odds_api": {
            "amostragem_referencia": {"maximo_ciclo": 2},
        }}
        self.servico._amostras_referencia_odds_ciclo = 0
        self.servico._contexto_amostragem_referencia_ciclo = {
            "ciclo_em": "2026-09-11T02:35:00",
            "posicao_fila": 3,
            "tarefas_ciclo": 8,
            "fila_operacional": "exploracao",
            "liga": "Liga Teste",
            "minuto": 54,
        }
        odds_operacionais = {"pre_jogo": [], "ao_vivo": []}

        sombra, diagnostico = self.servico._amostrar_referencia_odds_sombra(
            {"url": self.url, "mandante": "A", "visitante": "B"},
            {"gol_ft"},
        )

        self.assertEqual([], odds_operacionais["ao_vivo"])
        self.assertEqual(1, len(sombra["ao_vivo"]))
        self.assertTrue(diagnostico["pareado"])
        self.assertFalse(diagnostico["aplicacao_sinais"])
        self.assertFalse(diagnostico["telegram"])
        self.assertEqual(1, self.servico._amostras_referencia_odds_ciclo)
        self.assertEqual(
            "amostragem-referencia-sombra-auditoria-v5",
            diagnostico["auditoria_amostragem"]["versao"],
        )
        self.assertEqual(
            3, diagnostico["auditoria_amostragem"]["posicao_fila"]
        )
        self.assertEqual(
            8, diagnostico["auditoria_amostragem"]["tarefas_ciclo"]
        )
        self.assertTrue(
            diagnostico["auditoria_amostragem"][
                "selecao_antes_resultado"
            ]
        )
        cliente.buscar_mercados.assert_called_once_with(
            {"url": self.url, "mandante": "A", "visitante": "B"},
            {"gol_ft"},
        )

    def test_amostra_referencia_combina_todos_mercados_suportados(self):
        cliente = Mock()
        cliente.amostragem_referencia_ativa = True
        cliente.reservar_amostragem_referencia.return_value = {
            "autorizada": True,
            "motivo": "amostragem_reservada",
            "tipo_amostra": "nova_partida",
        }
        cliente.buscar_mercados.return_value = (
            {"ao_vivo": []},
            {
                "ativa": True,
                "pareado": True,
                "consultados": [
                    "alternate_totals",
                    "alternate_totals_h1",
                    "alternate_totals_corners",
                ],
                "consulta_combinada": True,
                "custo_estimado_creditos": 3,
            },
        )
        self.servico.the_odds_api = cliente
        self.servico.configuracao = {"the_odds_api": {
            "amostragem_referencia": {"maximo_ciclo": 2},
        }}
        self.servico._amostras_referencia_odds_ciclo = 0
        self.servico._amostras_referencia_confirmacoes_ciclo = 0
        jogo = {"url": self.url, "mandante": "A", "visitante": "B"}
        mercados = {
            "gol_ft", "gol_ht", "escanteios_ft_asiatico",
        }

        sombra, diagnostico = self.servico._amostrar_referencia_odds_sombra(
            jogo, mercados, permitir_recuperacao_coorte=True
        )

        self.assertEqual([], sombra["ao_vivo"])
        self.assertEqual(sorted(mercados), diagnostico[
            "mercados_elegiveis_betsapi"
        ])
        self.assertEqual(3, diagnostico["custo_estimado_creditos"])
        self.assertFalse(diagnostico["aplicacao_sinais"])
        self.assertFalse(diagnostico["telegram"])
        self.assertEqual(
            "amostragem-referencia-sombra-auditoria-v5",
            diagnostico["auditoria_amostragem"]["versao"],
        )
        cliente.reservar_amostragem_referencia.assert_called_once_with(
            f"{self.url}|gol_ft",
            custo_estimado=3,
            permitir_confirmacao=True,
            permitir_recuperacao_coorte=True,
        )
        self.assertTrue(diagnostico["recuperacao_coorte_solicitada"])
        cliente.buscar_mercados.assert_called_once_with(jogo, mercados)

    def test_api_football_fornece_referencia_sombra_com_outra_bookmaker(self):
        self.servico.api = Mock()
        self.servico.api.odds_referencia_independente.return_value = ([{
            "mercado": "Match Goals",
            "categoria": "gols",
            "escopo": "total",
            "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "fonte": "api_football",
            "bookmaker": "Pinnacle",
            "idade_segundos": 2.0,
            "cache": True,
            "ofertas": [{
                "linha": 2.5,
                "over": 1.92,
                "under": 1.94,
                "fonte": "api_football",
                "bookmaker": "Pinnacle",
                "idade_segundos": 2.0,
            }],
        }], {
            "versao": "api-football-referencia-sombra-v1",
            "cache": True,
            "motivo": "referencias_independentes_disponiveis",
        })
        jogo = {
            "mandante": "Time A",
            "visitante": "Time B",
            "placar": "1-0",
        }
        confirmacao_api = {
            "fixture_id": 123,
            "similaridade": 1.0,
            "orientacao": "direta",
            "placar": [1, 0],
        }

        referencia, diagnostico = (
            self.servico._amostrar_referencia_api_football_sombra(
                jogo, confirmacao_api, {"gol_ft"}
            )
        )

        self.servico.api.odds_referencia_independente.assert_called_once_with(
            123, "gol_ft", bookmaker_excluido="bet365"
        )
        self.assertTrue(diagnostico["pareado"])
        self.assertFalse(diagnostico["aplicacao_sinais"])
        self.assertFalse(diagnostico["telegram"])
        oferta = referencia["ao_vivo"][0]["ofertas"][0]
        identidade = oferta["identidade_evento"]
        self.assertEqual("api_football", identidade["fonte"])
        self.assertEqual("Time A", identidade["mandante_normalizado"])
        self.assertEqual("Time B", identidade["visitante_normalizado"])
        self.assertEqual("1-0", identidade["placar_normalizado"])
        self.assertEqual("Pinnacle", oferta["bookmaker"])

    def test_api_football_propaga_capacidade_e_consulta_evitada(self):
        self.servico.api = Mock()
        capacidade = {
            "versao": "api-football-referencia-capacidade-v1",
            "identidade_bookmaker_disponivel": False,
            "consulta_referencia_bloqueada": True,
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        self.servico.api.odds_referencia_independente.return_value = (
            [],
            {
                "versao": "api-football-referencia-sombra-v1",
                "mercado": "gol_ft",
                "bookmaker_excluido": "bet365",
                "cache": None,
                "consulta_rede_realizada": False,
                "consulta_rede_evitada": True,
                "motivo": "fonte_live_sem_identidade_bookmaker",
                "capacidade_referencia": capacidade,
                "aplicacao_sinais": False,
                "telegram": False,
                "promocao_automatica": False,
            },
        )

        referencia, diagnostico = (
            self.servico._amostrar_referencia_api_football_sombra(
                {
                    "mandante": "Time A",
                    "visitante": "Time B",
                    "placar": "1-0",
                },
                {
                    "fixture_id": 123,
                    "similaridade": 1.0,
                    "orientacao": "direta",
                    "placar": [1, 0],
                },
                {"gol_ft"},
            )
        )

        self.assertEqual([], referencia["ao_vivo"])
        self.assertEqual(0, diagnostico["consultas_rede_estimadas"])
        self.assertEqual(1, diagnostico["consultas_rede_evitadas"])
        self.assertEqual(
            ["gol_ft"],
            diagnostico["mercados_sem_identidade_bookmaker"],
        )
        self.assertEqual(
            "fonte_live_sem_identidade_bookmaker",
            diagnostico["motivo"],
        )
        self.assertFalse(diagnostico["aplicacao_sinais"])
        self.assertFalse(diagnostico["telegram"])

    def test_amostra_referencia_descarta_liga_antes_de_consumir_reserva(self):
        cliente = Mock()
        cliente.amostragem_referencia_ativa = True
        cliente.diagnosticar_cobertura_competicao.return_value = {
            "versao": "preselecao-cobertura-the-odds-api-v1",
            "executada": True,
            "coberta": False,
            "esportes_candidatos": [],
            "motivo": "competicao_nao_coberta",
            "reserva_consumida": False,
            "aplicacao_sinais": False,
            "telegram": False,
        }
        self.servico.the_odds_api = cliente
        self.servico._amostras_referencia_odds_ciclo = 0

        sombra, diagnostico = self.servico._amostrar_referencia_odds_sombra(
            {
                "url": self.url,
                "mandante": "A",
                "visitante": "B",
                "liga": "Liga sem cobertura",
            },
            {"gol_ft"},
        )

        self.assertEqual([], sombra["ao_vivo"])
        self.assertEqual(
            "competicao_nao_coberta_pre_reserva",
            diagnostico["motivo"],
        )
        self.assertTrue(diagnostico["elegivel_betsapi"])
        self.assertFalse(diagnostico["reserva_consumida"])
        self.assertTrue(
            diagnostico["preselecao_cobertura"]["executada"]
        )
        self.assertEqual(0, self.servico._amostras_referencia_odds_ciclo)
        cliente.reservar_amostragem_referencia.assert_not_called()
        cliente.buscar_mercados.assert_not_called()

    def test_amostra_referencia_descarta_evento_antes_de_reservar(self):
        cliente = Mock()
        cliente.amostragem_referencia_ativa = True
        cliente.diagnosticar_cobertura_competicao.return_value = {
            "versao": "preselecao-cobertura-the-odds-api-v1",
            "executada": True,
            "coberta": True,
            "esportes_candidatos": ["soccer_brazil_campeonato"],
            "motivo": "competicao_coberta",
            "reserva_consumida": False,
        }
        cliente.diagnosticar_cobertura_evento.return_value = {
            "versao": "preselecao-evento-the-odds-api-v1",
            "executada": True,
            "pareado": False,
            "consulta_eventos": True,
            "consulta_odds": False,
            "motivo": "evento_nao_encontrado",
            "reserva_consumida": False,
            "aplicacao_sinais": False,
            "telegram": False,
        }
        self.servico.the_odds_api = cliente
        self.servico._amostras_referencia_odds_ciclo = 0

        sombra, diagnostico = self.servico._amostrar_referencia_odds_sombra(
            {
                "url": self.url,
                "mandante": "A",
                "visitante": "B",
                "liga": "Serie A",
                "pais": "Brazil",
            },
            {"gol_ft"},
        )

        self.assertEqual([], sombra["ao_vivo"])
        self.assertEqual(
            "evento_nao_encontrado_pre_reserva",
            diagnostico["motivo"],
        )
        self.assertTrue(diagnostico["preselecao_evento"]["executada"])
        self.assertFalse(diagnostico["reserva_consumida"])
        self.assertEqual(0, self.servico._amostras_referencia_odds_ciclo)
        cliente.diagnosticar_cobertura_evento.assert_called_once_with(
            {
                "url": self.url,
                "mandante": "A",
                "visitante": "B",
                "liga": "Serie A",
                "pais": "Brazil",
            },
            esportes_candidatos=["soccer_brazil_campeonato"],
        )
        cliente.reservar_amostragem_referencia.assert_not_called()
        cliente.buscar_mercados.assert_not_called()

    def test_amostra_referencia_preserva_reserva_quando_consulta_falha(self):
        cliente = Mock()
        cliente.amostragem_referencia_ativa = True
        cliente.reservar_amostragem_referencia.return_value = {
            "autorizada": True,
            "motivo": "amostragem_reservada",
            "aplicacao_sinais": False,
        }
        cliente.buscar_mercados.side_effect = TimeoutError("indisponível")
        self.servico.the_odds_api = cliente
        self.servico.configuracao = {"the_odds_api": {
            "amostragem_referencia": {"maximo_ciclo": 2},
        }}
        self.servico._amostras_referencia_odds_ciclo = 0

        sombra, diagnostico = self.servico._amostrar_referencia_odds_sombra(
            {"url": self.url, "mandante": "A", "visitante": "B"},
            {"gol_ft"},
        )

        self.assertEqual([], sombra["ao_vivo"])
        self.assertEqual("falha_isolada", diagnostico["motivo"])
        self.assertEqual("TimeoutError", diagnostico["erro"])
        self.assertTrue(diagnostico["elegivel_betsapi"])
        self.assertTrue(diagnostico["reserva"]["autorizada"])
        self.assertFalse(diagnostico["aplicacao_sinais"])
        self.assertFalse(diagnostico["telegram"])

    def test_amostra_referencia_reserva_vaga_para_partida_nova(self):
        cliente = Mock()
        cliente.amostragem_referencia_ativa = True

        def reservar(
            chave,
            custo_estimado=1,
            *,
            permitir_confirmacao=True,
            permitir_recuperacao_coorte=False,
        ):
            if "novo" in chave:
                return {
                    "autorizada": True,
                    "motivo": "amostragem_reservada",
                    "tipo_amostra": "nova_partida",
                }
            if permitir_confirmacao:
                return {
                    "autorizada": True,
                    "motivo": "amostragem_reservada",
                    "tipo_amostra": "confirmacao_temporal",
                }
            return {
                "autorizada": False,
                "motivo": "reserva_diversidade_ciclo",
                "tipo_amostra": "confirmacao_temporal",
            }

        cliente.reservar_amostragem_referencia.side_effect = reservar
        cliente.buscar_mercados.return_value = (
            {"ao_vivo": []},
            {"ativa": True, "pareado": True, "consultados": []},
        )
        self.servico.the_odds_api = cliente
        self.servico.configuracao = {"the_odds_api": {
            "amostragem_referencia": {"maximo_ciclo": 2},
        }}
        self.servico._amostras_referencia_odds_ciclo = 0
        self.servico._amostras_referencia_confirmacoes_ciclo = 0

        _, primeira = self.servico._amostrar_referencia_odds_sombra(
            {"url": "jogo-antigo-1"}, {"gol_ft"}
        )
        _, segunda = self.servico._amostrar_referencia_odds_sombra(
            {"url": "jogo-antigo-2"}, {"gol_ft"}
        )
        _, terceira = self.servico._amostrar_referencia_odds_sombra(
            {"url": "jogo-novo"}, {"gol_ft"}
        )

        self.assertTrue(primeira["reserva"]["autorizada"])
        self.assertEqual("reserva_diversidade_ciclo", segunda["motivo"])
        self.assertTrue(terceira["reserva"]["autorizada"])
        self.assertEqual(2, self.servico._amostras_referencia_odds_ciclo)
        self.assertEqual(
            1, self.servico._amostras_referencia_confirmacoes_ciclo
        )
        self.assertFalse(primeira["aplicacao_sinais"])
        self.assertFalse(terceira["telegram"])

    def test_betsapi_complementa_packball_sem_apagar_origem(self):
        self.servico.betsapi = Mock()
        self.servico.betsapi.buscar_mercados.return_value = (
            {"ao_vivo": [{
                "categoria": "gols",
                "escopo": "total",
                "tipo_mercado": "total",
                "formato": "duas_opcoes",
                "ofertas": [{
                    "linha": 2.5,
                    "over": 1.72,
                    "under": 2.10,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "cache": False,
                    "coletado_em": "2026-08-29T17:25:00+00:00",
                }],
            }]},
            {"ativa": True, "pareado": True, "anexados": ["gol_ft"]},
        )
        self.servico.betsapi.diagnostico.return_value = {
            "ativa": True, "aplicacao_sinais": True,
        }
        odds = {"ao_vivo": [{
            "fonte": "packball", "categoria": "gols",
            "escopo": "total", "tipo_mercado": "outro",
            "formato": "duas_opcoes",
            "ofertas": [{
                "linha": 3.5, "over": 2.0, "under": 1.8,
                "fonte": "packball",
            }],
        }]}

        diagnostico = self.servico._complementar_odds_betsapi(
            odds,
            {"mandante": "A", "visitante": "B", "placar": "1-0"},
            {"gol_ft", "proximo_gol"},
        )

        self.assertTrue(diagnostico["pareado"])
        self.assertEqual(odds["ao_vivo"][0]["ofertas"][0]["fonte"], "packball")
        self.assertEqual(odds["ao_vivo"][0]["ofertas"][1]["fonte"], "betsapi")
        self.servico.betsapi.buscar_mercados.assert_called_once_with(
            {"mandante": "A", "visitante": "B", "placar": "1-0"},
            {"gol_ft", "proximo_gol"},
        )

    def test_diagnostico_cobertura_odds_mede_fallback_real(self):
        sem_odds = {"ao_vivo": []}
        com_odds = {
            "ao_vivo": [{
                "categoria": "gols",
                "fonte": "TheStatsAPI",
                "ofertas": [{"linha": 1.5, "over": 1.8}],
            }],
        }

        atendido = self.servico._diagnosticar_cobertura_odds(
            sem_odds, com_odds
        )
        desnecessario = self.servico._diagnosticar_cobertura_odds(
            com_odds, com_odds
        )

        self.assertTrue(atendido["fallback_necessario"])
        self.assertTrue(atendido["fallback_atendeu"])
        self.assertFalse(atendido["fallback_sem_cobertura"])
        self.assertEqual(
            atendido["fontes_fallback_atenderam"], ["thestatsapi"]
        )
        self.assertEqual(atendido["fontes_finais"], ["thestatsapi"])
        self.assertFalse(desnecessario["fallback_necessario"])
        self.assertTrue(desnecessario["packball_utilizavel"])
        self.assertFalse(atendido["aplicacao_sinais"])

    def test_mescla_packball_principal_e_thestats_fallback_por_linha(self):
        packball = {
            "fonte": "packball", "categoria": "gols",
            "escopo": "total", "tipo_mercado": "outro",
            "formato": "duas_opcoes",
            "ofertas": [{
                "linha": 1.5, "over": 1.80, "under": 2.0,
                "fonte": "packball",
            }],
        }
        thestats = {
            "fonte": "thestatsapi", "categoria": "gols",
            "escopo": "total", "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "ofertas": [
                {
                    "linha": 0.5, "over": 1.75, "under": 2.1,
                    "fonte": "thestatsapi",
                },
                {
                    "linha": 1.5, "over": 1.85, "under": 2.0,
                    "fonte": "thestatsapi",
                },
            ],
        }
        odds = {"ao_vivo": [packball]}

        resumo = self.servico._mesclar_mercados_odds_complementares(
            odds, [thestats]
        )
        com_packball = escolher_over_ao_vivo(
            odds, "gols", total_atual=1
        )
        com_fallback = escolher_over_ao_vivo(
            odds, "gols", total_atual=0
        )

        self.assertEqual(len(odds["ao_vivo"]), 1)
        self.assertEqual(resumo["ofertas"], 2)
        self.assertEqual(com_packball["fonte"], "packball")
        self.assertEqual(com_fallback["fonte"], "thestatsapi")
        self.assertEqual(
            odds["ao_vivo"][0]["fontes_complementares"],
            ["thestatsapi"],
        )

    def test_ordenacao_operacional_evitaria_odd_antiga_de_orense(self):
        odds = {"ao_vivo": [
            {
                "categoria": "gols", "escopo": "total",
                "formato": "duas_opcoes", "fonte": "thestatsapi",
                "ofertas": [{
                    "linha": 2.5, "over": 2.5,
                    "coletado_em": "2026-08-30T20:40:30+00:00",
                    "fonte": "thestatsapi",
                }],
            },
            {
                "categoria": "gols", "escopo": "total",
                "formato": "duas_opcoes", "fonte": "betsapi",
                "ofertas": [{
                    "linha": 2.5, "over": 1.125,
                    "coletado_em": "2026-08-30T20:51:47+00:00",
                    "fonte": "betsapi",
                }],
            },
            {
                "categoria": "gols", "escopo": "total",
                "formato": "duas_opcoes", "fonte": "thestatsapi",
                "ofertas": [{
                    "linha": 2.5, "over": 1.143,
                    "coletado_em": "2026-08-30T20:58:47+00:00",
                    "fonte": "thestatsapi",
                }],
            },
        ]}

        self.servico._ordenar_odds_por_frescor(odds)
        oferta = escolher_over_ao_vivo(odds, "gols", total_atual=2)

        self.assertEqual(oferta["over"], 1.143)
        self.assertEqual(oferta["fonte"], "thestatsapi")
        self.assertEqual(
            oferta["coletado_em"], "2026-08-30T20:58:47+00:00"
        )

    def test_frescor_remove_linha_de_escanteio_ja_substituida(self):
        comum = {
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "fonte": "betsapi",
            "bookmaker": "bet365",
        }
        odds = {"ao_vivo": [
            {
                **comum,
                "coletado_em": "2026-08-31T01:26:32+00:00",
                "cache": False,
                "ofertas": [{
                    "linha": 11.0,
                    "over": 1.95,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "coletado_em": "2026-08-31T01:26:32+00:00",
                    "evento_externo_id": "199420703",
                }],
            },
            {
                **comum,
                "coletado_em": "2026-08-31T01:19:49+00:00",
                "cache": True,
                "ofertas": [{
                    "linha": 9.5,
                    "over": 1.825,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "coletado_em": "2026-08-31T01:19:49+00:00",
                    "evento_externo_id": "199420703",
                }],
            },
        ]}

        self.servico._ordenar_odds_por_frescor(
            odds,
            agora=datetime.fromisoformat("2026-08-31T01:26:34+00:00"),
        )
        oferta = escolher_over_ao_vivo(
            odds, "escanteios", tipo_mercado="asiatico"
        )

        self.assertEqual(len(odds["ao_vivo"]), 1)
        self.assertEqual(oferta["linha"], 11.0)
        self.assertEqual(oferta["over"], 1.95)
        self.assertEqual(
            odds["_metadados"]["ofertas_substituidas_descartadas"], 2
        )

    def test_frescor_remove_oferta_unica_que_ja_envelheceu(self):
        odds = {"ao_vivo": [{
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "fonte": "betsapi",
            "bookmaker": "bet365",
            "ofertas": [{
                "linha": 9.5,
                "over": 1.825,
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "coletado_em": "2026-08-31T01:19:49+00:00",
            }],
        }]}

        self.servico._ordenar_odds_por_frescor(
            odds,
            agora=datetime.fromisoformat("2026-08-31T01:26:34+00:00"),
        )

        self.assertEqual(odds["ao_vivo"][0]["ofertas"], [])
        self.assertIsNone(escolher_over_ao_vivo(
            odds, "escanteios", tipo_mercado="asiatico"
        ))

    def test_mescla_fallback_thestats_em_ht_e_escanteio_por_periodo(self):
        odds = {"ao_vivo": [{
            "fonte": "packball", "categoria": "gols",
            "escopo": "total", "formato": "duas_opcoes",
            "ofertas": [],
            "ofertas_ht": [{
                "linha": 1.5, "over": 3.0, "under": 1.3,
                "fonte": "packball",
            }],
        }, {
            "fonte": "packball", "categoria": "escanteios",
            "escopo": "total", "tipo_mercado": "asiatico",
            "formato": "duas_opcoes", "ofertas": [],
            "ofertas_periodos": {"1T": {
                "formato": "duas_opcoes",
                "ofertas": [{
                    "linha": 5.5, "over": 2.5, "under": 1.5,
                    "fonte": "packball",
                }],
            }},
        }]}
        complementares = [{
            "fonte": "thestatsapi", "categoria": "gols",
            "escopo": "total", "formato": "duas_opcoes",
            "ofertas": [],
            "ofertas_ht": [{
                "linha": 0.5, "over": 1.75, "under": 2.1,
                "fonte": "thestatsapi",
            }],
        }, {
            "fonte": "thestatsapi", "categoria": "escanteios",
            "escopo": "total", "tipo_mercado": "asiatico",
            "formato": "duas_opcoes", "ofertas": [],
            "ofertas_periodos": {"1T": {
                "formato": "duas_opcoes",
                "ofertas": [{
                    "linha": 3.5, "over": 1.9, "under": 1.9,
                    "fonte": "thestatsapi",
                }],
            }},
        }]

        self.servico._mesclar_mercados_odds_complementares(
            odds, complementares
        )
        ht = escolher_over_ht(odds, total_atual=0)
        cantos = escolher_over_periodo(
            odds, "escanteios", "1T", total_periodo_atual=3,
            tipo_mercado="asiatico",
        )

        self.assertEqual(ht["fonte"], "thestatsapi")
        self.assertEqual(cantos["fonte"], "thestatsapi")

    def test_odds_sem_oferta_operacional_nao_adiam_nova_tentativa(self):
        vazias = {"ao_vivo": [], "pre_jogo": []}
        gols = {"ao_vivo": [{
            "categoria": "gols",
            "ofertas": [{"linha": 2.5, "over": 1.8, "under": 2.0}],
        }]}

        self.assertFalse(self.servico._odds_coletadas_com_sucesso(
            True, None, vazias
        ))
        self.assertTrue(self.servico._odds_coletadas_com_sucesso(
            True, None, gols
        ))
        self.assertFalse(self.servico._odds_coletadas_com_sucesso(
            True, RuntimeError("falha"), gols
        ))

    def test_registra_ancoras_v2_controle_antes_da_coleta(self):
        self.servico._registrar_ancoras_exploracao(
            self.banco.conexao
        )

        chaves = {
            linha["chave"] for linha in self.banco.conexao.execute(
                """SELECT chave FROM metadados
                   WHERE chave LIKE 'exploracao_sombra_%'"""
            ).fetchall()
        }

        self.assertIn(
            "exploracao_sombra_definicao:"
            f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}",
            chaves,
        )
        self.assertIn(
            "exploracao_sombra_politica:"
            f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}",
            chaves,
        )

    def test_servico_mantem_v2_e_v3_e_deduplica_por_versao(self):
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-08-11T10:00:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "1-1",
            "status": "70 '",
        })
        self.servico.regra_fingerprints = {"sinais-v6": "fp"}

        def sombra(versao):
            return {
                "mercado": "gol_ft",
                "linha": 2.5,
                "odd": 1.8,
                "pontuacao_tecnica": 70,
                "regra_versao": "sinais-v6",
                "regra_fingerprint": "fp",
                "status": "simulacao",
                "features": {
                    "exploracao_sombra": {"versao": versao}
                },
            }

        v3 = sombra("validacao-v3")
        v2 = sombra("controle-v2")
        with patch(
            "servico_monitor.gerar_exploracoes_sombra",
            return_value=[v3, v2],
        ):
            novas = self.servico._gerar_exploracoes_sombra_novas(
                snapshot, [], {}
            )
            ids = self.banco.salvar_candidatos(snapshot, novas)
            repetidas = self.servico._gerar_exploracoes_sombra_novas(
                snapshot, [], {}
            )

        self.assertEqual(len(ids), 2)
        self.assertEqual(repetidas, [])
        versoes = {
            linha[0] for linha in self.banco.conexao.execute(
                """SELECT json_extract(
                           features_json, '$.exploracao_sombra.versao'
                       )
                   FROM sinais WHERE id IN (?, ?)""",
                ids,
            ).fetchall()
        }
        self.assertEqual(versoes, {"validacao-v3", "controle-v2"})

    def test_exploracao_sombra_deduplica_repeticao_no_mesmo_lote(self):
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-08-11T10:00:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "1-1",
            "status": "70 '",
        })
        self.servico.regra_fingerprints = {"sinais-v6": "fp"}
        sombra = {
            "mercado": "gol_ft", "linha": 2.5, "odd": 1.8,
            "pontuacao_tecnica": 70, "regra_versao": "sinais-v6",
            "regra_fingerprint": "fp", "status": "simulacao",
            "features": {
                "exploracao_sombra": {"versao": "mesma-versao"}
            },
        }
        with patch(
            "servico_monitor.gerar_exploracoes_sombra",
            return_value=[dict(sombra), dict(sombra)],
        ):
            novas = self.servico._gerar_exploracoes_sombra_novas(
                snapshot, [], {}
            )
        self.assertEqual(1, len(novas))
        ids = self.banco.salvar_candidatos(snapshot, novas)
        self.assertEqual(1, len(ids))

    def test_filtro_geral_remove_exploracao_ja_registrada(self):
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-08-11T10:00:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "55 '",
        })
        sombra = {
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.50,
            "pontuacao_tecnica": 80, "regra_versao": "sinais-v6",
            "regra_fingerprint": None, "status": "simulacao",
            "features": {
                "exploracao_sombra": {"versao": "especial-v1"}
            },
        }
        self.banco.salvar_candidatos(snapshot, [sombra])
        base = {
            "mercado": "proximo_gol", "regra_versao": "sinais-v6",
            "status": "rejeitado", "features": {},
        }

        filtrados = self.servico._filtrar_exploracoes_repetidas(
            snapshot, [dict(sombra), dict(base), dict(sombra)]
        )

        self.assertEqual(filtrados, [base])

    def test_foco_usa_pontuacao_do_snapshot_mais_recente(self):
        snapshot_antigo = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:00:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "50 '",
        })
        self.banco.salvar_candidatos(snapshot_antigo, [
            {
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 95,
                "regra_versao": "sinais-v1",
                "status": "rejeitado",
            },
            {
                "mercado": "proximo_gol",
                "linha": "casa",
                "odd": 1.9,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v1",
                "status": "rejeitado",
            },
        ])
        snapshot_recente = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:05:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "55 '",
        })
        self.banco.salvar_candidatos(snapshot_recente, [
            {
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 40,
                "regra_versao": "sinais-v1",
                "status": "rejeitado",
            },
            {
                "mercado": "proximo_gol",
                "linha": "casa",
                "odd": 1.9,
                "pontuacao_tecnica": 50,
                "regra_versao": "sinais-v1",
                "status": "rejeitado",
            },
        ])

        pontuacoes = self.servico._pontuacoes_recentes([
            {"url": self.url}
        ])

        self.assertEqual(pontuacoes[self.url], 50)

    def test_rechecagem_pos_gol_considera_apenas_snapshot_recente(self):
        versao = versao_regra_operacional("proximo_gol")
        antigo = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:00:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "1-0",
            "status": "60 '",
        })
        self.banco.salvar_candidatos(antigo, [{
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 2.0,
            "pontuacao_tecnica": 80,
            "regra_versao": versao,
            "status": "rejeitado",
            "bloqueios": ["gol_recente_aguardar_odds"],
        }])
        recente = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:03:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "1-0",
            "status": "63 '",
        })
        self.banco.salvar_candidatos(recente, [{
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 2.1,
            "pontuacao_tecnica": 70,
            "regra_versao": versao,
            "status": "rejeitado",
            "motivos": ["odds_estabilizadas"],
        }])

        estado = self.servico._estado_prioridades_recentes([
            {"url": self.url}
        ])

        self.assertEqual(estado["pontuacoes"][self.url], 70)
        self.assertNotIn(
            self.url, estado["rechecagens_pos_evento"]
        )

        pos_gol = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:06:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "2-0",
            "status": "66 '",
        })
        self.banco.salvar_candidatos(pos_gol, [{
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 2.3,
            "pontuacao_tecnica": 75,
            "regra_versao": versao,
            "status": "rejeitado",
            "bloqueios": ["gol_recente_aguardar_odds"],
        }])

        atualizado = self.servico._estado_prioridades_recentes([
            {"url": self.url}
        ])
        self.assertIn(
            self.url, atualizado["rechecagens_pos_evento"]
        )

    def test_alerta_entregue_agenda_cotacao_unica_pos_dois_minutos(self):
        instante = datetime(2026, 9, 9, 12, 0, 0)
        snapshot = self.banco.salvar_registro({
            "coletado_em": instante.isoformat(),
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "20 '",
        })
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ht",
            "linha": 0.5,
            "odd": 1.8,
            "pontuacao_tecnica": 80,
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "status": "simulacao",
            "features": {"fonte_odds": "packball"},
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue", instante=instante
        )

        estado = self.servico._estado_prioridades_recentes(
            [{"url": self.url}],
            agora=instante + timedelta(seconds=180),
        )

        acompanhamento = estado["acompanhamentos_preco"][self.url]
        self.assertAlmostEqual(180.0, acompanhamento["idade_segundos"])
        self.assertEqual(["gol_ht"], acompanhamento["mercados"])
        self.assertEqual([], acompanhamento["mercados_api"])
        self.assertEqual(["packball"], acompanhamento["fontes"])
        expirado = self.servico._estado_prioridades_recentes(
            [{"url": self.url}],
            agora=instante + timedelta(seconds=601),
        )
        self.assertNotIn(self.url, expirado["acompanhamentos_preco"])

    def test_alerta_de_fonte_auxiliar_reagenda_o_mesmo_mercado_api(self):
        instante = datetime(2026, 9, 9, 12, 0, 0)
        snapshot = self.banco.salvar_registro({
            "coletado_em": instante.isoformat(),
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "55 '",
        })
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.8,
            "pontuacao_tecnica": 80,
            "regra_versao": "sinais-v6",
            "status": "simulacao",
            "features": {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
            },
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal, "chat:teste", "entregue", instante=instante
        )

        estado = self.servico._estado_prioridades_recentes(
            [{"url": self.url}],
            agora=instante + timedelta(seconds=180),
        )

        acompanhamento = estado["acompanhamentos_preco"][self.url]
        self.assertEqual(["betsapi"], acompanhamento["fontes"])
        self.assertEqual(["gol_ft"], acompanhamento["mercados_api"])

    def test_identifica_candidato_de_gols_que_precisa_revisita_temporal(self):
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:00:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "20 '",
        })
        self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "pontuacao_tecnica": 65,
            "regra_versao": "sinais-v6",
            "status": "rejeitado",
            "bloqueios": [
                "atividade_recente_insuficiente_gols",
                "historico_5min_insuficiente",
                "odd_ao_vivo_indisponivel",
            ],
        }])

        estado = self.servico._estado_prioridades_recentes([
            {"url": self.url}
        ])

        self.assertIn(
            self.url, estado["candidatos_exploracao_gols"]
        )

    def test_impressao_aceita_odd_estruturada_sem_campo_dados(self):
        with patch("builtins.print") as imprimir:
            self.servico._imprimir_jogo(
                {
                    "mandante": "A", "visitante": "B",
                    "placar": "0-0", "status": "60 '",
                },
                {},
                {"ao_vivo": [{"mercado": "Total Gols"}]},
                {},
                None,
                {"apto_para_sinal": True, "pontuacao": 100.0},
            )
        self.assertTrue(any(
            "Total Gols" in str(chamada)
            for chamada in imprimir.call_args_list
        ))

    def test_acompanhamento_odd_recebe_prioridade_ate_perder_elegibilidade(self):
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-08-29T10:20:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "20 '",
        })
        sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ht",
            "linha": 0.5,
            "odd": 1.25,
            "pontuacao_tecnica": 82,
            "regra_versao": "sinais-v6",
            "status": "rejeitado",
            "features": {
                "acompanhamento_odd": {
                    "elegivel_aviso": True,
                    "odd_alvo": 1.40,
                },
            },
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal_id, "-100123:aguardar_odd", "entregue"
        )

        aguardando = self.servico._estado_prioridades_recentes([
            {"url": self.url}
        ])
        self.assertIn(self.url, aguardando["rechecagens_odd_gol"])

        snapshot_fraco = self.banco.salvar_registro({
            "coletado_em": "2026-08-29T10:22:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "22 '",
        })
        self.banco.salvar_candidatos(snapshot_fraco, [{
            "mercado": "gol_ht",
            "linha": 0.5,
            "odd": 1.28,
            "pontuacao_tecnica": 60,
            "regra_versao": "sinais-v6",
            "status": "rejeitado",
            "bloqueios": ["atividade_recente_insuficiente_gols"],
        }])

        perdeu_forca = self.servico._estado_prioridades_recentes([
            {"url": self.url}
        ])
        self.assertNotIn(self.url, perdeu_forca["rechecagens_odd_gol"])

    def test_ciclo_principal_nao_duplica_consulta_do_trabalhador_dedicado(self):
        trabalhador = Mock()
        trabalhador.ativo.return_value = True
        self.servico._trabalhador_acompanhamento_odd = trabalhador
        self.servico._executar_rechecagem_odd_api = Mock(
            side_effect=AssertionError("consulta duplicada")
        )

        resumo = self.servico._rechecar_acompanhamentos_odd_api()

        self.assertEqual(resumo["motivo"], "trabalhador_dedicado_ativo")
        self.servico._executar_rechecagem_odd_api.assert_not_called()

    def test_consulta_forcada_e_executada_dentro_do_trabalhador(self):
        trabalhador = Mock()
        trabalhador.ativo.return_value = True
        self.servico._trabalhador_acompanhamento_odd = trabalhador
        esperado = {
            "consultados": 1,
            "atingiram_alvo": 0,
            "enviados": 0,
            "bloqueados": 0,
        }
        self.servico._executar_rechecagem_odd_api = Mock(
            return_value=esperado
        )
        self.servico._observar_rechecagem_odd_api = Mock()

        resumo = self.servico._rechecar_acompanhamentos_odd_api(
            forcar=True
        )

        self.assertEqual(resumo, esperado)
        self.servico._executar_rechecagem_odd_api.assert_called_once_with(
            forcar=True
        )

    def test_ciclo_principal_reinicia_trabalhador_encerrado(self):
        encerrado = Mock()
        encerrado.ativo.return_value = False
        ativo = Mock()
        ativo.ativo.return_value = True
        self.servico._trabalhador_acompanhamento_odd = encerrado

        def reiniciar():
            self.servico._trabalhador_acompanhamento_odd = ativo
            return {"iniciado": True, "estado": "iniciado"}

        self.servico._iniciar_trabalhador_acompanhamento_odd = Mock(
            side_effect=reiniciar
        )
        self.servico._executar_rechecagem_odd_api = Mock(
            side_effect=AssertionError("fallback desnecessario")
        )

        resumo = self.servico._rechecar_acompanhamentos_odd_api()

        self.assertEqual(resumo["motivo"], "trabalhador_dedicado_ativo")
        self.servico._iniciar_trabalhador_acompanhamento_odd.assert_called_once_with()
        self.servico._executar_rechecagem_odd_api.assert_not_called()

    def _criar_sinal(self):
        snapshot = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:00:00",
                "url": self.url,
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "60 '",
            }
        )
        self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "proximo_gol",
                "linha": "casa",
                "odd": 1.8,
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }],
        )

    def test_busca_eventos_quando_ambos_os_times_marcaram(self):
        self._criar_sinal()
        self.assertTrue(
            self.servico.precisa_eventos_proximo_gol(
                {"url": self.url, "placar": "1-1"}
            )
        )

    def test_nao_gasta_api_quando_so_um_time_marcou(self):
        self._criar_sinal()
        self.assertFalse(
            self.servico.precisa_eventos_proximo_gol(
                {"url": self.url, "placar": "2-0"}
            )
        )

    def test_nao_busca_eventos_sem_sinal_pendente(self):
        self.assertFalse(
            self.servico.precisa_eventos_proximo_gol(
                {"url": self.url, "placar": "1-1"}
            )
        )

    def test_nao_consulta_lista_api_sem_jogo_packball(self):
        self.servico.api = Mock()

        self.assertEqual(self.servico._fixtures_api_para([]), [])

        self.servico.api.jogos_ao_vivo.assert_not_called()

    def test_falha_de_fonte_rejeita_sinal_antes_do_backtest(self):
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": False,
            "motivo": "falha_api_no_ciclo",
        }
        candidatos = [{
            "status": "aprovado",
            "motivos": ["mercado_ao_vivo_disponivel"],
        }]

        estado = self.servico._estado_fontes_para_sinal([])
        bloqueados = self.servico._bloquear_candidatos_por_fontes(
            candidatos, estado
        )

        self.assertEqual(bloqueados, 1)
        self.assertEqual(candidatos[0]["status"], "rejeitado")
        self.assertIn(
            "fontes_operacionais_incompletas", candidatos[0]["motivos"]
        )

    def test_trava_do_ciclo_bloqueia_gateway_imediatamente(self):
        self.servico._operacao_bloqueada_ciclo = True

        resultado = self.servico._validar_operacao_para_alerta_oficial()

        self.assertEqual(resultado, {
            "apto": False,
            "estado": "degradado",
            "motivo": "bloqueio_preservado_no_ciclo",
            "fonte": "ciclo",
        })

    def test_lista_packball_inconsistente_fecha_todo_o_ciclo(self):
        self.servico._operacao_bloqueada_ciclo = False

        inconsistente = self.servico._aplicar_integridade_lista_packball({
            "contador_ao_vivo": 118,
            "jogos_extraidos": 133,
            "lista_consistente": False,
        })

        self.assertTrue(inconsistente)
        self.assertTrue(self.servico._operacao_bloqueada_ciclo)

    def test_lista_packball_confirmada_nao_fecha_o_ciclo(self):
        self.servico._operacao_bloqueada_ciclo = False

        inconsistente = self.servico._aplicar_integridade_lista_packball({
            "contador_ao_vivo": 118,
            "jogos_extraidos": 118,
            "lista_consistente": True,
        })

        self.assertFalse(inconsistente)
        self.assertFalse(self.servico._operacao_bloqueada_ciclo)

    def test_tres_listas_nao_validadas_ativam_pausa_auditavel(self):
        limite = datetime(2026, 8, 1, 14, 0, 0)
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.ativar_pausa.return_value = limite
        self.servico.observabilidade = Mock()

        resultado = self.servico._pausar_lista_packball_nao_validada()

        self.assertEqual(resultado, limite)
        self.servico.controle_packball.ativar_pausa.assert_called_once_with(
            "lista_packball_nao_validada",
            minutos=15,
        )
        chamada = (
            self.servico.observabilidade.circuito_packball_ativado
        )
        chamada.assert_called_once_with(
            "lista_packball_nao_validada",
            limite,
        )

    def test_pausa_persistida_nao_incrementa_falhas_do_ciclo(self):
        self.servico.observabilidade = Mock()
        erro = PackBallPausaPreventivaError(
            "motivo: lista_packball_nao_validada"
        )

        protegida = self.servico._registrar_interrupcao_ciclo(
            0.01, erro
        )

        self.assertTrue(protegida)
        self.servico.observabilidade.ciclo_pausado_packball.assert_called_once_with(
            0.01, erro
        )
        self.servico.observabilidade.ciclo_erro.assert_not_called()

    def test_pausa_persistida_mantem_historico_api_sem_virar_falha(self):
        erro = PackBallPausaPreventivaError(
            "motivo: lista_packball_nao_validada"
        )
        self.servico.pasta = Path.cwd()
        self.servico.preparar = Mock()
        self.servico.observabilidade = Mock()
        self.servico.observabilidade.deve_recuperar_navegador.return_value = (
            False
        )
        self.servico.conectividade = Mock()
        self.servico.conectividade.disponivel.return_value = True
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "restante_segundos": 60.0,
        }
        self.servico.executar_ciclo = Mock(side_effect=erro)
        self.servico._coletar_historico_api_live_durante_pausa_packball = (
            Mock()
        )
        navegador = Mock()
        navegador.is_connected.return_value = True
        contexto = Mock()
        pagina = Mock()
        detalhe = Mock()
        self.servico._abrir_navegador = Mock(return_value=(
            navegador, contexto, pagina, detalhe
        ))

        with (
            patch(
                "servico_monitor.ler_modo_manutencao",
                return_value={"ativo": False},
            ),
            patch.object(
                self.servico,
                "_iniciar_playwright_seguro",
                return_value=nullcontext(Mock()),
            ),
            patch("builtins.print"),
        ):
            self.servico.executar(uma_vez=True, headless=True)

        self.servico._coletar_historico_api_live_durante_pausa_packball.assert_called_once_with(
            "PackBallPausaPreventivaError"
        )
        self.servico.observabilidade.ciclo_pausado_packball.assert_called_once()
        self.servico.observabilidade.ciclo_erro.assert_not_called()

    def test_pausa_inicial_nao_abre_playwright(self):
        self.servico.pasta = Path.cwd()
        self.servico.preparar = Mock()
        self.servico.observabilidade = Mock()
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": True,
            "motivo": "falha_login_packball",
            "restante_segundos": 600.0,
        }
        self.servico._coletar_historico_api_live_durante_pausa_packball = (
            Mock()
        )
        self.servico._iniciar_playwright_seguro = Mock(
            side_effect=AssertionError("Playwright nao deveria iniciar")
        )

        with (
            patch(
                "servico_monitor.ler_modo_manutencao",
                return_value={"ativo": False},
            ),
            patch("builtins.print"),
        ):
            self.servico.executar(uma_vez=True, headless=True)

        self.servico._iniciar_playwright_seguro.assert_not_called()
        self.servico._coletar_historico_api_live_durante_pausa_packball.assert_called_once_with(
            "PackBallPausaPreventivaError"
        )
        self.servico.observabilidade.ciclo_pausado_packball.assert_called_once()
        self.servico.observabilidade.ciclo_erro.assert_not_called()

    def test_trabalhador_de_odds_inicia_antes_do_playwright(self):
        self.servico.pasta = Path.cwd()
        self.servico.preparar = Mock()
        self.servico._aguardar_pausa_packball_antes_navegador = Mock(
            return_value=False
        )
        self.servico._supervisionar_watchdog = Mock()
        self.servico._aguardar_supervisao_inicial = Mock(return_value={
            "estado": "pronto",
            "saudavel": True,
            "duracao_segundos": 0.0,
        })
        self.servico.observabilidade = Mock()
        self.servico._iniciar_trabalhador_acompanhamento_odd = Mock()
        self.servico._parar_trabalhador_acompanhamento_odd = Mock()
        gerenciador = Mock()
        gerenciador.__enter__ = Mock(
            side_effect=PermissionError("pipe do Playwright bloqueado")
        )
        gerenciador.__exit__ = Mock(return_value=False)
        self.servico._iniciar_playwright_seguro = Mock(
            return_value=gerenciador
        )

        with (
            patch(
                "servico_monitor.ler_modo_manutencao",
                return_value={"ativo": False},
            ),
            patch("builtins.print"),
            self.assertRaises(PermissionError),
        ):
            self.servico.executar(uma_vez=False, headless=True)

        self.servico._iniciar_trabalhador_acompanhamento_odd.assert_called_once_with()
        self.servico._parar_trabalhador_acompanhamento_odd.assert_called_once_with()

    def test_pausa_inicial_expira_e_libera_inicializacao_normal(self):
        self.servico.pasta = Path.cwd()
        self.servico.observabilidade = Mock()
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.side_effect = [{
            "ativo": True,
            "motivo": "limite_local_navegacoes",
            "restante_segundos": 30.0,
        }, {
            "ativo": False,
            "restante_segundos": 0.0,
        }]
        self.servico._coletar_historico_api_live_durante_pausa_packball = (
            Mock()
        )
        self.servico._supervisionar_watchdog = Mock()
        self.servico._avaliar_reinicio_runtime_monitor = Mock(
            return_value={
                "solicitado": False,
                "estado_monitor": "atualizado",
                "estado_watchdog": "atualizado",
            }
        )
        self.servico._aguardar_intervalo_interrompivel = Mock(
            return_value=False
        )

        with (
            patch(
                "servico_monitor.ler_modo_manutencao",
                return_value={"ativo": False},
            ),
            patch("builtins.print"),
        ):
            encerrar = (
                self.servico._aguardar_pausa_packball_antes_navegador()
            )

        self.assertFalse(encerrar)
        self.assertEqual(
            self.servico.controle_packball.estado_atual.call_count, 2
        )
        self.servico._coletar_historico_api_live_durante_pausa_packball.assert_called_once_with(
            "PackBallPausaPreventivaError"
        )
        self.servico._supervisionar_watchdog.assert_called_once_with()
        chamada = (
            self.servico._aguardar_intervalo_interrompivel.call_args
        )
        self.assertEqual(chamada.args, (30.0,))
        self.assertTrue(callable(chamada.kwargs["interromper_fn"]))

    def test_lista_invalida_renova_contexto_sem_navegar_durante_pausa(self):
        erro = PackBallListaNaoValidadaError(
            "contador_ao_vivo_ausente"
        )
        self.servico.pasta = Path.cwd()
        self.servico.preparar = Mock()
        self.servico.observabilidade = Mock()
        self.servico.observabilidade.deve_recuperar_navegador.return_value = (
            True
        )
        self.servico.conectividade = Mock()
        self.servico.conectividade.disponivel.return_value = True
        self.servico.executar_ciclo = Mock(side_effect=erro)
        self.servico._coletar_historico_api_live_durante_pausa_packball = (
            Mock()
        )
        limite = datetime(2026, 8, 25, 0, 30, 0)
        self.servico._pausar_lista_packball_nao_validada = Mock(
            return_value=limite
        )
        navegador_antigo = Mock()
        navegador_antigo.is_connected.return_value = True
        navegador_novo = Mock()
        navegador_novo.is_connected.return_value = True
        contexto_antigo, pagina_antiga = Mock(), Mock()
        contexto_novo, pagina_nova = Mock(), Mock()
        self.servico._abrir_navegador = Mock(side_effect=[
            (
                navegador_antigo,
                contexto_antigo,
                pagina_antiga,
                pagina_antiga,
            ),
            (
                navegador_novo,
                contexto_novo,
                pagina_nova,
                pagina_nova,
            ),
        ])

        with (
            patch(
                "servico_monitor.ler_modo_manutencao",
                return_value={"ativo": False},
            ),
            patch.object(
                self.servico,
                "_iniciar_playwright_seguro",
                return_value=nullcontext(Mock()),
            ),
            patch("builtins.print"),
        ):
            self.servico.executar(uma_vez=True, headless=True)

        self.assertEqual(self.servico._abrir_navegador.call_count, 2)
        navegador_antigo.close.assert_called_once_with()
        self.servico._pausar_lista_packball_nao_validada.assert_called_once()
        self.servico.observabilidade.recuperacao.assert_called_once_with(
            "lista ao vivo não validada; contexto renovado sem navegação "
            "durante a pausa"
        )

    def test_deteccao_inicial_do_bloqueio_continua_como_falha(self):
        self.servico.observabilidade = Mock()
        erro = PackBallBloqueadoError(
            "excesso_solicitacoes_packball detectado"
        )

        protegida = self.servico._registrar_interrupcao_ciclo(
            0.02, erro
        )

        self.assertFalse(protegida)
        self.servico.observabilidade.ciclo_erro.assert_called_once_with(
            0.02, erro
        )
        self.servico.observabilidade.ciclo_pausado_packball.assert_not_called()

    def test_falha_do_ciclo_invalida_sinal_pendente_sem_green_red(self):
        snapshot_id = self.banco.salvar_registro({
            "coletado_em": "2026-07-20T12:00:00",
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "60 '",
        })
        sinal_id = self.banco.salvar_candidatos(snapshot_id, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.8,
            "regra_versao": "sinais-v1",
            "status": "aprovado",
            "motivos": ["teste"],
        }])[0]
        self.servico._alertas_pendentes_ciclo = [(
            sinal_id,
            {"status": "aprovado"},
            {"url": self.url},
        )]

        alterados = self.servico._invalidar_alertas_pendentes_ciclo()

        sinal = self.banco.conexao.execute(
            "SELECT status, motivos_json FROM sinais WHERE id=?",
            (sinal_id,),
        ).fetchone()
        self.assertEqual(alterados, 1)
        self.assertEqual(sinal["status"], "rejeitado")
        self.assertIn(
            "bloqueio:operacao_degradada_no_ciclo",
            sinal["motivos_json"],
        )
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM resultados_sinais"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(self.servico._alertas_pendentes_ciclo, [])

    def test_fontes_saudaveis_preservam_sinal(self):
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True,
            "motivo": None,
        }
        candidatos = [{"status": "aprovado", "motivos": []}]

        estado = self.servico._estado_fontes_para_sinal([])
        bloqueados = self.servico._bloquear_candidatos_por_fontes(
            candidatos, estado
        )

        self.assertEqual(bloqueados, 0)
        self.assertEqual(candidatos[0]["status"], "aprovado")

    def test_so_consulta_odds_api_quando_podem_liberar_sinal(self):
        sem_potencial = [{
            "mercado": "gol_ft",
            "pontuacao_tecnica": 64.9,
            "status": "rejeitado",
            "bloqueios": ["odd_ao_vivo_indisponivel"],
        }]
        com_potencial = [{
            "mercado": "gol_ft",
            "pontuacao_tecnica": 65.0,
            "status": "rejeitado",
            "bloqueios": ["odd_ao_vivo_indisponivel"],
        }]
        impedido_por_dado = [{
            "mercado": "gol_ft",
            "pontuacao_tecnica": 90,
            "status": "rejeitado",
            "bloqueios": [
                "odd_ao_vivo_indisponivel",
                "historico_5min_insuficiente",
            ],
        }]

        self.assertEqual(
            self.servico._mercados_com_potencial_para_odds_api(
                sem_potencial
            ),
            set(),
        )
        self.assertEqual(
            self.servico._mercados_com_potencial_para_odds_api(
                com_potencial
            ),
            {"gol_ft"},
        )
        self.assertEqual(
            self.servico._mercados_com_potencial_para_odds_api(
                impedido_por_dado
            ),
            set(),
        )

    def _preparar_processamento_economico(self):
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True,
            "motivo": None,
        }
        self.servico.historico = Mock()
        self.servico.historico.calcular.return_value = {
            "5": {"chutes": [2, 1]},
        }
        self.servico.observabilidade = Mock()
        jogo = {
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "55 '",
        }
        estatisticas = {
            "Chutes": "8-7",
            "Chutes no gol": "3-2",
            "Índice de pressão": "60-40",
            "Escanteios": "4-3",
            "Ataques perigosos": "40-35",
        }
        self.servico._coletar_estatisticas_seguras = Mock(
            return_value=(estatisticas, jogo, None)
        )
        self.servico._coletar_odds_seguras = Mock(
            return_value=({"ao_vivo": []}, None)
        )
        self.servico._complementar_odds_escanteios_ft_api = Mock()
        self.servico._complementar_odds_gols_ft_api = Mock()
        self.servico._complementar_odds_proximo_gol_api = Mock()
        self.servico._imprimir_jogo = Mock()
        self.servico.salvar_registro = Mock(return_value=False)
        self.servico._operacao_bloqueada_ciclo = False
        self.servico._alertas_pendentes_ciclo = []
        return jogo

    def test_processar_jogo_despacha_imediatamente_sem_fila_do_ciclo(self):
        jogo = self._preparar_processamento_economico()
        coletado_em = datetime.now().replace(microsecond=0).isoformat()
        candidato = {
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.8,
            "pontuacao_tecnica": 80.0,
            "probabilidade_calibrada": None,
            "regra_versao": "sinais-v6",
            "motivos": ["oportunidade_teste"],
            "bloqueios": [],
            "qualidade_dados": 100.0,
            "features": {"minuto": 55},
            "status": "aprovado",
        }
        self.servico._coletar_odds_seguras.return_value = ({
            "pre_jogo": [],
            "ao_vivo": [{
                "mercado": "Total Gols",
                "categoria": "gols",
                "escopo": "total",
                "formato": "duas_opcoes",
                "fonte": "packball",
                "coletado_em": coletado_em,
                "cache": False,
                "idade_segundos": 0.0,
                "ofertas": [{
                    "linha": 0.5,
                    "over": 1.8,
                    "under": 2.0,
                }],
            }],
        }, None)
        self.servico.salvar_registro.return_value = 101
        self.servico.backtest = Mock()
        self.servico.backtest.avaliar_snapshot.return_value = 0
        self.servico.alertas = Mock()
        self.servico.alertas.modo_teste = False
        self.servico.alertas.cancelar_por_evento.return_value = 0
        self.servico.calibrador = Mock()
        self.servico.regra_fingerprints = {"sinais-v6": "fp"}
        self.servico._gerar_exploracoes_sombra_novas = Mock(return_value=[])
        self.servico._despachar_alertas = Mock()
        self.servico._adiar_alertas_ciclo = False
        self.servico._alertas_pendentes_ciclo = []

        def salvar_candidatos(_snapshot_id, candidatos, _instante):
            for item in candidatos:
                item["_status_persistido"] = item["status"]
            return [501]

        self.servico.banco.salvar_candidatos = Mock(
            side_effect=salvar_candidatos
        )
        with (
            patch(
                "servico_monitor.diagnosticar_associacao",
                return_value={
                    "associacao": None,
                    "motivo": "sem_associacao",
                },
            ),
            patch(
                "servico_monitor.gerar_candidatos",
                return_value=[candidato],
            ),
            patch(
                "servico_monitor.aplicar_protecao_conversao_gols",
                return_value={
                    "avaliados": 0, "aprovados": 0,
                    "bloqueados": 0, "motivos": {},
                },
            ),
        ):
            self.servico.processar_jogo(None, jogo, [])

        self.servico._despachar_alertas.assert_called_once()
        envios = self.servico._despachar_alertas.call_args.args[0]
        self.assertEqual(len(envios), 1)
        self.assertEqual(envios[0][0], 501)
        self.assertIs(envios[0][1], candidato)
        self.assertEqual(envios[0][2]["url"], jogo["url"])
        self.assertEqual(self.servico._alertas_pendentes_ciclo, [])

    def test_coleta_exclusiva_de_preco_nao_cria_nem_despacha_sinal(self):
        jogo = self._preparar_processamento_economico()
        candidato = {
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.8,
            "pontuacao_tecnica": 85.0,
            "probabilidade_calibrada": None,
            "regra_versao": "sinais-v6",
            "motivos": ["oportunidade_teste"],
            "bloqueios": [],
            "qualidade_dados": 100.0,
            "features": {"minuto": 55},
            "status": "aprovado",
        }
        self.servico.salvar_registro.return_value = 101
        self.servico.backtest = Mock()
        self.servico.backtest.avaliar_snapshot.return_value = 0
        self.servico.alertas = Mock()
        self.servico.alertas.modo_teste = True
        self.servico.alertas.cancelar_por_evento.return_value = 0
        self.servico.banco.salvar_candidatos = Mock()
        self.servico._gerar_exploracoes_sombra_novas = Mock(return_value=[])
        self.servico._despachar_alertas = Mock()

        with (
            patch(
                "servico_monitor.diagnosticar_associacao",
                return_value={
                    "associacao": None,
                    "motivo": "sem_associacao",
                },
            ),
            patch(
                "servico_monitor.gerar_candidatos",
                return_value=[candidato],
            ),
            patch(
                "servico_monitor.aplicar_protecao_conversao_gols",
                return_value={
                    "avaliados": 0, "aprovados": 0,
                    "bloqueados": 0, "motivos": {},
                },
            ),
        ):
            resultado = self.servico.processar_jogo(
                None,
                jogo,
                [],
                somente_acompanhamento_preco=True,
            )

        self.assertTrue(resultado["somente_acompanhamento_preco"])
        self.servico.banco.salvar_candidatos.assert_not_called()
        self.servico._gerar_exploracoes_sombra_novas.assert_not_called()
        self.servico._despachar_alertas.assert_not_called()
        self.servico.backtest.avaliar_snapshot.assert_called_once_with(101)

    def test_packball_sem_linha_usa_thestats_oficial_e_despacha(self):
        jogo = self._preparar_processamento_economico()
        coletado_em = datetime.now().replace(microsecond=0).isoformat()
        self.servico.thestatsapi_aplicacao_sinais_ativa = True
        self.servico.the_odds_api = None
        self.servico._thestatsapi_fusao_ciclo = {jogo["url"]: {
            "fonte": "thestatsapi",
            "packball_url": jogo["url"],
            "coletado_em": coletado_em,
            "placar": [0, 0],
            "minuto": 55,
            "xg_mandante": 1.1,
            "xg_visitante": 0.7,
            "resposta_stats": {"ok": True},
            "resposta_odds": {"ok": True},
            "diagnostico": {"motivo": "associado"},
        }}
        contrato_thestats = {
            "ao_vivo": [{
                "mercado": "TheStatsAPI Bet365 gols totais",
                "categoria": "gols",
                "escopo": "total",
                "tipo_mercado": "total",
                "formato": "duas_opcoes",
                "fonte": "thestatsapi",
                "bookmaker": "Bet365",
                "coletado_em": coletado_em,
                "idade_segundos": 0.0,
                "cache": False,
                "aplicacao_sinais": False,
                "autoriza_sinal": False,
                "ofertas": [{
                    "linha": 0.5,
                    "over": 1.80,
                    "under": 2.0,
                    "fonte": "thestatsapi",
                    "bookmaker": "Bet365",
                    "coletado_em": coletado_em,
                    "idade_segundos": 0.0,
                    "cache": False,
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
        self.servico.salvar_registro.return_value = 101
        self.servico.backtest = Mock()
        self.servico.backtest.avaliar_snapshot.return_value = 0
        self.servico.alertas = Mock()
        self.servico.alertas.modo_teste = False
        self.servico.alertas.cancelar_por_evento.return_value = 0
        self.servico.calibrador = Mock()
        self.servico.regra_fingerprints = {"sinais-v6": "fp"}
        self.servico._gerar_exploracoes_sombra_novas = Mock(return_value=[])
        self.servico._despachar_alertas = Mock()
        self.servico._adiar_alertas_ciclo = False
        self.servico._alertas_pendentes_ciclo = []

        def gerar(_jogo, _stats, _evolucao, odds, _qualidade):
            oferta = escolher_over_ao_vivo(odds, "gols", total_atual=0)
            if oferta is None:
                return [{
                    "mercado": "gol_ft", "linha": None, "odd": None,
                    "pontuacao_tecnica": 65.0,
                    "probabilidade_calibrada": None,
                    "regra_versao": "sinais-v6", "motivos": [],
                    "bloqueios": ["odd_ao_vivo_indisponivel"],
                    "qualidade_dados": 100.0, "features": {},
                    "status": "rejeitado",
                }]
            return [{
                "mercado": "gol_ft", "linha": oferta["linha"],
                "odd": oferta["over"], "pontuacao_tecnica": 80.0,
                "probabilidade_calibrada": None,
                "regra_versao": "sinais-v6",
                "motivos": ["oportunidade_teste"], "bloqueios": [],
                "qualidade_dados": 100.0, "features": {},
                "status": "aprovado",
            }]

        def salvar_candidatos(_snapshot_id, candidatos, _instante):
            for item in candidatos:
                item["_status_persistido"] = item["status"]
            return list(range(501, 501 + len(candidatos)))

        self.servico.banco.salvar_candidatos = Mock(
            side_effect=salvar_candidatos
        )
        with (
            patch(
                "servico_monitor.validar_gate_operacional_thestatsapi",
                return_value={"apto_sombra": True, "motivo": "apto_sombra"},
            ),
            patch(
                "servico_monitor.converter_odds_bet365_contrato_interno",
                return_value=contrato_thestats,
            ),
            patch(
                "servico_monitor.diagnosticar_associacao",
                return_value={
                    "associacao": None, "motivo": "sem_associacao",
                },
            ),
            patch("servico_monitor.gerar_candidatos", side_effect=gerar),
            patch(
                "servico_monitor.filtrar_mercados_operacionais",
                side_effect=lambda itens: itens,
            ),
            patch("servico_monitor.aplicar_politicas_por_mercado"),
            patch("servico_monitor.aplicar_politica_gol_ht"),
            patch("servico_monitor.aplicar_politica_proximo_gol"),
            patch("servico_monitor.aplicar_politica_gols_tempo"),
            patch("servico_monitor.gerar_gols_antecipados", return_value=[]),
            patch(
                "servico_monitor.aplicar_protecao_conversao_gols",
                return_value={
                    "avaliados": 0, "aprovados": 0,
                    "bloqueados": 0, "motivos": {},
                },
            ),
        ):
            resultado = self.servico.processar_jogo(None, jogo, [])

        self.servico._despachar_alertas.assert_called_once()
        envios = self.servico._despachar_alertas.call_args.args[0]
        self.assertEqual(len(envios), 1)
        candidato = envios[0][1]
        self.assertEqual(candidato["fonte_odds"], "thestatsapi")
        self.assertEqual(candidato["bookmaker_odds"], "Bet365")
        self.assertTrue(
            candidato["features"]["fusao_fontes"]["aplicacao_sinais"]
        )
        self.assertEqual(candidato["status"], "aprovado")
        self.assertEqual(
            resultado["thestatsapi_odds"],
            {
                "evidencia_disponivel": True,
                "gate_motivo": "apto_sombra",
                "gate_apto": True,
                "aplicacao_sinais": True,
                "mercados_convertidos": 1,
                "ofertas_anexadas": 1,
                "mercados_anexados": 1,
                "rollback": "THESTATSAPI_APLICACAO_SINAIS_ATIVA=0",
            },
        )
        registro = self.servico.salvar_registro.call_args.args[0]
        self.assertEqual(
            registro["qualidade"]["odds_thestatsapi"],
            resultado["thestatsapi_odds"],
        )

    def test_jogo_fraco_nao_gasta_odds_nem_detalhes_api(self):
        jogo = self._preparar_processamento_economico()
        rejeitado = [{
            "mercado": "gol_ft",
            "pontuacao_tecnica": 50,
            "status": "rejeitado",
            "bloqueios": ["atividade_recente_insuficiente_gols"],
        }]
        associacao = {
            "fixture_id": 10,
            "similaridade": 1.0,
            "eventos": [],
            "status": {"elapsed": 55},
            "placar": [0, 0],
        }
        with (
            patch(
                "servico_monitor.diagnosticar_associacao",
                return_value={"associacao": associacao, "motivo": "associado"},
            ),
            patch(
                "servico_monitor.gerar_candidatos",
                return_value=rejeitado,
            ),
            patch(
                "servico_monitor.filtrar_mercados_operacionais",
                side_effect=lambda itens: itens,
            ),
            patch("servico_monitor.aplicar_politicas_por_mercado"),
        ):
            self.servico.processar_jogo(None, jogo, [])

        self.servico._complementar_odds_gols_ft_api.assert_not_called()
        self.servico.api.estatisticas.assert_not_called()
        self.servico.api.estatisticas_jogadores.assert_not_called()
        registro = self.servico.salvar_registro.call_args.args[0]
        self.assertTrue(registro["_analise_tecnica_acompanhamento_odd"])

    def test_prioridade_asiatica_anexa_oferta_sem_ciclo_logico(self):
        jogo = self._preparar_processamento_economico()
        rejeitado = [{
            "mercado": "escanteios_ft_asiatico",
            "pontuacao_tecnica": 50,
            "status": "rejeitado",
            "bloqueios": ["atividade_recente_insuficiente_escanteios"],
        }]
        associacao = {
            "fixture_id": 10,
            "similaridade": 1.0,
            "eventos": [],
            "status": {"elapsed": 55},
            "placar": [0, 0],
        }
        self.servico._complementar_odds_escanteios_ft_api.return_value = True
        with (
            patch(
                "servico_monitor.diagnosticar_associacao",
                return_value={"associacao": associacao, "motivo": "associado"},
            ),
            patch(
                "servico_monitor.gerar_candidatos",
                return_value=rejeitado,
            ),
            patch(
                "servico_monitor.filtrar_mercados_operacionais",
                side_effect=lambda itens: itens,
            ),
            patch("servico_monitor.aplicar_politicas_por_mercado"),
        ):
            resultado = self.servico.processar_jogo(
                None,
                jogo,
                [],
                odd_asiatica_api_disponivel=True,
            )

        self.servico._complementar_odds_escanteios_ft_api.assert_called_once()
        self.assertTrue(resultado["odd_asiatica_api_priorizada"])
        self.assertTrue(resultado["odd_asiatica_api_anexada"])

    def test_jogo_com_potencial_recebe_analise_api_completa(self):
        jogo = self._preparar_processamento_economico()
        potencial = [{
            "mercado": "gol_ft",
            "pontuacao_tecnica": 65,
            "status": "rejeitado",
            "bloqueios": ["odd_ao_vivo_indisponivel"],
        }]
        aprovado = [{
            "mercado": "gol_ft",
            "pontuacao_tecnica": 70,
            "status": "aprovado",
            "bloqueios": [],
        }]
        associacao = {
            "fixture_id": 10,
            "similaridade": 1.0,
            "eventos": [],
            "status": {"elapsed": 55},
            "placar": [0, 0],
        }
        self.servico.api.estatisticas.return_value = [{"team": {}}]
        self.servico.api.estatisticas_jogadores.return_value = [
            {"team": {}}
        ]
        with (
            patch(
                "servico_monitor.diagnosticar_associacao",
                return_value={"associacao": associacao, "motivo": "associado"},
            ),
            patch(
                "servico_monitor.gerar_candidatos",
                side_effect=[potencial, aprovado, aprovado],
            ),
            patch(
                "servico_monitor.filtrar_mercados_operacionais",
                side_effect=lambda itens: itens,
            ),
            patch("servico_monitor.aplicar_politicas_por_mercado"),
        ):
            self.servico.processar_jogo(None, jogo, [])

        self.servico._complementar_odds_gols_ft_api.assert_called_once()
        self.servico.api.estatisticas.assert_called_once_with(10)
        self.servico.api.estatisticas_jogadores.assert_called_once_with(10)

    def test_enriquece_em_lote_somente_fixtures_associadas(self):
        self.servico.api = Mock()
        fixture_simples = {
            "fixture": {"id": 10, "status": {"elapsed": 55}},
            "teams": {
                "home": {"id": 1, "name": "Time A"},
                "away": {"id": 2, "name": "Time B"},
            },
            "goals": {"home": 1, "away": 0},
        }
        fixture_detalhada = {
            **fixture_simples,
            "statistics": [{"team": {"id": 1}, "statistics": []}],
            "players": [{"team": {"id": 1}, "players": []}],
        }
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = [
            fixture_detalhada
        ]
        tarefas = [{
            "jogo": {
                "mandante": "Time A",
                "visitante": "Time B",
                "placar": "1-0",
                "status": "55 '",
            }
        }]

        enriquecidas, diagnostico = (
            self.servico._enriquecer_fixtures_api_lote(
                tarefas, [fixture_simples]
            )
        )

        self.servico.api.fixtures_ao_vivo_detalhadas.assert_called_once_with(
            [10]
        )
        self.assertIs(enriquecidas[0], fixture_detalhada)
        self.assertEqual(diagnostico["estado"], "completo")
        self.assertEqual(diagnostico["incorporadas"], 1)

    def test_enriquecimento_recupera_fixture_pre_live_causal_omitida(self):
        self.servico.api = Mock()
        fixture_detalhada = {
            "fixture": {
                "id": 456,
                "status": {"elapsed": 18, "short": "1H"},
            },
            "teams": {
                "home": {"id": 1, "name": "San Antonio Bulo Bulo"},
                "away": {"id": 2, "name": "Aurora"},
            },
            "goals": {"home": 0, "away": 0},
            "statistics": [],
        }
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = [
            fixture_detalhada
        ]
        tarefas = [{
            "jogo": {
                "mandante": "San Antonio Bulo Bulo",
                "visitante": "Aurora",
                "placar": "0-0",
                "status": "18 '",
                "pre_live_fixture_id": 456,
                "pre_live_contexto_disponivel": True,
            }
        }]

        enriquecidas, diagnostico = (
            self.servico._enriquecer_fixtures_api_lote(tarefas, [])
        )

        self.servico.api.fixtures_ao_vivo_detalhadas.assert_called_once_with(
            [456]
        )
        self.assertEqual(enriquecidas, [fixture_detalhada])
        self.assertEqual(diagnostico["dicas_pre_live_causais"], 1)
        self.assertEqual(diagnostico["dicas_pre_live_recuperadas"], 1)
        self.assertEqual(diagnostico["dicas_pre_live_rejeitadas"], 0)
        self.assertEqual(tarefas[0]["api_fixture_id_prioridade"], 456)

    def test_enriquecimento_rejeita_fixture_pre_live_ainda_nao_ao_vivo(self):
        self.servico.api = Mock()
        fixture_agendada = {
            "fixture": {
                "id": 456,
                "status": {"elapsed": None, "short": "NS"},
            },
            "teams": {
                "home": {"id": 1, "name": "Time A"},
                "away": {"id": 2, "name": "Time B"},
            },
            "goals": {"home": None, "away": None},
        }
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = [
            fixture_agendada
        ]
        tarefas = [{
            "jogo": {
                "mandante": "Time A", "visitante": "Time B",
                "placar": "0-0", "status": "8 '",
                "pre_live_fixture_id": 456,
                "pre_live_contexto_disponivel": True,
            }
        }]

        enriquecidas, diagnostico = (
            self.servico._enriquecer_fixtures_api_lote(tarefas, [])
        )

        self.assertEqual(enriquecidas, [])
        self.assertEqual(diagnostico["dicas_pre_live_recuperadas"], 0)
        self.assertEqual(diagnostico["dicas_pre_live_rejeitadas"], 1)
        self.assertNotIn("api_fixture_id_prioridade", tarefas[0])

    def test_falha_do_enriquecimento_em_lote_preserva_fixtures_originais(self):
        self.servico.api = Mock()
        self.servico.api.fixtures_ao_vivo_detalhadas.side_effect = (
            RuntimeError("indisponível")
        )
        fixture_simples = {
            "fixture": {"id": 10, "status": {"elapsed": 55}},
            "teams": {
                "home": {"name": "Time A"},
                "away": {"name": "Time B"},
            },
            "goals": {"home": 1, "away": 0},
        }
        tarefas = [{
            "jogo": {
                "mandante": "Time A",
                "visitante": "Time B",
                "placar": "1-0",
                "status": "55 '",
            }
        }]

        enriquecidas, diagnostico = (
            self.servico._enriquecer_fixtures_api_lote(
                tarefas, [fixture_simples]
            )
        )

        self.assertEqual(enriquecidas, [fixture_simples])
        self.assertEqual(diagnostico["estado"], "falha_isolada")

    @staticmethod
    def _massa_enriquecimento(quantidade):
        fixtures = []
        tarefas = []
        for indice in range(1, quantidade + 1):
            token_casa = hashlib.sha256(
                f"casa-{indice}".encode()
            ).hexdigest()[:14]
            token_fora = hashlib.sha256(
                f"fora-{indice}".encode()
            ).hexdigest()[:14]
            nome_casa = f"Casa {token_casa}"
            nome_fora = f"Fora {token_fora}"
            fixtures.append({
                "fixture": {"id": indice, "status": {"elapsed": 55}},
                "teams": {
                    "home": {"name": nome_casa},
                    "away": {"name": nome_fora},
                },
                "goals": {"home": 0, "away": 0},
            })
            tarefas.append({
                "jogo": {
                    "mandante": nome_casa,
                    "visitante": nome_fora,
                    "placar": "0-0",
                    "status": "55 '",
                },
                "em_foco": indice == quantidade,
                "idade_segundos": (
                    None if indice == quantidade - 1 else 360
                ),
            })
        return tarefas, fixtures

    def test_enriquecimento_lote_limita_custo_e_preserva_prioridades(self):
        self.servico.api = Mock()
        self.servico.api.limite_diario_detalhes = 2000
        self.servico.api.consumo_atual.return_value = {
            "restante_seguro_dia": 3000,
            "dia": {"detalhe": 100},
        }
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = []
        tarefas, fixtures = self._massa_enriquecimento(55)

        _, diagnostico = self.servico._enriquecer_fixtures_api_lote(
            tarefas, fixtures
        )

        ids = self.servico.api.fixtures_ao_vivo_detalhadas.call_args.args[0]
        self.assertEqual(len(ids), 40)
        self.assertEqual(ids[:2], [55, 54])
        self.assertEqual(diagnostico["associadas"], 55)
        self.assertEqual(diagnostico["adiadas_capacidade_api"], 15)
        self.assertEqual(diagnostico["chamadas_maximas_estimadas"], 2)

    def test_enriquecimento_inclui_oferta_asiatica_sem_aumentar_lote(self):
        class APIComOfertaAsiatica:
            limite_diario_detalhes = 2000

            def __init__(self):
                self.ids = None
                self.chamadas_odds = 0

            def consumo_atual(self):
                return {
                    "restante_seguro_dia": 3000,
                    "dia": {"detalhe": 100},
                }

            def ofertas_escanteios_asiaticos_ft_por_fixture(self):
                self.chamadas_odds += 1
                return {43: {"linha": 8.5, "over": 1.9}}

            def fixtures_ao_vivo_detalhadas(self, ids):
                self.ids = list(ids)
                return []

        api = APIComOfertaAsiatica()
        self.servico.api = api
        tarefas, fixtures = self._massa_enriquecimento(45)

        _, diagnostico = self.servico._enriquecer_fixtures_api_lote(
            tarefas, fixtures
        )

        self.assertEqual(len(api.ids), 40)
        self.assertIn(43, api.ids)
        self.assertEqual(api.chamadas_odds, 1)
        self.assertEqual(diagnostico["ofertas_asiaticas_disponiveis"], 1)
        self.assertEqual(diagnostico["solicitadas_com_oferta_asiatica"], 1)
        self.assertEqual(diagnostico["chamadas_maximas_estimadas"], 2)

    def test_enriquecimento_lote_e_adiado_perto_da_reserva(self):
        self.servico.api = Mock()
        self.servico.api.limite_diario_detalhes = 2000
        self.servico.api.consumo_atual.return_value = {
            "restante_seguro_dia": 50,
            "dia": {"detalhe": 100},
        }
        tarefas, fixtures = self._massa_enriquecimento(5)

        enriquecidas, diagnostico = (
            self.servico._enriquecer_fixtures_api_lote(
                tarefas, fixtures
            )
        )

        self.assertEqual(enriquecidas, fixtures)
        self.servico.api.fixtures_ao_vivo_detalhadas.assert_not_called()
        self.assertEqual(diagnostico["estado"], "adiado_capacidade_api")
        self.assertEqual(diagnostico["limite_efetivo"], 0)

    def test_historico_api_live_reaproveita_lote_sem_nova_consulta(self):
        tarefas = [{
            "jogo": {"url": self.url},
            "api_fixture_id_prioridade": 123,
            "api_orientacao_prioridade": "direta",
        }]
        fixtures = [{
            "fixture": {
                "id": 123,
                "status": {"elapsed": 28, "short": "1H"},
            },
            "teams": {"home": {"id": 1}, "away": {"id": 2}},
            "statistics": [
                {
                    "team": {"id": 1},
                    "statistics": [
                        {"type": "Total Shots", "value": 7},
                        {"type": "Shots on Goal", "value": 3},
                        {"type": "Corner Kicks", "value": 2},
                    ],
                },
                {
                    "team": {"id": 2},
                    "statistics": [
                        {"type": "Total Shots", "value": 4},
                        {"type": "Shots on Goal", "value": 1},
                        {"type": "Corner Kicks", "value": 1},
                    ],
                },
            ],
        }]

        diagnostico = self.servico._persistir_historico_api_live_lote(
            tarefas, fixtures
        )
        linha = self.banco.conexao.execute(
            "SELECT * FROM historico_api_live"
        ).fetchone()

        self.assertTrue(diagnostico["saudavel"])
        self.assertEqual(diagnostico["normalizados"], 1)
        self.assertEqual(diagnostico["chamadas_api_adicionais"], 0)
        self.assertEqual(diagnostico["navegacoes_packball_adicionais"], 0)
        self.assertFalse(diagnostico["aplicacao_sinais"])
        self.assertEqual(linha["fixture_id"], 123)
        self.assertEqual(linha["chutes_gol_mandante"], 3.0)

    def test_enriquecimento_coleta_stats_resgate_com_limite_e_sombra(self):
        self.servico.api = Mock()
        self.servico.api.limite_diario_detalhes = 2000
        self.servico.api.consumo_atual.return_value = {
            "restante_seguro_dia": 3000,
            "dia": {"detalhe": 100},
        }
        tarefas, fixtures = self._massa_enriquecimento(3)
        for indice, tarefa in enumerate(tarefas, 1):
            tarefa["jogo"]["url"] = f"https://packball.test/{indice}"
            tarefa["jogo"]["status"] = "55'"
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = fixtures
        self.servico.api.estatisticas.return_value = [
            {
                "team": {"id": 1},
                "statistics": [
                    {"type": "Total Shots", "value": 7},
                    {"type": "Shots on Goal", "value": 3},
                    {"type": "Corner Kicks", "value": 2},
                ],
            },
            {
                "team": {"id": 2},
                "statistics": [
                    {"type": "Total Shots", "value": 4},
                    {"type": "Shots on Goal", "value": 1},
                    {"type": "Corner Kicks", "value": 1},
                ],
            },
        ]

        with patch.dict(
            os.environ, {"API_STATS_RESGATE_MAX_CICLO": "2"}
        ):
            enriquecidas, diagnostico = (
                self.servico._enriquecer_fixtures_api_lote(
                    tarefas, fixtures
                )
            )

        self.assertEqual(2, diagnostico["stats_resgate_selecionadas"])
        self.assertEqual(2, diagnostico["stats_resgate_consultadas"])
        self.assertEqual(2, diagnostico["stats_resgate_com_dados"])
        self.assertFalse(diagnostico["stats_resgate_aplicacao_sinais"])
        self.assertEqual(
            "API_STATS_RESGATE_MAX_CICLO=0",
            diagnostico["stats_resgate_rollback"],
        )
        self.assertEqual(2, sum(
            bool(item.get("statistics")) for item in enriquecidas
        ))

    def test_enriquecimento_nao_consulta_stats_fora_janela(self):
        self.servico.api = Mock()
        self.servico.api.limite_diario_detalhes = 2000
        self.servico.api.consumo_atual.return_value = {
            "restante_seguro_dia": 3000,
            "dia": {"detalhe": 100},
        }
        tarefas, fixtures = self._massa_enriquecimento(1)
        tarefas[0]["jogo"].update({
            "url": "https://packball.test/1", "status": "35'"
        })
        fixtures[0]["fixture"]["status"]["elapsed"] = 35
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = fixtures

        _, diagnostico = self.servico._enriquecer_fixtures_api_lote(
            tarefas, fixtures
        )

        self.assertEqual(0, diagnostico["stats_resgate_selecionadas"])
        self.servico.api.estatisticas.assert_not_called()

    def test_falha_historico_api_live_e_isolada_dos_sinais(self):
        banco_real = self.servico.banco
        self.servico.banco = Mock()
        self.servico.banco.salvar_historico_api_live.side_effect = (
            RuntimeError("temporaria")
        )
        try:
            diagnostico = self.servico._persistir_historico_api_live_lote(
                [], []
            )
        finally:
            self.servico.banco = banco_real

        self.assertFalse(diagnostico["saudavel"])
        self.assertEqual(diagnostico["estado"], "falha_isolada")
        self.assertFalse(diagnostico["aplicacao_sinais"])

    def test_pausa_packball_mantem_historico_api_sem_efeitos_operacionais(self):
        agora = datetime(2026, 8, 10, 21, 40)
        self.banco.salvar_registro({
            "coletado_em": (agora - timedelta(minutes=2)).isoformat(),
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "30 '",
            "confirmacao_api": {
                "fixture_id": 123,
                "orientacao": "direta",
            },
        })
        fixture = {
            "fixture": {
                "id": 123,
                "status": {"elapsed": 32, "short": "1H"},
            },
            "teams": {"home": {"id": 1}, "away": {"id": 2}},
            "statistics": [
                {
                    "team": {"id": 1},
                    "statistics": [
                        {"type": "Total Shots", "value": 7},
                        {"type": "Shots on Goal", "value": 3},
                        {"type": "Corner Kicks", "value": 2},
                    ],
                },
                {
                    "team": {"id": 2},
                    "statistics": [
                        {"type": "Total Shots", "value": 4},
                        {"type": "Shots on Goal", "value": 1},
                        {"type": "Corner Kicks", "value": 1},
                    ],
                },
            ],
        }
        self.servico.api = Mock()
        self.servico.api.limite_diario_detalhes = 2000
        self.servico.api.consumo_atual.return_value = {
            "restante_seguro_dia": 3000,
            "dia": {"detalhe": 100},
        }
        self.servico.api.jogos_ao_vivo.return_value = [fixture]
        self.servico.api.fixtures_ao_vivo_detalhadas.return_value = [fixture]
        self.servico.observabilidade = Mock()
        self.servico._alertas_pendentes_ciclo = []
        tabelas_operacionais = (
            "sinais", "resultados_sinais", "calibracoes",
            "entregas_alertas", "notificacoes_operacionais",
        )
        antes = {
            tabela: self.banco.conexao.execute(
                f"SELECT COUNT(*) FROM {tabela}"
            ).fetchone()[0]
            for tabela in tabelas_operacionais
        }

        primeiro = (
            self.servico
            ._coletar_historico_api_live_durante_pausa_packball(
                "PackBallBloqueadoError", agora=agora
            )
        )
        segundo = (
            self.servico
            ._coletar_historico_api_live_durante_pausa_packball(
                "PackBallBloqueadoError", agora=agora
            )
        )
        depois = {
            tabela: self.banco.conexao.execute(
                f"SELECT COUNT(*) FROM {tabela}"
            ).fetchone()[0]
            for tabela in tabelas_operacionais
        }

        self.assertTrue(self.servico._operacao_bloqueada_ciclo)
        self.assertEqual(primeiro["estado"], "persistido")
        self.assertEqual(primeiro["inseridos"], 1)
        self.assertEqual(segundo["inseridos"], 0)
        self.assertEqual(segundo["duplicados"], 1)
        self.assertFalse(primeiro["aplicacao_sinais"])
        self.assertEqual(antes, depois)
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM historico_api_live"
            ).fetchone()[0],
            1,
        )

    def test_pausa_packball_respeita_reserva_api_sem_chamar_rede(self):
        agora = datetime(2026, 8, 10, 21, 40)
        self.banco.salvar_registro({
            "coletado_em": (agora - timedelta(minutes=2)).isoformat(),
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "confirmacao_api": {
                "fixture_id": 123,
                "orientacao": "direta",
            },
        })
        self.servico.api = Mock()
        self.servico.api.limite_diario_detalhes = 2000
        self.servico.api.consumo_atual.return_value = {
            "restante_seguro_dia": 50,
            "dia": {"detalhe": 100},
        }
        self.servico.observabilidade = Mock()
        self.servico._alertas_pendentes_ciclo = []

        resultado = (
            self.servico
            ._coletar_historico_api_live_durante_pausa_packball(
                "PackBallListaNaoValidadaError", agora=agora
            )
        )

        self.assertEqual(resultado["estado"], "adiado_capacidade_api")
        self.assertTrue(resultado["operacao_bloqueada"])
        self.servico.api.jogos_ao_vivo.assert_not_called()
        self.servico.api.fixtures_ao_vivo_detalhadas.assert_not_called()
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM historico_api_live"
            ).fetchone()[0],
            0,
        )

    def test_pausa_packball_sem_cota_confirmada_nao_chama_rede(self):
        agora = datetime(2026, 8, 10, 21, 40)
        self.banco.salvar_registro({
            "coletado_em": (agora - timedelta(minutes=2)).isoformat(),
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
            "confirmacao_api": {
                "fixture_id": 123,
                "orientacao": "direta",
            },
        })
        self.servico.api = Mock()
        self.servico.api.limite_diario_detalhes = 2000
        self.servico.api.consumo_atual.side_effect = RuntimeError(
            "cota indisponivel"
        )
        self.servico.observabilidade = Mock()
        self.servico._alertas_pendentes_ciclo = []

        resultado = (
            self.servico
            ._coletar_historico_api_live_durante_pausa_packball(
                "PackBallPausaPreventivaError", agora=agora
            )
        )

        self.assertEqual(
            resultado["estado"], "adiado_cota_api_nao_confirmada"
        )
        self.assertTrue(resultado["operacao_bloqueada"])
        self.servico.api.jogos_ao_vivo.assert_not_called()
        self.servico.api.fixtures_ao_vivo_detalhadas.assert_not_called()
        self.assertEqual(
            self.banco.conexao.execute(
                "SELECT COUNT(*) FROM historico_api_live"
            ).fetchone()[0],
            0,
        )

    def test_anexa_evolucao_api_e_compara_em_sombra(self):
        agora = datetime(2026, 8, 9, 12, 0)
        base = {
            "fixture_id": 123,
            "packball_url": self.url,
            "minuto": 30,
            "periodo": "primeiro_tempo",
            "orientacao": "direta",
            "chutes_mandante": 4,
            "chutes_visitante": 2,
            "chutes_gol_mandante": 2,
            "chutes_gol_visitante": 1,
            "escanteios_mandante": 1,
            "escanteios_visitante": 0,
            "xg_mandante": 0.5,
            "xg_visitante": 0.2,
            "completo": True,
            "fonte": "api_football",
        }
        anterior = {
            **base,
            "coletado_em": (agora - timedelta(minutes=5)).isoformat(),
        }
        atual = {
            **base,
            "coletado_em": agora.isoformat(),
            "chutes_mandante": 7,
            "chutes_visitante": 3,
            "escanteios_mandante": 2,
        }
        self.banco.salvar_historico_api_live(
            [anterior, atual], agora=agora
        )

        contexto = self.servico._anexar_historico_api_live_contexto(
            {"cobertura": {}},
            {"fixture_id": 123},
            {"url": self.url},
            {"5": {"chutes": [3, 1], "escanteios": [1, 0]}},
            agora,
        )

        self.assertEqual(
            contexto["evolucao_temporal_api_live"]["5"]["chutes"],
            [3, 1],
        )
        comparacao = contexto["comparacao_temporal_packball_api"]
        self.assertEqual(comparacao["total"], 2)
        self.assertEqual(comparacao["taxa_concordancia"], 1.0)
        self.assertFalse(comparacao["aplicacao_sinais"])
        self.assertTrue(
            contexto["cobertura"]["comparacao_temporal_packball_api"]
        )

    def test_prioriza_exploracao_com_estatisticas_api_sem_nova_consulta(self):
        tarefas = [
            {
                "jogo": {"url": "baixa"},
                "em_foco": False,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "alta"},
                "em_foco": False,
                "api_fixture_id_prioridade": 2,
            },
        ]
        fixtures = [
            {
                "fixture": {"id": 1, "status": {"elapsed": 55}},
                "statistics": [],
            },
            {
                "fixture": {"id": 2, "status": {"elapsed": 60}},
                "statistics": [{
                    "statistics": [
                        {"type": "Shots on Goal", "value": 7},
                        {"type": "Total Shots", "value": 18},
                        {"type": "Corner Kicks", "value": 8},
                        {"type": "expected_goals", "value": "2.1"},
                    ]
                }],
            },
        ]

        ordenadas, diagnostico = (
            self.servico._priorizar_tarefas_por_api(tarefas, fixtures)
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "alta")
        self.assertGreater(
            ordenadas[0]["prioridade_api_lote"],
            ordenadas[1]["prioridade_api_lote"],
        )
        self.assertEqual(diagnostico["associadas_pontuadas"], 2)
        self.assertEqual(diagnostico["com_estatisticas"], 1)
        self.assertTrue(diagnostico["sem_solicitacoes_extras"])

    def test_prioriza_liga_de_gols_na_exploracao_congestionada(self):
        tarefas = [
            {
                "jogo": {"url": "liga-fraca", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "pontuacao_indicadores_lista": 30,
                "prioridade_liga_gols": 20,
            },
            {
                "jogo": {"url": "liga-forte", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "pontuacao_indicadores_lista": 30,
                "prioridade_liga_gols": 55,
            },
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        self.assertEqual("liga-forte", ordenadas[0]["jogo"]["url"])
        self.assertEqual(2, diagnostico["ligas_gols_pontuadas"])
        self.assertEqual(55, diagnostico["maior_pontuacao_liga_gols"])

    def test_reserva_preco_pos_alerta_mesmo_fora_da_janela_de_sinais(self):
        tarefas = [{
            "jogo": {"url": "preco-pos-alerta", "status": "88 '"},
            "em_foco": True,
            "acompanhamento_preco": True,
            "acompanhamento_preco_dados": {
                "idade_segundos": 540,
                "mercados": ["gol_ft"],
            },
            "coletar_odds": True,
            "idade_segundos": 120,
            "pontuacao_indicadores_lista": 0,
        }]
        for indice in range(1, 15):
            tarefas.append({
                "jogo": {"url": f"acionavel-{indice}", "status": "60 '"},
                "em_foco": indice <= 3,
                "idade_segundos": 120,
                "pontuacao_indicadores_lista": 20 + indice,
                "prioridade_liga_gols": 20 + indice,
            })

        with patch.object(
            self.servico,
            "_janelas_temporais_projetadas",
            return_value=set(),
        ):
            ordenadas, diagnostico = (
                self.servico._priorizar_tarefas_por_api(tarefas, [])
            )

        self.assertIn(
            "preco-pos-alerta",
            [item["jogo"]["url"] for item in ordenadas[:3]],
        )
        self.assertEqual(15, len(ordenadas))
        self.assertEqual(1, diagnostico["acompanhamentos_preco_disponiveis"])
        self.assertTrue(diagnostico["acompanhamento_preco_reservado"])
        self.assertTrue(
            diagnostico["acompanhamento_preco_nas_tres_primeiras"]
        )
        self.assertTrue(
            diagnostico[
                "acompanhamento_preco_reservado_fora_janela_sinais"
            ]
        )
        self.assertEqual(
            540.0,
            diagnostico[
                "acompanhamento_preco_reservado_idade_segundos"
            ],
        )

    def test_reserva_melhor_liga_quando_outras_reservas_ocupam_topo(self):
        tarefas = []
        for indice in range(15):
            tarefas.append({
                "jogo": {
                    "url": f"jogo-{indice}",
                    "status": "60 '",
                },
                "em_foco": indice == 0,
                "rechecagem_pos_evento": indice == 0,
                "idade_segundos": 100,
                "pontuacao_indicadores_lista": 20,
                "prioridade_liga_gols": 20,
            })
        tarefas[4]["jogo"]["url"] = "liga-forte"
        tarefas[4]["prioridade_liga_gols"] = 90
        tarefas[3]["api_fixture_id_prioridade"] = 33
        fixture = {
            "fixture": {"id": 33, "status": {"elapsed": 60}},
            "statistics": [{"statistics": [
                {"type": "Shots on Goal", "value": 7},
                {"type": "Total Shots", "value": 18},
            ]}],
        }

        def janelas(tarefa, agora=None):
            url = tarefa["jogo"]["url"]
            if url == "jogo-1":
                return {5}
            if url == "jogo-2":
                return {10}
            return set()

        with patch.object(
            self.servico,
            "_janelas_temporais_projetadas",
            side_effect=janelas,
        ):
            ordenadas, diagnostico = (
                self.servico._priorizar_tarefas_por_api(
                    tarefas, [fixture]
                )
            )

        self.assertIn(
            "liga-forte",
            [item["jogo"]["url"] for item in ordenadas[:4]],
        )
        self.assertTrue(diagnostico["liga_gols_reservada"])
        self.assertEqual(90, diagnostico["liga_gols_reservada_score"])
        self.assertTrue(
            diagnostico["liga_gols_reservada_nas_quatro_primeiras"]
        )
        self.assertFalse(ordenadas[0].get("reserva_liga_gols", False))

    def test_prioriza_radar_da_lista_quando_detalhe_ainda_nao_existe(self):
        tarefas = [
            {
                "jogo": {
                    "url": "radar-fraco",
                    "status": "60 '",
                    "indicadores_lista": {"campos": {
                        "indice_de_pressao_ult_10_minutos": {},
                    }},
                },
                "em_foco": False,
                "idade_segundos": 100,
                "pontuacao_indicadores_lista": 10,
            },
            {
                "jogo": {
                    "url": "radar-forte",
                    "status": "60 '",
                    "indicadores_lista": {"campos": {
                        "indice_de_pressao_ult_10_minutos": {},
                        "expectativa_de_gols_para_os_proximos_10_minutos": {},
                    }},
                },
                "em_foco": False,
                "idade_segundos": 100,
                "pontuacao_indicadores_lista": 70,
            },
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "radar-forte")
        self.assertEqual(diagnostico["indicadores_lista_disponiveis"], 2)
        self.assertEqual(
            diagnostico["maior_pontuacao_indicadores_lista"], 70
        )
        self.assertEqual(
            diagnostico["indicadores_lista_nas_quatro_primeiras"], 2
        )
        self.assertEqual(
            diagnostico["campos_indicadores_lista"],
            [
                "expectativa_de_gols_para_os_proximos_10_minutos",
                "indice_de_pressao_ult_10_minutos",
            ],
        )

    def test_priorizacao_api_preserva_pre_live_confirmado_no_lote_real(self):
        tarefas = [
            {
                "jogo": {"url": "foco", "status": "60 '"},
                "em_foco": True,
                "idade_segundos": 100,
                "pontuacao_indicadores_lista": 90,
            },
        ]
        tarefas.extend({
            "jogo": {"url": f"radar-{indice}", "status": "60 '"},
            "em_foco": False,
            "idade_segundos": 100,
            "pontuacao_indicadores_lista": 80 - indice,
        } for indice in range(5))
        tarefas.append({
            "jogo": {"url": "pre-live", "status": "60 '"},
            "em_foco": False,
            "idade_segundos": 100,
            "pontuacao_indicadores_lista": 0,
            "pre_live_prioritario": True,
            "pre_live_confirmado": True,
        })

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "foco")
        self.assertEqual(ordenadas[1]["jogo"]["url"], "pre-live")
        self.assertTrue(diagnostico["pre_live_reservado"])
        self.assertEqual(
            diagnostico["tipo_prioridade_pre_live"], "confirmado"
        )
        self.assertTrue(diagnostico["pre_live_nas_quatro_primeiras"])

    def test_prioriza_fixture_com_odd_asiatica_global_sem_navegacao_extra(self):
        class APIComOdds:
            def __init__(self):
                self.chamadas = 0

            def fixtures_com_odds_escanteios_asiaticos_ft(self):
                self.chamadas += 1
                return {2}

        api = APIComOdds()
        self.servico.api = api
        tarefas = [
            {
                "jogo": {"url": "sem-odd", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "com-odd", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 2,
            },
        ]
        fixtures = [
            {"fixture": {"id": 1, "status": {"elapsed": 60}}},
            {"fixture": {"id": 2, "status": {"elapsed": 60}}},
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "com-odd")
        self.assertEqual(api.chamadas, 1)
        self.assertEqual(diagnostico["fixtures_odds_asiaticas_api"], 1)
        self.assertEqual(diagnostico["tarefas_com_odds_asiaticas_api"], 1)
        self.assertTrue(diagnostico["odd_asiatica_api_nas_quatro_primeiras"])
        self.assertTrue(diagnostico["sem_navegacoes_packball_extras"])
        self.assertFalse(diagnostico["sem_solicitacoes_extras"])

    def test_prioriza_linha_asiatica_que_exige_um_escanteio(self):
        class APIComOfertas:
            def __init__(self):
                self.chamadas = 0

            def ofertas_escanteios_asiaticos_ft_por_fixture(self):
                self.chamadas += 1
                return {
                    1: {"linha": 10.5, "over": 1.9},
                    2: {"linha": 3.5, "over": 1.85},
                }

        api = APIComOfertas()
        self.servico.api = api
        tarefas = [
            {
                "jogo": {"url": "linha-distante", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "alvo-um-canto", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 2,
            },
        ]
        fixtures = [
            {
                "fixture": {"id": 1, "status": {"elapsed": 60}},
                "statistics": [
                    {"statistics": [
                        {"type": "Corner Kicks", "value": 1},
                        {"type": "Shots on Goal", "value": 8},
                    ]},
                    {"statistics": [
                        {"type": "Corner Kicks", "value": 1},
                        {"type": "Shots on Goal", "value": 8},
                    ]},
                ],
            },
            {
                "fixture": {"id": 2, "status": {"elapsed": 60}},
                "statistics": [
                    {"statistics": [
                        {"type": "Corner Kicks", "value": 2},
                    ]},
                    {"statistics": [
                        {"type": "Corner Kicks", "value": 1},
                    ]},
                ],
            },
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "alvo-um-canto")
        self.assertTrue(
            ordenadas[0]["odd_asiatica_api_alvo_um_escanteio"]
        )
        self.assertEqual(ordenadas[0]["escanteios_atuais_api"], 3.0)
        self.assertEqual(api.chamadas, 1)
        self.assertEqual(
            diagnostico["tarefas_asiaticas_alvo_um_escanteio"], 1
        )
        self.assertTrue(
            diagnostico["alvo_um_escanteio_nas_quatro_primeiras"]
        )

    def test_priorizacao_api_preserva_foco_e_vaga_de_exploracao(self):
        tarefas = [
            {
                "jogo": {"url": "vaga-reservada"},
                "em_foco": False,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "foco"},
                "em_foco": True,
                "api_fixture_id_prioridade": 2,
            },
            {
                "jogo": {"url": "exploracao-forte"},
                "em_foco": False,
                "api_fixture_id_prioridade": 3,
            },
        ]
        fixtures = [
            {"fixture": {"id": 1, "status": {"elapsed": 5}}},
            {"fixture": {"id": 2, "status": {"elapsed": 60}}},
            {
                "fixture": {"id": 3, "status": {"elapsed": 60}},
                "statistics": [{"statistics": [
                    {"type": "Shots on Goal", "value": 10},
                ]}],
            },
        ]

        ordenadas, _ = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(
            [item["jogo"]["url"] for item in ordenadas],
            ["vaga-reservada", "foco", "exploracao-forte"],
        )

    def test_priorizacao_reserva_uma_partida_realmente_inedita(self):
        tarefas = [
            {
                "jogo": {"url": "foco"},
                "em_foco": True,
                "idade_segundos": 300,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "revisita-forte"},
                "em_foco": False,
                "idade_segundos": 500,
                "api_fixture_id_prioridade": 2,
            },
            {
                "jogo": {"url": "nova-fraca"},
                "em_foco": False,
                "idade_segundos": None,
                "api_fixture_id_prioridade": 3,
            },
            {
                "jogo": {"url": "nova-forte"},
                "em_foco": False,
                "idade_segundos": None,
                "api_fixture_id_prioridade": 4,
            },
        ]
        fixtures = [
            {"fixture": {"id": 1, "status": {"elapsed": 60}}},
            {
                "fixture": {"id": 2, "status": {"elapsed": 60}},
                "statistics": [{"statistics": [
                    {"type": "Shots on Goal", "value": 10},
                ]}],
            },
            {"fixture": {"id": 3, "status": {"elapsed": 15}}},
            {
                "fixture": {"id": 4, "status": {"elapsed": 55}},
                "statistics": [{"statistics": [
                    {"type": "Shots on Goal", "value": 4},
                ]}],
            },
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "nova-fraca")
        self.assertEqual(diagnostico["novas_disponiveis"], 2)
        self.assertTrue(diagnostico["nova_reservada"])
        self.assertTrue(diagnostico["nova_gol_ht_reservada"])
        self.assertTrue(diagnostico["sem_solicitacoes_extras"])

    def test_priorizacao_reserva_seguimento_temporal_quando_foco_nao_cobre(self):
        tarefas = [
            {
                "jogo": {"url": "foco-antigo"},
                "em_foco": True,
                "idade_segundos": 1800,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "nova"},
                "em_foco": False,
                "idade_segundos": None,
                "api_fixture_id_prioridade": 2,
            },
            {
                "jogo": {"url": "seguimento-7min"},
                "em_foco": False,
                "idade_segundos": 420,
                "api_fixture_id_prioridade": 3,
            },
            {
                "jogo": {"url": "revisita-fora-da-janela"},
                "em_foco": False,
                "idade_segundos": 2500,
                "api_fixture_id_prioridade": 4,
            },
        ]
        fixtures = [
            {"fixture": {"id": indice, "status": {"elapsed": 60}}}
            for indice in range(1, 5)
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(
            [item["jogo"]["url"] for item in ordenadas[:3]],
            ["revisita-fora-da-janela", "nova", "seguimento-7min"],
        )
        self.assertEqual(diagnostico["atrasadas_acima_20_minutos"], 2)
        self.assertTrue(diagnostico["atrasada_reservada"])
        self.assertEqual(
            diagnostico["maior_atraso_reservado_segundos"], 2500.0
        )
        self.assertTrue(diagnostico["nova_reservada"])
        self.assertTrue(diagnostico["seguimento_temporal_reservado"])
        self.assertFalse(diagnostico["foco_ja_cobre_janela_temporal"])
        self.assertTrue(diagnostico["sem_solicitacoes_extras"])

    def test_priorizacao_resgata_mais_atrasada_sem_aumentar_coletas(self):
        tarefas = [
            {
                "jogo": {"url": "nova"},
                "em_foco": False,
                "idade_segundos": None,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "atrasada-25min"},
                "em_foco": False,
                "idade_segundos": 1500,
                "api_fixture_id_prioridade": 2,
            },
            {
                "jogo": {"url": "atrasada-70min"},
                "em_foco": False,
                "idade_segundos": 4200,
                "api_fixture_id_prioridade": 3,
            },
            {
                "jogo": {"url": "api-forte"},
                "em_foco": False,
                "idade_segundos": 500,
                "api_fixture_id_prioridade": 4,
            },
        ]
        fixtures = [
            {"fixture": {"id": 1, "status": {"elapsed": 10}}},
            {"fixture": {"id": 2, "status": {"elapsed": 40}}},
            {"fixture": {"id": 3, "status": {"elapsed": 50}}},
            {
                "fixture": {"id": 4, "status": {"elapsed": 60}},
                "statistics": [{"statistics": [
                    {"type": "Shots on Goal", "value": 10},
                ]}],
            },
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(len(ordenadas), len(tarefas))
        self.assertEqual(ordenadas[0]["jogo"]["url"], "atrasada-70min")
        self.assertEqual(diagnostico["atrasadas_acima_20_minutos"], 2)
        self.assertTrue(diagnostico["atrasada_reservada"])
        self.assertTrue(diagnostico["sem_solicitacoes_extras"])

    def test_atrasada_periodica_nao_e_reservada_duas_vezes(self):
        tarefas = [
            {
                "jogo": {"url": "atrasada-periodica"},
                "em_foco": False,
                "idade_segundos": 3600,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "foco"},
                "em_foco": True,
                "idade_segundos": 400,
                "api_fixture_id_prioridade": 2,
            },
            {
                "jogo": {"url": "exploracao"},
                "em_foco": False,
                "idade_segundos": 500,
                "api_fixture_id_prioridade": 3,
            },
        ]
        fixtures = [
            {"fixture": {"id": indice, "status": {"elapsed": 60}}}
            for indice in range(1, 4)
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        urls = [item["jogo"]["url"] for item in ordenadas]
        self.assertEqual(urls[0], "atrasada-periodica")
        self.assertEqual(len(urls), len(set(urls)))
        self.assertCountEqual(
            urls, ["atrasada-periodica", "foco", "exploracao"]
        )
        self.assertTrue(diagnostico["atrasada_reservada"])

    def test_foco_temporal_evitar_reserva_redundante(self):
        tarefas = [
            {
                "jogo": {"url": "foco-7min"},
                "em_foco": True,
                "idade_segundos": 420,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "seguimento"},
                "em_foco": False,
                "idade_segundos": 700,
                "api_fixture_id_prioridade": 2,
            },
        ]
        fixtures = [
            {"fixture": {"id": indice, "status": {"elapsed": 60}}}
            for indice in range(1, 3)
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "foco-7min")
        self.assertTrue(diagnostico["foco_ja_cobre_janela_temporal"])
        self.assertFalse(diagnostico["seguimento_temporal_reservado"])

    def test_reserva_janela_10_15_quando_foco_so_fecha_5(self):
        agora = datetime.now()
        self.servico.historico = Mock()
        self.servico.historico.partidas = {
            "foco-5": [{
                "instante": agora - timedelta(minutes=6),
                "periodo": "segundo_tempo",
            }],
            "seguimento-longo": [
                {
                    "instante": agora - timedelta(minutes=11),
                    "periodo": "segundo_tempo",
                },
                {
                    "instante": agora - timedelta(minutes=16),
                    "periodo": "segundo_tempo",
                },
            ],
        }
        tarefas = [
            {
                "jogo": {"url": "foco-5", "status": "60 '"},
                "em_foco": True,
                "idade_segundos": 360,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "nova", "status": "20 '"},
                "em_foco": False,
                "idade_segundos": None,
                "api_fixture_id_prioridade": 2,
            },
            {
                "jogo": {
                    "url": "seguimento-longo", "status": "60 '",
                },
                "em_foco": False,
                "idade_segundos": 660,
                "api_fixture_id_prioridade": 3,
            },
        ]
        fixtures = [
            {"fixture": {"id": indice, "status": {"elapsed": 60}}}
            for indice in range(1, 4)
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(
            [item["jogo"]["url"] for item in ordenadas[:3]],
            ["nova", "seguimento-longo", "foco-5"],
        )
        self.assertTrue(diagnostico["foco_ja_cobre_janela_temporal"])
        self.assertFalse(
            diagnostico["foco_ja_cobre_janela_temporal_longa"]
        )
        self.assertTrue(diagnostico["seguimento_temporal_reservado"])
        self.assertEqual(
            diagnostico["janelas_temporais_reservadas"], [10, 15]
        )

    def test_desempata_revisita_temporal_por_candidato_de_gols(self):
        agora = datetime.now()
        self.servico.historico = Mock()
        self.servico.historico.partidas = {
            "temporal-comum": [{
                "instante": agora - timedelta(minutes=6),
                "periodo": "segundo_tempo",
            }],
            "temporal-gols": [{
                "instante": agora - timedelta(minutes=6),
                "periodo": "segundo_tempo",
            }],
        }
        tarefas = [
            {
                "jogo": {"url": "temporal-comum", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 360,
                "ordem_agendador": 0,
            },
            {
                "jogo": {"url": "temporal-gols", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 360,
                "ordem_agendador": 1,
                "prioridade_exploracao_gols": True,
            },
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "temporal-gols")
        self.assertTrue(
            diagnostico["exploracao_gols_nas_quatro_primeiras"]
        )
        self.assertTrue(diagnostico["sem_solicitacoes_extras"])

    def test_carga_alta_prioriza_duas_revisitas_sem_perder_jogo_novo(self):
        agora = datetime.now()
        self.servico.historico = Mock()
        self.servico.historico.partidas = {
            "temporal-15": [{
                "instante": agora - timedelta(minutes=16),
                "periodo": "segundo_tempo",
            }],
            "temporal-10": [{
                "instante": agora - timedelta(minutes=11),
                "periodo": "segundo_tempo",
            }],
        }
        tarefas = [
            {
                "jogo": {"url": "atrasada", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 1500,
            },
            {
                "jogo": {"url": "nova", "status": "20 '"},
                "em_foco": False,
                "idade_segundos": None,
            },
            {
                "jogo": {"url": "temporal-15", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 960,
            },
            {
                "jogo": {"url": "temporal-10", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 660,
            },
            {
                "jogo": {"url": "foco", "status": "60 '"},
                "em_foco": True,
                "idade_segundos": 100,
            },
        ]
        tarefas.extend({
            "jogo": {"url": f"extra-{indice}", "status": "30 '"},
            "em_foco": False,
            "idade_segundos": None,
        } for indice in range(10))

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        urls = [item["jogo"]["url"] for item in ordenadas]
        self.assertEqual(
            urls[:4],
            ["foco", "nova", "atrasada", "temporal-15"],
        )
        self.assertIn("nova", urls)
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(
            diagnostico["seguimentos_temporais_reservados"], 2
        )
        self.assertTrue(diagnostico["carga_alta_temporal"])
        self.assertTrue(diagnostico["foco_prioritario_reservado"])
        self.assertTrue(diagnostico["atrasada_nas_tres_primeiras"])
        self.assertTrue(diagnostico["prioridade_gol_ht_garantida"])
        self.assertEqual(diagnostico["tipo_prioridade_gol_ht"], "base")
        self.assertTrue(
            diagnostico["prioridade_gol_ht_nas_quatro_primeiras"]
        )
        self.assertFalse(diagnostico["oportunidade_api_reservada"])
        self.assertEqual(
            diagnostico["janelas_temporais_reservadas"], [10, 15]
        )
        self.assertTrue(diagnostico["sem_solicitacoes_extras"])

    def test_carga_alta_reserva_oportunidade_api_e_jogo_novo(self):
        agora = datetime.now()
        self.servico.historico = Mock()
        self.servico.historico.partidas = {
            "temporal-15": [{
                "instante": agora - timedelta(minutes=16),
                "periodo": "segundo_tempo",
            }],
            "temporal-10": [{
                "instante": agora - timedelta(minutes=11),
                "periodo": "segundo_tempo",
            }],
        }
        tarefas = [
            {
                "jogo": {"url": "nova", "status": "20 '"},
                "em_foco": False,
                "idade_segundos": None,
            },
            {
                "jogo": {"url": "temporal-15", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 960,
            },
            {
                "jogo": {"url": "temporal-10", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 660,
            },
            {
                "jogo": {"url": "oportunidade", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 500,
                "coletar_odds": True,
                "api_fixture_id_prioridade": 99,
            },
        ]
        tarefas.extend({
            "jogo": {"url": f"extra-{indice}", "status": "30 '"},
            "em_foco": False,
            "idade_segundos": None,
        } for indice in range(11))
        fixtures = [{
            "fixture": {"id": 99, "status": {"elapsed": 60}},
            "statistics": [{"statistics": [
                {"type": "Shots on Goal", "value": 8},
                {"type": "Total Shots", "value": 18},
            ]}],
        }]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(
            [item["jogo"]["url"] for item in ordenadas[:4]],
            ["nova", "oportunidade", "temporal-15", "temporal-10"],
        )
        self.assertTrue(diagnostico["oportunidade_api_reservada"])
        self.assertTrue(diagnostico["prioridade_gol_ht_garantida"])
        self.assertEqual(diagnostico["tipo_prioridade_gol_ht"], "base")
        self.assertTrue(
            diagnostico["prioridade_gol_ht_nas_quatro_primeiras"]
        )

    def test_carga_alta_prioriza_janela_5_exigida_pelo_motor(self):
        agora = datetime.now()
        self.servico.historico = Mock()
        self.servico.historico.partidas = {
            "foco-15": [{
                "instante": agora - timedelta(minutes=16),
                "periodo": "segundo_tempo",
            }],
            "temporal-15": [{
                "instante": agora - timedelta(minutes=16),
                "periodo": "segundo_tempo",
            }],
            "temporal-5": [{
                "instante": agora - timedelta(minutes=6),
                "periodo": "segundo_tempo",
            }],
        }
        tarefas = [
            {
                "jogo": {"url": "foco-15", "status": "60 '"},
                "em_foco": True,
                "idade_segundos": 960,
            },
            {
                "jogo": {"url": "temporal-15", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 960,
            },
            {
                "jogo": {"url": "temporal-5", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 360,
            },
        ]
        tarefas.extend({
            "jogo": {"url": f"extra-cinco-{indice}", "status": "30 '"},
            "em_foco": False,
            "idade_segundos": None,
        } for indice in range(12))

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "foco-15")
        self.assertEqual(ordenadas[1]["jogo"]["url"], "temporal-5")
        self.assertFalse(diagnostico["foco_ja_cobre_janela_5"])
        self.assertTrue(diagnostico["janela_5_priorizada"])
        self.assertIn(5, diagnostico["janelas_temporais_reservadas"])

    def test_carga_alta_prioriza_seguimento_antes_do_limite_gol_ht(self):
        agora = datetime.now()
        self.servico.historico = Mock()
        self.servico.historico.partidas = {
            "temporal-ht": [{
                "instante": agora - timedelta(minutes=6),
                "periodo": "primeiro_tempo",
            }],
            "temporal-ft": [{
                "instante": agora - timedelta(minutes=6),
                "periodo": "segundo_tempo",
            }],
        }
        tarefas = [
            {
                "jogo": {"url": "temporal-ft", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 360,
            },
            {
                "jogo": {"url": "temporal-ht", "status": "25 '"},
                "em_foco": False,
                "idade_segundos": 360,
            },
        ]
        tarefas.extend({
            "jogo": {"url": f"extra-ht-{indice}", "status": "35 '"},
            "em_foco": False,
            "idade_segundos": None,
        } for indice in range(13))

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        urls = [item["jogo"]["url"] for item in ordenadas]
        self.assertLess(urls.index("temporal-ht"), urls.index("temporal-ft"))
        self.assertTrue(diagnostico["seguimento_gol_ht_reservado"])
        self.assertTrue(diagnostico["sem_solicitacoes_extras"])

    def test_foco_fora_da_janela_nao_ocupa_vaga_prioritaria(self):
        tarefas = [
            {
                "jogo": {"url": "foco-94", "status": "94 '"},
                "em_foco": True,
                "idade_segundos": 360,
            },
            {
                "jogo": {"url": "foco-70", "status": "70 '"},
                "em_foco": True,
                "idade_segundos": 360,
            },
        ]
        tarefas.extend({
            "jogo": {"url": f"extra-janela-{indice}", "status": "40 '"},
            "em_foco": False,
            "idade_segundos": None,
        } for indice in range(13))

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "foco-70")
        self.assertFalse(tarefas[0]["em_foco"])
        self.assertEqual(diagnostico["focos_fora_janela_operacional"], 1)
        self.assertEqual(
            diagnostico["minuto_maximo_prioridade_sinais"], 86
        )

    def test_intervalo_nao_ocupa_foco_ou_seguimento_temporal(self):
        agora = datetime.now()
        self.servico.historico = Mock()
        self.servico.historico.partidas = {
            "intervalo": [{
                "instante": agora - timedelta(minutes=6),
                "periodo": "primeiro_tempo",
            }],
            "ativo": [{
                "instante": agora - timedelta(minutes=6),
                "periodo": "segundo_tempo",
            }],
        }
        tarefas = [
            {
                "jogo": {"url": "intervalo", "status": "Intervalo"},
                "em_foco": True,
                "idade_segundos": 360,
            },
            {
                "jogo": {"url": "ativo", "status": "60 '"},
                "em_foco": True,
                "idade_segundos": 360,
            },
        ]
        tarefas.extend({
            "jogo": {"url": f"extra-intervalo-{indice}", "status": "40 '"},
            "em_foco": False,
            "idade_segundos": None,
        } for indice in range(13))

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "ativo")
        self.assertFalse(tarefas[0]["em_foco"])
        self.assertEqual(diagnostico["focos_fora_janela_operacional"], 1)
        self.assertEqual(
            diagnostico["tarefas_intervalo_fora_prioridade"], 1
        )

    def test_acionaveis_ficam_antes_de_intervalo_e_87_mais(self):
        tarefas = [
            {
                "jogo": {"url": "encerrada-90", "status": "90 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "acionavel-fraca", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 2,
            },
            {
                "jogo": {"url": "intervalo", "status": "Intervalo"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 3,
            },
            {
                "jogo": {"url": "acionavel-forte", "status": "70 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 4,
            },
        ]
        fixtures = [
            {
                "fixture": {"id": indice, "status": {"elapsed": 60}},
                "statistics": ([{"statistics": [
                    {"type": "Shots on Goal", "value": 8},
                ]}] if indice in {1, 3, 4} else []),
            }
            for indice in range(1, 5)
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(
            [item["jogo"]["url"] for item in ordenadas[:2]],
            ["acionavel-forte", "acionavel-fraca"],
        )
        self.assertEqual(diagnostico["tarefas_acionaveis"], 2)
        self.assertEqual(
            diagnostico["tarefas_fora_janelas_ativas"], 2
        )
        self.assertEqual(
            diagnostico["acionaveis_nas_quatro_primeiras"], 2
        )
        self.assertTrue(diagnostico["prioridade_acionaveis_aplicada"])

    def test_reserva_atrasada_prefere_acionavel_a_intervalo_mais_antigo(self):
        tarefas = [
            {
                "jogo": {"url": "intervalo-antigo", "status": "HT"},
                "em_foco": False,
                "idade_segundos": 7200,
            },
            {
                "jogo": {"url": "acionavel-atrasada", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 1500,
            },
            {
                "jogo": {"url": "acionavel-recente", "status": "65 '"},
                "em_foco": False,
                "idade_segundos": 100,
            },
        ]

        ordenadas, diagnostico = self.servico._priorizar_tarefas_por_api(
            tarefas, []
        )

        self.assertEqual(
            ordenadas[0]["jogo"]["url"], "acionavel-atrasada"
        )
        self.assertEqual(diagnostico["atrasadas_acima_20_minutos"], 2)
        self.assertEqual(diagnostico["atrasadas_acionaveis"], 1)
        self.assertEqual(
            diagnostico["maior_atraso_reservado_segundos"], 1500.0
        )
        self.assertTrue(diagnostico["atrasada_reservada_acionavel"])

    def test_odd_asiatica_generica_so_desempata_prioridade_api(self):
        class APIComOddsGenericas:
            def fixtures_com_odds_escanteios_asiaticos_ft(self):
                return {1}

        self.servico.api = APIComOddsGenericas()
        tarefas = [
            {
                "jogo": {"url": "odd-generica", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 1,
            },
            {
                "jogo": {"url": "pressao-forte", "status": "60 '"},
                "em_foco": False,
                "idade_segundos": 100,
                "api_fixture_id_prioridade": 2,
            },
        ]
        fixtures = [
            {"fixture": {"id": 1, "status": {"elapsed": 60}}},
            {
                "fixture": {"id": 2, "status": {"elapsed": 60}},
                "statistics": [{"statistics": [
                    {"type": "Shots on Goal", "value": 8},
                    {"type": "Total Shots", "value": 18},
                ]}],
            },
        ]

        ordenadas, _ = self.servico._priorizar_tarefas_por_api(
            tarefas, fixtures
        )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "pressao-forte")
        self.assertTrue(ordenadas[1]["odd_asiatica_api_disponivel"])
        self.assertFalse(
            ordenadas[1]["odd_asiatica_api_alvo_um_escanteio"]
        )

    def test_reconcilia_somente_calibracoes_desatualizadas(self):
        self.servico.calibrador = Mock()
        self.servico.calibrador.reconciliar_se_desatualizado.side_effect = (
            lambda mercado, _regra: (
                {"amostra": 100} if mercado == "gol_ft" else None
            )
        )

        reconciliadas = self.servico._recalibrar_desatualizadas()

        self.assertEqual(reconciliadas, ["gol_ft"])

    def test_seleciona_melhor_simulacao_e_registra_descartes_comparaveis(self):
        self.servico.alertas = Mock()
        self.servico.alertas.registrar_filtro_teste.return_value = (
            "pontuacao_teste_insuficiente"
        )
        pares = [
            (
                11,
                {
                    "_status_persistido": "aprovado",
                    "status": "aprovado",
                    "probabilidade_calibrada": None,
                    "mercado": "proximo_gol",
                    "regra_versao": versao_regra_operacional(
                        "proximo_gol"
                    ),
                    "odd": 1.66,
                    "features": {"minuto": 60},
                    "pontuacao_tecnica": 72.5,
                },
            ),
            (
                12,
                {
                    "_status_persistido": "aprovado",
                    "status": "aprovado",
                    "probabilidade_calibrada": None,
                    "mercado": "proximo_gol",
                    "regra_versao": versao_regra_operacional(
                        "proximo_gol"
                    ),
                    "odd": 1.66,
                    "features": {"minuto": 60},
                    "pontuacao_tecnica": 86.0,
                },
            ),
            (
                13,
                {
                    "_status_persistido": "rejeitado",
                    "status": "rejeitado",
                    "probabilidade_calibrada": None,
                    "pontuacao_tecnica": 95.0,
                },
            ),
        ]

        selecionada = self.servico._selecionar_simulacao_teste(pares)

        self.assertEqual(selecionada, pares[1])
        self.servico.alertas.registrar_filtro_teste.assert_called_once_with(
            11, pares[0][1]
        )
        self.servico.alertas.registrar_priorizacao_teste.assert_not_called()

    def test_registra_aprovado_superado_por_melhor_sinal_do_snapshot(self):
        self.servico.alertas = Mock()
        self.servico.alertas.registrar_filtro_teste.return_value = None
        menor = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "proximo_gol",
            "regra_versao": versao_regra_operacional("proximo_gol"),
            "odd": 1.66,
            "features": {"minuto": 60},
            "pontuacao_tecnica": 82.0,
        }
        maior = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "proximo_gol",
            "regra_versao": versao_regra_operacional("proximo_gol"),
            "odd": 1.66,
            "features": {"minuto": 60},
            "pontuacao_tecnica": 88.0,
        }

        selecionada = self.servico._selecionar_simulacao_teste([
            (14, menor), (15, maior),
        ])

        self.assertEqual(selecionada, (15, maior))
        self.servico.alertas.registrar_priorizacao_teste.assert_called_once_with(
            14
        )

    def test_top_ativo_vence_empate_com_metodo_pai_sem_duplicar_envio(self):
        self.servico.alertas = Mock()
        self.servico.alertas.registrar_filtro_teste.return_value = None
        pai = {
            "_status_persistido": "simulacao",
            "status": "simulacao",
            "probabilidade_calibrada": None,
            "mercado": "gol_ft",
            "pontuacao_tecnica": 82.0,
            "features": {
                "exploracao_sombra": {
                    "versao": VERSAO_GOL_FT_TENDENCIA,
                },
                "gol_ft_tendencia_mais_um": {
                    "linhagem_sha256": LINHAGEM_GOL_FT_TENDENCIA,
                },
            },
        }
        top = {
            **pai,
            "features": {
                "exploracao_sombra": {"versao": VERSAO_TOP_FT},
                "top_criterio_gols": {"linhagem_sha256": LINHAGEM_TOP},
            },
        }

        with (
            patch(
                "telegram_alertas.GOL_FT_TENDENCIA_MAIS_UM_GRUPO_ATIVO",
                True,
            ),
            patch(
                "telegram_alertas.TOP_CRITERIOS_GOLS_GRUPO_ATIVO",
                True,
            ),
        ):
            selecionada = self.servico._selecionar_simulacao_teste([
                (51, pai), (52, top),
            ])

        self.assertEqual((52, top), selecionada)
        self.servico.alertas.registrar_priorizacao_teste.assert_called_once_with(
            51
        )

    def test_reprovacao_oficial_nao_interrompe_simulacao_prospectiva(self):
        self.servico.alertas = Mock()
        candidato = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "proximo_gol",
            "regra_versao": versao_regra_operacional("proximo_gol"),
            "odd": 1.66,
            "features": {"minuto": 60},
            "motivo_sem_calibracao": "modelo_inativo_ou_ausente",
            "pontuacao_tecnica": 84.0,
        }

        selecionada = self.servico._selecionar_simulacao_teste([
            (21, candidato),
        ])

        self.assertEqual(selecionada, (21, candidato))
        self.servico.alertas.registrar_filtro_teste.assert_not_called()

    @patch(
        "telegram_alertas.ESCANTEIOS_FT_ASIATICO_MULTIPLOS_GRUPO_ATIVO",
        True,
    )
    def test_asiatico_ft_multiplos_so_e_selecionado_com_rollback_explicito(
        self,
    ):
        self.servico.alertas = Mock()
        sombra = {
            "_status_persistido": "simulacao",
            "status": "simulacao",
            "probabilidade_calibrada": None,
            "mercado": "escanteios_ft_asiatico",
            "pontuacao_tecnica": 90.0,
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

        selecionada = self.servico._selecionar_simulacao_teste([
            (22, sombra),
        ])

        self.assertEqual((22, sombra), selecionada)
        self.servico.alertas.registrar_filtro_teste.assert_not_called()

    def test_gol_e_escanteio_recebem_vagas_separadas_no_snapshot(self):
        self.servico.alertas = Mock()
        gol = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "proximo_gol",
            "regra_versao": versao_regra_operacional("proximo_gol"),
            "odd": 1.66,
            "features": {"minuto": 60},
            "pontuacao_tecnica": 92.0,
        }
        canto = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "escanteios_ft_asiatico",
            "regra_versao": versao_regra_operacional(
                "escanteios_ft_asiatico"
            ),
            "pontuacao_tecnica": 80.0,
            "features": {"tipo_mercado_odds": "asiatico"},
        }

        selecionadas = self.servico._selecionar_simulacoes_teste([
            (61, gol), (62, canto),
        ])

        self.assertEqual([(61, gol), (62, canto)], selecionadas)
        self.servico.alertas.registrar_priorizacao_teste.assert_not_called()

    def test_v2_controle_e_v3_nao_entram_no_grupo(self):
        self.servico.alertas = Mock()
        base = {
            "_status_persistido": "simulacao",
            "status": "simulacao",
            "probabilidade_calibrada": None,
            "mercado": "gol_ft",
            "regra_versao": REGRA_VERSAO_GOL_FT_V3,
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
            "pontuacao_tecnica": 80.0,
        }
        v3 = {
            **base,
            "pontuacao_tecnica": 99.0,
            "features": {"exploracao_sombra": {
                "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
            }},
        }
        v2 = {
            **base,
            "features": {"exploracao_sombra": {
                "versao": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
            }},
        }

        selecionada = self.servico._selecionar_simulacao_teste([
            (23, v3),
            (24, v2),
        ])

        self.assertIsNone(selecionada)
        self.servico.alertas.registrar_filtro_teste.assert_called_once_with(
            24, v2
        )

    def test_rota_declarada_mas_desligada_fica_auditavel(self):
        self.servico.alertas = Mock()
        candidato = {
            "_status_persistido": "simulacao",
            "status": "simulacao",
            "probabilidade_calibrada": None,
            "mercado": "gol_ht",
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "pontuacao_tecnica": 75.3,
            "features": {
                "exploracao_sombra": {
                    "versao": "gol-ht-capacidade-times-poisson-v1",
                    "grupo_teste": True,
                    "telegram_oficial": False,
                    "aplicacao_automatica": False,
                },
                "protecao_tendencias_packball": {
                    "ativa": True,
                    "aprovada": False,
                    "motivo": "tendencia_packball_indisponivel",
                },
            },
        }

        selecionada = self.servico._selecionar_simulacao_teste([
            (25, candidato),
        ])

        self.assertIsNone(selecionada)
        self.servico.alertas.registrar_filtro_teste.assert_called_once_with(
            25, candidato
        )

    def test_gol_ft_v6_reprovado_nao_ocupa_vaga_de_outro_mercado(self):
        self.servico.alertas = Mock()
        self.servico.alertas.registrar_filtro_teste.return_value = (
            "mercado_reprovado_validacao_gol_ft_v6"
        )
        gol_ft = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "gol_ft",
            "regra_versao": "sinais-v6",
            "pontuacao_tecnica": 96.0,
        }
        proximo_gol = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "proximo_gol",
            "regra_versao": versao_regra_operacional("proximo_gol"),
            "pontuacao_tecnica": 82.0,
            "odd": 1.66,
            "features": {"minuto": 75},
        }

        selecionada = self.servico._selecionar_simulacao_teste([
            (31, gol_ft),
            (32, proximo_gol),
        ])

        self.assertEqual(selecionada, (32, proximo_gol))
        self.servico.alertas.registrar_filtro_teste.assert_called_once_with(
            31, gol_ft
        )

    def test_ht_negativo_nao_ocupa_vaga_do_proximo_gol_positivo(self):
        self.servico.alertas = Mock()
        self.servico.alertas.registrar_filtro_teste.return_value = (
            "regra_fora_allowlist_simulacao_grupo"
        )
        gol_ht = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "gol_ht",
            "regra_versao": "sinais-v8b-gol-ht-max28",
            "pontuacao_tecnica": 99.0,
        }
        proximo_gol = {
            "_status_persistido": "aprovado",
            "status": "aprovado",
            "probabilidade_calibrada": None,
            "mercado": "proximo_gol",
            "regra_versao": versao_regra_operacional("proximo_gol"),
            "pontuacao_tecnica": 80.0,
            "odd": 1.66,
            "features": {"minuto": 60},
        }

        selecionada = self.servico._selecionar_simulacao_teste([
            (41, gol_ht),
            (42, proximo_gol),
        ])

        self.assertEqual(selecionada, (42, proximo_gol))
        self.servico.alertas.registrar_filtro_teste.assert_called_once_with(
            41, gol_ht
        )

    def test_supervisao_registra_reinicio_do_watchdog(self):
        self.servico.pasta = Path.cwd()
        self.servico.observabilidade = Mock()
        garantir = Mock(return_value={"estado": "reiniciado", "pid": 456})

        resultado = self.servico._supervisionar_watchdog(garantir)

        self.assertEqual(resultado["estado"], "reiniciado")
        self.servico.observabilidade.supervisao_watchdog.assert_called_once_with(
            reiniciado=True, pid=456
        )

    def _estados_gate_envio(self, persistido_em=None):
        iniciado_em = (datetime.now() - timedelta(seconds=10)).replace(
            microsecond=0
        ).isoformat()
        persistido_em = persistido_em or datetime.now().replace(
            microsecond=0
        ).isoformat()
        return {
            "watchdog_estado.json": {
                "saudavel": True,
                "validacao": {
                    "saudavel": True,
                    "fontes_sinais_operacionais": {"saudavel": True},
                },
                "persistencia_estado_watchdog": {
                    "saudavel": True,
                    "estado": "persistido",
                    "persistido_em": persistido_em,
                },
            },
            "monitor_processo.json": {
                "pid": 101,
                "atualizado_em": iniciado_em,
                "codigo_hash": "monitor",
            },
            "watchdog_processo.json": {
                "pid": 102,
                "atualizado_em": iniciado_em,
                "codigo_hash": "watchdog",
            },
        }

    def test_gate_envio_usa_espelho_rapido_e_saude_atual_das_fontes(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        estados = self._estados_gate_envio()
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
        ):
            resultado = (
                self.servico._validar_operacao_para_alerta_oficial()
            )

        self.assertEqual(
            resultado,
            {"apto": True, "estado": "saudavel"},
        )

    def test_gate_envio_oficial_exige_edge_da_versao_exata(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        estados = self._estados_gate_envio()
        candidato = {
            "mercado": "proximo_gol",
            "linha": "casa",
            "odd": 1.80,
            "regra_versao": "proximo-gol-v7",
            "probabilidade_calibrada": 0.81,
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
            "features": {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "cotacao_entrada_clv_estado": "congelada_v1",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v2",
                    "mercado": "proximo_gol",
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "coletado_em": "2026-09-12T20:00:00+00:00",
                    "idade_segundos": 5.0,
                    "cache": False,
                    "tipo": "tres_vias",
                    "selecao": "casa",
                    "odds": {
                        "casa": 1.80,
                        "visitante": 2.80,
                        "sem_gol": 9.0,
                    },
                    "odd_selecionada": 1.80,
                    "origem_mercado": {
                        "schema": "origem-mercado-odd-v1",
                        "fonte": "betsapi",
                        "bookmaker": "bet365",
                        "identificador": "1778",
                        "nome": "Next Goal",
                        "linha": 2.0,
                        "lados": ["casa", "sem_gol", "visitante"],
                    },
                },
            },
        }
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
            patch(
                "servico_monitor.avaliar_candidato_oficial",
                return_value={
                    "apto": False,
                    "estado": "edge_nao_comprovado",
                    "motivo": "vantagem_nao_replicada_holdout",
                    "mercado": "proximo_gol",
                    "regra_versao": "proximo-gol-v7",
                },
            ) as avaliar_edge,
        ):
            resultado = self.servico._validar_operacao_para_alerta_oficial(
                candidato=candidato
            )

        avaliar_edge.assert_called_once_with(
            self.servico.banco.conexao, candidato
        )
        self.assertEqual(resultado["estado"], "bloqueado")
        self.assertEqual(
            resultado["motivo"], "edge_portfolio_nao_comprovado"
        )
        self.assertEqual(resultado["fonte"], "portfolio_edge")

    def test_gate_oficial_bloqueia_cotacao_sem_casa_executavel(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        estados = self._estados_gate_envio()
        candidato = {
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": 1.80,
            "regra_versao": "gol-ft-v1",
            "probabilidade_calibrada": 0.81,
            "fonte_odds": "api_football",
            "bookmaker_odds": None,
            "features": {
                "fonte_odds": "api_football",
                "bookmaker_odds": None,
                "cotacao_entrada_clv_estado": "congelada_v1",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v1",
                    "mercado": "gol_ft",
                    "fonte": "api_football",
                    "bookmaker": None,
                    "coletado_em": "2026-09-12T20:00:00+00:00",
                    "idade_segundos": 5.0,
                    "cache": False,
                    "tipo": "binaria",
                    "linha": 2.5,
                    "over": 1.80,
                    "under": 2.05,
                    "odd_selecionada": 1.80,
                },
            },
        }
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
            patch(
                "servico_monitor.avaliar_candidato_oficial"
            ) as avaliar_edge,
        ):
            resultado = self.servico._validar_operacao_para_alerta_oficial(
                candidato=candidato
            )

        self.assertFalse(resultado["apto"])
        self.assertEqual(resultado["estado"], "bloqueado")
        self.assertEqual(
            resultado["motivo"], "cotacao_oficial_nao_executavel"
        )
        self.assertEqual(resultado["fonte"], "custodia_cotacao")
        self.assertEqual(
            resultado["detalhe"]["motivo"],
            "schema_cotacao_sem_origem_exata",
        )
        avaliar_edge.assert_not_called()

    def test_gate_simulacao_nao_exige_edge_antes_de_formar_amostra(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        estados = self._estados_gate_envio()
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": "proximo-gol-v7",
            "probabilidade_calibrada": None,
        }
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
            patch(
                "servico_monitor.avaliar_candidato_oficial"
            ) as avaliar_edge,
        ):
            resultado = self.servico._validar_operacao_para_alerta_oficial(
                candidato=candidato
            )

        self.assertEqual(resultado, {"apto": True, "estado": "saudavel"})
        avaliar_edge.assert_not_called()

    def test_pendencia_de_calibracao_nao_bloqueia_operacao_saudavel(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        estados = self._estados_gate_envio()
        estados["watchdog_estado.json"]["validacao"].update({
            "saudavel": False,
            "requer_atencao": True,
            "motivos": ["pendencias_acima_180_minutos"],
        })
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
        ):
            resultado = self.servico._validar_operacao_para_alerta_oficial()

        self.assertEqual(resultado, {"apto": True, "estado": "saudavel"})

    def test_gate_identifica_codigo_aguardando_reinicio_sem_culpar_api(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.controle_packball = Mock()
        estados = self._estados_gate_envio()
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="reinicio_pendente",
            ),
        ):
            resultado = self.servico._validar_operacao_para_alerta_oficial()

        self.assertEqual(resultado, {
            "apto": False,
            "estado": "degradado",
            "motivo": "codigo_runtime_desatualizado",
            "fonte": "runtime",
        })
        self.servico.api.saude_operacional.assert_not_called()

    def test_primeiro_espelho_fresco_nao_exige_ciclo_anterior_ao_reinicio(
        self,
    ):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        estados = self._estados_gate_envio()
        estados["watchdog_estado.json"].update({
            "saudavel": False,
            "motivo": "coleta_parada",
        })
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
        ):
            resultado = self.servico._validar_operacao_para_alerta_oficial()

        self.assertEqual(resultado, {"apto": True, "estado": "saudavel"})

    def test_supervisao_inicial_permite_primeira_consulta_que_confirma_api(
        self,
    ):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": False,
            "motivo": "api_ainda_nao_confirmada",
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        estados = self._estados_gate_envio()
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
        ):
            inicial = self.servico._validar_operacao_para_alerta_oficial(
                exigir_api_confirmada=False
            )
            envio = self.servico._validar_operacao_para_alerta_oficial()

        self.assertEqual(inicial, {"apto": True, "estado": "saudavel"})
        self.assertEqual(envio, {
            "apto": False,
            "estado": "degradado",
            "motivo": "api_nao_confirmada",
            "fonte": "api_football",
            "detalhe": "api_ainda_nao_confirmada",
        })

    def test_falha_historica_nao_sacrifica_novo_ciclo_local_saudavel(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        estados = self._estados_gate_envio()
        estados["watchdog_estado.json"]["validacao"][
            "fontes_sinais_operacionais"
        ] = {
            "saudavel": False,
            "estado": "degradado",
            "ciclos_degradados_consecutivos": 2,
        }
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
        ):
            resultado = self.servico._validar_operacao_para_alerta_oficial()

        self.assertEqual(resultado, {"apto": True, "estado": "saudavel"})

    def test_gate_envio_falha_fechado_com_espelho_desatualizado(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.controle_packball = Mock()
        antigo = (datetime.now() - timedelta(seconds=121)).isoformat()
        estados = self._estados_gate_envio(persistido_em=antigo)
        inicio_antigo = (
            datetime.now() - timedelta(seconds=300)
        ).isoformat()
        estados["monitor_processo.json"]["atualizado_em"] = inicio_antigo
        estados["watchdog_processo.json"]["atualizado_em"] = inicio_antigo
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
        ):
            resultado = (
                self.servico._validar_operacao_para_alerta_oficial()
            )

        self.assertEqual(resultado, {
            "apto": False,
            "estado": "degradado",
            "motivo": "espelho_watchdog_fora_do_prazo",
            "fonte": "watchdog",
        })
        self.servico.api.saude_operacional.assert_not_called()

    def test_gate_usa_duracao_real_watchdog_com_teto_limitado(self):
        self.servico.pasta = Path.cwd()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True
        }
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False
        }
        persistido = (
            datetime.now() - timedelta(seconds=150)
        ).isoformat()
        estados = self._estados_gate_envio(persistido_em=persistido)
        estados["watchdog_estado.json"]["observabilidade_watchdog"] = {
            "duracao_total_segundos": 97.0,
        }
        inicio = (datetime.now() - timedelta(seconds=400)).isoformat()
        estados["monitor_processo.json"]["atualizado_em"] = inicio
        estados["watchdog_processo.json"]["atualizado_em"] = inicio
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
        ):
            resultado = self.servico._validar_operacao_para_alerta_oficial()

        self.assertEqual(resultado, {"apto": True, "estado": "saudavel"})

        estados["watchdog_estado.json"]["persistencia_estado_watchdog"][
            "persistido_em"
        ] = (datetime.now() - timedelta(seconds=301)).isoformat()
        with (
            patch(
                "processo_monitor.ler_estado",
                side_effect=lambda caminho: estados[Path(caminho).name],
            ),
            patch("processo_monitor.pid_ativo", return_value=True),
            patch("processo_monitor.trava_em_uso", return_value=True),
            patch(
                "processo_monitor.estado_codigo_runtime",
                return_value="atualizado",
            ),
        ):
            expirado = self.servico._validar_operacao_para_alerta_oficial()

        self.assertEqual(
            expirado.get("motivo"), "espelho_watchdog_fora_do_prazo"
        )

    def test_gate_envio_bloqueia_api_ou_packball_indisponivel(self):
        self.servico.pasta = Path.cwd()
        estados = self._estados_gate_envio()
        cenarios = (
            ({"saudavel": False}, {"ativo": False}, "api"),
            ({"saudavel": True}, {"ativo": True}, "packball"),
        )
        for saude_api, estado_packball, nome in cenarios:
            with self.subTest(fonte=nome):
                self.servico.api = Mock()
                self.servico.api.saude_operacional.return_value = saude_api
                self.servico.controle_packball = Mock()
                self.servico.controle_packball.estado_atual.return_value = (
                    estado_packball
                )
                with (
                    patch(
                        "processo_monitor.ler_estado",
                        side_effect=lambda caminho: estados[
                            Path(caminho).name
                        ],
                    ),
                    patch(
                        "processo_monitor.pid_ativo", return_value=True
                    ),
                    patch(
                        "processo_monitor.trava_em_uso", return_value=True
                    ),
                    patch(
                        "processo_monitor.estado_codigo_runtime",
                        return_value="atualizado",
                    ),
                ):
                    resultado = (
                        self.servico
                        ._validar_operacao_para_alerta_oficial()
                    )

                self.assertEqual(resultado["apto"], False)
                self.assertEqual(resultado["estado"], "degradado")
                self.assertEqual(
                    resultado["fonte"],
                    "api_football" if nome == "api" else "packball",
                )
                self.assertEqual(
                    resultado["motivo"],
                    (
                        "api_nao_confirmada"
                        if nome == "api"
                        else "packball_em_pausa_preventiva"
                    ),
                )

    def test_bloqueio_de_fonte_permanece_ate_o_proximo_ciclo(self):
        atualizar = self.servico._atualizar_bloqueio_operacao_ciclo

        bloqueado = atualizar(gate={"apto": False, "estado": "degradado"})
        recuperou_no_mesmo_ciclo = atualizar(
            bloqueado,
            gate={"apto": True, "estado": "saudavel"},
        )
        pausa_packball = atualizar(
            False,
            gate={"apto": True},
            finalizacao_packball={
                "erros": 0,
                "pausa_preventiva": "circuit breaker",
            },
        )

        self.assertTrue(bloqueado)
        self.assertTrue(recuperou_no_mesmo_ciclo)
        self.assertTrue(pausa_packball)

    def test_falha_da_supervisao_nao_derruba_monitor(self):
        self.servico.pasta = Path.cwd()
        self.servico.observabilidade = Mock()
        garantir = Mock(side_effect=RuntimeError("falha temporaria"))

        resultado = self.servico._supervisionar_watchdog(garantir)

        self.assertEqual(resultado["estado"], "erro")
        self.servico.observabilidade.supervisao_watchdog.assert_called_once()

    def test_reinicio_runtime_isolado_e_solicitado_no_limite_do_ciclo(self):
        self.servico.pasta = Path.cwd()
        estados = {
            "monitor_processo.json": {"codigo_hash": "monitor-antigo"},
            "watchdog_processo.json": {"codigo_hash": "watchdog-atual"},
        }

        def ler(caminho):
            return estados[Path(caminho).name]

        def avaliar(_pasta, estado, arquivos=None):
            if arquivos is None:
                return (
                    "reinicio_pendente"
                    if estado["codigo_hash"] == "monitor-antigo"
                    else "atualizado"
                )
            return "atualizado"

        with (
            patch("processo_monitor.ler_estado", side_effect=ler),
            patch(
                "processo_monitor.estado_codigo_runtime",
                side_effect=avaliar,
            ),
        ):
            resultado = self.servico._avaliar_reinicio_runtime_monitor()

        self.assertTrue(resultado["solicitado"])
        self.assertEqual(
            resultado["motivo"],
            "codigo_runtime_monitor_desatualizado",
        )

    def test_reinicio_runtime_isolado_nao_ocorre_com_watchdog_antigo(self):
        self.servico.pasta = Path.cwd()
        with (
            patch(
                "processo_monitor.ler_estado",
                return_value={"codigo_hash": "antigo"},
            ),
            patch(
                "processo_monitor.estado_codigo_runtime",
                side_effect=["reinicio_pendente", "reinicio_pendente"],
            ),
        ):
            resultado = self.servico._avaliar_reinicio_runtime_monitor()

        self.assertFalse(resultado["solicitado"])
        self.assertEqual(
            resultado["estado_watchdog"], "reinicio_pendente"
        )

    def test_monitor_nao_inicia_navegador_em_modo_manutencao(self):
        pasta = Path.cwd() / ".teste_servico_modo_manutencao"
        pasta.mkdir(exist_ok=True)
        try:
            solicitar_modo_manutencao(pasta, "teste")
            self.servico.pasta = pasta
            self.servico.preparar = Mock()

            self.servico.executar()

            self.servico.preparar.assert_not_called()
        finally:
            for arquivo in pasta.iterdir():
                arquivo.unlink()
            pasta.rmdir()

    def test_consulta_lista_api_quando_ha_jogo_para_associar(self):
        self.servico.api = Mock()
        self.servico.api.jogos_ao_vivo.return_value = [{"fixture": {"id": 1}}]

        resultado = self.servico._fixtures_api_para([{"url": self.url}])

        self.assertEqual(resultado, [{"fixture": {"id": 1}}])
        self.servico.api.jogos_ao_vivo.assert_called_once_with()

    def test_restaura_agendamento_do_sqlite_convertendo_instantes_em_idades(self):
        self.servico.banco = Mock()
        self.servico.banco.carregar_instantes_agendamento.return_value = {
            self.url: {
                "ultima_coleta": "2026-07-21T11:59:30",
                "ultima_odds": "2026-07-21T11:55:00",
            }
        }
        self.servico.agendador = Mock()
        self.servico.agendador.restaurar.return_value = {
            "coletas_restauradas": 1,
            "odds_restauradas": 1,
        }

        resultado = self.servico._restaurar_agendamento_persistido(
            [{"url": self.url}], datetime(2026, 7, 21, 12, 0, 0)
        )

        self.assertEqual(resultado["coletas_restauradas"], 1)
        self.servico.agendador.restaurar.assert_called_once_with({
            self.url: {"idade_coleta": 30.0, "idade_odds": 300.0}
        })

    def test_falha_de_estatisticas_nao_interrompe_a_fonte(self):
        class PackBallComFalha:
            @staticmethod
            def coletar_estatisticas(pagina, jogo):
                raise TimeoutError("estatísticas demoraram")

        self.servico.packball = PackBallComFalha()
        self.servico.observabilidade = None
        jogo = {
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
        }

        with patch("builtins.print"):
            estatisticas, jogo_atualizado, falha = (
                self.servico._coletar_estatisticas_seguras(None, jogo)
            )

        self.assertEqual(estatisticas, {})
        self.assertEqual(jogo_atualizado, jogo)
        self.assertEqual(falha["fonte"], "estatisticas_packball")
        self.assertEqual(falha["fallback"], "estatisticas_vazias")

    def test_navegador_fechado_nao_persiste_estatisticas_vazias(self):
        class TargetClosedError(RuntimeError):
            pass

        self.servico.packball = Mock()
        self.servico.packball.coletar_estatisticas.side_effect = (
            TargetClosedError(
                "Page.goto: Target page, context or browser has been closed"
            )
        )

        with self.assertRaises(TargetClosedError):
            self.servico._coletar_estatisticas_seguras(
                None, {"url": self.url}
            )

    def test_bloqueio_nao_persiste_estatisticas_vazias(self):
        self.servico.packball = Mock()
        self.servico.packball.coletar_estatisticas.side_effect = (
            PackBallBloqueadoError("circuit breaker")
        )
        with self.assertRaises(PackBallBloqueadoError):
            self.servico._coletar_estatisticas_seguras(
                None, {"url": self.url}
            )

    def test_detecta_target_closed_encadeado_para_recuperacao_imediata(self):
        class TargetClosedError(RuntimeError):
            pass

        causa = TargetClosedError(
            "Page.goto: Target page, context or browser has been closed"
        )
        erro = RuntimeError("lista PackBall nÃ£o validada")
        erro.__cause__ = causa

        self.assertTrue(self.servico._erro_navegador_fatal(erro))
        self.assertFalse(
            self.servico._erro_navegador_fatal(TimeoutError("demorou"))
        )

    def test_falha_de_odds_preserva_ultima_leitura_sem_movimento(self):
        self.servico.observabilidade = None
        jogo = {
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
        }
        anteriores = {
            "pre_jogo": [{"mercado": "Total gols", "dados": "1.80"}],
            "ao_vivo": [],
        }

        with patch(
            "servico_monitor.coletar_odds",
            side_effect=TimeoutError("odds demoraram"),
        ), patch("builtins.print"):
            odds, falha = self.servico._coletar_odds_seguras(
                None, jogo, anteriores, True
            )

        self.assertEqual(odds["pre_jogo"], anteriores["pre_jogo"])
        self.assertEqual(odds["movimentacao"], [])
        self.assertEqual(falha["fonte"], "odds_packball")
        self.assertEqual(falha["fallback"], "ultimas_odds_persistidas")

    def test_bloqueio_nao_usa_odds_antigas_como_nova_coleta(self):
        self.servico.controle_packball = Mock()
        with patch(
            "servico_monitor.coletar_odds",
            side_effect=PackBallBloqueadoError("circuit breaker"),
        ), self.assertRaises(PackBallBloqueadoError):
            self.servico._coletar_odds_seguras(
                None,
                {"url": self.url},
                {"pre_jogo": [], "ao_vivo": []},
                True,
            )

    def test_abre_uma_unica_aba_para_lista_e_detalhes(self):
        pagina = object()
        contexto = Mock()
        contexto.new_page.return_value = pagina
        navegador = Mock()
        navegador.new_context.return_value = contexto
        playwright = Mock()
        playwright.chromium.launch.return_value = navegador
        self.servico.arquivo_sessao = Path("sessao.json")

        _, _, lista, detalhe = self.servico._abrir_navegador(
            playwright, True
        )

        contexto.new_page.assert_called_once_with()
        self.assertIs(lista, detalhe)

    def test_driver_playwright_repete_permission_error_transitorio(self):
        primeiro = MagicMock()
        primeiro.start.side_effect = PermissionError(
            "pipe temporariamente bloqueado"
        )
        segundo = MagicMock()
        playwright = Mock()
        segundo.start.return_value = playwright
        self.servico.observabilidade = Mock()

        with (
            patch(
                "servico_monitor.sync_playwright",
                side_effect=[primeiro, segundo],
            ) as fabrica,
            patch("servico_monitor.time.sleep") as dormir,
            self.servico._iniciar_playwright_seguro() as resultado,
        ):
            self.assertIs(resultado, playwright)

        self.assertEqual(fabrica.call_count, 2)
        dormir.assert_called_once_with(2.0)
        primeiro.__exit__.assert_called_once_with(None, None, None)
        playwright.stop.assert_called_once_with()
        self.servico.observabilidade.recuperacao.assert_called_once()

    def test_driver_playwright_falha_fechado_apos_limite(self):
        gerenciadores = [MagicMock(), MagicMock(), MagicMock()]
        for gerenciador in gerenciadores:
            gerenciador.start.side_effect = PermissionError(
                "pipe bloqueado"
            )

        with (
            patch(
                "servico_monitor.sync_playwright",
                side_effect=gerenciadores,
            ) as fabrica,
            patch("servico_monitor.time.sleep") as dormir,
            self.assertRaises(PermissionError),
        ):
            with self.servico._iniciar_playwright_seguro(tentativas=3):
                pass

        self.assertEqual(fabrica.call_count, 3)
        for gerenciador in gerenciadores:
            gerenciador.__exit__.assert_called_once_with(None, None, None)
        self.assertEqual(
            [item.args[0] for item in dormir.call_args_list],
            [2.0, 4.0],
        )

    def test_driver_playwright_default_sustenta_bloqueio_longo(self):
        gerenciadores = [MagicMock() for _ in range(8)]
        for gerenciador in gerenciadores[:7]:
            gerenciador.start.side_effect = PermissionError("pipe bloqueado")
        playwright = Mock()
        gerenciadores[7].start.return_value = playwright
        self.servico.observabilidade = Mock()

        with (
            patch(
                "servico_monitor.sync_playwright",
                side_effect=gerenciadores,
            ),
            patch("servico_monitor.time.sleep") as dormir,
            self.servico._iniciar_playwright_seguro() as resultado,
        ):
            self.assertIs(resultado, playwright)

        self.assertEqual(
            [item.args[0] for item in dormir.call_args_list],
            [2.0, 4.0, 8.0, 15.0, 15.0, 15.0, 15.0],
        )
        self.assertEqual(
            self.servico.observabilidade.ciclo_progresso.call_count, 7
        )
        playwright.stop.assert_called_once_with()

    def test_abertura_repete_permission_error_transitorio(self):
        pagina = object()
        contexto = Mock()
        contexto.new_page.return_value = pagina
        navegador = Mock()
        navegador.new_context.return_value = contexto
        playwright = Mock()
        playwright.chromium.launch.side_effect = [
            PermissionError("recurso ainda ocupado"),
            navegador,
        ]
        self.servico.arquivo_sessao = Path("sessao.json")

        with patch("servico_monitor.time.sleep") as dormir:
            _, _, lista, detalhe = self.servico._abrir_navegador(
                playwright, True
            )

        self.assertEqual(playwright.chromium.launch.call_count, 2)
        dormir.assert_called_once_with(2.0)
        self.assertIs(lista, detalhe)

    def test_abertura_fecha_navegador_parcial_antes_de_repetir(self):
        navegador_parcial = Mock()
        navegador_parcial.new_context.side_effect = PermissionError(
            "perfil ainda ocupado"
        )
        playwright = Mock()
        playwright.chromium.launch.return_value = navegador_parcial
        self.servico.arquivo_sessao = Path("sessao.json")

        with (
            patch("servico_monitor.time.sleep"),
            self.assertRaises(PermissionError),
        ):
            self.servico._abrir_navegador(
                playwright, True, tentativas=2
            )

        self.assertEqual(playwright.chromium.launch.call_count, 2)
        self.assertEqual(navegador_parcial.close.call_count, 2)

    def test_odds_novas_recebem_instante_e_nao_sao_cache(self):
        self.servico.observabilidade = None
        jogo = {
            "url": self.url,
            "mandante": "A",
            "visitante": "B",
        }
        coletadas = {
            "pre_jogo": [],
            "ao_vivo": [{"mercado": "Total gols", "dados": "1.80"}],
        }

        with patch("servico_monitor.coletar_odds", return_value=coletadas):
            odds, falha = self.servico._coletar_odds_seguras(
                None,
                jogo,
                {"pre_jogo": [], "ao_vivo": []},
                True,
            )

        self.assertIsNone(falha)
        self.assertFalse(odds["_metadados"]["cache"])
        self.assertEqual(odds["_metadados"]["idade_segundos"], 0.0)
        self.assertFalse(odds["ao_vivo"][0]["cache"])
        self.assertEqual(odds["ao_vivo"][0]["fonte"], "packball")
        self.assertEqual(odds["ao_vivo"][0]["idade_segundos"], 0.0)
        self.assertTrue(odds["ao_vivo"][0]["coletado_em"])

    def test_api_complementa_asiatico_1t_somente_se_packball_nao_tem(self):
        self.servico.api = Mock()
        self.servico.api.odds_escanteios_asiaticos_1t.return_value = {
            "mercado": "Asian Corners (1st Half)",
            "categoria": "escanteios",
            "tipo_mercado": "asiatico",
            "fonte": "api_football",
            "cache": False,
            "idade_segundos": 0.0,
            "ofertas_periodos": {
                "1T": {
                    "formato": "duas_opcoes",
                    "ofertas": [{"linha": 4.5, "over": 1.8, "under": 2.0}],
                }
            },
        }
        odds = {"pre_jogo": [], "ao_vivo": []}

        adicionou = self.servico._complementar_odds_escanteios_1t_api(
            odds,
            {"status": "25 '"},
            {"fixture_id": 123},
            True,
        )
        repetiu = self.servico._complementar_odds_escanteios_1t_api(
            odds,
            {"status": "26 '"},
            {"fixture_id": 123},
            True,
        )

        self.assertTrue(adicionou)
        self.assertFalse(repetiu)
        self.assertEqual(len(odds["ao_vivo"]), 1)
        self.servico.api.odds_escanteios_asiaticos_1t.assert_called_once_with(
            123
        )

    def test_api_complementa_asiatico_ft_somente_se_packball_nao_tem(self):
        self.servico.api = Mock()
        self.servico.api.odds_escanteios_asiaticos_ft.return_value = {
            "mercado": "Asian Corners",
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "fonte": "api_football",
            "cache": False,
            "idade_segundos": 0.0,
            "ofertas": [{"linha": 8.5, "over": 1.8, "under": 2.0}],
        }
        odds = {"pre_jogo": [], "ao_vivo": []}

        adicionou = self.servico._complementar_odds_escanteios_ft_api(
            odds, {"status": "55 '"}, {"fixture_id": 123}, True
        )
        repetiu = self.servico._complementar_odds_escanteios_ft_api(
            odds, {"status": "56 '"}, {"fixture_id": 123}, True
        )

        self.assertTrue(adicionou)
        self.assertFalse(repetiu)
        self.assertEqual(len(odds["ao_vivo"]), 1)
        self.servico.api.odds_escanteios_asiaticos_ft.assert_called_once_with(
            123
        )

    def test_api_asiatico_ft_independe_da_navegacao_odds_packball(self):
        self.servico.api = Mock()
        self.servico.api.odds_escanteios_asiaticos_ft.return_value = {
            "mercado": "Asian Corners",
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "ofertas": [{"linha": 8.5, "over": 1.8, "under": 2.0}],
        }
        odds = {"pre_jogo": [], "ao_vivo": []}

        adicionou = self.servico._complementar_odds_escanteios_ft_api(
            odds,
            {"status": "55 '"},
            {"fixture_id": 123},
            False,
        )

        self.assertTrue(adicionou)
        self.assertEqual(len(odds["ao_vivo"]), 1)
        self.servico.api.odds_escanteios_asiaticos_ft.assert_called_once_with(
            123
        )

    def test_api_nao_substitui_asiatico_ft_existente_do_packball(self):
        self.servico.api = Mock()
        odds = {
            "pre_jogo": [],
            "ao_vivo": [{
                "mercado": "Escanteios - 2 Opções",
                "categoria": "escanteios",
                "escopo": "total",
                "tipo_mercado": "asiatico",
                "formato": "duas_opcoes",
                "fonte": "packball",
                "coletado_em": datetime.now().replace(
                    microsecond=0
                ).isoformat(),
                "cache": False,
                "ofertas": [{"linha": 8.5, "over": 1.9, "under": 1.9}],
            }],
        }

        resultado = self.servico._complementar_odds_escanteios_ft_api(
            odds, {"status": "55 '"}, {"fixture_id": 123}, True
        )

        self.assertFalse(resultado)
        self.servico.api.odds_escanteios_asiaticos_ft.assert_not_called()

    def test_exactly_ft_nao_impede_fallback_asiatico_da_api(self):
        self.servico.api = Mock()
        self.servico.api.odds_escanteios_asiaticos_ft.return_value = {
            "mercado": "Asian Corners",
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "ofertas": [{"linha": 8.5, "over": 1.8, "under": 2.0}],
        }
        odds = {
            "pre_jogo": [],
            "ao_vivo": [{
                "mercado": "Escanteios Exactly",
                "categoria": "escanteios",
                "escopo": "exactly",
                "formato": "tres_opcoes_exactly",
                "ofertas": [],
                "ofertas_exatamente": [{
                    "linha": 8.0, "exatamente": 4.0,
                    "over": 2.0, "under": 1.8,
                }],
            }],
        }

        resultado = self.servico._complementar_odds_escanteios_ft_api(
            odds, {"status": "55 '"}, {"fixture_id": 123}, True
        )

        self.assertTrue(resultado)
        self.assertEqual(len(odds["ao_vivo"]), 2)

    def test_api_nao_consulta_asiatico_1t_fora_da_janela(self):
        self.servico.api = Mock()
        odds = {"pre_jogo": [], "ao_vivo": []}

        resultado = self.servico._complementar_odds_escanteios_1t_api(
            odds,
            {"status": "55 '"},
            {"fixture_id": 123},
            True,
        )

        self.assertFalse(resultado)
        self.servico.api.odds_escanteios_asiaticos_1t.assert_not_called()

    def test_api_complementa_gols_ft_somente_se_packball_nao_tem(self):
        self.servico.api = Mock()
        self.servico.api.odds_gols_total_ft.return_value = {
            "mercado": "Total Gols",
            "categoria": "gols",
            "escopo": "total",
            "formato": "duas_opcoes",
            "fonte": "api_football",
            "cache": False,
            "idade_segundos": 0.0,
            "ofertas": [{"linha": 2.5, "over": 1.8, "under": 2.0}],
        }
        odds = {"pre_jogo": [], "ao_vivo": []}

        adicionou = self.servico._complementar_odds_gols_ft_api(
            odds, {"status": "55 '"}, {"fixture_id": 123}
        )
        repetiu = self.servico._complementar_odds_gols_ft_api(
            odds, {"status": "56 '"}, {"fixture_id": 123}
        )

        self.assertTrue(adicionou)
        self.assertFalse(repetiu)
        self.servico.api.odds_gols_total_ft.assert_called_once_with(123)

    def test_api_nao_substitui_total_gols_existente_do_packball(self):
        self.servico.api = Mock()
        odds = {
            "pre_jogo": [],
            "ao_vivo": [{
                "mercado": "Total Gols",
                "categoria": "gols",
                "escopo": "total",
                "formato": "duas_opcoes",
                "fonte": "packball",
                "coletado_em": datetime.now().replace(
                    microsecond=0
                ).isoformat(),
                "cache": False,
                "ofertas": [{"linha": 2.5, "over": 1.9, "under": 1.9}],
            }],
        }

        adicionou = self.servico._complementar_odds_gols_ft_api(
            odds, {"status": "55 '"}, {"fixture_id": 123}
        )

        self.assertFalse(adicionou)
        self.servico.api.odds_gols_total_ft.assert_not_called()

    def test_api_complementa_proximo_gol_conforme_placar(self):
        self.servico.api = Mock()
        self.servico.api.odds_proximo_gol.return_value = {
            "mercado": "Marcar O Próximo Gol",
            "categoria": "gols",
            "escopo": "proximo",
            "formato": "tres_opcoes",
            "fonte": "api_football",
            "cache": False,
            "idade_segundos": 0.0,
            "selecoes": {
                "casa": 1.9,
                "visitante": 2.4,
                "sem_gol": 4.2,
            },
        }
        odds = {"pre_jogo": [], "ao_vivo": []}

        adicionou = self.servico._complementar_odds_proximo_gol_api(
            odds,
            {"status": "55 '", "placar": "1-0"},
            {"fixture_id": 123},
        )
        repetiu = self.servico._complementar_odds_proximo_gol_api(
            odds,
            {"status": "56 '", "placar": "1-0"},
            {"fixture_id": 123},
        )

        self.assertTrue(adicionou)
        self.assertFalse(repetiu)
        self.servico.api.odds_proximo_gol.assert_called_once_with(123, 1)

    def test_backup_e_criado_ao_mudar_o_dia_apenas_uma_vez(self):
        agora = datetime(2026, 7, 21, 0, 1)
        self.servico._data_backup_verificada = agora.date().replace(day=20)
        self.servico.backup = Mock()
        self.servico.backup.criar_diario.return_value = (
            Path("backup_20260721.db"),
            True,
        )
        self.servico.observabilidade = Mock()

        with patch("builtins.print"):
            primeiro = self.servico._manter_backup_diario(agora)
            segundo = self.servico._manter_backup_diario(agora)

        self.assertTrue(primeiro["criado"])
        self.assertEqual(segundo["motivo"], "dia_ja_verificado")
        self.servico.backup.criar_diario.assert_called_once_with(
            self.banco.conexao, agora
        )

    def test_backup_com_falha_e_tentado_novamente(self):
        agora = datetime(2026, 7, 21, 0, 1)
        self.servico._data_backup_verificada = None
        self.servico.backup = Mock()
        self.servico.backup.criar_diario.side_effect = OSError("disco")
        self.servico.observabilidade = Mock()

        with patch("builtins.print"):
            primeiro = self.servico._manter_backup_diario(agora)
            segundo = self.servico._manter_backup_diario(agora)

        self.assertEqual(primeiro["motivo"], "backup_falhou")
        self.assertEqual(segundo["motivo"], "backup_falhou")
        self.assertEqual(self.servico.backup.criar_diario.call_count, 2)

    def test_backup_periodico_e_criado_uma_vez_por_janela(self):
        agora = datetime(2026, 7, 21, 6, 1)
        self.servico._janela_backup_periodico_verificada = None
        self.servico.backup = Mock()
        self.servico.backup.criar_periodico.return_value = (
            Path("periodico_20260721_06.db"),
            True,
        )
        self.servico.backup.compactar_legado_mais_antigo.return_value = {
            "saudavel": True,
            "estado": "nenhum_backup_legado",
            "executado": False,
        }
        self.servico.observabilidade = Mock()

        with patch("builtins.print"):
            primeiro = self.servico._manter_backup_periodico(agora)
            segundo = self.servico._manter_backup_periodico(
                datetime(2026, 7, 21, 11, 59)
            )

        self.assertTrue(primeiro["criado"])
        self.assertEqual(segundo["motivo"], "janela_ja_verificada")
        self.servico.backup.criar_periodico.assert_called_once_with(
            self.banco.conexao, agora
        )
        self.servico.backup.compactar_legado_mais_antigo.assert_called_once_with(
            agora
        )
        self.servico.observabilidade.compactacao_backup_legado.assert_called_once()

    def test_manutencao_diaria_so_ocorre_depois_do_backup(self):
        agora = datetime(2026, 7, 21, 0, 2)
        self.servico._data_backup_verificada = agora.date()
        self.servico._data_manutencao_verificada = None
        self.servico.observabilidade = Mock()
        self.servico.banco.limpar_dados_antigos = Mock(
            return_value={"snapshots": 0, "sinais_descartados": 0}
        )
        self.servico.banco.checkpoint_wal = Mock(
            return_value={"ocupado": 0, "paginas": 1, "checkpoint": 1}
        )

        primeiro = self.servico._manter_manutencao_diaria(agora)
        segundo = self.servico._manter_manutencao_diaria(agora)

        self.assertTrue(primeiro["verificado"])
        self.assertEqual(segundo["motivo"], "dia_ja_verificado")
        self.servico.banco.limpar_dados_antigos.assert_called_once_with(
            dias=180
        )
        self.servico.banco.checkpoint_wal.assert_called_once()

    def test_manutencao_diaria_aceita_checkpoint_real_do_sqlite(self):
        agora = datetime(2026, 7, 21, 0, 2)
        log = Path.cwd() / ".teste_servico_monitor_eventos.jsonl"
        self.servico._data_backup_verificada = agora.date()
        self.servico._data_manutencao_verificada = None
        self.servico.observabilidade = Observabilidade(log)

        resultado = self.servico._manter_manutencao_diaria(agora)

        self.assertTrue(resultado["verificado"])
        self.assertEqual(
            set(resultado["checkpoint"]),
            {"ocupado", "paginas", "checkpoint"},
        )
        registro = __import__("json").loads(
            log.read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertEqual(registro["evento"], "manutencao_diaria_concluida")
        self.assertEqual(
            set(registro["checkpoint"]),
            {"ocupado", "paginas", "checkpoint"},
        )

    def test_manutencao_nao_roda_sem_backup_do_dia(self):
        agora = datetime(2026, 7, 21, 0, 2)
        self.servico._data_backup_verificada = agora.date().replace(day=20)
        self.servico._data_manutencao_verificada = None
        self.servico.banco.limpar_dados_antigos = Mock()

        resultado = self.servico._manter_manutencao_diaria(agora)

        self.assertEqual(resultado["motivo"], "aguardando_backup")
        self.servico.banco.limpar_dados_antigos.assert_not_called()

    def test_orcamento_adia_restante_sem_marcar_como_concluido(self):
        self.servico.agendador = Mock()
        self.servico.observabilidade = Mock()
        self.servico.processar_jogo = Mock(
            side_effect=[
                {
                    "fixture_id": None,
                    "odds_coletadas": True,
                    "duracao_segundos": 12.0,
                    "duracoes_etapas": {
                        "etapas": {
                            "estatisticas_packball_e_fusao": 5.0,
                            "api_contexto_e_motor_base": 7.0,
                        },
                    },
                    "janelas_temporais": ["5", "10"],
                    "sinais_bloqueados_fontes": 2,
                    "motivos_bloqueio_fontes": ["falha_api_no_ciclo"],
                    "gols_antecipados": {
                        "por_braco": {
                            "gol_ft_antecipado_pre_live": {
                                "estado": "bloqueado",
                                "motivo": "candidato_base_ausente",
                                "alertas": ["sem_confirmacao_api"],
                                "campos_ausentes": ["Índice de pressão"],
                            },
                        },
                    },
                    "gols_capacidade_contextual_v2": {
                        "por_mercado": {
                            "gol_ft": {
                                "estado": "bloqueado",
                                "motivo": "historico_contextual_insuficiente",
                            },
                            "gol_ht": {
                                "estado": "bloqueado",
                                "motivo": "apos_minuto_maximo_mercado",
                            },
                        },
                    },
                    "resgate_qualidade_api": {
                        "estado": "resgatado",
                        "campos_complementados": ["Chutes no gol"],
                    },
                    "thestatsapi_odds": {
                        "evidencia_disponivel": True,
                        "gate_apto": False,
                        "aplicacao_sinais": False,
                        "gate_motivo": "minuto_live_stats_incompativel",
                    },
                    "the_odds_api": {
                        "amostragem_referencia_sombra": {
                            "ativa": True,
                            "elegivel_betsapi": True,
                            "mercados_elegiveis_betsapi": [
                                "gol_ft", "gol_ht",
                                "escanteios_ft_asiatico",
                            ],
                            "solicitados": [
                                "gol_ft", "gol_ht",
                                "escanteios_ft_asiatico",
                            ],
                            "anexados": ["gol_ft", "gol_ht"],
                            "consultados": [
                                "alternate_totals",
                                "alternate_totals_h1",
                                "alternate_totals_corners",
                            ],
                            "consulta_combinada": True,
                            "custo_estimado_creditos": 3,
                            "mercados_persistidos_sombra": 2,
                            "reserva": {
                                "autorizada": True,
                                "tipo_amostra": "nova_partida",
                            },
                            "motivo": "oferta_anexada",
                        },
                    },
                },
                {
                    "fixture_id": None,
                    "odds_coletadas": True,
                    "duracao_segundos": 18.0,
                    "duracoes_etapas": {
                        "etapas": {
                            "estatisticas_packball_e_fusao": 7.0,
                            "api_contexto_e_motor_base": 11.0,
                        },
                    },
                    "janelas_temporais": ["5", "10", "15"],
                    "sinais_bloqueados_fontes": 1,
                    "motivos_bloqueio_fontes": [
                        "estatisticas_packball"
                    ],
                    "gols_antecipados": {
                        "por_braco": {
                            "gol_ft_antecipado_pre_live": {
                                "estado": "gerado",
                            },
                        },
                    },
                    "gols_capacidade_contextual_v2": {
                        "por_mercado": {
                            "gol_ft": {
                                "estado": "gerado",
                                "motivo": "candidato_gerado",
                            },
                            "gol_ht": {
                                "estado": "bloqueado",
                                "motivo": "apos_minuto_maximo_mercado",
                            },
                        },
                    },
                    "resgate_qualidade_api": {
                        "estado": "avaliado",
                        "campos_complementados": [],
                    },
                    "thestatsapi_odds": {
                        "evidencia_disponivel": True,
                        "gate_apto": True,
                        "aplicacao_sinais": True,
                        "gate_motivo": "apto_sombra",
                        "mercados_convertidos": 2,
                        "ofertas_anexadas": 7,
                        "mercados_anexados": 1,
                    },
                },
            ]
        )
        tarefas = [
            {
                "jogo": {"url": f"jogo-{indice}"},
                "coletar_odds": True,
                "em_foco": indice == 0,
                "idade_segundos": None if indice == 0 else 500,
            }
            for indice in range(3)
        ]
        tarefas[0]["taxa_liga_gols"] = {
            "liga": "Liga Sazonal",
            "temporada": "2026",
        }
        tarefas[2]["idade_segundos"] = 1800
        instantes = iter((0, 100, 181, 181))

        resultado = self.servico._processar_tarefas_detalhadas(
            None,
            tarefas,
            [],
            orcamento_segundos=180,
            relogio=lambda: next(instantes),
        )

        self.assertEqual(resultado["processadas"], 2)
        self.assertEqual(resultado["adiadas"], 1)
        self.assertEqual(resultado["associacoes_api"], {"nao_registrado": 2})
        self.assertEqual(resultado["tarefas_com_odds"], 2)
        self.assertEqual(resultado["tarefas_sem_odds"], 0)
        self.assertEqual(resultado["tarefas_odds_solicitadas"], 2)
        self.assertEqual(resultado["coletas_odds_sucesso"], 2)
        resumo_referencia = resultado[
            "the_odds_api"
        ]["amostragem_referencia"]
        self.assertEqual(3, resumo_referencia[
            "creditos_estimados_reservados"
        ])
        self.assertEqual(1, resumo_referencia["consultas_combinadas"])
        self.assertEqual(3, resumo_referencia[
            "maximo_mercados_por_consulta"
        ])
        self.assertEqual(
            {"elegiveis": 1, "consultados": 1, "anexados": 1},
            resumo_referencia["por_mercado"]["gol_ht"],
        )
        self.assertEqual(
            {"elegiveis": 1, "consultados": 1, "anexados": 0},
            resumo_referencia["por_mercado"][
                "escanteios_ft_asiatico"
            ],
        )
        self.assertEqual(resultado["fallback_odds_necessario"], 0)
        self.assertEqual(resultado["fallback_odds_atendeu"], 0)
        self.assertEqual(resultado["fallback_odds_sem_cobertura"], 0)
        self.assertEqual(len(resultado["comparacoes_fontes_odds"]), 2)
        self.assertEqual(
            resultado["comparacoes_fontes_odds"][0]["partida"],
            "jogo-0",
        )
        self.assertTrue(
            resultado["comparacoes_fontes_odds"][0]["thestatsapi"]
            ["evidencia_disponivel"]
        )
        self.assertEqual(
            resultado["thestatsapi_odds"],
            {
                "evidencias_disponiveis": 2,
                "gates_aptos": 1,
                "aplicacoes_sinais": 1,
                "mercados_convertidos": 2,
                "ofertas_anexadas": 7,
                "mercados_anexados": 1,
                "motivos_gate": {
                    "minuto_live_stats_incompativel": 1,
                    "apto_sombra": 1,
                },
            },
        )
        self.assertEqual(resultado["prioridades_asiaticas_processadas"], 0)
        self.assertEqual(resultado["odds_asiaticas_api_anexadas"], 0)
        self.assertEqual(resultado["prioridades_asiaticas_sem_anexo"], 0)
        self.assertEqual(resultado["sinais_bloqueados_fontes"], 3)
        self.assertEqual(
            resultado["motivos_bloqueio_fontes"],
            {"falha_api_no_ciclo": 1, "estatisticas_packball": 1},
        )
        self.assertEqual(
            resultado["gols_antecipados"],
            {
                "avaliacoes": 2,
                "gerados": 1,
                "por_braco": {
                    "gol_ft_antecipado_pre_live": {
                        "avaliacoes": 2,
                        "gerados": 1,
                        "motivos": {"candidato_base_ausente": 1},
                        "detalhes": {
                            "alertas": {"sem_confirmacao_api": 1},
                            "campos_ausentes": {"Índice de pressão": 1},
                        },
                    },
                },
            },
        )
        self.assertEqual(
            resultado["gols_capacidade_contextual_v2"],
            {
                "avaliacoes": 4,
                "gerados": 1,
                "por_mercado": {
                    "gol_ft": {
                        "avaliacoes": 2,
                        "gerados": 1,
                        "motivos": {
                            "historico_contextual_insuficiente": 1,
                        },
                    },
                    "gol_ht": {
                        "avaliacoes": 2,
                        "gerados": 0,
                        "motivos": {"apos_minuto_maximo_mercado": 2},
                    },
                },
            },
        )
        self.assertEqual(
            resultado["resgate_qualidade_api"],
            {
                "avaliacoes": 2,
                "resgatadas": 1,
                "estados": {"resgatado": 1, "avaliado": 1},
                "campos_complementados": {"Chutes no gol": 1},
            },
        )
        self.assertEqual(
            resultado["perfil_agendamento"],
            {
                "foco_agendadas": 1,
                "exploracao_agendadas": 2,
                "foco_processadas": 1,
                "exploracao_processadas": 1,
                "revisitas_processadas": 1,
                "novas_processadas": 1,
                "rechecagens_pos_evento_agendadas": 0,
                "rechecagens_pos_evento_processadas": 0,
                "acompanhamentos_preco_agendados": 0,
                "acompanhamentos_preco_processados": 0,
                "acompanhamentos_preco_com_odds": 0,
                "acompanhamentos_preco_sem_odds": 0,
                "acompanhamentos_preco_snapshots": 0,
                "acompanhamentos_preco_por_mercado": {},
            },
        )
        self.assertFalse(
            resultado["ritmo_packball"][
                "distribuicao_janela_ativa"
            ]
        )
        self.assertEqual(
            resultado["idade_fila"],
            {
                "agendadas": {
                    "tarefas": 3,
                    "com_historico": 2,
                    "sem_historico": 1,
                    "maxima_segundos": 1800.0,
                    "acima_20_minutos": 1,
                },
                "processadas": {
                    "tarefas": 2,
                    "com_historico": 1,
                    "sem_historico": 1,
                    "maxima_segundos": 500.0,
                    "acima_20_minutos": 0,
                },
                "adiadas": {
                    "tarefas": 1,
                    "com_historico": 1,
                    "sem_historico": 0,
                    "maxima_segundos": 1800.0,
                    "acima_20_minutos": 1,
                },
            },
        )
        self.assertEqual(
            resultado["auditoria_fila_packball"]["estado"],
            "persistido",
        )
        self.assertEqual(
            resultado["auditoria_fila_packball"]["inseridos"], 3
        )
        auditoria = self.banco.conexao.execute(
            """
            SELECT packball_url, posicao, processada, motivo, liga
            FROM auditoria_fila_packball
            ORDER BY posicao
            """
        ).fetchall()
        self.assertEqual(
            [
                ("jogo-0", 1, 1, "processada", "Liga Sazonal"),
                ("jogo-1", 2, 1, "processada", None),
                ("jogo-2", 3, 0, "orcamento_ciclo", None),
            ],
            [tuple(linha) for linha in auditoria],
        )
        self.assertEqual(resultado["duracao_tarefa_media_segundos"], 15.0)
        self.assertEqual(resultado["duracao_tarefa_p95_segundos"], 18.0)
        self.assertEqual(
            resultado["duracoes_etapas_detalhadas"],
            {
                "versao": "duracoes-etapas-detalhe-v1",
                "altera_sinal": False,
                "etapas": {
                    "api_contexto_e_motor_base": {
                        "amostras": 2,
                        "total_segundos": 18.0,
                        "media_segundos": 9.0,
                        "p95_segundos": 11.0,
                    },
                    "estatisticas_packball_e_fusao": {
                        "amostras": 2,
                        "total_segundos": 12.0,
                        "media_segundos": 6.0,
                        "p95_segundos": 7.0,
                    },
                },
            },
        )
        self.assertEqual(
            resultado["cobertura_temporal"],
            {
                "partidas_com_historico": 2,
                "taxa_com_historico": 1.0,
                "janelas_disponiveis": {"5": 2, "10": 2, "15": 1},
                "taxas_por_janela": {"5": 1.0, "10": 1.0, "15": 0.5},
                "por_perfil": {
                    "foco": {
                        "processadas": 1,
                        "com_historico": 1,
                        "taxa_com_historico": 1.0,
                    },
                    "exploracao": {
                        "processadas": 1,
                        "com_historico": 1,
                        "taxa_com_historico": 1.0,
                    },
                },
            },
        )
        self.assertEqual(self.servico.processar_jogo.call_count, 2)
        self.assertEqual(self.servico.agendador.concluir.call_count, 2)
        self.assertEqual(
            self.servico.observabilidade.ciclo_progresso.call_count, 2
        )

    def test_manutencao_interrompe_antes_da_proxima_partida(self):
        self.servico.agendador = Mock()
        self.servico.observabilidade = Mock()
        self.servico._modo_manutencao_ativo = Mock(
            side_effect=[False, True]
        )
        self.servico.processar_jogo = Mock(return_value={
            "fixture_id": None,
            "odds_coletadas": True,
            "duracao_segundos": 20.0,
            "janelas_temporais": ["5"],
        })
        tarefas = [
            {
                "jogo": {"url": f"jogo-{indice}"},
                "coletar_odds": True,
                "em_foco": False,
                "idade_segundos": 300,
            }
            for indice in range(2)
        ]

        with self.assertRaises(ManutencaoSolicitadaError):
            self.servico._processar_tarefas_detalhadas(
                None, tarefas, [], orcamento_segundos=180
            )

        self.servico.processar_jogo.assert_called_once()
        self.servico.agendador.concluir.assert_called_once()

    def test_lote_vazio_preserva_diagnostico_cota_betsapi(self):
        self.servico.betsapi = Mock()
        self.servico.betsapi.ativa = True
        self.servico.betsapi.aplicacao_sinais = True
        self.servico.betsapi.diagnostico.return_value = {
            "ativa": True,
            "aplicacao_sinais": True,
            "uso_hora": 12,
            "limite_hora": 3000,
            "uso_dia": 34,
            "limite_diario": 50000,
            "circuito_aberto": False,
            "circuito": {
                "persistente": True,
                "persistencia_saudavel": True,
            },
            "rollback": "BETSAPI_ATIVA=0",
        }

        resultado = self.servico._processar_tarefas_detalhadas(
            None, [], [], relogio=lambda: 0
        )

        self.assertEqual(resultado["processadas"], 0)
        self.assertEqual(resultado["betsapi"]["uso_hora"], 12)
        self.assertEqual(resultado["betsapi"]["limite_hora"], 3000)
        self.assertEqual(resultado["betsapi"]["uso_dia"], 34)
        self.assertEqual(resultado["betsapi"]["limite_diario"], 50000)
        self.assertFalse(resultado["betsapi"]["circuito_aberto"])
        self.assertTrue(
            resultado["betsapi"]["circuito"]["persistencia_saudavel"]
        )

    def test_lote_vazio_preserva_controle_estado_the_odds_api(self):
        self.servico.the_odds_api = Mock()
        self.servico.the_odds_api.ativa = True
        self.servico.the_odds_api.amostragem_referencia_ativa = True
        self.servico.the_odds_api.diagnostico.return_value = {
            "ativa": True,
            "controle_estado": {
                "saudavel": True,
                "origem": "backup",
                "recuperado": True,
                "backup": True,
                "fail_closed": False,
            },
            "circuito": {
                "falhas_consecutivas": 2,
                "bloqueado_ate": 12345,
            },
            "amostragem_referencia": {
                "ativa": True,
                "uso_dia": 3,
                "limite_diario": 30,
                "maximo_por_jogo_dia": 2,
                "jogos_distintos_dia": 2,
                "maior_uso_jogo_dia": 2,
            },
        }

        resultado = self.servico._processar_tarefas_detalhadas(
            None, [], [], relogio=lambda: 0
        )

        self.assertEqual(resultado["processadas"], 0)
        self.assertEqual(
            resultado["the_odds_api"]["controle_estado"]["origem"],
            "backup",
        )
        self.assertEqual(
            resultado["the_odds_api"]["circuito"]["falhas_consecutivas"],
            2,
        )
        self.assertEqual(
            resultado["the_odds_api"]["amostragem_referencia"][
                "reservadas"
            ],
            0,
        )
        self.assertEqual(
            resultado["the_odds_api"]["amostragem_referencia"][
                "jogos_distintos_dia"
            ],
            2,
        )
        self.assertEqual(
            resultado["the_odds_api"]["amostragem_referencia"][
                "confirmacoes_maximo_ciclo"
            ],
            1,
        )

    def test_espera_entre_ciclos_reage_sem_aguardar_intervalo_inteiro(self):
        self.servico._modo_manutencao_ativo = Mock(
            side_effect=[False, True]
        )
        dormir = Mock()

        interrompeu = self.servico._aguardar_intervalo_interrompivel(
            90,
            intervalo_segundos=1,
            relogio=Mock(side_effect=[0, 0]),
            dormir=dormir,
        )

        self.assertTrue(interrompeu)
        dormir.assert_called_once_with(1.0)

    def test_espera_reage_quando_pausa_packball_e_liberada(self):
        self.servico._modo_manutencao_ativo = Mock(return_value=False)
        mudou = Mock(side_effect=[False, True])
        dormir = Mock()

        interrompeu = self.servico._aguardar_intervalo_interrompivel(
            90,
            intervalo_segundos=1,
            relogio=Mock(side_effect=[0, 0, 1]),
            dormir=dormir,
            interromper_fn=mudou,
        )

        self.assertTrue(interrompeu)
        self.assertEqual(mudou.call_count, 2)
        dormir.assert_called_once_with(1.0)

    def test_supervisao_inicial_aguarda_espelho_e_libera_quando_saudavel(
        self,
    ):
        self.servico._modo_manutencao_ativo = Mock(return_value=False)
        self.servico._validar_operacao_para_alerta_oficial = Mock(
            side_effect=[
                {"apto": False, "estado": "inicializando"},
                {"apto": True, "estado": "saudavel"},
            ]
        )
        dormir = Mock()

        resultado = self.servico._aguardar_supervisao_inicial(
            timeout_segundos=10,
            intervalo_segundos=1,
            relogio=Mock(side_effect=[0, 0, 1]),
            dormir=dormir,
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "pronta")
        self.assertEqual(resultado["tentativas"], 2)
        self.assertEqual(resultado["duracao_segundos"], 1)
        dormir.assert_called_once_with(1.0)

    def test_supervisao_inicial_expira_sem_relaxar_gate_degradado(self):
        self.servico._modo_manutencao_ativo = Mock(return_value=False)
        self.servico._validar_operacao_para_alerta_oficial = Mock(
            return_value={"apto": False, "estado": "degradado"}
        )
        dormir = Mock()

        resultado = self.servico._aguardar_supervisao_inicial(
            timeout_segundos=2,
            intervalo_segundos=1,
            relogio=Mock(side_effect=[0, 0, 1, 2]),
            dormir=dormir,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "timeout")
        self.assertEqual(resultado["gate"]["estado"], "degradado")
        self.assertEqual(resultado["tentativas"], 3)
        self.assertEqual(dormir.call_count, 2)

    def test_supervisao_inicial_respeita_manutencao_sem_consultar_gate(self):
        self.servico._modo_manutencao_ativo = Mock(return_value=True)
        self.servico._validar_operacao_para_alerta_oficial = Mock()

        resultado = self.servico._aguardar_supervisao_inicial(
            timeout_segundos=120,
            relogio=Mock(side_effect=[0, 0]),
            dormir=Mock(),
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "manutencao")
        self.servico._validar_operacao_para_alerta_oficial.assert_not_called()

    def test_reserva_adaptativa_nao_inicia_tarefa_que_estouraria_orcamento(
        self,
    ):
        self.servico.agendador = Mock()
        self.servico.observabilidade = Mock()
        self.servico._duracoes_tarefas_recentes = []
        self.servico.processar_jogo = Mock(
            side_effect=[
                {
                    "fixture_id": None,
                    "odds_coletadas": False,
                    "duracao_segundos": 50.0,
                    "janelas_temporais": ["5"],
                },
                {
                    "fixture_id": None,
                    "odds_coletadas": False,
                    "duracao_segundos": 50.0,
                    "janelas_temporais": ["5"],
                },
            ]
        )
        tarefas = [{
            "jogo": {"url": f"jogo-{indice}"},
            "coletar_odds": False,
            "em_foco": False,
            "idade_segundos": 500,
        } for indice in range(3)]
        instantes = iter((0, 80, 150, 150))

        resultado = self.servico._processar_tarefas_detalhadas(
            None,
            tarefas,
            [],
            orcamento_segundos=180,
            relogio=lambda: next(instantes),
        )

        self.assertEqual(resultado["processadas"], 2)
        self.assertEqual(resultado["adiadas"], 1)
        self.assertTrue(resultado["interrompido_por_reserva"])
        self.assertEqual(resultado["reserva_admissao_segundos"], 53.0)
        self.assertEqual(
            resultado["duracoes_tarefas_segundos"],
            [50.0, 50.0],
        )
        self.assertEqual(resultado["duracoes_historicas_admissao"], 2)
        self.assertEqual(resultado["duracao_detalhada_segundos"], 150)
        self.assertEqual(self.servico.processar_jogo.call_count, 2)
        self.assertEqual(self.servico.agendador.concluir.call_count, 2)

    def test_detalhamento_adaptativo_libera_quinto_sem_mudar_teto(self):
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False,
            "distribuicao_janela_ativa": True,
            "maximo_navegacoes_efetivo_janela": 28,
            "janela_navegacoes_segundos": 600,
        }
        tarefas = [
            {"acionavel_fila_detalhada": True} for _ in range(8)
        ]
        with patch.dict(
            os.environ,
            {
                "PACKBALL_DETALHAMENTO_ADAPTATIVO": "1",
                "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA": "0",
            },
        ):
            resultado = self.servico._configurar_detalhamento_packball(
                tarefas
            )

        self.assertTrue(resultado["ativado_no_ciclo"])
        self.assertEqual(resultado["orcamento_efetivo_segundos"], 225.0)
        self.assertEqual(resultado["maximo_detalhes"], 5)
        self.assertEqual(resultado["maximo_navegacoes_janela"], 28)

    def test_triagem_capacidade_libera_sete_com_rollback_unico(self):
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False,
            "distribuicao_janela_ativa": True,
            "maximo_navegacoes_efetivo_janela": 32,
            "janela_navegacoes_segundos": 600,
        }
        tarefas = [
            {"acionavel_fila_detalhada": True} for _ in range(10)
        ]
        with patch.dict(os.environ, {
            "PACKBALL_DETALHAMENTO_ADAPTATIVO": "1",
            "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA": "1",
            "PACKBALL_CAPACIDADE_DINAMICA_ATIVA": "0",
            "PACKBALL_TRIAGEM_MAX_DETALHES": "7",
            "PACKBALL_TRIAGEM_ORCAMENTO_SEGUNDOS": "270",
        }):
            resultado = self.servico._configurar_detalhamento_packball(
                tarefas
            )

        self.assertTrue(resultado["ativado_no_ciclo"])
        self.assertTrue(resultado["teste_capacidade"])
        self.assertEqual(resultado["orcamento_efetivo_segundos"], 270.0)
        self.assertEqual(resultado["maximo_detalhes"], 7)
        self.assertEqual(
            resultado["rollback_teste"],
            "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA=0",
        )

    def test_triagem_capacidade_configuravel_libera_dez_com_teto_seguro(self):
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False,
            "distribuicao_janela_ativa": True,
            "maximo_navegacoes_efetivo_janela": 32,
            "janela_navegacoes_segundos": 600,
        }
        tarefas = [
            {"acionavel_fila_detalhada": True} for _ in range(12)
        ]
        with patch.dict(os.environ, {
            "PACKBALL_DETALHAMENTO_ADAPTATIVO": "1",
            "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA": "1",
            "PACKBALL_CAPACIDADE_DINAMICA_ATIVA": "0",
            "PACKBALL_TRIAGEM_MAX_DETALHES": "10",
            "PACKBALL_TRIAGEM_ORCAMENTO_SEGUNDOS": "360",
        }):
            resultado = self.servico._configurar_detalhamento_packball(
                tarefas
            )

        self.assertTrue(resultado["ativado_no_ciclo"])
        self.assertEqual(resultado["orcamento_efetivo_segundos"], 360.0)
        self.assertEqual(resultado["maximo_detalhes"], 10)
        self.assertIn(
            "PACKBALL_TRIAGEM_MAX_DETALHES=7",
            resultado["rollback_lote"],
        )

    def test_capacidade_dinamica_escolhe_sete_para_alvo_de_cinco_minutos(self):
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False,
            "distribuicao_janela_ativa": True,
            "maximo_navegacoes_efetivo_janela": 32,
            "janela_navegacoes_segundos": 600,
        }
        self.servico._duracoes_tarefas_recentes = [32.0] * 12
        self.servico._inicio_ciclo_monotonic = 100.0
        tarefas = [
            {"acionavel_fila_detalhada": True} for _ in range(12)
        ]
        with patch.dict(os.environ, {
            "PACKBALL_DETALHAMENTO_ADAPTATIVO": "1",
            "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA": "1",
            "PACKBALL_CAPACIDADE_DINAMICA_ATIVA": "1",
            "PACKBALL_TRIAGEM_MAX_DETALHES": "10",
            "PACKBALL_TRIAGEM_MIN_DETALHES": "5",
            "PACKBALL_TRIAGEM_ORCAMENTO_SEGUNDOS": "360",
            "PACKBALL_CICLO_ALVO_SEGUNDOS": "300",
            "PACKBALL_CICLO_RESERVA_FINAL_SEGUNDOS": "10",
            "THESTATSAPI_CUSTO_ESTIMADO_JOGO_SEGUNDOS": "3.5",
            "THESTATSAPI_RESERVA_AUDITORIA_FORA_LOTE": "2",
        }), patch("servico_monitor.time.monotonic", return_value=130.0):
            resultado = self.servico._configurar_detalhamento_packball(
                tarefas
            )

        self.assertTrue(resultado["capacidade_dinamica_ativa"])
        self.assertEqual(resultado["escolha_dinamica"], 7)
        self.assertEqual(resultado["maximo_detalhes"], 7)
        self.assertEqual(resultado["alvo_ciclo_segundos"], 300.0)

    def test_capacidade_dinamica_libera_dez_quando_historico_e_rapido(self):
        self.servico.controle_packball = Mock()
        self.servico.controle_packball.estado_atual.return_value = {
            "ativo": False,
            "distribuicao_janela_ativa": True,
        }
        self.servico._duracoes_tarefas_recentes = [20.0] * 12
        self.servico._inicio_ciclo_monotonic = 100.0
        tarefas = [
            {"acionavel_fila_detalhada": True} for _ in range(12)
        ]
        with patch.dict(os.environ, {
            "PACKBALL_DETALHAMENTO_ADAPTATIVO": "1",
            "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA": "1",
            "PACKBALL_CAPACIDADE_DINAMICA_ATIVA": "1",
            "PACKBALL_TRIAGEM_MAX_DETALHES": "10",
            "PACKBALL_TRIAGEM_MIN_DETALHES": "5",
            "PACKBALL_CICLO_ALVO_SEGUNDOS": "300",
            "PACKBALL_CICLO_RESERVA_FINAL_SEGUNDOS": "10",
            "THESTATSAPI_CUSTO_ESTIMADO_JOGO_SEGUNDOS": "3.5",
            "THESTATSAPI_RESERVA_AUDITORIA_FORA_LOTE": "2",
        }), patch("servico_monitor.time.monotonic", return_value=130.0):
            resultado = self.servico._configurar_detalhamento_packball(
                tarefas
            )

        self.assertEqual(resultado["maximo_detalhes"], 10)

    def test_filas_operacionais_colocam_rechecagem_antes_da_exploracao(self):
        tarefas = [
            {
                "jogo": {"url": "explorar", "status": "35 '"},
                "acionavel_fila_detalhada": False,
            },
            {
                "jogo": {"url": "rechecar", "status": "22 '"},
                "acionavel_fila_detalhada": True,
                "rechecagem_pos_evento": True,
            },
            {
                "jogo": {"url": "acompanhar", "status": "52 '"},
                "idade_segundos": 180,
            },
        ]
        with patch.dict(
            os.environ, {"PACKBALL_FILAS_OPERACIONAIS_ATIVAS": "1"}
        ):
            ordenadas, diagnostico = (
                self.servico._separar_filas_operacionais(tarefas)
            )

        self.assertEqual(ordenadas[0]["jogo"]["url"], "rechecar")
        self.assertEqual(diagnostico["urgentes"], 1)
        self.assertEqual(diagnostico["acompanhamento"], 1)
        self.assertEqual(diagnostico["exploracao"], 1)

    def test_fila_final_reserva_melhor_liga_sem_remover_primeira_urgencia(self):
        tarefas = []
        for indice in range(15):
            tarefas.append({
                "jogo": {"url": f"jogo-{indice}", "status": "60 '"},
                "acionavel_fila_detalhada": True,
                "rechecagem_pos_evento": indice < 5,
                "prioridade_liga_gols": 20,
                "pontuacao_indicadores_lista": 10,
            })
        tarefas[-1]["jogo"]["url"] = "liga-forte"
        tarefas[-1]["prioridade_liga_gols"] = 90

        with patch.dict(
            os.environ, {"PACKBALL_FILAS_OPERACIONAIS_ATIVAS": "1"}
        ):
            ordenadas, diagnostico = (
                self.servico._separar_filas_operacionais(tarefas)
            )

        self.assertEqual("jogo-0", ordenadas[0]["jogo"]["url"])
        self.assertIn(
            "liga-forte",
            [item["jogo"]["url"] for item in ordenadas[:4]],
        )
        self.assertTrue(diagnostico["liga_gols_reservada_final"])
        self.assertEqual(
            90, diagnostico["liga_gols_reservada_final_score"]
        )
        self.assertTrue(
            diagnostico[
                "liga_gols_reservada_final_nas_quatro_primeiras"
            ]
        )

    def test_fila_final_nao_reserva_liga_de_gols_depois_do_minuto_82(self):
        tarefas = []
        for indice in range(15):
            tarefas.append({
                "jogo": {"url": f"jogo-{indice}", "status": "60 '"},
                "acionavel_fila_detalhada": True,
                "rechecagem_pos_evento": indice < 5,
                "prioridade_liga_gols": 20,
                "pontuacao_indicadores_lista": 10,
            })
        tarefas[-2]["jogo"].update({
            "url": "forte-valida", "status": "75 '",
        })
        tarefas[-2]["prioridade_liga_gols"] = 80
        tarefas[-1]["jogo"].update({
            "url": "forte-tardia", "status": "86 '",
        })
        tarefas[-1]["prioridade_liga_gols"] = 95

        with patch.dict(
            os.environ, {"PACKBALL_FILAS_OPERACIONAIS_ATIVAS": "1"}
        ):
            ordenadas, diagnostico = (
                self.servico._separar_filas_operacionais(tarefas)
            )

        topo = [item["jogo"]["url"] for item in ordenadas[:4]]
        self.assertIn("forte-valida", topo)
        self.assertNotIn("forte-tardia", topo)
        self.assertEqual(
            80, diagnostico["liga_gols_reservada_final_score"]
        )
        self.assertEqual(
            82, diagnostico["liga_gols_minuto_maximo_reserva"]
        )

    def test_auditoria_bloqueio_promissor_e_silenciosa_e_deduplicada(self):
        self.servico.banco = Mock()
        self.servico.banco.auditoria_bloqueio_ja_registrada.return_value = False
        candidato = {
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": 1.55,
            "pontuacao_tecnica": 72,
            "regra_versao": "sinais-v6",
            "status": "rejeitado",
            "bloqueios": ["atividade_recente_insuficiente_gols"],
            "motivos": ["pressao_historica_forte"],
            "features": {},
        }
        with patch.dict(
            os.environ, {"AUDITORIA_BLOQUEIOS_PROMISSORES_ATIVA": "1"}
        ):
            novos = self.servico._gerar_auditorias_bloqueadas(
                10, [candidato]
            )

        self.assertEqual(len(novos), 1)
        self.assertEqual(novos[0]["status"], "auditoria")
        self.assertFalse(
            novos[0]["features"]["auditoria_bloqueio"]["telegram"]
        )
        self.assertEqual(candidato["status"], "rejeitado")
        self.servico.banco.auditoria_bloqueio_ja_registrada.return_value = True
        with patch.dict(
            os.environ, {"AUDITORIA_BLOQUEIOS_PROMISSORES_ATIVA": "1"}
        ):
            repetidos = self.servico._gerar_auditorias_bloqueadas(
                11, [candidato]
            )
        self.assertEqual(repetidos, [])

    def test_triagem_curta_prioriza_odds_api_sem_cortar_foco(self):
        self.servico.betsapi = Mock()
        self.servico.betsapi.ativa = True
        self.servico.betsapi.cobertura_jogos_ao_vivo.return_value = {
            "ativa": True,
            "pareados": 2,
            "cobertura_por_url": {
                "jogo-5": {"evento_externo_id": "5"},
                "jogo-6": {"evento_externo_id": "6"},
            },
        }
        self.servico._resgate_odds_packball_urls = {"jogo-6"}
        tarefas = [{
            "jogo": {"url": f"jogo-{indice}"},
            "coletar_odds": True,
            "em_foco": indice == 9,
        } for indice in range(10)]
        with patch.dict(os.environ, {
            "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA": "1",
            "PACKBALL_TRIAGEM_MAX_JOGOS": "7",
        }):
            selecionadas, diagnostico = (
                self.servico._aplicar_triagem_capacidade(tarefas)
            )

        urls = [item["jogo"]["url"] for item in selecionadas]
        self.assertIn("jogo-9", urls)
        self.assertIn("jogo-5", urls)
        por_url = {item["jogo"]["url"]: item for item in selecionadas}
        self.assertTrue(por_url["jogo-5"]["odds_api_prioritaria"])
        self.assertFalse(por_url["jogo-6"]["odds_api_prioritaria"])
        self.assertTrue(por_url["jogo-6"]["resgate_odds_packball"])
        self.assertEqual(diagnostico["tarefas_fora_lista_curta"], 2)

    def test_detalhamento_adaptativo_flag_zero_restaura_comportamento(self):
        self.servico.controle_packball = Mock()
        tarefas = [
            {"acionavel_fila_detalhada": True} for _ in range(8)
        ]
        with patch.dict(
            os.environ,
            {"PACKBALL_DETALHAMENTO_ADAPTATIVO": "0"},
        ):
            resultado = self.servico._configurar_detalhamento_packball(
                tarefas
            )

        self.assertFalse(resultado["ativado_no_ciclo"])
        self.assertEqual(resultado["orcamento_efetivo_segundos"], 180.0)
        self.assertIsNone(resultado["maximo_detalhes"])
        self.servico.controle_packball.estado_atual.assert_not_called()

    def test_processamento_adaptativo_para_exatamente_no_quinto(self):
        self.servico.agendador = Mock()
        self.servico.observabilidade = Mock()
        self.servico._duracoes_tarefas_recentes = []
        self.servico.processar_jogo = Mock(return_value={
            "fixture_id": None,
            "odds_coletadas": False,
            "duracao_segundos": 20.0,
            "janelas_temporais": ["5"],
        })
        tarefas = [{
            "jogo": {"url": f"jogo-{indice}"},
            "coletar_odds": False,
            "em_foco": False,
            "idade_segundos": 300,
        } for indice in range(7)]
        instantes = iter((0, 20, 40, 60, 80, 100, 100))

        resultado = self.servico._processar_tarefas_detalhadas(
            None,
            tarefas,
            [],
            orcamento_segundos=225,
            maximo_tarefas=5,
            relogio=lambda: next(instantes),
        )

        self.assertEqual(resultado["processadas"], 5)
        self.assertEqual(resultado["adiadas"], 2)
        self.assertEqual(self.servico.processar_jogo.call_count, 5)

    def test_coleta_mede_prioridade_asiatica_realmente_anexada(self):
        self.servico.agendador = Mock()
        self.servico.observabilidade = Mock()
        self.servico.processar_jogo = Mock(return_value={
            "fixture_id": 10,
            "odds_coletadas": True,
            "duracao_segundos": 30.0,
            "janelas_temporais": ["5"],
            "odd_asiatica_api_priorizada": True,
            "odd_asiatica_api_anexada": True,
        })
        tarefa = {
            "jogo": {"url": "jogo-asiatico"},
            "coletar_odds": False,
            "em_foco": False,
            "idade_segundos": None,
            "odd_asiatica_api_disponivel": True,
            "odd_asiatica_api_alvo_um_escanteio": True,
        }
        instantes = iter((0, 30))

        resultado = self.servico._processar_tarefas_detalhadas(
            None,
            [tarefa],
            [],
            orcamento_segundos=180,
            relogio=lambda: next(instantes),
        )

        self.assertEqual(resultado["prioridades_asiaticas_processadas"], 1)
        self.assertEqual(resultado["odds_asiaticas_api_anexadas"], 1)
        self.assertEqual(resultado["prioridades_asiaticas_sem_anexo"], 0)
        self.assertEqual(resultado["alvos_um_escanteio_processados"], 1)
        self.assertEqual(resultado["alvos_um_escanteio_anexados"], 1)
        self.assertTrue(
            self.servico.processar_jogo.call_args.kwargs[
                "odd_asiatica_api_disponivel"
            ]
        )

    def test_reserva_adaptativa_sempre_permite_primeira_tarefa(self):
        self.servico.agendador = Mock()
        self.servico.observabilidade = Mock()
        self.servico._duracoes_tarefas_recentes = [45.0] * 10
        self.servico.processar_jogo = Mock(return_value={
            "fixture_id": None,
            "odds_coletadas": False,
            "duracao_segundos": 45.0,
            "janelas_temporais": [],
        })
        tarefa = {
            "jogo": {"url": "jogo-prioritario"},
            "coletar_odds": False,
            "em_foco": True,
            "idade_segundos": 500,
        }
        instantes = iter((0, 50))

        resultado = self.servico._processar_tarefas_detalhadas(
            None,
            [tarefa],
            [],
            orcamento_segundos=20,
            relogio=lambda: next(instantes),
        )

        self.assertEqual(resultado["processadas"], 1)
        self.assertEqual(resultado["adiadas"], 0)
        self.assertFalse(resultado["interrompido_por_reserva"])
        self.assertEqual(self.servico.agendador.concluir.call_count, 1)

    def test_configuracao_usa_mesma_abertura_operacional_e_salva_sessao(self):
        playwright = object()
        navegador = Mock()
        navegador.is_connected.return_value = True
        contexto = Mock()
        pagina = Mock()
        packball = Mock()
        packball.url_partidas = "https://packball.com/pt/matches"
        self.servico.packball = packball
        self.servico.arquivo_sessao = Path("sessao-teste.json")
        self.servico._iniciar_playwright_seguro = Mock(
            return_value=nullcontext(playwright)
        )
        self.servico._abrir_navegador = Mock(return_value=(
            navegador, contexto, pagina, pagina,
        ))
        aguardar = Mock()

        with patch("servico_monitor._storage_state_completo") as salvar:
            resultado = self.servico._executar_configuracao_packball(
                aguardar=aguardar
            )

        self.assertTrue(resultado)
        self.servico._abrir_navegador.assert_called_once_with(
            playwright, headless=False
        )
        packball._navegar.assert_called_once_with(
            pagina, packball.url_partidas
        )
        pagina.wait_for_timeout.assert_called_once_with(5000)
        aguardar.assert_called_once()
        salvar.assert_called_once_with(
            contexto, path=self.servico.arquivo_sessao
        )
        navegador.close.assert_called_once()

    def test_configuracao_operacional_recusa_modo_sem_janela(self):
        with self.assertRaisesRegex(
            ValueError, "configuracao_packball_exige_janela_visivel"
        ):
            self.servico._executar_configuracao_packball(headless=True)

    def test_main_persiste_causa_da_falha_fatal_e_libera_trava(self):
        trava = Mock()
        trava.adquirir.return_value = True
        servico = Mock()
        servico.pasta = Path.cwd()
        servico.executar.side_effect = PermissionError(
            "Acesso negado token=segredo"
        )

        with (
            patch("servico_monitor.TravaInstancia", return_value=trava),
            patch("servico_monitor.ServicoMonitor", return_value=servico),
            patch("servico_monitor.hash_codigo_runtime", return_value="hash"),
            patch("servico_monitor.registrar_estado") as registrar,
        ):
            with self.assertRaises(PermissionError):
                main()

        self.assertEqual(registrar.call_count, 3)
        self.assertEqual(registrar.call_args_list[0].args[1], "iniciando")
        self.assertEqual(registrar.call_args_list[1].args[1], "ativo")
        falha = registrar.call_args_list[2]
        self.assertEqual(falha.args[1], "falha")
        self.assertEqual(falha.kwargs["erro"], "PermissionError")
        self.assertNotIn("segredo", falha.kwargs["mensagem"])
        servico.observabilidade.processo_falhou.assert_called_once()
        servico.fechar.assert_called_once()
        trava.liberar.assert_called_once()

    def test_main_publica_pid_antes_do_construtor_e_registra_falha(self):
        trava = Mock()
        trava.adquirir.return_value = True
        with (
            patch("servico_monitor.TravaInstancia", return_value=trava),
            patch("servico_monitor.hash_codigo_runtime", return_value="hash"),
            patch("servico_monitor.registrar_estado") as registrar,
        ):
            def falhar(_pasta):
                self.assertEqual(registrar.call_args.args[1], "iniciando")
                raise RuntimeError("falha inicial")

            with patch("servico_monitor.ServicoMonitor", side_effect=falhar):
                with self.assertRaisesRegex(RuntimeError, "falha inicial"):
                    main()
        self.assertEqual(registrar.call_args.args[1], "falha")
        self.assertEqual(registrar.call_args.kwargs["erro"], "RuntimeError")
        trava.liberar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
