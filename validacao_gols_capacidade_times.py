"""Âncora e avaliação prospectiva da rota histórica por capacidade."""

import hashlib
import json
import math
import statistics
from datetime import datetime

from gols_capacidade_times import (
    LINHAGEM_GOLS_CAPACIDADE,
    VERSAO_GOL_FT_CAPACIDADE,
    VERSAO_GOL_HT_CAPACIDADE,
    VERSAO_POLITICA,
)


VERSAO_VALIDACAO = "validacao-gols-capacidade-times-v1"
VERSAO_POLITICA_VALIDACAO = "politica-validacao-gols-capacidade-times-v1"
VERSOES_AVALIADAS = (
    VERSAO_GOL_HT_CAPACIDADE,
    VERSAO_GOL_FT_CAPACIDADE,
)
TAMANHO_COORTE = 100
TAMANHO_DESENVOLVIMENTO = 70
TAMANHO_HOLDOUT = 30
MINIMO_VALIDOS_TOTAL = 95
MINIMO_VALIDOS_HOLDOUT = 28
CHECKPOINTS_DESCRITIVOS = (20, 40, 60, 80, 100)
CHAVE_DEFINICAO = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"
CHAVE_POLITICA = f"exploracao_sombra_politica:{VERSAO_VALIDACAO}"


def _com_hash(nucleo, campo):
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        campo: hashlib.sha256(canonico.encode("utf-8")).hexdigest(),
    }


def definicao_gols_capacidade_times():
    return _com_hash({
        "versao": VERSAO_VALIDACAO,
        "politica_geracao": VERSAO_POLITICA,
        "versoes_avaliadas": list(VERSOES_AVALIADAS),
        "linhagem_sha256": LINHAGEM_GOLS_CAPACIDADE,
        "populacao": "primeiros_sinais_teste_entregues_pos_ancora",
        "independencia": "primeiro_por_partida_mercado_braco",
        "tamanho_coorte_fixa_por_braco": TAMANHO_COORTE,
        "desenvolvimento": TAMANHO_DESENVOLVIMENTO,
        "holdout_final": TAMANHO_HOLDOUT,
        "historico_pre_ancora": "observacional_nao_validante",
        "telegram_oficial": False,
        "promocao_automatica": False,
    }, "definicao_sha256")


def politica_validacao_gols_capacidade_times():
    return _com_hash({
        "versao": VERSAO_POLITICA_VALIDACAO,
        "experimento": VERSAO_VALIDACAO,
        "minimo_resultados_validos_total": MINIMO_VALIDOS_TOTAL,
        "minimo_resultados_validos_holdout": MINIMO_VALIDOS_HOLDOUT,
        "confianca": 0.95,
        "metodo_intervalo_roi": "media_normal_bilateral_95",
        "checkpoints_descritivos": list(CHECKPOINTS_DESCRITIVOS),
        "criterios_favoraveis": [
            "coorte_fixa_encerrada",
            "sem_pendencias",
            "linhagem_homogenea",
            "roi_total_maior_que_zero",
            "limite_inferior_ic95_roi_total_maior_que_zero",
            "roi_desenvolvimento_maior_que_zero",
            "roi_holdout_maior_que_zero",
        ],
        "regra_seguranca": (
            "somente_alertar_se_limite_superior_ic95_roi_abaixo_de_zero"
        ),
        "promocao_automatica": False,
    }, "politica_sha256")


def _registrar_ou_validar(conexao, chave, esperado, registrado_em=None):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in esperado.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Rota de capacidade diverge da âncora imutável; "
                    "crie uma nova versão antes de coletar."
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


def registrar_ou_validar_gols_capacidade_times(conexao, registrado_em=None):
    return {
        "definicao": _registrar_ou_validar(
            conexao, CHAVE_DEFINICAO, definicao_gols_capacidade_times(),
            registrado_em,
        ),
        "politica": _registrar_ou_validar(
            conexao, CHAVE_POLITICA,
            politica_validacao_gols_capacidade_times(), registrado_em,
        ),
    }


def auditar_validacao_gols_capacidade_times(conexao, exigir_registro=False):
    esperados = {
        CHAVE_DEFINICAO: definicao_gols_capacidade_times(),
        CHAVE_POLITICA: politica_validacao_gols_capacidade_times(),
    }
    ausentes = []
    divergencias = []
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
        for campo, valor in esperado.items():
            if documento.get(campo) != valor:
                divergencias.append(f"{chave}:{campo}")
    sinais = int(conexao.execute(
        """
        SELECT COUNT(*) FROM sinais
        WHERE json_extract(features_json, '$.exploracao_sombra.versao')
          IN (?, ?)
        """,
        VERSOES_AVALIADAS,
    ).fetchone()[0] or 0)
    obrigatorio = bool(exigir_registro or sinais)
    saudavel = bool(not divergencias and (not ausentes or not obrigatorio))
    if saudavel and ausentes:
        estado = "aguardando_primeiro_registro"
    elif saudavel:
        estado = "valida"
    elif ausentes:
        estado = "nao_registrada"
    else:
        estado = "inconsistente"
    return {
        "saudavel": saudavel,
        "estado": estado,
        "versao": VERSAO_VALIDACAO,
        "registrada": not ausentes,
        "metadados_ausentes": ausentes,
        "divergencias": divergencias,
        "sinais_existentes": sinais,
        "protegida": True,
        "promocao_automatica": False,
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
        "total": len(linhas),
        "validos": len(validas),
        "greens": sum(
            x["resultado"] in ("green", "half_green") for x in validas
        ),
        "reds": sum(
            x["resultado"] in ("red", "half_red") for x in validas
        ),
        "pendentes": sum(x["resultado"] is None for x in linhas),
        "lucro_unidades": lucro,
        "roi": round(lucro / len(validas), 4) if validas else None,
        "intervalo_roi_95": _intervalo_roi(retornos),
    }


