import copy
import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from probabilidade_individual import (
    FEATURES, ajustar, ajustar_v2, carregar_base, extrair_entrada, prever,
    prever_v2, validar_e_ajustar, validar_walk_forward_v2,
)


def exemplo(i=1, mercado="gol_ht"):
    ctx = {"historico_detalhado": {
        "mandante": {"jogos": 10, "gols_pro_media": 1.8, "gols_contra_media": .7},
        "visitante": {"jogos": 10, "gols_pro_media": 1.2, "gols_contra_media": 1.5}}}
    sinal = {"id": i, "partida_id": i, "mercado": mercado, "linha": .5, "odd": 1.7,
             "regra_versao": "metodo-v1", "regra_fingerprint": "fp-v1",
             "criado_em": "2026-09-01T12:00:00",
             "features": {"minuto": 25, "janelas": {"5": {
                 "disponivel": True, "duracao_real_minutos": 5,
                 "chutes_total": 3, "pressao_pico": [60, 30]}}}}
    snapshot = {"placar": "0-0", "contexto_api_json": ctx, "coletado_em": "2026-09-01T11:59:59"}
    jogo = {"mandante": "A", "visitante": "B", "liga": "Campeonato"}
    return sinal, snapshot, jogo


def sinteticos(n=140):
    itens = []
    for i in range(n):
        s, t, j = exemplo(i + 1)
        s["features"]["minuto"] = 10 + i % 30
        item = extrair_entrada(s, t, j)
        item["valores"]["ataque_casa_defesa_fora"] = 0.7 + (i % 13) / 5
        item["valores"]["ataque_fora_defesa_casa"] = 0.9 + (i % 7) / 5
        item["alvo"] = int(i % 30 < 17)
        item["criado_em"] = (datetime(2026, 1, 1) + timedelta(days=i)).isoformat()
        item["encerrado_em"] = (datetime(2026, 1, 1, 2) + timedelta(days=i)).isoformat()
        itens.append(item)
    return itens


class ExtracaoIndividualTest(unittest.TestCase):
    def test_tempo_linha_placar_e_cruzamento_ataque_defesa(self):
        s, t, j = exemplo()
        r = extrair_entrada(s, t, j)
        self.assertEqual(r["valores"]["tempo_restante"], 20)
        self.assertEqual(r["valores"]["gols_necessarios"], 1)
        self.assertAlmostEqual(r["valores"]["ataque_casa_defesa_fora"], 1.65)
        s.update(mercado="gol_ft", linha=3.5)
        s["features"]["minuto"] = 70
        t["placar"] = "1-1"
        r = extrair_entrada(s, t, j)
        self.assertEqual(r["valores"]["gols_necessarios"], 2)
        self.assertEqual(r["valores"]["tempo_restante"], 20)

    def test_nota_nao_entra_no_modelo(self):
        s, t, j = exemplo()
        r = extrair_entrada(s, t, j)
        s["pontuacao_tecnica"] = 100
        s["probabilidade_calibrada"] = .99
        self.assertEqual(r, extrair_entrada(s, t, j))

    def test_sem_perfis_nao_estima_so_com_odd_e_relogio(self):
        s, t, j = exemplo()
        t["contexto_api_json"] = {}
        self.assertIsNone(extrair_entrada(s, t, j))

    def test_nao_confunde_chutes_xg_ausentes_com_zero_ou_acumulados(self):
        s, t, j = exemplo()
        s["features"]["janelas"]["5"]["disponivel"] = False
        s["features"]["chutes_no_gol_total"] = 50
        t["contexto_api_json"]["estatisticas_ao_vivo"] = {"xg": [2, 2]}
        r = extrair_entrada(s, t, j)
        self.assertIsNone(r["valores"]["chutes_5min"])
        self.assertIsNone(r["valores"]["pressao_5min"])
        self.assertIsNone(r["valores"]["xg_5min"])
        self.assertIsNone(r["valores"]["vermelhos"])

    def test_duracao_real_janela_e_limites(self):
        s, t, j = exemplo()
        s["features"]["janelas"]["5"]["duracao_real_minutos"] = 7.5
        self.assertEqual(extrair_entrada(s, t, j)["valores"]["chutes_5min"], 2)
        s["features"]["janelas"]["5"]["duracao_real_minutos"] = 12
        self.assertIsNone(extrair_entrada(s, t, j)["valores"]["chutes_5min"])

    def test_zero_xg_confirmado_permanece_zero(self):
        s, t, j = exemplo()
        t["contexto_api_json"]["evolucao_temporal_api_live"] = {
            "5": {"duracao_real_minutos": 5, "xg": [0, 0]}}
        self.assertEqual(extrair_entrada(s, t, j)["valores"]["xg_5min"], 0)

    def test_mercado_ou_linha_incompativel_nao_reaproveita_probabilidade(self):
        for atualizacao in ({"mercado": "under_gol_ht"}, {"linha": 1}, {"odd": True}, {"odd": float("nan")}):
            s, t, j = exemplo()
            s.update(atualizacao)
            self.assertIsNone(extrair_entrada(s, t, j))
        s, t, j = exemplo()
        s["features"]["minuto"] = 55
        self.assertIsNone(extrair_entrada(s, t, j))

    def test_media_do_mando_preferida_sem_usar_temporada_de_um_jogo(self):
        s, t, j = exemplo()
        recente = {"geral": {"jogos": 15, "gols_pro_media": 1, "gols_contra_media": 1},
                   "mando": {"jogos": 5, "gols_pro_media": 2, "gols_contra_media": 1}}
        t["contexto_api_json"]["capacidade_times_v2"] = {
            "recentes": {"mandante": recente, "visitante": recente},
            "temporada_mando": {"mandante": {"jogos": 1, "gols_pro_media": 15}}}
        self.assertEqual(extrair_entrada(s, t, j)["valores"]["ataque_casa_defesa_fora"], 1.5)


