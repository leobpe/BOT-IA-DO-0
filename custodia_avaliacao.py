"""Envelope persistente comum para avaliacoes periodicas observacionais."""

from __future__ import annotations

import math
from datetime import datetime, timezone

VERSAO_CUSTODIA = "custodia-execucao-avaliacao-v3"
ESTADO_CONCLUIDO = "concluida"
ESTADO_EM_ANDAMENTO = "em_execucao"
ESTADO_FALHA = "falha"
ESTADOS_CONHECIDOS = frozenset({
    ESTADO_CONCLUIDO,
    ESTADO_EM_ANDAMENTO,
    ESTADO_FALHA,
})
LIMITE_EXECUCAO_SEGUNDOS = 600.0
TOLERANCIA_FUTURO_SEGUNDOS = 60.0
TOLERANCIA_FINALIZACAO_SEGUNDOS = 1.0

EFEITOS_DESATIVADOS = {
    "aplicacao_sinais": False,
    "altera_calibracao": False,
    "altera_prioridade": False,
    "promocao_automatica": False,
    "reativacao_automatica": False,
    "telegram": False,
}


def aplicar_efeitos_desativados(dados=None):
    """Normaliza uma resposta observacional sem confiar no avaliador."""
    resultado = dict(dados or {})
    resultado.update(EFEITOS_DESATIVADOS)
    return resultado


def auditar_efeitos_desativados(dados):
    """Exige contrato explicito: todo efeito existe e vale False."""
    ausentes = sorted(
        chave for chave in EFEITOS_DESATIVADOS if chave not in dados
    )
    invalidos = sorted(
        chave for chave in EFEITOS_DESATIVADOS
        if chave in dados and dados.get(chave) is not False
    )
    return {
        "versao": "efeitos-avaliacao-observacional-v1",
        "valida": not ausentes and not invalidos,
        "campos_esperados": sorted(EFEITOS_DESATIVADOS),
        "campos_ausentes": ausentes,
        "campos_invalidos": invalidos,
    }


def construir_estado_nao_concluido(
    *, versao_avaliacao, modo, estado_execucao,
    atualizado_em, iniciado_em, finalizado_em=None,
    duracao_segundos=None, motivo_falha=None,
    tipo_erro=None, erro=None,
):
    """Cria estado sem copiar conclusoes ou amostras da rodada anterior."""
    if estado_execucao not in {ESTADO_EM_ANDAMENTO, ESTADO_FALHA}:
        raise ValueError("estado de execucao nao concluida invalido")
    estado = {
        "versao": str(versao_avaliacao),
        "custodia_execucao_versao": VERSAO_CUSTODIA,
        "modo": str(modo),
        "estado_execucao": estado_execucao,
        "atualizado_em": str(atualizado_em),
        "iniciado_em": str(iniciado_em),
        **EFEITOS_DESATIVADOS,
    }
    if estado_execucao == ESTADO_FALHA:
        estado.update({
            "estado": "falha_avaliacao",
            "motivo": str(
                motivo_falha or "avaliacao_periodica_falhou"
            ),
            "finalizado_em": str(finalizado_em or atualizado_em),
            "duracao_segundos": (
                round(max(float(duracao_segundos), 0.0), 3)
                if duracao_segundos is not None else None
            ),
            "tipo_erro": str(tipo_erro or "ErroAvaliacao")[:120],
            "erro": str(erro or "falha sem detalhe")[:500],
        })
    return estado


def classificar_execucao(estado_execucao, idade_segundos):
    """Classifica custodia sem interpretar qualquer resultado estatistico."""
    if estado_execucao == ESTADO_CONCLUIDO:
        return "concluida"
    if estado_execucao == ESTADO_FALHA:
        return "falha"
    if estado_execucao == ESTADO_EM_ANDAMENTO:
        try:
            idade_segundos = float(idade_segundos)
            if not math.isfinite(idade_segundos) or idade_segundos < 0:
                raise ValueError
        except (TypeError, ValueError):
            return "invalida"
        if idade_segundos > LIMITE_EXECUCAO_SEGUNDOS:
            return "interrompida"
        return "em_execucao"
    return "invalida"


