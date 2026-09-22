import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from banco import BancoMonitor
from bet365_odds import (
    eventos_correspondentes_bet365,
    registrar_observacao_bet365,
)


PASTA = Path(__file__).parent
URL_AO_VIVO = "https://www.bet365.bet.br/#/IP/B1"
SCRIPT_EVENTOS = r"""
() => Array.from(document.querySelectorAll('.ovm-Fixture')).map(
    (elemento, indice) => {
        const nomes = Array.from(
            elemento.querySelectorAll('.ovm-FixtureDetailsTwoWay_TeamName')
        ).map(item => (item.innerText || '').replace(/\s+/g, ' ').trim());
        return {
            indice,
            mandante: nomes[0] || '',
            visitante: nomes[1] || '',
            texto: (elemento.innerText || '')
                .replace(/\s+/g, ' ').trim().slice(0, 300)
        };
    }
).filter(item => item.mandante && item.visitante)
"""
SCRIPT_PAINEL = r"""
() => {
    const visivel = elemento => Boolean(
        elemento && (
            elemento.offsetWidth || elemento.offsetHeight ||
            elemento.getClientRects().length
        )
    );
    const textoCorpo = (document.body?.innerText || '')
        .replace(/\s+/g, ' ').trim();
    const bloqueado = /acesso negado|muitas solicitações|verifique que você é humano|temporariamente bloqueado/i
        .test(textoCorpo);
    const carregadores = Array.from(document.querySelectorAll(
        '[class*="Spinner"], [class*="Loading"], [class*="Preloader"]'
    )).filter(visivel).length;
    const candidatos = Array.from(document.querySelectorAll(
        '[class*="Market"], [class*="Coupon"]'
    )).map(elemento => ({
        classe: String(elemento.className || ''),
        texto: (elemento.innerText || '')
            .replace(/\s+/g, ' ').trim()
    })).filter(item =>
        /escanteio|corner/i.test(item.texto) &&
        item.texto.length > 0 && item.texto.length <= 1500
    );
    const unicos = [];
    const chaves = new Set();
    for (const item of candidatos) {
        const chave = `${item.classe}|${item.texto}`;
        if (!chaves.has(chave)) {
            chaves.add(chave);
            unicos.push(item);
        }
        if (unicos.length >= 20) break;
    }
    return {
        url: location.href,
        bloqueado,
        carregadores,
        texto_corpo: textoCorpo.slice(0, 10000),
        mercados_escanteios: unicos
    };
}
"""


def _texto_normalizado(valor):
    return " ".join(str(valor or "").casefold().split())


def _painel_confirma_evento(painel, mandante=None, visitante=None):
    if not mandante or not visitante:
        return None
    texto = _texto_normalizado((painel or {}).get("texto_corpo"))
    return bool(
        _texto_normalizado(mandante) in texto
        and _texto_normalizado(visitante) in texto
    )


def classificar_painel_bet365(
    painel, mandante=None, visitante=None
):
    painel = painel or {}
    if painel.get("bloqueado"):
        return "bloqueado", "bloqueio_ou_verificacao_humana"
    evento_confirmado = _painel_confirma_evento(
        painel, mandante, visitante
    )
    if evento_confirmado is False:
        return (
            "painel_nao_carregou",
            "evento_selecionado_nao_substituiu_painel",
        )
    if painel.get("mercados_escanteios"):
        return "mercado_rejeitado", "estrutura_dom_aguardando_mapeamento"
    if int(painel.get("carregadores", 0) or 0) > 0:
        return "painel_nao_carregou", "carregamento_nao_concluido"
    return "mercado_ausente", "escanteios_nao_exibidos"


def _evento_id_da_url(url):
    encontrado = re.search(r"/(EV\d+)", str(url or ""))
    return encontrado.group(1) if encontrado else None


