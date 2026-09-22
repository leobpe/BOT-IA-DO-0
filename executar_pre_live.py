"""Executa a seleção pré-live e, quando autorizada, entrega no Telegram."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv(Path(__file__).parent / ".env")

from api_football import APIFootball
from betsapi import BetsAPI
from betsapi_pre_live import (
    VERSAO as VERSAO_BETSAPI_PRELIVE,
    carregar_catalogo_bet365_pre_live,
    extrair_ofertas_bet365_pre_live,
    listar_eventos_bet365_pre_live,
    parear_evento_bet365_pre_live,
    resumir_catalogo_bet365_pre_live,
)
from coletor_pre_live import coletar_contexto_pre_live
from controle_pre_live_preciso import aplicar_validacao as aplicar_controle_pre_live_preciso
from processo_monitor import gravar_json_atomico
from repositorio_pre_live import RepositorioPreLive, preparar_banco_pre_live
from seletor_pre_live import (
    CHAMADAS_ESTIMADAS_POR_JOGO,
    LINHAGEM,
    MAXIMO_JOGOS_PADRAO,
    ODD_MINIMA,
    ODD_MAXIMA,
    ODD_MAXIMA_PREFERENCIAL,
    PERFIL_SELECAO,
    RETORNO_DIA30,
    RESERVA_AO_VIVO_PADRAO,
    VERSAO,
    anexar_probabilidade_sem_margem,
    avaliar_ofertas_pre_live,
    extrair_ofertas_api_football,
    liquidar_bilhete_pre_live,
    montar_bilhetes_pre_live,
    politica_v11_ativa,
    revalidar_bilhetes_publicados_pre_live,
)
from telegram_pre_live import (
    editar_resultados_listas_pre_live,
    editar_resultados_pre_live,
    enviar_confirmados_pre_live,
    publicar_lista_preliminar_pre_live,
)
from validacao_pre_live_preciso import (
    registrar_ou_validar_definicao as registrar_definicao_pre_live_preciso,
    resumir_validacao_pre_live_preciso,
    sincronizar_coorte_pre_live_preciso,
)


def calcular_limite_analise(api, solicitado, reserva_ao_vivo=None):
    """Dimensiona a coleta profunda sem consumir a reserva do monitor ao vivo."""
    solicitado = max(int(solicitado), 1)
    reserva = max(int(
        reserva_ao_vivo
        if reserva_ao_vivo is not None
        else os.getenv("PRELIVE_RESERVA_AO_VIVO", RESERVA_AO_VIVO_PADRAO)
    ), 0)
    recarregar_fn = getattr(api, "recarregar_uso_compartilhado", None)
    contador_recarregado = bool(
        recarregar_fn() if callable(recarregar_fn) else False
    )
    consumo_fn = getattr(api, "consumo_atual", None)
    if not callable(consumo_fn):
        return {
            "configurado": solicitado,
            "efetivo": solicitado,
            "restante_seguro": None,
            "reserva_ao_vivo": reserva,
            "motivo": "contador_indisponivel",
            "contador_compartilhado_recarregado": contador_recarregado,
        }
    try:
        consumo = consumo_fn() or {}
        restante = int(consumo.get("restante_seguro_dia"))
    except (TypeError, ValueError, OSError):
        return {
            "configurado": solicitado,
            "efetivo": solicitado,
            "restante_seguro": None,
            "reserva_ao_vivo": reserva,
            "motivo": "contador_indisponivel",
            "contador_compartilhado_recarregado": contador_recarregado,
        }
    disponivel = max(restante - reserva, 0)
    por_cota = disponivel // CHAMADAS_ESTIMADAS_POR_JOGO
    efetivo = min(solicitado, por_cota)
    return {
        "configurado": solicitado,
        "efetivo": max(int(efetivo), 0),
        "restante_seguro": restante,
        "reserva_ao_vivo": reserva,
        "chamadas_estimadas_por_jogo": CHAMADAS_ESTIMADAS_POR_JOGO,
        "contador_compartilhado_recarregado": contador_recarregado,
        "motivo": (
            "reserva_ao_vivo_protegida"
            if efetivo < solicitado else "limite_configurado"
        ),
    }


def linhagem_operacional_pre_live(limite_analise):
    """Separa coortes quando a política configurável de cobertura mudar."""
    politica = {
        "linhagem_modelo": LINHAGEM,
        "limite_configurado": int(limite_analise["configurado"]),
        "reserva_ao_vivo": int(limite_analise["reserva_ao_vivo"]),
        "chamadas_estimadas_por_jogo": CHAMADAS_ESTIMADAS_POR_JOGO,
        "betsapi_pre_live_versao": VERSAO_BETSAPI_PRELIVE,
        "limite_efetivo_dinamico_por_cota": True,
    }
    serializado = json.dumps(
        politica, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def filtrar_avaliacoes_ineditas(avaliacoes, fixture_ids_publicados):
    """Exclui partidas já mostradas antes de montar o novo ranking."""
    publicados = {int(item) for item in fixture_ids_publicados or []}
    ineditas = []
    excluidas = 0
    for avaliacao in avaliacoes or []:
        try:
            fixture_id = int((avaliacao.get("jogo") or {}).get("fixture_id"))
        except (TypeError, ValueError):
            fixture_id = None
        if fixture_id is not None and fixture_id in publicados:
            excluidas += 1
            continue
        ineditas.append(avaliacao)
    return ineditas, excluidas


def _fixture_id(item):
    try:
        return int(((item or {}).get("fixture") or {}).get("id"))
    except (TypeError, ValueError):
        return None


def _resumo_jogo(fixture):
    fixture = fixture or {}
    dados = fixture.get("fixture") or {}
    times = fixture.get("teams") or {}
    liga = fixture.get("league") or {}
    return {
        "fixture_id": dados.get("id"),
        "inicio": dados.get("date"),
        "status": ((dados.get("status") or {}).get("short")),
        "mandante": ((times.get("home") or {}).get("name")),
        "visitante": ((times.get("away") or {}).get("name")),
        "liga": liga.get("name"),
        "pais": liga.get("country"),
        "temporada": liga.get("season"),
    }


def _futuro(fixture, agora):
    status = str(
        ((((fixture or {}).get("fixture") or {}).get("status") or {}).get("short"))
        or ""
    ).upper()
    if status and status not in {"NS", "TBD"}:
        return False
    data = (((fixture or {}).get("fixture") or {}).get("date"))
    try:
        instante = datetime.fromisoformat(str(data).replace("Z", "+00:00"))
        return instante.timestamp() > agora.timestamp()
    except (TypeError, ValueError):
        return status in {"NS", "TBD"}


def _liquidar_pendentes(
    api, repositorio, somente_entregues=False, somente_publicados=False
):
    if somente_publicados:
        pendentes = repositorio.listar_bilhetes_publicados_pendentes()
    elif somente_entregues:
        pendentes = repositorio.listar_bilhetes_entregues_pendentes()
    else:
        pendentes = repositorio.listar_bilhetes_pendentes()
    fixture_ids = sorted({
        int(perna.get("fixture_id"))
        for item in pendentes
        for perna in (item["bilhete"].get("pernas") or [])
        if perna.get("fixture_id")
    })
    fixtures = api.partidas_por_ids(fixture_ids) if fixture_ids else []
    por_id = {
        _fixture_id(item): item for item in fixtures if _fixture_id(item)
    }
    finalizados = verdes = vermelhos = anulados = 0
    for item in pendentes:
        liquidacao = liquidar_bilhete_pre_live(item["bilhete"], por_id)
        resultado = liquidacao.get("resultado")
        repositorio.registrar_resultados_pernas(
            item["id"], item["bilhete"], liquidacao.get("pernas") or []
        )
        if resultado not in {"green", "red", "anulada"}:
            continue
        if repositorio.finalizar_bilhete(
            item["id"], resultado, liquidacao.get("retorno") or 0.0
        ):
            finalizados += 1
            verdes += int(resultado == "green")
            vermelhos += int(resultado == "red")
            anulados += int(resultado == "anulada")
    return {
        "pendentes": len(pendentes),
        "fixtures_consultadas": len(fixture_ids),
        "finalizados": finalizados,
        "greens": verdes,
        "reds": vermelhos,
        "anulados": anulados,
    }


def reconciliar_entregas_pre_live(pasta=None, api=None):
    """Liquida apenas sinais publicados e edita a mensagem original."""
    pasta = Path(pasta or Path(__file__).parent)
    load_dotenv(pasta / ".env")
    api = api or APIFootball(pasta, perfil="pre_live_resultados")
    repositorio = RepositorioPreLive(pasta / "pre_live.db")
    try:
        registrar_definicao_pre_live_preciso(repositorio.conexao)
        pendentes = repositorio.listar_bilhetes_publicados_pendentes()
        liquidacao = (
            _liquidar_pendentes(api, repositorio, somente_publicados=True)
            if pendentes else {
                "pendentes": 0, "fixtures_consultadas": 0,
                "finalizados": 0, "greens": 0, "reds": 0,
                "anulados": 0,
            }
        )
        sincronizacao_precisa = sincronizar_coorte_pre_live_preciso(
            repositorio.conexao
        )
        edicao = editar_resultados_pre_live(
            repositorio, os.getenv("TELEGRAM_BOT_TOKEN")
        )
        edicao_listas = editar_resultados_listas_pre_live(
            repositorio, os.getenv("TELEGRAM_BOT_TOKEN")
        )
        validacao_precisa = resumir_validacao_pre_live_preciso(
            repositorio.conexao
        )
        controle_preciso = aplicar_controle_pre_live_preciso(
            validacao_precisa,
            caminho=pasta / "pre_live_preciso_estado.json",
        )
        return {
            "liquidacao": liquidacao,
            "telegram": edicao,
            "telegram_listas": edicao_listas,
            "sincronizacao_coorte_filtro_preciso": sincronizacao_precisa,
            "filtro_preciso_prospectivo": validacao_precisa,
            "controle_filtro_preciso": controle_preciso,
        }
    finally:
        repositorio.fechar()


def executar(
    pasta=None, data_alvo=None, maximo_jogos=None, api=None,
    cancelar_fn=None, slot_publicacao=None, betsapi=None,
):
    pasta = Path(pasta or Path(__file__).parent)
    load_dotenv(pasta / ".env")
    agora = datetime.now().astimezone()
    data_alvo = str(data_alvo or agora.strftime("%Y-%m-%d"))
    maximo_jogos = max(
        int(maximo_jogos or os.getenv(
            "PRELIVE_MAX_JOGOS", str(MAXIMO_JOGOS_PADRAO)
        )), 1
    )
    aplicacao_automatica = os.getenv(
        "PRELIVE_APLICACAO_AUTOMATICA", "0"
    ).strip().lower() in {"1", "true", "sim", "yes", "on"}
    estado_confirmado = (
        "apto_envio_automatico"
        if aplicacao_automatica else "apto_sombra_confirmado"
    )
    api = api or APIFootball(pasta, perfil="pre_live")
    betsapi_pre_live_ativa = os.getenv(
        "BETSAPI_PRELIVE_ATIVA", "0"
    ).strip().lower() in {"1", "true", "sim", "yes", "on"}
    if betsapi_pre_live_ativa and betsapi is None:
        try:
            timeout_betsapi = float(os.getenv(
                "BETSAPI_PRELIVE_TIMEOUT_SEGUNDOS", "30"
            ))
        except (TypeError, ValueError):
            timeout_betsapi = 30.0
        betsapi = BetsAPI(pasta, timeout=timeout_betsapi)
    elif not betsapi_pre_live_ativa:
        betsapi = None
    limite_analise = calcular_limite_analise(api, maximo_jogos)
    linhagem_execucao = linhagem_operacional_pre_live(limite_analise)
    preparacao_banco = preparar_banco_pre_live(
        pasta / "pre_live.db", pasta / "backups" / "pre_live"
    )
    repositorio = RepositorioPreLive(pasta / "pre_live.db")
    try:
        ancora_filtro_preciso = registrar_definicao_pre_live_preciso(
            repositorio.conexao
        )
    except Exception:
        repositorio.fechar()
        raise
    execucao_id = repositorio.iniciar_execucao(data_alvo)
    canal_pre_live = os.getenv("TELEGRAM_CHAT_ID_PRE_LIVE")
    fixture_ids_publicados = (
        repositorio.listar_fixture_ids_publicados(data_alvo, canal_pre_live)
        if canal_pre_live else set()
    )
    resumo = {
        "versao": VERSAO,
        "perfil_selecao": PERFIL_SELECAO,
        "odd_minima": ODD_MINIMA,
        "rollback_perfil_selecao": "PRELIVE_PERFIL_SELECAO=v11",
        "linhagem_sha256": linhagem_execucao,
        "linhagem_modelo_sha256": LINHAGEM,
        "data_alvo": data_alvo,
        "iniciado_em": agora.isoformat(),
        "slot_publicacao": str(slot_publicacao or agora.strftime("%H:%M")),
        "modo": (
            "telegram_automatico_confirmado"
            if aplicacao_automatica else "sombra_prospectiva"
        ),
        "telegram": bool(aplicacao_automatica),
        "aplicacao_automatica": bool(aplicacao_automatica),
        "rollback": "PRELIVE_APLICACAO_AUTOMATICA=0",
        "politica_profissional_v11": {
            "ativa": politica_v11_ativa(),
            "multiplas_oficiais": RETORNO_DIA30 or os.getenv(
                "PRELIVE_V11_MULTIPLAS_OFICIAIS_ATIVAS", "0"
            ).strip().lower() in {"1", "true", "sim", "yes", "on"},
            "revalidacao_sem_republicar": True,
            "resultados_por_perna": True,
            "rollback": "PRELIVE_POLITICA_V11_ATIVA=0",
        },
        "preparacao_banco": preparacao_banco,
        "jogos_calendario": 0,
        "jogos_com_odds_utilizaveis": 0,
        "jogos_analisados": 0,
        "odds_completas": False,
        "bilhetes": 0,
        "bilhetes_novos": 0,
        "limite_analise": limite_analise,
        "candidatos_elegiveis": 0,
        "jogos_nao_analisados_limite": 0,
        "cobertura_analise": None,
        "selecoes": [],
        "betsapi_pre_live": {
            "estado": (
                "aguardando_coleta" if betsapi is not None
                else "desativada"
            ),
            "rollback": "BETSAPI_PRELIVE_ATIVA=0",
        },
        "filtro_preciso_ancora": {
            "versao": ancora_filtro_preciso.get("versao"),
            "registrado_em": ancora_filtro_preciso.get("registrado_em"),
            "definicao_sha256": ancora_filtro_preciso.get(
                "definicao_sha256"
            ),
            "tamanho_coorte": ancora_filtro_preciso.get("coorte_fixa"),
        },
    }
    try:
        resumo["liquidacao"] = _liquidar_pendentes(api, repositorio)
        resumo["sincronizacao_coorte_filtro_preciso_antes"] = (
            sincronizar_coorte_pre_live_preciso(repositorio.conexao)
        )
        resumo["filtro_preciso_prospectivo_antes"] = (
            resumir_validacao_pre_live_preciso(repositorio.conexao)
        )
        resumo["controle_filtro_preciso"] = (
            aplicar_controle_pre_live_preciso(
                resumo["filtro_preciso_prospectivo_antes"],
                caminho=pasta / "pre_live_preciso_estado.json",
            )
        )
        resumo["telegram_resultados"] = editar_resultados_pre_live(
            repositorio, os.getenv("TELEGRAM_BOT_TOKEN")
        )
        resumo["telegram_resultados_listas"] = (
            editar_resultados_listas_pre_live(
                repositorio, os.getenv("TELEGRAM_BOT_TOKEN")
            )
        )
        resumo["validacao_antes"] = repositorio.resumir_validacao(
            linhagem_execucao, estado=estado_confirmado
        )
        if cancelar_fn is not None and cancelar_fn():
            resumo["cancelado"] = True
            resumo["finalizado_em"] = datetime.now().astimezone().isoformat()
            repositorio.concluir_execucao(
                execucao_id, resumo, estado="cancelada"
            )
            resumo["backup"] = repositorio.criar_backup(
                pasta / "backups" / "pre_live"
            )
            gravar_json_atomico(pasta / "pre_live_estado.json", resumo)
            return resumo
        fixtures = api.jogos_por_data(data_alvo, "America/New_York")
        odds = api.odds_pre_jogo_por_data(data_alvo)
        resumo["jogos_calendario"] = len(fixtures)
        resumo["odds_completas"] = bool(odds.get("completo"))
        resumo["paginas_odds"] = odds.get("paginas")
        resumo["motivo_odds"] = odds.get("motivo")
        consumo_apos_catalogo_fn = getattr(api, "consumo_atual", None)
        consumo_apos_catalogo = (
            consumo_apos_catalogo_fn()
            if callable(consumo_apos_catalogo_fn) else {}
        )
        if not isinstance(consumo_apos_catalogo, dict):
            consumo_apos_catalogo = {}
        restante_apos_catalogo = consumo_apos_catalogo.get(
            "restante_seguro_dia"
        )
        if restante_apos_catalogo is not None:
            resumo["consumo_api_apos_catalogo"] = {
                "categorias_dia": consumo_apos_catalogo.get("dia") or {},
                "consumo_dia": consumo_apos_catalogo.get("total_dia"),
                "restante_seguro_dia": int(restante_apos_catalogo),
            }
            limite_analise["restante_seguro_apos_catalogo"] = int(
                restante_apos_catalogo
            )
        if (
            (
                int(limite_analise.get("efetivo", 0) or 0) == 0
                and limite_analise.get("motivo")
                == "reserva_ao_vivo_protegida"
            )
            or (
                resumo["motivo_odds"] in {
                    "pagina_indisponivel", "limite_paginas_atingido"
                }
                and restante_apos_catalogo is not None
                and int(restante_apos_catalogo)
                <= int(limite_analise.get("reserva_ao_vivo", 0) or 0)
            )
        ):
            # A fonte não está tecnicamente indisponível: a execução foi
            # adiada para preservar a cota do monitor live. A segunda condição
            # cobre a reconciliação tardia do cabeçalho do provedor: o ciclo
            # pode começar com saldo local e descobrir o saldo real na primeira
            # resposta. Manter a causa real evita diagnóstico enganoso.
            resumo["motivo_odds"] = "reserva_ao_vivo_protegida"

        fixtures_por_id = {
            _fixture_id(item): item for item in fixtures if _fixture_id(item)
        }
        odds_por_fixture = {}
        ofertas_por_fixture = {}
        for item in odds.get("itens") or []:
            fixture_id = _fixture_id(item)
            if fixture_id is None:
                continue
            odds_por_fixture.setdefault(fixture_id, []).append(item)
        for fixture_id, itens in odds_por_fixture.items():
            ofertas = extrair_ofertas_api_football(itens, fixture_id)
            candidatas = [
                item for item in ofertas
                if 1.10 <= float(item.get("odd") or 0) <= ODD_MAXIMA
            ]
            if candidatas:
                ofertas_por_fixture[fixture_id] = ofertas

        eventos_bet365 = []
        diagnostico_eventos_bet365 = {
            "estado": "desativada", "eventos": 0, "paginas": 0,
        }
        pareamentos_bet365 = {}
        if betsapi is not None:
            eventos_bet365, diagnostico_eventos_bet365 = (
                listar_eventos_bet365_pre_live(betsapi, data_alvo)
            )
            candidatos_pareamento = []
            for fixture_id, fixture in fixtures_por_id.items():
                if not _futuro(fixture, agora):
                    continue
                pareamento = parear_evento_bet365_pre_live(
                    eventos_bet365, _resumo_jogo(fixture)
                )
                if pareamento:
                    candidatos_pareamento.append((
                        float(pareamento.get("similaridade") or 0),
                        fixture_id,
                        pareamento,
                    ))
            # Um mesmo FI não pode alimentar duas partidas internas.
            usados = set()
            for _, fixture_id, pareamento in sorted(
                candidatos_pareamento, reverse=True
            ):
                evento_id = pareamento["evento_id"]
                if evento_id in usados:
                    continue
                usados.add(evento_id)
                pareamentos_bet365[fixture_id] = pareamento
        resumo["jogos_com_odds_utilizaveis"] = len(
            set(ofertas_por_fixture) | set(pareamentos_bet365)
        )

        candidatos = []
        universo_fixture_ids = (
            set(ofertas_por_fixture) | set(pareamentos_bet365)
        )
        for fixture_id in universo_fixture_ids:
            ofertas = ofertas_por_fixture.get(fixture_id) or []
            fixture = fixtures_por_id.get(fixture_id)
            if not fixture or not _futuro(fixture, agora):
                continue
            alvo_preferencial = sum(
                1 for item in ofertas
                if ODD_MINIMA <= float(item.get("odd") or 0)
                <= ODD_MAXIMA_PREFERENCIAL
            )
            alvo_estendido = sum(
                1 for item in ofertas
                if ODD_MAXIMA_PREFERENCIAL
                < float(item.get("odd") or 0) <= ODD_MAXIMA
            )
            pernas = sum(
                1 for item in ofertas
                if 1.10 <= float(item.get("odd") or 0) <= 1.40
            )
            pareado_bet365 = fixture_id in pareamentos_bet365
            timestamp = int(
                (((fixture.get("fixture") or {}).get("timestamp")) or 0)
            )
            candidatos.append((
                -int(fixture_id in fixture_ids_publicados),
                -int(alvo_preferencial > 0), -int(pareado_bet365),
                -alvo_preferencial,
                -alvo_estendido, -pernas,
                timestamp, fixture_id, fixture,
            ))
        candidatos.sort()
        resumo["candidatos_elegiveis"] = len(candidatos)
        limite_efetivo = int(limite_analise["efetivo"])

        avaliacoes = []
        catalogos_bet365 = []
        ofertas_bet365_todas = []
        falhas_catalogo_bet365 = 0
        for _, _, _, _, _, _, _, fixture_id, fixture in candidatos[:limite_efetivo]:
            if cancelar_fn is not None and cancelar_fn():
                resumo["cancelado"] = True
                break
            ofertas_fixture = list(ofertas_por_fixture.get(fixture_id) or [])
            pareamento = pareamentos_bet365.get(fixture_id)
            if pareamento and betsapi is not None:
                catalogo, diagnostico_catalogo = (
                    carregar_catalogo_bet365_pre_live(betsapi, pareamento)
                )
                if diagnostico_catalogo.get("estado") == "catalogo_coletado":
                    catalogos_bet365.append(catalogo)
                    novas = extrair_ofertas_bet365_pre_live(
                        catalogo, fixture_id, _resumo_jogo(fixture)
                    )
                    anexar_probabilidade_sem_margem(novas)
                    ofertas_bet365_todas.extend(novas)
                    ofertas_fixture.extend(novas)
                else:
                    falhas_catalogo_bet365 += 1
            if not ofertas_fixture:
                continue
            contexto = coletar_contexto_pre_live(
                api, fixture, odds_por_fixture.get(fixture_id)
            )
            if not contexto:
                continue
            avaliacao = avaliar_ofertas_pre_live(
                ofertas_fixture, contexto
            )
            avaliacoes.append({
                "jogo": _resumo_jogo(fixture),
                "avaliacao": avaliacao,
            })
        resumo["jogos_analisados"] = len(avaliacoes)
        resumo["jogos_nao_analisados_limite"] = max(
            len(candidatos) - limite_efetivo, 0
        )
        resumo["cobertura_analise"] = (
            round(min(limite_efetivo, len(candidatos)) / len(candidatos), 4)
            if candidatos else 1.0
        )
        resumo_bet365 = resumir_catalogo_bet365_pre_live(
            catalogos_bet365, ofertas_bet365_todas
        )
        resumo["betsapi_pre_live"] = {
            **diagnostico_eventos_bet365,
            **resumo_bet365,
            "eventos_pareados": len(pareamentos_bet365),
            "falhas_catalogo": falhas_catalogo_bet365,
        }
        publicados_pendentes = (
            repositorio.listar_bilhetes_publicados_pendentes(
                data_alvo=data_alvo, canal=canal_pre_live
            )
            if canal_pre_live else []
        )
        revalidados = revalidar_bilhetes_publicados_pre_live(
            publicados_pendentes,
            avaliacoes,
            aplicacao_automatica=aplicacao_automatica,
        )
        registro_revalidacoes = repositorio.registrar_bilhetes(
            revalidados, data_alvo, detalhar=True
        )
        resumo["revalidacao_publicados"] = {
            "pendentes_considerados": len(publicados_pendentes),
            "ainda_elegiveis": len(revalidados),
            "confirmados_agora": registro_revalidacoes["confirmados"],
            "republicados": 0,
        }
        avaliacoes_ineditas, excluidas_publicadas = (
            filtrar_avaliacoes_ineditas(
                avaliacoes, fixture_ids_publicados
            )
        )
        resumo["jogos_ja_publicados_excluidos_antes_ranking"] = (
            excluidas_publicadas
        )
        resumo["jogos_ineditos_avaliados_para_ranking"] = len(
            avaliacoes_ineditas
        )
        bilhetes = montar_bilhetes_pre_live(
            avaliacoes_ineditas,
            maximo=20,
            aplicacao_automatica=aplicacao_automatica,
        )
        for bilhete in bilhetes:
            bilhete["linhagem_modelo_sha256"] = LINHAGEM
            bilhete["linhagem_sha256"] = linhagem_execucao
            bilhete["politica_cobertura"] = dict(limite_analise)
        resumo["bilhetes"] = len(bilhetes)
        registro_bilhetes = repositorio.registrar_bilhetes(
            bilhetes, data_alvo, detalhar=True
        )
        resumo["bilhetes_novos"] = registro_bilhetes["inseridos"]
        resumo["bilhetes_confirmados_agora"] = (
            registro_revalidacoes["confirmados"]
            + registro_bilhetes["confirmados"]
        )
        resumo["sincronizacao_coorte_filtro_preciso"] = (
            sincronizar_coorte_pre_live_preciso(repositorio.conexao)
        )
        resumo["telegram_lista_preliminar"] = (
            publicar_lista_preliminar_pre_live(
                repositorio,
                resumo,
                bilhetes,
                os.getenv("TELEGRAM_BOT_TOKEN"),
                canal_pre_live,
                limite=int(os.getenv(
                    "PRELIVE_TELEGRAM_LISTA_LIMITE", "10"
                )),
                ativo=os.getenv(
                    "PRELIVE_TELEGRAM_LISTA_PRELIMINAR", "1"
                ).strip().lower() in {
                    "1", "true", "sim", "yes", "on"
                },
            )
        )
        envio_individual = os.getenv(
            "PRELIVE_TELEGRAM_ENVIO_INDIVIDUAL", "0"
        ).strip().lower() in {"1", "true", "sim", "yes", "on"}
        if envio_individual:
            resumo["telegram"] = enviar_confirmados_pre_live(
                repositorio,
                data_alvo,
                os.getenv("TELEGRAM_BOT_TOKEN"),
                os.getenv("TELEGRAM_CHAT_ID_PRE_LIVE"),
                maximo_dia=int(os.getenv(
                    "PRELIVE_TELEGRAM_MAXIMO_DIA", "3"
                )),
                aplicacao_automatica=aplicacao_automatica,
            )
        else:
            resumo["telegram"] = {
                "estado": "consolidado_na_lista_do_horario",
                "enviados": 0,
                "falhas": 0,
                "envio_individual": False,
            }
        resumo["validacao_depois"] = repositorio.resumir_validacao(
            linhagem_execucao, estado=estado_confirmado
        )
        resumo["filtro_preciso_prospectivo"] = (
            resumir_validacao_pre_live_preciso(repositorio.conexao)
        )
        resumo["selecoes"] = [
            {
                "posicao": item["posicao"],
                "tipo": item["tipo"],
                "bookmaker": item["bookmaker"],
                "odd_total": item["odd_total"],
                "probabilidade_modelo": item["probabilidade_modelo"],
                "edge_modelo": item["edge_modelo"],
                "estado": item["estado"],
                "pernas": [
                    {
                        "fixture_id": perna["fixture_id"],
                        "jogo": perna.get("jogo"),
                        "mercado": perna["mercado"],
                        "selecao": perna["selecao"],
                        "odd": perna["odd"],
                        "qualidade": perna["qualidade_contexto"],
                    }
                    for perna in item["pernas"]
                ],
            }
            for item in bilhetes
        ]
        resumo["finalizado_em"] = datetime.now().astimezone().isoformat()
        repositorio.concluir_execucao(
            execucao_id, resumo,
            estado="cancelada" if resumo.get("cancelado") else "concluida",
        )
        resumo["backup"] = repositorio.criar_backup(
            pasta / "backups" / "pre_live"
        )
        gravar_json_atomico(pasta / "pre_live_estado.json", resumo)
        return resumo
    except Exception as erro:
        resumo["erro"] = type(erro).__name__
        resumo["finalizado_em"] = datetime.now().astimezone().isoformat()
        repositorio.concluir_execucao(execucao_id, resumo, estado="falha")
        try:
            resumo["backup"] = repositorio.criar_backup(
                pasta / "backups" / "pre_live"
            )
        except Exception as erro_backup:
            resumo["erro_backup"] = type(erro_backup).__name__
        gravar_json_atomico(pasta / "pre_live_estado.json", resumo)
        raise
    finally:
        repositorio.fechar()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data")
    parser.add_argument("--maximo-jogos", type=int)
    parser.add_argument("--slot-publicacao")
    argumentos = parser.parse_args()
    resultado = executar(
        data_alvo=argumentos.data,
        maximo_jogos=argumentos.maximo_jogos,
        slot_publicacao=argumentos.slot_publicacao,
    )
    print(
        "Pré-live concluído: "
        f"{resultado['jogos_analisados']} jogos analisados | "
        f"{resultado['bilhetes']} seleção(ões) em sombra."
    )
