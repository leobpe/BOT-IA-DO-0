import json
import unittest

from diagnostico_funil_proximo_gol import (
    diagnosticar_linhas,
    resumir_auditoria_contrafactual,
)
from politica_proximo_gol_preciso import MOTIVO_PRESSAO


class DiagnosticoFunilProximoGolTest(unittest.TestCase):
    def _linha(self, identificador, partida=1, **alteracoes):
        features = {
            "gols_atuais": 0,
            "minuto": 60,
            "qualidade_dados": 100,
            "lado_dominante": "casa",
            "chutes_lado_dominante_5min": 1,
            "janelas": {"5": {
                "pressao_pico": [60, 20],
                "pressao_media": [40, 20],
            }},
        }
        linha = {
            "id": identificador,
            "partida_id": partida,
            "criado_em": f"2026-09-10T12:00:{identificador:02d}",
            "odd": 1.55,
            "pontuacao_tecnica": 60,
            "motivos_json": json.dumps([f"bloqueio:{MOTIVO_PRESSAO}"]),
            "features_json": json.dumps(features),
            "placar": "0-0",
        }
        linha.update(alteracoes)
        return linha

    def test_marginal_nao_e_zerado_pelo_primeiro_gate(self):
        linha = self._linha(
            1,
            motivos_json=json.dumps(["bloqueio:outro_bloqueio"]),
        )

        resumo = diagnosticar_linhas([linha])

        self.assertEqual(1, resumo["estados_independentes"])
        self.assertEqual(0, resumo["passagens_marginais"][
            "somente_bloqueios_pressao_qualidade"
        ])
        self.assertEqual(0, resumo["distancia_minima_observada"])
        self.assertEqual(1, resumo["candidato_pronto_sem_gate"])
        self.assertFalse(resumo["altera_sinais"])

    def test_escolhe_menor_distancia_no_mesmo_estado_sem_usar_resultado(self):
        features_fracas = {
            "gols_atuais": 0,
            "minuto": 60,
            "qualidade_dados": 90,
            "lado_dominante": "casa",
            "chutes_lado_dominante_5min": 0,
            "janelas": {"5": {
                "pressao_pico": [40, 35],
                "pressao_media": [35, 30],
            }},
        }
        primeira = self._linha(
            1,
            odd=2.2,
            pontuacao_tecnica=40,
            features_json=json.dumps(features_fracas),
        )
        segunda = self._linha(2)

        resumo = diagnosticar_linhas([primeira, segunda])

        self.assertEqual(1, resumo["estados_independentes"])
        self.assertEqual(0, resumo["distancia_minima_observada"])
        self.assertFalse(resumo["usa_resultados"])

    def test_expõe_quase_candidato_e_descarta_json_invalido(self):
        features = json.loads(self._linha(1)["features_json"])
        features["chutes_lado_dominante_5min"] = 0
        quase = self._linha(1, features_json=json.dumps(features))
        invalida = self._linha(2, features_json="{")

        resumo = diagnosticar_linhas([quase, invalida])

        self.assertEqual(1, resumo["linhas_invalidas"])
        self.assertEqual(1, resumo["distancia_minima_observada"])
        self.assertEqual(
            ["chute_dominante_recente"],
            resumo["combinacoes_quase_candidatas"][0]["falhas"],
        )

    def test_exclui_copia_de_auditoria_e_expoe_bloqueio_de_risco(self):
        original = self._linha(
            1,
            motivos_json=json.dumps([
                f"bloqueio:{MOTIVO_PRESSAO}",
                "bloqueio:cartao_vermelho_reavaliar",
            ]),
        )
        features_auditoria = json.loads(original["features_json"])
        features_auditoria["auditoria_bloqueio"] = {
            "versao": "auditoria-bloqueios-promissores-v1",
            "bloqueios_originais": [
                MOTIVO_PRESSAO, "cartao_vermelho_reavaliar"
            ],
        }
        copia = self._linha(
            2,
            features_json=json.dumps(features_auditoria),
            motivos_json="[]",
        )

        resumo = diagnosticar_linhas([original, copia])

        self.assertEqual(2, resumo["linhas_avaliadas"])
        self.assertEqual(1, resumo["linhas_derivadas_excluidas"])
        self.assertEqual(1, resumo["estados_independentes"])
        self.assertEqual(1, resumo["candidato_pronto_sem_gate"])
        self.assertEqual(0, resumo["candidato_pronto_com_gate"])
        self.assertEqual(
            {"cartao_vermelho_reavaliar": 1},
            resumo[
                "bloqueios_adicionais_estados_tecnicamente_prontos"
            ],
        )

    def test_auditoria_contrafactual_escolhe_primeira_antes_do_resultado(self):
        features = json.loads(self._linha(1)["features_json"])
        features["auditoria_bloqueio"] = {
            "versao": "auditoria-bloqueios-promissores-v1",
            "bloqueios_originais": [MOTIVO_PRESSAO],
        }
        primeira = self._linha(
            1,
            features_json=json.dumps(features),
            resultado="red",
            retorno_unidades=-1.0,
        )
        posterior = self._linha(
            2,
            features_json=json.dumps(features),
            resultado="green",
            retorno_unidades=1.0,
        )

        resumo = resumir_auditoria_contrafactual([posterior, primeira])

        self.assertEqual(1, resumo["estados"])
        self.assertEqual(1, resumo["validos"])
        self.assertEqual(0, resumo["greens"])
        self.assertEqual(1, resumo["reds"])
        self.assertEqual(-1.0, resumo["roi"])
        self.assertFalse(resumo["pode_alterar_filtro"])

    def test_auditoria_contrafactual_separa_pendente_e_invalido(self):
        features = json.loads(self._linha(1)["features_json"])
        features["auditoria_bloqueio"] = {
            "versao": "auditoria-bloqueios-promissores-v1",
            "bloqueios_originais": [MOTIVO_PRESSAO],
        }
        pendente = self._linha(
            1,
            features_json=json.dumps(features),
            resultado=None,
            retorno_unidades=None,
        )
        invalido = self._linha(
            2,
            partida=2,
            features_json=json.dumps(features),
            resultado="sem_dado",
            retorno_unidades=None,
        )

        resumo = resumir_auditoria_contrafactual([pendente, invalido])

        self.assertEqual(2, resumo["estados"])
        self.assertEqual(1, resumo["pendentes"])
        self.assertEqual(1, resumo["invalidos"])
        self.assertFalse(resumo["amostra_suficiente"])
        self.assertEqual("exploratoria_nao_inferencial", resumo["natureza"])


if __name__ == "__main__":
    unittest.main()
