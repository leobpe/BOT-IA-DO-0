import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from betsapi import BetsAPI, _odd_decimal


class Resposta:
    def __init__(self, dados):
        self._dados = json.dumps(dados).encode("utf-8")

    def read(self, limite=-1):
        return self._dados


class TestBetsAPI(unittest.TestCase):
    def setUp(self):
        self.estado = Path(f".teste_betsapi_{id(self)}.json")
        self.estado.unlink(missing_ok=True)
        self.addCleanup(self.estado.unlink, missing_ok=True)
        self.env = patch.dict(os.environ, {
            "BETSAPI_TOKEN": "segredo",
            "BETSAPI_ATIVA": "1",
            "BETSAPI_APLICACAO_SINAIS_ATIVA": "1",
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.agora = 1_788_033_306.0

    def _lista(self):
        return {"success": 1, "results": [{
            "id": "200",
            "home": {"name": "Palmeiras"},
            "away": {"name": "Santos"},
            "ss": "1-1",
            "updated_at": str(int(self.agora - 5)),
        }]}

    def _evento(self):
        itens = [
            {"type": "EV", "FI": "200", "NA": "Palmeiras v Santos"},
            {"type": "MG", "NA": "Match Goals", "SU": "0"},
            {"type": "MA", "NA": "Over"},
            {"type": "PA", "HA": "2.5", "OD": "4/5", "SU": "0"},
            {"type": "MA", "NA": "Under"},
            {"type": "PA", "HA": "2.5", "OD": "1/1", "SU": "0"},
            {"type": "MG", "NA": "1st Half Goals", "SU": "0"},
            {"type": "MA", "NA": "Over"},
            {"type": "PA", "HA": "1.5", "OD": "6/4", "SU": "0"},
            {"type": "MA", "NA": "Under"},
            {"type": "PA", "HA": "1.5", "OD": "1/2", "SU": "0"},
            {"type": "MG", "NA": "Asian Corners", "SU": "0"},
            {"type": "MA", "NA": "Over"},
            {"type": "PA", "HA": "9.5", "OD": "10/11", "SU": "0"},
            {"type": "MA", "NA": "Under"},
            {"type": "PA", "HA": "9.5", "OD": "10/11", "SU": "0"},
            {"type": "MG", "NA": "3rd Goal", "SU": "0"},
            {"type": "PA", "NA": "Palmeiras", "OD": "5/4", "SU": "0"},
            {"type": "PA", "NA": "No 3rd Goal", "OD": "2/1", "SU": "0"},
            {"type": "PA", "NA": "Santos", "OD": "7/4", "SU": "0"},
        ]
        return {"success": 1, "results": [itens]}

    def test_converte_fracionaria_sem_inverter(self):
        self.assertEqual(_odd_decimal("4/5"), 1.8)
        self.assertEqual(_odd_decimal("1/14"), 1.0714)
        self.assertIsNone(_odd_decimal("0/1"))

    def test_pareia_e_converte_mercados_suportados(self):
        respostas = iter([Resposta(self._lista()), Resposta(self._evento())])
        api = BetsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: self.agora, arquivo_estado=self.estado,
        )
        saida, diag = api.buscar_mercados({
            "mandante": "Palmeiras FC", "visitante": "Santos FC",
            "placar": "1-1",
        }, {"gol_ft", "gol_ht", "proximo_gol", "escanteios_ft_asiatico"})

        self.assertTrue(diag["pareado"])
        self.assertEqual(set(diag["anexados"]), {
            "gol_ft", "gol_ht", "proximo_gol", "escanteios_ft_asiatico",
        })
        gols = next(m for m in saida["ao_vivo"] if m.get("ofertas"))
        self.assertEqual(gols["ofertas"][0]["over"], 1.8)
        self.assertEqual(gols["ofertas"][0]["bookmaker"], "bet365")
        self.assertEqual(
            gols["ofertas"][0]["origem_mercado"]["lados"],
            ["over", "under"],
        )
        self.assertEqual(
            gols["ofertas"][0]["origem_mercado"]["identificador"],
            "ordem:1:match goals",
        )
        proximo = next(m for m in saida["ao_vivo"] if m.get("escopo") == "proximo")
        self.assertEqual(proximo["selecoes"]["casa"], 2.25)
        self.assertEqual(proximo["selecoes"]["visitante"], 2.75)
        self.assertEqual(
            proximo["origem_mercado"]["lados"],
            ["casa", "visitante", "sem_gol"],
        )

    def test_frescor_da_odd_usa_consulta_evento_nao_evento_do_jogo(self):
        lista = self._lista()
        lista["results"][0]["updated_at"] = str(int(self.agora - 100))
        respostas = iter([Resposta(lista), Resposta(self._evento())])
        api = BetsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: self.agora, arquivo_estado=self.estado,
        )

        saida, diagnostico = api.buscar_mercados({
            "mandante": "Palmeiras", "visitante": "Santos",
            "placar": "1-1",
        }, {"escanteios_ft_asiatico"})

        self.assertTrue(diagnostico["pareado"])
        oferta = saida["ao_vivo"][0]["ofertas"][0]
        self.assertEqual(oferta["idade_segundos"], 0.0)
        self.assertEqual(
            oferta["coletado_em"],
            "2026-08-29T19:55:06+00:00",
        )
        self.assertFalse(oferta["cache"])

    def test_cache_curto_evento_preserva_idade_real_da_odd(self):
        agora = [self.agora]
        chamadas = []
        respostas = iter([Resposta(self._lista()), Resposta(self._evento())])

        def abrir(*args, **kwargs):
            chamadas.append(args[0])
            return next(respostas)

        api = BetsAPI(
            ".", abridor=abrir, relogio=lambda: agora[0],
            arquivo_estado=self.estado,
        )
        jogo = {
            "mandante": "Palmeiras", "visitante": "Santos",
            "placar": "1-1",
        }
        api.buscar_mercados(jogo, {"escanteios_ft_asiatico"})
        agora[0] += 7
        saida, _ = api.buscar_mercados(
            jogo, {"escanteios_ft_asiatico"}
        )

        oferta = saida["ao_vivo"][0]["ofertas"][0]
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(oferta["idade_segundos"], 7.0)
        self.assertTrue(oferta["cache"])

    def test_cobertura_em_lote_usa_uma_unica_leitura_global(self):
        chamadas = []

        def abrir(*args, **kwargs):
            chamadas.append(args[0])
            return Resposta(self._lista())

        api = BetsAPI(
            ".", abridor=abrir, relogio=lambda: self.agora,
            arquivo_estado=self.estado,
        )
        diagnostico = api.cobertura_jogos_ao_vivo([
            {
                "url": "palmeiras-santos",
                "mandante": "Palmeiras FC",
                "visitante": "Santos FC",
                "placar": "1-1",
            },
            {
                "url": "outro-jogo",
                "mandante": "Time sem cobertura",
                "visitante": "Outro time",
                "placar": "0-0",
            },
        ])

        self.assertEqual(diagnostico["pareados"], 1)
        self.assertIn(
            "palmeiras-santos", diagnostico["cobertura_por_url"]
        )
        self.assertEqual(len(chamadas), 1)

    def test_descarta_participante_suspenso_e_mercado_incompleto(self):
        evento = self._evento()
        evento["results"][0][3]["SU"] = "1"
        respostas = iter([Resposta(self._lista()), Resposta(evento)])
        api = BetsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: self.agora, arquivo_estado=self.estado,
        )
        saida, diag = api.buscar_mercados({
            "mandante": "Palmeiras", "visitante": "Santos", "placar": "1-1",
        }, {"gol_ft"})
        self.assertEqual(saida["ao_vivo"], [])
        self.assertEqual(diag["motivo"], "mercado_sem_oferta_ativa")

    def test_nao_combina_over_e_under_de_grupos_distintos(self):
        evento = {"success": 1, "results": [[
            {"type": "EV", "FI": "200", "NA": "Palmeiras v Santos"},
            {"type": "MG", "ID": "grupo-over", "NA": "Match Goals"},
            {"type": "MA", "NA": "Over"},
            {"type": "PA", "HA": "2.5", "OD": "4/5"},
            {"type": "MG", "ID": "grupo-under", "NA": "Match Goals"},
            {"type": "MA", "NA": "Under"},
            {"type": "PA", "HA": "2.5", "OD": "1/1"},
        ]]}
        respostas = iter([Resposta(self._lista()), Resposta(evento)])
        api = BetsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: self.agora, arquivo_estado=self.estado,
        )

        saida, diag = api.buscar_mercados({
            "mandante": "Palmeiras", "visitante": "Santos",
            "placar": "1-1",
        }, {"gol_ft"})

        self.assertEqual(saida["ao_vivo"], [])
        self.assertEqual(diag["motivo"], "mercado_sem_oferta_ativa")

    def test_placar_divergente_bloqueia_pareamento(self):
        respostas = iter([Resposta(self._lista())])
        api = BetsAPI(
            ".", abridor=lambda *a, **k: next(respostas),
            relogio=lambda: self.agora, arquivo_estado=self.estado,
        )
        saida, diag = api.buscar_mercados({
            "mandante": "Palmeiras", "visitante": "Santos", "placar": "0-0",
        }, {"gol_ft"})
        self.assertEqual(saida["ao_vivo"], [])
        self.assertEqual(diag["motivo"], "evento_nao_encontrado")

    def test_rollback_desliga_sem_chamada(self):
        with patch.dict(os.environ, {"BETSAPI_ATIVA": "0"}):
            api = BetsAPI(".", arquivo_estado=self.estado)
        saida, diag = api.buscar_mercados({}, {"gol_ft"})
        self.assertFalse(diag["ativa"])
        self.assertEqual(saida["ao_vivo"], [])

    def test_circuito_http_persiste_e_reinicio_respeita_backoff(self):
        chamadas = []

        def falhar(*args, **kwargs):
            chamadas.append(args[0])
            raise HTTPError("https://exemplo", 429, "limite", {}, None)

        api = BetsAPI(
            ".", abridor=falhar, relogio=lambda: self.agora,
            arquivo_estado=self.estado,
        )
        self.assertIsNone(api._requisitar("v1/teste", {}))
        diagnostico = api.diagnostico()
        self.assertTrue(diagnostico["circuito_aberto"])
        self.assertEqual(diagnostico["circuito"]["motivo"], "http_429")
        self.assertTrue(diagnostico["circuito"]["persistente"])

        api_reiniciada = BetsAPI(
            ".", abridor=falhar, relogio=lambda: self.agora + 1,
            arquivo_estado=self.estado,
        )
        self.assertIsNone(api_reiniciada._requisitar("v1/teste", {}))
        self.assertEqual(len(chamadas), 1)
        self.assertGreater(
            api_reiniciada.diagnostico()["circuito"]["restante_segundos"],
            0,
        )

    def test_circuito_recupera_apos_backoff_e_persiste_fechamento(self):
        agora = [self.agora]
        respostas = [
            HTTPError("https://exemplo", 429, "limite", {}, None),
            Resposta({"success": 1, "results": []}),
        ]

        def abrir(*args, **kwargs):
            resposta = respostas.pop(0)
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

        api = BetsAPI(
            ".", abridor=abrir, relogio=lambda: agora[0],
            arquivo_estado=self.estado,
        )
        self.assertIsNone(api._requisitar("v1/teste", {}))
        agora[0] += 901

        api_reiniciada = BetsAPI(
            ".", abridor=abrir, relogio=lambda: agora[0],
            arquivo_estado=self.estado,
        )
        self.assertEqual(
            api_reiniciada._requisitar("v1/teste", {}),
            {"success": 1, "results": []},
        )
        diagnostico = api_reiniciada.diagnostico()
        self.assertFalse(diagnostico["circuito_aberto"])
        self.assertEqual(diagnostico["circuito"]["falhas_consecutivas"], 0)
        self.assertIsNone(diagnostico["circuito"]["motivo"])

        api_final = BetsAPI(
            ".", relogio=lambda: agora[0], arquivo_estado=self.estado,
        )
        self.assertFalse(api_final.diagnostico()["circuito_aberto"])
        self.assertEqual(
            api_final.diagnostico()["circuito"]["falhas_consecutivas"], 0
        )

    def test_falhas_transitorias_somam_entre_reinicios(self):
        chamadas = []

        def falhar(*args, **kwargs):
            chamadas.append(args[0])
            raise URLError("indisponivel")

        for _ in range(3):
            api = BetsAPI(
                ".", abridor=falhar, relogio=lambda: self.agora,
                arquivo_estado=self.estado,
            )
            self.assertIsNone(api._requisitar("v1/teste", {}))

        diagnostico = api.diagnostico()
        self.assertEqual(len(chamadas), 3)
        self.assertTrue(diagnostico["circuito_aberto"])
        self.assertEqual(
            diagnostico["circuito"]["falhas_consecutivas"], 3
        )
        self.assertEqual(
            diagnostico["circuito"]["motivo"], "falha_transitoria"
        )

    def test_falha_ao_persistir_circuito_bloqueia_novas_chamadas(self):
        chamadas = []

        def falhar(*args, **kwargs):
            chamadas.append(args[0])
            raise URLError("indisponivel")

        api = BetsAPI(
            ".", abridor=falhar, relogio=lambda: self.agora,
            arquivo_estado=self.estado,
        )
        with patch(
            "betsapi.gravar_json_atomico",
            side_effect=[None, OSError("disco indisponivel")],
        ):
            self.assertIsNone(api._requisitar("v1/teste", {}))

        self.assertFalse(
            api.diagnostico()["circuito"]["persistencia_saudavel"]
        )
        self.assertIsNone(api._requisitar("v1/teste", {}))
        self.assertEqual(len(chamadas), 1)


if __name__ == "__main__":
    unittest.main()