class TreinoIndividualTest(unittest.TestCase):
    def test_probabilidade_muda_com_dados_da_entrada(self):
        registros = sinteticos()
        m = ajustar(registros)
        cedo = copy.deepcopy(registros[0])
        tarde = copy.deepcopy(cedo)
        cedo["valores"]["tempo_restante"] = 35
        tarde["valores"]["tempo_restante"] = 6
        self.assertGreater(prever(m, cedo), prever(m, tarde))
        self.assertTrue(0 < prever(m, cedo) < 1)

    def test_treino_insuficiente_e_classe_unica_nao_geram_modelo(self):
        with self.assertRaises(ValueError):
            ajustar(sinteticos(20))
        rs = sinteticos(100)
        for x in rs:
            x["alvo"] = 1
        with self.assertRaises(ValueError):
            ajustar(rs)

    def test_ausencia_nao_e_conversao_para_xg_zero(self):
        m = ajustar(sinteticos())
        self.assertNotIn("xg_5min", m["features"])
        self.assertNotIn("vermelhos", m["features"])

    def test_validacao_posterior_nao_passa_resultados_futuros_ao_treino(self):
        rs = sinteticos(140)
        rs[20]["encerrado_em"] = "2099-01-01T00:00:00"
        original = ajustar
        chamadas = []
        def registrar(registros):
            chamadas.append([x["sinal_id"] for x in registros])
            return original(registros)
        with patch("probabilidade_individual.ajustar", side_effect=registrar):
            r = validar_e_ajustar(rs, "gol_ht", "2026-09-02T12:00:00")
        self.assertNotIn(rs[20]["sinal_id"], chamadas[0])
        self.assertFalse(set(chamadas[0]) & set(r["validacao"]["sinais"]))
        self.assertFalse(r["validacao"]["calibracao_comprovada"])

    def test_modelo_mal_validado_nao_e_liberado(self):
        rs = sinteticos()
        for x in rs[-30:]:
            x["alvo"] = 0
        r = validar_e_ajustar(rs, "gol_ht", "2026-09-02T12:00:00")
        self.assertIsNone(r["modelo"])
        self.assertEqual(r["estado"], "validacao_inicial_insuficiente")

    def test_v2_usa_odd_como_offset_e_contexto_muda_probabilidade(self):
        registros = sinteticos(180)
        modelo = ajustar_v2(registros[:120])
        cedo = copy.deepcopy(registros[150])
        tarde = copy.deepcopy(cedo)
        cedo["valores"]["tempo_restante"] = 35
        tarde["valores"]["tempo_restante"] = 5
        self.assertGreater(prever_v2(modelo, cedo), prever_v2(modelo, tarde))
        cedo["odd"] = 1.5
        probabilidade_odd_baixa = prever_v2(modelo, cedo)
        cedo["odd"] = 2.0
        self.assertLess(prever_v2(modelo, cedo), probabilidade_odd_baixa)

    def test_v2_walk_forward_nao_vaza_validacao_no_treino(self):
        registros = sinteticos(200)
        original = ajustar_v2
        chamadas = []

        def registrar(itens):
            chamadas.append([item["sinal_id"] for item in itens])
            return original(itens)

        with patch("probabilidade_individual.ajustar_v2", side_effect=registrar):
            resultado = validar_walk_forward_v2(
                registros, "gol_ht", "2026-09-02T12:00:00"
            )
        self.assertEqual(len(resultado["folds"]), 3)
        for indice, fold in enumerate(resultado["folds"]):
            self.assertFalse(set(chamadas[indice]) & set(fold["sinais"]))
            self.assertLess(
                max(chamadas[indice]), min(fold["sinais"])
            )

    def test_v2_nao_aprova_se_nao_superar_a_odd(self):
        registros = sinteticos(200)
        # Resultado artificial que acompanha exatamente o preço constante,
        # sem padrão contextual estável que o challenger possa explorar.
        for indice, item in enumerate(registros):
            item["alvo"] = int(indice % 5 < 3)
            item["valores"]["tempo_restante"] = 20 + (indice % 2)
            item["valores"]["ataque_casa_defesa_fora"] = 1 + (indice % 3) / 10
            item["valores"]["ataque_fora_defesa_casa"] = 1 + (indice % 4) / 10
        resultado = validar_walk_forward_v2(
            registros, "gol_ht", "2026-09-02T12:00:00"
        )
        self.assertEqual(resultado["estado"], "validacao_reprovada")
        self.assertFalse(resultado["aprovado_para_coorte_prospectiva"])
        self.assertIsNone(resultado["modelo"])

    def test_v2_amostra_minima_exige_tres_folds_futuros(self):
        resultado = validar_walk_forward_v2(
            sinteticos(169), "gol_ht", "2026-09-02T12:00:00"
        )
        self.assertEqual(resultado["estado"], "amostra_insuficiente")
        self.assertEqual(resultado["minimo"], 170)


