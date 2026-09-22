"""Catálogo pré-jogo Bet365 para o seletor pré-live.

O feed v4 da Bet365 expõe um catálogo muito maior que o contrato histórico da
API-Football. Este módulo preserva todos os mercados ativos para auditoria e
normaliza somente seleções que o modelo de placar consegue precificar e
liquidar sem ambiguidade.
"""

from __future__ import annotations

import math
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from betsapi import _odd_decimal, _resultado_lista, _similaridade


VERSAO = "betsapi-bet365-prelive-futuro-paginado-casa-canonica-v4"
BOOKMAKER = "Bet365"
FONTE = "betsapi_bet365"
MAXIMO_PAGINAS_PADRAO = 20
ITENS_POR_PAGINA_ESPERADOS = 50
MAXIMO_TRABALHADORES_PADRAO = 4


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


def _epoch_inicio(jogo):
    valor = (jogo or {}).get("inicio")
    try:
        return datetime.fromisoformat(
            str(valor).replace("Z", "+00:00")
        ).timestamp()
    except (TypeError, ValueError):
        return None


def _inteiro_ambiente(nome, padrao, minimo, maximo):
    try:
        valor = int(os.getenv(nome, str(padrao)))
    except (TypeError, ValueError):
        valor = int(padrao)
    return min(max(valor, minimo), maximo)


def _data_evento_local(evento, fuso):
    epoch = _numero((evento or {}).get("time"))
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(
            epoch, timezone.utc
        ).astimezone(fuso).date()
    except (OverflowError, OSError, ValueError):
        return None


def _evento_futuro_do_dia(evento, data_alvo, agora):
    epoch = _numero((evento or {}).get("time"))
    if epoch is None:
        return False, "horario_invalido"
    status = str((evento or {}).get("time_status") or "").strip()
    if status not in {"", "0"}:
        return False, "status_nao_futuro"
    if epoch < agora.timestamp() - 15 * 60:
        return False, "horario_passado"
    if _data_evento_local(evento, agora.tzinfo) != data_alvo:
        return False, "fora_data_alvo"
    liga = (evento or {}).get("league") or {}
    liga = liga.get("name") if isinstance(liga, dict) else liga
    liga_normalizada = _normalizar(liga)
    if any(
        marcador in liga_normalizada
        for marcador in ("esoccer", "e soccer", "ebasketball", "e basketball")
    ):
        return False, "esports"
    return True, None