def executar_diagnostico(
    mandante,
    visitante,
    *,
    headless=False,
    caminho_banco=None,
):
    caminho_banco = Path(caminho_banco or PASTA / "monitor_packball.db")
    banco = BancoMonitor(caminho_banco)
    navegador = None
    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(
                channel="msedge", headless=bool(headless)
            )
            contexto = navegador.new_context()
            pagina = contexto.new_page()
            pagina.goto(
                URL_AO_VIVO,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            try:
                pagina.wait_for_selector(
                    ".ovm-Fixture", state="visible", timeout=15000
                )
            except PlaywrightTimeoutError:
                painel = pagina.evaluate(SCRIPT_PAINEL)
                estado, motivo = classificar_painel_bet365(painel)
                if estado not in ("bloqueado", "painel_nao_carregou"):
                    estado, motivo = (
                        "painel_nao_carregou",
                        "lista_ao_vivo_nao_carregou",
                    )
                registrar_observacao_bet365(
                    banco.conexao,
                    estado,
                    motivo=motivo,
                    url_origem=pagina.url,
                )
                return {
                    "estado": estado,
                    "motivo": motivo,
                    "partida_aberta": False,
                    "navegacoes": 1,
                }

            eventos = pagina.evaluate(SCRIPT_EVENTOS) or []
            correspondentes = eventos_correspondentes_bet365(
                eventos, mandante, visitante
            )
            if len(correspondentes) != 1:
                estado = (
                    "jogo_nao_encontrado"
                    if not correspondentes else "jogo_ambiguo"
                )
                registrar_observacao_bet365(
                    banco.conexao,
                    estado,
                    mandante_observado=mandante,
                    visitante_observado=visitante,
                    motivo=estado,
                    url_origem=pagina.url,
                )
                return {
                    "estado": estado,
                    "motivo": estado,
                    "partida_aberta": False,
                    "correspondencias": len(correspondentes),
                    "navegacoes": 1,
                }

            evento = correspondentes[0]
            partidas = pagina.locator(".ovm-Fixture")
            indice = int(evento["indice"])
            if indice < 0 or indice >= partidas.count():
                raise RuntimeError("A lista da Bet365 mudou durante a seleção.")
            alvo = partidas.nth(indice).locator(
                ".ovm-FixtureDetailsTwoWay_Wrapper"
            )
            if alvo.count() != 1:
                raise RuntimeError("O evento Bet365 não possui clique único.")
            alvo.click(timeout=5000)
            try:
                pagina.wait_for_function(
                    "() => /#\\/IP\\/EV\\d+/.test(location.hash)",
                    timeout=5000,
                )
            except PlaywrightTimeoutError:
                pass
            try:
                pagina.wait_for_function(
                    r"""() => {
                        const texto = document.body?.innerText || '';
                        const mercado = /escanteio|corner/i.test(texto);
                        const bloqueio = /acesso negado|muitas solicitações|verifique que você é humano|temporariamente bloqueado/i.test(texto);
                        return mercado || bloqueio;
                    }""",
                    timeout=8000,
                )
            except PlaywrightTimeoutError:
                pass
            painel = pagina.evaluate(SCRIPT_PAINEL)
            estado, motivo = classificar_painel_bet365(
                painel, evento["mandante"], evento["visitante"]
            )
            evento_id = _evento_id_da_url(painel.get("url"))
            evento_painel_confirmado = _painel_confirma_evento(
                painel, evento["mandante"], evento["visitante"]
            )
            mercado_texto = None
            if painel.get("mercados_escanteios"):
                mercado_texto = painel["mercados_escanteios"][0]["texto"]
            registrar_observacao_bet365(
                banco.conexao,
                estado,
                evento_externo_id=evento_id,
                mandante_observado=evento["mandante"],
                visitante_observado=evento["visitante"],
                mercado=mercado_texto,
                motivo=motivo,
                url_origem=painel.get("url"),
            )
            return {
                "estado": estado,
                "motivo": motivo,
                "partida_aberta": bool(evento_id),
                "evento_id": evento_id,
                "mandante": evento["mandante"],
                "visitante": evento["visitante"],
                "evento_painel_confirmado": evento_painel_confirmado,
                "mercados_candidatos": len(
                    painel.get("mercados_escanteios") or []
                ),
                "navegacoes": 2,
            }
    finally:
        if navegador is not None:
            try:
                navegador.close()
            except Exception:
                pass
        banco.fechar()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Abre uma única partida pública da Bet365 e registra o "
            "diagnóstico, sem login e sem aposta."
        )
    )
    parser.add_argument("--mandante", required=True)
    parser.add_argument("--visitante", required=True)
    parser.add_argument("--headless", action="store_true")
    argumentos = parser.parse_args()
    resultado = executar_diagnostico(
        argumentos.mandante,
        argumentos.visitante,
        headless=argumentos.headless,
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
