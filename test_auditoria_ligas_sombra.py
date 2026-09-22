import sqlite3
import json
import unittest

from auditoria_ligas_sombra import (
    auditar_ligas_por_mercado,
    carregar_resultados_ligas_metodo_grupo,
    avaliar_ligas_sombra,
    avaliar_validacao_prospectiva_ligas,
    registrar_ou_obter_validacao_prospectiva_ligas,
)


def _itens(liga, retornos):
    return [
        {
            "liga": liga,
            "retorno_unidades": retorno,
            "odd": 1.80,
            "minuto": 60,
        }
        for retorno in retornos
    ]


class AuditoriaLigasSombraTest(unittest.TestCase):
    def test_pequena_amostra_nao_cria_blacklist(self):
        resultado = avaliar_ligas_sombra(
            _itens("liga_ruim", [-1.0] * 20), minimo_total=60
        )
        self.assertEqual(resultado["estado"], "aguardando_amostra")
        self.assertEqual(resultado["ligas_exclusao_candidatas"], [])
        self.assertFalse(resultado["promocao_permitida"])

    def test_liga_negativa_historica_ainda_exige_validacao_prospectiva(self):
        desenvolvimento = (
            _itens("liga_ruim", [-1.0] * 20)
            + _itens("liga_boa", [0.8, -1.0] * 25)
        )
        validacao = (
            _itens("liga_ruim", [-1.0] * 12)
            + _itens("liga_boa", [0.8] * 18)
        )
        resultado = avaliar_ligas_sombra(
            desenvolvimento + validacao,
            minimo_total=60,
            reserva_minima=30,
            maximo_desenvolvimento=70,
            minimo_por_liga=8,
            minimo_excluidos_validacao=10,
        )
        self.assertEqual(
            resultado["estado"],
            "evidencia_historica_exige_validacao_prospectiva",
        )
        self.assertEqual(
            resultado["ligas_exclusao_candidatas"], ["liga_ruim"]
        )
        self.assertGreater(resultado["cobertura_condicional_taxa"], 0.99)
        self.assertGreater(
            resultado["limite_inferior_delta_ajustado_95"], 0
        )
        self.assertTrue(resultado["evidencia_historica_favoravel"])
        self.assertFalse(resultado["promocao_permitida"])

    def test_candidato_sem_presenca_futura_fica_inconclusivo(self):
        desenvolvimento = (
            _itens("liga_ruim", [-1.0] * 12)
            + _itens("liga_boa", [0.8, -1.0] * 14)
        )
        validacao = _itens("liga_boa", [0.8] * 20)
        resultado = avaliar_ligas_sombra(
            desenvolvimento + validacao,
            minimo_total=60,
            reserva_minima=20,
            maximo_desenvolvimento=40,
            minimo_por_liga=8,
            minimo_excluidos_validacao=10,
        )
        self.assertEqual(
            resultado["estado"], "validacao_excluida_insuficiente"
        )
        self.assertFalse(resultado["evidencia_historica_favoravel"])

    def test_total_suficiente_sem_oito_por_liga_nao_declara_conclusao(self):
        itens = []
        for indice in range(20):
            itens.extend(_itens(f"liga_{indice}", [0.8, -1.0] * 2))
        resultado = avaliar_ligas_sombra(itens)

        self.assertEqual(
            resultado["estado"], "amostra_por_liga_insuficiente"
        )
        self.assertEqual(resultado["ligas_testadas"], 0)

    def test_liga_nao_e_culpada_quando_prejuizo_vem_da_faixa_de_odd_minuto(self):
        itens = []
        for indice in range(80):
            dificil = indice % 2 == 0
            itens.append({
                "liga": "liga_a" if indice % 4 < 2 else "liga_b",
                "retorno_unidades": -1.0 if dificil else 0.8,
                "odd": 1.40 if dificil else 2.10,
                "minuto": 75 if dificil else 55,
            })
        resultado = avaliar_ligas_sombra(
            itens,
            minimo_total=60,
            reserva_minima=20,
            maximo_desenvolvimento=60,
        )

        self.assertEqual(resultado["ligas_exclusao_candidatas"], [])
        self.assertFalse(resultado["evidencia_historica_favoravel"])

    def test_ancora_prospectiva_congela_ligas_e_inicio(self):
        conexao = sqlite3.connect(":memory:")
        conexao.execute(
            "CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT)"
        )
        primeira = registrar_ou_obter_validacao_prospectiva_ligas(
            conexao,
            "gol_ft",
            "regra-v1",
            "fp-1",
            ["liga_b", "liga_a"],
            "2026-08-25T10:00:00",
            registrado_em="2026-08-25T10:01:00",
        )
        repetida = registrar_ou_obter_validacao_prospectiva_ligas(
            conexao,
            "gol_ft",
            "regra-v1",
            "fp-1",
            ["liga_a", "liga_b"],
            "2026-08-25T10:00:00",
        )

        self.assertEqual(
            primeira["ligas_exclusao_congeladas"], ["liga_a", "liga_b"]
        )
        self.assertEqual(repetida, primeira)
        with self.assertRaises(RuntimeError):
            registrar_ou_obter_validacao_prospectiva_ligas(
                conexao,
                "gol_ft",
                "regra-v1",
                "fp-1",
                ["liga_c"],
                "2026-08-25T10:00:00",
            )
        conexao.close()

    def test_validacao_futura_confirma_exclusao_sem_alterar_sinais(self):
        ancora = {
            "inicio_apos": "2026-08-25T09:59:59",
            "ligas_exclusao_congeladas": ["liga_ruim"],
            "tamanho_coorte": 100,
            "minimo_excluidos": 20,
        }
        itens = []
        for indice in range(100):
            itens.append({
                "criado_em": f"2026-08-25T10:{indice // 60:02d}:{indice % 60:02d}",
                "liga": "liga_ruim" if indice < 20 else "liga_boa",
                "retorno_unidades": -1.0 if indice < 20 else 0.8,
            })

        resultado = avaliar_validacao_prospectiva_ligas(itens, ancora)

        self.assertEqual(
            resultado["estado"], "pronta_para_revisao_independente"
        )
        self.assertTrue(resultado["evidencia_favoravel"])
        self.assertGreater(resultado["limite_inferior_delta_95"], 0)
        self.assertFalse(resultado["promocao_permitida"])
        self.assertFalse(resultado["altera_sinais"])

    def test_validacao_futura_nao_confirma_liga_que_se_recuperou(self):
        ancora = {
            "inicio_apos": "2026-08-25T10:00:00",
            "ligas_exclusao_congeladas": ["liga_ruim"],
            "tamanho_coorte": 100,
            "minimo_excluidos": 20,
        }
        itens = [
            {
                "criado_em": f"2026-08-25T11:{indice // 60:02d}:{indice % 60:02d}",
                "liga": "liga_ruim" if indice < 20 else "liga_boa",
                "retorno_unidades": 0.8,
            }
            for indice in range(100)
        ]

        resultado = avaliar_validacao_prospectiva_ligas(itens, ancora)

        self.assertEqual(resultado["estado"], "filtro_ligas_nao_confirmado")
        self.assertFalse(resultado["evidencia_favoravel"])

    def test_metodo_grupo_conta_so_entregues_e_primeiro_por_partida(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
          CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT);
          CREATE TABLE partidas(
            id INTEGER PRIMARY KEY, liga TEXT, liga_normalizada TEXT
          );
          CREATE TABLE sinais(
            id INTEGER PRIMARY KEY, partida_id INTEGER, criado_em TEXT,
            mercado TEXT, status TEXT, odd REAL, features_json TEXT
          );
          CREATE TABLE resultados_sinais(
            sinal_id INTEGER PRIMARY KEY, resultado TEXT,
            retorno_unidades REAL
          );
          CREATE TABLE entregas_alertas(
            id INTEGER PRIMARY KEY, sinal_id INTEGER, canal TEXT, status TEXT
          );
        """)
        conexao.executemany(
            "INSERT INTO partidas VALUES (?, ?, ?)",
            [(10, "Liga A", "liga_a"), (20, "Liga B", "liga_b")],
        )
        features = json.dumps({
            "minuto": 60,
            "exploracao_sombra": {"versao": "v2b"},
            "gol_capacidade_contextual_v2": {
                "linhagem_sha256": "linhagem-correta"
            },
        })
        conexao.executemany(
            "INSERT INTO sinais VALUES (?, ?, ?, 'gol_ft', 'simulacao', ?, ?)",
            [
                (1, 10, "2026-08-26T10:01:00", 1.80, features),
                (2, 10, "2026-08-26T10:02:00", 1.90, features),
                (3, 20, "2026-08-26T10:03:00", 1.75, features),
            ],
        )
        conexao.executemany(
            "INSERT INTO resultados_sinais VALUES (?, ?, ?)",
            [(1, "green", 0.8), (2, "red", -1.0), (3, "green", 0.75)],
        )
        conexao.executemany(
            "INSERT INTO entregas_alertas VALUES (?, ?, ?, 'entregue')",
            [
                (1, 1, "telegram:teste"),
                (2, 2, "telegram:teste"),
                (3, 3, "telegram:teste:resultado"),
            ],
        )
        itens = carregar_resultados_ligas_metodo_grupo(
            conexao,
            "gol_ft",
            "v2b",
            inicio="2026-08-26T10:00:00",
            linhagem="linhagem-correta",
        )

        self.assertEqual([1], [item["id"] for item in itens])
        self.assertEqual("liga_a", itens[0]["liga"])
        self.assertEqual(60, itens[0]["minuto"])
        conexao.close()

    def test_auditoria_publica_coorte_v2b_sem_aplicar_filtro(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript("""
          CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT);
          CREATE TABLE partidas(
            id INTEGER PRIMARY KEY, liga TEXT, liga_normalizada TEXT
          );
          CREATE TABLE sinais(
            id INTEGER PRIMARY KEY, partida_id INTEGER, criado_em TEXT,
            mercado TEXT, status TEXT, odd REAL, features_json TEXT
          );
          CREATE TABLE resultados_sinais(
            sinal_id INTEGER PRIMARY KEY, resultado TEXT,
            retorno_unidades REAL
          );
          CREATE TABLE entregas_alertas(
            id INTEGER PRIMARY KEY, sinal_id INTEGER, canal TEXT, status TEXT
          );
        """)
        resultado = auditar_ligas_por_mercado(
            conexao,
            {},
            metodos_grupo={
                "gol_ft_v2b": {
                    "mercado": "gol_ft",
                    "versao_exploracao": "v2b",
                    "inicio": "2026-08-26T10:00:00",
                    "linhagem": "linhagem-correta",
                }
            },
        )

        v2b = resultado["por_metodo_grupo"]["gol_ft_v2b"]
        self.assertTrue(resultado["integro"])
        self.assertEqual("aguardando_amostra", v2b["estado"])
        self.assertEqual(0, v2b["amostra"])
        self.assertFalse(v2b["aplicacao_automatica"])
        self.assertFalse(v2b["altera_sinais"])
        conexao.close()
