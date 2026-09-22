import unittest

from controle_acesso_packball import PackBallBloqueadoError
from coletor_packball import (
    ColetorPackBall,
    PackBallListaNaoValidadaError,
    SCRIPT_DIAGNOSTICO_LISTA,
    SCRIPT_DIAGNOSTICO_SCANNER,
    SCRIPT_DIAGNOSTICO_STATUS_LISTA,
    SCRIPT_ESTADO_PARTIDA,
    SCRIPT_ESTATISTICAS,
    SCRIPT_JOGOS_AO_VIVO,
)


class BotaoAoVivoFalso:
    def __init__(
        self, texto="2", visivel=True, quantidade=1, falhas_click=0
    ):
        self.texto = texto
        self.visivel = visivel
        self.quantidade = quantidade
        self.clicado = False
        self.falhas_click = falhas_click

    def count(self):
        return self.quantidade

    def inner_text(self):
        return self.texto

    def is_visible(self):
        return self.visivel

    def click(self, timeout=None):
        if self.falhas_click:
            self.falhas_click -= 1
            raise TimeoutError("element is not visible")
        self.clicado = True


class PaginaPackBallFalsa:
    def __init__(
        self, botao=None, retorno=None, login_visivel=False,
        diagnostico=None, diagnostico_status=None,
    ):
        self.botao = botao or BotaoAoVivoFalso()
        self.retorno = retorno if retorno is not None else []
        self.url = None
        self.login_visivel = login_visivel
        self.diagnostico = diagnostico or {}
        self.diagnostico_status = diagnostico_status
        self.navegacoes = 0
        self.esperas_dinamicas = []

    def goto(self, url, **kwargs):
        self.url = url
        self.navegacoes += 1

    def wait_for_timeout(self, milissegundos):
        return None

    def wait_for_function(self, script, timeout=None):
        self.esperas_dinamicas.append((script, timeout))
        return True

    def locator(self, seletor):
        if seletor == 'input[name="email"]':
            return BotaoAoVivoFalso(
                quantidade=1 if self.login_visivel else 0,
                visivel=self.login_visivel,
            )
        return self.botao

    def evaluate(self, script, *args):
        if script == SCRIPT_DIAGNOSTICO_LISTA:
            return self.diagnostico
        if script == SCRIPT_DIAGNOSTICO_STATUS_LISTA:
            return self.diagnostico_status or {
                "excluidos": [], "interrompidos_total": 0,
            }
        return self.retorno


class PaginaVirtualizadaFalsa:
    def __init__(self):
        self.indice = 0
        self.lotes = [
            [{"url": "a"}, {"url": "b"}],
            [{"url": "b"}, {"url": "c"}],
            [{"url": "c"}, {"url": "d"}],
        ]
        self.mouse = self

    def evaluate(self, _script, *_args):
        return self.lotes[min(self.indice, len(self.lotes) - 1)]

    def wheel(self, _x, y):
        if y > 0:
            self.indice += 1

    def wait_for_timeout(self, _milissegundos):
        return None


class PaginaVirtualizadaComStatusFalsa(PaginaVirtualizadaFalsa):
    def evaluate(self, script, *_args):
        lote = self.lotes[min(self.indice, len(self.lotes) - 1)]
        if script == SCRIPT_DIAGNOSTICO_STATUS_LISTA:
            return {
                "linhas_diagnosticadas": [
                    {
                        "url": jogo["url"],
                        "motivo": (
                            "interrompido" if jogo["url"] == "c"
                            else "ao_vivo"
                        ),
                    }
                    for jogo in lote
                ]
            }
        return lote


class PaginaVirtualizadaGrandeFalsa:
    def __init__(self, quantidade=320):
        self.quantidade = quantidade
        self.indice = 0
        self.mouse = self

    def evaluate(self, _script, *_args):
        limite = min((self.indice + 1) * 15, self.quantidade)
        return [{"url": f"jogo-{indice}"} for indice in range(limite)]

    def wheel(self, _x, y):
        if y > 0:
            self.indice += 1

    def wait_for_timeout(self, _milissegundos):
        return None


