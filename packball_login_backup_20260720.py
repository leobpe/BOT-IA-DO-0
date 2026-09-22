import os
import re
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

PASTA = Path(__file__).resolve().parent
load_dotenv(PASTA / ".env")

EMAIL = os.getenv("PACKBALL_EMAIL")
SENHA = os.getenv("PACKBALL_PASSWORD")
ARQUIVO_SESSAO = PASTA / "packball_session.json"

if not EMAIL or not SENHA:
    raise ValueError(
        "E-mail ou senha do PackBall não encontrados no .env"
    )


def localizar_campo(pagina, seletores):
    for seletor in seletores:
        campo = pagina.locator(seletor).first

        try:
            campo.wait_for(
                state="visible",
                timeout=10000,
            )
            return campo
        except Exception:
            continue

    return None


with sync_playwright() as p:
    navegador = p.chromium.launch(
        headless=False
    )

    contexto = navegador.new_context()
    pagina = contexto.new_page()

    pagina.goto(
        "https://packball.com/en/login",
        wait_until="domcontentloaded",
        timeout=60000,
    )

    pagina.wait_for_timeout(3000)

    campo_email = localizar_campo(
        pagina,
        [
            "input[type='email']",
            "input[name='email']",
            "input[placeholder*='mail' i]",
        ],
    )

    campo_senha = localizar_campo(
        pagina,
        [
            "input[type='password']",
            "input[name='password']",
            "input[placeholder*='assword' i]",
        ],
    )

    if campo_email is None or campo_senha is None:
        print("Campos de login não encontrados.")
        print(f"URL atual: {pagina.url}")
        input(
            "Preencha o login manualmente e pressione Enter..."
        )
    else:
        campo_email.fill(EMAIL)
        campo_senha.fill(SENHA)

        botao = pagina.get_by_role(
            "button",
            name=re.compile(
                r"login|entrar|sign in",
                re.IGNORECASE,
            ),
        ).first

        botao.click()

    pagina.wait_for_timeout(5000)

    if "/login" in pagina.url:
        print(
            "Login ainda não confirmado."
        )
        input(
            "Finalize o login no navegador e pressione Enter..."
        )

    if "/login" not in pagina.url:
        print("Login realizado com sucesso!")
        contexto.storage_state(
            path=ARQUIVO_SESSAO
        )
        print(
            "Sessão salva em packball_session.json"
        )
    else:
        print(
            "Sessão não foi salva porque o login não foi confirmado."
        )

    input("Pressione Enter para fechar...")
    navegador.close()