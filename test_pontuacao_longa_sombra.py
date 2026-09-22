import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from banco import BancoMonitor
from pontuacao_longa_sombra import (
    AMOSTRA_MINIMA_TREINO,
    AMOSTRA_MINIMA_VALIDACAO,
    _registros_prospectivos,
    avaliar_modelo_pontuacao_longa,
    carregar_ancora_pontuacao_longa,
    carregar_modelo_pontuacao_longa,
    registrar_ancora_pontuacao_longa,
    registrar_modelo_pontuacao_longa,
)


def _registro(indice, completo=True, green=None):
    green = (indice % 2 == 0) if green is None else bool(green)
    impulso = 1.0 if green else 0.0
    features = {
        "minuto": 50.0,
        "gols_atuais": 1.0,
        "chutes_no_gol_total": 3.0 + impulso * 3,
        "qualidade_dados": 95.0,
        "j5_disponivel": 1,
        "j10_disponivel": 1,
        "j15_disponivel": 1 if completo else 0,
    }
    for janela in (5, 10, 15):
        features.update({
            f"j{janela}_chutes_por_minuto": 0.2 + impulso * 0.4,
            f"j{janela}_escanteios_por_minuto": 0.1 + impulso * 0.2,
            f"j{janela}_pressao_media_max": 45.0 + impulso * 30,
        })
    return {
        "sinal_id": indice,
        "partida_id": indice,
        "snapshot_id": indice,
        "criado_em": f"2026-08-01T00:{indice % 60:02d}:00",
        "encerrado_em": f"2026-08-01T01:{indice % 60:02d}:00",
        "mercado": "gol_ft",
        "linha": 1.5,
        "odd": 1.8,
        "pontuacao_tecnica": 82.0 - impulso * 8,
        "resultado": "green" if green else "red",
        "alvo_green": int(green),
        "retorno_unidades": 0.8 if green else -1.0,
        "features": features,
    }


def _dataset(registros):
    return {"registros": registros, "fingerprint": "dataset"}


class PontuacaoLongaSombraTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_pontuacao_longa.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.fingerprint = patch(
            "pontuacao_longa_sombra.fingerprint_vinculado_no_banco",
            return_value="f" * 64,
        )
        self.fingerprint.start()

    def tearDown(self):
        self.fingerprint.stop()
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def _registrar_ancora(self):
        with self.banco.conexao:
            return registrar_ancora_pontuacao_longa(
                self.banco.conexao,
                "gol_ft",
                "sinais-v6",
                registrado_em="2026-08-01T12:00:00",
            )

    def test_ancora_e_imutavel_e_nao_reaproveita_amostra_anterior(self):
        primeira = self._registrar_ancora()
        segunda = self._registrar_ancora()

        self.assertTrue(primeira["criada"])
        self.assertFalse(segunda["criada"])
        self.assertTrue(segunda["integro"])
        self.assertEqual(segunda["iniciar_apos_sinal_id"], 0)
        chave = self.banco.conexao.execute(
            "SELECT chave FROM metadados "
            "WHERE chave LIKE 'pontuacao_sombra:longa_ancora:%'"
        ).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.conexao.execute(
                "UPDATE metadados SET valor='{}' WHERE chave=?", (chave,)
            )

    def test_nao_cria_ancora_antes_da_linhagem(self):
        with patch(
            "pontuacao_longa_sombra.fingerprint_vinculado_no_banco",
            return_value=None,
        ):
            resultado = registrar_ancora_pontuacao_longa(
                self.banco.conexao,
                "proximo_gol",
                "sinais-nova",
            )

        self.assertFalse(resultado["criada"])
        self.assertFalse(resultado["integro"])
        self.assertEqual(resultado["estado"], "aguardando_linhagem_regra")
        total = self.banco.conexao.execute(
            "SELECT COUNT(*) FROM metadados "
            "WHERE chave LIKE 'pontuacao_sombra:longa_ancora:%'"
        ).fetchone()[0]
        self.assertEqual(total, 0)

    def test_exige_janelas_5_10_e_15_completas(self):
        ancora = self._registrar_ancora()
        registros = [_registro(1), _registro(2, completo=False)]
        with patch(
            "pontuacao_longa_sombra.construir_dataset_temporal",
            return_value=_dataset(registros),
        ):
            elegiveis, excluidos, _ = _registros_prospectivos(
                self.banco.conexao, "gol_ft", "sinais-v6", ancora
            )

        self.assertEqual([item["sinal_id"] for item in elegiveis], [1])
        self.assertEqual(excluidos["janelas_incompletas"], 1)

    def test_forma_treino_apenas_com_resultados_futuros(self):
        self._registrar_ancora()
        futuros = [_registro(i) for i in range(1, 11)]
        with patch(
            "pontuacao_longa_sombra.construir_dataset_temporal",
            return_value=_dataset(futuros),
        ):
            resultado = registrar_modelo_pontuacao_longa(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )
            avaliacao = avaliar_modelo_pontuacao_longa(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertFalse(resultado["criado"])
        self.assertEqual(resultado["estado"], "formando_treino_prospectivo")
        self.assertEqual(avaliacao["treino"], 10)
        self.assertEqual(avaliacao["faltam_treino"], 50)
        self.assertEqual(avaliacao["validacao"], 0)

    def test_congela_60_treinos_e_os_30_resultados_seguintes(self):
        self._registrar_ancora()
        treino = [_registro(i) for i in range(1, AMOSTRA_MINIMA_TREINO + 1)]
        with patch(
            "pontuacao_longa_sombra.construir_dataset_temporal",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                criado = registrar_modelo_pontuacao_longa(
                    self.banco.conexao, "gol_ft", "sinais-v6"
                )
        self.assertTrue(criado["criado"])
        self.assertTrue(criado["integro"])
        self.assertEqual(criado["treino_ate_sinal_id"], 60)

        validacao = [
            _registro(i)
            for i in range(61, 61 + AMOSTRA_MINIMA_VALIDACAO)
        ]
        extras = [_registro(i, green=True) for i in range(91, 101)]
        with patch(
            "pontuacao_longa_sombra.construir_dataset_temporal",
            return_value=_dataset(treino + validacao),
        ):
            primeira = avaliar_modelo_pontuacao_longa(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )
        with patch(
            "pontuacao_longa_sombra.construir_dataset_temporal",
            return_value=_dataset(treino + validacao + extras),
        ):
            posterior = avaliar_modelo_pontuacao_longa(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertEqual(primeira["validacao"], 30)
        self.assertEqual(posterior["validacao"], 30)
        self.assertEqual(posterior["validacao_total_disponivel"], 40)
        self.assertTrue(posterior["validacao_congelada"])
        self.assertEqual(
            primeira["validacao_fingerprint"],
            posterior["validacao_fingerprint"],
        )
        self.assertEqual(primeira["auc_longa"], posterior["auc_longa"])
        self.assertEqual(
            primeira["brier_longa"], posterior["brier_longa"]
        )
        self.assertEqual(primeira["brier_odd"], posterior["brier_odd"])
        self.assertEqual(primeira["estado"], posterior["estado"])
        self.assertFalse(posterior["aplicacao_automatica"])

    def test_detecta_modelo_corrompido(self):
        self.banco.conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                "pontuacao_sombra:longa_modelo:pontuacao-longa-logistica-v2:"
                "sinais-v6:gol_ft",
                '{"modelo":{}}',
            ),
        )
        carregado = carregar_modelo_pontuacao_longa(
            self.banco.conexao, "gol_ft", "sinais-v6"
        )
        self.assertFalse(carregado["integro"])

    def test_detecta_ancora_vinculada_a_outra_linhagem(self):
        self._registrar_ancora()

        with patch(
            "pontuacao_longa_sombra.fingerprint_vinculado_no_banco",
            return_value="g" * 64,
        ):
            carregada = carregar_ancora_pontuacao_longa(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertFalse(carregada["integro"])
        self.assertEqual(
            carregada["motivo"], "ancora_incompativel_ou_corrompida"
        )

    def test_detecta_modelo_desvinculado_da_ancora(self):
        self._registrar_ancora()
        treino = [_registro(i) for i in range(1, AMOSTRA_MINIMA_TREINO + 1)]
        with patch(
            "pontuacao_longa_sombra.construir_dataset_temporal",
            return_value=_dataset(treino),
        ):
            with self.banco.conexao:
                registrar_modelo_pontuacao_longa(
                    self.banco.conexao, "gol_ft", "sinais-v6"
                )

        with patch(
            "pontuacao_longa_sombra.carregar_ancora_pontuacao_longa",
            return_value={
                "integro": True,
                "ancora_hash": "outra-ancora",
            },
        ):
            carregado = carregar_modelo_pontuacao_longa(
                self.banco.conexao, "gol_ft", "sinais-v6"
            )

        self.assertFalse(carregado["integro"])
        self.assertEqual(
            carregado["motivo"], "modelo_incompativel_ou_corrompido"
        )


if __name__ == "__main__":
    unittest.main()
