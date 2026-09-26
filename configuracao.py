import math
import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LimitesRisco:
    limite_diario_sinais: int = 10
    odd_minima: float = 1.4
    odd_maxima: float = 2.5
    limite_exposicao_diaria: float = 5.0
    limite_reds_consecutivos_oficiais: int = 3
    limite_perda_diaria_oficial: float = 3.0


@dataclass(frozen=True)
class LimitesAPI:
    limite_diario: int = 7500
    reserva_diaria: int = 500
    limite_diario_detalhes: int = 2000


def _inteiro(env, nome, padrao, minimo, maximo, erros):
    try:
        valor = int(env.get(nome, padrao))
    except (TypeError, ValueError):
        erros.append(f"{nome} deve ser um número inteiro")
        return padrao
    if not minimo <= valor <= maximo:
        erros.append(f"{nome} deve ficar entre {minimo} e {maximo}")
    return valor


def _decimal(env, nome, padrao, minimo, maximo, erros):
    try:
        valor = float(env.get(nome, padrao))
    except (TypeError, ValueError):
        erros.append(f"{nome} deve ser um número")
        return padrao
    if not minimo <= valor <= maximo:
        erros.append(f"{nome} deve ficar entre {minimo} e {maximo}")
    return valor


def validar_configuracao(env=None):
    env = os.environ if env is None else env
    erros = []
    avisos = []
    limite_diario = _inteiro(
        env, "LIMITE_DIARIO_SINAIS", 10, 0, 100, erros
    )
    limite_teste = _inteiro(
        env, "LIMITE_DIARIO_SINAIS_TESTE", 30, 0, 100, erros
    )
    limite_teste_global = _inteiro(
        env, "LIMITE_GLOBAL_SINAIS_TESTE", 45, 0, 200, erros
    )
    _decimal(
        env, "PONTUACAO_MINIMA_SINAL_TESTE", 70, 0, 100, erros
    )
    _decimal(
        env,
        "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE",
        env.get("PONTUACAO_MINIMA_SINAL_TESTE", 70),
        0,
        100,
        erros,
    )
    pontuacao_minima_proximo_gol_balanceado = _decimal(
        env,
        "PONTUACAO_MINIMA_PROXIMO_GOL_BALANCEADO_TESTE",
        60,
        0,
        100,
        erros,
    )
    _decimal(
        env, "QUALIDADE_MINIMA_SINAL_TESTE", 0, 0, 100, erros
    )
    if limite_teste_global < limite_teste:
        erros.append(
            "LIMITE_GLOBAL_SINAIS_TESTE não pode ser menor que "
            "LIMITE_DIARIO_SINAIS_TESTE"
        )
    odd_minima = _decimal(env, "ODD_MINIMA_SINAL", 1.4, 1.01, 20, erros)
    odd_maxima = _decimal(env, "ODD_MAXIMA_SINAL", 2.5, 1.01, 20, erros)
    aviso_odd_piso = _decimal(
        env, "AVISO_AGUARDAR_ODD_PISO", 1.10, 1.01, 20, erros
    )
    aviso_odd_alvo = _decimal(
        env, "AVISO_AGUARDAR_ODD_ALVO", odd_minima, 1.01, 20, erros
    )
    _decimal(
        env, "AVISO_AGUARDAR_ODD_NOTA_MINIMA", 70, 0, 100, erros
    )
    _decimal(
        env, "AVISO_AGUARDAR_ODD_QUALIDADE_MINIMA", 80, 0, 100, erros
    )
    exposicao = _decimal(
        env, "LIMITE_EXPOSICAO_DIARIA", 5.0, 0.1, 100, erros
    )
    reds_consecutivos = _inteiro(
        env, "LIMITE_REDS_CONSECUTIVOS_OFICIAIS", 3, 1, 20, erros
    )
    perda_diaria = _decimal(
        env, "LIMITE_PERDA_DIARIA_OFICIAL", 3.0, 0.1, 100, erros
    )
    limite_api_diario = _inteiro(
        env, "API_LIMITE_DIARIO", 7500, 1, 100000, erros
    )
    reserva_api_diaria = _inteiro(
        env, "API_RESERVA_DIARIA", 500, 0, 99999, erros
    )
    limite_api_detalhes = _inteiro(
        env, "API_LIMITE_DETALHES_DIARIO", 2000, 0, 100000, erros
    )
    stats_resgate_max_ciclo = _inteiro(
        env, "API_STATS_RESGATE_MAX_CICLO", 2, 0, 5, erros
    )
    if odd_minima >= odd_maxima:
        erros.append("ODD_MINIMA_SINAL deve ser menor que ODD_MAXIMA_SINAL")
    if aviso_odd_piso >= aviso_odd_alvo:
        erros.append(
            "AVISO_AGUARDAR_ODD_PISO deve ser menor que "
            "AVISO_AGUARDAR_ODD_ALVO"
        )
    limite_api_seguro = limite_api_diario - reserva_api_diaria
    if reserva_api_diaria >= limite_api_diario:
        erros.append("API_RESERVA_DIARIA deve ser menor que API_LIMITE_DIARIO")
    if limite_api_detalhes > max(limite_api_seguro, 0):
        erros.append(
            "API_LIMITE_DETALHES_DIARIO não pode ultrapassar o limite diário seguro"
        )
    if env.get("WATCHDOG_REINICIO_AUTOMATICO", "1") not in ("0", "1"):
        erros.append("WATCHDOG_REINICIO_AUTOMATICO deve ser 0 ou 1")
    if env.get("SINAIS_TESTE_ATIVO", "0") not in ("0", "1"):
        erros.append("SINAIS_TESTE_ATIVO deve ser 0 ou 1")
    if env.get("AVISO_AGUARDAR_ODD_ATIVO", "0") not in ("0", "1"):
        erros.append("AVISO_AGUARDAR_ODD_ATIVO deve ser 0 ou 1")
    mercados_odd_validos = {"gol_ht", "gol_ft", "proximo_gol"}
    mercados_odd = [
        item.strip().lower()
        for item in str(env.get(
            "AVISO_AGUARDAR_ODD_MERCADOS",
            "gol_ft,gol_ht,proximo_gol",
        ) or "").split(",")
        if item.strip()
    ]
    if not mercados_odd:
        erros.append("AVISO_AGUARDAR_ODD_MERCADOS não pode ficar vazio")
    mercados_odd_desconhecidos = sorted(
        set(mercados_odd) - mercados_odd_validos
    )
    if mercados_odd_desconhecidos:
        erros.append(
            "AVISO_AGUARDAR_ODD_MERCADOS contém mercado inválido: "
            + ", ".join(mercados_odd_desconhecidos)
        )
    if env.get("ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS", "1") not in ("0", "1"):
        erros.append("ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS deve ser 0 ou 1")
    flag_acompanhamento_preco = env.get(
        "ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO", "1"
    )
    if flag_acompanhamento_preco not in ("0", "1"):
        erros.append(
            "ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO deve ser 0 ou 1"
        )
    flag_proximo_gol_balanceado_sombra = env.get(
        "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO", "1"
    )
    if flag_proximo_gol_balanceado_sombra not in ("0", "1"):
        erros.append(
            "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO deve ser 0 ou 1"
        )
    flag_proximo_gol_balanceado_grupo = env.get(
        "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO", "1"
    )
    if flag_proximo_gol_balanceado_grupo not in ("0", "1"):
        erros.append(
            "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO deve ser 0 ou 1"
        )
    if (
        flag_proximo_gol_balanceado_grupo == "1"
        and flag_proximo_gol_balanceado_sombra != "1"
    ):
        erros.append(
            "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO exige "
            "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO=1"
        )
    if env.get("GOLS_ANTECIPADOS_GRUPO_ATIVO", "1") not in ("0", "1"):
        erros.append("GOLS_ANTECIPADOS_GRUPO_ATIVO deve ser 0 ou 1")
    if env.get(
        "FILTRO_GOL_FT_ANTECIPADO_PRECISO_ATIVO", "0"
    ) not in ("0", "1"):
        erros.append(
            "FILTRO_GOL_FT_ANTECIPADO_PRECISO_ATIVO deve ser 0 ou 1"
        )
    if env.get(
        "FILTRO_GOL_HT_ANTECIPADO_PRECISO_ATIVO", "0"
    ) not in ("0", "1"):
        erros.append(
            "FILTRO_GOL_HT_ANTECIPADO_PRECISO_ATIVO deve ser 0 ou 1"
        )
    if env.get("PRELIVE_FILTRO_PRECISO_ATIVO", "0") not in ("0", "1"):
        erros.append("PRELIVE_FILTRO_PRECISO_ATIVO deve ser 0 ou 1")
    if env.get("PRELIVE_MERCADOS_TIME_ATIVOS", "1") not in ("0", "1"):
        erros.append("PRELIVE_MERCADOS_TIME_ATIVOS deve ser 0 ou 1")
    if env.get(
        "PRELIVE_MULTIPLAS_TRES_PERNAS_ATIVAS", "1"
    ) not in ("0", "1"):
        erros.append(
            "PRELIVE_MULTIPLAS_TRES_PERNAS_ATIVAS deve ser 0 ou 1"
        )
    flag_gol_ht_00_min20_grupo = env.get(
        "GOL_HT_00_MIN20_GRUPO_ATIVO", "1"
    )
    if flag_gol_ht_00_min20_grupo not in ("0", "1"):
        erros.append("GOL_HT_00_MIN20_GRUPO_ATIVO deve ser 0 ou 1")
    flag_capacidade_contextual_v2_ht_grupo = env.get(
        "GOLS_CAPACIDADE_CONTEXTUAL_V2_HT_GRUPO_ATIVO", "1"
    )
    if flag_capacidade_contextual_v2_ht_grupo not in ("0", "1"):
        erros.append(
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_HT_GRUPO_ATIVO deve ser 0 ou 1"
        )
    flag_capacidade_contextual_v2_ft_grupo = env.get(
        "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO", "1"
    )
    if flag_capacidade_contextual_v2_ft_grupo not in ("0", "1"):
        erros.append(
            "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO deve ser 0 ou 1"
        )
    flag_top_criterios_gols_grupo = env.get(
        "TOP_CRITERIOS_GOLS_GRUPO_ATIVO", "1"
    )
    if flag_top_criterios_gols_grupo not in ("0", "1"):
        erros.append("TOP_CRITERIOS_GOLS_GRUPO_ATIVO deve ser 0 ou 1")
    flag_capacidade_ht_v1_grupo = env.get(
        "GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO", "0"
    )
    if flag_capacidade_ht_v1_grupo not in ("0", "1"):
        erros.append(
            "GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO deve ser 0 ou 1"
        )
    flag_capacidade_ft_v1_grupo = env.get(
        "GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO", "0"
    )
    if flag_capacidade_ft_v1_grupo not in ("0", "1"):
        erros.append(
            "GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO deve ser 0 ou 1"
        )
    if env.get(
        "GOL_HT_SEM_TENDENCIA_PACKBALL_GRUPO_ATIVO", "0"
    ) not in ("0", "1"):
        erros.append(
            "GOL_HT_SEM_TENDENCIA_PACKBALL_GRUPO_ATIVO deve ser 0 ou 1"
        )
    if env.get(
        "GOL_HT_HISTORICO_INSUFICIENTE_COM_SOT_GRUPO_ATIVO", "0"
    ) not in ("0", "1"):
        erros.append(
            "GOL_HT_HISTORICO_INSUFICIENTE_COM_SOT_GRUPO_ATIVO "
            "deve ser 0 ou 1"
        )
    if env.get("GOL_2T_POS_HT_RED_SOMBRA_ATIVO", "1") not in ("0", "1"):
        erros.append("GOL_2T_POS_HT_RED_SOMBRA_ATIVO deve ser 0 ou 1")
    if env.get("GOL_2T_POS_HT_RED_GRUPO_ATIVO", "0") not in ("0", "1"):
        erros.append("GOL_2T_POS_HT_RED_GRUPO_ATIVO deve ser 0 ou 1")
    flag_lista_temporal = env.get(
        "INDICADORES_LISTA_TEMPORAIS_APLICACAO_SINAIS", "1"
    )
    if flag_lista_temporal not in ("0", "1"):
        erros.append(
            "INDICADORES_LISTA_TEMPORAIS_APLICACAO_SINAIS deve ser 0 ou 1"
        )
    if env.get("ALERTAS_ANALISES_SOMBRA_TELEGRAM", "0") not in ("0", "1"):
        erros.append(
            "ALERTAS_ANALISES_SOMBRA_TELEGRAM deve ser 0 ou 1"
        )
    flag_alertas_tecnicos = env.get("TELEGRAM_ALERTAS_TECNICOS", "0")
    if flag_alertas_tecnicos not in ("0", "1"):
        erros.append("TELEGRAM_ALERTAS_TECNICOS deve ser 0 ou 1")
    flag_alertas_operacionais_grupos = env.get(
        "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS", "0"
    )
    if flag_alertas_operacionais_grupos not in ("0", "1"):
        erros.append(
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS deve ser 0 ou 1"
        )
    if env.get("CONSENSO_MULTIFONTE_SOMBRA_ATIVO", "0") not in ("0", "1"):
        erros.append("CONSENSO_MULTIFONTE_SOMBRA_ATIVO deve ser 0 ou 1")
    if env.get(
        "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS", "0"
    ) not in ("0", "1"):
        erros.append(
            "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS deve ser 0 ou 1"
        )
    flag_prioridade_cantos = env.get(
        "ESCANTEIOS_PRIORIDADE_CANAL_ATIVA", "1"
    )
    if flag_prioridade_cantos not in ("0", "1"):
        erros.append(
            "ESCANTEIOS_PRIORIDADE_CANAL_ATIVA deve ser 0 ou 1"
        )
    chave_thestatsapi = bool(
        (env.get("THESTATSAPI_KEY") or "").strip()
        or (env.get("NOVA_FOOTBALL_API_KEY") or "").strip()
    )
    flag_thestatsapi_padrao = "1" if chave_thestatsapi else "0"
    flag_thestatsapi = env.get(
        "THESTATSAPI_SOMBRA_ATIVA", flag_thestatsapi_padrao
    )
    if flag_thestatsapi not in ("0", "1"):
        erros.append("THESTATSAPI_SOMBRA_ATIVA deve ser 0 ou 1")
    flag_thestatsapi_sinais = env.get(
        "THESTATSAPI_APLICACAO_SINAIS_ATIVA", "0"
    )
    if flag_thestatsapi_sinais not in ("0", "1"):
        erros.append(
            "THESTATSAPI_APLICACAO_SINAIS_ATIVA deve ser 0 ou 1"
        )
    maximo_thestatsapi_ciclo = _inteiro(
        env,
        "THESTATSAPI_MAX_JOGOS_CICLO",
        17,
        0,
        17,
        erros,
    )
    thestatsapi_sombra_ativa = bool(
        chave_thestatsapi and flag_thestatsapi == "1"
    )
    thestatsapi_aplicacao_sinais = bool(
        thestatsapi_sombra_ativa and flag_thestatsapi_sinais == "1"
    )
    if flag_thestatsapi == "1" and not chave_thestatsapi:
        avisos.append(
            "TheStatsAPI solicitada sem chave; coleta auxiliar desativada"
        )
    if flag_thestatsapi_sinais == "1" and not thestatsapi_sombra_ativa:
        erros.append(
            "TheStatsAPI oficial exige chave e THESTATSAPI_SOMBRA_ATIVA=1"
        )
    chave_betsapi = bool((env.get("BETSAPI_TOKEN") or "").strip())
    flag_betsapi = env.get(
        "BETSAPI_ATIVA", "1" if chave_betsapi else "0"
    )
    if flag_betsapi not in ("0", "1"):
        erros.append("BETSAPI_ATIVA deve ser 0 ou 1")
    flag_betsapi_sinais = env.get(
        "BETSAPI_APLICACAO_SINAIS_ATIVA",
        "1" if chave_betsapi and flag_betsapi == "1" else "0",
    )
    if flag_betsapi_sinais not in ("0", "1"):
        erros.append(
            "BETSAPI_APLICACAO_SINAIS_ATIVA deve ser 0 ou 1"
        )
    limite_betsapi_hora = _inteiro(
        env, "BETSAPI_LIMITE_HORA", 3000, 1, 3600, erros
    )
    limite_betsapi_diario = _inteiro(
        env, "BETSAPI_LIMITE_DIARIO", 50000, 1, 500000, erros
    )
    betsapi_ativa = bool(chave_betsapi and flag_betsapi == "1")
    betsapi_aplicacao_sinais = bool(
        betsapi_ativa and flag_betsapi_sinais == "1"
    )
    if flag_betsapi == "1" and not chave_betsapi:
        avisos.append(
            "BetsAPI solicitada sem chave; complemento de odds desativado"
        )
    if (
        "BETSAPI_APLICACAO_SINAIS_ATIVA" in env
        and flag_betsapi_sinais == "1"
        and not betsapi_ativa
    ):
        erros.append(
            "BetsAPI oficial exige chave e BETSAPI_ATIVA=1"
        )
    chave_the_odds_api = bool(
        (env.get("THE_ODDS_API_KEY") or "").strip()
    )
    flag_the_odds_api = env.get(
        "THE_ODDS_API_ATIVA", "1" if chave_the_odds_api else "0"
    )
    if flag_the_odds_api not in ("0", "1"):
        erros.append("THE_ODDS_API_ATIVA deve ser 0 ou 1")
    limite_the_odds_api = _inteiro(
        env, "THE_ODDS_API_LIMITE_DIARIO", 600, 0, 20000, erros
    )
    reserva_the_odds_api = _inteiro(
        env, "THE_ODDS_API_RESERVA_MENSAL", 2000, 0, 19999, erros
    )
    flag_amostragem_referencia_odds = env.get(
        "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA", "0"
    )
    if flag_amostragem_referencia_odds not in ("0", "1"):
        erros.append(
            "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA deve ser 0 ou 1"
        )
    limite_amostragem_referencia_odds = _inteiro(
        env,
        "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_LIMITE_DIARIO",
        30,
        0,
        600,
        erros,
    )
    intervalo_amostragem_referencia_odds = _inteiro(
        env,
        "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_INTERVALO_SEGUNDOS",
        600,
        60,
        86400,
        erros,
    )
    maximo_ciclo_amostragem_referencia_odds = _inteiro(
        env,
        "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_MAX_CICLO",
        2,
        0,
        10,
        erros,
    )
    maximo_jogo_dia_amostragem_referencia_odds = _inteiro(
        env,
        "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_MAX_JOGO_DIA",
        2,
        1,
        10,
        erros,
    )
    the_odds_api_ativa = bool(
        chave_the_odds_api and flag_the_odds_api == "1"
    )
    if flag_the_odds_api == "1" and not chave_the_odds_api:
        avisos.append(
            "The Odds API solicitada sem chave; complemento de odds desativado"
        )
    if (
        flag_amostragem_referencia_odds == "1"
        and not the_odds_api_ativa
    ):
        erros.append(
            "Amostragem de referência exige The Odds API ativa e com chave"
        )
    if limite_amostragem_referencia_odds > limite_the_odds_api:
        erros.append(
            "Limite diário da amostragem de referência não pode superar "
            "o limite diário da The Odds API"
        )

    if not env.get("PACKBALL_EMAIL"):
        erros.append("PACKBALL_EMAIL não configurado")
    if not env.get("PACKBALL_PASSWORD"):
        erros.append("PACKBALL_PASSWORD não configurado")
    if not env.get("API_FOOTBALL_KEY"):
        avisos.append("API_FOOTBALL_KEY ausente; confirmação externa desativada")
    if not env.get("TELEGRAM_BOT_TOKEN"):
        avisos.append("TELEGRAM_BOT_TOKEN ausente; alertas desativados")
    canal_gols = env.get("TELEGRAM_CHAT_ID_GOLS") or env.get("TELEGRAM_CHAT_ID")
    if not canal_gols:
        avisos.append("canal Telegram de gols não configurado")
    if not env.get("TELEGRAM_CHAT_ID_ESCANTEIOS"):
        avisos.append("canal Telegram de escanteios não configurado")
    if not (env.get("TELEGRAM_ADMIN_ID") or env.get("TELEGRAM_CHAT_ID")):
        avisos.append("canal administrativo do watchdog não configurado")

    limites = LimitesRisco(
        limite_diario_sinais=limite_diario,
        odd_minima=odd_minima,
        odd_maxima=odd_maxima,
        limite_exposicao_diaria=exposicao,
        limite_reds_consecutivos_oficiais=reds_consecutivos,
        limite_perda_diaria_oficial=perda_diaria,
    )
    limites_api = LimitesAPI(
        limite_diario=limite_api_diario,
        reserva_diaria=reserva_api_diaria,
        limite_diario_detalhes=limite_api_detalhes,
    )
    return {
        "valida": not erros,
        "erros": erros,
        "avisos": avisos,
        "limites": asdict(limites),
        "api": {
            **asdict(limites_api),
            "limite_diario_seguro": max(limite_api_seguro, 0),
            "stats_resgate_max_ciclo": stats_resgate_max_ciclo,
        },
        "thestatsapi": {
            "chave_configurada": chave_thestatsapi,
            "sombra_ativa": thestatsapi_sombra_ativa,
            "maximo_jogos_ciclo": maximo_thestatsapi_ciclo,
            "aplicacao_sinais": thestatsapi_aplicacao_sinais,
            "modo": (
                "complemento_oficial_fail_closed"
                if thestatsapi_aplicacao_sinais
                else "coleta_sombra"
            ),
        },
        "betsapi": {
            "chave_configurada": chave_betsapi,
            "ativa": betsapi_ativa,
            "limite_hora": limite_betsapi_hora,
            "limite_diario": limite_betsapi_diario,
            "aplicacao_sinais": betsapi_aplicacao_sinais,
            "modo": (
                "complemento_oficial_fail_closed"
                if betsapi_aplicacao_sinais
                else "desativada"
                if not betsapi_ativa
                else "coleta_sem_autorizacao_sinal"
            ),
        },
        "the_odds_api": {
            "chave_configurada": chave_the_odds_api,
            "ativa": the_odds_api_ativa,
            "limite_diario": limite_the_odds_api,
            "reserva_mensal": reserva_the_odds_api,
            "aplicacao_sinais": the_odds_api_ativa,
            "modo": "complemento_fail_closed",
            "amostragem_referencia": {
                "ativa": bool(
                    the_odds_api_ativa
                    and flag_amostragem_referencia_odds == "1"
                ),
                "limite_diario": limite_amostragem_referencia_odds,
                "intervalo_segundos": intervalo_amostragem_referencia_odds,
                "maximo_ciclo": maximo_ciclo_amostragem_referencia_odds,
                "maximo_por_jogo_dia": (
                    maximo_jogo_dia_amostragem_referencia_odds
                ),
                "aplicacao_sinais": False,
                "telegram": False,
                "promocao_automatica": False,
            },
        },
        "telegram": {
            "acompanhamento_odd_avisos": (
                env.get("ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS", "1") == "1"
            ),
            "alertas_tecnicos_ativos": flag_alertas_tecnicos == "1",
            "alertas_sombra_ativos": (
                env.get("ALERTAS_ANALISES_SOMBRA_TELEGRAM", "0") == "1"
            ),
            "resumo_diario_desejado": "compacto-v1",
            "alertas_operacionais_criticos": True,
            "alertas_operacionais_nos_grupos": (
                flag_alertas_operacionais_grupos == "1"
            ),
        },
        "recursos": {
            "acompanhamento_odd_mercados": sorted(set(mercados_odd)),
            "acompanhamento_preco_pos_alerta": (
                flag_acompanhamento_preco == "1"
            ),
            "proximo_gol_balanceado_sombra": (
                flag_proximo_gol_balanceado_sombra == "1"
            ),
            "proximo_gol_balanceado_grupo_teste": (
                flag_proximo_gol_balanceado_grupo == "1"
            ),
            "pontuacao_minima_proximo_gol_balanceado_teste": (
                pontuacao_minima_proximo_gol_balanceado
            ),
            "packball": bool(
                env.get("PACKBALL_EMAIL") and env.get("PACKBALL_PASSWORD")
            ),
            "api_football": bool(env.get("API_FOOTBALL_KEY")),
            "indicadores_lista_temporais_condicionais": (
                flag_lista_temporal == "1"
            ),
            "gol_ht_capacidade_v1_grupo": (
                flag_capacidade_ht_v1_grupo == "1"
            ),
            "gol_ft_capacidade_v1_grupo": (
                flag_capacidade_ft_v1_grupo == "1"
            ),
            "gols_antecipados_grupo": (
                env.get("GOLS_ANTECIPADOS_GRUPO_ATIVO", "1") == "1"
            ),
            "filtro_gol_ht_antecipado_preciso": (
                env.get(
                    "FILTRO_GOL_HT_ANTECIPADO_PRECISO_ATIVO", "0"
                ) == "1"
            ),
            "filtro_gol_ft_antecipado_preciso": (
                env.get(
                    "FILTRO_GOL_FT_ANTECIPADO_PRECISO_ATIVO", "0"
                ) == "1"
            ),
            "gol_ht_00_min20_grupo": (
                flag_gol_ht_00_min20_grupo == "1"
            ),
            "gol_ht_capacidade_contextual_v2_grupo": (
                flag_capacidade_contextual_v2_ht_grupo == "1"
            ),
            "gol_ft_capacidade_contextual_v2_grupo": (
                flag_capacidade_contextual_v2_ft_grupo == "1"
            ),
            "top_criterios_gols_grupo": (
                flag_top_criterios_gols_grupo == "1"
            ),
            "thestatsapi_sombra": thestatsapi_sombra_ativa,
            "betsapi": betsapi_ativa,
            "the_odds_api": the_odds_api_ativa,
            "telegram_gols": bool(env.get("TELEGRAM_BOT_TOKEN") and canal_gols),
            "telegram_escanteios": bool(
                env.get("TELEGRAM_BOT_TOKEN")
                and env.get("TELEGRAM_CHAT_ID_ESCANTEIOS")
            ),
            "watchdog_telegram": bool(
                env.get("TELEGRAM_BOT_TOKEN")
                and (env.get("TELEGRAM_ADMIN_ID") or env.get("TELEGRAM_CHAT_ID"))
            ),
            "sinais_teste": bool(
                env.get("SINAIS_TESTE_ATIVO", "0") == "1"
                and env.get("TELEGRAM_BOT_TOKEN")
                and (
                    env.get("TELEGRAM_CHAT_ID_TESTE")
                    or canal_gols
                    or env.get("TELEGRAM_CHAT_ID_ESCANTEIOS")
                )
            ),
            "escanteios_asiaticos_periodos": (
                env.get(
                    "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS",
                    "0",
                )
                == "1"
            ),
            "escanteios_prioridade_canal": (
                flag_prioridade_cantos == "1"
            ),
        },
    }


def obter_limites_risco(env=None):
    resultado = validar_configuracao(env)
    erros_limites = [
        erro for erro in resultado["erros"]
        if erro.startswith(("LIMITE_", "ODD_"))
    ]
    if erros_limites:
        raise ValueError("; ".join(erros_limites))
    return LimitesRisco(**resultado["limites"])


def odd_elegivel(odd, limites=None, env=None):
    limites = limites or obter_limites_risco(env)
    try:
        valor = float(odd)
    except (TypeError, ValueError):
        return False
    return bool(
        math.isfinite(valor)
        and limites.odd_minima <= valor <= limites.odd_maxima
    )


def obter_limites_api(env=None):
    resultado = validar_configuracao(env)
    erros_api = [
        erro for erro in resultado["erros"] if erro.startswith("API_")
    ]
    if erros_api:
        raise ValueError("; ".join(erros_api))
    dados = dict(resultado["api"])
    dados.pop("limite_diario_seguro", None)
    dados.pop("stats_resgate_max_ciclo", None)
    return LimitesAPI(**dados)
