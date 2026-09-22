"""Challenger prospectivo da V2 Gol FT, sempre em modo sombra."""

import hashlib
import json
import math
import statistics
from copy import deepcopy
from datetime import datetime


VERSAO_CHALLENGER_V2_FT = (
    "exploracao-gol-ft-v2-odd-max165-pressao60-v1"
)
VERSAO_POLITICA_CHALLENGER_V2_FT = (
    "avaliacao-gol-ft-v2-odd-max165-pressao60-v1"
)
ODD_MAXIMA_CHALLENGER_V2_FT = 1.65
PRESSAO_MINIMA_CHALLENGER_V2_FT = 60.0
TAMANHO_COORTE_CHALLENGER_V2_FT = 75
MINIMO_VALIDOS_CHALLENGER_V2_FT = 70
CHAVE_DEFINICAO = f"exploracao_sombra_definicao:{VERSAO_CHALLENGER_V2_FT}"
CHAVE_POLITICA = f"exploracao_sombra_politica:{VERSAO_CHALLENGER_V2_FT}"


def _com_hash(nucleo, campo):
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        campo: hashlib.sha256(serializado.encode("utf-8")).hexdigest(),
    }


def definicao_challenger_v2_ft():
    return _com_hash({
        "versao": VERSAO_CHALLENGER_V2_FT,
        "fase": "validacao_prospectiva",
        "derivada_de": "exploracao-atividade-gol-ft-v2-controle-futuro-v1",
        "mercados": ["gol_ft"],
        "criterios": {
            "odd_maxima_inclusiva": ODD_MAXIMA_CHALLENGER_V2_FT,
            "pico_pressao_5min_minimo": PRESSAO_MINIMA_CHALLENGER_V2_FT,
        },
        "tamanho_coorte_fixa": TAMANHO_COORTE_CHALLENGER_V2_FT,
        "minimo_resultados_validos": MINIMO_VALIDOS_CHALLENGER_V2_FT,
        "evidencia_geradora": {
            "amostra_historica": 128,
            "selecionados_pos_hoc": 48,
            "roi_aproximado": 0.0835,
            "primeiros_75_roi": 0.057,
            "ultimos_53_roi": 0.121,
            "uso": "somente_geracao_de_hipotese",
        },
        "status": "simulacao",
        "telegram": False,
        "telegram_oficial": False,
        "aplicacao_automatica": False,
    }, "definicao_sha256")


def politica_challenger_v2_ft():
    return _com_hash({
        "versao": VERSAO_POLITICA_CHALLENGER_V2_FT,
        "experimento": VERSAO_CHALLENGER_V2_FT,
        "tamanho_coorte_fixa": TAMANHO_COORTE_CHALLENGER_V2_FT,
        "minimo_resultados_validos": MINIMO_VALIDOS_CHALLENGER_V2_FT,
        "confianca": 0.95,
        "metodo_intervalo_roi": "media_normal_bilateral_95",
        "criterios_favoraveis": [
            "coorte_fixa_encerrada",
            "sem_resultados_pendentes",
            "minimo_resultados_validos_atendido",
            "roi_maior_que_zero",
            "lucro_unidades_maior_que_zero",
            "limite_inferior_ic95_roi_maior_que_zero",
        ],
        "promocao_automatica": False,
        "telegram_oficial": False,
    }, "politica_sha256")


def _registrar_ou_validar(conexao, chave, esperado, registrado_em=None):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in esperado.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Challenger V2 Gol FT diverge da ancora imutavel SQLite."
                )
        return existente
    documento = dict(esperado)
    documento["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (chave, json.dumps(documento, ensure_ascii=False, sort_keys=True)),
        )
    return documento


def registrar_ou_validar_challenger_v2_ft(conexao, registrado_em=None):
    definicao = _registrar_ou_validar(
        conexao, CHAVE_DEFINICAO, definicao_challenger_v2_ft(), registrado_em
    )
    politica = _registrar_ou_validar(
        conexao, CHAVE_POLITICA, politica_challenger_v2_ft(), registrado_em
    )
    return {"definicao": definicao, "politica": politica}


def _intervalo_roi_95(retornos):
    if len(retornos) < 2:
        return None
    media = statistics.fmean(retornos)
    erro = statistics.stdev(retornos) / math.sqrt(len(retornos))
    return [round(media - 1.96 * erro, 4), round(media + 1.96 * erro, 4)]


