"""Auditoria descritiva HT; apenas leitura, sem banir ligas ou enviar mensagens."""

import json
from collections import defaultdict
from datetime import datetime, timedelta

from auditar_metodos_enviados import conectar, metricas
from filtro_ht_chutes_recentes import METODO, ROLLBACK, avaliar_chutes_ht


def resumir_ligas(itens):
    grupos = defaultdict(list)
    for item in itens:
        grupos[(item["pais"] or "não identificado", item["liga"] or "não identificada")].append(item)
    return sorted([
        {"pais": pais, "liga": liga, **metricas(linhas),
         "dias_distintos": len({x["enviado_em"][:10] for x in linhas}),
         "ids": [x["id"] for x in linhas]}
        for (pais, liga), linhas in grupos.items()
    ], key=lambda x: x["lucro_unidades"])


def auditar():
    corte = datetime.now().replace(microsecond=0)
    inicio7 = (corte.replace(hour=0, minute=0, second=0) - timedelta(days=6)).isoformat()
    hoje = corte.date().isoformat()
    with conectar("monitor_packball.db") as c:
        linhas = c.execute("""
          WITH envios AS (
            SELECT sinal_id, MIN(entregue_em) enviado_em FROM entregas_alertas
            WHERE status='entregue' AND provedor_mensagem_id IS NOT NULL
              AND (canal NOT LIKE '%:%' OR canal LIKE '%:teste')
            GROUP BY sinal_id
          )
          SELECT s.id,s.partida_id,s.mercado,s.regra_versao,s.features_json,
                 s.odd,e.enviado_em,r.resultado,r.retorno_unidades,
                 p.pais,p.liga,p.mandante,p.visitante,
                 sn.coletado_em,sn.contexto_api_json
          FROM envios e JOIN sinais s ON s.id=e.sinal_id
          JOIN partidas p ON p.id=s.partida_id JOIN snapshots sn ON sn.id=s.snapshot_id
          LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE s.mercado='gol_ht' AND e.enviado_em<=?
          ORDER BY e.enviado_em,s.id
        """, (corte.isoformat(),)).fetchall()
    itens = []
    vistos = set()
    duplicatas = []
    for linha in linhas:
        item = dict(linha)
        f = json.loads(item["features_json"] or "{}")
        item["metodo"] = (f.get("exploracao_sombra") or {}).get("versao") or item["regra_versao"]
        chave = (item["partida_id"], item["metodo"])
        if chave in vistos:
            duplicatas.append(item["id"])
            continue
        vistos.add(chave)
        if item["metodo"] == METODO:
            item["filtro_retrospectivo"] = avaliar_chutes_ht(
                item, item, datetime.fromisoformat(item["enviado_em"]), {ROLLBACK: "1"})
        item.pop("features_json")
        item.pop("contexto_api_json")
        itens.append(item)
    alvo = [x for x in itens if x["metodo"] == METODO]
    periodos = {"historico_mesma_versao": alvo,
                "ultimos_7_dias": [x for x in alvo if x["enviado_em"] >= inicio7],
                "hoje": [x for x in alvo if x["enviado_em"][:10] == hoje]}
    resumo = {}
    for nome, dados in periodos.items():
        veto = [x for x in dados if not x["filtro_retrospectivo"]["aprovada"]]
        mantidos = [x for x in dados if x not in veto]
        grupos = defaultdict(list)
        for item in dados:
            a = item["filtro_retrospectivo"]
            grupo = "zero_confirmado" if not a["aprovada"] else "positivo_confirmado" if a.get("chutes_total", 0) > 0 else "indisponivel"
            grupos[grupo].append(item)
        resumo[nome] = {"total": metricas(dados), "ligas": resumir_ligas(dados),
                       "filtro": {"vetados": metricas(veto), "mantidos": metricas(mantidos),
                                  "grupos": {k: metricas(v) for k, v in grupos.items()},
                                  "ids_vetados": [x["id"] for x in veto]}}
    outros = defaultdict(list)
    for item in itens:
        if item["metodo"] != METODO and item["enviado_em"] >= inicio7:
            outros[item["metodo"]].append(item)
    return {"corte": corte.isoformat(), "inicio7": inicio7, "metodo_alvo": METODO,
            "duplicatas_mesmo_jogo_metodo_excluidas": duplicatas,
            "periodos": resumo,
            "outros_metodos_ht_7dias": {k: {"total": metricas(v), "ligas": resumir_ligas(v)} for k, v in outros.items()},
            "entradas_alvo": alvo,
            "limite": "Retrospectivo e exploratório. Não estima benefício futuro; liga negativa não implica causa nem bloqueio automático."}


if __name__ == "__main__":
    print(json.dumps(auditar(), ensure_ascii=True))
