import unittest

from top_criterios_gols import (
    VERSAO_FT, VERSAO_HT, gerar_top_criterio_ft, gerar_top_criterio_ht,
)
from telegram_alertas import (
    candidato_top_criterio_grupo_teste,
    motivo_suspensao_simulacao,
)


def _contexto(taxa=0.8):
    base = {
        "jogos": 10,
        "marcou_ht_taxa": taxa, "sofreu_ht_taxa": taxa,
        "over_0_5_ht_taxa": taxa,
        "marcou_ft_taxa": taxa, "sofreu_ft_taxa": taxa,
        "over_1_5_ft_taxa": taxa, "over_2_5_ft_taxa": 0.6,
        "btts_ft_taxa": 0.6,
    }
    return {"historico_periodos_10": {
        "mandante": dict(base), "visitante": dict(base),
    }}


def _candidato(mercado):
    return {
        "mercado": mercado, "linha": 0.5, "odd": 1.6,
        "status": "simulacao", "bloqueios": [],
        "motivos": ["origem"], "features": {},
    }


class TopCriteriosGolsTest(unittest.TestCase):
    def test_top_ht_exige_e_preserva_10_jogos(self):
        itens = gerar_top_criterio_ht([_candidato("gol_ht")], _contexto())
        self.assertEqual(1, len(itens))
        self.assertEqual(
            VERSAO_HT, itens[0]["features"]["exploracao_sombra"]["versao"]
        )
        self.assertEqual(
            10, itens[0]["features"]["top_criterio_gols"]
            ["jogos_casa_fora_exigidos"]
        )
        self.assertTrue(candidato_top_criterio_grupo_teste(itens[0]))
        self.assertIsNone(motivo_suspensao_simulacao(itens[0]))

    def test_top_ft_exige_80_porcento(self):
        itens = gerar_top_criterio_ft([_candidato("gol_ft")], _contexto())
        self.assertEqual(1, len(itens))
        self.assertEqual(
            VERSAO_FT, itens[0]["features"]["exploracao_sombra"]["versao"]
        )
        self.assertEqual([], gerar_top_criterio_ft(
            [_candidato("gol_ft")], _contexto(0.7)
        ))


if __name__ == "__main__":
    unittest.main()
