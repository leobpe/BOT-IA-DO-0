import io
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from the_odds_api import TheOddsAPI


class Resposta:
    def __init__(self, dados, headers=None):
        self._dados = json.dumps(dados).encode()
        self.headers = headers or {
            "x-requests-used": "4",
            "x-requests-remaining": "19996",
            "x-requests-last": "1",
        }

    def read(self, limite=-1):
        return self._dados


class TestTheOddsAPI(unittest.TestCase):
    def setUp(self):
        self.estado = Path(f".teste_the_odds_api_{id(self)}.json")
        self.estado_backup = self.estado.with_suffix(
            self.estado.suffix + ".bak"
        )
        self.estado.unlink(missing_ok=True)
        self.estado_backup.unlink(missing_ok=True)
        self.addCleanup(self.estado.unlink, missing_ok=True)
        self.addCleanup(self.estado_backup.unlink, missing_ok=True)
        self.env = patch.dict(os.environ, {
            "THE_ODDS_API_KEY": "segredo",
            "THE_ODDS_API_ATIVA": "1",
            "THE_ODDS_API_LIMITE_DIARIO": "600",
            "THE_ODDS_API_RESERVA_MENSAL": "2000",
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_pareia_e_normaliza_gols_ft_com_proveniencia(self):
        agora = datetime(
            2026, 8, 24, 17, 27, tzinfo=timezone.utc
        ).timestamp()
        esportes = [{
            "key": "soccer_brazil_campeonato", "group": "Soccer - Brazil",
            "title": "Brazil Serie A", "active": True,
        }, {
            "key": "soccer_saudi_arabia_pro_league", "group": "Soccer",
            "title": "Saudi Arabia Pro League", "active": True,
        }]
        eventos = [{
            "id": "evento1", "home_team": "Palmeiras",
            "away_team": "Santos", "commence_time": "2026-08-24T17:00:00Z",
        }]
        odds = {
            "bookmakers": [{
                "key": "pinnacle", "markets": [{
                    "key": "alternate_totals",
                    "last_update": "2026-08-24T17:25:50Z",
                    "outcomes": [
                        {"name": "Over", "point": 2.5, "price": 1.72},
                        {"name": "Under", "point": 2.5, "price": 2.10},
                    ],
                }],
            }],
        }
        respostas = iter([Resposta(esportes), Resposta(eventos), Resposta(odds)])
        api = TheOddsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: agora,
            arquivo_estado=self.estado,
        )
        saida, diag = api.buscar_mercados({
            "mandante": "Palmeiras FC", "visitante": "Santos FC",
            "liga": "Serie A", "pais": "Brazil", "placar": "1-0",
        }, {"gol_ft"})
        self.assertTrue(diag["pareado"])
        oferta = saida["ao_vivo"][0]["ofertas"][0]
        self.assertEqual(oferta["linha"], 2.5)
        self.assertEqual(oferta["over"], 1.72)
        self.assertEqual(oferta["fonte"], "the_odds_api")
        self.assertEqual(oferta["bookmaker"], "pinnacle")
        self.assertEqual(diag["orientacao"], "direta")
        self.assertEqual(
            oferta["identidade_evento"]["evento_externo_id"], "evento1"
        )
        self.assertEqual(
            oferta["identidade_evento"]["placar_normalizado"], "1-0"
        )
        self.assertEqual(
            oferta["origem_mercado"]["schema"], "origem-mercado-odd-v1"
        )
        self.assertEqual(
            oferta["origem_mercado"]["lados"], ["over", "under"]
        )

    def test_combina_ft_e_ht_em_uma_chamada_com_custo_real(self):
        agora = datetime(
            2026, 8, 24, 17, 27, tzinfo=timezone.utc
        ).timestamp()
        esportes = [{
            "key": "soccer_brazil_campeonato", "group": "Soccer - Brazil",
            "title": "Brazil Serie A", "active": True,
        }]
        eventos = [{
            "id": "evento1", "home_team": "Palmeiras",
            "away_team": "Santos", "commence_time": "2026-08-24T17:00:00Z",
        }]
        odds = {
            "bookmakers": [{
                "key": "pinnacle", "markets": [{
                    "key": "alternate_totals",
                    "last_update": "2026-08-24T17:25:50Z",
                    "outcomes": [
                        {"name": "Over", "point": 2.5, "price": 1.72},
                        {"name": "Under", "point": 2.5, "price": 2.10},
                    ],
                }, {
                    "key": "alternate_totals_h1",
                    "last_update": "2026-08-24T17:25:50Z",
                    "outcomes": [
                        {"name": "Over", "point": 0.5, "price": 1.62},
                        {"name": "Under", "point": 0.5, "price": 2.20},
                    ],
                }],
            }],
        }
        sem_custo = {
            "x-requests-used": "0", "x-requests-remaining": "20000",
            "x-requests-last": "0",
        }
        custo_dois = {
            "x-requests-used": "2", "x-requests-remaining": "19998",
            "x-requests-last": "2",
        }
        respostas = iter([
            Resposta(esportes, sem_custo), Resposta(eventos, sem_custo),
            Resposta(odds, custo_dois),
        ])
        chamadas = []

        def abrir(requisicao, *args, **kwargs):
            chamadas.append(requisicao.full_url)
            return next(respostas)

        api = TheOddsAPI(
            ".", abridor=abrir, relogio=lambda: agora,
            arquivo_estado=self.estado,
        )
        saida, diag = api.buscar_mercados({
            "mandante": "Palmeiras FC", "visitante": "Santos FC",
            "liga": "Serie A", "pais": "Brazil",
        }, {"gol_ht", "gol_ft"})

        self.assertEqual(3, len(chamadas))
        parametros = parse_qs(urlparse(chamadas[-1]).query)
        self.assertEqual(
            ["alternate_totals,alternate_totals_h1"],
            parametros["markets"],
        )
        self.assertEqual(
            ["alternate_totals", "alternate_totals_h1"],
            diag["consultados"],
        )
        self.assertTrue(diag["consulta_combinada"])
        self.assertEqual(2, diag["custo_estimado_creditos"])
        self.assertEqual(2, len(saida["ao_vivo"]))
        self.assertEqual(2.5, saida["ao_vivo"][0]["ofertas"][0]["linha"])
        self.assertEqual(0.5, saida["ao_vivo"][1]["ofertas_ht"][0]["linha"])
        self.assertEqual(2, api.diagnostico()["consumo_dia"])

    def test_nao_pareia_partida_ambigua(self):
        agora = datetime(
            2026, 8, 24, 17, 27, tzinfo=timezone.utc
        ).timestamp()
        respostas = iter([
            Resposta([{
                "key": "soccer_brazil_campeonato", "group": "Soccer - Brazil",
                "title": "Brazil Serie A", "active": True,
            }]),
            Resposta([
                {"id": "1", "home_team": "ABC", "away_team": "Santos",
                 "commence_time": "2026-08-24T17:00:00Z"},
                {"id": "2", "home_team": "ABC FC", "away_team": "Santos FC",
                 "commence_time": "2026-08-24T17:01:00Z"},
            ]),
        ])
        api = TheOddsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: agora,
            arquivo_estado=self.estado,
        )
        saida, diag = api.buscar_mercados({
            "mandante": "ABC", "visitante": "Santos",
            "liga": "Serie A", "pais": "Brazil",
        }, {"gol_ft"})
        self.assertFalse(diag["pareado"])
        self.assertEqual(diag["motivo"], "evento_nao_encontrado")
        self.assertEqual(saida["ao_vivo"], [])

    def test_pais_no_titulo_recupera_liga_generica(self):
        agora = datetime(
            2026, 8, 24, 22, 0, tzinfo=timezone.utc
        ).timestamp()
        esportes = [{
            "key": "soccer_argentina_primera_division",
            "group": "Soccer", "title": "Argentina Primera Division",
            "active": True,
        }, {
            "key": "soccer_mexico_ligamx",
            "group": "Soccer", "title": "Mexico Liga MX",
            "active": True,
        }]
        eventos = [{
            "id": "arg1", "home_team": "Lanus",
            "away_team": "Argentinos Juniors",
            "commence_time": "2026-08-24T21:00:00Z",
        }]
        odds = {"bookmakers": []}
        respostas = iter([Resposta(esportes), Resposta(eventos), Resposta(odds)])
        api = TheOddsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: agora,
            arquivo_estado=self.estado,
        )
        _, diag = api.buscar_mercados({
            "mandante": "Lanus", "visitante": "Argentinos Juniors",
            "liga": "Liga Profesional de Futbol", "pais": "Argentina",
        }, {"gol_ft"})
        self.assertTrue(diag["pareado"])
        self.assertEqual(diag["similaridade"], 1.0)
        self.assertEqual(diag["consultados"], ["alternate_totals"])
        self.assertEqual(diag["motivo"], "mercado_sem_oferta_fresca")

    def test_distingue_competicao_nao_coberta_sem_consultar_eventos(self):
        agora = datetime(
            2026, 8, 24, 22, 0, tzinfo=timezone.utc
        ).timestamp()
        respostas = iter([Resposta([{
            "key": "soccer_usa_mls", "group": "Soccer",
            "title": "MLS", "active": True,
        }])])
        api = TheOddsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: agora,
            arquivo_estado=self.estado,
        )
        saida, diag = api.buscar_mercados({
            "mandante": "Alianza", "visitante": "Tauro",
            "liga": "LPF", "pais": "Panama",
        }, {"gol_ft"})
        self.assertEqual(saida["ao_vivo"], [])
        self.assertEqual(diag["motivo"], "competicao_nao_coberta")
        self.assertEqual(diag["esportes_candidatos"], [])

    def test_preselecao_cobertura_nao_consulta_eventos_nem_gasta_reserva(self):
        agora = datetime(
            2026, 8, 24, 22, 0, tzinfo=timezone.utc
        ).timestamp()
        chamadas = []
        esportes = [{
            "key": "soccer_brazil_campeonato", "group": "Soccer - Brazil",
            "title": "Brazil Serie A", "active": True,
        }]

        def abrir(requisicao, *args, **kwargs):
            chamadas.append(requisicao.full_url)
            return Resposta(esportes)

        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
        }):
            api = TheOddsAPI(
                ".", abridor=abrir, relogio=lambda: agora,
                arquivo_estado=self.estado,
            )
            coberta = api.diagnosticar_cobertura_competicao({
                "liga": "Serie A", "pais": "Brazil",
            })
            ausente = api.diagnosticar_cobertura_competicao({
                "liga": "Premier League", "pais": "Bahrain",
            })

        self.assertTrue(coberta["coberta"])
        self.assertEqual(
            ["soccer_brazil_campeonato"],
            coberta["esportes_candidatos"],
        )
        self.assertFalse(ausente["coberta"])
        self.assertEqual(
            "competicao_nao_coberta_pais_incompativel",
            ausente["motivo"],
        )
        self.assertIn(
            "soccer_brazil_campeonato",
            ausente["candidatos_descartados_pais"],
        )
        self.assertEqual(1, len(chamadas))
        self.assertIn("/sports/", chamadas[0])
        self.assertFalse(coberta["consulta_eventos"])
        self.assertFalse(coberta["consulta_odds"])
        self.assertFalse(coberta["reserva_consumida"])
        self.assertEqual(
            0,
            api.diagnostico()["amostragem_referencia"]["uso_dia"],
        )

    def test_preselecao_evento_pareia_sem_consultar_odds_ou_reservar(self):
        agora = datetime(
            2026, 8, 24, 17, 27, tzinfo=timezone.utc
        ).timestamp()
        esportes = [{
            "key": "soccer_brazil_campeonato", "group": "Soccer - Brazil",
            "title": "Brazil Serie A", "active": True,
        }]
        eventos = [{
            "id": "evento1", "home_team": "Palmeiras",
            "away_team": "Santos", "commence_time": "2026-08-24T17:00:00Z",
        }]
        chamadas = []
        respostas = iter((esportes, eventos))

        def abrir(requisicao, *args, **kwargs):
            chamadas.append(requisicao.full_url)
            return Resposta(next(respostas), headers={
                "x-requests-used": "4",
                "x-requests-remaining": "19996",
                "x-requests-last": "0",
            })

        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
        }):
            api = TheOddsAPI(
                ".", abridor=abrir, relogio=lambda: agora,
                arquivo_estado=self.estado,
            )
            diagnostico = api.diagnosticar_cobertura_evento({
                "mandante": "Palmeiras", "visitante": "Santos",
                "liga": "Serie A", "pais": "Brazil",
            })

        self.assertTrue(diagnostico["pareado"])
        self.assertEqual("evento1", diagnostico["evento_externo_id"])
        self.assertEqual(1.0, diagnostico["similaridade"])
        self.assertTrue(diagnostico["consulta_eventos"])
        self.assertFalse(diagnostico["consulta_odds"])
        self.assertFalse(diagnostico["reserva_consumida"])
        self.assertEqual(0, diagnostico["custo_estimado"])
        self.assertEqual(2, len(chamadas))
        self.assertTrue(any("/events" in url for url in chamadas))
        self.assertFalse(any("/odds" in url for url in chamadas))
        self.assertEqual(
            0,
            api.diagnostico()["amostragem_referencia"]["uso_dia"],
        )

    def test_odd_antiga_nao_e_anexada(self):
        api = TheOddsAPI(
            ".", abridor=lambda *a, **k: None,
            arquivo_estado=self.estado,
        )
        api.relogio = lambda: datetime(
            2026, 8, 24, 17, 27, tzinfo=timezone.utc
        ).timestamp()
        resposta = {"bookmakers": [{"key": "pinnacle", "markets": [{
            "key": "alternate_totals", "last_update": "2026-08-24T17:00:00Z",
            "outcomes": [
                {"name": "Over", "point": 2.5, "price": 1.8},
                {"name": "Under", "point": 2.5, "price": 2.0},
            ],
        }]}]}
        self.assertEqual(api._ofertas(resposta, "alternate_totals"), [])

    def test_desligamento_e_imediato(self):
        with patch.dict(os.environ, {"THE_ODDS_API_ATIVA": "0"}):
            api = TheOddsAPI(".", arquivo_estado=self.estado)
        saida, diag = api.buscar_mercados({}, {"gol_ft"})
        self.assertFalse(diag["ativa"])
        self.assertEqual(saida["ao_vivo"], [])

    def test_amostragem_referencia_tem_cooldown_e_limite_persistentes(self):
        relogio = [datetime(
            2026, 9, 11, 1, 0, tzinfo=timezone.utc
        ).timestamp()]
        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_LIMITE_DIARIO": "2",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_INTERVALO_SEGUNDOS": "600",
        }):
            api = TheOddsAPI(
                ".", relogio=lambda: relogio[0],
                arquivo_estado=self.estado,
            )
            primeira = api.reservar_amostragem_referencia("jogo-1|gol_ft")
            repetida = api.reservar_amostragem_referencia("jogo-1|gol_ft")
            relogio[0] += 601
            segunda = api.reservar_amostragem_referencia("jogo-1|gol_ft")
            excedente = api.reservar_amostragem_referencia("jogo-2|gol_ft")
            reiniciada = TheOddsAPI(
                ".", relogio=lambda: relogio[0],
                arquivo_estado=self.estado,
            )

        self.assertTrue(primeira["autorizada"])
        self.assertFalse(repetida["autorizada"])
        self.assertEqual("cooldown_amostragem", repetida["motivo"])
        self.assertTrue(segunda["autorizada"])
        self.assertFalse(excedente["autorizada"])
        self.assertEqual("limite_amostragem_diario", excedente["motivo"])
        self.assertEqual(
            2,
            reiniciada.diagnostico()["amostragem_referencia"]["uso_dia"],
        )
        self.assertFalse(primeira["aplicacao_sinais"])
        self.assertFalse(primeira["telegram"])

    def test_amostragem_preserva_diversidade_por_jogo_no_dia(self):
        relogio = [datetime(
            2026, 9, 11, 1, 0, tzinfo=timezone.utc
        ).timestamp()]
        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_LIMITE_DIARIO": "5",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_INTERVALO_SEGUNDOS": "600",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_MAX_JOGO_DIA": "2",
        }):
            api = TheOddsAPI(
                ".", relogio=lambda: relogio[0],
                arquivo_estado=self.estado,
            )
            primeira = api.reservar_amostragem_referencia("jogo-1|gol_ft")
            relogio[0] += 601
            confirmacao = api.reservar_amostragem_referencia(
                "jogo-1|gol_ft"
            )
            relogio[0] += 601
            repeticao_excedente = api.reservar_amostragem_referencia(
                "jogo-1|gol_ft"
            )
            novo_jogo = api.reservar_amostragem_referencia(
                "jogo-2|gol_ft"
            )
            diagnostico = api.diagnostico()["amostragem_referencia"]
            reiniciada = TheOddsAPI(
                ".", relogio=lambda: relogio[0],
                arquivo_estado=self.estado,
            )
            ainda_limitada = reiniciada.reservar_amostragem_referencia(
                "jogo-1|gol_ft"
            )
            relogio[0] += 86400
            novo_dia = reiniciada.reservar_amostragem_referencia(
                "jogo-1|gol_ft"
            )
            diagnostico_novo_dia = reiniciada.diagnostico()[
                "amostragem_referencia"
            ]

        self.assertTrue(primeira["autorizada"])
        self.assertTrue(confirmacao["autorizada"])
        self.assertFalse(repeticao_excedente["autorizada"])
        self.assertEqual(
            "limite_amostragem_jogo_dia",
            repeticao_excedente["motivo"],
        )
        self.assertTrue(novo_jogo["autorizada"])
        self.assertEqual(3, diagnostico["uso_dia"])
        self.assertEqual(2, diagnostico["jogos_distintos_dia"])
        self.assertEqual(2, diagnostico["maior_uso_jogo_dia"])
        self.assertEqual(2, diagnostico["maximo_por_jogo_dia"])
        self.assertFalse(ainda_limitada["autorizada"])
        self.assertEqual(
            "limite_amostragem_jogo_dia", ainda_limitada["motivo"]
        )
        self.assertTrue(novo_dia["autorizada"])
        self.assertEqual(1, diagnostico_novo_dia["uso_dia"])
        self.assertEqual(1, diagnostico_novo_dia["jogos_distintos_dia"])

    def test_recuperacao_coorte_libera_uma_unica_consulta_extra(self):
        relogio = [datetime(
            2026, 9, 11, 1, 0, tzinfo=timezone.utc
        ).timestamp()]
        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_LIMITE_DIARIO": "10",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_INTERVALO_SEGUNDOS": "60",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_MAX_JOGO_DIA": "2",
        }):
            api = TheOddsAPI(
                ".", relogio=lambda: relogio[0],
                arquivo_estado=self.estado,
            )
            primeira = api.reservar_amostragem_referencia(
                "jogo-1|gol_ft"
            )
            relogio[0] += 61
            segunda = api.reservar_amostragem_referencia(
                "jogo-1|gol_ft"
            )
            relogio[0] += 61
            bloqueada = api.reservar_amostragem_referencia(
                "jogo-1|gol_ft"
            )
            recuperada = api.reservar_amostragem_referencia(
                "jogo-1|gol_ft",
                permitir_confirmacao=False,
                permitir_recuperacao_coorte=True,
            )
            relogio[0] += 61
            repeticao = api.reservar_amostragem_referencia(
                "jogo-1|gol_ft",
                permitir_recuperacao_coorte=True,
            )

        self.assertTrue(primeira["autorizada"])
        self.assertTrue(segunda["autorizada"])
        self.assertFalse(bloqueada["autorizada"])
        self.assertEqual("limite_amostragem_jogo_dia", bloqueada["motivo"])
        self.assertTrue(recuperada["autorizada"])
        self.assertTrue(recuperada["recuperacao_coorte_aplicada"])
        self.assertEqual(
            "recuperacao_coorte_resultado", recuperada["tipo_amostra"]
        )
        self.assertEqual(3, recuperada["uso_jogo_dia"])
        self.assertFalse(repeticao["autorizada"])
        self.assertEqual("limite_amostragem_jogo_dia", repeticao["motivo"])
        self.assertEqual(3, repeticao["limite_efetivo_jogo_dia"])

    def test_reserva_de_ciclo_prioriza_partida_nova(self):
        relogio = [datetime(
            2026, 9, 11, 1, 0, tzinfo=timezone.utc
        ).timestamp()]
        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_LIMITE_DIARIO": "5",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_INTERVALO_SEGUNDOS": "600",
        }):
            api = TheOddsAPI(
                ".", relogio=lambda: relogio[0],
                arquivo_estado=self.estado,
            )
            primeira = api.reservar_amostragem_referencia("jogo-1|gol_ft")
            relogio[0] += 601
            repetida_bloqueada = api.reservar_amostragem_referencia(
                "jogo-1|gol_ft", permitir_confirmacao=False
            )
            nova = api.reservar_amostragem_referencia(
                "jogo-2|gol_ft", permitir_confirmacao=False
            )

        self.assertEqual("nova_partida", primeira["tipo_amostra"])
        self.assertFalse(repetida_bloqueada["autorizada"])
        self.assertEqual(
            "reserva_diversidade_ciclo", repetida_bloqueada["motivo"]
        )
        self.assertEqual(
            "confirmacao_temporal", repetida_bloqueada["tipo_amostra"]
        )
        self.assertTrue(nova["autorizada"])
        self.assertEqual("nova_partida", nova["tipo_amostra"])
        self.assertEqual(2, api.diagnostico()["amostragem_referencia"][
            "jogos_distintos_dia"
        ])

    def test_circuito_persiste_no_reinicio_e_recupera_automaticamente(self):
        relogio = [datetime(
            2026, 9, 11, 2, 0, tzinfo=timezone.utc
        ).timestamp()]

        def falhar(*args, **kwargs):
            raise URLError("fonte indisponível")

        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
        }):
            api = TheOddsAPI(
                ".", abridor=falhar, relogio=lambda: relogio[0],
                arquivo_estado=self.estado,
            )
            for _ in range(3):
                self.assertIsNone(api._requisitar("sports", {}))
            reiniciada = TheOddsAPI(
                ".", abridor=lambda *a, **k: Resposta([]),
                relogio=lambda: relogio[0], arquivo_estado=self.estado,
            )
            bloqueada = reiniciada.reservar_amostragem_referencia(
                "jogo-1|gol_ft"
            )
            relogio[0] += 121
            self.assertEqual([], reiniciada._requisitar("sports", {}))
            recuperada = TheOddsAPI(
                ".", relogio=lambda: relogio[0],
                arquivo_estado=self.estado,
            )

        self.assertTrue(api.diagnostico()["circuito"]["persistente"])
        self.assertTrue(reiniciada.diagnostico()["circuito"][
            "recuperacao_automatica"
        ])
        self.assertFalse(bloqueada["autorizada"])
        self.assertEqual("circuito_aberto", bloqueada["motivo"])
        self.assertFalse(recuperada.diagnostico()["circuito_aberto"])
        self.assertEqual(
            0,
            recuperada.diagnostico()["circuito"]["falhas_consecutivas"],
        )

    def test_estado_corrompido_recupera_backup_sem_zerar_protecao(self):
        agora = datetime(
            2026, 9, 11, 2, 0, tzinfo=timezone.utc
        ).timestamp()
        self.estado.write_text("{invalido", encoding="utf-8")
        self.estado_backup.write_text(json.dumps({
            "versao": 1,
            "dias": {"2026-09-11": 12},
            "provedor": {"restante": 19700, "usados": 300},
            "circuito": {
                "falhas_consecutivas": 3,
                "bloqueado_ate": agora + 120,
                "motivo": "URLError",
            },
        }), encoding="utf-8")

        api = TheOddsAPI(
            ".", relogio=lambda: agora, arquivo_estado=self.estado
        )
        diagnostico = api.diagnostico()

        self.assertTrue(diagnostico["controle_estado"]["saudavel"])
        self.assertEqual("backup", diagnostico["controle_estado"]["origem"])
        self.assertTrue(diagnostico["controle_estado"]["recuperado"])
        self.assertTrue(diagnostico["controle_estado"]["reparado"])
        self.assertEqual(12, diagnostico["consumo_dia"])
        self.assertTrue(diagnostico["circuito_aberto"])
        self.assertEqual(
            json.loads(self.estado_backup.read_text(encoding="utf-8")),
            json.loads(self.estado.read_text(encoding="utf-8")),
        )

    def test_estado_escolhe_revisao_mais_nova_e_repara_par(self):
        principal = {
            "versao": 1,
            "revisao": 1,
            "dias": {"2026-09-11": 1},
            "provedor": {},
        }
        backup = {
            "versao": 1,
            "revisao": 2,
            "dias": {"2026-09-11": 2},
            "provedor": {},
        }
        self.estado.write_text(json.dumps(principal), encoding="utf-8")
        self.estado_backup.write_text(json.dumps(backup), encoding="utf-8")
        agora = datetime(
            2026, 9, 11, 2, 0, tzinfo=timezone.utc
        ).timestamp()

        api = TheOddsAPI(
            ".", relogio=lambda: agora, arquivo_estado=self.estado
        )
        diagnostico = api.diagnostico()["controle_estado"]

        self.assertEqual("backup", diagnostico["origem"])
        self.assertTrue(diagnostico["recuperado"])
        self.assertTrue(diagnostico["reparado"])
        self.assertEqual(2, diagnostico["revisao"])
        self.assertEqual(2, api.diagnostico()["consumo_dia"])
        self.assertEqual(
            json.loads(self.estado_backup.read_text(encoding="utf-8")),
            json.loads(self.estado.read_text(encoding="utf-8")),
        )

    def test_estado_legado_migra_revisao_sem_consumir_cota(self):
        legado = {
            "versao": 1,
            "dias": {"2026-09-11": 12},
            "provedor": {"restante": 19700, "usados": 300},
            "amostragem_referencia": {
                "dia": "2026-09-11",
                "reservas": 4,
                "ultimas": {"jogo-1|gol_ft": 1.0},
                "contagens": {"jogo-1|gol_ft": 1},
            },
        }
        self.estado.write_text(json.dumps(legado), encoding="utf-8")
        agora = datetime(
            2026, 9, 11, 2, 0, tzinfo=timezone.utc
        ).timestamp()

        api = TheOddsAPI(
            ".", relogio=lambda: agora, arquivo_estado=self.estado
        )
        principal = json.loads(self.estado.read_text(encoding="utf-8"))
        backup = json.loads(
            self.estado_backup.read_text(encoding="utf-8")
        )
        diagnostico = api.diagnostico()

        self.assertEqual(1, principal["revisao"])
        self.assertEqual(principal, backup)
        self.assertEqual(12, diagnostico["consumo_dia"])
        self.assertEqual(4, diagnostico["amostragem_referencia"]["uso_dia"])
        self.assertTrue(diagnostico["controle_estado"]["reparado"])
        self.assertTrue(diagnostico["controle_estado"]["saudavel"])

    def test_falha_ao_persistir_reserva_bloqueia_consulta(self):
        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
        }):
            api = TheOddsAPI(".", arquivo_estado=self.estado)
            with patch(
                "the_odds_api.gravar_json_atomico",
                side_effect=OSError("disco indisponível"),
            ):
                reserva = api.reservar_amostragem_referencia(
                    "jogo-1|gol_ft"
                )

        self.assertFalse(reserva["autorizada"])
        self.assertEqual("falha_persistencia_reserva", reserva["motivo"])
        self.assertFalse(api.diagnostico()["controle_estado"]["saudavel"])

    def test_dois_estados_corrompidos_bloqueiam_chamadas(self):
        self.estado.write_text("{invalido", encoding="utf-8")
        self.estado_backup.write_text("[]", encoding="utf-8")
        chamadas = []
        with patch.dict(os.environ, {
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
        }):
            api = TheOddsAPI(
                ".", abridor=lambda *a, **k: chamadas.append(1),
                arquivo_estado=self.estado,
            )

        reserva = api.reservar_amostragem_referencia("jogo|gol_ft")
        resposta = api._requisitar("sports", {})
        diagnostico = api.diagnostico()

        self.assertFalse(diagnostico["controle_estado"]["saudavel"])
        self.assertTrue(diagnostico["controle_estado"]["fail_closed"])
        self.assertEqual("corrompido", diagnostico[
            "controle_estado"
        ]["origem"])
        self.assertFalse(reserva["autorizada"])
        self.assertEqual("controle_estado_invalido", reserva["motivo"])
        self.assertIsNone(resposta)
        self.assertEqual([], chamadas)


if __name__ == "__main__":
    unittest.main()
