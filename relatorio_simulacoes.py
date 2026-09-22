import json
import math
from collections import defaultdict
from datetime import datetime

from backtest import calcular_metricas


VERSAO_EXPERIMENTO_FILTRO = "filtro-simulacoes-v2"
VERSAO_CONCLUSAO_EXPERIMENTO_FILTRO = "conclusao-filtro-simulacoes-v1"
GATILHOS_EXPERIMENTO_FILTRO = frozenset({
    "trg_experimento_filtro_update_imutavel",
    "trg_experimento_filtro_delete_imutavel",
})
GATILHOS_CONCLUSAO_EXPERIMENTO_FILTRO = frozenset({
    "trg_conclusao_experimento_filtro_update_imutavel",
    "trg_conclusao_experimento_filtro_delete_imutavel",
})


def _chave_experimento_filtro(
    regra_versao, pontuacao_minima, qualidade_minima,
):
    return (
        f"experimento_filtro_teste:{VERSAO_EXPERIMENTO_FILTRO}:"
        f"{regra_versao}:{float(pontuacao_minima):g}:"
        f"{float(qualidade_minima):g}"
    )


def _chave_conclusao_experimento_filtro(
    regra_versao, pontuacao_minima, qualidade_minima, regra_fingerprint,
):
    return (
        "conclusao_experimento_filtro:"
        f"{VERSAO_CONCLUSAO_EXPERIMENTO_FILTRO}:"
        f"{regra_versao}:{float(pontuacao_minima):g}:"
        f"{float(qualidade_minima):g}:{regra_fingerprint}"
    )


