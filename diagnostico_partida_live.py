import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


PASTA = Path(__file__).parent
SESSAO = PASTA / "packball_session.json"


with sync_playwright() as p:
    navegador = p.chromium.launch(channel="msedge", headless=True)
    contexto = navegador.new_context(storage_state=SESSAO)
    pagina = contexto.new_page()
    pagina.goto("https://packball.com/pt/matches", wait_until="domcontentloaded")
    pagina.wait_for_timeout(7000)
    pagina.locator("span.count-live").click()
    pagina.wait_for_timeout(3000)

    links = pagina.locator('ul.row a[href$="/live"]')
    if links.count() == 0:
        raise RuntimeError("Nenhuma partida ao vivo encontrada.")

    url = urljoin(pagina.url, links.first.get_attribute("href"))
    pagina.goto(url, wait_until="domcontentloaded", timeout=30000)
    pagina.wait_for_timeout(8000)

    dados = pagina.evaluate(
        r"""
        () => {
          const limpar = v => (v || '').replace(/\s+/g, ' ').trim();
          return {
            url: location.href,
            linhas: limpar(document.body.innerText).split(/\n+/).slice(0, 500),
            candidatos: Array.from(document.querySelectorAll('[title], li, tr'))
              .map(el => ({
                tag: el.tagName,
                classe: String(el.className || ''),
                title: el.getAttribute('title') || '',
                texto: limpar(el.innerText)
              }))
              .filter(x => /press|shot|chute|finaliza|attack|ataque|posse|possession|corner|escanteio/i.test(x.title + ' ' + x.texto))
              .slice(0, 200)
          };
        }
        """
    )
    print(json.dumps(dados, ensure_ascii=False, indent=2))
    navegador.close()
