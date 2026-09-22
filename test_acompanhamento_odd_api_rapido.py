import json
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from acompanhamento_odd import extrair_odd_exata_acompanhamento
from avaliacao_desajuste_odds import (
    _carregar_observacoes_precos,
    _parear_observacoes_bookmaker,
)
from banco import BancoMonitor
from calibracao import CalibradorBacktest
from gol_ht_00_min20 import VERSAO as VERSAO_HT_00
from relatorio_desempenho_operacional import resumir_desempenho_operacional
from servico_monitor import ServicoMonitor
from telegram_alertas import AlertasTelegram
from test_acompanhamento_metodos_gols import (
    contexto_ht, preparar_ht_com_protecoes, qualidade_ht,
)
from test_validade_historico_gols import contexto_com_datas


def origem_mercado_teste(linha=2.5, fonte="betsapi"):
    return {
        "schema": "origem-mercado-odd-v1",
        "fonte": fonte,
        "identificador": "mercado-123",
        "nome": "Match Goals",
        "linha": linha,
        "lados": ["over", "under"],
        "bookmaker": "bet365",
    }


class BancoFalso:
    def __init__(self, item):
        self.item = item
        self.observacoes = []
        self.consultas = []
        self.parametros_fila = []
        self.comparacoes = []
        self.corroboracoes = []
        self.referencias_sombra = []
        self.resposta_observacao = {
            "estado": "nova_observacao",
            "persistido": True,
            "nova_linha": True,
            "mudanca_material": True,
            "ordem_temporal_valida": True,
        }

    def acompanhamentos_odd_para_rechecagem_api(
        self, limite, *, snapshot_desde=None,
    ):
        self.parametros_fila.append({
            "limite": limite,
            "snapshot_desde": snapshot_desde,
        })
        return [self.item]

    def registrar_consulta_acompanhamento_odd_api(
        self, sinal_id, **opcoes,
    ):
        self.consultas.append({"sinal_id": sinal_id, **opcoes})
        return {"estado": "consulta_registrada", "persistido": True}

    def registrar_observacao_acompanhamento_odd(
        self, sinal_id, oferta, estado, **opcoes
    ):
        self.observacoes.append({
            "sinal_id": sinal_id,
            "oferta": oferta,
            "estado": estado,
            **opcoes,
        })
        return dict(self.resposta_observacao)

    def registrar_comparacao_acompanhamento_odd_api(
        self, sinal_id, oferta, estado, **opcoes
    ):
        self.comparacoes.append({
            "sinal_id": sinal_id,
            "oferta": oferta,
            "estado": estado,
            **opcoes,
        })
        return {
            "estado": "comparacao_registrada",
            "persistidos": 1,
            "aplicacao_sinais": False,
            "chamadas_api_adicionais": 0,
        }

    def registrar_corroboracao_acompanhamento_odd_api(
        self, sinal_id, odds, estado, **opcoes
    ):
        self.corroboracoes.append({
            "sinal_id": sinal_id,
            "odds": odds,
            "estado": estado,
            **opcoes,
        })
        return {
            "estado": "corroboracao_registrada",
            "persistidos": 2,
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }

    def registrar_referencia_sombra_acompanhamento_odd(
        self, sinal_id, odds, diagnostico, estado, **opcoes
    ):
        self.referencias_sombra.append({
            "sinal_id": sinal_id,
            "odds": odds,
            "diagnostico": diagnostico,
            "estado": estado,
            **opcoes,
        })
        return {
            "estado": "referencia_sombra_auditada",
            "persistido": True,
            "observacao_id": 77,
            "aplicacao_sinais": False,
        }

    def estado_acompanhamento_odd_api_ja_registrado(
        self, sinal_id, placar, status_codigo
    ):
        return False


class APIFalsa:
    def __init__(self, placar="0-2", odd=None):
        casa, fora = (int(valor) for valor in placar.split("-"))
        self.odd = odd
        self.chamadas_odds_ft = 0
        self.chamadas_odds_ht = 0
        self.chamadas_odds_proximo_gol = 0
        self.fixture = {
            "fixture": {
                "id": 123,
                "status": {"elapsed": 48, "short": "2H"},
            },
            "goals": {"home": casa, "away": fora},
        }

    def fixtures_ao_vivo_detalhadas(self, ids):
        return [self.fixture]

    def odds_gols_total_ft(self, fixture_id):
        self.chamadas_odds_ft += 1
        if self.odd is None:
            return None
        return {
            "categoria": "gols",
            "fonte": "api_football",
            "idade_segundos": 0.0,
            "ofertas": [{
                "linha": 2.5,
                "over": self.odd,
                "under": 2.8,
                "fonte": "api_football",
                "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "cache": False,
                "origem_mercado": origem_mercado_teste(
                    2.5, "api_football"
                ),
            }],
            "ofertas_ht": [],
        }

    def odds_gols_total_ht(self, fixture_id):
        self.chamadas_odds_ht += 1
        return None

    def odds_proximo_gol(self, fixture_id, gols_atuais):
        self.chamadas_odds_proximo_gol += 1
        return None


class BetsAPIFalsa:
    aplicacao_sinais = True

    def __init__(self, odd=1.40):
        self.odd = odd

    def buscar_mercados(self, jogo, mercados):
        coletado_em = datetime.now().astimezone().replace(
            microsecond=0
        ).isoformat()
        identidade_evento = {
            "schema": "identidade-evento-odd-v1",
            "confirmada": True,
            "fonte": "betsapi",
            "evento_externo_id": "bets-123",
            "orientacao": "direta",
            "similaridade": 0.95,
            "mandante_normalizado": jogo.get("mandante"),
            "visitante_normalizado": jogo.get("visitante"),
            "placar_normalizado": jogo.get("placar"),
            "metodo": "teste",
        }
        return {
            "ao_vivo": [{
                "categoria": "gols",
                "identidade_evento": identidade_evento,
                "ofertas": [{
                    "linha": 2.5,
                    "over": self.odd,
                    "under": 2.8,
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "idade_segundos": 0.0,
                    "coletado_em": coletado_em,
                    "cache": False,
                    "origem_mercado": origem_mercado_teste(),
                }],
                "ofertas_ht": [],
            }],
        }, {"pareado": True, "motivo": "oferta_anexada"}


class ObservabilidadeFalsa:
    def __init__(self):
        self.registros = []

    def ciclo_progresso(self, etapa, **dados):
        self.registros.append({"etapa": etapa, **dados})


class CalibradorFalso:
    def __init__(self, probabilidade):
        self.probabilidade = probabilidade

    def aplicar(self, candidato):
        candidato["probabilidade_calibrada"] = self.probabilidade


class BacktestFalso:
    def avaliar_snapshot(self, snapshot_id):
        return 0


class AlertasFalso:
    def __init__(self):
        self.atualizacoes = 0

    def atualizar_acompanhamentos_odd(self, limite=50):
        self.atualizacoes += 1
        return {
            "consultados": 1,
            "conclusivos": 1,
            "entregues": 1,
            "erros": 0,
            "bloqueados": 0,
        }


