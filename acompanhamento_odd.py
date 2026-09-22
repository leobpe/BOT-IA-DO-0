"""Avisa quando uma leitura forte ainda está abaixo da odd operacional.

O acompanhamento não é sinal, não entra no backtest e nunca contorna os
gates de conversão, tendência do PackBall ou integridade das fontes.
"""

from __future__ import annotations

import copy
import math
import os
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

from backtest import _anulado, _encerrado, _intervalo, liquidar_over_asiatico
from configuracao import obter_limites_risco
from origem_mercado import (
    VERSAO_ORIGEM_MERCADO as VERSAO_ORIGEM_MERCADO_RAPIDA,
    normalizar_origem_mercado,
)


VERSAO = "acompanhamento-odd-baixa-gols-v1"
VERSAO_MATERIALIZACAO_RAPIDA = "acompanhamento-odd-api-rapido-v1"
VERSAO_EVIDENCIA_OFERTA_RAPIDA_V2 = "oferta-monitorada-odd-v2"
VERSAO_EVIDENCIA_OFERTA_RAPIDA_V3 = "oferta-monitorada-odd-v3"
VERSAO_EVIDENCIA_OFERTA_RAPIDA = "oferta-monitorada-odd-v4"
VERSAO_IDENTIDADE_EVENTO_RAPIDA = "identidade-evento-odd-v1"
FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS = 30.0
TOLERANCIA_RELOGIO_ODD_SEGUNDOS = 5.0
MERCADOS = frozenset({"gol_ht", "gol_ft", "proximo_gol"})
BLOQUEIOS_SOMENTE_ODD = frozenset({
    "odd_fora_da_faixa_operacional",
    "fora_da_faixa_operacional_global",
    "odd_proximo_gol_fora_144_199",
    "fora_da_faixa_proximo_gol_odd_min_166",
})


