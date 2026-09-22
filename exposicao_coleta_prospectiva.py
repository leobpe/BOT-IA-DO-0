"""Mede exposicao real de coleta apos ancoras prospectivas."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from custodia_avaliacao import aplicar_efeitos_desativados

VERSAO = "exposicao-coleta-prospectiva-v2"
EVENTOS_INICIO_MANUTENCAO = frozenset({
    "modo_manutencao_solicitado",
    "modo_manutencao_restaurado_apos_falha_inicio",
})
EVENTOS_FIM_MANUTENCAO = frozenset({"modo_manutencao_liberado"})
EVENTOS_RELEVANTES = frozenset({
    "ciclo_concluido",
    "ciclo_falhou",
}) | EVENTOS_INICIO_MANUTENCAO | EVENTOS_FIM_MANUTENCAO
LIMITE_SEM_CICLO_SEGUNDOS = 3600.0


def _instante(valor):
    resultado = datetime.fromisoformat(str(valor))
    if resultado.tzinfo is not None:
        # Os eventos históricos do monitor usam hora local sem offset. As
        # âncoras mais novas são UTC com offset. Converta as âncoras para a
        # mesma hora local antes de remover o fuso; remover em UTC deslocaria
        # a janela e descartaria ciclos legítimos em máquinas fora de UTC.
        resultado = resultado.astimezone().replace(tzinfo=None)
    return resultado


@lru_cache(maxsize=2)
def _carregar_eventos_cache(caminho_texto, tamanho, modificado_ns):
    del tamanho, modificado_ns
    caminho = Path(caminho_texto)
    eventos = []
    linhas = 0
    invalidas = 0
    with caminho.open("r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            linhas += 1
            try:
                item = json.loads(linha)
                if not isinstance(item, dict):
                    raise ValueError("evento nao e objeto")
                if item.get("evento") not in EVENTOS_RELEVANTES:
                    continue
                _instante(item.get("em"))
            except (json.JSONDecodeError, TypeError, ValueError):
                invalidas += 1
                continue
            eventos.append(item)
    return tuple(eventos), linhas, invalidas


def carregar_eventos_observabilidade(caminho):
    """Le somente eventos necessarios, com cache invalidado por stat."""
    caminho = Path(caminho)
    try:
        stat = caminho.stat()
        eventos, linhas, invalidas = _carregar_eventos_cache(
            str(caminho.resolve()), stat.st_size, stat.st_mtime_ns
        )
    except OSError as erro:
        return {
            "saudavel": False,
            "estado": "telemetria_indisponivel",
            "erro": f"{type(erro).__name__}: {erro}"[:300],
            "eventos": (),
            "linhas": 0,
            "linhas_invalidas": 0,
        }
    return {
        "saudavel": True,
        "estado": "carregada",
        "erro": None,
        "eventos": eventos,
        "linhas": linhas,
        "linhas_invalidas": invalidas,
    }


def _inteiro_nao_negativo(valor):
    try:
        return max(int(valor or 0), 0)
    except (TypeError, ValueError):
        return 0


def _numero_nao_negativo(valor):
    try:
        numero = float(valor or 0)
        return numero if math.isfinite(numero) and numero >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _periodos_manutencao(eventos, *, modo_manutencao, agora):
    """Reconstrói pausas explícitas, inclusive a pausa ainda aberta."""
    marcos = []
    for evento in eventos or ():
        if evento.get("evento") not in (
            EVENTOS_INICIO_MANUTENCAO | EVENTOS_FIM_MANUTENCAO
        ):
            continue
        try:
            instante = _instante(evento.get("em"))
        except (AttributeError, TypeError, ValueError):
            continue
        if instante <= agora:
            marcos.append((instante, evento.get("evento")))
    marcos.sort(key=lambda item: item[0])

    periodos = []
    inicio_aberto = None
    for instante, evento in marcos:
        if evento in EVENTOS_INICIO_MANUTENCAO:
            if inicio_aberto is None:
                inicio_aberto = instante
        elif inicio_aberto is not None:
            if instante > inicio_aberto:
                periodos.append((inicio_aberto, instante))
            inicio_aberto = None

    modo = dict(modo_manutencao or {})
    if modo.get("ativo"):
        try:
            solicitado = _instante(modo.get("solicitado_em"))
        except (TypeError, ValueError):
            solicitado = None
        if solicitado is not None and solicitado <= agora:
            if inicio_aberto is None:
                inicio_aberto = solicitado
            else:
                inicio_aberto = min(inicio_aberto, solicitado)
    if inicio_aberto is not None and inicio_aberto < agora:
        periodos.append((inicio_aberto, agora))
    consolidados = []
    for inicio, fim in sorted(periodos, key=lambda item: item[0]):
        if not consolidados or inicio > consolidados[-1][1]:
            consolidados.append([inicio, fim])
        else:
            consolidados[-1][1] = max(consolidados[-1][1], fim)
    return [tuple(periodo) for periodo in consolidados]


def _sobreposicao_manutencao(inicio, fim, periodos):
    segundos = 0.0
    ocorrencias = 0
    for inicio_pausa, fim_pausa in periodos:
        sobreposicao = (
            min(fim, fim_pausa) - max(inicio, inicio_pausa)
        ).total_seconds()
        if sobreposicao > 0:
            segundos += sobreposicao
            ocorrencias += 1
    return segundos, ocorrencias


def _exposicao_confirmada(ciclos, *, inicio, periodos_manutencao):
    """Conta somente faixas sustentadas por ciclos próximos entre si."""
    intervalos = []
    for instante, evento in ciclos:
        duracao = min(
            _numero_nao_negativo(evento.get("duracao_segundos")),
            LIMITE_SEM_CICLO_SEGUNDOS,
        )
        inicio_ciclo = max(
            instante - timedelta(seconds=duracao),
            inicio,
        )
        if not intervalos:
            intervalos.append([inicio_ciclo, instante])
            continue
        anterior = intervalos[-1]
        if (
            instante - anterior[1]
        ).total_seconds() <= LIMITE_SEM_CICLO_SEGUNDOS:
            anterior[1] = max(anterior[1], instante)
        else:
            intervalos.append([inicio_ciclo, instante])

    segundos = 0.0
    for inicio_intervalo, fim_intervalo in intervalos:
        bruto = max(
            (fim_intervalo - inicio_intervalo).total_seconds(), 0.0
        )
        pausa, _ = _sobreposicao_manutencao(
            inicio_intervalo, fim_intervalo, periodos_manutencao
        )
        segundos += max(bruto - pausa, 0.0)

    cobertura_desde_ancora = False
    lacuna_operacional = None
    if intervalos:
        primeira_faixa = intervalos[0][0]
        bruto_lacuna = max((primeira_faixa - inicio).total_seconds(), 0.0)
        pausa_lacuna, _ = _sobreposicao_manutencao(
            inicio, primeira_faixa, periodos_manutencao
        )
        lacuna_operacional = max(bruto_lacuna - pausa_lacuna, 0.0)
        cobertura_desde_ancora = (
            lacuna_operacional <= LIMITE_SEM_CICLO_SEGUNDOS
        )
    return segundos, cobertura_desde_ancora, lacuna_operacional


def resumir_exposicao(
    eventos, *, ancora, modo_manutencao=None, agora=None,
    telemetria_saudavel=True,
):
    """Resume trabalho confirmado; tempo de parede nunca vira amostra."""
    agora = agora or datetime.now()
    try:
        agora = _instante(agora.isoformat())
        inicio = _instante(ancora)
    except (AttributeError, TypeError, ValueError):
        return aplicar_efeitos_desativados({
            "versao": VERSAO,
            "estado": "ancora_invalida",
            "ancora": ancora,
            "saudavel": False,
            "requer_atencao": True,
            "relogio_amostra_iniciou": False,
        })
    if inicio > agora:
        return aplicar_efeitos_desativados({
            "versao": VERSAO,
            "estado": "ancora_futura",
            "ancora": str(ancora),
            "saudavel": False,
            "requer_atencao": True,
            "relogio_amostra_iniciou": False,
        })

    selecionados = []
    for evento in eventos or ():
        try:
            instante = _instante(evento.get("em"))
        except (AttributeError, TypeError, ValueError):
            continue
        if inicio <= instante <= agora:
            selecionados.append((instante, evento))
    selecionados.sort(key=lambda item: item[0])
    ciclos = [
        (instante, evento) for instante, evento in selecionados
        if evento.get("evento") == "ciclo_concluido"
    ]
    falhas = [
        evento for _, evento in selecionados
        if evento.get("evento") == "ciclo_falhou"
    ]
    modo = dict(modo_manutencao or {})
    manutencao_ativa = bool(modo.get("ativo"))
    manutencao_confiavel = not (
        manutencao_ativa
        and modo.get("motivo") == "arquivo_manutencao_invalido"
    )
    solicitado = None
    try:
        solicitado = _instante(modo.get("solicitado_em"))
    except (TypeError, ValueError):
        pass
    periodos_manutencao = _periodos_manutencao(
        eventos,
        modo_manutencao=modo,
        agora=agora,
    ) if manutencao_confiavel else []
    (
        exposicao_confirmada_segundos,
        cobertura_desde_ancora,
        lacuna_operacional_segundos,
    ) = _exposicao_confirmada(
        ciclos,
        inicio=inicio,
        periodos_manutencao=periodos_manutencao,
    )
    ancora_durante_manutencao = any(
        inicio_pausa <= inicio <= fim_pausa
        for inicio_pausa, fim_pausa in periodos_manutencao
    )
    idade_parede = max((agora - inicio).total_seconds(), 0.0)
    pausa_segundos, pausas = _sobreposicao_manutencao(
        inicio, agora, periodos_manutencao
    )
    idade_operacional = max(idade_parede - pausa_segundos, 0.0)

    partidas = sum(
        _inteiro_nao_negativo(item.get("partidas")) for _, item in ciclos
    )
    tarefas = sum(
        _inteiro_nao_negativo(item.get("tarefas_processadas"))
        for _, item in ciclos
    )
    duracao = sum(
        _numero_nao_negativo(item.get("duracao_segundos"))
        for _, item in ciclos
    )
    comparacoes = sum(
        len(item.get("comparacoes_fontes_odds") or [])
        for _, item in ciclos
        if isinstance(item.get("comparacoes_fontes_odds"), list)
    )
    betsapi_pareadas = sum(
        _inteiro_nao_negativo(
            (item.get("betsapi") or {}).get("partidas_pareadas")
        )
        for _, item in ciclos
    )
    betsapi_consultadas = sum(
        _inteiro_nao_negativo(
            (item.get("betsapi") or {}).get("partidas_consultadas")
        )
        for _, item in ciclos
    )
    betsapi_mercados = sum(
        _inteiro_nao_negativo(
            (item.get("betsapi") or {}).get("mercados_anexados")
        )
        for _, item in ciclos
    )

    if not telemetria_saudavel:
        estado = "telemetria_indisponivel"
        requer_atencao = True
        esperado_sem_dados = False
    elif manutencao_ativa and not manutencao_confiavel:
        estado = "estado_manutencao_invalido"
        requer_atencao = True
        esperado_sem_dados = False
    elif ciclos:
        estado = (
            "exposicao_observada_antes_da_pausa"
            if manutencao_ativa else "exposicao_observada"
        )
        requer_atencao = False
        esperado_sem_dados = False
    elif manutencao_ativa and ancora_durante_manutencao:
        estado = "sem_exposicao_manutencao_planejada"
        requer_atencao = False
        esperado_sem_dados = True
    elif manutencao_ativa and idade_operacional <= LIMITE_SEM_CICLO_SEGUNDOS:
        estado = "pausado_sem_ciclo_apos_ancora"
        requer_atencao = False
        esperado_sem_dados = True
    elif idade_operacional <= LIMITE_SEM_CICLO_SEGUNDOS:
        estado = "aguardando_primeiro_ciclo"
        requer_atencao = False
        esperado_sem_dados = True
    else:
        estado = (
            "sem_ciclo_antes_da_pausa_requer_atencao"
            if manutencao_ativa else
            "sem_ciclo_apos_ancora_requer_atencao"
        )
        requer_atencao = True
        esperado_sem_dados = False

    return aplicar_efeitos_desativados({
        "versao": VERSAO,
        "estado": estado,
        "saudavel": bool(telemetria_saudavel and not requer_atencao),
        "ancora": inicio.isoformat(),
        "agora": agora.isoformat(),
        "idade_parede_horas": round(idade_parede / 3600.0, 3),
        "idade_operacional_horas": round(idade_operacional / 3600.0, 3),
        "exposicao_operacional_confirmada_horas": round(
            exposicao_confirmada_segundos / 3600.0, 3
        ),
        "cobertura_telemetria_desde_ancora": cobertura_desde_ancora,
        "lacuna_operacional_antes_da_telemetria_horas": (
            round(lacuna_operacional_segundos / 3600.0, 3)
            if lacuna_operacional_segundos is not None else None
        ),
        "manutencao_excluida_horas": round(pausa_segundos / 3600.0, 3),
        "pausas_manutencao_apos_ancora": pausas,
        "relogio_amostra_iniciou": bool(ciclos),
        "esperado_sem_dados": esperado_sem_dados,
        "requer_atencao": requer_atencao,
        "manutencao_ativa": manutencao_ativa,
        "manutencao_confiavel": manutencao_confiavel,
        "manutencao_solicitada_em": (
            solicitado.isoformat() if solicitado is not None else None
        ),
        "ancora_durante_manutencao": ancora_durante_manutencao,
        "ciclos_concluidos": len(ciclos),
        "ciclos_falhos": len(falhas),
        "ciclos_com_partidas": sum(
            int(_inteiro_nao_negativo(item.get("partidas")) > 0)
            for _, item in ciclos
        ),
        "partidas_somadas": partidas,
        "tarefas_processadas": tarefas,
        "duracao_processamento_confirmada_segundos": round(duracao, 3),
        "comparacoes_fontes_odds": comparacoes,
        "betsapi_partidas_pareadas": betsapi_pareadas,
        "betsapi_partidas_consultadas": betsapi_consultadas,
        "betsapi_mercados_anexados": betsapi_mercados,
        "primeiro_ciclo_em": ciclos[0][0].isoformat() if ciclos else None,
        "ultimo_ciclo_em": ciclos[-1][0].isoformat() if ciclos else None,
    })


def _ancoras_avaliacao(avaliacao):
    ancoras = {}
    if avaliacao.get("ancora_prospectiva_em"):
        ancoras["principal"] = avaliacao["ancora_prospectiva_em"]
    for nome, chave in (
        ("desajuste_executavel", "recorte_observacional_executavel"),
        ("convergencia_gols", "recorte_convergencia_preco_prospectivo"),
        (
            "convergencia_escanteios",
            "recorte_convergencia_escanteios_prospectivo",
        ),
    ):
        recorte = avaliacao.get(chave) or {}
        if recorte.get("ancora_pre_registrada_em"):
            ancoras[nome] = recorte["ancora_pre_registrada_em"]
    return ancoras


def enriquecer_avaliacao_com_exposicao(
    avaliacao, *, pasta, modo_manutencao=None, agora=None,
):
    """Anexa relogios separados sem alterar decisao, coorte ou sinal."""
    resultado = dict(avaliacao or {})
    ancoras = _ancoras_avaliacao(resultado)
    if not ancoras:
        resultado["exposicao_coleta_prospectiva"] = (
            aplicar_efeitos_desativados({
                "versao": VERSAO,
                "estado": "sem_ancora_prospectiva",
                "saudavel": True,
                "por_coorte": {},
                "requer_atencao": False,
            })
        )
        return resultado
    carregamento = carregar_eventos_observabilidade(
        Path(pasta) / "monitor_eventos.jsonl"
    )
    por_coorte = {
        nome: resumir_exposicao(
            carregamento.get("eventos") or (),
            ancora=ancora,
            modo_manutencao=modo_manutencao,
            agora=agora,
            telemetria_saudavel=carregamento.get("saudavel") is True,
        )
        for nome, ancora in ancoras.items()
    }
    requer_atencao = any(
        item.get("requer_atencao") for item in por_coorte.values()
    )
    observadas = sum(
        int(bool(item.get("relogio_amostra_iniciou")))
        for item in por_coorte.values()
    )
    pausadas = sum(
        int(item.get("estado") == "sem_exposicao_manutencao_planejada")
        for item in por_coorte.values()
    )
    if requer_atencao:
        estado = "exposicao_requer_atencao"
    elif observadas and pausadas:
        estado = "exposicao_parcial_com_coortes_em_pausa"
    elif observadas:
        estado = "exposicao_observada"
    elif pausadas == len(por_coorte):
        estado = "sem_exposicao_manutencao_planejada"
    else:
        estado = "aguardando_exposicao"
    resultado["exposicao_coleta_prospectiva"] = (
        aplicar_efeitos_desativados({
            "versao": VERSAO,
            "estado": estado,
            "saudavel": bool(
                carregamento.get("saudavel") and not requer_atencao
            ),
            "fonte": "monitor_eventos.jsonl",
            "linhas_lidas": carregamento.get("linhas", 0),
            "linhas_invalidas": carregamento.get("linhas_invalidas", 0),
            "erro": carregamento.get("erro"),
            "coortes": len(por_coorte),
            "coortes_com_exposicao": observadas,
            "coortes_sem_exposicao_por_manutencao": pausadas,
            "requer_atencao": requer_atencao,
            "por_coorte": por_coorte,
        })
    )
    return resultado
