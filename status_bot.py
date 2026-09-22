import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from backtest import AvaliadorBacktest
from autostart_windows import consultar as consultar_autostart
from avaliacao_contexto import (
    TAMANHO_COORTE as TAMANHO_COORTE_CONTEXTO,
    TAMANHO_HOLDOUT as TAMANHO_HOLDOUT_CONTEXTO,
    auditar_historico_avaliacao_contexto,
    avaliar_contexto_avancado,
)
from backup_banco import BackupBanco, verificar_arquivo_backup
from bet365_odds import resumir_observacoes_bet365
from banco import (
    BancoMonitor,
    auditar_historico_drift_simulacoes,
    resumir_historico_drift_simulacoes,
)
from calibracao import (
    POLITICA_CALIBRACAO_VERSAO,
    hash_modelo_calibracao,
    serializar_modelo_calibracao,
)
from challenger_v2_ft import resumir_challenger_v2_ft
from validacao_gols_antecipados import resumir_validacao_gols_antecipados
from validacao_top_criterios_gols import resumir_top_criterios_gols
from configuracao import obter_limites_risco, validar_configuracao
from controle_acesso_packball import (
    auditar_ritmo_packball,
    verificar_acesso_packball,
)
from controle_sistema import ler_modo_manutencao
from contexto_pre_jogo import resumir_cobertura_contexto
from dataset_temporal import resumir_cobertura_dataset_temporal
from diagnostico_funil_proximo_gol import (
    executar as executar_diagnostico_funil_proximo_gol,
)
from integridade_calibracao import auditar_particoes_calibracao
from fila_odds_manual import listar_solicitacoes_odds_manuais
from hipoteses_sombra import avaliar_hipoteses_sombra_ativas
from exploracao_sombra import resumir_exploracoes_sombra
from observabilidade import Observabilidade
from thestatsapi import TheStatsAPI
from mercados import (
    MERCADOS_CALIBRADOS,
    ROTULOS_MERCADOS,
    mercados_calibrados_operacionais,
)
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS
from linhagem_regras import (
    auditar_linhagem_regra,
    fingerprint_vinculado_no_banco,
    resumir_cobertura_linhagem_sinais,
)
from processo_monitor import (
    ARQUIVOS_RUNTIME_WATCHDOG,
    estado_codigo_runtime,
    ler_estado,
    pid_ativo,
    trava_em_uso,
)
from proveniencia_odds import resumir_custodia_cotacao_oficial
from validacao_escanteios_ft_asiatico_executavel import (
    resumir_validacao as resumir_validacao_escanteios_executavel,
)
from progresso_calibracao import resumir_progresso_calibracao
from historico_api_live import resumir_historico_api_live
from prontidao_profissional import avaliar_prontidao, coletar_evidencias
from relatorio_odds_periodos import (
    diagnosticar_fontes_odds_periodos,
    resumir_odds_escanteios_periodos,
)
from relatorio_pendencias import resumir_pendencias_resultados
from relatorio_simulacoes import (
    comparar_filtros_por_mercado,
    comparar_filtro_simulacoes,
    obter_experimento_filtro,
    resumir_simulacoes,
)
from resgate_qualidade_api import resumir_resgate_qualidade_api
from supervisao_melhor_preco_sombra import (
    verificar_integridade_melhor_preco_sombra,
)
from supervisao_referencia_api_football import (
    verificar_referencia_api_football_sombra,
)
from versoes_gol_ft_reforcado import (
    VERSOES_REGRAS_OPERACIONAIS_POR_MERCADO
    as VERSOES_REGRAS_POR_MERCADO,
    versao_regra_operacional as versao_regra_para_mercado,
    versoes_regras_operacionais as versoes_regras_ativas,
)
from watchdog import (
    verificar_acompanhamento_preco_pos_alerta,
    verificar_amostragem_referencia_odds_sombra,
    verificar_avaliacao_acompanhamento_odd,
    verificar_avaliacao_desajuste_odds,
    verificar_avaliacao_probabilidade_individual,
    verificar_avaliacao_quarentena_fallback_ht,
    verificar_avaliacao_prioridade_ligas_gols,
    verificar_capacidade_coleta,
    verificar_cache_api_operacional,
    verificar_coleta,
    verificar_pareamento_api,
    verificar_ponto_recuperacao,
    verificar_prioridade_scanner_packball,
    verificar_validacao,
)


PASTA = Path(__file__).parent


def _descrever_cronologia_avaliacao(avaliacao):
    cronologia = (avaliacao or {}).get("cronologia_execucao") or {}
    if cronologia.get("valida") is True:
        return "ok"
    problemas = cronologia.get("problemas") or []
    if problemas:
        return "inválida:" + ",".join(str(item) for item in problemas)
    return "-"


def _descrever_efeitos_avaliacao(avaliacao):
    efeitos = (avaliacao or {}).get("efeitos_operacionais") or {}
    if efeitos.get("valida") is True:
        return "bloqueados"
    problemas = list(efeitos.get("campos_invalidos") or [])
    problemas.extend(
        f"{chave}:ausente"
        for chave in (efeitos.get("campos_ausentes") or [])
    )
    if problemas:
        return "inválidos:" + ",".join(str(item) for item in problemas)
    return "-"


def _descrever_exposicao_avaliacao(avaliacao):
    exposicao = (
        (avaliacao or {}).get("exposicao_coleta_prospectiva") or {}
    )
    if not exposicao:
        return "-"
    estado = exposicao.get("estado") or "-"
    por_coorte = exposicao.get("por_coorte") or {}
    principal = por_coorte.get("principal") or {}
    if not por_coorte:
        return estado
    resumo = (
        f"{estado}; principal="
        f"{principal.get('ciclos_concluidos', 0)} ciclos/"
        f"{principal.get('partidas_somadas', 0)} partidas/"
        f"{principal.get('tarefas_processadas', 0)} tarefas"
    )
    if len(por_coorte) > 1:
        resumo += (
            f"; coortes={exposicao.get('coortes', len(por_coorte))}/"
            f"observadas={exposicao.get('coortes_com_exposicao', 0)}/"
            "pausadas="
            f"{exposicao.get('coortes_sem_exposicao_por_manutencao', 0)}"
        )
    if exposicao.get("requer_atencao"):
        resumo += "; atenção=sim"
    return resumo


def descrever_prioridade_ligas_gols(avaliacao):
    avaliacao = avaliacao or {}
    return (
        "prioridade sazonal de ligas: "
        f"estado={avaliacao.get('estado') or '-'} | "
        f"execução={avaliacao.get('estado_execucao') or '-'} | "
        f"cronologia={_descrever_cronologia_avaliacao(avaliacao)} | "
        f"efeitos={_descrever_efeitos_avaliacao(avaliacao)} | "
        f"exposição={_descrever_exposicao_avaliacao(avaliacao)} | "
        f"saudável={'sim' if avaliacao.get('saudavel') else 'não'} | "
        f"motivo={avaliacao.get('motivo') or '-'} | "
        f"versão={avaliacao.get('versao') or '-'} | "
        "partidas independentes/decisões brutas="
        f"{avaliacao.get('unidades_independentes', 0)}/"
        f"{avaliacao.get('decisoes_brutas', 0)} | "
        "prioridade oportunidades/jogos="
        f"{avaliacao.get('oportunidades_prioridade', 0)}/"
        f"{avaliacao.get('jogos_prioridade', 0)} | "
        "controle oportunidades/jogos="
        f"{avaliacao.get('oportunidades_controle', 0)}/"
        f"{avaliacao.get('jogos_controle', 0)} | "
        "delta/IC95="
        f"{avaliacao.get('delta_rendimento_oportunidade_por_detalhe')}/"
        f"{avaliacao.get('ic95_delta_rendimento_oportunidade')} | "
        "vantagem comprovada="
        f"{'sim' if avaliacao.get('vantagem_captura_comprovada') else 'não'} | "
        "altera fila=não"
    )


def descrever_quarentena_fallback_ht(avaliacao):
    avaliacao = avaliacao or {}
    return (
        "quarentena do fallback HT de linhas altas: "
        f"estado={avaliacao.get('estado') or '-'} | "
        f"execução={avaliacao.get('estado_execucao') or '-'} | "
        f"cronologia={_descrever_cronologia_avaliacao(avaliacao)} | "
        f"efeitos={_descrever_efeitos_avaliacao(avaliacao)} | "
        f"exposição={_descrever_exposicao_avaliacao(avaliacao)} | "
        f"saudável={'sim' if avaliacao.get('saudavel') else 'não'} | "
        f"motivo={avaliacao.get('motivo') or '-'} | "
        f"versão={avaliacao.get('versao') or '-'} | "
        "metodologia compatível="
        f"{'sim' if avaliacao.get('metodologia_compativel') else 'não'} | "
        "partidas independentes/decisões brutas="
        f"{avaliacao.get('unidades_independentes', 0)}/"
        f"{avaliacao.get('decisoes_brutas_elegiveis', 0)} | "
        "quarentena válidos/holdout="
        f"{avaliacao.get('resultados_quarentena', 0)}/"
        f"{avaliacao.get('resultados_holdout_quarentena', 0)} | "
        "controle válidos/holdout="
        f"{avaliacao.get('resultados_controle', 0)}/"
        f"{avaliacao.get('resultados_holdout_controle', 0)} | "
        "vantagem/prejuízo comprovado="
        f"{'sim' if avaliacao.get('vantagem_linhas_altas_comprovada') else 'não'}/"
        f"{'sim' if avaliacao.get('prejuizo_linhas_altas_comprovado') else 'não'} | "
        "quarentena ativa="
        f"{'sim' if avaliacao.get('politica_operacional_ativa') else 'não'} | "
        "reativação automática=não"
    )


def descrever_desajuste_odds(avaliacao):
    """Resume execução, integridade e coorte sem sugerir promoção."""
    avaliacao = avaliacao or {}
    integridade = avaliacao.get("integridade_comparacoes_odds") or {}
    corroboracao = avaliacao.get("corroboracao_entrada_rapida") or {}
    observacional = (
        avaliacao.get("recorte_observacional_executavel") or {}
    )
    convergencia_gols = (
        avaliacao.get("recorte_convergencia_preco_prospectivo") or {}
    )
    convergencia_escanteios = (
        avaliacao.get("recorte_convergencia_escanteios_prospectivo") or {}
    )
    edge_sem_vig = (
        avaliacao.get("recorte_edge_sem_vig_multifonte") or {}
    )
    referencia_pos_envio = (
        avaliacao.get("recorte_referencia_pos_envio") or {}
    )
    mercados_referencia = referencia_pos_envio.get("por_mercado") or {}
    referencia_texto = ",".join(
        (
            f"{mercado}:edge={int((item or {}).get('coorte_edge') or 0)}"
            f"/controle={int((item or {}).get('coorte_controle') or 0)}"
            f"/resultados={int(((item or {}).get('total') or {}).get('resultados') or 0)}"
            f"/{(item or {}).get('decisao') or '-'}"
        )
        for mercado, item in sorted(mercados_referencia.items())
    ) or "-"
    liquidacao_edge = edge_sem_vig.get("liquidacao_resultados") or {}
    mercados_liquidacao = liquidacao_edge.get("por_mercado") or {}
    liquidacao_texto = ",".join(
        (
            f"{mercado}:coorte={int((item or {}).get('coorte') or 0)}"
            f"/resultados={int(((item or {}).get('total') or {}).get('resultados') or 0)}"
            f"/{(item or {}).get('decisao') or '-'}"
        )
        for mercado, item in sorted(mercados_liquidacao.items())
    ) or "-"
    contrato_fontes = (
        avaliacao.get("contrato_fontes_observacionais") or {}
    )
    fontes = observacional.get("fontes_observadas") or {}
    origens = observacional.get("origens_observacoes") or {}
    fontes_texto = ",".join(
        f"{nome}:{fontes[nome]}" for nome in sorted(fontes)
    ) or "-"
    origens_texto = ",".join(
        f"{nome}:{origens[nome]}" for nome in sorted(origens)
    ) or "-"
    fingerprint = str(
        integridade.get("fingerprint_evidencias") or ""
    )
    return (
        "desajuste de odds multifonte: "
        f"estado={avaliacao.get('estado') or '-'} | "
        f"execução={avaliacao.get('estado_execucao') or '-'} | "
        f"cronologia={_descrever_cronologia_avaliacao(avaliacao)} | "
        f"efeitos={_descrever_efeitos_avaliacao(avaliacao)} | "
        f"exposição={_descrever_exposicao_avaliacao(avaliacao)} | "
        f"saudável={'sim' if avaliacao.get('saudavel') else 'não'} | "
        f"motivo={avaliacao.get('motivo') or '-'} | "
        f"versão={avaliacao.get('versao') or '-'} | "
        "integridade válidas/auditadas/inválidas="
        f"{integridade.get('comparacoes_validas', 0)}/"
        f"{integridade.get('comparacoes_auditadas', 0)}/"
        f"{integridade.get('comparacoes_invalidas', 0)} | "
        "truncada="
        f"{'sim' if integridade.get('auditoria_truncada') else 'não'} | "
        f"fingerprint={fingerprint[:12] or '-'} | "
        "corroboração fotos/jogos/faltam="
        f"{corroboracao.get('fotografias_independentes', 0)}/"
        f"{corroboracao.get('jogos_distintos', 0)}/"
        f"{corroboracao.get('faltam_fotografias', 0)}+"
        f"{corroboracao.get('faltam_jogos', 0)} | "
        "Bet365 candidatos/seguidos/persistentes="
        f"{observacional.get('candidatos_independentes', 0)}/"
        f"{observacional.get('com_seguimento_mesma_bookmaker_5m', 0)}/"
        f"{observacional.get('persistentes_mesma_bookmaker_5m', 0)} | "
        "vantagem executável="
        f"{'sim' if observacional.get('vantagem_executavel_comprovada') else 'não'} | "
        "fontes/origens="
        f"{fontes_texto}/{origens_texto} | "
        "fonte independente="
        f"{'sim' if observacional.get('contraparte_exige_fonte_independente') else 'não'} | "
        "contrato fontes="
        f"{'ok' if contrato_fontes.get('saudavel') else 'falha'} | "
        "convergência gols/escanteios="
        f"{convergencia_gols.get('decisao') or '-'}/"
        f"{convergencia_escanteios.get('decisao') or '-'} | "
        "edge sem vig fotos/coorte/faltam="
        f"{edge_sem_vig.get('fotografias_completas', 0)}/"
        f"{edge_sem_vig.get('coorte', 0)}/"
        f"{edge_sem_vig.get('faltam_coorte', 0)} | "
        f"decisão sem vig={edge_sem_vig.get('decisao') or '-'} | "
        "liquidação sem vig candidatos/resultados/pendentes="
        f"{liquidacao_edge.get('candidatos_liquidaveis', 0)}/"
        f"{liquidacao_edge.get('resultados', 0)}/"
        f"{liquidacao_edge.get('pendentes', 0)} | "
        f"liquidação por mercado={liquidacao_texto} | "
        "vantagem sem vig comprovada="
        f"{'sim' if edge_sem_vig.get('vantagem_executavel_comprovada') else 'não'} | "
        "referência pós-envio auditorias/fotos="
        f"{referencia_pos_envio.get('auditorias_pos_envio', 0)}/"
        f"{referencia_pos_envio.get('fotografias_independentes', 0)} | "
        f"coortes pós-envio={referencia_texto} | "
        "vantagem pós-envio para revisão="
        f"{'sim' if referencia_pos_envio.get('vantagem_estatistica_para_revisao') else 'não'} | "
        "integridade pós-envio="
        f"{'ok' if referencia_pos_envio.get('saudavel') else 'falha'} | "
        "bloqueia inferência="
        f"{'não' if avaliacao.get('saudavel') else 'sim'} | "
        "aplicação automática=não"
    )


def enriquecer_validacao_com_watchdog(validacao, estado_watchdog):
    """Anexa evidencias persistentes que nao existem na auditoria pontual."""
    resultado = dict(validacao or {})
    persistida = (estado_watchdog or {}).get("validacao") or {}
    for chave in (
        "armazenamento",
        "drill_restauracao_compactada",
    ):
        valor = persistida.get(chave)
        if isinstance(valor, dict) and valor:
            resultado[chave] = valor
    return resultado


def _percentual_status(valor):
    return "n/d" if valor is None else f"{valor}%"


def _segundos_status(valor):
    return "n/d" if valor is None else f"{valor}s"


def descrever_cota_provedor(contador_api):
    """Expõe quando a última fotografia pertence a outro dia UTC."""
    contador_api = dict(contador_api or {})
    limite = contador_api.get("limite_confirmado_provedor")
    if limite is None:
        return None
    dia_atual = str(contador_api.get("dia") or "-")
    dia_provedor = str(
        contador_api.get("cota_provedor_dia")
        or (contador_api.get("provedor") or {}).get("dia")
        or "-"
    )
    vigente = contador_api.get("cota_provedor_vigente")
    if vigente is None:
        vigente = bool(
            dia_atual != "-" and dia_provedor != "-"
            and dia_atual == dia_provedor
        )
    observado = contador_api.get("cota_observada_em")
    try:
        observado_texto = datetime.fromtimestamp(
            float(observado), tz=timezone.utc
        ).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        observado_texto = "-"
    rotulo = "cota vigente do provedor" if vigente else (
        "última cota do provedor (dia anterior; não aplicada ao saldo atual)"
    )
    return (
        f"  {rotulo}: dia={dia_provedor} | dia atual={dia_atual} | "
        f"limite={limite} | restante informado="
        f"{contador_api.get('restante_informado_provedor')} | "
        f"observada em UTC={observado_texto} | "
        f"aplicada ao dia atual={'sim' if vigente else 'não'}"
    )


def resumir_simulacoes_ativas_hoje(conexao, regras_por_mercado):
    """Conta apenas envios das linhagens atualmente usadas por mercado."""
    regras = dict(regras_por_mercado or {})
    if not regras:
        return {}
    clausulas = []
    parametros = []
    for mercado, regra_versao in regras.items():
        clausulas.append("(s.mercado=? AND s.regra_versao=?)")
        parametros.extend((mercado, regra_versao))
    linhas = conexao.execute(
        f"""
        SELECT s.mercado, COUNT(DISTINCT s.id) AS quantidade
        FROM sinais s
        JOIN entregas_alertas e ON e.sinal_id=s.id
        WHERE e.status='entregue' AND e.canal LIKE '%:teste'
          AND date(e.entregue_em)=date('now', 'localtime')
          AND ({' OR '.join(clausulas)})
        GROUP BY s.mercado
        """,
        tuple(parametros),
    ).fetchall()
    contagens = {linha["mercado"]: linha["quantidade"] for linha in linhas}
    return {
        mercado: int(contagens.get(mercado, 0))
        for mercado in regras
    }


def descrever_simulacoes_ativas_hoje(contagens):
    return " | ".join(
        f"{mercado}={quantidade}"
        for mercado, quantidade in (contagens or {}).items()
    ) or "nenhuma"


def resumir_filtros_regras_ativas(conexao, mercados):
    regras = {
        mercado: versao_regra_para_mercado(mercado)
        for mercado in mercados
    }
    fingerprints = {
        regra: fingerprint_vinculado_no_banco(conexao, regra)
        for regra in set(regras.values())
    }
    return comparar_filtros_por_mercado(
        conexao,
        regras,
        fingerprints_por_regra=fingerprints,
    )


def descrever_filtro_regra_ativa(resumo):
    comparacao = resumo.get("comparacao") or {}
    enviadas = resumo.get("enviadas") or {}
    filtradas = resumo.get("filtradas") or {}

    def roi_texto(metricas):
        roi = metricas.get("roi")
        return "-" if roi is None else f"{roi * 100:+.1f}%"

    return (
        f"  filtro ativo {resumo.get('mercado')} "
        f"[{resumo.get('regra_versao')}]: "
        f"{comparacao.get('estado', 'amostra_insuficiente')} | "
        "enviadas="
        f"{comparacao.get('amostra_enviadas', 0)} "
        f"(G={enviadas.get('greens', 0)}, R={enviadas.get('reds', 0)}, "
        f"ROI={roi_texto(enviadas)}) | filtradas="
        f"{comparacao.get('amostra_filtradas', 0)} "
        f"(G={filtradas.get('greens', 0)}, R={filtradas.get('reds', 0)}, "
        f"ROI={roi_texto(filtradas)}) | mínimo="
        f"{comparacao.get('amostra_minima_por_coorte', 30)}/grupo | "
        f"decisão={comparacao.get('decisao', 'aguardando_amostra')}"
    )


def ler_recuperacao_banco(caminho):
    caminho = Path(caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"estado": "nunca_acionada", "saudavel": True}
    except (OSError, json.JSONDecodeError, TypeError):
        return {"estado": "registro_invalido", "saudavel": False}
    if not isinstance(dados, dict) or dados.get("estado") != "banco_restaurado":
        return {"estado": "registro_invalido", "saudavel": False}
    return dados


def descrever_recuperacao_banco(registro):
    estado = (registro or {}).get("estado") or "registro_invalido"
    if estado == "nunca_acionada":
        return "recuperacao automatica do banco: nunca necessaria"
    if estado != "banco_restaurado":
        return "recuperacao automatica do banco: registro invalido"
    alerta = (registro or {}).get("alerta_telegram") or {}
    return (
        "recuperacao automatica do banco: concluida | backup="
        f"{registro.get('backup') or '-'} | em="
        f"{registro.get('restaurado_em') or '-'} | quarentena="
        f"{registro.get('quarentena') or 'nao necessaria'} | telegram="
        f"{alerta.get('estado') or 'pendente'}"
    )


def descrever_integridade_banco_ativo(auditoria):
    auditoria = auditoria or {}
    estado = auditoria.get("estado") or "aguardando_primeira_verificacao"
    return (
        "integridade periodica do banco ativo: "
        f"{estado} | ultima={auditoria.get('verificado_em') or '-'} | "
        "proxima="
        f"{auditoria.get('proxima_verificacao_em') or '-'} | "
        "recuperacao necessaria="
        f"{'sim' if auditoria.get('recuperacao_necessaria') else 'nao'}"
    )


def descrever_pendencias_prontidao(prontidao):
    pendencias = list((prontidao or {}).get("pendencias") or [])
    if not pendencias:
        return ["  pendências profissionais: nenhuma"]
    return [
        "  pendência profissional — "
        f"{item.get('requisito') or 'requisito_desconhecido'}: "
        f"{item.get('estado') or 'estado_desconhecido'}"
        for item in pendencias
    ]


def descrever_clv_live(prontidao):
    clv = (
        ((prontidao or {}).get("diagnosticos_informativos") or {})
        .get("clv_live") or {}
    )
    total = clv.get("total") or {}
    cotacao_prospectiva = clv.get(
        "cobertura_cotacao_entrada_prospectiva"
    ) or {}
    coorte_fixa = clv.get("coorte_clv_prospectiva_fixa") or {}
    cadeia_custodia = clv.get("cadeia_custodia_clv") or {}
    if not clv or clv.get("erro"):
        return (
            "valor pós-alerta (CLV/mark-to-market): indisponível | "
            f"motivo={clv.get('erro') or 'sem_avaliacao'} | edge=não"
        )

    def percentual(valor):
        try:
            return f"{float(valor) * 100:.1f}%"
        except (TypeError, ValueError):
            return "-"

    resumo_prospectivo = ""
    if cotacao_prospectiva:
        resumo_prospectivo = (
            " | cotação de entrada prospectiva="
            f"{cotacao_prospectiva.get('cotacoes_congeladas_validas', 0)}/"
            f"{cotacao_prospectiva.get('entregas_instrumentadas', 0)} "
            f"({percentual(cotacao_prospectiva.get('taxa_cobertura_cotacao_entrada'))})"
            f" | estado da instrumentação="
            f"{cotacao_prospectiva.get('estado') or 'sem_evidencia'}"
        )

    resumo_coorte_fixa = ""
    if coorte_fixa:
        resumo_coorte_fixa = (
            " | coorte CLV fixa="
            f"{coorte_fixa.get('unidades_coorte', 0)}/"
            f"{coorte_fixa.get('tamanho_planejado', 120)} "
            f"(dev={coorte_fixa.get('tamanho_desenvolvimento', 84)}, "
            f"holdout={coorte_fixa.get('tamanho_holdout', 36)})"
            " | divisão fixa="
            f"{'sim' if coorte_fixa.get('divisao_fixa') else 'não'}"
            " | estado da coorte="
            f"{coorte_fixa.get('estado') or 'sem_evidencia'}"
            " | vantagem replicada="
            f"{'sim' if coorte_fixa.get('vantagem_replicada') else 'não'}"
        )

    resumo_custodia = ""
    if cadeia_custodia:
        integridade_evidencias = (
            cadeia_custodia.get("integridade_evidencias") or {}
        )
        resumo_custodia = (
            " | cadeia de custódia CLV="
            f"{cadeia_custodia.get('estado') or 'nao_auditada'}"
            " | observações de odds auditadas="
            f"{integridade_evidencias.get('observacoes_auditadas', 0)}"
            " | inconsistências="
            f"{integridade_evidencias.get('total_problemas', 0)}"
            " | bloqueia inferência="
            f"{'sim' if cadeia_custodia.get('bloqueia_inferencia') else 'não'}"
        )

    return (
        "valor pós-alerta (CLV/mark-to-market): "
        f"versão={clv.get('versao') or '-'} | "
        f"unidade={clv.get('criterio_independencia') or '-'} | "
        "partidas/comparáveis="
        f"{clv.get('sinais_independentes_consultados', 0)}/"
        f"{clv.get('comparaveis', 0)} | "
        f"cobertura={percentual(clv.get('taxa_cobertura'))} "
        "(mínimo="
        f"{percentual(total.get('cobertura_minima_informar_edge'))}) | "
        f"estado={total.get('estado_evidencia') or 'sem_evidencia'} | "
        "pode informar edge="
        f"{'sim' if total.get('pode_informar_edge') else 'não'} | "
        "gate operacional=não"
        f"{resumo_custodia}"
        f"{resumo_prospectivo}"
        f"{resumo_coorte_fixa}"
    )