def _linhas_braco(conexao, inicio, versao):
    return conexao.execute(
        """
        WITH entregues AS (
          SELECT sinal_id FROM entregas_alertas
          WHERE status='entregue' AND canal LIKE '%:teste'
            AND canal NOT LIKE '%:resultado' GROUP BY sinal_id
        ), independentes AS (
          SELECT s.id, s.partida_id, s.mercado, s.criado_em,
                 r.resultado, r.retorno_unidades,
                 json_extract(s.features_json,
                   '$.gol_capacidade_times.linhagem_sha256') AS linhagem,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.partida_id, s.mercado,
                     json_extract(s.features_json,
                                  '$.exploracao_sombra.versao')
                   ORDER BY datetime(s.criado_em), s.id
                 ) AS ordem
          FROM sinais s JOIN entregues e ON e.sinal_id=s.id
          LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE datetime(s.criado_em)>=datetime(?)
            AND json_extract(s.features_json,
                             '$.exploracao_sombra.versao')=?
        )
        SELECT id, criado_em, resultado, retorno_unidades, linhagem
        FROM independentes WHERE ordem=1
        ORDER BY datetime(criado_em), id LIMIT ?
        """,
        (inicio, versao, TAMANHO_COORTE),
    ).fetchall()


def resumir_validacao_gols_capacidade_times(conexao):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is None:
        return {"estado": "nao_registrado", "por_braco": {}}
    definicao = json.loads(linha["valor"])
    inicio = definicao["registrado_em"]
    fingerprint = definicao["linhagem_sha256"]
    por_braco = {}
    for versao in VERSOES_AVALIADAS:
        todas = _linhas_braco(conexao, inicio, versao)
        compativeis = [x for x in todas if x["linhagem"] == fingerprint]
        total = _metricas(compativeis)
        desenvolvimento = _metricas(compativeis[:TAMANHO_DESENVOLVIMENTO])
        holdout = _metricas(
            compativeis[TAMANHO_DESENVOLVIMENTO:TAMANHO_COORTE]
        )
        intervalo = total["intervalo_roi_95"]
        linhagem_homogenea = len(compativeis) == len(todas)
        coorte_fechada = len(todas) >= TAMANHO_COORTE
        if not linhagem_homogenea:
            decisao = "linhagem_inconsistente"
        elif not coorte_fechada:
            decisao = "aguardando_amostra_futura"
        elif total["pendentes"]:
            decisao = "aguardando_resultados"
        elif (
            total["validos"] < MINIMO_VALIDOS_TOTAL
            or holdout["validos"] < MINIMO_VALIDOS_HOLDOUT
        ):
            decisao = "amostra_valida_insuficiente"
        elif (
            total["roi"] is not None and total["roi"] > 0
            and intervalo is not None and intervalo[0] > 0
            and desenvolvimento["roi"] is not None
            and desenvolvimento["roi"] > 0
            and holdout["roi"] is not None and holdout["roi"] > 0
        ):
            decisao = "favoravel_para_revisao_independente"
        elif intervalo is not None and intervalo[1] < 0:
            decisao = "evidencia_desfavoravel"
        else:
            decisao = "inconclusiva"
        proximo_checkpoint = next(
            (n for n in CHECKPOINTS_DESCRITIVOS if n > total["validos"]),
            None,
        )
        por_braco[versao] = {
            **total,
            "candidatos_coorte": len(todas),
            "faltam": max(0, TAMANHO_COORTE - len(todas)),
            "linhagem_homogenea": linhagem_homogenea,
            "desenvolvimento": desenvolvimento,
            "holdout": holdout,
            "decisao_estatistica": decisao,
            "proximo_checkpoint": proximo_checkpoint,
            "alerta_desfavoravel": bool(
                total["validos"] >= CHECKPOINTS_DESCRITIVOS[0]
                and intervalo is not None and intervalo[1] < 0
            ),
        }
    return {
        "estado": "coletando",
        "versao": VERSAO_VALIDACAO,
        "registrado_em": inicio,
        "linhagem_sha256": fingerprint,
        "por_braco": por_braco,
        "telegram_oficial": False,
        "promocao_automatica": False,
    }
