"""Filtro protegido de Gol FT derivado da revisão de 08/09/2026."""

from copy import deepcopy
import math

from configuracao import obter_limites_risco
from versoes_gol_ft_reforcado import (
    VERSAO_GOL_FT_REFORCADO,
    gol_ft_reforcado_ativo,
    gol_ft_reforcado_oficial_ativo,
)


MERCADO = "gol_ft"
VERSAO_BASE = "sinais-v6"
MINUTO_MAXIMO = 70.0
ODD_MAXIMA_EXCLUSIVA = 1.90
XG_TOTAL_MINIMO = 1.50
CHUTES_5_MIN_MINIMOS = 3.0
CHUTES_NO_GOL_TOTAL_MINIMOS = 7.0
PRESSAO_PICO_5_MIN_MINIMA = 75.0
MOTIVO_SOMBRA_BASE = "gol_ft_v6_preservado_em_sombra"


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _total_xg_contexto(contexto_api):
    times = (
        ((contexto_api or {}).get("estatisticas_ao_vivo") or {})
        .get("times") or {}
    )
    valores = []
    for lado in ("mandante", "visitante"):
        xg = _numero((times.get(lado) or {}).get("xg"))
        if xg is None:
            return None
        valores.append(xg)
    return round(sum(valores), 4)


def _maximo_par(valor):
    if not isinstance(valor, (list, tuple)):
        return None
    numeros = [_numero(item) for item in valor]
    numeros = [item for item in numeros if item is not None]
    return max(numeros) if numeros else None


def avaliar_gol_ft_reforcado(candidato, contexto_api=None):
    features = candidato.get("features") or {}
    janela5 = ((features.get("janelas") or {}).get("5") or {})
    minuto = _numero(features.get("minuto"))
    odd = _numero(candidato.get("odd"))
    chutes5 = _numero(janela5.get("chutes_total"))
    chutes_no_gol = _numero(features.get("chutes_no_gol_total"))
    pico_pressao = _maximo_par(janela5.get("pressao_pico"))
    xg_total = _total_xg_contexto(contexto_api)
    limites = obter_limites_risco()

    criterios = {
        "minuto_valido": bool(
            minuto is not None and minuto <= MINUTO_MAXIMO
        ),
        "odd_valida": bool(
            odd is not None
            and float(limites.odd_minima) <= odd < ODD_MAXIMA_EXCLUSIVA
        ),
        "xg_forte": bool(
            xg_total is not None and xg_total >= XG_TOTAL_MINIMO
        ),
        "packball_forte": bool(
            chutes5 is not None and chutes5 >= CHUTES_5_MIN_MINIMOS
            and chutes_no_gol is not None
            and chutes_no_gol >= CHUTES_NO_GOL_TOTAL_MINIMOS
            and pico_pressao is not None
            and pico_pressao >= PRESSAO_PICO_5_MIN_MINIMA
        ),
    }
    aprovada = bool(
        criterios["minuto_valido"]
        and criterios["odd_valida"]
        and (criterios["xg_forte"] or criterios["packball_forte"])
    )
    return {
        "versao": VERSAO_GOL_FT_REFORCADO,
        "aprovada": aprovada,
        "criterios": criterios,
        "medidas": {
            "minuto": minuto,
            "odd": odd,
            "xg_total": xg_total,
            "chutes_5min": chutes5,
            "chutes_no_gol_total": chutes_no_gol,
            "pressao_pico_5min": pico_pressao,
        },
        "limites": {
            "minuto_maximo": MINUTO_MAXIMO,
            "odd_maxima_exclusiva": ODD_MAXIMA_EXCLUSIVA,
            "xg_total_minimo": XG_TOTAL_MINIMO,
            "chutes_5min_minimos": CHUTES_5_MIN_MINIMOS,
            "chutes_no_gol_total_minimos": CHUTES_NO_GOL_TOTAL_MINIMOS,
            "pressao_pico_5min_minima": PRESSAO_PICO_5_MIN_MINIMA,
        },
        "rollback": "GOL_FT_REFORCADO_ATIVO=0",
    }


def aplicar_politica_gol_ft_reforcado(
    candidatos, contexto_api=None, environ=None
):
    oficial_ativo = gol_ft_reforcado_oficial_ativo(environ)
    diagnostico = {
        "ativa": gol_ft_reforcado_ativo(environ),
        "oficial_ativo": oficial_ativo,
        "avaliados": 0,
        "elegiveis": 0,
        "oficiais": 0,
        "reforcados_sombra": 0,
        "v6_sombra": 0,
        "versao": VERSAO_GOL_FT_REFORCADO,
        "rollback": "GOL_FT_REFORCADO_ATIVO=0",
        "reativacao_oficial": "GOL_FT_REFORCADO_OFICIAL_ATIVO=1",
    }
    if not diagnostico["ativa"]:
        return diagnostico

    novos = []
    for candidato in list(candidatos or []):
        if not (
            candidato.get("mercado") == MERCADO
            and candidato.get("regra_versao") == VERSAO_BASE
            and candidato.get("status") == "aprovado"
        ):
            continue
        diagnostico["avaliados"] += 1
        avaliacao = avaliar_gol_ft_reforcado(candidato, contexto_api)

        features_base = candidato.setdefault("features", {})
        features_base["gol_ft_reforcado_sombra"] = deepcopy(avaliacao)
        motivos_base = list(candidato.get("motivos") or [])
        if MOTIVO_SOMBRA_BASE not in motivos_base:
            motivos_base.append(MOTIVO_SOMBRA_BASE)
        candidato["motivos"] = motivos_base
        candidato["status"] = "simulacao"
        diagnostico["v6_sombra"] += 1

        if not avaliacao["aprovada"]:
            continue
        diagnostico["elegiveis"] += 1
        reforcado = deepcopy(candidato)
        reforcado["regra_versao"] = VERSAO_GOL_FT_REFORCADO
        reforcado["status"] = (
            "aprovado" if oficial_ativo else "simulacao"
        )
        reforcado.pop("_status_persistido", None)
        features = reforcado.setdefault("features", {})
        features.pop("gol_ft_reforcado_sombra", None)
        features["gol_ft_reforcado"] = deepcopy(avaliacao)
        features["gol_ft_reforcado"]["modo"] = (
            "oficial" if oficial_ativo else "validacao_sombra"
        )
        features["gol_ft_reforcado"]["telegram"] = oficial_ativo
        features["gol_ft_reforcado"]["promocao_automatica"] = False
        motivos = [
            item for item in (reforcado.get("motivos") or [])
            if item != MOTIVO_SOMBRA_BASE
        ]
        motivos.extend((
            (
                "gol_ft_reforcado_oficial"
                if oficial_ativo
                else "gol_ft_reforcado_validacao_sombra"
            ),
            "confirmacao_xg_ou_packball_forte",
            "minuto_maximo_70",
            "odd_abaixo_190",
        ))
        if not oficial_ativo:
            motivos.append("nao_enviar_telegram_sem_vantagem_comprovada")
        reforcado["motivos"] = list(dict.fromkeys(motivos))
        novos.append(reforcado)
        if oficial_ativo:
            diagnostico["oficiais"] += 1
        else:
            diagnostico["reforcados_sombra"] += 1

    candidatos.extend(novos)
    return diagnostico
