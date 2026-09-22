import json
import shutil
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from backup_banco import (
    BackupBanco,
    calcular_sha256,
    caminho_manifesto,
    restaurar_banco_de_backup,
    verificar_arquivo_backup,
    verificar_backup_legado,
)
from backup_compactado import (
    caminho_manifesto_compactado,
    compactar_backup_verificado,
    executar_drill_restauracao_compactada,
    restaurar_backup_compactado,
    verificar_backup_compactado,
)
from banco import BancoMonitor


class BackupCompactadoTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / ".teste_backup_compactado"
        shutil.rmtree(self.pasta, ignore_errors=True)
        self.pasta.mkdir(exist_ok=True)
        self.banco_path = self.pasta / "origem.db"
        banco = BancoMonitor(self.banco_path)
        banco.salvar_registro({
            "coletado_em": datetime(2026, 8, 25, 0, 0),
            "url": "u",
            "mandante": "A",
            "visitante": "B",
            "placar": "0-0",
            "status": "10 '",
        })
        banco.fechar()
        origem = sqlite3.connect(self.banco_path)
        try:
            self.backup, _ = BackupBanco(self.pasta / "backups").criar_diario(
                origem, datetime(2026, 8, 25, 1, 0)
            )
        finally:
            origem.close()

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_compacta_verifica_e_restaura_sem_remover_original(self):
        compactacao = compactar_backup_verificado(
            self.backup, agora=datetime(2026, 8, 25, 2, 0)
        )
        arquivo = Path(compactacao["caminho"])

        self.assertTrue(compactacao["saudavel"])
        self.assertTrue(compactacao["criado"])
        self.assertTrue(self.backup.exists())
        self.assertTrue(arquivo.exists())
        self.assertTrue(caminho_manifesto_compactado(arquivo).exists())
        self.assertGreater(compactacao["economia_fracao"], 0)

        verificacao = verificar_backup_compactado(arquivo)
        self.assertTrue(verificacao["valido"])
        destino = self.pasta / "restaurado.db"
        restauracao = restaurar_backup_compactado(arquivo, destino)
        self.assertTrue(restauracao["saudavel"])
        conexao = sqlite3.connect(destino)
        try:
            quantidade = conexao.execute(
                "SELECT COUNT(*) FROM partidas"
            ).fetchone()[0]
        finally:
            conexao.close()
        self.assertEqual(quantidade, 1)

    def test_falha_de_compactacao_preserva_backup_sqlite_integro(self):
        pasta = self.pasta / "fallback"
        gerenciador = BackupBanco(pasta, compactar=True)
        origem = sqlite3.connect(self.banco_path)
        try:
            with patch(
                "backup_compactado.compactar_backup_verificado",
                return_value={
                    "saudavel": False,
                    "estado": "compactacao_falhou",
                    "motivo": "PermissionError",
                    "criado": False,
                },
            ):
                caminho, criado = gerenciador.criar_periodico(
                    origem, datetime(2026, 8, 25, 2, 0)
                )
        finally:
            origem.close()

        self.assertTrue(criado)
        self.assertEqual(caminho.suffix, ".db")
        self.assertTrue(verificar_arquivo_backup(caminho)["valido"])
        self.assertTrue(
            gerenciador.ultima_compactacao["fallback_original"]
        )
        self.assertTrue(
            gerenciador.ultima_compactacao["original_valido"]
        )

    def test_compactacao_e_idempotente_para_mesmo_conteudo(self):
        primeira = compactar_backup_verificado(self.backup)
        segunda = compactar_backup_verificado(self.backup)

        self.assertTrue(primeira["saudavel"])
        self.assertTrue(segunda["saudavel"])
        self.assertFalse(segunda["criado"])
        self.assertEqual(
            segunda["estado"], "compactado_existente_confirmado"
        )

    def test_drill_restaura_uma_vez_por_checksum_e_limpa_temporarios(self):
        compactacao = compactar_backup_verificado(self.backup)
        primeira = executar_drill_restauracao_compactada(
            Path(compactacao["caminho"]).parent,
            agora=datetime(2026, 8, 25, 3, 0),
        )
        segunda = executar_drill_restauracao_compactada(
            Path(compactacao["caminho"]).parent,
            anterior=primeira,
            agora=datetime(2026, 8, 25, 4, 0),
        )

        self.assertTrue(primeira["saudavel"])
        self.assertEqual(primeira["estado"], "restauracao_confirmada")
        self.assertTrue(primeira["executado"])
        self.assertFalse(segunda["executado"])
        self.assertTrue(segunda["resultado_reutilizado"])
        self.assertEqual(segunda["testado_em"], primeira["testado_em"])
        self.assertTrue(primeira["temporarios_removidos"])

    def test_drill_nao_reutiliza_falha_anterior_do_mesmo_backup(self):
        compactacao = compactar_backup_verificado(self.backup)
        anterior = {
            "saudavel": False,
            "estado": "restauracao_falhou",
            "checksum_compactado": compactacao["checksum_compactado"],
            "testado_em": "2026-08-25T02:00:00",
        }

        resultado = executar_drill_restauracao_compactada(
            Path(compactacao["caminho"]).parent,
            anterior=anterior,
            agora=datetime(2026, 8, 25, 3, 0),
        )

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["executado"])
        self.assertFalse(resultado["resultado_reutilizado"])
        self.assertEqual(resultado["estado"], "restauracao_confirmada")

    def test_drills_concorrentes_usam_temporarios_independentes(self):
        compactacao = compactar_backup_verificado(self.backup)
        pasta = Path(compactacao["caminho"]).parent

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(
                lambda _: executar_drill_restauracao_compactada(pasta),
                range(2),
            ))

        self.assertTrue(all(item["saudavel"] for item in resultados))
        self.assertTrue(all(item["executado"] for item in resultados))
        self.assertTrue(all(
            item["temporarios_removidos"] for item in resultados
        ))

    def test_drill_sem_compacto_aguarda_sem_falhar(self):
        vazio = self.pasta / "sem_compactos"
        vazio.mkdir()

        resultado = executar_drill_restauracao_compactada(vazio)

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "aguardando_backup_compacto")
        self.assertFalse(resultado["executado"])

    def test_detecta_corrupcao_sem_instalar_restauracao(self):
        compactacao = compactar_backup_verificado(self.backup)
        arquivo = Path(compactacao["caminho"])
        dados = bytearray(arquivo.read_bytes())
        dados[len(dados) // 2] ^= 0xFF
        arquivo.write_bytes(dados)

        verificacao = verificar_backup_compactado(arquivo)
        destino = self.pasta / "nao_deve_existir.db"
        restauracao = restaurar_backup_compactado(arquivo, destino)
        drill = executar_drill_restauracao_compactada(arquivo.parent)

        self.assertFalse(verificacao["saudavel"])
        self.assertEqual(
            verificacao["motivo"], "checksum_compactado_divergente"
        )
        self.assertFalse(restauracao["saudavel"])
        self.assertFalse(destino.exists())
        self.assertFalse(drill["saudavel"])
        self.assertEqual(drill["estado"], "restauracao_falhou")
        self.assertTrue(drill["temporarios_removidos"])

    def test_recusa_destino_existente_sem_sobrescrever(self):
        compactacao = compactar_backup_verificado(self.backup)
        destino = self.pasta / "existente.db"
        destino.write_bytes(b"preservar")

        restauracao = restaurar_backup_compactado(
            compactacao["caminho"], destino
        )

        self.assertFalse(restauracao["saudavel"])
        self.assertEqual(restauracao["estado"], "destino_ja_existe")
        self.assertEqual(destino.read_bytes(), b"preservar")

    def test_remocao_original_so_ocorre_apos_round_trip_valido(self):
        resultado = compactar_backup_verificado(
            self.backup, remover_original=True
        )

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["original_removido"])
        self.assertFalse(self.backup.exists())
        self.assertFalse(caminho_manifesto(self.backup).exists())
        self.assertTrue(Path(resultado["caminho"]).exists())

    def test_lock_ao_remover_original_preserva_os_dois_formatos_validos(self):
        with patch(
            "backup_compactado._remover_original_apos_roundtrip",
            return_value={
                "original_removido": False,
                "original_preservado": True,
                "limpeza_pendente": True,
                "erro_limpeza": "PermissionError",
            },
        ):
            resultado = compactar_backup_verificado(
                self.backup, remover_original=True
            )

        compacto = Path(resultado["caminho"])
        self.assertTrue(resultado["saudavel"])
        self.assertEqual(
            "compactado_verificado_limpeza_pendente",
            resultado["estado"],
        )
        self.assertTrue(resultado["limpeza_pendente"])
        self.assertTrue(self.backup.exists())
        self.assertTrue(compacto.exists())
        self.assertTrue(verificar_backup_compactado(compacto)["saudavel"])

        reconciliado = compactar_backup_verificado(
            self.backup, remover_original=True
        )
        self.assertTrue(reconciliado["saudavel"])
        self.assertEqual(
            "compactado_existente_confirmado", reconciliado["estado"]
        )
        self.assertFalse(self.backup.exists())

    def test_migracao_gradual_inclui_ponto_pre_migracao_gerenciado(self):
        pasta = self.pasta / "migracao-pendente"
        pasta.mkdir()
        origem = sqlite3.connect(self.banco_path)
        try:
            pre_migracao = BackupBanco(pasta).criar_pre_migracao(
                origem, datetime(2026, 8, 25, 1, 0)
            )
        finally:
            origem.close()

        resultado = BackupBanco(
            pasta, compactar=True
        ).compactar_legado_mais_antigo()

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(pre_migracao.name, resultado["origem"])
        self.assertFalse(pre_migracao.exists())
        self.assertTrue((pasta / resultado["destino"]).is_file())

    def test_migracao_gradual_compacta_um_legado_e_preserva_protecao(self):
        manifesto_path = caminho_manifesto(self.backup)
        manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
        manifesto["protegido_retencao"] = True
        manifesto["motivo_protecao"] = "teste_marco_historico"
        manifesto_path.write_text(
            json.dumps(manifesto), encoding="utf-8"
        )
        gerenciador = BackupBanco(
            self.backup.parent, compactar=True
        )

        resultado = gerenciador.compactar_legado_mais_antigo(
            datetime(2026, 8, 25, 2, 0)
        )
        compactado = Path(resultado["caminho"])

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["executado"])
        self.assertFalse(self.backup.exists())
        self.assertTrue(compactado.exists())
        self.assertTrue(gerenciador._protegido_retencao(compactado))
        manifesto_compacto = json.loads(
            caminho_manifesto(compactado).read_text(encoding="utf-8")
        )
        self.assertTrue(manifesto_compacto["protegido_retencao"])
        self.assertEqual(
            manifesto_compacto["motivo_protecao"],
            "teste_marco_historico",
        )

    def test_migracao_reconcilia_compacto_existente_antes_de_remover_original(self):
        existente = compactar_backup_verificado(self.backup)
        self.assertTrue(Path(existente["caminho"]).exists())
        self.assertTrue(self.backup.exists())

        resultado = BackupBanco(
            self.backup.parent, compactar=True
        ).compactar_legado_mais_antigo()

        self.assertTrue(resultado["saudavel"])
        self.assertFalse(resultado["criado"])
        self.assertTrue(resultado["original_removido"])
        self.assertFalse(self.backup.exists())

    def test_compacta_e_restaura_backup_de_esquema_historico(self):
        legado = self.pasta / "backups" / "monitor_20260801.db"
        conexao = sqlite3.connect(legado)
        try:
            conexao.execute("CREATE TABLE historica (id INTEGER PRIMARY KEY)")
            conexao.execute("INSERT INTO historica(id) VALUES (1)")
            conexao.commit()
        finally:
            conexao.close()
        caminho_manifesto(legado).write_text(
            json.dumps({
                "arquivo": legado.name,
                "criado_em": "2026-08-01T00:00:00",
                "tamanho_bytes": legado.stat().st_size,
                "sha256": calcular_sha256(legado),
                "integridade_sqlite": "ok",
                "tabelas": 1,
                "esquema_compativel": True,
                "violacoes_chaves_estrangeiras": 0,
            }),
            encoding="utf-8",
        )

        self.assertTrue(verificar_backup_legado(legado)["valido"])
        resultado = compactar_backup_verificado(
            legado, remover_original=True
        )
        compacto = Path(resultado["caminho"])
        restaurado = self.pasta / "historico_restaurado.db"
        restauracao = restaurar_backup_compactado(compacto, restaurado)

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(
            resultado["modo_verificacao_sqlite"],
            "integridade_legada",
        )
        self.assertFalse(legado.exists())
        self.assertTrue(restauracao["saudavel"])
        self.assertTrue(
            verificar_backup_legado(
                restaurado,
                manifesto_esperado=json.loads(
                    caminho_manifesto_compactado(compacto).read_text(
                        encoding="utf-8"
                    )
                )["manifesto_sqlite"],
            )["valido"]
        )

    def test_gzip_truncado_falha_fechado_e_limpa_temporario(self):
        compactacao = compactar_backup_verificado(self.backup)
        arquivo = Path(compactacao["caminho"])
        dados = arquivo.read_bytes()
        arquivo.write_bytes(dados[: max(len(dados) // 2, 1)])
        manifesto_path = caminho_manifesto_compactado(arquivo)
        manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
        manifesto["tamanho_compactado_bytes"] = arquivo.stat().st_size
        manifesto["sha256_compactado"] = calcular_sha256(arquivo)
        manifesto_path.write_text(
            json.dumps(manifesto), encoding="utf-8"
        )
        temporarios = self.pasta / "temporarios"
        temporarios.mkdir()

        verificacao = verificar_backup_compactado(
            arquivo, pasta_temporaria=temporarios
        )

        self.assertFalse(verificacao["saudavel"])
        self.assertEqual(verificacao["motivo"], "descompactacao_falhou")
        self.assertEqual(list(temporarios.iterdir()), [])

    def test_rotacao_compactada_e_rollback_convivem(self):
        origem = sqlite3.connect(self.banco_path)
        try:
            compactado, criado = BackupBanco(
                self.pasta / "rotacao-gzip", compactar=True
            ).criar_diario(origem, datetime(2026, 8, 25, 3, 0))
            legado, criado_legado = BackupBanco(
                self.pasta / "rotacao-db", compactar=False
            ).criar_diario(origem, datetime(2026, 8, 25, 3, 0))
        finally:
            origem.close()

        self.assertTrue(criado)
        self.assertTrue(criado_legado)
        self.assertTrue(compactado.name.endswith(".db.gz"))
        self.assertEqual(legado.suffix, ".db")
        self.assertFalse(Path(str(compactado)[:-3]).exists())
        self.assertTrue(verificar_arquivo_backup(compactado)["valido"])
        self.assertTrue(verificar_arquivo_backup(legado)["valido"])

    def test_rotaciona_backup_compactado_apos_migracao_aditiva(self):
        pasta_backups = self.pasta / "migracao-gzip"
        gerenciador = BackupBanco(pasta_backups, compactar=True)
        agora = datetime(2026, 8, 25, 5, 0)
        origem = sqlite3.connect(self.banco_path)
        try:
            antigo, criado = gerenciador.criar_diario(origem, agora)
            origem.execute(
                "CREATE TABLE auditoria_migracao_teste (id INTEGER)"
            )
            origem.commit()
            import banco

            esquema = dict(banco.ESQUEMA_OBRIGATORIO)
            esquema["auditoria_migracao_teste"] = {"id"}
            tabelas = set(banco.TABELAS_OBRIGATORIAS)
            tabelas.add("auditoria_migracao_teste")
            with patch.object(
                banco, "ESQUEMA_OBRIGATORIO", esquema
            ), patch.object(
                banco, "TABELAS_OBRIGATORIAS", tabelas
            ):
                atual, recriado = gerenciador.criar_diario(
                    origem, agora.replace(minute=10)
                )
                self.assertTrue(verificar_arquivo_backup(atual)["valido"])
                arquivados = list(
                    pasta_backups.glob("invalido_monitor_*.db.gz")
                )
                self.assertEqual(len(arquivados), 1)
                self.assertTrue(arquivados[0].is_file())
                self.assertTrue(
                    caminho_manifesto(arquivados[0]).is_file()
                )
        finally:
            origem.close()

        self.assertTrue(criado)
        self.assertTrue(recriado)
        self.assertEqual(atual, antigo)

    def test_restauracao_automatica_seleciona_backup_compactado(self):
        pasta_backups = self.pasta / "restauracao-automatica"
        origem = sqlite3.connect(self.banco_path)
        try:
            compactado, _ = BackupBanco(
                pasta_backups, compactar=True
            ).criar_diario(origem, datetime(2026, 8, 25, 4, 0))
        finally:
            origem.close()
        destino = self.pasta / "banco-recuperado.db"

        resultado = restaurar_banco_de_backup(
            destino,
            pasta_backups,
            datetime(2026, 8, 25, 4, 30),
            motivo="teste_round_trip_gzip",
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["backup"], compactado.name)
        conexao = sqlite3.connect(destino)
        try:
            self.assertEqual(
                conexao.execute("SELECT COUNT(*) FROM partidas").fetchone()[0],
                1,
            )
        finally:
            conexao.close()

    def test_retencao_periodica_conta_db_e_gzip_na_mesma_politica(self):
        pasta = self.pasta / "retencao-mista"
        origem = sqlite3.connect(self.banco_path)
        try:
            legado, _ = BackupBanco(
                pasta, manter_periodicos=1, compactar=False
            ).criar_periodico(origem, datetime(2026, 8, 25, 0, 0))
            compactado, _ = BackupBanco(
                pasta, manter_periodicos=1, compactar=True
            ).criar_periodico(origem, datetime(2026, 8, 25, 6, 0))
        finally:
            origem.close()

        self.assertFalse(legado.exists())
        self.assertTrue(compactado.exists())
        self.assertEqual(
            len(BackupBanco._glob_formatos(pasta, "periodico_*.db")), 1
        )

    def test_espelho_copia_e_revalida_formato_compactado(self):
        pasta = self.pasta / "local-espelho"
        espelho = self.pasta / "unidade-espelho"
        origem = sqlite3.connect(self.banco_path)
        try:
            compactado, _ = BackupBanco(
                pasta,
                pasta_espelho=espelho,
                compactar=True,
            ).criar_periodico(origem, datetime(2026, 8, 25, 12, 0))
        finally:
            origem.close()
        replica = espelho / compactado.name

        self.assertTrue(replica.exists())
        self.assertTrue(caminho_manifesto(replica).exists())
        self.assertTrue(verificar_arquivo_backup(replica)["valido"])


if __name__ == "__main__":
    unittest.main()
