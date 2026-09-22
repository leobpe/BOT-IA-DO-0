import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from banco import BancoMonitor
from linhagem_regras import (
    ARQUIVOS_LOGICA_REGRAS,
    auditar_linhagem_regra,
    calcular_linhagem_regra,
    registrar_ou_validar_linhagem_regra,
    registrar_inicio_linhagem_sinais,
    resumir_cobertura_linhagem_sinais,
)
from versoes_regras import VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86
from versoes_challengers_preciso import VERSAO_PROXIMO_GOL_FILTRO_PRECISO
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)


class LinhagemRegrasTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd()
        self.caminho_banco = self.pasta / ".teste_linhagem_regras.db"
        for sufixo in ("", "-wal", "-shm"):
            caminho = Path(str(self.caminho_banco) + sufixo)
            if caminho.exists():
                caminho.unlink()
        self.banco = BancoMonitor(self.caminho_banco)
        self.hashes = {
            nome: (str(indice + 1) * 64)[:64]
            for indice, nome in enumerate(ARQUIVOS_LOGICA_REGRAS)
        }
        self.hash_arquivo = patch(
            "linhagem_regras._hash_arquivo",
            side_effect=lambda caminho: self.hashes[Path(caminho).name],
        )
        self.hash_arquivo.start()
        self.limites = patch(
            "linhagem_regras.obter_limites_risco",
            return_value=SimpleNamespace(odd_minima=1.4, odd_maxima=2.5),
        )
        self.limites.start()

    def tearDown(self):
        self.hash_arquivo.stop()
        self.limites.stop()
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            caminho = Path(str(self.caminho_banco) + sufixo)
            if caminho.exists():
                caminho.unlink()

    def test_registra_nova_versao_e_valida_fingerprint(self):
        estado = registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "vinculada")
        self.assertEqual(estado["origem"], "nova")
        self.assertEqual(len(estado["fingerprint_atual"]), 64)
        self.assertTrue(estado["ancora_presente"])

    def test_linhagem_ft_inclui_politica_local_sem_alterar_base(self):
        self.hashes.update({
            "politica_escanteios_ft.py": "a" * 64,
            "versoes_regras.py": "b" * 64,
        })

        base = calcular_linhagem_regra(
            self.pasta, "sinais-v6", "features-v2"
        )
        ft = calcular_linhagem_regra(
            self.pasta,
            VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
            "features-v2",
        )

        self.assertNotIn(
            "politica_escanteios_ft.py",
            base["componentes"]["arquivos"],
        )
        self.assertIn(
            "politica_escanteios_ft.py",
            ft["componentes"]["arquivos"],
        )
        self.assertNotEqual(base["fingerprint"], ft["fingerprint"])

    def test_challenger_novo_nao_altera_componentes_da_v10f_congelada(self):
        self.hashes.update({
            "politica_proximo_gol_preciso.py": "a" * 64,
            "proximo_gol_balanceado_sombra.py": "b" * 64,
            "versoes_challengers_preciso.py": "c" * 64,
            "versoes_proximo_gol_balanceado.py": "d" * 64,
        })
        precisa = calcular_linhagem_regra(
            self.pasta, VERSAO_PROXIMO_GOL_FILTRO_PRECISO, "features-v2"
        )
        balanceada = calcular_linhagem_regra(
            self.pasta,
            VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            "features-v2",
        )

        arquivos_precisa = precisa["componentes"]["arquivos"]
        arquivos_balanceada = balanceada["componentes"]["arquivos"]
        self.assertIn("versoes_challengers_preciso.py", arquivos_precisa)
        self.assertNotIn(
            "versoes_proximo_gol_balanceado.py", arquivos_precisa
        )
        self.assertIn(
            "versoes_proximo_gol_balanceado.py", arquivos_balanceada
        )
        self.assertIn(
            "versoes_challengers_preciso.py", arquivos_balanceada
        )

    def test_adota_historico_existente_sem_fingir_origem_nova(self):
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO partidas (
                    packball_url, mandante, visitante,
                    primeira_coleta, ultima_coleta
                ) VALUES (
                    'partida', 'A', 'B',
                    '2026-07-21T12:00:00', '2026-07-21T12:00:00'
                )
                """
            )
            partida = self.banco.conexao.execute(
                "SELECT id FROM partidas WHERE packball_url='partida'"
            ).fetchone()[0]
            self.banco.conexao.execute(
                """
                INSERT INTO snapshots (
                    partida_id, coletado_em, placar, status, texto_linha
                ) VALUES (?, '2026-07-21T12:00:00', '0-0', '10', '')
                """,
                (partida,),
            )
            snapshot = self.banco.conexao.execute(
                "SELECT id FROM snapshots WHERE partida_id=?", (partida,)
            ).fetchone()[0]
            self.banco.conexao.execute(
                """
                INSERT INTO sinais (
                    partida_id, snapshot_id, criado_em, mercado, regra_versao
                ) VALUES (?, ?, '2026-07-21T12:00:00', 'gol_ft', 'sinais-teste')
                """,
                (partida, snapshot),
            )

        estado = registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )

        self.assertEqual(estado["origem"], "adocao_legado")
        self.assertEqual(estado["sinais_existentes_na_adocao"], 1)

    def test_mudanca_sem_nova_versao_falha_fechada(self):
        registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )
        self.hashes["motor_sinais.py"] = "f" * 64

        auditoria = auditar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )
        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["estado"], "fingerprint_divergente")
        self.assertEqual(
            auditoria["componentes_divergentes"],
            ["arquivo:motor_sinais.py"],
        )
        with self.assertRaisesRegex(RuntimeError, "nova versão"):
            registrar_ou_validar_linhagem_regra(
                self.banco.conexao,
                self.pasta,
                "sinais-teste",
                "features-v1",
            )

    def test_registro_adulterado_e_recusado(self):
        registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )
        chave = "linhagem_regra:sinais-teste"
        registro = json.loads(self.banco.conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave,)
        ).fetchone()[0])
        registro["componentes"]["versao_features"] = "adulterada"
        with self.banco.conexao:
            self.banco.conexao.execute(
                "UPDATE metadados SET valor=? WHERE chave=?",
                (json.dumps(registro), chave),
            )

        auditoria = auditar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["estado"], "registro_invalido")

    def test_vinculo_apagado_apos_inicializacao_nao_e_readotado(self):
        registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                "DELETE FROM metadados WHERE chave=?",
                ("linhagem_regra:sinais-teste",),
            )

        auditoria = auditar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(
            auditoria["estado"], "vinculo_ausente_apos_inicializacao"
        )
        with self.assertRaisesRegex(RuntimeError, "nova versão"):
            registrar_ou_validar_linhagem_regra(
                self.banco.conexao,
                self.pasta,
                "sinais-teste",
                "features-v1",
            )

    def test_ancora_ausente_e_reposta_sem_alterar_vinculo(self):
        primeiro = registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )
        with self.banco.conexao:
            self.banco.conexao.execute(
                "DELETE FROM metadados WHERE chave=?",
                ("linhagem_regra_inicializada:sinais-teste",),
            )

        intermediario = auditar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )
        final = registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )

        self.assertEqual(intermediario["estado"], "vinculada_sem_ancora")
        self.assertEqual(final["estado"], "vinculada")
        self.assertEqual(
            final["fingerprint_registrado"], primeiro["fingerprint_registrado"]
        )

    def test_banco_recusa_novo_sinal_sem_fingerprint_vinculado(self):
        linhagem = registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )
        snapshot = self.banco.salvar_registro({
            "coletado_em": "2026-07-21T22:00:00",
            "url": "https://packball.com/match/linhagem/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": "20 '",
        })
        candidato = {
            "mercado": "gol_ft",
            "regra_versao": "sinais-teste",
            "status": "aprovado",
        }

        with self.assertRaisesRegex(ValueError, "fingerprint vinculado"):
            self.banco.salvar_candidatos(snapshot, [candidato])
        candidato["regra_fingerprint"] = linhagem["fingerprint_atual"]
        self.banco.salvar_candidatos(snapshot, [candidato])

        cobertura = resumir_cobertura_linhagem_sinais(
            self.banco.conexao, "sinais-teste"
        )
        self.assertTrue(cobertura["saudavel"])
        self.assertEqual(cobertura["vinculados"], 1)
        self.assertEqual(cobertura["novos_sem_fingerprint"], 0)

    def test_marco_separa_legado_de_novo_sinal_sem_fingerprint(self):
        linhagem = registrar_ou_validar_linhagem_regra(
            self.banco.conexao, self.pasta, "sinais-teste", "features-v1"
        )
        registrar_inicio_linhagem_sinais(
            self.banco.conexao,
            "sinais-teste",
            linhagem["fingerprint_atual"],
        )
        snapshot = self.banco.salvar_registro({
            "coletado_em": "9998-01-01T00:00:00",
            "url": "https://packball.com/match/sem-hash/live",
            "mandante": "A", "visitante": "B",
            "placar": "0-0", "status": "20 '",
        })
        partida = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot,)
        ).fetchone()[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO sinais (
                    partida_id, snapshot_id, criado_em, mercado,
                    regra_versao, status
                ) VALUES (?, ?, '9998-01-01T00:00:00', 'gol_ft',
                          'sinais-teste', 'aprovado')
                """,
                (partida, snapshot),
            )

        cobertura = resumir_cobertura_linhagem_sinais(
            self.banco.conexao, "sinais-teste"
        )

        self.assertFalse(cobertura["saudavel"])
        self.assertEqual(cobertura["novos_sem_fingerprint"], 1)


if __name__ == "__main__":
    unittest.main()
