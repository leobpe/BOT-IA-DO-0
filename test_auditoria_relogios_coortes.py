import sqlite3
import unittest
from datetime import datetime

from auditoria_relogios_coortes import (
    COORTES_SINAIS,
    auditar_relogios_pre_live,
    auditar_relogios_sinais,
)
from validacao_escanteios_ft_asiatico_prospectiva import (
    registrar_ou_validar_definicao as registrar_escanteios_legado,
)
from validacao_escanteios_ft_asiatico_executavel import (
    registrar_ou_validar_definicao as registrar_escanteios,
)
from validacao_gol_ft_antecipado_preciso import (
    registrar_ou_validar_definicao as registrar_ft,
)
from validacao_gol_ht_antecipado_preciso import (
    registrar_ou_validar_definicao as registrar_ht,
)
from validacao_pre_live_preciso import (
    VERSAO_ALVO,
    registrar_ou_validar_definicao as registrar_pre_live,
)
from validacao_quase_candidatos_proximo_gol import (
    registrar_ou_validar_definicao as registrar_quase,
)


class AuditoriaRelogiosCoortesTest(unittest.TestCase):
    def _banco_monitor(self):
        conexao = sqlite3.connect(":memory:")
        conexao.execute(
            "CREATE TABLE sinais (id INTEGER PRIMARY KEY, criado_em TEXT)"
        )
        instante = datetime(2026, 9, 10, 14, 0)
        for registrar in (
            registrar_ht, registrar_ft, registrar_escanteios,
            registrar_escanteios_legado, registrar_quase,
        ):
            registrar(conexao, instante)
        return conexao

    def _banco_pre_live(self):
        conexao = sqlite3.connect(":memory:")
        conexao.execute(
            "CREATE TABLE bilhetes_pre_live ("
            "id INTEGER PRIMARY KEY, criado_em TEXT, versao TEXT)"
        )
        registrar_pre_live(
            conexao, datetime.fromisoformat("2026-09-10T18:00:00+00:00")
        )
        return conexao

    def test_monitor_aceita_sinais_locais_e_ancoras_duplas(self):
        conexao = self._banco_monitor()
        self.addCleanup(conexao.close)
        conexao.execute(
            "INSERT INTO sinais VALUES (?,?)",
            (1, "2026-09-10T14:00:01"),
        )

        resultado = auditar_relogios_sinais(conexao)

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(len(COORTES_SINAIS), len(resultado["coortes"]))
        self.assertTrue(all(
            item["ancora_presente"] and item["integra"]
            for item in resultado["coortes"]
        ))

    def test_monitor_rejeita_sinal_com_offset(self):
        conexao = self._banco_monitor()
        self.addCleanup(conexao.close)
        conexao.execute(
            "INSERT INTO sinais VALUES (?,?)",
            (1, "2026-09-10T18:00:01+00:00"),
        )

        resultado = auditar_relogios_sinais(conexao)

        self.assertFalse(resultado["saudavel"])
        self.assertIn("sinais:criado_em_com_offset:1", resultado["problemas"])

    def test_monitor_rejeita_ancora_com_relogio_local_adulterado(self):
        conexao = self._banco_monitor()
        self.addCleanup(conexao.close)
        nome, chave, _ = COORTES_SINAIS[0]
        documento = __import__("json").loads(conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave,)
        ).fetchone()[0])
        documento["registrado_em_relogio_sinais"] = "2026-09-10T13:00:00"
        conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (__import__("json").dumps(documento), chave),
        )

        resultado = auditar_relogios_sinais(conexao)

        self.assertFalse(resultado["saudavel"])
        self.assertIn(
            f"{nome}:relogios_nao_representam_mesmo_instante",
            resultado["problemas"],
        )

    def test_pre_live_aceita_bilhetes_utc(self):
        conexao = self._banco_pre_live()
        self.addCleanup(conexao.close)
        conexao.execute(
            "INSERT INTO bilhetes_pre_live VALUES (?,?,?)",
            (1, "2026-09-10T18:00:01+00:00", VERSAO_ALVO),
        )

        resultado = auditar_relogios_pre_live(conexao)

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(1, resultado["amostra_bilhetes"])

    def test_pre_live_rejeita_bilhete_local_sem_offset(self):
        conexao = self._banco_pre_live()
        self.addCleanup(conexao.close)
        conexao.execute(
            "INSERT INTO bilhetes_pre_live VALUES (?,?,?)",
            (1, "2026-09-10T14:00:01", VERSAO_ALVO),
        )

        resultado = auditar_relogios_pre_live(conexao)

        self.assertFalse(resultado["saudavel"])
        self.assertIn("pre_live:criado_em_fora_utc:1", resultado["problemas"])


if __name__ == "__main__":
    unittest.main()
