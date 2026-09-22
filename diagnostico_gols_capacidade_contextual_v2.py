"""Telemetria externa do V2b, sem alterar a linhagem congelada do método."""

import math

import gols_capacidade_contextual_v2 as v2
from configuracao import odd_elegivel, obter_limites_risco
from qualidade_dados import extrair_minuto, extrair_placar


VERSAO = "diagnostico-gols-capacidade-contextual-v2b-v1"
LINHAGEM_POLITICA_COMPATIVEL = (
    "f5873c34dd54a96eac8c027677bda79171dd923dc02bc90688c5070bda178faf"
)


def _numero(valor):
    try:
        numero = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
    return numero if numero is not None and math.isfinite(numero) else None


def _resultado(estado, motivo, **detalhes):
    return {"estado": estado, "motivo": motivo, **detalhes}


def _motivo_global(jogo, qualidade, candidatos):
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    ausentes = sorted(set((qualidade or {}).get("campos_ausentes") or []))
    if minuto is None:
        return _resultado("nao_elegivel", "minuto_indisponivel")
    if minuto < v2.MINUTO_MINIMO:
        return _resultado("nao_elegivel", "antes_minuto_minimo")
    if minuto > v2.MINUTO_MAXIMO_FT:
        return _resultado("nao_elegivel", "apos_minuto_maximo_ft")
    if placar is None:
        return _resultado("nao_elegivel", "placar_indisponivel")
    if (_numero((qualidade or {}).get("pontuacao")) or 0) < v2.QUALIDADE_MINIMA:
        return _resultado(
            "nao_elegivel", "qualidade_abaixo_minimo",
            qualidade=_numero((qualidade or {}).get("pontuacao")),
        )
    if ausentes:
        return _resultado(
            "nao_elegivel", "campos_qualidade_ausentes",
            campos_ausentes=ausentes,
        )
    if (qualidade or {}).get("divergencia_critica") is True:
        return _resultado("nao_elegivel", "divergencia_critica")
    if not any(
        item.get("mercado") in {"gol_ht", "gol_ft"}
        and item.get("odd") is not None
        for item in candidatos or []
    ):
        return _resultado(
            "nao_elegivel", "candidato_base_com_odd_ausente"
        )
    return None


