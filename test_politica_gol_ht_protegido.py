import unittest

from politica_gol_ht_protegido import aplicar_politica_gol_ht_protegido
from versoes_gol_ht_protegido import VERSAO_GOL_HT_PROTEGIDO
from versoes_operacionais import VERSAO_GOL_HT_MAX_28


class PoliticaGolHTProtegidoTest(unittest.TestCase):
    @staticmethod
    def candidato(versao=VERSAO_GOL_HT_MAX_28, status="aprovado"):
        return {
            "mercado": "gol_ht",
            "regra_versao": versao,
            "status": status,
            "odd": 1.75,
            "motivos": [],
            "bloqueios": [],
            "features": {"minuto": 24},
        }

    def test_principal_fica_em_duas_linhagens_sombra_por_padrao(self):
        candidatos = [self.candidato()]
        resumo = aplicar_politica_gol_ht_protegido(candidatos, {})
        self.assertEqual(2, len(candidatos))
        self.assertEqual("simulacao", candidatos[0]["status"])
        self.assertEqual("simulacao", candidatos[1]["status"])
        self.assertEqual(
            VERSAO_GOL_HT_PROTEGIDO, candidatos[1]["regra_versao"]
        )
        self.assertFalse(
            candidatos[1]["features"]["gol_ht_protegido"]["telegram"]
        )
        self.assertEqual(0, resumo["oficiais"])
        self.assertEqual(1, resumo["v8c_sombra"])

    def test_liberacao_explicita_e_manual_cria_oficial(self):
        candidatos = [self.candidato()]
        resumo = aplicar_politica_gol_ht_protegido(
            candidatos, {"GOL_HT_PRINCIPAL_OFICIAL_ATIVO": "1"}
        )
        self.assertEqual("aprovado", candidatos[1]["status"])
        self.assertEqual(1, resumo["oficiais"])

    def test_nao_interfere_em_metodo_ht_independente(self):
        alternativo = self.candidato("gol-ht-antecipado-faixa-historica-v2")
        candidatos = [alternativo]
        resumo = aplicar_politica_gol_ht_protegido(candidatos, {})
        self.assertEqual([alternativo], candidatos)
        self.assertEqual(0, resumo["avaliados"])

    def test_nao_ressuscita_candidato_rejeitado(self):
        candidato = self.candidato(status="rejeitado")
        candidatos = [candidato]
        aplicar_politica_gol_ht_protegido(candidatos, {})
        self.assertEqual([candidato], candidatos)


if __name__ == "__main__":
    unittest.main()
