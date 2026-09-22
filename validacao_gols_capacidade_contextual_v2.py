"""Âncora prospectiva do challenger contextual V2 de gols."""

import hashlib
import json
import math
import statistics
from datetime import datetime

from gols_capacidade_contextual_v2 import (
    LINHAGEM,
    VERSAO_GOL_FT,
    VERSAO_GOL_HT,
    VERSAO_POLITICA,
)


VERSAO_VALIDACAO = "validacao-gols-capacidade-contextual-v2b"
VERSAO_POLITICA_VALIDACAO = "politica-validacao-gols-capacidade-contextual-v2b"
VERSOES_AVALIADAS = (VERSAO_GOL_HT, VERSAO_GOL_FT)
SEGMENTOS = ("profissional", "sub21", "sub23", "reservas", "base_outra")
TAMANHO_COORTE = 100
TAMANHO_DESENVOLVIMENTO = 70
TAMANHO_HOLDOUT = 30
MINIMO_VALIDOS_TOTAL = 95
MINIMO_VALIDOS_HOLDOUT = 28
CHECKPOINTS = (20, 40, 60, 80, 100)
CHAVE_DEFINICAO = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"
CHAVE_POLITICA = f"exploracao_sombra_politica:{VERSAO_VALIDACAO}"
VERSAO_VALIDACAO_GRUPO_FT = (
    "validacao-gol-ft-capacidade-contextual-v2b-grupo-v1"
)
VERSAO_POLITICA_GRUPO_FT = (
    "politica-validacao-gol-ft-capacidade-contextual-v2b-grupo-v1"
)
CHAVE_DEFINICAO_GRUPO_FT = (
    f"exploracao_grupo_definicao:{VERSAO_VALIDACAO_GRUPO_FT}"
)
CHAVE_POLITICA_GRUPO_FT = (
    f"exploracao_grupo_politica:{VERSAO_VALIDACAO_GRUPO_FT}"
)
MINIMO_ALERTA_DESFAVORAVEL_GRUPO = 20


def _com_hash(documento, campo):
    canonico = json.dumps(
        documento, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **documento,
        campo: hashlib.sha256(canonico.encode("utf-8")).hexdigest(),
    }


def definicao():
    return _com_hash({
        "versao": VERSAO_VALIDACAO,
        "politica_geracao": VERSAO_POLITICA,
        "versoes_avaliadas": list(VERSOES_AVALIADAS),
        "segmentos": list(SEGMENTOS),
        "linhagem_sha256": LINHAGEM,
        "populacao": "primeiras_simulacoes_sombra_pos_ancora",
        "independencia": "primeiro_por_partida_mercado_braco_segmento",
        "tamanho_coorte_fixa_por_braco_segmento": TAMANHO_COORTE,
        "desenvolvimento": TAMANHO_DESENVOLVIMENTO,
        "holdout_final": TAMANHO_HOLDOUT,
        "historico_pre_ancora": "observacional_nao_validante",
        "telegram_oficial": False,
        "promocao_automatica": False,
    }, "definicao_sha256")


def politica():
    return _com_hash({
        "versao": VERSAO_POLITICA_VALIDACAO,
        "experimento": VERSAO_VALIDACAO,
        "minimo_resultados_validos_total": MINIMO_VALIDOS_TOTAL,
        "minimo_resultados_validos_holdout": MINIMO_VALIDOS_HOLDOUT,
        "confianca": 0.95,
        "criterios_favoraveis": [
            "coorte_fixa_encerrada", "sem_pendencias", "linhagem_homogenea",
            "roi_total_maior_que_zero",
            "limite_inferior_ic95_roi_total_maior_que_zero",
            "roi_desenvolvimento_maior_que_zero", "roi_holdout_maior_que_zero",
        ],
        "avaliacao_separada_por_segmento": True,
        "promocao_automatica": False,
    }, "politica_sha256")


