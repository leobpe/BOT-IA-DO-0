"""Mede, sem interferir nos sinais, o melhor preco do mesmo contrato.

A avaliacao e prospectiva e fail-closed: somente compara cotacoes recentes,
rastreaveis, da mesma linha/selecao e vindas de fonte e bookmaker distintos.
O resultado fica em ``features_json`` para formar uma coorte limpa antes de
qualquer mudanca operacional no seletor de odds.
"""

import math
import re
import unicodedata
from datetime import datetime, timezone

from validacao_resultado_valor_justo import (
    VERSAO_MEDIDOR,
    VERSAO_VALOR_JUSTO as VERSAO_VALOR_JUSTO_RESULTADO,
    politica_avaliacao_resultado,
)
from validacao_veto_preco_justo import avaliar_veto_preco_justo_sombra
from valor_mercado import VALOR_ESPERADO_MINIMO, avaliar_margem_bookmaker


VERSAO = VERSAO_MEDIDOR
VERSAO_VALOR_JUSTO = VERSAO_VALOR_JUSTO_RESULTADO
IDADE_MAXIMA_SEGUNDOS = 360.0
INTERVALO_FONTES_MAXIMO_SEGUNDOS = 60.0
TOLERANCIA_EQUIVALENCIA = 0.005

MERCADOS_SUPORTADOS = frozenset({
    "gol_ft",
    "gol_ht",
    "proximo_gol",
    "proximo_escanteio",
    "escanteios_ft_asiatico",
    "escanteios_1t",
    "escanteios_2t",
})


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _texto(valor):
    return str(valor or "").strip()


def _identidade_textual(valor):
    texto = unicodedata.normalize("NFKD", _texto(valor)).casefold()
    return "".join(
        caractere for caractere in texto
        if caractere.isalnum() and not unicodedata.combining(caractere)
    )


def _primeiro_definido(*valores):
    for valor in valores:
        if valor is not None:
            return valor
    return None


def _interpretar_instante(valor):
    if isinstance(valor, datetime):
        return valor
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip()
    if texto.endswith("Z"):
        texto = f"{texto[:-1]}+00:00"
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _utc_ingenuo(valor):
    if valor.tzinfo is None:
        valor = valor.astimezone()
    return valor.astimezone(timezone.utc).replace(tzinfo=None)


def _idade_efetiva(item, mercado, referencia):
    idade_bruta = _primeiro_definido(
        item.get("idade_segundos"), mercado.get("idade_segundos")
    )
    idade_declarada = _numero(idade_bruta)
    if idade_bruta is not None and (
        idade_declarada is None or idade_declarada < 0
    ):
        return None

    coletado_bruto = _primeiro_definido(
        item.get("coletado_em"), mercado.get("coletado_em")
    )
    coletado = _interpretar_instante(coletado_bruto)
    idades = []
    if idade_declarada is not None:
        idades.append(idade_declarada)
    if coletado is not None:
        idades.append(max(
            (_utc_ingenuo(referencia) - _utc_ingenuo(coletado))
            .total_seconds(),
            0.0,
        ))
    if not idades:
        return None
    return max(idades)


def _proveniencia(item, mercado, referencia, idade_maxima):
    fonte = _primeiro_definido(item.get("fonte"), mercado.get("fonte"))
    bookmaker = _primeiro_definido(
        item.get("bookmaker"), mercado.get("bookmaker")
    )
    cache = _primeiro_definido(item.get("cache"), mercado.get("cache"))
    coletado = _primeiro_definido(
        item.get("coletado_em"), mercado.get("coletado_em")
    )
    if (
        not fonte
        and _interpretar_instante(coletado) is not None
        and isinstance(cache, bool)
    ):
        fonte = "packball"
    idade = _idade_efetiva(item, mercado, referencia)
    if (
        not _identidade_textual(fonte)
        or not _identidade_textual(bookmaker)
        or not isinstance(cache, bool)
        or idade is None
        or idade < 0
        or idade > float(idade_maxima)
    ):
        return None
    return {
        "fonte": _texto(fonte),
        "bookmaker": _texto(bookmaker),
        "fonte_id": _identidade_textual(fonte),
        "bookmaker_id": _identidade_textual(bookmaker),
        "coletado_em": (
            coletado.isoformat()
            if isinstance(coletado, datetime)
            else _texto(coletado) or None
        ),
        "idade_segundos": round(float(idade), 3),
        "cache": cache,
    }


