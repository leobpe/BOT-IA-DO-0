"""Contrato comum da coleta rápida de preço posterior a um alerta.

A coleta é estritamente observacional: ela não cria candidatos, não envia
Telegram e não participa dos gates da decisão que já foi tomada.
"""

from __future__ import annotations

import math


VERSAO_EVIDENCIA_ESTADO_CLV_V1 = "estado-clv-pos-alerta-v1"
VERSAO_EVIDENCIA_ESTADO_CLV_V2 = "estado-clv-pos-alerta-v2"
VERSAO_EVIDENCIA_ESTADO_CLV = "estado-clv-pos-alerta-v3"
VERSAO_COLETA_CLV_API_RAPIDA = "coleta-clv-pos-alerta-api-rapida-v5"
ESTADO_OBSERVACAO_CLV = "clv_pos_alerta"
PREFIXO_REFERENCIA_CLV = "clv_pos_alerta:"
HORIZONTE_MINIMO_SEGUNDOS = 120
HORIZONTE_MAXIMO_SEGUNDOS = 600
MERCADOS_CLV_API_RAPIDA = frozenset({
    "gol_ft",
    "gol_ht",
    "proximo_gol",
    "escanteios_ft_asiatico",
})
MERCADOS_CLV_SOMENTE_SNAPSHOT = frozenset({"proximo_escanteio"})
MERCADOS_CLV_MONITORADOS = frozenset(
    MERCADOS_CLV_API_RAPIDA | MERCADOS_CLV_SOMENTE_SNAPSHOT
)
STATUS_FIM_JOGO = frozenset({"ft", "aet", "pen", "finalizado"})
STATUS_ANULADO = frozenset({"canc", "abd", "pst", "anulado"})
STATUS_FIM_PRIMEIRO_TEMPO = frozenset({
    "ht",
    "2h",
    "et",
    "bt",
    "p",
    "intervalo",
    *STATUS_FIM_JOGO,
})


def referencia_clv(sinal_id):
    return f"{PREFIXO_REFERENCIA_CLV}{int(sinal_id)}"


def numero_finito(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def normalizar_escanteios_estado(valor):
    """Valida o par de cantos incluído numa fotografia rápida da API."""
    if valor is None:
        return None
    if not isinstance(valor, dict) or set(valor) != {"mandante", "visitante"}:
        return False
    resultado = {}
    for lado in ("mandante", "visitante"):
        numero = numero_finito(valor.get(lado))
        if numero is None or numero < 0 or not numero.is_integer():
            return False
        resultado[lado] = int(numero)
    return resultado


def modo_coleta_estado_clv(fonte, bookmaker=None):
    """Separa preço executável de estado esportivo independente de preço."""
    fonte = str(fonte or "").strip().casefold()
    bookmaker = str(bookmaker or "").strip().casefold()
    if fonte == "betsapi" and bookmaker == "bet365":
        return "estado_e_preco"
    if fonte == "packball":
        return "somente_estado"
    return None


def linha_equivalente(mercado, valor_a, valor_b):
    if str(mercado or "") == "proximo_gol":
        return str(valor_a or "").strip().casefold() == str(
            valor_b or ""
        ).strip().casefold()
    a = numero_finito(valor_a)
    b = numero_finito(valor_b)
    return bool(a is not None and b is not None and math.isclose(
        a, b, abs_tol=1e-9
    ))


def status_normalizado(valor):
    return str(valor or "").strip().casefold()


def mercado_encerrado(mercado, status):
    mercado = str(mercado or "").strip().casefold()
    status = status_normalizado(status)
    if status in STATUS_ANULADO:
        return False
    if mercado == "gol_ht":
        return status in STATUS_FIM_PRIMEIRO_TEMPO
    return status in STATUS_FIM_JOGO


def canal_e_entrada(canal):
    canal = str(canal or "")
    bloqueados = (
        "gateway:", ":resultado", ":green_antecipado",
        ":aguardar_odd", ":cancelamento", ":insuficiente",
        ":monitoramento_final", ":correcao",
    )
    return bool(canal and not any(item in canal for item in bloqueados))
