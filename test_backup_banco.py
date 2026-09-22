import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from backup_banco import (
    BackupBanco,
    caminho_manifesto,
    comparar_dispositivos_armazenamento,
    verificar_backup,
    verificar_backup_espelho,
    verificar_backup_pre_migracao,
)
from banco import BancoMonitor


class BackupBancoTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_backups"
        self.pasta.mkdir(exist_ok=True)
        self.espelho = Path.cwd() / ".teste_backups_espelho"
        self.espelho.mkdir(exist_ok=True)
        for arquivo in self.pasta.iterdir():
            arquivo.unlink()
        for arquivo in self.espelho.iterdir():
            arquivo.unlink()
        self.banco_origem = BancoMonitor(":memory:")
        self.origem = self.banco_origem.conexao
        self.origem.execute(
            "INSERT INTO metadados(chave, valor) VALUES ('teste', 'ok')"
        )
        self.origem.commit()

    def tearDown(self):
        self.banco_origem.fechar()
        for arquivo in self.pasta.iterdir():
            arquivo.unlink()
        self.pasta.rmdir()
        for arquivo in self.espelho.iterdir():
            arquivo.unlink()
        self.espelho.rmdir()

    def test_replica_backup_em_espelho_e_audita_integridade(self):
        agora = datetime(2026, 7, 20, 10, 0)
        origem, _ = BackupBanco(
            self.pasta, pasta_espelho=self.espelho
        ).criar_diario(self.origem, agora)

        destino = self.espelho / origem.name
        self.assertTrue(verificar_backup(destino)["valido"])
        auditoria = verificar_backup_espelho(
            self.pasta, self.espelho, agora=agora
        )
        self.assertTrue(auditoria["configurado"])
        self.assertTrue(auditoria["saudavel"])
        self.assertFalse(auditoria["fora_dispositivo"])
        self.assertTrue(auditoria["dispositivos"]["comparavel"])

    def test_particoes_com_letras_diferentes_no_mesmo_disco_nao_sao_externas(self):
        with patch(
            "backup_banco.identificar_dispositivo_armazenamento",
            side_effect=[
                {
                    "saudavel": True,
                    "identificador": "device:7:0",
                    "raiz": "C:\\",
                },
                {
                    "saudavel": True,
                    "identificador": "device:7:0",
                    "raiz": "D:\\",
                },
            ],
        ):
            resultado = comparar_dispositivos_armazenamento(
                "C:\\backups", "D:\\espelho"
            )

        self.assertTrue(resultado["comparavel"])
        self.assertFalse(resultado["fora_dispositivo"])

    def test_dispositivo_fisico_distinto_e_reconhecido(self):
        with patch(
            "backup_banco.identificar_dispositivo_armazenamento",
            side_effect=[
                {
                    "saudavel": True,
                    "identificador": "device:7:0",
                    "raiz": "C:\\",
                },
                {
                    "saudavel": True,
                    "identificador": "device:7:1",
                    "raiz": "F:\\",
                },
            ],
        ):
            resultado = comparar_dispositivos_armazenamento(
                "C:\\backups", "F:\\espelho"
            )

        self.assertTrue(resultado["comparavel"])
        self.assertTrue(resultado["fora_dispositivo"])

    def test_auditoria_nao_confia_em_marcacao_legada_da_letra_da_unidade(self):
        agora = datetime(2026, 7, 20, 10, 0)
        origem, _ = BackupBanco(
            self.pasta, pasta_espelho=self.espelho
        ).criar_diario(self.origem, agora)
        estado_path = self.pasta / "backup_espelho_estado.json"
        estado = json.loads(estado_path.read_text(encoding="utf-8"))
        estado["fora_dispositivo"] = True
        estado_path.write_text(json.dumps(estado), encoding="utf-8")

        auditoria = verificar_backup_espelho(
            self.pasta, self.espelho, agora=agora
        )

        self.assertFalse(auditoria["fora_dispositivo"])
        self.assertFalse(auditoria["pronto_profissional"])

    def test_espelho_corrompido_nao_e_considerado_saudavel(self):
        agora = datetime(2026, 7, 20, 10, 0)
        origem, _ = BackupBanco(
            self.pasta, pasta_espelho=self.espelho
        ).criar_diario(self.origem, agora)
        (self.espelho / origem.name).write_bytes(b"corrompido")

        auditoria = verificar_backup_espelho(
            self.pasta, self.espelho, agora=agora
        )
        self.assertFalse(auditoria["saudavel"])
        self.assertFalse(auditoria["integridade"]["valido"])
        self.assertTrue(auditoria["saudavel_para_reinicio"])

    def test_espelho_nao_configurado_nao_bloqueia_reinicio(self):
        auditoria = verificar_backup_espelho(self.pasta)

        self.assertFalse(auditoria["configurado"])
        self.assertTrue(auditoria["saudavel_para_reinicio"])
        self.assertFalse(auditoria["pronto_profissional"])

    def test_replica_existente_nao_e_copiada_novamente(self):
        agora = datetime(2026, 7, 20, 10, 0)
        backup = BackupBanco(self.pasta, pasta_espelho=self.espelho)
        backup.criar_diario(self.origem, agora)

        with patch("backup_banco.shutil.copy2") as copiar:
            _, criado = backup.criar_diario(
                self.origem, agora + timedelta(minutes=5)
            )

        self.assertFalse(criado)
        copiar.assert_not_called()
        estado = json.loads(
            (self.pasta / "backup_espelho_estado.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(estado["estado"], "replica_existente_confirmada")

    def test_retencao_do_espelho_acompanha_limites_locais(self):
        backup = BackupBanco(
            self.pasta,
            pasta_espelho=self.espelho,
            manter_periodicos=1,
        )
        backup.criar_periodico(self.origem, datetime(2026, 7, 20, 1, 0))
        backup.criar_periodico(self.origem, datetime(2026, 7, 20, 7, 0))

        self.assertEqual(len(list(self.espelho.glob("periodico_*.db"))), 1)

    def test_cria_backup_consistente_uma_vez_por_dia(self):
        backup = BackupBanco(self.pasta)
        agora = datetime(2026, 7, 20, 10, 0)
        caminho, criado = backup.criar_diario(self.origem, agora)
        _, criado_novamente = backup.criar_diario(self.origem, agora)
        self.assertTrue(criado)
        self.assertFalse(criado_novamente)
        verificacao = verificar_backup(caminho)
        self.assertTrue(verificacao["valido"])
        self.assertTrue(verificacao["checksum_confere"])
        self.assertTrue(verificacao["modelos_sombra_integros"])
        self.assertTrue(caminho_manifesto(caminho).exists())
        copia = sqlite3.connect(caminho)
        try:
            self.assertEqual(
                copia.execute(
                    "SELECT valor FROM metadados WHERE chave='teste'"
                ).fetchone()[0],
                "ok",
            )
        finally:
            copia.close()

    def test_remove_backup_fora_da_retencao(self):
        backup = BackupBanco(self.pasta, retencao_dias=14)
        antigo = datetime(2026, 6, 1)
        backup.criar_diario(self.origem, antigo)
        backup.criar_diario(self.origem, antigo + timedelta(days=30))
        self.assertFalse((self.pasta / "monitor_20260601.db").exists())
        self.assertFalse(
            caminho_manifesto(self.pasta / "monitor_20260601.db").exists()
        )

    def test_backup_diario_existente_reconcilia_retencao_interrompida(self):
        sem_limite = BackupBanco(self.pasta, retencao_dias=365)
        antigo = datetime(2026, 6, 1, 10, 0)
        atual = datetime(2026, 7, 1, 10, 0)
        sem_limite.criar_diario(self.origem, antigo)
        sem_limite.criar_diario(self.origem, atual)
        backup = BackupBanco(self.pasta, retencao_dias=14)

        _, criado = backup.criar_diario(
            self.origem, atual + timedelta(minutes=5)
        )

        self.assertFalse(criado)
        self.assertFalse((self.pasta / "monitor_20260601.db").exists())
        self.assertTrue((self.pasta / "monitor_20260701.db").exists())
        self.assertTrue(backup.auditar_retencao(atual)["aplicacao_automatica"])

    def test_retencao_pre_migracao_usa_data_e_pode_ser_auditada_sem_apagar(self):
        antigo = self.pasta / "pre_migracao_z_antigo.db"
        novo = self.pasta / "pre_migracao_a_novo.db"
        antigo.write_bytes(b"antigo")
        novo.write_bytes(b"novo")
        caminho_manifesto(antigo).write_text(
            json.dumps({"criado_em": "2026-07-20T10:00:00"}),
            encoding="utf-8",
        )
        caminho_manifesto(novo).write_text(
            json.dumps({"criado_em": "2026-07-21T10:00:00"}),
            encoding="utf-8",
        )
        backup = BackupBanco(self.pasta, manter_pre_reinicio=1)

        auditoria = backup.auditar_retencao(
            datetime(2026, 7, 22, 10, 0)
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["quantidade"], 1)
        self.assertEqual(
            auditoria["candidatos_remocao"][0]["arquivo"], antigo.name
        )
        self.assertTrue(antigo.exists())
        self.assertTrue(novo.exists())

        removidos = backup._remover_pre_migracao_excedentes()
        self.assertEqual(removidos, [antigo])
        self.assertFalse(antigo.exists())
        self.assertTrue(novo.exists())

    def test_retencao_preserva_ponto_historico_protegido(self):
        protegido = self.pasta / "pre_migracao_linhagem.db"
        rotina_antiga = self.pasta / "pre_migracao_rotina_antiga.db"
        rotina_nova = self.pasta / "pre_migracao_rotina_nova.db"
        for arquivo in (protegido, rotina_antiga, rotina_nova):
            arquivo.write_bytes(arquivo.name.encode("utf-8"))
        caminho_manifesto(protegido).write_text(
            json.dumps({
                "criado_em": "2026-07-19T10:00:00",
                "protegido_retencao": True,
                "motivo_protecao": "marco_linhagem_regras",
            }),
            encoding="utf-8",
        )
        caminho_manifesto(rotina_antiga).write_text(
            json.dumps({"criado_em": "2026-07-20T10:00:00"}),
            encoding="utf-8",
        )
        caminho_manifesto(rotina_nova).write_text(
            json.dumps({"criado_em": "2026-07-21T10:00:00"}),
            encoding="utf-8",
        )
        backup = BackupBanco(self.pasta, manter_pre_reinicio=1)

        auditoria = backup.auditar_retencao(
            datetime(2026, 7, 22, 10, 0)
        )
        removidos = backup._remover_pre_migracao_excedentes()

        self.assertEqual(auditoria["protegidos"], 1)
        self.assertEqual(auditoria["quantidade"], 1)
        self.assertEqual(
            auditoria["candidatos_remocao"][0]["arquivo"],
            rotina_antiga.name,
        )
        self.assertEqual(removidos, [rotina_antiga])
        self.assertTrue(protegido.exists())
        self.assertTrue(rotina_nova.exists())

    def test_detecta_backup_corrompido(self):
        caminho = self.pasta / "monitor_20260720.db"
        caminho.write_bytes(b"nao e sqlite")
        verificacao = verificar_backup(caminho, criar_manifesto=True)
        self.assertFalse(verificacao["valido"])
        self.assertEqual(verificacao["motivo"], "integridade_sqlite_falhou")

    def test_recusa_sqlite_integro_com_esquema_incompleto(self):
        caminho = self.pasta / "monitor_20260720.db"
        conexao = sqlite3.connect(caminho)
        conexao.execute("CREATE TABLE partidas(id INTEGER PRIMARY KEY)")
        conexao.close()

        verificacao = verificar_backup(caminho, criar_manifesto=True)

        self.assertFalse(verificacao["valido"])
        self.assertEqual(
            verificacao["motivo"], "esquema_ou_relacoes_incompativeis"
        )
        self.assertIn("snapshots", verificacao["tabelas_ausentes"])
        self.assertFalse(caminho_manifesto(caminho).exists())

    def test_recusa_backup_com_chave_estrangeira_quebrada(self):
        caminho = self.pasta / "monitor_20260720.db"
        destino = sqlite3.connect(caminho)
        self.origem.backup(destino)
        destino.execute("PRAGMA foreign_keys=OFF")
        destino.execute(
            """
            INSERT INTO snapshots(partida_id, coletado_em)
            VALUES (999999, '2026-07-20T12:00:00')
            """
        )
        destino.commit()
        destino.close()

        verificacao = verificar_backup(caminho, criar_manifesto=True)

        self.assertFalse(verificacao["valido"])
        self.assertEqual(verificacao["violacoes_chaves_estrangeiras"], 1)
        self.assertEqual(
            verificacao["motivo"], "esquema_ou_relacoes_incompativeis"
        )

    def test_recusa_backup_sem_coluna_exigida_pelo_runtime(self):
        caminho = self.pasta / "monitor_20260720.db"
        destino = sqlite3.connect(caminho)
        self.origem.backup(destino)
        destino.execute("ALTER TABLE snapshots DROP COLUMN fontes_json")
        destino.commit()
        destino.close()

        verificacao = verificar_backup(caminho, criar_manifesto=True)

        self.assertFalse(verificacao["valido"])
        self.assertEqual(
            verificacao["colunas_ausentes"], {"snapshots": ["fontes_json"]}
        )
        self.assertEqual(
            verificacao["motivo"], "esquema_ou_relacoes_incompativeis"
        )

    def test_recusa_backup_com_ancora_longa_corrompida(self):
        caminho = self.pasta / "monitor_20260720.db"
        destino = sqlite3.connect(caminho)
        self.origem.backup(destino)
        destino.execute(
            "INSERT INTO metadados(chave, valor) VALUES (?, ?)",
            (
                "pontuacao_sombra:longa_ancora:"
                "pontuacao-longa-logistica-v2:sinais-v6:gol_ft",
                "{}",
            ),
        )
        destino.commit()
        destino.close()

        verificacao = verificar_backup(caminho, criar_manifesto=True)

        self.assertFalse(verificacao["valido"])
        self.assertEqual(
            verificacao["motivo"], "modelos_sombra_incompativeis"
        )
        self.assertFalse(verificacao["modelos_sombra_integros"])
        self.assertEqual(
            verificacao["modelos_sombra_inconsistentes"]["ancoras_longas"],
            ["gol_ft"],
        )
        self.assertFalse(caminho_manifesto(caminho).exists())

    def test_recusa_backup_com_modelo_contextual_corrompido(self):
        caminho = self.pasta / "monitor_20260720.db"
        destino = sqlite3.connect(caminho)
        self.origem.backup(destino)
        destino.execute(
            "INSERT INTO metadados(chave, valor) VALUES (?, ?)",
            (
                "pontuacao_sombra:regime-gols-contexto-logistica-v2:"
                "sinais-v6:gol_ft",
                '{"modelo":{},"modelo_hash":"invalido"}',
            ),
        )
        destino.commit()
        destino.close()

        verificacao = verificar_backup(caminho, criar_manifesto=True)

        self.assertFalse(verificacao["valido"])
        self.assertEqual(
            verificacao["motivo"], "modelos_sombra_incompativeis"
        )
        self.assertEqual(
            verificacao["modelos_sombra_inconsistentes"]["contextuais"],
            ["gol_ft"],
        )

    def test_regenera_backup_diario_incompativel_sem_apagar_o_antigo(self):
        agora = datetime(2026, 7, 20, 10, 0)
        caminho = self.pasta / "monitor_20260720.db"
        conexao = sqlite3.connect(caminho)
        conexao.execute("CREATE TABLE legado(id INTEGER PRIMARY KEY)")
        conexao.close()

        destino, regenerado = BackupBanco(self.pasta).criar_diario(
            self.origem, agora
        )

        self.assertTrue(regenerado)
        self.assertEqual(destino, caminho)
        self.assertTrue(verificar_backup(destino)["valido"])
        arquivados = list(self.pasta.glob("invalido_monitor_20260720_*.db"))
        self.assertEqual(len(arquivados), 1)
        legado = sqlite3.connect(arquivados[0])
        try:
            self.assertEqual(
                legado.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchone()[0],
                "legado",
            )
        finally:
            legado.close()

    def test_cria_backup_nomeado_antes_do_reinicio(self):
        backup = BackupBanco(self.pasta)
        agora = datetime(2026, 7, 20, 20, 55, 0)

        caminho = backup.criar_pre_reinicio(self.origem, agora)

        self.assertEqual(caminho.name, "pre_reinicio_20260720_205500.db")
        self.assertTrue(verificar_backup(caminho)["valido"])
        self.assertTrue(caminho_manifesto(caminho).exists())

    def test_preserva_esquema_antigo_antes_da_migracao(self):
        legado = sqlite3.connect(":memory:")
        try:
            legado.execute(
                "CREATE TABLE legado(id INTEGER PRIMARY KEY, valor TEXT)"
            )
            legado.execute(
                "INSERT INTO legado(valor) VALUES ('antes-da-migracao')"
            )
            legado.commit()

            caminho = BackupBanco(self.pasta).criar_pre_migracao(
                legado, datetime(2026, 7, 20, 20, 54, 0)
            )
        finally:
            legado.close()

        self.assertEqual(
            caminho.name, "pre_migracao_20260720_205400.db"
        )
        verificacao = verificar_backup_pre_migracao(caminho)
        self.assertTrue(verificacao["valido"])
        self.assertTrue(verificacao["checksum_confere"])
        self.assertFalse(verificar_backup(caminho)["valido"])
        copia = sqlite3.connect(caminho)
        try:
            self.assertEqual(
                copia.execute("SELECT valor FROM legado").fetchone()[0],
                "antes-da-migracao",
            )
        finally:
            copia.close()

    def test_conserva_apenas_cinco_backups_de_pre_reinicio(self):
        backup = BackupBanco(self.pasta, manter_pre_reinicio=5)
        inicio = datetime(2026, 7, 20, 20, 55, 0)
        criados = [
            backup.criar_pre_reinicio(
                self.origem, inicio + timedelta(seconds=indice)
            )
            for indice in range(6)
        ]

        restantes = sorted(self.pasta.glob("pre_reinicio_*.db"))
        self.assertEqual(len(restantes), 5)
        self.assertFalse(criados[0].exists())
        self.assertFalse(caminho_manifesto(criados[0]).exists())
        self.assertTrue(all(caminho_manifesto(item).exists() for item in restantes))

    def test_backup_periodico_usa_janela_de_seis_horas(self):
        backup = BackupBanco(self.pasta)
        primeiro, criado = backup.criar_periodico(
            self.origem, datetime(2026, 7, 20, 7, 15)
        )
        repetido, criado_repetido = backup.criar_periodico(
            self.origem, datetime(2026, 7, 20, 11, 59)
        )
        segundo, criado_segundo = backup.criar_periodico(
            self.origem, datetime(2026, 7, 20, 12, 0)
        )

        self.assertEqual(primeiro.name, "periodico_20260720_06.db")
        self.assertEqual(repetido, primeiro)
        self.assertEqual(segundo.name, "periodico_20260720_12.db")
        self.assertTrue(criado)
        self.assertFalse(criado_repetido)
        self.assertTrue(criado_segundo)
        self.assertTrue(verificar_backup(primeiro)["valido"])
        self.assertTrue(verificar_backup(segundo)["valido"])

    def test_backup_periodico_conserva_oito_pontos_recentes(self):
        backup = BackupBanco(self.pasta, manter_periodicos=8)
        inicio = datetime(2026, 7, 20, 0, 0)
        criados = [
            backup.criar_periodico(
                self.origem, inicio + timedelta(hours=6 * indice)
            )[0]
            for indice in range(9)
        ]

        restantes = sorted(self.pasta.glob("periodico_*.db"))
        self.assertEqual(len(restantes), 8)
        self.assertFalse(criados[0].exists())
        self.assertFalse(caminho_manifesto(criados[0]).exists())


if __name__ == "__main__":
    unittest.main()