def resumir_challenger_v2_ft(conexao):
    """Resume somente a coorte prospectiva fixa ancorada no SQLite."""
    linha_ancora = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha_ancora is None:
        return {
            "versao": VERSAO_CHALLENGER_V2_FT,
            "estado": "nao_registrado",
            "candidatos_coorte": 0,
            "tamanho_coorte_fixa": TAMANHO_COORTE_CHALLENGER_V2_FT,
            "avaliadas": 0,
            "minimo_resultados_validos": MINIMO_VALIDOS_CHALLENGER_V2_FT,
            "greens": 0, "reds": 0, "pendentes": 0, "invalidos": 0,
            "lucro_unidades": 0.0, "roi": None,
            "intervalo_roi_95": None,
            "faltam_candidatos": TAMANHO_COORTE_CHALLENGER_V2_FT,
            "faltam_validos": MINIMO_VALIDOS_CHALLENGER_V2_FT,
            "decisao_estatistica": "aguardando_registro",
            "telegram": False, "aplicacao_automatica": False,
        }
    try:
        registrado_em = json.loads(linha_ancora["valor"])["registrado_em"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise RuntimeError("Ancora do challenger V2 Gol FT invalida.")

    linhas = conexao.execute(
        """
        WITH candidatos AS (
            SELECT s.id, s.partida_id, s.criado_em,
                   r.resultado, r.retorno_unidades,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.partida_id, s.mercado,
                         json_extract(s.features_json,
                                      '$.exploracao_sombra.versao')
                       ORDER BY datetime(s.criado_em), s.id
                   ) AS ordem_independente
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='simulacao'
              AND s.mercado='gol_ft'
              AND s.criado_em>=?
              AND json_extract(
                    s.features_json, '$.exploracao_sombra.versao'
                  )=?
        )
        SELECT id, resultado, retorno_unidades
        FROM candidatos
        WHERE ordem_independente=1
        ORDER BY datetime(criado_em), id
        LIMIT ?
        """,
        (
            registrado_em,
            VERSAO_CHALLENGER_V2_FT,
            TAMANHO_COORTE_CHALLENGER_V2_FT,
        ),
    ).fetchall()
    validos = [
        linha for linha in linhas
        if linha["resultado"] in ("green", "half_green", "red", "half_red")
        and linha["retorno_unidades"] is not None
    ]
    retornos = [float(linha["retorno_unidades"]) for linha in validos]
    greens = sum(
        linha["resultado"] in ("green", "half_green") for linha in validos
    )
    reds = sum(
        linha["resultado"] in ("red", "half_red") for linha in validos
    )
    pendentes = sum(linha["resultado"] is None for linha in linhas)
    invalidos = len(linhas) - len(validos) - pendentes
    lucro = round(sum(retornos), 4)
    roi = round(lucro / len(validos), 4) if validos else None
    intervalo = _intervalo_roi_95(retornos)
    coorte_fechada = len(linhas) >= TAMANHO_COORTE_CHALLENGER_V2_FT
    if not coorte_fechada:
        decisao = "aguardando_amostra_futura"
    elif pendentes:
        decisao = "aguardando_resultados"
    elif len(validos) < MINIMO_VALIDOS_CHALLENGER_V2_FT:
        decisao = "amostra_valida_insuficiente"
    elif roi is not None and lucro > 0 and roi > 0 and intervalo[0] > 0:
        decisao = "favoravel_para_revisao_independente"
    elif intervalo is not None and intervalo[1] < 0:
        decisao = "evidencia_desfavoravel"
    else:
        decisao = "inconclusiva"
    return {
        "versao": VERSAO_CHALLENGER_V2_FT,
        "registrado_em": registrado_em,
        "estado": "coorte_encerrada" if coorte_fechada else "coletando",
        "candidatos_coorte": len(linhas),
        "tamanho_coorte_fixa": TAMANHO_COORTE_CHALLENGER_V2_FT,
        "avaliadas": len(validos),
        "minimo_resultados_validos": MINIMO_VALIDOS_CHALLENGER_V2_FT,
        "greens": greens, "reds": reds, "pendentes": pendentes,
        "invalidos": invalidos, "lucro_unidades": lucro, "roi": roi,
        "intervalo_roi_95": intervalo,
        "faltam_candidatos": max(
            0, TAMANHO_COORTE_CHALLENGER_V2_FT - len(linhas)
        ),
        "faltam_validos": max(
            0, MINIMO_VALIDOS_CHALLENGER_V2_FT - len(validos)
        ),
        "decisao_estatistica": decisao,
        "telegram": False,
        "aplicacao_automatica": False,
    }


def _numero(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero == numero else None


def criar_challenger_v2_ft(controle_v2):
    """Filtra uma cópia V2 já validada; nunca altera o braço de controle."""
    if controle_v2 is None or controle_v2.get("status") != "simulacao":
        return None
    features = controle_v2.get("features") or {}
    sombra = features.get("exploracao_sombra") or {}
    if sombra.get("versao") != (
        "exploracao-atividade-gol-ft-v2-controle-futuro-v1"
    ):
        return None
    odd = _numero(controle_v2.get("odd"))
    janela5 = (features.get("janelas") or {}).get("5") or {}
    picos = janela5.get("pressao_pico") or []
    if not isinstance(picos, (list, tuple)):
        picos = [picos]
    picos_validos = [_numero(item) for item in picos]
    picos_validos = [item for item in picos_validos if item is not None]
    pico = max(picos_validos) if picos_validos else None
    if (
        odd is None
        or odd > ODD_MAXIMA_CHALLENGER_V2_FT
        or pico is None
        or pico < PRESSAO_MINIMA_CHALLENGER_V2_FT
    ):
        return None

    challenger = deepcopy(controle_v2)
    challenger["motivos"] = list(challenger.get("motivos") or []) + [
        f"exploracao_sombra={VERSAO_CHALLENGER_V2_FT}",
        f"challenger_odd_maxima={ODD_MAXIMA_CHALLENGER_V2_FT:g}",
        f"challenger_pressao_minima={PRESSAO_MINIMA_CHALLENGER_V2_FT:g}",
        "nao_enviar_telegram",
    ]
    challenger["features"] = {
        **features,
        "exploracao_sombra": {
            **sombra,
            "versao": VERSAO_CHALLENGER_V2_FT,
            "derivada_de": sombra.get("versao"),
            "tamanho_coorte_fixa": TAMANHO_COORTE_CHALLENGER_V2_FT,
            "minimo_resultados_validacao": MINIMO_VALIDOS_CHALLENGER_V2_FT,
            "criterio_selecao": {
                "odd_maxima_inclusiva": ODD_MAXIMA_CHALLENGER_V2_FT,
                "odd_observada": odd,
                "pico_pressao_5min_minimo": PRESSAO_MINIMA_CHALLENGER_V2_FT,
                "pico_pressao_5min_observado": pico,
            },
            "telegram_oficial": False,
            "aplicacao_automatica": False,
        },
    }
    return challenger
