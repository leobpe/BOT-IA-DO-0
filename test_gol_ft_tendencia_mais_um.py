import unittest

from gol_ft_tendencia_mais_um import (
    VERSAO, _evidencias_tendencia, gerar_gol_ft_tendencia_mais_um,
)
from telegram_alertas import (
    candidato_gol_ft_tendencia_mais_um_grupo_teste,
    motivo_suspensao_simulacao,
)


def _candidato(placar=(0, 0), odd=1.60):
    return {
        "mercado": "gol_ft", "linha": sum(placar) + 0.5, "odd": odd,
        "status": "rejeitado", "regra_versao": "sinais-v6",
        "bloqueios": ["atividade_recente_insuficiente_gols"],
        "features": {"janelas": {
            "5": {
                "disponivel": True,
                "chutes_total": 2,
                "pressao_pico": [70, 50],
            }
        }},
    }


def _qualidade():
    return {"pontuacao": 90, "campos_ausentes": [], "divergencia_critica": False}


def _contexto():
    geral = {
        "jogos": 15,
        "over_0_5_taxa": 0.95,
        "over_1_5_taxa": 0.70,
        "over_2_5_taxa": 0.55,
        "over_4_5_taxa": 0.25,
    }
    mando = {
        "jogos": 8,
        "over_0_5_taxa": 0.90,
        "over_1_5_taxa": 0.65,
        "over_2_5_taxa": 0.50,
        "over_4_5_taxa": 0.20,
        "marcou_taxa": 0.70,
        "gols_pro_media": 1.30,
    }
    return {
        "odds_pre_jogo": {"mercados": {"gols_ft": {
            "consenso_suficiente": True, "linha_consenso": 2.5,
        }}},
        "eventos_ao_vivo": {"times": {}},
        "capacidade_times_v2": {"recentes": {
            lado: {
                "geral": dict(geral),
                "mando": dict(mando),
            }
            for lado in ("mandante", "visitante")
        }},
        "tendencia_linhas_gols_v1": {"recentes": {
            lado: {"geral": dict(geral), "mando": dict(mando)}
            for lado in ("mandante", "visitante")
        }},
    }


