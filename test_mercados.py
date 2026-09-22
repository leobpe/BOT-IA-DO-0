import unittest

from mercados import (
    filtrar_mercados_operacionais,
    mercados_calibrados_operacionais,
)


class MercadosOperacionaisTest(unittest.TestCase):
    def setUp(self):
        self.candidatos = [
            {"mercado": "gol_ft"},
            {"mercado": "proximo_escanteio"},
            {"mercado": "escanteios_ft_asiatico"},
            {"mercado": "escanteios_1t"},
            {"mercado": "escanteios_2t"},
        ]

    def test_suspende_periodos_sem_afetar_ft_ou_escanteio_normal(self):
        resultado = filtrar_mercados_operacionais(
            self.candidatos,
            environ={},
        )
        mercados = [item["mercado"] for item in resultado]

        self.assertEqual(
            mercados,
            [
                "gol_ft",
                "proximo_escanteio",
                "escanteios_ft_asiatico",
            ],
        )

    def test_reativacao_explicita_preserva_periodos(self):
        resultado = filtrar_mercados_operacionais(
            self.candidatos,
            environ={"ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS": "1"},
        )

        self.assertEqual(resultado, self.candidatos)

    def test_prontidao_exige_periodos_somente_quando_ativos(self):
        desligados = mercados_calibrados_operacionais(
            {"ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS": "0"}
        )
        ligados = mercados_calibrados_operacionais(
            {"ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS": "1"}
        )

        self.assertNotIn("escanteios_1t", desligados)
        self.assertNotIn("escanteios_2t", desligados)
        self.assertIn("escanteios_1t", ligados)
        self.assertIn("escanteios_2t", ligados)


if __name__ == "__main__":
    unittest.main()
