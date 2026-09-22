"""Auditoria somente leitura dos dados históricos antes da entrega de gols.

Não muda modelos, odds ou coortes. Cache atualizado não torna antigas partidas
atuais: as datas conferidas são as dos jogos efetivamente usados no resumo.
"""

import json
import math
import os
from datetime import datetime


VERSAO = "validade-historico-gols-envio-v1"
IDADE_MAXIMA_DIAS = 365
MINIMO_JOGOS_DISTRIBUICAO = 10
MERCADOS = {"gol_ht", "gol_ft", "proximo_gol"}
CHAVES_METODOS = {
    "gol_capacidade_contextual_v2", "gol_ht_00_min20",
    "gol_ft_tendencia_mais_um", "gol_2t_pos_ht_red",
    "gols_antecipados", "gol_antecipado", "gol_capacidade_times",
    "top_criterio_gols",
}


def _json(valor):
    if isinstance(valor, dict):
        return valor
    try:
        resultado = json.loads(valor or "{}")
        return resultado if isinstance(resultado, dict) else {}
    except (ValueError, TypeError):
        return {}


def _numero(valor):
    try:
        valor = float(valor)
        return valor if math.isfinite(valor) else None
    except (ValueError, TypeError):
        return None


def _timestamp(fixture):
    valor = _numero((fixture or {}).get("timestamp"))
    if valor is not None and valor > 0:
        return valor
    try:
        return datetime.fromisoformat(fixture["date"].replace("Z", "+00:00")).timestamp()
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None


def _resultado(aprovada, motivo, **dados):
    return {"versao": VERSAO, "aprovada": aprovada, "motivo": motivo, **dados}


def _selecionar(itens, time_id, limite=15, mando=None):
    selecionados = []
    for item in itens if isinstance(itens, list) else []:
        if not isinstance(item, dict):
            continue
        teams = item.get("teams") or {}
        home = (teams.get("home") or {}).get("id")
        away = (teams.get("away") or {}).get("id")
        if time_id not in (home, away):
            continue
        if mando is not None and (home == time_id) != mando:
            continue
        goals = item.get("goals") or {}
        if any(_numero(goals.get(k)) is None for k in ("home", "away")):
            continue
        selecionados.append(item)
    selecionados.sort(key=lambda x: _timestamp(x.get("fixture")) or 0, reverse=True)
    return selecionados[:limite]


def _auditar_datas(itens, agora, lado):
    if not itens:
        return _resultado(False, "historico_datas_indisponivel", lado=lado)
    datas = [_timestamp(x.get("fixture") or {}) for x in itens]
    if any(x is None for x in datas):
        return _resultado(False, "historico_data_ausente", lado=lado)
    if any(x > agora for x in datas):
        return _resultado(False, "historico_data_futura", lado=lado)
    antigos = sum(agora - x > IDADE_MAXIMA_DIAS * 86400 for x in datas)
    dados = {
        "lado": lado, "jogos": len(datas), "jogos_antigos": antigos,
        "idade_maxima_dias": IDADE_MAXIMA_DIAS,
        "idade_mais_antigo_dias": round((agora - min(datas)) / 86400, 2),
    }
    return _resultado(not antigos, "historico_antigo" if antigos else "datas_confirmadas", **dados)


