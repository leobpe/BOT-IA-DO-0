"""Prioriza no monitor ao vivo jogos já publicados pela pré-live.

Esta integração altera somente a ordem e a frequência de leitura. Ela não
cria candidatos, não aprova entradas e não interfere nos filtros de sinal.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from api_football import diagnosticar_associacao


ESTADOS_CONFIRMADOS = {
    "apto_sombra_confirmado",
    "apto_envio_automatico",
}
QUALIDADE_MINIMA_CONTEXTO = 80.0


def _instante(valor):
    try:
        instante = datetime.fromisoformat(str(valor or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone.utc)


def _referencia_fixture(fixture_id, alvo):
    return {
        "fixture": {"id": int(fixture_id), "status": {}},
        "teams": {
            "home": {"name": str(alvo.get("mandante") or "")},
            "away": {"name": str(alvo.get("visitante") or "")},
        },
        "goals": {"home": None, "away": None},
    }


def carregar_alvos_pre_live(caminho_banco, data_alvo=None):
    """Lê, sem escrever, partidas pendentes já publicadas no Telegram."""
    caminho = Path(caminho_banco)
    data_alvo = str(data_alvo or datetime.now().date().isoformat())
    diagnostico = {
        "estado": "sem_alvos",
        "data_alvo": data_alvo,
        "bilhetes_publicados": 0,
        "fixtures_publicados": 0,
        "fixtures_confirmados": 0,
        "alvos": {},
    }
    if not caminho.is_file():
        diagnostico["estado"] = "banco_ausente"
        return diagnostico

    conexao = None
    try:
        conexao = sqlite3.connect(
            caminho.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )
        linhas = conexao.execute(
            """
            SELECT DISTINCT b.id, b.estado, b.bilhete_json
            FROM bilhetes_pre_live b
            JOIN (
                SELECT bilhete_id FROM entregas_pre_live
                UNION
                SELECT bilhete_id FROM itens_listas_pre_live
            ) publicados ON publicados.bilhete_id=b.id
            WHERE b.data_alvo=? AND b.resultado IS NULL
            ORDER BY b.id
            """,
            (data_alvo,),
        ).fetchall()
    except (OSError, sqlite3.Error) as erro:
        diagnostico.update({
            "estado": "leitura_indisponivel",
            "erro": type(erro).__name__,
        })
        return diagnostico
    finally:
        if conexao is not None:
            conexao.close()

    alvos = {}
    bilhetes_validos = 0
    for bilhete_id, estado, bruto in linhas:
        try:
            bilhete = json.loads(bruto)
        except (TypeError, json.JSONDecodeError):
            continue
        confirmado = str(estado) in ESTADOS_CONFIRMADOS
        encontrou_perna = False
        for perna in bilhete.get("pernas") or []:
            try:
                fixture_id = int(perna.get("fixture_id") or 0)
            except (TypeError, ValueError):
                continue
            jogo = perna.get("jogo") or {}
            mandante = str(jogo.get("mandante") or "").strip()
            visitante = str(jogo.get("visitante") or "").strip()
            if fixture_id <= 0 or not mandante or not visitante:
                continue
            encontrou_perna = True
            atual = alvos.get(fixture_id)
            if atual is None or confirmado and not atual["confirmado"]:
                alvos[fixture_id] = {
                    "fixture_id": fixture_id,
                    "mandante": mandante,
                    "visitante": visitante,
                    "confirmado": confirmado,
                    "estado": str(estado),
                    "bilhete_id": int(bilhete_id),
                }
        bilhetes_validos += int(encontrou_perna)

    diagnostico.update({
        "estado": "pronto" if alvos else "sem_alvos",
        "bilhetes_publicados": bilhetes_validos,
        "fixtures_publicados": len(alvos),
        "fixtures_confirmados": sum(
            alvo["confirmado"] for alvo in alvos.values()
        ),
        "alvos": alvos,
    })
    return diagnostico


def carregar_contextos_pre_live(caminho_banco, data_alvo=None):
    """Carrega evidencias geradas antes do inicio, mesmo sem publicacao.

    A ponte e estritamente causal: uma perna so pode acompanhar o ao vivo
    quando o bilhete foi calculado antes do horario de inicio da partida.
    Ela fornece identidade/contexto para consulta posterior; nunca aprova um
    sinal e nunca transforma uma selecao pre-live em entrada ao vivo.
    """
    caminho = Path(caminho_banco)
    data_alvo = str(data_alvo or datetime.now().date().isoformat())
    diagnostico = {
        "estado": "sem_contextos",
        "data_alvo": data_alvo,
        "linhas_lidas": 0,
        "contextos_causais": 0,
        "rejeitados_nao_causais": 0,
        "rejeitados_qualidade": 0,
        "contextos": {},
    }
    if not caminho.is_file():
        diagnostico["estado"] = "banco_ausente"
        return diagnostico

    conexao = None
    try:
        conexao = sqlite3.connect(
            caminho.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )
        colunas = {
            linha[1] for linha in conexao.execute(
                "PRAGMA table_info(bilhetes_pre_live)"
            )
        }
        obrigatorias = {
            "id", "estado", "criado_em", "data_alvo", "resultado",
            "bilhete_json",
        }
        if not obrigatorias <= colunas:
            diagnostico["estado"] = "esquema_sem_contexto_causal"
            return diagnostico
        linhas = conexao.execute(
            """
            SELECT id, estado, criado_em, bilhete_json
            FROM bilhetes_pre_live
            WHERE data_alvo=? AND resultado IS NULL
            ORDER BY datetime(criado_em), id
            """,
            (data_alvo,),
        ).fetchall()
    except (OSError, sqlite3.Error) as erro:
        diagnostico.update({
            "estado": "leitura_indisponivel",
            "erro": type(erro).__name__,
        })
        return diagnostico
    finally:
        if conexao is not None:
            conexao.close()

    diagnostico["linhas_lidas"] = len(linhas)
    contextos = {}
    for bilhete_id, estado, criado_em, bruto in linhas:
        try:
            bilhete = json.loads(bruto)
        except (TypeError, json.JSONDecodeError):
            continue
        criado = _instante(criado_em)
        for perna in bilhete.get("pernas") or []:
            try:
                fixture_id = int(perna.get("fixture_id") or 0)
                qualidade = float(perna.get("qualidade_contexto") or 0.0)
            except (TypeError, ValueError):
                continue
            jogo = perna.get("jogo") or {}
            inicio = _instante(jogo.get("inicio"))
            mandante = str(jogo.get("mandante") or "").strip()
            visitante = str(jogo.get("visitante") or "").strip()
            if (
                fixture_id <= 0 or not mandante or not visitante
                or criado is None or inicio is None or criado > inicio
            ):
                diagnostico["rejeitados_nao_causais"] += 1
                continue
            if qualidade < QUALIDADE_MINIMA_CONTEXTO:
                diagnostico["rejeitados_qualidade"] += 1
                continue
            modelo = perna.get("modelo") or {}
            if not isinstance(modelo, dict) or not modelo:
                diagnostico["rejeitados_qualidade"] += 1
                continue
            contexto = {
                "fixture_id": fixture_id,
                "mandante": mandante,
                "visitante": visitante,
                "liga": jogo.get("liga"),
                "pais": jogo.get("pais"),
                "inicio": inicio.isoformat(),
                "criado_em": criado.isoformat(),
                "bilhete_id": int(bilhete_id),
                "estado": str(estado),
                "qualidade_contexto": round(qualidade, 1),
                "modelo": modelo,
                "probabilidade_modelo": perna.get("probabilidade_modelo"),
                "probabilidade_mercado_sem_margem": perna.get(
                    "probabilidade_mercado_sem_margem"
                ),
                "mercado": perna.get("mercado"),
                "selecao": perna.get("selecao"),
                "causal": True,
                "aplicacao_sinais": False,
            }
            anterior = contextos.get(fixture_id)
            chave = (qualidade, criado)
            chave_anterior = (
                float((anterior or {}).get("qualidade_contexto") or 0.0),
                _instante((anterior or {}).get("criado_em"))
                or datetime.min.replace(tzinfo=timezone.utc),
            )
            if anterior is None or chave > chave_anterior:
                contextos[fixture_id] = contexto

    diagnostico.update({
        "estado": "pronto" if contextos else "sem_contextos",
        "contextos_causais": len(contextos),
        "contextos": contextos,
    })
    return diagnostico


def aplicar_prioridade_pre_live(
    jogos,
    fixtures_api,
    caminho_banco,
    data_alvo=None,
    ativa=True,
):
    """Marca jogos associados; permanece fail-open para a coleta normal."""
    if not ativa:
        return {
            "estado": "desativada",
            "aplicacao_sinais": False,
            "jogos_associados": 0,
            "confirmados_associados": 0,
        }

    carregamento = carregar_alvos_pre_live(caminho_banco, data_alvo)
    alvos = carregamento.pop("alvos", {})
    carregamento_contextos = carregar_contextos_pre_live(
        caminho_banco, data_alvo
    )
    contextos = carregamento_contextos.pop("contextos", {})
    if not alvos and not contextos:
        return {
            **carregamento,
            "contexto_causal": carregamento_contextos,
            "aplicacao_sinais": False,
            "jogos_associados": 0,
            "confirmados_associados": 0,
            "jogos_contexto_associados": 0,
        }

    ids_referencia = set(alvos) | set(contextos)
    fixtures_live = {
        (item.get("fixture") or {}).get("id"): item
        for item in fixtures_api or []
        if isinstance(item, dict)
        and (item.get("fixture") or {}).get("id") in ids_referencia
    }
    referencias_por_id = {}
    for fixture_id, alvo in {**contextos, **alvos}.items():
        referencias_por_id[int(fixture_id)] = (
            fixtures_live.get(fixture_id)
            or _referencia_fixture(fixture_id, alvo)
        )
    referencias = list(referencias_por_id.values())
    associados = confirmados = contextos_associados = 0
    for jogo in jogos or []:
        try:
            associacao = diagnosticar_associacao(
                jogo, referencias
            ).get("associacao") or {}
        except (KeyError, TypeError, ValueError):
            continue
        alvo = alvos.get(associacao.get("fixture_id"))
        contexto = contextos.get(associacao.get("fixture_id"))
        if alvo is None and contexto is None:
            continue
        fixture_id = int(associacao["fixture_id"])
        jogo["pre_live_fixture_id"] = fixture_id
        if contexto is not None:
            jogo["pre_live_contexto_disponivel"] = True
            jogo["pre_live_contexto"] = dict(contexto)
            contextos_associados += 1
        if alvo is not None:
            jogo["pre_live_prioritario"] = True
            jogo["pre_live_confirmado"] = bool(alvo["confirmado"])
            jogo["pre_live_estado"] = alvo["estado"]
            associados += 1
            confirmados += int(alvo["confirmado"])

    return {
        **carregamento,
        "contexto_causal": carregamento_contextos,
        "aplicacao_sinais": False,
        "jogos_associados": associados,
        "confirmados_associados": confirmados,
        "jogos_contexto_associados": contextos_associados,
        "fallback_nomes_disponivel": True,
    }
