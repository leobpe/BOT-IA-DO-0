"""Prioridade de coleta por taxas sazonais de gols das ligas PackBall.

As taxas desta camada apenas ordenam o lote que recebera leitura detalhada.
Elas nunca aprovam, rejeitam ou alteram um sinal.
"""

import math
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from tendencias_packball_ligas import _ajustar_slider


VERSAO = "prioridade-ligas-gols-packball-v1"
URL_LIGAS = "https://packball.com/pt/leagues"
PERIODOS = ("1t", "2t")


def normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()


def extrair_liga_id(url):
    correspondencia = re.search(
        r"/(?:leagues|matches)/(\d+)/league(?:/|$)",
        str(url or ""),
        flags=re.IGNORECASE,
    )
    return int(correspondencia.group(1)) if correspondencia else None


def _percentual(valor):
    correspondencia = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(valor or ""))
    if not correspondencia:
        return None
    return float(correspondencia.group(1).replace(",", ".")) / 100.0


def _inteiro(valor):
    correspondencia = re.search(r"\d+", str(valor or ""))
    return int(correspondencia.group(0)) if correspondencia else None


def _painel_visivel(pagina):
    return pagina.locator("main:visible").first


def _localizar_seletor_over_gols(pagina):
    seletores = pagina.locator("select")
    for indice in range(seletores.count()):
        seletor = seletores.nth(indice)
        opcoes = seletor.locator("option")
        for indice_opcao, texto in enumerate(opcoes.all_text_contents()):
            if normalizar(texto) in {"over gols", "over goals"}:
                opcao = opcoes.nth(indice_opcao)
                return seletor, texto, opcao.get_attribute("value")
    return None


def _abrir_filtro(pagina):
    if _localizar_seletor_over_gols(pagina) is not None:
        return
    controles = pagina.locator(".filter-label:visible")
    limite = time.monotonic() + 8.0
    while controles.count() < 1 and time.monotonic() < limite:
        pagina.wait_for_timeout(200)
        controles = pagina.locator(".filter-label:visible")
    if controles.count() < 1:
        raise RuntimeError("filtro_ligas_packball_ausente")
    # O clique precisa ocorrer no controle inteiro (texto, periodo e seta).
    # Clicar apenas em ``.label-header`` nao dispara a abertura em todos os
    # layouts responsivos usados pelo navegador do monitor.
    controle = controles.first
    acionadores = (
        lambda: controle.evaluate("""elemento => {
          const nos = [elemento, ...elemento.querySelectorAll('*')];
          for (const no of nos) {
            const chaveProps = Object.keys(no).find(
              item => item.startsWith('__reactProps')
            );
            const propriedades = chaveProps && no[chaveProps];
            if (typeof propriedades?.onClick === 'function') {
              propriedades.onClick({
                currentTarget: no,
                target: no,
                preventDefault() {},
                stopPropagation() {},
              });
              return true;
            }
            const chaveFiber = Object.keys(no).find(
              item => item.startsWith('__reactFiber')
            );
            let fiber = chaveFiber && no[chaveFiber];
            while (fiber) {
              if (typeof fiber.memoizedProps?.onClick === 'function') {
                fiber.memoizedProps.onClick({
                  currentTarget: no,
                  target: no,
                  preventDefault() {},
                  stopPropagation() {},
                });
                return true;
              }
              fiber = fiber.return;
            }
          }
          return false;
        }"""),
        lambda: controle.locator(":scope > div").last.click(
            timeout=5000, force=True
        ),
        lambda: controle.click(timeout=5000, force=True),
        lambda: controle.evaluate(
            "elemento => HTMLElement.prototype.click.call(elemento)"
        ),
    )
    for acionar in acionadores:
        resultado = acionar()
        if resultado is False:
            continue
        limite = time.monotonic() + 8.0
        while time.monotonic() < limite:
            if _localizar_seletor_over_gols(pagina) is not None:
                return
            pagina.wait_for_timeout(200)
    try:
        pagina.screenshot(
            path=str(
                Path(__file__).resolve().parent
                / "diagnostico_ligas_packball.png"
            ),
            full_page=True,
        )
    except Exception:
        pass
    raise RuntimeError(
        "filtro_ligas_packball_nao_abriu:"
        f"controles_visiveis={controles.count()}:"
        f"seletores={pagina.locator('select').count()}:"
        f"url={pagina.url}"
    )


