import unittest
from datetime import datetime

from custodia_avaliacao import (
    EFEITOS_DESATIVADOS,
    ESTADO_EM_ANDAMENTO,
    ESTADO_FALHA,
    aplicar_efeitos_desativados,
    auditar_cronologia_execucao,
    auditar_efeitos_desativados,
    classificar_execucao,
    construir_estado_nao_concluido,
)


class CustodiaAvaliacaoTest(unittest.TestCase):
    def test_marcador_nao_transporta_conclusao_anterior(self):
        marcador = construir_estado_nao_concluido(
            versao_avaliacao="avaliacao-v1",
            modo="sombra",
            estado_execucao=ESTADO_EM_ANDAMENTO,
            atualizado_em="2026-09-10T10:00:00",
            iniciado_em="2026-09-10T10:00:00",
        )

        self.assertEqual("em_execucao", marcador["estado_execucao"])
        self.assertFalse(marcador["aplicacao_sinais"])
        self.assertFalse(marcador["promocao_automatica"])
        self.assertNotIn("vantagem_comprovada", marcador)
        self.assertNotIn("amostra", marcador)

    def test_falha_desativa_todos_os_efeitos(self):
        falha = construir_estado_nao_concluido(
            versao_avaliacao="avaliacao-v1",
            modo="sombra",
            estado_execucao=ESTADO_FALHA,
            atualizado_em="2026-09-10T10:00:01",
            iniciado_em="2026-09-10T10:00:00",
            finalizado_em="2026-09-10T10:00:01",
            duracao_segundos=1.0,
            motivo_falha="avaliacao_falhou",
            tipo_erro="RuntimeError",
            erro="falha controlada",
        )

        self.assertEqual("falha_avaliacao", falha["estado"])
        self.assertEqual("avaliacao_falhou", falha["motivo"])
        for chave in (
            "aplicacao_sinais",
            "altera_calibracao",
            "altera_prioridade",
            "promocao_automatica",
            "reativacao_automatica",
            "telegram",
        ):
            self.assertIs(falha[chave], False)

    def test_execucao_em_andamento_expira(self):
        self.assertEqual("em_execucao", classificar_execucao(
            "em_execucao", 599.9
        ))
        self.assertEqual("interrompida", classificar_execucao(
            "em_execucao", 600.1
        ))
        self.assertEqual("invalida", classificar_execucao(
            "desconhecida", 0
        ))
        self.assertEqual("invalida", classificar_execucao(
            "em_execucao", None
        ))

    def test_cronologia_concluida_valida_e_recalculada(self):
        resultado = auditar_cronologia_execucao({
            "estado_execucao": "concluida",
            "iniciado_em": "2026-09-10T09:59:58",
            "finalizado_em": "2026-09-10T10:00:00",
            "atualizado_em": "2026-09-10T10:00:00",
            "duracao_segundos": 1.75,
        }, agora=datetime(2026, 9, 10, 10, 0, 30))

        self.assertTrue(resultado["valida"])
        self.assertEqual([], resultado["problemas"])
        self.assertEqual(30.0, resultado["idade_segundos"])
        self.assertEqual(2.0, resultado["duracao_parede_segundos"])
        self.assertEqual(1.75, resultado["duracao_monotonic_segundos"])

    def test_cronologia_futura_nao_parece_fresca(self):
        resultado = auditar_cronologia_execucao({
            "estado_execucao": "concluida",
            "iniciado_em": "2026-09-10T10:02:00",
            "finalizado_em": "2026-09-10T10:02:01",
            "atualizado_em": "2026-09-10T10:02:01",
            "duracao_segundos": 1.0,
        }, agora=datetime(2026, 9, 10, 10, 0, 0))

        self.assertFalse(resultado["valida"])
        self.assertEqual(121.0, resultado["desvio_futuro_segundos"])
        self.assertIn("atualizado_em_futuro", resultado["problemas"])
        self.assertIn("iniciado_em_futuro", resultado["problemas"])
        self.assertIn("finalizado_em_futuro", resultado["problemas"])

    def test_cronologia_impossivel_e_duracao_invalida(self):
        resultado = auditar_cronologia_execucao({
            "estado_execucao": "concluida",
            "iniciado_em": "2026-09-10T09:59:59",
            "finalizado_em": "2026-09-10T09:59:58",
            "atualizado_em": "2026-09-10T10:00:00",
            "duracao_segundos": float("nan"),
        }, agora=datetime(2026, 9, 10, 10, 0, 1))

        self.assertFalse(resultado["valida"])
        self.assertIn("finalizacao_anterior_inicio", resultado["problemas"])
        self.assertIn(
            "finalizacao_divergente_atualizacao", resultado["problemas"]
        )
        self.assertIn("duracao_segundos_invalida", resultado["problemas"])

    def test_normalizador_sobrescreve_todo_efeito_operacional(self):
        resultado = aplicar_efeitos_desativados({
            chave: True for chave in EFEITOS_DESATIVADOS
        })

        for chave in EFEITOS_DESATIVADOS:
            self.assertIs(resultado[chave], False)
        self.assertTrue(auditar_efeitos_desativados(resultado)["valida"])

    def test_auditoria_rejeita_efeito_ausente_ou_ativo(self):
        incompleto = dict(EFEITOS_DESATIVADOS)
        incompleto.pop("telegram")
        ativo = dict(EFEITOS_DESATIVADOS)
        ativo["promocao_automatica"] = True

        auditoria_incompleta = auditar_efeitos_desativados(incompleto)
        auditoria_ativa = auditar_efeitos_desativados(ativo)

        self.assertFalse(auditoria_incompleta["valida"])
        self.assertEqual(
            ["telegram"], auditoria_incompleta["campos_ausentes"]
        )
        self.assertFalse(auditoria_ativa["valida"])
        self.assertEqual(
            ["promocao_automatica"],
            auditoria_ativa["campos_invalidos"],
        )


if __name__ == "__main__":
    unittest.main()
