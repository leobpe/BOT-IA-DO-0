import hashlib
import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from avaliacao_clv_live import (
    _metricas,
    _resumo_cobertura,
    _resumo_coorte_clv_prospectiva,
    _resumo_cotacao_entrada_prospectiva,
    auditar_cadeia_custodia_clv,
    avaliar,
    avaliar_sinal,
    carregar_sinais_entregues,
)
from banco import BancoMonitor


def identidade_evento_teste(placar="0-0"):
    return {
        "schema": "identidade-evento-odd-v1",
        "confirmada": True,
        "fonte": "betsapi",
        "evento_externo_id": "evento-123",
        "orientacao": "direta",
        "similaridade": 0.95,
        "mandante_normalizado": "A",
        "visitante_normalizado": "B",
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


class AvaliacaoClvLiveTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE snapshots (
              id INTEGER PRIMARY KEY, partida_id INTEGER, coletado_em TEXT,
              placar TEXT, estatisticas_json TEXT
            );
            CREATE TABLE sinais (
              id INTEGER PRIMARY KEY, partida_id INTEGER, snapshot_id INTEGER,
              criado_em TEXT, mercado TEXT, linha TEXT, odd REAL,
              regra_versao TEXT, features_json TEXT
            );
            CREATE TABLE odds (
              id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER,
              estrutura_json TEXT
            );
            CREATE TABLE entregas_alertas (
              id INTEGER PRIMARY KEY AUTOINCREMENT, sinal_id INTEGER,
              canal TEXT, tentado_em TEXT, entregue_em TEXT, status TEXT
            );
            """
        )
        self.inicio = datetime(2026, 9, 9, 10, 0, 0)

    def tearDown(self):
        self.conexao.close()

    @staticmethod
    def _estrutura_binaria(
        over, under, *, categoria="gols", campo="ofertas",
        fonte="packball", bookmaker=None, tipo="total", linha=1.5,
    ):
        estrutura = {
            "categoria": categoria,
            "escopo": "total",
            "tipo_mercado": tipo,
            "ofertas": [],
            "ofertas_ht": [],
            "fonte": fonte,
            "bookmaker": bookmaker,
            "cache": False,
            "idade_segundos": 0,
        }
        estrutura[campo] = [{
            "linha": linha, "over": over, "under": under,
            "fonte": fonte, "bookmaker": bookmaker,
            "cache": False, "idade_segundos": 0,
        }]
        return estrutura

    @staticmethod
    def _estrutura_tres_vias(
        casa, visitante, sem_gol, *, fonte="packball", bookmaker=None,
    ):
        return {
            "categoria": "gols",
            "escopo": "proximo",
            "tipo_mercado": "proximo",
            "selecoes": {
                "casa": casa, "visitante": visitante, "sem_gol": sem_gol,
            },
            "fonte": fonte,
            "bookmaker": bookmaker,
            "cache": False,
            "idade_segundos": 0,
        }

    def _snapshot(
        self, identificador, segundos, *, placar="0-0", cantos="1-1",
        estrutura=None,
    ):
        instante = self.inicio + timedelta(seconds=segundos)
        self.conexao.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?,?)",
            (
                identificador, 10, instante.isoformat(), placar,
                json.dumps({"Escanteios": cantos}),
            ),
        )
        if estrutura is not None:
            self.conexao.execute(
                "INSERT INTO odds(snapshot_id,estrutura_json) VALUES (?,?)",
                (identificador, json.dumps(estrutura)),
            )

    def _sinal(
        self, *, mercado="gol_ft", linha="1.5", odd=1.8,
        fonte="packball", bookmaker=None, cotacao_entrada=None,
        origem_mercado=None,
    ):
        features = {
            "fonte_odds": fonte,
            "bookmaker_odds": bookmaker,
        }
        if cotacao_entrada is not None:
            features["cotacao_entrada_clv"] = cotacao_entrada
        if origem_mercado is not None:
            features["acompanhamento_odd_rapido"] = {
                "origem_mercado_odd": origem_mercado,
            }
        self.conexao.execute(
            "INSERT INTO sinais VALUES (?,?,?,?,?,?,?,?,?)",
            (
                20, 10, 1, self.inicio.isoformat(), mercado, linha, odd,
                "regra-v1", json.dumps(features),
            ),
        )
        self.conexao.execute(
            "INSERT INTO entregas_alertas(sinal_id,canal,tentado_em,entregue_em,status) VALUES (?,?,?,?,?)",
            (
                20, "grupo:teste", self.inicio.isoformat(),
                (self.inicio + timedelta(seconds=5)).isoformat(), "entregue",
            ),
        )

    def test_binario_mede_movimento_sem_vig_positivo(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.8, 2.0)
        )
        self._snapshot(
            2, 150, estrutura=self._estrutura_binaria(1.6, 2.2)
        )
        self._sinal()

        sinal = carregar_sinais_entregues(self.conexao)[0]
        resultado = avaliar_sinal(self.conexao, sinal)

        self.assertEqual("comparavel", resultado["estado"])
        self.assertTrue(resultado["movimento_favoravel"])
        self.assertGreater(resultado["clv_probabilidade_pontos"], 0)
        self.assertEqual("packball", resultado["fonte"])
        self.assertEqual("snapshot_legado", resultado["origem_cotacao_entrada"])
        self.assertAlmostEqual(
            1 / 1.8 + 1 / 2.0 - 1,
            resultado["margem_bookmaker_entrada"],
            places=6,
        )
        self.assertAlmostEqual(
            1 / 1.6 + 1 / 2.2 - 1,
            resultado["margem_bookmaker_futura"],
            places=6,
        )

    def test_exclui_cotacao_de_entrada_com_margem_incoerente(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.2, 1.2)
        )
        self._snapshot(
            2, 130, estrutura=self._estrutura_binaria(1.6, 2.2)
        )
        self._sinal(odd=1.2)

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("excluido", resultado["estado"])
        self.assertEqual(
            "cotacao_entrada_margem_incoerente", resultado["motivo"]
        )

    def test_nao_aprende_com_cotacao_futura_de_margem_incoerente(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.8, 2.0)
        )
        self._snapshot(
            2, 130, estrutura=self._estrutura_binaria(1.2, 1.2)
        )
        self._sinal()

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("nao_comparavel", resultado["estado"])
        self.assertEqual(
            "cotacao_futura_margem_incoerente", resultado["motivo"]
        )

    def test_cotacao_congelada_preserva_entrada_com_snapshot_ambiguo(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.8, 2.0)
        )
        self.conexao.execute(
            "INSERT INTO odds(snapshot_id,estrutura_json) VALUES (?,?)",
            (1, json.dumps(self._estrutura_binaria(1.8, 2.4))),
        )
        self._snapshot(
            2, 130, estrutura=self._estrutura_binaria(1.6, 2.2)
        )
        self._sinal(cotacao_entrada={
            "schema": "cotacao-entrada-clv-v1",
            "mercado": "gol_ft",
            "tipo": "binaria",
            "linha": 1.5,
            "over": 1.8,
            "under": 2.0,
            "odd_selecionada": 1.8,
            "fonte": "packball",
            "bookmaker": None,
            "coletado_em": self.inicio.isoformat(),
            "idade_segundos": 0,
            "cache": False,
        })

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("comparavel", resultado["estado"])
        self.assertEqual("congelada_v1", resultado["origem_cotacao_entrada"])

    def test_cotacao_congelada_adulterada_falha_fechada(self):
        self._snapshot(1, 0)
        self._sinal(cotacao_entrada={
            "schema": "cotacao-entrada-clv-v1",
            "mercado": "gol_ft",
            "tipo": "binaria",
            "linha": 1.5,
            "over": 1.9,
            "under": 2.0,
            "odd_selecionada": 1.9,
            "fonte": "packball",
            "bookmaker": None,
            "coletado_em": self.inicio.isoformat(),
            "idade_segundos": 0,
            "cache": False,
        })

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("excluido", resultado["estado"])
        self.assertEqual(
            "cotacao_entrada_congelada_invalida", resultado["motivo"]
        )
        self.assertEqual(
            "congelada_v1_invalida", resultado["origem_cotacao_entrada"]
        )

    def test_cotacao_v2_com_origem_adulterada_falha_fechada(self):
        self._snapshot(1, 0)
        origem = origem_mercado_teste(1.5)
        adulterada = dict(origem)
        adulterada["identificador"] = "outro-grupo"
        self._sinal(
            fonte="betsapi", bookmaker="bet365", origem_mercado=origem,
            cotacao_entrada={
                "schema": "cotacao-entrada-clv-v2",
                "mercado": "gol_ft", "tipo": "binaria",
                "linha": 1.5, "over": 1.8, "under": 2.0,
                "odd_selecionada": 1.8,
                "fonte": "betsapi", "bookmaker": "bet365",
                "coletado_em": self.inicio.isoformat(),
                "idade_segundos": 0, "cache": False,
                "origem_mercado": adulterada,
            },
        )

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("excluido", resultado["estado"])
        self.assertEqual(
            "cotacao_entrada_congelada_invalida", resultado["motivo"]
        )
        self.assertEqual(
            "congelada_v2_invalida", resultado["origem_cotacao_entrada"]
        )

    def test_proximo_gol_usa_tres_vias_congeladas(self):
        self._snapshot(1, 0)
        self._snapshot(
            2, 130,
            estrutura=self._estrutura_tres_vias(1.6, 4.0, 6.0),
        )
        self._sinal(
            mercado="proximo_gol", linha="casa", odd=1.8,
            cotacao_entrada={
                "schema": "cotacao-entrada-clv-v1",
                "mercado": "proximo_gol",
                "tipo": "tres_vias",
                "selecao": "casa",
                "odds": {
                    "casa": 1.8, "visitante": 3.5, "sem_gol": 5.0,
                },
                "odd_selecionada": 1.8,
                "fonte": "packball",
                "bookmaker": None,
                "coletado_em": self.inicio.isoformat(),
                "idade_segundos": 0,
                "cache": False,
            },
        )

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("comparavel", resultado["estado"])
        self.assertEqual("congelada_v1", resultado["origem_cotacao_entrada"])
        self.assertTrue(resultado["movimento_favoravel"])

    def test_proximo_gol_exige_e_normaliza_as_tres_vias(self):
        self._snapshot(
            1, 0,
            estrutura=self._estrutura_tres_vias(1.8, 3.5, 5.0),
        )
        self._snapshot(
            2, 130,
            estrutura=self._estrutura_tres_vias(1.6, 4.0, 6.0),
        )
        self._sinal(mercado="proximo_gol", linha="casa", odd=1.8)

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("comparavel", resultado["estado"])
        self.assertTrue(resultado["movimento_favoravel"])

    def test_proximo_gol_do_adversario_entra_como_red_terminal(self):
        self._snapshot(
            1, 0,
            estrutura=self._estrutura_tres_vias(1.8, 3.5, 5.0),
        )
        self._snapshot(2, 60, placar="0-1")
        self._sinal(mercado="proximo_gol", linha="casa", odd=1.8)

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("comparavel", resultado["estado"])
        self.assertEqual(
            "liquidado_red", resultado["origem_valor_horizonte"]
        )
        self.assertEqual(0.0, resultado["valor_probabilidade_horizonte"])

    def test_observacao_rapida_bet365_mede_preco_sem_snapshot_principal(self):
        caminho = Path.cwd() / ".teste_clv_rapido_preco.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            origem = origem_mercado_teste(0.5)
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-12T10:00:00",
                "url": "https://packball.com/match/clv-rapido/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "20 '",
                "confirmacao_api": {
                    "fixture_id": 123, "orientacao": "direta",
                },
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.80,
                "regra_versao": "teste-clv-rapido-preco-v1",
                "status": "aprovado",
                "features": {
                    "fonte_odds": "betsapi",
                    "bookmaker_odds": "bet365",
                    "cotacao_entrada_clv_estado": "congelada_v1",
                    "acompanhamento_odd_rapido": {
                        "origem_mercado_odd": origem,
                    },
                    "cotacao_entrada_clv": {
                        "schema": "cotacao-entrada-clv-v2",
                        "mercado": "gol_ft", "tipo": "binaria",
                        "linha": 0.5, "over": 1.80, "under": 2.00,
                        "odd_selecionada": 1.80,
                        "fonte": "betsapi", "bookmaker": "bet365",
                        "coletado_em": "2026-09-12T10:00:00",
                        "idade_segundos": 0.0, "cache": False,
                        "origem_mercado": origem,
                    },
                },
            }])[0]
            with banco.conexao:
                banco.conexao.execute(
                    "UPDATE sinais SET criado_em=? WHERE id=?",
                    ("2026-09-12T10:00:00", sinal),
                )
            banco.registrar_entrega_alerta(
                sinal, "chat", "entregue",
                instante="2026-09-12T10:00:05",
                provedor="telegram", provedor_destino_id="chat",
                provedor_mensagem_id="clv-preco-1",
                confirmacao={
                    "provedor": "telegram", "ok": True,
                    "message_id": "clv-preco-1",
                },
            )
            instante = "2026-09-12T10:02:15"
            oferta = {
                "odd": 1.60, "odd_oposta": 2.20, "linha": 0.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0, "coletado_em": instante,
                "cache": False, "origem_mercado": origem,
                "identidade_evento": identidade_evento_teste(),
            }
            odds = {"ao_vivo": [{
                "categoria": "gols", "escopo": "total",
                "tipo_mercado": "total", "formato": "duas_opcoes",
                "fonte": "betsapi", "bookmaker": "bet365",
                "ofertas": [{
                    "linha": 0.5, "over": 1.60, "under": 2.20,
                    "origem_mercado": origem,
                    "identidade_evento": identidade_evento_teste(),
                }],
                "ofertas_ht": [],
            }]}
            cotacao = banco.registrar_observacao_acompanhamento_odd(
                sinal, oferta,
                {"placar": "0-0", "minuto": 22, "status": "22 '"},
                consultado_em=instante, odds=odds,
            )
            estado = banco.registrar_estado_clv_pos_alerta(
                sinal,
                {
                    "evento_externo_id": 123, "placar": "0-0",
                    "minuto": 22, "status_codigo": "1H",
                },
                observacao_oferta_id=cotacao["observacao_id"],
                consultado_em=instante,
            )

            self.assertTrue(cotacao["persistido"])
            self.assertTrue(estado["persistido"])
            auditoria = auditar_cadeia_custodia_clv(banco.conexao)
            self.assertTrue(auditoria["saudavel"], auditoria)
            self.assertEqual(
                1,
                auditoria["integridade_evidencias"][
                    "estados_clv_pos_alerta"
                ],
            )
            resultado = avaliar_sinal(
                banco.conexao, carregar_sinais_entregues(banco.conexao)[0]
            )
            self.assertEqual("comparavel", resultado["estado"], resultado)
            self.assertEqual("api_rapida_clv", resultado["origem_medicao_horizonte"])
            self.assertEqual(estado["observacao_id"], resultado["observacao_clv_id"])
            self.assertIsNone(resultado["snapshot_futuro_id"])
            self.assertEqual(1.60, resultado["odd_futura"])
            self.assertTrue(resultado["movimento_favoravel"])
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_estado_rapido_packball_ht_encerrado_sem_gol_conta_red(self):
        caminho = Path.cwd() / ".teste_clv_rapido_ht_red.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-12T10:00:00",
                "url": "https://packball.com/match/clv-ht-red/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "42 '",
                "confirmacao_api": {
                    "fixture_id": 123, "orientacao": "direta",
                },
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ht", "linha": 0.5, "odd": 1.80,
                "regra_versao": "teste-clv-rapido-ht-red-v1",
                "status": "aprovado",
                "features": {
                    "fonte_odds": "packball",
                    "bookmaker_odds": None,
                    "cotacao_entrada_clv_estado": "congelada_v1",
                    "cotacao_entrada_clv": {
                        "schema": "cotacao-entrada-clv-v1",
                        "mercado": "gol_ht", "tipo": "binaria",
                        "linha": 0.5, "over": 1.80, "under": 2.00,
                        "odd_selecionada": 1.80,
                        "fonte": "packball", "bookmaker": None,
                        "coletado_em": "2026-09-12T10:00:00",
                        "idade_segundos": 0.0, "cache": False,
                    },
                },
            }])[0]
            with banco.conexao:
                banco.conexao.execute(
                    "UPDATE sinais SET criado_em=? WHERE id=?",
                    ("2026-09-12T10:00:00", sinal),
                )
            banco.registrar_entrega_alerta(
                sinal, "chat", "entregue",
                instante="2026-09-12T10:00:05",
                provedor="telegram", provedor_destino_id="chat",
                provedor_mensagem_id="clv-ht-red-1",
                confirmacao={
                    "provedor": "telegram", "ok": True,
                    "message_id": "clv-ht-red-1",
                },
            )
            estado = banco.registrar_estado_clv_pos_alerta(
                sinal,
                {
                    "evento_externo_id": 123, "placar": "0-0",
                    "minuto": 45, "status_codigo": "HT",
                },
                consultado_em="2026-09-12T10:02:15",
            )

            self.assertTrue(estado["persistido"])
            resultado = avaliar_sinal(
                banco.conexao, carregar_sinais_entregues(banco.conexao)[0]
            )
            self.assertEqual("comparavel", resultado["estado"], resultado)
            self.assertEqual("liquidado_red", resultado["origem_valor_horizonte"])
            self.assertEqual(0.0, resultado["valor_probabilidade_horizonte"])
            self.assertEqual("api_rapida_clv", resultado["origem_medicao_horizonte"])

            auditoria = auditar_cadeia_custodia_clv(banco.conexao)
            self.assertTrue(auditoria["saudavel"], auditoria)
            features_divergentes = json.loads(
                banco.conexao.execute(
                    "SELECT features_json FROM sinais WHERE id=?", (sinal,)
                ).fetchone()[0]
            )
            features_divergentes["cotacao_entrada_clv"]["mercado"] = (
                "gol_ft"
            )
            sinal_divergente = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.80,
                "regra_versao": "teste-clv-fonte-divergente-v1",
                "status": "aprovado", "features": features_divergentes,
            }])[0]
            banco.registrar_entrega_alerta(
                sinal_divergente, "chat", "entregue",
                instante="2026-09-12T10:00:05",
                provedor="telegram", provedor_destino_id="chat",
                provedor_mensagem_id="clv-fonte-divergente-1",
                confirmacao={
                    "provedor": "telegram", "ok": True,
                    "message_id": "clv-fonte-divergente-1",
                },
            )
            payload_divergente = json.loads(
                banco.conexao.execute(
                    "SELECT oferta_json FROM observacoes_fontes_odds WHERE id=?",
                    (estado["observacao_id"],),
                ).fetchone()[0]
            )
            payload_divergente.update({
                "sinal_id": sinal_divergente,
                "mercado": "gol_ft",
                "fonte_entrada": "betsapi",
                "bookmaker_entrada": "bet365",
                "modo_coleta": "estado_e_preco",
            })
            documento_divergente = json.dumps(
                payload_divergente, ensure_ascii=False,
                sort_keys=True, separators=(",", ":"),
            )
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        partida_id, fonte, consultado_em, estado, mercado,
                        evento_externo_id, oferta_json, evidencia_sha256,
                        evidencia_referencia
                    ) VALUES (?, 'api_football', ?, ?, 'gol_ft', ?, ?, ?, ?)
                    """,
                    (
                        banco.conexao.execute(
                            "SELECT partida_id FROM sinais WHERE id=?",
                            (sinal_divergente,),
                        ).fetchone()[0],
                        "2026-09-12T10:02:15", "clv_pos_alerta",
                        "123", documento_divergente,
                        hashlib.sha256(
                            documento_divergente.encode("utf-8")
                        ).hexdigest(),
                        f"clv_pos_alerta:{sinal_divergente}",
                    ),
                )
            adulterada = auditar_cadeia_custodia_clv(banco.conexao)
            self.assertFalse(adulterada["saudavel"])
            self.assertEqual(
                1,
                adulterada["integridade_evidencias"]["problemas"][
                    "estado_clv_fonte_entrada_divergente"
                ],
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_observacao_rapida_mede_escanteio_asiatico_sem_snapshot(self):
        caminho = Path.cwd() / ".teste_clv_rapido_cantos.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            origem = origem_mercado_teste(8.5)
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-12T10:00:00",
                "url": "https://packball.com/match/clv-cantos/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
                "estatisticas": {"Escanteios": "3-2"},
                "confirmacao_api": {
                    "fixture_id": 123, "orientacao": "direta",
                },
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "escanteios_ft_asiatico",
                "linha": 8.5,
                "odd": 1.84,
                "regra_versao": "teste-clv-rapido-cantos-v1",
                "status": "aprovado",
                "features": {
                    "fonte_odds": "betsapi",
                    "bookmaker_odds": "bet365",
                    "cotacao_entrada_clv_estado": "congelada_v1",
                    "cotacao_entrada_clv": {
                        "schema": "cotacao-entrada-clv-v2",
                        "mercado": "escanteios_ft_asiatico",
                        "tipo": "binaria", "linha": 8.5,
                        "over": 1.84, "under": 2.02,
                        "odd_selecionada": 1.84,
                        "fonte": "betsapi", "bookmaker": "bet365",
                        "coletado_em": "2026-09-12T10:00:00",
                        "idade_segundos": 0.0, "cache": False,
                        "origem_mercado": origem,
                    },
                },
            }])[0]
            with banco.conexao:
                banco.conexao.execute(
                    "UPDATE sinais SET criado_em=? WHERE id=?",
                    ("2026-09-12T10:00:00", sinal),
                )
            banco.registrar_entrega_alerta(
                sinal, "chat", "entregue",
                instante="2026-09-12T10:00:05",
                provedor="telegram", provedor_destino_id="chat",
                provedor_mensagem_id="clv-cantos-1",
                confirmacao={
                    "provedor": "telegram", "ok": True,
                    "message_id": "clv-cantos-1",
                },
            )
            instante = "2026-09-12T10:02:15"
            identidade = identidade_evento_teste()
            oferta = {
                "odd": 1.70, "odd_oposta": 2.15, "linha": 8.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0, "coletado_em": instante,
                "cache": False, "origem_mercado": origem,
                "identidade_evento": identidade,
            }
            odds = {"ao_vivo": [{
                "categoria": "escanteios", "escopo": "total",
                "tipo_mercado": "asiatico", "formato": "duas_opcoes",
                "fonte": "betsapi", "bookmaker": "bet365",
                "ofertas": [{
                    "linha": 8.5, "over": 1.70, "under": 2.15,
                    "origem_mercado": origem,
                    "identidade_evento": identidade,
                }],
            }]}
            cotacao = banco.registrar_observacao_acompanhamento_odd(
                sinal, oferta,
                {"placar": "0-0", "minuto": 62, "status": "62 '"},
                consultado_em=instante, odds=odds,
            )
            estado = banco.registrar_estado_clv_pos_alerta(
                sinal,
                {
                    "evento_externo_id": 123, "placar": "0-0",
                    "minuto": 62, "status_codigo": "2H",
                    "escanteios": {"mandante": 5, "visitante": 4},
                },
                observacao_oferta_id=cotacao["observacao_id"],
                consultado_em=instante,
            )

            self.assertTrue(cotacao["persistido"], cotacao)
            self.assertTrue(estado["persistido"], estado)
            resultado = avaliar_sinal(
                banco.conexao, carregar_sinais_entregues(banco.conexao)[0]
            )
            self.assertEqual("comparavel", resultado["estado"], resultado)
            self.assertEqual(
                "api_rapida_clv", resultado["origem_medicao_horizonte"]
            )
            self.assertIsNone(resultado["odd_futura"])
            self.assertEqual(
                "liquidado_green", resultado["origem_valor_horizonte"]
            )
            self.assertTrue(resultado["movimento_favoravel"])
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_nao_mistura_fonte_ou_bookmaker(self):
        self._snapshot(
            1, 0,
            estrutura=self._estrutura_binaria(
                1.8, 2.0, fonte="betsapi", bookmaker="bet365"
            ),
        )
        self._snapshot(
            2, 130,
            estrutura=self._estrutura_binaria(
                1.6, 2.2, fonte="betsapi", bookmaker="bet365"
            ),
        )
        self._sinal(fonte="packball")

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("excluido", resultado["estado"])
        self.assertEqual(
            "cotacao_entrada_exata_ausente_ou_ambigua",
            resultado["motivo"],
        )

    def test_linha_asiatica_nao_binaria_nao_finge_liquidacao_cheia(self):
        entrada = self._estrutura_binaria(
            1.8, 2.0, categoria="escanteios", tipo="asiatico", linha=8.25
        )
        self._snapshot(1, 0, cantos="4-4", estrutura=entrada)
        self._sinal(
            mercado="escanteios_ft_asiatico", linha="8.25", odd=1.8
        )

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("excluido", resultado["estado"])
        self.assertEqual(
            "linha_nao_binaria_sem_liquidacao_1_0", resultado["motivo"]
        )

    def test_gol_antes_de_dois_minutos_entra_como_valor_terminal(self):
        self._snapshot(
            1, 0,
            estrutura=self._estrutura_binaria(1.8, 2.0, linha=0.5),
        )
        self._snapshot(2, 60, placar="1-0")
        self._sinal(linha="0.5")

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("comparavel", resultado["estado"])
        self.assertEqual(
            "liquidado_green", resultado["origem_valor_horizonte"]
        )
        self.assertEqual(1.0, resultado["valor_probabilidade_horizonte"])

    def test_escanteio_nao_compara_estado_diferente(self):
        entrada = self._estrutura_binaria(
            1.8, 2.0, categoria="escanteios", linha=2.5
        )
        self._snapshot(1, 0, cantos="1-1", estrutura=entrada)
        self._snapshot(2, 60, cantos="2-1")
        self._sinal(
            mercado="proximo_escanteio", linha="2.5", odd=1.8
        )

        resultado = avaliar_sinal(
            self.conexao, carregar_sinais_entregues(self.conexao)[0]
        )

        self.assertEqual("comparavel", resultado["estado"])
        self.assertEqual(
            "liquidado_green", resultado["origem_valor_horizonte"]
        )

    def test_deduplica_entrega_e_nao_altera_banco(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.8, 2.0)
        )
        self._snapshot(
            2, 130, estrutura=self._estrutura_binaria(1.7, 2.1)
        )
        self._sinal()
        self.conexao.execute(
            "INSERT INTO entregas_alertas(sinal_id,canal,tentado_em,entregue_em,status) VALUES (?,?,?,?,?)",
            (
                20, "grupo:teste:resultado", self.inicio.isoformat(),
                (self.inicio + timedelta(seconds=300)).isoformat(),
                "entregue",
            ),
        )
        antes = self.conexao.total_changes

        resumo = avaliar(self.conexao)

        self.assertEqual(1, resumo["sinais_entregues_consultados"])
        self.assertEqual(1, resumo["comparaveis"])
        cobertura = resumo["por_mercado"]["gol_ft"]
        self.assertEqual(1, cobertura["entregas_consultadas"])
        self.assertEqual(1, cobertura["comparaveis"])
        self.assertEqual(1.0, cobertura["taxa_cobertura"])
        self.assertEqual({}, cobertura["exclusoes"])
        self.assertEqual(
            {"snapshot_legado": 1},
            cobertura["origens_cotacao_entrada"],
        )
        self.assertEqual(
            1, cobertura["ultimas_30_entregas"]["comparaveis"]
        )
        self.assertEqual(
            1, resumo["ultimas_100_entregas"]["comparaveis"]
        )
        self.assertEqual(antes, self.conexao.total_changes)
        self.assertFalse(resumo["gate_operacional"])
        self.assertFalse(resumo["promocao_automatica"])

    def test_correcao_de_resultado_nao_pode_virar_entrada_clv(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.8, 2.0)
        )
        self._sinal()
        self.conexao.execute(
            "DELETE FROM entregas_alertas WHERE sinal_id=20"
        )
        self.conexao.execute(
            """
            INSERT INTO entregas_alertas(
                sinal_id,canal,tentado_em,entregue_em,status
            ) VALUES (?,?,?,?,?)
            """,
            (
                20, "grupo:teste:correcao:1", self.inicio.isoformat(),
                self.inicio.isoformat(), "entregue",
            ),
        )

        self.assertEqual([], carregar_sinais_entregues(self.conexao))

    def test_cobertura_preserva_denominador_e_motivo_por_regra(self):
        self._snapshot(
            1, 0,
            estrutura=self._estrutura_binaria(
                1.8, 2.0, fonte="betsapi", bookmaker="bet365"
            ),
        )
        self._sinal(fonte="packball")

        resumo = avaliar(self.conexao)

        cobertura = resumo["por_mercado"]["gol_ft"]
        self.assertEqual(1, cobertura["entregas_consultadas"])
        self.assertEqual(0, cobertura["comparaveis"])
        self.assertEqual(0.0, cobertura["taxa_cobertura"])
        self.assertEqual(
            {"cotacao_entrada_exata_ausente_ou_ambigua": 1},
            cobertura["exclusoes"],
        )
        grupo = resumo["por_regra_e_fonte"][0]
        self.assertEqual("regra-v1", grupo["regra_versao"])
        self.assertEqual("packball", grupo["fonte"])
        self.assertEqual(1, grupo["entregas_consultadas"])
        self.assertEqual(0, grupo["comparaveis"])

    def test_evidencia_exige_amostra_minima_mesmo_com_media_positiva(self):
        item = {
            "estado": "comparavel",
            "clv_probabilidade_pontos": 0.05,
            "origem_valor_horizonte": "cotacao_sem_vig",
            "segundos_apos_entrega": 130,
        }

        pequena = _metricas([dict(item) for _ in range(29)])
        suficiente = _metricas([dict(item) for _ in range(30)])
        sobreviventes = _metricas(
            [dict(item) for _ in range(30)],
            natureza="movimento_preco_condicionado_sobrevivencia",
        )

        self.assertEqual("amostra_insuficiente", pequena["estado_evidencia"])
        self.assertFalse(pequena["evidencia_valor_favoravel"])
        self.assertEqual(
            "mark_to_market_favoravel_com_ic95_positivo",
            suficiente["estado_evidencia"],
        )
        self.assertTrue(suficiente["evidencia_valor_favoravel"])
        self.assertTrue(suficiente["pode_informar_edge"])
        self.assertFalse(suficiente["pode_decidir_edge"])
        self.assertEqual(
            "diagnostico_condicionado_a_sobrevivencia",
            sobreviventes["estado_evidencia"],
        )
        self.assertFalse(sobreviventes["pode_decidir_edge"])
        self.assertFalse(sobreviventes["evidencia_valor_favoravel"])

    def test_cobertura_baixa_invalida_media_positiva_com_ic95(self):
        comparavel = {
            "estado": "comparavel",
            "clv_probabilidade_pontos": 0.05,
            "origem_valor_horizonte": "cotacao_sem_vig",
            "segundos_apos_entrega": 130,
        }
        ausente = {
            "estado": "nao_comparavel",
            "motivo": "cotacao_futura_exata_ausente",
        }

        resumo = _resumo_cobertura(
            [dict(comparavel) for _ in range(30)]
            + [dict(ausente) for _ in range(10)]
        )

        self.assertEqual(0.75, resumo["taxa_cobertura"])
        self.assertEqual(0.9, resumo["cobertura_minima_informar_edge"])
        self.assertFalse(
            resumo["cobertura_suficiente_para_informar_edge"]
        )
        self.assertEqual(
            "cobertura_insuficiente_para_informar_edge",
            resumo["estado_evidencia"],
        )
        self.assertFalse(resumo["evidencia_valor_favoravel"])
        self.assertFalse(resumo["pode_informar_edge"])

    def test_cobertura_prospectiva_nao_e_diluida_pelo_legado(self):
        legado = {
            "estado": "comparavel",
            "origem_cotacao_entrada": "snapshot_legado",
        }
        congelada = {
            "estado": "nao_comparavel",
            "estado_cotacao_entrada": "congelada_v1",
            "origem_cotacao_entrada": "congelada_v1",
        }
        incompleta = {
            "estado": "excluido",
            "estado_cotacao_entrada": "mercado_incompleto_ou_invalido",
        }
        corrompida = {
            "estado": "excluido",
            "estado_cotacao_entrada": "congelada_v1",
            "origem_cotacao_entrada": "congelada_v1_invalida",
        }

        resumo = _resumo_cotacao_entrada_prospectiva(
            [legado, congelada, incompleta, corrompida]
        )

        self.assertEqual(1, resumo["entregas_legadas_fora_do_denominador"])
        self.assertEqual(3, resumo["entregas_instrumentadas"])
        self.assertEqual(1, resumo["cotacoes_congeladas_validas"])
        self.assertEqual(1, resumo["cotacoes_congeladas_invalidas"])
        self.assertEqual(
            0.333333, resumo["taxa_cobertura_cotacao_entrada"]
        )
        self.assertEqual("formando_coorte_prospectiva", resumo["estado"])
        self.assertTrue(resumo["selecao_antes_da_comparabilidade"])
        self.assertFalse(resumo["pode_informar_edge"])
        self.assertFalse(resumo["gate_operacional"])

    def test_cobertura_prospectiva_exige_amostra_e_noventa_por_cento(self):
        congelada = {
            "estado": "comparavel",
            "estado_cotacao_entrada": "congelada_v1",
            "origem_cotacao_entrada": "congelada_v1",
        }
        incompleta = {
            "estado": "excluido",
            "estado_cotacao_entrada": "mercado_incompleto_ou_invalido",
        }

        suficiente = _resumo_cotacao_entrada_prospectiva(
            [dict(congelada) for _ in range(27)]
            + [dict(incompleta) for _ in range(3)]
        )
        insuficiente = _resumo_cotacao_entrada_prospectiva(
            [dict(congelada) for _ in range(26)]
            + [dict(incompleta) for _ in range(4)]
        )

        self.assertTrue(suficiente["amostra_suficiente"])
        self.assertTrue(suficiente["cobertura_suficiente"])
        self.assertEqual(
            "cobertura_cotacao_entrada_suficiente", suficiente["estado"]
        )
        self.assertFalse(insuficiente["cobertura_suficiente"])
        self.assertEqual(
            "cobertura_cotacao_entrada_insuficiente",
            insuficiente["estado"],
        )

    def test_coorte_clv_fixa_nao_move_holdout_com_novas_entregas(self):
        def item(indice):
            return {
                "sinal_id": indice,
                "partida_id": indice,
                "entregue_em": (
                    self.inicio + timedelta(minutes=indice)
                ).isoformat(),
                "estado": "comparavel",
                "estado_cotacao_entrada": "congelada_v1",
                "origem_cotacao_entrada": "congelada_v1",
                "clv_probabilidade_pontos": 0.05,
                "origem_valor_horizonte": "cotacao_sem_vig",
                "segundos_apos_entrega": 130,
            }

        inicial = _resumo_coorte_clv_prospectiva(
            [item(indice) for indice in range(1, 121)],
            {"saudavel": True},
        )
        ampliada = _resumo_coorte_clv_prospectiva(
            [item(indice) for indice in range(1, 131)],
            {"saudavel": True},
        )

        self.assertTrue(inicial["divisao_fixa"])
        self.assertEqual(84, inicial["tamanho_desenvolvimento"])
        self.assertEqual(36, inicial["tamanho_holdout"])
        self.assertEqual(120, ampliada["unidades_coorte"])
        self.assertEqual(10, ampliada["unidades_excedentes_fora_coorte"])
        self.assertEqual(
            inicial["fingerprint_ids"], ampliada["fingerprint_ids"]
        )
        self.assertEqual(1, ampliada["primeiro_sinal_id"])
        self.assertEqual(120, ampliada["ultimo_sinal_id"])
        self.assertTrue(ampliada["vantagem_replicada"])
        self.assertTrue(ampliada["pode_informar_edge"])
        self.assertFalse(ampliada["pode_decidir_edge"])
        self.assertFalse(ampliada["gate_operacional"])
        self.assertFalse(
            ampliada["desenvolvimento"]["pode_informar_edge"]
        )
        self.assertFalse(ampliada["holdout"]["pode_informar_edge"])
        self.assertEqual(
            "particao_isolada_da_coorte_fixa",
            ampliada["holdout"]["motivo_nao_inferencial"],
        )

    def test_coorte_clv_incompleta_nao_informa_edge(self):
        itens = [{
            "sinal_id": indice,
            "partida_id": indice,
            "entregue_em": (
                self.inicio + timedelta(minutes=indice)
            ).isoformat(),
            "estado": "comparavel",
            "estado_cotacao_entrada": "congelada_v1",
            "origem_cotacao_entrada": "congelada_v1",
            "clv_probabilidade_pontos": 0.05,
            "origem_valor_horizonte": "cotacao_sem_vig",
            "segundos_apos_entrega": 130,
        } for indice in range(1, 120)]

        resumo = _resumo_coorte_clv_prospectiva(
            itens, {"saudavel": True}
        )

        self.assertEqual(119, resumo["unidades_coorte"])
        self.assertEqual(1, resumo["unidades_faltantes"])
        self.assertEqual("formando_coorte_fixa", resumo["estado"])
        self.assertFalse(resumo["pronta_para_conclusao"])
        self.assertFalse(resumo["vantagem_replicada"])
        self.assertFalse(resumo["pode_informar_edge"])

    def test_coorte_clv_exclui_legado_antes_da_particao(self):
        legado = [{
            "sinal_id": indice,
            "partida_id": indice,
            "entregue_em": (
                self.inicio - timedelta(days=1, minutes=indice)
            ).isoformat(),
            "estado": "comparavel",
            "origem_cotacao_entrada": "snapshot_legado",
            "clv_probabilidade_pontos": 0.9,
            "origem_valor_horizonte": "liquidado_green",
            "segundos_apos_entrega": 60,
        } for indice in range(1, 201)]
        novo = {
            "sinal_id": 999,
            "partida_id": 999,
            "entregue_em": self.inicio.isoformat(),
            "estado": "comparavel",
            "estado_cotacao_entrada": "congelada_v1",
            "origem_cotacao_entrada": "congelada_v1",
            "clv_probabilidade_pontos": 0.01,
            "origem_valor_horizonte": "cotacao_sem_vig",
            "segundos_apos_entrega": 130,
        }

        resumo = _resumo_coorte_clv_prospectiva(
            [*legado, novo], {"saudavel": True}
        )

        self.assertEqual(1, resumo["unidades_coorte"])
        self.assertEqual(999, resumo["primeiro_sinal_id"])
        self.assertEqual(119, resumo["unidades_faltantes"])

    def test_coorte_com_edge_estatistico_falha_fechada_sem_custodia(self):
        itens = [{
            "sinal_id": indice,
            "partida_id": indice,
            "entregue_em": (
                self.inicio + timedelta(minutes=indice)
            ).isoformat(),
            "estado": "comparavel",
            "estado_cotacao_entrada": "congelada_v1",
            "origem_cotacao_entrada": "congelada_v1",
            "clv_probabilidade_pontos": 0.05,
            "origem_valor_horizonte": "cotacao_sem_vig",
            "segundos_apos_entrega": 130,
        } for indice in range(1, 121)]

        resumo = _resumo_coorte_clv_prospectiva(
            itens, {"saudavel": False}
        )

        self.assertTrue(resumo["pronta_estatisticamente"])
        self.assertFalse(resumo["cadeia_custodia_saudavel"])
        self.assertEqual("cadeia_custodia_invalida", resumo["estado"])
        self.assertFalse(resumo["pronta_para_conclusao"])
        self.assertFalse(resumo["vantagem_replicada"])
        self.assertFalse(resumo["pode_informar_edge"])

    def test_auditoria_custodia_detecta_rotulo_sem_cotacao_congelada(self):
        caminho = Path.cwd() / ".teste_custodia_cotacao_invalida.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-13T13:00:00",
                "url": "https://packball.com/match/cotacao-invalida/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "20 '",
                "confirmacao_api": {
                    "fixture_id": 123, "orientacao": "direta",
                },
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.60,
                "regra_versao": "teste-custodia-cotacao-invalida-v1",
                "status": "aprovado",
                "features": {
                    "fonte_odds": "packball", "bookmaker_odds": None,
                    "cotacao_entrada_clv_estado": "congelada_v1",
                },
            }])[0]
            banco.registrar_entrega_alerta(
                sinal, "chat", "entregue",
                instante="2026-09-13T13:00:00",
                provedor="telegram", provedor_destino_id="chat",
                provedor_mensagem_id="custodia-cotacao-invalida-1",
                confirmacao={
                    "provedor": "telegram", "ok": True,
                    "message_id": "custodia-cotacao-invalida-1",
                },
            )

            auditoria = auditar_cadeia_custodia_clv(banco.conexao)
            self.assertFalse(auditoria["saudavel"])
            self.assertEqual(
                1,
                auditoria["integridade_evidencias"][
                    "cotacoes_entrada_clv_entregues_auditadas"
                ],
            )
            self.assertEqual(
                1,
                auditoria["integridade_evidencias"]["problemas"][
                    "cotacao_entrada_clv_entregue_invalida"
                ],
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_custodia_valida_esquema_real_e_detecta_remocao(self):
        caminho = Path.cwd() / ".teste_cadeia_custodia_clv.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            integra = auditar_cadeia_custodia_clv(banco.conexao)
            self.assertTrue(integra["saudavel"])
            self.assertEqual("integra", integra["estado"])
            self.assertEqual(12, len(integra["gatilhos_presentes"]))
            self.assertEqual(64, len(integra["fingerprint_definicoes"]))
            self.assertTrue(
                integra["integridade_evidencias"]["saudavel"]
            )

            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        fonte, consultado_em, estado, oferta_json,
                        evidencia_sha256
                    ) VALUES (
                        'fonte-teste', '2026-09-10T01:00:00',
                        'oferta_disponivel', '{"odd":1.9}', ?
                    )
                    """,
                    ("0" * 64,),
                )
            corrompida = auditar_cadeia_custodia_clv(banco.conexao)
            self.assertFalse(corrompida["saudavel"])
            self.assertEqual(
                1,
                corrompida["integridade_evidencias"]["problemas"][
                    "hash_divergente"
                ],
            )
            self.assertEqual([], corrompida["gatilhos_ausentes"])

            with banco.conexao:
                banco.conexao.execute(
                    "DROP TRIGGER trg_odds_clv_delete_imutavel"
                )
            ausente = auditar_cadeia_custodia_clv(banco.conexao)
            self.assertFalse(ausente["saudavel"])
            self.assertTrue(ausente["bloqueia_inferencia"])
            self.assertEqual(
                ["trg_odds_clv_delete_imutavel"],
                ausente["gatilhos_ausentes"],
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_custodia_detecta_regressao_temporal(self):
        caminho = Path.cwd() / ".teste_ordem_temporal_clv.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-10T10:00:00",
                "url": "https://packball.com/match/ordem-clv/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "50 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.30,
                "regra_versao": "teste-ordem-clv-v1",
                "status": "rejeitado",
            }])[0]
            oferta = {
                "odd": 1.30, "odd_oposta": 2.50, "linha": 0.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0,
                "origem_mercado": origem_mercado_teste(),
                "identidade_evento": identidade_evento_teste(),
            }
            estado = {"placar": "0-0", "minuto": 50, "status": "50 '"}
            banco.registrar_observacao_acompanhamento_odd(
                sinal, {
                    **oferta,
                    "coletado_em": "2026-09-10T10:02:00",
                    "cache": False,
                }, estado,
                consultado_em="2026-09-10T10:02:00",
            )
            regressiva = banco.registrar_observacao_acompanhamento_odd(
                sinal, {
                    **oferta,
                    "coletado_em": "2026-09-10T10:01:00",
                    "cache": False,
                }, estado,
                consultado_em="2026-09-10T10:01:00",
            )
            ainda_regressiva = banco.registrar_observacao_acompanhamento_odd(
                sinal, {
                    **oferta,
                    "coletado_em": "2026-09-10T10:01:30",
                    "cache": False,
                }, estado,
                consultado_em="2026-09-10T10:01:30",
            )

            auditoria = auditar_cadeia_custodia_clv(banco.conexao)

            self.assertFalse(regressiva["ordem_temporal_valida"])
            self.assertFalse(ainda_regressiva["ordem_temporal_valida"])
            self.assertFalse(auditoria["saudavel"])
            self.assertEqual([], auditoria["gatilhos_ausentes"])
            self.assertEqual(
                2,
                auditoria["integridade_evidencias"]["problemas"][
                    "regressao_temporal"
                ],
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_custodia_detecta_relogio_falso_com_hash_valido(self):
        caminho = Path.cwd() / ".teste_relogio_fonte_clv.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-10T10:00:00",
                "url": "https://packball.com/match/relogio-clv/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "50 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.30,
                "regra_versao": "teste-relogio-clv-v1",
                "status": "rejeitado",
            }])[0]
            partida_id = banco.conexao.execute(
                "SELECT partida_id FROM sinais WHERE id=?", (sinal,)
            ).fetchone()[0]
            payload = json.dumps({
                "sinal_origem_id": sinal,
                "mercado": "gol_ft", "linha": 0.5,
                "odd": 1.30, "odd_oposta": 2.50,
                "fonte": "betsapi", "bookmaker": "bet365",
                "fonte_coletado_em": "2026-09-10T10:05:00",
                "idade_segundos": 0.0, "cache": False,
                "placar": "0-0", "minuto": 50, "status": "50 '",
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        partida_id, fonte, consultado_em, estado, mercado,
                        oferta_json, metodo_coleta, evidencia_sha256,
                        evidencia_referencia
                    ) VALUES (?, 'betsapi', '2026-09-10T10:00:00',
                              'oferta_monitorada', 'gol_ft', ?,
                              'api_rapida_sem_packball', ?, ?)
                    """,
                    (
                        partida_id, payload,
                        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                        f"acompanhamento_odd:{sinal}",
                    ),
                )
            auditoria = auditar_cadeia_custodia_clv(banco.conexao)

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual([], auditoria["gatilhos_ausentes"])
            self.assertEqual(
                1,
                auditoria["integridade_evidencias"]["problemas"][
                    "fonte_coletado_em_futuro"
                ],
            )
            self.assertEqual(
                0,
                auditoria["integridade_evidencias"]["problemas"][
                    "hash_divergente"
                ],
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_custodia_bloqueia_v2_sem_contrato_completo(self):
        caminho = Path.cwd() / ".teste_contrato_v2_clv.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-10T10:00:00",
                "url": "https://packball.com/match/contrato-v2/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "50 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.30,
                "regra_versao": "teste-contrato-v2-clv-v1",
                "status": "rejeitado",
            }])[0]
            partida_id = banco.conexao.execute(
                "SELECT partida_id FROM sinais WHERE id=?", (sinal,)
            ).fetchone()[0]
            payload = json.dumps({
                "schema": "oferta-monitorada-odd-v2",
                "sinal_origem_id": sinal,
                "mercado": "gol_ft", "linha": 0.5,
                "odd": 1.40,
                "fonte": "betsapi", "bookmaker": "bet365",
                "fonte_coletado_em": "2026-09-10T10:01:00",
                "idade_segundos": 0.0, "cache": False,
                "placar": "0-0", "minuto": 50, "status": "50 '",
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        partida_id, fonte, consultado_em, estado, mercado,
                        oferta_json, metodo_coleta, evidencia_sha256,
                        evidencia_referencia
                    ) VALUES (?, 'betsapi', '2026-09-10T10:01:00',
                              'oferta_monitorada', 'gol_ft', ?,
                              'api_rapida_sem_packball', ?, ?)
                    """,
                    (
                        partida_id, payload,
                        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                        f"acompanhamento_odd:{sinal}",
                    ),
                )

            auditoria = auditar_cadeia_custodia_clv(banco.conexao)

            self.assertFalse(auditoria["saudavel"])
            integridade = auditoria["integridade_evidencias"]
            self.assertEqual(integridade["ofertas_contrato_v2"], 1)
            self.assertEqual(integridade["ofertas_legadas_sem_schema"], 0)
            self.assertEqual(
                integridade["problemas"][
                    "contrato_mercado_v2_incompleto"
                ],
                1,
            )
            self.assertEqual(integridade["problemas"]["hash_divergente"], 0)
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_custodia_bloqueia_v3_com_evento_divergente(self):
        caminho = Path.cwd() / ".teste_identidade_v3_clv.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-10T10:00:00",
                "url": "https://packball.com/match/identidade-v3/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "50 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.30,
                "regra_versao": "teste-identidade-v3-clv-v1",
                "status": "rejeitado",
            }])[0]
            partida_id = banco.conexao.execute(
                "SELECT partida_id FROM sinais WHERE id=?", (sinal,)
            ).fetchone()[0]
            payload = json.dumps({
                "schema": "oferta-monitorada-odd-v3",
                "sinal_origem_id": sinal,
                "mercado": "gol_ft", "linha": 0.5,
                "odd": 1.40, "odd_oposta": 2.80,
                "odd_par_sincronizado": True,
                "fonte": "betsapi", "bookmaker": "bet365",
                "fonte_coletado_em": "2026-09-10T10:01:00",
                "idade_segundos": 0.0, "cache": False,
                "identidade_evento": identidade_evento_teste("1-0"),
                "placar": "0-0", "minuto": 50, "status": "50 '",
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            payload_equipes_obj = json.loads(payload)
            payload_equipes_obj["fonte_coletado_em"] = (
                "2026-09-10T10:02:00"
            )
            payload_equipes_obj["identidade_evento"] = {
                **identidade_evento_teste("0-0"),
                "mandante_normalizado": "Equipe Estranha",
                "visitante_normalizado": "Outro Clube",
            }
            payload_equipes = json.dumps(
                payload_equipes_obj,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        partida_id, fonte, consultado_em, estado, mercado,
                        oferta_json, metodo_coleta, evidencia_sha256,
                        evidencia_referencia
                    ) VALUES (?, 'betsapi', '2026-09-10T10:01:00',
                              'oferta_monitorada', 'gol_ft', ?,
                              'api_rapida_sem_packball', ?, ?)
                    """,
                    (
                        partida_id, payload,
                        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                        f"acompanhamento_odd:{sinal}",
                    ),
                )
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        partida_id, fonte, consultado_em, estado, mercado,
                        oferta_json, metodo_coleta, evidencia_sha256,
                        evidencia_referencia
                    ) VALUES (?, 'betsapi', '2026-09-10T10:02:00',
                              'oferta_monitorada', 'gol_ft', ?,
                              'api_rapida_sem_packball', ?, ?)
                    """,
                    (
                        partida_id, payload_equipes,
                        hashlib.sha256(
                            payload_equipes.encode("utf-8")
                        ).hexdigest(),
                        f"acompanhamento_odd:{sinal}",
                    ),
                )

            auditoria = auditar_cadeia_custodia_clv(banco.conexao)

            self.assertFalse(auditoria["saudavel"])
            integridade = auditoria["integridade_evidencias"]
            self.assertEqual(integridade["ofertas_contrato_v3"], 2)
            self.assertEqual(
                integridade["problemas"]["identidade_evento_v3_invalida"],
                1,
            )
            self.assertEqual(
                integridade["problemas"][
                    "identidade_evento_v3_equipes_divergentes"
                ],
                1,
            )
            self.assertEqual(
                integridade["problemas"]["contrato_mercado_v3_incompleto"],
                0,
            )
            self.assertEqual(integridade["problemas"]["hash_divergente"], 0)
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_custodia_bloqueia_v4_sem_origem_do_grupo(self):
        caminho = Path.cwd() / ".teste_origem_mercado_v4_clv.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-10T10:00:00",
                "url": "https://packball.com/match/origem-v4/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "50 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.30,
                "regra_versao": "teste-origem-v4-clv-v1",
                "status": "rejeitado",
            }])[0]
            partida_id = banco.conexao.execute(
                "SELECT partida_id FROM sinais WHERE id=?", (sinal,)
            ).fetchone()[0]
            payload = json.dumps({
                "schema": "oferta-monitorada-odd-v4",
                "sinal_origem_id": sinal,
                "mercado": "gol_ft", "linha": 0.5,
                "odd": 1.40, "odd_oposta": 2.80,
                "odd_par_sincronizado": True,
                "fonte": "betsapi", "bookmaker": "bet365",
                "fonte_coletado_em": "2026-09-10T10:01:00",
                "idade_segundos": 0.0, "cache": False,
                "identidade_evento": identidade_evento_teste(),
                "placar": "0-0", "minuto": 50, "status": "50 '",
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        partida_id, fonte, consultado_em, estado,
                        evento_externo_id, mercado, oferta_json,
                        metodo_coleta, evidencia_sha256,
                        evidencia_referencia
                    ) VALUES (?, 'betsapi', '2026-09-10T10:01:00',
                              'oferta_monitorada', 'evento-123',
                              'gol_ft', ?, 'api_rapida_sem_packball',
                              ?, ?)
                    """,
                    (
                        partida_id,
                        payload,
                        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                        f"acompanhamento_odd:{sinal}",
                    ),
                )

            auditoria = auditar_cadeia_custodia_clv(banco.conexao)
            integridade = auditoria["integridade_evidencias"]

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual(integridade["ofertas_contrato_v4"], 1)
            self.assertEqual(
                integridade["problemas"]["origem_mercado_v4_invalida"],
                1,
            )
            self.assertEqual(integridade["problemas"]["hash_divergente"], 0)
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_recalcula_anomalia_de_curva_persistida(self):
        caminho = Path.cwd() / ".teste_anomalia_curva_clv.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-10T10:00:00",
                "url": "https://packball.com/match/curva-clv/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "20 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 1.5, "odd": 1.30,
                "regra_versao": "teste-anomalia-curva-clv-v1",
                "status": "rejeitado",
            }])[0]
            instante = "2026-09-10T10:01:00"
            oferta = {
                "odd": 1.80, "odd_oposta": 2.00, "linha": 1.5,
                "fonte": "betsapi", "bookmaker": "bet365",
                "idade_segundos": 0.0, "coletado_em": instante,
                "cache": False,
                "origem_mercado": origem_mercado_teste(1.5),
                "identidade_evento": identidade_evento_teste(),
            }
            odds = {"ao_vivo": [{
                "categoria": "gols", "escopo": "total",
                "tipo_mercado": "total", "formato": "duas_opcoes",
                "ofertas": [
                    {
                        "linha": 0.5, "over": 2.00, "under": 1.70,
                        "origem_mercado": origem_mercado_teste(0.5),
                    },
                    {
                        "linha": 1.5, "over": 1.80, "under": 2.00,
                        "origem_mercado": origem_mercado_teste(1.5),
                    },
                ],
                "ofertas_ht": [],
            }]}
            persistida = banco.registrar_observacao_acompanhamento_odd(
                sinal, oferta,
                {"placar": "0-0", "minuto": 20, "status": "20 '"},
                consultado_em=instante,
                odds=odds,
            )

            auditoria = auditar_cadeia_custodia_clv(banco.conexao)
            integridade = auditoria["integridade_evidencias"]
            self.assertTrue(persistida["persistido"])
            self.assertFalse(persistida["autorizada"])
            self.assertTrue(auditoria["saudavel"])
            self.assertEqual(1, integridade["anomalias_curva_odds"])
            self.assertEqual(
                0, integridade["problemas"]["anomalia_curva_odd_invalida"]
            )

            linha = banco.conexao.execute(
                "SELECT * FROM observacoes_fontes_odds WHERE id=?",
                (persistida["observacao_id"],),
            ).fetchone()
            payload = json.loads(linha["oferta_json"])
            payload["coerencia_curva_odds"]["lado_incoerente"] = "over"
            adulterado = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        partida_id, fonte, consultado_em, estado,
                        evento_externo_id, mandante_observado,
                        visitante_observado, periodo, mercado, motivo,
                        oferta_json, metodo_coleta, evidencia_sha256,
                        evidencia_referencia
                    ) VALUES (?, ?, ?, 'anomalia_curva_odd', ?, ?, ?, ?, ?,
                              ?, ?, 'api_rapida_sem_packball', ?, ?)
                    """,
                    (
                        linha["partida_id"], linha["fonte"],
                        "2026-09-10T10:01:01", linha["evento_externo_id"],
                        linha["mandante_observado"],
                        linha["visitante_observado"], linha["periodo"],
                        linha["mercado"], linha["motivo"], adulterado,
                        hashlib.sha256(adulterado.encode("utf-8")).hexdigest(),
                        linha["evidencia_referencia"],
                    ),
                )

            corrompida = auditar_cadeia_custodia_clv(banco.conexao)
            self.assertFalse(corrompida["saudavel"])
            self.assertEqual(
                1,
                corrompida["integridade_evidencias"]["problemas"][
                    "anomalia_curva_odd_invalida"
                ],
            )
            self.assertEqual(
                0,
                corrompida["integridade_evidencias"]["problemas"][
                    "hash_divergente"
                ],
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_auditoria_custodia_detecta_troca_de_evento_na_trajetoria(self):
        caminho = Path.cwd() / ".teste_continuidade_evento_v3_clv.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-09-10T10:00:00",
                "url": "https://packball.com/match/continuidade-v3/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "50 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.30,
                "regra_versao": "teste-continuidade-v3-clv-v1",
                "status": "rejeitado",
            }])[0]
            primeira = banco.registrar_observacao_acompanhamento_odd(
                sinal,
                {
                    "odd": 1.40, "odd_oposta": 2.80, "linha": 0.5,
                    "fonte": "betsapi", "bookmaker": "bet365",
                    "fonte_coletado_em": "2026-09-10T10:01:00",
                    "coletado_em": "2026-09-10T10:01:00",
                    "idade_segundos": 0.0, "cache": False,
                    "origem_mercado": origem_mercado_teste(),
                    "identidade_evento": identidade_evento_teste(),
                },
                {"placar": "0-0", "minuto": 50, "status": "50 '"},
                consultado_em="2026-09-10T10:01:00",
            )
            linha = banco.conexao.execute(
                """
                SELECT partida_id, mercado, evidencia_referencia, oferta_json
                FROM observacoes_fontes_odds WHERE id=?
                """,
                (primeira["observacao_id"],),
            ).fetchone()
            payload = json.loads(linha["oferta_json"])
            payload["identidade_evento"]["evento_externo_id"] = "evento-999"
            payload["fonte_coletado_em"] = "2026-09-10T10:02:00"
            oferta_json = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            evidencia = hashlib.sha256(
                oferta_json.encode("utf-8")
            ).hexdigest()
            with banco.conexao:
                banco.conexao.execute(
                    "DROP TRIGGER trg_observacoes_odds_identidade_estavel"
                )
                banco.conexao.execute(
                    "DROP TRIGGER "
                    "trg_observacoes_odds_identidade_estavel_v2"
                )
                banco.conexao.execute(
                    """
                    INSERT INTO observacoes_fontes_odds (
                        partida_id, fonte, consultado_em, estado,
                        evento_externo_id, mercado, oferta_json,
                        metodo_coleta, evidencia_sha256,
                        evidencia_referencia
                    ) VALUES (?, 'betsapi', '2026-09-10T10:02:00',
                              'oferta_monitorada', 'evento-999', ?, ?,
                              'api_rapida_sem_packball', ?, ?)
                    """,
                    (
                        linha["partida_id"], linha["mercado"], oferta_json,
                        evidencia, linha["evidencia_referencia"],
                    ),
                )
            banco.fechar()
            banco = BancoMonitor(caminho)

            auditoria = auditar_cadeia_custodia_clv(banco.conexao)

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual([], auditoria["gatilhos_ausentes"])
            integridade = auditoria["integridade_evidencias"]
            self.assertEqual(
                1,
                integridade["problemas"][
                    "continuidade_identidade_evento_v3_quebrada"
                ],
            )
            self.assertEqual(
                0,
                integridade["problemas"][
                    "evento_externo_id_coluna_divergente"
                ],
            )
            self.assertEqual(integridade["problemas"]["hash_divergente"], 0)
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    def test_historico_amplo_nao_pode_substituir_coorte_fixa(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.8, 2.0)
        )
        self._snapshot(
            2, 130, estrutura=self._estrutura_binaria(1.6, 2.2)
        )
        self._sinal()

        resumo = avaliar(self.conexao)

        self.assertFalse(resumo["total"]["pode_informar_edge"])
        self.assertEqual(
            "historico_e_coorte_futura_misturados",
            resumo["total"]["motivo_nao_inferencial"],
        )
        self.assertEqual(0, resumo["coorte_clv_prospectiva_fixa"][
            "unidades_coorte"
        ])

    def test_ic95_pequeno_usa_student_em_vez_de_normal_otimista(self):
        base = {
            "estado": "comparavel",
            "origem_valor_horizonte": "cotacao_sem_vig",
            "segundos_apos_entrega": 130,
        }
        metricas = _metricas([
            {**base, "clv_probabilidade_pontos": 0.0},
            {**base, "clv_probabilidade_pontos": 1.0},
        ])

        self.assertLess(metricas["intervalo_media_95"][0], -5.0)
        self.assertGreater(metricas["intervalo_media_95"][1], 6.0)

    def test_varios_alertas_da_mesma_partida_nao_estreitam_ic95(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.8, 2.0)
        )
        self._snapshot(
            2, 130, estrutura=self._estrutura_binaria(1.6, 2.2)
        )
        self._snapshot(
            3, 150, estrutura=self._estrutura_binaria(1.6, 2.2)
        )
        self._sinal()
        self.conexao.execute(
            "INSERT INTO sinais VALUES (?,?,?,?,?,?,?,?,?)",
            (
                21, 10, 1, (self.inicio + timedelta(seconds=10)).isoformat(),
                "gol_ft", "1.5", 1.8, "regra-v1",
                json.dumps({
                    "fonte_odds": "packball", "bookmaker_odds": None,
                }),
            ),
        )
        self.conexao.execute(
            "INSERT INTO entregas_alertas"
            "(sinal_id,canal,tentado_em,entregue_em,status) "
            "VALUES (?,?,?,?,?)",
            (
                21, "grupo:teste",
                (self.inicio + timedelta(seconds=10)).isoformat(),
                (self.inicio + timedelta(seconds=15)).isoformat(),
                "entregue",
            ),
        )

        resumo = avaliar(self.conexao)

        self.assertEqual(2, resumo["entregas_brutas_consultadas"])
        self.assertEqual(1, resumo["sinais_independentes_consultados"])
        self.assertEqual(1, resumo["comparaveis"])
        self.assertEqual(
            2, resumo["diagnostico_todas_entregas"]["comparaveis"]
        )
        self.assertEqual(
            1, resumo["por_mercado"]["gol_ft"]["comparaveis"]
        )

    def test_agregado_principal_nao_soma_mercados_do_mesmo_jogo(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_binaria(1.8, 2.0)
        )
        self._snapshot(
            2, 150, estrutura=self._estrutura_binaria(1.6, 2.2)
        )
        for snapshot_id, estrutura in (
            (1, self._estrutura_tres_vias(1.8, 3.5, 5.0)),
            (2, self._estrutura_tres_vias(1.6, 4.0, 6.0)),
        ):
            self.conexao.execute(
                "INSERT INTO odds(snapshot_id,estrutura_json) VALUES (?,?)",
                (snapshot_id, json.dumps(estrutura)),
            )
        self._sinal()
        self.conexao.execute(
            "INSERT INTO sinais VALUES (?,?,?,?,?,?,?,?,?)",
            (
                21, 10, 1, (self.inicio + timedelta(seconds=10)).isoformat(),
                "proximo_gol", "casa", 1.8, "regra-v1",
                json.dumps({
                    "fonte_odds": "packball", "bookmaker_odds": None,
                }),
            ),
        )
        self.conexao.execute(
            "INSERT INTO entregas_alertas"
            "(sinal_id,canal,tentado_em,entregue_em,status) "
            "VALUES (?,?,?,?,?)",
            (
                21, "grupo:teste",
                (self.inicio + timedelta(seconds=10)).isoformat(),
                (self.inicio + timedelta(seconds=15)).isoformat(),
                "entregue",
            ),
        )

        resumo = avaliar(self.conexao)

        self.assertEqual(2, resumo["sinais_partida_mercado_consultados"])
        self.assertEqual(1, resumo["sinais_independentes_consultados"])
        self.assertEqual(1, resumo["total"]["amostra"])
        self.assertEqual(1, resumo["por_mercado"]["gol_ft"]["comparaveis"])
        self.assertEqual(
            1, resumo["por_mercado"]["proximo_gol"]["comparaveis"]
        )
        correlacionado = resumo["diagnostico_partida_e_mercado"]
        self.assertEqual(2, correlacionado["comparaveis"])
        self.assertEqual(
            "diagnostico_correlacionado_intrajogo",
            correlacionado["estado_evidencia"],
        )
        self.assertTrue(correlacionado["vies_correlacao_intrajogo"])
        self.assertFalse(correlacionado["pode_informar_edge"])

    def test_escolhe_unidade_antes_de_saber_se_e_comparavel(self):
        self._snapshot(
            1, 0, estrutura=self._estrutura_tres_vias(1.8, 3.5, 5.0)
        )
        self._snapshot(
            2, 150, estrutura=self._estrutura_tres_vias(1.6, 4.0, 6.0)
        )
        self._sinal()
        self.conexao.execute(
            "INSERT INTO sinais VALUES (?,?,?,?,?,?,?,?,?)",
            (
                21, 10, 1, (self.inicio + timedelta(seconds=10)).isoformat(),
                "proximo_gol", "casa", 1.8, "regra-v1",
                json.dumps({
                    "fonte_odds": "packball", "bookmaker_odds": None,
                }),
            ),
        )
        self.conexao.execute(
            "INSERT INTO entregas_alertas"
            "(sinal_id,canal,tentado_em,entregue_em,status) "
            "VALUES (?,?,?,?,?)",
            (
                21, "grupo:teste",
                (self.inicio + timedelta(seconds=10)).isoformat(),
                (self.inicio + timedelta(seconds=15)).isoformat(),
                "entregue",
            ),
        )

        resumo = avaliar(self.conexao)

        self.assertTrue(resumo["selecao_unidade_antes_da_comparabilidade"])
        self.assertEqual(1, resumo["sinais_independentes_consultados"])
        self.assertEqual(0, resumo["comparaveis"])
        self.assertEqual(0, resumo["total"]["amostra"])
        self.assertEqual(
            1, resumo["por_mercado"]["proximo_gol"]["comparaveis"]
        )

    def test_liquidacao_rapida_nao_finge_movimento_de_preco(self):
        self._snapshot(
            1, 0,
            estrutura=self._estrutura_binaria(1.8, 2.0, linha=0.5),
        )
        self._snapshot(2, 60, placar="1-0")
        self._sinal(linha="0.5")

        resumo = avaliar(self.conexao)

        self.assertEqual(1, resumo["total"]["amostra"])
        self.assertEqual(
            0,
            resumo["movimento_preco_contratos_sobreviventes"]["amostra"],
        )
        self.assertEqual(
            {"liquidado_green": 1},
            resumo["total"]["origens_valor_horizonte"],
        )


if __name__ == "__main__":
    unittest.main()
