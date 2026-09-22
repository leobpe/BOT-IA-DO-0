import json
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from controle_acesso_packball import (
    ControleAcessoPackBall,
    PackBallBloqueadoError,
)
from controle_sistema import ler_modo_manutencao
from processo_monitor import gravar_json_atomico, trava_em_uso


URL_PARTIDAS = "https://packball.com/pt/matches"


def avaliar_pagina(pagina):
    campo_login = pagina.locator('input[name="email"]')
    if campo_login.count() and campo_login.is_visible():
        return {
            "status": "sessao_expirada",
            "acessivel": True,
            "autenticado": False,
            "contador_ao_vivo": None,
        }
    contador = pagina.locator("span.count-live:visible")
    texto = (contador.inner_text() or "").strip() if contador.count() else ""
    quantidade = int(texto) if texto.isdigit() else None
    return {
        "status": "acesso_confirmado",
        "acessivel": True,
        "autenticado": True,
        "contador_ao_vivo": quantidade,
    }


def executar_teste_controlado(pasta, headless=True):
    pasta = Path(pasta)
    resultado_path = pasta / "packball_teste_controlado.json"
    agora = datetime.now().replace(microsecond=0)
    base = {"verificado_em": agora.isoformat(), "navegacoes": 0}
    if not ler_modo_manutencao(pasta).get("ativo"):
        resultado = {
            **base,
            "status": "recusado",
            "motivo": "modo_manutencao_inativo",
        }
        gravar_json_atomico(resultado_path, resultado)
        return resultado
    if trava_em_uso(pasta / "monitor_instancia.lock"):
        resultado = {
            **base,
            "status": "recusado",
            "motivo": "monitor_ainda_ativo",
        }
        gravar_json_atomico(resultado_path, resultado)
        return resultado
    sessao = pasta / "packball_session.json"
    if not sessao.exists():
        resultado = {
            **base,
            "status": "recusado",
            "motivo": "sessao_ausente",
        }
        gravar_json_atomico(resultado_path, resultado)
        return resultado

    controle = ControleAcessoPackBall(
        pasta / "packball_acesso_estado.json"
    )
    navegador = None
    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(
                channel="chrome", headless=headless
            )
            contexto = navegador.new_context(storage_state=sessao)
            pagina = contexto.new_page()
            controle.antes_navegacao()
            pagina.goto(
                URL_PARTIDAS,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            base["navegacoes"] = 1
            controle.validar_pagina(pagina)
            pagina.wait_for_timeout(3000)
            controle.validar_pagina(pagina)
            resultado = {
                **base,
                **avaliar_pagina(pagina),
                "url_final": pagina.url,
            }
    except PackBallBloqueadoError as erro:
        resultado = {
            **base,
            "status": "bloqueado",
            "acessivel": False,
            "autenticado": False,
            "motivo": "excesso_solicitacoes_packball",
            "erro": str(erro),
        }
    except Exception as erro:
        resultado = {
            **base,
            "status": "erro",
            "acessivel": False,
            "autenticado": False,
            "motivo": type(erro).__name__,
            "erro": str(erro)[:500],
        }
    finally:
        if navegador is not None:
            try:
                if navegador.is_connected():
                    navegador.close()
            except Exception:
                pass
    gravar_json_atomico(resultado_path, resultado)
    return resultado


def main():
    resultado = executar_teste_controlado(Path(__file__).parent)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    raise SystemExit(
        0 if resultado.get("status") == "acesso_confirmado" else 1
    )


if __name__ == "__main__":
    main()
