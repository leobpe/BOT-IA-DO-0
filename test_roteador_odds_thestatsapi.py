import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from roteador_odds_thestatsapi import (
    BOOKMAKER,
    converter_odds_bet365_contrato_interno,
    idade_efetiva_resposta,
    rotear_odds_thestatsapi_sombra,
    taxonomia_coortes_thestatsapi,
    validar_gate_operacional_thestatsapi,
)


AGORA = datetime(2026, 8, 13, 22, 0, tzinfo=timezone.utc)
MATCH_ID = "mt_745359007"


def jogo_packball(*, status="26 '", placar="1-0"):
    return {
        "mandante": "Alpha",
        "visitante": "Beta",
        "placar": placar,
        "status": status,
        "link": "https://packball.com/match/alpha-beta",
    }


def diagnostico_associacao(
    *,
    match_id=MATCH_ID,
    similaridade=0.96,
    margem=None,
    candidatos=1,
    orientacao="direta",
    placar=(1, 0),
    minuto=26,
    periodo="1H",
):
    return {
        "fonte": "thestatsapi",
        "motivo": "associado",
        "candidatos_compativeis": candidatos,
        "margem_associacao": margem,
        "associacao": {
            "match_id": match_id,
            "fixture_id": match_id,
            "similaridade": similaridade,
            "margem_associacao": margem,
            "candidatos_compativeis": candidatos,
            "orientacao": orientacao,
            "placar": list(placar),
            "status": {"short": periodo, "elapsed": minuto},
        },
    }


def resposta_live_stats(
    *,
    match_id=MATCH_ID,
    idade=5,
    placar=(1, 0),
    minuto=25,
    periodo="first_half",
    updated_at=None,
):
    dados = {
        "match_id": match_id,
        "meta": {
            "home_goals": placar[0],
            "away_goals": placar[1],
            "elapsed_minutes": minuto,
            "match_status": periodo,
        },
        "stats": {
            "total_shots": {"all": {"home": 5, "away": 2}},
            "expected_goals": {"all": {"home": 0.8, "away": 0.2}},
        },
    }
    if updated_at is not None:
        dados["updated_at"] = updated_at
    return {
        "ok": True,
        "cache": bool(idade),
        "idade_segundos": idade,
        "dados": dados,
    }


def mercados_suportados():
    oferta = lambda over, under: {
        "over": {"live": str(over)},
        "under": {"live": str(under)},
    }
    return {
        "total_goals": {"2.5": oferta(1.82, 1.94)},
        "first_half_total_goals": {"1.5": oferta(2.10, 1.70)},
        "second_half_total_goals": {"1.5": oferta(1.91, 1.87)},
        "match_corners": {
            "8.5": oferta(1.90, 1.90),
            "8": oferta(2.00, 1.80),
        },
        "first_half_corners": {
            "4.5": oferta(1.85, 1.95),
            "4.25": oferta(1.92, 1.88),
        },
        "second_half_corners": {
            "5.5": oferta(1.93, 1.87),
            "5.75": oferta(2.02, 1.78),
        },
        # Uma linha de meia unidade continua asiatica quando a taxonomia
        # declarada pelo provedor e explicitamente Asian Corners.
        "asian_corners": {"9.5": oferta(1.91, 1.89)},
        "first_half_asian_corners": {"4.5": oferta(1.86, 1.94)},
        "second_half_asian_corners": {"5.5": oferta(1.88, 1.92)},
    }


def resposta_odds(
    *,
    match_id=MATCH_ID,
    idade=4,
    bookmaker=BOOKMAKER,
    markets=None,
    updated_at=None,
):
    dados = {
        "match_id": match_id,
        "bookmakers": [{
            "bookmaker": bookmaker,
            "markets": mercados_suportados() if markets is None else markets,
        }],
    }
    if updated_at is not None:
        dados["updated_at"] = updated_at
    return {
        "ok": True,
        "cache": bool(idade),
        "idade_segundos": idade,
        "dados": dados,
    }


