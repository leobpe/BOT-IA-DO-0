import json
import subprocess
import sys
import unittest
from pathlib import Path

from treino_processo_isolado import PROTOCOLO_TREINO_ISOLADO


class TreinoProcessoIsoladoTest(unittest.TestCase):
    def test_worker_recusa_execucao_sem_processo_pai_vivo(self):
        worker = Path.cwd() / "treinar_modelo_worker.py"
        payload = json.dumps({
            "protocolo": PROTOCOLO_TREINO_ISOLADO,
            "tipo": "pontuacao_contexto",
            "pid_pai": 2_147_483_647,
            "dados": {},
        })

        processo = subprocess.run(
            [sys.executable, "-I", "-B", str(worker)],
            input=payload,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=5,
            cwd=str(worker.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        resposta = json.loads(processo.stdout)

        self.assertNotEqual(processo.returncode, 0)
        self.assertFalse(resposta["ok"])
        self.assertEqual(resposta["erro"], "RuntimeError")
        self.assertEqual(resposta["mensagem"], "processo_pai_ausente")


if __name__ == "__main__":
    unittest.main()
