import json
import sqlite3
import unittest
from datetime import datetime

from politica_proximo_gol_preciso import MOTIVO_PRESSAO, MOTIVO_QUALIDADE
from proximo_gol_balanceado_sombra import (
    CHAVE_DEFINICAO,
    gerar,
    registrar_ou_validar_definicao,
)
from versoes_challengers_preciso import VERSAO_PROXIMO_GOL_FILTRO_PRECISO
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)


class ProximoGolBalanceadoSombraTest(unittest.TestCase):
    def _candidato(self, **alteracoes):
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            "status": "rejeitado",
            "odd": 1.55,
            "pontuacao_tecnica": 60,
            "bloqueios": [MOTIVO_PRESSAO],
            "motivos": [],
            "features": {
                "minuto": 60,
                "qualidade_dados": 100,
                "lado_dominante": "casa",
                "chutes_lado_dominante_5min": 1,
                "janelas": {"5": {
                    "pressao_pico": [60, 25],
                    "pressao_media": [45, 25],
                }},
            },
        }
        candidato.update(alteracoes)
        return candidato

    def test_gera_challenger_de_teste_sem_alterar_original(self):
        original = self._candidato()
        gerados = gerar([original])
        self.assertEqual(1, len(gerados))
        challenger = gerados[0]
        self.assertEqual("rejeitado", original["status"])
        self.assertEqual("simulacao", challenger["status"])
        self.assertEqual([], challenger["bloqueios"])
        self.assertEqual(
            VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            challenger["regra_versao"],
        )
        experimento = challenger["features"]["exploracao_sombra"]
        self.assertEqual("somente_grupo_teste", experimento["telegram"])
        self.assertTrue(experimento["grupo_teste"])
        self.assertFalse(experimento["telegram_oficial"])
        self.assertFalse(experimento["promocao_automatica"])

    def test_preserva_qualquer_outro_bloqueio_e_limites(self):
        casos = (
            self._candidato(bloqueios=[
                MOTIVO_PRESSAO, "lado_dominante_sem_chute_recente"
            ]),
            self._candidato(odd=1.65),
            self._candidato(pontuacao_tecnica=59.9),
            self._candidato(features={
                "minuto": 60,
                "qualidade_dados": 100,
                "lado_dominante": "casa",
                "chutes_lado_dominante_5min": 1,
                "janelas": {"5": {
                    "pressao_pico": [49, 25],
                    "pressao_media": [45, 25],
                }},
            }),
        )
        for candidato in casos:
            with self.subTest(candidato=candidato):
                self.assertEqual([], gerar([candidato]))

    def test_aceita_qualidade_95_sem_relaxar_outro_bloqueio(self):
        candidato = self._candidato(
            bloqueios=[MOTIVO_PRESSAO, MOTIVO_QUALIDADE],
            features={
                "minuto": 60,
                "qualidade_dados": 95,
                "lado_dominante": "casa",
                "chutes_lado_dominante_5min": 1,
                "janelas": {"5": {
                    "pressao_pico": [55, 25],
                    "pressao_media": [45, 25],
                }},
            },
        )
        self.assertEqual(1, len(gerar([candidato])))

        candidato["bloqueios"].append("atividade_recente_insuficiente_gols")
        self.assertEqual([], gerar([candidato]))

    def test_rejeita_qualidade_abaixo_de_95(self):
        candidato = self._candidato(
            bloqueios=[MOTIVO_PRESSAO, MOTIVO_QUALIDADE],
            features={
                "minuto": 60,
                "qualidade_dados": 94.9,
                "lado_dominante": "casa",
                "chutes_lado_dominante_5min": 1,
                "janelas": {"5": {
                    "pressao_pico": [55, 25],
                    "pressao_media": [45, 25],
                }},
            },
        )
        self.assertEqual([], gerar([candidato]))

    def test_exige_vantagem_media_de_pressao(self):
        candidato = self._candidato(features={
            "minuto": 60,
            "qualidade_dados": 100,
            "lado_dominante": "casa",
            "chutes_lado_dominante_5min": 1,
            "janelas": {"5": {
                "pressao_pico": [60, 25],
                "pressao_media": [34, 25],
            }},
        })
        self.assertEqual([], gerar([candidato]))

    def test_rollback_desativa_coleta(self):
        self.assertEqual([], gerar(
            [self._candidato()],
            {"PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO": "0"},
        ))

    def test_definicao_sqlite_e_idempotente(self):
        conexao = sqlite3.connect(":memory:")
        self.addCleanup(conexao.close)
        conexao.row_factory = sqlite3.Row
        conexao.execute(
            "CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT)"
        )
        instante = datetime(2026, 9, 8, 18, 0, 0)
        primeira = registrar_ou_validar_definicao(conexao, instante)
        segunda = registrar_ou_validar_definicao(conexao, instante)
        self.assertEqual(primeira, segunda)
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
        ).fetchone()
        persistida = json.loads(linha["valor"])
        self.assertEqual(
            VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            persistida["regra_versao"],
        )


if __name__ == "__main__":
    unittest.main()
