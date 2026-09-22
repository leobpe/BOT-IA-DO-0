import json
import shutil
import sqlite3
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from transferir_projeto import (
    auditar_transferencia,
    criar_pacote,
    verificar_pacote,
)


def processos_parados(_pasta, **_opcoes):
    return {
        "parado": True,
        "componentes": {
            "monitor": {"ativo": False},
            "watchdog": {"ativo": False},
            "pre_live": {"ativo": False},
        },
    }


def processos_ativos(_pasta, **_opcoes):
    return {
        "parado": False,
        "componentes": {
            "monitor": {"ativo": True},
            "watchdog": {"ativo": False},
            "pre_live": {"ativo": False},
        },
    }


class TransferirProjetoTest(unittest.TestCase):
    def setUp(self):
        self.raiz = Path.cwd() / f".teste_transferencia_{uuid4().hex}"
        self.raiz.mkdir()
        self.origem = self.raiz / "origem"
        self.origem.mkdir()
        for nome in (
            ".env", "packball_session.json", "requirements.lock.txt",
            "iniciar_sistema.py", "preflight_reinicio.py",
        ):
            (self.origem / nome).write_text(nome, encoding="utf-8")
        with closing(sqlite3.connect(
            self.origem / "monitor_packball.db"
        )) as conexao:
            conexao.execute("CREATE TABLE historico (valor TEXT)")
            conexao.execute("INSERT INTO historico VALUES ('preservado')")
            conexao.commit()
        with closing(sqlite3.connect(
            self.origem / "pre_live.db"
        )) as conexao:
            conexao.execute("CREATE TABLE bilhetes (valor TEXT)")
            conexao.execute("INSERT INTO bilhetes VALUES ('prospectivo')")
            conexao.commit()

    def tearDown(self):
        shutil.rmtree(self.raiz, ignore_errors=True)

    def test_auditoria_recusa_processos_ativos(self):
        resultado = auditar_transferencia(
            self.origem, verificar_processos_fn=processos_ativos
        )
        self.assertFalse(resultado["pronto"])
        self.assertFalse(resultado["processos"]["parado"])

    def test_pacote_preserva_banco_e_exclui_estados_transitorios(self):
        (self.origem / "monitor_instancia.lock").write_text("0")
        (self.origem / "monitor_packball.db-wal").write_bytes(b"temporario")
        (self.origem / "pre_live.db-wal").write_bytes(b"temporario")
        (self.origem / "pre_live_processo.json").write_text("{}")
        (self.origem / "codigo.py").write_text("print('ok')")
        (self.origem / ".venv").mkdir()
        (self.origem / ".venv" / "python.exe").write_bytes(b"nao copiar")
        destino = self.raiz / "pacote"
        manifesto = criar_pacote(
            self.origem,
            destino,
            agora=datetime(2026, 8, 9, 15, 0),
            verificar_processos_fn=processos_parados,
        )
        self.assertTrue((destino / "codigo.py").exists())
        self.assertTrue((destino / ".env").exists())
        self.assertFalse((destino / ".venv").exists())
        self.assertFalse((destino / "monitor_instancia.lock").exists())
        self.assertFalse((destino / "monitor_packball.db-wal").exists())
        self.assertFalse((destino / "pre_live.db-wal").exists())
        self.assertFalse((destino / "pre_live_processo.json").exists())
        with closing(sqlite3.connect(
            destino / "monitor_packball.db"
        )) as conexao:
            valor = conexao.execute("SELECT valor FROM historico").fetchone()[0]
        self.assertEqual(valor, "preservado")
        with closing(sqlite3.connect(
            destino / "pre_live.db"
        )) as conexao:
            valor_pre_live = conexao.execute(
                "SELECT valor FROM bilhetes"
            ).fetchone()[0]
        self.assertEqual(valor_pre_live, "prospectivo")
        self.assertEqual(manifesto["banco"]["quick_check"], ["ok"])
        self.assertEqual(
            manifesto["bancos"]["pre_live.db"]["quick_check"], ["ok"]
        )
        gravado = json.loads(
            (destino / "manifesto_transferencia.json").read_text("utf-8")
        )
        self.assertEqual(gravado["versao"], "transferencia-packball-v2")
        self.assertGreater(gravado["total_arquivos"], 0)

    def test_destino_dentro_da_origem_e_recusado(self):
        with self.assertRaises(ValueError):
            criar_pacote(
                self.origem,
                self.origem / "pacote",
                verificar_processos_fn=processos_parados,
            )

    def test_arquivo_obrigatorio_ausente_e_recusado(self):
        (self.origem / ".env").unlink()
        resultado = auditar_transferencia(
            self.origem, verificar_processos_fn=processos_parados
        )
        self.assertFalse(resultado["pronto"])
        self.assertIn(".env", resultado["arquivos_ausentes"])

    def test_verificador_aprova_pacote_integro(self):
        destino = self.raiz / "pacote_integro"
        criar_pacote(
            self.origem, destino,
            verificar_processos_fn=processos_parados,
        )
        resultado = verificar_pacote(destino)
        self.assertTrue(resultado["valido"])
        self.assertEqual(resultado["motivos"], [])
        self.assertEqual(resultado["integridade_banco"], ["ok"])
        self.assertEqual(
            resultado["integridade_bancos"]["pre_live.db"], ["ok"]
        )

    def test_verificador_recusa_arquivo_alterado(self):
        (self.origem / "codigo.py").write_text("original", encoding="utf-8")
        destino = self.raiz / "pacote_alterado"
        criar_pacote(
            self.origem, destino,
            verificar_processos_fn=processos_parados,
        )
        (destino / "codigo.py").write_text("alterado", encoding="utf-8")
        resultado = verificar_pacote(destino)
        self.assertFalse(resultado["valido"])
        self.assertTrue(any(
            motivo.endswith(":codigo.py")
            for motivo in resultado["motivos"]
        ))

    def test_verificador_recusa_arquivo_ausente(self):
        destino = self.raiz / "pacote_incompleto"
        criar_pacote(
            self.origem, destino,
            verificar_processos_fn=processos_parados,
        )
        (destino / "requirements.lock.txt").unlink()
        resultado = verificar_pacote(destino)
        self.assertFalse(resultado["valido"])
        self.assertIn(
            "arquivo_ausente:requirements.lock.txt", resultado["motivos"]
        )

    def test_verificador_recusa_banco_pre_live_corrompido(self):
        destino = self.raiz / "pacote_pre_live_corrompido"
        criar_pacote(
            self.origem, destino,
            verificar_processos_fn=processos_parados,
        )
        (destino / "pre_live.db").write_bytes(b"corrupcao")
        resultado = verificar_pacote(destino)
        self.assertFalse(resultado["valido"])
        self.assertIn(
            "banco_integro_nao_confirmado:pre_live.db",
            resultado["motivos"],
        )


if __name__ == "__main__":
    unittest.main()
