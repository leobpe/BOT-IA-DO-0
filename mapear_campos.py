import json
from pathlib import Path

from playwright.sync_api import sync_playwright


PASTA_PROJETO = Path(__file__).parent
ARQUIVO_SESSAO = PASTA_PROJETO / "packball_session.json"
ARQUIVO_SAIDA = PASTA_PROJETO / "mapa_campos_packball.json"

URL_PARTIDAS = "https://packball.com/pt/matches"


if not ARQUIVO_SESSAO.exists():
    raise FileNotFoundError(
        "Sessão não encontrada. Execute:\n"
        "python packball_login.py"
    )


with sync_playwright() as p:
    navegador = p.chromium.launch(
        channel="chrome",
        headless=False,
        slow_mo=300,
    )

    contexto = navegador.new_context(
        storage_state=ARQUIVO_SESSAO,
    )

    pagina = contexto.new_page()

    print("Abrindo o Packball...")

    pagina.goto(
        URL_PARTIDAS,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    pagina.wait_for_timeout(8000)

    print()
    print("Abra uma partida ao vivo ou no intervalo.")
    print("Aguarde as estatísticas carregarem.")
    print()

    input("Depois, pressione Enter no terminal...")

    pagina.wait_for_timeout(5000)

    print("Mapeando campos e ícones...")

    dados = pagina.evaluate(
        """
        () => {
            const limpar = texto =>
                (texto || "").replace(/\\s+/g, " ").trim();

            const metadados = Array.from(
                document.querySelectorAll(
                    "[title], [aria-label], [alt], " +
                    "[data-original-title], " +
                    "[data-bs-original-title]"
                )
            ).map(elemento => ({
                tag: elemento.tagName,
                classe: elemento.className || "",
                title: elemento.getAttribute("title") || "",
                ariaLabel:
                    elemento.getAttribute("aria-label") || "",
                alt: elemento.getAttribute("alt") || "",
                dataOriginalTitle:
                    elemento.getAttribute(
                        "data-original-title"
                    ) || "",
                dataBsOriginalTitle:
                    elemento.getAttribute(
                        "data-bs-original-title"
                    ) || "",
                texto: limpar(elemento.innerText),
                textoPai: limpar(
                    elemento.parentElement?.innerText
                ).slice(0, 500)
            })).filter(item =>
                item.title ||
                item.ariaLabel ||
                item.alt ||
                item.dataOriginalTitle ||
                item.dataBsOriginalTitle
            );

            const regexValor =
                /^\\d+(?:[.,]\\d+)?%?\\s*-\\s*\\d+(?:[.,]\\d+)?%?$/;

            const valores = Array.from(
                document.querySelectorAll("body *")
            ).map(elemento => ({
                elemento,
                texto: limpar(elemento.innerText)
            })).filter(item =>
                regexValor.test(item.texto)
            ).slice(0, 100).map(item => ({
                valor: item.texto,
                tag: item.elemento.tagName,
                classe: item.elemento.className || "",
                textoPai: limpar(
                    item.elemento.parentElement?.innerText
                ).slice(0, 1000),
                textoAvo: limpar(
                    item.elemento.parentElement
                        ?.parentElement?.innerText
                ).slice(0, 1500),
                htmlPai: (
                    item.elemento.parentElement
                        ?.outerHTML || ""
                ).slice(0, 3000)
            }));

            return {
                url: window.location.href,
                titulo: document.title,
                metadados,
                valores
            };
        }
        """
    )

    ARQUIVO_SAIDA.write_text(
        json.dumps(
            dados,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Mapeamento concluído:")
    print(ARQUIVO_SAIDA)
    print()
    print(
        "Campos com metadados:",
        len(dados["metadados"]),
    )
    print(
        "Valores estatísticos:",
        len(dados["valores"]),
    )

    input("Pressione Enter para fechar...")
    navegador.close()