class BaseIndividualTest(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE sinais(id INTEGER, partida_id INTEGER,snapshot_id INTEGER,mercado TEXT,linha REAL,odd REAL,regra_versao TEXT,regra_fingerprint TEXT,features_json TEXT,criado_em TEXT);
            CREATE TABLE snapshots(id INTEGER,partida_id INTEGER,placar TEXT,contexto_api_json TEXT,coletado_em TEXT);
            CREATE TABLE partidas(id INTEGER,mandante TEXT,visitante TEXT,liga TEXT);
            CREATE TABLE entregas_alertas(sinal_id INTEGER,canal TEXT,status TEXT,provedor_mensagem_id INTEGER,entregue_em TEXT);
            CREATE TABLE resultados_sinais(sinal_id INTEGER,resultado TEXT,retorno_unidades REAL,encerrado_em TEXT);
        """)
        for i in range(1, 7):
            s, t, j = exemplo(i)
            self.c.execute("INSERT INTO sinais VALUES(?,?,?,?,?,?,?,?,?,?)", (i,i,i,"gol_ht",.5,1.7,"metodo-v1","fp-v1",json.dumps(s["features"]),s["criado_em"]))
            self.c.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)", (i,i,"0-0",json.dumps(t["contexto_api_json"]),t["coletado_em"]))
            self.c.execute("INSERT INTO partidas VALUES(?,?,?,?)", (i,"A","B","Liga"))
            self.c.execute("INSERT INTO entregas_alertas VALUES(?,?,?,?,?)", (i,"-100:teste","entregue",i,"2026-09-01T12:00:01"))
            self.c.execute("INSERT INTO resultados_sinais VALUES(?,?,?,?)", (i,"green",.7,"2026-09-01T13:00:00"))

    def test_base_so_reais_anteriores_ao_corte_sem_propria_partida(self):
        self.c.execute("DELETE FROM entregas_alertas WHERE sinal_id=2")
        self.c.execute("UPDATE entregas_alertas SET canal='-100:resultado' WHERE sinal_id=3")
        self.c.execute("UPDATE resultados_sinais SET encerrado_em='2026-09-03T13:00:00' WHERE sinal_id=4")
        self.c.execute("UPDATE snapshots SET coletado_em='2026-09-01T13:00:00' WHERE id=5")
        r = carregar_base(self.c, "gol_ht", "2026-09-02T12:00:00", excluir_partida=6)
        self.assertEqual([x["sinal_id"] for x in r], [1])

    def test_primeira_entrada_deduplicada_sem_trocar_red_por_green(self):
        self.c.execute("UPDATE resultados_sinais SET resultado='red',retorno_unidades=-1 WHERE sinal_id=1")
        self.c.execute("UPDATE sinais SET partida_id=1 WHERE id=2")
        self.c.execute("UPDATE snapshots SET partida_id=1 WHERE id=2")
        self.c.execute("INSERT INTO entregas_alertas SELECT sinal_id,'-200',status,provedor_mensagem_id,entregue_em FROM entregas_alertas WHERE sinal_id=1")
        r = carregar_base(self.c, "gol_ht", "2026-09-02T12:00:00")
        self.assertEqual(len(r), 5)
        self.assertEqual(r[0]["alvo"], 0)


if __name__ == "__main__":
    unittest.main()
