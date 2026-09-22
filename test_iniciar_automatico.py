import unittest
from datetime import datetime
from pathlib import Path

from iniciar_automatico import (
    VERSAO_HEARTBEAT_AUTOSTART,
    evidenciar_definicao_tarefa,
    executavel_python_console,
    iniciar_automaticamente,
    sistema_ativo_confirmado,
)
from processo_monitor import gravar_json_atomico, ler_estado
from controle_sistema import solicitar_modo_manutencao


class IniciarAutomaticoTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_iniciar_automatico"
        self.pasta.mkdir(exist_ok=True)

    def tearDown(self):
        for caminho in sorted(
            self.pasta.rglob("*"), key=lambda item: len(item.parts), reverse=True
        ):
            caminho.unlink() if caminho.is_file() else caminho.rmdir()
        self.pasta.rmdir()

    @staticmethod
    def _consulta_tarefa_valida(**_kwargs):
        return {
            "instalada": True,
            "saudavel": True,
            "consultavel": True,
            "origem_evidencia": "consulta_direta",
            "permite_inicio_em_bateria": True,
            "continua_em_bateria": True,
            "intervalo": "PT5M",
            "divergencias": [],
        }

    def test_prefere_python_console_da_venv(self):
        executavel = self.pasta / ".venv" / "Scripts" / "python.exe"
        executavel.parent.mkdir(parents=True)
        executavel.touch()
        self.assertEqual(
            executavel_python_console(
                self.pasta, "C:/Python/pythonw.exe"
            ),
            executavel,
        )

    def test_execucao_idempotente_registra_resultado(self):
        recebido = {}

        def garantir(destino, **opcoes):
            recebido.update(opcoes)
            return {
                "monitor": {"estado": "ja_ativo", "pid": 10},
                "watchdog": {"estado": "ja_ativo", "pid": 20},
            }

        resultado = iniciar_automaticamente(
            self.pasta,
            garantir_fn=garantir,
            executavel_atual="C:/Python/python.exe",
            agora=datetime(2026, 7, 21, 20, 0),
            origem_agendador=True,
            consultar_tarefa_fn=self._consulta_tarefa_valida,
        )

        self.assertEqual(resultado["monitor"]["estado"], "ja_ativo")
        self.assertIn("iniciar_monitor_fn", recebido)
        estado = ler_estado(
            self.pasta / "autostart_ultima_execucao.json"
        )
        self.assertEqual(estado["status"], "sucesso")
        self.assertEqual(estado["atualizado_em"], "2026-07-21T20:00:00")
        self.assertEqual(estado["origem"], "agendador_windows")
        self.assertEqual(estado["versao"], VERSAO_HEARTBEAT_AUTOSTART)
        self.assertTrue(estado["definicao_tarefa"]["saudavel"])
        self.assertTrue(
            estado["definicao_tarefa"]["permite_inicio_em_bateria"]
        )

    def test_confirma_sistema_ativo_com_travas_e_pids_vivos(self):
        gravar_json_atomico(
            self.pasta / "monitor_processo.json", {"pid": 10}
        )
        gravar_json_atomico(
            self.pasta / "watchdog_processo.json", {"pid": 20}
        )

        resultado = sistema_ativo_confirmado(
            self.pasta,
            verificar_pid=lambda pid: pid in {10, 20},
            verificar_trava=lambda _caminho: True,
        )

        self.assertTrue(resultado["ativo"])
        self.assertEqual(resultado["monitor"]["estado"], "ja_ativo")
        self.assertEqual(resultado["watchdog"]["estado"], "ja_ativo")

    def test_agendador_nao_repete_preflight_se_sistema_ja_esta_ativo(self):
        def nao_executar(*_args, **_kwargs):
            self.fail("não executar pré-voo com os dois processos ativos")

        resultado = iniciar_automaticamente(
            self.pasta,
            garantir_fn=nao_executar,
            detectar_sistema_fn=lambda _pasta: {
                "ativo": True,
                "monitor": {"estado": "ja_ativo", "pid": 10},
                "watchdog": {"estado": "ja_ativo", "pid": 20},
            },
            confirmar_fn=lambda _pasta, estado: estado,
            agora=datetime(2026, 8, 30, 20, 30),
            origem_agendador=True,
            consultar_tarefa_fn=self._consulta_tarefa_valida,
        )

        self.assertEqual(
            resultado["motivo"], "sistema_ja_ativo_confirmado"
        )
        estado = ler_estado(
            self.pasta / "autostart_ultima_execucao.json"
        )
        self.assertEqual(estado["status"], "sucesso")
        self.assertEqual(estado["monitor"]["estado"], "ja_ativo")

    def test_evidencia_recusa_consulta_baseada_no_proprio_heartbeat(self):
        evidencia = evidenciar_definicao_tarefa(
            self.pasta,
            consultar_fn=lambda **_kwargs: {
                "instalada": True,
                "saudavel": True,
                "consultavel": False,
                "origem_evidencia": "execucao_agendada_recente",
                "heartbeat": {"status": "sucesso"},
            },
        )

        self.assertFalse(evidencia["saudavel"])
        self.assertFalse(evidencia["consulta_direta"])
        self.assertIn(
            "consulta_definicao_nao_direta",
            evidencia["divergencias"],
        )

    def test_falha_fica_auditavel(self):
        def falhar(*_args, **_kwargs):
            raise RuntimeError("teste token=segredo")

        with self.assertRaises(RuntimeError):
            iniciar_automaticamente(
                self.pasta,
                garantir_fn=falhar,
                agora=datetime(2026, 7, 21, 20, 1),
            )

        estado = ler_estado(self.pasta / "autostart_ultima_execucao.json")
        self.assertEqual(estado["status"], "falha")
        self.assertEqual(estado["erro"], "RuntimeError")
        self.assertNotIn("segredo", estado["mensagem"])

    def test_falha_imediata_de_estabilidade_nao_vira_sucesso(self):
        def garantir(*_args, **_kwargs):
            return {
                "estado": "iniciado_ou_ja_ativo",
                "monitor": {"estado": "iniciado", "pid": 10},
                "watchdog": {"estado": "iniciado", "pid": 20},
            }

        def confirmar(_pasta, resultado):
            resultado["estado"] = "inicio_falhou"
            resultado["motivo"] = "processo_falhou_na_inicializacao"
            resultado["falhas_inicio"] = ["monitor"]
            resultado["confirmacao_inicio"] = {
                "saudavel": False,
                "estado": "falha_explicita",
                "componentes": {
                    "monitor": {
                        "erro": "PermissionError",
                        "mensagem": "Acesso negado",
                    }
                },
            }
            return resultado

        resultado = iniciar_automaticamente(
            self.pasta,
            garantir_fn=garantir,
            confirmar_fn=confirmar,
            agora=datetime(2026, 7, 28, 22, 0),
            origem_agendador=True,
            consultar_tarefa_fn=self._consulta_tarefa_valida,
        )

        self.assertEqual(resultado["estado"], "inicio_falhou")
        estado = ler_estado(
            self.pasta / "autostart_ultima_execucao.json"
        )
        self.assertEqual(estado["status"], "falha")
        self.assertEqual(
            estado["motivo"], "processo_falhou_na_inicializacao"
        )
        self.assertEqual(estado["falhas_inicio"], ["monitor"])

    def test_agendador_nao_desfaz_manutencao_manual(self):
        solicitar_modo_manutencao(self.pasta, "bloqueio_packball")

        resultado = iniciar_automaticamente(
            self.pasta,
            executavel_atual="C:/Python/python.exe",
            agora=datetime(2026, 7, 22, 13, 0),
        )

        self.assertEqual(resultado["estado"], "inicio_recusado")
        self.assertEqual(resultado["motivo"], "modo_manutencao_ativo")
        self.assertTrue((self.pasta / "modo_manutencao.json").exists())
        estado = ler_estado(
            self.pasta / "autostart_ultima_execucao.json"
        )
        self.assertEqual(estado["status"], "recusado")

    def test_recusa_registra_quais_checks_impediram_recuperacao(self):
        resultado = iniciar_automaticamente(
            self.pasta,
            garantir_fn=lambda *_args, **_opcoes: {
                "estado": "inicio_recusado",
                "motivo": "preflight_reprovado",
                "falhas_preflight": ["banco", "sessao_packball"],
                "monitor": {"estado": "preflight_recusado", "pid": None},
                "watchdog": {"estado": "preflight_recusado", "pid": None},
            },
            agora=datetime(2026, 7, 28, 21, 0),
            origem_agendador=True,
            consultar_tarefa_fn=self._consulta_tarefa_valida,
        )

        self.assertEqual(resultado["estado"], "inicio_recusado")
        estado = ler_estado(
            self.pasta / "autostart_ultima_execucao.json"
        )
        self.assertEqual(
            estado["falhas_preflight"],
            ["banco", "sessao_packball"],
        )

    def test_recusa_de_login_preserva_apenas_tipos_tecnicos(self):
        iniciar_automaticamente(
            self.pasta,
            garantir_fn=lambda *_args, **_opcoes: {
                "estado": "inicio_recusado",
                "motivo": "renovacao_sessao_falhou",
                "erro_renovacao": "PackBallBloqueadoError",
                "causa_renovacao": "PlaywrightTimeoutError",
                "monitor": {"estado": "sessao_nao_renovada", "pid": None},
                "watchdog": {"estado": "sessao_nao_renovada", "pid": None},
            },
            agora=datetime(2026, 8, 1, 14, 10),
            origem_agendador=True,
            consultar_tarefa_fn=self._consulta_tarefa_valida,
        )

        estado = ler_estado(
            self.pasta / "autostart_ultima_execucao.json"
        )
        self.assertEqual(
            estado["erro_renovacao"], "PackBallBloqueadoError"
        )
        self.assertEqual(
            estado["causa_renovacao"], "PlaywrightTimeoutError"
        )


if __name__ == "__main__":
    unittest.main()
