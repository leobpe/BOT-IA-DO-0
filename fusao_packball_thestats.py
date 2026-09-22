import re
from copy import deepcopy
from datetime import datetime


VERSAO_EXPERIMENTO_FUSAO = "fusao-packball-thestats-v1"
SLA_FUSAO_SEGUNDOS = 90.0


def _par(valor):
    numeros = re.findall(r"-?\d+(?:[.,]\d+)?", str(valor or ""))
    if len(numeros) < 2:
        return None
    return tuple(float(n.replace(",", ".")) for n in numeros[:2])


def _placar(valor):
    par = _par(valor)
    return tuple(int(x) for x in par) if par else None


def _minuto(status):
    numeros = re.findall(r"\d{1,3}", str(status or ""))
    return int(numeros[0]) if numeros else None


def _idade(iso, agora):
    try:
        instante = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        referencia = agora
        if instante.tzinfo is not None and referencia.tzinfo is None:
            referencia = referencia.astimezone()
        if instante.tzinfo is None and referencia.tzinfo is not None:
            instante = instante.replace(tzinfo=referencia.tzinfo)
        return max((referencia - instante).total_seconds(), 0.0)
    except (TypeError, ValueError):
        return None


def fundir_estatisticas_packball_thestats(
    jogo, estatisticas_packball, snapshot_thestats, agora=None
):
    """Completa apenas lacunas PB após validar o mesmo estado ao vivo."""
    agora = agora or datetime.now().astimezone()
    base = deepcopy(estatisticas_packball or {})
    diagnostico = {
        "versao": VERSAO_EXPERIMENTO_FUSAO,
        "valida": False,
        "complementou": [],
        "conflitos": [],
        "xg": None,
    }
    if not isinstance(snapshot_thestats, dict):
        diagnostico["motivo"] = "thestats_ausente"
        return base, diagnostico
    if snapshot_thestats.get("fonte") != "thestatsapi":
        diagnostico["motivo"] = "fonte_invalida"
        return base, diagnostico
    if snapshot_thestats.get("packball_url") != jogo.get("url"):
        diagnostico["motivo"] = "partida_divergente"
        return base, diagnostico
    idade = _idade(snapshot_thestats.get("coletado_em"), agora)
    diagnostico["idade_segundos"] = idade
    if idade is None or idade > SLA_FUSAO_SEGUNDOS:
        diagnostico["motivo"] = "thestats_desatualizado"
        return base, diagnostico
    placar_pb = _placar(jogo.get("placar"))
    placar_ts = snapshot_thestats.get("placar")
    if placar_pb is None or not isinstance(placar_ts, (list, tuple)):
        diagnostico["motivo"] = "placar_indeterminado"
        return base, diagnostico
    if tuple(placar_ts[:2]) != placar_pb:
        diagnostico["motivo"] = "placar_divergente"
        return base, diagnostico
    minuto_pb = _minuto(jogo.get("status"))
    minuto_ts = snapshot_thestats.get("minuto")
    if minuto_pb is None or minuto_ts is None or abs(minuto_pb - int(minuto_ts)) > 2:
        diagnostico["motivo"] = "minuto_divergente"
        return base, diagnostico

    campos = {
        "Chutes": ("chutes_mandante", "chutes_visitante", 2),
        "Chutes no gol": (
            "chutes_gol_mandante", "chutes_gol_visitante", 1
        ),
        "Escanteios": (
            "escanteios_mandante", "escanteios_visitante", 1
        ),
    }
    for campo, (casa, fora, tolerancia) in campos.items():
        valores_ts = (snapshot_thestats.get(casa), snapshot_thestats.get(fora))
        if None in valores_ts:
            continue
        valores_pb = _par(base.get(campo))
        if valores_pb is None:
            base[campo] = f"{valores_ts[0]} - {valores_ts[1]}"
            diagnostico["complementou"].append(campo)
        elif any(abs(a - b) > tolerancia for a, b in zip(valores_pb, valores_ts)):
            diagnostico["conflitos"].append(campo)

    xg = (snapshot_thestats.get("xg_mandante"), snapshot_thestats.get("xg_visitante"))
    if None not in xg:
        diagnostico["xg"] = list(xg)
    if diagnostico["conflitos"]:
        diagnostico["motivo"] = "metricas_divergentes"
        return estatisticas_packball or {}, diagnostico
    diagnostico["valida"] = bool(diagnostico["complementou"] or diagnostico["xg"])
    diagnostico["motivo"] = "complemento_confirmado" if diagnostico["valida"] else "sem_dado_novo"
    return base, diagnostico


def marcar_candidatos_dependentes_fusao(
    candidatos,
    candidatos_base,
    diagnostico,
    *,
    aplicacao_sinais=False,
):
    """Audita aprovações dependentes e só as isola quando não autorizadas."""
    if not diagnostico.get("valida"):
        return candidatos
    for candidato in candidatos or []:
        features = candidato.setdefault("features", {})
        features["fusao_fontes"] = deepcopy(diagnostico)
        features["xg_thestatsapi"] = diagnostico.get("xg")
    if not diagnostico.get("complementou"):
        return candidatos
    aprovados_base = {
        (c.get("mercado"), str(c.get("linha")), c.get("regra_versao"))
        for c in candidatos_base or [] if c.get("status") == "aprovado"
    }
    for candidato in candidatos or []:
        identidade = (
            candidato.get("mercado"), str(candidato.get("linha")),
            candidato.get("regra_versao"),
        )
        if candidato.get("status") != "aprovado" or identidade in aprovados_base:
            continue
        if aplicacao_sinais:
            features = candidato.setdefault("features", {})
            features["fusao_fontes"] = deepcopy(diagnostico)
            features["fusao_fontes"]["aplicacao_sinais"] = True
            features["fusao_fontes"]["modo"] = "oficial_fail_closed"
            features["xg_thestatsapi"] = diagnostico.get("xg")
            candidato.setdefault("motivos", []).append(
                "complemento_oficial_confirmado_packball_thestats"
            )
            continue
        candidato["status"] = "simulacao"
        features = candidato.setdefault("features", {})
        features["exploracao_sombra"] = {
            "versao": VERSAO_EXPERIMENTO_FUSAO,
            "aplicacao_automatica": False,
            "telegram_oficial": False,
        }
        features["fusao_fontes"] = deepcopy(diagnostico)
        features["xg_thestatsapi"] = diagnostico.get("xg")
        candidato.setdefault("motivos", []).append(
            "complemento_confirmado_packball_thestats"
        )
    return candidatos
