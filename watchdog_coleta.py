"""Verificacoes de coleta e das fontes de dados do watchdog.

Cobrem o ritmo da coleta, o cache e o pareamento da API, a capacidade
contratada, a prioridade do scanner e a amostragem de referencia das odds.
Cada funcao devolve um resumo de saude; dado ausente ou invalido vira
indisponibilidade explicita, nunca aprovacao silenciosa.

Extraido de watchdog.py, que reexporta estes nomes.
"""

import json
import sqlite3
from datetime import datetime
from historico_api_live import resumir_historico_api_live
from observabilidade import percentil_valores
from pathlib import Path


def _ler_registros_coleta_recentes(caminho_log, limite=1000):
    """Preserva a continuidade do ciclo quando o JSONL acabou de girar."""
    caminho_log = Path(caminho_log)

    def ler(caminho):
        if not caminho.exists():
            return []
        try:
            linhas = caminho.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return []
        registros = []
        for linha in linhas:
            try:
                evento = json.loads(linha)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if evento.get("em"):
                registros.append(evento)
        return registros

    registros = ler(caminho_log)
    recentes = registros[-max(int(limite), 1):]
    if any(
        item.get("evento") == "ciclo_concluido" for item in recentes
    ):
        return recentes

    # A rotação pode acontecer durante um ciclo longo: nesse instante o log
    # atual contém progresso, mas o último sucesso está em `.1`. Retrocedemos
    # somente até encontrá-lo e mantemos tudo a partir dele, inclusive falhas
    # atravessando a fronteira entre os arquivos.
    posteriores = registros
    for indice in range(1, 6):
        anteriores = ler(Path(f"{caminho_log}.{indice}"))
        if not anteriores:
            continue
        combinados = anteriores + posteriores
        posicao_sucesso = next(
            (
                posicao for posicao in range(len(combinados) - 1, -1, -1)
                if combinados[posicao].get("evento") == "ciclo_concluido"
            ),
            None,
        )
        if posicao_sucesso is not None:
            return combinados[posicao_sucesso:]
        posteriores = combinados
    return posteriores[-max(int(limite), 1):]


def verificar_coleta(
    caminho_log, agora=None, limite=300, limite_progresso=120
):
    agora = agora or datetime.now()
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {"saudavel": False, "motivo": "log_ausente", "idade": None}
    registros = _ler_registros_coleta_recentes(caminho_log)
    if not registros:
        return {"saudavel": False, "motivo": "log_invalido", "idade": None}

    ultimo_sucesso = next(
        (
            item for item in reversed(registros)
            if item.get("evento") == "ciclo_concluido"
        ),
        None,
    )
    ultimo_progresso = next(
        (
            item for item in reversed(registros)
            if item.get("evento") == "ciclo_em_andamento"
        ),
        None,
    )
    falhas_consecutivas = 0
    falhas_desde_sucesso = []
    for item in reversed(registros):
        if item.get("evento") in (
            "ciclo_concluido",
            "ciclo_pausado_packball",
        ):
            break
        if item.get("evento") == "ciclo_falhou":
            falhas_consecutivas += 1
            falhas_desde_sucesso.append(item)

    pausa_local_legada = bool(falhas_desde_sucesso) and all(
        item.get("erro") == "PackBallBloqueadoError"
        for item in falhas_desde_sucesso
    ) and any(
        "teto local" in str(item.get("mensagem") or "").lower()
        for item in falhas_desde_sucesso
    )
    if pausa_local_legada:
        falhas_consecutivas = 0

    if ultimo_sucesso is None:
        return {
            "saudavel": False,
            "motivo": "sem_ciclo_concluido",
            "idade": None,
            "ultimo_evento": registros[-1].get("evento"),
            "falhas_consecutivas": falhas_consecutivas,
        }
    instante = datetime.fromisoformat(ultimo_sucesso["em"])
    idade = max((agora - instante).total_seconds(), 0)
    idade_progresso = None
    ciclo_em_andamento = False
    if ultimo_progresso is not None:
        try:
            instante_progresso = datetime.fromisoformat(
                ultimo_progresso["em"]
            )
            idade_progresso = max(
                (agora - instante_progresso).total_seconds(), 0
            )
            falha_posterior = any(
                item.get("evento") == "ciclo_falhou"
                and datetime.fromisoformat(item["em"]) > instante_progresso
                for item in registros
                if item.get("em")
            )
            ciclo_em_andamento = (
                instante_progresso > instante
                and idade_progresso <= limite_progresso
                and not falha_posterior
            )
        except (KeyError, TypeError, ValueError):
            idade_progresso = None
    ultimo = registros[-1]
    pausa_recente = (
        ultimo.get("evento") == "ciclo_pausado_packball"
        or pausa_local_legada
    )
    try:
        idade_pausa = max(
            (agora - datetime.fromisoformat(ultimo["em"])).total_seconds(), 0
        )
    except (KeyError, TypeError, ValueError):
        idade_pausa = float("inf")
    if pausa_recente and idade_pausa <= limite and idade <= 900:
        motivo = None
    elif falhas_consecutivas >= 3:
        motivo = "falhas_consecutivas"
    elif idade > limite and not ciclo_em_andamento:
        motivo = "coleta_parada"
    else:
        motivo = None
    diagnostico_v2 = ultimo_sucesso.get(
        "gols_capacidade_contextual_v2"
    )
    if not isinstance(diagnostico_v2, dict):
        diagnostico_v2 = {}
    diagnostico_thestatsapi = ultimo_sucesso.get("thestatsapi_sombra")
    if not isinstance(diagnostico_thestatsapi, dict):
        diagnostico_thestatsapi = {}
    diagnostico_betsapi = ultimo_sucesso.get("betsapi")
    if not isinstance(diagnostico_betsapi, dict):
        diagnostico_betsapi = {}
    return {
        "saudavel": motivo is None,
        "motivo": motivo,
        "idade": round(idade, 1),
        "ultimo_evento": registros[-1].get("evento"),
        "ultimo_sucesso_em": ultimo_sucesso["em"],
        "partidas_ultimo_ciclo": int(
            ultimo_sucesso.get("partidas", 0) or 0
        ),
        "tarefas_processadas_ultimo_ciclo": int(
            ultimo_sucesso.get("tarefas_processadas", 0) or 0
        ),
        "falhas_consecutivas": falhas_consecutivas,
        "pausa_preventiva": bool(pausa_recente and idade_pausa <= limite),
        "ciclo_em_andamento": ciclo_em_andamento,
        "etapa_atual": (
            ultimo_progresso.get("etapa")
            if ciclo_em_andamento else None
        ),
        "ultimo_progresso_em": (
            ultimo_progresso.get("em") if ultimo_progresso else None
        ),
        "idade_progresso": (
            round(idade_progresso, 1)
            if idade_progresso is not None else None
        ),
        "gols_capacidade_contextual_v2": diagnostico_v2,
        "thestatsapi_sombra": diagnostico_thestatsapi,
        "betsapi": diagnostico_betsapi,
    }