def obter_experimento_filtro(
    conexao, regra_versao, pontuacao_minima, qualidade_minima,
):
    chave = _chave_experimento_filtro(
        regra_versao, pontuacao_minima, qualidade_minima
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is None:
        return None
    try:
        dados = json.loads(linha["valor"])
    except (TypeError, ValueError, json.JSONDecodeError):
        raise RuntimeError("Marco do experimento de filtro esta corrompido.")
    esperado = {
        "versao": VERSAO_EXPERIMENTO_FILTRO,
        "regra_versao": regra_versao,
        "pontuacao_minima": float(pontuacao_minima),
        "qualidade_minima": float(qualidade_minima),
    }
    if any(dados.get(chave) != valor for chave, valor in esperado.items()):
        raise RuntimeError("Marco do experimento de filtro esta incoerente.")
    try:
        datetime.fromisoformat(dados["iniciado_em"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("Inicio do experimento de filtro esta invalido.")
    return dados


def registrar_ou_obter_experimento_filtro(
    conexao, regra_versao, pontuacao_minima, qualidade_minima, agora=None,
):
    existente = obter_experimento_filtro(
        conexao, regra_versao, pontuacao_minima, qualidade_minima
    )
    if existente is not None:
        return existente
    dados = {
        "versao": VERSAO_EXPERIMENTO_FILTRO,
        "regra_versao": regra_versao,
        "pontuacao_minima": float(pontuacao_minima),
        "qualidade_minima": float(qualidade_minima),
        "iniciado_em": (agora or datetime.now()).replace(
            microsecond=0
        ).isoformat(),
    }
    chave = _chave_experimento_filtro(
        regra_versao, pontuacao_minima, qualidade_minima
    )
    with conexao:
        conexao.execute(
            "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
            (chave, json.dumps(dados, sort_keys=True)),
        )
    return obter_experimento_filtro(
        conexao, regra_versao, pontuacao_minima, qualidade_minima
    )


def obter_conclusao_experimento_filtro(
    conexao,
    regra_versao,
    pontuacao_minima,
    qualidade_minima,
    regra_fingerprint,
):
    if not regra_fingerprint:
        return None
    chave = _chave_conclusao_experimento_filtro(
        regra_versao,
        pontuacao_minima,
        qualidade_minima,
        regra_fingerprint,
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is None:
        return None
    try:
        dados = json.loads(linha["valor"])
    except (TypeError, ValueError, json.JSONDecodeError):
        raise RuntimeError(
            "Conclusao do experimento de filtro esta corrompida."
        )
    esperado = {
        "versao": VERSAO_CONCLUSAO_EXPERIMENTO_FILTRO,
        "versao_experimento": VERSAO_EXPERIMENTO_FILTRO,
        "regra_versao": regra_versao,
        "pontuacao_minima": float(pontuacao_minima),
        "qualidade_minima": float(qualidade_minima),
        "regra_fingerprint": regra_fingerprint,
    }
    if any(dados.get(campo) != valor for campo, valor in esperado.items()):
        raise RuntimeError(
            "Conclusao do experimento de filtro esta incoerente."
        )
    evidencia = dados.get("evidencia") or {}
    if (
        dados.get("decisao") not in (
            "evidencia_favoravel", "nao_comprovado"
        )
        or evidencia.get("estado") != "avaliavel"
        or evidencia.get("decisao") != dados.get("decisao")
    ):
        raise RuntimeError(
            "Evidencia da conclusao do experimento de filtro esta invalida."
        )
    try:
        datetime.fromisoformat(dados["iniciado_em"])
        datetime.fromisoformat(dados["concluido_em"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError(
            "Datas da conclusao do experimento de filtro estao invalidas."
        )
    return dados


def registrar_ou_obter_conclusao_experimento_filtro(
    conexao,
    regra_versao,
    pontuacao_minima,
    qualidade_minima,
    regra_fingerprint,
    comparacao,
    agora=None,
):
    """Congela a primeira análise avaliável; novas tentativas exigem versão."""
    existente = obter_conclusao_experimento_filtro(
        conexao,
        regra_versao,
        pontuacao_minima,
        qualidade_minima,
        regra_fingerprint,
    )
    if existente is not None:
        return existente
    geral = ((comparacao or {}).get("comparacao") or {}).get("geral") or {}
    if geral.get("estado") != "avaliavel":
        return None
    gatilhos = {
        linha[0]
        for linha in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    ausentes = GATILHOS_CONCLUSAO_EXPERIMENTO_FILTRO - gatilhos
    if ausentes:
        raise RuntimeError(
            "Conclusao do experimento de filtro esta sem protecao imutavel."
        )
    experimento = obter_experimento_filtro(
        conexao, regra_versao, pontuacao_minima, qualidade_minima
    )
    if experimento is None:
        raise RuntimeError(
            "Nao e possivel concluir experimento de filtro sem marco."
        )
    dados = {
        "versao": VERSAO_CONCLUSAO_EXPERIMENTO_FILTRO,
        "versao_experimento": VERSAO_EXPERIMENTO_FILTRO,
        "regra_versao": regra_versao,
        "pontuacao_minima": float(pontuacao_minima),
        "qualidade_minima": float(qualidade_minima),
        "regra_fingerprint": regra_fingerprint,
        "iniciado_em": experimento["iniciado_em"],
        "concluido_em": (agora or datetime.now()).replace(
            microsecond=0
        ).isoformat(),
        "decisao": geral.get("decisao") or "nao_comprovado",
        "evidencia": geral,
    }
    chave = _chave_conclusao_experimento_filtro(
        regra_versao,
        pontuacao_minima,
        qualidade_minima,
        regra_fingerprint,
    )
    with conexao:
        conexao.execute(
            "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
            (chave, json.dumps(dados, sort_keys=True)),
        )
    return obter_conclusao_experimento_filtro(
        conexao,
        regra_versao,
        pontuacao_minima,
        qualidade_minima,
        regra_fingerprint,
    )


def auditar_experimento_filtro(
    conexao,
    regra_versao,
    pontuacao_minima,
    qualidade_minima,
    ativo=True,
    regra_fingerprint=None,
    exigir_linhagem=False,
):
    contadores_vazios = {
        "decisoes_enviadas_auditadas": 0,
        "decisoes_filtradas_auditadas": 0,
        "simulacoes_enviadas_fora_criterio": 0,
        "filtros_motivo_incoerente": 0,
        "decisoes_fora_linhagem": 0,
    }
    if not ativo:
        return {
            "saudavel": True,
            "estado": "desativado",
            "motivo": None,
            "protegido": True,
            "iniciado_em": None,
            "decisoes_filtradas_anteriores": 0,
            **contadores_vazios,
        }
    gatilhos = {
        item[0]
        for item in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    ausentes = sorted(GATILHOS_EXPERIMENTO_FILTRO - gatilhos)
    try:
        experimento = obter_experimento_filtro(
            conexao,
            regra_versao,
            pontuacao_minima,
            qualidade_minima,
        )
        conclusao = obter_conclusao_experimento_filtro(
            conexao,
            regra_versao,
            pontuacao_minima,
            qualidade_minima,
            regra_fingerprint,
        )
        if conclusao is not None:
            ausentes = sorted(
                set(ausentes)
                | (GATILHOS_CONCLUSAO_EXPERIMENTO_FILTRO - gatilhos)
            )
    except RuntimeError as erro:
        return {
            "saudavel": False,
            "estado": "invalido",
            "motivo": str(erro),
            "protegido": not ausentes,
            "gatilhos_ausentes": ausentes,
            "iniciado_em": None,
            "decisoes_filtradas_anteriores": 0,
            **contadores_vazios,
        }
    if experimento is None:
        return {
            "saudavel": False,
            "estado": "ausente",
            "motivo": "marco_experimento_filtro_ausente",
            "protegido": not ausentes,
            "gatilhos_ausentes": ausentes,
            "iniciado_em": None,
            "decisoes_filtradas_anteriores": 0,
            **contadores_vazios,
        }
    if exigir_linhagem and not regra_fingerprint:
        return {
            **experimento,
            "saudavel": False,
            "estado": "invalido",
            "motivo": "linhagem_regra_indisponivel",
            "protegido": not ausentes,
            "gatilhos_ausentes": ausentes,
            "decisoes_filtradas_anteriores": 0,
            **contadores_vazios,
        }
    anteriores = conexao.execute(
        """
        SELECT COUNT(*)
        FROM entregas_alertas e
        JOIN sinais s ON s.id=e.sinal_id
        WHERE e.canal='gateway:teste' AND e.status='filtrado'
          AND s.regra_versao=?
          AND datetime(s.criado_em) < datetime(?)
        """,
        (regra_versao, experimento["iniciado_em"]),
    ).fetchone()[0]
    experimentos_anteriores = 0
    for linha in conexao.execute(
        "SELECT valor FROM metadados WHERE chave LIKE ?",
        ("experimento_filtro_teste:%",),
    ).fetchall():
        try:
            marco = json.loads(linha["valor"])
            inicio_marco = datetime.fromisoformat(marco["iniciado_em"])
            inicio_atual = datetime.fromisoformat(experimento["iniciado_em"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            marco.get("regra_versao") == regra_versao
            and inicio_marco < inicio_atual
        ):
            experimentos_anteriores += 1
    anteriores_sem_experimento = (
        0 if experimentos_anteriores else int(anteriores or 0)
    )
    parametros = (
        pontuacao_minima,
        qualidade_minima,
        regra_versao,
        experimento["iniciado_em"],
        *(
            (regra_fingerprint,)
            if regra_fingerprint is not None else ()
        ),
    )
    clausula_fingerprint = (
        " AND s.regra_fingerprint=?"
        if regra_fingerprint is not None else ""
    )
    enviadas = conexao.execute(
        f"""
        SELECT COUNT(DISTINCT s.id) AS total,
               COUNT(DISTINCT CASE
                   WHEN COALESCE(s.pontuacao_tecnica, 0) < ?
                     OR NOT json_valid(s.features_json)
                     OR COALESCE(
                         CAST(json_extract(
                             s.features_json, '$.qualidade_dados'
                         ) AS REAL), 0
                     ) < ?
                   THEN s.id
               END) AS fora_criterio
        FROM entregas_alertas e
        JOIN sinais s ON s.id=e.sinal_id
        WHERE e.status='entregue'
          AND e.canal LIKE '%:teste'
          AND e.canal NOT LIKE '%:teste:resultado'
          AND s.regra_versao=?
          AND datetime(s.criado_em) >= datetime(?)
          {clausula_fingerprint}
        """,
        parametros,
    ).fetchone()
    filtradas = conexao.execute(
        f"""
        WITH decisoes AS (
            SELECT e.erro,
                   COALESCE(s.pontuacao_tecnica, 0) AS pontuacao,
                   CASE
                       WHEN json_valid(s.features_json)
                       THEN COALESCE(
                           CAST(json_extract(
                               s.features_json, '$.qualidade_dados'
                           ) AS REAL), 0
                       )
                       ELSE 0
                   END AS qualidade
            FROM entregas_alertas e
            JOIN sinais s ON s.id=e.sinal_id
            WHERE e.canal='gateway:teste' AND e.status='filtrado'
              AND s.regra_versao=?
              AND datetime(s.criado_em) >= datetime(?)
              {clausula_fingerprint}
        )
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE
                   WHEN erro='pontuacao_teste_insuficiente'
                        AND pontuacao < ? THEN 0
                   WHEN erro='qualidade_teste_insuficiente'
                        AND pontuacao >= ? AND qualidade < ? THEN 0
                   ELSE 1
               END), 0) AS motivo_incoerente
        FROM decisoes
        """,
        (
            regra_versao,
            experimento["iniciado_em"],
            *(
                (regra_fingerprint,)
                if regra_fingerprint is not None else ()
            ),
            pontuacao_minima,
            pontuacao_minima,
            qualidade_minima,
        ),
    ).fetchone()
    decisoes_fora_linhagem = 0
    if regra_fingerprint is not None:
        decisoes_fora_linhagem = int(conexao.execute(
            """
            SELECT COUNT(DISTINCT s.id)
            FROM sinais s
            JOIN entregas_alertas e ON e.sinal_id=s.id
            WHERE s.regra_versao=?
              AND datetime(s.criado_em) >= datetime(?)
              AND s.regra_fingerprint IS NOT ?
              AND (
                (e.status='entregue' AND e.canal LIKE '%:teste'
                 AND e.canal NOT LIKE '%:teste:resultado')
                OR (e.canal='gateway:teste' AND e.status='filtrado')
              )
            """,
            (
                regra_versao,
                experimento["iniciado_em"],
                regra_fingerprint,
            ),
        ).fetchone()[0] or 0)
    enviadas_total = int(enviadas["total"] or 0)
    enviadas_fora = int(enviadas["fora_criterio"] or 0)
    filtradas_total = int(filtradas["total"] or 0)
    filtros_incoerentes = int(filtradas["motivo_incoerente"] or 0)
    if ausentes:
        estado = "sem_protecao"
        motivo = "gatilhos_experimento_filtro_ausentes"
    elif decisoes_fora_linhagem:
        estado = "incoerente"
        motivo = "decisoes_fora_linhagem_atual"
    elif anteriores_sem_experimento:
        estado = "incoerente"
        motivo = "decisoes_filtradas_anteriores_ao_marco"
    elif enviadas_fora:
        estado = "incoerente"
        motivo = "envios_fora_criterio_filtro"
    elif filtros_incoerentes:
        estado = "incoerente"
        motivo = "motivos_filtro_incoerentes"
    else:
        estado = "valido"
        motivo = None
    return {
        **experimento,
        "saudavel": motivo is None,
        "estado": estado,
        "motivo": motivo,
        "protegido": not ausentes,
        "gatilhos_ausentes": ausentes,
        "decisoes_filtradas_anteriores": anteriores_sem_experimento,
        "experimentos_anteriores": experimentos_anteriores,
        "decisoes_enviadas_auditadas": enviadas_total,
        "decisoes_filtradas_auditadas": filtradas_total,
        "simulacoes_enviadas_fora_criterio": enviadas_fora,
        "filtros_motivo_incoerente": filtros_incoerentes,
        "decisoes_fora_linhagem": decisoes_fora_linhagem,
        "regra_fingerprint": regra_fingerprint,
        "conclusao": conclusao,
    }


def resumir_simulacoes(conexao, regra_versao=None):
    linhas = conexao.execute(
        """
        SELECT DISTINCT s.id, s.partida_id, s.criado_em, s.mercado,
               r.resultado, r.retorno_unidades, r.encerrado_em,
               NOT EXISTS (
                   SELECT 1 FROM sinais anterior
                   WHERE anterior.partida_id=s.partida_id
                     AND anterior.mercado=s.mercado
                     AND anterior.regra_versao=s.regra_versao
                     AND anterior.id<s.id
                     AND anterior.status IN (
                         'aprovado', 'duplicado', 'simulacao'
                     )
               ) AS primeira_decisao
        FROM sinais s
        JOIN entregas_alertas e ON e.sinal_id=s.id
          AND e.status='entregue' AND e.canal LIKE '%:teste'
          AND e.canal NOT LIKE '%:teste:resultado'
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE (? IS NULL OR s.regra_versao=?)
        ORDER BY COALESCE(r.encerrado_em, '9999'), s.id
        """,
        (regra_versao, regra_versao),
    ).fetchall()
    grupos = defaultdict(list)
    for linha in linhas:
        item = dict(linha)
        grupos[item["mercado"]].append(item)
        grupos["geral"].append(item)
    resumo = {}
    for mercado, itens in grupos.items():
        validos = [item for item in itens if item["primeira_decisao"]]
        excluidos = len(itens) - len(validos)
        resolvidos = [
            item for item in validos if item["resultado"] is not None
        ]
        resolvidos.sort(key=lambda item: (item["criado_em"], item["id"]))
        independentes = []
        chaves_vistas = set()
        for item in resolvidos:
            chave = (item["partida_id"], item["mercado"])
            if chave in chaves_vistas:
                continue
            chaves_vistas.add(chave)
            independentes.append(item)
        resumo[mercado] = {
            **calcular_metricas(independentes),
            "entregues": len(itens),
            "pendentes": len(validos) - len(resolvidos),
            "resultados_brutos": len(resolvidos),
            "excluidos_nao_primeira_decisao": excluidos,
            "partidas_independentes_entregues": len({
                (item["partida_id"], item["mercado"])
                for item in validos
            }),
        }
    return resumo


def comparar_filtro_simulacoes(
    conexao, regra_versao=None, amostra_minima=30, iniciado_em=None,
    regra_fingerprint=None,
):
    """Compara decisões persistidas antes do resultado, sem reclassificá-las."""
    clausula_fingerprint = (
        " AND s.regra_fingerprint=?"
        if regra_fingerprint is not None else ""
    )
    linhas = conexao.execute(
        f"""
        SELECT DISTINCT
               s.id, s.partida_id, s.criado_em, s.mercado,
               s.pontuacao_tecnica,
               r.resultado, r.retorno_unidades, r.encerrado_em,
               CASE
                 WHEN EXISTS (
                   SELECT 1 FROM entregas_alertas enviada
                   WHERE enviada.sinal_id=s.id
                     AND enviada.status='entregue'
                     AND enviada.canal LIKE '%:teste'
                     AND enviada.canal NOT LIKE '%:teste:resultado'
                 ) THEN 'enviadas'
                 WHEN EXISTS (
                   SELECT 1 FROM entregas_alertas filtrada
                   WHERE filtrada.sinal_id=s.id
                     AND filtrada.canal='gateway:teste'
                     AND filtrada.status='filtrado'
                 ) THEN 'filtradas'
               END AS coorte,
               (
                 SELECT filtrada.erro
                 FROM entregas_alertas filtrada
                 WHERE filtrada.sinal_id=s.id
                   AND filtrada.canal='gateway:teste'
                   AND filtrada.status='filtrado'
                 ORDER BY filtrada.id LIMIT 1
               ) AS motivo_filtro,
               NOT EXISTS (
                   SELECT 1 FROM sinais anterior
                   WHERE anterior.partida_id=s.partida_id
                     AND anterior.mercado=s.mercado
                     AND anterior.regra_versao=s.regra_versao
                     AND anterior.id<s.id
                     AND anterior.status IN (
                         'aprovado', 'duplicado', 'simulacao'
                     )
               ) AS primeira_decisao
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE (? IS NULL OR s.regra_versao=?)
          AND (? IS NULL OR datetime(s.criado_em) >= datetime(?))
          {clausula_fingerprint}
          AND (
            EXISTS (
              SELECT 1 FROM entregas_alertas enviada
              WHERE enviada.sinal_id=s.id
                AND enviada.status='entregue'
                AND enviada.canal LIKE '%:teste'
                AND enviada.canal NOT LIKE '%:teste:resultado'
            )
            OR EXISTS (
              SELECT 1 FROM entregas_alertas filtrada
              WHERE filtrada.sinal_id=s.id
                AND filtrada.canal='gateway:teste'
                AND filtrada.status='filtrado'
            )
          )
        ORDER BY s.criado_em, s.id
        """,
        (
            regra_versao, regra_versao, iniciado_em, iniciado_em,
            *(
                (regra_fingerprint,)
                if regra_fingerprint is not None else ()
            ),
        ),
    ).fetchall()

    grupos = {
        "enviadas": defaultdict(list),
        "filtradas": defaultdict(list),
    }
    for linha in linhas:
        item = dict(linha)
        if not item["primeira_decisao"]:
            continue
        destino = grupos[item["coorte"]]
        destino[item["mercado"]].append(item)
        destino["geral"].append(item)

    resumo = {
        "iniciado_em": iniciado_em,
        "regra_fingerprint": regra_fingerprint,
        "enviadas": {},
        "filtradas": {},
        "comparacao": {},
    }
    for coorte, mercados in grupos.items():
        for mercado, itens in mercados.items():
            resolvidos = [
                item for item in itens if item["resultado"] is not None
            ]
            metricas = calcular_metricas(resolvidos)
            motivos = defaultdict(int)
            for item in itens:
                if item.get("motivo_filtro"):
                    motivos[item["motivo_filtro"]] += 1
            resumo[coorte][mercado] = {
                **metricas,
                "decisoes": len(itens),
                "pendentes": len(itens) - len(resolvidos),
                "motivos_filtro": dict(sorted(motivos.items())),
            }

    mercados = sorted(
        set(resumo["enviadas"]) | set(resumo["filtradas"])
    )
    for mercado in mercados:
        enviadas = resumo["enviadas"].get(mercado, {})
        filtradas = resumo["filtradas"].get(mercado, {})
        n_enviadas = int(enviadas.get("amostra") or 0)
        n_filtradas = int(filtradas.get("amostra") or 0)
        decisoes_enviadas = int(enviadas.get("decisoes") or 0)
        decisoes_filtradas = int(filtradas.get("decisoes") or 0)
        pendentes_enviadas = int(enviadas.get("pendentes") or 0)
        pendentes_filtradas = int(filtradas.get("pendentes") or 0)
        avaliavel = (
            n_enviadas >= amostra_minima
            and n_filtradas >= amostra_minima
        )
        taxa_enviadas = enviadas.get("taxa_acerto")
        taxa_filtradas = filtradas.get("taxa_acerto")
        roi_enviadas = enviadas.get("roi")
        roi_filtradas = filtradas.get("roi")
        itens_enviadas = grupos["enviadas"].get(mercado, [])
        itens_filtradas = grupos["filtradas"].get(mercado, [])
        resolvidos_enviadas = [
            item for item in itens_enviadas
            if item.get("resultado") in (
                "green", "half_green", "red", "half_red"
            )
        ]
        resolvidos_filtradas = [
            item for item in itens_filtradas
            if item.get("resultado") in (
                "green", "half_green", "red", "half_red"
            )
        ]
        intervalo_roi = (
            _intervalo_delta_media_95(
                [
                    float(item.get("retorno_unidades") or 0)
                    for item in resolvidos_enviadas
                ],
                [
                    float(item.get("retorno_unidades") or 0)
                    for item in resolvidos_filtradas
                ],
            )
            if avaliavel else None
        )
        intervalo_acerto = (
            _intervalo_delta_media_95(
                [
                    1.0
                    if item["resultado"] in ("green", "half_green")
                    else 0.0
                    for item in resolvidos_enviadas
                ],
                [
                    1.0
                    if item["resultado"] in ("green", "half_green")
                    else 0.0
                    for item in resolvidos_filtradas
                ],
            )
            if avaliavel else None
        )
        evidencia_favoravel = bool(
            avaliavel
            and roi_enviadas is not None
            and roi_enviadas > 0
            and intervalo_roi is not None
            and intervalo_roi[0] > 0
            and intervalo_acerto is not None
            and intervalo_acerto[0] >= 0
        )
        resumo["comparacao"][mercado] = {
            "estado": "avaliavel" if avaliavel else "amostra_insuficiente",
            "decisao": (
                "evidencia_favoravel"
                if evidencia_favoravel else
                "nao_comprovado"
                if avaliavel else
                "aguardando_amostra"
            ),
            "aplicacao_automatica": False,
            "amostra_minima_por_coorte": int(amostra_minima),
            "decisoes_enviadas": decisoes_enviadas,
            "decisoes_filtradas": decisoes_filtradas,
            "resultados_resolvidos_enviadas": max(
                decisoes_enviadas - pendentes_enviadas, 0
            ),
            "resultados_resolvidos_filtradas": max(
                decisoes_filtradas - pendentes_filtradas, 0
            ),
            "pendentes_enviadas": pendentes_enviadas,
            "pendentes_filtradas": pendentes_filtradas,
            "voids_enviadas": int(enviadas.get("voids") or 0),
            "voids_filtradas": int(filtradas.get("voids") or 0),
            "amostra_enviadas": n_enviadas,
            "amostra_filtradas": n_filtradas,
            "delta_taxa_acerto": (
                round(taxa_enviadas - taxa_filtradas, 4)
                if avaliavel
                and taxa_enviadas is not None
                and taxa_filtradas is not None
                else None
            ),
            "delta_roi": (
                round(roi_enviadas - roi_filtradas, 4)
                if avaliavel
                and roi_enviadas is not None
                and roi_filtradas is not None
                else None
            ),
            "intervalo_delta_taxa_acerto_95": intervalo_acerto,
            "intervalo_delta_roi_95": intervalo_roi,
        }
    return resumo


def comparar_filtros_por_mercado(
    conexao,
    regras_por_mercado,
    fingerprints_por_regra=None,
    amostra_minima=30,
):
    """Compara cada mercado apenas dentro de sua linhagem operacional."""
    fingerprints = dict(fingerprints_por_regra or {})
    resumos = []
    # Vários mercados podem compartilhar exatamente a mesma regra e a mesma
    # linhagem. A consulta base já devolve todos os mercados dessa linhagem;
    # executá-la novamente para cada mercado só repetia a mesma varredura.
    diagnosticos_por_linhagem = {}
    for mercado, regra_versao in (regras_por_mercado or {}).items():
        fingerprint = fingerprints.get(regra_versao)
        chave_linhagem = (regra_versao, fingerprint, int(amostra_minima))
        diagnostico = diagnosticos_por_linhagem.get(chave_linhagem)
        if diagnostico is None:
            diagnostico = comparar_filtro_simulacoes(
                conexao,
                regra_versao=regra_versao,
                regra_fingerprint=fingerprint,
                amostra_minima=amostra_minima,
            )
            diagnosticos_por_linhagem[chave_linhagem] = diagnostico
        comparacao = (diagnostico.get("comparacao") or {}).get(mercado)
        if comparacao is None:
            continue
        resumos.append({
            "mercado": mercado,
            "regra_versao": regra_versao,
            "comparacao": comparacao,
            "enviadas": (diagnostico.get("enviadas") or {}).get(
                mercado, {}
            ),
            "filtradas": (diagnostico.get("filtradas") or {}).get(
                mercado, {}
            ),
        })
    return resumos


def _intervalo_delta_media_95(recentes, base):
    recentes = [float(valor) for valor in recentes]
    base = [float(valor) for valor in base]
    if len(recentes) < 2 or len(base) < 2:
        return None

    def variancia_amostral(valores):
        media = sum(valores) / len(valores)
        return sum((valor - media) ** 2 for valor in valores) / (
            len(valores) - 1
        )

    media_recente = sum(recentes) / len(recentes)
    media_base = sum(base) / len(base)
    delta = media_recente - media_base
    erro_padrao = math.sqrt(
        variancia_amostral(recentes) / len(recentes)
        + variancia_amostral(base) / len(base)
    )
    margem = 1.96 * erro_padrao
    return [round(delta - margem, 4), round(delta + margem, 4)]


def avaliar_drift_simulacoes(
    conexao,
    regra_versao,
    janela_recente=30,
    janela_base=60,
    minimo_recente=20,
    minimo_base=30,
    queda_minima_roi=0.10,
):
    """Detecta deterioração móvel sem reclassificar ou ajustar sinais."""
    linhas = conexao.execute(
        """
        WITH decisoes AS (
          SELECT s.id, s.partida_id, s.mercado, s.criado_em,
                 r.encerrado_em, r.resultado, r.retorno_unidades,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.partida_id, s.mercado, s.regra_versao
                   ORDER BY datetime(s.criado_em), s.id
                 ) AS ordem
          FROM sinais s
          JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE s.regra_versao=?
            AND r.resultado IN ('green','half_green','red','half_red')
            AND EXISTS (
              SELECT 1 FROM entregas_alertas e
              WHERE e.sinal_id=s.id AND e.status='entregue'
                AND e.canal LIKE '%:teste'
                AND e.canal NOT LIKE '%:teste:resultado'
            )
        )
        SELECT *
        FROM decisoes
        WHERE ordem=1
        ORDER BY datetime(encerrado_em), datetime(criado_em), id
        """,
        (regra_versao,),
    ).fetchall()
    grupos = defaultdict(list)
    for linha in linhas:
        item = dict(linha)
        grupos[item["mercado"]].append(item)
        grupos["geral"].append(item)

    mercados = {}
    degradados = []
    for mercado, itens in sorted(grupos.items()):
        recentes = itens[-int(janela_recente):]
        anteriores = itens[
            max(0, len(itens) - int(janela_recente) - int(janela_base)):
            max(0, len(itens) - int(janela_recente))
        ]
        metricas_recentes = calcular_metricas(recentes)
        metricas_base = calcular_metricas(anteriores)
        n_recente = int(metricas_recentes.get("amostra") or 0)
        n_base = int(metricas_base.get("amostra") or 0)
        avaliavel = (
            n_recente >= int(minimo_recente)
            and n_base >= int(minimo_base)
        )
        roi_recente = metricas_recentes.get("roi")
        roi_base = metricas_base.get("roi")
        delta_roi = (
            round(float(roi_recente) - float(roi_base), 4)
            if avaliavel and roi_recente is not None and roi_base is not None
            else None
        )
        intervalo_delta = (
            _intervalo_delta_media_95(
                [item["retorno_unidades"] for item in recentes],
                [item["retorno_unidades"] for item in anteriores],
            )
            if avaliavel else None
        )
        queda_significativa = bool(
            avaliavel
            and roi_recente is not None
            and float(roi_recente) < 0
            and delta_roi is not None
            and delta_roi <= -abs(float(queda_minima_roi))
            and intervalo_delta is not None
            and intervalo_delta[1] < 0
        )
        if queda_significativa:
            estado = "degradado"
            degradados.append(mercado)
        elif avaliavel:
            estado = "estavel"
        else:
            estado = "formando_base"
        mercados[mercado] = {
            "estado": estado,
            "avaliavel": avaliavel,
            "amostra_recente": n_recente,
            "amostra_base": n_base,
            "minimo_recente": int(minimo_recente),
            "minimo_base": int(minimo_base),
            "janela_recente": int(janela_recente),
            "janela_base": int(janela_base),
            "roi_recente": roi_recente,
            "roi_base": roi_base,
            "delta_roi": delta_roi,
            "intervalo_delta_roi_95": intervalo_delta,
            "taxa_acerto_recente": metricas_recentes.get("taxa_acerto"),
            "taxa_acerto_base": metricas_base.get("taxa_acerto"),
            "queda_minima_roi": float(queda_minima_roi),
            "ultima_decisao_id": (
                int(recentes[-1]["id"]) if recentes else None
            ),
            "ultimo_resultado_em": (
                recentes[-1].get("encerrado_em") if recentes else None
            ),
        }
    return {
        "saudavel": not degradados,
        "estado": (
            "degradado" if degradados
            else "avaliavel"
            if any(item["avaliavel"] for item in mercados.values())
            else "formando_base"
        ),
        "regra_versao": regra_versao,
        "mercados_degradados": degradados,
        "mercados": mercados,
        "ajuste_automatico": False,
    }


def avaliar_drift_simulacoes_por_mercado(
    conexao,
    regras_por_mercado,
    **parametros,
):
    """Avalia cada mercado somente contra sua linhagem prospectiva ativa."""
    mercados = {}
    degradados = []
    versoes = {}
    for mercado, regra_versao in sorted(
        (regras_por_mercado or {}).items()
    ):
        parcial = avaliar_drift_simulacoes(
            conexao,
            regra_versao,
            **parametros,
        )
        metricas = (parcial.get("mercados") or {}).get(mercado)
        if metricas is None:
            metricas = {
                "estado": "formando_base",
                "avaliavel": False,
                "amostra_recente": 0,
                "amostra_base": 0,
                "minimo_recente": int(
                    parametros.get("minimo_recente", 20)
                ),
                "minimo_base": int(
                    parametros.get("minimo_base", 30)
                ),
                "janela_recente": int(
                    parametros.get("janela_recente", 30)
                ),
                "janela_base": int(
                    parametros.get("janela_base", 60)
                ),
                "roi_recente": None,
                "roi_base": None,
                "delta_roi": None,
                "intervalo_delta_roi_95": None,
                "taxa_acerto_recente": None,
                "taxa_acerto_base": None,
                "queda_minima_roi": float(
                    parametros.get("queda_minima_roi", 0.10)
                ),
                "ultima_decisao_id": None,
                "ultimo_resultado_em": None,
            }
        else:
            metricas = dict(metricas)
        metricas["regra_versao"] = regra_versao
        mercados[mercado] = metricas
        versoes[mercado] = regra_versao
        if metricas.get("estado") == "degradado":
            degradados.append(mercado)

    avaliavel = any(
        item.get("avaliavel") for item in mercados.values()
    )
    return {
        "saudavel": not degradados,
        "estado": (
            "degradado" if degradados
            else "avaliavel" if avaliavel
            else "formando_base"
        ),
        "regra_versao": "versoes-ativas-por-mercado",
        "regra_versoes_por_mercado": versoes,
        "mercados_degradados": degradados,
        "mercados": mercados,
        "ajuste_automatico": False,
    }
