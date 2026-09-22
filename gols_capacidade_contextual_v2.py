"""Challenger V2 de gols com histórico ampliado e estado contextual.

Esta versão é independente da V1, nasce apenas em sombra e não modifica
nenhuma regra ativa. A probabilidade é uma estimativa pré-calibração; a
promoção depende de coortes futuras separadas por tipo de competição.
"""

import copy
import hashlib
import inspect
import json
import math
import re
import time
import unicodedata
from pathlib import Path

from configuracao import odd_elegivel, obter_limites_risco
from qualidade_dados import extrair_minuto, extrair_placar


VERSAO_GOL_HT = "gol-ht-capacidade-contextual-v2b"
VERSAO_GOL_FT = "gol-ft-capacidade-contextual-v2b"
VERSOES = frozenset({VERSAO_GOL_HT, VERSAO_GOL_FT})
VERSAO_POLITICA = "gols-capacidade-contextual-politica-v2b"
VERSAO_CONTEXTO = "contexto-capacidade-times-v2"
MINUTO_MINIMO = 5
MINUTO_MAXIMO_HT = 28
MINUTO_MAXIMO_FT = 82
QUALIDADE_MINIMA = 80.0
HISTORICO_ALVO = 15
HISTORICO_MINIMO = 10
AMOSTRA_MANDO_MINIMA = 4
EDGE_MINIMO = 0.15
PROBABILIDADE_MINIMA = 0.58
TTL_HISTORICO_SEGUNDOS = 6 * 3600

_BLOQUEIOS_RELAXAVEIS = frozenset({
    "atividade_recente_insuficiente_gols",
    "historico_5min_insuficiente",
})
_FAIXAS = (
    ("0-15", 0, 15), ("16-30", 15, 30), ("31-45", 30, 45),
    ("46-60", 45, 60), ("61-75", 60, 75), ("76-90", 75, 90),
)


def _linhagem():
    pasta = Path(__file__).parent
    arquivos = (
        "gols_capacidade_contextual_v2.py",
        "contexto_pre_jogo.py",
        "qualidade_dados.py",
    )
    limites = obter_limites_risco()
    nucleo = {
        "versao": "linhagem-gols-capacidade-contextual-v2",
        "arquivos": {
            nome: hashlib.sha256((pasta / nome).read_bytes()).hexdigest()
            for nome in arquivos
        },
        "odd_elegivel": hashlib.sha256(
            inspect.getsource(odd_elegivel).encode("utf-8")
        ).hexdigest(),
        "faixa_odd": {
            "minima": float(limites.odd_minima),
            "maxima": float(limites.odd_maxima),
        },
        "historico_alvo": HISTORICO_ALVO,
        "edge_minimo": EDGE_MINIMO,
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


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).casefold()


def classificar_competicao(jogo):
    texto = _normalizar(" ".join((
        str((jogo or {}).get("mandante") or ""),
        str((jogo or {}).get("visitante") or ""),
        str((jogo or {}).get("liga") or ""),
    )))
    if re.search(r"\bu[\s-]?21\b|\bsub[\s-]?21\b", texto):
        return "sub21"
    if re.search(r"\bu[\s-]?23\b|\bsub[\s-]?23\b", texto):
        return "sub23"
    if any(token in texto for token in (
        "reserve", "reservas", "res.", "reserva league",
    )):
        return "reservas"
    if re.search(r"\bu[\s-]?(17|18|19|20)\b|\byouth\b|\bjunior", texto):
        return "base_outra"
    return "profissional"


