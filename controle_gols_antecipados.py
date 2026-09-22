"""Circuit breaker persistente por braço para os gols antecipados.

O arquivo de estado nunca altera a geração nem a coorte prospectiva. Ele
somente impede novas entregas do braço exato cuja validação tenha comprovado
retorno integralmente negativo. Ausência do arquivo preserva a configuração;
estado existente e inválido falha fechado para os braços gerenciados.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4


VERSAO = "controle-gols-antecipados-v1"
ARQUIVO_ESTADO = Path(__file__).with_name(
    "gols_antecipados_estado.json"
)


def _padrao(caminho):
    return {
        "versao": VERSAO,
        "saudavel": True,
        "estado": "sem_suspensoes",
        "metodos": {},
        "atualizado_em": None,
        "caminho": str(Path(caminho)),
    }


def ler_estado(caminho=None):
    caminho = Path(caminho or ARQUIVO_ESTADO)
    if not caminho.exists():
        return _padrao(caminho)
    try:
        documento = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as erro:
        return {
            **_padrao(caminho),
            "saudavel": False,
            "estado": "estado_invalido_fail_closed",
            "motivo": type(erro).__name__,
        }
    metodos = documento.get("metodos") if isinstance(documento, dict) else None
    estrutura_valida = bool(
        isinstance(documento, dict)
        and documento.get("versao") == VERSAO
        and isinstance(metodos, dict)
        and all(
            isinstance(chave, str)
            and isinstance(item, dict)
            and isinstance(item.get("ativo"), bool)
            for chave, item in metodos.items()
        )
    )
    if not estrutura_valida:
        return {
            **_padrao(caminho),
            "saudavel": False,
            "estado": "estado_incompativel_fail_closed",
            "motivo": "estrutura_incompativel",
        }
    return {
        **documento,
        "saudavel": True,
        "caminho": str(caminho),
    }


def metodo_liberado(versao_metodo, caminho=None):
    estado = ler_estado(caminho)
    if not estado.get("saudavel"):
        return False
    metodo = (estado.get("metodos") or {}).get(str(versao_metodo)) or {}
    return metodo.get("ativo", True) is True


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


def suspender_metodo(
    versao_metodo,
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
    versao_metodo = str(versao_metodo)
    assinatura = str(assinatura or "sem_assinatura")
    existente = (atual.get("metodos") or {}).get(versao_metodo) or {}
    if existente.get("ativo") is False and existente.get(
        "assinatura"
    ) == assinatura:
        return {**atual, "alterado": False, "idempotente": True}
    instante = (agora or datetime.now()).replace(microsecond=0).isoformat()
    metodos = dict(atual.get("metodos") or {})
    metodos[versao_metodo] = {
        "ativo": False,
        "estado": "sombra_automatico" if automatico else "sombra_manual",
        "motivo": str(motivo),
        "assinatura": assinatura,
        "atualizado_em": instante,
        "metricas": dict(metricas or {}),
        "reativacao": (
            "python controlar_gols_antecipados.py --ativar "
            f'"{versao_metodo}"'
        ),
    }
    documento = {
        "versao": VERSAO,
        "estado": "metodo_suspenso",
        "metodos": metodos,
        "atualizado_em": instante,
    }
    return {
        **_gravar(caminho, documento),
        "alterado": True,
        "idempotente": False,
    }


def ativar_metodo(
    versao_metodo, *, caminho=None, agora=None, motivo="reativacao_manual"
):
    caminho = Path(caminho or ARQUIVO_ESTADO)
    atual = ler_estado(caminho)
    if not atual.get("saudavel"):
        return {**atual, "alterado": False, "idempotente": False}
    versao_metodo = str(versao_metodo)
    instante = (agora or datetime.now()).replace(microsecond=0).isoformat()
    metodos = dict(atual.get("metodos") or {})
    metodos[versao_metodo] = {
        "ativo": True,
        "estado": "ativo_manual",
        "motivo": str(motivo),
        "assinatura": f"manual|{instante}",
        "atualizado_em": instante,
        "metricas": {},
        "rollback": (
            "python controlar_gols_antecipados.py --sombra "
            f'"{versao_metodo}"'
        ),
    }
    documento = {
        "versao": VERSAO,
        "estado": "controle_manual_atualizado",
        "metodos": metodos,
        "atualizado_em": instante,
    }
    return {
        **_gravar(caminho, documento),
        "alterado": True,
        "idempotente": False,
    }
