"""Mede, em sombra, se contadores API já coletados resgatariam qualidade."""

from collections import Counter
from datetime import datetime, timedelta
import json

from qualidade_dados import avaliar_qualidade, extrair_minuto, extrair_placar


VERSAO_RES_GATE = "resgate-qualidade-api-live-sombra-v1"
IDADE_MAXIMA_SEGUNDOS = 300.0
QUALIDADE_ALVO = 80.0
_CAMPOS_API = {
    "Chutes": ("chutes_mandante", "chutes_visitante"),
    "Chutes no gol": (
        "chutes_gol_mandante", "chutes_gol_visitante"
    ),
    "Escanteios": ("escanteios_mandante", "escanteios_visitante"),
}


def _instante(valor):
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    return datetime.fromisoformat(str(valor)).replace(tzinfo=None)


def _janela_gols(jogo):
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    return bool(
        minuto is not None
        and placar is not None
        and (
            (placar == [0, 0] and 5 <= minuto <= 28)
            or 46 <= minuto <= 82
        )
    )


def elegivel_coleta_resgate_qualidade(jogo):
    """Seleciona somente janelas em que o resgate poderá ser medido."""
    return _janela_gols(jogo)


def _numero(valor):
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _formatar_par(casa, fora):
    def formatar(valor):
        return str(int(valor)) if float(valor).is_integer() else str(valor)

    return f"{formatar(casa)}-{formatar(fora)}"


def avaliar_resgate_qualidade_api(
    conexao, jogo, confirmacao_api, estatisticas, qualidade, agora=None
):
    """Retorna evidência observacional; nunca altera estatísticas ou sinais."""
    agora = _instante(agora or datetime.now())
    base = {
        "versao": VERSAO_RES_GATE,
        "estado": "nao_elegivel",
        "aplicacao_sinais": False,
        "telegram": False,
        "chamadas_api_adicionais": 0,
        "qualidade_original": (qualidade or {}).get("pontuacao"),
        "qualidade_alvo": QUALIDADE_ALVO,
        "campos_complementados": [],
    }
    if not _janela_gols(jogo):
        base["motivo"] = "fora_janela_gols_antecipados"
        return base
    if (qualidade or {}).get("divergencia_critica") is True:
        base["motivo"] = "divergencia_critica"
        return base
    try:
        nota = float((qualidade or {}).get("pontuacao") or 0)
    except (TypeError, ValueError):
        nota = 0.0
    if nota >= QUALIDADE_ALVO:
        base.update({"estado": "dispensado", "motivo": "qualidade_ja_suficiente"})
        return base
    fixture_id = (confirmacao_api or {}).get("fixture_id")
    url = (jogo or {}).get("url")
    if fixture_id is None or not url:
        base["motivo"] = "pareamento_api_ausente"
        return base
    linha = conexao.execute(
        """
        SELECT * FROM historico_api_live
        WHERE fixture_id=? AND packball_url=?
        ORDER BY datetime(coletado_em) DESC, id DESC
        LIMIT 1
        """,
        (fixture_id, url),
    ).fetchone()
    if linha is None:
        base.update({"estado": "avaliado", "motivo": "sem_snapshot_api"})
        return base
    snapshot = dict(linha)
    try:
        idade = (agora - _instante(snapshot["coletado_em"])).total_seconds()
    except (KeyError, TypeError, ValueError):
        idade = None
    base["idade_snapshot_segundos"] = (
        round(idade, 3) if idade is not None else None
    )
    if idade is None or idade < -60 or idade > IDADE_MAXIMA_SEGUNDOS:
        base.update({"estado": "avaliado", "motivo": "snapshot_api_desatualizado"})
        return base
    minuto_packball = extrair_minuto((jogo or {}).get("status"))
    minuto_api = _numero(snapshot.get("minuto"))
    if (
        minuto_packball is not None and minuto_api is not None
        and abs(float(minuto_packball) - minuto_api) > 5
    ):
        base.update({"estado": "avaliado", "motivo": "minuto_api_incompativel"})
        return base

    combinadas = dict(estatisticas or {})
    ausentes = set((qualidade or {}).get("campos_ausentes") or [])
    for campo, (campo_casa, campo_fora) in _CAMPOS_API.items():
        if campo not in ausentes:
            continue
        casa = _numero(snapshot.get(campo_casa))
        fora = _numero(snapshot.get(campo_fora))
        if casa is None or fora is None:
            continue
        combinadas[campo] = _formatar_par(casa, fora)
        base["campos_complementados"].append(campo)
    if not base["campos_complementados"]:
        base.update({"estado": "avaliado", "motivo": "sem_campo_equivalente_api"})
        return base
    qualidade_sombra = avaliar_qualidade(
        jogo, combinadas, confirmacao_api
    )
    nota_sombra = float(qualidade_sombra.get("pontuacao") or 0)
    base.update({
        "estado": "resgatado" if nota_sombra >= QUALIDADE_ALVO else "avaliado",
        "motivo": (
            "qualidade_resgatada_sombra"
            if nota_sombra >= QUALIDADE_ALVO
            else "qualidade_ainda_insuficiente"
        ),
        "qualidade_sombra": nota_sombra,
        "campos_ainda_ausentes": list(
            qualidade_sombra.get("campos_ausentes") or []
        ),
        "proveniencia": "api_football_historico_live_persistido",
    })
    return base


