"""Proveniência e frescor da oferta de odd efetivamente escolhida.

Este módulo é deliberadamente independente do normalizador e do motor de
sinais. Ele pode ser aplicado logo depois de ``gerar_candidatos`` sem alterar
o contrato público dos seletores nem a linhagem já congelada das regras.
"""

import json
import math
from collections import Counter
from datetime import datetime, timezone

from coerencia_curva_odds import validar_coerencia_curva_odds
from origem_mercado import (
    assinatura_origem_mercado,
    normalizar_origem_mercado,
)


IDADE_ODD_MAXIMA_SEGUNDOS = 360.0
LIMIAR_APROVACAO_PADRAO = 70.0
VERSAO_COTACAO_ENTRADA_CLV_V1 = "cotacao-entrada-clv-v1"
VERSAO_COTACAO_ENTRADA_CLV = "cotacao-entrada-clv-v2"
VERSAO_CUSTODIA_COTACAO_OFICIAL = (
    "custodia-cotacao-executavel-oficial-v1"
)
CHAVE_ESTADO_COTACAO_ENTRADA = "cotacao_entrada_clv_estado"
ESTADO_COTACAO_CONGELADA = "congelada_v1"
FONTE_COTACAO_EXECUTAVEL_OFICIAL = "betsapi"
BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL = "bet365"

BLOQUEIOS_PROVENIENCIA = frozenset({
    "cache_odds_indeterminado",
    "coletado_em_odds_invalido",
    "curva_linhas_odd_duplicada_divergente",
    "curva_linhas_odd_incoerente",
    "fonte_odds_desconhecida",
    "frescor_odds_indeterminado",
    "idade_odds_invalida",
    "odds_desatualizadas",
    "oferta_odds_nao_rastreavel",
    "origem_mercado_entrada_divergente",
    "origem_mercado_entrada_invalida",
    "origem_curva_odd_invalida",
})


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _numeros_iguais(primeiro, segundo):
    primeiro = _numero(primeiro)
    segundo = _numero(segundo)
    return bool(
        primeiro is not None
        and segundo is not None
        and math.isclose(
            primeiro,
            segundo,
            rel_tol=0.0,
            abs_tol=0.000001,
        )
    )


def _mercados_ao_vivo(odds):
    return [
        item
        for item in (odds or {}).get("ao_vivo") or []
        if isinstance(item, dict)
    ]


def _oferta_exata(ofertas, linha, odd):
    for oferta in ofertas or []:
        if not isinstance(oferta, dict):
            continue
        if (
            _numeros_iguais(oferta.get("linha"), linha)
            and _numeros_iguais(oferta.get("over"), odd)
        ):
            return oferta
    return None


def _origem_esperada(candidato):
    features = candidato.get("features")
    features = features if isinstance(features, dict) else {}
    acompanhamento = features.get("acompanhamento_odd_rapido")
    acompanhamento = acompanhamento if isinstance(acompanhamento, dict) else {}
    return _primeiro_definido(
        candidato.get("origem_mercado"),
        features.get("origem_mercado_odd"),
        acompanhamento.get("origem_mercado_odd"),
    )


def _origem_oferta(mercado, oferta):
    return _primeiro_definido(
        oferta.get("origem_mercado"), mercado.get("origem_mercado")
    )


def _ofertas_curva(candidato, mercado):
    mercado_candidato = candidato.get("mercado")
    if mercado_candidato == "gol_ht":
        return mercado.get("ofertas_ht") or []
    if mercado_candidato in {"escanteios_1t", "escanteios_2t"}:
        periodo = "1T" if mercado_candidato.endswith("1t") else "2T"
        return (
            ((mercado.get("ofertas_periodos") or {}).get(periodo) or {})
            .get("ofertas") or []
        )
    if mercado_candidato == "proximo_gol":
        return []
    return mercado.get("ofertas") or []