def descrever_portfolio_edge(prontidao):
    componente = (
        ((prontidao or {}).get("componentes") or {}).get("portfolio_edge")
        or {}
    )
    evidencias = componente.get("evidencias") or {}
    if not componente:
        return "portfólio de edge: não auditado | promoção automática=não"
    decisoes = evidencias.get("decisoes") or {}
    coortes = evidencias.get("coortes_selecao") or {}
    partes = []
    for mercado in sorted(decisoes):
        partes.append(
            f"{mercado}={decisoes.get(mercado) or 'sem_decisao'}"
            f"[{coortes.get(mercado) or '-'}]"
        )
    favoraveis = evidencias.get("mercados_favoraveis") or []
    return (
        "portfólio de edge: "
        f"versão={evidencias.get('versao') or '-'} | "
        "referência sem vig="
        f"{evidencias.get('versao_referencia_preco_sem_vig') or '-'} | "
        "histórico asiático="
        f"{evidencias.get('versao_avaliacao_historica_escanteios_asiaticos') or '-'} | "
        f"favoráveis={','.join(favoraveis) if favoraveis else 'nenhum'} | "
        f"decisões={'; '.join(partes) if partes else '-'} | "
        "promoção automática=não"
    )


def descrever_janelas_temporais_ritmo(resumo):
    """Expõe a amostra temporal por janela sem confundir com percentual."""
    janelas = (resumo or {}).get("janelas_temporais") or {}
    return (
        f"5min={int(janelas.get('5') or 0)} | "
        f"10min={int(janelas.get('10') or 0)} | "
        f"15min={int(janelas.get('15') or 0)}"
    )


def descrever_cobertura_temporal_priorizada(experimento):
    """Distingue cobertura útil dos focos da exploração ampla."""
    experimento = experimento or {}
    base = experimento.get("base") or {}
    atual = experimento.get("experimento") or {}
    metrica = (
        experimento.get("metrica_retencao_temporal")
        or "cobertura_temporal_total"
    )
    rotulos = {
        "cobertura_temporal_foco": "cobertura dos jogos em foco",
        "rendimento_temporal_por_foco": "rendimento por jogo em foco",
        "cobertura_temporal_total": "cobertura de todas as leituras",
    }

    def valor(resumo, chave):
        bruto = resumo.get(chave)
        return "-" if bruto is None else str(bruto)

    return (
        "cobertura temporal priorizada: "
        "foco base/atual="
        f"{valor(base, 'cobertura_temporal_foco')}/"
        f"{valor(atual, 'cobertura_temporal_foco')} | "
        "rendimento por foco base/atual="
        f"{valor(base, 'rendimento_temporal_por_foco')}/"
        f"{valor(atual, 'rendimento_temporal_por_foco')} | "
        f"métrica decisória={rotulos.get(metrica, metrica)}"
    )


def descrever_historico_api_live(resumo):
    resumo = resumo or {}
    if not resumo.get("saudavel"):
        return (
            "histórico temporal auxiliar API: indisponível | motivo="
            f"{resumo.get('motivo') or 'nao_informado'} | "
            "uso nos sinais=não"
        )
    janelas = resumo.get("janelas_disponiveis") or {}
    cobertura = resumo.get("cobertura_completa")
    cobertura_texto = (
        "-" if cobertura is None else f"{float(cobertura) * 100:.1f}%"
    )


    concordancia = resumo.get("taxa_concordancia_packball_api")
    concordancia_texto = (
        "-" if concordancia is None
        else f"{float(concordancia) * 100:.1f}%"
    )
    prontidao = resumo.get("prontidao_revisao") or {}
    progresso_prontidao = (
        f"{int(prontidao.get('snapshots', 0) or 0)}/"
        f"{int(prontidao.get('minimo_snapshots', 30) or 30)} snapshots, "
        f"{int(prontidao.get('fixtures', 0) or 0)}/"
        f"{int(prontidao.get('minimo_fixtures', 10) or 10)} jogos"
    )
    return (
        "histórico temporal auxiliar API (somente sombra): "
        f"estado={resumo.get('estado') or '-'} | "
        f"snapshots={int(resumo.get('snapshots', 0) or 0)} | "
        f"fixtures={int(resumo.get('fixtures', 0) or 0)} | "
        f"completos={cobertura_texto} | janelas "
        f"5/10/15={int(janelas.get('5', 0) or 0)}/"
        f"{int(janelas.get('10', 0) or 0)}/"
        f"{int(janelas.get('15', 0) or 0)} | "
        "comparações PackBall/API="
        f"{int(resumo.get('comparacoes_packball_api', 0) or 0)} | "
        f"concordância={concordancia_texto} | "
        "prontidão para revisão="
        f"{prontidao.get('estado') or 'aguardando_amostra'} "
        f"({progresso_prontidao}) | "
        "chamadas adicionais=0 | acessos PackBall adicionais=0 | "
        "uso nos sinais=não"
    )


def descrever_thestatsapi_sombra(
    configuracao,
    diagnostico=None,
    cobertura=None,
    ciclo=None,
):
    """Mostra se a fonte esta em medicao ou complemento oficial restrito."""
    configuracao = dict(configuracao or {})
    diagnostico = dict(diagnostico or {})
    cobertura = dict(cobertura or {})
    ciclo = dict(ciclo or {})
    consumo = diagnostico.get("consumo") or {}
    scout = ciclo.get("prioridade_packball_auxiliar") or {}
    ativa = bool(configuracao.get("sombra_ativa"))
    oficial = bool(
        configuracao.get("aplicacao_sinais")
        or ciclo.get("aplicacao_sinais")
    )
    disponivel = bool(diagnostico.get("chave_configurada"))
    estado = (
        "desativada"
        if not ativa
        else ciclo.get("estado")
        or cobertura.get("estado")
        or "aguardando_primeiro_ciclo"
    )
    chamadas_ciclo = int(ciclo.get("chamadas_rede", 0) or 0)
    chamadas_dia = int(consumo.get("usado_local_dia", 0) or 0)
    pareadas = int(
        ciclo.get(
            "pareadas", cobertura.get("pareamentos_recentes", 0)
        ) or 0
    )
    tentativas = int(ciclo.get("tentativas_pareamento", 0) or 0)
    stats = int(
        ciclo.get(
            "stats_persistidos",
            cobertura.get("jogos_com_stats", cobertura.get("stats", 0)),
        )
        or 0
    )
    odds = int(
        ciclo.get(
            "partidas_com_odds",
            cobertura.get("jogos_com_odds", cobertura.get("odds", 0)),
        )
        or 0
    )
    pareamentos_historicos = int(
        cobertura.get("pareamentos_total", 0) or 0
    )
    ultima_stats = cobertura.get("ultima_coleta_stats") or "-"
    ultima_odds = cobertura.get("ultima_coleta_odds") or "-"
    modo = "oficial fail-closed" if oficial else "somente sombra"
    return (
        f"TheStatsAPI ({modo}): "
        f"estado={estado} | chave={'sim' if disponivel else 'nao'} | "
        f"ativa={'sim' if ativa else 'nao'} | chamadas ciclo/dia="
        f"{chamadas_ciclo}/{chamadas_dia} | pareamentos="
        f"{pareadas}/{tentativas if tentativas else '-'} | "
        f"pareamentos históricos={pareamentos_historicos} | "
        f"stats={stats} | jogos com odds={odds} | "
        f"última stats/odd={ultima_stats}/{ultima_odds} | "
        "scout PB="
        f"{int(bool(scout.get('scout_reservado')))}/"
        f"{int(scout.get('scout_disponiveis', 0) or 0)} | "
        f"uso nos sinais={'sim, com gate' if oficial else 'nao'} | "
        f"Telegram={'sim, se aprovado' if oficial else 'nao'} | "
        "calibracao=nao | desligar="
        f"{'THESTATSAPI_APLICACAO_SINAIS_ATIVA=0' if oficial else 'THESTATSAPI_SOMBRA_ATIVA=0'}"
    )


def resumir_uso_fontes_odds(conexao, horas=24):
    """Conta a fonte da odd efetivamente selecionada e a entrega do sinal."""
    try:
        horas = max(float(horas), 0.0)
    except (TypeError, ValueError):
        horas = 24.0
    modificador = f"-{horas:g} hours"
    linhas = conexao.execute(
        """
        WITH entregues AS (
            SELECT sinal_id, 1 AS entregue
            FROM entregas_alertas
            WHERE status='entregue'
            GROUP BY sinal_id
        ), candidatos AS (
            SELECT s.id,
                   s.status,
                   COALESCE(
                       json_extract(s.features_json, '$.fonte_odds'),
                       'sem_odd_rastreavel'
                   ) AS fonte
            FROM sinais s
            WHERE datetime(s.criado_em) >= datetime(
                'now', 'localtime', ?
            )
              AND json_valid(s.features_json)
        )
        SELECT c.fonte,
               COUNT(*) AS avaliados,
               SUM(CASE WHEN c.status='aprovado' THEN 1 ELSE 0 END)
                   AS aprovados,
               SUM(CASE WHEN c.status='rejeitado' THEN 1 ELSE 0 END)
                   AS rejeitados,
               SUM(CASE WHEN c.status='simulacao' THEN 1 ELSE 0 END)
                   AS simulacoes,
               SUM(CASE WHEN e.entregue=1 THEN 1 ELSE 0 END)
                   AS enviados
        FROM candidatos c
        LEFT JOIN entregues e ON e.sinal_id=c.id
        GROUP BY c.fonte
        """,
        (modificador,),
    ).fetchall()
    por_fonte = {}
    for linha in linhas:
        fonte = str(linha["fonte"] or "sem_odd_rastreavel")
        por_fonte[fonte] = {
            "avaliados": int(linha["avaliados"] or 0),
            "aprovados": int(linha["aprovados"] or 0),
            "rejeitados": int(linha["rejeitados"] or 0),
            "simulacoes": int(linha["simulacoes"] or 0),
            "enviados": int(linha["enviados"] or 0),
        }
    return {"horas": horas, "por_fonte": por_fonte}


def descrever_uso_fontes_odds(resumo):
    resumo = resumo or {}
    fontes = resumo.get("por_fonte") or {}
    ordem = (
        "packball", "thestatsapi", "the_odds_api", "api_football",
        "sem_odd_rastreavel",
    )
    nomes = {
        "packball": "PackBall",
        "thestatsapi": "TheStats",
        "the_odds_api": "The Odds API",
        "api_football": "API-Football",
        "sem_odd_rastreavel": "sem odd selecionada",
    }
    chaves = list(dict.fromkeys((*ordem, *sorted(fontes))))
    partes = []
    for fonte in chaves:
        item = fontes.get(fonte)
        if not item and fonte in ordem[:4]:
            item = {"avaliados": 0, "aprovados": 0, "enviados": 0}
        elif not item:
            continue
        partes.append(
            f"{nomes.get(fonte, fonte)}: avaliados={item['avaliados']}, "
            f"aprovados={item['aprovados']}, enviados={item['enviados']}"
        )
    horas = float(resumo.get("horas", 24) or 24)
    periodo = f"{horas:g}h"
    return (
        f"uso efetivo das fontes de odds ({periodo}): "
        + (" | ".join(partes) if partes else "sem candidatos")
    )


