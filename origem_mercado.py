"""Contrato compartilhado da origem exata de uma oferta de odd."""

from __future__ import annotations

import math


VERSAO_ORIGEM_MERCADO = "origem-mercado-odd-v1"


def _texto(valor):
    return str(valor or "").strip()


def _linha_normalizada(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        texto = _texto(valor)
        return texto.casefold() if texto else None
    return float(numero) if math.isfinite(numero) else None


def normalizar_origem_mercado(origem):
    """Normaliza a prova ou devolve ``None`` quando ela for incompleta."""
    if not isinstance(origem, dict):
        return None
    fonte = _texto(origem.get("fonte")).casefold()
    identificador = _texto(origem.get("identificador"))
    nome = _texto(origem.get("nome"))
    bookmaker = _texto(origem.get("bookmaker")).casefold()
    linha = _linha_normalizada(origem.get("linha"))
    lados_brutos = origem.get("lados")
    if not isinstance(lados_brutos, (list, tuple)):
        return None
    lados = [_texto(lado).casefold() for lado in lados_brutos]
    if (
        origem.get("schema") != VERSAO_ORIGEM_MERCADO
        or not fonte or not identificador or not nome or not bookmaker
        or linha is None or not lados or any(not lado for lado in lados)
        or len(set(lados)) != len(lados)
    ):
        return None
    return {
        "schema": VERSAO_ORIGEM_MERCADO,
        "fonte": fonte,
        "identificador": identificador,
        "nome": nome,
        "linha": linha,
        "lados": sorted(lados),
        "bookmaker": bookmaker,
    }


def assinatura_origem_mercado(origem):
    """Identidade estável usada para impedir mistura entre grupos."""
    normalizada = normalizar_origem_mercado(origem)
    if normalizada is None:
        return None
    return (
        normalizada["schema"],
        normalizada["fonte"],
        normalizada["identificador"],
        normalizada["nome"].casefold(),
        normalizada["linha"],
        tuple(normalizada["lados"]),
        normalizada["bookmaker"],
    )


def assinatura_grupo_mercado(origem):
    """Identifica o grupo, ignorando a linha específica dentro dele."""
    normalizada = normalizar_origem_mercado(origem)
    if normalizada is None:
        return None
    return (
        normalizada["schema"],
        normalizada["fonte"],
        normalizada["identificador"],
        normalizada["nome"].casefold(),
        normalizada["bookmaker"],
    )