def _localizar_oferta(candidato, odds):
    """Reproduz a semântica dos seletores e retorna mercado + oferta."""
    mercado_candidato = candidato.get("mercado")
    linha = candidato.get("linha")
    odd = candidato.get("odd")
    candidatas = []
    houve_correspondencia_economica = False
    origem_esperada = _origem_esperada(candidato)
    assinatura_esperada = assinatura_origem_mercado(origem_esperada)
    if origem_esperada is not None and assinatura_esperada is None:
        return None, None, False, "origem_mercado_entrada_invalida"

    for mercado in _mercados_ao_vivo(odds):
        categoria = mercado.get("categoria")
        escopo = mercado.get("escopo") or "total"
        tipo = mercado.get("tipo_mercado")
        formato = mercado.get("formato") or "duas_opcoes"

        if mercado_candidato == "proximo_gol":
            if categoria != "gols" or escopo != "proximo":
                continue
            selecoes = mercado.get("selecoes") or {}
            if linha in ("casa", "visitante", "sem_gol") and (
                _numeros_iguais(selecoes.get(linha), odd)
            ):
                oferta_virtual = {
                    "linha": linha,
                    "over": selecoes.get(linha),
                }
                houve_correspondencia_economica = True
                if (
                    assinatura_esperada is None
                    or assinatura_origem_mercado(
                        _origem_oferta(mercado, oferta_virtual)
                    ) == assinatura_esperada
                ):
                    candidatas.append((mercado, oferta_virtual))
            continue

        if mercado_candidato == "gol_ht":
            if categoria != "gols":
                continue
            oferta = _oferta_exata(
                mercado.get("ofertas_ht"), linha, odd
            )
        elif mercado_candidato in ("escanteios_1t", "escanteios_2t"):
            periodo = "1T" if mercado_candidato.endswith("1t") else "2T"
            dados_periodo = (
                (mercado.get("ofertas_periodos") or {}).get(periodo) or {}
            )
            if categoria != "escanteios" or tipo != "asiatico":
                continue
            oferta = _oferta_exata(
                dados_periodo.get("ofertas"), linha, odd
            )
        else:
            filtros = {
                "gol_ft": ("gols", None),
                "proximo_escanteio": ("escanteios", "total"),
                "escanteios_ft_asiatico": ("escanteios", "asiatico"),
            }
            filtro = filtros.get(mercado_candidato)
            if filtro is None:
                continue
            categoria_esperada, tipo_esperado = filtro
            if categoria != categoria_esperada or escopo != "total":
                continue
            if tipo_esperado is not None and tipo != tipo_esperado:
                continue
            if formato != "duas_opcoes":
                continue
            oferta = _oferta_exata(mercado.get("ofertas"), linha, odd)

        if oferta is not None:
            houve_correspondencia_economica = True
            if (
                assinatura_esperada is None
                or assinatura_origem_mercado(
                    _origem_oferta(mercado, oferta)
                ) == assinatura_esperada
            ):
                candidatas.append((mercado, oferta))
    if not candidatas:
        motivo = (
            "origem_mercado_entrada_divergente"
            if assinatura_esperada is not None
            and houve_correspondencia_economica
            else None
        )
        return None, None, False, motivo

    def chave(item):
        mercado, oferta = item
        coletado = _primeiro_definido(
            oferta.get("coletado_em"), mercado.get("coletado_em"),
            oferta.get("recebido_em"), mercado.get("recebido_em"),
        )
        instante = _interpretar_instante(coletado)
        if instante is None:
            return (False, float("-inf"))
        return (True, _utc_ingenuo(instante).timestamp())

    escolhida = max(candidatas, key=chave)
    chave_escolhida = chave(escolhida)
    empatadas = [item for item in candidatas if chave(item) == chave_escolhida]

    def assinatura(item):
        mercado, oferta = item
        if candidato.get("mercado") == "proximo_gol":
            selecoes = mercado.get("selecoes") or {}
            cotacao = tuple(_numero(selecoes.get(chave_selecao)) for chave_selecao in (
                "casa", "visitante", "sem_gol"
            ))
        else:
            cotacao = tuple(_numero(oferta.get(chave_oferta)) for chave_oferta in (
                "linha", "over", "under"
            ))
        return (
            cotacao,
            str(_primeiro_definido(
                oferta.get("fonte"), mercado.get("fonte")
            ) or "").strip().casefold(),
            str(_primeiro_definido(
                oferta.get("bookmaker"), mercado.get("bookmaker")
            ) or "").strip().casefold(),
            _primeiro_definido(oferta.get("cache"), mercado.get("cache")),
            assinatura_origem_mercado(_origem_oferta(mercado, oferta)),
        )

    cotacao_univoca = len({assinatura(item) for item in empatadas}) == 1
    return escolhida[0], escolhida[1], cotacao_univoca, None


