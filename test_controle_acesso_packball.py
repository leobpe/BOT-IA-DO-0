import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from controle_acesso_packball import (
    ControleAcessoPackBall,
    PackBallBloqueadoError,
    PackBallPausaPreventivaError,
    auditar_ritmo_packball,
    avaliar_experimento_ritmo_packball,
    verificar_acesso_packball,
)


class RelogioFalso:
    def __init__(self):
        self.monotonico = 100.0
        self.agora = datetime(2026, 7, 22, 12, 0, 0)
        self.esperas = []

    def dormir(self, segundos):
        self.esperas.append(segundos)
        self.monotonico += segundos
        self.agora += timedelta(seconds=segundos)


class PaginaFalsa:
    def __init__(self, texto):
        self.texto = texto

    def evaluate(self, _script):
        return self.texto


class ControleAcessoPackBallTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_packball_acesso_estado.json"
        self.lock = self.caminho.with_suffix(".json.lock")
        self.log = Path.cwd() / ".teste_packball_eventos.jsonl"
        self.avaliacao = Path.cwd() / ".teste_packball_ritmo.json"
        for caminho in (
            self.caminho, self.caminho.with_suffix(".json.tmp"), self.lock,
            self.log, self.avaliacao,
        ):
            if caminho.exists():
                caminho.unlink()
        self.relogio = RelogioFalso()

    def tearDown(self):
        for caminho in (
            self.caminho, self.caminho.with_suffix(".json.tmp"), self.lock,
            self.log, self.avaliacao,
        ):
            if caminho.exists():
                caminho.unlink()

    def _controle(self, **opcoes):
        opcoes.setdefault("intervalo_minimo_segundos", 10)
        opcoes.setdefault("cooldown_minutos", 10)
        return ControleAcessoPackBall(
            self.caminho,
            relogio=lambda: self.relogio.monotonico,
            dormir=self.relogio.dormir,
            agora_fn=lambda: self.relogio.agora,
            **opcoes,
        )

    def test_respeita_intervalo_global_entre_navegacoes(self):
        controle = self._controle()
        controle.antes_navegacao()
        self.relogio.monotonico += 3
        self.relogio.agora += timedelta(seconds=3)
        controle.antes_navegacao()
        self.assertEqual(self.relogio.esperas, [7])

    def test_intervalo_e_compartilhado_por_processos(self):
        primeiro = self._controle()
        segundo = self._controle()
        primeiro.antes_navegacao()
        segundo.antes_navegacao()
        self.assertEqual(self.relogio.esperas, [10])

    def test_teto_por_janela_ativa_pausa_sem_nova_navegacao(self):
        controle = self._controle(
            maximo_por_janela=2, janela_segundos=60
        )
        controle.antes_navegacao()
        controle.antes_navegacao()
        with self.assertRaises(PackBallBloqueadoError):
            controle.antes_navegacao()
        estado = controle.estado_atual()
        self.assertTrue(estado["ativo"])
        self.assertEqual(estado["motivo"], "limite_local_navegacoes")
        self.assertEqual(len(estado["navegacoes_recentes"]), 2)

    def test_distribui_cota_sem_rajada_nem_pausa_longa(self):
        controle = self._controle(
            maximo_por_janela=3,
            janela_segundos=60,
            distribuir_janela=True,
            margem_distribuicao_segundos=1,
        )

        for _ in range(4):
            controle.antes_navegacao()

        self.assertEqual(self.relogio.esperas, [21, 21, 21])
        estado = controle.estado_atual()
        self.assertFalse(estado["ativo"])
        self.assertTrue(estado["distribuicao_janela_ativa"])
        self.assertEqual(
            estado["intervalo_navegacao_efetivo_segundos"], 21
        )
        self.assertEqual(
            estado["maximo_navegacoes_efetivo_janela"], 3
        )

    def test_audita_ritmo_distribuido_seguro(self):
        controle = self._controle(
            maximo_por_janela=3,
            janela_segundos=60,
            distribuir_janela=True,
            margem_distribuicao_segundos=1,
        )
        for _ in range(4):
            controle.antes_navegacao()

        auditoria = auditar_ritmo_packball(
            self.caminho,
            agora=self.relogio.agora,
            exigir_distribuicao=True,
        )

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["estado"], "seguro")
        self.assertEqual(auditoria["violacoes_intervalo"], 0)
        self.assertLessEqual(
            auditoria["navegacoes_validas"],
            auditoria["maximo_por_janela"],
        )

    def test_verificacao_preserva_limites_persistidos_do_runtime(self):
        self.caminho.write_text(
            json.dumps({
                "motivo": "lista_packball_nao_validada",
                "distribuicao_janela_ativa": True,
                "intervalo_navegacao_efetivo_segundos": 21.929,
                "maximo_navegacoes_efetivo_janela": 28,
                "janela_navegacoes_segundos": 600,
            }),
            encoding="utf-8",
        )

        estado = verificar_acesso_packball(
            self.caminho, agora=self.relogio.agora
        )

        self.assertTrue(estado["saudavel"])
        self.assertEqual(
            estado["motivo_persistido"],
            "lista_packball_nao_validada",
        )
        self.assertTrue(estado["distribuicao_janela_ativa"])
        self.assertEqual(
            estado["intervalo_navegacao_efetivo_segundos"], 21.929
        )
        self.assertEqual(
            estado["maximo_navegacoes_efetivo_janela"], 28
        )

    def test_auditoria_detecta_ritmo_rapido_demais(self):
        self.caminho.write_text(
            json.dumps({
                "distribuicao_janela_ativa": True,
                "intervalo_navegacao_efetivo_segundos": 20,
                "maximo_navegacoes_efetivo_janela": 3,
                "janela_navegacoes_segundos": 60,
                "navegacoes_recentes": [
                    "2026-07-22T11:59:30",
                    "2026-07-22T11:59:40",
                    "2026-07-22T11:59:50",
                    "2026-07-22T12:00:00",
                ],
            }),
            encoding="utf-8",
        )

        auditoria = auditar_ritmo_packball(
            self.caminho,
            agora=self.relogio.agora,
            exigir_distribuicao=True,
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertIn("intervalo_minimo_violado", auditoria["motivos"])
        self.assertIn("teto_janela_excedido", auditoria["motivos"])

    def _gravar_ciclos_experimento(self, base=3, distribuido=4):
        eventos = []
        inicio = datetime(2026, 7, 22, 10, 0, 0)
        for indice in range(base + distribuido):
            distribuicao = indice >= base
            eventos.append({
                "em": (inicio + timedelta(minutes=5 * indice)).isoformat(),
                "evento": "ciclo_concluido",
                "duracao_segundos": 300,
                "tarefas_agendadas": 8,
                "tarefas_processadas": 6,
                "tarefas_com_odds": 5,
                "perfil_agendamento": {"foco_processadas": 2},
                "cobertura_temporal": {
                    "partidas_com_historico": 3 if distribuicao else 1,
                    "janelas_disponiveis": {
                        "5": 2 if distribuicao else 0,
                        "10": 1,
                        "15": 1 if distribuicao else 0,
                    },
                },
                "ritmo_packball": (
                    {
                        "distribuicao_janela_ativa": True,
                        "intervalo_efetivo_segundos": 21.929,
                        "maximo_por_janela": 28,
                        "janela_segundos": 600,
                    }
                    if distribuicao else {}
                ),
            })
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )
        return eventos

    def test_experimento_ritmo_preserva_base_e_aprova_amostra(self):
        eventos = self._gravar_ciclos_experimento(base=3, distribuido=4)
        primeira = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 40),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(primeira["estado"], "aprovado")
        self.assertEqual(primeira["base"]["ciclos"], 3)
        self.assertEqual(primeira["experimento"]["ciclos"], 4)
        self.assertGreater(primeira["retencao_temporal"], 1)

        # Simula a rotacao que removeu a base, mas manteve o inicio do teste.
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos[3:]) + "\n",
            encoding="utf-8",
        )
        segunda = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 45),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(segunda["base"], primeira["base"])
        self.assertEqual(segunda["estado"], "aprovado")

    def test_baixa_demanda_nao_prova_regressao_nem_aprovacao_do_ritmo(self):
        eventos = self._gravar_ciclos_experimento(base=3, distribuido=4)
        for evento in eventos[3:]:
            evento["tarefas_agendadas"] = 1
            evento["tarefas_processadas"] = 1
            evento["tarefas_com_odds"] = 1
            evento["perfil_agendamento"]["foco_processadas"] = 1
            evento["cobertura_temporal"]["partidas_com_historico"] = 1
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )
        resultado = avaliar_experimento_ritmo_packball(
            self.log, self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 40),
            minimo_ciclos=3, minimo_minutos=10,
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "em_observacao")
        self.assertLess(resultado["retencao_fluxo"], 0.75)
        self.assertNotIn("fluxo_abaixo_da_base", resultado["motivos"])
        comparacao = resultado["comparacao_demanda_fluxo"]
        self.assertFalse(comparacao["comparavel"])
        self.assertEqual(comparacao["capacidade_base_tarefas_por_ciclo"], 6)
        self.assertEqual(comparacao["demanda_atual_tarefas_por_ciclo"], 1)
        self.assertIn(
            "fluxo_inconclusivo_por_baixa_demanda", resultado["observacoes"]
        )

        # A mudança de interpretação não reescreve a referência congelada.
        segunda = avaliar_experimento_ritmo_packball(
            self.log, self.avaliacao,
            agora=datetime(2026, 7, 22, 10, 45),
            minimo_ciclos=3, minimo_minutos=10,
        )
        self.assertEqual(segunda["base"], resultado["base"])

        # Poucos jogos nunca escondem uma violação real do acesso.
        inseguro = avaliar_experimento_ritmo_packball(
            self.log, self.avaliacao,
            auditoria_ritmo={"saudavel": False},
            agora=datetime(2026, 7, 22, 10, 45),
            minimo_ciclos=3, minimo_minutos=10,
        )
        self.assertEqual(inseguro["estado"], "regressao_recomendada")
        self.assertIn("ritmo_atual_inseguro", inseguro["motivos"])

        # Tampouco escondem perda de cobertura temporal.
        for evento in eventos[3:]:
            evento["cobertura_temporal"]["partidas_com_historico"] = 0
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )
        sem_cobertura = avaliar_experimento_ritmo_packball(
            self.log, self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 45),
            minimo_ciclos=3, minimo_minutos=10,
        )
        self.assertIn(
            "cobertura_temporal_abaixo_da_base", sem_cobertura["motivos"]
        )

    def test_lentidao_com_demanda_preservada_continua_sendo_regressao(self):
        eventos = self._gravar_ciclos_experimento(base=3, distribuido=4)
        for evento in eventos[3:]:
            evento["tarefas_processadas"] = 2
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )
        resultado = avaliar_experimento_ritmo_packball(
            self.log, self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 40),
            minimo_ciclos=3, minimo_minutos=10,
        )
        self.assertTrue(resultado["comparacao_demanda_fluxo"]["comparavel"])
        self.assertEqual(resultado["estado"], "regressao_recomendada")
        self.assertIn("fluxo_abaixo_da_base", resultado["motivos"])

    def test_sem_telemetria_demanda_nao_suprime_alerta_de_fluxo(self):
        eventos = self._gravar_ciclos_experimento(base=3, distribuido=4)
        for evento in eventos[3:]:
            evento.pop("tarefas_agendadas")
            evento["tarefas_processadas"] = 2
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )
        resultado = avaliar_experimento_ritmo_packball(
            self.log, self.avaliacao,
            agora=datetime(2026, 7, 22, 10, 40),
            minimo_ciclos=3, minimo_minutos=10,
        )
        self.assertIsNone(resultado["comparacao_demanda_fluxo"]["comparavel"])
        self.assertIn("fluxo_abaixo_da_base", resultado["motivos"])

    def test_experimento_ritmo_detecta_pausa_apos_inicio(self):
        eventos = self._gravar_ciclos_experimento(base=2, distribuido=3)
        eventos.append({
            "em": "2026-07-22T10:24:30",
            "evento": "ciclo_pausado_packball",
            "motivo": "limite local",
        })
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )

        resultado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 30),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "em_observacao")
        self.assertEqual(resultado["pausas_packball_historicas"], 1)
        self.assertEqual(
            resultado["ultimo_incidente_em"], "2026-07-22T10:24:30"
        )
        self.assertIn(
            "janela_reiniciada_apos_incidente",
            resultado["observacoes"],
        )
        self.assertNotIn(
            "pausa_packball_durante_experimento", resultado["motivos"]
        )

        # O incidente continua registrado mesmo depois da rotacao do log.
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos[:-1]) + "\n",
            encoding="utf-8",
        )
        persistido = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 31),
            minimo_ciclos=3,
            minimo_minutos=10,
        )
        self.assertEqual(persistido["pausas_packball"], 1)
        self.assertTrue(persistido["saudavel"])
        self.assertEqual(persistido["estado"], "em_observacao")
        self.assertEqual(
            persistido["ultimo_incidente_em"],
            "2026-07-22T10:24:30",
        )

    def test_v3_congela_divida_v2_e_revalida_so_dados_futuros(self):
        eventos = self._gravar_ciclos_experimento(base=3, distribuido=4)
        inicial = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 40),
            minimo_ciclos=3,
            minimo_minutos=10,
        )
        legado = dict(inicial)
        legado.update({
            "versao": "ritmo-packball-v2",
            "estado": "regressao_recomendada",
            "saudavel": False,
            "motivos": ["pausa_packball_durante_experimento"],
            "iniciado_em": legado.pop("regime_iniciado_em"),
            "pausas_packball": 9,
        })
        for campo in (
            "revalidacao_prospectiva",
            "migrada_de",
            "evidencia_legada_congelada",
            "pausas_packball_historicas",
            "pausas_na_revalidacao",
            "ultimo_incidente_em",
        ):
            legado.pop(campo, None)
        self.avaliacao.write_text(
            json.dumps(legado), encoding="utf-8"
        )

        migrado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 41),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(migrado["versao"], "ritmo-packball-v3")
        self.assertEqual(migrado["estado"], "em_observacao")
        self.assertTrue(migrado["saudavel"])
        self.assertEqual(migrado["experimento"]["ciclos"], 0)
        self.assertEqual(migrado["migrada_de"], "ritmo-packball-v2")
        self.assertEqual(
            migrado["evidencia_legada_congelada"]["estado"],
            "regressao_recomendada",
        )
        self.assertEqual(
            migrado["evidencia_legada_congelada"]["pausas_packball"], 9
        )

        modelo = dict(eventos[-1])
        for minuto in (45, 50, 55):
            ciclo = json.loads(json.dumps(modelo))
            ciclo["em"] = datetime(
                2026, 7, 22, 10, minuto
            ).isoformat()
            eventos.append(ciclo)
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )
        aprovado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 11, 0),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(aprovado["estado"], "aprovado")
        self.assertEqual(aprovado["experimento"]["ciclos"], 3)
        self.assertEqual(aprovado["pausas_packball_historicas"], 9)
        self.assertEqual(
            aprovado["evidencia_legada_congelada"],
            migrado["evidencia_legada_congelada"],
        )

    def test_experimento_normaliza_cobertura_quando_fila_muda(self):
        eventos = self._gravar_ciclos_experimento(base=3, distribuido=4)
        for indice, evento in enumerate(eventos):
            if indice < 3:
                evento["tarefas_processadas"] = 4
                evento["perfil_agendamento"] = {"foco_processadas": 2}
                evento["cobertura_temporal"][
                    "partidas_com_historico"
                ] = 2
            else:
                evento["tarefas_processadas"] = 10
                evento["perfil_agendamento"] = {"foco_processadas": 2}
                evento["cobertura_temporal"][
                    "partidas_com_historico"
                ] = 2
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )

        resultado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 40),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(resultado["estado"], "aprovado")
        self.assertEqual(
            resultado["metrica_retencao_temporal"],
            "rendimento_temporal_por_foco",
        )
        self.assertEqual(resultado["retencao_temporal"], 1.0)
        self.assertEqual(resultado["retencao_temporal_bruta"], 0.4)
        self.assertIn(
            "comparacao_temporal_normalizada_por_foco",
            resultado["observacoes"],
        )

    def test_experimento_reconstroi_metrica_de_base_legada(self):
        self._gravar_ciclos_experimento(base=3, distribuido=4)
        avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 40),
            minimo_ciclos=3,
            minimo_minutos=10,
        )
        persistido = json.loads(self.avaliacao.read_text(encoding="utf-8"))
        persistido["base"].pop("rendimento_temporal_por_foco", None)
        persistido["base"].pop("telemetria_perfil_completa", None)
        self.avaliacao.write_text(
            json.dumps(persistido), encoding="utf-8"
        )

        segunda = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 41),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(segunda["estado"], "aprovado")
        self.assertEqual(
            segunda["metrica_retencao_temporal"],
            "rendimento_temporal_por_foco",
        )
        self.assertNotIn(
            "rendimento_temporal_por_foco", segunda["base"]
        )
        self.assertGreater(segunda["retencao_temporal"], 1)

    def test_experimento_ritmo_ignora_ciclo_vazio_de_inicializacao(self):
        eventos = self._gravar_ciclos_experimento(base=2, distribuido=2)
        eventos.append({
            "em": "2026-07-22T10:30:00",
            "evento": "ciclo_concluido",
            "duracao_segundos": 20,
            "tarefas_processadas": 0,
            "ritmo_packball": {
                "distribuicao_janela_ativa": True,
                "intervalo_efetivo_segundos": 21.929,
                "maximo_por_janela": 28,
                "janela_segundos": 600,
            },
        })
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )

        resultado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 35),
        )

        self.assertEqual(resultado["experimento"]["ciclos"], 2)

    def test_experimento_ritmo_mede_fluxo_no_tempo_corrido(self):
        eventos = self._gravar_ciclos_experimento(base=2, distribuido=2)
        eventos[0]["em"] = "2026-07-22T10:00:00"
        eventos[1]["em"] = "2026-07-22T10:30:00"
        eventos[0]["duracao_segundos"] = 60
        eventos[1]["duracao_segundos"] = 60
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )

        resultado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 11, 0),
        )

        self.assertEqual(resultado["base"]["periodo_observado_minutos"], 31)
        self.assertEqual(
            resultado["base"]["processadas_por_10_minutos"], 3.87
        )

    def test_experimento_ritmo_nao_conta_processo_parado_como_lentidao(self):
        eventos = self._gravar_ciclos_experimento(base=3, distribuido=4)
        eventos[-1]["em"] = (
            datetime.fromisoformat(eventos[-2]["em"])
            + timedelta(hours=2)
        ).isoformat()
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )

        resultado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 13, 0),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(resultado["estado"], "aprovado")
        self.assertEqual(
            resultado["experimento"]["gaps_inativos_excluidos"], 1
        )
        self.assertGreater(
            resultado["experimento"][
                "duracao_inativa_excluida_minutos"
            ],
            100,
        )

    def test_experimento_exclui_somente_manutencao_explicitamente_marcada(self):
        eventos = self._gravar_ciclos_experimento(base=2, distribuido=3)
        eventos[-1]["em"] = "2026-07-22T10:30:00"
        eventos.extend((
            {
                "em": "2026-07-22T10:16:00",
                "evento": "modo_manutencao_solicitado",
            },
            {
                "em": "2026-07-22T10:26:00",
                "evento": "modo_manutencao_liberado",
            },
        ))
        eventos.sort(key=lambda item: item["em"])
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )

        resultado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 35),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(resultado["estado"], "aprovado")
        self.assertEqual(
            resultado["experimento"]["pausas_manutencao_excluidas"], 1
        )
        self.assertEqual(
            resultado["experimento"][
                "duracao_manutencao_excluida_minutos"
            ],
            10.0,
        )
        self.assertIn(
            "manutencao_excluida_da_metrica_fluxo",
            resultado["observacoes"],
        )

        eventos = [
            item for item in eventos
            if not str(item.get("evento") or "").startswith(
                "modo_manutencao_"
            )
        ]
        self.log.write_text(
            "\n".join(json.dumps(item) for item in eventos) + "\n",
            encoding="utf-8",
        )
        self.avaliacao.unlink(missing_ok=True)
        sem_marcacao = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            agora=datetime(2026, 7, 22, 10, 35),
            minimo_ciclos=3,
            minimo_minutos=10,
        )

        self.assertEqual(sem_marcacao["estado"], "regressao_recomendada")
        self.assertIn("fluxo_abaixo_da_base", sem_marcacao["motivos"])

    def test_rollback_ativo_e_estado_seguro_nao_vira_falha(self):
        self._gravar_ciclos_experimento(base=2, distribuido=3)
        self.caminho.write_text(
            json.dumps({"rollback_capacidade_ativo": True}),
            encoding="utf-8",
        )

        resultado = avaliar_experimento_ritmo_packball(
            self.log,
            self.avaliacao,
            auditoria_ritmo={"saudavel": True},
            caminho_estado_acesso=self.caminho,
            agora=datetime(2026, 7, 22, 10, 30),
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "rollback_acionado")
        self.assertIn(
            "rollback_de_seguranca_acionado", resultado["observacoes"]
        )

    def test_falha_login_ativa_pausa_longa_persistente(self):
        controle = self._controle()
        limite = controle.ativar_pausa("falha_login_packball", minutos=360)
        self.assertEqual(limite, self.relogio.agora + timedelta(hours=6))
        with self.assertRaises(PackBallPausaPreventivaError):
            self._controle().antes_navegacao()

    def test_tentativa_manual_nao_libera_pausa_para_monitor(self):
        controle = self._controle()
        controle.ativar_pausa("falha_login_packball", minutos=360)

        controle.antes_navegacao(autorizar_login_manual=True)

        self.assertTrue(controle.estado_atual()["ativo"])
        with self.assertRaises(PackBallPausaPreventivaError):
            self._controle().antes_navegacao()

    def test_tentativa_manual_nao_ignora_bloqueio_do_site(self):
        controle = self._controle()
        controle.ativar_pausa(
            "excesso_solicitacoes_packball", minutos=15
        )

        with self.assertRaises(PackBallPausaPreventivaError):
            controle.antes_navegacao(autorizar_login_manual=True)

    def test_lista_nao_validada_ja_pausada_e_interrupcao_protegida(self):
        controle = self._controle()
        controle.ativar_pausa(
            "lista_packball_nao_validada", minutos=15
        )

        with self.assertRaises(PackBallPausaPreventivaError) as captura:
            self._controle().antes_navegacao()

        self.assertIn(
            "motivo: lista_packball_nao_validada",
            str(captura.exception),
        )

    def test_somente_pausa_de_login_pode_ser_liberada_manualmente(self):
        controle = self._controle()
        controle.ativar_pausa("falha_login_packball", minutos=360)
        self.assertTrue(controle.liberar_pausa_login_manual())
        self.assertFalse(controle.estado_atual()["ativo"])

        controle.ativar_pausa("excesso_solicitacoes_packball", minutos=15)
        self.assertFalse(controle.liberar_pausa_login_manual())
        self.assertTrue(controle.estado_atual()["ativo"])

    def test_login_confirmado_restaura_capacidade_do_experimento(self):
        controle = self._controle(
            intervalo_minimo_segundos=8,
            maximo_por_janela=4,
            janela_segundos=60,
            distribuir_janela=True,
            margem_distribuicao_segundos=1,
            experimento_capacidade=True,
            intervalo_rollback_segundos=20,
            maximo_rollback_por_janela=2,
        )
        controle.ativar_pausa("falha_login_packball", minutos=360)
        self.assertEqual(controle.intervalo_minimo_segundos, 31)
        self.assertEqual(controle.maximo_por_janela, 2)

        self.assertTrue(controle.liberar_pausa_login_manual())

        estado = controle.estado_atual()
        self.assertFalse(estado["ativo"])
        self.assertNotIn("rollback_capacidade_ativo", estado)
        self.assertEqual(controle.intervalo_minimo_segundos, 16)
        self.assertEqual(controle.maximo_por_janela, 4)
        self.assertEqual(
            estado["capacidade_restaurada_motivo"],
            "login_manual_confirmado",
        )
        self.assertEqual(
            estado["ultimo_rollback_capacidade"]["motivo"],
            "falha_login_packball",
        )

    def test_login_confirmado_limpa_rollback_residual_sem_pausa(self):
        controle = self._controle(
            intervalo_minimo_segundos=8,
            maximo_por_janela=4,
            experimento_capacidade=True,
            intervalo_rollback_segundos=10,
            maximo_rollback_por_janela=2,
        )
        controle.ativar_pausa("falha_login_packball", minutos=360)
        dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        for campo in ("pausado_ate", "pausado_em", "motivo"):
            dados.pop(campo, None)
        self.caminho.write_text(json.dumps(dados), encoding="utf-8")

        self.assertTrue(controle.liberar_pausa_login_manual())
        estado = controle.estado_atual()
        self.assertNotIn("rollback_capacidade_ativo", estado)
        self.assertEqual(controle.intervalo_minimo_segundos, 8)
        self.assertEqual(controle.maximo_por_janela, 4)

    def test_login_manual_nao_remove_rollback_de_excesso(self):
        controle = self._controle(
            intervalo_minimo_segundos=8,
            maximo_por_janela=4,
            experimento_capacidade=True,
            intervalo_rollback_segundos=10,
            maximo_rollback_por_janela=2,
        )
        controle.ativar_pausa(
            "excesso_solicitacoes_packball", minutos=15
        )

        self.assertFalse(controle.liberar_pausa_login_manual())
        estado = controle.estado_atual()
        self.assertTrue(estado["rollback_capacidade_ativo"])
        self.assertEqual(
            estado["rollback_capacidade_motivo"],
            "excesso_solicitacoes_packball",
        )
        self.assertEqual(controle.intervalo_minimo_segundos, 10)
        self.assertEqual(controle.maximo_por_janela, 2)

    def test_bloqueio_ativa_circuit_breaker_persistente(self):
        controle = self._controle()
        pagina = PaginaFalsa(
            "Voce fez muitas solicitacoes em um curto periodo de tempo. "
            "Aguarde 57 Segundos. packball@packball.com"
        )
        with self.assertRaises(PackBallBloqueadoError) as captura_inicial:
            controle.validar_pagina(pagina)
        self.assertNotIsInstance(
            captura_inicial.exception, PackBallPausaPreventivaError
        )

        novo_processo = self._controle()
        with self.assertRaises(PackBallPausaPreventivaError) as captura_pausa:
            novo_processo.antes_navegacao()
        self.assertIn(
            "motivo: excesso_solicitacoes_packball",
            str(captura_pausa.exception),
        )
        self.assertGreaterEqual(
            novo_processo.estado_atual()["restante_segundos"], 600
        )

        self.relogio.agora += timedelta(minutes=10, seconds=1)
        novo_processo.antes_navegacao()

    def test_pagina_normal_nao_ativa_bloqueio(self):
        controle = self._controle()
        controle.validar_pagina(PaginaFalsa("Partidas ao vivo"))
        self.assertFalse(controle.estado_atual()["ativo"])

    def test_bloqueio_reverte_experimento_para_limites_seguros(self):
        controle = self._controle(
            intervalo_minimo_segundos=8,
            maximo_por_janela=3,
            experimento_capacidade=True,
            intervalo_rollback_segundos=10,
            maximo_rollback_por_janela=2,
        )
        pagina = PaginaFalsa(
            "Voce fez muitas solicitacoes em um curto periodo de tempo. "
            "Aguarde 57 Segundos. packball@packball.com"
        )

        with self.assertRaises(PackBallBloqueadoError):
            controle.validar_pagina(pagina)

        estado = controle.estado_atual()
        self.assertTrue(estado["rollback_capacidade_ativo"])
        self.assertEqual(
            estado["rollback_capacidade_motivo"],
            "excesso_solicitacoes_packball",
        )
        self.assertEqual(controle.intervalo_minimo_segundos, 10)
        self.assertEqual(controle.maximo_por_janela, 2)

    def test_rejeita_rollback_mais_agressivo_que_ritmo_normal(self):
        with self.assertRaisesRegex(ValueError, "Rollback PackBall inseguro"):
            self._controle(
                intervalo_minimo_segundos=10,
                maximo_por_janela=8,
                janela_segundos=180,
                distribuir_janela=True,
                experimento_capacidade=True,
                intervalo_rollback_segundos=12,
                maximo_rollback_por_janela=24,
            )

    def test_aceita_rollback_realmente_conservador(self):
        controle = self._controle(
            intervalo_minimo_segundos=10,
            maximo_por_janela=8,
            janela_segundos=180,
            distribuir_janela=True,
            experimento_capacidade=True,
            intervalo_rollback_segundos=26,
            maximo_rollback_por_janela=7,
        )

        self.assertEqual(controle.intervalo_minimo_segundos, 23)
        self.assertEqual(controle.maximo_rollback_por_janela, 7)

    def test_rollback_experimental_persiste_apos_reinicio(self):
        primeiro = self._controle(
            experimento_capacidade=True,
            intervalo_rollback_segundos=10,
            maximo_rollback_por_janela=2,
        )
        primeiro.ativar_pausa("falha_login_packball", minutos=10)

        novo = self._controle(
            intervalo_minimo_segundos=8,
            maximo_por_janela=3,
            experimento_capacidade=True,
            intervalo_rollback_segundos=10,
            maximo_rollback_por_janela=2,
        )
        novo.estado_atual()

        self.assertEqual(novo.intervalo_minimo_segundos, 10)
        self.assertEqual(novo.maximo_por_janela, 2)


if __name__ == "__main__":
    unittest.main()
