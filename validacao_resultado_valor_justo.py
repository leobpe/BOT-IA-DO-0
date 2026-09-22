"""Valida prospectivamente o resultado do valor justo sincronizado.

A politica fica embutida no sinal antes do desfecho. A leitura posterior usa
somente o primeiro candidato elegivel de cada partida e mercado, separa edge
de controle e nunca promove uma conclusao automaticamente.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone


VERSAO_MEDIDOR = "melhor-preco-exato-sombra-v6-resultado-prospectivo"
VERSAO_VALOR_JUSTO = "desajuste-preco-justo-exato-sombra-v3-resultado"
VERSAO = "validacao-resultado-valor-justo-sincronizado-v1"
VERSAO_TRANSFERENCIA = "validacao-transferencia-valor-justo-origem-v1"

# Marco registrado antes de qualquer resultado da nova comparacao por origem.
# O relogio do SQLite e interpretado pela mesma rotina usada para os sinais.
ANCORA_TRANSFERENCIA = "2026-09-12T18:20:00-04:00"

TAMANHO_COORTE_POR_MERCADO = 100
DESENVOLVIMENTO = 70
HOLDOUT = 30
RESULTADOS_MINIMOS = 80
RESULTADOS_DEV_MINIMOS = 55
RESULTADOS_HOLDOUT_MINIMOS = 25
RESULTADOS_EDGE_MINIMOS = 30
RESULTADOS_CONTROLE_MINIMOS = 30
RESULTADOS_EDGE_HOLDOUT_MINIMOS = 8
RESULTADOS_CONTROLE_HOLDOUT_MINIMOS = 8

STATUS_ELEGIVEIS = frozenset({"aprovado", "simulacao", "auditoria"})
ESTRATOS_TRANSFERENCIA = {
    "candidatos_acionaveis": frozenset({"aprovado", "simulacao"}),
    "auditorias_silenciosas": frozenset({"auditoria"}),
}
RESULTADOS_VALIDOS = frozenset({
    "green", "half_green", "red", "half_red", "void",
})


def _documento_politica():
    nucleo = {
        "versao": VERSAO,
        "versao_medidor": VERSAO_MEDIDOR,
        "versao_valor_justo": VERSAO_VALOR_JUSTO,
        "unidade_independente": (
            "primeiro_sinal_elegivel_por_partida_e_mercado"
        ),
        "status_elegiveis": sorted(STATUS_ELEGIVEIS),
        "grupos": ["desajuste_favoravel", "controle_sem_desajuste"],
        "tamanho_coorte_por_mercado": TAMANHO_COORTE_POR_MERCADO,
        "desenvolvimento": DESENVOLVIMENTO,
        "holdout": HOLDOUT,
        "resultados_minimos": RESULTADOS_MINIMOS,
        "resultados_dev_minimos": RESULTADOS_DEV_MINIMOS,
        "resultados_holdout_minimos": RESULTADOS_HOLDOUT_MINIMOS,
        "resultados_edge_minimos": RESULTADOS_EDGE_MINIMOS,
        "resultados_controle_minimos": RESULTADOS_CONTROLE_MINIMOS,
        "resultados_edge_holdout_minimos": (
            RESULTADOS_EDGE_HOLDOUT_MINIMOS
        ),
        "resultados_controle_holdout_minimos": (
            RESULTADOS_CONTROLE_HOLDOUT_MINIMOS
        ),
        "criterio_revisao": (
            "roi_edge_positivo_e_superior_ao_controle_com_ic95_inferior_"
            "positivo_e_confirmacao_em_desenvolvimento_e_holdout"
        ),
        "resultado_posterior_selecao": True,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


POLITICA = _documento_politica()


def _documento_politica_transferencia():
    nucleo = {
        "versao": VERSAO_TRANSFERENCIA,
        "ancora_prospectiva": ANCORA_TRANSFERENCIA,
        "campo_de_estratificacao": "status_congelado_antes_resultado",
        "estratos_obrigatorios": {
            chave: sorted(status)
            for chave, status in ESTRATOS_TRANSFERENCIA.items()
        },
        "metrica_e_limites": VERSAO,
        "exige_vantagem_nos_dois_estratos": True,
        "vantagem_agregada_isolada_nao_basta": True,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


POLITICA_TRANSFERENCIA = _documento_politica_transferencia()


def politica_avaliacao_resultado():
    """Entrega uma copia para ser congelada no ``features_json``."""
    return dict(POLITICA)


def politica_transferencia_resultado():
    """Politica pre-registrada da replicacao entre origens do candidato."""
    return json.loads(json.dumps(POLITICA_TRANSFERENCIA))


def validar_politica_avaliacao_resultado(documento):
    return bool(
        isinstance(documento, dict)
        and documento == POLITICA
        and documento.get("aplicacao_sinais") is False
        and documento.get("altera_calibracao") is False
        and documento.get("telegram") is False
        and documento.get("promocao_automatica") is False
    )


def _tabelas(conexao):
    return {
        str(linha[0])
        for linha in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _colunas(conexao, tabela):
    return {
        str(linha[1])
        for linha in conexao.execute(f"PRAGMA table_info({tabela})")
    }


def mercados_com_candidato_sincronizado(conexao, packball_url, mercados):
    """Retorna mercados que ja possuem candidato V6 liquidavel no jogo.

    A consulta e usada apenas para economizar a fonte independente. Um novo
    snapshot do mesmo jogo nao precisa disputar cota depois que a unidade
    prospectiva daquele mercado ja foi formada.
    """
    mercados = sorted({
        str(mercado or "").strip()
        for mercado in (mercados or ())
        if str(mercado or "").strip()
    })
    packball_url = str(packball_url or "").strip()
    if not packball_url or not mercados:
        return set()
    if not {"partidas", "sinais"}.issubset(_tabelas(conexao)):
        return set()
    placeholders = ",".join("?" for _ in mercados)
    parametros = [
        packball_url,
        *mercados,
        VERSAO_MEDIDOR,
        VERSAO_VALOR_JUSTO,
    ]
    linhas = conexao.execute(
        f"""
        SELECT DISTINCT s.mercado
        FROM sinais s
        JOIN partidas p ON p.id=s.partida_id
        WHERE p.packball_url=?
          AND s.mercado IN ({placeholders})
          AND s.status IN ('aprovado', 'simulacao', 'auditoria')
          AND json_valid(s.features_json)
          AND json_extract(
              s.features_json, '$.melhor_preco_sombra.versao'
          )=?
          AND json_extract(
              s.features_json,
              '$.melhor_preco_sombra.valor_justo_sombra.versao'
          )=?
          AND json_extract(
              s.features_json,
              '$.melhor_preco_sombra.valor_justo_sombra.estado'
          ) IN ('desajuste_favoravel_candidato',
                'sem_desajuste_favoravel')
        """,
        parametros,
    ).fetchall()
    return {str(linha[0]) for linha in linhas}


def _instante(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip()
    if texto.endswith("Z"):
        texto = f"{texto[:-1]}+00:00"
    try:
        instante = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if instante.tzinfo is None:
        instante = instante.astimezone()
    return instante.astimezone(timezone.utc).replace(tzinfo=None)


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return numero if math.isfinite(numero) else None


def _intervalo_media_95(valores):
    valores = [float(valor) for valor in valores]
    if not valores:
        return None
    media = statistics.fmean(valores)
    if len(valores) == 1:
        return [round(media, 6), round(media, 6)]
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    return [round(media - 1.96 * erro, 6), round(media + 1.96 * erro, 6)]


def _intervalo_diferenca_95(edge, controle):
    if len(edge) < 2 or len(controle) < 2:
        return None
    diferenca = statistics.fmean(edge) - statistics.fmean(controle)
    erro = math.sqrt(
        statistics.variance(edge) / len(edge)
        + statistics.variance(controle) / len(controle)
    )
    return [
        round(diferenca - 1.96 * erro, 6),
        round(diferenca + 1.96 * erro, 6),
    ]


def _classificar_resultado(item):
    resultado = item.get("resultado")
    if resultado is None:
        return "pendente", None
    resultado = str(resultado).strip().casefold()
    encerrado = _instante(item.get("encerrado_em"))
    if encerrado is None or encerrado <= item["criado_instante"]:
        return "cronologia_invalida", None
    if resultado not in RESULTADOS_VALIDOS:
        return "resultado_invalido", None
    retorno = _numero(item.get("retorno_unidades"))
    if retorno is None:
        return "retorno_invalido", None
    if resultado == "void" and not math.isclose(
        retorno, 0.0, rel_tol=0.0, abs_tol=1e-9
    ):
        return "retorno_invalido", None
    return "valido", {"resultado": resultado, "retorno": retorno}


def _resumir_grupo(itens):
    estados = Counter()
    desfechos = Counter()
    retornos = []
    probabilidades = []
    valores_esperados = []
    brier = []
    calibracao = []
    for item in itens:
        estado, liquidacao = _classificar_resultado(item)
        estados[estado] += 1
        if estado != "valido":
            continue
        resultado = liquidacao["resultado"]
        retorno = liquidacao["retorno"]
        desfechos[resultado] += 1
        retornos.append(retorno)
        probabilidades.append(item["probabilidade"])
        valores_esperados.append(item["valor_esperado"])
        if resultado in {"green", "red"}:
            observado = 1.0 if resultado == "green" else 0.0
            brier.append((observado - item["probabilidade"]) ** 2)
            calibracao.append(observado - item["probabilidade"])
    resolvidos_direcionais = sum(
        desfechos[chave]
        for chave in ("green", "half_green", "red", "half_red")
    )
    lucro = sum(retornos)
    return {
        "candidatos": len(itens),
        "partidas_distintas": len({item["partida_id"] for item in itens}),
        "resultados_validos": len(retornos),
        "pendentes": estados["pendente"],
        "cronologia_invalida": estados["cronologia_invalida"],
        "resultado_invalido": estados["resultado_invalido"],
        "retorno_invalido": estados["retorno_invalido"],
        "greens": desfechos["green"],
        "half_greens": desfechos["half_green"],
        "reds": desfechos["red"],
        "half_reds": desfechos["half_red"],
        "voids": desfechos["void"],
        "retorno_unidades": round(lucro, 6),
        "roi_real": round(lucro / len(retornos), 6) if retornos else None,
        "ic95_roi_real": _intervalo_media_95(retornos),
        "taxa_green_direcional": round(
            (desfechos["green"] + desfechos["half_green"])
            / resolvidos_direcionais,
            6,
        ) if resolvidos_direcionais else None,
        "probabilidade_referencia_media": round(
            statistics.fmean(probabilidades), 6
        ) if probabilidades else None,
        "valor_esperado_previsto_medio": round(
            statistics.fmean(valores_esperados), 6
        ) if valores_esperados else None,
        "brier_score_binario": round(statistics.fmean(brier), 6)
        if brier else None,
        "vies_calibracao_binario": round(
            statistics.fmean(calibracao), 6
        ) if calibracao else None,
        "_retornos": retornos,
    }


def _comparar_grupos(itens):
    edge_itens = [item for item in itens if item["edge"]]
    controle_itens = [item for item in itens if not item["edge"]]
    edge = _resumir_grupo(edge_itens)
    controle = _resumir_grupo(controle_itens)
    retornos_edge = edge.pop("_retornos")
    retornos_controle = controle.pop("_retornos")
    diferenca = (
        statistics.fmean(retornos_edge) - statistics.fmean(retornos_controle)
        if retornos_edge and retornos_controle else None
    )
    return {
        "edge": edge,
        "controle_sem_edge": controle,
        "diferenca_roi_edge_menos_controle": round(diferenca, 6)
        if diferenca is not None else None,
        "ic95_diferenca_roi": _intervalo_diferenca_95(
            retornos_edge, retornos_controle
        ),
    }


def _resumir_mercado(mercado, itens):
    coorte = list(itens[:TAMANHO_COORTE_POR_MERCADO])
    desenvolvimento = coorte[:DESENVOLVIMENTO]
    holdout = coorte[DESENVOLVIMENTO:TAMANHO_COORTE_POR_MERCADO]
    total = _comparar_grupos(coorte)
    dev = _comparar_grupos(desenvolvimento)
    teste = _comparar_grupos(holdout)
    resultados_total = (
        total["edge"]["resultados_validos"]
        + total["controle_sem_edge"]["resultados_validos"]
    )
    resultados_dev = (
        dev["edge"]["resultados_validos"]
        + dev["controle_sem_edge"]["resultados_validos"]
    )
    resultados_holdout = (
        teste["edge"]["resultados_validos"]
        + teste["controle_sem_edge"]["resultados_validos"]
    )
    cronologia_invalida = sum(
        bloco[grupo]["cronologia_invalida"]
        for bloco in (total,)
        for grupo in ("edge", "controle_sem_edge")
    )
    evidencia_completa = bool(
        len(coorte) >= TAMANHO_COORTE_POR_MERCADO
        and resultados_total >= RESULTADOS_MINIMOS
        and resultados_dev >= RESULTADOS_DEV_MINIMOS
        and resultados_holdout >= RESULTADOS_HOLDOUT_MINIMOS
        and total["edge"]["resultados_validos"] >= RESULTADOS_EDGE_MINIMOS
        and total["controle_sem_edge"]["resultados_validos"]
        >= RESULTADOS_CONTROLE_MINIMOS
        and teste["edge"]["resultados_validos"]
        >= RESULTADOS_EDGE_HOLDOUT_MINIMOS
        and teste["controle_sem_edge"]["resultados_validos"]
        >= RESULTADOS_CONTROLE_HOLDOUT_MINIMOS
        and cronologia_invalida == 0
    )
    intervalo = total.get("ic95_diferenca_roi")
    edge_roi = total["edge"].get("roi_real")
    dev_edge = dev["edge"].get("roi_real")
    dev_controle = dev["controle_sem_edge"].get("roi_real")
    teste_edge = teste["edge"].get("roi_real")
    teste_controle = teste["controle_sem_edge"].get("roi_real")
    vantagem = bool(
        evidencia_completa
        and intervalo is not None and intervalo[0] > 0.0
        and edge_roi is not None and edge_roi > 0.0
        and dev_edge is not None and dev_controle is not None
        and dev_edge > dev_controle
        and teste_edge is not None and teste_controle is not None
        and teste_edge > teste_controle
    )
    if len(coorte) < TAMANHO_COORTE_POR_MERCADO:
        decisao = "formando_coorte"
    elif not evidencia_completa:
        decisao = "aguardando_resultados_e_equilibrio_dos_grupos"
    elif vantagem:
        decisao = "vantagem_real_confirmada_somente_para_revisao"
    else:
        decisao = "vantagem_real_nao_confirmada"
    return {
        "mercado": mercado,
        "candidatos_brutos": len(itens),
        "coorte": len(coorte),
        "faltam_coorte": max(TAMANHO_COORTE_POR_MERCADO - len(coorte), 0),
        "desenvolvimento": dev,
        "holdout": teste,
        "total": total,
        "resultados_total": resultados_total,
        "resultados_desenvolvimento": resultados_dev,
        "resultados_holdout": resultados_holdout,
        "evidencia_completa": evidencia_completa,
        "vantagem_resultados_comprovada": vantagem,
        "decisao": decisao,
    }


def _resumir_transferencia_mercado(mercado, itens):
    """Exige replicacao em acionaveis e auditorias, sem misturar populacoes."""
    estratos = {}
    for nome, status in ESTRATOS_TRANSFERENCIA.items():
        subconjunto = [item for item in itens if item["status"] in status]
        estratos[nome] = {
            **_resumir_mercado(mercado, subconjunto),
            "status_incluidos": sorted(status),
        }
    evidencia_completa = all(
        item["evidencia_completa"] for item in estratos.values()
    )
    vantagem_replicada = bool(
        evidencia_completa
        and all(
            item["vantagem_resultados_comprovada"]
            for item in estratos.values()
        )
    )
    if not evidencia_completa:
        decisao = "formando_coortes_por_origem"
    elif vantagem_replicada:
        decisao = "vantagem_transferivel_confirmada_somente_para_revisao"
    else:
        decisao = "vantagem_transferivel_nao_confirmada"
    return {
        "mercado": mercado,
        "candidatos_pos_ancora": len(itens),
        "composicao_status": dict(sorted(Counter(
            item["status"] for item in itens
        ).items())),
        "estratos": estratos,
        "evidencia_completa_nos_dois_estratos": evidencia_completa,
        "vantagem_transferivel_comprovada": vantagem_replicada,
        "decisao": decisao,
    }


def _base_transferencia():
    return {
        "versao": VERSAO_TRANSFERENCIA,
        "politica": politica_transferencia_resultado(),
        "ancora_prospectiva": ANCORA_TRANSFERENCIA,
        "estado": "aguardando_candidatos_pos_ancora",
        "candidatos_pos_ancora": 0,
        "partidas_distintas": 0,
        "composicao_status": {},
        "por_mercado": {},
        "mercados_com_vantagem_transferivel_comprovada": [],
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _base():
    return {
        "versao": VERSAO,
        "politica": politica_avaliacao_resultado(),
        "estado": "aguardando_candidatos",
        "saudavel": True,
        "motivo": None,
        "candidatos_elegiveis": 0,
        "partidas_distintas": 0,
        "primeiro_candidato_em": None,
        "ultimo_candidato_em": None,
        "por_mercado": {},
        "exclusoes": {},
        "violacoes_integridade": 0,
        "mercados_com_vantagem_comprovada": [],
        "validacao_transferencia": _base_transferencia(),
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def resumir_validacao_resultado_valor_justo(conexao):
    """Lê a coorte inteira; o recorte nunca desliza com uma janela de dias."""
    resumo = _base()
    tabelas = _tabelas(conexao)
    if not {"sinais", "resultados_sinais"}.issubset(tabelas):
        resumo.update(
            saudavel=False,
            estado="schema_incompleto",
            motivo="tabelas_resultado_valor_justo_ausentes",
        )
        return resumo
    requeridas_sinais = {
        "id", "partida_id", "criado_em", "status", "features_json",
        "mercado",
    }
    requeridas_resultados = {
        "sinal_id", "encerrado_em", "resultado", "retorno_unidades",
    }
    if (
        not requeridas_sinais.issubset(_colunas(conexao, "sinais"))
        or not requeridas_resultados.issubset(
            _colunas(conexao, "resultados_sinais")
        )
    ):
        resumo.update(
            saudavel=False,
            estado="schema_incompleto",
            motivo="colunas_resultado_valor_justo_ausentes",
        )
        return resumo
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.criado_em, s.status, s.mercado,
               s.features_json, r.encerrado_em, r.resultado,
               r.retorno_unidades
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE instr(s.features_json, 'melhor_preco_sombra') > 0
        ORDER BY datetime(s.criado_em), s.id
        """
    ).fetchall()
    exclusoes = Counter()
    independentes = {}
    for linha in linhas:
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            exclusoes["features_invalidas"] += 1
            continue
        sombra = features.get("melhor_preco_sombra") or {}
        if sombra.get("versao") != VERSAO_MEDIDOR:
            exclusoes["outra_versao"] += 1
            continue
        valor = sombra.get("valor_justo_sombra") or {}
        if valor.get("versao") != VERSAO_VALOR_JUSTO:
            exclusoes["versao_valor_justo_invalida"] += 1
            continue
        if valor.get("estado") not in {
            "desajuste_favoravel_candidato", "sem_desajuste_favoravel",
        }:
            exclusoes["sem_preco_justo_sincronizado"] += 1
            continue
        if not validar_politica_avaliacao_resultado(
            valor.get("avaliacao_resultado_sombra")
        ):
            exclusoes["politica_invalida"] += 1
            continue
        status = str(linha["status"] or "").strip().casefold()
        if status not in STATUS_ELEGIVEIS:
            exclusoes["status_nao_liquidavel"] += 1
            continue
        criado = _instante(linha["criado_em"])
        probabilidade = _numero(
            valor.get("probabilidade_referencia_sem_vig")
        )
        valor_esperado = _numero(valor.get("valor_esperado_referencia"))
        edge = valor.get("desajuste_favoravel")
        if (
            criado is None or probabilidade is None
            or not 0.0 < probabilidade < 1.0
            or valor_esperado is None or edge not in (True, False)
        ):
            exclusoes["evidencia_invalida"] += 1
            continue
        mercado = str(linha["mercado"] or "desconhecido")
        item = {
            "sinal_id": int(linha["id"]),
            "partida_id": int(linha["partida_id"]),
            "mercado": mercado,
            "status": status,
            "criado_em": str(linha["criado_em"]),
            "criado_instante": criado,
            "edge": edge is True,
            "probabilidade": probabilidade,
            "valor_esperado": valor_esperado,
            "encerrado_em": linha["encerrado_em"],
            "resultado": linha["resultado"],
            "retorno_unidades": linha["retorno_unidades"],
        }
        # A escolha usa apenas campos conhecidos antes do resultado. Uma
        # reavaliacao posterior da mesma partida nunca substitui a primeira.
        independentes.setdefault((item["partida_id"], mercado), item)

    itens = list(independentes.values())
    resumo["exclusoes"] = dict(sorted(exclusoes.items()))
    resumo["candidatos_elegiveis"] = len(itens)
    resumo["partidas_distintas"] = len({item["partida_id"] for item in itens})
    if itens:
        resumo["primeiro_candidato_em"] = itens[0]["criado_em"]
        resumo["ultimo_candidato_em"] = itens[-1]["criado_em"]
    por_mercado = {}
    for mercado in sorted({item["mercado"] for item in itens}):
        por_mercado[mercado] = _resumir_mercado(
            mercado, [item for item in itens if item["mercado"] == mercado]
        )
    resumo["por_mercado"] = por_mercado
    resumo["mercados_com_vantagem_comprovada"] = sorted(
        mercado for mercado, item in por_mercado.items()
        if item["vantagem_resultados_comprovada"]
    )
    ancora_transferencia = _instante(ANCORA_TRANSFERENCIA)
    itens_transferencia = [
        item for item in itens
        if ancora_transferencia is not None
        and item["criado_instante"] >= ancora_transferencia
    ]
    transferencia = _base_transferencia()
    transferencia["candidatos_pos_ancora"] = len(itens_transferencia)
    transferencia["partidas_distintas"] = len({
        item["partida_id"] for item in itens_transferencia
    })
    transferencia["composicao_status"] = dict(sorted(Counter(
        item["status"] for item in itens_transferencia
    ).items()))
    transferencia["por_mercado"] = {
        mercado: _resumir_transferencia_mercado(
            mercado,
            [
                item for item in itens_transferencia
                if item["mercado"] == mercado
            ],
        )
        for mercado in sorted({
            item["mercado"] for item in itens_transferencia
        })
    }
    transferencia[
        "mercados_com_vantagem_transferivel_comprovada"
    ] = sorted(
        mercado for mercado, item in transferencia["por_mercado"].items()
        if item["vantagem_transferivel_comprovada"]
    )
    if transferencia["mercados_com_vantagem_transferivel_comprovada"]:
        transferencia["estado"] = "apto_revisao_transferencia"
    elif itens_transferencia:
        completos = any(
            item["evidencia_completa_nos_dois_estratos"]
            for item in transferencia["por_mercado"].values()
        )
        transferencia["estado"] = (
            "vantagem_transferivel_nao_confirmada"
            if completos else "formando_coortes_por_origem"
        )
    resumo["validacao_transferencia"] = transferencia
    violacoes = exclusoes["politica_invalida"]
    for item in por_mercado.values():
        for grupo in ("edge", "controle_sem_edge"):
            violacoes += item["total"][grupo]["cronologia_invalida"]
            violacoes += item["total"][grupo]["resultado_invalido"]
            violacoes += item["total"][grupo]["retorno_invalido"]
    resumo["violacoes_integridade"] = violacoes
    if violacoes:
        resumo.update(
            saudavel=False,
            estado="resultado_inconsistente",
            motivo="validacao_resultado_valor_justo_inconsistente",
        )
    elif itens:
        resumo["estado"] = (
            "apto_revisao_humana"
            if resumo["mercados_com_vantagem_comprovada"]
            else "coletando_resultados_prospectivos"
        )
    return resumo
