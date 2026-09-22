"""Auditorias persistentes das regras prospectivas em produção."""

import json
import math
from collections import Counter

from configuracao import obter_limites_risco
from politica_proximo_gol_preciso import (
    MINUTO_MAXIMO,
    ODD_MAXIMA_EXCLUSIVA,
    PRESSAO_PICO_5_MIN_MINIMA,
    QUALIDADE_MINIMA,
    avaliar_criterios_precisos,
)
from versoes_challengers_preciso import VERSAO_PROXIMO_GOL_FILTRO_PRECISO


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def auditar_regra_proximo_gol(conexao):
    limites = obter_limites_risco()
    """Confirma que toda aprovação da V10f respeita o filtro preciso."""
    linhas = conexao.execute(
        """
        SELECT id, mercado, odd, features_json, status, motivos_json
        FROM sinais
        WHERE regra_versao=?
        ORDER BY id
        """,
        (VERSAO_PROXIMO_GOL_FILTRO_PRECISO,),
    ).fetchall()
    violacoes = []
    aprovadas = 0
    funil = {
        "mercado_correto": 0,
        "dentro_janela": 0,
        "historico_5min": 0,
        "atividade_recente": 0,
        "odd_minima": 0,
        "qualidade_100": 0,
        "pressao_pico_70": 0,
        "sem_outros_bloqueios": 0,
        "aprovadas": 0,
    }
    cobertura_independente = {
        "dentro_janela": 0,
        "historico_5min": 0,
        "atividade_recente": 0,
        "odd_disponivel": 0,
        "odd_fresca": 0,
        "odd_minima": 0,
        "qualidade_100": 0,
        "pressao_pico_70": 0,
    }
    bloqueios = Counter()
    for linha in linhas:
        sinal_id = int(linha[0])
        mercado = linha[1]
        if mercado != "proximo_gol":
            violacoes.append({
                "sinal_id": sinal_id,
                "motivo": "mercado_incorreto",
            })
            continue
        funil["mercado_correto"] += 1
        odd = _numero(linha[2])
        try:
            features = json.loads(linha[3] or "{}")
        except (TypeError, json.JSONDecodeError):
            features = {}
        minuto = _numero(
            features.get("minuto") if isinstance(features, dict) else None
        )
        idade_odds = _numero(
            features.get("idade_odds_segundos")
            if isinstance(features, dict) else None
        )
        qualidade = _numero(features.get("qualidade_dados"))
        lado = features.get("lado_dominante")
        indice = 0 if lado == "casa" else 1 if lado == "visitante" else None
        picos = (((features.get("janelas") or {}).get("5") or {}).get(
            "pressao_pico"
        ) or [])
        pico = _numero(picos[indice]) if (
            indice is not None and len(picos) > indice
        ) else None
        try:
            motivos = json.loads(linha[5] or "[]")
        except (TypeError, json.JSONDecodeError):
            motivos = []
        if not isinstance(motivos, list):
            motivos = []
        bloqueios_linha = {
            str(item).split("bloqueio:", 1)[1]
            for item in motivos
            if str(item).startswith("bloqueio:")
        }
        bloqueios.update(bloqueios_linha)
        dentro_janela = bool(
            minuto is not None and minuto <= MINUTO_MAXIMO
        )
        historico_5min = (
            "historico_5min_insuficiente" not in bloqueios_linha
        )
        atividade_recente = not bool({
            "atividade_recente_insuficiente_gols",
            "lado_dominante_sem_chute_recente",
        } & bloqueios_linha)
        limites = obter_limites_risco()
        odd_minima = bool(
            odd is not None
            and limites.odd_minima <= odd < ODD_MAXIMA_EXCLUSIVA
        )
        qualidade_100 = bool(
            qualidade is not None and qualidade >= QUALIDADE_MINIMA
        )
        pressao_pico_70 = bool(
            pico is not None and pico >= PRESSAO_PICO_5_MIN_MINIMA
        )
        odd_fresca = bool(
            odd is not None
            and idade_odds is not None
            and idade_odds <= 360
        )
        cobertura_independente["dentro_janela"] += int(dentro_janela)
        cobertura_independente["historico_5min"] += int(historico_5min)
        cobertura_independente["atividade_recente"] += int(
            atividade_recente
        )
        cobertura_independente["odd_disponivel"] += int(odd is not None)
        cobertura_independente["odd_fresca"] += int(odd_fresca)
        cobertura_independente["odd_minima"] += int(odd_minima)
        cobertura_independente["qualidade_100"] += int(qualidade_100)
        cobertura_independente["pressao_pico_70"] += int(pressao_pico_70)
        if dentro_janela:
            funil["dentro_janela"] += 1
            if historico_5min:
                funil["historico_5min"] += 1
                if atividade_recente:
                    funil["atividade_recente"] += 1
                    if odd_minima:
                        funil["odd_minima"] += 1
                        if qualidade_100:
                            funil["qualidade_100"] += 1
                            if pressao_pico_70:
                                funil["pressao_pico_70"] += 1
                                if not bloqueios_linha:
                                    funil["sem_outros_bloqueios"] += 1
        if linha[4] != "aprovado":
            continue
        aprovadas += 1
        funil["aprovadas"] += 1
        criterios_invalidos = avaliar_criterios_precisos({
            "mercado": mercado,
            "odd": odd,
            "features": features,
        })
        if criterios_invalidos:
            violacoes.append({
                "sinal_id": sinal_id,
                "motivo": criterios_invalidos[0],
            })

    return {
        "saudavel": not violacoes,
        "regra_versao": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
        "decisoes": len(linhas),
        "aprovadas": aprovadas,
        "violacoes": len(violacoes),
        "detalhes_violacoes": violacoes[:20],
        "funil": funil,
        "cobertura_independente": cobertura_independente,
        "bloqueios_principais": [
            {"motivo": motivo, "quantidade": quantidade}
            for motivo, quantidade in sorted(
                bloqueios.items(), key=lambda item: (-item[1], item[0])
            )[:10]
        ],
        "criterios": {
            "odd_minima": limites.odd_minima,
            "odd_maxima_exclusiva": ODD_MAXIMA_EXCLUSIVA,
            "minuto_maximo": MINUTO_MAXIMO,
            "qualidade_minima": QUALIDADE_MINIMA,
            "pressao_pico_5min_minima": PRESSAO_PICO_5_MIN_MINIMA,
        },
    }
