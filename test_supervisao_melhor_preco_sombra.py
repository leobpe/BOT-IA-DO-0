import json
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path

from melhor_preco_sombra import VERSAO as VERSAO_MEDIDOR
from melhor_preco_sombra import VERSAO_VALOR_JUSTO
from supervisao_melhor_preco_sombra import (
    verificar_integridade_melhor_preco_sombra,
)
from validacao_resultado_valor_justo import politica_avaliacao_resultado


class SupervisaoMelhorPrecoSombraTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_supervisao_melhor_preco.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.c = sqlite3.connect(self.caminho)
        self.c.executescript("""
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                partida_id INTEGER,
                snapshot_id INTEGER,
                criado_em TEXT,
                mercado TEXT,
                features_json TEXT,
                status TEXT
            );
            CREATE TABLE odds (
                id INTEGER PRIMARY KEY,
                snapshot_id INTEGER,
                tipo TEXT,
                mercado TEXT,
                dados TEXT,
                estrutura_json TEXT
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY,
                encerrado_em TEXT,
                resultado TEXT,
                retorno_unidades REAL
            );
        """)
        self.agora = datetime(2026, 9, 11, 20, 0, 0)

    def tearDown(self):
        self.c.close()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    @staticmethod
    def sombra(**alteracoes):
        item = {
            "versao": VERSAO_MEDIDOR,
            "estado": "sem_referencia_independente_exata",
            "ofertas_exatas_validas": 1,
            "ofertas_exatas_validas_operacionais": 1,
            "ofertas_exatas_validas_referencia_sombra": 0,
            "alternativas_independentes_validas": 0,
            "referencia_sombra_recebida": False,
            "referencia_sombra_consultada": False,
            "valor_justo_sombra": {
                "versao": VERSAO_VALOR_JUSTO,
                "estado": "sem_referencia_sem_vig_sincronizada",
                "motivo": "sem_referencia_sem_vig_sincronizada",
                "limiar_valor_esperado": 0.02,
                "intervalo_fontes_maximo_segundos": 60.0,
                "desajuste_favoravel": False,
                "avaliacao_resultado_sombra": (
                    politica_avaliacao_resultado()
                ),
                "aplicacao_sinais": False,
                "altera_calibracao": False,
                "telegram": False,
                "promocao_automatica": False,
            },
            "aplicacao_sinais": False,
            "altera_calibracao": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        item.update(alteracoes)
        return item

    def inserir(self, identificador, sombra, snapshot_id=None):
        snapshot_id = snapshot_id or identificador + 100
        self.c.execute(
            "INSERT INTO sinais "
            "(id, partida_id, snapshot_id, criado_em, mercado, "
            "features_json, status) "
            "VALUES (?, ?, ?, ?, 'gol_ft', ?, 'auditoria')",
            (
                identificador,
                identificador + 1000,
                snapshot_id,
                "2026-09-11T19:30:00",
                json.dumps({"melhor_preco_sombra": sombra}),
            ),
        )
        self.c.commit()
        return snapshot_id

    def verificar(self):
        return verificar_integridade_melhor_preco_sombra(
            self.caminho, agora=self.agora
        )

    def test_ausencia_de_observacao_nao_e_falha(self):
        estado = self.verificar()

        self.assertTrue(estado["saudavel"])
        self.assertEqual("aguardando_observacao", estado["estado"])
        self.assertFalse(estado["requer_atencao"])

    def test_observacao_valida_sem_par_fica_em_coleta(self):
        self.inserir(1, self.sombra())

        estado = self.verificar()

        self.assertTrue(estado["saudavel"])
        self.assertEqual(
            "coletando_sem_referencia_independente", estado["estado"]
        )
        self.assertEqual(1, estado["observacoes"])
        self.assertEqual(1, estado["partidas_distintas"])
        self.assertEqual(0, estado["violacoes_efeito"])

    def test_par_separado_integro_e_contado(self):
        sombra = self.sombra(
            estado="comparacao_independente_exata",
            ofertas_exatas_validas=2,
            ofertas_exatas_validas_referencia_sombra=1,
            alternativas_independentes_validas=1,
            referencia_sombra_recebida=True,
            referencia_sombra_consultada=True,
            cotacao_escolhida={
                "fonte": "betsapi", "bookmaker": "bet365", "odd": 1.8,
            },
            melhor_alternativa_independente={
                "fonte": "the_odds_api", "bookmaker": "pinnacle",
                "odd": 1.92, "camada": "referencia_sombra",
            },
            diferenca_odd=0.12,
            relacao="alternativa_melhor",
        )
        snapshot_id = self.inserir(2, sombra)
        self.c.execute(
            "INSERT INTO odds VALUES (1, ?, 'referencia_sombra', '', '', '{}')",
            (snapshot_id,),
        )
        self.c.commit()

        estado = self.verificar()

        self.assertTrue(estado["saudavel"])
        self.assertEqual("comparando_preco_exato", estado["estado"])
        self.assertEqual(1, estado["comparacoes_independentes_exatas"])
        self.assertEqual(1, estado["comparacoes_com_referencia_separada"])
        self.assertEqual(1, estado["snapshots_com_referencia_persistida"])
        self.assertEqual(1, estado["referencias_separadas_recebidas"])

    def test_detecta_ponte_nao_refletida_na_persistencia(self):
        snapshot_id = self.inserir(3, self.sombra())
        self.c.execute(
            "INSERT INTO odds VALUES (1, ?, 'referencia_sombra', '', '', '{}')",
            (snapshot_id,),
        )
        self.c.commit()

        estado = self.verificar()

        self.assertFalse(estado["saudavel"])
        self.assertEqual("telemetria_inconsistente", estado["estado"])
        self.assertEqual(1, estado["violacoes_ponte_persistencia"])
        self.assertEqual("atencao", estado["severidade"])

    def test_detecta_declaracao_de_efeito_operacional(self):
        self.inserir(4, self.sombra(aplicacao_sinais=True))

        estado = self.verificar()

        self.assertFalse(estado["saudavel"])
        self.assertEqual("vazamento_operacional_declarado", estado["estado"])
        self.assertEqual("critica", estado["severidade"])
        self.assertEqual(1, estado["violacoes_efeito"])

    def test_detecta_comparacao_com_mesma_bookmaker(self):
        sombra = self.sombra(
            estado="comparacao_independente_exata",
            ofertas_exatas_validas=2,
            ofertas_exatas_validas_referencia_sombra=1,
            alternativas_independentes_validas=1,
            cotacao_escolhida={
                "fonte": "betsapi", "bookmaker": "Bet 365", "odd": 1.8,
            },
            melhor_alternativa_independente={
                "fonte": "the_odds_api", "bookmaker": "bet365",
                "odd": 1.92, "camada": "referencia_sombra",
            },
            diferenca_odd=0.12,
            relacao="alternativa_melhor",
        )
        self.inserir(5, sombra)

        estado = self.verificar()

        self.assertFalse(estado["saudavel"])
        self.assertEqual(1, estado["violacoes_estrutura"])

    def test_valor_justo_integro_e_supervisionado(self):
        valor = {
            "versao": VERSAO_VALOR_JUSTO,
            "estado": "desajuste_favoravel_candidato",
            "motivo": "referencia_independente_sem_vig_disponivel",
            "limiar_valor_esperado": 0.02,
            "intervalo_fontes_maximo_segundos": 60.0,
            "desajuste_favoravel": True,
            "avaliacao_resultado_sombra": (
                politica_avaliacao_resultado()
            ),
            "referencia": {
                "fonte": "the_odds_api",
                "bookmaker": "pinnacle",
                "camada": "referencia_sombra",
                "coletado_em": "2026-09-11T19:29:50+00:00",
                "probabilidade_selecao_sem_vig": 0.5,
                "margem_bookmaker": 0.05,
                "identidade_evento": {
                    "schema": "identidade-evento-odd-v1",
                    "confirmada": True,
                    "fonte": "the_odds_api",
                    "mandante_normalizado": "timecasa",
                    "visitante_normalizado": "timefora",
                    "placar_normalizado": "0-0",
                },
            },
            "identidade_evento_escolhida": {
                "schema": "identidade-evento-odd-v1",
                "confirmada": True,
                "fonte": "betsapi",
                "mandante_normalizado": "timecasa",
                "visitante_normalizado": "timefora",
                "placar_normalizado": "0-0",
            },
            "sincronismo_estado": {
                "comprovado": True,
                "intervalo_fontes_segundos": 10.0,
                "intervalo_maximo_segundos": 60.0,
                "mandante_normalizado": "timecasa",
                "visitante_normalizado": "timefora",
                "placar_normalizado": "0-0",
            },
            "odd_escolhida": 2.1,
            "probabilidade_equilibrio_odd_escolhida": 0.47619048,
            "probabilidade_referencia_sem_vig": 0.5,
            "vantagem_probabilidade_pontos_percentuais": 2.381,
            "valor_esperado_referencia": 0.05,
            "aplicacao_sinais": False,
            "altera_calibracao": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        self.inserir(7, self.sombra(
            cotacao_escolhida={
                "fonte": "betsapi", "bookmaker": "bet365", "odd": 2.1,
                "coletado_em": "2026-09-11T19:30:00+00:00",
            },
            valor_justo_sombra=valor,
        ))

        estado = self.verificar()

        self.assertTrue(estado["saudavel"])
        self.assertEqual(1, estado["avaliacoes_valor_justo"])
        self.assertEqual(1, estado["desajustes_valor_justo_candidatos"])
        self.assertEqual(0, estado["violacoes_valor_justo"])

    def test_detecta_valor_esperado_incoerente(self):
        valor = self.sombra()["valor_justo_sombra"]
        valor.update({
            "estado": "desajuste_favoravel_candidato",
            "desajuste_favoravel": True,
            "referencia": {
                "fonte": "the_odds_api", "bookmaker": "pinnacle",
                "camada": "referencia_sombra",
                "coletado_em": "2026-09-11T19:29:50+00:00",
                "probabilidade_selecao_sem_vig": 0.5,
                "margem_bookmaker": 0.05,
                "identidade_evento": {
                    "schema": "identidade-evento-odd-v1",
                    "confirmada": True,
                    "fonte": "the_odds_api",
                    "mandante_normalizado": "timecasa",
                    "visitante_normalizado": "timefora",
                    "placar_normalizado": "0-0",
                },
            },
            "identidade_evento_escolhida": {
                "schema": "identidade-evento-odd-v1",
                "confirmada": True,
                "fonte": "betsapi",
                "mandante_normalizado": "timecasa",
                "visitante_normalizado": "timefora",
                "placar_normalizado": "0-0",
            },
            "sincronismo_estado": {
                "comprovado": True,
                "intervalo_fontes_segundos": 10.0,
                "intervalo_maximo_segundos": 60.0,
                "mandante_normalizado": "timecasa",
                "visitante_normalizado": "timefora",
                "placar_normalizado": "0-0",
            },
            "odd_escolhida": 2.1,
            "probabilidade_equilibrio_odd_escolhida": 0.47619048,
            "probabilidade_referencia_sem_vig": 0.5,
            "vantagem_probabilidade_pontos_percentuais": 2.381,
            "valor_esperado_referencia": 0.90,
        })
        self.inserir(8, self.sombra(
            cotacao_escolhida={
                "fonte": "betsapi", "bookmaker": "bet365", "odd": 2.1,
                "coletado_em": "2026-09-11T19:30:00+00:00",
            },
            valor_justo_sombra=valor,
        ))

        estado = self.verificar()

        self.assertFalse(estado["saudavel"])
        self.assertEqual(1, estado["violacoes_valor_justo"])
        self.assertEqual("telemetria_inconsistente", estado["estado"])

    def test_versao_anterior_nao_contamina_coorte(self):
        self.inserir(6, self.sombra(versao="versao-antiga"))

        estado = self.verificar()

        self.assertTrue(estado["saudavel"])
        self.assertEqual(0, estado["observacoes"])
        self.assertEqual(1, estado["versoes_anteriores"])


if __name__ == "__main__":
    unittest.main()