def verificar_historico_api_live(caminho_banco, agora=None):
    """Resume a série auxiliar em leitura, sem afetar a operação."""
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "banco_ausente",
            "aplicacao_sinais": False,
        }
    conexao = None
    try:
        conexao = sqlite3.connect(
            caminho_banco.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=10,
        )
        conexao.row_factory = sqlite3.Row
        return resumir_historico_api_live(
            conexao, agora=agora
        )
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "historico_api_live_indisponivel",
            "erro": type(erro).__name__,
            "aplicacao_sinais": False,
        }
    finally:
        if conexao is not None:
            conexao.close()


def verificar_cache_api_operacional(caminho_log, limite_consecutivo=3):
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_com_falha_consecutivos": 0,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-1000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            evento.get("evento") == "ciclo_concluido"
            and evento.get("cache_api_falhas_ciclo") is not None
        ):
            ciclos.append(evento)
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_com_falha_consecutivos": 0,
        }
    consecutivos = 0
    for ciclo in reversed(ciclos):
        if int(ciclo.get("cache_api_falhas_ciclo") or 0) <= 0:
            break
        consecutivos += 1
    ultima_falha = int(ciclos[-1].get("cache_api_falhas_ciclo") or 0)
    saudavel = consecutivos < int(limite_consecutivo)
    return {
        "saudavel": saudavel,
        "estado": "saudavel" if saudavel else "degradado",
        "motivo": None if saudavel else "cache_api_persistente_indisponivel",
        "ciclos_com_falha_consecutivos": consecutivos,
        "falhas_ultimo_ciclo": ultima_falha,
        "ciclos_observados": len(ciclos),
    }


def verificar_acompanhamento_preco_pos_alerta(
    caminho_log, limite_consecutivo=3
):
    """Audita a coleta auxiliar de preço sem interferir nos sinais.

    Ciclos sem alerta elegível não representam sucesso nem falha. A degradação
    só é confirmada quando as últimas execuções que realmente agendaram um
    acompanhamento falham de forma consecutiva. O estado é informativo: a
    seleção e o envio de sinais continuam sob as regras e gates próprios.
    """
    caminho_log = Path(caminho_log)
    limite = max(int(limite_consecutivo), 1)
    base = {
        "saudavel": True,
        "estado": "aguardando_telemetria",
        "motivo": None,
        "ciclos_degradados_consecutivos": 0,
        "limite_consecutivo": limite,
        "ciclos_aplicaveis_observados": 0,
        "altera_sinais": False,
    }
    if not caminho_log.exists():
        return base

    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-1000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if evento.get("evento") != "ciclo_concluido":
            continue
        perfil = evento.get("perfil_agendamento")
        if not isinstance(perfil, dict):
            continue
        if "acompanhamentos_preco_agendados" not in perfil:
            continue
        agendados = int(
            perfil.get("acompanhamentos_preco_agendados") or 0
        )
        if agendados <= 0:
            continue
        ciclos.append({
            "em": evento.get("em"),
            "agendados": agendados,
            "processados": int(
                perfil.get("acompanhamentos_preco_processados") or 0
            ),
            "com_odds": int(
                perfil.get("acompanhamentos_preco_com_odds") or 0
            ),
            "sem_odds": int(
                perfil.get("acompanhamentos_preco_sem_odds") or 0
            ),
            "snapshots": int(
                perfil.get("acompanhamentos_preco_snapshots") or 0
            ),
        })

    if not ciclos:
        return {
            **base,
            "estado": "sem_acompanhamentos_recentes",
        }

    def degradado(ciclo):
        return bool(
            ciclo["processados"] < ciclo["agendados"]
            or ciclo["com_odds"] < ciclo["processados"]
            or ciclo["snapshots"] < ciclo["processados"]
        )

    consecutivos = 0
    for ciclo in reversed(ciclos):
        if not degradado(ciclo):
            break
        consecutivos += 1

    ultimo = dict(ciclos[-1])
    saudavel = consecutivos < limite
    estado = "saudavel"
    if not saudavel:
        estado = "degradado"
    elif consecutivos:
        estado = "oscilacao_tolerada"
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": (
            None
            if saudavel
            else "acompanhamento_preco_pos_alerta_indisponivel"
        ),
        "ciclos_degradados_consecutivos": consecutivos,
        "limite_consecutivo": limite,
        "ciclos_aplicaveis_observados": len(ciclos),
        "ultimo_ciclo": ultimo,
        "altera_sinais": False,
    }


