import time

from controle_acesso_packball import PackBallBloqueadoError
from tendencias_packball_ligas import coletar_tendencias_packball_liga


URL_PARTIDAS = "https://packball.com/pt/matches"


class PackBallListaNaoValidadaError(RuntimeError):
    """A pagina abriu, mas nao comprovou a lista Ao Vivo."""


SCRIPT_JOGOS_AO_VIVO = r"""
(capturarIndicadores = false) => {
    const limpar = texto => (texto || "").replace(/\s+/g, " ").trim();
    const chave = texto => limpar(texto)
        .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
        .toLowerCase().replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "");
    const numero = texto => {
        const valor = limpar(texto).replace("%", "").replace(",", ".");
        return /^-?\d+(?:\.\d+)?$/.test(valor) ? Number(valor) : null;
    };
    const extrairIndicadores = linha => {
        if (!capturarIndicadores) return null;
        const cabecalho = document.querySelector("ul.header");
        if (!cabecalho) return null;
        const titulos = Array.from(cabecalho.children);
        const indiceOddsCabecalho = titulos.findIndex(
            el => el.classList.contains("odds-12")
        );
        const colunas = Array.from(linha.children);
        const indiceOddsLinha = colunas.findIndex(
            el => el.classList.contains("odds-12")
        );
        if (indiceOddsCabecalho < 0 || indiceOddsLinha < 0) return null;
        const cabecalhosMetricas = titulos.slice(indiceOddsCabecalho + 1);
        const colunasMetricas = colunas.slice(indiceOddsLinha + 1);
        const campos = {};
        for (let indice = 0; indice < cabecalhosMetricas.length; indice++) {
            const titulo = limpar(
                cabecalhosMetricas[indice]?.getAttribute("title")
            );
            const coluna = colunasMetricas[indice];
            if (!titulo || !coluna) continue;
            const container = coluna.querySelector(":scope > div");
            const lados = Array.from(container?.children || []).filter(
                el => el.tagName === "SPAN" && limpar(el.innerText) !== "-"
            );
            const casaBruto = limpar(lados[0]?.innerText);
            const visitanteBruto = limpar(lados[lados.length - 1]?.innerText);
            campos[chave(titulo)] = {
                titulo,
                bruto: limpar(coluna.innerText),
                casa: numero(casaBruto),
                visitante: numero(visitanteBruto),
                casa_bruto: casaBruto || null,
                visitante_bruto: visitanteBruto || null,
            };
        }
        return {
            versao: "packball-lista-indicadores-v1",
            campos,
            campos_disponiveis: Object.keys(campos).length,
            uso: "priorizacao_pre_detalhe",
            autoriza_sinal: false,
        };
    };
    const linhas = Array.from(document.querySelectorAll("ul.row"));
    const resultados = [];

    for (const linha of linhas) {
        const linkElemento = linha.querySelector(
            'a[href*="/match/"], a[href*="/link-game/"]'
        );
        if (!linkElemento) continue;

        const statusElemento = linha.querySelector(".blin [title]");
        const colunaStatus = linha.querySelector(".blin");
        const statusTitulo = limpar(statusElemento?.getAttribute("title"));
        const statusTexto = limpar(colunaStatus?.innerText);
        const textoStatus = (statusTitulo + " " + statusTexto).toLowerCase();
        const statusCompacto = statusTexto.trim();
        const terminou =
            textoStatus.includes("finalizado") ||
            textoStatus.includes("encerrado") ||
            textoStatus.includes("finished") ||
            textoStatus.includes("full time") ||
            textoStatus.includes("adiado") ||
            textoStatus.includes("atrasado") ||
            textoStatus.includes("mais tarde");
        const interrompido =
            textoStatus.includes("interrompido") ||
            textoStatus.includes("interrupted") ||
            textoStatus.includes("suspended");
        const foraRegulamentar =
            textoStatus.includes("prorrogação") ||
            textoStatus.includes("prorrogacao") ||
            textoStatus.includes("extra time") ||
            textoStatus.includes("pênaltis") ||
            textoStatus.includes("penaltis") ||
            textoStatus.includes("penalties") ||
            /(^|\s)(et|pen)\s*['’]?(\s|$)/i.test(statusTexto);
        const intervalo =
            textoStatus.includes("intervalo") ||
            textoStatus.includes("half time") ||
            textoStatus.trim() === "ht";
        const emAndamento =
            textoStatus.includes("ao vivo") ||
            textoStatus.includes("1º tempo") ||
            textoStatus.includes("2º tempo") ||
            textoStatus.includes("primeiro tempo") ||
            textoStatus.includes("segundo tempo") ||
            textoStatus.includes("first half") ||
            textoStatus.includes("second half") ||
            textoStatus.includes("live") ||
            /\d{1,3}(?:\(\d{1,2}\)|\+\d{1,2})?\s*['’]/.test(
                statusTexto
            ) ||
            /^\d{1,3}(?:\(\d{1,2}\)|\+\d{1,2})?$/.test(
                statusCompacto
            );
        // A SPA pode reduzir o contador antes de remover visualmente uma
        // linha encerrada. Mesmo na aba Ao Vivo, cada cartao precisa provar
        // que esta em andamento por minuto, intervalo ou rotulo live.
        if (terminou || interrompido || foraRegulamentar) continue;
        if (!intervalo && !emAndamento) continue;

        const indicadoresLista = extrairIndicadores(linha);
        const ligaElemento = linha.querySelector(
            'a[href*="/league/"][href*="/summary"]'
        );
        const jogo = {
            mandante: limpar(linha.querySelector(".team-home")?.innerText),
            visitante: limpar(linha.querySelector(".team-away")?.innerText),
            placar: limpar(linha.querySelector(".result-f")?.innerText),
            status: statusTitulo || statusTexto || "Ao vivo",
            url: new URL(
                linkElemento.getAttribute("href"), window.location.origin
            ).href,
            liga_url: ligaElemento ? new URL(
                ligaElemento.getAttribute("href"), window.location.origin
            ).href : null,
            liga_nome: limpar(ligaElemento?.innerText),
            texto_linha: limpar(linha.innerText)
        };
        if (indicadoresLista) jogo.indicadores_lista = indicadoresLista;
        resultados.push(jogo);
    }

    const unicos = [];
    const links = new Set();
    for (const jogo of resultados) {
        if (!links.has(jogo.url)) {
            links.add(jogo.url);
            unicos.push(jogo);
        }
    }
    return unicos;
}
"""