def assert_sem_autorizacao(caso, objeto):
    if isinstance(objeto, dict):
        for chave, valor in objeto.items():
            if chave in {
                "aplicacao_sinais",
                "autoriza_sinal",
                "calibracao",
                "telegram",
                "substitui_packball",
                "ativacao_automatica",
            }:
                caso.assertIs(valor, False, msg=f"{chave} concedeu autoridade")
            assert_sem_autorizacao(caso, valor)
    elif isinstance(objeto, list):
        for item in objeto:
            assert_sem_autorizacao(caso, item)


class TestGateEstritoTheStatsAPI(unittest.TestCase):
    def gate(self, **trocas):
        jogo = trocas.pop("jogo", jogo_packball())
        diagnostico = trocas.pop("diagnostico", diagnostico_associacao())
        live = trocas.pop("live", resposta_live_stats())
        odds = trocas.pop("odds", resposta_odds())
        return validar_gate_operacional_thestatsapi(
            jogo, diagnostico, live, odds, agora=AGORA, **trocas
        )

    def test_aprova_somente_com_identidade_estado_e_frescor_exatos(self):
        resultado = self.gate()

        self.assertTrue(resultado["apto_sombra"])
        self.assertEqual(resultado["motivo"], "apto_sombra")
        self.assertEqual(resultado["match_id"], MATCH_ID)
        self.assertEqual(resultado["placar_validado"], [1, 0])
        self.assertEqual(resultado["periodo_validado"], "1T")
        self.assertEqual(resultado["delta_minuto"], 1)
        self.assertEqual(resultado["idade_live_stats_segundos"], 5)
        self.assertEqual(resultado["idade_odds_segundos"], 4)
        assert_sem_autorizacao(self, resultado)

    def test_delta_de_dois_minutos_e_aceito_mas_tres_e_rejeitado(self):
        limite = self.gate(live=resposta_live_stats(minuto=24))
        excedido = self.gate(live=resposta_live_stats(minuto=23))

        self.assertTrue(limite["apto_sombra"])
        self.assertFalse(excedido["apto_sombra"])
        self.assertEqual(excedido["motivo"], "minuto_live_stats_incompativel")

    def test_rejeita_associacao_sem_confianca_ou_ambigua(self):
        casos = (
            (
                diagnostico_associacao(similaridade=0.899),
                "similaridade_insuficiente",
            ),
            (
                diagnostico_associacao(
                    candidatos=2, margem=0.049, similaridade=0.98
                ),
                "margem_associacao_insuficiente",
            ),
            (
                diagnostico_associacao(
                    candidatos=2, margem=None, similaridade=0.98
                ),
                "margem_associacao_insuficiente",
            ),
            (
                diagnostico_associacao(orientacao="duvidosa"),
                "orientacao_invalida",
            ),
            (
                diagnostico_associacao(candidatos=None),
                "quantidade_candidatos_invalida",
            ),
        )
        for diagnostico, motivo in casos:
            with self.subTest(motivo=motivo):
                resultado = self.gate(diagnostico=diagnostico)
                self.assertFalse(resultado["apto_sombra"])
                self.assertEqual(resultado["motivo"], motivo)

    def test_rejeita_match_id_diferente_em_qualquer_evidencia(self):
        ids_internos_diferentes = diagnostico_associacao()
        ids_internos_diferentes["associacao"]["fixture_id"] = "mt_outro"
        casos = (
            (
                {"live": resposta_live_stats(match_id="mt_outro")},
                "match_id_live_stats_incompativel",
            ),
            (
                {"odds": resposta_odds(match_id="mt_outro")},
                "match_id_odds_incompativel",
            ),
            (
                {"diagnostico": diagnostico_associacao(match_id="123")},
                "match_id_invalido",
            ),
            (
                {"diagnostico": ids_internos_diferentes},
                "ids_associacao_incompativeis",
            ),
        )
        for argumentos, motivo in casos:
            with self.subTest(motivo=motivo):
                resultado = self.gate(**argumentos)
                self.assertEqual(resultado["motivo"], motivo)

    def test_rejeita_placar_diferente_na_lista_ou_live_stats(self):
        casos = (
            (
                {"diagnostico": diagnostico_associacao(placar=(0, 0))},
                "placar_lista_incompativel",
            ),
            (
                {"live": resposta_live_stats(placar=(0, 1))},
                "placar_live_stats_incompativel",
            ),
            (
                {"jogo": jogo_packball(placar="sem placar")},
                "placar_packball_indisponivel",
            ),
        )
        for argumentos, motivo in casos:
            with self.subTest(motivo=motivo):
                resultado = self.gate(**argumentos)
                self.assertEqual(resultado["motivo"], motivo)

    def test_orientacao_invertida_reorienta_live_stats(self):
        resultado = self.gate(
            diagnostico=diagnostico_associacao(orientacao="invertida"),
            live=resposta_live_stats(placar=(0, 1)),
        )

        self.assertTrue(resultado["apto_sombra"])
        self.assertEqual(resultado["orientacao"], "invertida")

    def test_rejeita_periodo_diferente_na_lista_ou_live_stats(self):
        casos = (
            (
                {"diagnostico": diagnostico_associacao(periodo="2H")},
                "periodo_lista_incompativel",
            ),
            (
                {"live": resposta_live_stats(periodo="second_half")},
                "periodo_live_stats_incompativel",
            ),
        )
        for argumentos, motivo in casos:
            with self.subTest(motivo=motivo):
                resultado = self.gate(**argumentos)
                self.assertEqual(resultado["motivo"], motivo)

    def test_reconcilia_status_live_generico_da_lista_com_live_stats(self):
        # O teste valida a capacidade isolada do reconciliador, portanto não
        # pode depender da opção operacional carregada do .env da máquina.
        with patch.dict(
            "os.environ",
            {"THESTATSAPI_RECONCILIAR_STATUS_LIVE_GENERICO_ATIVA": "1"},
        ):
            resultado = self.gate(
                diagnostico=diagnostico_associacao(
                    periodo="LIVE", minuto=None
                )
            )

        self.assertTrue(resultado["apto_sombra"])
        self.assertTrue(resultado["periodo_lista_reconciliado"])
        self.assertIn(
            "status_lista_live_generico_reconciliado_por_live_stats",
            resultado["avisos"],
        )
        self.assertEqual(
            resultado["rollback"],
            "THESTATSAPI_RECONCILIAR_STATUS_LIVE_GENERICO_ATIVA=0",
        )

    def test_status_live_generico_nao_encobre_divergencia_do_live_stats(self):
        resultado = self.gate(
            diagnostico=diagnostico_associacao(
                periodo="LIVE", minuto=None
            ),
            live=resposta_live_stats(periodo="second_half"),
        )

        self.assertFalse(resultado["apto_sombra"])
        self.assertEqual(
            resultado["motivo"], "periodo_live_stats_incompativel"
        )

    def test_rollback_restaura_bloqueio_do_status_live_generico(self):
        with patch.dict(
            "os.environ",
            {"THESTATSAPI_RECONCILIAR_STATUS_LIVE_GENERICO_ATIVA": "0"},
        ):
            resultado = self.gate(
                diagnostico=diagnostico_associacao(
                    periodo="LIVE", minuto=None
                )
            )

        self.assertFalse(resultado["apto_sombra"])
        self.assertEqual(resultado["motivo"], "periodo_lista_incompativel")

    def test_rejeita_minuto_ausente_e_estado_packball_ausente(self):
        casos = (
            (
                {"diagnostico": diagnostico_associacao(minuto=None)},
                "minuto_lista_indisponivel",
            ),
            (
                {"live": resposta_live_stats(minuto=None)},
                "minuto_live_stats_indisponivel",
            ),
            (
                {"jogo": jogo_packball(status="ao vivo")},
                "estado_packball_indisponivel",
            ),
        )
        for argumentos, motivo in casos:
            with self.subTest(motivo=motivo):
                resultado = self.gate(**argumentos)
                self.assertEqual(resultado["motivo"], motivo)

    def test_frescor_de_trinta_e_aceito_e_trinta_e_um_rejeitado(self):
        limite = self.gate(
            live=resposta_live_stats(idade=30),
            odds=resposta_odds(idade=30),
        )
        stats_velho = self.gate(live=resposta_live_stats(idade=31))
        odds_velhas = self.gate(odds=resposta_odds(idade=31))

        self.assertTrue(limite["apto_sombra"])
        self.assertEqual(stats_velho["motivo"], "live_stats_sem_frescor")
        self.assertEqual(odds_velhas["motivo"], "odds_sem_frescor")

    def test_parametro_nao_consegue_relaxar_limite_de_trinta(self):
        resultado = self.gate(
            live=resposta_live_stats(idade=31),
            frescor_maximo_segundos=90,
        )

        self.assertEqual(resultado["motivo"], "live_stats_sem_frescor")

    def test_timestamp_do_provedor_mais_velho_domina_idade_do_cache(self):
        live = resposta_live_stats(
            idade=2,
            updated_at=(AGORA - timedelta(seconds=31)).isoformat(),
        )
        resultado = self.gate(live=live)

        self.assertEqual(idade_efetiva_resposta(live, AGORA), 31)
        self.assertEqual(resultado["motivo"], "live_stats_sem_frescor")

    def test_timestamp_mais_antigo_domina_envelope_mais_novo(self):
        odds = resposta_odds(
            idade=2,
            updated_at=(AGORA - timedelta(seconds=31)).isoformat(),
        )
        odds["updated_at"] = (AGORA - timedelta(seconds=1)).isoformat()

        self.assertEqual(idade_efetiva_resposta(odds, AGORA), 31)
        self.assertEqual(self.gate(odds=odds)["motivo"], "odds_sem_frescor")

    def test_gate_exige_bet365_exata_antes_da_conversao(self):
        resultado = self.gate(
            odds=resposta_odds(bookmaker="Bet365 Sportsbook")
        )

        self.assertEqual(resultado["motivo"], "bookmaker_bet365_exata_ausente")

    def test_rejeita_timestamp_futuro_ou_resposta_sem_prova_de_frescor(self):
        futuro = resposta_odds(
            idade=None,
            updated_at=(AGORA + timedelta(seconds=3)).isoformat(),
        )
        sem_prova = resposta_odds(idade=None)

        self.assertIsNone(idade_efetiva_resposta(futuro, AGORA))
        self.assertEqual(self.gate(odds=futuro)["motivo"], "odds_sem_frescor")
        self.assertEqual(
            self.gate(odds=sem_prova)["motivo"], "odds_sem_frescor"
        )


