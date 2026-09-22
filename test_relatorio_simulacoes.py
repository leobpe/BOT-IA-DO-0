import json
import sqlite3
import unittest
from datetime import datetime
from unittest.mock import patch

from relatorio_simulacoes import (
    VERSAO_CONCLUSAO_EXPERIMENTO_FILTRO,
    VERSAO_EXPERIMENTO_FILTRO,
    avaliar_drift_simulacoes,
    avaliar_drift_simulacoes_por_mercado,
    auditar_experimento_filtro,
    comparar_filtros_por_mercado,
    comparar_filtro_simulacoes,
    obter_experimento_filtro,
    obter_conclusao_experimento_filtro,
    registrar_ou_obter_conclusao_experimento_filtro,
    registrar_ou_obter_experimento_filtro,
    resumir_simulacoes,
)


class RelatorioSimulacoesTest(unittest.TestCase):
    def test_compara_cada_mercado_na_sua_propria_linhagem(self):
        retorno = {
            "comparacao": {"proximo_gol": {"estado": "amostra_insuficiente"}},
            "enviadas": {"proximo_gol": {"amostra": 8}},
            "filtradas": {"proximo_gol": {"amostra": 7}},
        }
        with patch(
            "relatorio_simulacoes.comparar_filtro_simulacoes",
            return_value=retorno,
        ) as comparar:
            conexao = object()
            resultado = comparar_filtros_por_mercado(
                conexao,
                {"proximo_gol": "regra-v10e"},
                {"regra-v10e": "fingerprint-v10e"},
            )

        self.assertEqual(resultado[0]["mercado"], "proximo_gol")
        self.assertEqual(resultado[0]["regra_versao"], "regra-v10e")
        self.assertEqual(resultado[0]["enviadas"]["amostra"], 8)
        comparar.assert_called_once_with(
            conexao,
            regra_versao="regra-v10e",
            regra_fingerprint="fingerprint-v10e",
            amostra_minima=30,
        )

    def test_experimento_prospectivo_usa_versao_dois(self):
        self.assertEqual(
            VERSAO_EXPERIMENTO_FILTRO, "filtro-simulacoes-v2"
        )

    @staticmethod
    def _banco_drift(retornos):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                criado_em TEXT, mercado TEXT, regra_versao TEXT
            );
            CREATE TABLE entregas_alertas (
                id INTEGER PRIMARY KEY, sinal_id INTEGER,
                canal TEXT, status TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER, resultado TEXT,
                retorno_unidades REAL, encerrado_em TEXT
            );
            """
        )
        for indice, retorno in enumerate(retornos, start=1):
            minuto = indice % 60
            hora = 10 + indice // 60
            instante = f"2026-07-22T{hora:02d}:{minuto:02d}:00"
            resultado = "green" if retorno > 0 else "red"
            conexao.execute(
                "INSERT INTO sinais VALUES (?, ?, ?, ?, ?)",
                (indice, indice, instante, "gol_ft", "sinais-v4"),
            )
            conexao.execute(
                "INSERT INTO entregas_alertas VALUES (?, ?, ?, ?)",
                (indice, indice, "10:teste", "entregue"),
            )
            conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?, ?, ?, ?)",
                (indice, resultado, retorno, instante),
            )
        return conexao

    @staticmethod
    def _banco_auditoria_filtro():
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE metadados (
                chave TEXT PRIMARY KEY, valor TEXT NOT NULL
            );
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, criado_em TEXT NOT NULL,
                regra_versao TEXT NOT NULL, pontuacao_tecnica REAL,
                features_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE entregas_alertas (
                id INTEGER PRIMARY KEY, sinal_id INTEGER NOT NULL,
                canal TEXT NOT NULL, status TEXT NOT NULL, erro TEXT
            );
            CREATE TRIGGER trg_experimento_filtro_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'experimento_filtro_teste:%'
              OR NEW.chave LIKE 'experimento_filtro_teste:%'
            BEGIN
                SELECT RAISE(ABORT, 'marco imutavel');
            END;
            CREATE TRIGGER trg_experimento_filtro_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'experimento_filtro_teste:%'
            BEGIN
                SELECT RAISE(ABORT, 'marco imutavel');
            END;
            CREATE TRIGGER
                trg_conclusao_experimento_filtro_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'conclusao_experimento_filtro:%'
              OR NEW.chave LIKE 'conclusao_experimento_filtro:%'
            BEGIN
                SELECT RAISE(ABORT, 'conclusao imutavel');
            END;
            CREATE TRIGGER
                trg_conclusao_experimento_filtro_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'conclusao_experimento_filtro:%'
            BEGIN
                SELECT RAISE(ABORT, 'conclusao imutavel');
            END;
            """
        )
        registrar_ou_obter_experimento_filtro(
            conexao, "sinais-v4", 80, 80,
            datetime(2026, 7, 22, 18, 10, 8),
        )
        return conexao

    def test_audita_envios_e_filtros_coerentes_com_decisao_original(self):
        conexao = self._banco_auditoria_filtro()
        conexao.executescript(
            """
            INSERT INTO sinais VALUES
                (1, '2026-07-22T18:11:00', 'sinais-v4', 90,
                 '{"qualidade_dados": 92}'),
                (2, '2026-07-22T18:12:00', 'sinais-v4', 75,
                 '{"qualidade_dados": 95}'),
                (3, '2026-07-22T18:13:00', 'sinais-v4', 85,
                 '{"qualidade_dados": 70}');
            INSERT INTO entregas_alertas VALUES
                (1, 1, '-100:teste', 'entregue', NULL),
                (2, 2, 'gateway:teste', 'filtrado',
                 'pontuacao_teste_insuficiente'),
                (3, 3, 'gateway:teste', 'filtrado',
                 'qualidade_teste_insuficiente');
            """
        )

        auditoria = auditar_experimento_filtro(
            conexao, "sinais-v4", 80, 80
        )

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["decisoes_enviadas_auditadas"], 1)
        self.assertEqual(auditoria["decisoes_filtradas_auditadas"], 2)
        self.assertEqual(
            auditoria["simulacoes_enviadas_fora_criterio"], 0
        )
        self.assertEqual(auditoria["filtros_motivo_incoerente"], 0)
        conexao.close()

    def test_rejeita_envio_abaixo_da_nota_ou_sem_qualidade_valida(self):
        conexao = self._banco_auditoria_filtro()
        conexao.executescript(
            """
            INSERT INTO sinais VALUES
                (1, '2026-07-22T18:11:00', 'sinais-v4', 79,
                 '{"qualidade_dados": 95}'),
                (2, '2026-07-22T18:12:00', 'sinais-v4', 90, '{}'),
                (3, '2026-07-22T18:13:00', 'sinais-v4', 90,
                 'json-invalido');
            INSERT INTO entregas_alertas VALUES
                (1, 1, '-100:teste', 'entregue', NULL),
                (2, 2, '-100:teste', 'entregue', NULL),
                (3, 3, '-100:teste', 'entregue', NULL);
            """
        )

        auditoria = auditar_experimento_filtro(
            conexao, "sinais-v4", 80, 80
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["motivo"], "envios_fora_criterio_filtro")
        self.assertEqual(
            auditoria["simulacoes_enviadas_fora_criterio"], 3
        )
        conexao.close()

    def test_rejeita_motivo_de_filtro_incompativel_com_os_dados(self):
        conexao = self._banco_auditoria_filtro()
        conexao.executescript(
            """
            INSERT INTO sinais VALUES
                (1, '2026-07-22T18:11:00', 'sinais-v4', 90,
                 '{"qualidade_dados": 95}'),
                (2, '2026-07-22T18:12:00', 'sinais-v4', 70,
                 '{"qualidade_dados": 60}'),
                (3, '2026-07-22T18:13:00', 'sinais-v4', 90,
                 '{"qualidade_dados": 70}');
            INSERT INTO entregas_alertas VALUES
                (1, 1, 'gateway:teste', 'filtrado',
                 'pontuacao_teste_insuficiente'),
                (2, 2, 'gateway:teste', 'filtrado',
                 'qualidade_teste_insuficiente'),
                (3, 3, 'gateway:teste', 'filtrado', 'motivo_desconhecido');
            """
        )

        auditoria = auditar_experimento_filtro(
            conexao, "sinais-v4", 80, 80
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["motivo"], "motivos_filtro_incoerentes")
        self.assertEqual(auditoria["filtros_motivo_incoerente"], 3)
        conexao.close()

    def test_separa_mercados_e_calcula_roi_sem_contar_pendentes(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                criado_em TEXT, mercado TEXT, regra_versao TEXT,
                status TEXT
            );
            CREATE TABLE entregas_alertas (
                sinal_id INTEGER, canal TEXT, status TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER, resultado TEXT,
                retorno_unidades REAL, encerrado_em TEXT
            );
            INSERT INTO sinais VALUES
                (1, 1, '2026-07-21T11:00:00', 'gol_ft', 'sinais-v3', 'simulacao'),
                (2, 1, '2026-07-21T11:05:00', 'gol_ft', 'sinais-v3', 'simulacao'),
                (3, 2, '2026-07-21T11:00:00', 'proximo_escanteio', 'sinais-v3', 'simulacao'),
                (4, 3, '2026-07-21T11:00:00', 'gol_ft', 'sinais-v3', 'simulacao');
            INSERT INTO entregas_alertas VALUES
                (1, '10:teste', 'entregue'),
                (1, '10:teste:resultado', 'entregue'),
                (2, '10:teste', 'entregue'),
                (3, '20:teste', 'entregue'),
                (4, '10:teste', 'entregue');
            INSERT INTO resultados_sinais VALUES
                (1, 'green', 0.80, '2026-07-21T12:00:00'),
                (2, 'red', -1.00, '2026-07-21T12:00:30'),
                (3, 'red', -1.00, '2026-07-21T12:01:00');
            """
        )

        resumo = resumir_simulacoes(conexao, "sinais-v3")

        self.assertEqual(resumo["geral"]["entregues"], 4)
        self.assertEqual(resumo["geral"]["amostra"], 2)
        self.assertEqual(resumo["geral"]["pendentes"], 1)
        self.assertEqual(resumo["geral"]["resultados_brutos"], 2)
        self.assertEqual(
            resumo["geral"]["excluidos_nao_primeira_decisao"], 1
        )
        self.assertEqual(resumo["geral"]["roi"], -0.1)
        self.assertEqual(resumo["gol_ft"]["greens"], 1)
        self.assertEqual(resumo["gol_ft"]["reds"], 0)
        self.assertEqual(resumo["gol_ft"]["amostra"], 1)
        self.assertEqual(resumo["proximo_escanteio"]["reds"], 1)
        conexao.close()

    def test_compara_filtro_sem_reclassificar_depois_do_resultado(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                criado_em TEXT, mercado TEXT, regra_versao TEXT,
                status TEXT, pontuacao_tecnica REAL
            );
            CREATE TABLE entregas_alertas (
                id INTEGER PRIMARY KEY, sinal_id INTEGER,
                canal TEXT, status TEXT, erro TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER, resultado TEXT,
                retorno_unidades REAL, encerrado_em TEXT
            );
            INSERT INTO sinais VALUES
                (1, 1, '2026-07-22T10:00:00', 'gol_ft',
                 'sinais-v4', 'simulacao', 90),
                (2, 2, '2026-07-22T10:01:00', 'gol_ft',
                 'sinais-v4', 'aprovado', 75),
                (3, 3, '2026-07-22T10:02:00', 'gol_ft',
                 'sinais-v4', 'simulacao', 92),
                (4, 4, '2026-07-22T10:03:00', 'gol_ft',
                 'sinais-v4', 'aprovado', 72),
                (5, 1, '2026-07-22T10:04:00', 'gol_ft',
                 'sinais-v4', 'duplicado', 99),
                (6, 99, '2026-07-22T09:59:00', 'gol_ft',
                 'sinais-v4', 'simulacao', 99);
            INSERT INTO entregas_alertas VALUES
                (1, 1, '10:teste', 'entregue', NULL),
                (2, 2, 'gateway:teste', 'filtrado',
                 'pontuacao_teste_insuficiente'),
                (3, 3, '10:teste', 'entregue', NULL),
                (4, 4, 'gateway:teste', 'filtrado',
                 'qualidade_teste_insuficiente'),
                (5, 5, '10:teste', 'entregue', NULL),
                (6, 6, '10:teste', 'entregue', NULL);
            INSERT INTO resultados_sinais VALUES
                (1, 'green', 0.80, '2026-07-22T12:00:00'),
                (2, 'red', -1.00, '2026-07-22T12:01:00'),
                (3, 'green', 0.90, '2026-07-22T12:02:00'),
                (4, 'red', -1.00, '2026-07-22T12:03:00'),
                (5, 'red', -1.00, '2026-07-22T12:04:00'),
                (6, 'green', 1.00, '2026-07-22T12:05:00');
            """
        )

        resumo = comparar_filtro_simulacoes(
            conexao,
            "sinais-v4",
            amostra_minima=2,
            iniciado_em="2026-07-22T10:00:00",
        )

        enviadas = resumo["enviadas"]["gol_ft"]
        filtradas = resumo["filtradas"]["gol_ft"]
        comparacao = resumo["comparacao"]["gol_ft"]
        self.assertEqual(enviadas["amostra"], 2)
        self.assertEqual(enviadas["greens"], 2)
        self.assertEqual(filtradas["amostra"], 2)
        self.assertEqual(filtradas["reds"], 2)
        self.assertEqual(
            filtradas["motivos_filtro"],
            {
                "pontuacao_teste_insuficiente": 1,
                "qualidade_teste_insuficiente": 1,
            },
        )
        self.assertEqual(comparacao["estado"], "avaliavel")
        self.assertEqual(comparacao["delta_taxa_acerto"], 1.0)
        self.assertEqual(comparacao["delta_roi"], 1.85)
        self.assertEqual(comparacao["decisao"], "evidencia_favoravel")
        self.assertFalse(comparacao["aplicacao_automatica"])
        self.assertGreater(
            comparacao["intervalo_delta_roi_95"][0], 0
        )
        self.assertGreaterEqual(
            comparacao["intervalo_delta_taxa_acerto_95"][0], 0
        )
        conexao.close()

    def test_comparacao_nao_publica_delta_com_amostra_pequena(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                criado_em TEXT, mercado TEXT, regra_versao TEXT,
                status TEXT, pontuacao_tecnica REAL
            );
            CREATE TABLE entregas_alertas (
                id INTEGER PRIMARY KEY, sinal_id INTEGER,
                canal TEXT, status TEXT, erro TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER, resultado TEXT,
                retorno_unidades REAL, encerrado_em TEXT
            );
            INSERT INTO sinais VALUES
                (1, 1, '2026-07-22T10:00:00', 'gol_ft',
                 'sinais-v4', 'simulacao', 90),
                (2, 2, '2026-07-22T10:01:00', 'gol_ft',
                 'sinais-v4', 'aprovado', 75),
                (3, 3, '2026-07-22T10:02:00', 'gol_ft',
                 'sinais-v4', 'aprovado', 88),
                (4, 4, '2026-07-22T10:03:00', 'gol_ft',
                 'sinais-v4', 'aprovado', 73);
            INSERT INTO entregas_alertas VALUES
                (1, 1, '10:teste', 'entregue', NULL),
                (2, 2, 'gateway:teste', 'filtrado',
                 'pontuacao_teste_insuficiente'),
                (3, 3, '10:teste', 'entregue', NULL),
                (4, 4, 'gateway:teste', 'filtrado',
                 'pontuacao_teste_insuficiente');
            INSERT INTO resultados_sinais VALUES
                (1, 'green', 0.80, '2026-07-22T12:00:00'),
                (2, 'red', -1.00, '2026-07-22T12:01:00');
            """
        )

        comparacao = comparar_filtro_simulacoes(
            conexao,
            "sinais-v4",
            amostra_minima=30,
            iniciado_em="2026-07-22T10:00:00",
        )["comparacao"]["gol_ft"]

        self.assertEqual(comparacao["estado"], "amostra_insuficiente")
        self.assertEqual(comparacao["decisao"], "aguardando_amostra")
        self.assertEqual(comparacao["decisoes_enviadas"], 2)
        self.assertEqual(comparacao["decisoes_filtradas"], 2)
        self.assertEqual(comparacao["resultados_resolvidos_enviadas"], 1)
        self.assertEqual(comparacao["resultados_resolvidos_filtradas"], 1)
        self.assertEqual(comparacao["pendentes_enviadas"], 1)
        self.assertEqual(comparacao["pendentes_filtradas"], 1)
        self.assertEqual(comparacao["amostra_enviadas"], 1)
        self.assertEqual(comparacao["amostra_filtradas"], 1)
        self.assertIsNone(comparacao["delta_taxa_acerto"])
        self.assertIsNone(comparacao["delta_roi"])
        self.assertIsNone(comparacao["intervalo_delta_roi_95"])
        self.assertIsNone(
            comparacao["intervalo_delta_taxa_acerto_95"]
        )
        conexao.close()

    def test_drift_exige_duas_janelas_independentes_suficientes(self):
        conexao = self._banco_drift([0.8] * 10)

        resultado = avaliar_drift_simulacoes(
            conexao, "sinais-v4",
            janela_recente=5, janela_base=5,
            minimo_recente=6, minimo_base=6,
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "formando_base")
        self.assertEqual(
            resultado["mercados"]["gol_ft"]["estado"], "formando_base"
        )
        conexao.close()

    def test_drift_detecta_queda_estatistica_de_roi(self):
        conexao = self._banco_drift([0.8] * 30 + [-1.0] * 20)

        resultado = avaliar_drift_simulacoes(
            conexao, "sinais-v4",
            janela_recente=20, janela_base=30,
            minimo_recente=20, minimo_base=30,
        )
        mercado = resultado["mercados"]["gol_ft"]

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "degradado")
        self.assertEqual(mercado["estado"], "degradado")
        self.assertEqual(mercado["roi_base"], 0.8)
        self.assertEqual(mercado["roi_recente"], -1.0)
        self.assertLess(mercado["intervalo_delta_roi_95"][1], 0)
        self.assertEqual(mercado["ultima_decisao_id"], 50)
        self.assertFalse(resultado["ajuste_automatico"])
        conexao.close()

    def test_drift_estavel_nao_cria_falso_alerta(self):
        retornos = [0.8, -1.0] * 25
        conexao = self._banco_drift(retornos)

        resultado = avaliar_drift_simulacoes(
            conexao, "sinais-v4",
            janela_recente=20, janela_base=30,
            minimo_recente=20, minimo_base=30,
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["mercados_degradados"], [])
        self.assertEqual(
            resultado["mercados"]["gol_ft"]["estado"], "estavel"
        )
        conexao.close()

    def test_drift_por_mercado_nao_mistura_versao_arquivada(self):
        conexao = self._banco_drift([0.8] * 10)
        for sinal_id, versao, retorno in (
            (101, "sinais-v6", 0.8),
            (102, "sinais-v7-ft-asiatico", -1.0),
        ):
            conexao.execute(
                "INSERT INTO sinais VALUES (?, ?, ?, ?, ?)",
                (
                    sinal_id,
                    sinal_id,
                    f"2026-07-22T12:{sinal_id - 100:02d}:00",
                    "escanteios_ft_asiatico",
                    versao,
                ),
            )
            conexao.execute(
                "INSERT INTO entregas_alertas VALUES (?, ?, ?, ?)",
                (sinal_id, sinal_id, "10:teste", "entregue"),
            )
            conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?, ?, ?, ?)",
                (
                    sinal_id,
                    "green" if retorno > 0 else "red",
                    retorno,
                    f"2026-07-22T12:{sinal_id - 100:02d}:00",
                ),
            )

        resultado = avaliar_drift_simulacoes_por_mercado(
            conexao,
            {
                "gol_ft": "sinais-v4",
                "escanteios_ft_asiatico": "sinais-v7-ft-asiatico",
            },
            janela_recente=5,
            janela_base=5,
        )

        asiatico = resultado["mercados"]["escanteios_ft_asiatico"]
        self.assertEqual(asiatico["amostra_recente"], 1)
        self.assertEqual(asiatico["roi_recente"], -1.0)
        self.assertEqual(
            asiatico["regra_versao"], "sinais-v7-ft-asiatico"
        )
        self.assertEqual(
            resultado["mercados"]["gol_ft"]["amostra_recente"], 5
        )
        conexao.close()

    def test_marco_do_filtro_e_persistente_e_separa_novos_limites(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.execute(
            "CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT)"
        )

        primeiro = registrar_ou_obter_experimento_filtro(
            conexao,
            "sinais-v4",
            80,
            80,
            datetime(2026, 7, 22, 18, 10, 8),
        )
        repetido = registrar_ou_obter_experimento_filtro(
            conexao,
            "sinais-v4",
            80,
            80,
            datetime(2026, 7, 23, 12, 0, 0),
        )
        novo_limiar = registrar_ou_obter_experimento_filtro(
            conexao,
            "sinais-v4",
            85,
            80,
            datetime(2026, 7, 23, 12, 0, 0),
        )

        self.assertEqual(
            primeiro["iniciado_em"], "2026-07-22T18:10:08"
        )
        self.assertEqual(repetido, primeiro)
        self.assertEqual(
            novo_limiar["iniciado_em"], "2026-07-23T12:00:00"
        )
        self.assertEqual(
            obter_experimento_filtro(
                conexao, "sinais-v4", 80, 80
            ),
            primeiro,
        )
        self.assertEqual(
            conexao.execute("SELECT COUNT(*) FROM metadados").fetchone()[0],
            2,
        )
        conexao.close()

    def test_auditoria_novo_limiar_nao_mistura_experimento_anterior(self):
        conexao = self._banco_auditoria_filtro()
        registrar_ou_obter_experimento_filtro(
            conexao,
            "sinais-v4",
            75,
            80,
            datetime(2026, 7, 23, 13, 0, 0),
        )
        conexao.execute(
            """
            INSERT INTO sinais (
                id, criado_em, regra_versao,
                pontuacao_tecnica, features_json
            ) VALUES (1, '2026-07-22T18:11:00', 'sinais-v4',
                      70, '{"qualidade_dados": 90}')
            """
        )
        conexao.execute(
            """
            INSERT INTO entregas_alertas (
                id, sinal_id, canal, status, erro
            ) VALUES (1, 1, 'gateway:teste', 'filtrado',
                      'pontuacao_teste_insuficiente')
            """,
        )
        conexao.commit()

        auditoria = auditar_experimento_filtro(
            conexao, "sinais-v4", 75, 80, ativo=True
        )

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["experimentos_anteriores"], 1)
        self.assertEqual(auditoria["decisoes_filtradas_anteriores"], 0)
        conexao.close()

    def test_auditoria_v2_reconhece_marco_de_versao_anterior(self):
        conexao = self._banco_auditoria_filtro()
        conexao.execute(
            """
            INSERT INTO metadados (chave, valor) VALUES (?, ?)
            """,
            (
                "experimento_filtro_teste:filtro-simulacoes-v1:"
                "sinais-v4:75:80",
                json.dumps({
                    "versao": "filtro-simulacoes-v1",
                    "regra_versao": "sinais-v4",
                    "pontuacao_minima": 75.0,
                    "qualidade_minima": 80.0,
                    "iniciado_em": "2026-07-22T17:00:00",
                }),
            ),
        )
        conexao.execute(
            """
            INSERT INTO sinais (
                id, criado_em, regra_versao,
                pontuacao_tecnica, features_json
            ) VALUES (1, '2026-07-22T17:10:00', 'sinais-v4',
                      70, '{"qualidade_dados": 90}')
            """
        )
        conexao.execute(
            """
            INSERT INTO entregas_alertas (
                id, sinal_id, canal, status, erro
            ) VALUES (1, 1, 'gateway:teste', 'filtrado',
                      'pontuacao_teste_insuficiente')
            """
        )
        conexao.commit()

        auditoria = auditar_experimento_filtro(
            conexao, "sinais-v4", 80, 80, ativo=True
        )

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["experimentos_anteriores"], 1)
        self.assertEqual(auditoria["decisoes_filtradas_anteriores"], 0)
        conexao.close()

    def test_auditoria_estrita_rejeita_linhagem_indisponivel(self):
        conexao = self._banco_auditoria_filtro()

        auditoria = auditar_experimento_filtro(
            conexao,
            "sinais-v4",
            80,
            80,
            exigir_linhagem=True,
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(
            auditoria["motivo"], "linhagem_regra_indisponivel"
        )
        conexao.close()

    def test_auditoria_detecta_decisao_de_outra_linhagem(self):
        conexao = self._banco_auditoria_filtro()
        conexao.execute(
            "ALTER TABLE sinais ADD COLUMN regra_fingerprint TEXT"
        )
        conexao.executescript(
            """
            INSERT INTO sinais (
                id, criado_em, regra_versao, pontuacao_tecnica,
                features_json, regra_fingerprint
            ) VALUES
                (1, '2026-07-22T18:11:00', 'sinais-v4', 90,
                 '{"qualidade_dados": 92}', 'fp-atual'),
                (2, '2026-07-22T18:12:00', 'sinais-v4', 75,
                 '{"qualidade_dados": 95}', NULL);
            INSERT INTO entregas_alertas VALUES
                (1, 1, '-100:teste', 'entregue', NULL),
                (2, 2, 'gateway:teste', 'filtrado',
                 'pontuacao_teste_insuficiente');
            """
        )

        auditoria = auditar_experimento_filtro(
            conexao,
            "sinais-v4",
            80,
            80,
            regra_fingerprint="fp-atual",
            exigir_linhagem=True,
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(
            auditoria["motivo"], "decisoes_fora_linhagem_atual"
        )
        self.assertEqual(auditoria["decisoes_enviadas_auditadas"], 1)
        self.assertEqual(auditoria["decisoes_filtradas_auditadas"], 0)
        self.assertEqual(auditoria["decisoes_fora_linhagem"], 1)
        conexao.close()

    def test_comparacao_por_fingerprint_exclui_regra_antiga(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY, partida_id INTEGER,
                criado_em TEXT, mercado TEXT, regra_versao TEXT,
                regra_fingerprint TEXT, pontuacao_tecnica REAL,
                status TEXT
            );
            CREATE TABLE entregas_alertas (
                id INTEGER PRIMARY KEY, sinal_id INTEGER,
                canal TEXT, status TEXT, erro TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER, resultado TEXT,
                retorno_unidades REAL, encerrado_em TEXT
            );
            INSERT INTO sinais VALUES
                (1, 1, '2026-07-22T18:11:00', 'gol_ft', 'sinais-v4',
                 'fp-atual', 90, 'simulacao'),
                (2, 2, '2026-07-22T18:12:00', 'gol_ft', 'sinais-v4',
                 'fp-atual', 75, 'simulacao'),
                (3, 3, '2026-07-22T18:13:00', 'gol_ft', 'sinais-v4',
                 NULL, 90, 'simulacao');
            INSERT INTO entregas_alertas VALUES
                (1, 1, '-100:teste', 'entregue', NULL),
                (2, 2, 'gateway:teste', 'filtrado',
                 'pontuacao_teste_insuficiente'),
                (3, 3, '-100:teste', 'entregue', NULL);
            INSERT INTO resultados_sinais VALUES
                (1, 'green', 0.80, '2026-07-22T19:00:00'),
                (2, 'red', -1.00, '2026-07-22T19:01:00'),
                (3, 'red', -1.00, '2026-07-22T19:02:00');
            """
        )

        comparacao = comparar_filtro_simulacoes(
            conexao,
            regra_versao="sinais-v4",
            amostra_minima=1,
            regra_fingerprint="fp-atual",
        )

        self.assertEqual(comparacao["enviadas"]["geral"]["amostra"], 1)
        self.assertEqual(comparacao["filtradas"]["geral"]["amostra"], 1)
        self.assertEqual(
            comparacao["enviadas"]["geral"]["lucro_unidades"], 0.8
        )
        conexao.close()

    def test_primeira_conclusao_avaliavel_e_congelada(self):
        conexao = self._banco_auditoria_filtro()
        comparacao_inicial = {
            "comparacao": {
                "geral": {
                    "estado": "avaliavel",
                    "decisao": "nao_comprovado",
                    "amostra_enviadas": 30,
                    "amostra_filtradas": 30,
                    "delta_roi": -0.05,
                    "intervalo_delta_roi_95": [-0.20, 0.10],
                }
            }
        }
        inicial = registrar_ou_obter_conclusao_experimento_filtro(
            conexao,
            "sinais-v4",
            80,
            80,
            "fp-atual",
            comparacao_inicial,
            datetime(2026, 7, 24, 10, 0, 0),
        )
        posterior = registrar_ou_obter_conclusao_experimento_filtro(
            conexao,
            "sinais-v4",
            80,
            80,
            "fp-atual",
            {
                "comparacao": {
                    "geral": {
                        "estado": "avaliavel",
                        "decisao": "evidencia_favoravel",
                        "amostra_enviadas": 100,
                        "amostra_filtradas": 100,
                    }
                }
            },
            datetime(2026, 7, 25, 10, 0, 0),
        )

        self.assertEqual(
            inicial["versao"], VERSAO_CONCLUSAO_EXPERIMENTO_FILTRO
        )
        self.assertEqual(inicial, posterior)
        self.assertEqual(posterior["decisao"], "nao_comprovado")
        self.assertEqual(
            posterior["evidencia"]["amostra_enviadas"], 30
        )
        carregada = obter_conclusao_experimento_filtro(
            conexao, "sinais-v4", 80, 80, "fp-atual"
        )
        self.assertEqual(carregada, inicial)
        with self.assertRaises(sqlite3.IntegrityError):
            conexao.execute(
                """
                UPDATE metadados SET valor='{}'
                WHERE chave LIKE 'conclusao_experimento_filtro:%'
                """
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conexao.execute(
                """
                DELETE FROM metadados
                WHERE chave LIKE 'conclusao_experimento_filtro:%'
                """
            )
        conexao.close()

    def test_conclusao_nao_e_criada_antes_da_amostra(self):
        conexao = self._banco_auditoria_filtro()

        conclusao = registrar_ou_obter_conclusao_experimento_filtro(
            conexao,
            "sinais-v4",
            80,
            80,
            "fp-atual",
            {
                "comparacao": {
                    "geral": {
                        "estado": "amostra_insuficiente",
                        "decisao": "aguardando_amostra",
                    }
                }
            },
        )

        self.assertIsNone(conclusao)
        total = conexao.execute(
            """
            SELECT COUNT(*) FROM metadados
            WHERE chave LIKE 'conclusao_experimento_filtro:%'
            """
        ).fetchone()[0]
        self.assertEqual(total, 0)
        conexao.close()


if __name__ == "__main__":
    unittest.main()
