"""Coorte prospectiva imutável do filtro FT antecipado preciso V2."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

from filtro_gol_ft_antecipado_preciso import (
    CHUTES_RECENTES_MINIMOS,
    EVIDENCIAS_LIVE_MINIMAS,
    GOLS_HISTORICOS_FAIXA_MINIMOS,
    IDADE_ODD_MAXIMA_SEGUNDOS,
    METODO,
    MINUTO_MAXIMO,
    MINUTO_MINIMO,
    ODD_MAXIMA_EXCLUSIVA,
    ODD_MINIMA,
    QUALIDADE_MINIMA,
    ROLLBACK,
    VERSAO as VERSAO_FILTRO,
    avaliar_filtro_gol_ft_antecipado,
)


VERSAO_VALIDACAO = "validacao-gol-ft-antecipado-preciso-v2"
CHAVE_DEFINICAO = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"
TABELA_COORTE = "coorte_gol_ft_antecipado_preciso"
TAMANHO_COORTE = 60
DESENVOLVIMENTO = 42
HOLDOUT = 18
MINIMO_VALIDOS_TOTAL = 55
MINIMO_VALIDOS_DESENVOLVIMENTO = 38
MINIMO_VALIDOS_HOLDOUT = 16
CHECKPOINT_SEGURANCA = 25
TAXA_GREEN_ALVO = 0.75
COBERTURA_REFERENCIA_MINIMA = 1.0
RESULTADOS_VALIDOS = {"green", "red"}


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


def definicao():
    nucleo = {
        "versao": VERSAO_VALIDACAO,
        "filtro": VERSAO_FILTRO,
        "metodo_origem": METODO,
        "populacao": (
            "primeiros_60_sinais_elegiveis_por_partida_congelados_apos_"
            "ancora_sem_consultar_resultado_ou_entrega"
        ),
        "relogios": {
            "auditoria": "utc_com_offset",
            "selecao": "relogio_local_naive_igual_ao_criado_em_dos_sinais",
        },
        "criterios": {
            "minuto": [MINUTO_MINIMO, MINUTO_MAXIMO],
            "odd": [ODD_MINIMA, ODD_MAXIMA_EXCLUSIVA],
            "odd_maxima_exclusiva": True,
            "qualidade_minima": QUALIDADE_MINIMA,
            "idade_odd_maxima_segundos": IDADE_ODD_MAXIMA_SEGUNDOS,
            "odds_cache": False,
            "evidencias_live_minimas": EVIDENCIAS_LIVE_MINIMAS,
            "gols_historicos_faixa_minimos": (
                GOLS_HISTORICOS_FAIXA_MINIMOS
            ),
            "chutes_5min_minimos": CHUTES_RECENTES_MINIMOS,
            "contadores_consistentes": True,
        },
        "coorte_fixa": TAMANHO_COORTE,
        "desenvolvimento": DESENVOLVIMENTO,
        "holdout": HOLDOUT,
        "minimo_validos_total": MINIMO_VALIDOS_TOTAL,
        "minimo_validos_desenvolvimento": (
            MINIMO_VALIDOS_DESENVOLVIMENTO
        ),
        "minimo_validos_holdout": MINIMO_VALIDOS_HOLDOUT,
        "checkpoint_fixo": CHECKPOINT_SEGURANCA,
        "taxa_green_alvo": TAXA_GREEN_ALVO,
        "referencia_preco": "probabilidade_conservadora_1_sobre_odd",
        "criterio_favoravel": (
            "taxa_green_total_minima_75_roi_total_ic95_inferior_positivo_"
            "roi_dev_holdout_positivos_e_residuo_1_sobre_odd_total_"
            "holdout_ic95_inferior_positivo"
        ),
        "criterio_suspensao": (
            "limite_superior_ic95_roi_primeiros_25_abaixo_de_zero"
        ),
        "telegram_oficial": False,
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
            odd REAL NOT NULL,
            candidato_json TEXT NOT NULL,
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
                "Ancora do filtro FT antecipado preciso inconsistente: "
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
        campo for campo in (
            "registrado_em", "registrado_em_relogio_sinais"
        )
        if not isinstance(documento.get(campo), str)
        or not documento.get(campo)
    )
    if divergencias:
        raise RuntimeError(
            "Ancora do filtro FT antecipado preciso inconsistente: "
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
        "linha": linha.get("linha"),
        "odd": linha.get("odd"),
        "pontuacao_tecnica": linha.get("pontuacao_tecnica"),
        "regra_versao": linha.get("regra_versao"),
        "regra_fingerprint": linha.get("regra_fingerprint"),
        "motivos": motivos,
        "features": features,
        "status": linha.get("status"),
    }


def _decisoes_pos_ancora(conexao, documento):
    """Lê decisões causais do gerador sem resultados ou entregas."""
    return _linhas(
        conexao,
        """
        SELECT id,partida_id,snapshot_id,criado_em,mercado,linha,odd,
               pontuacao_tecnica,regra_versao,regra_fingerprint,
               motivos_json,features_json,status
        FROM sinais
        WHERE datetime(criado_em)>=datetime(?)
          AND mercado='gol_ft' AND status='simulacao'
          AND json_extract(features_json,'$.exploracao_sombra.versao')=?
        ORDER BY datetime(criado_em),id
        """,
        (documento["registrado_em_relogio_sinais"], METODO),
    )


def _funil_candidatos_pos_ancora(conexao, documento):
    """Explica a coleta prospectiva sem mudar seleção nem ver desfechos."""
    linhas = _decisoes_pos_ancora(conexao, documento)
    motivos_decisoes = {}
    estado_partidas = {}
    elegiveis = rejeitadas = invalidas = 0
    ultima_decisao_em = None
    for linha in linhas:
        partida_id = int(linha["partida_id"])
        estado = estado_partidas.setdefault(partida_id, {
            "elegivel": False,
            "ultimo_motivo_rejeicao": None,
        })
        ultima_decisao_em = linha.get("criado_em") or ultima_decisao_em
        candidato = _candidato_da_linha(linha)
        if candidato is None:
            invalidas += 1
            estado["ultimo_motivo_rejeicao"] = "candidato_json_invalido"
            motivos_decisoes["candidato_json_invalido"] = (
                motivos_decisoes.get("candidato_json_invalido", 0) + 1
            )
            continue
        decisao = avaliar_filtro_gol_ft_antecipado(
            candidato, {ROLLBACK: "1"}
        )
        if decisao.get("aprovada") is True:
            elegiveis += 1
            estado["elegivel"] = True
            estado["ultimo_motivo_rejeicao"] = None
            continue
        rejeitadas += 1
        motivo = str(decisao.get("motivo") or "motivo_ausente")
        motivos_decisoes[motivo] = motivos_decisoes.get(motivo, 0) + 1
        estado["ultimo_motivo_rejeicao"] = motivo

    motivos_partidas = {}
    partidas_elegiveis = 0
    for estado in estado_partidas.values():
        if estado["elegivel"]:
            partidas_elegiveis += 1
            continue
        motivo = estado["ultimo_motivo_rejeicao"] or "motivo_ausente"
        motivos_partidas[motivo] = motivos_partidas.get(motivo, 0) + 1
    gargalo_atual = None
    if motivos_partidas:
        gargalo_atual = sorted(
            motivos_partidas.items(), key=lambda item: (-item[1], item[0])
        )[0][0]
    if not linhas:
        estado_funil = "sem_sinais_gerador"
    elif not partidas_elegiveis:
        estado_funil = "sem_elegiveis"
    else:
        estado_funil = "com_elegiveis"
    return {
        "versao": "funil-gol-ft-antecipado-preciso-v1",
        "estado": estado_funil,
        "decisoes_gerador": len(linhas),
        "decisoes_validas": len(linhas) - invalidas,
        "decisoes_elegiveis": elegiveis,
        "decisoes_rejeitadas": rejeitadas,
        "decisoes_json_invalidas": invalidas,
        "partidas_com_decisao": len(estado_partidas),
        "partidas_com_alguma_decisao_elegivel": partidas_elegiveis,
        "partidas_sem_decisao_elegivel": (
            len(estado_partidas) - partidas_elegiveis
        ),
        "motivos_rejeicao_decisoes": dict(sorted(motivos_decisoes.items())),
        "motivos_ultima_decisao_partidas_sem_elegivel": dict(
            sorted(motivos_partidas.items())
        ),
        "gargalo_atual": gargalo_atual,
        "ultima_decisao_em": ultima_decisao_em,
        "criterio_independencia": (
            "uma_partida_entra_na_coorte_no_primeiro_sinal_elegivel"
        ),
        "consulta_resultados": False,
        "consulta_entregas": False,
        "altera_sinais": False,
        "altera_telegram": False,
        "promocao_automatica": False,
    }


def sincronizar_coorte(conexao, agora=None):
    """Congela elegíveis em ordem causal sem consultar resultado ou entrega."""
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
    candidatos = _decisoes_pos_ancora(conexao, documento)
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
            if candidato is None:
                invalidos += 1
                continue
            decisao = avaliar_filtro_gol_ft_antecipado(
                candidato, {ROLLBACK: "1"}
            )
            if not decisao.get("aprovada"):
                continue
            odd = _numero(candidato.get("odd"))
            if odd is None or odd <= 1.0:
                continue
            congelado = json.dumps(
                candidato, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            )
            cursor = conexao.execute(f"""
                INSERT OR IGNORE INTO {TABELA_COORTE}(
                    definicao_sha256,sinal_id,partida_id,ordem,
                    incluido_em,odd,candidato_json
                ) VALUES (?,?,?,?,?,?,?)
            """, (
                sha, sinal_id, partida_id, total + 1,
                str(instante), odd, congelado,
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
        "linhas_json_invalidas": invalidos,
        "definicao_sha256": sha,
    }


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
        and item.get("odd") is not None
    ]
    retornos = [float(item["retorno_unidades"]) for item in validos]
    residuos = [
        (1.0 if item["resultado"] == "green" else 0.0)
        - 1.0 / float(item["odd"])
        for item in validos
    ]
    greens = sum(item["resultado"] == "green" for item in validos)
    lucro = sum(retornos)
    pendentes = sum(item.get("resultado") is None for item in itens)
    return {
        "candidatos": len(itens),
        "publicados": sum(bool(item.get("publicado")) for item in itens),
        "validos": len(validos),
        "greens": greens,
        "reds": len(validos) - greens,
        "pendentes": pendentes,
        "invalidos": len(itens) - len(validos) - pendentes,
        "taxa_green": round(greens / len(validos), 4) if validos else None,
        "lucro_unidades": round(lucro, 4),
        "roi": round(lucro / len(validos), 4) if validos else None,
        "intervalo_roi_95": _intervalo_95(retornos),
        "referencia_1_sobre_odd": {
            "cobertura": len(validos),
            "taxa_cobertura": 1.0 if validos else None,
            "probabilidade_media": (
                round(statistics.fmean(
                    1.0 / float(item["odd"]) for item in validos
                ), 4) if validos else None
            ),
            "desvio_observado_menos_mercado": (
                round(statistics.fmean(residuos), 4) if residuos else None
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
        SELECT c.sinal_id,c.partida_id,c.ordem,c.odd,c.candidato_json,
               r.resultado,r.retorno_unidades,
               CASE WHEN EXISTS(
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=c.sinal_id AND e.status='entregue'
                     AND e.canal NOT LIKE '%:resultado'
               ) THEN 1 ELSE 0 END AS publicado
        FROM {TABELA_COORTE} c
        LEFT JOIN resultados_sinais r ON r.sinal_id=c.sinal_id
        WHERE c.definicao_sha256=? ORDER BY c.ordem
    """, (documento["definicao_sha256"],))
    itens = []
    partidas = set()
    for ordem, linha in enumerate(linhas, 1):
        if int(linha.get("ordem") or 0) != ordem:
            raise RuntimeError("ordem_coorte_gol_ft_preciso_inconsistente")
        try:
            candidato = json.loads(linha.get("candidato_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            raise RuntimeError("json_coorte_gol_ft_preciso_invalido")
        decisao = avaliar_filtro_gol_ft_antecipado(
            candidato, {ROLLBACK: "1"}
        )
        partida_id = int(linha["partida_id"])
        if (
            not isinstance(candidato, dict)
            or int(candidato.get("id") or 0) != int(linha["sinal_id"])
            or int(candidato.get("partida_id") or 0) != partida_id
            or partida_id in partidas
            or decisao.get("aprovada") is not True
            or not math.isclose(
                float(candidato.get("odd")), float(linha["odd"]),
                abs_tol=1e-9,
            )
        ):
            raise RuntimeError("membro_coorte_gol_ft_preciso_invalido")
        partidas.add(partida_id)
        itens.append({
            "sinal_id": int(linha["sinal_id"]),
            "partida_id": partida_id,
            "odd": float(linha["odd"]),
            "resultado": linha.get("resultado"),
            "retorno_unidades": linha.get("retorno_unidades"),
            "publicado": bool(linha.get("publicado")),
            "candidato": candidato,
        })
    return itens


def _historico_gerador(conexao, documento):
    linhas = _linhas(conexao, """
        WITH base AS (
          SELECT s.id,s.partida_id,s.snapshot_id,s.criado_em,s.mercado,
                 s.linha,s.odd,s.pontuacao_tecnica,s.regra_versao,
                 s.regra_fingerprint,s.motivos_json,s.features_json,s.status,
                 r.resultado,r.retorno_unidades,
                 ROW_NUMBER() OVER(
                   PARTITION BY s.partida_id
                   ORDER BY datetime(s.criado_em),s.id
                 ) AS ordem_partida
          FROM sinais s JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE datetime(s.criado_em)<datetime(?)
            AND s.mercado='gol_ft' AND s.status='simulacao'
            AND json_extract(s.features_json,
                '$.exploracao_sombra.versao')=?
            AND r.resultado IN ('green','red')
            AND r.retorno_unidades IS NOT NULL
        ) SELECT * FROM base WHERE ordem_partida=1
          ORDER BY datetime(criado_em),id
    """, (documento["registrado_em_relogio_sinais"], METODO))
    base = []
    filtrados = []
    for linha in linhas:
        candidato = _candidato_da_linha(linha)
        if candidato is None:
            continue
        item = {
            "odd": _numero(candidato.get("odd")),
            "resultado": linha.get("resultado"),
            "retorno_unidades": linha.get("retorno_unidades"),
            "publicado": False,
        }
        base.append(item)
        if avaliar_filtro_gol_ft_antecipado(
            candidato, {ROLLBACK: "1"}
        ).get("aprovada"):
            filtrados.append((len(base) - 1, item))
    corte_base = int(len(base) * 0.70)
    desenvolvimento = [
        item for posicao, item in filtrados if posicao < corte_base
    ]
    holdout = [
        item for posicao, item in filtrados if posicao >= corte_base
    ]
    return {
        "uso": "geracao_de_hipotese_nao_validante",
        "entra_na_coorte_nova": False,
        "corte_temporal_base": corte_base,
        "gerador_sem_filtro": _metricas(base),
        "filtro_preciso": _metricas([item for _, item in filtrados]),
        "desenvolvimento_historico": _metricas(desenvolvimento),
        "holdout_historico": _metricas(holdout),
        "alerta_sobreajuste": (
            "limiares_escolhidos_apos_observar_historico; "
            "somente_coorte_futura_pode_validar"
        ),
    }


def resumir_validacao(conexao):
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "versao": VERSAO_VALIDACAO,
            "versao_filtro": VERSAO_FILTRO,
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
    referencia = total["referencia_1_sobre_odd"]
    referencia_holdout = holdout["referencia_1_sobre_odd"]
    intervalo_ref = referencia.get("intervalo_desvio_95")
    intervalo_ref_holdout = referencia_holdout.get("intervalo_desvio_95")
    gate_preco = bool(
        referencia.get("taxa_cobertura") == COBERTURA_REFERENCIA_MINIMA
        and isinstance(intervalo_ref, (list, tuple))
        and intervalo_ref[0] > 0
        and referencia_holdout.get("taxa_cobertura")
        == COBERTURA_REFERENCIA_MINIMA
        and isinstance(intervalo_ref_holdout, (list, tuple))
        and intervalo_ref_holdout[0] > 0
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
        total["validos"] >= MINIMO_VALIDOS_TOTAL
        and desenvolvimento["validos"] >= MINIMO_VALIDOS_DESENVOLVIMENTO
        and holdout["validos"] >= MINIMO_VALIDOS_HOLDOUT
        and total.get("taxa_green") is not None
        and total["taxa_green"] >= TAXA_GREEN_ALVO
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
        "versao_filtro": VERSAO_FILTRO,
        "metodo_origem": METODO,
        "saudavel": True,
        **total,
        "estado": "encerrada" if resultados_completos else "coletando",
        "decisao": decisao,
        "apto_revisao": decisao == "favoravel_para_revisao_manual",
        "coorte_fechada": coorte_fechada,
        "resultados_completos": resultados_completos,
        "tamanho_coorte": TAMANHO_COORTE,
        "faltam": max(TAMANHO_COORTE - len(coorte), 0),
        "taxa_green_alvo": TAXA_GREEN_ALVO,
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "checkpoint_seguranca": checkpoint,
        "alerta_desfavoravel": alerta_desfavoravel,
        "gate_preco_conservador": {
            "referencia": "1_sobre_odd_com_margem",
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
        "funil_candidatos": _funil_candidatos_pos_ancora(
            conexao, documento
        ),
        "historico_gerador": _historico_gerador(conexao, documento),
        "politica_seguranca": {
            "checkpoint_fixo": CHECKPOINT_SEGURANCA,
            "efeito": "suspender_somente_entrega_ft_antecipado_preciso",
            "coleta_sombra_continua": True,
            "outros_metodos_inalterados": True,
            "parada_obrigatoria_ao_fechar_coorte": True,
            "reativacao_automatica": False,
        },
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
