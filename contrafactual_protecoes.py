"""Registra o que teria ocorrido sem uma protecao operacional.

O contrafactual nunca e elegivel para Telegram ou calibracao oficial. Ele
existe apenas para receber liquidacao posterior no SQLite e medir se cada
bloqueio evitou reds ou perdeu greens.
"""

import copy
import os


VERSAO = "contrafactual-protecoes-gols-v1"
ATIVO = os.getenv(
    "CONTRAFACTUAL_PROTECOES_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}


def converter_em_contrafactual(candidato, protecao, motivo):
    """Converte somente uma aprovacao bloqueada em simulacao auditavel."""
    if candidato.get("status") != "aprovado":
        return False
    if not ATIVO:
        candidato["status"] = "rejeitado"
        return False

    features = copy.deepcopy(candidato.get("features") or {})
    features["avaliacao_contrafactual"] = {
        "versao": VERSAO,
        "protecao": str(protecao),
        "motivo": str(motivo),
        "status_sem_protecao": "aprovado",
        "aplicacao_automatica": False,
        "telegram": False,
        "calibracao_oficial": False,
    }
    features["exploracao_sombra"] = {
        "versao": VERSAO,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
        "grupo_teste": False,
        "origem": "bloqueio_protecao_operacional",
    }
    candidato["features"] = features
    candidato["status"] = "simulacao"
    return True