def _instante_normalizado(valor):
    instante = datetime.fromisoformat(str(valor))
    if instante.tzinfo is not None:
        instante = instante.astimezone(timezone.utc).replace(tzinfo=None)
    return instante


def auditar_cronologia_execucao(dados, *, agora=None):
    """Recalcula a cronologia sem confiar na idade informada no documento."""
    agora = agora or datetime.now()
    if agora.tzinfo is not None:
        agora = agora.astimezone(timezone.utc).replace(tzinfo=None)
    problemas = []
    instantes = {}
    for chave in ("atualizado_em", "iniciado_em"):
        try:
            instantes[chave] = _instante_normalizado(dados[chave])
        except (KeyError, TypeError, ValueError):
            problemas.append(f"{chave}_invalido")
    estado = dados.get("estado_execucao")
    exige_final = estado in {ESTADO_CONCLUIDO, ESTADO_FALHA}
    if exige_final:
        try:
            instantes["finalizado_em"] = _instante_normalizado(
                dados["finalizado_em"]
            )
        except (KeyError, TypeError, ValueError):
            problemas.append("finalizado_em_invalido")
    elif dados.get("finalizado_em") not in (None, ""):
        problemas.append("finalizacao_antes_da_conclusao")

    atualizado = instantes.get("atualizado_em")
    iniciado = instantes.get("iniciado_em")
    finalizado = instantes.get("finalizado_em")
    idade = None
    desvio_futuro = None
    if atualizado is not None:
        delta = (agora - atualizado).total_seconds()
        idade = max(delta, 0.0)
        desvio_futuro = max(-delta, 0.0)
        if desvio_futuro > TOLERANCIA_FUTURO_SEGUNDOS:
            problemas.append("atualizado_em_futuro")
    if iniciado is not None:
        futuro_inicio = (iniciado - agora).total_seconds()
        if futuro_inicio > TOLERANCIA_FUTURO_SEGUNDOS:
            problemas.append("iniciado_em_futuro")
        if atualizado is not None and iniciado > atualizado:
            problemas.append("inicio_posterior_atualizacao")
    duracao_parede = None
    if finalizado is not None:
        futuro_fim = (finalizado - agora).total_seconds()
        if futuro_fim > TOLERANCIA_FUTURO_SEGUNDOS:
            problemas.append("finalizado_em_futuro")
        if iniciado is not None:
            duracao_parede = (finalizado - iniciado).total_seconds()
            if duracao_parede < 0:
                problemas.append("finalizacao_anterior_inicio")
        if atualizado is not None and abs(
            (atualizado - finalizado).total_seconds()
        ) > TOLERANCIA_FINALIZACAO_SEGUNDOS:
            problemas.append("finalizacao_divergente_atualizacao")
    duracao = dados.get("duracao_segundos")
    if exige_final:
        try:
            duracao = float(duracao)
            if not math.isfinite(duracao) or duracao < 0:
                raise ValueError
        except (TypeError, ValueError):
            problemas.append("duracao_segundos_invalida")
            duracao = None
    elif duracao not in (None, ""):
        problemas.append("duracao_antes_da_conclusao")

    problemas = sorted(set(problemas))
    return {
        "versao": "cronologia-execucao-avaliacao-v1",
        "valida": not problemas,
        "problemas": problemas,
        "idade_segundos": (
            round(idade, 3) if idade is not None else None
        ),
        "desvio_futuro_segundos": (
            round(desvio_futuro, 3)
            if desvio_futuro is not None else None
        ),
        "duracao_parede_segundos": (
            round(duracao_parede, 3)
            if duracao_parede is not None else None
        ),
        "duracao_monotonic_segundos": (
            round(duracao, 3) if duracao is not None else None
        ),
        "tolerancia_futuro_segundos": TOLERANCIA_FUTURO_SEGUNDOS,
    }
