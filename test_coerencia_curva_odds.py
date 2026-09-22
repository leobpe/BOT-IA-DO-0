import unittest

from coerencia_curva_odds import (
    validar_coerencia_curva_candidato,
    validar_coerencia_curva_odds,
    validar_evidencia_anomalia_curva,
)


def origem(identificador="grupo-a", linha=0.5):
    return {
        "schema": "origem-mercado-odd-v1",
        "fonte": "betsapi",
        "identificador": identificador,
        "nome": "Match Goals",
        "linha": linha,
        "lados": ["over", "under"],
        "bookmaker": "bet365",
    }


def oferta(linha, over, under, identificador="grupo-a"):
    return {
        "linha": linha, "over": over, "under": under,
        "origem_mercado": origem(identificador, linha),
    }


class CoerenciaCurvaOddsTest(unittest.TestCase):
    def test_aceita_curva_binaria_monotona(self):
        resultado = validar_coerencia_curva_odds([
            oferta(0.5, 1.20, 5.00),
            oferta(1.5, 1.80, 2.00),
            oferta(2.5, 2.50, 1.50),
        ], origem("grupo-a", 1.5))

        self.assertTrue(resultado["valida"])
        self.assertEqual("curva_linhas_odd_confirmada", resultado["motivo"])
        self.assertEqual(2, resultado["pares_comparados"])

    def test_rejeita_over_e_under_dominados(self):
        resultado = validar_coerencia_curva_odds([
            oferta(0.5, 2.00, 1.70),
            oferta(1.5, 1.80, 2.00),
        ], origem("grupo-a", 1.5))

        self.assertFalse(resultado["valida"])
        self.assertEqual("curva_linhas_odd_incoerente", resultado["motivo"])
        self.assertEqual("ambos", resultado["lado_incoerente"])

    def test_nao_compara_linhas_de_grupos_diferentes(self):
        resultado = validar_coerencia_curva_odds([
            oferta(0.5, 2.00, 1.70, "grupo-a"),
            oferta(1.5, 1.80, 2.00, "grupo-b"),
        ])

        self.assertTrue(resultado["valida"])
        self.assertEqual(
            "curva_linhas_odd_sem_par_comparavel", resultado["motivo"]
        )
        self.assertEqual(0, resultado["pares_comparados"])

    def test_ignora_linha_quarto_sem_dominio_binario_exato(self):
        resultado = validar_coerencia_curva_odds([
            oferta(1.25, 2.00, 1.70),
            oferta(1.5, 1.80, 2.00),
        ], origem("grupo-a", 1.5))

        self.assertTrue(resultado["valida"])
        self.assertEqual(0, resultado["pares_comparados"])

    def test_reconstitui_curva_exata_do_candidato_no_payload_completo(self):
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "formato": "duas_opcoes",
            "ofertas": [
                oferta(0.5, 1.20, 5.00),
                oferta(1.5, 1.80, 2.00),
                oferta(2.5, 2.50, 1.50),
            ],
            "ofertas_ht": [],
        }]}

        resultado = validar_coerencia_curva_candidato(
            odds, "gol_ft", 1.5, origem("grupo-a", 1.5)
        )

        self.assertTrue(resultado["valida"])
        self.assertEqual(3, len(resultado["ofertas_curva"]))
        self.assertEqual(2, resultado["pares_comparados"])

    def test_prova_de_inversao_pode_ser_recalculada_e_detecta_adulteracao(self):
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "formato": "duas_opcoes",
            "ofertas": [
                oferta(0.5, 2.00, 1.70),
                oferta(1.5, 1.80, 2.00),
            ],
            "ofertas_ht": [],
        }]}
        resultado = validar_coerencia_curva_candidato(
            odds, "gol_ft", 1.5, origem("grupo-a", 1.5)
        )

        self.assertFalse(resultado["valida"])
        self.assertTrue(validar_evidencia_anomalia_curva(
            resultado,
            mercado="gol_ft",
            linha=1.5,
            origem_selecionada=origem("grupo-a", 1.5),
        )["valida"])
        resultado["lado_incoerente"] = "over"
        self.assertFalse(validar_evidencia_anomalia_curva(
            resultado,
            mercado="gol_ft",
            linha=1.5,
            origem_selecionada=origem("grupo-a", 1.5),
        )["valida"])

    def test_nao_valida_curva_de_preco_diferente_da_oferta_escolhida(self):
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "total",
            "formato": "duas_opcoes",
            "ofertas": [
                oferta(0.5, 1.20, 5.00),
                oferta(1.5, 1.80, 2.00),
            ],
            "ofertas_ht": [],
        }]}

        resultado = validar_coerencia_curva_candidato(
            odds,
            "gol_ft",
            1.5,
            origem("grupo-a", 1.5),
            odd_selecionada=1.90,
            odd_oposta_selecionada=2.00,
        )

        self.assertFalse(resultado["valida"])
        self.assertEqual(
            "oferta_curva_odd_nao_localizada", resultado["motivo"]
        )


if __name__ == "__main__":
    unittest.main()
