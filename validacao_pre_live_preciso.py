"""Validacao prospectiva imutavel do filtro pre-live preciso.

O historico anterior a ancora continua visivel apenas como diagnostico. A
decisao usa os primeiros 60 bilhetes V12 registrados depois da ancora que
passariam exatamente pelo filtro de entrega, independentemente de terem sido
publicados. Assim uma suspensao do Telegram nao interrompe a coleta sombra e
o resultado nunca escolhe quais observacoes entram na coorte.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

from filtro_pre_live_preciso import (
    EDGE_CONSERVADOR_MINIMO,
    MERCADOS_FRACOS,
    QUALIDADE_MINIMA,
    VERSAO as VERSAO_FILTRO,
    avaliar_criterios_bilhete_pre_live_preciso,
)


VERSAO_VALIDACAO = "validacao-pre-live-preciso-v2"
VERSAO_ALVO = "seletor-pre-live-retorno-dia30-odd150-v12"
CHAVE_DEFINICAO = f"validacao_definicao:{VERSAO_VALIDACAO}:{VERSAO_FILTRO}"
TAMANHO_COORTE = 60
DESENVOLVIMENTO = 42
HOLDOUT = 18
RESULTADOS_VALIDOS_MINIMOS = 55
RESULTADOS_VALIDOS_DESENVOLVIMENTO_MINIMOS = 38
RESULTADOS_VALIDOS_HOLDOUT_MINIMOS = 16
CHECKPOINT_SEGURANCA = 25
COBERTURA_REFERENCIA_SEM_VIG_MINIMA = 0.90
RESULTADOS_VALIDOS = {"green", "red"}


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _consulta_dicionarios(conexao, consulta, parametros=()):
    cursor = conexao.execute(consulta, parametros)
    colunas = [item[0] for item in cursor.description]
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def definicao():
    nucleo = {
        "versao": VERSAO_VALIDACAO,
        "versao_filtro": VERSAO_FILTRO,
        "versao_seletor": VERSAO_ALVO,
        "fase": "validacao_prospectiva",
        "populacao": (
            "primeiros_60_bilhetes_elegiveis_congelados_no_sqlite_apos_"
            "ancora_sem_consultar_resultado"
        ),
        "criterios_filtro": {
            "mercados_excluidos": sorted(MERCADOS_FRACOS),
            "multipla_pura_under_excluida": True,
            "qualidade_contexto_minima_por_perna": QUALIDADE_MINIMA,
            "edge_conservador_bilhete_minimo": EDGE_CONSERVADOR_MINIMO,
        },
        "coorte_fixa": TAMANHO_COORTE,
        "desenvolvimento": DESENVOLVIMENTO,
        "holdout": HOLDOUT,
        "resultados_validos_minimos": RESULTADOS_VALIDOS_MINIMOS,
        "resultados_validos_desenvolvimento_minimos": (
            RESULTADOS_VALIDOS_DESENVOLVIMENTO_MINIMOS
        ),
        "resultados_validos_holdout_minimos": (
            RESULTADOS_VALIDOS_HOLDOUT_MINIMOS
        ),
        "checkpoint_fixo": CHECKPOINT_SEGURANCA,
        "cobertura_referencia_sem_vig_minima": (
            COBERTURA_REFERENCIA_SEM_VIG_MINIMA
        ),
        "criterio_favoravel": (
            "roi_total_ic95_inferior_positivo_roi_dev_holdout_positivos_"
            "e_residuo_sem_vig_total_holdout_ic95_inferior_positivo"
        ),
        "criterio_suspensao": (
            "limite_superior_ic95_roi_primeiros_25_abaixo_de_zero"
        ),
        "referencia_multipla": (
            "produto_das_probabilidades_sem_margem_das_pernas"
        ),
        "promocao_automatica": False,
        "reativacao_automatica": False,
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


def registrar_ou_validar_definicao(conexao, registrado_em=None):
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS metadados_pre_live (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
        """
    )
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS coorte_pre_live_preciso (
            definicao_sha256 TEXT NOT NULL,
            bilhete_id INTEGER NOT NULL,
            ordem INTEGER NOT NULL,
            incluido_em TEXT NOT NULL,
            odd_total REAL NOT NULL,
            bilhete_json TEXT NOT NULL,
            PRIMARY KEY(definicao_sha256, bilhete_id),
            UNIQUE(definicao_sha256, ordem)
        )
        """
    )
    esperada = definicao()
    linha = conexao.execute(
        "SELECT valor FROM metadados_pre_live WHERE chave=?",
        (CHAVE_DEFINICAO,),
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha[0])
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        if divergencias:
            raise RuntimeError(
                "Ancora do filtro pre-live preciso inconsistente: "
                + ",".join(divergencias)
            )
        return existente
    instante = registrado_em or datetime.now(timezone.utc)
    if isinstance(instante, datetime):
        instante = instante.replace(microsecond=0).isoformat()
    esperada["registrado_em"] = str(instante)
    with conexao:
        conexao.execute(
            "INSERT INTO metadados_pre_live (chave, valor) VALUES (?, ?)",
            (
                CHAVE_DEFINICAO,
                json.dumps(esperada, ensure_ascii=False, sort_keys=True),
            ),
        )
    return esperada


def sincronizar_coorte_pre_live_preciso(conexao, agora=None):
    """Congela novas elegiveis em ordem causal, sem ler seus resultados."""
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "estado": "ancora_ausente", "inseridos": 0,
            "candidatos": 0, "faltam": TAMANHO_COORTE,
        }
    sha = documento["definicao_sha256"]
    linha_total = conexao.execute(
        """
        SELECT COUNT(*) FROM coorte_pre_live_preciso
        WHERE definicao_sha256=?
        """,
        (sha,),
    ).fetchone()
    total = int(linha_total[0] or 0)
    if total >= TAMANHO_COORTE:
        return {
            "estado": "coorte_fechada", "inseridos": 0,
            "candidatos": total, "faltam": 0,
        }
    linhas = _consulta_dicionarios(
        conexao,
        """
        SELECT b.id,b.criado_em,b.odd_total,b.bilhete_json
        FROM bilhetes_pre_live b
        WHERE b.versao=?
          AND datetime(b.criado_em)>=datetime(?)
          AND NOT EXISTS (
              SELECT 1 FROM coorte_pre_live_preciso c
              WHERE c.definicao_sha256=? AND c.bilhete_id=b.id
          )
        ORDER BY datetime(b.criado_em),b.id
        """,
        (VERSAO_ALVO, documento["registrado_em"], sha),
    )
    inseridos = invalidos_json = 0
    instante = agora or datetime.now(timezone.utc)
    if isinstance(instante, datetime):
        instante = instante.replace(microsecond=0).isoformat()
    with conexao:
        for linha in linhas:
            if total >= TAMANHO_COORTE:
                break
            try:
                bilhete = json.loads(linha.get("bilhete_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                invalidos_json += 1
                continue
            aprovado, _ = avaliar_criterios_bilhete_pre_live_preciso(
                bilhete
            )
            if not aprovado:
                continue
            odd = _numero(linha.get("odd_total"))
            if odd is None or odd <= 1.0:
                continue
            cursor = conexao.execute(
                """
                INSERT OR IGNORE INTO coorte_pre_live_preciso (
                    definicao_sha256,bilhete_id,ordem,incluido_em,
                    odd_total,bilhete_json
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    sha, int(linha["id"]), total + 1, str(instante),
                    odd,
                    json.dumps(
                        bilhete, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
            if cursor.rowcount:
                inseridos += 1
                total += 1
    return {
        "estado": "coorte_fechada" if total >= TAMANHO_COORTE else "coletando",
        "inseridos": inseridos,
        "candidatos": total,
        "faltam": max(TAMANHO_COORTE - total, 0),
        "linhas_json_invalidas": invalidos_json,
        "definicao_sha256": sha,
    }


def _carregar_ancora(conexao):
    tabela = conexao.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='metadados_pre_live'
        """
    ).fetchone()
    if tabela is None:
        return None
    linha = conexao.execute(
        "SELECT valor FROM metadados_pre_live WHERE chave=?",
        (CHAVE_DEFINICAO,),
    ).fetchone()
    if linha is None:
        return None
    documento = json.loads(linha[0])
    esperada = definicao()
    divergencias = [
        campo for campo, valor in esperada.items()
        if documento.get(campo) != valor
    ]
    if divergencias:
        raise RuntimeError(
            "Ancora do filtro pre-live preciso inconsistente: "
            + ",".join(divergencias)
        )
    return documento


def _probabilidade_sem_vig_bilhete(bilhete):
    probabilidades = []
    for perna in (bilhete or {}).get("pernas") or []:
        probabilidade = _numero(perna.get("probabilidade_mercado_sem_margem"))
        if probabilidade is None or not 0.0 < probabilidade < 1.0:
            return None
        probabilidades.append(probabilidade)
    if not probabilidades:
        return None
    return math.prod(probabilidades)


def _intervalo_95(valores):
    if len(valores) < 2:
        return None
    media = statistics.fmean(valores)
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    return [round(media - 1.96 * erro, 4), round(media + 1.96 * erro, 4)]


def _metricas(itens):
    validos = [
        item for item in itens
        if item.get("resultado") in RESULTADOS_VALIDOS
        and item.get("retorno_unidades") is not None
    ]
    retornos = [float(item["retorno_unidades"]) for item in validos]
    referencias_sem_vig = [
        item for item in validos
        if item.get("probabilidade_mercado_sem_vig") is not None
    ]
    residuos_sem_vig = [
        (1.0 if item["resultado"] == "green" else 0.0)
        - float(item["probabilidade_mercado_sem_vig"])
        for item in referencias_sem_vig
    ]
    referencias_equilibrio = [
        item for item in validos
        if item.get("probabilidade_equilibrio_odd") is not None
    ]
    residuos_equilibrio = [
        (1.0 if item["resultado"] == "green" else 0.0)
        - float(item["probabilidade_equilibrio_odd"])
        for item in referencias_equilibrio
    ]
    lucro = sum(retornos)
    return {
        "candidatos": len(itens),
        "publicados": sum(bool(item.get("publicado")) for item in itens),
        "validos": len(validos),
        "greens": sum(item["resultado"] == "green" for item in validos),
        "reds": sum(item["resultado"] == "red" for item in validos),
        "pendentes": sum(item.get("resultado") is None for item in itens),
        "invalidos": len(itens) - len(validos) - sum(
            item.get("resultado") is None for item in itens
        ),
        "lucro_unidades": round(lucro, 4),
        "roi": round(lucro / len(validos), 4) if validos else None,
        "intervalo_roi_95": _intervalo_95(retornos),
        "acerto": (
            round(sum(item["resultado"] == "green" for item in validos)
                  / len(validos), 4)
            if validos else None
        ),
        "referencia_sem_vig": {
            "cobertura": len(referencias_sem_vig),
            "taxa_cobertura": (
                round(len(referencias_sem_vig) / len(validos), 4)
                if validos else None
            ),
            "desvio_observado_menos_mercado": (
                round(statistics.fmean(residuos_sem_vig), 4)
                if residuos_sem_vig else None
            ),
            "intervalo_desvio_95": _intervalo_95(residuos_sem_vig),
        },
        "equilibrio_odd": {
            "cobertura": len(referencias_equilibrio),
            "taxa_cobertura": (
                round(len(referencias_equilibrio) / len(validos), 4)
                if validos else None
            ),
            "probabilidade_media": (
                round(statistics.fmean([
                    float(item["probabilidade_equilibrio_odd"])
                    for item in referencias_equilibrio
                ]), 4)
                if referencias_equilibrio else None
            ),
            "desvio_observado_menos_equilibrio": (
                round(statistics.fmean(residuos_equilibrio), 4)
                if residuos_equilibrio else None
            ),
            "intervalo_desvio_95": _intervalo_95(residuos_equilibrio),
        },
    }


def _converter_linha(linha):
    try:
        bilhete = json.loads(linha.get("bilhete_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    odd = _numero(linha.get("odd_total"))
    return {
        "id": int(linha["id"]),
        "criado_em": linha.get("criado_em"),
        "resultado": linha.get("resultado"),
        "retorno_unidades": linha.get("retorno_unidades"),
        "odd_total": odd,
        "probabilidade_equilibrio_odd": (
            1.0 / odd if odd is not None and odd > 1.0 else None
        ),
        "probabilidade_mercado_sem_vig": (
            _probabilidade_sem_vig_bilhete(bilhete)
        ),
        "publicado": bool(linha.get("publicado")),
        "bilhete": bilhete,
    }


def _carregar_coorte(conexao, documento):
    linhas = _consulta_dicionarios(
        conexao,
        """
        SELECT b.id,b.criado_em,b.resultado,b.retorno_unidades,
               c.ordem,c.odd_total,c.bilhete_json,
               CASE WHEN EXISTS (
                   SELECT 1 FROM entregas_pre_live e
                   WHERE e.bilhete_id=b.id AND e.mensagem_id IS NOT NULL
               ) OR EXISTS (
                   SELECT 1 FROM itens_listas_pre_live i
                   JOIN listas_pre_live l ON l.id=i.lista_id
                   WHERE i.bilhete_id=b.id AND l.mensagem_id IS NOT NULL
               ) THEN 1 ELSE 0 END AS publicado
        FROM coorte_pre_live_preciso c
        JOIN bilhetes_pre_live b ON b.id=c.bilhete_id
        WHERE c.definicao_sha256=?
        ORDER BY c.ordem
        """,
        (documento["definicao_sha256"],),
    )
    coorte = []
    invalidos_json = 0
    for ordem_esperada, linha in enumerate(linhas, 1):
        if int(linha.get("ordem") or 0) != ordem_esperada:
            raise RuntimeError("ordem_coorte_pre_live_preciso_inconsistente")
        item = _converter_linha(linha)
        if item is None:
            raise RuntimeError("json_coorte_pre_live_preciso_invalido")
        aprovado, _ = avaliar_criterios_bilhete_pre_live_preciso(
            item["bilhete"]
        )
        if not aprovado or item.get("odd_total") is None:
            raise RuntimeError("membro_coorte_pre_live_preciso_invalido")
        coorte.append(item)
    return coorte, invalidos_json


def _carregar_historico_legado(conexao, documento):
    linhas = _consulta_dicionarios(
        conexao,
        """
        SELECT b.id,b.criado_em,b.resultado,b.retorno_unidades,
               b.odd_total,b.bilhete_json,1 AS publicado
        FROM bilhetes_pre_live b
        WHERE b.versao=?
          AND datetime(b.criado_em)<datetime(?)
          AND b.resultado IN ('green','red')
          AND b.retorno_unidades IS NOT NULL
          AND (
              EXISTS (
                  SELECT 1 FROM entregas_pre_live e
                  WHERE e.bilhete_id=b.id AND e.mensagem_id IS NOT NULL
              ) OR EXISTS (
                  SELECT 1 FROM itens_listas_pre_live i
                  JOIN listas_pre_live l ON l.id=i.lista_id
                  WHERE i.bilhete_id=b.id AND l.mensagem_id IS NOT NULL
              )
          )
        ORDER BY datetime(b.criado_em),b.id
        """,
        (VERSAO_ALVO, documento["registrado_em"]),
    )
    itens = [item for item in map(_converter_linha, linhas) if item]
    ultimos_25 = _metricas(itens[-25:])
    ultimos_50 = _metricas(itens[-50:])
    intervalos = [
        ultimos_25.get("intervalo_roi_95"),
        ultimos_50.get("intervalo_roi_95"),
    ]
    drift_negativo = bool(all(
        isinstance(intervalo, (list, tuple))
        and len(intervalo) == 2
        and intervalo[1] is not None
        and float(intervalo[1]) < 0
        for intervalo in intervalos
    ))
    return {
        "uso": "diagnostico_nao_decisorio",
        "entra_na_coorte_nova": False,
        "publicados_resolvidos": len(itens),
        "ultimos_25": ultimos_25,
        "ultimos_50": ultimos_50,
        "drift_negativo_confirmado_duas_janelas": drift_negativo,
    }


def resumir_validacao_pre_live_preciso(conexao):
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "versao": VERSAO_VALIDACAO,
            "saudavel": True,
            "estado": "nao_registrada",
            "decisao": "aguardando_ancora",
            "apto_revisao": False,
            "promocao_automatica": False,
        }
    coorte, invalidos_json = _carregar_coorte(conexao, documento)
    total = _metricas(coorte)
    desenvolvimento = _metricas(coorte[:DESENVOLVIMENTO])
    holdout = _metricas(coorte[DESENVOLVIMENTO:TAMANHO_COORTE])
    checkpoint = _metricas(coorte[:CHECKPOINT_SEGURANCA])
    intervalo_checkpoint = checkpoint.get("intervalo_roi_95")
    alerta_desfavoravel = bool(
        checkpoint["validos"] >= CHECKPOINT_SEGURANCA
        and isinstance(intervalo_checkpoint, (list, tuple))
        and len(intervalo_checkpoint) == 2
        and intervalo_checkpoint[1] is not None
        and float(intervalo_checkpoint[1]) < 0
    )
    referencia = total["referencia_sem_vig"]
    referencia_holdout = holdout["referencia_sem_vig"]
    intervalo_referencia = referencia.get("intervalo_desvio_95")
    intervalo_referencia_holdout = referencia_holdout.get(
        "intervalo_desvio_95"
    )
    gate_preco_justo = bool(
        referencia.get("taxa_cobertura") is not None
        and referencia["taxa_cobertura"]
        >= COBERTURA_REFERENCIA_SEM_VIG_MINIMA
        and isinstance(intervalo_referencia, (list, tuple))
        and intervalo_referencia[0] > 0
        and referencia_holdout.get("taxa_cobertura") is not None
        and referencia_holdout["taxa_cobertura"]
        >= COBERTURA_REFERENCIA_SEM_VIG_MINIMA
        and isinstance(intervalo_referencia_holdout, (list, tuple))
        and intervalo_referencia_holdout[0] > 0
    )
    coorte_fechada = len(coorte) >= TAMANHO_COORTE
    resultados_completos = bool(
        coorte_fechada and total["pendentes"] == 0
    )
    intervalo_roi = total.get("intervalo_roi_95")
    if not coorte_fechada:
        decisao = "aguardando_amostra_futura"
    elif total["pendentes"]:
        decisao = "aguardando_resultados"
    elif (
        total["validos"] >= RESULTADOS_VALIDOS_MINIMOS
        and desenvolvimento["validos"]
        >= RESULTADOS_VALIDOS_DESENVOLVIMENTO_MINIMOS
        and holdout["validos"] >= RESULTADOS_VALIDOS_HOLDOUT_MINIMOS
        and total.get("roi") is not None
        and total["roi"] > 0
        and isinstance(intervalo_roi, (list, tuple))
        and intervalo_roi[0] > 0
        and desenvolvimento.get("roi") is not None
        and desenvolvimento["roi"] > 0
        and holdout.get("roi") is not None
        and holdout["roi"] > 0
        and gate_preco_justo
    ):
        decisao = "favoravel_para_revisao_manual"
    else:
        decisao = "inconclusiva_ou_desfavoravel"
    return {
        "versao": VERSAO_VALIDACAO,
        "versao_filtro": VERSAO_FILTRO,
        "versao_seletor": VERSAO_ALVO,
        "saudavel": invalidos_json == 0,
        **total,
        "estado": "encerrada" if resultados_completos else "coletando",
        "decisao": decisao,
        "apto_revisao": decisao == "favoravel_para_revisao_manual",
        "coorte_fechada": coorte_fechada,
        "resultados_completos": resultados_completos,
        "tamanho_coorte": TAMANHO_COORTE,
        "faltam": max(TAMANHO_COORTE - len(coorte), 0),
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "checkpoint_seguranca": checkpoint,
        "alerta_desfavoravel": alerta_desfavoravel,
        "rollback_recomendado": alerta_desfavoravel,
        "gate_preco_justo": {
            "cobertura_minima": COBERTURA_REFERENCIA_SEM_VIG_MINIMA,
            "total": referencia,
            "holdout": referencia_holdout,
            "satisfeito": gate_preco_justo,
        },
        "registrado_em": documento["registrado_em"],
        "definicao_sha256": documento["definicao_sha256"],
        "linhas_json_invalidas": invalidos_json,
        "populacao": documento["populacao"],
        "historico_legado": _carregar_historico_legado(
            conexao, documento
        ),
        "politica_seguranca": {
            "checkpoint_fixo": CHECKPOINT_SEGURANCA,
            "criterio_suspensao": documento["criterio_suspensao"],
            "efeito": "suspender_somente_entrega_pre_live_precisa",
            "coleta_sombra_continua": True,
            "outros_mercados_inalterados": True,
            "parada_obrigatoria_ao_fechar_coorte": True,
            "reativacao_automatica": False,
        },
        "promocao_automatica": False,
    }


def resumir_validacao_pre_live_preciso_arquivo(caminho):
    caminho = Path(caminho)
    if not caminho.is_file():
        return {
            "versao": VERSAO_VALIDACAO,
            "saudavel": False,
            "estado": "banco_ausente",
            "decisao": "indisponivel",
            "apto_revisao": False,
            "promocao_automatica": False,
        }
    conexao = None
    try:
        conexao = sqlite3.connect(
            caminho.resolve().as_uri() + "?mode=ro", uri=True, timeout=10
        )
        return resumir_validacao_pre_live_preciso(conexao)
    except (
        OSError, sqlite3.Error, json.JSONDecodeError, RuntimeError, ValueError
    ) as erro:
        return {
            "versao": VERSAO_VALIDACAO,
            "saudavel": False,
            "estado": "auditoria_falhou",
            "decisao": "indisponivel",
            "erro": type(erro).__name__,
            "apto_revisao": False,
            "promocao_automatica": False,
        }
    finally:
        if conexao is not None:
            conexao.close()
