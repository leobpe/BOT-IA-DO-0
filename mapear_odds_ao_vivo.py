import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


PASTA = Path(__file__).parent
SESSAO = PASTA / "packball_session.json"
SAIDA_TXT = PASTA / "odds_ao_vivo_mapeadas.txt"
SAIDA_JSON = PASTA / "odds_ao_vivo_mapeadas.json"


if not SESSAO.exists():
    raise FileNotFoundError(
        "Sessão não encontrada. Execute: python packball_login.py"
    )


with sync_playwright() as p:
    navegador = p.chromium.launch(
        channel="msedge",
        headless=False,
        slow_mo=300,
    )
    contexto = navegador.new_context(storage_state=SESSAO)
    pagina = contexto.new_page()

    pagina.goto(
        "https://packball.com/pt/matches",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    pagina.wait_for_timeout(7000)
    pagina.locator("span.count-live").click()
    pagina.wait_for_timeout(3000)

    links = pagina.locator('ul.row a[href$="/live"]')
    if links.count() == 0:
        raise RuntimeError("Nenhuma partida ao vivo encontrada.")

    url_live = urljoin(pagina.url, links.first.get_attribute("href"))
    url_odds = url_live.rsplit("/", 1)[0] + "/odds"
    pagina.goto(url_odds, wait_until="domcontentloaded", timeout=30000)
    pagina.wait_for_timeout(5000)

    print()
    print("No navegador:")
    print("1. Confirme que está na aba Odds.")
    print("2. Clique na terceira opção: Ao vivo.")
    print("3. Aguarde os mercados carregarem.")
    print()
    input("Depois disso, pressione Enter neste terminal...")

    pagina.wait_for_timeout(3000)
    dados = pagina.evaluate(
        r"""
        () => {
          const limpar = v => (v || '').replace(/\s+/g, ' ').trim();
          const artigos = Array.from(
            document.querySelectorAll('article.item.all-odds')
          );
          return {
            url: location.href,
            titulo_odds: limpar(
              Array.from(document.querySelectorAll('body *'))
                .find(el => /ODDS.*VIVO/i.test(limpar(el.innerText)))
                ?.innerText
            ).slice(0, 300),
            mercados: artigos.map(artigo => ({
              mercado: limpar(
                artigo.querySelector('.title-market')?.innerText ||
                artigo.querySelector('section')?.innerText
              ),
              texto: limpar(artigo.innerText),
              html: artigo.outerHTML.slice(0, 10000)
            })),
            texto_visivel: limpar(document.body.innerText)
          };
        }
        """
    )

    SAIDA_JSON.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    SAIDA_TXT.write_text(
        "URL: " + dados["url"] + "\n\n" +
        "MERCADOS:\n\n" +
        "\n\n".join(
            item["texto"] for item in dados["mercados"]
        ) +
        "\n\nCONTEÚDO VISÍVEL:\n\n" + dados["texto_visivel"],
        encoding="utf-8",
    )

    print()
    print("Mapeamento salvo em:")
    print(SAIDA_TXT)
    print(SAIDA_JSON)
    input("Pressione Enter para fechar o navegador...")
    navegador.close()
