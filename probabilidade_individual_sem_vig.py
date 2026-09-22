"""Challenger de probabilidade individual contra mercado sem margem.

Esta versão é estritamente observacional. Ela reconstrói o par Over/Under do
mesmo snapshot, remove a margem da bookmaker e usa essa probabilidade como
offset. O contexto precisa acrescentar informação fora da amostra para que um
modelo possa sequer iniciar uma coorte prospectiva.

O módulo não escreve no banco, não altera sinais e não envia Telegram.
"""

from __future__ import annotations

import math
from collections import Counter

from avaliacao_probabilidade_sem_vig import (
    _carregar_odds_snapshots,
    _probabilidade_sem_vig,
)
from probabilidade_individual import (
    COBERTURA_FEATURE,
    ERRO_CALIBRACAO_MAX_V2,
    FOLDS_V2,
    MELHORA_BRIER_MINIMA_V2,
    MIN_CLASSE_TREINO,
    MIN_CLASSE_VALIDACAO,
    MIN_TREINO,
    PASSO_V2,
    TAMANHO_FOLD_V2,
    TOLERANCIA_BRIER_FOLD_V2,
    _hash,
    _metricas_v2,
    _sigmoide,
    numero,
)
from valor_mercado import (
    anexar_par_odds_sincronizado,
    avaliar_margem_bookmaker,
)


VERSAO = "individual-logistica-offset-mercado-sem-vig-walkforward-v3"
FEATURES = (
    "tempo_restante",
    "gols_atuais",
    "diferenca_placar",
    "gols_necessarios",
    "ataque_casa_defesa_fora",
    "ataque_fora_defesa_casa",
    "chutes_5min",
    "pressao_5min",
    "xg_5min",
    "vermelhos",
)
L2 = 3.0
ITERACOES = 500
COBERTURA_MINIMA = 0.95
MELHORA_BRIER_MINIMA = MELHORA_BRIER_MINIMA_V2
ERRO_CALIBRACAO_MAXIMO = ERRO_CALIBRACAO_MAX_V2
TOLERANCIA_BRIER_FOLD = TOLERANCIA_BRIER_FOLD_V2


def anexar_referencia_sem_vig(conexao, registros):
    """Anexa apenas pares exatos e sincronizados, sem consultar desfechos."""
    registros = [dict(item) for item in (registros or [])]
    odds_por_snapshot = _carregar_odds_snapshots(
        conexao,
        [item.get("snapshot_id") for item in registros
         if item.get("snapshot_id") is not None],
    )
    validos = []
    exclusoes = Counter()
    margens = []
    for item in registros:
        try:
            snapshot_id = int(item["snapshot_id"])
        except (KeyError, TypeError, ValueError, OverflowError):
            exclusoes["snapshot_invalido"] += 1
            continue
        mercados = odds_por_snapshot.get(snapshot_id, [])
        if not mercados:
            exclusoes["snapshot_sem_odds_ao_vivo"] += 1
            continue
        candidato = {
            "mercado": item.get("mercado"),
            "linha": item.get("linha"),
            "odd": item.get("odd"),
            "fonte_odds": item.get("fonte_odds"),
            "bookmaker_odds": item.get("bookmaker_odds"),
            "features": {
                "fonte_odds": item.get("fonte_odds"),
                "bookmaker_odds": item.get("bookmaker_odds"),
            },
        }
        if not anexar_par_odds_sincronizado(
            candidato, {"ao_vivo": mercados}
        ):
            exclusoes["mercado_exato_incompleto_ou_ambiguo"] += 1
            continue
        referencia = _probabilidade_sem_vig(candidato)
        odd = numero(item.get("odd"))
        odd_oposta = numero(candidato.get("odd_oposta"))
        if referencia is None or odd is None or odd_oposta is None:
            exclusoes["referencia_sem_vig_indisponivel"] += 1
            continue
        qualidade = avaliar_margem_bookmaker(
            "binaria", [odd, odd_oposta]
        )
        probabilidade = numero(referencia.get("probabilidade"))
        if not qualidade.get("plausivel"):
            exclusoes["margem_bookmaker_implausivel"] += 1
            continue
        if probabilidade is None or not 0 < probabilidade < 1:
            exclusoes["probabilidade_sem_vig_invalida"] += 1
            continue
        novo = dict(item)
        novo.update({
            "probabilidade_mercado_sem_vig": probabilidade,
            "margem_bookmaker": float(qualidade["margem_bookmaker"]),
            "odd_oposta": odd_oposta,
            "tipo_referencia_mercado": "binaria_mesmo_snapshot",
        })
        validos.append(novo)
        margens.append(float(qualidade["margem_bookmaker"]))
    total = len(registros)
    cobertura = len(validos)
    return validos, {
        "total": total,
        "com_referencia_sem_vig": cobertura,
        "sem_referencia_sem_vig": total - cobertura,
        "taxa_cobertura": cobertura / total if total else None,
        "cobertura_minima": COBERTURA_MINIMA,
        "cobertura_suficiente": bool(
            total and cobertura / total >= COBERTURA_MINIMA
        ),
        "margem_bookmaker_media": (
            sum(margens) / len(margens) if margens else None
        ),
        "exclusoes": dict(exclusoes),
        "referencia": "over_under_mesmo_snapshot_sem_vig",
        "consulta_resultado": False,
        "aplicacao_sinais": False,
        "telegram": False,
    }


