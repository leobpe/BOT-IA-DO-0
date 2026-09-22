import hashlib
import json
import math
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from acompanhamento_odd import (
    VERSAO_EVIDENCIA_OFERTA_RAPIDA,
    VERSAO_EVIDENCIA_OFERTA_RAPIDA_V3,
    VERSAO_MATERIALIZACAO_RAPIDA,
    extrair_odd_exata_acompanhamento,
    validar_contrato_mercado_oferta,
    validar_identidade_evento_oferta,
    validar_proveniencia_temporal_oferta,
)
from desajuste_odds import (
    INTERVALO_FONTES_MAXIMO_SEGUNDOS,
    construir_comparacoes_multifonte,
)
from coerencia_curva_odds import (
    MOTIVOS_ANOMALIA_CURVA,
    VERSAO_EVIDENCIA_ANOMALIA,
    validar_coerencia_curva_candidato,
)
from clv_pos_alerta import (
    ESTADO_OBSERVACAO_CLV,
    HORIZONTE_MAXIMO_SEGUNDOS as CLV_HORIZONTE_MAXIMO_SEGUNDOS,
    HORIZONTE_MINIMO_SEGUNDOS as CLV_HORIZONTE_MINIMO_SEGUNDOS,
    MERCADOS_CLV_API_RAPIDA,
    VERSAO_EVIDENCIA_ESTADO_CLV,
    linha_equivalente,
    modo_coleta_estado_clv,
    normalizar_escanteios_estado,
    referencia_clv,
)
from linhagem_regras import fingerprint_vinculado_no_banco
from custodia_estimativa_historica import (
    GATILHOS_SQL as GATILHOS_ESTIMATIVA_HISTORICA,
    instalar_gatilhos as instalar_gatilhos_estimativa_historica,
)


FORMATO_ANTIGO = "%d/%m/%Y %H:%M:%S"


def _sql_leitura_acompanhamento_vigente(alias):
    """Predicado comum à fila e ao último gate; aliases são internos."""
    return f"""
        {alias}.status='rejeitado'
        AND json_extract({alias}.features_json, '$.acompanhamento_odd.elegivel_aviso')=1
        AND NOT EXISTS (
            SELECT 1 FROM sinais revisao
            WHERE revisao.partida_id={alias}.partida_id
              AND revisao.mercado={alias}.mercado
              AND revisao.regra_versao={alias}.regra_versao
              AND revisao.id>{alias}.id AND revisao.status='rejeitado'
              AND revisao.linha IS {alias}.linha
              AND json_type(revisao.features_json, '$.acompanhamento_odd')='object'
              AND json_extract(revisao.features_json, '$.acompanhamento_metodo_gols.metodo')
                  IS json_extract({alias}.features_json, '$.acompanhamento_metodo_gols.metodo')
        )
        AND NOT EXISTS (
            SELECT 1 FROM snapshots revisao_tecnica
            WHERE revisao_tecnica.partida_id={alias}.partida_id
              AND revisao_tecnica.id>{alias}.snapshot_id
              AND json_extract(revisao_tecnica.qualidade_json,
                  '$.analise_tecnica_acompanhamento_odd')=1
        )
    """


def _sql_vinculo_acompanhamento_vigente(alias):
    return f"""
        (json_extract({alias}.features_json,
            '$.acompanhamento_odd_rapido.leitura_tecnica_sinal_id') IS NULL
         OR EXISTS (
            SELECT 1 FROM sinais tecnica
            WHERE tecnica.id=json_extract({alias}.features_json,
                    '$.acompanhamento_odd_rapido.leitura_tecnica_sinal_id')
              AND tecnica.partida_id={alias}.partida_id
              AND tecnica.mercado={alias}.mercado AND tecnica.linha IS {alias}.linha
              AND {_sql_leitura_acompanhamento_vigente('tecnica')}
         ))
    """


class _ReservaNotificacaoInvalida(RuntimeError):
    """Forca rollback quando a revisao muda durante a finalizacao."""


ESQUEMA_OBRIGATORIO = {
    "metadados": {"chave", "valor"},
    "partidas": {
        "id", "packball_url", "mandante", "visitante",
        "mandante_normalizado", "visitante_normalizado",
        "packball_partida_id", "pais", "liga", "liga_normalizada",
        "primeira_coleta", "ultima_coleta", "api_fixture_id",
        "api_orientacao",
    },
    "snapshots": {
        "id", "partida_id", "coletado_em", "placar", "status",
        "texto_linha", "estatisticas_json", "evolucao_json",
        "confirmacao_api_json", "estatisticas_api_json",
        "contexto_api_json", "qualidade_dados", "qualidade_json",
        "movimentacao_odds_json", "fontes_json",
    },
    "odds": {
        "id", "snapshot_id", "tipo", "mercado", "dados",
        "estrutura_json",
    },
    "eventos": {
        "id", "snapshot_id", "tipo", "detalhe", "minuto", "time_nome",
        "jogador_nome", "payload_json",
    },
    "sinais": {
        "id", "partida_id", "snapshot_id", "criado_em", "mercado",
        "linha", "odd", "pontuacao_tecnica", "probabilidade_calibrada",
        "regra_versao", "regra_fingerprint", "motivos_json",
        "features_json", "status",
    },
    "resultados_sinais": {
        "sinal_id", "encerrado_em", "resultado", "retorno_unidades",
        "observacao", "snapshot_id_liquidacao", "fonte_resultado",
    },
    "revisoes_resultados": {
        "id", "sinal_id", "revisado_em", "encerrado_em_anterior",
        "resultado_anterior", "retorno_anterior", "observacao_anterior",
        "snapshot_id_liquidacao_anterior", "fonte_resultado_anterior",
        "motivo", "notificacao_status", "notificacao_erro",
        "notificacao_provedor", "notificacao_destino_id",
        "notificacao_mensagem_id",
        "notificacao_confirmacao_json",
    },
    "calibracoes": {
        "id", "mercado", "regra_versao", "atualizado_em", "amostra",
        "ativa", "modelo_json",
    },
    "historico_calibracoes": {
        "id", "mercado", "regra_versao", "registrado_em", "amostra",
        "ativa", "amostra_fingerprint", "motivo", "modelo_hash",
        "modelo_json",
    },
    "historico_drift_simulacoes": {
        "id", "regra_versao", "mercado", "registrado_em",
        "ultima_decisao_id", "ultimo_resultado_em", "estado", "avaliavel",
        "amostra_recente", "amostra_base", "roi_recente", "roi_base",
        "delta_roi", "intervalo_delta_min", "intervalo_delta_max",
        "taxa_acerto_recente", "taxa_acerto_base", "confirmacoes",
        "confirmado", "metricas_json",
    },
    "historico_avaliacao_contexto": {
        "id", "regra_versao", "mercado", "registrado_em",
        "ultimo_sinal_id", "amostra", "estado", "pronto_para_revisao",
        "avaliacao_json",
    },
    "entregas_alertas": {
        "id", "sinal_id", "canal", "tentado_em", "entregue_em", "status",
        "erro", "tentativas", "provedor", "provedor_mensagem_id",
        "provedor_destino_id", "confirmacao_json", "reserva_token",
    },
    "notificacoes_operacionais": {
        "id", "chave", "destino", "criado_em", "tentado_em",
        "entregue_em", "status", "tentativas", "erro", "provedor",
        "provedor_mensagem_id", "confirmacao_json", "resumo",
    },
    "cache_api_football": {
        "chave", "categoria", "armazenado_em", "dados_json",
    },
    "historico_api_live": {
        "id", "fixture_id", "packball_url", "coletado_em", "minuto",
        "periodo", "orientacao", "chutes_mandante",
        "chutes_visitante", "chutes_gol_mandante",
        "chutes_gol_visitante", "escanteios_mandante",
        "escanteios_visitante", "xg_mandante", "xg_visitante",
        "completo", "fonte",
    },
    "pareamentos_thestatsapi": {
        "packball_url", "match_id", "orientacao", "similaridade",
        "margem", "mandante_api", "visitante_api", "criado_em",
        "atualizado_em", "diagnostico_json", "fonte",
        "aplicacao_sinais",
    },
    "historico_thestatsapi_live": {
        "id", "match_id", "packball_url", "coletado_em", "minuto",
        "periodo", "placar", "placar_mandante", "placar_visitante",
        "orientacao", "chutes_mandante",
        "chutes_visitante", "chutes_gol_mandante",
        "chutes_gol_visitante", "escanteios_mandante",
        "escanteios_visitante", "xg_mandante", "xg_visitante",
        "completo", "fonte", "aplicacao_sinais",
    },
    "odds_thestatsapi_live": {
        "id", "match_id", "packball_url", "coletado_em", "bookmaker",
        "mercado", "mercado_origem", "categoria", "tipo_mercado",
        "periodo", "linha", "odd_over", "odd_under", "fonte",
        "aplicacao_sinais",
    },
    "consultas_finalizacao": {
        "id", "partida_id", "fonte", "consultado_em", "estado",
        "status_observado", "placar_observado", "erro",
    },
    "observacoes_fontes_odds": {
        "id", "partida_id", "fonte", "consultado_em", "estado",
        "evento_externo_id", "mandante_observado", "visitante_observado",
        "periodo", "mercado", "motivo", "oferta_json", "url_origem",
        "metodo_coleta", "metadados_json", "evidencia_sha256",
        "evidencia_referencia",
    },
    "comparacoes_odds_fontes": {
        "id", "snapshot_id", "partida_id", "observado_em", "placar",
        "status", "minuto", "categoria", "escopo", "periodo", "linha",
        "selecao", "fonte_a", "bookmaker_a", "odd_a", "coletado_em_a",
        "snapshot_fonte_a",
        "placar_fonte_a", "status_fonte_a", "minuto_fonte_a",
        "fonte_b", "bookmaker_b", "odd_b", "coletado_em_b",
        "snapshot_fonte_b",
        "placar_fonte_b", "status_fonte_b", "minuto_fonte_b",
        "fonte_melhor", "bookmaker_melhor", "odd_melhor",
        "fonte_controle", "bookmaker_controle", "odd_controle",
        "delta_absoluto", "delta_relativo", "intervalo_fontes_segundos",
        "frescor_maximo_segundos", "diferenca_minutos",
        "compatibilidade_bookmaker", "estado",
        "motivos_json", "versao", "evidencia_sha256",
    },
    "auditoria_fila_packball": {
        "id", "ciclo_em", "registrado_em", "packball_url",
        "mandante", "visitante", "liga", "minuto", "posicao",
        "processada", "acionavel", "fila_operacional",
        "idade_segundos", "atraso_segundos", "em_foco",
        "scanner_prioritario", "pre_live_prioritario",
        "prioridade_liga_gols", "prioridade_indicadores_lista",
        "prioridade_api_lote", "janelas_temporais_json", "motivo",
    },
    "historico_taxas_ligas_gols_packball": {
        "id", "league_id", "pais", "liga", "liga_normalizada",
        "temporada", "periodo", "jogos_realizados",
        "jogos_previstos", "jogos_com_stats", "over_0_5",
        "over_1_5", "over_2_5", "fonte", "coletado_em",
        "versao", "evidencia_sha256",
    },
}
TABELAS_OBRIGATORIAS = set(ESQUEMA_OBRIGATORIO)
INDICES_OBRIGATORIOS = {
    "idx_entregas_telegram_mensagem_unica",
    "idx_notificacoes_operacionais_fila",
    "idx_notificacoes_operacionais_mensagem_unica",
    "idx_cache_api_football_categoria_tempo",
    "idx_historico_api_live_fixture_tempo",
    "idx_historico_api_live_tempo",
    "idx_pareamentos_thestatsapi_match",
    "idx_pareamentos_thestatsapi_atualizado",
    "idx_thestatsapi_live_match_tempo",
    "idx_thestatsapi_live_tempo",
    "idx_odds_thestatsapi_match_tempo",
    "idx_odds_thestatsapi_tempo",
    "idx_odds_thestatsapi_mercado",
    "idx_historico_drift_simulacoes_mercado",
    "idx_historico_avaliacao_contexto_mercado",
    "idx_observacoes_fontes_odds_fonte_tempo",
    "idx_observacoes_fontes_odds_referencia_tempo",
    "idx_comparacoes_odds_estado_tempo",
    "idx_comparacoes_odds_chave_tempo",
    "idx_auditoria_fila_packball_ciclo",
    "idx_auditoria_fila_packball_partida",
    "idx_historico_taxas_ligas_tempo",
    "idx_historico_taxas_ligas_chave_tempo",
}
GATILHOS_OBRIGATORIOS = {
    "trg_historico_contexto_update_imutavel",
    "trg_historico_contexto_delete_imutavel",
    "trg_pontuacao_sombra_update_imutavel",
    "trg_pontuacao_sombra_delete_imutavel",
    "trg_hipotese_sombra_update_imutavel",
    "trg_hipotese_sombra_delete_imutavel",
    "trg_exploracao_sombra_definicao_update_imutavel",
    "trg_exploracao_sombra_definicao_delete_imutavel",
    "trg_exploracao_sombra_politica_update_imutavel",
    "trg_exploracao_sombra_politica_delete_imutavel",
    "trg_auditoria_ligas_prospectiva_update_imutavel",
    "trg_auditoria_ligas_prospectiva_delete_imutavel",
    "trg_historico_taxas_ligas_update_imutavel",
    "trg_historico_taxas_ligas_delete_imutavel",
    "trg_comparacoes_odds_update_imutavel",
    "trg_comparacoes_odds_delete_imutavel",
    "trg_avaliacao_desajuste_odds_update_imutavel",
    "trg_avaliacao_desajuste_odds_delete_imutavel",
    "trg_avaliacao_probabilidade_individual_update_imutavel",
    "trg_avaliacao_probabilidade_individual_delete_imutavel",
    "trg_avaliacao_contexto_update_imutavel",
    "trg_avaliacao_contexto_delete_imutavel",
    "trg_carteira_operacional_epoca_update_imutavel",
    "trg_carteira_operacional_epoca_delete_imutavel",
    "trg_sinais_exploracao_sombra_independente",
    "trg_sinais_exploracao_sombra_update_imutavel",
    "trg_sinais_exploracao_sombra_delete_imutavel",
    "trg_experimento_filtro_update_imutavel",
    "trg_experimento_filtro_delete_imutavel",
    "trg_conclusao_experimento_filtro_update_imutavel",
    "trg_conclusao_experimento_filtro_delete_imutavel",
    "trg_sinais_linhagem_imutavel",
    "trg_resultados_sinais_update_imutavel",
    "trg_resultados_sinais_delete_auditado",
    "trg_revisoes_resultados_insert_coerente",
    "trg_revisoes_resultados_evidencia_imutavel",
    "trg_revisoes_resultados_delete_imutavel",
    "trg_historico_calibracoes_update_imutavel",
    "trg_historico_calibracoes_delete_imutavel",
    "trg_historico_drift_update_imutavel",
    "trg_historico_drift_delete_imutavel",
    "trg_entregas_alertas_prova_imutavel",
    "trg_entregas_alertas_entrada_update_imutavel",
    "trg_entregas_alertas_entrada_delete_imutavel",
    "trg_sinais_entregues_evidencia_update_imutavel",
    "trg_sinais_entregues_evidencia_delete_imutavel",
    "trg_snapshots_update_imutavel",
    "trg_snapshots_clv_delete_imutavel",
    "trg_odds_update_imutavel",
    "trg_odds_clv_delete_imutavel",
    "trg_observacoes_odds_evidencia_update_imutavel",
    "trg_observacoes_odds_evidencia_delete_imutavel",
    "trg_observacoes_odds_identidade_estavel",
    "trg_observacoes_odds_identidade_estavel_v2",
    "trg_revisoes_notificacao_prova_imutavel",
    "trg_notificacoes_operacionais_prova_imutavel",
}
GATILHOS_OBRIGATORIOS.update(GATILHOS_ESTIMATIVA_HISTORICA)


