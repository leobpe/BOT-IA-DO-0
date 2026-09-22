import base64
import json
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from packball_login import (
    _criar_controle_acesso,
    diagnosticar_storage_state,
    fazer_login_manual,
    sincronizar_storage_state,
)


def token_jwt(expiracao, marcador):
    def codificar(dados):
        bruto = json.dumps(dados).encode("utf-8")
        return base64.urlsafe_b64encode(bruto).decode().rstrip("=")

    return ".".join((
        codificar({"alg": "none"}),
        codificar({
            "exp": int(expiracao.timestamp()),
            "marcador": marcador,
        }),
        "assinatura",
    ))


def estado_com_token(token):
    return {
        "cookies": [],
        "origins": [{
            "origin": "https://packball.com",
            "localStorage": [{
                "name": "packballBearer",
                "value": token,
            }],
        }],
    }


class ContextoFalso:
    def __init__(self, estado):
        self.estado = estado

    def storage_state(self):
        return self.estado


class ConfiguracaoControleAcessoTest(unittest.TestCase):
    def test_login_herda_o_mesmo_ritmo_distribuido_do_monitor(self):
        ambiente = {
            "PACKBALL_INTERVALO_NAVEGACAO_SEGUNDOS": "12",
            "PACKBALL_COOLDOWN_MINUTOS": "20",
            "PACKBALL_MAXIMO_NAVEGACOES_JANELA": "32",
            "PACKBALL_JANELA_NAVEGACOES_SEGUNDOS": "600",
            "PACKBALL_EXPERIMENTO_CAPACIDADE": "1",
            "PACKBALL_INTERVALO_ROLLBACK_SEGUNDOS": "20",
            "PACKBALL_MAXIMO_ROLLBACK_JANELA": "20",
            "PACKBALL_DISTRIBUIR_NAVEGACOES": "1",
            "PACKBALL_MARGEM_DISTRIBUICAO_SEGUNDOS": "0.5",
        }
        with (
            patch.dict(os.environ, ambiente),
            patch("packball_login.ControleAcessoPackBall") as fabrica,
        ):
            _criar_controle_acesso()

        argumentos = fabrica.call_args.kwargs
        self.assertEqual(32, argumentos["maximo_por_janela"])
        self.assertEqual(600, argumentos["janela_segundos"])
        self.assertTrue(argumentos["distribuir_janela"])
        self.assertEqual(0.5, argumentos["margem_distribuicao_segundos"])


class PaginaManualFalsa:
    def __init__(self, eventos, falhar=False):
        self.eventos = eventos
        self.falhar = falhar

    def goto(self, *_args, **_kwargs):
        self.eventos.append("goto")

    def wait_for_url(self, *_args, **_kwargs):
        self.eventos.append("wait_for_url")
        if self.falhar:
            raise RuntimeError("login_nao_confirmado")


class ContextoManualFalso:
    def __init__(self, eventos, falhar=False):
        self.eventos = eventos
        self.pagina = PaginaManualFalsa(eventos, falhar=falhar)

    def new_page(self):
        return self.pagina

    def storage_state(self, **_kwargs):
        self.eventos.append("storage_state")


class NavegadorManualFalso:
    def __init__(self, eventos, falhar=False):
        self.eventos = eventos
        self.contexto = ContextoManualFalso(eventos, falhar=falhar)

    def new_context(self, **_kwargs):
        return self.contexto

    def close(self):
        self.eventos.append("navegador_close")


class PlaywrightManualFalso:
    def __init__(self, eventos, falhar=False):
        self.eventos = eventos
        self.navegador = NavegadorManualFalso(eventos, falhar=falhar)
        self.chromium = self

    def start(self):
        return self

    def launch(self, **_kwargs):
        return self.navegador

    def stop(self):
        self.eventos.append("playwright_stop")


class ControleManualFalso:
    def __init__(self, eventos):
        self.eventos = eventos

    def antes_navegacao(self, **kwargs):
        self.eventos.append(("antes_navegacao", kwargs))

    def validar_pagina(self, _pagina):
        self.eventos.append("validar_pagina")

    def liberar_pausa_login_manual(self):
        self.eventos.append("liberar_pausa")
        return True

    def ativar_pausa(self, motivo, minutos):
        self.eventos.append(("ativar_pausa", motivo, minutos))


class PackBallLoginTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_packball_session_sync.json"
        self.caminho.unlink(missing_ok=True)
        self.caminho.with_suffix(".json.tmp").unlink(missing_ok=True)
        self.agora = datetime(2026, 8, 1, 14, 0, 0)

    def tearDown(self):
        self.caminho.unlink(missing_ok=True)
        self.caminho.with_suffix(".json.tmp").unlink(missing_ok=True)

    def _gravar(self, estado):
        self.caminho.write_text(
            json.dumps(estado),
            encoding="utf-8",
        )

    def test_diagnostico_expirado_nao_expoe_bearer(self):
        token = token_jwt(self.agora - timedelta(seconds=1), "segredo")

        resultado = diagnosticar_storage_state(
            estado_com_token(token),
            agora=self.agora,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["motivo"], "sessao_expirada")
        self.assertNotIn(token, str(resultado))
        self.assertNotIn("segredo", str(resultado))

    def test_diagnostico_conta_indexed_db_sem_expor_conteudo(self):
        token = token_jwt(self.agora + timedelta(hours=1), "segredo")
        estado = estado_com_token(token)
        estado["origins"][0]["indexedDB"] = [
            {"name": "configuracao", "stores": []},
            {"name": "cache", "stores": []},
        ]

        resultado = diagnosticar_storage_state(estado, agora=self.agora)

        self.assertEqual(resultado["bancos_indexed_db"], 2)
        self.assertNotIn("configuracao", str(resultado))
        self.assertNotIn("cache", str(resultado))

    def test_contexto_com_bearer_mais_novo_substitui_atomicamente(self):
        token_antigo = token_jwt(
            self.agora + timedelta(hours=1), "antigo"
        )
        token_novo = token_jwt(
            self.agora + timedelta(hours=2), "novo"
        )
        self._gravar(estado_com_token(token_antigo))

        resultado = sincronizar_storage_state(
            ContextoFalso(estado_com_token(token_novo)),
            self.caminho,
            agora=self.agora,
        )

        self.assertTrue(resultado["atualizada"])
        persistido = json.loads(self.caminho.read_text(encoding="utf-8"))
        self.assertEqual(
            persistido["origins"][0]["localStorage"][0]["value"],
            token_novo,
        )
        self.assertFalse(self.caminho.with_suffix(".json.tmp").exists())
        self.assertNotIn(token_novo, str(resultado))

    def test_contexto_antigo_nao_regride_sessao_persistida(self):
        token_atual = token_jwt(
            self.agora + timedelta(hours=2), "atual"
        )
        token_antigo = token_jwt(
            self.agora + timedelta(hours=1), "antigo"
        )
        self._gravar(estado_com_token(token_atual))

        resultado = sincronizar_storage_state(
            ContextoFalso(estado_com_token(token_antigo)),
            self.caminho,
            agora=self.agora,
        )

        self.assertFalse(resultado["atualizada"])
        self.assertEqual(resultado["motivo"], "sessao_ja_atual")
        self.assertIn(
            token_atual,
            self.caminho.read_text(encoding="utf-8"),
        )

    def test_contexto_expirado_nao_sobrescreve_arquivo(self):
        token_atual = token_jwt(
            self.agora + timedelta(hours=1), "atual"
        )
        token_expirado = token_jwt(
            self.agora - timedelta(seconds=1), "expirado"
        )
        self._gravar(estado_com_token(token_atual))

        resultado = sincronizar_storage_state(
            ContextoFalso(estado_com_token(token_expirado)),
            self.caminho,
            agora=self.agora,
        )

        self.assertFalse(resultado["atualizada"])
        self.assertEqual(
            resultado["motivo"], "sessao_contexto_nao_comprovada"
        )
        self.assertIn(
            token_atual,
            self.caminho.read_text(encoding="utf-8"),
        )

    def test_login_manual_libera_pausa_somente_apos_salvar_sessao(self):
        eventos = []
        controle = ControleManualFalso(eventos)
        playwright = PlaywrightManualFalso(eventos)
        with (
            patch(
                "packball_login.ControleAcessoPackBall",
                return_value=controle,
            ),
            patch(
                "packball_login.sync_playwright",
                return_value=playwright,
            ),
        ):
            resultado = fazer_login_manual(
                timeout_ms=100,
                autorizar_nova_tentativa=True,
            )

        self.assertTrue(resultado)
        self.assertIn(
            (
                "antes_navegacao",
                {"autorizar_login_manual": True},
            ),
            eventos,
        )
        self.assertLess(
            eventos.index("storage_state"),
            eventos.index("liberar_pausa"),
        )
        self.assertLess(
            eventos.index("navegador_close"),
            eventos.index("liberar_pausa"),
        )
        self.assertLess(
            eventos.index("playwright_stop"),
            eventos.index("liberar_pausa"),
        )

    def test_login_manual_falho_preserva_pausa_global(self):
        eventos = []
        controle = ControleManualFalso(eventos)
        playwright = PlaywrightManualFalso(eventos, falhar=True)
        with (
            patch(
                "packball_login.ControleAcessoPackBall",
                return_value=controle,
            ),
            patch(
                "packball_login.sync_playwright",
                return_value=playwright,
            ),
        ):
            with self.assertRaises(RuntimeError):
                fazer_login_manual(
                    timeout_ms=100,
                    autorizar_nova_tentativa=True,
                )

        self.assertNotIn("liberar_pausa", eventos)
        self.assertIn(
            ("ativar_pausa", "falha_login_packball", 360),
            eventos,
        )


if __name__ == "__main__":
    unittest.main()