class PaginaEstatisticasProgressivasFalsa(PaginaPackBallFalsa):
    def __init__(self, leituras):
        super().__init__()
        self.leituras = list(leituras)
        self.leituras_realizadas = 0
        self.esperas_timeout = []

    def evaluate(self, script, *args):
        if script == SCRIPT_ESTATISTICAS:
            indice = min(
                self.leituras_realizadas, len(self.leituras) - 1
            )
            self.leituras_realizadas += 1
            return dict(self.leituras[indice])
        return super().evaluate(script, *args)

    def wait_for_timeout(self, milissegundos):
        self.esperas_timeout.append(milissegundos)


class AbaScannerFalsa:
    def __init__(self, pagina, link=False):
        self.pagina = pagina
        self.link = link

    def count(self):
        return 1

    def is_visible(self):
        return True

    def locator(self, seletor):
        if seletor != "a":
            raise AssertionError(seletor)
        return AbaScannerFalsa(self.pagina, link=True)

    def click(self, timeout=None, force=False):
        self.pagina.cliques_scanner.append({
            "link": self.link,
            "force": force,
            "timeout": timeout,
        })


class PaginaScannerFalsa:
    def __init__(self, provas):
        self.provas = list(provas)
        self.leituras = 0
        self.cliques_scanner = []
        self.esperas = []

    def locator(self, seletor):
        if seletor != "li:has(i.filter):visible":
            raise AssertionError(seletor)
        return AbaScannerFalsa(self)

    def wait_for_function(self, script, timeout=None, **_kwargs):
        self.esperas.append((script, timeout))
        return True

    def evaluate(self, script, *args):
        if script != SCRIPT_DIAGNOSTICO_SCANNER:
            return []
        indice = min(self.leituras, len(self.provas) - 1)
        self.leituras += 1
        return dict(self.provas[indice])


