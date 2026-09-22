import json
from pathlib import Path

from playwright.sync_api import sync_playwright


PASTA = Path(__file__).parent
SESSAO = PASTA / "packball_session.json"


with sync_playwright() as p:
    navegador = p.chromium.launch(channel="msedge", headless=True)
    contexto = navegador.new_context(storage_state=SESSAO)
    pagina = contexto.new_page()
    pagina.goto(
        "https://packball.com/pt/matches",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    pagina.wait_for_timeout(8000)

    scanner = pagina.locator("li:has(i.filter):visible").first
    scanner_encontrado = scanner.count() == 1 and scanner.is_visible()
    if scanner_encontrado:
        scanner.locator("a").click(timeout=5000)
        pagina.wait_for_timeout(3000)

    dados = pagina.evaluate(
        r"""
        () => Array.from(document.querySelectorAll('ul.row')).map(linha => {
            const limpar = valor => (valor || '').replace(/\s+/g, ' ').trim();
            const link = linha.querySelector('a[href*="/match/"]');
            const blin = linha.querySelector('.blin');
            return {
                classe: linha.className,
                url: link?.href || '',
                status_texto: limpar(blin?.innerText),
                status_title: limpar(blin?.querySelector('[title]')?.title),
                mandante: limpar(linha.querySelector('.team-home, .team-name-home')?.innerText),
                visitante: limpar(linha.querySelector('.team-away, .team-name-away')?.innerText),
                placar: limpar(linha.querySelector('.result-f')?.innerText),
                texto: limpar(linha.innerText),
                colunas: Array.from(linha.children).map((coluna, indice) => ({
                    indice,
                    tag: coluna.tagName,
                    classe: String(coluna.className || ''),
                    texto: limpar(coluna.innerText),
                    title: limpar(coluna.getAttribute('title')),
                    titulos_internos: Array.from(
                        coluna.querySelectorAll('[title]')
                    ).map(el => limpar(el.getAttribute('title'))).filter(Boolean),
                    classes_icones: Array.from(
                        coluna.querySelectorAll('i, svg, img')
                    ).map(el => String(el.className?.baseVal || el.className || '')),
                    html: coluna.outerHTML.slice(0, 1200),
                }))
            };
        }).filter(item => item.url)
        """
    )

    cabecalhos = pagina.evaluate(
        r"""
        () => Array.from(document.querySelectorAll(
            'ul:not(.row) > li, thead th, [class*="header"] [title]'
        )).map((el, indice) => ({
            indice,
            tag: el.tagName,
            classe: String(el.className || ''),
            texto: (el.innerText || '').replace(/\s+/g, ' ').trim(),
            title: el.getAttribute('title') || '',
            titulos_internos: Array.from(el.querySelectorAll('[title]'))
                .map(x => x.getAttribute('title')).filter(Boolean),
            html: el.outerHTML.slice(0, 800),
        })).filter(x => x.texto || x.title || x.titulos_internos.length)
        """
    )

    controles = pagina.evaluate(
        r"""
        () => Array.from(document.querySelectorAll('*')).map(el => {
          const r = el.getBoundingClientRect();
          return ({
            tag: el.tagName,
            classe: String(el.className || ''),
            title: el.getAttribute('title') || '',
            aria: el.getAttribute('aria-label') || '',
            texto: (el.innerText || '').replace(/\s+/g, ' ').trim(),
            html: el.outerHTML.slice(0, 500),
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height)
          });
        }).filter(x => x.y >= 0 && x.y < 80 && x.x > 250 && x.x < 650 && x.w < 300)
        """
    )

    resumo_scanner = pagina.evaluate(
        r"""
        () => ({
          texto: (document.body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 4000),
          linhas: document.querySelectorAll('ul.row').length,
          links: Array.from(document.querySelectorAll(
            'a[href*="/match/"], a[href*="/link-game/"]'
          )).map(a => a.href),
          botoes: Array.from(document.querySelectorAll('button, a')).map(el =>
            (el.innerText || '').replace(/\s+/g, ' ').trim()
          ).filter(Boolean).slice(0, 100),
        })
        """
    )

    amostra_ao_vivo = []
    cabecalhos_por_codigo = []
    estrutura_cabecalho = []
    if not dados:
        ao_vivo = pagina.locator("li:has(.count-live):visible").first
        if ao_vivo.count() == 1 and ao_vivo.is_visible():
            ao_vivo.locator("a").click(timeout=5000)
            pagina.wait_for_timeout(2500)
            amostra_ao_vivo = pagina.evaluate(
                r"""
                () => {
                  const limpar = valor => (valor || '')
                    .replace(/\s+/g, ' ').trim();
                  const linha = Array.from(
                    document.querySelectorAll('ul.row')
                  ).find(x => x.querySelector('a[href*="/match/"]'));
                  if (!linha) return [];
                  return Array.from(linha.children).map((coluna, indice) => ({
                    indice,
                    classe: String(coluna.className || ''),
                    texto: limpar(coluna.innerText),
                    title: limpar(coluna.getAttribute('title')),
                    titulos: Array.from(coluna.querySelectorAll('[title]'))
                      .map(x => limpar(x.getAttribute('title'))).filter(Boolean),
                    atributos: Object.fromEntries(
                      Array.from(coluna.attributes || []).map(a => [a.name, a.value])
                    ),
                    html: '',
                  }));
                }
                """
            )
            cabecalhos_por_codigo = pagina.evaluate(
                r"""
                () => {
                  const linha = Array.from(document.querySelectorAll('ul.row'))
                    .find(x => x.querySelector('a[href*="/match/"]'));
                  const codigos = Array.from(linha?.children || [])
                    .flatMap(el => Array.from(el.classList || []))
                    .filter(x => /^c\d+$/.test(x));
                  return Array.from(new Set(codigos)).map(codigo => ({
                    codigo,
                    elementos: Array.from(document.querySelectorAll('.' + codigo))
                      .filter(el => !el.closest('ul.row'))
                      .slice(0, 4)
                      .map(el => ({
                        tag: el.tagName,
                        classe: String(el.className || ''),
                        texto: (el.innerText || '').replace(/\s+/g, ' ').trim(),
                        title: el.getAttribute('title') || '',
                        aria: el.getAttribute('aria-label') || '',
                        html: el.outerHTML.slice(0, 1000),
                      })),
                  }));
                }
                """
            )
            estrutura_cabecalho = pagina.evaluate(
                r"""
                () => Array.from(
                  document.querySelector('ul.header')?.children || []
                ).map((el, indice) => ({
                  indice,
                  classe: String(el.className || ''),
                  texto: (el.innerText || '').replace(/\s+/g, ' ').trim(),
                  title: el.getAttribute('title') || '',
                  titulos: Array.from(el.querySelectorAll('[title]'))
                    .map(x => x.getAttribute('title')).filter(Boolean),
                }))
                """
            )

    print(json.dumps({
        "scanner_encontrado": scanner_encontrado,
        "estrutura_cabecalho": estrutura_cabecalho,
    }, ensure_ascii=False, indent=2))
    navegador.close()
