"""Exploração prospectiva restrita, sem envio e sem contaminar calibração."""

import json
import hashlib
import math
import statistics
from copy import deepcopy
from datetime import datetime, timedelta

from configuracao import odd_elegivel, obter_limites_risco
from challenger_v2_ft import criar_challenger_v2_ft


VERSAO_EXPLORACAO_DESENVOLVIMENTO = "exploracao-atividade-gols-v1"
VERSAO_EXPLORACAO_SOMBRA = (
    "exploracao-atividade-gols-validacao-v2"
)
VERSAO_EXPLORACAO_GOL_FT_V3 = (
    "exploracao-atividade-gol-ft-chutes5-min1-validacao-v3"
)
VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE = (
    "exploracao-atividade-gol-ft-v2-controle-futuro-v1"
)
FASE_EXPLORACAO_GOLS = "validacao_prospectiva"
MINIMO_VALIDACAO_EXPLORACAO_GOLS = 30
VERSAO_POLITICA_AVALIACAO_GOLS = "avaliacao-exploracao-gols-v1"
VERSAO_POLITICA_AVALIACAO_GOL_FT_V3 = (
    "avaliacao-exploracao-gol-ft-chutes5-v3"
)
VERSAO_POLITICA_AVALIACAO_GOL_FT_V2_CONTROLE = (
    "avaliacao-exploracao-gol-ft-v2-controle-futuro-v1"
)
TAMANHO_COORTE_VALIDACAO_GOL_FT_V3 = 75
MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3 = 70
TAMANHO_COORTE_GOL_FT_V2_CONTROLE = 75
MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE = 70
REGRA_VERSAO_GOL_FT_V3 = "sinais-v6"
REGRA_FINGERPRINT_GOL_FT_V3 = (
    "92b66ba3ecd8faa8f087649a6a545601ed8be83933a132c3b7c9bc4cd87ccb81"
)
FEATURE_CHUTES_5MIN_GOL_FT_V3 = "janelas.5.chutes_total"
LIMIAR_CHUTES_5MIN_GOL_FT_V3 = 1.0
CONFIANCA_AVALIACAO_GOLS = 0.95
VERSAO_EXPLORACAO_ASIATICA = "exploracao-asiatico-ft-multiplos-v2"
MERCADOS = frozenset({"gol_ft", "gol_ht"})
BLOQUEIOS_RELAXAVEIS = frozenset({
    "atividade_recente_insuficiente_gols",
})
PONTUACAO_MINIMA = 65.0
QUALIDADE_MINIMA = 80.0
IDADE_ODD_MAXIMA_SEGUNDOS = 360.0
IDADE_ODD_ENVIO_ASIATICA_SEGUNDOS = 60.0
PONTUACAO_MINIMA_ASIATICA = 75.0
QUALIDADE_MINIMA_ASIATICA = 85.0
MINUTO_MINIMO_ASIATICA = 20.0
MINUTO_MAXIMO_ASIATICA = 70.0
GAP_MAXIMO_ASIATICA = 3.5
CHAVE_DEFINICAO_PREFIXO = "exploracao_sombra_definicao:"
CHAVE_POLITICA_AVALIACAO_PREFIXO = "exploracao_sombra_politica:"
GATILHOS_DEFINICAO = frozenset({
    "trg_exploracao_sombra_definicao_update_imutavel",
    "trg_exploracao_sombra_definicao_delete_imutavel",
})
GATILHOS_POLITICA_AVALIACAO = frozenset({
    "trg_exploracao_sombra_politica_update_imutavel",
    "trg_exploracao_sombra_politica_delete_imutavel",
})


def _politica_avaliacao_exploracao_gol_ft_v3():
    """Politica pre-registrada da confirmacao independente da V3."""
    nucleo = {
        "versao": VERSAO_POLITICA_AVALIACAO_GOL_FT_V3,
        "experimento": VERSAO_EXPLORACAO_GOL_FT_V3,
        "mercados": ["gol_ft"],
        "tamanho_coorte_fixa": TAMANHO_COORTE_VALIDACAO_GOL_FT_V3,
        "minimo_resultados_validos": MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3,
        "maximo_resultados_invalidos": (
            TAMANHO_COORTE_VALIDACAO_GOL_FT_V3
            - MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3
        ),
        "confianca": CONFIANCA_AVALIACAO_GOLS,
        "metodo_intervalo_roi": "media_normal_bilateral_95",
        "criterio_selecao": {
            "feature": FEATURE_CHUTES_5MIN_GOL_FT_V3,
            "operador": "maior_igual",
            "limiar": LIMIAR_CHUTES_5MIN_GOL_FT_V3,
        },
        "linhagem_esperada": {
            "regra_versao": REGRA_VERSAO_GOL_FT_V3,
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
        },
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
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "politica_sha256": hashlib.sha256(
            serializado.encode("utf-8")
        ).hexdigest(),
    }


def _definicao_exploracao_gol_ft_v3():
    nucleo = {
        "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
        "fase": FASE_EXPLORACAO_GOLS,
        "derivada_de": VERSAO_EXPLORACAO_SOMBRA,
        "mercados": ["gol_ft"],
        "bloqueios_relaxaveis": sorted(BLOQUEIOS_RELAXAVEIS),
        "pontuacao_minima": PONTUACAO_MINIMA,
        "qualidade_minima": QUALIDADE_MINIMA,
        "idade_odd_maxima_segundos": IDADE_ODD_MAXIMA_SEGUNDOS,
        "tamanho_coorte_fixa": TAMANHO_COORTE_VALIDACAO_GOL_FT_V3,
        "minimo_resultados_validos": MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3,
        "criterio_selecao": {
            "feature": FEATURE_CHUTES_5MIN_GOL_FT_V3,
            "operador": "maior_igual",
            "limiar": LIMIAR_CHUTES_5MIN_GOL_FT_V3,
        },
        "linhagem_esperada": {
            "regra_versao": REGRA_VERSAO_GOL_FT_V3,
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
        },
        "evidencia_geradora": {
            "experimento": VERSAO_EXPLORACAO_SOMBRA,
            "coorte": 30,
            "selecionados_pos_hoc": 17,
            "greens": 14,
            "reds": 3,
            "roi": 0.3829,
            "uso": "somente_geracao_de_hipotese",
        },
        "status": "simulacao",
        "telegram": False,
        "aplicacao_automatica": False,
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            serializado.encode("utf-8")
        ).hexdigest(),
    }


def _politica_avaliacao_gol_ft_v2_controle():
    """Politica pre-registrada do controle futuro fiel a V2."""
    nucleo = {
        "versao": VERSAO_POLITICA_AVALIACAO_GOL_FT_V2_CONTROLE,
        "experimento": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
        "comparado_com": VERSAO_EXPLORACAO_GOL_FT_V3,
        "mercados": ["gol_ft"],
        "tamanho_coorte_fixa": TAMANHO_COORTE_GOL_FT_V2_CONTROLE,
        "minimo_resultados_validos": (
            MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE
        ),
        "maximo_resultados_invalidos": (
            TAMANHO_COORTE_GOL_FT_V2_CONTROLE
            - MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE
        ),
        "confianca": CONFIANCA_AVALIACAO_GOLS,
        "metodo_intervalo_roi": "media_normal_bilateral_95",
        "criterio_selecao": {
            "bloqueios_exatos": sorted(BLOQUEIOS_RELAXAVEIS),
            "pontuacao_minima": PONTUACAO_MINIMA,
            "qualidade_minima": QUALIDADE_MINIMA,
            "idade_odd_maxima_segundos": IDADE_ODD_MAXIMA_SEGUNDOS,
            "filtro_atividade_adicional": False,
        },
        "linhagem_esperada": {
            "regra_versao": REGRA_VERSAO_GOL_FT_V3,
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
        },
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
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "politica_sha256": hashlib.sha256(
            serializado.encode("utf-8")
        ).hexdigest(),
    }


def _definicao_exploracao_gol_ft_v2_controle():
    """Definicao futura; nao reabre nem altera a coorte V2 historica."""
    nucleo = {
        "versao": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
        "fase": FASE_EXPLORACAO_GOLS,
        "reproducao_fiel_de": VERSAO_EXPLORACAO_SOMBRA,
        "comparado_com": VERSAO_EXPLORACAO_GOL_FT_V3,
        "mercados": ["gol_ft"],
        "bloqueios_relaxaveis": sorted(BLOQUEIOS_RELAXAVEIS),
        "pontuacao_minima": PONTUACAO_MINIMA,
        "qualidade_minima": QUALIDADE_MINIMA,
        "idade_odd_maxima_segundos": IDADE_ODD_MAXIMA_SEGUNDOS,
        "tamanho_coorte_fixa": TAMANHO_COORTE_GOL_FT_V2_CONTROLE,
        "minimo_resultados_validos": (
            MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE
        ),
        "criterio_selecao": {
            "bloqueios_exatos": sorted(BLOQUEIOS_RELAXAVEIS),
            "filtro_atividade_adicional": False,
        },
        "linhagem_esperada": {
            "regra_versao": REGRA_VERSAO_GOL_FT_V3,
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
        },
        "historico_v2_reaberto": False,
        "status": "simulacao",
        "telegram": False,
        "aplicacao_automatica": False,
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            serializado.encode("utf-8")
        ).hexdigest(),
    }


def _politica_avaliacao_exploracao_gols():
    """Critérios congelados antes do primeiro resultado futuro da V2."""
    nucleo = {
        "versao": VERSAO_POLITICA_AVALIACAO_GOLS,
        "experimento": VERSAO_EXPLORACAO_SOMBRA,
        "mercados": sorted(MERCADOS),
        "minimo_resultados_por_mercado": (
            MINIMO_VALIDACAO_EXPLORACAO_GOLS
        ),
        "confianca": CONFIANCA_AVALIACAO_GOLS,
        "metodo_intervalo_roi": "media_normal_bilateral_95",
        "criterios_favoraveis": [
            "roi_maior_que_zero",
            "lucro_unidades_maior_que_zero",
            "limite_inferior_ic95_roi_maior_que_zero",
        ],
        "estados": [
            "aguardando_amostra_futura",
            "favoravel_para_revisao_independente",
            "inconclusiva",
            "evidencia_desfavoravel",
        ],
        "promocao_automatica": False,
        "telegram_oficial": False,
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "politica_sha256": hashlib.sha256(
            serializado.encode("utf-8")
        ).hexdigest(),
    }


