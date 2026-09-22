"""Coleta profunda e isolada para a seleção pré-live diária."""

from __future__ import annotations

import time

from contexto_pre_jogo import resumir_contexto_pre_jogo
from gols_capacidade_contextual_v2 import (
    HISTORICO_ALVO,
    TTL_HISTORICO_SEGUNDOS,
    _medias_mando_temporada,
    _resumir_partidas,
)


TTL_JOGADORES_CHAVE_SEGUNDOS = 6 * 3600
VERSAO = "coletor-pre-live-15j-v1"


def _confirmacao_fixture(fixture):
    fixture = fixture or {}
    dados_fixture = fixture.get("fixture") or {}
    return {
        "fixture_id": dados_fixture.get("id"),
        "fixture": dados_fixture,
        "times": fixture.get("teams") or {},
        "liga": fixture.get("league") or {},
        "league": fixture.get("league") or {},
        "goals": fixture.get("goals") or {},
        "score": fixture.get("score") or {},
    }


def _numero(valor):
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _estatistica_jogador(item, time_id):
    for estatistica in item.get("statistics") or []:
        if ((estatistica.get("team") or {}).get("id")) == time_id:
            return estatistica
    return None


def _impacto_jogador(estatistica):
    estatistica = estatistica or {}
    jogos = estatistica.get("games") or {}
    gols = estatistica.get("goals") or {}
    chutes = estatistica.get("shots") or {}
    aparicoes = max(_numero(jogos.get("appearences")) or 1.0, 1.0)
    gols_jogo = (_numero(gols.get("total")) or 0.0) / aparicoes
    assistencias_jogo = (_numero(gols.get("assists")) or 0.0) / aparicoes
    chutes_gol_jogo = (_numero(chutes.get("on")) or 0.0) / aparicoes
    nota = _numero(jogos.get("rating")) or 6.0
    impacto = (
        min(gols_jogo / 0.70, 1.0) * 0.45
        + min(assistencias_jogo / 0.45, 1.0) * 0.25
        + min(max(nota - 6.0, 0.0) / 1.5, 1.0) * 0.20
        + min(chutes_gol_jogo / 1.5, 1.0) * 0.10
    )
    return round(min(max(impacto, 0.0), 1.0), 4)


def _resumir_jogadores_chave(
    itens, time_id, escalacoes_resumo, desfalques_resumo
):
    escalacao = (escalacoes_resumo or {}).get(str(time_id)) or {}
    titulares = {
        item.get("id") for item in escalacao.get("titulares") or []
        if item.get("id") is not None
    }
    desfalques = {
        item.get("id")
        for item in (
            ((desfalques_resumo or {}).get(str(time_id)) or {})
            .get("jogadores") or []
        )
        if item.get("id") is not None
    }
    jogadores = []
    for item in itens or []:
        estatistica = _estatistica_jogador(item, time_id)
        if not estatistica:
            continue
        jogador = item.get("player") or {}
        jogador_id = jogador.get("id")
        impacto = _impacto_jogador(estatistica)
        if impacto <= 0:
            continue
        confirmado = bool(escalacao.get("confirmada"))
        jogadores.append({
            "id": jogador_id,
            "nome": jogador.get("name"),
            "impacto": impacto,
            "titular": (
                jogador_id in titulares
                if confirmado else None
            ),
            "desfalque": jogador_id in desfalques,
        })
    jogadores.sort(key=lambda item: item["impacto"], reverse=True)
    return {
        "escalacao_confirmada": bool(escalacao.get("confirmada")),
        "jogadores": jogadores[:5],
        "destaques_encontrados": len(jogadores),
    }