def definicao_grupo_ft():
    return _com_hash({
        "versao": VERSAO_VALIDACAO_GRUPO_FT,
        "versao_avaliada": VERSAO_GOL_FT,
        "mercado": "gol_ft",
        "linhagem_sha256": LINHAGEM,
        "populacao": "primeiros_sinais_entregues_grupo_pos_ativacao",
        "independencia": "primeiro_por_partida_mercado_braco",
        "tamanho_coorte_fixa": TAMANHO_COORTE,
        "desenvolvimento": TAMANHO_DESENVOLVIMENTO,
        "holdout_final": TAMANHO_HOLDOUT,
        "segmentos_auditados": list(SEGMENTOS),
        "historico_pre_ativacao": "excluido",
        "grupo_telegram_ativo": True,
        "promocao_automatica": False,
    }, "definicao_sha256")


def politica_grupo_ft():
    return _com_hash({
        "versao": VERSAO_POLITICA_GRUPO_FT,
        "experimento": VERSAO_VALIDACAO_GRUPO_FT,
        "minimo_resultados_alerta_desfavoravel": (
            MINIMO_ALERTA_DESFAVORAVEL_GRUPO
        ),
        "regra_alerta_desfavoravel": (
            "limite_superior_ic95_roi_menor_que_zero"
        ),
        "criterios_favoraveis_finais": [
            "coorte_fixa_encerrada",
            "sem_pendencias",
            "linhagem_homogenea",
            "roi_total_maior_que_zero",
            "limite_inferior_ic95_roi_total_maior_que_zero",
            "roi_desenvolvimento_maior_que_zero",
            "roi_holdout_maior_que_zero",
        ],
        "rollback": (
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO=0"
        ),
        "rollback_automatico": False,
    }, "politica_sha256")


def _registrar(conexao, chave, esperado, registrado_em=None):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in esperado.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Challenger contextual V2 diverge da âncora imutável; "
                    "crie nova versão antes de coletar."
                )
        return existente
    documento = dict(esperado)
    documento["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados(chave, valor) VALUES (?, ?)",
            (chave, json.dumps(documento, ensure_ascii=False, sort_keys=True)),
        )
    return documento


def registrar_ou_validar_gols_capacidade_contextual_v2(conexao, registrado_em=None):
    return {
        "definicao": _registrar(conexao, CHAVE_DEFINICAO, definicao(), registrado_em),
        "politica": _registrar(conexao, CHAVE_POLITICA, politica(), registrado_em),
    }


def registrar_ou_validar_grupo_ft_capacidade_contextual_v2(
    conexao, registrado_em=None
):
    return {
        "definicao": _registrar(
            conexao,
            CHAVE_DEFINICAO_GRUPO_FT,
            definicao_grupo_ft(),
            registrado_em,
        ),
        "politica": _registrar(
            conexao,
            CHAVE_POLITICA_GRUPO_FT,
            politica_grupo_ft(),
            registrado_em,
        ),
    }


def auditar_validacao_gols_capacidade_contextual_v2(conexao, exigir_registro=False):
    esperados = {CHAVE_DEFINICAO: definicao(), CHAVE_POLITICA: politica()}
    ausentes, divergencias = [], []
    for chave, esperado in esperados.items():
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave,)
        ).fetchone()
        if linha is None:
            ausentes.append(chave)
            continue
        try:
            documento = json.loads(linha["valor"])
        except (TypeError, json.JSONDecodeError):
            divergencias.append(f"{chave}:json_invalido")
            continue
        divergencias.extend(
            f"{chave}:{campo}" for campo, valor in esperado.items()
            if documento.get(campo) != valor
        )
    sinais = int(conexao.execute(
        """
        SELECT COUNT(*) FROM sinais
        WHERE json_extract(features_json, '$.exploracao_sombra.versao') IN (?, ?)
        """, VERSOES_AVALIADAS,
    ).fetchone()[0] or 0)
    obrigatorio = bool(exigir_registro or sinais)
    saudavel = not divergencias and (not ausentes or not obrigatorio)
    return {
        "saudavel": saudavel,
        "estado": (
            "valida" if saudavel and not ausentes
            else "aguardando_primeiro_registro" if saudavel
            else "nao_registrada" if ausentes else "inconsistente"
        ),
        "versao": VERSAO_VALIDACAO,
        "registrada": not ausentes,
        "metadados_ausentes": ausentes,
        "divergencias": divergencias,
        "sinais_existentes": sinais,
        "promocao_automatica": False,
    }


