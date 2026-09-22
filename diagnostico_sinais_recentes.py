"""Diagnostico somente-leitura do funil apos o ultimo envio de teste."""

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def _inicio_janela_local(horas, agora=None):
    """Usa o mesmo relógio local dos timestamps persistidos no SQLite.

    ``datetime('now')`` do SQLite usa UTC. Os campos ``criado_em`` e
    ``tentado_em`` são gravados no horário local sem fuso; misturar os dois
    relógios deslocava os relatórios e podia deixar a janela recente vazia.
    """
    instante = (agora or datetime.now()).replace(microsecond=0)
    return (instante - timedelta(hours=float(horas))).isoformat(sep=" ")


def _instante_indexavel(valor):
    """Normaliza o separador sem envolver a coluna em ``datetime()``.

    Os instantes persistidos usam ISO-8601 com ``T``. Comparar a coluna
    diretamente permite que o SQLite utilize os índices temporais; aplicar
    ``datetime(criado_em)`` forçava uma varredura integral a cada auditoria.
    """
    if valor is None:
        return None
    return str(valor).replace(" ", "T", 1)


def _categoria_bloqueio(motivo):
    texto = str(motivo or "")
    # Uma oferta pode existir e ainda assim ser incompatível com o alvo
    # (por exemplo, exigir dois escanteios quando o sinal mede mais um).
    # Nesse caso o gargalo é da regra/linha, não da cobertura da fonte.
    if "linha_exige_multiplos_" in texto:
        return "criterio_linha"
    if "odd_ao_vivo_indisponivel" in texto:
        return "cobertura_odds"
    if "historico_" in texto and "_insuficiente" in texto:
        return "cobertura_temporal"
    if "qualidade_insuficiente" in texto:
        return "qualidade_dados"
    if "fonte" in texto or "api_" in texto or "packball_" in texto:
        return "fontes"
    return "criterio_regra"


def _bloqueios_normalizados(motivos):
    bloqueios = [
        str(motivo).removeprefix("bloqueio:")
        for motivo in (motivos or [])
        if str(motivo).startswith("bloqueio:")
    ]
    if any(
        motivo.startswith("linha_exige_multiplos_")
        for motivo in bloqueios
    ):
        # A ausência aqui é da linha-alvo, não da fonte de odds.
        bloqueios = [
            motivo for motivo in bloqueios
            if motivo != "odd_ao_vivo_indisponivel"
        ]
    return sorted(set(bloqueios))


def _resumir_bloqueios(registros):
    bloqueios = defaultdict(lambda: {
        "observacoes": 0,
        "partidas": set(),
    })
    for mercado, partida_id, motivos in registros:
        for motivo in _bloqueios_normalizados(motivos):
            item = bloqueios[(mercado, motivo)]
            item["observacoes"] += 1
            item["partidas"].add(partida_id)
    por_mercado = defaultdict(list)
    for (mercado, motivo), contagem in bloqueios.items():
        por_mercado[mercado].append({
            "motivo": motivo,
            "categoria": _categoria_bloqueio(motivo),
            "observacoes": contagem["observacoes"],
            "partidas": len(contagem["partidas"]),
        })
    return {
        mercado: sorted(
            itens,
            key=lambda item: (
                -item["partidas"], -item["observacoes"], item["motivo"]
            ),
        )
        for mercado, itens in por_mercado.items()
    }