class ColetorPackBallTest(unittest.TestCase):
    def test_scanner_prioriza_sem_remover_cobertura_ao_vivo(self):
        ao_vivo = [
            {"url": "a", "texto_linha": "lista geral A"},
            {"url": "b", "texto_linha": "lista geral B"},
            {"url": "c", "texto_linha": "lista geral C"},
        ]
        scanner = [
            {"url": "b", "texto_linha": "pressao e ExG completos"},
            {"url": "fora", "texto_linha": "nao confirmado ao vivo"},
        ]

        jogos = ColetorPackBall._mesclar_prioridade_scanner(
            ao_vivo, scanner
        )

        self.assertEqual([jogo["url"] for jogo in jogos], ["b", "a", "c"])
        self.assertTrue(jogos[0]["scanner_prioritario"])
        self.assertEqual(jogos[0]["texto_linha"], "pressao e ExG completos")
        self.assertFalse(jogos[1]["scanner_prioritario"])
        self.assertNotIn("fora", {jogo["url"] for jogo in jogos})

    def test_diagnostico_scanner_exige_painel_e_contador_filtrado(self):
        self.assertIn("Partidas? filtradas?", SCRIPT_DIAGNOSTICO_SCANNER)
        self.assertIn("contador_filtrado", SCRIPT_DIAGNOSTICO_SCANNER)
        self.assertNotIn("localStorage", SCRIPT_DIAGNOSTICO_SCANNER)
        self.assertNotIn("cookie", SCRIPT_DIAGNOSTICO_SCANNER.lower())

    def test_scanner_repete_abertura_quando_primeiro_clique_nao_renderiza(self):
        pagina = PaginaScannerFalsa([
            {
                "painel_visivel": False,
                "contador_filtrado": None,
                "aba_encontrada": True,
            },
            {
                "painel_visivel": True,
                "contador_filtrado": 0,
                "aba_encontrada": True,
            },
        ])
        coletor = ColetorPackBall(usar_scanner_prioridade=True)

        jogos, diagnostico = coletor._coletar_scanner_prioritario(pagina)

        self.assertEqual(jogos, [])
        self.assertEqual(diagnostico["estado"], "prioridade_carregada")
        self.assertEqual(diagnostico["contador_filtrado"], 0)
        self.assertEqual(diagnostico["tentativas_abertura"], 2)
        self.assertEqual(len(pagina.cliques_scanner), 2)
        self.assertTrue(pagina.cliques_scanner[1]["force"])
        self.assertEqual(len(pagina.esperas), 2)

    def test_lista_mapeia_colunas_pelo_titulo_sem_autorizar_sinal(self):
        self.assertIn('document.querySelector("ul.header")', SCRIPT_JOGOS_AO_VIVO)
        self.assertIn('packball-lista-indicadores-v1', SCRIPT_JOGOS_AO_VIVO)
        self.assertIn('autoriza_sinal: false', SCRIPT_JOGOS_AO_VIVO)
        self.assertIn('capturarIndicadores', SCRIPT_JOGOS_AO_VIVO)

    def test_diagnostico_de_status_nao_coleta_token_ou_storage(self):
        self.assertIn("status_titulo", SCRIPT_DIAGNOSTICO_STATUS_LISTA)
        self.assertIn("status_texto", SCRIPT_DIAGNOSTICO_STATUS_LISTA)
        self.assertNotIn("localStorage", SCRIPT_DIAGNOSTICO_STATUS_LISTA)
        self.assertNotIn("cookie", SCRIPT_DIAGNOSTICO_STATUS_LISTA.lower())
        self.assertIn("interrompidos_total", SCRIPT_DIAGNOSTICO_STATUS_LISTA)
        self.assertIn(
            "fora_regulamentar_total", SCRIPT_DIAGNOSTICO_STATUS_LISTA
        )
        self.assertIn("fora_tempo_regulamentar", SCRIPT_DIAGNOSTICO_STATUS_LISTA)
        self.assertIn("interrompido", SCRIPT_JOGOS_AO_VIVO)

    def test_lista_descarta_finalizado_mesmo_na_aba_ao_vivo(self):
        descarte = SCRIPT_JOGOS_AO_VIVO.index(
            "if (terminou || interrompido || foraRegulamentar) continue;"
        )
        filtro_ambiguo = SCRIPT_JOGOS_AO_VIVO.index(
            "if (!intervalo && !emAndamento) continue;"
        )

        self.assertLess(descarte, filtro_ambiguo)
        self.assertNotIn(
            "!abaAoVivoConfirmada && !intervalo",
            SCRIPT_JOGOS_AO_VIVO,
        )

    def setUp(self):
        self.coletor = ColetorPackBall()

    def test_estado_final_exige_codigo_e_placar_principal(self):
        self.assertIn("status-5", SCRIPT_ESTADO_PARTIDA)
        self.assertIn(".result-tab", SCRIPT_ESTADO_PARTIDA)
        self.assertIn(".status-tab", SCRIPT_ESTADO_PARTIDA)

    def test_lista_aceita_minuto_numerico_sem_apostrofo(self):
        self.assertIn(
            r"^\d{1,3}(?:\(\d{1,2}\)|\+\d{1,2})?$",
            SCRIPT_JOGOS_AO_VIVO,
        )

    def test_lista_aceita_acrescimos_entre_parenteses_do_packball(self):
        padrao = (
            r"\d{1,3}(?:\(\d{1,2}\)|\+\d{1,2})?\s*['’]"
        )

        self.assertIn(padrao, SCRIPT_JOGOS_AO_VIVO)
        self.assertIn(padrao, SCRIPT_DIAGNOSTICO_STATUS_LISTA)
        self.assertIn(
            r"^\d{1,3}(?:\(\d{1,2}\)|\+\d{1,2})?$",
            SCRIPT_DIAGNOSTICO_STATUS_LISTA,
        )

    def test_entra_na_aba_ao_vivo_e_retorna_jogos(self):
        jogos = [{"mandante": "A", "visitante": "B", "url": "u"}]
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(texto="1"),
            retorno=jogos,
        )
        self.assertEqual(self.coletor.buscar_jogos_ao_vivo(pagina), jogos)
        self.assertTrue(pagina.botao.clicado)
        self.assertEqual(self.coletor.ultimo_diagnostico_lista, {
            "contador_ao_vivo": 1,
            "jogos_extraidos": 1,
            "diferenca": 0,
            "lista_consistente": True,
            "modo_confirmacao": "contador_ao_vivo",
            "tentativas": 1,
            "entraram": None,
            "sairam": None,
        })

    def test_divergencia_unitaria_confirma_transicao_na_segunda_leitura(self):
        jogos = [{"mandante": "A", "visitante": "B", "url": "u"}]
        pagina = PaginaPackBallFalsa(retorno=jogos)

        self.assertEqual(self.coletor.buscar_jogos_ao_vivo(pagina), jogos)

        self.assertEqual(pagina.navegacoes, 2)
        self.assertTrue(
            self.coletor.ultimo_diagnostico_lista["lista_consistente"]
        )
        self.assertEqual(
            self.coletor.ultimo_diagnostico_lista["tentativas"], 2
        )
        self.assertEqual(
            self.coletor.ultimo_diagnostico_lista["diferenca"], 1
        )
        self.assertTrue(
            self.coletor.ultimo_diagnostico_lista["transicao_dinamica"]
        )
        self.assertEqual(
            self.coletor.ultimo_diagnostico_lista["modo_confirmacao"],
            "transicao_dinamica_status_explicito",
        )

    def test_divergencia_maior_que_um_permanece_fechada(self):
        jogos = [{"mandante": "A", "visitante": "B", "url": "u"}]
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(texto="3"), retorno=jogos
        )

        self.assertEqual(self.coletor.buscar_jogos_ao_vivo(pagina), jogos)

        self.assertEqual(pagina.navegacoes, 2)
        self.assertFalse(
            self.coletor.ultimo_diagnostico_lista["lista_consistente"]
        )
        self.assertEqual(
            self.coletor.ultimo_diagnostico_lista["diferenca"], 2
        )

    def test_contador_desconta_jogos_explicitamente_interrompidos(self):
        jogos = [{"mandante": "A", "visitante": "B", "url": "u"}]
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(texto="3"),
            retorno=jogos,
            diagnostico_status={
                "excluidos": [
                    {
                        "status_titulo": "O jogo foi interrompido",
                        "status_texto": "INT 20",
                        "motivo": "interrompido",
                    },
                    {
                        "status_titulo": "O jogo foi interrompido",
                        "status_texto": "INT 65",
                        "motivo": "interrompido",
                    },
                ],
                "interrompidos_total": 2,
            },
        )

        self.assertEqual(self.coletor.buscar_jogos_ao_vivo(pagina), jogos)
        diagnostico = self.coletor.ultimo_diagnostico_lista
        self.assertTrue(diagnostico["lista_consistente"])
        self.assertEqual(diagnostico["contador_ao_vivo"], 3)
        self.assertEqual(diagnostico["contador_ao_vivo_efetivo"], 1)
        self.assertEqual(diagnostico["jogos_interrompidos"], 2)
        self.assertEqual(diagnostico["diferenca"], 0)
        self.assertEqual(diagnostico["tentativas"], 1)

    def test_contador_desconta_prorrogacao_explicitamente_identificada(self):
        jogos = [{"mandante": "A", "visitante": "B", "url": "u"}]
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(texto="2"),
            retorno=jogos,
            diagnostico_status={
                "excluidos": [{
                    "status_titulo": "Prorrogação",
                    "status_texto": "ET '",
                    "motivo": "fora_tempo_regulamentar",
                }],
                "interrompidos_total": 0,
                "fora_regulamentar_total": 1,
            },
        )

        self.assertEqual(self.coletor.buscar_jogos_ao_vivo(pagina), jogos)
        diagnostico = self.coletor.ultimo_diagnostico_lista

        self.assertTrue(diagnostico["lista_consistente"])
        self.assertEqual(diagnostico["contador_ao_vivo"], 2)
        self.assertEqual(diagnostico["contador_ao_vivo_efetivo"], 1)
        self.assertEqual(
            diagnostico["jogos_fora_tempo_regulamentar"], 1
        )
        self.assertEqual(diagnostico["diferenca"], 0)
        self.assertEqual(diagnostico["tentativas"], 1)

    def test_status_desconhecido_nao_e_descontado_do_contador(self):
        jogos = [{"mandante": "A", "visitante": "B", "url": "u"}]
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(texto="3"),
            retorno=jogos,
            diagnostico_status={
                "excluidos": [{
                    "status_titulo": "Estado novo",
                    "status_texto": "XYZ",
                    "motivo": "status_nao_reconhecido",
                }],
                "interrompidos_total": 0,
                "fora_regulamentar_total": 0,
            },
        )

        self.coletor.buscar_jogos_ao_vivo(pagina)

        diagnostico = self.coletor.ultimo_diagnostico_lista
        self.assertFalse(diagnostico["lista_consistente"])
        self.assertEqual(diagnostico["diferenca"], 2)
        self.assertNotIn("contador_ao_vivo_efetivo", diagnostico)

    def test_divergencia_transitoria_e_confirmada_na_segunda_leitura(self):
        class PaginaQueEstabiliza(PaginaPackBallFalsa):
            def evaluate(self, script, *args):
                if script == SCRIPT_DIAGNOSTICO_LISTA:
                    return self.diagnostico
                if self.navegacoes == 1:
                    return [{"url": "a"}]
                return [{"url": "a"}, {"url": "b"}]

        pagina = PaginaQueEstabiliza()
        jogos = self.coletor.buscar_jogos_ao_vivo(pagina)

        self.assertEqual({jogo["url"] for jogo in jogos}, {"a", "b"})
        self.assertEqual(pagina.navegacoes, 2)
        self.assertTrue(
            self.coletor.ultimo_diagnostico_lista["lista_consistente"]
        )
        self.assertEqual(
            self.coletor.ultimo_diagnostico_lista["tentativas"], 2
        )
        leituras = self.coletor.ultimo_diagnostico_lista[
            "leituras_tentativas"
        ]
        self.assertEqual(len(leituras), 2)
        self.assertFalse(leituras[0]["lista_consistente"])
        self.assertEqual(leituras[0]["jogos_extraidos"], 1)
        self.assertTrue(leituras[1]["lista_consistente"])
        self.assertEqual(leituras[1]["jogos_extraidos"], 2)

    def test_identifica_jogos_que_entram_e_saem_ao_vivo(self):
        pagina = PaginaPackBallFalsa(
            retorno=[{"url": "a"}, {"url": "b"}]
        )
        self.coletor.buscar_jogos_ao_vivo(pagina)
        pagina.retorno = [{"url": "b"}, {"url": "c"}]
        self.coletor.buscar_jogos_ao_vivo(pagina)
        self.assertEqual(self.coletor.ultimo_diagnostico_lista["entraram"], 1)
        self.assertEqual(self.coletor.ultimo_diagnostico_lista["sairam"], 1)

    def test_acumula_linhas_da_lista_virtualizada_ao_rolar(self):
        jogos = self.coletor._coletar_lista_virtualizada(
            PaginaVirtualizadaFalsa(), 4
        )
        self.assertEqual({jogo["url"] for jogo in jogos}, {"a", "b", "c", "d"})

    def test_acumula_status_de_toda_a_lista_virtualizada(self):
        self.coletor._coletar_lista_virtualizada(
            PaginaVirtualizadaComStatusFalsa(), 4
        )

        diagnostico = self.coletor._ultimo_diagnostico_virtualizacao
        self.assertEqual(diagnostico["fonte"], "rolagem_virtualizada_completa")
        self.assertEqual(diagnostico["linhas_com_partida"], 4)
        self.assertEqual(diagnostico["ao_vivo_total"], 3)
        self.assertEqual(diagnostico["interrompidos_total"], 1)
        self.assertEqual(diagnostico["excluidos"], [{
            "url": "c", "motivo": "interrompido",
        }])

    def test_lista_virtualizada_grande_ultrapassa_antigo_teto_de_rolagem(self):
        pagina = PaginaVirtualizadaGrandeFalsa(320)

        jogos = self.coletor._coletar_lista_virtualizada(pagina, 320)

        self.assertEqual(len(jogos), 320)
        self.assertGreater(pagina.indice, 12)

    def test_bloqueio_detectado_nao_e_retentado(self):
        class ControleBloqueado:
            chamadas = 0

            def antes_navegacao(self):
                self.chamadas += 1

            def validar_pagina(self, _pagina):
                raise PackBallBloqueadoError("bloqueado")

        controle = ControleBloqueado()
        coletor = ColetorPackBall(controle_acesso=controle)
        pagina = PaginaPackBallFalsa()
        with self.assertRaises(PackBallBloqueadoError):
            coletor.buscar_jogos_ao_vivo(pagina)
        self.assertEqual(pagina.navegacoes, 1)
        self.assertEqual(controle.chamadas, 1)

    def test_zero_ao_vivo_nao_tenta_clicar(self):
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(texto="0", visivel=False)
        )
        self.assertEqual(self.coletor.buscar_jogos_ao_vivo(pagina), [])
        self.assertFalse(pagina.botao.clicado)

    def test_botao_ausente_gera_erro_claro(self):
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(quantidade=0)
        )
        with self.assertRaisesRegex(
            PackBallListaNaoValidadaError, "Ao Vivo"
        ):
            self.coletor.buscar_jogos_ao_vivo(pagina)
        self.assertEqual(pagina.navegacoes, 2)

    def test_botao_ausente_usa_status_das_linhas_como_fallback(self):
        jogos = [{"mandante": "A", "visitante": "B", "url": "u"}]
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(quantidade=0),
            retorno=jogos,
        )

        self.assertEqual(self.coletor.buscar_jogos_ao_vivo(pagina), jogos)
        self.assertEqual(pagina.navegacoes, 1)

    def test_lista_geral_sem_contador_ao_vivo_falha_fechado(self):
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(quantidade=0),
            retorno=[],
            diagnostico={
                "linhas": 12,
                "links_partidas": 12,
                "corpo_visivel": True,
            },
        )

        with self.assertRaisesRegex(
            PackBallListaNaoValidadaError, "contador_ao_vivo_ausente"
        ):
            self.coletor.buscar_jogos_ao_vivo(pagina)
        self.assertEqual(pagina.navegacoes, 2)

    def test_zero_sem_contador_confirmado_por_duas_leituras(self):
        diagnostico_status = {
            "excluidos": [],
            "linhas_com_partida": 12,
            "ao_vivo_total": 0,
            "intervalo_total": 0,
            "finalizados_total": 8,
            "agendados_total": 3,
            "adiados_cancelados_total": 1,
            "interrompidos_total": 0,
            "fora_regulamentar_total": 0,
            "status_nao_reconhecido_total": 0,
            "classificados_total": 12,
        }
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(quantidade=0),
            retorno=[],
            diagnostico={
                "linhas": 12,
                "links_partidas": 30,
                "corpo_visivel": True,
            },
            diagnostico_status=diagnostico_status,
        )
        coletor = ColetorPackBall(
            aceitar_zero_sem_contador_confirmado=True
        )

        self.assertEqual(coletor.buscar_jogos_ao_vivo(pagina), [])
        self.assertEqual(pagina.navegacoes, 2)
        self.assertEqual(
            coletor.ultimo_diagnostico_lista["modo_confirmacao"],
            "status_linhas_zero_confirmado",
        )
        self.assertTrue(
            coletor.ultimo_diagnostico_lista["lista_consistente"]
        )

    def test_zero_sem_contador_com_status_desconhecido_falha_fechado(self):
        pagina = PaginaPackBallFalsa(
            botao=BotaoAoVivoFalso(quantidade=0),
            retorno=[],
            diagnostico={
                "linhas": 12,
                "links_partidas": 30,
                "corpo_visivel": True,
            },
            diagnostico_status={
                "excluidos": [{
                    "status_titulo": "",
                    "status_texto": "?",
                    "motivo": "status_nao_reconhecido",
                }],
                "linhas_com_partida": 12,
                "ao_vivo_total": 0,
                "finalizados_total": 8,
                "agendados_total": 3,
                "adiados_cancelados_total": 0,
                "interrompidos_total": 0,
                "fora_regulamentar_total": 0,
                "status_nao_reconhecido_total": 1,
                "classificados_total": 12,
            },
        )
        coletor = ColetorPackBall(
            aceitar_zero_sem_contador_confirmado=True
        )

        with self.assertRaises(PackBallListaNaoValidadaError):
            coletor.buscar_jogos_ao_vivo(pagina)
        self.assertEqual(pagina.navegacoes, 2)

    def test_click_transitorio_invisivel_recarrega_e_tenta_novamente(self):
        jogos = [{"mandante": "A", "visitante": "B", "url": "u"}]
        botao = BotaoAoVivoFalso(falhas_click=1)
        pagina = PaginaPackBallFalsa(botao=botao, retorno=jogos)

        self.assertEqual(self.coletor.buscar_jogos_ao_vivo(pagina), jogos)
        self.assertEqual(pagina.navegacoes, 2)
        self.assertTrue(botao.clicado)

    def test_coleta_estatisticas_na_url_da_partida(self):
        esperado = {"Chutes": "8-4", "Escanteios": "3-1"}
        pagina = PaginaPackBallFalsa(retorno=esperado)
        resultado = self.coletor.coletar_estatisticas(
            pagina, {"url": "https://packball.com/match/10/live"}
        )
        self.assertEqual(resultado, esperado)
        self.assertEqual(pagina.url, "https://packball.com/match/10/live")
        self.assertEqual(pagina.esperas_dinamicas[-1][1], 4000)

    def test_releitura_spa_complementa_essenciais_sem_nova_navegacao(self):
        pagina = PaginaEstatisticasProgressivasFalsa([
            {
                "Chutes": "8-4",
                "Chutes no gol": None,
                "Índice de pressão": None,
            },
            {
                "Chutes": None,
                "Chutes no gol": "3-2",
                "Índice de pressão": None,
            },
            {
                "Chutes no gol": None,
                "Índice de pressão": "55-45",
            },
        ])

        resultado = self.coletor.coletar_estatisticas(
            pagina, {"url": "https://packball.com/match/10/live"}
        )

        self.assertEqual(resultado["Chutes"], "8-4")
        self.assertEqual(resultado["Chutes no gol"], "3-2")
        self.assertEqual(resultado["Índice de pressão"], "55-45")
        self.assertEqual(pagina.navegacoes, 1)
        self.assertEqual(pagina.leituras_realizadas, 3)
        self.assertEqual(pagina.esperas_timeout[-2:], [1000, 1000])
        diagnostico = self.coletor.ultimo_diagnostico_estatisticas
        self.assertEqual(
            diagnostico["versao"],
            "diagnostico-coleta-estatisticas-v3",
        )
        self.assertEqual(diagnostico["estado"], "completo")
        self.assertEqual(diagnostico["tentativas_adicionais"], 2)
        self.assertEqual(diagnostico["campos_essenciais_ausentes"], [])
        self.assertEqual(
            diagnostico["campos_lidos"],
            ["Chutes", "Chutes no gol", "Índice de pressão"],
        )
        self.assertEqual(diagnostico["quantidade_campos_lidos"], 3)
        self.assertFalse(diagnostico["nova_navegacao"])
        self.assertFalse(diagnostico["altera_sinal"])
        self.assertIn("navegacao_segundos", diagnostico["duracoes_etapas"])
        self.assertIn(
            "carregamento_dom_segundos",
            diagnostico["navegacao_detalhada"],
        )

    def test_diagnostico_explica_coleta_parcial_apos_retentativas(self):
        pagina = PaginaEstatisticasProgressivasFalsa([
            {"Chutes": "8-4", "Chutes no gol": None},
            {"Chutes no gol": None},
            {"Chutes no gol": None},
        ])

        resultado = self.coletor.coletar_estatisticas(
            pagina, {"url": "https://packball.com/match/11/live"}
        )

        self.assertEqual(resultado["Chutes"], "8-4")
        diagnostico = self.coletor.ultimo_diagnostico_estatisticas
        self.assertEqual(diagnostico["estado"], "parcial")
        self.assertEqual(
            diagnostico["campos_essenciais_ausentes"],
            ["Chutes no gol", "Índice de pressão"],
        )
        self.assertEqual(diagnostico["campos_lidos"], ["Chutes"])
        self.assertEqual(diagnostico["quantidade_campos_lidos"], 1)

    def test_renova_sessao_expirada_e_continua(self):
        pagina = PaginaPackBallFalsa(login_visivel=True)
        chamadas = []

        def renovar(pagina_recebida):
            chamadas.append(pagina_recebida)
            pagina_recebida.login_visivel = False

        coletor = ColetorPackBall(renovar_sessao=renovar)
        self.assertEqual(coletor.buscar_jogos_ao_vivo(pagina), [])
        self.assertEqual(chamadas, [pagina])


if __name__ == "__main__":
    unittest.main()
