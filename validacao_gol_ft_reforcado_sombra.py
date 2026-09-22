"""Coorte prospectiva fixa para reavaliar o Gol FT reforçado.

O Gol FT permanece silencioso por padrão. Somente resultados posteriores à
âncora entram nesta validação, com desenvolvimento e holdout separados. Uma
conclusão favorável permite revisão humana, nunca promoção automática.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime

from versoes_gol_ft_reforcado import (
    VERSAO_GOL_FT_REFORCADO,
    VERSAO_GOL_FT_REFORCADO_ANTERIOR,
)


VERSAO_VALIDACAO = "validacao-gol-ft-reforcado-sombra-v1"
CHAVE = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"
TAMANHO_COORTE = 75
DESENVOLVIMENTO = 50
HOLDOUT = 25
MINIMO_VALIDOS_TOTAL = 70
MINIMO_VALIDOS_DESENVOLVIMENTO = 47
MINIMO_VALIDOS_HOLDOUT = 23
RESULTADOS_VALIDOS = {"green", "half_green", "red", "half_red"}


def definicao():
    nucleo = {
        "versao": VERSAO_VALIDACAO,
        "regra": VERSAO_GOL_FT_REFORCADO,
        "populacao": "primeiro_elegivel_por_partida_pos_ancora",
        "status": "simulacao",
        "modo": "validacao_sombra",
        "tamanho_coorte": TAMANHO_COORTE,
        "desenvolvimento": DESENVOLVIMENTO,
        "holdout": HOLDOUT,
        "minimo_validos_total": MINIMO_VALIDOS_TOTAL,
        "minimo_validos_desenvolvimento": (
            MINIMO_VALIDOS_DESENVOLVIMENTO
        ),
        "minimo_validos_holdout": MINIMO_VALIDOS_HOLDOUT,
        "criterio": (
            "roi_total_ic95_inferior_e_roi_dev_holdout_positivos"
        ),
        "evidencia_geradora": {
            "regra_historica": VERSAO_GOL_FT_REFORCADO_ANTERIOR,
            "amostra_oficial_v11": 13,
            "greens": 7,
            "reds": 6,
            "roi": -0.1812,
            "aviso": "historico_nao_comprova_vantagem",
        },
        "telegram": False,
        "promocao_automatica": False,
        "reativacao_somente_manual": (
            "GOL_FT_REFORCADO_OFICIAL_ATIVO=1"
        ),
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


def registrar_ou_validar_gol_ft_reforcado(conexao, registrado_em=None):
    esperada = definicao()
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        if divergencias:
            raise RuntimeError(
                "Validação Gol FT reforçado diverge da âncora imutável: "
                + ",".join(divergencias)
            )
        return existente
    documento = {
        **esperada,
        "registrado_em": (registrado_em or datetime.now()).replace(
            microsecond=0
        ).isoformat(),
    }
    with conexao:
        conexao.execute(
            "INSERT INTO metadados(chave,valor) VALUES (?,?)",
            (
                CHAVE,
                json.dumps(documento, ensure_ascii=False, sort_keys=True),
            ),
        )
    return documento


def auditar_validacao_gol_ft_reforcado(conexao, exigir_registro=False):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE,)
    ).fetchone()
    if linha is None:
        return {
            "saudavel": not exigir_registro,
            "estado": "nao_registrada",
            "versao": VERSAO_VALIDACAO,
        }
    try:
        documento = json.loads(linha["valor"])
    except (TypeError, json.JSONDecodeError):
        return {
            "saudavel": False,
            "estado": "json_invalido",
            "versao": VERSAO_VALIDACAO,
        }
    divergencias = [
        campo for campo, valor in definicao().items()
        if documento.get(campo) != valor
    ]
    return {
        "saudavel": not divergencias,
        "estado": "valida" if not divergencias else "inconsistente",
        "versao": VERSAO_VALIDACAO,
        "divergencias": divergencias,
    }


def _metricas(linhas):
    validas = [
        item for item in linhas
        if item["resultado"] in RESULTADOS_VALIDOS
        and item["retorno_unidades"] is not None
    ]
    retornos = [float(item["retorno_unidades"]) for item in validas]
    lucro = sum(retornos)
    intervalo = None
    if len(retornos) >= 2:
        media = statistics.fmean(retornos)
        erro = statistics.stdev(retornos) / math.sqrt(len(retornos))
        intervalo = [
            round(media - 1.96 * erro, 4),
            round(media + 1.96 * erro, 4),
        ]
    pendentes = sum(item["resultado"] is None for item in linhas)
    return {
        "candidatos": len(linhas),
        "validos": len(validas),
        "greens": sum(
            item["resultado"] in {"green", "half_green"}
            for item in validas
        ),
        "reds": sum(
            item["resultado"] in {"red", "half_red"}
            for item in validas
        ),
        "pendentes": pendentes,
        "invalidos": len(linhas) - len(validas) - pendentes,
        "lucro_unidades": round(lucro, 4),
        "roi": round(lucro / len(validas), 4) if validas else None,
        "intervalo_roi_95": intervalo,
    }


def resumir_validacao_gol_ft_reforcado(conexao):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE,)
    ).fetchone()
    if linha is None:
        return {
            "versao": VERSAO_VALIDACAO,
            "estado": "nao_registrada",
            "telegram": False,
            "promocao_automatica": False,
        }
    documento = json.loads(linha["valor"])
    auditoria = auditar_validacao_gol_ft_reforcado(conexao, True)
    if not auditoria["saudavel"]:
        return {
            **auditoria,
            "telegram": False,
            "promocao_automatica": False,
        }
    linhas = conexao.execute(
        """
        WITH independentes AS (
          SELECT s.id,s.partida_id,s.criado_em,s.regra_fingerprint,
                 r.resultado,r.retorno_unidades,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.partida_id
                   ORDER BY datetime(s.criado_em),s.id
                 ) AS ordem
          FROM sinais s
          LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE datetime(s.criado_em)>=datetime(?)
            AND s.mercado='gol_ft'
            AND s.status='simulacao'
            AND s.regra_versao=?
            AND json_extract(
                  s.features_json,'$.gol_ft_reforcado.modo'
                )='validacao_sombra'
        )
        SELECT * FROM independentes WHERE ordem=1
        ORDER BY datetime(criado_em),id LIMIT ?
        """,
        (
            documento["registrado_em"],
            VERSAO_GOL_FT_REFORCADO,
            TAMANHO_COORTE,
        ),
    ).fetchall()
    itens = [dict(item) for item in linhas]
    total = _metricas(itens)
    desenvolvimento = _metricas(itens[:DESENVOLVIMENTO])
    holdout = _metricas(itens[DESENVOLVIMENTO:TAMANHO_COORTE])
    fingerprints = {
        item["regra_fingerprint"] for item in itens
        if item["regra_fingerprint"]
    }
    linhagem_homogenea = len(fingerprints) <= 1 and all(
        item["regra_fingerprint"] for item in itens
    )
    coorte_fechada = len(itens) >= TAMANHO_COORTE
    resultados_completos = coorte_fechada and total["pendentes"] == 0
    intervalo = total["intervalo_roi_95"]
    if not coorte_fechada:
        decisao = "aguardando_amostra_futura"
    elif total["pendentes"]:
        decisao = "aguardando_resultados"
    elif not linhagem_homogenea:
        decisao = "linhagem_inconsistente"
    elif (
        total["validos"] >= MINIMO_VALIDOS_TOTAL
        and desenvolvimento["validos"]
        >= MINIMO_VALIDOS_DESENVOLVIMENTO
        and holdout["validos"] >= MINIMO_VALIDOS_HOLDOUT
        and total["roi"] is not None
        and total["roi"] > 0
        and intervalo is not None
        and intervalo[0] > 0
        and desenvolvimento["roi"] is not None
        and desenvolvimento["roi"] > 0
        and holdout["roi"] is not None
        and holdout["roi"] > 0
    ):
        decisao = "favoravel_para_revisao_manual"
    else:
        decisao = "inconclusiva_ou_desfavoravel"
    return {
        "versao": VERSAO_VALIDACAO,
        **total,
        "estado": "encerrada" if resultados_completos else "coletando",
        "decisao": decisao,
        "tamanho_coorte": TAMANHO_COORTE,
        "faltam": max(0, TAMANHO_COORTE - len(itens)),
        "coorte_fechada": coorte_fechada,
        "resultados_completos": resultados_completos,
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "linhagem_homogenea": linhagem_homogenea,
        "fingerprints": sorted(fingerprints),
        "registrado_em": documento["registrado_em"],
        "telegram": False,
        "promocao_automatica": False,
    }
