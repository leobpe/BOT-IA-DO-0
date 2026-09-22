import copy
import unittest
from unittest.mock import patch

from acompanhamento_metodos_gols import (
    CHAVE, gerar_acompanhamentos_metodos_gols, revalidar_metodo_acompanhado,
)
from acompanhamento_odd import preparar_acompanhamento_odd, finalizar_acompanhamento_odd
from gol_ht_00_min20 import gerar_gol_ht_00_min20, VERSAO as HT
from gols_capacidade_contextual_v2 import gerar_gols_capacidade_contextual_v2, VERSAO_GOL_FT
from protecao_conversao_gols import aplicar_protecao_conversao_gols
from telegram_alertas import AlertasTelegram
from tendencias_packball_ligas import aplicar_protecao_tendencias_packball
from test_gol_ht_00_min20 import _candidato as base_ht, _qualidade as qualidade_ht
from test_gols_capacidade_contextual_v2 import _candidato as base_ft, _contexto as contexto_ft, _qualidade as qualidade_ft
from test_tendencias_packball_ligas import _time, _contexto as contexto_packball


def contexto_ht():
    taxas = {"jogos": 15, "jogos_ht": 15, "ht_over_0_5_taxa": 0.8}
    return {
        "odds_pre_jogo": {"mercados": {"gols_ft": {
            "consenso_suficiente": True, "linha_consenso": 2.5,
        }}},
        "confrontos_diretos": {"jogos": 5, "taxa_ambas_marcam": 0.8},
        "eventos_ao_vivo": {"times": {}},
        "tendencia_linhas_gols_v1": {"recentes": {
            lado: {"geral": dict(taxas), "mando": dict(taxas)}
            for lado in ("mandante", "visitante")
        }},
    }


def preparar_ht_com_protecoes(alertas, jogo):
    itens = gerar_acompanhamentos_metodos_gols(
        jogo, [base_ht(odd=1.22)], contexto_ht(), qualidade_ht(), alertas,
    )
    itens = [x for x in itens if x["features"][CHAVE]["metodo"] == HT]
    preparar_acompanhamento_odd(itens)
    aplicar_protecao_conversao_gols(itens, contexto_ht())
    aplicar_protecao_tendencias_packball(itens, contexto_packball(
        _time(jogo["mandante"], 0.5, 0.8),
        _time(jogo["visitante"], 0.5, 0.8), "1t",
    ), jogo)
    finalizar_acompanhamento_odd(itens, fontes_saudaveis=True)
    return itens


