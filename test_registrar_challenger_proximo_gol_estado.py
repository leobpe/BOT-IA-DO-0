import unittest
from unittest.mock import Mock, patch

from registrar_challenger_proximo_gol_estado import (
    CRITERIOS,
    EVIDENCIA_HISTORICA,
    IDENTIFICADOR,
    MINIMO_RESULTADOS,
    REGRA_VERSAO,
    registrar,
)


class RegistrarChallengerProximoGolEstadoTest(unittest.TestCase):
    def test_registro_e_prospectivo_imutavel_e_sem_promocao(self):
        conexao = Mock()
        with patch(
            "registrar_challenger_proximo_gol_estado."
            "registrar_hipotese_composta_sombra",
            return_value={"aplicacao_automatica": False},
        ) as registrar_fn:
            resultado = registrar(
                conexao, iniciado_em="2026-08-13T20:00:00"
            )

        self.assertFalse(resultado["aplicacao_automatica"])
        self.assertEqual(MINIMO_RESULTADOS, 60)
        self.assertEqual(
            CRITERIOS,
            [
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
        )
        self.assertEqual(
            EVIDENCIA_HISTORICA["corte_exploratorio"]["roi"], 0.1577
        )
        self.assertEqual(
            EVIDENCIA_HISTORICA["corte_exploratorio"][
                "resultados_validos"
            ],
            58,
        )
        registrar_fn.assert_called_once_with(
            conexao,
            IDENTIFICADOR,
            REGRA_VERSAO,
            "proximo_gol",
            CRITERIOS,
            EVIDENCIA_HISTORICA,
            minimo_resultados=60,
            iniciado_em="2026-08-13T20:00:00",
        )


if __name__ == "__main__":
    unittest.main()