def coletar_contexto_pre_live(
    api, fixture, odds_fixture=None, prazo_segundos=45.0
):
    """Coleta 15 jogos, mando, H2H, elenco e contexto competitivo."""
    confirmacao = _confirmacao_fixture(fixture)
    fixture_id = confirmacao.get("fixture_id")
    times = confirmacao.get("times") or {}
    mandante_id = ((times.get("home") or {}).get("id"))
    visitante_id = ((times.get("away") or {}).get("id"))
    if not fixture_id or not mandante_id or not visitante_id:
        return None
    prazo = time.monotonic() + max(float(prazo_segundos), 5.0)
    liga = confirmacao.get("liga") or {}
    liga_id, temporada = liga.get("id"), liga.get("season")

    forma = {}
    for lado, time_id in (
        ("mandante", mandante_id), ("visitante", visitante_id)
    ):
        forma[lado] = api._lista_contexto(
            f"contexto:prelive:forma15:{time_id}",
            "/fixtures",
            {"team": time_id, "last": HISTORICO_ALVO, "status": "FT"},
            TTL_HISTORICO_SEGUNDOS,
            prazo,
        )

    h2h = api._lista_contexto(
        f"contexto:prelive:h2h:{mandante_id}:{visitante_id}",
        "/fixtures/headtohead",
        {"h2h": f"{mandante_id}-{visitante_id}", "last": 10},
        TTL_HISTORICO_SEGUNDOS,
        prazo,
    )
    escalacoes = api._lista_contexto(
        f"contexto:prelive:escalacoes:{fixture_id}",
        "/fixtures/lineups",
        {"fixture": fixture_id},
        10 * 60,
        prazo,
    )
    desfalques = api._lista_contexto(
        f"contexto:prelive:desfalques:{fixture_id}",
        "/injuries",
        {"fixture": fixture_id},
        30 * 60,
        prazo,
    )
    previsao = api._lista_contexto(
        f"contexto:prelive:previsao:{fixture_id}",
        "/predictions",
        {"fixture": fixture_id},
        TTL_HISTORICO_SEGUNDOS,
        prazo,
    )

    estatisticas_times = {}
    temporada_mando = {}
    classificacao = None
    if liga_id and temporada:
        classificacao = api._lista_contexto(
            f"contexto:prelive:classificacao:{liga_id}:{temporada}",
            "/standings",
            {"league": liga_id, "season": temporada},
            3600,
            prazo,
        )
        for lado, time_id, mando in (
            ("mandante", mandante_id, True),
            ("visitante", visitante_id, False),
        ):
            dados = api._dados_contexto(
                f"contexto:time:{time_id}:{liga_id}:{temporada}",
                "/teams/statistics",
                {"team": time_id, "league": liga_id, "season": temporada},
                TTL_HISTORICO_SEGUNDOS,
                prazo,
            )
            if isinstance(dados, dict) and dados:
                estatisticas_times[lado] = dados
                temporada_mando[lado] = _medias_mando_temporada(
                    dados, mando
                )

    contexto = resumir_contexto_pre_jogo(
        confirmacao,
        h2h=h2h,
        escalacoes=escalacoes,
        desfalques=desfalques,
        forma_mandante=forma.get("mandante"),
        forma_visitante=forma.get("visitante"),
        estatisticas_times=estatisticas_times,
        previsao=(previsao or [None])[0],
        classificacao=classificacao,
        odds_pre_jogo=odds_fixture,
    )
    contexto["versao_pre_live"] = VERSAO
    contexto["capacidade_times_v2"] = {
        "historico_alvo": HISTORICO_ALVO,
        "recentes": {
            "mandante": _resumir_partidas(
                forma.get("mandante"), mandante_id, True
            ),
            "visitante": _resumir_partidas(
                forma.get("visitante"), visitante_id, False
            ),
        },
        "temporada_mando": temporada_mando,
    }
    contexto["capacidade_times_v2"]["cobertura"] = {
        lado: {
            "historico_total": int(
                ((contexto["capacidade_times_v2"]["recentes"].get(lado) or {})
                 .get("geral") or {}).get("jogos") or 0
            ),
            "historico_mando": int(
                ((contexto["capacidade_times_v2"]["recentes"].get(lado) or {})
                 .get("mando") or {}).get("jogos") or 0
            ),
        }
        for lado in ("mandante", "visitante")
    }

    top_jogadores = []
    if liga_id and temporada:
        for caminho, rotulo in (
            ("/players/topscorers", "artilheiros"),
            ("/players/topassists", "assistentes"),
        ):
            itens = api._lista_contexto(
                f"contexto:prelive:{rotulo}:{liga_id}:{temporada}",
                caminho,
                {"league": liga_id, "season": temporada},
                TTL_JOGADORES_CHAVE_SEGUNDOS,
                prazo,
            )
            top_jogadores.extend(itens or [])
    unicos = {}
    for item in top_jogadores:
        jogador_id = ((item.get("player") or {}).get("id"))
        if jogador_id is not None:
            unicos[jogador_id] = item
    escalacoes_resumo = contexto.get("escalacoes") or {}
    desfalques_resumo = contexto.get("desfalques") or {}
    contexto["jogadores_chave"] = {
        "mandante": _resumir_jogadores_chave(
            unicos.values(), mandante_id,
            escalacoes_resumo, desfalques_resumo,
        ),
        "visitante": _resumir_jogadores_chave(
            unicos.values(), visitante_id,
            escalacoes_resumo, desfalques_resumo,
        ),
    }
    contexto["coleta_pre_live"] = {
        "h2h": h2h is not None,
        "forma_15_mandante": len(forma.get("mandante") or []),
        "forma_15_visitante": len(forma.get("visitante") or []),
        "escalacoes": bool(escalacoes),
        "desfalques": desfalques is not None,
        "classificacao": bool(classificacao),
        "jogadores_chave": bool(unicos),
    }
    return contexto