class TestConversorOddsBet365(unittest.TestCase):
    def converter(self, **trocas):
        return converter_odds_bet365_contrato_interno(
            resposta_odds(**trocas), agora=AGORA
        )

    @staticmethod
    def ofertas(resultado):
        encontradas = []
        for mercado in resultado["ao_vivo"]:
            encontradas.extend(mercado.get("ofertas") or [])
            for bloco in (mercado.get("ofertas_periodos") or {}).values():
                encontradas.extend(bloco.get("ofertas") or [])
        return encontradas

    def test_converte_gols_e_cantos_ft_1t_2t_em_nove_coortes(self):
        resultado = self.converter()
        coortes = resultado["_metadados"]["coortes_sombra"]

        self.assertEqual(len(resultado["ao_vivo"]), 3)
        self.assertEqual(resultado["_metadados"]["total_ofertas"], 12)
        self.assertEqual(set(coortes), {
            "thestatsapi-bet365-gols-total-ft-v1",
            "thestatsapi-bet365-gols-total-1t-v1",
            "thestatsapi-bet365-gols-total-2t-v1",
            "thestatsapi-bet365-escanteios-total-ft-v1",
            "thestatsapi-bet365-escanteios-total-1t-v1",
            "thestatsapi-bet365-escanteios-total-2t-v1",
            "thestatsapi-bet365-escanteios-asiaticos-ft-v1",
            "thestatsapi-bet365-escanteios-asiaticos-1t-v1",
            "thestatsapi-bet365-escanteios-asiaticos-2t-v1",
        })
        ofertas = self.ofertas(resultado)
        self.assertTrue(all(item["bookmaker"] == "Bet365" for item in ofertas))
        self.assertTrue(all(item["fonte"] == "thestatsapi" for item in ofertas))
        self.assertTrue(all(item["match_id"] == MATCH_ID for item in ofertas))
        assert_sem_autorizacao(self, resultado)

    def test_diferencia_linha_normal_e_asiatica_sem_confundir_nome_explicito(self):
        resultado = self.converter()
        ofertas = self.ofertas(resultado)
        por_chave = {
            (item["mercado_original"], item["linha"]): item
            for item in ofertas
        }

        self.assertEqual(
            por_chave[("match_corners", 8.5)]["tipo_mercado"], "total"
        )
        self.assertEqual(
            por_chave[("match_corners", 8.0)]["tipo_mercado"], "asiatico"
        )
        self.assertEqual(
            por_chave[("first_half_corners", 4.25)]["tipo_mercado"],
            "asiatico",
        )
        self.assertEqual(
            por_chave[("asian_corners", 9.5)]["tipo_mercado"], "asiatico"
        )
        self.assertEqual(
            por_chave[("first_half_asian_corners", 4.5)]["periodo"], "1T"
        )
        self.assertEqual(
            por_chave[("second_half_asian_corners", 5.5)]["periodo"], "2T"
        )

    def test_aceita_alias_asian_corners_periodo_na_ordem_do_provedor(self):
        oferta = lambda over, under: {
            "over": {"live": str(over)},
            "under": {"live": str(under)},
        }
        resultado = self.converter(markets={
            "Asian Corners 1st Half": {
                "4.5": oferta(1.84, 1.96),
            },
            "Asian Corners 2nd Half": {
                "5.5": oferta(1.87, 1.93),
            },
        })
        ofertas = self.ofertas(resultado)
        por_original = {
            item["mercado_original"]: item for item in ofertas
        }

        self.assertEqual(
            por_original["Asian Corners 1st Half"]["periodo"], "1T"
        )
        self.assertEqual(
            por_original["Asian Corners 2nd Half"]["periodo"], "2T"
        )
        self.assertTrue(all(
            item["tipo_mercado"] == "asiatico" for item in ofertas
        ))

    def test_rejeita_explicitamente_mercados_fora_do_escopo(self):
        oferta = {
            "2.5": {
                "over": {"live": "1.90"},
                "under": {"live": "1.90"},
            }
        }
        proibidos = {
            "next_goal": oferta,
            "next_corner": oferta,
            "team_total_goals": oferta,
            "home_total_corners": oferta,
            "away_total_goals": oferta,
            "asian_handicap": oferta,
            "exact_goals": oferta,
            "corner_race": oferta,
            "most_corners": oferta,
            "first_to_score": oferta,
            "unknown_goal_line": oferta,
        }
        resultado = self.converter(markets=proibidos)

        self.assertEqual(resultado["ao_vivo"], [])
        self.assertEqual(resultado["movimentacao"], [])
        self.assertEqual(resultado["_metadados"]["total_ofertas"], 0)
        self.assertEqual(
            set(resultado["_metadados"]["mercados_ignorados"]),
            set(proibidos),
        )

    def test_exige_bookmaker_bet365_exata(self):
        aceito = self.converter(bookmaker="  bEt365  ")
        rejeitado = self.converter(bookmaker="Bet365 Sportsbook")

        self.assertGreater(aceito["_metadados"]["total_ofertas"], 0)
        self.assertEqual(rejeitado["_metadados"]["total_ofertas"], 0)
        self.assertEqual(
            rejeitado["_metadados"]["bookmakers_ignorados"],
            ["Bet365 Sportsbook"],
        )

    def test_rejeita_oferta_incompleta_ou_odd_invalida(self):
        mercados = {
            "total_goals": {
                "2.5": {
                    "over": {"live": "1.90"},
                    "under": {},
                },
                "3.5": {
                    "over": {"live": "1.00"},
                    "under": {"live": "2.00"},
                },
            }
        }
        resultado = self.converter(markets=mercados)

        self.assertEqual(resultado["_metadados"]["total_ofertas"], 0)

    def test_preserva_linhagem_frescor_cache_e_nao_cria_movimento(self):
        instante = AGORA - timedelta(seconds=7)
        resultado = self.converter(
            idade=3,
            updated_at=instante.isoformat(),
        )
        oferta = self.ofertas(resultado)[0]

        self.assertEqual(resultado["_metadados"]["idade_segundos"], 7)
        self.assertTrue(resultado["_metadados"]["cache"])
        self.assertEqual(oferta["coletado_em"], instante.isoformat())
        self.assertEqual(oferta["recebido_em"], AGORA.isoformat())
        self.assertEqual(resultado["movimentacao"], [])


