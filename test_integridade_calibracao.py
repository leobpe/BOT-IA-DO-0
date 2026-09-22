import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from backtest import AvaliadorBacktest
from banco import BancoMonitor
from calibracao import CalibradorBacktest
from configuracao import obter_limites_risco
from integridade_calibracao import (
    auditar_diversidade_amostra_calibracao,
    auditar_particao_temporal,
    auditar_particoes_calibracao,
    auditar_particoes_calibracao_por_mercado,
    auditar_frescor_calibracoes,
    auditar_frescor_calibracoes_por_mercado,
    carregar_amostra_independente,
    carregar_coorte_independente,
    fingerprint_amostra,
    resumir_cobertura_amostra_calibracao,
)
from linhagem_regras import registrar_ou_validar_linhagem_regra


class IntegridadeCalibracaoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_integridade_calibracao.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.linhagem = registrar_ou_validar_linhagem_regra(
            self.banco.conexao, Path.cwd(), "sinais-v3", "features-v2"
        )

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    def _criar_resultado(self):
        inicial = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-21T12:00:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-0",
                "status": "60 '",
            }
        )
        self.banco.salvar_candidatos(
            inicial,
            [{
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": "sinais-v3",
                "regra_fingerprint": self.linhagem["fingerprint_atual"],
                "status": "aprovado",
            }],
            datetime(2026, 7, 21, 12, 0),
        )
        final = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-21T13:00:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "1-0",
                "status": "Finalizado",
            }
        )
        AvaliadorBacktest(self.banco).avaliar_snapshot(final)

    def _inserir_sinal_calibracao(
        self,
        sufixo,
        criado_em,
        *,
        partida_id=None,
        resultado=None,
        retorno=None,
        encerrado_em=None,
        odd=1.8,
        executavel=True,
    ):
        if partida_id is None:
            snapshot = self.banco.salvar_registro({
                "coletado_em": criado_em,
                "url": f"https://packball.com/match/coorte-{sufixo}/live",
                "mandante": f"A{sufixo}",
                "visitante": f"B{sufixo}",
                "placar": "0-0",
                "status": "20 '",
            })
            partida_id = int(self.banco.conexao.execute(
                "SELECT partida_id FROM snapshots WHERE id=?", (snapshot,)
            ).fetchone()[0])
        else:
            snapshot = int(self.banco.conexao.execute(
                "SELECT MIN(id) FROM snapshots WHERE partida_id=?",
                (partida_id,),
            ).fetchone()[0])
        origem = {
            "schema": "origem-mercado-odd-v1",
            "fonte": "betsapi",
            "identificador": f"teste-{sufixo}",
            "nome": "Match Goals",
            "linha": 0.5,
            "lados": ["over", "under"],
            "bookmaker": "bet365",
        }
        features = (
            {
                "fonte_odds": "betsapi",
                "bookmaker_odds": "bet365",
                "cotacao_entrada_clv_estado": "congelada_v1",
                "cotacao_entrada_clv": {
                    "schema": "cotacao-entrada-clv-v2",
                    "mercado": "gol_ft",
                    "fonte": "betsapi",
                    "bookmaker": "bet365",
                    "coletado_em": criado_em,
                    "idade_segundos": 1.0,
                    "cache": False,
                    "tipo": "binaria",
                    "linha": 0.5,
                    "over": odd,
                    "under": 2.0,
                    "odd_selecionada": odd,
                    "origem_mercado": origem,
                },
            }
            if executavel else {
                "fonte_odds": "packball",
                "bookmaker_odds": None,
            }
        )
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO sinais (
                    partida_id, snapshot_id, criado_em, mercado, linha, odd,
                    pontuacao_tecnica, regra_versao, regra_fingerprint,
                    status, features_json
                ) VALUES (?, ?, ?, 'gol_ft', 0.5, ?, 80, 'sinais-v3', ?,
                          'aprovado', ?)
                """,
                (
                    partida_id,
                    snapshot,
                    criado_em,
                    odd,
                    self.linhagem["fingerprint_atual"],
                    json.dumps(features),
                ),
            )
            sinal_id = int(cursor.lastrowid)
            if resultado is not None:
                self.banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado, retorno_unidades
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        sinal_id,
                        encerrado_em or criado_em,
                        resultado,
                        retorno,
                    ),
                )
        return sinal_id, partida_id

    def test_coorte_executavel_nao_perde_bet365_por_leitura_agregada_anterior(self):
        primeiro, partida_id = self._inserir_sinal_calibracao(
            "agregado-primeiro",
            "2026-07-21T12:00:00",
            resultado="green",
            retorno=0.8,
            encerrado_em="2026-07-21T13:00:00",
            executavel=False,
        )
        segundo, _ = self._inserir_sinal_calibracao(
            "bet365-depois",
            "2026-07-21T12:01:00",
            partida_id=partida_id,
            resultado="green",
            retorno=0.8,
            encerrado_em="2026-07-21T13:01:00",
        )

        coorte = carregar_coorte_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
            janela_maxima=1,
            janela="primeiros",
            somente_executaveis=True,
        )

        self.assertNotEqual(primeiro, segundo)
        self.assertEqual(coorte["validas"][0]["id"], segundo)
        self.assertTrue(
            coorte["diagnostico"]["cotacao_executavel_obrigatoria"]
        )
        self.assertEqual(coorte["diagnostico"]["fonte_odds_exigida"], "betsapi")
        self.assertEqual(coorte["diagnostico"]["bookmaker_odds_exigida"], "bet365")
        self.assertEqual(len(coorte["validas"][0]["custodia_cotacao_hash"]), 64)

    def test_coorte_executavel_falha_fechada_se_prova_for_adulterada(self):
        sinal_id, _ = self._inserir_sinal_calibracao(
            "prova-adulterada",
            "2026-07-21T12:00:00",
            resultado="green",
            retorno=0.8,
            encerrado_em="2026-07-21T13:00:00",
        )
        linha = self.banco.conexao.execute(
            "SELECT features_json FROM sinais WHERE id=?", (sinal_id,)
        ).fetchone()
        features = json.loads(linha[0])
        features["cotacao_entrada_clv"]["over"] = 1.9
        with self.banco.conexao:
            self.banco.conexao.execute(
                "UPDATE sinais SET features_json=? WHERE id=?",
                (json.dumps(features), sinal_id),
            )

        coorte = carregar_coorte_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
            janela_maxima=1,
            janela="primeiros",
            somente_executaveis=True,
        )

        self.assertEqual(coorte["validas"], [])
        self.assertEqual(coorte["diagnostico"]["custodias_invalidas"], 1)
        self.assertEqual(coorte["diagnostico"]["estado"], "liquidacoes_invalidas")

    def test_coorte_escolhe_primeira_exposicao_antes_do_resultado(self):
        primeiro, partida_id = self._inserir_sinal_calibracao(
            "causal", "2026-07-21T12:00:00"
        )
        segundo, _ = self._inserir_sinal_calibracao(
            "causal-2",
            "2026-07-21T12:01:00",
            partida_id=partida_id,
            resultado="green",
            retorno=0.8,
            encerrado_em="2026-07-21T13:00:00",
        )

        coorte = carregar_coorte_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
            janela_maxima=1,
            janela="primeiros",
        )

        self.assertEqual(coorte["unidades"][0]["id"], primeiro)
        self.assertNotEqual(coorte["unidades"][0]["id"], segundo)
        self.assertEqual(coorte["validas"], [])
        self.assertEqual(
            coorte["diagnostico"]["motivos"], {"resultado_ausente": 1}
        )
        self.assertTrue(
            coorte["diagnostico"]["selecao_antes_do_resultado"]
        )
        calibracao = CalibradorBacktest(self.banco).recalibrar(
            "gol_ft", "sinais-v3"
        )
        self.assertFalse(calibracao["ativa"])
        self.assertEqual(calibracao["motivo"], "coorte_resultados_pendentes")
        self.assertEqual(
            calibracao["integridade_coorte_modelo"]["pendentes"], 1
        )

    def test_coorte_nao_silencia_retorno_incompativel(self):
        sinal_id, _ = self._inserir_sinal_calibracao(
            "retorno-invalido",
            "2026-07-21T12:00:00",
            resultado="green",
            retorno=-1.0,
            encerrado_em="2026-07-21T13:00:00",
        )

        coorte = carregar_coorte_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
            janela_maxima=1,
            janela="primeiros",
        )

        self.assertEqual(coorte["unidades"][0]["id"], sinal_id)
        self.assertEqual(coorte["validas"], [])
        self.assertEqual(
            coorte["diagnostico"]["motivos"],
            {"retorno_incompativel_com_resultado_e_odd": 1},
        )

    def test_coorte_separa_void_sem_dado_e_falha_tecnica(self):
        self._inserir_sinal_calibracao(
            "void",
            "2026-07-21T12:00:00",
            resultado="void",
            retorno=0.0,
            encerrado_em="2026-07-21T13:00:00",
        )
        self._inserir_sinal_calibracao(
            "sem-dado",
            "2026-07-21T12:01:00",
            resultado="sem_dado",
            retorno=0.0,
            encerrado_em="2026-07-21T13:00:00",
        )
        self._inserir_sinal_calibracao(
            "retorno-invalido-granular",
            "2026-07-21T12:02:00",
            resultado="green",
            retorno=-1.0,
            encerrado_em="2026-07-21T13:00:00",
        )

        diagnostico = carregar_coorte_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
            janela_maxima=3,
            janela="primeiros",
        )["diagnostico"]

        self.assertEqual(diagnostico["invalidas"], 2)
        self.assertEqual(diagnostico["devolvidas_contratuais"], 1)
        self.assertEqual(diagnostico["neutras"], 1)
        self.assertEqual(diagnostico["encerradas_sem_dado"], 1)
        self.assertEqual(diagnostico["invalidas_tecnicas"], 1)
        self.assertEqual(diagnostico["pendentes"], 0)
        self.assertEqual(diagnostico["pendentes_ou_invalidas"], 2)

    def test_void_integro_preenche_alvo_sem_escolher_green_ou_red(self):
        self._inserir_sinal_calibracao(
            "antes-void",
            "2026-07-21T12:00:00",
            resultado="green",
            retorno=0.8,
            encerrado_em="2026-07-21T13:00:00",
        )
        self._inserir_sinal_calibracao(
            "void-neutro",
            "2026-07-21T12:01:00",
            resultado="void",
            retorno=0.0,
            encerrado_em="2026-07-21T13:01:00",
        )
        self._inserir_sinal_calibracao(
            "depois-void",
            "2026-07-21T12:02:00",
            resultado="red",
            retorno=-1.0,
            encerrado_em="2026-07-21T13:02:00",
        )

        coorte = carregar_coorte_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
            janela_maxima=3,
            janela="primeiros",
            alvo_validas=2,
        )

        self.assertEqual(len(coorte["unidades"]), 3)
        self.assertEqual(
            [item["resultado"] for item in coorte["validas"]],
            ["green", "red"],
        )
        self.assertEqual(len(coorte["neutras"]), 1)
        self.assertEqual(coorte["diagnostico"]["estado"], "completa")
        self.assertEqual(coorte["diagnostico"]["invalidas"], 0)
        self.assertEqual(
            coorte["diagnostico"]["motivos_neutros"],
            {"resultado_neutro:void": 1},
        )
        self.assertEqual(coorte["diagnostico"]["alvo_validas"], 2)

    def test_void_com_retorno_incoerente_continua_fail_closed(self):
        self._inserir_sinal_calibracao(
            "void-corrompido",
            "2026-07-21T12:00:00",
            resultado="void",
            retorno=0.8,
            encerrado_em="2026-07-21T13:00:00",
        )

        diagnostico = carregar_coorte_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
            janela_maxima=1,
            janela="primeiros",
        )["diagnostico"]

        self.assertEqual(diagnostico["devolvidas_contratuais"], 0)
        self.assertEqual(diagnostico["invalidas"], 1)
        self.assertEqual(diagnostico["invalidas_tecnicas"], 1)
        self.assertEqual(
            diagnostico["motivos"],
            {"retorno_incompativel_com_resultado_e_odd": 1},
        )

    def test_sem_dado_no_prefixo_continua_bloqueando_alvo_preenchido(self):
        for indice, (resultado, retorno) in enumerate((
            ("green", 0.8),
            ("sem_dado", 0.0),
            ("red", -1.0),
        )):
            self._inserir_sinal_calibracao(
                f"prefixo-{indice}",
                f"2026-07-21T12:0{indice}:00",
                resultado=resultado,
                retorno=retorno,
                encerrado_em=f"2026-07-21T13:0{indice}:00",
            )

        coorte = carregar_coorte_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
            janela_maxima=3,
            janela="primeiros",
            alvo_validas=2,
        )

        self.assertEqual(len(coorte["validas"]), 2)
        self.assertEqual(
            coorte["diagnostico"]["estado"], "liquidacoes_invalidas"
        )
        self.assertEqual(coorte["diagnostico"]["invalidas"], 1)
        self.assertEqual(coorte["diagnostico"]["encerradas_sem_dado"], 1)

    def test_diversidade_exige_amostra_dias_e_ligas(self):
        inicio = datetime(2026, 7, 1, 12, 0)
        for indice in range(100):
            instante = inicio + timedelta(days=indice % 7, minutes=indice)
            snapshot = self.banco.salvar_registro({
                "coletado_em": instante,
                "url": f"https://packball.com/match/div-{indice}/live",
                "mandante": f"A{indice}",
                "visitante": f"B{indice}",
                "liga": f"Liga {indice % 5}",
                "placar": "0-0",
                "status": "60 '",
            })
            sinal = self.banco.salvar_candidatos(
                snapshot,
                [{
                    "mercado": "gol_ft",
                    "linha": 0.5,
                    "odd": 1.8,
                    "pontuacao_tecnica": 80,
                    "regra_versao": "sinais-v3",
                    "regra_fingerprint": self.linhagem[
                        "fingerprint_atual"
                    ],
                    "status": "aprovado",
                }],
                instante,
            )[0]
            with self.banco.conexao:
                self.banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, fonte_resultado
                    ) VALUES (?, ?, 'green', 0.8, 'packball')
                    """,
                    (sinal, (instante + timedelta(minutes=30)).isoformat()),
                )

        limites = obter_limites_risco()
        aprovada = auditar_diversidade_amostra_calibracao(
            self.banco.conexao, "gol_ft", "sinais-v3", limites
        )
        poucos_dias = auditar_diversidade_amostra_calibracao(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            limites,
            minimo_dias=8,
        )
        poucas_ligas = auditar_diversidade_amostra_calibracao(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            limites,
            minimo_ligas=6,
        )

        self.assertTrue(aprovada["pronto"])
        self.assertEqual(aprovada["dias_distintos"], 7)
        self.assertEqual(aprovada["ligas_distintas"], 5)
        self.assertEqual(
            poucos_dias["estado"], "diversidade_temporal_insuficiente"
        )
        self.assertEqual(
            poucas_ligas["estado"], "diversidade_ligas_insuficiente"
        )

    def test_detecta_e_recupera_calibracao_ativa_desatualizada(self):
        self._criar_resultado()
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO calibracoes (
                    mercado, regra_versao, atualizado_em,
                    amostra, ativa, modelo_json
                ) VALUES ('gol_ft', 'sinais-v3', ?, 0, 1, '{}')
                """,
                ("2026-07-21T12:30:00",),
            )

        atrasada = auditar_frescor_calibracoes(
            self.banco.conexao,
            "sinais-v3",
            obter_limites_risco(),
        )

        self.assertFalse(atrasada["saudavel"])
        self.assertEqual(atrasada["desatualizadas"], 1)
        self.assertEqual(
            atrasada["detalhes"][0]["amostra_esperada"], 1
        )

        limites = obter_limites_risco()
        amostra = carregar_amostra_independente(
            self.banco.conexao, "gol_ft", "sinais-v3", limites
        )
        modelo = {"amostra_fingerprint": fingerprint_amostra(amostra)}
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                UPDATE calibracoes
                SET amostra=1, atualizado_em='2026-07-21T13:01:00',
                    modelo_json=?
                """,
                (json.dumps(modelo),),
            )
        atualizada = auditar_frescor_calibracoes(
            self.banco.conexao,
            "sinais-v3",
            limites,
        )

        self.assertTrue(atualizada["saudavel"])
        self.assertEqual(atualizada["desatualizadas"], 0)

        resultado = self.banco.conexao.execute(
            "SELECT * FROM resultados_sinais"
        ).fetchone()
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior,
                    observacao_anterior, snapshot_id_liquidacao_anterior,
                    fonte_resultado_anterior, motivo
                ) VALUES (?, '2026-07-21T13:02:00', ?, ?, ?, ?, ?, ?,
                          'reliquidacao auditada de teste')
                """,
                (
                    resultado["sinal_id"], resultado["encerrado_em"],
                    resultado["resultado"], resultado["retorno_unidades"],
                    resultado["observacao"],
                    resultado["snapshot_id_liquidacao"],
                    resultado["fonte_resultado"],
                ),
            )
            self.banco.conexao.execute(
                "DELETE FROM resultados_sinais WHERE sinal_id=?",
                (resultado["sinal_id"],),
            )
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, 'red', -1, ?, ?, ?)
                """,
                (
                    resultado["sinal_id"], resultado["encerrado_em"],
                    resultado["observacao"],
                    resultado["snapshot_id_liquidacao"],
                    resultado["fonte_resultado"],
                ),
            )
        revisada = auditar_frescor_calibracoes(
            self.banco.conexao, "sinais-v3", limites
        )
        self.assertFalse(revisada["saudavel"])
        self.assertFalse(
            revisada["detalhes"][0]["fingerprint_confere"]
        )

    def test_detecta_calibracao_inativa_desatualizada_quando_solicitado(self):
        self._criar_resultado()
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO calibracoes (
                    mercado, regra_versao, atualizado_em,
                    amostra, ativa, modelo_json
                ) VALUES ('gol_ft', 'sinais-v3', ?, 0, 0, '{}')
                """,
                ("2026-07-21T12:30:00",),
            )

        somente_ativas = auditar_frescor_calibracoes(
            self.banco.conexao,
            "sinais-v3",
            obter_limites_risco(),
        )
        todas = auditar_frescor_calibracoes(
            self.banco.conexao,
            "sinais-v3",
            obter_limites_risco(),
            somente_ativas=False,
        )

        self.assertTrue(somente_ativas["saudavel"])
        self.assertEqual(somente_ativas["inativas"], 0)
        self.assertFalse(todas["saudavel"])
        self.assertEqual(todas["desatualizadas_inativas"], 1)
        self.assertFalse(todas["detalhes"][0]["ativa"])

    def test_legado_sem_fingerprint_e_preservado_mas_nao_calibra(self):
        snapshot = self.banco.salvar_registro(
            {
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/2/live",
                "mandante": "C",
                "visitante": "D",
                "placar": "0-0",
                "status": "60 '",
            }
        )
        partida_id = self.banco.conexao.execute(
            "SELECT partida_id FROM snapshots WHERE id=?", (snapshot,)
        ).fetchone()[0]
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO sinais (
                    partida_id, snapshot_id, criado_em, mercado, linha, odd,
                    pontuacao_tecnica, regra_versao, status
                ) VALUES (?, ?, ?, 'gol_ft', 0.5, 1.8, 80,
                          'sinais-v3', 'aprovado')
                """,
                (partida_id, snapshot, "2026-07-20T12:00:00"),
            )
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades
                ) VALUES (?, '2026-07-20T13:00:00', 'green', 0.8)
                """,
                (cursor.lastrowid,),
            )

        amostra = carregar_amostra_independente(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
        )
        cobertura = resumir_cobertura_amostra_calibracao(
            self.banco.conexao,
            "gol_ft",
            "sinais-v3",
            obter_limites_risco(),
        )

        self.assertEqual(amostra, [])
        self.assertEqual(cobertura["historicas"], 1)
        self.assertEqual(cobertura["vinculadas"], 0)
        self.assertEqual(cobertura["legado_excluido"], 1)

    def test_particao_temporal_separa_passado_de_validacao_futura(self):
        resultados = [
            {
                "id": indice,
                "partida_id": indice,
                "criado_em": f"2026-07-21T{indice:02d}:00:00",
                "encerrado_em": f"2026-07-21T{indice:02d}:00:00",
            }
            for indice in range(1, 11)
        ]

        auditoria = auditar_particao_temporal(resultados)

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["desenvolvimento"], 7)
        self.assertEqual(auditoria["validacao"], 3)
        self.assertLessEqual(
            auditoria["ultimo_desenvolvimento_em"],
            auditoria["primeiro_validacao_em"],
        )

    def test_particao_fixa_nao_move_corte_ao_receber_novos_resultados(self):
        resultados = [
            {
                "id": indice,
                "partida_id": indice,
                "criado_em": (
                    datetime(2026, 7, 21, 0, 0)
                    + timedelta(hours=indice)
                ).isoformat(),
                "encerrado_em": (
                    datetime(2026, 7, 21, 0, 0)
                    + timedelta(hours=indice)
                ).isoformat(),
            }
            for indice in range(1, 90)
        ]

        parcial = auditar_particao_temporal(
            resultados[:71], tamanho_desenvolvimento=70
        )
        ampliada = auditar_particao_temporal(
            resultados, tamanho_desenvolvimento=70
        )

        self.assertEqual(parcial["desenvolvimento"], 70)
        self.assertEqual(parcial["validacao"], 1)
        self.assertEqual(ampliada["desenvolvimento"], 70)
        self.assertEqual(ampliada["validacao"], 19)
        self.assertEqual(
            parcial["fingerprint_desenvolvimento"],
            ampliada["fingerprint_desenvolvimento"],
        )

    def test_particao_temporal_rejeita_ordem_e_partida_duplicada(self):
        resultados = [
            {"id": 1, "partida_id": 1,
             "criado_em": "2026-07-21T12:00:00",
             "encerrado_em": "2026-07-21T12:00:00"},
            {"id": 2, "partida_id": 1,
             "criado_em": "2026-07-21T11:00:00",
             "encerrado_em": "2026-07-21T11:00:00"},
        ]

        auditoria = auditar_particao_temporal(resultados)

        self.assertFalse(auditoria["saudavel"])
        self.assertIn(
            "partidas_ausentes_ou_duplicadas", auditoria["motivos"]
        )
        self.assertIn(
            "amostra_fora_de_ordem_cronologica", auditoria["motivos"]
        )

    def test_auditoria_das_particoes_reais_vazias_e_saudavel(self):
        auditoria = auditar_particoes_calibracao(
            self.banco.conexao,
            ("gol_ft",),
            "sinais-v3",
            obter_limites_risco(),
        )

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["detalhes"]["gol_ft"]["total"], 0)

    def test_auditorias_respeitam_versao_especifica_de_cada_mercado(self):
        regras = {
            "gol_ft": "sinais-v6",
            "escanteios_ft_asiatico": "sinais-v7-ft-asiatico",
        }
        limites = obter_limites_risco()

        particoes = auditar_particoes_calibracao_por_mercado(
            self.banco.conexao,
            regras,
            limites,
        )
        frescor = auditar_frescor_calibracoes_por_mercado(
            self.banco.conexao,
            regras,
            limites,
        )

        self.assertTrue(particoes["saudavel"])
        self.assertEqual(particoes["regras_por_mercado"], regras)
        self.assertEqual(
            particoes["detalhes"]["gol_ft"]["regra_versao"],
            "sinais-v6",
        )
        self.assertEqual(
            particoes["detalhes"]["escanteios_ft_asiatico"][
                "regra_versao"
            ],
            "sinais-v7-ft-asiatico",
        )
        self.assertTrue(frescor["saudavel"])
        self.assertEqual(frescor["regras_por_mercado"], regras)


if __name__ == "__main__":
    unittest.main()
