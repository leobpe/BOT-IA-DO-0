"""Distribuição histórica por linha para decisões de mais um gol.

Mantém esta hipótese isolada da linhagem do modelo contextual V2b. A coleta
reutiliza a mesma chave de cache das últimas 15 partidas e, portanto, não
consome uma segunda chamada de rede quando o contexto V2b já foi obtido.
"""

import copy
import time


VERSAO = "contexto-linhas-gols-v1"
HISTORICO_ALVO = 15
TTL_SEGUNDOS = 6 * 3600
LINHAS = tuple(indice + 0.5 for indice in range(10))


def _numero(valor):
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _resumir(itens, time_id, mando_alvo):
    partidas = []
    for item in itens or []:
        times = item.get("teams") or {}
        casa_id = (times.get("home") or {}).get("id")
        fora_id = (times.get("away") or {}).get("id")
        if time_id not in (casa_id, fora_id):
            continue
        em_casa = time_id == casa_id
        gols = item.get("goals") or {}
        gols_casa = _numero(gols.get("home"))
        gols_fora = _numero(gols.get("away"))
        if gols_casa is None or gols_fora is None:
            continue
        intervalo = (item.get("score") or {}).get("halftime") or {}
        ht_casa = _numero(intervalo.get("home"))
        ht_fora = _numero(intervalo.get("away"))
        partidas.append({
            "em_casa": em_casa,
            "total_gols": gols_casa + gols_fora,
            "total_gols_ht": (
                ht_casa + ht_fora
                if ht_casa is not None and ht_fora is not None else None
            ),
            "timestamp": _numero((item.get("fixture") or {}).get("timestamp")),
        })
    partidas.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
    partidas = partidas[:HISTORICO_ALVO]

    def metricas(amostra):
        amostra_ht = [x for x in amostra if x["total_gols_ht"] is not None]
        resultado = {"jogos": len(amostra), "jogos_ht": len(amostra_ht)}
        for linha in LINHAS:
            chave = f"over_{str(linha).replace('.', '_')}_taxa"
            resultado[chave] = (
                round(sum(x["total_gols"] > linha for x in amostra) / len(amostra), 4)
                if amostra else None
            )
            resultado[f"ht_{chave}"] = (
                round(
                    sum(x["total_gols_ht"] > linha for x in amostra_ht)
                    / len(amostra_ht),
                    4,
                )
                if amostra_ht else None
            )
        return resultado

    mando = [x for x in partidas if x["em_casa"] == bool(mando_alvo)]
    return {"geral": metricas(partidas), "mando": metricas(mando)}


def coletar_contexto_linhas_gols(api, confirmacao, contexto_base=None):
    confirmacao = confirmacao or {}
    times = confirmacao.get("times") or {}
    mandante_id = (times.get("home") or {}).get("id")
    visitante_id = (times.get("away") or {}).get("id")
    if not mandante_id or not visitante_id:
        return contexto_base
    prazo = time.monotonic() + 7.0
    recentes = {}
    for lado, time_id, mando in (
        ("mandante", mandante_id, True),
        ("visitante", visitante_id, False),
    ):
        itens = api._lista_contexto(
            f"contexto:v2:forma15:{time_id}",
            "/fixtures",
            {"team": time_id, "last": HISTORICO_ALVO, "status": "FT"},
            TTL_SEGUNDOS,
            prazo,
        )
        recentes[lado] = _resumir(itens, time_id, mando)
    destino = copy.deepcopy(contexto_base) if isinstance(contexto_base, dict) else {}
    destino["tendencia_linhas_gols_v1"] = {
        "versao": VERSAO,
        "historico_alvo": HISTORICO_ALVO,
        "recentes": recentes,
    }
    return destino
