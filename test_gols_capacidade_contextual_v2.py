import unittest
from pathlib import Path
from unittest.mock import patch

from controle_v2b_ft import suspender_v2b_ft
from diagnostico_gols_capacidade_contextual_v2 import (
    diagnosticar_gols_capacidade_contextual_v2,
)

from gols_capacidade_contextual_v2 import (
    VERSAO_GOL_FT,
    VERSAO_GOL_HT,
    classificar_competicao,
    coletar_contexto_capacidade_v2,
    gerar_gols_capacidade_contextual_v2,
)
from telegram_alertas import (
    candidato_gol_capacidade_contextual_v2_grupo_teste,
    motivo_suspensao_simulacao,
)


def _partidas(time_id, mando, quantidade=15, gols_pro=3, gols_contra=2):
    itens = []
    for indice in range(quantidade):
        em_casa = mando if indice < 6 else not mando
        casa_id, fora_id = ((time_id, 9000 + indice) if em_casa else (9000 + indice, time_id))
        casa_gols, fora_gols = ((gols_pro, gols_contra) if em_casa else (gols_contra, gols_pro))
        itens.append({
            "fixture": {"timestamp": 100000 - indice},
            "teams": {"home": {"id": casa_id}, "away": {"id": fora_id}},
            "goals": {"home": casa_gols, "away": fora_gols},
        })
    return itens


class _API:
    def __init__(self, quantidade=15):
        self.quantidade = quantidade
        self.chamadas = []

    def _lista_contexto(self, chave, caminho, parametros, ttl, prazo):
        self.chamadas.append((chave, parametros))
        time_id = parametros["team"]
        return _partidas(time_id, time_id == 1, self.quantidade)

    def _dados_contexto(self, chave, caminho, parametros, ttl, prazo):
        return {
            "fixtures": {"played": {"home": 12, "away": 12}},
            "goals": {
                "for": {"average": {"home": "2.4", "away": "2.2"}},
                "against": {"average": {"home": "1.7", "away": "1.8"}},
            },
        }


def _contexto(quantidade=15, com_live=True):
    contexto = coletar_contexto_capacidade_v2(
        _API(quantidade),
        {
            "times": {"home": {"id": 1}, "away": {"id": 2}},
            "liga": {"id": 10, "season": 2026},
        },
        {
            "estatisticas_temporada": {},
            "eventos_ao_vivo": {"times": {}, "eventos_criticos_recentes": []},
        },
    )
    if com_live:
        contexto["evolucao_temporal_api_live"] = {
            "5": {"chutes": [2, 1], "xg": [0.18, 0.02], "duracao_real_minutos": 5.0}
        }
    return contexto


def _candidato(mercado="gol_ft", minuto=60, odd=2.20, placar=(0, 0)):
    return {
        "mercado": mercado,
        "linha": sum(placar) + 0.5,
        "odd": odd,
        "pontuacao_tecnica": 55,
        "probabilidade_calibrada": None,
        "regra_versao": "base",
        "status": "rejeitado",
        "bloqueios": ["atividade_recente_insuficiente_gols"],
        "features": {
            "minuto": minuto,
            "janelas": {
                "5": {
                    "disponivel": True,
                    "duracao_real_minutos": 5,
                    "chutes_total": 3,
                    "pressao_pico": [70, 30],
                    "pressao_tendencia": [5, -2],
                }
            },
        },
    }


def _qualidade():
    return {"pontuacao": 95, "campos_ausentes": [], "divergencia_critica": False}


