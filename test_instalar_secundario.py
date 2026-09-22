import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from instalar_secundario import (
    diagnosticar_secundario,
    instalar_secundario,
    localizar_edge,
)


class InstalarSecundarioTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / f".teste_instalador_{uuid4().hex}"
        self.pasta.mkdir()
        (self.pasta / "requirements.lock.txt").write_text(
            "python-dotenv==1.2.2\n", encoding="utf-8"
        )
        (self.pasta / "preflight_reinicio.py").write_text(
            "print('ok')\n", encoding="utf-8"
        )
        self.programas = self.pasta / "Program Files (x86)"
        self.edge = (
            self.programas / "Microsoft" / "Edge" / "Application" /
            "msedge.exe"
        )
        self.edge.parent.mkdir(parents=True)
        self.edge.write_bytes(b"edge")
        self.ambiente = {"PROGRAMFILES(X86)": str(self.programas)}

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_localiza_edge_sem_depender_de_registro_windows(self):
        self.assertEqual(localizar_edge(self.ambiente), self.edge)

    def test_diagnostico_exige_pacote_integro(self):
        resultado = diagnosticar_secundario(
            self.pasta,
            versao_python=(3, 14, 0),
            plataforma="nt",
            ambiente=self.ambiente,
            verificar_pacote_fn=lambda _pasta: {
                "valido": False, "motivos": ["checksum_divergente"]
            },
        )
        self.assertFalse(resultado["pronto"])
        self.assertIn("pacote_transferencia_invalido", resultado["motivos"])

    def test_instalacao_e_idempotente_e_nao_inicia_bot(self):
        comandos = []

        def executar(comando, **_opcoes):
            comandos.append(comando)
            if comando[1:3] == ["-m", "venv"]:
                python_venv = self.pasta / ".venv" / "Scripts" / "python.exe"
                python_venv.parent.mkdir(parents=True)
                python_venv.write_bytes(b"python")

        diagnostico = lambda _pasta: {"pronto": True, "motivos": []}
        with patch("instalar_secundario.os.name", "nt"):
            primeiro = instalar_secundario(
                self.pasta,
                executar_fn=executar,
                diagnosticar_fn=diagnostico,
            )
            quantidade_primeira = len(comandos)
            segundo = instalar_secundario(
                self.pasta,
                executar_fn=executar,
                diagnosticar_fn=diagnostico,
            )
        self.assertEqual(quantidade_primeira, 5)
        self.assertEqual(len(comandos) - quantidade_primeira, 4)
        self.assertFalse(primeiro["iniciou_bot"])
        self.assertFalse(primeiro["instalou_autostart"])
        self.assertEqual(segundo["estado"], "instalado_e_preflight_aprovado")


if __name__ == "__main__":
    unittest.main()
