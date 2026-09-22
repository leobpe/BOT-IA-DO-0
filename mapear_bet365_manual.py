import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


PASTA = Path(__file__).parent
URL_AO_VIVO = "https://www.bet365.bet.br/#/IP/B1"
PASTA_SAIDA = PASTA / "capturas_bet365"
ARQUIVO_SINAL = PASTA / ".capturar_bet365_agora"


SCRIPT_CAPTURA = r"""
() => {
    const visivel = elemento => Boolean(
        elemento && (
            elemento.offsetWidth ||
            elemento.offsetHeight ||
            elemento.getClientRects().length
        )
    );
    const limpar = valor => String(valor || '')
        .replace(/\s+/g, ' ')
        .trim();
    const seletores = [
        '[class*="Market"]',
        '[class*="Coupon"]',
        '[class*="Participant"]',
        '[class*="Expandable"]'
    ];
    const candidatos = Array.from(
        document.querySelectorAll(seletores.join(','))
    ).filter(visivel).map(elemento => {
        const selecoes = Array.from(elemento.querySelectorAll(
            '[class*="Participant"], [class*="Odds"], button'
        )).filter(visivel).map(selecao => ({
            classe: limpar(selecao.className),
            texto: limpar(selecao.innerText),
            aria_label: limpar(selecao.getAttribute('aria-label'))
        })).filter(item => item.texto || item.aria_label).slice(0, 100);
        return {
            classe: limpar(elemento.className),
            texto: limpar(elemento.innerText),
            selecoes,
            html: String(elemento.outerHTML || '').slice(0, 30000)
        };
    }).filter(item =>
        item.texto &&
        item.texto.length <= 2500 &&
        /escanteio|corner|asi[aá]tic/i.test(item.texto)
    );
    const mercados = [];
    const vistos = new Set();
    for (const item of candidatos) {
        const chave = `${item.classe}|${item.texto}`;
        if (!vistos.has(chave)) {
            vistos.add(chave);
            mercados.push(item);
        }
        if (mercados.length >= 100) break;
    }
    return {
        url: location.href,
        titulo: document.title,
        capturado_em: new Date().toISOString(),
        texto_visivel: limpar(document.body?.innerText),
        mercados_escanteios: mercados
    };
}
"""


def criar_caminhos_captura(agora=None):
    agora = agora or datetime.now()
    identificador = agora.strftime("%Y%m%d_%H%M%S")
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    return {
        "json": PASTA_SAIDA / f"bet365_{identificador}.json",
        "txt": PASTA_SAIDA / f"bet365_{identificador}.txt",
        "imagem": PASTA_SAIDA / f"bet365_{identificador}.png",
    }


def aguardar_sinal(caminho_sinal, timeout_segundos=1800):
    caminho_sinal = Path(caminho_sinal)
    inicio = time.monotonic()
    while not caminho_sinal.exists():
        if time.monotonic() - inicio >= timeout_segundos:
            raise TimeoutError(
                "Tempo esgotado aguardando o sinal de captura."
            )
        time.sleep(0.5)
    caminho_sinal.unlink(missing_ok=True)


def executar(*, aguardar_comando=False):
    caminhos = criar_caminhos_captura()
    if aguardar_comando:
        ARQUIVO_SINAL.unlink(missing_ok=True)
    navegador = None
    with sync_playwright() as playwright:
        try:
            navegador = playwright.chromium.launch(
                channel="msedge",
                headless=False,
                slow_mo=150,
            )
            contexto = navegador.new_context(
                viewport={"width": 1440, "height": 900}
            )
            pagina = contexto.new_page()
            pagina.goto(
                URL_AO_VIVO,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            print()
            print("BET365 ABERTA PARA NAVEGACAO MANUAL")
            print("1. Clique em uma partida de futebol ao vivo.")
            print("2. Abra a categoria Escanteios.")
            print("3. Expanda Escanteios Asiaticos, se existir.")
            print("4. Deixe as linhas e odds visiveis.")
            print()
            if aguardar_comando:
                print(
                    'Quando estiver pronto, diga "pronto" na conversa.'
                )
                aguardar_sinal(ARQUIVO_SINAL)
            else:
                input("Quando estiver pronto, pressione Enter aqui...")

            pagina.wait_for_timeout(1500)
            dados = pagina.evaluate(SCRIPT_CAPTURA)
            pagina.screenshot(
                path=str(caminhos["imagem"]),
                full_page=True,
            )
            caminhos["json"].write_text(
                json.dumps(dados, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            caminhos["txt"].write_text(
                (
                    f"URL: {dados['url']}\n"
                    f"TÍTULO: {dados['titulo']}\n"
                    f"CAPTURADO EM: {dados['capturado_em']}\n\n"
                    "MERCADOS DE ESCANTEIOS:\n\n"
                    + "\n\n".join(
                        item["texto"]
                        for item in dados["mercados_escanteios"]
                    )
                    + "\n\nTEXTO VISÍVEL:\n\n"
                    + dados["texto_visivel"]
                ),
                encoding="utf-8",
            )

            print()
            print("Captura concluida:")
            print(caminhos["imagem"])
            print(caminhos["txt"])
            print(caminhos["json"])
            input("Pressione Enter para fechar...")
        finally:
            if navegador is not None:
                try:
                    navegador.close()
                except Exception:
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Captura a tela da Bet365 depois da navegação manual do usuário."
        )
    )
    parser.add_argument(
        "--aguardar-sinal",
        action="store_true",
        help=(
            "Aguarda um sinal local enviado pela conversa, sem exigir Enter."
        ),
    )
    argumentos = parser.parse_args()
    executar(aguardar_comando=argumentos.aguardar_sinal)
