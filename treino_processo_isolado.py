"""Fronteira resiliente para treinamentos numericos locais e raros."""

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path


PROTOCOLO_TREINO_ISOLADO = "treino-modelo-isolado-v1"
TENTATIVAS_TREINO_ISOLADO = 3
TIMEOUT_TREINO_ISOLADO_SEGUNDOS = 5.0


def executar_treino_isolado(
    tipo,
    dados,
    validar_modelo,
    erros_dominio_exatos=(),
    erros_dominio_prefixos=(),
):
    """Executa, limita e valida um treino em processo descartavel."""
    payload = json.dumps(
        {
            "protocolo": PROTOCOLO_TREINO_ISOLADO,
            "tipo": str(tipo),
            "pid_pai": os.getpid(),
            "dados": dados,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    worker = Path(__file__).with_name("treinar_modelo_worker.py")
    erros = []
    for tentativa in range(1, TENTATIVAS_TREINO_ISOLADO + 1):
        try:
            processo = subprocess.run(
                [sys.executable, "-I", "-B", str(worker)],
                input=payload,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=TIMEOUT_TREINO_ISOLADO_SEGUNDOS,
                cwd=str(worker.parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except subprocess.TimeoutExpired:
            erros.append("timeout")
            continue
        try:
            resposta = json.loads(processo.stdout or "{}")
        except (TypeError, ValueError):
            resposta = {}
        if processo.returncode != 0 or not resposta.get("ok"):
            tipo_erro = str(resposta.get("erro") or "worker_invalido")
            mensagem = str(resposta.get("mensagem") or "")
            if tipo_erro == "ValueError" and (
                mensagem in set(erros_dominio_exatos)
                or any(
                    mensagem.startswith(prefixo)
                    for prefixo in erros_dominio_prefixos
                )
            ):
                raise ValueError(mensagem)
            erros.append(tipo_erro)
            continue
        modelo = resposta.get("modelo")
        if validar_modelo(modelo):
            modelo = dict(modelo)
            modelo["execucao_treino_isolado"] = {
                "protocolo": PROTOCOLO_TREINO_ISOLADO,
                "tipo": str(tipo),
                "tentativas": tentativa,
                "recuperou_falha_transitoria": bool(erros),
                "falhas_transitorias": list(erros),
            }
            return modelo
        erros.append("modelo_incompativel")
    tipos = ",".join(erros[-TENTATIVAS_TREINO_ISOLADO:])
    raise RuntimeError(f"treino_isolado_falhou:{tipo}:{tipos}")


def verificar_worker_treino_isolado():
    """Prova localmente processo, protocolo, custodia, timeout e retorno."""
    desafio = secrets.token_hex(16)
    inicio = time.monotonic()
    try:
        resposta = executar_treino_isolado(
            "autoteste",
            {"desafio": desafio},
            validar_modelo=lambda modelo: bool(
                isinstance(modelo, dict)
                and modelo.get("tipo") == "autoteste"
                and modelo.get("desafio") == desafio
            ),
        )
    except (OSError, RuntimeError, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "worker_treino_isolado_indisponivel",
            "erro": type(erro).__name__,
            "duracao_ms": round((time.monotonic() - inicio) * 1000, 3),
        }
    isolamento = resposta.get("execucao_treino_isolado") or {}
    saudavel = bool(
        isolamento.get("protocolo") == PROTOCOLO_TREINO_ISOLADO
        and isolamento.get("tipo") == "autoteste"
        and int(isolamento.get("tentativas") or 0) >= 1
    )
    return {
        "saudavel": saudavel,
        "estado": (
            "recuperado"
            if isolamento.get("recuperou_falha_transitoria")
            else "pronto"
            if saudavel
            else "invalido"
        ),
        "motivo": None if saudavel else "resposta_autoteste_invalida",
        "protocolo": isolamento.get("protocolo"),
        "tentativas": isolamento.get("tentativas"),
        "recuperou_falha_transitoria": bool(
            isolamento.get("recuperou_falha_transitoria")
        ),
        "falhas_transitorias": list(
            isolamento.get("falhas_transitorias") or []
        ),
        "duracao_ms": round((time.monotonic() - inicio) * 1000, 3),
    }