def auditar_grupo_ft_capacidade_contextual_v2(
    conexao, exigir_registro=False
):
    esperados = {
        CHAVE_DEFINICAO_GRUPO_FT: definicao_grupo_ft(),
        CHAVE_POLITICA_GRUPO_FT: politica_grupo_ft(),
    }
    ausentes, divergencias = [], []
    for chave, esperado in esperados.items():
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave,)
        ).fetchone()
        if linha is None:
            ausentes.append(chave)
            continue
        try:
            documento = json.loads(linha["valor"])
        except (TypeError, json.JSONDecodeError):
            divergencias.append(f"{chave}:json_invalido")
            continue
        divergencias.extend(
            f"{chave}:{campo}"
            for campo, valor in esperado.items()
            if documento.get(campo) != valor
        )
    entregues = int(conexao.execute(
        """
        SELECT COUNT(DISTINCT s.id)
        FROM sinais s
        JOIN entregas_alertas e ON e.sinal_id=s.id
        WHERE e.status='entregue'
          AND e.canal LIKE '%:teste'
          AND e.canal NOT LIKE '%:resultado'
          AND json_extract(
            s.features_json, '$.exploracao_sombra.versao'
          )=?
        """,
        (VERSAO_GOL_FT,),
    ).fetchone()[0] or 0)
    obrigatorio = bool(exigir_registro or entregues)
    saudavel = not divergencias and (not ausentes or not obrigatorio)
    return {
        "saudavel": saudavel,
        "estado": (
            "valida" if saudavel and not ausentes
            else "aguardando_ativacao" if saudavel
            else "nao_registrada" if ausentes else "inconsistente"
        ),
        "versao": VERSAO_VALIDACAO_GRUPO_FT,
        "registrada": not ausentes,
        "metadados_ausentes": ausentes,
        "divergencias": divergencias,
        "sinais_entregues_existentes": entregues,
        "rollback_automatico": False,
    }


def _intervalo_roi(retornos):
    if len(retornos) < 2:
        return None
    media = statistics.fmean(retornos)
    erro = statistics.stdev(retornos) / math.sqrt(len(retornos))
    return [round(media - 1.96 * erro, 4), round(media + 1.96 * erro, 4)]


def _metricas(linhas):
    validas = [
        x for x in linhas
        if x["resultado"] in ("green", "half_green", "red", "half_red")
        and x["retorno_unidades"] is not None
    ]
    retornos = [float(x["retorno_unidades"]) for x in validas]
    lucro = round(sum(retornos), 4)
    return {
        "candidatos": len(linhas), "validos": len(validas),
        "greens": sum(x["resultado"] in ("green", "half_green") for x in validas),
        "reds": sum(x["resultado"] in ("red", "half_red") for x in validas),
        "pendentes": sum(x["resultado"] is None for x in linhas),
        "lucro_unidades": lucro,
        "roi": round(lucro / len(validas), 4) if validas else None,
        "intervalo_roi_95": _intervalo_roi(retornos),
    }