class TestGolsCapacidadeContextualV2(unittest.TestCase):
    def test_classifica_segmentos_sem_misturar_calibracao(self):
        self.assertEqual("sub21", classificar_competicao({"liga": "Brasil U21"}))
        self.assertEqual("sub23", classificar_competicao({"mandante": "Time Sub-23"}))
        self.assertEqual("reservas", classificar_competicao({"liga": "Reserve League"}))
        self.assertEqual("profissional", classificar_competicao({"liga": "Serie A"}))

    def test_coleta_15_e_separa_mando(self):
        api = _API()
        contexto = coletar_contexto_capacidade_v2(api, {
            "times": {"home": {"id": 1}, "away": {"id": 2}},
            "league": {"id": 10, "season": 2026},
        })
        self.assertEqual(15, contexto["capacidade_times_v2"]["cobertura"]["mandante"]["historico_total"])
        self.assertEqual(6, contexto["capacidade_times_v2"]["cobertura"]["mandante"]["historico_mando"])
        self.assertTrue(all(chamada[1]["last"] == 15 for chamada in api.chamadas))

    def test_historico_curto_nao_gera(self):
        candidato = _candidato()
        gerados = gerar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0"}, [candidato], _contexto(9), _qualidade()
        )
        self.assertEqual([], gerados)
        diagnostico = diagnosticar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0"}, [candidato],
            _contexto(9), _qualidade(), gerados,
        )
        self.assertTrue(diagnostico["linhagem_compativel"])
        self.assertEqual(
            "historico_contextual_insuficiente",
            diagnostico["por_mercado"]["gol_ft"]["motivo"],
        )

    def test_usa_historico_mando_adversario_live_e_linha_exata(self):
        candidato = _candidato()
        itens = gerar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0", "liga": "Serie A"},
            [candidato], _contexto(), _qualidade(),
        )
        self.assertEqual(1, len(itens))
        diagnostico = diagnosticar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0", "liga": "Serie A"},
            [candidato], _contexto(), _qualidade(), itens,
        )
        self.assertEqual(1, diagnostico["gerados"])
        self.assertEqual(
            "gerado", diagnostico["por_mercado"]["gol_ft"]["estado"]
        )
        item = itens[0]
        self.assertEqual(VERSAO_GOL_FT, item["features"]["exploracao_sombra"]["versao"])
        dados = item["features"]["gol_capacidade_contextual_v2"]
        self.assertEqual("profissional", dados["segmento_competicao"])
        self.assertGreaterEqual(dados["modelo_historico"]["amostra_casa_total"], 10)
        self.assertEqual({"chutes_5min", "xg_5min", "pressao_5min"}, set(dados["evidencia_recente"]["evidencias"]))
        self.assertFalse(item["features"]["exploracao_sombra"]["grupo_teste"])
        self.assertTrue(
            candidato_gol_capacidade_contextual_v2_grupo_teste(item)
        )
        with patch(
            "telegram_alertas.GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO",
            False,
        ):
            self.assertFalse(
                candidato_gol_capacidade_contextual_v2_grupo_teste(item)
            )
        estado = Path.cwd() / ".teste_v2b_ft_telegram.json"
        estado.unlink(missing_ok=True)
        try:
            suspender_v2b_ft(
                "teste|ancora",
                "evidencia_negativa",
                caminho=estado,
            )
            self.assertFalse(
                candidato_gol_capacidade_contextual_v2_grupo_teste(
                    item, estado
                )
            )
        finally:
            estado.unlink(missing_ok=True)

    def test_acumulado_sem_janela_recente_nao_basta(self):
        candidato = _candidato()
        candidato["features"]["chutes_no_gol_total"] = 20
        candidato["features"]["janelas"]["5"]["disponivel"] = False
        self.assertEqual([], gerar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0"}, [candidato], _contexto(com_live=False), _qualidade()
        ))

    def test_api_temporal_velha_nao_basta(self):
        candidato = _candidato()
        candidato["features"]["janelas"]["5"]["disponivel"] = False
        contexto = _contexto()
        contexto["evolucao_temporal_api_live"]["5"]["duracao_real_minutos"] = 12
        self.assertEqual([], gerar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0"}, [candidato], contexto, _qualidade()
        ))

    def test_cartao_vermelho_e_odd_em_alta_bloqueiam(self):
        candidato = _candidato()
        contexto = _contexto()
        contexto["eventos_ao_vivo"]["times"] = {"mandante": {"cartoes_vermelhos": 1}}
        self.assertEqual([], gerar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0"}, [candidato], contexto, _qualidade()
        ))
        contexto = _contexto()
        candidato["features"]["movimento_gols"] = {
            "odd_anterior": 2.08, "odd_atual": 2.20, "delta": 0.12, "direcao": "alta"
        }
        self.assertEqual([], gerar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0"}, [candidato], contexto, _qualidade()
        ))

    def test_respeita_limites_e_mede_base_aprovada_sem_duplicar_regra(self):
        for mercado, minuto in (("gol_ht", 29), ("gol_ft", 83)):
            candidato = _candidato(mercado, minuto)
            self.assertEqual([], gerar_gols_capacidade_contextual_v2(
                {"status": f"{minuto}'", "placar": "0-0"}, [candidato], _contexto(), _qualidade()
            ))
        candidato = _candidato()
        candidato["status"], candidato["bloqueios"] = "aprovado", []
        itens = gerar_gols_capacidade_contextual_v2(
            {"status": "60'", "placar": "0-0"},
            [candidato], _contexto(), _qualidade(),
        )
        self.assertEqual(1, len(itens))
        self.assertEqual("simulacao", itens[0]["status"])
        self.assertTrue(
            candidato_gol_capacidade_contextual_v2_grupo_teste(itens[0])
        )

    def test_ht_zero_a_zero_exige_live_forte(self):
        candidato = _candidato("gol_ht", 20, 2.20)
        candidato["features"]["janelas"]["5"].update({
            "chutes_total": 2, "pressao_pico": [50, 20]
        })
        contexto = _contexto()
        contexto["evolucao_temporal_api_live"]["5"].update({"chutes": [1, 1], "xg": [0.05, 0.04]})
        self.assertEqual([], gerar_gols_capacidade_contextual_v2(
            {"status": "20'", "placar": "0-0"}, [candidato], contexto, _qualidade()
        ))

    def test_ht_v2b_exclui_linha_05_que_foi_negativa_na_v1(self):
        candidato = _candidato("gol_ht", 20, 2.20, placar=(0, 0))
        self.assertEqual([], gerar_gols_capacidade_contextual_v2(
            {"status": "20'", "placar": "0-0"},
            [candidato], _contexto(), _qualidade(),
        ))

    def test_scanner_temporal_recupera_contador_reiniciado_em_sombra(self):
        candidato = _candidato("gol_ht", 20, 2.20, placar=(1, 0))
        candidato["features"]["janelas"]["5"]["disponivel"] = False
        qualidade = _qualidade()
        qualidade["auditoria_indicadores_temporais_lista"] = {
            "idade_segundos": 30,
            "janelas": {"5": {
                "chutes": [1, 1],
                "pressao": [70, 20],
                "expectativa_gols": [0.3, 0.2],
            }},
        }
        itens = gerar_gols_capacidade_contextual_v2(
            {"status": "20'", "placar": "1-0"},
            [candidato], _contexto(com_live=False), qualidade,
        )
        self.assertEqual(1, len(itens))
        evidencia = itens[0]["features"][
            "gol_capacidade_contextual_v2"
        ]["evidencia_recente"]
        self.assertTrue(evidencia["scanner_temporal_valido"])
        self.assertIn("expectativa_gols_5min", evidencia["evidencias"])
        self.assertTrue(
            candidato_gol_capacidade_contextual_v2_grupo_teste(itens[0])
        )
        self.assertIsNone(motivo_suspensao_simulacao(itens[0]))


if __name__ == "__main__":
    unittest.main()
