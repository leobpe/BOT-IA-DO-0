import json
import unittest

from analise_proximo_gol_balanceado import (
    metricas,
    normalizar_linha,
    selecionar_balanceado_sombra,
    selecionar_oportunidades,
)
from politica_proximo_gol_preciso import MOTIVO_PRESSAO


class AnaliseProximoGolBalanceadoTest(unittest.TestCase):
    def _linha(self, **alteracoes):
        features = {
            "minuto": 40,
            "qualidade_dados": 100,
            "gols_atuais": 0,
            "lado_dominante": "casa",
            "chutes_lado_dominante_5min": 2,
            "janelas": {
                "5": {
                    "pressao_pico": [65, 20],
                    "pressao_media": [60, 20],
                }
            },
            "auditoria_bloqueio": {
                "bloqueios_originais": [MOTIVO_PRESSAO]
            },
        }
        linha = {
            "id": 1,
            "partida_id": 10,
            "criado_em": "2026-09-08T18:00:00",
            "odd": 1.5,
            "pontuacao_tecnica": 60,
            "status": "auditoria",
            "motivos_json": "[]",
            "features_json": json.dumps(features),
            "contexto_api_json": "{}",
            "placar": "0-0",
            "resultado": "green",
            "retorno_unidades": 0.5,
        }
        linha.update(alteracoes)
        return linha

    def test_exclui_auditoria_com_bloqueio_de_seguranca(self):
        linha = self._linha()
        features = json.loads(linha["features_json"])
        features["auditoria_bloqueio"]["bloqueios_originais"].append(
            "lado_dominante_sem_chute_recente"
        )
        linha["features_json"] = json.dumps(features)
        self.assertIsNone(normalizar_linha(linha))

    def test_deduplica_primeiro_alerta_do_mesmo_estado_de_gols(self):
        primeira = normalizar_linha(self._linha())
        segunda_linha = self._linha(
            id=2,
            criado_em="2026-09-08T18:01:00",
            resultado="red",
            retorno_unidades=-1.0,
        )
        segunda = normalizar_linha(segunda_linha)
        itens = selecionar_oportunidades(
            [segunda, primeira], qualidade_minima=100, pressao_minima=60
        )
        self.assertEqual([1], [item["id"] for item in itens])
        self.assertEqual(1, metricas(itens)["greens"])

    def test_balanceado_aplica_confirmacao_antes_de_deduplicar(self):
        inicial = normalizar_linha(self._linha(odd=1.70))
        posterior = normalizar_linha(self._linha(
            id=2,
            criado_em="2026-09-08T18:01:00",
            odd=1.55,
        ))
        itens = selecionar_balanceado_sombra([inicial, posterior])
        self.assertEqual([2], [item["id"] for item in itens])


if __name__ == "__main__":
    unittest.main()
