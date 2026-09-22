import unittest
from unittest.mock import Mock, patch

from hipoteses_sombra import avaliar_hipotese_registros
from registrar_hipotese_gol_ft_ritmo_escanteios import (
    EVIDENCIA_HISTORICA,
    FEATURE,
    IDENTIFICADOR,
    LIMIAR,
    MINIMO_RESULTADOS,
    registrar,
)


class RegistrarHipoteseGolFTRitmoEscanteiosTest(unittest.TestCase):
    def test_registro_e_prospectivo_e_nao_automatico(self):
        conexao = Mock()
        with patch(
            "registrar_hipotese_gol_ft_ritmo_escanteios."
            "registrar_hipotese_sombra",
            return_value={"aplicacao_automatica": False},
        ) as registrar_fn:
            resultado = registrar(
                conexao, iniciado_em="2026-08-09T13:30:00"
            )

        self.assertFalse(resultado["aplicacao_automatica"])
        self.assertEqual(MINIMO_RESULTADOS, 30)
        self.assertTrue(
            EVIDENCIA_HISTORICA["busca_exploratoria_multiplos_cortes"]
        )
        self.assertTrue(EVIDENCIA_HISTORICA["validacao_original_movel"])
        registrar_fn.assert_called_once_with(
            conexao,
            IDENTIFICADOR,
            "sinais-v6",
            "gol_ft",
            FEATURE,
            "maior_igual",
            LIMIAR,
            EVIDENCIA_HISTORICA,
            minimo_resultados=30,
            iniciado_em="2026-08-09T13:30:00",
        )

    def test_avaliacao_le_feature_aninhada_do_snapshot(self):
        hipotese = {
            "identificador": IDENTIFICADOR,
            "regra_versao": "sinais-v6",
            "mercado": "gol_ft",
            "feature": FEATURE,
            "operador": "maior_igual",
            "limiar": LIMIAR,
            "minimo_resultados": 30,
            "iniciado_em": "2026-08-09T13:30:00",
        }
        registros = [
            {
                "sinal_id": 1,
                "partida_id": 10,
                "criado_em": "2026-08-09T13:31:00",
                "resultado": "green",
                "retorno_unidades": 0.8,
                "features": {
                    "janelas": {
                        "5": {"escanteios_por_minuto": 0.20}
                    }
                },
            },
            {
                "sinal_id": 2,
                "partida_id": 11,
                "criado_em": "2026-08-09T13:32:00",
                "resultado": "red",
                "retorno_unidades": -1.0,
                "features": {
                    "janelas": {
                        "5": {"escanteios_por_minuto": 0.10}
                    }
                },
            },
        ]

        avaliacao = avaliar_hipotese_registros(hipotese, registros)

        self.assertEqual(avaliacao["selecionada"]["amostra"], 1)
        self.assertEqual(avaliacao["controle_excluido"]["amostra"], 1)
        self.assertEqual(avaliacao["faltam"], 29)


if __name__ == "__main__":
    unittest.main()
