import os
import sqlite3
import shutil
import unittest
from datetime import datetime
from pathlib import Path

from backup_banco import BackupBanco
from banco import BancoMonitor
from compactar_backups_legados import executar_compactacao
from controle_sistema import solicitar_modo_manutencao


class CompactarBackupsLegadosTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_compactar_backups_legados"
        shutil.rmtree(self.pasta, ignore_errors=True)
        self.pasta.mkdir()
        banco_path = self.pasta / "origem.db"
        BancoMonitor(banco_path).fechar()
        origem = sqlite3.connect(banco_path)
        try:
            gerenciador = BackupBanco(self.pasta / "backups")
            gerenciador.criar_pre_migracao(
                origem, datetime(2026, 9, 10, 10, 0)
            )
            gerenciador.criar_pre_reinicio(
                origem, datetime(2026, 9, 10, 11, 0)
            )
        finally:
            origem.close()

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_recusa_se_monitor_ainda_esta_ativo(self):
        solicitar_modo_manutencao(self.pasta)
        resultado = executar_compactacao(
            self.pasta, maximo=2,
            verificar_trava=lambda caminho: "monitor" in caminho.name,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(
            "manutencao_segura_necessaria", resultado["estado"]
        )
        self.assertEqual(["monitor"], resultado["processos_ativos"])

    def test_compacta_lote_limitado_em_manutencao(self):
        solicitar_modo_manutencao(self.pasta)
        resultado = executar_compactacao(
            self.pasta, maximo=2, verificar_trava=lambda _: False
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual("concluida", resultado["estado"])
        self.assertEqual(2, resultado["executados"])
        self.assertEqual(0, resultado["restantes"])
        self.assertEqual(
            2, len(list((self.pasta / "backups").glob("*.db.gz")))
        )

    def test_preserva_incompativel_e_continua_com_os_validos(self):
        invalido = self.pasta / "backups" / "monitor_20000101.db"
        conexao = sqlite3.connect(invalido)
        try:
            conexao.execute("CREATE TABLE legado (id INTEGER PRIMARY KEY)")
            conexao.commit()
        finally:
            conexao.close()
        os.utime(invalido, (1, 1))
        solicitar_modo_manutencao(self.pasta)

        resultado = executar_compactacao(
            self.pasta, maximo=3, verificar_trava=lambda _: False
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(3, resultado["executados"])
        self.assertEqual(0, resultado["restantes"])
        self.assertEqual(
            "concluida_com_incompativeis_preservados",
            resultado["estado"],
        )
        self.assertTrue(invalido.exists())
        self.assertTrue(Path(
            f"{invalido}.compactacao-incompativel.json"
        ).exists())
        self.assertEqual(
            2, len(list((self.pasta / "backups").glob("*.db.gz")))
        )


if __name__ == "__main__":
    unittest.main()
