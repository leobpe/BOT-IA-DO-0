import unittest
from unittest.mock import Mock, patch

from registrar_challenger_gol_ht_nota_max_81_5 import (
    EVIDENCIA_HISTORICA,
    FEATURE,
    IDENTIFICADOR,
    LIMIAR,
    MERCADO,
    MINIMO_RESULTADOS,
    OPERADOR,
    REGRA_VERSAO,
    registrar,
)
from versoes_operacionais import VERSAO_GOL_HT_MAX_28


class RegistrarChallengerGolHtNotaMax815Test(unittest.TestCase):
    def test_registro_futuro_simples_e_sem_promocao(self):
        conexao = Mock()
        with patch(
            "registrar_challenger_gol_ht_nota_max_81_5."
            "registrar_hipotese_sombra",
            return_value={"aplicacao_automatica": False},
        ) as registrar_fn:
            resultado = registrar(
                conexao, iniciado_em="2026-08-25T01:45:00"
            )

        self.assertFalse(resultado["aplicacao_automatica"])
        self.assertEqual(REGRA_VERSAO, VERSAO_GOL_HT_MAX_28)
        self.assertEqual(MERCADO, "gol_ht")
        self.assertEqual(FEATURE, "pontuacao_tecnica")
        self.assertEqual(OPERADOR, "menor_igual")
        self.assertEqual(LIMIAR, 81.5)
        self.assertEqual(MINIMO_RESULTADOS, 40)
        self.assertTrue(
            EVIDENCIA_HISTORICA["busca_exploratoria_multiplos_cortes"]
        )
        self.assertEqual(
            EVIDENCIA_HISTORICA["validacao_exploratoria_posterior"][
                "resultados_validos"
            ],
            17,
        )
        registrar_fn.assert_called_once_with(
            conexao,
            IDENTIFICADOR,
            REGRA_VERSAO,
            MERCADO,
            FEATURE,
            OPERADOR,
            LIMIAR,
            EVIDENCIA_HISTORICA,
            minimo_resultados=40,
            iniciado_em="2026-08-25T01:45:00",
        )


if __name__ == "__main__":
    unittest.main()
