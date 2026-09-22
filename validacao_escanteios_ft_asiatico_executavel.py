"""Coorte prospectiva V3 do escanteio asiatico FT realmente executavel.

A V2 continua imutavel como diagnostico historico. Esta definicao nova usa
somente candidatos cuja fotografia de entrada comprova a mesma oferta da
Bet365 via BetsAPI que o gateway oficial aceitaria. Precos agregados ou de
casa desconhecida sao auditados, mas nunca ocupam vaga nem provam edge.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from proveniencia_odds import (
    BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
    FONTE_COTACAO_EXECUTAVEL_OFICIAL,
    VERSAO_CUSTODIA_COTACAO_OFICIAL,
    validar_cotacao_executavel_oficial,
)
from validacao_escanteios_ft_asiatico_prospectiva import (
    CHECKPOINT_SEGURANCA,
    COBERTURA_REFERENCIA_MINIMA,
    DESENVOLVIMENTO,
    HOLDOUT,
    MERCADO,
    MINIMO_BINARIOS_HOLDOUT,
    MINIMO_BINARIOS_TOTAL,
    MINIMO_VALIDOS_DESENVOLVIMENTO,
    MINIMO_VALIDOS_HOLDOUT,
    MINIMO_VALIDOS_TOTAL,
    REGRA_VERSAO,
    TAMANHO_COORTE,
    TAXA_RESULTADO_POSITIVO_ALVO,
    _candidato_elegivel as _candidato_tecnicamente_elegivel,
    _canonico,
    _linhas,
    _metricas,
    _numero,
    _referencia_sem_vig,
)


VERSAO_VALIDACAO = "validacao-escanteios-ft-asiatico-executavel-v3"
CHAVE_DEFINICAO = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"
TABELA_COORTE = "coorte_escanteios_ft_asiatico_executavel"
TABELA_EXCLUSOES = "exclusoes_escanteios_ft_asiatico_executavel"


def definicao():
    nucleo = {
        "versao": VERSAO_VALIDACAO,
        "mercado": MERCADO,
        "regra_versao": REGRA_VERSAO,
        "populacao": (
            "primeiros_100_candidatos_aprovados_da_versao_exata_com_"
            "cotacao_congelada_betsapi_bet365_executavel_uma_entrada_"
            "por_partida_apos_ancora_sem_consultar_resultado_ou_entrega"
        ),
        "relogios": {
            "auditoria": "utc_com_offset",
            "selecao": "relogio_local_naive_igual_ao_criado_em_dos_sinais",
        },
        "custodia_cotacao": {
            "versao": VERSAO_CUSTODIA_COTACAO_OFICIAL,
            "fonte_exigida": FONTE_COTACAO_EXECUTAVEL_OFICIAL,
            "bookmaker_exigida": BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
            "prova_congelada_antes_do_resultado": True,
            "fontes_agregadas_ocupam_coorte": False,
            "exclusoes_auditadas": True,
        },
        "coorte_fixa": TAMANHO_COORTE,
        "desenvolvimento": DESENVOLVIMENTO,
        "holdout": HOLDOUT,
        "minimo_validos": {
            "total": MINIMO_VALIDOS_TOTAL,
            "desenvolvimento": MINIMO_VALIDOS_DESENVOLVIMENTO,
            "holdout": MINIMO_VALIDOS_HOLDOUT,
        },
        "checkpoint_fixo": CHECKPOINT_SEGURANCA,
        "taxa_resultado_positivo_alvo": TAXA_RESULTADO_POSITIVO_ALVO,
        "retorno_asiatico_liquidado": True,
        "referencia_sem_vig": {
            "cobertura_minima": COBERTURA_REFERENCIA_MINIMA,
            "somente_linhas_meia_para_residuo_binario": True,
            "minimo_binarios_total": MINIMO_BINARIOS_TOTAL,
            "minimo_binarios_holdout": MINIMO_BINARIOS_HOLDOUT,
        },
        "criterio_favoravel": (
            "taxa_positiva_total_minima_75_roi_total_ic95_inferior_positivo_"
            "roi_desenvolvimento_holdout_positivos_cobertura_preco_90pct_"
            "e_residuo_sem_vig_binario_total_holdout_ic95_positivo"
        ),
        "criterio_suspensao": (
            "limite_superior_ic95_roi_primeiros_25_abaixo_de_zero"
        ),
        "telegram_oficial": False,
        "promocao_automatica": False,
        "reativacao_automatica": False,
    }
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            _canonico(nucleo).encode("utf-8")
        ).hexdigest(),
    }


def _criar_estrutura(conexao):
    conexao.execute(
        "CREATE TABLE IF NOT EXISTS metadados "
        "(chave TEXT PRIMARY KEY, valor TEXT NOT NULL)"
    )
    conexao.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABELA_COORTE} (
            definicao_sha256 TEXT NOT NULL,
            sinal_id INTEGER NOT NULL,
            partida_id INTEGER NOT NULL,
            ordem INTEGER NOT NULL,
            incluido_em TEXT NOT NULL,
            linha REAL NOT NULL,
            odd REAL NOT NULL,
            referencia_json TEXT NOT NULL,
            candidato_json TEXT NOT NULL,
            conteudo_sha256 TEXT NOT NULL,
            PRIMARY KEY(definicao_sha256, sinal_id),
            UNIQUE(definicao_sha256, partida_id),
            UNIQUE(definicao_sha256, ordem)
        )
    """)
    conexao.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABELA_EXCLUSOES} (
            definicao_sha256 TEXT NOT NULL,
            sinal_id INTEGER NOT NULL,
            partida_id INTEGER NOT NULL,
            excluido_em TEXT NOT NULL,
            motivo TEXT NOT NULL,
            auditoria_json TEXT NOT NULL,
            conteudo_sha256 TEXT NOT NULL,
            PRIMARY KEY(definicao_sha256, sinal_id)
        )
    """)


def _instantes_ancora(registrado_em):
    instante = registrado_em or datetime.now(timezone.utc)
    if not isinstance(instante, datetime):
        return str(instante), str(instante)
    if instante.tzinfo is None:
        local = instante.replace(microsecond=0)
        utc = instante.astimezone().astimezone(timezone.utc).replace(
            microsecond=0
        )
    else:
        local = instante.astimezone().replace(tzinfo=None, microsecond=0)
        utc = instante.astimezone(timezone.utc).replace(microsecond=0)
    return utc.isoformat(), local.isoformat()


def registrar_ou_validar_definicao(conexao, registrado_em=None):
    _criar_estrutura(conexao)
    esperada = definicao()
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha[0])
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        divergencias.extend(
            campo for campo in (
                "registrado_em", "registrado_em_relogio_sinais"
            )
            if not isinstance(existente.get(campo), str)
            or not existente.get(campo)
        )
        if divergencias:
            raise RuntimeError(
                "Ancora executavel de escanteios FT inconsistente: "
                + ",".join(divergencias)
            )
        return existente
    registrado_utc, relogio_sinais = _instantes_ancora(registrado_em)
    documento = {
        **esperada,
        "registrado_em": registrado_utc,
        "registrado_em_relogio_sinais": relogio_sinais,
    }
    with conexao:
        conexao.execute(
            "INSERT INTO metadados(chave,valor) VALUES (?,?)",
            (
                CHAVE_DEFINICAO,
                json.dumps(documento, ensure_ascii=False, sort_keys=True),
            ),
        )
    return documento


def _carregar_ancora(conexao):
    tabela = conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadados'"
    ).fetchone()
    if tabela is None:
        return None
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is None:
        return None
    documento = json.loads(linha[0])
    esperada = definicao()
    divergencias = [
        campo for campo, valor in esperada.items()
        if documento.get(campo) != valor
    ]
    divergencias.extend(
        campo for campo in ("registrado_em", "registrado_em_relogio_sinais")
        if not isinstance(documento.get(campo), str)
        or not documento.get(campo)
    )
    if divergencias:
        raise RuntimeError(
            "Ancora executavel de escanteios FT inconsistente: "
            + ",".join(divergencias)
        )
    return documento


def _candidato_da_linha(linha):
    try:
        features = json.loads(linha.get("features_json") or "{}")
        motivos = json.loads(linha.get("motivos_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(features, dict) or not isinstance(motivos, list):
        return None
    return {
        "id": int(linha["id"]),
        "partida_id": int(linha["partida_id"]),
        "snapshot_id": int(linha["snapshot_id"]),
        "criado_em": linha.get("criado_em"),
        "mercado": linha.get("mercado"),
        "linha": _numero(linha.get("linha")),
        "odd": _numero(linha.get("odd")),
        "pontuacao_tecnica": _numero(linha.get("pontuacao_tecnica")),
        "probabilidade_calibrada": _numero(
            linha.get("probabilidade_calibrada")
        ),
        "regra_versao": linha.get("regra_versao"),
        "regra_fingerprint": linha.get("regra_fingerprint"),
        "motivos": motivos,
        "fonte_odds": features.get("fonte_odds"),
        "bookmaker_odds": features.get("bookmaker_odds"),
        "features": features,
        "status": linha.get("status"),
    }


def _auditar_candidato(candidato):
    if not isinstance(candidato, dict) or not (
        _candidato_tecnicamente_elegivel(candidato)
    ):
        return {
            "apto": False,
            "categoria": "elegibilidade_tecnica",
            "motivo": "candidato_tecnicamente_invalido",
        }
    custodia = validar_cotacao_executavel_oficial(candidato)
    return {
        **custodia,
        "categoria": (
            "cotacao_executavel" if custodia.get("apto")
            else "custodia_cotacao"
        ),
    }


def _registrar_exclusao(
    conexao, sha, candidato, auditoria, instante
):
    auditoria_json = _canonico(auditoria)
    conteudo_sha256 = hashlib.sha256(
        auditoria_json.encode("utf-8")
    ).hexdigest()
    cursor = conexao.execute(f"""
        INSERT OR IGNORE INTO {TABELA_EXCLUSOES}(
            definicao_sha256,sinal_id,partida_id,excluido_em,motivo,
            auditoria_json,conteudo_sha256
        ) VALUES (?,?,?,?,?,?,?)
    """, (
        sha, int(candidato["id"]), int(candidato["partida_id"]),
        str(instante), str(auditoria.get("motivo") or "motivo_ausente"),
        auditoria_json, conteudo_sha256,
    ))
    return bool(cursor.rowcount)


def sincronizar_coorte(conexao, agora=None):
    """Congela apenas candidatos executaveis, sem ler resultado/entrega."""
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "estado": "ancora_ausente", "inseridos": 0,
            "candidatos": 0, "faltam": TAMANHO_COORTE,
            "excluidos_custodia": 0,
        }
    _criar_estrutura(conexao)
    sha = documento["definicao_sha256"]
    existentes = _linhas(
        conexao,
        f"SELECT sinal_id,partida_id FROM {TABELA_COORTE} "
        "WHERE definicao_sha256=? ORDER BY ordem",
        (sha,),
    )
    total = len(existentes)
    ids = {int(item["sinal_id"]) for item in existentes}
    partidas = {int(item["partida_id"]) for item in existentes}
    candidatos = _linhas(conexao, """
        SELECT id,partida_id,snapshot_id,criado_em,mercado,linha,odd,
               pontuacao_tecnica,probabilidade_calibrada,regra_versao,
               regra_fingerprint,motivos_json,features_json,status
        FROM sinais
        WHERE datetime(criado_em)>=datetime(?)
          AND mercado=? AND regra_versao=? AND status='aprovado'
        ORDER BY datetime(criado_em),id
    """, (
        documento["registrado_em_relogio_sinais"], MERCADO, REGRA_VERSAO,
    ))
    instante = agora or datetime.now(timezone.utc)
    if isinstance(instante, datetime):
        instante = instante.replace(microsecond=0).isoformat()
    inseridos = invalidos = excluidos_novos = 0
    motivos_exclusao = Counter()
    with conexao:
        for linha in candidatos:
            if total >= TAMANHO_COORTE:
                break
            sinal_id = int(linha["id"])
            partida_id = int(linha["partida_id"])
            if sinal_id in ids or partida_id in partidas:
                continue
            candidato = _candidato_da_linha(linha)
            auditoria = _auditar_candidato(candidato)
            if auditoria.get("categoria") == "elegibilidade_tecnica":
                invalidos += 1
                continue
            if auditoria.get("apto") is not True:
                motivo = str(auditoria.get("motivo") or "motivo_ausente")
                motivos_exclusao[motivo] += 1
                if _registrar_exclusao(
                    conexao, sha, candidato, auditoria, instante
                ):
                    excluidos_novos += 1
                continue
            candidato["custodia_cotacao_oficial"] = auditoria
            referencia = _referencia_sem_vig(conexao, candidato)
            candidato_json = _canonico(candidato)
            referencia_json = _canonico(referencia)
            conteudo_sha256 = hashlib.sha256(
                (candidato_json + "\n" + referencia_json).encode("utf-8")
            ).hexdigest()
            cursor = conexao.execute(f"""
                INSERT OR IGNORE INTO {TABELA_COORTE}(
                    definicao_sha256,sinal_id,partida_id,ordem,incluido_em,
                    linha,odd,referencia_json,candidato_json,conteudo_sha256
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                sha, sinal_id, partida_id, total + 1, str(instante),
                float(candidato["linha"]), float(candidato["odd"]),
                referencia_json, candidato_json, conteudo_sha256,
            ))
            if cursor.rowcount:
                ids.add(sinal_id)
                partidas.add(partida_id)
                inseridos += 1
                total += 1
    exclusoes_total = conexao.execute(
        f"SELECT COUNT(*) FROM {TABELA_EXCLUSOES} "
        "WHERE definicao_sha256=?", (sha,)
    ).fetchone()[0]
    return {
        "estado": "coorte_fechada" if total >= TAMANHO_COORTE else "coletando",
        "inseridos": inseridos,
        "candidatos": total,
        "faltam": max(TAMANHO_COORTE - total, 0),
        "candidatos_invalidos": invalidos,
        "excluidos_custodia_novos": excluidos_novos,
        "excluidos_custodia": int(exclusoes_total or 0),
        "motivos_exclusao_ciclo": dict(sorted(motivos_exclusao.items())),
        "fonte_exigida": FONTE_COTACAO_EXECUTAVEL_OFICIAL,
        "bookmaker_exigida": BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
        "definicao_sha256": sha,
    }