def _identidade_evento(item, mercado, proveniencia):
    identidade = _primeiro_definido(
        item.get("identidade_evento"), mercado.get("identidade_evento")
    )
    if not isinstance(identidade, dict):
        return None
    fonte = _identidade_textual(identidade.get("fonte"))
    mandante = _identidade_textual(identidade.get("mandante_normalizado"))
    visitante = _identidade_textual(identidade.get("visitante_normalizado"))
    placar = _texto(identidade.get("placar_normalizado")).replace(" ", "")
    if (
        identidade.get("schema") != "identidade-evento-odd-v1"
        or identidade.get("confirmada") is not True
        or not fonte
        or fonte != proveniencia["fonte_id"]
        or not mandante
        or not visitante
        or mandante == visitante
        or re.fullmatch(r"\d+-\d+", placar) is None
    ):
        return None
    return {
        "schema": "identidade-evento-odd-v1",
        "confirmada": True,
        "fonte": proveniencia["fonte"],
        "evento_externo_id": _texto(
            identidade.get("evento_externo_id")
        ) or None,
        "mandante_normalizado": mandante,
        "visitante_normalizado": visitante,
        "placar_normalizado": placar,
    }


def _sincronismo_estado(escolhida, referencia):
    if not isinstance(escolhida, dict) or not isinstance(referencia, dict):
        return None
    identidade_escolhida = escolhida.get("identidade_evento")
    identidade_referencia = referencia.get("identidade_evento")
    if not isinstance(identidade_escolhida, dict) or not isinstance(
        identidade_referencia, dict
    ):
        return None
    for campo in (
        "mandante_normalizado", "visitante_normalizado", "placar_normalizado"
    ):
        if identidade_escolhida.get(campo) != identidade_referencia.get(campo):
            return None
    instante_escolhida = _interpretar_instante(escolhida.get("coletado_em"))
    instante_referencia = _interpretar_instante(referencia.get("coletado_em"))
    if instante_escolhida is None or instante_referencia is None:
        return None
    intervalo = abs(
        (_utc_ingenuo(instante_escolhida) - _utc_ingenuo(instante_referencia))
        .total_seconds()
    )
    if intervalo > INTERVALO_FONTES_MAXIMO_SEGUNDOS:
        return None
    return {
        "comprovado": True,
        "intervalo_fontes_segundos": round(intervalo, 3),
        "intervalo_maximo_segundos": INTERVALO_FONTES_MAXIMO_SEGUNDOS,
        "mandante_normalizado": identidade_escolhida["mandante_normalizado"],
        "visitante_normalizado": identidade_escolhida["visitante_normalizado"],
        "placar_normalizado": identidade_escolhida["placar_normalizado"],
    }


def _linha_igual(primeira, segunda):
    primeira = _numero(primeira)
    segunda = _numero(segunda)
    return bool(
        primeira is not None
        and segunda is not None
        and math.isclose(primeira, segunda, rel_tol=0.0, abs_tol=0.000001)
    )