def listar_eventos_bet365_pre_live(
    api, data_alvo, maximo_paginas=None, agora=None
):
    """Lista apenas eventos futuros do dia, com paginação ampla e limitada."""
    if not getattr(api, "ativa", False):
        return [], {
            "estado": "fonte_desativada", "eventos": 0, "paginas": 0,
            "versao": VERSAO,
        }
    if maximo_paginas is None:
        paginas = _inteiro_ambiente(
            "BETSAPI_PRELIVE_MAX_PAGINAS", MAXIMO_PAGINAS_PADRAO, 1, 20
        )
    else:
        paginas = min(max(int(maximo_paginas), 1), 20)
    trabalhadores = _inteiro_ambiente(
        "BETSAPI_PRELIVE_WORKERS", MAXIMO_TRABALHADORES_PADRAO, 1, 8
    )
    agora = agora or datetime.now().astimezone()
    if agora.tzinfo is None:
        agora = agora.astimezone()
    try:
        data_objeto = datetime.strptime(str(data_alvo), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return [], {
            "estado": "data_alvo_invalida", "eventos": 0, "paginas": 0,
            "versao": VERSAO,
        }
    dia = data_objeto.strftime("%Y%m%d")
    consulta_sem_historico = data_objeto == agora.date()

    def parametros_pagina(pagina):
        parametros = {
            "sport_id": 1,
            "page": pagina,
            "skip_esports": 1,
        }
        # O endpoint com `day=hoje` inclui os já encerrados desde 00:00.
        # Sem `day`, a própria fonte inicia nos próximos eventos.
        if not consulta_sem_historico:
            parametros["day"] = dia
        return parametros

    def carregar_pagina(pagina):
        resposta = api._requisitar(
            "v1/bet365/upcoming", parametros_pagina(pagina)
        )
        return pagina, resposta, _resultado_lista(resposta)

    def carregar():
        primeira_pagina, primeira_resposta, primeiros = carregar_pagina(1)
        if primeira_resposta is None:
            return None
        respostas = {primeira_pagina: primeiros}
        paginas_tentadas = 1
        paginas_falhas = 0
        total = ((primeira_resposta or {}).get("pager") or {}).get("total")
        try:
            paginas_total = math.ceil(int(total) / ITENS_POR_PAGINA_ESPERADOS)
        except (TypeError, ValueError):
            paginas_total = paginas
        limite_paginas = min(max(paginas_total, 1), paginas)
        if len(primeiros) >= ITENS_POR_PAGINA_ESPERADOS:
            restantes = list(range(2, limite_paginas + 1))
            for indice in range(0, len(restantes), trabalhadores):
                lote = restantes[indice:indice + trabalhadores]
                with ThreadPoolExecutor(max_workers=len(lote)) as executor:
                    futuros = {
                        executor.submit(carregar_pagina, pagina): pagina
                        for pagina in lote
                    }
                    for futuro in as_completed(futuros):
                        pagina = futuros[futuro]
                        paginas_tentadas += 1
                        try:
                            _, resposta, itens = futuro.result()
                        except Exception:
                            resposta, itens = None, []
                        if resposta is None:
                            paginas_falhas += 1
                        else:
                            respostas[pagina] = itens
                eventos_lote = [
                    evento
                    for pagina in lote
                    for evento in respostas.get(pagina, [])
                ]
                datas_lote = [
                    _data_evento_local(evento, agora.tzinfo)
                    for evento in eventos_lote
                ]
                # As páginas são cronológicas. Ao ultrapassar o dia-alvo,
                # continuar consumiria chamadas sem ampliar a cobertura.
                if (
                    eventos_lote
                    and all(data is not None for data in datas_lote)
                    and min(datas_lote) > data_objeto
                ):
                    break
                if any(
                    len(respostas.get(pagina, []))
                    < ITENS_POR_PAGINA_ESPERADOS
                    for pagina in lote if pagina in respostas
                ):
                    break
        encontrados = [
            evento
            for pagina in sorted(respostas)
            for evento in respostas[pagina]
        ]
        return {
            "eventos": encontrados,
            "paginas": len(respostas),
            "paginas_tentadas": paginas_tentadas,
            "paginas_falhas": paginas_falhas,
        }

    dados = api._cacheado(
        (
            "bet365_upcoming_pre_live_futuro_v2", dia, paginas,
            consulta_sem_historico,
        ),
        10 * 60,
        carregar,
    )
    if not dados:
        return [], {
            "estado": "pagina_indisponivel", "eventos": 0, "paginas": 0,
            "versao": VERSAO,
        }
    recebidos = list(dados.get("eventos") or [])
    eventos = []
    descartes = {}
    ids = set()
    for evento in recebidos:
        valido, motivo = _evento_futuro_do_dia(
            evento, data_objeto, agora
        )
        if not valido:
            descartes[motivo] = int(descartes.get(motivo, 0)) + 1
            continue
        evento_id = str(evento.get("id") or evento.get("FI") or "").strip()
        if not evento_id or evento_id in ids:
            descartes["duplicado_ou_sem_id"] = int(
                descartes.get("duplicado_ou_sem_id", 0)
            ) + 1
            continue
        ids.add(evento_id)
        eventos.append(evento)
    return eventos, {
        "estado": "catalogo_disponivel",
        "eventos": len(eventos),
        "paginas": int(dados.get("paginas") or 0),
        "paginas_tentadas": int(dados.get("paginas_tentadas") or 0),
        "paginas_falhas": int(dados.get("paginas_falhas") or 0),
        "eventos_recebidos": len(recebidos),
        "eventos_descartados": sum(descartes.values()),
        "descartes": descartes,
        "consulta": (
            "proximos_eventos_sem_historico"
            if consulta_sem_historico else "data_especifica"
        ),
        "versao": VERSAO,
    }


def parear_evento_bet365_pre_live(eventos, jogo):
    """Pareia por nomes e horário, recusando candidato ambíguo."""
    casa = (jogo or {}).get("mandante") or ""
    fora = (jogo or {}).get("visitante") or ""
    inicio = _epoch_inicio(jogo)
    candidatos = []
    for evento in eventos or []:
        casa_api = evento.get("home") or {}
        fora_api = evento.get("away") or {}
        casa_api = (
            casa_api.get("name") or casa_api.get("name_en") or ""
            if isinstance(casa_api, dict) else str(casa_api or "")
        )
        fora_api = (
            fora_api.get("name") or fora_api.get("name_en") or ""
            if isinstance(fora_api, dict) else str(fora_api or "")
        )
        direta = (_similaridade(casa, casa_api), _similaridade(fora, fora_api))
        inversa = (_similaridade(casa, fora_api), _similaridade(fora, casa_api))
        orientacao, par = (
            ("direta", direta) if sum(direta) >= sum(inversa)
            else ("invertida", inversa)
        )
        if min(par) < 0.76 or sum(par) / 2.0 < 0.84:
            continue
        inicio_api = _numero(evento.get("time"))
        diferenca = (
            abs(inicio - inicio_api)
            if inicio is not None and inicio_api is not None else None
        )
        if diferenca is None or diferenca > 6 * 60 * 60:
            continue
        nota = sum(par) / 2.0 - min(diferenca / (24 * 60 * 60), 0.25)
        candidatos.append((nota, diferenca, evento, orientacao, casa_api, fora_api))
    candidatos.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    if not candidatos:
        return None
    if len(candidatos) > 1 and candidatos[0][0] - candidatos[1][0] < 0.06:
        return None
    nota, diferenca, evento, orientacao, casa_api, fora_api = candidatos[0]
    evento_id = str(evento.get("id") or evento.get("FI") or "").strip()
    if not evento_id:
        return None
    return {
        "evento_id": evento_id,
        "orientacao": orientacao,
        "similaridade": round(nota, 4),
        "diferenca_inicio_segundos": round(diferenca, 1),
        "mandante_observado": casa_api,
        "visitante_observado": fora_api,
    }


def _iterar_grupos_catalogo(no, caminho=()):
    if isinstance(no, dict):
        mercados = no.get("sp")
        if isinstance(mercados, dict):
            for chave, mercado in mercados.items():
                if isinstance(mercado, dict):
                    yield caminho, str(chave), mercado
        for chave, valor in no.items():
            if chave != "sp":
                yield from _iterar_grupos_catalogo(valor, caminho + (str(chave),))
    elif isinstance(no, list):
        for indice, valor in enumerate(no):
            yield from _iterar_grupos_catalogo(valor, caminho + (str(indice),))


def carregar_catalogo_bet365_pre_live(api, pareamento):
    """Obtém e preserva todos os mercados ativos do evento pré-jogo."""
    evento_id = str((pareamento or {}).get("evento_id") or "").strip()
    if not evento_id:
        return {"mercados": []}, {"estado": "evento_nao_pareado"}
    resposta = api._cacheado(
        ("bet365_prematch_v4", evento_id), 5 * 60,
        lambda: api._requisitar(
            "v4/bet365/prematch", {"FI": evento_id}
        ),
    )
    resultados = _resultado_lista(resposta)
    evento = resultados[0] if resultados else None
    if not isinstance(evento, dict):
        return {"mercados": []}, {
            "estado": "prematch_indisponivel", "evento_id": evento_id,
        }

    por_chave = {}
    selecoes_ativas = 0
    for caminho, chave, grupo in _iterar_grupos_catalogo(evento):
        odds = []
        for item in grupo.get("odds") or []:
            if not isinstance(item, dict):
                continue
            odd = _odd_decimal(item.get("odds") or item.get("OD"))
            suspensa = str(
                item.get("suspended") or item.get("SU") or "0"
            ) == "1"
            if odd is None or suspensa:
                continue
            odds.append({
                "id": item.get("id") or item.get("ID"),
                "odd": odd,
                "nome": item.get("name") or item.get("NA"),
                "cabecalho": item.get("header"),
                "linha": item.get("handicap") or item.get("HA"),
                "intervalo": item.get("ED"),
            })
        if not odds:
            continue
        identidade = (
            chave, str(grupo.get("id") or ""),
            tuple(sorted(
                (str(item.get("id") or ""), item["odd"]) for item in odds
            )),
        )
        existente = por_chave.get(identidade)
        secao = caminho[0] if caminho else "outros"
        if existente is None:
            por_chave[identidade] = {
                "chave": chave,
                "id": grupo.get("id"),
                "nome": grupo.get("name") or chave,
                "secoes": [secao],
                "odds": odds,
            }
            selecoes_ativas += len(odds)
        elif secao not in existente["secoes"]:
            existente["secoes"].append(secao)
    mercados = list(por_chave.values())
    return {
        "versao": VERSAO,
        "fonte": FONTE,
        "bookmaker": BOOKMAKER,
        "evento_id": evento_id,
        "mercados": mercados,
    }, {
        "estado": "catalogo_coletado",
        "evento_id": evento_id,
        "mercados_ativos": len(mercados),
        "selecoes_ativas": selecoes_ativas,
    }


def _resultado_selecao(valor, jogo):
    normalizado = _normalizar(valor)
    if normalizado in {"1", "home", "mandante"}:
        return "mandante"
    if normalizado in {"2", "away", "visitante"}:
        return "visitante"
    if normalizado in {"x", "draw", "empate"}:
        return "empate"
    casa = (jogo or {}).get("mandante") or ""
    fora = (jogo or {}).get("visitante") or ""
    sim_casa = _similaridade(normalizado, casa)
    sim_fora = _similaridade(normalizado, fora)
    if max(sim_casa, sim_fora) < 0.76:
        return None
    return "mandante" if sim_casa >= sim_fora else "visitante"


def _ambas(valor):
    normalizado = _normalizar(valor)
    if normalizado in {"yes", "sim"}:
        return "sim"
    if normalizado in {"no", "nao"}:
        return "nao"
    return None


def _linha_sem_devolucao(valor):
    numero = _numero(valor)
    if numero is None:
        return None
    dobrado = numero * 2
    return numero if abs(dobrado - round(dobrado)) < 1e-9 and int(round(dobrado)) % 2 else None


def _intervalo(valor):
    encontrado = re.search(r"\b(\d+)\s*(?:-|to|a)\s*(\d+)\b", _normalizar(valor))
    if not encontrado:
        return None
    minimo, maximo = map(int, encontrado.groups())
    return (minimo, maximo) if 0 <= minimo <= maximo <= 12 else None


def extrair_ofertas_bet365_pre_live(catalogo, fixture_id, jogo):
    """Normaliza o subconjunto já precificável pelo modelo de placar."""
    evento_id = str((catalogo or {}).get("evento_id") or "")
    # A casa precisa manter a mesma identidade entre partidas para permitir
    # múltiplas reais. O FI continua preservado em evento_externo_id.
    bookmaker_id = "bet365"
    ofertas = []

    def adicionar(grupo, item, mercado, selecao, particionamento):
        ofertas.append({
            "fixture_id": int(fixture_id),
            "bookmaker_id": bookmaker_id,
            "bookmaker": BOOKMAKER,
            "bet_id": item.get("id"),
            "mercado_origem": grupo.get("nome") or grupo.get("chave"),
            "selecao_origem": item.get("nome"),
            "mercado": mercado,
            "selecao": selecao,
            "grupo_precificacao": particionamento,
            "odd": round(float(item["odd"]), 4),
            "fonte": FONTE,
            "evento_externo_id": evento_id,
        })

    for grupo in (catalogo or {}).get("mercados") or []:
        chave = _normalizar(grupo.get("chave")).replace(" ", "_")
        for item in grupo.get("odds") or []:
            if chave == "full_time_result":
                resultado = _resultado_selecao(item.get("nome"), jogo)
                if resultado:
                    adicionar(grupo, item, "resultado", resultado, "resultado")
            elif chave in {
                "goals_over/under", "goals_over_under",
                "alternative_total_goals", "goal_line",
            }:
                lado = _normalizar(item.get("cabecalho"))
                linha = _linha_sem_devolucao(item.get("nome") or item.get("linha"))
                if lado in {"over", "under"} and linha is not None:
                    adicionar(
                        grupo, item, "total_gols", f"{lado}_{linha:g}",
                        f"total_gols:{linha:g}",
                    )
            elif chave == "both_teams_to_score":
                ambas = _ambas(item.get("nome"))
                if ambas:
                    adicionar(grupo, item, "ambas_marcam", ambas, "ambas_marcam")
            elif chave == "result_/_total_goals" or chave == "result_total_goals":
                resultado = _resultado_selecao(item.get("nome"), jogo)
                lado = _normalizar(item.get("cabecalho"))
                linha = _linha_sem_devolucao(item.get("linha"))
                if resultado and lado in {"over", "under"} and linha is not None:
                    adicionar(
                        grupo, item, "resultado_mais_gols",
                        f"{resultado}|{lado}_{linha:g}",
                        f"resultado_mais_gols:{linha:g}",
                    )
            elif chave == "result/both_teams_to_score" or chave == "result_both_teams_to_score":
                texto = str(item.get("nome") or "")
                partes = re.split(r"\s*(?:&|/|\+)\s*", texto, maxsplit=1)
                resultado = _resultado_selecao(partes[0] if partes else texto, jogo)
                ambas = _ambas(partes[1]) if len(partes) == 2 else None
                if resultado and ambas:
                    adicionar(
                        grupo, item, "resultado_mais_ambas",
                        f"{resultado}|{ambas}", "resultado_mais_ambas",
                    )
            elif chave == "total_goals/both_teams_to_score" or chave == "total_goals_both_teams_to_score":
                texto = _normalizar(item.get("nome"))
                encontrado = re.search(
                    r"(over|under)\s+([0-9.]+)\s+(?:(?:&|and)\s+)?(yes|no)",
                    texto,
                )
                if encontrado:
                    lado, linha_texto, ambas_texto = encontrado.groups()
                    linha = _linha_sem_devolucao(linha_texto)
                    ambas = _ambas(ambas_texto)
                    if linha is not None and ambas:
                        adicionar(
                            grupo, item, "total_gols_mais_ambas",
                            f"{lado}_{linha:g}|{ambas}",
                            f"total_gols_mais_ambas:{linha:g}",
                        )
            elif chave == "match_goals_range":
                intervalo = _intervalo(item.get("intervalo"))
                if intervalo and _ambas(item.get("cabecalho")) == "sim":
                    adicionar(
                        grupo, item, "multigols",
                        f"de_{intervalo[0]}_a_{intervalo[1]}", "multigols",
                    )
            elif chave == "team_goals_range":
                intervalo = _intervalo(item.get("intervalo"))
                lado = _resultado_selecao(item.get("nome"), jogo)
                if (
                    intervalo and lado in {"mandante", "visitante"}
                    and _ambas(item.get("cabecalho")) == "sim"
                ):
                    adicionar(
                        grupo, item, "multigols_time",
                        f"{lado}|de_{intervalo[0]}_a_{intervalo[1]}",
                        f"multigols_time:{lado}",
                    )
            elif chave == "team_total_goals":
                # Na Bet365 o time vem no cabecalho (1/2) e a linha em HA,
                # por exemplo: header=2, handicap="Over 0.5". A linha 0.5
                # equivale exatamente a o time marcar ou nao marcar e deve
                # concorrer com o multigols 1-N como a opcao menos restritiva.
                lado = _resultado_selecao(item.get("cabecalho"), jogo)
                linha_texto = _normalizar(
                    item.get("linha") or item.get("nome")
                )
                encontrado = re.fullmatch(
                    r"(over|under)\s+([0-9.]+)", linha_texto
                )
                if lado in {"mandante", "visitante"} and encontrado:
                    direcao, valor = encontrado.groups()
                    linha = _numero(valor)
                    if linha is not None and abs(linha - 0.5) < 1e-9:
                        adicionar(
                            grupo,
                            item,
                            "time_marca_gol",
                            f"{lado}|{'sim' if direcao == 'over' else 'nao'}",
                            f"time_marca_gol:{lado}",
                        )

    unicas = {}
    for oferta in ofertas:
        chave = (
            oferta["fixture_id"], oferta["bookmaker_id"],
            oferta["mercado"], oferta["selecao"],
        )
        anterior = unicas.get(chave)
        if anterior is None or oferta["odd"] > anterior["odd"]:
            unicas[chave] = oferta
    return list(unicas.values())


def resumir_catalogo_bet365_pre_live(catalogos, ofertas_suportadas):
    nomes = {}
    selecoes = 0
    for catalogo in catalogos or []:
        for mercado in catalogo.get("mercados") or []:
            nome = str(mercado.get("nome") or mercado.get("chave") or "-")
            nomes[nome] = nomes.get(nome, 0) + 1
            selecoes += len(mercado.get("odds") or [])
    return {
        "versao": VERSAO,
        "eventos_catalogados": len(catalogos or []),
        "familias_distintas": len(nomes),
        "selecoes_ativas": selecoes,
        "ofertas_precificaveis": len(ofertas_suportadas or []),
        "familias": sorted(nomes),
        "politica": (
            "catalogo_completo; envio_somente_com_modelo_e_liquidacao"
        ),
        "rollback": "BETSAPI_PRELIVE_ATIVA=0",
    }
