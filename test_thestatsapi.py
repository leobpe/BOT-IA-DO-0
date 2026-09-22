import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from uuid import uuid4

from thestatsapi import (
    BASE_URL,
    CACHE_JOGOS_AO_VIVO_SEGUNDOS,
    TheStatsAPI,
)


class RelogioFalso:
    def __init__(self, valor=1_786_579_200.0):
        self.valor = float(valor)

    def __call__(self):
        return self.valor

    def avancar(self, segundos):
        self.valor += float(segundos)


class RespostaFalsa:
    def __init__(self, corpo, *, status=200, headers=None):
        self.corpo = json.dumps(corpo).encode("utf-8")
        self.status = status
        self.headers = headers or {}

    def read(self, _limite=-1):
        return self.corpo

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class AbridorFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, requisicao, timeout):
        self.chamadas.append((requisicao, timeout))
        resposta = self.respostas.pop(0)
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta


class TheStatsAPITest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / f".teste_thestatsapi_{uuid4().hex}"
        self.pasta.mkdir(exist_ok=True)
        self.relogio = RelogioFalso()

    def tearDown(self):
        for arquivo in self.pasta.glob("*"):
            arquivo.unlink()
        self.pasta.rmdir()

    def criar(self, respostas=(), **env):
        padrao = {
            "THESTATSAPI_KEY": "chave-teste",
            "NOVA_FOOTBALL_API_KEY": "",
            "THESTATSAPI_LIMITE_DIARIO": "100",
            "THESTATSAPI_RESERVA_DIARIA": "10",
            "THESTATSAPI_LIMITE_MINUTO": "30",
        }
        padrao.update(env)
        abridor = AbridorFalso(respostas)
        contexto = patch.dict(os.environ, padrao, clear=False)
        contexto.start()
        self.addCleanup(contexto.stop)
        return TheStatsAPI(
            self.pasta, abridor=abridor, relogio=self.relogio
        ), abridor

    def test_prefere_variavel_oficial_e_nao_expoe_chave(self):
        api, _ = self.criar(
            THESTATSAPI_KEY="oficial-secreta",
            NOVA_FOOTBALL_API_KEY="legada-secreta",
        )

        diagnostico = api.diagnostico()

        self.assertEqual(api.chave, "oficial-secreta")
        self.assertEqual(diagnostico["variavel_chave"], "THESTATSAPI_KEY")
        self.assertNotIn("oficial-secreta", repr(diagnostico))
        self.assertNotIn("legada-secreta", repr(diagnostico))

    def test_usa_variavel_legada_como_fallback(self):
        api, _ = self.criar(
            THESTATSAPI_KEY="",
            NOVA_FOOTBALL_API_KEY="fallback-seguro",
        )

        self.assertTrue(api.disponivel)
        self.assertEqual(api.variavel_chave, "NOVA_FOOTBALL_API_KEY")

    def test_jogos_ao_vivo_monta_endpoint_auth_e_resposta_padronizada(self):
        api, abridor = self.criar([
            RespostaFalsa(
                {"data": [{"match_id": "mt_1"}], "meta": {"page": 1}},
                headers={"X-RateLimit-Limit": "200", "X-RateLimit-Remaining": "199"},
            )
        ])

        resultado = api.jogos_ao_vivo(pagina=1, por_pagina=50)

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["dados"], [{"match_id": "mt_1"}])
        self.assertEqual(resultado["meta"], {"page": 1})
        self.assertEqual(resultado["origem"], "rede")
        requisicao = abridor.chamadas[0][0]
        self.assertEqual(
            requisicao.full_url,
            f"{BASE_URL}/football/matches?status=live&page=1&per_page=50",
        )
        self.assertEqual(
            requisicao.get_header("Authorization"), "Bearer chave-teste"
        )
        self.assertEqual(requisicao.get_header("Accept"), "application/json")

    def test_cache_evita_segunda_chamada_e_expira_no_ttl(self):
        api, abridor = self.criar([
            RespostaFalsa({"data": [{"match_id": "mt_1"}]}),
            RespostaFalsa({"data": [{"match_id": "mt_2"}]}),
        ])

        primeira = api.jogos_ao_vivo()
        self.relogio.avancar(10)
        segunda = api.jogos_ao_vivo()
        self.relogio.avancar(CACHE_JOGOS_AO_VIVO_SEGUNDOS)
        terceira = api.jogos_ao_vivo()

        self.assertFalse(primeira["cache"])
        self.assertTrue(segunda["cache"])
        self.assertEqual(segunda["idade_segundos"], 10.0)
        self.assertEqual(terceira["dados"][0]["match_id"], "mt_2")
        self.assertEqual(len(abridor.chamadas), 2)
        self.assertEqual(api.consumo_atual()["usado_local_dia"], 2)

    def test_404_de_stats_tem_cache_negativo_sem_bloquear_odds(self):
        erro_404 = HTTPError(
            f"{BASE_URL}/football/matches/mt_1/live-stats",
            404,
            "not found",
            {},
            None,
        )
        self.addCleanup(erro_404.close)
        api, abridor = self.criar([
            erro_404,
            RespostaFalsa({"data": {"bookmakers": []}}),
            RespostaFalsa({"data": {"stats": {}}}),
        ])

        primeira = api.estatisticas_ao_vivo("mt_1")
        self.relogio.avancar(10)
        segunda = api.estatisticas_ao_vivo("mt_1")
        odds = api.odds_ao_vivo("mt_1")
        self.relogio.avancar(300)
        recuperada = api.estatisticas_ao_vivo("mt_1")

        self.assertEqual(primeira["erro"]["codigo"], "http_404")
        self.assertFalse(primeira["cache"])
        self.assertEqual(segunda["erro"]["codigo"], "http_404")
        self.assertTrue(segunda["cache"])
        self.assertEqual(segunda["origem"], "cache_negativo")
        self.assertGreater(
            segunda["erro"]["tentar_novamente_em_segundos"], 0
        )
        self.assertTrue(odds["ok"])
        self.assertTrue(recuperada["ok"])
        self.assertEqual(len(abridor.chamadas), 3)
        self.assertEqual(api.consumo_atual()["usado_local_dia"], 3)

    def test_metodos_de_detalhe_validam_id_e_usam_rotas_oficiais(self):
        api, abridor = self.criar([
            RespostaFalsa({"data": {"overview": {"shots": {}}}}),
            RespostaFalsa({
                "data": {
                    "meta": {"match_id": "mt_745359007"},
                    "stats": {"shots": {"home": 8, "away": 5}},
                }
            }),
            RespostaFalsa({"data": {"bookmakers": []}}),
        ])

        estatisticas = api.estatisticas_partida("mt_745359007")
        estatisticas_live = api.estatisticas_ao_vivo("mt_745359007")
        odds = api.odds_ao_vivo("mt_745359007")
        invalido = api.odds_ao_vivo("../segredo")

        self.assertTrue(estatisticas["ok"])
        self.assertTrue(estatisticas_live["ok"])
        self.assertEqual(
            estatisticas_live["dados"]["stats"]["shots"]["home"], 8
        )
        self.assertEqual(
            estatisticas_live["meta"]["match_id"], "mt_745359007"
        )
        self.assertTrue(odds["ok"])
        self.assertEqual(invalido["erro"]["codigo"], "id_partida_invalido")
        self.assertEqual(len(abridor.chamadas), 3)
        self.assertEqual(
            abridor.chamadas[0][0].full_url,
            f"{BASE_URL}/football/matches/mt_745359007/stats",
        )
        self.assertEqual(
            abridor.chamadas[1][0].full_url,
            f"{BASE_URL}/football/matches/mt_745359007/live-stats",
        )
        self.assertEqual(
            abridor.chamadas[2][0].full_url,
            f"{BASE_URL}/football/matches/mt_745359007/odds/live",
        )

    def test_tentativa_de_rede_e_contada_antes_de_falhar(self):
        api, _ = self.criar([URLError("Bearer chave-teste")])

        resultado = api.jogos_ao_vivo()

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["erro"]["codigo"], "erro_rede")
        self.assertNotIn("chave-teste", repr(resultado))
        self.assertEqual(api.consumo_atual()["usado_local_dia"], 1)
        self.assertTrue((self.pasta / "thestatsapi_uso.json").exists())
        self.assertTrue((self.pasta / "thestatsapi_uso.json.bak").exists())

    def test_rate_limit_local_bloqueia_sem_nova_chamada(self):
        respostas = [RespostaFalsa({"data": []}) for _ in range(2)]
        api, abridor = self.criar(
            respostas, THESTATSAPI_LIMITE_MINUTO="1"
        )

        primeira = api.jogos_ao_vivo(pagina=1)
        segunda = api.jogos_ao_vivo(pagina=2)

        self.assertTrue(primeira["ok"])
        self.assertEqual(
            segunda["erro"]["codigo"], "limite_minuto_local"
        )
        self.assertGreater(
            segunda["erro"]["tentar_novamente_em_segundos"], 0
        )
        self.assertEqual(len(abridor.chamadas), 1)

    def test_cota_diaria_segura_bloqueia_sem_rede(self):
        api, abridor = self.criar(
            [RespostaFalsa({"data": []})],
            THESTATSAPI_LIMITE_DIARIO="2",
            THESTATSAPI_RESERVA_DIARIA="1",
        )

        self.assertTrue(api.jogos_ao_vivo(pagina=1)["ok"])
        bloqueada = api.jogos_ao_vivo(pagina=2)

        self.assertEqual(bloqueada["erro"]["codigo"], "cota_local_esgotada")
        self.assertEqual(len(abridor.chamadas), 1)

    def test_429_abre_circuito_e_respeita_retry_after(self):
        erro = HTTPError(
            f"{BASE_URL}/football/matches",
            429,
            "segredo chave-teste",
            {"Retry-After": "45"},
            None,
        )
        self.addCleanup(erro.close)
        api, abridor = self.criar([erro])

        resultado = api.jogos_ao_vivo(pagina=1)
        bloqueada = api.jogos_ao_vivo(pagina=2)

        self.assertEqual(resultado["erro"]["codigo"], "http_429")
        self.assertEqual(
            resultado["erro"]["tentar_novamente_em_segundos"], 60
        )
        self.assertEqual(bloqueada["erro"]["codigo"], "circuito_aberto")
        self.assertEqual(len(abridor.chamadas), 1)
        self.assertNotIn("chave-teste", repr(resultado))

    def test_tres_falhas_de_rede_abrem_circuit_breaker(self):
        api, abridor = self.criar([
            URLError("falha 1"),
            URLError("falha 2"),
            URLError("falha 3"),
        ])

        for pagina in range(1, 4):
            self.assertFalse(api.jogos_ao_vivo(pagina=pagina)["ok"])
        bloqueada = api.jogos_ao_vivo(pagina=4)

        self.assertEqual(bloqueada["erro"]["codigo"], "circuito_aberto")
        self.assertEqual(len(abridor.chamadas), 3)
        self.assertTrue(api.diagnostico()["circuito_aberto"])

    def test_payload_e_diagnostico_sao_sanitizados(self):
        api, _ = self.criar([
            RespostaFalsa({
                "data": {
                    "authorization": "Bearer chave-teste",
                    "X-Api-Key": "outra-chave",
                    "descricao": "eco chave-teste",
                }
            })
        ])

        resultado = api.jogos_ao_vivo()

        self.assertNotIn("chave-teste", repr(resultado))
        self.assertEqual(
            resultado["dados"]["authorization"], "[REMOVIDO]"
        )
        self.assertEqual(resultado["dados"]["X-Api-Key"], "[REMOVIDO]")
        self.assertNotIn("chave-teste", repr(api.diagnostico()))

    def test_retry_after_do_provedor_persiste_entre_instancias(self):
        erro = HTTPError(
            f"{BASE_URL}/football/matches",
            429,
            "too many requests",
            {"Retry-After": "90"},
            None,
        )
        self.addCleanup(erro.close)
        primeira, _ = self.criar([erro])
        primeira.jogos_ao_vivo()

        segunda, abridor = self.criar([RespostaFalsa({"data": []})])
        bloqueada = segunda.jogos_ao_vivo()

        self.assertEqual(bloqueada["erro"]["codigo"], "limite_provedor")
        self.assertEqual(
            bloqueada["erro"]["tentar_novamente_em_segundos"], 90
        )
        self.assertEqual(len(abridor.chamadas), 0)

    def test_contador_corrompido_falha_fechado(self):
        (self.pasta / "thestatsapi_uso.json").write_text(
            "nao-json", encoding="utf-8"
        )
        api, abridor = self.criar([RespostaFalsa({"data": []})])

        resultado = api.jogos_ao_vivo()

        self.assertEqual(resultado["erro"]["codigo"], "contador_inseguro")
        self.assertEqual(len(abridor.chamadas), 0)
        self.assertFalse(api.diagnostico()["consumo"]["contador_saudavel"])


if __name__ == "__main__":
    unittest.main()