def _primeiro_definido(*valores):
    for valor in valores:
        if valor is not None:
            return valor
    return None


def _instante_iso(valor):
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
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
        # Instantes ingênuos do monitor são horários locais. Tratar um deles
        # como UTC pode transformar uma odd antiga em idade zero quando a
        # fonte externa usa ISO com fuso explícito.
        valor = valor.astimezone()
    return valor.astimezone(timezone.utc).replace(tzinfo=None)


def _idade_por_instante(coletado_em, referencia):
    coletado = _interpretar_instante(coletado_em)
    if coletado is None:
        return None
    referencia = _interpretar_instante(referencia)
    if referencia is None:
        return None
    return max(
        (_utc_ingenuo(referencia) - _utc_ingenuo(coletado)).total_seconds(),
        0.0,
    )


def _extrair_proveniencia(mercado, oferta, referencia):
    fonte_explicita = _primeiro_definido(
        oferta.get("fonte"), mercado.get("fonte")
    )
    bookmaker = _primeiro_definido(
        oferta.get("bookmaker"), mercado.get("bookmaker")
    )
    coletado_bruto = _primeiro_definido(
        oferta.get("coletado_em"), mercado.get("coletado_em")
    )
    coletado_em = _instante_iso(coletado_bruto)
    idade_declarada_bruta = _primeiro_definido(
        oferta.get("idade_segundos"), mercado.get("idade_segundos")
    )
    idade_declarada = _numero(idade_declarada_bruta)
    cache = _primeiro_definido(
        oferta.get("cache"), mercado.get("cache")
    )
    cache_valido = isinstance(cache, bool)
    coletado_valido = (
        coletado_em is not None
        and _interpretar_instante(coletado_em) is not None
    )

    # O coletor PackBall não grava uma fonte textual, mas sempre carimba o
    # mercado com instante e booleano de cache. Não inferimos PackBall de um
    # mero valor ausente, pois o mesmo dicionário também pode conter API.
    fonte = fonte_explicita
    if (
        not fonte
        and coletado_valido
        and cache_valido
    ):
        fonte = "packball"

    idade_instante = _idade_por_instante(coletado_em, referencia)
    idades_validas = [
        valor
        for valor in (idade_declarada, idade_instante)
        if valor is not None and valor >= 0
    ]
    idade = max(idades_validas) if idades_validas else None
    return {
        "fonte_odds": str(fonte).strip() if fonte else None,
        "bookmaker_odds": bookmaker,
        "coletado_em_odds": coletado_em,
        "idade_odds_segundos": (
            round(float(idade), 3) if idade is not None else None
        ),
        "odds_cache": cache if cache_valido else None,
        "tipo_mercado_odds": mercado.get("tipo_mercado"),
        "_cache_valido": cache_valido,
        "_coletado_invalido": bool(
            coletado_em is not None and not coletado_valido
        ),
        "_idade_declarada_invalida": bool(
            idade_declarada_bruta is not None
            and (
                idade_declarada is None
                or idade_declarada < 0
            )
        ),
    }