def _selecionar_over_gols(pagina):
    limite = time.monotonic() + 8.0
    while time.monotonic() < limite:
        localizado = _localizar_seletor_over_gols(pagina)
        if localizado is not None:
            seletor, texto, valor = localizado
            if valor is not None:
                seletor.select_option(value=valor)
            else:
                seletor.select_option(label=texto)
            return
        pagina.wait_for_timeout(200)
    raise RuntimeError("estatistica_over_gols_ligas_ausente")


def _configurar_periodo_persistido(
    pagina,
    periodo,
    controle_acesso=None,
):
    """Aplica o mesmo estado persistido consumido pela pagina de ligas.

    O painel lateral pode recusar abertura na janela automatizada. O provider
    React da propria pagina inicializa a tabela por ``packballFiltersLeagues``;
    portanto, persistir o estado e recarregar reproduz a aplicacao manual do
    filtro sem depender de coordenadas ou do breakpoint visual.
    """
    if periodo not in PERIODOS:
        raise ValueError(f"periodo_ligas_invalido:{periodo}")
    inicio, fim = (0, 45) if periodo == "1t" else (45, 90)
    pagina.evaluate("""filtro => {
      const chave = 'packballFiltersLeagues';
      let atual = {};
      try {
        atual = JSON.parse(localStorage.getItem(chave) || '{}') || {};
      } catch (_) {
        atual = {};
      }
      localStorage.setItem(chave, JSON.stringify({
        ...atual,
        season: '1',
        marketplace: '4',
        period: {min: filtro.inicio, max: filtro.fim},
        groups: 'goals',
      }));
    }""", {"inicio": inicio, "fim": fim})
    if controle_acesso is not None:
        controle_acesso.antes_navegacao()
    pagina.reload(wait_until="domcontentloaded", timeout=30000)
    pagina.locator("main:visible").first.wait_for(
        state="visible", timeout=15000
    )
    pagina.wait_for_timeout(500)
    if controle_acesso is not None:
        controle_acesso.validar_pagina(pagina)
    esperado = "1st" if periodo == "1t" else "2nd"
    limite = time.monotonic() + 12.0
    while time.monotonic() < limite:
        cabecalhos = normalizar(" ".join(
            pagina.locator(".label-header").all_inner_texts()
        ))
        periodos = [
            normalizar(item)
            for item in pagina.locator(".label-period").all_inner_texts()
        ]
        texto_tabela = normalizar(
            pagina.locator("main:visible").last.inner_text()
        )
        if (
            "over gols" in cabecalhos
            and normalizar(esperado) in periodos
            and all(item in texto_tabela for item in ("0 5", "1 5", "2 5"))
        ):
            return inicio, fim
        pagina.wait_for_timeout(250)
    raise RuntimeError(
        "filtro_ligas_persistido_nao_confirmado:"
        f"periodo={periodo}:cabecalho={cabecalhos}:"
        f"periodos={','.join(periodos)}"
    )


def _configurar_periodo(pagina, periodo):
    if periodo not in PERIODOS:
        raise ValueError(f"periodo_ligas_invalido:{periodo}")
    _abrir_filtro(pagina)
    _selecionar_over_gols(pagina)
    painel = _painel_visivel(pagina)
    sliders = painel.locator('[role="slider"]')
    if sliders.count() != 2:
        raise RuntimeError("seletores_periodo_ligas_invalidos")
    inicio, fim = (0, 45) if periodo == "1t" else (45, 90)
    tabela_anterior = painel.inner_text()
    _ajustar_slider(pagina, sliders.nth(0), inicio)
    sliders = _painel_visivel(pagina).locator('[role="slider"]')
    _ajustar_slider(pagina, sliders.nth(1), fim)
    funil = _painel_visivel(pagina).locator("a.filter-ok").first
    if funil.count() != 1:
        raise RuntimeError("funil_ligas_packball_ausente")
    funil.evaluate("""elemento => {
      const chave = Object.keys(elemento).find(
        item => item.startsWith('__reactProps')
      );
      const aplicar = chave && elemento[chave] && elemento[chave].onClick;
      if (typeof aplicar !== 'function') {
        throw new Error('acao_funil_ligas_packball_ausente');
      }
      aplicar();
    }""")
    esperado = "1st" if periodo == "1t" else "2nd"
    limite = time.monotonic() + 10.0
    while time.monotonic() < limite:
        pagina.wait_for_timeout(200)
        valores = [
            int(item.get_attribute("aria-valuenow"))
            for item in _painel_visivel(pagina).locator(
                '[role="slider"]'
            ).all()
        ]
        rotulos = [
            texto.strip() for texto in
            _painel_visivel(pagina).locator(
                ".label-period"
            ).all_inner_texts()
        ]
        tabela_atual = pagina.locator("main:visible").first.inner_text()
        if (
            valores == [inicio, fim]
            and any(normalizar(item) == normalizar(esperado) for item in rotulos)
            and (tabela_atual != tabela_anterior or esperado in rotulos)
        ):
            return inicio, fim
    raise RuntimeError(f"periodo_ligas_nao_confirmado:{periodo}")


