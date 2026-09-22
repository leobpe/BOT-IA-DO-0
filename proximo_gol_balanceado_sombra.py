"""Challenger prospectivo controlado para ampliar o Proximo Gol.

A hipotese nasceu de uma triagem retroativa pequena e, por isso, nao pode
virar alerta oficial ainda. Ela preserva integralmente a V10f e libera apenas
o bloqueio de pressao quando ha ao menos uma finalizacao recente do lado
dominante, vantagem media de pressao, qualidade completa, pontuacao tecnica
minima e odd curta. A coorte futura fica congelada no SQLite e os candidatos
podem ser mostrados somente no grupo de teste, claramente identificados.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from copy import deepcopy
from datetime import datetime

from politica_proximo_gol_preciso import (
    MINUTO_MAXIMO,
    MOTIVO_PRESSAO,
    MOTIVO_QUALIDADE,
    ODD_MAXIMA_EXCLUSIVA,
)
from versoes_challengers_preciso import VERSAO_PROXIMO_GOL_FILTRO_PRECISO
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)


VERSAO = "proximo-gol-balanceado-sombra-v4"
CHAVE_DEFINICAO = (
    "exploracao_sombra_definicao:"
    + VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA
)
QUALIDADE_MINIMA_BALANCEADA = 95.0
PRESSAO_MINIMA = 50.0
PRESSAO_MEDIA_DIFERENCA_MINIMA = 10.0
CHUTES_DOMINANTE_5MIN_MINIMOS = 1.0
PONTUACAO_TECNICA_MINIMA = 60.0
ODD_MAXIMA_BALANCEADA_EXCLUSIVA = 1.65
TAMANHO_COORTE = 40
RESULTADOS_VALIDOS_MINIMOS = 35


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _pico_dominante(features):
    lado = features.get("lado_dominante")
    indice = 0 if lado == "casa" else 1 if lado == "visitante" else None
    picos = (((features.get("janelas") or {}).get("5") or {}).get(
        "pressao_pico"
    ) or [])
    if (
        indice is None
        or not isinstance(picos, (list, tuple))
        or len(picos) <= indice
    ):
        return None
    return _numero(picos[indice])


def _medias_pressao(features):
    lado = features.get("lado_dominante")
    indice = 0 if lado == "casa" else 1 if lado == "visitante" else None
    medias = (((features.get("janelas") or {}).get("5") or {}).get(
        "pressao_media"
    ) or [])
    if (
        indice is None
        or not isinstance(medias, (list, tuple))
        or len(medias) < 2
    ):
        return None, None
    return _numero(medias[indice]), _numero(medias[1 - indice])


def definicao():
    nucleo = {
        "versao": VERSAO,
        "regra_versao": VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
        "derivada_de": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
        "fase": "validacao_prospectiva",
        "mercado": "proximo_gol",
        "bloqueios_relaxaveis_exatos": [
            [MOTIVO_PRESSAO],
            sorted([MOTIVO_PRESSAO, MOTIVO_QUALIDADE]),
        ],
        "criterios": {
            "qualidade_minima": QUALIDADE_MINIMA_BALANCEADA,
            "pressao_pico_5min_minima": PRESSAO_MINIMA,
            "vantagem_pressao_media_5min_minima": (
                PRESSAO_MEDIA_DIFERENCA_MINIMA
            ),
            "chutes_dominante_5min_minimos": (
                CHUTES_DOMINANTE_5MIN_MINIMOS
            ),
            "pontuacao_tecnica_minima": PONTUACAO_TECNICA_MINIMA,
            "odd_maxima_exclusiva": ODD_MAXIMA_BALANCEADA_EXCLUSIVA,
            "minuto_maximo": MINUTO_MAXIMO,
        },
        "coorte_fixa": TAMANHO_COORTE,
        "resultados_validos_minimos": RESULTADOS_VALIDOS_MINIMOS,
        "evidencia_geradora": {
            "uso": "somente_geracao_de_hipotese",
            "amostra_retroativa": 17,
            "greens": 13,
            "reds": 4,
            "roi": 0.1592,
            "desenvolvimento": {
                "amostra": 11,
                "greens": 8,
                "reds": 3,
                "roi": 0.1128,
            },
            "holdout_cronologico": {
                "amostra": 6,
                "greens": 5,
                "reds": 1,
                "roi": 0.2444,
            },
            "alerta": (
                "corte_exploratorio_com_amostra_pequena_nao_comprova_vantagem"
            ),
        },
        "status": "simulacao",
        "telegram": "somente_grupo_teste",
        "telegram_oficial": False,
        "aplicacao_sinais": False,
        "promocao_automatica": False,
        "rollback": "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO=0",
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


def registrar_ou_validar_definicao(conexao, registrado_em=None):
    esperada = definicao()
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in esperada.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Definicao do Proximo Gol balanceado diverge da ancora "
                    "imutavel do SQLite."
                )
        return existente
    esperada["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                CHAVE_DEFINICAO,
                json.dumps(esperada, ensure_ascii=False, sort_keys=True),
            ),
        )
    return esperada


def ativa(environ=None):
    environ = os.environ if environ is None else environ
    return str(environ.get(
        "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO", "1"
    )).strip().casefold() not in {"0", "false", "nao", "não", "off"}


def avaliar(candidato):
    features = candidato.get("features") or {}
    bloqueios = {
        str(item).strip() for item in candidato.get("bloqueios") or []
        if str(item).strip()
    }
    odd = _numero(candidato.get("odd"))
    minuto = _numero(features.get("minuto"))
    qualidade = _numero(features.get("qualidade_dados"))
    pico = _pico_dominante(features)
    pressao_media, pressao_media_adversario = _medias_pressao(features)
    chutes = _numero(features.get("chutes_lado_dominante_5min"))
    pontuacao = _numero(candidato.get("pontuacao_tecnica"))
    criterios = {
        "origem_v10f": (
            candidato.get("regra_versao")
            == VERSAO_PROXIMO_GOL_FILTRO_PRECISO
        ),
        "somente_bloqueios_pressao_qualidade": bool(
            MOTIVO_PRESSAO in bloqueios
            and bloqueios <= {MOTIVO_PRESSAO, MOTIVO_QUALIDADE}
        ),
        "qualidade_completa": bool(
            qualidade is not None
            and qualidade >= QUALIDADE_MINIMA_BALANCEADA
        ),
        "pressao_balanceada": bool(
            pico is not None and PRESSAO_MINIMA <= pico < 70.0
        ),
        "dominio_medio_confirmado": bool(
            pressao_media is not None
            and pressao_media_adversario is not None
            and pressao_media - pressao_media_adversario
            >= PRESSAO_MEDIA_DIFERENCA_MINIMA
        ),
        "chute_dominante_recente": bool(
            chutes is not None
            and chutes >= CHUTES_DOMINANTE_5MIN_MINIMOS
        ),
        "pontuacao_tecnica_suficiente": bool(
            pontuacao is not None
            and pontuacao >= PONTUACAO_TECNICA_MINIMA
        ),
        "odd_curta": bool(
            odd is not None
            and 1.40 <= odd < ODD_MAXIMA_BALANCEADA_EXCLUSIVA
            and odd < ODD_MAXIMA_EXCLUSIVA
        ),
        "minuto_valido": bool(
            minuto is not None and minuto <= MINUTO_MAXIMO
        ),
    }
    return {
        "elegivel": bool(all(criterios.values())),
        "criterios": criterios,
        "medidas": {
            "odd": odd,
            "minuto": minuto,
            "qualidade": qualidade,
            "pressao_pico_5min": pico,
            "pressao_media_5min": pressao_media,
            "pressao_media_adversario_5min": pressao_media_adversario,
            "vantagem_pressao_media_5min": (
                pressao_media - pressao_media_adversario
                if pressao_media is not None
                and pressao_media_adversario is not None
                else None
            ),
            "chutes_dominante_5min": chutes,
            "pontuacao_tecnica": pontuacao,
        },
    }


def gerar(candidatos, environ=None):
    if not ativa(environ):
        return []
    definicao_atual = definicao()
    novos = []
    for candidato in list(candidatos or []):
        if candidato.get("mercado") != "proximo_gol":
            continue
        avaliacao = avaliar(candidato)
        if not avaliacao["elegivel"]:
            continue
        item = deepcopy(candidato)
        item.update({
            "regra_versao": VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            "status": "simulacao",
            "bloqueios": [],
            "probabilidade_calibrada": None,
            "probabilidade_observada": None,
        })
        features = item.setdefault("features", {})
        features["proximo_gol_balanceado_sombra"] = {
            **avaliacao,
            "versao": VERSAO,
            "definicao_sha256": definicao_atual["definicao_sha256"],
        }
        features["exploracao_sombra"] = {
            "versao": VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            "fase": "validacao_prospectiva",
            "grupo_teste": True,
            "bloqueios_originais": [MOTIVO_PRESSAO],
            "telegram": "somente_grupo_teste",
            "telegram_oficial": False,
            "aplicacao_automatica": False,
            "promocao_automatica": False,
            "rollback": "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO=0",
        }
        motivos = list(item.get("motivos") or [])
        motivos.extend((
            "challenger_proximo_gol_balanceado_sombra",
            "pressao_50_com_chute_e_dominio_medio_10",
            "qualidade_minima_95",
            "pontuacao_tecnica_minima_60",
            "odd_abaixo_165",
            "enviar_somente_grupo_teste",
        ))
        item["motivos"] = list(dict.fromkeys(motivos))
        novos.append(item)
    return novos