def verificar_amostragem_referencia_odds_sombra(
    caminho_log, limite_consecutivo=3
):
    """Detecta falha ou ausência persistente na referência independente.

    Somente ciclos que reservaram uma chamada contam como tentativa. Ciclos
    sem jogos elegíveis, em cooldown ou após o limite diário não são falhas.
    A auditoria é observacional e jamais altera sinais, HT/FT ou Telegram.
    """
    caminho_log = Path(caminho_log)
    limite = max(int(limite_consecutivo), 1)
    base = {
        "saudavel": True,
        "estado": "aguardando_telemetria",
        "motivo": None,
        "requer_atencao": False,
        "tentativas_sem_cobertura_consecutivas": 0,
        "falhas_tecnicas_consecutivas": 0,
        "limite_consecutivo": limite,
        "ciclos_observados": 0,
        "ciclos_com_tentativa": 0,
        "elegiveis_betsapi": 0,
        "reservadas": 0,
        "mercados_persistidos_sombra": 0,
        "preselecoes_cobertura": 0,
        "preselecoes_cobertas": 0,
        "preselecoes_descartadas": 0,
        "preselecoes_evento": 0,
        "eventos_pareados_pre_reserva": 0,
        "eventos_descartados_pre_reserva": 0,
        "reservas_economizadas": 0,
        "reservas_economizadas_evento": 0,
        "creditos_estimados_reservados": 0,
        "consultas_combinadas": 0,
        "maximo_mercados_por_consulta": 0,
        "por_mercado": {},
        "ciclos_telemetria_multimercado": 0,
        "altera_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    if not caminho_log.exists():
        return base

    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if evento.get("evento") != "ciclo_concluido":
            continue
        diagnostico_fonte = evento.get("the_odds_api") or {}
        resumo = (diagnostico_fonte.get(
            "amostragem_referencia"
        ))
        if not isinstance(resumo, dict) or "ativa" not in resumo:
            continue
        ciclos.append({
            **resumo,
            "em": evento.get("em"),
            "controle_estado": diagnostico_fonte.get("controle_estado"),
            "circuito": diagnostico_fonte.get("circuito"),
        })

    if not ciclos:
        return base
    ultimo = ciclos[-1]
    if ultimo.get("ativa") is not True:
        return {
            **base,
            "estado": "desativada",
            "ciclos_observados": len(ciclos),
        }
    controle_estado = ultimo.get("controle_estado")
    if (
        isinstance(controle_estado, dict)
        and controle_estado.get("saudavel") is False
    ):
        return {
            **base,
            "saudavel": False,
            "estado": "controle_estado_invalido",
            "motivo": "the_odds_api_estado_irrecuperavel",
            "requer_atencao": True,
            "ciclos_observados": len(ciclos),
            "elegiveis_betsapi": sum(
                int(ciclo.get("elegiveis_betsapi") or 0)
                for ciclo in ciclos
            ),
            "reservadas": sum(
                int(ciclo.get("reservadas") or 0) for ciclo in ciclos
            ),
            "mercados_persistidos_sombra": sum(
                int(ciclo.get("mercados_persistidos_sombra") or 0)
                for ciclo in ciclos
            ),
            "controle_estado": dict(controle_estado),
            "ultimo_ciclo": dict(ultimo),
        }

    tentativas = [
        ciclo for ciclo in ciclos
        if ciclo.get("ativa") is True
        and int(ciclo.get("elegiveis_betsapi") or 0) > 0
        and int(ciclo.get("reservadas") or 0) > 0
    ]
    elegiveis = sum(
        int(ciclo.get("elegiveis_betsapi") or 0) for ciclo in ciclos
    )
    reservadas = sum(int(ciclo.get("reservadas") or 0) for ciclo in ciclos)
    mercados = sum(
        int(ciclo.get("mercados_persistidos_sombra") or 0)
        for ciclo in ciclos
    )
    preselecoes = sum(
        int(ciclo.get("preselecoes_cobertura") or 0)
        for ciclo in ciclos
    )
    preselecoes_cobertas = sum(
        int(ciclo.get("preselecoes_cobertas") or 0)
        for ciclo in ciclos
    )
    preselecoes_descartadas = sum(
        int(ciclo.get("preselecoes_descartadas") or 0)
        for ciclo in ciclos
    )
    reservas_economizadas = sum(
        int(ciclo.get("reservas_economizadas") or 0)
        for ciclo in ciclos
    )
    preselecoes_evento = sum(
        int(ciclo.get("preselecoes_evento") or 0)
        for ciclo in ciclos
    )
    eventos_pareados = sum(
        int(ciclo.get("eventos_pareados_pre_reserva") or 0)
        for ciclo in ciclos
    )
    eventos_descartados = sum(
        int(ciclo.get("eventos_descartados_pre_reserva") or 0)
        for ciclo in ciclos
    )
    reservas_economizadas_evento = sum(
        int(ciclo.get("reservas_economizadas_evento") or 0)
        for ciclo in ciclos
    )
    creditos_estimados_reservados = sum(
        int(ciclo.get("creditos_estimados_reservados") or 0)
        for ciclo in ciclos
    )
    consultas_combinadas = sum(
        int(ciclo.get("consultas_combinadas") or 0)
        for ciclo in ciclos
    )
    maximo_mercados_por_consulta = max((
        int(ciclo.get("maximo_mercados_por_consulta") or 0)
        for ciclo in ciclos
    ), default=0)
    ciclos_telemetria_multimercado = sum(
        1 for ciclo in ciclos
        if "creditos_estimados_reservados" in ciclo
        and "por_mercado" in ciclo
    )
    por_mercado = {}
    auditorias_multimercado_invalidas = 0
    for ciclo in ciclos:
        if not (
            "creditos_estimados_reservados" in ciclo
            and "por_mercado" in ciclo
        ):
            continue
        reservas_ciclo = int(ciclo.get("reservadas") or 0)
        consultas_ciclo = int(ciclo.get("consultadas") or 0)
        persistidos_ciclo = int(
            ciclo.get("mercados_persistidos_sombra") or 0
        )
        creditos_ciclo = int(
            ciclo.get("creditos_estimados_reservados") or 0
        )
        combinadas_ciclo = int(
            ciclo.get("consultas_combinadas") or 0
        )
        maximo_ciclo = int(
            ciclo.get("maximo_mercados_por_consulta") or 0
        )
        mercados_ciclo = ciclo.get("por_mercado") or {}
        invalida = bool(
            not isinstance(mercados_ciclo, dict)
            or creditos_ciclo < reservas_ciclo
            or creditos_ciclo > 3 * reservas_ciclo
            or creditos_ciclo < maximo_ciclo
            or combinadas_ciclo < 0
            or combinadas_ciclo > reservas_ciclo
            or maximo_ciclo < 0
            or maximo_ciclo > 3
            or (combinadas_ciclo > 0 and maximo_ciclo < 2)
        )
        soma_consultados = 0
        soma_anexados = 0
        if isinstance(mercados_ciclo, dict):
            for mercado, contadores in mercados_ciclo.items():
                if not isinstance(contadores, dict):
                    invalida = True
                    continue
                try:
                    elegiveis_mercado = int(
                        contadores.get("elegiveis") or 0
                    )
                    consultados_mercado = int(
                        contadores.get("consultados") or 0
                    )
                    anexados_mercado = int(
                        contadores.get("anexados") or 0
                    )
                except (TypeError, ValueError):
                    invalida = True
                    continue
                if (
                    elegiveis_mercado < 0
                    or consultados_mercado < 0
                    or anexados_mercado < 0
                    or consultados_mercado > elegiveis_mercado
                    or anexados_mercado > consultados_mercado
                ):
                    invalida = True
                soma_consultados += consultados_mercado
                soma_anexados += anexados_mercado
                acumulado = por_mercado.setdefault(str(mercado), {
                    "elegiveis": 0,
                    "consultados": 0,
                    "anexados": 0,
                })
                acumulado["elegiveis"] += elegiveis_mercado
                acumulado["consultados"] += consultados_mercado
                acumulado["anexados"] += anexados_mercado
        if (
            soma_anexados != persistidos_ciclo
            or soma_consultados < consultas_ciclo
            or soma_consultados > 3 * consultas_ciclo
        ):
            invalida = True
        if invalida:
            auditorias_multimercado_invalidas += 1
    if auditorias_multimercado_invalidas:
        return {
            **base,
            "saudavel": False,
            "estado": "auditoria_multimercado_invalida",
            "motivo": "amostragem_referencia_multimercado_inconsistente",
            "requer_atencao": True,
            "ciclos_observados": len(ciclos),
            "ciclos_com_tentativa": len(tentativas),
            "elegiveis_betsapi": elegiveis,
            "reservadas": reservadas,
            "mercados_persistidos_sombra": mercados,
            "creditos_estimados_reservados": (
                creditos_estimados_reservados
            ),
            "consultas_combinadas": consultas_combinadas,
            "maximo_mercados_por_consulta": (
                maximo_mercados_por_consulta
            ),
            "por_mercado": por_mercado,
            "ciclos_telemetria_multimercado": (
                ciclos_telemetria_multimercado
            ),
            "auditorias_multimercado_invalidas": (
                auditorias_multimercado_invalidas
            ),
            "ultimo_ciclo": dict(ultimo),
        }
    auditorias_preselecao_invalidas = sum(
        1 for ciclo in ciclos
        if (
            int(ciclo.get("preselecoes_cobertas") or 0)
            + int(ciclo.get("preselecoes_descartadas") or 0)
            != int(ciclo.get("preselecoes_cobertura") or 0)
            or int(ciclo.get("eventos_pareados_pre_reserva") or 0)
            + int(ciclo.get("eventos_descartados_pre_reserva") or 0)
            != int(ciclo.get("preselecoes_evento") or 0)
            or int(ciclo.get("preselecoes_evento") or 0)
            > int(ciclo.get("preselecoes_cobertas") or 0)
            or int(ciclo.get("reservas_economizadas") or 0)
            > (
                int(ciclo.get("preselecoes_descartadas") or 0)
                + int(ciclo.get("eventos_descartados_pre_reserva") or 0)
            )
            or int(ciclo.get("reservas_economizadas_evento") or 0)
            > int(ciclo.get("eventos_descartados_pre_reserva") or 0)
        )
    )
    if auditorias_preselecao_invalidas:
        return {
            **base,
            "saudavel": False,
            "estado": "auditoria_preselecao_invalida",
            "motivo": "amostragem_referencia_preselecao_inconsistente",
            "requer_atencao": True,
            "ciclos_observados": len(ciclos),
            "ciclos_com_tentativa": len(tentativas),
            "elegiveis_betsapi": elegiveis,
            "reservadas": reservadas,
            "mercados_persistidos_sombra": mercados,
            "preselecoes_cobertura": preselecoes,
            "preselecoes_cobertas": preselecoes_cobertas,
            "preselecoes_descartadas": preselecoes_descartadas,
            "preselecoes_evento": preselecoes_evento,
            "eventos_pareados_pre_reserva": eventos_pareados,
            "eventos_descartados_pre_reserva": eventos_descartados,
            "reservas_economizadas": reservas_economizadas,
            "reservas_economizadas_evento": (
                reservas_economizadas_evento
            ),
            "auditorias_preselecao_invalidas": (
                auditorias_preselecao_invalidas
            ),
            "ultimo_ciclo": dict(ultimo),
        }
    if not tentativas:
        return {
            **base,
            "estado": (
                "aguardando_reserva" if elegiveis else "sem_oportunidade"
            ),
            "ciclos_observados": len(ciclos),
            "elegiveis_betsapi": elegiveis,
            "reservadas": reservadas,
            "mercados_persistidos_sombra": mercados,
            "preselecoes_cobertura": preselecoes,
            "preselecoes_cobertas": preselecoes_cobertas,
            "preselecoes_descartadas": preselecoes_descartadas,
            "preselecoes_evento": preselecoes_evento,
            "eventos_pareados_pre_reserva": eventos_pareados,
            "eventos_descartados_pre_reserva": eventos_descartados,
            "reservas_economizadas": reservas_economizadas,
            "reservas_economizadas_evento": (
                reservas_economizadas_evento
            ),
            "creditos_estimados_reservados": (
                creditos_estimados_reservados
            ),
            "consultas_combinadas": consultas_combinadas,
            "maximo_mercados_por_consulta": (
                maximo_mercados_por_consulta
            ),
            "por_mercado": por_mercado,
            "ciclos_telemetria_multimercado": (
                ciclos_telemetria_multimercado
            ),
            "ultimo_ciclo": dict(ultimo),
        }

    sem_cobertura = 0
    falhas_tecnicas = 0
    for ciclo in reversed(tentativas):
        persistidos = int(
            ciclo.get("mercados_persistidos_sombra") or 0
        )
        if persistidos > 0:
            break
        sem_cobertura += 1
    for ciclo in reversed(tentativas):
        motivos = ciclo.get("motivos") or {}
        if int(motivos.get("falha_isolada") or 0) <= 0:
            break
        falhas_tecnicas += 1

    saudavel = falhas_tecnicas < limite
    requer_atencao = bool(
        falhas_tecnicas >= limite or sem_cobertura >= limite
    )
    motivo = None
    estado = "saudavel"
    if falhas_tecnicas >= limite:
        estado = "falha_persistente"
        motivo = "amostragem_referencia_odds_falhou"
    elif sem_cobertura >= limite:
        estado = "sem_cobertura_persistente"
        motivo = "amostragem_referencia_odds_sem_cobertura"
    elif sem_cobertura:
        estado = "cobertura_em_formacao"
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": motivo,
        "requer_atencao": requer_atencao,
        "tentativas_sem_cobertura_consecutivas": sem_cobertura,
        "falhas_tecnicas_consecutivas": falhas_tecnicas,
        "limite_consecutivo": limite,
        "ciclos_observados": len(ciclos),
        "ciclos_com_tentativa": len(tentativas),
        "elegiveis_betsapi": elegiveis,
        "reservadas": reservadas,
        "mercados_persistidos_sombra": mercados,
        "preselecoes_cobertura": preselecoes,
        "preselecoes_cobertas": preselecoes_cobertas,
        "preselecoes_descartadas": preselecoes_descartadas,
        "preselecoes_evento": preselecoes_evento,
        "eventos_pareados_pre_reserva": eventos_pareados,
        "eventos_descartados_pre_reserva": eventos_descartados,
        "reservas_economizadas": reservas_economizadas,
        "reservas_economizadas_evento": reservas_economizadas_evento,
        "creditos_estimados_reservados": (
            creditos_estimados_reservados
        ),
        "consultas_combinadas": consultas_combinadas,
        "maximo_mercados_por_consulta": maximo_mercados_por_consulta,
        "por_mercado": por_mercado,
        "ciclos_telemetria_multimercado": (
            ciclos_telemetria_multimercado
        ),
        "ultimo_ciclo": dict(ultimo),
        "altera_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def verificar_prioridade_scanner_packball(
    caminho_log, limite_consecutivo=3
):
    """Detecta perda persistente do Scanner sem reagir a uma oscilação.

    O Scanner organiza a prioridade, mas a lista Ao Vivo continua sendo o
    fallback de cobertura. Por isso uma falha isolada permanece saudável e só
    três ciclos concluídos consecutivos sem ``prioridade_carregada`` formam um
    incidente operacional.
    """
    def _instante_ciclo(ciclo):
        valor = ciclo.get("_em_ciclo")
        if not valor:
            return None
        try:
            return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    def _duracao_segundos(inicio, fim):
        if inicio is None or fim is None:
            return 0.0
        try:
            return round(max((fim - inicio).total_seconds(), 0.0), 3)
        except (TypeError, ValueError):
            return 0.0

    caminho_log = Path(caminho_log)
    limite = max(int(limite_consecutivo), 1)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_sem_prioridade_consecutivos": 0,
            "limite_consecutivo": limite,
            "ciclos_observados": 0,
            "episodios_sem_prioridade_observados": 0,
            "duracao_sem_prioridade_segundos": 0.0,
            "duracao_total_sem_prioridade_segundos": 0.0,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if evento.get("evento") != "ciclo_concluido":
            continue
        scanner = ((evento.get("lista_packball") or {}).get("scanner"))
        if not isinstance(scanner, dict) or "habilitado" not in scanner:
            continue
        ciclos.append({**scanner, "_em_ciclo": evento.get("em")})
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_sem_prioridade_consecutivos": 0,
            "limite_consecutivo": limite,
            "ciclos_observados": 0,
            "episodios_sem_prioridade_observados": 0,
            "duracao_sem_prioridade_segundos": 0.0,
            "duracao_total_sem_prioridade_segundos": 0.0,
        }

    episodios = []
    inicio_episodio = None
    ultimo_degradado = None
    for scanner in ciclos:
        instante = _instante_ciclo(scanner)
        degradado = bool(
            scanner.get("habilitado") is True
            and scanner.get("estado") != "prioridade_carregada"
        )
        if degradado:
            if inicio_episodio is None:
                inicio_episodio = instante
            if instante is not None:
                ultimo_degradado = instante
            continue
        if inicio_episodio is not None:
            fim_episodio = instante or ultimo_degradado
            episodios.append({
                "inicio": inicio_episodio,
                "fim": fim_episodio,
                "aberto": False,
                "duracao_segundos": _duracao_segundos(
                    inicio_episodio, fim_episodio
                ),
            })
            inicio_episodio = None
            ultimo_degradado = None
    if inicio_episodio is not None:
        episodios.append({
            "inicio": inicio_episodio,
            "fim": ultimo_degradado,
            "aberto": True,
            "duracao_segundos": _duracao_segundos(
                inicio_episodio, ultimo_degradado
            ),
        })

    episodio_atual = (
        episodios[-1]
        if episodios and episodios[-1]["aberto"]
        else None
    )
    duracao_total = round(sum(
        episodio["duracao_segundos"] for episodio in episodios
    ), 3)

    ultimo = ciclos[-1]
    if ultimo.get("habilitado") is not True:
        return {
            "saudavel": True,
            "estado": "desativado",
            "motivo": None,
            "ciclos_sem_prioridade_consecutivos": 0,
            "limite_consecutivo": limite,
            "ciclos_observados": len(ciclos),
            "estado_ultimo_ciclo": ultimo.get("estado") or "desativado",
            "fallback_ao_vivo_ativo": True,
            "episodios_sem_prioridade_observados": len(episodios),
            "duracao_sem_prioridade_segundos": 0.0,
            "duracao_total_sem_prioridade_segundos": duracao_total,
        }

    consecutivos = 0
    estados_recentes = []
    for scanner in reversed(ciclos):
        if scanner.get("habilitado") is not True:
            break
        estado = scanner.get("estado")
        if estado == "prioridade_carregada":
            break
        consecutivos += 1
        estados_recentes.append(estado or "estado_ausente")

    saudavel = consecutivos < limite
    return {
        "saudavel": saudavel,
        "estado": "saudavel" if saudavel else "degradado",
        "motivo": None if saudavel else "prioridade_scanner_indisponivel",
        "ciclos_sem_prioridade_consecutivos": consecutivos,
        "limite_consecutivo": limite,
        "ciclos_observados": len(ciclos),
        "estado_ultimo_ciclo": ultimo.get("estado"),
        "estados_degradados_recentes": estados_recentes,
        "contador_filtrado_ultimo_ciclo": ultimo.get("contador_filtrado"),
        "jogos_extraidos_ultimo_ciclo": ultimo.get("jogos_extraidos"),
        "fallback_ao_vivo_ativo": True,
        "episodios_sem_prioridade_observados": len(episodios),
        "sem_prioridade_desde": (
            episodio_atual["inicio"].isoformat()
            if episodio_atual and episodio_atual["inicio"] is not None
            else None
        ),
        "duracao_sem_prioridade_segundos": (
            episodio_atual["duracao_segundos"] if episodio_atual else 0.0
        ),
        "duracao_total_sem_prioridade_segundos": duracao_total,
    }


