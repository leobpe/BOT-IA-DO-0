import os
import unittest
from unittest.mock import patch

from gols_antecipados import (
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
    VERSAO_GOL_HT_ANTECIPADO,
    elegivel_para_enriquecimento_antecipado,
    gerar_gols_antecipados,
)
from diagnostico_gols_antecipados import diagnosticar_gols_antecipados
from telegram_alertas import (
    candidato_gol_antecipado_grupo_teste,
    motivo_suspensao_simulacao,
)


def _contexto():
    return {
        "forma_recente": {
            "mandante": {
                "jogos": 5, "gols_pro_media": 1.5,
                "gols_contra_media": 1.0,
            },
            "visitante": {
                "jogos": 5, "gols_pro_media": 1.4,
                "gols_contra_media": 1.0,
            },
        },
        "confrontos_diretos": {
            "jogos": 4, "media_gols": 2.5, "taxa_over_1_5": 0.75,
        },
        "historico_detalhado": {},
        "estatisticas_temporada": {
            "mandante": {
                "jogos": 12,
                "gols_pro_por_minuto": {
                    "0-15": {"total": 3, "percentual": 20.0},
                    "16-30": {"total": 4, "percentual": 25.0},
                },
                "gols_contra_por_minuto": {},
            },
            "visitante": {
                "jogos": 12,
                "gols_pro_por_minuto": {},
                "gols_contra_por_minuto": {
                    "0-15": {"total": 2, "percentual": 16.0},
                    "16-30": {"total": 3, "percentual": 20.0},
                },
            },
        },
        "previsao_provedor": None,
        "odds_pre_jogo": {"cobertura": {"gols_ft": False}},
        "estatisticas_ao_vivo": {
            "times": {
                "mandante": {"xg": 0.16},
                "visitante": {"xg": 0.08},
            }
        },
    }


def _candidato(mercado):
    return {
        "mercado": mercado,
        "linha": 0.5,
        "odd": 1.70,
        "pontuacao_tecnica": 60,
        "probabilidade_calibrada": None,
        "regra_versao": "sinais-v8b-gol-ht-max28" if mercado == "gol_ht" else "sinais-v6",
        "motivos": [],
        "bloqueios": ["atividade_recente_insuficiente_gols"],
        "qualidade_dados": 90,
        "fonte_odds": "packball",
        "status": "rejeitado",
        "features": {
            "minuto": 12,
            "chutes_no_gol_total": 1,
            "janelas": {
                "5": {
                    "disponivel": True,
                    "chutes_total": 2,
                    "pressao_pico": [70, 55],
                }
            },
        },
    }


