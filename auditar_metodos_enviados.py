"""Comparação descritiva, somente leitura, de entradas entregues (sem sombra)."""
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def conectar(nome):
    c = sqlite3.connect(Path(nome).resolve().as_uri() + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def metricas(itens):
    resolvidos = [x for x in itens if x["resultado"] in
                  ("green", "red", "half_green", "half_red") and x["retorno_unidades"] is not None]
    r = Counter(x["resultado"] for x in resolvidos)
    n = len(resolvidos)
    lucro = sum(x["retorno_unidades"] for x in resolvidos)
    return {
        "enviados": len(itens), "resolvidos": n, "resultados": dict(r),
        "pendentes": sum(x["resultado"] is None for x in itens),
        "outros_resultados": dict(Counter(x["resultado"] for x in itens if x["resultado"] is not None and x not in resolvidos)),
        "acerto_percentual": round(100 * r["green"] / n, 2) if n else None,
        "lucro_unidades": round(lucro, 4), "roi_percentual": round(100 * lucro / n, 2) if n else None,
        "odd_media": round(sum(x["odd"] for x in resolvidos) / n, 3) if n else None,
    }


def resumir(itens, inicio=None):
    itens = [x for x in itens if inicio is None or x["enviado_em"] >= inicio]
    grupos = defaultdict(list)
    for x in itens:
        grupos[x["metodo"]].append(x)
    return {"total": metricas(itens), "metodos": {
        k: metricas(v) for k, v in sorted(grupos.items())
    }}


def carregar_live():
    with conectar("monitor_packball.db") as c:
        linhas = c.execute("""
          WITH envios AS (
            SELECT sinal_id, MIN(entregue_em) enviado_em
            FROM entregas_alertas
            WHERE status='entregue' AND provedor_mensagem_id IS NOT NULL
              AND (canal NOT LIKE '%:%' OR canal LIKE '%:teste')
            GROUP BY sinal_id
          )
          SELECT s.id, s.partida_id, s.mercado, s.regra_versao metodo,
                 s.odd, s.features_json, e.enviado_em, r.resultado, r.retorno_unidades
          FROM envios e JOIN sinais s ON s.id=e.sinal_id
          LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
          ORDER BY e.enviado_em, s.id
        """).fetchall()
    itens = [dict(x) for x in linhas]
    for x in itens:
        f = json.loads(x["features_json"] or "{}")
        versao = (f.get("exploracao_sombra") or {}).get("versao") or x["metodo"]
        x["metodo"] = x["mercado"] + " | " + versao
    return itens


def carregar_pre_live():
    with conectar("pre_live.db") as c:
        individuais = [dict(x) for x in c.execute("""
          SELECT b.id, b.tipo, b.versao metodo, b.bilhete_json, b.odd_total odd,
                 b.resultado, b.retorno_unidades, MIN(e.criado_em) enviado_em
          FROM bilhetes_pre_live b JOIN entregas_pre_live e ON e.bilhete_id=b.id
          WHERE e.mensagem_id IS NOT NULL GROUP BY b.id
        """)]
        listas = [dict(x) for x in c.execute("""
          SELECT b.id, b.tipo, b.versao metodo, i.bilhete_json, b.odd_total odd,
                 b.resultado, b.retorno_unidades, MIN(l.criado_em) enviado_em
          FROM bilhetes_pre_live b JOIN itens_listas_pre_live i ON i.bilhete_id=b.id
          JOIN listas_pre_live l ON l.id=i.lista_id
          WHERE NOT EXISTS (SELECT 1 FROM entregas_pre_live e WHERE e.bilhete_id=b.id AND e.mensagem_id IS NOT NULL)
          GROUP BY b.id
        """)]
    return individuais, listas


if __name__ == "__main__":
    agora = datetime.now()
    inicio7 = (agora.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)).isoformat()
    inicio2 = (agora - timedelta(days=2)).isoformat()
    live = carregar_live()
    pre, listas = carregar_pre_live()
    saida = {"corte": agora.isoformat(timespec="seconds"), "inicio7": inicio7,
             "ao_vivo": {"historico": resumir(live), "7dias": resumir(live, inicio7), "48h": resumir(live, inicio2)},
             "pre_live_individuais_confirmados": {"historico": resumir(pre), "7dias": resumir(pre, inicio7)},
             "pre_live_somente_lista_separado": {"historico": resumir(listas), "7dias": resumir(listas, inicio7)}}
    print(json.dumps(saida, ensure_ascii=True))