def _probabilidade_referencia(item):
    probabilidade = numero(item.get("probabilidade_mercado_sem_vig"))
    if probabilidade is None or not 0 < probabilidade < 1:
        raise ValueError("referencia_sem_vig_invalida")
    return max(0.02, min(0.98, probabilidade))


def _logit(probabilidade):
    probabilidade = max(0.02, min(0.98, float(probabilidade)))
    return math.log(probabilidade / (1 - probabilidade))


def _vetor(modelo, entrada):
    vetor = []
    for nome in modelo["features"]:
        valor = entrada["valores"].get(nome)
        vetor.extend((
            0 if valor is None else max(
                -4,
                min(
                    4,
                    (valor - modelo["medias"][nome])
                    / modelo["desvios"][nome],
                ),
            ),
            int(valor is None),
        ))
    vetor.extend(
        int(entrada["metodo"] == item) for item in modelo["metodos"]
    )
    vetor.extend(
        int(entrada["segmento"] == item) for item in modelo["segmentos"]
    )
    return vetor


def ajustar(registros):
    verdes = sum(int(item["alvo"]) for item in registros)
    if (
        len(registros) < MIN_TREINO
        or min(verdes, len(registros) - verdes) < MIN_CLASSE_TREINO
    ):
        raise ValueError("amostra_treino_insuficiente")
    modelo = {
        "versao": VERSAO,
        "features": [],
        "medias": {},
        "desvios": {},
        "dominio": {},
        "metodos": sorted({item["metodo"] for item in registros}),
        "segmentos": sorted({item["segmento"] for item in registros}),
        "contagem_metodos": dict(Counter(
            item["metodo"] for item in registros
        )),
        "contagem_segmentos": dict(Counter(
            item["segmento"] for item in registros
        )),
    }
    for nome in FEATURES:
        valores = [
            item["valores"][nome]
            for item in registros
            if item["valores"].get(nome) is not None
        ]
        if len(valores) < COBERTURA_FEATURE * len(registros):
            continue
        media = sum(valores) / len(valores)
        desvio = math.sqrt(
            sum((valor - media) ** 2 for valor in valores) / len(valores)
        )
        modelo["dominio"][nome] = [min(valores), max(valores)]
        if desvio < 1e-8:
            continue
        modelo["features"].append(nome)
        modelo["medias"][nome] = media
        modelo["desvios"][nome] = desvio
    essenciais = {
        "tempo_restante",
        "ataque_casa_defesa_fora",
        "ataque_fora_defesa_casa",
    }
    if not essenciais <= set(modelo["features"]):
        raise ValueError("contexto_sem_variacao_para_modelar")
    matriz = [_vetor(modelo, item) for item in registros]
    pesos = [0.0] * len(matriz[0])
    intercepto = 0.0
    for _ in range(ITERACOES):
        gradiente_intercepto = 0.0
        gradiente = [0.0] * len(pesos)
        for vetor, item in zip(matriz, registros):
            previsto = _sigmoide(
                _logit(_probabilidade_referencia(item))
                + intercepto
                + sum(
                    peso * valor
                    for peso, valor in zip(pesos, vetor)
                )
            )
            erro = previsto - int(item["alvo"])
            gradiente_intercepto += erro
            for indice, valor in enumerate(vetor):
                gradiente[indice] += erro * valor
        intercepto -= PASSO_V2 * gradiente_intercepto / len(registros)
        pesos = [
            peso - PASSO_V2 * (
                gradiente_item / len(registros) + L2 * peso
            )
            for peso, gradiente_item in zip(pesos, gradiente)
        ]
    modelo.update({
        "pesos": pesos,
        "intercepto": intercepto,
        "amostra": len(registros),
        "sinais_treino": [item["sinal_id"] for item in registros],
        "base_hash": _hash(registros),
        "offset": "logit_probabilidade_mercado_sem_vig_mesmo_snapshot",
        "regularizacao_l2": L2,
    })
    return modelo


