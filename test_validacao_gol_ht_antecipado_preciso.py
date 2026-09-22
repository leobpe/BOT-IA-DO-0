import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from filtro_gol_ht_antecipado_preciso import METODO
from validacao_gol_ht_antecipado_preciso import (
    CHAVE_DEFINICAO,
    TAMANHO_COORTE,
    registrar_ou_validar_definicao,
    resumir_validacao,
    sincronizar_coorte,
)


class ValidacaoGolHtAntecipadoPrecisoTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.executescript("""
            CREATE TABLE metadados (
                chave TEXT PRIMARY KEY, valor TEXT NOT NULL
            );
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                partida_id INTEGER NOT NULL,
                snapshot_id INTEGER NOT NULL,
                criado_em TEXT NOT NULL,
                mercado TEXT NOT NULL,
                linha TEXT,
                odd REAL,
                pontuacao_tecnica REAL,
                regra_versao TEXT,
                regra_fingerprint TEXT,
                motivos_json TEXT,
                features_json TEXT,
                status TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY,
                resultado TEXT,
                retorno_unidades REAL
            );
            CREATE TABLE entregas_alertas (
                id INTEGER PRIMARY KEY,
                sinal_id INTEGER,
                canal TEXT,
                status TEXT
            );
        """)
        # sinais.criado_em usa o relógio local sem offset no banco real.
        self.inicio = datetime(2026, 9, 9, 19, 0)
        self.ancora = registrar_ou_validar_definicao(
            self.conexao, self.inicio
        )

    def tearDown(self):
        self.conexao.close()

    @staticmethod
    def _features(*, chutes=2, sot=2, gols_faixa=12):
        return {
            "exploracao_sombra": {"versao": METODO},
            "gol_antecipado": {"minuto": 20},
            "gol_antecipado_ht": {
                "confirmado": True,
                "total_gols_amostra_faixa": gols_faixa,
            },
            "qualidade_dados": 100,
            "odds_cache": False,
            "idade_odds_segundos": 5,
            "chutes_no_gol": [sot, 0],
            "chutes_no_gol_total": sot,
            "janelas": {"5": {
                "disponivel": True,
                "duracao_real_minutos": 5,
                "resets_detectados": [],
                "chutes": [chutes, 0],
                "chutes_total": chutes,
            }},
        }

    def _inserir(
        self, indice, *, minutos=None, resultado="green", retorno=1.0,
        odd=2.0, features=None, partida_id=None, publicar=False,
    ):
        minutos = indice if minutos is None else minutos
        criado_em = (self.inicio + timedelta(minutes=minutos)).isoformat()
        self.conexao.execute("""
            INSERT INTO sinais(
                id,partida_id,snapshot_id,criado_em,mercado,linha,odd,
                pontuacao_tecnica,regra_versao,regra_fingerprint,
                motivos_json,features_json,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            indice, partida_id or indice, indice, criado_em, "gol_ht", 0.5,
            odd, 96, "regra", "sha", "[]",
            json.dumps(features or self._features()), "simulacao",
        ))
        if resultado is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?,?,?)",
                (indice, resultado, retorno),
            )
        if publicar:
            self.conexao.execute(
                "INSERT INTO entregas_alertas VALUES (?,?,?,?)",
                (indice, indice, "grupo:teste", "entregue"),
            )

    def _resumir(self):
        sincronizar_coorte(
            self.conexao, agora=self.inicio + timedelta(hours=3)
        )
        return resumir_validacao(self.conexao)

    def test_ancora_exclui_legado_e_filtro_fraco(self):
        self._inserir(1, minutos=-10)
        self._inserir(2, features=self._features(sot=1))
        self._inserir(3, publicar=False)

        resumo = self._resumir()

        self.assertEqual(1, resumo["candidatos"])
        self.assertEqual(0, resumo["publicados"])
        self.assertEqual(TAMANHO_COORTE - 1, resumo["faltam"])
        historico = resumo["historico_gerador"]
        self.assertEqual(1, historico["gerador_sem_filtro"]["validos"])
        self.assertFalse(historico["entra_na_coorte_nova"])

    def test_funil_explica_gargalo_sem_consultar_resultados(self):
        self._inserir(
            1, resultado="red", retorno=-1.0,
            features=self._features(sot=0), partida_id=10,
        )
        self._inserir(
            2, resultado="green", retorno=1.0,
            features=self._features(sot=1), partida_id=10,
        )
        self._inserir(
            3, resultado=None, retorno=None,
            features=self._features(sot=2), partida_id=20,
        )

        resumo = self._resumir()
        funil = resumo["funil_candidatos"]

        self.assertEqual("com_elegiveis", funil["estado"])
        self.assertEqual(3, funil["decisoes_gerador"])
        self.assertEqual(2, funil["decisoes_rejeitadas"])
        self.assertEqual(1, funil["decisoes_elegiveis"])
        self.assertEqual(2, funil["partidas_com_decisao"])
        self.assertEqual(
            1, funil["partidas_com_alguma_decisao_elegivel"]
        )
        self.assertEqual(
            {"chutes_no_gol_insuficientes": 2},
            funil["motivos_rejeicao_decisoes"],
        )
        self.assertEqual(
            {"chutes_no_gol_insuficientes": 1},
            funil["motivos_ultima_decisao_partidas_sem_elegivel"],
        )
        self.assertEqual(
            "chutes_no_gol_insuficientes", funil["gargalo_atual"]
        )
        self.assertFalse(funil["consulta_resultados"])
        self.assertFalse(funil["consulta_entregas"])
        self.assertEqual(1, resumo["candidatos"])

    def test_funil_distingue_gerador_ausente_de_filtro_sem_elegiveis(self):
        vazio = resumir_validacao(self.conexao)["funil_candidatos"]
        self.assertEqual("sem_sinais_gerador", vazio["estado"])

        self._inserir(
            1, resultado=None, retorno=None,
            features=self._features(sot=0),
        )
        rejeitado = resumir_validacao(self.conexao)["funil_candidatos"]
        self.assertEqual("sem_elegiveis", rejeitado["estado"])
        self.assertEqual(1, rejeitado["partidas_sem_decisao_elegivel"])
        self.assertEqual(0, rejeitado["decisoes_json_invalidas"])

    def test_ancora_preserva_utc_e_seleciona_no_relogio_dos_sinais(self):
        self.assertEqual(
            self.inicio.isoformat(),
            self.ancora["registrado_em_relogio_sinais"],
        )
        self.assertRegex(self.ancora["registrado_em"], r"[+-]\d\d:\d\d$")
        adulterada = dict(self.ancora)
        adulterada.pop("registrado_em_relogio_sinais")
        self.conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(adulterada), CHAVE_DEFINICAO),
        )
        with self.assertRaises(RuntimeError):
            resumir_validacao(self.conexao)

    def test_coorte_favoravel_exige_60_futuros_e_holdout(self):
        for indice in range(1, 61):
            self._inserir(indice, publicar=indice % 2 == 0)

        resumo = self._resumir()

        self.assertEqual(60, resumo["candidatos"])
        self.assertEqual(30, resumo["publicados"])
        self.assertEqual(42, resumo["desenvolvimento"]["validos"])
        self.assertEqual(18, resumo["holdout"]["validos"])
        self.assertTrue(resumo["gate_preco_conservador"]["satisfeito"])
        self.assertEqual(
            "favoravel_para_revisao_manual", resumo["decisao"]
        )
        self.assertTrue(resumo["apto_revisao"])

    def test_taxa_abaixo_de_75_nao_e_promovida_mesmo_com_roi(self):
        for indice in range(1, 61):
            green = indice <= 44
            self._inserir(
                indice,
                resultado="green" if green else "red",
                retorno=1.0 if green else -1.0,
            )

        resumo = self._resumir()

        self.assertEqual(0.7333, resumo["taxa_green"])
        self.assertGreater(resumo["roi"], 0)
        self.assertEqual(
            "inconclusiva_ou_desfavoravel", resumo["decisao"]
        )

    def test_checkpoint_so_usa_prefixo_fixo_de_25(self):
        for indice in range(1, 25):
            self._inserir(indice, resultado="red", retorno=-1.0)
        self.assertFalse(self._resumir()["alerta_desfavoravel"])
        self._inserir(25, resultado="red", retorno=-1.0)
        resumo = self._resumir()
        self.assertTrue(resumo["alerta_desfavoravel"])
        self.assertEqual(25, resumo["checkpoint_seguranca"]["validos"])

    def test_primeiros_60_nao_mudam_com_o_61(self):
        for indice in range(1, 62):
            self._inserir(
                indice,
                resultado="red" if indice == 61 else "green",
                retorno=-1.0 if indice == 61 else 1.0,
            )
        resumo = self._resumir()
        self.assertEqual(60, resumo["candidatos"])
        self.assertEqual(60, resumo["greens"])
        self.assertEqual(0, resumo["reds"])

    def test_partida_entra_uma_vez_e_conteudo_fica_congelado(self):
        self._inserir(1, partida_id=10)
        sincronizar_coorte(self.conexao)
        self._inserir(2, partida_id=10)
        self.conexao.execute(
            "UPDATE sinais SET odd=9,features_json=? WHERE id=1",
            (json.dumps(self._features(sot=0)),),
        )
        resumo = self._resumir()
        self.assertEqual(1, resumo["candidatos"])
        congelado = self.conexao.execute(
            "SELECT odd,candidato_json FROM "
            "coorte_gol_ht_antecipado_preciso WHERE sinal_id=1"
        ).fetchone()
        self.assertEqual(2.0, congelado[0])
        self.assertEqual(2, json.loads(congelado[1])["features"][
            "chutes_no_gol_total"
        ])

    def test_ancora_e_membro_adulterados_falham_fechado(self):
        documento = dict(self.ancora)
        documento["coorte_fixa"] = 999
        self.conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(documento), CHAVE_DEFINICAO),
        )
        with self.assertRaises(RuntimeError):
            resumir_validacao(self.conexao)

        self.conexao.rollback()
        self.conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(self.ancora), CHAVE_DEFINICAO),
        )
        self._inserir(1)
        sincronizar_coorte(self.conexao)
        congelado = self.conexao.execute(
            "SELECT candidato_json FROM coorte_gol_ht_antecipado_preciso"
        ).fetchone()[0]
        candidato = json.loads(congelado)
        candidato["features"]["chutes_no_gol_total"] = 0
        self.conexao.execute(
            "UPDATE coorte_gol_ht_antecipado_preciso SET candidato_json=?",
            (json.dumps(candidato),),
        )
        with self.assertRaises(RuntimeError):
            resumir_validacao(self.conexao)


if __name__ == "__main__":
    unittest.main()
