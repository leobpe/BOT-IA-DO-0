import unittest

from gol_ht_00_min20 import VERSAO, gerar_gol_ht_00_min20
from telegram_alertas import (
    candidato_gol_ht_00_min20_grupo_teste,
    motivo_suspensao_simulacao,
)


def _candidato(minuto=20, odd=1.80):
    return {
        "mercado": "gol_ht", "linha": 0.5, "odd": odd,
        "status": "rejeitado", "regra_versao": "sinais-v8b-gol-ht-max28",
        "bloqueios": ["atividade_recente_insuficiente_gols"],
        "features": {"minuto": minuto, "janelas": {"5": {
            "disponivel": True, "duracao_real_minutos": 5,
            "chutes": [1, 0], "chutes_total": 1,
            "resets_detectados": [],
        }}},
    }


def _qualidade():
    return {"pontuacao": 90, "campos_ausentes": [], "divergencia_critica": False}


def _contexto_aprovado():
    return {
        "odds_pre_jogo": {"mercados": {"gols_ft": {
            "consenso_suficiente": True, "linha_consenso": 2.5,
        }}},
        "confrontos_diretos": {"jogos": 5, "taxa_ambas_marcam": 0.8},
        "eventos_ao_vivo": {"times": {}},
    }


class GolHT00Min20Test(unittest.TestCase):
    def test_previsao_under_sozinha_nao_aprova_ht(self):
        for valor in ("-3.5", "-2.5", "Under 3.5", "−3,5", "3.5", None):
            with self.subTest(valor=valor):
                self.assertEqual([], gerar_gol_ht_00_min20(
                    {"status": "23'", "placar": "0-0"}, [_candidato(23)],
                    {"previsao_provedor": {"over_under": valor}}, _qualidade()))

    def test_previsao_over_25_preserva_envio(self):
        for valor in ("+2.5", "+3.5", "Over 2.5", "mais de 2,5 gols"):
            with self.subTest(valor=valor):
                itens = gerar_gol_ht_00_min20(
                    {"status": "23'", "placar": "0-0"}, [_candidato(23)],
                    {"previsao_provedor": {"over_under": valor},
                     "confrontos_diretos": {"jogos": 5, "taxa_ambas_marcam": 0.8}},
                    _qualidade())
                self.assertEqual(1, len(itens))
                self.assertEqual(["previsao_provedor_over25"], itens[0]["features"]["gol_ht_00_min20"]["evidencias_over25"])

    def test_under_nao_cumpre_apoio_over_mesmo_com_btts(self):
        self.assertEqual([], gerar_gol_ht_00_min20(
            {"status": "23'", "placar": "0-0"}, [_candidato(23)],
            {"previsao_provedor": {"over_under": "-3.5"},
             "confrontos_diretos": {"jogos": 5, "taxa_ambas_marcam": 0.8}},
            _qualidade()))

    def test_faixas_dos_times_nao_sao_medias(self):
        for esperado in ({"home": "+1.5", "away": "+1.5"}, {"home": 3, "away": None}, {"home": "+5.5", "away": "-1.5"}):
            self.assertEqual([], gerar_gol_ht_00_min20(
                {"status": "23'", "placar": "0-0"}, [_candidato(23)],
                {"previsao_provedor": {"gols_esperados": esperado}}, _qualidade()))

    def test_over25_libera_na_janela(self):
        contexto = _contexto_aprovado()
        itens = gerar_gol_ht_00_min20(
            {"status": "20'", "placar": "0-0"}, [_candidato()], contexto, _qualidade()
        )
        self.assertEqual(1, len(itens))
        self.assertEqual(VERSAO, itens[0]["features"]["exploracao_sombra"]["versao"])
        self.assertTrue(candidato_gol_ht_00_min20_grupo_teste(itens[0]))
        self.assertIsNone(motivo_suspensao_simulacao(itens[0]))

    def test_btts_sozinho_nao_libera(self):
        contexto = {
            "confrontos_diretos": {"jogos": 5, "taxa_ambas_marcam": 0.8},
            "eventos_ao_vivo": {"times": {}},
        }
        self.assertEqual([], gerar_gol_ht_00_min20(
            {"status": "24'", "placar": "0-0"}, [_candidato(24)], contexto, _qualidade()
        ))

    def test_over25_sozinho_nao_libera(self):
        contexto = _contexto_aprovado()
        contexto.pop("confrontos_diretos")
        self.assertEqual([], gerar_gol_ht_00_min20(
            {"status": "24'", "placar": "0-0"}, [_candidato(24)],
            contexto, _qualidade(),
        ))

    def test_exige_janela_5min_valida_e_ao_menos_um_chute(self):
        contexto = _contexto_aprovado()
        alteracoes_invalidas = (
            {"disponivel": False},
            {"disponivel": True, "duracao_real_minutos": 4.9,
             "chutes": [1, 0], "chutes_total": 1, "resets_detectados": []},
            {"disponivel": True, "duracao_real_minutos": 5,
             "chutes": [0, 0], "chutes_total": 0, "resets_detectados": []},
            {"disponivel": True, "duracao_real_minutos": 5,
             "chutes": [1, 0], "chutes_total": 2, "resets_detectados": []},
            {"disponivel": True, "duracao_real_minutos": 5,
             "chutes": [1, 0], "chutes_total": 1, "resets_detectados": ["chutes"]},
        )
        for janela in alteracoes_invalidas:
            with self.subTest(janela=janela):
                candidato = _candidato(24)
                candidato["features"]["janelas"]["5"] = janela
                self.assertEqual([], gerar_gol_ht_00_min20(
                    {"status": "24'", "placar": "0-0"}, [candidato],
                    contexto, _qualidade(),
                ))

    def test_janela_api_fundida_nao_e_tratada_como_packball(self):
        candidato = _candidato(24)
        candidato["features"]["fusao_temporal_api_live"] = {
            "preenchimentos": ["5.chutes"]
        }
        self.assertEqual([], gerar_gol_ht_00_min20(
            {"status": "24'", "placar": "0-0"}, [candidato],
            _contexto_aprovado(), _qualidade(),
        ))

    def test_exige_00_minuto_linha_odd_e_qualidade(self):
        contexto = _contexto_aprovado()
        for jogo, candidato, qualidade in (
            ({"status": "19'", "placar": "0-0"}, _candidato(19), _qualidade()),
            ({"status": "29'", "placar": "0-0"}, _candidato(29), _qualidade()),
            ({"status": "22'", "placar": "1-0"}, _candidato(22), _qualidade()),
            ({"status": "22'", "placar": "0-0"}, {**_candidato(22), "linha": 1.5}, _qualidade()),
            ({"status": "22'", "placar": "0-0"}, _candidato(22, 1.43), _qualidade()),
            ({"status": "22'", "placar": "0-0"}, _candidato(22), {"pontuacao": 70, "campos_ausentes": []}),
        ):
            self.assertEqual([], gerar_gol_ht_00_min20(jogo, [candidato], contexto, qualidade))

    def test_odd_144_e_aceita(self):
        contexto = _contexto_aprovado()
        itens = gerar_gol_ht_00_min20(
            {"status": "22'", "placar": "0-0"},
            [_candidato(22, 1.44)], contexto, _qualidade(),
        )
        self.assertEqual(1, len(itens))
        self.assertEqual(
            1.44, itens[0]["features"]["gol_ht_00_min20"]["odd_minima_disparo"]
        )

    def test_vermelho_nao_bloqueia_e_fica_registrado(self):
        contexto = _contexto_aprovado()
        contexto["eventos_ao_vivo"] = {
            "times": {"mandante": {"cartoes_vermelhos": 1}}
        }
        itens = gerar_gol_ht_00_min20(
            {"status": "22'", "placar": "0-0"}, [_candidato(22)], contexto, _qualidade()
        )
        self.assertEqual(1, len(itens))
        self.assertEqual(
            1,
            itens[0]["features"]["gol_ht_00_min20"]
            ["cartoes_vermelhos_antes_entrada"],
        )
        self.assertFalse(
            itens[0]["features"]["gol_ht_00_min20"]
            ["cartao_vermelho_bloqueia"]
        )


if __name__ == "__main__":
    unittest.main()