def prever(modelo, entrada):
    if modelo.get("versao") != VERSAO:
        raise ValueError("modelo_sem_vig_incompativel")
    return _sigmoide(
        _logit(_probabilidade_referencia(entrada))
        + float(modelo["intercepto"])
        + sum(
            peso * valor
            for peso, valor in zip(modelo["pesos"], _vetor(modelo, entrada))
        )
    )


def metricas(probabilidades, alvos, referencias):
    resultado = _metricas_v2(probabilidades, alvos, referencias)
    resultado["brier_mercado_sem_vig"] = resultado.pop(
        "brier_odd_bruta"
    )
    resultado["delta_brier_vs_mercado_sem_vig"] = resultado.pop(
        "delta_brier_vs_odd"
    )
    return resultado


def validar_walk_forward(registros, mercado, corte):
    """Três blocos futuros; aprovação apenas inicia coorte em sombra."""
    ordenados = sorted(
        registros,
        key=lambda item: (
            str(item.get("criado_em") or ""),
            int(item["sinal_id"]),
        ),
    )
    minimo = MIN_TREINO + FOLDS_V2 * TAMANHO_FOLD_V2
    saida = {
        "versao": VERSAO,
        "mercado": mercado,
        "corte": corte,
        "estado": "amostra_insuficiente",
        "amostra": len(ordenados),
        "minimo": minimo,
        "folds_esperados": FOLDS_V2,
        "folds": [],
        "modelo": None,
        "aprovado_para_coorte_prospectiva": False,
        "aplicacao_sinais": False,
        "telegram": False,
    }
    if len(ordenados) < minimo:
        return saida
    inicio_validacao = len(ordenados) - FOLDS_V2 * TAMANHO_FOLD_V2
    probabilidades = []
    referencias = []
    alvos = []
    sinais_validacao = []
    for indice in range(FOLDS_V2):
        inicio = inicio_validacao + indice * TAMANHO_FOLD_V2
        fim = inicio + TAMANHO_FOLD_V2
        validacao = ordenados[inicio:fim]
        marco = min(str(item["criado_em"]) for item in validacao)
        treino = [
            item for item in ordenados[:inicio]
            if str(item.get("encerrado_em") or "") < marco
        ]
        try:
            modelo = ajustar(treino)
        except ValueError as erro:
            saida["estado"] = str(erro)
            return saida
        ys = [int(item["alvo"]) for item in validacao]
        if min(sum(ys), len(ys) - sum(ys)) < MIN_CLASSE_VALIDACAO:
            saida["estado"] = "classe_validacao_insuficiente"
            return saida
        previsoes = [prever(modelo, item) for item in validacao]
        bases = [_probabilidade_referencia(item) for item in validacao]
        resumo = metricas(previsoes, ys, bases)
        resumo.update({
            "indice": indice + 1,
            "marco": marco,
            "treino": len(treino),
            "sinais": [item["sinal_id"] for item in validacao],
            "sinais_treino": [item["sinal_id"] for item in treino],
        })
        saida["folds"].append(resumo)
        probabilidades.extend(previsoes)
        referencias.extend(bases)
        alvos.extend(ys)
        sinais_validacao.extend(resumo["sinais"])
    agregado = metricas(probabilidades, alvos, referencias)
    nenhum_fold_regrediu = all(
        fold["delta_brier_vs_mercado_sem_vig"]
        <= TOLERANCIA_BRIER_FOLD
        for fold in saida["folds"]
    )
    aprovado = bool(
        agregado["delta_brier_vs_mercado_sem_vig"]
        <= -MELHORA_BRIER_MINIMA
        and agregado["delta_brier_vs_taxa_observada"]
        <= -MELHORA_BRIER_MINIMA
        and agregado["erro_calibracao"] <= ERRO_CALIBRACAO_MAXIMO
        and nenhum_fold_regrediu
    )
    saida.update({
        "estado": (
            "aprovado_para_coorte_prospectiva"
            if aprovado else "validacao_reprovada"
        ),
        "validacao": agregado,
        "sinais_validacao": sinais_validacao,
        "nenhum_fold_regrediu_vs_mercado_sem_vig": nenhum_fold_regrediu,
        "criterios": {
            "melhora_brier_minima": MELHORA_BRIER_MINIMA,
            "tolerancia_brier_fold": TOLERANCIA_BRIER_FOLD,
            "erro_calibracao_maximo": ERRO_CALIBRACAO_MAXIMO,
            "folds": FOLDS_V2,
            "tamanho_fold": TAMANHO_FOLD_V2,
            "referencia": "mercado_sem_vig_mesmo_snapshot",
        },
        "aprovado_para_coorte_prospectiva": aprovado,
    })
    if aprovado:
        saida["modelo"] = ajustar(ordenados)
    return saida
