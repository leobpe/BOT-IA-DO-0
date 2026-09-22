import math
from datetime import datetime, timedelta

from configuracao import obter_limites_risco
from integridade_calibracao import carregar_amostra_independente
from mercados import MERCADOS_CALIBRADOS
from motor_sinais import VERSAO_REGRAS
from versoes_gol_ft_reforcado import (
    versao_regra_operacional as versao_regra_para_mercado,
)


ALVO_AMOSTRA_PROFISSIONAL = 100
JANELA_RITMO_DIAS = 7


def calcular_progresso_amostra(
    resultados,
    agora=None,
    alvo=ALVO_AMOSTRA_PROFISSIONAL,
    janela_dias=JANELA_RITMO_DIAS,
):
    agora = (agora or datetime.now()).replace(microsecond=0)
    instantes = []
    for item in resultados:
        try:
            instante = datetime.fromisoformat(item["encerrado_em"])
        except (KeyError, TypeError, ValueError):
            continue
        if instante <= agora:
            instantes.append(instante)
    instantes.sort()
    amostra = len(instantes)
    faltam = max(int(alvo) - amostra, 0)
    if not instantes:
        return {
            "amostra": 0,
            "faltam": faltam,
            "resultados_janela": 0,
            "dias_observados": 0,
            "ritmo_dia": 0.0,
            "dias_estimados": None,
            "data_estimada": None,
            "confiabilidade_estimativa": "sem_ritmo",
        }

    limite = agora - timedelta(days=int(janela_dias))
    recentes = [instante for instante in instantes if instante >= limite]
    inicio_observado = max(instantes[0].date(), limite.date())
    dias_observados = min(
        (agora.date() - inicio_observado).days + 1,
        int(janela_dias),
    )
    dias_observados = max(dias_observados, 1)
    ritmo = len(recentes) / dias_observados
    if faltam == 0:
        dias_estimados = 0
        data_estimada = agora.date().isoformat()
    elif ritmo > 0 and len(recentes) >= 5:
        dias_estimados = int(math.ceil(faltam / ritmo))
        data_estimada = (
            agora.date() + timedelta(days=dias_estimados)
        ).isoformat()
    else:
        dias_estimados = None
        data_estimada = None
    if len(recentes) < 5:
        confiabilidade = "sem_ritmo"
    elif dias_observados < 3 or len(recentes) < 15:
        confiabilidade = "preliminar"
    else:
        confiabilidade = "observada"
    return {
        "amostra": amostra,
        "faltam": faltam,
        "resultados_janela": len(recentes),
        "dias_observados": dias_observados,
        "ritmo_dia": round(ritmo, 2),
        "dias_estimados": dias_estimados,
        "data_estimada": data_estimada,
        "confiabilidade_estimativa": confiabilidade,
    }


def resumir_progresso_calibracao(
    conexao,
    agora=None,
    regra_versao=VERSAO_REGRAS,
    mercados=MERCADOS_CALIBRADOS,
    usar_versoes_ativas=False,
):
    agora = agora or datetime.now()
    limites = obter_limites_risco()
    return {
        mercado: calcular_progresso_amostra(
            carregar_amostra_independente(
                conexao,
                mercado,
                (
                    versao_regra_para_mercado(mercado)
                    if usar_versoes_ativas else regra_versao
                ),
                limites,
                somente_executaveis=True,
            ),
            agora,
        )
        for mercado in mercados
    }
