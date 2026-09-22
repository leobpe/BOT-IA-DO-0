"""Confere a leitura real das tendencias de gols por periodo no PackBall."""

from pathlib import Path

from playwright.sync_api import sync_playwright

from tendencias_packball_ligas import coletar_tendencias_packball_liga


PASTA = Path(__file__).resolve().parent
URL = (
    "https://packball.com/pt/leagues/699/league/"
    "ecuador-liga-pro-serie-b/teams"
)


def main():
    jogo = {
        "liga_url": URL,
        "liga_nome": "Liga Pro Serie B",
        "mandante": "San Antonio",
        "visitante": "9 de Octubre",
    }
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(channel="msedge", headless=True)
        contexto_navegador = navegador.new_context(
            storage_state=PASTA / "packball_session.json",
            viewport={"width": 1920, "height": 1080},
        )
        pagina = contexto_navegador.new_page()
        for periodo in ("1t", "2t"):
            contexto = coletar_tendencias_packball_liga(
                pagina, jogo, periodo, cache={}
            )
            san_antonio = next(
                item for item in contexto["times"]
                if item["time"] == "San Antonio"
            )
            print("COLETA_REAL", periodo, san_antonio)
        navegador.close()


if __name__ == "__main__":
    main()