def verificar_fontes_sinais_operacionais(
    caminho_log, limite_consecutivo=2
):
    """Alerta apenas quando o gate fail-closed persiste entre ciclos."""
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_degradados_consecutivos": 0,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if evento.get("evento") != "ciclo_concluido":
            continue
        if (
            "saude_api" not in evento
            and "sinais_bloqueados_fontes" not in evento
        ):
            continue
        ciclos.append(evento)
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_degradados_consecutivos": 0,
        }

    consecutivos = 0
    for ciclo in reversed(ciclos):
        saude_api = ciclo.get("saude_api") or {}
        betsapi = ciclo.get("betsapi") or {}
        bloqueados = int(ciclo.get("sinais_bloqueados_fontes") or 0)
        sem_demanda_api = bool(
            int(ciclo.get("partidas") or 0) == 0
            and int(ciclo.get("tarefas_agendadas") or 0) == 0
        )
        api_ainda_nao_necessaria = bool(
            sem_demanda_api
            and saude_api.get("motivo") == "api_ainda_nao_confirmada"
        )
        betsapi_oficial_disponivel = bool(
            betsapi.get("ativa") is True
            and betsapi.get("aplicacao_sinais") is True
            and betsapi.get("circuito_aberto") is not True
            and (
                (betsapi.get("circuito") or {}).get(
                    "persistencia_saudavel"
                ) is not False
            )
        )
        degradado = (
            (
                saude_api.get("saudavel") is False
                and not api_ainda_nao_necessaria
                and not betsapi_oficial_disponivel
            )
            or bloqueados > 0
        )
        if not degradado:
            break
        consecutivos += 1
    ultimo = ciclos[-1]
    ultima_saude_api = dict(ultimo.get("saude_api") or {})
    ultimos_bloqueados = int(
        ultimo.get("sinais_bloqueados_fontes") or 0
    )
    motivos = dict(ultimo.get("motivos_bloqueio_fontes") or {})
    betsapi_ultimo = dict(ultimo.get("betsapi") or {})
    betsapi_oficial_ultimo_ciclo = bool(
        betsapi_ultimo.get("ativa") is True
        and betsapi_ultimo.get("aplicacao_sinais") is True
        and betsapi_ultimo.get("circuito_aberto") is not True
        and (
            (betsapi_ultimo.get("circuito") or {}).get(
                "persistencia_saudavel"
            ) is not False
        )
    )
    saudavel = consecutivos < max(int(limite_consecutivo), 1)
    return {
        "saudavel": saudavel,
        "estado": "saudavel" if saudavel else "degradado",
        "motivo": None if saudavel else "fontes_sinais_indisponiveis",
        "ciclos_degradados_consecutivos": consecutivos,
        "limite_consecutivo": max(int(limite_consecutivo), 1),
        "sinais_bloqueados_ultimo_ciclo": ultimos_bloqueados,
        "motivos_ultimo_ciclo": motivos,
        "saude_api_ultimo_ciclo": ultima_saude_api,
        "betsapi_oficial_ultimo_ciclo": betsapi_oficial_ultimo_ciclo,
        "ciclos_observados": len(ciclos),
    }


