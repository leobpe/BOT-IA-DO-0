"""Espera condicional de preço, sem criar uma entrada ou consumir a coorte.

O preço-alvo é usado somente em uma cópia para perguntar ao método existente
se a análise seria elegível nesse preço. A observação sempre conserva a odd
real. Antes do envio, o mesmo gerador é executado novamente com a oferta real.
"""

import copy
import math
import os

from acompanhamento_odd import BLOQUEIOS_SOMENTE_ODD, acompanhamento_odd_ativo
from configuracao import obter_limites_risco
from gol_2t_pos_ht_red import gerar_gol_2t_pos_ht_red, ODD_MINIMA as MIN_2T
from gol_ft_tendencia_mais_um import (
    gerar_gol_ft_tendencia_mais_um, ODD_MINIMA_DISPARO as MIN_FT,
)
from gol_ht_00_min20 import gerar_gol_ht_00_min20, ODD_MINIMA_DISPARO as MIN_HT
from gols_antecipados import gerar_gols_antecipados
from gols_capacidade_contextual_v2 import gerar_gols_capacidade_contextual_v2
from gols_capacidade_times import gerar_gols_capacidade_times
from top_criterios_gols import gerar_top_criterio_ft, gerar_top_criterio_ht


VERSAO = "acompanhamento-metodos-gols-v1"
CHAVE = "acompanhamento_metodo_gols"
# Uma consulta de preço não renova chutes, pressão ou eventos. Uma leitura
# mais antiga deve ser renovada pelo ciclo técnico normal antes da conversão.
IDADE_MAXIMA_REANALISE_SEGUNDOS = 120


