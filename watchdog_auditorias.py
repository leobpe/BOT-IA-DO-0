"""Auditorias de qualidade e verificacoes de saude do watchdog.

Funil recente, features temporais, integridade do Telegram, notificacoes
operacionais, tendencia de armazenamento e o trabalhador de acompanhamento
de odd. Sao leituras de estado que devolvem diagnostico: nenhuma envia
alerta, altera politica ou grava estado operacional.

Extraido de watchdog.py, que reexporta estes nomes.
"""

import json
import os
from clv_pos_alerta import (
    MERCADOS_CLV_API_RAPIDA,
    MERCADOS_CLV_SOMENTE_SNAPSHOT,
    VERSAO_COLETA_CLV_API_RAPIDA,
)
from datetime import (
    datetime,
    timedelta,
)
from motor_sinais import (
    VERSAO_FEATURES,
    VERSAO_REGRAS,
)
from pathlib import Path
from statistics import median


JANELA_FUNIL_MINUTOS = 30
AMOSTRA_MINIMA_FUNIL = 10
AMOSTRA_MINIMA_FEATURES = 10


def atualizar_tendencia_armazenamento(
    atual,
    anterior=None,
    agora=None,
    intervalo_minutos=60,
    janela_horas=72,
    minimo_horas=6,
    horizonte_alerta_dias=30,
    reducao_material_minima_mb=1024,
    reducao_material_fracao=0.10,
):
    """Estima esgotamento sem reagir a oscilações curtas do arquivo WAL."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    resultado = dict(atual or {})
    anterior = anterior or {}
    metrica_versao = resultado.get("metrica_versao")
    if (
        metrica_versao
        and anterior.get("metrica_versao") != metrica_versao
    ):
        anterior = {}
    historico = []
    limite_historico = agora - timedelta(hours=float(janela_horas))
    for amostra in anterior.get("historico") or []:
        try:
            instante = datetime.fromisoformat(amostra["em"])
            total = float(amostra["total_mb"])
        except (KeyError, TypeError, ValueError):
            continue
        if limite_historico <= instante <= agora:
            historico.append({
                "em": instante.replace(microsecond=0).isoformat(),
                "total_mb": round(total, 1),
            })
    historico.sort(key=lambda item: item["em"])

    try:
        total_atual = float(resultado["total_mb"])
        livre_atual = float(resultado["livre_mb"])
    except (KeyError, TypeError, ValueError):
        resultado.update({
            "historico": historico,
            "tendencia_avaliavel": False,
            "crescimento_mb_dia": None,
            "dias_ate_limite": None,
        })
        return resultado

    # Uma compactação ou retenção verificada muda o patamar físico do
    # armazenamento. Manter todos os pontos anteriores depois de uma queda
    # grande faria o estimador interpretar espaço já recuperado como se ainda
    # estivesse crescendo. Rebasa somente quedas materiais; oscilações normais
    # do WAL permanecem no mesmo histórico.
    if historico:
        total_anterior = float(historico[-1]["total_mb"])
        reducao_mb = total_anterior - total_atual
        limiar_reducao = max(
            float(reducao_material_minima_mb),
            total_anterior * float(reducao_material_fracao),
        )
        if reducao_mb >= limiar_reducao:
            resultado["rebase_tendencia"] = True
            resultado["motivo_rebase_tendencia"] = (
                "reducao_material_armazenamento"
            )
            resultado["reducao_material_mb"] = round(reducao_mb, 1)
            resultado["historico_antes_rebase"] = {
                "amostras": len(historico),
                "primeiro_em": historico[0]["em"],
                "ultimo_em": historico[-1]["em"],
                "ultimo_total_mb": round(total_anterior, 1),
            }
            historico = []

    ultimo_em = (
        datetime.fromisoformat(historico[-1]["em"])
        if historico else None
    )
    if (
        ultimo_em is None
        or (agora - ultimo_em).total_seconds()
        >= float(intervalo_minutos) * 60
    ):
        historico.append({
            "em": agora.isoformat(),
            "total_mb": round(total_atual, 1),
        })

    resultado["historico"] = historico
    resultado["tendencia_avaliavel"] = False
    resultado["crescimento_mb_dia"] = None
    resultado["dias_ate_limite"] = None
    if not historico:
        return resultado

    inicio = datetime.fromisoformat(historico[0]["em"])
    horas = (agora - inicio).total_seconds() / 3600
    if horas < float(minimo_horas):
        return resultado

    crescimento_endpoint = (
        (total_atual - float(historico[0]["total_mb"]))
        / horas * 24
    )
    # Backups diarios, periodicos e pre-migracao entram no disco em degraus.
    # Usar somente o primeiro e o ultimo ponto transforma um backup isolado
    # em uma taxa permanente e pode fechar toda a operacao por um falso
    # esgotamento. A mediana das inclinacoes entre todos os pares (estimador
    # de Theil-Sen) conserva crescimento sustentado, mas e resistente a um
    # salto ou a uma limpeza pontual. Com apenas dois pontos, preservamos o
    # calculo historico ate existir amostra suficiente para a estimativa
    # robusta.
    inclinacoes = []
    intervalo_minimo_horas = max(float(intervalo_minutos) / 60.0, 1 / 60)
    for indice, primeiro in enumerate(historico):
        instante_primeiro = datetime.fromisoformat(primeiro["em"])
        total_primeiro = float(primeiro["total_mb"])
        for segundo in historico[indice + 1:]:
            instante_segundo = datetime.fromisoformat(segundo["em"])
            intervalo_horas = (
                instante_segundo - instante_primeiro
            ).total_seconds() / 3600
            if intervalo_horas < intervalo_minimo_horas:
                continue
            inclinacoes.append(
                (float(segundo["total_mb"]) - total_primeiro)
                / intervalo_horas * 24
            )
    usar_estimador_robusto = bool(
        len(historico) >= 3 and inclinacoes
    )
    crescimento_estimado = (
        median(inclinacoes)
        if usar_estimador_robusto else crescimento_endpoint
    )
    crescimento = max(crescimento_estimado, 0.0)
    resultado["metodo_tendencia"] = (
        "theil_sen_mediana_pares_v1"
        if usar_estimador_robusto else "primeiro_ultimo_ponto"
    )
    resultado["amostras_tendencia"] = len(historico)
    resultado["pares_tendencia"] = len(inclinacoes)
    resultado["crescimento_endpoint_mb_dia"] = round(
        max(crescimento_endpoint, 0.0), 1
    )
    resultado["tendencia_avaliavel"] = True
    resultado["crescimento_mb_dia"] = round(crescimento, 1)
    if crescimento <= 0:
        return resultado

    reserva = float(resultado.get("limite_livre_mb", 0) or 0)
    dias = max(livre_atual - reserva, 0.0) / crescimento
    resultado["dias_ate_limite"] = round(dias, 1)
    if dias < float(horizonte_alerta_dias):
        motivos = list(resultado.get("motivos") or [])
        if "crescimento_armazenamento_critico" not in motivos:
            motivos.append("crescimento_armazenamento_critico")
        resultado["motivos"] = motivos
        resultado["saudavel"] = False
    return resultado

def auditar_funil_recente(
    conexao,
    agora=None,
    regra_versao=VERSAO_REGRAS,
    janela_minutos=JANELA_FUNIL_MINUTOS,
):
    regra_versoes = (
        (regra_versao,)
        if isinstance(regra_versao, str)
        else tuple(dict.fromkeys(regra_versao or ()))
    )
    if not regra_versoes:
        regra_versoes = (VERSAO_REGRAS,)
    marcadores_versoes = ",".join("?" for _ in regra_versoes)
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite = (agora - timedelta(minutes=janela_minutos)).isoformat()
    inicio_versao = conexao.execute(
        f"""
        SELECT MIN(sn.coletado_em)
        FROM sinais s
        JOIN snapshots sn ON sn.id=s.snapshot_id
        WHERE s.regra_versao IN ({marcadores_versoes})
        """,
        regra_versoes,
    ).fetchone()[0]
    origem_inicio_versao = "primeiro_candidato"
    if inicio_versao is None:
        inicio_versao = conexao.execute(
            f"""
            SELECT MIN(atualizado_em) FROM calibracoes
            WHERE regra_versao IN ({marcadores_versoes})
            """,
            regra_versoes,
        ).fetchone()[0]
        origem_inicio_versao = "calibracao_inicial"
    transicao_versao = bool(
        inicio_versao
        and datetime.fromisoformat(inicio_versao)
        > datetime.fromisoformat(limite)
    )
    if transicao_versao:
        limite = inicio_versao
    linha = conexao.execute(
        f"""
        WITH base AS (
            SELECT id, qualidade_json, contexto_api_json
            FROM snapshots
            WHERE datetime(coletado_em) >= datetime(?)
              AND COALESCE(LOWER(status), '') NOT LIKE '%finaliz%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%encerrad%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%finished%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%full time%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%cancelad%'
              AND COALESCE(LOWER(status), '') NOT LIKE '%anulad%'
              AND COALESCE(LOWER(status), '') NOT IN ('ft', 'wo')
        ),
        recentes AS (
            SELECT id
            FROM base
            WHERE COALESCE(
                json_extract(qualidade_json, '$.versao'), ''
            ) <> 'recuperacao-packball-v1'
              AND COALESCE(
                json_extract(qualidade_json, '$.versao'), ''
              ) NOT LIKE 'resultado-%'
              AND COALESCE(
                  json_extract(
                      contexto_api_json, '$.sem_detalhe_packball'
                  ), 0
              ) <> 1
        )
        SELECT
            COUNT(*) AS snapshots,
            (
                SELECT COUNT(*) FROM base
                WHERE COALESCE(
                    json_extract(qualidade_json, '$.versao'), ''
                ) = 'recuperacao-packball-v1'
            ) AS snapshots_recuperacao_excluidos,
            (
                SELECT COUNT(*) FROM base
                WHERE COALESCE(
                    json_extract(qualidade_json, '$.versao'), ''
                ) LIKE 'resultado-%'
            ) AS snapshots_liquidacao_excluidos,
            (
                SELECT COUNT(*) FROM base
                WHERE COALESCE(
                    json_extract(
                        contexto_api_json, '$.sem_detalhe_packball'
                    ), 0
                ) = 1
            ) AS snapshots_sombra_multifonte_excluidos,
            SUM(EXISTS (
                SELECT 1 FROM sinais s
                WHERE s.snapshot_id=recentes.id
                  AND s.regra_versao IN ({marcadores_versoes})
            )) AS com_candidatos,
            SUM(EXISTS (
                SELECT 1 FROM odds o
                WHERE o.snapshot_id=recentes.id AND o.tipo='ao_vivo'
                  AND CASE
                    WHEN json_valid(o.estrutura_json) THEN (
                        COALESCE(json_array_length(json_extract(
                            o.estrutura_json, '$.ofertas'
                        )), 0) > 0
                        OR COALESCE(json_array_length(json_extract(
                            o.estrutura_json, '$.ofertas_ht'
                        )), 0) > 0
                        OR json_extract(
                            o.estrutura_json, '$.selecoes.casa'
                        ) IS NOT NULL
                        OR json_extract(
                            o.estrutura_json, '$.selecoes.visitante'
                        ) IS NOT NULL
                    ) ELSE 0
                  END
            )) AS com_odds_estruturadas
        FROM recentes
        """,
        (limite, *regra_versoes),
    ).fetchone()
    snapshots = int(linha["snapshots"] or 0)
    candidatos = int(linha["com_candidatos"] or 0)
    odds = int(linha["com_odds_estruturadas"] or 0)
    recuperacao_excluidos = int(
        linha["snapshots_recuperacao_excluidos"] or 0
    )
    liquidacao_excluidos = int(
        linha["snapshots_liquidacao_excluidos"] or 0
    )
    sombra_multifonte_excluidos = int(
        linha["snapshots_sombra_multifonte_excluidos"] or 0
    )
    cobertura_candidatos = candidatos / snapshots if snapshots else None
    cobertura_odds = odds / snapshots if snapshots else None
    if snapshots == 0:
        estado = "sem_jogos_recentes"
    elif snapshots < AMOSTRA_MINIMA_FUNIL:
        estado = "amostra_operacional_insuficiente"
    else:
        estado = "avaliavel"
    return {
        "estado": estado,
        "janela_minutos": int(janela_minutos),
        "inicio_janela": limite,
        "transicao_versao": transicao_versao,
        "origem_inicio_versao": origem_inicio_versao,
        "regra_versoes": list(regra_versoes),
        "amostra_minima": AMOSTRA_MINIMA_FUNIL,
        "snapshots_ao_vivo": snapshots,
        "snapshots_com_candidatos": candidatos,
        "snapshots_com_odds_estruturadas": odds,
        "snapshots_recuperacao_excluidos": recuperacao_excluidos,
        "snapshots_liquidacao_excluidos": liquidacao_excluidos,
        "snapshots_sombra_multifonte_excluidos": (
            sombra_multifonte_excluidos
        ),
        "cobertura_candidatos": (
            round(cobertura_candidatos, 4)
            if cobertura_candidatos is not None else None
        ),
        "cobertura_odds_estruturadas": (
            round(cobertura_odds, 4) if cobertura_odds is not None else None
        ),
    }

def auditar_features_temporais(
    conexao,
    agora=None,
    regra_versao=VERSAO_REGRAS,
    versao_features=VERSAO_FEATURES,
    janela_minutos=JANELA_FUNIL_MINUTOS,
    amostra_minima=AMOSTRA_MINIMA_FEATURES,
):
    """Confere se candidatos novos preservam o vetor temporal versionado."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite = (agora - timedelta(minutes=janela_minutos)).isoformat()
    inicio_features = conexao.execute(
        """
        SELECT MIN(criado_em) FROM sinais
        WHERE regra_versao=? AND json_valid(features_json)
          AND json_extract(features_json, '$.schema_versao')=?
        """,
        (regra_versao, versao_features),
    ).fetchone()[0]
    transicao = bool(
        inicio_features
        and datetime.fromisoformat(inicio_features)
        > datetime.fromisoformat(limite)
    )
    if transicao:
        limite = inicio_features
    linhas = conexao.execute(
        """
        SELECT snapshot_id, mercado, features_json
        FROM sinais
        WHERE regra_versao=? AND datetime(criado_em) >= datetime(?)
        ORDER BY snapshot_id, id
        """,
        (regra_versao, limite),
    ).fetchall()
    por_snapshot = {}
    candidatos_validos = 0
    janelas_disponiveis = {str(item): 0 for item in (5, 10, 15)}
    duracoes_medidas = {str(item): 0 for item in (5, 10, 15)}
    features_representativas = {}

    def janela_valida(janela):
        if not isinstance(janela, dict) or not isinstance(
            janela.get("disponivel"), bool
        ):
            return False
        if not janela["disponivel"]:
            return True
        try:
            duracao_bruta = janela.get("duracao_real_minutos")
            duracao = (
                float(duracao_bruta) if duracao_bruta is not None else None
            )
            if duracao is not None and duracao <= 0:
                return False
            for nome in ("chutes", "escanteios"):
                par = janela.get(nome)
                total = janela.get(f"{nome}_total")
                taxa = janela.get(f"{nome}_por_minuto")
                taxas_lados = janela.get(f"{nome}_por_minuto_lados")
                if par is None:
                    if total is not None or taxa is not None or taxas_lados is not None:
                        return False
                    continue
                if not isinstance(par, list) or len(par) != 2:
                    return False
                valores = [float(par[0]), float(par[1])]
                if total is None or abs(float(total) - sum(valores)) > 0.001:
                    return False
                if duracao is None:
                    if taxa is not None or taxas_lados is not None:
                        return False
                    continue
                if abs(float(taxa) - sum(valores) / duracao) > 0.001:
                    return False
                if not isinstance(taxas_lados, list) or len(taxas_lados) != 2:
                    return False
                if any(
                    abs(float(taxas_lados[indice]) - valores[indice] / duracao)
                    > 0.001
                    for indice in (0, 1)
                ):
                    return False
        except (TypeError, ValueError, ZeroDivisionError):
            return False
        return True

    for linha in linhas:
        valido = False
        features = None
        try:
            features = json.loads(linha["features_json"] or "{}")
            janelas = features.get("janelas")
            valido = bool(
                isinstance(features, dict)
                and features.get("schema_versao") == versao_features
                and features.get("mercado") == linha["mercado"]
                and isinstance(janelas, dict)
                and all(
                    janela_valida(janelas.get(str(item)))
                    for item in (5, 10, 15)
                )
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            valido = False
        por_snapshot.setdefault(linha["snapshot_id"], []).append(valido)
        if valido:
            candidatos_validos += 1
            features_representativas.setdefault(
                linha["snapshot_id"], features
            )
    for features in features_representativas.values():
        for item in (5, 10, 15):
            janela = features["janelas"][str(item)]
            if janela.get("disponivel"):
                janelas_disponiveis[str(item)] += 1
            if janela.get("duracao_real_minutos") is not None:
                duracoes_medidas[str(item)] += 1
    snapshots = len(por_snapshot)
    snapshots_integros = sum(all(itens) for itens in por_snapshot.values())
    total = len(linhas)
    cobertura = candidatos_validos / total if total else None
    cobertura_snapshots = snapshots_integros / snapshots if snapshots else None
    if total == 0:
        estado = "sem_candidatos_recentes"
    elif inicio_features is None:
        estado = "aguardando_primeiro_registro"
    elif snapshots < int(amostra_minima):
        estado = "amostra_operacional_insuficiente"
    else:
        estado = "avaliavel"
    saudavel = not (
        inicio_features is not None and candidatos_validos != total
    )
    return {
        "saudavel": saudavel,
        "estado": estado,
        "schema_versao": versao_features,
        "janela_minutos": int(janela_minutos),
        "inicio_janela": limite,
        "inicio_schema": inicio_features,
        "transicao_schema": transicao,
        "amostra_minima": int(amostra_minima),
        "candidatos": total,
        "candidatos_validos": candidatos_validos,
        "snapshots": snapshots,
        "snapshots_integros": snapshots_integros,
        "cobertura": round(cobertura, 4) if cobertura is not None else None,
        "cobertura_snapshots": (
            round(cobertura_snapshots, 4)
            if cobertura_snapshots is not None else None
        ),
        "janelas_disponiveis": janelas_disponiveis,
        "duracoes_medidas": duracoes_medidas,
    }

def auditar_integridade_telegram(
    conexao, agora=None, tolerancia_minutos=5, erro_minutos=10,
    incerto_minutos=2,
):
    """Confere a cadeia persistida entre sinal, resultado e Telegram."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite_aviso = (
        agora - timedelta(minutes=tolerancia_minutos)
    ).isoformat()
    limite_erro = (agora - timedelta(minutes=erro_minutos)).isoformat()
    limite_incerto = (
        agora - timedelta(minutes=incerto_minutos)
    ).isoformat()
    resultados_sem_aviso_linha = conexao.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE
                   WHEN faltante.canal NOT LIKE '%:%' THEN 1 ELSE 0
               END), 0) AS oficiais,
               COALESCE(SUM(CASE
                   WHEN faltante.canal LIKE '%:teste' THEN 1 ELSE 0
               END), 0) AS analises
        FROM (
            SELECT DISTINCT r.sinal_id, origem.canal
            FROM resultados_sinais r
            JOIN entregas_alertas origem ON origem.sinal_id=r.sinal_id
             AND origem.status='entregue'
             AND (
                 origem.canal NOT LIKE '%:%'
                 OR origem.canal LIKE '%:teste'
             )
            WHERE datetime(r.encerrado_em) <= datetime(?)
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas aviso
                  WHERE aviso.sinal_id=r.sinal_id
                    AND aviso.canal=origem.canal || ':resultado'
                    AND aviso.status='entregue'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM revisoes_resultados rev
                  WHERE rev.sinal_id=r.sinal_id
                    AND rev.notificacao_status='entregue'
              )
        ) AS faltante
        """,
        (limite_aviso,),
    ).fetchone()
    resultados_sem_aviso = int(resultados_sem_aviso_linha[0] or 0)
    resultados_oficiais_sem_aviso = int(
        resultados_sem_aviso_linha[1] or 0
    )
    resultados_analise_sem_aviso = int(
        resultados_sem_aviso_linha[2] or 0
    )
    avisos_sem_resultado = conexao.execute(
        """
        SELECT COUNT(*)
        FROM entregas_alertas aviso
        LEFT JOIN resultados_sinais r ON r.sinal_id=aviso.sinal_id
        WHERE aviso.status='entregue'
          AND aviso.canal LIKE '%:resultado'
          AND r.sinal_id IS NULL
        """
    ).fetchone()[0]
    erros_persistentes = conexao.execute(
        """
        SELECT COUNT(*) FROM entregas_alertas
        WHERE status='erro' AND datetime(tentado_em) <= datetime(?)
        """,
        (limite_erro,),
    ).fetchone()[0]
    correcoes_pendentes = conexao.execute(
        """
        SELECT COUNT(*)
        FROM revisoes_resultados rev
        JOIN entregas_alertas origem
          ON origem.sinal_id=rev.sinal_id
         AND origem.status='entregue'
         AND origem.canal LIKE '%:teste'
         AND origem.canal NOT LIKE '%:teste:resultado'
        WHERE rev.notificacao_status<>'entregue'
          AND datetime(rev.revisado_em) <= datetime(?)
        """,
        (limite_aviso,),
    ).fetchone()[0]
    resultados_duplicados = conexao.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT sinal_id
            FROM entregas_alertas
            WHERE status='entregue' AND canal LIKE '%:resultado'
            GROUP BY sinal_id HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    bloqueios_gateway = conexao.execute(
        """
        SELECT COUNT(*) FROM entregas_alertas
        WHERE status='bloqueado' AND canal='gateway:oficial'
          AND datetime(tentado_em) >= datetime(?, '-24 hours')
        """,
        (agora.isoformat(),),
    ).fetchone()[0]
    envios_incertos_linha = conexao.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE
                   WHEN pendente.canal NOT LIKE '%:%' THEN 1 ELSE 0
               END), 0) AS oficiais,
               COALESCE(SUM(CASE
                   WHEN pendente.canal LIKE '%:teste%' THEN 1 ELSE 0
               END), 0) AS analises
        FROM entregas_alertas pendente
        WHERE pendente.status IN ('enviando', 'tentando', 'incerto')
          AND (
              pendente.status='incerto'
              OR datetime(pendente.tentado_em) <= datetime(?)
          )
          AND NOT EXISTS (
              SELECT 1 FROM entregas_alertas final
              WHERE final.sinal_id=pendente.sinal_id
                AND final.canal=pendente.canal
                AND final.status IN (
                    'entregue', 'erro', 'recuperado', 'cancelado',
                    'expirado'
                )
                AND datetime(final.tentado_em)
                    >= datetime(pendente.tentado_em)
          )
          AND NOT EXISTS (
              SELECT 1 FROM entregas_alertas posterior
              WHERE posterior.sinal_id=pendente.sinal_id
                AND posterior.canal=pendente.canal
                AND posterior.status IN ('enviando', 'tentando', 'incerto')
                AND (
                    datetime(posterior.tentado_em)
                        > datetime(pendente.tentado_em)
                    OR (
                        datetime(posterior.tentado_em)
                            = datetime(pendente.tentado_em)
                        AND posterior.id > pendente.id
                    )
                )
          )
        """,
        (limite_incerto,),
    ).fetchone()
    envios_incertos = int(envios_incertos_linha[0] or 0)
    envios_oficiais_incertos = int(envios_incertos_linha[1] or 0)
    envios_analise_incertos = int(envios_incertos_linha[2] or 0)
    confirmacoes_telegram_invalidas = conexao.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT provedor_destino_id AS destino,
                   provedor_mensagem_id AS mensagem_id,
                   confirmacao_json AS confirmacao
            FROM entregas_alertas
            WHERE status='entregue' AND provedor='telegram'
            UNION ALL
            SELECT notificacao_destino_id,
                   notificacao_mensagem_id,
                   notificacao_confirmacao_json
            FROM revisoes_resultados
            WHERE notificacao_status='entregue'
              AND notificacao_provedor='telegram'
        ) AS provas
        WHERE destino IS NULL OR TRIM(destino)=''
           OR CASE
                WHEN json_valid(confirmacao) THEN
                    COALESCE(json_extract(confirmacao, '$.ok'), 0) <> 1
                    OR CASE
                         WHEN COALESCE(
                             json_extract(confirmacao, '$.edicao'), 0
                         ) = 1 THEN
                             mensagem_id IS NOT NULL
                             OR TRIM(CAST(COALESCE(
                                 json_extract(
                                     confirmacao, '$.message_id_origem'
                                 ), ''
                             ) AS TEXT)) = ''
                         ELSE
                             COALESCE(
                                 json_extract(confirmacao, '$.provedor'), ''
                             ) <> 'telegram'
                             OR
                             mensagem_id IS NULL
                             OR TRIM(mensagem_id)=''
                             OR CAST(COALESCE(
                                 json_extract(
                                     confirmacao, '$.message_id'
                                 ), ''
                             ) AS TEXT) <> CAST(mensagem_id AS TEXT)
                       END
                ELSE 1
              END
        """
    ).fetchone()[0]
    confirmacoes_telegram_duplicadas = conexao.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT destino, mensagem_id
            FROM (
                SELECT provedor_destino_id AS destino,
                       provedor_mensagem_id AS mensagem_id
                FROM entregas_alertas
                WHERE status='entregue' AND provedor='telegram'
                UNION ALL
                SELECT notificacao_destino_id,
                       notificacao_mensagem_id
                FROM revisoes_resultados
                WHERE notificacao_status='entregue'
                  AND notificacao_provedor='telegram'
            ) AS provas
            WHERE destino IS NOT NULL AND mensagem_id IS NOT NULL
            GROUP BY destino, mensagem_id
            HAVING COUNT(*) > 1
        ) AS duplicadas
        """
    ).fetchone()[0]
    confirmacoes_telegram_validas = conexao.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT provedor_mensagem_id AS mensagem_id
            FROM entregas_alertas
            WHERE status='entregue' AND provedor='telegram'
            UNION ALL
            SELECT notificacao_mensagem_id
            FROM revisoes_resultados
            WHERE notificacao_status='entregue'
              AND notificacao_provedor='telegram'
        ) AS provas
        WHERE mensagem_id IS NOT NULL
        """
    ).fetchone()[0]
    entregas_telegram_legadas_sem_prova = conexao.execute(
        """
        SELECT (
            SELECT COUNT(*) FROM entregas_alertas
            WHERE status='entregue' AND provedor IS NULL
        ) + (
            SELECT COUNT(*) FROM revisoes_resultados
            WHERE notificacao_status='entregue'
              AND notificacao_provedor IS NULL
        )
        """
    ).fetchone()[0]
    valores = {
        "resultados_sem_aviso": resultados_sem_aviso,
        "avisos_sem_resultado": int(avisos_sem_resultado or 0),
        "erros_persistentes": int(erros_persistentes or 0),
        "correcoes_pendentes": int(correcoes_pendentes or 0),
        "resultados_duplicados": int(resultados_duplicados or 0),
        "bloqueios_gateway_24h": int(bloqueios_gateway or 0),
        "envios_incertos": int(envios_incertos or 0),
        "confirmacoes_telegram_invalidas": int(
            confirmacoes_telegram_invalidas or 0
        ),
        "confirmacoes_telegram_duplicadas": int(
            confirmacoes_telegram_duplicadas or 0
        ),
    }
    valores_operacionais = {
        **valores,
        # Uma análise já liquidada com entrega ambígua exige conferência,
        # mas não invalida o dado esportivo nem deve bloquear novas análises.
        "resultados_sem_aviso": resultados_oficiais_sem_aviso,
        "envios_incertos": envios_oficiais_incertos,
    }
    return {
        "saudavel": not any(valores.values()),
        "saudavel_operacional": not any(valores_operacionais.values()),
        "tolerancia_minutos": int(tolerancia_minutos),
        "erro_minutos": int(erro_minutos),
        "incerto_minutos": int(incerto_minutos),
        "confirmacoes_telegram_validas": int(
            confirmacoes_telegram_validas or 0
        ),
        "entregas_telegram_legadas_sem_prova": int(
            entregas_telegram_legadas_sem_prova or 0
        ),
        "envios_oficiais_incertos": envios_oficiais_incertos,
        "envios_analise_incertos": envios_analise_incertos,
        "resultados_oficiais_sem_aviso": resultados_oficiais_sem_aviso,
        "resultados_analise_sem_aviso": resultados_analise_sem_aviso,
        **valores,
    }