def _ler_linhas_ligas(pagina, periodo, coletado_em=None):
    coletado_em = coletado_em or datetime.now().replace(
        microsecond=0
    ).isoformat()
    registros = []
    seletor_link = 'a[href*="/leagues/"][href*="/league/"][href*="/summary"]'
    for linha in pagina.locator("main:visible ul").all():
        links = linha.locator(seletor_link)
        if links.count() < 1:
            continue
        link = links.first
        href = link.get_attribute("href")
        liga_id = extrair_liga_id(href)
        liga = str(link.inner_text() or "").strip()
        textos = [
            str(item or "").strip()
            for item in linha.locator("li").all_inner_texts()
            if str(item or "").strip()
        ]
        indice_temporada = next((
            indice for indice, texto in enumerate(textos)
            if re.fullmatch(r"\d{4}(?:/\d{4})?", texto)
        ), None)
        if liga_id is None or not liga or indice_temporada is None:
            continue
        temporada = textos[indice_temporada]
        pais = textos[0] if textos else ""
        cauda = textos[indice_temporada + 1:]
        if not cauda:
            continue
        partida = re.search(r"(\d+)\s*/\s*(\d+)", cauda[0])
        if not partida:
            continue
        jogos_realizados = int(partida.group(1))
        jogos_previstos = int(partida.group(2))
        jogos_com_stats = _inteiro(cauda[1]) if len(cauda) >= 2 else None
        percentuais = [
            _percentual(item) for item in cauda[2:]
            if _percentual(item) is not None
        ]
        if jogos_com_stats is None or len(percentuais) < 3:
            continue
        registros.append({
            "league_id": liga_id,
            "pais": pais,
            "liga": liga,
            "liga_normalizada": normalizar(liga),
            "temporada": temporada,
            "periodo": periodo,
            "jogos_realizados": jogos_realizados,
            "jogos_previstos": jogos_previstos,
            "jogos_com_stats": jogos_com_stats,
            "over_0_5": percentuais[0],
            "over_1_5": percentuais[1],
            "over_2_5": percentuais[2],
            "fonte": "packball_ligas_sazonal",
            "coletado_em": coletado_em,
            "versao": VERSAO,
        })
    return registros


def coletar_taxas_ligas_packball(pagina, controle_acesso=None):
    """Coleta 1T e 2T em uma unica visita a pagina global de ligas."""
    viewport_original = pagina.viewport_size
    viewport_ampliado = bool(
        viewport_original
        and int(viewport_original.get("width") or 0) < 1600
    )
    filtro_original = None
    filtro_original_capturado = False
    try:
        # A barra de filtros da lista global nao abre de forma confiavel no
        # breakpoint compacto de 1280 px. A coleta usa temporariamente o
        # layout desktop ja validado e restaura o tamanho antes de devolver a
        # pagina ao monitor ao vivo.
        if viewport_ampliado:
            pagina.set_viewport_size({"width": 1920, "height": 1080})
        if controle_acesso is not None:
            controle_acesso.antes_navegacao()
        pagina.goto(URL_LIGAS, wait_until="domcontentloaded", timeout=30000)
        pagina.locator("main:visible").first.wait_for(
            state="visible", timeout=15000
        )
        pagina.wait_for_timeout(500)
        if controle_acesso is not None:
            controle_acesso.validar_pagina(pagina)
        filtro_original = pagina.evaluate(
            "() => localStorage.getItem('packballFiltersLeagues')"
        )
        filtro_original_capturado = True
        coletado_em = datetime.now().replace(microsecond=0).isoformat()
        registros = []
        por_periodo = {}
        for periodo in PERIODOS:
            try:
                _configurar_periodo_persistido(
                    pagina,
                    periodo,
                    controle_acesso=controle_acesso,
                )
            except RuntimeError:
                _configurar_periodo(pagina, periodo)
            atuais = _ler_linhas_ligas(
                pagina, periodo, coletado_em=coletado_em
            )
            if not atuais:
                raise RuntimeError(f"taxas_ligas_packball_vazias:{periodo}")
            registros.extend(atuais)
            por_periodo[periodo] = len(atuais)
        return {
            "versao": VERSAO,
            "fonte": "packball_ligas_sazonal",
            "coletado_em": coletado_em,
            "registros": registros,
            "por_periodo": por_periodo,
            "viewport_desktop_temporario": viewport_ampliado,
        }
    finally:
        if filtro_original_capturado:
            try:
                pagina.evaluate("""valor => {
                  const chave = 'packballFiltersLeagues';
                  if (valor === null) localStorage.removeItem(chave);
                  else localStorage.setItem(chave, valor);
                }""", filtro_original)
            except Exception:
                pass
        if viewport_ampliado:
            pagina.set_viewport_size(viewport_original)


