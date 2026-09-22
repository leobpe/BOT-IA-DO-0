import unittest

from politica_gol_ft_reforcado import (
    VERSAO_BASE,
    aplicar_politica_gol_ft_reforcado,
)
from versoes_gol_ft_reforcado import (
    VERSAO_GOL_FT_REFORCADO,
    versao_regra_operacional,
    versoes_regras_operacionais,
)


class PoliticaGolFTReforcadoTest(unittest.TestCase):
    def candidato(
        self, minuto=63, odd=1.40, chutes=3,
        chutes_no_gol=7, pressao=92,
    ):
        return {
            "mercado": "gol_ft",
            "regra_versao": VERSAO_BASE,
            "status": "aprovado",
            "odd": odd,
            "bloqueios": [],
            "motivos": [],
            "features": {
                "minuto": minuto,
                "chutes_no_gol_total": chutes_no_gol,
                "janelas": {
                    "5": {
                        "chutes_total": chutes,
                        "pressao_pico": [pressao, 40],
                    }
                },
            },
        }

    @staticmethod
    def contexto(xg_casa=None, xg_fora=None):
        if xg_casa is None or xg_fora is None:
            return {}
        return {
            "estatisticas_ao_vivo": {
                "times": {
                    "mandante": {"xg": xg_casa},
                    "visitante": {"xg": xg_fora},
                }
            }
        }

    def test_packball_forte_fica_em_validacao_sombra_por_padrao(self):
        candidatos = [self.candidato()]

        resumo = aplicar_politica_gol_ft_reforcado(candidatos, {})

        self.assertEqual(resumo["oficiais"], 0)
        self.assertEqual(resumo["reforcados_sombra"], 1)
        self.assertEqual(len(candidatos), 2)
        self.assertEqual(candidatos[0]["status"], "simulacao")
        self.assertEqual(candidatos[0]["regra_versao"], VERSAO_BASE)
        self.assertEqual(candidatos[1]["status"], "simulacao")
        self.assertEqual(
            candidatos[1]["regra_versao"], VERSAO_GOL_FT_REFORCADO
        )
        self.assertFalse(
            candidatos[1]["features"]["gol_ft_reforcado"]["telegram"]
        )

    def test_liberacao_explicita_cria_oficial(self):
        candidatos = [self.candidato()]

        resumo = aplicar_politica_gol_ft_reforcado(
            candidatos,
            {},
            {"GOL_FT_REFORCADO_OFICIAL_ATIVO": "1"},
        )

        self.assertEqual(resumo["oficiais"], 1)
        self.assertEqual(candidatos[1]["status"], "aprovado")
        self.assertTrue(
            candidatos[1]["features"]["gol_ft_reforcado"]["telegram"]
        )

    def test_xg_forte_aprova_sem_pressao_packball(self):
        candidatos = [self.candidato(
            chutes=1, chutes_no_gol=3, pressao=40
        )]

        aplicar_politica_gol_ft_reforcado(
            candidatos,
            self.contexto(0.8, 0.7),
            {"GOL_FT_REFORCADO_OFICIAL_ATIVO": "1"},
        )

        self.assertEqual(len(candidatos), 2)
        self.assertTrue(
            candidatos[1]["features"]["gol_ft_reforcado"]
            ["criterios"]["xg_forte"]
        )

    def test_minuto_71_nao_cria_oficial(self):
        candidatos = [self.candidato(minuto=71)]

        aplicar_politica_gol_ft_reforcado(candidatos, {})

        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["status"], "simulacao")

    def test_odd_190_nao_cria_oficial(self):
        candidatos = [self.candidato(odd=1.90)]

        aplicar_politica_gol_ft_reforcado(candidatos, {})

        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["status"], "simulacao")

    def test_sem_xg_e_packball_fraco_fica_somente_no_v6_sombra(self):
        candidatos = [self.candidato(
            chutes=2, chutes_no_gol=6, pressao=74
        )]

        resumo = aplicar_politica_gol_ft_reforcado(candidatos, {})

        self.assertEqual(resumo["oficiais"], 0)
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["status"], "simulacao")

    def test_rollback_preserva_v6_oficial(self):
        candidatos = [self.candidato()]

        resumo = aplicar_politica_gol_ft_reforcado(
            candidatos, {}, {"GOL_FT_REFORCADO_ATIVO": "0"}
        )

        self.assertFalse(resumo["ativa"])
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["status"], "aprovado")

    def test_roteamento_operacional_usa_nova_versao(self):
        self.assertEqual(
            versao_regra_operacional("gol_ft"),
            VERSAO_GOL_FT_REFORCADO,
        )
        self.assertIn(
            VERSAO_GOL_FT_REFORCADO, versoes_regras_operacionais()
        )


if __name__ == "__main__":
    unittest.main()