def _congelar_cotacao_entrada(candidato, mercado, oferta, proveniencia):
    """Materializa a cotacao sincronizada usada na decisao.

    A evidencia fica dentro de ``features_json`` quando o candidato for
    persistido. O registro nao tenta completar lados ausentes nem inferir uma
    casa: sem o par binario inteiro (ou as tres vias de proximo gol), nada e
    congelado.
    """
    fonte = proveniencia.get("fonte_odds")
    cache = proveniencia.get("odds_cache")
    idade = _numero(proveniencia.get("idade_odds_segundos"))
    if not fonte or not isinstance(cache, bool) or idade is None or idade < 0:
        return None

    origem_bruta = _origem_oferta(mercado, oferta)
    origem = normalizar_origem_mercado(origem_bruta)
    origem_esperada = _origem_esperada(candidato)
    assinatura_esperada = assinatura_origem_mercado(origem_esperada)
    if origem_esperada is not None and (
        assinatura_esperada is None
        or assinatura_origem_mercado(origem) != assinatura_esperada
    ):
        return None

    base = {
        "schema": (
            VERSAO_COTACAO_ENTRADA_CLV
            if origem is not None else VERSAO_COTACAO_ENTRADA_CLV_V1
        ),
        "mercado": candidato.get("mercado"),
        "fonte": fonte,
        "bookmaker": proveniencia.get("bookmaker_odds"),
        "coletado_em": proveniencia.get("coletado_em_odds"),
        "idade_segundos": round(float(idade), 3),
        "cache": cache,
    }
    if origem is not None:
        base["origem_mercado"] = origem
    if candidato.get("mercado") == "proximo_gol":
        selecao = str(candidato.get("linha") or "").strip().casefold()
        if selecao not in {"casa", "visitante", "sem_gol"}:
            return None
        selecoes = mercado.get("selecoes") or {}
        odds = {
            chave: _numero(selecoes.get(chave))
            for chave in ("casa", "visitante", "sem_gol")
        }
        if any(valor is None or valor <= 1.0 for valor in odds.values()):
            return None
        if not _numeros_iguais(odds[selecao], candidato.get("odd")):
            return None
        return {
            **base,
            "tipo": "tres_vias",
            "selecao": selecao,
            "odds": odds,
            "odd_selecionada": odds[selecao],
        }

    linha = _numero(oferta.get("linha"))
    over = _numero(oferta.get("over"))
    under = _numero(oferta.get("under"))
    if (
        linha is None
        or over is None or over <= 1.0
        or under is None or under <= 1.0
        or not _numeros_iguais(linha, candidato.get("linha"))
        or not _numeros_iguais(over, candidato.get("odd"))
    ):
        return None
    return {
        **base,
        "tipo": "binaria",
        "linha": linha,
        "over": over,
        "under": under,
        "odd_selecionada": over,
    }