class AcompanhamentoMetodosGolsTest(unittest.TestCase):
    def setUp(self):
        ambiente = patch.dict("os.environ", {
            "AVISO_AGUARDAR_ODD_ATIVO": "1", "AVISO_AGUARDAR_ODD_ALVO": "1.40",
            "AVISO_AGUARDAR_ODD_MERCADOS": "gol_ft,gol_ht,proximo_gol",
            "ACOMPANHAMENTO_METODOS_GOLS_ATIVO": "1", "ODD_MINIMA_SINAL": "1.40",
        })
        ambiente.start()
        self.addCleanup(ambiente.stop)
        ativo = patch("telegram_alertas.GOL_HT_00_MIN20_GRUPO_ATIVO", True)
        ativo.start()
        self.addCleanup(ativo.stop)
        self.alertas = AlertasTelegram.__new__(AlertasTelegram)
        self.alertas.modo_teste = True
        self.alertas.pontuacao_minima_teste = 70
        self.alertas.qualidade_minima_teste = 80
        self.jogo = {"mandante": "Casa FC", "visitante": "Fora FC", "status": "20'", "placar": "0-0", "minuto": 20}

    def gerar_ht(self, base=None, contexto=None):
        return gerar_acompanhamentos_metodos_gols(
            self.jogo, [base if base is not None else base_ht(odd=1.22)],
            contexto if contexto is not None else contexto_ht(), qualidade_ht(), self.alertas,
        )

    def test_ht_preserva_odd_real_e_nao_consume_coorte(self):
        base = base_ht(odd=1.22)
        original = copy.deepcopy(base)
        itens = self.gerar_ht(base)
        self.assertEqual(base, original)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["odd"], 1.22)
        self.assertEqual(item["status"], "rejeitado")
        self.assertIsNone(item["probabilidade_calibrada"])
        self.assertNotIn("exploracao_sombra", item["features"])
        self.assertEqual(item["features"][CHAVE]["odd_alvo"], 1.44)
        preparar_acompanhamento_odd(itens)
        self.assertEqual(item["features"]["acompanhamento_odd"]["odd_alvo"], 1.44)
        finalizar_acompanhamento_odd(itens, fontes_saudaveis=True)
        self.assertFalse(item["features"]["acompanhamento_odd"]["elegivel_aviso"])

    def test_mesmas_protecoes_historicas_sao_obrigatorias(self):
        item = preparar_ht_com_protecoes(self.alertas, self.jogo)[0]
        self.assertTrue(item["features"]["acompanhamento_odd"]["elegivel_aviso"])
        self.assertEqual(item["status"], "rejeitado")
        self.assertNotIn("exploracao_sombra", item["features"])

    def test_preco_atingido_refaz_exatamente_o_mesmo_ht(self):
        item = self.gerar_ht()[0]
        jogo = {**self.jogo, "status": "23'", "minuto": 23}
        convertido, motivo = revalidar_metodo_acompanhado(
            item["features"], jogo, contexto_ht(), qualidade_ht(),
            {"odd": 1.50}, self.alertas, 30,
        )
        base = base_ht(minuto=23, odd=1.50)
        esperado = gerar_gol_ht_00_min20(jogo, [base], contexto_ht(), qualidade_ht())[0]
        esperado["qualidade_dados"] = 90
        self.assertIsNone(motivo)
        self.assertEqual(convertido, esperado)
        self.assertEqual(item["odd"], 1.22)

    def test_140_nao_contorna_minimo_144_do_ht(self):
        _, motivo = revalidar_metodo_acompanhado(
            self.gerar_ht()[0]["features"], self.jogo, contexto_ht(), qualidade_ht(),
            {"odd": 1.40}, self.alertas, 10,
        )
        self.assertEqual(motivo, "odd_alvo_do_metodo_nao_atingida")

    def test_minuto_limite_e_leitura_vencida_nao_enviam(self):
        features = self.gerar_ht()[0]["features"]
        for minuto, idade, motivo_esperado in (
            (29, 10, "criterios_do_metodo_nao_confirmados_na_odd_atual"),
            (22, 121, "leitura_recente_do_metodo_precisa_renovacao"),
        ):
            _, motivo = revalidar_metodo_acompanhado(
                features, {**self.jogo, "status": f"{minuto}'", "minuto": minuto},
                contexto_ht(), qualidade_ht(), {"odd": 1.44}, self.alertas, idade,
            )
            self.assertEqual(motivo, motivo_esperado)

    def test_desativacao_e_rollback_nao_reativam_metodos(self):
        item = self.gerar_ht()[0]
        with patch("telegram_alertas.GOL_HT_00_MIN20_GRUPO_ATIVO", False):
            self.assertEqual(self.gerar_ht(), [])
            _, motivo = revalidar_metodo_acompanhado(item["features"], self.jogo,
                contexto_ht(), qualidade_ht(), {"odd": 1.44}, self.alertas, 10)
            self.assertIsNotNone(motivo)
        with patch.dict("os.environ", {"ACOMPANHAMENTO_METODOS_GOLS_ATIVO": "0"}):
            self.assertEqual(self.gerar_ht(), [])

    def test_dados_ou_bloqueios_tecnicos_nao_sao_removidos(self):
        base = base_ht(odd=1.22)
        base["bloqueios"].append("placar_divergente_entre_fontes")
        self.assertEqual(self.gerar_ht(base), [])
        self.assertEqual(self.gerar_ht(contexto={}), [])
        self.assertEqual(self.gerar_ht(base_ht(odd=1.05)), [])
        self.assertEqual(self.gerar_ht(base_ht(odd=1.60)), [])

    def test_ft_recalcula_probabilidade_e_edge_por_tempo_restante(self):
        contexto = contexto_ft()
        qualidade = qualidade_ft()
        jogo = {**self.jogo, "status": "40'", "minuto": 40, "liga": "Serie A"}
        base = base_ft(minuto=40, odd=1.22)
        itens = gerar_acompanhamentos_metodos_gols(jogo, [base], contexto, qualidade, self.alertas)
        item = next(x for x in itens if x["features"][CHAVE]["metodo"] == VERSAO_GOL_FT)
        jogo.update({"status": "41'", "minuto": 41})
        resultado, motivo = revalidar_metodo_acompanhado(
            item["features"], jogo, contexto, qualidade, {"odd": 1.50}, self.alertas, 40,
        )
        esperado = gerar_gols_capacidade_contextual_v2(
            jogo, [base_ft(minuto=41, odd=1.50)], contexto, qualidade,
        )[0]
        self.assertIsNone(motivo)
        campo = "gol_capacidade_contextual_v2"
        self.assertEqual(resultado["features"][campo], esperado["features"][campo])
        self.assertNotEqual(resultado["features"][campo], item["features"][campo])
        self.assertIsNone(resultado["probabilidade_calibrada"])

    def test_alteracao_de_linhagem_exige_nova_leitura(self):
        item = self.gerar_ht()[0]
        item["features"][CHAVE]["linhagens"] = {"gol_ht_00_min20": "antiga"}
        _, motivo = revalidar_metodo_acompanhado(item["features"], self.jogo,
            contexto_ht(), qualidade_ht(), {"odd": 1.44}, self.alertas, 10)
        self.assertEqual(motivo, "linhagem_do_metodo_alterada")

    def test_preco_condicional_nao_contorna_movimento_adverso_do_v2(self):
        base = base_ft(minuto=40, odd=1.30)
        base["features"]["movimento_gols"] = {
            "odd_anterior": 1.20, "odd_atual": 1.30,
            "delta": 0.10, "direcao": "alta",
        }
        itens = gerar_acompanhamentos_metodos_gols(
            {**self.jogo, "status": "40'"}, [base], contexto_ft(), qualidade_ft(), self.alertas,
        )
        self.assertNotIn(VERSAO_GOL_FT, [x["features"][CHAVE]["metodo"] for x in itens])


if __name__ == "__main__":
    unittest.main()
