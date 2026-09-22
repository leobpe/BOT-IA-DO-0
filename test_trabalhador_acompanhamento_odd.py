import json
import threading
import unittest
from pathlib import Path

from trabalhador_acompanhamento_odd import (
    TrabalhadorAcompanhamentoOdd,
)


class _ObservabilidadeFalsa:
    def __init__(self):
        self.eventos = []

    def ciclo_progresso(self, etapa, **dados):
        self.eventos.append((etapa, dados))


class _ServicoFalso:
    def __init__(self, segunda_rodada=None, falhar_primeira=False):
        self.observabilidade = _ObservabilidadeFalsa()
        self.segunda_rodada = segunda_rodada
        self.falhar_primeira = falhar_primeira
        self.chamadas = 0
        self.fechado = False

    def _rechecar_acompanhamentos_odd_api(self, forcar=False):
        self.chamadas += 1
        if self.falhar_primeira and self.chamadas == 1:
            raise RuntimeError("falha temporaria")
        if self.chamadas >= 2 and self.segunda_rodada is not None:
            self.segunda_rodada.set()
        return {
            "consultados": 1,
            "atingiram_alvo": 0,
            "enviados": 0,
            "bloqueados": 0,
            "motivos": {"odd_abaixo_da_faixa": 1},
            "referencias_sombra_rapidas_tentadas": 1,
            "referencias_sombra_rapidas_reservadas": 1,
            "referencias_sombra_rapidas_consultadas": 1,
            "referencias_sombra_rapidas_linha_exata": 1,
            "referencias_sombra_rapidas_auditadas": 1,
            "referencias_sombra_rapidas_observadas": 1,
            "comparacoes_referencia_sombra_rapida": 1,
            "creditos_estimados_referencia_sombra_rapida": 1,
            "referencias_sombra_rapidas_motivos": {"observada": 1},
            "referencias_sombra_rapidas_funil": {
                "versao": "funil-referencia-sombra-rapida-v1",
                "avaliadas": 1,
                "aprovadas": 1,
                "reprovadas": 0,
                "com_oferta": 1,
                "bloqueadas_custodia": 0,
                "bloqueadas_materializacao": 0,
                "alertas_enviados": 1,
                "fontes_executaveis_pos_envio": 1,
                "selecionadas_para_consulta": 1,
                "suprimidas_limite_rodada": 0,
                "exclusoes": {},
                "aplicacao_sinais": False,
                "telegram": False,
            },
            "aplicacao_sinais_referencia_sombra": False,
        }

    def fechar(self):
        self.fechado = True


class _ServicoClvFalho(_ServicoFalso):
    def _capturar_cotacoes_clv_pos_alerta_api(self):
        raise RuntimeError("falha observacional")