def validar_cotacao_executavel_oficial(candidato):
    """Exige uma oferta Bet365 íntegra antes de qualquer entrada oficial.

    Fontes agregadas continuam úteis para observação, backtest e simulação,
    mas não provam que o preço exibido pode ser executado pelo usuário. O
    contrato usa somente a fotografia imutável criada por
    :func:`aplicar_proveniencia_odds`; não tenta inferir casa, completar lados
    nem procurar uma cotação substituta no histórico.
    """
    resultado = {
        "versao": VERSAO_CUSTODIA_COTACAO_OFICIAL,
        "apto": False,
        "estado": "bloqueado",
        "motivo": None,
        "fonte_exigida": FONTE_COTACAO_EXECUTAVEL_OFICIAL,
        "bookmaker_exigida": BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
        "aplicacao": "somente_entrada_oficial",
        "simulacoes_afetadas": False,
    }
    if not isinstance(candidato, dict):
        resultado["motivo"] = "candidato_invalido"
        return resultado
    features = candidato.get("features")
    if not isinstance(features, dict):
        resultado["motivo"] = "features_ausentes"
        return resultado
    if features.get(CHAVE_ESTADO_COTACAO_ENTRADA) != (
        ESTADO_COTACAO_CONGELADA
    ):
        resultado["motivo"] = "cotacao_entrada_nao_congelada"
        return resultado
    cotacao = features.get("cotacao_entrada_clv")
    if not isinstance(cotacao, dict):
        resultado["motivo"] = "prova_cotacao_entrada_ausente"
        return resultado
    if cotacao.get("schema") != VERSAO_COTACAO_ENTRADA_CLV:
        resultado["motivo"] = "schema_cotacao_sem_origem_exata"
        return resultado

    fonte = str(cotacao.get("fonte") or "").strip().casefold()
    bookmaker = str(cotacao.get("bookmaker") or "").strip().casefold()
    resultado.update({
        "fonte_observada": fonte or None,
        "bookmaker_observada": bookmaker or None,
    })
    if fonte != FONTE_COTACAO_EXECUTAVEL_OFICIAL:
        resultado["motivo"] = "fonte_cotacao_nao_executavel"
        return resultado
    if bookmaker != BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL:
        resultado["motivo"] = "bookmaker_cotacao_nao_executavel"
        return resultado

    for valor, esperado, motivo in (
        (
            candidato.get("fonte_odds"),
            FONTE_COTACAO_EXECUTAVEL_OFICIAL,
            "fonte_candidato_divergente",
        ),
        (
            features.get("fonte_odds"),
            FONTE_COTACAO_EXECUTAVEL_OFICIAL,
            "fonte_features_divergente",
        ),
        (
            candidato.get("bookmaker_odds"),
            BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
            "bookmaker_candidato_divergente",
        ),
        (
            features.get("bookmaker_odds"),
            BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
            "bookmaker_features_divergente",
        ),
    ):
        if str(valor or "").strip().casefold() != esperado:
            resultado["motivo"] = motivo
            return resultado

    if cotacao.get("mercado") != candidato.get("mercado"):
        resultado["motivo"] = "mercado_cotacao_divergente"
        return resultado
    if not _numeros_iguais(
        cotacao.get("odd_selecionada"), candidato.get("odd")
    ):
        resultado["motivo"] = "odd_cotacao_divergente"
        return resultado
    if not isinstance(cotacao.get("cache"), bool):
        resultado["motivo"] = "cache_cotacao_indeterminado"
        return resultado
    if _interpretar_instante(cotacao.get("coletado_em")) is None:
        resultado["motivo"] = "instante_cotacao_invalido"
        return resultado
    idade = _numero(cotacao.get("idade_segundos"))
    if idade is None or idade < 0:
        resultado["motivo"] = "idade_cotacao_invalida"
        return resultado

    origem = normalizar_origem_mercado(cotacao.get("origem_mercado"))
    if origem is None:
        resultado["motivo"] = "origem_mercado_cotacao_invalida"
        return resultado
    if (
        str(origem.get("fonte") or "").strip().casefold() != fonte
        or str(origem.get("bookmaker") or "").strip().casefold()
        != bookmaker
    ):
        resultado["motivo"] = "origem_mercado_cotacao_divergente"
        return resultado

    tipo = cotacao.get("tipo")
    if tipo == "binaria":
        if (
            not _numeros_iguais(cotacao.get("linha"), candidato.get("linha"))
            or not _numeros_iguais(
                cotacao.get("over"), cotacao.get("odd_selecionada")
            )
            or _numero(cotacao.get("under")) is None
            or _numero(cotacao.get("under")) <= 1.0
        ):
            resultado["motivo"] = "contrato_binario_cotacao_invalido"
            return resultado
    elif tipo == "tres_vias":
        selecao = str(cotacao.get("selecao") or "").strip().casefold()
        odds = cotacao.get("odds")
        if (
            selecao not in {"casa", "visitante", "sem_gol"}
            or not isinstance(odds, dict)
            or any(
                _numero(odds.get(chave)) is None
                or _numero(odds.get(chave)) <= 1.0
                for chave in ("casa", "visitante", "sem_gol")
            )
            or not _numeros_iguais(
                odds.get(selecao), cotacao.get("odd_selecionada")
            )
            or str(candidato.get("linha") or "").strip().casefold()
            != selecao
        ):
            resultado["motivo"] = "contrato_tres_vias_cotacao_invalido"
            return resultado
    else:
        resultado["motivo"] = "tipo_cotacao_invalido"
        return resultado

    resultado.update({
        "apto": True,
        "estado": "apto",
        "motivo": None,
        "schema_cotacao": cotacao.get("schema"),
        "tipo_cotacao": tipo,
        "origem_mercado": assinatura_origem_mercado(origem),
    })
    return resultado