class AcompanhamentoOddAPIRapidoTest(unittest.TestCase):
    def setUp(self):
        # A suíte cobre os três mercados contratuais; a carteira restrita
        # do .env é uma decisão operacional de produção.
        self._carteira_odd = patch.dict(os.environ, {
            "AVISO_AGUARDAR_ODD_MERCADOS": "gol_ft,gol_ht,proximo_gol",
        })
        self._carteira_odd.start()

    def tearDown(self):
        self._carteira_odd.stop()

    @staticmethod
    def item():
        acompanhamento = {
            "elegivel_aviso": True,
            "conversao_confirmada": True,
            "tendencia_packball_confirmada": True,
            "odd_alvo": 1.40,
            "odd_maxima_operacional": 2.50,
        }
        return {
            "origem_sinal_id": 10,
            "sinal_id": 11,
            "api_fixture_id": 123,
            "api_orientacao": "direta",
            "mercado": "gol_ft",
            "linha": 2.5,
            "placar_origem": "0-2",
            "snapshot_em": datetime.now().replace(microsecond=0).isoformat(),
            "features_json": json.dumps({
                "acompanhamento_odd": acompanhamento
            }),
            "packball_url": "https://packball/match/123",
            "mandante": "Al Tadhamon",
            "visitante": "Al Salmiyah",
        }

    def servico(self, *, placar="0-2", odd=1.40, odd_api=None):
        servico = ServicoMonitor.__new__(ServicoMonitor)
        servico._ultima_rechecagem_odd_api = 0.0
        servico._operacao_bloqueada_ciclo = False
        servico.banco = BancoFalso(self.item())
        servico.api = APIFalsa(placar, odd_api)
        servico.betsapi = BetsAPIFalsa(odd)
        servico.observabilidade = ObservabilidadeFalsa()
        servico.registros_desfecho = []
        servico.salvar_registro = lambda registro: (
            servico.registros_desfecho.append(registro) or 700
        )
        servico.backtest = BacktestFalso()
        servico.alertas = AlertasFalso()
        servico._validar_operacao_para_alerta_oficial = lambda: {
            "apto": True, "estado": "pronta"
        }
        servico.materializados = []
        servico._materializar_entrada_acompanhamento_odd_api = (
            lambda item, fixture, estado, odds, avaliacao: (
                servico.materializados.append({
                    "item": item,
                    "estado": estado,
                    "avaliacao": avaliacao,
                })
                or {"estado": "enviado"}
            )
        )
        return servico

    def test_atingiu_140_envia_sem_objeto_packball_ou_navegacao(self):
        servico = self.servico()
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(
                forcar=True
            )
        self.assertEqual(resumo["enviados"], 1)
        self.assertEqual(len(servico.materializados), 1)
        self.assertEqual(resumo["observacoes_odds"], 1)
        self.assertEqual(resumo["mudancas_odds"], 1)
        self.assertEqual(len(servico.banco.observacoes), 1)
        self.assertEqual(len(servico.banco.consultas), 1)
        self.assertEqual(len(servico.banco.comparacoes), 1)
        self.assertEqual(resumo["comparacoes_odds_fontes"], 1)
        self.assertFalse(hasattr(servico, "packball"))

    @staticmethod
    def _referencia_the_odds(item, estado, linha=2.5):
        coletado_em = datetime.now().astimezone().replace(
            microsecond=0
        ).isoformat()
        identidade = {
            "schema": "identidade-evento-odd-v1",
            "confirmada": True,
            "fonte": "the_odds_api",
            "evento_externo_id": "odds-evento-123",
            "orientacao": "direta",
            "similaridade": 0.98,
            "mandante_normalizado": item["mandante"],
            "visitante_normalizado": item["visitante"],
            "placar_normalizado": estado["placar"],
            "metodo": "teste",
        }
        origem = {
            "schema": "origem-mercado-odd-v1",
            "fonte": "the_odds_api",
            "identificador": "odds-evento-123:alternate_totals:pinnacle",
            "nome": "alternate_totals",
            "linha": linha,
            "lados": ["over", "under"],
            "bookmaker": "pinnacle",
        }
        referencia = {"pre_jogo": [], "ao_vivo": [{
            "categoria": "gols",
            "escopo": "total",
            "tipo_mercado": "total",
            "formato": "duas_opcoes",
            "fonte": "the_odds_api",
            "ofertas": [{
                "linha": linha,
                "over": 1.62,
                "under": 2.28,
                "fonte": "the_odds_api",
                "bookmaker": "pinnacle",
                "coletado_em": coletado_em,
                "idade_segundos": 0.0,
                "cache": False,
                "identidade_evento": identidade,
                "origem_mercado": origem,
            }],
            "ofertas_ht": [],
        }]}
        diagnostico = {
            "ativa": True,
            "pareado": True,
            "motivo": "oferta_anexada",
            "consultados": ["alternate_totals"],
            "anexados": ["gol_ft"],
            "reserva_consumida": True,
            "custo_estimado_creditos": 1,
            "reserva": {"autorizada": True},
            "auditoria_amostragem": {
                "origem_coleta": "monitor_odd_rapido",
            },
            "aplicacao_sinais": False,
            "telegram": False,
        }
        return referencia, diagnostico

    def test_referencia_rapida_mesma_linha_e_auditada_sem_mudar_odds(self):
        servico = self.servico(odd=1.32)
        servico.the_odds_api = type("Cliente", (), {
            "amostragem_referencia_ativa": True,
        })()
        item = servico.banco.item
        estado = {
            "placar": "0-2", "minuto": 48, "status": "48'",
        }
        odds, _ = servico.betsapi.buscar_mercados(
            {
                "mandante": item["mandante"],
                "visitante": item["visitante"],
                "placar": estado["placar"],
            },
            {"gol_ft"},
        )
        oferta = {
            "linha": 2.5, "odd": 1.32, "fonte": "betsapi",
            "bookmaker": "bet365",
        }
        referencia, diagnostico = self._referencia_the_odds(item, estado)
        servico._amostrar_referencia_odds_sombra = (
            lambda *args, **kwargs: (referencia, diagnostico)
        )
        quantidade_operacional = len(odds["ao_vivo"])

        resultado = servico._amostrar_referencia_odd_monitor_rapido(
            item, estado, oferta, odds
        )

        self.assertTrue(resultado["reserva_consumida"])
        self.assertTrue(resultado["consulta_executada"])
        self.assertTrue(resultado["linha_exata"])
        self.assertTrue(resultado["auditoria_persistida"])
        self.assertTrue(resultado["observacao_persistida"])
        self.assertEqual(2, resultado["comparacoes_persistidas"])
        self.assertEqual(1, len(servico.banco.referencias_sombra))
        self.assertEqual(1, len(servico.banco.observacoes))
        self.assertEqual(
            "the_odds_api",
            servico.banco.observacoes[0]["oferta"]["fonte"],
        )
        self.assertEqual(quantidade_operacional, len(odds["ao_vivo"]))
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["telegram"])

    def test_fluxo_real_grava_par_temporal_exato_para_avaliacao(self):
        caminho = Path(f".teste_referencia_rapida_{uuid4().hex}.db")
        banco = BancoMonitor(caminho)
        agora = datetime.now().astimezone().replace(microsecond=0)
        try:
            snapshot_id = banco.salvar_registro({
                "coletado_em": agora.isoformat(),
                "url": "https://packball/match/123",
                "mandante": "Al Tadhamon",
                "visitante": "Al Salmiyah",
                "pais": "Kuwait",
                "liga": "Premier League",
                "placar": "0-2",
                "status": "48 '",
                "odds": {"pre_jogo": [], "ao_vivo": []},
            })
            sinal_id = banco.salvar_candidatos(snapshot_id, [{
                "mercado": "gol_ft",
                "linha": 2.5,
                "odd": 1.32,
                "pontuacao_tecnica": 80,
                "regra_versao": "teste-fluxo-referencia-rapida-v1",
                "status": "rejeitado",
                "features": {},
            }], criado_em=agora.isoformat())[0]
            item = self.item()
            item.update({
                "origem_sinal_id": sinal_id,
                "sinal_id": sinal_id,
                "snapshot_id": snapshot_id,
                "snapshot_em": agora.isoformat(),
                "placar_origem": "0-2",
                "status_origem": "48 '",
                "pais": "Kuwait",
                "liga": "Premier League",
            })
            estado = {
                "placar": "0-2", "minuto": 48, "status": "48 '",
            }
            cliente_betsapi = BetsAPIFalsa(odd=1.32)
            odds_operacionais, _ = cliente_betsapi.buscar_mercados(
                {
                    "mandante": item["mandante"],
                    "visitante": item["visitante"],
                    "placar": estado["placar"],
                },
                {"gol_ft"},
            )
            oferta_betsapi = extrair_odd_exata_acompanhamento(
                odds_operacionais, "gol_ft", 2.5
            )
            observacao_betsapi = (
                banco.registrar_observacao_acompanhamento_odd(
                    sinal_id,
                    oferta_betsapi,
                    estado,
                    consultado_em=agora.isoformat(),
                    odds=odds_operacionais,
                )
            )
            self.assertTrue(observacao_betsapi["persistido"])

            servico = ServicoMonitor.__new__(ServicoMonitor)
            servico.banco = banco
            servico.the_odds_api = type("Cliente", (), {
                "amostragem_referencia_ativa": True,
            })()
            referencia, diagnostico = self._referencia_the_odds(
                item, estado
            )
            servico._amostrar_referencia_odds_sombra = (
                lambda *args, **kwargs: (referencia, diagnostico)
            )
            resultado = servico._amostrar_referencia_odd_monitor_rapido(
                item,
                estado,
                oferta_betsapi,
                odds_operacionais,
            )

            ancora = (agora - timedelta(minutes=1)).isoformat()
            observacoes, invalidas = _carregar_observacoes_precos(
                banco, ancora
            )
            pares, _ = _parear_observacoes_bookmaker(
                observacoes, "bet365",
                delta_absoluto_minimo=0.0,
                delta_relativo_minimo=0.0,
            )
            fontes = {item["fonte"] for item in observacoes}
            comparacoes = banco.conexao.execute(
                "SELECT COUNT(*) FROM comparacoes_odds_fontes "
                "WHERE motivos_json LIKE '%corroboracao_odd_entrada_rapida%'"
            ).fetchone()[0]

            self.assertTrue(resultado["observacao_persistida"])
            self.assertEqual(2, resultado["comparacoes_persistidas"])
            self.assertEqual(0, invalidas)
            self.assertIn("betsapi", fontes)
            self.assertIn("the_odds_api", fontes)
            self.assertEqual(1, len(pares))
            self.assertEqual("betsapi", pares[0]["fonte_bookmaker"])
            self.assertEqual("the_odds_api", pares[0]["fonte_controle"])
            self.assertEqual(2, comparacoes)
            self.assertFalse(resultado["aplicacao_sinais"])
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_referencia_rapida_sem_mesma_linha_nao_fabrica_comparacao(self):
        servico = self.servico(odd=1.32)
        servico.the_odds_api = type("Cliente", (), {
            "amostragem_referencia_ativa": True,
        })()
        item = servico.banco.item
        estado = {
            "placar": "0-2", "minuto": 48, "status": "48'",
        }
        odds, _ = servico.betsapi.buscar_mercados(
            {
                "mandante": item["mandante"],
                "visitante": item["visitante"],
                "placar": estado["placar"],
            },
            {"gol_ft"},
        )
        referencia, diagnostico = self._referencia_the_odds(
            item, estado, linha=3.5
        )
        servico._amostrar_referencia_odds_sombra = (
            lambda *args, **kwargs: (referencia, diagnostico)
        )

        resultado = servico._amostrar_referencia_odd_monitor_rapido(
            item,
            estado,
            {
                "linha": 2.5, "odd": 1.32, "fonte": "betsapi",
                "bookmaker": "bet365",
            },
            odds,
        )

        self.assertEqual("referencia_sem_mesma_linha", resultado["motivo"])
        self.assertTrue(resultado["auditoria_persistida"])
        self.assertFalse(resultado["linha_exata"])
        self.assertFalse(resultado["observacao_persistida"])
        self.assertEqual(0, resultado["comparacoes_persistidas"])
        self.assertEqual([], servico.banco.observacoes)
        self.assertEqual([], servico.banco.corroboracoes)

    def test_alerta_e_materializado_antes_da_consulta_sombra(self):
        servico = self.servico(odd=1.40)
        ordem = []
        sinais_referencia = []
        servico._materializar_entrada_acompanhamento_odd_api = (
            lambda *args, **kwargs: (
                ordem.append("materializar")
                or {"estado": "enviado", "sinal_id": 777}
            )
        )
        servico._amostrar_referencia_odd_monitor_rapido = (
            lambda *args, **kwargs: (
                ordem.append("referencia")
                or sinais_referencia.append(kwargs.get("sinal_enviado_id"))
                or {
                    "tentada": True,
                    "reserva_consumida": True,
                    "consulta_executada": True,
                    "linha_exata": True,
                    "auditoria_persistida": True,
                    "observacao_persistida": True,
                    "comparacoes_persistidas": 1,
                    "creditos_estimados_reservados": 1,
                    "motivo": "referencia_mesma_linha_persistida",
                    "aplicacao_sinais": False,
                }
            )
        )

        resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual(["materializar", "referencia"], ordem)
        self.assertEqual([777], sinais_referencia)
        self.assertEqual(1, resumo["enviados"])
        self.assertEqual(1, resumo["referencias_sombra_rapidas_tentadas"])
        self.assertEqual(1, resumo["comparacoes_referencia_sombra_rapida"])
        self.assertEqual(2, resumo["comparacoes_odds_fontes"])
        self.assertFalse(resumo["aplicacao_sinais_referencia_sombra"])
        funil = resumo["referencias_sombra_rapidas_funil"]
        self.assertEqual(1, funil["avaliadas"])
        self.assertEqual(1, funil["aprovadas"])
        self.assertEqual(0, funil["reprovadas"])
        self.assertEqual(1, funil["alertas_enviados"])
        self.assertEqual(1, funil["fontes_executaveis_pos_envio"])
        self.assertEqual(1, funil["selecionadas_para_consulta"])
        self.assertEqual(0, funil["suprimidas_limite_rodada"])
        self.assertFalse(funil["aplicacao_sinais"])

    def test_reprovacao_nao_consumira_vaga_da_referencia_rapida(self):
        servico = self.servico(odd=1.32)
        chamadas = []
        servico._amostrar_referencia_odd_monitor_rapido = (
            lambda *args, **kwargs: chamadas.append((args, kwargs))
        )

        resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual([], chamadas)
        self.assertEqual(0, resumo["referencias_sombra_rapidas_tentadas"])
        funil = resumo["referencias_sombra_rapidas_funil"]
        self.assertEqual(1, funil["avaliadas"])
        self.assertEqual(0, funil["aprovadas"])
        self.assertEqual(1, funil["reprovadas"])
        self.assertEqual(0, funil["alertas_enviados"])
        self.assertEqual(0, funil["selecionadas_para_consulta"])
        self.assertEqual(
            1,
            sum(
                quantidade
                for motivo, quantidade in funil["exclusoes"].items()
                if motivo.startswith("decisao_reprovada:")
            ),
        )

    def test_materializacao_bloqueada_nao_consome_referencia_rapida(self):
        servico = self.servico(odd=1.40)
        chamadas = []
        servico._materializar_entrada_acompanhamento_odd_api = (
            lambda *args, **kwargs: {"estado": "duplicado"}
        )
        servico._amostrar_referencia_odd_monitor_rapido = (
            lambda *args, **kwargs: chamadas.append((args, kwargs))
        )

        resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual([], chamadas)
        self.assertEqual(0, resumo["enviados"])
        funil = resumo["referencias_sombra_rapidas_funil"]
        self.assertEqual(1, funil["aprovadas"])
        self.assertEqual(1, funil["bloqueadas_materializacao"])
        self.assertEqual(0, funil["alertas_enviados"])
        self.assertEqual(
            1,
            funil["exclusoes"]["materializacao_bloqueada:duplicado"],
        )

    def test_limite_da_rodada_prioriza_primeiro_alerta_enviado(self):
        servico = self.servico(odd=1.40)
        primeiro = dict(servico.banco.item)
        segundo = dict(servico.banco.item)
        segundo.update({"origem_sinal_id": 20, "sinal_id": 21})
        servico.banco.acompanhamentos_odd_para_rechecagem_api = (
            lambda *args, **kwargs: [primeiro, segundo]
        )
        chamadas = []
        servico._amostrar_referencia_odd_monitor_rapido = (
            lambda *args, **kwargs: (
                chamadas.append(args[0]["sinal_id"])
                or {
                    "tentada": True,
                    "reserva_consumida": True,
                    "consulta_executada": True,
                    "linha_exata": True,
                    "auditoria_persistida": True,
                    "observacao_persistida": True,
                    "comparacoes_persistidas": 2,
                    "creditos_estimados_reservados": 1,
                    "motivo": "referencia_mesma_linha_persistida",
                    "aplicacao_sinais": False,
                }
            )
        )

        resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual([11], chamadas)
        self.assertEqual(2, resumo["enviados"])
        funil = resumo["referencias_sombra_rapidas_funil"]
        self.assertEqual(2, funil["alertas_enviados"])
        self.assertEqual(2, funil["fontes_executaveis_pos_envio"])
        self.assertEqual(1, funil["selecionadas_para_consulta"])
        self.assertEqual(1, funil["suprimidas_limite_rodada"])
        self.assertEqual(
            1, funil["exclusoes"]["limite_referencias_rapidas_rodada"]
        )

    def test_lote_configuravel_e_limite_seguro_sao_aplicados(self):
        servico = self.servico(odd=1.32)
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_LOTE": "999",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["lote_maximo"], 20)
        self.assertEqual(
            servico.banco.parametros_fila[-1]["limite"], 20
        )
        self.assertIsNotNone(
            servico.banco.parametros_fila[-1]["snapshot_desde"]
        )

    def test_odd_abaixo_do_alvo_e_auditada_sem_enviar(self):
        servico = self.servico(odd=1.32)
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(resumo["observacoes_odds"], 1)
        self.assertEqual(
            resumo["motivos"].get("odd_ainda_abaixo_do_alvo"), 1
        )
        self.assertEqual(
            servico.banco.observacoes[0]["oferta"]["odd"], 1.32
        )

    def test_controle_api_football_nao_gasta_chamada_antes_do_alvo(self):
        servico = self.servico(odd=1.32, odd_api=1.42)
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual(0, resumo["atingiram_alvo"])
        self.assertEqual(0, resumo["corroboracoes_api_football_solicitadas"])
        self.assertEqual(0, resumo["corroboracoes_api_football_disponiveis"])
        self.assertEqual(0, resumo["comparacoes_corroboracao_odds"])
        self.assertEqual(0, servico.api.chamadas_odds_ft)
        self.assertEqual([], servico.banco.corroboracoes)

    def test_alvo_coleta_e_persiste_controle_api_football_em_shadow(self):
        servico = self.servico(odd=1.40, odd_api=1.42)
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual(1, resumo["enviados"])
        self.assertEqual(1, resumo["corroboracoes_api_football_solicitadas"])
        self.assertEqual(1, resumo["corroboracoes_api_football_disponiveis"])
        self.assertEqual(2, resumo["comparacoes_corroboracao_odds"])
        self.assertEqual(1, servico.api.chamadas_odds_ft)
        self.assertEqual(1, len(servico.banco.corroboracoes))
        fontes = {
            mercado.get("fonte")
            or ((mercado.get("ofertas") or [{}])[0].get("fonte"))
            for mercado in servico.banco.corroboracoes[0]["odds"]["ao_vivo"]
        }
        self.assertEqual({"betsapi", "api_football"}, fontes)
        self.assertEqual(
            "betsapi",
            servico.materializados[0]["avaliacao"]["oferta"]["fonte"],
        )

    def test_indisponibilidade_do_controle_nao_bloqueia_sinal_principal(self):
        servico = self.servico(odd=1.40, odd_api=None)
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual(1, resumo["enviados"])
        self.assertEqual(1, resumo["corroboracoes_api_football_solicitadas"])
        self.assertEqual(0, resumo["corroboracoes_api_football_disponiveis"])
        self.assertEqual(0, resumo["comparacoes_corroboracao_odds"])
        self.assertEqual(1, servico.api.chamadas_odds_ft)
        self.assertEqual([], servico.banco.corroboracoes)

    def test_observacao_fora_de_ordem_nao_simula_movimento_de_mercado(self):
        servico = self.servico(odd=1.40)
        servico.banco.resposta_observacao = {
            "estado": "nova_observacao_fora_de_ordem",
            "persistido": True,
            "nova_linha": True,
            "mudanca_material": False,
            "ordem_temporal_valida": False,
        }
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual(resumo["observacoes_odds"], 1)
        self.assertEqual(resumo["mudancas_odds"], 0)
        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(resumo["bloqueados"], 1)
        self.assertEqual(resumo["comparacoes_odds_fontes"], 0)
        self.assertEqual(servico.materializados, [])
        self.assertEqual(
            resumo["motivos"].get("regressao_temporal_observacao_odd"), 1
        )

    def test_recusa_da_custodia_bloqueia_envio_e_comparacao(self):
        servico = self.servico(odd=1.40)
        servico.banco.resposta_observacao = {
            "estado": "identidade_evento_alterada",
            "persistido": False,
            "motivo": "evento_externo_trocado_na_mesma_fonte",
        }
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(resumo["atingiram_alvo"], 0)
        self.assertEqual(resumo["observacoes_odds"], 0)
        self.assertEqual(resumo["bloqueados"], 1)
        self.assertEqual(resumo["comparacoes_odds_fontes"], 0)
        self.assertEqual(servico.materializados, [])
        self.assertEqual(
            resumo["motivos"].get(
                "evento_externo_trocado_na_mesma_fonte"
            ),
            1,
        )

    def test_anomalia_curva_persistida_nunca_vira_sinal_ou_comparacao(self):
        servico = self.servico(odd=1.40)
        servico.banco.resposta_observacao = {
            "estado": "anomalia_curva_odd",
            "persistido": True,
            "autorizada": False,
            "motivo": "curva_linhas_odd_incoerente",
            "nova_linha": True,
            "mudanca_material": False,
            "ordem_temporal_valida": True,
        }
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)

        self.assertEqual(1, resumo["observacoes_odds"])
        self.assertEqual(1, resumo["anomalias_curva_odds"])
        self.assertEqual(1, resumo["bloqueados"])
        self.assertEqual(0, resumo["atingiram_alvo"])
        self.assertEqual(0, resumo["enviados"])
        self.assertEqual(0, resumo["comparacoes_odds_fontes"])
        self.assertEqual([], servico.materializados)
        self.assertIn("odds", servico.banco.observacoes[0])
        self.assertEqual(
            1, resumo["motivos"].get("curva_linhas_odd_incoerente")
        )

    def test_janela_de_quinze_minutos_cobre_alvo_sem_novo_packball(self):
        servico = self.servico(odd=1.40)
        servico.banco.item["snapshot_em"] = (
            datetime.now() - timedelta(minutes=11)
        ).replace(microsecond=0).isoformat()
        servico.api.fixture["fixture"]["status"]["elapsed"] = 57
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "900",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(
                forcar=True
            )
        self.assertEqual(resumo["enviados"], 1)
        self.assertEqual(resumo["atingiram_alvo"], 1)
        self.assertEqual(len(servico.materializados), 1)
        self.assertEqual(
            servico.materializados[0]["estado"]["minuto"], 57
        )
        self.assertFalse(hasattr(servico, "packball"))

    def test_placar_mudou_bloqueia_antes_de_materializar(self):
        servico = self.servico(placar="1-2")
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(
                forcar=True
            )
        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(servico.materializados, [])
        self.assertEqual(resumo["motivos"].get("placar_alterado"), 1)
        self.assertEqual(resumo["estados_decisivos"], 1)
        self.assertEqual(resumo["avisos_resultado_atualizados"], 1)
        self.assertEqual(len(servico.registros_desfecho), 1)
        self.assertTrue(
            servico.registros_desfecho[0]["qualidade"][
                "apto_para_liquidacao"
            ]
        )
        self.assertFalse(hasattr(servico, "packball"))

    def test_falha_api_football_fica_isolada_do_ciclo_principal(self):
        servico = self.servico()

        def falhar(ids):
            raise RuntimeError("API temporariamente indisponivel")

        servico.api.fixtures_ao_vivo_detalhadas = falhar
        resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["motivo"], "falha_isolada_api")
        self.assertEqual(resumo["tipo_erro"], "RuntimeError")
        self.assertEqual(
            servico.observabilidade.registros[-1]["etapa"],
            "acompanhamento_odd_api_rapido",
        )

    def test_falha_betsapi_do_item_nao_interrompe_vigilancia(self):
        servico = self.servico()

        def falhar(jogo, mercados):
            raise TimeoutError("timeout da fonte")

        servico.betsapi.buscar_mercados = falhar
        resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["consultados"], 1)
        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(
            resumo["motivos"].get("falha_isolada_betsapi_item"), 1
        )

    def test_api_football_cobre_evento_nao_pareado_pela_betsapi(self):
        servico = self.servico(odd=1.22, odd_api=1.40)
        servico.betsapi.buscar_mercados = lambda jogo, mercados: (
            {"ao_vivo": []},
            {"pareado": False, "motivo": "evento_nao_encontrado"},
        )
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["atingiram_alvo"], 1)
        self.assertEqual(resumo["enviados"], 1)
        self.assertEqual(len(servico.materializados), 1)
        oferta = servico.materializados[0]["avaliacao"]["oferta"]
        self.assertEqual(oferta["odd"], 1.40)
        self.assertEqual(oferta["fonte"], "api_football")
        self.assertEqual(resumo["observacoes_odds"], 1)
        self.assertFalse(hasattr(servico, "packball"))

    def test_api_football_mantem_vigilancia_com_betsapi_desativada(self):
        servico = self.servico(odd=1.22, odd_api=1.40)
        servico.betsapi.aplicacao_sinais = False
        servico.betsapi.buscar_mercados = lambda jogo, mercados: self.fail(
            "BetsAPI desativada nao deveria ser consultada"
        )
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["atingiram_alvo"], 1)
        self.assertEqual(resumo["enviados"], 1)
        self.assertEqual(resumo["observacoes_odds"], 1)
        oferta = servico.materializados[0]["avaliacao"]["oferta"]
        self.assertEqual(oferta["fonte"], "api_football")

    def test_leitura_expirada_nao_consome_as_apis(self):
        servico = self.servico()
        servico.banco.item["snapshot_em"] = (
            datetime.now() - timedelta(seconds=601)
        ).replace(microsecond=0).isoformat()
        servico.banco.item.update({
            "fila_total": 1,
            "fila_tecnica_recente_total": 0,
            "fila_tecnica_dormente_total": 1,
            "fila_recente_nunca_consultada": 0,
        })
        servico.api.fixtures_ao_vivo_detalhadas = lambda ids: self.fail(
            "Leitura expirada nao deveria consultar a API-Football"
        )
        servico.betsapi.buscar_mercados = lambda jogo, mercados: self.fail(
            "Leitura expirada nao deveria consultar a BetsAPI"
        )
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["consultados"], 0)
        self.assertEqual(
            resumo["motivo"], "sem_acompanhamento_tecnico_recente"
        )
        self.assertEqual(
            resumo["motivos"].get("leitura_tecnica_expirada"), 1
        )
        self.assertEqual(resumo["fila_tecnica_recente"], 0)
        self.assertEqual(resumo["fila_tecnica_dormente"], 1)
        self.assertEqual(resumo["fila_pendente_apos_lote"], 0)

    def test_api_football_cobre_gol_ht_sem_evento_na_betsapi(self):
        servico = self.servico(odd=1.22)
        servico.banco.item["mercado"] = "gol_ht"
        servico.banco.item["linha"] = 0.5
        servico.api.fixture["fixture"]["status"]["elapsed"] = 40
        servico.api.fixture["fixture"]["status"]["short"] = "1H"
        servico.api.odds_gols_total_ht = lambda fixture_id: {
            "categoria": "gols",
            "fonte": "api_football",
            "idade_segundos": 0.0,
            "ofertas": [],
            "ofertas_ht": [{
                "linha": 0.5,
                "over": 1.44,
                "under": 2.7,
                "fonte": "api_football",
                "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "cache": False,
                "origem_mercado": origem_mercado_teste(
                    0.5, "api_football"
                ),
            }],
        }
        servico.betsapi.buscar_mercados = lambda jogo, mercados: (
            {"ao_vivo": []},
            {"pareado": False, "motivo": "evento_nao_encontrado"},
        )
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "ACOMPANHAMENTO_ODD_API_TTL_TECNICO_SEGUNDOS": "600",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["atingiram_alvo"], 1)
        self.assertEqual(resumo["enviados"], 1)
        oferta = servico.materializados[0]["avaliacao"]["oferta"]
        self.assertEqual(oferta["odd"], 1.44)
        self.assertEqual(oferta["linha"], 0.5)
        self.assertEqual(oferta["fonte"], "api_football")

    def test_fila_existente_de_mercado_fora_da_carteira_nao_converte(self):
        servico = self.servico(odd=1.40)
        servico.banco.item["mercado"] = "gol_ht"
        servico.banco.item["linha"] = 0.5
        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            "AVISO_AGUARDAR_ODD_MERCADOS": "gol_ft",
        }):
            resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["consultados"], 0)
        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(servico.materializados, [])
        self.assertEqual(
            resumo["motivos"].get(
                "mercado_fora_carteira_acompanhamento_odd"
            ),
            1,
        )

    def test_sem_calibracao_nao_persiste_sinal_aberto(self):
        servico = ServicoMonitor.__new__(ServicoMonitor)
        servico.calibrador = CalibradorFalso(None)
        servico.salvar_registro = lambda registro: self.fail(
            "nao deveria persistir sem calibracao"
        )
        resultado = servico._materializar_entrada_acompanhamento_odd_api(
            self._item_materializacao(),
            {},
            {"placar": "0-2", "minuto": 48, "status": "48'"},
            {},
            self._avaliacao_materializacao(),
        )
        self.assertEqual(resultado["estado"], "sem_calibracao_ativa")
        self.assertFalse(resultado["persistido"])

    def test_materializacao_expoe_inversao_da_curva_na_telemetria(self):
        servico = ServicoMonitor.__new__(ServicoMonitor)
        servico.calibrador = CalibradorFalso(0.80)
        avaliacao = self._avaliacao_materializacao()
        selecionada = avaliacao["oferta"]
        linha_baixa = {
            **selecionada,
            "linha": 0.5,
            "over": 1.50,
            "under": 2.00,
            "odd": 1.50,
            "odd_oposta": 2.00,
            "origem_mercado": origem_mercado_teste(0.5),
        }
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "tipo_mercado": "total", "formato": "duas_opcoes",
            "fonte": "betsapi", "bookmaker": "bet365",
            "ofertas": [linha_baixa, selecionada],
        }]}

        resultado = servico._materializar_entrada_acompanhamento_odd_api(
            self._item_materializacao(), {},
            {"placar": "0-2", "minuto": 48, "status": "48'"},
            odds, avaliacao,
        )

        self.assertEqual("curva_linhas_odd_incoerente", resultado["estado"])
        self.assertEqual(
            "proveniencia_odd_rapida_invalida", resultado["categoria"]
        )
        self.assertEqual(
            "curva_linhas_odd_incoerente",
            resultado["coerencia_curva_odds"]["motivo"],
        )
        self.assertFalse(resultado["persistido"])

    def test_rota_autorizada_converte_odd_silenciosa_sem_promover_calibracao(self):
        self._verificar_rota_integrada(usar_metodo_atual=False)

    def test_metodo_atual_da_geracao_silenciosa_ate_telegram_e_roi_real(self):
        self._verificar_rota_integrada(usar_metodo_atual=True)

    def test_metodo_atual_com_historico_antigo_nao_envia_mesmo_com_odd_alvo(self):
        self._verificar_rota_integrada(usar_metodo_atual=True, historico_antigo=True)

    def test_rota_rapida_respeita_exposicao_aberta_de_outro_mercado(self):
        self._verificar_rota_integrada(usar_metodo_atual=True, exposicao_aberta=True)

    def test_analise_revogada_durante_consulta_odd_nao_vira_entrada(self):
        self._verificar_rota_integrada(usar_metodo_atual=True, revogar_em="consulta")

    def test_analise_revogada_depois_de_materializar_nao_chega_ao_telegram(self):
        self._verificar_rota_integrada(usar_metodo_atual=True, revogar_em="pre_envio")

    def test_leitura_recente_vencida_nao_gasta_chamadas_de_odds(self):
        servico = self.servico()
        item = servico.banco.item
        features = json.loads(item["features_json"])
        features["acompanhamento_metodo_gols"] = {"metodo": VERSAO_HT_00}
        item["features_json"] = json.dumps(features)
        item["snapshot_em"] = (datetime.now() - timedelta(seconds=125)).isoformat()
        servico.api.fixtures_ao_vivo_detalhadas = lambda ids: self.fail("leitura vencida consultou API")
        resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
        self.assertEqual(resumo["consultados"], 0)
        self.assertEqual(resumo["motivos"]["leitura_tecnica_expirada"], 1)

    def _verificar_rota_integrada(self, usar_metodo_atual, exposicao_aberta=False, revogar_em=None, historico_antigo=False):
        caminho = Path.cwd() / f".teste_odd_integrada_{uuid4().hex}.db"
        banco = BancoMonitor(caminho)
        mensagens = []

        def transporte(_url, dados):
            mensagens.append(dados)
            return {"ok": True, "result": {
                "message_id": 901, "date": int(datetime.now().timestamp()),
                "chat": {"id": -100123},
            }}

        try:
            with patch.dict(os.environ, {
                "SINAIS_TESTE_ATIVO": "1",
                "TELEGRAM_BOT_TOKEN": "teste-local-sem-rede",
                "TELEGRAM_CHAT_ID_GOLS": "-100123",
                "TELEGRAM_CHAT_ID_TESTE": "-100123",
                "AVISO_AGUARDAR_ODD_ATIVO": "1",
                "ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS": "0",
                "ACOMPANHAMENTO_ODD_API_RAPIDO_ATIVO": "1",
            }), patch("telegram_alertas.GOL_HT_00_MIN20_GRUPO_ATIVO", True), patch.object(
                AlertasTelegram, "_validar_operacao_oficial", return_value=None,
            ):
                servico = self.servico(placar="0-0")
                del servico._materializar_entrada_acompanhamento_odd_api
                servico.banco = banco
                servico.calibrador = CalibradorBacktest(banco)
                servico.salvar_registro = banco.salvar_registro
                servico.alertas = AlertasTelegram(banco, transporte=transporte)
                servico.api.fixture["fixture"]["status"].update({
                    "elapsed": 26, "short": "1H",
                })
                oferta = self._avaliacao_materializacao("0-0")["oferta"]
                oferta.update({"linha": 0.5, "over": 1.44})
                oferta["origem_mercado"] = origem_mercado_teste(0.5)
                servico.betsapi.buscar_mercados = lambda jogo, mercados: (
                    {"ao_vivo": [{
                        "categoria": "gols", "ofertas": [],
                        "ofertas_ht": [oferta],
                    }]}, {"pareado": True},
                )
                agora = datetime.now().replace(microsecond=0)
                item = self._item_materializacao()
                features = json.loads(item["features_json"])
                features.update({
                    "exploracao_sombra": {"versao": VERSAO_HT_00},
                    "gol_ht_00_min20": {"linhagem_sha256": "teste"},
                    "protecao_conversao_gols": {"ativa": True, "aprovada": True},
                    "protecao_tendencias_packball": {"ativa": True, "aprovada": True},
                })
                snapshot = banco.salvar_registro({
                    "coletado_em": (agora - timedelta(seconds=20)).isoformat(),
                    "url": item["packball_url"], "mandante": item["mandante"],
                    "visitante": item["visitante"], "status": "25'", "placar": "0-0",
                    "qualidade": {"pontuacao": 90, "apto_para_sinal": True},
                    "contexto_api": contexto_com_datas(
                        banco.conexao, contexto_ht() if usar_metodo_atual else {}, agora,
                        antigos=historico_antigo,
                    ),
                    "confirmacao_api": {"fixture_id": 123, "orientacao": "direta"},
                })
                origem_candidato = {
                    "mercado": "gol_ht", "linha": 0.5, "odd": 1.22,
                    "pontuacao_tecnica": 90, "qualidade_dados": 90,
                    "regra_versao": "teste-v1", "status": "rejeitado",
                    "regra_fingerprint": "abc123", "features": features,
                }
                if usar_metodo_atual:
                    origem_candidato = preparar_ht_com_protecoes(servico.alertas, {
                        "mandante": item["mandante"], "visitante": item["visitante"],
                        "status": "25'", "placar": "0-0",
                    })[0]
                    origem_candidato["regra_fingerprint"] = "abc123"
                    self.assertNotIn("exploracao_sombra", origem_candidato["features"])
                origem = banco.salvar_candidatos(snapshot, [origem_candidato])[0]
                servico.alertas.enviar_acompanhamento_odd(origem, origem_candidato, {})
                self.assertEqual(mensagens, [])
                self.assertEqual(len(banco.acompanhamentos_odd_para_rechecagem_api()), 1)
                if exposicao_aberta:
                    anterior = banco.salvar_candidatos(snapshot, [{
                        "mercado": "gol_ft", "linha": 0.5, "odd": 1.50,
                        "regra_versao": "teste-exposicao-ft", "status": "aprovado",
                    }])[0]
                    banco.registrar_entrega_alerta(anterior, "-100123:teste", "entregue",
                        provedor="telegram", provedor_mensagem_id="800")

                def revogar():
                    banco.salvar_registro({
                        "coletado_em": (agora - timedelta(seconds=5)).isoformat(),
                        "url": item["packball_url"], "mandante": item["mandante"],
                        "visitante": item["visitante"], "status": "26'", "placar": "0-0",
                        "_analise_tecnica_acompanhamento_odd": True,
                        "qualidade": {"pontuacao": 90, "apto_para_sinal": True},
                    })
                if revogar_em == "consulta":
                    buscar = servico.betsapi.buscar_mercados
                    def buscar_e_revogar(*args):
                        revogar()
                        return buscar(*args)
                    servico.betsapi.buscar_mercados = buscar_e_revogar
                elif revogar_em == "pre_envio":
                    despachar = servico._despachar_alertas
                    def despachar_e_revogar(*args):
                        revogar()
                        return despachar(*args)
                    servico._despachar_alertas = despachar_e_revogar

                resumo = servico._rechecar_acompanhamentos_odd_api(forcar=True)
                if historico_antigo:
                    self.assertEqual(resumo["enviados"], 0, resumo)
                    self.assertEqual(mensagens, [])
                    auditoria = banco.conexao.execute(
                        "SELECT erro FROM entregas_alertas WHERE canal='gateway:validade_historico' ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    self.assertEqual(json.loads(auditoria[0])["motivo"], "historico_antigo")
                    return
                if revogar_em:
                    self.assertEqual(resumo["enviados"], 0, resumo)
                    self.assertEqual(mensagens, [])
                    if revogar_em == "consulta":
                        self.assertIn("analise_acompanhamento_substituida", resumo["motivos"])
                        self.assertEqual(banco.contar_exploracao_sombra_versao(VERSAO_HT_00), 0)
                    self.assertEqual(banco.acompanhamentos_odd_para_rechecagem_api(), [])
                    return
                if exposicao_aberta:
                    self.assertEqual(resumo["enviados"], 0, resumo)
                    self.assertEqual(mensagens, [])
                    self.assertIn("exposicao_gol_partida_existente", resumo["motivos"])
                    return
                self.assertEqual(resumo["enviados"], 1, resumo)
                self.assertEqual(len(mensagens), 1)
                self.assertIn("1.44", mensagens[0]["text"])
                convertido = banco.entrada_oficial_apos_acompanhamento(origem, "-100123")
                self.assertIsNotNone(convertido)
                self.assertEqual(convertido["odd"], 1.44)
                persistido = banco.conexao.execute(
                    "SELECT * FROM sinais WHERE id=?", (convertido["sinal_id"],),
                ).fetchone()
                self.assertEqual(persistido["status"], "simulacao")
                self.assertIsNone(persistido["probabilidade_calibrada"])
                revalidacao = json.loads(persistido["features_json"])["acompanhamento_odd_rapido"]
                self.assertEqual(revalidacao["rota_envio"], "politica_envio_grupo_ativa")
                self.assertNotIn("calibracao_ativa", revalidacao["criterios_revalidados"])
                features_persistidas = json.loads(persistido["features_json"])
                self.assertEqual(
                    features_persistidas["cotacao_entrada_clv_estado"],
                    "congelada_v1",
                )
                self.assertEqual(
                    features_persistidas["cotacao_entrada_clv"]["over"],
                    1.44,
                )
                self.assertEqual(
                    features_persistidas["cotacao_entrada_clv"]["under"],
                    2.8,
                )
                self.assertEqual(
                    features_persistidas["cotacao_entrada_clv"]["schema"],
                    "cotacao-entrada-clv-v2",
                )
                self.assertEqual(
                    features_persistidas["cotacao_entrada_clv"][
                        "origem_mercado"
                    ]["identificador"],
                    revalidacao["origem_mercado_odd"]["identificador"],
                )
                self.assertIn(
                    "contrato_de_mercado_completo",
                    revalidacao["criterios_revalidados"],
                )
                if usar_metodo_atual:
                    self.assertIn("mesmo_metodo_recalculado_na_odd_e_minuto_atuais",
                                  revalidacao["criterios_revalidados"])
                    self.assertEqual(banco.contar_exploracao_sombra_versao(VERSAO_HT_00), 1)
                self.assertEqual(banco.acompanhamentos_odd_para_rechecagem_api(), [])
                servico._rechecar_acompanhamentos_odd_api(forcar=True)
                self.assertEqual(len(mensagens), 1)

                # Mesmo um green hipotético não pode entrar no ROI enviado.
                with banco.conexao:
                    for sinal, retorno in ((origem, 0.22), (convertido["sinal_id"], 0.44)):
                        banco.conexao.execute(
                            "INSERT INTO resultados_sinais (sinal_id, encerrado_em, resultado, retorno_unidades) VALUES (?, ?, 'green', ?)",
                            (sinal, agora.isoformat(), retorno),
                        )
                desempenho = resumir_desempenho_operacional(banco.conexao, "2026-01-01")
                self.assertEqual(desempenho["categorias"]["validacao_enviada"]["roi"], 0.44)
                self.assertEqual(banco.total_alertas_entregues_hoje(), 0)
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                caminho.with_name(caminho.name + sufixo).unlink(missing_ok=True)

    def test_rota_rapida_nao_libera_metodo_desativado(self):
        servico = ServicoMonitor.__new__(ServicoMonitor)
        servico.calibrador = CalibradorFalso(None)
        servico.alertas = AlertasTelegram.__new__(AlertasTelegram)
        servico.alertas.modo_teste = True
        item = self._item_materializacao()
        features = json.loads(item["features_json"])
        features.update({
            "exploracao_sombra": {"versao": VERSAO_HT_00},
            "gol_ht_00_min20": {"linhagem_sha256": "teste"},
        })
        item.update({"mercado": "gol_ht", "features_json": json.dumps(features)})
        servico.salvar_registro = lambda registro: self.fail("método desativado persistido")
        with patch("telegram_alertas.GOL_HT_00_MIN20_GRUPO_ATIVO", False):
            resultado = servico._materializar_entrada_acompanhamento_odd_api(
                item, {}, {"placar": "0-0", "minuto": 26, "status": "26'"},
                {}, self._avaliacao_materializacao("0-0"),
            )
        self.assertEqual(resultado["estado"], "exploracao_sombra_fora_allowlist_simulacao_grupo")
        self.assertFalse(resultado["persistido"])

    def test_calibracao_abaixo_do_minimo_nao_persiste(self):
        servico = ServicoMonitor.__new__(ServicoMonitor)
        servico.calibrador = CalibradorFalso(0.74)
        servico.salvar_registro = lambda registro: self.fail(
            "nao deveria persistir com confianca insuficiente"
        )
        resultado = servico._materializar_entrada_acompanhamento_odd_api(
            self._item_materializacao(),
            {},
            {"placar": "0-2", "minuto": 48, "status": "48'"},
            {},
            self._avaliacao_materializacao(),
        )
        self.assertEqual(
            resultado["estado"], "confianca_calibrada_insuficiente"
        )
        self.assertFalse(resultado["persistido"])

    def test_avaliacao_prospectiva_e_observavel_sem_aplicar_sinais(self):
        servico = self.servico()
        servico.pasta = Path.cwd()
        servico._ultima_avaliacao_acompanhamento_odd = 0.0
        avaliacao = {
            "versao": "avaliacao-aguardar-odd-prospectiva-v6",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            "estado_execucao": "concluida",
            "estado": "amostra_em_formacao",
            "aplicacao_sinais": False,
            "avisos": 10,
            "detalhes": [{"sinal_id": 1}],
        }
        with (
            patch(
                "servico_monitor.avaliar_estrategia_acompanhamento_odd",
                return_value=avaliacao,
            ),
            patch("servico_monitor.gravar_json_atomico") as gravar,
        ):
            resultado = servico._avaliar_acompanhamento_odd_prospectivo(
                forcar=True
            )
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertNotIn("detalhes", resultado)
        self.assertEqual(2, gravar.call_count)
        self.assertEqual(
            servico.observabilidade.registros[-1]["etapa"],
            "avaliacao_estrategia_aguardar_odd",
        )

    def test_falha_da_avaliacao_prospectiva_fica_isolada(self):
        servico = self.servico()
        servico.pasta = Path.cwd()
        servico._ultima_avaliacao_acompanhamento_odd = 0.0
        with (
            patch(
                "servico_monitor.avaliar_estrategia_acompanhamento_odd",
                side_effect=RuntimeError("falha de leitura"),
            ),
            patch("servico_monitor.gravar_json_atomico") as gravar,
        ):
            resultado = servico._avaliar_acompanhamento_odd_prospectivo(
                forcar=True
            )
        self.assertEqual(resultado["estado"], "falha_avaliacao")
        self.assertEqual(resultado["estado_execucao"], "falha")
        self.assertEqual(2, gravar.call_count)
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_avaliacao_prioridade_ligas_e_persistida_sem_aplicar(self):
        servico = self.servico()
        servico.pasta = Path.cwd()
        servico._ultima_avaliacao_prioridade_ligas_gols = 0.0
        avaliacao = {
            "versao": "avaliacao-prioridade-ligas-gols-prospectiva-v3",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            "estado_execucao": "concluida",
            "estado": "coorte_prospectiva_em_formacao",
            "aplicacao_sinais": False,
            "altera_prioridade": False,
            "por_grupo": {},
        }
        with patch(
            "servico_monitor.avaliar_prioridade_ligas_gols",
            return_value=avaliacao,
        ), patch("servico_monitor.gravar_json_atomico") as gravar:
            resultado = (
                servico._avaliar_prioridade_ligas_gols_prospectiva(
                    forcar=True
                )
            )

        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["altera_prioridade"])
        self.assertIn("atualizado_em", resultado)
        self.assertEqual(2, gravar.call_count)
        self.assertEqual(
            servico.observabilidade.registros[-1]["etapa"],
            "avaliacao_prioridade_ligas_gols",
        )

    @classmethod
    def _item_materializacao(cls):
        item = cls.item()
        item.update({
            "pontuacao_tecnica": 90.0,
            "probabilidade_calibrada": None,
            "regra_versao": "teste-v1",
            "regra_fingerprint": "abc123",
            "motivos_json": "[]",
            "qualidade_dados": 90.0,
        })
        return item

    @staticmethod
    def _avaliacao_materializacao(placar="0-2"):
        return {
            "idade_tecnica_segundos": 10.0,
            "oferta": {
                "odd": 1.40,
                "odd_oposta": 2.80,
                "odd_par_sincronizado": True,
                "linha": 2.5,
                "over": 1.40,
                "under": 2.80,
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "coletado_em": datetime.now().isoformat(),
                "idade_segundos": 0.0,
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": {
                    "schema": "identidade-evento-odd-v1",
                    "confirmada": True,
                    "fonte": "betsapi",
                    "evento_externo_id": "bets-123",
                    "orientacao": "direta",
                    "similaridade": 0.95,
                    "mandante_normalizado": "Al Tadhamon",
                    "visitante_normalizado": "Al Salmiyah",
                    "placar_normalizado": placar,
                    "metodo": "teste",
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
