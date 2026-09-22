"""Validação matemática da curva de preços de totais binários."""

from __future__ import annotations

import math

from origem_mercado import (
    assinatura_grupo_mercado,
    assinatura_origem_mercado,
    normalizar_origem_mercado,
)


VERSAO = "coerencia-curva-odds-v1"
VERSAO_EVIDENCIA_ANOMALIA = "anomalia-curva-odd-v1"
TOLERANCIA_NUMERICA = 0.000001
MOTIVOS_ANOMALIA_CURVA = frozenset({
    "curva_linhas_odd_duplicada_divergente",
    "curva_linhas_odd_incoerente",
})


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _linha_binaria(linha):
    return bool(
        linha is not None
        and math.isclose(linha % 1.0, 0.5, abs_tol=TOLERANCIA_NUMERICA)
    )


def validar_coerencia_curva_odds(ofertas, origem_selecionada=None):
    """Rejeita preços dominados entre linhas .5 do mesmo grupo comprovado.

    Over de uma linha menor representa um evento mais abrangente e não pode
    pagar mais que Over de uma linha maior. Under segue a ordem inversa. A
    validação só compara ofertas com a mesma identidade de grupo; sem essa
    prova, permanece inconclusiva em vez de presumir que as linhas são irmãs.
    """
    grupo_selecionado = assinatura_grupo_mercado(origem_selecionada)
    if origem_selecionada is not None and grupo_selecionado is None:
        return {
            "valida": False,
            "motivo": "origem_curva_odd_invalida",
            "versao": VERSAO,
            "linhas_comparadas": 0,
            "pares_comparados": 0,
        }

    por_grupo = {}
    ofertas_validas = 0
    for oferta in ofertas or []:
        if not isinstance(oferta, dict):
            continue
        linha = _numero(oferta.get("linha"))
        over = _numero(oferta.get("over"))
        under = _numero(oferta.get("under"))
        grupo = assinatura_grupo_mercado(oferta.get("origem_mercado"))
        if (
            not _linha_binaria(linha)
            or over is None or over <= 1.0
            or under is None or under <= 1.0
            or grupo is None
            or (grupo_selecionado is not None and grupo != grupo_selecionado)
        ):
            continue
        ofertas_validas += 1
        linhas = por_grupo.setdefault(grupo, {})
        anterior = linhas.get(linha)
        atual = (over, under)
        if anterior is not None and anterior != atual:
            return {
                "valida": False,
                "motivo": "curva_linhas_odd_duplicada_divergente",
                "versao": VERSAO,
                "linha": linha,
                "linhas_comparadas": len(linhas),
                "pares_comparados": 0,
            }
        linhas[linha] = atual

    pares = 0
    for grupo, linhas in por_grupo.items():
        ordenadas = sorted(linhas.items())
        for (linha_baixa, preco_baixo), (linha_alta, preco_alto) in zip(
            ordenadas, ordenadas[1:]
        ):
            pares += 1
            over_baixo, under_baixo = preco_baixo
            over_alto, under_alto = preco_alto
            over_dominado = over_baixo > over_alto + TOLERANCIA_NUMERICA
            under_dominado = under_baixo + TOLERANCIA_NUMERICA < under_alto
            if over_dominado or under_dominado:
                return {
                    "valida": False,
                    "motivo": "curva_linhas_odd_incoerente",
                    "versao": VERSAO,
                    "grupo": grupo[2],
                    "linha_baixa": linha_baixa,
                    "linha_alta": linha_alta,
                    "over_linha_baixa": over_baixo,
                    "over_linha_alta": over_alto,
                    "under_linha_baixa": under_baixo,
                    "under_linha_alta": under_alto,
                    "lado_incoerente": (
                        "ambos" if over_dominado and under_dominado
                        else "over" if over_dominado else "under"
                    ),
                    "linhas_comparadas": len(linhas),
                    "pares_comparados": pares,
                }

    return {
        "valida": True,
        "motivo": (
            "curva_linhas_odd_confirmada"
            if pares else "curva_linhas_odd_sem_par_comparavel"
        ),
        "versao": VERSAO,
        "ofertas_validas": ofertas_validas,
        "linhas_comparadas": sum(len(linhas) for linhas in por_grupo.values()),
        "pares_comparados": pares,
    }