def _diagnosticar_mercado(
    mercado, jogo, candidatos, contexto, qualidade, gerados
):
    versao = v2.VERSAO_GOL_HT if mercado == "gol_ht" else v2.VERSAO_GOL_FT
    gerado = next(
        (
            item for item in gerados or []
            if ((item.get("features") or {}).get("exploracao_sombra") or {})
            .get("versao") == versao
        ),
        None,
    )
    if gerado is not None:
        dados = (
            (gerado.get("features") or {})
            .get("gol_capacidade_contextual_v2") or {}
        )
        return _resultado(
            "gerado", "candidato_gerado",
            minuto=dados.get("minuto"),
            probabilidade=dados.get("probabilidade_estimada_nao_calibrada"),
            edge=dados.get("edge_estimado_nao_calibrado"),
            odd=_numero(gerado.get("odd")),
        )

    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    limite = v2.MINUTO_MAXIMO_HT if mercado == "gol_ht" else v2.MINUTO_MAXIMO_FT
    fim = 45 if mercado == "gol_ht" else 90
    base = next(
        (
            item for item in candidatos or []
            if item.get("mercado") == mercado
            and not ((item.get("features") or {}).get("exploracao_sombra"))
        ),
        None,
    )
    if base is None:
        return _resultado("bloqueado", "candidato_base_ausente")
    if minuto > limite:
        return _resultado(
            "bloqueado", "apos_minuto_maximo_mercado",
            minuto=minuto, minuto_maximo=limite,
        )
    linha, odd = _numero(base.get("linha")), _numero(base.get("odd"))
    if linha is None or odd is None:
        return _resultado("bloqueado", "linha_ou_odd_invalida")
    linha_esperada = sum(placar) + 0.5
    if linha != linha_esperada:
        return _resultado(
            "bloqueado", "linha_nao_e_um_gol",
            linha=linha, linha_esperada=linha_esperada,
        )
    if not odd_elegivel(odd, obter_limites_risco()):
        return _resultado(
            "bloqueado", "odd_fora_faixa_operacional", odd=odd
        )
    if mercado == "gol_ht" and linha < 1.5:
        return _resultado("bloqueado", "linha_05_ht_excluida")
    modelo = v2._modelo_historico(contexto, minuto, fim, placar)
    if modelo is None:
        cobertura = (
            ((contexto or {}).get("capacidade_times_v2") or {})
            .get("cobertura") or {}
        )
        return _resultado(
            "bloqueado", "historico_contextual_insuficiente",
            cobertura=cobertura,
        )
    recente = v2._evidencia_recente(base, contexto, qualidade)
    if len(recente["evidencias"]) < 2:
        return _resultado(
            "bloqueado", "evidencias_recentes_insuficientes",
            evidencias=list(recente["evidencias"]),
        )
    if mercado == "gol_ht" and not recente["forte"]:
        return _resultado(
            "bloqueado", "evidencia_recente_ht_sem_forca",
            evidencias=list(recente["evidencias"]),
        )
    eventos = v2._estado_eventos(contexto, minuto)
    if eventos["cartoes_vermelhos"]:
        return _resultado(
            "bloqueado", "cartao_vermelho",
            cartoes_vermelhos=eventos["cartoes_vermelhos"],
        )
    movimento = v2._movimento_odd_confiavel(base)
    if (
        movimento.get("disponivel")
        and movimento.get("direcao") in {"alta", "subida"}
        and float(movimento.get("delta") or 0) >= 0.10
    ):
        return _resultado(
            "bloqueado", "odd_em_alta_relevante",
            movimento_odd=movimento,
        )
    bloqueios = [
        item for item in base.get("bloqueios") or []
        if item not in v2._BLOQUEIOS_RELAXAVEIS
    ]
    if bloqueios:
        return _resultado(
            "bloqueado", "bloqueio_base_nao_relaxavel",
            bloqueios=bloqueios,
        )

    multiplicador = 1.0
    if (recente.get("chutes_5min") or 0) >= 3:
        multiplicador *= 1.06
    if (recente.get("xg_5min") or 0) >= 0.15:
        multiplicador *= 1.08
    if (recente.get("pressao_5min") or 0) >= 65:
        multiplicador *= 1.06
    if (
        recente.get("tendencia_pressao_5min") is not None
        and recente["tendencia_pressao_5min"] < 0
    ):
        multiplicador *= 0.94
    if eventos["substituicoes"] >= 4 and minuto >= 65:
        multiplicador *= 0.92
    if movimento.get("disponivel") and movimento.get("direcao") == "queda":
        multiplicador *= 1.03
    lambda_final = modelo["lambda_restante_base"] * multiplicador
    probabilidade = 1.0 - math.exp(-max(lambda_final, 0.0))
    edge = probabilidade - 1.0 / odd
    if probabilidade < v2.PROBABILIDADE_MINIMA:
        return _resultado(
            "bloqueado", "probabilidade_abaixo_minimo",
            probabilidade=round(probabilidade, 4),
            minima=v2.PROBABILIDADE_MINIMA, edge=round(edge, 4),
        )
    if edge < v2.EDGE_MINIMO:
        return _resultado(
            "bloqueado", "edge_abaixo_minimo",
            probabilidade=round(probabilidade, 4),
            edge=round(edge, 4), minimo=v2.EDGE_MINIMO,
        )
    return _resultado("inconsistente", "gerador_nao_retornou_candidato")


def diagnosticar_gols_capacidade_contextual_v2(
    jogo, candidatos, contexto, qualidade, gerados=None
):
    resumo = {
        "versao": VERSAO,
        "linhagem_politica": v2.LINHAGEM,
        "linhagem_compativel": v2.LINHAGEM == LINHAGEM_POLITICA_COMPATIVEL,
        "executado": True,
        "gerados": len(gerados or []),
        "por_mercado": {},
    }
    global_ = _motivo_global(jogo, qualidade, candidatos)
    for mercado in ("gol_ht", "gol_ft"):
        resumo["por_mercado"][mercado] = (
            dict(global_)
            if global_ is not None
            else _diagnosticar_mercado(
                mercado, jogo, candidatos, contexto, qualidade, gerados
            )
        )
    return resumo