def registrar_ou_validar_politica_avaliacao_gols(
    conexao, registrado_em=None
):
    politica = _politica_avaliacao_exploracao_gols()
    chave = (
        f"{CHAVE_POLITICA_AVALIACAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_SOMBRA}"
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in politica.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Politica de avaliacao da exploracao de gols diverge "
                    "da ancora SQLite."
                )
        return existente
    politica["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                chave,
                json.dumps(politica, ensure_ascii=False, sort_keys=True),
            ),
        )
    return politica


def _definicao_exploracao_gols():
    nucleo = {
        "versao": VERSAO_EXPLORACAO_SOMBRA,
        "fase": FASE_EXPLORACAO_GOLS,
        "versao_desenvolvimento": VERSAO_EXPLORACAO_DESENVOLVIMENTO,
        "mercados": sorted(MERCADOS),
        "bloqueios_relaxaveis": sorted(BLOQUEIOS_RELAXAVEIS),
        "pontuacao_minima": PONTUACAO_MINIMA,
        "qualidade_minima": QUALIDADE_MINIMA,
        "idade_odd_maxima_segundos": IDADE_ODD_MAXIMA_SEGUNDOS,
        "minimo_resultados_por_mercado": (
            MINIMO_VALIDACAO_EXPLORACAO_GOLS
        ),
        "status": "simulacao",
        "telegram": False,
        "aplicacao_automatica": False,
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            serializado.encode("utf-8")
        ).hexdigest(),
    }


def registrar_ou_validar_definicao_exploracao_gols(
    conexao, registrado_em=None
):
    definicao = _definicao_exploracao_gols()
    chave = f"{CHAVE_DEFINICAO_PREFIXO}{VERSAO_EXPLORACAO_SOMBRA}"
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in definicao.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Definicao da exploracao de gols diverge da ancora SQLite."
                )
        return existente
    definicao["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                chave,
                json.dumps(
                    definicao, ensure_ascii=False, sort_keys=True
                ),
            ),
        )
    return definicao


def registrar_ou_validar_definicao_exploracao_gol_ft_v3(
    conexao, registrado_em=None
):
    definicao = _definicao_exploracao_gol_ft_v3()
    chave = (
        f"{CHAVE_DEFINICAO_PREFIXO}{VERSAO_EXPLORACAO_GOL_FT_V3}"
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in definicao.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Definicao da exploracao Gol FT V3 diverge da ancora "
                    "SQLite."
                )
        return existente
    definicao["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                chave,
                json.dumps(definicao, ensure_ascii=False, sort_keys=True),
            ),
        )
    return definicao


def registrar_ou_validar_politica_avaliacao_gol_ft_v3(
    conexao, registrado_em=None
):
    politica = _politica_avaliacao_exploracao_gol_ft_v3()
    chave = (
        f"{CHAVE_POLITICA_AVALIACAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_GOL_FT_V3}"
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in politica.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Politica da exploracao Gol FT V3 diverge da ancora "
                    "SQLite."
                )
        return existente
    politica["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                chave,
                json.dumps(politica, ensure_ascii=False, sort_keys=True),
            ),
        )
    return politica


def registrar_ou_validar_definicao_gol_ft_v2_controle(
    conexao, registrado_em=None
):
    definicao = _definicao_exploracao_gol_ft_v2_controle()
    chave = (
        f"{CHAVE_DEFINICAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}"
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in definicao.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Definicao do controle futuro Gol FT V2 diverge da "
                    "ancora SQLite."
                )
        return existente
    definicao["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                chave,
                json.dumps(definicao, ensure_ascii=False, sort_keys=True),
            ),
        )
    return definicao


def registrar_ou_validar_politica_gol_ft_v2_controle(
    conexao, registrado_em=None
):
    politica = _politica_avaliacao_gol_ft_v2_controle()
    chave = (
        f"{CHAVE_POLITICA_AVALIACAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}"
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in politica.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Politica do controle futuro Gol FT V2 diverge da "
                    "ancora SQLite."
                )
        return existente
    politica["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                chave,
                json.dumps(politica, ensure_ascii=False, sort_keys=True),
            ),
        )
    return politica


def auditar_definicao_exploracao_gol_ft_v3(conexao):
    gatilhos = {
        linha[0] for linha in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    gatilhos_ausentes = sorted(
        (GATILHOS_DEFINICAO | GATILHOS_POLITICA_AVALIACAO) - gatilhos
    )
    definicao_chave = (
        f"{CHAVE_DEFINICAO_PREFIXO}{VERSAO_EXPLORACAO_GOL_FT_V3}"
    )
    politica_chave = (
        f"{CHAVE_POLITICA_AVALIACAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_GOL_FT_V3}"
    )
    definicao_linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (definicao_chave,)
    ).fetchone()
    politica_linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (politica_chave,)
    ).fetchone()
    motivo = None
    registrado_em = None
    ainda_nao_iniciada = (
        definicao_linha is None and politica_linha is None
    )
    try:
        # O preflight roda antes de o ServicoMonitor registrar uma nova
        # experiencia. A ausencia simultanea das duas ancoras representa
        # apenas "ainda nao iniciada"; somente uma ancora ausente e outra
        # presente e inconsistencia real.
        if ainda_nao_iniciada:
            pass
        elif definicao_linha is None:
            motivo = "definicao_exploracao_gol_ft_v3_ausente"
        else:
            existente = json.loads(definicao_linha["valor"])
            registrado_em = existente.get("registrado_em")
            datetime.fromisoformat(registrado_em)
            if any(
                existente.get(campo) != valor
                for campo, valor in _definicao_exploracao_gol_ft_v3().items()
            ):
                motivo = "definicao_exploracao_gol_ft_v3_divergente"
        if ainda_nao_iniciada:
            pass
        elif politica_linha is None:
            motivo = "politica_exploracao_gol_ft_v3_ausente"
        else:
            existente = json.loads(politica_linha["valor"])
            datetime.fromisoformat(existente.get("registrado_em"))
            if any(
                existente.get(campo) != valor
                for campo, valor in (
                    _politica_avaliacao_exploracao_gol_ft_v3().items()
                )
            ):
                motivo = "politica_exploracao_gol_ft_v3_divergente"
    except (TypeError, ValueError, json.JSONDecodeError):
        motivo = "exploracao_gol_ft_v3_invalida"
    if gatilhos_ausentes:
        motivo = "protecao_exploracao_gol_ft_v3_ausente"
    return {
        "saudavel": motivo is None,
        "estado": (
            "nao_registrada"
            if motivo is None and ainda_nao_iniciada
            else "valida" if motivo is None
            else "inconsistente"
        ),
        "motivo": motivo,
        "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
        "registrada": definicao_linha is not None,
        "registrado_em": registrado_em,
        "definicao_sha256": _definicao_exploracao_gol_ft_v3()[
            "definicao_sha256"
        ],
        "politica_sha256": _politica_avaliacao_exploracao_gol_ft_v3()[
            "politica_sha256"
        ],
        "gatilhos_ausentes": gatilhos_ausentes,
        "protegida": not gatilhos_ausentes,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
    }


def auditar_definicao_gol_ft_v2_controle(conexao):
    gatilhos = {
        linha[0] for linha in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    gatilhos_ausentes = sorted(
        (GATILHOS_DEFINICAO | GATILHOS_POLITICA_AVALIACAO) - gatilhos
    )
    definicao_chave = (
        f"{CHAVE_DEFINICAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}"
    )
    politica_chave = (
        f"{CHAVE_POLITICA_AVALIACAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}"
    )
    definicao_linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (definicao_chave,)
    ).fetchone()
    politica_linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (politica_chave,)
    ).fetchone()
    ainda_nao_iniciada = (
        definicao_linha is None and politica_linha is None
    )
    motivo = None
    registrado_em = None
    try:
        if ainda_nao_iniciada:
            pass
        elif definicao_linha is None:
            motivo = "definicao_gol_ft_v2_controle_ausente"
        else:
            existente = json.loads(definicao_linha["valor"])
            registrado_em = existente.get("registrado_em")
            datetime.fromisoformat(registrado_em)
            if any(
                existente.get(campo) != valor
                for campo, valor in (
                    _definicao_exploracao_gol_ft_v2_controle().items()
                )
            ):
                motivo = "definicao_gol_ft_v2_controle_divergente"
        if ainda_nao_iniciada:
            pass
        elif politica_linha is None:
            motivo = "politica_gol_ft_v2_controle_ausente"
        else:
            existente = json.loads(politica_linha["valor"])
            datetime.fromisoformat(existente.get("registrado_em"))
            if any(
                existente.get(campo) != valor
                for campo, valor in (
                    _politica_avaliacao_gol_ft_v2_controle().items()
                )
            ):
                motivo = "politica_gol_ft_v2_controle_divergente"
    except (TypeError, ValueError, json.JSONDecodeError):
        motivo = "gol_ft_v2_controle_invalido"
    if gatilhos_ausentes:
        motivo = "protecao_gol_ft_v2_controle_ausente"
    return {
        "saudavel": motivo is None,
        "estado": (
            "nao_registrada"
            if motivo is None and ainda_nao_iniciada
            else "valida" if motivo is None
            else "inconsistente"
        ),
        "motivo": motivo,
        "versao": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
        "registrada": definicao_linha is not None,
        "registrado_em": registrado_em,
        "definicao_sha256": _definicao_exploracao_gol_ft_v2_controle()[
            "definicao_sha256"
        ],
        "politica_sha256": _politica_avaliacao_gol_ft_v2_controle()[
            "politica_sha256"
        ],
        "gatilhos_ausentes": gatilhos_ausentes,
        "protegida": not gatilhos_ausentes,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
    }