def avaliar_historico_envio(conexao, sinal, snapshot, agora=None):
    """Usa somente SQLite/cache existente; não consulta APIs nem altera dados."""
    if os.getenv("VALIDADE_HISTORICO_GOLS_ATIVA", "1").lower() in {"0", "false", "off", "nao"}:
        return _resultado(True, "desativada")
    if sinal.get("mercado") not in MERCADOS:
        return _resultado(True, "fora_do_escopo")
    features = _json(sinal.get("features") or sinal.get("features_json"))
    contexto = _json((snapshot or {}).get("contexto_api_json"))
    usa_historico = (
        any(k in features for k in CHAVES_METODOS)
        or bool(features.get("protecao_conversao_gols"))
        or bool(contexto.get("capacidade_times_v2"))
        or bool(contexto.get("tendencia_linhas_gols_v1"))
    )
    if not usa_historico:
        return _resultado(True, "sem_modelo_historico")
    times = contexto.get("times") or {}
    if not all(times.get(k) for k in ("mandante_id", "visitante_id")):
        return _resultado(False, "historico_identidade_indisponivel")
    if conexao is None:
        return _resultado(False, "historico_cache_indisponivel")
    instante = (agora or datetime.now()).timestamp()
    auditorias = []
    # As mesmas rotinas que produziram os resumos, sem mudar suas fórmulas.
    from contexto_linhas_gols import _resumir
    from gols_capacidade_contextual_v2 import _resumir_partidas
    for lado, mando in (("mandante", True), ("visitante", False)):
        time_id = times[lado + "_id"]
        raw = conexao.execute(
            "SELECT dados_json FROM cache_api_football WHERE chave=?",
            (f"contexto:v2:forma15:{time_id}",),
        ).fetchone()
        try:
            itens = json.loads(raw[0]) if raw else []
        except (ValueError, TypeError):
            itens = []
        selecionados = _selecionar(itens, time_id)
        auditoria = _auditar_datas(selecionados, instante, lado)
        auditorias.append(auditoria)
        if not auditoria["aprovada"]:
            return _resultado(False, auditoria["motivo"], times=auditorias)
        # Um cache mais novo não pode atestar resumos diferentes dos que
        # sustentaram a decisão. Nesse caso é necessária uma nova análise.
        for chave, resumir in (("tendencia_linhas_gols_v1", _resumir),
                               ("capacidade_times_v2", _resumir_partidas)):
            esperado = ((contexto.get(chave) or {}).get("recentes") or {}).get(lado)
            if esperado and resumir(itens, time_id, mando) != esperado:
                return _resultado(False, "historico_cache_diverge_da_analise", lado=lado)
        if features.get("top_criterio_gols"):
            from contexto_periodos_10 import _resumir_periodos_venue
            raw_periodos = conexao.execute(
                "SELECT dados_json FROM cache_api_football WHERE chave=?",
                (f"contexto:periodos10:{lado}:{time_id}",),
            ).fetchone()
            try:
                itens_periodos = json.loads(raw_periodos[0]) if raw_periodos else []
            except (ValueError, TypeError):
                itens_periodos = []
            validos = [x for x in itens_periodos if isinstance(x, dict) and all(
                _numero((((x.get("score") or {}).get("halftime") or {}).get(k))) is not None
                for k in ("home", "away")
            )] if isinstance(itens_periodos, list) else []
            selecao = _selecionar(validos, time_id, limite=10, mando=mando)
            auditoria = _auditar_datas(selecao, instante, lado + "_mando10")
            auditorias.append(auditoria)
            if not auditoria["aprovada"]:
                return _resultado(False, auditoria["motivo"], times=auditorias)
            esperado = (contexto.get("historico_periodos_10") or {}).get(lado)
            if not esperado or _resumir_periodos_venue(itens_periodos, time_id, mando) != esperado:
                return _resultado(False, "historico_cache_diverge_da_analise", lado=lado + "_mando10")
    modelo = (features.get("gol_capacidade_contextual_v2") or {}).get("modelo_historico") or {}
    if modelo.get("metodo_tempo") == "distribuicao_temporada":
        for lado in ("mandante", "visitante"):
            temporada = (contexto.get("estatisticas_temporada") or {}).get(lado) or {}
            if any(temporada.get(k) for k in ("gols_pro_por_minuto", "gols_contra_por_minuto")):
                if (_numero(temporada.get("jogos")) or 0) < MINIMO_JOGOS_DISTRIBUICAO:
                    return _resultado(False, "distribuicao_temporal_amostra_insuficiente", lado=lado,
                                      jogos=temporada.get("jogos"), minimo=MINIMO_JOGOS_DISTRIBUICAO)
    return _resultado(True, "historico_atual_confirmado", times=auditorias)