def verificar_capacidade_coleta(
    caminho_log,
    limite_consecutivo=3,
    janela_ciclos=20,
    limiar_pressao=0.85,
    margem_ultima_tarefa_segundos=5.0,
):
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_adiando": 0,
            "ciclos_pausa_preventiva": 0,
            "ciclos_reserva_adaptativa": 0,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-1000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            evento.get("evento") == "ciclo_concluido"
            and evento.get("tarefas_adiadas") is not None
        ):
            ciclos.append(evento)
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
            "ciclos_adiando": 0,
            "ciclos_pausa_preventiva": 0,
        }
    consecutivos = 0
    for ciclo in reversed(ciclos):
        # O limitador de acesso do PackBall adia tarefas de propósito para
        # evitar bloqueios. Esses ciclos são neutros: não criam nem apagam
        # uma sequência de falta real de capacidade de processamento.
        limitado_packball = (
            (ciclo.get("ritmo_packball") or {}).get(
                "distribuicao_janela_ativa"
            ) is True
        )
        if limitado_packball:
            # A distribuição uniforme é um novo regime de capacidade:
            # a fila restante decorre do teto externo, não de atraso do
            # processamento. Ela encerra a sequência do regime anterior.
            break
        if ciclo.get("pausa_preventiva"):
            continue
        if int(ciclo.get("tarefas_adiadas") or 0) <= 0:
            break
        consecutivos += 1
    pausas_preventivas = 0
    for ciclo in reversed(ciclos):
        if not ciclo.get("pausa_preventiva"):
            break
        pausas_preventivas += 1
    ciclos_limitados_packball = 0
    for ciclo in reversed(ciclos):
        if (
            (ciclo.get("ritmo_packball") or {}).get(
                "distribuicao_janela_ativa"
            ) is not True
        ):
            break
        ciclos_limitados_packball += 1
    ciclos_sem_resgate_antigo = 0
    for ciclo in reversed(ciclos):
        idade_fila = ciclo.get("idade_fila")
        if not isinstance(idade_fila, dict) or not idade_fila:
            break
        agendadas_idade = (
            idade_fila.get("agendadas_acionaveis")
            or idade_fila.get("agendadas")
            or {}
        )
        processadas_idade = (
            idade_fila.get("processadas_acionaveis")
            or idade_fila.get("processadas")
            or {}
        )
        atrasadas = int(agendadas_idade.get("acima_20_minutos") or 0)
        resgatadas = int(
            processadas_idade.get("acima_20_minutos") or 0
        )
        # Compatibilidade com ciclos produzidos antes da telemetria de idade
        # acionável. A priorização já registrava essa contagem e permite
        # distinguir uma partida expirada de uma oportunidade que ainda pode
        # gerar sinal. Na ausência das duas evidências, conserva a leitura
        # legada mais prudente.
        telemetria_acionavel = isinstance(
            idade_fila.get("agendadas_acionaveis"), dict
        )
        if not telemetria_acionavel:
            priorizacao = (
                (ciclo.get("enriquecimento_api_lote") or {})
                .get("priorizacao") or {}
            )
            if priorizacao.get("atrasadas_acionaveis") is not None:
                atrasadas = int(
                    priorizacao.get("atrasadas_acionaveis") or 0
                )
        if atrasadas <= 0 or resgatadas > 0:
            break
        if ciclo.get("pausa_preventiva"):
            break
        ciclos_sem_resgate_antigo += 1
    ciclos_sem_rechecagem_pos_evento = 0
    for ciclo in reversed(ciclos):
        perfil = ciclo.get("perfil_agendamento")
        if not isinstance(perfil, dict):
            break
        agendadas_pos_evento = int(
            perfil.get("rechecagens_pos_evento_agendadas") or 0
        )
        processadas_pos_evento = int(
            perfil.get("rechecagens_pos_evento_processadas") or 0
        )
        if agendadas_pos_evento <= 0 or processadas_pos_evento > 0:
            break
        if ciclo.get("pausa_preventiva"):
            break
        ciclos_sem_rechecagem_pos_evento += 1
    ciclos_observados = []
    ciclos_ativos = []
    for ciclo in ciclos:
        duracao = ciclo.get("duracao_detalhada_segundos")
        orcamento = ciclo.get("orcamento_detalhado_segundos")
        mensuravel = (
            not ciclo.get("pausa_preventiva")
            and int(ciclo.get("tarefas_agendadas") or 0) > 0
            and duracao is not None
            and orcamento is not None
            and float(orcamento) > 0
        )
        if mensuravel:
            ciclos_observados.append(ciclo)
        if (
            mensuravel
            and not (
                (ciclo.get("ritmo_packball") or {}).get(
                    "distribuicao_janela_ativa"
                ) is True
            )
        ):
            ciclos_ativos.append(ciclo)
    if ciclos_limitados_packball:
        ciclos_ativos = []
    ciclos_ativos = ciclos_ativos[-int(janela_ciclos):]
    ciclos_observados = ciclos_observados[-int(janela_ciclos):]
    utilizacoes = [
        float(ciclo["duracao_detalhada_segundos"])
        / float(ciclo["orcamento_detalhado_segundos"])
        for ciclo in ciclos_ativos
    ]
    utilizacoes_observadas = [
        float(ciclo["duracao_detalhada_segundos"])
        / float(ciclo["orcamento_detalhado_segundos"])
        for ciclo in ciclos_observados
    ]
    excessos_observados = [
        max(
            float(ciclo["duracao_detalhada_segundos"])
            - float(ciclo["orcamento_detalhado_segundos"]),
            0.0,
        )
        for ciclo in ciclos_observados
    ]
    excessos_inesperados_consecutivos = 0
    for ciclo in reversed(ciclos_observados):
        p95_tarefa = ciclo.get("duracao_tarefa_p95_segundos")
        if p95_tarefa is None:
            break
        excesso = max(
            float(ciclo["duracao_detalhada_segundos"])
            - float(ciclo["orcamento_detalhado_segundos"]),
            0.0,
        )
        tolerancia = (
            max(float(p95_tarefa), 0.0)
            + float(margem_ultima_tarefa_segundos)
        )
        if excesso <= tolerancia:
            break
        excessos_inesperados_consecutivos += 1
    pressao_consecutiva = 0
    if not ciclos_limitados_packball:
        for utilizacao in reversed(utilizacoes):
            if utilizacao < float(limiar_pressao):
                break
            pressao_consecutiva += 1
    ultimo = ciclos[-1]
    saturada = consecutivos >= int(limite_consecutivo)
    degradada = pressao_consecutiva >= int(limite_consecutivo)
    excesso_anormal = (
        excessos_inesperados_consecutivos >= int(limite_consecutivo)
    )
    starvation = ciclos_sem_resgate_antigo >= int(limite_consecutivo)
    starvation_pos_evento = (
        ciclos_sem_rechecagem_pos_evento >= int(limite_consecutivo)
    )
    saudavel = (
        not saturada
        and not degradada
        and not excesso_anormal
        and not starvation
        and not starvation_pos_evento
    )
    if saturada:
        estado = "saturada"
        motivo = "capacidade_coleta_saturada"
    elif degradada:
        estado = "degradada"
        motivo = "orcamento_coleta_proximo_limite"
    elif excesso_anormal:
        estado = "degradada"
        motivo = "ciclo_excede_orcamento_mais_ultima_tarefa"
    elif starvation:
        estado = "degradada"
        motivo = "fila_antiga_sem_resgate"
    elif starvation_pos_evento:
        estado = "degradada"
        motivo = "rechecagem_pos_evento_sem_processamento"
    elif pausas_preventivas:
        estado = "protegida_packball"
        motivo = None
    elif ciclos_limitados_packball:
        estado = "limitada_packball"
        motivo = None
    else:
        estado = "saudavel"
        motivo = None
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": motivo,
        "ciclos_adiando": consecutivos,
        "ciclos_pausa_preventiva": pausas_preventivas,
        "ciclos_limitados_packball": ciclos_limitados_packball,
        "ciclos_sob_pressao": pressao_consecutiva,
        "ciclos_sem_resgate_antigo": ciclos_sem_resgate_antigo,
        "starvation_avalia_somente_acionaveis": bool(
            isinstance(
                (ultimo.get("idade_fila") or {}).get(
                    "agendadas_acionaveis"
                ),
                dict,
            )
            or (
                (
                    (ultimo.get("enriquecimento_api_lote") or {})
                    .get("priorizacao") or {}
                ).get("atrasadas_acionaveis") is not None
            )
        ),
        "ciclos_sem_rechecagem_pos_evento": (
            ciclos_sem_rechecagem_pos_evento
        ),
        "limite_consecutivo": int(limite_consecutivo),
        "limiar_pressao_percentual": round(float(limiar_pressao) * 100, 1),
        "janela_ciclos_ativos": len(ciclos_ativos),
        "janela_ciclos_observados": len(ciclos_observados),
        "utilizacao_capacidade_motivo": (
            "limitada_packball"
            if ciclos_limitados_packball and not utilizacoes
            else None
        ),
        "utilizacao_media_percentual": (
            round(sum(utilizacoes) / len(utilizacoes) * 100, 1)
            if utilizacoes else None
        ),
        "utilizacao_p95_percentual": (
            round(percentil_valores(utilizacoes, 0.95) * 100, 1)
            if utilizacoes else None
        ),
        "utilizacao_maxima_percentual": (
            round(max(utilizacoes) * 100, 1) if utilizacoes else None
        ),
        "utilizacao_observada_media_percentual": (
            round(
                sum(utilizacoes_observadas)
                / len(utilizacoes_observadas) * 100,
                1,
            )
            if utilizacoes_observadas else None
        ),
        "utilizacao_observada_p95_percentual": (
            round(
                percentil_valores(utilizacoes_observadas, 0.95) * 100,
                1,
            )
            if utilizacoes_observadas else None
        ),
        "utilizacao_observada_maxima_percentual": (
            round(max(utilizacoes_observadas) * 100, 1)
            if utilizacoes_observadas else None
        ),
        "margem_ultima_tarefa_segundos": float(
            margem_ultima_tarefa_segundos
        ),
        "ciclos_com_excesso_orcamento": sum(
            excesso > 0 for excesso in excessos_observados
        ),
        "ciclos_reserva_adaptativa": sum(
            ciclo.get("interrompido_por_reserva") is True
            for ciclo in ciclos_observados
        ),
        "ultimo_interrompido_por_reserva": (
            ultimo.get("interrompido_por_reserva") is True
        ),
        "ultima_reserva_admissao_segundos": (
            float(ultimo["reserva_admissao_segundos"])
            if ultimo.get("reserva_admissao_segundos") is not None
            else None
        ),
        "ciclos_excesso_inesperado_consecutivos": (
            excessos_inesperados_consecutivos
        ),
        "excesso_orcamento_media_segundos": (
            round(
                sum(excessos_observados) / len(excessos_observados),
                1,
            )
            if excessos_observados else None
        ),
        "excesso_orcamento_p95_segundos": (
            round(percentil_valores(excessos_observados, 0.95), 1)
            if excessos_observados else None
        ),
        "excesso_orcamento_maximo_segundos": (
            round(max(excessos_observados), 1)
            if excessos_observados else None
        ),
        "agendadas": int(ultimo.get("tarefas_agendadas") or 0),
        "processadas": int(ultimo.get("tarefas_processadas") or 0),
        "adiadas": int(ultimo.get("tarefas_adiadas") or 0),
        "idade_fila": dict(ultimo.get("idade_fila") or {}),
        "priorizacao_fila": dict(
            (
                ultimo.get("enriquecimento_api_lote") or {}
            ).get("priorizacao") or {}
        ),
        "perfil_agendamento": dict(
            ultimo.get("perfil_agendamento") or {}
        ),
        "associacoes_api": dict(ultimo.get("associacoes_api") or {}),
        "enriquecimento_api_lote": dict(
            ultimo.get("enriquecimento_api_lote") or {}
        ),
        "gols_antecipados": dict(
            ultimo.get("gols_antecipados") or {}
        ),
        "resgate_qualidade_api": dict(
            ultimo.get("resgate_qualidade_api") or {}
        ),
    }