def _ofertas_do_mercado(estrutura, mercado):
    """Devolve apenas a curva economicamente equivalente ao candidato."""
    if not isinstance(estrutura, dict):
        return []
    categoria = estrutura.get("categoria")
    escopo = estrutura.get("escopo") or "total"
    tipo = estrutura.get("tipo_mercado")
    formato = estrutura.get("formato") or "duas_opcoes"
    if formato != "duas_opcoes":
        return []
    if mercado == "gol_ft":
        return (
            estrutura.get("ofertas") or []
            if categoria == "gols" and escopo == "total" else []
        )
    if mercado == "gol_ht":
        return (
            estrutura.get("ofertas_ht") or []
            if categoria == "gols" and escopo == "total" else []
        )
    if mercado == "escanteios_ft_asiatico":
        return (
            estrutura.get("ofertas") or []
            if categoria == "escanteios"
            and escopo == "total" and tipo == "asiatico" else []
        )
    if mercado in {"escanteios_1t", "escanteios_2t"}:
        if categoria != "escanteios" or tipo != "asiatico":
            return []
        periodo = "1T" if mercado.endswith("1t") else "2T"
        return (
            ((estrutura.get("ofertas_periodos") or {}).get(periodo) or {})
            .get("ofertas") or []
        )
    return []


def _oferta_canonica(oferta):
    if not isinstance(oferta, dict):
        return None
    linha = _numero(oferta.get("linha"))
    over = _numero(oferta.get("over"))
    under = _numero(oferta.get("under"))
    origem = normalizar_origem_mercado(oferta.get("origem_mercado"))
    if (
        linha is None or over is None or under is None or origem is None
        or not math.isclose(
            float(origem["linha"]), linha, abs_tol=TOLERANCIA_NUMERICA
        )
    ):
        return None
    return {
        "linha": linha,
        "over": over,
        "under": under,
        "origem_mercado": origem,
    }


def validar_coerencia_curva_candidato(
    odds, mercado, linha, origem_selecionada, *,
    odd_selecionada=None, odd_oposta_selecionada=None,
):
    """Reconstitui e valida a curva exata que contém a oferta escolhida.

    O diagnóstico carrega as linhas canônicas usadas no cálculo. Isso permite
    persistir e reexecutar a prova posteriormente, sem depender do payload
    transitório devolvido pela API.
    """
    if mercado == "proximo_gol":
        return {
            "valida": True,
            "motivo": "curva_linhas_odd_nao_aplicavel",
            "versao": VERSAO,
            "mercado": mercado,
            "linhas_comparadas": 0,
            "pares_comparados": 0,
        }
    linha_selecionada = _numero(linha)
    over_selecionado = _numero(odd_selecionada)
    under_selecionado = _numero(odd_oposta_selecionada)
    origem_normalizada = normalizar_origem_mercado(origem_selecionada)
    assinatura_selecionada = assinatura_origem_mercado(origem_normalizada)
    grupo_selecionado = assinatura_grupo_mercado(origem_normalizada)
    if (
        linha_selecionada is None
        or origem_normalizada is None
        or assinatura_selecionada is None
        or grupo_selecionado is None
    ):
        return {
            "valida": False,
            "motivo": "origem_curva_odd_invalida",
            "versao": VERSAO,
            "mercado": mercado,
            "linhas_comparadas": 0,
            "pares_comparados": 0,
        }

    ofertas_curva = []
    selecionada_localizada = False
    for estrutura in (odds or {}).get("ao_vivo") or []:
        for oferta in _ofertas_do_mercado(estrutura, mercado):
            canonica = _oferta_canonica(oferta)
            if canonica is None:
                continue
            if assinatura_grupo_mercado(
                canonica["origem_mercado"]
            ) != grupo_selecionado:
                continue
            ofertas_curva.append(canonica)
            if (
                assinatura_origem_mercado(canonica["origem_mercado"])
                == assinatura_selecionada
                and math.isclose(
                    canonica["linha"], linha_selecionada,
                    abs_tol=TOLERANCIA_NUMERICA,
                )
                and (
                    over_selecionado is None
                    or math.isclose(
                        canonica["over"], over_selecionado,
                        abs_tol=TOLERANCIA_NUMERICA,
                    )
                )
                and (
                    under_selecionado is None
                    or math.isclose(
                        canonica["under"], under_selecionado,
                        abs_tol=TOLERANCIA_NUMERICA,
                    )
                )
            ):
                selecionada_localizada = True

    ofertas_curva.sort(key=lambda item: (
        item["linha"], item["over"], item["under"],
        item["origem_mercado"]["identificador"],
    ))
    if not selecionada_localizada:
        return {
            "valida": False,
            "motivo": "oferta_curva_odd_nao_localizada",
            "versao": VERSAO,
            "mercado": mercado,
            "linha_selecionada": linha_selecionada,
            "origem_selecionada": origem_normalizada,
            "ofertas_curva": ofertas_curva,
            "linhas_comparadas": len(ofertas_curva),
            "pares_comparados": 0,
        }

    resultado = validar_coerencia_curva_odds(
        ofertas_curva, origem_normalizada
    )
    return {
        **resultado,
        "mercado": mercado,
        "linha_selecionada": linha_selecionada,
        "origem_selecionada": origem_normalizada,
        "ofertas_curva": ofertas_curva,
    }


