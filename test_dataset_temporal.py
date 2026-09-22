import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from banco import BancoMonitor
from dataset_temporal import (
    achatar_features,
    avaliar_corte_sombra,
    avaliar_discriminacao_temporal,
    construir_dataset_temporal,
    dividir_cronologicamente,
    resumir_cobertura_dataset_temporal,
    resumir_cortes_sombra,
)
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS
from linhagem_regras import registrar_ou_validar_linhagem_regra


class DatasetTemporalTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_dataset_temporal.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)
        linhagem = registrar_ou_validar_linhagem_regra(
            self.banco.conexao,
            Path.cwd(),
            VERSAO_REGRAS,
            VERSAO_FEATURES,
        )
        self.regra_fingerprint = linhagem["fingerprint_registrado"]

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    @staticmethod
    def features(mercado="gol_ft", chutes=2):
        return {
            "schema_versao": VERSAO_FEATURES,
            "mercado": mercado,
            "linha": 0.5,
            "odd": 1.8,
            "minuto": 60,
            "janelas": {
                "5": {
                    "disponivel": True, "duracao_real_minutos": 5,
                    "chutes_total": chutes,
                    "chutes_por_minuto": chutes / 5,
                    "chutes": [chutes, 0],
                    "chutes_por_minuto_lados": [chutes / 5, 0],
                    "pressao_media": [60, 40],
                    "pressao_pico": [85, 55],
                },
                "10": {"disponivel": False},
                "15": {"disponivel": False},
            },
        }

    def salvar_resultado(
        self, indice, resultado="green", features=None, odd=1.8,
        criado_em=None,
    ):
        criado_em = criado_em or (
            datetime(2026, 7, 20, 12, 0) + timedelta(minutes=indice)
        ).isoformat()
        snapshot = self.banco.salvar_registro({
            "coletado_em": criado_em,
            "url": f"https://packball.com/match/{indice}/live",
            "mandante": f"A{indice}", "visitante": f"B{indice}",
            "placar": "0-0", "status": "60 '",
        })
        sinal_id = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft", "linha": 0.5, "odd": odd,
            "pontuacao_tecnica": 80, "regra_versao": VERSAO_REGRAS,
            "regra_fingerprint": self.regra_fingerprint,
            "status": "aprovado", "features": features,
        }], criado_em)[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    sinal_id, criado_em, resultado,
                    0.8 if resultado == "green" else -1.0,
                ),
            )
        return sinal_id, snapshot

    def test_achata_janelas_sem_inventar_ausentes(self):
        linha = achatar_features(self.features())
        self.assertEqual(linha["j5_chutes_por_minuto"], 0.4)
        self.assertEqual(linha["j5_chutes_por_minuto_lados_casa"], 0.4)
        self.assertEqual(linha["j5_pressao_media_casa"], 60.0)
        self.assertEqual(linha["j5_pressao_media_max"], 60.0)
        self.assertEqual(linha["j5_pressao_media_diferenca_abs"], 20.0)
        self.assertEqual(linha["j5_pressao_pico_max"], 85.0)
        self.assertIsNone(linha["j10_chutes_por_minuto"])

    def test_dataset_filtra_features_invalidas_e_preserva_independencia(self):
        primeiro, snapshot = self.salvar_resultado(
            1, features=self.features(chutes=2)
        )
        # Candidato posterior da mesma partida não pode substituir o primeiro.
        segundo = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.9,
            "pontuacao_tecnica": 99, "regra_versao": VERSAO_REGRAS,
            "regra_fingerprint": self.regra_fingerprint,
            "status": "aprovado", "features": self.features(chutes=20),
        }], "2026-07-20T12:02:00")[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades
                ) VALUES (?, '2026-07-20T13:00:00', 'green', 0.9)
                """, (segundo,),
            )
        self.salvar_resultado(2, resultado="red", features={})
        self.salvar_resultado(3, features=self.features(), odd=3.0)

        dataset = construir_dataset_temporal(
            self.banco.conexao, "gol_ft"
        )

        self.assertEqual(dataset["elegiveis_independentes"], 2)
        self.assertEqual(dataset["registros_validos"], 1)
        self.assertEqual(dataset["excluidos_features_invalidas"], 1)
        self.assertEqual(
            dataset["exclusoes_por_motivo"]["schema_incompativel"], 1
        )
        self.assertEqual(dataset["registros"][0]["sinal_id"], primeiro)
        self.assertEqual(
            dataset["registros"][0]["features"]["j5_chutes_total"], 2.0
        )

    def test_divisao_cronologica_nunca_mistura_futuro_no_desenvolvimento(self):
        registros = [
            {"sinal_id": indice, "criado_em": f"2026-07-{dia:02d}"}
            for indice, dia in ((3, 3), (1, 1), (2, 2), (4, 4))
        ]
        desenvolvimento, validacao = dividir_cronologicamente(registros)
        self.assertEqual([item["sinal_id"] for item in desenvolvimento], [1, 2])
        self.assertEqual([item["sinal_id"] for item in validacao], [3, 4])

    def test_resumo_separa_elegiveis_validos_e_excluidos(self):
        self.salvar_resultado(1, features=self.features())
        self.salvar_resultado(2, resultado="red", features={})

        resumo = resumir_cobertura_dataset_temporal(
            self.banco.conexao, ("gol_ft", "gol_ht")
        )

        self.assertEqual(resumo["elegiveis"], 2)
        self.assertEqual(resumo["historicos"], 2)
        self.assertEqual(resumo["legado_excluido"], 0)
        self.assertEqual(resumo["validos"], 1)
        self.assertEqual(resumo["excluidos"], 1)
        self.assertEqual(resumo["cobertura"], 0.5)
        self.assertEqual(
            resumo["exclusoes_por_motivo"]["schema_incompativel"], 1
        )
        self.assertEqual(resumo["por_mercado"]["gol_ht"]["elegiveis"], 0)

    def test_resumo_respeita_versao_especifica_de_cada_mercado(self):
        vazio = {
            "elegiveis_independentes": 0,
            "historicos_independentes": 0,
            "legado_excluido": 0,
            "registros_validos": 0,
            "excluidos_features_invalidas": 0,
            "exclusoes_por_motivo": {},
            "cobertura": None,
        }
        with patch(
            "dataset_temporal.construir_dataset_temporal",
            return_value=vazio,
        ) as construir:
            resumo = resumir_cobertura_dataset_temporal(
                self.banco.conexao,
                ("gol_ft", "escanteios_ft_asiatico"),
                regra_versao="sinais-v6",
                regras_por_mercado={
                    "escanteios_ft_asiatico": "sinais-v7-ft-asiatico"
                },
            )

        self.assertEqual(
            resumo["regras_por_mercado"],
            {
                "gol_ft": "sinais-v6",
                "escanteios_ft_asiatico": "sinais-v7-ft-asiatico",
            },
        )
        self.assertEqual(
            construir.call_args_list[0].kwargs["regra_versao"],
            "sinais-v6",
        )
        self.assertEqual(
            construir.call_args_list[1].kwargs["regra_versao"],
            "sinais-v7-ft-asiatico",
        )

    def test_dataset_classifica_divergencia_de_odd_separadamente(self):
        features = self.features()
        features["odd"] = 1.9
        self.salvar_resultado(1, features=features, odd=1.8)

        dataset = construir_dataset_temporal(
            self.banco.conexao, "gol_ft"
        )

        self.assertEqual(dataset["registros_validos"], 0)
        self.assertEqual(
            dataset["exclusoes_por_motivo"]["odd_linha_inconsistente"], 1
        )
        self.assertEqual(
            dataset["exclusoes_por_motivo"]["schema_incompativel"], 0
        )

    def test_dataset_sombra_exclui_linhagem_legada_como_calibrador(self):
        self.salvar_resultado(1, features=self.features())
        criado_em = "2026-07-20T13:00:00"
        snapshot = self.banco.salvar_registro({
            "coletado_em": criado_em,
            "url": "https://packball.com/match/legado/live",
            "mandante": "Legado A",
            "visitante": "Legado B",
            "placar": "0-0",
            "status": "60 '",
        })
        with self.banco.conexao:
            partida_id = self.banco.conexao.execute(
                "SELECT partida_id FROM snapshots WHERE id=?",
                (snapshot,),
            ).fetchone()[0]
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO sinais (
                    partida_id, snapshot_id, criado_em, mercado,
                    linha, odd, pontuacao_tecnica, regra_versao,
                    regra_fingerprint, features_json, status
                ) VALUES (?, ?, ?, 'gol_ft', '0.5', 1.8, 99, ?, NULL, ?,
                          'aprovado')
                """,
                (
                    partida_id,
                    snapshot,
                    criado_em,
                    VERSAO_REGRAS,
                    json.dumps(self.features(chutes=20)),
                ),
            )
            sinal_id = cursor.lastrowid
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades
                ) VALUES (?, ?, 'green', 0.8)
                """,
                (sinal_id, criado_em),
            )

        dataset = construir_dataset_temporal(
            self.banco.conexao, "gol_ft"
        )

        self.assertEqual(dataset["elegiveis_independentes"], 1)
        self.assertEqual(dataset["historicos_independentes"], 2)
        self.assertEqual(dataset["legado_excluido"], 1)
        self.assertEqual(
            dataset["regra_fingerprint"], self.regra_fingerprint
        )

    def test_avaliacao_sombra_define_direcao_so_no_desenvolvimento(self):
        registros = []
        for indice in range(100):
            green = indice % 2 == 0
            valor = 10.0 if green else 1.0
            registros.append({
                "sinal_id": indice + 1,
                "criado_em": f"2026-07-{indice // 24 + 1:02d}T"
                              f"{indice % 24:02d}:00:00",
                "resultado": "green" if green else "red",
                "alvo_green": int(green),
                "pontuacao_tecnica": valor,
                "features": {
                    "j5_chutes_por_minuto": valor,
                },
            })

        avaliacao = avaliar_discriminacao_temporal(registros)
        feature = avaliacao["avaliacoes"]["j5_chutes_por_minuto"]

        self.assertEqual(avaliacao["estado"], "avaliavel")
        self.assertEqual(
            feature["direcao_definida_no_desenvolvimento"],
            "maior_melhor",
        )
        self.assertEqual(
            feature["discriminacao_validacao"]["auc"], 1.0
        )
        self.assertEqual(
            avaliacao["avaliacoes"]["j10_chutes_por_minuto"]["motivo"],
            "cobertura_insuficiente",
        )

    def test_avaliacao_sombra_nao_abre_resultado_com_amostra_pequena(self):
        avaliacao = avaliar_discriminacao_temporal([
            {
                "sinal_id": 1, "criado_em": "2026-07-20T12:00:00",
                "resultado": "green", "alvo_green": 1,
                "pontuacao_tecnica": 90, "features": {},
            }
        ])
        self.assertEqual(avaliacao["estado"], "inconclusiva")
        self.assertEqual(avaliacao["motivo"], "amostra_insuficiente")
        self.assertEqual(avaliacao["avaliacoes"], {})

    def test_corte_sombra_e_escolhido_sem_consultar_resultado_futuro(self):
        def registros(validacao_invertida=False):
            itens = []
            for indice in range(100):
                green = indice % 2 == 0
                if indice >= 70 and validacao_invertida:
                    green = not green
                valor = 10.0 if indice % 2 == 0 else 1.0
                itens.append({
                    "sinal_id": indice + 1,
                    "criado_em": f"2026-07-{indice // 24 + 1:02d}T"
                                  f"{indice % 24:02d}:00:00",
                    "resultado": "green" if green else "red",
                    "alvo_green": int(green),
                    "retorno_unidades": 0.8 if green else -1.0,
                    "pontuacao_tecnica": valor,
                    "odd": 1.8,
                    "linha": 1.5,
                    "features": {},
                })
            return itens

        coerente = avaliar_corte_sombra(
            registros(), minimo_desenvolvimento=20,
            minimo_validacao=10,
        )
        invertida = avaliar_corte_sombra(
            registros(validacao_invertida=True),
            minimo_desenvolvimento=20,
            minimo_validacao=10,
        )

        corte_coerente = coerente["corte_escolhido_no_desenvolvimento"]
        corte_invertido = invertida["corte_escolhido_no_desenvolvimento"]
        self.assertEqual(
            (
                corte_coerente["feature"],
                corte_coerente["operador"],
                corte_coerente["limiar"],
            ),
            (
                corte_invertido["feature"],
                corte_invertido["operador"],
                corte_invertido["limiar"],
            ),
        )
        self.assertTrue(coerente["apto_para_alterar_regra"], coerente)
        self.assertFalse(invertida["apto_para_alterar_regra"])
        self.assertGreater(coerente["candidatos_explorados"], 1)
        self.assertGreater(coerente["features_com_candidatos"], 0)
        self.assertTrue(
            coerente["busca_exploratoria_multiplos_cortes"]
        )
        self.assertFalse(coerente["uso_confirmatorio"])
        self.assertFalse(
            coerente["correcao_multiplas_comparacoes_confirmatoria"]
        )
        self.assertTrue(coerente["requer_validacao_prospectiva"])

    def test_resumo_cortes_sombra_nunca_aplica_regra_automaticamente(self):
        for indice in range(45):
            self.salvar_resultado(
                indice,
                resultado="green" if indice % 2 == 0 else "red",
                features=self.features(chutes=indice % 5 + 1),
            )

        resumo = resumir_cortes_sombra(
            self.banco.conexao, ["gol_ft"]
        )

        self.assertEqual(resumo["versao"], "cortes-sombra-v1")
        self.assertFalse(resumo["aplicacao_automatica"])
        self.assertIn("gol_ft", resumo["avaliacoes"])


if __name__ == "__main__":
    unittest.main()
