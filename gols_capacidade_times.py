"""Rota prospectiva de gols baseada na capacidade histórica dos times.

Não substitui as regras live. Ela estima a chance de pelo menos mais um gol
com ataque/defesa, forma, H2H e distribuição por minuto, compara essa chance
com a odd atual e mantém a decisão rastreável em uma coorte independente.
"""

import copy
import hashlib
import inspect
import json
import math
import os
from pathlib import Path

from configuracao import odd_elegivel, obter_limites_risco
from qualidade_dados import extrair_minuto, extrair_placar


VERSAO_GOL_HT_CAPACIDADE = "gol-ht-capacidade-times-poisson-v1"
VERSAO_GOL_FT_CAPACIDADE = "gol-ft-capacidade-times-poisson-v1"
VERSOES_GOLS_CAPACIDADE = frozenset({
    VERSAO_GOL_HT_CAPACIDADE,
    VERSAO_GOL_FT_CAPACIDADE,
})
VERSAO_POLITICA = "gols-capacidade-times-valor-v1"
MINUTO_MINIMO = 5
MINUTO_MAXIMO_HT = 28
MINUTO_MAXIMO_FT = 82
QUALIDADE_MINIMA = 70.0
JOGOS_MINIMOS = 5
EDGE_MINIMO_COM_LIVE = 0.05
EDGE_MINIMO_SEM_LIVE = 0.10
PROBABILIDADE_MINIMA = 0.52
MEDIA_GOLS_TIME_NEUTRA = 1.25
FORCA_PRIOR_NEUTRO = 8.0

_BLOQUEIOS_RELAXAVEIS = frozenset({
    "atividade_recente_insuficiente_gols",
    "historico_5min_insuficiente",
})
_FAIXAS = (
    ("0-15", 0, 15),
    ("16-30", 15, 30),
    ("31-45", 30, 45),
    ("46-60", 45, 60),
    ("61-75", 60, 75),
    ("76-90", 75, 90),
)


