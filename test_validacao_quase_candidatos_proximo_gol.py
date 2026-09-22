import json
import sqlite3
import unittest
from datetime import datetime, timedelta

from politica_proximo_gol_preciso import MOTIVO_PRESSAO
from validacao_quase_candidatos_proximo_gol import (
    BRACO_ATIVIDADE_COM_CHUTE,
    BRACO_ODD_165_199,
    CHAVE_DEFINICAO,
    MOTIVO_ATIVIDADE,
    TABELA_COORTE,
    VERSAO_AUDITORIA_BLOQUEIOS,
    classificar_braco,
    registrar_ou_validar_definicao,
    resumir_validacao,
    sincronizar_coorte,
)
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)


class ValidacaoQuaseCandidatosProximoGolTest(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")
        self.conexao.execute("""
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                partida_id TEXT NOT NULL,
                snapshot_id INTEGER NOT NULL,
                criado_em TEXT NOT NULL,
                mercado TEXT,
                linha REAL,
                odd REAL,
                pontuacao_tecnica REAL,
                regra_versao TEXT,
                regra_fingerprint TEXT,
                motivos_json TEXT,
                features_json TEXT,
                status TEXT
            )
        """)
        # O SQLite operacional grava criado_em no relógio local sem offset.
        self.ancora = datetime(2026, 9, 10, 12, 0)

    def tearDown(self):
        self.conexao.close()

    @staticmethod
    def _features(bloqueios, **alteracoes):
        features = {
            "minuto": 60,
            "qualidade_dados": 100,
            "lado_dominante": "casa",
            "chutes_lado_dominante_5min": 1,
            "gols_atuais": 0,
            "janelas": {"5": {
                "pressao_pico": [55, 25],
                "pressao_media": [45, 25],
            }},
            "auditoria_bloqueio": {
                "versao": VERSAO_AUDITORIA_BLOQUEIOS,
                "bloqueios_originais": list(bloqueios),
                "bloqueios_chave": "|".join(sorted(bloqueios)),
                "origem_status": "rejeitado",
                "aplicacao_sinais": False,
                "telegram": False,
                "calibracao": False,
            },
        }
        features.update(alteracoes)
        return features

    def _candidato(self, *, identificador=1, partida="jogo-1", odd=1.80,
                   bloqueios=None, **alteracoes):
        bloqueios = list(bloqueios or [MOTIVO_PRESSAO])
        candidato = {
            "id": identificador,
            "partida_id": partida,
            "snapshot_id": identificador,
            "criado_em": self.ancora.isoformat(),
            "mercado": "proximo_gol",
            "linha": 0.5,
            "odd": odd,
            "pontuacao_tecnica": 65,
            "regra_versao": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            "regra_fingerprint": "fp",
            "motivos": [],
            "bloqueios": bloqueios,
            "features": self._features(bloqueios),
            "status": "auditoria",
        }
        candidato.update(alteracoes)
        return candidato

    def _inserir(self, identificador, partida, odd, bloqueios,
                 momento=None, **features_extra):
        momento = momento or (self.ancora + timedelta(minutes=identificador))
        features = self._features(bloqueios, **features_extra)
        self.conexao.execute("""
            INSERT INTO sinais(
                id,partida_id,snapshot_id,criado_em,mercado,linha,odd,
                pontuacao_tecnica,regra_versao,regra_fingerprint,
                motivos_json,features_json,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            identificador, partida, identificador, momento.isoformat(),
            "proximo_gol", 0.5, odd, 65,
            VERSAO_PROXIMO_GOL_FILTRO_PRECISO, "fp",
            json.dumps([]), json.dumps(features), "auditoria",
        ))

    def test_classifica_somente_os_dois_relaxamentos_pre_registrados(self):
        odd = classificar_braco(self._candidato())
        atividade = classificar_braco(self._candidato(
            odd=1.55,
            bloqueios=[MOTIVO_PRESSAO, MOTIVO_ATIVIDADE],
        ))

        self.assertEqual(BRACO_ODD_165_199, odd["braco"])
        self.assertEqual(BRACO_ATIVIDADE_COM_CHUTE, atividade["braco"])

    def test_rejeita_cartao_fonte_odd_vencida_e_metadado_nao_silencioso(self):
        for bloqueio in (
            "cartao_vermelho_reavaliar",
            "odds_desatualizadas",
            "fonte_odds_invalida",
        ):
            with self.subTest(bloqueio=bloqueio):
                candidato = self._candidato(
                    bloqueios=[MOTIVO_PRESSAO, bloqueio]
                )
                self.assertIsNone(classificar_braco(candidato))
        candidato = self._candidato()
        candidato["features"]["auditoria_bloqueio"]["telegram"] = True
        self.assertIsNone(classificar_braco(candidato))

    def test_braco_atividade_exige_chute_e_os_dois_bloqueios(self):
        sem_atividade = self._candidato(odd=1.55)
        sem_chute = self._candidato(
            odd=1.55,
            bloqueios=[MOTIVO_PRESSAO, MOTIVO_ATIVIDADE],
        )
        sem_chute["features"]["chutes_lado_dominante_5min"] = 0

        self.assertIsNone(classificar_braco(sem_atividade))
        self.assertIsNone(classificar_braco(sem_chute))

    def test_ancora_e_imutavel(self):
        primeira = registrar_ou_validar_definicao(
            self.conexao, self.ancora
        )
        segunda = registrar_ou_validar_definicao(
            self.conexao, self.ancora + timedelta(hours=1)
        )
        self.assertEqual(primeira, segunda)
        self.assertEqual(
            "2026-09-10T12:00:00",
            primeira["registrado_em_relogio_sinais"],
        )
        self.assertRegex(primeira["registrado_em"], r"[+-]\d\d:\d\d$")

        adulterada = dict(primeira)
        adulterada["telegram"] = True
        self.conexao.execute(
            "UPDATE metadados SET valor=? WHERE chave=?",
            (json.dumps(adulterada), CHAVE_DEFINICAO),
        )
        with self.assertRaises(RuntimeError):
            registrar_ou_validar_definicao(self.conexao)

    def test_sincroniza_sem_tabela_de_resultados_e_deduplica_partida(self):
        registrar_ou_validar_definicao(self.conexao, self.ancora)
        self._inserir(
            1, "antigo", 1.80, [MOTIVO_PRESSAO],
            self.ancora - timedelta(seconds=1),
        )
        self._inserir(
            2, "risco", 1.80,
            [MOTIVO_PRESSAO, "cartao_vermelho_reavaliar"],
        )
        self._inserir(3, "unico", 1.80, [MOTIVO_PRESSAO])
        self._inserir(
            4, "unico", 1.55, [MOTIVO_PRESSAO, MOTIVO_ATIVIDADE]
        )
        self._inserir(
            5, "atividade", 1.55,
            [MOTIVO_PRESSAO, MOTIVO_ATIVIDADE],
        )

        resumo = sincronizar_coorte(self.conexao, self.ancora)
        linhas = self.conexao.execute(
            f"SELECT braco,partida_id FROM {TABELA_COORTE} "
            "ORDER BY ordem_global"
        ).fetchall()

        self.assertEqual(2, resumo["inseridos"])
        self.assertEqual([
            (BRACO_ODD_165_199, "unico"),
            (BRACO_ATIVIDADE_COM_CHUTE, "atividade"),
        ], linhas)

    def test_fecha_60_por_braco_e_avalia_sem_promocao_automatica(self):
        registrar_ou_validar_definicao(self.conexao, self.ancora)
        identificador = 1
        for indice in range(61):
            self._inserir(
                identificador, f"odd-{indice}", 1.80, [MOTIVO_PRESSAO]
            )
            identificador += 1
        for indice in range(61):
            self._inserir(
                identificador, f"atividade-{indice}", 1.55,
                [MOTIVO_PRESSAO, MOTIVO_ATIVIDADE],
            )
            identificador += 1
        sincronizacao = sincronizar_coorte(self.conexao, self.ancora)
        self.assertEqual("coortes_fechadas", sincronizacao["estado"])
        self.assertEqual({
            BRACO_ODD_165_199: 60,
            BRACO_ATIVIDADE_COM_CHUTE: 60,
        }, sincronizacao["por_braco"])

        self.conexao.execute("""
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY,
                resultado TEXT,
                retorno_unidades REAL
            )
        """)
        membros = self.conexao.execute(
            f"SELECT braco,sinal_id,ordem_braco,odd FROM {TABELA_COORTE}"
        ).fetchall()
        for braco, sinal_id, ordem, odd in membros:
            # Um caso realmente forte deve atravessar inclusive o limite
            # inferior do holdout contra 1/odd; 75% nominal isolado nao basta.
            resultado = "red" if ordem % 10 == 0 else "green"
            retorno = -1.0 if resultado == "red" else float(odd) - 1.0
            self.conexao.execute(
                "INSERT INTO resultados_sinais VALUES (?,?,?)",
                (sinal_id, resultado, retorno),
            )

        resumo = resumir_validacao(self.conexao)
        self.assertEqual("encerrada", resumo["estado"])
        self.assertEqual(
            "hipotese_favoravel_para_revisao_manual", resumo["decisao"]
        )
        self.assertEqual(set((
            BRACO_ODD_165_199, BRACO_ATIVIDADE_COM_CHUTE,
        )), set(resumo["bracos_favoraveis"]))
        self.assertFalse(resumo["promocao_automatica"])
        self.assertFalse(resumo["telegram"])

    def test_detecta_adulteracao_do_membro_congelado(self):
        registrar_ou_validar_definicao(self.conexao, self.ancora)
        self._inserir(1, "jogo", 1.80, [MOTIVO_PRESSAO])
        sincronizar_coorte(self.conexao, self.ancora)
        self.conexao.execute("""
            CREATE TABLE resultados_sinais (
                sinal_id INTEGER PRIMARY KEY,
                resultado TEXT,
                retorno_unidades REAL
            )
        """)
        self.conexao.execute(
            f"UPDATE {TABELA_COORTE} SET odd=1.91"
        )

        with self.assertRaises(RuntimeError):
            resumir_validacao(self.conexao)


if __name__ == "__main__":
    unittest.main()
