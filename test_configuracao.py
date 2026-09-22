import unittest

from configuracao import odd_elegivel, obter_limites_risco, validar_configuracao


BASE = {
    "PACKBALL_EMAIL": "usuario@example.com",
    "PACKBALL_PASSWORD": "segredo",
    "API_FOOTBALL_KEY": "api",
    "TELEGRAM_BOT_TOKEN": "token",
    "TELEGRAM_CHAT_ID_GOLS": "1",
    "TELEGRAM_CHAT_ID_ESCANTEIOS": "2",
    "TELEGRAM_ADMIN_ID": "3",
}


class ConfiguracaoTest(unittest.TestCase):
    def test_amostragem_referencia_odds_exige_fonte_e_limites_validos(self):
        ativa = validar_configuracao({
            **BASE,
            "THE_ODDS_API_KEY": "chave-odds",
            "THE_ODDS_API_ATIVA": "1",
            "THE_ODDS_API_LIMITE_DIARIO": "100",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_LIMITE_DIARIO": "30",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_INTERVALO_SEGUNDOS": "600",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_MAX_CICLO": "2",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_MAX_JOGO_DIA": "2",
        })
        sem_fonte = validar_configuracao({
            **BASE,
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA": "1",
        })
        acima_do_total = validar_configuracao({
            **BASE,
            "THE_ODDS_API_KEY": "chave-odds",
            "THE_ODDS_API_ATIVA": "1",
            "THE_ODDS_API_LIMITE_DIARIO": "10",
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_LIMITE_DIARIO": "30",
        })

        amostragem = ativa["the_odds_api"]["amostragem_referencia"]
        self.assertTrue(ativa["valida"])
        self.assertTrue(amostragem["ativa"])
        self.assertEqual(30, amostragem["limite_diario"])
        self.assertEqual(600, amostragem["intervalo_segundos"])
        self.assertEqual(2, amostragem["maximo_ciclo"])
        self.assertEqual(2, amostragem["maximo_por_jogo_dia"])
        self.assertFalse(amostragem["aplicacao_sinais"])
        self.assertFalse(amostragem["telegram"])
        self.assertFalse(sem_fonte["valida"])
        self.assertFalse(acima_do_total["valida"])

    def test_proximo_gol_balanceado_tem_geracao_e_grupo_auditaveis(self):
        ativo = validar_configuracao({
            **BASE,
            "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO": "1",
            "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO": "1",
            "PONTUACAO_MINIMA_PROXIMO_GOL_BALANCEADO_TESTE": "60",
        })
        sem_gerador = validar_configuracao({
            **BASE,
            "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO": "0",
            "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO": "1",
        })
        flag_invalida = validar_configuracao({
            **BASE,
            "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO": "talvez",
            "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO": "0",
        })

        self.assertTrue(ativo["valida"])
        self.assertTrue(
            ativo["recursos"]["proximo_gol_balanceado_sombra"]
        )
        self.assertTrue(
            ativo["recursos"]["proximo_gol_balanceado_grupo_teste"]
        )
        self.assertEqual(
            60.0,
            ativo["recursos"][
                "pontuacao_minima_proximo_gol_balanceado_teste"
            ],
        )
        self.assertFalse(sem_gerador["valida"])
        self.assertIn(
            "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO exige "
            "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO=1",
            sem_gerador["erros"],
        )
        self.assertFalse(flag_invalida["valida"])

    def test_proximo_gol_balanceado_rejeita_nota_fora_da_faixa(self):
        resultado = validar_configuracao({
            **BASE,
            "PONTUACAO_MINIMA_PROXIMO_GOL_BALANCEADO_TESTE": "101",
        })

        self.assertFalse(resultado["valida"])
        self.assertIn(
            "PONTUACAO_MINIMA_PROXIMO_GOL_BALANCEADO_TESTE deve ficar "
            "entre 0 e 100",
            resultado["erros"],
        )

    def test_acompanhamento_preco_pos_alerta_tem_rollback_binario(self):
        ativo = validar_configuracao({
            **BASE, "ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO": "1",
        })
        desligado = validar_configuracao({
            **BASE, "ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO": "0",
        })
        invalido = validar_configuracao({
            **BASE, "ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO": "talvez",
        })

        self.assertTrue(
            ativo["recursos"]["acompanhamento_preco_pos_alerta"]
        )
        self.assertFalse(
            desligado["recursos"]["acompanhamento_preco_pos_alerta"]
        )
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO deve ser 0 ou 1",
            invalido["erros"],
        )

    def test_preferencia_avisos_odd_silenciosa_e_binaria(self):
        silenciosa = validar_configuracao({
            **BASE, "ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS": "0",
        })
        self.assertTrue(silenciosa["valida"])
        self.assertFalse(silenciosa["telegram"]["acompanhamento_odd_avisos"])
        invalida = validar_configuracao({
            **BASE, "ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS": "talvez",
        })
        self.assertFalse(invalida["valida"])

    def test_carteira_acompanhamento_odd_valida_mercados(self):
        somente_ft = validar_configuracao({
            **BASE, "AVISO_AGUARDAR_ODD_MERCADOS": "gol_ft",
        })
        self.assertTrue(somente_ft["valida"])
        self.assertEqual(
            somente_ft["recursos"]["acompanhamento_odd_mercados"],
            ["gol_ft"],
        )
        invalida = validar_configuracao({
            **BASE, "AVISO_AGUARDAR_ODD_MERCADOS": "escanteios",
        })
        self.assertFalse(invalida["valida"])
        self.assertIn(
            "AVISO_AGUARDAR_ODD_MERCADOS contém mercado inválido: escanteios",
            invalida["erros"],
        )

    def test_configuracao_valida_nao_expoe_segredos(self):
        resultado = validar_configuracao(BASE)
        self.assertTrue(resultado["valida"])
        self.assertNotIn("segredo", str(resultado))
        self.assertTrue(resultado["recursos"]["telegram_gols"])
        self.assertEqual(resultado["api"]["limite_diario"], 7500)
        self.assertEqual(resultado["api"]["limite_diario_seguro"], 7000)
        self.assertEqual(resultado["api"]["stats_resgate_max_ciclo"], 2)
        self.assertFalse(
            resultado["recursos"]["escanteios_asiaticos_periodos"]
        )
        self.assertFalse(
            resultado["telegram"]["alertas_tecnicos_ativos"]
        )
        self.assertFalse(
            resultado["telegram"]["alertas_operacionais_nos_grupos"]
        )
        self.assertEqual(
            resultado["telegram"]["resumo_diario_desejado"],
            "compacto-v1",
        )

    def test_alertas_tecnicos_telegram_exigem_flag_binaria(self):
        ativo = validar_configuracao({
            **BASE, "TELEGRAM_ALERTAS_TECNICOS": "1",
        })
        invalido = validar_configuracao({
            **BASE, "TELEGRAM_ALERTAS_TECNICOS": "talvez",
        })

        self.assertTrue(ativo["telegram"]["alertas_tecnicos_ativos"])
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "TELEGRAM_ALERTAS_TECNICOS deve ser 0 ou 1",
            invalido["erros"],
        )

    def test_alertas_operacionais_nos_grupos_exigem_opt_in_binario(self):
        ativo = validar_configuracao({
            **BASE, "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS": "1",
        })
        invalido = validar_configuracao({
            **BASE,
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS": "talvez",
        })

        self.assertTrue(
            ativo["telegram"]["alertas_operacionais_nos_grupos"]
        )
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS deve ser 0 ou 1",
            invalido["erros"],
        )

    def test_periodos_asiaticos_exigem_reativacao_explicita(self):
        ativo = validar_configuracao({
            **BASE,
            "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS": "1",
        })
        invalido = validar_configuracao({
            **BASE,
            "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS": "talvez",
        })

        self.assertTrue(
            ativo["recursos"]["escanteios_asiaticos_periodos"]
        )
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS deve ser 0 ou 1",
            invalido["erros"],
        )

    def test_prioridade_cantos_por_canal_tem_rollback_validado(self):
        ativo = validar_configuracao({
            **BASE, "ESCANTEIOS_PRIORIDADE_CANAL_ATIVA": "1",
        })
        desligado = validar_configuracao({
            **BASE, "ESCANTEIOS_PRIORIDADE_CANAL_ATIVA": "0",
        })
        invalido = validar_configuracao({
            **BASE, "ESCANTEIOS_PRIORIDADE_CANAL_ATIVA": "talvez",
        })

        self.assertTrue(
            ativo["recursos"]["escanteios_prioridade_canal"]
        )
        self.assertFalse(
            desligado["recursos"]["escanteios_prioridade_canal"]
        )
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "ESCANTEIOS_PRIORIDADE_CANAL_ATIVA deve ser 0 ou 1",
            invalido["erros"],
        )

    def test_fallback_temporal_da_lista_tem_rollback_validado(self):
        ativo = validar_configuracao({
            **BASE,
            "INDICADORES_LISTA_TEMPORAIS_APLICACAO_SINAIS": "1",
        })
        desligado = validar_configuracao({
            **BASE,
            "INDICADORES_LISTA_TEMPORAIS_APLICACAO_SINAIS": "0",
        })
        invalido = validar_configuracao({
            **BASE,
            "INDICADORES_LISTA_TEMPORAIS_APLICACAO_SINAIS": "talvez",
        })

        self.assertTrue(
            ativo["recursos"]["indicadores_lista_temporais_condicionais"]
        )
        self.assertFalse(
            desligado["recursos"]["indicadores_lista_temporais_condicionais"]
        )
        self.assertFalse(invalido["valida"])

    def test_ht_capacidade_v1_negativo_exige_reativacao_explicita(self):
        padrao = validar_configuracao(BASE)
        ativo = validar_configuracao({
            **BASE,
            "GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO": "1",
        })
        invalido = validar_configuracao({
            **BASE,
            "GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO": "talvez",
        })

        self.assertFalse(
            padrao["recursos"]["gol_ht_capacidade_v1_grupo"]
        )
        self.assertTrue(
            ativo["recursos"]["gol_ht_capacidade_v1_grupo"]
        )
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO deve ser 0 ou 1",
            invalido["erros"],
        )

    def test_ft_capacidade_v1_negativo_exige_reativacao_explicita(self):
        padrao = validar_configuracao(BASE)
        ativo = validar_configuracao({
            **BASE,
            "GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO": "1",
        })
        invalido = validar_configuracao({
            **BASE,
            "GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO": "talvez",
        })

        self.assertFalse(
            padrao["recursos"]["gol_ft_capacidade_v1_grupo"]
        )
        self.assertTrue(
            ativo["recursos"]["gol_ft_capacidade_v1_grupo"]
        )
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO deve ser 0 ou 1",
            invalido["erros"],
        )

    def test_portfolio_gols_expoe_flags_reversiveis(self):
        ativo = validar_configuracao({
            **BASE,
            "GOL_HT_00_MIN20_GRUPO_ATIVO": "1",
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_HT_GRUPO_ATIVO": "1",
            "TOP_CRITERIOS_GOLS_GRUPO_ATIVO": "1",
            "FILTRO_GOL_HT_ANTECIPADO_PRECISO_ATIVO": "1",
            "FILTRO_GOL_FT_ANTECIPADO_PRECISO_ATIVO": "1",
        })
        desligado = validar_configuracao({
            **BASE,
            "GOL_HT_00_MIN20_GRUPO_ATIVO": "0",
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_HT_GRUPO_ATIVO": "0",
            "TOP_CRITERIOS_GOLS_GRUPO_ATIVO": "0",
            "FILTRO_GOL_HT_ANTECIPADO_PRECISO_ATIVO": "0",
            "FILTRO_GOL_FT_ANTECIPADO_PRECISO_ATIVO": "0",
        })
        invalido = validar_configuracao({
            **BASE,
            "GOL_HT_00_MIN20_GRUPO_ATIVO": "talvez",
        })

        self.assertTrue(ativo["recursos"]["gol_ht_00_min20_grupo"])
        self.assertTrue(
            ativo["recursos"]["gol_ht_capacidade_contextual_v2_grupo"]
        )
        self.assertTrue(ativo["recursos"]["top_criterios_gols_grupo"])
        self.assertTrue(
            ativo["recursos"]["filtro_gol_ht_antecipado_preciso"]
        )
        self.assertTrue(
            ativo["recursos"]["filtro_gol_ft_antecipado_preciso"]
        )
        self.assertFalse(
            desligado["recursos"]["gol_ht_00_min20_grupo"]
        )
        self.assertFalse(
            desligado["recursos"][
                "gol_ht_capacidade_contextual_v2_grupo"
            ]
        )
        self.assertFalse(
            desligado["recursos"]["top_criterios_gols_grupo"]
        )
        self.assertFalse(
            desligado["recursos"]["filtro_gol_ht_antecipado_preciso"]
        )
        self.assertFalse(
            desligado["recursos"]["filtro_gol_ft_antecipado_preciso"]
        )
        self.assertFalse(invalido["valida"])

    def test_ft_contextual_v2_expoe_flag_validada(self):
        ativo = validar_configuracao({
            **BASE,
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO": "1",
        })
        desligado = validar_configuracao({
            **BASE,
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO": "0",
        })
        invalido = validar_configuracao({
            **BASE,
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO": "talvez",
        })

        self.assertTrue(
            ativo["recursos"]["gol_ft_capacidade_contextual_v2_grupo"]
        )
        self.assertFalse(
            desligado["recursos"]["gol_ft_capacidade_contextual_v2_grupo"]
        )
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO deve ser 0 ou 1",
            invalido["erros"],
        )

    def test_pontuacao_proximo_gol_isolada_precisa_ser_percentual(self):
        valido = validar_configuracao({
            **BASE,
            "PONTUACAO_MINIMA_SINAL_TESTE": "75",
            "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE": "70",
        })
        invalido = validar_configuracao({
            **BASE,
            "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE": "101",
        })

        self.assertTrue(valido["valida"])
        self.assertFalse(invalido["valida"])
        self.assertIn(
            "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE deve ficar entre 0 e 100",
            invalido["erros"],
        )

    def test_bloqueia_odds_invertidas_e_numero_invalido(self):
        env = {
            **BASE,
            "ODD_MINIMA_SINAL": "3",
            "ODD_MAXIMA_SINAL": "2",
            "LIMITE_DIARIO_SINAIS": "muitos",
        }
        resultado = validar_configuracao(env)
        self.assertFalse(resultado["valida"])
        self.assertGreaterEqual(len(resultado["erros"]), 2)
        with self.assertRaises(ValueError):
            obter_limites_risco(env)

    def test_recursos_opcionais_ausentes_geram_avisos(self):
        resultado = validar_configuracao(
            {
                "PACKBALL_EMAIL": "a",
                "PACKBALL_PASSWORD": "b",
            }
        )
        self.assertTrue(resultado["valida"])
        self.assertFalse(resultado["recursos"]["api_football"])
        self.assertGreaterEqual(len(resultado["avisos"]), 3)

    def test_credenciais_packball_sao_obrigatorias(self):
        resultado = validar_configuracao({})
        self.assertFalse(resultado["valida"])
        self.assertIn("PACKBALL_EMAIL não configurado", resultado["erros"])

    def test_bloqueia_reserva_api_maior_que_franquia(self):
        resultado = validar_configuracao(
            {
                **BASE,
                "API_LIMITE_DIARIO": "7500",
                "API_RESERVA_DIARIA": "7500",
            }
        )
        self.assertFalse(resultado["valida"])
        self.assertIn(
            "API_RESERVA_DIARIA deve ser menor que API_LIMITE_DIARIO",
            resultado["erros"],
        )

    def test_limite_global_de_teste_nao_pode_ser_menor_que_o_da_regra(self):
        resultado = validar_configuracao({
            **BASE,
            "LIMITE_DIARIO_SINAIS_TESTE": "30",
            "LIMITE_GLOBAL_SINAIS_TESTE": "20",
        })
        self.assertFalse(resultado["valida"])
        self.assertIn(
            "LIMITE_GLOBAL_SINAIS_TESTE não pode ser menor que "
            "LIMITE_DIARIO_SINAIS_TESTE",
            resultado["erros"],
        )

    def test_odd_elegivel_usa_exatamente_a_faixa_operacional(self):
        limites = obter_limites_risco(BASE)
        self.assertTrue(odd_elegivel(1.4, limites))
        self.assertTrue(odd_elegivel("2.5", limites))
        self.assertFalse(odd_elegivel(1.39, limites))
        self.assertFalse(odd_elegivel(2.51, limites))
        self.assertFalse(odd_elegivel(None, limites))

    def test_valida_limites_do_circuit_breaker_oficial(self):
        resultado = validar_configuracao({
            **BASE,
            "LIMITE_REDS_CONSECUTIVOS_OFICIAIS": "0",
            "LIMITE_PERDA_DIARIA_OFICIAL": "invalido",
        })
        self.assertFalse(resultado["valida"])
        self.assertTrue(any(
            "LIMITE_REDS_CONSECUTIVOS_OFICIAIS" in erro
            for erro in resultado["erros"]
        ))
        self.assertTrue(any(
            "LIMITE_PERDA_DIARIA_OFICIAL" in erro
            for erro in resultado["erros"]
        ))

    def test_limite_stats_resgate_api_e_restrito_e_reversivel(self):
        desligado = validar_configuracao({
            **BASE, "API_STATS_RESGATE_MAX_CICLO": "0",
        })
        invalido = validar_configuracao({
            **BASE, "API_STATS_RESGATE_MAX_CICLO": "6",
        })

        self.assertTrue(desligado["valida"])
        self.assertEqual(
            desligado["api"]["stats_resgate_max_ciclo"], 0
        )
        self.assertFalse(invalido["valida"])
        self.assertTrue(any(
            "API_STATS_RESGATE_MAX_CICLO" in erro
            for erro in invalido["erros"]
        ))

    def test_betsapi_oficial_e_validada_sem_expor_token(self):
        resultado = validar_configuracao({
            **BASE,
            "BETSAPI_TOKEN": "token-secreto-betsapi",
            "BETSAPI_ATIVA": "1",
            "BETSAPI_APLICACAO_SINAIS_ATIVA": "1",
            "BETSAPI_LIMITE_HORA": "3000",
            "BETSAPI_LIMITE_DIARIO": "50000",
        })

        self.assertTrue(resultado["valida"])
        self.assertTrue(resultado["betsapi"]["ativa"])
        self.assertTrue(resultado["betsapi"]["aplicacao_sinais"])
        self.assertTrue(resultado["recursos"]["betsapi"])
        self.assertNotIn("token-secreto-betsapi", str(resultado))

    def test_betsapi_oficial_exige_chave_e_flag_ativa(self):
        resultado = validar_configuracao({
            **BASE,
            "BETSAPI_ATIVA": "0",
            "BETSAPI_APLICACAO_SINAIS_ATIVA": "1",
        })

        self.assertFalse(resultado["valida"])
        self.assertIn(
            "BetsAPI oficial exige chave e BETSAPI_ATIVA=1",
            resultado["erros"],
        )


if __name__ == "__main__":
    unittest.main()
