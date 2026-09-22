import unittest
from pathlib import Path

from avaliacao_acompanhamento_odd import (
    _primeiros_independentes,
    avaliar_estrategia_acompanhamento_odd,
)
from banco import BancoMonitor


def identidade_evento_teste(placar="0-0", indice=None):
    return {
        "schema": "identidade-evento-odd-v1",
        "confirmada": True,
        "fonte": "betsapi",
        "evento_externo_id": "evento-123",
        "orientacao": "direta",
        "similaridade": 0.95,
        "mandante_normalizado": (
            f"Casa {indice}" if indice is not None else "Casa"
        ),
        "visitante_normalizado": (
            f"Fora {indice}" if indice is not None else "Fora"
        ),
        "placar_normalizado": placar,
        "metodo": "teste",
    }


def origem_mercado_teste(linha=0.5):
    return {
        "schema": "origem-mercado-odd-v1",
        "fonte": "betsapi",
        "identificador": "mercado-123",
        "nome": "Match Goals",
        "linha": linha,
        "lados": ["over", "under"],
        "bookmaker": "bet365",
    }


class AvaliacaoAcompanhamentoOddTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_avaliacao_aguardar_odd.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def criar_aviso(self, indice, instante="2026-09-01T12:00:00"):
        url = f"https://packball.com/match/{indice}/live"
        snapshot = self.banco.salvar_registro({
            "coletado_em": instante,
            "url": url,
            "mandante": f"Casa {indice}",
            "visitante": f"Fora {indice}",
            "placar": "0-0",
            "status": "46 '",
            "qualidade": {
                "pontuacao": 90,
                "fontes": ["packball", "api_football"],
                "apto_para_liquidacao": True,
            },
        })
        sinal = self.banco.salvar_candidatos(snapshot, [{
            "mercado": "gol_ft",
            "linha": 0.5,
            "odd": 1.20,
            "pontuacao_tecnica": 90,
            "regra_versao": "teste-aguardar-odd-v1",
            "status": "rejeitado",
            "features": {
                "fonte_odds": "packball",
                "acompanhamento_odd": {
                    "elegivel_aviso": True,
                    "odd_alvo": 1.40,
                    "odd_maxima_operacional": 2.50,
                },
            },
        }])[0]
        self.banco.registrar_entrega_alerta(
            sinal,
            "-100123:aguardar_odd",
            "entregue",
            instante=instante,
            provedor="telegram",
            provedor_destino_id="-100123",
            provedor_mensagem_id=str(indice),
        )
        return sinal, url

    def salvar_resultado(self, url, placar, instante):
        return self.banco.salvar_registro({
            "coletado_em": instante,
            "url": url,
            "mandante": "Casa",
            "visitante": "Fora",
            "placar": placar,
            "status": "Finalizado",
            "qualidade": {
                "pontuacao": 100,
                "fontes": ["api_football"],
                "apto_para_liquidacao": True,
                "versao": "resultado-api-v1",
            },
        })

    def test_separa_green_antes_alvo_de_red_executavel(self):
        _, url_green = self.criar_aviso(1)
        self.salvar_resultado(url_green, "1-0", "2026-09-01T12:02:00")

        sinal_red, url_red = self.criar_aviso(2)
        self.banco.registrar_observacao_acompanhamento_odd(
            sinal_red,
            {
                "odd": 1.40,
                "odd_oposta": 2.50,
                "linha": 0.5,
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T12:01:00",
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(indice=2),
            },
            {"placar": "0-0", "minuto": 52, "status": "52 '"},
            consultado_em="2026-09-01T12:01:00",
        )
        self.salvar_resultado(url_red, "0-0", "2026-09-01T12:05:00")

        resultado = avaliar_estrategia_acompanhamento_odd(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
        )
        self.assertEqual("concluida", resultado["estado_execucao"])
        self.assertEqual(
            "custodia-execucao-avaliacao-v3",
            resultado["custodia_execucao_versao"],
        )
        historico = resultado["historico_exploratorio"]
        prospectivo = resultado["coorte_prospectiva_rapida"]
        self.assertEqual(resultado["avisos_total"], 2)
        self.assertEqual(historico["conclusivos"], 2)
        self.assertEqual(historico["greens_hipoteticos"], 1)
        self.assertEqual(historico["atingiram_faixa"], 1)
        self.assertEqual(historico["greens_apos_faixa"], 0)
        self.assertEqual(historico["greens_antes_do_alvo"], 1)
        self.assertEqual(historico["roi_odd_inicial_hipotetico"], -0.4)
        self.assertEqual(historico["roi_aguardando_alvo_hipotetico"], -1.0)
        self.assertEqual(prospectivo["conclusivos"], 1)
        self.assertEqual(prospectivo["atingiram_faixa"], 1)
        self.assertEqual(prospectivo["greens_apos_faixa"], 0)
        self.assertEqual(prospectivo["roi_aguardando_alvo_hipotetico"], -1.0)
        self.assertEqual(
            prospectivo["roi_espera_estrategia_por_aviso"], -1.0
        )
        self.assertEqual(
            prospectivo["delta_roi_espera_vs_entrada_imediata"], 0.0
        )
        self.assertEqual(
            historico["roi_espera_estrategia_por_aviso"], -0.5
        )
        self.assertEqual(
            historico["delta_roi_espera_vs_entrada_imediata"], -0.1
        )
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["pronto_para_revisao_estrategia"])
        self.assertFalse(resultado["pronto_para_revisao_execucao"])
        self.assertEqual(resultado["faltam_conclusivos_prospectivos"], 29)
        self.assertEqual(
            resultado["estado"], "coorte_prospectiva_em_formacao"
        )
        self.assertFalse(resultado["promocao_automatica"])

    def test_trinta_historicos_nao_aprovam_coorte_rapida_vazia(self):
        for indice in range(1, 31):
            _, url = self.criar_aviso(indice)
            self.salvar_resultado(url, "1-0", "2026-09-01T12:02:00")
        resultado = avaliar_estrategia_acompanhamento_odd(self.banco)
        self.assertEqual(
            resultado["historico_exploratorio"]["conclusivos"], 30
        )
        self.assertEqual(
            resultado["coorte_prospectiva_rapida"]["conclusivos"], 0
        )
        self.assertFalse(resultado["pronto_para_revisao_estrategia"])
        self.assertEqual(resultado["faltam_conclusivos_prospectivos"], 30)

    def test_ancora_prospectiva_nao_reclassifica_aviso_antigo(self):
        sinal, url = self.criar_aviso(41, "2026-09-01T12:00:00")
        self.banco.registrar_observacao_acompanhamento_odd(
            sinal,
            {
                "odd": 1.40,
                "odd_oposta": 2.50,
                "linha": 0.5,
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T13:01:00",
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(indice=41),
            },
            {"placar": "0-0", "minuto": 52, "status": "52 '"},
            consultado_em="2026-09-01T13:01:00",
        )
        self.salvar_resultado(url, "1-0", "2026-09-01T13:05:00")

        resultado = avaliar_estrategia_acompanhamento_odd(
            self.banco,
            ancora_prospectiva="2026-09-01T13:00:00",
        )

        self.assertEqual(
            resultado["historico_exploratorio"]["conclusivos"], 1
        )
        self.assertEqual(
            resultado["coorte_prospectiva_rapida"]["conclusivos"], 0
        )
        self.assertEqual(
            resultado["criterio_coorte_prospectiva"],
            "aviso_criado_apos_ancora_e_monitorado_por_api_rapida",
        )

    def test_cotacao_anterior_ao_aviso_nao_finge_faixa_executavel(self):
        sinal, url = self.criar_aviso(51, "2026-09-01T12:00:00")
        self.banco.conexao.execute(
            "UPDATE entregas_alertas SET tentado_em=?, entregue_em=? "
            "WHERE sinal_id=?",
            ("2026-09-01T12:02:00", "2026-09-01T12:02:00", sinal),
        )
        self.banco.registrar_observacao_acompanhamento_odd(
            sinal,
            {
                "odd": 1.40, "odd_oposta": 2.50,
                "linha": 0.5, "fonte": "betsapi",
                "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T12:01:00",
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(indice=51),
            },
            {"placar": "0-0", "minuto": 47, "status": "47 '"},
            consultado_em="2026-09-01T12:01:00",
        )
        self.banco.registrar_observacao_acompanhamento_odd(
            sinal,
            {
                "odd": 1.30, "odd_oposta": 3.60,
                "linha": 0.5, "fonte": "betsapi",
                "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "coletado_em": "2026-09-01T12:03:00",
                "cache": False,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(indice=51),
            },
            {"placar": "0-0", "minuto": 49, "status": "49 '"},
            consultado_em="2026-09-01T12:03:00",
        )
        self.salvar_resultado(url, "1-0", "2026-09-01T12:05:00")

        resultado = avaliar_estrategia_acompanhamento_odd(
            self.banco,
            ancora_prospectiva="2026-09-01T11:59:00",
        )

        prospectivo = resultado["coorte_prospectiva_rapida"]
        self.assertEqual(1, prospectivo["conclusivos"])
        self.assertEqual(0, prospectivo["atingiram_faixa"])
        self.assertIsNone(prospectivo["tempo_mediano_ate_faixa_segundos"])
        self.assertEqual(
            "primeira_cotacao_api_rapida_pos_alerta_na_mesma_linha",
            resultado["criterio_execucao_faixa"],
        )

    def test_coorte_decisoria_usa_primeiro_aviso_por_partida_e_mercado(self):
        itens = [
            {
                "sinal_id": 2, "partida_id": 10, "mercado": "gol_ft",
                "aviso_em": "2026-09-01T12:02:00",
            },
            {
                "sinal_id": 1, "partida_id": 10, "mercado": "gol_ft",
                "aviso_em": "2026-09-01T12:01:00",
            },
            {
                "sinal_id": 3, "partida_id": 10, "mercado": "gol_ht",
                "aviso_em": "2026-09-01T12:03:00",
            },
        ]

        independentes = _primeiros_independentes(itens)

        self.assertEqual([1, 3], [item["sinal_id"] for item in independentes])


if __name__ == "__main__":
    unittest.main()
