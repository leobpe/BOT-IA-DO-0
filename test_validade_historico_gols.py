import copy
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from contexto_linhas_gols import _resumir
from gols_capacidade_contextual_v2 import _resumir_partidas
from validade_historico_gols import avaliar_historico_envio


def contexto_com_datas(conexao, base=None, agora=None, antigos=False):
    agora = agora or datetime.now()
    contexto = copy.deepcopy(base or {})
    contexto['times'] = {'mandante_id': 1, 'visitante_id': 2}
    capacidade = {}
    linhas = {}
    for lado, tid, mando in [('mandante', 1, True), ('visitante', 2, False)]:
        itens = []
        for i in range(15):
            casa = mando if i < 7 else not mando
            dias = 1100 + i if antigos and tid == 1 and i else i + 1
            itens.append({
                'fixture': {'id': tid * 100 + i, 'timestamp': (agora - timedelta(days=dias)).timestamp()},
                'teams': {'home': {'id': tid if casa else 900}, 'away': {'id': 900 if casa else tid}},
                'goals': {'home': 2, 'away': 1},
                'score': {'halftime': {'home': 1, 'away': 1}},
            })
        conexao.execute('INSERT OR REPLACE INTO cache_api_football(chave,categoria,armazenado_em,dados_json) VALUES (?,?,?,?)',
                        (f'contexto:v2:forma15:{tid}', 'contexto', agora.timestamp(), json.dumps(itens)))
        capacidade[lado] = _resumir_partidas(itens, tid, mando)
        linhas[lado] = _resumir(itens, tid, mando)
    contexto.setdefault('capacidade_times_v2', {})['recentes'] = capacidade
    contexto.setdefault('tendencia_linhas_gols_v1', {})['recentes'] = linhas
    return contexto


class ValidadeHistoricoGolsTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'VALIDADE_HISTORICO_GOLS_ATIVA': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.c = sqlite3.connect(':memory:')
        self.addCleanup(self.c.close)
        self.c.execute('CREATE TABLE cache_api_football(chave TEXT PRIMARY KEY,categoria TEXT,armazenado_em REAL,dados_json TEXT)')
        self.agora = datetime(2026, 9, 2, 10, 30)
        self.sinal = {'mercado': 'gol_ft', 'features': {'gol_capacidade_contextual_v2': {}}}
        self.ctx = contexto_com_datas(self.c, agora=self.agora)

    def avaliar(self):
        return avaliar_historico_envio(self.c, self.sinal, {'contexto_api_json': json.dumps(self.ctx)}, self.agora)

    def alterar_cache(self, alterar):
        a = json.loads(self.c.execute("SELECT dados_json FROM cache_api_football WHERE chave='contexto:v2:forma15:1'").fetchone()[0])
        alterar(a)
        self.c.execute("UPDATE cache_api_football SET dados_json=? WHERE chave='contexto:v2:forma15:1'", (json.dumps(a),))

    def test_historico_atual_aprovado_sem_mutar_contexto(self):
        anterior = copy.deepcopy(self.ctx)
        self.assertTrue(self.avaliar()['aprovada'])
        self.assertEqual(anterior, self.ctx)

    def test_reproduz_um_jogo_atual_e_quatorze_de_2023(self):
        self.ctx = contexto_com_datas(self.c, agora=self.agora, antigos=True)
        a = self.avaliar()
        self.assertFalse(a['aprovada'])
        self.assertEqual('historico_antigo', a['motivo'])
        self.assertEqual(14, a['times'][0]['jogos_antigos'])

    def test_cache_atualizado_nao_renova_data_dos_jogos(self):
        self.ctx = contexto_com_datas(self.c, agora=self.agora, antigos=True)
        self.c.execute('UPDATE cache_api_football SET armazenado_em=?', (self.agora.timestamp(),))
        self.assertEqual('historico_antigo', self.avaliar()['motivo'])

    def test_datas_ausentes_fecham_envio(self):
        self.alterar_cache(lambda a: a[0].update(fixture={}))
        self.assertEqual('historico_data_ausente', self.avaliar()['motivo'])

    def test_futuro_fechado(self):
        self.alterar_cache(lambda a: a[0]['fixture'].update(timestamp=(self.agora + timedelta(days=1)).timestamp()))
        self.assertEqual('historico_data_futura', self.avaliar()['motivo'])

    def test_cache_ausente_nao_vira_aprovacao(self):
        self.c.execute('DELETE FROM cache_api_football')
        self.assertEqual('historico_datas_indisponivel', self.avaliar()['motivo'])

    def test_cache_com_outros_resultados_exige_nova_analise(self):
        self.alterar_cache(lambda a: a[0]['goals'].update(home=9))
        self.assertEqual('historico_cache_diverge_da_analise', self.avaliar()['motivo'])

    def test_distribuicao_de_um_jogo_nao_sustenta_projecao_temporal(self):
        self.sinal['features']['gol_capacidade_contextual_v2']['modelo_historico'] = {'metodo_tempo': 'distribuicao_temporada'}
        self.ctx['estatisticas_temporada'] = {'visitante': {'jogos': 1, 'gols_pro_por_minuto': {'61-75': {'total': 1, 'percentual': 100}}}}
        self.assertEqual('distribuicao_temporal_amostra_insuficiente', self.avaliar()['motivo'])

    def test_modelo_relogio_nao_depende_de_distribuicao_temporal(self):
        self.sinal['features']['gol_capacidade_contextual_v2']['modelo_historico'] = {'metodo_tempo': 'relogio'}
        self.ctx['estatisticas_temporada'] = {'visitante': {'jogos': 1}}
        self.assertTrue(self.avaliar()['aprovada'])

    def test_mercado_nao_historico_permanece_intacto(self):
        self.sinal['mercado'] = 'escanteios_ft_asiatico'
        self.ctx = {}
        self.assertTrue(self.avaliar()['aprovada'])

    def test_dados_ausentes_em_metodo_historico_bloqueiam(self):
        self.ctx = {}
        self.assertEqual('historico_identidade_indisponivel', self.avaliar()['motivo'])

    def test_rollback_explicito(self):
        with patch.dict(os.environ, {'VALIDADE_HISTORICO_GOLS_ATIVA': '0'}):
            self.ctx = {}
            self.assertEqual('desativada', self.avaliar()['motivo'])

    def test_top_exige_datas_tambem_do_historico_mando10(self):
        self.sinal['features']['top_criterio_gols'] = {'versao': 'top'}
        a = self.avaliar()
        self.assertFalse(a['aprovada'])
        self.assertEqual('historico_datas_indisponivel', a['motivo'])
        self.assertEqual('mandante_mando10', a['times'][-1]['lado'])

    def test_pre_envio_real_nao_chama_transporte_com_historico_antigo(self):
        from test_telegram_alertas import TelegramAlertasTest
        from telegram_alertas import AlertasTelegram
        fixture = TelegramAlertasTest()
        fixture.setUp()
        try:
            contexto = contexto_com_datas(fixture.banco.conexao, antigos=True)
            snapshot = fixture.banco.salvar_registro({
                'coletado_em': (
                    datetime.now().replace(microsecond=0)
                    + timedelta(seconds=1)
                ).isoformat(),
                'url': 'https://packball.com/match/1/live',
                'mandante': 'A',
                'visitante': 'B',
                'placar': '0-0',
                'status': "60 '",
                'qualidade_dados': 90,
                'contexto_api': contexto,
            })
            with fixture.banco.conexao:
                fixture.banco.conexao.execute(
                    'UPDATE sinais SET snapshot_id=? WHERE id=?',
                    (snapshot, fixture.sinal_id),
                )
            transporte = Mock()
            alertas = AlertasTelegram(fixture.banco, transporte=transporte)
            estado = alertas._revalidar_pre_envio(fixture.sinal_id, fixture.candidato(), fixture.jogo)
            self.assertEqual('revalidacao_pre_envio_historico_antigo', estado)
            transporte.assert_not_called()
            self.assertEqual(0, fixture.banco.conexao.execute("SELECT count(*) FROM entregas_alertas WHERE status='entregue'").fetchone()[0])
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