class TrabalhadorAcompanhamentoOddTest(unittest.TestCase):
    def test_executa_em_thread_propria_e_persiste_cadencia(self):
        segunda_rodada = threading.Event()
        servicos = []
        threads_fabrica = []

        def criar():
            threads_fabrica.append(threading.get_ident())
            servico = _ServicoFalso(segunda_rodada=segunda_rodada)
            servicos.append(servico)
            return servico

        caminho = Path.cwd() / ".teste_trabalhador_odd_estado.json"
        caminho.unlink(missing_ok=True)
        try:
            trabalhador = TrabalhadorAcompanhamentoOdd(
                criar,
                intervalo_segundos=0.02,
                caminho_estado=caminho,
            )
            principal = threading.get_ident()
            self.assertTrue(trabalhador.iniciar())
            self.assertTrue(segunda_rodada.wait(1.0))
            self.assertTrue(trabalhador.parar(timeout_segundos=1.0))

            estado = json.loads(caminho.read_text(encoding="utf-8"))
        finally:
            caminho.unlink(missing_ok=True)

        self.assertNotEqual(threads_fabrica[0], principal)
        self.assertGreaterEqual(servicos[0].chamadas, 2)
        self.assertTrue(servicos[0].fechado)
        self.assertEqual(estado["status"], "encerrado")
        self.assertTrue(estado["sem_navegacao_packball"])
        self.assertIsNotNone(estado["intervalo_real_segundos"])
        self.assertEqual(
            estado["referencias_sombra_rapidas_observadas"], 1
        )
        self.assertEqual(
            estado["comparacoes_referencia_sombra_rapida"], 1
        )
        self.assertFalse(
            estado["aplicacao_sinais_referencia_sombra"]
        )
        acumulada = estado["referencia_sombra_rapida_acumulada"]
        self.assertEqual(
            acumulada["versao"],
            "referencia-sincronizada-monitor-odd-rapido-acumulada-v1",
        )
        self.assertTrue(acumulada["integridade"])
        self.assertGreaterEqual(acumulada["rodadas"], 2)
        self.assertGreaterEqual(acumulada["observadas"], 2)
        self.assertGreaterEqual(acumulada["comparacoes"], 2)
        self.assertFalse(acumulada["aplicacao_sinais"])
        self.assertFalse(acumulada["telegram"])
        self.assertIsNotNone(acumulada["ultima_evidencia_em"])
        funil = acumulada["funil_selecao"]
        self.assertTrue(funil["integridade"])
        self.assertGreaterEqual(funil["avaliadas"], 2)
        self.assertEqual(funil["avaliadas"], funil["aprovadas"])
        self.assertEqual(
            funil["selecionadas_para_consulta"],
            acumulada["tentadas"],
        )
        self.assertTrue(any(
            etapa == "trabalhador_acompanhamento_odd"
            for etapa, _dados in servicos[0].observabilidade.eventos
        ))

    def test_acumulado_sobrevive_reinicio_do_trabalhador(self):
        caminho = Path.cwd() / ".teste_trabalhador_odd_reinicio.json"
        caminho.unlink(missing_ok=True)
        try:
            segunda_rodada_1 = threading.Event()
            servico_1 = _ServicoFalso(
                segunda_rodada=segunda_rodada_1
            )
            trabalhador_1 = TrabalhadorAcompanhamentoOdd(
                lambda: servico_1,
                intervalo_segundos=0.01,
                caminho_estado=caminho,
            )
            trabalhador_1.iniciar()
            self.assertTrue(segunda_rodada_1.wait(1.0))
            self.assertTrue(trabalhador_1.parar(timeout_segundos=1.0))
            primeiro = json.loads(
                caminho.read_text(encoding="utf-8")
            )["referencia_sombra_rapida_acumulada"]

            segunda_rodada_2 = threading.Event()
            servico_2 = _ServicoFalso(
                segunda_rodada=segunda_rodada_2
            )
            trabalhador_2 = TrabalhadorAcompanhamentoOdd(
                lambda: servico_2,
                intervalo_segundos=0.01,
                caminho_estado=caminho,
            )
            trabalhador_2.iniciar()
            self.assertTrue(segunda_rodada_2.wait(1.0))
            self.assertTrue(trabalhador_2.parar(timeout_segundos=1.0))
            segundo = json.loads(
                caminho.read_text(encoding="utf-8")
            )["referencia_sombra_rapida_acumulada"]
        finally:
            caminho.unlink(missing_ok=True)

        self.assertGreater(segundo["rodadas"], primeiro["rodadas"])
        self.assertGreater(segundo["observadas"], primeiro["observadas"])
        self.assertGreater(segundo["comparacoes"], primeiro["comparacoes"])
        self.assertEqual(segundo["iniciado_em"], primeiro["iniciado_em"])
        self.assertTrue(segundo["integridade"])

    def test_migra_ultima_rodada_legada_sem_perder_evidencia(self):
        caminho = Path.cwd() / ".teste_trabalhador_odd_legado.json"
        caminho.write_text(json.dumps({
            "status": "encerrado",
            "atualizado_em": "2026-09-11T15:00:00",
            "ultima_rodada_em": "2026-09-11T14:59:59",
            "referencias_sombra_rapidas_tentadas": 1,
            "referencias_sombra_rapidas_reservadas": 1,
            "referencias_sombra_rapidas_consultadas": 1,
            "referencias_sombra_rapidas_linha_exata": 1,
            "referencias_sombra_rapidas_auditadas": 1,
            "referencias_sombra_rapidas_observadas": 1,
            "comparacoes_referencia_sombra_rapida": 2,
            "creditos_estimados_referencia_sombra_rapida": 1,
            "referencias_sombra_rapidas_motivos": {"observada": 1},
            "aplicacao_sinais_referencia_sombra": False,
        }), encoding="utf-8")
        try:
            segunda_rodada = threading.Event()
            trabalhador = TrabalhadorAcompanhamentoOdd(
                lambda: _ServicoFalso(
                    segunda_rodada=segunda_rodada
                ),
                intervalo_segundos=0.01,
                caminho_estado=caminho,
            )
            acumulada_inicial = trabalhador.estado()[
                "referencia_sombra_rapida_acumulada"
            ]
            trabalhador.iniciar()
            self.assertTrue(segunda_rodada.wait(1.0))
            self.assertTrue(trabalhador.parar(timeout_segundos=1.0))
            acumulada = json.loads(
                caminho.read_text(encoding="utf-8")
            )["referencia_sombra_rapida_acumulada"]
        finally:
            caminho.unlink(missing_ok=True)

        self.assertEqual(
            acumulada_inicial["origem_migracao"],
            "ultima_rodada_legada",
        )
        self.assertEqual(acumulada_inicial["rodadas"], 1)
        self.assertEqual(acumulada_inicial["observadas"], 1)
        self.assertEqual(acumulada_inicial["comparacoes"], 2)
        self.assertEqual(
            acumulada["funil_selecao"][
                "tentativas_anteriores_funil"
            ],
            1,
        )
        self.assertGreaterEqual(acumulada["rodadas"], 3)
        self.assertGreaterEqual(acumulada["tentadas"], 3)
        self.assertGreaterEqual(
            acumulada["funil_selecao"]["selecionadas_para_consulta"],
            2,
        )
        self.assertTrue(acumulada["integridade"])

    def test_falha_de_uma_rodada_nao_mata_trabalhador(self):
        segunda_rodada = threading.Event()
        servico = _ServicoFalso(
            segunda_rodada=segunda_rodada,
            falhar_primeira=True,
        )
        trabalhador = TrabalhadorAcompanhamentoOdd(
            lambda: servico,
            intervalo_segundos=0.01,
        )

        trabalhador.iniciar()
        self.assertTrue(segunda_rodada.wait(1.0))
        estado_antes = trabalhador.estado()
        encerrado = trabalhador.parar(timeout_segundos=1.0)

        self.assertTrue(encerrado)
        self.assertGreaterEqual(servico.chamadas, 2)
        self.assertEqual(estado_antes["status"], "ativo")
        self.assertEqual(estado_antes["falhas_consecutivas"], 0)

    def test_falha_clv_e_isolada_e_nao_degrada_fila_operacional(self):
        segunda_rodada = threading.Event()
        servico = _ServicoClvFalho(segunda_rodada=segunda_rodada)
        trabalhador = TrabalhadorAcompanhamentoOdd(
            lambda: servico,
            intervalo_segundos=0.01,
        )

        trabalhador.iniciar()
        self.assertTrue(segunda_rodada.wait(1.0))
        estado_antes = trabalhador.estado()
        encerrado = trabalhador.parar(timeout_segundos=1.0)

        self.assertTrue(encerrado)
        self.assertEqual("ativo", estado_antes["status"])
        self.assertEqual(0, estado_antes["falhas_consecutivas"])
        self.assertEqual("falha_isolada", estado_antes["clv_pos_alerta_estado"])
        self.assertGreaterEqual(
            estado_antes["clv_pos_alerta_falhas_consecutivas"], 1
        )
        self.assertFalse(estado_antes["clv_pos_alerta_aplicacao_sinais"])
        self.assertFalse(estado_antes["clv_pos_alerta_telegram"])


if __name__ == "__main__":
    unittest.main()
