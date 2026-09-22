import time


class AgendadorColeta:
    def __init__(
        self,
        intervalo_rapido=240,
        intervalo_lento=360,
        odds_rapidas=600,
        odds_lentas=900,
        maximo_foco=3,
        intervalo_exploracao=3,
        intervalo_rechecagem_evento=120,
        usar_indicadores_lista=False,
        relogio=None,
    ):
        self.intervalo_rapido = intervalo_rapido
        self.intervalo_lento = intervalo_lento
        self.odds_rapidas = odds_rapidas
        self.odds_lentas = odds_lentas
        self.maximo_foco = max(int(maximo_foco), 1)
        self.intervalo_exploracao = max(int(intervalo_exploracao), 1)
        self.intervalo_rechecagem_evento = max(
            int(intervalo_rechecagem_evento), 1
        )
        self.usar_indicadores_lista = bool(usar_indicadores_lista)
        self.relogio = relogio or time.monotonic
        self.ultima_coleta = {}
        self.ultima_odds = {}
        self.ciclos_com_disputa = 0

    @staticmethod
    def _pontuar_indicadores_lista(jogo):
        """Resume o radar da lista; nunca substitui a leitura detalhada."""
        campos = ((jogo or {}).get("indicadores_lista") or {}).get("campos")
        if not isinstance(campos, dict):
            return 0.0

        def valores(*chaves):
            resultado = []
            for chave in chaves:
                campo = campos.get(chave) or {}
                for lado in ("casa", "visitante"):
                    try:
                        valor = float(campo.get(lado))
                    except (TypeError, ValueError):
                        continue
                    if valor >= 0:
                        resultado.append(valor)
            return resultado

        pressao = valores(
            "indice_de_pressao_ult_5_minutos",
            "indice_de_pressao_ult_10_minutos",
        )
        exg = valores(
            "expectativa_de_gols_para_os_proximos_5_minutos",
            "expectativa_de_gols_para_os_proximos_10_minutos",
        )
        chutes_gol = valores(
            "chutes_no_gol_ult_5_minutos",
            "chutes_no_gol_ult_10_minutos",
        )
        chutes = valores(
            "total_chutes_ult_5_minutos",
            "total_chutes_ult_10_minutos",
        )
        perigosos = valores(
            "ataques_perigosos_ult_5_minutos",
            "ataques_perigosos_ult_10_minutos",
        )
        cantos = valores(
            "escanteios_ult_5_minutos",
            "escanteios_ult_10_minutos",
        )
        exc = valores(
            "expectativa_de_escanteios_para_os_proximos_5_minutos",
            "expectativa_de_escanteios_para_os_proximos_10_minutos",
        )
        pontos = 0.0
        if pressao:
            pontos += min(max(pressao), 100.0) * 0.40
        if exg:
            pontos += min(max(exg), 2.0) * 10.0
        if chutes_gol:
            pontos += min(max(chutes_gol), 5.0) * 3.0
        if chutes:
            pontos += min(max(chutes), 10.0) * 1.0
        if perigosos:
            pontos += min(max(perigosos), 20.0) * 0.35
        if cantos:
            pontos += min(max(cantos), 5.0) * 1.2
        if exc:
            pontos += min(max(exc), 2.0) * 1.0
        return round(min(pontos, 100.0), 2)

    def planejar(
        self, jogos, pontuacoes=None, rechecagens_pos_evento=None,
        acompanhamentos_preco=None,
    ):
        agora = self.relogio()
        pontuacoes = pontuacoes or {}
        rechecagens_pos_evento = set(rechecagens_pos_evento or ())
        acompanhamentos_preco = acompanhamentos_preco or {}
        acompanhamentos_preco_pendentes = set()
        dados_acompanhamentos_preco = {}
        for url, dados_alerta in acompanhamentos_preco.items():
            dados_alerta = (
                dict(dados_alerta)
                if isinstance(dados_alerta, dict)
                else {"idade_segundos": dados_alerta}
            )
            try:
                idade_alerta = float(dados_alerta.get("idade_segundos"))
            except (TypeError, ValueError):
                continue
            if not 120 <= idade_alerta <= 600:
                continue
            instante_alerta = agora - idade_alerta
            alvo_pos_alerta = instante_alerta + 120
            ultima_odd = self.ultima_odds.get(url)
            if ultima_odd is None or ultima_odd < alvo_pos_alerta:
                acompanhamentos_preco_pendentes.add(url)
                dados_acompanhamentos_preco[url] = dados_alerta
        urls_foco = {
            jogo["url"]
            for jogo in sorted(
                jogos,
                key=lambda item: (
                    item["url"] in acompanhamentos_preco_pendentes,
                    item["url"] in rechecagens_pos_evento,
                    float(pontuacoes.get(item["url"]) or 0),
                ),
                reverse=True,
            )[:self.maximo_foco]
            if (
                float(pontuacoes.get(jogo["url"]) or 0) >= 60
                or jogo["url"] in rechecagens_pos_evento
                or jogo["url"] in acompanhamentos_preco_pendentes
            )
        }
        tarefas = []
        for jogo in jogos:
            url = jogo["url"]
            pontuacao = float(pontuacoes.get(url) or 0)
            rechecagem_pos_evento = url in rechecagens_pos_evento
            acompanhamento_preco = (
                url in acompanhamentos_preco_pendentes
            )
            pre_live_confirmado = bool(
                jogo.get("pre_live_confirmado") is True
            )
            rapido_fluxo_normal = (
                pontuacao >= 60
                or rechecagem_pos_evento
                or pre_live_confirmado
            )
            rapido = rapido_fluxo_normal or acompanhamento_preco
            intervalo_normal = (
                self.intervalo_rapido
                if rapido_fluxo_normal else self.intervalo_lento
            )
            ultima = self.ultima_coleta.get(url)
            idade = None if ultima is None else max(agora - ultima, 0)
            devido_fluxo_normal = bool(
                ultima is None or idade >= intervalo_normal
            )
            intervalo = (
                min(
                    intervalo_normal,
                    self.intervalo_rechecagem_evento,
                )
                if (rechecagem_pos_evento or acompanhamento_preco)
                else intervalo_normal
            )
            if idade is not None and idade < intervalo:
                continue

            intervalo_odds = self.odds_rapidas if rapido else self.odds_lentas
            ultima_odd = self.ultima_odds.get(url)
            coletar_odds = (
                rechecagem_pos_evento
                or acompanhamento_preco
                or ultima_odd is None
                or agora - ultima_odd >= intervalo_odds
            )
            tarefas.append(
                {
                    "jogo": jogo,
                    "prioridade": "rapida" if rapido else "lenta",
                    "em_foco": url in urls_foco,
                    "rechecagem_pos_evento": rechecagem_pos_evento,
                    "acompanhamento_preco": acompanhamento_preco,
                    "acompanhamento_preco_dados": (
                        dados_acompanhamentos_preco.get(url)
                        if acompanhamento_preco else None
                    ),
                    "somente_acompanhamento_preco": bool(
                        acompanhamento_preco
                        and not devido_fluxo_normal
                        and not rechecagem_pos_evento
                    ),
                    "coletar_odds": coletar_odds,
                    "pontuacao_anterior": pontuacao,
                    "scanner_prioritario": bool(
                        jogo.get("scanner_prioritario") is True
                    ),
                    "pre_live_prioritario": bool(
                        jogo.get("pre_live_prioritario") is True
                    ),
                    "pre_live_confirmado": pre_live_confirmado,
                    "pontuacao_indicadores_lista": (
                        self._pontuar_indicadores_lista(jogo)
                        if self.usar_indicadores_lista else 0.0
                    ),
                    "idade_segundos": idade,
                    "atraso_segundos": (
                        None if idade is None else max(idade - intervalo, 0)
                    ),
                    "urgencia": (
                        float("inf") if idade is None else idade / intervalo
                    ),
                }
            )

        tarefas.sort(
            key=lambda item: (
                not item["acompanhamento_preco"],
                not item["em_foco"],
                not item["pre_live_confirmado"],
                not item["scanner_prioritario"],
                -item["pontuacao_indicadores_lista"],
                not item["pre_live_prioritario"],
                item["idade_segundos"] is not None,
                -item["urgencia"],
                item["prioridade"] != "rapida",
                -item["pontuacao_anterior"],
            )
        )
        # O Scanner e radar, nao barreira. Quando as duas populacoes estao
        # disponiveis, preserva uma vaga inicial para a lista Ao Vivo geral.
        # Isso permite descobrir oportunidades sustentadas por outros dados
        # mesmo com pressao abaixo do corte configurado no Scanner.
        janela_inicial = min(self.maximo_foco + 1, len(tarefas))
        scanner_disponivel = any(
            item["scanner_prioritario"] for item in tarefas
        )
        controle_fora_scanner = next(
            (
                item for item in tarefas[janela_inicial:]
                if not item["scanner_prioritario"]
            ),
            None,
        )
        if (
            scanner_disponivel
            and controle_fora_scanner is not None
            and janela_inicial > 0
            and all(
                item["scanner_prioritario"]
                for item in tarefas[:janela_inicial]
            )
        ):
            tarefas.remove(controle_fora_scanner)
            tarefas.insert(janela_inicial - 1, controle_fora_scanner)
        # A lista pré-live não toma toda a fila do Scanner. Ainda assim, ao
        # menos um jogo publicado recebe vaga na primeira janela de detalhes,
        # evitando que uma seleção já estudada só seja aberta tarde demais.
        pre_live_fora_janela = next(
            (
                item for item in tarefas[janela_inicial:]
                if item["pre_live_prioritario"]
            ),
            None,
        )
        if (
            pre_live_fora_janela is not None
            and janela_inicial > 0
            and not any(
                item["pre_live_prioritario"]
                for item in tarefas[:janela_inicial]
            )
        ):
            tarefas.remove(pre_live_fora_janela)
            tarefas.insert(janela_inicial - 1, pre_live_fora_janela)
        foco = [item for item in tarefas if item["em_foco"]]
        exploracao = [item for item in tarefas if not item["em_foco"]]
        if foco and exploracao:
            self.ciclos_com_disputa += 1
            if self.ciclos_com_disputa % self.intervalo_exploracao == 0:
                # Em ciclos congestionados pode existir vaga para apenas uma
                # navegação. Reservar periodicamente a primeira posição evita
                # que jogos novos fiquem invisíveis sem abandonar o foco.
                escolhido = exploracao[0]
                tarefas.remove(escolhido)
                tarefas.insert(0, escolhido)
        return tarefas

    def restaurar(self, estado_por_url):
        """Reconstrói relógios monotônicos a partir de idades persistidas."""
        agora = self.relogio()
        restauradas = 0
        odds_restauradas = 0
        for url, estado in (estado_por_url or {}).items():
            if url not in self.ultima_coleta:
                try:
                    idade = max(float(estado.get("idade_coleta")), 0.0)
                except (AttributeError, TypeError, ValueError):
                    idade = None
                if idade is not None:
                    self.ultima_coleta[url] = agora - idade
                    restauradas += 1
            if url not in self.ultima_odds:
                try:
                    idade_odds = max(
                        float(estado.get("idade_odds")), 0.0
                    )
                except (AttributeError, TypeError, ValueError):
                    idade_odds = None
                if idade_odds is not None:
                    self.ultima_odds[url] = agora - idade_odds
                    odds_restauradas += 1
        return {
            "coletas_restauradas": restauradas,
            "odds_restauradas": odds_restauradas,
        }

    def concluir(self, tarefa, odds_coletadas=None):
        agora = self.relogio()
        url = tarefa["jogo"]["url"]
        self.ultima_coleta[url] = agora
        if odds_coletadas is None:
            odds_coletadas = tarefa["coletar_odds"]
        if odds_coletadas:
            self.ultima_odds[url] = agora
