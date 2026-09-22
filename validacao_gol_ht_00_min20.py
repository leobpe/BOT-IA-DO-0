"""Âncora prospectiva da rota HT 0-0 entre 20 e 28 minutos."""

import hashlib
import json
import math
import statistics
from datetime import datetime

from gol_ht_00_min20 import LINHAGEM, VERSAO, VERSAO_POLITICA


VERSAO_VALIDACAO = "validacao-gol-ht-00-min20-apoio-duplo-atividade5-v5"
TAMANHO_COORTE = 100
DESENVOLVIMENTO = 70
HOLDOUT = 30
CHAVE = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"


def definicao():
    base = {
        "versao": VERSAO_VALIDACAO,
        "regra": VERSAO,
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
        "definicao_sha256": hashlib.sha256(serializado.encode("utf-8")).hexdigest(),
    }


def registrar_ou_validar_gol_ht_00_min20(conexao, registrado_em=None):
    esperado = definicao()
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        if any(existente.get(k) != v for k, v in esperado.items()):
            raise RuntimeError(
                "Gol HT 0-0 min20 diverge da âncora imutável; crie nova versão."
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
            (CHAVE, json.dumps(documento, ensure_ascii=False, sort_keys=True)),
        )
    return documento


def auditar_validacao_gol_ht_00_min20(conexao, exigir_registro=False):
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
        return {"saudavel": False, "estado": "json_invalido", "versao": VERSAO_VALIDACAO}
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
        x for x in linhas
        if x["resultado"] in ("green", "half_green", "red", "half_red")
        and x["retorno_unidades"] is not None
    ]
    retornos = [float(x["retorno_unidades"]) for x in validas]
    lucro = sum(retornos)
    intervalo = None
    if len(retornos) >= 2:
        erro = statistics.stdev(retornos) / math.sqrt(len(retornos))
        media = statistics.fmean(retornos)
        intervalo = [round(media - 1.96 * erro, 4), round(media + 1.96 * erro, 4)]
    return {
        "candidatos": len(linhas), "validos": len(validas),
        "greens": sum(x["resultado"] in ("green", "half_green") for x in validas),
        "reds": sum(x["resultado"] in ("red", "half_red") for x in validas),
        "pendentes": sum(x["resultado"] is None for x in linhas),
        "lucro_unidades": round(lucro, 4),
        "roi": round(lucro / len(validas), 4) if validas else None,
        "intervalo_roi_95": intervalo,
    }


def resumir_validacao_gol_ht_00_min20(conexao):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE,)
    ).fetchone()
    if linha is None:
        return {"estado": "nao_registrada"}
    documento = json.loads(linha["valor"])
    linhas = conexao.execute(
        """
        WITH independentes AS (
          SELECT s.id,s.partida_id,s.criado_em,r.resultado,r.retorno_unidades,
                 json_extract(s.features_json,
                   '$.gol_ht_00_min20.linhagem_sha256') AS linhagem,
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
        """, (documento["registrado_em"], VERSAO, TAMANHO_COORTE),
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
        "versao_avaliada": VERSAO,
    }
