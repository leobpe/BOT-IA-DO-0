"""Adaptacao e normalizacao isoladas da TheStatsAPI.

Este modulo existe somente para comparar a nova fonte com o PackBall e com a
API-Football. Ele nao envia Telegram, nao alimenta calibracao e nao autoriza
sinais. A promocao para uso operacional exige avaliacao prospectiva separada.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
import re
import unicodedata

from api_football import (
    MARGEM_MINIMA_ASSOCIACAO,
    diagnosticar_associacao,
)


FONTE = "thestatsapi"
APLICACAO_SINAIS = False

_ID_PARTIDA_RE = re.compile(r"^mt_[A-Za-z0-9_-]+$")
_SUFIXOS_CLUBE = {"fc", "cf", "sc"}

_METRICAS_LIVE = {
    "total_shots": "chutes",
    "shots_on_target": "chutes_gol",
    "corner_kicks": "escanteios",
    "expected_goals": "xg",
}


def _desembrulhar_resposta(resposta):
    """Aceita tanto o JSON do provedor quanto a resposta do cliente local."""
    if not isinstance(resposta, dict):
        return resposta
    if resposta.get("ok") is False:
        return None
    if "dados" in resposta:
        return resposta.get("dados")
    if "data" in resposta:
        return resposta.get("data")
    return resposta


def _texto_sem_acentos(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )


def _nome_para_pareamento(nome):
    """Remove apenas afixos societarios, preservando W e categorias Uxx."""
    original = str(nome or "").strip()
    tokens = re.findall(r"[A-Za-z0-9]+", _texto_sem_acentos(original))
    while len(tokens) > 1 and tokens[0].casefold() == "club":
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1].casefold() in _SUFIXOS_CLUBE:
        tokens.pop()
    return " ".join(tokens) or original


def _numero(valor, *, inteiro=False):
    if valor is None or isinstance(valor, bool):
        return None
    texto = str(valor).strip().replace("%", "").replace(",", ".")
    if not texto:
        return None
    try:
        numero = float(texto)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numero) or numero < 0:
        return None
    if inteiro and numero.is_integer():
        return int(numero)
    return round(numero, 4)


def _inteiro_minuto(valor):
    numero = _numero(valor)
    return int(numero) if numero is not None else None


def _valor_lado(bloco, lado):
    if not isinstance(bloco, dict):
        return None
    valor = bloco.get(lado)
    if isinstance(valor, dict):
        for chave in ("current", "total", "value", "goals"):
            if chave in valor:
                return valor.get(chave)
        return None
    return valor


def _status_para_fixture(item):
    bruto = item.get("status")
    status_texto = (
        str(bruto.get("name") or bruto.get("short") or "")
        if isinstance(bruto, dict)
        else str(bruto or "")
    ).strip().casefold().replace("-", "_").replace(" ", "_")
    mapa = {
        "first_half": "1H",
        "1st_half": "1H",
        "second_half": "2H",
        "2nd_half": "2H",
        "half_time": "HT",
        "halftime": "HT",
        "finished": "FT",
        "full_time": "FT",
        "not_started": "NS",
        "scheduled": "NS",
        "live": "LIVE",
    }
    minuto = item.get("elapsed_minutes")
    if minuto is None:
        minuto = item.get("minute")
    if minuto is None and isinstance(bruto, dict):
        minuto = bruto.get("elapsed") or bruto.get("elapsed_minutes")
    if minuto is None and isinstance(item.get("clock"), dict):
        minuto = item["clock"].get("elapsed")
    return {
        "short": mapa.get(status_texto, status_texto.upper() or None),
        "long": str(
            bruto.get("name") if isinstance(bruto, dict) else bruto or ""
        ).strip() or None,
        "elapsed": _inteiro_minuto(minuto),
    }


def _extrair_lista_partidas(resposta):
    dados = _desembrulhar_resposta(resposta)
    if isinstance(dados, list):
        return dados
    if isinstance(dados, dict):
        for chave in ("matches", "items", "results"):
            if isinstance(dados.get(chave), list):
                return dados[chave]
    return []


def adaptar_lista_thestatsapi_para_associador(resposta):
    """Converte a lista real da TheStatsAPI ao contrato do associador atual.

    Os nomes usados na comparacao perdem apenas ``Club`` no inicio e
    ``FC/CF/SC`` no fim. O nome original permanece junto do time e e restaurado
    no diagnostico devolvido ao chamador.
    """
    adaptadas = []
    for item in _extrair_lista_partidas(resposta):
        if not isinstance(item, dict):
            continue
        match_id = str(item.get("id") or item.get("match_id") or "").strip()
        if not _ID_PARTIDA_RE.fullmatch(match_id):
            continue
        casa = item.get("home_team") or {}
        fora = item.get("away_team") or {}
        nome_casa = str(casa.get("name") or "").strip()
        nome_fora = str(fora.get("name") or "").strip()
        if not nome_casa or not nome_fora:
            continue
        placar = item.get("score") or {}
        gols_casa = _numero(_valor_lado(placar, "home"), inteiro=True)
        gols_fora = _numero(_valor_lado(placar, "away"), inteiro=True)
        fixture = {
            "fixture": {
                "id": match_id,
                "status": _status_para_fixture(item),
            },
            "teams": {
                "home": {
                    "id": casa.get("id"),
                    "name": _nome_para_pareamento(nome_casa),
                    "name_original": nome_casa,
                },
                "away": {
                    "id": fora.get("id"),
                    "name": _nome_para_pareamento(nome_fora),
                    "name_original": nome_fora,
                },
            },
            "goals": {"home": gols_casa, "away": gols_fora},
            "league": {
                "id": item.get("competition_id"),
                "season_id": item.get("season_id"),
                "name": item.get("competition_name"),
            },
            "_thestatsapi_original": item,
        }
        adaptadas.append(fixture)
    return adaptadas


def diagnosticar_associacao_thestatsapi(
    jogo_packball,
    resposta_lista,
    margem_minima=MARGEM_MINIMA_ASSOCIACAO,
):
    """Pareia somente com a validacao profissional ja usada pelo monitor."""
    adaptadas = adaptar_lista_thestatsapi_para_associador(resposta_lista)
    jogo = dict(jogo_packball or {})
    jogo["mandante"] = _nome_para_pareamento(jogo.get("mandante"))
    jogo["visitante"] = _nome_para_pareamento(jogo.get("visitante"))
    diagnostico = diagnosticar_associacao(
        jogo,
        adaptadas,
        margem_minima=max(float(margem_minima), MARGEM_MINIMA_ASSOCIACAO),
    )
    diagnostico = dict(diagnostico)
    associacao = diagnostico.get("associacao")
    if isinstance(associacao, dict):
        associacao = dict(associacao)
        times = {}
        for lado in ("home", "away"):
            time = dict((associacao.get("times") or {}).get(lado) or {})
            time["name"] = time.pop("name_original", time.get("name"))
            times[lado] = time
        match_id = str(associacao.get("fixture_id"))
        original = next(
            (
                item.get("_thestatsapi_original")
                for item in adaptadas
                if str((item.get("fixture") or {}).get("id")) == match_id
            ),
            None,
        )
        associacao.update({
            "match_id": match_id,
            "times": times,
            "item_thestatsapi": original,
            "fonte": FONTE,
            "aplicacao_sinais": APLICACAO_SINAIS,
        })
        diagnostico["associacao"] = associacao
    diagnostico.update({
        "fonte": FONTE,
        "partidas_adaptadas": len(adaptadas),
        "aplicacao_sinais": APLICACAO_SINAIS,
        "calibracao": False,
    })
    return diagnostico


def associar_jogo_thestatsapi(
    jogo_packball,
    resposta_lista,
    margem_minima=MARGEM_MINIMA_ASSOCIACAO,
):
    return diagnosticar_associacao_thestatsapi(
        jogo_packball, resposta_lista, margem_minima
    )["associacao"]


def _instante_iso(valor=None):
    if isinstance(valor, datetime):
        return valor.replace(microsecond=0).isoformat()
    if valor is not None and str(valor).strip():
        return str(valor).strip()
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _periodo_live(meta, minuto):
    bruto = str(
        meta.get("match_status") or meta.get("period") or ""
    ).strip().casefold().replace("-", "_").replace(" ", "_")
    if bruto in {"first_half", "1st_half", "1h", "first"}:
        return "primeiro_tempo"
    if bruto in {"half_time", "halftime", "ht", "interval"}:
        return "intervalo"
    if bruto in {"second_half", "2nd_half", "2h", "second"}:
        return "segundo_tempo"
    if bruto in {"extra_time", "et", "penalties", "penalty_shootout"}:
        return "prorrogacao"
    if minuto is not None:
        return "primeiro_tempo" if minuto <= 45 else "segundo_tempo"
    return None


def _par_metrica(stats, chave, *, inteiro=False):
    bloco = stats.get(chave) if isinstance(stats, dict) else None
    if isinstance(bloco, dict) and isinstance(bloco.get("all"), dict):
        bloco = bloco["all"]
    if not isinstance(bloco, dict):
        return {"home": None, "away": None}
    return {
        "home": _numero(bloco.get("home"), inteiro=inteiro),
        "away": _numero(bloco.get("away"), inteiro=inteiro),
    }


def normalizar_live_stats_thestatsapi(
    resposta,
    *,
    packball_url=None,
    orientacao="direta",
    coletado_em=None,
):
    """Normaliza ``data.meta`` + ``data.stats`` sem preencher ausencias."""
    if orientacao not in {"direta", "invertida"}:
        return None
    dados = _desembrulhar_resposta(resposta)
    if not isinstance(dados, dict):
        return None
    match_id = str(dados.get("match_id") or "").strip()
    if not _ID_PARTIDA_RE.fullmatch(match_id):
        return None
    meta = dados.get("meta") or {}
    stats = dados.get("stats") or {}
    if not isinstance(meta, dict) or not isinstance(stats, dict):
        return None

    metricas = {}
    for chave_api, chave_local in _METRICAS_LIVE.items():
        metricas[chave_local] = _par_metrica(
            stats,
            chave_api,
            inteiro=chave_local != "xg",
        )
    if orientacao == "invertida":
        metricas = {
            nome: {"home": lados["away"], "away": lados["home"]}
            for nome, lados in metricas.items()
        }
    if not any(
        valor is not None
        for lados in metricas.values()
        for valor in lados.values()
    ):
        return None

    placar = {
        "home": _numero(meta.get("home_goals"), inteiro=True),
        "away": _numero(meta.get("away_goals"), inteiro=True),
    }
    if orientacao == "invertida":
        placar = {"home": placar["away"], "away": placar["home"]}
    placar_lista = (
        [placar["home"], placar["away"]]
        if placar["home"] is not None or placar["away"] is not None
        else None
    )
    minuto = _inteiro_minuto(meta.get("elapsed_minutes"))
    obrigatorias = ("chutes", "chutes_gol", "escanteios")
    completo = all(
        metricas[nome][lado] is not None
        for nome in obrigatorias
        for lado in ("home", "away")
    )
    instante_fonte = (
        dados.get("updated_at")
        or meta.get("updated_at")
        or meta.get("generated_at")
    )
    return {
        "match_id": match_id,
        "fixture_id": match_id,
        "packball_url": str(packball_url) if packball_url else None,
        "coletado_em": _instante_iso(coletado_em or instante_fonte),
        "minuto": minuto,
        "periodo": _periodo_live(meta, minuto),
        "placar": placar_lista,
        "placar_mandante": placar["home"],
        "placar_visitante": placar["away"],
        "orientacao": orientacao,
        "chutes_mandante": metricas["chutes"]["home"],
        "chutes_visitante": metricas["chutes"]["away"],
        "chutes_gol_mandante": metricas["chutes_gol"]["home"],
        "chutes_gol_visitante": metricas["chutes_gol"]["away"],
        "escanteios_mandante": metricas["escanteios"]["home"],
        "escanteios_visitante": metricas["escanteios"]["away"],
        "xg_mandante": metricas["xg"]["home"],
        "xg_visitante": metricas["xg"]["away"],
        "metricas_presentes": sorted(
            nome for nome, lados in metricas.items()
            if any(valor is not None for valor in lados.values())
        ),
        "completo": bool(completo),
        "fonte": FONTE,
        "aplicacao_sinais": APLICACAO_SINAIS,
        "calibracao": False,
    }


def _decimal_linha(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        linha = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if not linha.is_finite() or linha < 0:
        return None
    return linha


def _odd_live(selecao):
    if isinstance(selecao, dict):
        selecao = selecao.get("live")
    odd = _numero(selecao)
    return odd if odd is not None and odd > 1 else None


def _classificar_mercado(nome):
    original = str(nome or "").strip()
    chave = re.sub(r"[^a-z0-9]+", "_", _texto_sem_acentos(original).lower())
    chave = chave.strip("_")
    if not chave or any(
        termo in chave
        for termo in ("next_goal", "next_corner", "race_to", "most_corners")
    ):
        return None

    if "corner" in chave:
        categoria = "escanteios"
    elif "goal" in chave and (
        "total" in chave or chave in {"match_goals", "goals_over_under"}
    ) and "team_total" not in chave:
        categoria = "gols"
    else:
        return None

    if any(termo in chave for termo in ("first_half", "1st_half", "1h")):
        periodo = "primeiro_tempo"
    elif any(
        termo in chave for termo in ("second_half", "2nd_half", "2h")
    ):
        periodo = "segundo_tempo"
    else:
        periodo = "jogo"
    return categoria, periodo


def _tipo_linha_escanteio(linha):
    fracao = linha % 1
    if fracao in {Decimal("0"), Decimal("0.25"), Decimal("0.75")}:
        return "asiatico"
    if fracao == Decimal("0.5"):
        return "total_normal"
    return "linha_nao_classificada"


def _iterar_mercados(mercados):
    if isinstance(mercados, dict):
        yield from mercados.items()
        return
    if isinstance(mercados, list):
        for item in mercados:
            if not isinstance(item, dict):
                continue
            nome = item.get("market") or item.get("name") or item.get("key")
            linhas = item.get("lines") or item.get("odds") or item.get("values")
            if nome is not None:
                yield nome, linhas


def normalizar_odds_live_thestatsapi(resposta, *, coletado_em=None):
    """Mantem apenas totais de gols e escanteios do endpoint ao vivo."""
    dados = _desembrulhar_resposta(resposta)
    if not isinstance(dados, dict):
        return {
            "match_id": None,
            "ofertas": [],
            "fonte": FONTE,
            "aplicacao_sinais": APLICACAO_SINAIS,
            "calibracao": False,
        }
    match_id = str(dados.get("match_id") or "").strip()
    if not _ID_PARTIDA_RE.fullmatch(match_id):
        match_id = None
    instante_fonte = dados.get("updated_at") or dados.get("generated_at")
    instante = _instante_iso(coletado_em or instante_fonte)
    ofertas = []
    ignorados = set()
    bookmakers = dados.get("bookmakers") or []
    if isinstance(bookmakers, dict):
        bookmakers = [bookmakers]
    for bookmaker_item in bookmakers:
        if not isinstance(bookmaker_item, dict):
            continue
        bookmaker = str(
            bookmaker_item.get("bookmaker")
            or bookmaker_item.get("name")
            or ""
        ).strip() or None
        for mercado_original, linhas in _iterar_mercados(
            bookmaker_item.get("markets") or {}
        ):
            classificacao = _classificar_mercado(mercado_original)
            if classificacao is None:
                ignorados.add(str(mercado_original))
                continue
            categoria, periodo = classificacao
            if not isinstance(linhas, dict):
                continue
            for linha_original, selecoes in linhas.items():
                linha_decimal = _decimal_linha(linha_original)
                if linha_decimal is None or not isinstance(selecoes, dict):
                    continue
                over = _odd_live(selecoes.get("over"))
                under = _odd_live(selecoes.get("under"))
                if over is None and under is None:
                    continue
                if categoria == "escanteios":
                    tipo_mercado = _tipo_linha_escanteio(linha_decimal)
                else:
                    tipo_mercado = "total_normal"
                ofertas.append({
                    "match_id": match_id,
                    "bookmaker": bookmaker,
                    "mercado_original": str(mercado_original),
                    "categoria": categoria,
                    "periodo": periodo,
                    "tipo_mercado": tipo_mercado,
                    "linha": float(linha_decimal),
                    "linha_original": str(linha_original),
                    "over": over,
                    "under": under,
                    "completa": over is not None and under is not None,
                    "coletado_em": instante,
                    "fonte": FONTE,
                    "aplicacao_sinais": APLICACAO_SINAIS,
                })
    ofertas.sort(key=lambda item: (
        item["bookmaker"] or "",
        item["categoria"],
        item["periodo"],
        item["linha"],
    ))
    return {
        "match_id": match_id,
        "coletado_em": instante,
        "ofertas": ofertas,
        "total_ofertas": len(ofertas),
        "mercados_ignorados": sorted(ignorados),
        "bookmakers": sorted({
            item["bookmaker"] for item in ofertas if item["bookmaker"]
        }),
        "fonte": FONTE,
        "aplicacao_sinais": APLICACAO_SINAIS,
        "calibracao": False,
    }


def resumir_associacoes_thestatsapi(diagnosticos):
    itens = [item for item in diagnosticos or [] if isinstance(item, dict)]
    motivos = Counter(
        str(item.get("motivo") or "nao_informado") for item in itens
    )
    associadas = sum(isinstance(item.get("associacao"), dict) for item in itens)
    return {
        "tentativas": len(itens),
        "associadas": associadas,
        "taxa_associacao": (
            round(associadas / len(itens), 4) if itens else None
        ),
        "motivos": dict(sorted(motivos.items())),
        "fonte": FONTE,
        "aplicacao_sinais": APLICACAO_SINAIS,
        "calibracao": False,
    }


def resumir_cobertura_thestatsapi(
    *,
    partidas=None,
    diagnosticos=None,
    snapshots=None,
    odds=None,
):
    """Resume cobertura observada, sempre sem promover a fonte para sinais."""
    partidas_adaptadas = adaptar_lista_thestatsapi_para_associador(
        partidas or []
    )
    snapshots = [item for item in snapshots or [] if isinstance(item, dict)]
    envelopes_odds = [item for item in odds or [] if isinstance(item, dict)]
    ofertas = []
    for envelope in envelopes_odds:
        if isinstance(envelope.get("ofertas"), list):
            ofertas.extend(
                item for item in envelope["ofertas"]
                if isinstance(item, dict)
            )
        elif "categoria" in envelope:
            ofertas.append(envelope)
    ids_stats = {item.get("match_id") for item in snapshots if item.get("match_id")}
    ids_odds = {item.get("match_id") for item in ofertas if item.get("match_id")}
    metricas = {}
    for nome in ("chutes", "chutes_gol", "escanteios", "xg"):
        com_par = sum(
            item.get(f"{nome}_mandante") is not None
            and item.get(f"{nome}_visitante") is not None
            for item in snapshots
        )
        metricas[nome] = {
            "com_par": com_par,
            "cobertura": round(com_par / len(snapshots), 4)
            if snapshots else None,
        }
    por_categoria = Counter(
        str(item.get("categoria") or "desconhecida") for item in ofertas
    )
    tipos_cantos = Counter(
        str(item.get("tipo_mercado") or "desconhecido")
        for item in ofertas
        if item.get("categoria") == "escanteios"
    )
    return {
        "estado": "coletando_sombra" if (
            partidas_adaptadas or snapshots or ofertas
        ) else "aguardando_primeira_amostra",
        "partidas_ao_vivo": len(partidas_adaptadas),
        "partidas_com_stats": len(ids_stats),
        "partidas_com_odds": len(ids_odds),
        "snapshots": len(snapshots),
        "snapshots_completos": sum(bool(item.get("completo")) for item in snapshots),
        "cobertura_metricas": metricas,
        "ofertas": len(ofertas),
        "ofertas_por_categoria": dict(sorted(por_categoria.items())),
        "linhas_escanteio_por_tipo": dict(sorted(tipos_cantos.items())),
        "associacoes": resumir_associacoes_thestatsapi(diagnosticos or []),
        "fonte": FONTE,
        "aplicacao_sinais": APLICACAO_SINAIS,
        "telegram": False,
        "calibracao": False,
        "promocao_automatica": False,
    }
