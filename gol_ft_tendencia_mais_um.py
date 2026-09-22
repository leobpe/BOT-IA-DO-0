"""Rota FT de mais um gol guiada por tendência pré-jogo e histórica."""

import copy
import hashlib
import inspect
import json
import math
from pathlib import Path

from configuracao import odd_elegivel, obter_limites_risco
from qualidade_dados import extrair_minuto, extrair_placar
from previsao_gols_provedor import linha_over_prevista, total_gols_esperados


VERSAO = "gol-ft-tendencia-15-mais-um-odd144-v5"
VERSAO_POLITICA = "politica-gol-ft-tendencia-15-mais-um-odd144-v5"
MINUTO_MINIMO = 46
MINUTO_MAXIMO_PADRAO = 82
MINUTO_MAXIMO_2_2 = 75
ODD_MINIMA_DISPARO = 1.44
QUALIDADE_MINIMA = 80.0
TAXA_OVER_15_MINIMA = 0.60
AMOSTRA_MINIMA = 5
AMOSTRA_MANDO_MINIMA = 6
TAXA_OVER_15_MANDO_MINIMA = 0.50
TAXA_MARCOU_MANDO_MINIMA = 0.65
MEDIA_GOLS_PRO_MANDO_MINIMA = 1.20
CHUTES_RECENTES_MINIMOS = 2.0
PRESSAO_PICO_MINIMA = 65.0
EVIDENCIAS_MINIMAS = 2
TENDENCIA_MINIMA = 1.5

# O apoio histórico precisa acompanhar a linha pedida no momento da entrada.
# Usar Over 1,5 para aprovar Over 2,5/4,5 confunde um padrão que o placar atual
# já cumpriu com evidência de que ainda sairá outro gol.
APOIO_HISTORICO_POR_LINHA = {
    0.5: {
        "campo": "over_0_5_taxa", "geral_minima": 0.75,
        "mando_minima": 0.65,
    },
    1.5: {
        "campo": "over_1_5_taxa", "geral_minima": 0.60,
        "mando_minima": 0.50,
    },
    2.5: {
        "campo": "over_2_5_taxa", "geral_minima": 0.45,
        "mando_minima": 0.35,
    },
    4.5: {
        "campo": "over_4_5_taxa", "geral_minima": 0.15,
        "mando_minima": 0.10,
    },
}

PLACARES_LINHAS = {
    (0, 0): 0.5,
    (1, 0): 1.5,
    (0, 1): 1.5,
    (1, 1): 2.5,
    (2, 2): 4.5,
}

_BLOQUEIOS_RELAXAVEIS = frozenset({
    "atividade_recente_insuficiente_gols",
    "historico_5min_insuficiente",
})