def _resumir_partidas(itens, time_id, mando_alvo):
    linhas = []
    for item in itens or []:
        times = item.get("teams") or {}
        casa_id = ((times.get("home") or {}).get("id"))
        fora_id = ((times.get("away") or {}).get("id"))
        if time_id not in (casa_id, fora_id):
            continue
        gols = item.get("goals") or {}
        casa = time_id == casa_id
        pro = _numero(gols.get("home" if casa else "away"))
        contra = _numero(gols.get("away" if casa else "home"))
        if pro is None or contra is None:
            continue
        linhas.append({
            "em_casa": casa,
            "gols_pro": pro,
            "gols_contra": contra,
            "timestamp": _numero((item.get("fixture") or {}).get("timestamp")),
        })
    linhas.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
    linhas = linhas[:HISTORICO_ALVO]

    def metricas(amostra):
        if not amostra:
            return {
                "jogos": 0, "gols_pro_media": None,
                "gols_contra_media": None, "marcou_taxa": None,
                "sofreu_taxa": None, "over_1_5_taxa": None,
            }
        pesos = [0.93 ** indice for indice in range(len(amostra))]
        soma_pesos = sum(pesos)
        return {
            "jogos": len(amostra),
            "gols_pro_media": round(sum(
                x["gols_pro"] * peso for x, peso in zip(amostra, pesos)
            ) / soma_pesos, 4),
            "gols_contra_media": round(sum(
                x["gols_contra"] * peso for x, peso in zip(amostra, pesos)
            ) / soma_pesos, 4),
            "marcou_taxa": round(sum(x["gols_pro"] > 0 for x in amostra) / len(amostra), 4),
            "sofreu_taxa": round(sum(x["gols_contra"] > 0 for x in amostra) / len(amostra), 4),
            "over_1_5_taxa": round(sum(
                x["gols_pro"] + x["gols_contra"] > 1 for x in amostra
            ) / len(amostra), 4),
        }

    mando = [x for x in linhas if x["em_casa"] == bool(mando_alvo)]
    return {"geral": metricas(linhas), "mando": metricas(mando)}


def _medias_mando_temporada(raw, mando):
    gols = (raw or {}).get("goals") or {}
    chave = "home" if mando else "away"
    return {
        "gols_pro_media": _numero(
            (((gols.get("for") or {}).get("average") or {}).get(chave))
        ),
        "gols_contra_media": _numero(
            (((gols.get("against") or {}).get("average") or {}).get(chave))
        ),
        "jogos": _numero(
            ((((raw or {}).get("fixtures") or {}).get("played") or {}).get(chave))
        ),
    }


def coletar_contexto_capacidade_v2(api, confirmacao, contexto_base=None):
    """Amplia somente candidatos V2; usa o cache persistente da API."""
    confirmacao = confirmacao or {}
    times = confirmacao.get("times") or {}
    mandante_id = ((times.get("home") or {}).get("id"))
    visitante_id = ((times.get("away") or {}).get("id"))
    if not mandante_id or not visitante_id:
        return contexto_base
    prazo = time.monotonic() + 7.0
    recentes = {}
    for lado, time_id, mando in (
        ("mandante", mandante_id, True),
        ("visitante", visitante_id, False),
    ):
        itens = api._lista_contexto(
            f"contexto:v2:forma15:{time_id}",
            "/fixtures",
            {"team": time_id, "last": HISTORICO_ALVO, "status": "FT"},
            TTL_HISTORICO_SEGUNDOS,
            prazo,
        )
        recentes[lado] = _resumir_partidas(itens, time_id, mando)

    temporada_mando = {}
    liga = confirmacao.get("liga") or confirmacao.get("league") or {}
    liga_id, temporada = liga.get("id"), liga.get("season")
    if liga_id and temporada:
        for lado, time_id, mando in (
            ("mandante", mandante_id, True),
            ("visitante", visitante_id, False),
        ):
            raw = api._dados_contexto(
                f"contexto:time:{time_id}:{liga_id}:{temporada}",
                "/teams/statistics",
                {"team": time_id, "league": liga_id, "season": temporada},
                TTL_HISTORICO_SEGUNDOS,
                prazo,
            )
            temporada_mando[lado] = _medias_mando_temporada(raw, mando)

    destino = copy.deepcopy(contexto_base) if isinstance(contexto_base, dict) else {}
    destino["capacidade_times_v2"] = {
        "versao": VERSAO_CONTEXTO,
        "historico_alvo": HISTORICO_ALVO,
        "recentes": recentes,
        "temporada_mando": temporada_mando,
        "cobertura": {
            lado: {
                "historico_total": int(
                    ((recentes.get(lado) or {}).get("geral") or {}).get("jogos") or 0
                ),
                "historico_mando": int(
                    ((recentes.get(lado) or {}).get("mando") or {}).get("jogos") or 0
                ),
            }
            for lado in ("mandante", "visitante")
        },
    }
    return destino