SCRIPT_DIAGNOSTICO_LISTA = r"""
() => ({
    linhas: document.querySelectorAll("ul.row").length,
    links_partidas: document.querySelectorAll(
        'a[href*="/match/"], a[href*="/link-game/"]'
    ).length,
    corpo_visivel: Boolean((document.body?.innerText || "").trim())
})
"""


SCRIPT_DIAGNOSTICO_STATUS_LISTA = r"""
() => {
    const limpar = texto => (texto || "").replace(/\s+/g, " ").trim();
    const excluidos = [];
    const linhasDiagnosticadas = [];
    let linhasComPartida = 0;
    let aoVivoTotal = 0;
    let intervaloTotal = 0;
    let finalizadosTotal = 0;
    let agendadosTotal = 0;
    let adiadosCanceladosTotal = 0;
    let statusNaoReconhecidoTotal = 0;
    let interrompidosTotal = 0;
    let foraRegulamentarTotal = 0;
    for (const linha of Array.from(document.querySelectorAll("ul.row"))) {
        const linkElemento = linha.querySelector(
            'a[href*="/match/"], a[href*="/link-game/"]'
        );
        if (!linkElemento) {
            continue;
        }
        linhasComPartida += 1;
        const statusElemento = linha.querySelector(".blin [title]");
        const colunaStatus = linha.querySelector(".blin");
        const colunaHorario = linha.querySelector(".col.time");
        const colunaResultado = linha.querySelector(".result-f");
        const titulo = limpar(statusElemento?.getAttribute("title"));
        const texto = limpar(colunaStatus?.innerText);
        const horario = limpar(colunaHorario?.innerText);
        const resultado = limpar(colunaResultado?.innerText);
        const combinado = (titulo + " " + texto).toLowerCase();
        const compacto = texto.trim();
        const linhaDiagnostico = motivo => ({
            url: new URL(
                linkElemento.getAttribute("href"), window.location.origin
            ).href,
            mandante: limpar(linha.querySelector(".team-home")?.innerText),
            visitante: limpar(linha.querySelector(".team-away")?.innerText),
            status_titulo: titulo,
            status_texto: texto,
            status_horario: horario,
            resultado_linha: resultado,
            motivo,
        });
        const possuiPlacar = /\d+\s*[-:]\s*\d+/.test(resultado);
        const confrontoNaoIniciado =
            !possuiPlacar &&
            (!resultado || /^(vs\.?|x|-)$/.test(resultado.toLowerCase()));
        const finalizado =
            combinado.includes("finalizado") ||
            combinado.includes("encerrado") ||
            combinado.includes("finished") ||
            combinado.includes("full time");
        const adiadoCancelado =
            combinado.includes("adiado") ||
            combinado.includes("atrasado") ||
            combinado.includes("mais tarde") ||
            combinado.includes("cancelado") ||
            combinado.includes("cancelled") ||
            combinado.includes("canceled") ||
            combinado.includes("postponed") ||
            combinado.includes("delayed") ||
            combinado.includes("abandoned");
        const agendado =
            combinado.includes("não iniciado") ||
            combinado.includes("nao iniciado") ||
            combinado.includes("not started") ||
            combinado.includes("agendado") ||
            combinado.includes("scheduled") ||
            combinado.includes("próximo") ||
            combinado.includes("proximo") ||
            combinado.includes("upcoming") ||
            /^\d{1,2}:\d{2}$/.test(compacto) ||
            /^\d{1,2}[\/.]\d{1,2}(?:[\/.]\d{2,4})?$/.test(compacto) ||
            (
                !texto && confrontoNaoIniciado &&
                /^\d{1,2}:\d{2}$/.test(horario)
            );
        const interrompido =
            combinado.includes("interrompido") ||
            combinado.includes("interrupted") ||
            combinado.includes("suspended");
        const foraRegulamentar =
            combinado.includes("prorrogação") ||
            combinado.includes("prorrogacao") ||
            combinado.includes("extra time") ||
            combinado.includes("pênaltis") ||
            combinado.includes("penaltis") ||
            combinado.includes("penalties") ||
            /(^|\s)(et|pen)\s*['’]?(\s|$)/i.test(texto);
        const intervalo =
            combinado.includes("intervalo") ||
            combinado.includes("half time") ||
            combinado.trim() === "ht";
        const emAndamento =
            combinado.includes("ao vivo") ||
            combinado.includes("1º tempo") ||
            combinado.includes("2º tempo") ||
            combinado.includes("primeiro tempo") ||
            combinado.includes("segundo tempo") ||
            combinado.includes("first half") ||
            combinado.includes("second half") ||
            combinado.includes("live") ||
            /\d{1,3}(?:\(\d{1,2}\)|\+\d{1,2})?\s*['’]/.test(texto) ||
            /^\d{1,3}(?:\(\d{1,2}\)|\+\d{1,2})?$/.test(compacto);
        if (finalizado) {
            finalizadosTotal += 1;
            linhasDiagnosticadas.push(linhaDiagnostico("finalizado"));
            continue;
        }
        if (adiadoCancelado) {
            adiadosCanceladosTotal += 1;
            linhasDiagnosticadas.push(
                linhaDiagnostico("adiado_cancelado")
            );
            continue;
        }
        if (agendado) {
            agendadosTotal += 1;
            linhasDiagnosticadas.push(linhaDiagnostico("agendado"));
            continue;
        }
        if (intervalo) {
            intervaloTotal += 1;
            aoVivoTotal += 1;
            linhasDiagnosticadas.push(linhaDiagnostico("intervalo"));
            continue;
        }
        if (emAndamento && !interrompido && !foraRegulamentar) {
            aoVivoTotal += 1;
            linhasDiagnosticadas.push(linhaDiagnostico("ao_vivo"));
            continue;
        }
        if (interrompido) interrompidosTotal += 1;
        if (foraRegulamentar) foraRegulamentarTotal += 1;
        if (!interrompido && !foraRegulamentar) {
            statusNaoReconhecidoTotal += 1;
        }
        const motivoExclusao = interrompido
            ? "interrompido"
            : foraRegulamentar
            ? "fora_tempo_regulamentar"
            : "status_nao_reconhecido";
        linhasDiagnosticadas.push(linhaDiagnostico(motivoExclusao));
        excluidos.push({
            status_titulo: titulo,
            status_texto: texto,
            status_horario: horario,
            resultado_linha: resultado,
            texto_linha: limpar(linha.innerText).slice(0, 180),
            classes_diretas: Array.from(linha.children)
                .map(elemento => limpar(String(elemento.className || "")))
                .filter(Boolean)
                .slice(0, 12),
            motivo: motivoExclusao,
        });
    }
    return {
        excluidos: excluidos.slice(0, 5),
        linhas_com_partida: linhasComPartida,
        ao_vivo_total: aoVivoTotal,
        intervalo_total: intervaloTotal,
        finalizados_total: finalizadosTotal,
        agendados_total: agendadosTotal,
        adiados_cancelados_total: adiadosCanceladosTotal,
        interrompidos_total: interrompidosTotal,
        fora_regulamentar_total: foraRegulamentarTotal,
        status_nao_reconhecido_total: statusNaoReconhecidoTotal,
        linhas_diagnosticadas: linhasDiagnosticadas.slice(0, 500),
        classificados_total:
            aoVivoTotal + finalizadosTotal + agendadosTotal +
            adiadosCanceladosTotal + interrompidosTotal +
            foraRegulamentarTotal + statusNaoReconhecidoTotal,
    };
}
"""


