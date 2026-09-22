import copy
import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from probabilidade_por_acertos import (
    CAMPO, PREFIXO, VERSAO, anexar_estimativa, calcular_estimativa,
    auditar_estimativas_persistidas, carregar_estimativa,
    registrar_estimativa, validar_integridade_estimativa,
    _selar_estimativa,
)
from custodia_estimativa_historica import (
    PREFIXO_CHAVE_V2,
    PREFIXO_CHAVE_V3,
    auditar_gatilhos as auditar_gatilhos_estimativa_historica,
    instalar_gatilhos as instalar_gatilhos_estimativa_historica,
)
from resumo_forca_sinais import resumo_forca_ao_vivo
from telegram_alertas import AlertasTelegram


class ProbabilidadeAcertosTest(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")
        self.addCleanup(self.c.close)
        self.c.executescript("""
            CREATE TABLE partidas (id INTEGER PRIMARY KEY, liga TEXT);
            CREATE TABLE sinais (id INTEGER PRIMARY KEY, partida_id INTEGER,
                mercado TEXT, linha REAL, odd REAL,
                regra_versao TEXT, regra_fingerprint TEXT,
                features_json TEXT, criado_em TEXT);
            CREATE TABLE entregas_alertas (sinal_id INTEGER, canal TEXT,
                status TEXT, provedor_mensagem_id INTEGER, entregue_em TEXT);
            CREATE TABLE resultados_sinais (sinal_id INTEGER PRIMARY KEY,
                resultado TEXT, retorno_unidades REAL, encerrado_em TEXT);
            CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT);
        """)
        instalar_gatilhos_estimativa_historica(self.c)
        self.corte = datetime(2026, 9, 2, 12)
        self.sinal = {"id": 999, "partida_id": 999, "mercado": "gol_ht",
                      "linha": 0.5, "odd": 1.8,
                      "regra_versao": "sinais-v6", "regra_fingerprint": "fp-ht",
                      "features": self.features_executaveis(),
                      "criado_em": self.corte.isoformat()}
        for i in range(1, 11):
            self.adicionar(i, "green" if i <= 6 else "red")
        self.c.execute(
            "INSERT INTO partidas(id,liga) VALUES(?,?)",
            (999, "Liga alvo"),
        )
        self.c.execute(
            "INSERT INTO sinais VALUES(?,?,?,?,?,?,?,?,?)",
            (
                999, 999, "gol_ht", 0.5, 1.8, "sinais-v6", "fp-ht",
                json.dumps(self.sinal["features"]),
                self.sinal["criado_em"],
            ),
        )
        self.c.commit()

    def features_executaveis(self, *, fonte="betsapi", bookmaker="bet365",
                             odd=1.8, linha=0.5):
        return {
            "exploracao_sombra": {"versao": "ht00-v3"},
            "modelo": {"linhagem_sha256": "linhagem-ht"},
            "fonte_odds": fonte,
            "bookmaker_odds": bookmaker,
            "cotacao_entrada_clv_estado": "congelada_v1",
            "cotacao_entrada_clv": {
                "schema": "cotacao-entrada-clv-v2",
                "tipo": "binaria",
                "mercado": "gol_ht",
                "linha": linha,
                "odd_selecionada": odd,
                "over": odd,
                "under": 2.0,
                "fonte": fonte,
                "bookmaker": bookmaker,
                "coletado_em": "2026-09-01T14:59:00+00:00",
                "idade_segundos": 1.0,
                "cache": False,
                "origem_mercado": {
                    "schema": "origem-mercado-odd-v1",
                    "fonte": fonte,
                    "bookmaker": bookmaker,
                    "identificador": "fixture-1",
                    "nome": "1st Half Goals",
                    "linha": linha,
                    "lados": ["over", "under"],
                },
            },
        }

    def adicionar(self, i, resultado="green", *, partida=None, canal="-100:teste",
                  entregue=True, data=None, final=None, mercado="gol_ht",
                  versao="ht00-v3", fingerprint="fp-ht", linhagem="linhagem-ht",
                  retorno=None, executavel=True, adulterar=False,
                  liga="Liga A"):
        data = data or self.corte - timedelta(days=1)
        final = final or data + timedelta(hours=1)
        f = self.features_executaveis()
        f["exploracao_sombra"]["versao"] = versao
        f["modelo"]["linhagem_sha256"] = linhagem
        if not executavel:
            f.update(fonte_odds="packball", bookmaker_odds=None)
            f["cotacao_entrada_clv_estado"] = "mercado_incompleto_ou_invalido"
            f.pop("cotacao_entrada_clv", None)
        elif adulterar:
            f["cotacao_entrada_clv"]["odd_selecionada"] = 1.99
            f["cotacao_entrada_clv"]["over"] = 1.99
        self.c.execute(
            "INSERT OR IGNORE INTO partidas(id,liga) VALUES(?,?)",
            (partida or i, liga),
        )
        self.c.execute("INSERT INTO sinais VALUES(?,?,?,?,?,?,?,?,?)",
                       (i, partida or i, mercado, 0.5, 1.8,
                        "sinais-v6", fingerprint,
                        json.dumps(f), (data - timedelta(seconds=1)).isoformat()))
        if entregue:
            self.c.execute("INSERT INTO entregas_alertas VALUES(?,?,?,?,?)",
                           (i, canal, "entregue", i, data.isoformat()))
        if resultado:
            retorno = retorno if retorno is not None else (
                0.8 if resultado == "green" else -1
            )
            self.c.execute("INSERT INTO resultados_sinais VALUES(?,?,?,?)",
                           (i, resultado, retorno, final.isoformat()))
        self.c.commit()

    def calcular(self):
        return calcular_estimativa(self.c, self.sinal)

    def test_base_beta11_nao_e_nota_nem_inverso_da_odd(self):
        self.sinal.update(pontuacao_tecnica=100, odd=1.01, probabilidade_calibrada=0.99)
        self.sinal["features"]["cotacao_entrada_clv"]["odd_selecionada"] = 1.01
        self.sinal["features"]["cotacao_entrada_clv"]["over"] = 1.01
        antes = copy.deepcopy(self.sinal)
        r = self.calcular()
        self.assertEqual(r["amostra"], 10)
        self.assertEqual((r["greens"], r["reds"]), (6, 4))
        self.assertAlmostEqual(r["probabilidade"], 7 / 12)
        self.assertEqual(r["taxa_observada"], 0.6)
        self.assertAlmostEqual(r["retorno_unidades_total"], 0.8)
        self.assertAlmostEqual(r["roi"], 0.08)
        self.assertAlmostEqual(r["odd_media_executada"], 1.8)
        self.assertEqual(len(r["unidades_base"]), 10)
        self.assertEqual(r["dias_distintos"], 1)
        self.assertEqual(r["ligas_distintas"], 1)
        self.assertEqual(r["maior_sequencia_red"], 4)
        self.assertAlmostEqual(r["drawdown_maximo_unidades"], 4.0)
        self.assertFalse(r["vantagem_historica_robusta"])
        self.assertEqual(r["estado_vantagem"], "amostra_inicial")
        self.assertIsNone(r["intervalo_roi_95_agrupado_dia"])
        self.assertLess(r["intervalo_roi_95"][0], 0)
        self.assertGreater(r["intervalo_roi_95"][1], 0)
        self.assertEqual(r["estado"], "amostra_inicial")
        self.assertLess(r["intervalo_wilson95"][0], 0.6)
        self.assertGreater(r["intervalo_wilson95"][1], 0.6)
        self.assertEqual(antes, self.sinal)

    def test_so_entregas_reais_sem_sombra_avisos_ou_resultados(self):
        self.adicionar(11, entregue=False)
        for i, canal in enumerate(("-100:aguardar_odd", "-100:resultado", "-100:teste:resultado"), 12):
            self.adicionar(i, canal=canal)
        self.adicionar(15)
        self.c.execute("UPDATE entregas_alertas SET status='incerto' WHERE sinal_id=15")
        self.adicionar(16)
        self.c.execute("UPDATE entregas_alertas SET provedor_mensagem_id=NULL WHERE sinal_id=16")
        self.assertEqual(self.calcular()["amostra"], 10)
        self.adicionar(17, canal="-100")
        self.assertEqual(self.calcular()["amostra"], 11)

    def test_sem_resultado_futuro_proprio_jogo_ou_proprio_sinal(self):
        self.adicionar(11, final=self.corte + timedelta(seconds=1))
        self.adicionar(12, final=self.corte)
        self.adicionar(13, partida=999)
        self.adicionar(998, partida=777)
        self.adicionar(14, data=self.corte + timedelta(seconds=1))
        self.assertEqual(self.calcular()["amostra"], 11)
        candidato_id_998 = {**self.sinal, "id": 998}
        self.assertEqual(
            calcular_estimativa(self.c, candidato_id_998)["amostra"], 10
        )

    def test_sem_misturar_versoes_fingerprints_e_mercados(self):
        self.adicionar(11, versao="ht00-v2")
        self.adicionar(12, fingerprint="fp-antigo")
        self.adicionar(13, linhagem="linhagem-antiga")
        self.adicionar(14, mercado="gol_ft")
        self.adicionar(15, mercado="under_gol_ht")
        self.assertEqual(self.calcular()["amostra"], 10)

    def test_deduplica_jogo_e_canal_sem_escolher_resultado_melhor(self):
        self.adicionar(11, partida=10)  # Primeira entrada no jogo 10 é red.
        self.c.execute("INSERT INTO entregas_alertas SELECT sinal_id,'-200',status,provedor_mensagem_id,entregue_em FROM entregas_alertas WHERE sinal_id=1")
        self.adicionar(12, resultado=None)
        self.adicionar(13, partida=12)  # Não substitui a primeira pendente.
        r = self.calcular()
        self.assertEqual((r["amostra"], r["greens"], r["reds"]), (10, 6, 4))

    def test_exclui_parciais_sem_dado_void_inconsistentes_e_antigos(self):
        for i, resultado in enumerate(("half_green", "half_red", "void", "sem_dado"), 11):
            self.adicionar(i, resultado)
        self.adicionar(15, retorno=-1)
        self.adicionar(16, "red", retorno=0.5)
        self.adicionar(17, data=self.corte - timedelta(days=91))
        self.adicionar(18, final=self.corte - timedelta(days=2))
        self.assertEqual(self.calcular()["amostra"], 10)

    def test_pouca_amostra_nao_inventa_percentual(self):
        self.c.execute("DELETE FROM resultados_sinais WHERE sinal_id>4")
        r = self.calcular()
        self.assertIsNone(r["probabilidade"])
        self.assertEqual(r["amostra"], 4)
        self.assertIn("amostra insuficiente (4/5)", resumo_forca_ao_vivo({CAMPO: r}))

    def test_exclui_fontes_mistas_e_prova_adulterada(self):
        self.adicionar(11, executavel=False)
        self.adicionar(12, adulterar=True)
        r = self.calcular()
        self.assertEqual((r["amostra"], r["greens"], r["reds"]), (10, 6, 4))
        self.assertEqual(r["entregas_excluidas_custodia"], 2)
        self.assertEqual(r["populacao"], "entregas_executaveis_betsapi_bet365")

    def test_exclui_liquidacao_cujo_retorno_diverge_da_odd(self):
        self.adicionar(11, "green", retorno=0.5)
        self.adicionar(12, "red", retorno=-0.5)
        r = self.calcular()
        self.assertEqual((r["amostra"], r["greens"], r["reds"]), (10, 6, 4))
        self.assertEqual(r["liquidacoes_excluidas_retorno"], 2)
        self.assertAlmostEqual(r["retorno_unidades_total"], 0.8)

    def test_fonte_mista_anterior_nao_expulsa_primeira_bet365_do_jogo(self):
        data = self.corte - timedelta(hours=2)
        self.adicionar(11, partida=200, data=data, executavel=False)
        self.adicionar(12, partida=200, data=data + timedelta(minutes=1))
        r = self.calcular()
        self.assertEqual((r["amostra"], r["greens"], r["reds"]), (11, 7, 4))
        self.assertEqual(r["entregas_excluidas_custodia"], 1)

    def test_alerta_sem_cotacao_executavel_nao_herda_taxa_bet365(self):
        sinal = copy.deepcopy(self.sinal)
        sinal["features"] = self.features_executaveis()
        sinal["features"].update(fonte_odds="packball", bookmaker_odds=None)
        sinal["features"]["cotacao_entrada_clv_estado"] = "incompleta"
        sinal["features"].pop("cotacao_entrada_clv", None)
        r = calcular_estimativa(self.c, sinal)
        self.assertEqual(r["estado"], "cotacao_atual_nao_executavel")
        self.assertEqual(r["amostra"], 0)
        self.assertIn("não possui prova executável Bet365", resumo_forca_ao_vivo({CAMPO: r}))

    def test_dez_greens_nao_prometem_cem_por_cento(self):
        self.c.execute("UPDATE resultados_sinais SET resultado='green',retorno_unidades=0.8")
        self.assertAlmostEqual(self.calcular()["probabilidade"], 11 / 12)

    def test_sem_identidade_ou_data_nao_usa_media_global(self):
        for campo in ("regra_fingerprint", "criado_em"):
            candidato = {**self.sinal, campo: None}
            self.assertIsNone(calcular_estimativa(self.c, candidato)["probabilidade"])

    def test_congela_antes_do_envio_e_reutiliza_apos_green(self):
        r = registrar_estimativa(self.c, self.sinal)
        self.assertTrue(validar_integridade_estimativa(r)["integra"])
        self.c.execute(
            "INSERT INTO resultados_sinais VALUES(?,?,?,?)",
            (999, "green", 0.8, (self.corte + timedelta(hours=1)).isoformat()),
        )
        self.assertEqual(r, registrar_estimativa(self.c, self.sinal))
        self.assertEqual(r, carregar_estimativa(self.c, 999))
        item = {"sinal_id": 999, "resultado": "green"}
        anexar_estimativa(self.c, item)
        self.assertEqual(item[CAMPO], r)

    def test_edicao_legada_nao_calcula_retroativamente(self):
        item = {"sinal_id": 1, "resultado": "green"}
        anexar_estimativa(self.c, item)
        self.assertNotIn(CAMPO, item)
        self.assertIsNone(carregar_estimativa(self.c, 1))

    def test_transacao_do_chamador_nao_e_comitada(self):
        self.c.execute("INSERT INTO metadados VALUES('chamador','pendente')")
        registrar_estimativa(self.c, self.sinal)
        self.c.rollback()
        self.assertIsNone(carregar_estimativa(self.c, 999))
        self.assertEqual(self.c.execute("SELECT count(*) FROM metadados").fetchone()[0], 0)

    def test_sqlite_bloqueia_update_delete_e_replace_da_fotografia(self):
        registrar_estimativa(self.c, self.sinal)
        chave = PREFIXO + "999"
        original = self.c.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave,)
        ).fetchone()[0]
        for sql, parametros in (
            ("UPDATE metadados SET valor=? WHERE chave=?", ("{}", chave)),
            ("DELETE FROM metadados WHERE chave=?", (chave,)),
            ("INSERT OR REPLACE INTO metadados(chave,valor) VALUES(?,?)",
             (chave, "{}")),
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                self.c.execute(sql, parametros)
        self.assertEqual(original, self.c.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave,)
        ).fetchone()[0])
        self.assertEqual(carregar_estimativa(self.c, 999)["amostra"], 10)

    def test_sqlite_preserva_tambem_fotografias_v2_e_v3(self):
        for prefixo in (PREFIXO_CHAVE_V2, PREFIXO_CHAVE_V3):
            chave = prefixo + "legado"
            self.c.execute(
                "INSERT INTO metadados(chave,valor) VALUES(?,?)",
                (chave, '{"congelada":true}'),
            )
            for sql, parametros in (
                ("UPDATE metadados SET valor=? WHERE chave=?", ("{}", chave)),
                ("DELETE FROM metadados WHERE chave=?", (chave,)),
                (
                    "INSERT OR REPLACE INTO metadados(chave,valor) VALUES(?,?)",
                    (chave, "{}"),
                ),
            ):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.c.execute(sql, parametros)

    def test_hash_alterado_em_memoria_falha_fechado(self):
        valor = calcular_estimativa(self.c, self.sinal)
        valor["greens"] = 10
        validacao = validar_integridade_estimativa(valor)
        self.assertFalse(validacao["integra"])
        self.assertEqual(validacao["motivo"], "hash_divergente")

    def test_ausencia_de_gatilho_bloqueia_leitura_registro_e_auditoria(self):
        registrar_estimativa(self.c, self.sinal)
        self.c.execute(
            "DROP TRIGGER trg_probabilidade_acertos_v2_update_imutavel"
        )
        custodia = auditar_gatilhos_estimativa_historica(self.c)
        self.assertFalse(custodia["saudavel"])
        self.assertIsNone(carregar_estimativa(self.c, 999))
        auditoria = auditar_estimativas_persistidas(self.c)
        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(
            auditoria["motivos"].get(
                "custodia_sqlite:gatilhos_ausentes"
            ),
            1,
        )

    def test_auditoria_confirma_registro_integro_e_vinculado(self):
        registrar_estimativa(self.c, self.sinal)
        auditoria = auditar_estimativas_persistidas(self.c)
        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["estado"], "integra")
        self.assertEqual((auditoria["analisadas"], auditoria["integras"]), (1, 1))
        self.assertEqual(auditoria["proveniencia_reproduzida"], 1)

    def test_origem_alterada_invalida_leitura_e_auditoria(self):
        registrar_estimativa(self.c, self.sinal)
        self.c.execute(
            "UPDATE resultados_sinais SET resultado='green',"
            "retorno_unidades=0.8 WHERE sinal_id=10"
        )
        self.assertIsNone(carregar_estimativa(self.c, 999))
        auditoria = auditar_estimativas_persistidas(self.c)
        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["invalidas"], 1)
        self.assertEqual(auditoria["motivos"], {"base_historica_divergente": 1})

    def test_hash_recalculado_nao_mascara_contrato_incoerente(self):
        r = calcular_estimativa(self.c, self.sinal)
        r["amostra"] = r["greens"] + r["reds"] + 1
        r = _selar_estimativa(r)
        validacao = validar_integridade_estimativa(r)
        self.assertFalse(validacao["integra"])
        self.assertEqual(validacao["motivo"], "amostra_incoerente")

    def test_hash_recalculado_nao_mascara_roi_incoerente(self):
        r = calcular_estimativa(self.c, self.sinal)
        r["roi"] = 0.99
        r = _selar_estimativa(r)
        validacao = validar_integridade_estimativa(r)
        self.assertFalse(validacao["integra"])
        self.assertEqual(validacao["motivo"], "roi_incoerente")

    def test_hash_recalculado_nao_mascara_robustez_incoerente(self):
        r = calcular_estimativa(self.c, self.sinal)
        r["drawdown_maximo_unidades"] = 0
        r = _selar_estimativa(r)
        validacao = validar_integridade_estimativa(r)
        self.assertFalse(validacao["integra"])
        self.assertEqual(validacao["motivo"], "robustez_incoerente")

    def test_vantagem_robusta_exige_dias_e_consistencia_temporal(self):
        self.c.execute("DELETE FROM resultados_sinais")
        self.c.execute("DELETE FROM entregas_alertas")
        self.c.execute("DELETE FROM sinais")
        self.c.execute("DELETE FROM partidas")
        for indice in range(40):
            self.adicionar(
                100 + indice,
                "green",
                data=self.corte - timedelta(days=20 - indice // 2),
                liga="Liga A" if indice % 3 else "Liga B",
            )
        r = self.calcular()
        self.assertEqual(r["amostra"], 40)
        self.assertEqual(r["dias_distintos"], 20)
        self.assertEqual(r["ligas_distintas"], 2)
        self.assertGreater(r["intervalo_roi_95_agrupado_dia"][0], 0)
        self.assertGreater(r["roi_metade_antiga"], 0)
        self.assertGreater(r["roi_metade_recente"], 0)
        self.assertTrue(r["vantagem_historica_robusta"])
        self.assertEqual(
            r["estado_vantagem"], "vantagem_historica_robusta"
        )
        self.assertTrue(validar_integridade_estimativa(r)["integra"])

    def test_apresentacao_descritiva_com_amostra_e_sem_alterar_calibracao(self):
        candidato = {"mercado": "gol_ht", "probabilidade_calibrada": 0.8}
        anexar_estimativa(self.c, candidato, sinal=self.sinal)
        texto = resumo_forca_ao_vivo(candidato)
        self.assertIn("histórica executável do método: 58,3%", texto)
        self.assertIn("Base Bet365: 6 greens / 4 reds", texto)
        self.assertIn("ROI histórico executável", texto)
        self.assertIn("+8,0%", texto)
        self.assertIn("resultado financeiro ainda inconclusivo", texto)
        self.assertIn("Amostra inicial", texto)
        self.assertIn("80,0%", resumo_forca_ao_vivo(candidato, calibrado=True))

    def test_edicoes_green_e_red_mantem_percentual_original(self):
        registrar_estimativa(self.c, self.sinal)
        item = {"sinal_id": 999, "liga": "Liga", "mandante": "A", "visitante": "B",
                "mercado": "gol_ht", "linha": 0.5, "odd": 1.44, "minuto_entrada": 20,
                "placar_entrada": "0-0", "resultado": "green", "retorno_unidades": 0.44}
        anexar_estimativa(self.c, item)
        green = AlertasTelegram._mensagem_green_antecipado(item, {"status": 30, "placar": "1-0"}, simulacao=True)
        final = AlertasTelegram._mensagem_entrada_finalizada(item, {}, simulacao=True)
        self.assertIn("histórica executável do método: 58,3%", green)
        self.assertIn("histórica executável do método: 58,3%", final)
        self.assertIn("GREEN DA SIMULAÇÃO", green)
        self.assertIn("Retorno hipotético", final)

    def test_falha_de_banco_nao_muda_candidato_ou_gates(self):
        candidato = {"status": "aprovado", "odd": 1.44}
        self.c.close()
        anexar_estimativa(self.c, candidato, sinal=self.sinal)
        self.assertEqual(candidato, {"status": "aprovado", "odd": 1.44})

    def test_rollback_sem_consulta_ou_escrita(self):
        with patch.dict("os.environ", {"PROBABILIDADE_ACERTOS_ATIVA": "0"}):
            destino = {}
            anexar_estimativa(None, destino, sinal=self.sinal)
            self.assertEqual(destino, {})
        with patch.dict("os.environ", {"RESUMO_FORCA_SINAIS_ATIVO": "0"}):
            anexar_estimativa(self.c, destino, sinal=self.sinal)
            self.assertEqual(resumo_forca_ao_vivo(destino), "")


if __name__ == "__main__":
    unittest.main()