def elegivel_para_enriquecimento_v2(jogo, qualidade=None, candidatos=None):
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    ausentes = set((qualidade or {}).get("campos_ausentes") or [])
    return bool(
        minuto is not None and placar is not None
        and MINUTO_MINIMO <= minuto <= MINUTO_MAXIMO_FT
        and (_numero((qualidade or {}).get("pontuacao")) or 0) >= QUALIDADE_MINIMA
        and not ausentes
        and (qualidade or {}).get("divergencia_critica") is not True
        and any(
            x.get("mercado") in {"gol_ht", "gol_ft"}
            and x.get("odd") is not None
            for x in candidatos or []
        )
    )


def _combinar_media(recentes, temporada):
    valores = []
    recente = _numero(recentes)
    temporada = _numero(temporada)
    if recente is not None:
        valores.append((recente, 0.65))
    if temporada is not None:
        valores.append((temporada, 0.35))
    if not valores:
        return None
    soma_pesos = sum(peso for _, peso in valores)
    return sum(valor * peso for valor, peso in valores) / soma_pesos


def _fracao_intervalo(distribuicao, inicio, fim):
    total = 0.0
    encontrou = False
    for faixa, a, b in _FAIXAS:
        percentual = _numero(((distribuicao or {}).get(faixa) or {}).get("percentual"))
        if percentual is None:
            continue
        sobreposicao = max(0.0, min(float(fim), b) - max(float(inicio), a))
        if sobreposicao:
            total += percentual / 100.0 * sobreposicao / (b - a)
            encontrou = True
    return total if encontrou else None


def _fracao_restante(contexto, minuto, fim):
    temporada = (contexto or {}).get("estatisticas_temporada") or {}
    fracoes = []
    for lado in ("mandante", "visitante"):
        item = temporada.get(lado) or {}
        for chave in ("gols_pro_por_minuto", "gols_contra_por_minuto"):
            valor = _fracao_intervalo(item.get(chave), minuto, fim)
            if valor is not None:
                fracoes.append(valor)
    if fracoes:
        return sum(fracoes) / len(fracoes), "distribuicao_temporada"
    return max(fim - minuto, 0) / float(fim), "relogio"


def _historico_valido(contexto_v2):
    recentes = (contexto_v2 or {}).get("recentes") or {}
    for lado in ("mandante", "visitante"):
        geral = (recentes.get(lado) or {}).get("geral") or {}
        mando = (recentes.get(lado) or {}).get("mando") or {}
        if int(geral.get("jogos") or 0) < HISTORICO_MINIMO:
            return False
        if int(mando.get("jogos") or 0) < AMOSTRA_MANDO_MINIMA:
            return False
    return True


