"""Worker descartavel e restrito para os treinamentos em sombra."""

import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from treino_processo_isolado import PROTOCOLO_TREINO_ISOLADO


def _pid_ativo_windows(pid):
    import ctypes
    from ctypes import wintypes

    acesso_consulta_limitada = 0x1000
    processo_ativo = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    identificador = kernel32.OpenProcess(
        acesso_consulta_limitada, False, pid
    )
    if not identificador:
        return ctypes.get_last_error() == 5
    try:
        codigo_saida = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(
            identificador, ctypes.byref(codigo_saida)
        ):
            return False
        return codigo_saida.value == processo_ativo
    finally:
        kernel32.CloseHandle(identificador)


def _pid_ativo(pid):
    try:
        pid = int(pid)
        if pid <= 0 or pid == os.getpid():
            return False
        if os.name == "nt":
            return _pid_ativo_windows(pid)
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False


def _vigiar_processo_pai(pid_pai):
    while True:
        time.sleep(0.25)
        if not _pid_ativo(pid_pai):
            os._exit(70)


def _iniciar_custodia_pai(pid_pai):
    if not _pid_ativo(pid_pai):
        raise RuntimeError("processo_pai_ausente")
    thread = threading.Thread(
        target=_vigiar_processo_pai,
        args=(pid_pai,),
        name="custodia-pai-treino",
        daemon=True,
    )
    thread.start()


def _treinar(tipo, dados):
    if tipo == "autoteste":
        desafio = dados.get("desafio")
        if not isinstance(desafio, str) or len(desafio) < 16:
            raise ValueError("desafio_autoteste_invalido")
        return {"tipo": "autoteste", "desafio": desafio}
    if tipo == "pontuacao_contexto":
        from pontuacao_contexto_sombra import _ajustar_modelo_impl

        return _ajustar_modelo_impl(
            dados.get("registros"), dados.get("mercado")
        )
    if tipo == "pontuacao_longa":
        from pontuacao_longa_sombra import (
            _ajustar_modelo_pontuacao_longa_impl,
        )

        return _ajustar_modelo_pontuacao_longa_impl(
            dados.get("registros")
        )
    raise ValueError("tipo_treino_invalido")


def main():
    try:
        payload = json.load(sys.stdin)
        if payload.get("protocolo") != PROTOCOLO_TREINO_ISOLADO:
            raise ValueError("protocolo_treino_invalido")
        _iniciar_custodia_pai(payload.get("pid_pai"))
        modelo = _treinar(payload.get("tipo"), payload.get("dados") or {})
        resposta = {"ok": True, "modelo": modelo}
        codigo = 0
    except Exception as erro:
        resposta = {
            "ok": False,
            "erro": type(erro).__name__,
            "mensagem": str(erro),
        }
        codigo = 1
    json.dump(
        resposta,
        sys.stdout,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
