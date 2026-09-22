import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


PASTA_PROJETO = Path(__file__).parent
ARQUIVO_SESSAO = PASTA_PROJETO / "packball_session.json"
ARQUIVO_SAIDA = PASTA_PROJETO / "jogo_estruturado.json"

URL_PARTIDAS = "https://packball.com/pt/matches"


def separar_valores(texto):
    if not texto:
        return [0, 0]

    texto = texto.replace("%", "").strip()
    partes = re.split(r"\s*-\s*", texto)

    if len(partes) != 2:
        return [0, 0]

    valores = []

    for parte in partes:
        try:
            numero = float(parte.replace(",", "."))

            if numero.is_integer():
                numero = int(numero)

            valores.append(numero)

        except ValueError:
            valores.append(0)

    return valores


def procurar_odd(texto, mercado):
    padrao = rf"{re.escape(mercado)}:\s*([0-9.,]+)"
    resultado = re.search(padrao, texto, re.IGNORECASE)

    if not resultado:
        return None

    return float(
        resultado.group(1).replace(",", ".")
    )


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

    campos = {
        "chutes": "Chutes",
        "chutes_no_gol": "Chutes no gol",
        "pressao": "Índice de Pressão",
        "escanteios": "Escanteios",
        "posse": "Posse de bola",
        "cartoes": "Cartões",
        "chutes_area": "Chutes dentro da área",
        "chutes_fora_area": "Chutes fora da área",
        "gols": "Gols",
        "ataques_perigosos": "Ataques perigosos",
        "ataques": "Ataques",
    }

    textos_campos = pagina.evaluate(
        """
        campos => {
            const resultado = {};

            for (const [chave, titulo] of Object.entries(campos)) {
                const elemento = document.querySelector(
                    `[title="${titulo}"]`
                );

                resultado[chave] = elemento
                    ? elemento.innerText.trim()
                    : null;
            }

            return resultado;
        }
        """,
        campos,
    )

    titulo = pagina.title()
    nome_jogo = titulo.split(" Ao vivo")[0]

    if " x " in nome_jogo:
        mandante, visitante = nome_jogo.split(" x ", 1)
    else:
        mandante = "Mandante"
        visitante = "Visitante"

    corpo = pagina.locator("body").inner_text()

    status = "Ao vivo"

    if pagina.locator('[title="Intervalo"]').count() > 0:
        status = "Intervalo"

    if pagina.locator('[title="Finalizado"]').count() > 0:
        status = "Finalizado"

    # Extrai o bloco do mercado próximo gol
    bloco_proximo_gol = ""

    resultado_bloco = re.search(
        r"Marcar O Próximo Gol(.*?)(?:Ambas As Equipes|EVENTOS)",
        corpo,
        re.IGNORECASE | re.DOTALL,
    )

    if resultado_bloco:
        bloco_proximo_gol = resultado_bloco.group(1)

    odd_casa = procurar_odd(
        bloco_proximo_gol,
        "1",
    )

    odd_fora = procurar_odd(
        bloco_proximo_gol,
        "2",
    )

    odd_sem_gol = procurar_odd(
        bloco_proximo_gol,
        "No",
    )

    # Coleta a pressão minuto a minuto
    titulos_pressao = pagina.evaluate(
        """
        () => Array.from(
            document.querySelectorAll('[title^="Índice de pressão:"]')
        ).map(elemento => elemento.getAttribute("title"))
        """
    )

    pressao_minuto = []

    for titulo_pressao in titulos_pressao:
        resultado = re.search(
            r"pressão:\s*(\d+)\s*:\s*\((\d+)\)",
            titulo_pressao,
            re.IGNORECASE,
        )

        if resultado:
            pressao_minuto.append(
                {
                    "minuto": int(resultado.group(1)),
                    "valor": int(resultado.group(2)),
                }
            )

    dados = {
        "url": pagina.url,
        "mandante": mandante.strip(),
        "visitante": visitante.strip(),
        "status": status,
        "placar": textos_campos.get("gols"),
        "chutes": separar_valores(
            textos_campos.get("chutes")
        ),
        "chutes_no_gol": separar_valores(
            textos_campos.get("chutes_no_gol")
        ),
        "pressao": separar_valores(
            textos_campos.get("pressao")
        ),
        "escanteios": separar_valores(
            textos_campos.get("escanteios")
        ),
        "posse": separar_valores(
            textos_campos.get("posse")
        ),
        "cartoes": separar_valores(
            textos_campos.get("cartoes")
        ),
        "chutes_area": separar_valores(
            textos_campos.get("chutes_area")
        ),
        "chutes_fora_area": separar_valores(
            textos_campos.get("chutes_fora_area")
        ),
        "ataques_perigosos": separar_valores(
            textos_campos.get("ataques_perigosos")
        ),
        "ataques": separar_valores(
            textos_campos.get("ataques")
        ),
        "odds": {
            "proximo_gol_casa": odd_casa,
            "proximo_gol_fora": odd_fora,
            "sem_outro_gol": odd_sem_gol,
        },
        "pressao_minuto": pressao_minuto,
    }

    ARQUIVO_SAIDA.write_text(
        json.dumps(
            dados,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Coleta concluída!")
    print("Jogo:", mandante, "x", visitante)
    print("Placar:", dados["placar"])
    print("Chutes:", dados["chutes"])
    print("Chutes no gol:", dados["chutes_no_gol"])
    print("Pressão:", dados["pressao"])
    print("Ataques perigosos:", dados["ataques_perigosos"])
    print("Odds:", dados["odds"])
    print()
    print("Arquivo criado:")
    print(ARQUIVO_SAIDA)

    input("Pressione Enter para fechar...")
    navegador.close()