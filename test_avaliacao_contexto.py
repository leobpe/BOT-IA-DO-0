import json
import unittest
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from avaliacao_contexto import (
    TAMANHO_COORTE,
    TAMANHO_DESENVOLVIMENTO,
    TAMANHO_HOLDOUT,
    VERSAO_AVALIACAO_CONTEXTO,
    auditar_historico_avaliacao_contexto,
    avaliar_contexto_avancado,
    avaliar_segmento_contexto,
    extrair_variaveis_contexto,
    registrar_historico_avaliacao_contexto,
    registrar_ou_obter_ancoras_contexto,
)
from banco import BancoMonitor
from configuracao import obter_limites_risco
from linhagem_regras import registrar_ou_validar_linhagem_regra


class AvaliacaoContextoTest(unittest.TestCase):
    def setUp(self):
        self.caminho = Path.cwd() / ".teste_avaliacao_contexto.db"
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.banco = BancoMonitor(self.caminho)
        self.regra = "sinais-contexto-teste"
        self.linhagem = registrar_ou_validar_linhagem_regra(
            self.banco.conexao,
            Path.cwd(),
            self.regra,
            "features-temporais-v2",
        )
        registrar_ou_obter_ancoras_contexto(
            self.banco.conexao,
            {
                "gol_ft": self.regra,
                "proximo_escanteio": self.regra,
            },
            registrado_em="2026-07-29T00:00:00",
        )

    def tearDown(self):
        self.banco.fechar()
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho) + sufixo)
            if arquivo.exists():
                arquivo.unlink()

    @staticmethod
    def _contexto(h2h_alto):
        return {
            "versao": "contexto-pre-jogo-v1",
            "times": {"mandante_id": 1, "visitante_id": 2},
            "forma_recente": {
                "mandante": {"pontos_por_jogo": 2.2},
                "visitante": {"pontos_por_jogo": 1.0},
            },
            "confrontos_diretos": {
                "media_gols": 3.0 if h2h_alto else 1.0,
            },
            "desfalques": {"1": {"total": 0}, "2": {"total": 3}},
            "escalacoes": {
                "1": {"confirmada": True},
                "2": {"confirmada": True},
            },
            "comparacao_fontes_ao_vivo": {
                "comparadas": 3,
                "taxa_concordancia": 1.0,
            },
            "odds_pre_jogo": {
                "mercados": {
                    "gols_ft": {
                        "consenso_suficiente": True,
                        "linha_consenso": 2.5,
                    },
                    "escanteios_ft": {
                        "consenso_suficiente": True,
                        "linha_consenso": 9.5,
                    },
                },
            },
        }

    def _criar_resultado(self, indice, resultado, retorno, h2h_alto):
        snapshot = self.banco.salvar_registro({
            "coletado_em": f"2026-07-29T1{indice}:00:00",
            "url": f"https://packball.com/match/contexto-{indice}/live",
            "mandante": f"A{indice}",
            "visitante": f"B{indice}",
            "placar": "0-0",
            "status": "60 '",
            "contexto_api": self._contexto(h2h_alto),
        })
        sinal = self.banco.salvar_candidatos(
            snapshot,
            [{
                "mercado": "gol_ft",
                "linha": 0.5,
                "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": self.regra,
                "regra_fingerprint": self.linhagem["fingerprint_atual"],
                "status": "aprovado",
            }],
        )[0]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    fonte_resultado
                ) VALUES (?, ?, ?, ?, 'packball')
                """,
                (
                    sinal,
                    f"2026-07-29T1{indice}:30:00",
                    resultado,
                    retorno,
                ),
            )

    def _inserir_sinal_direto(
        self, partida_chave, criado_em, *, contexto, resultado=None,
        retorno=None, odd=1.8, mercado="gol_ft",
    ):
        url = f"https://packball.com/match/{partida_chave}/live"
        self.banco.conexao.execute(
            """
            INSERT OR IGNORE INTO partidas (
                packball_url, mandante, visitante,
                mandante_normalizado, visitante_normalizado,
                primeira_coleta, ultima_coleta
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url, f"A-{partida_chave}", f"B-{partida_chave}",
                f"a-{partida_chave}", f"b-{partida_chave}",
                criado_em, criado_em,
            ),
        )
        partida_id = int(self.banco.conexao.execute(
            "SELECT id FROM partidas WHERE packball_url=?", (url,)
        ).fetchone()["id"])
        cursor_snapshot = self.banco.conexao.execute(
            """
            INSERT INTO snapshots (
                partida_id, coletado_em, placar, status,
                contexto_api_json
            ) VALUES (?, ?, '0-0', '60', ?)
            """,
            (
                partida_id,
                criado_em,
                json.dumps(contexto) if contexto is not None else None,
            ),
        )
        cursor_sinal = self.banco.conexao.execute(
            """
            INSERT INTO sinais (
                partida_id, snapshot_id, criado_em, mercado, linha, odd,
                pontuacao_tecnica, regra_versao, regra_fingerprint, status
            ) VALUES (?, ?, ?, ?, '0.5', ?, 80, ?, ?, 'aprovado')
            """,
            (
                partida_id,
                cursor_snapshot.lastrowid,
                criado_em,
                mercado,
                odd,
                self.regra,
                self.linhagem["fingerprint_atual"],
            ),
        )
        if resultado is not None:
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    retorno_unidades, fonte_resultado
                ) VALUES (?, ?, ?, ?, 'packball')
                """,
                (cursor_sinal.lastrowid, criado_em, resultado, retorno),
            )
        return int(cursor_sinal.lastrowid)

    def test_extrai_variaveis_sem_influenciar_regra(self):
        variaveis = extrair_variaveis_contexto(self._contexto(True))
        self.assertTrue(variaveis["forma_mandante_superior"])
        self.assertTrue(variaveis["h2h_gols_alto"])
        self.assertTrue(variaveis["desfalques_desequilibrados"])
        self.assertTrue(variaveis["escalacoes_confirmadas"])
        self.assertTrue(variaveis["fontes_concordantes"])
        self.assertTrue(variaveis["linha_pre_jogo_gols_alta"])
        self.assertTrue(variaveis["linha_pre_jogo_escanteios_alta"])

    def test_dado_ausente_e_desconhecido_e_nao_condicao_falsa(self):
        variaveis = extrair_variaveis_contexto({
            "times": {"mandante_id": 1, "visitante_id": 2},
        })
        self.assertTrue(
            all(valor is None for valor in variaveis.values())
        )

    def test_segmento_so_e_favoravel_com_amostra_e_intervalo_positivo(self):
        com = [
            {"resultado": "green", "retorno_unidades": 1.0}
            for _ in range(30)
        ]
        sem = [
            {"resultado": "red", "retorno_unidades": -1.0}
            for _ in range(30)
        ]
        segmento = avaliar_segmento_contexto(com, sem, total=60)
        self.assertTrue(segmento["avaliavel"])
        self.assertTrue(segmento["conclusivo"])
        self.assertEqual(segmento["evidencia"], "favoravel")
        self.assertEqual(
            segmento["intervalo_delta_roi_ajustado"], [2.0, 2.0]
        )
        self.assertEqual(segmento["z_ajustado"], 3.0)

    def test_segmento_avaliavel_pode_continuar_inconclusivo(self):
        com = [
            {
                "resultado": "green" if indice % 2 else "red",
                "retorno_unidades": 1.0 if indice % 2 else -1.0,
            }
            for indice in range(30)
        ]
        sem = list(com)
        segmento = avaliar_segmento_contexto(com, sem, total=60)
        self.assertTrue(segmento["avaliavel"])
        self.assertFalse(segmento["conclusivo"])
        self.assertEqual(segmento["evidencia"], "inconclusiva")

    def test_avalia_amostra_independente_por_mercado(self):
        self._criar_resultado(1, "green", 0.8, True)
        self._criar_resultado(2, "red", -1.0, False)

        avaliacao = avaliar_contexto_avancado(
            self.banco.conexao,
            {"gol_ft": self.regra},
            obter_limites_risco(),
        )

        mercado = avaliacao["por_mercado"]["gol_ft"]
        self.assertEqual(mercado["base"]["amostra"], 2)
        self.assertEqual(mercado["base"]["greens"], 1)
        self.assertFalse(avaliacao["aplicacao_automatica"])
        h2h = mercado["segmentos"]["h2h_gols_alto"]
        self.assertEqual(h2h["com"]["amostra"], 1)
        self.assertEqual(h2h["sem"]["amostra"], 1)
        self.assertEqual(h2h["desconhecidos"], 0)
        self.assertEqual(h2h["cobertura"], 1.0)
        self.assertEqual(h2h["delta_roi"], 1.8)
        self.assertEqual(
            mercado["hipoteses_pre_registradas"],
            [
                "forma_mandante_superior",
                "forma_visitante_superior",
                "h2h_gols_alto",
                "desfalques_desequilibrados",
                "escalacoes_confirmadas",
                "fontes_concordantes",
                "historico_gols_alto",
                "linha_pre_jogo_gols_alta",
                "xg_live_alto",
                "volume_ofensivo_api_alto",
            ],
        )
        self.assertEqual(
            avaliacao["versao"], VERSAO_AVALIACAO_CONTEXTO
        )
        self.assertEqual(avaliacao["modo"], "sombra_causal_holdout_fixo")
        self.assertFalse(mercado["pronto_para_revisao"])

        with self.banco.conexao:
            primeira = registrar_historico_avaliacao_contexto(
                self.banco.conexao,
                avaliacao,
                "2026-07-29T13:00:00",
            )
            segunda = registrar_historico_avaliacao_contexto(
                self.banco.conexao,
                avaliacao,
                "2026-07-29T13:01:00",
            )
        self.assertEqual(primeira["inseridos"], 1)
        self.assertEqual(segunda["ignorados"], 1)
        auditoria = auditar_historico_avaliacao_contexto(
            self.banco.conexao
        )
        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["estado"], "integro")
        self.assertEqual(auditoria["total"], 1)
        self.assertEqual(auditoria["json_invalidos"], [])
        self.assertEqual(auditoria["divergentes"], [])
        with self.assertRaises(sqlite3.IntegrityError):
            self.banco.conexao.execute(
                "UPDATE historico_avaliacao_contexto SET amostra=99"
            )

    def test_primeira_exposicao_pendente_nao_e_trocada_por_green_posterior(self):
        with self.banco.conexao:
            primeiro = self._inserir_sinal_direto(
                "mesmo-jogo",
                "2026-07-30T10:00:00",
                contexto=None,
            )
            self._inserir_sinal_direto(
                "mesmo-jogo",
                "2026-07-30T10:01:00",
                contexto=self._contexto(True),
                resultado="green",
                retorno=0.8,
            )

        avaliacao = avaliar_contexto_avancado(
            self.banco.conexao,
            {"gol_ft": self.regra},
            obter_limites_risco(),
        )

        mercado = avaliacao["por_mercado"]["gol_ft"]
        self.assertEqual(1, mercado["base"]["candidatos_independentes"])
        self.assertEqual(0, mercado["base"]["amostra"])
        self.assertEqual(1, mercado["base"]["pendentes_ou_invalidos"])
        self.assertEqual(primeiro, mercado["ultimo_sinal_id"])
        self.assertFalse(mercado["pronto_para_revisao"])

    def test_retorno_incompativel_nao_entra_na_avaliacao(self):
        with self.banco.conexao:
            self._inserir_sinal_direto(
                "retorno-invalido",
                "2026-07-30T11:00:00",
                contexto=self._contexto(True),
                resultado="green",
                retorno=0.7,
                odd=1.8,
            )

        avaliacao = avaliar_contexto_avancado(
            self.banco.conexao,
            {"gol_ft": self.regra},
            obter_limites_risco(),
        )
        base = avaliacao["por_mercado"]["gol_ft"]["base"]

        self.assertEqual(0, base["amostra"])
        self.assertEqual(
            1,
            base["auditoria_resultados"]["motivos"][
                "retorno_incompativel_com_resultado_e_odd"
            ],
        )

    def test_historico_registra_liquidacao_sem_novo_sinal(self):
        with self.banco.conexao:
            sinal_id = self._inserir_sinal_direto(
                "liquidacao-tardia",
                "2026-07-30T11:30:00",
                contexto=self._contexto(True),
            )
        primeira = avaliar_contexto_avancado(
            self.banco.conexao,
            {"gol_ft": self.regra},
            obter_limites_risco(),
        )
        with self.banco.conexao:
            gravacao_pendente = registrar_historico_avaliacao_contexto(
                self.banco.conexao, primeira, "2026-07-30T11:31:00"
            )
            self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado,
                    retorno_unidades, fonte_resultado
                ) VALUES (?, '2026-07-30T11:32:00', 'green', 0.8, 'packball')
                """,
                (sinal_id,),
            )
        segunda = avaliar_contexto_avancado(
            self.banco.conexao,
            {"gol_ft": self.regra},
            obter_limites_risco(),
        )
        with self.banco.conexao:
            gravacao_liquidada = registrar_historico_avaliacao_contexto(
                self.banco.conexao, segunda, "2026-07-30T11:33:00"
            )

        primeiro_estado = primeira["por_mercado"]["gol_ft"]
        segundo_estado = segunda["por_mercado"]["gol_ft"]
        self.assertEqual(
            primeiro_estado["ultimo_sinal_real_id"],
            segundo_estado["ultimo_sinal_real_id"],
        )
        self.assertNotEqual(
            primeiro_estado["chave_historico_estado"],
            segundo_estado["chave_historico_estado"],
        )
        self.assertEqual(1, gravacao_pendente["inseridos"])
        self.assertEqual(1, gravacao_liquidada["inseridos"])
        auditoria = auditar_historico_avaliacao_contexto(
            self.banco.conexao
        )
        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(2, auditoria["total"])

    def test_coorte_300_exige_replicacao_no_holdout_fixo(self):
        inicio = datetime(2026, 7, 30, 12, 0)
        with self.banco.conexao:
            for indice in range(TAMANHO_COORTE + 1):
                h2h_alto = indice % 2 == 0
                resultado = "green" if h2h_alto else "red"
                retorno = 0.8 if h2h_alto else -1.0
                self._inserir_sinal_direto(
                    f"coorte-{indice}",
                    (inicio + timedelta(minutes=indice)).isoformat(),
                    contexto=self._contexto(h2h_alto),
                    resultado=resultado,
                    retorno=retorno,
                )

        avaliacao = avaliar_contexto_avancado(
            self.banco.conexao,
            {"gol_ft": self.regra},
            obter_limites_risco(),
            janela_maxima=TAMANHO_COORTE + 1,
        )

        mercado = avaliacao["por_mercado"]["gol_ft"]
        auditoria = mercado["auditoria_coorte"]
        h2h = mercado["segmentos"]["h2h_gols_alto"]
        self.assertEqual(TAMANHO_COORTE, mercado["base"]["amostra"])
        self.assertEqual(TAMANHO_COORTE + 1, auditoria[
            "unidades_independentes_disponiveis"
        ])
        self.assertEqual(1, auditoria[
            "unidades_pos_coorte_somente_diagnostico"
        ])
        self.assertEqual(
            TAMANHO_DESENVOLVIMENTO,
            auditoria["resultados_validos_desenvolvimento"],
        )
        self.assertEqual(
            TAMANHO_HOLDOUT,
            auditoria["resultados_validos_holdout"],
        )
        self.assertEqual("favoravel_replicada", h2h["evidencia"])
        self.assertTrue(h2h["conclusivo"])
        self.assertTrue(mercado["pronto_para_revisao"])

    def test_auditoria_detecta_json_invalido_no_historico_contexto(self):
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO historico_avaliacao_contexto (
                    regra_versao, mercado, registrado_em,
                    ultimo_sinal_id, amostra, estado,
                    pronto_para_revisao, avaliacao_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.regra,
                    "gol_ft",
                    "2026-07-29T13:00:00",
                    999,
                    1,
                    "inconclusiva",
                    0,
                    "{json-invalido",
                ),
            )

        auditoria = auditar_historico_avaliacao_contexto(
            self.banco.conexao
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["estado"], "inconsistente")
        self.assertEqual(len(auditoria["json_invalidos"]), 1)

    def test_auditoria_detecta_colunas_divergentes_do_payload(self):
        payload = {
            "versao_avaliacao": "avaliacao-contexto-sombra-v5",
            "regra_versao": self.regra,
            "ultimo_sinal_id": 1000,
            "pronto_para_revisao": False,
            "base": {"amostra": 2, "estado": "inconclusiva"},
        }
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO historico_avaliacao_contexto (
                    regra_versao, mercado, registrado_em,
                    ultimo_sinal_id, amostra, estado,
                    pronto_para_revisao, avaliacao_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.regra,
                    "gol_ft",
                    "2026-07-29T13:00:00",
                    1000,
                    99,
                    "inconclusiva",
                    0,
                    json.dumps(payload),
                ),
            )

        auditoria = auditar_historico_avaliacao_contexto(
            self.banco.conexao
        )

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(len(auditoria["divergentes"]), 1)

    def test_auditoria_preserva_payload_legado_sem_versao(self):
        payload = {
            "regra_versao": self.regra,
            "ultimo_sinal_id": 1001,
            "pronto_para_revisao": False,
            "base": {"amostra": 2, "estado": "inconclusiva"},
        }
        with self.banco.conexao:
            cursor = self.banco.conexao.execute(
                """
                INSERT INTO historico_avaliacao_contexto (
                    regra_versao, mercado, registrado_em,
                    ultimo_sinal_id, amostra, estado,
                    pronto_para_revisao, avaliacao_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.regra,
                    "gol_ft",
                    "2026-07-29T13:00:00",
                    1001,
                    2,
                    "inconclusiva",
                    0,
                    json.dumps(payload),
                ),
            )

        auditoria = auditar_historico_avaliacao_contexto(
            self.banco.conexao
        )

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(
            auditoria["legado_sem_versao"], [cursor.lastrowid]
        )
        self.assertEqual(auditoria["prontos"], 0)
        self.assertEqual(
            auditoria["metodologias_desatualizadas"], [cursor.lastrowid]
        )

    def test_mercado_de_escanteio_nao_testa_h2h_de_gols(self):
        avaliacao = avaliar_contexto_avancado(
            self.banco.conexao,
            {"proximo_escanteio": self.regra},
            obter_limites_risco(),
        )
        mercado = avaliacao["por_mercado"]["proximo_escanteio"]
        self.assertEqual(
            mercado["hipoteses_pre_registradas"],
            [
                "fontes_concordantes",
                "historico_escanteios_alto",
                "linha_pre_jogo_escanteios_alta",
                "volume_ofensivo_api_alto",
            ],
        )
        self.assertNotIn("h2h_gols_alto", mercado["segmentos"])


if __name__ == "__main__":
    unittest.main()
