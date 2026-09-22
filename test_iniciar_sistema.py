import unittest
import json
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from iniciar_sistema import (
    _restaurar_manutencao_apos_falha_inicio,
    analisar_argumentos_inicio,
    confirmar_inicio_estavel,
    garantir_sistema,
    iniciar_validado,
    preparar_banco_para_preflight,
)
from backup_banco import (
    BackupBanco,
    verificar_arquivo_backup,
    verificar_backup,
    verificar_backup_pre_migracao,
)
from banco import BancoMonitor
from controle_sistema import ler_modo_manutencao, solicitar_modo_manutencao
from processo_monitor import registrar_estado
from watchdog import acionar_recuperacao_banco_ativo


class IniciarSistemaTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_iniciar_sistema"
        self.pasta.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.pasta)

    def _criar_backup_valido(self, agora, valor="preservado"):
        origem = self.pasta / "origem_backup.db"
        banco = BancoMonitor(origem)
        banco.fechar()
        conexao = sqlite3.connect(origem)
        try:
            conexao.execute(
                "CREATE TABLE IF NOT EXISTS marcador_recuperacao "
                "(valor TEXT NOT NULL)"
            )
            conexao.execute("DELETE FROM marcador_recuperacao")
            conexao.execute(
                "INSERT INTO marcador_recuperacao (valor) VALUES (?)",
                (valor,),
            )
            conexao.commit()
            caminho, _ = BackupBanco(
                self.pasta / "backups"
            ).criar_periodico(conexao, agora)
        finally:
            conexao.close()
        origem.unlink()
        return caminho

    def test_inicia_apenas_componentes_ausentes(self):
        chamadas = []
        resultado = garantir_sistema(
            self.pasta,
            iniciar_watchdog_fn=lambda pasta: chamadas.append(
                ("watchdog", pasta)
            ) or 101,
            iniciar_monitor_fn=lambda pasta: chamadas.append(
                ("monitor", pasta)
            ) or 202,
            verificar_pid=lambda pid: False,
        )
        self.assertEqual(resultado["watchdog"]["pid"], 101)
        self.assertEqual(resultado["monitor"]["pid"], 202)
        self.assertEqual(
            [componente for componente, _ in chamadas],
            ["monitor", "watchdog"],
        )

    def test_nao_duplica_componentes_ativos(self):
        registrar_estado(
            self.pasta / "watchdog_processo.json", "ativo", pid=101
        )
        registrar_estado(
            self.pasta / "monitor_processo.json", "ativo", pid=202
        )
        resultado = garantir_sistema(
            self.pasta,
            iniciar_watchdog_fn=lambda pasta: self.fail(
                "não deveria iniciar watchdog"
            ),
            iniciar_monitor_fn=lambda pasta: self.fail(
                "não deveria iniciar monitor"
            ),
            verificar_pid=lambda pid: pid in (101, 202),
            verificar_trava=lambda _caminho: True,
        )
        self.assertEqual(resultado["watchdog"]["estado"], "ja_ativo")
        self.assertEqual(resultado["monitor"]["estado"], "ja_ativo")

    def test_pid_reutilizado_sem_trava_inicia_componentes_reais(self):
        registrar_estado(
            self.pasta / "watchdog_processo.json", "ativo", pid=101
        )
        registrar_estado(
            self.pasta / "monitor_processo.json", "ativo", pid=202
        )

        resultado = garantir_sistema(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: 303,
            iniciar_monitor_fn=lambda _pasta: 404,
            verificar_pid=lambda _pid: True,
            verificar_trava=lambda _caminho: False,
        )

        self.assertEqual(resultado["watchdog"]["pid"], 303)
        self.assertEqual(resultado["monitor"]["pid"], 404)

    def test_iniciar_libera_modo_manutencao(self):
        solicitar_modo_manutencao(self.pasta, "teste")

        resultado = garantir_sistema(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: 101,
            iniciar_monitor_fn=lambda _pasta: 202,
            verificar_pid=lambda _pid: False,
        )

        self.assertTrue(resultado["modo_manutencao_liberado"])
        self.assertFalse((self.pasta / "modo_manutencao.json").exists())

    def test_cli_exige_intencao_explicita_para_retomar_manutencao(self):
        comum = analisar_argumentos_inicio([])
        retomada = analisar_argumentos_inicio(["--retomar-manutencao"])

        self.assertFalse(comum.retomar_manutencao)
        self.assertTrue(retomada.retomar_manutencao)

    def test_circuit_breaker_impede_inicio_e_preserva_manutencao(self):
        solicitar_modo_manutencao(self.pasta, "teste")
        (self.pasta / "packball_acesso_estado.json").write_text(
            json.dumps({
                "bloqueado_ate": (
                    datetime.now() + timedelta(minutes=10)
                ).isoformat(),
                "motivo": "excesso_solicitacoes_packball",
            }),
            encoding="utf-8",
        )

        resultado = garantir_sistema(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: self.fail("nao iniciar"),
            iniciar_monitor_fn=lambda _pasta: self.fail("nao iniciar"),
            verificar_pid=lambda _pid: False,
        )

        self.assertFalse(resultado["modo_manutencao_liberado"])
        self.assertEqual(
            resultado["monitor"]["estado"],
            "bloqueado_acesso_packball",
        )
        self.assertTrue((self.pasta / "modo_manutencao.json").exists())

    def test_inicio_validado_recusa_preflight_sem_criar_processos(self):
        opcoes_preflight = {}

        def preflight(*_args, **opcoes):
            opcoes_preflight.update(opcoes)
            return {
                "pronto_para_reinicio": False,
                "verificacoes": {
                    "banco": {"saudavel": False},
                    "sessao": {"saudavel": True},
                },
            }

        resultado = iniciar_validado(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: self.fail("nao iniciar"),
            iniciar_monitor_fn=lambda _pasta: self.fail("nao iniciar"),
            preflight_fn=preflight,
        )
        self.assertEqual(resultado["estado"], "inicio_recusado")
        self.assertEqual(resultado["falhas_preflight"], ["banco"])
        self.assertTrue(
            opcoes_preflight["permitir_coleta_parada_para_reinicio"]
        )

    def test_falhas_preflight_omitem_alerta_contido_para_reinicio(self):
        resultado = iniciar_validado(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: self.fail("nao iniciar"),
            iniciar_monitor_fn=lambda _pasta: self.fail("nao iniciar"),
            preflight_fn=lambda *_args, **_opcoes: {
                "pronto_para_reinicio": False,
                "verificacoes": {
                    "backup": {"saudavel": False},
                    "integridade_telegram": {
                        "saudavel": False,
                        "saudavel_para_reinicio": True,
                    },
                },
            },
        )

        self.assertEqual(resultado["falhas_preflight"], ["backup"])

    def test_esquema_atual_reconcilia_backup_diario_antes_preflight(self):
        caminho_banco = self.pasta / "monitor_packball.db"
        banco = BancoMonitor(caminho_banco)
        banco.fechar()
        agora = datetime(2026, 8, 2, 8, 15, 0)

        resultado = preparar_banco_para_preflight(
            self.pasta,
            agora=agora,
            verificar_trava=lambda _caminho: False,
        )

        self.assertTrue(resultado["saudavel"], resultado)
        self.assertEqual(resultado["estado"], "esquema_atual")
        self.assertTrue(resultado["backup_diario_reconciliado"])
        self.assertTrue(resultado["backup_diario_regenerado"])
        self.assertTrue(
            verificar_arquivo_backup(resultado["backup_diario"])["valido"]
        )

    def test_prepara_migracao_aditiva_com_dois_backups_verificados(self):
        caminho_banco = self.pasta / "monitor_packball.db"
        banco = BancoMonitor(caminho_banco)
        banco.fechar()
        conexao = sqlite3.connect(caminho_banco)
        try:
            conexao.execute(
                "ALTER TABLE notificacoes_operacionais DROP COLUMN resumo"
            )
            conexao.commit()
        finally:
            conexao.close()

        resultado = preparar_banco_para_preflight(
            self.pasta,
            agora=datetime(2026, 8, 2, 0, 15, 0),
            verificar_trava=lambda _caminho: False,
        )

        self.assertTrue(resultado["saudavel"], resultado)
        self.assertTrue(resultado["necessaria"])
        self.assertEqual(resultado["estado"], "migracao_aplicada")
        self.assertTrue(
            verificar_backup_pre_migracao(
                resultado["backup_pre_migracao"]
            )["valido"]
        )
        self.assertTrue(
            verificar_arquivo_backup(resultado["backup_diario"])["valido"]
        )
        conexao = sqlite3.connect(caminho_banco)
        try:
            colunas = {
                item[1]
                for item in conexao.execute(
                    "PRAGMA table_info(notificacoes_operacionais)"
                )
            }
        finally:
            conexao.close()
        self.assertIn("resumo", colunas)

    def test_recupera_banco_corrompido_e_preserva_evidencia_forense(self):
        agora = datetime(2026, 8, 9, 15, 30, 0)
        backup = self._criar_backup_valido(agora, "backup-valido")
        caminho_banco = self.pasta / "monitor_packball.db"
        caminho_banco.write_bytes(b"banco-corrompido")
        Path(f"{caminho_banco}-wal").write_bytes(b"wal-corrompido")
        Path(f"{caminho_banco}-shm").write_bytes(b"shm-corrompido")

        resultado = preparar_banco_para_preflight(
            self.pasta,
            agora=agora,
            verificar_trava=lambda _caminho: False,
        )

        self.assertTrue(resultado["saudavel"], resultado)
        self.assertEqual(resultado["estado"], "banco_recuperado_backup")
        self.assertEqual(resultado["recuperacao"]["backup"], backup.name)
        conexao = sqlite3.connect(caminho_banco)
        try:
            valor = conexao.execute(
                "SELECT valor FROM marcador_recuperacao"
            ).fetchone()[0]
        finally:
            conexao.close()
        self.assertEqual(valor, "backup-valido")
        quarentena = self.pasta / "backups" / resultado["recuperacao"][
            "quarentena"
        ]
        self.assertEqual(quarentena.read_bytes(), b"banco-corrompido")
        self.assertEqual(
            Path(f"{quarentena}-wal").read_bytes(), b"wal-corrompido"
        )
        self.assertGreater(Path(f"{quarentena}-shm").stat().st_size, 0)
        self.assertTrue(
            (self.pasta / "recuperacao_banco_estado.json").exists()
        )

    def test_recuperacao_pula_backup_recente_com_checksum_invalido(self):
        antigo = self._criar_backup_valido(
            datetime(2026, 8, 9, 6, 0, 0), "antigo-valido"
        )
        novo = self._criar_backup_valido(
            datetime(2026, 8, 9, 12, 0, 0), "novo"
        )
        with novo.open("ab") as arquivo:
            arquivo.write(b"adulterado")
        caminho_banco = self.pasta / "monitor_packball.db"
        caminho_banco.write_bytes(b"banco-corrompido")

        resultado = preparar_banco_para_preflight(
            self.pasta,
            agora=datetime(2026, 8, 9, 15, 31, 0),
            verificar_trava=lambda _caminho: False,
        )

        self.assertTrue(resultado["saudavel"], resultado)
        self.assertEqual(resultado["recuperacao"]["backup"], antigo.name)
        conexao = sqlite3.connect(caminho_banco)
        try:
            valor = conexao.execute(
                "SELECT valor FROM marcador_recuperacao"
            ).fetchone()[0]
        finally:
            conexao.close()
        self.assertEqual(valor, "antigo-valido")

    def test_nao_recupera_banco_corrompido_com_processos_ativos(self):
        self._criar_backup_valido(
            datetime(2026, 8, 9, 12, 0, 0), "backup-valido"
        )
        caminho_banco = self.pasta / "monitor_packball.db"
        caminho_banco.write_bytes(b"banco-corrompido")

        resultado = preparar_banco_para_preflight(
            self.pasta,
            verificar_trava=lambda _caminho: True,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(
            resultado["estado"], "recuperacao_adiada_processos_ativos"
        )
        self.assertEqual(caminho_banco.read_bytes(), b"banco-corrompido")
        self.assertFalse(list(
            (self.pasta / "backups").glob("quarentena_corrompido_*.db")
        ))

    def test_banco_ausente_recupera_backup_em_vez_de_criar_base_vazia(self):
        backup = self._criar_backup_valido(
            datetime(2026, 8, 9, 12, 0, 0), "historico-existente"
        )
        caminho_banco = self.pasta / "monitor_packball.db"

        resultado = preparar_banco_para_preflight(
            self.pasta,
            agora=datetime(2026, 8, 9, 15, 32, 0),
            verificar_trava=lambda _caminho: False,
        )

        self.assertTrue(resultado["saudavel"], resultado)
        self.assertEqual(resultado["estado"], "banco_recuperado_backup")
        self.assertEqual(resultado["recuperacao"]["backup"], backup.name)
        self.assertIsNone(resultado["recuperacao"]["quarentena"])
        conexao = sqlite3.connect(caminho_banco)
        try:
            valor = conexao.execute(
                "SELECT valor FROM marcador_recuperacao"
            ).fetchone()[0]
        finally:
            conexao.close()
        self.assertEqual(valor, "historico-existente")

    def test_banco_ausente_com_backups_invalidos_bloqueia_inicio(self):
        pasta_backups = self.pasta / "backups"
        pasta_backups.mkdir()
        (pasta_backups / "periodico_20260809_12.db").write_bytes(
            b"backup-invalido"
        )

        resultado = preparar_banco_para_preflight(
            self.pasta,
            verificar_trava=lambda _caminho: False,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(
            resultado["estado"], "banco_ausente_sem_backup_valido"
        )
        self.assertFalse((self.pasta / "monitor_packball.db").exists())

    def test_banco_ausente_com_processos_ativos_nao_tenta_recuperar(self):
        self._criar_backup_valido(
            datetime(2026, 8, 9, 12, 0, 0), "backup-valido"
        )

        resultado = preparar_banco_para_preflight(
            self.pasta,
            verificar_trava=lambda _caminho: True,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(
            resultado["estado"], "recuperacao_adiada_processos_ativos"
        )
        self.assertFalse((self.pasta / "monitor_packball.db").exists())

    def test_banco_corrompido_sem_backup_valido_permanece_preservado(self):
        caminho_banco = self.pasta / "monitor_packball.db"
        caminho_banco.write_bytes(b"banco-corrompido-sem-backup")

        resultado = preparar_banco_para_preflight(
            self.pasta,
            verificar_trava=lambda _caminho: False,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "banco_corrompido")
        self.assertEqual(
            caminho_banco.read_bytes(), b"banco-corrompido-sem-backup"
        )

    def test_fluxo_continuo_detecta_para_e_restaura_banco_corrompido(self):
        agora = datetime(2026, 8, 9, 16, 0, 0)
        backup = self._criar_backup_valido(agora, "fluxo-restaurado")
        caminho_banco = self.pasta / "monitor_packball.db"
        caminho_banco.write_bytes(b"corrupcao-detectada-em-operacao")

        deteccao = acionar_recuperacao_banco_ativo(
            caminho_banco,
            self.pasta,
            agora=agora,
            enviar=lambda _texto: True,
        )
        manutencao = ler_modo_manutencao(self.pasta)
        restauracao = preparar_banco_para_preflight(
            self.pasta,
            agora=agora + timedelta(minutes=1),
            verificar_trava=lambda _caminho: False,
        )

        self.assertTrue(deteccao["recuperacao_necessaria"])
        self.assertTrue(deteccao["manutencao_solicitada"])
        self.assertTrue(manutencao["ativo"])
        self.assertEqual(
            manutencao["motivo"], "recuperacao_banco_automatica"
        )
        self.assertTrue(restauracao["saudavel"])
        self.assertEqual(restauracao["estado"], "banco_recuperado_backup")
        self.assertEqual(restauracao["recuperacao"]["backup"], backup.name)
        conexao = sqlite3.connect(caminho_banco)
        try:
            valor = conexao.execute(
                "SELECT valor FROM marcador_recuperacao"
            ).fetchone()[0]
        finally:
            conexao.close()
        self.assertEqual(valor, "fluxo-restaurado")

    def test_nao_migra_banco_enquanto_componentes_estao_ativos(self):
        caminho_banco = self.pasta / "monitor_packball.db"
        banco = BancoMonitor(caminho_banco)
        banco.fechar()
        conexao = sqlite3.connect(caminho_banco)
        try:
            conexao.execute(
                "ALTER TABLE notificacoes_operacionais DROP COLUMN resumo"
            )
            conexao.commit()
        finally:
            conexao.close()

        resultado = preparar_banco_para_preflight(
            self.pasta, verificar_trava=lambda _caminho: True
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(
            resultado["estado"], "migracao_adiada_processos_ativos"
        )
        self.assertFalse((self.pasta / "backups").exists())

    def test_inicio_recusa_falha_na_preparacao_sem_rodar_preflight(self):
        resultado = iniciar_validado(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: self.fail("nao iniciar"),
            iniciar_monitor_fn=lambda _pasta: self.fail("nao iniciar"),
            preflight_fn=lambda *_args, **_kwargs: self.fail(
                "nao executar preflight"
            ),
            preparar_banco_fn=lambda _pasta: {
                "saudavel": False,
                "estado": "migracao_incompleta",
            },
        )

        self.assertEqual(resultado["estado"], "inicio_recusado")
        self.assertEqual(resultado["motivo"], "preparacao_banco_falhou")

    def test_inicio_renova_sessao_expirada_uma_vez_e_repete_preflight(self):
        chamadas_preflight = []
        renovacoes = []

        def preflight(*_args, **_opcoes):
            chamadas_preflight.append(True)
            if len(chamadas_preflight) == 1:
                return {
                    "pronto_para_reinicio": False,
                    "verificacoes": {
                        "sessao_packball": {
                            "saudavel": False,
                            "motivo": "sessao_expirada",
                        },
                        "acesso_packball": {"saudavel": True},
                    },
                }
            return {
                "pronto_para_reinicio": True,
                "verificacoes": {
                    "sessao_packball": {"saudavel": True},
                    "acesso_packball": {"saudavel": True},
                },
            }

        resultado = iniciar_validado(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: 101,
            iniciar_monitor_fn=lambda _pasta: 202,
            verificar_pid=lambda _pid: False,
            preflight_fn=preflight,
            renovar_sessao_fn=lambda: renovacoes.append(True),
        )

        self.assertEqual(len(chamadas_preflight), 2)
        self.assertEqual(renovacoes, [True])
        self.assertTrue(resultado["sessao_renovada"])
        self.assertEqual(resultado["monitor"]["pid"], 202)

    def test_falha_ao_renovar_sessao_recusa_sem_criar_processos(self):
        resultado = iniciar_validado(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: self.fail("nao iniciar"),
            iniciar_monitor_fn=lambda _pasta: self.fail("nao iniciar"),
            preflight_fn=lambda *_args, **_opcoes: {
                "pronto_para_reinicio": False,
                "verificacoes": {
                    "sessao_packball": {
                        "saudavel": False,
                        "motivo": "sessao_expirada",
                    },
                    "acesso_packball": {"saudavel": True},
                },
            },
            renovar_sessao_fn=lambda: (_ for _ in ()).throw(
                RuntimeError("falha")
            ),
        )

        self.assertEqual(resultado["estado"], "inicio_recusado")
        self.assertEqual(resultado["motivo"], "renovacao_sessao_falhou")
        self.assertEqual(resultado["erro_renovacao"], "RuntimeError")
        self.assertEqual(resultado["causa_renovacao"], "RuntimeError")

    def test_autorretomada_preserva_manutencao_manual(self):
        solicitar_modo_manutencao(self.pasta, "teste")
        resultado = iniciar_validado(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: self.fail("nao iniciar"),
            iniciar_monitor_fn=lambda _pasta: self.fail("nao iniciar"),
            preflight_fn=lambda *_args, **_kwargs: self.fail(
                "nao executar preflight em manutencao"
            ),
        )
        self.assertEqual(resultado["motivo"], "modo_manutencao_ativo")
        self.assertTrue((self.pasta / "modo_manutencao.json").exists())

    def test_manutencao_criada_durante_preflight_nao_e_apagada(self):
        def preflight(*_args, **_kwargs):
            solicitar_modo_manutencao(
                self.pasta, "solicitada_durante_preflight"
            )
            return {
                "pronto_para_reinicio": True,
                "verificacoes": {"banco": {"saudavel": True}},
            }

        resultado = iniciar_validado(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: self.fail("nao iniciar"),
            iniciar_monitor_fn=lambda _pasta: self.fail("nao iniciar"),
            verificar_pid=lambda _pid: False,
            preflight_fn=preflight,
        )

        self.assertEqual(resultado["estado"], "inicio_recusado")
        self.assertEqual(resultado["motivo"], "modo_manutencao_ativo")
        self.assertEqual(
            resultado["monitor"]["estado"], "manutencao_preservada"
        )
        self.assertTrue((self.pasta / "modo_manutencao.json").exists())

    def test_retomada_manual_so_libera_manutencao_apos_preflight(self):
        solicitar_modo_manutencao(self.pasta, "teste")
        resultado = iniciar_validado(
            self.pasta,
            iniciar_watchdog_fn=lambda _pasta: 101,
            iniciar_monitor_fn=lambda _pasta: 202,
            verificar_pid=lambda _pid: False,
            permitir_retomada_manutencao=True,
            preflight_fn=lambda *_args, **_kwargs: {
                "pronto_para_reinicio": True,
                "verificacoes": {"banco": {"saudavel": True}},
            },
        )
        self.assertEqual(resultado["monitor"]["pid"], 202)
        self.assertFalse((self.pasta / "modo_manutencao.json").exists())

    def test_falha_ao_lancar_componente_restaura_manutencao(self):
        solicitar_modo_manutencao(self.pasta, "teste")

        resultado = iniciar_validado(
            self.pasta,
            iniciar_monitor_fn=lambda _pasta: (_ for _ in ()).throw(
                RuntimeError("falha de abertura")
            ),
            iniciar_watchdog_fn=lambda _pasta: self.fail(
                "watchdog nao deveria iniciar"
            ),
            verificar_pid=lambda _pid: False,
            permitir_retomada_manutencao=True,
            preparar_banco_fn=lambda _pasta: {
                "saudavel": True,
                "estado": "sem_migracao",
            },
            preflight_fn=lambda *_args, **_kwargs: {
                "pronto_para_reinicio": True,
                "verificacoes": {"banco": {"saudavel": True}},
            },
        )

        self.assertEqual(resultado["estado"], "inicio_falhou")
        self.assertEqual(
            resultado["motivo"], "falha_lancamento_componentes"
        )
        self.assertEqual(resultado["erro_inicio"], "RuntimeError")
        self.assertTrue(resultado["rollback_manutencao"]["aplicado"])
        manutencao = ler_modo_manutencao(self.pasta)
        self.assertTrue(manutencao["ativo"])
        self.assertEqual(
            manutencao["motivo"], "rollback_inicio_instavel"
        )

    @patch("iniciar_sistema.Observabilidade")
    def test_rollback_permanece_aplicado_se_observabilidade_falhar(
        self, observabilidade_mock
    ):
        observabilidade_mock.return_value.modo_manutencao.side_effect = (
            ValueError("falha secundaria")
        )
        resultado = {}

        rollback = _restaurar_manutencao_apos_falha_inicio(
            self.pasta, resultado, "falha_teste"
        )

        self.assertTrue(rollback["aplicado"])
        self.assertEqual(rollback["observabilidade"], "indisponivel")
        self.assertEqual(rollback["erro_observabilidade"], "ValueError")
        self.assertTrue(ler_modo_manutencao(self.pasta)["ativo"])

    def test_confirma_processos_recem_iniciados_apos_janela_estavel(self):
        registrar_estado(
            self.pasta / "monitor_processo.json", "ativo", pid=202
        )
        registrar_estado(
            self.pasta / "watchdog_processo.json", "ativo", pid=101
        )
        instante = [0.0]
        resultado = confirmar_inicio_estavel(
            self.pasta,
            {
                "monitor": {"estado": "iniciado", "pid": 404},
                "watchdog": {"estado": "iniciado", "pid": 303},
            },
            timeout_segundos=5,
            estabilidade_segundos=2,
            intervalo_segundos=1,
            verificar_pid=lambda pid: pid in (101, 202),
            verificar_trava=lambda _caminho: True,
            relogio=lambda: instante[0],
            dormir=lambda segundos: instante.__setitem__(
                0, instante[0] + segundos
            ),
        )

        self.assertTrue(resultado["confirmacao_inicio"]["saudavel"])
        self.assertEqual(
            resultado["confirmacao_inicio"]["estado"], "estavel"
        )
        self.assertEqual(
            set(resultado["confirmacao_inicio"]["componentes"]),
            {"monitor", "watchdog"},
        )

    def test_falha_explicita_interrompe_confirmacao_e_redige_segredo(self):
        registrar_estado(
            self.pasta / "monitor_processo.json",
            "falha",
            pid=202,
            erro="PermissionError",
            mensagem="Playwright negado token=segredo",
        )
        resultado = confirmar_inicio_estavel(
            self.pasta,
            {
                "monitor": {"estado": "iniciado", "pid": 404},
                "watchdog": {"estado": "ja_ativo", "pid": 101},
            },
            verificar_pid=lambda _pid: False,
            verificar_trava=lambda _caminho: False,
        )

        self.assertEqual(resultado["estado"], "inicio_falhou")
        self.assertEqual(
            resultado["motivo"], "processo_falhou_na_inicializacao"
        )
        diagnostico = resultado["confirmacao_inicio"]["componentes"][
            "monitor"
        ]
        self.assertEqual(diagnostico["erro"], "PermissionError")
        self.assertNotIn("segredo", diagnostico["mensagem"])
        self.assertTrue(resultado["rollback_manutencao"]["aplicado"])
        self.assertTrue(ler_modo_manutencao(self.pasta)["ativo"])

    def test_confirmacao_expira_quando_processo_nao_adquire_trava(self):
        instante = [0.0]
        resultado = confirmar_inicio_estavel(
            self.pasta,
            {
                "monitor": {"estado": "iniciado", "pid": 404},
                "watchdog": {"estado": "ja_ativo", "pid": 101},
            },
            timeout_segundos=2,
            estabilidade_segundos=1,
            intervalo_segundos=1,
            verificar_pid=lambda _pid: False,
            verificar_trava=lambda _caminho: False,
            relogio=lambda: instante[0],
            dormir=lambda segundos: instante.__setitem__(
                0, instante[0] + segundos
            ),
        )

        self.assertEqual(resultado["estado"], "inicio_falhou")
        self.assertEqual(resultado["motivo"], "confirmacao_inicio_expirou")
        self.assertEqual(
            resultado["confirmacao_inicio"]["estado"], "timeout"
        )
        self.assertTrue(resultado["rollback_manutencao"]["aplicado"])
        self.assertTrue(ler_modo_manutencao(self.pasta)["ativo"])

    def test_componentes_ja_ativos_nao_criam_espera(self):
        resultado = confirmar_inicio_estavel(
            self.pasta,
            {
                "monitor": {"estado": "ja_ativo", "pid": 202},
                "watchdog": {"estado": "ja_ativo", "pid": 101},
            },
            dormir=lambda _segundos: self.fail("não deveria aguardar"),
        )

        self.assertEqual(
            resultado["confirmacao_inicio"]["estado"], "nao_necessaria"
        )


if __name__ == "__main__":
    unittest.main()