def _numero(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _familias():
    return {
        "antecipados": 0, "capacidade_v1": 0, "capacidade_v2": 0,
        "ht_00": MIN_HT, "ft_tendencia": MIN_FT, "2t_pos_ht": MIN_2T,
    }


def _gerar(familia, jogo, base, contexto, qualidade, tendencia_ht):
    if familia == "antecipados":
        return gerar_gols_antecipados(jogo, [base], contexto, qualidade)
    if familia == "capacidade_v1":
        return gerar_gols_capacidade_times(jogo, [base], contexto, qualidade)
    if familia == "capacidade_v2":
        return gerar_gols_capacidade_contextual_v2(jogo, [base], contexto, qualidade)
    if familia == "ht_00":
        pais = gerar_gol_ht_00_min20(jogo, [base], contexto, qualidade)
        return pais + gerar_top_criterio_ht(pais, contexto)
    if familia == "ft_tendencia":
        pais = gerar_gol_ft_tendencia_mais_um(jogo, [base], contexto, qualidade)
        return pais + gerar_top_criterio_ft(pais, contexto)
    if familia == "2t_pos_ht":
        return gerar_gol_2t_pos_ht_red(jogo, [base], qualidade, tendencia_ht)
    return []


def _base_no_preco(original, odd, oferta=None):
    base = copy.deepcopy(original)
    base["odd"] = odd
    base["bloqueios"] = [
        b for b in base.get("bloqueios") or [] if b not in BLOQUEIOS_SOMENTE_ODD
    ]
    features = base.setdefault("features", {})
    movimento = features.get("movimento_gols")
    if isinstance(movimento, dict):
        anterior = _numero(movimento.get("odd_anterior"))
        atual = _numero(movimento.get("odd_atual"))
        real = _numero(original.get("odd"))
        mesma_fonte = oferta is None or bool(
            oferta.get("fonte") and oferta.get("bookmaker")
            and oferta["fonte"] == features.get("fonte_odds")
            and oferta["bookmaker"] == features.get("bookmaker_odds")
        )
        if (mesma_fonte and anterior is not None and atual is not None
                and real is not None and abs(atual - real) <= 0.15):
            delta = round(odd - anterior, 4)
            movimento.update({
                "odd_atual": odd, "delta": delta,
                "direcao": "alta" if delta > 0 else "queda" if delta < 0 else "estavel",
            })
        else:
            # Não transportar movimento antigo ou de outra casa para a nova
            # oferta. O método tratará esse dado como indisponível.
            features.pop("movimento_gols", None)
    return base


def _linhagens(features):
    return {
        nome: dados["linhagem_sha256"] for nome, dados in features.items()
        if isinstance(dados, dict) and "linhagem_sha256" in dados
    }


def gerar_acompanhamentos_metodos_gols(
    jogo, candidatos, contexto, qualidade, alertas, tendencia_ht=None,
):
    filtro = getattr(alertas, "motivo_filtro_teste", None)
    if (not acompanhamento_odd_ativo()
            or not getattr(alertas, "modo_teste", False) or not callable(filtro)
            or os.getenv("ACOMPANHAMENTO_METODOS_GOLS_ATIVO", "1") != "1"):
        return []
    limites = obter_limites_risco()
    alvo_global = max(limites.odd_minima, _numero(os.getenv(
        "AVISO_AGUARDAR_ODD_ALVO", str(limites.odd_minima)
    )) or limites.odd_minima)
    piso = max(1.01, _numero(os.getenv("AVISO_AGUARDAR_ODD_PISO", "1.10")) or 1.10)
    gerados = []
    vistos = set()
    for original in candidatos or []:
        features = original.get("features") or {}
        odd_real = _numero(original.get("odd"))
        if (original.get("mercado") not in {"gol_ht", "gol_ft"}
                or original.get("status") != "rejeitado"
                or features.get("exploracao_sombra") or features.get(CHAVE)
                or odd_real is None or odd_real < piso):
            continue
        for familia, minimo in _familias().items():
            alvo = max(alvo_global, minimo)
            if not odd_real < alvo <= limites.odd_maxima:
                continue
            base = _base_no_preco(original, alvo)
            for calculado in _gerar(familia, jogo, base, contexto, qualidade, tendencia_ht):
                calculado["qualidade_dados"] = qualidade.get("pontuacao", 0)
                if calculado.get("bloqueios") or filtro(calculado) is not None:
                    continue
                f = calculado["features"]
                metodo = (f.get("exploracao_sombra") or {}).get("versao")
                chave = (calculado["mercado"], str(calculado["linha"]), metodo)
                if not metodo or chave in vistos:
                    continue
                vistos.add(chave)
                f[CHAVE] = {
                    "versao": VERSAO, "familia": familia, "metodo": metodo,
                    "odd_alvo": alvo, "odd_observada": odd_real,
                    "calculo_condicional_ao_preco_alvo": True,
                    "validade_tecnica_segundos": IDADE_MAXIMA_REANALISE_SEGUNDOS,
                    "linhagens": _linhagens(f),
                    "base_candidato": copy.deepcopy(original),
                    "tendencia_ht": copy.deepcopy(tendencia_ht) if familia == "2t_pos_ht" else None,
                    "exploracao_condicional": f.pop("exploracao_sombra"),
                    "rollback": "ACOMPANHAMENTO_METODOS_GOLS_ATIVO=0",
                }
                # Só os diagnósticos do método são condicionais. A cotação e
                # o movimento observado no snapshot permanecem os reais.
                if "movimento_gols" in features:
                    f["movimento_gols"] = copy.deepcopy(features["movimento_gols"])
                calculado.update({
                    "odd": odd_real, "probabilidade_calibrada": None,
                    "status": "rejeitado", "bloqueios": ["odd_fora_da_faixa_operacional"],
                    "motivos": ["metodo_elegivel_condicionalmente_ao_preco_alvo"],
                })
                gerados.append(calculado)
    return gerados


def revalidar_metodo_acompanhado(
    features, jogo, contexto, qualidade, oferta, alertas, idade_tecnica,
):
    """Retorna (candidato recalculado, motivo). Nunca grava nem envia."""
    meta = features.get(CHAVE)
    if not meta:
        return None, None  # Compatibilidade com observações legadas.
    if (meta.get("versao") != VERSAO or meta.get("familia") not in _familias()
            or os.getenv("ACOMPANHAMENTO_METODOS_GOLS_ATIVO", "1") != "1"):
        return None, "acompanhamento_metodo_desativado_ou_incompativel"
    idade = _numero(idade_tecnica)
    if idade is None or not 0 <= idade <= IDADE_MAXIMA_REANALISE_SEGUNDOS:
        return None, "leitura_recente_do_metodo_precisa_renovacao"
    filtro = getattr(alertas, "motivo_filtro_teste", None)
    if not getattr(alertas, "modo_teste", False) or not callable(filtro):
        return None, "rota_do_metodo_nao_autorizada"
    odd = _numero(oferta.get("odd"))
    if odd is None or odd < max(meta.get("odd_alvo", 0), obter_limites_risco().odd_minima):
        return None, "odd_alvo_do_metodo_nao_atingida"
    base = _base_no_preco(meta["base_candidato"], odd, oferta)
    base["features"]["minuto"] = jogo["minuto"]
    for item in _gerar(meta["familia"], jogo, base, contexto, qualidade, meta.get("tendencia_ht")):
        f = item.get("features") or {}
        if (f.get("exploracao_sombra") or {}).get("versao") != meta.get("metodo"):
            continue
        if _linhagens(f) != meta.get("linhagens"):
            return None, "linhagem_do_metodo_alterada"
        item["qualidade_dados"] = qualidade.get("pontuacao", 0)
        motivo = filtro(item)
        if motivo:
            return None, motivo
        if not item.get("bloqueios"):
            return item, None
    return None, "criterios_do_metodo_nao_confirmados_na_odd_atual"