def _mercado_compativel(mercado_candidato, mercado):
    categoria = _texto(mercado.get("categoria")).casefold()
    escopo = _texto(mercado.get("escopo") or "total").casefold()
    tipo = _texto(mercado.get("tipo_mercado")).casefold()
    formato = _texto(
        mercado.get("formato") or "duas_opcoes"
    ).casefold()

    if mercado_candidato in {"gol_ft", "gol_ht"}:
        return categoria == "gols" and escopo == "total"
    if mercado_candidato == "proximo_gol":
        return categoria == "gols" and escopo == "proximo"
    if mercado_candidato == "proximo_escanteio":
        return bool(
            categoria == "escanteios"
            and escopo == "total"
            and tipo == "total"
            and formato == "duas_opcoes"
        )
    if mercado_candidato in {
        "escanteios_ft_asiatico", "escanteios_1t", "escanteios_2t"
    }:
        return bool(
            categoria == "escanteios"
            and escopo == "total"
            and tipo == "asiatico"
        )
    return False


def _probabilidade_sem_vig(tipo, odds, indice_selecao):
    margem = avaliar_margem_bookmaker(tipo, odds)
    if not margem.get("plausivel"):
        return None
    implicitas = [1.0 / float(odd) for odd in odds]
    total = sum(implicitas)
    if not math.isfinite(total) or total <= 0:
        return None
    return {
        "tipo_mercado_sem_vig": tipo,
        "probabilidade_selecao_sem_vig": round(
            implicitas[indice_selecao] / total, 8
        ),
        "margem_bookmaker": margem["margem_bookmaker"],
    }


def _itens_contrato(candidato, odds):
    mercado_candidato = _texto(candidato.get("mercado")).casefold()
    linha = candidato.get("linha")
    for mercado in (odds or {}).get("ao_vivo") or []:
        if not isinstance(mercado, dict):
            continue
        if not _mercado_compativel(mercado_candidato, mercado):
            continue

        if mercado_candidato == "proximo_gol":
            selecao = _texto(linha).casefold()
            selecoes = mercado.get("selecoes")
            if selecao not in {"casa", "visitante", "sem_gol"}:
                continue
            if not isinstance(selecoes, dict):
                continue
            odds_tres_vias = {
                chave: _numero(selecoes.get(chave))
                for chave in ("casa", "visitante", "sem_gol")
            }
            if any(
                valor is None or valor <= 1.0
                for valor in odds_tres_vias.values()
            ):
                continue
            chaves = ("casa", "visitante", "sem_gol")
            referencia_sem_vig = _probabilidade_sem_vig(
                "tres_vias",
                [odds_tres_vias[chave] for chave in chaves],
                chaves.index(selecao),
            )
            yield (
                mercado, mercado, odds_tres_vias[selecao],
                referencia_sem_vig,
            )
            continue

        if mercado_candidato == "gol_ht":
            ofertas = mercado.get("ofertas_ht") or []
        elif mercado_candidato in {"escanteios_1t", "escanteios_2t"}:
            periodo = "1T" if mercado_candidato.endswith("1t") else "2T"
            dados = (mercado.get("ofertas_periodos") or {}).get(periodo) or {}
            if _texto(dados.get("formato") or "duas_opcoes").casefold() != (
                "duas_opcoes"
            ):
                continue
            ofertas = dados.get("ofertas") or []
        else:
            if _texto(
                mercado.get("formato") or "duas_opcoes"
            ).casefold() != "duas_opcoes":
                continue
            ofertas = mercado.get("ofertas") or []

        for oferta in ofertas:
            if not isinstance(oferta, dict):
                continue
            if not _linha_igual(oferta.get("linha"), linha):
                continue
            over = _numero(oferta.get("over"))
            under = _numero(oferta.get("under"))
            if over is None or over <= 1.0 or under is None or under <= 1.0:
                continue
            yield (
                mercado, oferta, over,
                _probabilidade_sem_vig("binaria", [over, under], 0),
            )