def auditar_definicao_exploracao_gols(conexao):
    gatilhos = {
        linha[0] for linha in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    ausentes_definicao = sorted(GATILHOS_DEFINICAO - gatilhos)
    ausentes_politica = sorted(
        GATILHOS_POLITICA_AVALIACAO - gatilhos
    )
    chave = f"{CHAVE_DEFINICAO_PREFIXO}{VERSAO_EXPLORACAO_SOMBRA}"
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    motivo = None
    registrada = linha is not None
    registrado_em = None
    try:
        if linha is None:
            # Um banco novo ainda pode não ter iniciado o experimento. Os
            # gatilhos devem existir desde o esquema; o ServicoMonitor grava
            # a ancora antes da primeira coleta.
            motivo = None
        else:
            existente = json.loads(linha["valor"])
            registrado_em = existente.get("registrado_em")
            datetime.fromisoformat(registrado_em)
            if any(
                existente.get(campo) != valor
                for campo, valor in _definicao_exploracao_gols().items()
            ):
                motivo = "definicao_exploracao_gols_divergente"
    except (TypeError, ValueError, json.JSONDecodeError):
        motivo = "definicao_exploracao_gols_invalida"
    if ausentes_definicao:
        motivo = "protecao_exploracao_gols_ausente"
    chave_politica = (
        f"{CHAVE_POLITICA_AVALIACAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_SOMBRA}"
    )
    linha_politica = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave_politica,)
    ).fetchone()
    politica_registrada = linha_politica is not None
    politica_registrado_em = None
    try:
        if linha_politica is not None:
            politica_existente = json.loads(linha_politica["valor"])
            politica_registrado_em = politica_existente.get(
                "registrado_em"
            )
            datetime.fromisoformat(politica_registrado_em)
            if any(
                politica_existente.get(campo) != valor
                for campo, valor in (
                    _politica_avaliacao_exploracao_gols().items()
                )
            ):
                motivo = "politica_avaliacao_gols_divergente"
        elif registrada:
            motivo = "politica_avaliacao_gols_ausente"
    except (TypeError, ValueError, json.JSONDecodeError):
        motivo = "politica_avaliacao_gols_invalida"
    if ausentes_politica:
        motivo = "protecao_politica_avaliacao_gols_ausente"
    auditoria_v3 = auditar_definicao_exploracao_gol_ft_v3(conexao)
    if registrada and not auditoria_v3["saudavel"]:
        motivo = auditoria_v3["motivo"]
    auditoria_v2_controle = auditar_definicao_gol_ft_v2_controle(
        conexao
    )
    if registrada and not auditoria_v2_controle["saudavel"]:
        motivo = auditoria_v2_controle["motivo"]
    return {
        "saudavel": motivo is None,
        "estado": (
            "valida" if motivo is None and registrada
            else "nao_registrada" if motivo is None
            else "inconsistente"
        ),
        "motivo": motivo,
        "versao": VERSAO_EXPLORACAO_SOMBRA,
        "registrada": registrada,
        "registrado_em": registrado_em,
        "definicao_sha256": _definicao_exploracao_gols()[
            "definicao_sha256"
        ],
        "gatilhos_ausentes": (
            ausentes_definicao + ausentes_politica
        ),
        "protegida": not (
            ausentes_definicao or ausentes_politica
        ),
        "politica_avaliacao": {
            "versao": VERSAO_POLITICA_AVALIACAO_GOLS,
            "registrada": politica_registrada,
            "registrado_em": politica_registrado_em,
            "politica_sha256": (
                _politica_avaliacao_exploracao_gols()[
                    "politica_sha256"
                ]
            ),
            "protegida": not ausentes_politica,
            "promocao_automatica": False,
        },
        "exploracao_gol_ft_v3": auditoria_v3,
        "gol_ft_v2_controle": auditoria_v2_controle,
        "aplicacao_automatica": False,
    }


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _intervalo_media_roi_95(retornos):
    valores = [float(valor) for valor in retornos]
    if len(valores) < 2:
        return None
    media = statistics.mean(valores)
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    margem = 1.96 * erro
    return [round(media - margem, 4), round(media + margem, 4)]


def _avaliar_retornos_validacao_gols(
    retornos, minimo_resultados=MINIMO_VALIDACAO_EXPLORACAO_GOLS
):
    valores = [float(valor) for valor in retornos]
    avaliadas = len(valores)
    lucro = round(sum(valores), 4)
    roi = round(lucro / avaliadas, 4) if avaliadas else None
    intervalo = _intervalo_media_roi_95(valores)
    if avaliadas < int(minimo_resultados):
        decisao = "aguardando_amostra_futura"
    elif (
        roi is not None
        and roi > 0
        and lucro > 0
        and intervalo is not None
        and intervalo[0] > 0
    ):
        decisao = "favoravel_para_revisao_independente"
    elif intervalo is not None and intervalo[1] < 0:
        decisao = "evidencia_desfavoravel"
    else:
        decisao = "inconclusiva"
    return {
        "avaliadas": avaliadas,
        "lucro_unidades": lucro,
        "roi": roi,
        "intervalo_roi_95": intervalo,
        "decisao_estatistica": decisao,
    }


def _extrair_contexto_comparacao_gol_ft(features):
    features = features or {}
    janela_5 = (features.get("janelas") or {}).get("5") or {}
    picos = janela_5.get("pressao_pico") or []
    picos_validos = [
        _numero(valor) for valor in picos if _numero(valor) is not None
    ]
    return {
        "minuto": _numero(features.get("minuto")),
        "qualidade_dados": _numero(features.get("qualidade_dados")),
        "idade_odds_segundos": _numero(
            features.get("idade_odds_segundos")
        ),
        "chutes_5min": _numero(janela_5.get("chutes_total")),
        "pico_pressao_5min": max(picos_validos) if picos_validos else None,
        "gols_atuais": _numero(features.get("gols_atuais")),
    }


def _resumir_subgrupo_comparacao_gol_ft(itens):
    resolvidos = [
        item for item in itens
        if item.get("resultado") in (
            "green", "half_green", "red", "half_red"
        )
        and item.get("retorno_unidades") is not None
    ]
    retornos = [float(item["retorno_unidades"]) for item in resolvidos]
    avaliacao = _avaliar_retornos_validacao_gols(
        retornos, minimo_resultados=30
    )
    resumo_contexto = {}
    for campo in (
        "odd", "minuto", "qualidade_dados", "idade_odds_segundos",
        "chutes_5min", "pico_pressao_5min", "gols_atuais",
    ):
        valores = [
            _numero(item.get(campo)) for item in resolvidos
            if _numero(item.get(campo)) is not None
        ]
        resumo_contexto[campo] = {
            "cobertura": len(valores),
            "mediana": round(statistics.median(valores), 4)
            if valores else None,
        }
    return {
        "candidatos": len(itens),
        "avaliadas": len(resolvidos),
        "greens": sum(
            item["resultado"] in ("green", "half_green")
            for item in resolvidos
        ),
        "reds": sum(
            item["resultado"] in ("red", "half_red")
            for item in resolvidos
        ),
        "roi": avaliacao["roi"],
        "lucro_unidades": avaliacao["lucro_unidades"],
        "intervalo_roi_95": avaliacao["intervalo_roi_95"],
        "decisao_estatistica": avaliacao["decisao_estatistica"],
        "contexto_mediano": resumo_contexto,
    }


def _comparar_subgrupos_independentes(esquerdo, direito):
    retornos_esquerdo = [
        float(item["retorno_unidades"]) for item in esquerdo
        if item.get("retorno_unidades") is not None
    ]
    retornos_direito = [
        float(item["retorno_unidades"]) for item in direito
        if item.get("retorno_unidades") is not None
    ]
    if len(retornos_esquerdo) < 2 or len(retornos_direito) < 2:
        return {
            "delta_roi_v2_menos_v3": None,
            "intervalo_delta_95": None,
            "decisao": "amostra_insuficiente",
        }
    media_esquerdo = statistics.mean(retornos_esquerdo)
    media_direito = statistics.mean(retornos_direito)
    delta = media_esquerdo - media_direito
    erro = math.sqrt(
        statistics.variance(retornos_esquerdo) / len(retornos_esquerdo)
        + statistics.variance(retornos_direito) / len(retornos_direito)
    )
    intervalo = [delta - 1.96 * erro, delta + 1.96 * erro]
    if intervalo[0] > 0:
        decisao = "v2_exclusivo_superior"
    elif intervalo[1] < 0:
        decisao = "v3_exclusivo_superior"
    else:
        decisao = "diferenca_inconclusiva"
    return {
        "delta_roi_v2_menos_v3": round(delta, 4),
        "intervalo_delta_95": [round(valor, 4) for valor in intervalo],
        "decisao": decisao,
    }


