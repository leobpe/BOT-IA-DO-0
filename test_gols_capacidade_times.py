import os
import unittest
from unittest.mock import patch

from gols_capacidade_times import (
    LINHAGEM_GOLS_CAPACIDADE,
    VERSAO_GOL_FT_CAPACIDADE,
    VERSAO_GOL_HT_CAPACIDADE,
    elegivel_para_enriquecimento_capacidade,
    gerar_gols_capacidade_times,
)
from telegram_alertas import (
    candidato_gol_capacidade_grupo_teste,
    motivo_suspensao_simulacao,
)


def _distribuicao():
    return {
        "0-15": {"percentual": 12.0},
        "16-30": {"percentual": 18.0},
        "31-45": {"percentual": 20.0},
        "46-60": {"percentual": 18.0},
        "61-75": {"percentual": 17.0},
        "76-90": {"percentual": 15.0},
    }


def _contexto(forte=True):
    pro = 2.4 if forte else 0.7
    contra = 1.7 if forte else 0.6
    return {
        "forma_recente": {
            "mandante": {
                "jogos": 5, "gols_pro_media": pro,
                "gols_contra_media": contra,
            },
            "visitante": {
                "jogos": 5, "gols_pro_media": pro,
                "gols_contra_media": contra,
            },
        },
        "historico_detalhado": {
            "mandante": {
                "jogos": 10, "gols_pro_media": pro,
                "gols_contra_media": contra,
            },
            "visitante": {
                "jogos": 10, "gols_pro_media": pro,
                "gols_contra_media": contra,
            },
        },
        "estatisticas_temporada": {
            "mandante": {
                "jogos": 20, "gols_pro_media": pro,
                "gols_contra_media": contra,
                "gols_pro_por_minuto": _distribuicao(),
                "gols_contra_por_minuto": _distribuicao(),
            },
            "visitante": {
                "jogos": 20, "gols_pro_media": pro,
                "gols_contra_media": contra,
                "gols_pro_por_minuto": _distribuicao(),
                "gols_contra_por_minuto": _distribuicao(),
            },
        },
        "confrontos_diretos": {
            "jogos": 5, "media_gols": 3.5 if forte else 1.2,
        },
        "estatisticas_ao_vivo": {"times": {}},
    }


def _candidato(mercado, minuto=20, linha=0.5, odd=1.80, pressao=35):
    return {
        "mercado": mercado,
        "linha": linha,
        "odd": odd,
        "pontuacao_tecnica": 55.0,
        "probabilidade_calibrada": None,
        "regra_versao": (
            "sinais-v8b-gol-ht-max28" if mercado == "gol_ht"
            else "sinais-v6"
        ),
        "motivos": [],
        "bloqueios": ["atividade_recente_insuficiente_gols"],
        "qualidade_dados": 90.0,
        "fonte_odds": "packball",
        "status": "rejeitado",
        "features": {
            "minuto": minuto,
            "chutes_no_gol_total": 0,
            "janelas": {
                "5": {
                    "disponivel": True,
                    "chutes_total": 0,
                    "pressao_pico": [pressao, 20],
                }
            },
        },
    }


