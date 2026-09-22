import copy
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import os

from filtro_ht_chutes_recentes import METODO, ROLLBACK, avaliar_chutes_ht


class FiltroHTChutesTest(unittest.TestCase):
    def setUp(self):
        self.agora = datetime(2026, 9, 2, 17, 0)
        self.janela = {"disponivel": True, "duracao_real_minutos": 5,
                       "chutes": [0, 0], "chutes_total": 0, "resets_detectados": []}
        self.sinal = {"mercado": "gol_ht", "features": {
            "exploracao_sombra": {"versao": METODO}, "periodo": "primeiro_tempo",
            "estado_observado_em": self.agora.isoformat(), "janelas": {"5": self.janela}}}
        self.snapshot = {"coletado_em": self.agora.isoformat(), "contexto_api_json": {}}

    def avaliar(self):
        return avaliar_chutes_ht(self.sinal, self.snapshot, self.agora, {ROLLBACK: "1"})

    def api(self, par=(0, 0)):
        self.snapshot["contexto_api_json"] = {"fixture_id": 123, "evolucao_temporal_api_live": {
            "fixture_id": 123, "fonte": "api_football", "periodo": "primeiro_tempo",
            "coletado_em": self.agora.isoformat(),
            "5": {"chutes": list(par), "duracao_real_minutos": 5, "resets_detectados": []}}}
        return self.snapshot["contexto_api_json"]["evolucao_temporal_api_live"]

    def test_zero_bloqueia_sem_mudar_evidencia(self):
        antes = copy.deepcopy((self.sinal, self.snapshot))
        self.assertFalse(self.avaliar()["aprovada"])
        self.assertEqual(antes, (self.sinal, self.snapshot))

    def test_v5_mantem_filtro_de_chutes(self):
        from gol_ht_00_min20 import VERSAO
        self.sinal["features"]["exploracao_sombra"]["versao"] = VERSAO
        self.assertTrue(self.avaliar()["aplicavel"])
        self.assertFalse(self.avaliar()["aprovada"])

    def test_um_chute_qualquer_lado_nao_bloqueia(self):
        for par in ([0, 1], [1, 0], [2, 3]):
            self.janela.update(chutes=par, chutes_total=sum(par))
            self.assertTrue(self.avaliar()["aprovada"])

    def test_ausencia_nao_e_zero(self):
        self.sinal["features"]["janelas"] = {"5": {"disponivel": False}}
        self.assertTrue(self.avaliar()["aprovada"])
        self.assertIsNone(self.avaliar()["fonte"])

    def test_invalido_nao_e_zero(self):
        for par in ([None, 0], [False, 0], [-1, 1], [float("nan"), 0], [0], [0.5, 0], [float("inf"), 0]):
            with self.subTest(par=par):
                self.janela["chutes"] = par
                self.assertIsNone(self.avaliar()["fonte"])

    def test_total_incoerente_nao_e_zero(self):
        self.janela["chutes"] = [1, 0]
        self.assertIsNone(self.avaliar()["fonte"])

    def test_janela_curta_longa_ausente_invalida(self):
        for duracao in (None, 0, 2, 4.99, 8.01, 10, float("nan")):
            self.janela["duracao_real_minutos"] = duracao
            self.assertIsNone(self.avaliar()["fonte"])

    def test_tolerancia_janela_existente(self):
        for duracao in (5, 7.62, 8):
            self.janela["duracao_real_minutos"] = duracao
            self.assertFalse(self.avaliar()["aprovada"])

    def test_reset_chutes_nao_vira_zero(self):
        self.janela["resets_detectados"] = ["chutes"]
        self.assertIsNone(self.avaliar()["fonte"])

    def test_reset_escanteio_nao_altera_chutes(self):
        self.janela["resets_detectados"] = ["escanteios"]
        self.assertFalse(self.avaliar()["aprovada"])

    def test_outros_metodos_intactos(self):
        for mercado, metodo in (("gol_ft", METODO), ("gol_ht", "antecipado"), ("proximo_gol", METODO)):
            self.sinal["mercado"] = mercado
            self.sinal["features"]["exploracao_sombra"]["versao"] = metodo
            self.assertFalse(self.avaliar()["aplicavel"])

    def test_rollback(self):
        self.assertTrue(avaliar_chutes_ht(self.sinal, self.snapshot, self.agora, {ROLLBACK: "0"})["aprovada"])

    def test_tempo_ausente_antigo_futuro_nao_e_zero_atual(self):
        for instante in (None, "ruim", (self.agora - timedelta(seconds=121)).isoformat(), (self.agora + timedelta(seconds=1)).isoformat()):
            self.snapshot["coletado_em"] = instante
            self.assertIsNone(self.avaliar()["fonte"])

    def test_odds_rapidas_nao_renovam_janela_tecnica(self):
        self.sinal["features"]["acompanhamento_odd_rapido"] = {"idade_tecnica_segundos": 500}
        self.assertIsNone(self.avaliar()["fonte"])

    def test_api_fallback_somente_quando_packball_indisponivel(self):
        self.janela["disponivel"] = False
        self.api()
        self.assertFalse(self.avaliar()["aprovada"])
        self.assertEqual("api_football", self.avaliar()["fonte"])

    def test_zero_packball_nao_e_sobrescrito_por_api(self):
        self.api((3, 2))
        self.assertFalse(self.avaliar()["aprovada"])
        self.assertEqual("packball", self.avaliar()["fonte"])

    def test_packball_positivo_nao_e_vetado_por_api_zero(self):
        self.api()
        self.janela.update(chutes=[0, 1], chutes_total=1)
        self.assertTrue(self.avaliar()["aprovada"])

    def test_api_fresh_fixture_periodo_fonte_obrigatorios(self):
        self.janela["disponivel"] = False
        for chave, valor in (("fixture_id", 999), ("periodo", "segundo_tempo"), ("fonte", "outra"), ("coletado_em", (self.agora - timedelta(minutes=3)).isoformat())):
            api = self.api()
            api[chave] = valor
            self.assertIsNone(self.avaliar()["fonte"])

    def test_api_divergente_nao_vira_veto(self):
        self.janela["disponivel"] = False
        self.api()
        self.snapshot["contexto_api_json"]["comparacao_fontes_ao_vivo"] = {"metricas": {"chutes": {"concorda": False}}}
        self.assertIsNone(self.avaliar()["fonte"])

    def test_origem_lista_registrada(self):
        self.sinal["features"]["fallback_temporal_lista"] = {"campos_complementados": ["5.chutes"]}
        self.assertEqual("packball_lista_ao_vivo", self.avaliar()["fonte"])

    def test_json_persistido_suportado(self):
        self.sinal["features_json"] = json.dumps(self.sinal.pop("features"))
        self.snapshot["contexto_api_json"] = json.dumps(self.snapshot["contexto_api_json"])
        self.assertFalse(self.avaliar()["aprovada"])

    def _testar_gateway(self, zero=True, rollback=False):
        from test_telegram_alertas import TelegramAlertasTest
        from test_validade_historico_gols import contexto_com_datas
        from telegram_alertas import AlertasTelegram
        from gol_ht_00_min20 import LINHAGEM, VERSAO
        fixture = TelegramAlertasTest()
        fixture.setUp()
        try:
            agora = datetime.now().replace(microsecond=0)
            candidato = fixture.candidato()
            features = copy.deepcopy(self.sinal["features"])
            features.update(minuto=25, decisao_em=agora.isoformat(),
                            estado_observado_em=agora.isoformat(), idade_odds_segundos=0.0)
            features["gol_ht_00_min20"] = {"linhagem_sha256": LINHAGEM}
            features["exploracao_sombra"]["versao"] = VERSAO
            if not zero:
                features["janelas"]["5"].update(chutes=[1, 0], chutes_total=1)
            candidato.update(mercado="gol_ht", linha=0.5, features=features, status="simulacao")
            jogo = {**fixture.jogo, "url": "https://packball.com/match/2/live", "status": "25 '",
                    "qualidade_dados": 90,
                    "contexto_api": contexto_com_datas(fixture.banco.conexao, agora=agora)}
            snapshot = fixture.banco.salvar_registro(jogo)
            sid = fixture.banco.salvar_candidatos(snapshot, [candidato])[0]
            original = fixture.banco.conexao.execute("SELECT features_json FROM sinais WHERE id=?", (sid,)).fetchone()[0]
            transporte = Mock()
            alertas = AlertasTelegram(fixture.banco, transporte=transporte)
            with patch.dict(os.environ, {ROLLBACK: "0" if rollback else "1"}), patch("telegram_alertas.GOL_HT_00_MIN20_GRUPO_ATIVO", True):
                estado = alertas._revalidar_pre_envio(sid, candidato, jogo, agora=agora)
            auditoria = fixture.banco.conexao.execute("SELECT erro FROM entregas_alertas WHERE sinal_id=? AND canal='gateway:ht_chutes_recentes'", (sid,)).fetchone()
            self.assertIsNotNone(auditoria)
            self.assertEqual(not zero or rollback, json.loads(auditoria[0])["aprovada"])
            self.assertEqual(original, fixture.banco.conexao.execute("SELECT features_json FROM sinais WHERE id=?", (sid,)).fetchone()[0])
            self.assertEqual(0, fixture.banco.conexao.execute("SELECT count(*) FROM entregas_alertas WHERE status='entregue'").fetchone()[0])
            transporte.assert_not_called()
            return estado
        finally:
            fixture.tearDown()

    def test_gateway_real_veta_zero_e_persiste_auditoria(self):
        self.assertEqual("revalidacao_pre_envio_ht00_zero_chutes_recentes_confirmado", self._testar_gateway())

    def test_gateway_real_nao_veta_chute(self):
        self.assertIsNone(self._testar_gateway(zero=False))

    def test_gateway_real_rollback(self):
        self.assertIsNone(self._testar_gateway(rollback=True))


if __name__ == "__main__":
    unittest.main()
