"""Veto reversível de zero chute confirmado, somente no HT 0x0 v3/v4/v5.

Não substitui o modelo, não aprova entradas e não converte dado ausente em zero.
Usa a janela de 5 minutos (tolerância temporal existente: até 8 minutos).
"""

import json
import math
import os
from datetime import datetime

VERSAO = "ht00-veto-zero-chutes-recentes-v1"
METODO = "gol-ht-00-min20-over25-ou-btts-odd144-red-ok-v3"
METODOS = frozenset({
    METODO,
    "gol-ht-00-min20-over25-ou-btts-odd144-red-ok-v4",
    "gol-ht-00-min20-over25-e-btts-atividade5-odd144-red-ok-v5",
})
ROLLBACK = "FILTRO_HT_CHUTES_RECENTES_ATIVO"
MAX_IDADE_SEGUNDOS = 120


def _dict(valor):
    if isinstance(valor, dict):
        return valor
    try:
        item = json.loads(valor or "{}")
        return item if isinstance(item, dict) else {}
    except (ValueError, TypeError):
        return {}


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        valor = float(valor)
        return valor if math.isfinite(valor) and valor >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _idade(valor, agora):
    try:
        data = valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))
        segundos = (agora - data).total_seconds()
        return segundos if 0 <= segundos <= MAX_IDADE_SEGUNDOS else None
    except (TypeError, ValueError, OverflowError):
        return None


def validar_janela_chutes_recentes(janela):
    janela = _dict(janela)
    if janela.get("disponivel") is False:
        return None
    duracao = _numero(janela.get("duracao_real_minutos"))
    if duracao is None or not 5 <= duracao <= 8:
        return None
    resets = janela.get("resets_detectados", [])
    if not isinstance(resets, (list, tuple)) or "chutes" in resets:
        return None
    par = janela.get("chutes")
    if not isinstance(par, (list, tuple)) or len(par) != 2:
        return None
    par = [_numero(v) for v in par]
    if any(v is None or not v.is_integer() for v in par):
        return None
    total = int(sum(par))
    if "chutes_total" in janela and _numero(janela["chutes_total"]) != total:
        return None
    return {"chutes_total": total, "chutes": [int(v) for v in par],
            "duracao_real_minutos": duracao}


# Compatibilidade interna com a versão anterior do filtro.
_janela_valida = validar_janela_chutes_recentes


def avaliar_chutes_ht(sinal, snapshot, agora=None, env=None):
    """Decisão pura a partir da evidência persistida; nenhuma chamada externa."""
    agora = agora or datetime.now()
    env = os.environ if env is None else env
    features = _dict(sinal.get("features", sinal.get("features_json")))
    metodo = _dict(features.get("exploracao_sombra")).get("versao") or sinal.get("regra_versao")
    aplicavel = sinal.get("mercado") == "gol_ht" and metodo in METODOS
    resultado = {"versao": VERSAO, "aplicavel": aplicavel, "aprovada": True,
                 "motivo": "outro_metodo", "avaliado_em": agora.isoformat(),
                 "rollback": ROLLBACK + "=0", "fonte": None}
    if not aplicavel:
        return resultado
    if env.get(ROLLBACK, "1") != "1":
        return {**resultado, "motivo": "desativado"}
    resultado["motivo"] = "chutes_recentes_indisponiveis_sem_veto_adicional"
    snapshot = _dict(snapshot)
    if _idade(snapshot.get("coletado_em"), agora) is None:
        return {**resultado, "motivo": "snapshot_sem_frescor_para_chutes"}

    janela = _dict(_dict(features.get("janelas")).get("5"))
    observada = _idade(features.get("estado_observado_em"), agora)
    rapido = _dict(features.get("acompanhamento_odd_rapido"))
    if rapido:
        idade_tecnica = _numero(rapido.get("idade_tecnica_segundos"))
        # A atualização de odd não renova o horário da estatística técnica.
        if idade_tecnica is None or observada is None or idade_tecnica + observada > MAX_IDADE_SEGUNDOS:
            observada = None
    fusao = _dict(features.get("fusao_temporal_api_live"))
    chutes_api = "5.chutes" in (fusao.get("preenchimentos") or [])
    evidencia = _janela_valida(janela) if janela.get("disponivel") is True and observada is not None and not chutes_api else None
    fonte = "packball"
    lista = _dict(features.get("fallback_temporal_lista"))
    if evidencia and "5.chutes" in (lista.get("campos_complementados") or []):
        fonte = "packball_lista_ao_vivo"

    if evidencia is None:
        contexto = _dict(snapshot.get("contexto_api_json"))
        api = _dict(contexto.get("evolucao_temporal_api_live"))
        fixture_id = contexto.get("fixture_id")
        comparacao = _dict(_dict(contexto.get("comparacao_fontes_ao_vivo")).get("metricas"))
        conflito_chutes = _dict(comparacao.get("chutes")).get("concorda") is False
        if (fixture_id is not None and str(fixture_id) == str(api.get("fixture_id"))
                and api.get("fonte") == "api_football"
                and api.get("periodo") == "primeiro_tempo"
                and _idade(api.get("coletado_em"), agora) is not None
                and not conflito_chutes):
            evidencia = _janela_valida(api.get("5"))
            fonte = "api_football"
    if evidencia is None:
        return resultado
    return {**resultado, **evidencia, "fonte": fonte,
            "aprovada": evidencia["chutes_total"] > 0,
            "motivo": "chutes_recentes_confirmados" if evidencia["chutes_total"] > 0 else "ht00_zero_chutes_recentes_confirmado"}
