"""Coorte prospectiva imutavel V2 do escanteio asiatico FT operacional.

O historico anterior serve apenas para formular a hipotese. A decisao usa os
primeiros 100 candidatos futuros da versao exata, congelados antes do resultado
e da entrega. Retorno de linhas asiaticas preserva green/half-green/void/
half-red/red; somente linhas .5 entram na comparacao binaria sem margem.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

from avaliacao_probabilidade_sem_vig import _carregar_odds_snapshots
from valor_mercado import anexar_par_odds_sincronizado, odd_oposta_sincronizada
from versoes_regras import VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86


VERSAO_VALIDACAO = "validacao-escanteios-ft-asiatico-prospectiva-v2"
CHAVE_DEFINICAO = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"
TABELA_COORTE = "coorte_escanteios_ft_asiatico_prospectiva"
MERCADO = "escanteios_ft_asiatico"
REGRA_VERSAO = VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86
TAMANHO_COORTE = 100
DESENVOLVIMENTO = 70
HOLDOUT = 30
MINIMO_VALIDOS_TOTAL = 90
MINIMO_VALIDOS_DESENVOLVIMENTO = 63
MINIMO_VALIDOS_HOLDOUT = 27
CHECKPOINT_SEGURANCA = 25
TAXA_RESULTADO_POSITIVO_ALVO = 0.75
COBERTURA_REFERENCIA_MINIMA = 0.90
MINIMO_BINARIOS_TOTAL = 45
MINIMO_BINARIOS_HOLDOUT = 12
RESULTADOS_VALIDOS = frozenset({
    "green", "half_green", "void", "half_red", "red",
})
RESULTADOS_POSITIVOS = frozenset({"green", "half_green"})
RESULTADOS_NEGATIVOS = frozenset({"half_red", "red"})


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _linhas(conexao, consulta, parametros=()):
    cursor = conexao.execute(consulta, parametros)
    colunas = [item[0] for item in cursor.description]
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def _canonico(valor):
    return json.dumps(
        valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _tipo_linha(linha):
    linha = _numero(linha)
    if linha is None:
        return "invalida"
    fracao = round(linha - math.floor(linha), 2)
    return {
        0.00: "inteira",
        0.25: "quarto_25",
        0.50: "meia",
        0.75: "quarto_75",
    }.get(fracao, "invalida")


def definicao():
    nucleo = {
        "versao": VERSAO_VALIDACAO,
        "mercado": MERCADO,
        "regra_versao": REGRA_VERSAO,
        "populacao": (
            "primeiros_100_candidatos_aprovados_da_versao_exata_uma_"
            "entrada_por_partida_congelados_apos_ancora_sem_consultar_"
            "resultado_ou_entrega"
        ),
        "relogios": {
            "auditoria": "utc_com_offset",
            "selecao": "relogio_local_naive_igual_ao_criado_em_dos_sinais",
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
        "resultados_positivos": sorted(RESULTADOS_POSITIVOS),
        "resultados_negativos": sorted(RESULTADOS_NEGATIVOS),
        "void_excluido_da_taxa_direcional": True,
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
                "Ancora de escanteios FT asiaticos inconsistente: "
                + ",".join(divergencias)
            )
        return existente
    instante = registrado_em or datetime.now(timezone.utc)
    if isinstance(instante, datetime):
        if instante.tzinfo is None:
            instante_local = instante.replace(microsecond=0)
            instante_utc = instante.astimezone().astimezone(
                timezone.utc
            ).replace(microsecond=0)
        else:
            instante_local = instante.astimezone().replace(
                tzinfo=None, microsecond=0
            )
            instante_utc = instante.astimezone(timezone.utc).replace(
                microsecond=0
            )
        registrado_utc = instante_utc.isoformat()
        relogio_sinais = instante_local.isoformat()
    else:
        registrado_utc = str(instante)
        relogio_sinais = str(instante)
    documento = {
        **esperada,
        "registrado_em": registrado_utc,
        "registrado_em_relogio_sinais": relogio_sinais,
    }
    with conexao:
        conexao.execute(
            "INSERT INTO metadados(chave,valor) VALUES (?,?)",
            (CHAVE_DEFINICAO, json.dumps(
                documento, ensure_ascii=False, sort_keys=True
            )),
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
        campo for campo in (
            "registrado_em", "registrado_em_relogio_sinais"
        )
        if not isinstance(documento.get(campo), str)
        or not documento.get(campo)
    )
    if divergencias:
        raise RuntimeError(
            "Ancora de escanteios FT asiaticos inconsistente: "
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
        "features": features,
        "status": linha.get("status"),
    }


def _candidato_elegivel(candidato):
    features = candidato.get("features") or {}
    return bool(
        candidato.get("mercado") == MERCADO
        and candidato.get("regra_versao") == REGRA_VERSAO
        and candidato.get("status") == "aprovado"
        and candidato.get("odd") is not None
        and float(candidato["odd"]) > 1.0
        and _tipo_linha(candidato.get("linha")) != "invalida"
        and features.get("tipo_mercado_odds") == "asiatico"
        and _numero(features.get("escanteios_atuais")) is not None
        and float(candidato["linha"])
        >= float(features["escanteios_atuais"])
    )


def _referencia_sem_vig(conexao, candidato):
    try:
        odds_por_snapshot = _carregar_odds_snapshots(
            conexao, [int(candidato["snapshot_id"])]
        )
        mercados = odds_por_snapshot.get(int(candidato["snapshot_id"]), [])
        if not mercados:
            return None
        consulta = {
            "mercado": MERCADO,
            "linha": candidato["linha"],
            "odd": candidato["odd"],
            "fonte_odds": (candidato.get("features") or {}).get("fonte_odds"),
            "bookmaker_odds": (
                candidato.get("features") or {}
            ).get("bookmaker_odds"),
            "features": dict(candidato.get("features") or {}),
        }
        if not anexar_par_odds_sincronizado(
            consulta, {"ao_vivo": mercados}
        ):
            return None
        odd_oposta = odd_oposta_sincronizada(consulta)
        if odd_oposta is None or float(odd_oposta) <= 1.0:
            return None
        soma = 1.0 / float(candidato["odd"]) + 1.0 / float(odd_oposta)
        return {
            "probabilidade_over": round(
                (1.0 / float(candidato["odd"])) / soma, 8
            ),
            "odd_under": round(float(odd_oposta), 8),
            "margem_bookmaker": round(soma - 1.0, 8),
            "fonte": consulta["features"].get(
                "fonte_referencia_sem_vig"
            ),
            "bookmaker": consulta["features"].get(
                "bookmaker_referencia_sem_vig"
            ),
        }
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        return None


def sincronizar_coorte(conexao, agora=None):
    """Congela candidatos em ordem causal sem ler resultado nem entrega."""
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "estado": "ancora_ausente", "inseridos": 0,
            "candidatos": 0, "faltam": TAMANHO_COORTE,
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
    if total >= TAMANHO_COORTE:
        return {
            "estado": "coorte_fechada", "inseridos": 0,
            "candidatos": total, "faltam": 0,
            "definicao_sha256": sha,
        }
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
    inseridos = invalidos = 0
    with conexao:
        for linha in candidatos:
            if total >= TAMANHO_COORTE:
                break
            sinal_id = int(linha["id"])
            partida_id = int(linha["partida_id"])
            if sinal_id in ids or partida_id in partidas:
                continue
            candidato = _candidato_da_linha(linha)
            if candidato is None or not _candidato_elegivel(candidato):
                invalidos += 1
                continue
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
    return {
        "estado": "coorte_fechada" if total >= TAMANHO_COORTE else "coletando",
        "inseridos": inseridos,
        "candidatos": total,
        "faltam": max(TAMANHO_COORTE - total, 0),
        "candidatos_invalidos": invalidos,
        "definicao_sha256": sha,
    }


def _intervalo_95(valores):
    if len(valores) < 2:
        return None
    media = statistics.fmean(valores)
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    return [round(media - 1.96 * erro, 6), round(media + 1.96 * erro, 6)]


def _metricas(itens):
    validos = [
        item for item in itens
        if item.get("resultado") in RESULTADOS_VALIDOS
        and _numero(item.get("retorno_unidades")) is not None
    ]
    retornos = [float(item["retorno_unidades"]) for item in validos]
    direcionais = [
        item for item in validos
        if item["resultado"] in RESULTADOS_POSITIVOS | RESULTADOS_NEGATIVOS
    ]
    positivos = sum(
        item["resultado"] in RESULTADOS_POSITIVOS for item in direcionais
    )
    referencias = [
        item for item in validos if isinstance(item.get("referencia"), dict)
    ]
    binarias = [
        item for item in validos
        if _tipo_linha(item.get("linha")) == "meia"
        and item.get("resultado") in {"green", "red"}
        and isinstance(item.get("referencia"), dict)
        and _numero(item["referencia"].get("probabilidade_over")) is not None
    ]
    residuos = [
        (1.0 if item["resultado"] == "green" else 0.0)
        - float(item["referencia"]["probabilidade_over"])
        for item in binarias
    ]
    pendentes = sum(item.get("resultado") is None for item in itens)
    return {
        "candidatos": len(itens),
        "publicados": sum(bool(item.get("publicado")) for item in itens),
        "validos": len(validos),
        "greens": sum(item.get("resultado") == "green" for item in validos),
        "half_greens": sum(
            item.get("resultado") == "half_green" for item in validos
        ),
        "voids": sum(item.get("resultado") == "void" for item in validos),
        "half_reds": sum(
            item.get("resultado") == "half_red" for item in validos
        ),
        "reds": sum(item.get("resultado") == "red" for item in validos),
        "resultados_direcionais": len(direcionais),
        "resultados_positivos": positivos,
        "taxa_resultado_positivo": (
            round(positivos / len(direcionais), 6) if direcionais else None
        ),
        "pendentes": pendentes,
        "invalidos": len(itens) - len(validos) - pendentes,
        "lucro_unidades": round(sum(retornos), 6),
        "roi": round(sum(retornos) / len(validos), 6) if validos else None,
        "intervalo_roi_95": _intervalo_95(retornos),
        "referencia_sem_vig": {
            "cobertura": len(referencias),
            "taxa_cobertura": (
                round(len(referencias) / len(validos), 6) if validos else None
            ),
            "binarios_meia": len(binarias),
            "desvio_observado_menos_mercado": (
                round(statistics.fmean(residuos), 6) if residuos else None
            ),
            "intervalo_desvio_95": _intervalo_95(residuos),
        },
    }


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
            raise RuntimeError("ordem_coorte_escanteios_ft_inconsistente")
        try:
            candidato = json.loads(linha.get("candidato_json") or "{}")
            referencia = json.loads(linha.get("referencia_json") or "null")
        except (TypeError, json.JSONDecodeError):
            raise RuntimeError("json_coorte_escanteios_ft_invalido")
        candidato_json = _canonico(candidato)
        referencia_json = _canonico(referencia)
        conteudo_sha256 = hashlib.sha256(
            (candidato_json + "\n" + referencia_json).encode("utf-8")
        ).hexdigest()
        partida_id = int(linha["partida_id"])
        if (
            not isinstance(candidato, dict)
            or not _candidato_elegivel(candidato)
            or int(candidato.get("id") or 0) != int(linha["sinal_id"])
            or int(candidato.get("partida_id") or 0) != partida_id
            or partida_id in partidas
            or not math.isclose(
                float(candidato["linha"]), float(linha["linha"]),
                abs_tol=1e-9,
            )
            or not math.isclose(
                float(candidato["odd"]), float(linha["odd"]),
                abs_tol=1e-9,
            )
            or conteudo_sha256 != linha.get("conteudo_sha256")
            or (referencia is not None and not isinstance(referencia, dict))
        ):
            raise RuntimeError("membro_coorte_escanteios_ft_invalido")
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
            "promocao_automatica": False,
        }
    coorte = _carregar_coorte(conexao, documento)
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
        decisao = "aguardando_amostra_futura"
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
        "historico_anterior_entra_na_decisao": False,
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
