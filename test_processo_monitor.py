import json
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from processo_monitor import (
    TravaInstancia,
    estado_codigo_runtime,
    garantir_watchdog_ativo,
    garantir_pre_live_ativo,
    hash_codigo_watchdog,
    hash_codigo_runtime,
    gravar_json_atomico,
    dependencias_runtime_ausentes,
    dependencias_runtime_transitivas,
    ARQUIVOS_RUNTIME,
    ARQUIVOS_RUNTIME_WATCHDOG,
    iniciar_monitor,
    iniciar_pre_live,
    iniciar_watchdog,
    ler_estado,
    pid_ativo,
    registrar_estado,
    trava_em_uso,
)


class ProcessoMonitorTest(unittest.TestCase):
    def test_assinaturas_cobrem_imports_locais_transitivos(self):
        self.assertEqual(
            dependencias_runtime_ausentes(Path.cwd(), ARQUIVOS_RUNTIME), []
        )
        self.assertEqual(
            dependencias_runtime_ausentes(
                Path.cwd(), ARQUIVOS_RUNTIME_WATCHDOG
            ),
            [],
        )

    def test_assinatura_monitor_nao_inclui_watchdog_ou_relatorios(self):
        dependencias = set(dependencias_runtime_transitivas(
            Path.cwd(), ("monitor_ao_vivo.py",)
        ))
        declaradas = set(ARQUIVOS_RUNTIME)

        self.assertNotIn("watchdog.py", declaradas)
        self.assertNotIn("diagnostico_sinais_recentes.py", declaradas)
        # A política legada e o worker descartável são lidos dinamicamente e
        # por isso não aparecem na árvore de imports do Python.
        self.assertEqual(
            declaradas - dependencias,
            {"politica_proximo_gol.py", "treinar_modelo_worker.py"},
        )
        self.assertEqual(dependencias - declaradas, set())
    def setUp(self):
        self.lock = Path.cwd() / ".teste_monitor_instancia.lock"
        self.estado = Path.cwd() / ".teste_monitor_processo.json"
        self.pasta_processos = Path.cwd() / ".teste_processos_monitor"
        self.pasta_processos.mkdir(exist_ok=True)
        for arquivo in (self.lock, self.estado, self.estado.with_suffix(".json.tmp")):
            if arquivo.exists():
                arquivo.unlink()

    def tearDown(self):
        for arquivo in (self.lock, self.estado, self.estado.with_suffix(".json.tmp")):
            if arquivo.exists():
                arquivo.unlink()
        for arquivo in self.pasta_processos.iterdir():
            arquivo.unlink()
        self.pasta_processos.rmdir()

    def test_impede_segunda_instancia_e_libera_depois(self):
        primeira = TravaInstancia(self.lock)
        segunda = TravaInstancia(self.lock)
        self.assertTrue(primeira.adquirir())
        self.assertFalse(segunda.adquirir())
        primeira.liberar()
        self.assertTrue(segunda.adquirir())
        segunda.liberar()

    def test_gravacao_atomica_repete_bloqueio_transitorio_windows(self):
        caminho = self.pasta_processos / "estado.json"
        substituir_real = Path.replace
        chamadas = {"total": 0}

        def substituir_com_falha_transitoria(origem, destino):
            chamadas["total"] += 1
            if chamadas["total"] == 1:
                raise PermissionError("arquivo temporariamente ocupado")
            return substituir_real(origem, destino)

        with patch(
            "processo_monitor.Path.replace",
            autospec=True,
            side_effect=substituir_com_falha_transitoria,
        ), patch("processo_monitor.time.sleep") as dormir:
            gravar_json_atomico(caminho, {"status": "ativo"})

        self.assertEqual(
            json.loads(caminho.read_text(encoding="utf-8")),
            {"status": "ativo"},
        )
        self.assertEqual(chamadas["total"], 2)
        dormir.assert_called_once_with(0.05)
        self.assertEqual(
            list(self.pasta_processos.glob("*.tmp")), []
        )

    def test_trava_confirma_instancia_sem_depender_de_pid(self):
        trava = TravaInstancia(self.lock)
        self.assertTrue(trava.adquirir())
        try:
            self.assertTrue(trava_em_uso(self.lock))
        finally:
            trava.liberar()
        self.assertFalse(trava_em_uso(self.lock))

    def test_estado_e_gravado_atomicamente(self):
        registro = registrar_estado(self.estado, "ativo", pid=123)
        self.assertEqual(registro["pid"], 123)
        self.assertEqual(ler_estado(self.estado)["status"], "ativo")
        self.assertEqual(json.loads(self.estado.read_text())["pid"], 123)

    def test_pid_ativo_reconhece_processo_atual(self):
        self.assertTrue(pid_ativo(os.getpid()))

    def test_pid_ativo_rejeita_identificador_inexistente(self):
        self.assertFalse(pid_ativo(2_147_483_647))

    def test_inicia_watchdog_sem_janela_e_sem_console_herdado(self):
        with patch("processo_monitor.subprocess.Popen") as abrir:
            abrir.return_value.pid = 321
            pid = iniciar_watchdog(Path.cwd(), executavel="python-teste")
        self.assertEqual(pid, 321)
        argumentos, opcoes = abrir.call_args
        self.assertEqual(argumentos[0][0], "python-teste")
        self.assertTrue(argumentos[0][1].endswith("watchdog.py"))
        self.assertIsNotNone(opcoes["stdin"])
        self.assertIsNotNone(opcoes["stdout"])
        self.assertIsNotNone(opcoes["stderr"])
        self.assertEqual(
            opcoes["env"]["PYTHONIOENCODING"],
            "utf-8:backslashreplace",
        )
        self.assertEqual(opcoes["env"]["PYTHONUTF8"], "1")

    def test_inicia_pre_live_sem_janela_e_registra_estado(self):
        with patch("processo_monitor.subprocess.Popen") as abrir:
            abrir.return_value.pid = 322
            pid = iniciar_pre_live(
                self.pasta_processos, executavel="python-teste"
            )
        self.assertEqual(322, pid)
        argumentos, opcoes = abrir.call_args
        self.assertTrue(argumentos[0][1].endswith("agendador_pre_live.py"))
        self.assertIsNotNone(opcoes["stdout"])
        self.assertEqual(
            opcoes["env"]["PYTHONIOENCODING"],
            "utf-8:backslashreplace",
        )
        self.assertEqual(
            "iniciando",
            ler_estado(
                self.pasta_processos / "pre_live_processo.json"
            )["status"],
        )

    def test_supervisao_pre_live_nao_duplica_e_reinicia(self):
        registrar_estado(
            self.pasta_processos / "pre_live_processo.json",
            "ativo", pid=123,
        )
        iniciar = Mock(return_value=456)
        ativo = garantir_pre_live_ativo(
            self.pasta_processos,
            iniciar_fn=iniciar,
            verificar_pid=lambda pid: pid == 123,
            verificar_instancia=lambda: True,
        )
        self.assertEqual("ativo", ativo["estado"])
        iniciar.assert_not_called()
        reiniciado = garantir_pre_live_ativo(
            self.pasta_processos,
            iniciar_fn=iniciar,
            verificar_pid=lambda _pid: False,
            verificar_instancia=lambda: False,
        )
        self.assertEqual("iniciado", reiniciado["estado"])
        self.assertEqual(456, reiniciado["pid"])

    def test_monitor_registra_inicializacao_antes_de_criar_processo(self):
        with patch("processo_monitor.subprocess.Popen") as abrir:
            abrir.return_value.pid = 654
            pid = iniciar_monitor(
                self.pasta_processos,
                executavel="python-teste",
                terminal_visivel=(os.name == "nt"),
            )

        self.assertEqual(pid, 654)
        estado = ler_estado(
            self.pasta_processos / "monitor_processo.json"
        )
        self.assertEqual(estado["status"], "iniciando")
        opcoes = abrir.call_args.kwargs
        self.assertEqual(
            opcoes["env"]["PYTHONIOENCODING"],
            "utf-8:backslashreplace",
        )
        self.assertEqual(opcoes["env"]["PYTHONUTF8"], "1")
        if os.name == "nt":
            self.assertNotIn("stdin", opcoes)
            self.assertNotIn("stdout", opcoes)
            self.assertNotIn("stderr", opcoes)
            self.assertEqual(
                opcoes["creationflags"],
                subprocess.CREATE_NEW_CONSOLE
                | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            self.assertEqual(
                opcoes["env"]["MONITOR_MODO_INICIO"],
                "terminal_visivel",
            )
            self.assertEqual(estado["modo_inicio"], "terminal_visivel")
        else:
            self.assertEqual(opcoes["stdin"], subprocess.DEVNULL)
            self.assertEqual(opcoes["stdout"], subprocess.DEVNULL)
            self.assertEqual(opcoes["stderr"], subprocess.DEVNULL)

    def test_lancamento_duplicado_preserva_pid_e_estado_do_monitor_ativo(self):
        caminho = self.pasta_processos / "monitor_processo.json"
        esperado = registrar_estado(caminho, "ativo", pid=os.getpid())
        trava = TravaInstancia(
            self.pasta_processos / "monitor_instancia.lock"
        )
        self.assertTrue(trava.adquirir())
        try:
            with patch("processo_monitor.subprocess.Popen") as abrir:
                pid = iniciar_monitor(self.pasta_processos)
            abrir.assert_not_called()
            self.assertEqual(pid, os.getpid())
            self.assertEqual(ler_estado(caminho), esperado)
        finally:
            trava.liberar()

    def test_lancamento_nao_sobrescreve_ativo_publicado_pelo_filho(self):
        caminho = self.pasta_processos / "monitor_processo.json"

        def criar_filho(*_args, **_kwargs):
            registrar_estado(caminho, "ativo", pid=765)
            return Mock(pid=654)

        with patch(
            "processo_monitor.subprocess.Popen", side_effect=criar_filho
        ):
            self.assertEqual(iniciar_monitor(self.pasta_processos), 654)
        self.assertEqual(ler_estado(caminho)["pid"], 765)
        self.assertEqual(ler_estado(caminho)["status"], "ativo")
        self.assertEqual(
            ler_estado(self.pasta_processos / "monitor_lancamento.json")["pid"],
            654,
        )

    def test_segundo_lancador_aguarda_filho_ainda_sem_trava(self):
        registrar_estado(
            self.pasta_processos / "monitor_lancamento.json",
            "iniciado", pid=os.getpid(),
        )
        with patch("processo_monitor.subprocess.Popen") as abrir:
            self.assertEqual(
                iniciar_monitor(self.pasta_processos), os.getpid()
            )
        abrir.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "específico do Windows")
    def test_monitor_visivel_usa_iniciador_cmd_quando_disponivel(self):
        iniciador = self.pasta_processos / "abrir_monitor_visivel.cmd"
        iniciador.write_text("@echo off\r\n", encoding="utf-8")
        with patch("processo_monitor.subprocess.Popen") as abrir:
            abrir.return_value.pid = 656
            iniciar_monitor(
                self.pasta_processos,
                executavel="python-teste",
                terminal_visivel=True,
            )

        argumentos = abrir.call_args.args[0]
        self.assertEqual(argumentos[1:3], ["/d", "/c"])
        self.assertEqual(Path(argumentos[3]), iniciador)

    @unittest.skipUnless(os.name == "nt", "específico do Windows")
    def test_monitor_permite_rollback_para_segundo_plano(self):
        with patch("processo_monitor.subprocess.Popen") as abrir:
            abrir.return_value.pid = 655
            iniciar_monitor(
                self.pasta_processos,
                executavel="python-teste",
                terminal_visivel=False,
            )

        opcoes = abrir.call_args.kwargs
        self.assertEqual(opcoes["stdin"], subprocess.DEVNULL)
        self.assertEqual(opcoes["stdout"], subprocess.DEVNULL)
        self.assertEqual(opcoes["stderr"], subprocess.DEVNULL)
        self.assertEqual(
            opcoes["creationflags"],
            subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self.assertEqual(
            opcoes["env"]["MONITOR_MODO_INICIO"], "segundo_plano"
        )

    def test_falha_ao_criar_monitor_fica_persistida(self):
        with patch(
            "processo_monitor.subprocess.Popen",
            side_effect=OSError("falha simulada"),
        ):
            with self.assertRaises(OSError):
                iniciar_monitor(
                    self.pasta_processos, executavel="python-teste"
                )

        estado = ler_estado(
            self.pasta_processos / "monitor_processo.json"
        )
        self.assertEqual(estado["status"], "falha")
        self.assertEqual(estado["erro"], "OSError")

    def test_monitor_nao_duplica_watchdog_ativo(self):
        registrar_estado(
            self.pasta_processos / "watchdog_processo.json",
            "ativo",
            pid=123,
        )
        iniciar = Mock(return_value=456)

        resultado = garantir_watchdog_ativo(
            self.pasta_processos,
            iniciar_fn=iniciar,
            verificar_pid=lambda pid: pid == 123,
            verificar_instancia=lambda: True,
        )

        self.assertEqual(resultado["estado"], "ativo")
        self.assertEqual(resultado["pid"], 123)
        self.assertTrue(resultado["trava_em_uso"])
        iniciar.assert_not_called()

    def test_monitor_reinicia_watchdog_encerrado(self):
        registrar_estado(
            self.pasta_processos / "watchdog_processo.json",
            "encerrado",
            pid=123,
        )
        iniciar = Mock(return_value=456)

        resultado = garantir_watchdog_ativo(
            self.pasta_processos,
            iniciar_fn=iniciar,
            verificar_pid=lambda _pid: False,
            verificar_instancia=lambda: False,
        )

        self.assertEqual(resultado["estado"], "reiniciado")
        self.assertEqual(resultado["pid"], 456)
        self.assertEqual(resultado["pid_anterior"], 123)
        iniciar.assert_called_once_with(self.pasta_processos)

    def test_pid_reutilizado_sem_trava_nao_mascara_watchdog_morto(self):
        registrar_estado(
            self.pasta_processos / "watchdog_processo.json",
            "ativo",
            pid=123,
        )
        iniciar = Mock(return_value=456)

        resultado = garantir_watchdog_ativo(
            self.pasta_processos,
            iniciar_fn=iniciar,
            verificar_pid=lambda _pid: True,
            verificar_instancia=lambda: False,
        )

        self.assertEqual(resultado["estado"], "reiniciado")
        self.assertTrue(resultado["pid_anterior_responde"])
        self.assertFalse(resultado["trava_em_uso"])

    def test_hash_runtime_muda_quando_codigo_muda(self):
        arquivo = Path.cwd() / ".teste_runtime.py"
        try:
            arquivo.write_text("VERSAO = 1\n", encoding="utf-8")
            primeiro = hash_codigo_runtime(Path.cwd(), [arquivo.name])
            arquivo.write_text("VERSAO = 2\n", encoding="utf-8")
            segundo = hash_codigo_runtime(Path.cwd(), [arquivo.name])
        finally:
            if arquivo.exists():
                arquivo.unlink()

        self.assertNotEqual(primeiro, segundo)

    def test_hash_watchdog_tem_assinatura_sha256(self):
        assinatura = hash_codigo_watchdog(Path.cwd())

        self.assertEqual(len(assinatura), 64)
        int(assinatura, 16)

    def test_detecta_codigo_alterado_apos_inicio_sem_hash_legado(self):
        arquivo = Path.cwd() / ".teste_runtime.py"
        try:
            arquivo.write_text("VERSAO = 1\n", encoding="utf-8")
            estado = {"atualizado_em": "2020-01-01T00:00:00"}
            resultado = estado_codigo_runtime(
                Path.cwd(), estado, [arquivo.name]
            )
        finally:
            if arquivo.exists():
                arquivo.unlink()

        self.assertEqual(resultado, "reinicio_pendente")
