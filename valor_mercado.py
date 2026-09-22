"""Valor de mercado conservador derivado da calibração e da odd exata."""

from __future__ import annotations

import json
import math

from origem_mercado import (
    assinatura_origem_mercado,
    normalizar_origem_mercado,
)


VERSAO = "valor-mercado-calibrado-conservador-v6"
VALOR_ESPERADO_MINIMO = 0.02
VANTAGEM_SEM_VIG_MINIMA = 0.0
MARGEM_BOOKMAKER_MINIMA = -0.02
MARGEM_BOOKMAKER_MAXIMA = 0.20
VERSAO_COTACAO_ENTRADA_CLV_V1 = "cotacao-entrada-clv-v1"
VERSAO_COTACAO_ENTRADA_CLV = "cotacao-entrada-clv-v2"
CHAVE_ESTADO_COTACAO_ENTRADA = "cotacao_entrada_clv_estado"
ESTADO_COTACAO_CONGELADA = "congelada_v1"


def _numero(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _features_dict(valor):
    if isinstance(valor, dict):
        return valor
    if isinstance(valor, str):
        try:
            carregado = json.loads(valor)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return carregado if isinstance(carregado, dict) else {}
    return {}


def _texto_normalizado(valor):
    return str(valor or "").strip().casefold()


def avaliar_margem_bookmaker(tipo, odds):
    """Valida a coerencia estrutural do mercado usado para retirar o vig.

    Uma pequena margem negativa continua permitida para não apagar um possível
    desajuste real. Valores fora da faixa ampla observada são tratados como
    provável mistura temporal/de bookmaker ou preço corrompido.
    """
    tipo = _texto_normalizado(tipo)
    esperadas = 2 if tipo == "binaria" else 3 if tipo == "tres_vias" else 0
    valores = [_numero(valor) for valor in (odds or [])]
    if (
        not esperadas
        or len(valores) != esperadas
        or any(valor is None or valor <= 1.0 for valor in valores)
    ):
        return {
            "disponivel": False,
            "plausivel": False,
            "margem_bookmaker": None,
            "margem_minima": MARGEM_BOOKMAKER_MINIMA,
            "margem_maxima": MARGEM_BOOKMAKER_MAXIMA,
        }
    margem = sum(1.0 / valor for valor in valores) - 1.0
    plausivel = bool(
        margem + 1e-12 >= MARGEM_BOOKMAKER_MINIMA
        and margem - 1e-12 <= MARGEM_BOOKMAKER_MAXIMA
    )
    return {
        "disponivel": True,
        "plausivel": plausivel,
        "margem_bookmaker": round(margem, 6),
        "margem_minima": MARGEM_BOOKMAKER_MINIMA,
        "margem_maxima": MARGEM_BOOKMAKER_MAXIMA,
    }


def _proveniencia_candidato(candidato):
    features = _features_dict((candidato or {}).get("features"))
    return (
        _texto_normalizado(
            (candidato or {}).get("fonte_odds")
            or features.get("fonte_odds")
        ),
        _texto_normalizado(
            (candidato or {}).get("bookmaker_odds")
            or features.get("bookmaker_odds")
        ),
    )


def _proveniencia_oferta(oferta, mercado):
    return (
        _texto_normalizado(
            (oferta or {}).get("fonte") or (mercado or {}).get("fonte")
        ),
        _texto_normalizado(
            (oferta or {}).get("bookmaker")
            or (mercado or {}).get("bookmaker")
        ),
    )


def _selecionar_referencia_univoca(candidato, referencias, assinatura):
    """Prefere a proveniência declarada e rejeita preços contraditórios."""
    referencias = list(referencias or [])
    if not referencias:
        return None
    fonte_alvo, bookmaker_alvo = _proveniencia_candidato(candidato)
    if fonte_alvo:
        mesma_fonte = [
            item for item in referencias if item["fonte"] == fonte_alvo
        ]
        if mesma_fonte:
            referencias = mesma_fonte
    if bookmaker_alvo:
        mesma_bookmaker = [
            item for item in referencias
            if item["bookmaker"] == bookmaker_alvo
        ]
        if mesma_bookmaker:
            referencias = mesma_bookmaker
    assinaturas = {assinatura(item) for item in referencias}
    if len(assinaturas) != 1:
        return None
    return referencias[0]


def odd_oposta_sincronizada(candidato):
    """Retorna a odd oposta somente quando o par tem origem sincronizada."""
    odd_oposta = _numero((candidato or {}).get("odd_oposta"))
    if (
        odd_oposta is not None
        and odd_oposta > 1.0
        and (candidato or {}).get("odd_par_sincronizado") is True
    ):
        return odd_oposta
    features = _features_dict((candidato or {}).get("features"))
    if features.get("odd_par_sincronizado") is not True:
        return None
    odd_oposta = _numero(features.get("odd_oposta"))
    return odd_oposta if odd_oposta is not None and odd_oposta > 1.0 else None


def referencia_tres_vias_sincronizada(candidato):
    """Retorna o trio Casa/Visitante/Sem gol somente com prova de sincronia."""
    candidato = candidato or {}
    features = _features_dict(candidato.get("features"))
    if candidato.get("mercado_odds_sincronizado") is True:
        odds = candidato.get("odds_mercado_sincronizadas")
        selecao = candidato.get("selecao_mercado")
    else:
        odds = None
        selecao = None
    if not isinstance(odds, dict):
        if features.get("mercado_odds_sincronizado") is not True:
            return None
        odds = features.get("odds_mercado_sincronizadas")
        selecao = features.get("selecao_mercado")
    if not isinstance(odds, dict):
        return None
    selecao = _texto_normalizado(selecao)
    normalizadas = {
        chave: _numero(odds.get(chave))
        for chave in ("casa", "visitante", "sem_gol")
    }
    if (
        selecao not in normalizadas
        or any(valor is None or valor <= 1.0 for valor in normalizadas.values())
    ):
        return None
    odd_selecionada = _numero(candidato.get("odd"))
    if (
        odd_selecionada is not None
        and not math.isclose(
            normalizadas[selecao], odd_selecionada, abs_tol=1e-9
        )
    ):
        return None
    return {"selecao": selecao, "odds": normalizadas}


def _cotacao_entrada_congelada(candidato):
    """Valida o contrato completo congelado pela camada de proveniencia."""
    candidato = candidato or {}
    features = _features_dict(candidato.get("features"))
    evidencia = features.get("cotacao_entrada_clv")
    if evidencia is None:
        return None
    if not isinstance(evidencia, dict):
        return False
    estado = features.get(CHAVE_ESTADO_COTACAO_ENTRADA)
    if estado is not None and estado != ESTADO_COTACAO_CONGELADA:
        return False
    schema = evidencia.get("schema")
    if (
        schema not in {
            VERSAO_COTACAO_ENTRADA_CLV_V1,
            VERSAO_COTACAO_ENTRADA_CLV,
        }
        or evidencia.get("mercado") != candidato.get("mercado")
        or not _texto_normalizado(evidencia.get("fonte"))
        or evidencia.get("cache") not in (True, False)
        or _numero(evidencia.get("idade_segundos")) is None
        or _numero(evidencia.get("idade_segundos")) < 0
    ):
        return False
    fonte, bookmaker = _proveniencia_candidato(candidato)
    if (
        _texto_normalizado(evidencia.get("fonte")) != fonte
        or _texto_normalizado(evidencia.get("bookmaker")) != bookmaker
    ):
        return False
    acompanhamento = features.get("acompanhamento_odd_rapido")
    acompanhamento = acompanhamento if isinstance(acompanhamento, dict) else {}
    origem_esperada = (
        features.get("origem_mercado_odd")
        or acompanhamento.get("origem_mercado_odd")
    )
    assinatura_esperada = assinatura_origem_mercado(origem_esperada)
    if origem_esperada is not None and assinatura_esperada is None:
        return False
    if schema == VERSAO_COTACAO_ENTRADA_CLV_V1:
        if origem_esperada is not None:
            return False
    else:
        origem = normalizar_origem_mercado(evidencia.get("origem_mercado"))
        if (
            origem is None
            or origem["fonte"] != fonte
            or origem["bookmaker"] != bookmaker
            or (
                assinatura_esperada is not None
                and assinatura_origem_mercado(origem) != assinatura_esperada
            )
        ):
            return False
    odd = _numero(candidato.get("odd"))
    odd_evidencia = _numero(evidencia.get("odd_selecionada"))
    if (
        odd is None or odd <= 1.0 or odd_evidencia is None
        or not math.isclose(odd, odd_evidencia, abs_tol=1e-9)
    ):
        return False
    if candidato.get("mercado") == "proximo_gol":
        selecao = _texto_normalizado(candidato.get("linha"))
        odds = {
            chave: _numero((evidencia.get("odds") or {}).get(chave))
            for chave in ("casa", "visitante", "sem_gol")
        }
        if (
            evidencia.get("tipo") != "tres_vias"
            or selecao not in {"casa", "visitante"}
            or _texto_normalizado(evidencia.get("selecao")) != selecao
            or any(valor is None or valor <= 1.0 for valor in odds.values())
            or not math.isclose(odds[selecao], odd, abs_tol=1e-9)
        ):
            return False
        if schema == VERSAO_COTACAO_ENTRADA_CLV and (
            set(origem["lados"]) != {"casa", "visitante", "sem_gol"}
        ):
            return False
        return {"tipo": "tres_vias", "selecao": selecao, "odds": odds}

    linha = _numero(candidato.get("linha"))
    linha_evidencia = _numero(evidencia.get("linha"))
    over = _numero(evidencia.get("over"))
    under = _numero(evidencia.get("under"))
    if (
        evidencia.get("tipo") != "binaria"
        or linha is None or linha_evidencia is None
        or not math.isclose(linha, linha_evidencia, abs_tol=1e-9)
        or over is None or over <= 1.0 or under is None or under <= 1.0
        or not math.isclose(over, odd, abs_tol=1e-9)
    ):
        return False
    if schema == VERSAO_COTACAO_ENTRADA_CLV and (
        set(origem["lados"]) != {"over", "under"}
        or _numero(origem["linha"]) is None
        or not math.isclose(
            _numero(origem["linha"]), linha, abs_tol=1e-9
        )
    ):
        return False
    return {"tipo": "binaria", "linha": linha, "over": over, "under": under}


def _anexar_referencia_congelada(candidato, evidencia):
    features = dict(_features_dict(candidato.get("features")))
    bruto = features["cotacao_entrada_clv"]
    if evidencia["tipo"] == "tres_vias":
        features.update({
            "selecao_mercado": evidencia["selecao"],
            "odds_mercado_sincronizadas": dict(evidencia["odds"]),
            "mercado_odds_sincronizado": True,
            "fonte_referencia_sem_vig": bruto.get("fonte"),
            "bookmaker_referencia_sem_vig": bruto.get("bookmaker"),
        })
        candidato["features"] = features
        candidato["selecao_mercado"] = evidencia["selecao"]
        candidato["odds_mercado_sincronizadas"] = dict(evidencia["odds"])
        candidato["mercado_odds_sincronizado"] = True
        return True
    features.update({
        "odd_oposta": evidencia["under"],
        "odd_par_sincronizado": True,
        "fonte_referencia_sem_vig": bruto.get("fonte"),
        "bookmaker_referencia_sem_vig": bruto.get("bookmaker"),
    })
    candidato["features"] = features
    candidato["odd_oposta"] = evidencia["under"]
    candidato["odd_par_sincronizado"] = True
    return True


def anexar_par_odds_sincronizado(candidato, odds):
    """Localiza a referência completa que originou a seleção no snapshot.

    A busca ocorre depois da decisão do motor e não altera mercado, linha,
    preço selecionado, nota ou status. Ela apenas preserva o par exato usado
    no mesmo snapshot para a auditoria sem vig. Em ``proximo_gol``, preserva
    obrigatoriamente as três saídas: Casa, Visitante e Sem gol.
    """
    congelada = _cotacao_entrada_congelada(candidato)
    if congelada is False:
        return False
    if congelada is not None:
        return _anexar_referencia_congelada(candidato, congelada)
    features = _features_dict((candidato or {}).get("features"))
    if CHAVE_ESTADO_COTACAO_ENTRADA in features:
        # O fallback abaixo existe apenas para sinais históricos anteriores
        # ao contrato congelado. Se a camada atual já avaliou a cotação e não
        # produziu prova, reconstruí-la aqui apagaria a ambiguidade original.
        return False

    mercado_alvo = str((candidato or {}).get("mercado") or "")
    linha_original = (candidato or {}).get("linha")
    odd_alvo = _numero((candidato or {}).get("odd"))
    if mercado_alvo == "proximo_gol":
        selecao_alvo = _texto_normalizado(linha_original)
        if selecao_alvo not in {"casa", "visitante"} or odd_alvo is None:
            return False
        referencias = []
        for mercado in (odds or {}).get("ao_vivo") or []:
            selecoes = mercado.get("selecoes") or {}
            if not isinstance(selecoes, dict):
                continue
            normalizadas = {
                chave: _numero(selecoes.get(chave))
                for chave in ("casa", "visitante", "sem_gol")
            }
            if (
                any(
                    valor is None or valor <= 1.0
                    for valor in normalizadas.values()
                )
                or not math.isclose(
                    normalizadas[selecao_alvo], odd_alvo, abs_tol=1e-9
                )
            ):
                continue
            fonte, bookmaker = _proveniencia_oferta({}, mercado)
            referencias.append({
                "odds": normalizadas,
                "fonte": fonte,
                "bookmaker": bookmaker,
            })
        referencia = _selecionar_referencia_univoca(
            candidato,
            referencias,
            lambda item: tuple(
                round(float(item["odds"][chave]), 9)
                for chave in ("casa", "visitante", "sem_gol")
            ),
        )
        if referencia is None:
            return False
        features = dict(_features_dict(candidato.get("features")))
        features.update({
            "selecao_mercado": selecao_alvo,
            "odds_mercado_sincronizadas": dict(referencia["odds"]),
            "mercado_odds_sincronizado": True,
            "fonte_referencia_sem_vig": referencia["fonte"] or None,
            "bookmaker_referencia_sem_vig": (
                referencia["bookmaker"] or None
            ),
        })
        candidato["features"] = features
        candidato["selecao_mercado"] = selecao_alvo
        candidato["odds_mercado_sincronizadas"] = dict(
            referencia["odds"]
        )
        candidato["mercado_odds_sincronizado"] = True
        return True

    configuracoes = {
        "gol_ft": ("gols", None, "ofertas", None),
        "gol_ht": ("gols", None, "ofertas_ht", None),
        "proximo_escanteio": (
            "escanteios", "total", "ofertas", None
        ),
        "escanteios_ft_asiatico": (
            "escanteios", "asiatico", "ofertas", None
        ),
        "escanteios_1t": (
            "escanteios", "asiatico", "ofertas_periodos", "1T"
        ),
        "escanteios_2t": (
            "escanteios", "asiatico", "ofertas_periodos", "2T"
        ),
    }
    configuracao = configuracoes.get(mercado_alvo)
    linha_alvo = _numero((candidato or {}).get("linha"))
    if configuracao is None or linha_alvo is None or odd_alvo is None:
        return False
    categoria, tipo, campo, periodo = configuracao
    referencias = []
    for mercado in (odds or {}).get("ao_vivo") or []:
        if mercado.get("categoria") != categoria:
            continue
        if tipo is not None and mercado.get("tipo_mercado") != tipo:
            continue
        if campo == "ofertas_periodos":
            dados_periodo = (
                (mercado.get("ofertas_periodos") or {}).get(periodo) or {}
            )
            if dados_periodo.get("formato") != "duas_opcoes":
                continue
            ofertas = dados_periodo.get("ofertas") or []
        else:
            if campo == "ofertas" and (
                mercado.get("escopo") or "total"
            ) != "total":
                continue
            ofertas = mercado.get(campo) or []
        for oferta in ofertas:
            linha = _numero((oferta or {}).get("linha"))
            over = _numero((oferta or {}).get("over"))
            under = _numero((oferta or {}).get("under"))
            if (
                linha is None or over is None or under is None
                or under <= 1.0
                or not math.isclose(linha, linha_alvo, abs_tol=1e-9)
                or not math.isclose(over, odd_alvo, abs_tol=1e-9)
            ):
                continue
            fonte, bookmaker = _proveniencia_oferta(oferta, mercado)
            referencias.append({
                "under": under,
                "fonte": fonte,
                "bookmaker": bookmaker,
            })
    referencia = _selecionar_referencia_univoca(
        candidato,
        referencias,
        lambda item: round(float(item["under"]), 9),
    )
    if referencia is None:
        return False
    features = dict(_features_dict((candidato or {}).get("features")))
    features.update({
        "odd_oposta": referencia["under"],
        "odd_par_sincronizado": True,
        "fonte_referencia_sem_vig": referencia["fonte"] or None,
        "bookmaker_referencia_sem_vig": referencia["bookmaker"] or None,
    })
    candidato["features"] = features
    candidato["odd_oposta"] = referencia["under"]
    candidato["odd_par_sincronizado"] = True
    return True


def avaliar_valor_mercado(
    probabilidade_calibrada,
    odd,
    odd_oposta=None,
    *,
    odds_mercado=None,
    selecao_mercado=None,
    valor_esperado_minimo=VALOR_ESPERADO_MINIMO,
    vantagem_sem_vig_minima=VANTAGEM_SEM_VIG_MINIMA,
):
    """Calcula a margem conservadora contra o ponto de equilíbrio da odd.

    A probabilidade recebida é o menor limite de Wilson entre
    desenvolvimento e validação. Para mercados asiáticos, o cálculo binário
    ainda é conservador: half-green e half-red não recebem crédito adicional.
    """
    probabilidade = _numero(probabilidade_calibrada)
    preco = _numero(odd)
    preco_oposto = _numero(odd_oposta)
    minimo = _numero(valor_esperado_minimo)
    minimo_sem_vig = _numero(vantagem_sem_vig_minima)
    if (
        probabilidade is None or not 0 < probabilidade <= 1
        or preco is None or preco <= 1
        or minimo is None or minimo < 0
        or minimo_sem_vig is None or minimo_sem_vig < 0
    ):
        return {
            "versao": VERSAO,
            "estado": "indisponivel",
            "motivo": "probabilidade_ou_odd_invalida",
            "aprovado": False,
            "referencia_sem_vig_disponivel": False,
            "valor_esperado_minimo": (
                round(minimo, 6) if minimo is not None else None
            ),
        }

    probabilidade_equilibrio = 1.0 / preco
    selecao_mercado = _texto_normalizado(selecao_mercado)
    odds_tres_vias = None
    if isinstance(odds_mercado, dict):
        candidatas = {
            chave: _numero(odds_mercado.get(chave))
            for chave in ("casa", "visitante", "sem_gol")
        }
        if (
            selecao_mercado in candidatas
            and all(
                valor is not None and valor > 1.0
                for valor in candidatas.values()
            )
            and math.isclose(
                candidatas[selecao_mercado], preco, abs_tol=1e-9
            )
        ):
            odds_tres_vias = candidatas
    referencia_sem_vig_disponivel = bool(
        odds_tres_vias is not None
        or (preco_oposto is not None and preco_oposto > 1.0)
    )
    tipo_referencia_sem_vig = None
    qualidade_margem = avaliar_margem_bookmaker(None, [])
    if odds_tres_vias is not None:
        soma_implicitas = sum(1.0 / valor for valor in odds_tres_vias.values())
        probabilidade_mercado_sem_vig = (
            (1.0 / preco) / soma_implicitas
        )
        margem_bookmaker = soma_implicitas - 1.0
        vantagem_sem_vig = probabilidade - probabilidade_mercado_sem_vig
        tipo_referencia_sem_vig = "tres_vias"
        qualidade_margem = avaliar_margem_bookmaker(
            tipo_referencia_sem_vig,
            [odds_tres_vias[chave] for chave in (
                "casa", "visitante", "sem_gol"
            )],
        )
    elif referencia_sem_vig_disponivel:
        soma_implicitas = probabilidade_equilibrio + 1.0 / preco_oposto
        probabilidade_mercado_sem_vig = (
            probabilidade_equilibrio / soma_implicitas
        )
        margem_bookmaker = soma_implicitas - 1.0
        vantagem_sem_vig = probabilidade - probabilidade_mercado_sem_vig
        tipo_referencia_sem_vig = "binaria"
        qualidade_margem = avaliar_margem_bookmaker(
            tipo_referencia_sem_vig, [preco, preco_oposto]
        )
    else:
        probabilidade_mercado_sem_vig = None
        margem_bookmaker = None
        vantagem_sem_vig = None
    vantagem_probabilidade = probabilidade - probabilidade_equilibrio
    valor_esperado = probabilidade * preco - 1.0
    valor_suficiente = valor_esperado + 1e-12 >= minimo
    vantagem_sem_vig_suficiente = bool(
        vantagem_sem_vig is not None
        and vantagem_sem_vig + 1e-12 >= minimo_sem_vig
    )
    aprovado = bool(
        valor_suficiente
        and referencia_sem_vig_disponivel
        and qualidade_margem["plausivel"]
        and vantagem_sem_vig_suficiente
    )
    if (
        referencia_sem_vig_disponivel
        and not qualidade_margem["plausivel"]
    ):
        motivo = "margem_bookmaker_incoerente"
    elif not valor_suficiente:
        motivo = "valor_esperado_abaixo_minimo"
    elif not referencia_sem_vig_disponivel:
        motivo = "referencia_sem_vig_ausente"
    elif not vantagem_sem_vig_suficiente:
        motivo = "vantagem_sem_vig_abaixo_minimo"
    else:
        motivo = None
    return {
        "versao": VERSAO,
        "estado": "vantagem_conservadora" if aprovado else "sem_margem",
        "motivo": motivo,
        "probabilidade_calibrada_conservadora": round(probabilidade, 6),
        "probabilidade_equilibrio_odd": round(
            probabilidade_equilibrio, 6
        ),
        "referencia_sem_vig_disponivel": referencia_sem_vig_disponivel,
        "tipo_referencia_sem_vig": tipo_referencia_sem_vig,
        "odd_oposta": (
            round(preco_oposto, 6)
            if tipo_referencia_sem_vig == "binaria" else None
        ),
        "selecao_mercado": (
            selecao_mercado
            if tipo_referencia_sem_vig == "tres_vias" else None
        ),
        "odds_mercado_sincronizadas": (
            {
                chave: round(valor, 6)
                for chave, valor in odds_tres_vias.items()
            }
            if tipo_referencia_sem_vig == "tres_vias" else None
        ),
        "probabilidade_mercado_sem_vig": (
            round(probabilidade_mercado_sem_vig, 6)
            if probabilidade_mercado_sem_vig is not None else None
        ),
        "margem_bookmaker": (
            round(margem_bookmaker, 6)
            if margem_bookmaker is not None else None
        ),
        "margem_bookmaker_plausivel": (
            qualidade_margem["plausivel"]
            if referencia_sem_vig_disponivel else None
        ),
        "margem_bookmaker_minima": MARGEM_BOOKMAKER_MINIMA,
        "margem_bookmaker_maxima": MARGEM_BOOKMAKER_MAXIMA,
        "vantagem_probabilidade_sem_vig": (
            round(vantagem_sem_vig, 6)
            if vantagem_sem_vig is not None else None
        ),
        "vantagem_probabilidade": round(vantagem_probabilidade, 6),
        "odd_justa_conservadora": round(1.0 / probabilidade, 6),
        "valor_esperado_conservador": round(valor_esperado, 6),
        "valor_esperado_minimo": round(minimo, 6),
        "vantagem_probabilidade_sem_vig_minima": round(
            minimo_sem_vig, 6
        ),
        "modelo_retorno": "binario_pessimista",
        "aprovado": aprovado,
    }


def anexar_valor_mercado(candidato):
    """Anexa a decisão ao rastro persistível sem apagar outras features."""
    features = dict(_features_dict(candidato.get("features")))
    odd_oposta = odd_oposta_sincronizada({
        **candidato,
        "features": features,
    })
    if odd_oposta is not None and candidato.get("odd_oposta") is not None:
        features["odd_oposta"] = odd_oposta
        features["odd_par_sincronizado"] = True
    referencia_tres_vias = referencia_tres_vias_sincronizada({
        **candidato,
        "features": features,
    })
    if referencia_tres_vias is not None:
        features["selecao_mercado"] = referencia_tres_vias["selecao"]
        features["odds_mercado_sincronizadas"] = dict(
            referencia_tres_vias["odds"]
        )
        features["mercado_odds_sincronizado"] = True
    avaliacao = avaliar_valor_mercado(
        candidato.get("probabilidade_calibrada"),
        candidato.get("odd"),
        odd_oposta,
        odds_mercado=(
            referencia_tres_vias["odds"]
            if referencia_tres_vias else None
        ),
        selecao_mercado=(
            referencia_tres_vias["selecao"]
            if referencia_tres_vias else None
        ),
    )
    features["valor_mercado_conservador"] = avaliacao
    candidato["features"] = features
    candidato["valor_esperado_conservador"] = avaliacao.get(
        "valor_esperado_conservador"
    )
    candidato["odd_justa_conservadora"] = avaliacao.get(
        "odd_justa_conservadora"
    )
    return avaliacao


def _validar_referencia_contra_cotacao_entrada(odd, features):
    """Vincula o sem-vig persistido à prova exata usada na entrada."""
    features = _features_dict(features)
    evidencia = features.get("cotacao_entrada_clv")
    referencia_binaria = odd_oposta_sincronizada({"features": features})
    referencia_tres_vias = referencia_tres_vias_sincronizada({
        "features": features,
    })
    possui_referencia = bool(
        referencia_binaria is not None or referencia_tres_vias is not None
    )
    if evidencia is None:
        if (
            CHAVE_ESTADO_COTACAO_ENTRADA in features
            and possui_referencia
        ):
            return {
                "valido": False,
                "motivo": "referencia_sem_vig_sem_cotacao_congelada",
            }
        # Compatibilidade estrita com sinais anteriores ao marcador novo.
        return {"valido": True, "motivo": None}

    dados_evidencia = evidencia if isinstance(evidencia, dict) else {}
    candidato_evidencia = {
        "mercado": dados_evidencia.get("mercado"),
        "linha": (
            dados_evidencia.get("selecao")
            if dados_evidencia.get("tipo") == "tres_vias"
            else dados_evidencia.get("linha")
        ),
        "odd": odd,
        "fonte_odds": features.get("fonte_odds"),
        "bookmaker_odds": features.get("bookmaker_odds"),
        "features": features,
    }
    congelada = _cotacao_entrada_congelada(candidato_evidencia)
    if congelada is False or congelada is None:
        return {
            "valido": False,
            "motivo": "cotacao_entrada_valor_invalida",
        }
    if congelada["tipo"] == "binaria":
        if (
            referencia_binaria is None
            or not math.isclose(
                referencia_binaria, congelada["under"], abs_tol=1e-9
            )
            or referencia_tres_vias is not None
        ):
            return {
                "valido": False,
                "motivo": "referencia_sem_vig_diverge_cotacao_entrada",
            }
        return {"valido": True, "motivo": None}

    if referencia_binaria is not None or referencia_tres_vias is None:
        return {
            "valido": False,
            "motivo": "referencia_sem_vig_diverge_cotacao_entrada",
        }
    if (
        referencia_tres_vias["selecao"] != congelada["selecao"]
        or any(
            not math.isclose(
                referencia_tres_vias["odds"][chave],
                congelada["odds"][chave],
                abs_tol=1e-9,
            )
            for chave in ("casa", "visitante", "sem_gol")
        )
    ):
        return {
            "valido": False,
            "motivo": "referencia_sem_vig_diverge_cotacao_entrada",
        }
    return {"valido": True, "motivo": None}


def validar_rastro_valor_mercado(
    probabilidade_calibrada,
    odd,
    features,
):
    """Confere se o cálculo persistido é idêntico ao cálculo vigente."""
    features = _features_dict(features)
    persistido = features.get("valor_mercado_conservador")
    referencia = referencia_tres_vias_sincronizada({
        "features": features,
    })
    esperado = avaliar_valor_mercado(
        probabilidade_calibrada,
        odd,
        odd_oposta_sincronizada({"features": features}),
        odds_mercado=(
            referencia["odds"] if referencia else None
        ),
        selecao_mercado=(
            referencia["selecao"] if referencia else None
        ),
    )
    if not isinstance(persistido, dict):
        return {
            "valido": False,
            "motivo": "rastro_valor_mercado_ausente",
            "esperado": esperado,
            "persistido": persistido,
        }
    if persistido != esperado:
        return {
            "valido": False,
            "motivo": "rastro_valor_mercado_divergente",
            "esperado": esperado,
            "persistido": persistido,
        }
    integridade_referencia = _validar_referencia_contra_cotacao_entrada(
        odd, features
    )
    if not integridade_referencia["valido"]:
        return {
            "valido": False,
            "motivo": integridade_referencia["motivo"],
            "esperado": esperado,
            "persistido": persistido,
        }
    return {
        "valido": True,
        "motivo": None,
        "esperado": esperado,
        "persistido": persistido,
    }


def auditar_valor_mercado_sinais(conexao):
    """Detecta entrega oficial incompatível com o gate de valor."""
    linhas = conexao.execute(
        """
        SELECT s.id, s.mercado, s.regra_versao, s.status, s.odd,
               s.probabilidade_calibrada, s.features_json,
               EXISTS (
                   SELECT 1
                   FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal NOT LIKE 'gateway:%'
                     AND e.canal NOT LIKE '%:teste%'
                     AND e.canal NOT LIKE '%:aguardar_odd%'
                     AND e.canal NOT LIKE '%:insuficiente%'
               ) AS entregue_oficial
        FROM sinais s
        WHERE s.probabilidade_calibrada IS NOT NULL
        ORDER BY s.id
        """
    ).fetchall()
    sem_valor = []
    entregues_sem_valor = []
    rastros_ausentes = []
    rastros_divergentes = []
    entregues_rastro_invalido = []
    margens_incoerentes = []
    com_referencia_sem_vig = 0
    por_mercado = {}
    for linha in linhas:
        item = dict(linha)
        mercado = str(item.get("mercado") or "")
        resumo = por_mercado.setdefault(mercado, {
            "calibrados": 0,
            "com_valor": 0,
            "sem_valor": 0,
            "entregues_oficiais_sem_valor": 0,
            "rastros_validos": 0,
            "rastros_ausentes": 0,
            "rastros_divergentes": 0,
            "entregues_oficiais_rastro_invalido": 0,
            "referencias_margem_incoerente": 0,
        })
        resumo["calibrados"] += 1
        try:
            features = json.loads(item.get("features_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        rastro = validar_rastro_valor_mercado(
            item.get("probabilidade_calibrada"), item.get("odd"), features
        )
        avaliacao = rastro["esperado"]
        if rastro["valido"]:
            resumo["rastros_validos"] += 1
        else:
            detalhe_rastro = {
                "sinal_id": int(item["id"]),
                "mercado": mercado,
                "regra_versao": item.get("regra_versao"),
                "status": item.get("status"),
                "motivo": rastro["motivo"],
                "entregue_oficial": bool(item.get("entregue_oficial")),
            }
            if rastro["motivo"] == "rastro_valor_mercado_ausente":
                resumo["rastros_ausentes"] += 1
                rastros_ausentes.append(detalhe_rastro)
            else:
                resumo["rastros_divergentes"] += 1
                rastros_divergentes.append(detalhe_rastro)
            if detalhe_rastro["entregue_oficial"]:
                resumo["entregues_oficiais_rastro_invalido"] += 1
                entregues_rastro_invalido.append(detalhe_rastro)
        if avaliacao.get("referencia_sem_vig_disponivel"):
            com_referencia_sem_vig += 1
        if avaliacao.get("margem_bookmaker_plausivel") is False:
            resumo["referencias_margem_incoerente"] += 1
            margens_incoerentes.append({
                "sinal_id": int(item["id"]),
                "mercado": mercado,
                "regra_versao": item.get("regra_versao"),
                "status": item.get("status"),
                "margem_bookmaker": avaliacao.get("margem_bookmaker"),
                "entregue_oficial": bool(item.get("entregue_oficial")),
            })
        if avaliacao["aprovado"]:
            resumo["com_valor"] += 1
            continue
        resumo["sem_valor"] += 1
        detalhe = {
            "sinal_id": int(item["id"]),
            "mercado": mercado,
            "regra_versao": item.get("regra_versao"),
            "status": item.get("status"),
            "motivo": avaliacao.get("motivo"),
            "valor_esperado_conservador": avaliacao.get(
                "valor_esperado_conservador"
            ),
            "entregue_oficial": bool(item.get("entregue_oficial")),
        }
        sem_valor.append(detalhe)
        if detalhe["entregue_oficial"]:
            resumo["entregues_oficiais_sem_valor"] += 1
            entregues_sem_valor.append(detalhe)
    return {
        "versao": VERSAO,
        "sinais_calibrados": len(linhas),
        "com_valor_conservador": len(linhas) - len(sem_valor),
        "sem_valor_conservador": len(sem_valor),
        "entregues_oficiais_sem_valor": len(entregues_sem_valor),
        "rastros_validos": len(linhas) - len(rastros_ausentes)
        - len(rastros_divergentes),
        "rastros_ausentes": len(rastros_ausentes),
        "rastros_divergentes": len(rastros_divergentes),
        "entregues_oficiais_rastro_invalido": len(
            entregues_rastro_invalido
        ),
        "com_referencia_sem_vig": com_referencia_sem_vig,
        "sem_referencia_sem_vig": len(linhas) - com_referencia_sem_vig,
        "referencias_margem_incoerente": len(margens_incoerentes),
        "por_mercado": por_mercado,
        "detalhes_sem_valor": sem_valor[:50],
        "detalhes_margem_incoerente": margens_incoerentes[:50],
        "detalhes_rastro_invalido": (
            rastros_ausentes + rastros_divergentes
        )[:50],
        "saudavel": not entregues_sem_valor
        and not entregues_rastro_invalido,
    }
