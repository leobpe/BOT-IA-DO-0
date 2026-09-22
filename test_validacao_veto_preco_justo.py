import json
import sqlite3
import unittest
from pathlib import Path

from validacao_resultado_valor_justo import (
    VERSAO_MEDIDOR,
    VERSAO_VALOR_JUSTO,
)
from validacao_veto_preco_justo import (
    POLITICA,
    avaliar_veto_preco_justo_sombra,
    resumir_validacao_veto_preco_justo,
    validar_avaliacao_veto,
)


class ValidacaoVetoPrecoJustoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_veto_preco_justo.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.conexao = sqlite3.connect(self.caminho)
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                partida_id INTEGER NOT NULL,
                criado_em TEXT NOT NULL,
                mercado TEXT NOT NULL,
                status TEXT NOT NULL,
                features_json TEXT NOT NULL
            );
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY,
                encerrado_em TEXT,
                resultado TEXT,
                retorno_unidades REAL
            );
            """
        )

    def tearDown(self):
        self.conexao.close()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    @staticmethod
    def _features(valor_esperado, avaliacao=None):
        return json.dumps({
            "melhor_preco_sombra": {
                "versao": VERSAO_MEDIDOR,
                "valor_justo_sombra": {
                    "versao": VERSAO_VALOR_JUSTO,
                    "valor_esperado_referencia": valor_esperado,
                    "avaliacao_veto_preco_sombra": (
                        avaliacao
                        if avaliacao is not None
                        else avaliar_veto_preco_justo_sombra(valor_esperado)
                    ),
                },
            },
        })

    def _inserir(
        self,
        sinal_id,
        partida_id,
        status,
        valor_esperado,
        *,
        criado_em="2026-09-12T19:31:00-04:00",
        retorno=None,
        avaliacao=None,
    ):
        self.conexao.execute(
            "INSERT INTO sinais VALUES (?, ?, ?, 'gol_ft', ?, ?)",
            (
                sinal_id, partida_id, criado_em, status,
                self._features(valor_esperado, avaliacao),
            ),
        )
        if retorno is not None:
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?, ?, ?, ?)",
                (
                    sinal_id,
                    "2026-09-13T01:00:00-04:00",
                    "green" if retorno > 0 else "red",
                    retorno,
                ),
            )
        self.conexao.commit()

    def test_classificacao_e_politica_sao_congeladas_sem_efeito(self):
        veto = avaliar_veto_preco_justo_sombra(-0.05)
        controle = avaliar_veto_preco_justo_sombra(-0.049)
        inelegivel = avaliar_veto_preco_justo_sombra(None)

        self.assertEqual("veto_preco_negativo", veto["classificacao"])
        self.assertEqual("controle_nao_veto", controle["classificacao"])
        self.assertEqual(
            "inelegivel_sem_preco_justo", inelegivel["classificacao"]
        )
        self.assertEqual(POLITICA["definicao_sha256"], veto["politica_sha256"])
        self.assertTrue(validar_avaliacao_veto(veto, -0.05))
        self.assertFalse(veto["aplicacao_sinais"])
        self.assertFalse(veto["telegram"])

    def test_relatorio_ignora_passado_e_separa_origens(self):
        self._inserir(
            1, 1, "aprovado", -0.2,
            criado_em="2026-09-12T19:29:59-04:00", retorno=-1,
        )
        self._inserir(2, 2, "aprovado", -0.2, retorno=-1)
        self._inserir(3, 3, "auditoria", 0.02, retorno=0.8)

        resumo = resumir_validacao_veto_preco_justo(self.conexao)

        self.assertTrue(resumo["saudavel"])
        self.assertEqual(2, resumo["candidatos_pos_ancora"])
        self.assertEqual(
            {"aprovado": 1, "auditoria": 1},
            resumo["composicao_status"],
        )
        estratos = resumo["por_mercado"]["gol_ft"]["estratos"]
        self.assertEqual(1, estratos["candidatos_acionaveis"]["coorte"])
        self.assertEqual(1, estratos["auditorias_silenciosas"]["coorte"])
        self.assertFalse(resumo["aplicacao_sinais"])

    def test_avaliacao_adulterada_falha_fechado(self):
        avaliacao = avaliar_veto_preco_justo_sombra(-0.2)
        avaliacao["classificacao"] = "controle_nao_veto"
        self._inserir(1, 1, "aprovado", -0.2, avaliacao=avaliacao)

        resumo = resumir_validacao_veto_preco_justo(self.conexao)

        self.assertFalse(resumo["saudavel"])
        self.assertEqual("telemetria_veto_inconsistente", resumo["estado"])
        self.assertEqual([1], resumo["ids_invalidos"])

    def test_veto_so_e_comprovado_em_dev_holdout_e_nas_duas_origens(self):
        sinal_id = 1
        for status, deslocamento in (("aprovado", 0), ("auditoria", 1000)):
            for indice in range(120):
                veto = indice % 2 == 0
                self._inserir(
                    sinal_id,
                    deslocamento + indice + 1,
                    status,
                    -0.2 if veto else 0.02,
                    criado_em=(
                        f"2026-09-12T19:{31 + indice // 60:02d}:"
                        f"{indice % 60:02d}-04:00"
                    ),
                    retorno=-1.0 if veto else 0.8,
                )
                sinal_id += 1

        resumo = resumir_validacao_veto_preco_justo(self.conexao)

        self.assertTrue(resumo["saudavel"])
        mercado = resumo["por_mercado"]["gol_ft"]
        self.assertTrue(mercado["veto_transferivel_comprovado"])
        self.assertTrue(mercado["evidencia_completa_nos_dois_estratos"])
        self.assertEqual(
            ["gol_ft"],
            resumo["mercados_com_veto_transferivel_comprovado"],
        )
        for estrato in mercado["estratos"].values():
            self.assertTrue(estrato["veto_benefico_comprovado"])
            self.assertEqual(40, estrato["holdout"][
                "veto_preco_negativo"
            ]["resultados_validos"] + estrato["holdout"][
                "controle_nao_veto"
            ]["resultados_validos"])


if __name__ == "__main__":
    unittest.main()