def _linhas(conexao, inicio, versao, segmento):
    return conexao.execute(
        """
        WITH independentes AS (
          SELECT s.id, s.partida_id, s.criado_em,
                 r.resultado, r.retorno_unidades,
                 json_extract(s.features_json,
                   '$.gol_capacidade_contextual_v2.linhagem_sha256') AS linhagem,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.partida_id, s.mercado,
                     json_extract(s.features_json, '$.exploracao_sombra.versao'),
                     json_extract(s.features_json,
                       '$.gol_capacidade_contextual_v2.segmento_competicao')
                   ORDER BY datetime(s.criado_em), s.id
                 ) AS ordem
          FROM sinais s
          LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE datetime(s.criado_em)>=datetime(?)
            AND s.status='simulacao'
            AND json_extract(s.features_json, '$.exploracao_sombra.versao')=?
            AND json_extract(s.features_json,
              '$.gol_capacidade_contextual_v2.segmento_competicao')=?
        )
        SELECT id, criado_em, resultado, retorno_unidades, linhagem
        FROM independentes WHERE ordem=1
        ORDER BY datetime(criado_em), id LIMIT ?
        """, (inicio, versao, segmento, TAMANHO_COORTE),
    ).fetchall()


def resumir_validacao_gols_capacidade_contextual_v2(conexao):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is None:
        return {"estado": "nao_registrado", "por_braco_segmento": {}}
    documento = json.loads(linha["valor"])
    inicio, linhagem = documento["registrado_em"], documento["linhagem_sha256"]
    saida = {}
    for versao in VERSOES_AVALIADAS:
        for segmento in SEGMENTOS:
            todas = _linhas(conexao, inicio, versao, segmento)
            compativeis = [x for x in todas if x["linhagem"] == linhagem]
            total = _metricas(compativeis)
            desenvolvimento = _metricas(compativeis[:TAMANHO_DESENVOLVIMENTO])
            holdout = _metricas(compativeis[TAMANHO_DESENVOLVIMENTO:TAMANHO_COORTE])
            intervalo = total["intervalo_roi_95"]
            homogenea = len(compativeis) == len(todas)
            if not homogenea:
                decisao = "linhagem_inconsistente"
            elif len(todas) < TAMANHO_COORTE:
                decisao = "aguardando_amostra_futura"
            elif total["pendentes"]:
                decisao = "aguardando_resultados"
            elif total["validos"] < MINIMO_VALIDOS_TOTAL or holdout["validos"] < MINIMO_VALIDOS_HOLDOUT:
                decisao = "amostra_valida_insuficiente"
            elif (
                total["roi"] is not None and total["roi"] > 0
                and intervalo is not None and intervalo[0] > 0
                and desenvolvimento["roi"] is not None and desenvolvimento["roi"] > 0
                and holdout["roi"] is not None and holdout["roi"] > 0
            ):
                decisao = "favoravel_para_revisao_independente"
            elif intervalo is not None and intervalo[1] < 0:
                decisao = "evidencia_desfavoravel"
            else:
                decisao = "inconclusiva"
            saida[f"{versao}|{segmento}"] = {
                **total,
                "versao": versao, "segmento": segmento,
                "faltam": max(0, TAMANHO_COORTE - len(todas)),
                "linhagem_homogenea": homogenea,
                "desenvolvimento": desenvolvimento, "holdout": holdout,
                "decisao_estatistica": decisao,
                "proximo_checkpoint": next((n for n in CHECKPOINTS if n > total["validos"]), None),
            }
    return {
        "estado": "coletando", "versao": VERSAO_VALIDACAO,
        "registrado_em": inicio, "linhagem_sha256": linhagem,
        "por_braco_segmento": saida,
        "telegram_oficial": False, "promocao_automatica": False,
    }


def _linhas_grupo_ft(conexao, inicio):
    return conexao.execute(
        """
        WITH entregues AS (
          SELECT sinal_id
          FROM entregas_alertas
          WHERE status='entregue'
            AND canal LIKE '%:teste'
            AND canal NOT LIKE '%:resultado'
          GROUP BY sinal_id
        ), independentes AS (
          SELECT s.id, s.partida_id, s.criado_em,
                 r.resultado, r.retorno_unidades,
                 json_extract(
                   s.features_json,
                   '$.gol_capacidade_contextual_v2.linhagem_sha256'
                 ) AS linhagem,
                 json_extract(
                   s.features_json,
                   '$.gol_capacidade_contextual_v2.segmento_competicao'
                 ) AS segmento,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.partida_id, s.mercado,
                     json_extract(
                       s.features_json, '$.exploracao_sombra.versao'
                     )
                   ORDER BY datetime(s.criado_em), s.id
                 ) AS ordem
          FROM sinais s
          JOIN entregues e ON e.sinal_id=s.id
          LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE datetime(s.criado_em)>=datetime(?)
            AND s.status='simulacao'
            AND s.mercado='gol_ft'
            AND json_extract(
              s.features_json, '$.exploracao_sombra.versao'
            )=?
        )
        SELECT id, criado_em, resultado, retorno_unidades,
               linhagem, segmento
        FROM independentes
        WHERE ordem=1
        ORDER BY datetime(criado_em), id
        LIMIT ?
        """,
        (inicio, VERSAO_GOL_FT, TAMANHO_COORTE),
    ).fetchall()