def _calcular_linhagem():
    pasta = Path(__file__).parent
    arquivos = (
        "gols_capacidade_times.py",
        "contexto_pre_jogo.py",
        "qualidade_dados.py",
    )
    nucleo = {
        "versao": "linhagem-gols-capacidade-times-v1",
        "arquivos": {
            nome: hashlib.sha256((pasta / nome).read_bytes()).hexdigest()
            for nome in arquivos
        },
        "odd_elegivel": hashlib.sha256(
            inspect.getsource(odd_elegivel).encode("utf-8")
        ).hexdigest(),
        "faixa_odd": {
            "minima": float(obter_limites_risco().odd_minima),
            "maxima": float(obter_limites_risco().odd_maxima),
        },
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


LINHAGEM_GOLS_CAPACIDADE = _calcular_linhagem()


def gols_capacidade_grupo_ativo(env=None):
    env = os.environ if env is None else env
    return env.get("GOLS_CAPACIDADE_TIMES_GRUPO_ATIVO", "1") == "1"


def _numero(valor):
    if isinstance(valor, str):
        valor = valor.strip().replace("%", "").replace(",", ".")
    try:
        numero = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
    return numero if numero is not None and math.isfinite(numero) else None


def _media_ponderada(fontes, campo):
    numerador = denominador = 0.0
    amostras = 0
    for fonte, peso_maximo in fontes:
        jogos = _numero((fonte or {}).get("jogos"))
        valor = _numero((fonte or {}).get(campo))
        if jogos is None or jogos <= 0 or valor is None:
            continue
        peso = min(jogos, peso_maximo)
        numerador += valor * peso
        denominador += peso
        amostras = max(amostras, int(jogos))
    return (
        numerador / denominador if denominador else None,
        amostras,
    )


def _perfil_time(contexto, lado):
    forma = ((contexto.get("forma_recente") or {}).get(lado) or {})
    temporada = (
        (contexto.get("estatisticas_temporada") or {}).get(lado) or {}
    )
    historico = (
        (contexto.get("historico_detalhado") or {}).get(lado) or {}
    )
    fontes = ((temporada, 20), (historico, 10), (forma, 5))
    gols_pro, jogos_pro = _media_ponderada(fontes, "gols_pro_media")
    gols_contra, jogos_contra = _media_ponderada(
        fontes, "gols_contra_media"
    )
    # As fontes historicas se sobrepoem (forma e historico podem conter os
    # mesmos jogos). A contracao evita tratar uma amostra curta como verdade
    # absoluta e reduz falsos positivos em copas/base e ligas pouco cobertas.
    jogos = max(jogos_pro, jogos_contra)
    credibilidade = jogos / (jogos + FORCA_PRIOR_NEUTRO) if jogos else 0.0
    gols_pro_ajustada = (
        credibilidade * gols_pro
        + (1.0 - credibilidade) * MEDIA_GOLS_TIME_NEUTRA
        if gols_pro is not None else None
    )
    gols_contra_ajustada = (
        credibilidade * gols_contra
        + (1.0 - credibilidade) * MEDIA_GOLS_TIME_NEUTRA
        if gols_contra is not None else None
    )
    return {
        "gols_pro_media": gols_pro_ajustada,
        "gols_contra_media": gols_contra_ajustada,
        "gols_pro_media_bruta": gols_pro,
        "gols_contra_media_bruta": gols_contra,
        "jogos": jogos,
        "credibilidade": credibilidade,
        "gols_pro_por_minuto": temporada.get("gols_pro_por_minuto") or {},
        "gols_contra_por_minuto": (
            temporada.get("gols_contra_por_minuto") or {}
        ),
    }


def _fracao_intervalo(distribuicao, inicio, fim):
    parcelas = []
    for faixa, limite_inicio, limite_fim in _FAIXAS:
        item = (distribuicao or {}).get(faixa) or {}
        percentual = _numero(item.get("percentual"))
        if percentual is None:
            continue
        sobreposicao = max(
            0.0, min(float(fim), limite_fim) - max(float(inicio), limite_inicio)
        )
        if sobreposicao:
            parcelas.append(
                percentual / 100.0 * sobreposicao / (limite_fim - limite_inicio)
            )
    return sum(parcelas) if parcelas else None


def _fracao_gols_restantes(time, rival, minuto, fim):
    fracoes = [
        _fracao_intervalo(time.get("gols_pro_por_minuto"), minuto, fim),
        _fracao_intervalo(rival.get("gols_contra_por_minuto"), minuto, fim),
    ]
    fracoes = [valor for valor in fracoes if valor is not None]
    if fracoes:
        return sum(fracoes) / len(fracoes), "distribuicao_por_minuto"
    return max(float(fim) - float(minuto), 0.0) / 90.0, "fracao_relogio"


def _modelo_capacidade(contexto, minuto, fim):
    contexto = contexto or {}
    mandante = _perfil_time(contexto, "mandante")
    visitante = _perfil_time(contexto, "visitante")
    if min(mandante["jogos"], visitante["jogos"]) < JOGOS_MINIMOS:
        return None
    valores = (
        mandante["gols_pro_media"], mandante["gols_contra_media"],
        visitante["gols_pro_media"], visitante["gols_contra_media"],
    )
    if any(valor is None for valor in valores):
        return None
    lambda_mandante = (
        mandante["gols_pro_media"] + visitante["gols_contra_media"]
    ) / 2.0
    lambda_visitante = (
        visitante["gols_pro_media"] + mandante["gols_contra_media"]
    ) / 2.0
    h2h = contexto.get("confrontos_diretos") or {}
    h2h_jogos = int(_numero(h2h.get("jogos")) or 0)
    h2h_media = _numero(h2h.get("media_gols"))
    lambda_total = lambda_mandante + lambda_visitante
    if h2h_jogos >= 3 and h2h_media is not None:
        lambda_total = 0.85 * lambda_total + 0.15 * h2h_media
        escala = lambda_total / max(
            lambda_mandante + lambda_visitante, 0.01
        )
        lambda_mandante *= escala
        lambda_visitante *= escala
    fracao_mandante, metodo_mandante = _fracao_gols_restantes(
        mandante, visitante, minuto, fim
    )
    fracao_visitante, metodo_visitante = _fracao_gols_restantes(
        visitante, mandante, minuto, fim
    )
    lambda_restante = (
        lambda_mandante * fracao_mandante
        + lambda_visitante * fracao_visitante
    )
    probabilidade = 1.0 - math.exp(-max(lambda_restante, 0.0))
    return {
        "lambda_mandante_jogo": round(lambda_mandante, 4),
        "lambda_visitante_jogo": round(lambda_visitante, 4),
        "lambda_total_jogo": round(lambda_total, 4),
        "lambda_restante": round(lambda_restante, 4),
        "probabilidade_mais_um_gol": round(probabilidade, 4),
        "fracao_restante_mandante": round(fracao_mandante, 4),
        "fracao_restante_visitante": round(fracao_visitante, 4),
        "metodo_temporal_mandante": metodo_mandante,
        "metodo_temporal_visitante": metodo_visitante,
        "jogos_mandante": mandante["jogos"],
        "jogos_visitante": visitante["jogos"],
        "credibilidade_mandante": round(mandante["credibilidade"], 4),
        "credibilidade_visitante": round(visitante["credibilidade"], 4),
        "ataque_mandante": round(mandante["gols_pro_media"], 4),
        "ataque_visitante": round(visitante["gols_pro_media"], 4),
        "defesa_mandante_sofridos": round(
            mandante["gols_contra_media"], 4
        ),
        "defesa_visitante_sofridos": round(
            visitante["gols_contra_media"], 4
        ),
        "h2h_jogos": h2h_jogos,
        "h2h_media_gols": h2h_media,
    }


def _evidencias_live(candidato, contexto, qualidade):
    features = candidato.get("features") or {}
    janela5 = ((features.get("janelas") or {}).get("5") or {})
    evidencias = []
    if (_numero(janela5.get("chutes_total")) or 0) >= 1:
        evidencias.append("chute_recente")
    if (_numero(features.get("chutes_no_gol_total")) or 0) >= 1:
        evidencias.append("chute_no_gol_partida")
    live = ((contexto or {}).get("estatisticas_ao_vivo") or {}).get(
        "times"
    ) or {}
    xg_total = sum(
        _numero((live.get(lado) or {}).get("xg")) or 0
        for lado in ("mandante", "visitante")
    )
    if xg_total >= 0.12:
        evidencias.append("xg_ao_vivo")
    pressao_ausente = "Índice de pressão" in set(
        (qualidade or {}).get("campos_ausentes") or []
    )
    picos = janela5.get("pressao_pico") or []
    if not isinstance(picos, (list, tuple)):
        picos = [picos]
    pico = max([_numero(valor) or 0 for valor in picos] or [0])
    if not pressao_ausente and pico >= 50:
        evidencias.append("pressao_observada")
    return evidencias, round(xg_total, 4), pressao_ausente, round(pico, 2)


def elegivel_para_enriquecimento_capacidade(
    jogo, qualidade=None, candidatos=None
):
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    nota = _numero((qualidade or {}).get("pontuacao")) or 0
    ausentes = set((qualidade or {}).get("campos_ausentes") or [])
    odds_presentes = any(
        item.get("mercado") in {"gol_ht", "gol_ft"}
        and item.get("odd") is not None
        for item in candidatos or []
    )
    return bool(
        minuto is not None and placar is not None
        and MINUTO_MINIMO <= minuto <= MINUTO_MAXIMO_FT
        and nota >= QUALIDADE_MINIMA
        and not ausentes
        and (qualidade or {}).get("divergencia_critica") is not True
        and odds_presentes
    )


def _clonar_candidato(
    base, versao, modelo, edge, evidencias_live, xg_total,
    pressao_ausente, pico_pressao, minuto, fim,
):
    bloqueios = [
        motivo for motivo in base.get("bloqueios") or []
        if motivo not in _BLOQUEIOS_RELAXAVEIS
    ]
    if bloqueios:
        return None
    item = copy.deepcopy(base)
    item["status"] = "simulacao"
    item["bloqueios"] = []
    item["pontuacao_tecnica"] = round(min(
        100.0,
        65.0 + edge * 100.0 + min(len(evidencias_live), 3) * 3.0,
    ), 1)
    item["motivos"] = [
        "capacidade_historica_dos_times",
        "valor_probabilidade_versus_odd",
        f"edge_estimado={edge:.4f}",
    ]
    features = copy.deepcopy(item.get("features") or {})
    features["exploracao_sombra"] = {
        "versao": versao,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
        "grupo_teste": gols_capacidade_grupo_ativo(),
    }
    features["gol_capacidade_times"] = {
        "versao_politica": VERSAO_POLITICA,
        "linhagem_sha256": LINHAGEM_GOLS_CAPACIDADE,
        "modelo": modelo,
        "odd": float(item["odd"]),
        "probabilidade_implicita_odd": round(1.0 / float(item["odd"]), 4),
        "edge_estimado": round(edge, 4),
        "minuto": minuto,
        "fim_mercado": fim,
        "evidencias_ao_vivo": list(evidencias_live),
        "xg_ao_vivo_total": xg_total,
        "pressao_ausente": pressao_ausente,
        "pico_pressao_observado": pico_pressao,
        "permite_pressao_ausente": False,
        "permite_pressao_baixa": True,
        "somente_coorte_prospectiva": True,
    }
    item["features"] = features
    return item


def gerar_gols_capacidade_times(
    jogo, candidatos, contexto_pre_jogo, qualidade
):
    if not elegivel_para_enriquecimento_capacidade(
        jogo, qualidade, candidatos
    ) or not isinstance(contexto_pre_jogo, dict):
        return []
    minuto = extrair_minuto(jogo.get("status"))
    placar = extrair_placar(jogo.get("placar"))
    gols_atuais = sum(placar)
    por_mercado = {
        item.get("mercado"): item for item in candidatos or []
        if item.get("mercado") in {"gol_ht", "gol_ft"}
    }
    resultado = []
    for mercado, versao, fim, minuto_maximo in (
        ("gol_ht", VERSAO_GOL_HT_CAPACIDADE, 45, MINUTO_MAXIMO_HT),
        ("gol_ft", VERSAO_GOL_FT_CAPACIDADE, 90, MINUTO_MAXIMO_FT),
    ):
        base = por_mercado.get(mercado)
        if base is None or minuto > minuto_maximo:
            continue
        # A rota adicional existe para recuperar oportunidades que a regra
        # live não aprovou; nunca duplica nem compete com um sinal já ativo.
        if base.get("status") == "aprovado" and not base.get("bloqueios"):
            continue
        try:
            linha = float(base.get("linha"))
            odd = float(base.get("odd"))
        except (TypeError, ValueError):
            continue
        if linha != gols_atuais + 0.5 or not odd_elegivel(
            odd, obter_limites_risco()
        ):
            continue
        modelo = _modelo_capacidade(contexto_pre_jogo, minuto, fim)
        if modelo is None:
            continue
        probabilidade = modelo["probabilidade_mais_um_gol"]
        edge = probabilidade - 1.0 / odd
        evidencias, xg_total, pressao_ausente, pico = _evidencias_live(
            base, contexto_pre_jogo, qualidade
        )
        edge_minimo = (
            EDGE_MINIMO_COM_LIVE if evidencias
            else EDGE_MINIMO_SEM_LIVE
        )
        if probabilidade < PROBABILIDADE_MINIMA or edge < edge_minimo:
            continue
        item = _clonar_candidato(
            base, versao, modelo, edge, evidencias, xg_total,
            pressao_ausente, pico, minuto, fim,
        )
        if item is not None:
            resultado.append(item)
    return resultado