def resumir_amostragem_referencia_odds(
    conexao, estado=None, horas=24, limite_diario=30,
    maximo_por_jogo_dia=2, maximo_ciclo=2,
):
    """Resume a coleta sombra sem misturá-la ao uso efetivo dos sinais."""
    try:
        horas = max(float(horas), 0.0)
    except (TypeError, ValueError):
        horas = 24.0
    modificador = f"-{horas:g} hours"
    sombra = conexao.execute(
        """
        SELECT COUNT(*) AS mercados,
               COUNT(DISTINCT s.partida_id) AS jogos,
               MAX(s.coletado_em) AS ultima
        FROM odds o
        JOIN snapshots s ON s.id=o.snapshot_id
        WHERE o.tipo='referencia_sombra'
          AND datetime(s.coletado_em)>=datetime(
                'now', 'localtime', ?
              )
        """,
        (modificador,),
    ).fetchone()
    pares = conexao.execute(
        """
        SELECT COUNT(*) AS comparacoes,
               COUNT(DISTINCT partida_id) AS jogos
        FROM comparacoes_odds_fontes
        WHERE datetime(observado_em)>=datetime(
                'now', 'localtime', ?
              )
          AND (lower(fonte_a)='the_odds_api'
               OR lower(fonte_b)='the_odds_api')
        """,
        (modificador,),
    ).fetchone()
    auditoria_amostragem = {
        "tentativas": 0,
        "jogos": 0,
        "ofertas": 0,
        "novas": 0,
        "confirmacoes": 0,
        "contextos_posicao": 0,
        "primeira_metade": 0,
        "posicao_relativa_media": None,
        "por_estado": {},
        "preselecoes": 0,
        "preselecoes_cobertas": 0,
        "preselecoes_descartadas": 0,
        "preselecoes_evento": 0,
        "eventos_pareados_pre_reserva": 0,
        "eventos_descartados_pre_reserva": 0,
        "reservas_economizadas": 0,
        "reservas_economizadas_evento": 0,
    }
    try:
        linha_auditoria = conexao.execute(
            """
            SELECT COUNT(*) AS tentativas,
                   COUNT(DISTINCT partida_id) AS jogos,
                   SUM(CASE WHEN estado='oferta_disponivel'
                            THEN 1 ELSE 0 END) AS ofertas,
                   SUM(CASE WHEN json_extract(
                                  metadados_json, '$.tipo_amostra'
                                )='nova_partida'
                            THEN 1 ELSE 0 END) AS novas,
                   SUM(CASE WHEN json_extract(
                                  metadados_json, '$.tipo_amostra'
                                )='confirmacao_temporal'
                            THEN 1 ELSE 0 END) AS confirmacoes,
                   SUM(CASE WHEN CAST(json_extract(
                                      metadados_json, '$.posicao_fila'
                                    ) AS REAL)>0
                                  AND CAST(json_extract(
                                      metadados_json, '$.tarefas_ciclo'
                                    ) AS REAL)>0
                            THEN 1 ELSE 0 END) AS contextos_posicao,
                   SUM(CASE WHEN CAST(json_extract(
                                      metadados_json, '$.posicao_fila'
                                    ) AS REAL)>0
                                  AND CAST(json_extract(
                                      metadados_json, '$.tarefas_ciclo'
                                    ) AS REAL)>0
                                  AND 2*CAST(json_extract(
                                      metadados_json, '$.posicao_fila'
                                    ) AS REAL)<=CAST(json_extract(
                                      metadados_json, '$.tarefas_ciclo'
                                    ) AS REAL)
                            THEN 1 ELSE 0 END) AS primeira_metade,
                   AVG(CASE WHEN CAST(json_extract(
                                      metadados_json, '$.posicao_fila'
                                    ) AS REAL)>0
                                  AND CAST(json_extract(
                                      metadados_json, '$.tarefas_ciclo'
                                    ) AS REAL)>0
                            THEN CAST(json_extract(
                                      metadados_json, '$.posicao_fila'
                                    ) AS REAL)/CAST(json_extract(
                                      metadados_json, '$.tarefas_ciclo'
                                    ) AS REAL)
                       END) AS posicao_relativa_media
            FROM observacoes_fontes_odds
            WHERE lower(fonte)='the_odds_api'
              AND metodo_coleta='amostragem_referencia_sombra'
              AND datetime(consultado_em)>=datetime(
                    'now', 'localtime', ?
                  )
            """,
            (modificador,),
        ).fetchone()
        estados_auditoria = conexao.execute(
            """
            SELECT estado, COUNT(*) AS total
            FROM observacoes_fontes_odds
            WHERE lower(fonte)='the_odds_api'
              AND metodo_coleta='amostragem_referencia_sombra'
              AND datetime(consultado_em)>=datetime(
                    'now', 'localtime', ?
                  )
            GROUP BY estado
            ORDER BY total DESC, estado
            """,
            (modificador,),
        ).fetchall()
        linha_preselecao = conexao.execute(
            """
            SELECT COUNT(*) AS preselecoes,
                   SUM(CASE WHEN json_extract(
                                  metadados_json, '$.competicao_coberta'
                                )=1 THEN 1 ELSE 0 END) AS cobertas,
                   SUM(CASE WHEN json_extract(
                                  metadados_json, '$.competicao_coberta'
                                )=0 THEN 1 ELSE 0 END) AS descartadas,
                   SUM(CASE WHEN COALESCE(json_extract(
                                  metadados_json, '$.reserva_consumida'
                                ), 0)=0
                                  AND (
                                    json_extract(
                                      metadados_json,
                                      '$.competicao_coberta'
                                    )=0
                                    OR (
                                      json_extract(
                                        metadados_json,
                                        '$.preselecao_evento_executada'
                                      )=1
                                      AND COALESCE(json_extract(
                                        metadados_json,
                                        '$.evento_pareado_pre_reserva'
                                      ), 0)=0
                                    )
                                  ) THEN 1 ELSE 0 END) AS economizadas,
                   SUM(CASE WHEN json_extract(
                                  metadados_json,
                                  '$.preselecao_evento_executada'
                                )=1 THEN 1 ELSE 0 END) AS eventos,
                   SUM(CASE WHEN json_extract(
                                  metadados_json,
                                  '$.evento_pareado_pre_reserva'
                                )=1 THEN 1 ELSE 0 END) AS eventos_pareados,
                   SUM(CASE WHEN json_extract(
                                  metadados_json,
                                  '$.preselecao_evento_executada'
                                )=1
                                  AND COALESCE(json_extract(
                                  metadados_json,
                                  '$.evento_pareado_pre_reserva'
                                ), 0)=0 THEN 1 ELSE 0 END)
                       AS eventos_descartados,
                   SUM(CASE WHEN json_extract(
                                  metadados_json,
                                  '$.preselecao_evento_executada'
                                )=1
                                  AND COALESCE(json_extract(
                                  metadados_json,
                                  '$.evento_pareado_pre_reserva'
                                ), 0)=0
                                  AND COALESCE(json_extract(
                                  metadados_json,
                                  '$.reserva_consumida'
                                ), 0)=0 THEN 1 ELSE 0 END)
                       AS economizadas_evento
            FROM observacoes_fontes_odds
            WHERE lower(fonte)='the_odds_api'
              AND metodo_coleta IN (
                    'amostragem_referencia_preselecao',
                    'amostragem_referencia_sombra'
                  )
              AND json_extract(
                    metadados_json, '$.preselecao_executada'
                  )=1
              AND datetime(consultado_em)>=datetime(
                    'now', 'localtime', ?
                  )
            """,
            (modificador,),
        ).fetchone()
        auditoria_amostragem = {
            "tentativas": int(linha_auditoria["tentativas"] or 0),
            "jogos": int(linha_auditoria["jogos"] or 0),
            "ofertas": int(linha_auditoria["ofertas"] or 0),
            "novas": int(linha_auditoria["novas"] or 0),
            "confirmacoes": int(
                linha_auditoria["confirmacoes"] or 0
            ),
            "contextos_posicao": int(
                linha_auditoria["contextos_posicao"] or 0
            ),
            "primeira_metade": int(
                linha_auditoria["primeira_metade"] or 0
            ),
            "posicao_relativa_media": (
                round(float(linha_auditoria["posicao_relativa_media"]), 4)
                if linha_auditoria["posicao_relativa_media"] is not None
                else None
            ),
            "por_estado": {
                str(linha["estado"]): int(linha["total"] or 0)
                for linha in estados_auditoria
            },
            "preselecoes": int(linha_preselecao["preselecoes"] or 0),
            "preselecoes_cobertas": int(
                linha_preselecao["cobertas"] or 0
            ),
            "preselecoes_descartadas": int(
                linha_preselecao["descartadas"] or 0
            ),
            "preselecoes_evento": int(
                linha_preselecao["eventos"] or 0
            ),
            "eventos_pareados_pre_reserva": int(
                linha_preselecao["eventos_pareados"] or 0
            ),
            "eventos_descartados_pre_reserva": int(
                linha_preselecao["eventos_descartados"] or 0
            ),
            "reservas_economizadas": int(
                linha_preselecao["economizadas"] or 0
            ),
            "reservas_economizadas_evento": int(
                linha_preselecao["economizadas_evento"] or 0
            ),
        }
    except (sqlite3.OperationalError, sqlite3.DatabaseError, TypeError):
        # Bancos antigos são migrados por BancoMonitor; esta tolerância mantém
        # o status somente leitura utilizável durante a própria atualização.
        pass
    contextos_posicao = int(
        auditoria_amostragem.get("contextos_posicao", 0) or 0
    )
    primeira_metade = int(
        auditoria_amostragem.get("primeira_metade", 0) or 0
    )
    proporcao_primeira_metade = (
        primeira_metade / contextos_posicao if contextos_posicao else None
    )
    if contextos_posicao < 30:
        estado_vies_ordem = "aguardando_30_amostras"
    elif proporcao_primeira_metade >= 0.75:
        estado_vies_ordem = "concentrada_primeira_metade"
    elif proporcao_primeira_metade <= 0.25:
        estado_vies_ordem = "concentrada_segunda_metade"
    else:
        estado_vies_ordem = "sem_concentracao_extrema"
    estado = estado if isinstance(estado, dict) else {}
    amostragem = estado.get("amostragem_referencia") or {}
    contagens = (
        amostragem.get("contagens") or {}
        if amostragem.get("dia")
        == datetime.now(timezone.utc).strftime("%Y-%m-%d")
        else {}
    )
    provedor = estado.get("provedor") or {}
    circuito = estado.get("circuito") or {}
    controle_estado = estado.get("controle_estado") or {}
    try:
        bloqueado_ate = float(circuito.get("bloqueado_ate") or 0.0)
    except (TypeError, ValueError):
        bloqueado_ate = 0.0
    agora_epoch = datetime.now(timezone.utc).timestamp()
    circuito_aberto = bloqueado_ate > agora_epoch
    return {
        "horas": horas,
        "mercados_sombra": int(sombra["mercados"] or 0),
        "jogos_sombra": int(sombra["jogos"] or 0),
        "ultima_amostra": sombra["ultima"],
        "comparacoes": int(pares["comparacoes"] or 0),
        "jogos_pareados": int(pares["jogos"] or 0),
        "tentativas_auditadas": int(
            auditoria_amostragem.get("tentativas", 0) or 0
        ),
        "jogos_tentados": int(
            auditoria_amostragem.get("jogos", 0) or 0
        ),
        "ofertas_auditadas": int(
            auditoria_amostragem.get("ofertas", 0) or 0
        ),
        "novas_partidas_auditadas": int(
            auditoria_amostragem.get("novas", 0) or 0
        ),
        "confirmacoes_auditadas": int(
            auditoria_amostragem.get("confirmacoes", 0) or 0
        ),
        "contextos_posicao": contextos_posicao,
        "posicao_relativa_media": auditoria_amostragem.get(
            "posicao_relativa_media"
        ),
        "proporcao_primeira_metade": (
            round(proporcao_primeira_metade, 4)
            if proporcao_primeira_metade is not None else None
        ),
        "estado_vies_ordem": estado_vies_ordem,
        "tentativas_por_estado": auditoria_amostragem.get(
            "por_estado", {}
        ),
        "preselecoes": int(
            auditoria_amostragem.get("preselecoes", 0) or 0
        ),
        "preselecoes_cobertas": int(
            auditoria_amostragem.get("preselecoes_cobertas", 0) or 0
        ),
        "preselecoes_descartadas": int(
            auditoria_amostragem.get(
                "preselecoes_descartadas", 0
            ) or 0
        ),
        "preselecoes_evento": int(
            auditoria_amostragem.get("preselecoes_evento", 0) or 0
        ),
        "eventos_pareados_pre_reserva": int(
            auditoria_amostragem.get(
                "eventos_pareados_pre_reserva", 0
            ) or 0
        ),
        "eventos_descartados_pre_reserva": int(
            auditoria_amostragem.get(
                "eventos_descartados_pre_reserva", 0
            ) or 0
        ),
        "reservas_economizadas": int(
            auditoria_amostragem.get("reservas_economizadas", 0) or 0
        ),
        "reservas_economizadas_evento": int(
            auditoria_amostragem.get(
                "reservas_economizadas_evento", 0
            ) or 0
        ),
        "dia_controle": amostragem.get("dia"),
        "reservas_dia": int(amostragem.get("reservas", 0) or 0),
        "limite_diario": int(limite_diario or 0),
        "jogos_distintos_dia": len(contagens),
        "maior_uso_jogo_dia": max(
            (int(valor) for valor in contagens.values()), default=0
        ),
        "maximo_por_jogo_dia": int(maximo_por_jogo_dia or 0),
        "confirmacoes_maximo_ciclo": max(int(maximo_ciclo or 0) - 1, 0),
        "creditos_restantes": provedor.get("restante"),
        "circuito_aberto": circuito_aberto,
        "circuito_falhas": int(
            circuito.get("falhas_consecutivas", 0) or 0
        ),
        "circuito_restante_segundos": round(
            max(bloqueado_ate - agora_epoch, 0.0), 3
        ),
        "circuito_motivo": circuito.get("motivo"),
        "controle_estado_saudavel": controle_estado.get("saudavel"),
        "controle_estado_origem": controle_estado.get("origem"),
        "controle_estado_recuperado": bool(
            controle_estado.get("recuperado", False)
        ),
        "controle_estado_backup": bool(
            controle_estado.get("backup", False)
        ),
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def descrever_amostragem_referencia_odds(resumo):
    resumo = resumo or {}
    restantes = resumo.get("creditos_restantes")
    restantes = "-" if restantes is None else str(int(restantes))
    controle_saudavel = resumo.get("controle_estado_saudavel")
    if controle_saudavel is True:
        controle_descricao = "saudavel"
    elif controle_saudavel is False:
        controle_descricao = "bloqueado"
    else:
        controle_descricao = "nao informado"
    controle_origem = resumo.get("controle_estado_origem") or "-"
    posicao_media = resumo.get("posicao_relativa_media")
    posicao_media_texto = (
        "-" if posicao_media is None else f"{float(posicao_media) * 100:.1f}%"
    )
    return (
        "referência independente de odds (somente sombra): "
        f"reservas hoje={int(resumo.get('reservas_dia', 0) or 0)}/"
        f"{int(resumo.get('limite_diario', 30) or 0)} | "
        "jogos distintos/maior repetição hoje="
        f"{int(resumo.get('jogos_distintos_dia', 0) or 0)}/"
        f"{int(resumo.get('maior_uso_jogo_dia', 0) or 0)}"
        f" (máx={int(resumo.get('maximo_por_jogo_dia', 0) or 0)}) | "
        "confirmações máximas/ciclo="
        f"{int(resumo.get('confirmacoes_maximo_ciclo', 0) or 0)} | "
        "tentativas auditadas/jogos="
        f"{int(resumo.get('tentativas_auditadas', 0) or 0)}/"
        f"{int(resumo.get('jogos_tentados', 0) or 0)}"
        " (novas/confirmações="
        f"{int(resumo.get('novas_partidas_auditadas', 0) or 0)}/"
        f"{int(resumo.get('confirmacoes_auditadas', 0) or 0)}) | "
        f"posição relativa média={posicao_media_texto} | "
        f"viés da fila={resumo.get('estado_vies_ordem') or '-'} | "
        "pré-seleções cobertas/descartadas/reservas economizadas="
        f"{int(resumo.get('preselecoes_cobertas', 0) or 0)}/"
        f"{int(resumo.get('preselecoes_descartadas', 0) or 0)}/"
        f"{int(resumo.get('reservas_economizadas', 0) or 0)} | "
        "eventos pareados/descartados/economia específica="
        f"{int(resumo.get('eventos_pareados_pre_reserva', 0) or 0)}/"
        f"{int(resumo.get('eventos_descartados_pre_reserva', 0) or 0)}/"
        f"{int(resumo.get('reservas_economizadas_evento', 0) or 0)} | "
        f"mercados/jogos {float(resumo.get('horas', 24) or 24):g}h="
        f"{int(resumo.get('mercados_sombra', 0) or 0)}/"
        f"{int(resumo.get('jogos_sombra', 0) or 0)} | "
        "comparações/jogos pareados="
        f"{int(resumo.get('comparacoes', 0) or 0)}/"
        f"{int(resumo.get('jogos_pareados', 0) or 0)} | "
        f"créditos restantes={restantes} | "
        "circuito="
        f"{'aberto' if resumo.get('circuito_aberto') else 'fechado'}"
        f" (falhas={int(resumo.get('circuito_falhas', 0) or 0)}) | "
        f"estado persistente={controle_origem}/{controle_descricao} | "
        "altera HT/FT=não | Telegram=não"
    )


def descrever_comparacao_gol_ft_v2_v3(
    historico_v2, controle_v2, comparacao
):
    """Expõe o reteste contemporâneo sem misturar a V2 congelada."""
    historico_v2 = historico_v2 or {}
    controle_v2 = controle_v2 or {}
    comparacao = comparacao or {}
    v2 = comparacao.get("v2_controle") or {}
    v3 = comparacao.get("v3") or {}

    def roi_texto(item):
        roi = item.get("roi")
        return "-" if roi is None else f"{float(roi) * 100:+.1f}%"

    def resumo_braco(nome, item):
        return (
            f"{nome}: coorte={int(item.get('candidatos_coorte', 0) or 0)}/"
            f"{int(controle_v2.get('tamanho_coorte_fixa', 75) or 75)} | "
            f"resultados={int(item.get('avaliadas', 0) or 0)} | "
            f"pendentes={int(item.get('pendentes', 0) or 0)} | "
            f"G/R={int(item.get('greens', 0) or 0)}/"
            f"{int(item.get('reds', 0) or 0)} | ROI={roi_texto(item)}"
        )

    avaliadas_v2 = int(v2.get("avaliadas", 0) or 0)
    avaliadas_v3 = int(v3.get("avaliadas", 0) or 0)
    roi_v2 = v2.get("roi")
    roi_v3 = v3.get("roi")
    if (
        avaliadas_v2 > 0
        and avaliadas_v3 > 0
        and roi_v2 is not None
        and roi_v3 is not None
    ):
        delta = (float(roi_v3) - float(roi_v2)) * 100
        comparacao_texto = f"diferença descritiva V3-V2={delta:+.1f} pp"
    else:
        comparacao_texto = "diferença descritiva: aguardando os dois braços"

    inicio = comparacao.get("iniciado_em") or controle_v2.get("iniciado_em")
    historico_avaliadas = int(historico_v2.get("avaliadas", 0) or 0)
    historico_greens = int(historico_v2.get("greens", 0) or 0)
    historico_reds = int(historico_v2.get("reds", 0) or 0)
    return "\n".join((
        "  V2 histórica gol_ft — congelada: "
        f"resultados={historico_avaliadas} | "
        f"G/R={historico_greens}/{historico_reds} | "
        f"ROI={roi_texto(historico_v2)} | não recebe jogos novos",
        "  reteste simultâneo Gol FT "
        f"(somente sombra; desde {inicio or '-'}):",
        "    " + resumo_braco("V2-controle", v2),
        "    " + resumo_braco("V3", v3),
        "    " + comparacao_texto
        + " | Telegram oficial=não | promoção automática=não",
    ))


def descrever_challenger_v2_ft(resumo):
    """Formata a coorte challenger sem sugerir aprovação antecipada."""
    resumo = resumo or {}
    roi = resumo.get("roi")
    roi_texto = "-" if roi is None else f"{float(roi) * 100:+.1f}%"
    intervalo = resumo.get("intervalo_roi_95")
    if intervalo is None:
        ic_texto = "-"
    else:
        ic_texto = (
            f"[{float(intervalo[0]) * 100:+.1f}%, "
            f"{float(intervalo[1]) * 100:+.1f}%]"
        )
    return (
        "  challenger V2 Gol FT — somente sombra: "
        f"coorte={int(resumo.get('candidatos_coorte', 0) or 0)}/"
        f"{int(resumo.get('tamanho_coorte_fixa', 75) or 75)} | "
        f"válidos={int(resumo.get('avaliadas', 0) or 0)}/"
        f"{int(resumo.get('minimo_resultados_validos', 70) or 70)} | "
        f"G/R/P={int(resumo.get('greens', 0) or 0)}/"
        f"{int(resumo.get('reds', 0) or 0)}/"
        f"{int(resumo.get('pendentes', 0) or 0)} | "
        f"lucro={float(resumo.get('lucro_unidades', 0) or 0):+.2f}u | "
        f"ROI={roi_texto} | IC95={ic_texto} | "
        f"julgamento={resumo.get('decisao_estatistica', '-')} | "
        "Telegram=não | promoção automática=não"
    )


def descrever_proximo_gol_balanceado(resumo):
    """Expõe volume e evidência do braço menos rígido sem promovê-lo."""
    resumo = resumo or {}
    funil = resumo.get("funil_origem_v10f") or {}
    candidatos = int(resumo.get("candidatos", 0) or 0)
    alvo = int(resumo.get("tamanho_coorte", 40) or 40)
    roi = resumo.get("roi")
    roi_texto = "-" if roi is None else f"{float(roi) * 100:+.1f}%"
    cadencia = funil.get("candidatos_por_24h")
    cadencia_texto = (
        "-" if cadencia is None else f"{float(cadencia):.2f}"
    )
    breaker = resumo.get("circuit_breaker") or {}
    grupo_liberado = resumo.get("grupo_liberado")
    grupo_texto = (
        "ativo" if grupo_liberado is True
        else "pausado" if grupo_liberado is False
        else "não auditado"
    )
    return (
        "  Próximo Gol balanceado — grupo de teste: "
        f"estado={resumo.get('estado') or 'não registrado'} | "
        f"coorte={candidatos}/{alvo} | "
        f"G/R/P={int(resumo.get('greens', 0) or 0)}/"
        f"{int(resumo.get('reds', 0) or 0)}/"
        f"{int(resumo.get('pendentes', 0) or 0)} | "
        f"ROI={roi_texto} | candidatos/24h={cadencia_texto} | "
        f"gargalo={funil.get('gargalo_principal_interno') or '-'} | "
        f"julgamento={resumo.get('decisao') or 'aguardando_amostra_futura'} | "
        f"grupo={grupo_texto} | breaker={breaker.get('estado') or '-'} | "
        "Telegram oficial=não | promoção automática=não"
    )


def descrever_funil_marginal_proximo_gol(resumo):
    """Mostra os gargalos reais mesmo quando o funil cumulativo zera."""
    resumo = resumo or {}
    if resumo.get("erro"):
        return (
            "  Próximo Gol balanceado — diagnóstico marginal: "
            f"indisponível ({resumo['erro']})"
        )
    total = int(resumo.get("estados_independentes", 0) or 0)
    passagens = resumo.get("passagens_marginais") or {}
    distancia = resumo.get("distancia_minima_observada")
    distancia_texto = "-" if distancia is None else str(int(distancia))
    bloqueios_adicionais = resumo.get(
        "bloqueios_adicionais_estados_tecnicamente_prontos"
    ) or {}
    bloqueio_texto = ",".join(
        f"{motivo}={quantidade}"
        for motivo, quantidade in bloqueios_adicionais.items()
    ) or "-"
    auditoria = resumo.get("auditoria_contrafactual") or {}
    auditoria_texto = (
        f"{int(auditoria.get('greens', 0) or 0)}/"
        f"{int(auditoria.get('reds', 0) or 0)}/"
        f"{int(auditoria.get('pendentes', 0) or 0)}"
    )
    return (
        "  Próximo Gol balanceado — diagnóstico marginal: "
        f"estados={total} | menor distância={distancia_texto} | "
        f"odd curta={int(passagens.get('odd_curta', 0) or 0)}/{total} | "
        "pressão balanceada="
        f"{int(passagens.get('pressao_balanceada', 0) or 0)}/{total} | "
        f"gargalo={resumo.get('gargalo_tecnico_marginal') or '-'} | "
        f"bloqueio de risco nos prontos={bloqueio_texto} | "
        f"auditoria exploratória G/R/P={auditoria_texto} | "
        "resultados não usados no funil | efeito operacional=nenhum"
    )


def descrever_quase_candidatos_proximo_gol(resumo):
    """Expõe as coortes causais sem sugerir que já existe vantagem."""
    resumo = resumo or {}
    if resumo.get("saudavel") is False:
        return (
            "  Próximo Gol — quase-candidatos prospectivos: "
            f"indisponível ({resumo.get('estado') or 'erro'})"
        )
    bracos = resumo.get("bracos") or {}

    def trecho(chave, rotulo):
        item = bracos.get(chave) or {}
        roi = item.get("roi")
        roi_texto = "-" if roi is None else f"{float(roi) * 100:+.1f}%"
        return (
            f"{rotulo}={int(item.get('candidatos', 0) or 0)}/"
            f"{int(item.get('tamanho_coorte', 60) or 60)} "
            f"G/R/P={int(item.get('greens', 0) or 0)}/"
            f"{int(item.get('reds', 0) or 0)}/"
            f"{int(item.get('pendentes', 0) or 0)} ROI={roi_texto} "
            f"decisão={item.get('decisao') or 'aguardando_amostra_futura'}"
        )

    return (
        "  Próximo Gol — quase-candidatos prospectivos: "
        f"estado={resumo.get('estado') or 'não registrado'} | "
        f"{trecho('odd_165_199', 'odd 1,65–1,99')} | "
        f"{trecho('atividade_com_chute', 'atividade+chute')} | "
        "seleção antes do resultado=sim | Telegram=não | "
        "promoção automática=não"
    )


def descrever_quase_candidatos_gol_ft(resumo):
    """Mostra a busca causal de melhorias sem confundir com sinais ativos."""
    resumo = resumo or {}
    if resumo.get("saudavel") is False:
        return (
            "  Gol FT — quase-candidatos prospectivos: "
            f"indisponível ({resumo.get('estado') or 'erro'})"
        )
    bracos = resumo.get("bracos") or {}

    def trecho(chave, rotulo):
        item = bracos.get(chave) or {}
        roi = item.get("roi")
        roi_texto = "-" if roi is None else f"{float(roi) * 100:+.1f}%"
        return (
            f"{rotulo}={int(item.get('candidatos', 0) or 0)}/"
            f"{int(item.get('tamanho_coorte', 60) or 60)} "
            f"G/R/P={int(item.get('greens', 0) or 0)}/"
            f"{int(item.get('reds', 0) or 0)}/"
            f"{int(item.get('pendentes', 0) or 0)} ROI={roi_texto} "
            f"decisão={item.get('decisao') or 'aguardando_amostra_futura'}"
        )

    return (
        "  Gol FT — quase-candidatos prospectivos: "
        f"estado={resumo.get('estado') or 'não registrado'} | "
        f"{trecho('minuto_61_75', 'minuto 61–75')} | "
        f"{trecho('historico_8_11', 'histórico 8–11')} | "
        "um filtro alterado por braço=sim | seleção antes do resultado=sim | "
        "Telegram=não | promoção automática=não"
    )


def descrever_validacao_gols_antecipados(resumo):
    linhas = [
        "  gols antecipados — validação prospectiva imutável: "
        f"desde={resumo.get('registrado_em') or '-'} | "
        "grupo de análises=ativo | oficial=não"
    ]
    rotulos = {
        "gol-ht-antecipado-faixa-historica-v2": "Gol HT antecipado",
        "gol-ft-antecipado-pre-live-v1": "Gol FT inicial",
        "gol-ft-antecipado-2t-faixa-historica-v1": "Gol FT 2º tempo",
    }
    for versao, item in (resumo.get("por_braco") or {}).items():
        historico = item.get("historico_observacional") or {}
        roi = item.get("roi")
        roi_texto = "-" if roi is None else f"{float(roi) * 100:+.1f}%"
        linhas.append(
            f"    {rotulos.get(versao, versao)}: prospectiva="
            f"{int(item.get('candidatos_coorte', 0) or 0)}/"
            f"{int(item.get('tamanho_coorte', 100) or 100)} | "
            f"G/R/P={int(item.get('greens', 0) or 0)}/"
            f"{int(item.get('reds', 0) or 0)}/"
            f"{int(item.get('pendentes', 0) or 0)} | ROI={roi_texto} | "
            f"julgamento={item.get('decisao_estatistica', '-')} | "
            "histórico anterior observacional="
            f"{int(historico.get('greens', 0) or 0)}G/"
            f"{int(historico.get('reds', 0) or 0)}R"
        )
    return "\n".join(linhas)


def descrever_top_criterios_gols(resumo):
    linhas = [
        "  Top HT/FT casa-fora — comparação prospectiva: "
        "envio ativo no Telegram | validação separada | métodos anteriores preservados"
    ]
    for periodo, rotulo in (("ht", "Top HT"), ("ft", "Top FT")):
        item = (resumo or {}).get(periodo) or {}
        roi = item.get("roi")
        roi_texto = "-" if roi is None else f"{float(roi) * 100:+.1f}%"
        linhas.append(
            f"    {rotulo}: amostra={int(item.get('candidatos', 0) or 0)}/100 | "
            f"G/R/P={int(item.get('greens', 0) or 0)}/"
            f"{int(item.get('reds', 0) or 0)}/"
            f"{int(item.get('pendentes', 0) or 0)} | ROI={roi_texto} | "
            f"decisão={item.get('decisao', 'aguardando_amostra_futura')}"
        )
    return "\n".join(linhas)


def resumir_calibracoes_arquivadas(
    conexao, regra_ativa=VERSAO_REGRAS, regras_ativas_por_mercado=None
):
    """Expõe checkpoints antigos e identifica exceções ainda em uso."""
    linhas = conexao.execute(
        """
        SELECT regra_versao, mercado, amostra, ativa, atualizado_em,
               modelo_json
        FROM calibracoes
        WHERE regra_versao IS NOT NULL AND regra_versao<>?
        ORDER BY regra_versao, mercado
        """,
        (regra_ativa,),
    ).fetchall()
    regras_ativas_por_mercado = dict(regras_ativas_por_mercado or {})
    versoes = {}
    for linha in linhas:
        versao = linha["regra_versao"]
        item = versoes.setdefault(
            versao,
            {
                "regra_versao": versao,
                "mercados": {},
                "atualizado_em": None,
                "alguma_ativa": False,
                "historico_vinculado": True,
                "mercados_em_uso": [],
            },
        )
        mercado = linha["mercado"]
        item["mercados"][mercado] = int(linha["amostra"] or 0)
        if regras_ativas_por_mercado.get(mercado) == versao:
            item["mercados_em_uso"].append(mercado)
        item["alguma_ativa"] = (
            item["alguma_ativa"] or bool(linha["ativa"])
        )
        atualizado_em = linha["atualizado_em"]
        if (
            atualizado_em
            and (
                item["atualizado_em"] is None
                or atualizado_em > item["atualizado_em"]
            )
        ):
            item["atualizado_em"] = atualizado_em
        try:
            modelo = json.loads(linha["modelo_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            modelo = {}
        modelo_json = serializar_modelo_calibracao(modelo)
        modelo_hash = hash_modelo_calibracao(modelo)
        vinculado = conexao.execute(
            """
            SELECT 1 FROM historico_calibracoes
            WHERE mercado=? AND regra_versao=? AND amostra=? AND ativa=?
              AND modelo_hash=? AND modelo_json=?
            LIMIT 1
            """,
            (
                linha["mercado"],
                linha["regra_versao"],
                linha["amostra"],
                linha["ativa"],
                modelo_hash,
                modelo_json,
            ),
        ).fetchone() is not None
        item["historico_vinculado"] = (
            item["historico_vinculado"] and vinculado
        )
    return list(versoes.values())


def imprimir_calibracoes_arquivadas(
    conexao, regra_ativa=VERSAO_REGRAS, regras_ativas_por_mercado=None
):
    versoes = resumir_calibracoes_arquivadas(
        conexao, regra_ativa, regras_ativas_por_mercado
    )
    print(
        "calibrações preservadas e versões específicas por mercado:"
    )
    if not versoes:
        print("  nenhuma")
        return
    for item in versoes:
        mercados = ", ".join(
            f"{mercado}={amostra}"
            for mercado, amostra in item["mercados"].items()
            if amostra
        ) or "sem amostra"
        mercados_em_uso = sorted(set(item.get("mercados_em_uso") or ()))
        uso = (
            "sim (" + ",".join(mercados_em_uso) + ")"
            if mercados_em_uso else "não"
        )
        print(
            f"  {item['regra_versao']}: {mercados} | "
            f"checkpoint={item['atualizado_em'] or '-'} | "
            "histórico imutável="
            f"{'vinculado' if item['historico_vinculado'] else 'inválido'} | "
            f"uso na regra ativa={uso}"
        )


def carregar_historico_drift_status(
    caminho, regra_versao=VERSAO_REGRAS, drift_atual=None
):
    caminho = Path(caminho)
    if not caminho.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
            "total": 0,
            "mercados": 0,
        }
    conexao = None
    try:
        conexao = sqlite3.connect(
            caminho.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=10,
        )
        resumo = (
            auditar_historico_drift_simulacoes(
                conexao, drift_atual, regra_versao
            )
            if drift_atual is not None
            else resumir_historico_drift_simulacoes(
                conexao, regra_versao
            )
        )
        return {
            "saudavel": True,
            "estado": resumo.get("estado") or "ativo",
            "motivo": None,
            **resumo,
        }
    except (OSError, sqlite3.Error) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "historico_drift_indisponivel",
            "erro": type(erro).__name__,
            "total": 0,
            "mercados": 0,
        }
    finally:
        if conexao is not None:
            conexao.close()


def imprimir_cortes_sombra(validacao):
    cortes_sombra = (validacao or {}).get("cortes_sombra") or {}
    print(
        "supervisao de cortes temporais: "
        f"{cortes_sombra.get('versao') or '-'} | "
        "aplicacao automatica=nao | aptos para revisao="
        f"{','.join(cortes_sombra.get('mercados_aptos_para_revisao') or []) or '-'}"
    )
    for mercado, avaliacao in (
        cortes_sombra.get("avaliacoes") or {}
    ).items():
        if avaliacao.get("estado") != "avaliavel":
            continue
        corte = (
            avaliacao.get("corte_escolhido_no_desenvolvimento")
            or {}
        )
        metricas = avaliacao.get("metricas_validacao_corte") or {}
        limiar = corte.get("limiar")
        print(
            f"  pista exploratória {mercado}: "
            f"{corte.get('feature') or '-'} "
            f"{corte.get('operador') or '-'} "
            f"{limiar if limiar is not None else '-'} | "
            f"validacao n={metricas.get('amostra', 0)} | "
            f"ROI={metricas.get('roi')} | apto para hipótese="
            f"{'sim' if avaliacao.get('apto_para_alterar_regra') else 'nao'} | "
            "cortes explorados="
            f"{avaliacao.get('candidatos_explorados', 0)} | "
            "valor confirmatório=não | exige prospectiva="
            f"{'sim' if avaliacao.get('requer_validacao_prospectiva') else 'nao'}"
        )


def imprimir_hipoteses_sombra(caminho):
    conexao = None
    try:
        conexao = sqlite3.connect(
            Path(caminho).resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=10,
        )
        conexao.row_factory = sqlite3.Row
        resumo = avaliar_hipoteses_sombra_ativas(
            conexao,
            {
                mercado: versao_regra_para_mercado(mercado)
                for mercado in MERCADOS_CALIBRADOS
            },
        )
        for item in resumo["avaliacoes"]:
            selecionada = item["selecionada"]
            controle = item.get("controle_excluido") or {}
            descricao_corte = item.get("descricao_corte") or (
                f"{item.get('feature')} {item.get('operador')} "
                f"{float(item.get('limiar')):g}"
            )
            print(
                f"hipotese sombra {item['mercado']}: "
                f"id={item.get('identificador') or '-'} | "
                f"desde={item.get('iniciado_em') or '-'} | "
                f"{descricao_corte} | estado={item['estado']} | "
                f"resultados novos={selecionada['amostra']}/"
                f"{item['minimo_resultados']} | "
                f"aguardando resultado="
                f"{item.get('pendentes_resultado', 0)} "
                f"(corte={item.get('pendentes_selecionados', 0)}, "
                f"controle={item.get('pendentes_controle', 0)}) | "
                f"faltam={item['faltam']} | "
                f"ROI={selecionada.get('roi')} | "
                f"controle={controle.get('amostra', 0)}/"
                f"{item.get('minimo_controle', 0)} | "
                f"faltam controle={item.get('faltam_controle', 0)} | "
                "delta ROI corte-controle="
                f"{item.get('delta_roi_selecionada_controle')} | "
                f"IC95={item.get('intervalo_delta_roi_95')} | "
                f"politica={item.get('versao_avaliacao') or '-'} | "
                "aplicacao automatica=nao"
            )
    except (OSError, sqlite3.Error) as erro:
        print(
            "hipoteses sombra: indisponiveis | erro="
            f"{type(erro).__name__}"
        )
    finally:
        if conexao is not None:
            conexao.close()


def descrever_autostart(autostart):
    autostart = autostart or {}
    if (
        autostart.get("instalada")
        and autostart.get("saudavel")
        and autostart.get("origem_evidencia")
        == "execucao_agendada_recente"
    ):
        heartbeat = autostart.get("heartbeat") or {}
        idade = heartbeat.get("idade_minutos")
        idade_texto = f"{idade}min" if idade is not None else "recente"
        definicao = heartbeat.get("definicao_tarefa") or {}
        prova_definicao = (
            "; definição e bateria comprovadas"
            if (
                definicao.get("saudavel")
                and definicao.get("consulta_direta")
                and definicao.get("permite_inicio_em_bateria") is True
                and definicao.get("continua_em_bateria") is True
            )
            else ""
        )
        return (
            "instalada; execução agendada confirmada "
            f"há {idade_texto}{prova_definicao}"
        )
    if not autostart.get("consultavel", True):
        return "consulta direta indisponível; sem prova recente"
    if autostart.get("instalada") and not autostart.get("saudavel"):
        return "instalada, porém inconsistente"
    return "instalada" if autostart.get("instalada") else "não instalada"


def descrever_escanteios_ft_asiatico(prontidao, estado_odds_api):
    componente = (
        (prontidao.get("componentes") or {})
        .get("mercados", {})
        .get("escanteios_ft_asiatico", {})
    )
    evidencias = componente.get("evidencias") or {}
    bet_32 = (
        (estado_odds_api.get("por_bet") or {}).get("32") or {}
    )
    fonte = (
        "comprovada"
        if evidencias.get("fonte_comprovada")
        else "não comprovada"
    )
    resolvidos = int(evidencias.get("resultados_resolvidos") or 0)
    faltam = int(evidencias.get("faltam_resultados_reais") or 0)
    total_meta = resolvidos + faltam
    oficial = "liberado" if componente.get("pronto") else "bloqueado"
    motivo = (
        "mercado calibrado"
        if componente.get("pronto")
        else (
            "aguardando calibração"
            if evidencias.get("fonte_comprovada")
            else "aguardando fonte real"
        )
    )
    return (
        "escanteios asiáticos FT: fonte API-Football bet 32="
        f"{fonte} | ofertas anexadas="
        f"{int(bet_32.get('ofertas_anexadas') or 0)} | "
        f"última={bet_32.get('ultima_oferta_anexada_em') or '-'} | "
        f"amostra independente={resolvidos}/{total_meta} | "
        f"faltam={faltam} | sinal oficial={oficial} ({motivo})"
    )


def imprimir_conclusao_experimento_filtro(validacao):
    auditoria = validacao.get("experimento_filtro") or {}
    conclusao = (
        validacao.get("conclusao_filtro_simulacoes")
        or auditoria.get("conclusao")
        or {}
    )
    if not conclusao:
        print(
            "conclusão imutável do filtro: aguardando amostra mínima | "
            "filtro promovido=não"
        )
        return
    evidencia = conclusao.get("evidencia") or {}
    favoravel = conclusao.get("decisao") == "evidencia_favoravel"
    print(
        "conclusão imutável do filtro: "
        f"{'vantagem comprovada' if favoravel else 'vantagem não comprovada'} "
        "| congelada=sim | filtro promovido="
        f"{'apto para revisão manual' if favoravel else 'não'} | "
        f"versão={conclusao.get('versao') or '-'} | "
        f"concluída em={conclusao.get('concluido_em') or '-'} | "
        "amostras enviadas/filtradas="
        f"{evidencia.get('amostra_enviadas', 0)}/"
        f"{evidencia.get('amostra_filtradas', 0)} | "
        f"delta ROI={evidencia.get('delta_roi')} | "
        f"IC95={evidencia.get('intervalo_delta_roi_95')}"
    )
    print(
        "  resultados posteriores não reabrem este experimento; "
        "nova tentativa exige nova versão registrada"
    )


def imprimir_diversidade_calibracao(validacao):
    diversidade = validacao.get("diversidade_calibracao") or {}
    if not diversidade:
        print("diversidade da calibração: indisponível")
        return
    print("diversidade da amostra oficial:")
    for mercado, item in diversidade.items():
        amostra = int(item.get("amostra", 0) or 0)
        dias = int(item.get("dias_distintos", 0) or 0)
        ligas = int(item.get("ligas_distintas", 0) or 0)
        minimo_dias = int(item.get("minimo_dias", 0) or 0)
        minimo_ligas = int(item.get("minimo_ligas", 0) or 0)
        print(
            f"  {mercado}: estado={item.get('estado') or '-'} | "
            f"amostra={amostra}/100 | dias={dias}/{minimo_dias} | "
            f"ligas={ligas}/{minimo_ligas} | oficial="
            f"{'apto' if item.get('pronto') else 'bloqueado'}"
        )


def configurar_saida_terminal(stream=None):
    """Evita que simbolos do relatorio derrubem terminais Windows CP1252."""
    stream = stream or sys.stdout
    reconfigurar = getattr(stream, "reconfigure", None)
    if not callable(reconfigurar):
        return False
    try:
        reconfigurar(encoding="utf-8", errors="replace")
    except (OSError, TypeError, ValueError):
        return False
    return True


def main():
    configurar_saida_terminal()
    load_dotenv(PASTA / ".env")
    modo_manutencao = ler_modo_manutencao(PASTA)
    configuracao = validar_configuracao(os.environ)
    cliente_thestatsapi = TheStatsAPI(PASTA)
    diagnostico_thestatsapi = cliente_thestatsapi.diagnostico()
    cobertura_thestatsapi = {}
    print("CONFIGURAÇÃO SEGURA")
    print(f"válida: {'sim' if configuracao['valida'] else 'não'}")
    for recurso, ativo in configuracao["recursos"].items():
        print(f"  {recurso}: {'configurado' if ativo else 'indisponível'}")
    for erro in configuracao["erros"]:
        print(f"  erro: {erro}")
    for aviso in configuracao["avisos"]:
        print(f"  aviso: {aviso}")
    api = configuracao["api"]
    print(
        "  franquia API-Football: "
        f"{api['limite_diario']} por dia | "
        f"limite seguro={api['limite_diario_seguro']} | "
        f"reserva={api['reserva_diaria']}"
    )
    print()
    banco = BancoMonitor(PASTA / "monitor_packball.db")
    resumos_resgate_qualidade = {}
    try:
        print("STATUS DO BOT PACKBALL")
        print(
            "modo operacional: "
            + (
                "manutenção solicitada | motivo="
                f"{modo_manutencao.get('motivo')} | desde="
                f"{modo_manutencao.get('solicitado_em') or '-'}"
                if modo_manutencao.get("ativo")
                else "produção contínua"
            )
        )
        acesso_packball = verificar_acesso_packball(
            PASTA / "packball_acesso_estado.json"
        )
        print(
            "protecao de acesso PackBall: "
            + (
                "pausa ativa | restante="
                f"{acesso_packball['restante_segundos']:.0f}s | motivo="
                f"{acesso_packball.get('motivo') or '-'}"
                if acesso_packball["ativo"]
                else "liberada"
            )
        )
        custodia_cotacao = resumir_custodia_cotacao_oficial(
            banco.conexao
        )
        print(
            "custódia da cotação oficial: "
            f"{custodia_cotacao['estado']} | "
            "fonte/casa exigida="
            f"{custodia_cotacao['fonte_exigida']}/"
            f"{custodia_cotacao['bookmaker_exigida']} | "
            "auditados/aptos/bloqueados="
            f"{custodia_cotacao['sinais_analisados']}/"
            f"{custodia_cotacao['aptos']}/"
            f"{custodia_cotacao['bloqueados']} | "
            "bloqueios no gateway="
            f"{custodia_cotacao['bloqueios_gateway']} | "
            "simulações afetadas=não"
        )
        escanteios_executavel = resumir_validacao_escanteios_executavel(
            banco.conexao
        )
        custodia_escanteios = (
            escanteios_executavel.get("custodia_cotacao") or {}
        )
        exclusoes_escanteios = custodia_escanteios.get("exclusoes") or {}
        print(
            "validação executável dos escanteios FT: "
            f"{escanteios_executavel.get('estado')} | "
            "fonte/casa="
            f"{custodia_escanteios.get('fonte_exigida', 'betsapi')}/"
            f"{custodia_escanteios.get('bookmaker_exigida', 'bet365')} | "
            "coorte/faltam/excluídos="
            f"{escanteios_executavel.get('candidatos', 0)}/"
            f"{escanteios_executavel.get('faltam', 100)}/"
            f"{exclusoes_escanteios.get('total', 0)} | "
            f"decisão={escanteios_executavel.get('decisao')} | "
            "legado com fontes mistas decide=não"
        )
        ritmo_packball = auditar_ritmo_packball(
            PASTA / "packball_acesso_estado.json",
            exigir_distribuicao=(
                os.getenv(
                    "PACKBALL_DISTRIBUIR_NAVEGACOES", "0"
                ) == "1"
            ),
        )
        print(
            "ritmo de acesso PackBall: "
            f"{ritmo_packball['estado']} | "
            "distribuição="
            f"{'sim' if ritmo_packball.get('distribuicao_ativa') else 'não'} | "
            "intervalo efetivo/observado="
            f"{ritmo_packball.get('intervalo_efetivo_segundos')}/"
            f"{ritmo_packball.get('intervalo_minimo_observado_segundos')}s | "
            "janela="
            f"{ritmo_packball.get('navegacoes_validas', 0)}/"
            f"{ritmo_packball.get('maximo_por_janela') or '-'} | "
            "violações="
            f"{ritmo_packball.get('violacoes_intervalo', 0)} | "
            f"motivos={','.join(ritmo_packball.get('motivos') or []) or '-'}"
        )
        for nome, quantidade in banco.contagens().items():
            print(f"{nome}: {quantidade}")
        print(descrever_uso_fontes_odds(
            resumir_uso_fontes_odds(banco.conexao, horas=24)
        ))
        try:
            estado_the_odds = json.loads(
                (PASTA / "the_odds_api_estado.json").read_text(
                    encoding="utf-8"
                )
            )
        except (FileNotFoundError, OSError, TypeError, json.JSONDecodeError):
            estado_the_odds = {}
        print(descrever_amostragem_referencia_odds(
            resumir_amostragem_referencia_odds(
                banco.conexao,
                estado_the_odds,
                horas=24,
                limite_diario=(
                    ((configuracao.get("the_odds_api") or {}).get(
                        "amostragem_referencia"
                    ) or {}).get("limite_diario", 30)
                ),
                maximo_por_jogo_dia=(
                    ((configuracao.get("the_odds_api") or {}).get(
                        "amostragem_referencia"
                    ) or {}).get("maximo_por_jogo_dia", 2)
                ),
                maximo_ciclo=(
                    ((configuracao.get("the_odds_api") or {}).get(
                        "amostragem_referencia"
                    ) or {}).get("maximo_ciclo", 2)
                ),
            )
        ))
        print(descrever_historico_api_live(
            resumir_historico_api_live(banco.conexao)
        ))
        cobertura_thestatsapi = banco.resumir_cobertura_thestatsapi()

        resultados = banco.conexao.execute(
            "SELECT COUNT(*) FROM resultados_sinais"
        ).fetchone()[0]
        entregas = banco.conexao.execute(
            """
            SELECT COUNT(*) FROM entregas_alertas
            WHERE status='entregue' AND canal NOT LIKE '%:%'
            """
        ).fetchone()[0]
        entregas_teste = banco.total_alertas_teste_entregues_hoje()
        regras_operacionais = {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in mercados_calibrados_operacionais()
        }
        entregas_teste_ativas = resumir_simulacoes_ativas_hoje(
            banco.conexao,
            regras_operacionais,
        )
        print(f"resultados brutos avaliados: {resultados}")
        print(f"alertas oficiais entregues: {entregas}")
        print(
            "simulações entregues hoje (todas as versões): "
            f"{entregas_teste}"
        )
        print(
            "simulações das regras ativas hoje: "
            f"{descrever_simulacoes_ativas_hoje(entregas_teste_ativas)} | "
            "teto por versão="
            f"{os.getenv('LIMITE_DIARIO_SINAIS_TESTE', '30')} | "
            "teto global="
            f"{entregas_teste}/"
            f"{os.getenv('LIMITE_GLOBAL_SINAIS_TESTE', '45')}"
        )
        filtro_teste = {
            item["motivo"]: int(item["quantidade"])
            for item in banco.conexao.execute(
                """
                SELECT COALESCE(erro, 'motivo_ausente') AS motivo,
                       COUNT(*) AS quantidade
                FROM entregas_alertas
                WHERE canal='gateway:teste' AND status='filtrado'
                  AND date(tentado_em)=date('now', 'localtime')
                GROUP BY COALESCE(erro, 'motivo_ausente')
                """
            ).fetchall()
        }
        print(
            "filtro das melhores simulacoes: "
            f"nota>={os.getenv('PONTUACAO_MINIMA_SINAL_TESTE', '70')} | "
            f"qualidade>={os.getenv('QUALIDADE_MINIMA_SINAL_TESTE', '0')} | "
            f"descartadas hoje={sum(filtro_teste.values())} | motivos="
            + (
                ", ".join(
                    f"{motivo}={quantidade}"
                    for motivo, quantidade in sorted(filtro_teste.items())
                )
                or "-"
            )
        )
        experimento_filtro = obter_experimento_filtro(
            banco.conexao,
            VERSAO_REGRAS,
            float(os.getenv("PONTUACAO_MINIMA_SINAL_TESTE", "70")),
            float(os.getenv("QUALIDADE_MINIMA_SINAL_TESTE", "0")),
        )
        diagnostico_filtro = comparar_filtro_simulacoes(
            banco.conexao,
            VERSAO_REGRAS,
            iniciado_em=(
                experimento_filtro["iniciado_em"]
                if experimento_filtro else "9999-12-31T23:59:59"
            ),
            regra_fingerprint=fingerprint_vinculado_no_banco(
                banco.conexao, VERSAO_REGRAS
            ),
        )
        comparacao_geral = diagnostico_filtro["comparacao"].get(
            "geral",
            {
                "estado": "amostra_insuficiente",
                "decisoes_enviadas": 0,
                "decisoes_filtradas": 0,
                "pendentes_enviadas": 0,
                "pendentes_filtradas": 0,
                "amostra_enviadas": 0,
                "amostra_filtradas": 0,
                "amostra_minima_por_coorte": 30,
            },
        )
        print(
            "validacao do filtro: "
            + (
                f"{comparacao_geral['estado']}"
                if experimento_filtro else "marco_ausente"
            )
            + " | inicio="
            + (
                experimento_filtro["iniciado_em"]
                if experimento_filtro else "-"
            )
            + " | "
            "enviadas: decisoes="
            f"{comparacao_geral.get('decisoes_enviadas', 0)}, "
            f"validas={comparacao_geral['amostra_enviadas']}, "
            f"pendentes={comparacao_geral.get('pendentes_enviadas', 0)} | "
            "filtradas: decisoes="
            f"{comparacao_geral.get('decisoes_filtradas', 0)}, "
            f"validas={comparacao_geral['amostra_filtradas']}, "
            f"pendentes={comparacao_geral.get('pendentes_filtradas', 0)} | "
            "minimo por grupo="
            f"{comparacao_geral['amostra_minima_por_coorte']}"
        )
        for mercado, metricas in sorted(
            diagnostico_filtro["comparacao"].items()
        ):
            if mercado == "geral":
                continue
            filtradas = diagnostico_filtro["filtradas"].get(mercado, {})
            if not filtradas.get("decisoes"):
                continue
            print(
                f"  filtro {mercado}: {metricas['estado']} | "
                "enviadas="
                f"{metricas.get('decisoes_enviadas', 0)} decisoes/"
                f"{metricas['amostra_enviadas']} validas/"
                f"{metricas.get('pendentes_enviadas', 0)} pendentes | "
                "filtradas="
                f"{metricas.get('decisoes_filtradas', 0)} decisoes/"
                f"{metricas['amostra_filtradas']} validas/"
                f"{metricas.get('pendentes_filtradas', 0)} pendentes | "
                f"decisão={metricas.get('decisao', '-')} | "
                "delta acerto="
                + (
                    f"{metricas['delta_taxa_acerto'] * 100:+.1f}pp"
                    if metricas["delta_taxa_acerto"] is not None else "-"
                )
                + " | delta ROI="
                + (
                    f"{metricas['delta_roi'] * 100:+.1f}pp"
                    if metricas["delta_roi"] is not None else "-"
                )
                + " | IC95 delta ROI="
                + (
                    "["
                    f"{metricas['intervalo_delta_roi_95'][0] * 100:+.1f}, "
                    f"{metricas['intervalo_delta_roi_95'][1] * 100:+.1f}"
                    "]pp"
                    if metricas.get("intervalo_delta_roi_95") is not None
                    else "-"
                )
            )
        print("comparação prospectiva do filtro nas regras ativas:")
        filtros_ativos = resumir_filtros_regras_ativas(
            banco.conexao,
            mercados_calibrados_operacionais(),
        )
        if filtros_ativos:
            for resumo_filtro_ativo in filtros_ativos:
                print(descrever_filtro_regra_ativa(resumo_filtro_ativo))
        else:
            print("  nenhuma decisão prospectiva disponível")
        simulacoes = banco.conexao.execute(
            """
            SELECT
              COUNT(DISTINCT CASE WHEN r.sinal_id IS NOT NULL THEN s.id END),
              COUNT(DISTINCT CASE WHEN r.resultado IN ('green','half_green')
                                  THEN s.id END),
              COUNT(DISTINCT CASE WHEN r.resultado IN ('red','half_red')
                                  THEN s.id END),
              COUNT(DISTINCT CASE WHEN r.sinal_id IS NULL THEN s.id END)
            FROM sinais s
            JOIN entregas_alertas e ON e.sinal_id=s.id
              AND e.status='entregue' AND e.canal LIKE '%:teste'
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            """
        ).fetchone()
        print(
            "resultado das simulações (todas as versões): "
            f"avaliadas={simulacoes[0]} | greens={simulacoes[1]} | "
            f"reds={simulacoes[2]} | pendentes={simulacoes[3]}"
        )
        risco_oficial = banco.resumir_risco_alertas_oficiais()
        limites_risco = configuracao["limites"]
        breaker_reds = (
            risco_oficial["reds_consecutivos_24h"]
            >= limites_risco["limite_reds_consecutivos_oficiais"]
        )
        breaker_perda = (
            risco_oficial["perda_realizada_hoje"]
            >= limites_risco["limite_perda_diaria_oficial"]
        )
        print(
            "placar oficial green/red: "
            f"total={risco_oficial['resultados_oficiais']} | "
            f"greens={risco_oficial['greens_total']} | "
            f"reds={risco_oficial['reds_total']}"
        )
        print(
            "placar oficial de hoje: "
            f"greens={risco_oficial['greens_hoje']} | "
            f"reds={risco_oficial['reds_hoje']} | "
            f"retorno={risco_oficial['retorno_realizado_hoje']:+.2f}u"
        )
        print(
            "circuit breaker oficial: "
            f"reds consecutivos 24h="
            f"{risco_oficial['reds_consecutivos_24h']}/"
            f"{limites_risco['limite_reds_consecutivos_oficiais']} | "
            f"perda hoje={risco_oficial['perda_realizada_hoje']:.2f}/"
            f"{limites_risco['limite_perda_diaria_oficial']:.2f}u | "
            f"estado={'BLOQUEADO' if breaker_reds or breaker_perda else 'ativo'}"
        )
        placar_simulado = banco.resumir_placar_por_mercado(simulacoes=True)
        placar_oficial = banco.resumir_placar_por_mercado(simulacoes=False)
        print(
            "placar green/red por tipo de entrada "
            "(simulações: todas as versões):"
        )
        for mercado in MERCADOS_CALIBRADOS:
            simulado = placar_simulado.get(
                mercado, {"greens": 0, "reds": 0, "pendentes": 0}
            )
            oficial = placar_oficial.get(
                mercado, {"greens": 0, "reds": 0, "pendentes": 0}
            )
            print(
                f"  {ROTULOS_MERCADOS.get(mercado, mercado)}: "
                f"simulação G={simulado['greens']} "
                f"R={simulado['reds']} P={simulado['pendentes']} | "
                f"oficial G={oficial['greens']} "
                f"R={oficial['reds']} P={oficial['pendentes']}"
            )
        revisoes = banco.conexao.execute(
            """
            SELECT COUNT(DISTINCT rev.id),
                   COUNT(DISTINCT CASE
                     WHEN origem.sinal_id IS NOT NULL
                      AND rev.notificacao_status='pendente' THEN rev.id END),
                   COUNT(DISTINCT CASE
                     WHEN origem.sinal_id IS NOT NULL
                      AND rev.notificacao_status='erro' THEN rev.id END)
            FROM revisoes_resultados rev
            LEFT JOIN entregas_alertas origem
              ON origem.sinal_id=rev.sinal_id
             AND origem.status='entregue'
             AND origem.canal LIKE '%:teste'
             AND origem.canal NOT LIKE '%:teste:resultado'
            """
        ).fetchone()
        print(
            "revisões de resultados provisórios: "
            f"total={revisoes[0] or 0} | "
            f"notificações pendentes={revisoes[1] or 0} | "
            f"erros={revisoes[2] or 0}"
        )
        desempenho_simulado = resumir_simulacoes(
            banco.conexao, VERSAO_REGRAS
        )
        for mercado, metricas_teste in desempenho_simulado.items():
            if mercado == "geral":
                continue
            taxa = metricas_teste["taxa_acerto"]
            roi = metricas_teste["roi"]
            print(
                f"  simulação {mercado}: "
                f"n_independente={metricas_teste['amostra']} | "
                f"resolvidos_brutos={metricas_teste['resultados_brutos']} | "
                "excluídos_posteriores="
                f"{metricas_teste['excluidos_nao_primeira_decisao']} | "
                f"pendentes={metricas_teste['pendentes']} | "
                f"greens={metricas_teste['greens']} | "
                f"reds={metricas_teste['reds']} | "
                f"acerto={taxa * 100:.1f}%" if taxa is not None else
                f"  simulação {mercado}: n_independente=0 | "
                f"pendentes={metricas_teste['pendentes']} | "
                "excluídos_posteriores="
                f"{metricas_teste['excluidos_nao_primeira_decisao']} | "
                "aguardando resultados",
                end="",
            )
            if roi is not None:
                print(f" | ROI hipotético={roi * 100:.1f}%")
            else:
                print()
        pendencias = resumir_pendencias_resultados(banco.conexao)
        mercados_pendentes = ", ".join(
            f"{mercado}={quantidade}"
            for mercado, quantidade in pendencias["por_mercado"].items()
        ) or "-"
        idade_pendente = pendencias["idade_mais_antiga_minutos"]
        print(
            "pendências de resultado: "
            f"sinais={pendencias['sinais']} | "
            f"partidas={pendencias['partidas']} | "
            f"com API={pendencias['partidas_com_api']} | "
            "somente PackBall="
            f"{pendencias['partidas_somente_packball']} | "
            f"idade>180min={pendencias['sinais_acima_180_minutos']} | "
            "idade máxima="
            f"{idade_pendente if idade_pendente is not None else '-'}min"
        )
        print(
            "  tentativas: partidas com="
            f"{pendencias['partidas_com_tentativa']} | sem="
            f"{pendencias['partidas_sem_tentativa']} | "
            f"mercados: {mercados_pendentes}"
        )
        validacao_runtime_odds = (
            ler_estado(PASTA / "watchdog_estado.json").get("validacao") or {}
        )
        periodos = diagnosticar_fontes_odds_periodos(
            resumir_odds_escanteios_periodos(banco.conexao),
            validacao_runtime_odds.get("catalogo_odds_live") or {},
            validacao_runtime_odds.get("estado_odds_api") or {},
        )
        print("mapeamento de escanteios asiáticos por tempo:")
        for periodo, dados_periodo in periodos.items():
            estado = "detectado" if dados_periodo["mapeada"] else "não detectado"
            linhas_texto = ", ".join(
                f"{linha:g}" for linha in dados_periodo["linhas_asiaticas"]
            ) or "-"
            fontes_texto = ", ".join(
                dados_periodo.get("fontes") or []
            ) or "-"
            print(
                f"  {periodo}: {estado} | asiáticas="
                f"{dados_periodo['asiaticas']} | exactly="
                f"{dados_periodo['exactly']} | linhas={linhas_texto} | "
                f"fontes={fontes_texto} | "
                f"diagnóstico={dados_periodo['diagnostico_fonte']} | "
                f"API consultas/ofertas="
                f"{dados_periodo['consultas_api']}/"
                f"{dados_periodo['ofertas_api_anexadas']} | "
                "última evidência="
                f"{dados_periodo.get('ultima_asiatica_em') or '-'}"
            )
        bet365 = resumir_observacoes_bet365(banco.conexao)
        integridade_bet365 = bet365["integridade"]
        print(
            "fonte complementar Bet365: "
            f"{'ativa' if bet365['ativa_no_monitor'] else 'desligada'} | "
            f"observações={bet365['total']} | "
            f"ofertas válidas={bet365['ofertas_validas']} | "
            f"última={bet365['ultima_observacao'] or '-'} | estados="
            + (
                ", ".join(
                    f"{estado}={total}"
                    for estado, total in bet365["por_estado"].items()
                )
                or "-"
            )
            + " | motivos="
            + (
                ", ".join(
                    f"{motivo}={total}"
                    for motivo, total in bet365["por_motivo"].items()
                )
                or "-"
            )
            + " | métodos="
            + (
                ", ".join(
                    f"{metodo}={total}"
                    for metodo, total in bet365["por_metodo"].items()
                )
                or "-"
            )
            + " | integridade="
            + integridade_bet365["estado"]
            + " | comprovada="
            + ("sim" if integridade_bet365["comprovada"] else "não")
        )
        fila_manual = listar_solicitacoes_odds_manuais(banco.conexao)
        print(
            "conferência manual Bet365: "
            f"pendentes agora={fila_manual['total']} | "
            f"janela={fila_manual['janela_minutos']}min | "
            f"nota mínima={fila_manual['pontuacao_minima']:.0f} | "
            "envio automático=desligado"
        )
        print(
            f"regra ativa padrão: {VERSAO_REGRAS} | exceções="
            + (
                ", ".join(
                    f"{mercado}={versao}"
                    for mercado, versao
                    in VERSOES_REGRAS_POR_MERCADO.items()
                )
                or "-"
            )
        )
        coberturas_linhagem = {}
        for regra_versao in versoes_regras_ativas():
            linhagem = auditar_linhagem_regra(
                banco.conexao,
                PASTA,
                regra_versao,
                VERSAO_FEATURES,
            )
            print(
                f"linhagem {regra_versao}: "
                f"{linhagem['estado']} | "
                f"origem={linhagem.get('origem') or '-'} | fingerprint="
                f"{(linhagem.get('fingerprint_atual') or '-')[:12]} | "
                f"âncora={'sim' if linhagem.get('ancora_presente') else 'não'}"
            )
            if linhagem.get("componentes_divergentes"):
                print(
                    "  divergências da linhagem: "
                    + ", ".join(linhagem["componentes_divergentes"])
                )
            cobertura = resumir_cobertura_linhagem_sinais(
                banco.conexao, regra_versao
            )
            coberturas_linhagem[regra_versao] = cobertura
            print(
                f"  cobertura {regra_versao}: vinculados="
                f"{cobertura['vinculados']} | legado preservado="
                f"{cobertura['legado_sem_fingerprint']} | divergentes="
                f"{cobertura['divergentes']} | novos sem fingerprint="
                f"{cobertura['novos_sem_fingerprint']} | marco="
                f"{'sim' if cobertura.get('marco_presente') else 'não'} | "
                f"estado={'saudável' if cobertura['saudavel'] else 'bloqueado'}"
            )
        cobertura_linhagem = coberturas_linhagem[VERSAO_REGRAS]
        amostra_oficial_id = "|".join((
            VERSAO_REGRAS,
            POLITICA_CALIBRACAO_VERSAO,
            cobertura_linhagem.get("fingerprint") or "sem_fingerprint",
            cobertura_linhagem.get("iniciado_em") or "sem_marco",
        ))
        print(
            "população oficial da calibração: "
            f"política={POLITICA_CALIBRACAO_VERSAO} | "
            f"id={amostra_oficial_id[:24]}..."
        )
        imprimir_calibracoes_arquivadas(
            banco.conexao,
            VERSAO_REGRAS,
            regras_ativas_por_mercado={
                mercado: versao_regra_para_mercado(mercado)
                for mercado in MERCADOS_CALIBRADOS
            },
        )
        dataset_temporal = resumir_cobertura_dataset_temporal(
            banco.conexao,
            MERCADOS_CALIBRADOS,
            regras_por_mercado={
                mercado: versao_regra_para_mercado(mercado)
                for mercado in MERCADOS_CALIBRADOS
            },
        )
        cobertura_temporal = dataset_temporal["cobertura"]
        print(
            "amostra temporal resolvida: schema="
            f"{dataset_temporal['schema_features']} | válidos="
            f"{dataset_temporal['validos']}/{dataset_temporal['elegiveis']} | "
            f"históricos={dataset_temporal['historicos']} | "
            "legado pré-fingerprint excluído="
            f"{dataset_temporal['legado_excluido']} | "
            "excluídos por schema/integridade="
            f"{dataset_temporal['excluidos']} | cobertura="
            f"{cobertura_temporal if cobertura_temporal is not None else '-'}"
        )
        motivos_exclusao = ", ".join(
            f"{motivo}={quantidade}"
            for motivo, quantidade in (
                dataset_temporal["exclusoes_por_motivo"].items()
            )
            if quantidade
        )
        if motivos_exclusao:
            print(f"  exclusões temporais: {motivos_exclusao}")
        for mercado, dados_temporais in (
            dataset_temporal["por_mercado"].items()
        ):
            if (
                dados_temporais["excluidos"]
                or dados_temporais["legado_excluido"]
            ):
                print(
                    f"  temporal {mercado}: válidos="
                    f"{dados_temporais['validos']}/"
                    f"{dados_temporais['elegiveis']} | excluídos="
                    f"{dados_temporais['excluidos']} | legado excluído="
                    f"{dados_temporais['legado_excluido']}"
                )
        if resultados:
            avaliador = AvaliadorBacktest(banco)
            mercados = MERCADOS_CALIBRADOS
            desempenho = {
                mercado: avaliador.metricas(
                    mercado=mercado,
                    regra_versao=versao_regra_para_mercado(mercado),
                )
                for mercado in mercados
            }
            elegiveis = sum(item["amostra"] for item in desempenho.values())
            print(
                "resultados elegíveis históricos independentes "
                f"(inclui legado pré-fingerprint): {elegiveis}"
            )
            print(
                "desempenho histórico por mercado "
                "(não ativa calibração sem fingerprint):"
            )
            for mercado, metricas in desempenho.items():
                acerto = metricas["taxa_acerto"]
                roi = metricas["roi"]
                auc = metricas["discriminacao_pontuacao"]["auc"]
                acerto_texto = (
                    f"{acerto * 100:.1f}%" if acerto is not None else "-"
                )
                roi_texto = (
                    f"{roi * 100:.1f}%" if roi is not None else "-"
                )
                auc_texto = f"{auc:.3f}" if auc is not None else "-"
                print(
                    f"  {mercado}: n binário={metricas['amostra']} | "
                    "exposições liquidadas="
                    f"{metricas.get('exposicoes_liquidadas', metricas['amostra'])} | "
                    f"voids={metricas.get('voids', 0)} | "
                    f"acerto={acerto_texto} | ROI={roi_texto} | "
                    f"AUC nota={auc_texto} | "
                    f"estado={metricas['estado_amostra']}"
                )
            progresso = resumir_progresso_calibracao(
                banco.conexao,
                regra_versao=VERSAO_REGRAS,
                usar_versoes_ativas=True,
            )
            print("ritmo até 100 resultados independentes:")
            for mercado, item in progresso.items():
                prazo = (
                    f"{item['dias_estimados']} dias / "
                    f"{item['data_estimada']}"
                    if item["dias_estimados"] is not None
                    else "sem previsão"
                )
                print(
                    f"  {mercado}: resolvidos={item['amostra']} | "
                    f"ritmo={item['ritmo_dia']}/dia | "
                    f"faltam resultados reais={item['faltam']} | "
                    f"prazo={prazo} | "
                    f"estimativa={item['confiabilidade_estimativa']}"
                )

        calibracoes = banco.conexao.execute(
            """
            SELECT mercado, regra_versao, amostra, ativa, atualizado_em,
                   modelo_json
            FROM calibracoes ORDER BY mercado
            """
        ).fetchall()
        calibracoes = [
            item for item in calibracoes
            if item["regra_versao"]
            == versao_regra_para_mercado(item["mercado"])
        ]
        if not calibracoes:
            print("calibração: aguardando amostra")
        calibracoes_sem_vinculo = 0
        calibracoes_incoerentes = 0
        for item in calibracoes:
            estado = "ativa" if item["ativa"] else "inativa"
            try:
                modelo = json.loads(item["modelo_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                modelo = {}
            modelo_json = serializar_modelo_calibracao(modelo)
            modelo_hash = hash_modelo_calibracao(modelo)
            historico_vinculado = banco.conexao.execute(
                """
                SELECT 1 FROM historico_calibracoes
                WHERE mercado=? AND regra_versao=? AND amostra=? AND ativa=?
                  AND modelo_hash=? AND modelo_json=?
                LIMIT 1
                """,
                (
                    item["mercado"], item["regra_versao"], item["amostra"],
                    item["ativa"], modelo_hash, modelo_json,
                ),
            ).fetchone() is not None
            try:
                estado_coerente = bool(
                    bool(item["ativa"]) == (modelo.get("ativa") is True)
                    and int(item["amostra"] or 0)
                    == int(modelo.get("amostra") or 0)
                )
            except (TypeError, ValueError):
                estado_coerente = False
            calibracoes_sem_vinculo += int(not historico_vinculado)
            calibracoes_incoerentes += int(not estado_coerente)
            drift = modelo.get("drift") or {}
            populacao = modelo.get("populacao") or "legada"
            politica = modelo.get("politica_versao") or "legada"
            celulas = modelo.get("validacao_por_faixa") or {}
            celulas_aprovadas = sum(
                bool(valor.get("aprovada")) for valor in celulas.values()
            )
            estado_drift = (
                "detectado" if drift.get("detectado")
                else drift.get("motivo") or "estável"
            )
            print(
                f"calibração {item['mercado']}: {estado} | "
                f"amostra independente {item['amostra']} | "
                f"{item['regra_versao']} | "
                f"motivo={modelo.get('motivo') or 'aprovada'} | "
                f"drift={estado_drift} | população={populacao} | "
                f"política={politica} | células="
                f"{celulas_aprovadas}/{len(celulas)} | histórico="
                f"{'vinculado' if historico_vinculado else 'inválido'} | "
                f"estado={'coerente' if estado_coerente else 'divergente'}"
            )
            if modelo.get("janela_modelo_fixa") is not None:
                print(
                    "  janela oficial congelada: modelo="
                    f"{item['amostra']}/"
                    f"{modelo.get('janela_modelo_fixa')} | "
                    "total disponivel="
                    f"{modelo.get('amostra_total_disponivel', item['amostra'])} | "
                    "monitoramento recente="
                    f"{modelo.get('amostra_monitoramento', 0)}/"
                    f"{modelo.get('janela_calibracao_maxima', 300)} | "
                    "novas exposicoes posteriores alteram modelo=nao"
                )
            integridade_coorte = (
                modelo.get("integridade_coorte_modelo") or {}
            )
            if integridade_coorte:
                print(
                    "  coorte causal oficial: estado="
                    f"{integridade_coorte.get('estado') or '-'} | "
                    "unidades/validas="
                    f"{integridade_coorte.get('unidades_selecionadas', 0)}/"
                    f"{integridade_coorte.get('validas', 0)} | "
                    f"pendentes={integridade_coorte.get('pendentes', 0)} | "
                    f"invalidas={integridade_coorte.get('invalidas', 0)} | "
                    "devolvidas="
                    f"{integridade_coorte.get('devolvidas_contratuais', 0)} | "
                    "sem dado="
                    f"{integridade_coorte.get('encerradas_sem_dado', 0)} | "
                    "falhas tecnicas="
                    f"{integridade_coorte.get('invalidas_tecnicas', 0)} | "
                    "selecao antes do resultado="
                    f"{'sim' if integridade_coorte.get('selecao_antes_do_resultado') else 'nao'}"
                )
            discriminacao_final = (
                modelo.get("discriminacao_pontuacao") or {}
            )
            if (
                modelo.get("amostra_validacao") is not None
                or modelo.get("roi_validacao_agregado") is not None
                or discriminacao_final
            ):
                auc_final = discriminacao_final.get("auc")
                limite_auc_final = discriminacao_final.get(
                    "limite_inferior_auc_95"
                )
                roi_final = modelo.get("roi_validacao_agregado")
                erro_final = modelo.get("erro_calibracao")
                print(
                    "  validação cronológica final: "
                    f"n={modelo.get('amostra_validacao', 0)} | "
                    f"ROI={roi_final if roi_final is not None else '-'} | "
                    f"AUC={auc_final if auc_final is not None else '-'} | "
                    "limite inferior AUC95="
                    f"{limite_auc_final if limite_auc_final is not None else '-'} | "
                    "erro de calibração="
                    f"{erro_final if erro_final is not None else '-'}"
                )
            linhagem_amostra = modelo.get("linhagem_amostra") or {}
            if linhagem_amostra:
                print(
                    "  amostra por linhagem: vinculada="
                    f"{linhagem_amostra.get('vinculadas', 0)} | "
                    "legado preservado e excluído do oficial="
                    f"{linhagem_amostra.get('legado_excluido', 0)} | "
                    f"histórica={linhagem_amostra.get('historicas', 0)}"
                )
            sombra = modelo.get("diagnostico_sombra") or {}
            if sombra:
                discriminacao = sombra.get("discriminacao_pontuacao") or {}
                auc = discriminacao.get("auc")
                limite_auc = discriminacao.get("limite_inferior_auc_95")
                roi = sombra.get("roi_validacao_agregado")
                motivos_tendencia = ",".join(
                    sombra.get("motivos_tendencia") or ()
                ) or "-"
                print(
                    "  pré-validação sombra (não ativa sinais): "
                    f"etapa={sombra.get('etapa') or '-'} | "
                    f"desenvolvimento={sombra.get('amostra_desenvolvimento')}/"
                    f"{sombra.get('amostra_desenvolvimento_alvo', 70)} | "
                    f"validação={sombra.get('amostra_validacao')}/"
                    f"{sombra.get('amostra_validacao_alvo', 30)} | "
                    "faltam desenvolvimento/validação="
                    f"{sombra.get('desenvolvimento_faltante', 0)}/"
                    f"{sombra.get('validacao_faltante', 0)} | "
                    f"AUC={auc if auc is not None else '-'} | "
                    "limite inferior AUC95="
                    f"{limite_auc if limite_auc is not None else '-'} | "
                    f"ROI validação={roi if roi is not None else '-'} | "
                    "tendência provisória="
                    f"{sombra.get('tendencia_provisoria') or '-'} | "
                    f"motivos provisórios={motivos_tendencia} | "
                    "células observadas="
                    f"{len(sombra.get('celulas_observadas') or {})}"
                )
        print(
            "integridade das calibrações atuais: "
            f"sem histórico={calibracoes_sem_vinculo} | "
            f"estado incoerente={calibracoes_incoerentes}"
        )
        historico_calibracoes = banco.conexao.execute(
            """
            SELECT COUNT(*) AS total,
                   MIN(registrado_em) AS primeiro,
                   MAX(registrado_em) AS ultimo
            FROM historico_calibracoes
            """
        ).fetchone()
        print(
            "histórico imutável de calibrações: "
            f"modelos={historico_calibracoes['total']} | "
            f"primeiro={historico_calibracoes['primeiro'] or '-'} | "
            f"último={historico_calibracoes['ultimo'] or '-'}"
        )
        particoes = auditar_particoes_calibracao(
            banco.conexao,
            MERCADOS_CALIBRADOS,
            VERSAO_REGRAS,
            obter_limites_risco(),
        )
        print(
            "partições temporais treino/validação: "
            f"{'íntegras' if particoes['saudavel'] else 'inconsistentes'} | "
            "mercados inconsistentes="
            f"{','.join(particoes['inconsistentes']) or '-'}"
        )
        resumos_resgate_qualidade = {
            horas: resumir_resgate_qualidade_api(
                banco.conexao, horas=horas
            )
            for horas in (24, 24 * 7)
        }
    finally:
        banco.fechar()

    arquivo_log = PASTA / "monitor_eventos.jsonl"
    observabilidade = Observabilidade(arquivo_log)
    resumo = observabilidade.resumo()
    funis_operacionais = {
        "3h": observabilidade.resumo_funil_periodo(horas=3),
        "24h": observabilidade.resumo_funil_periodo(horas=24),
    }
    ultimo_ciclo = resumo.get("ultimo_evento") or {}
    print(descrever_thestatsapi_sombra(
        configuracao.get("thestatsapi") or {},
        diagnostico_thestatsapi,
        cobertura_thestatsapi,
        ultimo_ciclo.get("thestatsapi_sombra") or {},
    ))
    if resumo["ciclos"]:
        print(
            "operação: "
            f"ciclos={resumo['ciclos']} | erros={resumo['erros']} | "
            f"uptime={resumo['uptime_percentual']:.2f}% | "
            f"latência média={resumo['latencia_media_segundos']:.2f}s | "
            f"p95={resumo['latencia_p95_segundos']:.2f}s | "
            f"máxima={resumo['latencia_maxima_segundos']:.2f}s"
        )
        ultima_falha_fatal = (
            resumo.get("processo_ultima_falha_fatal") or {}
        )
        if ultima_falha_fatal:
            print(
                "última falha fatal registrada: "
                f"{ultima_falha_fatal.get('em') or '-'} | "
                f"componente={ultima_falha_fatal.get('componente') or '-'} | "
                f"erro={ultima_falha_fatal.get('erro') or '-'} | "
                f"mensagem={ultima_falha_fatal.get('mensagem') or '-'} | "
                "falhas fatais no log atual="
                f"{resumo.get('processos_falhas_fatais', 0)}"
            )
        if ultimo_ciclo.get("tarefas_agendadas") is not None:
            print(
                "último ciclo detalhado: "
                f"agendadas={ultimo_ciclo.get('tarefas_agendadas', 0)} | "
                f"processadas={ultimo_ciclo.get('tarefas_processadas', 0)} | "
                f"adiadas={ultimo_ciclo.get('tarefas_adiadas', 0)} | "
                "duração="
                f"{ultimo_ciclo.get('duracao_detalhada_segundos', 0)}s/"
                f"{ultimo_ciclo.get('orcamento_detalhado_segundos', 180)}s"
            )
        if ultimo_ciclo.get("cache_api_hits_ciclo") is not None:
            print(
                "cache API no último ciclo: "
                f"hits={ultimo_ciclo.get('cache_api_hits_ciclo', 0)} | "
                "gravações="
                f"{ultimo_ciclo.get('cache_api_gravacoes_ciclo', 0)} | "
                "descartes="
                f"{ultimo_ciclo.get('cache_api_descartes_ciclo', 0)} | "
                f"falhas={ultimo_ciclo.get('cache_api_falhas_ciclo', 0)}"
            )
        ultima_supervisao = resumo.get("watchdog_ultima_supervisao") or {}
        print(
            "supervisão do watchdog pelo monitor: "
            f"reinícios={resumo.get('watchdog_reinicios', 0)} | "
            "falhas="
            f"{resumo.get('watchdog_falhas_supervisao', 0)} | "
            f"última={ultima_supervisao.get('em', '-')}"
        )
    rotulos_gargalos = {
        "baixa_oferta_jogos_ao_vivo": "baixa oferta de jogos ao vivo",
        "sem_partidas_elegiveis": "nenhuma partida elegível",
        "qualidade_insuficiente": "qualidade insuficiente",
        "fora_janelas_operacionais": "fora das janelas de minutos",
        "sem_odds": "odd indisponível",
        "fontes_bloqueadas": "fontes bloqueadas",
        "tarefas_adiadas_capacidade": "capacidade interna insuficiente",
        "ritmo_packball_seguro": "ritmo seguro do PackBall",
    }
    for periodo, funil in funis_operacionais.items():
        def fontes_texto(valores):
            return ",".join(
                f"{nome}:{quantidade}"
                for nome, quantidade in sorted((valores or {}).items())
            ) or "-"

        cobertura_odds = funil.get("cobertura_odds")
        cobertura_odds_texto = (
            "-" if cobertura_odds is None
            else f"{float(cobertura_odds) * 100:.1f}%"
        )
        gargalo = funil.get("gargalo_principal")
        print(
            f"funil operacional {periodo}: "
            f"estado={funil.get('estado')} | "
            "gargalo="
            f"{rotulos_gargalos.get(gargalo, gargalo or '-')} | "
            f"ciclos ok/falhos={funil.get('ciclos_concluidos', 0)}/"
            f"{funil.get('ciclos_falhos', 0)} | "
            "sequência final ok/falha="
            f"{funil.get('sucessos_consecutivos_finais', 0)}/"
            f"{funil.get('falhas_consecutivas_finais', 0)} | "
            "recuperada="
            f"{'sim' if funil.get('operacao_recuperada') else 'não'} | "
            "zero ao vivo confirmado="
            f"{funil.get('ciclos_zero_ao_vivo_confirmado', 0)} | "
            "jogos média/máx por ciclo="
            f"{float(funil.get('partidas_media_por_ciclo') or 0):.2f}/"
            f"{funil.get('partidas_maximo_por_ciclo', 0)} | "
            "tarefas processadas/agendadas="
            f"{funil.get('tarefas_processadas', 0)}/"
            f"{funil.get('tarefas_agendadas', 0)} | "
            "adiadas seguras/capacidade="
            f"{funil.get('tarefas_adiadas_distribuidas', 0)}/"
            f"{funil.get('tarefas_adiadas_capacidade', 0)} | "
            f"cobertura de odds={cobertura_odds_texto} | "
            "coleta de odds solicitada/sucesso="
            f"{funil.get('tarefas_odds_solicitadas', 0)}/"
            f"{funil.get('coletas_odds_sucesso', 0)} | "
            "fallback necessário/atendeu/sem cobertura="
            f"{funil.get('fallback_odds_necessario', 0)}/"
            f"{funil.get('fallback_odds_atendeu', 0)}/"
            f"{funil.get('fallback_odds_sem_cobertura', 0)} | "
            "fontes utilizáveis="
            f"{fontes_texto(funil.get('fontes_odds_utilizaveis'))} | "
            "fontes que atenderam fallback="
            f"{fontes_texto(funil.get('fontes_fallback_odds'))} | "
            "gols antecipados avaliados/gerados="
            f"{funil.get('avaliacoes_gols_antecipados', 0)}/"
            f"{funil.get('gols_antecipados_gerados', 0)}"
        )
        comparacao = funil.get("comparacao_fontes_odds") or {}
        if comparacao:
            fontes_comparadas = comparacao.get("fontes") or {}
            betsapi = fontes_comparadas.get("betsapi") or {}
            thestats = fontes_comparadas.get("thestatsapi") or {}
            print(
                f"comparação de odds {periodo}: "
                f"estado={comparacao.get('estado')} | "
                "jogos únicos/horas="
                f"{comparacao.get('partidas_unicas_comparadas', 0)}/"
                f"{float(comparacao.get('horas_telemetria_direta') or 0):.1f} | "
                "BetsAPI utilizável/fallback="
                f"{betsapi.get('partidas_unicas_utilizaveis', 0)}/"
                f"{betsapi.get('partidas_unicas_fallback', 0)} | "
                "TheStats utilizável/fallback="
                f"{thestats.get('partidas_unicas_utilizaveis', 0)}/"
                f"{thestats.get('partidas_unicas_fallback', 0)} | "
                "líder provisório="
                f"{comparacao.get('lider_cobertura_provisorio') or '-'} | "
                "substituição conclusiva=não"
            )
    if arquivo_log.exists():
        linhas = arquivo_log.read_text(encoding="utf-8").splitlines()
        if linhas:
            ultimo = json.loads(linhas[-1])
            print(
                "último evento: "
                f"{ultimo.get('em')} | {ultimo.get('evento')}"
            )
        saude = verificar_coleta(arquivo_log)
        print(
            "saúde da coleta: "
            f"{'saudável' if saude['saudavel'] else 'degradada'} | "
            f"último sucesso há {saude.get('idade')}s | "
            f"falhas consecutivas={saude.get('falhas_consecutivas', 0)}"
        )
        if saude.get("ciclo_em_andamento"):
            print(
                "ciclo atual: em andamento | "
                f"etapa={saude.get('etapa_atual') or '-'} | "
                "último progresso há "
                f"{saude.get('idade_progresso')}s"
            )
        capacidade = verificar_capacidade_coleta(arquivo_log)
        idade_fila = capacidade.get("idade_fila") or {}
        idade_processadas = idade_fila.get("processadas") or {}
        idade_adiadas = idade_fila.get("adiadas") or {}
        priorizacao_fila = capacidade.get("priorizacao_fila") or {}
        perfil_agendamento = capacidade.get("perfil_agendamento") or {}
        print(
            "capacidade da fila: "
            f"{capacidade.get('estado')} | "
            f"ciclos adiando={capacidade.get('ciclos_adiando', 0)} | "
            "pausas preventivas PackBall="
            f"{capacidade.get('ciclos_pausa_preventiva', 0)} | "
            "ciclos limitados com distribuição="
            f"{capacidade.get('ciclos_limitados_packball', 0)} | "
            f"sob pressão={capacidade.get('ciclos_sob_pressao', 0)} | "
            f"último agendadas={capacidade.get('agendadas', '-')} | "
            f"processadas={capacidade.get('processadas', '-')} | "
            f"adiadas={capacidade.get('adiadas', '-')} | "
            "capacidade interna média/p95/máx="
            f"{_percentual_status(capacidade.get('utilizacao_media_percentual'))}/"
            f"{_percentual_status(capacidade.get('utilizacao_p95_percentual'))}/"
            f"{_percentual_status(capacidade.get('utilizacao_maxima_percentual'))}"
            " | janela total observada média/p95/máx="
            f"{_percentual_status(capacidade.get('utilizacao_observada_media_percentual'))}/"
            f"{_percentual_status(capacidade.get('utilizacao_observada_p95_percentual'))}/"
            f"{_percentual_status(capacidade.get('utilizacao_observada_maxima_percentual'))}"
            " | excesso orçamento média/p95/máx="
            f"{_segundos_status(capacidade.get('excesso_orcamento_media_segundos'))}/"
            f"{_segundos_status(capacidade.get('excesso_orcamento_p95_segundos'))}/"
            f"{_segundos_status(capacidade.get('excesso_orcamento_maximo_segundos'))}"
            " | excesso anormal consecutivo="
            f"{capacidade.get('ciclos_excesso_inesperado_consecutivos', 0)}"
            " | reserva adaptativa ciclos/última="
            f"{capacidade.get('ciclos_reserva_adaptativa', 0)}/"
            f"{'sim' if capacidade.get('ultimo_interrompido_por_reserva') else 'não'}"
            " | reserva estimada="
            f"{_segundos_status(capacidade.get('ultima_reserva_admissao_segundos'))}"
            " | fila >20min processadas/adiadas="
            f"{idade_processadas.get('acima_20_minutos', 0)}/"
            f"{idade_adiadas.get('acima_20_minutos', 0)}"
            " | maior idade adiada="
            f"{_segundos_status(idade_adiadas.get('maxima_segundos'))}"
            " | resgate antigo reservado="
            f"{'sim' if priorizacao_fila.get('atrasada_reservada') else 'não'}"
            " | ciclos sem resgate antigo="
            f"{capacidade.get('ciclos_sem_resgate_antigo', 0)}"
            " | pós-gol agendadas/processadas="
            f"{perfil_agendamento.get('rechecagens_pos_evento_agendadas', 0)}/"
            f"{perfil_agendamento.get('rechecagens_pos_evento_processadas', 0)}"
            " | ciclos pós-gol sem processamento="
            f"{capacidade.get('ciclos_sem_rechecagem_pos_evento', 0)}"
            " | prioridade Gol HT base/seguimento/oportunidade="
            f"{'sim' if priorizacao_fila.get('nova_gol_ht_reservada') else 'não'}/"
            f"{'sim' if priorizacao_fila.get('seguimento_gol_ht_reservado') else 'não'}/"
            f"{'sim' if priorizacao_fila.get('oportunidade_gol_ht_reservada') else 'não'}"
            " | Gol HT garantido/tipo/top4="
            f"{'sim' if priorizacao_fila.get('prioridade_gol_ht_garantida') else 'não'}/"
            f"{priorizacao_fila.get('tipo_prioridade_gol_ht') or '-'}/"
            f"{'sim' if priorizacao_fila.get('prioridade_gol_ht_nas_quatro_primeiras') else 'não'}"
        )
        associacoes_api = capacidade.get("associacoes_api") or {}
        print(
            "pareamento API no último ciclo: "
            + (
                " | ".join(
                    f"{motivo}={quantidade}"
                    for motivo, quantidade in sorted(
                        associacoes_api.items()
                    )
                )
                if associacoes_api else "sem tarefas detalhadas"
            )
        )
        funil_antecipados = capacidade.get("gols_antecipados") or {}
        print(
            "funil de gols antecipados no último ciclo: "
            f"avaliações={funil_antecipados.get('avaliacoes', 0)} | "
            f"gerados={funil_antecipados.get('gerados', 0)}"
        )
        nomes_bracos = {
            "global": "gate global",
            "gol_ht_antecipado": "Gol HT antecipado",
            "gol_ft_antecipado_pre_live": "Gol FT inicial",
            "gol_ft_antecipado_2t": "Gol FT 2º tempo",
        }
        for braco, dados in sorted(
            (funil_antecipados.get("por_braco") or {}).items()
        ):
            motivos = dados.get("motivos") or {}
            resumo_motivos = (
                ", ".join(
                    f"{motivo}={quantidade}"
                    for motivo, quantidade in sorted(motivos.items())
                )
                if motivos else "-"
            )
            print(
                f"  {nomes_bracos.get(braco, braco)}: "
                f"avaliado={dados.get('avaliacoes', 0)} | "
                f"gerado={dados.get('gerados', 0)} | "
                f"primeira barreira={resumo_motivos}"
            )
            detalhes = dados.get("detalhes") or {}
            if detalhes:
                campos = detalhes.get("campos_ausentes") or {}
                alertas = detalhes.get("alertas") or {}
                print(
                    "    qualidade: campos ausentes="
                    + (
                        ", ".join(
                            f"{nome}={quantidade}"
                            for nome, quantidade in sorted(campos.items())
                        )
                        if campos else "-"
                    )
                    + " | alertas="
                    + (
                        ", ".join(
                            f"{nome}={quantidade}"
                            for nome, quantidade in sorted(alertas.items())
                        )
                        if alertas else "-"
                    )
                )
        resgate_api = capacidade.get("resgate_qualidade_api") or {}
        campos_resgate = resgate_api.get("campos_complementados") or {}
        estados_resgate = resgate_api.get("estados") or {}
        print(
            "resgate de qualidade API-Football (somente sombra): "
            f"avaliações={resgate_api.get('avaliacoes', 0)} | "
            f"resgatadas={resgate_api.get('resgatadas', 0)} | "
            "estados="
            + (
                ", ".join(
                    f"{estado}={quantidade}"
                    for estado, quantidade in sorted(estados_resgate.items())
                )
                if estados_resgate else "-"
            )
            + " | campos="
            + (
                ", ".join(
                    f"{campo}={quantidade}"
                    for campo, quantidade in sorted(campos_resgate.items())
                )
                if campos_resgate else "-"
            )
            + " | uso nos sinais=não"
        )
        for horas_resgate, rotulo_resgate in (
            (24, "24h"), (24 * 7, "7 dias")
        ):
            acumulado_resgate = resumos_resgate_qualidade[horas_resgate]
            taxa_resgate = acumulado_resgate.get("taxa_resgate")
            print(
                f"  acumulado {rotulo_resgate}: "
                f"registros={acumulado_resgate['registros']} | "
                f"elegíveis={acumulado_resgate['elegiveis']} | "
                f"jogos={acumulado_resgate['jogos_distintos']} | "
                f"resgatadas={acumulado_resgate['resgatadas']} | "
                "taxa="
                f"{(f'{taxa_resgate * 100:.1f}%' if taxa_resgate is not None else '-')} | "
                "ganho médio de qualidade="
                f"{acumulado_resgate.get('ganho_medio_qualidade') or '-'} | "
                "revisão="
                f"{'pronta' if acumulado_resgate['pronto_para_revisao'] else 'aguardando amostra'}"
            )
        enriquecimento_lote = (
            capacidade.get("enriquecimento_api_lote") or {}
        )
        print(
            "enriquecimento API em lote: "
            f"estado={enriquecimento_lote.get('estado', 'aguardando')} | "
            f"associadas={enriquecimento_lote.get('associadas', 0)} | "
            f"solicitadas={enriquecimento_lote.get('solicitadas', 0)} | "
            f"retornadas={enriquecimento_lote.get('retornadas', 0)} | "
            f"incorporadas={enriquecimento_lote.get('incorporadas', 0)} | "
            "stats para resgate selecionadas/consultadas/com dados="
            f"{enriquecimento_lote.get('stats_resgate_selecionadas', 0)}/"
            f"{enriquecimento_lote.get('stats_resgate_consultadas', 0)}/"
            f"{enriquecimento_lote.get('stats_resgate_com_dados', 0)} | "
            "limite por ciclo="
            f"{enriquecimento_lote.get('stats_resgate_limite_ciclo', 0)} | "
            "uso nos sinais=não"
        )
        cache_api_operacional = verificar_cache_api_operacional(arquivo_log)
        print(
            "operação do cache API: "
            f"{cache_api_operacional.get('estado')} | "
            "ciclos com falha consecutivos="
            f"{cache_api_operacional.get('ciclos_com_falha_consecutivos', 0)} "
            "| falhas no último="
            f"{cache_api_operacional.get('falhas_ultimo_ciclo', 0)}"
        )
        acompanhamento_preco = verificar_acompanhamento_preco_pos_alerta(
            arquivo_log
        )
        ultimo_acompanhamento = acompanhamento_preco.get("ultimo_ciclo") or {}
        print(
            "cotação posterior aos alertas: "
            f"{acompanhamento_preco.get('estado')} | "
            "falhas aplicáveis consecutivas="
            f"{acompanhamento_preco.get('ciclos_degradados_consecutivos', 0)}/"
            f"{acompanhamento_preco.get('limite_consecutivo', 3)} | "
            "último agendado/processado/com odd/snapshot="
            f"{ultimo_acompanhamento.get('agendados', 0)}/"
            f"{ultimo_acompanhamento.get('processados', 0)}/"
            f"{ultimo_acompanhamento.get('com_odds', 0)}/"
            f"{ultimo_acompanhamento.get('snapshots', 0)} | "
            "altera sinais=não"
        )
        amostragem_sombra = verificar_amostragem_referencia_odds_sombra(
            arquivo_log
        )
        ultimo_amostragem_sombra = (
            amostragem_sombra.get("ultimo_ciclo") or {}
        )
        controle_amostragem_sombra = (
            ultimo_amostragem_sombra.get("controle_estado") or {}
        )
        controle_sombra_saudavel = controle_amostragem_sombra.get(
            "saudavel"
        )
        if controle_sombra_saudavel is True:
            controle_sombra_descricao = "saudável"
        elif controle_sombra_saudavel is False:
            controle_sombra_descricao = "bloqueado"
        else:
            controle_sombra_descricao = "-"
        print(
            "supervisão da referência independente: "
            f"{amostragem_sombra.get('estado')} | "
            "elegíveis/reservas/mercados="
            f"{amostragem_sombra.get('elegiveis_betsapi', 0)}/"
            f"{amostragem_sombra.get('reservadas', 0)}/"
            f"{amostragem_sombra.get('mercados_persistidos_sombra', 0)} | "
            "tentativas sem cobertura="
            f"{amostragem_sombra.get('tentativas_sem_cobertura_consecutivas', 0)}/"
            f"{amostragem_sombra.get('limite_consecutivo', 3)} | "
            "diversidade hoje="
            f"{ultimo_amostragem_sombra.get('jogos_distintos_dia', 0)}/"
            f"{ultimo_amostragem_sombra.get('maior_uso_jogo_dia', 0)}"
            " (máx="
            f"{ultimo_amostragem_sombra.get('maximo_por_jogo_dia', 0)}) | "
            "novas/confirmações no ciclo="
            f"{ultimo_amostragem_sombra.get('novas_partidas_ciclo', 0)}/"
            f"{ultimo_amostragem_sombra.get('confirmacoes_temporais_ciclo', 0)}"
            " (conf. máx="
            f"{ultimo_amostragem_sombra.get('confirmacoes_maximo_ciclo', 0)}) | "
            "estado persistente="
            f"{controle_amostragem_sombra.get('origem') or '-'}/"
            f"{controle_sombra_descricao} | "
            "altera HT/FT=não"
        )
        integridade_melhor_preco = (
            verificar_integridade_melhor_preco_sombra(
                PASTA / "monitor_packball.db"
            )
        )
        validacao_resultado_preco = (
            integridade_melhor_preco.get(
                "validacao_resultado_valor_justo"
            ) or {}
        )
        mercados_resultado_preco = (
            validacao_resultado_preco.get("por_mercado") or {}
        )
        transferencia_resultado_preco = (
            validacao_resultado_preco.get("validacao_transferencia") or {}
        )
        composicao_transferencia = (
            transferencia_resultado_preco.get("composicao_status") or {}
        )
        validacao_veto_preco = (
            integridade_melhor_preco.get("validacao_veto_preco_justo")
            or {}
        )
        edge_resultados = sum(
            int(
                ((item.get("total") or {}).get("edge") or {}).get(
                    "resultados_validos", 0
                ) or 0
            )
            for item in mercados_resultado_preco.values()
        )
        controle_resultados = sum(
            int(
                (
                    (item.get("total") or {}).get("controle_sem_edge")
                    or {}
                ).get("resultados_validos", 0) or 0
            )
            for item in mercados_resultado_preco.values()
        )
        print(
            "integridade do melhor preço em sombra: "
            f"{integridade_melhor_preco.get('estado')} | "
            "observações/partidas/pares="
            f"{integridade_melhor_preco.get('observacoes', 0)}/"
            f"{integridade_melhor_preco.get('partidas_distintas', 0)}/"
            f"{integridade_melhor_preco.get('comparacoes_independentes_exatas', 0)} | "
            "referência recebida/consultada="
            f"{integridade_melhor_preco.get('referencias_separadas_recebidas', 0)}/"
            f"{integridade_melhor_preco.get('referencias_separadas_consultadas', 0)} | "
            "preço justo avaliado/desajuste="
            f"{integridade_melhor_preco.get('avaliacoes_valor_justo', 0)}/"
            f"{integridade_melhor_preco.get('desajustes_valor_justo_candidatos', 0)} | "
            "resultado prospectivo/casos/edge/controle="
            f"{validacao_resultado_preco.get('estado', '-')}/"
            f"{validacao_resultado_preco.get('candidatos_elegiveis', 0)}/"
            f"{edge_resultados}/{controle_resultados} | "
            "transferência acionável/auditoria/estado="
            f"{int(composicao_transferencia.get('aprovado', 0) or 0) + int(composicao_transferencia.get('simulacao', 0) or 0)}/"
            f"{int(composicao_transferencia.get('auditoria', 0) or 0)}/"
            f"{transferencia_resultado_preco.get('estado', '-')} | "
            "veto negativo estado/casos="
            f"{validacao_veto_preco.get('estado', '-')}/"
            f"{validacao_veto_preco.get('candidatos_pos_ancora', 0)} | "
            "violações efeito/estrutura/ponte/valor/política="
            f"{integridade_melhor_preco.get('violacoes_efeito', 0)}/"
            f"{integridade_melhor_preco.get('violacoes_estrutura', 0)}/"
            f"{integridade_melhor_preco.get('violacoes_ponte_persistencia', 0)}/"
            f"{integridade_melhor_preco.get('violacoes_valor_justo', 0)}/"
            f"{integridade_melhor_preco.get('violacoes_politica_resultado', 0)} | "
            "efeito nos sinais=não"
        )
        referencia_api_football = (
            verificar_referencia_api_football_sombra(
                PASTA / "monitor_packball.db"
            )
        )
        print(
            "referência API-Football em sombra: "
            f"{referencia_api_football.get('estado')} | "
            "tentativas/referências/mercados="
            f"{referencia_api_football.get('tentativas', 0)}/"
            f"{referencia_api_football.get('referencias_disponiveis', 0)}/"
            f"{referencia_api_football.get('mercados_retornados', 0)} | "
            "partidas/consultas="
            f"{referencia_api_football.get('partidas_distintas', 0)}/"
            f"{referencia_api_football.get('consultas_rede_estimadas', 0)} | "
            "consultas evitadas/mercados sem identidade="
            f"{referencia_api_football.get('consultas_rede_evitadas', 0)}/"
            f"{','.join(referencia_api_football.get('mercados_sem_identidade_bookmaker') or []) or '-'} | "
            "violações efeito/estrutura/persistência="
            f"{referencia_api_football.get('violacoes_efeito', 0)}/"
            f"{referencia_api_football.get('violacoes_estrutura', 0)}/"
            f"{referencia_api_football.get('violacoes_persistencia', 0)} | "
            "altera HT/FT=não"
        )
        prioridade_scanner = verificar_prioridade_scanner_packball(
            arquivo_log
        )
        print(
            "prioridade do Scanner PackBall: "
            f"{prioridade_scanner.get('estado')} | "
            "ciclos sem prioridade consecutivos="
            f"{prioridade_scanner.get('ciclos_sem_prioridade_consecutivos', 0)}"
            f"/{prioridade_scanner.get('limite_consecutivo', 3)} | "
            "último estado="
            f"{prioridade_scanner.get('estado_ultimo_ciclo') or '-'} | "
            "fallback Ao Vivo="
            f"{'ativo' if prioridade_scanner.get('fallback_ao_vivo_ativo') else '-'}"
        )
        saude_pareamento = verificar_pareamento_api(arquivo_log)
        recente_api = saude_pareamento.get("recente") or {}
        base_api = saude_pareamento.get("base") or {}
        print(
            "saúde do pareamento API: "
            f"{saude_pareamento.get('estado')} | "
            "taxa recente="
            f"{recente_api.get('taxa_associacao', '-')} | "
            f"tarefas recentes={recente_api.get('tarefas', 0)} | "
            f"taxa base={base_api.get('taxa_associacao', '-')} | "
            f"tarefas base={base_api.get('tarefas', 0)} | "
            f"motivo={saude_pareamento.get('motivo') or 'nenhum'}"
        )
    estado_watchdog_status = ler_estado(PASTA / "watchdog_estado.json")
    trabalhador_odd = (
        estado_watchdog_status.get("trabalhador_acompanhamento_odd") or {}
    )
    referencia_rapida = (
        trabalhador_odd.get("referencia_sombra_rapida") or {}
    )
    referencia_acumulada = referencia_rapida.get("acumulada") or {}
    funil_referencia = referencia_acumulada.get("funil_selecao") or {}
    exclusoes_referencia = funil_referencia.get("exclusoes") or {}
    principal_exclusao_referencia = (
        max(
            exclusoes_referencia.items(),
            key=lambda item: int(item[1] or 0),
        )[0]
        if exclusoes_referencia else "-"
    )
    print(
        "referência sincronizada no instante do sinal: "
        f"trabalhador={trabalhador_odd.get('estado') or '-'} | "
        "rodada tentadas/observadas/comparações="
        f"{referencia_rapida.get('tentadas', 0)}/"
        f"{referencia_rapida.get('observadas', 0)}/"
        f"{referencia_rapida.get('comparacoes', 0)} | "
        "acumulado rodadas/tentadas/observadas/comparações="
        f"{referencia_acumulada.get('rodadas', 0)}/"
        f"{referencia_acumulada.get('tentadas', 0)}/"
        f"{referencia_acumulada.get('observadas', 0)}/"
        f"{referencia_acumulada.get('comparacoes', 0)} | "
        "funil avaliadas/aprovadas/enviadas/executáveis/selecionadas="
        f"{funil_referencia.get('avaliadas', 0)}/"
        f"{funil_referencia.get('aprovadas', 0)}/"
        f"{funil_referencia.get('alertas_enviados', 0)}/"
        f"{funil_referencia.get('fontes_executaveis_pos_envio', 0)}/"
        f"{funil_referencia.get('selecionadas_para_consulta', 0)} | "
        f"principal exclusão={principal_exclusao_referencia} | "
        "última evidência="
        f"{referencia_acumulada.get('ultima_evidencia_em') or '-'} | "
        "integridade="
        f"{'ok' if referencia_acumulada.get('integridade') else 'pendente'} | "
        "efeito nos sinais=não | Telegram=não"
    )
    avaliacao_espera_odd = verificar_avaliacao_acompanhamento_odd(
        PASTA / "avaliacao_acompanhamento_odd_estado.json"
    )
    print(
        "estratégia de aguardar odd: "
        f"estado={avaliacao_espera_odd.get('estado')} | "
        f"execução={avaliacao_espera_odd.get('estado_execucao') or '-'} | "
        "cronologia="
        f"{_descrever_cronologia_avaliacao(avaliacao_espera_odd)} | "
        "efeitos="
        f"{_descrever_efeitos_avaliacao(avaliacao_espera_odd)} | "
        "exposição="
        f"{_descrever_exposicao_avaliacao(avaliacao_espera_odd)} | "
        f"saudável={'sim' if avaliacao_espera_odd.get('saudavel') else 'não'} | "
        f"motivo={avaliacao_espera_odd.get('motivo') or '-'} | "
        f"versão={avaliacao_espera_odd.get('versao') or '-'} | "
        "coorte independente/jogos="
        f"{avaliacao_espera_odd.get('conclusivos_prospectivos', 0)}/"
        f"{avaliacao_espera_odd.get('jogos_distintos_prospectivos', 0)} | "
        "atingiram faixa/taxa="
        f"{avaliacao_espera_odd.get('atingiram_faixa', 0)}/"
        f"{avaliacao_espera_odd.get('taxa_conversao_faixa')} | "
        "execuções oficiais vinculadas="
        f"{avaliacao_espera_odd.get('entradas_oficiais_convertidas', 0)} | "
        "ROI espera por aviso/IC95="
        f"{avaliacao_espera_odd.get('roi_espera_por_aviso')}/"
        f"{avaliacao_espera_odd.get('ic95_roi_espera_por_aviso')} | "
        "delta vs entrada imediata/IC95="
        f"{avaliacao_espera_odd.get('delta_roi_espera_vs_entrada_imediata')}/"
        f"{avaliacao_espera_odd.get('ic95_delta_roi')} | "
        "vantagem comprovada="
        f"{'sim' if avaliacao_espera_odd.get('vantagem_espera_comprovada') else 'não'} | "
        "aplicação automática=não"
    )
    avaliacao_prioridade_ligas = verificar_avaliacao_prioridade_ligas_gols(
        PASTA / "avaliacao_prioridade_ligas_gols_estado.json"
    )
    print(descrever_prioridade_ligas_gols(avaliacao_prioridade_ligas))
    avaliacao_quarentena_ht = verificar_avaliacao_quarentena_fallback_ht(
        PASTA / "avaliacao_quarentena_fallback_ht_estado.json"
    )
    print(descrever_quarentena_fallback_ht(avaliacao_quarentena_ht))
    avaliacao_desajuste = verificar_avaliacao_desajuste_odds(
        PASTA / "avaliacao_desajuste_odds_estado.json"
    )
    print(descrever_desajuste_odds(avaliacao_desajuste))
    avaliacao_probabilidade = verificar_avaliacao_probabilidade_individual(
        PASTA / "avaliacao_probabilidade_individual_estado.json"
    )
    print(
        "probabilidade individual prospectiva: "
        f"estado={avaliacao_probabilidade.get('estado')} | "
        f"saudável={'sim' if avaliacao_probabilidade.get('saudavel') else 'não'} | "
        "efeito nos sinais=não | Telegram=não"
    )
    for mercado, item in (
        avaliacao_probabilidade.get("mercados") or {}
    ).items():
        print(
            f"  {mercado}: retro={item.get('validacao_retro_estado')} "
            f"(n={item.get('amostra_retro', 0)}/"
            f"{item.get('amostra_retro_bruta', 0)}) | "
            "referência sem vig="
            f"{(item.get('referencia_sem_vig') or {}).get('taxa_cobertura')} | "
            f"modelo congelado={'sim' if item.get('definicao_presente') else 'não'} | "
            f"coorte/resultados/pendentes={item.get('candidatos', 0)}/"
            f"{item.get('resultados', 0)}/{item.get('pendentes', 0)} | "
            "delta Brier vs mercado sem vig="
            f"{item.get('delta_brier_vs_mercado_sem_vig')} | "
            "vantagem comprovada="
            f"{'sim' if item.get('vantagem_preditiva_prospectiva') else 'não'}"
        )
    validacao = enriquecer_validacao_com_watchdog(
        verificar_validacao(PASTA / "monitor_packball.db"),
        estado_watchdog_status,
    )
    imprimir_diversidade_calibracao(validacao)
    historico_drift = carregar_historico_drift_status(
        PASTA / "monitor_packball.db",
        (validacao.get("drift_simulacoes") or {}).get("regra_versao")
        or VERSAO_REGRAS,
        validacao.get("drift_simulacoes") or {},
    )
    historico_watchdog = (
        ler_estado(PASTA / "watchdog_estado.json").get("validacao") or {}
    ).get("historico_drift_simulacoes") or {}
    if (
        historico_drift["saudavel"]
        and historico_watchdog.get("total") == historico_drift.get("total")
    ):
        historico_drift["inseridos"] = int(
            historico_watchdog.get("inseridos") or 0
        )
        historico_drift["ignorados"] = int(
            historico_watchdog.get("ignorados") or 0
        )
    validacao["historico_drift_simulacoes"] = historico_drift
    imprimir_cortes_sombra(validacao)
    imprimir_hipoteses_sombra(PASTA / "monitor_packball.db")
    funil = validacao.get("funil_recente") or {}
    cobertura_candidatos = funil.get("cobertura_candidatos")
    cobertura_odds = funil.get("cobertura_odds_estruturadas")
    print(
        "funil recente: "
        f"{funil.get('estado', 'indisponível')} | "
        f"snapshots={funil.get('snapshots_ao_vivo', 0)} | "
        "recuperação excluídos="
        f"{funil.get('snapshots_recuperacao_excluidos', 0)} | "
        "liquidação excluídos="
        f"{funil.get('snapshots_liquidacao_excluidos', 0)} | "
        "candidatos="
        f"{cobertura_candidatos if cobertura_candidatos is not None else '-'} | "
        "odds estruturadas="
        f"{cobertura_odds if cobertura_odds is not None else '-'}"
    )
    fluxo = validacao.get("diagnostico_fluxo_sinais") or {}
    if fluxo:
        status_fluxo = fluxo.get("por_status") or {}
        principais = fluxo.get("principais_gargalos") or []
        gargalos_texto = ", ".join(
            f"{item.get('mercado')}:{item.get('motivo')}"
            f"({int(item.get('partidas', 0) or 0)} jogos)"
            for item in principais[:3]
        ) or "-"
        print(
            "fluxo de sinais (60 min): "
            f"{fluxo.get('estado', 'indisponivel')} | "
            f"avaliacoes={int(fluxo.get('observacoes', 0) or 0)} | "
            "aprovadas="
            f"{int((status_fluxo.get('aprovado') or {}).get('observacoes', 0) or 0)} | "
            "simulacoes="
            f"{int((status_fluxo.get('simulacao') or {}).get('observacoes', 0) or 0)} | "
            "entregues oficiais="
            f"{int(fluxo.get('entregues_oficiais', 0) or 0)} | "
            "entregues teste="
            f"{int(fluxo.get('entregues_teste', 0) or 0)} | "
            f"gargalos={gargalos_texto}"
        )
    comparacao_fluxo = validacao.get("comparacao_fluxo_sinais") or {}
    if comparacao_fluxo:
        janela_atual = comparacao_fluxo.get("atual") or {}
        janela_anterior = comparacao_fluxo.get("anterior") or {}
        print(
            "comparação de sinais (24h atual/anterior): "
            f"causa={comparacao_fluxo.get('causa_principal', '-')} | "
            f"métrica={comparacao_fluxo.get('metrica_volume', '-')} | "
            "entregues="
            f"{int(janela_atual.get('entregues', 0) or 0)}/"
            f"{int(janela_anterior.get('entregues', 0) or 0)} | "
            "oportunidades="
            f"{int(janela_atual.get('pares_com_oportunidade', 0) or 0)}/"
            f"{int(janela_anterior.get('pares_com_oportunidade', 0) or 0)} | "
            "partidas="
            f"{int(janela_atual.get('partidas', 0) or 0)}/"
            f"{int(janela_anterior.get('partidas', 0) or 0)} | "
            "altera sinais=não"
        )
    auditoria_ligas = validacao.get("auditoria_ligas_sombra") or {}
    if auditoria_ligas:
        partes_ligas = []
        for mercado, item in (
            auditoria_ligas.get("por_mercado") or {}
        ).items():
            prospectiva = item.get("validacao_prospectiva") or {}
            partes_ligas.append(
                f"{mercado}={item.get('estado')}"
                f"(n={int(item.get('amostra', 0) or 0)},"
                " candidatas="
                f"{len(item.get('ligas_exclusao_candidatas') or [])},"
                " prospectiva="
                f"{prospectiva.get('estado', 'sem_ancora_historica')}"
                f" {int(prospectiva.get('coorte', 0) or 0)}/"
                f"{int(prospectiva.get('coorte_alvo', 0) or 0)})"
            )
        print(
            "auditoria sombra de ligas: "
            + (" | ".join(partes_ligas) if partes_ligas else "sem dados")
            + " | aplicação automática=não"
        )
    regra_proximo_gol = (
        (validacao.get("conformidade_regras_operacionais") or {}).get(
            "proximo_gol"
        ) or {}
    )
    funil_proximo_gol = regra_proximo_gol.get("funil") or {}
    if funil_proximo_gol:
        criterios_proximo_gol = regra_proximo_gol.get("criterios") or {}
        odd_minima_proximo_gol = criterios_proximo_gol.get("odd_minima")
        odd_maxima_proximo_gol = criterios_proximo_gol.get(
            "odd_maxima_exclusiva"
        )
        faixa_odd_proximo_gol = (
            f"{odd_minima_proximo_gol:g}≤odd<{odd_maxima_proximo_gol:g}"
            if isinstance(odd_minima_proximo_gol, (int, float))
            and isinstance(odd_maxima_proximo_gol, (int, float))
            else "faixa atual"
        )
        cobertura_odd_proximo_gol = (
            regra_proximo_gol.get("cobertura_independente") or {}
        )
        print(
            "funil prospectivo próximo gol: decisões="
            f"{regra_proximo_gol.get('decisoes', 0)} | "
            "janela válida="
            f"{funil_proximo_gol.get('dentro_janela', 0)} | "
            "histórico 5min="
            f"{funil_proximo_gol.get('historico_5min', 0)} | "
            "atividade recente="
            f"{funil_proximo_gol.get('atividade_recente', 0)} | "
            f"{faixa_odd_proximo_gol}="
            f"{funil_proximo_gol.get('odd_minima', 0)} | "
            "sem bloqueios="
            f"{funil_proximo_gol.get('sem_outros_bloqueios', 0)} | "
            f"aprovadas={funil_proximo_gol.get('aprovadas', 0)}"
        )
        print(
            "  cobertura independente da odd: disponível="
            f"{cobertura_odd_proximo_gol.get('odd_disponivel', 0)} | "
            "fresca<=6min="
            f"{cobertura_odd_proximo_gol.get('odd_fresca', 0)} | "
            f"na {faixa_odd_proximo_gol}="
            f"{cobertura_odd_proximo_gol.get('odd_minima', 0)}"
        )
        bloqueios_proximo_gol = ", ".join(
            f"{item.get('motivo')}={item.get('quantidade')}"
            for item in regra_proximo_gol.get("bloqueios_principais") or []
        )
        if bloqueios_proximo_gol:
            print(
                "  bloqueios do próximo gol: "
                f"{bloqueios_proximo_gol}"
            )
    print(descrever_proximo_gol_balanceado(
        validacao.get("progresso_proximo_gol_balanceado_sombra") or {}
    ))
    try:
        diagnostico_funil_proximo_gol = (
            executar_diagnostico_funil_proximo_gol(
                PASTA / "monitor_packball.db"
            )
        )
    except Exception as erro:
        diagnostico_funil_proximo_gol = {"erro": type(erro).__name__}
    print(descrever_funil_marginal_proximo_gol(
        diagnostico_funil_proximo_gol
    ))
    print(descrever_quase_candidatos_proximo_gol(
        validacao.get("progresso_quase_candidatos_proximo_gol") or {}
    ))
    print(descrever_quase_candidatos_gol_ft(
        validacao.get("progresso_quase_candidatos_gol_ft") or {}
    ))
    features = validacao.get("features_temporais") or {}
    cobertura_features = features.get("cobertura")
    print(
        "features temporais: "
        f"{features.get('estado', 'indisponível')} | "
        f"schema={features.get('schema_versao') or '-'} | "
        f"candidatos={features.get('candidatos_validos', 0)}/"
        f"{features.get('candidatos', 0)} | "
        "cobertura="
        f"{cobertura_features if cobertura_features is not None else '-'} | "
        "janelas disponíveis 5/10/15="
        f"{features.get('janelas_disponiveis', {}).get('5', 0)}/"
        f"{features.get('janelas_disponiveis', {}).get('10', 0)}/"
        f"{features.get('janelas_disponiveis', {}).get('15', 0)} | "
        "duração medida 5/10/15="
        f"{features.get('duracoes_medidas', {}).get('5', 0)}/"
        f"{features.get('duracoes_medidas', {}).get('10', 0)}/"
        f"{features.get('duracoes_medidas', {}).get('15', 0)}"
    )
    with sqlite3.connect(
        (PASTA / "monitor_packball.db").resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=10,
    ) as conexao_contexto:
        conexao_contexto.row_factory = sqlite3.Row
        contexto = resumir_cobertura_contexto(conexao_contexto)
        avaliacao_contexto = avaliar_contexto_avancado(
            conexao_contexto,
            {
                mercado: versao_regra_para_mercado(mercado)
                for mercado in MERCADOS_CALIBRADOS
            },
            obter_limites_risco(),
        )
        historico_contexto = auditar_historico_avaliacao_contexto(
            conexao_contexto
        )
        exploracao_sombra = resumir_exploracoes_sombra(conexao_contexto)
        challenger_v2_ft = resumir_challenger_v2_ft(conexao_contexto)
        validacao_gols_antecipados = resumir_validacao_gols_antecipados(
            conexao_contexto
        )
        top_criterios_gols = resumir_top_criterios_gols(conexao_contexto)
    print(
        "experimentos prospectivos: "
        f"versão={exploracao_sombra['versao']} | modo=sombra | "
        "Telegram=não | aplicação automática=não | hipóteses="
        + ",".join(exploracao_sombra.get("versoes") or [])
    )
    for mercado, item in exploracao_sombra["por_mercado"].items():
        print(
            f"  exploração {mercado}: total={item['total']} | "
            f"pendentes={item['pendentes']} | "
            f"greens/reds={item['greens']}/{item['reds']} | "
            f"acerto={item['taxa_acerto']} | ROI={item['roi']}"
        )
    for versao, mercados in (
        exploracao_sombra.get("por_experimento") or {}
    ).items():
        total = sum(item["total"] for item in mercados.values())
        pendentes = sum(
            item["pendentes"] for item in mercados.values()
        )
        print(
            f"  hipótese {versao}: total={total} | "
            f"pendentes={pendentes}"
        )
    for mercado, item in (
        exploracao_sombra.get("validacao_prospectiva_gols") or {}
    ).items():
        if (
            mercado == "gol_ft"
            and exploracao_sombra.get("validacao_gol_ft_v2_controle")
        ):
            continue
        rotulo_validacao = (
            "V2 histórica gol_ft — congelada"
            if mercado == "gol_ft"
            else f"validação futura {mercado}"
        )
        print(
            f"  {rotulo_validacao}: "
            f"estado={item['estado']} | "
            f"resultados={item['avaliadas']}/"
            f"{item['minimo_resultados']} | faltam={item['faltam']} | "
            "coorte fixa="
            f"{item.get('candidatos_coorte', item['avaliadas'])}/"
            f"{item['minimo_resultados']} | disponíveis="
            f"{item.get('total_disponivel', item['avaliadas'])} | "
            "congelada="
            f"{'sim' if item.get('validacao_congelada') else 'não'} | "
            "linhagem="
            f"{'homogênea' if item.get('linhagem_homogenea', True) else 'inconsistente'} | "
            f"ROI={item['roi']} | IC95={item['intervalo_roi_95']} | "
            f"julgamento={item['decisao_estatistica']} | "
            f"política={item['politica_avaliacao_versao']} | "
            "aplicação automática=não"
        )
    validacao_ft_v3 = (
        exploracao_sombra.get("validacao_prospectiva_gol_ft_v3") or {}
    )
    if validacao_ft_v3:
        print(
            "  validacao futura gol_ft V3: "
            f"estado={validacao_ft_v3['estado']} | coorte="
            f"{validacao_ft_v3['candidatos_coorte']}/"
            f"{validacao_ft_v3['tamanho_coorte_fixa']} | faltam="
            f"{validacao_ft_v3['faltam_candidatos']} | resultados "
            f"validos={validacao_ft_v3['avaliadas']}/"
            f"{validacao_ft_v3['minimo_resultados_validos']} | "
            f"pendentes={validacao_ft_v3['pendentes']} | "
            f"invalidos={validacao_ft_v3['invalidos']} | "
            f"ROI={validacao_ft_v3['roi']} | "
            f"IC95={validacao_ft_v3['intervalo_roi_95']} | "
            f"julgamento={validacao_ft_v3['decisao_estatistica']} | "
            "chutes5>=1 | linhagem="
            f"{'compativel' if validacao_ft_v3['linhagem_compativel'] else 'inconsistente'} | "
            "Telegram oficial=nao | aplicacao automatica=nao"
        )
    validacao_ft_v2_controle = (
        exploracao_sombra.get("validacao_gol_ft_v2_controle") or {}
    )
    comparacao_ft_v2_v3 = (
        exploracao_sombra.get("comparacao_gol_ft_v2_controle_v3") or {}
    )
    if validacao_ft_v2_controle:
        print(descrever_comparacao_gol_ft_v2_v3(
            (
                exploracao_sombra.get("validacao_prospectiva_gols") or {}
            ).get("gol_ft") or {},
            validacao_ft_v2_controle,
            comparacao_ft_v2_v3,
        ))
    print(descrever_challenger_v2_ft(challenger_v2_ft))
    print(descrever_validacao_gols_antecipados(validacao_gols_antecipados))
    print(descrever_top_criterios_gols(top_criterios_gols))
    for mercado, item in (
        exploracao_sombra.get("cobertura_temporal_validacao_gols") or {}
    ).items():
        print(
            f"  cobertura explicativa {mercado}: "
            f"API temporal={item['com_evolucao_api']}/{item['total']} | "
            "comparação PackBall/API="
            f"{item['com_comparacao_fontes']}/{item['total']} | "
            f"concordância={item['taxa_concordancia_comparacoes']} | "
            "uso na decisão=não"
        )
    for mercado, item in (
        (exploracao_sombra.get("funil_recente_gols") or {})
        .get("por_mercado", {})
        .items()
    ):
        principais = list((item.get("bloqueios") or {}).items())[:3]
        print(
            f"  funil desde a validação {mercado}: tentativas="
            f"{item['tentativas_rejeitadas']} | partidas="
            f"{item['partidas_unicas']} | somente atividade="
            f"{item['somente_atividade']} | aptas="
            f"{item['aptas_reconstruidas']} | bloqueios="
            f"{principais}"
        )
    cobertura_contexto = contexto["cobertura"]
    print(
        "contexto avançado API "
        f"({'ativo' if os.getenv('API_CONTEXTO_AVANCADO_ATIVO', '1') == '1' else 'desligado'}) "
        "(modo sombra): "
        f"snapshots={contexto['snapshots']} | "
        "forma casa/fora="
        f"{cobertura_contexto['forma_mandante']}/"
        f"{cobertura_contexto['forma_visitante']} | "
        f"H2H={cobertura_contexto['h2h']} | "
        f"escalações={cobertura_contexto['escalacoes']} | "
        f"desfalques={cobertura_contexto['desfalques']} | "
        f"temporada={cobertura_contexto['estatisticas_temporada']} | "
        f"previsão={cobertura_contexto['previsao']} | "
        f"classificação={cobertura_contexto['classificacao']} | "
        f"histórico detalhado={cobertura_contexto['historico_detalhado']} | "
        "odds pré-jogo gols/escanteios="
        f"{cobertura_contexto['odds_pre_jogo_gols']}/"
        f"{cobertura_contexto['odds_pre_jogo_escanteios']} | "
        "estatísticas live API="
        f"{cobertura_contexto['estatisticas_ao_vivo']} | "
        f"jogadores live={cobertura_contexto['jogadores_ao_vivo']} | "
        f"eventos live={cobertura_contexto['eventos_ao_vivo']} | "
        f"métricas PackBall/API comparadas="
        f"{contexto['metricas_comparadas']} | concordância="
        f"{contexto['taxa_concordancia_fontes']}"
    )
    print(
        "avaliação do contexto avançado: "
        f"modo={avaliacao_contexto['modo']} | "
        "partidas independentes/resultados válidos="
        f"{avaliacao_contexto['amostra_total']}/"
        f"{avaliacao_contexto.get('resultados_validos_total', 0)} | "
        "aplicação automática=não | mercados prontos para revisão="
        f"{','.join(avaliacao_contexto['mercados_prontos_para_revisao']) or '-'}"
    )
    for mercado, item in avaliacao_contexto["por_mercado"].items():
        if item["base"].get("candidatos_independentes", 0) <= 0:
            continue
        segmentos_avaliaveis = [
            nome
            for nome, segmento in item["segmentos"].items()
            if segmento["avaliavel"]
        ]
        segmentos_conclusivos = [
            f"{nome}:{segmento['evidencia']}"
            for nome, segmento in item["segmentos"].items()
            if segmento["conclusivo"]
        ]
        print(
            f"  contexto {mercado}: coorte="
            f"{item['base'].get('candidatos_independentes', 0)}/"
            f"{TAMANHO_COORTE_CONTEXTO} | "
            f"válidos={item['base']['amostra']} | "
            "holdout válido="
            f"{(item.get('auditoria_coorte') or {}).get('resultados_validos_holdout', 0)}/"
            f"{TAMANHO_HOLDOUT_CONTEXTO} | "
            f"acerto={item['base']['taxa_acerto']} | "
            f"ROI={item['base']['roi']} | estado={item['base']['estado']} | "
            "segmentos avaliáveis="
            f"{','.join(segmentos_avaliaveis) or '-'} | "
            "conclusivos="
            f"{','.join(segmentos_conclusivos) or '-'}"
        )
    print(
        "histórico da avaliação de contexto: "
        f"{'íntegro' if historico_contexto['saudavel'] else 'inconsistente'} | "
        f"registros={historico_contexto['total']} | "
        f"mercados={historico_contexto['mercados']} | "
        f"prontos V6={historico_contexto['prontos']} | "
        "prontos metodologia antiga="
        f"{historico_contexto.get('prontos_metodologia_antiga', 0)} | "
        f"último={historico_contexto['ultimo'] or '-'}"
    )
    pontuacao_sombra = validacao.get("pontuacao_sombra") or {}
    print(
        "pontuação candidata prospectiva: "
        f"modo={pontuacao_sombra.get('modo') or 'sombra'} | "
        f"{'íntegra' if pontuacao_sombra.get('integro') else 'inconsistente'} | "
        "modelos congelados="
        f"{','.join(pontuacao_sombra.get('mercados_com_modelo') or []) or '-'} | "
        "prontos para revisão="
        f"{','.join(pontuacao_sombra.get('mercados_prontos_para_revisao') or []) or '-'} | "
        "aplicação automática=não"
    )
    for mercado, item in (
        pontuacao_sombra.get("por_mercado") or {}
    ).items():
        if not item.get("amostra_total"):
            continue
        metricas_auc_sombra = item.get("auc_sombra") or {}
        auc_sombra = metricas_auc_sombra.get("auc")
        auc_sombra_inferior = metricas_auc_sombra.get(
            "limite_inferior_auc_95"
        )
        auc_atual = (item.get("auc_nota_atual") or {}).get("auc")
        print(
            f"  score {mercado}: estado={item.get('estado')} | "
            f"treino={item.get('treino', 0)} | "
            f"validação futura={item.get('validacao', 0)}/"
            f"{item.get('amostra_minima_validacao', 30)} | "
            f"AUC candidata/atual={auc_sombra}/{auc_atual} | "
            f"AUC95 inferior={auc_sombra_inferior} | "
            "Brier candidata/odd="
            f"{item.get('brier_sombra')}/{item.get('brier_odd')} | "
            f"faltam={item.get('faltam_validacao', '-')}"
        )
    pontuacao_longa = validacao.get("pontuacao_longa_sombra") or {}
    if pontuacao_longa:
        print(
            "challenger temporal longo V2: "
            f"modo={pontuacao_longa.get('modo') or 'sombra'} | "
            f"{'íntegro' if pontuacao_longa.get('integro') else 'inconsistente'} | "
            "modelos congelados="
            f"{','.join(pontuacao_longa.get('mercados_com_modelo') or []) or '-'} | "
            "prontos para revisão="
            f"{','.join(pontuacao_longa.get('mercados_prontos_para_revisao') or []) or '-'} | "
            "janelas obrigatórias=5/10/15 | aplicação automática=não"
        )
        for mercado, item in (
            pontuacao_longa.get("por_mercado") or {}
        ).items():
            metricas_auc_longa = item.get("auc_longa") or {}
            auc_longa = metricas_auc_longa.get("auc")
            auc_longa_inferior = metricas_auc_longa.get(
                "limite_inferior_auc_95"
            )
            auc_atual = (item.get("auc_nota_atual") or {}).get("auc")
            print(
                f"  longo {mercado}: estado={item.get('estado')} | "
                f"treino prospectivo={item.get('treino', 0)}/"
                f"{item.get('amostra_minima_treino', 60)} | "
                f"validação futura={item.get('validacao', 0)}/"
                f"{item.get('amostra_minima_validacao', 30)} | "
                f"AUC longa/atual={auc_longa}/{auc_atual} | "
                f"AUC95 inferior={auc_longa_inferior} | "
                "Brier longa/odd="
                f"{item.get('brier_longa')}/{item.get('brier_odd')} | "
                f"faltam treino={item.get('faltam_treino', 0)} | "
                f"faltam validação={item.get('faltam_validacao', 30)}"
            )
    pontuacao_contexto = (
        validacao.get("pontuacao_contexto_sombra") or {}
    )
    print(
        "challenger com contexto API V4: "
        f"modo={pontuacao_contexto.get('modo') or 'sombra'} | "
        f"{'íntegro' if pontuacao_contexto.get('integro') else 'inconsistente'} | "
        "modelos congelados="
        f"{','.join(pontuacao_contexto.get('mercados_com_modelo') or []) or '-'} | "
        "prontos para revisão="
        f"{','.join(pontuacao_contexto.get('mercados_prontos_para_revisao') or []) or '-'} | "
        "aplicação automática=não"
    )
    for mercado, item in (
        pontuacao_contexto.get("por_mercado") or {}
    ).items():
        if not item.get("amostra_base"):
            continue
        metricas_auc_contexto = item.get("auc_contexto") or {}
        auc_contexto = metricas_auc_contexto.get("auc")
        auc_contexto_inferior = metricas_auc_contexto.get(
            "limite_inferior_auc_95"
        )
        auc_atual = (item.get("auc_nota_atual") or {}).get("auc")
        print(
            f"  contexto {mercado}: estado={item.get('estado')} | "
            f"amostra V4={item.get('amostra_total', 0)}/"
            f"{item.get('amostra_minima_treino', 60)} | "
            f"classes G/R={item.get('greens', '-')}/"
            f"{item.get('reds', '-')} | "
            f"validação futura={item.get('validacao', 0)}/"
            f"{item.get('amostra_minima_validacao', 30)} | "
            f"AUC contexto/atual={auc_contexto}/{auc_atual} | "
            f"AUC95 inferior={auc_contexto_inferior} | "
            "Brier contexto/odd="
            f"{item.get('brier_contexto')}/{item.get('brier_odd')}"
        )
    print(
        "saúde da validação: "
        f"{'saudável' if validacao['saudavel'] else 'degradada'} | "
        "atenção="
        f"{'sim' if validacao.get('requer_atencao') else 'não'} | "
        f"vencidas={validacao.get('pendencias_vencidas', 0)} | "
        "longas ainda ativas="
        f"{validacao.get('pendencias_longas_ativas', 0)}"
    )
    print(
        "antispam da validação: "
        "confirmação alerta/recuperação=3/3 ciclos | "
        "cooldown=6h | causas aguardando confirmação="
        f"{','.join(validacao.get('alerta_validacao_causas_pendentes') or []) or '-'} | "
        "ciclos saudáveis consecutivos="
        f"{validacao.get('alerta_validacao_ciclos_recuperacao', 0)}"
    )
    auditoria_filtro = validacao.get("experimento_filtro") or {}
    print(
        "integridade do experimento do filtro: "
        f"{auditoria_filtro.get('estado', 'indisponivel')} | "
        f"protegido={'sim' if auditoria_filtro.get('protegido') else 'nao'} | "
        f"inicio={auditoria_filtro.get('iniciado_em') or '-'} | "
        "filtradas anteriores ao marco="
        f"{auditoria_filtro.get('decisoes_filtradas_anteriores', 0)} | "
        "decisoes auditadas enviadas/filtradas="
        f"{auditoria_filtro.get('decisoes_enviadas_auditadas', 0)}/"
        f"{auditoria_filtro.get('decisoes_filtradas_auditadas', 0)} | "
        "envios fora do criterio="
        f"{auditoria_filtro.get('simulacoes_enviadas_fora_criterio', 0)} | "
        "motivos de filtro incoerentes="
        f"{auditoria_filtro.get('filtros_motivo_incoerente', 0)}"
    )
    imprimir_conclusao_experimento_filtro(validacao)
    drift_simulacoes = validacao.get("drift_simulacoes") or {}
    print(
        "drift das simulações por mercado: "
        f"{drift_simulacoes.get('estado', 'indisponivel')} | "
        "mercados degradados="
        f"{','.join(drift_simulacoes.get('mercados_degradados') or []) or '-'} "
        "| confirmados="
        f"{','.join(validacao.get('drift_simulacoes_mercados_confirmados') or []) or '-'} "
        "| ajuste automático="
        f"{'sim' if drift_simulacoes.get('ajuste_automatico') else 'não'}"
    )
    historico_drift = validacao.get("historico_drift_simulacoes") or {}
    print(
        "historico persistente do drift: "
        f"{historico_drift.get('estado', 'indisponivel')} | "
        f"registros={historico_drift.get('total', 0)} | "
        f"mercados={historico_drift.get('mercados', 0)} | "
        f"novos neste ciclo={historico_drift.get('inseridos', 0)} | "
        f"ultimo={historico_drift.get('ultimo_registro_em') or '-'}"
    )
    for mercado, drift in sorted(
        (drift_simulacoes.get("mercados") or {}).items()
    ):
        if mercado == "geral":
            continue
        print(
            f"  drift {mercado}: {drift.get('estado')} | "
            f"base={drift.get('amostra_base', 0)} | "
            f"recente={drift.get('amostra_recente', 0)} | "
            f"ROI base/recente={drift.get('roi_base')}/"
            f"{drift.get('roi_recente')} | "
            f"delta={drift.get('delta_roi')} | "
            f"IC95={drift.get('intervalo_delta_roi_95')}"
        )
    proveniencia = validacao.get("proveniencia_resultados") or {}
    print(
        "proveniência dos resultados: "
        f"{'saudável' if proveniencia.get('saudavel') else 'degradada'} | "
        f"coerentes={proveniencia.get('coerentes', 0)}/"
        f"{proveniencia.get('total', 0)} | "
        f"inconsistentes={proveniencia.get('inconsistentes', 0)} | "
        "times API validados="
        f"{proveniencia.get('api_times_validados', 0)} | "
        f"ausentes={proveniencia.get('api_times_ausentes', 0)} | "
        "incompatíveis="
        f"{proveniencia.get('api_times_incompativeis', 0)}"
    )
    valor_mercado = validacao.get("valor_mercado_sinais") or {}
    print(
        "valor conservador dos sinais: "
        f"{'saudável' if valor_mercado.get('saudavel') else 'degradado'} | "
        f"versão={valor_mercado.get('versao') or '-'} | "
        f"calibrados={valor_mercado.get('sinais_calibrados', 0)} | "
        "com/sem valor="
        f"{valor_mercado.get('com_valor_conservador', 0)}/"
        f"{valor_mercado.get('sem_valor_conservador', 0)} | "
        "referência sem vig presente/ausente="
        f"{valor_mercado.get('com_referencia_sem_vig', 0)}/"
        f"{valor_mercado.get('sem_referencia_sem_vig', 0)} | "
        "margens incoerentes bloqueadas="
        f"{valor_mercado.get('referencias_margem_incoerente', 0)} | "
        "entregues oficiais sem valor="
        f"{valor_mercado.get('entregues_oficiais_sem_valor', 0)} | "
        "rastros válidos/ausentes/divergentes="
        f"{valor_mercado.get('rastros_validos', 0)}/"
        f"{valor_mercado.get('rastros_ausentes', 0)}/"
        f"{valor_mercado.get('rastros_divergentes', 0)} | "
        "oficiais com rastro inválido="
        f"{valor_mercado.get('entregues_oficiais_rastro_invalido', 0)}"
    )
    integridade_telegram = validacao.get("integridade_telegram") or {}
    print(
        "integridade Telegram: "
        f"{'saudável' if integridade_telegram.get('saudavel_operacional', integridade_telegram.get('saudavel')) else 'degradada'} | "
        "auditoria completa="
        f"{'sim' if integridade_telegram.get('saudavel') else 'pendente'} | "
        "resultados sem aviso="
        f"{integridade_telegram.get('resultados_sem_aviso', 0)} | "
        "oficiais/análises="
        f"{integridade_telegram.get('resultados_oficiais_sem_aviso', 0)}/"
        f"{integridade_telegram.get('resultados_analise_sem_aviso', 0)} | "
        "avisos sem resultado="
        f"{integridade_telegram.get('avisos_sem_resultado', 0)} | "
        "erros persistentes="
        f"{integridade_telegram.get('erros_persistentes', 0)} | "
        "correcoes pendentes="
        f"{integridade_telegram.get('correcoes_pendentes', 0)} | "
        "resultados duplicados="
        f"{integridade_telegram.get('resultados_duplicados', 0)} | "
        "bloqueios gateway 24h="
        f"{integridade_telegram.get('bloqueios_gateway_24h', 0)} | "
        "envios incertos="
        f"{integridade_telegram.get('envios_incertos', 0)} | "
        "oficiais/análises="
        f"{integridade_telegram.get('envios_oficiais_incertos', 0)}/"
        f"{integridade_telegram.get('envios_analise_incertos', 0)} | "
        "provas Telegram válidas="
        f"{integridade_telegram.get('confirmacoes_telegram_validas', 0)} | "
        "inválidas="
        f"{integridade_telegram.get('confirmacoes_telegram_invalidas', 0)} | "
        "reutilizadas="
        f"{integridade_telegram.get('confirmacoes_telegram_duplicadas', 0)} | "
        "legado sem prova="
        f"{integridade_telegram.get('entregas_telegram_legadas_sem_prova', 0)}"
    )
    if integridade_telegram.get("envios_oficiais_incertos", 0):
        print(
            "AÇÃO NECESSÁRIA: novas entradas oficiais estão pausadas. "
            "Confira o Telegram e execute "
            "'python resolver_envio_incerto.py'."
        )
    elif integridade_telegram.get("envios_analise_incertos", 0):
        print(
            "CONFERÊNCIA PENDENTE: há resultado(s) antigo(s) de análise com "
            "entrega ambígua; novas análises não estão pausadas."
        )
    notificacoes_operacionais = (
        validacao.get("notificacoes_operacionais") or {}
    )
    print(
        "notificações operacionais: "
        f"{'saudável' if notificacoes_operacionais.get('saudavel') else 'degradada'} | "
        "entregues com prova="
        f"{notificacoes_operacionais.get('entregues_com_prova', 0)} | "
        "destinos configurados="
        f"{notificacoes_operacionais.get('destinos_configurados', 0)} | "
        f"incertas={notificacoes_operacionais.get('incertas', 0)} | "
        "erros persistentes="
        f"{notificacoes_operacionais.get('erros_persistentes', 0)} | "
        "disjuntor="
        f"{'pausado' if notificacoes_operacionais.get('disjuntor_pausado') else 'liberado'} | "
        "próxima tentativa="
        f"{notificacoes_operacionais.get('proxima_tentativa_em') or '-'} | "
        f"provas inválidas={notificacoes_operacionais.get('provas_invalidas', 0)} | "
        f"reutilizadas={notificacoes_operacionais.get('provas_duplicadas', 0)}"
    )
    cache_api = validacao.get("cache_api_football") or {}
    print(
        "cache persistente API-Football: "
        f"{'saudável' if cache_api.get('saudavel') else 'degradado'} | "
        f"itens={cache_api.get('total', 0)} | "
        f"expirados={cache_api.get('expirados', 0)} | "
        f"payloads inválidos={cache_api.get('payloads_invalidos', 0)} | "
        f"relógios futuros={cache_api.get('relogios_futuros', 0)} | "
        f"tamanho={cache_api.get('tamanho_json_mb', 0)}MB"
    )
    armazenamento = validacao.get("armazenamento") or {}
    dias_armazenamento = armazenamento.get("dias_ate_limite")
    crescimento_endpoint = armazenamento.get(
        "crescimento_endpoint_mb_dia"
    )
    detalhe_endpoint = (
        f" | variação bruta entre extremos={crescimento_endpoint}MB/dia"
        if crescimento_endpoint is not None else ""
    )
    print(
        "armazenamento SQLite: "
        f"banco={armazenamento.get('banco_mb', '-')}MB | "
        f"WAL={armazenamento.get('wal_mb', '-')}MB | "
        f"backups={armazenamento.get('backups_mb', '-')}MB "
        f"({armazenamento.get('backups_arquivos', '-')} arquivos) | "
        f"livre={armazenamento.get('livre_mb', '-')}MB | "
        "crescimento recorrente="
        f"{armazenamento.get('crescimento_mb_dia', '-')}MB/dia | "
        "método="
        f"{armazenamento.get('metodo_tendencia', '-')}"
        f"{detalhe_endpoint} | "
        "previsão até reserva="
        f"{dias_armazenamento if dias_armazenamento is not None else '-'} dias"
    )
    retencao_backups = armazenamento.get("retencao_backups") or {}
    print(
        "retenção dos backups: "
        f"{'dentro da política' if retencao_backups.get('saudavel') else 'revisão pendente'} | "
        f"excedentes={retencao_backups.get('quantidade', 0)} | "
        f"tamanho={retencao_backups.get('tamanho_mb', 0)}MB | "
        f"protegidos={retencao_backups.get('protegidos', 0)} "
        f"({retencao_backups.get('protegidos_mb', 0)}MB) | "
        "auditoria remove arquivos=não"
    )
    print(
        "compactação dos backups: "
        f"{'ativa' if armazenamento.get('compactacao_ativa') else 'desligada'} | "
        f"estado={armazenamento.get('estado_compactacao', '-')} | "
        f"compactados/legados={armazenamento.get('backups_compactados', 0)}/"
        f"{armazenamento.get('backups_legados', 0)} | "
        f"economia={armazenamento.get('economia_compactacao_mb', 0)}MB | "
        "rollback="
        f"{armazenamento.get('rollback_compactacao') or 'BACKUP_COMPACTACAO_ATIVA=0'}"
    )
    drill_backup = validacao.get("drill_restauracao_compactada") or {}
    print(
        "drill de restauração compactada: "
        f"estado={drill_backup.get('estado', 'indisponível')} | "
        f"backup={drill_backup.get('backup', '-')} | "
        "último teste="
        f"{drill_backup.get('testado_em', '-')} | "
        "banco ativo alterado=não"
    )
    frescor = validacao.get("frescor_calibracoes") or {}
    print(
        "frescor das calibrações ativas: "
        f"{'saudável' if frescor.get('saudavel') else 'degradado'} | "
        f"ativas={frescor.get('ativas', 0)} | "
        f"desatualizadas={frescor.get('desatualizadas', 0)}"
    )
    if validacao.get("motivos") or validacao.get("avisos"):
        print(
            "  motivos: "
            + ", ".join(
                (validacao.get("motivos") or [])
                + (validacao.get("avisos") or [])
            )
        )
    contador_api = validacao.get("contador_api") or {}
    consumo_api = contador_api.get("consumo_dia")
    limite_api = contador_api.get("limite_diario_seguro")
    restante_api = contador_api.get("restante_seguro_dia")
    print(
        "contador da API: "
        f"{contador_api.get('estado', 'indisponível')} | "
        f"origem={contador_api.get('origem') or '-'} | "
        "hoje="
        f"{consumo_api if consumo_api is not None else '-'}/"
        f"{limite_api if limite_api is not None else '-'} | "
        "restante="
        f"{restante_api if restante_api is not None else '-'} | "
        "novas chamadas="
        f"{'permitidas' if contador_api.get('saudavel') else 'bloqueadas'}"
    )
    cota_provedor_texto = descrever_cota_provedor(contador_api)
    if cota_provedor_texto:
        print(cota_provedor_texto)
    estado_odds_api = validacao.get("estado_odds_api") or {}
    catalogo_odds_live = validacao.get("catalogo_odds_live") or {}
    print(
        "catálogo API de odds ao vivo: estado="
        f"{catalogo_odds_live.get('estado', 'indisponível')} | idade="
        f"{catalogo_odds_live.get('idade_horas', '-')}h | "
        "Asian Corners 2T="
        f"{'disponível' if catalogo_odds_live.get('asiatico_2t_disponivel') else 'não oferecido'} | "
        "divergências="
        f"{','.join(catalogo_odds_live.get('divergencias') or []) or '-'}"
    )
    print(
        "odds ao vivo API-Football: estado="
        f"{estado_odds_api.get('estado', 'indisponível')} | consultas="
        f"{estado_odds_api.get('consultas', 0)} | com oferta global="
        f"{estado_odds_api.get('com_ofertas_globais', 0)} | sem oferta="
        f"{estado_odds_api.get('sem_ofertas_globais', 0)} | falhas="
        f"{estado_odds_api.get('falhas', 0)} | última consulta="
        f"{estado_odds_api.get('ultima_consulta_em') or '-'} | "
        "último bet="
        f"{estado_odds_api.get('ultimo_bet_id') or '-'} | "
        "última oferta="
        f"{estado_odds_api.get('ultima_oferta_em') or '-'}"
    )
    mercados_odds_api = (
        ("25", "gols FT"),
        ("32", "escanteios FT"),
        ("51", "escanteios 1T"),
        ("73", "próximo 1º gol"),
        ("84", "próximo 2º gol"),
        ("92", "próximo 3º gol"),
        ("109", "próximo 4º gol"),
        ("112", "próximo 5º gol"),
        ("127", "próximo 6º gol"),
        ("132", "próximo 7º gol"),
    )
    for bet_id, rotulo in mercados_odds_api:
        por_bet = (estado_odds_api.get("por_bet") or {}).get(bet_id) or {}
        motivos = por_bet.get("rejeicoes_por_motivo") or {}
        resumo_motivos = ", ".join(
            f"{motivo}={quantidade}"
            for motivo, quantidade in sorted(motivos.items())
        ) or "-"
        print(
            f"  bet {bet_id} {rotulo}: consultas="
            f"{por_bet.get('consultas', 0)} | globais="
            f"{por_bet.get('com_ofertas_globais', 0)} | solicitações="
            f"{por_bet.get('solicitacoes_fixture', 0)} | fixtures="
            f"{por_bet.get('fixtures_correspondentes', 0)} | anexadas="
            f"{por_bet.get('ofertas_anexadas', 0)} | rejeitadas="
            f"{por_bet.get('ofertas_rejeitadas', 0)} | última anexada="
            f"{por_bet.get('ultima_oferta_anexada_em') or '-'} | "
            "última rejeição="
            f"{por_bet.get('ultimo_motivo_rejeicao') or '-'} | "
            "sem diagnóstico legado="
            f"{por_bet.get('rejeicoes_sem_diagnostico', 0)} | "
            "vazias consecutivas="
            f"{por_bet.get('sem_ofertas_consecutivas', 0)} | "
            "consultas suprimidas="
            f"{por_bet.get('consultas_suprimidas', 0)} | "
            "suspenso atÃ©="
            f"{por_bet.get('suspenso_ate') or '-'} | "
            f"motivos={resumo_motivos}"
        )
    estado_watchdog = estado_watchdog_status
    validacao_watchdog = estado_watchdog.get("validacao") or {}
    persistencia_watchdog = (
        estado_watchdog.get("persistencia_estado_watchdog") or {}
    )
    recuperacao_watchdog = (
        estado_watchdog.get("recuperacao_estado_watchdog") or {}
    )
    print(
        "estado persistente do watchdog: "
        f"{persistencia_watchdog.get('estado') or 'indisponivel'} | "
        f"saudavel={'sim' if persistencia_watchdog.get('saudavel') else 'nao'} | "
        f"ultimo espelho={persistencia_watchdog.get('persistido_em') or '-'}"
    )
    print(
        "recuperacao do estado do watchdog: "
        f"origem={recuperacao_watchdog.get('origem') or '-'} | "
        f"recuperado={'sim' if recuperacao_watchdog.get('recuperado') else 'nao'} | "
        f"motivo={recuperacao_watchdog.get('motivo') or '-'}"
    )
    print(descrever_integridade_banco_ativo(
        estado_watchdog.get("integridade_banco_ativo") or {}
    ))
    experimento_ritmo = (
        validacao_watchdog.get("experimento_ritmo_packball") or {}
    )
    base_ritmo = experimento_ritmo.get("base") or {}
    teste_ritmo = experimento_ritmo.get("experimento") or {}
    print(
        "avaliação persistente do ritmo PackBall: "
        f"{experimento_ritmo.get('estado') or 'aguardando'} | "
        f"ciclos={teste_ritmo.get('ciclos', 0)}/"
        f"{experimento_ritmo.get('minimo_ciclos', '-')} | "
        f"observação={experimento_ritmo.get('minutos_observados', '-')}min | "
        "fluxo base/atual="
        f"{base_ritmo.get('processadas_por_10_minutos', '-')}/"
        f"{teste_ritmo.get('processadas_por_10_minutos', '-')} por 10min | "
        "cobertura temporal base/atual="
        f"{base_ritmo.get('cobertura_temporal', '-')}/"
        f"{teste_ritmo.get('cobertura_temporal', '-')} | "
        "incidentes na revalidacao="
        f"{experimento_ritmo.get('pausas_na_revalidacao', 0)} | "
        "incidentes historicos="
        f"{experimento_ritmo.get('pausas_packball_historicas', experimento_ritmo.get('pausas_packball', 0))} | "
        f"janela desde={experimento_ritmo.get('iniciado_em') or '-'}"
    )
    print(
        "janelas temporais acumuladas no ritmo atual: "
        f"{descrever_janelas_temporais_ritmo(teste_ritmo)}"
    )
    print(descrever_cobertura_temporal_priorizada(experimento_ritmo))
    resumo_diario = validacao_watchdog.get("resumo_operacao_diaria") or {}
    print(
        "resumo diário Telegram: "
        "último enviado="
        f"{validacao_watchdog.get('resumo_diario_enviado_em') or '-'} | "
        f"dia observado={resumo_diario.get('dia') or '-'} | "
        f"horário={os.getenv('HORA_RESUMO_DIARIO', '18')}:00"
    )
    processo_watchdog = ler_estado(PASTA / "watchdog_processo.json")
    pid_watchdog = processo_watchdog.get("pid")
    pid_watchdog_ativo = pid_ativo(pid_watchdog)
    trava_watchdog = trava_em_uso(PASTA / "watchdog_instancia.lock")
    codigo_watchdog = estado_codigo_runtime(
        PASTA, processo_watchdog, ARQUIVOS_RUNTIME_WATCHDOG
    )
    estado_codigo_watchdog = {
        "atualizado": "atualizado",
        "reinicio_pendente": "reinício pendente",
        "desconhecido": "desconhecido; reinicie para registrar",
    }[codigo_watchdog]
    print(
        "processo watchdog: "
        f"{processo_watchdog.get('status', 'não registrado')} | "
        f"pid={pid_watchdog or '-'} | "
        f"pid ativo={'sim' if pid_watchdog_ativo else 'não'} | "
        f"trava={'ocupada' if trava_watchdog else 'livre'} | "
        "instância="
        f"{'confirmada' if pid_watchdog_ativo and trava_watchdog else 'divergente'} | "
        f"código={estado_codigo_watchdog}"
    )
    processo_monitor = ler_estado(PASTA / "monitor_processo.json")
    pid_monitor = processo_monitor.get("pid")
    pid_monitor_ativo = pid_ativo(pid_monitor)
    trava_monitor = trava_em_uso(PASTA / "monitor_instancia.lock")
    codigo = estado_codigo_runtime(PASTA, processo_monitor)
    estado_codigo = {
        "atualizado": "atualizado",
        "reinicio_pendente": "reinício pendente",
        "desconhecido": "desconhecido; reinicie para registrar",
    }[codigo]
    print(
        "processo monitor: "
        f"{processo_monitor.get('status', 'não registrado')} | "
        f"pid={pid_monitor or '-'} | "
        f"pid ativo={'sim' if pid_monitor_ativo else 'não'} | "
        f"trava={'ocupada' if trava_monitor else 'livre'} | "
        "instância="
        f"{'confirmada' if pid_monitor_ativo and trava_monitor else 'divergente'} | "
        f"código={estado_codigo}"
    )
    autostart = consultar_autostart(pasta=Path(__file__).parent)
    estado_autostart = descrever_autostart(autostart)
    print(
        "recuperação após reinício do Windows: "
        f"{estado_autostart} | intervalo=5min | "
        "monitor visível=sim | divergências="
        f"{','.join(autostart.get('divergencias') or []) or '-'}"
    )
    pasta_backups = PASTA / "backups"
    backups = sorted(BackupBanco._glob_formatos(
        pasta_backups, "monitor_*.db"
    ))
    periodicos = sorted(BackupBanco._glob_formatos(
        pasta_backups, "periodico_*.db"
    ))
    print(
        "backups disponíveis: "
        f"diários={len(backups)} | periódicos={len(periodicos)}"
    )
    if backups:
        print(f"backup diário mais recente: {backups[-1].name}")
        verificacao = verificar_arquivo_backup(backups[-1])
        print(
            "integridade do backup: "
            f"{'válida' if verificacao['valido'] else 'inválida'} | "
            f"motivo={verificacao.get('motivo') or 'nenhum'}"
        )
    recuperacao = verificar_ponto_recuperacao(pasta_backups)
    caminho_recuperacao = recuperacao.get("caminho")
    nome_recuperacao = (
        Path(caminho_recuperacao).name if caminho_recuperacao else "-"
    )
    print(
        "ponto de recuperação (RPO): "
        f"{'saudável' if recuperacao['saudavel'] else 'degradado'} | "
        f"mais recente={nome_recuperacao} | "
        f"idade={recuperacao.get('idade_minutos', '-')}min | "
        f"limite={recuperacao.get('limite_minutos', 375)}min | "
        f"motivo={recuperacao.get('motivo') or 'nenhum'}"
    )
    print(descrever_recuperacao_banco(ler_recuperacao_banco(
        PASTA / "recuperacao_banco_estado.json"
    )))
    prontidao = avaliar_prontidao(coletar_evidencias(PASTA))
    print(descrever_clv_live(prontidao))
    print(descrever_portfolio_edge(prontidao))
    liberados = prontidao["mercados_liberados_para_oficial"]
    print(
        "prontidão profissional: "
        f"{prontidao['estado_geral']} | "
        "mercados oficiais liberados="
        f"{', '.join(liberados) if liberados else 'nenhum'} | "
        f"pendências={len(prontidao['pendencias'])}"
    )
    for linha in descrever_pendencias_prontidao(prontidao):
        print(linha)
    print(descrever_escanteios_ft_asiatico(prontidao, estado_odds_api))


if __name__ == "__main__":
    main()
