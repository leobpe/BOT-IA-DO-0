import re
import json
import statistics
import unicodedata


def _id_time(item):
    return ((item or {}).get("team") or {}).get("id")


def _normalizar_nome_mercado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texto.lower()).split())


def _numero_odd(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if 1.0 < numero <= 1000 else None


def _linha_total(valor, nome_aposta):
    handicap = valor.get("handicap")
    if handicap is not None and not isinstance(handicap, bool):
        try:
            linha = float(str(handicap).replace(",", "."))
        except (TypeError, ValueError):
            linha = None
        if linha is not None and linha >= 0:
            return linha
    for texto in (valor.get("value"), nome_aposta):
        encontrado = re.search(
            r"(?:over|under|mais de|menos de)?\s*"
            r"(\d+(?:[.,]\d+)?)",
            str(texto or ""),
            re.IGNORECASE,
        )
        if encontrado:
            return float(encontrado.group(1).replace(",", "."))
    return None


def _classificar_total_pre_jogo(nome):
    normalizado = _normalizar_nome_mercado(nome)
    palavras_excluidas = (
        "first half", "second half", "1st half", "2nd half",
        "home", "away", "team", "exact", "range", "odd even",
        "winner", "handicap", "shot", "kick", "goal minute",
        "goal method", "goalscorer",
    )
    if any(termo in normalizado for termo in palavras_excluidas):
        return None
    formato_total = (
        "over under" in normalizado
        or "total" in normalizado
        or normalizado in ("asian corners", "match goals")
    )
    if not formato_total:
        return None
    if "corner" in normalizado:
        return "escanteios_ft"
    if "goal" in normalizado:
        return "gols_ft"
    return None


def _lado_total(valor):
    selecao = _normalizar_nome_mercado(valor)
    if selecao == "over" or selecao.startswith("over "):
        return "over"
    if selecao == "under" or selecao.startswith("under "):
        return "under"
    return None


def _oferta_central_aposta(aposta):
    nome = str(aposta.get("name") or "")
    por_linha = {}
    for valor in aposta.get("values") or []:
        if not isinstance(valor, dict) or valor.get("suspended") is True:
            continue
        lado = _lado_total(valor.get("value"))
        linha = _linha_total(valor, nome)
        odd = _numero_odd(valor.get("odd"))
        if lado is None or linha is None or odd is None:
            continue
        oferta = por_linha.setdefault(
            linha,
            {"linha": linha, "over": None, "under": None, "principal": False},
        )
        oferta[lado] = odd
        oferta["principal"] = bool(
            oferta["principal"] or valor.get("main") is True
        )
    completas = [
        oferta for oferta in por_linha.values()
        if oferta["over"] is not None and oferta["under"] is not None
    ]
    if not completas:
        return None

    def chave(oferta):
        equilibrio = abs(1 / oferta["over"] - 1 / oferta["under"])
        return (not oferta["principal"], equilibrio, oferta["linha"])

    return min(completas, key=chave)


def _resumir_consenso_odds(ofertas, mercado):
    por_casa = {}
    for oferta in ofertas:
        chave = str(oferta.get("bookmaker_id") or oferta["bookmaker"])
        atual = por_casa.get(chave)
        if atual is None:
            por_casa[chave] = oferta
            continue
        equilibrio_atual = abs(1 / atual["over"] - 1 / atual["under"])
        equilibrio_novo = abs(1 / oferta["over"] - 1 / oferta["under"])
        if (
            oferta.get("principal") and not atual.get("principal")
        ) or (
            oferta.get("principal") == atual.get("principal")
            and equilibrio_novo < equilibrio_atual
        ):
            por_casa[chave] = oferta
    selecionadas = list(por_casa.values())
    if not selecionadas:
        return {
            "estado": "ausente",
            "casas": 0,
            "consenso_suficiente": False,
            "linha_consenso": None,
            "odd_over_mediana": None,
            "odd_under_mediana": None,
            "probabilidade_over_sem_margem": None,
            "dispersao_linha": None,
            "evidencias": [],
        }
    linhas = [item["linha"] for item in selecionadas]
    probabilidades_over = [
        (1 / item["over"]) / (1 / item["over"] + 1 / item["under"])
        for item in selecionadas
    ]
    dispersao = max(linhas) - min(linhas)
    limite_dispersao = 1.0 if mercado == "gols_ft" else 2.0
    return {
        "estado": "disponivel",
        "casas": len(selecionadas),
        "consenso_suficiente": (
            len(selecionadas) >= 2 and dispersao <= limite_dispersao
        ),
        "linha_consenso": round(float(statistics.median(linhas)), 3),
        "odd_over_mediana": round(
            float(statistics.median(
                item["over"] for item in selecionadas
            )),
            3,
        ),
        "odd_under_mediana": round(
            float(statistics.median(
                item["under"] for item in selecionadas
            )),
            3,
        ),
        "probabilidade_over_sem_margem": round(
            float(statistics.median(probabilidades_over)), 4
        ),
        "dispersao_linha": round(float(dispersao), 3),
        "evidencias": [
            {
                "bookmaker_id": item.get("bookmaker_id"),
                "bookmaker": item["bookmaker"],
                "bet_id": item.get("bet_id"),
                "mercado": item["mercado"],
                "linha": item["linha"],
                "over": item["over"],
                "under": item["under"],
                "principal": bool(item.get("principal")),
            }
            for item in sorted(
                selecionadas,
                key=lambda item: (
                    str(item["bookmaker"]).casefold(), item["linha"]
                ),
            )[:20]
        ],
    }


def resumir_odds_pre_jogo(itens):
    ofertas = {"gols_ft": [], "escanteios_ft": []}
    atualizacoes = []
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        if item.get("update"):
            atualizacoes.append(str(item["update"]))
        for bookmaker in item.get("bookmakers") or []:
            if not isinstance(bookmaker, dict):
                continue
            nome_bookmaker = str(bookmaker.get("name") or "").strip()
            if not nome_bookmaker:
                continue
            for aposta in bookmaker.get("bets") or []:
                if not isinstance(aposta, dict):
                    continue
                mercado = _classificar_total_pre_jogo(aposta.get("name"))
                if mercado is None:
                    continue
                oferta = _oferta_central_aposta(aposta)
                if oferta is None:
                    continue
                ofertas[mercado].append({
                    **oferta,
                    "bookmaker_id": bookmaker.get("id"),
                    "bookmaker": nome_bookmaker,
                    "bet_id": aposta.get("id"),
                    "mercado": aposta.get("name"),
                })
    mercados = {
        mercado: _resumir_consenso_odds(itens_mercado, mercado)
        for mercado, itens_mercado in ofertas.items()
    }
    return {
        "versao": "odds-pre-jogo-consenso-v1",
        "modo": "sombra",
        "atualizado_em": max(atualizacoes) if atualizacoes else None,
        "mercados": mercados,
        "cobertura": {
            mercado: item["estado"] == "disponivel"
            for mercado, item in mercados.items()
        },
    }


def _resumir_forma(jogos, time_id):
    resumo = {
        "jogos": 0, "vitorias": 0, "empates": 0, "derrotas": 0,
        "gols_pro_media": None, "gols_contra_media": None,
        "pontos_por_jogo": None,
    }
    gols_pro = gols_contra = pontos = 0
    for item in jogos or []:
        times = item.get("teams") or {}
        gols = item.get("goals") or {}
        casa = (times.get("home") or {}).get("id") == time_id
        fora = (times.get("away") or {}).get("id") == time_id
        if not (casa or fora):
            continue
        pro = gols.get("home" if casa else "away")
        contra = gols.get("away" if casa else "home")
        if not isinstance(pro, (int, float)) or not isinstance(
            contra, (int, float)
        ):
            continue
        resumo["jogos"] += 1
        gols_pro += pro
        gols_contra += contra
        if pro > contra:
            resumo["vitorias"] += 1
            pontos += 3
        elif pro == contra:
            resumo["empates"] += 1
            pontos += 1
        else:
            resumo["derrotas"] += 1
    total = resumo["jogos"]
    if total:
        resumo["gols_pro_media"] = round(gols_pro / total, 3)
        resumo["gols_contra_media"] = round(gols_contra / total, 3)
        resumo["pontos_por_jogo"] = round(pontos / total, 3)
    return resumo


def _resumir_h2h(jogos, mandante_id, visitante_id):
    resumo = {
        "jogos": 0, "vitorias_mandante": 0, "empates": 0,
        "vitorias_visitante": 0, "media_gols": None,
        "taxa_over_1_5": None, "taxa_ambas_marcam": None,
    }
    gols_total = overs = ambas = 0
    for item in jogos or []:
        times = item.get("teams") or {}
        gols = item.get("goals") or {}
        casa_id = (times.get("home") or {}).get("id")
        fora_id = (times.get("away") or {}).get("id")
        casa_gols, fora_gols = gols.get("home"), gols.get("away")
        if (
            {casa_id, fora_id} != {mandante_id, visitante_id}
            or not isinstance(casa_gols, (int, float))
            or not isinstance(fora_gols, (int, float))
        ):
            continue
        resumo["jogos"] += 1
        gols_total += casa_gols + fora_gols
        overs += casa_gols + fora_gols > 1
        ambas += casa_gols > 0 and fora_gols > 0
        gols_mandante = casa_gols if casa_id == mandante_id else fora_gols
        gols_visitante = fora_gols if casa_id == mandante_id else casa_gols
        if gols_mandante > gols_visitante:
            resumo["vitorias_mandante"] += 1
        elif gols_mandante == gols_visitante:
            resumo["empates"] += 1
        else:
            resumo["vitorias_visitante"] += 1
    total = resumo["jogos"]
    if total:
        resumo["media_gols"] = round(gols_total / total, 3)
        resumo["taxa_over_1_5"] = round(overs / total, 3)
        resumo["taxa_ambas_marcam"] = round(ambas / total, 3)
    return resumo


def _resumir_escalacoes(itens, ids):
    por_time = {}
    for item in itens or []:
        time_id = _id_time(item)
        if time_id not in ids:
            continue
        titulares = []
        for entrada in item.get("startXI") or []:
            jogador = entrada.get("player") or {}
            titulares.append({
                "id": jogador.get("id"),
                "nome": jogador.get("name"),
                "posicao": jogador.get("pos"),
            })
        por_time[str(time_id)] = {
            "confirmada": len(titulares) >= 11,
            "formacao": item.get("formation"),
            "titulares": titulares,
        }
    return por_time


def _resumir_desfalques(itens, ids):
    por_time = {str(time_id): [] for time_id in ids}
    for item in itens or []:
        time_id = _id_time(item)
        if time_id not in ids:
            continue
        jogador = item.get("player") or {}
        por_time[str(time_id)].append({
            "id": jogador.get("id"),
            "nome": jogador.get("name"),
            "tipo": jogador.get("type"),
            "motivo": jogador.get("reason"),
        })
    return {
        time_id: {"total": len(jogadores), "jogadores": jogadores}
        for time_id, jogadores in por_time.items()
    }


def _resumir_estatisticas_temporada(estatisticas_times):
    def minutos_gols(bloco):
        resultado = {}
        for faixa, dados in ((bloco or {}).get("minute") or {}).items():
            if not isinstance(dados, dict):
                continue
            total = dados.get("total")
            percentual = dados.get("percentage")
            try:
                total = int(total) if total is not None else None
            except (TypeError, ValueError):
                total = None
            try:
                percentual = float(
                    str(percentual).strip().replace("%", "").replace(",", ".")
                ) if percentual is not None else None
            except (TypeError, ValueError):
                percentual = None
            if total is not None or percentual is not None:
                resultado[str(faixa)] = {
                    "total": total,
                    "percentual": percentual,
                }
        return resultado

    resumo = {}
    for lado, item in (estatisticas_times or {}).items():
        fixtures = item.get("fixtures") or {}
        gols = item.get("goals") or {}
        gols_pro = gols.get("for") or {}
        gols_contra = gols.get("against") or {}
        resumo[lado] = {
            "time_id": ((item.get("team") or {}).get("id")),
            "liga_id": ((item.get("league") or {}).get("id")),
            "temporada": item.get("season"),
            "jogos": ((fixtures.get("played") or {}).get("total")),
            "vitorias": ((fixtures.get("wins") or {}).get("total")),
            "empates": ((fixtures.get("draws") or {}).get("total")),
            "derrotas": ((fixtures.get("loses") or {}).get("total")),
            "gols_pro_media": (
                (gols_pro.get("average") or {}).get("total")
            ),
            "gols_contra_media": (
                (gols_contra.get("average") or {}).get("total")
            ),
            "gols_pro_por_minuto": minutos_gols(gols_pro),
            "gols_contra_por_minuto": minutos_gols(gols_contra),
            "sem_sofrer_gol": (
                (item.get("clean_sheet") or {}).get("total")
            ),
            "sem_marcar": (
                (item.get("failed_to_score") or {}).get("total")
            ),
        }
    return resumo


def _resumir_previsao(previsao):
    if not isinstance(previsao, dict):
        return None
    predicoes = previsao.get("predictions") or {}
    vencedor = predicoes.get("winner") or {}
    comparacao = previsao.get("comparison") or {}
    return {
        "vencedor_id": vencedor.get("id"),
        "vencedor_nome": vencedor.get("name"),
        "vencedor_comentario": vencedor.get("comment"),
        "vitoria_ou_empate": predicoes.get("win_or_draw"),
        "over_under": predicoes.get("under_over"),
        "gols_esperados": predicoes.get("goals") or {},
        "conselho_provedor": predicoes.get("advice"),
        "comparacao_percentual": {
            chave: valor
            for chave, valor in comparacao.items()
            if chave in {
                "form", "att", "def", "poisson", "h2h", "goals", "total"
            }
        },
    }


def _valor_estatistica(estatisticas, nome):
    valor = (estatisticas or {}).get(nome)
    if isinstance(valor, str):
        valor = valor.strip().replace("%", "")
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _estatisticas_por_time(item):
    return {
        ((time.get("team") or {}).get("id")): {
            estatistica.get("type"): estatistica.get("value")
            for estatistica in time.get("statistics") or []
            if estatistica.get("type")
        }
        for time in (item or {}).get("statistics") or []
        if ((time.get("team") or {}).get("id")) is not None
    }


def _resumir_historico_detalhado(itens, times):
    campos = {
        "escanteios": "Corner Kicks",
        "chutes": "Total Shots",
        "chutes_no_gol": "Shots on Goal",
        "xg": "expected_goals",
    }
    resumo = {}
    for lado, time_id in times.items():
        acumulado = {
            "jogos": 0,
            "gols_pro": [],
            "gols_contra": [],
            **{
                chave: []
                for campo in campos
                for chave in (campo, f"{campo}_contra")
            },
        }
        for item in itens or []:
            equipes = item.get("teams") or {}
            casa_id = ((equipes.get("home") or {}).get("id"))
            fora_id = ((equipes.get("away") or {}).get("id"))
            if time_id not in (casa_id, fora_id):
                continue
            gols = item.get("goals") or {}
            casa = time_id == casa_id
            gols_pro = gols.get("home" if casa else "away")
            gols_contra = gols.get("away" if casa else "home")
            if isinstance(gols_pro, (int, float)) and isinstance(
                gols_contra, (int, float)
            ):
                acumulado["jogos"] += 1
                acumulado["gols_pro"].append(float(gols_pro))
                acumulado["gols_contra"].append(float(gols_contra))
            estatisticas_partida = _estatisticas_por_time(item)
            estatisticas = estatisticas_partida.get(time_id) or {}
            adversario_id = fora_id if casa else casa_id
            estatisticas_adversario = (
                estatisticas_partida.get(adversario_id) or {}
            )
            for campo, nome_api in campos.items():
                valor = _valor_estatistica(estatisticas, nome_api)
                if valor is not None:
                    acumulado[campo].append(valor)
                valor_contra = _valor_estatistica(
                    estatisticas_adversario, nome_api
                )
                if valor_contra is not None:
                    acumulado[f"{campo}_contra"].append(valor_contra)
        resumo_lado = {"jogos": acumulado.pop("jogos")}
        for campo, valores in acumulado.items():
            resumo_lado[f"{campo}_media"] = (
                round(sum(valores) / len(valores), 3)
                if valores else None
            )
            resumo_lado[f"{campo}_amostra"] = len(valores)
        resumo[lado] = resumo_lado
    return resumo


def _linhas_classificacao(itens):
    linhas = []
    for item in itens or []:
        liga = item.get("league") or {}
        for grupo in liga.get("standings") or []:
            if isinstance(grupo, list):
                linhas.extend(grupo)
    return linhas


def _resumir_classificacao(itens, times):
    por_id = {
        ((linha.get("team") or {}).get("id")): linha
        for linha in _linhas_classificacao(itens)
    }
    resumo = {}
    for lado, time_id in times.items():
        linha = por_id.get(time_id)
        if not linha:
            continue
        geral = linha.get("all") or {}
        gols = geral.get("goals") or {}
        resumo[lado] = {
            "time_id": time_id,
            "posicao": linha.get("rank"),
            "pontos": linha.get("points"),
            "saldo_gols": linha.get("goalsDiff"),
            "forma": linha.get("form"),
            "descricao": linha.get("description"),
            "jogos": geral.get("played"),
            "vitorias": geral.get("win"),
            "empates": geral.get("draw"),
            "derrotas": geral.get("lose"),
            "gols_pro": gols.get("for"),
            "gols_contra": gols.get("against"),
        }
    return resumo


def resumir_estatisticas_api_ao_vivo(estatisticas, confirmacao):
    times = (confirmacao or {}).get("times") or {}
    ids = {
        "mandante": ((times.get("home") or {}).get("id")),
        "visitante": ((times.get("away") or {}).get("id")),
    }
    por_time = {
        ((item.get("team") or {}).get("id")): {
            estatistica.get("type"): estatistica.get("value")
            for estatistica in item.get("statistics") or []
            if estatistica.get("type")
        }
        for item in estatisticas or []
    }
    mapeamento = {
        "chutes_no_gol": "Shots on Goal",
        "chutes_fora": "Shots off Goal",
        "chutes": "Total Shots",
        "chutes_bloqueados": "Blocked Shots",
        "chutes_dentro_area": "Shots insidebox",
        "chutes_fora_area": "Shots outsidebox",
        "faltas": "Fouls",
        "escanteios": "Corner Kicks",
        "impedimentos": "Offsides",
        "posse": "Ball Possession",
        "cartoes_amarelos": "Yellow Cards",
        "cartoes_vermelhos": "Red Cards",
        "defesas_goleiro": "Goalkeeper Saves",
        "passes": "Total passes",
        "passes_certos": "Passes accurate",
        "precisao_passes": "Passes %",
        "xg": "expected_goals",
    }
    resumo = {}
    for lado, time_id in ids.items():
        origem = por_time.get(time_id) or {}
        valores = {}
        for destino, nome_api in mapeamento.items():
            valor = _valor_estatistica(origem, nome_api)
            if valor is not None:
                valores[destino] = valor
        if valores:
            resumo[lado] = valores
    return {
        "versao": "estatisticas-live-api-v1",
        "times": resumo,
        "metricas_disponiveis": sorted({
            metrica for item in resumo.values() for metrica in item
        }),
    }


def resumir_jogadores_api_ao_vivo(itens, confirmacao):
    times = (confirmacao or {}).get("times") or {}
    ids = {
        "mandante": ((times.get("home") or {}).get("id")),
        "visitante": ((times.get("away") or {}).get("id")),
    }
    por_id = {
        ((item.get("team") or {}).get("id")): item
        for item in itens or []
    }
    resumo = {}
    for lado, time_id in ids.items():
        jogadores = []
        totais = {
            "chutes": 0.0,
            "chutes_no_gol": 0.0,
            "passes_chave": 0.0,
            "gols": 0.0,
            "assistencias": 0.0,
        }
        for item in (por_id.get(time_id) or {}).get("players") or []:
            atleta = item.get("player") or {}
            estatistica = (item.get("statistics") or [{}])[0] or {}
            jogos = estatistica.get("games") or {}
            chutes = estatistica.get("shots") or {}
            passes = estatistica.get("passes") or {}
            gols = estatistica.get("goals") or {}
            nota = _valor_estatistica(
                {"rating": jogos.get("rating")}, "rating"
            )
            resumo_atleta = {
                "id": atleta.get("id"),
                "nome": atleta.get("name"),
                "posicao": jogos.get("position"),
                "minutos": jogos.get("minutes"),
                "nota": nota,
                "chutes": chutes.get("total"),
                "chutes_no_gol": chutes.get("on"),
                "passes_chave": passes.get("key"),
                "gols": gols.get("total"),
                "assistencias": gols.get("assists"),
            }
            if any(
                valor not in (None, 0, 0.0, "")
                for chave, valor in resumo_atleta.items()
                if chave not in ("id", "nome", "posicao")
            ):
                jogadores.append(resumo_atleta)
            for destino, valor in (
                ("chutes", chutes.get("total")),
                ("chutes_no_gol", chutes.get("on")),
                ("passes_chave", passes.get("key")),
                ("gols", gols.get("total")),
                ("assistencias", gols.get("assists")),
            ):
                numero = _valor_estatistica({"v": valor}, "v")
                totais[destino] += numero or 0.0
        destaques = sorted(
            jogadores,
            key=lambda jogador: (
                jogador.get("nota") is not None,
                jogador.get("nota") or 0,
                jogador.get("chutes_no_gol") or 0,
            ),
            reverse=True,
        )[:3]
        if jogadores:
            resumo[lado] = {
                "jogadores_com_dados": len(jogadores),
                "totais": {
                    chave: round(valor, 3)
                    for chave, valor in totais.items()
                },
                "destaques": destaques,
            }
    return {
        "versao": "jogadores-live-api-v1",
        "times": resumo,
    }


def resumir_eventos_api_ao_vivo(itens, confirmacao):
    times = (confirmacao or {}).get("times") or {}
    ids = {
        ((times.get("home") or {}).get("id")): "mandante",
        ((times.get("away") or {}).get("id")): "visitante",
    }
    resumo = {
        lado: {
            "gols": 0,
            "cartoes_amarelos": 0,
            "cartoes_vermelhos": 0,
            "substituicoes": 0,
            "var": 0,
        }
        for lado in ("mandante", "visitante")
    }
    criticos = []
    for item in itens or []:
        lado = ids.get(((item.get("team") or {}).get("id")))
        if lado is None:
            continue
        tipo = str(item.get("type") or "").lower()
        detalhe = str(item.get("detail") or "").lower()
        if tipo == "goal":
            resumo[lado]["gols"] += 1
        elif tipo == "card" and "red" in detalhe:
            resumo[lado]["cartoes_vermelhos"] += 1
        elif tipo == "card" and "yellow" in detalhe:
            resumo[lado]["cartoes_amarelos"] += 1
        elif tipo == "subst":
            resumo[lado]["substituicoes"] += 1
        elif tipo == "var":
            resumo[lado]["var"] += 1
        if tipo in ("goal", "card", "var"):
            tempo = item.get("time") or {}
            criticos.append({
                "lado": lado,
                "tipo": item.get("type"),
                "detalhe": item.get("detail"),
                "minuto": tempo.get("elapsed"),
                "acrescimos": tempo.get("extra"),
                "jogador": ((item.get("player") or {}).get("name")),
            })
    return {
        "versao": "eventos-live-api-v1",
        "times": resumo,
        "eventos_criticos_recentes": criticos[-10:],
    }


def resumir_contexto_pre_jogo(
    confirmacao, h2h=None, escalacoes=None, desfalques=None,
    forma_mandante=None, forma_visitante=None, estatisticas_times=None,
    previsao=None, classificacao=None, historico_detalhado=None,
    odds_pre_jogo=None,
):
    times = (confirmacao or {}).get("times") or {}
    mandante_id = ((times.get("home") or {}).get("id"))
    visitante_id = ((times.get("away") or {}).get("id"))
    ids = {valor for valor in (mandante_id, visitante_id) if valor is not None}
    resumo_odds_pre_jogo = resumir_odds_pre_jogo(odds_pre_jogo)
    return {
        "versao": "contexto-pre-jogo-v4",
        "modo": "sombra",
        "fixture_id": (confirmacao or {}).get("fixture_id"),
        "times": {
            "mandante_id": mandante_id,
            "visitante_id": visitante_id,
        },
        "forma_recente": {
            "mandante": _resumir_forma(forma_mandante, mandante_id),
            "visitante": _resumir_forma(forma_visitante, visitante_id),
        },
        "confrontos_diretos": _resumir_h2h(
            h2h, mandante_id, visitante_id
        ),
        "escalacoes": _resumir_escalacoes(escalacoes, ids),
        "desfalques": _resumir_desfalques(desfalques, ids),
        "estatisticas_temporada": _resumir_estatisticas_temporada(
            estatisticas_times
        ),
        "previsao_provedor": _resumir_previsao(previsao),
        "classificacao": _resumir_classificacao(
            classificacao,
            {"mandante": mandante_id, "visitante": visitante_id},
        ),
        "historico_detalhado": _resumir_historico_detalhado(
            historico_detalhado,
            {"mandante": mandante_id, "visitante": visitante_id},
        ),
        "odds_pre_jogo": resumo_odds_pre_jogo,
        "cobertura": {
            "forma_mandante": bool(forma_mandante),
            "forma_visitante": bool(forma_visitante),
            "h2h": bool(h2h),
            "escalacoes": bool(escalacoes),
            "desfalques": desfalques is not None,
            "estatisticas_temporada": bool(estatisticas_times),
            "previsao": bool(previsao),
            "classificacao": bool(classificacao),
            "historico_detalhado": bool(historico_detalhado),
            "odds_pre_jogo_gols": bool(
                resumo_odds_pre_jogo["cobertura"]["gols_ft"]
            ),
            "odds_pre_jogo_escanteios": bool(
                resumo_odds_pre_jogo["cobertura"]["escanteios_ft"]
            ),
        },
    }


def _par_packball(valor):
    numeros = re.findall(r"\d+(?:[.,]\d+)?", str(valor or ""))
    if len(numeros) < 2:
        return None
    return [float(numero.replace(",", ".")) for numero in numeros[:2]]


def comparar_estatisticas_ao_vivo(
    estatisticas_packball, estatisticas_api, confirmacao
):
    ids = [
        ((((confirmacao or {}).get("times") or {}).get(lado) or {}).get("id"))
        for lado in ("home", "away")
    ]
    api_por_time = {}
    for time in estatisticas_api or []:
        time_id = ((time.get("team") or {}).get("id"))
        api_por_time[time_id] = {
            item.get("type"): item.get("value")
            for item in time.get("statistics") or []
        }
    mapeamento = {
        "chutes": ("Chutes", "Total Shots", 2.0),
        "chutes_no_gol": ("Chutes no gol", "Shots on Goal", 1.0),
        "escanteios": ("Escanteios", "Corner Kicks", 1.0),
    }
    metricas = {}
    concordantes = divergentes = 0
    for nome, (campo_packball, campo_api, tolerancia) in mapeamento.items():
        packball = _par_packball(
            (estatisticas_packball or {}).get(campo_packball)
        )
        api = [
            api_por_time.get(time_id, {}).get(campo_api)
            for time_id in ids
        ]
        if (
            packball is None
            or any(not isinstance(valor, (int, float)) for valor in api)
        ):
            continue
        diferencas = [
            round(abs(packball[indice] - float(api[indice])), 3)
            for indice in range(2)
        ]
        concorda = max(diferencas) <= tolerancia
        concordantes += int(concorda)
        divergentes += int(not concorda)
        metricas[nome] = {
            "packball": packball,
            "api_football": [float(valor) for valor in api],
            "diferencas": diferencas,
            "concorda": concorda,
        }
    return {
        "versao": "comparacao-fontes-live-v1",
        "modo": "sombra",
        "metricas": metricas,
        "comparadas": len(metricas),
        "concordantes": concordantes,
        "divergentes": divergentes,
        "taxa_concordancia": (
            round(concordantes / len(metricas), 3) if metricas else None
        ),
    }


def resumir_cobertura_contexto(conexao, limite=100):
    linhas = conexao.execute(
        """
        SELECT contexto_api_json
        FROM snapshots
        WHERE contexto_api_json IS NOT NULL
          AND contexto_api_json NOT IN ('null', '{}')
        ORDER BY coletado_em DESC, id DESC
        LIMIT ?
        """,
        (int(limite),),
    ).fetchall()
    campos = (
        "forma_mandante", "forma_visitante", "h2h", "escalacoes",
        "desfalques", "estatisticas_temporada", "previsao",
        "classificacao", "historico_detalhado",
        "odds_pre_jogo_gols", "odds_pre_jogo_escanteios",
        "estatisticas_ao_vivo", "jogadores_ao_vivo",
        "eventos_ao_vivo",
    )
    totais = {campo: 0 for campo in campos}
    comparadas = concordantes = 0
    validos = 0
    versoes = {}
    for linha in linhas:
        try:
            item = json.loads(linha[0] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        versao = item.get("versao")
        if versao not in (
            "contexto-pre-jogo-v1",
            "contexto-pre-jogo-v2",
            "contexto-pre-jogo-v3",
            "contexto-pre-jogo-v4",
        ):
            continue
        validos += 1
        versoes[versao] = versoes.get(versao, 0) + 1
        cobertura = item.get("cobertura") or {}
        for campo in campos:
            totais[campo] += int(bool(cobertura.get(campo)))
        comparacao = item.get("comparacao_fontes_ao_vivo") or {}
        comparadas += int(comparacao.get("comparadas") or 0)
        concordantes += int(comparacao.get("concordantes") or 0)
    return {
        "versao": "contexto-pre-jogo-v4",
        "versoes_observadas": versoes,
        "modo": "sombra",
        "snapshots": validos,
        "cobertura": {
            campo: (round(total / validos, 3) if validos else None)
            for campo, total in totais.items()
        },
        "metricas_comparadas": comparadas,
        "taxa_concordancia_fontes": (
            round(concordantes / comparadas, 3) if comparadas else None
        ),
    }
