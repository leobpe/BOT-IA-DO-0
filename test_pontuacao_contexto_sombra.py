import json
import os
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from treino_processo_isolado import TIMEOUT_TREINO_ISOLADO_SEGUNDOS

from banco import BancoMonitor
from estatistica import discriminacao_pontuacao
from pontuacao_contexto_sombra import (
    AMOSTRA_MINIMA_VALIDACAO,
    AMOSTRA_MINIMA_TREINO,
    ajustar_modelo,
    avaliar_modelo,
    carregar_modelo,
    construir_dataset_contexto,
    prever,
    registrar_ou_obter_modelo,
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
        "odd": 1.9 - impulso * 0.2,
        "pontuacao_tecnica": 88.0 - impulso * 12.0,
        "resultado": "green" if green else "red",
        "alvo_green": int(green),
        "retorno_unidades": 0.7 if green else -1.0,
        "features": {
            "minuto": 45.0,
            "gols_atuais": 1.0,
            "chutes_no_gol_total": 3.0 + impulso * 4.0,
            "qualidade_dados": 95.0,
            "j5_chutes_total": 1.0 + impulso * 4.0,
            "j5_escanteios_total": impulso * 2.0,
            "j5_pressao_pico_max": 50.0 + impulso * 25.0,
            "api_forma_ppg_total": 2.0 + impulso,
            "api_forma_ppg_diferenca_abs": 0.4,
            "api_h2h_media_gols": 2.0 + impulso,
            "api_temporada_gols_media_total": 1.8 + impulso,
            "api_historico_gols_media_total": 2.0 + impulso,
            "api_historico_xg_media_total": 1.5 + impulso,
            "api_live_xg_total": 0.5 + impulso,
            "api_live_chutes_no_gol_total": 2.0 + impulso * 3.0,
            "api_odds_pre_gols_linha": 2.5,
            "api_odds_pre_gols_prob_over": 0.45 + impulso * 0.1,
            "api_escalacoes_confirmadas": 2.0,
            "api_desfalques_total": 1.0,
        },
    }


def _dataset(registros):
    return {
        "registros": registros,
        "fingerprint": "dataset-contexto-fingerprint",
        "total_base": len(registros),
        "excluidos": {
            "sem_contexto_v4": 0,
            "contexto_insuficiente": 0,
        },
        "cobertura_features": {},
    }


class PontuacaoContextoSombraTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_pontuacao_contexto_sombra.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    def test_dataset_exige_contexto_v4_do_snapshot_do_sinal(self):
        contexto = {
            "versao": "contexto-pre-jogo-v4",
            "modo": "sombra",
            "fixture_id": 123,
            "forma_recente": {
                "mandante": {"pontos_por_jogo": 2.0},
                "visitante": {"pontos_por_jogo": 1.0},
            },
            "confrontos_diretos": {"media_gols": 2.5},
            "estatisticas_temporada": {
                "mandante": {"gols_pro_media": 1.4},
                "visitante": {"gols_pro_media": 1.2},
            },
            "historico_detalhado": {
                "mandante": {
                    "gols_pro_media": 1.5,
                    "xg_media": 1.3,
                },
                "visitante": {
                    "gols_pro_media": 1.2,
                    "xg_media": 1.0,
                },
            },
            "estatisticas_ao_vivo": {
                "times": {
                    "mandante": {"xg": 0.8, "chutes_no_gol": 3},
                    "visitante": {"xg": 0.4, "chutes_no_gol": 2},
                }
            },
            "odds_pre_jogo": {
                "mercados": {
                    "gols_ft": {
                        "consenso_suficiente": True,
                        "linha_consenso": 2.5,
                        "probabilidade_over_sem_margem": 0.52,
                    }
                }
            },
            "escalacoes": {
                "1": {"confirmada": True},
                "2": {"confirmada": True},
            },
            "desfalques": {
                "1": {"total": 1},
                "2": {"total": 0},
            },
        }
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-29T20:00:00",
            "url": "https://packball.com/match/contexto-v4/live",
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "45 '",
            "contexto_api": contexto,
        })
        registro = _registro(1)
        registro["snapshot_id"] = snapshot
        with patch(
            "pontuacao_contexto_sombra.construir_dataset_temporal",
            return_value={
                "registros": [registro],
                "fingerprint": "base",
            },
        ):
            dataset = construir_dataset_contexto(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertEqual(len(dataset["registros"]), 1)
        features = dataset["registros"][0]["features"]
        self.assertAlmostEqual(features["api_live_xg_total"], 1.2)
        self.assertEqual(features["api_odds_pre_gols_linha"], 2.5)
        self.assertEqual(features["api_escalacoes_confirmadas"], 2)

    def test_modelo_contextual_aprende_sem_alterar_nota_atual(self):
        registros = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 21)
        ]
        modelo = ajustar_modelo(registros, "gol_ft")
        avaliados = [{
            "resultado": item["resultado"],
            "pontuacao_tecnica": prever(modelo, item, "gol_ft"),
        } for item in registros]
        auc = discriminacao_pontuacao(avaliados)

        self.assertGreater(auc["auc"], 0.95)
        self.assertEqual(registros[0]["pontuacao_tecnica"], 88.0)

    def test_treino_isolado_repete_apos_timeout_e_valida_saida(self):
        registros = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        modelo = ajustar_modelo(registros, "gol_ft")
        concluido = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"ok": True, "modelo": modelo}),
            stderr="",
        )
        with patch(
            "treino_processo_isolado.subprocess.run",
            side_effect=[
                subprocess.TimeoutExpired(
                    "worker", TIMEOUT_TREINO_ISOLADO_SEGUNDOS
                ),
                concluido,
            ],
        ) as executar:
            ajustado = ajustar_modelo(registros, "gol_ft")

        self.assertEqual(executar.call_count, 2)
        payload_enviado = json.loads(
            executar.call_args_list[0].kwargs["input"]
        )
        self.assertEqual(payload_enviado["pid_pai"], os.getpid())
        self.assertEqual(ajustado["pesos"], modelo["pesos"])
        isolamento = ajustado["execucao_treino_isolado"]
        self.assertEqual(isolamento["tentativas"], 2)
        self.assertTrue(isolamento["recuperou_falha_transitoria"])
        self.assertEqual(isolamento["falhas_transitorias"], ["timeout"])

    def test_contexto_parcial_nao_fabrica_zero_nem_total(self):
        contexto = {
            "versao": "contexto-pre-jogo-v4",
            "modo": "sombra",
            "fixture_id": 456,
            "forma_recente": {
                "mandante": {"pontos_por_jogo": 2.0},
            },
            "confrontos_diretos": {"media_gols": 2.5},
            "estatisticas_ao_vivo": {
                "times": {
                    "mandante": {"xg": 0.8, "chutes_no_gol": 3},
                }
            },
            "escalacoes": {},
            "desfalques": {},
        }
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-29T20:00:00",
            "url": "https://packball.com/match/contexto-parcial/live",
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "45 '",
            "contexto_api": contexto,
        })
        registro = _registro(1)
        registro["snapshot_id"] = snapshot
        with patch(
            "pontuacao_contexto_sombra.construir_dataset_temporal",
            return_value={
                "registros": [registro],
                "fingerprint": "base",
            },
        ):
            dataset = construir_dataset_contexto(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertEqual(dataset["registros"], [])
        self.assertEqual(
            dataset["excluidos"]["contexto_insuficiente"], 1
        )

    def test_modelo_e_congelado_e_protegido_no_sqlite(self):
        treino = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        with patch(
            "pontuacao_contexto_sombra.construir_dataset_contexto",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                primeiro = registrar_ou_obter_modelo(
                    self.banco.conexao,
                    "gol_ft",
                    "sinais-v6",
                    registrado_em="2026-07-29T20:00:00",
                )
                repetido = registrar_ou_obter_modelo(
                    self.banco.conexao,
                    "gol_ft",
                    "sinais-v6",
                )

        self.assertTrue(primeiro["criado"])
        self.assertFalse(repetido["criado"])
        self.assertTrue(repetido["integro"])
        chave = self.banco.conexao.execute(
            """
            SELECT chave FROM metadados
            WHERE chave LIKE 'pontuacao_sombra:%:sinais-v6:gol_ft'
            """
        ).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.conexao.execute(
                "UPDATE metadados SET valor='{}' WHERE chave=?",
                (chave,),
            )
        carregado = carregar_modelo(
            self.banco.conexao, "gol_ft", "sinais-v6"
        )
        self.assertTrue(carregado["integro"])

    def test_validacao_e_exclusivamente_posterior_ao_congelamento(self):
        treino = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        with patch(
            "pontuacao_contexto_sombra.construir_dataset_contexto",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                registrar_ou_obter_modelo(
                    self.banco.conexao,
                    "gol_ft",
                    "sinais-v6",
                )
        futuros = [
            _registro(indice)
            for indice in range(
                AMOSTRA_MINIMA_TREINO + 1,
                AMOSTRA_MINIMA_TREINO + 11,
            )
        ]
        with patch(
            "pontuacao_contexto_sombra.construir_dataset_contexto",
            return_value=_dataset(treino + futuros),
        ):
            avaliacao = avaliar_modelo(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertEqual(avaliacao["treino"], AMOSTRA_MINIMA_TREINO)
        self.assertEqual(avaliacao["validacao"], 10)
        self.assertEqual(avaliacao["estado"], "aguardando_validacao")
        self.assertFalse(avaliacao["aplicacao_automatica"])

    def test_validacao_contextual_congela_primeiros_trinta_resultados(self):
        treino = [
            _registro(indice)
            for indice in range(1, AMOSTRA_MINIMA_TREINO + 1)
        ]
        with patch(
            "pontuacao_contexto_sombra.construir_dataset_contexto",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                registrar_ou_obter_modelo(
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
            "pontuacao_contexto_sombra.construir_dataset_contexto",
            return_value=_dataset(treino + primeiros),
        ):
            primeira = avaliar_modelo(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )
        with patch(
            "pontuacao_contexto_sombra.construir_dataset_contexto",
            return_value=_dataset(treino + primeiros + extras),
        ):
            posterior = avaliar_modelo(
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
        self.assertEqual(
            primeira["auc_contexto"], posterior["auc_contexto"]
        )
        self.assertEqual(
            primeira["brier_contexto"], posterior["brier_contexto"]
        )
        self.assertEqual(primeira["brier_odd"], posterior["brier_odd"])
        self.assertEqual(primeira["estado"], posterior["estado"])


if __name__ == "__main__":
    unittest.main()
