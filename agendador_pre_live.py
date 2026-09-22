"""Processo autônomo da seleção pré-live prospectiva."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv(Path(__file__).parent / ".env")

from api_football import APIFootball
from controle_sistema import ler_modo_manutencao
from executar_pre_live import executar, reconciliar_entregas_pre_live
from seletor_pre_live import (
    LINHAGEM as LINHAGEM_SELETOR,
    ODD_MINIMA as ODD_MINIMA_SELETOR,
    PERFIL_SELECAO,
    VERSAO as VERSAO_SELETOR,
)
from processo_monitor import (
    TravaInstancia,
    gravar_json_atomico,
    registrar_estado,
)


VERSAO = "agendador-pre-live-v1"
INTERVALO_SEGUNDOS = 60
INTERVALO_RESULTADOS_SEGUNDOS = 120
ATRASO_MAXIMO_MINUTOS = 180
REPETIR_FALHA_TEMPORARIA_MINUTOS = 5
JANELA_EXTRA_REPETICAO_MINUTOS = 30
VERSAO_RECONCILIACAO = "pre-live-reconciliacao-resultados-v1"


def _horarios_configurados(valor=None):
    bruto = str(valor if valor is not None else os.getenv(
        "PRELIVE_HORARIOS", "06:00,12:00,17:00"
    ))
    horarios = []
    for item in bruto.split(","):
        try:
            hora, minuto = [int(parte) for parte in item.strip().split(":", 1)]
        except (TypeError, ValueError):
            continue
        if 0 <= hora <= 23 and 0 <= minuto <= 59:
            horarios.append(f"{hora:02d}:{minuto:02d}")
    return sorted(set(horarios)) or ["06:00", "12:00", "17:00"]


def _ler_agenda(caminho):
    try:
        import json
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _registrar_reconciliacao_resultados(
    pasta, resultado=None, erro=None, agora=None
):
    """Persiste saúde da liquidação sem gerar mensagens operacionais."""
    agora = agora or datetime.now().astimezone()
    resultado = resultado or {}
    liquidacao = resultado.get("liquidacao") or {}
    telegram = resultado.get("telegram") or {}
    telegram_listas = resultado.get("telegram_listas") or {}
    estado = {
        "versao": VERSAO_RECONCILIACAO,
        "estado": "falha" if erro is not None else "saudavel",
        "atualizado_em": agora.isoformat(),
        "intervalo_segundos": max(int(os.getenv(
            "PRELIVE_INTERVALO_RESULTADOS_SEGUNDOS",
            str(INTERVALO_RESULTADOS_SEGUNDOS),
        )), 60),
        "pendentes": int(liquidacao.get("pendentes") or 0),
        "fixtures_consultadas": int(
            liquidacao.get("fixtures_consultadas") or 0
        ),
        "finalizados": int(liquidacao.get("finalizados") or 0),
        "greens": int(liquidacao.get("greens") or 0),
        "reds": int(liquidacao.get("reds") or 0),
        "anulados": int(liquidacao.get("anulados") or 0),
        "telegram_editados": int(telegram.get("editados") or 0),
        "telegram_falhas": int(telegram.get("falhas") or 0),
        "listas_telegram_editadas": int(
            telegram_listas.get("editados") or 0
        ),
        "listas_telegram_falhas": int(
            telegram_listas.get("falhas") or 0
        ),
    }
    if erro is not None:
        estado["erro"] = type(erro).__name__
    gravar_json_atomico(
        Path(pasta) / "pre_live_reconciliacao_estado.json", estado
    )
    return estado


def encontrar_slot_devido(
    agora, agenda, horarios=None,
    atraso_maximo_minutos=ATRASO_MAXIMO_MINUTOS,
    janela_extra_repeticao_minutos=JANELA_EXTRA_REPETICAO_MINUTOS,
):
    horarios = horarios or _horarios_configurados()
    execucoes = (agenda or {}).get("execucoes") or {}
    for horario in horarios:
        chave = f"{agora:%Y-%m-%d}|{horario}"
        execucao = execucoes.get(chave) or {}
        if execucao.get("estado") in {
            "concluida", "cancelada", "executando",
        }:
            continue
        repeticao_temporaria = execucao.get("estado") == "falha_temporaria"
        if repeticao_temporaria:
            try:
                proxima_tentativa = datetime.fromisoformat(
                    execucao["proxima_tentativa_em"]
                )
            except (KeyError, TypeError, ValueError):
                proxima_tentativa = None
            if proxima_tentativa is not None and agora < proxima_tentativa:
                continue
        hora, minuto = [int(item) for item in horario.split(":")]
        instante = agora.replace(
            hour=hora, minute=minuto, second=0, microsecond=0
        )
        atraso = agora - instante
        # Um slot pode falhar nos últimos minutos de sua janela normal. A
        # repetição agendada para cinco minutos depois não deve se tornar
        # inelegível só porque ultrapassou o limite por poucos minutos. A
        # extensão é curta e limitada para impedir tentativas durante todo o
        # restante do dia e para não bloquear os slots seguintes.
        atraso_permitido = max(int(atraso_maximo_minutos), 1)
        if repeticao_temporaria:
            atraso_permitido += max(
                int(janela_extra_repeticao_minutos), 0
            )
        if timedelta(0) <= atraso <= timedelta(
            minutes=atraso_permitido
        ):
            return chave, horario
    return None, None


def executar_slot(pasta, api, agenda, chave, horario, agora=None):
    agora = agora or datetime.now().astimezone()
    caminho_agenda = Path(pasta) / "pre_live_agenda.json"
    execucoes = agenda.setdefault("execucoes", {})
    execucoes[chave] = {
        "estado": "executando", "iniciado_em": agora.isoformat(),
        "horario": horario,
    }
    agenda.update({"versao": VERSAO, "atualizado_em": agora.isoformat()})
    gravar_json_atomico(caminho_agenda, agenda)
    try:
        resultado = executar(
            pasta=pasta,
            data_alvo=agora.strftime("%Y-%m-%d"),
            api=api,
            cancelar_fn=lambda: ler_modo_manutencao(pasta).get("ativo", False),
            slot_publicacao=horario,
        )
        falha_temporaria = bool(
            not resultado.get("cancelado")
            and resultado.get("motivo_odds")
            in {
                "pagina_indisponivel",
                "limite_paginas_atingido",
                "reserva_ao_vivo_protegida",
            }
            and not int(resultado.get("jogos_analisados") or 0)
        )
        estado = (
            "cancelada" if resultado.get("cancelado")
            else "falha_temporaria" if falha_temporaria
            else "concluida"
        )
        execucoes[chave] = {
            "estado": estado,
            "iniciado_em": execucoes[chave]["iniciado_em"],
            "finalizado_em": agora.isoformat(),
            "horario": horario,
            "jogos_analisados": int(resultado.get("jogos_analisados") or 0),
            "candidatos_elegiveis": int(
                resultado.get("candidatos_elegiveis") or 0
            ),
            "jogos_nao_analisados_limite": int(
                resultado.get("jogos_nao_analisados_limite") or 0
            ),
            "cobertura_analise": resultado.get("cobertura_analise"),
            "limite_analise": resultado.get("limite_analise") or {},
            "bilhetes": int(resultado.get("bilhetes") or 0),
        }
        if falha_temporaria:
            execucoes[chave].update({
                "motivo": resultado.get("motivo_odds"),
                "proxima_tentativa_em": (
                    agora
                    + timedelta(minutes=REPETIR_FALHA_TEMPORARIA_MINUTOS)
                ).isoformat(),
            })
        return resultado
    except Exception as erro:
        execucoes[chave] = {
            "estado": "falha",
            "iniciado_em": execucoes[chave]["iniciado_em"],
            "finalizado_em": agora.isoformat(),
            "horario": horario,
            "erro": type(erro).__name__,
        }
        raise
    finally:
        agenda["atualizado_em"] = agora.isoformat()
        # Conserva apenas 14 dias de slots, sem apagar o banco prospectivo.
        limite = (agora - timedelta(days=14)).date()
        agenda["execucoes"] = {
            chave_item: valor
            for chave_item, valor in execucoes.items()
            if str(chave_item).split("|", 1)[0] >= limite.isoformat()
        }
        gravar_json_atomico(caminho_agenda, agenda)


def executar_loop(pasta, uma_vez=False, dormir=None, agora_fn=None):
    pasta = Path(pasta)
    dormir = dormir or time.sleep
    agora_fn = agora_fn or (lambda: datetime.now().astimezone())
    api = APIFootball(pasta, perfil="pre_live")
    caminho_agenda = pasta / "pre_live_agenda.json"
    ciclos = execucoes = falhas = 0
    ultima_reconciliacao = 0.0
    while True:
        if os.getenv("PRELIVE_AGENDADOR_ATIVO", "1") != "1":
            break
        if ler_modo_manutencao(pasta).get("ativo", False):
            break
        ciclos += 1
        agora_monotonic = time.monotonic()
        intervalo_resultados = max(int(os.getenv(
            "PRELIVE_INTERVALO_RESULTADOS_SEGUNDOS",
            str(INTERVALO_RESULTADOS_SEGUNDOS),
        )), 60)
        if agora_monotonic - ultima_reconciliacao >= intervalo_resultados:
            try:
                resultado_reconciliacao = reconciliar_entregas_pre_live(
                    pasta=pasta, api=api
                )
                _registrar_reconciliacao_resultados(
                    pasta, resultado=resultado_reconciliacao
                )
            except Exception as erro:
                falhas += 1
                _registrar_reconciliacao_resultados(pasta, erro=erro)
            ultima_reconciliacao = agora_monotonic
        agenda = _ler_agenda(caminho_agenda)
        chave, horario = encontrar_slot_devido(agora_fn(), agenda)
        if chave:
            try:
                executar_slot(
                    pasta, api, agenda, chave, horario, agora=agora_fn()
                )
                execucoes += 1
            except Exception:
                falhas += 1
                if uma_vez:
                    raise
        if uma_vez:
            break
        restante = INTERVALO_SEGUNDOS
        while restante > 0:
            if ler_modo_manutencao(pasta).get("ativo", False):
                restante = 0
                break
            passo = min(restante, 1)
            dormir(passo)
            restante -= passo
    return {"ciclos": ciclos, "execucoes": execucoes, "falhas": falhas}


def main():
    pasta = Path(__file__).parent
    load_dotenv(pasta / ".env")
    uma_vez = "--uma-vez" in sys.argv
    if os.getenv("PRELIVE_AGENDADOR_ATIVO", "1") != "1":
        return
    trava = TravaInstancia(pasta / "pre_live_instancia.lock")
    if not trava.adquirir():
        return
    caminho_estado = pasta / "pre_live_processo.json"
    registrar_estado(
        caminho_estado, "ativo", perfil_selecao=PERFIL_SELECAO,
        versao_seletor=VERSAO_SELETOR, linhagem_seletor=LINHAGEM_SELETOR,
        odd_minima=ODD_MINIMA_SELETOR,
    )
    estado_final = "encerrado"
    erro = None
    try:
        executar_loop(pasta, uma_vez=uma_vez)
    except Exception as excecao:
        estado_final = "falha"
        erro = type(excecao).__name__
        raise
    finally:
        registrar_estado(caminho_estado, estado_final, erro=erro)
        trava.liberar()


if __name__ == "__main__":
    main()