def limite_inferior_wilson(taxa, amostra, z=1.959963984540054):
    try:
        p = min(max(float(taxa), 0.0), 1.0)
        n = int(amostra)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    denominador = 1.0 + (z * z / n)
    centro = p + (z * z / (2.0 * n))
    margem = z * math.sqrt((p * (1.0 - p) / n) + (z * z / (4.0 * n * n)))
    return max((centro - margem) / denominador, 0.0)


def pontuar_taxa_liga(registro, amostra_minima=20):
    amostra = int((registro or {}).get("jogos_com_stats") or 0)
    if amostra < int(amostra_minima):
        return None
    limites = [
        limite_inferior_wilson((registro or {}).get(campo), amostra)
        for campo in ("over_0_5", "over_1_5", "over_2_5")
    ]
    if any(item is None for item in limites):
        return None
    return round(100.0 * sum(
        peso * valor
        for peso, valor in zip((0.65, 0.25, 0.10), limites)
    ), 3)


def periodo_da_tarefa(tarefa):
    status = str(((tarefa or {}).get("jogo") or {}).get("status") or "")
    if normalizar(status) in {"ht", "intervalo"}:
        return "1t"
    numeros = re.findall(r"\d{1,3}", status)
    minuto = int(numeros[0]) if numeros else None
    return "1t" if minuto is not None and minuto <= 45 else "2t"


def priorizar_tarefas_por_ligas(
    tarefas,
    registros,
    limiar_carga=15,
    amostra_minima=20,
):
    """Anota a fila; a ordenacao final continua sob o agendador operacional."""
    tarefas = list(tarefas or [])
    ativa = len(tarefas) >= int(limiar_carga)
    indice_id = {}
    indice_nome = {}
    for registro in registros or []:
        periodo = registro.get("periodo")
        score = pontuar_taxa_liga(registro, amostra_minima=amostra_minima)
        if periodo not in PERIODOS or score is None:
            continue
        item = {**registro, "score_wilson": score}
        liga_id = registro.get("league_id")
        if liga_id is not None:
            indice_id[(int(liga_id), periodo)] = item
        nome = registro.get("liga_normalizada") or normalizar(
            registro.get("liga")
        )
        if nome:
            indice_nome[(nome, periodo)] = item

    cobertas = 0
    pontuadas = 0
    for tarefa in tarefas:
        jogo = tarefa.get("jogo") or {}
        periodo = periodo_da_tarefa(tarefa)
        liga_id = extrair_liga_id(jogo.get("liga_url"))
        registro = indice_id.get((liga_id, periodo)) if liga_id else None
        if registro is None:
            registro = indice_nome.get((normalizar(jogo.get("liga_nome")), periodo))
        score = registro.get("score_wilson") if registro else None
        tarefa["prioridade_liga_gols"] = score if ativa else None
        tarefa["taxa_liga_gols"] = (
            {
                "league_id": registro.get("league_id"),
                "liga": registro.get("liga"),
                "temporada": registro.get("temporada"),
                "periodo": periodo,
                "jogos_com_stats": registro.get("jogos_com_stats"),
                "over_0_5": registro.get("over_0_5"),
                "over_1_5": registro.get("over_1_5"),
                "over_2_5": registro.get("over_2_5"),
                "score_wilson": score,
                "versao": VERSAO,
            }
            if registro else None
        )
        cobertas += registro is not None
        pontuadas += score is not None

    return tarefas, {
        "versao": VERSAO,
        "ativa": ativa,
        "motivo": "carga_alta" if ativa else "abaixo_limiar",
        "limiar_carga": int(limiar_carga),
        "tarefas": len(tarefas),
        "cobertas": cobertas,
        "pontuadas": pontuadas,
        "amostra_minima": int(amostra_minima),
        "somente_priorizacao": True,
        "altera_aprovacao_sinal": False,
        "reserva_diversidade": (
            "agendador_foco_rechecagem_nova_e_atrasada_preservados"
        ),
    }
