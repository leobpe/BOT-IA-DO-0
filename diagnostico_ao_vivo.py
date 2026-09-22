from pathlib import Path

from playwright.sync_api import sync_playwright


PASTA_PROJETO = Path(__file__).parent
ARQUIVO_SESSAO = PASTA_PROJETO / "packball_session.json"
ARQUIVO_SAIDA = PASTA_PROJETO / "diagnostico_ao_vivo.txt"

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

    print("Abrindo as partidas do Packball...")

    pagina.goto(
        URL_PARTIDAS,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    pagina.wait_for_timeout(8000)

    print()
    print("No navegador:")
    print("1. Procure uma partida AO VIVO.")
    print("2. Clique na partida.")
    print("3. Aguarde as estatísticas carregarem.")
    print("4. Volte ao terminal e pressione Enter.")
    print()

    input("Pressione Enter após abrir um jogo ao vivo...")

    pagina.wait_for_timeout(5000)

    print("Coletando dados do jogo ao vivo...")

    texto_pagina = pagina.locator("body").inner_text()

    linhas = []

    for linha in texto_pagina.splitlines():
        linha_limpa = " ".join(linha.split())

        if linha_limpa:
            linhas.append(linha_limpa)

    resultado = [
        f"URL analisada: {pagina.url}",
        "",
        "CONTEÚDO VISÍVEL DA PARTIDA:",
        "",
    ]

    # Limita o diagnóstico para evitar o rodapé enorme
    resultado.extend(linhas[:500])

    ARQUIVO_SAIDA.write_text(
        "\n".join(resultado),
        encoding="utf-8",
    )

    print()
    print("Diagnóstico salvo em:")
    print(ARQUIVO_SAIDA)
    print()
    print(f"Linhas coletadas: {min(len(linhas), 500)}")

    input("Pressione Enter para fechar o navegador...")
    navegador.close()