"""Circuit breaker do grupo de teste do Próximo Gol balanceado.

O controle não interfere na geração nem na coorte prospectiva. Ele bloqueia
somente novas entregas ao grupo de teste quando a validação detectar evidência
forte de ROI negativo. Estado ausente libera; estado ilegível falha fechado.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4


VERSAO_CONTROLE = "controle-proximo-gol-balanceado-v1"
ARQUIVO_ESTADO = Path(__file__).with_name(
    "proximo_gol_balanceado_estado.json"
)


def _estado_padrao(caminho):
    return {
        "versao": VERSAO_CONTROLE,
        "saudavel": True,
        "ativo": True,
        "estado": "ativo_padrao",
        "motivo": None,
        "assinatura": None,
        "atualizado_em": None,
        "caminho": str(Path(caminho)),
    }


def ler_estado(caminho=None):
    caminho = Path(caminho or ARQUIVO_ESTADO)
    if not caminho.exists():
        return _estado_padrao(caminho)
    try:
        documento = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as erro:
        return {
            **_estado_padrao(caminho),
            "saudavel": False,
            "ativo": False,
            "estado": "estado_invalido_fail_closed",
            "motivo": type(erro).__name__,
        }
    if (
        not isinstance(documento, dict)
        or documento.get("versao") != VERSAO_CONTROLE
        or not isinstance(documento.get("ativo"), bool)
    ):
        return {
            **_estado_padrao(caminho),
            "saudavel": False,
            "ativo": False,
            "estado": "estado_incompativel_fail_closed",
            "motivo": "estrutura_incompativel",
        }
    return {**documento, "saudavel": True, "caminho": str(caminho)}


def grupo_liberado(caminho=None):
    estado = ler_estado(caminho)
    return bool(estado.get("saudavel") and estado.get("ativo"))


def _gravar(caminho, documento):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(f".{caminho.name}.{uuid4().hex}.tmp")
    try:
        temporario.write_text(
            json.dumps(documento, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)
    return ler_estado(caminho)


def suspender(
    assinatura,
    motivo,
    *,
    metricas=None,
    caminho=None,
    agora=None,
    automatico=True,
):
    caminho = Path(caminho or ARQUIVO_ESTADO)
    atual = ler_estado(caminho)
    if not atual.get("saudavel"):
        return {**atual, "alterado": False, "idempotente": False}
    assinatura = str(assinatura or "sem_assinatura")
    if atual.get("ativo") is False and atual.get("assinatura") == assinatura:
        return {**atual, "alterado": False, "idempotente": True}
    instante = (agora or datetime.now()).replace(microsecond=0).isoformat()
    documento = {
        "versao": VERSAO_CONTROLE,
        "ativo": False,
        "estado": "sombra_automatico" if automatico else "sombra_manual",
        "motivo": str(motivo),
        "assinatura": assinatura,
        "atualizado_em": instante,
        "metricas": dict(metricas or {}),
        "reativacao": "python controlar_proximo_gol_balanceado.py --ativar",
    }
    return {
        **_gravar(caminho, documento),
        "alterado": True,
        "idempotente": False,
    }


def ativar(caminho=None, agora=None, motivo="reativacao_manual"):
    caminho = Path(caminho or ARQUIVO_ESTADO)
    atual = ler_estado(caminho)
    if not atual.get("saudavel"):
        return {**atual, "alterado": False, "idempotente": False}
    instante = (agora or datetime.now()).replace(microsecond=0).isoformat()
    documento = {
        "versao": VERSAO_CONTROLE,
        "ativo": True,
        "estado": "ativo_manual",
        "motivo": str(motivo),
        "assinatura": f"manual|{instante}",
        "atualizado_em": instante,
        "metricas": {},
        "rollback": "python controlar_proximo_gol_balanceado.py --sombra",
    }
    return {
        **_gravar(caminho, documento),
        "alterado": True,
        "idempotente": False,
    }