def _numero(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _normalizar_nome_evento(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    texto = re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()
    descartadas = {"fc", "cf", "sc", "ac", "club", "de", "da", "do", "the"}
    return " ".join(
        parte for parte in texto.split() if parte not in descartadas
    )


def _similaridade_nome_evento(valor_a, valor_b):
    a = _normalizar_nome_evento(valor_a)
    b = _normalizar_nome_evento(valor_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sequencia = SequenceMatcher(None, a, b).ratio()
    tokens_a, tokens_b = set(a.split()), set(b.split())
    jaccard = len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)
    return max(sequencia, jaccard)


def mercados_acompanhamento_odd_autorizados(env=None):
    """Retorna a carteira operacional explicitamente autorizada.

    A lista permite promover a vantagem comprovada de um mercado sem
    extrapolar o resultado para mercados ainda sem amostra suficiente.
    """
    env = os.environ if env is None else env
    bruto = str(
        env.get(
            "AVISO_AGUARDAR_ODD_MERCADOS",
            ",".join(sorted(MERCADOS)),
        )
        or ""
    )
    return frozenset(
        item.strip().lower()
        for item in bruto.split(",")
        if item.strip().lower() in MERCADOS
    )


def mercado_acompanhamento_odd_autorizado(mercado, env=None):
    return str(mercado or "").strip().lower() in (
        mercados_acompanhamento_odd_autorizados(env)
    )


def _instante(valor):
    if isinstance(valor, datetime):
        return valor
    texto = str(valor or "").strip()
    if not texto:
        return None
    if texto.endswith("Z"):
        texto = f"{texto[:-1]}+00:00"
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _idade_segundos(valor, agora):
    instante = _instante(valor)
    if instante is None:
        return None
    if instante.tzinfo is not None:
        instante = instante.astimezone().replace(tzinfo=None)
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    idade = (agora - instante).total_seconds()
    return idade if idade >= -1.0 else None


def validar_proveniencia_temporal_oferta(
    oferta,
    *,
    agora,
    frescor_maximo_segundos=FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS,
):
    """Confirma que idade declarada e relógio da fonte contam a mesma história."""
    if not isinstance(oferta, dict) or not isinstance(oferta.get("cache"), bool):
        return {
            "valida": False,
            "motivo": "odd_proveniencia_temporal_indeterminada",
        }
    idade_declarada = _numero(oferta.get("idade_segundos"))
    if idade_declarada is None or idade_declarada < 0:
        return {"valida": False, "motivo": "odd_sem_frescor_comprovado"}
    limite = max(float(frescor_maximo_segundos), 1.0)
    idade_instante = _idade_segundos(oferta.get("coletado_em"), agora)
    if idade_instante is None:
        return {
            "valida": False,
            "motivo": "odd_proveniencia_temporal_indeterminada",
        }
    idade_instante = max(idade_instante, 0.0)
    if idade_declarada > limite or idade_instante > limite:
        return {"valida": False, "motivo": "odd_sem_frescor_comprovado"}
    divergencia = abs(idade_instante - idade_declarada)
    if divergencia > TOLERANCIA_RELOGIO_ODD_SEGUNDOS:
        return {"valida": False, "motivo": "odd_relogio_inconsistente"}
    return {
        "valida": True,
        "motivo": "proveniencia_temporal_confirmada",
        "idade_declarada_segundos": round(idade_declarada, 3),
        "idade_instante_segundos": round(idade_instante, 3),
        "divergencia_relogio_segundos": round(divergencia, 3),
        "frescor_maximo_segundos": limite,
    }


def validar_origem_mercado_oferta(oferta, mercado, linha=None):
    """Prova que todos os lados vieram do mesmo grupo da casa de apostas."""
    if not isinstance(oferta, dict):
        return {"valida": False, "motivo": "origem_mercado_ausente"}
    origem_bruta = oferta.get("origem_mercado")
    if not isinstance(origem_bruta, dict):
        return {"valida": False, "motivo": "origem_mercado_ausente"}
    origem = normalizar_origem_mercado(origem_bruta)
    if origem is None:
        return {"valida": False, "motivo": "origem_mercado_invalida"}
    fonte = str(oferta.get("fonte") or "").strip().casefold()
    bookmaker = str(oferta.get("bookmaker") or "").strip().casefold()
    lados = origem.get("lados")
    mercado = str(mercado or "").strip().casefold()
    esperados = (
        {"casa", "visitante", "sem_gol"}
        if mercado == "proximo_gol" else {"over", "under"}
    )
    if (
        not fonte or fonte != origem["fonte"]
        or not bookmaker or bookmaker != origem["bookmaker"]
        or set(lados) != esperados
    ):
        return {"valida": False, "motivo": "origem_mercado_invalida"}
    linha_origem = origem.get("linha")
    if mercado == "proximo_gol":
        if not str(linha_origem or "").strip():
            return {
                "valida": False,
                "motivo": "origem_mercado_linha_divergente",
            }
    else:
        alvo = _numero(linha)
        observada = _numero(linha_origem)
        if (
            alvo is None
            or observada is None
            or not math.isclose(alvo, observada, abs_tol=0.000001)
        ):
            return {
                "valida": False,
                "motivo": "origem_mercado_linha_divergente",
            }
        linha_origem = observada
    return {
        "valida": True,
        "motivo": "origem_mercado_confirmada",
        "origem_mercado": {
            **origem,
            "linha": linha_origem,
            "lados": sorted(esperados),
        },
    }


def validar_contrato_mercado_oferta(
    oferta, mercado, linha=None, *, exigir_origem=False,
):
    """Exige a fotografia completa usada para calcular a margem sem vig.

    Uma odd isolada não permite distinguir vantagem real de simples margem
    da casa. Totais precisam do par Over/Under e próximo gol precisa das três
    saídas observadas na mesma coleta.
    """
    if not isinstance(oferta, dict):
        return {"valido": False, "motivo": "contrato_mercado_incompleto"}
    odd = _numero(oferta.get("odd"))
    if odd is None or odd <= 1.0:
        return {"valido": False, "motivo": "odd_invalida"}
    mercado = str(mercado or "").strip().casefold()
    if mercado == "proximo_gol":
        selecao = str(
            oferta.get("selecao_mercado")
            or linha
            or oferta.get("linha")
            or ""
        ).strip().casefold()
        odds = oferta.get("odds_mercado_sincronizadas")
        if selecao not in {"casa", "visitante", "sem_gol"} or not isinstance(
            odds, dict
        ):
            return {
                "valido": False,
                "motivo": "contrato_mercado_incompleto",
            }
        normalizadas = {
            chave: _numero(odds.get(chave))
            for chave in ("casa", "visitante", "sem_gol")
        }
        if (
            any(valor is None or valor <= 1.0 for valor in normalizadas.values())
            or not math.isclose(
                normalizadas[selecao], odd, rel_tol=0.0, abs_tol=0.000001
            )
        ):
            return {
                "valido": False,
                "motivo": "contrato_mercado_incompleto",
            }
        origem = None
        if exigir_origem:
            origem = validar_origem_mercado_oferta(
                oferta, mercado, linha
            )
            if origem["valida"] is not True:
                return {"valido": False, "motivo": origem["motivo"]}
        return {
            "valido": True,
            "motivo": "contrato_mercado_completo",
            "tipo": "tres_vias",
            "odd": odd,
            "selecao_mercado": selecao,
            "odds_mercado_sincronizadas": normalizadas,
            **(
                {"origem_mercado": origem["origem_mercado"]}
                if origem is not None else {}
            ),
        }

    if mercado not in {
        "gol_ht", "gol_ft", "escanteios_ft_asiatico",
    }:
        return {"valido": False, "motivo": "mercado_nao_suportado"}
    odd_oposta = _numero(oferta.get("odd_oposta"))
    if odd_oposta is None or odd_oposta <= 1.0:
        return {"valido": False, "motivo": "contrato_mercado_incompleto"}
    origem = None
    if exigir_origem:
        origem = validar_origem_mercado_oferta(oferta, mercado, linha)
        if origem["valida"] is not True:
            return {"valido": False, "motivo": origem["motivo"]}
    return {
        "valido": True,
        "motivo": "contrato_mercado_completo",
        "tipo": "binario",
        "odd": odd,
        "odd_oposta": odd_oposta,
        **(
            {"origem_mercado": origem["origem_mercado"]}
            if origem is not None else {}
        ),
    }


def validar_identidade_evento_oferta(oferta, jogo_atual=None):
    """Vincula a cotação ao evento externo já conferido por nomes e placar."""
    identidade = (
        oferta.get("identidade_evento")
        if isinstance(oferta, dict) else None
    )
    if not isinstance(identidade, dict):
        return {"valida": False, "motivo": "identidade_evento_ausente"}
    fonte = str((oferta or {}).get("fonte") or "").strip().casefold()
    fonte_identidade = str(
        identidade.get("fonte") or ""
    ).strip().casefold()
    evento_id = str(identidade.get("evento_externo_id") or "").strip()
    orientacao = str(identidade.get("orientacao") or "").strip().casefold()
    if (
        identidade.get("schema") != VERSAO_IDENTIDADE_EVENTO_RAPIDA
        or identidade.get("confirmada") is not True
        or not fonte
        or fonte_identidade != fonte
        or not evento_id
        or orientacao not in {"direta", "invertida"}
        or not str(identidade.get("mandante_normalizado") or "").strip()
        or not str(identidade.get("visitante_normalizado") or "").strip()
    ):
        return {"valida": False, "motivo": "identidade_evento_invalida"}
    similaridade = identidade.get("similaridade")
    if similaridade is not None:
        similaridade = _numero(similaridade)
        if similaridade is None or not 0.84 <= similaridade <= 1.0:
            return {
                "valida": False,
                "motivo": "pareamento_evento_insuficiente",
            }
    mandante_identidade = str(
        identidade.get("mandante_normalizado") or ""
    ).strip()
    visitante_identidade = str(
        identidade.get("visitante_normalizado") or ""
    ).strip()
    mandante_atual = str((jogo_atual or {}).get("mandante") or "").strip()
    visitante_atual = str(
        (jogo_atual or {}).get("visitante") or ""
    ).strip()
    similaridade_equipes = None
    if mandante_atual or visitante_atual:
        if not mandante_atual or not visitante_atual:
            return {
                "valida": False,
                "motivo": "equipes_evento_atual_incompletas",
            }
        nota_mandante = _similaridade_nome_evento(
            mandante_identidade, mandante_atual
        )
        nota_visitante = _similaridade_nome_evento(
            visitante_identidade, visitante_atual
        )
        media_equipes = (nota_mandante + nota_visitante) / 2.0
        if min(nota_mandante, nota_visitante) < 0.76 or media_equipes < 0.84:
            return {
                "valida": False,
                "motivo": "evento_odd_equipes_divergentes",
            }
        similaridade_equipes = {
            "mandante": round(nota_mandante, 4),
            "visitante": round(nota_visitante, 4),
            "media": round(media_equipes, 4),
        }
    placar_identidade = _placar_par(
        identidade.get("placar_normalizado")
    )
    placar_atual = _placar_par((jogo_atual or {}).get("placar"))
    if placar_identidade is None or (
        placar_atual is not None and placar_identidade != placar_atual
    ):
        return {"valida": False, "motivo": "evento_odd_placar_divergente"}
    return {
        "valida": True,
        "motivo": "identidade_evento_confirmada",
        "identidade_evento": {
            **identidade,
            "fonte": fonte_identidade,
            "evento_externo_id": evento_id,
            "orientacao": orientacao,
            "similaridade": similaridade,
            "similaridade_equipes_confirmada": similaridade_equipes,
            "placar_normalizado": (
                f"{placar_identidade[0]}-{placar_identidade[1]}"
            ),
        },
    }


def extrair_odd_exata_acompanhamento(odds, mercado, linha):
    """Localiza somente a mesma linha que originou o aviso.

    A fila rapida nunca troca 2.5 por 3.5 nem escolhe uma linha apenas por
    ela ter uma cotacao parecida. Isso evita transformar a observacao em uma
    aposta diferente durante a espera.
    """
    if mercado == "proximo_gol":
        selecao = str(linha or "").strip().casefold()
        if selecao not in {"casa", "visitante", "sem_gol"}:
            return None
        for item in (odds or {}).get("ao_vivo") or []:
            if (
                item.get("categoria") != "gols"
                or item.get("escopo") != "proximo"
            ):
                continue
            selecoes = item.get("selecoes") or {}
            sincronizadas = {
                chave: _numero(selecoes.get(chave))
                for chave in ("casa", "visitante", "sem_gol")
            }
            if any(
                valor is None or valor <= 1.0
                for valor in sincronizadas.values()
            ):
                continue
            odd = sincronizadas[selecao]
            return {
                "odd": odd,
                "linha": selecao,
                "selecao_mercado": selecao,
                "odds_mercado_sincronizadas": sincronizadas,
                "mercado_odds_sincronizado": True,
                "identidade_evento": item.get("identidade_evento"),
                "origem_mercado": item.get("origem_mercado"),
                "fonte": item.get("fonte"),
                "bookmaker": item.get("bookmaker"),
                "idade_segundos": item.get("idade_segundos"),
                "coletado_em": item.get("coletado_em"),
                "recebido_em": item.get("recebido_em"),
                "cache": item.get("cache"),
            }
        return None

    grupos = []
    for item in (odds or {}).get("ao_vivo") or []:
        if mercado == "escanteios_ft_asiatico":
            if (
                item.get("categoria") != "escanteios"
                or item.get("escopo") != "total"
                or item.get("tipo_mercado") != "asiatico"
            ):
                continue
            grupos.append((item.get("ofertas") or [], item))
        elif item.get("categoria") != "gols":
            continue
        elif mercado == "gol_ht":
            grupos.append((item.get("ofertas_ht") or [], item))
        elif mercado == "gol_ft":
            grupos.append((item.get("ofertas") or [], item))
    linha_alvo = _numero(linha)
    if linha_alvo is None:
        return None
    for ofertas, item in grupos:
        for oferta in ofertas:
            linha_oferta = _numero((oferta or {}).get("linha"))
            odd = _numero((oferta or {}).get("over"))
            odd_oposta = _numero((oferta or {}).get("under"))
            if (
                linha_oferta is None
                or odd is None
                or odd <= 1.0
                or odd_oposta is None
                or odd_oposta <= 1.0
                or abs(linha_oferta - linha_alvo) > 0.000001
            ):
                continue
            return {
                "odd": odd,
                "odd_oposta": odd_oposta,
                "odd_par_sincronizado": True,
                "identidade_evento": (
                    oferta.get("identidade_evento")
                    or item.get("identidade_evento")
                ),
                "origem_mercado": (
                    oferta.get("origem_mercado")
                    or item.get("origem_mercado")
                ),
                "linha": linha_oferta,
                "fonte": oferta.get("fonte") or item.get("fonte"),
                "bookmaker": (
                    oferta.get("bookmaker") or item.get("bookmaker")
                ),
                "idade_segundos": (
                    oferta.get("idade_segundos")
                    if oferta.get("idade_segundos") is not None
                    else item.get("idade_segundos")
                ),
                "coletado_em": (
                    oferta.get("coletado_em") or item.get("coletado_em")
                ),
                "recebido_em": (
                    oferta.get("recebido_em") or item.get("recebido_em")
                ),
                "cache": (
                    oferta.get("cache")
                    if isinstance(oferta.get("cache"), bool)
                    else item.get("cache")
                ),
            }
    return None


def avaliar_rechecagem_odd_api(
    acompanhamento,
    *,
    mercado,
    linha,
    placar_origem,
    snapshot_em,
    jogo_atual,
    odds,
    agora=None,
    ttl_tecnico_segundos=600.0,
    frescor_odd_maximo_segundos=FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS,
):
    """Valida a conversao rapida sem nova navegacao no PackBall."""
    agora = agora or datetime.now()
    if (
        acompanhamento.get("elegivel_aviso") is not True
        or acompanhamento.get("conversao_confirmada") is not True
        or acompanhamento.get("tendencia_packball_confirmada") is not True
    ):
        return {"aprovada": False, "motivo": "criterios_tecnicos_nao_confirmados"}
    idade_tecnica = _idade_segundos(snapshot_em, agora)
    if idade_tecnica is None:
        return {"aprovada": False, "motivo": "instante_tecnico_indeterminado"}
    if idade_tecnica > max(float(ttl_tecnico_segundos), 1.0):
        return {"aprovada": False, "motivo": "leitura_tecnica_expirada"}
    if _placar_par(placar_origem) != _placar_par(jogo_atual.get("placar")):
        return {"aprovada": False, "motivo": "placar_alterado"}
    status_codigo = str(jogo_atual.get("status_codigo") or "").upper()
    if status_codigo in {
        "FT", "AET", "PEN", "PST", "CANC", "ABD", "SUSP", "INT", "NS",
    }:
        return {"aprovada": False, "motivo": "partida_nao_operacional"}
    if mercado == "gol_ht" and status_codigo in {"HT", "2H", "ET", "BT", "P"}:
        return {"aprovada": False, "motivo": "primeiro_tempo_encerrado"}
    minuto = _numero(jogo_atual.get("minuto"))
    limites_minuto = {"gol_ht": 45.0, "gol_ft": 82.0, "proximo_gol": 75.0}
    if minuto is None:
        return {"aprovada": False, "motivo": "minuto_atual_indeterminado"}
    if minuto > limites_minuto.get(mercado, 82.0):
        return {"aprovada": False, "motivo": "minuto_maximo_excedido"}
    oferta = extrair_odd_exata_acompanhamento(odds, mercado, linha)
    if oferta is None:
        return {"aprovada": False, "motivo": "linha_exata_indisponivel"}
    contrato_mercado = validar_contrato_mercado_oferta(
        oferta, mercado, linha, exigir_origem=True
    )
    if contrato_mercado["valido"] is not True:
        return {
            "aprovada": False,
            "motivo": contrato_mercado["motivo"],
        }
    identidade_evento = validar_identidade_evento_oferta(
        oferta, jogo_atual
    )
    if identidade_evento["valida"] is not True:
        return {
            "aprovada": False,
            "motivo": identidade_evento["motivo"],
        }
    proveniencia_temporal = validar_proveniencia_temporal_oferta(
        oferta,
        agora=agora,
        frescor_maximo_segundos=frescor_odd_maximo_segundos,
    )
    if proveniencia_temporal["valida"] is not True:
        return {
            "aprovada": False,
            "motivo": proveniencia_temporal["motivo"],
        }
    odd_alvo = _numero(acompanhamento.get("odd_alvo"))
    odd_maxima = _numero(acompanhamento.get("odd_maxima_operacional"))
    if odd_alvo is None or odd_maxima is None:
        return {"aprovada": False, "motivo": "faixa_operacional_indeterminada"}
    if oferta["odd"] < odd_alvo:
        return {
            "aprovada": False,
            "motivo": "odd_ainda_abaixo_do_alvo",
            "oferta": oferta,
            "identidade_evento": identidade_evento,
            "proveniencia_temporal": proveniencia_temporal,
        }
    if oferta["odd"] > odd_maxima:
        return {
            "aprovada": False,
            "motivo": "odd_acima_do_limite_operacional",
            "oferta": oferta,
            "identidade_evento": identidade_evento,
            "proveniencia_temporal": proveniencia_temporal,
        }
    return {
        "aprovada": True,
        "motivo": "odd_alvo_atingida_com_estado_confirmado",
        "oferta": oferta,
        "contrato_mercado": contrato_mercado,
        "identidade_evento": identidade_evento,
        "proveniencia_temporal": proveniencia_temporal,
        "idade_tecnica_segundos": round(max(idade_tecnica, 0.0), 3),
        "minuto": minuto,
    }


def acompanhamento_odd_ativo():
    return os.getenv("AVISO_AGUARDAR_ODD_ATIVO", "0") == "1"


def _parametro_decimal(nome, padrao):
    valor = _numero(os.getenv(nome, str(padrao)))
    return valor if valor is not None else float(padrao)


def preparar_acompanhamento_odd(candidatos):
    """Libera candidatos de odd baixa apenas para os gates históricos.

    O status temporário ``simulacao`` permite que as proteções já usadas nos
    sinais normais avaliem o candidato. ``finalizar_acompanhamento_odd`` o
    devolve obrigatoriamente a ``rejeitado`` antes da persistência.
    """
    if not acompanhamento_odd_ativo():
        return 0
    limites = obter_limites_risco()
    piso = max(
        1.01,
        _parametro_decimal("AVISO_AGUARDAR_ODD_PISO", 1.10),
    )
    alvo_configurado = _parametro_decimal(
        "AVISO_AGUARDAR_ODD_ALVO", limites.odd_minima
    )
    alvo = max(float(limites.odd_minima), alvo_configurado)
    qualidade_minima = _parametro_decimal(
        "AVISO_AGUARDAR_ODD_QUALIDADE_MINIMA", 80.0
    )
    nota_minima = _parametro_decimal(
        "AVISO_AGUARDAR_ODD_NOTA_MINIMA", 70.0
    )
    preparados = 0
    for candidato in candidatos or []:
        if not mercado_acompanhamento_odd_autorizado(
            candidato.get("mercado")
        ):
            continue
        if candidato.get("status") != "rejeitado":
            continue
        metodo = (candidato.get("features") or {}).get("acompanhamento_metodo_gols") or {}
        alvo_candidato = max(alvo, _numero(metodo.get("odd_alvo")) or alvo)
        odd = _numero(candidato.get("odd"))
        nota = _numero(candidato.get("pontuacao_tecnica")) or 0.0
        qualidade = _numero(candidato.get("qualidade_dados")) or 0.0
        bloqueios = set(candidato.get("bloqueios") or [])
        if not (
            odd is not None
            and piso <= odd < alvo_candidato <= float(limites.odd_maxima)
            and nota >= nota_minima
            and qualidade >= qualidade_minima
            and bloqueios
            and bloqueios <= BLOQUEIOS_SOMENTE_ODD
        ):
            continue
        features = copy.deepcopy(candidato.get("features") or {})
        features["acompanhamento_odd"] = {
            "versao": VERSAO,
            "odd_atual": odd,
            "odd_alvo": alvo_candidato,
            "odd_maxima_operacional": float(limites.odd_maxima),
            "piso_observacao": piso,
            "nota_minima": nota_minima,
            "qualidade_minima": qualidade_minima,
            "elegivel_pre_protecoes": True,
            "elegivel_aviso": False,
            "aplicacao_sinal": False,
            "contabiliza_resultado": False,
            "rollback": "AVISO_AGUARDAR_ODD_ATIVO=0",
        }
        candidato["features"] = features
        candidato["status"] = "simulacao"
        motivos = list(candidato.get("motivos") or [])
        if "monitoramento_odd_abaixo_da_faixa" not in motivos:
            motivos.append("monitoramento_odd_abaixo_da_faixa")
        candidato["motivos"] = motivos
        preparados += 1
    return preparados


def finalizar_acompanhamento_odd(candidatos, fontes_saudaveis):
    resumo = {"avaliados": 0, "elegiveis": 0, "bloqueados": 0}
    for candidato in candidatos or []:
        features = copy.deepcopy(candidato.get("features") or {})
        acompanhamento = features.get("acompanhamento_odd")
        if not isinstance(acompanhamento, dict):
            continue
        resumo["avaliados"] += 1
        bloqueios_extras = sorted(
            set(candidato.get("bloqueios") or [])
            - BLOQUEIOS_SOMENTE_ODD
        )
        conversao = features.get("protecao_conversao_gols") or {}
        tendencia = features.get("protecao_tendencias_packball") or {}
        elegivel = bool(
            fontes_saudaveis
            and not bloqueios_extras
            and conversao.get("aprovada") is True
            and tendencia.get("aprovada") is True
        )
        acompanhamento.update({
            "elegivel_aviso": elegivel,
            "fontes_saudaveis": bool(fontes_saudaveis),
            "conversao_confirmada": conversao.get("aprovada") is True,
            "tendencia_packball_confirmada": tendencia.get("aprovada") is True,
            "bloqueios_extras": bloqueios_extras,
        })
        features["acompanhamento_odd"] = acompanhamento
        candidato["features"] = features
        # Nunca permitir que um aviso vire sinal ou contamine Green/Red.
        candidato["status"] = "rejeitado"
        if elegivel:
            resumo["elegiveis"] += 1
        else:
            resumo["bloqueados"] += 1
    return resumo


def _placar_par(valor):
    numeros = re.findall(r"\d+", str(valor or ""))
    if len(numeros) < 2:
        return None
    return [int(numeros[0]), int(numeros[1])]


def avaliar_resultado_acompanhamento_odd(origem, historico):
    """Liquida apenas a observacao, sem gravar resultado oficial.

    O retorno identifica o primeiro snapshot confiavel que torna o desfecho
    irreversivel. A persistencia continua separada de ``resultados_sinais``.
    """
    mercado = str(origem.get("mercado") or "")
    placar_inicial = _placar_par(origem.get("placar_inicial"))
    if placar_inicial is None or mercado not in MERCADOS:
        return None
    try:
        linha = (
            float(origem["linha"])
            if origem.get("linha") is not None and mercado != "proximo_gol"
            else origem.get("linha")
        )
        odd = float(origem.get("odd") or 1.0)
    except (TypeError, ValueError):
        return None

    for leitura in historico or []:
        if leitura.get("qualidade_apta") is not True:
            continue
        placar_atual = _placar_par(leitura.get("placar"))
        if placar_atual is None:
            continue
        status = leitura.get("status")
        anulado = _anulado(status)
        encerrado = _encerrado(status) or anulado
        intervalo = _intervalo(status)
        resultado = None

        if anulado:
            resultado = "void"
        elif mercado in {"gol_ft", "gol_ht"}:
            if mercado == "gol_ht" and not intervalo:
                texto = str(status or "")
                minutos = re.findall(r"\d+", texto)
                if not minutos or int(minutos[0]) > 45:
                    continue
            total_atual = sum(placar_atual)
            if linha is None:
                if total_atual > sum(placar_inicial):
                    resultado = "green"
            else:
                parcial, _ = liquidar_over_asiatico(total_atual, linha, odd)
                if parcial in {"green", "half_green"}:
                    resultado = parcial
            periodo_encerrado = encerrado or (
                mercado == "gol_ht" and intervalo
            )
            if resultado is None and periodo_encerrado:
                if linha is None:
                    resultado = "red"
                else:
                    resultado, _ = liquidar_over_asiatico(
                        total_atual, linha, odd
                    )
        else:  # proximo_gol
            deltas = [
                placar_atual[indice] - placar_inicial[indice]
                for indice in range(2)
            ]
            if any(delta < 0 for delta in deltas):
                continue
            total_delta = sum(deltas)
            if total_delta == 1:
                lado = "casa" if deltas[0] == 1 else "visitante"
                resultado = "green" if lado == linha else "red"
            elif total_delta > 1:
                # Sem a ordem dos gols, nao existe prova do primeiro lado.
                continue
            elif encerrado:
                resultado = "red"

        if resultado is not None:
            return {
                "resultado": resultado,
                "snapshot_id": leitura.get("snapshot_id"),
                "coletado_em": leitura.get("coletado_em"),
                "status": status,
                "placar": leitura.get("placar"),
            }
    return None
