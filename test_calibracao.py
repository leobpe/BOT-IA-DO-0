import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from banco import BancoMonitor
from linhagem_regras import registrar_ou_validar_linhagem_regra
from integridade_calibracao import POPULACAO_CALIBRACAO_EXECUTAVEL
from calibracao import (
    CalibradorBacktest,
    DIMENSOES_CALIBRACAO,
    POLITICA_CALIBRACAO_VERSAO,
    RESULTADOS_CALIBRAVEIS,
    _discriminacao_compativel,
    calibrar_resultados,
    diagnosticar_pre_validacao,
    diagnosticar_validacao_prospectiva_expandida,
    detectar_drift,
    faixa_odd_calibracao,
    faixa_pontuacao,
    hash_modelo_calibracao,
    limite_inferior_wilson,
    serializar_modelo_calibracao,
)


def registrar_modelo_com_historico(
    banco, modelo, mercado="gol_ft", regra_versao="sinais-v1",
    atualizado_em="2026-07-20T12:00:00",
):
    modelo_json = serializar_modelo_calibracao(modelo)
    modelo_hash = hash_modelo_calibracao(modelo)
    amostra = int(modelo.get("amostra") or 0)
    ativa = int(modelo.get("ativa") is True)
    with banco.conexao:
        banco.conexao.execute(
            """
            INSERT INTO calibracoes (
                mercado, regra_versao, atualizado_em,
                amostra, ativa, modelo_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mercado, regra_versao, atualizado_em,
                amostra, ativa, modelo_json,
            ),
        )
        banco.conexao.execute(
            """
            INSERT INTO historico_calibracoes (
                mercado, regra_versao, registrado_em, amostra, ativa,
                amostra_fingerprint, motivo, modelo_hash, modelo_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mercado, regra_versao, atualizado_em, amostra, ativa,
                modelo.get("amostra_fingerprint") or "",
                modelo.get("motivo"), modelo_hash, modelo_json,
            ),
        )


def integridade_coorte_modelo_completa():
    return {
        "estado": "completa",
        "unidades_selecionadas": 100,
        "validas": 100,
        "pendentes": 0,
        "invalidas": 0,
        "devolvidas_contratuais": 0,
        "pendentes_ou_invalidas": 0,
        "motivos": {},
        "selecao_antes_do_resultado": True,
        "exclusao_somente_liquidacao_neutra": True,
        "chave_independencia": "partida_id",
        "ordem_coorte": "criado_em_asc_id_asc",
        "janela": "primeiros",
        "janela_maxima": 300,
        "alvo_validas": 100,
        "criterio_preenchimento": (
            "primeiras_liquidacoes_binarias_executaveis_"
            "sem_escolher_green_red"
        ),
        "populacao": POPULACAO_CALIBRACAO_EXECUTAVEL,
        "cotacao_executavel_obrigatoria": True,
        "fonte_odds_exigida": "betsapi",
        "bookmaker_odds_exigida": "bet365",
    }


def criterios_executaveis():
    return {
        "status": "aprovado",
        "odd_minima": 1.4,
        "odd_maxima": 2.5,
        "resultados": list(RESULTADOS_CALIBRAVEIS),
        "fonte_odds": "betsapi",
        "bookmaker_odds": "bet365",
        "cotacao_entrada_clv_estado": "congelada_v1",
        "cotacao_entrada_clv_schema": "cotacao-entrada-clv-v2",
    }


def candidato_com_cotacao_executavel(candidato, linha=2.5):
    origem = {
        "schema": "origem-mercado-odd-v1",
        "fonte": "betsapi",
        "identificador": "teste-calibracao",
        "nome": "Match Goals",
        "linha": linha,
        "lados": ["over", "under"],
        "bookmaker": "bet365",
    }
    candidato.update({
        "linha": linha,
        "fonte_odds": "betsapi",
        "bookmaker_odds": "bet365",
    })
    candidato["features"] = {
        "fonte_odds": "betsapi",
        "bookmaker_odds": "bet365",
        "cotacao_entrada_clv_estado": "congelada_v1",
        "cotacao_entrada_clv": {
            "schema": "cotacao-entrada-clv-v2",
            "mercado": candidato["mercado"],
            "fonte": "betsapi",
            "bookmaker": "bet365",
            "coletado_em": "2026-07-20T12:00:00",
            "idade_segundos": 1.0,
            "cache": False,
            "tipo": "binaria",
            "linha": linha,
            "over": candidato["odd"],
            "under": candidato.get("odd_oposta", 2.2),
            "odd_selecionada": candidato["odd"],
            "origem_mercado": origem,
        },
    }
    return candidato


