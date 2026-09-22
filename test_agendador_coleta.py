import unittest

from agendador_coleta import AgendadorColeta


class RelogioFalso:
    def __init__(self):
        self.agora = 0

    def __call__(self):
        return self.agora


class AgendadorColetaTest(unittest.TestCase):
    def setUp(self):
        self.relogio = RelogioFalso()
        self.agendador = AgendadorColeta(
            intervalo_rapido=60,
            intervalo_lento=180,
            odds_rapidas=120,
            odds_lentas=300,
            relogio=self.relogio,
        )
        self.jogos = [
            {"url": "frio", "mandante": "A"},
            {"url": "quente", "mandante": "B"},
        ]

    def test_novos_jogos_entram_completos_e_quente_primeiro(self):
        tarefas = self.agendador.planejar(
            self.jogos, {"frio": 20, "quente": 80}
        )
        self.assertEqual(tarefas[0]["jogo"]["url"], "quente")
        self.assertTrue(all(item["coletar_odds"] for item in tarefas))

    def test_padrao_de_producao_respeita_teto_conservador(self):
        padrao = AgendadorColeta(relogio=self.relogio)
        self.assertEqual(padrao.intervalo_rapido, 240)
        self.assertEqual(padrao.intervalo_lento, 360)
        self.assertEqual(padrao.odds_rapidas, 600)
        self.assertEqual(padrao.odds_lentas, 900)
        self.assertEqual(padrao.intervalo_rechecagem_evento, 120)

    def test_pos_gol_reconsulta_rapido_com_odds_sem_aumentar_fila(self):
        agendador = AgendadorColeta(
            intervalo_rapido=240,
            intervalo_lento=360,
            odds_rapidas=600,
            odds_lentas=900,
            intervalo_rechecagem_evento=120,
            relogio=self.relogio,
        )
        iniciais = agendador.planejar(self.jogos, {})
        for tarefa in iniciais:
            agendador.concluir(tarefa)

        self.relogio.agora = 121
        normais = agendador.planejar(self.jogos, {"quente": 55})
        urgentes = agendador.planejar(
            self.jogos,
            {"quente": 55},
            rechecagens_pos_evento={"quente"},
        )

        self.assertEqual(normais, [])
        self.assertEqual(len(urgentes), 1)
        self.assertEqual(urgentes[0]["jogo"]["url"], "quente")
        self.assertTrue(urgentes[0]["em_foco"])
        self.assertTrue(urgentes[0]["rechecagem_pos_evento"])
        self.assertTrue(urgentes[0]["coletar_odds"])

    def test_acompanhamento_preco_forca_uma_cotacao_apos_dois_minutos(self):
        inicial = self.agendador.planejar([self.jogos[0]], {})[0]
        self.agendador.concluir(inicial)

        self.relogio.agora = 121
        tarefas = self.agendador.planejar(
            [self.jogos[0]],
            {},
            acompanhamentos_preco={"frio": 121},
        )

        self.assertEqual(1, len(tarefas))
        self.assertTrue(tarefas[0]["acompanhamento_preco"])
        self.assertTrue(tarefas[0]["coletar_odds"])
        self.assertTrue(tarefas[0]["em_foco"])
        self.assertTrue(tarefas[0]["somente_acompanhamento_preco"])
        self.agendador.concluir(tarefas[0])

        self.relogio.agora = 181
        repeticao = self.agendador.planejar(
            [self.jogos[0]],
            {},
            acompanhamentos_preco={"frio": 181},
        )
        self.assertEqual([], repeticao)

    def test_acompanhamento_preco_nao_roda_antes_de_dois_ou_depois_de_dez(self):
        inicial = self.agendador.planejar([self.jogos[0]], {})[0]
        self.agendador.concluir(inicial)

        self.relogio.agora = 60
        self.assertEqual([], self.agendador.planejar(
            [self.jogos[0]], {}, acompanhamentos_preco={"frio": 60}
        ))
        self.relogio.agora = 601
        tarefas = self.agendador.planejar(
            [self.jogos[0]], {}, acompanhamentos_preco={"frio": 601}
        )
        self.assertTrue(tarefas)
        self.assertFalse(tarefas[0]["acompanhamento_preco"])

    def test_fila_rapida_volta_antes_da_lenta(self):
        tarefas = self.agendador.planejar(
            self.jogos, {"frio": 20, "quente": 80}
        )
        for tarefa in tarefas:
            self.agendador.concluir(tarefa)
        self.relogio.agora = 61
        novas = self.agendador.planejar(
            self.jogos, {"frio": 20, "quente": 80}
        )
        self.assertEqual([item["jogo"]["url"] for item in novas], ["quente"])
        self.assertFalse(novas[0]["coletar_odds"])

    def test_fila_lenta_nunca_e_abandonada(self):
        tarefas = self.agendador.planejar(self.jogos, {})
        for tarefa in tarefas:
            self.agendador.concluir(tarefa)
        self.relogio.agora = 181
        novas = self.agendador.planejar(self.jogos, {})
        self.assertEqual(len(novas), 2)

    def test_falha_de_odds_nao_adia_nova_tentativa(self):
        tarefas = self.agendador.planejar([self.jogos[0]], {})
        self.agendador.concluir(tarefas[0], odds_coletadas=False)

        self.relogio.agora = 181
        novas = self.agendador.planejar([self.jogos[0]], {})

        self.assertEqual(len(novas), 1)
        self.assertTrue(novas[0]["coletar_odds"])

    def test_jogo_de_foco_supera_lento_muito_atrasado(self):
        tarefas = self.agendador.planejar(
            self.jogos, {"frio": 20, "quente": 80}
        )
        for tarefa in tarefas:
            self.agendador.concluir(tarefa)
        self.relogio.agora = 61
        rapido = self.agendador.planejar(
            self.jogos, {"frio": 20, "quente": 80}
        )[0]
        self.agendador.concluir(rapido)
        self.relogio.agora = 121
        rapido = self.agendador.planejar(
            self.jogos, {"frio": 20, "quente": 80}
        )[0]
        self.agendador.concluir(rapido)

        self.relogio.agora = 181
        novas = self.agendador.planejar(
            self.jogos, {"frio": 20, "quente": 80}
        )

        self.assertEqual(novas[0]["jogo"]["url"], "quente")
        self.assertTrue(novas[0]["em_foco"])

    def test_foco_tem_prioridade_sobre_jogo_nunca_processado(self):
        inicial = self.agendador.planejar(
            [self.jogos[1]], {"quente": 80}
        )[0]
        self.agendador.concluir(inicial)
        self.relogio.agora = 61

        tarefas = self.agendador.planejar(
            self.jogos, {"frio": 20, "quente": 80}
        )

        self.assertEqual(tarefas[0]["jogo"]["url"], "quente")
        self.assertTrue(tarefas[0]["em_foco"])

    def test_limita_foco_a_tres_melhores_jogos(self):
        jogos = [
            {"url": f"jogo-{indice}", "mandante": str(indice)}
            for indice in range(5)
        ]
        pontuacoes = {
            jogo["url"]: 90 - indice
            for indice, jogo in enumerate(jogos)
        }

        tarefas = self.agendador.planejar(jogos, pontuacoes)

        self.assertEqual(
            [item["jogo"]["url"] for item in tarefas[:3]],
            ["jogo-0", "jogo-1", "jogo-2"],
        )
        self.assertTrue(all(item["em_foco"] for item in tarefas[:3]))
        self.assertFalse(any(item["em_foco"] for item in tarefas[3:]))

    def test_sem_candidato_quente_novos_continuam_prioritarios(self):
        inicial = self.agendador.planejar([self.jogos[1]], {})[0]
        self.agendador.concluir(inicial)
        self.relogio.agora = 181

        tarefas = self.agendador.planejar(self.jogos, {})

        self.assertEqual(tarefas[0]["jogo"]["url"], "frio")
        self.assertIsNone(tarefas[0]["idade_segundos"])

    def test_scanner_prioriza_mas_reserva_controle_ao_vivo(self):
        jogos = [
            {"url": f"scanner-{indice}", "scanner_prioritario": True}
            for indice in range(5)
        ] + [{"url": "controle", "scanner_prioritario": False}]

        tarefas = self.agendador.planejar(jogos, {})
        primeiras = tarefas[:4]

        self.assertEqual(primeiras[0]["jogo"]["url"], "scanner-0")
        self.assertEqual(primeiras[-1]["jogo"]["url"], "controle")
        self.assertEqual(
            sum(item["scanner_prioritario"] for item in primeiras), 3
        )

    def test_pre_live_confirmado_fica_antes_do_scanner_sem_superar_foco(self):
        jogos = [
            {"url": "foco"},
            {"url": "scanner", "scanner_prioritario": True},
            {
                "url": "pre-live",
                "pre_live_prioritario": True,
                "pre_live_confirmado": True,
            },
        ]

        tarefas = self.agendador.planejar(jogos, {"foco": 90})

        self.assertEqual(
            [item["jogo"]["url"] for item in tarefas],
            ["foco", "pre-live", "scanner"],
        )
        self.assertEqual(tarefas[1]["prioridade"], "rapida")

    def test_pre_live_publicado_tem_vaga_sem_tomar_toda_fila_scanner(self):
        agendador = AgendadorColeta(
            maximo_foco=3,
            relogio=self.relogio,
        )
        jogos = [
            {"url": f"scanner-{indice}", "scanner_prioritario": True}
            for indice in range(6)
        ] + [{"url": "pre-live", "pre_live_prioritario": True}]

        tarefas = agendador.planejar(jogos, {})
        primeiras = tarefas[:4]

        self.assertTrue(any(
            item["jogo"]["url"] == "pre-live" for item in primeiras
        ))
        self.assertGreaterEqual(sum(
            item["scanner_prioritario"] for item in primeiras
        ), 3)

    def test_colunas_priorizam_radar_mais_forte_quando_ativadas(self):
        agendador = AgendadorColeta(
            relogio=self.relogio, usar_indicadores_lista=True
        )
        fraco = {
            "url": "fraco",
            "indicadores_lista": {"campos": {
                "indice_de_pressao_ult_5_minutos": {
                    "casa": 20, "visitante": 15,
                },
            }},
        }
        forte = {
            "url": "forte",
            "indicadores_lista": {"campos": {
                "indice_de_pressao_ult_5_minutos": {
                    "casa": 75, "visitante": 30,
                },
                "chutes_no_gol_ult_5_minutos": {
                    "casa": 2, "visitante": 0,
                },
            }},
        }

        tarefas = agendador.planejar([fraco, forte], {})

        self.assertEqual(tarefas[0]["jogo"]["url"], "forte")
        self.assertGreater(
            tarefas[0]["pontuacao_indicadores_lista"],
            tarefas[1]["pontuacao_indicadores_lista"],
        )

    def test_colunas_desativadas_preservam_prioridade_anterior(self):
        jogos = [
            {"url": "primeiro", "indicadores_lista": {"campos": {}}},
            {"url": "segundo", "indicadores_lista": {"campos": {
                "indice_de_pressao_ult_5_minutos": {
                    "casa": 100, "visitante": 100,
                },
            }}},
        ]

        tarefas = self.agendador.planejar(jogos, {})

        self.assertEqual(tarefas[0]["jogo"]["url"], "primeiro")
        self.assertTrue(all(
            tarefa["pontuacao_indicadores_lista"] == 0
            for tarefa in tarefas
        ))


    def test_reserva_um_ciclo_em_tres_para_exploracao(self):
        quente = self.jogos[1]
        frio = self.jogos[0]
        primeira = self.agendador.planejar(
            [frio, quente], {"quente": 80}
        )
        segunda = self.agendador.planejar(
            [frio, quente], {"quente": 80}
        )
        terceira = self.agendador.planejar(
            [frio, quente], {"quente": 80}
        )

        self.assertEqual(primeira[0]["jogo"]["url"], "quente")
        self.assertEqual(segunda[0]["jogo"]["url"], "quente")
        self.assertEqual(terceira[0]["jogo"]["url"], "frio")
        self.assertFalse(terceira[0]["em_foco"])

    def test_sem_disputa_nao_avanca_cota_de_exploracao(self):
        self.agendador.planejar([self.jogos[0]], {})
        self.agendador.planejar([self.jogos[0]], {})

        tarefas = self.agendador.planejar(
            self.jogos, {"quente": 80}
        )

        self.assertEqual(tarefas[0]["jogo"]["url"], "quente")

    def test_restaura_idades_sem_tratar_todos_como_novos(self):
        self.relogio.agora = 1000

        restaurado = self.agendador.restaurar({
            "frio": {"idade_coleta": 30, "idade_odds": 200},
        })

        self.assertEqual(restaurado["coletas_restauradas"], 1)
        self.assertEqual(restaurado["odds_restauradas"], 1)
        self.assertEqual(self.agendador.planejar([self.jogos[0]], {}), [])
        novas = self.agendador.planejar([self.jogos[1]], {})
        self.assertEqual(len(novas), 1)
        self.assertIsNone(novas[0]["idade_segundos"])

        self.relogio.agora = 1151
        vencida = self.agendador.planejar([self.jogos[0]], {})[0]
        self.assertTrue(vencida["coletar_odds"])

    def test_restauracao_nao_sobrescreve_relogio_ja_ativo(self):
        self.relogio.agora = 100
        tarefa = self.agendador.planejar([self.jogos[0]], {})[0]
        self.agendador.concluir(tarefa)
        self.relogio.agora = 120

        resultado = self.agendador.restaurar({
            "frio": {"idade_coleta": 999, "idade_odds": 999},
        })

        self.assertEqual(resultado["coletas_restauradas"], 0)
        self.assertEqual(resultado["odds_restauradas"], 0)
        self.assertEqual(self.agendador.planejar([self.jogos[0]], {}), [])


if __name__ == "__main__":
    unittest.main()