def diagnosticar_funil(conexao, desde, ate=None):
    limite_sinais = (
        " AND criado_em<?" if ate else ""
    )
    limite_entregas = (
        " AND tentado_em<?" if ate else ""
    )
    limite_sinais_alias = (
        " AND s.criado_em<?" if ate else ""
    )
    desde = _instante_indexavel(desde)
    ate = _instante_indexavel(ate)
    parametros = (desde, ate) if ate else (desde,)
    candidatos = [dict(linha) for linha in conexao.execute(
        f"""
        SELECT mercado, status, COUNT(*) AS observacoes,
               COUNT(DISTINCT partida_id) AS partidas
        FROM sinais WHERE criado_em>=?
        {limite_sinais}
        GROUP BY mercado, status ORDER BY mercado, status
        """,
        parametros,
    )]
    entregas_bloqueadas = [dict(linha) for linha in conexao.execute(
        f"""
        SELECT COALESCE(erro, 'sem_motivo') AS motivo,
               COUNT(*) AS quantidade
        FROM entregas_alertas
        WHERE tentado_em>=?
          {limite_entregas}
          AND status IN ('filtrado', 'bloqueado')
        GROUP BY COALESCE(erro, 'sem_motivo')
        ORDER BY quantidade DESC
        """,
        parametros,
    )]
    decisoes_entrega = [dict(linha) for linha in conexao.execute(
        f"""
        WITH ultima_entrega AS (
            SELECT sinal_id, canal, MAX(rowid) AS entrega_rowid
            FROM entregas_alertas
            GROUP BY sinal_id, canal
        ), decisoes AS (
            SELECT s.mercado, s.regra_versao,
                   s.status AS status_sinal,
                   CASE
                     WHEN e.canal IS NOT NULL THEN e.canal
                     WHEN s.status='simulacao' THEN 'gateway:sombra'
                     WHEN s.probabilidade_calibrada IS NULL
                       THEN 'gateway:calibracao'
                     ELSE 'sem_registro'
                   END AS canal,
                   CASE
                     WHEN e.status IS NOT NULL THEN e.status
                     WHEN s.status='simulacao'
                       THEN 'nao_enviado_por_politica'
                     WHEN s.probabilidade_calibrada IS NULL
                       THEN 'nao_elegivel_oficial'
                     ELSE 'sem_registro'
                   END AS status_entrega,
                   CASE
                     WHEN e.rowid IS NOT NULL
                       THEN COALESCE(e.erro, 'sem_motivo')
                     WHEN s.status='simulacao' THEN 'simulacao_sem_envio'
                     WHEN s.probabilidade_calibrada IS NULL
                       THEN 'probabilidade_calibrada_ausente'
                     ELSE 'sem_motivo'
                   END AS motivo,
                   s.id, s.partida_id
            FROM sinais s
            LEFT JOIN ultima_entrega ue ON ue.sinal_id=s.id
            LEFT JOIN entregas_alertas e ON e.rowid=ue.entrega_rowid
            WHERE s.criado_em>=?
              {limite_sinais_alias}
              AND s.status IN ('aprovado', 'simulacao')
        )
        SELECT mercado, regra_versao, status_sinal, canal,
               status_entrega, motivo,
               COUNT(DISTINCT id) AS sinais,
               COUNT(DISTINCT partida_id) AS partidas
        FROM decisoes
        GROUP BY mercado, regra_versao, status_sinal, canal,
                 status_entrega, motivo
        ORDER BY mercado, status_sinal, sinais DESC, status_entrega
        """,
        parametros,
    )]
    registros_recentes = []
    for linha in conexao.execute(
        f"""
        SELECT s.mercado, s.partida_id, s.motivos_json
        FROM sinais s
        JOIN (
            SELECT mercado, partida_id, MAX(id) AS sinal_id
            FROM sinais
            WHERE criado_em>=?
              {limite_sinais}
            GROUP BY mercado, partida_id
        ) recentes ON recentes.sinal_id=s.id
        WHERE s.status='rejeitado'
        """,
        parametros,
    ):
        try:
            motivos = json.loads(linha["motivos_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            motivos = []
        registros_recentes.append((
            linha["mercado"], linha["partida_id"], motivos
        ))
    gargalos_por_mercado = _resumir_bloqueios(registros_recentes)

    # Para explicar escassez de sinais, a última leitura é uma evidência
    # ruim: frequentemente ela já está fora da janela operacional. Escolhe a
    # tentativa válida que chegou mais perto da aprovação em cada
    # mercado/partida (menos bloqueios; depois maior nota; depois mais nova).
    sucessos = {
        (linha["mercado"], linha["partida_id"])
        for linha in conexao.execute(
            f"""
            SELECT DISTINCT mercado, partida_id
            FROM sinais
            WHERE criado_em>=?
              {limite_sinais}
              AND status IN ('aprovado', 'simulacao')
            """,
            parametros,
        )
    }
    melhores = {}
    for linha in conexao.execute(
        f"""
        SELECT id, mercado, partida_id, pontuacao_tecnica, motivos_json
        FROM sinais
        WHERE criado_em>=?
          {limite_sinais}
          AND status='rejeitado'
        ORDER BY id
        """,
        parametros,
    ):
        chave = (linha["mercado"], linha["partida_id"])
        if chave in sucessos:
            continue
        try:
            motivos = json.loads(linha["motivos_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            motivos = []
        bloqueios = _bloqueios_normalizados(motivos)
        if any(
            motivo.startswith("fora_da_janela") for motivo in bloqueios
        ):
            continue
        try:
            nota = float(linha["pontuacao_tecnica"] or 0)
        except (TypeError, ValueError):
            nota = 0.0
        ranking = (len(bloqueios), -nota, -int(linha["id"]))
        if chave not in melhores or ranking < melhores[chave][0]:
            melhores[chave] = (ranking, motivos)
    gargalos_operacionais = _resumir_bloqueios([
        (mercado, partida_id, dados[1])
        for (mercado, partida_id), dados in melhores.items()
    ])
    return {
        "desde": desde,
        "ate": ate,
        "metodo_gargalos": "ultima_observacao_por_mercado_e_partida",
        "metodo_gargalos_operacionais": (
            "melhor_tentativa_na_janela_sem_sinal_por_mercado_e_partida"
        ),
        "candidatos": candidatos,
        "entregas_bloqueadas": entregas_bloqueadas,
        "decisoes_entrega": decisoes_entrega,
        "gargalos_por_mercado": gargalos_por_mercado,
        "gargalos_operacionais_por_mercado": gargalos_operacionais,
    }


def resumir_fluxo_sinais(resultado, funil_operacional=None, limite=5):
    """Classifica a escassez sem confundir repeticoes com jogos distintos.

    O resumo e somente observacional: nao altera regras nem envia alertas. Os
    gargalos usam a ultima decisao de cada par mercado/partida, de modo que um
    jogo reavaliado muitas vezes nao infla artificialmente a conclusao.
    """
    resultado = resultado or {}
    funil_operacional = funil_operacional or {}
    por_status = defaultdict(lambda: {"observacoes": 0, "partidas": 0})
    for item in resultado.get("candidatos") or []:
        status = str(item.get("status") or "desconhecido")
        por_status[status]["observacoes"] += int(
            item.get("observacoes", 0) or 0
        )
        por_status[status]["partidas"] += int(item.get("partidas", 0) or 0)

    categorias = defaultdict(lambda: {"ocorrencias": 0, "partidas": 0})
    motivos = []
    gargalos = (
        resultado.get("gargalos_operacionais_por_mercado")
        or resultado.get("gargalos_por_mercado")
        or {}
    )
    for mercado, itens in gargalos.items():
        for item in itens:
            categoria = str(item.get("categoria") or "criterio_regra")
            ocorrencias = int(item.get("observacoes", 0) or 0)
            partidas = int(item.get("partidas", 0) or 0)
            categorias[categoria]["ocorrencias"] += ocorrencias
            categorias[categoria]["partidas"] += partidas
            motivos.append({
                "mercado": mercado,
                "motivo": item.get("motivo") or "desconhecido",
                "categoria": categoria,
                "partidas": partidas,
                "ocorrencias": ocorrencias,
            })
    motivos.sort(key=lambda item: (
        -item["partidas"], -item["ocorrencias"], item["mercado"],
        item["motivo"],
    ))

    entregues = 0
    entregues_oficiais = 0
    entregues_teste = 0
    bloqueadas = 0
    sem_registro = 0
    nao_elegiveis_oficiais = 0
    sombras_sem_envio = 0
    for item in resultado.get("decisoes_entrega") or []:
        quantidade = int(item.get("sinais", 0) or 0)
        status = str(item.get("status_entrega") or "sem_registro")
        canal = str(item.get("canal") or "sem_registro")
        if status == "entregue":
            entregues += quantidade
            if ":teste" in canal:
                if not canal.endswith(":resultado"):
                    entregues_teste += quantidade
            elif ":" not in canal:
                entregues_oficiais += quantidade
        elif status == "sem_registro":
            sem_registro += quantidade
        elif status == "nao_elegivel_oficial":
            nao_elegiveis_oficiais += quantidade
        elif status == "nao_enviado_por_politica":
            sombras_sem_envio += quantidade
        else:
            bloqueadas += quantidade

    avaliadas = sum(
        item["observacoes"] for item in por_status.values()
    )
    aprovadas = por_status["aprovado"]["observacoes"]
    simulacoes = por_status["simulacao"]["observacoes"]
    snapshots = int(funil_operacional.get("snapshots_ao_vivo", 0) or 0)
    cobertura_candidatos = funil_operacional.get("cobertura_candidatos")
    cobertura_odds = funil_operacional.get("cobertura_odds_estruturadas")

    if snapshots == 0 and avaliadas == 0:
        estado = "sem_jogos_ao_vivo_recentes"
    elif avaliadas == 0:
        estado = "falha_geracao_candidatos"
    elif entregues_oficiais > 0:
        estado = "fluxo_com_entregas_oficiais"
    elif entregues_teste > 0:
        estado = "fluxo_validacao_com_entregas"
    elif aprovadas > 0 and sem_registro > 0:
        estado = "aprovacoes_sem_entrega"
    elif aprovadas > 0 and nao_elegiveis_oficiais > 0:
        estado = "aprovacoes_sem_calibracao"
    elif simulacoes > 0:
        estado = "somente_oportunidades_sombra"
    elif (
        cobertura_odds is not None
        and float(cobertura_odds) < 0.5
        and categorias["cobertura_odds"]["partidas"] > 0
    ):
        estado = "cobertura_odds_restritiva"
    else:
        estado = "sem_oportunidade_elegivel"

    return {
        "estado": estado,
        "desde": resultado.get("desde"),
        "metodo": "ultima_decisao_por_mercado_partida-v1",
        "observacoes": avaliadas,
        "por_status": dict(por_status),
        "entregues": entregues,
        "entregues_oficiais": entregues_oficiais,
        "entregues_teste": entregues_teste,
        "entregas_bloqueadas": bloqueadas,
        "sem_registro_entrega": sem_registro,
        "nao_elegiveis_oficiais": nao_elegiveis_oficiais,
        "sombras_sem_envio": sombras_sem_envio,
        "snapshots_ao_vivo": snapshots,
        "cobertura_candidatos": cobertura_candidatos,
        "cobertura_odds_estruturadas": cobertura_odds,
        "categorias_gargalo": dict(categorias),
        "principais_gargalos": motivos[:max(int(limite), 0)],
        "altera_sinais": False,
        "envia_telegram": False,
    }


def _metricas_janela(conexao, desde, ate):
    desde = _instante_indexavel(desde)
    ate = _instante_indexavel(ate)
    linha = conexao.execute(
        """
        SELECT COUNT(*) AS observacoes,
               COUNT(DISTINCT partida_id) AS partidas,
               COUNT(DISTINCT mercado || ':' || partida_id) AS pares,
               COUNT(DISTINCT CASE
                   WHEN status IN ('aprovado','simulacao')
                   THEN mercado || ':' || partida_id END
               ) AS pares_oportunidade,
               SUM(CASE WHEN status='aprovado' THEN 1 ELSE 0 END)
                   AS aprovacoes,
               SUM(CASE WHEN status='simulacao' THEN 1 ELSE 0 END)
                   AS simulacoes
        FROM sinais
        WHERE criado_em>=?
          AND criado_em<?
        """,
        (desde, ate),
    ).fetchone()
    entregues = conexao.execute(
        """
        SELECT COUNT(DISTINCT s.id)
        FROM sinais s
        JOIN entregas_alertas e ON e.sinal_id=s.id
        WHERE s.criado_em>=?
          AND s.criado_em<?
          AND e.status='entregue'
          AND e.canal NOT LIKE '%:resultado'
        """,
        (desde, ate),
    ).fetchone()[0]
    diagnostico = diagnosticar_funil(conexao, desde, ate=ate)
    categorias = defaultdict(int)
    for itens in (
        diagnostico.get("gargalos_operacionais_por_mercado") or {}
    ).values():
        for item in itens:
            categorias[str(item.get("categoria") or "criterio_regra")] += (
                int(item.get("partidas", 0) or 0)
            )
    pares = int(linha["pares"] or 0)
    pares_oportunidade = int(linha["pares_oportunidade"] or 0)
    return {
        "desde": desde,
        "ate": ate,
        "observacoes": int(linha["observacoes"] or 0),
        "partidas": int(linha["partidas"] or 0),
        "pares_mercado_partida": pares,
        "pares_com_oportunidade": pares_oportunidade,
        "conversao_oportunidade": (
            round(pares_oportunidade / pares, 4) if pares else None
        ),
        "aprovacoes": int(linha["aprovacoes"] or 0),
        "simulacoes": int(linha["simulacoes"] or 0),
        "entregues": int(entregues or 0),
        "gargalos_pares": dict(categorias),
        "gargalos_por_par_avaliado": {
            categoria: round(quantidade / pares, 4)
            for categoria, quantidade in categorias.items()
        } if pares else {},
        "lacunas_qualidade": _lacunas_qualidade_janela(
            conexao, desde, ate
        ),
    }


def _lacunas_qualidade_janela(conexao, desde, ate):
    desde = _instante_indexavel(desde)
    ate = _instante_indexavel(ate)
    existe = conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshots'"
    ).fetchone()
    if existe is None:
        return {
            "disponivel": False,
            "snapshots_abaixo_70": 0,
            "partidas_distintas": 0,
            "campos_ausentes": {},
            "alertas": {},
            "coleta_packball": {},
            "fallback_lista": {},
        }
    colunas = {
        str(item[1])
        for item in conexao.execute("PRAGMA table_info(snapshots)")
    }
    obrigatorias = {
        "partida_id", "coletado_em", "qualidade_dados", "qualidade_json"
    }
    if not obrigatorias.issubset(colunas):
        return {
            "disponivel": False,
            "snapshots_abaixo_70": 0,
            "partidas_distintas": 0,
            "campos_ausentes": {},
            "alertas": {},
            "coleta_packball": {},
            "fallback_lista": {},
        }
    linhas = conexao.execute(
        """
        SELECT partida_id, qualidade_json
        FROM snapshots
        WHERE coletado_em>=?
          AND coletado_em<?
          AND COALESCE(qualidade_dados, 0)<70
        """,
        (desde, ate),
    ).fetchall()
    campos = defaultdict(lambda: {"observacoes": 0, "partidas": set()})
    alertas = defaultdict(lambda: {"observacoes": 0, "partidas": set()})
    coleta_packball = defaultdict(
        lambda: {"observacoes": 0, "partidas": set()}
    )
    fallback_lista = defaultdict(
        lambda: {"observacoes": 0, "partidas": set()}
    )
    partidas = set()
    for linha in linhas:
        partida_id = linha["partida_id"]
        partidas.add(partida_id)
        try:
            qualidade = json.loads(linha["qualidade_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            qualidade = {}
        for campo in set(qualidade.get("campos_ausentes") or []):
            item = campos[str(campo)]
            item["observacoes"] += 1
            item["partidas"].add(partida_id)
        for alerta in set(qualidade.get("alertas") or []):
            item = alertas[str(alerta)]
            item["observacoes"] += 1
            item["partidas"].add(partida_id)
        diagnostico_coleta = qualidade.get(
            "coleta_estatisticas_packball"
        )
        if not isinstance(diagnostico_coleta, dict):
            estado_coleta = "diagnostico_ausente"
        elif diagnostico_coleta.get("campos_essenciais_ausentes"):
            estado_coleta = "detalhe_sem_campos_essenciais"
        elif diagnostico_coleta.get("estado") == "iniciando":
            estado_coleta = "detalhe_nao_concluido"
        else:
            estado_coleta = "detalhe_com_essenciais_lidos"
        item = coleta_packball[estado_coleta]
        item["observacoes"] += 1
        item["partidas"].add(partida_id)

        diagnostico_fallback = qualidade.get("fallback_indicadores_lista")
        if isinstance(diagnostico_fallback, dict):
            estado_fallback = str(
                diagnostico_fallback.get("motivo") or "sem_motivo"
            )
        else:
            estado_fallback = "diagnostico_ausente"
        item = fallback_lista[estado_fallback]
        item["observacoes"] += 1
        item["partidas"].add(partida_id)

    def finalizar(itens):
        return {
            chave: {
                "observacoes": valor["observacoes"],
                "partidas": len(valor["partidas"]),
            }
            for chave, valor in sorted(
                itens.items(),
                key=lambda item: (
                    -len(item[1]["partidas"]),
                    -item[1]["observacoes"],
                    item[0],
                ),
            )
        }

    return {
        "disponivel": True,
        "snapshots_abaixo_70": len(linhas),
        "partidas_distintas": len(partidas),
        "campos_ausentes": finalizar(campos),
        "alertas": finalizar(alertas),
        "coleta_packball": finalizar(coleta_packball),
        "fallback_lista": finalizar(fallback_lista),
    }


def comparar_fluxos_consecutivos(
    conexao, horas=24, agora=None, deslocamento_horas=None,
):
    """Explica queda de envios comparando duas janelas sem mudar sinais.

    Por padrao, compara periodos imediatamente consecutivos. Quando
    ``deslocamento_horas`` e informado, a janela anterior termina esse total
    de horas antes do fim da janela atual. Isso permite comparar, por
    exemplo, as ultimas seis horas com o mesmo horario do dia anterior sem
    misturar a madrugada e a manha no diagnostico.
    """
    horas = max(float(horas), 1.0)
    agora = (agora or datetime.now()).replace(microsecond=0)
    deslocamento = (
        horas if deslocamento_horas is None
        else max(float(deslocamento_horas), horas)
    )
    inicio_atual = agora - timedelta(hours=horas)
    fim_anterior = agora - timedelta(hours=deslocamento)
    inicio_anterior = fim_anterior - timedelta(hours=horas)
    atual = _metricas_janela(
        conexao, inicio_atual.isoformat(), agora.isoformat()
    )
    anterior = _metricas_janela(
        conexao, inicio_anterior.isoformat(), fim_anterior.isoformat()
    )
    oportunidades_atual = atual["pares_com_oportunidade"]
    oportunidades_anterior = anterior["pares_com_oportunidade"]
    entregues_atual = atual["entregues"]
    entregues_anterior = anterior["entregues"]
    possui_evidencia_entregas = (entregues_atual + entregues_anterior) > 0
    if possui_evidencia_entregas:
        metrica_volume = "entregas"
        volume_atual = entregues_atual
        volume_anterior = entregues_anterior
    else:
        # Bancos antigos e testes sem trilha de entrega ainda podem explicar
        # a geração de oportunidades sem inventar uma queda no Telegram.
        metrica_volume = "oportunidades"
        volume_atual = oportunidades_atual
        volume_anterior = oportunidades_anterior
    delta = volume_atual - volume_anterior
    variacao = (
        round(delta / volume_anterior, 4)
        if volume_anterior else None
    )
    conversao_atual = atual["conversao_oportunidade"]
    conversao_anterior = anterior["conversao_oportunidade"]
    partidas_atual = atual["partidas"]
    partidas_anterior = anterior["partidas"]
    razao_partidas = (
        partidas_atual / partidas_anterior if partidas_anterior else None
    )
    razao_conversao = (
        conversao_atual / conversao_anterior
        if conversao_atual is not None and conversao_anterior
        else None
    )
    deltas_gargalos = {}
    categorias = set(atual["gargalos_por_par_avaliado"]) | set(
        anterior["gargalos_por_par_avaliado"]
    )
    for categoria in sorted(categorias):
        deltas_gargalos[categoria] = round(
            atual["gargalos_por_par_avaliado"].get(categoria, 0.0)
            - anterior["gargalos_por_par_avaliado"].get(categoria, 0.0),
            4,
        )
    principal_candidato = max(
        deltas_gargalos,
        key=deltas_gargalos.get,
        default=None,
    )
    principal = (
        principal_candidato
        if principal_candidato is not None
        and deltas_gargalos.get(principal_candidato, 0.0) > 0
        else None
    )
    mapa_causas = {
        "cobertura_odds": "queda_cobertura_odds",
        "qualidade_dados": "queda_qualidade_dados",
        "cobertura_temporal": "historico_temporal_insuficiente",
        "criterio_linha": "linhas_disponiveis_incompativeis",
        "fontes": "degradacao_fontes_auxiliares",
        "criterio_regra": "menos_partidas_no_padrao",
    }
    if delta >= 0:
        causa = "sem_reducao_comprovada"
    elif (
        metrica_volume == "entregas"
        and oportunidades_atual >= oportunidades_anterior
        and atual["aprovacoes"] >= anterior["aprovacoes"]
    ):
        causa = "queda_pos_aprovacao"
    elif (
        metrica_volume == "entregas"
        and oportunidades_atual >= oportunidades_anterior
    ):
        causa = "menos_aprovacoes"
    elif (
        razao_partidas is not None
        and razao_partidas < 0.80
        and (razao_conversao is None or razao_conversao >= 0.85)
    ):
        causa = "menos_partidas_avaliadas"
    elif (
        razao_conversao is not None
        and razao_conversao < 0.85
        and principal is not None
        and deltas_gargalos.get(principal, 0.0) >= 0.05
    ):
        causa = mapa_causas.get(principal, "variacao_multifatorial")
    elif razao_partidas is not None and razao_partidas < 0.90:
        causa = "menos_partidas_avaliadas"
    else:
        causa = "variacao_multifatorial"
    causas_contribuintes = []
    if delta < 0:
        if razao_partidas is not None and razao_partidas < 0.90:
            causas_contribuintes.append("menos_partidas_avaliadas")
        if atual["aprovacoes"] < anterior["aprovacoes"]:
            causas_contribuintes.append("menos_aprovacoes")
        elif (
            metrica_volume == "entregas"
            and entregues_atual < entregues_anterior
        ):
            causas_contribuintes.append("queda_pos_aprovacao")
        if (
            principal is not None
            and deltas_gargalos.get(principal, 0.0) >= 0.05
        ):
            causas_contribuintes.append(
                mapa_causas.get(principal, "variacao_multifatorial")
            )
    causas_contribuintes = list(dict.fromkeys(causas_contribuintes))
    periodos_alinhados = deslocamento > horas
    return {
        "versao": (
            "comparacao-fluxo-periodos-alinhados-v1"
            if periodos_alinhados
            else "comparacao-fluxo-periodos-v2"
        ),
        "tipo_comparacao": (
            "mesmo_horario_anterior"
            if periodos_alinhados else "periodos_consecutivos"
        ),
        "horas_por_periodo": horas,
        "deslocamento_horas": deslocamento,
        "metrica_volume": metrica_volume,
        "evidencia_entregas": possui_evidencia_entregas,
        "atual": atual,
        "anterior": anterior,
        "delta_pares_com_oportunidade": (
            oportunidades_atual - oportunidades_anterior
        ),
        "delta_entregas": entregues_atual - entregues_anterior,
        "delta_volume": delta,
        "variacao_oportunidades": variacao,
        "razao_partidas": (
            round(razao_partidas, 4) if razao_partidas is not None else None
        ),
        "razao_conversao": (
            round(razao_conversao, 4)
            if razao_conversao is not None else None
        ),
        "causa_principal": causa,
        "causas_contribuintes": causas_contribuintes,
        "categoria_gargalo_com_maior_alta": principal,
        "deltas_gargalos_normalizados": deltas_gargalos,
        "altera_sinais": False,
        "envia_telegram": False,
    }


def comparar_fluxos_mesmo_horario(
    conexao, horas=6, agora=None, deslocamento_horas=24,
):
    """Compara uma janela curta com o mesmo horario do periodo anterior."""
    return comparar_fluxos_consecutivos(
        conexao,
        horas=horas,
        agora=agora,
        deslocamento_horas=deslocamento_horas,
    )


def _resumir(resultado, limite=8):
    return {
        "desde": resultado["desde"],
        "metodo_gargalos": resultado["metodo_gargalos"],
        "metodo_gargalos_operacionais": resultado.get(
            "metodo_gargalos_operacionais"
        ),
        "candidatos": resultado["candidatos"],
        "entregas_bloqueadas": resultado["entregas_bloqueadas"][:limite],
        "decisoes_entrega": resultado["decisoes_entrega"],
        "gargalos_por_mercado": {
            mercado: itens[:limite]
            for mercado, itens in resultado["gargalos_por_mercado"].items()
        },
        "gargalos_operacionais_por_mercado": {
            mercado: itens[:limite]
            for mercado, itens in (
                resultado.get("gargalos_operacionais_por_mercado") or {}
            ).items()
        },
    }


def main():
    parser = argparse.ArgumentParser()
    janela = parser.add_mutually_exclusive_group()
    janela.add_argument(
        "--horas",
        type=int,
        help="Analisa uma janela fixa das ultimas N horas.",
    )
    janela.add_argument(
        "--desde",
        help="Analisa desde um instante SQLite/ISO informado.",
    )
    parser.add_argument(
        "--resumo",
        action="store_true",
        help="Limita a lista de gargalos por mercado.",
    )
    janela.add_argument(
        "--comparar-horas",
        type=float,
        help=(
            "Compara as últimas N horas com as N horas imediatamente "
            "anteriores."
        ),
    )
    janela.add_argument(
        "--comparar-mesmo-horario",
        type=float,
        help=(
            "Compara as últimas N horas com o mesmo horário do dia "
            "anterior."
        ),
    )
    argumentos = parser.parse_args()
    caminho = Path(__file__).with_name("monitor_packball.db")
    conexao = sqlite3.connect(
        f"file:{caminho.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    conexao.row_factory = sqlite3.Row
    try:
        if argumentos.comparar_mesmo_horario is not None:
            if argumentos.comparar_mesmo_horario <= 0:
                parser.error(
                    "--comparar-mesmo-horario deve ser maior que zero"
                )
            resultado = comparar_fluxos_mesmo_horario(
                conexao, horas=argumentos.comparar_mesmo_horario
            )
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
            return
        if argumentos.comparar_horas is not None:
            if argumentos.comparar_horas <= 0:
                parser.error("--comparar-horas deve ser maior que zero")
            resultado = comparar_fluxos_consecutivos(
                conexao, horas=argumentos.comparar_horas
            )
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
            return
        if argumentos.desde:
            ultimo = argumentos.desde
        elif argumentos.horas is not None:
            if argumentos.horas <= 0:
                parser.error("--horas deve ser maior que zero")
            ultimo = _inicio_janela_local(argumentos.horas)
        else:
            ultimo = conexao.execute(
                """
                SELECT MAX(entregue_em) AS instante
                FROM entregas_alertas
                WHERE status='entregue' AND canal LIKE '%:teste'
                """
            ).fetchone()["instante"]
            if not ultimo:
                ultimo = _inicio_janela_local(24)
        resultado = diagnosticar_funil(conexao, ultimo)
        if argumentos.resumo:
            resultado = _resumir(resultado)
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    finally:
        conexao.close()


if __name__ == "__main__":
    main()
