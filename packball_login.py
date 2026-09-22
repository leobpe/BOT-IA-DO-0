import os
import argparse
import base64
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from controle_acesso_packball import (
    ControleAcessoPackBall,
    PackBallBloqueadoError,
)
from processo_monitor import gravar_json_atomico


PASTA_PROJETO = Path(__file__).parent
ARQUIVO_ENV = PASTA_PROJETO / ".env"
ARQUIVO_SESSAO = PASTA_PROJETO / "packball_session.json"
URL_LOGIN = "https://packball.com/en/login"
URL_PARTIDAS = "https://packball.com/pt/matches"

load_dotenv(ARQUIVO_ENV)


def _criar_controle_acesso():
    """Usa no login exatamente o mesmo ritmo seguro do monitor."""
    return ControleAcessoPackBall(
        PASTA_PROJETO / "packball_acesso_estado.json",
        intervalo_minimo_segundos=float(
            os.getenv("PACKBALL_INTERVALO_NAVEGACAO_SEGUNDOS", "12")
        ),
        cooldown_minutos=int(
            os.getenv("PACKBALL_COOLDOWN_MINUTOS", "15")
        ),
        maximo_por_janela=int(
            os.getenv("PACKBALL_MAXIMO_NAVEGACOES_JANELA", "24")
        ),
        janela_segundos=int(
            os.getenv("PACKBALL_JANELA_NAVEGACOES_SEGUNDOS", "600")
        ),
        experimento_capacidade=(
            os.getenv("PACKBALL_EXPERIMENTO_CAPACIDADE", "0") == "1"
        ),
        intervalo_rollback_segundos=float(
            os.getenv("PACKBALL_INTERVALO_ROLLBACK_SEGUNDOS", "12")
        ),
        maximo_rollback_por_janela=int(
            os.getenv("PACKBALL_MAXIMO_ROLLBACK_JANELA", "24")
        ),
        distribuir_janela=(
            os.getenv("PACKBALL_DISTRIBUIR_NAVEGACOES", "0") == "1"
        ),
        margem_distribuicao_segundos=float(
            os.getenv("PACKBALL_MARGEM_DISTRIBUICAO_SEGUNDOS", "0.5")
        ),
    )


def _storage_state_completo(contexto, path=None):
    """Inclui IndexedDB, onde o PackBall pode guardar Scanner/colunas."""
    argumentos = {"indexed_db": True}
    if path is not None:
        argumentos["path"] = path
    try:
        return contexto.storage_state(**argumentos)
    except TypeError:
        # Compatibilidade com versões antigas do Playwright e dublês de teste.
        argumentos.pop("indexed_db", None)
        return contexto.storage_state(**argumentos)


def _expiracao_bearer(valor):
    try:
        token = str(valor or "").strip().strip('"')
        partes = token.split(".")
        if len(partes) != 3:
            return None
        payload = partes[1].replace("-", "+").replace("_", "/")
        payload += "=" * (-len(payload) % 4)
        dados = json.loads(base64.b64decode(payload).decode("utf-8"))
        return datetime.fromtimestamp(int(dados.get("exp")))
    except (TypeError, ValueError, OSError, UnicodeError, json.JSONDecodeError):
        return None


def diagnosticar_storage_state(dados, agora=None):
    """Valida a autenticacao sem devolver cookies, bearer ou payload JWT."""
    agora = agora or datetime.now()
    dados = dados if isinstance(dados, dict) else {}
    cookies = dados.get("cookies")
    origens = dados.get("origins")
    cookies = cookies if isinstance(cookies, list) else []
    origens = origens if isinstance(origens, list) else []
    bearer = None
    itens_locais = 0
    bancos_indexed_db = 0
    for origem in origens:
        if not isinstance(origem, dict):
            continue
        itens = origem.get("localStorage") or []
        itens_locais += len(itens) if isinstance(itens, list) else 0
        bancos = origem.get("indexedDB") or []
        bancos_indexed_db += len(bancos) if isinstance(bancos, list) else 0
        if "packball.com" not in str(origem.get("origin") or ""):
            continue
        for item in itens:
            if (
                isinstance(item, dict)
                and item.get("name") == "packballBearer"
                and bool(item.get("value"))
            ):
                bearer = item.get("value")
                break
    if not cookies and not bearer:
        return {"saudavel": False, "motivo": "sessao_sem_autenticacao"}
    expiracao = _expiracao_bearer(bearer) if bearer else None
    if bearer and expiracao is not None and agora >= expiracao:
        return {
            "saudavel": False,
            "motivo": "sessao_expirada",
            "metodo": "local_storage",
            "expira_em": expiracao.replace(microsecond=0).isoformat(),
            "cookies": len(cookies),
            "itens_local_storage": itens_locais,
            "bancos_indexed_db": bancos_indexed_db,
        }
    return {
        "saudavel": True,
        "metodo": "local_storage" if bearer else "cookie",
        "cookies": len(cookies),
        "itens_local_storage": itens_locais,
        "bancos_indexed_db": bancos_indexed_db,
        **(
            {"expira_em": expiracao.replace(microsecond=0).isoformat()}
            if expiracao is not None else {}
        ),
    }