def validar_evidencia_anomalia_curva(
    evidencia, *, mercado=None, linha=None, origem_selecionada=None,
    odd_selecionada=None, odd_oposta_selecionada=None,
):
    """Recalcula uma prova persistida e recusa diagnóstico adulterado."""
    if (
        not isinstance(evidencia, dict)
        or evidencia.get("versao") != VERSAO
        or evidencia.get("valida") is not False
        or evidencia.get("motivo") not in MOTIVOS_ANOMALIA_CURVA
        or not isinstance(evidencia.get("ofertas_curva"), list)
    ):
        return {"valida": False, "motivo": "evidencia_curva_formato_invalido"}
    if mercado is not None and evidencia.get("mercado") != mercado:
        return {"valida": False, "motivo": "evidencia_curva_mercado_divergente"}
    if linha is not None and not math.isclose(
        _numero(evidencia.get("linha_selecionada")) or float("nan"),
        _numero(linha) or float("nan"),
        abs_tol=TOLERANCIA_NUMERICA,
    ):
        return {"valida": False, "motivo": "evidencia_curva_linha_divergente"}

    origem = normalizar_origem_mercado(
        origem_selecionada or evidencia.get("origem_selecionada")
    )
    if origem is None or assinatura_origem_mercado(origem) != (
        assinatura_origem_mercado(evidencia.get("origem_selecionada"))
    ):
        return {"valida": False, "motivo": "evidencia_curva_origem_divergente"}
    linha_alvo = _numero(evidencia.get("linha_selecionada"))
    if linha_alvo is None:
        return {"valida": False, "motivo": "evidencia_curva_linha_invalida"}
    over_alvo = _numero(odd_selecionada)
    under_alvo = _numero(odd_oposta_selecionada)
    assinatura_alvo = assinatura_origem_mercado(origem)
    selecionada_presente = any(
        canonica is not None
        and assinatura_origem_mercado(canonica["origem_mercado"])
        == assinatura_alvo
        and math.isclose(
            canonica["linha"], linha_alvo, abs_tol=TOLERANCIA_NUMERICA
        )
        and (
            over_alvo is None
            or math.isclose(
                canonica["over"], over_alvo, abs_tol=TOLERANCIA_NUMERICA
            )
        )
        and (
            under_alvo is None
            or math.isclose(
                canonica["under"], under_alvo, abs_tol=TOLERANCIA_NUMERICA
            )
        )
        for canonica in (
            _oferta_canonica(oferta)
            for oferta in evidencia["ofertas_curva"]
        )
    )
    if not selecionada_presente:
        return {"valida": False, "motivo": "evidencia_curva_oferta_ausente"}
    recalculada = validar_coerencia_curva_odds(
        evidencia["ofertas_curva"], origem
    )
    if (
        recalculada.get("valida") is not False
        or recalculada.get("motivo") != evidencia.get("motivo")
    ):
        return {"valida": False, "motivo": "evidencia_curva_calculo_divergente"}
    for chave, valor in recalculada.items():
        if evidencia.get(chave) != valor:
            return {
                "valida": False,
                "motivo": "evidencia_curva_diagnostico_divergente",
                "campo": chave,
            }
    return {"valida": True, "motivo": "evidencia_curva_confirmada"}
