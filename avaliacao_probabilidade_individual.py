"""Custódia prospectiva da probabilidade individual de gols HT/FT.

O avaliador pode congelar um challenger somente depois de validação cronológica
pré-declarada. As previsões são registradas antes do desfecho e nunca alteram
sinal, calibração oficial, prioridade ou Telegram automaticamente.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

from custodia_avaliacao import ESTADO_CONCLUIDO, VERSAO_CUSTODIA
from probabilidade_individual import (
    MERCADOS,
    carregar_base,
    extrair_entrada,
)
from probabilidade_individual_sem_vig import (
    COBERTURA_MINIMA as COBERTURA_REFERENCIA_MINIMA,
    VERSAO as VERSAO_MODELO,
    _probabilidade_referencia,
    anexar_referencia_sem_vig,
    metricas as metricas_modelo,
    prever as prever_modelo,
    validar_walk_forward as validar_modelo,
)


VERSAO = "avaliacao-probabilidade-individual-sem-vig-prospectiva-v2"
MOTIVO_FALHA_EXECUCAO = "avaliacao_probabilidade_individual_falhou"
PREFIXO_DEFINICAO = "avaliacao_probabilidade_individual:v2:definicao:"
PREFIXO_PREVISAO = "avaliacao_probabilidade_individual:v2:previsao:"
TAMANHO_COORTE = 60
DESENVOLVIMENTO = 42
HOLDOUT = 18
RESULTADOS_MINIMOS = 50
RESULTADOS_DESENVOLVIMENTO_MINIMOS = 35
RESULTADOS_HOLDOUT_MINIMOS = 15
MELHORA_BRIER_MINIMA = 0.002
ERRO_CALIBRACAO_MAXIMO = 0.10


def _json(valor):
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash(valor):
    return hashlib.sha256(_json(valor).encode("utf-8")).hexdigest()


def _data(valor):
    try:
        instante = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None
    return instante if instante.tzinfo is None else None


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _carregar_json_metadado(conexao, chave):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (str(chave),)
    ).fetchone()
    if linha is None:
        return None
    try:
        valor = json.loads(str(linha["valor"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return valor if isinstance(valor, dict) else None


def _validar_definicao(definicao, mercado):
    if not isinstance(definicao, dict):
        return False, "definicao_ausente"
    modelo = definicao.get("modelo")
    corpo = {chave: valor for chave, valor in definicao.items() if chave != "sha256"}
    criado = _data(definicao.get("criado_em"))
    if (
        definicao.get("avaliacao_versao") != VERSAO
        or definicao.get("modelo_versao") != VERSAO_MODELO
        or definicao.get("mercado") != mercado
        or criado is None
        or not isinstance(modelo, dict)
        or modelo.get("versao") != VERSAO_MODELO
        or definicao.get("modelo_sha256") != _hash(modelo)
        or definicao.get("sha256") != _hash(corpo)
    ):
        return False, "definicao_integra_invalida"
    return True, None


def _criar_definicao(mercado, validacao, criado_em):
    modelo = validacao.get("modelo")
    if not isinstance(modelo, dict):
        raise ValueError("modelo_validado_ausente")
    corpo = {
        "avaliacao_versao": VERSAO,
        "modelo_versao": VERSAO_MODELO,
        "mercado": mercado,
        "criado_em": str(criado_em),
        "unidade_independente": "primeiro_sinal_entregue_por_partida_e_mercado",
        "coorte_alvo": TAMANHO_COORTE,
        "desenvolvimento": DESENVOLVIMENTO,
        "holdout": HOLDOUT,
        "criterios_prospectivos": {
            "resultados_total": RESULTADOS_MINIMOS,
            "resultados_desenvolvimento": RESULTADOS_DESENVOLVIMENTO_MINIMOS,
            "resultados_holdout": RESULTADOS_HOLDOUT_MINIMOS,
            "melhora_brier_minima_vs_mercado_sem_vig": (
                MELHORA_BRIER_MINIMA
            ),
            "erro_calibracao_maximo": ERRO_CALIBRACAO_MAXIMO,
            "delta_brier_sem_vig_dev_e_holdout_maximo": 0.0,
            "cobertura_referencia_sem_vig_minima": (
                COBERTURA_REFERENCIA_MINIMA
            ),
        },
        "validacao_retro_hash": _hash({
            chave: valor
            for chave, valor in validacao.items()
            if chave != "modelo"
        }),
        "modelo_sha256": _hash(modelo),
        "modelo": modelo,
    }
    return {**corpo, "sha256": _hash(corpo)}


def _obter_ou_criar_definicao(banco, mercado, validacao, agora):
    chave = PREFIXO_DEFINICAO + mercado
    existente = _carregar_json_metadado(banco.conexao, chave)
    if existente is None and validacao.get("aprovado_para_coorte_prospectiva"):
        definicao = _criar_definicao(mercado, validacao, agora)
        with banco.conexao:
            banco.conexao.execute(
                "INSERT OR IGNORE INTO metadados(chave,valor) VALUES (?,?)",
                (chave, _json(definicao)),
            )
        existente = _carregar_json_metadado(banco.conexao, chave)
    valida, motivo = _validar_definicao(existente, mercado)
    return existente, valida, motivo


def _predicoes_existentes(conexao, mercado, definicao_sha):
    cursor = conexao.execute(
        "SELECT chave,valor FROM metadados WHERE chave LIKE ? ORDER BY chave",
        (PREFIXO_PREVISAO + mercado + ":%",),
    )
    predicoes = []
    invalidas = 0
    for linha in cursor:
        try:
            item = json.loads(str(linha["valor"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            invalidas += 1
            continue
        if not isinstance(item, dict):
            invalidas += 1
            continue
        corpo = {chave: valor for chave, valor in item.items() if chave != "sha256"}
        if (
            item.get("avaliacao_versao") != VERSAO
            or item.get("mercado") != mercado
            or item.get("definicao_sha256") != definicao_sha
            or item.get("sha256") != _hash(corpo)
            or _data(item.get("registrado_em")) is None
            or _numero(item.get("probabilidade")) is None
            or _numero(
                item.get("probabilidade_mercado_sem_vig")
            ) is None
            or _numero(item.get("margem_bookmaker")) is None
        ):
            invalidas += 1
            continue
        predicoes.append(item)
    predicoes.sort(
        key=lambda item: (
            str(item.get("registrado_em") or ""),
            int(item.get("sinal_id") or 0),
        )
    )
    return predicoes, invalidas


def _candidatos_futuros(conexao, mercado, inicio):
    cursor = conexao.execute(
        """
        WITH envios AS (
            SELECT sinal_id, MIN(entregue_em) AS entregue_em
            FROM entregas_alertas
            WHERE status='entregue' AND provedor_mensagem_id IS NOT NULL
              AND entregue_em IS NOT NULL
              AND (canal NOT LIKE '%:%' OR canal LIKE '%:teste')
            GROUP BY sinal_id
        )
        SELECT s.id,s.partida_id,s.snapshot_id,s.mercado,s.linha,s.odd,
               s.regra_versao,s.regra_fingerprint,s.features_json,s.criado_em,
               e.entregue_em,t.placar,t.contexto_api_json,t.coletado_em,
               p.mandante,p.visitante,p.liga,r.encerrado_em
        FROM sinais s
        JOIN envios e ON e.sinal_id=s.id
        JOIN snapshots t ON t.id=s.snapshot_id AND t.partida_id=s.partida_id
        JOIN partidas p ON p.id=s.partida_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado=? AND s.criado_em>=? AND e.entregue_em>=?
        ORDER BY e.entregue_em,s.id
        LIMIT 20000
        """,
        (mercado, str(inicio), str(inicio)),
    )
    nomes = [item[0] for item in cursor.description]
    return [dict(zip(nomes, linha)) for linha in cursor]


def _registrar_predicoes(banco, mercado, definicao, agora):
    predicoes, invalidas = _predicoes_existentes(
        banco.conexao, mercado, definicao["sha256"]
    )
    if invalidas:
        return predicoes, invalidas, 0
    faltam = max(TAMANHO_COORTE - len(predicoes), 0)
    if not faltam:
        return predicoes, 0, 0
    vistos = {int(item["partida_id"]) for item in predicoes}
    novas = []
    instante_agora = _data(agora)
    for linha in _candidatos_futuros(
        banco.conexao, mercado, definicao["criado_em"]
    ):
        partida_id = int(linha["partida_id"])
        if partida_id in vistos:
            continue
        # A primeira exposição define a unidade antes de qualquer desfecho.
        vistos.add(partida_id)
        criado = _data(linha["criado_em"])
        entregue = _data(linha["entregue_em"])
        coletado = _data(linha["coletado_em"])
        encerrado = _data(linha.get("encerrado_em"))
        if (
            criado is None
            or entregue is None
            or coletado is None
            or instante_agora is None
            or not coletado <= criado <= entregue <= instante_agora
            or (encerrado is not None and encerrado <= instante_agora)
        ):
            continue
        entrada = extrair_entrada(linha, linha, linha)
        if entrada is None:
            continue
        entrada.update({
            "snapshot_id": int(linha["snapshot_id"]),
        })
        entradas_referenciadas, auditoria_referencia = (
            anexar_referencia_sem_vig(banco.conexao, [entrada])
        )
        if (
            len(entradas_referenciadas) != 1
            or auditoria_referencia.get("cobertura_suficiente") is not True
        ):
            continue
        entrada = entradas_referenciadas[0]
        probabilidade = prever_modelo(definicao["modelo"], entrada)
        corpo = {
            "avaliacao_versao": VERSAO,
            "modelo_versao": VERSAO_MODELO,
            "definicao_sha256": definicao["sha256"],
            "mercado": mercado,
            "sinal_id": int(linha["id"]),
            "partida_id": partida_id,
            "criado_em": linha["criado_em"],
            "entregue_em": linha["entregue_em"],
            "registrado_em": str(agora),
            "probabilidade": round(probabilidade, 12),
            "probabilidade_mercado_sem_vig": round(
                _probabilidade_referencia(entrada), 12
            ),
            "margem_bookmaker": round(
                float(entrada["margem_bookmaker"]), 12
            ),
            "tipo_referencia_mercado": entrada[
                "tipo_referencia_mercado"
            ],
            "odd": round(float(linha["odd"]), 6),
        }
        item = {**corpo, "sha256": _hash(corpo)}
        chave = PREFIXO_PREVISAO + mercado + ":" + str(item["sinal_id"])
        with banco.conexao:
            banco.conexao.execute(
                "INSERT OR IGNORE INTO metadados(chave,valor) VALUES (?,?)",
                (chave, _json(item)),
            )
        persistida = _carregar_json_metadado(banco.conexao, chave)
        if persistida != item:
            return predicoes + novas, 1, len(novas)
        novas.append(item)
        if len(novas) >= faltam:
            break
    return predicoes + novas, 0, len(novas)


def _resultados_predicoes(conexao, predicoes):
    if not predicoes:
        return []
    por_id = {int(item["sinal_id"]): item for item in predicoes}
    marcadores = ",".join("?" for _ in por_id)
    cursor = conexao.execute(
        f"""
        SELECT sinal_id,resultado,retorno_unidades,encerrado_em
        FROM resultados_sinais WHERE sinal_id IN ({marcadores})
        """,
        tuple(por_id),
    )
    resultados = []
    for linha in cursor:
        item = por_id[int(linha["sinal_id"])]
        encerrado = _data(linha["encerrado_em"])
        registrado = _data(item["registrado_em"])
        retorno = _numero(linha["retorno_unidades"])
        resultado = linha["resultado"]
        coerente = (
            encerrado is not None
            and registrado is not None
            and registrado < encerrado
            and retorno is not None
            and (
                (resultado == "green" and retorno > 0)
                or (resultado == "red" and retorno < 0)
            )
        )
        if coerente:
            resultados.append({
                **item,
                "alvo": int(resultado == "green"),
                "resultado": resultado,
                "retorno_unidades": retorno,
                "encerrado_em": linha["encerrado_em"],
            })
    resultados.sort(
        key=lambda item: predicoes.index(por_id[int(item["sinal_id"])])
    )
    return resultados


def _resumir_resultados(itens):
    if not itens:
        return {
            "n": 0,
            "greens": 0,
            "reds": 0,
            "brier": None,
            "brier_mercado_sem_vig": None,
            "delta_brier_vs_mercado_sem_vig": None,
            "erro_calibracao": None,
        }
    return metricas_modelo(
        [float(item["probabilidade"]) for item in itens],
        [int(item["alvo"]) for item in itens],
        [
            float(item["probabilidade_mercado_sem_vig"])
            for item in itens
        ],
    )


def _resumir_coorte(conexao, predicoes):
    resultados = _resultados_predicoes(conexao, predicoes)
    posicao = {int(item["sinal_id"]): indice for indice, item in enumerate(predicoes)}
    desenvolvimento = [
        item for item in resultados
        if posicao[int(item["sinal_id"])] < DESENVOLVIMENTO
    ]
    holdout = [
        item for item in resultados
        if DESENVOLVIMENTO <= posicao[int(item["sinal_id"])] < TAMANHO_COORTE
    ]
    total = _resumir_resultados(resultados)
    dev = _resumir_resultados(desenvolvimento)
    teste = _resumir_resultados(holdout)
    pronta = bool(
        total["n"] >= RESULTADOS_MINIMOS
        and dev["n"] >= RESULTADOS_DESENVOLVIMENTO_MINIMOS
        and teste["n"] >= RESULTADOS_HOLDOUT_MINIMOS
    )
    favoravel = bool(
        pronta
        and total["delta_brier_vs_mercado_sem_vig"]
        <= -MELHORA_BRIER_MINIMA
        and dev["delta_brier_vs_mercado_sem_vig"] <= 0
        and teste["delta_brier_vs_mercado_sem_vig"] <= 0
        and total["erro_calibracao"] <= ERRO_CALIBRACAO_MAXIMO
    )
    return {
        "candidatos": len(predicoes),
        "resultados": len(resultados),
        "pendentes": len(predicoes) - len(resultados),
        "faltam_candidatos": max(TAMANHO_COORTE - len(predicoes), 0),
        "faltam_resultados": max(RESULTADOS_MINIMOS - len(resultados), 0),
        "total": total,
        "desenvolvimento": dev,
        "holdout": teste,
        "pronta_para_revisao": pronta,
        "vantagem_preditiva_prospectiva": favoravel,
    }


def avaliar_probabilidade_individual(banco, *, agora=None):
    agora = str(
        agora or datetime.now().replace(microsecond=0).isoformat()
    )
    mercados = {}
    integridade = True
    for mercado in sorted(MERCADOS):
        base_bruta = carregar_base(banco.conexao, mercado, agora)
        base, auditoria_referencia = anexar_referencia_sem_vig(
            banco.conexao, base_bruta
        )
        if auditoria_referencia.get("cobertura_suficiente") is True:
            retro = validar_modelo(base, mercado, agora)
        else:
            retro = {
                "versao": VERSAO_MODELO,
                "mercado": mercado,
                "corte": agora,
                "estado": "cobertura_referencia_sem_vig_insuficiente",
                "amostra": len(base),
                "minimo": 0,
                "folds_esperados": 3,
                "folds": [],
                "modelo": None,
                "aprovado_para_coorte_prospectiva": False,
                "aplicacao_sinais": False,
                "telegram": False,
            }
        definicao, definicao_valida, motivo_definicao = (
            _obter_ou_criar_definicao(banco, mercado, retro, agora)
        )
        if definicao is None:
            coorte = _resumir_coorte(banco.conexao, [])
            estado = "aguardando_modelo_retro_validado"
            novas = 0
            invalidas = 0
        elif not definicao_valida:
            coorte = _resumir_coorte(banco.conexao, [])
            estado = "definicao_integra_invalida"
            novas = 0
            invalidas = 1
            integridade = False
        else:
            predicoes, invalidas, novas = _registrar_predicoes(
                banco, mercado, definicao, agora
            )
            if invalidas:
                integridade = False
                estado = "predicao_integra_invalida"
            else:
                estado = "coleta_prospectiva"
            coorte = _resumir_coorte(banco.conexao, predicoes)
        mercados[mercado] = {
            "estado": estado,
            "amostra_retro_bruta": len(base_bruta),
            "amostra_retro": len(base),
            "auditoria_referencia_sem_vig": auditoria_referencia,
            "validacao_retro": {
                chave: valor for chave, valor in retro.items()
                if chave != "modelo"
            },
            "definicao_presente": definicao is not None,
            "definicao_valida": bool(definicao_valida),
            "motivo_definicao": motivo_definicao,
            "definicao_sha256": (
                definicao.get("sha256") if isinstance(definicao, dict) else None
            ),
            "novas_predicoes": novas,
            "predicoes_invalidas": invalidas,
            "coorte_prospectiva": coorte,
        }
    return {
        "versao": VERSAO,
        "custodia_execucao_versao": VERSAO_CUSTODIA,
        "estado_execucao": ESTADO_CONCLUIDO,
        "modo": "sombra_prospectiva",
        "estado": "saudavel" if integridade else "integridade_invalida",
        "integridade": integridade,
        "modelo_versao": VERSAO_MODELO,
        "mercados": mercados,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "altera_prioridade": False,
        "promocao_automatica": False,
        "reativacao_automatica": False,
        "telegram": False,
        "recomendacao": (
            "bloquear_inferencia_e_corrigir_integridade"
            if not integridade
            else "revisao_independente_sem_promocao"
            if any(
                item["coorte_prospectiva"]["vantagem_preditiva_prospectiva"]
                for item in mercados.values()
            )
            else "continuar_validacao_e_coleta_prospectiva"
        ),
    }