def resumir_grupo_ft_capacidade_contextual_v2(conexao):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (CHAVE_DEFINICAO_GRUPO_FT,),
    ).fetchone()
    if linha is None:
        return {
            "estado": "nao_registrado",
            "versao": VERSAO_VALIDACAO_GRUPO_FT,
            "grupo_ativo": True,
            "rollback_recomendado": False,
        }
    documento = json.loads(linha["valor"])
    inicio = documento["registrado_em"]
    linhagem = documento["linhagem_sha256"]
    todas = _linhas_grupo_ft(conexao, inicio)
    compativeis = [x for x in todas if x["linhagem"] == linhagem]
    total = _metricas(compativeis)
    desenvolvimento = _metricas(
        compativeis[:TAMANHO_DESENVOLVIMENTO]
    )
    holdout = _metricas(
        compativeis[TAMANHO_DESENVOLVIMENTO:TAMANHO_COORTE]
    )
    intervalo = total["intervalo_roi_95"]
    linhagem_homogenea = len(compativeis) == len(todas)
    alerta_desfavoravel = bool(
        total["validos"] >= MINIMO_ALERTA_DESFAVORAVEL_GRUPO
        and intervalo is not None
        and intervalo[1] < 0
    )
    if not linhagem_homogenea:
        decisao = "linhagem_inconsistente"
    elif alerta_desfavoravel:
        decisao = "evidencia_desfavoravel"
    elif len(todas) < TAMANHO_COORTE:
        decisao = "aguardando_amostra_futura"
    elif total["pendentes"]:
        decisao = "aguardando_resultados"
    elif (
        total["validos"] < MINIMO_VALIDOS_TOTAL
        or holdout["validos"] < MINIMO_VALIDOS_HOLDOUT
    ):
        decisao = "amostra_valida_insuficiente"
    elif (
        total["roi"] is not None
        and total["roi"] > 0
        and intervalo is not None
        and intervalo[0] > 0
        and desenvolvimento["roi"] is not None
        and desenvolvimento["roi"] > 0
        and holdout["roi"] is not None
        and holdout["roi"] > 0
    ):
        decisao = "favoravel_para_revisao_independente"
    else:
        decisao = "inconclusiva"
    por_segmento = {
        segmento: _metricas([
            x for x in compativeis if x["segmento"] == segmento
        ])
        for segmento in SEGMENTOS
    }
    return {
        **total,
        "estado": "coletando",
        "versao": VERSAO_VALIDACAO_GRUPO_FT,
        "versao_avaliada": VERSAO_GOL_FT,
        "registrado_em": inicio,
        "linhagem_sha256": linhagem,
        "grupo_ativo": True,
        "candidatos_coorte": len(todas),
        "faltam": max(0, TAMANHO_COORTE - len(todas)),
        "linhagem_homogenea": linhagem_homogenea,
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "por_segmento": por_segmento,
        "decisao_estatistica": decisao,
        "proximo_checkpoint": next(
            (n for n in CHECKPOINTS if n > total["validos"]), None
        ),
        "alerta_desfavoravel": alerta_desfavoravel,
        "rollback_recomendado": alerta_desfavoravel,
        "rollback": "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO=0",
        "rollback_automatico": False,
    }