def verificar_pareamento_api(
    caminho_log,
    ciclos_recentes=3,
    ciclos_base=20,
    minimo_tarefas_recentes=10,
    minimo_tarefas_base=20,
):
    """Detecta colapso relativo sem exigir cobertura universal da API."""
    caminho_log = Path(caminho_log)
    if not caminho_log.exists():
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
        }
    ciclos = []
    for linha in caminho_log.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            evento = json.loads(linha)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            evento.get("evento") == "ciclo_concluido"
            and isinstance(evento.get("associacoes_api"), dict)
            and evento.get("associacoes_api")
        ):
            saude_api = evento.get("saude_api") or {}
            if (
                saude_api.get("saudavel") is False
                and saude_api.get("motivo") in {
                    "cota_api_segura_esgotada",
                    "api_ainda_nao_confirmada",
                }
            ):
                continue
            ciclos.append(evento)
    if not ciclos:
        return {
            "saudavel": True,
            "estado": "aguardando_telemetria",
            "motivo": None,
        }

    recentes = ciclos[-int(ciclos_recentes):]
    anteriores = ciclos[
        -int(ciclos_recentes + ciclos_base):-int(ciclos_recentes)
    ]

    def resumir(itens):
        totais = {}
        for ciclo in itens:
            for motivo, quantidade in (
                ciclo.get("associacoes_api") or {}
            ).items():
                try:
                    quantidade = max(int(quantidade), 0)
                except (TypeError, ValueError):
                    continue
                totais[motivo] = totais.get(motivo, 0) + quantidade
        tarefas = sum(totais.values())
        associados = totais.get("associado", 0)
        return {
            "ciclos": len(itens),
            "tarefas": tarefas,
            "associados": associados,
            "taxa_associacao": (
                round(associados / tarefas, 4) if tarefas else None
            ),
            "motivos": totais,
        }

    recente = resumir(recentes)
    base = resumir(anteriores)
    erros = recente["motivos"].get("erro_processamento", 0)
    ambiguas = recente["motivos"].get("associacao_ambigua", 0)
    comparaveis_ambiguidade = recente["associados"] + ambiguas
    taxa_ambiguidade = (
        ambiguas / comparaveis_ambiguidade
        if comparaveis_ambiguidade else 0.0
    )
    recente_suficiente = recente["tarefas"] >= int(
        minimo_tarefas_recentes
    )
    base_suficiente = base["tarefas"] >= int(minimo_tarefas_base)
    colapso = bool(
        recente_suficiente
        and base_suficiente
        and (base["taxa_associacao"] or 0) >= 0.30
        and (recente["taxa_associacao"] or 0)
        < (base["taxa_associacao"] or 0) * 0.25
    )
    ambiguidade_excessiva = bool(
        comparaveis_ambiguidade >= 10 and taxa_ambiguidade >= 0.5
    )
    if erros >= 3:
        motivo = "erros_pareamento_api_repetidos"
    elif ambiguidade_excessiva:
        motivo = "ambiguidade_api_excessiva"
    elif colapso:
        motivo = "cobertura_api_caiu_versus_base"
    else:
        motivo = None
    if motivo:
        estado = "degradado"
    elif recente_suficiente and base_suficiente:
        estado = "avaliavel"
    else:
        estado = "formando_linha_de_base"
    return {
        "saudavel": motivo is None,
        "estado": estado,
        "motivo": motivo,
        "recente": recente,
        "base": base,
        "taxa_ambiguidade": round(taxa_ambiguidade, 4),
        "minimo_tarefas_recentes": int(minimo_tarefas_recentes),
        "minimo_tarefas_base": int(minimo_tarefas_base),
    }