def auditar_compatibilidade(conexao):
    tabelas = {
        item[0]
        for item in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    tabelas_ausentes = sorted(TABELAS_OBRIGATORIAS - tabelas)
    gatilhos = {
        item[0]
        for item in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    gatilhos_ausentes = sorted(GATILHOS_OBRIGATORIOS - gatilhos)
    indices = {
        item[0]
        for item in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    indices_ausentes = sorted(INDICES_OBRIGATORIOS - indices)
    colunas_ausentes = {}
    for tabela, obrigatorias in ESQUEMA_OBRIGATORIO.items():
        if tabela not in tabelas:
            continue
        existentes = {
            item[1]
            for item in conexao.execute(
                f'PRAGMA table_info("{tabela}")'
            ).fetchall()
        }
        ausentes = sorted(obrigatorias - existentes)
        if ausentes:
            colunas_ausentes[tabela] = ausentes
    violacoes = conexao.execute("PRAGMA foreign_key_check").fetchall()
    return {
        "compativel": not (
            tabelas_ausentes or colunas_ausentes
            or gatilhos_ausentes or indices_ausentes or violacoes
        ),
        "tabelas": len(tabelas),
        "tabelas_ausentes": tabelas_ausentes,
        "colunas_ausentes": colunas_ausentes,
        "gatilhos_ausentes": gatilhos_ausentes,
        "indices_ausentes": indices_ausentes,
        "violacoes_chaves_estrangeiras": len(violacoes),
    }


def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(
        caractere.lower()
        for caractere in texto
        if not unicodedata.combining(caractere) and caractere.isalnum()
    )


def extrair_packball_id(url):
    correspondencia = re.search(r"/(?:matches|match)/(\d+)(?:/|$)", url or "")
    return int(correspondencia.group(1)) if correspondencia else None


def normalizar_data(valor):
    if isinstance(valor, datetime):
        return valor.replace(microsecond=0).isoformat()
    if not valor:
        return datetime.now().replace(microsecond=0).isoformat()
    try:
        return datetime.fromisoformat(str(valor)).replace(
            microsecond=0
        ).isoformat()
    except ValueError:
        return datetime.strptime(str(valor), FORMATO_ANTIGO).isoformat()


def resumir_risco_alertas_oficiais_conexao(conexao, agora=None):
    """Resume green/red e risco só de alertas oficiais entregues."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    linhas = conexao.execute(
        """
        SELECT DISTINCT r.sinal_id, r.resultado,
                        r.retorno_unidades, r.encerrado_em
        FROM resultados_sinais r
        JOIN entregas_alertas e ON e.sinal_id=r.sinal_id
        WHERE e.status='entregue' AND e.canal NOT LIKE '%:%'
          AND r.resultado IN (
              'green', 'half_green', 'red', 'half_red'
          )
        ORDER BY datetime(r.encerrado_em) DESC, r.sinal_id DESC
        """
    ).fetchall()
    greens_total = sum(
        linha["resultado"] in ("green", "half_green")
        for linha in linhas
    )
    reds_total = sum(
        linha["resultado"] in ("red", "half_red")
        for linha in linhas
    )
    greens_hoje = 0
    reds_hoje = 0
    retorno_hoje = 0.0
    for linha in linhas:
        try:
            encerrado = datetime.fromisoformat(linha["encerrado_em"])
        except (TypeError, ValueError):
            continue
        if encerrado.date() == agora.date():
            retorno_hoje += float(linha["retorno_unidades"] or 0.0)
            if linha["resultado"] in ("green", "half_green"):
                greens_hoje += 1
            elif linha["resultado"] in ("red", "half_red"):
                reds_hoje += 1

    limite_24h = agora - timedelta(hours=24)
    reds_consecutivos = 0
    for linha in linhas:
        try:
            encerrado = datetime.fromisoformat(linha["encerrado_em"])
        except (TypeError, ValueError):
            continue
        if encerrado < limite_24h:
            break
        if linha["resultado"] in ("red", "half_red"):
            reds_consecutivos += 1
        else:
            break
    return {
        "resultados_oficiais": len(linhas),
        "greens_total": greens_total,
        "reds_total": reds_total,
        "greens_hoje": greens_hoje,
        "reds_hoje": reds_hoje,
        "reds_consecutivos_24h": reds_consecutivos,
        "retorno_realizado_hoje": round(retorno_hoje, 4),
        "perda_realizada_hoje": max(0.0, round(-retorno_hoje, 4)),
    }


def registrar_historico_drift_simulacoes(
    conexao, validacao, registrado_em=None
):
    """Persiste uma avaliação somente quando existe resultado independente novo."""
    drift = (validacao or {}).get("drift_simulacoes") or {}
    regra_versao = (
        drift.get("regra_versao")
        or (validacao or {}).get("regra_versao")
    )
    if not regra_versao:
        return {"inseridos": 0, "ignorados": 0, "sem_decisao": 0}

    registrado_em = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    confirmacoes = (
        (validacao or {}).get("drift_simulacoes_confirmacoes") or {}
    )
    confirmados = set(
        (validacao or {}).get("drift_simulacoes_mercados_confirmados") or []
    )
    inseridos = 0
    ignorados = 0
    sem_decisao = 0
    for mercado, metricas in sorted((drift.get("mercados") or {}).items()):
        metricas = metricas or {}
        regra_versao_mercado = (
            metricas.get("regra_versao")
            or (drift.get("regra_versoes_por_mercado") or {}).get(mercado)
            or regra_versao
        )
        if not regra_versao_mercado:
            sem_decisao += 1
            continue
        decisao_id = metricas.get("ultima_decisao_id")
        if decisao_id is None:
            sem_decisao += 1
            continue
        try:
            decisao_id = int(decisao_id)
        except (TypeError, ValueError):
            sem_decisao += 1
            continue
        intervalo = metricas.get("intervalo_delta_roi_95")
        if not isinstance(intervalo, (list, tuple)) or len(intervalo) != 2:
            intervalo = (None, None)
        confirmacao = confirmacoes.get(mercado) or {}
        try:
            quantidade_confirmacoes = max(
                int(confirmacao.get("quantidade") or 0), 0
            )
        except (TypeError, ValueError):
            quantidade_confirmacoes = 0
        metricas_json = json.dumps(
            metricas,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cursor = conexao.execute(
            """
            INSERT OR IGNORE INTO historico_drift_simulacoes (
                regra_versao, mercado, registrado_em, ultima_decisao_id,
                ultimo_resultado_em, estado, avaliavel, amostra_recente,
                amostra_base, roi_recente, roi_base, delta_roi,
                intervalo_delta_min, intervalo_delta_max,
                taxa_acerto_recente, taxa_acerto_base, confirmacoes,
                confirmado, metricas_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(regra_versao_mercado),
                str(mercado),
                registrado_em,
                decisao_id,
                metricas.get("ultimo_resultado_em"),
                str(metricas.get("estado") or "indisponivel"),
                int(bool(metricas.get("avaliavel"))),
                int(metricas.get("amostra_recente") or 0),
                int(metricas.get("amostra_base") or 0),
                metricas.get("roi_recente"),
                metricas.get("roi_base"),
                metricas.get("delta_roi"),
                intervalo[0],
                intervalo[1],
                metricas.get("taxa_acerto_recente"),
                metricas.get("taxa_acerto_base"),
                quantidade_confirmacoes,
                int(mercado in confirmados),
                metricas_json,
            ),
        )
        if cursor.rowcount:
            inseridos += 1
        else:
            ignorados += 1
    return {
        "inseridos": inseridos,
        "ignorados": ignorados,
        "sem_decisao": sem_decisao,
    }


def _filtro_historico_drift(
    regra_versao=None, regras_por_mercado=None
):
    regras_por_mercado = regras_por_mercado or {}
    if regras_por_mercado:
        pares = sorted(regras_por_mercado.items())
        filtro = "WHERE " + " OR ".join(
            "(mercado=? AND regra_versao=?)" for _ in pares
        )
        parametros = [
            valor for par in pares for valor in par
        ]
        return filtro, parametros
    if regra_versao:
        return "WHERE regra_versao=?", [str(regra_versao)]
    return "", []


def resumir_historico_drift_simulacoes(
    conexao, regra_versao=None, regras_por_mercado=None
):
    filtro, parametros = _filtro_historico_drift(
        regra_versao, regras_por_mercado
    )
    linhas = conexao.execute(
        f"""
        SELECT mercado, COUNT(*) AS total,
               MIN(registrado_em) AS primeiro_registro_em,
               MAX(registrado_em) AS ultimo_registro_em,
               SUM(CASE WHEN estado='degradado' THEN 1 ELSE 0 END)
                   AS avaliacoes_degradadas,
               SUM(confirmado) AS avaliacoes_confirmadas
        FROM historico_drift_simulacoes
        {filtro}
        GROUP BY mercado
        ORDER BY mercado
        """,
        parametros,
    ).fetchall()
    por_mercado = {
        linha[0]: {
            "total": int(linha[1] or 0),
            "primeiro_registro_em": linha[2],
            "ultimo_registro_em": linha[3],
            "avaliacoes_degradadas": int(linha[4] or 0),
            "avaliacoes_confirmadas": int(linha[5] or 0),
        }
        for linha in linhas
    }
    return {
        "total": sum(item["total"] for item in por_mercado.values()),
        "mercados": len(por_mercado),
        "por_mercado": por_mercado,
        "ultimo_registro_em": max(
            (
                item["ultimo_registro_em"]
                for item in por_mercado.values()
                if item["ultimo_registro_em"]
            ),
            default=None,
        ),
    }


def auditar_historico_drift_simulacoes(
    conexao, drift_atual, regra_versao=None
):
    drift_atual = drift_atual or {}
    regra_versao = (
        regra_versao
        or drift_atual.get("regra_versao")
    )
    regras_por_mercado = (
        drift_atual.get("regra_versoes_por_mercado") or {}
    )
    resumo = resumir_historico_drift_simulacoes(
        conexao,
        regra_versao,
        regras_por_mercado=regras_por_mercado,
    )
    atuais = {}
    for mercado, metricas in (drift_atual.get("mercados") or {}).items():
        decisao_id = (metricas or {}).get("ultima_decisao_id")
        if decisao_id is None:
            continue
        try:
            atuais[(str(mercado), int(decisao_id))] = metricas or {}
        except (TypeError, ValueError):
            continue
    filtro, parametros = _filtro_historico_drift(
        regra_versao, regras_por_mercado
    )
    linhas = conexao.execute(
        f"""
        SELECT mercado, ultima_decisao_id, metricas_json
        FROM historico_drift_simulacoes
        {filtro}
        """,
        parametros,
    ).fetchall()
    persistidos = {}
    json_invalidos = 0
    for linha in linhas:
        chave = (str(linha[0]), int(linha[1]))
        try:
            persistidos[chave] = json.loads(linha[2])
        except (TypeError, json.JSONDecodeError):
            json_invalidos += 1
    ausentes = sorted(
        f"{mercado}:{decisao_id}"
        for mercado, decisao_id in set(atuais) - set(persistidos)
    )
    campos = (
        "estado",
        "avaliavel",
        "amostra_recente",
        "amostra_base",
        "roi_recente",
        "roi_base",
        "delta_roi",
        "intervalo_delta_roi_95",
        "taxa_acerto_recente",
        "taxa_acerto_base",
        "ultimo_resultado_em",
    )
    divergentes = []
    for chave in sorted(set(atuais) & set(persistidos)):
        atual = atuais[chave]
        persistido = persistidos[chave]
        if any(persistido.get(campo) != atual.get(campo) for campo in campos):
            divergentes.append(f"{chave[0]}:{chave[1]}")
    duplicadas = conexao.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT regra_versao, mercado, ultima_decisao_id
            FROM historico_drift_simulacoes
            {filtro}
            GROUP BY regra_versao, mercado, ultima_decisao_id
            HAVING COUNT(*) > 1
        )
        """,
        parametros,
    ).fetchone()[0]
    saudavel = not (
        ausentes or divergentes or json_invalidos or duplicadas
    )
    return {
        "saudavel": saudavel,
        "estado": (
            "integro"
            if saudavel and atuais
            else "aguardando_resultados"
            if saudavel
            else "inconsistente"
        ),
        "motivo": None if saudavel else "historico_drift_inconsistente",
        **resumo,
        "chaves_atuais": len(atuais),
        "chaves_atuais_ausentes": ausentes,
        "chaves_atuais_divergentes": divergentes,
        "json_invalidos": int(json_invalidos),
        "chaves_duplicadas": int(duplicadas or 0),
    }


class BancoMonitor:
    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self.conexao = sqlite3.connect(self.caminho, timeout=30)
        self.conexao.row_factory = sqlite3.Row
        self.conexao.execute("PRAGMA journal_mode=WAL")
        self.conexao.execute("PRAGMA foreign_keys=ON")
        self.conexao.execute("PRAGMA synchronous=NORMAL")
        self._criar_esquema()

    def _criar_esquema(self):
        self.conexao.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadados (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS partidas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                packball_url TEXT NOT NULL UNIQUE,
                mandante TEXT NOT NULL,
                visitante TEXT NOT NULL,
                mandante_normalizado TEXT NOT NULL DEFAULT '',
                visitante_normalizado TEXT NOT NULL DEFAULT '',
                packball_partida_id INTEGER,
                pais TEXT,
                liga TEXT,
                liga_normalizada TEXT NOT NULL DEFAULT '',
                primeira_coleta TEXT NOT NULL,
                ultima_coleta TEXT NOT NULL,
                api_fixture_id INTEGER,
                api_orientacao TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partida_id INTEGER NOT NULL,
                coletado_em TEXT NOT NULL,
                placar TEXT,
                status TEXT,
                texto_linha TEXT,
                estatisticas_json TEXT NOT NULL DEFAULT '{}',
                evolucao_json TEXT NOT NULL DEFAULT '{}',
                confirmacao_api_json TEXT,
                estatisticas_api_json TEXT,
                contexto_api_json TEXT,
                qualidade_dados REAL,
                qualidade_json TEXT NOT NULL DEFAULT '{}',
                movimentacao_odds_json TEXT NOT NULL DEFAULT '[]',
                fontes_json TEXT NOT NULL DEFAULT '["packball"]',
                FOREIGN KEY (partida_id) REFERENCES partidas(id),
                UNIQUE (partida_id, coletado_em)
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_partida_data
            ON snapshots(partida_id, coletado_em DESC);

            CREATE TABLE IF NOT EXISTS odds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                mercado TEXT NOT NULL,
                dados TEXT NOT NULL,
                estrutura_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_odds_snapshot
            ON odds(snapshot_id);

            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                tipo TEXT,
                detalhe TEXT,
                minuto INTEGER,
                time_nome TEXT,
                jogador_nome TEXT,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_eventos_snapshot
            ON eventos(snapshot_id);

            CREATE TABLE IF NOT EXISTS sinais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partida_id INTEGER NOT NULL,
                snapshot_id INTEGER NOT NULL,
                criado_em TEXT NOT NULL,
                mercado TEXT NOT NULL,
                linha TEXT,
                odd REAL,
                pontuacao_tecnica REAL,
                probabilidade_calibrada REAL,
                regra_versao TEXT NOT NULL,
                regra_fingerprint TEXT,
                motivos_json TEXT NOT NULL DEFAULT '[]',
                features_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'candidato',
                FOREIGN KEY (partida_id) REFERENCES partidas(id),
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
            );

            CREATE TABLE IF NOT EXISTS resultados_sinais (
                sinal_id INTEGER PRIMARY KEY,
                encerrado_em TEXT NOT NULL,
                resultado TEXT NOT NULL,
                retorno_unidades REAL,
                observacao TEXT,
                snapshot_id_liquidacao INTEGER,
                fonte_resultado TEXT,
                FOREIGN KEY (sinal_id) REFERENCES sinais(id),
                FOREIGN KEY (snapshot_id_liquidacao) REFERENCES snapshots(id)
            );

            CREATE TABLE IF NOT EXISTS revisoes_resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sinal_id INTEGER NOT NULL,
                revisado_em TEXT NOT NULL,
                encerrado_em_anterior TEXT NOT NULL,
                resultado_anterior TEXT NOT NULL,
                retorno_anterior REAL,
                observacao_anterior TEXT,
                snapshot_id_liquidacao_anterior INTEGER,
                fonte_resultado_anterior TEXT,
                motivo TEXT NOT NULL,
                notificacao_status TEXT NOT NULL DEFAULT 'pendente',
                notificacao_erro TEXT,
                notificacao_provedor TEXT,
                notificacao_destino_id TEXT,
                notificacao_mensagem_id TEXT,
                notificacao_confirmacao_json TEXT,
                FOREIGN KEY (sinal_id) REFERENCES sinais(id),
                FOREIGN KEY (snapshot_id_liquidacao_anterior)
                    REFERENCES snapshots(id),
                UNIQUE (
                    sinal_id, encerrado_em_anterior, resultado_anterior
                )
            );

            CREATE TABLE IF NOT EXISTS calibracoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mercado TEXT NOT NULL,
                regra_versao TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                amostra INTEGER NOT NULL,
                ativa INTEGER NOT NULL DEFAULT 0,
                modelo_json TEXT NOT NULL,
                UNIQUE (mercado, regra_versao)
            );

            CREATE TABLE IF NOT EXISTS historico_calibracoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mercado TEXT NOT NULL,
                regra_versao TEXT NOT NULL,
                registrado_em TEXT NOT NULL,
                amostra INTEGER NOT NULL,
                ativa INTEGER NOT NULL,
                amostra_fingerprint TEXT NOT NULL DEFAULT '',
                motivo TEXT,
                modelo_hash TEXT NOT NULL,
                modelo_json TEXT NOT NULL,
                UNIQUE (mercado, regra_versao, modelo_hash)
            );

            CREATE INDEX IF NOT EXISTS idx_historico_calibracoes_estado
            ON historico_calibracoes(
                mercado, regra_versao, registrado_em DESC
            );

            CREATE TABLE IF NOT EXISTS historico_drift_simulacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regra_versao TEXT NOT NULL,
                mercado TEXT NOT NULL,
                registrado_em TEXT NOT NULL,
                ultima_decisao_id INTEGER NOT NULL,
                ultimo_resultado_em TEXT,
                estado TEXT NOT NULL,
                avaliavel INTEGER NOT NULL,
                amostra_recente INTEGER NOT NULL,
                amostra_base INTEGER NOT NULL,
                roi_recente REAL,
                roi_base REAL,
                delta_roi REAL,
                intervalo_delta_min REAL,
                intervalo_delta_max REAL,
                taxa_acerto_recente REAL,
                taxa_acerto_base REAL,
                confirmacoes INTEGER NOT NULL DEFAULT 0,
                confirmado INTEGER NOT NULL DEFAULT 0,
                metricas_json TEXT NOT NULL,
                UNIQUE (regra_versao, mercado, ultima_decisao_id)
            );

            CREATE INDEX IF NOT EXISTS idx_historico_drift_simulacoes_mercado
            ON historico_drift_simulacoes(
                regra_versao, mercado, registrado_em DESC
            );

            CREATE TABLE IF NOT EXISTS historico_avaliacao_contexto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regra_versao TEXT NOT NULL,
                mercado TEXT NOT NULL,
                registrado_em TEXT NOT NULL,
                ultimo_sinal_id INTEGER NOT NULL,
                amostra INTEGER NOT NULL,
                estado TEXT NOT NULL,
                pronto_para_revisao INTEGER NOT NULL DEFAULT 0,
                avaliacao_json TEXT NOT NULL,
                UNIQUE (regra_versao, mercado, ultimo_sinal_id)
            );

            CREATE INDEX IF NOT EXISTS
                idx_historico_avaliacao_contexto_mercado
            ON historico_avaliacao_contexto(
                regra_versao, mercado, registrado_em DESC
            );

            CREATE TABLE IF NOT EXISTS entregas_alertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sinal_id INTEGER NOT NULL,
                canal TEXT NOT NULL,
                tentado_em TEXT NOT NULL,
                entregue_em TEXT,
                status TEXT NOT NULL,
                erro TEXT,
                tentativas INTEGER NOT NULL DEFAULT 1,
                provedor TEXT,
                provedor_destino_id TEXT,
                provedor_mensagem_id TEXT,
                confirmacao_json TEXT,
                reserva_token TEXT,
                FOREIGN KEY (sinal_id) REFERENCES sinais(id),
                UNIQUE (sinal_id, canal, status)
            );

            CREATE TABLE IF NOT EXISTS notificacoes_operacionais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chave TEXT NOT NULL,
                destino TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                tentado_em TEXT NOT NULL,
                entregue_em TEXT,
                status TEXT NOT NULL,
                tentativas INTEGER NOT NULL DEFAULT 1,
                erro TEXT,
                provedor TEXT,
                provedor_mensagem_id TEXT,
                confirmacao_json TEXT,
                resumo TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_notificacoes_operacionais_fila
            ON notificacoes_operacionais(
                chave, destino, status, tentado_em DESC
            );

            CREATE TABLE IF NOT EXISTS cache_api_football (
                chave TEXT PRIMARY KEY,
                categoria TEXT NOT NULL,
                armazenado_em REAL NOT NULL,
                dados_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cache_api_football_categoria_tempo
            ON cache_api_football(categoria, armazenado_em DESC);

            CREATE TABLE IF NOT EXISTS taxas_ligas_gols_packball (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                league_id INTEGER NOT NULL,
                pais TEXT NOT NULL,
                liga TEXT NOT NULL,
                liga_normalizada TEXT NOT NULL,
                temporada TEXT NOT NULL,
                periodo TEXT NOT NULL
                    CHECK (periodo IN ('1t', '2t')),
                jogos_realizados INTEGER NOT NULL,
                jogos_previstos INTEGER,
                jogos_com_stats INTEGER NOT NULL,
                over_0_5 REAL,
                over_1_5 REAL,
                over_2_5 REAL,
                fonte TEXT NOT NULL DEFAULT 'packball_ligas_sazonal',
                coletado_em TEXT NOT NULL,
                versao TEXT NOT NULL,
                UNIQUE (league_id, temporada, periodo)
            );

            CREATE INDEX IF NOT EXISTS idx_taxas_ligas_gols_periodo
            ON taxas_ligas_gols_packball(
                periodo, coletado_em DESC, jogos_com_stats DESC
            );

            CREATE INDEX IF NOT EXISTS idx_taxas_ligas_gols_nome
            ON taxas_ligas_gols_packball(
                liga_normalizada, periodo, coletado_em DESC
            );

            CREATE TABLE IF NOT EXISTS historico_taxas_ligas_gols_packball (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                league_id INTEGER NOT NULL,
                pais TEXT NOT NULL,
                liga TEXT NOT NULL,
                liga_normalizada TEXT NOT NULL,
                temporada TEXT NOT NULL,
                periodo TEXT NOT NULL
                    CHECK (periodo IN ('1t', '2t')),
                jogos_realizados INTEGER NOT NULL,
                jogos_previstos INTEGER,
                jogos_com_stats INTEGER NOT NULL,
                over_0_5 REAL,
                over_1_5 REAL,
                over_2_5 REAL,
                fonte TEXT NOT NULL,
                coletado_em TEXT NOT NULL,
                versao TEXT NOT NULL,
                evidencia_sha256 TEXT NOT NULL,
                UNIQUE (league_id, temporada, periodo, coletado_em)
            );

            CREATE INDEX IF NOT EXISTS idx_historico_taxas_ligas_tempo
            ON historico_taxas_ligas_gols_packball(
                coletado_em DESC, league_id, periodo
            );

            CREATE INDEX IF NOT EXISTS idx_historico_taxas_ligas_chave_tempo
            ON historico_taxas_ligas_gols_packball(
                league_id, temporada, periodo, coletado_em DESC
            );

            CREATE TRIGGER IF NOT EXISTS
                trg_historico_taxas_ligas_update_imutavel
            BEFORE UPDATE ON historico_taxas_ligas_gols_packball
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'historico de taxas de ligas e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_historico_taxas_ligas_delete_imutavel
            BEFORE DELETE ON historico_taxas_ligas_gols_packball
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'historico de taxas de ligas e imutavel'
                );
            END;

            CREATE TABLE IF NOT EXISTS auditoria_fila_packball (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ciclo_em TEXT NOT NULL,
                registrado_em TEXT NOT NULL,
                packball_url TEXT NOT NULL,
                mandante TEXT,
                visitante TEXT,
                liga TEXT,
                minuto INTEGER,
                posicao INTEGER NOT NULL,
                processada INTEGER NOT NULL DEFAULT 0,
                acionavel INTEGER NOT NULL DEFAULT 0,
                fila_operacional TEXT NOT NULL DEFAULT 'exploracao',
                idade_segundos REAL,
                atraso_segundos REAL,
                em_foco INTEGER NOT NULL DEFAULT 0,
                scanner_prioritario INTEGER NOT NULL DEFAULT 0,
                pre_live_prioritario INTEGER NOT NULL DEFAULT 0,
                prioridade_liga_gols REAL,
                prioridade_indicadores_lista REAL,
                prioridade_api_lote REAL,
                janelas_temporais_json TEXT NOT NULL DEFAULT '[]',
                motivo TEXT NOT NULL,
                UNIQUE (ciclo_em, packball_url)
            );

            CREATE INDEX IF NOT EXISTS idx_auditoria_fila_packball_ciclo
            ON auditoria_fila_packball(
                ciclo_em DESC, processada, posicao
            );

            CREATE INDEX IF NOT EXISTS idx_auditoria_fila_packball_partida
            ON auditoria_fila_packball(packball_url, ciclo_em DESC);

            CREATE TABLE IF NOT EXISTS historico_api_live (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER NOT NULL,
                packball_url TEXT NOT NULL,
                coletado_em TEXT NOT NULL,
                minuto REAL,
                periodo TEXT,
                orientacao TEXT NOT NULL,
                chutes_mandante REAL,
                chutes_visitante REAL,
                chutes_gol_mandante REAL,
                chutes_gol_visitante REAL,
                escanteios_mandante REAL,
                escanteios_visitante REAL,
                xg_mandante REAL,
                xg_visitante REAL,
                completo INTEGER NOT NULL DEFAULT 0,
                fonte TEXT NOT NULL DEFAULT 'api_football',
                UNIQUE (fixture_id, packball_url, coletado_em)
            );

            CREATE INDEX IF NOT EXISTS idx_historico_api_live_fixture_tempo
            ON historico_api_live(
                fixture_id, packball_url, coletado_em DESC
            );

            CREATE INDEX IF NOT EXISTS idx_historico_api_live_tempo
            ON historico_api_live(coletado_em DESC);

            CREATE TABLE IF NOT EXISTS pareamentos_thestatsapi (
                packball_url TEXT PRIMARY KEY,
                match_id TEXT NOT NULL UNIQUE,
                orientacao TEXT NOT NULL
                    CHECK (orientacao IN ('direta', 'invertida')),
                similaridade REAL NOT NULL,
                margem REAL,
                mandante_api TEXT NOT NULL,
                visitante_api TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                diagnostico_json TEXT NOT NULL DEFAULT '{}'
                    CHECK (json_valid(diagnostico_json)),
                fonte TEXT NOT NULL DEFAULT 'thestatsapi'
                    CHECK (fonte='thestatsapi'),
                aplicacao_sinais INTEGER NOT NULL DEFAULT 0
                    CHECK (aplicacao_sinais=0)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_pareamentos_thestatsapi_match
            ON pareamentos_thestatsapi(match_id);

            CREATE INDEX IF NOT EXISTS
                idx_pareamentos_thestatsapi_atualizado
            ON pareamentos_thestatsapi(atualizado_em DESC);

            CREATE TABLE IF NOT EXISTS historico_thestatsapi_live (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                packball_url TEXT NOT NULL,
                coletado_em TEXT NOT NULL,
                minuto REAL,
                periodo TEXT,
                placar TEXT,
                placar_mandante REAL,
                placar_visitante REAL,
                orientacao TEXT
                    CHECK (
                        orientacao IS NULL
                        OR orientacao IN ('direta', 'invertida')
                    ),
                chutes_mandante REAL,
                chutes_visitante REAL,
                chutes_gol_mandante REAL,
                chutes_gol_visitante REAL,
                escanteios_mandante REAL,
                escanteios_visitante REAL,
                xg_mandante REAL,
                xg_visitante REAL,
                completo INTEGER NOT NULL DEFAULT 0
                    CHECK (completo IN (0, 1)),
                fonte TEXT NOT NULL DEFAULT 'thestatsapi'
                    CHECK (fonte='thestatsapi'),
                aplicacao_sinais INTEGER NOT NULL DEFAULT 0
                    CHECK (aplicacao_sinais=0),
                UNIQUE (match_id, packball_url, coletado_em)
            );

            CREATE INDEX IF NOT EXISTS idx_thestatsapi_live_match_tempo
            ON historico_thestatsapi_live(
                match_id, packball_url, coletado_em DESC
            );

            CREATE INDEX IF NOT EXISTS idx_thestatsapi_live_tempo
            ON historico_thestatsapi_live(coletado_em DESC);

            CREATE TABLE IF NOT EXISTS odds_thestatsapi_live (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                packball_url TEXT NOT NULL,
                coletado_em TEXT NOT NULL,
                bookmaker TEXT NOT NULL,
                mercado TEXT NOT NULL,
                mercado_origem TEXT NOT NULL,
                categoria TEXT NOT NULL,
                tipo_mercado TEXT NOT NULL,
                periodo TEXT NOT NULL,
                linha REAL NOT NULL,
                odd_over REAL,
                odd_under REAL,
                fonte TEXT NOT NULL DEFAULT 'thestatsapi'
                    CHECK (fonte='thestatsapi'),
                aplicacao_sinais INTEGER NOT NULL DEFAULT 0
                    CHECK (aplicacao_sinais=0),
                CHECK (odd_over IS NOT NULL OR odd_under IS NOT NULL),
                UNIQUE (
                    match_id, packball_url, coletado_em, bookmaker,
                    mercado, tipo_mercado, periodo, linha
                )
            );

            CREATE INDEX IF NOT EXISTS idx_odds_thestatsapi_match_tempo
            ON odds_thestatsapi_live(
                match_id, packball_url, coletado_em DESC
            );

            CREATE INDEX IF NOT EXISTS idx_odds_thestatsapi_tempo
            ON odds_thestatsapi_live(coletado_em DESC);

            CREATE INDEX IF NOT EXISTS idx_odds_thestatsapi_mercado
            ON odds_thestatsapi_live(
                categoria, tipo_mercado, periodo, bookmaker,
                coletado_em DESC
            );

            CREATE TABLE IF NOT EXISTS consultas_finalizacao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partida_id INTEGER NOT NULL,
                fonte TEXT NOT NULL,
                consultado_em TEXT NOT NULL,
                estado TEXT NOT NULL,
                status_observado TEXT,
                placar_observado TEXT,
                erro TEXT,
                FOREIGN KEY (partida_id) REFERENCES partidas(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_consultas_finalizacao
            ON consultas_finalizacao(partida_id, fonte, consultado_em DESC);

            CREATE TABLE IF NOT EXISTS observacoes_fontes_odds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partida_id INTEGER,
                fonte TEXT NOT NULL,
                consultado_em TEXT NOT NULL,
                estado TEXT NOT NULL,
                evento_externo_id TEXT,
                mandante_observado TEXT,
                visitante_observado TEXT,
                periodo TEXT,
                mercado TEXT,
                motivo TEXT,
                oferta_json TEXT,
                url_origem TEXT,
                metodo_coleta TEXT NOT NULL DEFAULT 'automatizada',
                metadados_json TEXT NOT NULL DEFAULT '{}'
                    CHECK (json_valid(metadados_json)),
                evidencia_sha256 TEXT,
                evidencia_referencia TEXT,
                FOREIGN KEY (partida_id) REFERENCES partidas(id)
                    ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_observacoes_fontes_odds_fonte_tempo
            ON observacoes_fontes_odds(
                fonte, consultado_em DESC, estado
            );

            CREATE INDEX IF NOT EXISTS
                idx_observacoes_fontes_odds_referencia_tempo
            ON observacoes_fontes_odds(
                evidencia_referencia, consultado_em DESC, id DESC
            );

            CREATE TABLE IF NOT EXISTS comparacoes_odds_fontes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                partida_id INTEGER NOT NULL,
                observado_em TEXT NOT NULL,
                placar TEXT,
                status TEXT,
                minuto REAL,
                categoria TEXT NOT NULL,
                escopo TEXT NOT NULL,
                periodo TEXT NOT NULL,
                linha REAL NOT NULL,
                selecao TEXT NOT NULL,
                fonte_a TEXT NOT NULL,
                bookmaker_a TEXT NOT NULL DEFAULT '',
                odd_a REAL NOT NULL,
                coletado_em_a TEXT,
                snapshot_fonte_a INTEGER,
                placar_fonte_a TEXT,
                status_fonte_a TEXT,
                minuto_fonte_a REAL,
                fonte_b TEXT NOT NULL,
                bookmaker_b TEXT NOT NULL DEFAULT '',
                odd_b REAL NOT NULL,
                coletado_em_b TEXT,
                snapshot_fonte_b INTEGER,
                placar_fonte_b TEXT,
                status_fonte_b TEXT,
                minuto_fonte_b REAL,
                fonte_melhor TEXT NOT NULL,
                bookmaker_melhor TEXT NOT NULL DEFAULT '',
                odd_melhor REAL NOT NULL,
                fonte_controle TEXT NOT NULL,
                bookmaker_controle TEXT NOT NULL DEFAULT '',
                odd_controle REAL NOT NULL,
                delta_absoluto REAL NOT NULL,
                delta_relativo REAL NOT NULL,
                intervalo_fontes_segundos REAL,
                frescor_maximo_segundos REAL,
                diferenca_minutos REAL,
                compatibilidade_bookmaker TEXT NOT NULL,
                estado TEXT NOT NULL,
                motivos_json TEXT NOT NULL,
                versao TEXT NOT NULL,
                evidencia_sha256 TEXT NOT NULL,
                UNIQUE (
                    snapshot_id, categoria, escopo, periodo, linha,
                    selecao, fonte_a, bookmaker_a, fonte_b, bookmaker_b
                )
            );

            CREATE INDEX IF NOT EXISTS idx_comparacoes_odds_estado_tempo
            ON comparacoes_odds_fontes(
                estado, observado_em DESC, categoria, periodo
            );

            CREATE INDEX IF NOT EXISTS idx_comparacoes_odds_chave_tempo
            ON comparacoes_odds_fontes(
                partida_id, categoria, escopo, periodo, linha, selecao,
                observado_em DESC
            );

            CREATE TRIGGER IF NOT EXISTS
                trg_comparacoes_odds_update_imutavel
            BEFORE UPDATE ON comparacoes_odds_fontes
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'comparacao temporal de odds e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_comparacoes_odds_delete_imutavel
            BEFORE DELETE ON comparacoes_odds_fontes
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'comparacao temporal de odds e imutavel'
                );
            END;

            CREATE INDEX IF NOT EXISTS idx_sinais_calibracao
            ON sinais(regra_versao, mercado, status, odd, partida_id);

            CREATE INDEX IF NOT EXISTS idx_sinais_partida_status
            ON sinais(partida_id, status, id);

            CREATE INDEX IF NOT EXISTS idx_sinais_grupo_independente
            ON sinais(partida_id, mercado, regra_versao, status, id);

            CREATE INDEX IF NOT EXISTS idx_sinais_snapshot
            ON sinais(snapshot_id);

            CREATE INDEX IF NOT EXISTS idx_sinais_criado_em
            ON sinais(criado_em);

            CREATE INDEX IF NOT EXISTS idx_entregas_alertas_tentado_em
            ON entregas_alertas(tentado_em, status);
            """
        )
        instalar_gatilhos_estimativa_historica(self.conexao)
        colunas = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(snapshots)"
            ).fetchall()
        }
        if "fontes_json" not in colunas:
            self.conexao.execute(
                """
                ALTER TABLE snapshots
                ADD COLUMN fontes_json TEXT NOT NULL DEFAULT '["packball"]'
                """
            )
        if "qualidade_json" not in colunas:
            self.conexao.execute(
                """
                ALTER TABLE snapshots
                ADD COLUMN qualidade_json TEXT NOT NULL DEFAULT '{}'
                """
            )
        if "movimentacao_odds_json" not in colunas:
            self.conexao.execute(
                """
                ALTER TABLE snapshots
                ADD COLUMN movimentacao_odds_json TEXT NOT NULL DEFAULT '[]'
                """
            )
        if "contexto_api_json" not in colunas:
            self.conexao.execute(
                "ALTER TABLE snapshots ADD COLUMN contexto_api_json TEXT"
            )
        colunas_comparacoes_odds = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(comparacoes_odds_fontes)"
            ).fetchall()
        }
        for nome, definicao in (
            ("snapshot_fonte_a", "INTEGER"),
            ("placar_fonte_a", "TEXT"),
            ("status_fonte_a", "TEXT"),
            ("minuto_fonte_a", "REAL"),
            ("snapshot_fonte_b", "INTEGER"),
            ("placar_fonte_b", "TEXT"),
            ("status_fonte_b", "TEXT"),
            ("minuto_fonte_b", "REAL"),
            ("diferenca_minutos", "REAL"),
        ):
            if nome not in colunas_comparacoes_odds:
                self.conexao.execute(
                    "ALTER TABLE comparacoes_odds_fontes "
                    f"ADD COLUMN {nome} {definicao}"
                )
        colunas_sinais = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(sinais)"
            ).fetchall()
        }
        if "features_json" not in colunas_sinais:
            self.conexao.execute(
                """
                ALTER TABLE sinais
                ADD COLUMN features_json TEXT NOT NULL DEFAULT '{}'
                """
            )
        if "regra_fingerprint" not in colunas_sinais:
            self.conexao.execute(
                "ALTER TABLE sinais ADD COLUMN regra_fingerprint TEXT"
            )
        definicao_independencia = """
            CREATE TRIGGER IF NOT EXISTS
                trg_sinais_exploracao_sombra_independente
            BEFORE INSERT ON sinais
            WHEN json_extract(
                NEW.features_json,
                '$.exploracao_sombra.versao'
            ) IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM sinais existente
                  WHERE existente.partida_id=NEW.partida_id
                    AND existente.mercado=NEW.mercado
                    AND NOT (
                        existente.status='rejeitado'
                        AND COALESCE(json_extract(
                            existente.features_json,
                            '$.acompanhamento_odd.elegivel_aviso'
                        ), 0)=1
                        AND NEW.status IN ('aprovado', 'simulacao')
                        AND COALESCE(json_extract(
                            NEW.features_json,
                            '$.acompanhamento_odd_rapido.leitura_tecnica_sinal_id'
                        ), 0)=existente.id
                        AND NOT EXISTS (
                            SELECT 1 FROM resultados_sinais resultado
                            WHERE resultado.sinal_id=existente.id
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM entregas_alertas envio
                            WHERE envio.sinal_id=existente.id
                              AND envio.status='entregue'
                              AND envio.canal NOT LIKE '%:aguardar_odd'
                        )
                    )
                    AND json_extract(
                        existente.features_json,
                        '$.exploracao_sombra.versao'
                    )=json_extract(
                        NEW.features_json,
                        '$.exploracao_sombra.versao'
                    )
              )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'exploracao sombra repetida para partida e mercado'
                );
            END
            """
        nome_independencia = "trg_sinais_exploracao_sombra_independente"
        anterior = self.conexao.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
            (nome_independencia,),
        ).fetchone()
        if anterior and "leitura_tecnica_sinal_id" not in (anterior["sql"] or ""):
            # Preserva o nome exigido também nos backups anteriores. Instala
            # a proteção nova antes de substituir a antiga, em transação.
            with self.conexao:
                self.conexao.execute(definicao_independencia.replace(
                    nome_independencia, nome_independencia + "_transicao"
                ))
                self.conexao.execute(f"DROP TRIGGER {nome_independencia}")
                self.conexao.execute(definicao_independencia)
                self.conexao.execute(f"DROP TRIGGER {nome_independencia}_transicao")
        else:
            self.conexao.execute(definicao_independencia)
        self.conexao.execute(f"DROP TRIGGER IF EXISTS {nome_independencia}_v2")
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_sinais_exploracao_sombra_update_imutavel
            BEFORE UPDATE ON sinais
            WHEN json_extract(
                OLD.features_json,
                '$.exploracao_sombra.versao'
            ) IS NOT NULL
              OR json_extract(
                  NEW.features_json,
                  '$.exploracao_sombra.versao'
              ) IS NOT NULL
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'evidencia da exploracao sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_sinais_exploracao_sombra_delete_imutavel
            BEFORE DELETE ON sinais
            WHEN json_extract(
                OLD.features_json,
                '$.exploracao_sombra.versao'
            ) IS NOT NULL
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'evidencia da exploracao sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sinais_linhagem_calibracao
            ON sinais(
                regra_versao, regra_fingerprint, mercado,
                status, odd, partida_id
            )
            """
        )
        # Estes índices dependem de colunas adicionadas pela migração acima.
        # Criá-los antes dela impediria a abertura de bancos antigos.
        self.conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sinais_regra_linhagem_tempo
            ON sinais(regra_versao, regra_fingerprint, criado_em)
            """
        )
        self.conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sinais_exploracao_versao
            ON sinais(
                json_extract(features_json, '$.exploracao_sombra.versao')
            )
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_sinais_linhagem_imutavel
            BEFORE UPDATE OF regra_versao, regra_fingerprint ON sinais
            WHEN OLD.regra_versao IS NOT NEW.regra_versao
              OR OLD.regra_fingerprint IS NOT NEW.regra_fingerprint
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'regra_versao e regra_fingerprint sao imutaveis'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_historico_contexto_update_imutavel
            BEFORE UPDATE ON historico_avaliacao_contexto
            BEGIN
                SELECT RAISE(
                    ABORT, 'historico_avaliacao_contexto e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_historico_contexto_delete_imutavel
            BEFORE DELETE ON historico_avaliacao_contexto
            BEGIN
                SELECT RAISE(
                    ABORT, 'historico_avaliacao_contexto e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_pontuacao_sombra_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'pontuacao_sombra:%'
              OR NEW.chave LIKE 'pontuacao_sombra:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'modelo da pontuacao sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_pontuacao_sombra_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'pontuacao_sombra:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'modelo da pontuacao sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_experimento_filtro_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'experimento_filtro_teste:%'
              OR NEW.chave LIKE 'experimento_filtro_teste:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'marco do experimento de filtro e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_experimento_filtro_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'experimento_filtro_teste:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'marco do experimento de filtro e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_conclusao_experimento_filtro_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'conclusao_experimento_filtro:%'
              OR NEW.chave LIKE 'conclusao_experimento_filtro:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'conclusao do experimento de filtro e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_conclusao_experimento_filtro_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'conclusao_experimento_filtro:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'conclusao do experimento de filtro e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_hipotese_sombra_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'hipotese_sombra:%'
              OR NEW.chave LIKE 'hipotese_sombra:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'definicao da hipotese sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_hipotese_sombra_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'hipotese_sombra:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'definicao da hipotese sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_exploracao_sombra_definicao_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'exploracao_sombra_definicao:%'
              OR NEW.chave LIKE 'exploracao_sombra_definicao:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'definicao da exploracao sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_exploracao_sombra_definicao_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'exploracao_sombra_definicao:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'definicao da exploracao sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_exploracao_sombra_politica_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'exploracao_sombra_politica:%'
              OR NEW.chave LIKE 'exploracao_sombra_politica:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'politica da exploracao sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_exploracao_sombra_politica_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'exploracao_sombra_politica:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'politica da exploracao sombra e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_auditoria_ligas_prospectiva_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'auditoria_ligas_prospectiva:%'
              OR NEW.chave LIKE 'auditoria_ligas_prospectiva:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'ancora prospectiva de ligas e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_auditoria_ligas_prospectiva_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'auditoria_ligas_prospectiva:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'ancora prospectiva de ligas e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_avaliacao_desajuste_odds_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'avaliacao_desajuste_odds:%'
              OR NEW.chave LIKE 'avaliacao_desajuste_odds:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'ancora prospectiva de desajuste de odds e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_avaliacao_desajuste_odds_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'avaliacao_desajuste_odds:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'ancora prospectiva de desajuste de odds e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_avaliacao_contexto_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'avaliacao_contexto:causal_v6:%'
              OR NEW.chave LIKE 'avaliacao_contexto:causal_v6:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'ancora prospectiva de contexto e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_avaliacao_probabilidade_individual_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'avaliacao_probabilidade_individual:%'
              OR NEW.chave LIKE 'avaliacao_probabilidade_individual:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'definicao e previsao de probabilidade individual sao imutaveis'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_avaliacao_probabilidade_individual_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'avaliacao_probabilidade_individual:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'definicao e previsao de probabilidade individual sao imutaveis'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_avaliacao_contexto_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'avaliacao_contexto:causal_v6:%'
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'ancora prospectiva de contexto e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_carteira_operacional_epoca_update_imutavel
            BEFORE UPDATE ON metadados
            WHEN OLD.chave LIKE 'carteira_operacional:epoca:%'
              OR NEW.chave LIKE 'carteira_operacional:epoca:%'
            BEGIN
                SELECT RAISE(
                    ABORT, 'epoca da carteira operacional e imutavel'
                );
            END
            """
        )
        self.conexao.execute(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_carteira_operacional_epoca_delete_imutavel
            BEFORE DELETE ON metadados
            WHEN OLD.chave LIKE 'carteira_operacional:epoca:%'
            BEGIN
                SELECT RAISE(
                    ABORT, 'epoca da carteira operacional e imutavel'
                );
            END
            """
        )
        colunas_partidas = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(partidas)"
            ).fetchall()
        }
        for nome, definicao in (
            ("mandante_normalizado", "TEXT NOT NULL DEFAULT ''"),
            ("visitante_normalizado", "TEXT NOT NULL DEFAULT ''"),
            ("packball_partida_id", "INTEGER"),
            ("pais", "TEXT"),
            ("liga", "TEXT"),
            ("liga_normalizada", "TEXT NOT NULL DEFAULT ''"),
            ("api_orientacao", "TEXT"),
        ):
            if nome not in colunas_partidas:
                self.conexao.execute(
                    f"ALTER TABLE partidas ADD COLUMN {nome} {definicao}"
                )
        colunas_odds = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(odds)"
            ).fetchall()
        }
        if "estrutura_json" not in colunas_odds:
            self.conexao.execute(
                """
                ALTER TABLE odds
                ADD COLUMN estrutura_json TEXT NOT NULL DEFAULT '{}'
                """
            )
        colunas_observacoes_odds = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(observacoes_fontes_odds)"
            ).fetchall()
        }
        for nome, definicao in (
            (
                "metodo_coleta",
                "TEXT NOT NULL DEFAULT 'automatizada'",
            ),
            (
                "metadados_json",
                "TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadados_json))",
            ),
            ("evidencia_sha256", "TEXT"),
            ("evidencia_referencia", "TEXT"),
        ):
            if nome not in colunas_observacoes_odds:
                self.conexao.execute(
                    "ALTER TABLE observacoes_fontes_odds "
                    f"ADD COLUMN {nome} {definicao}"
                )
        colunas_entregas = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(entregas_alertas)"
            ).fetchall()
        }
        if "tentativas" not in colunas_entregas:
            self.conexao.execute(
                """
                ALTER TABLE entregas_alertas
                ADD COLUMN tentativas INTEGER NOT NULL DEFAULT 1
                """
            )
        for nome, definicao in (
            ("provedor", "TEXT"),
            ("provedor_destino_id", "TEXT"),
            ("provedor_mensagem_id", "TEXT"),
            ("confirmacao_json", "TEXT"),
            ("reserva_token", "TEXT"),
        ):
            if nome not in colunas_entregas:
                self.conexao.execute(
                    f"ALTER TABLE entregas_alertas ADD COLUMN {nome} {definicao}"
                )
        colunas_notificacoes = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(notificacoes_operacionais)"
            ).fetchall()
        }
        if "resumo" not in colunas_notificacoes:
            self.conexao.execute(
                "ALTER TABLE notificacoes_operacionais ADD COLUMN resumo TEXT"
            )
        colunas_resultados = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(resultados_sinais)"
            ).fetchall()
        }
        if "snapshot_id_liquidacao" not in colunas_resultados:
            self.conexao.execute(
                """
                ALTER TABLE resultados_sinais
                ADD COLUMN snapshot_id_liquidacao INTEGER
                    REFERENCES snapshots(id)
                """
            )
        if "fonte_resultado" not in colunas_resultados:
            self.conexao.execute(
                """
                ALTER TABLE resultados_sinais
                ADD COLUMN fonte_resultado TEXT
                """
            )
        colunas_revisoes = {
            linha["name"]
            for linha in self.conexao.execute(
                "PRAGMA table_info(revisoes_resultados)"
            ).fetchall()
        }
        if "snapshot_id_liquidacao_anterior" not in colunas_revisoes:
            self.conexao.execute(
                """
                ALTER TABLE revisoes_resultados
                ADD COLUMN snapshot_id_liquidacao_anterior INTEGER
                    REFERENCES snapshots(id)
                """
            )
        if "fonte_resultado_anterior" not in colunas_revisoes:
            self.conexao.execute(
                """
                ALTER TABLE revisoes_resultados
                ADD COLUMN fonte_resultado_anterior TEXT
                """
            )
        for nome in (
            "notificacao_provedor",
            "notificacao_destino_id",
            "notificacao_mensagem_id",
            "notificacao_confirmacao_json",
        ):
            if nome not in colunas_revisoes:
                self.conexao.execute(
                    f"ALTER TABLE revisoes_resultados ADD COLUMN {nome} TEXT"
                )
        self.conexao.execute(
            """
            UPDATE resultados_sinais AS r
            SET snapshot_id_liquidacao=(
                SELECT sn.id
                FROM sinais s
                JOIN snapshots sn ON sn.partida_id=s.partida_id
                WHERE s.id=r.sinal_id
                  AND sn.coletado_em=r.encerrado_em
                ORDER BY sn.id DESC LIMIT 1
            )
            WHERE r.snapshot_id_liquidacao IS NULL
              AND r.resultado <> 'sem_dado'
            """
        )
        self.conexao.execute(
            """
            UPDATE resultados_sinais
            SET fonte_resultado=CASE
                WHEN resultado='sem_dado' THEN 'sem_dado'
                WHEN snapshot_id_liquidacao IS NULL THEN NULL
                WHEN EXISTS (
                    SELECT 1 FROM snapshots sn
                    WHERE sn.id=snapshot_id_liquidacao
                      AND sn.fontes_json LIKE '%api_football%'
                ) THEN 'api_football'
                ELSE 'packball'
            END
            WHERE fonte_resultado IS NULL
            """
        )
        partidas_sem_normalizacao = self.conexao.execute(
            """
            SELECT id, packball_url, mandante, visitante
            FROM partidas
            WHERE mandante_normalizado=''
               OR visitante_normalizado=''
               OR packball_partida_id IS NULL
            """
        ).fetchall()
        for partida in partidas_sem_normalizacao:
            self.conexao.execute(
                """
                UPDATE partidas SET
                    mandante_normalizado=?,
                    visitante_normalizado=?,
                    packball_partida_id=COALESCE(?, packball_partida_id)
                WHERE id=?
                """,
                (
                    normalizar_texto(partida["mandante"]),
                    normalizar_texto(partida["visitante"]),
                    extrair_packball_id(partida["packball_url"]),
                    partida["id"],
                ),
            )
        partidas_sem_orientacao = self.conexao.execute(
            """
            SELECT p.id,
                   (
                       SELECT s.confirmacao_api_json
                       FROM snapshots s
                       WHERE s.partida_id=p.id
                         AND s.confirmacao_api_json NOT IN ('null', '{}', '')
                       ORDER BY s.id DESC LIMIT 1
                   ) AS confirmacao_api_json
            FROM partidas p
            WHERE p.api_fixture_id IS NOT NULL AND p.api_orientacao IS NULL
            """
        ).fetchall()
        for partida in partidas_sem_orientacao:
            try:
                confirmacao = json.loads(
                    partida["confirmacao_api_json"] or "null"
                ) or {}
            except json.JSONDecodeError:
                continue
            orientacao = confirmacao.get("orientacao")
            if orientacao not in ("direta", "invertida"):
                continue
            self.conexao.execute(
                "UPDATE partidas SET api_orientacao=? WHERE id=?",
                (orientacao, partida["id"]),
            )
        calibracoes_sem_historico = self.conexao.execute(
            """
            SELECT mercado, regra_versao, atualizado_em, amostra,
                   ativa, modelo_json
            FROM calibracoes
            """
        ).fetchall()
        for calibracao in calibracoes_sem_historico:
            try:
                modelo = json.loads(calibracao["modelo_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            modelo_json = json.dumps(
                modelo,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            modelo_hash = hashlib.sha256(
                modelo_json.encode("utf-8")
            ).hexdigest()
            self.conexao.execute(
                """
                INSERT OR IGNORE INTO historico_calibracoes (
                    mercado, regra_versao, registrado_em, amostra, ativa,
                    amostra_fingerprint, motivo, modelo_hash, modelo_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    calibracao["mercado"],
                    calibracao["regra_versao"],
                    calibracao["atualizado_em"],
                    calibracao["amostra"],
                    calibracao["ativa"],
                    modelo.get("amostra_fingerprint") or "",
                    modelo.get("motivo"),
                    modelo_hash,
                    modelo_json,
                ),
            )
        self.conexao.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS
                trg_resultados_sinais_update_imutavel
            BEFORE UPDATE ON resultados_sinais
            WHEN OLD.encerrado_em IS NOT NEW.encerrado_em
              OR OLD.resultado IS NOT NEW.resultado
              OR OLD.retorno_unidades IS NOT NEW.retorno_unidades
              OR OLD.observacao IS NOT NEW.observacao
              OR OLD.snapshot_id_liquidacao IS NOT NEW.snapshot_id_liquidacao
              OR OLD.fonte_resultado IS NOT NEW.fonte_resultado
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'resultados_sinais sao imutaveis; registre uma revisao'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_resultados_sinais_delete_auditado
            BEFORE DELETE ON resultados_sinais
            WHEN NOT EXISTS (
                SELECT 1
                FROM revisoes_resultados AS revisao
                WHERE revisao.sinal_id=OLD.sinal_id
                  AND revisao.encerrado_em_anterior IS OLD.encerrado_em
                  AND revisao.resultado_anterior IS OLD.resultado
                  AND revisao.retorno_anterior IS OLD.retorno_unidades
                  AND revisao.observacao_anterior IS OLD.observacao
                  AND (
                      (
                          revisao.snapshot_id_liquidacao_anterior
                              IS OLD.snapshot_id_liquidacao
                          AND revisao.fonte_resultado_anterior
                              IS OLD.fonte_resultado
                      )
                      OR (
                          revisao.snapshot_id_liquidacao_anterior IS NULL
                          AND revisao.fonte_resultado_anterior IS NULL
                      )
                  )
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'exclusao de resultado exige revisao correspondente'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_revisoes_resultados_insert_coerente
            BEFORE INSERT ON revisoes_resultados
            WHEN EXISTS (
                SELECT 1
                FROM resultados_sinais AS resultado
                WHERE resultado.sinal_id=NEW.sinal_id
                  AND (
                      resultado.encerrado_em
                          IS NOT NEW.encerrado_em_anterior
                      OR resultado.resultado
                          IS NOT NEW.resultado_anterior
                      OR resultado.retorno_unidades
                          IS NOT NEW.retorno_anterior
                      OR resultado.observacao
                          IS NOT NEW.observacao_anterior
                      OR resultado.snapshot_id_liquidacao
                          IS NOT NEW.snapshot_id_liquidacao_anterior
                      OR resultado.fonte_resultado
                          IS NOT NEW.fonte_resultado_anterior
                  )
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'revisao nao corresponde ao resultado persistido'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_revisoes_resultados_evidencia_imutavel
            BEFORE UPDATE OF
                sinal_id, revisado_em, encerrado_em_anterior,
                resultado_anterior, retorno_anterior, observacao_anterior,
                snapshot_id_liquidacao_anterior, fonte_resultado_anterior,
                motivo
            ON revisoes_resultados
            WHEN OLD.sinal_id IS NOT NEW.sinal_id
              OR OLD.revisado_em IS NOT NEW.revisado_em
              OR OLD.encerrado_em_anterior IS NOT NEW.encerrado_em_anterior
              OR OLD.resultado_anterior IS NOT NEW.resultado_anterior
              OR OLD.retorno_anterior IS NOT NEW.retorno_anterior
              OR OLD.observacao_anterior IS NOT NEW.observacao_anterior
              OR OLD.snapshot_id_liquidacao_anterior
                    IS NOT NEW.snapshot_id_liquidacao_anterior
              OR OLD.fonte_resultado_anterior
                    IS NOT NEW.fonte_resultado_anterior
              OR OLD.motivo IS NOT NEW.motivo
            BEGIN
                SELECT RAISE(ABORT, 'evidencia de revisao e imutavel');
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_revisoes_resultados_delete_imutavel
            BEFORE DELETE ON revisoes_resultados
            BEGIN
                SELECT RAISE(ABORT, 'revisoes_resultados sao imutaveis');
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_historico_calibracoes_update_imutavel
            BEFORE UPDATE ON historico_calibracoes
            BEGIN
                SELECT RAISE(ABORT, 'historico_calibracoes e imutavel');
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_historico_calibracoes_delete_imutavel
            BEFORE DELETE ON historico_calibracoes
            BEGIN
                SELECT RAISE(ABORT, 'historico_calibracoes e imutavel');
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_historico_drift_update_imutavel
            BEFORE UPDATE ON historico_drift_simulacoes
            BEGIN
                SELECT RAISE(
                    ABORT, 'historico_drift_simulacoes e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_historico_drift_delete_imutavel
            BEFORE DELETE ON historico_drift_simulacoes
            BEGIN
                SELECT RAISE(
                    ABORT, 'historico_drift_simulacoes e imutavel'
                );
            END;

            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_entregas_telegram_mensagem_unica
            ON entregas_alertas(
                provedor, provedor_destino_id, provedor_mensagem_id
            )
            WHERE provedor='telegram'
              AND provedor_destino_id IS NOT NULL
              AND provedor_mensagem_id IS NOT NULL;

            CREATE TRIGGER IF NOT EXISTS
                trg_entregas_alertas_prova_imutavel
            BEFORE UPDATE OF
                provedor, provedor_destino_id, provedor_mensagem_id,
                confirmacao_json
            ON entregas_alertas
            WHEN (
                    OLD.provedor IS NOT NULL
                    OR OLD.provedor_destino_id IS NOT NULL
                    OR OLD.provedor_mensagem_id IS NOT NULL
                    OR OLD.confirmacao_json IS NOT NULL
                 )
             AND (
                    OLD.provedor IS NOT NEW.provedor
                    OR OLD.provedor_destino_id
                        IS NOT NEW.provedor_destino_id
                    OR OLD.provedor_mensagem_id
                        IS NOT NEW.provedor_mensagem_id
                    OR OLD.confirmacao_json IS NOT NEW.confirmacao_json
                 )
            BEGIN
                SELECT RAISE(ABORT, 'prova de entrega e imutavel');
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_entregas_alertas_entrada_update_imutavel
            BEFORE UPDATE OF
                sinal_id, canal, tentado_em, entregue_em, status
            ON entregas_alertas
            WHEN OLD.status='entregue'
             AND OLD.canal NOT LIKE 'gateway:%'
             AND INSTR(OLD.canal, ':resultado')=0
             AND INSTR(OLD.canal, ':green_antecipado')=0
             AND INSTR(OLD.canal, ':aguardar_odd')=0
             AND INSTR(OLD.canal, ':cancelamento')=0
             AND INSTR(OLD.canal, ':insuficiente')=0
             AND INSTR(OLD.canal, ':monitoramento_final')=0
             AND INSTR(OLD.canal, ':correcao')=0
             AND (
                    OLD.sinal_id IS NOT NEW.sinal_id
                    OR OLD.canal IS NOT NEW.canal
                    OR OLD.tentado_em IS NOT NEW.tentado_em
                    OR OLD.entregue_em IS NOT NEW.entregue_em
                    OR OLD.status IS NOT NEW.status
                 )
            BEGIN
                SELECT RAISE(
                    ABORT, 'entrega de entrada confirmada e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_entregas_alertas_entrada_delete_imutavel
            BEFORE DELETE ON entregas_alertas
            WHEN OLD.status='entregue'
             AND OLD.canal NOT LIKE 'gateway:%'
             AND INSTR(OLD.canal, ':resultado')=0
             AND INSTR(OLD.canal, ':green_antecipado')=0
             AND INSTR(OLD.canal, ':aguardar_odd')=0
             AND INSTR(OLD.canal, ':cancelamento')=0
             AND INSTR(OLD.canal, ':insuficiente')=0
             AND INSTR(OLD.canal, ':monitoramento_final')=0
             AND INSTR(OLD.canal, ':correcao')=0
            BEGIN
                SELECT RAISE(
                    ABORT, 'entrega de entrada confirmada e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_sinais_entregues_evidencia_update_imutavel
            BEFORE UPDATE OF
                partida_id, snapshot_id, criado_em, mercado, linha, odd,
                features_json
            ON sinais
            WHEN EXISTS (
                SELECT 1 FROM entregas_alertas e
                WHERE e.sinal_id=OLD.id AND e.status='entregue'
                  AND e.canal NOT LIKE 'gateway:%'
                  AND INSTR(e.canal, ':resultado')=0
                  AND INSTR(e.canal, ':green_antecipado')=0
                  AND INSTR(e.canal, ':aguardar_odd')=0
                  AND INSTR(e.canal, ':cancelamento')=0
                  AND INSTR(e.canal, ':insuficiente')=0
                  AND INSTR(e.canal, ':monitoramento_final')=0
                  AND INSTR(e.canal, ':correcao')=0
             )
             AND (
                    OLD.partida_id IS NOT NEW.partida_id
                    OR OLD.snapshot_id IS NOT NEW.snapshot_id
                    OR OLD.criado_em IS NOT NEW.criado_em
                    OR OLD.mercado IS NOT NEW.mercado
                    OR OLD.linha IS NOT NEW.linha
                    OR OLD.odd IS NOT NEW.odd
                    OR OLD.features_json IS NOT NEW.features_json
                 )
            BEGIN
                SELECT RAISE(
                    ABORT, 'evidencia do sinal entregue e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_sinais_entregues_evidencia_delete_imutavel
            BEFORE DELETE ON sinais
            WHEN EXISTS (
                SELECT 1 FROM entregas_alertas e
                WHERE e.sinal_id=OLD.id AND e.status='entregue'
                  AND e.canal NOT LIKE 'gateway:%'
                  AND INSTR(e.canal, ':resultado')=0
                  AND INSTR(e.canal, ':green_antecipado')=0
                  AND INSTR(e.canal, ':aguardar_odd')=0
                  AND INSTR(e.canal, ':cancelamento')=0
                  AND INSTR(e.canal, ':insuficiente')=0
                  AND INSTR(e.canal, ':monitoramento_final')=0
                  AND INSTR(e.canal, ':correcao')=0
             )
            BEGIN
                SELECT RAISE(
                    ABORT, 'evidencia do sinal entregue e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS trg_snapshots_update_imutavel
            BEFORE UPDATE ON snapshots
            BEGIN
                SELECT RAISE(ABORT, 'snapshots sao append-only e imutaveis');
            END;

            CREATE TRIGGER IF NOT EXISTS trg_snapshots_clv_delete_imutavel
            BEFORE DELETE ON snapshots
            WHEN EXISTS (
                SELECT 1
                FROM sinais s
                JOIN entregas_alertas e ON e.sinal_id=s.id
                WHERE (
                    s.snapshot_id=OLD.id
                    OR (
                        s.partida_id=OLD.partida_id
                        AND datetime(OLD.coletado_em) > datetime(
                            COALESCE(e.entregue_em,e.tentado_em)
                        )
                        AND datetime(OLD.coletado_em) <= datetime(
                            COALESCE(e.entregue_em,e.tentado_em),
                            '+10 minutes'
                        )
                    )
                )
                  AND e.status='entregue'
                  AND e.canal NOT LIKE 'gateway:%'
                  AND INSTR(e.canal, ':resultado')=0
                  AND INSTR(e.canal, ':green_antecipado')=0
                  AND INSTR(e.canal, ':aguardar_odd')=0
                  AND INSTR(e.canal, ':cancelamento')=0
                  AND INSTR(e.canal, ':insuficiente')=0
                  AND INSTR(e.canal, ':monitoramento_final')=0
                  AND INSTR(e.canal, ':correcao')=0
            )
            BEGIN
                SELECT RAISE(
                    ABORT, 'snapshot usado pela coorte CLV e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS trg_odds_update_imutavel
            BEFORE UPDATE ON odds
            BEGIN
                SELECT RAISE(ABORT, 'odds sao append-only e imutaveis');
            END;

            CREATE TRIGGER IF NOT EXISTS trg_odds_clv_delete_imutavel
            BEFORE DELETE ON odds
            WHEN EXISTS (
                SELECT 1
                FROM snapshots sn
                JOIN sinais s ON s.partida_id=sn.partida_id
                JOIN entregas_alertas e ON e.sinal_id=s.id
                WHERE sn.id=OLD.snapshot_id
                  AND (
                    s.snapshot_id=sn.id
                    OR (
                        datetime(sn.coletado_em) > datetime(
                            COALESCE(e.entregue_em,e.tentado_em)
                        )
                        AND datetime(sn.coletado_em) <= datetime(
                            COALESCE(e.entregue_em,e.tentado_em),
                            '+10 minutes'
                        )
                    )
                  )
                  AND e.status='entregue'
                  AND e.canal NOT LIKE 'gateway:%'
                  AND INSTR(e.canal, ':resultado')=0
                  AND INSTR(e.canal, ':green_antecipado')=0
                  AND INSTR(e.canal, ':aguardar_odd')=0
                  AND INSTR(e.canal, ':cancelamento')=0
                  AND INSTR(e.canal, ':insuficiente')=0
                  AND INSTR(e.canal, ':monitoramento_final')=0
                  AND INSTR(e.canal, ':correcao')=0
            )
            BEGIN
                SELECT RAISE(
                    ABORT, 'odd usada pela coorte CLV e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_observacoes_odds_evidencia_update_imutavel
            BEFORE UPDATE ON observacoes_fontes_odds
            WHEN OLD.estado<>'consulta_monitoramento'
            BEGIN
                SELECT RAISE(
                    ABORT, 'observacao de fonte de odd e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_observacoes_odds_evidencia_delete_imutavel
            BEFORE DELETE ON observacoes_fontes_odds
            WHEN OLD.estado<>'consulta_monitoramento'
            BEGIN
                SELECT RAISE(
                    ABORT, 'observacao de fonte de odd e imutavel'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_observacoes_odds_identidade_estavel
            BEFORE INSERT ON observacoes_fontes_odds
            WHEN NEW.estado='oferta_monitorada'
             AND json_valid(NEW.oferta_json)
             AND json_extract(
                    NEW.oferta_json, '$.schema'
                 )='oferta-monitorada-odd-v3'
             AND EXISTS (
                SELECT 1
                FROM observacoes_fontes_odds anterior
                WHERE anterior.estado='oferta_monitorada'
                  AND anterior.evidencia_referencia
                      = NEW.evidencia_referencia
                  AND lower(trim(anterior.fonte))
                      = lower(trim(NEW.fonte))
                  AND json_valid(anterior.oferta_json)
                  AND json_extract(
                        anterior.oferta_json, '$.schema'
                      )='oferta-monitorada-odd-v3'
                  AND (
                    CAST(json_extract(
                        anterior.oferta_json,
                        '$.identidade_evento.evento_externo_id'
                    ) AS TEXT) <> CAST(json_extract(
                        NEW.oferta_json,
                        '$.identidade_evento.evento_externo_id'
                    ) AS TEXT)
                    OR lower(CAST(json_extract(
                        anterior.oferta_json,
                        '$.identidade_evento.orientacao'
                    ) AS TEXT)) <> lower(CAST(json_extract(
                        NEW.oferta_json,
                        '$.identidade_evento.orientacao'
                    ) AS TEXT))
                  )
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'identidade externa da odd mudou na mesma fonte'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_observacoes_odds_identidade_estavel_v2
            BEFORE INSERT ON observacoes_fontes_odds
            WHEN NEW.estado='oferta_monitorada'
             AND json_valid(NEW.oferta_json)
             AND json_extract(
                    NEW.oferta_json, '$.schema'
                 ) IN (
                    'oferta-monitorada-odd-v3',
                    'oferta-monitorada-odd-v4'
                 )
             AND EXISTS (
                SELECT 1
                FROM observacoes_fontes_odds anterior
                WHERE anterior.estado='oferta_monitorada'
                  AND anterior.evidencia_referencia
                      = NEW.evidencia_referencia
                  AND lower(trim(anterior.fonte))
                      = lower(trim(NEW.fonte))
                  AND json_valid(anterior.oferta_json)
                  AND json_extract(
                        anterior.oferta_json, '$.schema'
                      ) IN (
                        'oferta-monitorada-odd-v3',
                        'oferta-monitorada-odd-v4'
                      )
                  AND (
                    CAST(json_extract(
                        anterior.oferta_json,
                        '$.identidade_evento.evento_externo_id'
                    ) AS TEXT) <> CAST(json_extract(
                        NEW.oferta_json,
                        '$.identidade_evento.evento_externo_id'
                    ) AS TEXT)
                    OR lower(CAST(json_extract(
                        anterior.oferta_json,
                        '$.identidade_evento.orientacao'
                    ) AS TEXT)) <> lower(CAST(json_extract(
                        NEW.oferta_json,
                        '$.identidade_evento.orientacao'
                    ) AS TEXT))
                  )
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'identidade externa V3/V4 mudou na mesma fonte'
                );
            END;

            CREATE TRIGGER IF NOT EXISTS
                trg_revisoes_notificacao_prova_imutavel
            BEFORE UPDATE OF
                notificacao_provedor, notificacao_destino_id,
                notificacao_mensagem_id,
                notificacao_confirmacao_json
            ON revisoes_resultados
            WHEN (
                    OLD.notificacao_provedor IS NOT NULL
                    OR OLD.notificacao_destino_id IS NOT NULL
                    OR OLD.notificacao_mensagem_id IS NOT NULL
                    OR OLD.notificacao_confirmacao_json IS NOT NULL
                 )
             AND (
                    OLD.notificacao_provedor IS NOT NEW.notificacao_provedor
                    OR OLD.notificacao_destino_id
                        IS NOT NEW.notificacao_destino_id
                    OR OLD.notificacao_mensagem_id
                        IS NOT NEW.notificacao_mensagem_id
                    OR OLD.notificacao_confirmacao_json
                        IS NOT NEW.notificacao_confirmacao_json
                 )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'prova da notificacao de revisao e imutavel'
                );
            END;

            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_notificacoes_operacionais_mensagem_unica
            ON notificacoes_operacionais(
                provedor, destino, provedor_mensagem_id
            )
            WHERE provedor='telegram'
              AND provedor_mensagem_id IS NOT NULL;

            CREATE TRIGGER IF NOT EXISTS
                trg_notificacoes_operacionais_prova_imutavel
            BEFORE UPDATE OF
                provedor, provedor_mensagem_id, confirmacao_json
            ON notificacoes_operacionais
            WHEN (
                    OLD.provedor IS NOT NULL
                    OR OLD.provedor_mensagem_id IS NOT NULL
                    OR OLD.confirmacao_json IS NOT NULL
                 )
             AND (
                    OLD.provedor IS NOT NEW.provedor
                    OR OLD.provedor_mensagem_id
                        IS NOT NEW.provedor_mensagem_id
                    OR OLD.confirmacao_json IS NOT NEW.confirmacao_json
                 )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'prova de notificacao operacional e imutavel'
                );
            END;
            """
        )
        # As edicoes de monitoramento nao sao liquidacoes oficiais. A versao
        # inicial usou o sufixo reservado ``:resultado`` e o auditor as
        # interpretou corretamente como inconsistentes. Renomear preserva a
        # prova Telegram e separa os dois dominios sem apagar historico.
        self.conexao.execute(
            """
            UPDATE OR IGNORE entregas_alertas
            SET canal=REPLACE(
                canal,
                ':aguardar_odd:resultado',
                ':aguardar_odd:monitoramento_final'
            )
            WHERE canal LIKE '%:aguardar_odd:resultado'
            """
        )
        self.conexao.execute(
            """
            INSERT OR IGNORE INTO metadados (chave, valor)
            VALUES (?, ?)
            """,
            (
                "migracao_schema:thestatsapi_sombra:v1",
                json.dumps(
                    {
                        "aplicado_em": datetime.now().replace(
                            microsecond=0
                        ).isoformat(),
                        "aplicacao_sinais": False,
                        "fonte": "thestatsapi",
                        "versao": 1,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        # A tabela corrente existia antes do histórico append-only. Faz um
        # backfill idempotente para que a primeira observação disponível não
        # seja perdida na migração.
        taxas_existentes = [
            dict(linha) for linha in self.conexao.execute(
                """
                SELECT league_id, pais, liga, liga_normalizada, temporada,
                       periodo, jogos_realizados, jogos_previstos,
                       jogos_com_stats, over_0_5, over_1_5, over_2_5,
                       fonte, coletado_em, versao
                FROM taxas_ligas_gols_packball
                """
            ).fetchall()
        ]
        if taxas_existentes:
            self._inserir_historico_taxas_ligas(taxas_existentes)
        self.conexao.commit()

    def _obter_partida(
        self, registro, coletado_em, atualizar_ultima_coleta=True,
    ):
        confirmacao = registro.get("confirmacao_api") or {}
        fixture_id = confirmacao.get("fixture_id")
        orientacao_api = confirmacao.get("orientacao")
        self.conexao.execute(
            """
            INSERT INTO partidas (
                packball_url, mandante, visitante,
                mandante_normalizado, visitante_normalizado,
                packball_partida_id, pais, liga, liga_normalizada,
                primeira_coleta, ultima_coleta, api_fixture_id,
                api_orientacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(packball_url) DO UPDATE SET
                mandante=excluded.mandante,
                visitante=excluded.visitante,
                mandante_normalizado=excluded.mandante_normalizado,
                visitante_normalizado=excluded.visitante_normalizado,
                packball_partida_id=COALESCE(
                    excluded.packball_partida_id,
                    partidas.packball_partida_id
                ),
                pais=COALESCE(excluded.pais, partidas.pais),
                liga=COALESCE(excluded.liga, partidas.liga),
                liga_normalizada=CASE
                    WHEN excluded.liga_normalizada<>''
                    THEN excluded.liga_normalizada
                    ELSE partidas.liga_normalizada
                END,
                ultima_coleta=CASE
                    WHEN ?=1 THEN excluded.ultima_coleta
                    ELSE partidas.ultima_coleta
                END,
                api_fixture_id=COALESCE(
                    excluded.api_fixture_id,
                    partidas.api_fixture_id
                ),
                api_orientacao=COALESCE(
                    excluded.api_orientacao,
                    partidas.api_orientacao
                )
            """,
            (
                registro["url"],
                registro.get("mandante", ""),
                registro.get("visitante", ""),
                normalizar_texto(registro.get("mandante")),
                normalizar_texto(registro.get("visitante")),
                extrair_packball_id(registro["url"]),
                registro.get("pais"),
                registro.get("liga"),
                normalizar_texto(registro.get("liga")),
                coletado_em,
                coletado_em,
                fixture_id,
                orientacao_api,
                int(bool(atualizar_ultima_coleta)),
            ),
        )
        linha = self.conexao.execute(
            "SELECT id FROM partidas WHERE packball_url=?",
            (registro["url"],),
        ).fetchone()
        return linha["id"]

    def salvar_historico_api_live(
        self, registros, agora=None, retencao_dias=30
    ):
        """Persiste contadores API já coletados, sem participar dos sinais."""
        registros = [dict(item) for item in registros or [] if item]
        agora = agora or datetime.now()
        limite = (
            agora - timedelta(days=max(float(retencao_dias), 1.0))
        ).replace(microsecond=0).isoformat()
        campos = (
            "fixture_id", "packball_url", "coletado_em", "minuto",
            "periodo", "orientacao", "chutes_mandante",
            "chutes_visitante", "chutes_gol_mandante",
            "chutes_gol_visitante", "escanteios_mandante",
            "escanteios_visitante", "xg_mandante", "xg_visitante",
            "completo", "fonte",
        )
        with self.conexao:
            total_antes = self.conexao.total_changes
            self.conexao.executemany(
                """
                INSERT OR IGNORE INTO historico_api_live (
                    fixture_id, packball_url, coletado_em, minuto,
                    periodo, orientacao, chutes_mandante,
                    chutes_visitante, chutes_gol_mandante,
                    chutes_gol_visitante, escanteios_mandante,
                    escanteios_visitante, xg_mandante, xg_visitante,
                    completo, fonte
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    tuple(
                        int(bool(item.get(campo)))
                        if campo == "completo"
                        else item.get(campo)
                        for campo in campos
                    )
                    for item in registros
                ],
            )
            inseridos = self.conexao.total_changes - total_antes
            cursor = self.conexao.execute(
                "DELETE FROM historico_api_live "
                "WHERE datetime(coletado_em) < datetime(?)",
                (limite,),
            )
        return {
            "saudavel": True,
            "estado": "persistido",
            "recebidos": len(registros),
            "inseridos": int(inseridos),
            "duplicados": max(len(registros) - int(inseridos), 0),
            "removidos_retencao": int(cursor.rowcount or 0),
            "retencao_dias": float(retencao_dias),
            "aplicacao_sinais": False,
        }

    def _inserir_historico_taxas_ligas(self, registros):
        campos = (
            "league_id", "pais", "liga", "liga_normalizada",
            "temporada", "periodo", "jogos_realizados",
            "jogos_previstos", "jogos_com_stats", "over_0_5",
            "over_1_5", "over_2_5", "fonte", "coletado_em", "versao",
        )
        historico = []
        for item in registros:
            dados = {campo: item.get(campo) for campo in campos}
            evidencia = hashlib.sha256(json.dumps(
                dados,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
            historico.append(tuple(dados[campo] for campo in campos) + (
                evidencia,
            ))
        total_historico_antes = self.conexao.total_changes
        self.conexao.executemany(
            """
            INSERT OR IGNORE INTO historico_taxas_ligas_gols_packball (
                league_id, pais, liga, liga_normalizada, temporada,
                periodo, jogos_realizados, jogos_previstos,
                jogos_com_stats, over_0_5, over_1_5, over_2_5,
                fonte, coletado_em, versao, evidencia_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            historico,
        )
        return self.conexao.total_changes - total_historico_antes

    def salvar_taxas_ligas_gols(self, registros):
        registros = [
            dict(item) for item in (registros or [])
            if isinstance(item, dict)
        ]
        if not registros:
            return {
                "recebidos": 0,
                "persistidos": 0,
                "historico_inseridos": 0,
                "historico_duplicados": 0,
            }
        campos = (
            "league_id", "pais", "liga", "liga_normalizada",
            "temporada", "periodo", "jogos_realizados",
            "jogos_previstos", "jogos_com_stats", "over_0_5",
            "over_1_5", "over_2_5", "fonte", "coletado_em", "versao",
        )
        with self.conexao:
            historico_inseridos = self._inserir_historico_taxas_ligas(
                registros
            )
            total_antes = self.conexao.total_changes
            self.conexao.executemany(
                """
                INSERT INTO taxas_ligas_gols_packball (
                    league_id, pais, liga, liga_normalizada, temporada,
                    periodo, jogos_realizados, jogos_previstos,
                    jogos_com_stats, over_0_5, over_1_5, over_2_5,
                    fonte, coletado_em, versao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(league_id, temporada, periodo) DO UPDATE SET
                    pais=excluded.pais,
                    liga=excluded.liga,
                    liga_normalizada=excluded.liga_normalizada,
                    jogos_realizados=excluded.jogos_realizados,
                    jogos_previstos=excluded.jogos_previstos,
                    jogos_com_stats=excluded.jogos_com_stats,
                    over_0_5=excluded.over_0_5,
                    over_1_5=excluded.over_1_5,
                    over_2_5=excluded.over_2_5,
                    fonte=excluded.fonte,
                    coletado_em=excluded.coletado_em,
                    versao=excluded.versao
                """,
                [tuple(item.get(campo) for campo in campos) for item in registros],
            )
            persistidos = self.conexao.total_changes - total_antes
        return {
            "recebidos": len(registros),
            "persistidos": int(persistidos),
            "historico_inseridos": int(historico_inseridos),
            "historico_duplicados": max(
                len(registros) - int(historico_inseridos), 0
            ),
        }

    def resumir_historico_taxas_ligas_gols(self):
        linha = self.conexao.execute(
            """
            SELECT COUNT(*) AS registros,
                   COUNT(DISTINCT league_id) AS ligas,
                   COUNT(DISTINCT temporada) AS temporadas,
                   MIN(coletado_em) AS primeira_coleta,
                   MAX(coletado_em) AS ultima_coleta
            FROM historico_taxas_ligas_gols_packball
            """
        ).fetchone()
        return {
            "registros": int((linha["registros"] if linha else 0) or 0),
            "ligas": int((linha["ligas"] if linha else 0) or 0),
            "temporadas": int(
                (linha["temporadas"] if linha else 0) or 0
            ),
            "primeira_coleta": (
                linha["primeira_coleta"] if linha else None
            ),
            "ultima_coleta": linha["ultima_coleta"] if linha else None,
            "imutavel": True,
            "aplicacao_sinais": False,
        }

    def carregar_taxas_ligas_gols(self):
        linhas = self.conexao.execute(
            """
            SELECT atual.*
            FROM taxas_ligas_gols_packball atual
            WHERE NOT EXISTS (
                SELECT 1
                FROM taxas_ligas_gols_packball nova
                WHERE nova.league_id=atual.league_id
                  AND nova.periodo=atual.periodo
                  AND (
                      datetime(nova.coletado_em) > datetime(atual.coletado_em)
                      OR (
                          datetime(nova.coletado_em)=datetime(atual.coletado_em)
                          AND nova.id > atual.id
                      )
                  )
            )
            ORDER BY atual.league_id, atual.periodo
            """
        ).fetchall()
        return [dict(linha) for linha in linhas]

    def ultima_coleta_taxas_ligas_gols(self):
        linha = self.conexao.execute(
            """
            SELECT MAX(coletado_em) AS coletado_em,
                   COUNT(*) AS registros
            FROM taxas_ligas_gols_packball
            """
        ).fetchone()
        return {
            "coletado_em": linha["coletado_em"] if linha else None,
            "registros": int((linha["registros"] if linha else 0) or 0),
        }

    def salvar_auditoria_fila_packball(
        self, registros, agora=None, retencao_dias=7
    ):
        """Persiste decisões da fila sem participar da geração de sinais."""
        registros = [
            dict(item) for item in (registros or [])
            if isinstance(item, dict) and item.get("packball_url")
        ]
        agora = (agora or datetime.now()).replace(microsecond=0)
        registrado_em = agora.isoformat()
        limite = (
            agora - timedelta(days=max(float(retencao_dias), 1.0))
        ).isoformat()
        campos = (
            "ciclo_em", "registrado_em", "packball_url", "mandante",
            "visitante", "liga", "minuto", "posicao", "processada",
            "acionavel", "fila_operacional", "idade_segundos",
            "atraso_segundos", "em_foco", "scanner_prioritario",
            "pre_live_prioritario", "prioridade_liga_gols",
            "prioridade_indicadores_lista", "prioridade_api_lote",
            "janelas_temporais_json", "motivo",
        )
        normalizados = []
        for item in registros:
            ciclo_em = str(item.get("ciclo_em") or registrado_em)
            janelas = item.get("janelas_temporais") or []
            if not isinstance(janelas, (list, tuple, set)):
                janelas = []
            linha = {
                **item,
                "ciclo_em": ciclo_em,
                "registrado_em": registrado_em,
                "posicao": max(int(item.get("posicao") or 0), 1),
                "processada": int(bool(item.get("processada"))),
                "acionavel": int(bool(item.get("acionavel"))),
                "fila_operacional": str(
                    item.get("fila_operacional") or "exploracao"
                ),
                "em_foco": int(bool(item.get("em_foco"))),
                "scanner_prioritario": int(bool(
                    item.get("scanner_prioritario")
                )),
                "pre_live_prioritario": int(bool(
                    item.get("pre_live_prioritario")
                )),
                "janelas_temporais_json": json.dumps(
                    sorted(set(janelas)), ensure_ascii=False
                ),
                "motivo": str(item.get("motivo") or "nao_informado"),
            }
            normalizados.append(tuple(linha.get(campo) for campo in campos))
        with self.conexao:
            total_antes = self.conexao.total_changes
            if normalizados:
                self.conexao.executemany(
                    """
                    INSERT OR IGNORE INTO auditoria_fila_packball (
                        ciclo_em, registrado_em, packball_url, mandante,
                        visitante, liga, minuto, posicao, processada,
                        acionavel, fila_operacional, idade_segundos,
                        atraso_segundos, em_foco, scanner_prioritario,
                        pre_live_prioritario, prioridade_liga_gols,
                        prioridade_indicadores_lista, prioridade_api_lote,
                        janelas_temporais_json, motivo
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?
                    )
                    """,
                    normalizados,
                )
            inseridos = self.conexao.total_changes - total_antes
            cursor = self.conexao.execute(
                "DELETE FROM auditoria_fila_packball "
                "WHERE datetime(ciclo_em) < datetime(?)",
                (limite,),
            )
        return {
            "saudavel": True,
            "estado": "persistido",
            "recebidos": len(registros),
            "inseridos": int(inseridos),
            "duplicados": max(len(registros) - int(inseridos), 0),
            "removidos_retencao": int(cursor.rowcount or 0),
            "retencao_dias": float(retencao_dias),
            "aplicacao_sinais": False,
            "navegacoes_adicionais": 0,
        }

    @staticmethod
    def _validar_chave_thestatsapi(valor, campo):
        texto = str(valor or "").strip()
        if not texto:
            raise ValueError(f"{campo} da TheStatsAPI nao pode ser vazio.")
        if len(texto) > 2048:
            raise ValueError(f"{campo} da TheStatsAPI excedeu o limite.")
        return texto

    @staticmethod
    def _numero_thestatsapi(valor, campo, *, obrigatorio=False):
        if valor is None or valor == "":
            if obrigatorio:
                raise ValueError(
                    f"{campo} da TheStatsAPI precisa ser numerico."
                )
            return None
        if isinstance(valor, bool):
            raise ValueError(
                f"{campo} da TheStatsAPI precisa ser numerico."
            )
        try:
            numero = float(valor)
        except (TypeError, ValueError) as erro:
            raise ValueError(
                f"{campo} da TheStatsAPI precisa ser numerico."
            ) from erro
        if numero != numero or numero in (float("inf"), float("-inf")):
            raise ValueError(
                f"{campo} da TheStatsAPI precisa ser finito."
            )
        return numero

    @staticmethod
    def _limite_retencao_thestatsapi(agora, retencao_dias):
        if isinstance(agora, datetime):
            instante = agora
        else:
            instante = datetime.fromisoformat(normalizar_data(agora))
        try:
            dias = float(retencao_dias)
        except (TypeError, ValueError) as erro:
            raise ValueError("Retencao da TheStatsAPI deve ser numerica.") from erro
        if (
            dias < 1
            or dias != dias
            or dias in (float("inf"), float("-inf"))
        ):
            raise ValueError("Retencao da TheStatsAPI deve ser de ao menos 1 dia.")
        return (
            instante - timedelta(days=dias)
        ).replace(microsecond=0).isoformat(), dias

    def salvar_pareamento_thestatsapi(
        self, pareamento, agora=None, retencao_dias=30
    ):
        """Salva um pareamento auditavel sem habilita-lo para sinais."""
        pareamento = dict(pareamento or {})
        packball_url = self._validar_chave_thestatsapi(
            pareamento.get("packball_url") or pareamento.get("url"),
            "packball_url",
        )
        match_id = self._validar_chave_thestatsapi(
            pareamento.get("match_id"), "match_id"
        )
        orientacao = str(pareamento.get("orientacao") or "").strip()
        if orientacao not in ("direta", "invertida"):
            raise ValueError("Orientacao TheStatsAPI invalida.")
        similaridade = self._numero_thestatsapi(
            pareamento.get("similaridade"),
            "similaridade",
            obrigatorio=True,
        )
        margem = self._numero_thestatsapi(
            pareamento.get("margem"), "margem"
        )
        mandante_api = self._validar_chave_thestatsapi(
            pareamento.get("mandante_api"), "mandante_api"
        )
        visitante_api = self._validar_chave_thestatsapi(
            pareamento.get("visitante_api"), "visitante_api"
        )
        atualizado_em = normalizar_data(
            pareamento.get("atualizado_em") or agora
        )
        criado_em = normalizar_data(
            pareamento.get("criado_em") or atualizado_em
        )
        diagnostico_json = json.dumps(
            pareamento.get("diagnostico") or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        limite, dias = self._limite_retencao_thestatsapi(
            agora or datetime.now(), retencao_dias
        )
        with self.conexao:
            existente = self.conexao.execute(
                """
                SELECT match_id, orientacao, similaridade, margem,
                       mandante_api, visitante_api, diagnostico_json
                FROM pareamentos_thestatsapi
                WHERE packball_url=?
                """,
                (packball_url,),
            ).fetchone()
            self.conexao.execute(
                """
                INSERT INTO pareamentos_thestatsapi (
                    packball_url, match_id, orientacao, similaridade,
                    margem, mandante_api, visitante_api, criado_em,
                    atualizado_em, diagnostico_json, fonte,
                    aplicacao_sinais
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'thestatsapi', 0)
                ON CONFLICT(packball_url) DO UPDATE SET
                    match_id=excluded.match_id,
                    orientacao=excluded.orientacao,
                    similaridade=excluded.similaridade,
                    margem=excluded.margem,
                    mandante_api=excluded.mandante_api,
                    visitante_api=excluded.visitante_api,
                    atualizado_em=excluded.atualizado_em,
                    diagnostico_json=excluded.diagnostico_json
                """,
                (
                    packball_url, match_id, orientacao, similaridade,
                    margem, mandante_api, visitante_api, criado_em,
                    atualizado_em, diagnostico_json,
                ),
            )
            removidos = self.conexao.execute(
                """
                DELETE FROM pareamentos_thestatsapi
                WHERE datetime(atualizado_em) < datetime(?)
                """,
                (limite,),
            ).rowcount
        valores = (
            match_id, orientacao, similaridade, margem,
            mandante_api, visitante_api, diagnostico_json,
        )
        estado = (
            "inserido"
            if existente is None
            else "inalterado"
            if tuple(existente) == valores
            else "atualizado"
        )
        return {
            "saudavel": True,
            "estado": estado,
            "packball_url": packball_url,
            "match_id": match_id,
            "removidos_retencao": int(removidos or 0),
            "retencao_dias": dias,
            "fonte": "thestatsapi",
            "aplicacao_sinais": False,
        }

    def obter_pareamento_thestatsapi(
        self, packball_url=None, match_id=None
    ):
        if packball_url:
            campo = "packball_url"
            valor = self._validar_chave_thestatsapi(
                packball_url, campo
            )
        elif match_id:
            campo = "match_id"
            valor = self._validar_chave_thestatsapi(match_id, campo)
        else:
            raise ValueError("Informe packball_url ou match_id.")
        linha = self.conexao.execute(
            f"SELECT * FROM pareamentos_thestatsapi WHERE {campo}=?",
            (valor,),
        ).fetchone()
        if linha is None:
            return None
        resultado = dict(linha)
        resultado["diagnostico"] = json.loads(
            resultado.pop("diagnostico_json")
        )
        resultado["aplicacao_sinais"] = False
        return resultado

    def salvar_historico_thestatsapi_live(
        self, registros, agora=None, retencao_dias=30
    ):
        """Persiste snapshots ao vivo da fonte nova somente em sombra."""
        if isinstance(registros, dict):
            registros = [registros]
        agora = agora or datetime.now()
        limite, dias = self._limite_retencao_thestatsapi(
            agora, retencao_dias
        )
        preparados = []
        for bruto in registros or []:
            if not bruto:
                continue
            item = dict(bruto)
            match_id = self._validar_chave_thestatsapi(
                item.get("match_id"), "match_id"
            )
            packball_url = self._validar_chave_thestatsapi(
                item.get("packball_url") or item.get("url"),
                "packball_url",
            )
            orientacao = item.get("orientacao")
            if orientacao is not None:
                orientacao = str(orientacao).strip()
                if orientacao not in ("direta", "invertida"):
                    raise ValueError("Orientacao TheStatsAPI invalida.")
            placar_bruto = item.get("placar")
            placar_mandante = item.get("placar_mandante")
            placar_visitante = item.get("placar_visitante")
            if isinstance(placar_bruto, (list, tuple)):
                if len(placar_bruto) >= 2:
                    if placar_mandante is None:
                        placar_mandante = placar_bruto[0]
                    if placar_visitante is None:
                        placar_visitante = placar_bruto[1]
                placar = "-".join(str(valor) for valor in placar_bruto[:2])
            elif isinstance(placar_bruto, dict):
                if placar_mandante is None:
                    placar_mandante = placar_bruto.get(
                        "mandante", placar_bruto.get("home")
                    )
                if placar_visitante is None:
                    placar_visitante = placar_bruto.get(
                        "visitante", placar_bruto.get("away")
                    )
                placar = (
                    f"{placar_mandante}-{placar_visitante}"
                    if placar_mandante is not None
                    and placar_visitante is not None
                    else None
                )
            else:
                placar = str(placar_bruto or "").strip() or None
            preparados.append((
                match_id,
                packball_url,
                normalizar_data(item.get("coletado_em") or agora),
                self._numero_thestatsapi(item.get("minuto"), "minuto"),
                str(item.get("periodo") or "").strip() or None,
                placar,
                self._numero_thestatsapi(
                    placar_mandante, "placar_mandante"
                ),
                self._numero_thestatsapi(
                    placar_visitante, "placar_visitante"
                ),
                orientacao,
                self._numero_thestatsapi(
                    item.get("chutes_mandante"), "chutes_mandante"
                ),
                self._numero_thestatsapi(
                    item.get("chutes_visitante"), "chutes_visitante"
                ),
                self._numero_thestatsapi(
                    item.get("chutes_gol_mandante"),
                    "chutes_gol_mandante",
                ),
                self._numero_thestatsapi(
                    item.get("chutes_gol_visitante"),
                    "chutes_gol_visitante",
                ),
                self._numero_thestatsapi(
                    item.get("escanteios_mandante"),
                    "escanteios_mandante",
                ),
                self._numero_thestatsapi(
                    item.get("escanteios_visitante"),
                    "escanteios_visitante",
                ),
                self._numero_thestatsapi(
                    item.get("xg_mandante"), "xg_mandante"
                ),
                self._numero_thestatsapi(
                    item.get("xg_visitante"), "xg_visitante"
                ),
                int(bool(item.get("completo"))),
            ))
        recebidos = len(preparados)
        unicos = {}
        for item in preparados:
            unicos[item[:3]] = item
        preparados = list(unicos.values())
        duplicados_entrada = recebidos - len(preparados)
        chaves = [item[:3] for item in preparados]
        existentes = 0
        if chaves:
            existentes = sum(
                self.conexao.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM historico_thestatsapi_live
                        WHERE match_id=? AND packball_url=?
                          AND coletado_em=?
                    )
                    """,
                    chave,
                ).fetchone()[0]
                for chave in chaves
            )
        with self.conexao:
            self.conexao.executemany(
                """
                INSERT INTO historico_thestatsapi_live (
                    match_id, packball_url, coletado_em, minuto, periodo,
                    placar, placar_mandante, placar_visitante, orientacao,
                    chutes_mandante, chutes_visitante,
                    chutes_gol_mandante, chutes_gol_visitante,
                    escanteios_mandante, escanteios_visitante,
                    xg_mandante, xg_visitante, completo, fonte,
                    aplicacao_sinais
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, 'thestatsapi', 0)
                ON CONFLICT(match_id, packball_url, coletado_em) DO UPDATE SET
                    minuto=excluded.minuto,
                    periodo=excluded.periodo,
                    placar=excluded.placar,
                    placar_mandante=excluded.placar_mandante,
                    placar_visitante=excluded.placar_visitante,
                    orientacao=excluded.orientacao,
                    chutes_mandante=excluded.chutes_mandante,
                    chutes_visitante=excluded.chutes_visitante,
                    chutes_gol_mandante=excluded.chutes_gol_mandante,
                    chutes_gol_visitante=excluded.chutes_gol_visitante,
                    escanteios_mandante=excluded.escanteios_mandante,
                    escanteios_visitante=excluded.escanteios_visitante,
                    xg_mandante=excluded.xg_mandante,
                    xg_visitante=excluded.xg_visitante,
                    completo=excluded.completo
                """,
                preparados,
            )
            removidos = self.conexao.execute(
                """
                DELETE FROM historico_thestatsapi_live
                WHERE datetime(coletado_em) < datetime(?)
                """,
                (limite,),
            ).rowcount
        return {
            "saudavel": True,
            "estado": "persistido",
            "recebidos": recebidos,
            "inseridos": len(preparados) - int(existentes),
            "atualizados": int(existentes),
            "duplicados_entrada": duplicados_entrada,
            "removidos_retencao": int(removidos or 0),
            "retencao_dias": dias,
            "fonte": "thestatsapi",
            "aplicacao_sinais": False,
        }

    def salvar_odds_thestatsapi_live(
        self, registros, agora=None, retencao_dias=14
    ):
        """Persiste linhas over/under normalizadas, ainda sem uso no motor."""
        if isinstance(registros, dict):
            registros = [registros]
        agora = agora or datetime.now()
        limite, dias = self._limite_retencao_thestatsapi(
            agora, retencao_dias
        )
        expandidos = []
        for bruto in registros or []:
            if not bruto:
                continue
            envelope = dict(bruto)
            ofertas = envelope.pop("ofertas", None)
            if isinstance(ofertas, list):
                for oferta in ofertas:
                    if not isinstance(oferta, dict):
                        continue
                    item = dict(envelope)
                    item.update(oferta)
                    expandidos.append(item)
            else:
                expandidos.append(envelope)
        preparados = []
        for item in expandidos:
            odd_over = self._numero_thestatsapi(
                item.get("odd_over", item.get("over")), "odd_over"
            )
            odd_under = self._numero_thestatsapi(
                item.get("odd_under", item.get("under")), "odd_under"
            )
            if odd_over is None and odd_under is None:
                raise ValueError(
                    "Odd TheStatsAPI exige odd_over ou odd_under."
                )
            categoria = self._validar_chave_thestatsapi(
                item.get("categoria")
                or item.get("mercado")
                or item.get("tipo_mercado"),
                "categoria",
            )
            tipo_mercado = self._validar_chave_thestatsapi(
                item.get("tipo_mercado")
                or item.get("mercado")
                or categoria,
                "tipo_mercado",
            )
            mercado = self._validar_chave_thestatsapi(
                item.get("mercado") or categoria, "mercado"
            )
            mercado_origem = self._validar_chave_thestatsapi(
                item.get("mercado_origem")
                or item.get("mercado_original")
                or mercado,
                "mercado_origem",
            )
            preparados.append((
                self._validar_chave_thestatsapi(
                    item.get("match_id"), "match_id"
                ),
                self._validar_chave_thestatsapi(
                    item.get("packball_url") or item.get("url"),
                    "packball_url",
                ),
                normalizar_data(item.get("coletado_em") or agora),
                self._validar_chave_thestatsapi(
                    item.get("bookmaker"), "bookmaker"
                ),
                mercado,
                mercado_origem,
                categoria,
                tipo_mercado,
                self._validar_chave_thestatsapi(
                    item.get("periodo") or "FT", "periodo"
                ),
                self._numero_thestatsapi(
                    item.get("linha"), "linha", obrigatorio=True
                ),
                odd_over,
                odd_under,
            ))
        recebidos = len(preparados)
        unicos = {}
        for item in preparados:
            chave = (
                item[0], item[1], item[2], item[3], item[4],
                item[7], item[8], item[9],
            )
            unicos[chave] = item
        preparados = list(unicos.values())
        duplicados_entrada = recebidos - len(preparados)
        chaves = [
            (
                item[0], item[1], item[2], item[3], item[4],
                item[7], item[8], item[9],
            )
            for item in preparados
        ]
        existentes = 0
        if chaves:
            existentes = sum(
                self.conexao.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM odds_thestatsapi_live
                        WHERE match_id=? AND packball_url=?
                          AND coletado_em=? AND bookmaker=?
                          AND mercado=? AND tipo_mercado=?
                          AND periodo=? AND linha=?
                    )
                    """,
                    chave,
                ).fetchone()[0]
                for chave in chaves
            )
        with self.conexao:
            self.conexao.executemany(
                """
                INSERT INTO odds_thestatsapi_live (
                    match_id, packball_url, coletado_em, bookmaker,
                    mercado, mercado_origem, categoria, tipo_mercado,
                    periodo, linha, odd_over, odd_under, fonte,
                    aplicacao_sinais
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'thestatsapi', 0)
                ON CONFLICT(
                    match_id, packball_url, coletado_em, bookmaker,
                    mercado, tipo_mercado, periodo, linha
                ) DO UPDATE SET
                    mercado_origem=excluded.mercado_origem,
                    categoria=excluded.categoria,
                    odd_over=excluded.odd_over,
                    odd_under=excluded.odd_under
                """,
                preparados,
            )
            removidos = self.conexao.execute(
                """
                DELETE FROM odds_thestatsapi_live
                WHERE datetime(coletado_em) < datetime(?)
                """,
                (limite,),
            ).rowcount
        return {
            "saudavel": True,
            "estado": "persistido",
            "recebidos": recebidos,
            "inseridos": len(preparados) - int(existentes),
            "atualizados": int(existentes),
            "duplicados_entrada": duplicados_entrada,
            "removidos_retencao": int(removidos or 0),
            "retencao_dias": dias,
            "fonte": "thestatsapi",
            "aplicacao_sinais": False,
        }

    def carregar_serie_thestatsapi_recente(
        self, packball_url=None, match_id=None, minutos=180,
        limite=500, agora=None
    ):
        return self._carregar_thestatsapi_recente(
            "historico_thestatsapi_live",
            packball_url=packball_url,
            match_id=match_id,
            minutos=minutos,
            limite=limite,
            agora=agora,
        )

    def carregar_odds_thestatsapi_recentes(
        self, packball_url=None, match_id=None, minutos=180,
        limite=1000, agora=None
    ):
        return self._carregar_thestatsapi_recente(
            "odds_thestatsapi_live",
            packball_url=packball_url,
            match_id=match_id,
            minutos=minutos,
            limite=limite,
            agora=agora,
        )

    def _carregar_thestatsapi_recente(
        self, tabela, *, packball_url=None, match_id=None, minutos,
        limite, agora=None
    ):
        if tabela not in (
            "historico_thestatsapi_live", "odds_thestatsapi_live"
        ):
            raise ValueError("Tabela TheStatsAPI nao permitida.")
        filtros = []
        parametros = []
        if packball_url:
            filtros.append("packball_url=?")
            parametros.append(self._validar_chave_thestatsapi(
                packball_url, "packball_url"
            ))
        if match_id:
            filtros.append("match_id=?")
            parametros.append(self._validar_chave_thestatsapi(
                match_id, "match_id"
            ))
        if not filtros:
            raise ValueError("Informe packball_url ou match_id.")
        try:
            minutos = float(minutos)
            limite = int(limite)
        except (TypeError, ValueError) as erro:
            raise ValueError("Janela ou limite TheStatsAPI invalido.") from erro
        if minutos <= 0 or not 1 <= limite <= 10000:
            raise ValueError("Janela ou limite TheStatsAPI invalido.")
        referencia = agora or datetime.now()
        if not isinstance(referencia, datetime):
            referencia = datetime.fromisoformat(normalizar_data(referencia))
        inicio = (
            referencia - timedelta(minutes=minutos)
        ).replace(microsecond=0).isoformat()
        parametros.extend((inicio, referencia.isoformat(), limite))
        linhas = self.conexao.execute(
            f"""
            SELECT * FROM {tabela}
            WHERE {' AND '.join(filtros)}
              AND datetime(coletado_em) >= datetime(?)
              AND datetime(coletado_em) <= datetime(?)
            ORDER BY datetime(coletado_em) ASC, id ASC
            LIMIT ?
            """,
            parametros,
        ).fetchall()
        resultado = [dict(linha) for linha in linhas]
        for item in resultado:
            item["aplicacao_sinais"] = False
        return resultado

    def resumir_cobertura_thestatsapi(
        self, janela_minutos=60, agora=None
    ):
        try:
            janela_minutos = float(janela_minutos)
        except (TypeError, ValueError) as erro:
            raise ValueError("Janela de cobertura invalida.") from erro
        if janela_minutos <= 0:
            raise ValueError("Janela de cobertura invalida.")
        referencia = agora or datetime.now()
        if not isinstance(referencia, datetime):
            referencia = datetime.fromisoformat(normalizar_data(referencia))
        referencia = referencia.replace(microsecond=0)
        inicio = (
            referencia - timedelta(minutes=janela_minutos)
        ).isoformat()
        stats = self.conexao.execute(
            """
            SELECT COUNT(*) AS snapshots,
                   COUNT(DISTINCT packball_url) AS jogos,
                   SUM(CASE WHEN completo=1 THEN 1 ELSE 0 END) AS completos,
                   MAX(coletado_em) AS ultima_coleta
            FROM historico_thestatsapi_live
            WHERE datetime(coletado_em) >= datetime(?)
              AND datetime(coletado_em) <= datetime(?)
            """,
            (inicio, referencia.isoformat()),
        ).fetchone()
        odds = self.conexao.execute(
            """
            SELECT COUNT(*) AS ofertas,
                   COUNT(DISTINCT packball_url) AS jogos,
                   COUNT(DISTINCT bookmaker) AS bookmakers,
                   COUNT(DISTINCT mercado || '|' || periodo) AS mercados,
                   MAX(coletado_em) AS ultima_coleta
            FROM odds_thestatsapi_live
            WHERE datetime(coletado_em) >= datetime(?)
              AND datetime(coletado_em) <= datetime(?)
            """,
            (inicio, referencia.isoformat()),
        ).fetchone()
        pareamentos_total = self.conexao.execute(
            "SELECT COUNT(*) FROM pareamentos_thestatsapi"
        ).fetchone()[0]
        pareamentos_recentes = self.conexao.execute(
            """
            SELECT COUNT(*) FROM pareamentos_thestatsapi
            WHERE datetime(atualizado_em) >= datetime(?)
              AND datetime(atualizado_em) <= datetime(?)
            """,
            (inicio, referencia.isoformat()),
        ).fetchone()[0]
        snapshots = int(stats["snapshots"] or 0)
        jogos_stats = int(stats["jogos"] or 0)
        completos = int(stats["completos"] or 0)
        jogos_odds = int(odds["jogos"] or 0)
        return {
            "saudavel": True,
            "estado": "sombra",
            "fonte": "thestatsapi",
            "aplicacao_sinais": False,
            "janela_minutos": janela_minutos,
            "inicio": inicio,
            "fim": referencia.isoformat(),
            "pareamentos_total": int(pareamentos_total or 0),
            "pareamentos_recentes": int(pareamentos_recentes or 0),
            "jogos_com_stats": jogos_stats,
            "snapshots_stats": snapshots,
            "snapshots_completos": completos,
            "cobertura_stats_completa": round(
                completos / snapshots, 4
            ) if snapshots else 0.0,
            "ultima_coleta_stats": stats["ultima_coleta"],
            "jogos_com_odds": jogos_odds,
            "ofertas_odds": int(odds["ofertas"] or 0),
            "bookmakers": int(odds["bookmakers"] or 0),
            "mercados": int(odds["mercados"] or 0),
            "cobertura_odds_por_jogo": round(
                jogos_odds / jogos_stats, 4
            ) if jogos_stats else 0.0,
            "ultima_coleta_odds": odds["ultima_coleta"],
        }

    @staticmethod
    def _ofertas_de_fonte(odds, fonte):
        """Extrai ofertas normalizadas preservando mercado e periodo."""
        encontradas = []
        for tipo in ("pre_jogo", "ao_vivo"):
            for mercado in (odds or {}).get(tipo) or []:
                if not isinstance(mercado, dict):
                    continue
                grupos = [
                    ("FT", mercado.get("ofertas") or []),
                    ("HT", mercado.get("ofertas_ht") or []),
                ]
                grupos.extend(
                    (str(periodo), (dados or {}).get("ofertas") or [])
                    for periodo, dados in (
                        mercado.get("ofertas_periodos") or {}
                    ).items()
                )
                for periodo, ofertas in grupos:
                    for oferta in ofertas:
                        if not isinstance(oferta, dict):
                            continue
                        if str(oferta.get("fonte") or "").casefold() != (
                            str(fonte).casefold()
                        ):
                            continue
                        encontradas.append({
                            "tipo": tipo,
                            "categoria": mercado.get("categoria"),
                            "tipo_mercado": mercado.get("tipo_mercado"),
                            "periodo": periodo,
                            "oferta": oferta,
                        })
        return encontradas

    def _registro_odds_janela_temporal(
        self, partida_id, snapshot_id, registro,
    ):
        """Reconstrói odds ao vivo próximas preservando sua proveniência.

        Fontes distintas nem sempre são coletadas no mesmo snapshot. A
        comparação continua exata por mercado/linha/seleção, mas pode usar o
        snapshot imediatamente anterior quando os instantes estiverem dentro
        da janela máxima aceita pelo comparador.
        """
        observado_em = str(registro.get("coletado_em") or "")
        try:
            observado_data = datetime.fromisoformat(observado_em)
            if observado_data.tzinfo is not None:
                observado_data = observado_data.astimezone().replace(
                    tzinfo=None
                )
        except (TypeError, ValueError, OSError):
            return registro
        linhas = self.conexao.execute(
            """
            SELECT s.id AS snapshot_origem, s.coletado_em,
                   s.placar AS placar_origem,
                   s.status AS status_origem,
                   o.tipo, o.mercado, o.dados, o.estrutura_json
            FROM snapshots s
            JOIN odds o ON o.snapshot_id=s.id
            WHERE s.partida_id=? AND s.id<=?
            ORDER BY s.id DESC, o.id DESC
            LIMIT 400
            """,
            (int(partida_id), int(snapshot_id)),
        ).fetchall()
        mercados = []
        limite = float(INTERVALO_FONTES_MAXIMO_SEGUNDOS)
        for linha in linhas:
            if str(linha["tipo"] or "") not in {
                "ao_vivo", "referencia_sombra",
            }:
                continue
            try:
                instante_data = datetime.fromisoformat(
                    str(linha["coletado_em"])
                )
                if instante_data.tzinfo is not None:
                    instante_data = instante_data.astimezone().replace(
                        tzinfo=None
                    )
            except (TypeError, ValueError, OSError):
                continue
            idade = (observado_data - instante_data).total_seconds()
            if idade < -1.0 or idade > limite:
                continue
            try:
                estrutura = json.loads(linha["estrutura_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(estrutura, dict):
                continue
            mercado = {
                "mercado": linha["mercado"],
                "dados": linha["dados"],
                **estrutura,
                "_snapshot_origem": int(linha["snapshot_origem"]),
                "_placar_origem": linha["placar_origem"],
                "_status_origem": linha["status_origem"],
            }
            mercado.setdefault("coletado_em", linha["coletado_em"])
            mercados.append(mercado)
        if not mercados:
            return registro
        temporal = dict(registro)
        temporal["odds"] = {"pre_jogo": [], "ao_vivo": mercados}
        return temporal

    def _salvar_comparacoes_odds_fontes(
        self, partida_id, snapshot_id, registro, *, reconstruir_temporal=True,
    ):
        """Persiste a coorte sombra exata sem participar da decisao."""
        if reconstruir_temporal:
            registro = self._registro_odds_janela_temporal(
                partida_id, snapshot_id, registro
            )
        comparacoes = construir_comparacoes_multifonte(
            registro, partida_id, snapshot_id
        )
        if not comparacoes:
            return 0
        campos = (
            "snapshot_id", "partida_id", "observado_em", "placar",
            "status", "minuto", "categoria", "escopo", "periodo",
            "linha", "selecao", "fonte_a", "bookmaker_a", "odd_a",
            "coletado_em_a", "snapshot_fonte_a",
            "placar_fonte_a", "status_fonte_a", "minuto_fonte_a",
            "fonte_b",
            "bookmaker_b", "odd_b", "coletado_em_b", "snapshot_fonte_b",
            "placar_fonte_b", "status_fonte_b", "minuto_fonte_b",
            "fonte_melhor", "bookmaker_melhor",
            "odd_melhor", "fonte_controle", "bookmaker_controle",
            "odd_controle", "delta_absoluto", "delta_relativo",
            "intervalo_fontes_segundos", "frescor_maximo_segundos",
            "diferenca_minutos",
            "compatibilidade_bookmaker", "estado", "motivos_json",
            "versao", "evidencia_sha256",
        )
        total_antes = self.conexao.total_changes
        marcadores = ", ".join("?" for _ in campos)
        self.conexao.executemany(
            f"""
            INSERT OR IGNORE INTO comparacoes_odds_fontes (
                snapshot_id, partida_id, observado_em, placar, status,
                minuto, categoria, escopo, periodo, linha, selecao,
                fonte_a, bookmaker_a, odd_a, coletado_em_a,
                snapshot_fonte_a,
                placar_fonte_a, status_fonte_a, minuto_fonte_a,
                fonte_b, bookmaker_b, odd_b, coletado_em_b,
                snapshot_fonte_b,
                placar_fonte_b, status_fonte_b, minuto_fonte_b,
                fonte_melhor, bookmaker_melhor, odd_melhor,
                fonte_controle, bookmaker_controle, odd_controle,
                delta_absoluto, delta_relativo,
                intervalo_fontes_segundos, frescor_maximo_segundos,
                diferenca_minutos,
                compatibilidade_bookmaker, estado, motivos_json,
                versao, evidencia_sha256
            ) VALUES ({marcadores})
            """,
            [tuple(item.get(campo) for campo in campos)
             for item in comparacoes],
        )
        return self.conexao.total_changes - total_antes

    def registrar_comparacao_acompanhamento_odd_api(
        self, sinal_id, oferta, estado_jogo, *, consultado_em=None,
    ):
        """Compara a cotacao tecnica com a API rapida sem nova chamada.

        A observacao usa apenas a mesma linha de gols e preserva o placar,
        minuto e instante de cada fonte. Ela alimenta exclusivamente a
        avaliacao prospectiva de desajustes; nunca aprova um sinal.
        """
        if not isinstance(oferta, dict):
            return {"estado": "oferta_invalida", "persistidos": 0}
        origem = self.conexao.execute(
            """
            SELECT s.partida_id, s.snapshot_id, s.mercado, s.linha, s.odd,
                   s.features_json, snapshot.coletado_em AS snapshot_em,
                   snapshot.placar AS placar_origem,
                   snapshot.status AS status_origem
            FROM sinais s
            JOIN snapshots snapshot ON snapshot.id=s.snapshot_id
            WHERE s.id=?
            """,
            (int(sinal_id),),
        ).fetchone()
        if origem is None or origem["mercado"] not in {"gol_ft", "gol_ht"}:
            return {"estado": "mercado_nao_comparavel", "persistidos": 0}
        try:
            linha_origem = float(origem["linha"])
            linha_atual = float(oferta.get("linha"))
            odd_origem = float(origem["odd"])
            odd_atual = float(oferta.get("odd"))
        except (TypeError, ValueError):
            return {"estado": "linha_ou_odd_invalida", "persistidos": 0}
        if not math.isclose(linha_origem, linha_atual, abs_tol=1e-9):
            return {"estado": "linha_incompativel", "persistidos": 0}
        try:
            features = json.loads(origem["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        fonte_origem = str(features.get("fonte_odds") or "").strip().casefold()
        fonte_atual = str(oferta.get("fonte") or "").strip().casefold()
        if not fonte_origem or not fonte_atual:
            return {"estado": "fonte_indeterminada", "persistidos": 0}
        if fonte_origem == fonte_atual:
            return {"estado": "mesma_fonte", "persistidos": 0}

        consultado_em = normalizar_data(consultado_em)
        coletado_atual = oferta.get("coletado_em")
        if not coletado_atual:
            try:
                idade = max(float(oferta.get("idade_segundos")), 0.0)
                coletado_atual = (
                    datetime.fromisoformat(consultado_em)
                    - timedelta(seconds=idade)
                ).isoformat()
            except (TypeError, ValueError):
                coletado_atual = None
        minuto_origem = None
        correspondencia = re.search(
            r"\d+(?:[.,]\d+)?", str(origem["status_origem"] or "")
        )
        if correspondencia:
            try:
                minuto_origem = float(
                    correspondencia.group(0).replace(",", ".")
                )
            except ValueError:
                minuto_origem = None
        try:
            minuto_atual = float((estado_jogo or {}).get("minuto"))
        except (TypeError, ValueError):
            minuto_atual = None
        placar_atual = (estado_jogo or {}).get("placar")
        status_atual = (estado_jogo or {}).get("status")
        periodo = "1T" if origem["mercado"] == "gol_ht" else "FT"
        chave_ofertas = "ofertas_ht" if periodo == "1T" else "ofertas"

        def mercado(fonte, bookmaker, odd, coletado, placar, status,
                    minuto, snapshot_origem=None):
            oferta_normalizada = {
                "linha": linha_origem,
                "over": odd,
                "fonte": fonte,
                "bookmaker": str(bookmaker or "").strip().casefold(),
                "coletado_em": coletado,
                "_snapshot_origem": snapshot_origem,
                "_placar_origem": placar,
                "_status_origem": status,
                "_minuto_origem": minuto,
            }
            return {
                "categoria": "gols",
                "escopo": "total",
                "fonte": fonte,
                "bookmaker": oferta_normalizada["bookmaker"],
                "coletado_em": coletado,
                "ofertas": (
                    [oferta_normalizada] if chave_ofertas == "ofertas" else []
                ),
                "ofertas_ht": (
                    [oferta_normalizada]
                    if chave_ofertas == "ofertas_ht" else []
                ),
                "_snapshot_origem": snapshot_origem,
                "_placar_origem": placar,
                "_status_origem": status,
                "_minuto_origem": minuto,
            }

        registro = {
            "coletado_em": consultado_em,
            "placar": placar_atual,
            "status": status_atual,
            "minuto": minuto_atual,
            "odds": {"pre_jogo": [], "ao_vivo": [
                mercado(
                    fonte_origem, features.get("bookmaker_odds"),
                    odd_origem,
                    features.get("coletado_em_odds") or origem["snapshot_em"],
                    origem["placar_origem"], origem["status_origem"],
                    minuto_origem, int(origem["snapshot_id"]),
                ),
                mercado(
                    fonte_atual, oferta.get("bookmaker"), odd_atual,
                    coletado_atual, placar_atual, status_atual,
                    minuto_atual,
                ),
            ]},
        }
        with self.conexao:
            persistidos = self._salvar_comparacoes_odds_fontes(
                int(origem["partida_id"]), int(origem["snapshot_id"]),
                registro, reconstruir_temporal=False,
            )
        return {
            "estado": "comparacao_registrada" if persistidos else "sem_nova_comparacao",
            "persistidos": int(persistidos),
            "aplicacao_sinais": False,
            "chamadas_api_adicionais": 0,
        }

    def registrar_corroboracao_acompanhamento_odd_api(
        self, sinal_id, odds, estado_jogo, *, consultado_em=None,
    ):
        """Congela a primeira comparação BetsAPI/API-Football no alvo.

        Apenas fontes com contrato, identidade e relógio novamente validados
        entram na evidência. O resultado alimenta a coorte prospectiva de
        desajustes e nunca autoriza ou reprova o sinal atual.
        """
        if not isinstance(odds, dict):
            return {"estado": "odds_invalidas", "persistidos": 0}
        origem = self.conexao.execute(
            """
            SELECT s.partida_id, s.snapshot_id, s.mercado, s.linha,
                   p.mandante, p.visitante
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.id=?
            """,
            (int(sinal_id),),
        ).fetchone()
        if origem is None or origem["mercado"] not in {"gol_ft", "gol_ht"}:
            return {"estado": "mercado_nao_comparavel", "persistidos": 0}
        consultado_em = normalizar_data(consultado_em)
        try:
            instante_consulta = datetime.fromisoformat(consultado_em)
            linha_alvo = float(origem["linha"])
        except (TypeError, ValueError):
            return {"estado": "consulta_ou_linha_invalida", "persistidos": 0}
        estado = dict(estado_jogo) if isinstance(estado_jogo, dict) else {}
        estado.update({
            "mandante": origem["mandante"],
            "visitante": origem["visitante"],
        })
        try:
            minuto_atual = float(estado.get("minuto"))
        except (TypeError, ValueError):
            minuto_atual = None
        periodo = "1T" if origem["mercado"] == "gol_ht" else "FT"
        mercados_validos = []
        fontes_validas = set()
        descartes = []
        for estrutura in odds.get("ao_vivo") or []:
            if not isinstance(estrutura, dict):
                continue
            exata = extrair_odd_exata_acompanhamento(
                {"ao_vivo": [estrutura]},
                origem["mercado"],
                linha_alvo,
            )
            if exata is None:
                continue
            contrato = validar_contrato_mercado_oferta(
                exata,
                origem["mercado"],
                linha_alvo,
                exigir_origem=True,
            )
            identidade = validar_identidade_evento_oferta(exata, estado)
            temporal = validar_proveniencia_temporal_oferta(
                exata, agora=instante_consulta
            )
            if contrato.get("valido") is not True:
                descartes.append(str(
                    contrato.get("motivo") or "contrato_invalido"
                ))
                continue
            if identidade.get("valida") is not True:
                descartes.append(str(
                    identidade.get("motivo") or "identidade_invalida"
                ))
                continue
            if temporal.get("valida") is not True:
                descartes.append(str(
                    temporal.get("motivo") or "relogio_invalido"
                ))
                continue
            fonte = str(exata.get("fonte") or "").strip().casefold()
            if not fonte:
                descartes.append("fonte_indeterminada")
                continue
            minuto_origem = (
                max(
                    minuto_atual
                    - float(temporal["idade_instante_segundos"]) / 60.0,
                    0.0,
                )
                if minuto_atual is not None else None
            )
            oferta_normalizada = {
                "linha": linha_alvo,
                "over": contrato["odd"],
                "under": contrato.get("odd_oposta"),
                "fonte": fonte,
                "bookmaker": exata.get("bookmaker"),
                "coletado_em": exata.get("coletado_em"),
                "idade_segundos": exata.get("idade_segundos"),
                "_placar_origem": estado.get("placar"),
                "_status_origem": estado.get("status"),
                "_minuto_origem": minuto_origem,
            }
            mercados_validos.append({
                "categoria": "gols",
                "escopo": "total",
                "formato": "duas_opcoes",
                "fonte": fonte,
                "bookmaker": exata.get("bookmaker"),
                "coletado_em": exata.get("coletado_em"),
                "ofertas": (
                    [oferta_normalizada] if periodo == "FT" else []
                ),
                "ofertas_ht": (
                    [oferta_normalizada] if periodo == "1T" else []
                ),
                "_placar_origem": estado.get("placar"),
                "_status_origem": estado.get("status"),
                "_minuto_origem": minuto_origem,
            })
            fontes_validas.add(fonte)
        if len(fontes_validas) < 2:
            return {
                "estado": "fontes_independentes_insuficientes",
                "persistidos": 0,
                "fontes_validas": sorted(fontes_validas),
                "descartes": sorted(set(descartes)),
                "aplicacao_sinais": False,
            }
        registro = {
            "coletado_em": consultado_em,
            "placar": estado.get("placar"),
            "status": estado.get("status"),
            "minuto": minuto_atual,
            "_motivo_comparacao": "corroboracao_odd_entrada_rapida",
            "odds": {"pre_jogo": [], "ao_vivo": mercados_validos},
        }
        with self.conexao:
            persistidos = self._salvar_comparacoes_odds_fontes(
                int(origem["partida_id"]),
                int(origem["snapshot_id"]),
                registro,
                reconstruir_temporal=False,
            )
        return {
            "estado": (
                "corroboracao_registrada"
                if persistidos else "corroboracao_ja_registrada"
            ),
            "persistidos": int(persistidos),
            "fontes_validas": sorted(fontes_validas),
            "descartes": sorted(set(descartes)),
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }

    def resumir_comparacoes_odds_fontes(self, desde=None):
        filtros = ""
        parametros = []
        if desde is not None:
            filtros = "WHERE datetime(observado_em)>=datetime(?)"
            parametros.append(str(desde))
        linhas = self.conexao.execute(
            f"""
            SELECT estado, COUNT(*) AS registros,
                   COUNT(DISTINCT partida_id) AS jogos
            FROM comparacoes_odds_fontes
            {filtros}
            GROUP BY estado
            ORDER BY registros DESC
            """,
            parametros,
        ).fetchall()
        por_estado = {
            str(linha["estado"]): {
                "registros": int(linha["registros"] or 0),
                "jogos": int(linha["jogos"] or 0),
            }
            for linha in linhas
        }
        return {
            "registros": sum(
                item["registros"] for item in por_estado.values()
            ),
            "por_estado": por_estado,
            "imutavel": True,
            "aplicacao_sinais": False,
        }

    def _salvar_observacao_the_odds_api(
        self, partida_id, snapshot_id, coletado_em, registro
    ):
        diagnostico_raiz = (
            (registro.get("qualidade") or {}).get("the_odds_api") or {}
        )
        diagnostico_sombra = (
            diagnostico_raiz.get("amostragem_referencia_sombra") or {}
        )
        reserva_sombra = diagnostico_sombra.get("reserva") or {}
        amostragem_sombra_participou = bool(
            isinstance(reserva_sombra, dict)
            and reserva_sombra.get("autorizada") is True
        )
        preselecao_cobertura = diagnostico_sombra.get(
            "preselecao_cobertura"
        ) or {}
        amostragem_sombra_preselecionou = bool(
            isinstance(preselecao_cobertura, dict)
            and preselecao_cobertura.get("executada") is True
        )
        preselecao_evento = diagnostico_sombra.get(
            "preselecao_evento"
        ) or {}
        amostragem_sombra_preselecionou_evento = bool(
            isinstance(preselecao_evento, dict)
            and preselecao_evento.get("executada") is True
        )
        diagnostico = (
            diagnostico_sombra
            if (
                amostragem_sombra_participou
                or amostragem_sombra_preselecionou
                or amostragem_sombra_preselecionou_evento
                or diagnostico_sombra.get("consultados")
            )
            else diagnostico_raiz
        )
        if diagnostico.get("ativa") is not True:
            return None
        motivo = str(diagnostico.get("motivo") or "").strip()
        # Sem mercado compativel o provedor nem participou desta decisao.
        if not motivo or motivo == "sem_mercado_compativel":
            return None
        odds_origem = (
            registro.get("odds_referencia_sombra") or {}
            if amostragem_sombra_participou
            else registro.get("odds") or {}
        )
        ofertas = self._ofertas_de_fonte(odds_origem, "the_odds_api")
        oferta_json = (
            json.dumps(
                ofertas, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            )
            if ofertas else None
        )
        evidencia_sha256 = (
            hashlib.sha256(oferta_json.encode("utf-8")).hexdigest()
            if oferta_json else None
        )
        consultados = [
            str(item) for item in diagnostico.get("consultados") or []
        ]
        periodos = []
        if any(item.endswith("_h1") for item in consultados):
            periodos.append("HT")
        if any(not item.endswith("_h1") for item in consultados):
            periodos.append("FT")
        estado = {
            "oferta_anexada": "oferta_disponivel",
            "mercado_sem_oferta_fresca": "consultado_sem_oferta",
            "evento_nao_encontrado": "evento_nao_encontrado",
            "competicao_nao_coberta": "competicao_nao_coberta",
        }.get(motivo, motivo)
        metodo_coleta = (
            "amostragem_referencia_sombra"
            if amostragem_sombra_participou
            else "amostragem_referencia_preselecao"
            if (
                amostragem_sombra_preselecionou
                or amostragem_sombra_preselecionou_evento
            )
            else "automatizada"
        )
        auditoria_amostragem = (
            diagnostico_sombra.get("auditoria_amostragem") or {}
        )
        if not isinstance(auditoria_amostragem, dict):
            auditoria_amostragem = {}
        metadados = {}
        if (
            amostragem_sombra_participou
            or amostragem_sombra_preselecionou
            or amostragem_sombra_preselecionou_evento
        ):
            versao_regular = str(
                auditoria_amostragem.get("versao") or ""
            ).strip()
            if versao_regular not in {
                "amostragem-referencia-sombra-auditoria-v4",
                "amostragem-referencia-sombra-auditoria-v5",
            }:
                versao_regular = (
                    "amostragem-referencia-sombra-auditoria-v4"
                )
            versao_auditoria = (
                "amostragem-referencia-sombra-auditoria-v6"
                if auditoria_amostragem.get("funil_selecao_versao")
                == "funil-referencia-sombra-rapida-v1"
                else versao_regular
            )
            metadados = {
                "versao": versao_auditoria,
                "tipo_amostra": reserva_sombra.get("tipo_amostra"),
                "uso_dia": reserva_sombra.get("uso_dia"),
                "uso_jogo_dia": reserva_sombra.get("uso_jogo_dia"),
                "limite_efetivo_jogo_dia": reserva_sombra.get(
                    "limite_efetivo_jogo_dia"
                ),
                "recuperacao_coorte_solicitada": bool(
                    diagnostico_sombra.get(
                        "recuperacao_coorte_solicitada", False
                    )
                ),
                "recuperacao_coorte_aplicada": bool(
                    reserva_sombra.get(
                        "recuperacao_coorte_aplicada", False
                    )
                ),
                "jogos_distintos_dia": reserva_sombra.get(
                    "jogos_distintos_dia"
                ),
                "ciclo_em": auditoria_amostragem.get("ciclo_em"),
                "posicao_fila": auditoria_amostragem.get("posicao_fila"),
                "tarefas_ciclo": auditoria_amostragem.get("tarefas_ciclo"),
                "fila_operacional": auditoria_amostragem.get(
                    "fila_operacional"
                ),
                "origem_coleta": auditoria_amostragem.get(
                    "origem_coleta"
                ),
                "sinal_origem_id": auditoria_amostragem.get(
                    "sinal_origem_id"
                ),
                "sinal_tecnico_id": auditoria_amostragem.get(
                    "sinal_tecnico_id"
                ),
                "sinal_enviado_id": auditoria_amostragem.get(
                    "sinal_enviado_id"
                ),
                "alerta_enviado_em": auditoria_amostragem.get(
                    "alerta_enviado_em"
                ),
                "alerta_enviado_comprovado": bool(
                    auditoria_amostragem.get(
                        "alerta_enviado_comprovado", False
                    )
                ),
                "referencia_posterior_alerta": bool(
                    auditoria_amostragem.get(
                        "referencia_posterior_alerta", False
                    )
                ),
                "linhagem_materializacao_comprovada": bool(
                    auditoria_amostragem.get(
                        "linhagem_materializacao_comprovada", False
                    )
                ),
                "criterios_materializacao_comprovados": bool(
                    auditoria_amostragem.get(
                        "criterios_materializacao_comprovados", False
                    )
                ),
                "placar_materializacao_comprovado": bool(
                    auditoria_amostragem.get(
                        "placar_materializacao_comprovado", False
                    )
                ),
                "placar_referencia_contexto_comprovado": bool(
                    auditoria_amostragem.get(
                        "placar_referencia_contexto_comprovado", False
                    )
                ),
                "timestamp_referencia_comprovado": bool(
                    auditoria_amostragem.get(
                        "timestamp_referencia_comprovado", False
                    )
                ),
                "placar_confirmado": auditoria_amostragem.get(
                    "placar_confirmado"
                ),
                "status_confirmado": auditoria_amostragem.get(
                    "status_confirmado"
                ),
                "referencia_publicada_em": auditoria_amostragem.get(
                    "referencia_publicada_em"
                ),
                "referencia_recebida_em": auditoria_amostragem.get(
                    "referencia_recebida_em"
                ),
                "referencia_idade_segundos": auditoria_amostragem.get(
                    "referencia_idade_segundos"
                ),
                "funil_selecao_versao": auditoria_amostragem.get(
                    "funil_selecao_versao"
                ),
                "mercado_alvo": auditoria_amostragem.get(
                    "mercado_alvo"
                ),
                "linha_alvo": auditoria_amostragem.get(
                    "linha_alvo"
                ),
                "bookmaker_alvo": auditoria_amostragem.get(
                    "bookmaker_alvo"
                ),
                "liga": auditoria_amostragem.get("liga"),
                "minuto": auditoria_amostragem.get("minuto"),
                "preselecao_cobertura_versao": (
                    preselecao_cobertura.get("versao")
                ),
                "preselecao_executada": bool(
                    preselecao_cobertura.get("executada") is True
                ),
                "competicao_coberta": preselecao_cobertura.get(
                    "coberta"
                ),
                "esportes_candidatos": list(
                    preselecao_cobertura.get(
                        "esportes_candidatos"
                    ) or []
                ),
                "preselecao_evento_versao": (
                    preselecao_evento.get("versao")
                ),
                "preselecao_evento_executada": bool(
                    preselecao_evento.get("executada") is True
                ),
                "evento_pareado_pre_reserva": (
                    preselecao_evento.get("pareado")
                ),
                "evento_sport_key": preselecao_evento.get(
                    "sport_key"
                ),
                "evento_externo_id_pre_reserva": (
                    preselecao_evento.get("evento_externo_id")
                ),
                "evento_similaridade": preselecao_evento.get(
                    "similaridade"
                ),
                "evento_mandante_observado": (
                    preselecao_evento.get("mandante_observado")
                ),
                "evento_visitante_observado": (
                    preselecao_evento.get("visitante_observado")
                ),
                "consulta_eventos_sem_custo": bool(
                    preselecao_evento.get("consulta_eventos") is True
                ),
                "reserva_consumida": bool(
                    diagnostico_sombra.get("reserva_consumida", False)
                ),
                "mercados_elegiveis_betsapi": list(
                    diagnostico_sombra.get(
                        "mercados_elegiveis_betsapi"
                    ) or []
                ),
                "custo_estimado_creditos": (
                    diagnostico_sombra.get("custo_estimado_creditos")
                ),
                "consulta_combinada": bool(
                    diagnostico_sombra.get("consulta_combinada", False)
                ),
                "selecao_antes_resultado": True,
                "aplicacao_sinais": False,
                "telegram": False,
            }
        cursor = self.conexao.execute(
            """
            INSERT INTO observacoes_fontes_odds (
                partida_id, fonte, consultado_em, estado,
                evento_externo_id, mandante_observado,
                visitante_observado, periodo, mercado,
                motivo, oferta_json, url_origem, metodo_coleta,
                metadados_json, evidencia_sha256, evidencia_referencia
            ) VALUES (?, 'the_odds_api', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?)
            """,
            (
                partida_id, coletado_em, estado,
                diagnostico.get("evento_externo_id"),
                diagnostico.get("mandante_observado"),
                diagnostico.get("visitante_observado"),
                ",".join(periodos) or None,
                ",".join(consultados) or None,
                motivo, oferta_json, registro.get("url"),
                metodo_coleta,
                json.dumps(
                    metadados, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"),
                ),
                evidencia_sha256, f"snapshot:{snapshot_id}",
            ),
        )
        return int(cursor.lastrowid)

    def registrar_referencia_sombra_acompanhamento_odd(
        self,
        sinal_id,
        odds_referencia,
        diagnostico,
        estado_jogo,
        *,
        consultado_em=None,
        origem_sinal_id=None,
        sinal_enviado_id=None,
    ):
        """Audita a consulta independente feita pela fila rapida.

        A referencia permanece fora de ``odds`` e, portanto, nunca participa
        da selecao ou do envio do sinal. O registro liga custo, pareamento,
        mercado e estado da partida ao snapshot tecnico que originou a fila.
        """
        if not isinstance(diagnostico, dict):
            return {"estado": "diagnostico_invalido", "persistido": False}
        if not isinstance(odds_referencia, dict):
            return {"estado": "odds_invalidas", "persistido": False}
        origem = self.conexao.execute(
            """
            SELECT s.partida_id, s.snapshot_id, s.mercado, s.linha,
                   p.packball_url, p.liga
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.id=?
            """,
            (int(sinal_id),),
        ).fetchone()
        if origem is None:
            return {"estado": "sinal_inexistente", "persistido": False}
        if origem["mercado"] not in {"gol_ft", "gol_ht"}:
            return {"estado": "mercado_nao_suportado", "persistido": False}

        consultado_em = normalizar_data(consultado_em)
        alerta_enviado = None
        if sinal_enviado_id is not None:
            try:
                sinal_enviado_id = int(sinal_enviado_id)
            except (TypeError, ValueError):
                sinal_enviado_id = None
        if sinal_enviado_id is not None:
            alerta_enviado = self.conexao.execute(
                """
                SELECT s.id, s.partida_id, s.mercado, s.linha,
                       s.features_json, snapshot.placar AS placar_sinal,
                       e.entregue_em
                FROM sinais s
                JOIN snapshots snapshot ON snapshot.id=s.snapshot_id
                JOIN entregas_alertas e ON e.sinal_id=s.id
                WHERE s.id=? AND s.partida_id=?
                  AND e.status='entregue'
                  AND e.entregue_em IS NOT NULL
                  AND e.canal NOT LIKE '%:resultado'
                  AND e.canal NOT LIKE '%:green_antecipado'
                ORDER BY datetime(e.entregue_em), e.id
                LIMIT 1
                """,
                (sinal_enviado_id, int(origem["partida_id"])),
            ).fetchone()
        sinal_origem_esperado = int(
            origem_sinal_id if origem_sinal_id is not None else sinal_id
        )
        oferta_exata = extrair_odd_exata_acompanhamento(
            odds_referencia, origem["mercado"], origem["linha"]
        )
        materializacao = {}
        if alerta_enviado is not None:
            try:
                features_enviadas = json.loads(
                    str(alerta_enviado["features_json"] or "{}")
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                features_enviadas = {}
            materializacao = (
                features_enviadas.get("acompanhamento_odd_rapido") or {}
                if isinstance(features_enviadas, dict) else {}
            )
            if not isinstance(materializacao, dict):
                materializacao = {}
        try:
            linhagem_materializacao_comprovada = bool(
                materializacao.get("versao")
                == VERSAO_MATERIALIZACAO_RAPIDA
                and int(materializacao.get("leitura_tecnica_sinal_id"))
                == int(sinal_id)
                and int(materializacao.get("origem_sinal_id"))
                == sinal_origem_esperado
            )
        except (TypeError, ValueError):
            linhagem_materializacao_comprovada = False
        criterios = set(materializacao.get("criterios_revalidados") or [])
        criterios_materializacao_comprovados = bool(
            materializacao.get("linha_exata_confirmada") is True
            and {
                "placar_inalterado", "linha_exata_disponivel",
                "odd_atual_fresca",
            }.issubset(criterios)
        )
        placar_confirmado = str(
            (estado_jogo or {}).get("placar") or ""
        ).strip()
        placar_materializacao_comprovado = bool(
            alerta_enviado is not None and placar_confirmado
            and str(alerta_enviado["placar_sinal"] or "").strip()
            == placar_confirmado
            and str(
                materializacao.get("placar_confirmado") or ""
            ).strip() == placar_confirmado
        )
        identidade_referencia = (
            (oferta_exata or {}).get("identidade_evento") or {}
        )
        if not isinstance(identidade_referencia, dict):
            identidade_referencia = {}
        placar_referencia_contexto_comprovado = bool(
            oferta_exata is not None
            and identidade_referencia.get("confirmada") is True
            and str(
                identidade_referencia.get("placar_normalizado") or ""
            ).strip() == placar_confirmado
        )
        referencia_publicada_em = (
            (oferta_exata or {}).get("coletado_em")
        )
        referencia_recebida_em = (
            (oferta_exata or {}).get("recebido_em")
        )
        referencia_idade_segundos = (
            (oferta_exata or {}).get("idade_segundos")
        )

        def instante(valor):
            try:
                atual = datetime.fromisoformat(str(valor or ""))
            except (TypeError, ValueError):
                return None
            if atual.tzinfo is None:
                atual = atual.astimezone()
            return atual.timestamp()

        publicada_ts = instante(referencia_publicada_em)
        recebida_ts = instante(referencia_recebida_em)
        inicio_ts = instante(consultado_em)
        alerta_ts = instante(
            alerta_enviado["entregue_em"]
            if alerta_enviado is not None else None
        )
        try:
            idade_declarada = float(referencia_idade_segundos)
        except (TypeError, ValueError):
            idade_declarada = None
        idade_calculada = (
            max(recebida_ts - publicada_ts, 0.0)
            if recebida_ts is not None and publicada_ts is not None
            else None
        )
        timestamp_referencia_comprovado = bool(
            None not in {publicada_ts, recebida_ts, inicio_ts, alerta_ts}
            and inicio_ts <= recebida_ts
            and alerta_ts <= recebida_ts
            and publicada_ts <= recebida_ts + 5.0
            and idade_calculada <= 120.0
            and idade_declarada is not None
            and abs(idade_declarada - idade_calculada) <= 2.0
        )
        alerta_compativel = False
        alerta_em = None
        referencia_posterior_alerta = False
        if alerta_enviado is not None:
            try:
                alerta_compativel = bool(
                    str(alerta_enviado["mercado"]) == str(origem["mercado"])
                    and math.isclose(
                        float(alerta_enviado["linha"]),
                        float(origem["linha"]),
                        abs_tol=1e-9,
                    )
                )
            except (TypeError, ValueError):
                alerta_compativel = False
            alerta_em = alerta_enviado["entregue_em"]
            try:
                instante_alerta = datetime.fromisoformat(str(alerta_em))
                instante_referencia = datetime.fromisoformat(
                    str(consultado_em)
                )
                if instante_alerta.tzinfo is None:
                    instante_alerta = instante_alerta.astimezone()
                if instante_referencia.tzinfo is None:
                    instante_referencia = instante_referencia.astimezone()
                referencia_posterior_alerta = bool(
                    instante_referencia >= instante_alerta
                    and timestamp_referencia_comprovado
                )
            except (TypeError, ValueError, OSError):
                referencia_posterior_alerta = False
        diagnostico = dict(diagnostico)
        auditoria = dict(diagnostico.get("auditoria_amostragem") or {})
        auditoria.update({
            "origem_coleta": "monitor_odd_rapido",
            "sinal_origem_id": sinal_origem_esperado,
            "sinal_tecnico_id": int(sinal_id),
            "sinal_enviado_id": sinal_enviado_id,
            "alerta_enviado_em": alerta_em,
            "alerta_enviado_comprovado": bool(alerta_compativel),
            "referencia_posterior_alerta": bool(
                alerta_compativel and referencia_posterior_alerta
            ),
            "linhagem_materializacao_comprovada": bool(
                linhagem_materializacao_comprovada
            ),
            "criterios_materializacao_comprovados": bool(
                criterios_materializacao_comprovados
            ),
            "placar_materializacao_comprovado": bool(
                placar_materializacao_comprovado
            ),
            "placar_referencia_contexto_comprovado": bool(
                placar_referencia_contexto_comprovado
            ),
            "timestamp_referencia_comprovado": bool(
                timestamp_referencia_comprovado
            ),
            "placar_confirmado": placar_confirmado or None,
            "status_confirmado": (estado_jogo or {}).get("status"),
            "referencia_publicada_em": referencia_publicada_em,
            "referencia_recebida_em": referencia_recebida_em,
            "referencia_idade_segundos": referencia_idade_segundos,
            "funil_selecao_versao": "funil-referencia-sombra-rapida-v1",
            "mercado_alvo": origem["mercado"],
            "linha_alvo": float(origem["linha"]),
            "bookmaker_alvo": "bet365",
            "liga": auditoria.get("liga") or origem["liga"],
            "minuto": (estado_jogo or {}).get("minuto"),
            "selecao_antes_resultado": True,
            "aplicacao_sinais": False,
        })
        diagnostico["auditoria_amostragem"] = auditoria
        diagnostico["aplicacao_sinais"] = False
        diagnostico["telegram"] = False
        diagnostico["promocao_automatica"] = False
        registro = {
            "url": origem["packball_url"],
            "odds": {"pre_jogo": [], "ao_vivo": []},
            "odds_referencia_sombra": odds_referencia,
            "qualidade": {
                "the_odds_api": {
                    "ativa": bool(diagnostico.get("ativa")),
                    "motivo": "referencia_sombra_monitor_rapido",
                    "amostragem_referencia_sombra": diagnostico,
                }
            },
        }
        with self.conexao:
            observacao_id = self._salvar_observacao_the_odds_api(
                int(origem["partida_id"]),
                int(origem["snapshot_id"]),
                consultado_em,
                registro,
            )
        return {
            "estado": (
                "referencia_sombra_auditada"
                if observacao_id is not None else "referencia_nao_participou"
            ),
            "persistido": observacao_id is not None,
            "observacao_id": observacao_id,
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }

    def salvar_registro(self, registro):
        coletado_em = normalizar_data(registro.get("coletado_em"))
        qualidade = dict(registro.get("qualidade") or {})
        # Somente o ciclo técnico completo pode substituir sua análise.
        # Rechecagens de preço/finalização podem copiar a qualidade antiga,
        # mas não podem se apresentar como novas leituras de pressão/chutes.
        qualidade.pop("analise_tecnica_acompanhamento_odd", None)
        if (registro.get("_analise_tecnica_acompanhamento_odd") is True
                and not registro.get("_nao_atualizar_ultima_coleta")):
            qualidade["analise_tecnica_acompanhamento_odd"] = True
        with self.conexao:
            partida_id = self._obter_partida(
                registro,
                coletado_em,
                atualizar_ultima_coleta=not bool(
                    registro.get("_nao_atualizar_ultima_coleta")
                ),
            )
            cursor = self.conexao.execute(
                """
                INSERT OR IGNORE INTO snapshots (
                    partida_id, coletado_em, placar, status, texto_linha,
                    estatisticas_json, evolucao_json,
                    confirmacao_api_json, estatisticas_api_json,
                    contexto_api_json,
                    qualidade_dados, qualidade_json, fontes_json
                    , movimentacao_odds_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    partida_id,
                    coletado_em,
                    registro.get("placar"),
                    registro.get("status"),
                    registro.get("texto_linha"),
                    json.dumps(
                        registro.get("estatisticas") or {},
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        registro.get("evolucao") or {},
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        registro.get("confirmacao_api"),
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        registro.get("estatisticas_api"),
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        registro.get("contexto_api"),
                        ensure_ascii=False,
                    ),
                    (registro.get("qualidade") or {}).get(
                        "pontuacao", registro.get("qualidade_dados")
                    ),
                    json.dumps(
                        qualidade,
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        (registro.get("qualidade") or {}).get("fontes")
                        or ["packball"] + (
                            ["api_football"]
                            if registro.get("confirmacao_api") else []
                        ),
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        (registro.get("odds") or {}).get("movimentacao")
                        or [],
                        ensure_ascii=False,
                    ),
                ),
            )
            if cursor.rowcount == 0:
                return False

            snapshot_id = cursor.lastrowid
            def salvar_mercado_odds(tipo, mercado):
                self.conexao.execute(
                    """
                    INSERT INTO odds (
                        snapshot_id, tipo, mercado, dados,
                        estrutura_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        tipo,
                        mercado.get("mercado", ""),
                        mercado.get("dados", ""),
                        json.dumps(
                            {
                                "categoria": mercado.get("categoria"),
                                "escopo": mercado.get("escopo"),
                                "tipo_mercado": mercado.get("tipo_mercado"),
                                "formato": mercado.get("formato"),
                                "ofertas": mercado.get("ofertas") or [],
                                "ofertas_exatamente": (
                                    mercado.get("ofertas_exatamente") or []
                                ),
                                "ofertas_periodos": (
                                    mercado.get("ofertas_periodos") or {}
                                ),
                                "ofertas_ht": mercado.get("ofertas_ht") or [],
                                "selecoes": mercado.get("selecoes") or {},
                                "fonte": mercado.get("fonte"),
                                "bookmaker": mercado.get("bookmaker"),
                                "coletado_em": mercado.get("coletado_em"),
                                "recebido_em": mercado.get("recebido_em"),
                                "idade_segundos": mercado.get(
                                    "idade_segundos"
                                ),
                                "cache": mercado.get("cache")
                                if isinstance(mercado.get("cache"), bool)
                                else None,
                                "aplicacao_sinais": False
                                if tipo == "referencia_sombra" else None,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )

            odds = registro.get("odds") or {}
            for tipo in ("pre_jogo", "ao_vivo"):
                for mercado in odds.get(tipo) or []:
                    salvar_mercado_odds(tipo, mercado)
            odds_sombra = registro.get("odds_referencia_sombra") or {}
            for mercado in odds_sombra.get("ao_vivo") or []:
                salvar_mercado_odds("referencia_sombra", mercado)

            # A contraparte sombra só participa da auditoria de preço. Ela não
            # é inserida no objeto de odds usado pelo motor e, no SQLite, usa
            # um tipo separado para não ser confundida com oferta operacional.
            registro_comparacao = dict(registro)
            registro_comparacao["odds"] = {
                "pre_jogo": list(odds.get("pre_jogo") or []),
                "ao_vivo": list(odds.get("ao_vivo") or [])
                + list(odds_sombra.get("ao_vivo") or []),
            }
            self._salvar_observacao_the_odds_api(
                partida_id, snapshot_id, coletado_em, registro_comparacao
            )
            self._salvar_comparacoes_odds_fontes(
                partida_id, snapshot_id, registro_comparacao
            )

            confirmacao = registro.get("confirmacao_api") or {}
            for evento in confirmacao.get("eventos") or []:
                tempo = evento.get("time") or {}
                time_evento = evento.get("team") or {}
                jogador = evento.get("player") or {}
                self.conexao.execute(
                    """
                    INSERT INTO eventos (
                        snapshot_id, tipo, detalhe, minuto,
                        time_nome, jogador_nome, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        evento.get("type"),
                        evento.get("detail"),
                        tempo.get("elapsed"),
                        time_evento.get("name"),
                        jogador.get("name"),
                        json.dumps(evento, ensure_ascii=False),
                    ),
                )
        return snapshot_id

    def salvar_candidatos(self, snapshot_id, candidatos, criado_em=None):
        criado_em = normalizar_data(criado_em)
        linha = self.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?",
            (snapshot_id,),
        ).fetchone()
        if linha is None:
            raise ValueError("Snapshot não encontrado para salvar candidatos.")

        ids = []
        with self.conexao:
            for candidato in candidatos:
                fingerprint_esperado = fingerprint_vinculado_no_banco(
                    self.conexao, candidato["regra_versao"]
                )
                if (
                    fingerprint_esperado is not None
                    and candidato.get("regra_fingerprint")
                    != fingerprint_esperado
                ):
                    raise ValueError(
                        "Candidato sem o fingerprint vinculado da regra."
                    )
                motivos = list(candidato.get("motivos") or [])
                motivos.extend(
                    f"bloqueio:{item}"
                    for item in candidato.get("bloqueios") or []
                )
                status_persistido = candidato.get("status", "candidato")
                if status_persistido == "aprovado":
                    aberto = self.conexao.execute(
                        """
                        SELECT 1
                        FROM sinais s
                        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
                        WHERE s.partida_id=? AND s.mercado=?
                          AND s.regra_versao=? AND s.status='aprovado'
                          AND r.sinal_id IS NULL
                        LIMIT 1
                        """,
                        (
                            linha["partida_id"],
                            candidato["mercado"],
                            candidato["regra_versao"],
                        ),
                    ).fetchone()
                    if aberto is not None:
                        status_persistido = "duplicado"
                        motivos.append("bloqueio:sinal_aberto_mesmo_mercado")
                candidato["_status_persistido"] = status_persistido
                cursor = self.conexao.execute(
                    """
                    INSERT INTO sinais (
                        partida_id, snapshot_id, criado_em, mercado,
                        linha, odd, pontuacao_tecnica,
                        probabilidade_calibrada, regra_versao,
                        regra_fingerprint,
                        motivos_json, features_json, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        linha["partida_id"],
                        snapshot_id,
                        criado_em,
                        candidato["mercado"],
                        candidato.get("linha"),
                        candidato.get("odd"),
                        candidato.get("pontuacao_tecnica"),
                        candidato.get("probabilidade_calibrada"),
                        candidato["regra_versao"],
                        candidato.get("regra_fingerprint"),
                        json.dumps(motivos, ensure_ascii=False),
                        json.dumps(
                            candidato.get("features") or {},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        status_persistido,
                    ),
                )
                ids.append(cursor.lastrowid)
        return ids

    def exploracao_sombra_ja_registrada(
        self, snapshot_id, mercado, regra_versao,
        versao_experimento=None,
    ):
        """Deduplica a exploração; sem versão, preserva a consulta antiga."""
        filtro_versao = ""
        parametros = [snapshot_id, mercado, regra_versao]
        if versao_experimento is not None:
            filtro_versao = """
              AND json_extract(
                  s.features_json, '$.exploracao_sombra.versao'
              )=?
            """
            parametros.append(str(versao_experimento))
        linha = self.conexao.execute(
            f"""
            SELECT 1
            FROM snapshots atual
            JOIN sinais s ON s.partida_id=atual.partida_id
            WHERE atual.id=? AND s.mercado=? AND s.regra_versao=?
              AND json_extract(
                  s.features_json, '$.exploracao_sombra.versao'
              ) IS NOT NULL
              {filtro_versao}
            LIMIT 1
            """,
            parametros,
        ).fetchone()
        return linha is not None

    def auditoria_bloqueio_ja_registrada(
        self, snapshot_id, mercado, regra_versao, versao, bloqueios_chave,
    ):
        """Mantém uma única entrada auditável por jogo, regra e bloqueio."""
        linha = self.conexao.execute(
            """
            SELECT 1
            FROM snapshots atual
            JOIN sinais s ON s.partida_id=atual.partida_id
            WHERE atual.id=? AND s.mercado=? AND s.regra_versao=?
              AND json_extract(
                  s.features_json, '$.auditoria_bloqueio.versao'
              )=?
              AND json_extract(
                  s.features_json, '$.auditoria_bloqueio.bloqueios_chave'
              )=?
            LIMIT 1
            """,
            (
                snapshot_id, mercado, regra_versao,
                str(versao), str(bloqueios_chave),
            ),
        ).fetchone()
        return linha is not None

    def contar_exploracao_sombra_versao(self, versao):
        """Conta decisões persistidas de uma versão experimental exata."""
        if not versao:
            return 0
        padrao = f'%"versao": "{str(versao)}"%'
        linha = self.conexao.execute(
            """
            SELECT COUNT(*) AS total
            FROM sinais
            WHERE status='simulacao'
              AND features_json LIKE ?
            """,
            (padrao,),
        ).fetchone()
        return int(linha["total"] if linha is not None else 0)

    def normalizar_sinais_duplicados(self):
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE sinais SET status='duplicado'
                WHERE id IN (
                    SELECT id FROM (
                        SELECT s.id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY s.partida_id, s.mercado,
                                                s.regra_versao
                                   ORDER BY s.id
                               ) AS ordem
                        FROM sinais s
                        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
                        WHERE s.status='aprovado' AND r.sinal_id IS NULL
                    ) repetidos
                    WHERE ordem > 1
                )
                """
            )
        return cursor.rowcount

    def marcar_sinal_como_simulacao(self, sinal_id):
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE sinais SET status='simulacao'
                WHERE id=? AND status='duplicado'
                """,
                (sinal_id,),
            )
        return cursor.rowcount == 1

    def carregar_sinal_para_entrega(self, sinal_id):
        """Carrega a decisao persistida usada como autoridade do Telegram."""
        linha = self.conexao.execute(
            """
            SELECT s.id, s.mercado, s.linha, s.odd,
                   s.pontuacao_tecnica, s.probabilidade_calibrada,
                   s.regra_versao, s.regra_fingerprint, s.status,
                   s.features_json,
                   EXISTS (
                       SELECT 1 FROM resultados_sinais r
                       WHERE r.sinal_id=s.id
                   ) AS resolvido
            FROM sinais s
            WHERE s.id=?
            """,
            (int(sinal_id),),
        ).fetchone()
        return dict(linha) if linha is not None else None

    def carregar_contexto_pre_envio(self, sinal_id):
        """Carrega a evidencia persistida necessaria ao ultimo gate de envio."""
        linha_sinal = self.conexao.execute(
            """
            SELECT s.*,
                   EXISTS (
                       SELECT 1 FROM resultados_sinais r
                       WHERE r.sinal_id=s.id
                   ) AS resolvido,
                   EXISTS (
                       SELECT 1 FROM entregas_alertas e
                       WHERE e.sinal_id=s.id AND e.status='entregue'
                   ) AS entrega_ja_entregue
            FROM sinais s
            WHERE s.id=?
            """,
            (int(sinal_id),),
        ).fetchone()
        if linha_sinal is None:
            return None

        sinal = dict(linha_sinal)
        resolvido = bool(sinal.pop("resolvido"))
        entrega_ja_entregue = bool(sinal.pop("entrega_ja_entregue"))

        def carregar_json(valor, padrao):
            try:
                carregado = json.loads(valor) if valor is not None else padrao
            except (TypeError, ValueError, json.JSONDecodeError):
                return padrao
            if isinstance(padrao, list) and not isinstance(carregado, list):
                return padrao
            if isinstance(padrao, dict) and not isinstance(carregado, dict):
                return padrao
            return carregado

        sinal["motivos"] = carregar_json(sinal.get("motivos_json"), [])
        sinal["features"] = carregar_json(sinal.get("features_json"), {})

        snapshot_origem_linha = self.conexao.execute(
            "SELECT * FROM snapshots WHERE id=?",
            (sinal["snapshot_id"],),
        ).fetchone()
        snapshot_mais_recente_linha = self.conexao.execute(
            """
            SELECT * FROM snapshots
            WHERE partida_id=?
            ORDER BY datetime(coletado_em) DESC, id DESC
            LIMIT 1
            """,
            (sinal["partida_id"],),
        ).fetchone()
        partida_linha = self.conexao.execute(
            "SELECT * FROM partidas WHERE id=?",
            (sinal["partida_id"],),
        ).fetchone()

        return {
            "sinal": sinal,
            "snapshot_origem": (
                dict(snapshot_origem_linha)
                if snapshot_origem_linha is not None else None
            ),
            "snapshot_mais_recente": (
                dict(snapshot_mais_recente_linha)
                if snapshot_mais_recente_linha is not None else None
            ),
            "partida": (
                dict(partida_linha) if partida_linha is not None else None
            ),
            "resolvido": resolvido,
            "entrega_ja_entregue": entrega_ja_entregue,
        }

    def expirar_sinal_pre_envio(self, sinal_id, motivo):
        """Rejeita atomicamente um sinal obsoleto ainda nao consumido."""
        motivo = str(motivo or "").strip()
        if not motivo:
            raise ValueError("Motivo obrigatorio para expirar o sinal.")
        bloqueio = (
            motivo if motivo.startswith("bloqueio:")
            else f"bloqueio:{motivo}"
        )
        with self.conexao:
            self.conexao.execute(
                """
                WITH alvo AS (
                    SELECT id,
                           CASE
                               WHEN json_valid(motivos_json) THEN
                                   CASE
                                       WHEN json_type(motivos_json)='array'
                                       THEN motivos_json
                                       ELSE '[]'
                                   END
                               ELSE '[]'
                           END AS motivos
                    FROM sinais
                    WHERE id=? AND status='aprovado'
                      AND NOT EXISTS (
                          SELECT 1 FROM entregas_alertas e
                          WHERE e.sinal_id=sinais.id
                            AND e.status='entregue'
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM resultados_sinais r
                          WHERE r.sinal_id=sinais.id
                      )
                )
                UPDATE sinais
                SET status='rejeitado',
                    motivos_json=(
                        SELECT CASE
                            WHEN EXISTS (
                                SELECT 1 FROM json_each(alvo.motivos)
                                WHERE json_each.value=?
                            ) THEN alvo.motivos
                            ELSE json_insert(alvo.motivos, '$[#]', ?)
                        END
                        FROM alvo
                    )
                WHERE id=(SELECT id FROM alvo)
                """,
                (int(sinal_id), bloqueio, bloqueio),
            )
            alterados = self.conexao.execute(
                "SELECT changes()"
            ).fetchone()[0]
        return alterados == 1

    def invalidar_sinais_operacao_degradada(self, sinais_ids):
        """Retira do backtest sinais de um ciclo que perdeu alguma fonte."""
        ids = sorted({int(item) for item in (sinais_ids or []) if item})
        if not ids:
            return 0
        alterados = 0
        with self.conexao:
            for sinal_id in ids:
                linha = self.conexao.execute(
                    """
                    SELECT motivos_json FROM sinais
                    WHERE id=? AND status='aprovado'
                      AND NOT EXISTS (
                          SELECT 1 FROM entregas_alertas e
                          WHERE e.sinal_id=sinais.id
                            AND e.status='entregue'
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM resultados_sinais r
                          WHERE r.sinal_id=sinais.id
                      )
                    """,
                    (sinal_id,),
                ).fetchone()
                if linha is None:
                    continue
                try:
                    motivos = json.loads(linha["motivos_json"] or "[]")
                except (TypeError, ValueError, json.JSONDecodeError):
                    motivos = []
                if not isinstance(motivos, list):
                    motivos = []
                motivo = "bloqueio:operacao_degradada_no_ciclo"
                if motivo not in motivos:
                    motivos.append(motivo)
                cursor = self.conexao.execute(
                    """
                    UPDATE sinais
                    SET status='rejeitado', motivos_json=?
                    WHERE id=? AND status='aprovado'
                    """,
                    (json.dumps(motivos, ensure_ascii=False), sinal_id),
                )
                alterados += cursor.rowcount
        return alterados

    def normalizar_sinais_simulacao(self):
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE sinais SET status='simulacao'
                WHERE status='duplicado' AND EXISTS (
                    SELECT 1 FROM entregas_alertas e
                    WHERE e.sinal_id=sinais.id AND e.status='entregue'
                      AND e.canal LIKE '%:teste'
                )
                """
            )
        return cursor.rowcount

    def alerta_ja_entregue(self, sinal_id, canal):
        return self.conexao.execute(
            """
            SELECT 1 FROM entregas_alertas
            WHERE sinal_id=? AND canal=? AND status='entregue'
            LIMIT 1
            """,
            (sinal_id, canal),
        ).fetchone() is not None

    def acompanhamento_odd_ja_entregue_na_partida(self, sinal_id, canal):
        """Evita repetir o aviso ou a inscrição silenciosa em cada snapshot."""
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais atual
            JOIN sinais anterior
              ON anterior.partida_id=atual.partida_id
             AND anterior.mercado=atual.mercado
            JOIN entregas_alertas e ON e.sinal_id=anterior.id
            WHERE atual.id=? AND e.canal=?
              AND e.status IN ('entregue', 'monitoramento_silencioso')
              AND anterior.linha IS atual.linha
              AND json_extract(anterior.features_json, '$.acompanhamento_metodo_gols.metodo')
                  IS json_extract(atual.features_json, '$.acompanhamento_metodo_gols.metodo')
            LIMIT 1
            """,
            (int(sinal_id), str(canal)),
        ).fetchone() is not None

    def acompanhamentos_odd_pendentes(self, limite=50):
        """Lista observações públicas ou silenciosas ainda sem desfecho."""
        return self.conexao.execute(
            """
            SELECT s.id AS sinal_id, s.partida_id, s.snapshot_id,
                   s.mercado, s.linha, s.odd, s.features_json,
                   p.mandante, p.visitante, p.liga,
                   inicial.placar AS placar_inicial,
                   inicial.status AS status_inicial,
                   origem.canal AS canal_origem,
                   origem.status AS status_notificacao_origem,
                   origem.provedor_mensagem_id AS mensagem_id_origem
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            JOIN snapshots inicial ON inicial.id=s.snapshot_id
            JOIN entregas_alertas origem
              ON origem.sinal_id=s.id
             AND origem.status IN ('entregue', 'monitoramento_silencioso')
             AND origem.canal LIKE '%:aguardar_odd'
             AND (
                 origem.status='monitoramento_silencioso'
                 OR (
                     origem.provedor='telegram'
                     AND origem.provedor_mensagem_id IS NOT NULL
                 )
             )
            WHERE json_valid(s.features_json)
              AND json_extract(
                    s.features_json,
                    '$.acompanhamento_odd.elegivel_aviso'
                  )=1
              AND EXISTS (
                  SELECT 1 FROM snapshots posterior
                  WHERE posterior.partida_id=s.partida_id
                    AND posterior.id>s.snapshot_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas final
                  WHERE final.sinal_id=s.id
                    AND final.canal=origem.canal || ':monitoramento_final'
              )
            ORDER BY s.id
            LIMIT ?
            """,
            (int(limite),),
        ).fetchall()

    def acompanhamentos_odd_para_rechecagem_api(
        self, limite=10, *, snapshot_desde=None,
    ):
        """Retorna a leitura tecnica mais nova de cada aviso ainda aberto.

        O aviso original identifica a conversa do Telegram. A decisao usada
        pela fila rapida, contudo, e sempre o candidato elegivel mais recente
        para a mesma partida, mercado e linha. O rodizio prioriza leituras
        tecnicas recentes que estao ha mais tempo sem consulta, impedindo que
        uma sequencia de avisos novos deixe os anteriores sem acompanhamento.
        """
        return self.conexao.execute(
            f"""
            WITH avisos AS (
                SELECT origem_sinal.id AS origem_sinal_id,
                       origem_sinal.partida_id,
                       origem_sinal.mercado,
                       origem_sinal.linha,
                       json_extract(origem_sinal.features_json,
                         '$.acompanhamento_metodo_gols.metodo') AS metodo_acompanhado,
                       entrega.canal AS canal_aviso
                FROM sinais origem_sinal
                JOIN entregas_alertas entrega
                  ON entrega.sinal_id=origem_sinal.id
                 AND entrega.status IN ('entregue', 'monitoramento_silencioso')
                 AND entrega.canal LIKE '%:aguardar_odd'
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM sinais oficial
                    JOIN entregas_alertas envio
                      ON envio.sinal_id=oficial.id
                     AND envio.status='entregue'
                     AND envio.provedor='telegram'
                     AND envio.provedor_mensagem_id IS NOT NULL
                     AND (
                         envio.canal NOT LIKE '%:%'
                         OR (envio.canal LIKE '%:teste'
                             AND envio.canal NOT LIKE '%:teste:%')
                     )
                    WHERE oficial.partida_id=origem_sinal.partida_id
                      AND oficial.mercado=origem_sinal.mercado
                      AND oficial.id>origem_sinal.id
                      AND json_valid(oficial.features_json)
                      AND json_extract(
                            oficial.features_json,
                            '$.acompanhamento_odd_rapido.versao'
                          )=?
                      AND CAST(json_extract(
                            oficial.features_json,
                            '$.acompanhamento_odd_rapido.origem_sinal_id'
                          ) AS INTEGER)=origem_sinal.id
                      AND (
                          (
                              oficial.linha IS NULL
                              AND origem_sinal.linha IS NULL
                          )
                          OR (
                              oficial.mercado<>'proximo_gol'
                              AND ABS(
                                  CAST(oficial.linha AS REAL)
                                  - CAST(origem_sinal.linha AS REAL)
                              ) < 0.000001
                          )
                          OR (
                              oficial.mercado='proximo_gol'
                              AND CAST(oficial.linha AS TEXT)
                                  = CAST(origem_sinal.linha AS TEXT)
                          )
                      )
                )
                  AND NOT EXISTS (
                    SELECT 1 FROM entregas_alertas final
                    WHERE final.sinal_id=origem_sinal.id
                      AND final.canal=entrega.canal || ':monitoramento_final'
                )
            )
            , candidatos AS (
                SELECT aviso.origem_sinal_id, aviso.canal_aviso,
                       atual.id AS sinal_id, atual.partida_id,
                       atual.snapshot_id, atual.mercado, atual.linha,
                       atual.odd, atual.pontuacao_tecnica,
                       atual.probabilidade_calibrada, atual.regra_versao,
                       atual.regra_fingerprint, atual.motivos_json,
                       atual.features_json, atual.status AS sinal_status,
                       snapshot.coletado_em AS snapshot_em,
                       snapshot.placar AS placar_origem,
                       snapshot.status AS status_origem,
                       snapshot.texto_linha,
                       snapshot.estatisticas_json, snapshot.evolucao_json,
                       snapshot.confirmacao_api_json,
                       snapshot.estatisticas_api_json,
                       snapshot.contexto_api_json,
                       snapshot.qualidade_dados, snapshot.qualidade_json,
                       partida.packball_url, partida.mandante,
                       partida.visitante, partida.pais, partida.liga,
                       partida.api_fixture_id, partida.api_orientacao,
                       CASE
                         WHEN aviso.metodo_acompanhado IS NOT NULL
                          AND datetime(snapshot.coletado_em, '+' || CAST(
                            COALESCE(json_extract(atual.features_json,
                              '$.acompanhamento_metodo_gols.validade_tecnica_segundos'), 120)
                            AS TEXT) || ' seconds') < datetime('now', 'localtime')
                         THEN 0
                         WHEN ? IS NULL THEN 1
                         WHEN datetime(snapshot.coletado_em)>=datetime(?)
                         THEN 1 ELSE 0
                       END AS tecnica_recente,
                       (
                         SELECT MAX(observacao.consultado_em)
                         FROM observacoes_fontes_odds observacao
                         WHERE observacao.evidencia_referencia=
                               'acompanhamento_odd:'
                               || CAST(aviso.origem_sinal_id AS TEXT)
                           AND observacao.estado IN (
                               'oferta_monitorada',
                               'consulta_monitoramento'
                           )
                       ) AS ultima_consulta_api
                FROM avisos aviso
                JOIN sinais atual
                  ON atual.partida_id=aviso.partida_id
                 AND atual.mercado=aviso.mercado
                 AND (
                     (atual.linha IS NULL AND aviso.linha IS NULL)
                     OR (
                        atual.mercado<>'proximo_gol'
                        AND ABS(
                            CAST(atual.linha AS REAL)
                            - CAST(aviso.linha AS REAL)
                        ) < 0.000001
                     )
                     OR CAST(atual.linha AS TEXT)=CAST(aviso.linha AS TEXT)
                 )
                 AND atual.id=(
                     SELECT MAX(novo.id)
                     FROM sinais novo
                     WHERE novo.partida_id=aviso.partida_id
                       AND novo.mercado=aviso.mercado
                       AND novo.status='rejeitado'
                       AND json_valid(novo.features_json)
                       AND json_extract(novo.features_json,
                             '$.acompanhamento_metodo_gols.metodo') IS aviso.metodo_acompanhado
                       AND json_extract(
                             novo.features_json,
                             '$.acompanhamento_odd.elegivel_aviso'
                           )=1
                       AND (
                           (novo.linha IS NULL AND aviso.linha IS NULL)
                           OR (
                              novo.mercado<>'proximo_gol'
                              AND ABS(
                                  CAST(novo.linha AS REAL)
                                  - CAST(aviso.linha AS REAL)
                              ) < 0.000001
                           )
                           OR CAST(novo.linha AS TEXT)=CAST(aviso.linha AS TEXT)
                       )
                 )
                JOIN snapshots snapshot ON snapshot.id=atual.snapshot_id
                JOIN partidas partida ON partida.id=atual.partida_id
                WHERE {_sql_leitura_acompanhamento_vigente('atual')}
            )
            SELECT candidatos.*,
                   COUNT(*) OVER() AS fila_total,
                   SUM(tecnica_recente) OVER() AS fila_tecnica_recente_total,
                   SUM(CASE WHEN tecnica_recente=0 THEN 1 ELSE 0 END)
                       OVER() AS fila_tecnica_dormente_total,
                   SUM(CASE
                         WHEN tecnica_recente=1
                          AND ultima_consulta_api IS NULL THEN 1 ELSE 0
                       END) OVER() AS fila_recente_nunca_consultada
            FROM candidatos
            ORDER BY tecnica_recente DESC,
                     CASE WHEN ultima_consulta_api IS NULL THEN 0 ELSE 1 END,
                     datetime(ultima_consulta_api), sinal_id DESC
            LIMIT ?
            """,
            (
                VERSAO_MATERIALIZACAO_RAPIDA,
                snapshot_desde,
                snapshot_desde,
                min(max(int(limite), 1), 50),
            ),
        ).fetchall()

    def sinais_entregues_para_clv_pos_alerta(
        self, limite=10, *, agora=None,
    ):
        """Seleciona alertas com cotação congelada na janela de 2–10 min.

        Esta fila é independente da estratégia de aguardar odd. Ela existe
        somente para fotografar estado e, quando compatível, a mesma linha
        depois do envio, sem navegar no PackBall e sem criar nova entrada.
        """
        agora = normalizar_data(agora)
        mercados = sorted(MERCADOS_CLV_API_RAPIDA)
        marcadores = ",".join("?" for _ in mercados)
        limite = min(max(int(limite), 1), 50)
        linhas = self.conexao.execute(
            f"""
            WITH entregues AS (
                SELECT s.id AS sinal_id,
                       MIN(COALESCE(e.entregue_em,e.tentado_em)) AS entregue_em
                FROM sinais s
                JOIN entregas_alertas e ON e.sinal_id=s.id
                WHERE e.status='entregue'
                  AND e.provedor='telegram'
                  AND e.provedor_mensagem_id IS NOT NULL
                  AND e.canal NOT LIKE 'gateway:%'
                  AND INSTR(e.canal, ':resultado')=0
                  AND INSTR(e.canal, ':green_antecipado')=0
                  AND INSTR(e.canal, ':aguardar_odd')=0
                  AND INSTR(e.canal, ':cancelamento')=0
                  AND INSTR(e.canal, ':insuficiente')=0
                  AND INSTR(e.canal, ':monitoramento_final')=0
                  AND INSTR(e.canal, ':correcao')=0
                GROUP BY s.id
            )
            SELECT s.id AS sinal_id, s.id AS origem_sinal_id,
                   s.partida_id, s.snapshot_id, s.mercado, s.linha,
                       s.odd, s.criado_em, s.features_json,
                       entregue.entregue_em,
                       lower(trim(json_extract(
                         s.features_json, '$.fonte_odds'
                       ))) AS fonte_odds,
                       lower(trim(COALESCE(json_extract(
                         s.features_json, '$.bookmaker_odds'
                       ), ''))) AS bookmaker_odds,
                   snapshot.coletado_em AS snapshot_em,
                   snapshot.placar AS placar_origem,
                   snapshot.status AS status_origem,
                   partida.packball_url, partida.mandante,
                   partida.visitante, partida.pais, partida.liga,
                   partida.api_fixture_id, partida.api_orientacao
            FROM entregues entregue
            JOIN sinais s ON s.id=entregue.sinal_id
            JOIN snapshots snapshot ON snapshot.id=s.snapshot_id
            JOIN partidas partida ON partida.id=s.partida_id
            WHERE s.mercado IN ({marcadores})
              AND json_valid(s.features_json)
              AND json_extract(
                    s.features_json, '$.cotacao_entrada_clv_estado'
                  )='congelada_v1'
              AND (
                    (
                      lower(trim(json_extract(
                        s.features_json, '$.fonte_odds'
                      )))='betsapi'
                      AND lower(trim(json_extract(
                        s.features_json, '$.bookmaker_odds'
                      )))='bet365'
                    )
                    OR lower(trim(json_extract(
                      s.features_json, '$.fonte_odds'
                    )))='packball'
                  )
              AND partida.api_fixture_id IS NOT NULL
              AND datetime(entregue.entregue_em, '+' || ? || ' seconds')
                    <= datetime(?)
              AND datetime(entregue.entregue_em, '+' || ? || ' seconds')
                    >= datetime(?)
              AND NOT EXISTS (
                    SELECT 1 FROM observacoes_fontes_odds observacao
                    WHERE observacao.estado=?
                      AND observacao.evidencia_referencia=(
                            ? || CAST(s.id AS TEXT)
                      )
              )
            ORDER BY datetime(entregue.entregue_em), s.id
            """,
            (
                *mercados,
                CLV_HORIZONTE_MINIMO_SEGUNDOS, agora,
                CLV_HORIZONTE_MAXIMO_SEGUNDOS, agora,
                ESTADO_OBSERVACAO_CLV, "clv_pos_alerta:",
            ),
        ).fetchall()
        from avaliacao_clv_live import _cotacao_entrada_congelada

        elegiveis = []
        for linha in linhas:
            try:
                features = json.loads(linha["features_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                features = {}
            if not isinstance(
                _cotacao_entrada_congelada(features, dict(linha)), dict
            ):
                continue
            elegiveis.append(linha)
            if len(elegiveis) >= limite:
                break
        return elegiveis

    def registrar_estado_clv_pos_alerta(
        self,
        sinal_id,
        estado_jogo,
        *,
        observacao_oferta_id=None,
        consultado_em=None,
    ):
        """Congela estado/horário da fotografia CLV em registro imutável."""
        sinal_id = int(sinal_id)
        origem = self.conexao.execute(
            """
            SELECT s.partida_id, s.mercado, s.linha, s.odd, s.criado_em,
                   s.features_json,
                   p.packball_url, p.mandante, p.visitante,
                   p.api_fixture_id,
                   (
                       SELECT MIN(COALESCE(e.entregue_em,e.tentado_em))
                       FROM entregas_alertas e
                       WHERE e.sinal_id=s.id AND e.status='entregue'
                         AND e.provedor='telegram'
                         AND e.provedor_mensagem_id IS NOT NULL
                         AND e.canal NOT LIKE 'gateway:%'
                         AND INSTR(e.canal, ':resultado')=0
                         AND INSTR(e.canal, ':green_antecipado')=0
                         AND INSTR(e.canal, ':aguardar_odd')=0
                         AND INSTR(e.canal, ':cancelamento')=0
                         AND INSTR(e.canal, ':insuficiente')=0
                         AND INSTR(e.canal, ':monitoramento_final')=0
                         AND INSTR(e.canal, ':correcao')=0
                   ) AS entregue_em
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.id=?
            """,
            (sinal_id,),
        ).fetchone()
        if origem is None or not isinstance(estado_jogo, dict):
            return {"estado": "origem_ou_estado_invalido", "persistido": False}
        if origem["mercado"] not in MERCADOS_CLV_API_RAPIDA:
            return {"estado": "mercado_nao_suportado", "persistido": False}
        if not origem["entregue_em"]:
            return {"estado": "entrega_confirmada_ausente", "persistido": False}
        try:
            features = json.loads(origem["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        from avaliacao_clv_live import _cotacao_entrada_congelada
        if not isinstance(
            _cotacao_entrada_congelada(features, dict(origem)), dict
        ):
            return {
                "estado": "cotacao_entrada_clv_invalida",
                "persistido": False,
            }
        fonte_entrada = str(
            features.get("fonte_odds") or ""
        ).strip().casefold()
        bookmaker_entrada = str(
            features.get("bookmaker_odds") or ""
        ).strip().casefold()
        modo_coleta = modo_coleta_estado_clv(
            fonte_entrada, bookmaker_entrada
        )
        if modo_coleta is None:
            return {
                "estado": "fonte_entrada_estado_clv_nao_suportada",
                "persistido": False,
            }

        consultado_em = normalizar_data(consultado_em)
        try:
            consulta = datetime.fromisoformat(consultado_em)
            entrega = datetime.fromisoformat(str(origem["entregue_em"]))
            if consulta.tzinfo is not None and entrega.tzinfo is None:
                consulta = consulta.astimezone().replace(tzinfo=None)
            elif consulta.tzinfo is None and entrega.tzinfo is not None:
                entrega = entrega.astimezone().replace(tzinfo=None)
            idade = (consulta - entrega).total_seconds()
        except (TypeError, ValueError):
            return {"estado": "instante_clv_invalido", "persistido": False}
        if not (
            CLV_HORIZONTE_MINIMO_SEGUNDOS
            <= idade <= CLV_HORIZONTE_MAXIMO_SEGUNDOS
        ):
            return {
                "estado": "fora_horizonte_clv",
                "persistido": False,
                "idade_segundos": round(idade, 3),
            }

        fixture_id = estado_jogo.get("evento_externo_id")
        if fixture_id is None:
            fixture_id = estado_jogo.get("fixture_id")
        if str(fixture_id or "") != str(origem["api_fixture_id"] or ""):
            return {"estado": "fixture_clv_divergente", "persistido": False}
        placar = str(estado_jogo.get("placar") or "").strip()
        if re.fullmatch(r"\d+\s*-\s*\d+", placar) is None:
            return {"estado": "placar_clv_invalido", "persistido": False}
        status_codigo = str(
            estado_jogo.get("status_codigo") or ""
        ).strip().upper()
        if not status_codigo:
            return {"estado": "status_clv_invalido", "persistido": False}
        minuto = estado_jogo.get("minuto")
        try:
            minuto = float(minuto)
        except (TypeError, ValueError):
            minuto = None
        if minuto is not None and (not math.isfinite(minuto) or minuto < 0):
            return {"estado": "minuto_clv_invalido", "persistido": False}
        escanteios = normalizar_escanteios_estado(
            estado_jogo.get("escanteios")
        )
        if escanteios is False:
            return {
                "estado": "escanteios_clv_invalidos", "persistido": False,
            }

        referencia = referencia_clv(sinal_id)
        existente = self.conexao.execute(
            """
            SELECT id FROM observacoes_fontes_odds
            WHERE estado=? AND evidencia_referencia=?
            ORDER BY id LIMIT 1
            """,
            (ESTADO_OBSERVACAO_CLV, referencia),
        ).fetchone()
        if existente is not None:
            return {
                "estado": "ja_persistido",
                "persistido": False,
                "observacao_id": int(existente["id"]),
            }

        oferta_vinculada = None
        if observacao_oferta_id is not None:
            if modo_coleta != "estado_e_preco":
                return {
                    "estado": "oferta_clv_proibida_em_modo_somente_estado",
                    "persistido": False,
                }
            oferta_vinculada = self.conexao.execute(
                """
                SELECT id,partida_id,consultado_em,mercado,oferta_json,
                       evidencia_sha256,evidencia_referencia
                FROM observacoes_fontes_odds
                WHERE id=? AND estado='oferta_monitorada'
                """,
                (int(observacao_oferta_id),),
            ).fetchone()
            if (
                oferta_vinculada is None
                or int(oferta_vinculada["partida_id"]) != int(origem["partida_id"])
                or oferta_vinculada["evidencia_referencia"]
                    != f"acompanhamento_odd:{sinal_id}"
                or oferta_vinculada["mercado"] != origem["mercado"]
            ):
                return {"estado": "oferta_clv_divergente", "persistido": False}
            try:
                payload_oferta = json.loads(
                    oferta_vinculada["oferta_json"] or "{}"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                payload_oferta = {}
            if (
                hashlib.sha256(str(
                    oferta_vinculada["oferta_json"]
                ).encode("utf-8")).hexdigest()
                != str(oferta_vinculada["evidencia_sha256"] or "")
                or not linha_equivalente(
                    origem["mercado"], payload_oferta.get("linha"),
                    origem["linha"],
                )
                or str(payload_oferta.get("fonte") or "").casefold()
                    != "betsapi"
                or str(payload_oferta.get("bookmaker") or "").casefold()
                    != "bet365"
            ):
                return {"estado": "oferta_clv_integra_ausente", "persistido": False}

        payload = {
            "schema": VERSAO_EVIDENCIA_ESTADO_CLV,
            "sinal_id": sinal_id,
            "partida_id": int(origem["partida_id"]),
            "mercado": origem["mercado"],
            "linha": origem["linha"],
            "entregue_em": origem["entregue_em"],
            "consultado_em": consultado_em,
            "idade_apos_entrega_segundos": round(idade, 3),
            "fixture_id": int(origem["api_fixture_id"]),
            "placar": placar,
            "minuto": minuto,
            "status_codigo": status_codigo,
            "escanteios": escanteios,
            "fonte_entrada": fonte_entrada,
            "bookmaker_entrada": bookmaker_entrada or None,
            "modo_coleta": modo_coleta,
            "fonte_estado": "api_football",
            "oferta_observacao_id": (
                int(oferta_vinculada["id"])
                if oferta_vinculada is not None else None
            ),
            "oferta_exata_disponivel": oferta_vinculada is not None,
            "aplicacao_sinais": False,
            "telegram": False,
        }
        payload_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        evidencia_sha256 = hashlib.sha256(
            payload_json.encode("utf-8")
        ).hexdigest()
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id,fonte,consultado_em,estado,
                    evento_externo_id,mandante_observado,
                    visitante_observado,periodo,mercado,motivo,
                    oferta_json,url_origem,metodo_coleta,
                    evidencia_sha256,evidencia_referencia
                ) VALUES (?,?,?, ?,?,?,?,?,?,?, ?,?,?,?,?)
                """,
                (
                    origem["partida_id"], "api_football", consultado_em,
                    ESTADO_OBSERVACAO_CLV, str(origem["api_fixture_id"]),
                    origem["mandante"], origem["visitante"],
                    "HT" if origem["mercado"] == "gol_ht" else "FT",
                    origem["mercado"],
                    "cotacao_exata" if oferta_vinculada is not None
                    else "cotacao_exata_ausente",
                    payload_json, str(origem["packball_url"] or ""),
                    "api_rapida_clv_sem_packball", evidencia_sha256,
                    referencia,
                ),
            )
        return {
            "estado": "persistido",
            "persistido": True,
            "observacao_id": int(cursor.lastrowid),
            "oferta_exata": oferta_vinculada is not None,
            "idade_segundos": round(idade, 3),
            "aplicacao_sinais": False,
            "telegram": False,
        }

    def acompanhamento_odd_leitura_vigente(self, sinal_id):
        """Não autoriza preço novo apoiado em uma análise já substituída."""
        return self.conexao.execute(
            f"SELECT 1 FROM sinais tecnica WHERE tecnica.id=? AND {_sql_leitura_acompanhamento_vigente('tecnica')}",
            (int(sinal_id),),
        ).fetchone() is not None

    def registrar_consulta_acompanhamento_odd_api(
        self,
        sinal_id,
        *,
        consultado_em=None,
        motivo="selecionado_para_consulta",
    ):
        """Marca o rodizio da fila rapida sem criar uma linha por rodada."""
        origem = self.conexao.execute(
            """
            SELECT s.partida_id, s.mercado, s.linha,
                   p.packball_url, p.api_fixture_id
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.id=?
            """,
            (int(sinal_id),),
        ).fetchone()
        if origem is None:
            return {"estado": "origem_invalida", "persistido": False}
        consultado_em = normalizar_data(consultado_em)
        referencia = f"acompanhamento_odd:{int(sinal_id)}"
        payload = {
            "sinal_origem_id": int(sinal_id),
            "mercado": origem["mercado"],
            "linha": origem["linha"],
            "fixture_id": origem["api_fixture_id"],
            "motivo": str(motivo),
        }
        oferta_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        evidencia_sha256 = hashlib.sha256(
            oferta_json.encode("utf-8")
        ).hexdigest()
        with self.conexao:
            anterior = self.conexao.execute(
                """
                SELECT id FROM observacoes_fontes_odds
                WHERE evidencia_referencia=?
                  AND estado='consulta_monitoramento'
                ORDER BY id DESC LIMIT 1
                """,
                (referencia,),
            ).fetchone()
            if anterior is not None:
                self.conexao.execute(
                    """
                    UPDATE observacoes_fontes_odds
                    SET consultado_em=?, motivo=?, oferta_json=?,
                        evidencia_sha256=?
                    WHERE id=?
                    """,
                    (
                        consultado_em, str(motivo), oferta_json,
                        evidencia_sha256, int(anterior["id"]),
                    ),
                )
                return {
                    "estado": "consulta_atualizada",
                    "persistido": True,
                    "observacao_id": int(anterior["id"]),
                }
            cursor = self.conexao.execute(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado,
                    evento_externo_id, periodo, mercado, motivo,
                    oferta_json, url_origem, metodo_coleta,
                    evidencia_sha256, evidencia_referencia
                ) VALUES (?, 'agregador_odds_rapido', ?,
                          'consulta_monitoramento', ?, NULL, ?, ?, ?, ?,
                          'api_rapida_sem_packball', ?, ?)
                """,
                (
                    int(origem["partida_id"]), consultado_em,
                    (
                        str(origem["api_fixture_id"])
                        if origem["api_fixture_id"] is not None else None
                    ),
                    origem["mercado"], str(motivo), oferta_json,
                    origem["packball_url"], evidencia_sha256, referencia,
                ),
            )
        return {
            "estado": "consulta_registrada",
            "persistido": True,
            "observacao_id": int(cursor.lastrowid),
        }

    def registrar_observacao_acompanhamento_odd(
        self,
        sinal_id,
        oferta,
        estado_jogo,
        *,
        consultado_em=None,
        url_origem=None,
        motivo="cotacao_monitorada",
        odds=None,
    ):
        """Persiste cada leitura da odd rápida como evidência append-only.

        ``mudanca_material`` continua distinguindo repetição de alteração de
        preço para a telemetria, mas uma repetição também ganha linha própria.
        Assim o horário observado nunca é deslocado por uma consulta futura.
        """
        origem = self.conexao.execute(
            """
            SELECT s.partida_id, s.mercado, s.linha,
                   p.packball_url, p.mandante, p.visitante,
                   p.api_fixture_id
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.id=?
            """,
            (int(sinal_id),),
        ).fetchone()
        if origem is None or not isinstance(oferta, dict):
            return {"estado": "origem_ou_oferta_invalida", "persistido": False}
        try:
            odd = float(oferta.get("odd"))
        except (TypeError, ValueError):
            return {"estado": "odd_invalida", "persistido": False}
        if not math.isfinite(odd) or odd <= 1.0:
            return {"estado": "odd_invalida", "persistido": False}
        linha_origem = origem["linha"]
        linha_oferta = oferta.get("linha")
        if origem["mercado"] != "proximo_gol":
            try:
                linha_compativel = math.isclose(
                    float(linha_origem), float(linha_oferta), abs_tol=1e-9
                )
            except (TypeError, ValueError):
                linha_compativel = False
        else:
            linha_compativel = str(linha_origem) == str(linha_oferta)
        if not linha_compativel:
            return {"estado": "linha_incompativel", "persistido": False}

        contrato_mercado = validar_contrato_mercado_oferta(
            oferta,
            origem["mercado"],
            linha_origem,
            exigir_origem=True,
        )
        if contrato_mercado["valido"] is not True:
            return {
                "estado": "contrato_mercado_incompleto",
                "persistido": False,
                "motivo": contrato_mercado["motivo"],
            }
        estado_identidade = (
            dict(estado_jogo) if isinstance(estado_jogo, dict) else {}
        )
        estado_identidade.update({
            "mandante": origem["mandante"],
            "visitante": origem["visitante"],
        })
        identidade_evento = validar_identidade_evento_oferta(
            oferta, estado_identidade
        )
        if identidade_evento["valida"] is not True:
            return {
                "estado": "identidade_evento_invalida",
                "persistido": False,
                "motivo": identidade_evento["motivo"],
            }

        consultado_em = normalizar_data(consultado_em)
        try:
            instante_consulta = datetime.fromisoformat(consultado_em)
        except (TypeError, ValueError):
            return {
                "estado": "instante_consulta_invalido",
                "persistido": False,
            }
        proveniencia_temporal = validar_proveniencia_temporal_oferta(
            oferta, agora=instante_consulta
        )
        if proveniencia_temporal["valida"] is not True:
            return {
                "estado": "oferta_temporal_invalida",
                "persistido": False,
                "motivo": proveniencia_temporal["motivo"],
            }
        fonte = str(oferta.get("fonte") or "").strip()
        if not fonte:
            return {
                "estado": "fonte_odd_invalida",
                "persistido": False,
            }
        referencia = f"acompanhamento_odd:{int(sinal_id)}"
        identidade_normalizada = identidade_evento["identidade_evento"]
        vinculo_anterior = self.conexao.execute(
            """
            SELECT oferta_json
            FROM observacoes_fontes_odds
            WHERE evidencia_referencia=?
              AND estado='oferta_monitorada'
              AND lower(trim(fonte))=lower(trim(?))
              AND json_valid(oferta_json)
              AND json_extract(oferta_json, '$.schema') IN (?, ?)
            ORDER BY id
            LIMIT 1
            """,
            (
                referencia,
                fonte,
                VERSAO_EVIDENCIA_OFERTA_RAPIDA_V3,
                VERSAO_EVIDENCIA_OFERTA_RAPIDA,
            ),
        ).fetchone()
        if vinculo_anterior is not None:
            try:
                identidade_anterior = (
                    json.loads(vinculo_anterior["oferta_json"])[
                        "identidade_evento"
                    ]
                )
                vinculo_estavel = (
                    str(identidade_anterior.get("evento_externo_id") or "")
                    == str(
                        identidade_normalizada.get("evento_externo_id") or ""
                    )
                    and str(
                        identidade_anterior.get("orientacao") or ""
                    ).casefold()
                    == str(
                        identidade_normalizada.get("orientacao") or ""
                    ).casefold()
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                vinculo_estavel = False
            if not vinculo_estavel:
                return {
                    "estado": "identidade_evento_alterada",
                    "persistido": False,
                    "motivo": "evento_externo_trocado_na_mesma_fonte",
                }

        coerencia_curva = None
        if odds is not None:
            coerencia_curva = validar_coerencia_curva_candidato(
                odds,
                origem["mercado"],
                linha_origem,
                contrato_mercado["origem_mercado"],
                odd_selecionada=odd,
                odd_oposta_selecionada=contrato_mercado.get("odd_oposta"),
            )
            if coerencia_curva.get("valida") is not True:
                motivo_curva = str(
                    coerencia_curva.get("motivo")
                    or "coerencia_curva_odd_indeterminada"
                )
                if motivo_curva not in MOTIVOS_ANOMALIA_CURVA:
                    return {
                        "estado": motivo_curva,
                        "motivo": motivo_curva,
                        "persistido": False,
                        "autorizada": False,
                        "coerencia_curva_odds": coerencia_curva,
                    }
                payload_anomalia = {
                    "schema": VERSAO_EVIDENCIA_ANOMALIA,
                    "sinal_origem_id": int(sinal_id),
                    "mercado": origem["mercado"],
                    "linha": linha_oferta,
                    "odd": odd,
                    "fonte": fonte,
                    "bookmaker": oferta.get("bookmaker"),
                    "fonte_coletado_em": oferta.get("coletado_em"),
                    "idade_segundos": oferta.get("idade_segundos"),
                    "cache": oferta.get("cache"),
                    "identidade_evento": identidade_normalizada,
                    "origem_mercado": contrato_mercado["origem_mercado"],
                    "placar": (estado_jogo or {}).get("placar"),
                    "minuto": (estado_jogo or {}).get("minuto"),
                    "status": (estado_jogo or {}).get("status"),
                    "coerencia_curva_odds": coerencia_curva,
                }
                if contrato_mercado["tipo"] == "tres_vias":
                    payload_anomalia.update({
                        "selecao_mercado": contrato_mercado[
                            "selecao_mercado"
                        ],
                        "odds_mercado_sincronizadas": contrato_mercado[
                            "odds_mercado_sincronizadas"
                        ],
                        "mercado_odds_sincronizado": True,
                    })
                else:
                    payload_anomalia.update({
                        "odd_oposta": contrato_mercado["odd_oposta"],
                        "odd_par_sincronizado": True,
                    })
                anomalia_json = json.dumps(
                    payload_anomalia,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                anomalia_sha256 = hashlib.sha256(
                    anomalia_json.encode("utf-8")
                ).hexdigest()
                with self.conexao:
                    cursor = self.conexao.execute(
                        """
                        INSERT INTO observacoes_fontes_odds (
                            partida_id, fonte, consultado_em, estado,
                            evento_externo_id, mandante_observado,
                            visitante_observado, periodo, mercado,
                            motivo, oferta_json, url_origem, metodo_coleta,
                            evidencia_sha256, evidencia_referencia
                        ) VALUES (?, ?, ?, 'anomalia_curva_odd', ?, ?, ?, ?,
                                  ?, ?, ?, ?, 'api_rapida_sem_packball', ?, ?)
                        """,
                        (
                            origem["partida_id"], fonte, consultado_em,
                            identidade_normalizada["evento_externo_id"],
                            identidade_normalizada["mandante_normalizado"],
                            identidade_normalizada["visitante_normalizado"],
                            "HT" if origem["mercado"] == "gol_ht" else "FT",
                            origem["mercado"], motivo_curva, anomalia_json,
                            str(url_origem or origem["packball_url"] or ""),
                            anomalia_sha256, referencia,
                        ),
                    )
                return {
                    "estado": "anomalia_curva_odd",
                    "motivo": motivo_curva,
                    "persistido": True,
                    "autorizada": False,
                    "observacao_id": int(cursor.lastrowid),
                    "nova_linha": True,
                    "mudanca_material": False,
                    "ordem_temporal_valida": True,
                    "proveniencia_temporal": proveniencia_temporal,
                    "coerencia_curva_odds": coerencia_curva,
                }
        payload = {
            "schema": VERSAO_EVIDENCIA_OFERTA_RAPIDA,
            "sinal_origem_id": int(sinal_id),
            "mercado": origem["mercado"],
            "linha": linha_oferta,
            "odd": odd,
            "fonte": fonte,
            "bookmaker": oferta.get("bookmaker"),
            "fonte_coletado_em": oferta.get("coletado_em"),
            "idade_segundos": oferta.get("idade_segundos"),
            "cache": oferta.get("cache"),
            "identidade_evento": identidade_normalizada,
            "origem_mercado": contrato_mercado["origem_mercado"],
            "placar": (estado_jogo or {}).get("placar"),
            "minuto": (estado_jogo or {}).get("minuto"),
            "status": (estado_jogo or {}).get("status"),
        }
        if contrato_mercado["tipo"] == "tres_vias":
            payload.update({
                "selecao_mercado": contrato_mercado["selecao_mercado"],
                "odds_mercado_sincronizadas": contrato_mercado[
                    "odds_mercado_sincronizadas"
                ],
                "mercado_odds_sincronizado": True,
            })
        else:
            payload.update({
                "odd_oposta": contrato_mercado["odd_oposta"],
                "odd_par_sincronizado": True,
            })
        oferta_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        evidencia_sha256 = hashlib.sha256(
            oferta_json.encode("utf-8")
        ).hexdigest()
        with self.conexao:
            anterior = self.conexao.execute(
                """
                SELECT id, fonte, consultado_em, oferta_json
                FROM observacoes_fontes_odds
                WHERE evidencia_referencia=?
                  AND estado='oferta_monitorada'
                ORDER BY consultado_em DESC, id DESC
                LIMIT 1
                """,
                (referencia,),
            ).fetchone()
            mesma_observacao = False
            regressao_temporal = False
            if anterior is not None:
                try:
                    instante_atual = datetime.fromisoformat(consultado_em)
                    instante_anterior = datetime.fromisoformat(
                        str(anterior["consultado_em"])
                    )
                    regressao_temporal = instante_atual < instante_anterior
                except (TypeError, ValueError):
                    regressao_temporal = True
                try:
                    payload_anterior = json.loads(
                        anterior["oferta_json"] or "{}"
                    )
                    if origem["mercado"] == "proximo_gol":
                        odds_anteriores = payload_anterior.get(
                            "odds_mercado_sincronizadas"
                        ) or {}
                        odds_atuais = payload.get(
                            "odds_mercado_sincronizadas"
                        ) or {}
                        mesmo_contrato = all(
                            math.isclose(
                                float(odds_anteriores.get(chave)),
                                float(odds_atuais.get(chave)),
                                abs_tol=0.0005,
                            )
                            for chave in ("casa", "visitante", "sem_gol")
                        )
                    else:
                        mesmo_contrato = math.isclose(
                            float(payload_anterior.get("odd_oposta")),
                            float(payload.get("odd_oposta")),
                            abs_tol=0.0005,
                        )
                    mesma_observacao = (
                        str(anterior["fonte"] or "") == fonte
                        and str(payload_anterior.get("bookmaker") or "").casefold()
                        == str(payload.get("bookmaker") or "").casefold()
                        and str(
                            (payload_anterior.get("identidade_evento") or {}).get(
                                "evento_externo_id"
                            ) or ""
                        ) == str(
                            (payload.get("identidade_evento") or {}).get(
                                "evento_externo_id"
                            ) or ""
                        )
                        and str(
                            (payload_anterior.get("origem_mercado") or {}).get(
                                "identificador"
                            ) or ""
                        ) == str(
                            (payload.get("origem_mercado") or {}).get(
                                "identificador"
                            ) or ""
                        )
                        and math.isclose(
                            float(payload_anterior.get("odd")), odd,
                            abs_tol=0.0005,
                        )
                        and str(payload_anterior.get("placar") or "")
                        == str(payload.get("placar") or "")
                        and str(payload_anterior.get("linha"))
                        == str(payload.get("linha"))
                        and mesmo_contrato
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    mesma_observacao = False
            cursor = self.conexao.execute(
                """
                INSERT INTO observacoes_fontes_odds (
                    partida_id, fonte, consultado_em, estado,
                    evento_externo_id, mandante_observado,
                    visitante_observado, periodo, mercado,
                    motivo, oferta_json, url_origem, metodo_coleta,
                    evidencia_sha256, evidencia_referencia
                ) VALUES (?, ?, ?, 'oferta_monitorada', ?, ?, ?, ?, ?, ?,
                          ?, ?, 'api_rapida_sem_packball', ?, ?)
                """,
                (
                    origem["partida_id"], fonte, consultado_em,
                    identidade_normalizada["evento_externo_id"],
                    identidade_normalizada["mandante_normalizado"],
                    identidade_normalizada["visitante_normalizado"],
                    "HT" if origem["mercado"] == "gol_ht" else "FT",
                    origem["mercado"], str(motivo), oferta_json,
                    str(url_origem or origem["packball_url"] or ""),
                    evidencia_sha256, referencia,
                ),
            )
        return {
            "estado": (
                "nova_observacao_fora_de_ordem"
                if regressao_temporal else
                "nova_observacao_repetida"
                if mesma_observacao else "nova_observacao"
            ),
            "persistido": True,
            "observacao_id": int(cursor.lastrowid),
            "nova_linha": True,
            "mudanca_material": bool(
                not mesma_observacao and not regressao_temporal
            ),
            "ordem_temporal_valida": not regressao_temporal,
            "proveniencia_temporal": proveniencia_temporal,
        }

    def estado_acompanhamento_odd_api_ja_registrado(
        self, sinal_id, placar, status_codigo,
    ):
        """Evita repetir snapshots rápidos do mesmo estado confirmado."""
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais origem
            JOIN snapshots posterior
              ON posterior.partida_id=origem.partida_id
             AND posterior.id>origem.snapshot_id
            WHERE origem.id=?
              AND COALESCE(posterior.placar, '')=COALESCE(?, '')
              AND json_valid(posterior.contexto_api_json)
              AND json_extract(
                    posterior.contexto_api_json,
                    '$.acompanhamento_odd_api_rapido.estado_decisivo'
                  )=1
              AND json_valid(posterior.confirmacao_api_json)
              AND COALESCE(
                    json_extract(
                      posterior.confirmacao_api_json, '$.status.short'
                    ), ''
                  )=COALESCE(?, '')
            LIMIT 1
            """,
            (int(sinal_id), placar, str(status_codigo or "")),
        ).fetchone() is not None

    def historico_acompanhamento_odd(self, sinal_id):
        linha = self.conexao.execute(
            "SELECT partida_id, snapshot_id FROM sinais WHERE id=?",
            (int(sinal_id),),
        ).fetchone()
        if linha is None:
            return []
        leituras = self.conexao.execute(
            """
            SELECT id AS snapshot_id, coletado_em, placar, status,
                   qualidade_json
            FROM snapshots
            WHERE partida_id=? AND id>?
            ORDER BY id
            """,
            (linha["partida_id"], linha["snapshot_id"]),
        ).fetchall()
        resultado = []
        for leitura in leituras:
            try:
                qualidade = json.loads(leitura["qualidade_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                qualidade = {}
            item = dict(leitura)
            resultado_api_confiavel = (
                isinstance(qualidade, dict)
                and qualidade.get("versao") == "resultado-api-v1"
                and "api_football" in (qualidade.get("fontes") or [])
                and float(qualidade.get("pontuacao") or 0) >= 80.0
            )
            item["qualidade_apta"] = (
                isinstance(qualidade, dict)
                and qualidade.get("apto_para_liquidacao") is True
            ) or resultado_api_confiavel
            resultado.append(item)
        return resultado

    def ultima_odd_acompanhamento_odd(
        self, sinal_id, snapshot_limite_exclusivo,
    ):
        """Retorna a ultima odd comprovadamente anterior ao desfecho."""
        origem = self.conexao.execute(
            """
            SELECT partida_id, snapshot_id, mercado, linha, odd,
                   features_json
            FROM sinais WHERE id=?
            """,
            (int(sinal_id),),
        ).fetchone()
        if origem is None:
            return {"odd": None, "fonte": None}
        try:
            features = json.loads(origem["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        fonte_alvo = str((features or {}).get("fonte_odds") or "").strip()
        try:
            linha_alvo = float(origem["linha"])
        except (TypeError, ValueError):
            linha_alvo = origem["linha"]
        registros = self.conexao.execute(
            """
            SELECT sp.id AS snapshot_id, sp.coletado_em,
                   o.estrutura_json
            FROM snapshots sp
            JOIN odds o ON o.snapshot_id=sp.id
            WHERE sp.partida_id=? AND sp.id>=? AND sp.id<?
            ORDER BY sp.id DESC, o.id DESC
            """,
            (
                origem["partida_id"], origem["snapshot_id"],
                int(snapshot_limite_exclusivo),
            ),
        ).fetchall()
        candidatos = []
        for registro in registros:
            try:
                estrutura = json.loads(registro["estrutura_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            fonte = str(estrutura.get("fonte") or "").strip()
            odd = None
            if origem["mercado"] == "proximo_gol":
                odd = (estrutura.get("selecoes") or {}).get(
                    str(linha_alvo)
                )
            else:
                grupos = [estrutura.get("ofertas") or []]
                grupos.append(estrutura.get("ofertas_ht") or [])
                periodos = estrutura.get("ofertas_periodos") or {}
                if isinstance(periodos, dict):
                    grupos.extend(
                        valor for valor in periodos.values()
                        if isinstance(valor, list)
                    )
                for grupo in grupos:
                    for oferta in grupo:
                        if not isinstance(oferta, dict):
                            continue
                        try:
                            mesma_linha = math.isclose(
                                float(oferta.get("linha")),
                                float(linha_alvo),
                                abs_tol=1e-9,
                            )
                        except (TypeError, ValueError):
                            mesma_linha = False
                        if mesma_linha:
                            odd = oferta.get("over")
                            fonte = str(
                                oferta.get("fonte") or fonte
                            ).strip()
                            break
                    if odd is not None:
                        break
            try:
                odd = float(odd)
            except (TypeError, ValueError):
                continue
            item = {
                "odd": odd,
                "fonte": fonte or None,
                "snapshot_id": registro["snapshot_id"],
                "consultado_em": registro["coletado_em"],
                "metodo_coleta": "snapshot",
            }
            candidatos.append(item)

        limite = self.conexao.execute(
            "SELECT coletado_em FROM snapshots WHERE id=?",
            (int(snapshot_limite_exclusivo),),
        ).fetchone()
        if limite is not None:
            observacoes = self.conexao.execute(
                """
                SELECT id, fonte, consultado_em, oferta_json,
                       metodo_coleta
                FROM observacoes_fontes_odds
                WHERE partida_id=?
                  AND evidencia_referencia=?
                  AND estado='oferta_monitorada'
                  AND consultado_em<?
                ORDER BY consultado_em DESC, id DESC
                """,
                (
                    origem["partida_id"],
                    f"acompanhamento_odd:{int(sinal_id)}",
                    limite["coletado_em"],
                ),
            ).fetchall()
            for observacao in observacoes:
                try:
                    payload = json.loads(observacao["oferta_json"] or "{}")
                    odd = float(payload.get("odd"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if str(payload.get("mercado") or "") != origem["mercado"]:
                    continue
                if origem["mercado"] == "proximo_gol":
                    mesma_linha = str(payload.get("linha")) == str(linha_alvo)
                else:
                    try:
                        mesma_linha = math.isclose(
                            float(payload.get("linha")),
                            float(linha_alvo),
                            abs_tol=1e-9,
                        )
                    except (TypeError, ValueError):
                        mesma_linha = False
                if not mesma_linha:
                    continue
                candidatos.append({
                    "odd": odd,
                    "fonte": observacao["fonte"] or None,
                    "observacao_id": observacao["id"],
                    "consultado_em": observacao["consultado_em"],
                    "metodo_coleta": observacao["metodo_coleta"],
                    "minuto": payload.get("minuto"),
                    "placar": payload.get("placar"),
                })

        if candidatos:
            return max(
                candidatos,
                key=lambda item: (
                    str(item.get("consultado_em") or ""),
                    int(item.get("observacao_id") or 0),
                    int(item.get("snapshot_id") or 0),
                ),
            )
        return {
            "odd": float(origem["odd"])
            if origem["odd"] is not None else None,
            "fonte": fonte_alvo or None,
            "snapshot_id": origem["snapshot_id"],
            "consultado_em": None,
            "metodo_coleta": "sinal_origem",
        }

    def entrada_oficial_apos_acompanhamento(self, sinal_id, canal_base):
        return self.conexao.execute(
            """
            SELECT posterior.id AS sinal_id, posterior.odd,
                   resultado.resultado
            FROM sinais origem
            JOIN sinais posterior
              ON posterior.partida_id=origem.partida_id
             AND posterior.mercado=origem.mercado
             AND (
                 (
                     posterior.linha IS NULL
                     AND origem.linha IS NULL
                 )
                 OR (
                     posterior.mercado<>'proximo_gol'
                     AND ABS(
                         CAST(posterior.linha AS REAL)
                         - CAST(origem.linha AS REAL)
                     ) < 0.000001
                 )
                 OR (
                     posterior.mercado='proximo_gol'
                     AND CAST(posterior.linha AS TEXT)
                         = CAST(origem.linha AS TEXT)
                 )
             )
             AND posterior.snapshot_id>origem.snapshot_id
             AND posterior.status IN ('aprovado', 'simulacao')
             AND json_valid(posterior.features_json)
             AND json_extract(
                   posterior.features_json,
                   '$.acompanhamento_odd_rapido.versao'
                 )=?
             AND CAST(json_extract(
                   posterior.features_json,
                   '$.acompanhamento_odd_rapido.origem_sinal_id'
                 ) AS INTEGER)=origem.id
            JOIN entregas_alertas entrega
              ON entrega.sinal_id=posterior.id
             AND entrega.canal IN (?, ?)
             AND entrega.status='entregue'
             AND entrega.provedor='telegram'
             AND entrega.provedor_mensagem_id IS NOT NULL
            LEFT JOIN resultados_sinais resultado
              ON resultado.sinal_id=posterior.id
            WHERE origem.id=?
            ORDER BY posterior.snapshot_id, posterior.id
            LIMIT 1
            """,
            (
                VERSAO_MATERIALIZACAO_RAPIDA,
                str(canal_base),
                f"{canal_base}:teste",
                int(sinal_id),
            ),
        ).fetchone()

    def reservar_resultado_acompanhamento_odd(
        self, sinal_id, canal_origem, instante=None,
    ):
        canal_origem = str(canal_origem)
        canal = f"{canal_origem}:monitoramento_final"
        instante = normalizar_data(instante)
        token = secrets.token_urlsafe(24)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT OR IGNORE INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, erro, tentativas, reserva_token
                )
                SELECT s.id, ?, ?, NULL, 'enviando', NULL, 1, ?
                FROM sinais s
                WHERE s.id=?
                  AND EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=s.id AND origem.canal=?
                        AND origem.status='entregue'
                        AND origem.provedor='telegram'
                        AND origem.provedor_mensagem_id IS NOT NULL
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM entregas_alertas final
                      WHERE final.sinal_id=s.id AND final.canal=?
                  )
                """,
                (canal, instante, token, int(sinal_id), canal_origem, canal),
            )
        return token if cursor.rowcount == 1 else None

    def reserva_resultado_acompanhamento_odd_valida(
        self, sinal_id, canal_origem, reserva_token,
    ):
        canal_origem = str(canal_origem)
        canal = f"{canal_origem}:monitoramento_final"
        return self.conexao.execute(
            """
            SELECT 1 FROM entregas_alertas final
            WHERE final.sinal_id=? AND final.canal=?
              AND final.reserva_token=? AND final.status='enviando'
              AND EXISTS (
                  SELECT 1 FROM entregas_alertas origem
                  WHERE origem.sinal_id=final.sinal_id
                    AND origem.canal=? AND origem.status='entregue'
              )
            LIMIT 1
            """,
            (
                int(sinal_id), canal, str(reserva_token), canal_origem,
            ),
        ).fetchone() is not None

    def reservar_entrega_alerta(
        self, sinal_id, canal, instante=None, permitir_simulacao=False,
    ):
        """Adquire uma unica autorizacao persistida para fazer o POST.

        O INSERT ... SELECT e uma unica instrucao de escrita. O bloqueio de
        escritor do SQLite, somado a chave unica da tabela, impede que dois
        processos reservem o mesmo sinal antes de qualquer um deles receber a
        resposta do Telegram.
        """
        sinal_id = int(sinal_id)
        canal = str(canal)
        instante = normalizar_data(instante)
        token = secrets.token_urlsafe(24)
        with self.conexao:
            cursor = self.conexao.execute(
                f"""
                INSERT OR IGNORE INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, erro, tentativas, reserva_token
                )
                SELECT s.id, ?, ?, NULL, 'enviando', NULL, 1, ?
                FROM sinais s
                WHERE s.id=?
                  AND {_sql_vinculo_acompanhamento_vigente('s')}
                  AND (
                      s.status='aprovado'
                      OR (?=1 AND s.status='simulacao')
                  )
                  AND s.snapshot_id=(
                      SELECT sn.id
                      FROM snapshots sn
                      WHERE sn.partida_id=s.partida_id
                      ORDER BY datetime(sn.coletado_em) DESC, sn.id DESC
                      LIMIT 1
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM resultados_sinais r
                      WHERE r.sinal_id=s.id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM entregas_alertas e
                      WHERE e.sinal_id=s.id
                        AND e.status IN (
                            'enviando', 'tentando', 'incerto',
                            'erro', 'entregue'
                        )
                  )
                """,
                (
                    canal, instante, token, sinal_id,
                    1 if permitir_simulacao else 0,
                ),
            )
        return token if cursor.rowcount == 1 else None

    def reserva_entrega_valida(
        self, sinal_id, canal, reserva_token,
        permitir_simulacao=False,
    ):
        """Confirma que a reserva ainda autoriza exatamente esta entrega."""
        if not reserva_token:
            return False
        return self.conexao.execute(
            f"""
            SELECT 1
            FROM entregas_alertas e
            JOIN sinais s ON s.id=e.sinal_id
            WHERE e.sinal_id=? AND e.canal=? AND e.reserva_token=?
              AND {_sql_vinculo_acompanhamento_vigente('s')}
              AND e.status IN ('enviando', 'tentando')
              AND (
                  s.status='aprovado'
                  OR (?=1 AND s.status='simulacao')
              )
              AND s.snapshot_id=(
                  SELECT sn.id
                  FROM snapshots sn
                  WHERE sn.partida_id=s.partida_id
                  ORDER BY datetime(sn.coletado_em) DESC, sn.id DESC
                  LIMIT 1
              )
              AND NOT EXISTS (
                  SELECT 1 FROM resultados_sinais r
                  WHERE r.sinal_id=s.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas final
                  WHERE final.sinal_id=s.id AND final.status='entregue'
              )
            LIMIT 1
            """,
            (
                int(sinal_id), str(canal), str(reserva_token),
                1 if permitir_simulacao else 0,
            ),
        ).fetchone() is not None

    def possui_entrega_oficial_incerta(self, excluir_sinal_id=None):
        return self.conexao.execute(
            """
            SELECT 1
            FROM entregas_alertas e
            JOIN sinais s ON s.id=e.sinal_id
            WHERE e.status IN ('enviando', 'tentando', 'incerto')
              AND e.canal NOT LIKE '%:%'
              AND s.probabilidade_calibrada IS NOT NULL
              AND (? IS NULL OR e.sinal_id<>?)
              AND NOT EXISTS (
                  SELECT 1
                  FROM entregas_alertas final
                  WHERE final.sinal_id=e.sinal_id
                    AND final.canal=e.canal
                    AND final.status IN (
                        'entregue', 'erro', 'recuperado',
                        'cancelado', 'expirado'
                    )
                    AND datetime(final.tentado_em)
                        >= datetime(e.tentado_em)
              )
            LIMIT 1
            """,
            (excluir_sinal_id, excluir_sinal_id),
        ).fetchone() is not None

    def possui_entrega_incerta(self, sinal_id, canal):
        """Impede repetir uma entrega cuja confirmação ficou ambígua."""
        return self.conexao.execute(
            """
            SELECT 1
            FROM entregas_alertas pendente
            WHERE pendente.sinal_id=? AND pendente.canal=?
              AND pendente.status IN ('enviando', 'tentando', 'incerto')
              AND NOT EXISTS (
                  SELECT 1
                  FROM entregas_alertas final
                  WHERE final.sinal_id=pendente.sinal_id
                    AND final.canal=pendente.canal
                    AND final.status IN (
                        'entregue', 'erro', 'recuperado',
                        'cancelado', 'expirado'
                    )
                    AND datetime(final.tentado_em)
                        >= datetime(pendente.tentado_em)
              )
            LIMIT 1
            """,
            (int(sinal_id), str(canal)),
        ).fetchone() is not None

    def alerta_recente_mesmo_mercado(self, sinal_id, minutos=15):
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais atual
            JOIN sinais anterior
              ON anterior.partida_id=atual.partida_id
             AND anterior.mercado=atual.mercado
             AND anterior.id<>atual.id
            JOIN entregas_alertas e ON e.sinal_id=anterior.id
            WHERE atual.id=? AND e.status='entregue'
              AND e.canal NOT LIKE '%:%'
              AND datetime(e.entregue_em) >= datetime(
                    'now', 'localtime', ?
              )
            LIMIT 1
            """,
            (sinal_id, f"-{int(minutos)} minutes"),
        ).fetchone() is not None

    def total_alertas_entregues_hoje(self):
        return self.conexao.execute(
            """
            SELECT COUNT(*) FROM entregas_alertas
            WHERE status='entregue'
              AND canal NOT LIKE '%:%'
              AND date(entregue_em)=date('now', 'localtime')
            """
        ).fetchone()[0]

    def exposicao_alertas_hoje(self, unidades_por_sinal=1.0):
        quantidade = self.conexao.execute(
            """
            SELECT COUNT(*) FROM entregas_alertas
            WHERE status='entregue'
              AND canal NOT LIKE '%:%'
              AND date(entregue_em)=date('now', 'localtime')
            """
        ).fetchone()[0]
        return quantidade * float(unidades_por_sinal)

    def resumir_risco_alertas_oficiais(self, agora=None):
        """Resume resultados e risco de sinais oficiais entregues."""
        return resumir_risco_alertas_oficiais_conexao(
            self.conexao, agora
        )

    def resumir_placar_por_mercado(
        self, simulacoes=False, regra_versao=None, iniciado_em=None,
    ):
        """Separa green, red e pendente por tipo de entrada entregue."""
        filtro_canal = (
            "e.canal LIKE '%:teste'"
            if simulacoes
            else "e.canal NOT LIKE '%:%'"
        )
        filtros = [f"e.status='entregue'", filtro_canal]
        parametros = []
        if regra_versao is not None:
            filtros.append("s.regra_versao=?")
            parametros.append(regra_versao)
        if iniciado_em is not None:
            filtros.append("datetime(s.criado_em)>=datetime(?)")
            parametros.append(iniciado_em)
        linhas = self.conexao.execute(
            f"""
            SELECT s.mercado,
                   COUNT(DISTINCT CASE
                     WHEN r.resultado IN ('green', 'half_green')
                     THEN s.id END) AS greens,
                   COUNT(DISTINCT CASE
                     WHEN r.resultado IN ('red', 'half_red')
                     THEN s.id END) AS reds,
                   COUNT(DISTINCT CASE
                     WHEN r.sinal_id IS NULL THEN s.id END) AS pendentes
            FROM sinais s
            JOIN entregas_alertas e ON e.sinal_id=s.id
             AND {' AND '.join(filtros)}
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            GROUP BY s.mercado
            ORDER BY s.mercado
            """,
            tuple(parametros),
        ).fetchall()
        return {
            linha["mercado"]: {
                "greens": linha["greens"],
                "reds": linha["reds"],
                "pendentes": linha["pendentes"],
            }
            for linha in linhas
        }

    def total_alertas_teste_entregues_hoje(self, regra_versao=None):
        if regra_versao is None:
            return self.conexao.execute(
                """
                SELECT COUNT(*) FROM entregas_alertas
                WHERE status='entregue' AND canal LIKE '%:teste'
                  AND date(entregue_em)=date('now', 'localtime')
                """
            ).fetchone()[0]
        return self.conexao.execute(
            """
            SELECT COUNT(*)
            FROM entregas_alertas e
            JOIN sinais s ON s.id=e.sinal_id
            WHERE e.status='entregue' AND e.canal LIKE '%:teste'
              AND date(e.entregue_em)=date('now', 'localtime')
              AND s.regra_versao=?
            """,
            (regra_versao,),
        ).fetchone()[0]

    def alerta_teste_recente_na_partida(self, sinal_id, minutos=15):
        # Gols e escanteios têm canais e riscos independentes. O intervalo
        # protege duplicidade dentro da mesma família, sem fazer um sinal de
        # gol silenciar uma oportunidade de canto (ou vice-versa).
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais atual
            JOIN sinais anterior
              ON anterior.partida_id=atual.partida_id
             AND anterior.id<>atual.id
            JOIN entregas_alertas e ON e.sinal_id=anterior.id
            WHERE atual.id=? AND e.status='entregue'
              AND e.canal LIKE '%:teste'
              AND CASE
                    WHEN atual.mercado IN (
                      'proximo_escanteio', 'escanteios_ft_asiatico',
                      'escanteios_1t', 'escanteios_2t'
                    ) THEN 'escanteios' ELSE 'gols'
                  END = CASE
                    WHEN anterior.mercado IN (
                      'proximo_escanteio', 'escanteios_ft_asiatico',
                      'escanteios_1t', 'escanteios_2t'
                    ) THEN 'escanteios' ELSE 'gols'
                  END
              AND datetime(e.entregue_em) >= datetime(
                    'now', 'localtime', ?
              )
            LIMIT 1
            """,
            (sinal_id, f"-{int(minutos)} minutes"),
        ).fetchone() is not None

    def alerta_teste_ja_entregue_no_grupo_independente(self, sinal_id):
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais atual
            JOIN sinais anterior
              ON anterior.partida_id=atual.partida_id
             AND anterior.mercado=atual.mercado
             AND anterior.regra_versao=atual.regra_versao
             AND anterior.id<>atual.id
            JOIN entregas_alertas e ON e.sinal_id=anterior.id
            WHERE atual.id=? AND e.status='entregue'
              AND e.canal LIKE '%:teste'
            LIMIT 1
            """,
            (sinal_id,),
        ).fetchone() is not None

    def sinal_e_primeira_decisao_independente(self, sinal_id):
        """Garante a mesma unidade partida/mercado/regra da calibração."""
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais atual
            WHERE atual.id=?
              AND atual.status IN ('aprovado', 'duplicado', 'simulacao')
              AND NOT EXISTS (
                  SELECT 1 FROM sinais anterior
                  WHERE anterior.partida_id=atual.partida_id
                    AND anterior.mercado=atual.mercado
                    AND anterior.regra_versao=atual.regra_versao
                    AND anterior.id<atual.id
                    AND anterior.status IN (
                        'aprovado', 'duplicado', 'simulacao'
                    )
              )
            LIMIT 1
            """,
            (sinal_id,),
        ).fetchone() is not None

    def existe_exposicao_gol_aberta_na_partida(self, sinal_id):
        """Veda exposições simultâneas, sem transportar HT para o segundo tempo.

        Um mercado HT termina no intervalo. Portanto, uma eventual demora para
        persistir seu Green/Red não pode bloquear uma nova decisão independente
        de FT ou próximo gol já identificada explicitamente no segundo tempo.
        """
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais atual
            JOIN sinais anterior
              ON anterior.partida_id=atual.partida_id
             AND anterior.id<>atual.id
             AND anterior.mercado IN ('gol_ht', 'gol_ft', 'proximo_gol')
            JOIN entregas_alertas e
              ON e.sinal_id=anterior.id AND e.status='entregue'
             AND e.canal NOT LIKE '%:resultado'
             AND e.canal NOT LIKE '%:cancelamento'
             AND e.canal NOT LIKE '%:aguardar_odd'
            LEFT JOIN resultados_sinais r ON r.sinal_id=anterior.id
            WHERE atual.id=?
              AND atual.mercado IN ('gol_ht', 'gol_ft', 'proximo_gol')
              AND r.sinal_id IS NULL
              AND NOT (
                  anterior.mercado='gol_ht'
                  AND atual.mercado IN ('gol_ft', 'proximo_gol')
                  AND json_extract(
                        atual.features_json, '$.periodo'
                      )='segundo_tempo'
              )
            LIMIT 1
            """,
            (int(sinal_id),),
        ).fetchone() is not None

    def obter_tendencia_ht_red_para_2t(
        self, packball_url, versao_experimento
    ):
        """Localiza uma tendência HT entregue em teste e encerrada em red."""
        partida = self.conexao.execute(
            "SELECT id FROM partidas WHERE packball_url=?",
            (packball_url,),
        ).fetchone()
        if partida is None:
            return {"identificada": False, "ja_registrado": False}
        partida_id = int(partida[0])
        ja_registrado = self.conexao.execute(
            """
            SELECT 1 FROM sinais
            WHERE partida_id=? AND mercado='gol_ft'
              AND json_extract(
                    features_json, '$.exploracao_sombra.versao'
                  )=?
            LIMIT 1
            """,
            (partida_id, versao_experimento),
        ).fetchone() is not None
        origem = self.conexao.execute(
            """
            SELECT s.id, s.regra_versao, s.pontuacao_tecnica,
                   s.odd, s.features_json, r.resultado,
                   snap.placar AS placar_entrada
            FROM sinais s
            JOIN snapshots snap ON snap.id=s.snapshot_id
            JOIN resultados_sinais r
              ON r.sinal_id=s.id AND r.resultado='red'
            WHERE s.partida_id=? AND s.mercado='gol_ht'
              AND EXISTS (
                  SELECT 1 FROM entregas_alertas e
                  WHERE e.sinal_id=s.id AND e.status='entregue'
                    AND e.canal LIKE '%:teste'
                    AND e.canal NOT LIKE '%:resultado'
              )
            ORDER BY s.id DESC
            LIMIT 1
            """,
            (partida_id,),
        ).fetchone()
        if origem is None:
            return {
                "identificada": False,
                "ja_registrado": ja_registrado,
                "partida_id": partida_id,
            }
        try:
            features = json.loads(origem["features_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            features = {}
        return {
            "identificada": origem["placar_entrada"] == "0-0",
            "ja_registrado": ja_registrado,
            "partida_id": partida_id,
            "sinal_id": int(origem["id"]),
            "regra_versao": origem["regra_versao"],
            "pontuacao_tecnica": origem["pontuacao_tecnica"],
            "odd_ht": origem["odd"],
            "resultado": origem["resultado"],
            "placar_entrada": origem["placar_entrada"],
            "entrega_teste": True,
            "features_origem": features,
        }

    def sinal_e_primeira_decisao_exploracao(
        self, sinal_id, versao_experimento
    ):
        """Deduplica um braço sombra sem confundi-lo com braços paralelos."""
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais atual
            WHERE atual.id=?
              AND atual.status='simulacao'
              AND json_extract(
                    atual.features_json,
                    '$.exploracao_sombra.versao'
                  )=?
              AND NOT EXISTS (
                  SELECT 1 FROM sinais anterior
                  WHERE anterior.partida_id=atual.partida_id
                    AND anterior.mercado=atual.mercado
                    AND anterior.id<atual.id
                    AND anterior.status='simulacao'
                    AND json_extract(
                          anterior.features_json,
                          '$.exploracao_sombra.versao'
                        )=?
              )
            LIMIT 1
            """,
            (sinal_id, versao_experimento, versao_experimento),
        ).fetchone() is not None

    def alerta_oficial_ja_entregue_no_grupo_independente(self, sinal_id):
        return self.conexao.execute(
            """
            SELECT 1
            FROM sinais atual
            JOIN sinais anterior
              ON anterior.partida_id=atual.partida_id
             AND anterior.mercado=atual.mercado
             AND anterior.regra_versao=atual.regra_versao
             AND anterior.id<>atual.id
            JOIN entregas_alertas e ON e.sinal_id=anterior.id
            WHERE atual.id=? AND e.status='entregue'
              AND e.canal NOT LIKE '%:%'
            LIMIT 1
            """,
            (sinal_id,),
        ).fetchone() is not None

    def sinais_entregues_pendentes(self, packball_url):
        return self.conexao.execute(
            """
            SELECT DISTINCT s.id, s.mercado, e.canal,
                   e.provedor_mensagem_id AS mensagem_id_origem
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            JOIN entregas_alertas e
              ON e.sinal_id=s.id AND e.status='entregue'
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE p.packball_url=? AND r.sinal_id IS NULL
              AND e.canal NOT LIKE '%:%'
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas aviso
                  WHERE aviso.sinal_id=s.id
                    AND aviso.canal=e.canal || ':cancelamento'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas green
                  WHERE green.sinal_id=s.id
                    AND green.canal=e.canal || ':green_antecipado'
                    AND green.status='entregue'
              )
            """,
            (packball_url,),
        ).fetchall()

    def sinais_entregues_pendentes_green_antecipado(self, limite=50):
        """Lista mensagens que ainda podem receber um GREEN antecipado."""
        return self.conexao.execute(
            """
            SELECT DISTINCT s.id AS sinal_id, s.mercado, s.linha, s.odd,
                   s.pontuacao_tecnica, s.probabilidade_calibrada,
                   s.regra_versao, s.regra_fingerprint,
                   s.motivos_json, s.features_json,
                   s.status AS status_sinal,
                   p.mandante, p.visitante, p.liga,
                   inicial.status AS minuto_entrada,
                   inicial.placar AS placar_entrada,
                   inicial.qualidade_dados,
                   origem.canal AS canal_origem,
                   origem.provedor_mensagem_id AS mensagem_id_origem
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            JOIN snapshots inicial ON inicial.id=s.snapshot_id
            JOIN entregas_alertas origem
              ON origem.sinal_id=s.id AND origem.status='entregue'
             AND origem.provedor='telegram'
             AND origem.provedor_mensagem_id IS NOT NULL
             AND (
                  origem.canal NOT LIKE '%:%'
                  OR (
                      origem.canal LIKE '%:teste'
                      AND origem.canal NOT LIKE '%:teste:%'
                  )
             )
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE r.sinal_id IS NULL
              AND s.status IN ('aprovado', 'simulacao')
              AND EXISTS (
                  SELECT 1 FROM snapshots atual
                  WHERE atual.partida_id=s.partida_id
                    AND atual.id>s.snapshot_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas aviso
                  WHERE aviso.sinal_id=s.id
                    AND aviso.canal=origem.canal || ':green_antecipado'
                    AND aviso.status='entregue'
              )
            ORDER BY s.id
            LIMIT ?
            """,
            (int(limite),),
        ).fetchall()

    def reservar_notificacao_green_antecipado(
        self, sinal_id, canal_origem, instante=None, espera_minutos=2,
        max_tentativas=5,
    ):
        """Reserva uma edição idempotente sem liquidar o resultado oficial."""
        sinal_id = int(sinal_id)
        canal_origem = str(canal_origem)
        canal = f"{canal_origem}:green_antecipado"
        instante = normalizar_data(instante)
        token = secrets.token_urlsafe(24)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT OR IGNORE INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, erro, tentativas, reserva_token
                )
                SELECT s.id, ?, ?, NULL, 'enviando', NULL, 1, ?
                FROM sinais s
                WHERE s.id=?
                  AND s.status IN ('aprovado', 'simulacao')
                  AND EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=s.id AND origem.canal=?
                        AND origem.status='entregue'
                        AND origem.provedor='telegram'
                        AND origem.provedor_mensagem_id IS NOT NULL
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM resultados_sinais r
                      WHERE r.sinal_id=s.id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM entregas_alertas aviso
                      WHERE aviso.sinal_id=s.id AND aviso.canal=?
                  )
                """,
                (canal, instante, token, sinal_id, canal_origem, canal),
            )
            if cursor.rowcount == 1:
                return token
            cursor = self.conexao.execute(
                """
                UPDATE entregas_alertas
                SET status='tentando', tentado_em=?,
                    tentativas=tentativas+1, reserva_token=?, erro=NULL
                WHERE sinal_id=? AND canal=?
                  AND status IN ('enviando', 'tentando', 'incerto')
                  AND tentativas<?
                  AND datetime(tentado_em) <= datetime(
                      'now', 'localtime', ?
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM resultados_sinais r
                      WHERE r.sinal_id=entregas_alertas.sinal_id
                  )
                """,
                (
                    instante, token, sinal_id, canal, int(max_tentativas),
                    f"-{int(espera_minutos)} minutes",
                ),
            )
        return token if cursor.rowcount == 1 else None

    def reserva_notificacao_green_antecipado_valida(
        self, sinal_id, canal_origem, reserva_token,
    ):
        if not reserva_token:
            return False
        canal_origem = str(canal_origem)
        canal = f"{canal_origem}:green_antecipado"
        return self.conexao.execute(
            """
            SELECT 1
            FROM entregas_alertas aviso
            WHERE aviso.sinal_id=? AND aviso.canal=?
              AND aviso.reserva_token=?
              AND aviso.status IN ('enviando', 'tentando')
              AND EXISTS (
                  SELECT 1 FROM entregas_alertas origem
                  WHERE origem.sinal_id=aviso.sinal_id
                    AND origem.canal=? AND origem.status='entregue'
                    AND origem.provedor='telegram'
                    AND origem.provedor_mensagem_id IS NOT NULL
              )
              AND NOT EXISTS (
                  SELECT 1 FROM resultados_sinais r
                  WHERE r.sinal_id=aviso.sinal_id
              )
            LIMIT 1
            """,
            (int(sinal_id), canal, str(reserva_token), canal_origem),
        ).fetchone() is not None

    def registrar_entrega_alerta(
        self, sinal_id, canal, status, erro=None, instante=None,
        provedor=None, provedor_destino_id=None,
        provedor_mensagem_id=None, confirmacao=None,
    ):
        instante = normalizar_data(instante)
        entregue_em = instante if status == "entregue" else None
        confirmacao_json = (
            json.dumps(
                confirmacao,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if confirmacao is not None else None
        )
        with self.conexao:
            self.conexao.execute(
                """
                INSERT INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, erro, tentativas, provedor,
                    provedor_destino_id, provedor_mensagem_id,
                    confirmacao_json
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(sinal_id, canal, status) DO UPDATE SET
                    tentado_em=CASE
                        WHEN entregas_alertas.status='entregue'
                        THEN entregas_alertas.tentado_em
                        ELSE excluded.tentado_em
                    END,
                    entregue_em=COALESCE(
                        entregas_alertas.entregue_em,
                        excluded.entregue_em
                    ),
                    erro=excluded.erro,
                    tentativas=entregas_alertas.tentativas + 1,
                    provedor=COALESCE(
                        entregas_alertas.provedor, excluded.provedor
                    ),
                    provedor_destino_id=COALESCE(
                        entregas_alertas.provedor_destino_id,
                        excluded.provedor_destino_id
                    ),
                    provedor_mensagem_id=COALESCE(
                        entregas_alertas.provedor_mensagem_id,
                        excluded.provedor_mensagem_id
                    ),
                    confirmacao_json=COALESCE(
                        entregas_alertas.confirmacao_json,
                        excluded.confirmacao_json
                    )
                """,
                (
                    sinal_id,
                    canal,
                    instante,
                    entregue_em,
                    status,
                    erro,
                    provedor,
                    (
                        str(provedor_destino_id)
                        if provedor_destino_id is not None else None
                    ),
                    (
                        str(provedor_mensagem_id)
                        if provedor_mensagem_id is not None else None
                    ),
                    confirmacao_json,
                ),
            )

    @staticmethod
    def _identidade_resultado_notificacao(resultado):
        resultado = dict(resultado)
        return (
            resultado.get("encerrado_em"),
            resultado.get("resultado"),
            resultado.get("retorno_unidades"),
            resultado.get("snapshot_id_liquidacao"),
            resultado.get("fonte_resultado"),
        )

    def reservar_notificacao_resultado(
        self, sinal_id, canal_origem, resultado, instante=None,
    ):
        """Reserva, uma unica vez, o aviso do resultado ja persistido."""
        sinal_id = int(sinal_id)
        canal_origem = str(canal_origem)
        canal = f"{canal_origem}:resultado"
        instante = normalizar_data(instante)
        token = secrets.token_urlsafe(24)
        identidade = self._identidade_resultado_notificacao(resultado)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT OR IGNORE INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, erro, tentativas, reserva_token
                )
                SELECT s.id, ?, ?, NULL, 'enviando', NULL, 1, ?
                FROM sinais s
                JOIN resultados_sinais r ON r.sinal_id=s.id
                WHERE s.id=?
                  AND r.encerrado_em IS ?
                  AND r.resultado IS ?
                  AND r.retorno_unidades IS ?
                  AND r.snapshot_id_liquidacao IS ?
                  AND r.fonte_resultado IS ?
                  AND EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=s.id AND origem.canal=?
                        AND origem.status='entregue'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM entregas_alertas aviso
                      WHERE aviso.sinal_id=s.id AND aviso.canal=?
                  )
                """,
                (
                    canal, instante, token, sinal_id,
                    *identidade, canal_origem, canal,
                ),
            )
        return token if cursor.rowcount == 1 else None

    def reserva_notificacao_resultado_valida(
        self, sinal_id, canal_origem, reserva_token, resultado,
    ):
        """Reconfere o claim e a identidade exata do resultado pre-POST."""
        if not reserva_token:
            return False
        canal_origem = str(canal_origem)
        canal = f"{canal_origem}:resultado"
        identidade = self._identidade_resultado_notificacao(resultado)
        return self.conexao.execute(
            """
            SELECT 1
            FROM entregas_alertas aviso
            JOIN resultados_sinais r ON r.sinal_id=aviso.sinal_id
            WHERE aviso.sinal_id=? AND aviso.canal=?
              AND aviso.reserva_token=?
              AND aviso.status IN ('enviando', 'tentando')
              AND r.encerrado_em IS ?
              AND r.resultado IS ?
              AND r.retorno_unidades IS ?
              AND r.snapshot_id_liquidacao IS ?
              AND r.fonte_resultado IS ?
              AND EXISTS (
                  SELECT 1 FROM entregas_alertas origem
                  WHERE origem.sinal_id=aviso.sinal_id
                    AND origem.canal=? AND origem.status='entregue'
              )
            LIMIT 1
            """,
            (
                int(sinal_id), canal, str(reserva_token),
                *identidade, canal_origem,
            ),
        ).fetchone() is not None

    def reservar_notificacao_cancelamento(
        self, sinal_id, canal_origem, instante=None,
    ):
        """Reserva o cancelamento somente enquanto o sinal esta pendente."""
        sinal_id = int(sinal_id)
        canal_origem = str(canal_origem)
        canal = f"{canal_origem}:cancelamento"
        instante = normalizar_data(instante)
        token = secrets.token_urlsafe(24)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT OR IGNORE INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, erro, tentativas, reserva_token
                )
                SELECT s.id, ?, ?, NULL, 'enviando', NULL, 1, ?
                FROM sinais s
                WHERE s.id=?
                  AND EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=s.id AND origem.canal=?
                        AND origem.status='entregue'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM resultados_sinais r
                      WHERE r.sinal_id=s.id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM entregas_alertas aviso
                      WHERE aviso.sinal_id=s.id AND aviso.canal=?
                  )
                """,
                (canal, instante, token, sinal_id, canal_origem, canal),
            )
        return token if cursor.rowcount == 1 else None

    def reserva_notificacao_cancelamento_valida(
        self, sinal_id, canal_origem, reserva_token,
    ):
        """Reconfere o claim e que o sinal continua sem resultado pre-POST."""
        if not reserva_token:
            return False
        canal_origem = str(canal_origem)
        canal = f"{canal_origem}:cancelamento"
        return self.conexao.execute(
            """
            SELECT 1
            FROM entregas_alertas aviso
            WHERE aviso.sinal_id=? AND aviso.canal=?
              AND aviso.reserva_token=? AND aviso.status='enviando'
              AND EXISTS (
                  SELECT 1 FROM entregas_alertas origem
                  WHERE origem.sinal_id=aviso.sinal_id
                    AND origem.canal=? AND origem.status='entregue'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM resultados_sinais r
                  WHERE r.sinal_id=aviso.sinal_id
              )
            LIMIT 1
            """,
            (int(sinal_id), canal, str(reserva_token), canal_origem),
        ).fetchone() is not None

    @staticmethod
    def canal_notificacao_correcao(canal_origem, revisao_id):
        return f"{str(canal_origem)}:correcao:{int(revisao_id)}"

    def reservar_notificacao_correcao(
        self, revisao_id, sinal_id, canal_origem, instante=None,
    ):
        """Reserva atomicamente a notificacao de uma revisao pendente."""
        revisao_id = int(revisao_id)
        sinal_id = int(sinal_id)
        canal_origem = str(canal_origem)
        canal = self.canal_notificacao_correcao(
            canal_origem, revisao_id
        )
        instante = normalizar_data(instante)
        token = secrets.token_urlsafe(24)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT OR IGNORE INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, erro, tentativas, reserva_token
                )
                SELECT s.id, ?, ?, NULL, 'enviando', NULL, 1, ?
                FROM sinais s
                WHERE s.id=?
                  AND EXISTS (
                      SELECT 1 FROM revisoes_resultados rev
                      WHERE rev.id=? AND rev.sinal_id=s.id
                        AND rev.notificacao_status='pendente'
                  )
                  AND EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=s.id AND origem.canal=?
                        AND origem.status='entregue'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM entregas_alertas aviso
                      WHERE aviso.sinal_id=s.id AND aviso.canal=?
                  )
                """,
                (
                    canal, instante, token, sinal_id, revisao_id,
                    canal_origem, canal,
                ),
            )
        return token if cursor.rowcount == 1 else None

    def reserva_notificacao_correcao_valida(
        self, revisao_id, sinal_id, canal_origem, reserva_token,
    ):
        """Reconfere claim, revisao e canal de origem imediatamente pre-POST."""
        if not reserva_token:
            return False
        revisao_id = int(revisao_id)
        sinal_id = int(sinal_id)
        canal_origem = str(canal_origem)
        canal = self.canal_notificacao_correcao(
            canal_origem, revisao_id
        )
        return self.conexao.execute(
            """
            SELECT 1
            FROM entregas_alertas aviso
            WHERE aviso.sinal_id=? AND aviso.canal=?
              AND aviso.reserva_token=? AND aviso.status='enviando'
              AND EXISTS (
                  SELECT 1 FROM revisoes_resultados rev
                  WHERE rev.id=? AND rev.sinal_id=aviso.sinal_id
                    AND rev.notificacao_status='pendente'
              )
              AND EXISTS (
                  SELECT 1 FROM entregas_alertas origem
                  WHERE origem.sinal_id=aviso.sinal_id
                    AND origem.canal=? AND origem.status='entregue'
              )
            LIMIT 1
            """,
            (
                sinal_id, canal, str(reserva_token), revisao_id,
                canal_origem,
            ),
        ).fetchone() is not None

    @staticmethod
    def _confirmacao_json(confirmacao):
        if confirmacao is None:
            return None
        return json.dumps(
            confirmacao,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def finalizar_notificacao_alerta(
        self, sinal_id, canal, reserva_token, status, erro=None,
        instante=None, provedor=None, provedor_destino_id=None,
        provedor_mensagem_id=None, confirmacao=None,
    ):
        """Finaliza em lugar o claim; token alheio nunca pode conclui-lo."""
        if status not in ("entregue", "incerto", "cancelado"):
            raise ValueError("Status final de notificacao invalido.")
        instante = normalizar_data(instante)
        entregue_em = instante if status == "entregue" else None
        confirmacao_json = self._confirmacao_json(confirmacao)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE entregas_alertas
                SET status=?, erro=?, entregue_em=?,
                    provedor=?, provedor_destino_id=?,
                    provedor_mensagem_id=?, confirmacao_json=?
                WHERE sinal_id=? AND canal=? AND reserva_token=?
                  AND status IN ('enviando', 'tentando')
                """,
                (
                    status, erro, entregue_em, provedor,
                    (
                        str(provedor_destino_id)
                        if provedor_destino_id is not None else None
                    ),
                    (
                        str(provedor_mensagem_id)
                        if provedor_mensagem_id is not None else None
                    ),
                    confirmacao_json, int(sinal_id), str(canal),
                    str(reserva_token),
                ),
            )
        return cursor.rowcount == 1

    def finalizar_notificacao_correcao(
        self, revisao_id, sinal_id, canal_origem, reserva_token, status,
        erro=None, instante=None, provedor=None, provedor_destino_id=None,
        provedor_mensagem_id=None, confirmacao=None,
    ):
        """Finaliza claim e revisao na mesma transacao apos o POST."""
        if status not in ("entregue", "incerto", "cancelado"):
            raise ValueError("Status final de correcao invalido.")
        revisao_id = int(revisao_id)
        sinal_id = int(sinal_id)
        canal = self.canal_notificacao_correcao(
            canal_origem, revisao_id
        )
        instante = normalizar_data(instante)
        entregue_em = instante if status == "entregue" else None
        status_claim = "controle_entregue" if status == "entregue" else status
        confirmacao_json = self._confirmacao_json(confirmacao)
        try:
            with self.conexao:
                claim = self.conexao.execute(
                    """
                    UPDATE entregas_alertas
                    SET status=?, erro=?, entregue_em=?
                    WHERE sinal_id=? AND canal=? AND reserva_token=?
                      AND status='enviando'
                    """,
                    (
                        status_claim, erro, entregue_em, sinal_id, canal,
                        str(reserva_token),
                    ),
                )
                if claim.rowcount != 1:
                    return False
                revisao = self.conexao.execute(
                    """
                    UPDATE revisoes_resultados
                    SET notificacao_status=?, notificacao_erro=?,
                        notificacao_provedor=COALESCE(
                            notificacao_provedor, ?
                        ),
                        notificacao_destino_id=COALESCE(
                            notificacao_destino_id, ?
                        ),
                        notificacao_mensagem_id=COALESCE(
                            notificacao_mensagem_id, ?
                        ),
                        notificacao_confirmacao_json=COALESCE(
                            notificacao_confirmacao_json, ?
                        )
                    WHERE id=? AND sinal_id=?
                      AND notificacao_status='pendente'
                    """,
                    (
                        status, erro, provedor,
                        (
                            str(provedor_destino_id)
                            if provedor_destino_id is not None else None
                        ),
                        (
                            str(provedor_mensagem_id)
                            if provedor_mensagem_id is not None else None
                        ),
                        confirmacao_json, revisao_id, sinal_id,
                    ),
                )
                if revisao.rowcount != 1:
                    raise _ReservaNotificacaoInvalida()
        except _ReservaNotificacaoInvalida:
            return False
        return True

    def resultados_simulacoes_nao_notificados(self, limite=20):
        return self.conexao.execute(
            """
            SELECT DISTINCT s.id AS sinal_id, s.mercado, s.linha, s.odd,
                   s.pontuacao_tecnica, s.probabilidade_calibrada,
                   s.regra_versao, s.regra_fingerprint,
                   s.motivos_json, s.features_json,
                   p.mandante, p.visitante, p.liga,
                   sn.status AS minuto_entrada,
                   sn.placar AS placar_entrada,
                   sn.qualidade_dados,
                   r.resultado, r.retorno_unidades, r.encerrado_em,
                   r.fonte_resultado, r.snapshot_id_liquidacao,
                   fim.status AS status_liquidacao,
                   fim.placar AS placar_liquidacao,
                   origem.canal AS canal_teste,
                   origem.provedor_mensagem_id AS mensagem_id_origem
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            JOIN snapshots sn ON sn.id=s.snapshot_id
            JOIN resultados_sinais r ON r.sinal_id=s.id
            LEFT JOIN snapshots fim ON fim.id=r.snapshot_id_liquidacao
            JOIN entregas_alertas origem
              ON origem.sinal_id=s.id AND origem.status='entregue'
             AND origem.canal LIKE '%:teste'
             AND origem.canal NOT LIKE '%:teste:resultado'
            WHERE NOT EXISTS (
                SELECT 1 FROM entregas_alertas aviso
                WHERE aviso.sinal_id=s.id
                  AND aviso.canal=origem.canal || ':resultado'
            )
              AND NOT EXISTS (
                  SELECT 1 FROM revisoes_resultados rev
                  WHERE rev.sinal_id=s.id
                    AND rev.notificacao_status='entregue'
              )
            ORDER BY r.encerrado_em, s.id
            LIMIT ?
            """,
            (int(limite),),
        ).fetchall()

    def resultados_oficiais_nao_notificados(self, limite=20):
        return self.conexao.execute(
            """
            SELECT DISTINCT s.id AS sinal_id, s.mercado, s.linha, s.odd,
                   s.pontuacao_tecnica, s.probabilidade_calibrada,
                   s.regra_versao, s.motivos_json,
                   p.mandante, p.visitante, p.liga,
                   sn.status AS minuto_entrada,
                   sn.placar AS placar_entrada,
                   sn.qualidade_dados,
                   r.resultado, r.retorno_unidades, r.encerrado_em,
                   r.fonte_resultado, r.snapshot_id_liquidacao,
                   fim.status AS status_liquidacao,
                   fim.placar AS placar_liquidacao,
                   origem.canal AS canal_oficial,
                   origem.provedor_mensagem_id AS mensagem_id_origem
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            JOIN snapshots sn ON sn.id=s.snapshot_id
            JOIN resultados_sinais r ON r.sinal_id=s.id
            LEFT JOIN snapshots fim ON fim.id=r.snapshot_id_liquidacao
            JOIN entregas_alertas origem
              ON origem.sinal_id=s.id AND origem.status='entregue'
             AND origem.canal NOT LIKE '%:%'
            WHERE NOT EXISTS (
                SELECT 1 FROM entregas_alertas aviso
                WHERE aviso.sinal_id=s.id
                  AND aviso.canal=origem.canal || ':resultado'
            )
              AND NOT EXISTS (
                  SELECT 1 FROM revisoes_resultados rev
                  WHERE rev.sinal_id=s.id
                    AND rev.notificacao_status='entregue'
              )
            ORDER BY r.encerrado_em, s.id
            LIMIT ?
            """,
            (int(limite),),
        ).fetchall()

    def resultados_edicoes_incertas(
        self, simulacoes, limite=10, espera_minutos=2, max_tentativas=5,
    ):
        """Lista somente edits idempotentes de resultado aptos a retry."""
        filtro_canal = (
            "origem.canal LIKE '%:teste'"
            if simulacoes else "origem.canal NOT LIKE '%:%'"
        )
        return self.conexao.execute(
            f"""
            SELECT aviso.id AS entrega_id, aviso.sinal_id,
                   aviso.canal AS canal_registro,
                   aviso.status AS status_claim, aviso.tentativas,
                   s.mercado, s.linha, s.odd, s.pontuacao_tecnica,
                   s.probabilidade_calibrada, s.regra_versao,
                   s.regra_fingerprint, s.motivos_json, s.features_json,
                   p.mandante, p.visitante, p.liga,
                   sn.status AS minuto_entrada,
                   sn.placar AS placar_entrada, sn.qualidade_dados,
                   r.resultado, r.retorno_unidades, r.encerrado_em,
                   r.fonte_resultado, r.snapshot_id_liquidacao,
                   fim.status AS status_liquidacao,
                   fim.placar AS placar_liquidacao,
                   origem.canal AS canal_origem,
                   origem.provedor_mensagem_id AS mensagem_id_origem
            FROM entregas_alertas aviso
            JOIN sinais s ON s.id=aviso.sinal_id
            JOIN partidas p ON p.id=s.partida_id
            JOIN snapshots sn ON sn.id=s.snapshot_id
            JOIN resultados_sinais r ON r.sinal_id=s.id
            LEFT JOIN snapshots fim ON fim.id=r.snapshot_id_liquidacao
            JOIN entregas_alertas origem
              ON origem.sinal_id=s.id AND origem.status='entregue'
             AND origem.canal || ':resultado'=aviso.canal
             AND origem.provedor='telegram'
             AND origem.provedor_mensagem_id IS NOT NULL
            WHERE aviso.status IN ('enviando', 'tentando', 'incerto')
              AND aviso.tentativas < ?
              AND (
                  aviso.status='incerto'
                  OR datetime(aviso.tentado_em) <= datetime(
                      'now', 'localtime', ?
                  )
              )
              AND {filtro_canal}
            ORDER BY aviso.tentado_em, aviso.id
            LIMIT ?
            """,
            (
                int(max_tentativas),
                f"-{int(espera_minutos)} minutes",
                int(limite),
            ),
        ).fetchall()

    def reservar_reenvio_edicao_resultado(self, entrega_id, instante=None):
        instante = normalizar_data(instante)
        token = secrets.token_urlsafe(24)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE entregas_alertas
                SET status='tentando', tentado_em=?,
                    tentativas=tentativas+1, reserva_token=?, erro=NULL
                WHERE id=?
                  AND status IN ('enviando', 'tentando', 'incerto')
                  AND canal LIKE '%:resultado'
                  AND EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=entregas_alertas.sinal_id
                        AND origem.canal || ':resultado'
                            =entregas_alertas.canal
                        AND origem.status='entregue'
                        AND origem.provedor='telegram'
                        AND origem.provedor_mensagem_id IS NOT NULL
                  )
                """,
                (instante, token, int(entrega_id)),
            )
        return token if cursor.rowcount == 1 else None

    def revisoes_simulacoes_nao_notificadas(self, limite=20):
        return self.conexao.execute(
            """
            SELECT DISTINCT rev.id AS revisao_id, rev.sinal_id,
                   rev.resultado_anterior, rev.motivo,
                   s.mercado, s.linha, s.odd, s.regra_versao,
                   p.mandante, p.visitante,
                   origem.canal AS canal_teste,
                   origem.provedor_mensagem_id AS mensagem_id_origem
            FROM revisoes_resultados rev
            JOIN sinais s ON s.id=rev.sinal_id
            JOIN partidas p ON p.id=s.partida_id
            JOIN entregas_alertas origem
              ON origem.sinal_id=s.id AND origem.status='entregue'
             AND origem.canal LIKE '%:teste'
             AND origem.canal NOT LIKE '%:teste:resultado'
            WHERE rev.notificacao_status='pendente'
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas aviso
                  WHERE aviso.sinal_id=s.id
                    AND aviso.canal=origem.canal || ':correcao:' || rev.id
              )
            ORDER BY rev.revisado_em, rev.id
            LIMIT ?
            """,
            (int(limite),),
        ).fetchall()

    def marcar_revisao_resultado_notificada(
        self, revisao_id, status, erro=None, provedor=None,
        provedor_destino_id=None, provedor_mensagem_id=None,
        confirmacao=None,
    ):
        if status not in ("entregue", "erro"):
            raise ValueError("Status de revisão inválido.")
        confirmacao_json = (
            json.dumps(
                confirmacao,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if confirmacao is not None else None
        )
        with self.conexao:
            self.conexao.execute(
                """
                UPDATE revisoes_resultados
                SET notificacao_status=?, notificacao_erro=?,
                    notificacao_provedor=COALESCE(
                        notificacao_provedor, ?
                    ),
                    notificacao_destino_id=COALESCE(
                        notificacao_destino_id, ?
                    ),
                    notificacao_mensagem_id=COALESCE(
                        notificacao_mensagem_id, ?
                    ),
                    notificacao_confirmacao_json=COALESCE(
                        notificacao_confirmacao_json, ?
                    )
                WHERE id=?
                """,
                (
                    status,
                    erro,
                    provedor,
                    (
                        str(provedor_destino_id)
                        if provedor_destino_id is not None else None
                    ),
                    (
                        str(provedor_mensagem_id)
                        if provedor_mensagem_id is not None else None
                    ),
                    confirmacao_json,
                    int(revisao_id),
                ),
            )

    def alertas_com_erro_para_reenvio(self, limite=5, espera_minutos=2):
        return self.conexao.execute(
            """
            SELECT e.id AS entrega_id, e.sinal_id, e.canal,
                   (
                       SELECT COALESCE(SUM(h.tentativas), 0)
                       FROM entregas_alertas h
                       WHERE h.sinal_id=e.sinal_id AND h.canal=e.canal
                         AND h.status IN ('erro', 'tentando')
                   ) AS tentativas,
                   s.mercado, s.linha, s.odd, s.pontuacao_tecnica,
                   s.probabilidade_calibrada, s.regra_versao,
                   s.regra_fingerprint, s.motivos_json, s.features_json,
                   s.status AS status_sinal,
                   sn.status AS minuto, sn.placar, sn.qualidade_dados,
                   p.packball_url, p.mandante, p.visitante
            FROM entregas_alertas e
            JOIN sinais s ON s.id=e.sinal_id
            JOIN snapshots sn ON sn.id=s.snapshot_id
            JOIN partidas p ON p.id=s.partida_id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE e.status='erro'
              AND (
                  SELECT COALESCE(SUM(h.tentativas), 0)
                  FROM entregas_alertas h
                  WHERE h.sinal_id=e.sinal_id AND h.canal=e.canal
                    AND h.status IN ('erro', 'tentando')
              ) < 3
              AND s.status='aprovado' AND r.sinal_id IS NULL
              AND datetime(e.tentado_em) <= datetime(
                    'now', 'localtime', ?
              )
              AND datetime(s.criado_em) >= datetime(
                    'now', 'localtime', '-10 minutes'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas ok
                  WHERE ok.sinal_id=e.sinal_id AND ok.canal=e.canal
                    AND ok.status='entregue'
              )
            ORDER BY e.tentado_em, e.id
            LIMIT ?
            """,
            (f"-{int(espera_minutos)} minutes", int(limite)),
        ).fetchall()

    def marcar_alerta_em_reenvio(self, entrega_id):
        token = secrets.token_urlsafe(24)
        instante = normalizar_data(None)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE entregas_alertas
                SET status='tentando', tentado_em=?, reserva_token=?
                WHERE id=? AND status='erro'
                  AND EXISTS (
                      SELECT 1 FROM sinais s
                      WHERE s.id=entregas_alertas.sinal_id
                        AND s.status='aprovado'
                        AND s.snapshot_id=(
                            SELECT sn.id
                            FROM snapshots sn
                            WHERE sn.partida_id=s.partida_id
                            ORDER BY datetime(sn.coletado_em) DESC, sn.id DESC
                            LIMIT 1
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM resultados_sinais r
                            WHERE r.sinal_id=s.id
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM entregas_alertas final
                            WHERE final.sinal_id=s.id
                              AND final.status='entregue'
                        )
                  )
                """,
                (instante, token, int(entrega_id)),
            )
        return token if cursor.rowcount == 1 else None

    def consolidar_falha_reenvio(self, entrega_id, sinal_id, canal):
        """Transfere tentativas da intencao antiga para o novo erro."""
        with self.conexao:
            anterior = self.conexao.execute(
                """
                SELECT tentativas FROM entregas_alertas
                WHERE id=? AND status='tentando'
                """,
                (int(entrega_id),),
            ).fetchone()
            if anterior is None:
                return False
            atual = self.conexao.execute(
                """
                SELECT id FROM entregas_alertas
                WHERE sinal_id=? AND canal=? AND status='erro'
                ORDER BY id DESC LIMIT 1
                """,
                (int(sinal_id), canal),
            ).fetchone()
            if atual is None:
                self.conexao.execute(
                    """
                    UPDATE entregas_alertas
                    SET status='erro', tentativas=tentativas + 1
                    WHERE id=?
                    """,
                    (int(entrega_id),),
                )
                return True
            self.conexao.execute(
                """
                UPDATE entregas_alertas
                SET tentativas=tentativas + ?
                WHERE id=?
                """,
                (int(anterior["tentativas"]), int(atual["id"])),
            )
            self.conexao.execute(
                "DELETE FROM entregas_alertas WHERE id=?",
                (int(entrega_id),),
            )
        return True

    def finalizar_erro_alerta(self, entrega_id, status="cancelado"):
        if status not in (
            "cancelado", "expirado", "recuperado", "incerto_origem"
        ):
            raise ValueError("Status final de entrega inválido.")
        with self.conexao:
            self.conexao.execute(
                """
                UPDATE entregas_alertas SET status=?
                WHERE id=? AND status IN ('erro', 'tentando')
                """,
                (status, entrega_id),
            )

    def expirar_alertas_com_erro(self, minutos=10):
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE entregas_alertas SET status='expirado'
                WHERE status='erro' AND sinal_id IN (
                    SELECT id FROM sinais
                    WHERE datetime(criado_em) < datetime(
                        'now', 'localtime', ?
                    )
                )
                """,
                (f"-{int(minutos)} minutes",),
            )
        return cursor.rowcount

    def registrar_consulta_finalizacao(
        self,
        partida_id,
        fonte,
        estado,
        status_observado=None,
        placar_observado=None,
        erro=None,
        instante=None,
    ):
        instante = normalizar_data(instante)
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT INTO consultas_finalizacao (
                    partida_id, fonte, consultado_em, estado,
                    status_observado, placar_observado, erro
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    partida_id,
                    fonte,
                    instante,
                    estado,
                    status_observado,
                    placar_observado,
                    erro,
                ),
            )
        return cursor.lastrowid

    def consulta_finalizacao_recente(
        self, partida_id, fonte, minutos=10, agora=None
    ):
        linha = self.conexao.execute(
            """
            SELECT consultado_em FROM consultas_finalizacao
            WHERE partida_id=? AND fonte=?
            ORDER BY consultado_em DESC, id DESC LIMIT 1
            """,
            (partida_id, fonte),
        ).fetchone()
        if linha is None:
            return False
        agora = agora or datetime.now()
        consultado = datetime.fromisoformat(linha["consultado_em"])
        return agora - consultado < timedelta(minutes=minutos)

    def migrar_jsonl(self, caminho_jsonl):
        caminho_jsonl = Path(caminho_jsonl)
        chave = f"jsonl_importado:{caminho_jsonl.resolve()}"
        if self.conexao.execute(
            "SELECT 1 FROM metadados WHERE chave=?", (chave,)
        ).fetchone():
            return 0
        if not caminho_jsonl.exists():
            return 0

        importados = 0
        with caminho_jsonl.open("r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                try:
                    registro = json.loads(linha)
                    if registro.get("url") and self.salvar_registro(registro):
                        importados += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

        with self.conexao:
            self.conexao.execute(
                "INSERT OR REPLACE INTO metadados(chave, valor) VALUES (?, ?)",
                (chave, datetime.now().isoformat()),
            )
        return importados

    def total_escanteios_intervalo(
        self, packball_url=None, partida_id=None, antes_snapshot_id=None
    ):
        if packball_url is None and partida_id is None:
            raise ValueError("Informe a URL ou o ID da partida.")
        filtros = [
            "(LOWER(TRIM(s.status))='ht' "
            "OR LOWER(s.status) LIKE '%intervalo%' "
            "OR LOWER(s.status) LIKE '%half time%')"
        ]
        parametros = []
        if partida_id is not None:
            filtros.append("s.partida_id=?")
            parametros.append(partida_id)
        else:
            filtros.append("p.packball_url=?")
            parametros.append(packball_url)
        if antes_snapshot_id is not None:
            filtros.append("s.id < ?")
            parametros.append(antes_snapshot_id)
        linhas = self.conexao.execute(
            f"""
            SELECT s.estatisticas_json
            FROM snapshots s
            JOIN partidas p ON p.id=s.partida_id
            WHERE {' AND '.join(filtros)}
            ORDER BY datetime(s.coletado_em) DESC, s.id DESC
            """,
            parametros,
        ).fetchall()
        for linha in linhas:
            try:
                estatisticas = json.loads(
                    linha["estatisticas_json"] or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                continue
            numeros = re.findall(
                r"\d+(?:[.,]\d+)?",
                str(estatisticas.get("Escanteios") or ""),
            )
            if len(numeros) >= 2:
                return sum(
                    float(numero.replace(",", "."))
                    for numero in numeros[:2]
                )
        return None

    def carregar_historico_recente(self, minutos=20):
        limite = (datetime.now() - timedelta(minutes=minutos)).isoformat()
        linhas = self.conexao.execute(
            """
            SELECT p.packball_url, s.coletado_em, s.estatisticas_json,
                   s.status, s.placar, s.confirmacao_api_json
            FROM snapshots s
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.coletado_em >= ?
            ORDER BY s.coletado_em
            """,
            (limite,),
        ).fetchall()
        historico = {}
        for linha in linhas:
            historico.setdefault(linha["packball_url"], []).append(
                {
                    "instante": datetime.fromisoformat(
                        linha["coletado_em"]
                    ),
                    "estatisticas": json.loads(
                        linha["estatisticas_json"] or "{}"
                    ),
                    "status": linha["status"],
                    "placar": linha["placar"],
                    "confirmacao_api": json.loads(
                        linha["confirmacao_api_json"] or "null"
                    ),
                }
            )
        return historico

    def carregar_ultimas_odds(self, packball_url):
        linhas = self.conexao.execute(
            """
            SELECT o.tipo, o.mercado, o.dados, o.estrutura_json,
                   s.coletado_em
            FROM odds o
            JOIN snapshots s ON s.id=o.snapshot_id
            JOIN partidas p ON p.id=s.partida_id
            WHERE p.packball_url=?
              AND s.id=(
                  SELECT MAX(s2.id)
                  FROM snapshots s2
                  JOIN odds o2 ON o2.snapshot_id=s2.id
                  WHERE s2.partida_id=p.id
              )
            ORDER BY o.id
            """,
            (packball_url,),
        ).fetchall()
        resultado = {"pre_jogo": [], "ao_vivo": []}
        instantes_origem = []
        for linha in linhas:
            estrutura = json.loads(linha["estrutura_json"] or "{}")
            coletado_em = estrutura.get("coletado_em")
            if coletado_em:
                instantes_origem.append(coletado_em)
            resultado.setdefault(linha["tipo"], []).append(
                {
                    "mercado": linha["mercado"],
                    "dados": linha["dados"],
                    **estrutura,
                    "coletado_em": coletado_em,
                    "cache": True
                    if isinstance(estrutura.get("cache"), bool)
                    else None,
                }
            )
        origem = min(instantes_origem) if instantes_origem else None
        idade = None
        if origem:
            try:
                idade = max(
                    0.0,
                    (datetime.now() - datetime.fromisoformat(origem))
                    .total_seconds(),
                )
            except (TypeError, ValueError):
                idade = None
        resultado["_metadados"] = {
            "cache": True,
            "coletado_em": origem,
            "idade_segundos": round(idade, 3) if idade is not None else None,
        }
        return resultado

    def carregar_instantes_agendamento(self, packball_urls):
        urls = list(dict.fromkeys(packball_urls or []))
        if not urls:
            return {}
        marcadores = ",".join("?" for _ in urls)
        linhas = self.conexao.execute(
            f"""
            SELECT p.packball_url,
                   MAX(s.coletado_em) AS ultima_coleta,
                   MAX(CASE WHEN o.id IS NOT NULL THEN COALESCE(
                       CASE WHEN json_valid(o.estrutura_json)
                            THEN NULLIF(json_extract(
                                o.estrutura_json, '$.coletado_em'
                            ), '')
                       END,
                       s.coletado_em
                   ) END) AS ultima_odds
            FROM partidas p
            JOIN snapshots s ON s.partida_id=p.id
            LEFT JOIN odds o ON o.snapshot_id=s.id
            WHERE p.packball_url IN ({marcadores})
            GROUP BY p.id
            """,
            urls,
        ).fetchall()
        return {
            linha["packball_url"]: {
                "ultima_coleta": linha["ultima_coleta"],
                "ultima_odds": linha["ultima_odds"],
            }
            for linha in linhas
        }

    def contagens(self):
        return {
            "partidas": self.conexao.execute(
                "SELECT COUNT(*) FROM partidas"
            ).fetchone()[0],
            "snapshots": self.conexao.execute(
                "SELECT COUNT(*) FROM snapshots"
            ).fetchone()[0],
            "odds": self.conexao.execute(
                "SELECT COUNT(*) FROM odds"
            ).fetchone()[0],
            "eventos": self.conexao.execute(
                "SELECT COUNT(*) FROM eventos"
            ).fetchone()[0],
            "sinais": self.conexao.execute(
                "SELECT COUNT(*) FROM sinais"
            ).fetchone()[0],
        }

    def limpar_dados_antigos(self, dias=180):
        limite = (datetime.now() - timedelta(days=dias)).isoformat()
        with self.conexao:
            sinais_descartados = self.conexao.execute(
                """
                DELETE FROM sinais
                WHERE criado_em < ? AND status IN ('rejeitado', 'duplicado')
                  AND id NOT IN (SELECT sinal_id FROM resultados_sinais)
                  AND id NOT IN (SELECT sinal_id FROM entregas_alertas)
                """,
                (limite,),
            ).rowcount
            removidos = self.conexao.execute(
                """
                DELETE FROM snapshots
                WHERE coletado_em < ?
                  AND id NOT IN (SELECT snapshot_id FROM sinais)
                  AND NOT EXISTS (
                      SELECT 1
                      FROM sinais s
                      JOIN entregas_alertas e ON e.sinal_id=s.id
                      WHERE s.partida_id=snapshots.partida_id
                        AND e.status='entregue'
                        AND e.canal NOT LIKE 'gateway:%'
                        AND INSTR(e.canal, ':resultado')=0
                        AND INSTR(e.canal, ':green_antecipado')=0
                        AND INSTR(e.canal, ':aguardar_odd')=0
                        AND INSTR(e.canal, ':cancelamento')=0
                        AND INSTR(e.canal, ':insuficiente')=0
                        AND INSTR(e.canal, ':monitoramento_final')=0
                        AND INSTR(e.canal, ':correcao')=0
                        AND datetime(snapshots.coletado_em) > datetime(
                            COALESCE(e.entregue_em,e.tentado_em)
                        )
                        AND datetime(snapshots.coletado_em) <= datetime(
                            COALESCE(e.entregue_em,e.tentado_em),
                            '+10 minutes'
                        )
                  )
                """,
                (limite,),
            ).rowcount
            self.conexao.execute(
                """
                DELETE FROM partidas
                WHERE id NOT IN (SELECT DISTINCT partida_id FROM snapshots)
                  AND id NOT IN (
                      SELECT DISTINCT partida_id
                      FROM observacoes_fontes_odds
                      WHERE partida_id IS NOT NULL
                  )
                """
            )
        return {
            "snapshots": removidos,
            "sinais_descartados": sinais_descartados,
        }

    def checkpoint_wal(self):
        linha = self.conexao.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        if linha is None:
            return {
                "ocupado": None,
                "paginas": None,
                "checkpoint": None,
            }
        return {
            "ocupado": int(linha[0]),
            "paginas": int(linha[1]),
            "checkpoint": int(linha[2]),
        }

    def fechar(self):
        self.conexao.close()
