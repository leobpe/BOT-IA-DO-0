"""Circuit breaker isolado da entrega do filtro FT antecipado preciso."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4


VERSAO_CONTROLE = "controle-filtro-gol-ft-antecipado-preciso-v1"
ARQUIVO_ESTADO = Path(__file__).with_name(
    "filtro_gol_ft_antecipado_preciso_estado.json"
)


def _padrao(caminho):
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
        return _padrao(caminho)
    try:
        documento = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as erro:
        return {
            **_padrao(caminho), "saudavel": False, "ativo": False,
            "estado": "estado_invalido_fail_closed",
            "motivo": type(erro).__name__,
        }
    if (
        not isinstance(documento, dict)
        or documento.get("versao") != VERSAO_CONTROLE
        or not isinstance(documento.get("ativo"), bool)
    ):
        return {
            **_padrao(caminho), "saudavel": False, "ativo": False,
            "estado": "estado_incompativel_fail_closed",
            "motivo": "estrutura_incompativel",
        }
    return {**documento, "saudavel": True, "caminho": str(caminho)}


def entrega_liberada(caminho=None):
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
    assinatura, motivo, *, metricas=None, caminho=None, agora=None,
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
        "estado": "suspenso_automatico" if automatico else "suspenso_manual",
        "motivo": str(motivo),
        "assinatura": assinatura,
        "atualizado_em": instante,
        "metricas": dict(metricas or {}),
        "reativacao": "python controlar_filtro_gol_ft_preciso.py --ativar",
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
        "rollback": "python controlar_filtro_gol_ft_preciso.py --suspender",
    }
    return {
        **_gravar(caminho, documento),
        "alterado": True,
        "idempotente": False,
    }


def aplicar_validacao(validacao, *, caminho=None, agora=None):
    validacao = validacao or {}
    estado = ler_estado(caminho)
    inconsistente = bool(
        validacao.get("versao") and validacao.get("saudavel") is False
    )
    negativo = bool(validacao.get("alerta_desfavoravel"))
    concluida = bool(validacao.get("resultados_completos"))
    if (inconsistente or negativo or concluida) and estado.get("ativo"):
        assinatura = "|".join((
            str(validacao.get("versao") or "sem_validacao"),
            str(validacao.get("registrado_em") or "sem_ancora"),
            str(validacao.get("definicao_sha256") or "sem_definicao"),
        ))
        motivo = (
            "validacao_filtro_gol_ft_preciso_inconsistente"
            if inconsistente else
            "ic95_roi_checkpoint_25_integralmente_negativo"
            if negativo else
            "coorte_60_concluida_aguardando_revisao_manual"
        )
        estado = suspender(
            assinatura,
            motivo,
            metricas={
                "validos": int(validacao.get("validos", 0) or 0),
                "greens": int(validacao.get("greens", 0) or 0),
                "reds": int(validacao.get("reds", 0) or 0),
                "roi": validacao.get("roi"),
                "intervalo_roi_95": validacao.get("intervalo_roi_95"),
                "checkpoint_seguranca": validacao.get(
                    "checkpoint_seguranca"
                ),
                "coorte_concluida": concluida,
                "coleta_sombra_continua": True,
            },
            caminho=caminho,
            agora=agora,
            automatico=True,
        )
    return estado