def sincronizar_storage_state(contexto, arquivo_sessao, agora=None):
    """Persiste atomicamente somente um bearer valido e realmente mais novo."""
    agora = agora or datetime.now()
    arquivo_sessao = Path(arquivo_sessao)
    try:
        atual = json.loads(arquivo_sessao.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        atual = {}
    candidato = _storage_state_completo(contexto)
    diagnostico_atual = diagnosticar_storage_state(atual, agora=agora)
    diagnostico_novo = diagnosticar_storage_state(candidato, agora=agora)
    expira_novo = diagnostico_novo.get("expira_em")
    if not diagnostico_novo.get("saudavel") or not expira_novo:
        return {
            "atualizada": False,
            "motivo": "sessao_contexto_nao_comprovada",
            "estado_novo": diagnostico_novo.get("motivo"),
        }
    expira_atual = diagnostico_atual.get("expira_em")
    if (
        diagnostico_atual.get("saudavel")
        and expira_atual
        and datetime.fromisoformat(expira_novo)
        <= datetime.fromisoformat(expira_atual)
    ):
        return {
            "atualizada": False,
            "motivo": "sessao_ja_atual",
            "expira_em": expira_atual,
        }
    gravar_json_atomico(arquivo_sessao, candidato)
    return {
        "atualizada": True,
        "motivo": None,
        "expira_em": expira_novo,
    }


def autenticar_pagina(
    pagina, arquivo_sessao=ARQUIVO_SESSAO, controle_acesso=None
):
    email = os.getenv("PACKBALL_EMAIL")
    senha = os.getenv("PACKBALL_PASSWORD")
    if not email or not senha:
        raise ValueError(
            "E-mail ou senha do PackBall não encontrados no arquivo .env"
        )

    tentativa_enviada = False
    try:
        if controle_acesso is not None:
            controle_acesso.validar_pagina(pagina)
        if "/login" not in str(getattr(pagina, "url", "")):
            if controle_acesso is not None:
                controle_acesso.antes_navegacao()
            pagina.goto(
                URL_LOGIN,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            if controle_acesso is not None:
                controle_acesso.validar_pagina(pagina)
        pagina.locator('input[name="email"]').fill(email)
        pagina.locator('input[name="password"]').fill(senha)
        if controle_acesso is not None:
            controle_acesso.antes_navegacao()
        tentativa_enviada = True
        pagina.get_by_role("button", name="Login", exact=True).click()
        try:
            pagina.wait_for_url(
                lambda url: "/login" not in url, timeout=30000
            )
        except PlaywrightTimeoutError:
            if controle_acesso is not None:
                controle_acesso.validar_pagina(pagina)
            raise
        if controle_acesso is not None:
            controle_acesso.validar_pagina(pagina)
        _storage_state_completo(pagina.context, path=arquivo_sessao)
    except PackBallBloqueadoError:
        raise
    except Exception as erro:
        if tentativa_enviada and controle_acesso is not None:
            limite = controle_acesso.ativar_pausa(
                "falha_login_packball", minutos=360
            )
            raise PackBallBloqueadoError(
                "Login do PackBall falhou; novas tentativas suspensas até "
                f"{limite.isoformat()}."
            ) from erro
        raise


def fazer_login(headless=True, manter_aberto=False):
    email = os.getenv("PACKBALL_EMAIL")
    senha = os.getenv("PACKBALL_PASSWORD")

    if not email or not senha:
        raise ValueError(
            "E-mail ou senha do PackBall não encontrados no arquivo .env"
        )

    playwright = sync_playwright().start()
    navegador = playwright.chromium.launch(
        channel="chrome",
        headless=headless,
        slow_mo=300 if not headless else 0,
    )
    contexto = navegador.new_context()
    pagina = contexto.new_page()
    controle_acesso = _criar_controle_acesso()

    try:
        print("Entrando no PackBall...")
        autenticar_pagina(
            pagina, ARQUIVO_SESSAO, controle_acesso=controle_acesso
        )
        print("Login do PackBall realizado e sessão salva.")

        if manter_aberto:
            print("Abrindo a página de partidas...")
            controle_acesso.antes_navegacao()
            pagina.goto(
                URL_PARTIDAS,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            controle_acesso.validar_pagina(pagina)
            print("A janela do PackBall permanecerá aberta.")
            return playwright, navegador

        navegador.close()
        playwright.stop()
        return None

    except PlaywrightTimeoutError as erro:
        navegador.close()
        playwright.stop()
        raise RuntimeError(
            "O PackBall não confirmou o login em 30 segundos. "
            "Confira e-mail/senha ou se o site exibiu CAPTCHA."
        ) from erro
    except Exception:
        navegador.close()
        playwright.stop()
        raise


def fazer_login_manual(timeout_ms=300000, autorizar_nova_tentativa=False):
    controle_acesso = _criar_controle_acesso()
    playwright = sync_playwright().start()
    navegador = playwright.chromium.launch(
        channel="chrome", headless=False,
        args=["--start-maximized"],
    )
    contexto = navegador.new_context(no_viewport=True)
    pagina = contexto.new_page()
    sessao_confirmada = False
    try:
        controle_acesso.antes_navegacao(
            autorizar_login_manual=autorizar_nova_tentativa
        )
        pagina.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=30000)
        controle_acesso.validar_pagina(pagina)
        print(
            "Preencha o login manualmente na janela do navegador e clique "
            "em Entrar. Aguardando..."
        )
        pagina.wait_for_url(
            lambda url: "/login" not in url, timeout=timeout_ms
        )
        controle_acesso.validar_pagina(pagina)
        _storage_state_completo(contexto, path=ARQUIVO_SESSAO)
        sessao_confirmada = True
    except Exception as erro:
        if not isinstance(erro, PackBallBloqueadoError):
            controle_acesso.ativar_pausa(
                "falha_login_packball", minutos=360
            )
        raise
    finally:
        try:
            navegador.close()
        finally:
            playwright.stop()
    if not sessao_confirmada:
        return False
    controle_acesso.liberar_pausa_login_manual()
    print("Login manual confirmado e sessão salva.")
    return True


def abrir_sessao_salva_para_configuracao():
    """Abre a sessão autenticada e a mantém viva para ajustes manuais."""
    if not ARQUIVO_SESSAO.exists():
        raise FileNotFoundError(
            "Sessão do PackBall ausente; faça o login manual primeiro."
        )
    controle_acesso = _criar_controle_acesso()
    playwright = sync_playwright().start()
    navegador = playwright.chromium.launch(
        channel="chrome", headless=False,
        args=["--start-maximized"],
    )
    contexto = navegador.new_context(
        storage_state=ARQUIVO_SESSAO,
        no_viewport=True,
    )
    pagina = contexto.new_page()
    try:
        controle_acesso.antes_navegacao()
        pagina.goto(
            URL_PARTIDAS,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        controle_acesso.validar_pagina(pagina)
        print(
            "Sessão salva aberta. Configure o Scanner e, quando terminar, "
            "retorne ao Codex para concluir."
        )
        input("Aguardando confirmação para salvar e fechar...")
        _storage_state_completo(contexto, path=ARQUIVO_SESSAO)
        print("Configuração concluída e sessão atualizada.")
        return True
    finally:
        try:
            navegador.close()
        finally:
            playwright.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--fechar", action="store_true")
    parser.add_argument("--autorizar-nova-tentativa", action="store_true")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--abrir-sessao", action="store_true")
    argumentos = parser.parse_args()
    if argumentos.abrir_sessao:
        abrir_sessao_salva_para_configuracao()
        raise SystemExit(0)
    if argumentos.manual:
        fazer_login_manual(
            autorizar_nova_tentativa=argumentos.autorizar_nova_tentativa
        )
        raise SystemExit(0)
    if argumentos.autorizar_nova_tentativa:
        _criar_controle_acesso().liberar_pausa_login_manual()
    recursos = fazer_login(
        headless=argumentos.headless,
        manter_aberto=not argumentos.fechar,
    )
    if recursos is not None:
        input("Pressione Enter para fechar o navegador...")
        recursos[1].close()
        recursos[0].stop()
