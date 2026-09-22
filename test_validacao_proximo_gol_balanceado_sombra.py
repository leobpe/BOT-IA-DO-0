import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from proximo_gol_balanceado_sombra import (
    registrar_ou_validar_definicao,
)
from politica_proximo_gol_preciso import MOTIVO_PRESSAO
from validacao_proximo_gol_balanceado_sombra import (
    resumir_validacao_proximo_gol_balanceado,
)
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)


class ValidacaoProximoGolBalanceadoSombraTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE snapshots (
              id INTEGER PRIMARY KEY, placar TEXT
            );
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id TEXT, snapshot_id INTEGER,
              criado_em TEXT, mercado TEXT, status TEXT, regra_versao TEXT,
              features_json TEXT, odd REAL, motivos_json TEXT,
              pontuacao_tecnica REAL
            );
            CREATE TABLE resultados_sinais (
              sinal_id INTEGER PRIMARY KEY, resultado TEXT,
              retorno_unidades REAL
            );
            """
        )
        self.inicio = datetime(2026, 9, 8, 18, 0, 0)
        self.documento = registrar_ou_validar_definicao(
            self.conexao, self.inicio
        )

    def tearDown(self):
        self.conexao.close()

    def _inserir(self, indice, partida, gols, resultado="green", retorno=0.5,
                  versao=None, sha=None, referencia_sem_vig=False):
        momento = self.inicio + timedelta(minutes=indice)
        self.conexao.execute(
            "INSERT INTO snapshots(id,placar) VALUES (?,?)",
            (indice, f"{gols}-0"),
        )
        features = {
            "gols_atuais": gols,
            "exploracao_sombra": {
                "versao": versao or VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            },
            "proximo_gol_balanceado_sombra": {
                "definicao_sha256": sha or self.documento["definicao_sha256"],
            },
        }
        if referencia_sem_vig:
            features.update({
                "selecao_mercado": "casa",
                "odds_mercado_sincronizadas": {
                    "casa": 1.70,
                    "visitante": 3.20,
                    "sem_gol": 5.00,
                },
                "mercado_odds_sincronizado": True,
            })
        self.conexao.execute(
            """
            INSERT INTO sinais(
              id,partida_id,snapshot_id,criado_em,mercado,status,
              regra_versao,features_json
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                indice, partida, indice, momento.isoformat(), "proximo_gol",
                "simulacao", VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
                json.dumps(features),
            ),
        )
        if resultado is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?,?,?)",
                (indice, resultado, retorno),
            )

    def _inserir_origem(self, indice, partida, odd=1.55):
        identificador = 1000 + indice
        momento = self.inicio + timedelta(minutes=indice)
        self.conexao.execute(
            "INSERT INTO snapshots(id,placar) VALUES (?,?)",
            (identificador, "0-0"),
        )
        features = {
            "gols_atuais": 0,
            "minuto": 50,
            "qualidade_dados": 100,
            "lado_dominante": "casa",
            "chutes_lado_dominante_5min": 1,
            "janelas": {"5": {
                "pressao_pico": [60, 25],
                "pressao_media": [45, 25],
            }},
        }
        self.conexao.execute(
            """
            INSERT INTO sinais(
              id,partida_id,snapshot_id,criado_em,mercado,status,
              regra_versao,features_json,odd,motivos_json,pontuacao_tecnica
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                identificador, partida, identificador,
                momento.isoformat(), "proximo_gol", "rejeitado",
                VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
                json.dumps(features), odd,
                json.dumps(["bloqueio:" + MOTIVO_PRESSAO]),
                60,
            ),
        )

    def test_deduplica_por_partida_e_estado_de_gols(self):
        self._inserir(1, "jogo-a", 0)
        self._inserir(2, "jogo-a", 0)
        self._inserir(3, "jogo-a", 1)
        resumo = resumir_validacao_proximo_gol_balanceado(self.conexao)
        self.assertEqual(2, resumo["candidatos"])
        self.assertEqual(38, resumo["faltam"])
        self.assertEqual("somente_grupo_teste", resumo["telegram"])
        self.assertFalse(resumo["telegram_oficial"])
        self.assertFalse(resumo["promocao_automatica"])

    def test_reporta_referencia_sem_vig_sem_alterar_decisao(self):
        self._inserir(
            1, "jogo-a", 0, "green", 0.70, referencia_sem_vig=True
        )
        self._inserir(
            2, "jogo-b", 0, "red", -1.0, referencia_sem_vig=True
        )

        resumo = resumir_validacao_proximo_gol_balanceado(self.conexao)

        referencia = resumo["referencia_sem_vig"]
        self.assertEqual(2, referencia["cobertura"])
        self.assertEqual(1.0, referencia["taxa_cobertura"])
        self.assertEqual("aguardando_amostra_futura", resumo["decisao"])
        self.assertFalse(resumo["promocao_automatica"])

    def test_coorte_fixa_favoravel_exige_dev_holdout_e_ic_positivo(self):
        for indice in range(1, 41):
            retorno = 0.3 if indice % 5 else 0.1
            self._inserir(
                indice,
                f"jogo-{indice}",
                0,
                "green",
                retorno,
                referencia_sem_vig=True,
            )
        resumo = resumir_validacao_proximo_gol_balanceado(self.conexao)
        self.assertTrue(resumo["coorte_fechada"])
        self.assertEqual("encerrada", resumo["estado"])
        self.assertEqual(
            "favoravel_para_revisao_manual", resumo["decisao"]
        )
        self.assertEqual(28, resumo["desenvolvimento"]["validos"])
        self.assertEqual(12, resumo["holdout"]["validos"])
        self.assertTrue(resumo["gate_preco_justo"]["satisfeito"])

    def test_roi_positivo_sem_referencia_sem_vig_nao_comprova_edge(self):
        for indice in range(1, 41):
            self._inserir(
                indice, f"jogo-sem-preco-{indice}", 0, "green", 0.3
            )

        resumo = resumir_validacao_proximo_gol_balanceado(self.conexao)

        self.assertEqual(
            "inconclusiva_ou_desfavoravel", resumo["decisao"]
        )
        self.assertFalse(resumo["gate_preco_justo"]["satisfeito"])
        self.assertEqual(
            0, resumo["referencia_sem_vig"]["cobertura"]
        )

    def test_edge_sem_vig_precisa_se_repetir_no_holdout(self):
        for indice in range(1, 41):
            self._inserir(
                indice,
                f"jogo-holdout-sem-preco-{indice}",
                0,
                "green",
                0.3,
                referencia_sem_vig=indice <= 28,
            )

        resumo = resumir_validacao_proximo_gol_balanceado(self.conexao)

        self.assertEqual(
            "inconclusiva_ou_desfavoravel", resumo["decisao"]
        )
        self.assertGreaterEqual(
            resumo["gate_preco_justo"]["cobertura_observada"], 0.7
        )
        self.assertEqual(
            0,
            resumo["gate_preco_justo"]["holdout"][
                "cobertura_observada"
            ],
        )
        self.assertFalse(resumo["gate_preco_justo"]["satisfeito"])

    def test_nao_mistura_linhagem_e_aguarda_resultados(self):
        for indice in range(1, 40):
            self._inserir(indice, f"jogo-{indice}", 0)
        self._inserir(40, "jogo-40", 0, resultado=None)
        self._inserir(41, "fora", 0, versao="outra-versao")
        resumo = resumir_validacao_proximo_gol_balanceado(self.conexao)
        self.assertEqual(40, resumo["candidatos"])
        self.assertEqual(1, resumo["pendentes"])
        self.assertEqual("aguardando_resultados", resumo["decisao"])

    def test_alerta_desfavoravel_exige_20_e_ic95_totalmente_negativo(self):
        for indice in range(1, 20):
            self._inserir(
                indice, f"jogo-negativo-{indice}", 0, "red", -1.0
            )
        antes = resumir_validacao_proximo_gol_balanceado(self.conexao)
        self.assertFalse(antes["alerta_desfavoravel"])
        self.assertFalse(antes["rollback_recomendado"])

        self._inserir(20, "jogo-negativo-20", 0, "red", -1.0)
        depois = resumir_validacao_proximo_gol_balanceado(self.conexao)
        self.assertTrue(depois["alerta_desfavoravel"])
        self.assertTrue(depois["rollback_recomendado"])
        self.assertTrue(
            depois["politica_seguranca_grupo"]["coleta_sombra_continua"]
        )

    def test_checkpoint_negativo_nao_e_recalculado_opcionalmente(self):
        for indice in range(1, 41):
            if indice <= 20 and indice % 2:
                resultado, retorno = "green", 0.5
            else:
                resultado, retorno = "red", -1.0
            self._inserir(
                indice,
                f"jogo-checkpoint-{indice}",
                0,
                resultado,
                retorno,
            )

        resumo = resumir_validacao_proximo_gol_balanceado(self.conexao)

        self.assertLess(resumo["intervalo_roi_95"][1], 0)
        self.assertGreater(
            resumo["checkpoint_seguranca"]["intervalo_roi_95"][1], 0
        )
        self.assertFalse(resumo["alerta_desfavoravel"])
        self.assertTrue(resumo["resultados_completos"])

    def test_funil_mostra_criterio_que_elimina_oportunidades(self):
        self._inserir_origem(1, "origem-a", odd=1.55)
        self._inserir_origem(2, "origem-b", odd=1.70)
        resumo = resumir_validacao_proximo_gol_balanceado(self.conexao)
        funil = resumo["funil_origem_v10f"]
        self.assertEqual(2, funil["estados_independentes"])
        self.assertEqual(2, funil["funil_cumulativo"]["minuto_ate_75"])
        self.assertEqual(1, funil["funil_cumulativo"]["odd_140_164"])
        self.assertEqual(
            1, funil["funil_cumulativo"]["vantagem_pressao_media_10"]
        )
        self.assertEqual("odd_140_164", funil["gargalo_principal"])
        self.assertEqual(
            "odd_140_164", funil["gargalo_principal_interno"]
        )
        self.assertFalse(funil["altera_sinal"])


if __name__ == "__main__":
    unittest.main()
