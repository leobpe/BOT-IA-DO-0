import unittest
from unittest.mock import patch

from telegram_alertas import motivo_suspensao_simulacao
from tendencias_packball_ligas import (
    _cabecalhos_reutilizaveis,
    _descobrir_liga_url_pagina,
    _ler_times_dom_periodo,
    _ler_times_api,
    _rotulo_estatistica_over_gols,
    _url_times_liga,
    aplicar_protecao_tendencias_packball,
    avaliar_tendencia_packball,
    coletar_tendencias_packball_liga,
    periodo_atual,
)


def _time(nome, eficiencia, over_05, over_15=0.30, over_25=0.10):
    return {
        "time": nome,
        "time_normalizado": nome.casefold(),
        "eficiencia": eficiencia,
        "jogos": 20,
        "over_0_5": over_05,
        "over_1_5": over_15,
        "over_2_5": over_25,
    }


def _contexto(casa, fora, periodo="2t"):
    return {
        "fonte": "packball_ligas_times",
        "periodo": periodo,
        "times": [casa, fora],
        "cache": False,
    }


def _candidato(mercado="gol_ft", linha=0.5, status="aprovado"):
    return {
        "mercado": mercado,
        "linha": linha,
        "status": status,
        "features": {},
        "bloqueios": [],
        "motivos": [],
    }


def _candidato_com_historico_proprio(
    mercado="gol_ft", linha=0.5, versao=None
):
    item = _candidato(
        mercado=mercado, linha=linha, status="simulacao"
    )
    versao = versao or "gol-ft-capacidade-contextual-v2b"
    item["features"] = {
        "exploracao_sombra": {
            "versao": versao
        },
        "protecao_conversao_gols": {
            "ativa": True,
            "aprovada": True,
            "versao": "protecao-conversao-gols-v1",
            "motivo": "apoio_da_linha_confirmado",
        },
        "gol_capacidade_contextual_v2": {
            "linhagem_sha256": "linhagem-imutavel",
            "probabilidade_estimada_nao_calibrada": 0.80,
        },
    }
    return item


def _candidato_com_historico_api(mercado="gol_ft", linha=1.5):
    item = _candidato(mercado=mercado, linha=linha)
    item["features"] = {
        "protecao_conversao_gols": {
            "ativa": True,
            "aprovada": True,
            "versao": "protecao-conversao-gols-v1",
            "motivo": "apoio_da_linha_confirmado",
            "mercado": mercado,
            "linha": linha,
            "campo": "over_1_5_taxa",
            "amostras_gerais": [15, 15],
            "amostras_mando": [7, 6],
            "taxas_gerais": [0.80, 0.67],
            "taxas_mando": [0.71, 0.72],
            "media_geral": 0.735,
            "media_mando": 0.715,
        }
    }
    return item


