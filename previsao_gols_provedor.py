"""Leitura direcional de previsões: linhas under/over não são médias de gols."""

import math
import re
import unicodedata

VERSAO = "previsao-gols-direcional-v1"
_LINHA = re.compile(
    r"(?:(?P<sinal>[+-])\s*(?P<numero_sinal>\d+(?:[.,]\d+)?)"
    r"|(?P<rotulo>over|under|mais(?:\s+de)?|menos(?:\s+de)?)\s*"
    r"(?P<numero_texto>\d+(?:[.,]\d+)?))"
    r"(?:\s*(?:gols?|goals?))?",
    re.IGNORECASE,
)


def interpretar_previsao_gols(valor):
    """Exige direção explícita e uma única linha, sem extrair números soltos."""
    if not isinstance(valor, str):
        return None
    texto = unicodedata.normalize("NFKC", valor).strip().replace("−", "-")
    match = _LINHA.fullmatch(texto)
    if not match:
        return None
    linha = float((match["numero_sinal"] or match["numero_texto"]).replace(",", "."))
    if not math.isfinite(linha) or linha <= 0:
        return None
    rotulo = (match["rotulo"] or "").casefold()
    direcao = "under" if match["sinal"] == "-" or rotulo.startswith(("under", "menos")) else "over"
    return {"direcao": direcao, "linha": linha}


def linha_over_prevista(valor):
    previsao = interpretar_previsao_gols(valor)
    return previsao["linha"] if previsao and previsao["direcao"] == "over" else None


def total_gols_esperados(valores):
    """Soma apenas estimativas pontuais completas, nunca '+1.5' ou '-2.5'.

    A API-Football também usa o campo goals para faixas direcionais; um limite
    de gols não é uma média esperada. Dados ausentes não entram como zero.
    """
    if not isinstance(valores, dict) or set(valores) != {"home", "away"}:
        return None
    numeros = []
    for lado in ("home", "away"):
        valor = valores[lado]
        if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
            return None
        if isinstance(valor, str):
            valor = valor.strip()
            if not re.fullmatch(r"\d+(?:[.,]\d+)?", valor):
                return None
            valor = valor.replace(",", ".")
        numero = float(valor)
        if not math.isfinite(numero) or numero < 0:
            return None
        numeros.append(numero)
    total = sum(numeros)
    return total if math.isfinite(total) else None
