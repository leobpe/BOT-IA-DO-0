import json
import sqlite3
import unittest
from datetime import datetime

from gols_antecipados import (
    LINHAGEM_GOLS_ANTECIPADOS,
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
    VERSAO_GOL_HT_ANTECIPADO,
    _clone_antecipado,
)
from linhagem_gols_antecipados import calcular_linhagem_gols_antecipados
from validacao_gols_antecipados import (
    CHAVE_DEFINICAO,
    auditar_validacao_gols_antecipados,
    registrar_ou_validar_gols_antecipados,
    resumir_validacao_gols_antecipados,
)


class ValidacaoGolsAntecipadosTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript("""
            CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
            CREATE TABLE sinais(
              id INTEGER PRIMARY KEY, partida_id INTEGER, criado_em TEXT,
              mercado TEXT, status TEXT, features_json TEXT
            );
            CREATE TABLE resultados_sinais(
              sinal_id INTEGER PRIMARY KEY, resultado TEXT,
              retorno_unidades REAL
            );
            CREATE TABLE entregas_alertas(
              id INTEGER PRIMARY KEY, sinal_id INTEGER, canal TEXT,
              tentado_em TEXT, status TEXT
            );
            CREATE TABLE snapshots(
              id INTEGER PRIMARY KEY, partida_id INTEGER,
              coletado_em TEXT, qualidade_json TEXT
            );
        """)

    def tearDown(self):
        self.conexao.close()

    def _sinal(
        self, identificador, partida, criado_em, linhagem, resultado=None,
        retorno=None,
    ):
        features = {
            "exploracao_sombra": {
                "versao": VERSAO_GOL_FT_ANTECIPADO_2T,
            },
            "gol_antecipado": {"linhagem_sha256": linhagem},
        }
        self.conexao.execute(
            "INSERT INTO sinais VALUES (?, ?, ?, 'gol_ft', 'simulacao', ?)",
            (identificador, partida, criado_em, json.dumps(features)),
        )
        self.conexao.execute(
            "INSERT INTO entregas_alertas VALUES (?, ?, '-1:teste', ?, 'entregue')",
            (identificador, identificador, criado_em),
        )
        if resultado is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?, ?, ?)",
                (identificador, resultado, retorno),
            )

    def _snapshot(self, identificador, partida, criado_em, diagnostico):
        self.conexao.execute(
            "INSERT INTO snapshots VALUES (?, ?, ?, ?)",
            (
                identificador,
                partida,
                criado_em,
                json.dumps({
                    "diagnostico_gols_antecipados": diagnostico,
                }),
            ),
        )

    def test_registro_idempotente_e_divergencia_falha_fechado(self):
        marco = datetime(2026, 8, 20, 12, 0)
        primeiro = registrar_ou_validar_gols_antecipados(
            self.conexao, marco
        )
        segundo = registrar_ou_validar_gols_antecipados(
            self.conexao, datetime(2099, 1, 1)
        )
        self.assertEqual(
            primeiro["definicao"]["registrado_em"],
            segundo["definicao"]["registrado_em"],
        )
        self.assertTrue(
            auditar_validacao_gols_antecipados(
                self.conexao, exigir_registro=True
            )["saudavel"]
        )
        documento = json.loads(self.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
        ).fetchone()["valor"])
        documento["linhagem_sha256"] = "0" * 64
        self.conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(documento), CHAVE_DEFINICAO),
        )
        with self.assertRaisesRegex(RuntimeError, "ancora imutavel"):
            registrar_ou_validar_gols_antecipados(self.conexao)
        auditoria = auditar_validacao_gols_antecipados(
            self.conexao, exigir_registro=True
        )
        self.assertFalse(auditoria["saudavel"])
        self.assertIn(
            f"{CHAVE_DEFINICAO}:linhagem_sha256",
            auditoria["divergencias"],
        )

    def test_clone_carimba_linhagem_exata(self):
        clone = _clone_antecipado(
            {"features": {}, "bloqueios": [], "motivos": []},
            VERSAO_GOL_FT_ANTECIPADO_2T,
            60, ["pre1", "pre2"], ["live1", "live2"], 0.4,
        )
        self.assertEqual(
            clone["features"]["gol_antecipado"]["linhagem_sha256"],
            LINHAGEM_GOLS_ANTECIPADOS,
        )
        self.assertEqual(
            LINHAGEM_GOLS_ANTECIPADOS,
            calcular_linhagem_gols_antecipados()["fingerprint"],
        )

    def test_linhagem_ignora_configuracoes_auxiliares(self):
        componentes = calcular_linhagem_gols_antecipados()["componentes"]
        self.assertNotIn("configuracao.py", componentes["arquivos"])
        self.assertEqual(
            componentes["esquema_linhagem"],
            "gols-antecipados-semantica-v2",
        )
        self.assertIn("odd_elegivel", componentes["configuracao_relevante"])

    def test_resumo_separa_historico_deduplica_e_detecta_linhagem(self):
        marco = datetime(2026, 8, 20, 12, 0)
        registro = registrar_ou_validar_gols_antecipados(
            self.conexao, marco
        )
        fingerprint = registro["definicao"]["linhagem_sha256"]
        self._sinal(1, 10, "2026-08-20T11:00:00", None, "green", 0.6)
        self._sinal(2, 20, "2026-08-20T12:01:00", fingerprint, "green", 0.5)
        # Mesma partida/braço: não pode inflar a coorte.
        self._sinal(3, 20, "2026-08-20T12:02:00", fingerprint, "red", -1.0)
        # Outra partida com fingerprint inválido deve fechar a auditoria.
        self._sinal(4, 30, "2026-08-20T12:03:00", "x" * 64, "red", -1.0)
        self.conexao.commit()

        resumo = resumir_validacao_gols_antecipados(self.conexao)
        braco = resumo["por_braco"][VERSAO_GOL_FT_ANTECIPADO_2T]
        self.assertEqual(braco["candidatos_coorte"], 2)
        self.assertEqual(braco["validos"], 1)
        self.assertEqual(braco["greens"], 1)
        self.assertEqual(braco["linhagem_divergente"], 1)
        self.assertFalse(braco["linhagem_homogenea"])
        self.assertEqual(braco["decisao_estatistica"], "linhagem_inconsistente")
        self.assertEqual(
            braco["historico_observacional"]["greens"], 1
        )

    def test_funil_gerador_explica_bracos_sem_consultar_desfechos(self):
        marco = datetime(2026, 8, 20, 12, 0)
        registrar_ou_validar_gols_antecipados(self.conexao, marco)
        self._snapshot(1, 10, "2026-08-20T12:01:00", {
            "minuto": 12,
            "por_braco": {
                "gol_ht_antecipado": {"estado": "gerado"},
                "gol_ft_antecipado_pre_live": {
                    "estado": "bloqueado",
                    "motivo": "candidato_base_ausente",
                },
            },
        })
        self._snapshot(2, 10, "2026-08-20T12:02:00", {
            "minuto": 15,
            "por_braco": {
                "gol_ht_antecipado": {
                    "estado": "bloqueado",
                    "motivo": "evidencias_ao_vivo_insuficientes",
                },
                "gol_ft_antecipado_pre_live": {"estado": "gerado"},
            },
        })
        # Um bloqueio global dentro da janela de 2T deve ser atribuído somente
        # ao braço FT de segundo tempo.
        self._snapshot(3, 20, "2026-08-20T12:03:00", {
            "minuto": 50,
            "por_braco": {
                "global": {
                    "estado": "bloqueado",
                    "motivo": "evidencias_pre_jogo_insuficientes",
                },
            },
        })
        self._snapshot(4, 30, "2026-08-20T12:04:00", {
            "minuto": 55,
            "por_braco": {
                "gol_ft_antecipado_2t": {"estado": "gerado"},
            },
        })

        resumo = resumir_validacao_gols_antecipados(self.conexao)
        ft_1t = resumo["por_braco"][VERSAO_GOL_FT_ANTECIPADO][
            "funil_gerador"
        ]
        ft_2t = resumo["por_braco"][VERSAO_GOL_FT_ANTECIPADO_2T][
            "funil_gerador"
        ]
        ht = resumo["por_braco"][VERSAO_GOL_HT_ANTECIPADO][
            "funil_gerador"
        ]

        self.assertEqual("com_gerados", ft_1t["estado"])
        self.assertEqual(2, ft_1t["decisoes_observadas"])
        self.assertEqual(1, ft_1t["decisoes_geradas"])
        self.assertEqual(1, ft_1t["partidas_com_alguma_geracao"])
        self.assertEqual(
            {"candidato_base_ausente": 1},
            ft_1t["motivos_bloqueio_decisoes"],
        )
        self.assertEqual(2, ht["decisoes_observadas"])
        self.assertEqual(1, ht["decisoes_geradas"])
        self.assertEqual(2, ft_2t["decisoes_observadas"])
        self.assertEqual(1, ft_2t["decisoes_geradas"])
        self.assertEqual(
            {"evidencias_pre_jogo_insuficientes": 1},
            ft_2t["motivos_bloqueio_decisoes"],
        )
        self.assertFalse(ft_2t["consulta_resultados"])
        self.assertFalse(ft_2t["consulta_entregas"])
        self.assertFalse(ft_2t["altera_sinais"])
        self.assertFalse(ft_2t["altera_telegram"])

    def test_funil_gerador_declara_telemetria_ainda_indisponivel(self):
        registrar_ou_validar_gols_antecipados(
            self.conexao, datetime(2026, 8, 20, 12, 0)
        )
        resumo = resumir_validacao_gols_antecipados(self.conexao)
        funil = resumo["por_braco"][VERSAO_GOL_FT_ANTECIPADO][
            "funil_gerador"
        ]
        self.assertEqual("telemetria_indisponivel", funil["estado"])
        self.assertFalse(funil["telemetria_disponivel"])


if __name__ == "__main__":
    unittest.main()
