import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from banco import BancoMonitor
from calibracao import CalibradorBacktest
from linhagem_regras import registrar_ou_validar_linhagem_regra
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS
from telegram_alertas import AlertasTelegram, PROBABILIDADE_MINIMA


class AtivacaoOficialTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_ativacao_oficial.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        self.banco = BancoMonitor(self.caminho)
        self.linhagem = registrar_ou_validar_linhagem_regra(
            self.banco.conexao,
            Path.cwd(),
            VERSAO_REGRAS,
            VERSAO_FEATURES,
        )

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            Path(str(self.caminho) + sufixo).unlink(missing_ok=True)

    @staticmethod
    def _anexar_cotacao_executavel(candidato, instante, identificador):
        origem = {
            "schema": "origem-mercado-odd-v1",
            "fonte": "betsapi",
            "identificador": str(identificador),
            "nome": "Match Goals",
            "linha": candidato["linha"],
            "lados": ["over", "under"],
            "bookmaker": "bet365",
        }
        candidato.update({
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
        })
        candidato.setdefault("features", {}).update({
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
            "cotacao_entrada_clv_estado": "congelada_v1",
            "cotacao_entrada_clv": {
                "schema": "cotacao-entrada-clv-v2",
                "mercado": candidato["mercado"],
                "fonte": "betsapi",
                "bookmaker": "bet365",
                "coletado_em": instante,
                "idade_segundos": 1.0,
                "cache": False,
                "tipo": "binaria",
                "linha": candidato["linha"],
                "over": candidato["odd"],
                "under": candidato.get("odd_oposta", 2.2),
                "odd_selecionada": candidato["odd"],
                "origem_mercado": origem,
            },
        })
        return candidato

    def _popular_amostra_independente(self, quantidade=300):
        inicio = datetime(2026, 1, 1, 12, 0)
        with self.banco.conexao:
            for indice in range(quantidade):
                instante = (inicio + timedelta(hours=indice * 2)).isoformat()
                partida = self.banco.conexao.execute(
                    """
                    INSERT INTO partidas (
                        packball_url, mandante, visitante, liga,
                        liga_normalizada,
                        primeira_coleta, ultima_coleta
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"https://packball.com/match/cal-{indice}/live",
                        f"Casa {indice}", f"Fora {indice}",
                        f"Liga {indice % 5}", f"liga-{indice % 5}",
                        instante, instante,
                    ),
                ).lastrowid
                snapshot = self.banco.conexao.execute(
                    """
                    INSERT INTO snapshots (
                        partida_id, coletado_em, placar, status
                    ) VALUES (?, ?, '0-0', '60')
                    """,
                    (partida, instante),
                ).lastrowid
                if indice < 35:
                    # Faixa forte: 35/35 no desenvolvimento.
                    green = True
                    pontuacao = 95
                elif indice < 68:
                    # Faixa de controle: 20/33 no desenvolvimento.
                    green = indice - 35 < 20
                    pontuacao = 89 if green else 80
                elif indice < 70:
                    # Duas observações adversas fora das faixas calibráveis.
                    green = False
                    pontuacao = 70
                elif indice < 85:
                    # Faixa forte: 15/15 na validação posterior.
                    green = True
                    pontuacao = 95
                elif indice < 100:
                    # Controle: 10/15, com ROI ainda positivo.
                    green = indice - 85 < 10
                    pontuacao = 89 if green else 80
                else:
                    green = indice % 10 != 0
                    pontuacao = 89 if green else 80
                prova = self._anexar_cotacao_executavel(
                    {
                        "mercado": "gol_ft",
                        "linha": 0.5,
                        "odd": 1.8,
                        "odd_oposta": 2.2,
                    },
                    instante,
                    f"amostra-{indice}",
                )
                sinal = self.banco.conexao.execute(
                    """
                    INSERT INTO sinais (
                        partida_id, snapshot_id, criado_em, mercado,
                        linha, odd, pontuacao_tecnica,
                        regra_versao, regra_fingerprint, status,
                        features_json
                    ) VALUES (
                        ?, ?, ?, 'gol_ft', 0.5, 1.8, ?, ?, ?, 'aprovado', ?
                    )
                    """,
                    (
                        partida, snapshot, instante,
                        pontuacao, VERSAO_REGRAS,
                        self.linhagem["fingerprint_atual"],
                        json.dumps(prova["features"]),
                    ),
                ).lastrowid
                self.banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, snapshot_id_liquidacao,
                        fonte_resultado
                    ) VALUES (?, ?, ?, ?, ?, 'packball')
                    """,
                    (
                        sinal, instante, "green" if green else "red",
                        0.8 if green else -1.0, snapshot,
                    ),
                )

    def test_amostra_validada_libera_candidato_seguinte_no_canal_oficial(self):
        self._popular_amostra_independente()
        calibrador = CalibradorBacktest(self.banco)

        modelo = calibrador.recalibrar("gol_ft", VERSAO_REGRAS)

        self.assertTrue(modelo["ativa"])
        self.assertEqual(modelo["amostra"], 100)
        self.assertEqual(modelo["amostra_total_disponivel"], 300)
        self.assertEqual(modelo["janela_modelo_fixa"], 100)
        self.assertGreaterEqual(
            modelo["discriminacao_pontuacao"]["limite_inferior_auc_95"],
            0.50,
        )
        candidato = {
            "mercado": "gol_ft", "linha": 0.5, "odd": 1.8,
            "odd_oposta": 2.2, "odd_par_sincronizado": True,
            "pontuacao_tecnica": 95, "regra_versao": VERSAO_REGRAS,
            "regra_fingerprint": self.linhagem["fingerprint_atual"],
            "status": "aprovado", "motivos": ["teste_ponta_a_ponta"],
            "qualidade_dados": 100,
        }
        self._anexar_cotacao_executavel(
            candidato,
            datetime.now().replace(microsecond=0).isoformat(),
            "candidato-oficial",
        )
        calibrador.aplicar(candidato)
        self.assertGreaterEqual(
            candidato["probabilidade_calibrada"], PROBABILIDADE_MINIMA
        )
        self.assertLessEqual(
            candidato["probabilidade_calibrada"],
            candidato["probabilidade_observada"],
        )

        instante = datetime.now().replace(microsecond=0).isoformat()
        candidato.setdefault("features", {}).update({
            "minuto": 60,
            "decisao_em": instante,
            "estado_observado_em": instante,
            "idade_odds_segundos": 0.0,
        })
        snapshot = self.banco.salvar_registro({
            "coletado_em": instante,
            "url": "https://packball.com/match/proximo/live",
            "mandante": "Próximo Casa", "visitante": "Próximo Fora",
            "placar": "0-0", "status": "60 '",
        })
        sinal_id = self.banco.salvar_candidatos(
            snapshot, [candidato], instante
        )[0]
        transporte = Mock(return_value={
            "ok": True,
            "result": {"message_id": 1234, "date": 1784678400},
        })
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "token-teste",
            "TELEGRAM_CHAT_ID_GOLS": "canal-oficial",
            "SINAIS_TESTE_ATIVO": "0",
        }):
            alertas = AlertasTelegram(
                self.banco,
                transporte=transporte,
                validador_operacao_oficial=lambda: {
                    "apto": True,
                    "estado": "pronto",
                },
            )
            resultado = alertas.avaliar_e_enviar(
                sinal_id,
                candidato,
                {
                    "mandante": "Próximo Casa",
                    "visitante": "Próximo Fora",
                    "placar": "0-0", "status": "60 '",
                },
            )

        self.assertEqual(resultado, "entregue")
        transporte.assert_called_once()
        self.assertEqual(
            transporte.call_args.args[1]["chat_id"], "canal-oficial"
        )
        entrega = self.banco.conexao.execute(
            "SELECT canal, status FROM entregas_alertas WHERE sinal_id=?",
            (sinal_id,),
        ).fetchone()
        self.assertEqual(tuple(entrega), ("canal-oficial", "entregue"))


if __name__ == "__main__":
    unittest.main()