def resumir_resgate_qualidade_api(conexao, horas=24, agora=None):
    """Resume evidências persistidas sem reavaliar nem alterar snapshots."""
    agora = _instante(agora or datetime.now())
    desde = (agora - timedelta(hours=max(float(horas), 0.0))).isoformat()
    linhas = conexao.execute(
        """
        SELECT partida_id, coletado_em, qualidade_json
        FROM snapshots
        WHERE datetime(coletado_em) >= datetime(?)
          AND qualidade_json LIKE '%resgate_qualidade_api_sombra%'
        ORDER BY datetime(coletado_em), id
        """,
        (desde,),
    ).fetchall()
    estados = Counter()
    motivos = Counter()
    campos = Counter()
    partidas_elegiveis = set()
    ganhos = []
    primeira = ultima = None
    registros = elegiveis = resgatadas = 0
    for linha in linhas:
        try:
            qualidade = json.loads(linha["qualidade_json"] or "{}")
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
        diagnostico = qualidade.get("resgate_qualidade_api_sombra") or {}
        if not isinstance(diagnostico, dict) or not diagnostico:
            continue
        registros += 1
        estado = str(diagnostico.get("estado") or "desconhecido")
        motivo = str(diagnostico.get("motivo") or "sem_motivo")
        estados[estado] += 1
        motivos[motivo] += 1
        instante = str(linha["coletado_em"])
        primeira = primeira or instante
        ultima = instante
        if estado not in {"avaliado", "resgatado"}:
            continue
        elegiveis += 1
        partidas_elegiveis.add(linha["partida_id"])
        if estado == "resgatado":
            resgatadas += 1
        for campo in diagnostico.get("campos_complementados") or []:
            campos[str(campo)] += 1
        try:
            original = float(diagnostico.get("qualidade_original"))
            sombra = float(diagnostico.get("qualidade_sombra"))
        except (TypeError, ValueError):
            continue
        ganhos.append(sombra - original)
    jogos = len(partidas_elegiveis)
    return {
        "versao": VERSAO_RES_GATE,
        "janela_horas": float(horas),
        "registros": registros,
        "elegiveis": elegiveis,
        "jogos_distintos": jogos,
        "resgatadas": resgatadas,
        "taxa_resgate": (
            round(resgatadas / elegiveis, 4) if elegiveis else None
        ),
        "ganho_medio_qualidade": (
            round(sum(ganhos) / len(ganhos), 3) if ganhos else None
        ),
        "estados": dict(sorted(estados.items())),
        "motivos": dict(sorted(motivos.items())),
        "campos_complementados": dict(sorted(campos.items())),
        "primeira_observacao": primeira,
        "ultima_observacao": ultima,
        "pronto_para_revisao": bool(elegiveis >= 30 and jogos >= 10),
        "criterio_revisao": {"elegiveis": 30, "jogos_distintos": 10},
        "aplicacao_sinais": False,
        "promocao_automatica": False,
    }
