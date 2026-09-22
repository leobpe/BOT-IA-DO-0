"""Histórico independente de HT e FT no mando correto para challengers Top."""

import copy
import math
import time


HISTORICO_PERIODO_ALVO = 10
HISTORICO_BUSCA_PERIODO = 30
TTL_HISTORICO_SEGUNDOS = 6 * 3600


def _numero(valor):
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".")
    try:
        numero = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
    return numero if numero is not None and math.isfinite(numero) else None


def _resumir_periodos_venue(itens, time_id, em_casa):
    partidas = []
    for item in itens or []:
        times = item.get("teams") or {}
        casa_id = ((times.get("home") or {}).get("id"))
        fora_id = ((times.get("away") or {}).get("id"))
        if em_casa and casa_id != time_id:
            continue
        if not em_casa and fora_id != time_id:
            continue

        gols_ft = item.get("goals") or {}
        gols_ht = ((item.get("score") or {}).get("halftime") or {})
        ft_casa = _numero(gols_ft.get("home"))
        ft_fora = _numero(gols_ft.get("away"))
        ht_casa = _numero(gols_ht.get("home"))
        ht_fora = _numero(gols_ht.get("away"))
        if None in (ft_casa, ft_fora, ht_casa, ht_fora):
            continue

        if em_casa:
            pro_ft, contra_ft = ft_casa, ft_fora
            pro_ht, contra_ht = ht_casa, ht_fora
        else:
            pro_ft, contra_ft = ft_fora, ft_casa
            pro_ht, contra_ht = ht_fora, ht_casa
        partidas.append({
            "timestamp": _numero((item.get("fixture") or {}).get("timestamp")) or 0,
            "pro_ft": pro_ft,
            "contra_ft": contra_ft,
            "pro_ht": pro_ht,
            "contra_ht": contra_ht,
        })

    partidas.sort(key=lambda x: x["timestamp"], reverse=True)
    partidas = partidas[:HISTORICO_PERIODO_ALVO]
    total = len(partidas)
    if not total:
        return {"jogos": 0}

    def taxa(teste):
        return round(sum(bool(teste(item)) for item in partidas) / total, 4)

    return {
        "jogos": total,
        "marcou_ht_taxa": taxa(lambda x: x["pro_ht"] >= 1),
        "sofreu_ht_taxa": taxa(lambda x: x["contra_ht"] >= 1),
        "over_0_5_ht_taxa": taxa(
            lambda x: x["pro_ht"] + x["contra_ht"] >= 1
        ),
        "marcou_ft_taxa": taxa(lambda x: x["pro_ft"] >= 1),
        "sofreu_ft_taxa": taxa(lambda x: x["contra_ft"] >= 1),
        "over_1_5_ft_taxa": taxa(
            lambda x: x["pro_ft"] + x["contra_ft"] >= 2
        ),
        "over_2_5_ft_taxa": taxa(
            lambda x: x["pro_ft"] + x["contra_ft"] >= 3
        ),
        "btts_ft_taxa": taxa(
            lambda x: x["pro_ft"] >= 1 and x["contra_ft"] >= 1
        ),
    }


def coletar_contexto_periodos_10(api, confirmacao, contexto_base=None):
    """Busca os dez jogos válidos em casa/fora sem tocar nos modelos antigos."""
    confirmacao = confirmacao or {}
    times = confirmacao.get("times") or {}
    mandante_id = ((times.get("home") or {}).get("id"))
    visitante_id = ((times.get("away") or {}).get("id"))
    if not mandante_id or not visitante_id:
        return contexto_base

    prazo = time.monotonic() + 7.0
    resumos = {}
    for lado, time_id, em_casa in (
        ("mandante", mandante_id, True),
        ("visitante", visitante_id, False),
    ):
        itens = api._lista_contexto(
            f"contexto:periodos10:{lado}:{time_id}",
            "/fixtures",
            {
                "team": time_id,
                "last": HISTORICO_BUSCA_PERIODO,
                "status": "FT",
            },
            TTL_HISTORICO_SEGUNDOS,
            prazo,
        )
        resumos[lado] = _resumir_periodos_venue(itens, time_id, em_casa)

    contexto = copy.deepcopy(contexto_base or {})
    contexto["historico_periodos_10"] = resumos
    return contexto