class TestRoteadorSomenteSombra(unittest.TestCase):
    def test_valido_continua_packball_e_mede_thestats_em_sombra(self):
        resultado = rotear_odds_thestatsapi_sombra(
            jogo_packball(),
            diagnostico_associacao(),
            resposta_live_stats(),
            resposta_odds(),
            agora=AGORA,
        )

        self.assertEqual(resultado["rota"], "packball")
        self.assertEqual(resultado["fallback"], "packball")
        self.assertEqual(resultado["rota_sombra"], "thestatsapi_bet365")
        self.assertEqual(resultado["estado"], "elegivel_somente_sombra")
        self.assertFalse(resultado["pode_omitir_packball"])
        self.assertIsNotNone(resultado["odds_sombra"])
        assert_sem_autorizacao(self, resultado)

    def test_falha_da_api_faz_fallback_sem_bloquear(self):
        falha = resposta_odds()
        falha.update({"ok": False, "dados": None})
        resultado = rotear_odds_thestatsapi_sombra(
            jogo_packball(),
            diagnostico_associacao(),
            resposta_live_stats(),
            falha,
            agora=AGORA,
        )

        self.assertEqual(resultado["rota"], "packball")
        self.assertEqual(resultado["estado"], "fallback_packball")
        self.assertFalse(resultado["pode_omitir_packball"])
        self.assertFalse(resultado["autoriza_sinal"])

    def test_sem_mercado_suportado_faz_fallback_packball(self):
        resultado = rotear_odds_thestatsapi_sombra(
            jogo_packball(),
            diagnostico_associacao(),
            resposta_live_stats(),
            resposta_odds(markets={"next_goal": {}}),
            agora=AGORA,
        )

        self.assertEqual(resultado["rota"], "packball")
        self.assertEqual(resultado["motivo"], "sem_ofertas_bet365_suportadas")

    def test_rollback_desativa_integracao_sem_alterar_rota(self):
        resultado = rotear_odds_thestatsapi_sombra(
            jogo_packball(),
            diagnostico_associacao(),
            resposta_live_stats(),
            resposta_odds(),
            agora=AGORA,
            ativa=False,
        )

        self.assertEqual(resultado["estado"], "desativada_rollback")
        self.assertEqual(resultado["rota"], "packball")
        self.assertIsNone(resultado["odds_sombra"])
        self.assertFalse(resultado["pode_omitir_packball"])
        assert_sem_autorizacao(self, resultado)

    def test_taxonomia_tem_nove_coortes_sem_promocao_automatica(self):
        taxonomia = taxonomia_coortes_thestatsapi()
        chaves = {
            (item["categoria"], item["tipo_mercado"], item["periodo"])
            for item in taxonomia
        }

        self.assertEqual(len(taxonomia), 9)
        self.assertEqual(len(chaves), 9)
        self.assertIn(("escanteios", "asiatico", "FT"), chaves)
        self.assertIn(("escanteios", "asiatico", "1T"), chaves)
        self.assertIn(("escanteios", "asiatico", "2T"), chaves)
        self.assertTrue(all(not item["ativacao_automatica"] for item in taxonomia))
        self.assertFalse(any(
            "proximo" in item["coorte_sombra"] or "next" in item["coorte_sombra"]
            for item in taxonomia
        ))
        assert_sem_autorizacao(self, taxonomia)


if __name__ == "__main__":
    unittest.main()
