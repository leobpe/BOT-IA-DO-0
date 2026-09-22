import unittest
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from repositorio_pre_live import (
    RepositorioPreLive,
    preparar_banco_pre_live,
    verificar_backup_pre_live,
    verificar_banco_pre_live,
)


class RepositorioPreLiveTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path.cwd() / f".teste_repositorio_pre_live_{uuid4().hex}"
        self.pasta.mkdir()
        self.repo = RepositorioPreLive(self.pasta / "pre_live.db")

    def tearDown(self):
        self.repo.fechar()
        shutil.rmtree(self.pasta, ignore_errors=True)

    def bilhete(
        self, fixture_id, odd=1.5, estado="apto_sombra_confirmado"
    ):
        return {
            "tipo": "simples", "bookmaker": "Casa A",
            "odd_total": odd, "probabilidade_modelo": 0.72,
            "edge_modelo": 0.0533, "estado": estado,
            "versao": "v1", "linhagem_sha256": "linha",
            "pernas": [{
                "fixture_id": fixture_id, "bookmaker_id": 1,
                "mercado": "resultado", "selecao": "mandante",
                "odd": odd,
            }],
        }

    def test_registra_deduplica_finaliza_e_resume(self):
        self.assertEqual(1, self.repo.registrar_bilhetes([self.bilhete(1)], "2026-08-27"))
        self.assertEqual(0, self.repo.registrar_bilhetes([self.bilhete(1)], "2026-08-27"))
        pendentes = self.repo.listar_bilhetes_pendentes()
        self.assertEqual(1, len(pendentes))
        self.assertTrue(self.repo.finalizar_bilhete(pendentes[0]["id"], "green", 0.5))
        resumo = self.repo.resumir_validacao("linha")
        self.assertEqual(1, resumo["resultados"])
        self.assertEqual(1, resumo["greens"])
        self.assertEqual(0.5, resumo["roi"])
        self.assertFalse(resumo["apto_revisao"])

    def test_apto_revisao_exige_roi_inferior_positivo(self):
        for indice in range(30):
            self.repo.registrar_bilhetes(
                [self.bilhete(indice + 1, odd=1.5)], "2026-08-27"
            )
        for item in self.repo.listar_bilhetes_pendentes():
            self.repo.finalizar_bilhete(item["id"], "green", 0.5)
        resumo = self.repo.resumir_validacao("linha")
        self.assertTrue(resumo["apto_revisao"])
        self.assertGreater(resumo["roi_95_inferior"], 0)

    def test_backup_e_verificado_e_restaurado_apos_corrupcao(self):
        self.repo.registrar_bilhetes([self.bilhete(77)], "2026-08-27")
        pasta_backups = self.pasta / "backups"
        backup = self.repo.criar_backup(
            pasta_backups,
            agora=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
        )
        caminho_backup = pasta_backups / backup["arquivo"]
        self.assertTrue(verificar_banco_pre_live(caminho_backup)["valido"])
        self.assertTrue(verificar_backup_pre_live(caminho_backup)["saudavel"])
        self.repo.fechar()
        (self.pasta / "pre_live.db").write_bytes(b"banco corrompido")
        preparacao = preparar_banco_pre_live(
            self.pasta / "pre_live.db", pasta_backups
        )
        self.assertTrue(preparacao["restaurado"])
        self.assertTrue((pasta_backups / preparacao["quarentena"]).exists())
        self.repo = RepositorioPreLive(self.pasta / "pre_live.db")
        self.assertEqual(1, len(self.repo.listar_bilhetes_pendentes()))

    def test_corrupcao_sem_backup_falha_fechado(self):
        self.repo.fechar()
        (self.pasta / "pre_live.db").write_bytes(b"invalido")
        with self.assertRaisesRegex(
            RuntimeError, "pre_live_corrompido_sem_backup_restauravel"
        ):
            preparar_banco_pre_live(
                self.pasta / "pre_live.db", self.pasta / "backups"
            )

    def test_backup_recusa_manifesto_adulterado(self):
        pasta_backups = self.pasta / "backups"
        backup = self.repo.criar_backup(
            pasta_backups,
            agora=datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc),
        )
        caminho = pasta_backups / backup["arquivo"]
        caminho.with_suffix(".db.manifest.json").write_text(
            "{}", encoding="utf-8"
        )
        self.assertFalse(verificar_backup_pre_live(caminho)["saudavel"])

    def test_retencao_nao_apaga_quarentena_forense(self):
        pasta_backups = self.pasta / "backups"
        pasta_backups.mkdir()
        quarentena = pasta_backups / "pre_live_corrompido_20260827.db"
        quarentena.write_bytes(b"preservar")
        self.repo.criar_backup(
            pasta_backups,
            agora=datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc),
            manter=1,
        )
        self.repo.criar_backup(
            pasta_backups,
            agora=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
            manter=1,
        )
        self.assertTrue(quarentena.exists())

    def test_preliminar_e_atualizado_quando_escalacao_confirma(self):
        preliminar = self.bilhete(
            88, odd=1.50, estado="preliminar_aguardando_escalacao"
        )
        confirmado = self.bilhete(88, odd=1.56)
        self.assertEqual(
            1, self.repo.registrar_bilhetes([preliminar], "2026-08-27")
        )
        detalhes = self.repo.registrar_bilhetes(
            [confirmado], "2026-08-27", detalhar=True
        )
        self.assertEqual({"inseridos": 0, "confirmados": 1}, detalhes)
        pendente = self.repo.listar_bilhetes_pendentes()[0]["bilhete"]
        self.assertEqual("apto_sombra_confirmado", pendente["estado"])
        self.assertEqual(1.56, pendente["odd_total"])

    def test_preliminar_e_promovido_para_envio_automatico(self):
        preliminar = self.bilhete(
            89, odd=1.50, estado="preliminar_aguardando_escalacao"
        )
        confirmado = self.bilhete(
            89, odd=1.55, estado="apto_envio_automatico"
        )
        self.repo.registrar_bilhetes([preliminar], "2026-08-27")

        detalhes = self.repo.registrar_bilhetes(
            [confirmado], "2026-08-27", detalhar=True
        )

        self.assertEqual({"inseridos": 0, "confirmados": 1}, detalhes)
        candidatos = self.repo.listar_confirmados_para_envio(
            "2026-08-27", "-1002", limite=3
        )
        self.assertEqual(1, len(candidatos))
        self.assertEqual(
            "apto_envio_automatico", candidatos[0]["bilhete"]["estado"]
        )

    def test_sombra_confirmada_nao_entra_na_fila_oficial(self):
        self.repo.registrar_bilhetes([self.bilhete(90)], "2026-08-27")
        self.assertEqual([], self.repo.listar_confirmados_para_envio(
            "2026-08-27", "-1002", limite=3
        ))

    def test_resultado_de_cada_perna_e_persistido_ate_finalizar(self):
        bilhete = self.bilhete(93)
        bilhete["tipo"] = "multipla_dois_jogos"
        bilhete["pernas"].append({
            "fixture_id": 94, "bookmaker_id": 1,
            "mercado": "total_gols", "selecao": "over_1.5",
            "odd": 1.20,
        })
        self.repo.registrar_bilhetes([bilhete], "2026-08-27")
        item = self.repo.listar_bilhetes_pendentes()[0]

        self.assertEqual(2, self.repo.registrar_resultados_pernas(
            item["id"], item["bilhete"], ["red", "pendente"]
        ))
        self.repo.finalizar_bilhete(item["id"], "red", -1.0)
        self.assertEqual(1, len(self.repo.listar_bilhetes_pendentes()))
        self.repo.registrar_resultados_pernas(
            item["id"], item["bilhete"], ["red", "green"]
        )

        resultados = self.repo.listar_resultados_pernas(item["id"])
        self.assertEqual(["red", "green"], [
            resultado["resultado"] for resultado in resultados
        ])
        self.assertEqual([], self.repo.listar_bilhetes_pendentes())

    def test_validacao_nao_promove_bilhetes_sem_escalacao(self):
        self.repo.registrar_bilhetes([
            self.bilhete(
                91, estado="preliminar_aguardando_escalacao"
            )
        ], "2026-08-27")
        pendente = self.repo.listar_bilhetes_pendentes()[0]
        self.repo.finalizar_bilhete(pendente["id"], "green", 0.5)
        resumo = self.repo.resumir_validacao("linha")
        self.assertEqual(0, resumo["resultados"])

    def test_entrega_finalizada_fica_disponivel_para_edicao_unica(self):
        self.repo.registrar_bilhetes([self.bilhete(92)], "2026-08-27")
        pendente = self.repo.listar_bilhetes_pendentes()[0]
        self.assertTrue(self.repo.registrar_entrega(
            pendente["id"], "-1002", 77
        ))
        self.assertEqual(1, len(
            self.repo.listar_bilhetes_entregues_pendentes()
        ))
        self.repo.finalizar_bilhete(pendente["id"], "green", 0.5)
        entregas = self.repo.listar_entregas_para_editar()
        self.assertEqual(1, len(entregas))
        self.assertEqual("green", entregas[0]["resultado"])
        self.assertTrue(self.repo.marcar_entrega_editada(entregas[0]["id"]))
        self.assertEqual([], self.repo.listar_entregas_para_editar())

    def test_entrega_red_volta_para_edicao_quando_outra_perna_finaliza(self):
        bilhete = self.bilhete(95)
        bilhete["tipo"] = "multipla_dois_jogos"
        bilhete["pernas"].append({
            "fixture_id": 96, "bookmaker_id": 1,
            "mercado": "total_gols", "selecao": "over_1.5",
            "odd": 1.20,
        })
        self.repo.registrar_bilhetes([bilhete], "2026-08-27")
        item = self.repo.listar_bilhetes_pendentes()[0]
        self.repo.registrar_entrega(item["id"], "-1002", 78)
        self.repo.registrar_resultados_pernas(
            item["id"], item["bilhete"], ["red", "pendente"]
        )
        self.repo.finalizar_bilhete(item["id"], "red", -1.0)

        primeira = self.repo.listar_entregas_para_editar()[0]
        self.assertEqual(
            ["red", "pendente"],
            [x["resultado"] for x in primeira["resultados_pernas"]],
        )
        self.repo.marcar_entrega_editada(
            primeira["id"], primeira["resultado_sha256"]
        )
        self.assertEqual([], self.repo.listar_entregas_para_editar())

        self.repo.registrar_resultados_pernas(
            item["id"], item["bilhete"], ["red", "green"]
        )
        segunda = self.repo.listar_entregas_para_editar()[0]
        self.assertNotEqual(
            primeira["resultado_sha256"], segunda["resultado_sha256"]
        )
        self.assertEqual(
            ["red", "green"],
            [x["resultado"] for x in segunda["resultados_pernas"]],
        )

    def test_lista_preliminar_diaria_e_persistida_e_atualizada(self):
        self.assertIsNone(self.repo.obter_lista_preliminar(
            "2026-08-27", "-1002"
        ))
        criada = self.repo.registrar_lista_preliminar(
            "2026-08-27", "-1002", 77, "hash-1"
        )
        self.assertEqual(77, criada["mensagem_id"])
        self.assertEqual("hash-1", criada["conteudo_sha256"])
        atualizada = self.repo.registrar_lista_preliminar(
            "2026-08-27", "-1002", 77, "hash-2"
        )
        self.assertEqual(77, atualizada["mensagem_id"])
        self.assertEqual("hash-2", atualizada["conteudo_sha256"])

    def test_lista_partidas_publicadas_em_todos_os_horarios_do_dia(self):
        bilhetes = [self.bilhete(101), self.bilhete(202)]
        self.repo.registrar_bilhetes(bilhetes, "2026-08-27")
        self.repo.registrar_lista_preliminar(
            "2026-08-27|09:00", "-1002", 77, "hash-1",
            bilhetes=[bilhetes[0]], data_bilhetes="2026-08-27",
        )
        self.repo.registrar_lista_preliminar(
            "2026-08-27|12:00", "-1002", 78, "hash-2",
            bilhetes=[bilhetes[1]], data_bilhetes="2026-08-27",
        )

        self.assertEqual(
            {101, 202},
            self.repo.listar_fixture_ids_publicados(
                "2026-08-27", "-1002"
            ),
        )
        self.assertEqual(
            set(),
            self.repo.listar_fixture_ids_publicados(
                "2026-08-28", "-1002"
            ),
        )


if __name__ == "__main__":
    unittest.main()