def _modelo_historico(contexto, minuto, fim, placar):
    v2 = (contexto or {}).get("capacidade_times_v2") or {}
    if not _historico_valido(v2):
        return None
    recentes = v2.get("recentes") or {}
    temporada = v2.get("temporada_mando") or {}
    casa = ((recentes.get("mandante") or {}).get("mando") or {})
    fora = ((recentes.get("visitante") or {}).get("mando") or {})
    casa_temp = temporada.get("mandante") or {}
    fora_temp = temporada.get("visitante") or {}
    ataque_casa = _combinar_media(casa.get("gols_pro_media"), casa_temp.get("gols_pro_media"))
    defesa_casa = _combinar_media(casa.get("gols_contra_media"), casa_temp.get("gols_contra_media"))
    ataque_fora = _combinar_media(fora.get("gols_pro_media"), fora_temp.get("gols_pro_media"))
    defesa_fora = _combinar_media(fora.get("gols_contra_media"), fora_temp.get("gols_contra_media"))
    if any(x is None for x in (ataque_casa, defesa_casa, ataque_fora, defesa_fora)):
        return None
    lambda_casa = (ataque_casa + defesa_fora) / 2.0
    lambda_fora = (ataque_fora + defesa_casa) / 2.0
    # Contrai extremos de bases/juvenis antes de calcular o tempo restante.
    lambda_casa = 0.75 * lambda_casa + 0.25 * 1.25
    lambda_fora = 0.75 * lambda_fora + 0.25 * 1.25
    diferenca = abs(int(placar[0]) - int(placar[1]))
    multiplicador_placar = {0: 1.0, 1: 0.90, 2: 0.78}.get(diferenca, 0.60)
    if sum(placar) >= 4:
        multiplicador_placar *= 0.85
    fracao, metodo_tempo = _fracao_restante(contexto, minuto, fim)
    lambda_restante = (lambda_casa + lambda_fora) * fracao * multiplicador_placar
    return {
        "lambda_casa_jogo": round(lambda_casa, 4),
        "lambda_fora_jogo": round(lambda_fora, 4),
        "lambda_restante_base": round(lambda_restante, 4),
        "fracao_restante": round(fracao, 4),
        "metodo_tempo": metodo_tempo,
        "multiplicador_placar": round(multiplicador_placar, 4),
        "diferenca_placar": diferenca,
        "amostra_casa_total": int((((recentes.get("mandante") or {}).get("geral") or {}).get("jogos") or 0)),
        "amostra_casa_mando": int(casa.get("jogos") or 0),
        "amostra_fora_total": int((((recentes.get("visitante") or {}).get("geral") or {}).get("jogos") or 0)),
        "amostra_fora_mando": int(fora.get("jogos") or 0),
        "ataque_casa": round(ataque_casa, 4),
        "defesa_fora": round(defesa_fora, 4),
        "ataque_fora": round(ataque_fora, 4),
        "defesa_casa": round(defesa_casa, 4),
    }


def _somar_par(valor):
    if isinstance(valor, (list, tuple)):
        return sum(_numero(x) or 0 for x in valor)
    return _numero(valor) or 0


def _evidencia_recente(base, contexto, qualidade=None):
    features = base.get("features") or {}
    janela_pack = ((features.get("janelas") or {}).get("5") or {})
    temporal = ((contexto or {}).get("evolucao_temporal_api_live") or {}).get("5")
    temporal = temporal if isinstance(temporal, dict) else {}
    auditoria_lista = (
        (qualidade or {}).get("auditoria_indicadores_temporais_lista") or {}
    )
    janela_lista = (
        ((auditoria_lista.get("janelas") or {}).get("5")) or {}
    )
    idade_lista = _numero(auditoria_lista.get("idade_segundos"))
    lista_valida = bool(
        isinstance(janela_lista, dict)
        and janela_lista
        and (idade_lista is None or idade_lista <= 240.0)
    )
    duracao_pack = _numero(janela_pack.get("duracao_real_minutos"))
    duracao_api = _numero(temporal.get("duracao_real_minutos"))
    pack_valido = janela_pack.get("disponivel") is True and (
        duracao_pack is None or duracao_pack <= 8.0
    )
    api_valido = bool(temporal) and (duracao_api is None or duracao_api <= 8.0)
    chutes_pack = _numero(janela_pack.get("chutes_total")) if pack_valido else None
    chutes_api = _somar_par(temporal.get("chutes")) if api_valido else None
    chutes_lista = (
        _somar_par(janela_lista.get("chutes")) if lista_valida else None
    )
    chutes = max(
        x for x in (chutes_pack, chutes_api, chutes_lista) if x is not None
    ) if any(
        x is not None for x in (chutes_pack, chutes_api, chutes_lista)
    ) else None
    xg_5 = _somar_par(temporal.get("xg")) if api_valido and temporal.get("xg") is not None else None
    picos = janela_pack.get("pressao_pico") if pack_valido else None
    if not isinstance(picos, (list, tuple)):
        picos = [picos] if picos is not None else []
    pressao_pack = (
        max([_numero(x) or 0 for x in picos] or [0])
        if pack_valido else None
    )
    pressao_lista = (
        max(
            [_numero(x) or 0 for x in (janela_lista.get("pressao") or [])]
            or [0]
        ) if lista_valida else None
    )
    pressao = max(
        x for x in (pressao_pack, pressao_lista) if x is not None
    ) if any(
        x is not None for x in (pressao_pack, pressao_lista)
    ) else None
    expectativa_gols_5 = (
        _somar_par(janela_lista.get("expectativa_gols"))
        if lista_valida else None
    )
    tendencias = janela_pack.get("pressao_tendencia") if pack_valido else []
    if not isinstance(tendencias, (list, tuple)):
        tendencias = [tendencias]
    tendencia = max([_numero(x) or 0 for x in tendencias] or [0]) if pack_valido else None
    evidencias = []
    if chutes is not None and chutes >= 2:
        evidencias.append("chutes_5min")
    if xg_5 is not None and xg_5 >= 0.08:
        evidencias.append("xg_5min")
    if pressao is not None and pressao >= 50:
        evidencias.append("pressao_5min")
    if expectativa_gols_5 is not None and expectativa_gols_5 >= 0.35:
        evidencias.append("expectativa_gols_5min")
    forte = bool(
        (chutes is not None and chutes >= 3)
        or (xg_5 is not None and xg_5 >= 0.15)
        or (pressao is not None and pressao >= 65)
        or (
            expectativa_gols_5 is not None
            and expectativa_gols_5 >= 0.50
        )
    )
    return {
        "evidencias": evidencias,
        "forte": forte,
        "chutes_5min": chutes,
        "xg_5min": xg_5,
        "expectativa_gols_5min": expectativa_gols_5,
        "pressao_5min": pressao,
        "tendencia_pressao_5min": tendencia,
        "packball_valido": pack_valido,
        "api_temporal_valida": api_valido,
        "scanner_temporal_valido": lista_valida,
        "idade_scanner_segundos": idade_lista,
    }


