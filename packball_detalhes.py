from pathlib import Path

from playwright.sync_api import sync_playwright


PASTA_PROJETO = Path(__file__).parent
ARQUIVO_SESSAO = PASTA_PROJETO / "packball_session.json"
ARQUIVO_DIAGNOSTICO = PASTA_PROJETO / "diagnostico_packball.txt"

URL_PARTIDAS = "https://packball.com/pt/matches"


if not ARQUIVO_SESSAO.exists():
    raise FileNotFoundError(
        "Sessão não encontrada. Execute primeiro:\n"
        "python packball_login.py"
    )


with sync_playwright() as p:
    navegador = p.chromium.launch(
        channel="chrome",
        headless=False,
        slow_mo=500,
    )

    contexto = navegador.new_context(
        storage_state=ARQUIVO_SESSAO,
    )

    pagina = contexto.new_page()

    print("Abrindo a lista de partidas...")

    pagina.goto(
        URL_PARTIDAS,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    pagina.wait_for_timeout(8000)

    # Verifica se a sessão está conectada
    campo_login = pagina.locator('input[name="email"]')

    if campo_login.is_visible():
        print("A sessão expirou.")
        print("Execute: python packball_login.py")

        input("Pressione Enter para fechar...")
        navegador.close()
        raise SystemExit(1)

    print("Procurando partidas...")

    # Localiza os links reais das partidas
    partidas = pagina.locator(
        'a[href*="/match/"], '
        'a[href*="/link-game/"]'
    )

    quantidade = partidas.count()

    print(f"Links de partidas encontrados: {quantidade}")

    if quantidade == 0:
        print("Nenhuma partida foi encontrada na página.")

        input("Pressione Enter para fechar...")
        navegador.close()
        raise SystemExit(1)

    # Pega o endereço antes de clicar
    primeira_partida = partidas.nth(0)
    link_partida = primeira_partida.get_attribute("href")

    print("Primeira partida:")
    print(link_partida)
    print("Clicando na partida...")

    # Clica na primeira partida encontrada
    primeira_partida.click()

    pagina.wait_for_timeout(10000)

    print("Página aberta:")
    print(pagina.url)

    # Verifica se continuou na lista
    if pagina.url.rstrip("/") == URL_PARTIDAS.rstrip("/"):
        print("O clique não abriu a partida.")
        print("Clique manualmente em qualquer jogo no navegador.")

        input(
            "Depois que a partida abrir, pressione Enter no terminal..."
        )

    print("Coletando os dados visíveis...")

    texto_pagina = pagina.locator("body").inner_text()

    linhas = []

    for linha in texto_pagina.splitlines():
        linha_limpa = " ".join(linha.split())

        if linha_limpa:
            linhas.append(linha_limpa)

    palavras_importantes = (
        "gol",
        "goal",
        "over",
        "under",
        "finaliza",
        "shot",
        "ataque",
        "attack",
        "posse",
        "possession",
        "escanteio",
        "corner",
        "odd",
        "média",
        "average",
        "ambas",
        "btts",
        "placar",
        "score",
        "minuto",
        "minute",
        "intervalo",
        "half",
        "ht",
        "ft",
    )

    linhas_relevantes = []

    for linha in linhas:
        linha_minuscula = linha.lower()

        if any(
            palavra in linha_minuscula
            for palavra in palavras_importantes
        ):
            linhas_relevantes.append(linha)

    resultado = [
        f"URL analisada: {pagina.url}",
        "",
        "DADOS RELEVANTES ENCONTRADOS:",
        "",
    ]

    resultado.extend(linhas_relevantes)

    ARQUIVO_DIAGNOSTICO.write_text(
        "\n".join(resultado),
        encoding="utf-8",
    )

    print()
    print(f"Linhas relevantes: {len(linhas_relevantes)}")
    print("Diagnóstico salvo em:")
    print(ARQUIVO_DIAGNOSTICO)

    print()
    print("Primeiras informações:")
    print()

    for linha in linhas_relevantes[:50]:
        print(linha)

    input("Pressione Enter para fechar o navegador...")
    navegador.close()