def _carregar_exclusoes(conexao, documento):
    tabela = conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (TABELA_EXCLUSOES,),
    ).fetchone()
    if tabela is None:
        return {"total": 0, "por_motivo": {}}
    linhas = _linhas(conexao, f"""
        SELECT motivo,auditoria_json,conteudo_sha256
        FROM {TABELA_EXCLUSOES}
        WHERE definicao_sha256=? ORDER BY sinal_id
    """, (documento["definicao_sha256"],))
    motivos = Counter()
    for linha in linhas:
        try:
            auditoria = json.loads(linha.get("auditoria_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            raise RuntimeError("exclusao_custodia_json_invalida")
        auditoria_json = _canonico(auditoria)
        if (
            not isinstance(auditoria, dict)
            or auditoria.get("apto") is not False
            or auditoria.get("categoria") != "custodia_cotacao"
            or str(auditoria.get("motivo") or "") != linha.get("motivo")
            or hashlib.sha256(auditoria_json.encode("utf-8")).hexdigest()
            != linha.get("conteudo_sha256")
        ):
            raise RuntimeError("exclusao_custodia_adulterada")
        motivos[str(linha["motivo"])] += 1
    return {"total": len(linhas), "por_motivo": dict(sorted(motivos.items()))}


def _carregar_coorte(conexao, documento):
    tabela = conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (TABELA_COORTE,),
    ).fetchone()
    if tabela is None:
        return []
    linhas = _linhas(conexao, f"""
        SELECT c.sinal_id,c.partida_id,c.ordem,c.linha,c.odd,
               c.referencia_json,c.candidato_json,c.conteudo_sha256,
               r.resultado,r.retorno_unidades,
               CASE WHEN EXISTS(
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=c.sinal_id
                     AND e.status IN ('entregue','controle_entregue')
                     AND e.canal NOT LIKE 'gateway:%'
                     AND e.canal NOT LIKE '%:resultado%'
                     AND e.canal NOT LIKE '%:green_antecipado%'
               ) THEN 1 ELSE 0 END AS publicado
        FROM {TABELA_COORTE} c
        LEFT JOIN resultados_sinais r ON r.sinal_id=c.sinal_id
        WHERE c.definicao_sha256=? ORDER BY c.ordem
    """, (documento["definicao_sha256"],))
    itens = []
    partidas = set()
    for ordem, linha in enumerate(linhas, 1):
        if int(linha.get("ordem") or 0) != ordem:
            raise RuntimeError("ordem_coorte_escanteios_executavel_inconsistente")
        try:
            candidato = json.loads(linha.get("candidato_json") or "{}")
            referencia = json.loads(linha.get("referencia_json") or "null")
        except (TypeError, json.JSONDecodeError):
            raise RuntimeError("json_coorte_escanteios_executavel_invalido")
        auditoria = _auditar_candidato(candidato)
        candidato_json = _canonico(candidato)
        referencia_json = _canonico(referencia)
        conteudo_sha256 = hashlib.sha256(
            (candidato_json + "\n" + referencia_json).encode("utf-8")
        ).hexdigest()
        partida_id = int(linha["partida_id"])
        if (
            not isinstance(candidato, dict)
            or auditoria.get("apto") is not True
            or _canonico(candidato.get("custodia_cotacao_oficial"))
            != _canonico(auditoria)
            or int(candidato.get("id") or 0) != int(linha["sinal_id"])
            or int(candidato.get("partida_id") or 0) != partida_id
            or partida_id in partidas
            or not math.isclose(
                float(candidato["linha"]), float(linha["linha"]), abs_tol=1e-9
            )
            or not math.isclose(
                float(candidato["odd"]), float(linha["odd"]), abs_tol=1e-9
            )
            or conteudo_sha256 != linha.get("conteudo_sha256")
            or (referencia is not None and not isinstance(referencia, dict))
        ):
            raise RuntimeError("membro_coorte_escanteios_executavel_invalido")
        partidas.add(partida_id)
        itens.append({
            "sinal_id": int(linha["sinal_id"]),
            "partida_id": partida_id,
            "linha": float(linha["linha"]),
            "odd": float(linha["odd"]),
            "referencia": referencia,
            "resultado": linha.get("resultado"),
            "retorno_unidades": _numero(linha.get("retorno_unidades")),
            "publicado": bool(linha.get("publicado")),
            "candidato": candidato,
        })
    return itens


def resumir_validacao(conexao):
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "versao": VERSAO_VALIDACAO,
            "mercado": MERCADO,
            "regra_versao": REGRA_VERSAO,
            "saudavel": True,
            "estado": "nao_registrada",
            "decisao": "aguardando_ancora",
            "apto_revisao": False,
            "coorte_execucao_alinhada": True,
            "promocao_automatica": False,
        }
    coorte = _carregar_coorte(conexao, documento)
    exclusoes = _carregar_exclusoes(conexao, documento)
    total = _metricas(coorte)
    desenvolvimento = _metricas(coorte[:DESENVOLVIMENTO])
    holdout = _metricas(coorte[DESENVOLVIMENTO:TAMANHO_COORTE])
    checkpoint = _metricas(coorte[:CHECKPOINT_SEGURANCA])
    intervalo_checkpoint = checkpoint.get("intervalo_roi_95")
    alerta_desfavoravel = bool(
        checkpoint["validos"] >= CHECKPOINT_SEGURANCA
        and isinstance(intervalo_checkpoint, (list, tuple))
        and intervalo_checkpoint[1] < 0
    )
    referencia = total["referencia_sem_vig"]
    referencia_holdout = holdout["referencia_sem_vig"]
    intervalo_ref = referencia.get("intervalo_desvio_95")
    intervalo_ref_holdout = referencia_holdout.get("intervalo_desvio_95")
    gate_preco = bool(
        (referencia.get("taxa_cobertura") or 0)
        >= COBERTURA_REFERENCIA_MINIMA
        and referencia.get("binarios_meia", 0) >= MINIMO_BINARIOS_TOTAL
        and isinstance(intervalo_ref, (list, tuple))
        and intervalo_ref[0] > 0
        and (referencia_holdout.get("taxa_cobertura") or 0)
        >= COBERTURA_REFERENCIA_MINIMA
        and referencia_holdout.get("binarios_meia", 0)
        >= MINIMO_BINARIOS_HOLDOUT
        and isinstance(intervalo_ref_holdout, (list, tuple))
        and intervalo_ref_holdout[0] > 0
    )
    coorte_fechada = len(coorte) >= TAMANHO_COORTE
    resultados_completos = bool(coorte_fechada and total["pendentes"] == 0)
    intervalo_roi = total.get("intervalo_roi_95")
    taxa = total.get("taxa_resultado_positivo")
    if not coorte_fechada:
        decisao = "aguardando_amostra_executavel_futura"
    elif total["pendentes"]:
        decisao = "aguardando_resultados"
    elif (
        total["validos"] >= MINIMO_VALIDOS_TOTAL
        and desenvolvimento["validos"] >= MINIMO_VALIDOS_DESENVOLVIMENTO
        and holdout["validos"] >= MINIMO_VALIDOS_HOLDOUT
        and taxa is not None and taxa >= TAXA_RESULTADO_POSITIVO_ALVO
        and total.get("roi") is not None and total["roi"] > 0
        and isinstance(intervalo_roi, (list, tuple))
        and intervalo_roi[0] > 0
        and desenvolvimento.get("roi") is not None
        and desenvolvimento["roi"] > 0
        and holdout.get("roi") is not None and holdout["roi"] > 0
        and gate_preco
    ):
        decisao = "favoravel_para_revisao_manual"
    else:
        decisao = "inconclusiva_ou_desfavoravel"
    return {
        "versao": VERSAO_VALIDACAO,
        "mercado": MERCADO,
        "regra_versao": REGRA_VERSAO,
        "saudavel": True,
        **total,
        "estado": "encerrada" if resultados_completos else "coletando",
        "decisao": decisao,
        "apto_revisao": decisao == "favoravel_para_revisao_manual",
        "coorte_fechada": coorte_fechada,
        "resultados_completos": resultados_completos,
        "tamanho_coorte": TAMANHO_COORTE,
        "faltam": max(TAMANHO_COORTE - len(coorte), 0),
        "taxa_resultado_positivo_alvo": TAXA_RESULTADO_POSITIVO_ALVO,
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "checkpoint_seguranca": checkpoint,
        "alerta_desfavoravel": alerta_desfavoravel,
        "gate_preco_sem_vig": {
            "total": referencia,
            "holdout": referencia_holdout,
            "satisfeito": gate_preco,
        },
        "custodia_cotacao": {
            "versao": VERSAO_CUSTODIA_COTACAO_OFICIAL,
            "fonte_exigida": FONTE_COTACAO_EXECUTAVEL_OFICIAL,
            "bookmaker_exigida": BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
            "membros_executaveis": len(coorte),
            "violacoes_na_coorte": 0,
            "exclusoes": exclusoes,
        },
        "coorte_execucao_alinhada": True,
        "registrado_em": documento["registrado_em"],
        "registrado_em_relogio_sinais": (
            documento["registrado_em_relogio_sinais"]
        ),
        "definicao_sha256": documento["definicao_sha256"],
        "populacao": documento["populacao"],
        "politica_seguranca": {
            "checkpoint_fixo": CHECKPOINT_SEGURANCA,
            "efeito": "suspender_somente_escanteios_ft_asiatico",
            "coleta_continua": True,
            "outros_mercados_inalterados": True,
            "parada_obrigatoria_ao_fechar_coorte": True,
            "reativacao_automatica": False,
        },
        "coorte_legada_v2_entra_na_decisao": False,
        "telegram_oficial": False,
        "promocao_automatica": False,
    }


def resumir_validacao_arquivo(caminho):
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
        conexao.row_factory = sqlite3.Row
        return resumir_validacao(conexao)
    except (
        OSError, sqlite3.Error, json.JSONDecodeError, ValueError, RuntimeError
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
