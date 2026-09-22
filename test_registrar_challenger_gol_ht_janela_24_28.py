import unittest
from unittest.mock import Mock, patch

from registrar_challenger_gol_ht_janela_24_28 import (
    CRITERIOS,
    EVIDENCIA_HISTORICA,
    IDENTIFICADOR,
    MERCADO,
    MINIMO_RESULTADOS,
    REGRA_VERSAO,
    registrar,
)
from versoes_operacionais import VERSAO_GOL_HT_MAX_28


class RegistrarChallengerGolHtJanela2428Test(unittest.TestCase):
    def test_registro_futuro_composto_e_sem_promocao(self):
        conexao = Mock()
        with patch(
            "registrar_challenger_gol_ht_janela_24_28."
            "registrar_hipotese_composta_sombra",
            return_value={"aplicacao_automatica": False},
        ) as registrar_fn:
            resultado = registrar(
                conexao, iniciado_em="2026-08-13T20:30:00"
            )

        self.assertFalse(resultado["aplicacao_automatica"])
        self.assertEqual(REGRA_VERSAO, VERSAO_GOL_HT_MAX_28)
        self.assertEqual(MERCADO, "gol_ht")
        self.assertEqual(MINIMO_RESULTADOS, 40)
        self.assertEqual(
            CRITERIOS,
            [
                {
                    "feature": "minuto",
                    "operador": "maior_igual",
                    "limiar": 24.0,
                },
                {
                    "feature": "minuto",
                    "operador": "menor_igual",
                    "limiar": 28.0,
                },
            ],
        )
        self.assertEqual(
            EVIDENCIA_HISTORICA["corte_exploratorio"][
                "resultados_validos"
            ],
            30,
        )
        self.assertEqual(
            EVIDENCIA_HISTORICA["corte_exploratorio"]["roi"],
            0.3243,
        )
        self.assertTrue(
            EVIDENCIA_HISTORICA["criterio_confirmacao_futura"][
                "controle_contemporaneo"
            ]
        )
        registrar_fn.assert_called_once_with(
            conexao,
            IDENTIFICADOR,
            REGRA_VERSAO,
            MERCADO,
            CRITERIOS,
            EVIDENCIA_HISTORICA,
            minimo_resultados=40,
            iniciado_em="2026-08-13T20:30:00",
        )


if __name__ == "__main__":
    unittest.main()
