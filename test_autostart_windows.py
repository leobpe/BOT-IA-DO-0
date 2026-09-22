import subprocess
import unittest
import json
from datetime import datetime, timedelta
from pathlib import Path

from autostart_windows import (
    NOME_TAREFA,
    VERSAO_HEARTBEAT_AUTOSTART,
    acao_tarefa,
    comando_ajuste_energia,
    comando_instalacao,
    instalar,
    consultar,
    remover,
    validar_definicao_xml,
)


class ExecutorFalso:
    def __init__(self, codigos, saidas=None):
        self.codigos = list(codigos)
        self.saidas = list(saidas or [])
        self.comandos = []

    def __call__(self, comando, **_kwargs):
        self.comandos.append(comando)
        codigo = self.codigos.pop(0)
        saida = self.saidas.pop(0) if self.saidas else "OK"
        return subprocess.CompletedProcess(
            comando, codigo, stdout=saida if codigo == 0 else "", stderr="erro"
        )


class AutostartWindowsTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_autostart_windows"
        self.pasta.mkdir(exist_ok=True)
        (self.pasta / "iniciar_automatico.py").touch()
        self.pythonw = self.pasta / "pythonw.exe"
        self.pythonw.touch()

    def tearDown(self):
        for arquivo in self.pasta.iterdir():
            arquivo.unlink()
        self.pasta.rmdir()

    def test_acao_preserva_caminhos_com_espaco(self):
        acao = acao_tarefa(self.pasta, pythonw=self.pythonw)
        self.assertEqual(acao.count('"'), 4)
        self.assertIn("iniciar_automatico.py", acao)
        self.assertIn("--agendador-windows", acao)

    def test_comando_e_interativo_limitado_e_idempotente(self):
        comando = comando_instalacao(
            self.pasta, pythonw=self.pythonw, usuario="Leonardo"
        )
        self.assertIn(NOME_TAREFA, comando)
        self.assertIn("/IT", comando)
        self.assertIn("LIMITED", comando)
        self.assertIn("/F", comando)
        self.assertEqual(comando[comando.index("/MO") + 1], "5")

    def test_ajuste_de_energia_mantem_recuperacao_ativa_na_bateria(self):
        comando = comando_ajuste_energia()
        script = comando[-1]
        self.assertIn("DisallowStartIfOnBatteries=$false", script)
        self.assertIn("StopIfGoingOnBatteries=$false", script)
        self.assertIn(NOME_TAREFA, script)

    def test_instalacao_so_confirma_depois_da_consulta(self):
        executor = ExecutorFalso(
            [0, 0, 0], ["OK", "OK", self._xml_valido()]
        )
        estado = instalar(
            self.pasta,
            executor=executor,
            pythonw=self.pythonw,
            usuario="Leonardo",
        )
        self.assertTrue(estado["instalada"])
        self.assertEqual(len(executor.comandos), 3)
        self.assertIn("/Create", executor.comandos[0])
        self.assertEqual(executor.comandos[1][0], "powershell.exe")
        self.assertIn("/Query", executor.comandos[2])

    def test_falha_no_ajuste_de_energia_remove_tarefa_incompleta(self):
        executor = ExecutorFalso([0, 1, 0], ["OK", "erro", "OK"])

        with self.assertRaises(RuntimeError):
            instalar(
                self.pasta,
                executor=executor,
                pythonw=self.pythonw,
                usuario="Leonardo",
            )

        self.assertIn("/Create", executor.comandos[0])
        self.assertEqual(executor.comandos[1][0], "powershell.exe")
        self.assertIn("/Delete", executor.comandos[2])

    def _xml_valido(self, intervalo="PT5M", comando=None, argumentos=None):
        comando = comando or str(self.pythonw.resolve())
        argumentos = argumentos or (
            f'"{(self.pasta / "iniciar_automatico.py").resolve()}" '
            "--agendador-windows"
        )
        return f"""
        <Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <Triggers><CalendarTrigger><Repetition>
            <Interval>{intervalo}</Interval>
          </Repetition></CalendarTrigger></Triggers>
          <Principals><Principal>
            <LogonType>InteractiveToken</LogonType>
            <RunLevel>LeastPrivilege</RunLevel>
          </Principal></Principals>
          <Settings>
            <Enabled>true</Enabled>
            <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
            <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
          </Settings>
          <Actions><Exec><Command>{comando}</Command>
            <Arguments>{argumentos}</Arguments></Exec></Actions>
        </Task>
        """

    def test_valida_toda_a_definicao_da_tarefa(self):
        estado = validar_definicao_xml(
            self._xml_valido(), pasta=self.pasta, pythonw=self.pythonw
        )
        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["divergencias"], [])
        self.assertTrue(estado["permite_inicio_em_bateria"])
        self.assertTrue(estado["continua_em_bateria"])

    def test_detecta_tarefa_bloqueada_na_bateria(self):
        xml = self._xml_valido().replace(
            "<DisallowStartIfOnBatteries>false",
            "<DisallowStartIfOnBatteries>true",
        ).replace(
            "<StopIfGoingOnBatteries>false",
            "<StopIfGoingOnBatteries>true",
        )

        estado = validar_definicao_xml(
            xml, pasta=self.pasta, pythonw=self.pythonw
        )

        self.assertFalse(estado["saudavel"])
        self.assertIn(
            "inicio_em_bateria_bloqueado", estado["divergencias"]
        )
        self.assertIn(
            "parada_ao_usar_bateria", estado["divergencias"]
        )

    def test_aceita_nivel_limitado_implicito_serializado_pelo_schtasks(self):
        xml = self._xml_valido().replace(
            "<RunLevel>LeastPrivilege</RunLevel>", ""
        )

        estado = validar_definicao_xml(
            xml, pasta=self.pasta, pythonw=self.pythonw
        )

        self.assertTrue(estado["saudavel"])
        self.assertEqual(
            estado["nivel_privilegio"], "LeastPrivilege (implícito)"
        )

    def test_detecta_tarefa_com_acao_intervalo_e_privilegio_incorretos(self):
        xml = self._xml_valido(
            intervalo="PT1M",
            comando="C:/Python/python.exe",
            argumentos='"C:/outro.py"',
        ).replace("InteractiveToken", "Password").replace(
            "LeastPrivilege", "HighestAvailable"
        )

        estado = validar_definicao_xml(
            xml, pasta=self.pasta, pythonw=self.pythonw
        )

        self.assertFalse(estado["saudavel"])
        self.assertEqual(
            set(estado["divergencias"]),
            {
                "executavel_incorreto", "launcher_incorreto",
                "intervalo_incorreto", "logon_nao_interativo",
                "nivel_privilegio_incorreto",
            },
        )

    def test_consulta_reprova_xml_corrompido(self):
        estado = consultar(executor=ExecutorFalso([0], ["nao-e-xml"]))
        self.assertTrue(estado["instalada"])
        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["divergencias"], ["xml_tarefa_invalido"])

    def test_remocao_ausente_nao_falha(self):
        executor = ExecutorFalso([1])
        estado = remover(executor=executor)
        self.assertFalse(estado["removida"])
        self.assertEqual(len(executor.comandos), 1)

    def test_consulta_indisponivel_e_diagnosticavel(self):
        def indisponivel(*_args, **_kwargs):
            raise FileNotFoundError("schtasks")

        estado = consultar(executor=indisponivel)
        self.assertFalse(estado["instalada"])
        self.assertFalse(estado["consultavel"])
        self.assertFalse(estado["saudavel"])
        self.assertIn("FileNotFoundError", estado["detalhes"])

    def test_heartbeat_recente_comprova_tarefa_sem_visibilidade(self):
        agora = datetime(2026, 7, 25, 18, 0)
        (self.pasta / "autostart_ultima_execucao.json").write_text(
            json.dumps({
                "versao": VERSAO_HEARTBEAT_AUTOSTART,
                "status": "sucesso",
                "atualizado_em": (
                    agora - timedelta(minutes=5)
                ).isoformat(),
                "origem": "agendador_windows",
                "definicao_tarefa": {
                    "saudavel": True,
                    "consulta_direta": True,
                    "permite_inicio_em_bateria": True,
                    "continua_em_bateria": True,
                    "divergencias": [],
                },
            }),
            encoding="utf-8",
        )

        estado = consultar(
            executor=ExecutorFalso([1]),
            pasta=self.pasta,
            pythonw=self.pythonw,
            agora=agora,
        )

        self.assertTrue(estado["instalada"])
        self.assertTrue(estado["saudavel"])
        self.assertFalse(estado["consultavel"])
        self.assertEqual(
            estado["origem_evidencia"], "execucao_agendada_recente"
        )

    def test_heartbeat_sem_prova_direta_da_definicao_nao_e_saudavel(self):
        agora = datetime(2026, 7, 25, 18, 0)
        (self.pasta / "autostart_ultima_execucao.json").write_text(
            json.dumps({
                "versao": VERSAO_HEARTBEAT_AUTOSTART,
                "status": "sucesso",
                "atualizado_em": agora.isoformat(),
                "origem": "agendador_windows",
                "definicao_tarefa": {
                    "saudavel": False,
                    "consulta_direta": False,
                    "divergencias": [
                        "consulta_definicao_nao_direta"
                    ],
                },
            }),
            encoding="utf-8",
        )

        estado = consultar(
            executor=ExecutorFalso([1]),
            pasta=self.pasta,
            pythonw=self.pythonw,
            agora=agora,
        )

        self.assertTrue(estado["instalada"])
        self.assertFalse(estado["saudavel"])
        self.assertEqual(
            estado["divergencias"],
            ["consulta_definicao_nao_direta"],
        )

    def test_heartbeat_vencido_nao_mascara_tarefa_ausente(self):
        agora = datetime(2026, 7, 25, 18, 0)
        (self.pasta / "autostart_ultima_execucao.json").write_text(
            json.dumps({
                "versao": VERSAO_HEARTBEAT_AUTOSTART,
                "status": "sucesso",
                "atualizado_em": (
                    agora - timedelta(minutes=16)
                ).isoformat(),
                "origem": "agendador_windows",
                "definicao_tarefa": {
                    "saudavel": True,
                    "consulta_direta": True,
                    "permite_inicio_em_bateria": True,
                    "continua_em_bateria": True,
                    "divergencias": [],
                },
            }),
            encoding="utf-8",
        )

        estado = consultar(
            executor=ExecutorFalso([1]),
            pasta=self.pasta,
            pythonw=self.pythonw,
            agora=agora,
        )

        self.assertFalse(estado["instalada"])
        self.assertFalse(estado["saudavel"])

    def test_preflight_recusado_nao_finge_recuperacao_saudavel(self):
        agora = datetime(2026, 7, 28, 21, 0)
        (self.pasta / "autostart_ultima_execucao.json").write_text(
            json.dumps({
                "versao": VERSAO_HEARTBEAT_AUTOSTART,
                "status": "recusado",
                "atualizado_em": agora.isoformat(),
                "origem": "agendador_windows",
                "motivo": "preflight_reprovado",
                "falhas_preflight": ["coleta"],
                "definicao_tarefa": {
                    "saudavel": True,
                    "consulta_direta": True,
                    "permite_inicio_em_bateria": True,
                    "continua_em_bateria": True,
                    "divergencias": [],
                },
            }),
            encoding="utf-8",
        )

        estado = consultar(
            executor=ExecutorFalso([1]),
            pasta=self.pasta,
            pythonw=self.pythonw,
            agora=agora,
        )

        self.assertFalse(estado["saudavel"])
        self.assertEqual(
            estado["divergencias"],
            ["ultima_execucao_nao_recuperou_sistema"],
        )
        self.assertEqual(estado["heartbeat"]["falhas_preflight"], ["coleta"])

    def test_recusa_por_manutencao_planejada_permanece_saudavel(self):
        agora = datetime(2026, 7, 28, 21, 0)
        (self.pasta / "autostart_ultima_execucao.json").write_text(
            json.dumps({
                "versao": VERSAO_HEARTBEAT_AUTOSTART,
                "status": "recusado",
                "atualizado_em": agora.isoformat(),
                "origem": "agendador_windows",
                "motivo": "modo_manutencao_ativo",
                "definicao_tarefa": {
                    "saudavel": True,
                    "consulta_direta": True,
                    "permite_inicio_em_bateria": True,
                    "continua_em_bateria": True,
                    "divergencias": [],
                },
            }),
            encoding="utf-8",
        )

        estado = consultar(
            executor=ExecutorFalso([1]),
            pasta=self.pasta,
            pythonw=self.pythonw,
            agora=agora,
        )

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["divergencias"], [])


if __name__ == "__main__":
    unittest.main()
