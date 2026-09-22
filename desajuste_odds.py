"""Normalizacao estrita de comparacoes de odds entre fontes.

Esta camada produz somente evidencia temporal. Ela nao aprova candidatos,
nao altera regras e nao envia mensagens ao Telegram.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime


VERSAO = "comparacao-odds-multifonte-temporal-estado-minuto-v4"
FRESCOR_MAXIMO_SEGUNDOS = 180.0
INTERVALO_FONTES_MAXIMO_SEGUNDOS = 60.0
DIFERENCA_MINUTO_MAXIMA = 1.5
DELTA_ABSOLUTO_MINIMO = 0.05
DELTA_RELATIVO_MINIMO = 0.05
ODD_CANDIDATA_MINIMA = 1.20
ODD_CANDIDATA_MAXIMA = 10.0
CAMPOS_EVIDENCIA_COMPARACAO = (
    "snapshot_id", "partida_id", "observado_em", "placar", "status",
    "minuto", "categoria", "escopo", "periodo", "linha", "selecao",
    "fonte_a", "bookmaker_a", "odd_a", "coletado_em_a",
    "snapshot_fonte_a", "placar_fonte_a", "status_fonte_a",
    "minuto_fonte_a", "fonte_b", "bookmaker_b", "odd_b",
    "coletado_em_b", "snapshot_fonte_b", "placar_fonte_b",
    "status_fonte_b", "minuto_fonte_b", "fonte_melhor",
    "bookmaker_melhor", "odd_melhor", "fonte_controle",
    "bookmaker_controle", "odd_controle", "delta_absoluto",
    "delta_relativo", "intervalo_fontes_segundos",
    "frescor_maximo_segundos", "diferenca_minutos",
    "compatibilidade_bookmaker", "estado", "motivos_json", "versao",
)
MOTIVO_CORROBORACAO_ENTRADA_RAPIDA = (
    "corroboracao_odd_entrada_rapida"
)


def _numero(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _instante(valor):
    try:
        instante = datetime.fromisoformat(str(valor or ""))
    except (TypeError, ValueError):
        return None
    if instante.tzinfo is None:
        instante = instante.astimezone()
    return instante.timestamp()


def _periodo(valor):
    periodo = str(valor or "FT").strip().upper()
    return {
        "H1": "1T",
        "HT": "1T",
        "1H": "1T",
        "H2": "2T",
        "2H": "2T",
        "FULL": "FT",
        "TOTAL": "FT",
    }.get(periodo, periodo)


def _minuto(registro):
    for valor in (
        registro.get("minuto"),
        (registro.get("evolucao") or {}).get("minuto"),
        registro.get("status"),
    ):
        correspondencia = re.search(r"\d+(?:[.,]\d+)?", str(valor or ""))
        if correspondencia:
            return _numero(correspondencia.group(0).replace(",", "."))
    return None


def _placar_normalizado(valor):
    numeros = re.findall(r"\d+", str(valor or ""))
    if len(numeros) < 2:
        return None
    return f"{int(numeros[0])}-{int(numeros[1])}"


def _grupos_ofertas(mercado):
    yield "FT", mercado.get("ofertas") or []
    yield "1T", mercado.get("ofertas_ht") or []
    for periodo, dados in (mercado.get("ofertas_periodos") or {}).items():
        if isinstance(dados, dict):
            yield _periodo(periodo), dados.get("ofertas") or []


def _frescor(oferta, mercado, observado_em):
    coletado_em = oferta.get("coletado_em") or mercado.get("coletado_em")
    observado = _instante(observado_em)
    coletado = _instante(coletado_em)
    if observado is not None and coletado is not None:
        return abs(observado - coletado), coletado_em, coletado
    idade = _numero(
        oferta.get("idade_segundos", mercado.get("idade_segundos"))
    )
    return (
        abs(idade) if idade is not None else None,
        coletado_em,
        coletado,
    )


def _ofertas_normalizadas(
    odds, observado_em, placar_padrao=None, status_padrao=None,
):
    unicas = {}
    for mercado in (odds or {}).get("ao_vivo") or []:
        if not isinstance(mercado, dict):
            continue
        categoria = str(mercado.get("categoria") or "").strip().casefold()
        escopo = str(mercado.get("escopo") or "total").strip().casefold()
        if categoria not in {"gols", "escanteios"} or escopo != "total":
            continue
        for periodo, ofertas in _grupos_ofertas(mercado):
            for oferta in ofertas:
                if not isinstance(oferta, dict):
                    continue
                linha = _numero(oferta.get("linha"))
                if linha is None or linha < 0:
                    continue
                fonte = str(
                    oferta.get("fonte") or mercado.get("fonte") or ""
                ).strip().casefold()
                if not fonte:
                    continue
                bookmaker = str(
                    oferta.get("bookmaker")
                    or mercado.get("bookmaker")
                    or ""
                ).strip().casefold()
                frescor, coletado_em, instante = _frescor(
                    oferta, mercado, observado_em
                )
                status_origem = str(
                    oferta.get("_status_origem")
                    or mercado.get("_status_origem")
                    or status_padrao
                    or ""
                )
                minuto_origem = _numero(
                    oferta.get("_minuto_origem")
                    if oferta.get("_minuto_origem") is not None
                    else mercado.get("_minuto_origem")
                )
                if minuto_origem is None:
                    minuto_origem = _minuto({"status": status_origem})
                for selecao in ("over", "under"):
                    odd = _numero(oferta.get(selecao))
                    if odd is None or odd <= 1.0 or odd > 1000.0:
                        continue
                    item = {
                        "categoria": categoria,
                        "escopo": escopo,
                        "periodo": _periodo(periodo),
                        "linha": linha,
                        "selecao": selecao,
                        "fonte": fonte,
                        "bookmaker": bookmaker,
                        "odd": odd,
                        "coletado_em": coletado_em,
                        "instante": instante,
                        "frescor_segundos": frescor,
                        "snapshot_origem": (
                            oferta.get("_snapshot_origem")
                            or mercado.get("_snapshot_origem")
                        ),
                        "placar_origem": _placar_normalizado(
                            oferta.get("_placar_origem")
                            or mercado.get("_placar_origem")
                            or placar_padrao
                        ),
                        "status_origem": status_origem,
                        "minuto_origem": minuto_origem,
                    }
                    chave = (
                        categoria, escopo, item["periodo"], linha, selecao,
                        fonte, bookmaker,
                    )
                    anterior = unicas.get(chave)
                    frescor_anterior = (
                        anterior.get("frescor_segundos")
                        if anterior is not None else None
                    )
                    if anterior is None or (
                        frescor is not None
                        and (
                            frescor_anterior is None
                            or frescor < frescor_anterior
                        )
                    ):
                        unicas[chave] = item
    return list(unicas.values())


def normalizar_ofertas_temporais(
    odds, observado_em, placar_padrao=None, status_padrao=None,
):
    """Expõe a normalização temporal para avaliadores somente leitura."""
    return _ofertas_normalizadas(
        odds,
        observado_em,
        placar_padrao=placar_padrao,
        status_padrao=status_padrao,
    )


def _compatibilidade_bookmaker(a, b):
    bookmaker_a = a.get("bookmaker") or ""
    bookmaker_b = b.get("bookmaker") or ""
    if bookmaker_a and bookmaker_b:
        return (
            "mesma_bookmaker"
            if bookmaker_a == bookmaker_b
            else "bookmakers_distintas"
        )
    return "bookmaker_parcial"


def calcular_evidencia_comparacao(comparacao):
    """Reproduz o SHA-256 canônico persistido no SQLite."""
    documento = {
        campo: comparacao.get(campo)
        for campo in CAMPOS_EVIDENCIA_COMPARACAO
    }
    canonico = json.dumps(
        documento,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _igual_numero(observado, esperado, tolerancia=0.000001):
    observado = _numero(observado)
    esperado = _numero(esperado)
    if observado is None or esperado is None:
        return observado is None and esperado is None
    return math.isclose(
        observado, esperado, rel_tol=0.0, abs_tol=tolerancia
    )


def _classificar_comparacao_persistida(item):
    placar_a = item.get("placar_fonte_a")
    placar_b = item.get("placar_fonte_b")
    minuto_a = _numero(item.get("minuto_fonte_a"))
    minuto_b = _numero(item.get("minuto_fonte_b"))
    diferenca_minutos = (
        abs(minuto_a - minuto_b)
        if minuto_a is not None and minuto_b is not None else None
    )
    intervalo = item.get("intervalo_fontes_segundos")
    frescor = item.get("frescor_maximo_segundos")
    odd_a = _numero(item.get("odd_a"))
    odd_b = _numero(item.get("odd_b"))
    delta_abs = (
        abs(odd_a - odd_b)
        if odd_a is not None and odd_b is not None else None
    )
    delta_rel = (
        max(odd_a, odd_b) / min(odd_a, odd_b) - 1.0
        if (
            odd_a is not None and odd_b is not None
            and min(odd_a, odd_b) > 0
        )
        else None
    )
    odd_melhor = (
        max(odd_a, odd_b)
        if odd_a is not None and odd_b is not None else None
    )
    if placar_a is None or placar_b is None:
        return (
            "descartado_estado_jogo_desconhecido",
            "placar_da_oferta_incompleto",
            diferenca_minutos,
        )
    if placar_a != placar_b:
        return (
            "descartado_estado_jogo_divergente",
            "placar_mudou_entre_as_fontes",
            diferenca_minutos,
        )
    if diferenca_minutos is None:
        return (
            "descartado_minuto_desconhecido",
            "minuto_da_oferta_incompleto",
            diferenca_minutos,
        )
    if diferenca_minutos > DIFERENCA_MINUTO_MAXIMA:
        return (
            "descartado_minuto_divergente",
            "minuto_incompativel_entre_as_fontes",
            diferenca_minutos,
        )
    if _numero(frescor) is None or _numero(intervalo) is None:
        return (
            "descartado_tempo_desconhecido",
            "tempo_da_oferta_incompleto",
            diferenca_minutos,
        )
    if float(frescor) > FRESCOR_MAXIMO_SEGUNDOS:
        return (
            "descartado_cotacao_antiga",
            "frescor_acima_do_limite",
            diferenca_minutos,
        )
    if float(intervalo) > INTERVALO_FONTES_MAXIMO_SEGUNDOS:
        return (
            "descartado_intervalo_temporal",
            "fontes_observadas_em_instantes_distantes",
            diferenca_minutos,
        )
    if (
        delta_abs is not None
        and delta_rel is not None
        and odd_melhor is not None
        and delta_abs >= DELTA_ABSOLUTO_MINIMO
        and delta_rel >= DELTA_RELATIVO_MINIMO
        and ODD_CANDIDATA_MINIMA <= odd_melhor <= ODD_CANDIDATA_MAXIMA
    ):
        return (
            "desajuste_candidato",
            "diferenca_de_preco_relevante",
            diferenca_minutos,
        )
    return (
        "comparavel_sem_desajuste",
        "diferenca_abaixo_do_corte",
        diferenca_minutos,
    )


def validar_comparacao_persistida(comparacao):
    """Recalcula custódia, matemática e classificação de uma comparação."""
    item = dict(comparacao or {})
    problemas = []
    evidencia = str(item.get("evidencia_sha256") or "").strip().casefold()
    recalculada = calcular_evidencia_comparacao(item)
    if not re.fullmatch(r"[0-9a-f]{64}", evidencia):
        problemas.append("evidencia_sha256_invalida")
    elif evidencia != recalculada:
        problemas.append("evidencia_sha256_divergente")
    if item.get("versao") != VERSAO:
        problemas.append("versao_comparacao_invalida")
    for campo in ("snapshot_id", "partida_id"):
        try:
            if int(item.get(campo)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            problemas.append(f"{campo}_invalido")
    if (
        item.get("categoria") not in {"gols", "escanteios"}
        or item.get("escopo") != "total"
        or item.get("periodo") not in {"FT", "1T", "2T"}
        or item.get("selecao") not in {"over", "under"}
    ):
        problemas.append("chave_mercado_invalida")
    linha = _numero(item.get("linha"))
    odd_a = _numero(item.get("odd_a"))
    odd_b = _numero(item.get("odd_b"))
    if linha is None or linha < 0:
        problemas.append("linha_invalida")
    if (
        odd_a is None or odd_b is None
        or not 1.0 < odd_a <= 1000.0
        or not 1.0 < odd_b <= 1000.0
    ):
        problemas.append("odds_fontes_invalidas")
    fonte_a = str(item.get("fonte_a") or "").strip().casefold()
    fonte_b = str(item.get("fonte_b") or "").strip().casefold()
    if not fonte_a or not fonte_b or fonte_a == fonte_b:
        problemas.append("fontes_nao_independentes")
    if odd_a is not None and odd_b is not None:
        melhor_a = odd_a >= odd_b
        melhor = {
            "fonte": fonte_a if melhor_a else fonte_b,
            "bookmaker": (
                str(item.get("bookmaker_a") or "")
                if melhor_a else str(item.get("bookmaker_b") or "")
            ),
            "odd": max(odd_a, odd_b),
        }
        controle = {
            "fonte": fonte_b if melhor_a else fonte_a,
            "bookmaker": (
                str(item.get("bookmaker_b") or "")
                if melhor_a else str(item.get("bookmaker_a") or "")
            ),
            "odd": min(odd_a, odd_b),
        }
        if (
            str(item.get("fonte_melhor") or "").strip().casefold()
            != melhor["fonte"]
            or str(item.get("bookmaker_melhor") or "")
            != melhor["bookmaker"]
            or not _igual_numero(item.get("odd_melhor"), melhor["odd"])
            or str(item.get("fonte_controle") or "").strip().casefold()
            != controle["fonte"]
            or str(item.get("bookmaker_controle") or "")
            != controle["bookmaker"]
            or not _igual_numero(
                item.get("odd_controle"), controle["odd"]
            )
        ):
            problemas.append("melhor_preco_ou_fonte_divergente")
        delta_abs = abs(odd_a - odd_b)
        delta_rel = max(odd_a, odd_b) / min(odd_a, odd_b) - 1.0
        if (
            not _igual_numero(
                item.get("delta_absoluto"), round(delta_abs, 6)
            )
            or not _igual_numero(
                item.get("delta_relativo"), round(delta_rel, 6)
            )
        ):
            problemas.append("delta_preco_divergente")
    compatibilidade = _compatibilidade_bookmaker(
        {"bookmaker": str(item.get("bookmaker_a") or "")},
        {"bookmaker": str(item.get("bookmaker_b") or "")},
    )
    if item.get("compatibilidade_bookmaker") != compatibilidade:
        problemas.append("compatibilidade_bookmaker_divergente")
    instante_a = _instante(item.get("coletado_em_a"))
    instante_b = _instante(item.get("coletado_em_b"))
    intervalo_esperado = (
        abs(instante_a - instante_b)
        if instante_a is not None and instante_b is not None else None
    )
    if not _igual_numero(
        item.get("intervalo_fontes_segundos"),
        (
            round(intervalo_esperado, 3)
            if intervalo_esperado is not None else None
        ),
        tolerancia=0.001,
    ):
        problemas.append("intervalo_fontes_divergente")
    estado, motivo_estado, diferenca_minutos = (
        _classificar_comparacao_persistida(item)
    )
    if not _igual_numero(
        item.get("diferenca_minutos"),
        (
            round(diferenca_minutos, 3)
            if diferenca_minutos is not None else None
        ),
        tolerancia=0.001,
    ):
        problemas.append("diferenca_minutos_divergente")
    if item.get("estado") != estado:
        problemas.append("estado_comparacao_divergente")
    try:
        motivos = json.loads(str(item.get("motivos_json") or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        motivos = None
    snapshots = [
        item.get("snapshot_fonte_a"),
        item.get("snapshot_fonte_b"),
    ]
    conhecidos = {valor for valor in snapshots if valor is not None}
    motivo_snapshot = (
        "fontes_em_snapshots_temporais_distintos"
        if len(conhecidos) > 1
        else "snapshot_de_uma_fonte_indisponivel"
        if any(valor is None for valor in snapshots)
        else "fontes_no_mesmo_snapshot"
    )
    motivos_esperados = ["mesma_linha_periodo_escopo_selecao"]
    if (
        isinstance(motivos, list)
        and MOTIVO_CORROBORACAO_ENTRADA_RAPIDA in motivos
    ):
        motivos_esperados.append(MOTIVO_CORROBORACAO_ENTRADA_RAPIDA)
    motivos_esperados.extend((motivo_snapshot, motivo_estado))
    if motivos != motivos_esperados:
        problemas.append("motivos_comparacao_divergentes")
    return {
        "valida": not problemas,
        "problemas": sorted(set(problemas)),
        "evidencia_recalculada": recalculada,
        "estado_recalculado": estado,
        "motivos_recalculados": motivos_esperados,
    }


def construir_comparacoes_multifonte(registro, partida_id, snapshot_id):
    """Compara ofertas idênticas observadas na mesma janela temporal."""
    observado_em = str(
        registro.get("coletado_em")
        or datetime.now().replace(microsecond=0).isoformat()
    )
    agrupadas = defaultdict(list)
    for oferta in _ofertas_normalizadas(
        registro.get("odds") or {}, observado_em,
        placar_padrao=registro.get("placar"),
        status_padrao=registro.get("status"),
    ):
        chave = tuple(oferta[campo] for campo in (
            "categoria", "escopo", "periodo", "linha", "selecao"
        ))
        agrupadas[chave].append(oferta)

    comparacoes = []
    for chave, ofertas in agrupadas.items():
        ofertas.sort(key=lambda item: (
            item["fonte"], item.get("bookmaker") or "", item["odd"]
        ))
        for indice, fonte_a in enumerate(ofertas):
            for fonte_b in ofertas[indice + 1:]:
                if fonte_a["fonte"] == fonte_b["fonte"]:
                    continue
                delta_abs = abs(fonte_a["odd"] - fonte_b["odd"])
                odd_controle = min(fonte_a["odd"], fonte_b["odd"])
                odd_melhor = max(fonte_a["odd"], fonte_b["odd"])
                delta_relativo = odd_melhor / odd_controle - 1.0
                instantes = [
                    item.get("instante") for item in (fonte_a, fonte_b)
                ]
                intervalo = (
                    abs(instantes[0] - instantes[1])
                    if all(item is not None for item in instantes)
                    else None
                )
                frescores = [
                    item.get("frescor_segundos")
                    for item in (fonte_a, fonte_b)
                ]
                frescor_maximo = (
                    max(frescores)
                    if all(item is not None for item in frescores)
                    else None
                )
                motivos = ["mesma_linha_periodo_escopo_selecao"]
                motivo_contexto = str(
                    registro.get("_motivo_comparacao") or ""
                ).strip()
                if motivo_contexto:
                    motivos.append(motivo_contexto)
                snapshots_lista = [
                    fonte_a.get("snapshot_origem"),
                    fonte_b.get("snapshot_origem"),
                ]
                snapshots_origem = {
                    item for item in snapshots_lista if item is not None
                }
                if len(snapshots_origem) > 1:
                    motivos.append("fontes_em_snapshots_temporais_distintos")
                elif any(item is None for item in snapshots_lista):
                    motivos.append("snapshot_de_uma_fonte_indisponivel")
                else:
                    motivos.append("fontes_no_mesmo_snapshot")
                placar_a = fonte_a.get("placar_origem")
                placar_b = fonte_b.get("placar_origem")
                minuto_a = fonte_a.get("minuto_origem")
                minuto_b = fonte_b.get("minuto_origem")
                diferenca_minutos = (
                    abs(minuto_a - minuto_b)
                    if minuto_a is not None and minuto_b is not None
                    else None
                )
                if placar_a is None or placar_b is None:
                    estado = "descartado_estado_jogo_desconhecido"
                    motivos.append("placar_da_oferta_incompleto")
                elif placar_a != placar_b:
                    estado = "descartado_estado_jogo_divergente"
                    motivos.append("placar_mudou_entre_as_fontes")
                elif diferenca_minutos is None:
                    estado = "descartado_minuto_desconhecido"
                    motivos.append("minuto_da_oferta_incompleto")
                elif diferenca_minutos > DIFERENCA_MINUTO_MAXIMA:
                    estado = "descartado_minuto_divergente"
                    motivos.append("minuto_incompativel_entre_as_fontes")
                elif frescor_maximo is None or intervalo is None:
                    estado = "descartado_tempo_desconhecido"
                    motivos.append("tempo_da_oferta_incompleto")
                elif frescor_maximo > FRESCOR_MAXIMO_SEGUNDOS:
                    estado = "descartado_cotacao_antiga"
                    motivos.append("frescor_acima_do_limite")
                elif intervalo > INTERVALO_FONTES_MAXIMO_SEGUNDOS:
                    estado = "descartado_intervalo_temporal"
                    motivos.append("fontes_observadas_em_instantes_distantes")
                elif (
                    delta_abs >= DELTA_ABSOLUTO_MINIMO
                    and delta_relativo >= DELTA_RELATIVO_MINIMO
                    and ODD_CANDIDATA_MINIMA <= odd_melhor
                    <= ODD_CANDIDATA_MAXIMA
                ):
                    estado = "desajuste_candidato"
                    motivos.append("diferenca_de_preco_relevante")
                else:
                    estado = "comparavel_sem_desajuste"
                    motivos.append("diferenca_abaixo_do_corte")

                melhor = (
                    fonte_a if fonte_a["odd"] >= fonte_b["odd"] else fonte_b
                )
                controle = fonte_b if melhor is fonte_a else fonte_a
                item = {
                    "snapshot_id": int(snapshot_id),
                    "partida_id": int(partida_id),
                    "observado_em": observado_em,
                    "placar": registro.get("placar"),
                    "status": registro.get("status"),
                    "minuto": _minuto(registro),
                    "categoria": chave[0],
                    "escopo": chave[1],
                    "periodo": chave[2],
                    "linha": chave[3],
                    "selecao": chave[4],
                    "fonte_a": fonte_a["fonte"],
                    "bookmaker_a": fonte_a.get("bookmaker") or "",
                    "odd_a": round(fonte_a["odd"], 6),
                    "coletado_em_a": fonte_a.get("coletado_em"),
                    "snapshot_fonte_a": fonte_a.get("snapshot_origem"),
                    "placar_fonte_a": fonte_a.get("placar_origem"),
                    "status_fonte_a": fonte_a.get("status_origem"),
                    "minuto_fonte_a": minuto_a,
                    "fonte_b": fonte_b["fonte"],
                    "bookmaker_b": fonte_b.get("bookmaker") or "",
                    "odd_b": round(fonte_b["odd"], 6),
                    "coletado_em_b": fonte_b.get("coletado_em"),
                    "snapshot_fonte_b": fonte_b.get("snapshot_origem"),
                    "placar_fonte_b": fonte_b.get("placar_origem"),
                    "status_fonte_b": fonte_b.get("status_origem"),
                    "minuto_fonte_b": minuto_b,
                    "fonte_melhor": melhor["fonte"],
                    "bookmaker_melhor": melhor.get("bookmaker") or "",
                    "odd_melhor": round(odd_melhor, 6),
                    "fonte_controle": controle["fonte"],
                    "bookmaker_controle": controle.get("bookmaker") or "",
                    "odd_controle": round(odd_controle, 6),
                    "delta_absoluto": round(delta_abs, 6),
                    "delta_relativo": round(delta_relativo, 6),
                    "intervalo_fontes_segundos": (
                        round(intervalo, 3) if intervalo is not None else None
                    ),
                    "frescor_maximo_segundos": (
                        round(frescor_maximo, 3)
                        if frescor_maximo is not None else None
                    ),
                    "diferenca_minutos": (
                        round(diferenca_minutos, 3)
                        if diferenca_minutos is not None else None
                    ),
                    "compatibilidade_bookmaker": (
                        _compatibilidade_bookmaker(fonte_a, fonte_b)
                    ),
                    "estado": estado,
                    "motivos_json": json.dumps(
                        motivos, ensure_ascii=False, separators=(",", ":")
                    ),
                    "versao": VERSAO,
                }
                item["evidencia_sha256"] = (
                    calcular_evidencia_comparacao(item)
                )
                comparacoes.append(item)
    return comparacoes