SCRIPT_DIAGNOSTICO_SCANNER = r"""
() => {
    const texto = (document.body?.innerText || "")
        .replace(/\s+/g, " ").trim();
    const correspondencia = texto.match(/(\d+)\s+Partidas? filtradas?/i);
    const aba = document.querySelector("li:has(i.filter)");
    return {
        painel_visivel: Boolean(correspondencia),
        contador_filtrado: correspondencia
            ? Number(correspondencia[1]) : null,
        aba_encontrada: Boolean(aba),
        classe_aba: String(aba?.className || ""),
    };
}
"""


SCRIPT_ESTATISTICAS = r"""
() => {
    const nomes = [
        "Chutes", "Chutes no gol", "Índice de pressão",
        "Escanteios", "Posse de bola", "Chutes dentro da área",
        "Chutes fora da área", "Chutes bloqueados",
        "Ataques perigosos", "Ataques"
    ];
    const limpar = texto => (texto || "").replace(/\s+/g, " ").trim();
    const elementos = Array.from(document.querySelectorAll("[title]"));
    const resultado = {};
    for (const nome of nomes) {
        const elemento = elementos.find(
            item => item.getAttribute("title") === nome
        );
        resultado[nome] = elemento ? limpar(elemento.innerText) : null;
    }
    const corpo = document.body.innerText || "";
    const liga = corpo.match(
        /([^\n:]{2,60}):\s*([^\n]{2,100}?)\s*-\s*Rodada\s*:/i
    );
    resultado._metadados = {
        pais: liga ? limpar(liga[1]) : null,
        liga: liga ? limpar(liga[2]) : null,
        placar: limpar(document.querySelector(".result-tab")?.innerText),
        status: limpar(document.querySelector(".status-tab")?.innerText)
    };
    return resultado;
}
"""


SCRIPT_ESTADO_PARTIDA = r"""
() => {
    const limpar = texto => (texto || "").replace(/\s+/g, " ").trim();
    const painel = document.querySelector(".result-game");
    const classes = String(painel?.className || "");
    const placar = limpar(document.querySelector(".result-tab")?.innerText);
    const statusMinuto = limpar(
        document.querySelector(".status-tab")?.innerText
    );
    const finalizado = /(^|\s)status-5(\s|$)/.test(classes);
    const eventosGols = Array.from(
        document.querySelectorAll('li[type="goal"] span[title^="Gol:"]')
    ).map((marcador, ordemDom) => {
        const titulo = marcador.getAttribute("title") || "";
        const minutoTexto = (
            titulo.match(/Gol:\s*([0-9]+(?:\+[0-9]+)?)/i) || []
        )[1];
        const estilo = marcador.parentElement?.getAttribute("style") || "";
        const topoTexto = (
            estilo.match(/--span-top:\s*(-?[0-9.]+)px/i) || []
        )[1];
        const topo = topoTexto == null ? null : Number(topoTexto);
        if (!minutoTexto || !Number.isFinite(topo) || topo === 0) return null;
        const partes = minutoTexto.split("+").map(Number);
        return {
            minuto: minutoTexto,
            minuto_ordenacao: partes[0] + ((partes[1] || 0) / 100),
            lado: topo < 0 ? "casa" : "visitante",
            ordem_dom: ordemDom,
            fonte: "packball_timeline"
        };
    }).filter(Boolean).sort((a, b) =>
        a.minuto_ordenacao - b.minuto_ordenacao || a.ordem_dom - b.ordem_dom
    );
    return {
        finalizado,
        placar,
        status_minuto: statusMinuto,
        classes_status: classes,
        texto_status: limpar(painel?.innerText),
        eventos_gols: eventosGols
    };
}
"""


