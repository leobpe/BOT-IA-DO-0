import base64
import json
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from preflight_reinicio import (
    ajustar_coleta_em_manutencao,
    ajustar_coleta_para_reinicio,
    executar_preflight,
    executar_testes,
    verificar_banco,
    verificar_carteira_operacional,
    verificar_experimento_filtro,
    verificar_frescor_calibracoes,
    verificar_hipoteses_sombra,
    verificar_historico_contexto,
    verificar_integridade_alertas,
    verificar_linhagem,
    verificar_modelos_sombra,
    verificar_notificacoes_operacionais,
    verificar_sessao,
    verificar_worker_treino_isolado,
)
from banco import BancoMonitor
from controle_acesso_packball import verificar_acesso_packball
from linhagem_regras import registrar_ou_validar_linhagem_regra
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS
from relatorio_simulacoes import registrar_ou_obter_experimento_filtro


class PreflightReinicioTest(unittest.TestCase):
    @patch("treino_processo_isolado.executar_treino_isolado")
    def test_preflight_prova_worker_treino_isolado(self, executar):
        executar.return_value = {
            "tipo": "autoteste",
            "execucao_treino_isolado": {
                "protocolo": "treino-modelo-isolado-v1",
                "tipo": "autoteste",
                "tentativas": 2,
                "recuperou_falha_transitoria": True,
                "falhas_transitorias": ["timeout"],
            },
        }

        resultado = verificar_worker_treino_isolado()

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "recuperado")
        self.assertEqual(resultado["tentativas"], 2)
        self.assertEqual(resultado["falhas_transitorias"], ["timeout"])

    @patch(
        "treino_processo_isolado.executar_treino_isolado",
        side_effect=RuntimeError("falha interna sensivel"),
    )
    def test_preflight_bloqueia_worker_treino_indisponivel(self, _executar):
        resultado = verificar_worker_treino_isolado()

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "indisponivel")
        self.assertEqual(
            resultado["motivo"], "worker_treino_isolado_indisponivel"
        )
        self.assertEqual(resultado["erro"], "RuntimeError")
        self.assertNotIn("sensivel", json.dumps(resultado))

    def test_preflight_bloqueia_contrato_de_relogio_inconsistente(self):
        saudavel = {"saudavel": True}
        verificadores = {
            nome: Mock(return_value=saudavel)
            for nome in (
                "verificar_worker_treino_isolado", "verificar_dependencias",
                "verificar_sessao", "verificar_acesso_packball",
                "verificar_banco", "verificar_carteira_operacional",
                "verificar_experimento_filtro", "verificar_hipoteses_sombra",
                "verificar_definicao_exploracao_gols",
                "verificar_validacao_gols_antecipados",
                "verificar_modelos_sombra", "verificar_historico_contexto",
                "verificar_integridade_alertas",
                "verificar_notificacoes_operacionais",
                "verificar_frescor_calibracoes", "verificar_cache_api",
                "verificar_linhagem", "verificar_backup_diario",
                "verificar_backup_espelho", "verificar_coleta",
                "verificar_armazenamento", "verificar_contador_uso",
            )
        }
        verificadores.update({
            "load_dotenv": Mock(),
            "validar_configuracao": Mock(return_value={
                "valida": True, "erros": [], "avisos": [], "recursos": {},
            }),
            "ler_modo_manutencao": Mock(return_value={"ativo": False}),
            "verificar_relogios_coortes": Mock(return_value={
                "saudavel": False,
                "estado": "inconsistente",
                "problemas": ["sinais:criado_em_com_offset:1"],
            }),
        })
        with patch.multiple("preflight_reinicio", **verificadores):
            resultado = executar_preflight(Path.cwd(), rodar_testes=False)

        self.assertFalse(resultado["pronto_para_reinicio"])
        self.assertEqual(
            "inconsistente",
            resultado["verificacoes"]["relogios_coortes"]["estado"],
        )

    def _limpar_banco_teste(self):
        for sufixo in ("", "-wal", "-shm"):
            Path(f"{self.banco}{sufixo}").unlink(missing_ok=True)

    def setUp(self):
        self.gol_ft_legado = patch.dict(
            "os.environ", {"GOL_FT_REFORCADO_ATIVO": "0"}, clear=False
        )
        self.gol_ft_legado.start()
        self.sessao = Path.cwd() / ".teste_preflight_sessao.json"
        self.banco = Path.cwd() / ".teste_preflight.db"
        self.acesso = Path.cwd() / ".teste_preflight_acesso.json"
        self.sessao.unlink(missing_ok=True)
        self._limpar_banco_teste()
        self.acesso.unlink(missing_ok=True)

    def tearDown(self):
        self.gol_ft_legado.stop()
        self.sessao.unlink(missing_ok=True)
        self._limpar_banco_teste()
        self.acesso.unlink(missing_ok=True)

    def test_carteira_operacional_permite_primeira_epoca_e_detecta_corrupcao(self):
        banco = BancoMonitor(self.banco)
        banco.fechar()
        ambiente = {"GOL_FT_REFORCADO_ATIVO": "1"}

        primeira = verificar_carteira_operacional(
            self.banco, Path.cwd(), ambiente
        )
        self.assertTrue(primeira["saudavel_para_reinicio"])
        self.assertEqual(
            primeira["estado"], "aguardando_primeira_inicializacao"
        )

        conexao = sqlite3.connect(self.banco)
        try:
            with conexao:
                conexao.execute(
                    "INSERT OR REPLACE INTO metadados(chave, valor) "
                    "VALUES (?, ?)",
                    (
                        "estado_carteira_operacional:atual",
                        json.dumps({
                            "fingerprint": "ausente",
                            "chave_epoca": "carteira_operacional:epoca:ausente",
                        }),
                    ),
                )
        finally:
            conexao.close()

        corrompida = verificar_carteira_operacional(
            self.banco, Path.cwd(), ambiente
        )
        self.assertFalse(corrompida["saudavel_para_reinicio"])
        self.assertEqual(
            corrompida["estado"], "epoca_referenciada_ausente"
        )

    def test_linhagem_permite_nova_versao_sem_sinais_para_registro_no_inicio(self):
        banco = BancoMonitor(self.banco)
        banco.fechar()
        with patch(
            "preflight_reinicio.versoes_regras_operacionais",
            return_value=("sinais-nova-sem-historico",),
        ):
            resultado = verificar_linhagem(self.banco, Path.cwd())

        self.assertTrue(resultado["saudavel"])
        item = resultado["por_versao"]["sinais-nova-sem-historico"]
        self.assertEqual(
            item["estado_preflight"],
            "nova_versao_pendente_registro_no_inicio",
        )
        self.assertEqual(item["sinais_existentes"], 0)

    @patch(
        "preflight_reinicio.dotenv_values",
        return_value={
            "INTEGRACAO_OPERACIONAL_ATIVA": "1",
            "PRELIVE_PERFIL_SELECAO": "dia30_v7",
        },
    )
    @patch("preflight_reinicio.subprocess.run")
    def test_testes_rodam_sem_herdar_configuracao_operacional(
        self, executar, _ler_env
    ):
        executar.return_value.returncode = 0
        executar.return_value.stderr = ""
        executar.return_value.stdout = ""
        with patch.dict(
            "os.environ",
            {
                "INTEGRACAO_OPERACIONAL_ATIVA": "1",
                "PRELIVE_PERFIL_SELECAO": "dia30_v7",
                "VARIAVEL_DO_SISTEMA": "preservada",
            },
            clear=False,
        ):
            resultado = executar_testes(Path.cwd())

        ambiente = executar.call_args.kwargs["env"]
        self.assertTrue(resultado["saudavel"])
        self.assertNotIn("INTEGRACAO_OPERACIONAL_ATIVA", ambiente)
        self.assertEqual(ambiente["PRELIVE_PERFIL_SELECAO"], "v11")
        self.assertEqual(ambiente["PRELIVE_FILTRO_PRECISO_ATIVO"], "0")
        self.assertEqual(
            ambiente["GOL_FT_REFORCADO_OFICIAL_ATIVO"], "0"
        )
        self.assertEqual(
            ambiente["GOL_HT_PRINCIPAL_OFICIAL_ATIVO"], "0"
        )
        self.assertEqual(
            ambiente["AVISO_AGUARDAR_ODD_MERCADOS"],
            "gol_ft,gol_ht,proximo_gol",
        )
        self.assertEqual(ambiente["PRELIVE_MERCADOS_TIME_ATIVOS"], "1")
        self.assertEqual(
            ambiente["PRELIVE_MULTIPLAS_TRES_PERNAS_ATIVAS"], "1"
        )
        self.assertEqual(ambiente["VARIAVEL_DO_SISTEMA"], "preservada")

    @patch(
        "preflight_reinicio._listar_modulos_testes",
        return_value=["test_primeiro", "test_segundo"],
    )
    @patch("preflight_reinicio.subprocess.run")
    def test_testes_isolam_cada_modulo_em_processo_descartavel(
        self, executar, _listar
    ):
        executar.return_value = SimpleNamespace(
            returncode=0, stdout="", stderr=""
        )

        resultado = executar_testes(Path.cwd())

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["modo"], "isolado_por_modulo")
        self.assertEqual(resultado["modulos_concluidos"], 2)
        self.assertEqual(executar.call_count, 2)
        comandos = [chamada.args[0] for chamada in executar.call_args_list]
        self.assertEqual(comandos[0][-1], "test_primeiro")
        self.assertEqual(comandos[1][-1], "test_segundo")

    @patch(
        "preflight_reinicio._listar_modulos_testes",
        return_value=["test_estavel", "test_nativo"],
    )
    @patch("preflight_reinicio.subprocess.run")
    def test_falha_nativa_identifica_modulo_sem_aprovar_preflight(
        self, executar, _listar
    ):
        executar.side_effect = [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(
                returncode=3221225477,
                stdout="",
                stderr="Fatal Python error",
            ),
        ]

        resultado = executar_testes(Path.cwd())

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["motivo"], "testes_falharam")
        self.assertTrue(resultado["falha_nativa"])
        self.assertEqual(resultado["modulo"], "test_nativo")
        self.assertEqual(resultado["modulos_concluidos"], 1)
        self.assertIn("Fatal Python error", resultado["resumo"])

    @patch(
        "preflight_reinicio._listar_modulos_testes",
        return_value=["test_transitorio", "test_seguinte"],
    )
    @patch("preflight_reinicio.subprocess.run")
    def test_falha_comum_isolada_exige_tres_confirmacoes_limpas(
        self, executar, _listar
    ):
        executar.side_effect = [
            SimpleNamespace(returncode=1, stdout="erro transitorio", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]

        resultado = executar_testes(Path.cwd())

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["recuperou_falha_transitoria"])
        self.assertEqual(resultado["modulos_concluidos"], 2)
        self.assertEqual(executar.call_count, 5)
        incidente = resultado["falhas_transitorias"][0]
        self.assertEqual(incidente["modulo"], "test_transitorio")
        self.assertEqual(incidente["confirmacoes_aprovadas"], 3)

    @patch(
        "preflight_reinicio._listar_modulos_testes",
        return_value=["test_regressao"],
    )
    @patch("preflight_reinicio.subprocess.run")
    def test_falha_repetida_mantem_reinicio_bloqueado(
        self, executar, _listar
    ):
        executar.side_effect = [
            SimpleNamespace(returncode=1, stdout="falhou", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=1, stdout="falhou de novo", stderr=""),
        ]

        resultado = executar_testes(Path.cwd())

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["motivo"], "testes_falharam")
        self.assertEqual(resultado["modulo"], "test_regressao")
        self.assertEqual(resultado["confirmacoes_aprovadas"], 1)
        self.assertIn("falhou de novo", resultado["resumo"])
        self.assertEqual(executar.call_count, 3)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_ADMIN_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID": "",
            "TELEGRAM_CHAT_ID_GOLS": "",
        },
        clear=False,
    )
    def test_disjuntor_operacional_contido_permite_reinicio_corretivo(self):
        banco = BancoMonitor(self.banco)
        try:
            with banco.conexao:
                for indice, minuto in enumerate((0, 1, 2), start=1):
                    banco.conexao.execute(
                        """
                        INSERT INTO notificacoes_operacionais (
                            chave, destino, criado_em, tentado_em,
                            status, tentativas, erro
                        ) VALUES (?, 'grupo-valido', ?, ?, 'erro', 1,
                                  'URLError: conexao recusada')
                        """,
                        (
                            f"falha-{indice}",
                            f"2026-07-20T12:{minuto:02d}:00",
                            f"2026-07-20T12:{minuto:02d}:00",
                        ),
                    )
        finally:
            banco.fechar()

        resultado = verificar_notificacoes_operacionais(
            self.banco, datetime(2026, 7, 20, 12, 3)
        )

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["requer_atencao"])
        self.assertTrue(resultado["disjuntor_pausado"])
        self.assertTrue(resultado["saudavel_para_reinicio"])

    def test_calibracao_inativa_atrasada_permite_reinicio_corretivo(self):
        banco = BancoMonitor(self.banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO calibracoes (
                        mercado, regra_versao, atualizado_em,
                        amostra, ativa, modelo_json
                    ) VALUES ('gol_ft', 'sinais-v6',
                              '2026-07-20T12:00:00', 0, 0, '{}')
                    """
                )
        finally:
            banco.fechar()

        resultado = verificar_frescor_calibracoes(self.banco)

        self.assertFalse(resultado["saudavel"])
        self.assertTrue(resultado["saudavel_para_reinicio"])
        self.assertTrue(resultado["requer_reconciliacao"])
        self.assertEqual(
            resultado["estado"], "requer_reconciliacao_no_inicio"
        )

    def test_falha_de_leitura_da_calibracao_bloqueia_reinicio(self):
        self.banco.write_text("nao e sqlite", encoding="utf-8")

        resultado = verificar_frescor_calibracoes(self.banco)

        self.assertFalse(resultado["saudavel"])
        self.assertFalse(resultado["saudavel_para_reinicio"])

    def test_acesso_packball_ativo_e_recusado_sem_navegar(self):
        agora = datetime(2026, 7, 22, 12, 0, 0)
        self.acesso.write_text(json.dumps({
            "bloqueado_ate": (agora + timedelta(minutes=5)).isoformat(),
            "motivo": "excesso_solicitacoes_packball",
        }), encoding="utf-8")

        resultado = verificar_acesso_packball(self.acesso, agora)

        self.assertFalse(resultado["saudavel"])
        self.assertTrue(resultado["ativo"])
        self.assertEqual(resultado["restante_segundos"], 300)

    def test_coleta_parada_por_manutencao_e_pausa_planejada(self):
        resultado = ajustar_coleta_em_manutencao(
            {
                "saudavel": False,
                "motivo": "coleta_parada",
                "ultimo_evento": "modo_manutencao_solicitado",
                "ultimo_sucesso_em": "2026-07-22T11:59:00",
                "falhas_consecutivas": 1,
            },
            {"ativo": True},
        )
        self.assertTrue(resultado["saudavel"])
        self.assertEqual(
            resultado["estado"], "pausa_planejada_para_manutencao"
        )

    def test_manutencao_nao_mascara_varias_falhas_consecutivas(self):
        resultado = ajustar_coleta_em_manutencao(
            {
                "saudavel": False,
                "motivo": "coleta_parada",
                "ultimo_evento": "modo_manutencao_solicitado",
                "ultimo_sucesso_em": "2026-07-22T11:00:00",
                "falhas_consecutivas": 3,
            },
            {"ativo": True},
        )
        self.assertFalse(resultado["saudavel"])

    def test_manutencao_durante_primeiro_ciclo_permite_reinicio(self):
        resultado = ajustar_coleta_em_manutencao(
            {
                "saudavel": False,
                "motivo": "sem_ciclo_concluido",
                "ultimo_evento": "ciclo_em_andamento",
                "falhas_consecutivas": 0,
            },
            {"ativo": True},
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(
            "pausa_planejada_para_manutencao", resultado["estado"]
        )

    def test_ciclo_final_apos_pedido_continua_sendo_pausa_planejada(self):
        resultado = ajustar_coleta_em_manutencao(
            {
                "saudavel": False,
                "motivo": "coleta_parada",
                "ultimo_evento": "ciclo_concluido",
                "ultimo_sucesso_em": "2026-07-22T12:01:00",
                "falhas_consecutivas": 0,
            },
            {
                "ativo": True,
                "solicitado_em": "2026-07-22T12:00:00",
            },
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(
            resultado["estado"], "pausa_planejada_para_manutencao"
        )

    def test_ciclo_anterior_ao_pedido_nao_mascara_coleta_parada(self):
        resultado = ajustar_coleta_em_manutencao(
            {
                "saudavel": False,
                "motivo": "coleta_parada",
                "ultimo_evento": "ciclo_concluido",
                "ultimo_sucesso_em": "2026-07-22T11:59:00",
                "falhas_consecutivas": 0,
            },
            {
                "ativo": True,
                "solicitado_em": "2026-07-22T12:00:00",
            },
        )

        self.assertFalse(resultado["saudavel"])

    def test_inicio_pode_recuperar_coleta_parada_sem_mascarar_causa(self):
        resultado = ajustar_coleta_para_reinicio(
            {
                "saudavel": False,
                "motivo": "coleta_parada",
                "ultimo_sucesso_em": "2026-07-28T18:53:42",
            },
            permitir=True,
        )

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["requer_reinicio"])
        self.assertEqual(
            resultado["estado"], "recuperavel_apos_reinicio"
        )
        self.assertEqual(resultado["motivo_original"], "coleta_parada")

    def test_inicio_nao_mascara_outra_falha_da_coleta(self):
        resultado = ajustar_coleta_para_reinicio(
            {
                "saudavel": False,
                "motivo": "estado_corrompido",
            },
            permitir=True,
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["motivo"], "estado_corrompido")

    def test_inicio_recupera_falhas_apos_pausa_da_lista_expirar(self):
        resultado = ajustar_coleta_para_reinicio(
            {
                "saudavel": False,
                "motivo": "falhas_consecutivas",
                "falhas_consecutivas": 4,
            },
            permitir=True,
            acesso_packball={
                "saudavel": True,
                "ativo": False,
                "restante_segundos": 0,
                "motivo_persistido": "lista_packball_nao_validada",
            },
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(
            resultado["estado"],
            "recuperavel_apos_circuit_breaker_packball",
        )
        self.assertEqual(
            resultado["motivo_original"], "falhas_consecutivas"
        )

    def test_inicio_nao_fura_pausa_ativa_da_lista_packball(self):
        resultado = ajustar_coleta_para_reinicio(
            {"saudavel": False, "motivo": "falhas_consecutivas"},
            permitir=True,
            acesso_packball={
                "saudavel": False,
                "ativo": True,
                "restante_segundos": 300,
                "motivo_persistido": "lista_packball_nao_validada",
            },
        )

        self.assertFalse(resultado["saudavel"])

    def test_inicio_recupera_falhas_apos_sessao_manual_renovada(self):
        resultado = ajustar_coleta_para_reinicio(
            {
                "saudavel": False,
                "motivo": "falhas_consecutivas",
                "falhas_consecutivas": 7,
                "ultimo_evento": "modo_manutencao_solicitado",
                "ultimo_progresso_em": "2026-08-01T13:53:10",
            },
            permitir=True,
            acesso_packball={"saudavel": True, "ativo": False},
            sessao_packball={"saudavel": True},
            sessao_atualizada_em="2026-08-01T18:46:22",
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(
            resultado["estado"],
            "recuperavel_apos_sessao_packball_renovada",
        )

    def test_inicio_nao_mascara_falhas_com_sessao_antiga(self):
        resultado = ajustar_coleta_para_reinicio(
            {
                "saudavel": False,
                "motivo": "falhas_consecutivas",
                "ultimo_evento": "modo_manutencao_solicitado",
                "ultimo_progresso_em": "2026-08-01T13:53:10",
            },
            permitir=True,
            acesso_packball={"saudavel": True, "ativo": False},
            sessao_packball={"saudavel": True},
            sessao_atualizada_em="2026-08-01T12:00:00",
        )

        self.assertFalse(resultado["saudavel"])

    def test_sessao_exige_json_com_cookie_sem_expor_valor(self):
        self.sessao.write_text(
            json.dumps({"cookies": [{"name": "sessao", "value": "secreto"}]}),
            encoding="utf-8",
        )

        resultado = verificar_sessao(self.sessao)

        self.assertEqual(
            resultado,
            {
                "saudavel": True,
                "metodo": "cookie",
                "cookies": 1,
                "itens_local_storage": 0,
                "bancos_indexed_db": 0,
            },
        )
        self.assertNotIn("secreto", str(resultado))

    def test_sessao_packball_por_local_storage_e_aceita_sem_expor_token(self):
        self.sessao.write_text(
            json.dumps(
                {
                    "cookies": [],
                    "origins": [{
                        "origin": "https://packball.com",
                        "localStorage": [{
                            "name": "packballBearer",
                            "value": "token-secreto",
                        }],
                    }],
                }
            ),
            encoding="utf-8",
        )

        resultado = verificar_sessao(self.sessao)

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["metodo"], "local_storage")
        self.assertNotIn("token-secreto", str(resultado))

    def test_sessao_packball_jwt_expirado_e_recusado_sem_expor_token(self):
        agora = datetime(2026, 8, 1, 13, 10, 0)

        def codificar(dados):
            bruto = json.dumps(dados).encode("utf-8")
            return base64.urlsafe_b64encode(bruto).decode().rstrip("=")

        token = ".".join((
            codificar({"alg": "none"}),
            codificar({"exp": int((agora - timedelta(seconds=1)).timestamp())}),
            "assinatura",
        ))
        self.sessao.write_text(
            json.dumps({
                "cookies": [{"name": "analytics", "value": "x"}],
                "origins": [{
                    "origin": "https://packball.com",
                    "localStorage": [{
                        "name": "packballBearer",
                        "value": token,
                    }],
                }],
            }),
            encoding="utf-8",
        )

        resultado = verificar_sessao(self.sessao, agora=agora)

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["motivo"], "sessao_expirada")
        self.assertEqual(resultado["metodo"], "local_storage")
        self.assertNotIn(token, str(resultado))

    def test_sessao_packball_jwt_vigente_informa_expiracao(self):
        agora = datetime(2026, 8, 1, 13, 10, 0)
        expiracao = agora + timedelta(hours=1)

        def codificar(dados):
            bruto = json.dumps(dados).encode("utf-8")
            return base64.urlsafe_b64encode(bruto).decode().rstrip("=")

        token = ".".join((
            codificar({"alg": "none"}),
            codificar({"exp": int(expiracao.timestamp())}),
            "assinatura",
        ))
        self.sessao.write_text(
            json.dumps({
                "origins": [{
                    "origin": "https://packball.com",
                    "localStorage": [{
                        "name": "packballBearer",
                        "value": token,
                    }],
                }],
            }),
            encoding="utf-8",
        )

        resultado = verificar_sessao(self.sessao, agora=agora)

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(
            resultado["expira_em"],
            expiracao.replace(microsecond=0).isoformat(),
        )

    def test_banco_incompleto_e_recusado(self):
        conexao = sqlite3.connect(self.banco)
        conexao.execute("CREATE TABLE partidas(id INTEGER PRIMARY KEY)")
        conexao.close()

        resultado = verificar_banco(self.banco)

        self.assertFalse(resultado["saudavel"])
        self.assertIn("snapshots", resultado["tabelas_ausentes"])

    @patch.dict(
        "os.environ",
        {
            "PONTUACAO_MINIMA_SINAL_TESTE": "80",
            "QUALIDADE_MINIMA_SINAL_TESTE": "80",
        },
        clear=False,
    )
    def test_preflight_exige_marco_do_filtro_quando_teste_ativo(self):
        banco = BancoMonitor(self.banco)
        banco.fechar()

        ausente = verificar_experimento_filtro(self.banco, ativo=True)
        self.assertFalse(ausente["saudavel"])
        self.assertEqual(ausente["estado"], "ausente")

        banco = BancoMonitor(self.banco)
        try:
            registrar_ou_obter_experimento_filtro(
                banco.conexao,
                VERSAO_REGRAS,
                80,
                80,
                datetime(2026, 7, 22, 18, 10, 8),
            )
            registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
        finally:
            banco.fechar()

        valido = verificar_experimento_filtro(self.banco, ativo=True)
        self.assertTrue(valido["saudavel"])
        self.assertEqual(valido["estado"], "valido")

    def test_preflight_audita_protecao_das_hipoteses_sombra(self):
        banco = BancoMonitor(self.banco)
        banco.fechar()

        valido = verificar_hipoteses_sombra(self.banco)
        self.assertTrue(valido["saudavel"])
        self.assertTrue(valido["protegido"])

        conexao = sqlite3.connect(self.banco)
        with conexao:
            conexao.execute(
                "DROP TRIGGER trg_hipotese_sombra_update_imutavel"
            )
        conexao.close()

        invalido = verificar_hipoteses_sombra(self.banco)
        self.assertFalse(invalido["saudavel"])
        self.assertEqual(
            invalido["motivo"],
            "gatilhos_hipoteses_sombra_ausentes",
        )

    def test_preflight_audita_modelos_sombra_ausentes_como_validos(self):
        banco = BancoMonitor(self.banco)
        banco.fechar()

        resultado = verificar_modelos_sombra(self.banco)

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["pontuacao_temporal_integra"])
        self.assertTrue(resultado["pontuacao_contexto_integra"])
        self.assertTrue(resultado["pontuacao_longa_integra"])
        self.assertEqual(resultado["modelos_contextuais"], [])
        self.assertEqual(resultado["modelos_longos"], [])

    def test_preflight_recusa_modelo_contextual_corrompido(self):
        banco = BancoMonitor(self.banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    "DROP TRIGGER trg_pontuacao_sombra_update_imutavel"
                )
                banco.conexao.execute(
                    "DROP TRIGGER trg_pontuacao_sombra_delete_imutavel"
                )
                banco.conexao.execute(
                    """
                    INSERT INTO metadados(chave, valor)
                    VALUES (?, ?)
                    """,
                    (
                        "pontuacao_sombra:regime-gols-contexto-logistica-v2:"
                        "sinais-v6:gol_ft",
                        json.dumps({
                            "mercado": "gol_ft",
                            "regra_versao": "sinais-v6",
                            "modelo_hash": "hash-incorreto",
                            "modelo": {},
                        }),
                    ),
                )
        finally:
            banco.fechar()

        resultado = verificar_modelos_sombra(self.banco)

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(
            resultado["motivo"], "modelos_sombra_inconsistentes"
        )
        self.assertEqual(
            resultado["mercados_contextuais_inconsistentes"],
            ["gol_ft"],
        )

    def test_preflight_recusa_historico_contextual_invalido(self):
        banco = BancoMonitor(self.banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO historico_avaliacao_contexto (
                        regra_versao, mercado, registrado_em,
                        ultimo_sinal_id, amostra, estado,
                        pronto_para_revisao, avaliacao_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "sinais-v6",
                        "gol_ft",
                        "2026-07-29T20:00:00",
                        999,
                        1,
                        "inconclusiva",
                        0,
                        "{json-invalido",
                    ),
                )
        finally:
            banco.fechar()

        resultado = verificar_historico_contexto(self.banco)

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "inconsistente")
        self.assertEqual(len(resultado["json_invalidos"]), 1)

    def test_preflight_recusa_contador_da_api_sem_estado_confiavel(self):
        saudavel = {"saudavel": True}
        with patch(
            "preflight_reinicio.load_dotenv"
        ), patch(
            "preflight_reinicio.validar_configuracao",
            return_value={"valida": True, "erros": [], "avisos": []},
        ), patch(
            "preflight_reinicio.verificar_sessao", return_value=saudavel
        ), patch(
            "preflight_reinicio.verificar_banco", return_value=saudavel
        ), patch(
            "preflight_reinicio.verificar_integridade_alertas",
            return_value=saudavel,
        ), patch(
            "preflight_reinicio.verificar_linhagem", return_value=saudavel
        ), patch(
            "preflight_reinicio.verificar_backup_diario", return_value=saudavel
        ), patch(
            "preflight_reinicio.verificar_coleta", return_value=saudavel
        ), patch(
            "preflight_reinicio.verificar_armazenamento", return_value=saudavel
        ), patch(
            "preflight_reinicio.verificar_contador_uso",
            return_value={
                "saudavel": False,
                "requer_atencao": True,
                "estado": "corrompido",
            },
        ):
            resultado = executar_preflight(Path.cwd(), rodar_testes=False)

        self.assertFalse(resultado["pronto_para_reinicio"])
        self.assertEqual(
            resultado["verificacoes"]["contador_api"]["estado"],
            "corrompido",
        )

    def test_preflight_recusa_envio_telegram_incerto(self):
        banco = BancoMonitor(self.banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/preflight/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": "sinais-v4",
                "status": "aprovado",
            }])[0]
            banco.registrar_entrega_alerta(
                sinal, "chat", "enviando", instante="2026-07-20T12:00:00"
            )
        finally:
            banco.fechar()

        resultado = verificar_integridade_alertas(
            self.banco,
            agora=datetime(2026, 7, 20, 12, 3),
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["envios_incertos"], 1)
        self.assertEqual(
            resultado["motivo"], "integridade_telegram_inconsistente"
        )


if __name__ == "__main__":
    unittest.main()