class GolFTTendenciaMaisUmTest(unittest.TestCase):
    def test_under_nao_completa_numero_minimo_de_evidencias(self):
        contexto = _contexto()
        contexto.pop("odds_pre_jogo")
        for valor in ("-1.5", "-2.5", "Under 2.5", "−2,5", "2.5", None):
            contexto["previsao_provedor"] = {"over_under": valor}
            with self.subTest(valor=valor):
                self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
                    {"status": "60'", "placar": "0-0"}, [_candidato()], contexto, _qualidade()))

    def test_over_preserva_evidencia_na_faixa(self):
        contexto = _contexto()
        contexto.pop("odds_pre_jogo")
        for valor in ("+1.5", "+2.5", "Over 2.5", "mais de 1,5 gols"):
            contexto["previsao_provedor"] = {"over_under": valor}
            itens = gerar_gol_ft_tendencia_mais_um(
                {"status": "60'", "placar": "0-0"}, [_candidato()], contexto, _qualidade())
            self.assertEqual(1, len(itens))
            self.assertIn("previsao_provedor_15_ou_mais", itens[0]["features"]["gol_ft_tendencia_mais_um"]["evidencias_tendencia"])

    def test_under_nao_vira_veto_global_com_outros_apoios(self):
        contexto = _contexto()
        contexto["previsao_provedor"] = {"over_under": "-2.5"}
        itens = gerar_gol_ft_tendencia_mais_um(
            {"status": "60'", "placar": "0-0"}, [_candidato()], contexto, _qualidade())
        self.assertEqual(1, len(itens))
        self.assertNotIn("previsao_provedor_15_ou_mais", itens[0]["features"]["gol_ft_tendencia_mais_um"]["evidencias_tendencia"])

    def test_tendencia_superior_a_25_conta_sem_mudar_linha_da_entrada(self):
        contexto = _contexto()
        contexto.pop("odds_pre_jogo")
        for valor in ("+2.5", "+3.5", "+4.5", "+5.5", "Over 3,5"):
            with self.subTest(valor=valor):
                contexto["previsao_provedor"] = {"over_under": valor}
                itens = gerar_gol_ft_tendencia_mais_um(
                    {"status": "60'", "placar": "0-0"}, [_candidato()], contexto, _qualidade())
                self.assertEqual(1, len(itens))
                self.assertEqual(0.5, itens[0]["linha"])
                self.assertEqual(1.60, itens[0]["odd"])
                self.assertTrue(candidato_gol_ft_tendencia_mais_um_grupo_teste(itens[0]))
                dados = itens[0]["features"]["gol_ft_tendencia_mais_um"]
                self.assertEqual([1.5, None], dados["tendencia_exigida"])
                self.assertEqual(2, len(dados["evidencias_tendencia"]))
                self.assertEqual(86.0, itens[0]["pontuacao_tecnica"])

    def test_remove_teto_tambem_de_consenso_media_esperada_e_h2h(self):
        for valor in (1.5, 2.5, 2.6, 3.5, 4.5, 6.0):
            with self.subTest(valor=valor):
                contexto = {
                    "odds_pre_jogo": {"mercados": {"gols_ft": {
                        "consenso_suficiente": True, "linha_consenso": valor,
                    }}},
                    "previsao_provedor": {"gols_esperados": {"home": valor, "away": 0}},
                    "confrontos_diretos": {"jogos": 5, "media_gols": valor},
                }
                self.assertEqual([
                    "consenso_odds_pre_15_ou_mais", "gols_esperados_15_ou_mais",
                    "h2h_media_15_ou_mais",
                ], _evidencias_tendencia(contexto))

    def test_sem_teto_preserva_minimo_e_nao_aceita_dado_invalido(self):
        for valor in (None, -3.5, 0, 1.49, float("nan"), float("inf")):
            with self.subTest(valor=valor):
                contexto = {
                    "odds_pre_jogo": {"mercados": {"gols_ft": {
                        "consenso_suficiente": True, "linha_consenso": valor,
                    }}},
                    "previsao_provedor": {"gols_esperados": {"home": valor, "away": 0}},
                    "confrontos_diretos": {"jogos": 5, "media_gols": valor},
                }
                self.assertEqual([], _evidencias_tendencia(contexto))
        for valor in ("+1.0", "-3.5", "-4.5", "Under 4.5", "3.5"):
            self.assertEqual([], _evidencias_tendencia({
                "previsao_provedor": {"over_under": valor},
            }))

    def test_tendencia_alta_nao_substitui_amostra_ou_consenso(self):
        self.assertEqual([], _evidencias_tendencia({
            "odds_pre_jogo": {"mercados": {"gols_ft": {
                "consenso_suficiente": False, "linha_consenso": 4.5,
            }}},
            "confrontos_diretos": {"jogos": 4, "media_gols": 4.5},
        }))

    def test_tendencia_alta_nao_dispensa_demais_criterios(self):
        for falha in ("odd", "minuto", "qualidade", "chutes", "historico_linha", "minimo_evidencias"):
            with self.subTest(falha=falha):
                contexto = _contexto()
                contexto["previsao_provedor"] = {"over_under": "+4.5"}
                contexto["odds_pre_jogo"]["mercados"]["gols_ft"]["linha_consenso"] = 3.5
                jogo = {"status": "60'", "placar": "1-1"}
                candidato = _candidato((1, 1))
                qualidade = _qualidade()
                if falha == "odd":
                    candidato["odd"] = 1.43
                elif falha == "minuto":
                    jogo["status"] = "83'"
                elif falha == "qualidade":
                    qualidade["pontuacao"] = 79
                elif falha == "chutes":
                    candidato["features"]["janelas"]["5"]["chutes_total"] = 0
                elif falha == "historico_linha":
                    contexto["tendencia_linhas_gols_v1"]["recentes"]["mandante"]["geral"]["over_2_5_taxa"] = 0.30
                elif falha == "minimo_evidencias":
                    contexto.pop("odds_pre_jogo")
                    for lado in ("mandante", "visitante"):
                        contexto["capacidade_times_v2"]["recentes"][lado]["geral"]["over_1_5_taxa"] = 0.5
                self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
                    jogo, [candidato], contexto, qualidade))

    def test_faixas_assinadas_nao_completam_gols_esperados(self):
        contexto = _contexto()
        contexto.pop("odds_pre_jogo")
        contexto["previsao_provedor"] = {"gols_esperados": {"home": "+3.5", "away": "-1.5"}}
        self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
            {"status": "60'", "placar": "0-0"}, [_candidato()], contexto, _qualidade()))

    def test_mapeia_placares_para_linha_de_mais_um_gol(self):
        for placar, linha in (
            ((0, 0), 0.5), ((1, 0), 1.5), ((0, 1), 1.5),
            ((1, 1), 2.5), ((2, 2), 4.5),
        ):
            itens = gerar_gol_ft_tendencia_mais_um(
                {"status": "60'", "placar": f"{placar[0]}-{placar[1]}"},
                [_candidato(placar)], _contexto(), _qualidade(),
            )
            self.assertEqual(1, len(itens), placar)
            self.assertEqual(linha, itens[0]["linha"])
            self.assertEqual(
                VERSAO, itens[0]["features"]["exploracao_sombra"]["versao"]
            )
            self.assertTrue(
                candidato_gol_ft_tendencia_mais_um_grupo_teste(itens[0])
            )
            self.assertIsNone(motivo_suspensao_simulacao(itens[0]))

    def test_2_2_aceita_ate_75_e_bloqueia_depois(self):
        self.assertEqual(1, len(gerar_gol_ft_tendencia_mais_um(
            {"status": "75'", "placar": "2-2"},
            [_candidato((2, 2))], _contexto(), _qualidade(),
        )))
        self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
            {"status": "76'", "placar": "2-2"},
            [_candidato((2, 2))], _contexto(), _qualidade(),
        ))

    def test_demais_placares_aceitam_ate_82(self):
        self.assertEqual(1, len(gerar_gol_ft_tendencia_mais_um(
            {"status": "82'", "placar": "1-1"},
            [_candidato((1, 1))], _contexto(), _qualidade(),
        )))
        self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
            {"status": "83'", "placar": "1-1"},
            [_candidato((1, 1))], _contexto(), _qualidade(),
        ))

    def test_exige_odd_144_tendencia_qualidade_e_segundo_tempo(self):
        casos = (
            ({"status": "45'", "placar": "0-0"}, _candidato(), _contexto(), _qualidade()),
            ({"status": "60'", "placar": "0-0"}, _candidato(odd=1.43), _contexto(), _qualidade()),
            ({"status": "60'", "placar": "2-0"}, _candidato((2, 0)), _contexto(), _qualidade()),
            ({"status": "60'", "placar": "0-0"}, _candidato(), {}, _qualidade()),
            ({"status": "60'", "placar": "0-0"}, _candidato(), _contexto(), {"pontuacao": 79, "campos_ausentes": []}),
        )
        for jogo, candidato, contexto, qualidade in casos:
            self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
                jogo, [candidato], contexto, qualidade,
            ))

    def test_odd_144_e_vermelho_sao_aceitos_e_auditados(self):
        contexto = _contexto()
        contexto["eventos_ao_vivo"] = {
            "times": {"visitante": {"cartoes_vermelhos": 1}}
        }
        itens = gerar_gol_ft_tendencia_mais_um(
            {"status": "60'", "placar": "1-0"},
            [_candidato((1, 0), 1.44)], contexto, _qualidade(),
        )
        self.assertEqual(1, len(itens))
        dados = itens[0]["features"]["gol_ft_tendencia_mais_um"]
        self.assertEqual(1.44, dados["odd_minima_disparo"])
        self.assertEqual(1, dados["cartoes_vermelhos_antes_entrada"])

    def test_rejeita_times_pouco_ofensivos_mesmo_com_odds_e_h2h(self):
        contexto = _contexto()
        contexto["confrontos_diretos"] = {
            "jogos": 10, "media_gols": 2.0,
        }
        recentes = contexto["capacidade_times_v2"]["recentes"]
        for lado in ("mandante", "visitante"):
            recentes[lado]["mando"].update({
                "marcou_taxa": 0.60,
                "gols_pro_media": 1.10,
            })
        recentes["visitante"]["mando"].update({
            "marcou_taxa": 0.625,
            "gols_pro_media": 1.1929,
        })
        self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
            {"status": "59'", "placar": "0-0"},
            [_candidato()], contexto, _qualidade(),
        ))

    def test_rejeita_sem_atividade_recente_mesmo_com_historico_forte(self):
        candidato = _candidato()
        candidato["features"]["janelas"]["5"].update({
            "chutes_total": 0,
            "pressao_pico": [58, 47],
        })
        self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
            {"status": "59'", "placar": "0-0"},
            [candidato], _contexto(), _qualidade(),
        ))

    def test_apoio_historico_deve_corresponder_a_linha_atual(self):
        contexto = _contexto()
        for lado in ("mandante", "visitante"):
            contexto["tendencia_linhas_gols_v1"]["recentes"][lado]["geral"][
                "over_2_5_taxa"
            ] = 0.30
            contexto["tendencia_linhas_gols_v1"]["recentes"][lado]["mando"][
                "over_2_5_taxa"
            ] = 0.25
        # Over 1,5 continua forte, mas já foi cumprido no placar 1-1 e não
        # pode justificar sozinho uma entrada em Over 2,5.
        self.assertEqual([], gerar_gol_ft_tendencia_mais_um(
            {"status": "60'", "placar": "1-1"},
            [_candidato((1, 1))], contexto, _qualidade(),
        ))


if __name__ == "__main__":
    unittest.main()