def _destinos_operacionais_configurados():
    admin = os.getenv("TELEGRAM_ADMIN_ID")
    grupos_ativos = (
        os.getenv("TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS", "0") == "1"
    )
    grupos = tuple(filter(None, (
        os.getenv("TELEGRAM_CHAT_ID"),
        os.getenv("TELEGRAM_CHAT_ID_GOLS"),
        os.getenv("TELEGRAM_CHAT_ID_ESCANTEIOS"),
    )))
    destinos = []
    # TELEGRAM_ADMIN_ID só é uma rota administrativa segura quando não
    # aponta para um dos grupos de sinais. Sem esse cuidado, a configuração
    # aparentemente separada continuava publicando telemetria no grupo.
    admin_exclusivo = bool(admin and admin not in grupos)
    candidatos = [admin] if admin_exclusivo else []
    if grupos_ativos or not admin:
        candidatos.extend(grupos)
    for destino in candidatos:
        if destino and destino not in destinos:
            destinos.append(destino)
    return destinos

def auditar_notificacoes_operacionais(
    conexao, agora=None, incerto_minutos=2, erro_minutos=10,
):
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite_incerto = (
        agora - timedelta(minutes=incerto_minutos)
    ).isoformat()
    limite_erro = (agora - timedelta(minutes=erro_minutos)).isoformat()
    incertas_em_transito = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais
        WHERE status IN ('enviando', 'tentando')
          AND datetime(tentado_em) <= datetime(?)
        """,
        (limite_incerto,),
    ).fetchone()[0]
    incertas_nao_superadas = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais incerta
        WHERE incerta.status='incerto'
          AND NOT EXISTS (
              SELECT 1 FROM notificacoes_operacionais sucesso
              WHERE sucesso.destino=incerta.destino
                AND sucesso.status='entregue'
                AND datetime(sucesso.entregue_em)
                    > datetime(incerta.tentado_em)
          )
        """
    ).fetchone()[0]
    incertas_superadas = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais incerta
        WHERE incerta.status='incerto'
          AND EXISTS (
              SELECT 1 FROM notificacoes_operacionais sucesso
              WHERE sucesso.destino=incerta.destino
                AND sucesso.status='entregue'
                AND datetime(sucesso.entregue_em)
                    > datetime(incerta.tentado_em)
          )
        """
    ).fetchone()[0]
    incertas = int(incertas_em_transito or 0) + int(
        incertas_nao_superadas or 0
    )
    destinos_ativos = _destinos_operacionais_configurados()
    filtro_destinos = ""
    parametros_erros = [limite_erro]
    if destinos_ativos:
        filtro_destinos = (
            " AND falha.destino IN ("
            + ",".join("?" for _ in destinos_ativos)
            + ")"
        )
        parametros_erros.extend(destinos_ativos)
    else:
        # Sem contexto de configuração não é correto reclassificar falhas
        # históricas de destinos já removidos como incidentes atuais.
        # A ausência de destino é tratada pela validação de configuração.
        filtro_destinos = " AND 0"
    erros_persistentes = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais falha
        WHERE falha.status='erro'
          AND falha.tentativas >= 3
          AND datetime(falha.tentado_em) <= datetime(?)
        """ + filtro_destinos + """
          AND NOT EXISTS (
              SELECT 1 FROM notificacoes_operacionais sucesso
              WHERE sucesso.status='entregue'
                AND (
                    sucesso.chave=falha.chave
                    OR (
                        sucesso.destino=falha.destino
                        AND datetime(sucesso.entregue_em)
                            > datetime(falha.tentado_em)
                    )
                )
          )
        """,
        parametros_erros,
    ).fetchone()[0]
    provas_invalidas = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais
        WHERE status='entregue'
          AND (
              provedor<>'telegram'
              OR provedor_mensagem_id IS NULL
              OR TRIM(provedor_mensagem_id)=''
              OR CASE
                   WHEN json_valid(confirmacao_json) THEN
                       COALESCE(
                           json_extract(confirmacao_json, '$.ok'), 0
                       ) <> 1
                       OR COALESCE(
                           json_extract(
                               confirmacao_json, '$.provedor'
                           ), ''
                       ) <> 'telegram'
                       OR CAST(COALESCE(
                           json_extract(
                               confirmacao_json, '$.message_id'
                           ), ''
                       ) AS TEXT) <> CAST(provedor_mensagem_id AS TEXT)
                   ELSE 1
                 END
          )
        """
    ).fetchone()[0]
    provas_duplicadas = conexao.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT destino, provedor_mensagem_id
            FROM notificacoes_operacionais
            WHERE status='entregue' AND provedor='telegram'
              AND provedor_mensagem_id IS NOT NULL
            GROUP BY destino, provedor_mensagem_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    entregues = conexao.execute(
        """
        SELECT COUNT(*) FROM notificacoes_operacionais
        WHERE status='entregue'
        """
    ).fetchone()[0]
    disjuntores = [
        _estado_disjuntor_notificacao_operacional(
            conexao, destino, agora
        )
        for destino in destinos_ativos
    ]
    pausados = [
        item for item in disjuntores if item.get("pausado")
    ]
    valores = {
        "incertas": int(incertas or 0),
        "incertas_em_transito": int(incertas_em_transito or 0),
        "incertas_nao_superadas": int(incertas_nao_superadas or 0),
        "incertas_superadas": int(incertas_superadas or 0),
        "erros_persistentes": int(erros_persistentes or 0),
        "provas_invalidas": int(provas_invalidas or 0),
        "provas_duplicadas": int(provas_duplicadas or 0),
        "disjuntor_pausado": bool(pausados),
    }
    criticos = {
        "erros_persistentes": valores["erros_persistentes"],
        "provas_invalidas": valores["provas_invalidas"],
        "provas_duplicadas": valores["provas_duplicadas"],
    }
    return {
        # Uma confirmação operacional ambígua não altera snapshots,
        # sinais ou resultados. Ela continua visível para reconciliação,
        # mas somente falha persistente ou prova inválida degrada os dados.
        "saudavel": not any(criticos.values()),
        "requer_atencao": bool(
            valores["incertas"] or valores["disjuntor_pausado"]
        ),
        "entregues_com_prova": int(entregues or 0),
        "destinos_configurados": len(destinos_ativos),
        "incerto_minutos": int(incerto_minutos),
        "erro_minutos": int(erro_minutos),
        "disjuntor_pausado": bool(pausados),
        "destinos_pausados": len(pausados),
        "proxima_tentativa_em": min(
            (
                item["proxima_tentativa_em"]
                for item in pausados
                if item.get("proxima_tentativa_em")
            ),
            default=None,
        ),
        **valores,
    }

def verificar_trabalhador_acompanhamento_odd(
    caminho,
    *,
    agora=None,
    ativo=None,
    monitor_inicializando=False,
):
    """Audita a cadencia da thread sem transformar oscilacao em Telegram."""
    if ativo is None:
        ativo = str(os.getenv(
            "ACOMPANHAMENTO_ODD_WORKER_DEDICADO_ATIVO", "1"
        )).strip().casefold() in {"1", "true", "sim", "yes", "on"}
    if not ativo:
        return {
            "saudavel": True,
            "estado": "desativado",
            "motivo": None,
            "aplicacao_sinais": False,
        }
    agora = agora or datetime.now()
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        atualizado = datetime.fromisoformat(str(dados["atualizado_em"]))
        intervalo = max(float(
            dados.get("intervalo_alvo_segundos") or 15.0
        ), 1.0)
    except (
        OSError, KeyError, TypeError, ValueError, json.JSONDecodeError,
    ):
        return {
            "saudavel": bool(monitor_inicializando),
            "estado": (
                "inicializando" if monitor_inicializando
                else "estado_ausente_ou_invalido"
            ),
            "motivo": (
                None if monitor_inicializando
                else "trabalhador_acompanhamento_odd_sem_estado"
            ),
            "aplicacao_sinais": False,
        }
    if atualizado.tzinfo is not None:
        atualizado = atualizado.astimezone().replace(tzinfo=None)
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    idade = max((agora - atualizado).total_seconds(), 0.0)
    limite = max(intervalo * 4.0, 90.0)
    status = str(dados.get("status") or "indeterminado")
    try:
        falhas = max(int(dados.get("falhas_consecutivas") or 0), 0)
    except (TypeError, ValueError):
        falhas = 0
    def inteiro_nao_negativo(chave, padrao=0):
        try:
            return max(int(dados.get(chave, padrao)), 0)
        except (TypeError, ValueError):
            return max(int(padrao), 0)

    clv_informado = "clv_pos_alerta_versao" in dados
    clv_versao = dados.get("clv_pos_alerta_versao")
    clv_candidatos = inteiro_nao_negativo("clv_pos_alerta_candidatos")
    clv_consultados = inteiro_nao_negativo("clv_pos_alerta_consultados")
    clv_com_oferta = inteiro_nao_negativo(
        "clv_pos_alerta_com_oferta_exata"
    )
    clv_sem_oferta = inteiro_nao_negativo(
        "clv_pos_alerta_sem_oferta_exata"
    )
    clv_somente_estado = inteiro_nao_negativo(
        "clv_pos_alerta_somente_estado"
    )
    clv_persistidos = inteiro_nao_negativo(
        "clv_pos_alerta_estados_persistidos"
    )
    clv_falhas = inteiro_nao_negativo("clv_pos_alerta_falhas")
    clv_falhas_consecutivas = inteiro_nao_negativo(
        "clv_pos_alerta_falhas_consecutivas"
    )
    clv_aplicacao_sinais = bool(
        dados.get("clv_pos_alerta_aplicacao_sinais")
    )
    clv_telegram = bool(dados.get("clv_pos_alerta_telegram"))
    clv_mercados_api = dados.get(
        "clv_pos_alerta_mercados_api_rapida"
    )
    clv_mercados_snapshot = dados.get(
        "clv_pos_alerta_mercados_somente_snapshot"
    )
    cobertura_clv_v2 = bool(
        isinstance(clv_mercados_api, list)
        and isinstance(clv_mercados_snapshot, list)
        and set(clv_mercados_api) == set(MERCADOS_CLV_API_RAPIDA)
        and len(clv_mercados_api) == len(set(clv_mercados_api))
        and set(clv_mercados_snapshot)
        == set(MERCADOS_CLV_SOMENTE_SNAPSHOT)
        and len(clv_mercados_snapshot) == len(set(clv_mercados_snapshot))
        and not set(clv_mercados_api) & set(clv_mercados_snapshot)
    )
    integridade_clv = bool(
        not clv_informado
        or (
            clv_versao in {
                "coleta-clv-pos-alerta-api-rapida-v1",
                "coleta-clv-pos-alerta-api-rapida-v2",
                "coleta-clv-pos-alerta-api-rapida-v3",
                "coleta-clv-pos-alerta-api-rapida-v4",
                VERSAO_COLETA_CLV_API_RAPIDA,
            }
            and (
                clv_versao == "coleta-clv-pos-alerta-api-rapida-v1"
                or cobertura_clv_v2
            )
            and clv_consultados <= clv_candidatos
            and clv_com_oferta <= clv_consultados
            and clv_sem_oferta <= clv_consultados
            and clv_com_oferta + clv_sem_oferta == clv_consultados
            and clv_somente_estado <= clv_sem_oferta
            and clv_persistidos <= clv_consultados
            and not clv_aplicacao_sinais
            and not clv_telegram
        )
    )

    lote = max(inteiro_nao_negativo("lote_maximo", 10), 1)
    fila_total = inteiro_nao_negativo("fila_total")
    fila_recente = inteiro_nao_negativo("fila_tecnica_recente")
    fila_dormente = inteiro_nao_negativo("fila_tecnica_dormente")
    fila_nunca_consultada = inteiro_nao_negativo(
        "fila_recente_nunca_consultada"
    )
    fila_pendente = inteiro_nao_negativo("fila_pendente_apos_lote")
    referencias_tentadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_tentadas"
    )
    referencias_reservadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_reservadas"
    )
    referencias_consultadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_consultadas"
    )
    referencias_linha_exata = inteiro_nao_negativo(
        "referencias_sombra_rapidas_linha_exata"
    )
    referencias_auditadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_auditadas"
    )
    referencias_observadas = inteiro_nao_negativo(
        "referencias_sombra_rapidas_observadas"
    )
    comparacoes_referencia = inteiro_nao_negativo(
        "comparacoes_referencia_sombra_rapida"
    )
    aplicacao_referencia = bool(
        dados.get("aplicacao_sinais_referencia_sombra")
    )
    integridade_referencia_rodada = bool(
        referencias_reservadas <= referencias_tentadas
        and referencias_consultadas <= referencias_reservadas
        and referencias_linha_exata <= referencias_consultadas
        and referencias_auditadas <= referencias_tentadas
        and referencias_observadas <= referencias_linha_exata
        and comparacoes_referencia <= referencias_observadas * 2
        and not aplicacao_referencia
    )
    campos_funil_referencia = (
        "avaliadas", "aprovadas", "reprovadas", "com_oferta",
        "bloqueadas_custodia", "bloqueadas_materializacao",
        "alertas_enviados", "fontes_executaveis_pos_envio",
        "selecionadas_para_consulta", "suprimidas_limite_rodada",
    )

    def auditar_funil_referencia(bruto, *, informado, versao_esperada):
        presente = isinstance(bruto, dict)
        funil = bruto if presente else {}
        valor_anterior = funil.get("tentativas_anteriores_funil")
        if isinstance(valor_anterior, bool):
            tentativas_anteriores = 0
            tentativas_anteriores_validas = False
        else:
            try:
                tentativas_anteriores = int(valor_anterior or 0)
                tentativas_anteriores_validas = tentativas_anteriores >= 0
            except (TypeError, ValueError):
                tentativas_anteriores = 0
                tentativas_anteriores_validas = False
        contadores = {}
        contadores_validos = True
        for chave in campos_funil_referencia:
            valor = funil.get(chave)
            if isinstance(valor, bool):
                numero = None
            else:
                try:
                    numero = int(valor or 0)
                except (TypeError, ValueError):
                    numero = None
            if numero is None or numero < 0:
                contadores_validos = False
                numero = 0
            contadores[chave] = numero
        exclusoes = funil.get("exclusoes") or {}
        exclusoes_validas = isinstance(exclusoes, dict)
        if exclusoes_validas:
            for quantidade in exclusoes.values():
                if isinstance(quantidade, bool):
                    exclusoes_validas = False
                    break
                try:
                    if int(quantidade) < 0:
                        exclusoes_validas = False
                        break
                except (TypeError, ValueError):
                    exclusoes_validas = False
                    break
        if not informado:
            integridade = True
        else:
            integridade = bool(
                presente
                and funil.get("versao") == versao_esperada
                and contadores_validos
                and tentativas_anteriores_validas
                and exclusoes_validas
                and contadores["aprovadas"] + contadores["reprovadas"]
                == contadores["avaliadas"]
                and contadores["com_oferta"] <= contadores["avaliadas"]
                and contadores["bloqueadas_custodia"]
                <= contadores["avaliadas"]
                and contadores["bloqueadas_materializacao"]
                <= contadores["aprovadas"]
                and contadores["alertas_enviados"]
                <= contadores["aprovadas"]
                and contadores["fontes_executaveis_pos_envio"]
                <= contadores["alertas_enviados"]
                and contadores["selecionadas_para_consulta"]
                + contadores["suprimidas_limite_rodada"]
                == contadores["fontes_executaveis_pos_envio"]
                and not bool(funil.get("aplicacao_sinais"))
                and not bool(funil.get("telegram"))
                and funil.get("integridade", True) is True
            )
        return {
            "presente": presente,
            "legado_sem_funil": not informado,
            "versao": funil.get("versao"),
            "integridade": integridade,
            **contadores,
            "tentativas_anteriores_funil": tentativas_anteriores,
            "exclusoes": exclusoes if exclusoes_validas else {},
            "aplicacao_sinais": bool(funil.get("aplicacao_sinais")),
            "telegram": bool(funil.get("telegram")),
        }

    chave_funil_rodada = "referencias_sombra_rapidas_funil"
    funil_rodada = auditar_funil_referencia(
        dados.get(chave_funil_rodada),
        informado=chave_funil_rodada in dados,
        versao_esperada="funil-referencia-sombra-rapida-v1",
    )
    integridade_referencia_rodada = bool(
        integridade_referencia_rodada
        and funil_rodada["integridade"]
        and referencias_tentadas
        <= funil_rodada["selecionadas_para_consulta"]
        if not funil_rodada["legado_sem_funil"]
        else integridade_referencia_rodada
    )
    chave_acumulada = "referencia_sombra_rapida_acumulada"
    acumulada_informada = chave_acumulada in dados
    acumulada_bruta = dados.get(chave_acumulada)
    acumulada_presente = isinstance(acumulada_bruta, dict)
    acumulada = acumulada_bruta if acumulada_presente else {}

    def inteiro_acumulado(chave):
        valor = acumulada.get(chave)
        if isinstance(valor, bool):
            return None
        try:
            numero = int(valor or 0)
        except (TypeError, ValueError):
            return None
        return numero if numero >= 0 else None

    nomes_acumulados = (
        "rodadas", "tentadas", "reservadas", "consultadas",
        "linha_exata", "auditadas", "observadas", "comparacoes",
        "creditos_estimados_reservados",
    )
    contadores_acumulados = {
        chave: inteiro_acumulado(chave) for chave in nomes_acumulados
    }
    valores_acumulados_validos = all(
        valor is not None for valor in contadores_acumulados.values()
    )
    if not acumulada_informada:
        integridade_referencia_acumulada = True
    elif not acumulada_presente or not valores_acumulados_validos:
        integridade_referencia_acumulada = False
    else:
        evidencia_acumulada = any(
            contadores_acumulados[chave]
            for chave in nomes_acumulados
            if chave != "rodadas"
        )
        ultima_evidencia_valida = not evidencia_acumulada
        if evidencia_acumulada:
            try:
                datetime.fromisoformat(str(
                    acumulada["ultima_evidencia_em"]
                ))
                ultima_evidencia_valida = True
            except (KeyError, TypeError, ValueError):
                ultima_evidencia_valida = False
        integridade_referencia_acumulada = bool(
            acumulada.get("versao")
            == "referencia-sincronizada-monitor-odd-rapido-acumulada-v1"
            and acumulada.get("integridade") is True
            and not bool(acumulada.get("aplicacao_sinais"))
            and not bool(acumulada.get("telegram"))
            and contadores_acumulados["reservadas"]
            <= contadores_acumulados["tentadas"]
            and contadores_acumulados["consultadas"]
            <= contadores_acumulados["reservadas"]
            and contadores_acumulados["linha_exata"]
            <= contadores_acumulados["consultadas"]
            and contadores_acumulados["auditadas"]
            <= contadores_acumulados["tentadas"]
            and contadores_acumulados["observadas"]
            <= contadores_acumulados["linha_exata"]
            and contadores_acumulados["comparacoes"]
            <= contadores_acumulados["observadas"] * 2
            and contadores_acumulados["tentadas"]
            >= referencias_tentadas
            and contadores_acumulados["reservadas"]
            >= referencias_reservadas
            and contadores_acumulados["consultadas"]
            >= referencias_consultadas
            and contadores_acumulados["linha_exata"]
            >= referencias_linha_exata
            and contadores_acumulados["auditadas"]
            >= referencias_auditadas
            and contadores_acumulados["observadas"]
            >= referencias_observadas
            and contadores_acumulados["comparacoes"]
            >= comparacoes_referencia
            and ultima_evidencia_valida
        )
    chave_funil_acumulado = "funil_selecao"
    funil_acumulado = auditar_funil_referencia(
        acumulada.get(chave_funil_acumulado),
        informado=(
            acumulada_presente and chave_funil_acumulado in acumulada
        ),
        versao_esperada="funil-referencia-sombra-rapida-acumulado-v1",
    )
    if acumulada_presente and not funil_acumulado["legado_sem_funil"]:
        integridade_referencia_acumulada = bool(
            integridade_referencia_acumulada
            and funil_acumulado["integridade"]
            and contadores_acumulados.get("tentadas", 0)
            <= (
                funil_acumulado["tentativas_anteriores_funil"]
                + funil_acumulado["selecionadas_para_consulta"]
            )
            and all(
                funil_acumulado[chave] >= funil_rodada[chave]
                for chave in campos_funil_referencia
            )
        )
    integridade_referencia = bool(
        integridade_referencia_rodada
        and integridade_referencia_acumulada
    )
    rodadas_estimadas = (
        (fila_recente + lote - 1) // lote if fila_recente else 0
    )
    espera_fila_estimada = max(rodadas_estimadas - 1, 0) * intervalo
    try:
        sla_fila = min(max(float(os.getenv(
            "ACOMPANHAMENTO_ODD_API_FILA_SLA_SEGUNDOS", "60"
        )), 30.0), 300.0)
    except (TypeError, ValueError):
        sla_fila = 60.0
    fila_saturada = bool(
        fila_pendente > 0 and espera_fila_estimada > sla_fila
    )
    if fila_saturada:
        estado_fila = "saturada"
    elif fila_pendente:
        estado_fila = "em_rodizio"
    elif fila_recente:
        estado_fila = "coberta"
    elif fila_dormente:
        estado_fila = "dormente"
    else:
        estado_fila = "vazia"
    fresco = idade <= limite
    executando = status in {"ativo", "iniciando"}
    saudavel = bool(
        fresco and executando and falhas < 3 and not fila_saturada
        and integridade_referencia and integridade_clv
    )
    if not fresco:
        motivo = "trabalhador_acompanhamento_odd_atrasado"
        estado = "atrasado"
    elif status == "degradado" or falhas:
        motivo = "trabalhador_acompanhamento_odd_em_recuperacao"
        estado = "recuperando"
    elif not executando:
        motivo = "trabalhador_acompanhamento_odd_parado"
        estado = "parado"
    elif fila_saturada:
        motivo = "fila_acompanhamento_odd_saturada"
        estado = "fila_saturada"
    elif not integridade_referencia:
        motivo = "referencia_sombra_rapida_inconsistente"
        estado = "referencia_sombra_inconsistente"
    elif not integridade_clv:
        motivo = "clv_pos_alerta_inconsistente"
        estado = "clv_pos_alerta_inconsistente"
    else:
        motivo = None
        estado = "ativo"
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": motivo,
        "status": status,
        "idade_segundos": round(idade, 3),
        "limite_atraso_segundos": round(limite, 3),
        "intervalo_alvo_segundos": intervalo,
        "intervalo_real_segundos": dados.get(
            "intervalo_real_segundos"
        ),
        "atraso_inicio_segundos": dados.get("atraso_inicio_segundos"),
        "duracao_rodada_segundos": dados.get(
            "duracao_rodada_segundos"
        ),
        "falhas_consecutivas": falhas,
        "consultados": int(dados.get("consultados") or 0),
        "lote_maximo": lote,
        "fila_total": fila_total,
        "fila_tecnica_recente": fila_recente,
        "fila_tecnica_dormente": fila_dormente,
        "fila_recente_nunca_consultada": fila_nunca_consultada,
        "fila_pendente_apos_lote": fila_pendente,
        "estado_fila": estado_fila,
        "rodadas_estimadas_para_cobrir_fila": rodadas_estimadas,
        "espera_fila_estimada_segundos": round(
            espera_fila_estimada, 3
        ),
        "sla_fila_segundos": round(sla_fila, 3),
        "sem_navegacao_packball": bool(
            dados.get("sem_navegacao_packball")
        ),
        "referencia_sombra_rapida": {
            "versao": "referencia-sincronizada-monitor-odd-rapido-v1",
            "integridade": integridade_referencia,
            "integridade_rodada": integridade_referencia_rodada,
            "tentadas": referencias_tentadas,
            "reservadas": referencias_reservadas,
            "consultadas": referencias_consultadas,
            "linha_exata": referencias_linha_exata,
            "auditadas": referencias_auditadas,
            "observadas": referencias_observadas,
            "comparacoes": comparacoes_referencia,
            "creditos_estimados_reservados": inteiro_nao_negativo(
                "creditos_estimados_referencia_sombra_rapida"
            ),
            "aplicacao_sinais": aplicacao_referencia,
            "telegram": False,
            "funil_rodada": funil_rodada,
            "acumulada": {
                "presente": acumulada_presente,
                "legado_sem_acumulado": not acumulada_informada,
                "versao": acumulada.get("versao"),
                "integridade": integridade_referencia_acumulada,
                "iniciado_em": acumulada.get("iniciado_em"),
                "atualizado_em": acumulada.get("atualizado_em"),
                "ultima_evidencia_em": acumulada.get(
                    "ultima_evidencia_em"
                ),
                **{
                    chave: (
                        contadores_acumulados[chave]
                        if contadores_acumulados[chave] is not None else 0
                    )
                    for chave in nomes_acumulados
                },
                "aplicacao_sinais": bool(
                    acumulada.get("aplicacao_sinais")
                ),
                "telegram": bool(acumulada.get("telegram")),
                "motivos": acumulada.get("motivos") or {},
                "funil_selecao": funil_acumulado,
            },
        },
        "clv_pos_alerta": {
            "presente": clv_informado,
            "legado_sem_telemetria": not clv_informado,
            "versao": clv_versao,
            "mercados_api_rapida": (
                list(clv_mercados_api)
                if isinstance(clv_mercados_api, list) else []
            ),
            "mercados_somente_snapshot": (
                list(clv_mercados_snapshot)
                if isinstance(clv_mercados_snapshot, list) else []
            ),
            "cobertura_mercados_integra": (
                cobertura_clv_v2
                if clv_versao != "coleta-clv-pos-alerta-api-rapida-v1"
                else True
            ),
            "estado": dados.get("clv_pos_alerta_estado"),
            "integridade": integridade_clv,
            "coleta_saudavel": clv_falhas_consecutivas < 3,
            "candidatos": clv_candidatos,
            "consultados": clv_consultados,
            "com_oferta_exata": clv_com_oferta,
            "sem_oferta_exata": clv_sem_oferta,
            "somente_estado": clv_somente_estado,
            "estados_persistidos": clv_persistidos,
            "falhas": clv_falhas,
            "falhas_consecutivas": clv_falhas_consecutivas,
            "motivos": dados.get("clv_pos_alerta_motivos") or {},
            "aplicacao_sinais": clv_aplicacao_sinais,
            "telegram": clv_telegram,
        },
        "aplicacao_sinais": False,
    }

def _estado_disjuntor_notificacao_operacional(
    conexao,
    destino,
    agora,
    limite_falhas=3,
    janela_minutos=10,
    pausa_minutos=5,
):
    """Evita tempestade de alertas durante indisponibilidade do Telegram."""
    inicio_janela = (
        agora - timedelta(minutes=janela_minutos)
    ).replace(microsecond=0).isoformat()
    linha = conexao.execute(
        """
        SELECT COUNT(*) AS falhas, MAX(falha.tentado_em) AS ultima_falha
        FROM notificacoes_operacionais falha
        WHERE falha.destino=? AND falha.status='erro'
          AND datetime(falha.tentado_em) >= datetime(?)
          AND NOT EXISTS (
              SELECT 1 FROM notificacoes_operacionais sucesso
              WHERE sucesso.destino=falha.destino
                AND sucesso.status='entregue'
                AND datetime(sucesso.entregue_em)
                    > datetime(falha.tentado_em)
          )
        """,
        (destino, inicio_janela),
    ).fetchone()
    try:
        falhas = int(linha["falhas"] or 0)
        ultima_falha = linha["ultima_falha"]
    except (TypeError, IndexError):
        falhas = int(linha[0] or 0)
        ultima_falha = linha[1]
    proxima_tentativa_em = None
    pausado = False
    if falhas >= int(limite_falhas) and ultima_falha:
        try:
            proxima = datetime.fromisoformat(ultima_falha) + timedelta(
                minutes=pausa_minutos
            )
            proxima_tentativa_em = proxima.replace(
                microsecond=0
            ).isoformat()
            pausado = agora < proxima
        except (TypeError, ValueError):
            pausado = False
    return {
        "pausado": pausado,
        "destino": destino,
        "falhas_recentes": falhas,
        "limite_falhas": int(limite_falhas),
        "janela_minutos": int(janela_minutos),
        "pausa_minutos": int(pausa_minutos),
        "ultima_falha_em": ultima_falha,
        "proxima_tentativa_em": proxima_tentativa_em,
    }
