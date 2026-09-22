"""Experimento somente leitura: challengers individuais contra preço sem margem.

Seleciona especificação e regularização nos dois primeiros blocos futuros e
abre o terceiro bloco somente depois da escolha. Não escreve no SQLite.
"""

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
VALIDACAO = 90
PASSO = 0.04
ITERACOES = 900


def sigmoide(valor):
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, valor))))


def logit(probabilidade):
    p = max(0.02, min(0.98, float(probabilidade)))
    return math.log(p / (1.0 - p))


def derivados(item):
    p = _probabilidade_referencia(item)
    valores = dict(item["valores"])
    valores.update({
        "logit_mercado": logit(p),
        "log_p": math.log(p),
        "log_1mp": math.log(1.0 - p),
        "clock_x_logit": (
            valores.get("tempo_restante") * logit(p)
            if valores.get("tempo_restante") is not None else None
        ),
        "forca_total": (
            valores.get("ataque_casa_defesa_fora")
            + valores.get("ataque_fora_defesa_casa")
            if valores.get("ataque_casa_defesa_fora") is not None
            and valores.get("ataque_fora_defesa_casa") is not None
            else None
        ),
    })
    return valores


ESPECIFICACOES = {
    "offset_intercepto": (True, ()),
    "offset_relogio": (True, ("tempo_restante",)),
    "offset_placar": (
        True,
        ("tempo_restante", "gols_necessarios", "gols_atuais",
         "diferenca_placar"),
    ),
    "offset_forca": (
        True,
        ("tempo_restante", "gols_necessarios", "gols_atuais",
         "diferenca_placar", "forca_total"),
    ),
    "offset_live": (
        True,
        ("tempo_restante", "gols_necessarios", "gols_atuais",
         "diferenca_placar", "forca_total", "chutes_5min",
         "pressao_5min", "xg_5min", "vermelhos"),
    ),
    "offset_interacao_preco": (
        True,
        ("tempo_restante", "gols_necessarios", "forca_total",
         "clock_x_logit"),
    ),
    "platt_mercado": (False, ("logit_mercado",)),
    "beta_mercado": (False, ("log_p", "log_1mp")),
    "beta_contexto": (
        False,
        ("log_p", "log_1mp", "tempo_restante", "gols_necessarios",
         "forca_total"),
    ),
}


def preparar(treino, nomes):
    selecionadas = []
    medias = {}
    desvios = {}
    for nome in nomes:
        valores = [
            derivados(item).get(nome) for item in treino
            if derivados(item).get(nome) is not None
        ]
        if len(valores) < 0.5 * len(treino):
            continue
        media = sum(valores) / len(valores)
        desvio = math.sqrt(
            sum((valor - media) ** 2 for valor in valores) / len(valores)
        )
        if desvio < 1e-10:
            continue
        selecionadas.append(nome)
        medias[nome] = media
        desvios[nome] = desvio
    return selecionadas, medias, desvios


def vetor(item, nomes, medias, desvios):
    valores = derivados(item)
    saida = []
    for nome in nomes:
        valor = valores.get(nome)
        saida.extend((
            0.0 if valor is None else max(
                -4.0, min(4.0, (valor - medias[nome]) / desvios[nome])
            ),
            float(valor is None),
        ))
    return saida


def ajustar(treino, especificacao, l2):
    offset, nomes_candidatos = ESPECIFICACOES[especificacao]
    nomes, medias, desvios = preparar(treino, nomes_candidatos)
    matriz = [vetor(item, nomes, medias, desvios) for item in treino]
    pesos = [0.0] * (len(matriz[0]) if matriz else 0)
    intercepto = 0.0
    for _ in range(ITERACOES):
        gradiente_i = 0.0
        gradientes = [0.0] * len(pesos)
        for item, linha in zip(treino, matriz):
            base = logit(_probabilidade_referencia(item)) if offset else 0.0
            previsto = sigmoide(
                base + intercepto
                + sum(peso * valor for peso, valor in zip(pesos, linha))
            )
            erro = previsto - int(item["alvo"])
            gradiente_i += erro
            for indice, valor in enumerate(linha):
                gradientes[indice] += erro * valor
        n = len(treino)
        intercepto -= PASSO * gradiente_i / n
        pesos = [
            peso - PASSO * (gradiente / n + l2 * peso)
            for peso, gradiente in zip(pesos, gradientes)
        ]
    return {
        "offset": offset,
        "nomes": nomes,
        "medias": medias,
        "desvios": desvios,
        "pesos": pesos,
        "intercepto": intercepto,
    }


def prever(modelo, item):
    linha = vetor(
        item, modelo["nomes"], modelo["medias"], modelo["desvios"]
    )
    base = (
        logit(_probabilidade_referencia(item)) if modelo["offset"] else 0.0
    )
    return sigmoide(
        base + modelo["intercepto"]
        + sum(peso * valor for peso, valor in zip(modelo["pesos"], linha))
    )


def brier(probabilidades, alvos):
    return sum(
        (probabilidade - alvo) ** 2
        for probabilidade, alvo in zip(probabilidades, alvos)
    ) / len(alvos)


def fold(ordenados, inicio, especificacao, l2):
    validacao = ordenados[inicio:inicio + FOLD]
    marco = min(str(item["criado_em"]) for item in validacao)
    treino = [
        item for item in ordenados[:inicio]
        if str(item.get("encerrado_em") or "") < marco
    ]
    modelo = ajustar(treino, especificacao, l2)
    alvos = [int(item["alvo"]) for item in validacao]
    probabilidades = [prever(modelo, item) for item in validacao]
    referencias = [_probabilidade_referencia(item) for item in validacao]
    return {
        "n": len(validacao),
        "treino": len(treino),
        "brier": brier(probabilidades, alvos),
        "brier_mercado": brier(referencias, alvos),
        "delta": brier(probabilidades, alvos) - brier(referencias, alvos),
        "greens": sum(alvos),
        "features": modelo["nomes"],
    }


def avaliar_mercado(conexao, mercado):
    agora = datetime.now().replace(microsecond=0).isoformat()
    bruta = carregar_base(conexao, mercado, agora)
    base, auditoria = anexar_referencia_sem_vig(conexao, bruta)
    ordenados = sorted(
        base,
        key=lambda item: (str(item["criado_em"]), int(item["sinal_id"])),
    )
    inicio = len(ordenados) - VALIDACAO
    candidatos = []
    for especificacao in ESPECIFICACOES:
        for l2 in (0.03, 0.1, 0.3, 1.0, 3.0, 10.0):
            folds = [
                fold(ordenados, inicio + indice * FOLD, especificacao, l2)
                for indice in (0, 1)
            ]
            candidatos.append({
                "especificacao": especificacao,
                "l2": l2,
                "delta_dev": sum(item["delta"] for item in folds) / 2,
                "folds_dev": folds,
            })
    candidatos.sort(key=lambda item: (item["delta_dev"], item["especificacao"], item["l2"]))
    escolhido = candidatos[0]
    holdout = fold(
        ordenados,
        inicio + 2 * FOLD,
        escolhido["especificacao"],
        escolhido["l2"],
    )
    return {
        "mercado": mercado,
        "amostra": len(ordenados),
        "auditoria_referencia": auditoria,
        "metodo_selecao": "menor_delta_brier_nos_dois_primeiros_blocos",
        "escolhido": escolhido,
        "holdout_final_nao_usado_na_escolha": holdout,
        "top5_desenvolvimento": candidatos[:5],
        "promover": bool(
            escolhido["delta_dev"] <= -0.002
            and holdout["delta"] <= -0.002
        ),
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
