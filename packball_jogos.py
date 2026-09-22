from pathlib import Path

from playwright.sync_api import sync_playwright


PASTA_PROJETO = Path(__file__).parent
ARQUIVO_SESSAO = PASTA_PROJETO / "packball_session.json"

if not ARQUIVO_SESSAO.exists():
    raise FileNotFoundError(
        "Sessão não encontrada. Execute primeiro: "
        "python packball_login.py"
    )


with sync_playwright() as p:
    navegador = p.chromium.launch(
        channel="chrome",
        headless=False,
        slow_mo=300,
    )

    # Abre o navegador usando a sessão salva
    contexto = navegador.new_context(
        storage_state=ARQUIVO_SESSAO,
    )

    pagina = contexto.new_page()

    print("Abrindo a página de partidas...")

    pagina.goto(
        "https://packball.com/pt/matches",
        wait_until="domcontentloaded",
        timeout=30000,
    )

    pagina.wait_for_timeout(5000)

    # Verifica se a sessão expirou
    campo_login = pagina.locator('input[name="email"]')

    if campo_login.is_visible():
        print("A sessão não está conectada ou expirou.")
        print("Execute novamente: python packball_login.py")

        input("Pressione Enter para fechar...")
        navegador.close()
        raise SystemExit(1)

    print("Sessão conectada com sucesso!")
    print("Página atual:", pagina.url)

    # Coleta links que parecem pertencer a partidas
    links = pagina.locator("a").evaluate_all(
        """
        elementos => elementos.map(elemento => ({
            texto: (elemento.innerText || "").trim(),
            link: elemento.href || ""
        }))
        """
    )

    partidas = []
    links_encontrados = set()

    for item in links:
        link = item["link"]
        texto = item["texto"]

        parece_partida = (
            "/match/" in link
            or "/link-game/" in link
        )

        if (
            parece_partida
            and link not in links_encontrados
        ):
            links_encontrados.add(link)

            partidas.append(
                {
                    "texto": texto,
                    "link": link,
                }
            )

    print()
    print(f"Partidas encontradas: {len(partidas)}")
    print()

    for numero, partida in enumerate(
        partidas[:20],
        start=1,
    ):
        print(f"{numero}. {partida['texto']}")
        print(partida["link"])
        print("-" * 50)

    if not partidas:
        print("Nenhum link de partida foi identificado.")
        print("A página permanecerá aberta para verificação.")

    input("Pressione Enter para fechar o navegador...")
    navegador.close()