def resumir_custodia_cotacao_oficial(conexao, limite=1000):
    """Resume, sem alterar o SQLite, a nova fronteira de execução oficial."""
    try:
        limite = max(1, int(limite))
    except (TypeError, ValueError):
        limite = 1000
    linhas = conexao.execute(
        """
        SELECT id, mercado, linha, odd, probabilidade_calibrada, features_json
        FROM sinais
        WHERE status = 'aprovado'
          AND probabilidade_calibrada IS NOT NULL
          AND features_json LIKE '%cotacao_entrada_clv_estado%'
        ORDER BY id DESC
        LIMIT ?
        """,
        (limite,),
    ).fetchall()
    motivos = Counter()
    por_mercado = Counter()
    aptos = 0
    for linha in linhas:
        item = dict(linha)
        try:
            features = json.loads(item.get("features_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        candidato = {
            "mercado": item.get("mercado"),
            "linha": item.get("linha"),
            "odd": item.get("odd"),
            "probabilidade_calibrada": item.get(
                "probabilidade_calibrada"
            ),
            "fonte_odds": features.get("fonte_odds"),
            "bookmaker_odds": features.get("bookmaker_odds"),
            "features": features,
        }
        auditoria = validar_cotacao_executavel_oficial(candidato)
        mercado = str(item.get("mercado") or "desconhecido")
        if auditoria.get("apto") is True:
            aptos += 1
            por_mercado[f"{mercado}:apto"] += 1
        else:
            motivo = str(auditoria.get("motivo") or "motivo_ausente")
            motivos[motivo] += 1
            por_mercado[f"{mercado}:bloqueado"] += 1
    bloqueios_gateway = conexao.execute(
        """
        SELECT COUNT(*) AS total
        FROM entregas_alertas
        WHERE canal = 'gateway:oficial'
          AND status = 'bloqueado'
          AND erro = 'cotacao_oficial_nao_executavel'
        """
    ).fetchone()
    total = len(linhas)
    return {
        "versao": VERSAO_CUSTODIA_COTACAO_OFICIAL,
        "estado": "ativo",
        "fonte_exigida": FONTE_COTACAO_EXECUTAVEL_OFICIAL,
        "bookmaker_exigida": BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
        "sinais_analisados": total,
        "aptos": aptos,
        "bloqueados": total - aptos,
        "motivos_bloqueio": dict(sorted(motivos.items())),
        "por_mercado": dict(sorted(por_mercado.items())),
        "bloqueios_gateway": int(bloqueios_gateway["total"] or 0),
        "simulacoes_afetadas": False,
        "altera_selecao_sombra": False,
    }


def _adicionar_unico(lista, item):
    if item not in lista:
        lista.append(item)


def _atualizar_status(candidato, limiar_aprovacao):
    bloqueios = candidato.get("bloqueios") or []
    if bloqueios:
        candidato["status"] = "rejeitado"
        return
    if candidato.get("status") not in ("aprovado", "rejeitado"):
        return
    pontuacao = _numero(candidato.get("pontuacao_tecnica"))
    candidato["status"] = (
        "aprovado"
        if pontuacao is not None and pontuacao >= float(limiar_aprovacao)
        else "rejeitado"
    )


def aplicar_proveniencia_odds(
    candidatos,
    odds,
    instante=None,
    idade_maxima_segundos=IDADE_ODD_MAXIMA_SEGUNDOS,
    limiar_aprovacao=LIMIAR_APROVACAO_PADRAO,
):
    """Enriquece, valida e devolve a mesma coleção de candidatos.

    A função muta cada candidato para permitir integração sem mudar o restante
    do pipeline. ``instante`` deve representar o momento da decisão; quando
    omitido, usa o relógio atual. A idade efetiva é sempre o maior valor entre
    a idade declarada pela fonte e a idade derivada de ``coletado_em``.
    """
    referencia = instante or datetime.now()
    for candidato in candidatos or []:
        if not isinstance(candidato, dict):
            continue
        bloqueios = [
            item
            for item in candidato.get("bloqueios") or []
            if item not in BLOQUEIOS_PROVENIENCIA
        ]
        coerencia_curva = None
        mercado, oferta, cotacao_univoca, motivo_origem = _localizar_oferta(
            candidato, odds
        )
        if mercado is None or oferta is None:
            proveniencia = {
                "fonte_odds": None,
                "bookmaker_odds": None,
                "coletado_em_odds": None,
                "idade_odds_segundos": None,
                "odds_cache": None,
                "tipo_mercado_odds": None,
            }
            if motivo_origem:
                _adicionar_unico(bloqueios, motivo_origem)
            elif _numero(candidato.get("odd")) is not None:
                _adicionar_unico(bloqueios, "oferta_odds_nao_rastreavel")
        else:
            dados = _extrair_proveniencia(mercado, oferta, referencia)
            proveniencia = {
                chave: valor
                for chave, valor in dados.items()
                if not chave.startswith("_")
            }
            if not proveniencia["fonte_odds"]:
                _adicionar_unico(bloqueios, "fonte_odds_desconhecida")
            if not dados["_cache_valido"]:
                _adicionar_unico(bloqueios, "cache_odds_indeterminado")
            if dados["_coletado_invalido"]:
                _adicionar_unico(bloqueios, "coletado_em_odds_invalido")
            if dados["_idade_declarada_invalida"]:
                _adicionar_unico(bloqueios, "idade_odds_invalida")
            idade = proveniencia["idade_odds_segundos"]
            if idade is None:
                _adicionar_unico(bloqueios, "frescor_odds_indeterminado")
            elif idade > float(idade_maxima_segundos):
                _adicionar_unico(bloqueios, "odds_desatualizadas")
            if candidato.get("mercado") != "proximo_gol":
                coerencia_curva = validar_coerencia_curva_odds(
                    _ofertas_curva(candidato, mercado),
                    origem_selecionada=_origem_oferta(mercado, oferta),
                )
                if coerencia_curva["valida"] is not True:
                    _adicionar_unico(
                        bloqueios, coerencia_curva["motivo"]
                    )

        candidato.update(proveniencia)
        features = candidato.get("features")
        if not isinstance(features, dict):
            features = {}
        features = {**features, **proveniencia}
        if coerencia_curva is not None:
            features["coerencia_curva_odds"] = coerencia_curva
        cotacao_entrada = None
        curva_valida = bool(
            coerencia_curva is None or coerencia_curva.get("valida") is True
        )
        if (
            mercado is not None and oferta is not None
            and cotacao_univoca and curva_valida
        ):
            cotacao_entrada = _congelar_cotacao_entrada(
                candidato, mercado, oferta, proveniencia
            )
        if cotacao_entrada is not None:
            features["cotacao_entrada_clv"] = cotacao_entrada
            features[CHAVE_ESTADO_COTACAO_ENTRADA] = (
                ESTADO_COTACAO_CONGELADA
            )
        else:
            # Evita preservar evidencia velha quando a mesma estrutura de
            # candidato e reavaliada com uma oferta nova incompleta.
            features.pop("cotacao_entrada_clv", None)
            if mercado is None or oferta is None:
                estado_cotacao = motivo_origem or "oferta_nao_localizada"
            elif not cotacao_univoca:
                estado_cotacao = "oferta_ambigua"
            elif not curva_valida:
                estado_cotacao = coerencia_curva["motivo"]
            else:
                estado_cotacao = "mercado_incompleto_ou_invalido"
            features[CHAVE_ESTADO_COTACAO_ENTRADA] = estado_cotacao
        candidato["features"] = features
        candidato["bloqueios"] = bloqueios
        _atualizar_status(candidato, limiar_aprovacao)
    return candidatos
