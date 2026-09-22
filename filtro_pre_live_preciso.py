"""Protecao de entrega para selecoes pre-live de alta precisao.

O seletor continua avaliando e persistindo a populacao completa. Este modulo
decide somente quais bilhetes podem sair nos canais, permitindo medir em
sombra tudo o que foi barrado e desligar a protecao por variavel de ambiente.
"""

from __future__ import annotations

import os
from collections import Counter

from controle_pre_live_preciso import entrega_liberada


VERSAO = "filtro-pre-live-preciso-v1"
MERCADOS_FRACOS = {"multigols_time", "time_marca_gol"}
QUALIDADE_MINIMA = 85.0
EDGE_CONSERVADOR_MINIMO = 0.04


def filtro_ativo():
    return os.getenv("PRELIVE_FILTRO_PRECISO_ATIVO", "0").strip().lower() in {
        "1", "true", "sim", "yes", "on",
    }


def _eh_under(perna):
    return "under_" in str((perna or {}).get("selecao") or "").lower()


def avaliar_criterios_bilhete_pre_live_preciso(bilhete):
    """Aplica a regra imutavel sem consultar ambiente ou circuit breaker."""
    bilhete = bilhete or {}
    pernas = list(bilhete.get("pernas") or [])
    if not pernas:
        return False, "sem_pernas"

    mercados = {
        str(perna.get("mercado") or "").strip().lower()
        for perna in pernas
    }
    if mercados & MERCADOS_FRACOS:
        return False, "mercado_time_sem_edge_estavel"

    if len(pernas) > 1 and all(_eh_under(perna) for perna in pernas):
        return False, "multipla_under_sem_edge_estavel"

    qualidade_minima = min(
        float(perna.get("qualidade_contexto") or 0.0)
        for perna in pernas
    )
    if qualidade_minima < QUALIDADE_MINIMA:
        return False, "qualidade_contexto_abaixo_85"

    edge_conservador = float(
        bilhete.get("edge_conservador", bilhete.get("edge_modelo") or 0.0)
    )
    if edge_conservador < EDGE_CONSERVADOR_MINIMO:
        return False, "edge_conservador_abaixo_4pct"

    return True, "aprovado"


def avaliar_bilhete_pre_live_preciso(bilhete, caminho_controle=None):
    """Retorna (aprovado, motivo) sem alterar o bilhete recebido."""
    if not filtro_ativo():
        return True, "filtro_desativado"
    if not entrega_liberada(caminho_controle):
        return False, "circuit_breaker_pre_live_preciso"
    return avaliar_criterios_bilhete_pre_live_preciso(bilhete)


def filtrar_bilhetes_pre_live_precisos(
    bilhetes, caminho_controle=None
):
    aprovados = []
    motivos = Counter()
    for bilhete in bilhetes or []:
        aprovado, motivo = avaliar_bilhete_pre_live_preciso(
            bilhete, caminho_controle=caminho_controle
        )
        if aprovado:
            aprovados.append(bilhete)
        else:
            motivos[motivo] += 1
    return aprovados, dict(sorted(motivos.items()))
