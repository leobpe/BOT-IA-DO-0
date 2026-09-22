"""Roteamento estrito das odds da TheStatsAPI.

O modulo valida identidade e estado da partida e converte somente mercados
Bet365 explicitamente suportados. O contrato nasce sem autoridade; o servico
so o promove depois do gate operacional e da configuracao oficial. PackBall
permanece principal e TheStats cobre mercado ou linha ausente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import math
import os
import re
import unicodedata


FONTE = "thestatsapi"
BOOKMAKER = "Bet365"
FRESCOR_MAXIMO_SEGUNDOS = 30.0
DELTA_MINUTO_MAXIMO = 2
SIMILARIDADE_MINIMA = 0.90
MARGEM_MINIMA_MULTIPLOS = 0.05
VAR_RECONCILIAR_STATUS_LIVE_GENERICO = (
    "THESTATSAPI_RECONCILIAR_STATUS_LIVE_GENERICO_ATIVA"
)

_ID_PARTIDA_RE = re.compile(r"^mt_[A-Za-z0-9_-]+$")

_COORTES = {
    ("gols", "total", "FT"): "thestatsapi-bet365-gols-total-ft-v1",
    ("gols", "total", "1T"): "thestatsapi-bet365-gols-total-1t-v1",
    ("gols", "total", "2T"): "thestatsapi-bet365-gols-total-2t-v1",
    (
        "escanteios", "total", "FT",
    ): "thestatsapi-bet365-escanteios-total-ft-v1",
    (
        "escanteios", "total", "1T",
    ): "thestatsapi-bet365-escanteios-total-1t-v1",
    (
        "escanteios", "total", "2T",
    ): "thestatsapi-bet365-escanteios-total-2t-v1",
    (
        "escanteios", "asiatico", "FT",
    ): "thestatsapi-bet365-escanteios-asiaticos-ft-v1",
    (
        "escanteios", "asiatico", "1T",
    ): "thestatsapi-bet365-escanteios-asiaticos-1t-v1",
    (
        "escanteios", "asiatico", "2T",
    ): "thestatsapi-bet365-escanteios-asiaticos-2t-v1",
}

# A lista e deliberadamente fechada. Mercados novos permanecem observaveis
# nos diagnosticos, mas nunca herdam semantica por conter "goal" ou "corner".
_MERCADOS_PERMITIDOS = {
    "total_goals": ("gols", "FT", False),
    "match_goals": ("gols", "FT", False),
    "goals_over_under": ("gols", "FT", False),
    "total_match_goals": ("gols", "FT", False),
    "first_half_total_goals": ("gols", "1T", False),
    "1st_half_total_goals": ("gols", "1T", False),
    "first_half_goals": ("gols", "1T", False),
    "total_goals_first_half": ("gols", "1T", False),
    "second_half_total_goals": ("gols", "2T", False),
    "2nd_half_total_goals": ("gols", "2T", False),
    "second_half_goals": ("gols", "2T", False),
    "total_goals_second_half": ("gols", "2T", False),
    "match_corners": ("escanteios", "FT", False),
    "total_corners": ("escanteios", "FT", False),
    "corners_over_under": ("escanteios", "FT", False),
    "total_match_corners": ("escanteios", "FT", False),
    "first_half_corners": ("escanteios", "1T", False),
    "first_half_total_corners": ("escanteios", "1T", False),
    "1st_half_corners": ("escanteios", "1T", False),
    "total_corners_first_half": ("escanteios", "1T", False),
    "second_half_corners": ("escanteios", "2T", False),
    "second_half_total_corners": ("escanteios", "2T", False),
    "2nd_half_corners": ("escanteios", "2T", False),
    "total_corners_second_half": ("escanteios", "2T", False),
    "asian_corners": ("escanteios", "FT", True),
    "asian_total_corners": ("escanteios", "FT", True),
    "match_asian_corners": ("escanteios", "FT", True),
    "asian_corners_total": ("escanteios", "FT", True),
    "first_half_asian_corners": ("escanteios", "1T", True),
    "first_half_asian_total_corners": ("escanteios", "1T", True),
    "1st_half_asian_corners": ("escanteios", "1T", True),
    "asian_corners_first_half": ("escanteios", "1T", True),
    "asian_corners_1st_half": ("escanteios", "1T", True),
    "asian_total_corners_1st_half": ("escanteios", "1T", True),
    "second_half_asian_corners": ("escanteios", "2T", True),
    "second_half_asian_total_corners": ("escanteios", "2T", True),
    "2nd_half_asian_corners": ("escanteios", "2T", True),
    "asian_corners_second_half": ("escanteios", "2T", True),
    "asian_corners_2nd_half": ("escanteios", "2T", True),
    "asian_total_corners_2nd_half": ("escanteios", "2T", True),
}

_TERMOS_PROIBIDOS = frozenset({
    "next", "team", "home", "away", "handicap", "exact", "exactly",
    "race", "most", "first_to", "last", "winning_margin",
})


def _sem_acentos(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )


def _chave_mercado(valor):
    return re.sub(
        r"_+", "_", re.sub(
            r"[^a-z0-9]+", "_", _sem_acentos(valor).casefold()
        )
    ).strip("_")


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(str(valor).strip().replace("%", "").replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _inteiro(valor):
    numero = _numero(valor)
    return int(numero) if numero is not None and numero.is_integer() else None


def _instante_utc(valor):
    if isinstance(valor, datetime):
        instante = valor
    elif isinstance(valor, str) and valor.strip():
        texto = valor.strip()
        if texto.endswith("Z"):
            texto = f"{texto[:-1]}+00:00"
        try:
            instante = datetime.fromisoformat(texto)
        except ValueError:
            return None
    else:
        return None
    if instante.tzinfo is None:
        return instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone.utc)


def _agora_utc(agora=None):
    instante = _instante_utc(agora)
    return instante or datetime.now(timezone.utc)


def _desembrulhar(resposta):
    if not isinstance(resposta, dict) or resposta.get("ok") is False:
        return None
    if "dados" in resposta:
        return resposta.get("dados")
    if "data" in resposta:
        return resposta.get("data")
    return resposta


def _timestamps_fonte(resposta):
    dados = _desembrulhar(resposta)
    candidatos = []
    for recipiente in (
        resposta if isinstance(resposta, dict) else None,
        dados if isinstance(dados, dict) else None,
        (dados or {}).get("meta") if isinstance(dados, dict) else None,
    ):
        if not isinstance(recipiente, dict):
            continue
        candidatos.extend(
            recipiente.get(chave)
            for chave in ("updated_at", "generated_at", "coletado_em")
        )
    instantes = []
    for candidato in candidatos:
        instante = _instante_utc(candidato)
        if instante is not None:
            instantes.append(instante)
    return instantes


def _timestamp_fonte(resposta):
    instantes = _timestamps_fonte(resposta)
    # O instante mais antigo e conservador quando envelope, payload e meta
    # informam relogios diferentes para o mesmo snapshot.
    return min(instantes) if instantes else None


def idade_efetiva_resposta(resposta, agora=None):
    """Usa a maior idade comprovavel entre cache e timestamp do provedor."""
    if not isinstance(resposta, dict) or resposta.get("ok") is False:
        return None
    referencia = _agora_utc(agora)
    idades = []
    idade_envelope = _numero(resposta.get("idade_segundos"))
    if idade_envelope is not None:
        if idade_envelope < 0:
            return None
        idades.append(idade_envelope)
    for instante in _timestamps_fonte(resposta):
        idade_fonte = (referencia - instante).total_seconds()
        if idade_fonte < -2.0:
            return None
        idades.append(max(idade_fonte, 0.0))
    # Respostas do cliente oficial sempre trazem idade. Para entradas cruas,
    # o instante do provedor ainda e uma prova suficiente de frescor.
    return max(idades) if idades else None


def _placar_packball(valor):
    if isinstance(valor, (list, tuple)) and len(valor) >= 2:
        placar = [_inteiro(valor[0]), _inteiro(valor[1])]
    else:
        numeros = re.findall(r"\d+", str(valor or ""))
        placar = (
            [int(numeros[0]), int(numeros[1])]
            if len(numeros) >= 2 else None
        )
    return placar if placar and None not in placar else None


def _periodo_packball(status):
    texto = _sem_acentos(status).casefold().strip()
    if not texto:
        return None
    if texto == "ht" or "intervalo" in texto or "half time" in texto:
        return "HT"
    if any(item in texto for item in ("1h", "1t", "primeiro tempo")):
        return "1T"
    if any(item in texto for item in ("2h", "2t", "segundo tempo")):
        return "2T"
    minuto = _minuto_packball(status)
    if minuto is None:
        return None
    return "1T" if minuto <= 45 else "2T"


def _minuto_packball(status):
    texto = _sem_acentos(status).casefold().strip()
    if texto == "ht" or "intervalo" in texto or "half time" in texto:
        return 45
    numeros = re.findall(r"\d{1,3}", texto)
    return int(numeros[0]) if numeros else None


def _periodo_api(valor, minuto=None):
    if isinstance(valor, dict):
        valor = (
            valor.get("match_status") or valor.get("period")
            or valor.get("short") or valor.get("name") or valor.get("long")
        )
    chave = _chave_mercado(valor)
    if chave in {"ht", "half_time", "halftime", "interval", "intervalo"}:
        return "HT"
    if chave in {"1h", "1t", "first", "first_half", "1st_half"}:
        return "1T"
    if chave in {"2h", "2t", "second", "second_half", "2nd_half"}:
        return "2T"
    if minuto is not None:
        return "1T" if minuto <= 45 else "2T"
    return None


def _status_live_generico(valor):
    """Reconhece somente o estado genérico que a lista live realmente envia."""
    if isinstance(valor, dict):
        valores = (
            valor.get("match_status"),
            valor.get("period"),
            valor.get("short"),
            valor.get("name"),
            valor.get("long"),
        )
    else:
        valores = (valor,)
    chaves = {_chave_mercado(item) for item in valores if item is not None}
    return bool(chaves & {"live", "ao_vivo", "in_play", "inplay"})


def _reconciliacao_status_live_generico_ativa():
    valor = str(
        os.getenv(VAR_RECONCILIAR_STATUS_LIVE_GENERICO, "1")
    ).strip().casefold()
    return valor not in {"0", "false", "nao", "não", "off"}


def _estado_live_stats(resposta, orientacao):
    dados = _desembrulhar(resposta)
    if not isinstance(dados, dict):
        return None
    meta = dados.get("meta") or {}
    if not isinstance(meta, dict):
        return None
    match_id = str(dados.get("match_id") or "").strip()
    placar = [
        _inteiro(meta.get("home_goals")),
        _inteiro(meta.get("away_goals")),
    ]
    minuto = _inteiro(
        meta.get("elapsed_minutes")
        if meta.get("elapsed_minutes") is not None else meta.get("minute")
    )
    periodo = _periodo_api(
        meta.get("match_status") or meta.get("period"), minuto
    )
    if periodo == "HT" and minuto is None:
        minuto = 45
    if orientacao == "invertida":
        placar.reverse()
    return {
        "match_id": match_id,
        "placar": placar if None not in placar else None,
        "minuto": minuto,
        "periodo": periodo,
    }


def _estado_associacao(associacao):
    status = associacao.get("status") or {}
    minuto = _inteiro(
        status.get("elapsed") if isinstance(status, dict) else None
    )
    periodo = _periodo_api(status, minuto)
    if periodo == "HT" and minuto is None:
        minuto = 45
    return {
        "placar": _placar_packball(associacao.get("placar")),
        "periodo": periodo,
        "minuto": minuto,
        "status_live_generico": _status_live_generico(status),
    }


def _resultado_gate(motivo, **dados):
    apto = motivo == "apto_sombra"
    return {
        "apto_sombra": apto,
        "motivo": motivo,
        "fonte": FONTE,
        "bookmaker_exigida": BOOKMAKER,
        "aplicacao_sinais": False,
        "autoriza_sinal": False,
        "calibracao": False,
        "telegram": False,
        "substitui_packball": False,
        **dados,
    }


def _bookmaker_exato(valor):
    return " ".join(str(valor or "").split()).casefold() == "bet365"


def _tem_bet365_exata(dados_odds):
    if not isinstance(dados_odds, dict):
        return False
    bookmakers = dados_odds.get("bookmakers") or []
    if isinstance(bookmakers, dict):
        bookmakers = [bookmakers]
    return any(
        isinstance(item, dict)
        and _bookmaker_exato(item.get("bookmaker") or item.get("name"))
        for item in bookmakers
    )


def validar_gate_operacional_thestatsapi(
    jogo_packball,
    diagnostico_associacao,
    resposta_live_stats,
    resposta_odds,
    *,
    agora=None,
    frescor_maximo_segundos=FRESCOR_MAXIMO_SEGUNDOS,
):
    """Valida uma evidencia candidata; nunca concede autoridade de sinal."""
    try:
        frescor_maximo = min(float(frescor_maximo_segundos), 30.0)
    except (TypeError, ValueError):
        return _resultado_gate("frescor_configuracao_invalida")
    if not math.isfinite(frescor_maximo) or frescor_maximo <= 0:
        return _resultado_gate("frescor_configuracao_invalida")
    diagnostico = dict(diagnostico_associacao or {})
    associacao = diagnostico.get("associacao")
    if diagnostico.get("fonte") != FONTE or not isinstance(associacao, dict):
        return _resultado_gate("associacao_ausente_ou_fonte_invalida")
    if diagnostico.get("motivo") != "associado":
        return _resultado_gate("associacao_nao_confirmada")
    similaridade = _numero(associacao.get("similaridade"))
    if similaridade is None or similaridade < SIMILARIDADE_MINIMA:
        return _resultado_gate("similaridade_insuficiente")
    candidatos = _inteiro(
        associacao.get("candidatos_compativeis")
        if associacao.get("candidatos_compativeis") is not None
        else diagnostico.get("candidatos_compativeis")
    )
    margem = _numero(
        associacao.get("margem_associacao")
        if associacao.get("margem_associacao") is not None
        else diagnostico.get("margem_associacao")
    )
    if candidatos is None or candidatos < 1:
        return _resultado_gate("quantidade_candidatos_invalida")
    if candidatos is not None and candidatos > 1 and (
        margem is None or margem < MARGEM_MINIMA_MULTIPLOS
    ):
        return _resultado_gate("margem_associacao_insuficiente")
    orientacao = associacao.get("orientacao")
    if orientacao not in {"direta", "invertida"}:
        return _resultado_gate("orientacao_invalida")

    match_id_associacao = str(associacao.get("match_id") or "").strip()
    fixture_id_associacao = str(
        associacao.get("fixture_id") or ""
    ).strip()
    if (
        match_id_associacao
        and fixture_id_associacao
        and match_id_associacao != fixture_id_associacao
    ):
        return _resultado_gate("ids_associacao_incompativeis")
    match_id = match_id_associacao or fixture_id_associacao
    if not _ID_PARTIDA_RE.fullmatch(match_id):
        return _resultado_gate("match_id_invalido")
    estado_stats = _estado_live_stats(resposta_live_stats, orientacao)
    dados_odds = _desembrulhar(resposta_odds)
    match_id_odds = str(
        (dados_odds or {}).get("match_id") if isinstance(dados_odds, dict) else ""
    ).strip()
    if estado_stats is None or estado_stats.get("match_id") != match_id:
        return _resultado_gate("match_id_live_stats_incompativel")
    if match_id_odds != match_id:
        return _resultado_gate("match_id_odds_incompativel")
    if not _tem_bet365_exata(dados_odds):
        return _resultado_gate("bookmaker_bet365_exata_ausente")

    idade_stats = idade_efetiva_resposta(resposta_live_stats, agora)
    idade_odds = idade_efetiva_resposta(resposta_odds, agora)
    if idade_stats is None or idade_stats > frescor_maximo:
        return _resultado_gate(
            "live_stats_sem_frescor", idade_live_stats_segundos=idade_stats
        )
    if idade_odds is None or idade_odds > frescor_maximo:
        return _resultado_gate(
            "odds_sem_frescor", idade_odds_segundos=idade_odds
        )

    placar_packball = _placar_packball(
        (jogo_packball or {}).get("placar")
    )
    estado_associado = _estado_associacao(associacao)
    if placar_packball is None:
        return _resultado_gate("placar_packball_indisponivel")
    if estado_associado["placar"] != placar_packball:
        return _resultado_gate("placar_lista_incompativel")
    if estado_stats["placar"] != placar_packball:
        return _resultado_gate("placar_live_stats_incompativel")

    periodo_packball = _periodo_packball(
        (jogo_packball or {}).get("status")
    )
    minuto_packball = _minuto_packball(
        (jogo_packball or {}).get("status")
    )
    if periodo_packball is None or minuto_packball is None:
        return _resultado_gate("estado_packball_indisponivel")
    if estado_stats["periodo"] != periodo_packball:
        return _resultado_gate("periodo_live_stats_incompativel")
    minuto_stats = estado_stats["minuto"]
    if minuto_stats is None:
        return _resultado_gate("minuto_live_stats_indisponivel")
    if abs(minuto_packball - minuto_stats) > DELTA_MINUTO_MAXIMO:
        return _resultado_gate(
            "minuto_live_stats_incompativel",
            delta_minuto=abs(minuto_packball - minuto_stats),
        )

    periodo_lista_reconciliado = False
    if estado_associado["periodo"] != periodo_packball:
        pode_reconciliar = (
            estado_associado["periodo"] is None
            and estado_associado["minuto"] is None
            and estado_associado["status_live_generico"]
            and _reconciliacao_status_live_generico_ativa()
        )
        if not pode_reconciliar:
            return _resultado_gate("periodo_lista_incompativel")
        # A lista /matches informa somente ``live``. Nesse caso ela continua
        # validando identidade e placar; período e minuto são reconciliados
        # pelo /live-stats fresco, que já foi confrontado com o PackBall.
        periodo_lista_reconciliado = True
    else:
        minuto_lista = estado_associado["minuto"]
        if minuto_lista is None:
            return _resultado_gate("minuto_lista_indisponivel")
        if abs(minuto_packball - minuto_lista) > DELTA_MINUTO_MAXIMO:
            return _resultado_gate(
                "minuto_lista_incompativel",
                delta_minuto=abs(minuto_packball - minuto_lista),
            )

    return _resultado_gate(
        "apto_sombra",
        match_id=match_id,
        orientacao=orientacao,
        similaridade=round(similaridade, 4),
        margem_associacao=(round(margem, 4) if margem is not None else None),
        placar_validado=list(placar_packball),
        periodo_validado=periodo_packball,
        minuto_packball=minuto_packball,
        minuto_thestatsapi=estado_stats["minuto"],
        delta_minuto=abs(minuto_packball - estado_stats["minuto"]),
        periodo_lista_reconciliado=periodo_lista_reconciliado,
        avisos=(
            ["status_lista_live_generico_reconciliado_por_live_stats"]
            if periodo_lista_reconciliado else []
        ),
        rollback=(
            f"{VAR_RECONCILIAR_STATUS_LIVE_GENERICO}=0"
            if periodo_lista_reconciliado else None
        ),
        idade_live_stats_segundos=round(idade_stats, 3),
        idade_odds_segundos=round(idade_odds, 3),
        frescor_maximo_segundos=frescor_maximo,
    )


def _iterar_mercados(bruto):
    if isinstance(bruto, dict):
        yield from bruto.items()
    elif isinstance(bruto, list):
        for item in bruto:
            if not isinstance(item, dict):
                continue
            nome = item.get("market") or item.get("name") or item.get("key")
            linhas = item.get("lines") or item.get("odds") or item.get("values")
            if nome is not None:
                yield nome, linhas


def _linha_decimal(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        linha = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return linha if linha.is_finite() and linha >= 0 else None


def _odd_live(valor):
    if isinstance(valor, dict):
        valor = valor.get("live")
    odd = _numero(valor)
    return round(odd, 4) if odd is not None and odd > 1 else None


def _tipo_cantos(linha, mercado_asiatico_explicito):
    if mercado_asiatico_explicito:
        return "asiatico"
    fracao = linha % 1
    if fracao == Decimal("0.5"):
        return "total"
    if fracao in {Decimal("0"), Decimal("0.25"), Decimal("0.75")}:
        return "asiatico"
    return None


def coorte_sombra_thestatsapi(categoria, tipo_mercado, periodo):
    return _COORTES.get((categoria, tipo_mercado, str(periodo).upper()))


def converter_odds_bet365_contrato_interno(resposta, *, agora=None):
    """Converte somente totais Bet365, preservando taxonomia e linhagem."""
    referencia = _agora_utc(agora)
    dados = _desembrulhar(resposta)
    idade = idade_efetiva_resposta(resposta, referencia)
    base = {
        "pre_jogo": [],
        "ao_vivo": [],
        "movimentacao": [],
        "_metadados": {
            "fonte": FONTE,
            "bookmaker": BOOKMAKER,
            "cache": bool((resposta or {}).get("cache", False))
            if isinstance(resposta, dict) else False,
            "idade_segundos": round(idade, 3) if idade is not None else None,
            "recebido_em": referencia.isoformat(),
            "aplicacao_sinais": False,
            "autoriza_sinal": False,
            "calibracao": False,
            "telegram": False,
            "substitui_packball": False,
            "mercados_ignorados": [],
            "bookmakers_ignorados": [],
            "coortes_sombra": {},
        },
    }
    if not isinstance(dados, dict):
        base["_metadados"]["estado"] = "resposta_invalida"
        return base
    match_id = str(dados.get("match_id") or "").strip()
    base["_metadados"]["match_id"] = match_id or None
    instante_fonte = _timestamp_fonte(resposta)
    if instante_fonte is None and idade is not None:
        instante_fonte = referencia - timedelta(seconds=idade)
    coletado_em = instante_fonte.isoformat() if instante_fonte else None
    grupos = {}
    bookmakers = dados.get("bookmakers") or []
    if isinstance(bookmakers, dict):
        bookmakers = [bookmakers]
    for bloco in bookmakers:
        if not isinstance(bloco, dict):
            continue
        nome_bookmaker = bloco.get("bookmaker") or bloco.get("name")
        if not _bookmaker_exato(nome_bookmaker):
            if nome_bookmaker:
                base["_metadados"]["bookmakers_ignorados"].append(
                    str(nome_bookmaker)
                )
            continue
        for mercado_original, linhas in _iterar_mercados(
            bloco.get("markets") or {}
        ):
            chave = _chave_mercado(mercado_original)
            proibido = any(
                termo == chave or f"_{termo}_" in f"_{chave}_"
                for termo in _TERMOS_PROIBIDOS
            )
            classificacao = None if proibido else _MERCADOS_PERMITIDOS.get(chave)
            if classificacao is None:
                base["_metadados"]["mercados_ignorados"].append(
                    str(mercado_original)
                )
                continue
            categoria, periodo, asiatico_explicito = classificacao
            if not isinstance(linhas, dict):
                base["_metadados"]["mercados_ignorados"].append(
                    str(mercado_original)
                )
                continue
            for linha_original, selecoes in linhas.items():
                linha = _linha_decimal(linha_original)
                if linha is None or not isinstance(selecoes, dict):
                    continue
                if categoria == "escanteios":
                    tipo = _tipo_cantos(linha, asiatico_explicito)
                else:
                    tipo = "total"
                coorte = coorte_sombra_thestatsapi(categoria, tipo, periodo)
                if tipo is None or coorte is None:
                    continue
                over = _odd_live(selecoes.get("over"))
                under = _odd_live(selecoes.get("under"))
                # Uma oferta incompleta nao prova o mercado over/under exato.
                if over is None or under is None:
                    continue
                oferta = {
                    "linha": float(linha),
                    "over": over,
                    "under": under,
                    "fonte": FONTE,
                    "bookmaker": BOOKMAKER,
                    "match_id": match_id or None,
                    "mercado_original": str(mercado_original),
                    "linha_original": str(linha_original),
                    "periodo": periodo,
                    "tipo_mercado": tipo,
                    "coorte_sombra": coorte,
                    "coletado_em": coletado_em,
                    "recebido_em": referencia.isoformat(),
                    "idade_segundos": (
                        round(idade, 3) if idade is not None else None
                    ),
                    "cache": bool((resposta or {}).get("cache", False))
                    if isinstance(resposta, dict) else False,
                    "aplicacao_sinais": False,
                    "autoriza_sinal": False,
                    "calibracao": False,
                }
                grupos.setdefault((categoria, tipo), {}).setdefault(
                    periodo, []
                ).append(oferta)
                coortes = base["_metadados"]["coortes_sombra"]
                coortes[coorte] = int(coortes.get(coorte, 0)) + 1

    for (categoria, tipo), por_periodo in sorted(grupos.items()):
        for ofertas in por_periodo.values():
            ofertas.sort(key=lambda item: item["linha"])
        mercado = {
            "mercado": (
                f"TheStatsAPI Bet365 {categoria} "
                f"{'asiaticos' if tipo == 'asiatico' else 'totais'}"
            ),
            "dados": "",
            "categoria": categoria,
            "escopo": "total",
            "tipo_mercado": tipo,
            "formato": "duas_opcoes",
            "ofertas": list(por_periodo.get("FT") or []),
            "ofertas_exatamente": [],
            "ofertas_periodos": {
                periodo: {
                    "formato": "duas_opcoes",
                    "ofertas": list(por_periodo.get(periodo) or []),
                }
                for periodo in ("1T", "2T")
                if por_periodo.get(periodo)
            },
            "ofertas_ht": (
                list(por_periodo.get("1T") or [])
                if categoria == "gols" else []
            ),
            "selecoes": {},
            "fonte": FONTE,
            "bookmaker": BOOKMAKER,
            "match_id": match_id or None,
            "coletado_em": coletado_em,
            "recebido_em": referencia.isoformat(),
            "idade_segundos": round(idade, 3) if idade is not None else None,
            "cache": bool((resposta or {}).get("cache", False))
            if isinstance(resposta, dict) else False,
            "aplicacao_sinais": False,
            "autoriza_sinal": False,
            "calibracao": False,
        }
        base["ao_vivo"].append(mercado)
    metadados = base["_metadados"]
    metadados["mercados_ignorados"] = sorted(set(
        metadados["mercados_ignorados"]
    ))
    metadados["bookmakers_ignorados"] = sorted(set(
        metadados["bookmakers_ignorados"]
    ))
    metadados["total_mercados"] = len(base["ao_vivo"])
    metadados["total_ofertas"] = sum(
        len(mercado.get("ofertas") or [])
        + sum(
            len((periodo or {}).get("ofertas") or [])
            for periodo in (mercado.get("ofertas_periodos") or {}).values()
        )
        for mercado in base["ao_vivo"]
    )
    metadados["estado"] = (
        "convertido_sombra" if metadados["total_ofertas"]
        else "sem_ofertas_bet365_suportadas"
    )
    return base


def rotear_odds_thestatsapi_sombra(
    jogo_packball,
    diagnostico_associacao,
    resposta_live_stats,
    resposta_odds,
    *,
    agora=None,
    ativa=True,
):
    """Avalia a rota auxiliar, mantendo PackBall como decisao operacional."""
    base = {
        "rota": "packball",
        "fallback": "packball",
        "rota_sombra": None,
        "pode_omitir_packball": False,
        "substitui_packball": False,
        "aplicacao_sinais": False,
        "autoriza_sinal": False,
        "calibracao": False,
        "telegram": False,
        "odds_sombra": None,
    }
    if not ativa:
        return {**base, "estado": "desativada_rollback", "motivo": "desativada"}
    gate = validar_gate_operacional_thestatsapi(
        jogo_packball,
        diagnostico_associacao,
        resposta_live_stats,
        resposta_odds,
        agora=agora,
    )
    if not gate["apto_sombra"]:
        return {
            **base,
            "estado": "fallback_packball",
            "motivo": gate["motivo"],
            "gate": gate,
        }
    odds = converter_odds_bet365_contrato_interno(
        resposta_odds, agora=agora
    )
    if not ((odds.get("_metadados") or {}).get("total_ofertas")):
        return {
            **base,
            "estado": "fallback_packball",
            "motivo": "sem_ofertas_bet365_suportadas",
            "gate": gate,
            "odds_sombra": odds,
        }
    return {
        **base,
        "estado": "elegivel_somente_sombra",
        "motivo": "aguardando_validacao_prospectiva",
        "rota_sombra": "thestatsapi_bet365",
        "gate": gate,
        "odds_sombra": odds,
        "coortes_sombra": dict(
            (odds.get("_metadados") or {}).get("coortes_sombra") or {}
        ),
    }


def taxonomia_coortes_thestatsapi():
    """Exposicao imutavel da taxonomia sem conceder uso operacional."""
    return [
        {
            "categoria": categoria,
            "tipo_mercado": tipo,
            "periodo": periodo,
            "coorte_sombra": coorte,
            "aplicacao_sinais": False,
            "ativacao_automatica": False,
        }
        for (categoria, tipo, periodo), coorte in sorted(_COORTES.items())
    ]
