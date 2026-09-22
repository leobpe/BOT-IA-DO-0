"""Avaliação prospectiva, não operacional, da prioridade sazonal de ligas.

A unidade inferencial é a partida em sua primeira exposição à fila. Decisões
repetidas do mesmo jogo permanecem no diagnóstico, mas não estreitam o
intervalo de confiança. Sinais são vinculados a uma única decisão e somente
oportunidades acionáveis entram no ROI.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from custodia_avaliacao import ESTADO_CONCLUIDO, VERSAO_CUSTODIA
from estatistica import intervalo_wilson


VERSAO = "avaliacao-prioridade-ligas-gols-prospectiva-v3"
CHAVE_ANCORA = "avaliacao_prioridade_ligas_gols:prospectiva_v2:inicio"
CHAVE_ANCORA_LEGADA = "avaliacao_prioridade_ligas_gols:prospectiva_v1:inicio"
AMOSTRA_JOGOS_MINIMA = 100
OPORTUNIDADES_MINIMAS = 30
RESULTADOS_MINIMOS = 30


def _obter_ou_criar_ancora(banco, ancora=None):
    if ancora is not None:
        return str(ancora)
    agora = datetime.now().replace(microsecond=0).isoformat()
    with banco.conexao:
        banco.conexao.execute(
            "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
            (CHAVE_ANCORA, agora),
        )
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_ANCORA,)
    ).fetchone()
    return str(linha["valor"] if linha is not None else agora)


def _instante(valor):
    try:
        atual = datetime.fromisoformat(str(valor or ""))
    except (TypeError, ValueError):
        return None
    if atual.tzinfo is None:
        atual = atual.astimezone()
    return atual.timestamp()


def _mediana(valores):
    numeros = sorted(float(valor) for valor in valores if valor is not None)
    if not numeros:
        return None
    meio = len(numeros) // 2
    if len(numeros) % 2:
        return round(numeros[meio], 3)
    return round((numeros[meio - 1] + numeros[meio]) / 2.0, 3)


def _linhas(banco, ancora, limite):
    return banco.conexao.execute(
        """
        WITH ciclos AS (
            SELECT a.ciclo_em
            FROM auditoria_fila_packball a
            WHERE datetime(a.registrado_em) >= datetime(?)
              AND a.acionavel=1
              AND a.prioridade_liga_gols IS NOT NULL
            GROUP BY a.ciclo_em
            ORDER BY datetime(a.ciclo_em), a.ciclo_em
            LIMIT ?
        ),
        auditoria AS (
            SELECT a.*
            FROM auditoria_fila_packball a
            JOIN ciclos c ON c.ciclo_em=a.ciclo_em
            WHERE datetime(a.registrado_em) >= datetime(?)
              AND a.acionavel=1
              AND a.prioridade_liga_gols IS NOT NULL
        ),
        sinais_gol AS (
            SELECT s.id, s.partida_id, sp.coletado_em, s.status,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM entregas_alertas ea
                       WHERE ea.sinal_id=s.id
                         AND ea.status='entregue'
                         AND ea.canal LIKE '%:aguardar_odd'
                   ) THEN 1 ELSE 0 END AS aviso_aguardar_odd,
                   r.resultado, r.retorno_unidades
            FROM sinais s
            JOIN snapshots sp ON sp.id=s.snapshot_id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.mercado IN ('gol_ft', 'gol_ht', 'proximo_gol')
        ),
        vinculos AS (
            SELECT a.id AS auditoria_id,
                   sg.id, sg.status, sg.aviso_aguardar_odd,
                   sg.resultado, sg.retorno_unidades,
                   ROW_NUMBER() OVER (
                       PARTITION BY sg.id
                       ORDER BY datetime(a.registrado_em), a.id
                   ) AS ordem_vinculo
            FROM auditoria a
            JOIN partidas p ON p.packball_url=a.packball_url
            JOIN sinais_gol sg
              ON sg.partida_id=p.id
             AND datetime(sg.coletado_em) >= datetime(a.ciclo_em)
             AND datetime(sg.coletado_em) <= datetime(a.registrado_em)
        )
        SELECT a.id, a.ciclo_em, a.registrado_em, a.packball_url,
               a.liga, a.posicao, a.processada, a.acionavel,
               a.prioridade_liga_gols,
               COUNT(DISTINCT sg.id) AS candidatos_gol,
               COUNT(DISTINCT CASE
                   WHEN sg.status='aprovado' THEN sg.id END
               ) AS candidatos_gol_aprovados,
               COUNT(DISTINCT CASE
                   WHEN sg.aviso_aguardar_odd=1 THEN sg.id END
               ) AS avisos_aguardar_odd,
               COUNT(DISTINCT CASE
                   WHEN sg.status='aprovado' OR sg.aviso_aguardar_odd=1
                   THEN sg.id END
               ) AS candidatos_gol_acionaveis,
               COUNT(DISTINCT CASE
                   WHEN (sg.status='aprovado' OR sg.aviso_aguardar_odd=1)
                    AND sg.resultado IN (
                        'green', 'half_green', 'void', 'half_red', 'red'
                    )
                    AND sg.retorno_unidades IS NOT NULL
                   THEN sg.id END
               ) AS resultados_gol,
               COALESCE(SUM(CASE
                   WHEN (sg.status='aprovado' OR sg.aviso_aguardar_odd=1)
                    AND sg.resultado IN (
                        'green', 'half_green', 'void', 'half_red', 'red'
                    )
                    AND sg.retorno_unidades IS NOT NULL
                   THEN sg.retorno_unidades ELSE 0 END
               ), 0.0) AS retorno_gol
        FROM auditoria a
        LEFT JOIN vinculos sg
          ON sg.auditoria_id=a.id AND sg.ordem_vinculo=1
        GROUP BY a.id
        ORDER BY datetime(a.ciclo_em), a.id
        """,
        (
            str(ancora), min(max(int(limite), 1), 20000),
            str(ancora),
        ),
    ).fetchall()


def _classificar(linhas):
    por_ciclo = defaultdict(list)
    for linha in linhas:
        por_ciclo[str(linha["ciclo_em"])].append(dict(linha))
    resultado = []
    for grupo in por_ciclo.values():
        maior = max(float(item["prioridade_liga_gols"]) for item in grupo)
        for item in grupo:
            item["grupo"] = (
                "prioridade_maxima"
                if float(item["prioridade_liga_gols"]) == maior
                else "controle_pontuado"
            )
            resultado.append(item)
    return resultado


def _unidades_por_jogo(linhas):
    """Atribui o grupo pela primeira exposição, antes de qualquer desfecho."""
    por_jogo = defaultdict(list)
    for item in linhas:
        por_jogo[str(item["packball_url"])].append(item)
    unidades = []
    for registros in por_jogo.values():
        registros.sort(
            key=lambda item: (
                str(item["ciclo_em"]),
                int(item["id"]),
            )
        )
        primeira = registros[0]
        processados = [
            item for item in registros if int(item["processada"]) == 1
        ]
        grupos = {str(item["grupo"]) for item in registros}
        unidades.append({
            "id": primeira["id"],
            "packball_url": primeira["packball_url"],
            "liga": primeira["liga"],
            "grupo": primeira["grupo"],
            "ciclo_em": primeira["ciclo_em"],
            "registrado_em": primeira["registrado_em"],
            "processada": int(bool(processados)),
            "primeiro_detalhe_em": (
                min(
                    (item["registrado_em"] for item in processados),
                    key=str,
                ) if processados else None
            ),
            "decisoes_brutas": len(registros),
            "ciclos_observados": tuple({
                str(item["ciclo_em"]) for item in registros
            }),
            "mudou_grupo_depois_atribuicao": len(grupos) > 1,
            "candidatos_gol": sum(
                int(item["candidatos_gol"] or 0) for item in registros
            ),
            "candidatos_gol_aprovados": sum(
                int(item["candidatos_gol_aprovados"] or 0)
                for item in registros
            ),
            "avisos_aguardar_odd": sum(
                int(item["avisos_aguardar_odd"] or 0)
                for item in registros
            ),
            "candidatos_gol_acionaveis": sum(
                int(item["candidatos_gol_acionaveis"] or 0)
                for item in registros
            ),
            "resultados_gol": sum(
                int(item["resultados_gol"] or 0) for item in registros
            ),
            "retorno_gol": sum(
                float(item["retorno_gol"] or 0.0) for item in registros
            ),
        })
    return sorted(
        unidades,
        key=lambda item: (str(item["ciclo_em"]), int(item["id"])),
    )


def _resumir_grupo(unidades):
    processadas = [
        item for item in unidades if int(item["processada"]) == 1
    ]
    resultados = sum(int(item["resultados_gol"] or 0) for item in unidades)
    retorno = sum(float(item["retorno_gol"] or 0.0) for item in unidades)
    candidatos = sum(int(item["candidatos_gol"] or 0) for item in unidades)
    jogos_com_candidato = sum(
        int(item["candidatos_gol"] or 0) > 0 for item in unidades
    )
    aprovados = sum(
        int(item["candidatos_gol_aprovados"] or 0) for item in unidades
    )
    avisos = sum(
        int(item["avisos_aguardar_odd"] or 0) for item in unidades
    )
    oportunidades = sum(
        int(item["candidatos_gol_acionaveis"] or 0) for item in unidades
    )
    jogos_com_oportunidade = sum(
        int(item["candidatos_gol_acionaveis"] or 0) > 0
        for item in unidades
    )
    total = len(unidades)
    ciclos = {
        ciclo
        for item in unidades
        for ciclo in item["ciclos_observados"]
    }
    return {
        "decisoes": total,
        "decisoes_brutas": sum(
            int(item["decisoes_brutas"]) for item in unidades
        ),
        "unidades_independentes": total,
        "unidade_independente": "primeira_exposicao_da_partida",
        "ciclos": len(ciclos),
        "jogos_distintos": total,
        "processadas": len(processadas),
        "taxa_processamento": (
            round(len(processadas) / total, 4) if total else None
        ),
        "candidatos_gol": candidatos,
        "detalhes_com_candidato_gol": jogos_com_candidato,
        "jogos_com_candidato_gol": jogos_com_candidato,
        "candidatos_gol_aprovados": aprovados,
        "avisos_aguardar_odd": avisos,
        "oportunidades_gol_acionaveis": oportunidades,
        "detalhes_com_oportunidade_gol": jogos_com_oportunidade,
        "jogos_com_oportunidade_gol": jogos_com_oportunidade,
        "taxa_captura_oportunidade_por_jogo_exposto": (
            round(jogos_com_oportunidade / total, 4) if total else None
        ),
        "taxa_oportunidade_entre_jogos_processados": (
            round(jogos_com_oportunidade / len(processadas), 4)
            if processadas else None
        ),
        "rendimento_candidato_por_detalhe": (
            round(candidatos / len(processadas), 4)
            if processadas else None
        ),
        "rendimento_aprovado_por_detalhe": (
            round(aprovados / len(processadas), 4)
            if processadas else None
        ),
        "rendimento_oportunidade_por_detalhe": (
            round(oportunidades / len(processadas), 4)
            if processadas else None
        ),
        "jogos_com_mudanca_de_grupo_apos_atribuicao": sum(
            bool(item["mudou_grupo_depois_atribuicao"])
            for item in unidades
        ),
        "resultados_gol": resultados,
        "retorno_unidades": round(retorno, 4),
        "roi_resultados": (
            round(retorno / resultados, 4) if resultados else None
        ),
    }


def _latencias_primeiro_detalhe(unidades):
    latencias = defaultdict(list)
    censurados = defaultdict(int)
    for unidade in unidades:
        grupo = unidade["grupo"]
        inicio = _instante(unidade["ciclo_em"])
        processado_em = _instante(unidade["primeiro_detalhe_em"])
        if inicio is None or processado_em is None:
            censurados[grupo] += 1
            continue
        latencias[grupo].append(max(processado_em - inicio, 0.0))
    return {
        grupo: {
            "tempo_mediano_primeiro_detalhe_segundos": _mediana(
                latencias.get(grupo, [])
            ),
            "jogos_com_detalhe": len(latencias.get(grupo, [])),
            "jogos_ainda_sem_detalhe": int(censurados.get(grupo, 0)),
        }
        for grupo in ("prioridade_maxima", "controle_pontuado")
    }


def avaliar_prioridade_ligas_gols(
    banco, *, ancora_prospectiva=None, limite=10000,
):
    """Mede captura e desfechos; nunca reordena fila ou altera sinal."""
    ancora_pre_registrada = ancora_prospectiva is None
    ancora = _obter_ou_criar_ancora(banco, ancora_prospectiva)
    itens = _classificar(_linhas(banco, ancora, limite))
    unidades = _unidades_por_jogo(itens)
    por_grupo = {
        grupo: _resumir_grupo([
            item for item in unidades if item["grupo"] == grupo
        ])
        for grupo in ("prioridade_maxima", "controle_pontuado")
    }
    alta = por_grupo["prioridade_maxima"]
    controle = por_grupo["controle_pontuado"]
    alta_jogos = alta["jogos_distintos"]
    controle_jogos = controle["jogos_distintos"]
    alta_oportunidades = alta["jogos_com_oportunidade_gol"]
    controle_oportunidades = controle["jogos_com_oportunidade_gol"]
    intervalo_alta = intervalo_wilson(
        alta_oportunidades, alta_jogos
    )
    intervalo_controle = intervalo_wilson(
        controle_oportunidades, controle_jogos
    )
    intervalo_delta = (
        [
            round(intervalo_alta[0] - intervalo_controle[1], 4),
            round(intervalo_alta[1] - intervalo_controle[0], 4),
        ]
        if intervalo_alta and intervalo_controle else None
    )
    rendimento_alta = alta["taxa_captura_oportunidade_por_jogo_exposto"]
    rendimento_controle = controle[
        "taxa_captura_oportunidade_por_jogo_exposto"
    ]
    delta = (
        round(rendimento_alta - rendimento_controle, 4)
        if rendimento_alta is not None and rendimento_controle is not None
        else None
    )
    amostras_suficientes = (
        alta_jogos >= AMOSTRA_JOGOS_MINIMA
        and controle_jogos >= AMOSTRA_JOGOS_MINIMA
    )
    oportunidades_suficientes = (
        alta_oportunidades >= OPORTUNIDADES_MINIMAS
        and controle_oportunidades >= OPORTUNIDADES_MINIMAS
    )
    pronto = (
        ancora_pre_registrada
        and amostras_suficientes
        and oportunidades_suficientes
    )
    vantagem_captura = bool(
        pronto and intervalo_delta and intervalo_delta[0] > 0.0
    )
    regressao_captura = bool(
        pronto and intervalo_delta and intervalo_delta[1] < 0.0
    )
    resultados_suficientes = (
        alta["resultados_gol"] >= RESULTADOS_MINIMOS
        and controle["resultados_gol"] >= RESULTADOS_MINIMOS
    )
    return {
        "versao": VERSAO,
        "custodia_execucao_versao": VERSAO_CUSTODIA,
        "estado_execucao": ESTADO_CONCLUIDO,
        "modo": "avaliacao_prospectiva",
        "ancora_prospectiva_em": ancora,
        "ancora_metodologia_v2_pre_registrada": ancora_pre_registrada,
        "criterio_grupo": (
            "grupo_da_primeira_exposicao_da_partida; prioridade_maxima_"
            "do_ciclo_vs_demais_ligas_pontuadas"
        ),
        "criterio_vinculo_sinal": (
            "cada_sinal_vinculado_a_uma_unica_decisao_da_fila"
        ),
        "unidade_independente": "primeira_exposicao_da_partida",
        "decisoes": len(unidades),
        "decisoes_brutas": len(itens),
        "unidades_independentes": len(unidades),
        "ciclos": len({item["ciclo_em"] for item in itens}),
        "por_grupo": por_grupo,
        "latencia_primeiro_detalhe": _latencias_primeiro_detalhe(unidades),
        "delta_rendimento_oportunidade_por_detalhe": delta,
        "delta_taxa_captura_por_jogo_exposto": delta,
        "ic95_delta_rendimento_oportunidade": intervalo_delta,
        "ic95_delta_taxa_captura_por_jogo_exposto": intervalo_delta,
        "amostras_independentes_suficientes": amostras_suficientes,
        "oportunidades_independentes_suficientes": oportunidades_suficientes,
        "pronto_para_revisao_captura": pronto,
        "resultados_suficientes_para_roi": resultados_suficientes,
        "vantagem_captura_comprovada": vantagem_captura,
        "regressao_captura_comprovada": regressao_captura,
        "faltam_jogos_prioridade": max(
            AMOSTRA_JOGOS_MINIMA - alta_jogos, 0
        ),
        "faltam_jogos_controle": max(
            AMOSTRA_JOGOS_MINIMA - controle_jogos, 0
        ),
        "faltam_oportunidades_prioridade": max(
            OPORTUNIDADES_MINIMAS - alta_oportunidades, 0
        ),
        "faltam_oportunidades_controle": max(
            OPORTUNIDADES_MINIMAS - controle_oportunidades, 0
        ),
        "faltam_processadas_prioridade": max(
            AMOSTRA_JOGOS_MINIMA - alta_jogos, 0
        ),
        "faltam_processadas_controle": max(
            AMOSTRA_JOGOS_MINIMA - controle_jogos, 0
        ),
        "aplicacao_sinais": False,
        "altera_prioridade": False,
        "promocao_automatica": False,
        "recomendacao": (
            "diagnostico_pre_ancora_v2_sem_poder_decisorio"
            if not ancora_pre_registrada else
            "revisar_vantagem_sem_promocao_automatica"
            if vantagem_captura else
            "revisar_regressao_sem_rollback_automatico"
            if regressao_captura else
            "continuar_coleta_prospectiva"
        ),
    }
