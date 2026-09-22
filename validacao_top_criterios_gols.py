"""Âncoras prospectivas independentes dos challengers Top HT e Top FT."""

import hashlib
import json
import math
import statistics
from datetime import datetime

from top_criterios_gols import LINHAGEM, VERSAO_FT, VERSAO_HT, VERSAO_POLITICA


TAMANHO_COORTE = 100
DESENVOLVIMENTO = 70
HOLDOUT = 30
VERSAO_VALIDACAO_HT = "validacao-top-criterio-ht-v1"
VERSAO_VALIDACAO_FT = "validacao-top-criterio-ft-v1"


def _chave(versao_validacao):
    return f"exploracao_sombra_definicao:{versao_validacao}"


def _definicao(versao_validacao, regra):
    base = {
        "versao": versao_validacao,
        "regra": regra,
        "politica": VERSAO_POLITICA,
        "linhagem_sha256": LINHAGEM,
        "populacao": "primeiro_sinal_por_partida_pos_ancora",
        "tamanho_coorte": TAMANHO_COORTE,
        "desenvolvimento": DESENVOLVIMENTO,
        "holdout": HOLDOUT,
        "criterio": "roi_total_ic95_inferior_dev_e_holdout_positivos",
        "promocao_automatica": False,
    }
    serializado = json.dumps(
        base, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **base,
        "definicao_sha256": hashlib.sha256(
            serializado.encode("utf-8")
        ).hexdigest(),
    }


def _registrar(conexao, versao_validacao, regra, registrado_em=None):
    esperado = _definicao(versao_validacao, regra)
    chave = _chave(versao_validacao)
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        if any(existente.get(k) != v for k, v in esperado.items()):
            raise RuntimeError(
                "Top critério diverge da âncora imutável; crie nova versão."
            )
        return existente
    documento = {
        **esperado,
        "registrado_em": (registrado_em or datetime.now()).replace(
            microsecond=0
        ).isoformat(),
    }
    with conexao:
        conexao.execute(
            "INSERT INTO metadados(chave,valor) VALUES (?,?)",
            (chave, json.dumps(documento, ensure_ascii=False, sort_keys=True)),
        )
    return documento


def registrar_ou_validar_top_criterios_gols(conexao, registrado_em=None):
    return {
        "ht": _registrar(
            conexao, VERSAO_VALIDACAO_HT, VERSAO_HT, registrado_em
        ),
        "ft": _registrar(
            conexao, VERSAO_VALIDACAO_FT, VERSAO_FT, registrado_em
        ),
    }


def _metricas(linhas):
    resolvidos = [x for x in linhas if x["resultado"] in {"green", "red"}]
    retornos = [float(x["retorno_unidades"]) for x in resolvidos]
    roi = sum(retornos) / len(retornos) if retornos else None
    intervalo = None
    if len(retornos) >= 2:
        erro = 1.96 * statistics.stdev(retornos) / math.sqrt(len(retornos))
        intervalo = [round(roi - erro, 4), round(roi + erro, 4)]
    return {
        "candidatos": len(linhas), "validos": len(resolvidos),
        "greens": sum(x["resultado"] == "green" for x in resolvidos),
        "reds": sum(x["resultado"] == "red" for x in resolvidos),
        "pendentes": len(linhas) - len(resolvidos),
        "lucro_unidades": round(sum(retornos), 4),
        "roi": round(roi, 4) if roi is not None else None,
        "intervalo_roi_95": intervalo,
    }


def resumir_top_criterio(conexao, versao_validacao, regra):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (_chave(versao_validacao),),
    ).fetchone()
    if linha is None:
        return {"estado": "nao_registrada"}
    documento = json.loads(linha["valor"])
    linhas = conexao.execute(
        """
        WITH independentes AS (
          SELECT s.id,s.partida_id,s.criado_em,r.resultado,r.retorno_unidades,
                 json_extract(s.features_json,
                   '$.top_criterio_gols.linhagem_sha256') AS linhagem,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.partida_id
                   ORDER BY datetime(s.criado_em),s.id
                 ) AS ordem
          FROM sinais s
          LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE datetime(s.criado_em)>=datetime(?)
            AND s.status='simulacao'
            AND json_extract(s.features_json,'$.exploracao_sombra.versao')=?
        )
        SELECT * FROM independentes WHERE ordem=1
        ORDER BY datetime(criado_em),id LIMIT ?
        """, (documento["registrado_em"], regra, TAMANHO_COORTE),
    ).fetchall()
    compativeis = [x for x in linhas if x["linhagem"] == LINHAGEM]
    total = _metricas(compativeis)
    dev = _metricas(compativeis[:DESENVOLVIMENTO])
    holdout = _metricas(compativeis[DESENVOLVIMENTO:TAMANHO_COORTE])
    intervalo = total["intervalo_roi_95"]
    if len(linhas) < TAMANHO_COORTE:
        decisao = "aguardando_amostra_futura"
    elif total["pendentes"]:
        decisao = "aguardando_resultados"
    elif (
        len(compativeis) == len(linhas)
        and total["validos"] >= 95 and holdout["validos"] >= 28
        and total["roi"] is not None and total["roi"] > 0
        and intervalo is not None and intervalo[0] > 0
        and dev["roi"] is not None and dev["roi"] > 0
        and holdout["roi"] is not None and holdout["roi"] > 0
    ):
        decisao = "favoravel_para_revisao"
    else:
        decisao = "inconclusiva"
    return {
        **total, "estado": "coletando", "decisao": decisao,
        "faltam": max(0, TAMANHO_COORTE - len(linhas)),
        "desenvolvimento": dev, "holdout": holdout,
        "linhagem_homogenea": len(compativeis) == len(linhas),
        "registrado_em": documento["registrado_em"],
        "linhagem_sha256": documento["linhagem_sha256"],
        "versao_avaliada": regra,
    }


def resumir_top_criterios_gols(conexao):
    return {
        "ht": resumir_top_criterio(
            conexao, VERSAO_VALIDACAO_HT, VERSAO_HT
        ),
        "ft": resumir_top_criterio(
            conexao, VERSAO_VALIDACAO_FT, VERSAO_FT
        ),
    }