def _resumir_coorte_fixa_gol_ft(
    coorte,
    tamanho_coorte,
    minimo_validos,
    regra_versao_esperada,
    regra_fingerprint_esperado,
):
    resolvidos = [
        item for item in coorte
        if item["resultado"] in (
            "green", "half_green", "red", "half_red"
        )
        and item["retorno_unidades"] is not None
    ]
    retornos = [
        float(item["retorno_unidades"]) for item in resolvidos
    ]
    avaliadas = len(resolvidos)
    greens = sum(
        item["resultado"] in ("green", "half_green")
        for item in resolvidos
    )
    reds = sum(
        item["resultado"] in ("red", "half_red")
        for item in resolvidos
    )
    pendentes = sum(item["resultado"] is None for item in coorte)
    invalidos = len(coorte) - avaliadas - pendentes
    coorte_fechada = len(coorte) >= int(tamanho_coorte)
    linhagens = sorted({
        (
            str(item["regra_versao"] or ""),
            str(item["regra_fingerprint"] or ""),
        )
        for item in coorte
    })
    linhagem_homogenea = len(linhagens) <= 1
    linhagem_compativel = all(
        regra_versao == regra_versao_esperada
        and regra_fingerprint == regra_fingerprint_esperado
        for regra_versao, regra_fingerprint in linhagens
    )
    avaliacao = _avaliar_retornos_validacao_gols(
        retornos, minimo_resultados=minimo_validos
    )
    if not (linhagem_homogenea and linhagem_compativel):
        estado = "inconsistente"
        decisao = "linhagem_inconsistente"
    elif not coorte_fechada:
        estado = "aguardando_coorte_futura"
        decisao = "aguardando_coorte_futura"
    elif pendentes:
        estado = "aguardando_resultados"
        decisao = "aguardando_resultados"
    elif avaliadas < int(minimo_validos):
        estado = "inconclusiva"
        decisao = "amostra_valida_insuficiente"
    else:
        estado = "pronta_para_revisao_independente"
        decisao = avaliacao["decisao_estatistica"]
    fingerprint = hashlib.sha256(json.dumps(
        [
            [
                item["sinal_id"], item["partida_id"],
                item["regra_versao"], item["regra_fingerprint"],
            ]
            for item in coorte
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "candidatos_coorte": len(coorte),
        "faltam_candidatos": max(0, int(tamanho_coorte) - len(coorte)),
        "avaliadas": avaliadas,
        "faltam_resultados_validos": max(
            0, int(minimo_validos) - avaliadas
        ),
        "greens": greens,
        "reds": reds,
        "pendentes": pendentes,
        "invalidos": invalidos,
        "taxa_acerto": (
            round(greens / avaliadas, 4) if avaliadas else None
        ),
        "lucro_unidades": avaliacao["lucro_unidades"],
        "roi": avaliacao["roi"],
        "intervalo_roi_95": avaliacao["intervalo_roi_95"],
        "estado": estado,
        "decisao_estatistica": decisao,
        "coorte_fechada": coorte_fechada,
        "validacao_congelada": coorte_fechada,
        "resultados_completos": coorte_fechada and pendentes == 0,
        "validacao_fingerprint": fingerprint,
        "linhagem_homogenea": linhagem_homogenea,
        "linhagem_compativel": linhagem_compativel,
        "linhagens_coorte": [
            {
                "regra_versao": regra_versao,
                "regra_fingerprint": regra_fingerprint,
            }
            for regra_versao, regra_fingerprint in linhagens
        ],
    }


def criar_exploracao_sombra(candidato, regra_fingerprints=None):
    """Cria uma cópia liquidável somente quando um único gate é relaxado."""
    if candidato.get("mercado") not in MERCADOS:
        return None
    if candidato.get("status") != "rejeitado":
        return None
    bloqueios = set(candidato.get("bloqueios") or [])
    if not bloqueios or not bloqueios <= BLOQUEIOS_RELAXAVEIS:
        return None
    pontuacao = _numero(candidato.get("pontuacao_tecnica"))
    qualidade = _numero(candidato.get("qualidade_dados"))
    odd = _numero(candidato.get("odd"))
    idade_odd = _numero(candidato.get("idade_odds_segundos"))
    if (
        pontuacao is None
        or pontuacao < PONTUACAO_MINIMA
        or qualidade is None
        or qualidade < QUALIDADE_MINIMA
        or odd is None
        or (idade_odd is not None and idade_odd > IDADE_ODD_MAXIMA_SEGUNDOS)
    ):
        return None

    mercado = candidato.get("mercado")
    if mercado == "gol_ft":
        features = candidato.get("features") or {}
        janela5 = (features.get("janelas") or {}).get("5") or {}
        chutes5 = _numero(janela5.get("chutes_total"))
        regra_versao = candidato.get("regra_versao")
        regra_fingerprint = (
            candidato.get("regra_fingerprint")
            or (regra_fingerprints or {}).get(regra_versao)
        )
        if (
            chutes5 is None
            or chutes5 < LIMIAR_CHUTES_5MIN_GOL_FT_V3
            or regra_versao != REGRA_VERSAO_GOL_FT_V3
            or regra_fingerprint != REGRA_FINGERPRINT_GOL_FT_V3
        ):
            return None
        versao_exploracao = VERSAO_EXPLORACAO_GOL_FT_V3
        minimo_resultados = MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3
        detalhes_especificos = {
            "derivada_de": VERSAO_EXPLORACAO_SOMBRA,
            "tamanho_coorte_fixa": (
                TAMANHO_COORTE_VALIDACAO_GOL_FT_V3
            ),
            "minimo_resultados_validos": (
                MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3
            ),
            "criterio_selecao": {
                "feature": FEATURE_CHUTES_5MIN_GOL_FT_V3,
                "operador": "maior_igual",
                "limiar": LIMIAR_CHUTES_5MIN_GOL_FT_V3,
                "valor_observado": chutes5,
            },
            "linhagem_esperada": {
                "regra_versao": REGRA_VERSAO_GOL_FT_V3,
                "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
            },
            "telegram_oficial": False,
        }
    else:
        versao_exploracao = VERSAO_EXPLORACAO_SOMBRA
        minimo_resultados = MINIMO_VALIDACAO_EXPLORACAO_GOLS
        detalhes_especificos = {
            "versao_desenvolvimento": (
                VERSAO_EXPLORACAO_DESENVOLVIMENTO
            ),
        }

    exploracao = deepcopy(candidato)
    exploracao["status"] = "simulacao"
    exploracao["bloqueios"] = []
    exploracao["motivos"] = list(exploracao.get("motivos") or []) + [
        f"exploracao_sombra={versao_exploracao}",
        "relaxamento_exclusivo=atividade_recente_insuficiente_gols",
        "nao_enviar_telegram",
    ]
    exploracao["features"] = {
        **(exploracao.get("features") or {}),
        "exploracao_sombra": {
            "versao": versao_exploracao,
            "fase": FASE_EXPLORACAO_GOLS,
            "minimo_resultados_validacao": minimo_resultados,
            "bloqueios_originais": sorted(bloqueios),
            "pontuacao_minima": PONTUACAO_MINIMA,
            "qualidade_minima": QUALIDADE_MINIMA,
            "aplicacao_automatica": False,
            **detalhes_especificos,
        },
    }
    return exploracao


def criar_exploracao_gol_ft_v2_controle(
    candidato, regra_fingerprints=None
):
    """Reproduz a V2 em dados futuros, sem o filtro adicional da V3."""
    if candidato.get("mercado") != "gol_ft":
        return None
    if candidato.get("status") != "rejeitado":
        return None
    bloqueios = set(candidato.get("bloqueios") or [])
    if bloqueios != BLOQUEIOS_RELAXAVEIS:
        return None
    pontuacao = _numero(candidato.get("pontuacao_tecnica"))
    qualidade = _numero(candidato.get("qualidade_dados"))
    odd = _numero(candidato.get("odd"))
    idade_odd = _numero(candidato.get("idade_odds_segundos"))
    regra_versao = candidato.get("regra_versao")
    regra_fingerprint = (
        candidato.get("regra_fingerprint")
        or (regra_fingerprints or {}).get(regra_versao)
    )
    if (
        pontuacao is None
        or pontuacao < PONTUACAO_MINIMA
        or qualidade is None
        or qualidade < QUALIDADE_MINIMA
        or odd is None
        or (idade_odd is not None and idade_odd > IDADE_ODD_MAXIMA_SEGUNDOS)
        or regra_versao != REGRA_VERSAO_GOL_FT_V3
        or regra_fingerprint != REGRA_FINGERPRINT_GOL_FT_V3
    ):
        return None

    features = candidato.get("features") or {}
    janela5 = (features.get("janelas") or {}).get("5") or {}
    chutes5 = _numero(janela5.get("chutes_total"))
    exploracao = deepcopy(candidato)
    exploracao["status"] = "simulacao"
    exploracao["bloqueios"] = []
    exploracao["motivos"] = list(exploracao.get("motivos") or []) + [
        (
            "exploracao_sombra="
            f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}"
        ),
        "relaxamento_exclusivo=atividade_recente_insuficiente_gols",
        "controle_futuro_fiel_v2_sem_filtro_atividade_adicional",
        "nao_enviar_telegram",
    ]
    exploracao["features"] = {
        **features,
        "exploracao_sombra": {
            "versao": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
            "fase": FASE_EXPLORACAO_GOLS,
            "reproducao_fiel_de": VERSAO_EXPLORACAO_SOMBRA,
            "comparado_com": VERSAO_EXPLORACAO_GOL_FT_V3,
            "minimo_resultados_validacao": (
                MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE
            ),
            "tamanho_coorte_fixa": (
                TAMANHO_COORTE_GOL_FT_V2_CONTROLE
            ),
            "bloqueios_originais": sorted(bloqueios),
            "pontuacao_minima": PONTUACAO_MINIMA,
            "qualidade_minima": QUALIDADE_MINIMA,
            "criterio_selecao": {
                "filtro_atividade_adicional": False,
                "chutes_5min_observados": chutes5,
            },
            "linhagem_esperada": {
                "regra_versao": REGRA_VERSAO_GOL_FT_V3,
                "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
            },
            "historico_v2_reaberto": False,
            "telegram_oficial": False,
            "aplicacao_automatica": False,
        },
    }
    return exploracao


def _instante_odds_epoch(valor):
    if isinstance(valor, datetime):
        instante = valor
    elif isinstance(valor, str) and valor.strip():
        texto = valor.strip()
        if texto.endswith("Z"):
            texto = f"{texto[:-1]}+00:00"
        try:
            instante = datetime.fromisoformat(texto)
        except ValueError:
            return None
    else:
        return None
    if instante.tzinfo is None:
        instante = instante.astimezone()
    return instante.timestamp()


def _instante_oferta_asiatica(mercado, oferta):
    for valor in (
        oferta.get("coletado_em"),
        mercado.get("coletado_em"),
        oferta.get("recebido_em"),
        mercado.get("recebido_em"),
    ):
        instante = _instante_odds_epoch(valor)
        if instante is not None:
            return instante
    return None


def _identidade_oferta_asiatica(mercado, oferta):
    fonte = str(
        oferta.get("fonte") or mercado.get("fonte") or ""
    ).strip().casefold()
    bookmaker = str(
        oferta.get("bookmaker") or mercado.get("bookmaker") or ""
    ).strip().casefold()
    evento = str(
        oferta.get("evento_externo_id")
        or mercado.get("evento_externo_id")
        or ""
    ).strip().casefold()
    if not (fonte or bookmaker or evento):
        # Sem uma identidade comprovada, dois mercados parecidos nao podem
        # ser tratados como revisoes da mesma casa/evento.
        return ("sem_identidade", id(mercado))
    return fonte, bookmaker, evento


def _idade_efetiva_oferta_asiatica(
    mercado, oferta, referencia=None
):
    idades = []
    for origem in (oferta, mercado):
        try:
            idade = float(origem.get("idade_segundos"))
        except (AttributeError, TypeError, ValueError):
            continue
        if math.isfinite(idade) and idade >= 0:
            idades.append(idade)
    instante = _instante_oferta_asiatica(mercado, oferta)
    referencia_epoch = _instante_odds_epoch(referencia)
    if referencia_epoch is None:
        referencia_epoch = datetime.now().astimezone().timestamp()
    if instante is not None:
        idades.append(max(referencia_epoch - instante, 0.0))
    return max(idades) if idades else None


def _oferta_asiatica_mais_proxima(candidato, odds):
    features = candidato.get("features") or {}
    atual = _numero(features.get("escanteios_atuais"))
    if atual is None:
        return None
    candidatas = []
    referencia = features.get("decisao_em")
    for mercado in (odds or {}).get("ao_vivo") or []:
        if (
            mercado.get("categoria") != "escanteios"
            or mercado.get("tipo_mercado") != "asiatico"
            or (mercado.get("escopo") or "total") != "total"
            or (mercado.get("formato") or "duas_opcoes")
            != "duas_opcoes"
        ):
            continue
        for oferta in mercado.get("ofertas") or []:
            linha = _numero((oferta or {}).get("linha"))
            if linha is None or linha < atual:
                continue
            idade_efetiva = _idade_efetiva_oferta_asiatica(
                mercado, oferta, referencia=referencia
            )
            candidatas.append((
                linha,
                mercado,
                oferta,
                _instante_oferta_asiatica(mercado, oferta),
                _identidade_oferta_asiatica(mercado, oferta),
                idade_efetiva,
            ))
    if not candidatas:
        return None

    # Uma casa substitui a linha inteira depois de cada escanteio. Nunca
    # escolha a menor linha de uma leitura antiga quando a mesma fonte ja
    # publicou outra: foi exatamente o que tornou 9.5 indisponivel enquanto
    # a Bet365 ja mostrava 11.0.
    mais_recentes = {}
    for (
        _linha, _mercado, _oferta, instante, identidade, _idade
    ) in candidatas:
        if instante is None:
            continue
        atual_recente = mais_recentes.get(identidade)
        if atual_recente is None or instante > atual_recente:
            mais_recentes[identidade] = instante
    candidatas = [
        item for item in candidatas
        if item[3] is None
        or mais_recentes.get(item[4]) is None
        or math.isclose(item[3], mais_recentes[item[4]], abs_tol=0.001)
    ]
    # Se houver uma linha que ainda pode ser enviada, uma cotação menor mas
    # já vencida não deve ganhar só por parecer mais fácil. Antes isso criava
    # uma simulação inevitavelmente barrada no pré-envio, mesmo com outra
    # fonte fresca disponível no mesmo snapshot.
    frescas = [
        item for item in candidatas
        if item[5] is not None
        and item[5] <= IDADE_ODD_ENVIO_ASIATICA_SEGUNDOS
    ]
    if frescas:
        candidatas = frescas
    _linha, mercado, oferta, _instante, _identidade, idade_efetiva = min(
        candidatas, key=lambda item: item[0]
    )
    coletado_em = oferta.get("coletado_em") or mercado.get("coletado_em")
    recebido_em = oferta.get("recebido_em") or mercado.get("recebido_em")
    cache = (
        oferta.get("cache")
        if isinstance(oferta.get("cache"), bool)
        else mercado.get("cache")
    )
    return {
        **oferta,
        "fonte": oferta.get("fonte") or mercado.get("fonte"),
        "bookmaker": oferta.get("bookmaker") or mercado.get("bookmaker"),
        "tipo_mercado": "asiatico",
        "coletado_em": coletado_em,
        "recebido_em": recebido_em,
        "cache": cache,
        "idade_segundos": idade_efetiva,
    }


def criar_exploracao_asiatica_multiplos(candidato, odds=None):
    """Mede Over asiático distante sem enviar ou alterar a regra oficial."""
    if candidato.get("mercado") != "escanteios_ft_asiatico":
        return None
    if candidato.get("status") != "rejeitado":
        return None
    bloqueios = set(candidato.get("bloqueios") or [])
    if bloqueios != {
        "linha_exige_multiplos_escanteios",
        "odd_ao_vivo_indisponivel",
    }:
        return None
    oferta = _oferta_asiatica_mais_proxima(candidato, odds)
    if oferta is None:
        return None
    pontuacao = _numero(candidato.get("pontuacao_tecnica"))
    qualidade = _numero(candidato.get("qualidade_dados"))
    odd = _numero(oferta.get("over"))
    linha = _numero(oferta.get("linha"))
    features = candidato.get("features") or {}
    minuto = _numero(features.get("minuto"))
    escanteios_atuais = _numero(features.get("escanteios_atuais"))
    idade_odd = _numero(oferta.get("idade_segundos"))
    janela5 = (features.get("janelas") or {}).get("5") or {}
    chutes5 = _numero(janela5.get("chutes_total")) or 0.0
    escanteios5 = _numero(janela5.get("escanteios_total")) or 0.0
    if linha is None or escanteios_atuais is None:
        return None
    gap = linha - escanteios_atuais
    if (
        pontuacao is None
        or pontuacao < PONTUACAO_MINIMA_ASIATICA
        or qualidade is None
        or qualidade < QUALIDADE_MINIMA_ASIATICA
        or odd is None
        or not odd_elegivel(odd, obter_limites_risco())
        or minuto is None
        or not MINUTO_MINIMO_ASIATICA <= minuto <= MINUTO_MAXIMO_ASIATICA
        or not 0.5 < gap <= GAP_MAXIMO_ASIATICA
        or janela5.get("disponivel") is not True
        or (escanteios5 < 1.0 and chutes5 < 3.0)
        or (idade_odd is not None and idade_odd > IDADE_ODD_MAXIMA_SEGUNDOS)
    ):
        return None

    exploracao = deepcopy(candidato)
    exploracao["status"] = "simulacao"
    exploracao["bloqueios"] = []
    exploracao["linha"] = linha
    exploracao["odd"] = odd
    exploracao["fonte_odds"] = oferta.get("fonte")
    exploracao["bookmaker_odds"] = oferta.get("bookmaker")
    exploracao["tipo_mercado_odds"] = "asiatico"
    exploracao["coletado_em_odds"] = oferta.get("coletado_em")
    exploracao["odds_cache"] = oferta.get("cache")
    exploracao["idade_odds_segundos"] = idade_odd
    exploracao["motivos"] = list(exploracao.get("motivos") or []) + [
        f"exploracao_sombra={VERSAO_EXPLORACAO_ASIATICA}",
        f"distancia_linha_escanteios={gap:g}",
        "nao_enviar_telegram",
    ]
    exploracao["features"] = {
        **features,
        "linha": linha,
        "odd": odd,
        "fonte_odds": oferta.get("fonte"),
        "bookmaker_odds": oferta.get("bookmaker"),
        "tipo_mercado_odds": "asiatico",
        "coletado_em_odds": oferta.get("coletado_em"),
        "odds_cache": oferta.get("cache"),
        "idade_odds_segundos": idade_odd,
        "exploracao_sombra": {
            "versao": VERSAO_EXPLORACAO_ASIATICA,
            "bloqueios_originais": sorted(bloqueios),
            "pontuacao_minima": PONTUACAO_MINIMA_ASIATICA,
            "qualidade_minima": QUALIDADE_MINIMA_ASIATICA,
            "minuto_minimo": MINUTO_MINIMO_ASIATICA,
            "minuto_maximo": MINUTO_MAXIMO_ASIATICA,
            "gap_maximo": GAP_MAXIMO_ASIATICA,
            "gap_observado": round(gap, 3),
            "atividade_minima": "escanteio_5min>=1_ou_chutes_5min>=3",
            "aplicacao_automatica": False,
        },
    }
    return exploracao


def gerar_exploracoes_sombra(
    candidatos, odds=None, regra_fingerprints=None
):
    exploracoes = []
    for candidato in candidatos or []:
        exploracao = criar_exploracao_sombra(
            candidato, regra_fingerprints=regra_fingerprints
        )
        if exploracao is not None:
            exploracoes.append(exploracao)
        controle_v2 = criar_exploracao_gol_ft_v2_controle(
            candidato, regra_fingerprints=regra_fingerprints
        )
        if controle_v2 is not None:
            exploracoes.append(controle_v2)
            challenger_v2 = criar_challenger_v2_ft(controle_v2)
            if challenger_v2 is not None:
                exploracoes.append(challenger_v2)
        if exploracao is None and controle_v2 is None:
            asiatica = criar_exploracao_asiatica_multiplos(
                candidato, odds
            )
            if asiatica is not None:
                exploracoes.append(asiatica)
    return exploracoes


def _resumir_funil_exploracao_gols_linhas(linhas):
    por_mercado = {}
    for linha in linhas:
        mercado = linha["mercado"]
        item = por_mercado.setdefault(mercado, {
            "tentativas_rejeitadas": 0,
            "partidas_unicas": set(),
            "bloqueios": {},
            "somente_atividade": 0,
            "pontuacao_elegivel": 0,
            "qualidade_elegivel": 0,
            "odd_disponivel": 0,
            "odd_fresca": 0,
            "aptas_reconstruidas": 0,
        })
        item["tentativas_rejeitadas"] += 1
        item["partidas_unicas"].add(linha["partida_id"])
        try:
            motivos = json.loads(linha["motivos_json"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            motivos = []
        bloqueios = {
            motivo.removeprefix("bloqueio:")
            for motivo in motivos
            if isinstance(motivo, str) and motivo.startswith("bloqueio:")
        }
        for bloqueio in bloqueios:
            item["bloqueios"][bloqueio] = (
                item["bloqueios"].get(bloqueio, 0) + 1
            )
        if bloqueios != BLOQUEIOS_RELAXAVEIS:
            continue
        item["somente_atividade"] += 1
        pontuacao = _numero(linha["pontuacao_tecnica"])
        if pontuacao is None or pontuacao < PONTUACAO_MINIMA:
            continue
        item["pontuacao_elegivel"] += 1
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        qualidade = _numero(features.get("qualidade_dados"))
        if qualidade is None or qualidade < QUALIDADE_MINIMA:
            continue
        item["qualidade_elegivel"] += 1
        if _numero(linha["odd"]) is None:
            continue
        item["odd_disponivel"] += 1
        idade = _numero(features.get("idade_odds_segundos"))
        if idade is not None and idade > IDADE_ODD_MAXIMA_SEGUNDOS:
            continue
        item["odd_fresca"] += 1
        item["aptas_reconstruidas"] += 1
    for item in por_mercado.values():
        item["partidas_unicas"] = len(item["partidas_unicas"])
        item["bloqueios"] = dict(sorted(
            item["bloqueios"].items(),
            key=lambda par: (-par[1], par[0]),
        ))
    return por_mercado


def resumir_exploracoes_sombra(conexao, agora=None, janela_horas=24):
    linhas = conexao.execute(
        """
        WITH exploracoes AS (
            SELECT s.id, s.partida_id, s.criado_em,
                   s.mercado, s.odd, s.regra_versao,
                   s.regra_fingerprint, s.features_json,
                   sp.contexto_api_json,
                   r.resultado, r.retorno_unidades,
                   ROW_NUMBER() OVER (
                       PARTITION BY
                           s.partida_id,
                           s.mercado,
                           json_extract(
                               s.features_json,
                               '$.exploracao_sombra.versao'
                           )
                       ORDER BY s.criado_em, s.id
                   ) AS ordem_independente
            FROM sinais s
            JOIN snapshots sp ON sp.id=s.snapshot_id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='simulacao'
              AND json_extract(
                  s.features_json,
                  '$.exploracao_sombra.versao'
              ) IS NOT NULL
        )
        SELECT id, partida_id, criado_em, mercado, odd,
               regra_versao, regra_fingerprint,
               features_json, contexto_api_json,
               resultado, retorno_unidades
        FROM exploracoes
        WHERE ordem_independente=1
        ORDER BY datetime(criado_em), id
        """
    ).fetchall()
    resumo = {}
    por_experimento = {}
    coorte_validacao = {mercado: [] for mercado in MERCADOS}
    coorte_validacao_gol_ft_v3 = []
    coorte_gol_ft_v2_controle = []
    coorte_v3_periodo_controle = []
    todos_gol_ft_v2_controle = []
    todos_v3_periodo_controle = []
    cobertura_temporal_validacao = {}

    chave_definicao_v3 = (
        f"{CHAVE_DEFINICAO_PREFIXO}{VERSAO_EXPLORACAO_GOL_FT_V3}"
    )
    linha_definicao_v3 = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (chave_definicao_v3,),
    ).fetchone()
    inicio_validacao_v3 = None
    if linha_definicao_v3 is not None:
        try:
            inicio_validacao_v3 = datetime.fromisoformat(
                json.loads(linha_definicao_v3["valor"])["registrado_em"]
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            inicio_validacao_v3 = None

    chave_definicao_v2_controle = (
        f"{CHAVE_DEFINICAO_PREFIXO}"
        f"{VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE}"
    )
    linha_definicao_v2_controle = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (chave_definicao_v2_controle,),
    ).fetchone()
    inicio_v2_controle = None
    if linha_definicao_v2_controle is not None:
        try:
            inicio_v2_controle = datetime.fromisoformat(
                json.loads(
                    linha_definicao_v2_controle["valor"]
                )["registrado_em"]
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            inicio_v2_controle = None

    def acumular(destino, mercado, resultado, retorno):
        item = destino.setdefault(mercado, {
            "total": 0,
            "pendentes": 0,
            "greens": 0,
            "reds": 0,
            "voids": 0,
            "lucro_unidades": 0.0,
        })
        item["total"] += 1
        if resultado is None:
            item["pendentes"] += 1
        elif resultado in ("green", "half_green"):
            item["greens"] += 1
        elif resultado in ("red", "half_red"):
            item["reds"] += 1
        else:
            item["voids"] += 1
        if retorno is not None:
            item["lucro_unidades"] += float(retorno)

    for linha in linhas:
        mercado = linha["mercado"]
        resultado = linha["resultado"]
        retorno = linha["retorno_unidades"]
        acumular(resumo, mercado, resultado, retorno)
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, ValueError):
            features = {}
        versao = ((features.get("exploracao_sombra") or {}).get("versao"))
        try:
            criado_em_linha = datetime.fromisoformat(linha["criado_em"])
        except (TypeError, ValueError):
            criado_em_linha = None
        if versao:
            acumular(
                por_experimento.setdefault(versao, {}),
                mercado,
                resultado,
                retorno,
            )
        if versao == VERSAO_EXPLORACAO_SOMBRA and mercado in MERCADOS:
            # A validação prospectiva precisa ser uma janela fixa. Depois
            # que os primeiros 30 candidatos independentes são escolhidos,
            # exemplos posteriores continuam no monitoramento geral, mas não
            # podem alterar retroativamente a decisão dessa validação.
            coorte = coorte_validacao[mercado]
            if len(coorte) < MINIMO_VALIDACAO_EXPLORACAO_GOLS:
                coorte.append({
                    "sinal_id": int(linha["id"]),
                    "regra_versao": linha["regra_versao"],
                    "regra_fingerprint": linha["regra_fingerprint"],
                    "resultado": resultado,
                    "retorno_unidades": retorno,
                })
            cobertura = cobertura_temporal_validacao.setdefault(
                mercado,
                {
                    "total": 0,
                    "resolvidos": 0,
                    "com_evolucao_api": 0,
                    "com_comparacao_fontes": 0,
                    "comparacoes": 0,
                    "comparacoes_concordantes": 0,
                    "com_confirmacao": {
                        "greens": 0, "reds": 0,
                        "lucro_unidades": 0.0,
                    },
                    "sem_confirmacao": {
                        "greens": 0, "reds": 0,
                        "lucro_unidades": 0.0,
                    },
                },
            )
            cobertura["total"] += 1
            try:
                contexto = json.loads(
                    linha["contexto_api_json"] or "{}"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                contexto = {}
            evolucao_api = (
                (contexto or {}).get("evolucao_temporal_api_live") or {}
            )
            tem_evolucao_api = any(
                isinstance(evolucao_api.get(str(janela)), dict)
                for janela in (5, 10, 15)
            )
            comparacao = (
                (contexto or {}).get(
                    "comparacao_temporal_packball_api"
                ) or {}
            )
            total_comparacoes = int(comparacao.get("total", 0) or 0)
            concordantes_comparacao = int(
                comparacao.get("concordantes", 0) or 0
            )
            confirmacao_fontes = (
                total_comparacoes > 0
                and concordantes_comparacao == total_comparacoes
            )
            cobertura["com_evolucao_api"] += int(tem_evolucao_api)
            cobertura["com_comparacao_fontes"] += int(
                total_comparacoes > 0
            )
            cobertura["comparacoes"] += total_comparacoes
            cobertura["comparacoes_concordantes"] += (
                concordantes_comparacao
            )
            if resultado in (
                "green", "half_green", "red", "half_red"
            ):
                cobertura["resolvidos"] += 1
                segmento = cobertura[
                    "com_confirmacao"
                    if confirmacao_fontes else "sem_confirmacao"
                ]
                if resultado in ("green", "half_green"):
                    segmento["greens"] += 1
                else:
                    segmento["reds"] += 1
                if retorno is not None:
                    segmento["lucro_unidades"] += float(retorno)
        if (
            versao == VERSAO_EXPLORACAO_GOL_FT_V3
            and mercado == "gol_ft"
            and len(coorte_validacao_gol_ft_v3)
            < TAMANHO_COORTE_VALIDACAO_GOL_FT_V3
        ):
            if (
                inicio_validacao_v3 is not None
                and criado_em_linha is not None
                and criado_em_linha >= inicio_validacao_v3
            ):
                coorte_validacao_gol_ft_v3.append({
                    "sinal_id": int(linha["id"]),
                    "partida_id": int(linha["partida_id"]),
                    "odd": linha["odd"],
                    "regra_versao": linha["regra_versao"],
                    "regra_fingerprint": linha["regra_fingerprint"],
                    "resultado": resultado,
                    "retorno_unidades": retorno,
                    **_extrair_contexto_comparacao_gol_ft(features),
                })
        if (
            versao == VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE
            and mercado == "gol_ft"
            and inicio_v2_controle is not None
            and criado_em_linha is not None
            and criado_em_linha >= inicio_v2_controle
        ):
            item_v2_controle = {
                "sinal_id": int(linha["id"]),
                "partida_id": int(linha["partida_id"]),
                "odd": linha["odd"],
                "regra_versao": linha["regra_versao"],
                "regra_fingerprint": linha["regra_fingerprint"],
                "resultado": resultado,
                "retorno_unidades": retorno,
                **_extrair_contexto_comparacao_gol_ft(features),
            }
            todos_gol_ft_v2_controle.append(item_v2_controle)
            if (
                len(coorte_gol_ft_v2_controle)
                < TAMANHO_COORTE_GOL_FT_V2_CONTROLE
            ):
                coorte_gol_ft_v2_controle.append(item_v2_controle)
        if (
            versao == VERSAO_EXPLORACAO_GOL_FT_V3
            and mercado == "gol_ft"
            and inicio_v2_controle is not None
            and criado_em_linha is not None
            and criado_em_linha >= inicio_v2_controle
        ):
            item_v3_controle = {
                "sinal_id": int(linha["id"]),
                "partida_id": int(linha["partida_id"]),
                "odd": linha["odd"],
                "regra_versao": linha["regra_versao"],
                "regra_fingerprint": linha["regra_fingerprint"],
                "resultado": resultado,
                "retorno_unidades": retorno,
                **_extrair_contexto_comparacao_gol_ft(features),
            }
            todos_v3_periodo_controle.append(item_v3_controle)
            if (
                len(coorte_v3_periodo_controle)
                < TAMANHO_COORTE_GOL_FT_V2_CONTROLE
            ):
                coorte_v3_periodo_controle.append(item_v3_controle)
    def finalizar(destino):
        for item in destino.values():
            avaliadas = item["greens"] + item["reds"]
            item["roi"] = (
                round(item["lucro_unidades"] / avaliadas, 4)
                if avaliadas else None
            )
            item["taxa_acerto"] = (
                round(item["greens"] / avaliadas, 4)
                if avaliadas else None
            )
            item["lucro_unidades"] = round(
                item["lucro_unidades"], 4
            )

    finalizar(resumo)
    for mercados in por_experimento.values():
        finalizar(mercados)
    for cobertura in cobertura_temporal_validacao.values():
        cobertura["taxa_cobertura_evolucao_api"] = round(
            cobertura["com_evolucao_api"] / cobertura["total"], 4
        ) if cobertura["total"] else None
        cobertura["taxa_cobertura_comparacao_fontes"] = round(
            cobertura["com_comparacao_fontes"] / cobertura["total"], 4
        ) if cobertura["total"] else None
        cobertura["taxa_concordancia_comparacoes"] = round(
            cobertura["comparacoes_concordantes"]
            / cobertura["comparacoes"], 4
        ) if cobertura["comparacoes"] else None
        for segmento in (
            cobertura["com_confirmacao"],
            cobertura["sem_confirmacao"],
        ):
            avaliadas_segmento = segmento["greens"] + segmento["reds"]
            segmento["lucro_unidades"] = round(
                segmento["lucro_unidades"], 4
            )
            segmento["roi"] = round(
                segmento["lucro_unidades"] / avaliadas_segmento, 4
            ) if avaliadas_segmento else None
            segmento["amostra"] = avaliadas_segmento
        cobertura["aplicacao_automatica"] = False
        cobertura["uso_na_decisao_validacao"] = False
    validacao_prospectiva = {}
    for mercado in sorted(MERCADOS):
        item_total = (
            por_experimento.get(VERSAO_EXPLORACAO_SOMBRA, {})
            .get(mercado, {})
        )
        coorte = coorte_validacao[mercado]
        resolvidos = [
            item for item in coorte
            if item["resultado"] in (
                "green", "half_green", "red", "half_red"
            )
            and item["retorno_unidades"] is not None
        ]
        retornos = [
            float(item["retorno_unidades"])
            for item in resolvidos
        ]
        avaliadas = len(resolvidos)
        greens = sum(
            item["resultado"] in ("green", "half_green")
            for item in resolvidos
        )
        reds = sum(
            item["resultado"] in ("red", "half_red")
            for item in resolvidos
        )
        pendentes = len(coorte) - avaliadas
        linhagens_coorte = sorted({
            (
                str(item["regra_versao"] or ""),
                str(item["regra_fingerprint"] or ""),
            )
            for item in coorte
        })
        linhagem_homogenea = len(linhagens_coorte) <= 1
        avaliacao = _avaliar_retornos_validacao_gols(
            retornos
        )
        intervalo_roi_95 = avaliacao["intervalo_roi_95"]
        roi = avaliacao["roi"]
        lucro = avaliacao["lucro_unidades"]
        decisao_estatistica = avaliacao["decisao_estatistica"]
        if not linhagem_homogenea:
            decisao_estatistica = "linhagem_inconsistente"
        fingerprint_coorte = hashlib.sha256(json.dumps(
            [
                [item["sinal_id"], item["resultado"]]
                for item in coorte
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        validacao_prospectiva[mercado] = {
            "versao": VERSAO_EXPLORACAO_SOMBRA,
            "versao_desenvolvimento": (
                VERSAO_EXPLORACAO_DESENVOLVIMENTO
            ),
            "minimo_resultados": MINIMO_VALIDACAO_EXPLORACAO_GOLS,
            "avaliadas": avaliadas,
            "faltam": max(
                0,
                MINIMO_VALIDACAO_EXPLORACAO_GOLS - avaliadas,
            ),
            "estado": (
                "inconsistente"
                if not linhagem_homogenea
                else
                "pronta_para_revisao_independente"
                if avaliadas >= MINIMO_VALIDACAO_EXPLORACAO_GOLS
                else "aguardando_amostra_futura"
            ),
            "roi": roi,
            "intervalo_roi_95": intervalo_roi_95,
            "politica_avaliacao_versao": (
                VERSAO_POLITICA_AVALIACAO_GOLS
            ),
            "decisao_estatistica": decisao_estatistica,
            "taxa_acerto": (
                round(greens / avaliadas, 4) if avaliadas else None
            ),
            "greens": greens,
            "reds": reds,
            "pendentes": pendentes,
            "lucro_unidades": lucro,
            "candidatos_coorte": len(coorte),
            "total_disponivel": int(item_total.get("total", 0)),
            "resultados_totais_disponiveis": (
                int(item_total.get("greens", 0))
                + int(item_total.get("reds", 0))
            ),
            "validacao_congelada": (
                avaliadas >= MINIMO_VALIDACAO_EXPLORACAO_GOLS
            ),
            "validacao_fingerprint": fingerprint_coorte,
            "linhagem_homogenea": linhagem_homogenea,
            "linhagens_coorte": [
                {
                    "regra_versao": regra_versao,
                    "regra_fingerprint": regra_fingerprint,
                }
                for regra_versao, regra_fingerprint in linhagens_coorte
            ],
            "aplicacao_automatica": False,
            "promocao_automatica": False,
        }

    item_total_v3 = (
        por_experimento.get(VERSAO_EXPLORACAO_GOL_FT_V3, {})
        .get("gol_ft", {})
    )
    coorte_v3 = coorte_validacao_gol_ft_v3
    resolvidos_v3 = [
        item for item in coorte_v3
        if item["resultado"] in (
            "green", "half_green", "red", "half_red"
        )
        and item["retorno_unidades"] is not None
    ]
    retornos_v3 = [
        float(item["retorno_unidades"]) for item in resolvidos_v3
    ]
    avaliadas_v3 = len(resolvidos_v3)
    greens_v3 = sum(
        item["resultado"] in ("green", "half_green")
        for item in resolvidos_v3
    )
    reds_v3 = sum(
        item["resultado"] in ("red", "half_red")
        for item in resolvidos_v3
    )
    pendentes_v3 = sum(
        item["resultado"] is None for item in coorte_v3
    )
    invalidos_v3 = len(coorte_v3) - avaliadas_v3 - pendentes_v3
    coorte_fechada_v3 = (
        len(coorte_v3) >= TAMANHO_COORTE_VALIDACAO_GOL_FT_V3
    )
    linhagens_v3 = sorted({
        (
            str(item["regra_versao"] or ""),
            str(item["regra_fingerprint"] or ""),
        )
        for item in coorte_v3
    })
    linhagem_homogenea_v3 = len(linhagens_v3) <= 1
    linhagem_compativel_v3 = all(
        regra_versao == REGRA_VERSAO_GOL_FT_V3
        and regra_fingerprint == REGRA_FINGERPRINT_GOL_FT_V3
        for regra_versao, regra_fingerprint in linhagens_v3
    )
    avaliacao_v3 = _avaliar_retornos_validacao_gols(
        retornos_v3,
        minimo_resultados=MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3,
    )
    if not (linhagem_homogenea_v3 and linhagem_compativel_v3):
        estado_v3 = "inconsistente"
        decisao_v3 = "linhagem_inconsistente"
    elif not coorte_fechada_v3:
        estado_v3 = "aguardando_coorte_futura"
        decisao_v3 = "aguardando_coorte_futura"
    elif pendentes_v3:
        estado_v3 = "aguardando_resultados"
        decisao_v3 = "aguardando_resultados"
    elif avaliadas_v3 < MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3:
        estado_v3 = "inconclusiva"
        decisao_v3 = "amostra_valida_insuficiente"
    else:
        estado_v3 = "pronta_para_revisao_independente"
        decisao_v3 = avaliacao_v3["decisao_estatistica"]
    fingerprint_coorte_v3 = hashlib.sha256(json.dumps(
        [
            [
                item["sinal_id"], item["partida_id"],
                item["regra_versao"], item["regra_fingerprint"],
            ]
            for item in coorte_v3
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    validacao_prospectiva_gol_ft_v3 = {
        "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
        "derivada_de": VERSAO_EXPLORACAO_SOMBRA,
        "politica_avaliacao_versao": (
            VERSAO_POLITICA_AVALIACAO_GOL_FT_V3
        ),
        "tamanho_coorte_fixa": TAMANHO_COORTE_VALIDACAO_GOL_FT_V3,
        "minimo_resultados_validos": (
            MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3
        ),
        "candidatos_coorte": len(coorte_v3),
        "faltam_candidatos": max(
            0,
            TAMANHO_COORTE_VALIDACAO_GOL_FT_V3 - len(coorte_v3),
        ),
        "avaliadas": avaliadas_v3,
        "faltam_resultados_validos": max(
            0,
            MINIMO_RESULTADOS_VALIDOS_GOL_FT_V3 - avaliadas_v3,
        ),
        "greens": greens_v3,
        "reds": reds_v3,
        "pendentes": pendentes_v3,
        "invalidos": invalidos_v3,
        "taxa_acerto": (
            round(greens_v3 / avaliadas_v3, 4)
            if avaliadas_v3 else None
        ),
        "lucro_unidades": avaliacao_v3["lucro_unidades"],
        "roi": avaliacao_v3["roi"],
        "intervalo_roi_95": avaliacao_v3["intervalo_roi_95"],
        "estado": estado_v3,
        "decisao_estatistica": decisao_v3,
        "coorte_fechada": coorte_fechada_v3,
        "validacao_congelada": coorte_fechada_v3,
        "resultados_completos": (
            coorte_fechada_v3 and pendentes_v3 == 0
        ),
        "validacao_fingerprint": fingerprint_coorte_v3,
        "linhagem_homogenea": linhagem_homogenea_v3,
        "linhagem_compativel": linhagem_compativel_v3,
        "linhagem_esperada": {
            "regra_versao": REGRA_VERSAO_GOL_FT_V3,
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
        },
        "linhagens_coorte": [
            {
                "regra_versao": regra_versao,
                "regra_fingerprint": regra_fingerprint,
            }
            for regra_versao, regra_fingerprint in linhagens_v3
        ],
        "criterio_selecao": {
            "feature": FEATURE_CHUTES_5MIN_GOL_FT_V3,
            "operador": "maior_igual",
            "limiar": LIMIAR_CHUTES_5MIN_GOL_FT_V3,
        },
        "iniciado_em": (
            inicio_validacao_v3.replace(microsecond=0).isoformat()
            if inicio_validacao_v3 is not None else None
        ),
        "total_disponivel": int(item_total_v3.get("total", 0)),
        "resultados_totais_disponiveis": (
            int(item_total_v3.get("greens", 0))
            + int(item_total_v3.get("reds", 0))
        ),
        "aplicacao_automatica": False,
        "promocao_automatica": False,
        "telegram_oficial": False,
    }

    item_total_v2_controle = (
        por_experimento.get(
            VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE, {}
        ).get("gol_ft", {})
    )
    metricas_v2_controle = _resumir_coorte_fixa_gol_ft(
        coorte_gol_ft_v2_controle,
        TAMANHO_COORTE_GOL_FT_V2_CONTROLE,
        MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE,
        REGRA_VERSAO_GOL_FT_V3,
        REGRA_FINGERPRINT_GOL_FT_V3,
    )
    validacao_gol_ft_v2_controle = {
        "versao": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
        "reproducao_fiel_de": VERSAO_EXPLORACAO_SOMBRA,
        "historico_v2_reaberto": False,
        "comparado_com": VERSAO_EXPLORACAO_GOL_FT_V3,
        "politica_avaliacao_versao": (
            VERSAO_POLITICA_AVALIACAO_GOL_FT_V2_CONTROLE
        ),
        "tamanho_coorte_fixa": TAMANHO_COORTE_GOL_FT_V2_CONTROLE,
        "minimo_resultados_validos": (
            MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE
        ),
        **metricas_v2_controle,
        "linhagem_esperada": {
            "regra_versao": REGRA_VERSAO_GOL_FT_V3,
            "regra_fingerprint": REGRA_FINGERPRINT_GOL_FT_V3,
        },
        "criterio_selecao": {
            "bloqueios_exatos": sorted(BLOQUEIOS_RELAXAVEIS),
            "pontuacao_minima": PONTUACAO_MINIMA,
            "qualidade_minima": QUALIDADE_MINIMA,
            "idade_odd_maxima_segundos": IDADE_ODD_MAXIMA_SEGUNDOS,
            "filtro_atividade_adicional": False,
        },
        "iniciado_em": (
            inicio_v2_controle.replace(microsecond=0).isoformat()
            if inicio_v2_controle is not None else None
        ),
        "total_disponivel": int(item_total_v2_controle.get("total", 0)),
        "resultados_totais_disponiveis": (
            int(item_total_v2_controle.get("greens", 0))
            + int(item_total_v2_controle.get("reds", 0))
        ),
        "aplicacao_automatica": False,
        "promocao_automatica": False,
        "telegram_oficial": False,
    }

    metricas_v3_periodo_controle = _resumir_coorte_fixa_gol_ft(
        coorte_v3_periodo_controle,
        TAMANHO_COORTE_GOL_FT_V2_CONTROLE,
        MINIMO_RESULTADOS_VALIDOS_GOL_FT_V2_CONTROLE,
        REGRA_VERSAO_GOL_FT_V3,
        REGRA_FINGERPRINT_GOL_FT_V3,
    )
    por_partida_v2 = {
        item["partida_id"]: item for item in coorte_gol_ft_v2_controle
    }
    por_partida_v3 = {
        item["partida_id"]: item for item in coorte_v3_periodo_controle
    }
    ids_sobrepostos = sorted(set(por_partida_v2) & set(por_partida_v3))
    pares_resolvidos = [
        (por_partida_v2[partida_id], por_partida_v3[partida_id])
        for partida_id in ids_sobrepostos
        if por_partida_v2[partida_id]["resultado"] in (
            "green", "half_green", "red", "half_red"
        )
        and por_partida_v3[partida_id]["resultado"] in (
            "green", "half_green", "red", "half_red"
        )
    ]
    pares_resultado_concordante = sum(
        esquerdo["resultado"] == direito["resultado"]
        for esquerdo, direito in pares_resolvidos
    )
    ids_apenas_v2 = sorted(set(por_partida_v2) - set(por_partida_v3))
    ids_apenas_v3 = sorted(set(por_partida_v3) - set(por_partida_v2))
    itens_apenas_v2 = [por_partida_v2[item] for item in ids_apenas_v2]
    itens_apenas_v3 = [por_partida_v3[item] for item in ids_apenas_v3]
    resumo_exclusivo_v2 = _resumir_subgrupo_comparacao_gol_ft(
        itens_apenas_v2
    )
    resumo_exclusivo_v3 = _resumir_subgrupo_comparacao_gol_ft(
        itens_apenas_v3
    )
    comparacao_exclusivos = _comparar_subgrupos_independentes(
        itens_apenas_v2, itens_apenas_v3
    )
    pos_coorte_v2 = todos_gol_ft_v2_controle[
        TAMANHO_COORTE_GOL_FT_V2_CONTROLE:
    ]
    pos_coorte_v3 = todos_v3_periodo_controle[
        TAMANHO_COORTE_GOL_FT_V2_CONTROLE:
    ]
    resumo_pos_coorte_v2 = _resumir_subgrupo_comparacao_gol_ft(
        pos_coorte_v2
    )
    resumo_pos_coorte_v3 = _resumir_subgrupo_comparacao_gol_ft(
        pos_coorte_v3
    )
    roi_v2 = metricas_v2_controle.get("roi")
    roi_v3 = metricas_v3_periodo_controle.get("roi")
    if (
        resumo_pos_coorte_v2.get("decisao_estatistica")
        == "evidencia_desfavoravel"
    ):
        estado_comparacao = "v2_regrediu_pos_coorte_sem_promocao"
        metodo_preferido = None
    elif (
        metricas_v2_controle.get("decisao_estatistica")
        == "favoravel_para_revisao_independente"
        and comparacao_exclusivos.get("decisao") == "v2_exclusivo_superior"
    ):
        estado_comparacao = "v2_apto_somente_para_revisao_independente"
        metodo_preferido = "v2_controle"
    elif (
        metricas_v3_periodo_controle.get("decisao_estatistica")
        == "favoravel_para_revisao_independente"
        and comparacao_exclusivos.get("decisao") == "v3_exclusivo_superior"
    ):
        estado_comparacao = "v3_apto_somente_para_revisao_independente"
        metodo_preferido = "v3"
    elif (
        roi_v2 is not None and roi_v3 is not None and roi_v2 > roi_v3
    ):
        estado_comparacao = "v2_melhor_estimativa_sem_vantagem_comprovada"
        metodo_preferido = None
    elif (
        roi_v2 is not None and roi_v3 is not None and roi_v3 > roi_v2
    ):
        estado_comparacao = "v3_melhor_estimativa_sem_vantagem_comprovada"
        metodo_preferido = None
    else:
        estado_comparacao = "nenhum_metodo_com_vantagem_comprovada"
        metodo_preferido = None
    comparacao_gol_ft_v2_controle_v3 = {
        "iniciado_em": (
            inicio_v2_controle.replace(microsecond=0).isoformat()
            if inicio_v2_controle is not None else None
        ),
        "criterio_periodo": "mesmo_inicio_do_controle_v2_futuro",
        "tamanho_maximo_por_braco": (
            TAMANHO_COORTE_GOL_FT_V2_CONTROLE
        ),
        "v2_controle": {
            "versao": VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
            **metricas_v2_controle,
        },
        "v3": {
            "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
            **metricas_v3_periodo_controle,
        },
        "sobreposicao": {
            "candidatos": len(ids_sobrepostos),
            "resolvidos_pareados": len(pares_resolvidos),
            "resultados_concordantes": pares_resultado_concordante,
            "resultados_divergentes": (
                len(pares_resolvidos) - pares_resultado_concordante
            ),
            "apenas_v2_controle": len(
                ids_apenas_v2
            ),
            "apenas_v3": len(
                ids_apenas_v3
            ),
            "taxa_sobreposicao_na_v3": (
                round(
                    len(ids_sobrepostos) / len(por_partida_v3), 4
                )
                if por_partida_v3 else None
            ),
        },
        "subgrupos_exclusivos": {
            "v2_controle": resumo_exclusivo_v2,
            "v3": resumo_exclusivo_v3,
            "comparacao": comparacao_exclusivos,
            "uso_para_sinais": False,
        },
        "monitoramento_pos_coorte": {
            "v2_controle": resumo_pos_coorte_v2,
            "v3": resumo_pos_coorte_v3,
            "inicio_indice": TAMANHO_COORTE_GOL_FT_V2_CONTROLE,
            "altera_validacao_congelada": False,
            "uso_para_sinais": False,
        },
        "conclusao": {
            "estado": estado_comparacao,
            "metodo_preferido_para_revisao": metodo_preferido,
            "manter_v2_em_sombra": True,
            "manter_v3_em_sombra": True,
            "alterar_regra_ativa": False,
            "motivo": (
                "nenhum_braco_possui_roi_positivo_com_intervalo_95_acima_zero"
                if metodo_preferido is None
                else "revisao_independente_obrigatoria_antes_de_promocao"
            ),
        },
        "promocao_automatica": False,
        "telegram_oficial": False,
    }
    agora = agora or datetime.now()
    desde = agora - timedelta(hours=float(janela_horas))
    chave_definicao = (
        f"{CHAVE_DEFINICAO_PREFIXO}{VERSAO_EXPLORACAO_SOMBRA}"
    )
    linha_definicao = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (chave_definicao,),
    ).fetchone()
    inicio_validacao = None
    if linha_definicao is not None:
        try:
            inicio_validacao = datetime.fromisoformat(
                json.loads(linha_definicao["valor"])["registrado_em"]
            )
            desde = max(desde, inicio_validacao)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            inicio_validacao = None
    linhas_funil = conexao.execute(
        """
        SELECT partida_id, mercado, pontuacao_tecnica, odd,
               motivos_json, features_json
        FROM sinais
        WHERE status='rejeitado'
          AND mercado IN ('gol_ft', 'gol_ht')
          AND datetime(criado_em) >= datetime(?)
        ORDER BY id
        """,
        (desde.replace(microsecond=0).isoformat(),),
    ).fetchall()
    funil_recente = {
        "janela_horas": float(janela_horas),
        "desde": desde.replace(microsecond=0).isoformat(),
        "inicio_validacao": (
            inicio_validacao.replace(microsecond=0).isoformat()
            if inicio_validacao is not None else None
        ),
        "por_mercado": _resumir_funil_exploracao_gols_linhas(
            linhas_funil
        ),
    }
    return {
        "versao": "exploracoes-sombra-v4",
        "versoes": sorted(por_experimento),
        "aplicacao_automatica": False,
        "por_mercado": resumo,
        "por_experimento": por_experimento,
        "validacao_prospectiva_gols": validacao_prospectiva,
        "validacao_prospectiva_gol_ft_v3": (
            validacao_prospectiva_gol_ft_v3
        ),
        "validacao_gol_ft_v2_controle": (
            validacao_gol_ft_v2_controle
        ),
        "comparacao_gol_ft_v2_controle_v3": (
            comparacao_gol_ft_v2_controle_v3
        ),
        "cobertura_temporal_validacao_gols": (
            cobertura_temporal_validacao
        ),
        "funil_recente_gols": funil_recente,
    }
