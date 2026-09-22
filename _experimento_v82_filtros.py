"""Busca somente leitura por filtros simples que sobrevivam ao holdout final."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime

from probabilidade_individual import carregar_base
from probabilidade_individual_sem_vig import (
    _probabilidade_referencia,
    anexar_referencia_sem_vig,
)


DB = "file:monitor_packball.db?mode=ro"
FOLD = 30


def wilson(verdes, total):
    if not total:
        return [None, None]
    z = 1.96
    p = verdes / total
    d = 1 + z * z / total
    c = (p + z * z / (2 * total)) / d
    m = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / d
    return [c - m, c + m]


def valor(item, nome):
    if nome == "probabilidade_mercado":
        return _probabilidade_referencia(item)
    if nome == "odd":
        return float(item["odd"])
    if nome == "minuto":
        return float(item["minuto"])
    if nome == "forca_total":
        a = item["valores"].get("ataque_casa_defesa_fora")
        b = item["valores"].get("ataque_fora_defesa_casa")
        return a + b if a is not None and b is not None else None
    return item["valores"].get(nome)


def predicado(nome, campo, operador, limite):
    def aplicar(item):
        atual = valor(item, campo)
        if atual is None:
            return False
        return atual >= limite if operador == ">=" else atual <= limite
    return {"nome": nome, "aplicar": aplicar}


def candidatos(mercado):
    regras = []
    for limite in (0.48, 0.52, 0.56, 0.60, 0.64):
        regras.append(predicado(
            f"probabilidade_mercado>={limite}",
            "probabilidade_mercado", ">=", limite,
        ))
    for limite in (1.60, 1.70, 1.80, 1.90, 2.00, 2.20):
        regras.append(predicado(f"odd<={limite}", "odd", "<=", limite))
    minutos = (15, 20, 25, 30, 35) if mercado == "gol_ht" else (45, 55, 65, 70, 75)
    for limite in minutos:
        regras.append(predicado(f"minuto<={limite}", "minuto", "<=", limite))
    restantes = (10, 15, 20, 25, 30) if mercado == "gol_ht" else (15, 20, 25, 30, 35, 45)
    for limite in restantes:
        regras.append(predicado(
            f"tempo_restante>={limite}", "tempo_restante", ">=", limite,
        ))
    for limite in (2.0, 2.5, 3.0, 3.5, 4.0):
        regras.append(predicado(f"forca_total>={limite}", "forca_total", ">=", limite))
    for campo, limites in (
        ("chutes_5min", (1, 2, 3, 4)),
        ("pressao_5min", (50, 70, 90, 110)),
        ("xg_5min", (0.05, 0.10, 0.20, 0.35)),
    ):
        for limite in limites:
            regras.append(predicado(f"{campo}>={limite}", campo, ">=", limite))
    regras.append(predicado("sem_vermelho", "vermelhos", "<=", 0))

    # Combinações definidas antes de consultar os resultados do holdout.
    simples = list(regras)
    probabilidade = [
        item for item in simples if item["nome"].startswith("probabilidade")
    ]
    contexto = [
        item for item in simples
        if item["nome"].startswith((
            "forca_total", "chutes_5min", "pressao_5min",
            "xg_5min", "tempo_restante",
        ))
    ]
    for primeira in probabilidade:
        for segunda in contexto:
            regras.append({
                "nome": primeira["nome"] + " E " + segunda["nome"],
                "aplicar": lambda item, a=primeira["aplicar"], b=segunda["aplicar"]: a(item) and b(item),
            })
    return regras


def metricas(itens):
    n = len(itens)
    verdes = sum(int(item["alvo"]) for item in itens)
    retorno = sum(
        float(item["odd"]) - 1.0 if item["alvo"] else -1.0
        for item in itens
    )
    return {
        "n": n,
        "greens": verdes,
        "hit_rate": verdes / n if n else None,
        "wilson95": wilson(verdes, n),
        "retorno": retorno,
        "roi": retorno / n if n else None,
    }


def avaliar_mercado(conexao, mercado):
    agora = datetime.now().replace(microsecond=0).isoformat()
    bruta = carregar_base(conexao, mercado, agora)
    base, auditoria = anexar_referencia_sem_vig(conexao, bruta)
    base.sort(key=lambda item: (str(item["criado_em"]), int(item["sinal_id"])))
    inicio = len(base) - 90
    dev_folds = [base[inicio:inicio + FOLD], base[inicio + FOLD:inicio + 2 * FOLD]]
    holdout = base[inicio + 2 * FOLD:inicio + 3 * FOLD]
    bases_dev = [metricas(itens) for itens in dev_folds]
    candidatos_validos = []
    for regra in candidatos(mercado):
        filtrados = [
            [item for item in itens if regra["aplicar"](item)]
            for itens in dev_folds
        ]
        resumos = [metricas(itens) for itens in filtrados]
        if min(item["n"] for item in resumos) < 15:
            continue
        delta_hit = [
            item["hit_rate"] - base_fold["hit_rate"]
            for item, base_fold in zip(resumos, bases_dev)
        ]
        delta_roi = [
            item["roi"] - base_fold["roi"]
            for item, base_fold in zip(resumos, bases_dev)
        ]
        # Exige consistência nos dois blocos, não só uma média favorável.
        if min(delta_hit) < 0 or min(delta_roi) < 0:
            continue
        candidatos_validos.append({
            "nome": regra["nome"],
            "regra": regra,
            "dev": resumos,
            "delta_hit_minimo": min(delta_hit),
            "delta_hit_medio": sum(delta_hit) / len(delta_hit),
            "delta_roi_minimo": min(delta_roi),
            "delta_roi_medio": sum(delta_roi) / len(delta_roi),
            "retidos": sum(item["n"] for item in resumos),
        })
    candidatos_validos.sort(key=lambda item: (
        -item["delta_hit_minimo"],
        -item["delta_roi_minimo"],
        -item["retidos"],
        item["nome"],
    ))
    escolhido = candidatos_validos[0] if candidatos_validos else None
    if escolhido is None:
        return {
            "mercado": mercado,
            "amostra": len(base),
            "baseline_dev": bases_dev,
            "baseline_holdout": metricas(holdout),
            "candidatos_consistentes_dev": 0,
            "escolhido": None,
            "promover_para_sombra": False,
            "auditoria_referencia": auditoria,
        }
    filtrado_holdout = [
        item for item in holdout if escolhido["regra"]["aplicar"](item)
    ]
    resumo_holdout = metricas(filtrado_holdout)
    baseline_holdout = metricas(holdout)
    delta_hit_holdout = (
        resumo_holdout["hit_rate"] - baseline_holdout["hit_rate"]
        if resumo_holdout["n"] else None
    )
    delta_roi_holdout = (
        resumo_holdout["roi"] - baseline_holdout["roi"]
        if resumo_holdout["n"] else None
    )
    escolhido_publico = {
        chave: valor for chave, valor in escolhido.items() if chave != "regra"
    }
    escolhido_publico.update({
        "holdout": resumo_holdout,
        "baseline_holdout": baseline_holdout,
        "delta_hit_holdout": delta_hit_holdout,
        "delta_roi_holdout": delta_roi_holdout,
    })
    return {
        "mercado": mercado,
        "amostra": len(base),
        "baseline_dev": bases_dev,
        "baseline_holdout": baseline_holdout,
        "candidatos_consistentes_dev": len(candidatos_validos),
        "top5_dev": [
            {chave: valor for chave, valor in item.items() if chave != "regra"}
            for item in candidatos_validos[:5]
        ],
        "escolhido": escolhido_publico,
        "promover_para_sombra": bool(
            resumo_holdout["n"] >= 15
            and delta_hit_holdout is not None and delta_hit_holdout >= 0.05
            and delta_roi_holdout is not None and delta_roi_holdout >= 0
            and escolhido["delta_hit_medio"] >= 0.05
        ),
        "auditoria_referencia": auditoria,
        "aplicacao_sinais": False,
        "escritas_sqlite": 0,
    }


def main():
    conexao = sqlite3.connect(DB, uri=True, timeout=30)
    conexao.row_factory = sqlite3.Row
    try:
        resultado = {
            mercado: avaliar_mercado(conexao, mercado)
            for mercado in ("gol_ft", "gol_ht")
        }
    finally:
        conexao.close()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