class TendenciasPackBallLigasTest(unittest.TestCase):
    def setUp(self):
        self.jogo = {
            "mandante": "San Antonio",
            "visitante": "Rival FC",
            "placar": "0-0",
            "status": "65 '",
        }

    def test_converte_link_da_lista_para_aba_times_da_liga(self):
        self.assertEqual(
            "https://packball.com/pt/leagues/699/league/ecuador-liga-pro-serie-b/teams",
            _url_times_liga(
                "https://packball.com/pt/matches/699/league/"
                "ecuador-liga-pro-serie-b/summary"
            ),
        )

    def test_reconhece_rotulos_atuais_de_over_gols(self):
        self.assertTrue(_rotulo_estatistica_over_gols("Over Gols"))
        self.assertTrue(_rotulo_estatistica_over_gols("OVER GOALS"))
        self.assertFalse(_rotulo_estatistica_over_gols("Under Gols"))
        self.assertFalse(_rotulo_estatistica_over_gols("Média de gols"))

    def test_recupera_link_da_liga_na_pagina_da_partida(self):
        class Pagina:
            @staticmethod
            def evaluate(_script):
                return (
                    "https://packball.com/pt/matches/699/league/"
                    "ecuador-liga-pro-serie-b/summary"
                )

        self.assertEqual(
            "https://packball.com/pt/matches/699/league/"
            "ecuador-liga-pro-serie-b/summary",
            _descobrir_liga_url_pagina(Pagina()),
        )

    def test_fallback_dom_configura_periodo_e_exige_times(self):
        class Pagina:
            @property
            def first(self):
                return self

            def locator(self, _seletor):
                return self

            def wait_for(self, **_kwargs):
                return None

        pagina = Pagina()
        times = [_time("San Antonio", 0.70, 0.80)]
        with (
            patch(
                "tendencias_packball_ligas._configurar_periodo",
                return_value=(0, 45),
            ) as configurar,
            patch(
                "tendencias_packball_ligas._ler_times",
                return_value=times,
            ),
        ):
            leitura = _ler_times_dom_periodo(pagina, "1t")

        configurar.assert_called_once_with(pagina, "1t")
        self.assertEqual("packball_ligas_times_dom", leitura["fonte"])
        self.assertEqual((0, 45), (
            leitura["minuto_inicio"], leitura["minuto_fim"]
        ))
        self.assertEqual(times, leitura["times"])

    def test_coleta_usa_tabela_dom_quando_requisicao_interna_ausente(self):
        class Pagina:
            def on(self, _evento, callback):
                self.callback = callback

            def goto(self, *_args, **_kwargs):
                return None

            def wait_for_timeout(self, _tempo):
                return None

            def remove_listener(self, _evento, _callback):
                return None

        times = [
            _time("San Antonio", 0.70, 0.80),
            _time("Rival FC", 0.65, 0.75),
        ]
        with patch(
            "tendencias_packball_ligas._ler_times_dom_periodo",
            return_value={
                "times": times,
                "minuto_inicio": 45,
                "minuto_fim": 90,
                "fonte": "packball_ligas_times_dom",
            },
        ):
            leitura = coletar_tendencias_packball_liga(
                Pagina(),
                {
                    "liga_url": (
                        "https://packball.com/pt/matches/699/league/"
                        "ecuador-liga-pro-serie-b/summary"
                    ),
                    "liga_nome": "Liga Pro Serie B",
                },
                "2t",
                cache={},
            )

        self.assertEqual("packball_ligas_times_dom", leitura["fonte"])
        self.assertEqual(2, len(leitura["times"]))
        self.assertEqual(
            "consulta_times_packball_ausente",
            leitura["fallback_dom"]["motivo"],
        )

    def test_periodo_atual_respeita_primeiro_e_segundo_tempo(self):
        self.assertEqual("1t", periodo_atual({"status": "28 '"}))
        self.assertEqual("2t", periodo_atual({"status": "65 '"}))

    def test_converte_resposta_oficial_packball_em_tendencias(self):
        times = _ler_times_api({
            "data": {"teams": [{
                "team": {"name": "San Antonio", "ranking": 25},
                "matches": {"playeds": 20, "with_stats": 20},
                "values": [60, 30, 5],
            }]}
        })
        self.assertEqual(1, len(times))
        self.assertEqual(0.25, times[0]["eficiencia"])
        self.assertEqual(0.60, times[0]["over_0_5"])
        self.assertEqual(0.30, times[0]["over_1_5"])
        self.assertEqual(0.05, times[0]["over_2_5"])

    def test_nao_repassa_pseudo_cabecalhos_http(self):
        self.assertEqual(
            {"authorization": "privado", "accept": "application/json"},
            _cabecalhos_reutilizaveis({
                ":authority": "api.packball.com",
                "host": "api.packball.com",
                "content-length": "0",
                "authorization": "privado",
                "accept": "application/json",
            }),
        )

    def test_perfil_fraco_como_san_antonio_bloqueia(self):
        contexto = _contexto(
            _time("San Antonio", 0.10, 0.40),
            _time("Rival FC", 0.15, 0.45),
        )
        avaliacao = avaliar_tendencia_packball(
            _candidato(), contexto, self.jogo, {"placar_intervalo": [0, 0]}
        )
        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual("tendencia_packball_fraca", avaliacao["motivo"])
        self.assertEqual(0.5, avaliacao["linha_periodo"])

    def test_compara_os_dois_times_e_aprova_perfil_forte(self):
        contexto = _contexto(
            _time("San Antonio", 0.30, 0.60),
            _time("Rival FC", 0.40, 0.75),
        )
        avaliacao = avaliar_tendencia_packball(
            _candidato(), contexto, self.jogo, {"placar_intervalo": [0, 0]}
        )
        self.assertTrue(avaliacao["aprovada"])
        self.assertEqual(0.675, avaliacao["media_taxa"])

    def test_linha_do_periodo_considera_gols_apos_intervalo(self):
        jogo = {**self.jogo, "placar": "1-0"}
        contexto = _contexto(
            _time("San Antonio", 0.30, 0.60, over_15=0.40),
            _time("Rival FC", 0.40, 0.75, over_15=0.50),
        )
        avaliacao = avaliar_tendencia_packball(
            _candidato(linha=1.5),
            contexto,
            jogo,
            {"placar_intervalo": [0, 0]},
        )
        self.assertEqual(1.5, avaliacao["linha_periodo"])
        self.assertTrue(avaliacao["aprovada"])

    def test_simulacao_fraca_fica_registrada_mas_nao_e_enviada(self):
        item = _candidato(status="simulacao")
        item["features"]["exploracao_sombra"] = {"versao": "teste"}
        contexto = _contexto(
            _time("San Antonio", 0.10, 0.40),
            _time("Rival FC", 0.15, 0.45),
        )
        aplicar_protecao_tendencias_packball(
            [item], contexto, self.jogo, {"placar_intervalo": [0, 0]}
        )
        self.assertEqual("simulacao", item["status"])
        self.assertTrue(
            motivo_suspensao_simulacao(item).startswith(
                "protecao_tendencias_packball:"
            )
        )

    def test_aprovado_bloqueado_vira_contrafactual_sem_telegram(self):
        item = _candidato(status="aprovado")
        contexto = _contexto(
            _time("San Antonio", 0.10, 0.40),
            _time("Rival FC", 0.15, 0.45),
        )

        aplicar_protecao_tendencias_packball(
            [item], contexto, self.jogo, {"placar_intervalo": [0, 0]}
        )

        self.assertEqual("simulacao", item["status"])
        contrafactual = item["features"]["avaliacao_contrafactual"]
        self.assertEqual(
            "protecao_tendencias_packball", contrafactual["protecao"]
        )
        self.assertFalse(contrafactual["telegram"])
        self.assertFalse(contrafactual["calibracao_oficial"])
        self.assertTrue(
            motivo_suspensao_simulacao(item).startswith(
                "protecao_tendencias_packball:"
            )
        )

    def test_indisponibilidade_usa_historico_forte_do_metodo(self):
        item = _candidato_com_historico_proprio()
        resumo = aplicar_protecao_tendencias_packball(
            [item],
            {"estado": "indisponivel"},
            self.jogo,
            {"placar_intervalo": [0, 0]},
        )

        avaliacao = item["features"]["protecao_tendencias_packball"]
        self.assertTrue(avaliacao["aprovada"])
        self.assertEqual(
            "fallback_historico_metodo_confirmado",
            avaliacao["motivo"],
        )
        self.assertEqual(1, resumo["fallbacks_historicos"])
        self.assertIsNone(motivo_suspensao_simulacao(item))

    def test_indisponibilidade_tambem_libera_braco_ht_v2b(self):
        item = _candidato_com_historico_proprio(
            mercado="gol_ht",
            linha=1.5,
            versao="gol-ht-capacidade-contextual-v2b",
        )
        jogo = {**self.jogo, "status": "25 '"}
        resumo = aplicar_protecao_tendencias_packball(
            [item],
            {"estado": "indisponivel"},
            jogo,
            {"placar_intervalo": [0, 0]},
        )

        avaliacao = item["features"]["protecao_tendencias_packball"]
        self.assertTrue(avaliacao["aprovada"])
        self.assertEqual(
            "fallback_historico_metodo_confirmado",
            avaliacao["motivo"],
        )
        self.assertEqual(1, resumo["fallbacks_historicos"])
        self.assertIsNone(motivo_suspensao_simulacao(item))

    def test_fallback_nao_libera_regra_sem_linhagem_e_conversao(self):
        item = _candidato(status="simulacao")
        aplicar_protecao_tendencias_packball(
            [item], {"estado": "indisponivel"}, self.jogo
        )

        avaliacao = item["features"]["protecao_tendencias_packball"]
        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual(
            "tendencia_packball_indisponivel", avaliacao["motivo"]
        )

    def test_fallback_amplo_reprovado_nao_libera_gol_antecipado(self):
        item = _candidato(status="simulacao")
        item["features"] = {
            "protecao_conversao_gols": {
                "ativa": True,
                "aprovada": True,
                "versao": "protecao-conversao-gols-v1",
            },
            "gol_antecipado": {
                "linhagem_sha256": "linhagem-antecipada"
            },
        }
        avaliacao = avaliar_tendencia_packball(
            item, {"estado": "indisponivel"}, self.jogo
        )
        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual(
            "tendencia_packball_indisponivel", avaliacao["motivo"]
        )

    def test_rollback_desativa_fallback_historico(self):
        item = _candidato_com_historico_proprio()
        with patch(
            "tendencias_packball_ligas.FALLBACK_HISTORICO_ATIVO", False
        ):
            avaliacao = avaliar_tendencia_packball(
                item, {"estado": "indisponivel"}, self.jogo
            )
        self.assertFalse(avaliacao["aprovada"])

    def test_packball_fraco_continua_bloqueando_mesmo_com_fallback(self):
        item = _candidato_com_historico_proprio()
        contexto = _contexto(
            _time("San Antonio", 0.10, 0.40),
            _time("Rival FC", 0.15, 0.45),
        )
        avaliacao = avaliar_tendencia_packball(
            item, contexto, self.jogo, {"placar_intervalo": [0, 0]}
        )
        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual("tendencia_packball_fraca", avaliacao["motivo"])

    def test_amostra_pequena_preserva_fonte_e_tamanho_observado(self):
        casa = _time("San Antonio", 0.70, 0.80)
        casa["jogos"] = 4
        contexto = _contexto(
            casa,
            _time("Rival FC", 0.65, 0.75),
        )
        contexto["fonte"] = "packball_ligas_times_dom"

        avaliacao = avaliar_tendencia_packball(
            _candidato(),
            contexto,
            self.jogo,
            {"placar_intervalo": [0, 0]},
        )

        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual(
            "amostra_packball_insuficiente", avaliacao["motivo"]
        )
        self.assertTrue(avaliacao["fonte_packball_disponivel"])
        self.assertEqual(
            "packball_ligas_times_dom", avaliacao["fonte"]
        )
        self.assertEqual(
            {"mandante": 4, "visitante": 20, "minima": 10},
            avaliacao["amostras"],
        )

    def test_amostra_packball_curta_usa_historico_confirmado_da_api(self):
        item = _candidato_com_historico_api()
        casa = _time("San Antonio", 0.70, 0.80)
        fora = _time("Rival FC", 0.65, 0.75)
        casa["jogos"] = 1
        fora["jogos"] = 2

        resumo = aplicar_protecao_tendencias_packball(
            [item],
            _contexto(casa, fora),
            {**self.jogo, "placar": "1-0"},
            {"placar_intervalo": [0, 0]},
        )

        avaliacao = item["features"]["protecao_tendencias_packball"]
        self.assertTrue(avaliacao["aprovada"])
        self.assertEqual(
            "fallback_historico_api_amostra_confirmado",
            avaliacao["motivo"],
        )
        self.assertEqual("amostra_packball_insuficiente", avaliacao["motivo_packball"])
        self.assertEqual([15, 15], avaliacao["fallback_historico"]["amostras_gerais"])
        self.assertEqual(1, resumo["fallbacks_api_amostra"])
        self.assertEqual("aprovado", item["status"])

    def test_fallback_api_ht_linha_alta_fica_em_quarentena(self):
        item = _candidato_com_historico_api(
            mercado="gol_ht", linha=1.5
        )
        casa = _time("San Antonio", 0.70, 0.80)
        fora = _time("Rival FC", 0.65, 0.75)
        casa["jogos"] = 1
        fora["jogos"] = 2

        resumo = aplicar_protecao_tendencias_packball(
            [item],
            _contexto(casa, fora, periodo="1t"),
            {**self.jogo, "placar": "0-0", "status": "22 '"},
            {"placar_intervalo": [0, 0]},
        )

        avaliacao = item["features"]["protecao_tendencias_packball"]
        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual(
            "fallback_historico_api_ht_linha_alta_em_quarentena",
            avaliacao["motivo"],
        )
        self.assertEqual(
            "quarentena_prospectiva",
            avaliacao["politica_fallback_ht"]["estado"],
        )
        self.assertTrue(
            avaliacao["politica_fallback_ht"][
                "preserva_confirmacao_direta_packball"
            ]
        )
        self.assertEqual("simulacao", item["status"])
        self.assertEqual(1, resumo["bloqueados"])

    def test_rollback_relibera_fallback_api_ht_linha_alta(self):
        item = _candidato_com_historico_api(
            mercado="gol_ht", linha=1.5
        )
        casa = _time("San Antonio", 0.70, 0.80)
        fora = _time("Rival FC", 0.65, 0.75)
        casa["jogos"] = 1
        fora["jogos"] = 2

        with patch(
            "tendencias_packball_ligas."
            "fallback_api_ht_linhas_altas_ativo",
            return_value=True,
        ):
            avaliacao = avaliar_tendencia_packball(
                item,
                _contexto(casa, fora, periodo="1t"),
                {**self.jogo, "placar": "0-0", "status": "22 '"},
                {"placar_intervalo": [0, 0]},
            )

        self.assertTrue(avaliacao["aprovada"])
        self.assertEqual(
            "fallback_historico_api_amostra_confirmado",
            avaliacao["motivo"],
        )

    def test_fallback_api_nao_cobre_packball_totalmente_indisponivel(self):
        item = _candidato_com_historico_api()
        avaliacao = avaliar_tendencia_packball(
            item, {"estado": "indisponivel"}, self.jogo
        )
        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual("tendencia_packball_indisponivel", avaliacao["motivo"])

    def test_fallback_api_nao_cobre_tendencia_packball_fraca(self):
        item = _candidato_com_historico_api(linha=0.5)
        contexto = _contexto(
            _time("San Antonio", 0.10, 0.40),
            _time("Rival FC", 0.15, 0.45),
        )
        avaliacao = avaliar_tendencia_packball(
            item, contexto, self.jogo, {"placar_intervalo": [0, 0]}
        )
        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual("tendencia_packball_fraca", avaliacao["motivo"])

    def test_rollback_desativa_somente_fallback_api_de_amostra(self):
        item = _candidato_com_historico_api()
        casa = _time("San Antonio", 0.70, 0.80)
        casa["jogos"] = 2
        with patch(
            "tendencias_packball_ligas.FALLBACK_API_AMOSTRA_ATIVO", False
        ):
            avaliacao = avaliar_tendencia_packball(
                item,
                _contexto(casa, _time("Rival FC", 0.65, 0.75)),
                self.jogo,
                {"placar_intervalo": [0, 0]},
            )
        self.assertFalse(avaliacao["aprovada"])
        self.assertEqual("amostra_packball_insuficiente", avaliacao["motivo"])


if __name__ == "__main__":
    unittest.main()