def _base_valor_justo():
    return {
        "versao": VERSAO_VALOR_JUSTO,
        "estado": "sem_referencia_sem_vig_sincronizada",
        "motivo": "sem_referencia_sem_vig_sincronizada",
        "intervalo_fontes_maximo_segundos": (
            INTERVALO_FONTES_MAXIMO_SEGUNDOS
        ),
        "limiar_valor_esperado": float(VALOR_ESPERADO_MINIMO),
        "desajuste_favoravel": False,
        "avaliacao_resultado_sombra": politica_avaliacao_resultado(),
        "avaliacao_veto_preco_sombra": (
            avaliar_veto_preco_justo_sombra(None)
        ),
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _base(candidato, referencia, idade_maxima):
    return {
        "versao": VERSAO,
        "estado": "nao_avaliado",
        "motivo": "nao_avaliado",
        "mercado": candidato.get("mercado") if isinstance(candidato, dict) else None,
        "decisao_em": referencia.isoformat(),
        "idade_maxima_segundos": float(idade_maxima),
        "tolerancia_equivalencia": TOLERANCIA_EQUIVALENCIA,
        "ofertas_exatas_validas": 0,
        "ofertas_exatas_validas_operacionais": 0,
        "ofertas_exatas_validas_referencia_sombra": 0,
        "referencia_sombra_recebida": False,
        "referencia_sombra_consultada": False,
        "alternativas_independentes_validas": 0,
        "valor_justo_sombra": _base_valor_justo(),
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _cotacao_escolhida(candidato, referencia, idade_maxima):
    features = candidato.get("features")
    features = features if isinstance(features, dict) else {}
    cotacao = features.get("cotacao_entrada_clv")
    if not isinstance(cotacao, dict):
        return None, "cotacao_escolhida_nao_congelada"
    odd = _numero(cotacao.get("odd_selecionada"))
    fonte = cotacao.get("fonte")
    bookmaker = cotacao.get("bookmaker")
    cache = cotacao.get("cache")
    idade = _numero(cotacao.get("idade_segundos"))
    coletado = _interpretar_instante(cotacao.get("coletado_em"))
    if (
        odd is None or odd <= 1.0
        or not _identidade_textual(fonte)
        or not _identidade_textual(bookmaker)
        or not isinstance(cache, bool)
    ):
        return None, "proveniencia_escolhida_incompleta"
    idades = [idade] if idade is not None and idade >= 0 else []
    if coletado is not None:
        idades.append(max(
            (_utc_ingenuo(referencia) - _utc_ingenuo(coletado))
            .total_seconds(),
            0.0,
        ))
    if not idades or max(idades) > float(idade_maxima):
        return None, "cotacao_escolhida_sem_frescor"
    return {
        "fonte": _texto(fonte),
        "bookmaker": _texto(bookmaker),
        "fonte_id": _identidade_textual(fonte),
        "bookmaker_id": _identidade_textual(bookmaker),
        "odd": round(float(odd), 6),
        "coletado_em": cotacao.get("coletado_em"),
        "idade_segundos": round(float(max(idades)), 3),
        "cache": cache,
    }, None


def avaliar_melhor_preco_sombra(
    candidato,
    odds,
    instante=None,
    idade_maxima_segundos=IDADE_MAXIMA_SEGUNDOS,
    odds_referencia_sombra=None,
):
    """Retorna uma medicao isolada, sem alterar o candidato."""
    referencia = instante or datetime.now().astimezone()
    if referencia.tzinfo is None:
        referencia = referencia.astimezone()
    referencia = referencia.replace(microsecond=0)
    resultado = _base(candidato, referencia, idade_maxima_segundos)
    if not isinstance(candidato, dict):
        resultado.update(
            estado="entrada_invalida", motivo="candidato_invalido"
        )
        return resultado

    mercado_candidato = _texto(candidato.get("mercado")).casefold()
    referencia_separada = bool(
        isinstance(odds_referencia_sombra, dict)
        and odds_referencia_sombra is not odds
        and odds_referencia_sombra.get("ao_vivo")
    )
    resultado["referencia_sombra_recebida"] = referencia_separada
    if mercado_candidato not in MERCADOS_SUPORTADOS:
        resultado.update(
            estado="mercado_nao_suportado", motivo="mercado_nao_suportado"
        )
        return resultado

    escolhida, motivo = _cotacao_escolhida(
        candidato, referencia, idade_maxima_segundos
    )
    if escolhida is None:
        resultado.update(estado=motivo, motivo=motivo)
        return resultado

    resultado["cotacao_escolhida"] = {
        chave: valor for chave, valor in escolhida.items()
        if not chave.endswith("_id")
    }
    por_origem = {}
    estruturas = [("operacional", odds)]
    if isinstance(odds_referencia_sombra, dict) and (
        odds_referencia_sombra is not odds
    ):
        estruturas.append(("referencia_sombra", odds_referencia_sombra))
        resultado["referencia_sombra_consultada"] = referencia_separada
    for camada, estrutura in estruturas:
        for mercado, item, odd, referencia_sem_vig in _itens_contrato(
            candidato, estrutura
        ):
            proveniencia = _proveniencia(
                item, mercado, referencia, idade_maxima_segundos
            )
            if proveniencia is None:
                continue
            resultado["ofertas_exatas_validas"] += 1
            resultado[
                "ofertas_exatas_validas_referencia_sombra"
                if camada == "referencia_sombra"
                else "ofertas_exatas_validas_operacionais"
            ] += 1
            chave = (
                proveniencia["fonte_id"], proveniencia["bookmaker_id"]
            )
            observacao = {
                **proveniencia,
                "odd": round(float(odd), 6),
                "camada": camada,
            }
            identidade_evento = _identidade_evento(
                item, mercado, proveniencia
            )
            if identidade_evento is not None:
                observacao["identidade_evento"] = identidade_evento
            if referencia_sem_vig is not None:
                observacao.update(referencia_sem_vig)
            anterior = por_origem.get(chave)
            if anterior is None or (
                observacao["idade_segundos"], observacao["cache"],
                -observacao["odd"],
            ) < (
                anterior["idade_segundos"], anterior["cache"],
                -anterior["odd"],
            ):
                por_origem[chave] = observacao

    alternativas = [
        item for item in por_origem.values()
        if item["fonte_id"] != escolhida["fonte_id"]
        and item["bookmaker_id"] != escolhida["bookmaker_id"]
    ]
    resultado["alternativas_independentes_validas"] = len(alternativas)
    if not alternativas:
        resultado.update(
            estado="sem_referencia_independente_exata",
            motivo="sem_fonte_e_bookmaker_distintos_no_mesmo_contrato",
        )
        return resultado

    melhor = max(
        alternativas,
        key=lambda item: (
            item["odd"], -item["idade_segundos"], not item["cache"]
        ),
    )
    escolhida_observada = por_origem.get((
        escolhida["fonte_id"], escolhida["bookmaker_id"]
    ))
    if escolhida_observada is not None:
        instante_escolhida = _interpretar_instante(escolhida.get("coletado_em"))
        instante_observada = _interpretar_instante(
            escolhida_observada.get("coletado_em")
        )
        if (
            not math.isclose(
                escolhida_observada["odd"], escolhida["odd"],
                rel_tol=0.0, abs_tol=0.000001,
            )
            or instante_escolhida is None
            or instante_observada is None
            or abs(
                (_utc_ingenuo(instante_escolhida) - _utc_ingenuo(
                    instante_observada
                )).total_seconds()
            ) > 1.0
        ):
            escolhida_observada = None
    referencias_valor = []
    for item in alternativas:
        if (
            _numero(item.get("probabilidade_selecao_sem_vig")) is None
            or _numero(item.get("margem_bookmaker")) is None
        ):
            continue
        sincronismo = _sincronismo_estado(escolhida_observada, item)
        if sincronismo is None:
            continue
        referencias_valor.append((item, sincronismo))
    referencias_separadas = [
        item for item in referencias_valor
        if item[0].get("camada") == "referencia_sombra"
    ]
    if referencias_separadas:
        referencias_valor = referencias_separadas
    if referencias_valor:
        # A referência de preço justo é escolhida por frescor e identidade,
        # nunca pelo tamanho da odd. Isso evita selecionar retrospectivamente
        # a fonte que mais favorece a hipótese de edge.
        referencia_valor, sincronismo = min(
            referencias_valor,
            key=lambda par: (
                par[0]["idade_segundos"], par[0]["cache"],
                par[0]["fonte_id"], par[0]["bookmaker_id"],
            ),
        )
        probabilidade = float(
            referencia_valor["probabilidade_selecao_sem_vig"]
        )
        probabilidade_equilibrio = 1.0 / escolhida["odd"]
        valor_esperado = escolhida["odd"] * probabilidade - 1.0
        desajuste_favoravel = bool(
            valor_esperado + 1e-12 >= float(VALOR_ESPERADO_MINIMO)
        )
        resultado["valor_justo_sombra"].update({
            "estado": (
                "desajuste_favoravel_candidato"
                if desajuste_favoravel
                else "sem_desajuste_favoravel"
            ),
            "motivo": "referencia_independente_sem_vig_disponivel",
            "referencia": {
                chave: valor for chave, valor in referencia_valor.items()
                if not chave.endswith("_id")
            },
            "identidade_evento_escolhida": escolhida_observada[
                "identidade_evento"
            ],
            "sincronismo_estado": sincronismo,
            "odd_escolhida": escolhida["odd"],
            "probabilidade_equilibrio_odd_escolhida": round(
                probabilidade_equilibrio, 8
            ),
            "probabilidade_referencia_sem_vig": round(probabilidade, 8),
            "vantagem_probabilidade_pontos_percentuais": round(
                (probabilidade - probabilidade_equilibrio) * 100.0, 4
            ),
            "valor_esperado_referencia": round(valor_esperado, 8),
            "desajuste_favoravel": desajuste_favoravel,
            "avaliacao_veto_preco_sombra": (
                avaliar_veto_preco_justo_sombra(valor_esperado)
            ),
        })
    diferenca = round(melhor["odd"] - escolhida["odd"], 6)
    if diferenca > TOLERANCIA_EQUIVALENCIA:
        relacao = "alternativa_melhor"
    elif diferenca < -TOLERANCIA_EQUIVALENCIA:
        relacao = "escolhida_melhor"
    else:
        relacao = "equivalentes"
    resultado.update({
        "estado": "comparacao_independente_exata",
        "motivo": "comparacao_independente_exata_disponivel",
        "melhor_alternativa_independente": {
            chave: valor for chave, valor in melhor.items()
            if not chave.endswith("_id")
        },
        "diferenca_odd": diferenca,
        "relacao": relacao,
        "ganho_retorno_bruto_potencial_percentual": round(
            (melhor["odd"] / escolhida["odd"] - 1.0) * 100.0, 3
        ),
    })
    return resultado


def anexar_melhor_preco_sombra(
    candidatos,
    odds,
    instante=None,
    idade_maxima_segundos=IDADE_MAXIMA_SEGUNDOS,
    odds_referencia_sombra=None,
):
    """Anexa apenas evidencia; nunca muda odd, status ou bloqueios."""
    referencia = instante or datetime.now().astimezone()
    for candidato in candidatos or []:
        if not isinstance(candidato, dict):
            continue
        features = candidato.get("features")
        features = features if isinstance(features, dict) else {}
        candidato["features"] = {
            **features,
            "melhor_preco_sombra": avaliar_melhor_preco_sombra(
                candidato,
                odds,
                instante=referencia,
                idade_maxima_segundos=idade_maxima_segundos,
                odds_referencia_sombra=odds_referencia_sombra,
            ),
        }
    return candidatos
