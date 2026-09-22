"""Audita cortes conservadores nos bilhetes pre-live entregues/listados.

Somente leitura. O relatorio separa o historico em uma parte antiga e outra
recente para reduzir o risco de aprovar um filtro que apenas decorou o total.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path


VERSAO_ALVO = "seletor-pre-live-retorno-dia30-odd150-v12"
MERCADOS_FRACOS = {"multigols_time", "time_marca_gol"}


def _conectar():
    caminho = Path("pre_live.db").resolve()
    conexao = sqlite3.connect(caminho.as_uri() + "?mode=ro", uri=True)
    conexao.row_factory = sqlite3.Row
    return conexao


def _carregar():
    with _conectar() as conexao:
        linhas = conexao.execute(
            """
            WITH publicados AS (
                SELECT b.id, MIN(e.criado_em) publicado_em
                FROM bilhetes_pre_live b
                JOIN entregas_pre_live e ON e.bilhete_id=b.id
                WHERE e.mensagem_id IS NOT NULL
                GROUP BY b.id
                UNION ALL
                SELECT b.id, MIN(l.criado_em) publicado_em
                FROM bilhetes_pre_live b
                JOIN itens_listas_pre_live i ON i.bilhete_id=b.id
                JOIN listas_pre_live l ON l.id=i.lista_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM entregas_pre_live e
                    WHERE e.bilhete_id=b.id AND e.mensagem_id IS NOT NULL
                )
                GROUP BY b.id
            )
            SELECT b.id, b.criado_em, MIN(p.publicado_em) publicado_em,
                   b.resultado, b.retorno_unidades, b.bilhete_json
            FROM bilhetes_pre_live b
            JOIN publicados p ON p.id=b.id
            WHERE b.versao=?
            GROUP BY b.id
            ORDER BY publicado_em, b.id
            """,
            (VERSAO_ALVO,),
        ).fetchall()
    itens = []
    for linha in linhas:
        item = dict(linha)
        item["bilhete"] = json.loads(item.pop("bilhete_json") or "{}")
        itens.append(item)
    return itens


def _tema_perna(perna):
    mercado = str(perna.get("mercado") or "")
    selecao = str(perna.get("selecao") or "")
    if mercado in {
        "total_gols", "chance_dupla_mais_gols", "resultado_mais_gols",
        "total_gols_mais_ambas",
    }:
        if "under_" in selecao:
            return "under"
        if "over_" in selecao:
            return "over"
    if mercado in {"multigols", "multigols_time"}:
        return "multigols"
    if mercado == "time_marca_gol":
        return "time_marca"
    if mercado in {"resultado", "chance_dupla"}:
        return "resultado_protegido"
    if mercado in {"ambas_marcam", "resultado_mais_ambas"}:
        return "ambas_marcam"
    return "outro"


def _tema_bilhete(bilhete):
    temas = {_tema_perna(perna) for perna in bilhete.get("pernas") or []}
    temas.discard("outro")
    if len(temas) == 1:
        return next(iter(temas))
    return "misto" if temas else "outro"


def _passa(item, modo):
    bilhete = item["bilhete"]
    pernas = list(bilhete.get("pernas") or [])
    if not pernas:
        return False
    sem_mercados_fracos = all(
        str(perna.get("mercado") or "") not in MERCADOS_FRACOS
        for perna in pernas
    )
    nao_e_under_multipla = not (
        len(pernas) > 1 and _tema_bilhete(bilhete) == "under"
    )
    base = sem_mercados_fracos and nao_e_under_multipla
    if modo == "base":
        return base

    qualidade = min(
        (float(perna.get("qualidade_contexto") or 0.0) for perna in pernas),
        default=0.0,
    )
    if modo == "qualidade85":
        return base and qualidade >= 85.0

    edges_perna = [
        float(perna.get("edge_conservador", perna.get("edge_modelo") or 0.0))
        for perna in pernas
    ]
    if modo == "qualidade85_edge_perna_nao_negativo":
        return base and qualidade >= 85.0 and min(edges_perna) >= 0.0

    edge_bilhete = float(
        bilhete.get("edge_conservador", bilhete.get("edge_modelo") or 0.0)
    )
    if modo == "qualidade85_edge_bilhete4":
        return base and qualidade >= 85.0 and edge_bilhete >= 0.04
    raise ValueError(modo)


def _metricas(itens):
    resolvidos = [
        item for item in itens
        if item.get("resultado") in {"green", "red"}
        and item.get("retorno_unidades") is not None
    ]
    resultados = Counter(item["resultado"] for item in resolvidos)
    lucro = sum(float(item["retorno_unidades"]) for item in resolvidos)
    n = len(resolvidos)
    return {
        "publicados": len(itens),
        "resolvidos": n,
        "green": resultados["green"],
        "red": resultados["red"],
        "acerto_pct": round(100.0 * resultados["green"] / n, 2) if n else None,
        "lucro_u": round(lucro, 4),
        "roi_pct": round(100.0 * lucro / n, 2) if n else None,
    }


def _janela(itens, inicio, fim):
    return itens[inicio:fim]


def main():
    itens = _carregar()
    resolvidos = [item for item in itens if item.get("resultado") in {"green", "red"}]
    corte = max(round(len(resolvidos) * 0.70), 1)
    modos = [
        "sem_filtro",
        "base",
        "qualidade85",
        "qualidade85_edge_perna_nao_negativo",
        "qualidade85_edge_bilhete4",
    ]
    saida = {
        "versao": VERSAO_ALVO,
        "resolvidos_total": len(resolvidos),
        "corte_temporal_70_pct": corte,
        "variantes": {},
    }
    for modo in modos:
        filtrados = resolvidos if modo == "sem_filtro" else [
            item for item in resolvidos if _passa(item, modo)
        ]
        antigos = resolvidos[:corte]
        recentes = resolvidos[corte:]
        antigos = antigos if modo == "sem_filtro" else [
            item for item in antigos if _passa(item, modo)
        ]
        recentes = recentes if modo == "sem_filtro" else [
            item for item in recentes if _passa(item, modo)
        ]
        saida["variantes"][modo] = {
            "todos": _metricas(filtrados),
            "antigos_70_pct": _metricas(antigos),
            "recentes_30_pct": _metricas(recentes),
        }
    print(json.dumps(saida, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
