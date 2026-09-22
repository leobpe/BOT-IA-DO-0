import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from banco import BancoMonitor
from estatistica import discriminacao_pontuacao
from pontuacao_sombra import (
    AMOSTRA_MINIMA_VALIDACAO,
    AMOSTRA_MINIMA_TREINO,
    ajustar_modelo_pontuacao_sombra,
    avaliar_modelo_pontuacao_sombra,
    carregar_modelo_pontuacao_sombra,
    fingerprint_configuracao_pontuacao_sombra,
    prever_pontuacao_sombra,
    registrar_ou_obter_modelo_pontuacao_sombra,
)


def _registro(indice, green=None):
    green = (indice % 4 in (2, 3)) if green is None else bool(green)
    impulso = 1.0 if green else 0.0
    return {
        "sinal_id": indice,
        "partida_id": indice,
        "snapshot_id": indice,
        "criado_em": f"2026-07-01T00:{indice % 60:02d}:00",
        "encerrado_em": f"2026-07-01T01:{indice % 60:02d}:00",
        "mercado": "gol_ft",
        "linha": 1.5,
        "odd": 1.8 - impulso * 0.1,
        "pontuacao_tecnica": 90.0 - impulso * 15.0,
        "resultado": "green" if green else "red",
        "alvo_green": int(green),
        "retorno_unidades": 0.7 if green else -1.0,
        "features": {
            "minuto": 45.0,
            "gols_atuais": 1.0,
            "chutes_no_gol_total": 4.0 + impulso * 3.0,
            "qualidade_dados": 95.0,
            "j5_chutes_total": 2.0 + impulso * 3.0,
            "j5_escanteios_total": impulso * 2.0,
            "j5_pressao_pico_max": 55.0 + impulso * 20.0,
        },
    }


def _dataset(registros):
    return {
        "registros": registros,
        "fingerprint": "dataset-fingerprint",
    }


class PontuacaoSombraTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_pontuacao_sombra.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def test_politica_avaliacao_nao_altera_fingerprint_modelo_congelado(self):
        self.assertEqual(
            fingerprint_configuracao_pontuacao_sombra(),
            "d7e8ff622b6dfac52bd43d753ebea3a022970ef4c0e0cffd896f79fd"
            "639aebec",
        )

    def test_modelo_aprende_relacao_sem_alterar_nota_atual(self):
        registros = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 21)
        ]
        modelo = ajustar_modelo_pontuacao_sombra(registros)
        avaliados = [{
            "resultado": item["resultado"],
            "pontuacao_tecnica": prever_pontuacao_sombra(modelo, item),
        } for item in registros]
        auc = discriminacao_pontuacao(avaliados)

        self.assertGreater(auc["auc"], 0.95)
        self.assertEqual(registros[0]["pontuacao_tecnica"], 90.0)
        incompleto = dict(registros[0])
        incompleto["features"] = {}
        probabilidade = prever_pontuacao_sombra(modelo, incompleto)
        self.assertGreaterEqual(probabilidade, 0.0)
        self.assertLessEqual(probabilidade, 1.0)

    def test_modelo_e_congelado_e_idempotente_no_sqlite(self):
        treino = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                primeiro = registrar_ou_obter_modelo_pontuacao_sombra(
                    self.banco.conexao,
                    "gol_ft",
                    "sinais-v6",
                    registrado_em="2026-07-29T20:00:00",
                )
                repetido = registrar_ou_obter_modelo_pontuacao_sombra(
                    self.banco.conexao,
                    "gol_ft",
                    "sinais-v6",
                    registrado_em="2026-07-29T21:00:00",
                )

        self.assertTrue(primeiro["criado"])
        self.assertFalse(repetido["criado"])
        self.assertTrue(repetido["integro"])
        self.assertEqual(repetido["treino_ate_sinal_id"], 60)
        chave = self.banco.conexao.execute(
            """
            SELECT chave FROM metadados
            WHERE chave LIKE 'pontuacao_sombra:%'
            """
        ).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.conexao.execute(
                "UPDATE metadados SET valor='{}' WHERE chave=?",
                (chave,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.conexao.execute(
                "DELETE FROM metadados WHERE chave=?",
                (chave,),
            )

    def test_validacao_considera_somente_sinais_posteriores_ao_congelamento(
        self,
    ):
        treino = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                registrar_ou_obter_modelo_pontuacao_sombra(
                    self.banco.conexao,
                    "gol_ft",
                    "sinais-v6",
                    registrado_em="2026-07-29T20:00:00",
                )

        futuros = [
            _registro(indice)
            for indice in range(
                AMOSTRA_MINIMA_TREINO + 1,
                AMOSTRA_MINIMA_TREINO + 11,
            )
        ]
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino + futuros),
        ):
            avaliacao = avaliar_modelo_pontuacao_sombra(
                self.banco.conexao,
                "gol_ft",
                "sinais-v6",
            )

        self.assertEqual(avaliacao["treino"], AMOSTRA_MINIMA_TREINO)
        self.assertEqual(avaliacao["validacao"], 10)
        self.assertEqual(avaliacao["estado"], "aguardando_validacao")
        self.assertEqual(avaliacao["faltam_validacao"], 20)
        self.assertFalse(avaliacao["aplicacao_automatica"])

    def test_validacao_fica_congelada_nos_primeiros_trinta_resultados(self):
        treino = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                registrar_ou_obter_modelo_pontuacao_sombra(
                    self.banco.conexao, "gol_ft", "sinais-v6"
                )
        primeiros = [
            _registro(indice)
            for indice in range(
                AMOSTRA_MINIMA_TREINO + 1,
                AMOSTRA_MINIMA_TREINO
                + AMOSTRA_MINIMA_VALIDACAO + 1,
            )
        ]
        extras = [
            _registro(indice, green=True)
            for indice in range(
                AMOSTRA_MINIMA_TREINO
                + AMOSTRA_MINIMA_VALIDACAO + 1,
                AMOSTRA_MINIMA_TREINO
                + AMOSTRA_MINIMA_VALIDACAO + 11,
            )
        ]
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino + primeiros),
        ):
            primeira = avaliar_modelo_pontuacao_sombra(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino + primeiros + extras),
        ):
            posterior = avaliar_modelo_pontuacao_sombra(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertEqual(primeira["validacao"], 30)
        self.assertEqual(posterior["validacao"], 30)
        self.assertEqual(posterior["validacao_total_disponivel"], 40)
        self.assertTrue(posterior["validacao_congelada"])
        self.assertEqual(
            primeira["validacao_fingerprint"],
            posterior["validacao_fingerprint"],
        )
        self.assertEqual(primeira["auc_sombra"], posterior["auc_sombra"])
        self.assertEqual(
            primeira["brier_sombra"], posterior["brier_sombra"]
        )
        self.assertEqual(primeira["brier_odd"], posterior["brier_odd"])
        self.assertEqual(primeira["estado"], posterior["estado"])

    def test_auc_favoravel_nao_aprova_probabilidade_pior_que_odd(self):
        treino = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        futuros = [
            _registro(indice)
            for indice in range(
                AMOSTRA_MINIMA_TREINO + 1,
                AMOSTRA_MINIMA_TREINO
                + AMOSTRA_MINIMA_VALIDACAO + 1,
            )
        ]
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                registrar_ou_obter_modelo_pontuacao_sombra(
                    self.banco.conexao, "gol_ft", "sinais-v6"
                )

        auc_favoravel = {
            "auc": 0.80,
            "limite_inferior_auc_95": 0.60,
            "intervalo_auc_95": [0.60, 0.92],
        }
        auc_atual = {
            "auc": 0.60,
            "limite_inferior_auc_95": 0.40,
            "intervalo_auc_95": [0.40, 0.80],
        }
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino + futuros),
        ), patch(
            "pontuacao_sombra.discriminacao_pontuacao",
            side_effect=[auc_favoravel, auc_atual],
        ), patch(
            "pontuacao_sombra._brier", side_effect=[0.35, 0.20]
        ):
            avaliacao = avaliar_modelo_pontuacao_sombra(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertEqual(avaliacao["estado"], "inconclusiva")
        self.assertFalse(avaliacao["pronto_para_revisao"])
        self.assertEqual(avaliacao["brier_sombra"], 0.35)
        self.assertEqual(avaliacao["brier_odd"], 0.20)
        self.assertEqual(
            avaliacao["avaliacao_versao"],
            "avaliacao-pontuacao-sombra-janela-fixa-v2",
        )

    def test_auc_e_brier_favoraveis_permitiriam_revisao_humana(self):
        treino = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        futuros = [
            _registro(indice)
            for indice in range(
                AMOSTRA_MINIMA_TREINO + 1,
                AMOSTRA_MINIMA_TREINO
                + AMOSTRA_MINIMA_VALIDACAO + 1,
            )
        ]
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                registrar_ou_obter_modelo_pontuacao_sombra(
                    self.banco.conexao, "gol_ft", "sinais-v6"
                )
        auc_favoravel = {
            "auc": 0.80,
            "limite_inferior_auc_95": 0.60,
            "intervalo_auc_95": [0.60, 0.92],
        }
        auc_atual = {
            "auc": 0.60,
            "limite_inferior_auc_95": 0.40,
            "intervalo_auc_95": [0.40, 0.80],
        }
        with patch(
            "pontuacao_sombra.construir_dataset_temporal",
            return_value=_dataset(treino + futuros),
        ), patch(
            "pontuacao_sombra.discriminacao_pontuacao",
            side_effect=[auc_favoravel, auc_atual],
        ), patch(
            "pontuacao_sombra._brier", side_effect=[0.18, 0.20]
        ):
            avaliacao = avaliar_modelo_pontuacao_sombra(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertEqual(
            avaliacao["estado"], "favoravel_para_revisao"
        )
        self.assertTrue(avaliacao["pronto_para_revisao"])

    def test_carregamento_detecta_payload_incompativel(self):
        self.banco.conexao.execute(
            """
            INSERT INTO metadados (chave, valor) VALUES (?, ?)
            """,
            (
                "pontuacao_sombra:pontuacao-sombra-logistica-v1:"
                "sinais-v6:gol_ft",
                '{"mercado":"gol_ft","regra_versao":"sinais-v6",'
                '"modelo":{},"modelo_hash":"invalido"}',
            ),
        )
        carregado = carregar_modelo_pontuacao_sombra(
            self.banco.conexao, "gol_ft", "sinais-v6"
        )
        self.assertFalse(carregado["integro"])
        self.assertEqual(
            carregado["motivo"],
            "modelo_incompativel_ou_corrompido",
        )


if __name__ == "__main__":
    unittest.main()
