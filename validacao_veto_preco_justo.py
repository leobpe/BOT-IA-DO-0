"""Avalia prospectivamente um veto de preço justo negativo em sombra.

O ensaio nunca bloqueia sinal. Ele congela a classificação antes do desfecho
e só permite uma futura revisão operacional depois de desenvolvimento,
holdout e replicação entre sinais acionáveis e auditorias silenciosas.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone

from validacao_resultado_valor_justo import (
    VERSAO_MEDIDOR,
    VERSAO_VALOR_JUSTO,
)


VERSAO = "validacao-veto-preco-justo-negativo-v1"
ANCORA_PROSPECTIVA = "2026-09-12T19:30:00-04:00"
LIMIAR_VALOR_ESPERADO_VETO = -0.05
TAMANHO_COORTE_POR_MERCADO = 120
DESENVOLVIMENTO = 80
HOLDOUT = 40
RESULTADOS_MINIMOS = 100
RESULTADOS_DEV_MINIMOS = 65
RESULTADOS_HOLDOUT_MINIMOS = 30
RESULTADOS_GRUPO_MINIMOS = 25
RESULTADOS_GRUPO_HOLDOUT_MINIMOS = 8

STATUS_ELEGIVEIS = frozenset({"aprovado", "simulacao", "auditoria"})
ESTRATOS = {
    "candidatos_acionaveis": frozenset({"aprovado", "simulacao"}),
    "auditorias_silenciosas": frozenset({"auditoria"}),
}
CLASSIFICACOES = frozenset({
    "veto_preco_negativo",
    "controle_nao_veto",
    "inelegivel_sem_preco_justo",
})
RESULTADOS_VALIDOS = frozenset({
    "green", "half_green", "red", "half_red", "void",
})


def _documento_politica():
    nucleo = {
        "versao": VERSAO,
        "ancora_prospectiva": ANCORA_PROSPECTIVA,
        "versao_medidor": VERSAO_MEDIDOR,
        "versao_valor_justo": VERSAO_VALOR_JUSTO,
        "limiar_valor_esperado_veto": LIMIAR_VALOR_ESPERADO_VETO,
        "regra_veto": "valor_esperado_referencia_menor_ou_igual_ao_limiar",
        "unidade_independente": (
            "primeiro_sinal_por_partida_mercado_e_origem"
        ),
        "status_elegiveis": sorted(STATUS_ELEGIVEIS),
        "estratos_obrigatorios": {
            chave: sorted(status) for chave, status in ESTRATOS.items()
        },
        "tamanho_coorte_por_mercado": TAMANHO_COORTE_POR_MERCADO,
        "desenvolvimento": DESENVOLVIMENTO,
        "holdout": HOLDOUT,
        "resultados_minimos": RESULTADOS_MINIMOS,
        "resultados_dev_minimos": RESULTADOS_DEV_MINIMOS,
        "resultados_holdout_minimos": RESULTADOS_HOLDOUT_MINIMOS,
        "resultados_grupo_minimos": RESULTADOS_GRUPO_MINIMOS,
        "resultados_grupo_holdout_minimos": (
            RESULTADOS_GRUPO_HOLDOUT_MINIMOS
        ),
        "criterio_revisao": (
            "retorno_do_grupo_veto_pior_que_controle_com_ic95_superior_"
            "da_diferenca_abaixo_de_zero_e_replicacao_dev_holdout_origens"
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


def politica_veto_preco_justo():
    return json.loads(json.dumps(POLITICA))


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return numero if math.isfinite(numero) else None


def _classificacao(valor_esperado):
    valor = _numero(valor_esperado)
    if valor is None:
        return "inelegivel_sem_preco_justo"
    if valor <= LIMIAR_VALOR_ESPERADO_VETO + 1e-12:
        return "veto_preco_negativo"
    return "controle_nao_veto"


def avaliar_veto_preco_justo_sombra(valor_esperado):
    """Congela a hipótese antes do resultado, sempre sem efeito operacional."""
    valor = _numero(valor_esperado)
    return {
        "versao": VERSAO,
        "politica_sha256": POLITICA["definicao_sha256"],
        "ancora_prospectiva": ANCORA_PROSPECTIVA,
        "limiar_valor_esperado_veto": LIMIAR_VALOR_ESPERADO_VETO,
        "valor_esperado_observado": (
            round(valor, 8) if valor is not None else None
        ),
        "classificacao": _classificacao(valor),
        "selecao_antes_resultado": True,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def validar_avaliacao_veto(documento, valor_esperado):
    esperado = avaliar_veto_preco_justo_sombra(valor_esperado)
    return bool(isinstance(documento, dict) and documento == esperado)


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


def _intervalo_media_95(valores):
    valores = [float(valor) for valor in valores]
    if not valores:
        return None
    media = statistics.fmean(valores)
    if len(valores) == 1:
        return [round(media, 6), round(media, 6)]
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    return [round(media - 1.96 * erro, 6), round(media + 1.96 * erro, 6)]


def _intervalo_diferenca_95(veto, controle):
    if len(veto) < 2 or len(controle) < 2:
        return None
    diferenca = statistics.fmean(veto) - statistics.fmean(controle)
    erro = math.sqrt(
        statistics.variance(veto) / len(veto)
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
    for item in itens:
        estado, liquidacao = _classificar_resultado(item)
        estados[estado] += 1
        if estado != "valido":
            continue
        retornos.append(liquidacao["retorno"])
        desfechos[liquidacao["resultado"]] += 1
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
        "retorno_unidades": round(sum(retornos), 6),
        "roi_real": (
            round(statistics.fmean(retornos), 6) if retornos else None
        ),
        "ic95_roi_real": _intervalo_media_95(retornos),
        "retornos": retornos,
    }


def _resumir_fatia(itens):
    veto = [
        item for item in itens
        if item["classificacao"] == "veto_preco_negativo"
    ]
    controle = [
        item for item in itens
        if item["classificacao"] == "controle_nao_veto"
    ]
    resumo_veto = _resumir_grupo(veto)
    resumo_controle = _resumir_grupo(controle)
    diferenca = None
    if (
        resumo_veto["roi_real"] is not None
        and resumo_controle["roi_real"] is not None
    ):
        diferenca = round(
            resumo_veto["roi_real"] - resumo_controle["roi_real"], 6
        )
    intervalo = _intervalo_diferenca_95(
        resumo_veto.pop("retornos"),
        resumo_controle.pop("retornos"),
    )
    return {
        "veto_preco_negativo": resumo_veto,
        "controle_nao_veto": resumo_controle,
        "diferenca_roi_veto_menos_controle": diferenca,
        "ic95_diferenca_roi": intervalo,
    }


def _resumir_coorte(itens):
    itens = sorted(itens, key=lambda item: (item["criado_instante"], item["id"]))
    coorte = itens[:TAMANHO_COORTE_POR_MERCADO]
    desenvolvimento = coorte[:DESENVOLVIMENTO]
    holdout = coorte[DESENVOLVIMENTO:]
    total = _resumir_fatia(coorte)
    dev = _resumir_fatia(desenvolvimento)
    teste = _resumir_fatia(holdout)
    resultados_total = sum(
        total[grupo]["resultados_validos"]
        for grupo in ("veto_preco_negativo", "controle_nao_veto")
    )
    resultados_dev = sum(
        dev[grupo]["resultados_validos"]
        for grupo in ("veto_preco_negativo", "controle_nao_veto")
    )
    resultados_holdout = sum(
        teste[grupo]["resultados_validos"]
        for grupo in ("veto_preco_negativo", "controle_nao_veto")
    )
    intervalo = total["ic95_diferenca_roi"]
    evidencia = bool(
        len(coorte) >= TAMANHO_COORTE_POR_MERCADO
        and resultados_total >= RESULTADOS_MINIMOS
        and resultados_dev >= RESULTADOS_DEV_MINIMOS
        and resultados_holdout >= RESULTADOS_HOLDOUT_MINIMOS
        and all(
            total[grupo]["resultados_validos"]
            >= RESULTADOS_GRUPO_MINIMOS
            for grupo in ("veto_preco_negativo", "controle_nao_veto")
        )
        and all(
            teste[grupo]["resultados_validos"]
            >= RESULTADOS_GRUPO_HOLDOUT_MINIMOS
            for grupo in ("veto_preco_negativo", "controle_nao_veto")
        )
    )
    veto_comprovado = bool(
        evidencia
        and intervalo is not None
        and intervalo[1] < 0
        and total["veto_preco_negativo"]["ic95_roi_real"] is not None
        and total["veto_preco_negativo"]["ic95_roi_real"][1] < 0
        and dev["diferenca_roi_veto_menos_controle"] is not None
        and dev["diferenca_roi_veto_menos_controle"] < 0
        and teste["diferenca_roi_veto_menos_controle"] is not None
        and teste["diferenca_roi_veto_menos_controle"] < 0
    )
    return {
        "candidatos_brutos": len(itens),
        "coorte": len(coorte),
        "faltam_coorte": max(TAMANHO_COORTE_POR_MERCADO - len(coorte), 0),
        "desenvolvimento": dev,
        "holdout": teste,
        "total": total,
        "resultados_total": resultados_total,
        "resultados_desenvolvimento": resultados_dev,
        "resultados_holdout": resultados_holdout,
        "evidencia_completa": evidencia,
        "veto_benefico_comprovado": veto_comprovado,
        "decisao": (
            "veto_benefico_comprovado"
            if veto_comprovado else "sem_vantagem_comprovada"
            if evidencia else "formando_coorte"
        ),
    }


def _base():
    return {
        "versao": VERSAO,
        "politica": politica_veto_preco_justo(),
        "estado": "aguardando_candidatos_pos_ancora",
        "saudavel": True,
        "motivo": None,
        "candidatos_pos_ancora": 0,
        "partidas_distintas": 0,
        "composicao_status": {},
        "por_mercado": {},
        "violacoes_integridade": 0,
        "ids_invalidos": [],
        "mercados_com_veto_transferivel_comprovado": [],
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def resumir_validacao_veto_preco_justo(conexao):
    """Lê somente casos futuros e nunca promove o veto automaticamente."""
    resumo = _base()
    tabelas = {
        str(linha[0]) for linha in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if not {"sinais", "resultados_sinais"}.issubset(tabelas):
        resumo.update(
            saudavel=False,
            estado="schema_incompleto",
            motivo="tabelas_veto_preco_justo_ausentes",
        )
        return resumo
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.criado_em, s.mercado, s.status,
               s.features_json, r.encerrado_em, r.resultado,
               r.retorno_unidades
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.status IN ('aprovado', 'simulacao', 'auditoria')
          AND json_valid(s.features_json)
          AND json_extract(
                s.features_json, '$.melhor_preco_sombra.versao'
              )=?
          AND json_extract(
                s.features_json,
                '$.melhor_preco_sombra.valor_justo_sombra.versao'
              )=?
        ORDER BY s.criado_em, s.id
        """,
        (VERSAO_MEDIDOR, VERSAO_VALOR_JUSTO),
    ).fetchall()
    ancora = _instante(ANCORA_PROSPECTIVA)
    itens = []
    invalidos = []
    composicao = Counter()
    vistos = set()
    for linha in linhas:
        criado = _instante(linha["criado_em"])
        if criado is None or criado < ancora:
            continue
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            invalidos.append(int(linha["id"]))
            continue
        valor = (
            (features.get("melhor_preco_sombra") or {})
            .get("valor_justo_sombra") or {}
        )
        valor_esperado = _numero(valor.get("valor_esperado_referencia"))
        avaliacao = valor.get("avaliacao_veto_preco_sombra")
        if valor_esperado is None:
            continue
        if not validar_avaliacao_veto(avaliacao, valor_esperado):
            invalidos.append(int(linha["id"]))
            continue
        status = str(linha["status"])
        estrato = next(
            (
                chave for chave, status_aceitos in ESTRATOS.items()
                if status in status_aceitos
            ),
            None,
        )
        if estrato is None:
            invalidos.append(int(linha["id"]))
            continue
        chave = (int(linha["partida_id"]), str(linha["mercado"]), estrato)
        if chave in vistos:
            continue
        vistos.add(chave)
        composicao[status] += 1
        itens.append({
            "id": int(linha["id"]),
            "partida_id": int(linha["partida_id"]),
            "criado_instante": criado,
            "mercado": str(linha["mercado"]),
            "status": status,
            "estrato": estrato,
            "classificacao": avaliacao["classificacao"],
            "encerrado_em": linha["encerrado_em"],
            "resultado": linha["resultado"],
            "retorno_unidades": linha["retorno_unidades"],
        })
    por_mercado = {}
    mercados_transferiveis = []
    for mercado in sorted({item["mercado"] for item in itens}):
        estratos = {
            estrato: _resumir_coorte([
                item for item in itens
                if item["mercado"] == mercado and item["estrato"] == estrato
            ])
            for estrato in ESTRATOS
        }
        transferivel = all(
            item["veto_benefico_comprovado"] for item in estratos.values()
        )
        por_mercado[mercado] = {
            "mercado": mercado,
            "estratos": estratos,
            "evidencia_completa_nos_dois_estratos": all(
                item["evidencia_completa"] for item in estratos.values()
            ),
            "veto_transferivel_comprovado": transferivel,
            "decisao": (
                "veto_transferivel_comprovado"
                if transferivel else "formando_coortes_por_origem"
            ),
        }
        if transferivel:
            mercados_transferiveis.append(mercado)
    resumo.update({
        "estado": (
            "veto_transferivel_comprovado"
            if mercados_transferiveis
            else "formando_coortes_por_origem" if itens
            else "aguardando_candidatos_pos_ancora"
        ),
        "candidatos_pos_ancora": len(itens),
        "partidas_distintas": len({item["partida_id"] for item in itens}),
        "composicao_status": dict(sorted(composicao.items())),
        "por_mercado": por_mercado,
        "violacoes_integridade": len(invalidos),
        "ids_invalidos": sorted(set(invalidos))[:20],
        "mercados_com_veto_transferivel_comprovado": mercados_transferiveis,
    })
    if invalidos:
        resumo.update(
            saudavel=False,
            estado="telemetria_veto_inconsistente",
            motivo="avaliacao_veto_preco_justo_invalida",
        )
    return resumo