def _aguardar_renderizacao(
    pagina, condicao_javascript, timeout_ms, fallback_ms
):
    """Prossegue cedo quando a SPA terminou; preserva o limite antigo."""
    esperar = getattr(pagina, "wait_for_function", None)
    if esperar is None:
        pagina.wait_for_timeout(fallback_ms)
        return False
    try:
        esperar(condicao_javascript, timeout=timeout_ms)
        return True
    except Exception:
        # O wait_for_function jÃ¡ consumiu o limite; a coleta parcial abaixo
        # continua sendo preferÃ­vel a adicionar outra espera fixa.
        return False


class ColetorPackBall:
    def __init__(
        self, url_partidas=URL_PARTIDAS, renovar_sessao=None,
        controle_acesso=None, usar_scanner_prioridade=False,
        capturar_indicadores_lista=False,
        aceitar_zero_sem_contador_confirmado=False,
        relogio=None,
    ):
        self.url_partidas = url_partidas
        self.renovar_sessao = renovar_sessao
        self.controle_acesso = controle_acesso
        self.usar_scanner_prioridade = bool(usar_scanner_prioridade)
        self.capturar_indicadores_lista = bool(capturar_indicadores_lista)
        self.aceitar_zero_sem_contador_confirmado = bool(
            aceitar_zero_sem_contador_confirmado
        )
        self.ultimo_diagnostico_lista = {}
        self._ultimo_diagnostico_virtualizacao = {}
        self._urls_ao_vivo_anteriores = None
        self._cache_tendencias_liga = {}
        self.relogio = relogio or time.monotonic
        self.ultimo_diagnostico_navegacao = {}

    def coletar_tendencias_gols_liga(self, pagina, jogo, periodo):
        return coletar_tendencias_packball_liga(
            pagina,
            jogo,
            periodo,
            controle_acesso=self.controle_acesso,
            cache=self._cache_tendencias_liga,
        )

    @staticmethod
    def _diagnostico_zero_sem_contador_confiavel(diagnostico):
        """Aceita zero apenas se cada linha possui estado não operacional."""
        if not isinstance(diagnostico, dict):
            return False
        linhas = int(diagnostico.get("linhas_com_partida") or 0)
        ao_vivo = int(diagnostico.get("ao_vivo_total") or 0)
        desconhecidos = int(
            diagnostico.get("status_nao_reconhecido_total") or 0
        )
        nao_operacionais = sum(
            int(diagnostico.get(campo) or 0)
            for campo in (
                "finalizados_total",
                "agendados_total",
                "adiados_cancelados_total",
                "interrompidos_total",
                "fora_regulamentar_total",
            )
        )
        return bool(
            linhas > 0
            and ao_vivo == 0
            and desconhecidos == 0
            and nao_operacionais == linhas
            and int(diagnostico.get("classificados_total") or 0) == linhas
        )

    @staticmethod
    def _mesclar_prioridade_scanner(jogos_ao_vivo, jogos_scanner):
        """Mantem cobertura completa e coloca o radar quente primeiro."""
        ao_vivo = {
            jogo.get("url"): dict(jogo)
            for jogo in (jogos_ao_vivo or []) if jogo.get("url")
        }
        scanner = {
            jogo.get("url"): dict(jogo)
            for jogo in (jogos_scanner or []) if jogo.get("url")
        }
        resultado = []
        for url, jogo in scanner.items():
            if url not in ao_vivo:
                # Scanner e somente prioridade. Uma linha que nao foi
                # confirmada na aba Ao Vivo nunca entra na fila operacional.
                continue
            jogo["scanner_prioritario"] = True
            jogo["origem_lista"] = "scanner+ao_vivo"
            resultado.append(jogo)
        for url, jogo in ao_vivo.items():
            if url in scanner:
                continue
            jogo["scanner_prioritario"] = False
            jogo["origem_lista"] = "ao_vivo"
            resultado.append(jogo)
        return resultado

    def _coletar_scanner_prioritario(self, pagina):
        diagnostico = {
            "habilitado": self.usar_scanner_prioridade,
            "estado": "desativado",
            "contador_filtrado": None,
            "jogos_extraidos": 0,
            "tentativas_abertura": 0,
        }
        if not self.usar_scanner_prioridade:
            return [], diagnostico
        try:
            aba = pagina.locator("li:has(i.filter):visible")
            if aba.count() != 1 or not aba.is_visible():
                diagnostico["estado"] = "aba_scanner_ausente"
                return [], diagnostico

            def abrir_e_confirmar(alvo, forcar=False):
                diagnostico["tentativas_abertura"] += 1
                alvo.click(timeout=5000, force=forcar)
                try:
                    pagina.wait_for_function(
                        """() => /\\d+\\s+Partidas? filtradas?/i.test(
                            (document.body?.innerText || "")
                                .replace(/\\s+/g, " ")
                        )""",
                        timeout=7000,
                    )
                except Exception:
                    # A confirmação abaixo decide o estado. O timeout apenas
                    # aciona a segunda tentativa, sem assumir que a SPA abriu.
                    pass
                return pagina.evaluate(SCRIPT_DIAGNOSTICO_SCANNER) or {}

            link = aba.locator("a")
            prova = abrir_e_confirmar(link)
            if prova.get("painel_visivel") is not True:
                # Em alguns carregamentos da SPA o primeiro clique no link é
                # absorvido pela lista virtualizada. Um clique forçado no
                # próprio item da aba recupera a navegação sem alterar filtros.
                prova = abrir_e_confirmar(aba, forcar=True)
            diagnostico.update(prova)
            if prova.get("painel_visivel") is not True:
                diagnostico["estado"] = "painel_scanner_nao_validado"
                return [], diagnostico
            contador = prova.get("contador_filtrado")
            try:
                contador = max(int(contador), 0)
            except (TypeError, ValueError):
                diagnostico["estado"] = "contador_scanner_invalido"
                return [], diagnostico
            if contador > 0:
                try:
                    pagina.wait_for_function(
                        """() => document.querySelectorAll(
                            'ul.row a[href*="/match/"], '
                            + 'ul.row a[href*="/link-game/"]'
                        ).length > 0""",
                        timeout=7000,
                    )
                except Exception:
                    # O coletor abaixo confirma a lista; esta espera serve
                    # apenas para não ler durante a troca de rota da SPA.
                    pass
            diagnostico["tentativas_extracao"] = 1
            try:
                jogos = self._coletar_lista_virtualizada(pagina, contador)
            except Exception:
                # A navegação do Scanner pode substituir o contexto JS uma
                # vez mesmo depois do título aparecer. Uma releitura curta é
                # segura e não provoca nova navegação no PackBall.
                diagnostico["tentativas_extracao"] = 2
                pagina.wait_for_timeout(1000)
                jogos = self._coletar_lista_virtualizada(pagina, contador)
            diagnostico.update({
                "estado": "prioridade_carregada",
                "contador_filtrado": contador,
                "jogos_extraidos": len(jogos),
                "lista_consistente": len(jogos) == contador,
            })
            return jogos, diagnostico
        except PackBallBloqueadoError:
            raise
        except Exception as erro:
            diagnostico.update({
                "estado": "fallback_ao_vivo",
                "erro": type(erro).__name__,
                "mensagem": " ".join(str(erro).split())[:300],
            })
            return [], diagnostico

    def _navegar(self, pagina, url):
        inicio = self.relogio()
        if self.controle_acesso is not None:
            self.controle_acesso.antes_navegacao()
        apos_controle = self.relogio()
        pagina.goto(url, wait_until="domcontentloaded", timeout=30000)
        apos_goto = self.relogio()
        if self.controle_acesso is not None:
            self.controle_acesso.validar_pagina(pagina)
        fim = self.relogio()
        self.ultimo_diagnostico_navegacao = {
            "versao": "diagnostico-navegacao-packball-v1",
            "controle_acesso_segundos": round(
                max(apos_controle - inicio, 0.0), 3
            ),
            "carregamento_dom_segundos": round(
                max(apos_goto - apos_controle, 0.0), 3
            ),
            "validacao_pagina_segundos": round(
                max(fim - apos_goto, 0.0), 3
            ),
            "total_segundos": round(max(fim - inicio, 0.0), 3),
            "altera_sinal": False,
        }

    def _coletar_lista_virtualizada(self, pagina, quantidade_esperada):
        encontrados = {}
        linhas_diagnosticadas = {}

        def acumular_diagnostico():
            try:
                diagnostico = (
                    pagina.evaluate(SCRIPT_DIAGNOSTICO_STATUS_LISTA) or {}
                )
            except Exception:
                return
            if not isinstance(diagnostico, dict):
                return
            for linha in diagnostico.get("linhas_diagnosticadas") or []:
                if not isinstance(linha, dict) or not linha.get("url"):
                    continue
                linhas_diagnosticadas[linha["url"]] = dict(linha)

        def acumular():
            for jogo in (
                pagina.evaluate(
                    SCRIPT_JOGOS_AO_VIVO,
                    self.capturar_indicadores_lista,
                ) or []
            ):
                if jogo.get("url"):
                    encontrados[jogo["url"]] = jogo
            acumular_diagnostico()

        acumular()
        mouse = getattr(pagina, "mouse", None)
        rolou = False
        sem_crescimento = 0
        # O PackBall virtualiza a lista. Doze passos cobriam cerca de 260
        # linhas, mas truncavam dias com mais de 300 jogos. O teto passa a
        # acompanhar o contador, continuando limitado e encerrando cedo assim
        # que toda a lista foi vista ou a página realmente estabilizou.
        quantidade_esperada = max(int(quantidade_esperada or 0), 0)
        maximo_passos = min(
            36,
            max(12, (quantidade_esperada + 14) // 15),
        )
        for _ in range(maximo_passos):
            if len(encontrados) >= quantidade_esperada or mouse is None:
                break
            quantidade_anterior = len(encontrados)
            mouse.wheel(0, 650)
            rolou = True
            pagina.wait_for_timeout(250)
            acumular()
            sem_crescimento = (
                sem_crescimento + 1
                if len(encontrados) == quantidade_anterior else 0
            )
            if sem_crescimento >= 5:
                break
        if mouse is not None and rolou:
            try:
                mouse.wheel(0, -100000)
            except Exception:
                # Restaurar a posição é cosmético; nunca descarte partidas
                # já coletadas por uma falha transitória nesse movimento.
                pass
        contagens = {}
        for linha in linhas_diagnosticadas.values():
            motivo = str(linha.get("motivo") or "status_nao_reconhecido")
            contagens[motivo] = contagens.get(motivo, 0) + 1
        ao_vivo_total = (
            contagens.get("ao_vivo", 0) + contagens.get("intervalo", 0)
        )
        motivos_excluidos = {
            "interrompido",
            "fora_tempo_regulamentar",
            "status_nao_reconhecido",
        }
        self._ultimo_diagnostico_virtualizacao = {
            "fonte": "rolagem_virtualizada_completa",
            "linhas_com_partida": len(linhas_diagnosticadas),
            "ao_vivo_total": ao_vivo_total,
            "intervalo_total": contagens.get("intervalo", 0),
            "finalizados_total": contagens.get("finalizado", 0),
            "agendados_total": contagens.get("agendado", 0),
            "adiados_cancelados_total": contagens.get(
                "adiado_cancelado", 0
            ),
            "interrompidos_total": contagens.get("interrompido", 0),
            "fora_regulamentar_total": contagens.get(
                "fora_tempo_regulamentar", 0
            ),
            "status_nao_reconhecido_total": contagens.get(
                "status_nao_reconhecido", 0
            ),
            "classificados_total": len(linhas_diagnosticadas),
            "excluidos": [
                linha for linha in linhas_diagnosticadas.values()
                if linha.get("motivo") in motivos_excluidos
            ][:10],
        }
        return list(encontrados.values())

    def buscar_jogos_ao_vivo(self, pagina):
        ultimo_diagnostico = None
        ultimo_erro = None
        leituras_tentativas = []
        primeira_confirmacao_zero = None
        for tentativa in range(2):
            try:
                resultado = self._buscar_jogos_ao_vivo_na_pagina(pagina)
            except Exception as erro:
                if isinstance(erro, PackBallBloqueadoError):
                    raise
                ultimo_erro = erro
                ultimo_diagnostico = {
                    "erro": type(erro).__name__,
                    "mensagem": str(erro)[:300],
                }
                leituras_tentativas.append({
                    "tentativa": tentativa + 1,
                    "estado": "erro",
                    **ultimo_diagnostico,
                })
                if tentativa == 0:
                    continue
                break
            if resultado["estado"] == "ok":
                jogos = resultado["jogos"]
                contador = resultado.get("contador_ao_vivo")
                urls_atuais = {
                    jogo.get("url") for jogo in jogos if jogo.get("url")
                }
                urls_anteriores = self._urls_ao_vivo_anteriores
                interrompidos_total = int(
                    resultado.get("interrompidos_total") or 0
                )
                fora_regulamentar_total = int(
                    resultado.get("fora_regulamentar_total") or 0
                )
                contador_efetivo = (
                    None
                    if contador is None
                    else max(
                        0,
                        contador
                        - interrompidos_total
                        - fora_regulamentar_total,
                    )
                )
                diferenca = (
                    None
                    if contador_efetivo is None
                    else contador_efetivo - len(jogos)
                )
                transicao_dinamica = bool(
                    tentativa == 1
                    and resultado.get("status_explicito") is True
                    and jogos
                    and diferenca is not None
                    and abs(diferenca) == 1
                )
                lista_consistente = bool(
                    contador is None
                    or contador_efetivo == len(jogos)
                    or transicao_dinamica
                )
                diagnostico_lista = {
                    "contador_ao_vivo": contador,
                    "jogos_extraidos": len(jogos),
                    "diferenca": diferenca,
                    "lista_consistente": lista_consistente,
                    "modo_confirmacao": (
                        "status_linhas"
                        if contador is None
                        else "transicao_dinamica_status_explicito"
                        if transicao_dinamica
                        else "contador_ao_vivo"
                    ),
                    "tentativas": tentativa + 1,
                    "entraram": (
                        None if urls_anteriores is None
                        else len(urls_atuais - urls_anteriores)
                    ),
                    "sairam": (
                        None if urls_anteriores is None
                        else len(urls_anteriores - urls_atuais)
                    ),
                }
                if contador is not None and (
                    interrompidos_total or fora_regulamentar_total
                ):
                    diagnostico_lista["contador_ao_vivo_efetivo"] = max(
                        0,
                        contador
                        - interrompidos_total
                        - fora_regulamentar_total,
                    )
                if interrompidos_total:
                    diagnostico_lista["jogos_interrompidos"] = (
                        interrompidos_total
                    )
                if fora_regulamentar_total:
                    diagnostico_lista["jogos_fora_tempo_regulamentar"] = (
                        fora_regulamentar_total
                    )
                if transicao_dinamica:
                    diagnostico_lista["transicao_dinamica"] = True
                    diagnostico_lista["diferenca_tolerada"] = diferenca
                status_excluidos = resultado.get("status_excluidos") or []
                if status_excluidos:
                    diagnostico_lista["status_excluidos"] = status_excluidos
                scanner = resultado.get("scanner")
                if (
                    isinstance(scanner, dict)
                    and scanner.get("habilitado") is True
                ):
                    diagnostico_lista["scanner"] = scanner
                leituras_tentativas.append({
                    "tentativa": tentativa + 1,
                    "contador_ao_vivo": contador,
                    "contador_ao_vivo_efetivo": contador_efetivo,
                    "jogos_extraidos": len(jogos),
                    "diferenca": diferenca,
                    "lista_consistente": lista_consistente,
                    "jogos_interrompidos": interrompidos_total,
                    "jogos_fora_tempo_regulamentar": (
                        fora_regulamentar_total
                    ),
                })
                if len(leituras_tentativas) > 1:
                    diagnostico_lista["leituras_tentativas"] = list(
                        leituras_tentativas
                    )
                if not lista_consistente and tentativa == 0:
                    # A SPA pode conservar linhas da renderizacao anterior
                    # por alguns segundos. Uma nova navegacao confirma se a
                    # diferenca era apenas transitoria; nunca liberamos o
                    # ciclo usando uma lista que ainda diverge do contador.
                    ultimo_diagnostico = diagnostico_lista
                    continue
                self.ultimo_diagnostico_lista = diagnostico_lista
                if not lista_consistente:
                    return jogos
                self._urls_ao_vivo_anteriores = urls_atuais
                return jogos
            if resultado["estado"] == "zero_sem_contador_candidato":
                diagnostico_zero = dict(resultado.get("diagnostico") or {})
                assinatura_zero = tuple(
                    int(diagnostico_zero.get(campo) or 0)
                    for campo in (
                        "linhas_com_partida",
                        "finalizados_total",
                        "agendados_total",
                        "adiados_cancelados_total",
                        "interrompidos_total",
                        "fora_regulamentar_total",
                    )
                )
                leituras_tentativas.append({
                    "tentativa": tentativa + 1,
                    "estado": resultado["estado"],
                    "assinatura": list(assinatura_zero),
                })
                ultimo_diagnostico = diagnostico_zero
                if tentativa == 0:
                    primeira_confirmacao_zero = assinatura_zero
                    continue
                if assinatura_zero == primeira_confirmacao_zero:
                    self.ultimo_diagnostico_lista = {
                        "contador_ao_vivo": None,
                        "jogos_extraidos": 0,
                        "diferenca": None,
                        "lista_consistente": True,
                        "modo_confirmacao": (
                            "status_linhas_zero_confirmado"
                        ),
                        "tentativas": 2,
                        "classificacao_status": diagnostico_zero,
                        "leituras_tentativas": list(leituras_tentativas),
                        "rollback": (
                            "PACKBALL_ZERO_SEM_CONTADOR_CONFIRMADO_ATIVO=0"
                        ),
                    }
                    self._urls_ao_vivo_anteriores = set()
                    return []
                continue
            ultimo_diagnostico = resultado.get("diagnostico")
            leituras_tentativas.append({
                "tentativa": tentativa + 1,
                "estado": resultado.get("estado"),
                "diagnostico": ultimo_diagnostico,
            })
            if tentativa == 0:
                continue
        detalhe = (
            f" Diagnóstico: {ultimo_diagnostico}."
            if ultimo_diagnostico else ""
        )
        raise PackBallListaNaoValidadaError(
            "Botão Ao Vivo não foi encontrado e a lista de partidas não "
            f"pôde ser validada no PackBall.{detalhe}"
        ) from ultimo_erro

    def _buscar_jogos_ao_vivo_na_pagina(self, pagina):
        self._navegar(pagina, self.url_partidas)
        # A lista cresce progressivamente; esperar o primeiro item faria o
        # monitor voltar a enxergar apenas parte dos jogos ao vivo.
        pagina.wait_for_timeout(7000)
        campo_login = pagina.locator('input[name="email"]')
        if campo_login.count() and campo_login.is_visible():
            if self.renovar_sessao is None:
                raise RuntimeError("Sessão do PackBall expirada.")
            self.renovar_sessao(pagina)
            self._navegar(pagina, self.url_partidas)
            pagina.wait_for_timeout(5000)
        botao = pagina.locator("span.count-live:visible")
        if botao.count() != 1:
            jogos = pagina.evaluate(SCRIPT_JOGOS_AO_VIVO, False) or []
            if jogos:
                return {
                    "estado": "ok", "jogos": jogos,
                    "contador_ao_vivo": None,
                    "status_explicito": True,
                }
            diagnostico = pagina.evaluate(SCRIPT_DIAGNOSTICO_LISTA) or {}
            diagnostico_status = (
                pagina.evaluate(SCRIPT_DIAGNOSTICO_STATUS_LISTA) or {}
            )
            if isinstance(diagnostico_status, dict):
                diagnostico = {**diagnostico, **diagnostico_status}
            if (
                self.aceitar_zero_sem_contador_confirmado
                and self._diagnostico_zero_sem_contador_confiavel(
                    diagnostico
                )
            ):
                return {
                    "estado": "zero_sem_contador_candidato",
                    "diagnostico": {
                        **diagnostico,
                        "motivo": "zero_sem_contador_classificado",
                    },
                }
            # Links de partidas provam apenas que a pagina geral carregou;
            # nao provam que a aba Ao Vivo esteja vazia. Zero somente e
            # confiavel quando o contador existe e mostra explicitamente 0.
            # Sem contador nem linhas com status ao vivo, uma segunda leitura
            # e obrigatoria e o ciclo permanece fail-closed se ela falhar.
            if diagnostico.get("links_partidas", 0) > 0:
                diagnostico = {
                    **diagnostico,
                    "motivo": "contador_ao_vivo_ausente",
                }
            return {
                "estado": "lista_nao_validada",
                "diagnostico": diagnostico,
            }

        texto = (botao.inner_text() or "0").strip()
        quantidade = int(texto) if texto.isdigit() else 0
        if quantidade == 0 or not botao.is_visible():
            return {
                "estado": "ok", "jogos": [],
                "contador_ao_vivo": quantidade,
                "status_explicito": True,
            }

        botao.click(timeout=5000)
        pagina.wait_for_timeout(3000)
        texto_atualizado = (botao.inner_text() or "0").strip()
        if texto_atualizado.isdigit():
            quantidade = int(texto_atualizado)
        jogos_ao_vivo = self._coletar_lista_virtualizada(pagina, quantidade)
        diagnostico_virtualizacao_ao_vivo = dict(
            self._ultimo_diagnostico_virtualizacao or {}
        )
        status_excluidos = []
        interrompidos_total = 0
        fora_regulamentar_total = 0
        if quantidade != len(jogos_ao_vivo):
            diagnostico_status = diagnostico_virtualizacao_ao_vivo
            if not diagnostico_status.get("linhas_com_partida"):
                diagnostico_status = (
                    pagina.evaluate(SCRIPT_DIAGNOSTICO_STATUS_LISTA) or {}
                )
            if isinstance(diagnostico_status, dict):
                status_excluidos = list(
                    diagnostico_status.get("excluidos") or []
                )
                interrompidos_total = int(
                    diagnostico_status.get("interrompidos_total") or 0
                )
                fora_regulamentar_total = int(
                    diagnostico_status.get(
                        "fora_regulamentar_total"
                    ) or 0
                )
            elif isinstance(diagnostico_status, list):
                # Compatibilidade conservadora com uma página já carregada
                # durante a troca da versão do script.
                status_excluidos = diagnostico_status
        if self.usar_scanner_prioridade:
            jogos_scanner, diagnostico_scanner = (
                self._coletar_scanner_prioritario(pagina)
            )
            jogos = self._mesclar_prioridade_scanner(
                jogos_ao_vivo, jogos_scanner
            )
        else:
            jogos = jogos_ao_vivo
            diagnostico_scanner = {
                "habilitado": False,
                "estado": "desativado",
                "contador_filtrado": None,
                "jogos_extraidos": 0,
            }
        return {
            "estado": "ok",
            "jogos": jogos,
            "contador_ao_vivo": quantidade,
            "status_explicito": True,
            "status_excluidos": status_excluidos,
            "interrompidos_total": interrompidos_total,
            "fora_regulamentar_total": fora_regulamentar_total,
            "scanner": diagnostico_scanner,
        }

    def coletar_estatisticas(self, pagina, jogo):
        inicio = self.relogio()
        self._navegar(pagina, jogo["url"])
        apos_navegacao = self.relogio()
        renderizacao_antecipada = _aguardar_renderizacao(
            pagina,
            """() => Array.from(document.querySelectorAll('[title]'))
                .filter(item => /Chutes|Escanteios|Ataques/i.test(
                    item.getAttribute('title') || ''
                )).length >= 3""",
            timeout_ms=4000,
            fallback_ms=4000,
        )
        apos_renderizacao = self.relogio()
        estatisticas = self._ler_estatisticas_com_retentativa(pagina)
        fim = self.relogio()
        diagnostico = dict(self.ultimo_diagnostico_estatisticas or {})
        diagnostico.update({
            "versao": "diagnostico-coleta-estatisticas-v3",
            "renderizacao_antecipada": bool(renderizacao_antecipada),
            "duracoes_etapas": {
                "navegacao_segundos": round(
                    max(apos_navegacao - inicio, 0.0), 3
                ),
                "renderizacao_segundos": round(
                    max(apos_renderizacao - apos_navegacao, 0.0), 3
                ),
                "leitura_retentativas_segundos": round(
                    max(fim - apos_renderizacao, 0.0), 3
                ),
                "total_segundos": round(max(fim - inicio, 0.0), 3),
            },
            "navegacao_detalhada": dict(
                self.ultimo_diagnostico_navegacao or {}
            ),
            "altera_sinal": False,
        })
        self.ultimo_diagnostico_estatisticas = diagnostico
        return estatisticas

    @staticmethod
    def _valor_estatistica_presente(valor):
        if valor is None:
            return False
        if isinstance(valor, str):
            return bool(valor.strip())
        return True

    def _ler_estatisticas_com_retentativa(
        self, pagina, tentativas_adicionais=2, espera_ms=1000
    ):
        """Relê a SPA incompleta sem nova navegação nem novo acesso contado."""
        estatisticas = pagina.evaluate(SCRIPT_ESTATISTICAS) or {}
        essenciais = ("Chutes no gol", "Índice de pressão")
        tentativas = 0
        while tentativas < max(int(tentativas_adicionais), 0):
            ausentes = [
                campo for campo in essenciais
                if not self._valor_estatistica_presente(
                    estatisticas.get(campo)
                )
            ]
            if not ausentes:
                break
            pagina.wait_for_timeout(max(int(espera_ms), 0))
            releitura = pagina.evaluate(SCRIPT_ESTATISTICAS) or {}
            for campo, valor in releitura.items():
                if self._valor_estatistica_presente(valor):
                    estatisticas[campo] = valor
                elif campo not in estatisticas:
                    estatisticas[campo] = valor
            tentativas += 1
        campos_essenciais_ausentes = [
            campo for campo in essenciais
            if not self._valor_estatistica_presente(
                estatisticas.get(campo)
            )
        ]
        campos_lidos = sorted(
            str(campo) for campo, valor in estatisticas.items()
            if self._valor_estatistica_presente(valor)
            and not str(campo).startswith("_")
        )
        self.ultimo_diagnostico_estatisticas = {
            "versao": "diagnostico-coleta-estatisticas-v2",
            "estado": (
                "completo" if not campos_essenciais_ausentes else "parcial"
            ),
            "tentativas_adicionais": tentativas,
            "campos_essenciais_ausentes": campos_essenciais_ausentes,
            "campos_lidos": campos_lidos,
            "quantidade_campos_lidos": len(campos_lidos),
            "nova_navegacao": False,
        }
        return estatisticas

    def coletar_estado_partida(self, pagina, jogo):
        self._navegar(pagina, jogo["url"])
        _aguardar_renderizacao(
            pagina,
            """() => Array.from(document.querySelectorAll('[title]'))
                .filter(item => /Chutes|Escanteios|Ataques/i.test(
                    item.getAttribute('title') || ''
                )).length >= 3""",
            timeout_ms=4000,
            fallback_ms=4000,
        )
        estado = pagina.evaluate(SCRIPT_ESTADO_PARTIDA) or {}
        estado["estatisticas"] = self._ler_estatisticas_com_retentativa(
            pagina
        )
        return estado