def _estado_eventos(contexto, minuto):
    eventos = (contexto or {}).get("eventos_ao_vivo") or {}
    times = eventos.get("times") or {}
    vermelhos = sum(int((times.get(lado) or {}).get("cartoes_vermelhos") or 0) for lado in ("mandante", "visitante"))
    substituicoes = sum(int((times.get(lado) or {}).get("substituicoes") or 0) for lado in ("mandante", "visitante"))
    criticos = eventos.get("eventos_criticos_recentes") or []
    criticos_10 = [
        x for x in criticos
        if _numero(x.get("minuto")) is not None
        and 0 <= minuto - float(x["minuto"]) <= 10
    ]
    return {
        "cartoes_vermelhos": vermelhos,
        "substituicoes": substituicoes,
        "eventos_criticos_10min": len(criticos_10),
    }


def _movimento_odd_confiavel(base):
    movimento = ((base.get("features") or {}).get("movimento_gols"))
    if not isinstance(movimento, dict):
        return {"disponivel": False}
    atual = _numero(movimento.get("odd_atual"))
    odd = _numero(base.get("odd"))
    delta = _numero(movimento.get("delta"))
    if atual is None or odd is None or delta is None or abs(atual - odd) > 0.15:
        return {"disponivel": False, "motivo": "movimento_nao_comparavel"}
    return {
        "disponivel": True,
        "direcao": str(movimento.get("direcao") or "").casefold(),
        "delta": round(delta, 4),
        "odd_anterior": _numero(movimento.get("odd_anterior")),
        "odd_atual": atual,
    }


def _gerar_item(base, versao, segmento, modelo, recente, eventos, movimento, prob, edge, minuto, fim):
    bloqueios = [
        x for x in base.get("bloqueios") or [] if x not in _BLOQUEIOS_RELAXAVEIS
    ]
    if bloqueios:
        return None
    item = copy.deepcopy(base)
    item["status"] = "simulacao"
    item["bloqueios"] = []
    item["pontuacao_tecnica"] = round(min(100.0, 60.0 + edge * 100.0), 1)
    item["motivos"] = [
        "challenger_contextual_v2",
        f"segmento={segmento}",
        f"edge_estimado_nao_calibrado={edge:.4f}",
    ]
    features = copy.deepcopy(item.get("features") or {})
    features["exploracao_sombra"] = {
        "versao": versao,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
        "grupo_teste": False,
    }
    features["gol_capacidade_contextual_v2"] = {
        "versao_politica": VERSAO_POLITICA,
        "linhagem_sha256": LINHAGEM,
        "segmento_competicao": segmento,
        "modelo_historico": modelo,
        "evidencia_recente": recente,
        "estado_eventos": eventos,
        "movimento_odd": movimento,
        "probabilidade_estimada_nao_calibrada": round(prob, 4),
        "probabilidade_implicita_odd": round(1.0 / float(item["odd"]), 4),
        "edge_estimado_nao_calibrado": round(edge, 4),
        "minuto": minuto,
        "fim_mercado": fim,
        "linha_mais_um_gol": True,
        "uma_exposicao_gol_por_partida": True,
        "somente_sombra": True,
    }
    item["features"] = features
    return item


