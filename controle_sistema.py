import json
import os
from datetime import datetime
from pathlib import Path


NOME_ARQUIVO_MODO = "modo_manutencao.json"


def caminho_modo_manutencao(pasta):
    return Path(pasta) / NOME_ARQUIVO_MODO


def ler_modo_manutencao(pasta):
    caminho = caminho_modo_manutencao(pasta)
    if not caminho.exists():
        return {"ativo": False}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        # Fail-safe: arquivo presente e ilegivel ainda impede autorreinicios.
        return {
            "ativo": True,
            "motivo": "arquivo_manutencao_invalido",
            "solicitado_em": None,
        }
    return {
        "ativo": bool(dados.get("ativo", True)),
        "motivo": dados.get("motivo") or "manutencao_manual",
        "solicitado_em": dados.get("solicitado_em"),
        "pid_solicitante": dados.get("pid_solicitante"),
    }


def solicitar_modo_manutencao(pasta, motivo="manutencao_manual", agora=None):
    caminho = caminho_modo_manutencao(pasta)
    agora = agora or datetime.now()
    dados = {
        "ativo": True,
        "motivo": str(motivo or "manutencao_manual"),
        "solicitado_em": agora.replace(microsecond=0).isoformat(),
        "pid_solicitante": os.getpid(),
    }
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporario.replace(caminho)
    return dados


def liberar_modo_manutencao(pasta):
    caminho = caminho_modo_manutencao(pasta)
    existia = caminho.exists()
    caminho.unlink(missing_ok=True)
    caminho.with_suffix(caminho.suffix + ".tmp").unlink(missing_ok=True)
    return existia
