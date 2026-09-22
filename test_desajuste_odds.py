import unittest

from desajuste_odds import (
    calcular_evidencia_comparacao,
    construir_comparacoes_multifonte,
    validar_comparacao_persistida,
)


def registro(ofertas, *, coletado_em="2026-09-01T12:00:00"):
    return {
        "coletado_em": coletado_em,
        "placar": "0-0",
        "status": "25 '",
        "odds": {
            "ao_vivo": [{
                "categoria": "gols",
                "escopo": "total",
                "fonte": "packball",
                "coletado_em": coletado_em,
                "ofertas": ofertas,
            }],
        },
    }


class DesajusteOddsTest(unittest.TestCase):
    def test_prefere_fonte_da_oferta_e_compara_mesma_linha(self):
        dados = registro([
            {"linha": 2.5, "over": 1.50, "under": 2.40},
            {
                "linha": 2.5, "over": 1.65, "under": 2.20,
                "fonte": "betsapi", "bookmaker": "bet365",
                "coletado_em": "2026-09-01T12:00:10",
            },
        ])

        comparacoes = construir_comparacoes_multifonte(dados, 1, 2)

        over = next(
            item for item in comparacoes if item["selecao"] == "over"
        )
        self.assertEqual("desajuste_candidato", over["estado"])
        self.assertEqual("betsapi", over["fonte_melhor"])
        self.assertEqual(1.65, over["odd_melhor"])
        self.assertEqual(10.0, over["intervalo_fontes_segundos"])
        self.assertFalse(over.get("aplicacao_sinais", False))

    def test_descarta_cotacao_antiga_mesmo_com_gap_grande(self):
        dados = registro([
            {
                "linha": 2.5, "over": 1.50, "under": 2.40,
                "coletado_em": "2026-09-01T11:50:00",
            },
            {
                "linha": 2.5, "over": 2.20, "under": 1.60,
                "fonte": "betsapi",
                "coletado_em": "2026-09-01T12:00:00",
            },
        ])

        comparacoes = construir_comparacoes_multifonte(dados, 1, 2)

        self.assertTrue(comparacoes)
        self.assertTrue(all(
            item["estado"] == "descartado_cotacao_antiga"
            for item in comparacoes
        ))

    def test_nao_compara_linhas_diferentes(self):
        dados = registro([
            {"linha": 2.5, "over": 1.50, "under": 2.40},
            {
                "linha": 3.5, "over": 1.70, "under": 2.10,
                "fonte": "betsapi",
            },
        ])

        comparacoes = construir_comparacoes_multifonte(dados, 1, 2)

        self.assertEqual([], comparacoes)

    def test_descarta_fontes_em_minutos_incompativeis(self):
        dados = registro([
            {
                "linha": 2.5, "over": 1.50,
                "fonte": "packball", "_minuto_origem": 25,
            },
            {
                "linha": 2.5, "over": 1.80,
                "fonte": "betsapi", "_minuto_origem": 29,
            },
        ])

        comparacoes = construir_comparacoes_multifonte(dados, 1, 2)

        self.assertEqual(1, len(comparacoes))
        self.assertEqual(
            "descartado_minuto_divergente", comparacoes[0]["estado"]
        )
        self.assertEqual(
            {25.0, 29.0},
            {
                comparacoes[0]["minuto_fonte_a"],
                comparacoes[0]["minuto_fonte_b"],
            },
        )
        self.assertEqual(4.0, comparacoes[0]["diferenca_minutos"])

    def test_recalcula_hash_matematica_e_estado_da_comparacao(self):
        dados = registro([
            {
                "linha": 2.5, "over": 1.50, "under": 2.40,
                "_minuto_origem": 25,
            },
            {
                "linha": 2.5, "over": 1.65, "under": 2.20,
                "fonte": "betsapi", "bookmaker": "bet365",
                "coletado_em": "2026-09-01T12:00:10",
                "_minuto_origem": 25,
            },
        ])
        comparacao = next(
            item for item in construir_comparacoes_multifonte(
                dados, 1, 2
            )
            if item["selecao"] == "over"
        )

        valida = validar_comparacao_persistida(comparacao)
        adulterada = dict(comparacao)
        adulterada["odd_a"] = 1.51
        adulterada["odd_b"] = 1.50
        adulterada["odd_melhor"] = 9.0
        adulterada["delta_absoluto"] = 0.0
        adulterada["delta_relativo"] = 0.0
        adulterada["evidencia_sha256"] = calcular_evidencia_comparacao(
            adulterada
        )
        invalida = validar_comparacao_persistida(adulterada)

        self.assertTrue(valida["valida"])
        self.assertEqual([], valida["problemas"])
        self.assertFalse(invalida["valida"])
        self.assertNotIn(
            "evidencia_sha256_divergente", invalida["problemas"]
        )
        self.assertIn(
            "melhor_preco_ou_fonte_divergente", invalida["problemas"]
        )
        self.assertIn(
            "estado_comparacao_divergente", invalida["problemas"]
        )


if __name__ == "__main__":
    unittest.main()