def gerar_gols_capacidade_contextual_v2(jogo, candidatos, contexto, qualidade):
    if not elegivel_para_enriquecimento_v2(jogo, qualidade, candidatos):
        return []
    minuto = extrair_minuto(jogo.get("status"))
    placar = extrair_placar(jogo.get("placar"))
    segmento = classificar_competicao(jogo)
    por_mercado = {
        x.get("mercado"): x for x in candidatos or []
        if x.get("mercado") in {"gol_ht", "gol_ft"}
        and not ((x.get("features") or {}).get("exploracao_sombra"))
    }
    resultado = []
    for mercado, versao, fim, limite in (
        ("gol_ht", VERSAO_GOL_HT, 45, MINUTO_MAXIMO_HT),
        ("gol_ft", VERSAO_GOL_FT, 90, MINUTO_MAXIMO_FT),
    ):
        base = por_mercado.get(mercado)
        if base is None or minuto > limite:
            continue
        try:
            linha, odd = float(base.get("linha")), float(base.get("odd"))
        except (TypeError, ValueError):
            continue
        if linha != sum(placar) + 0.5 or not odd_elegivel(odd, obter_limites_risco()):
            continue
        # Na coorte V1, a linha 0.5 HT fez 2 green/6 red (ROI -52,3%).
        # Esta nova hipótese é pré-registrada apenas para linhas a partir de
        # 1.5; a coleta continua prospectiva e não promove a regra.
        if mercado == "gol_ht" and linha < 1.5:
            continue
        modelo = _modelo_historico(contexto, minuto, fim, placar)
        if modelo is None:
            continue
        recente = _evidencia_recente(base, contexto, qualidade)
        if len(recente["evidencias"]) < 2:
            continue
        if mercado == "gol_ht" and not recente["forte"]:
            continue
        eventos = _estado_eventos(contexto, minuto)
        if eventos["cartoes_vermelhos"]:
            continue
        movimento = _movimento_odd_confiavel(base)
        if (
            movimento.get("disponivel")
            and movimento.get("direcao") in {"alta", "subida"}
            and float(movimento.get("delta") or 0) >= 0.10
        ):
            continue
        multiplicador_live = 1.0
        if (recente.get("chutes_5min") or 0) >= 3:
            multiplicador_live *= 1.06
        if (recente.get("xg_5min") or 0) >= 0.15:
            multiplicador_live *= 1.08
        if (recente.get("pressao_5min") or 0) >= 65:
            multiplicador_live *= 1.06
        if recente.get("tendencia_pressao_5min") is not None and recente["tendencia_pressao_5min"] < 0:
            multiplicador_live *= 0.94
        if eventos["substituicoes"] >= 4 and minuto >= 65:
            multiplicador_live *= 0.92
        if movimento.get("disponivel") and movimento.get("direcao") == "queda":
            multiplicador_live *= 1.03
        lambda_final = modelo["lambda_restante_base"] * multiplicador_live
        prob = 1.0 - math.exp(-max(lambda_final, 0.0))
        edge = prob - 1.0 / odd
        if prob < PROBABILIDADE_MINIMA or edge < EDGE_MINIMO:
            continue
        modelo = {
            **modelo,
            "multiplicador_live": round(multiplicador_live, 4),
            "lambda_restante_final": round(lambda_final, 4),
        }
        item = _gerar_item(
            base, versao, segmento, modelo, recente, eventos,
            movimento, prob, edge, minuto, fim,
        )
        if item is not None:
            resultado.append(item)
    return resultado
