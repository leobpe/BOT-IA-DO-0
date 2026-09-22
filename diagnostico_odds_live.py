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

    url_live = urljoin(pagina.url, links.first.get_attribute("href"))
    url_odds = url_live.rsplit("/", 1)[0] + "/odds"
    pagina.goto(url_odds, wait_until="domcontentloaded", timeout=30000)
    pagina.wait_for_timeout(8000)

    candidatos_html = pagina.evaluate(
        r"""
        () => Array.from(document.querySelectorAll('*')).filter(el =>
          (el.innerText || '').trim() === 'Ao vivo'
        ).map(el => ({
          tag: el.tagName,
          classe: String(el.className || ''),
          html: el.outerHTML.slice(0, 1000),
          pai: el.parentElement?.outerHTML.slice(0, 2000) || ''
        }))
        """
    )
    print(json.dumps(candidatos_html, ensure_ascii=False, indent=2))

    clicou = pagina.evaluate(
        r"""
        () => {
          const limpar = v => (v || '').replace(/\s+/g, ' ').trim();
          const candidatos = Array.from(document.querySelectorAll('a, button, li, span'))
            .filter(el => limpar(el.innerText) === 'Ao vivo');
          const alvo = candidatos.find(el => {
            let pai = el.parentElement;
            for (let i = 0; i < 5 && pai; i++, pai = pai.parentElement) {
              if (limpar(pai.innerText).includes('Queda de Odds')) return true;
            }
            return false;
          });
          if (!alvo) return false;
          alvo.click();
          return true;
        }
        """
    )
    pagina.wait_for_timeout(4000)

    dados = pagina.evaluate(
        r"""
        () => {
          const limpar = v => (v || '').replace(/\s+/g, ' ').trim();
          return {
            url: location.href,
            clicou_ao_vivo: true,
            texto: limpar(document.body.innerText),
            blocos: Array.from(document.querySelectorAll(
              'table, section, [class*="odd"], [class*="market"]'
            )).map(el => ({
              tag: el.tagName,
              classe: String(el.className || ''),
              texto: limpar(el.innerText)
            })).filter(x =>
              /gol|goal|over|under|escanteio|corner/i.test(x.texto)
            ).slice(0, 100)
          };
        }
        """
    )
    print(json.dumps(dados, ensure_ascii=False, indent=2))
    navegador.close()
