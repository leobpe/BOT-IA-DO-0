import json
import sqlite3
import unittest
from unittest.mock import patch

from hipoteses_sombra import (
    avaliar_hipotese_registros,
    avaliar_hipoteses_sombra,
    avaliar_hipoteses_sombra_ativas,
    _saldo_alvo_proximo_gol,
)


class HipotesesSombraTest(unittest.TestCase):
    def hipotese(self, minimo=3):
        return {
            "identificador": "proximo_gol_minuto_56",
            "regra_versao": "sinais-v6",
            "mercado": "proximo_gol",
            "feature": "minuto",
            "operador": "maior_igual",
            "limiar": 56.0,
            "iniciado_em": "2026-07-26T01:00:00",
            "minimo_resultados": minimo,
        }

    def registro(self, sinal, partida, minuto, resultado, retorno):
        return {
            "sinal_id": sinal,
            "partida_id": partida,
            "criado_em": f"2026-07-26T01:{sinal:02d}:00",
            "resultado": resultado,
            "retorno_unidades": retorno,
            "features": {"minuto": minuto},
        }

    def test_aguarda_amostra_e_nunca_aplica_automaticamente(self):
        resultado = avaliar_hipotese_registros(
            self.hipotese(minimo=3),
            [
                self.registro(1, 1, 60, "green", 0.8),
                self.registro(2, 2, 70, "red", -1.0),
            ],
        )

        self.assertEqual(resultado["estado"], "aguardando_amostra")
        self.assertEqual(resultado["faltam"], 1)
        self.assertIsNone(resultado["confirmada"])
        self.assertFalse(resultado["aplicacao_automatica"])

    def test_confirma_somente_com_roi_positivo_e_ic_melhor_que_controle(self):
        resultado = avaliar_hipotese_registros(
            self.hipotese(minimo=3),
            [
                self.registro(1, 1, 20, "red", -1.0),
                self.registro(2, 2, 30, "red", -1.0),
                self.registro(3, 3, 40, "red", -1.0),
                self.registro(4, 4, 60, "green", 0.8),
                self.registro(5, 5, 70, "green", 0.8),
                self.registro(6, 6, 80, "green", 0.8),
            ],
        )

        self.assertEqual(resultado["estado"], "confirmada")
        self.assertTrue(resultado["confirmada"])
        self.assertEqual(resultado["selecionada"]["amostra"], 3)
        self.assertEqual(resultado["controle_excluido"]["amostra"], 3)
        self.assertGreater(resultado["intervalo_delta_roi_95"][0], 0)

    def test_amostra_selecionada_sem_controle_suficiente_nao_confirma(self):
        resultado = avaliar_hipotese_registros(
            self.hipotese(minimo=3),
            [
                self.registro(1, 1, 20, "red", -1.0),
                self.registro(2, 2, 60, "green", 0.8),
                self.registro(3, 3, 70, "green", 0.8),
                self.registro(4, 4, 80, "green", 0.8),
            ],
        )

        self.assertEqual(resultado["estado"], "aguardando_controle")
        self.assertIsNone(resultado["confirmada"])
        self.assertEqual(resultado["faltam_controle"], 2)

    def test_primeiro_resultado_por_partida_e_independente(self):
        resultado = avaliar_hipotese_registros(
            self.hipotese(minimo=2),
            [
                self.registro(1, 10, 60, "red", -1.0),
                self.registro(2, 10, 70, "green", 0.8),
                self.registro(3, 11, 80, "red", -1.0),
                self.registro(4, 12, 20, "green", 0.8),
                self.registro(5, 13, 30, "red", -1.0),
                self.registro(6, 14, 40, "green", 0.8),
            ],
        )

        self.assertEqual(resultado["selecionada"]["amostra"], 2)
        self.assertEqual(resultado["estado"], "refutada")

    def test_contabiliza_pendentes_sem_poluir_metricas_resolvidas(self):
        pendente_selecionado = self.registro(1, 10, 60, None, None)
        pendente_controle = self.registro(2, 11, 40, None, None)
        resolvido = self.registro(3, 12, 70, "green", 0.8)

        resultado = avaliar_hipotese_registros(
            self.hipotese(minimo=3),
            [pendente_selecionado, pendente_controle, resolvido],
        )

        self.assertEqual(resultado["selecionada"]["amostra"], 1)
        self.assertEqual(resultado["pendentes_resultado"], 2)
        self.assertEqual(resultado["pendentes_selecionados"], 1)
        self.assertEqual(resultado["pendentes_controle"], 1)

    def test_resultado_substitui_pendente_da_mesma_partida(self):
        pendente = self.registro(1, 10, 60, None, None)
        resolvido = self.registro(2, 10, 70, "green", 0.8)

        resultado = avaliar_hipotese_registros(
            self.hipotese(minimo=3), [pendente, resolvido]
        )

        self.assertEqual(resultado["selecionada"]["amostra"], 1)
        self.assertEqual(resultado["pendentes_resultado"], 0)

    def test_hipotese_composta_exige_todos_os_criterios(self):
        hipotese = {
            **self.hipotese(minimo=2),
            "feature": None,
            "operador": None,
            "limiar": None,
            "criterios": [
                {
                    "feature": "gols_atuais",
                    "operador": "menor_igual",
                    "limiar": 3,
                },
                {
                    "feature": "janelas.5.chutes_total",
                    "operador": "menor_igual",
                    "limiar": 3,
                },
            ],
        }
        registros = [
            {
                **self.registro(1, 1, 60, "green", 0.8),
                "features": {
                    "gols_atuais": 2,
                    "janelas": {"5": {"chutes_total": 3}},
                },
            },
            {
                **self.registro(2, 2, 60, "red", -1.0),
                "features": {
                    "gols_atuais": 4,
                    "janelas": {"5": {"chutes_total": 2}},
                },
            },
            {
                **self.registro(3, 3, 60, "green", 0.8),
                "features": {
                    "gols_atuais": 1,
                    "janelas": {"5": {"chutes_total": 2}},
                },
            },
            {
                **self.registro(4, 4, 60, "red", -1.0),
                "features": {
                    "gols_atuais": 1,
                    "janelas": {"5": {"chutes_total": 5}},
                },
            },
            {
                **self.registro(5, 5, 60, "red", -1.0),
                "features": {
                    "gols_atuais": 5,
                    "janelas": {"5": {"chutes_total": 5}},
                },
            },
        ]

        resultado = avaliar_hipotese_registros(hipotese, registros)

        self.assertEqual(resultado["selecionada"]["amostra"], 2)
        self.assertEqual(resultado["controle_excluido"]["amostra"], 3)
        self.assertEqual(
            resultado["descricao_corte"],
            "gols_atuais menor_igual 3 E "
            "janelas.5.chutes_total menor_igual 3",
        )
        self.assertEqual(resultado["estado"], "confirmada")

    def test_saldo_alvo_e_calculado_do_ponto_de_vista_da_selecao(self):
        self.assertEqual(_saldo_alvo_proximo_gol("casa", "3-1"), 2.0)
        self.assertEqual(
            _saldo_alvo_proximo_gol("visitante", "3-4"), 1.0
        )
        self.assertIsNone(_saldo_alvo_proximo_gol("empate", "1-1"))
        self.assertIsNone(_saldo_alvo_proximo_gol("casa", "-"))

    def test_challenger_estado_usa_somente_dados_apos_o_registro(self):
        conexao = sqlite3.connect(":memory:")
        conexao.row_factory = sqlite3.Row
        conexao.executescript(
            """
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY,
                placar TEXT
            );
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                partida_id INTEGER,
                snapshot_id INTEGER,
                criado_em TEXT,
                mercado TEXT,
                linha TEXT,
                odd REAL,
                pontuacao_tecnica REAL,
                regra_versao TEXT,
                regra_fingerprint TEXT,
                features_json TEXT,
                status TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY,
                resultado TEXT,
                retorno_unidades REAL
            );
            """
        )
        hipotese = {
            "versao": "hipoteses-sombra-v2",
            "identificador": "proximo_gol_estado_teste",
            "regra_versao": "sinais-proximo-gol-teste",
            "regra_fingerprint": "fingerprint-teste",
            "mercado": "proximo_gol",
            "criterios": [
                {
                    "feature": "minuto",
                    "operador": "menor_igual",
                    "limiar": 70.0,
                },
                {
                    "feature": "saldo_alvo_proximo_gol",
                    "operador": "menor_igual",
                    "limiar": 1.0,
                },
            ],
            "combinador": "todos",
            "iniciado_em": "2026-08-13T12:00:00",
            "minimo_resultados": 60,
            "aplicacao_automatica": False,
        }
        snapshots = [(1, "0-0"), (2, "2-1"), (3, "3-1")]
        conexao.executemany(
            "INSERT INTO snapshots(id, placar) VALUES (?, ?)", snapshots
        )
        sinais = [
            (
                1, 10, 1, "2026-08-13T11:59:59", "proximo_gol",
                "casa", 1.80, 80.0, "sinais-proximo-gol-teste",
                "fingerprint-teste", json.dumps({"minuto": 60}),
                "aprovado",
            ),
            (
                2, 11, 2, "2026-08-13T12:00:01", "proximo_gol",
                "casa", 1.80, 80.0, "sinais-proximo-gol-teste",
                "fingerprint-teste", json.dumps({"minuto": 69}),
                "aprovado",
            ),
            (
                3, 12, 3, "2026-08-13T12:00:02", "proximo_gol",
                "casa", 1.80, 80.0, "sinais-proximo-gol-teste",
                "fingerprint-teste", json.dumps({"minuto": 69}),
                "aprovado",
            ),
        ]
        conexao.executemany(
            """
            INSERT INTO sinais(
                id, partida_id, snapshot_id, criado_em, mercado, linha,
                odd, pontuacao_tecnica, regra_versao, regra_fingerprint,
                features_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sinais,
        )
        conexao.executemany(
            """
            INSERT INTO resultados_sinais(
                sinal_id, resultado, retorno_unidades
            ) VALUES (?, ?, ?)
            """,
            [(1, "green", 0.8), (2, "green", 0.8), (3, "red", -1.0)],
        )
        try:
            with (
                patch(
                    "hipoteses_sombra.listar_hipoteses_sombra",
                    return_value=[hipotese],
                ),
                patch(
                    "hipoteses_sombra.auditar_hipoteses_sombra",
                    return_value={"saudavel": True},
                ),
            ):
                resultado = avaliar_hipoteses_sombra(
                    conexao, "sinais-proximo-gol-teste"
                )
        finally:
            conexao.close()

        avaliacao = resultado["avaliacoes"][0]
        self.assertEqual(avaliacao["baseline"]["amostra"], 2)
        self.assertEqual(avaliacao["selecionada"]["amostra"], 1)
        self.assertEqual(avaliacao["controle_excluido"]["amostra"], 1)
        self.assertEqual(avaliacao["faltam"], 59)

    def test_avaliacao_ativa_inclui_cada_versao_sem_duplicar(self):
        def parcial(_conexao, regra):
            return {
                "avaliacoes": [{
                    "identificador": f"hipotese-{regra}",
                    "regra_versao": regra,
                }]
            }

        with (
            patch(
                "hipoteses_sombra.avaliar_hipoteses_sombra",
                side_effect=parcial,
            ) as avaliar,
            patch(
                "hipoteses_sombra.auditar_hipoteses_sombra",
                return_value={"saudavel": True},
            ),
        ):
            resultado = avaliar_hipoteses_sombra_ativas(
                object(),
                {
                    "gol_ft": "sinais-v6",
                    "proximo_gol": "sinais-v6",
                    "escanteios_ft_asiatico": "sinais-v7-ft-asiatico",
                },
            )

        self.assertEqual(
            [chamada.args[1] for chamada in avaliar.call_args_list],
            ["sinais-v6", "sinais-v7-ft-asiatico"],
        )
        self.assertEqual(len(resultado["avaliacoes"]), 2)
        self.assertEqual(
            resultado["versoes_ativas"],
            ["sinais-v6", "sinais-v7-ft-asiatico"],
        )


if __name__ == "__main__":
    unittest.main()