class TestGolsAntecipados(unittest.TestCase):
    def test_enriquecimento_sem_candidato_base_aprovado(self):
        self.assertTrue(elegivel_para_enriquecimento_antecipado(
            {"status": "12'", "placar": "0-0"},
            {"pontuacao": 80, "divergencia_critica": False},
        ))

    def test_gera_ht_e_ft_separados_com_contexto_e_live(self):
        diagnostico = {}
        itens = gerar_gols_antecipados(
            {"status": "12'", "placar": "0-0"},
            [_candidato("gol_ht"), _candidato("gol_ft")],
            _contexto(),
            {"pontuacao": 90, "divergencia_critica": False},
        )
        diagnostico = diagnosticar_gols_antecipados(
            {"status": "12'", "placar": "0-0"},
            [_candidato("gol_ht"), _candidato("gol_ft")],
            _contexto(),
            {"pontuacao": 90, "divergencia_critica": False}, itens,
        )
        self.assertEqual(2, len(itens))
        self.assertEqual({"gol_ht", "gol_ft"}, {i["mercado"] for i in itens})
        self.assertTrue(all(i["status"] == "simulacao" for i in itens))
        versoes = {
            i["features"]["exploracao_sombra"]["versao"] for i in itens
        }
        self.assertEqual(
            {VERSAO_GOL_HT_ANTECIPADO, VERSAO_GOL_FT_ANTECIPADO}, versoes
        )
        self.assertTrue(all(
            i["features"]["gol_antecipado"]["xg_ao_vivo_total"] == 0.24
            for i in itens
        ))
        self.assertEqual(
            "gerado",
            diagnostico["por_braco"]["gol_ht_antecipado"]["estado"],
        )
        self.assertEqual(
            "gerado",
            diagnostico["por_braco"]["gol_ft_antecipado_pre_live"][
                "estado"
            ],
        )

    def test_diagnostico_explica_bloqueio_global_e_por_braco(self):
        diagnostico = diagnosticar_gols_antecipados(
            {"status": "12'", "placar": "0-0"}, [], _contexto(),
            {"pontuacao": 90}, [],
        )
        self.assertEqual(
            "candidato_base_ausente",
            diagnostico["por_braco"]["gol_ht_antecipado"]["motivo"],
        )
        self.assertEqual(
            "candidato_base_ausente",
            diagnostico["por_braco"]["gol_ft_antecipado_pre_live"][
                "motivo"
            ],
        )

        gerados = gerar_gols_antecipados(
            {"status": "12'", "placar": "0-0"}, [_candidato("gol_ft")],
            _contexto(), {"pontuacao": 70},
        )
        self.assertEqual([], gerados)
        diagnostico = diagnosticar_gols_antecipados(
            {"status": "12'", "placar": "0-0"}, [_candidato("gol_ft")],
            _contexto(), {
                "pontuacao": 70,
                "completude": 0.6,
                "alertas": ["campos_essenciais_ausentes"],
                "campos_ausentes": ["Chutes no gol", "Índice de pressão"],
            }, gerados,
        )
        self.assertEqual(
            "qualidade_insuficiente",
            diagnostico["por_braco"]["global"]["motivo"],
        )
        self.assertEqual(
            ["Chutes no gol", "Índice de pressão"],
            diagnostico["por_braco"]["global"]["campos_ausentes"],
        )

    def test_diagnostico_separa_janela_ft_da_ht(self):
        candidatos = [_candidato("gol_ht"), _candidato("gol_ft")]
        itens = gerar_gols_antecipados(
            {"status": "27'", "placar": "0-0"}, candidatos,
            _contexto(), {"pontuacao": 90},
        )
        diagnostico = diagnosticar_gols_antecipados(
            {"status": "27'", "placar": "0-0"}, candidatos,
            _contexto(), {"pontuacao": 90}, itens,
        )
        self.assertEqual(["gol_ht"], [item["mercado"] for item in itens])
        self.assertEqual(
            "fora_janela_mercado",
            diagnostico["por_braco"]["gol_ft_antecipado_pre_live"][
                "motivo"
            ],
        )

    def test_ht_historico_continua_ate_28_ft_para_no_25(self):
        candidatos = [_candidato("gol_ht"), _candidato("gol_ft")]
        for item in candidatos:
            item["features"]["minuto"] = 23
        itens = gerar_gols_antecipados(
            {"status": "23'", "placar": "0-0"}, candidatos,
            _contexto(), {"pontuacao": 90},
        )
        self.assertEqual(
            {"gol_ht", "gol_ft"}, {item["mercado"] for item in itens}
        )
        ht = next(item for item in itens if item["mercado"] == "gol_ht")
        self.assertEqual(
            "16-30", ht["features"]["gol_antecipado_ht"]["faixa"]
        )

        for item in candidatos:
            item["features"]["minuto"] = 27
        itens = gerar_gols_antecipados(
            {"status": "27'", "placar": "0-0"}, candidatos,
            _contexto(), {"pontuacao": 90},
        )
        self.assertEqual(["gol_ht"], [item["mercado"] for item in itens])

    def test_ht_exige_faixa_historica_e_para_depois_do_28(self):
        contexto = _contexto()
        contexto["estatisticas_temporada"] = {}
        self.assertEqual([], gerar_gols_antecipados(
            {"status": "12'", "placar": "0-0"},
            [_candidato("gol_ht")], contexto, {"pontuacao": 90},
        ))
        candidato = _candidato("gol_ht")
        candidato["features"]["minuto"] = 29
        self.assertEqual([], gerar_gols_antecipados(
            {"status": "29'", "placar": "0-0"}, [candidato],
            _contexto(), {"pontuacao": 90},
        ))

    def test_gera_ft_antecipado_2t_na_faixa_historica(self):
        contexto = _contexto()
        contexto["estatisticas_temporada"] = {
            "mandante": {
                "jogos": 12,
                "gols_pro_por_minuto": {
                    "46-60": {"total": 4, "percentual": 25.0},
                },
                "gols_contra_por_minuto": {},
            },
            "visitante": {
                "jogos": 12,
                "gols_pro_por_minuto": {},
                "gols_contra_por_minuto": {
                    "46-60": {"total": 3, "percentual": 20.0},
                },
            },
        }
        candidato = _candidato("gol_ft")
        candidato["linha"] = 1.5
        candidato["features"]["minuto"] = 52
        itens = gerar_gols_antecipados(
            {"status": "52'", "placar": "1-0"}, [candidato],
            contexto, {"pontuacao": 90, "divergencia_critica": False},
        )
        self.assertEqual(1, len(itens))
        self.assertEqual(
            VERSAO_GOL_FT_ANTECIPADO_2T,
            itens[0]["features"]["exploracao_sombra"]["versao"],
        )
        self.assertEqual(
            "46-60", itens[0]["features"]["gol_antecipado_2t"]["faixa"]
        )
        self.assertTrue(candidato_gol_antecipado_grupo_teste(itens[0]))

    def test_2t_exige_faixa_historica_e_linha_de_mais_um_gol(self):
        candidato = _candidato("gol_ft")
        candidato["linha"] = 1.5
        self.assertEqual([], gerar_gols_antecipados(
            {"status": "52'", "placar": "1-0"}, [candidato],
            _contexto(), {"pontuacao": 90},
        ))

    def test_2t_usa_faixa_76_90_e_respeita_limite_82(self):
        contexto = _contexto()
        contexto["estatisticas_temporada"] = {
            "mandante": {
                "jogos": 15,
                "gols_pro_por_minuto": {
                    "76-90": {"total": 6, "percentual": 30.0},
                },
                "gols_contra_por_minuto": {},
            },
            "visitante": {
                "jogos": 15,
                "gols_pro_por_minuto": {},
                "gols_contra_por_minuto": {
                    "76-90": {"total": 5, "percentual": 27.0},
                },
            },
        }
        candidato = _candidato("gol_ft")
        candidato["linha"] = 2.5
        candidato["features"]["minuto"] = 78
        itens = gerar_gols_antecipados(
            {"status": "78'", "placar": "1-1"}, [candidato],
            contexto, {"pontuacao": 90},
        )
        self.assertEqual(1, len(itens))
        self.assertEqual(
            "76-90", itens[0]["features"]["gol_antecipado_2t"]["faixa"]
        )
        self.assertEqual(
            3,
            itens[0]["features"]["gol_antecipado_2t"]
            ["evidencias_live_minimas"],
        )
        self.assertEqual([], gerar_gols_antecipados(
            {"status": "83'", "placar": "1-1"}, [candidato],
            contexto, {"pontuacao": 90},
        ))

    def test_bloqueia_placar_odd_contexto_e_cartao(self):
        base = [_candidato("gol_ft")]
        self.assertEqual([], gerar_gols_antecipados(
            {"status": "12'", "placar": "1-0"}, base, _contexto(),
            {"pontuacao": 90},
        ))
        base[0]["odd"] = 1.30
        self.assertEqual([], gerar_gols_antecipados(
            {"status": "12'", "placar": "0-0"}, base, _contexto(),
            {"pontuacao": 90},
        ))
        base = [_candidato("gol_ft")]
        base[0]["bloqueios"].append("cartao_vermelho_reavaliar")
        self.assertEqual([], gerar_gols_antecipados(
            {"status": "12'", "placar": "0-0"}, base, _contexto(),
            {"pontuacao": 90},
        ))
        self.assertEqual([], gerar_gols_antecipados(
            {"status": "12'", "placar": "0-0"}, [_candidato("gol_ft")],
            {}, {"pontuacao": 90},
        ))

    def test_grupo_tem_rollback_por_flag_sem_apagar_sombra(self):
        item = gerar_gols_antecipados(
            {"status": "12'", "placar": "0-0"}, [_candidato("gol_ft")],
            _contexto(), {"pontuacao": 90},
        )[0]
        with patch.dict(os.environ, {"GOLS_ANTECIPADOS_GRUPO_ATIVO": "1"}):
            self.assertTrue(candidato_gol_antecipado_grupo_teste(item))
            self.assertIsNone(motivo_suspensao_simulacao(item))
        with patch.dict(os.environ, {"GOLS_ANTECIPADOS_GRUPO_ATIVO": "0"}):
            self.assertFalse(candidato_gol_antecipado_grupo_teste(item))
            self.assertEqual(
                "exploracao_sombra_fora_allowlist_simulacao_grupo",
                motivo_suspensao_simulacao(item),
            )


if __name__ == "__main__":
    unittest.main()
