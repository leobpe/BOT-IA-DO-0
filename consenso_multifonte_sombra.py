"""Consenso prospectivo API-Football + TheStats sem detalhe PackBall.

O módulo produz somente evidência de pesquisa. A lista do PackBall continua
identificando a partida, mas nenhuma decisão gerada aqui pode ir ao Telegram,
à calibração ou promover/substituir uma regra automaticamente.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import re


VERSAO_CONSENSO_MULTIFONTE_SOMBRA = (
    "consenso-api-football-thestats-sem-packball-v1"
)
VERSAO_POLITICA_CONSENSO = "politica-consenso-multifonte-sombra-v1"
TOLERANCIAS = {
    "chutes": 2.0,
    "chutes_gol": 1.0,
    "escanteios": 1.0,
}


def registrar_ou_validar_consenso_multifonte(conexao, iniciado_em=None):
    """Ancora a hipótese antes da primeira observação prospectiva."""
    chave = f"consenso_multifonte_sombra:definicao:{VERSAO_CONSENSO_MULTIFONTE_SOMBRA}"
    definicao = {
        "versao": VERSAO_CONSENSO_MULTIFONTE_SOMBRA,
        "politica": VERSAO_POLITICA_CONSENSO,
        "iniciado_em": str(
            iniciado_em or datetime.now().replace(microsecond=0).isoformat()
        ),
        "fontes": ["api_football", "thestatsapi"],
        "packball": "somente_identidade_lista_sem_detalhe",
        "mercados": ["gol_ft", "gol_ht"],
        "tolerancias": dict(TOLERANCIAS),
        "minimo_resultados_futuros": 70,
        "coorte_alvo": 75,
        "telegram": False,
        "calibracao": False,
        "promocao_automatica": False,
        "rollback": "CONSENSO_MULTIFONTE_SOMBRA_ATIVO=0",
    }
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"] if hasattr(linha, "keys") else linha[0])
        comparaveis = dict(existente)
        comparaveis.pop("iniciado_em", None)
        esperado = dict(definicao)
        esperado.pop("iniciado_em", None)
        if comparaveis != esperado:
            raise RuntimeError("Definição do consenso multifonte foi alterada.")
        return existente
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (chave, json.dumps(definicao, ensure_ascii=False, sort_keys=True)),
        )
    return definicao


def _par_placar(valor):
    numeros = re.findall(r"\d+", str(valor or ""))
    if len(numeros) < 2:
        return None
    return [int(numeros[0]), int(numeros[1])]


def _minuto(valor):
    numeros = re.findall(r"\d{1,3}", str(valor or ""))
    return int(numeros[0]) if numeros else None


def _idade_segundos(valor, agora):
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        referencia = agora
        if instante.tzinfo is not None and referencia.tzinfo is None:
            referencia = referencia.astimezone()
        elif instante.tzinfo is None and referencia.tzinfo is not None:
            instante = instante.replace(tzinfo=referencia.tzinfo)
        return max((referencia - instante).total_seconds(), 0.0)
    except (TypeError, ValueError):
        return None


def _placar_api(fixture, orientacao):
    gols = (fixture or {}).get("goals") or {}
    valores = [gols.get("home"), gols.get("away")]
    if any(valor is None for valor in valores):
        return None
    valores = [int(valor) for valor in valores]
    return list(reversed(valores)) if orientacao == "invertida" else valores


def validar_consenso_multifonte(
    jogo, fixture_api, snapshot_api, snapshot_thestats, *, agora=None
):
    """Falha fechado quando as duas APIs descrevem estados incompatíveis."""
    agora = agora or datetime.now().astimezone()
    diagnostico = {
        "versao": VERSAO_POLITICA_CONSENSO,
        "valido": False,
        "conflitos": [],
        "aplicacao_sinais": False,
        "telegram": False,
        "calibracao": False,
        "promocao_automatica": False,
    }
    if not isinstance(snapshot_api, dict) or not snapshot_api.get("completo"):
        diagnostico["motivo"] = "api_football_incompleta"
        return diagnostico
    if not isinstance(snapshot_thestats, dict):
        diagnostico["motivo"] = "thestats_ausente"
        return diagnostico
    if snapshot_thestats.get("fonte") != "thestatsapi":
        diagnostico["motivo"] = "fonte_thestats_invalida"
        return diagnostico
    url = (jogo or {}).get("url")
    if (
        snapshot_api.get("packball_url") != url
        or snapshot_thestats.get("packball_url") != url
    ):
        diagnostico["motivo"] = "partida_incompativel"
        return diagnostico

    idade_api = _idade_segundos(snapshot_api.get("coletado_em"), agora)
    idade_ts = _idade_segundos(snapshot_thestats.get("coletado_em"), agora)
    diagnostico["idade_api_segundos"] = idade_api
    diagnostico["idade_thestats_segundos"] = idade_ts
    if idade_api is None or idade_api > 90:
        diagnostico["motivo"] = "api_football_desatualizada"
        return diagnostico
    if idade_ts is None or idade_ts > 90:
        diagnostico["motivo"] = "thestats_desatualizada"
        return diagnostico

    orientacao = snapshot_api.get("orientacao") or "direta"
    placares = {
        "packball_lista": _par_placar((jogo or {}).get("placar")),
        "api_football": _placar_api(fixture_api, orientacao),
        "thestatsapi": list(snapshot_thestats.get("placar") or []),
    }
    diagnostico["placares"] = placares
    if any(len(valor or []) != 2 for valor in placares.values()):
        diagnostico["motivo"] = "placar_indeterminado"
        return diagnostico
    if len({tuple(valor) for valor in placares.values()}) != 1:
        diagnostico["motivo"] = "placar_divergente"
        return diagnostico

    minutos = {
        "packball_lista": _minuto((jogo or {}).get("status")),
        "api_football": snapshot_api.get("minuto"),
        "thestatsapi": snapshot_thestats.get("minuto"),
    }
    diagnostico["minutos"] = minutos
    if any(valor is None for valor in minutos.values()):
        diagnostico["motivo"] = "minuto_indeterminado"
        return diagnostico
    if max(int(v) for v in minutos.values()) - min(
        int(v) for v in minutos.values()
    ) > 2:
        diagnostico["motivo"] = "minuto_divergente"
        return diagnostico
    if snapshot_api.get("periodo") != snapshot_thestats.get("periodo"):
        diagnostico["motivo"] = "periodo_divergente"
        return diagnostico

    campos = {
        "chutes": ("chutes_mandante", "chutes_visitante"),
        "chutes_gol": (
            "chutes_gol_mandante", "chutes_gol_visitante"
        ),
        "escanteios": (
            "escanteios_mandante", "escanteios_visitante"
        ),
    }
    metricas = {}
    for metrica, nomes in campos.items():
        api = [snapshot_api.get(nome) for nome in nomes]
        ts = [snapshot_thestats.get(nome) for nome in nomes]
        if any(valor is None for valor in (*api, *ts)):
            diagnostico["motivo"] = f"{metrica}_incompleta"
            return diagnostico
        diferencas = [abs(float(a) - float(b)) for a, b in zip(api, ts)]
        metricas[metrica] = {
            "api_football": api,
            "thestatsapi": ts,
            "diferencas": diferencas,
        }
        if any(d > TOLERANCIAS[metrica] for d in diferencas):
            diagnostico["conflitos"].append(metrica)
    diagnostico["metricas"] = metricas
    if diagnostico["conflitos"]:
        diagnostico["motivo"] = "metricas_divergentes"
        return diagnostico

    diagnostico.update({
        "valido": True,
        "motivo": "consenso_confirmado",
        "xg_thestatsapi": [
            snapshot_thestats.get("xg_mandante"),
            snapshot_thestats.get("xg_visitante"),
        ],
    })
    return diagnostico


def estatisticas_do_consenso(snapshot_api, snapshot_thestats):
    """Usa contadores API confirmados pela TheStats, sem inventar pressão."""
    return {
        "Chutes": (
            f"{snapshot_api['chutes_mandante']} - "
            f"{snapshot_api['chutes_visitante']}"
        ),
        "Chutes no gol": (
            f"{snapshot_api['chutes_gol_mandante']} - "
            f"{snapshot_api['chutes_gol_visitante']}"
        ),
        "Escanteios": (
            f"{snapshot_api['escanteios_mandante']} - "
            f"{snapshot_api['escanteios_visitante']}"
        ),
        "xG TheStats": (
            f"{snapshot_thestats.get('xg_mandante')} - "
            f"{snapshot_thestats.get('xg_visitante')}"
        ),
    }


def isolar_candidatos_consenso(candidatos, diagnostico):
    """Mantém apenas gols que a regra atual aprovaria, sempre como sombra."""
    isolados = []
    for original in candidatos or []:
        if original.get("mercado") not in {"gol_ft", "gol_ht"}:
            continue
        if original.get("status") != "aprovado":
            continue
        candidato = deepcopy(original)
        candidato["status"] = "simulacao"
        candidato["probabilidade_calibrada"] = None
        features = candidato.setdefault("features", {})
        features["exploracao_sombra"] = {
            "versao": VERSAO_CONSENSO_MULTIFONTE_SOMBRA,
            "aplicacao_automatica": False,
            "telegram_oficial": False,
            "grupo_teste": False,
        }
        features["consenso_multifonte"] = deepcopy(diagnostico)
        candidato.setdefault("motivos", []).append(
            "consenso_api_football_thestats_sem_detalhe_packball"
        )
        isolados.append(candidato)
    return isolados
