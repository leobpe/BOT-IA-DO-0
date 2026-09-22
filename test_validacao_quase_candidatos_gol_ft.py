import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from filtro_gol_ft_antecipado_preciso import METODO
from validacao_quase_candidatos_gol_ft import (
    BRACO_HISTORICO_8_11,
    BRACO_MINUTO_61_75,
    CHAVE_DEFINICAO,
    TAMANHO_POR_BRACO,
    classificar_braco,
    registrar_ou_validar_definicao,
    resumir_validacao,
    sincronizar_coorte,
)


class ValidacaoQuaseCandidatosGolFtTest(unittest.TestCase):
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
        """)
        self.inicio = datetime(2026, 9, 11, 1, 0)
        self.ancora = registrar_ou_validar_definicao(
            self.conexao, self.inicio
        )

    def tearDown(self):
        self.conexao.close()

    @staticmethod
    def _features(
        *, minuto=55, historico=12, chutes=1, qualidade=100,
        odd_cache=False,
    ):
        return {
            "exploracao_sombra": {"versao": METODO},
            "gol_antecipado": {
                "minuto": minuto,
                "evidencias_ao_vivo": ["chutes_5min", "chute_no_gol"],
            },
            "gol_antecipado_2t": {
                "confirmado": True,
                "total_gols_amostra_faixa": historico,
            },
            "qualidade_dados": qualidade,
            "odds_cache": odd_cache,
            "idade_odds_segundos": 5,
            "chutes_no_gol": [2, 1],
            "chutes_no_gol_total": 3,
            "janelas": {"5": {
                "disponivel": True,
                "resets_detectados": [],
                "chutes": [chutes, 0],
                "chutes_total": chutes,
            }},
        }

    def _candidato(self, indice=1, *, features=None, odd=1.7):
        return {
            "id": indice,
            "partida_id": indice,
            "snapshot_id": indice,
            "criado_em": self.inicio.isoformat(),
            "mercado": "gol_ft",
            "linha": 2.5,
            "odd": odd,
            "pontuacao_tecnica": 95,
            "regra_versao": "regra",
            "regra_fingerprint": "sha",
            "motivos": [],
            "features": features or self._features(),
            "status": "simulacao",
        }

    def _inserir(
        self, indice, *, minutos=None, features=None, odd=1.7,
        resultado="green", retorno=0.7, partida_id=None,
    ):
        minutos = indice if minutos is None else minutos
        candidato = self._candidato(
            indice, features=features, odd=odd
        )
        candidato["partida_id"] = partida_id or indice
        candidato["criado_em"] = (
            self.inicio + timedelta(minutes=minutos)
        ).isoformat()
        self.conexao.execute("""
            INSERT INTO sinais(
                id,partida_id,snapshot_id,criado_em,mercado,linha,odd,
                pontuacao_tecnica,regra_versao,regra_fingerprint,
                motivos_json,features_json,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            candidato["id"], candidato["partida_id"],
            candidato["snapshot_id"], candidato["criado_em"],
            candidato["mercado"], candidato["linha"], candidato["odd"],
            candidato["pontuacao_tecnica"], candidato["regra_versao"],
            candidato["regra_fingerprint"], "[]",
            json.dumps(candidato["features"]), candidato["status"],
        ))
        if resultado is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?,?,?)",
                (indice, resultado, retorno),
            )

    def test_classifica_apenas_minuto_quando_todo_resto_aprova(self):
        classificacao = classificar_braco(self._candidato(
            features=self._features(minuto=67, historico=20)
        ))

        self.assertEqual(BRACO_MINUTO_61_75, classificacao["braco"])
        self.assertTrue(classificacao["criterio_unico_relaxado"])

    def test_classifica_apenas_historico_na_janela_original(self):
        classificacao = classificar_braco(self._candidato(
            features=self._features(minuto=58, historico=10)
        ))

        self.assertEqual(BRACO_HISTORICO_8_11, classificacao["braco"])

    def test_rejeita_quem_falha_em_duas_barreiras(self):
        candidato = self._candidato(
            features=self._features(minuto=67, historico=10)
        )
        self.assertIsNone(classificar_braco(candidato))

        candidato = self._candidato(
            features=self._features(minuto=67, historico=20, chutes=0)
        )
        self.assertIsNone(classificar_braco(candidato))

    def test_nao_relaxa_odd_qualidade_cache_ou_candidato_aprovado(self):
        self.assertIsNone(classificar_braco(self._candidato()))
        self.assertIsNone(classificar_braco(self._candidato(
            features=self._features(minuto=67, historico=20), odd=2.0
        )))
        self.assertIsNone(classificar_braco(self._candidato(
            features=self._features(
                minuto=67, historico=20, qualidade=70
            )
        )))
        self.assertIsNone(classificar_braco(self._candidato(
            features=self._features(
                minuto=67, historico=20, odd_cache=True
            )
        )))

    def test_ancora_exclui_passado_e_congela_um_jogo(self):
        self._inserir(
            1, minutos=-1,
            features=self._features(minuto=67, historico=20),
        )
        self._inserir(
            2, minutos=1, partida_id=20,
            features=self._features(minuto=67, historico=20),
        )
        self._inserir(
            3, minutos=2, partida_id=20,
            features=self._features(minuto=58, historico=10),
        )

        sincronizacao = sincronizar_coorte(self.conexao)
        resumo = resumir_validacao(self.conexao)

        self.assertEqual(1, sincronizacao["inseridos"])
        self.assertFalse(sincronizacao["consulta_resultados"])
        self.assertFalse(sincronizacao["consulta_entregas"])
        self.assertEqual(1, resumo["candidatos"])
        self.assertEqual(
            1, resumo["bracos"][BRACO_MINUTO_61_75]["candidatos"]
        )
        self.assertEqual(
            0, resumo["bracos"][BRACO_HISTORICO_8_11]["candidatos"]
        )

    def test_sincronizacao_nao_consulta_resultados(self):
        self._inserir(
            1, resultado=None,
            features=self._features(minuto=67, historico=20),
        )
        leituras_proibidas = []

        def autorizar(acao, arg1, arg2, banco, gatilho):
            if (
                acao == sqlite3.SQLITE_READ
                and arg1 in {"resultados_sinais", "entregas_alertas"}
            ):
                leituras_proibidas.append((arg1, arg2))
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.conexao.set_authorizer(autorizar)
        try:
            resultado = sincronizar_coorte(self.conexao)
        finally:
            self.conexao.set_authorizer(None)

        self.assertEqual(1, resultado["inseridos"])
        self.assertEqual([], leituras_proibidas)

    def test_resumo_exige_amostra_futura_e_holdout(self):
        for indice in range(1, TAMANHO_POR_BRACO + 1):
            self._inserir(
                indice,
                features=self._features(minuto=67, historico=20),
                odd=2.0 - 0.001 * indice,
                resultado="green",
                retorno=1.0,
            )
        # Odd >=1,90 não pertence ao filtro preciso; usa faixa válida.
        self.conexao.execute(
            "UPDATE sinais SET odd=1.80"
        )
        sincronizar_coorte(self.conexao)
        resumo = resumir_validacao(self.conexao)
        braco = resumo["bracos"][BRACO_MINUTO_61_75]

        self.assertEqual(TAMANHO_POR_BRACO, braco["candidatos"])
        self.assertEqual(42, braco["desenvolvimento"]["validos"])
        self.assertEqual(18, braco["holdout"]["validos"])
        self.assertEqual("favoravel_para_revisao_manual", braco["decisao"])
        self.assertFalse(resumo["promocao_automatica"])
        self.assertFalse(resumo["telegram"])

    def test_adulteracao_da_ancora_falha_fechado(self):
        documento = dict(self.ancora)
        documento["taxa_green_minima"] = 0.5
        self.conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(documento), CHAVE_DEFINICAO),
        )
        with self.assertRaises(RuntimeError):
            resumir_validacao(self.conexao)


if __name__ == "__main__":
    unittest.main()
