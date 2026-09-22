import json
import unittest

from diagnostico_totalcorner import (
    consultar_totalcorner,
    gerar_relatorio,
)


class _Resposta:
    headers = {
        "X-Rate-Limit-Limit": "30",
        "X-Rate-Limit-Remaining": "29",
    }

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class _Abridor:
    def __init__(self, payload):
        self.payload = payload
        self.chamadas = []

    def __call__(self, *args, **kwargs):
        self.chamadas.append((args, kwargs))
        return _Resposta(self.payload)


class DiagnosticoTotalCornerTest(unittest.TestCase):
    def _payload(self, historico):
        return {
            "success": 1,
            "data": [{
                "id": "123",
                "h": "Time A",
                "a": "Time B",
                "status": "32",
                "corner_half_list": historico,
                "outro_campo": "não deve aparecer",
            }],
        }

    def test_detecta_historico_real_de_duas_opcoes_sem_promover(self):
        relatorio = gerar_relatorio(self._payload([[
            "32", "4.5", "1.85", "1.95",
            "2026-07-30 12:00:00", "2", "1",
        ]]))

        self.assertTrue(relatorio["candidato_1t_encontrado"])
        self.assertFalse(relatorio["habilita_integracao_automatica"])
        candidato = relatorio[
            "candidatos_estruturais_duas_opcoes"
        ][0]
        self.assertEqual(candidato["linha"], "4.5")
        self.assertEqual(candidato["over"], 1.85)
        self.assertEqual(candidato["under"], 1.95)

    def test_rejeita_linha_de_tres_opcoes_exactly(self):
        relatorio = gerar_relatorio(self._payload([[
            "32", "4", "1.85", "3.20", "2.05",
            "2026-07-30 12:00:00", "2", "1",
        ]]))

        self.assertFalse(relatorio["candidato_1t_encontrado"])
        self.assertEqual(
            relatorio["candidatos_estruturais_duas_opcoes"], []
        )

    def test_faz_exatamente_uma_consulta_e_nao_vaza_token(self):
        token = "segredo-totalcorner"
        abrir = _Abridor(self._payload([]))

        relatorio = consultar_totalcorner(token, abrir=abrir)

        self.assertEqual(len(abrir.chamadas), 1)
        args, kwargs = abrir.chamadas[0]
        self.assertIn("columns=cornerLineHalf", args[0].full_url)
        self.assertEqual(kwargs["timeout"], 15)
        self.assertNotIn(
            token,
            json.dumps(relatorio, ensure_ascii=False),
        )
        self.assertEqual(relatorio["requisicoes_realizadas"], 1)
        self.assertEqual(relatorio["limite_requisicoes"], "30")

    def test_sem_token_nao_realiza_consulta(self):
        abrir = _Abridor(self._payload([]))

        with self.assertRaisesRegex(ValueError, "não configurado"):
            consultar_totalcorner("", abrir=abrir)

        self.assertEqual(abrir.chamadas, [])


if __name__ == "__main__":
    unittest.main()
