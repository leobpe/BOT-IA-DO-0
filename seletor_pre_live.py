"""Seleção pré-live auditável de jogos e combinações de baixa complexidade.

O módulo só aceita odds realmente oferecidas por uma casa. Combinações do
mesmo jogo precisam existir como mercado pronto no provedor; nunca são
fabricadas multiplicando pernas correlacionadas. Até três pernas de partidas
diferentes podem formar uma múltipla, desde que pertençam à mesma casa.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from itertools import combinations
from statistics import median


PERFIL_SELECAO = os.getenv("PRELIVE_PERFIL_SELECAO", "v11").strip().lower()
if PERFIL_SELECAO not in {"v11", "dia30_v7"}:
    raise ValueError("PRELIVE_PERFIL_SELECAO deve ser v11 ou dia30_v7")
RETORNO_DIA30 = PERFIL_SELECAO == "dia30_v7"
VERSAO = (
    "seletor-pre-live-retorno-dia30-odd150-v12"
    if RETORNO_DIA30 else "seletor-pre-live-profissional-revalidacao-v11"
)
ODD_MINIMA = 1.50
ODD_MAXIMA_PREFERENCIAL = 1.60
ODD_MAXIMA = 1.70
ODD_MINIMA_PERNA = 1.10
ODD_MAXIMA_PERNA = 1.40
EDGE_MINIMO = 0.03
EDGE_CONSERVADOR_MINIMO = 0.02
EDGE_MINIMO_BILHETE = 0.04
EDGE_CONSERVADOR_MINIMO_BILHETE = 0.03
PROBABILIDADE_MINIMA_PERNA = 0.72
QUALIDADE_MINIMA = 70.0
QUALIDADE_CONFIRMADA_MINIMA = 82.0
QUALIDADE_OFICIAL_V11_MINIMA = 85.0
EDGE_CONSERVADOR_OFICIAL_V11_MINIMO = 0.04
QUALIDADE_MINIMA_FAIXA_ESTENDIDA = 85.0
EDGE_MINIMO_FAIXA_ESTENDIDA = 0.06
MAXIMO_PERNAS = 3
PROBABILIDADE_MINIMA_PERNA_TRIPLA = 0.80
QUALIDADE_MINIMA_TRIPLA = 75.0
EDGE_MINIMO_BILHETE_TRIPLA = 0.05
MAXIMO_PERNAS_POR_CASA_TRIPLA = 36
CONSENSO_MINIMO_CASAS = 2
DIVERGENCIA_MAXIMA_MODELO_CONSENSO = 0.12
DESCONTO_EDGE_SEM_CONSENSO = 0.85
FAIXA_RELATIVA_SCORE_MELHORES = 0.82
MERCADOS_TIME_ATIVOS = os.getenv(
    "PRELIVE_MERCADOS_TIME_ATIVOS", "1"
).strip().lower() in {"1", "true", "sim", "yes", "on"}
MULTIPLAS_TRES_PERNAS_ATIVAS = os.getenv(
    "PRELIVE_MULTIPLAS_TRES_PERNAS_ATIVAS", "1"
).strip().lower() in {"1", "true", "sim", "yes", "on"}
PESO_RECENTE = 0.70
PESO_TEMPORADA = 0.30
PESO_MANDO_RECENTE_MAXIMO = 0.65
AMOSTRA_MANDO_CONFIAVEL = 6
AJUSTE_PREVISAO_MAXIMO = 0.06
AJUSTE_CLASSIFICACAO_MAXIMO = 0.05
MAXIMO_JOGOS_PADRAO = 60
CHAMADAS_ESTIMADAS_POR_JOGO = 12
RESERVA_AO_VIVO_PADRAO = 2500


def _linhagem():
    parametros = {
        "versao": VERSAO,
        "odd": {
            "minima": ODD_MINIMA,
            "maxima_preferencial": ODD_MAXIMA_PREFERENCIAL,
            "maxima_estendida": ODD_MAXIMA,
        },
        "odd_perna": [ODD_MINIMA_PERNA, ODD_MAXIMA_PERNA],
        "edge": {
            "modelo": [EDGE_MINIMO, EDGE_MINIMO_BILHETE],
            "conservador": [
                EDGE_CONSERVADOR_MINIMO,
                EDGE_CONSERVADOR_MINIMO_BILHETE,
            ],
            "desconto_sem_consenso": DESCONTO_EDGE_SEM_CONSENSO,
        },
        "consenso_casas": {
            "minimo_casas": CONSENSO_MINIMO_CASAS,
            "divergencia_maxima_modelo": DIVERGENCIA_MAXIMA_MODELO_CONSENSO,
            "somente_melhor_preco": True,
            "ranking": "score_valor_conservador",
        },
        "selecao_melhores": {
            "preencher_limite": False,
            "score_minimo_relativo_ao_lider": (
                FAIXA_RELATIVA_SCORE_MELHORES
            ),
        },
        "probabilidade_minima_perna": PROBABILIDADE_MINIMA_PERNA,
        "qualidade": [QUALIDADE_MINIMA, QUALIDADE_CONFIRMADA_MINIMA],
        "politica_oficial_v11": {
            "qualidade_minima": QUALIDADE_OFICIAL_V11_MINIMA,
            "edge_conservador_minimo": (
                EDGE_CONSERVADOR_OFICIAL_V11_MINIMO
            ),
            "multiplas_oficiais_padrao": False,
            "revalidacao_sem_repetir_lista": True,
        },
        "faixa_estendida": {
            "qualidade_minima": QUALIDADE_MINIMA_FAIXA_ESTENDIDA,
            "edge_minimo": EDGE_MINIMO_FAIXA_ESTENDIDA,
        },
        "maximo_pernas": MAXIMO_PERNAS,
        "tripla": {
            "ativa": MULTIPLAS_TRES_PERNAS_ATIVAS,
            "probabilidade_minima_perna": PROBABILIDADE_MINIMA_PERNA_TRIPLA,
            "qualidade_minima_perna": QUALIDADE_MINIMA_TRIPLA,
            "edge_minimo_bilhete": EDGE_MINIMO_BILHETE_TRIPLA,
            "maximo_pernas_por_casa": MAXIMO_PERNAS_POR_CASA_TRIPLA,
        },
        "mercados_time_ativos": MERCADOS_TIME_ATIVOS,
        "dominancia_mercados_time": (
            "time_marca_substitui_multigols_1-N_quando_odd_maior_ou_igual"
        ),
        "variedade_sem_quota": {
            "ativa": True,
            "criterio_selecao": "maior_probabilidade_depois_edge_e_qualidade",
            "cotas_por_mercado": False,
            "mercados": [
                "over", "under", "ambas_marcam", "gols_mais_ambas", "multigols",
                "time_marca", "resultado_protegido", "misto",
            ],
        },
        "pesos": {
            "recente": PESO_RECENTE,
            "temporada": PESO_TEMPORADA,
            "mando_recente_maximo": PESO_MANDO_RECENTE_MAXIMO,
            "amostra_mando_confiavel": AMOSTRA_MANDO_CONFIAVEL,
        },
        "ajustes_maximos": {
            "previsao": AJUSTE_PREVISAO_MAXIMO,
            "classificacao": AJUSTE_CLASSIFICACAO_MAXIMO,
        },
        "universo_candidatos": {
            "maximo_jogos_padrao": MAXIMO_JOGOS_PADRAO,
            "chamadas_estimadas_por_jogo": CHAMADAS_ESTIMADAS_POR_JOGO,
            "reserva_ao_vivo": RESERVA_AO_VIVO_PADRAO,
            "ordenacao": "odd_alvo-pernas-liquidaveis-horario",
        },
    }
    if RETORNO_DIA30:
        parametros.update({
            "perfil_selecao": PERFIL_SELECAO,
            "origem": "seletor-pre-live-variedade-bet365-v7",
            "edge": [EDGE_MINIMO, EDGE_MINIMO_BILHETE],
            "consenso_casas": {"uso": "diagnostico_sem_veto_ou_ranking"},
            "selecao_melhores": {
                "ranking": "probabilidade-faixa_preferencial-edge-qualidade",
                "corte_relativo_score": False,
                "exige_criterios_minimos": True,
            },
            "politica_oficial_v11": {
                "ativa": False, "qualidade_minima": QUALIDADE_CONFIRMADA_MINIMA,
                "exige_escalacoes": True, "multiplas_confirmadas": True,
                "revalidacao_sem_repetir_lista": True,
            },
        })
    bruto = json.dumps(
        parametros, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


LINHAGEM = _linhagem()


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return " ".join(re.sub(r"[^a-z0-9.+/-]+", " ", texto.casefold()).split())


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _fixture_id(item):
    try:
        return int(((item or {}).get("fixture") or {}).get("id"))
    except (TypeError, ValueError):
        return None


def _linha_over_under(valor):
    encontrado = re.search(
        r"\b(over|under)\s+(\d+(?:[.,]\d+)?)\b",
        str(valor or ""),
        re.IGNORECASE,
    )
    if not encontrado:
        return None, None
    return encontrado.group(1).casefold(), float(
        encontrado.group(2).replace(",", ".")
    )


def _linha_sem_devolucao(linha):
    """Aceita apenas meia linha; inteiras/quartos exigem regra de push."""
    numero = _numero(linha)
    if numero is None:
        return False
    return abs((numero % 1.0) - 0.5) < 1e-9


def _selecao_resultado(valor):
    mapa = {
        "home": "mandante",
        "draw": "empate",
        "away": "visitante",
    }
    return mapa.get(_normalizar(valor))


def _selecao_dupla(valor):
    mapa = {
        "home/draw": "mandante_ou_empate",
        "home/away": "sem_empate",
        "draw/away": "visitante_ou_empate",
    }
    return mapa.get(_normalizar(valor))


def _selecao_dupla_em_combinacao(valor):
    texto = _normalizar(valor)
    for trecho, selecao in (
        ("home/draw", "mandante_ou_empate"),
        ("draw/away", "visitante_ou_empate"),
        ("home/away", "sem_empate"),
    ):
        if trecho in texto:
            return selecao
    return None


def _classificar_valor(nome_mercado, valor):
    nome = _normalizar(nome_mercado)
    valor_normalizado = _normalizar(valor)
    if "double chance" in nome and (
        "total goal" in nome or "goals over under" in nome
    ):
        dupla = _selecao_dupla_em_combinacao(valor)
        lado, linha = _linha_over_under(valor)
        if dupla and lado is not None and _linha_sem_devolucao(linha):
            return (
                "chance_dupla_mais_gols",
                f"{dupla}|{lado}_{linha:g}",
                f"chance_dupla_mais_gols:{linha:g}",
            )
    if nome == "match winner":
        selecao = _selecao_resultado(valor)
        if selecao:
            return "resultado", selecao, "resultado"
    if nome == "double chance":
        selecao = _selecao_dupla(valor)
        if selecao:
            return "chance_dupla", selecao, "chance_dupla"
    if nome == "goals over/under":
        lado, linha = _linha_over_under(valor)
        if lado is not None and _linha_sem_devolucao(linha):
            return "total_gols", f"{lado}_{linha:g}", f"total_gols:{linha:g}"
    if nome == "both teams score":
        if valor_normalizado in {"yes", "no"}:
            return (
                "ambas_marcam",
                "sim" if valor_normalizado == "yes" else "nao",
                "ambas_marcam",
            )
    if nome == "result/total goals":
        partes = str(valor or "").split("/", 1)
        if len(partes) == 2:
            resultado = _selecao_resultado(partes[0])
            lado, linha = _linha_over_under(partes[1])
            if (
                resultado and lado is not None
                and _linha_sem_devolucao(linha)
            ):
                return (
                    "resultado_mais_gols",
                    f"{resultado}|{lado}_{linha:g}",
                    f"resultado_mais_gols:{linha:g}",
                )
    if nome == "results/both teams score":
        partes = str(valor or "").split("/", 1)
        if len(partes) == 2:
            resultado = _selecao_resultado(partes[0])
            ambas = _normalizar(partes[1])
            if resultado and ambas in {"yes", "no"}:
                return (
                    "resultado_mais_ambas",
                    f"{resultado}|{'sim' if ambas == 'yes' else 'nao'}",
                    "resultado_mais_ambas",
                )
    if MERCADOS_TIME_ATIVOS and nome in {
        "home team score a goal", "away team score a goal",
    }:
        if valor_normalizado in {"yes", "no"}:
            lado = "mandante" if nome.startswith("home") else "visitante"
            resposta = "sim" if valor_normalizado == "yes" else "nao"
            return (
                "time_marca_gol",
                f"{lado}|{resposta}",
                f"time_marca_gol:{lado}",
            )
    eh_multigols = "multi goal" in nome or "multigoal" in nome
    if MERCADOS_TIME_ATIVOS and eh_multigols:
        lado = None
        if "home" in nome:
            lado = "mandante"
        elif "away" in nome:
            lado = "visitante"
        if lado:
            intervalo = re.search(
                r"\b(\d+)\s*(?:-|or|to)\s*(\d+)\b", valor_normalizado
            )
            if intervalo:
                minimo, maximo = map(int, intervalo.groups())
                if 0 <= minimo <= maximo <= 10:
                    return (
                        "multigols_time",
                        f"{lado}|de_{minimo}_a_{maximo}",
                        f"multigols_time:{lado}",
                    )
    if eh_multigols or nome == "number of goals in match":
        intervalo = re.search(r"\b(\d+)\s*(?:-|or|to)\s*(\d+)\b", valor_normalizado)
        if intervalo:
            minimo, maximo = map(int, intervalo.groups())
            if 0 <= minimo <= maximo <= 10:
                return (
                    "multigols",
                    f"de_{minimo}_a_{maximo}",
                    "multigols",
                )
    return None


def extrair_ofertas_api_football(itens, fixture_id=None):
    """Normaliza somente mercados cujo resultado pode ser liquidado."""
    ofertas = []
    for item in itens or []:
        observado = _fixture_id(item)
        if fixture_id is not None and observado != int(fixture_id):
            continue
        for bookmaker in item.get("bookmakers") or []:
            nome_casa = str(bookmaker.get("name") or "").strip()
            if not nome_casa:
                continue
            for aposta in bookmaker.get("bets") or []:
                nome_mercado = str(aposta.get("name") or "").strip()
                for valor in aposta.get("values") or []:
                    odd = _numero(valor.get("odd"))
                    classificada = _classificar_valor(
                        nome_mercado, valor.get("value")
                    )
                    if odd is None or odd <= 1.0 or classificada is None:
                        continue
                    mercado, selecao, grupo = classificada
                    ofertas.append({
                        "fixture_id": observado,
                        "bookmaker_id": bookmaker.get("id"),
                        "bookmaker": nome_casa,
                        "bet_id": aposta.get("id"),
                        "mercado_origem": nome_mercado,
                        "selecao_origem": valor.get("value"),
                        "mercado": mercado,
                        "selecao": selecao,
                        "grupo_precificacao": grupo,
                        "odd": round(odd, 4),
                        "fonte": "api_football",
                    })
    unicas = {}
    for oferta in ofertas:
        chave = (
            oferta["fixture_id"], oferta["bookmaker_id"],
            oferta["mercado"], oferta["selecao"],
        )
        anterior = unicas.get(chave)
        if anterior is None or oferta["odd"] > anterior["odd"]:
            unicas[chave] = oferta
    resultado = list(unicas.values())
    _anexar_probabilidade_sem_margem(resultado)
    return resultado


def _anexar_probabilidade_sem_margem(ofertas):
    grupos = {}
    mercados_particionados = {
        "resultado", "total_gols", "ambas_marcam",
        "resultado_mais_gols", "resultado_mais_ambas",
        "total_gols_mais_ambas",
        "time_marca_gol",
    }
    for oferta in ofertas:
        if oferta["mercado"] not in mercados_particionados:
            continue
        chave = (
            oferta["fixture_id"], oferta["bookmaker_id"],
            oferta["grupo_precificacao"],
        )
        grupos.setdefault(chave, []).append(oferta)
    for grupo in grupos.values():
        if len({item.get("selecao") for item in grupo}) < 2:
            continue
        soma = sum(1.0 / item["odd"] for item in grupo)
        if soma < 0.90 or soma > 1.50:
            continue
        for item in grupo:
            item["probabilidade_mercado_sem_margem"] = round(
                (1.0 / item["odd"]) / soma, 4
            )


def anexar_probabilidade_sem_margem(ofertas):
    """Aplica a remoção de margem também a ofertas de fontes complementares."""
    _anexar_probabilidade_sem_margem(ofertas)
    return ofertas


def _casa_consenso(oferta):
    nome = _normalizar((oferta or {}).get("bookmaker"))
    if nome:
        return nome
    return str((oferta or {}).get("bookmaker_id") or "desconhecida")


def anexar_consenso_casas(ofertas):
    """Compara a mesma seleção entre casas e identifica o melhor preço."""
    grupos = {}
    for oferta in ofertas or []:
        chave = (
            oferta.get("fixture_id"), oferta.get("mercado"),
            oferta.get("selecao"),
        )
        grupos.setdefault(chave, []).append(oferta)
    for grupo in grupos.values():
        por_casa = {}
        for item in grupo:
            casa = _casa_consenso(item)
            anterior = por_casa.get(casa)
            if anterior is None or float(item["odd"]) > float(anterior["odd"]):
                por_casa[casa] = item
        representantes = list(por_casa.values())
        odds = [float(item["odd"]) for item in representantes]
        odd_mediana = median(odds)
        odd_melhor = max(odds)
        probabilidades = [
            float(item["probabilidade_mercado_sem_margem"])
            for item in representantes
            if item.get("probabilidade_mercado_sem_margem") is not None
            and 0 < float(item["probabilidade_mercado_sem_margem"]) < 1
        ]
        consenso = (
            median(probabilidades)
            if len(probabilidades) >= CONSENSO_MINIMO_CASAS else None
        )
        for item in grupo:
            odd = float(item["odd"])
            item.update({
                "casas_comparadas": len(representantes),
                "casas_consenso_sem_margem": len(probabilidades),
                "probabilidade_consenso_casas": (
                    round(consenso, 4) if consenso is not None else None
                ),
                "odd_mediana_casas": round(odd_mediana, 4),
                "odd_melhor_casas": round(odd_melhor, 4),
                "desajuste_odd_relativo": round(
                    odd / odd_mediana - 1.0, 4
                ) if odd_mediana > 0 else 0.0,
                "melhor_preco_disponivel": bool(
                    abs(odd - odd_melhor) <= 1e-9
                ),
            })
    return ofertas


def _valor(bloco, chave):
    return _numero((bloco or {}).get(chave))


def _combinar_media(recente, temporada):
    valores = []
    for valor, peso in (
        (recente, PESO_RECENTE), (temporada, PESO_TEMPORADA)
    ):
        numero = _numero(valor)
        if numero is not None:
            valores.append((numero, peso))
    if not valores:
        return None
    peso_total = sum(peso for _, peso in valores)
    return sum(valor * peso for valor, peso in valores) / peso_total


def _media_recente_com_mando(bloco, chave):
    bloco = bloco or {}
    geral = bloco.get("geral") or {}
    mando = bloco.get("mando") or {}
    valor_geral = _valor(geral, chave)
    valor_mando = _valor(mando, chave)
    if valor_geral is None:
        return valor_mando
    if valor_mando is None:
        return valor_geral
    jogos_mando = max(int(_numero(mando.get("jogos")) or 0), 0)
    confianca_mando = min(jogos_mando / AMOSTRA_MANDO_CONFIAVEL, 1.0)
    peso_mando = PESO_MANDO_RECENTE_MAXIMO * confianca_mando
    return valor_mando * peso_mando + valor_geral * (1.0 - peso_mando)


def _percentual(valor):
    numero = _numero(str(valor or "").replace("%", ""))
    return numero / 100.0 if numero is not None else None


def _ajuste_previsao(contexto):
    previsao = (contexto or {}).get("previsao_provedor") or {}
    comparacao = previsao.get("comparacao_percentual") or {}
    total = comparacao.get("total") or {}
    casa = _percentual(total.get("home") or total.get("mandante"))
    fora = _percentual(total.get("away") or total.get("visitante"))
    delta = 0.0
    if casa is not None and fora is not None:
        delta = min(max(casa - fora, -1.0), 1.0)
    times = (contexto or {}).get("times") or {}
    vencedor_id = previsao.get("vencedor_id")
    direcao_vencedor = 0.0
    if vencedor_id == times.get("mandante_id"):
        direcao_vencedor = 1.0
    elif vencedor_id == times.get("visitante_id"):
        direcao_vencedor = -1.0
    deslocamento = min(max(0.04 * delta + 0.02 * direcao_vencedor,
                            -AJUSTE_PREVISAO_MAXIMO),
                       AJUSTE_PREVISAO_MAXIMO)
    return 1.0 + deslocamento, 1.0 - deslocamento, {
        "disponivel": bool(previsao),
        "delta_total": round(delta, 4),
        "vencedor_id": vencedor_id,
        "deslocamento": round(deslocamento, 4),
    }


def _ajuste_classificacao(contexto):
    classificacao = (contexto or {}).get("classificacao") or {}

    def forca(lado):
        item = classificacao.get(lado) or {}
        jogos = _numero(item.get("jogos"))
        pontos = _numero(item.get("pontos"))
        saldo = _numero(item.get("saldo_gols"))
        if not jogos or pontos is None:
            return None
        return pontos / jogos + 0.25 * ((saldo or 0.0) / jogos)

    casa, fora = forca("mandante"), forca("visitante")
    delta = 0.0 if casa is None or fora is None else min(
        max(casa - fora, -2.0), 2.0
    )
    deslocamento = min(max(0.025 * delta, -AJUSTE_CLASSIFICACAO_MAXIMO),
                       AJUSTE_CLASSIFICACAO_MAXIMO)
    return 1.0 + deslocamento, 1.0 - deslocamento, {
        "disponivel": casa is not None and fora is not None,
        "forca_mandante": round(casa, 4) if casa is not None else None,
        "forca_visitante": round(fora, 4) if fora is not None else None,
        "deslocamento": round(deslocamento, 4),
    }


def _ajuste_jogadores(contexto, lado):
    bloco = ((contexto or {}).get("jogadores_chave") or {}).get(lado) or {}
    confirmada = bool(bloco.get("escalacao_confirmada"))
    ajuste = 1.0
    presentes = ausentes = desfalques_relevantes = 0
    for jogador in bloco.get("jogadores") or []:
        impacto = min(max(_numero(jogador.get("impacto")) or 0.0, 0.0), 1.0)
        titular = jogador.get("titular")
        desfalque = bool(jogador.get("desfalque"))
        if desfalque:
            ajuste *= 1.0 - 0.08 * impacto
            ausentes += 1
            desfalques_relevantes += 1
        elif titular is True:
            ajuste *= 1.0 + 0.025 * impacto
            presentes += 1
        elif titular is False and confirmada:
            ajuste *= 1.0 - 0.06 * impacto
            ausentes += 1
    return min(max(ajuste, 0.88), 1.08), {
        "escalacao_confirmada": confirmada,
        "destaques_titulares": presentes,
        "destaques_ausentes": ausentes,
        "desfalques_relevantes": desfalques_relevantes,
    }


def construir_modelo_pre_live(contexto):
    capacidade = (contexto or {}).get("capacidade_times_v2") or {}
    recentes = capacidade.get("recentes") or {}
    temporada = capacidade.get("temporada_mando") or {}
    recentes_casa = recentes.get("mandante") or {}
    recentes_fora = recentes.get("visitante") or {}
    casa = (recentes_casa.get("mando") or {})
    fora = (recentes_fora.get("mando") or {})
    casa_temp = temporada.get("mandante") or {}
    fora_temp = temporada.get("visitante") or {}
    ataque_casa = _combinar_media(
        _media_recente_com_mando(recentes_casa, "gols_pro_media"),
        casa_temp.get("gols_pro_media"),
    )
    defesa_casa = _combinar_media(
        _media_recente_com_mando(recentes_casa, "gols_contra_media"),
        casa_temp.get("gols_contra_media"),
    )
    ataque_fora = _combinar_media(
        _media_recente_com_mando(recentes_fora, "gols_pro_media"),
        fora_temp.get("gols_pro_media"),
    )
    defesa_fora = _combinar_media(
        _media_recente_com_mando(recentes_fora, "gols_contra_media"),
        fora_temp.get("gols_contra_media"),
    )
    if any(
        valor is None
        for valor in (ataque_casa, defesa_casa, ataque_fora, defesa_fora)
    ):
        return None
    lambda_casa = 0.78 * ((ataque_casa + defesa_fora) / 2.0) + 0.22 * 1.25
    lambda_fora = 0.78 * ((ataque_fora + defesa_casa) / 2.0) + 0.22 * 1.10
    ajuste_casa, jogadores_casa = _ajuste_jogadores(contexto, "mandante")
    ajuste_fora, jogadores_fora = _ajuste_jogadores(contexto, "visitante")
    lambda_casa *= ajuste_casa
    lambda_fora *= ajuste_fora
    previsao_casa, previsao_fora, previsao_detalhe = _ajuste_previsao(
        contexto
    )
    classificacao_casa, classificacao_fora, classificacao_detalhe = (
        _ajuste_classificacao(contexto)
    )
    lambda_casa *= previsao_casa * classificacao_casa
    lambda_fora *= previsao_fora * classificacao_fora
    h2h = (contexto or {}).get("confrontos_diretos") or {}
    h2h_jogos = int(_numero(h2h.get("jogos")) or 0)
    h2h_media = _numero(h2h.get("media_gols"))
    ajuste_h2h = None
    if h2h_jogos >= 3 and h2h_media is not None:
        total_atual = lambda_casa + lambda_fora
        total_ajustado = 0.90 * total_atual + 0.10 * min(
            max(h2h_media, 0.5), 5.5
        )
        ajuste_h2h = round(total_ajustado - total_atual, 4)
        if total_atual > 0:
            lambda_casa *= total_ajustado / total_atual
            lambda_fora *= total_ajustado / total_atual
    lambda_casa = min(max(lambda_casa, 0.25), 3.8)
    lambda_fora = min(max(lambda_fora, 0.20), 3.5)
    return {
        "versao": VERSAO,
        "linhagem_sha256": LINHAGEM,
        "lambda_mandante": round(lambda_casa, 4),
        "lambda_visitante": round(lambda_fora, 4),
        "lambda_total": round(lambda_casa + lambda_fora, 4),
        "h2h": {
            "jogos": h2h_jogos,
            "media_gols": h2h_media,
            "ajuste_lambda_total": ajuste_h2h,
        },
        "amostras": {
            "mandante_geral": int(
                ((recentes.get("mandante") or {}).get("geral") or {}).get("jogos") or 0
            ),
            "mandante_mando": int(casa.get("jogos") or 0),
            "visitante_geral": int(
                ((recentes.get("visitante") or {}).get("geral") or {}).get("jogos") or 0
            ),
            "visitante_mando": int(fora.get("jogos") or 0),
        },
        "jogadores": {
            "mandante": jogadores_casa,
            "visitante": jogadores_fora,
        },
        "previsao": previsao_detalhe,
        "classificacao": classificacao_detalhe,
        "pesos_historico": {
            "recente": PESO_RECENTE,
            "temporada": PESO_TEMPORADA,
            "mando_recente_maximo": PESO_MANDO_RECENTE_MAXIMO,
        },
    }


def _poisson(k, media):
    return math.exp(-media) * (media ** k) / math.factorial(k)


def _matriz_probabilidades(modelo, maximo=12):
    casa = modelo["lambda_mandante"]
    fora = modelo["lambda_visitante"]
    matriz = []
    soma = 0.0
    for gols_casa in range(maximo + 1):
        for gols_fora in range(maximo + 1):
            prob = _poisson(gols_casa, casa) * _poisson(gols_fora, fora)
            matriz.append((gols_casa, gols_fora, prob))
            soma += prob
    if soma > 0:
        matriz = [(a, b, p / soma) for a, b, p in matriz]
    return matriz


def _probabilidade_selecao(oferta, matriz):
    mercado, selecao = oferta["mercado"], oferta["selecao"]

    def resultado(casa, fora):
        return "mandante" if casa > fora else "visitante" if fora > casa else "empate"

    def total_valido(total, texto):
        lado, linha = texto.split("_", 1)
        linha = float(linha)
        return total > linha if lado == "over" else total < linha

    probabilidade = 0.0
    for gols_casa, gols_fora, prob in matriz:
        total = gols_casa + gols_fora
        vencedor = resultado(gols_casa, gols_fora)
        ambas = gols_casa > 0 and gols_fora > 0
        ganhou = False
        if mercado == "resultado":
            ganhou = vencedor == selecao
        elif mercado == "chance_dupla":
            ganhou = (
                selecao == "mandante_ou_empate" and vencedor != "visitante"
                or selecao == "visitante_ou_empate" and vencedor != "mandante"
                or selecao == "sem_empate" and vencedor != "empate"
            )
        elif mercado == "chance_dupla_mais_gols":
            dupla, total_texto = selecao.split("|", 1)
            dupla_valida = (
                dupla == "mandante_ou_empate" and vencedor != "visitante"
                or dupla == "visitante_ou_empate" and vencedor != "mandante"
                or dupla == "sem_empate" and vencedor != "empate"
            )
            ganhou = dupla_valida and total_valido(total, total_texto)
        elif mercado == "total_gols":
            ganhou = total_valido(total, selecao)
        elif mercado == "ambas_marcam":
            ganhou = ambas if selecao == "sim" else not ambas
        elif mercado == "resultado_mais_gols":
            alvo, total_texto = selecao.split("|", 1)
            ganhou = vencedor == alvo and total_valido(total, total_texto)
        elif mercado == "resultado_mais_ambas":
            alvo, ambas_texto = selecao.split("|", 1)
            ganhou = vencedor == alvo and (
                ambas if ambas_texto == "sim" else not ambas
            )
        elif mercado == "total_gols_mais_ambas":
            total_texto, ambas_texto = selecao.split("|", 1)
            ganhou = total_valido(total, total_texto) and (
                ambas if ambas_texto == "sim" else not ambas
            )
        elif mercado == "multigols":
            numeros = [int(item) for item in re.findall(r"\d+", selecao)]
            ganhou = len(numeros) == 2 and numeros[0] <= total <= numeros[1]
        elif mercado == "time_marca_gol":
            lado, resposta = selecao.split("|", 1)
            gols_time = gols_casa if lado == "mandante" else gols_fora
            ganhou = gols_time > 0 if resposta == "sim" else gols_time == 0
        elif mercado == "multigols_time":
            lado, intervalo = selecao.split("|", 1)
            gols_time = gols_casa if lado == "mandante" else gols_fora
            numeros = [int(item) for item in re.findall(r"\d+", intervalo)]
            ganhou = (
                len(numeros) == 2
                and numeros[0] <= gols_time <= numeros[1]
            )
        if ganhou:
            probabilidade += prob
    return probabilidade


def liquidar_perna_pre_live(perna, fixture):
    """Liquida uma perna pela pontuação regulamentar da API-Football."""
    fixture = fixture or {}
    dados_fixture = fixture.get("fixture") or {}
    status = str((dados_fixture.get("status") or {}).get("short") or "").upper()
    if status in {"CANC", "ABD", "AWD", "WO", "PST"}:
        return "anulada"
    finalizada = status in {"FT", "AET", "PEN"}
    placar = (
        (fixture.get("score") or {}).get("fulltime") or {}
        if finalizada else {}
    )
    casa = _numero(placar.get("home"))
    fora = _numero(placar.get("away"))
    if casa is None or fora is None:
        gols = fixture.get("goals") or {}
        casa, fora = _numero(gols.get("home")), _numero(gols.get("away"))
    if casa is None or fora is None:
        return "pendente"
    casa, fora = int(casa), int(fora)
    mercado, selecao = perna.get("mercado"), perna.get("selecao")
    vencedor = "mandante" if casa > fora else "visitante" if fora > casa else "empate"
    total = casa + fora
    ambas = casa > 0 and fora > 0

    def total_valido(texto):
        try:
            lado, linha = str(texto).split("_", 1)
            linha = float(linha)
        except (TypeError, ValueError):
            return None
        return total > linha if lado == "over" else total < linha

    ganhou = None
    if not finalizada:
        if mercado == "total_gols":
            atual = total_valido(selecao)
            if str(selecao).startswith("over_") and atual is True:
                return "green"
            if str(selecao).startswith("under_") and atual is False:
                return "red"
        elif mercado == "ambas_marcam":
            if selecao == "sim" and ambas:
                return "green"
            if selecao == "nao" and ambas:
                return "red"
        elif mercado in {"chance_dupla_mais_gols", "resultado_mais_gols"}:
            try:
                _alvo, total_texto = str(selecao).split("|", 1)
            except ValueError:
                return "pendente"
            if (
                str(total_texto).startswith("under_")
                and total_valido(total_texto) is False
            ):
                return "red"
        elif mercado == "resultado_mais_ambas":
            try:
                _alvo, ambas_texto = str(selecao).split("|", 1)
            except ValueError:
                return "pendente"
            if ambas_texto == "nao" and ambas:
                return "red"
        elif mercado == "total_gols_mais_ambas":
            try:
                total_texto, ambas_texto = str(selecao).split("|", 1)
            except ValueError:
                return "pendente"
            total_atual = total_valido(total_texto)
            if str(total_texto).startswith("over_") and total_atual is True:
                if ambas_texto == "sim" and ambas:
                    return "green"
                if ambas_texto == "nao" and ambas:
                    return "red"
            if str(total_texto).startswith("under_") and total_atual is False:
                return "red"
            if ambas_texto == "nao" and ambas:
                return "red"
        elif mercado == "multigols":
            numeros = [int(item) for item in re.findall(r"\d+", str(selecao))]
            if len(numeros) == 2 and total > numeros[1]:
                return "red"
        elif mercado == "time_marca_gol":
            try:
                lado, resposta = str(selecao).split("|", 1)
            except ValueError:
                return "pendente"
            gols_time = casa if lado == "mandante" else fora
            if resposta == "sim" and gols_time > 0:
                return "green"
            if resposta == "nao" and gols_time > 0:
                return "red"
        elif mercado == "multigols_time":
            try:
                lado, intervalo = str(selecao).split("|", 1)
            except ValueError:
                return "pendente"
            gols_time = casa if lado == "mandante" else fora
            numeros = [int(item) for item in re.findall(r"\d+", intervalo)]
            if len(numeros) == 2 and gols_time > numeros[1]:
                return "red"
        return "pendente"
    if mercado == "resultado":
        ganhou = vencedor == selecao
    elif mercado == "chance_dupla":
        ganhou = (
            selecao == "mandante_ou_empate" and vencedor != "visitante"
            or selecao == "visitante_ou_empate" and vencedor != "mandante"
            or selecao == "sem_empate" and vencedor != "empate"
        )
    elif mercado == "chance_dupla_mais_gols":
        try:
            dupla, total_texto = str(selecao).split("|", 1)
        except ValueError:
            return "pendente"
        dupla_valida = (
            dupla == "mandante_ou_empate" and vencedor != "visitante"
            or dupla == "visitante_ou_empate" and vencedor != "mandante"
            or dupla == "sem_empate" and vencedor != "empate"
        )
        total_ok = total_valido(total_texto)
        ganhou = dupla_valida and total_ok is True
    elif mercado == "total_gols":
        ganhou = total_valido(selecao)
    elif mercado == "ambas_marcam":
        ganhou = ambas if selecao == "sim" else not ambas
    elif mercado == "resultado_mais_gols":
        try:
            alvo, total_texto = str(selecao).split("|", 1)
        except ValueError:
            return "pendente"
        total_ok = total_valido(total_texto)
        ganhou = vencedor == alvo and total_ok is True
    elif mercado == "resultado_mais_ambas":
        try:
            alvo, ambas_texto = str(selecao).split("|", 1)
        except ValueError:
            return "pendente"
        ganhou = vencedor == alvo and (
            ambas if ambas_texto == "sim" else not ambas
        )
    elif mercado == "total_gols_mais_ambas":
        try:
            total_texto, ambas_texto = str(selecao).split("|", 1)
        except ValueError:
            return "pendente"
        total_ok = total_valido(total_texto)
        ganhou = total_ok is True and (
            ambas if ambas_texto == "sim" else not ambas
        )
    elif mercado == "multigols":
        numeros = [int(item) for item in re.findall(r"\d+", str(selecao))]
        if len(numeros) == 2:
            ganhou = numeros[0] <= total <= numeros[1]
    elif mercado == "time_marca_gol":
        try:
            lado, resposta = str(selecao).split("|", 1)
        except ValueError:
            return "pendente"
        gols_time = casa if lado == "mandante" else fora
        ganhou = gols_time > 0 if resposta == "sim" else gols_time == 0
    elif mercado == "multigols_time":
        try:
            lado, intervalo = str(selecao).split("|", 1)
        except ValueError:
            return "pendente"
        gols_time = casa if lado == "mandante" else fora
        numeros = [int(item) for item in re.findall(r"\d+", intervalo)]
        if len(numeros) == 2:
            ganhou = numeros[0] <= gols_time <= numeros[1]
    if ganhou is None:
        return "pendente"
    return "green" if ganhou else "red"


def liquidar_bilhete_pre_live(bilhete, fixtures_por_id):
    resultados = []
    for perna in (bilhete or {}).get("pernas") or []:
        fixture = (fixtures_por_id or {}).get(int(perna.get("fixture_id") or 0))
        resultados.append(liquidar_perna_pre_live(perna, fixture))
    if not resultados:
        return {"resultado": "pendente", "pernas": resultados}
    if "red" in resultados:
        return {"resultado": "red", "pernas": resultados, "retorno": -1.0}
    if "pendente" in resultados:
        return {"resultado": "pendente", "pernas": resultados}
    if all(item == "anulada" for item in resultados):
        return {"resultado": "anulada", "pernas": resultados, "retorno": 0.0}
    odd_efetiva = 1.0
    for perna, resultado in zip((bilhete or {}).get("pernas") or [], resultados):
        if resultado == "green":
            odd_efetiva *= float(perna.get("odd") or 1.0)
    return {
        "resultado": "green", "pernas": resultados,
        "odd_efetiva": round(odd_efetiva, 4),
        "retorno": round(odd_efetiva - 1.0, 4),
    }


def avaliar_ofertas_pre_live(ofertas, contexto, qualidade=None):
    modelo = construir_modelo_pre_live(contexto)
    if modelo is None:
        return {
            "modelo": None, "avaliadas": [], "elegiveis": [],
            "motivo": "historico_contextual_insuficiente",
        }
    qualidade = float(qualidade if qualidade is not None else calcular_qualidade_contexto(contexto))
    matriz = _matriz_probabilidades(modelo)
    ofertas = list(ofertas or [])
    _anexar_probabilidade_sem_margem(ofertas)
    anexar_consenso_casas(ofertas)
    avaliadas = []
    for oferta in ofertas:
        probabilidade = _probabilidade_selecao(oferta, matriz)
        implicita = 1.0 / oferta["odd"]
        edge = probabilidade - implicita
        mercado_sem_margem = oferta.get("probabilidade_mercado_sem_margem")
        consenso = oferta.get("probabilidade_consenso_casas")
        casas_consenso = int(oferta.get("casas_consenso_sem_margem") or 0)
        consenso_disponivel = bool(
            consenso is not None and casas_consenso >= CONSENSO_MINIMO_CASAS
        )
        divergencia_consenso = (
            abs(probabilidade - float(consenso))
            if consenso_disponivel else None
        )
        if consenso_disponivel:
            probabilidade_conservadora = min(
                probabilidade, float(consenso)
            )
        else:
            probabilidade_conservadora = (
                implicita + max(edge, 0.0) * DESCONTO_EDGE_SEM_CONSENSO
            )
        edge_conservador = probabilidade_conservadora - implicita
        valor_esperado = probabilidade * float(oferta["odd"]) - 1.0
        desajuste_preco = max(
            float(oferta.get("desajuste_odd_relativo") or 0.0), 0.0
        )
        base_valor = (
            0.55 * max(edge_conservador, 0.0)
            + 0.30 * max(edge, 0.0)
            + 0.15 * min(desajuste_preco, 0.20)
        )
        score_valor = (
            100.0 * base_valor * (0.75 + 0.25 * qualidade / 100.0)
        )
        avaliadas.append({
            **oferta,
            "probabilidade_modelo": round(probabilidade, 4),
            "probabilidade_conservadora": round(
                probabilidade_conservadora, 4
            ),
            "probabilidade_implicita": round(implicita, 4),
            "edge_modelo": round(edge, 4),
            "edge_conservador": round(edge_conservador, 4),
            "valor_esperado_modelo": round(valor_esperado, 4),
            "score_valor": round(score_valor, 4),
            "consenso_disponivel": consenso_disponivel,
            "divergencia_modelo_consenso": (
                round(divergencia_consenso, 4)
                if divergencia_consenso is not None else None
            ),
            "diferenca_consenso_sem_margem": (
                round(probabilidade - float(consenso), 4)
                if consenso_disponivel else (
                    round(probabilidade - mercado_sem_margem, 4)
                    if mercado_sem_margem is not None else None
                )
            ),
            "qualidade_contexto": round(qualidade, 1),
            "modelo": modelo,
        })
    elegiveis = [
        item for item in avaliadas
        if ODD_MINIMA_PERNA <= item["odd"] <= ODD_MAXIMA
        and item["probabilidade_modelo"] >= PROBABILIDADE_MINIMA_PERNA
        and item["edge_modelo"] >= EDGE_MINIMO
        and (
            RETORNO_DIA30 or (
                item["edge_conservador"] >= EDGE_CONSERVADOR_MINIMO
                and item.get("melhor_preco_disponivel", True)
                and (
                    item["divergencia_modelo_consenso"] is None
                    or item["divergencia_modelo_consenso"]
                    <= DIVERGENCIA_MAXIMA_MODELO_CONSENSO
                )
            )
        )
        and qualidade >= QUALIDADE_MINIMA
    ]
    elegiveis.sort(
        key=lambda item: (
            item["edge_modelo"], item["probabilidade_modelo"],
            item["qualidade_contexto"],
        ) if RETORNO_DIA30 else (
            item["score_valor"], item["edge_conservador"],
            item["valor_esperado_modelo"], item["probabilidade_modelo"],
            item["qualidade_contexto"],
        ),
        reverse=True,
    )
    return {
        "modelo": modelo,
        "avaliadas": avaliadas,
        "elegiveis": elegiveis,
        "motivo": None if elegiveis else "nenhuma_oferta_com_vantagem",
    }


def calcular_qualidade_contexto(contexto):
    capacidade = (contexto or {}).get("capacidade_times_v2") or {}
    cobertura = capacidade.get("cobertura") or {}
    pontos = 0.0
    for lado in ("mandante", "visitante"):
        item = cobertura.get(lado) or {}
        pontos += min(int(item.get("historico_total") or 0) / 15.0, 1.0) * 17.5
        pontos += min(int(item.get("historico_mando") or 0) / 4.0, 1.0) * 7.5
    if capacidade.get("temporada_mando"):
        pontos += 10.0
    if ((contexto or {}).get("confrontos_diretos") or {}).get("jogos"):
        pontos += 5.0
    jogadores = (contexto or {}).get("jogadores_chave") or {}
    if any(
        int((jogadores.get(lado) or {}).get("destaques_encontrados") or 0) > 0
        or bool((jogadores.get(lado) or {}).get("jogadores"))
        for lado in ("mandante", "visitante")
    ):
        pontos += 5.0
    if all(
        bool((jogadores.get(lado) or {}).get("escalacao_confirmada"))
        for lado in ("mandante", "visitante")
    ):
        pontos += 15.0
    if (contexto or {}).get("previsao_provedor"):
        pontos += 5.0
    classificacao = (contexto or {}).get("classificacao") or {}
    if all(classificacao.get(lado) for lado in ("mandante", "visitante")):
        pontos += 5.0
    if (contexto or {}).get("desfalques") is not None:
        pontos += 5.0
    return min(round(pontos, 1), 100.0)


def _identidade_perna(item):
    return (
        item.get("fixture_id"), item.get("bookmaker_id"),
        item.get("mercado"), item.get("selecao"),
    )


def _chave_perna_estavel(item):
    try:
        fixture_id = int(item.get("fixture_id") or 0)
    except (TypeError, ValueError):
        fixture_id = 0
    return (
        fixture_id,
        str(item.get("bookmaker_id") or ""),
        str(item.get("mercado") or ""),
        str(item.get("selecao") or ""),
    )


def _ambiente_ativo(nome, padrao=False):
    valor_padrao = "1" if padrao else "0"
    return os.getenv(nome, valor_padrao).strip().lower() in {
        "1", "true", "sim", "yes", "on",
    }


def _escalacoes_confirmadas(bilhete):
    return all(
        all(
            bool(
                ((perna.get("modelo") or {}).get("jogadores") or {})
                .get(lado, {}).get("escalacao_confirmada")
            )
            for lado in ("mandante", "visitante")
        )
        for perna in (bilhete or {}).get("pernas") or []
    )


def politica_v11_ativa():
    return not RETORNO_DIA30 and _ambiente_ativo("PRELIVE_POLITICA_V11_ATIVA", True)


def _aplicar_politica_confirmacao(bilhete, aplicacao_automatica):
    """Exige escalações reais nos dois perfis; V11 acrescenta seus filtros."""
    politica_v11 = politica_v11_ativa()
    multiplas_oficiais = RETORNO_DIA30 or _ambiente_ativo(
        "PRELIVE_V11_MULTIPLAS_OFICIAIS_ATIVAS", False
    )
    pernas = list((bilhete or {}).get("pernas") or [])
    qualidade_minima = min(
        (float(item.get("qualidade_contexto") or 0.0) for item in pernas),
        default=0.0,
    )
    edge_conservador = float(
        bilhete.get("edge_conservador", bilhete.get("edge_modelo") or 0.0)
    )
    escalacoes_confirmadas = bool(
        pernas and _escalacoes_confirmadas(bilhete)
    )
    confirmada = bool(
        qualidade_minima >= QUALIDADE_CONFIRMADA_MINIMA
        and escalacoes_confirmadas
    )
    atende_v11 = bool(
        qualidade_minima >= QUALIDADE_OFICIAL_V11_MINIMA
        and edge_conservador >= EDGE_CONSERVADOR_OFICIAL_V11_MINIMO
    )
    multipla_bloqueada = bool(
        politica_v11
        and str(bilhete.get("tipo") or "") != "simples"
        and not multiplas_oficiais
    )
    oficial = bool(
        confirmada
        and aplicacao_automatica
        and (not politica_v11 or atende_v11)
        and not multipla_bloqueada
    )
    if oficial:
        estado = "apto_envio_automatico"
    elif confirmada:
        estado = "apto_sombra_confirmado"
    else:
        estado = "preliminar_aguardando_escalacao"
    bilhete.update({
        "estado": estado,
        "aplicacao_automatica": bool(aplicacao_automatica),
        "telegram": bool(oficial),
        "politica_oficial": (
            "retorno-dia30-v7-odd150" if RETORNO_DIA30 else (
                "prelive-profissional-v11" if politica_v11 else "legado-v10"
            )
        ),
        "criterios_oficiais_v11": {
            "atendidos": bool(atende_v11),
            "qualidade_minima_observada": round(qualidade_minima, 1),
            "qualidade_minima_exigida": QUALIDADE_OFICIAL_V11_MINIMA,
            "edge_conservador": round(edge_conservador, 4),
            "edge_conservador_minimo": (
                EDGE_CONSERVADOR_OFICIAL_V11_MINIMO
            ),
            "escalacoes_confirmadas": escalacoes_confirmadas,
            "multipla_oficial_liberada": bool(
                str(bilhete.get("tipo") or "") == "simples"
                or multiplas_oficiais
            ),
        },
        "rollback_politica_oficial": "PRELIVE_POLITICA_V11_ATIVA=0",
        "perfil_selecao": PERFIL_SELECAO,
        "rollback_perfil_selecao": "PRELIVE_PERFIL_SELECAO=v11",
    })
    return bilhete


def _recalcular_bilhete_existente(bilhete, pernas):
    tipo = str((bilhete or {}).get("tipo") or "")
    tamanhos = {
        "simples": 1,
        "multipla_dois_jogos": 2,
        "multipla_tres_jogos": 3,
    }
    if tamanhos.get(tipo) != len(pernas):
        return None
    if len(pernas) > 1 and len({
        int(item.get("fixture_id") or 0) for item in pernas
    }) != len(pernas):
        return None
    if len(pernas) > 1 and len({
        str(item.get("bookmaker_id") or "") for item in pernas
    }) != 1:
        return None

    odd_total = math.prod(float(item.get("odd") or 0.0) for item in pernas)
    if not ODD_MINIMA <= odd_total <= ODD_MAXIMA:
        return None
    probabilidade = math.prod(
        float(item.get("probabilidade_modelo") or 0.0) for item in pernas
    )
    probabilidade_conservadora = math.prod(
        float(item.get(
            "probabilidade_conservadora",
            item.get("probabilidade_modelo") or 0.0,
        ))
        for item in pernas
    )
    edge = probabilidade - 1.0 / odd_total
    edge_conservador = probabilidade_conservadora - 1.0 / odd_total
    if len(pernas) == 1:
        edge = float(pernas[0].get("edge_modelo") or edge)
        edge_conservador = float(
            pernas[0].get("edge_conservador", edge_conservador)
        )
        if edge < EDGE_MINIMO or (
            not RETORNO_DIA30 and edge_conservador < EDGE_CONSERVADOR_MINIMO
        ):
            return None
    elif len(pernas) == 2:
        if (
            edge < EDGE_MINIMO_BILHETE
            or (not RETORNO_DIA30 and edge_conservador < EDGE_CONSERVADOR_MINIMO_BILHETE)
        ):
            return None
    else:
        if any(
            float(item.get("probabilidade_modelo") or 0.0)
            < PROBABILIDADE_MINIMA_PERNA_TRIPLA
            or float(item.get("qualidade_contexto") or 0.0)
            < QUALIDADE_MINIMA_TRIPLA
            for item in pernas
        ):
            return None
        if (
            edge < EDGE_MINIMO_BILHETE_TRIPLA
            or (not RETORNO_DIA30 and edge_conservador < EDGE_CONSERVADOR_MINIMO_BILHETE)
        ):
            return None
    faixa_estendida = odd_total > ODD_MAXIMA_PREFERENCIAL
    if faixa_estendida and not (
        edge >= EDGE_MINIMO_FAIXA_ESTENDIDA
        and all(
            float(item.get("qualidade_contexto") or 0.0)
            >= QUALIDADE_MINIMA_FAIXA_ESTENDIDA
            for item in pernas
        )
    ):
        return None

    atualizado = dict(bilhete or {})
    atualizado.update({
        "pernas": pernas,
        "bookmaker": str(pernas[0].get("bookmaker") or ""),
        "odd_total": round(odd_total, 4),
        "probabilidade_modelo": round(probabilidade, 4),
        "edge_modelo": round(edge, 4),
        "edge_conservador": round(edge_conservador, 4),
        "score_valor": round(
            100.0 * (0.65 * edge_conservador + 0.35 * edge), 4
        ),
        "faixa_odd": "estendida" if faixa_estendida else "preferencial",
        "tema": _tema_bilhete({"pernas": pernas}),
        "revalidado_sem_republicar": True,
    })
    return atualizado


def revalidar_bilhetes_publicados_pre_live(
    publicados, avaliacoes_por_jogo, aplicacao_automatica=False,
):
    """Reconfere bilhetes exibidos sem recolocá-los no ranking do horário."""
    ofertas = {}
    for avaliacao in avaliacoes_por_jogo or []:
        jogo = avaliacao.get("jogo") or {}
        for item in (avaliacao.get("avaliacao") or {}).get("elegiveis") or []:
            perna = {**item, "jogo": jogo}
            chave = _chave_perna_estavel(perna)
            anterior = ofertas.get(chave)
            if anterior is None or (
                float(perna.get("score_valor") or 0.0),
                float(perna.get("odd") or 0.0),
            ) > (
                float(anterior.get("score_valor") or 0.0),
                float(anterior.get("odd") or 0.0),
            ):
                ofertas[chave] = perna

    revalidados = []
    for registro in publicados or []:
        original = registro.get("bilhete") if isinstance(registro, dict) else None
        original = original if isinstance(original, dict) else registro
        if not isinstance(original, dict):
            continue
        novas_pernas = []
        for perna in original.get("pernas") or []:
            atual = ofertas.get(_chave_perna_estavel(perna))
            if atual is None:
                novas_pernas = []
                break
            novas_pernas.append(atual)
        if not novas_pernas:
            continue
        atualizado = _recalcular_bilhete_existente(original, novas_pernas)
        if atualizado is None:
            continue
        # A identidade precisa continuar sendo a originalmente publicada.
        atualizado["versao"] = original.get("versao") or VERSAO
        atualizado["linhagem_sha256"] = original.get(
            "linhagem_sha256"
        ) or LINHAGEM
        atualizado["politica_revalidacao"] = (
            "retorno-dia30-v7-odd150" if RETORNO_DIA30 else "prelive-profissional-v11"
        )
        _aplicar_politica_confirmacao(atualizado, aplicacao_automatica)
        revalidados.append(atualizado)
    return revalidados


def _remover_pernas_dominadas(pernas):
    """Remove a selecao mais restritiva quando ela nao paga melhor.

    Marcar ao menos um gol contem todos os resultados 1-N e tambem os raros
    N+1 em diante. Portanto, na mesma casa e jogo, o multigols 1-N e
    estritamente pior quando sua odd e menor ou igual a do time +0.5.
    """
    melhores_time_marca = {}
    for perna in pernas or []:
        if perna.get("mercado") != "time_marca_gol":
            continue
        try:
            lado, resposta = str(perna.get("selecao") or "").split("|", 1)
        except ValueError:
            continue
        if resposta != "sim":
            continue
        chave = (
            perna.get("fixture_id"), perna.get("bookmaker_id"), lado,
        )
        melhores_time_marca[chave] = max(
            float(perna.get("odd") or 0.0),
            float(melhores_time_marca.get(chave) or 0.0),
        )

    resultado = []
    for perna in pernas or []:
        if perna.get("mercado") == "multigols_time":
            try:
                lado, intervalo = str(
                    perna.get("selecao") or ""
                ).split("|", 1)
            except ValueError:
                lado, intervalo = None, ""
            numeros = [int(item) for item in re.findall(r"\d+", intervalo)]
            chave = (
                perna.get("fixture_id"), perna.get("bookmaker_id"), lado,
            )
            odd_dominante = melhores_time_marca.get(chave)
            if (
                len(numeros) == 2
                and numeros[0] == 1
                and odd_dominante is not None
                and float(odd_dominante) + 1e-9
                >= float(perna.get("odd") or 0.0)
            ):
                continue
        resultado.append(perna)
    return resultado


def _tema_perna(perna):
    mercado = str((perna or {}).get("mercado") or "")
    selecao = str((perna or {}).get("selecao") or "")
    if mercado in {
        "total_gols", "chance_dupla_mais_gols", "resultado_mais_gols",
        "total_gols_mais_ambas",
    }:
        if "under_" in selecao:
            return "under"
        if "over_" in selecao:
            return "over"
    if mercado in {"ambas_marcam", "resultado_mais_ambas"}:
        return "ambas_marcam"
    if mercado in {"multigols", "multigols_time"}:
        return "multigols"
    if mercado == "time_marca_gol":
        return "time_marca"
    if mercado in {"resultado", "chance_dupla"}:
        return "resultado_protegido"
    return "outro"


def _tema_bilhete(bilhete):
    temas = {_tema_perna(item) for item in (bilhete or {}).get("pernas") or []}
    temas.discard("outro")
    if len(temas) == 1:
        return next(iter(temas))
    return "misto" if temas else "outro"


def _filtrar_faixa_melhores(bilhetes):
    """Retém somente o primeiro patamar de valor, sem completar uma quota."""
    bilhetes = list(bilhetes or [])
    if RETORNO_DIA30:
        return bilhetes
    if not bilhetes:
        return []
    melhor_score = max(
        float(item.get("score_valor") or 0.0) for item in bilhetes
    )
    if melhor_score <= 0:
        return bilhetes[:1]
    limiar = melhor_score * FAIXA_RELATIVA_SCORE_MELHORES
    return [
        item for item in bilhetes
        if float(item.get("score_valor") or 0.0) >= limiar
    ]


def montar_bilhetes_pre_live(
    avaliacoes_por_jogo, maximo=10, aplicacao_automatica=False,
):
    """Monta singles e múltiplas de até três partidas independentes."""
    pernas = []
    for avaliacao in avaliacoes_por_jogo or []:
        dados_jogo = avaliacao.get("jogo") or {}
        for item in (avaliacao.get("avaliacao") or {}).get("elegiveis") or []:
            pernas.append({**item, "jogo": dados_jogo})
    pernas = _remover_pernas_dominadas(pernas)

    bilhetes = []
    for perna in pernas:
        if ODD_MINIMA <= perna["odd"] <= ODD_MAXIMA:
            faixa_estendida = perna["odd"] > ODD_MAXIMA_PREFERENCIAL
            if faixa_estendida and not (
                perna["edge_modelo"] >= EDGE_MINIMO_FAIXA_ESTENDIDA
                and perna["qualidade_contexto"]
                >= QUALIDADE_MINIMA_FAIXA_ESTENDIDA
            ):
                continue
            bilhetes.append({
                "tipo": "simples",
                "pernas": [perna],
                "bookmaker": perna["bookmaker"],
                "odd_total": perna["odd"],
                "probabilidade_modelo": perna["probabilidade_modelo"],
                "edge_modelo": perna["edge_modelo"],
                "edge_conservador": perna.get(
                    "edge_conservador", perna["edge_modelo"]
                ),
                "score_valor": perna.get(
                    "score_valor",
                    round(100.0 * perna["edge_modelo"], 4),
                ),
                "faixa_odd": (
                    "estendida" if faixa_estendida else "preferencial"
                ),
            })

    pernas_multiplas = [
        item for item in pernas
        if ODD_MINIMA_PERNA <= item["odd"] <= ODD_MAXIMA_PERNA
    ]
    for primeira, segunda in combinations(pernas_multiplas, 2):
        if primeira.get("fixture_id") == segunda.get("fixture_id"):
            continue
        if primeira.get("bookmaker_id") != segunda.get("bookmaker_id"):
            continue
        odd_total = primeira["odd"] * segunda["odd"]
        if not ODD_MINIMA <= odd_total <= ODD_MAXIMA:
            continue
        probabilidade = (
            primeira["probabilidade_modelo"]
            * segunda["probabilidade_modelo"]
        )
        edge = probabilidade - 1.0 / odd_total
        if edge < EDGE_MINIMO_BILHETE:
            continue
        probabilidade_conservadora = math.prod(
            item.get(
                "probabilidade_conservadora", item["probabilidade_modelo"]
            )
            for item in (primeira, segunda)
        )
        edge_conservador = probabilidade_conservadora - 1.0 / odd_total
        if not RETORNO_DIA30 and edge_conservador < EDGE_CONSERVADOR_MINIMO_BILHETE:
            continue
        faixa_estendida = odd_total > ODD_MAXIMA_PREFERENCIAL
        if faixa_estendida and not (
            edge >= EDGE_MINIMO_FAIXA_ESTENDIDA
            and all(
                item["qualidade_contexto"]
                >= QUALIDADE_MINIMA_FAIXA_ESTENDIDA
                for item in (primeira, segunda)
            )
        ):
            continue
        bilhetes.append({
            "tipo": "multipla_dois_jogos",
            "pernas": [primeira, segunda],
            "bookmaker": primeira["bookmaker"],
            "odd_total": round(odd_total, 4),
            "probabilidade_modelo": round(probabilidade, 4),
            "edge_modelo": round(edge, 4),
            "edge_conservador": round(edge_conservador, 4),
            "score_valor": round(
                100.0 * (0.65 * edge_conservador + 0.35 * edge)
                * (
                    0.75 + 0.25 * sum(
                        item["qualidade_contexto"]
                        for item in (primeira, segunda)
                    ) / 200.0
                ),
                4,
            ),
            "hipotese_independencia_partidas": True,
            "faixa_odd": (
                "estendida" if faixa_estendida else "preferencial"
            ),
        })

    if MULTIPLAS_TRES_PERNAS_ATIVAS and MAXIMO_PERNAS >= 3:
        por_casa = {}
        for perna in pernas_multiplas:
            chave_casa = (perna.get("bookmaker_id"), perna.get("bookmaker"))
            por_casa.setdefault(chave_casa, []).append(perna)
        for pernas_casa in por_casa.values():
            por_fixture = {}
            for perna in pernas_casa:
                por_fixture.setdefault(perna.get("fixture_id"), []).append(perna)
            candidatas = []
            for opcoes in por_fixture.values():
                opcoes.sort(
                    key=lambda item: (
                        item["probabilidade_modelo"], item["edge_modelo"],
                        item["qualidade_contexto"],
                    ),
                    reverse=True,
                )
                candidatas.extend(opcoes[:2])
            candidatas.sort(
                key=lambda item: (
                    item["probabilidade_modelo"], item["edge_modelo"],
                    item["qualidade_contexto"],
                ),
                reverse=True,
            )
            candidatas = candidatas[:MAXIMO_PERNAS_POR_CASA_TRIPLA]
            for tripla in combinations(candidatas, 3):
                if len({item.get("fixture_id") for item in tripla}) != 3:
                    continue
                if any(
                    item["probabilidade_modelo"]
                    < PROBABILIDADE_MINIMA_PERNA_TRIPLA
                    or item["qualidade_contexto"] < QUALIDADE_MINIMA_TRIPLA
                    for item in tripla
                ):
                    continue
                odd_total = math.prod(item["odd"] for item in tripla)
                if not ODD_MINIMA <= odd_total <= ODD_MAXIMA:
                    continue
                probabilidade = math.prod(
                    item["probabilidade_modelo"] for item in tripla
                )
                edge = probabilidade - 1.0 / odd_total
                if edge < EDGE_MINIMO_BILHETE_TRIPLA:
                    continue
                probabilidade_conservadora = math.prod(
                    item.get(
                        "probabilidade_conservadora",
                        item["probabilidade_modelo"],
                    )
                    for item in tripla
                )
                edge_conservador = (
                    probabilidade_conservadora - 1.0 / odd_total
                )
                if not RETORNO_DIA30 and edge_conservador < EDGE_CONSERVADOR_MINIMO_BILHETE:
                    continue
                faixa_estendida = odd_total > ODD_MAXIMA_PREFERENCIAL
                if faixa_estendida and not (
                    edge >= EDGE_MINIMO_FAIXA_ESTENDIDA
                    and all(
                        item["qualidade_contexto"]
                        >= QUALIDADE_MINIMA_FAIXA_ESTENDIDA
                        for item in tripla
                    )
                ):
                    continue
                bilhetes.append({
                    "tipo": "multipla_tres_jogos",
                    "pernas": list(tripla),
                    "bookmaker": tripla[0]["bookmaker"],
                    "odd_total": round(odd_total, 4),
                    "probabilidade_modelo": round(probabilidade, 4),
                    "edge_modelo": round(edge, 4),
                    "edge_conservador": round(edge_conservador, 4),
                    "score_valor": round(
                        100.0 * (
                            0.65 * edge_conservador + 0.35 * edge
                        ) * (
                            0.75 + 0.25 * sum(
                                item["qualidade_contexto"]
                                for item in tripla
                            ) / 300.0
                        ),
                        4,
                    ),
                    "hipotese_independencia_partidas": True,
                    "faixa_odd": (
                        "estendida" if faixa_estendida else "preferencial"
                    ),
                })

    unicos = {}
    for bilhete in bilhetes:
        chave = tuple(sorted(_identidade_perna(item) for item in bilhete["pernas"]))
        anterior = unicos.get(chave)
        if anterior is None or bilhete["edge_modelo"] > anterior["edge_modelo"]:
            unicos[chave] = bilhete
    ordenados = sorted(
        unicos.values(),
        key=lambda item: (
            item["probabilidade_modelo"],
            item.get("faixa_odd") == "preferencial",
            item["edge_modelo"],
            min(perna["qualidade_contexto"] for perna in item["pernas"]),
        ) if RETORNO_DIA30 else (
            item.get("score_valor", 0.0),
            item.get("edge_conservador", item["edge_modelo"]),
            item["probabilidade_modelo"],
            item.get("faixa_odd") == "preferencial",
            item["edge_modelo"],
            min(perna["qualidade_contexto"] for perna in item["pernas"]),
        ),
        reverse=True,
    )

    for bilhete in ordenados:
        bilhete["tema"] = _tema_bilhete(bilhete)

    candidatos_portfolio = []
    fixtures_expostos = set()
    for bilhete in ordenados:
        fixtures = {
            int(perna.get("fixture_id"))
            for perna in bilhete["pernas"]
            if perna.get("fixture_id") is not None
        }
        if fixtures & fixtures_expostos:
            continue
        candidatos_portfolio.append(bilhete)
        fixtures_expostos.update(fixtures)
    selecionados = _filtrar_faixa_melhores(candidatos_portfolio)[
        :max(int(maximo), 0)
    ]
    for indice, bilhete in enumerate(selecionados, 1):
        bilhete.update({
            "posicao": indice,
            "versao": VERSAO,
            "linhagem_sha256": LINHAGEM,
            "controle_correlacao": "fixtures_nao_repetidos_no_portfolio",
            "rollback_variedade": (
                "PRELIVE_MULTIPLAS_TRES_PERNAS_ATIVAS=0; "
                "PRELIVE_MERCADOS_TIME_ATIVOS=0"
            ),
        })
        _aplicar_politica_confirmacao(bilhete, aplicacao_automatica)
    return selecionados
