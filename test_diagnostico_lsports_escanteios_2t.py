import json
import unittest
import uuid
from pathlib import Path

from diagnostico_lsports_escanteios_2t import (
    carregar_amostra,
    carregar_amostra_com_proveniencia,
    gerar_relatorio,
    salvar_relatorio,
)


class DiagnosticoLSportsEscanteios2TTest(unittest.TestCase):
    def _contrato(self):
        return {
            "formato_preco": "decimal",
            "status_ativos": [1],
            "status_liquidado": 3,
            "settlement_vencedor": [1],
            "settlement_perdedor": [2],
            "settlement_reembolso": [3],
            "origem_mapeamento": "contrato escrito do trial LSports",
        }

    def _apostas(self, *, status=1, linha_over=4.5, linha_under=4.5):
        return [
            {
                "Id": 101,
                "Name": "Over",
                "Line": linha_over,
                "BaseLine": 4.5,
                "Status": status,
                "Price": 1.91,
                "LastUpdate": "2026-09-09T20:10:00Z",
            },
            {
                "Id": 102,
                "Name": "Under",
                "Line": linha_under,
                "BaseLine": 4.5,
                "Status": status,
                "Price": 1.89,
                "LastUpdate": "2026-09-09T20:10:00Z",
            },
        ]

    def _snapshot(self, *, mercado=None, apostas=None, provider=True):
        mercado = mercado or "2nd Half Corners Over/Under"
        item_mercado = {
            "Id": 2201,
            "Name": mercado,
        }
        if provider:
            item_mercado["Providers"] = {
                "Provider": [{
                    "Id": 8,
                    "Name": "Bookmaker de teste",
                    "LastUpdate": "2026-09-09T20:10:00Z",
                    "Bets": {"Bet": apostas or self._apostas()},
                }]
            }
        return {
            "Message": {
                "Header": {
                    "Type": 31,
                    "CreationDate": "2026-09-09T20:10:05Z",
                },
                "MessageBody": {
                    "Events": {
                        "Event": [{
                            "FixtureId": 9001,
                            "Fixture": {
                                "Sport": {"Id": 6046, "Name": "Football"},
                                "League": {"Id": 88, "Name": "Liga Teste"},
                                "Participants": {
                                    "Participant": [
                                        {"Id": 1, "Name": "Casa", "Position": 1},
                                        {"Id": 2, "Name": "Fora", "Position": 2},
                                    ]
                                },
                            },
                            "Livescore": {
                                "Scoreboard": {"CurrentPeriod": 2}
                            },
                            "Markets": {"Market": [item_mercado]},
                        }]
                    }
                }
            }
        }

    def _liquidacao(self, *, mercado=None, resultados=(1, 2)):
        mercado = mercado or "2nd Half Corners Over/Under"
        apostas = self._apostas(status=3)
        apostas[0]["Settlement"] = resultados[0]
        apostas[1]["Settlement"] = resultados[1]
        apostas[0]["LastUpdate"] = "2026-09-09T21:00:00Z"
        apostas[1]["LastUpdate"] = "2026-09-09T21:00:00Z"
        return {
            "Header": {
                "Type": 35,
                "CreationDate": "2026-09-09T21:00:05Z",
            },
            "MessageBody": {
                "Events": [{
                    "FixtureId": 9001,
                    "Markets": [{
                        "Id": 2201,
                        "Name": mercado,
                        "Bets": apostas,
                    }],
                }]
            }
        }

    def _documento(self, **kwargs):
        return {
            "contrato": kwargs.get("contrato", self._contrato()),
            "snapshot": kwargs.get("snapshot", self._snapshot()),
            "liquidacao": kwargs.get("liquidacao", self._liquidacao()),
        }

    def test_comprova_par_2t_e_liquidacao_sem_ativar_fonte(self):
        relatorio = gerar_relatorio(
            self._documento(),
            gerado_em="2026-09-09T22:00:00+00:00",
        )

        self.assertTrue(relatorio["oferta_real_comprovada"])
        self.assertTrue(relatorio["liquidacao_comprovada"])
        self.assertTrue(relatorio["apto_apenas_integracao_sombra"])
        self.assertFalse(relatorio["habilita_integracao_automatica"])
        self.assertEqual(relatorio["requisicoes_realizadas"], 0)
        self.assertEqual(relatorio["ofertas_validas"], 1)
        self.assertEqual(relatorio["liquidacoes_validas"], 1)
        self.assertEqual(relatorio["ofertas"][0]["linha"], 4.5)
        self.assertEqual(relatorio["ofertas"][0]["over"]["odd"], 1.91)

    def test_segundo_tempo_da_partida_nao_transforma_mercado_ft_em_2t(self):
        snapshot = self._snapshot(mercado="Corners Over/Under")
        relatorio = gerar_relatorio(self._documento(snapshot=snapshot))

        self.assertFalse(relatorio["oferta_real_comprovada"])
        self.assertEqual(relatorio["mercados_2t_estruturais_encontrados"], 0)
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn("mercado_2t_cantos_over_under_nao_encontrado", motivos)

    def test_rejeita_exactly_mesmo_ao_lado_de_over_e_under(self):
        apostas = self._apostas()
        apostas.append({
            "Id": 103,
            "Name": "Exactly",
            "Line": 4.5,
            "BaseLine": 4.5,
            "Status": 1,
            "Price": 3.2,
            "LastUpdate": "2026-09-09T20:10:00Z",
        })
        relatorio = gerar_relatorio(
            self._documento(snapshot=self._snapshot(apostas=apostas))
        )

        self.assertFalse(relatorio["oferta_real_comprovada"])
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn(
            "mercado_contem_opcao_diferente_de_over_under", motivos
        )

    def test_rejeita_linhas_diferentes_no_par(self):
        snapshot = self._snapshot(
            apostas=self._apostas(linha_over=4.5, linha_under=5.5)
        )
        relatorio = gerar_relatorio(self._documento(snapshot=snapshot))

        self.assertFalse(relatorio["oferta_real_comprovada"])
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn("par_over_under_incompleto", motivos)

    def test_rejeita_provider_ausente(self):
        relatorio = gerar_relatorio(
            self._documento(snapshot=self._snapshot(provider=False))
        )

        self.assertFalse(relatorio["oferta_real_comprovada"])
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn("provider_ausente", motivos)

    def test_sem_mapeamento_contratual_nao_comprova_status(self):
        relatorio = gerar_relatorio(self._documento(contrato={}))

        self.assertFalse(relatorio["oferta_real_comprovada"])
        self.assertFalse(relatorio["liquidacao_comprovada"])
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn("mapeamento_status_ativo_ausente", motivos)
        self.assertIn("mapeamento_liquidacao_incompleto", motivos)

    def test_oferta_sem_liquidacao_so_permite_continuar_bloqueado(self):
        relatorio = gerar_relatorio(self._documento(liquidacao=None))

        self.assertTrue(relatorio["oferta_real_comprovada"])
        self.assertFalse(relatorio["liquidacao_comprovada"])
        self.assertFalse(relatorio["apto_apenas_integracao_sombra"])
        self.assertFalse(relatorio["habilita_integracao_automatica"])

    def test_liquidacao_precisa_corresponder_aos_ids_da_oferta(self):
        liquidacao = self._liquidacao()
        evento = liquidacao["MessageBody"]["Events"][0]
        evento["Markets"][0]["Bets"][0]["Id"] = 999
        relatorio = gerar_relatorio(
            self._documento(liquidacao=liquidacao)
        )

        self.assertTrue(relatorio["oferta_real_comprovada"])
        self.assertFalse(relatorio["liquidacao_comprovada"])
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn("liquidacao_nao_corresponde_a_oferta", motivos)

    def test_rejeita_snapshot_com_odd_antiga(self):
        snapshot = self._snapshot()
        snapshot["Message"]["Header"][
            "CreationDate"
        ] = "2026-09-09T21:00:05Z"
        relatorio = gerar_relatorio(self._documento(snapshot=snapshot))

        self.assertFalse(relatorio["oferta_real_comprovada"])
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn("provider_last_update_ausente_ou_antigo", motivos)

    def test_rejeita_liquidacao_sem_tipo_oficial_35(self):
        liquidacao = self._liquidacao()
        liquidacao["Header"]["Type"] = 34
        relatorio = gerar_relatorio(
            self._documento(liquidacao=liquidacao)
        )

        self.assertTrue(relatorio["oferta_real_comprovada"])
        self.assertFalse(relatorio["liquidacao_comprovada"])
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn("tipo_mensagem_liquidacao_nao_e_35", motivos)

    def test_rejeita_liquidacao_anterior_ao_snapshot(self):
        liquidacao = self._liquidacao()
        liquidacao["Header"][
            "CreationDate"
        ] = "2026-09-09T20:00:00Z"
        relatorio = gerar_relatorio(
            self._documento(liquidacao=liquidacao)
        )

        self.assertTrue(relatorio["oferta_real_comprovada"])
        self.assertFalse(relatorio["liquidacao_comprovada"])
        motivos = {item["motivo"] for item in relatorio["motivos_bloqueio"]}
        self.assertIn("liquidacao_nao_e_posterior_a_oferta", motivos)

    def test_carrega_e_salva_json_sem_incluir_payload_bruto(self):
        sufixo = uuid.uuid4().hex
        entrada = Path.cwd() / f".teste_lsports_entrada_{sufixo}.json"
        saida = Path.cwd() / f".teste_lsports_saida_{sufixo}.json"
        try:
            documento = self._documento()
            documento["segredo_do_trial"] = "nao-pode-sair"
            entrada.write_text(
                json.dumps(documento, ensure_ascii=False), encoding="utf-8"
            )

            carregado = carregar_amostra(entrada)
            carregado_prova, proveniencia = (
                carregar_amostra_com_proveniencia(entrada)
            )
            self.assertEqual(carregado_prova, carregado)
            salvar_relatorio(
                gerar_relatorio(
                    carregado,
                    entrada_sha256=proveniencia["sha256"],
                    entrada_bytes=proveniencia["bytes"],
                ),
                saida,
            )
            texto_saida = saida.read_text(encoding="utf-8")
            self.assertNotIn("nao-pode-sair", texto_saida)
            self.assertNotIn(
                "contrato escrito do trial LSports", texto_saida
            )
            self.assertTrue(json.loads(texto_saida)["liquidacao_comprovada"])
            evidencia = json.loads(texto_saida)["evidencia_entrada"]
            self.assertEqual(len(evidencia["sha256"]), 64)
            self.assertGreater(evidencia["bytes"], 0)
            self.assertFalse(evidencia["payload_bruto_persistido"])
        finally:
            entrada.unlink(missing_ok=True)
            saida.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
