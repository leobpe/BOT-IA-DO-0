import os
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from backtest import AvaliadorBacktest
from banco import BancoMonitor
from calibracao import CalibradorBacktest
from linhagem_regras import (
    registrar_inicio_linhagem_sinais,
    registrar_ou_validar_linhagem_regra,
)
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS
from versoes_gol_ft_reforcado import (
    VERSAO_GOL_FT_REFORCADO,
    versoes_regras_operacionais as versoes_regras_ativas,
)
from relatorio_simulacoes import comparar_filtro_simulacoes
from servico_monitor import ServicoMonitor
from telegram_alertas import AlertasTelegram


class PackBallFalso:
    def __init__(self):
        self.estatisticas = {
            "Chutes": "9-4",
            "Chutes no gol": "5-2",
            "Índice de pressão": "70-30",
            "Escanteios": "3-2",
            "Ataques perigosos": "42-21",
            "Posse de bola": "61-39",
            "Ataques": "71-48",
            "_metadados": {"pais": "Teste", "liga": "Liga E2E"},
        }

    def coletar_estatisticas(self, pagina, jogo):
        return dict(self.estatisticas)


class HistoricoFalso:
    def calcular(self, *args, **kwargs):
        return {
            "5": {
                "chutes": [4, 2],
                "escanteios": [1, 1],
                "resets_detectados": [],
                "pressao_resumo": {
                    "media": [68, 32],
                    "pico": [82, 41],
                },
            },
            "10": None,
            "15": None,
            "aceleracao_5_vs_5": {"chutes": [1, 0]},
            "eventos_recentes": {},
        }


def odds_estruturadas(*args, **kwargs):
    coletado_em = datetime.now().replace(microsecond=0).isoformat()
    return {
        "pre_jogo": [],
        "ao_vivo": [
            {
                "mercado": "Total Gols",
                "dados": "Over Under 0.5 1.80 2.00",
                "categoria": "gols",
                "fonte": "packball", "cache": False,
                "coletado_em": coletado_em, "idade_segundos": 0.0,
                "ofertas": [
                    {"linha": 0.5, "over": 1.8, "under": 2.0}
                ],
            },
            {
                "mercado": "Escanteios - 2 Opções",
                "dados": "Over Under 5.5 1.90 1.90",
                "categoria": "escanteios",
                "tipo_mercado": "total",
                "fonte": "packball", "cache": False,
                "coletado_em": coletado_em, "idade_segundos": 0.0,
                "ofertas": [
                    {"linha": 5.5, "over": 1.9, "under": 1.9}
                ],
            },
            {
                "mercado": "Marcar O Próximo Gol",
                "dados": "1: 1.75 2: 2.20 No: 8.00",
                "categoria": "gols",
                "escopo": "proximo", "tipo_mercado": "proximo",
                "fonte": "packball", "cache": False,
                "coletado_em": coletado_em, "idade_segundos": 0.0,
                "selecoes": {
                    "casa": 1.75,
                    "visitante": 2.2,
                    "sem_gol": 8.0,
                },
            },
        ],
    }


def fixture(placar, minuto):
    return {
        "fixture": {
            "id": 9001,
            "status": {"short": "2H", "elapsed": minuto},
        },
        "teams": {
            "home": {"id": 1, "name": "Time A"},
            "away": {"id": 2, "name": "Time B"},
        },
        "goals": {"home": placar[0], "away": placar[1]},
    }


class IntegracaoPipelineTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_integracao_pipeline.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.regra_fingerprints = {}
        for regra_versao in versoes_regras_ativas():
            linhagem = registrar_ou_validar_linhagem_regra(
                self.banco.conexao,
                Path.cwd(),
                regra_versao,
                VERSAO_FEATURES,
            )
            fingerprint = linhagem["fingerprint_atual"]
            self.regra_fingerprints[regra_versao] = fingerprint
            registrar_inicio_linhagem_sinais(
                self.banco.conexao,
                regra_versao,
                fingerprint,
            )
        self.servico_fingerprint = self.regra_fingerprints[VERSAO_REGRAS]
        self.servico = object.__new__(ServicoMonitor)
        self.servico.banco = self.banco
        self.servico.regra_fingerprint = self.servico_fingerprint
        self.servico.regra_fingerprints = self.regra_fingerprints
        self.servico.packball = PackBallFalso()
        self.servico.historico = HistoricoFalso()
        self.servico.api = Mock()
        self.servico.api.saude_operacional.return_value = {
            "saudavel": True,
            "motivo": None,
        }
        self.servico.api.estatisticas.return_value = {
            "Chutes no gol": [5, 2]
        }
        self.servico.api.odds_escanteios_asiaticos_ft.return_value = None
        self.servico.api.odds_escanteios_asiaticos_1t.return_value = None
        self.servico.api.odds_gols_total_ft.return_value = None
        self.servico.api.odds_proximo_gol.return_value = None
        self.servico.observabilidade = Mock()
        self.servico.backtest = AvaliadorBacktest(self.banco)
        self.servico.calibrador = CalibradorBacktest(self.banco)
        self.servico.alertas = AlertasTelegram(
            self.banco,
            transporte=lambda *_: {"ok": True},
            validador_operacao_oficial=lambda: {
                "apto": True,
                "estado": "saudavel",
            },
        )
        self.servico.alertas.modo_teste = False
        self.servico.salvar_registro = self.banco.salvar_registro
        self.jogo = {
            "url": "https://packball.com/match/9001/live",
            "mandante": "Time A",
            "visitante": "Time B",
            "placar": "0-0",
            "status": "65 '",
        }

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    @patch.dict(
        os.environ,
        {"GOL_FT_REFORCADO_OFICIAL_ATIVO": "1"},
        clear=False,
    )
    @patch(
        "servico_monitor.aplicar_protecao_conversao_gols",
        return_value={
            "avaliados": 0, "aprovados": 0,
            "bloqueados": 0, "motivos": {},
        },
    )
    @patch("servico_monitor.coletar_odds", side_effect=odds_estruturadas)
    def test_partida_percorre_pipeline_e_liquida_proximo_gol(
        self, _odds, _protecao
    ):
        with redirect_stdout(StringIO()):
            primeiro = self.servico.processar_jogo(
                None,
                dict(self.jogo),
                [fixture([0, 0], 65)],
                instante=datetime(2026, 7, 20, 12, 0, 0),
            )

        self.assertEqual(primeiro["fixture_id"], 9001)
        self.assertTrue(primeiro["odds_coletadas"])
        contagens = self.banco.contagens()
        self.assertEqual(contagens["snapshots"], 1)
        self.assertEqual(contagens["odds"], 3)
        self.assertEqual(contagens["sinais"], 6)
        aprovados = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM sinais WHERE status='aprovado'"
        ).fetchone()[0]
        self.assertEqual(aprovados, 3)
        ft = self.banco.conexao.execute(
            """
            SELECT regra_versao, status FROM sinais
            WHERE mercado='gol_ft' ORDER BY id
            """
        ).fetchall()
        self.assertEqual(
            [tuple(item) for item in ft],
            [
                (VERSAO_REGRAS, "simulacao"),
                (VERSAO_GOL_FT_REFORCADO, "aprovado"),
            ],
        )

        jogo_com_gol = {
            **self.jogo, "placar": "1-0", "status": "Finalizado"
        }
        with redirect_stdout(StringIO()):
            segundo = self.servico.processar_jogo(
                None,
                jogo_com_gol,
                [fixture([1, 0], 66)],
                instante=datetime(2026, 7, 20, 12, 1, 0),
            )

        self.assertEqual(segundo["fixture_id"], 9001)
        resultado = self.banco.conexao.execute(
            """
            SELECT r.resultado, r.retorno_unidades
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            WHERE s.mercado='proximo_gol'
            ORDER BY s.id LIMIT 1
            """
        ).fetchone()
        self.assertEqual(tuple(resultado), ("green", 0.75))
        partida = self.banco.conexao.execute(
            "SELECT api_fixture_id, api_orientacao FROM partidas"
        ).fetchone()
        self.assertEqual(tuple(partida), (9001, "direta"))
        entregas = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM entregas_alertas"
        ).fetchone()[0]
        self.assertEqual(entregas, 0)

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_CHAT_ID_GOLS": "123",
            "SINAIS_TESTE_ATIVO": "1",
            "PONTUACAO_MINIMA_SINAL_TESTE": "75",
            "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE": "75",
            "QUALIDADE_MINIMA_SINAL_TESTE": "80",
            "LIMITE_DIARIO_SINAIS_TESTE": "100",
            "LIMITE_GLOBAL_SINAIS_TESTE": "200",
        },
        clear=False,
    )
    @patch(
        "servico_monitor.motivo_suspensao_simulacao",
        return_value=None,
    )
    @patch(
        "telegram_alertas.motivo_suspensao_simulacao",
        return_value=None,
    )
    def test_filtro_v2_envia_um_liquida_e_separa_as_duas_coortes(
        self, _suspensao_alerta, _suspensao_servico
    ):
        chamadas = []
        self.servico.alertas = AlertasTelegram(
            self.banco,
            transporte=lambda _url, dados: (
                chamadas.append(dados)
                or {
                    "ok": True,
                    "result": {
                        "message_id": 9901,
                        "date": 1785049200,
                    },
                }
            ),
            validador_operacao_oficial=lambda: {
                "apto": True,
                "estado": "saudavel",
            },
        )
        inicio = datetime.fromisoformat(
            self.servico.alertas.experimento_filtro["iniciado_em"]
        )
        instante = inicio.replace(microsecond=0)
        decisao_em = datetime.now().replace(microsecond=0).isoformat()
        snapshot = self.banco.salvar_registro(
            {
                "coletado_em": instante,
                "url": "https://packball.com/match/filtro-v2/live",
                "mandante": "Time Filtro A",
                "visitante": "Time Filtro B",
                "placar": "0-0",
                "status": "60 '",
                "estatisticas": {"Chutes no gol": "5-2"},
                "qualidade": {
                    "pontuacao": 90,
                    "apto_para_sinal": True,
                    "fontes": ["packball"],
                },
            }
        )
        candidatos = [
            {
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 86.0,
                "probabilidade_calibrada": None,
                "regra_versao": VERSAO_REGRAS,
                "regra_fingerprint": self.servico_fingerprint,
                "qualidade_dados": 90,
                "motivos": ["alvo=mais_1_gol"],
                "features": {
                    "minuto": 60,
                    "decisao_em": decisao_em,
                    "estado_observado_em": decisao_em,
                    "idade_odds_segundos": 0.0,
                },
                "status": "aprovado",
            },
            {
                "mercado": "proximo_gol",
                "linha": "casa",
                "odd": 1.8,
                "pontuacao_tecnica": 72.5,
                "probabilidade_calibrada": None,
                "regra_versao": VERSAO_REGRAS,
                "regra_fingerprint": self.servico_fingerprint,
                "qualidade_dados": 90,
                "motivos": ["lado_dominante=casa"],
                "features": {
                    "minuto": 60,
                    "decisao_em": decisao_em,
                    "estado_observado_em": decisao_em,
                    "idade_odds_segundos": 0.0,
                },
                "status": "aprovado",
            },
        ]
        ids = self.banco.salvar_candidatos(
            snapshot, candidatos, instante
        )
        pares = list(zip(ids, candidatos))

        selecionada = self.servico._selecionar_simulacao_teste(pares)
        retorno = self.servico.alertas.avaliar_e_enviar(
            selecionada[0],
            selecionada[1],
            {
                "mandante": "Time Filtro A",
                "visitante": "Time Filtro B",
                "placar": "0-0",
                "status": "60 '",
            },
        )

        self.assertEqual(retorno, "teste_entregue")
        self.assertEqual(len(chamadas), 1)
        decisoes = self.banco.conexao.execute(
            """
            SELECT s.mercado, e.canal, e.status, e.erro
            FROM entregas_alertas e
            JOIN sinais s ON s.id=e.sinal_id
            ORDER BY s.id, e.id
            """
        ).fetchall()
        self.assertEqual(
            [tuple(item) for item in decisoes],
            [
                ("gol_ft", "123:teste", "entregue", None),
                (
                    "proximo_gol",
                    "gateway:teste",
                    "filtrado",
                    "pontuacao_teste_insuficiente",
                ),
            ],
        )

        final = self.banco.salvar_registro(
            {
                "coletado_em": instante + timedelta(minutes=1),
                "url": "https://packball.com/match/filtro-v2/live",
                "mandante": "Time Filtro A",
                "visitante": "Time Filtro B",
                "placar": "1-0",
                "status": "Finalizado",
                "estatisticas": {"Chutes no gol": "7-2"},
                "qualidade": {
                    "pontuacao": 90,
                    "apto_para_sinal": True,
                    "fontes": ["packball"],
                },
            }
        )
        self.assertEqual(AvaliadorBacktest(self.banco).avaliar_snapshot(final), 2)

        comparacao = comparar_filtro_simulacoes(
            self.banco.conexao,
            regra_versao=VERSAO_REGRAS,
            amostra_minima=1,
            iniciado_em=(
                self.servico.alertas.experimento_filtro["iniciado_em"]
            ),
            regra_fingerprint=self.servico_fingerprint,
        )
        self.assertEqual(comparacao["enviadas"]["geral"]["amostra"], 1)
        self.assertEqual(comparacao["filtradas"]["geral"]["amostra"], 1)
        geral = comparacao["comparacao"]["geral"]
        self.assertEqual(geral["decisoes_enviadas"], 1)
        self.assertEqual(geral["decisoes_filtradas"], 1)
        self.assertEqual(geral["resultados_resolvidos_enviadas"], 1)
        self.assertEqual(geral["resultados_resolvidos_filtradas"], 1)
        self.assertEqual(geral["pendentes_enviadas"], 0)
        self.assertEqual(geral["pendentes_filtradas"], 0)
        self.assertEqual(
            geral["estado"], "avaliavel"
        )


if __name__ == "__main__":
    unittest.main()