def _linhagem():
    pasta = Path(__file__).parent
    nucleo = {
        "versao": VERSAO,
        "politica": VERSAO_POLITICA,
        "arquivo": hashlib.sha256(
            (pasta / Path(__file__).name).read_bytes()
        ).hexdigest(),
        "leitura_previsao": hashlib.sha256(
            (pasta / "previsao_gols_provedor.py").read_bytes()
        ).hexdigest(),
        "odd_elegivel": hashlib.sha256(
            inspect.getsource(odd_elegivel).encode("utf-8")
        ).hexdigest(),
        "minuto_minimo": MINUTO_MINIMO,
        "minuto_maximo_padrao": MINUTO_MAXIMO_PADRAO,
        "minuto_maximo_2_2": MINUTO_MAXIMO_2_2,
        "placares_linhas": sorted(
            (list(placar), linha) for placar, linha in PLACARES_LINHAS.items()
        ),
        "odd_minima_disparo": ODD_MINIMA_DISPARO,
        "qualidade_minima": QUALIDADE_MINIMA,
        "taxa_over_15_minima": TAXA_OVER_15_MINIMA,
        "amostra_minima": AMOSTRA_MINIMA,
        "historico_mando": {
            "amostra_minima": AMOSTRA_MANDO_MINIMA,
            "taxa_over_15_minima": TAXA_OVER_15_MANDO_MINIMA,
            "taxa_marcou_minima": TAXA_MARCOU_MANDO_MINIMA,
            "media_gols_pro_minima": MEDIA_GOLS_PRO_MANDO_MINIMA,
        },
        "atividade_recente": {
            "chutes_minimos": CHUTES_RECENTES_MINIMOS,
            "pressao_pico_minima": PRESSAO_PICO_MINIMA,
        },
        "evidencias_minimas": EVIDENCIAS_MINIMAS,
        "tendencia_exigida": [TENDENCIA_MINIMA, None],
        "apoio_historico_por_linha": APOIO_HISTORICO_POR_LINHA,
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


LINHAGEM = _linhagem()


def _numero(valor):
    if isinstance(valor, str):
        valor = valor.strip().replace("%", "").replace(",", ".")
    try:
        numero = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
    return numero if numero is not None and math.isfinite(numero) else None


def _linha_esperada(jogo):
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    if minuto is None or placar is None:
        return None, None, None
    placar = tuple(placar)
    linha = PLACARES_LINHAS.get(placar)
    limite = MINUTO_MAXIMO_2_2 if placar == (2, 2) else MINUTO_MAXIMO_PADRAO
    if linha is None or not MINUTO_MINIMO <= minuto <= limite:
        return None, placar, minuto
    return linha, placar, minuto


def elegivel_para_contexto(jogo, qualidade=None, candidatos=None):
    linha, _, _ = _linha_esperada(jogo)
    return bool(
        linha is not None
        and (_numero((qualidade or {}).get("pontuacao")) or 0) >= 70
        and (qualidade or {}).get("divergencia_critica") is not True
        and any(
            x.get("mercado") == "gol_ft"
            and _numero(x.get("linha")) == linha
            and x.get("odd") is not None
            for x in candidatos or []
        )
    )


def _evidencias_tendencia(contexto):
    evidencias = []
    odds = (
        (((contexto or {}).get("odds_pre_jogo") or {}).get("mercados") or {})
        .get("gols_ft") or {}
    )
    linha_consenso = _numero(odds.get("linha_consenso"))
    if (
        odds.get("consenso_suficiente") is True
        and linha_consenso is not None
        and linha_consenso >= TENDENCIA_MINIMA
    ):
        evidencias.append("consenso_odds_pre_15_ou_mais")

    previsao = (contexto or {}).get("previsao_provedor") or {}
    linha_prevista = linha_over_prevista(previsao.get("over_under"))
    if linha_prevista is not None and linha_prevista >= TENDENCIA_MINIMA:
        evidencias.append("previsao_provedor_15_ou_mais")

    soma = total_gols_esperados(previsao.get("gols_esperados"))
    if soma is not None and soma >= TENDENCIA_MINIMA:
        evidencias.append("gols_esperados_15_ou_mais")

    h2h = (contexto or {}).get("confrontos_diretos") or {}
    media_h2h = _numero(h2h.get("media_gols"))
    if (
        int(_numero(h2h.get("jogos")) or 0) >= AMOSTRA_MINIMA
        and media_h2h is not None
        and media_h2h >= TENDENCIA_MINIMA
    ):
        evidencias.append("h2h_media_15_ou_mais")

    recentes = (
        ((contexto or {}).get("capacidade_times_v2") or {}).get("recentes")
        or {}
    )
    perfis = [
        ((recentes.get(lado) or {}).get("geral") or {})
        for lado in ("mandante", "visitante")
    ]
    if all(
        int(perfil.get("jogos") or 0) >= 10
        and (_numero(perfil.get("over_1_5_taxa")) or 0)
        >= TAXA_OVER_15_MINIMA
        for perfil in perfis
    ):
        evidencias.append("forma15_over15_ambos_times")
    return evidencias


def _total_vermelhos(contexto):
    times = (((contexto or {}).get("eventos_ao_vivo") or {}).get("times") or {})
    return sum(
        int((times.get(lado) or {}).get("cartoes_vermelhos") or 0) > 0
        for lado in ("mandante", "visitante")
    )


def _historico_gols_forte(contexto, linha):
    capacidade_recentes = (
        ((contexto or {}).get("capacidade_times_v2") or {}).get("recentes")
        or {}
    )
    linhas_recentes = (
        ((contexto or {}).get("tendencia_linhas_gols_v1") or {}).get("recentes")
        or {}
    )
    gerais = [
        ((linhas_recentes.get(lado) or {}).get("geral") or {})
        for lado in ("mandante", "visitante")
    ]
    mandos = [
        ((linhas_recentes.get(lado) or {}).get("mando") or {})
        for lado in ("mandante", "visitante")
    ]
    mandos_capacidade = [
        ((capacidade_recentes.get(lado) or {}).get("mando") or {})
        for lado in ("mandante", "visitante")
    ]
    apoio = APOIO_HISTORICO_POR_LINHA.get(float(linha))
    if apoio is None:
        return {"aprovado": False, "motivo": "linha_sem_apoio_historico"}
    campo_linha = apoio["campo"]
    gerais_fortes = all(
        int(_numero(item.get("jogos")) or 0) >= 10
        and (_numero(item.get(campo_linha)) or 0)
        >= apoio["geral_minima"]
        for item in gerais
    )
    mandos_cobertos = all(
        int(_numero(item.get("jogos")) or 0) >= AMOSTRA_MANDO_MINIMA
        and (_numero(item.get(campo_linha)) or 0)
        >= apoio["mando_minima"]
        for item in mandos
    )
    ataque_capaz = any(
        (_numero(item.get("marcou_taxa")) or 0)
        >= TAXA_MARCOU_MANDO_MINIMA
        and (_numero(item.get("gols_pro_media")) or 0)
        >= MEDIA_GOLS_PRO_MANDO_MINIMA
        for item in mandos_capacidade
    )
    return {
        "aprovado": bool(gerais_fortes and mandos_cobertos and ataque_capaz),
        "gerais_fortes": gerais_fortes,
        "mandos_cobertos": mandos_cobertos,
        "ataque_capaz": ataque_capaz,
        "linha_avaliada": float(linha),
        "campo_historico_linha": campo_linha,
        "taxa_linha_geral": [
            _numero(item.get(campo_linha)) for item in gerais
        ],
        "taxa_linha_mando": [
            _numero(item.get(campo_linha)) for item in mandos
        ],
        "taxa_linha_geral_minima": apoio["geral_minima"],
        "taxa_linha_mando_minima": apoio["mando_minima"],
        "marcou_mando": [
            _numero(item.get("marcou_taxa")) for item in mandos_capacidade
        ],
        "gols_pro_mando": [
            _numero(item.get("gols_pro_media")) for item in mandos_capacidade
        ],
    }


def _atividade_recente_forte(base):
    features = (base or {}).get("features") or {}
    janelas = features.get("janelas") or {}
    chutes = []
    picos = []
    for janela in ("5", "10"):
        dados = janelas.get(janela) or {}
        if dados.get("disponivel") is False:
            continue
        total = _numero(dados.get("chutes_total"))
        if total is not None:
            chutes.append(total)
        for valor in dados.get("pressao_pico") or []:
            numero = _numero(valor)
            if numero is not None:
                picos.append(numero)
    chutes_maximo = max(chutes, default=0.0)
    pressao_pico = max(picos, default=0.0)
    aprovado = bool(
        chutes_maximo >= CHUTES_RECENTES_MINIMOS
        or (chutes_maximo >= 1.0 and pressao_pico >= PRESSAO_PICO_MINIMA)
    )
    return {
        "aprovado": aprovado,
        "chutes_maximo_5_10": chutes_maximo,
        "pressao_pico_5_10": pressao_pico,
    }


def gerar_gol_ft_tendencia_mais_um(jogo, candidatos, contexto, qualidade):
    if not elegivel_para_contexto(jogo, qualidade, candidatos):
        return []
    if (
        (_numero((qualidade or {}).get("pontuacao")) or 0) < QUALIDADE_MINIMA
        or (qualidade or {}).get("campos_ausentes")
        or not isinstance(contexto, dict)
    ):
        return []
    linha, placar, minuto = _linha_esperada(jogo)
    base = next(
        (
            item for item in candidatos or []
            if item.get("mercado") == "gol_ft"
            and _numero(item.get("linha")) == linha
        ),
        None,
    )
    if base is None or (
        base.get("status") == "aprovado" and not base.get("bloqueios")
    ):
        return []
    odd = _numero(base.get("odd"))
    if (
        odd is None
        or odd < ODD_MINIMA_DISPARO
        or not odd_elegivel(odd, obter_limites_risco())
    ):
        return []
    bloqueios = [
        item for item in base.get("bloqueios") or []
        if item not in _BLOQUEIOS_RELAXAVEIS
    ]
    if bloqueios:
        return []
    evidencias = _evidencias_tendencia(contexto)
    historico_gols = _historico_gols_forte(contexto, linha)
    atividade_recente = _atividade_recente_forte(base)
    if (
        len(evidencias) < EVIDENCIAS_MINIMAS
        or not historico_gols["aprovado"]
        or not atividade_recente["aprovado"]
    ):
        return []

    total_vermelhos = _total_vermelhos(contexto)
    item = copy.deepcopy(base)
    item["status"] = "simulacao"
    item["bloqueios"] = []
    item["pontuacao_tecnica"] = round(
        min(100.0, 78.0 + 4.0 * min(len(evidencias), 4)), 1
    )
    item["motivos"] = [
        "gol_ft_tendencia_15_ou_mais_mais_um",
        f"evidencias_tendencia={len(evidencias)}",
        f"vermelhos={total_vermelhos}",
    ]
    features = copy.deepcopy(item.get("features") or {})
    features["exploracao_sombra"] = {
        "versao": VERSAO,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
        "grupo_teste": False,
    }
    features["gol_ft_tendencia_mais_um"] = {
        "versao_politica": VERSAO_POLITICA,
        "linhagem_sha256": LINHAGEM,
        "placar_entrada": list(placar),
        "minuto_entrada": minuto,
        "linha_exigida": linha,
        "odd_minima_disparo": ODD_MINIMA_DISPARO,
        "tendencia_exigida": [TENDENCIA_MINIMA, None],
        "evidencias_tendencia": evidencias,
        "historico_gols_forte": historico_gols,
        "atividade_recente_forte": atividade_recente,
        "minuto_maximo_padrao": MINUTO_MAXIMO_PADRAO,
        "minuto_maximo_2_2": MINUTO_MAXIMO_2_2,
        "qualidade_minima": QUALIDADE_MINIMA,
        "cartao_vermelho_bloqueia": False,
        "cartoes_vermelhos_antes_entrada": total_vermelhos,
        "uma_exposicao_gol_por_partida": True,
        "rollback": "GOL_FT_TENDENCIA_MAIS_UM_GRUPO_ATIVO=0",
    }
    item["features"] = features
    return [item]
