"""Tendencias de gols por time/periodo lidas na area Ligas do PackBall."""

import copy
import math
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse, urlunparse

from contrafactual_protecoes import converter_em_contrafactual


VERSAO = "tendencias-packball-ligas-v1.4"
ATIVA = os.getenv("PROTECAO_TENDENCIAS_PACKBALL_ATIVA", "1").strip().lower() not in {
    "0", "false", "nao", "não", "off",
}
FALLBACK_HISTORICO_ATIVO = os.getenv(
    "PROTECAO_TENDENCIAS_PACKBALL_FALLBACK_HISTORICO_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
FALLBACK_API_AMOSTRA_ATIVO = os.getenv(
    "PROTECAO_TENDENCIAS_PACKBALL_FALLBACK_API_AMOSTRA_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
VERSAO_QUARENTENA_FALLBACK_HT = (
    "fallback-api-ht-linhas-altas-quarentena-v1"
)
MERCADOS = frozenset({"gol_ft", "gol_ht", "proximo_gol"})
TTL_SEGUNDOS = 12 * 3600
AMOSTRA_MINIMA = 10
ESPERA_FILTRO_SEGUNDOS = 12.0
ESPERA_TABELA_MILISSEGUNDOS = 15000
TENTATIVAS_LEITURA_DOM = 2
LIMITES = {
    0.5: {"media": 0.50, "melhor": 0.55, "eficiencia": 0.20},
    1.5: {"media": 0.25, "melhor": 0.30, "eficiencia": 0.15},
    2.5: {"media": 0.10, "melhor": 0.15, "eficiencia": 0.08},
}

CHAVES_METODOS_FALLBACK_VALIDADO = (
    "gol_capacidade_contextual_v2",
)


def _numero(valor):
    try:
        numero = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
    return numero if numero is not None and math.isfinite(numero) else None


def fallback_api_ht_linhas_altas_ativo(environ=None):
    """Lê a chave após o ``.env`` ser carregado pelo serviço."""
    ambiente = os.environ if environ is None else environ
    return str(ambiente.get(
        "PROTECAO_TENDENCIAS_PACKBALL_FALLBACK_API_HT_LINHAS_ALTAS_ATIVO",
        "0",
    )).strip().casefold() not in {"0", "false", "nao", "não", "off"}


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(x for x in texto if not unicodedata.combining(x))
    return re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()


def _percentual(valor):
    numero = _numero(str(valor or "").replace("%", "").replace(",", "."))
    return None if numero is None else numero / 100.0


def _rotulo_estatistica_over_gols(valor):
    normalizado = _normalizar(valor)
    palavras = set(normalizado.split())
    return bool(
        "over" in palavras
        and ({"gols", "goals"} & palavras)
    )


def _selecionar_estatistica_over_gols(pagina):
    """Espera as opcoes React e seleciona Over Gols pelo valor real.

    O painel pode ficar visivel alguns segundos antes de o ``select`` receber
    suas opcoes. Ler imediatamente produzia um falso
    ``estatistica_over_gols_ausente`` em ligas que carregavam normalmente.
    """
    limite = time.monotonic() + ESPERA_FILTRO_SEGUNDOS
    while time.monotonic() < limite:
        barra = pagina.locator("section.filter-bar").first
        seletores = barra.locator("select")
        for indice in range(seletores.count()):
            seletor = seletores.nth(indice)
            opcoes = seletor.locator("option")
            textos = opcoes.all_text_contents()
            for indice_opcao, texto in enumerate(textos):
                if not _rotulo_estatistica_over_gols(texto):
                    continue
                opcao = opcoes.nth(indice_opcao)
                valor = opcao.get_attribute("value")
                if valor is not None:
                    seletor.select_option(value=valor)
                else:
                    seletor.select_option(label=texto)
                return
        pagina.wait_for_timeout(250)
    raise RuntimeError("estatistica_over_gols_ausente")


def _placar(valor):
    if isinstance(valor, (list, tuple)) and len(valor) >= 2:
        numeros = [_numero(valor[0]), _numero(valor[1])]
        return None if None in numeros else [int(x) for x in numeros]
    numeros = re.findall(r"\d+", str(valor or ""))
    return [int(numeros[0]), int(numeros[1])] if len(numeros) >= 2 else None


def _minuto(jogo):
    texto = str((jogo or {}).get("status") or "")
    if "intervalo" in texto.casefold() or texto.strip().casefold() == "ht":
        return 45
    numeros = re.findall(r"\d{1,3}", texto)
    return int(numeros[0]) if numeros else None


def periodo_atual(jogo):
    minuto = _minuto(jogo)
    return "1t" if minuto is not None and minuto <= 45 else "2t"


def _url_times_liga(liga_url):
    if not liga_url:
        return None
    absoluta = urljoin("https://packball.com", str(liga_url))
    partes = urlparse(absoluta)
    caminho = re.sub(r"/pt/matches/", "/pt/leagues/", partes.path, count=1)
    caminho = re.sub(r"/(summary|matches|players|characteristics|stats|standings)$", "/teams", caminho)
    if not caminho.endswith("/teams"):
        caminho = caminho.rstrip("/") + "/teams"
    return urlunparse((partes.scheme, partes.netloc, caminho, "", "", ""))


def _descobrir_liga_url_pagina(pagina):
    """Recupera a liga na partida quando a linha do Scanner não a trouxe."""
    try:
        return pagina.evaluate(r"""() => {
          const links = Array.from(document.querySelectorAll(
            'a[href*="/league/"]'
          ));
          const href = links.map(item => item.href).find(item =>
            /\/league\//i.test(item || '')
          );
          return href || null;
        }""")
    except Exception:
        return None


def _ajustar_slider(pagina, slider, alvo):
    atual = int(slider.get_attribute("aria-valuenow"))
    alvo = int(alvo)
    if atual == alvo:
        return
    geometria = slider.evaluate("""elemento => {
      const faixa = elemento.closest('.input-range');
      if (!faixa) return null;
      const r = faixa.getBoundingClientRect();
      const s = elemento.getBoundingClientRect();
      return {faixa: {x: r.x, y: r.y, width: r.width, height: r.height},
        slider: {x: s.x, y: s.y, width: s.width, height: s.height}};
    }""")
    if not geometria:
        raise RuntimeError("geometria_seletor_periodo_ausente")
    slider.evaluate("""(elemento, alvo) => {
      const faixa = elemento.closest('.input-range').getBoundingClientRect();
      const atual = elemento.getBoundingClientRect();
      const origemX = atual.x + atual.width / 2;
      const y = atual.y + atual.height / 2;
      const destinoX = faixa.x + faixa.width * (alvo / 90);
      const criar = (tipo, x, botoes) => new MouseEvent(tipo, {
        bubbles: true, cancelable: true, view: window, button: 0,
        buttons: botoes, clientX: x, clientY: y
      });
      elemento.dispatchEvent(criar('mousedown', origemX, 1));
      document.dispatchEvent(criar('mousemove', destinoX, 1));
      window.dispatchEvent(criar('mousemove', destinoX, 1));
      document.dispatchEvent(criar('mouseup', destinoX, 0));
      window.dispatchEvent(criar('mouseup', destinoX, 0));
    }""", alvo)
    pagina.wait_for_timeout(150)
    confirmado = int(slider.get_attribute("aria-valuenow"))
    if confirmado != alvo:
        raise RuntimeError(f"marcador_periodo_nao_ajustado:{confirmado}:{alvo}")


def _configurar_periodo(pagina, periodo):
    barra = pagina.locator("section.filter-bar").first
    if barra.count() != 1:
        raise RuntimeError("painel_filtro_liga_ausente")
    if barra.locator('[role="slider"]').count() < 2:
        barra.locator("header a").first.click(timeout=5000)
        pagina.wait_for_timeout(250)
    rotulo_anterior = ""
    if barra.locator(".label-period").count():
        rotulo_anterior = barra.locator(".label-period").first.inner_text().strip()
    tabela_anterior = ""
    if pagina.locator("table tbody").count():
        tabela_anterior = pagina.locator("table tbody").first.inner_text()
    _selecionar_estatistica_over_gols(pagina)
    pagina.wait_for_timeout(250)
    barra = pagina.locator("section.filter-bar").first
    sliders = barra.locator('[role="slider"]')
    if sliders.count() != 2:
        raise RuntimeError("seletores_periodo_invalidos")
    inicio, fim = (0, 45) if periodo == "1t" else (45, 90)
    _ajustar_slider(pagina, sliders.nth(0), inicio)
    sliders = pagina.locator("section.filter-bar").first.locator('[role="slider"]')
    _ajustar_slider(pagina, sliders.nth(1), fim)
    funil = pagina.locator("section.filter-bar a.filter-ok").first
    if funil.count() != 1:
        raise RuntimeError("funil_aplicar_filtro_ausente")
    # O painel lateral do PackBall pode ficar visualmente sobre o funil durante
    # a animacao. O clique forcado aciona o mesmo controle que o usuario usa,
    # sem depender da geometria momentanea da pagina.
    funil.evaluate("""elemento => {
      const chave = Object.keys(elemento).find(
        item => item.startsWith('__reactProps')
      );
      const aplicar = chave && elemento[chave] && elemento[chave].onClick;
      if (typeof aplicar !== 'function') {
        throw new Error('acao_funil_packball_ausente');
      }
      aplicar();
    }""")
    pagina.wait_for_timeout(250)
    valores = [
        int(x.get_attribute("aria-valuenow"))
        for x in pagina.locator("section.filter-bar").first.locator('[role="slider"]').all()
    ]
    if valores != [inicio, fim]:
        raise RuntimeError(f"periodo_nao_confirmado:{valores}")
    esperado = "1st" if periodo == "1t" else "2nd"
    rotulos = pagina.locator(".label-period").all_inner_texts()
    rotulo = rotulos[0].strip() if rotulos else ""
    limite_rotulo = time.monotonic() + 5.0
    while rotulo.casefold() != esperado.casefold() and time.monotonic() < limite_rotulo:
        pagina.wait_for_timeout(200)
        rotulos = pagina.locator(".label-period").all_inner_texts()
        rotulo = rotulos[0].strip() if rotulos else ""
    if rotulo.casefold() != esperado.casefold():
        raise RuntimeError(f"rotulo_periodo_incompativel:{rotulo}")
    if rotulo_anterior and rotulo_anterior.casefold() != esperado.casefold():
        limite = time.monotonic() + 8.0
        while time.monotonic() < limite:
            atual = pagina.locator("table tbody").first.inner_text()
            if atual != tabela_anterior:
                break
            pagina.wait_for_timeout(250)
        else:
            raise RuntimeError("tabela_periodo_nao_atualizada")
    pagina.wait_for_timeout(250)
    return inicio, fim


def _ler_times(pagina):
    pagina.locator("table tbody tr").first.wait_for(
        state="visible", timeout=ESPERA_TABELA_MILISSEGUNDOS
    )
    resultado = []
    for linha in pagina.locator("table tbody tr").all():
        celulas = linha.locator("td").all_inner_texts()
        if len(celulas) < 10:
            continue
        nome = str(celulas[3] or "").strip()
        jogos = _numero(celulas[6])
        if not nome or jogos is None:
            continue
        resultado.append({
            "time": nome,
            "time_normalizado": _normalizar(nome),
            "eficiencia": _percentual(celulas[1]),
            "jogos": int(jogos),
            "over_0_5": _percentual(celulas[7]),
            "over_1_5": _percentual(celulas[8]),
            "over_2_5": _percentual(celulas[9]),
        })
    return resultado


def _ler_times_api(conteudo):
    dados = (conteudo or {}).get("data") or {}
    resultado = []
    for item in dados.get("teams") or []:
        time_dados = item.get("team") or {}
        partidas = item.get("matches") or {}
        valores = item.get("values") or []
        nome = str(time_dados.get("name") or "").strip()
        jogos = _numero(partidas.get("playeds"))
        if not nome or jogos is None or len(valores) < 3:
            continue
        resultado.append({
            "time": nome,
            "time_normalizado": _normalizar(nome),
            "eficiencia": (
                None if _numero(time_dados.get("ranking")) is None
                else _numero(time_dados.get("ranking")) / 100.0
            ),
            "jogos": int(jogos),
            "over_0_5": (
                None if _numero(valores[0]) is None
                else _numero(valores[0]) / 100.0
            ),
            "over_1_5": (
                None if _numero(valores[1]) is None
                else _numero(valores[1]) / 100.0
            ),
            "over_2_5": (
                None if _numero(valores[2]) is None
                else _numero(valores[2]) / 100.0
            ),
        })
    return resultado


def _ler_times_dom_periodo(pagina, periodo):
    """Recupera a mesma evidência pela tabela visível da aba Ligas.

    Algumas ligas são atendidas pelo cache da SPA e não emitem novamente a
    requisição ``/league/team-stats`` durante a navegação. A tabela exibida ao
    usuário continua sendo uma fonte PackBall válida; configuramos o período,
    confirmamos os seletores e somente então lemos as linhas renderizadas.
    """
    # A rota de ligas pode concluir ``domcontentloaded`` antes de montar o
    # painel React. Esperar o elemento evita confundir atraso visual com
    # ausência definitiva da estatística.
    pagina.locator("section.filter-bar").first.wait_for(
        state="visible", timeout=int(ESPERA_FILTRO_SEGUNDOS * 1000)
    )
    inicio, fim = _configurar_periodo(pagina, periodo)
    times = _ler_times(pagina)
    if not times:
        raise RuntimeError("tabela_times_over_gols_dom_vazia")
    return {
        "times": times,
        "minuto_inicio": inicio,
        "minuto_fim": fim,
        "fonte": "packball_ligas_times_dom",
    }


def _cabecalhos_reutilizaveis(cabecalhos):
    return {
        chave: valor
        for chave, valor in (cabecalhos or {}).items()
        if not chave.startswith(":")
        and chave.casefold() not in {"host", "content-length"}
    }


def coletar_tendencias_packball_liga(
    pagina, jogo, periodo, controle_acesso=None, cache=None,
):
    liga_url = (jogo or {}).get("liga_url") or (
        ((jogo or {}).get("metadados") or {}).get("liga_url")
    )
    if not liga_url:
        liga_url = _descobrir_liga_url_pagina(pagina)
    url = _url_times_liga(liga_url)
    if url is None:
        raise RuntimeError("url_liga_packball_ausente")
    chave = f"{url}|{periodo}"
    agora = time.time()
    cache = cache if isinstance(cache, dict) else {}
    anterior = cache.get(chave)
    if isinstance(anterior, dict) and agora - float(anterior.get("timestamp") or 0) <= TTL_SEGUNDOS:
        retorno = copy.deepcopy(anterior["dados"])
        retorno["cache"] = True
        return retorno
    if controle_acesso is not None:
        controle_acesso.antes_navegacao()
    requisicoes_times = []

    def capturar_requisicao(requisicao):
        if "/league/team-stats" in requisicao.url:
            requisicoes_times.append({
                "url": requisicao.url,
                "headers": requisicao.all_headers(),
            })

    pagina.on("request", capturar_requisicao)
    try:
        pagina.goto(url, wait_until="domcontentloaded", timeout=30000)
        pagina.wait_for_timeout(1000)
    finally:
        pagina.remove_listener("request", capturar_requisicao)
    if controle_acesso is not None:
        controle_acesso.validar_pagina(pagina)
    inicio, fim = (0, 45) if periodo == "1t" else (45, 90)
    times = []
    fonte = "packball_ligas_times"
    erro_api = None
    if requisicoes_times:
        try:
            tempo_api = 1 if periodo == "1t" else 2
            requisicao_base = requisicoes_times[-1]
            url_api = re.sub(
                r"([?&]match_time=)\d+",
                rf"\g<1>{tempo_api}",
                requisicao_base["url"],
            )
            resposta = pagina.context.request.get(
                url_api,
                headers=_cabecalhos_reutilizaveis(
                    requisicao_base["headers"]
                ),
                timeout=30000,
            )
            if not resposta.ok:
                raise RuntimeError(
                    f"consulta_times_packball_http_{resposta.status}"
                )
            times = _ler_times_api(resposta.json())
            if not times:
                raise RuntimeError("tabela_times_over_gols_vazia")
        except Exception as erro:
            erro_api = erro
            times = []
    else:
        erro_api = RuntimeError("consulta_times_packball_ausente")

    if not times:
        erro_dom = None
        leitura_dom = None
        for tentativa in range(TENTATIVAS_LEITURA_DOM):
            try:
                leitura_dom = _ler_times_dom_periodo(pagina, periodo)
                break
            except Exception as erro:
                erro_dom = erro
                if tentativa + 1 < TENTATIVAS_LEITURA_DOM:
                    pagina.wait_for_timeout(750 * (tentativa + 1))
        if leitura_dom is None:
            raise RuntimeError(
                f"{erro_api};fallback_dom={type(erro_dom).__name__}:"
                f"{str(erro_dom)[:180]}"
            ) from erro_dom
        times = leitura_dom["times"]
        inicio = leitura_dom["minuto_inicio"]
        fim = leitura_dom["minuto_fim"]
        fonte = leitura_dom["fonte"]
    dados = {
        "versao": VERSAO,
        "fonte": fonte,
        "liga_url": url,
        "liga": (jogo or {}).get("liga_nome"),
        "periodo": periodo,
        "minuto_inicio": inicio,
        "minuto_fim": fim,
        "times": times,
        "cache": False,
        "coletado_em_epoch": agora,
    }
    if erro_api is not None and fonte.endswith("_dom"):
        dados["fallback_dom"] = {
            "usado": True,
            "motivo": str(erro_api)[:180],
        }
    cache[chave] = {"timestamp": agora, "dados": copy.deepcopy(dados)}
    return dados


def _associar_time(nome, times):
    alvo = _normalizar(nome)
    candidatos = []
    for item in times or []:
        atual = item.get("time_normalizado") or _normalizar(item.get("time"))
        if not atual:
            continue
        nota = 1.0 if alvo == atual else SequenceMatcher(None, alvo, atual).ratio()
        candidatos.append((nota, item))
    candidatos.sort(key=lambda x: x[0], reverse=True)
    if not candidatos or candidatos[0][0] < 0.72:
        return None, None
    if len(candidatos) > 1 and candidatos[0][0] - candidatos[1][0] < 0.05:
        return None, None
    return candidatos[0][1], round(candidatos[0][0], 4)


def _gols_periodo(jogo, confirmacao_api, periodo):
    atual = _placar((jogo or {}).get("placar"))
    if atual is None:
        return None
    total = sum(atual)
    if periodo == "1t":
        return total
    intervalo = _placar((confirmacao_api or {}).get("placar_intervalo"))
    if intervalo is not None and sum(intervalo) <= total:
        return total - sum(intervalo)
    eventos = (confirmacao_api or {}).get("eventos") or []
    gols_2t = 0
    for evento in eventos:
        if str(evento.get("type") or "").casefold() != "goal":
            continue
        minuto = _numero(((evento.get("time") or {}).get("elapsed")))
        if minuto is not None and minuto > 45:
            gols_2t += 1
    return gols_2t if gols_2t <= total else None


def _linha_periodo(candidato, jogo, confirmacao_api, periodo):
    gols_periodo = _gols_periodo(jogo, confirmacao_api, periodo)
    if gols_periodo is None:
        return None
    if candidato.get("mercado") == "proximo_gol":
        necessarios = 1
    else:
        linha = _numero(candidato.get("linha"))
        atual = _placar((jogo or {}).get("placar"))
        if linha is None or atual is None:
            return None
        necessarios = max(int(math.floor(linha) + 1 - sum(atual)), 1)
    return float(gols_periodo + necessarios) - 0.5


def _fallback_historico_metodo(candidato):
    """Valida outra evidência forte quando a aba Ligas não está disponível.

    O fallback não libera a regra-base. Ele exige um challenger versionado,
    linhagem persistida e a proteção histórica específica da linha já
    aprovada. Assim, uma falha auxiliar do PackBall não zera todo o fluxo,
    mas um perfil realmente fraco encontrado no PackBall continua bloqueando.
    """
    if not FALLBACK_HISTORICO_ATIVO:
        return None
    features = (candidato or {}).get("features") or {}
    conversao = features.get("protecao_conversao_gols") or {}
    if not (
        conversao.get("ativa") is True
        and conversao.get("aprovada") is True
    ):
        return None
    # O fallback amplo foi recusado no replay de 28/08: 4 green/6 red,
    # ROI -34,3%. Somente o contextual V2b combina modelo de tempo restante,
    # histórico segmentado e evidência live dentro da própria linhagem.
    for chave in CHAVES_METODOS_FALLBACK_VALIDADO:
        metodo = features.get(chave)
        if isinstance(metodo, dict) and metodo.get("linhagem_sha256"):
            return {
                "chave_metodo": chave,
                "linhagem_sha256": metodo["linhagem_sha256"],
                "protecao_conversao_versao": conversao.get("versao"),
                "protecao_conversao_motivo": conversao.get("motivo"),
            }
    return None


def _fallback_historico_api_amostra(candidato):
    """Complementa somente uma amostra curta do PackBall com a API.

    A aprovação transversal de conversão já exige histórico recente dos dois
    times: ao menos dez jogos gerais e quatro no recorte mandante/visitante,
    além das taxas mínimas da linha atual. Reutilizar essa decisão evita uma
    nova consulta externa e mantém a origem auditável.

    Este caminho não cobre indisponibilidade total do PackBall nem tendência
    PackBall fraca. Assim, a mudança corrige apenas o falso bloqueio causado
    pela tabela da temporada conter poucos jogos.
    """
    if not FALLBACK_API_AMOSTRA_ATIVO:
        return None
    if (candidato or {}).get("mercado") not in {"gol_ft", "gol_ht"}:
        return None
    features = (candidato or {}).get("features") or {}
    conversao = features.get("protecao_conversao_gols") or {}
    if not (
        conversao.get("ativa") is True
        and conversao.get("aprovada") is True
        and conversao.get("motivo") == "apoio_da_linha_confirmado"
    ):
        return None
    amostras_gerais = [
        int(_numero(valor) or 0)
        for valor in (conversao.get("amostras_gerais") or [])
    ]
    amostras_mando = [
        int(_numero(valor) or 0)
        for valor in (conversao.get("amostras_mando") or [])
    ]
    if (
        len(amostras_gerais) != 2
        or len(amostras_mando) != 2
        or min(amostras_gerais) < 10
        or min(amostras_mando) < 4
    ):
        return None
    return {
        "origem": "api_football_historico_linhas_gols",
        "protecao_conversao_versao": conversao.get("versao"),
        "protecao_conversao_motivo": conversao.get("motivo"),
        "mercado": conversao.get("mercado"),
        "linha": conversao.get("linha"),
        "campo": conversao.get("campo"),
        "amostras_gerais": amostras_gerais,
        "amostras_mando": amostras_mando,
        "taxas_gerais": conversao.get("taxas_gerais"),
        "taxas_mando": conversao.get("taxas_mando"),
        "media_geral": conversao.get("media_geral"),
        "media_mando": conversao.get("media_mando"),
    }


def _indisponivel_ou_fallback(
    candidato, motivo, fonte_packball_disponivel=False, **detalhes
):
    fallback = _fallback_historico_metodo(candidato)
    motivo_fallback = "fallback_historico_metodo_confirmado"
    if (
        fallback is None
        and motivo == "amostra_packball_insuficiente"
        and fonte_packball_disponivel
    ):
        fallback_api = _fallback_historico_api_amostra(candidato)
        linha = _numero((candidato or {}).get("linha"))
        linha_alta_ht = bool(
            (candidato or {}).get("mercado") == "gol_ht"
            and linha is not None
            and linha > 0.5
        )
        if (
            fallback_api is not None
            and linha_alta_ht
            and not fallback_api_ht_linhas_altas_ativo()
        ):
            return {
                "versao": VERSAO,
                "ativa": ATIVA,
                "aprovada": False,
                "motivo": (
                    "fallback_historico_api_ht_linha_alta_em_quarentena"
                ),
                "motivo_packball": motivo,
                "fonte_packball_disponivel": bool(
                    fonte_packball_disponivel
                ),
                "fallback_historico": fallback_api,
                "politica_fallback_ht": {
                    "versao": VERSAO_QUARENTENA_FALLBACK_HT,
                    "estado": "quarentena_prospectiva",
                    "linha": linha,
                    "linhas_bloqueadas": "acima_de_0.5",
                    "avaliacao_estado": (
                        "avaliacao_quarentena_fallback_ht_estado.json"
                    ),
                    "independencia": (
                        "primeiro_candidato_por_jogo_e_grupo"
                    ),
                    "aplicacao_sinais": True,
                    "preserva_confirmacao_direta_packball": True,
                    "preserva_linha_ht_0_5": True,
                    "rollback": (
                        "PROTECAO_TENDENCIAS_PACKBALL_FALLBACK_API_"
                        "HT_LINHAS_ALTAS_ATIVO=1"
                    ),
                },
                **detalhes,
            }
        fallback = fallback_api
        motivo_fallback = "fallback_historico_api_amostra_confirmado"
    if fallback is not None:
        return {
            "versao": VERSAO,
            "ativa": ATIVA,
            "aprovada": True,
            "motivo": motivo_fallback,
            "motivo_packball": motivo,
            "fonte_packball_disponivel": bool(
                fonte_packball_disponivel
            ),
            "fallback_historico": fallback,
            **detalhes,
        }
    return {
        "versao": VERSAO,
        "ativa": ATIVA,
        "aprovada": False,
        "motivo": motivo,
        "fonte_packball_disponivel": bool(fonte_packball_disponivel),
        **detalhes,
    }


def avaliar_tendencia_packball(candidato, contexto, jogo, confirmacao_api=None):
    if not ATIVA or candidato.get("mercado") not in MERCADOS:
        return {"versao": VERSAO, "ativa": ATIVA, "aprovada": True, "motivo": "fora_do_escopo_ou_desativada"}
    if not isinstance(contexto, dict) or not contexto.get("times"):
        return _indisponivel_ou_fallback(
            candidato, "tendencia_packball_indisponivel"
        )
    periodo = contexto.get("periodo") or periodo_atual(jogo)
    linha = _linha_periodo(candidato, jogo, confirmacao_api, periodo)
    if linha not in LIMITES:
        return _indisponivel_ou_fallback(
            candidato,
            "linha_periodo_sem_modelo",
            fonte_packball_disponivel=True,
            fonte=contexto.get("fonte"),
            linha_periodo=linha,
            periodo=periodo,
        )
    casa, nota_casa = _associar_time((jogo or {}).get("mandante"), contexto["times"])
    fora, nota_fora = _associar_time((jogo or {}).get("visitante"), contexto["times"])
    if casa is None or fora is None:
        return _indisponivel_ou_fallback(
            candidato,
            "times_nao_localizados_na_liga",
            fonte_packball_disponivel=True,
            fonte=contexto.get("fonte"),
            periodo=periodo,
        )
    if casa.get("jogos", 0) < AMOSTRA_MINIMA or fora.get("jogos", 0) < AMOSTRA_MINIMA:
        return _indisponivel_ou_fallback(
            candidato,
            "amostra_packball_insuficiente",
            fonte_packball_disponivel=True,
            fonte=contexto.get("fonte"),
            periodo=periodo,
            amostras={
                "mandante": int(casa.get("jogos", 0) or 0),
                "visitante": int(fora.get("jogos", 0) or 0),
                "minima": AMOSTRA_MINIMA,
            },
        )
    campo = f"over_{str(linha).replace('.', '_')}"
    taxas = [_numero(casa.get(campo)), _numero(fora.get(campo))]
    eficiencias = [_numero(casa.get("eficiencia")), _numero(fora.get("eficiencia"))]
    if None in taxas or None in eficiencias:
        return _indisponivel_ou_fallback(
            candidato,
            "percentuais_packball_incompletos",
            fonte_packball_disponivel=True,
            fonte=contexto.get("fonte"),
            periodo=periodo,
            linha_periodo=linha,
        )
    media = sum(taxas) / 2
    media_eficiencia = sum(eficiencias) / 2
    limites = LIMITES[linha]
    aprovada = bool(
        media >= limites["media"]
        and max(taxas) >= limites["melhor"]
        and media_eficiencia >= limites["eficiencia"]
    )
    return {
        "versao": VERSAO,
        "ativa": ATIVA,
        "aprovada": aprovada,
        "motivo": "tendencia_packball_confirmada" if aprovada else "tendencia_packball_fraca",
        "periodo": periodo,
        "linha_periodo": linha,
        "campo": campo,
        "media_taxa": round(media, 4),
        "melhor_taxa": round(max(taxas), 4),
        "media_eficiencia": round(media_eficiencia, 4),
        "times": {
            "mandante": {**casa, "similaridade": nota_casa},
            "visitante": {**fora, "similaridade": nota_fora},
        },
        "limites": limites,
        "fonte": contexto.get("fonte"),
        "cache": contexto.get("cache"),
    }


def aplicar_protecao_tendencias_packball(candidatos, contexto, jogo, confirmacao_api=None):
    resumo = {
        "avaliados": 0,
        "aprovados": 0,
        "bloqueados": 0,
        "fallbacks_historicos": 0,
        "fallbacks_api_amostra": 0,
        "motivos": {},
    }
    for candidato in candidatos or []:
        if candidato.get("mercado") not in MERCADOS or candidato.get("status") not in {"aprovado", "simulacao"}:
            continue
        avaliacao = avaliar_tendencia_packball(candidato, contexto, jogo, confirmacao_api)
        features = copy.deepcopy(candidato.get("features") or {})
        features["protecao_tendencias_packball"] = avaliacao
        candidato["features"] = features
        resumo["avaliados"] += 1
        if avaliacao["aprovada"]:
            resumo["aprovados"] += 1
            if avaliacao.get("fallback_historico"):
                resumo["fallbacks_historicos"] += 1
                if (
                    avaliacao.get("motivo")
                    == "fallback_historico_api_amostra_confirmado"
                ):
                    resumo["fallbacks_api_amostra"] += 1
            continue
        resumo["bloqueados"] += 1
        motivo = "protecao_tendencias_packball:" + avaliacao["motivo"]
        resumo["motivos"][motivo] = resumo["motivos"].get(motivo, 0) + 1
        candidato["bloqueios"] = list(dict.fromkeys(list(candidato.get("bloqueios") or []) + [motivo]))
        candidato["motivos"] = list(dict.fromkeys(list(candidato.get("motivos") or []) + [motivo]))
        converter_em_contrafactual(
            candidato,
            "protecao_tendencias_packball",
            avaliacao["motivo"],
        )
    return resumo
