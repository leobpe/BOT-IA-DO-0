import unittest
from unittest.mock import Mock, patch

from registrar_hipotese_gol_ft_movimento import (
    CRITERIOS,
    EVIDENCIA_HISTORICA,
    IDENTIFICADOR,
    MINIMO_RESULTADOS,
    registrar,
)


class RegistrarHipoteseGolFTMovimentoTest(unittest.TestCase):
    def test_registro_e_prospectivo_e_nao_automatico(self):
        conexao = Mock()
        with patch(
            "registrar_hipotese_gol_ft_movimento."
            "registrar_hipotese_composta_sombra",
            return_value={"aplicacao_automatica": False},
        ) as registrar_fn:
            resultado = registrar(
                conexao, iniciado_em="2026-08-08T10:00:00"
            )

        self.assertFalse(resultado["aplicacao_automatica"])
        self.assertEqual(MINIMO_RESULTADOS, 30)
        self.assertTrue(
            EVIDENCIA_HISTORICA[
                "busca_exploratoria_multiplos_cortes"
            ]
        )
        self.assertEqual(
            [item["feature"] for item in CRITERIOS],
            [
                "movimento_gols.delta",
                "movimento_gols.odd_atual",
            ],
        )
        registrar_fn.assert_called_once_with(
            conexao,
            IDENTIFICADOR,
            "sinais-v6",
            "gol_ft",
            CRITERIOS,
            EVIDENCIA_HISTORICA,
            minimo_resultados=30,
            iniciado_em="2026-08-08T10:00:00",
        )


if __name__ == "__main__":
    unittest.main()