class CalibracaoTest(unittest.TestCase):
    def test_reconcilia_calibracao_inativa_desatualizada(self):
        banco = Mock()
        calibrador = CalibradorBacktest(banco)
        with patch(
            "calibracao.auditar_frescor_calibracoes",
            return_value={
                "saudavel": False,
                "detalhes": [{"ativa": False, "desatualizada": True}],
            },
        ), patch.object(
            calibrador,
            "recalibrar",
            return_value={"amostra": 100, "ativa": False},
        ) as recalibrar:
            resultado = calibrador.reconciliar_se_desatualizado(
                "gol_ft", "sinais-v6"
            )

        self.assertEqual(resultado["amostra"], 100)
        recalibrar.assert_called_once_with("gol_ft", "sinais-v6")

    def test_nao_regrava_calibracao_que_ja_esta_atualizada(self):
        banco = Mock()
        calibrador = CalibradorBacktest(banco)
        with patch(
            "calibracao.auditar_frescor_calibracoes",
            return_value={
                "saudavel": True,
                "detalhes": [{"ativa": False, "desatualizada": False}],
            },
        ), patch.object(calibrador, "recalibrar") as recalibrar:
            resultado = calibrador.reconciliar_se_desatualizado(
                "gol_ft", "sinais-v6"
            )

        self.assertIsNone(resultado)
        recalibrar.assert_not_called()
    def test_diagnostico_sombra_so_existe_entre_30_e_99(self):
        base = [{
            "pontuacao_tecnica": 80,
            "odd": 1.8,
            "resultado": "green",
            "retorno_unidades": 0.8,
        }]
        self.assertIsNone(diagnosticar_pre_validacao(base * 29))
        self.assertIsNone(diagnosticar_pre_validacao(base * 100))

    def test_diagnostico_sombra_e_cronologico_e_nao_ativavel(self):
        resultados = []
        for indice in range(30):
            green = indice % 3 != 0
            resultados.append({
                "pontuacao_tecnica": 85 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })

        sombra = diagnosticar_pre_validacao(resultados)

        self.assertEqual(sombra["estado"], "sombra_nao_ativavel")
        self.assertFalse(sombra["habilita_sinal_oficial"])
        self.assertEqual(sombra["etapa"], "formando_desenvolvimento")
        self.assertEqual(sombra["amostra_desenvolvimento"], 30)
        self.assertEqual(sombra["amostra_validacao"], 0)
        self.assertEqual(sombra["desenvolvimento_faltante"], 40)
        self.assertEqual(sombra["validacao_faltante"], 30)
        self.assertIsNone(sombra["roi_validacao_agregado"])
        self.assertEqual(
            sombra["tendencia_provisoria"], "aguardando_validacao"
        )
        self.assertEqual(sombra["motivos_tendencia"], [])
        self.assertIn("80-89|1.70-1.99", sombra["celulas_observadas"])
        self.assertNotIn("probabilidades", sombra)

    def test_diagnostico_previo_preserva_primeiros_setenta(self):
        resultados = []
        for indice in range(99):
            green = indice % 3 != 0
            resultados.append({
                "id": indice + 1,
                "pontuacao_tecnica": 85 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })

        parcial_71 = diagnosticar_pre_validacao(resultados[:71])
        parcial_99 = diagnosticar_pre_validacao(resultados)

        self.assertEqual(parcial_71["etapa"], "validacao_parcial")
        self.assertEqual(parcial_71["amostra_desenvolvimento"], 70)
        self.assertEqual(parcial_71["amostra_validacao"], 1)
        self.assertEqual(parcial_99["amostra_desenvolvimento"], 70)
        self.assertEqual(parcial_99["amostra_validacao"], 29)
        self.assertEqual(parcial_99["validacao_faltante"], 1)
        self.assertEqual(
            parcial_71["celulas_observadas"][
                "80-89|1.70-1.99"
            ]["desenvolvimento_total"],
            parcial_99["celulas_observadas"][
                "80-89|1.70-1.99"
            ]["desenvolvimento_total"],
        )

    def test_diagnostico_sombra_explica_tendencia_sem_ativar(self):
        resultados = []
        for indice in range(70):
            green = indice % 2 == 0
            resultados.append({
                "pontuacao_tecnica": 85 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })
        for indice in range(20):
            green = indice % 2 == 0
            resultados.append({
                "pontuacao_tecnica": 80 if green else 90,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })

        sombra = diagnosticar_pre_validacao(resultados)

        self.assertEqual(
            sombra["tendencia_provisoria"],
            "desfavoravel_no_recorte_atual",
        )
        self.assertIn("auc_abaixo_minimo", sombra["motivos_tendencia"])
        self.assertIn(
            "limite_inferior_auc_abaixo_minimo",
            sombra["motivos_tendencia"],
        )
        self.assertIn("roi_nao_positivo", sombra["motivos_tendencia"])
        self.assertFalse(sombra["habilita_sinal_oficial"])

    def test_nao_calibra_com_amostra_pequena(self):
        resultado = calibrar_resultados(
            [{"pontuacao_tecnica": 80, "resultado": "green"}] * 99
        )
        self.assertFalse(resultado["ativa"])
        self.assertEqual(resultado["motivo"], "amostra_insuficiente")

    def test_auc_corrompida_ou_sem_confianca_falha_fechada(self):
        self.assertFalse(_discriminacao_compativel({
            "auc": "inválida", "limite_inferior_auc_95": 0.6,
            "amostra": 30,
        }))
        self.assertFalse(_discriminacao_compativel({
            "auc": 0.70, "limite_inferior_auc_95": 0.49,
            "amostra": 100,
        }))

    def test_nao_calibra_quando_notas_maiores_ordenam_piores_resultados(self):
        resultados = []
        for indice in range(140):
            green = indice % 2 == 0
            resultados.append({
                "pontuacao_tecnica": 70 if green else 90,
                "odd": 2.5,
                "resultado": "green" if green else "red",
                "retorno_unidades": 1.5 if green else -1.0,
            })

        calibracao = calibrar_resultados(resultados)

        self.assertFalse(calibracao["ativa"])
        self.assertEqual(
            calibracao["motivo"], "pontuacao_sem_discriminacao"
        )
        self.assertEqual(calibracao["discriminacao_pontuacao"]["auc"], 0.0)

    def test_calibra_com_validacao_cronologica_compativel(self):
        resultados = []
        for indice in range(140):
            green = indice % 4 != 0
            resultados.append(
                {
                    "pontuacao_tecnica": 85 if green else 80,
                    "resultado": "green" if green else "red",
                    "retorno_unidades": (
                        0.8 if green else -1.0
                    ),
                    "odd": 1.8,
                }
            )
        calibracao = calibrar_resultados(resultados)
        self.assertTrue(calibracao["ativa"])
        self.assertGreaterEqual(calibracao["amostra_validacao"], 30)
        celula = "80-89|1.70-1.99"
        self.assertIn(celula, calibracao["probabilidades"])
        self.assertLess(
            calibracao["probabilidades_conservadoras"][celula],
            calibracao["probabilidades"][celula],
        )
        self.assertGreaterEqual(
            calibracao["validacao_por_faixa"][celula]["total"], 10
        )
        self.assertGreater(
            calibracao["validacao_por_faixa"][celula]["roi_validacao"], 0
        )
        self.assertEqual(
            calibracao["probabilidades_conservadoras"][celula],
            min(
                calibracao["limites_wilson_desenvolvimento"][celula],
                calibracao["limites_wilson_validacao"][celula],
            ),
        )

    def test_confianca_usa_menor_wilson_da_validacao_posterior(self):
        resultados = []
        for indice in range(70):
            green = indice < 56
            resultados.append(
                {
                    "pontuacao_tecnica": 89 if green else 80,
                    "odd": 1.8,
                    "resultado": "green" if green else "red",
                    "retorno_unidades": 0.8 if green else -1.0,
                }
            )
        for indice in range(30):
            green = indice < 21
            resultados.append(
                {
                    "pontuacao_tecnica": 89 if green else 80,
                    "odd": 1.8,
                    "resultado": "green" if green else "red",
                    "retorno_unidades": 0.8 if green else -1.0,
                }
            )

        calibracao = calibrar_resultados(resultados)
        celula = "80-89|1.70-1.99"

        self.assertTrue(calibracao["ativa"])
        self.assertLess(
            calibracao["limites_wilson_validacao"][celula],
            calibracao["limites_wilson_desenvolvimento"][celula],
        )
        self.assertEqual(
            calibracao["probabilidades_conservadoras"][celula],
            calibracao["limites_wilson_validacao"][celula],
        )

    def test_resultados_posteriores_nao_reabrem_janela_oficial(self):
        resultados = []
        for indice in range(100):
            green = (
                indice < 49 if indice < 70 else indice - 70 < 21
            )
            resultados.append({
                "id": indice + 1,
                "partida_id": indice + 1,
                "pontuacao_tecnica": 89 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
                "encerrado_em": f"2026-07-{indice // 24 + 1:02d}"
                f"T{indice % 24:02d}:00:00",
            })
        inicial = calibrar_resultados(resultados)
        posteriores = [
            {
                **resultados[-1],
                "id": 101 + indice,
                "partida_id": 101 + indice,
                "resultado": "red",
                "retorno_unidades": -1.0,
            }
            for indice in range(40)
        ]

        depois = calibrar_resultados(resultados + posteriores)

        self.assertEqual(inicial, depois)
        self.assertEqual(depois["amostra"], 100)
        self.assertEqual(depois["amostra_validacao"], 30)

    def test_validacao_expandida_usa_futuro_sem_promover_automaticamente(self):
        resultados = []
        for indice in range(70):
            green = indice < 49
            resultados.append({
                "id": indice + 1,
                "partida_id": indice + 1,
                "pontuacao_tecnica": 89 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })
        for indice in range(30):
            green = indice < 12
            resultados.append({
                "id": 71 + indice,
                "partida_id": 71 + indice,
                "pontuacao_tecnica": 89 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })
        resultados.extend({
            "id": 101 + indice,
            "partida_id": 101 + indice,
            "pontuacao_tecnica": 89,
            "odd": 1.8,
            "resultado": "green",
            "retorno_unidades": 0.8,
        } for indice in range(70))

        oficial = calibrar_resultados(resultados)
        expandida = diagnosticar_validacao_prospectiva_expandida(
            resultados
        )

        self.assertFalse(oficial["ativa"])
        self.assertEqual(oficial["motivo"], "faixas_sem_validacao")
        self.assertEqual(expandida["amostra_validacao"], 100)
        self.assertEqual(expandida["resultados_apos_holdout_original"], 70)
        self.assertEqual(
            expandida["estado"],
            "favoravel_para_revisao_independente",
        )
        self.assertFalse(expandida["habilita_sinal_oficial"])
        self.assertFalse(expandida["promocao_automatica"])

    def test_validacao_expandida_preserva_evidencia_desfavoravel(self):
        resultados = []
        for indice in range(70):
            green = indice < 49
            resultados.append({
                "pontuacao_tecnica": 89 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })
        for indice in range(60):
            green = indice < 20
            resultados.append({
                "pontuacao_tecnica": 89 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })

        expandida = diagnosticar_validacao_prospectiva_expandida(
            resultados
        )

        self.assertEqual(
            expandida["estado"], "evidencia_atual_desfavoravel"
        )
        self.assertIn(
            "roi_agregado_nao_positivo", expandida["motivos"]
        )
        self.assertFalse(expandida["habilita_sinal_oficial"])

    def test_faixa_superior_termina_em_cem(self):
        self.assertEqual(faixa_pontuacao(100), "90-100")

    def test_faixas_de_odd_sao_pre_definidas(self):
        self.assertEqual(faixa_odd_calibracao(1.4), "1.40-1.69")
        self.assertEqual(faixa_odd_calibracao(1.7), "1.70-1.99")
        self.assertEqual(faixa_odd_calibracao(2.0), "2.00-2.50")
        self.assertEqual(faixa_odd_calibracao(2.5), "2.00-2.50")

    def test_celula_com_roi_negativo_na_validacao_nao_ativa(self):
        resultados = []
        for indice in range(140):
            green = indice % 5 < 3
            resultados.append(
                {
                    "pontuacao_tecnica": 85 if green else 80,
                    "odd": 1.4,
                    "resultado": "green" if green else "red",
                    "retorno_unidades": 0.4 if green else -1.0,
                }
            )
        calibracao = calibrar_resultados(resultados)
        self.assertFalse(calibracao["ativa"])
        self.assertEqual(calibracao["motivo"], "faixas_sem_validacao")
        celula = calibracao["validacao_por_faixa"]["80-89|1.40-1.69"]
        self.assertFalse(celula["aprovada"])
        self.assertIn("roi_nao_positivo", celula["motivos_reprovacao"])

    def test_cem_resultados_ruins_nao_ativam_so_por_quantidade(self):
        resultados = []
        for indice in range(100):
            posicao_validacao = indice - 70
            if indice < 70:
                green = indice < 42
            else:
                green = posicao_validacao < 18
            resultados.append({
                "pontuacao_tecnica": 89 if green else 80,
                "odd": 1.4,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.4 if green else -1.0,
            })

        calibracao = calibrar_resultados(resultados)

        self.assertFalse(calibracao["ativa"])
        self.assertEqual(calibracao["amostra"], 100)
        self.assertEqual(calibracao["motivo"], "faixas_sem_validacao")
        celula = calibracao["validacao_por_faixa"][
            "80-89|1.40-1.69"
        ]
        self.assertGreater(
            calibracao["discriminacao_pontuacao"]["auc"], 0.55
        )
        self.assertEqual(calibracao["roi_validacao_agregado"], -0.16)
        self.assertLess(celula["roi_validacao"], 0)
        self.assertIn("roi_nao_positivo", celula["motivos_reprovacao"])

    def test_cem_resultados_so_ativam_com_validacao_de_qualidade(self):
        resultados = []
        for indice in range(100):
            posicao_validacao = indice - 70
            if indice < 70:
                green = indice < 49
            else:
                green = posicao_validacao < 21
            resultados.append({
                "pontuacao_tecnica": 89 if green else 80,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })

        calibracao = calibrar_resultados(resultados)

        self.assertTrue(calibracao["ativa"])
        self.assertEqual(calibracao["amostra"], 100)
        self.assertEqual(calibracao["amostra_validacao"], 30)
        self.assertGreater(calibracao["roi_validacao_agregado"], 0)
        self.assertGreaterEqual(
            calibracao["discriminacao_pontuacao"]["auc"], 0.55
        )

    def test_amostra_direta_nao_converte_retorno_invalido_em_zero(self):
        resultados = []
        for indice in range(100):
            green = indice % 2 == 0
            resultados.append({
                "pontuacao_tecnica": 90 if green else 75,
                "odd": 1.8,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.8 if green else -1.0,
            })
        resultados[0]["retorno_unidades"] = None

        calibracao = calibrar_resultados(resultados)

        self.assertFalse(calibracao["ativa"])
        self.assertEqual(calibracao["motivo"], "amostra_invalida")
        self.assertEqual(
            calibracao["integridade_entrada"]["motivos"],
            {"retorno_ausente_ou_invalido": 1},
        )

    def test_nao_ativa_com_apenas_greens(self):
        resultado = calibrar_resultados(
            [{"pontuacao_tecnica": 90, "resultado": "green"}] * 150
        )
        self.assertFalse(resultado["ativa"])
        self.assertEqual(resultado["motivo"], "resultados_desbalanceados")

    def test_reprovacao_desbalanceada_preserva_metricas_da_validacao(self):
        resultados = []
        for indice in range(70):
            green = indice % 2 == 0
            resultados.append({
                "pontuacao_tecnica": 90 if green else 75,
                "odd": 1.50,
                "mercado": "gol_ft",
                "linha": 2.5,
                "resultado": "green" if green else "red",
                "retorno_unidades": 0.5 if green else -1.0,
            })
        resultados.extend({
            "pontuacao_tecnica": 90,
            "odd": 1.50,
            "mercado": "gol_ft",
            "linha": 2.5,
            "resultado": "green",
            "retorno_unidades": 0.5,
        } for _ in range(30))

        calibracao = calibrar_resultados(resultados)

        self.assertFalse(calibracao["ativa"])
        self.assertEqual(calibracao["motivo"], "validacao_desbalanceada")
        self.assertEqual(calibracao["amostra_validacao"], 30)
        self.assertEqual(calibracao["greens_validacao"], 30)
        self.assertEqual(calibracao["reds_validacao"], 0)
        self.assertEqual(calibracao["roi_validacao_agregado"], 0.5)
        self.assertIn("discriminacao_pontuacao", calibracao)

    def test_limite_wilson_e_conservador_com_amostra_pequena(self):
        self.assertLess(limite_inferior_wilson(15, 15), 1.0)
        self.assertGreater(limite_inferior_wilson(100, 100), 0.95)

    def test_calibrador_conta_uma_observacao_por_partida(self):
        caminho = Path.cwd() / ".teste_calibracao_independente.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        banco = BancoMonitor(caminho)
        try:
            linhagem = registrar_ou_validar_linhagem_regra(
                banco.conexao, Path.cwd(), "sinais-v1", "features-v1"
            )
            snapshot = banco.salvar_registro(
                {
                    "coletado_em": "2026-07-20T12:00:00",
                    "url": "https://packball.com/match/1/live",
                    "mandante": "A",
                    "visitante": "B",
                    "placar": "0-0",
                    "status": "20 '",
                }
            )
            partida_id = banco.conexao.execute(
                "SELECT partida_id FROM snapshots WHERE id=?", (snapshot,)
            ).fetchone()[0]
            with banco.conexao:
                for indice, odd in enumerate((1.28, 1.8, 1.9)):
                    prova = candidato_com_cotacao_executavel({
                        "mercado": "gol_ft",
                        "odd": odd,
                        "odd_oposta": 2.2,
                    })
                    cursor = banco.conexao.execute(
                        """
                        INSERT INTO sinais (
                            partida_id, snapshot_id, criado_em, mercado,
                            linha, odd, pontuacao_tecnica, regra_versao,
                            regra_fingerprint, status, features_json
                        ) VALUES (
                            ?, ?, ?, 'gol_ft', 2.5, ?, 80,
                            'sinais-v1', ?, 'aprovado', ?
                        )
                        """,
                        (
                            partida_id,
                            snapshot,
                            f"2026-07-20T12:0{indice}:00",
                            odd,
                            linhagem["fingerprint_atual"],
                            json.dumps(prova["features"]),
                        ),
                    )
                    banco.conexao.execute(
                        """
                        INSERT INTO resultados_sinais (
                            sinal_id, encerrado_em, resultado, retorno_unidades
                        ) VALUES (?, ?, 'green', 0.8)
                        """,
                        (cursor.lastrowid, f"2026-07-20T13:0{indice}:00"),
                    )
            resultado = CalibradorBacktest(banco).recalibrar(
                "gol_ft", "sinais-v1"
            )
            self.assertEqual(resultado["amostra"], 1)
            self.assertEqual(resultado["unidade_amostral"], "partida_unica")
            self.assertEqual(
                resultado["populacao"], POPULACAO_CALIBRACAO_EXECUTAVEL
            )
            self.assertEqual(
                resultado["criterios_elegibilidade"]["odd_minima"], 1.4
            )
            self.assertEqual(len(resultado["modelo_hash"]), 64)
            CalibradorBacktest(banco).recalibrar("gol_ft", "sinais-v1")
            historico = banco.conexao.execute(
                """
                SELECT COUNT(*), MIN(modelo_hash), MAX(modelo_hash)
                FROM historico_calibracoes
                WHERE mercado='gol_ft' AND regra_versao='sinais-v1'
                """
            ).fetchone()
            self.assertEqual(historico[0], 1)
            self.assertEqual(historico[1], historico[2])
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                arquivo = Path(str(caminho) + sufixo)
                if arquivo.exists():
                    arquivo.unlink()

    def test_detecta_deterioracao_temporal_com_roi_negativo(self):
        historico = [
            {
                "pontuacao_tecnica": 85,
                "resultado": "green" if indice % 10 else "red",
                "retorno_unidades": 0.8 if indice % 10 else -1.0,
            }
            for indice in range(100)
        ]
        recentes = [
            {
                "pontuacao_tecnica": 85,
                "resultado": "green" if indice < 12 else "red",
                "retorno_unidades": 0.8 if indice < 12 else -1.0,
            }
            for indice in range(30)
        ]
        drift = detectar_drift(historico + recentes)
        self.assertTrue(drift["detectado"])
        self.assertLess(drift["roi_recente"], 0)

    def test_nao_declara_drift_sem_janela_suficiente(self):
        drift = detectar_drift(
            [{"resultado": "red", "retorno_unidades": -1}] * 59
        )
        self.assertFalse(drift["detectado"])
        self.assertEqual(drift["motivo"], "amostra_recente_insuficiente")

    def test_aplicacao_recusa_modelo_ativo_com_politica_legada(self):
        caminho = Path.cwd() / ".teste_calibracao_politica.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        banco = BancoMonitor(caminho)
        try:
            modelo = {
                "ativa": True,
                "amostra": 100,
                "probabilidades_conservadoras": {"80-89": 0.8},
            }
            registrar_modelo_com_historico(banco, modelo)
            candidato = {
                "mercado": "gol_ft",
                "regra_versao": "sinais-v1",
                "pontuacao_tecnica": 85,
                "odd": 1.8,
                "odd_oposta": 2.2,
                "odd_par_sincronizado": True,
            }
            with patch(
                "calibracao.auditar_frescor_calibracoes",
                return_value={"saudavel": True},
            ):
                CalibradorBacktest(banco).aplicar(candidato)
            self.assertIsNone(candidato["probabilidade_calibrada"])
            self.assertEqual(
                candidato["motivo_sem_calibracao"],
                "modelo_politica_incompativel",
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                arquivo = Path(str(caminho) + sufixo)
                if arquivo.exists():
                    arquivo.unlink()

    def test_aplicacao_aceita_modelo_com_politica_atual(self):
        caminho = Path.cwd() / ".teste_calibracao_politica_atual.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        banco = BancoMonitor(caminho)
        try:
            modelo = {
                "ativa": True,
                "amostra": 100,
                "amostra_fingerprint": "a" * 64,
                "janela_modelo_fixa": 100,
                "amostra_total_disponivel": 100,
                "amostra_monitoramento": 100,
                "monitoramento_fingerprint": "b" * 64,
                "integridade_coorte_modelo": (
                    integridade_coorte_modelo_completa()
                ),
                "politica_versao": POLITICA_CALIBRACAO_VERSAO,
                "populacao": POPULACAO_CALIBRACAO_EXECUTAVEL,
                "unidade_amostral": "partida_unica",
                "dimensoes": list(DIMENSOES_CALIBRACAO),
                "discriminacao_pontuacao": {
                    "auc": 0.70, "limite_inferior_auc_95": 0.52,
                    "amostra": 30,
                },
                "criterios_elegibilidade": criterios_executaveis(),
                "probabilidades": {"80-89|1.70-1.99": 0.84},
                "probabilidades_conservadoras": {
                    "80-89|1.70-1.99": 0.76
                },
                "limites_wilson_desenvolvimento": {
                    "80-89|1.70-1.99": 0.78
                },
                "limites_wilson_validacao": {
                    "80-89|1.70-1.99": 0.76
                },
            }
            registrar_modelo_com_historico(banco, modelo)
            candidato = {
                "mercado": "gol_ft",
                "regra_versao": "sinais-v1",
                "pontuacao_tecnica": 85,
                "odd": 1.8,
                "odd_oposta": 2.2,
                "odd_par_sincronizado": True,
            }
            candidato_com_cotacao_executavel(candidato)
            with patch(
                "calibracao.auditar_frescor_calibracoes",
                return_value={"saudavel": True},
            ):
                CalibradorBacktest(banco).aplicar(candidato)
            self.assertEqual(candidato["probabilidade_observada"], 0.84)
            self.assertEqual(candidato["probabilidade_calibrada"], 0.76)
            self.assertAlmostEqual(
                0.368, candidato["valor_esperado_conservador"]
            )
            self.assertTrue(
                candidato["features"]["valor_mercado_conservador"][
                    "aprovado"
                ]
            )
            self.assertNotIn("motivo_sem_calibracao", candidato)

            agregado = {
                "mercado": "gol_ft",
                "regra_versao": "sinais-v1",
                "pontuacao_tecnica": 85,
                "linha": 2.5,
                "odd": 1.8,
                "features": {
                    "fonte_odds": "packball",
                    "bookmaker_odds": None,
                },
            }
            with patch(
                "calibracao.auditar_frescor_calibracoes",
                return_value={"saudavel": True},
            ):
                CalibradorBacktest(banco).aplicar(agregado)
            self.assertIsNone(agregado["probabilidade_calibrada"])
            self.assertEqual(
                agregado["motivo_sem_calibracao"],
                "cotacao_executavel_incompativel_com_modelo",
            )
            self.assertFalse(
                agregado["features"][
                    "transferencia_calibracao_execucao"
                ]["apta"]
            )

            modelo_sem_registro = dict(modelo)
            modelo_sem_registro["motivo"] = "modelo_nao_registrado"
            banco.conexao.execute(
                """
                UPDATE calibracoes SET modelo_json=?
                WHERE mercado='gol_ft' AND regra_versao='sinais-v1'
                """,
                (serializar_modelo_calibracao(modelo_sem_registro),),
            )
            banco.conexao.commit()
            sem_historico = dict(candidato)
            with patch(
                "calibracao.auditar_frescor_calibracoes",
                return_value={"saudavel": True},
            ):
                CalibradorBacktest(banco).aplicar(sem_historico)
            self.assertIsNone(sem_historico["probabilidade_calibrada"])
            self.assertEqual(
                sem_historico["motivo_sem_calibracao"],
                "modelo_sem_historico_imutavel",
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                arquivo = Path(str(caminho) + sufixo)
                if arquivo.exists():
                    arquivo.unlink()

    def test_aplicacao_recusa_modelo_ativo_desatualizado(self):
        caminho = Path.cwd() / ".teste_calibracao_desatualizada.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        banco = BancoMonitor(caminho)
        try:
            celula = "80-89|1.70-1.99"
            modelo = {
                "ativa": True,
                "amostra": 100,
                "amostra_fingerprint": "a" * 64,
                "janela_modelo_fixa": 100,
                "amostra_total_disponivel": 100,
                "amostra_monitoramento": 100,
                "monitoramento_fingerprint": "b" * 64,
                "integridade_coorte_modelo": (
                    integridade_coorte_modelo_completa()
                ),
                "politica_versao": POLITICA_CALIBRACAO_VERSAO,
                "populacao": POPULACAO_CALIBRACAO_EXECUTAVEL,
                "unidade_amostral": "partida_unica",
                "dimensoes": list(DIMENSOES_CALIBRACAO),
                "discriminacao_pontuacao": {
                    "auc": 0.70, "limite_inferior_auc_95": 0.52,
                    "amostra": 30,
                },
                "criterios_elegibilidade": criterios_executaveis(),
                "probabilidades": {celula: 0.84},
                "probabilidades_conservadoras": {celula: 0.76},
                "limites_wilson_desenvolvimento": {celula: 0.78},
                "limites_wilson_validacao": {celula: 0.76},
            }
            registrar_modelo_com_historico(banco, modelo)
            candidato = {
                "mercado": "gol_ft",
                "regra_versao": "sinais-v1",
                "pontuacao_tecnica": 85,
                "odd": 1.8,
            }

            CalibradorBacktest(banco).aplicar(candidato)

            self.assertIsNone(candidato["probabilidade_calibrada"])
            self.assertEqual(
                candidato["motivo_sem_calibracao"],
                "modelo_desatualizado",
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                arquivo = Path(str(caminho) + sufixo)
                if arquivo.exists():
                    arquivo.unlink()

    def test_aplicacao_recusa_wilson_duplo_incoerente(self):
        caminho = Path.cwd() / ".teste_calibracao_wilson_incoerente.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        banco = BancoMonitor(caminho)
        try:
            celula = "80-89|1.70-1.99"
            modelo = {
                "ativa": True,
                "politica_versao": POLITICA_CALIBRACAO_VERSAO,
                "populacao": "sinais_elegiveis_para_alerta",
                "unidade_amostral": "partida_unica",
                "dimensoes": list(DIMENSOES_CALIBRACAO),
                "criterios_elegibilidade": {
                    "status": "aprovado",
                    "odd_minima": 1.4,
                    "odd_maxima": 2.5,
                    "resultados": list(RESULTADOS_CALIBRAVEIS),
                },
                "probabilidades": {celula: 0.84},
                "probabilidades_conservadoras": {celula: 0.80},
                "limites_wilson_desenvolvimento": {celula: 0.78},
                "limites_wilson_validacao": {celula: 0.76},
            }
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO calibracoes (
                        mercado, regra_versao, atualizado_em,
                        amostra, ativa, modelo_json
                    ) VALUES ('gol_ft', 'sinais-v1', ?, 100, 1, ?)
                    """,
                    ("2026-07-20T12:00:00", json.dumps(modelo)),
                )
            candidato = {
                "mercado": "gol_ft",
                "regra_versao": "sinais-v1",
                "pontuacao_tecnica": 85,
                "odd": 1.8,
            }

            CalibradorBacktest(banco).aplicar(candidato)

            self.assertIsNone(candidato["probabilidade_calibrada"])
            self.assertEqual(
                candidato["motivo_sem_calibracao"],
                "modelo_politica_incompativel",
            )
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                arquivo = Path(str(caminho) + sufixo)
                if arquivo.exists():
                    arquivo.unlink()


if __name__ == "__main__":
    unittest.main()
