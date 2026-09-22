import unittest
from datetime import datetime
from unittest.mock import patch

from acompanhamento_odd import (
    avaliar_rechecagem_odd_api,
    avaliar_resultado_acompanhamento_odd,
    extrair_odd_exata_acompanhamento,
    finalizar_acompanhamento_odd,
    preparar_acompanhamento_odd,
    validar_contrato_mercado_oferta,
)


def identidade_evento_teste(placar="0-2", fonte="betsapi"):
    return {
        "schema": "identidade-evento-odd-v1",
        "confirmada": True,
        "fonte": fonte,
        "evento_externo_id": "evento-123",
        "orientacao": "direta",
        "similaridade": 0.95,
        "mandante_normalizado": "Casa",
        "visitante_normalizado": "Fora",
        "placar_normalizado": placar,
        "metodo": "teste",
    }


def origem_mercado_teste(
    linha=2.5, fonte="betsapi", lados=("over", "under"),
):
    return {
        "schema": "origem-mercado-odd-v1",
        "fonte": fonte,
        "identificador": "mercado-123",
        "nome": "Match Goals",
        "linha": linha,
        "lados": list(lados),
        "bookmaker": "bet365",
    }


class AcompanhamentoOddTest(unittest.TestCase):
    @staticmethod
    def candidato(**alteracoes):
        candidato = {
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.25,
            "pontuacao_tecnica": 82.0,
            "qualidade_dados": 90.0,
            "status": "rejeitado",
            "bloqueios": ["odd_fora_da_faixa_operacional"],
            "features": {},
            "motivos": [],
        }
        candidato.update(alteracoes)
        return candidato

    def test_avisa_somente_apos_todas_as_protecoes_aprovarem(self):
        candidato = self.candidato()
        with patch.dict("os.environ", {
            "AVISO_AGUARDAR_ODD_ATIVO": "1",
            "AVISO_AGUARDAR_ODD_PISO": "1.10",
            "AVISO_AGUARDAR_ODD_ALVO": "1.40",
        }):
            self.assertEqual(preparar_acompanhamento_odd([candidato]), 1)
            self.assertEqual(candidato["status"], "simulacao")
            candidato["features"]["protecao_conversao_gols"] = {
                "aprovada": True,
            }
            candidato["features"]["protecao_tendencias_packball"] = {
                "aprovada": True,
            }
            resumo = finalizar_acompanhamento_odd(
                [candidato], fontes_saudaveis=True
            )
        self.assertEqual(resumo["elegiveis"], 1)
        self.assertEqual(candidato["status"], "rejeitado")
        self.assertTrue(
            candidato["features"]["acompanhamento_odd"][
                "elegivel_aviso"
            ]
        )

    def test_bloqueio_tecnico_adicional_impede_aviso(self):
        candidato = self.candidato(bloqueios=[
            "odd_fora_da_faixa_operacional",
            "atividade_recente_insuficiente_gols",
        ])
        with patch.dict("os.environ", {
            "AVISO_AGUARDAR_ODD_ATIVO": "1",
            "AVISO_AGUARDAR_ODD_ALVO": "1.40",
        }):
            self.assertEqual(preparar_acompanhamento_odd([candidato]), 0)
        self.assertNotIn("acompanhamento_odd", candidato["features"])

    def test_odd_abaixo_do_piso_nao_poluira_o_grupo(self):
        candidato = self.candidato(odd=1.05)
        with patch.dict("os.environ", {
            "AVISO_AGUARDAR_ODD_ATIVO": "1",
            "AVISO_AGUARDAR_ODD_PISO": "1.10",
            "AVISO_AGUARDAR_ODD_ALVO": "1.40",
        }):
            self.assertEqual(preparar_acompanhamento_odd([candidato]), 0)

    def test_carteira_operacional_nao_extrapola_vantagem_do_ft_para_ht(self):
        candidato_ft = self.candidato(mercado="gol_ft")
        candidato_ht = self.candidato(mercado="gol_ht")
        with patch.dict("os.environ", {
            "AVISO_AGUARDAR_ODD_ATIVO": "1",
            "AVISO_AGUARDAR_ODD_MERCADOS": "gol_ft",
        }):
            self.assertEqual(
                preparar_acompanhamento_odd([candidato_ft, candidato_ht]),
                1,
            )
        self.assertIn("acompanhamento_odd", candidato_ft["features"])
        self.assertNotIn("acompanhamento_odd", candidato_ht["features"])

    def test_fontes_ou_protecoes_reprovadas_fecham_o_aviso(self):
        candidato = self.candidato()
        with patch.dict("os.environ", {
            "AVISO_AGUARDAR_ODD_ATIVO": "1",
            "AVISO_AGUARDAR_ODD_ALVO": "1.40",
        }):
            preparar_acompanhamento_odd([candidato])
            candidato["features"]["protecao_conversao_gols"] = {
                "aprovada": True,
            }
            candidato["features"]["protecao_tendencias_packball"] = {
                "aprovada": True,
            }
            resumo = finalizar_acompanhamento_odd(
                [candidato], fontes_saudaveis=False
            )
        self.assertEqual(resumo["bloqueados"], 1)
        self.assertFalse(
            candidato["features"]["acompanhamento_odd"][
                "elegivel_aviso"
            ]
        )

    def test_resultado_hipotetico_fica_separado_e_fecha_no_primeiro_gol(self):
        origem = {
            "mercado": "gol_ft", "linha": "4.5", "odd": 1.36,
            "placar_inicial": "4-0",
        }
        desfecho = avaliar_resultado_acompanhamento_odd(origem, [
            {
                "snapshot_id": 2, "placar": "4-0", "status": "69 '",
                "coletado_em": "2026-08-29T02:27:00",
                "qualidade_apta": True,
            },
            {
                "snapshot_id": 3, "placar": "5-0", "status": "73 '",
                "coletado_em": "2026-08-29T02:31:00",
                "qualidade_apta": True,
            },
        ])
        self.assertEqual(desfecho["resultado"], "green")
        self.assertEqual(desfecho["snapshot_id"], 3)

    def test_red_do_monitoramento_so_fecha_no_fim_do_periodo(self):
        origem = {
            "mercado": "gol_ft", "linha": "4.5", "odd": 1.36,
            "placar_inicial": "4-0",
        }
        andamento = [{
            "snapshot_id": 2, "placar": "4-0", "status": "82 '",
            "coletado_em": "2026-08-29T02:40:00",
            "qualidade_apta": True,
        }]
        self.assertIsNone(
            avaliar_resultado_acompanhamento_odd(origem, andamento)
        )
        andamento.append({
            "snapshot_id": 3, "placar": "4-0", "status": "FT",
            "coletado_em": "2026-08-29T02:52:00",
            "qualidade_apta": True,
        })
        self.assertEqual(
            avaliar_resultado_acompanhamento_odd(
                origem, andamento
            )["resultado"],
            "red",
        )

    @staticmethod
    def odds_api(
        odd=1.40, linha=2.5, idade=0.0,
        coletado_em="2026-09-01T15:02:00",
        recebido_em="2026-09-01T15:02:00", cache=False,
    ):
        return {"ao_vivo": [{
            "categoria": "gols",
            "ofertas": [{
                "linha": linha,
                "over": odd,
                "under": 2.80,
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "idade_segundos": idade,
                "coletado_em": coletado_em,
                "recebido_em": recebido_em,
                "cache": cache,
                "identidade_evento": identidade_evento_teste(),
                "origem_mercado": origem_mercado_teste(linha),
            }],
            "ofertas_ht": [],
        }]}

    @staticmethod
    def acompanhamento_api():
        return {
            "elegivel_aviso": True,
            "conversao_confirmada": True,
            "tendencia_packball_confirmada": True,
            "odd_alvo": 1.40,
            "odd_maxima_operacional": 2.50,
        }

    def test_api_rapida_aprova_mesma_linha_estado_e_odd_alvo(self):
        agora = datetime(2026, 9, 1, 15, 2, 0)
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft",
            linha=2.5,
            placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=self.odds_api(),
            agora=agora,
        )
        self.assertTrue(resultado["aprovada"])
        self.assertEqual(resultado["oferta"]["odd"], 1.40)
        self.assertEqual(resultado["oferta"]["odd_oposta"], 2.80)
        self.assertTrue(resultado["oferta"]["odd_par_sincronizado"])
        self.assertEqual(
            "2026-09-01T15:02:00",
            resultado["oferta"]["recebido_em"],
        )
        self.assertEqual(resultado["contrato_mercado"]["tipo"], "binario")

    def test_api_rapida_recusa_total_sem_lado_oposto(self):
        odds = self.odds_api()
        del odds["ao_vivo"][0]["ofertas"][0]["under"]

        self.assertIsNone(extrair_odd_exata_acompanhamento(
            odds, "gol_ft", 2.5
        ))
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=odds,
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )
        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "linha_exata_indisponivel")

    def test_api_rapida_preserva_tres_vias_do_proximo_gol(self):
        odds = {"ao_vivo": [{
            "categoria": "gols", "escopo": "proximo",
            "fonte": "betsapi", "bookmaker": "bet365",
            "idade_segundos": 0.0,
            "coletado_em": "2026-09-01T15:02:00",
            "cache": False,
            "identidade_evento": identidade_evento_teste("0-0"),
            "origem_mercado": origem_mercado_teste(
                1,
                lados=("casa", "visitante", "sem_gol"),
            ),
            "selecoes": {
                "casa": 1.75, "visitante": 4.20, "sem_gol": 6.50,
            },
        }]}
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="proximo_gol", linha="casa", placar_origem="0-0",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-0", "minuto": 20,
                "status_codigo": "1H",
            },
            odds=odds,
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertTrue(resultado["aprovada"])
        self.assertEqual(resultado["contrato_mercado"]["tipo"], "tres_vias")
        self.assertEqual(resultado["oferta"]["selecao_mercado"], "casa")
        self.assertEqual(
            resultado["oferta"]["odds_mercado_sincronizadas"],
            {"casa": 1.75, "visitante": 4.20, "sem_gol": 6.50},
        )

    def test_api_rapida_extrai_linha_asiatica_de_escanteios_completa(self):
        odds = {"ao_vivo": [{
            "categoria": "escanteios",
            "escopo": "total",
            "tipo_mercado": "asiatico",
            "formato": "duas_opcoes",
            "fonte": "betsapi",
            "bookmaker": "bet365",
            "ofertas": [{
                "linha": 8.5,
                "over": 1.84,
                "under": 2.02,
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T15:02:00",
                "recebido_em": "2026-09-01T15:02:00",
                "cache": False,
                "identidade_evento": identidade_evento_teste("0-0"),
                "origem_mercado": origem_mercado_teste(8.5),
            }],
        }]}

        oferta = extrair_odd_exata_acompanhamento(
            odds, "escanteios_ft_asiatico", 8.5
        )
        contrato = validar_contrato_mercado_oferta(
            oferta,
            "escanteios_ft_asiatico",
            8.5,
            exigir_origem=True,
        )

        self.assertEqual(1.84, oferta["odd"])
        self.assertEqual(2.02, oferta["odd_oposta"])
        self.assertTrue(oferta["odd_par_sincronizado"])
        self.assertTrue(contrato["valido"])
        self.assertEqual("binario", contrato["tipo"])
        self.assertIsNone(extrair_odd_exata_acompanhamento(
            odds, "escanteios_ft_asiatico", 9.5
        ))
        self.assertIsNone(extrair_odd_exata_acompanhamento(
            odds, "proximo_escanteio", None
        ))

    def test_api_rapida_bloqueia_par_sem_prova_do_mesmo_grupo(self):
        odds = self.odds_api()
        del odds["ao_vivo"][0]["ofertas"][0]["origem_mercado"]

        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=odds,
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "origem_mercado_ausente")

    def test_api_rapida_bloqueia_origem_de_outra_casa(self):
        odds = self.odds_api()
        odds["ao_vivo"][0]["ofertas"][0]["origem_mercado"][
            "bookmaker"
        ] = "pinnacle"

        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=odds,
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "origem_mercado_invalida")

    def test_api_rapida_bloqueia_odd_vinculada_a_outro_placar(self):
        odds = self.odds_api()
        odds["ao_vivo"][0]["ofertas"][0]["identidade_evento"] = (
            identidade_evento_teste("1-0")
        )

        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=odds,
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "evento_odd_placar_divergente")

    def test_api_rapida_bloqueia_identidade_de_outras_equipes(self):
        odds = self.odds_api()
        identidade = odds["ao_vivo"][0]["ofertas"][0][
            "identidade_evento"
        ]
        identidade["mandante_normalizado"] = "Equipe Estranha"
        identidade["visitante_normalizado"] = "Outro Clube"

        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
                "mandante": "Casa", "visitante": "Fora",
            },
            odds=odds,
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "evento_odd_equipes_divergentes")

    def test_api_rapida_aceita_cache_curto_com_relogios_coerentes(self):
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=self.odds_api(
                idade=10.0,
                coletado_em="2026-09-01T15:01:50",
                cache=True,
            ),
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertTrue(resultado["aprovada"])
        self.assertEqual(
            resultado["proveniencia_temporal"][
                "divergencia_relogio_segundos"
            ],
            0.0,
        )

    def test_api_rapida_bloqueia_idade_falsa_ainda_dentro_do_ttl(self):
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=self.odds_api(
                idade=0.0,
                coletado_em="2026-09-01T15:01:40",
            ),
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "odd_relogio_inconsistente")

    def test_api_rapida_bloqueia_carimbo_futuro_ou_cache_indeterminado(self):
        futuro = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=self.odds_api(
                coletado_em="2026-09-01T15:02:10",
            ),
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )
        sem_cache = self.odds_api()
        del sem_cache["ao_vivo"][0]["ofertas"][0]["cache"]
        indeterminado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=sem_cache,
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertEqual(
            futuro["motivo"], "odd_proveniencia_temporal_indeterminada"
        )
        self.assertEqual(
            indeterminado["motivo"],
            "odd_proveniencia_temporal_indeterminada",
        )

    def test_api_rapida_bloqueia_idade_nao_finita(self):
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=self.odds_api(idade="nan"),
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )

        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "odd_sem_frescor_comprovado")

    def test_api_rapida_continua_esperando_abaixo_do_alvo(self):
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=self.odds_api(odd=1.39),
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )
        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "odd_ainda_abaixo_do_alvo")

    def test_api_rapida_mantem_leitura_por_quinze_minutos(self):
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "0-2", "minuto": 57,
                "status_codigo": "2H",
            },
            odds=self.odds_api(
                odd=1.40, coletado_em="2026-09-01T15:14:59"
            ),
            agora=datetime(2026, 9, 1, 15, 14, 59),
            ttl_tecnico_segundos=900,
        )

        self.assertTrue(resultado["aprovada"])
        self.assertEqual(resultado["idade_tecnica_segundos"], 899.0)

    def test_api_rapida_bloqueia_gol_antes_do_envio(self):
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T15:00:00",
            jogo_atual={
                "placar": "1-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=self.odds_api(),
            agora=datetime(2026, 9, 1, 15, 2, 0),
        )
        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "placar_alterado")

    def test_api_rapida_nao_substitui_linha_nem_usa_leitura_velha(self):
        self.assertIsNone(extrair_odd_exata_acompanhamento(
            self.odds_api(linha=3.5), "gol_ft", 2.5
        ))
        resultado = avaliar_rechecagem_odd_api(
            self.acompanhamento_api(),
            mercado="gol_ft", linha=2.5, placar_origem="0-2",
            snapshot_em="2026-09-01T14:55:00",
            jogo_atual={
                "placar": "0-2", "minuto": 48,
                "status_codigo": "2H",
            },
            odds=self.odds_api(),
            agora=datetime(2026, 9, 1, 15, 2, 0),
            ttl_tecnico_segundos=240,
        )
        self.assertFalse(resultado["aprovada"])
        self.assertEqual(resultado["motivo"], "leitura_tecnica_expirada")


if __name__ == "__main__":
    unittest.main()