class TestGolsCapacidadeTimes(unittest.TestCase):
    def test_capacidade_gera_com_pressao_baixa_observada(self):
        candidatos = [_candidato("gol_ht"), _candidato("gol_ft")]
        itens = gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"}, candidatos,
            _contexto(), {
                "pontuacao": 90, "campos_ausentes": [],
                "divergencia_critica": False,
            },
        )
        self.assertEqual({"gol_ht", "gol_ft"}, {x["mercado"] for x in itens})
        self.assertTrue(all(x["status"] == "simulacao" for x in itens))
        self.assertEqual(
            {VERSAO_GOL_HT_CAPACIDADE, VERSAO_GOL_FT_CAPACIDADE},
            {
                x["features"]["exploracao_sombra"]["versao"]
                for x in itens
            },
        )
        for item in itens:
            dados = item["features"]["gol_capacidade_times"]
            self.assertEqual(LINHAGEM_GOLS_CAPACIDADE, dados["linhagem_sha256"])
            self.assertFalse(dados["pressao_ausente"])
            self.assertLess(dados["pico_pressao_observado"], 50)
        self.assertEqual("rejeitado", candidatos[0]["status"])

    def test_dado_ausente_nao_e_confundido_com_pressao_baixa(self):
        qualidade = {
            "pontuacao": 90,
            "campos_ausentes": ["Índice de pressão"],
            "divergencia_critica": False,
        }
        self.assertFalse(elegivel_para_enriquecimento_capacidade(
            {"status": "20'", "placar": "0-0"}, qualidade,
            [_candidato("gol_ft")],
        ))
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"},
            [_candidato("gol_ft")], _contexto(), qualidade,
        ))

    def test_time_fraco_sem_vantagem_na_odd_nao_gera(self):
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"},
            [_candidato("gol_ft", odd=1.50)], _contexto(forte=False),
            {"pontuacao": 90, "campos_ausentes": []},
        ))

    def test_exige_linha_de_mais_um_gol_e_odd_operacional(self):
        qualidade = {"pontuacao": 90, "campos_ausentes": []}
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "20'", "placar": "1-0"},
            [_candidato("gol_ft", linha=0.5)], _contexto(), qualidade,
        ))
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"},
            [_candidato("gol_ft", odd=1.20)], _contexto(), qualidade,
        ))

    def test_respeita_minutos_finais_e_divergencia_critica(self):
        qualidade = {"pontuacao": 90, "campos_ausentes": []}
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "29'", "placar": "0-0"},
            [_candidato("gol_ht", minuto=29)], _contexto(), qualidade,
        ))
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "83'", "placar": "0-0"},
            [_candidato("gol_ft", minuto=83)], _contexto(), qualidade,
        ))
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"},
            [_candidato("gol_ft")], _contexto(), {
                **qualidade, "divergencia_critica": True,
            },
        ))

    def test_bloqueio_estranho_nao_e_relaxado(self):
        candidato = _candidato("gol_ft")
        candidato["bloqueios"].append("cartao_vermelho_reavaliar")
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"}, [candidato],
            _contexto(), {"pontuacao": 90, "campos_ausentes": []},
        ))

    def test_nao_duplica_regra_ativa_ja_aprovada(self):
        candidato = _candidato("gol_ft")
        candidato["status"] = "aprovado"
        candidato["bloqueios"] = []
        self.assertEqual([], gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"}, [candidato],
            _contexto(), {"pontuacao": 90, "campos_ausentes": []},
        ))

    def test_flag_desliga_somente_envio_sem_apagar_coleta(self):
        with patch.dict(os.environ, {"GOLS_CAPACIDADE_TIMES_GRUPO_ATIVO": "0"}):
            item = gerar_gols_capacidade_times(
                {"status": "20'", "placar": "0-0"},
                [_candidato("gol_ft")], _contexto(),
                {"pontuacao": 90, "campos_ausentes": []},
            )[0]
        self.assertFalse(
            item["features"]["exploracao_sombra"]["grupo_teste"]
        )

    def test_allowlist_telegram_tem_rollback_imediato(self):
        item = gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"},
            [_candidato("gol_ft")], _contexto(),
            {"pontuacao": 90, "campos_ausentes": []},
        )[0]
        with patch.dict(os.environ, {"GOLS_CAPACIDADE_TIMES_GRUPO_ATIVO": "1"}), patch(
            "telegram_alertas.GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO", True
        ):
            self.assertTrue(candidato_gol_capacidade_grupo_teste(item))
            self.assertIsNone(motivo_suspensao_simulacao(item))
        with patch.dict(os.environ, {"GOLS_CAPACIDADE_TIMES_GRUPO_ATIVO": "0"}):
            self.assertFalse(candidato_gol_capacidade_grupo_teste(item))
            self.assertEqual(
                "exploracao_sombra_fora_allowlist_simulacao_grupo",
                motivo_suspensao_simulacao(item),
            )

    def test_bracos_v1_negativos_ficam_em_sombra_com_rollback_separado(self):
        ht = gerar_gols_capacidade_times(
            {"status": "20'", "placar": "0-0"},
            [_candidato("gol_ht")], _contexto(),
            {"pontuacao": 90, "campos_ausentes": []},
        )[0]
        ft = gerar_gols_capacidade_times(
            {"status": "55'", "placar": "0-0"},
            [_candidato("gol_ft")], _contexto(),
            {"pontuacao": 90, "campos_ausentes": []},
        )[0]
        self.assertFalse(candidato_gol_capacidade_grupo_teste(ht))
        self.assertFalse(candidato_gol_capacidade_grupo_teste(ft))

        with patch("telegram_alertas.GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO", True):
            self.assertTrue(candidato_gol_capacidade_grupo_teste(ht))
        with patch("telegram_alertas.GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO", True):
            self.assertTrue(candidato_gol_capacidade_grupo_teste(ft))


if __name__ == "__main__":
    unittest.main()
