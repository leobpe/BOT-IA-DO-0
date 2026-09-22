import hashlib
import io
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backup_banco import BackupBanco
from avaliacao_quarentena_fallback_ht import (
    REGRA_VERSAO_ALVO as REGRA_VERSAO_QUARENTENA_FALLBACK_HT,
    STATUS_COORTE as STATUS_COORTE_QUARENTENA_FALLBACK_HT,
    VERSAO as VERSAO_AVALIACAO_QUARENTENA_FALLBACK_HT,
)
from banco import BancoMonitor
from calibracao import POLITICA_CALIBRACAO_VERSAO
from custodia_avaliacao import EFEITOS_DESATIVADOS
from exploracao_sombra import (
    VERSAO_EXPLORACAO_GOL_FT_V3,
    registrar_ou_validar_definicao_exploracao_gol_ft_v3,
    registrar_ou_validar_definicao_exploracao_gols,
    registrar_ou_validar_politica_avaliacao_gol_ft_v3,
    registrar_ou_validar_politica_avaliacao_gols,
)
from linhagem_regras import registrar_ou_validar_linhagem_regra
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS
from processo_monitor import TravaInstancia
from relatorio_simulacoes import registrar_ou_obter_experimento_filtro
from versoes_regras import VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86
from watchdog import (
    _destinos_operacionais_configurados,
    _destinos_resumo_configurados,
    auditar_operacao_pre_live,
    acionar_recuperacao_banco_ativo,
    atualizar_alerta_recuperacao_banco,
    atualizar_alerta_cota_api,
    atualizar_alerta_sessao_packball,
    atualizar_alerta_drift_simulacoes,
    atualizar_alerta_experimento_filtro,
    atualizar_alerta_grupo_gol_ft_capacidade_v2,
    atualizar_alerta_circuit_breaker_gols_antecipados,
    atualizar_alerta_circuit_breaker_filtro_gol_ft_preciso,
    atualizar_alerta_circuit_breaker_escanteios_ft_asiatico,
    atualizar_alerta_circuit_breaker_filtro_gol_ht_preciso,
    atualizar_alerta_circuit_breaker_proximo_gol_balanceado,
    atualizar_alerta_circuit_breaker_pre_live_preciso,
    aplicar_circuit_breaker_gols_antecipados,
    aplicar_circuit_breaker_filtro_gol_ft_preciso,
    aplicar_circuit_breaker_escanteios_ft_asiatico,
    aplicar_circuit_breaker_filtro_gol_ht_preciso,
    aplicar_circuit_breaker_proximo_gol_balanceado,
    aplicar_circuit_breaker_pre_live_preciso,
    aplicar_circuit_breaker_grupo_gol_ft_capacidade_v2,
    atualizar_alertas_filtros_regras_ativas,
    atualizar_alerta_experimento_ritmo,
    atualizar_alerta_hipoteses_sombra,
    atualizar_conclusao_gol_ft_v3,
    atualizar_conclusao_gol_ht_00_min20,
    atualizar_marcos_exploracao_gols,
    atualizar_alerta_prontidao_historico_api_live,
    atualizar_alertas_pontuacao_contexto_sombra,
    atualizar_alertas_pontuacao_longa_sombra,
    atualizar_alerta_risco_oficial,
    reinicio_isolado_watchdog_solicitado,
    atualizar_alerta_reinicio_monitor,
    atualizar_alerta_saude_monitor,
    atualizar_alerta_validacao,
    atualizar_alertas_estado_calibracoes,
    atualizar_marcos_odds_periodos,
    atualizar_marcos_validacao,
    atualizar_resumo_diario,
    comprimento_texto_telegram,
    dividir_resumo_diario_telegram,
    auditar_funil_recente,
    auditar_features_temporais,
    auditar_integridade_telegram,
    auditar_notificacoes_operacionais,
    reconciliar_notificacoes_operacionais,
    reconciliar_acompanhamentos_odd_expirados,
    atualizar_tendencia_armazenamento,
    monitor_em_inicializacao,
    carregar_estado_anterior_watchdog,
    carregar_estado_watchdog_sqlite,
    persistir_estado_watchdog_sqlite,
    persistir_historico_drift_simulacoes,
    persistir_historico_avaliacao_contexto,
    persistir_estudos_pontuacao_longa_sombra,
    tentar_reiniciar_processo,
    verificar_armazenamento,
    verificar_backup_diario,
    verificar_capacidade_coleta,
    verificar_cache_api_operacional,
    verificar_acompanhamento_preco_pos_alerta,
    verificar_amostragem_referencia_odds_sombra,
    verificar_fontes_sinais_operacionais,
    verificar_prioridade_scanner_packball,
    verificar_historico_api_live,
    verificar_ponto_recuperacao,
    verificar_pareamento_api,
    verificar_sessao_packball,
    verificar_coleta,
    verificar_validacao,
    verificar_integridade_banco_ativo,
    verificar_avaliacao_acompanhamento_odd,
    verificar_avaliacao_desajuste_odds,
    verificar_avaliacao_probabilidade_individual,
    verificar_avaliacao_quarentena_fallback_ht,
    verificar_avaliacao_prioridade_ligas_gols,
    verificar_carteira_operacional,
    verificar_trabalhador_acompanhamento_odd,
    resumir_operacao_diaria,
    executar_loop,
    executar_verificacao,
    enviar_alerta,
    enviar_alerta_conclusao_gol_ft_v3,
    enviar_alerta_conclusao_gol_ht_00_min20,
    formatar_alerta_reinicio_monitor,
    formatar_alerta_recuperacao_banco,
    main as main_watchdog,
)


def _liquidacao_edge_sem_vig_teste(coorte_gols=3):
    def recorte(tamanho, resultados=0):
        return {
            "resultados": resultados,
            "pendentes": tamanho - resultados,
            "cronologia_invalida": 0,
            "greens": 0,
            "reds": resultados,
            "taxa_green": 0.0 if resultados else None,
            "ic95_taxa_green": None,
            "odd_media": None,
            "probabilidade_controle_sem_vig_media": None,
            "ev_previsto_medio": None,
            "retorno_unidades": -float(resultados),
            "roi_real": -1.0 if resultados else None,
            "ic95_roi_real": None,
            "vies_calibracao": None,
            "brier_score": None,
            "resultado_posterior_selecao": True,
        }

    def mercado(categoria, tamanho):
        return {
            "categoria": categoria,
            "periodo": "FT",
            "candidatos_brutos": tamanho,
            "candidatos_independentes": tamanho,
            "coorte": tamanho,
            "jogos": tamanho,
            "faltam_coorte": 60 - tamanho,
            "total": recorte(tamanho),
            "desenvolvimento": recorte(tamanho),
            "holdout": recorte(0),
            "evidencia_completa": False,
            "vantagem_resultados_comprovada": False,
            "decisao": "formando_coorte",
        }

    return {
        "versao": "liquidacao-edge-sem-vig-v1",
        "definicao_sha256": "e" * 64,
        "registrado_em": "2026-09-01T16:27:00",
        "linhas": "somente_meias_linhas_sem_push",
        "candidatos_liquidaveis": coorte_gols,
        "resultados": 0,
        "pendentes": coorte_gols,
        "por_mercado": {
            "escanteios:FT": mercado("escanteios", 0),
            "gols:FT": mercado("gols", coorte_gols),
        },
        "exclusoes": {},
        "mercados_com_vantagem_comprovada": [],
        "vantagem_executavel_comprovada": False,
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _recorte_referencia_pos_envio_teste():
    def resumo():
        return {
            "resultados": 0,
            "pendentes": 0,
            "cronologia_invalida": 0,
            "desfechos_nao_binarios": 0,
            "greens": 0,
            "reds": 0,
            "neutros": 0,
            "roi_real": None,
            "ic95_roi_real": None,
            "resultado_posterior_selecao": True,
        }

    def mercado():
        return {
            "fotografias_independentes": 0,
            "candidatos_edge": 0,
            "sem_edge": 0,
            "coorte_edge": 0,
            "coorte_controle": 0,
            "desenvolvimento": 0,
            "holdout": 0,
            "total": resumo(),
            "desenvolvimento_resultados": resumo(),
            "holdout_resultados": resumo(),
            "controle_sem_edge": resumo(),
            "comparacao_roi": {
                "resultados_edge": 0,
                "resultados_sem_edge": 0,
                "delta_roi_edge_vs_sem_edge": None,
                "ic95_delta_roi": None,
            },
            "evidencia_completa": False,
            "vantagem_estatistica_para_revisao": False,
            "faltam_coorte_edge": 60,
            "faltam_resultados_edge": 50,
            "faltam_resultados_controle": 30,
            "decisao": "aguardando_primeira_referencia_pos_envio",
        }

    return {
        "versao": "edge-referencia-pos-envio-executavel-prospectiva-v2",
        "definicao_sha256": "f" * 64,
        "ancora_pre_registrada_em": "2026-09-01T16:28:00",
        "auditorias_pos_envio": 0,
        "fotografias_elegiveis": 0,
        "fotografias_independentes": 0,
        "exclusoes": {},
        "por_mercado": {
            "gol_ft": mercado(),
            "gol_ht": mercado(),
        },
        "mercados_para_revisao": [],
        "vantagem_estatistica_para_revisao": False,
        "selecao_antes_resultado": True,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "altera_prioridade": False,
        "telegram": False,
        "promocao_automatica": False,
    }


class WatchdogTest(unittest.TestCase):
    def _caminho_pre_live_preciso_isolado(self):
        """Impede que executar_verificacao grave no estado real do projeto.

        O circuit breaker do pre-live cai em ARQUIVO_ESTADO_PRE_LIVE_PRECISO
        quando nenhum caminho e informado. Sem isolar, a suite deixava um
        pre_live_preciso_estado.json suspenso na pasta e contaminava as
        execucoes seguintes.
        """
        caminho = Path.cwd() / f".teste_pre_live_preciso_{id(self):x}.json"
        caminho.unlink(missing_ok=True)
        self.addCleanup(caminho.unlink, missing_ok=True)
        return caminho

    def setUp(self):
        self.ambiente_teste = patch.dict(
            os.environ,
            {
                "SINAIS_TESTE_ATIVO": "0",
                "GOL_FT_REFORCADO_ATIVO": "0",
            },
            clear=False,
        )
        self.ambiente_teste.start()
        self.catalogo_odds_teste = patch(
            "watchdog.verificar_catalogo_odds_live",
            return_value={
                "saudavel": True, "estado": "valido",
                "motivo": None, "divergencias": [],
                "asiatico_2t_disponivel": False,
            },
        )

        self.catalogo_odds_teste.start()
        self.caminho = Path.cwd() / ".teste_watchdog.jsonl"
        self.caminho_banco = Path.cwd() / ".teste_watchdog.db"
        self.caminho_trava = Path.cwd() / ".teste_watchdog_instancia.lock"
        self.caminho_processo = Path.cwd() / ".teste_watchdog_processo.json"
        self.caminho_reinicio = Path.cwd() / ".teste_watchdog_reinicio.json"
        self.caminho_worker_odd = (
            Path.cwd() / ".teste_watchdog_worker_odd.json"
        )
        self.caminho_avaliacao_odd = (
            Path.cwd() / ".teste_watchdog_avaliacao_odd.json"
        )
        self.caminho_avaliacao_ligas = (
            Path.cwd() / ".teste_watchdog_avaliacao_ligas.json"
        )
        self.caminho_avaliacao_desajuste = (
            Path.cwd() / ".teste_watchdog_avaliacao_desajuste.json"
        )
        self.caminho_avaliacao_probabilidade = (
            Path.cwd() / ".teste_watchdog_avaliacao_probabilidade.json"
        )
        self.caminho_avaliacao_quarentena_ht = (
            Path.cwd() / ".teste_watchdog_avaliacao_quarentena_ht.json"
        )
        self.caminho_recuperacao = (
            Path.cwd() / ".teste_watchdog_recuperacao_banco.json"
        )
        self.pasta_backups = Path.cwd() / ".teste_watchdog_backups"
        for indice in range(0, 6):
            caminho_log = (
                self.caminho if indice == 0
                else Path(f"{self.caminho}.{indice}")
            )
            caminho_log.unlink(missing_ok=True)
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho_banco) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        self.pasta_backups.mkdir(exist_ok=True)
        for arquivo in self.pasta_backups.iterdir():
            arquivo.unlink()
        self.caminho_trava.unlink(missing_ok=True)
        self.caminho_processo.unlink(missing_ok=True)
        self.caminho_reinicio.unlink(missing_ok=True)
        self.caminho_worker_odd.unlink(missing_ok=True)
        self.caminho_avaliacao_odd.unlink(missing_ok=True)
        self.caminho_avaliacao_ligas.unlink(missing_ok=True)
        self.caminho_avaliacao_desajuste.unlink(missing_ok=True)
        self.caminho_avaliacao_probabilidade.unlink(missing_ok=True)
        self.caminho_avaliacao_quarentena_ht.unlink(missing_ok=True)
        self.caminho_recuperacao.unlink(missing_ok=True)

    def test_watchdog_expoe_estado_da_carteira_sem_registra_la(self):
        caminho = Path.cwd() / ".teste_watchdog_carteira.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(f"{caminho}{sufixo}").unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        banco.fechar()
        try:
            resultado = verificar_carteira_operacional(
                caminho,
                Path.cwd(),
                {"GOL_FT_REFORCADO_ATIVO": "1"},
            )
            self.assertTrue(resultado["saudavel"])
            self.assertEqual(
                resultado["estado"],
                "aguardando_primeira_inicializacao",
            )
            conexao = sqlite3.connect(caminho)
            try:
                quantidade = conexao.execute(
                    "SELECT COUNT(*) FROM metadados WHERE chave LIKE ?",
                    ("carteira_operacional:%",),
                ).fetchone()[0]
            finally:
                conexao.close()
            self.assertEqual(quantidade, 0)
        finally:
            for sufixo in ("", "-wal", "-shm"):
                Path(f"{caminho}{sufixo}").unlink(missing_ok=True)

    def tearDown(self):
        for indice in range(0, 6):
            caminho_log = (
                self.caminho if indice == 0
                else Path(f"{self.caminho}.{indice}")
            )
            caminho_log.unlink(missing_ok=True)
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(self.caminho_banco) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
        for arquivo in self.pasta_backups.iterdir():
            arquivo.unlink()
        self.pasta_backups.rmdir()
        self.caminho_trava.unlink(missing_ok=True)
        self.caminho_processo.unlink(missing_ok=True)
        self.caminho_reinicio.unlink(missing_ok=True)
        self.caminho_worker_odd.unlink(missing_ok=True)
        self.caminho_avaliacao_odd.unlink(missing_ok=True)
        self.caminho_avaliacao_ligas.unlink(missing_ok=True)
        self.caminho_avaliacao_desajuste.unlink(missing_ok=True)
        self.caminho_avaliacao_probabilidade.unlink(missing_ok=True)
        self.caminho_avaliacao_quarentena_ht.unlink(missing_ok=True)
        self.caminho_recuperacao.unlink(missing_ok=True)
        self.catalogo_odds_teste.stop()
        self.ambiente_teste.stop()

    def _salvar_funil_recente(
        self, banco, com_candidatos=False, regra_versao=VERSAO_REGRAS
    ):
        inicio = datetime(2026, 7, 20, 12, 0)
        for deslocamento in range(10):
            snapshot = banco.salvar_registro(
                {
                    "coletado_em": inicio + timedelta(minutes=deslocamento),
                    "url": "https://packball.com/match/funil/live",
                    "mandante": "A",
                    "visitante": "B",
                    "placar": "0-0",
                    "status": f"{20 + deslocamento} '",
                }
            )
            if com_candidatos:
                banco.salvar_candidatos(
                    snapshot,
                    [{
                        "mercado": "gol_ft",
                        "regra_versao": regra_versao,
                        "status": "rejeitado",
                        "bloqueios": ["odd_ao_vivo_indisponivel"],
                    }],
                    inicio + timedelta(minutes=deslocamento),
                )

    def test_funil_aceita_todas_as_versoes_operacionais_informadas(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            self._salvar_funil_recente(
                banco,
                com_candidatos=True,
                regra_versao=VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
            )

            funil = auditar_funil_recente(
                banco.conexao,
                datetime(2026, 7, 20, 12, 10),
                (
                    VERSAO_REGRAS,
                    VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
                ),
            )

            self.assertEqual(funil["estado"], "avaliavel")
            self.assertEqual(funil["snapshots_com_candidatos"], 10)
            self.assertEqual(funil["cobertura_candidatos"], 1.0)
            self.assertEqual(
                funil["regra_versoes"],
                [VERSAO_REGRAS, VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86],
            )
        finally:
            banco.fechar()

    def _salvar_recuperacao_banco_teste(self):
        registro = {
            "saudavel": True,
            "estado": "banco_restaurado",
            "motivo": "corrupcao_comprovada",
            "restaurado_em": "2026-08-09T15:30:00",
            "backup": "periodico_20260809_12.db",
            "checksum_sha256": "abc123",
            "quarentena": "quarentena_corrompido.db",
        }
        self.caminho_recuperacao.write_text(
            json.dumps(registro), encoding="utf-8"
        )
        return registro

    def test_rotas_telegram_separam_operacao_do_resumo(self):
        ambiente = {
            "TELEGRAM_ADMIN_ID": "admin",
            "TELEGRAM_CHAT_ID": "geral",
            "TELEGRAM_CHAT_ID_GOLS": "gols",
            "TELEGRAM_CHAT_ID_ESCANTEIOS": "cantos",
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS": "0",
        }
        with patch.dict(os.environ, ambiente, clear=False):
            self.assertEqual(
                _destinos_operacionais_configurados(), ["admin"]
            )
            self.assertEqual(
                _destinos_resumo_configurados(),
                ["geral", "gols"],
            )

    def test_rota_operacional_tem_opt_in_e_fallback_sem_admin(self):
        ambiente = {
            "TELEGRAM_ADMIN_ID": "admin",
            "TELEGRAM_CHAT_ID": "geral",
            "TELEGRAM_CHAT_ID_GOLS": "gols",
            "TELEGRAM_CHAT_ID_ESCANTEIOS": "cantos",
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS": "1",
        }
        with patch.dict(os.environ, ambiente, clear=False):
            self.assertEqual(
                _destinos_operacionais_configurados(),
                ["admin", "geral", "gols", "cantos"],
            )
        ambiente["TELEGRAM_ADMIN_ID"] = ""
        ambiente["TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS"] = "0"
        with patch.dict(os.environ, ambiente, clear=False):
            self.assertEqual(
                _destinos_operacionais_configurados(),
                ["geral", "gols", "cantos"],
            )

    def test_admin_igual_grupo_nao_recebe_telemetria_sem_opt_in(self):
        ambiente = {
            "TELEGRAM_ADMIN_ID": "grupo-geral",
            "TELEGRAM_CHAT_ID": "grupo-geral",
            "TELEGRAM_CHAT_ID_GOLS": "grupo-gols",
            "TELEGRAM_CHAT_ID_ESCANTEIOS": "grupo-cantos",
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS": "0",
        }
        with patch.dict(os.environ, ambiente, clear=False):
            self.assertEqual(_destinos_operacionais_configurados(), [])
            self.assertEqual(
                _destinos_resumo_configurados(),
                ["grupo-geral", "grupo-gols"],
            )

    def test_watchdog_resume_historico_api_live_sem_aplicar_em_sinais(self):
        banco = BancoMonitor(self.caminho_banco)
        agora = datetime(2026, 8, 9, 12, 0)
        base = {
            "fixture_id": 321,
            "packball_url": "https://packball.com/match/auditoria/live",
            "minuto": 30,
            "periodo": "primeiro_tempo",
            "orientacao": "direta",
            "chutes_mandante": 2,
            "chutes_visitante": 1,
            "chutes_gol_mandante": 1,
            "chutes_gol_visitante": 0,
            "escanteios_mandante": 1,
            "escanteios_visitante": 0,
            "xg_mandante": 0.2,
            "xg_visitante": 0.1,
            "completo": True,
            "fonte": "api_football",
        }
        banco.salvar_historico_api_live([
            {
                **base,
                "coletado_em": (
                    agora - timedelta(minutes=5)
                ).isoformat(),
            },
            {
                **base,
                "coletado_em": agora.isoformat(),
                "chutes_mandante": 4,
            },
        ], agora=agora)
        banco.fechar()

        resumo = verificar_historico_api_live(
            self.caminho_banco, agora=agora
        )

        self.assertTrue(resumo["saudavel"])
        self.assertEqual(resumo["snapshots"], 2)
        self.assertEqual(resumo["janelas_disponiveis"]["5"], 1)
        self.assertFalse(resumo["aplicacao_sinais"])

    def test_alerta_recuperacao_banco_e_entregue_uma_unica_vez(self):
        self._salvar_recuperacao_banco_teste()
        enviar = Mock(return_value=True)
        agora = datetime(2026, 8, 9, 15, 31, 0)

        primeiro = atualizar_alerta_recuperacao_banco(
            self.caminho_recuperacao, enviar=enviar, agora=agora
        )
        segundo = atualizar_alerta_recuperacao_banco(
            self.caminho_recuperacao,
            enviar=enviar,
            agora=agora + timedelta(minutes=10),
        )

        self.assertEqual(primeiro["estado"], "entregue")
        self.assertEqual(segundo["estado"], "ja_entregue")
        enviar.assert_called_once()
        persistido = json.loads(
            self.caminho_recuperacao.read_text(encoding="utf-8")
        )
        self.assertEqual(
            persistido["alerta_telegram"]["estado"], "entregue"
        )

    def test_alerta_recuperacao_respeita_retry_apos_falha(self):
        self._salvar_recuperacao_banco_teste()
        enviar = Mock(side_effect=[False, True])
        agora = datetime(2026, 8, 9, 15, 31, 0)

        falha = atualizar_alerta_recuperacao_banco(
            self.caminho_recuperacao, enviar=enviar, agora=agora
        )
        cedo = atualizar_alerta_recuperacao_banco(
            self.caminho_recuperacao,
            enviar=enviar,
            agora=agora + timedelta(minutes=1),
        )
        recuperado = atualizar_alerta_recuperacao_banco(
            self.caminho_recuperacao,
            enviar=enviar,
            agora=agora + timedelta(minutes=3),
        )

        self.assertEqual(falha["estado"], "erro_temporario")
        self.assertEqual(cedo["estado"], "aguardando_retry")
        self.assertEqual(recuperado["estado"], "entregue")
        self.assertEqual(enviar.call_count, 2)

    def test_alerta_recuperacao_reconcilia_envio_apos_interrupcao(self):
        registro = self._salvar_recuperacao_banco_teste()
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        texto = formatar_alerta_recuperacao_banco(registro)
        chave = hashlib.sha256(texto.encode("utf-8")).hexdigest()

        def enviar_e_interromper(_texto):
            conexao = sqlite3.connect(self.caminho_banco)
            try:
                with conexao:
                    conexao.execute(
                        """
                        INSERT INTO notificacoes_operacionais (
                            chave, destino, criado_em, tentado_em,
                            entregue_em, status, tentativas
                        ) VALUES (?, ?, ?, ?, ?, 'entregue', 1)
                        """,
                        (
                            chave, "teste", "2026-08-09T15:31:00",
                            "2026-08-09T15:31:00",
                            "2026-08-09T15:31:00",
                        ),
                    )
            finally:
                conexao.close()
            raise SystemExit("interrupcao simulada")

        with self.assertRaises(SystemExit):
            atualizar_alerta_recuperacao_banco(
                self.caminho_recuperacao,
                caminho_banco=self.caminho_banco,
                enviar=enviar_e_interromper,
                agora=datetime(2026, 8, 9, 15, 31, 0),
            )
        reenviar = Mock(return_value=True)
        reconciliado = atualizar_alerta_recuperacao_banco(
            self.caminho_recuperacao,
            caminho_banco=self.caminho_banco,
            enviar=reenviar,
            agora=datetime(2026, 8, 9, 15, 32, 0),
        )

        self.assertEqual(reconciliado["estado"], "entrega_reconciliada")
        reenviar.assert_not_called()

    def test_integridade_banco_ativo_respeita_intervalo_e_detecta_dano(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        agora = datetime(2026, 8, 9, 16, 0, 0)

        primeira = verificar_integridade_banco_ativo(
            self.caminho_banco, agora=agora, intervalo_minutos=10
        )
        self.caminho_banco.write_bytes(b"corrupcao-posterior")
        cache = verificar_integridade_banco_ativo(
            self.caminho_banco,
            anterior=primeira,
            agora=agora + timedelta(minutes=5),
            intervalo_minutos=10,
        )
        vencida = verificar_integridade_banco_ativo(
            self.caminho_banco,
            anterior=primeira,
            agora=agora + timedelta(minutes=11),
            intervalo_minutos=10,
        )

        self.assertEqual(primeira["estado"], "integro")
        self.assertFalse(cache["executada"])
        self.assertEqual(cache["estado"], "integro")
        self.assertEqual(vencida["estado"], "corrompido")
        self.assertTrue(vencida["corrupcao_comprovada"])

    def test_auditoria_pre_live_confirma_processo_banco_e_resultados(self):
        with patch("watchdog.ler_estado", side_effect=[
            {"pid": 321, "estado": "ativo"},
            {
                "finalizado_em": "2026-08-27T12:00:00-04:00",
                "jogos_analisados": 18,
                "candidatos_elegiveis": 24,
                "jogos_nao_analisados_limite": 6,
                "cobertura_analise": 0.75,
                "limite_analise": {"configurado": 60, "efetivo": 18},
                "bilhetes": 3,
                "validacao_depois": {
                    "resultados": 9, "roi": 0.08,
                    "apto_revisao": False,
                },
            },
        ]):
            resultado = auditar_operacao_pre_live(
                Path.cwd(),
                verificar_pid_fn=lambda pid: pid == 321,
                verificar_trava_fn=lambda _caminho: True,
                verificar_banco_fn=lambda _caminho: {
                    "valido": True, "integridade": ["ok"]
                },
            )
        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "ativo")
        self.assertEqual(resultado["jogos_analisados"], 18)
        self.assertEqual(resultado["candidatos_elegiveis"], 24)
        self.assertEqual(resultado["jogos_nao_analisados_limite"], 6)
        self.assertEqual(resultado["cobertura_analise"], 0.75)
        self.assertEqual(resultado["resultados"], 9)
        self.assertEqual(resultado["roi"], 0.08)

    def test_auditoria_pre_live_nao_confunde_pid_watchdog_com_trava(self):
        with patch("watchdog.ler_estado", side_effect=[
            {"pid": 999, "status": "iniciando"},
            {},
        ]):
            resultado = auditar_operacao_pre_live(
                Path.cwd(),
                verificar_pid_fn=lambda _pid: True,
                verificar_trava_fn=lambda _caminho: False,
                verificar_banco_fn=lambda _caminho: {"valido": True},
            )
        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "inicializando")

    def test_auditoria_pre_live_expoe_coorte_precisa_separada(self):
        with patch("watchdog.ler_estado", side_effect=[
            {"pid": 321, "status": "ativo"},
            {"validacao_depois": {"resultados": 99, "roi": -0.2}},
        ]):
            resultado = auditar_operacao_pre_live(
                Path.cwd(),
                verificar_pid_fn=lambda _pid: True,
                verificar_trava_fn=lambda _caminho: True,
                verificar_banco_fn=lambda _caminho: {"valido": True},
                resumir_filtro_preciso_fn=lambda _caminho: {
                    "estado": "coletando",
                    "candidatos": 7,
                    "validos": 5,
                    "faltam": 53,
                    "decisao": "aguardando_amostra_futura",
                },
                ler_controle_preciso_fn=lambda _caminho: {
                    "versao": "controle-v1",
                    "saudavel": True,
                    "ativo": True,
                    "estado": "ativo_padrao",
                },
            )

        self.assertEqual(7, resultado["filtro_preciso"]["candidatos"])
        self.assertEqual(53, resultado["filtro_preciso"]["faltam"])
        self.assertTrue(
            resultado["filtro_preciso"]["controle_operacional"]["ativo"]
        )
        self.assertEqual(99, resultado["resultados"])

    def test_corrupcao_ativa_solicita_manutencao_uma_unica_vez(self):
        self.caminho_banco.write_bytes(b"banco-corrompido")
        enviar = Mock(return_value=True)
        solicitar = Mock()
        agora = datetime(2026, 8, 9, 16, 0, 0)

        primeiro = acionar_recuperacao_banco_ativo(
            self.caminho_banco,
            Path.cwd(),
            agora=agora,
            enviar=enviar,
            solicitar=solicitar,
        )
        segundo = acionar_recuperacao_banco_ativo(
            self.caminho_banco,
            Path.cwd(),
            anterior=primeiro,
            agora=agora + timedelta(minutes=1),
            enviar=enviar,
            solicitar=solicitar,
        )

        self.assertTrue(primeiro["recuperacao_necessaria"])
        self.assertTrue(primeiro["manutencao_solicitada"])
        self.assertEqual(primeiro["estado"], "corrompido")
        self.assertTrue(segundo["manutencao_solicitada"])
        enviar.assert_called_once()
        solicitar.assert_called_once()

    def test_falha_temporaria_nao_aciona_restauracao(self):
        self.caminho_banco.write_bytes(b"arquivo-existente")
        solicitar = Mock()
        with patch(
            "watchdog.sqlite3.connect",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            resultado = acionar_recuperacao_banco_ativo(
                self.caminho_banco,
                Path.cwd(),
                enviar=Mock(),
                solicitar=solicitar,
            )

        self.assertEqual(resultado["estado"], "indisponivel_temporario")
        self.assertFalse(resultado["recuperacao_necessaria"])
        solicitar.assert_not_called()

    def test_banco_ativo_ausente_solicita_recuperacao(self):
        enviar = Mock(return_value=True)
        solicitar = Mock()

        resultado = acionar_recuperacao_banco_ativo(
            self.caminho_banco,
            Path.cwd(),
            enviar=enviar,
            solicitar=solicitar,
        )

        self.assertEqual(resultado["estado"], "banco_ausente")
        self.assertTrue(resultado["recuperacao_necessaria"])
        enviar.assert_called_once()
        solicitar.assert_called_once()

    def test_watchdog_interrompe_auditorias_apos_solicitar_recuperacao(self):
        integridade = {
            "saudavel": False,
            "estado": "corrompido",
            "motivo": "banco_ativo_corrompido",
            "recuperacao_necessaria": True,
            "manutencao_solicitada": True,
        }
        reinicio_pendente = {
            "novo_pid": 456,
            "motivo_reinicio": "instancia_ausente",
            "ultimo_reinicio_em": "2026-08-10T22:10:00",
        }
        anterior = {
            "alertado": True,
            "alerta_saude_incidente_id": "incidente-em-recuperacao",
            "alerta_reinicio_pendente": reinicio_pendente,
            "alertas_reinicio_pendentes": [reinicio_pendente],
            "ultimo_reinicio_em": "2026-08-10T22:10:00",
        }
        gravar = Mock()
        with patch(
            "watchdog.verificar_coleta",
            return_value={"saudavel": True, "motivo": None},
        ), patch(
            "watchdog.carregar_estado_anterior_watchdog",
            return_value=(
                anterior,
                {"origem": "json", "recuperado": False},
            ),
        ), patch(
            "watchdog.acionar_recuperacao_banco_ativo",
            return_value=integridade,
        ), patch(
            "watchdog.gravar_json_atomico", gravar,
        ), patch(
            "watchdog.ARQUIVO_ESTADO_PRE_LIVE_PRECISO",
            self._caminho_pre_live_preciso_isolado(),
        ), patch(
            "watchdog.verificar_validacao"
        ) as validar:
            estado = executar_verificacao()

        self.assertFalse(estado["saudavel"])
        self.assertTrue(estado["recuperacao_automatica_solicitada"])
        self.assertEqual(
            estado["alertas_reinicio_pendentes"], [reinicio_pendente]
        )
        self.assertEqual(
            estado["alerta_saude_incidente_id"],
            "incidente-em-recuperacao",
        )
        gravar.assert_called_once()
        validar.assert_not_called()

    def test_intencao_reinicio_persiste_antes_de_falha_posterior(self):
        reinicio = {
            "novo_pid": 456,
            "motivo_reinicio": "instancia_ausente",
            "ultimo_reinicio_em": "2026-08-10T22:10:00",
        }
        gravar = Mock()
        persistir = Mock(return_value={
            "saudavel": True,
            "estado": "persistido",
            "motivo": None,
            "persistido_em": "2026-08-10T22:10:01",
        })
        with patch(
            "watchdog.verificar_coleta",
            return_value={"saudavel": True, "motivo": None},
        ), patch(
            "watchdog.carregar_estado_anterior_watchdog",
            return_value=(
                {}, {"origem": "vazio", "recuperado": False}
            ),
        ), patch(
            "watchdog.acionar_recuperacao_banco_ativo",
            return_value={"recuperacao_necessaria": False},
        ), patch(
            "watchdog.ler_estado", return_value={"status": "ativo"},
        ), patch(
            "watchdog.monitor_em_inicializacao", return_value=False,
        ), patch(
            "watchdog.tentar_reiniciar_processo", return_value=reinicio,
        ), patch(
            "watchdog.enviar_alerta", return_value=False,
        ), patch(
            "watchdog.gravar_json_atomico", gravar,
        ), patch(
            "watchdog.persistir_estado_watchdog_sqlite", persistir,
        ), patch(
            "watchdog.ARQUIVO_ESTADO_PRE_LIVE_PRECISO",
            self._caminho_pre_live_preciso_isolado(),
        ), patch(
            "watchdog.persistir_conclusao_experimento_filtro",
            side_effect=RuntimeError("falha posterior"),
        ):
            with self.assertRaisesRegex(RuntimeError, "falha posterior"):
                executar_verificacao()

        persistir.assert_called_once()
        gravar.assert_called_once()
        antecipado = gravar.call_args.args[1]
        self.assertEqual(
            antecipado["alertas_reinicio_pendentes"], [reinicio]
        )
        self.assertEqual(
            antecipado["alerta_reinicio_pendente"], reinicio
        )

    def test_detecta_coleta_saudavel(self):
        agora = datetime(2026, 7, 20, 20, 0)
        self.caminho.write_text(
            json.dumps(
                {
                    "em": (agora - timedelta(seconds=60)).isoformat(),
                    "evento": "ciclo_concluido",
                    "partidas": 18,
                    "tarefas_processadas": 5,
                }
            ),
            encoding="utf-8",
        )
        estado = verificar_coleta(self.caminho, agora)
        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["partidas_ultimo_ciclo"], 18)
        self.assertEqual(estado["tarefas_processadas_ultimo_ciclo"], 5)

    def test_coleta_expoe_diagnostico_v2b_do_ultimo_ciclo(self):
        agora = datetime(2026, 7, 20, 20, 0)
        diagnostico = {
            "avaliacoes": 3,
            "gerados": 1,
            "por_mercado": {
                "gol_ft": {
                    "avaliacoes": 3,
                    "gerados": 1,
                    "motivos": {"pressao_insuficiente": 2},
                }
            },
        }
        self.caminho.write_text(json.dumps({
            "em": (agora - timedelta(seconds=60)).isoformat(),
            "evento": "ciclo_concluido",
            "gols_capacidade_contextual_v2": diagnostico,
        }), encoding="utf-8")

        estado = verificar_coleta(self.caminho, agora)

        self.assertEqual(
            diagnostico, estado["gols_capacidade_contextual_v2"]
        )

    def test_coleta_expoe_fonte_thestatsapi_do_ultimo_ciclo(self):
        agora = datetime(2026, 7, 20, 20, 0)
        diagnostico = {
            "estado": "coleta_oficial",
            "ativa": True,
            "disponivel": True,
            "aplicacao_sinais": True,
            "telegram": True,
            "calibracao": False,
            "substitui_packball": False,
            "sem_autorizacao_sinal": False,
            "modo": "oficial_fail_closed",
            "partidas_com_odds": 13,
            "ofertas_odds_persistidas": 301,
        }
        self.caminho.write_text(json.dumps({
            "em": (agora - timedelta(seconds=60)).isoformat(),
            "evento": "ciclo_concluido",
            "thestatsapi_sombra": diagnostico,
        }), encoding="utf-8")

        estado = verificar_coleta(self.caminho, agora)

        self.assertEqual(diagnostico, estado["thestatsapi_sombra"])

    def test_coleta_expoe_fonte_betsapi_do_ultimo_ciclo(self):
        agora = datetime(2026, 7, 20, 20, 0)
        diagnostico = {
            "ativa": True,
            "aplicacao_sinais": True,
            "uso_hora": 30,
            "limite_hora": 3000,
            "uso_dia": 120,
            "limite_diario": 50000,
            "circuito_aberto": False,
        }
        self.caminho.write_text(json.dumps({
            "em": (agora - timedelta(seconds=60)).isoformat(),
            "evento": "ciclo_concluido",
            "betsapi": diagnostico,
        }), encoding="utf-8")

        estado = verificar_coleta(self.caminho, agora)

        self.assertEqual(diagnostico, estado["betsapi"])

    def test_watchdog_impede_segunda_instancia(self):
        primeira = TravaInstancia(self.caminho_trava)
        self.assertTrue(primeira.adquirir())
        try:
            with patch("watchdog.ARQUIVO_TRAVA", self.caminho_trava), patch(
                "watchdog.executar_verificacao"
            ) as executar, patch("sys.argv", ["watchdog.py", "--uma-vez"]):
                main_watchdog()
            executar.assert_not_called()
        finally:
            primeira.liberar()

    def test_watchdog_registra_hash_do_codigo_carregado(self):
        with patch(
            "watchdog.ARQUIVO_TRAVA", self.caminho_trava
        ), patch(
            "watchdog.ARQUIVO_PROCESSO_WATCHDOG", self.caminho_processo
        ), patch(
            "watchdog.executar_loop", return_value={"ciclos": 1}
        ), patch("sys.argv", ["watchdog.py", "--uma-vez"]):
            main_watchdog()

        estado = json.loads(
            self.caminho_processo.read_text(encoding="utf-8")
        )
        self.assertEqual(estado["status"], "encerrado")
        self.assertRegex(estado["codigo_hash"], r"^[0-9a-f]{64}$")

    def test_reinicio_isolado_aceita_somente_pid_alvo_exato(self):
        caminho = self.caminho_reinicio
        caminho.write_text(json.dumps({
            "estado": "solicitado", "pid_alvo": 321,
        }), encoding="utf-8")

        self.assertTrue(
            reinicio_isolado_watchdog_solicitado(caminho, pid=321)
        )
        self.assertFalse(
            reinicio_isolado_watchdog_solicitado(caminho, pid=322)
        )

    def test_reinicio_isolado_rejeita_pedido_invalido(self):
        caminho = self.caminho_reinicio
        caminho.write_text("{invalido", encoding="utf-8")

        self.assertFalse(
            reinicio_isolado_watchdog_solicitado(caminho, pid=321)
        )

    def test_loop_se_recupera_de_falha_interna_transitoria(self):
        mensagens = []
        with patch(
            "watchdog.executar_verificacao",
            side_effect=[RuntimeError("temporária"), {"saudavel": True}],
        ):
            resultado = executar_loop(
                limite_ciclos=2,
                dormir=lambda _: None,
                enviar=lambda texto: mensagens.append(texto) or True,
                modo_manutencao_fn=lambda: False,
            )
        self.assertEqual(resultado["ciclos"], 2)
        self.assertEqual(resultado["falhas_consecutivas"], 0)
        self.assertEqual(resultado["recuperacoes"], 1)
        self.assertEqual(len(mensagens), 2)

    def test_loop_aceita_estado_com_emoji_em_stream_cp1252(self):
        bruto = io.BytesIO()
        stream = io.TextIOWrapper(
            bruto, encoding="cp1252", errors="strict"
        )
        mensagens = []
        try:
            with patch(
                "watchdog.executar_verificacao",
                return_value={"resumo": chr(0x1F4CB)},
            ), patch("watchdog.sys.stdout", stream):
                resultado = executar_loop(
                    uma_vez=True,
                    enviar=lambda texto: mensagens.append(texto) or True,
                    modo_manutencao_fn=lambda: False,
                )
            stream.flush()
            saida = bruto.getvalue().decode("cp1252")
        finally:
            stream.detach()

        self.assertEqual(resultado["falhas_consecutivas"], 0)
        self.assertEqual(resultado["recuperacoes"], 0)
        self.assertEqual(mensagens, [])
        self.assertIn(r"\U0001f4cb", saida)

    def test_loop_encerra_limpo_em_modo_manutencao(self):
        with patch("watchdog.executar_verificacao") as executar:
            resultado = executar_loop(
                limite_ciclos=2,
                dormir=lambda _: None,
                modo_manutencao_fn=lambda: True,
            )

        self.assertEqual(resultado["ciclos"], 0)
        self.assertTrue(resultado["encerrado_por_manutencao"])
        executar.assert_not_called()

    def test_loop_interrompe_espera_assim_que_manutencao_e_solicitada(self):
        dormir = Mock()
        manutencao = Mock(side_effect=[False, False, True])
        with patch(
            "watchdog.executar_verificacao",
            return_value={"saudavel": True},
        ) as executar:
            resultado = executar_loop(
                limite_ciclos=2,
                intervalo_segundos=60,
                dormir=dormir,
                modo_manutencao_fn=manutencao,
            )

        self.assertEqual(resultado["ciclos"], 1)
        self.assertTrue(resultado["encerrado_por_manutencao"])
        executar.assert_called_once_with()
        dormir.assert_called_once_with(1.0)

    def test_detecta_coleta_parada(self):
        agora = datetime(2026, 7, 20, 20, 0)
        self.caminho.write_text(
            json.dumps(
                {
                    "em": (agora - timedelta(minutes=10)).isoformat(),
                    "evento": "ciclo_concluido",
                }
            ),
            encoding="utf-8",
        )
        estado = verificar_coleta(self.caminho, agora)
        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "coleta_parada")

    def test_ciclo_longo_com_progresso_recente_permanece_saudavel(self):
        agora = datetime(2026, 7, 20, 20, 0)
        eventos = [
            {
                "em": (agora - timedelta(minutes=8)).isoformat(),
                "evento": "ciclo_concluido",
            },
            {
                "em": (agora - timedelta(seconds=30)).isoformat(),
                "evento": "ciclo_em_andamento",
                "etapa": "coleta_detalhada",
                "processadas": 4,
                "agendadas": 20,
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_coleta(self.caminho, agora)

        self.assertTrue(estado["saudavel"])
        self.assertTrue(estado["ciclo_em_andamento"])
        self.assertEqual(estado["etapa_atual"], "coleta_detalhada")
        self.assertEqual(estado["idade_progresso"], 30.0)

    def test_ciclo_longo_permanece_saudavel_quando_log_gira(self):
        agora = datetime(2026, 7, 20, 20, 0)
        Path(f"{self.caminho}.1").write_text(
            json.dumps({
                "em": (agora - timedelta(minutes=8)).isoformat(),
                "evento": "ciclo_concluido",
                "partidas": 18,
            }),
            encoding="utf-8",
        )
        self.caminho.write_text(
            json.dumps({
                "em": (agora - timedelta(seconds=30)).isoformat(),
                "evento": "ciclo_em_andamento",
                "etapa": "coleta_detalhada",
                "processadas": 4,
                "agendadas": 20,
            }),
            encoding="utf-8",
        )

        estado = verificar_coleta(self.caminho, agora)

        self.assertTrue(estado["saudavel"])
        self.assertTrue(estado["ciclo_em_andamento"])
        self.assertEqual(estado["partidas_ultimo_ciclo"], 18)

    def test_falha_apos_rotacao_conta_desde_ultimo_sucesso(self):
        agora = datetime(2026, 7, 20, 20, 0)
        Path(f"{self.caminho}.1").write_text(
            json.dumps({
                "em": (agora - timedelta(minutes=10)).isoformat(),
                "evento": "ciclo_concluido",
            }),
            encoding="utf-8",
        )
        self.caminho.write_text(
            json.dumps({
                "em": (agora - timedelta(seconds=30)).isoformat(),
                "evento": "ciclo_falhou",
            }),
            encoding="utf-8",
        )

        estado = verificar_coleta(self.caminho, agora)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["falhas_consecutivas"], 1)

    def test_progresso_vencido_nao_mascara_coleta_parada(self):
        agora = datetime(2026, 7, 20, 20, 0)
        eventos = [
            {
                "em": (agora - timedelta(minutes=8)).isoformat(),
                "evento": "ciclo_concluido",
            },
            {
                "em": (agora - timedelta(minutes=3)).isoformat(),
                "evento": "ciclo_em_andamento",
                "etapa": "coleta_detalhada",
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_coleta(self.caminho, agora)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "coleta_parada")
        self.assertFalse(estado["ciclo_em_andamento"])

    def test_falha_posterior_ao_progresso_nao_e_mascarada(self):
        agora = datetime(2026, 7, 20, 20, 0)
        eventos = [
            {
                "em": (agora - timedelta(minutes=8)).isoformat(),
                "evento": "ciclo_concluido",
            },
            {
                "em": (agora - timedelta(seconds=40)).isoformat(),
                "evento": "ciclo_em_andamento",
                "etapa": "coleta_detalhada",
            },
            {
                "em": (agora - timedelta(seconds=20)).isoformat(),
                "evento": "ciclo_falhou",
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_coleta(self.caminho, agora)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "coleta_parada")
        self.assertFalse(estado["ciclo_em_andamento"])

    def test_erros_recentes_nao_disfarcam_sucesso_antigo(self):
        agora = datetime(2026, 7, 20, 20, 0)
        eventos = [
            {
                "em": (agora - timedelta(minutes=10)).isoformat(),
                "evento": "ciclo_concluido",
            },
            {
                "em": (agora - timedelta(seconds=30)).isoformat(),
                "evento": "ciclo_falhou",
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos), encoding="utf-8"
        )
        estado = verificar_coleta(self.caminho, agora)
        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "coleta_parada")
        self.assertEqual(estado["falhas_consecutivas"], 1)

    def test_pausa_preventiva_recente_mantem_coleta_saudavel(self):
        agora = datetime(2026, 7, 20, 20, 0)
        eventos = [
            {
                "em": (agora - timedelta(minutes=8)).isoformat(),
                "evento": "ciclo_concluido",
            },
            {
                "em": (agora - timedelta(seconds=30)).isoformat(),
                "evento": "ciclo_pausado_packball",
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )
        estado = verificar_coleta(self.caminho, agora)
        self.assertTrue(estado["saudavel"])
        self.assertTrue(estado["pausa_preventiva"])

    def test_pausa_protegida_reinicia_contagem_de_falhas(self):
        agora = datetime(2026, 7, 20, 20, 0)
        eventos = [{
            "em": (agora - timedelta(minutes=4)).isoformat(),
            "evento": "ciclo_concluido",
        }]
        eventos.extend([
            {
                "em": (agora - timedelta(minutes=3, seconds=indice)).isoformat(),
                "evento": "ciclo_falhou",
                "erro": "PackBallListaNaoValidadaError",
            }
            for indice in range(3)
        ])
        eventos.extend([
            {
                "em": (agora - timedelta(minutes=2)).isoformat(),
                "evento": "ciclo_pausado_packball",
            },
            {
                "em": (agora - timedelta(seconds=30)).isoformat(),
                "evento": "ciclo_falhou",
                "erro": "PackBallListaNaoValidadaError",
            },
        ])
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_coleta(self.caminho, agora)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["falhas_consecutivas"], 1)

    def test_erros_legados_do_teto_local_nao_bloqueiam_reinicio(self):
        agora = datetime(2026, 7, 20, 20, 0)
        eventos = [{
            "em": (agora - timedelta(minutes=5)).isoformat(),
            "evento": "ciclo_concluido",
        }]
        eventos.extend([
            {
                "em": (agora - timedelta(seconds=60 - indice)).isoformat(),
                "evento": "ciclo_falhou",
                "erro": "PackBallBloqueadoError",
                "mensagem": (
                    "Pausa preventiva do PackBall: teto local atingido"
                    if indice == 0 else
                    "Circuit breaker do PackBall ativo; aguarde"
                ),
            }
            for indice in range(3)
        ])
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )
        estado = verificar_coleta(self.caminho, agora)
        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["falhas_consecutivas"], 0)

    def test_capacidade_alerta_apos_tres_ciclos_adiando(self):
        eventos = [
            {
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 20,
                "tarefas_processadas": 15,
                "tarefas_adiadas": 5,
            }
            for indice in range(3)
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "capacidade_coleta_saturada")

    def test_ciclo_sem_adiamento_recupera_capacidade(self):
        eventos = [
            {
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 20,
                "tarefas_processadas": 15,
                "tarefas_adiadas": 5,
            }
            for indice in range(3)
        ]
        eventos.append({
            "em": "2026-07-20T20:04:00",
            "evento": "ciclo_concluido",
            "tarefas_agendadas": 10,
            "tarefas_processadas": 10,
            "tarefas_adiadas": 0,
        })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_adiando"], 0)

    def test_pausas_preventivas_nao_viram_saturacao(self):
        eventos = [{
            "em": "2026-07-20T20:00:00",
            "evento": "ciclo_concluido",
            "tarefas_agendadas": 5,
            "tarefas_processadas": 5,
            "tarefas_adiadas": 0,
            "duracao_detalhada_segundos": 90,
            "orcamento_detalhado_segundos": 180,
        }]
        for indice in range(1, 4):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 5,
                "tarefas_processadas": 0,
                "tarefas_adiadas": 5,
                "duracao_detalhada_segundos": 2,
                "orcamento_detalhado_segundos": 180,
                "pausa_preventiva": True,
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "protegida_packball")
        self.assertEqual(estado["ciclos_adiando"], 0)
        self.assertEqual(estado["ciclos_pausa_preventiva"], 3)
        self.assertEqual(estado["janela_ciclos_ativos"], 1)

    def test_distribuicao_segura_nao_vira_saturacao(self):
        eventos = [{
            "em": f"2026-07-20T19:5{indice}:00",
            "evento": "ciclo_concluido",
            "tarefas_agendadas": 30,
            "tarefas_processadas": 6,
            "tarefas_adiadas": 24,
            "duracao_detalhada_segundos": 190,
            "orcamento_detalhado_segundos": 180,
        } for indice in range(3)]
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 30,
                "tarefas_processadas": 6,
                "tarefas_adiadas": 24,
                "duracao_detalhada_segundos": 215,
                "orcamento_detalhado_segundos": 180,
                "duracao_tarefa_p95_segundos": 48,
                "ritmo_packball": {
                    "distribuicao_janela_ativa": True,
                    "intervalo_efetivo_segundos": 21.929,
                    "maximo_por_janela": 28,
                    "janela_segundos": 600,
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "limitada_packball")
        self.assertEqual(estado["ciclos_adiando"], 0)
        self.assertEqual(estado["ciclos_limitados_packball"], 3)
        self.assertEqual(estado["janela_ciclos_ativos"], 0)
        self.assertEqual(estado["janela_ciclos_observados"], 6)
        self.assertEqual(
            estado["utilizacao_capacidade_motivo"],
            "limitada_packball",
        )
        self.assertIsNone(estado["utilizacao_media_percentual"])
        self.assertEqual(
            estado["utilizacao_observada_media_percentual"],
            112.5,
        )
        self.assertEqual(
            estado["utilizacao_observada_p95_percentual"],
            119.4,
        )
        self.assertEqual(
            estado["utilizacao_observada_maxima_percentual"],
            119.4,
        )
        self.assertEqual(estado["ciclos_com_excesso_orcamento"], 6)
        self.assertEqual(
            estado["ciclos_excesso_inesperado_consecutivos"], 0
        )
        self.assertEqual(estado["excesso_orcamento_maximo_segundos"], 35.0)

    def test_excesso_maior_que_ultima_tarefa_degrada_apos_tres_ciclos(self):
        eventos = [
            {
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 10,
                "tarefas_processadas": 5,
                "tarefas_adiadas": 5,
                "duracao_detalhada_segundos": 250,
                "orcamento_detalhado_segundos": 180,
                "duracao_tarefa_p95_segundos": 40,
                "ritmo_packball": {
                    "distribuicao_janela_ativa": True,
                },
            }
            for indice in range(3)
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["estado"], "degradada")
        self.assertEqual(
            estado["motivo"],
            "ciclo_excede_orcamento_mais_ultima_tarefa",
        )
        self.assertEqual(
            estado["ciclos_excesso_inesperado_consecutivos"], 3
        )

    def test_capacidade_expoe_reserva_adaptativa_sem_tratar_como_falha(self):
        eventos = [{
            "em": "2026-07-20T20:00:00",
            "evento": "ciclo_concluido",
            "tarefas_agendadas": 10,
            "tarefas_processadas": 4,
            "tarefas_adiadas": 6,
            "duracao_detalhada_segundos": 166,
            "orcamento_detalhado_segundos": 180,
            "duracao_tarefa_p95_segundos": 43,
            "interrompido_por_reserva": True,
            "reserva_admissao_segundos": 46,
            "ritmo_packball": {
                "distribuicao_janela_ativa": True,
            },
        }]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "limitada_packball")
        self.assertEqual(estado["ciclos_reserva_adaptativa"], 1)
        self.assertTrue(estado["ultimo_interrompido_por_reserva"])
        self.assertEqual(estado["ultima_reserva_admissao_segundos"], 46.0)

    def test_fila_antiga_sem_resgate_degrada_apos_tres_ciclos(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 20,
                "tarefas_processadas": 5,
                "tarefas_adiadas": 15,
                "ritmo_packball": {"distribuicao_janela_ativa": True},
                "idade_fila": {
                    "agendadas": {"acima_20_minutos": 8},
                    "processadas": {"acima_20_minutos": 0},
                    "adiadas": {
                        "acima_20_minutos": 8,
                        "maxima_segundos": 3600,
                    },
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "fila_antiga_sem_resgate")
        self.assertEqual(estado["ciclos_sem_resgate_antigo"], 3)
        self.assertEqual(
            estado["idade_fila"]["adiadas"]["maxima_segundos"], 3600
        )

    def test_um_resgate_antigo_recupera_supervisao_da_fila(self):
        eventos = []
        for indice, resgatadas in enumerate((0, 0, 1)):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 20,
                "tarefas_processadas": 5,
                "tarefas_adiadas": 15,
                "ritmo_packball": {"distribuicao_janela_ativa": True},
                "idade_fila": {
                    "agendadas": {"acima_20_minutos": 8},
                    "processadas": {
                        "acima_20_minutos": resgatadas
                    },
                    "adiadas": {"acima_20_minutos": 8 - resgatadas},
                },
                "enriquecimento_api_lote": {
                    "priorizacao": {"atrasada_reservada": True}
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_sem_resgate_antigo"], 0)
        self.assertTrue(estado["priorizacao_fila"]["atrasada_reservada"])

    def test_fila_antiga_expirada_nao_simula_starvation_acionavel(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 7,
                "tarefas_processadas": 4,
                "tarefas_adiadas": 3,
                "ritmo_packball": {
                    "distribuicao_janela_ativa": True,
                },
                "idade_fila": {
                    "agendadas": {"acima_20_minutos": 1},
                    "processadas": {"acima_20_minutos": 0},
                    "adiadas": {"acima_20_minutos": 1},
                },
                "enriquecimento_api_lote": {
                    "priorizacao": {
                        "atrasadas_acima_20_minutos": 1,
                        "atrasadas_acionaveis": 0,
                    },
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_sem_resgate_antigo"], 0)
        self.assertTrue(
            estado["starvation_avalia_somente_acionaveis"]
        )

    def test_telemetria_acionavel_preserva_alerta_de_starvation_real(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 7,
                "tarefas_processadas": 4,
                "tarefas_adiadas": 3,
                "ritmo_packball": {
                    "distribuicao_janela_ativa": True,
                },
                "idade_fila": {
                    "agendadas": {"acima_20_minutos": 2},
                    "processadas": {"acima_20_minutos": 0},
                    "agendadas_acionaveis": {
                        "acima_20_minutos": 1,
                    },
                    "processadas_acionaveis": {
                        "acima_20_minutos": 0,
                    },
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "fila_antiga_sem_resgate")
        self.assertEqual(estado["ciclos_sem_resgate_antigo"], 3)

    def test_rechecagem_pos_evento_sem_processamento_degrada(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 20,
                "tarefas_processadas": 4,
                "tarefas_adiadas": 16,
                "ritmo_packball": {
                    "distribuicao_janela_ativa": True,
                },
                "perfil_agendamento": {
                    "rechecagens_pos_evento_agendadas": 1,
                    "rechecagens_pos_evento_processadas": 0,
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(
            estado["motivo"],
            "rechecagem_pos_evento_sem_processamento",
        )
        self.assertEqual(
            estado["ciclos_sem_rechecagem_pos_evento"], 3
        )

    def test_rechecagem_pos_evento_processada_recupera_supervisao(self):
        eventos = []
        for indice, processadas in enumerate((0, 0, 1)):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 20,
                "tarefas_processadas": 4,
                "tarefas_adiadas": 16,
                "ritmo_packball": {
                    "distribuicao_janela_ativa": True,
                },
                "perfil_agendamento": {
                    "rechecagens_pos_evento_agendadas": 1,
                    "rechecagens_pos_evento_processadas": processadas,
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(
            estado["ciclos_sem_rechecagem_pos_evento"], 0
        )
        self.assertEqual(
            estado["perfil_agendamento"][
                "rechecagens_pos_evento_processadas"
            ],
            1,
        )

    def test_pausa_preventiva_nao_apaga_saturacao_real(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-20T20:0{indice * 2}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 10,
                "tarefas_processadas": 5,
                "tarefas_adiadas": 5,
            })
            if indice < 2:
                eventos.append({
                    "em": f"2026-07-20T20:0{indice * 2 + 1}:00",
                    "evento": "ciclo_concluido",
                    "tarefas_agendadas": 5,
                    "tarefas_processadas": 0,
                    "tarefas_adiadas": 5,
                    "pausa_preventiva": True,
                })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "capacidade_coleta_saturada")
        self.assertEqual(estado["ciclos_adiando"], 3)

    def test_cache_api_alerta_apos_tres_ciclos_com_falha(self):
        eventos = [
            {
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "cache_api_falhas_ciclo": 1,
            }
            for indice in range(3)
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_cache_api_operacional(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(
            estado["motivo"], "cache_api_persistente_indisponivel"
        )
        self.assertEqual(estado["ciclos_com_falha_consecutivos"], 3)

    def test_cache_api_ciclo_sem_falha_recupera_saude(self):
        eventos = [
            {
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "cache_api_falhas_ciclo": 1,
            }
            for indice in range(3)
        ]
        eventos.append({
            "em": "2026-07-20T20:04:00",
            "evento": "ciclo_concluido",
            "cache_api_falhas_ciclo": 0,
        })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_cache_api_operacional(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_com_falha_consecutivos"], 0)

    def test_acompanhamento_preco_ignora_ciclos_sem_demanda(self):
        eventos = [
            {
                "em": "2026-09-01T20:00:00",
                "evento": "ciclo_concluido",
                "perfil_agendamento": {
                    "acompanhamentos_preco_agendados": 1,
                    "acompanhamentos_preco_processados": 1,
                    "acompanhamentos_preco_com_odds": 0,
                    "acompanhamentos_preco_sem_odds": 1,
                    "acompanhamentos_preco_snapshots": 1,
                },
            },
            {
                "em": "2026-09-01T20:01:00",
                "evento": "ciclo_concluido",
                "perfil_agendamento": {
                    "acompanhamentos_preco_agendados": 0,
                    "acompanhamentos_preco_processados": 0,
                    "acompanhamentos_preco_com_odds": 0,
                    "acompanhamentos_preco_sem_odds": 0,
                    "acompanhamentos_preco_snapshots": 0,
                },
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_acompanhamento_preco_pos_alerta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "oscilacao_tolerada")
        self.assertEqual(estado["ciclos_degradados_consecutivos"], 1)
        self.assertFalse(estado["altera_sinais"])

    def test_acompanhamento_preco_alerta_so_apos_tres_falhas_reais(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-09-01T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "perfil_agendamento": {
                    "acompanhamentos_preco_agendados": 2,
                    "acompanhamentos_preco_processados": 2,
                    "acompanhamentos_preco_com_odds": 1,
                    "acompanhamentos_preco_sem_odds": 1,
                    "acompanhamentos_preco_snapshots": 2,
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos[:2]),
            encoding="utf-8",
        )

        oscilacao = verificar_acompanhamento_preco_pos_alerta(self.caminho)

        self.assertTrue(oscilacao["saudavel"])
        self.assertEqual(oscilacao["ciclos_degradados_consecutivos"], 2)

        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )
        persistente = verificar_acompanhamento_preco_pos_alerta(
            self.caminho
        )

        self.assertFalse(persistente["saudavel"])
        self.assertEqual(
            persistente["motivo"],
            "acompanhamento_preco_pos_alerta_indisponivel",
        )
        self.assertEqual(
            persistente["ciclos_degradados_consecutivos"], 3
        )
        self.assertFalse(persistente["altera_sinais"])

    def test_acompanhamento_preco_recupera_com_coleta_completa(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-09-01T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "perfil_agendamento": {
                    "acompanhamentos_preco_agendados": 1,
                    "acompanhamentos_preco_processados": 1,
                    "acompanhamentos_preco_com_odds": 0,
                    "acompanhamentos_preco_sem_odds": 1,
                    "acompanhamentos_preco_snapshots": 1,
                },
            })
        eventos.append({
            "em": "2026-09-01T20:04:00",
            "evento": "ciclo_concluido",
            "perfil_agendamento": {
                "acompanhamentos_preco_agendados": 1,
                "acompanhamentos_preco_processados": 1,
                "acompanhamentos_preco_com_odds": 1,
                "acompanhamentos_preco_sem_odds": 0,
                "acompanhamentos_preco_snapshots": 1,
            },
        })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_acompanhamento_preco_pos_alerta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "saudavel")
        self.assertEqual(estado["ciclos_degradados_consecutivos"], 0)

    def test_amostragem_referencia_ignora_ciclo_sem_oportunidade(self):
        evento = {
            "em": "2026-09-11T01:00:00",
            "evento": "ciclo_concluido",
            "the_odds_api": {"amostragem_referencia": {
                "ativa": True,
                "elegiveis_betsapi": 0,
                "reservadas": 0,
                "mercados_persistidos_sombra": 0,
                "motivos": {},
            }},
        }
        self.caminho.write_text(json.dumps(evento), encoding="utf-8")

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertTrue(estado["saudavel"])
        self.assertEqual("sem_oportunidade", estado["estado"])
        self.assertFalse(estado["requer_atencao"])
        self.assertFalse(estado["altera_sinais"])

    def test_amostragem_referencia_audita_economia_da_preselecao(self):
        evento = {
            "em": "2026-09-11T01:00:00",
            "evento": "ciclo_concluido",
            "the_odds_api": {"amostragem_referencia": {
                "ativa": True,
                "elegiveis_betsapi": 2,
                "reservadas": 1,
                "mercados_persistidos_sombra": 1,
                "preselecoes_cobertura": 2,
                "preselecoes_cobertas": 1,
                "preselecoes_descartadas": 1,
                "preselecoes_evento": 1,
                "eventos_pareados_pre_reserva": 0,
                "eventos_descartados_pre_reserva": 1,
                "reservas_economizadas": 2,
                "reservas_economizadas_evento": 1,
                "motivos": {"oferta_anexada": 1},
            }},
        }
        self.caminho.write_text(json.dumps(evento), encoding="utf-8")

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertTrue(estado["saudavel"])
        self.assertEqual(2, estado["preselecoes_cobertura"])
        self.assertEqual(1, estado["preselecoes_descartadas"])
        self.assertEqual(1, estado["preselecoes_evento"])
        self.assertEqual(1, estado["eventos_descartados_pre_reserva"])
        self.assertEqual(2, estado["reservas_economizadas"])
        self.assertEqual(1, estado["reservas_economizadas_evento"])
        self.assertFalse(estado["altera_sinais"])

    def test_amostragem_referencia_audita_mercados_e_custo_separados(self):
        evento = {
            "em": "2026-09-11T01:00:00",
            "evento": "ciclo_concluido",
            "the_odds_api": {"amostragem_referencia": {
                "ativa": True,
                "elegiveis_betsapi": 1,
                "reservadas": 1,
                "consultadas": 1,
                "mercados_persistidos_sombra": 2,
                "creditos_estimados_reservados": 3,
                "consultas_combinadas": 1,
                "maximo_mercados_por_consulta": 3,
                "por_mercado": {
                    "gol_ft": {
                        "elegiveis": 1, "consultados": 1, "anexados": 1,
                    },
                    "gol_ht": {
                        "elegiveis": 1, "consultados": 1, "anexados": 1,
                    },
                    "escanteios_ft_asiatico": {
                        "elegiveis": 1, "consultados": 1, "anexados": 0,
                    },
                },
                "motivos": {"oferta_anexada": 1},
            }},
        }
        self.caminho.write_text(json.dumps(evento), encoding="utf-8")

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertTrue(estado["saudavel"])
        self.assertEqual(3, estado["creditos_estimados_reservados"])
        self.assertEqual(1, estado["consultas_combinadas"])
        self.assertEqual(3, estado["maximo_mercados_por_consulta"])
        self.assertEqual(1, estado["por_mercado"]["gol_ht"]["anexados"])
        self.assertEqual(1, estado["ciclos_telemetria_multimercado"])

    def test_amostragem_referencia_rejeita_custo_multimercado_impossivel(self):
        evento = {
            "em": "2026-09-11T01:00:00",
            "evento": "ciclo_concluido",
            "the_odds_api": {"amostragem_referencia": {
                "ativa": True,
                "elegiveis_betsapi": 1,
                "reservadas": 1,
                "consultadas": 1,
                "mercados_persistidos_sombra": 2,
                "creditos_estimados_reservados": 1,
                "consultas_combinadas": 1,
                "maximo_mercados_por_consulta": 2,
                "por_mercado": {
                    "gol_ft": {
                        "elegiveis": 1, "consultados": 1, "anexados": 1,
                    },
                    "gol_ht": {
                        "elegiveis": 1, "consultados": 1, "anexados": 1,
                    },
                },
                "motivos": {"oferta_anexada": 1},
            }},
        }
        self.caminho.write_text(json.dumps(evento), encoding="utf-8")

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertFalse(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertEqual("auditoria_multimercado_invalida", estado["estado"])
        self.assertEqual(
            "amostragem_referencia_multimercado_inconsistente",
            estado["motivo"],
        )

    def test_amostragem_referencia_rejeita_contadores_de_evento(self):
        evento = {
            "em": "2026-09-11T01:00:00",
            "evento": "ciclo_concluido",
            "the_odds_api": {"amostragem_referencia": {
                "ativa": True,
                "elegiveis_betsapi": 1,
                "reservadas": 0,
                "mercados_persistidos_sombra": 0,
                "preselecoes_cobertura": 1,
                "preselecoes_cobertas": 1,
                "preselecoes_descartadas": 0,
                "preselecoes_evento": 1,
                "eventos_pareados_pre_reserva": 1,
                "eventos_descartados_pre_reserva": 1,
                "reservas_economizadas": 0,
                "reservas_economizadas_evento": 0,
                "motivos": {},
            }},
        }
        self.caminho.write_text(json.dumps(evento), encoding="utf-8")

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertFalse(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertEqual(
            "auditoria_preselecao_invalida", estado["estado"]
        )

    def test_amostragem_referencia_rejeita_contadores_de_preselecao(self):
        evento = {
            "em": "2026-09-11T01:00:00",
            "evento": "ciclo_concluido",
            "the_odds_api": {"amostragem_referencia": {
                "ativa": True,
                "elegiveis_betsapi": 1,
                "reservadas": 0,
                "mercados_persistidos_sombra": 0,
                "preselecoes_cobertura": 1,
                "preselecoes_cobertas": 1,
                "preselecoes_descartadas": 1,
                "reservas_economizadas": 2,
                "motivos": {},
            }},
        }
        self.caminho.write_text(json.dumps(evento), encoding="utf-8")

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertFalse(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertEqual(
            "auditoria_preselecao_invalida", estado["estado"]
        )
        self.assertEqual(
            "amostragem_referencia_preselecao_inconsistente",
            estado["motivo"],
        )
        self.assertFalse(estado["telegram"])

    def test_amostragem_referencia_avisa_apos_tres_tentativas_sem_cobertura(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-09-11T01:0{indice}:00",
                "evento": "ciclo_concluido",
                "the_odds_api": {"amostragem_referencia": {
                    "ativa": True,
                    "elegiveis_betsapi": 1,
                    "reservadas": 1,
                    "mercados_persistidos_sombra": 0,
                    "motivos": {"evento_nao_encontrado": 1},
                }},
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertTrue(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertEqual("sem_cobertura_persistente", estado["estado"])
        self.assertEqual(
            "amostragem_referencia_odds_sem_cobertura",
            estado["motivo"],
        )
        self.assertEqual(3, estado[
            "tentativas_sem_cobertura_consecutivas"
        ])
        self.assertFalse(estado["telegram"])

    def test_amostragem_referencia_recupera_quando_persiste_mercado(self):
        eventos = []
        for indice, persistidos in enumerate((0, 0, 1)):
            eventos.append({
                "em": f"2026-09-11T01:0{indice}:00",
                "evento": "ciclo_concluido",
                "the_odds_api": {"amostragem_referencia": {
                    "ativa": True,
                    "elegiveis_betsapi": 1,
                    "reservadas": 1,
                    "mercados_persistidos_sombra": persistidos,
                    "motivos": ({
                        "evento_nao_encontrado": 1
                    } if not persistidos else {"oferta_anexada": 1}),
                }},
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertTrue(estado["saudavel"])
        self.assertFalse(estado["requer_atencao"])
        self.assertEqual("saudavel", estado["estado"])
        self.assertEqual(0, estado[
            "tentativas_sem_cobertura_consecutivas"
        ])

    def test_amostragem_referencia_detecta_falha_tecnica_persistente(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-09-11T01:0{indice}:00",
                "evento": "ciclo_concluido",
                "the_odds_api": {"amostragem_referencia": {
                    "ativa": True,
                    "elegiveis_betsapi": 1,
                    "reservadas": 1,
                    "mercados_persistidos_sombra": 0,
                    "motivos": {"falha_isolada": 1},
                }},
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertFalse(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertEqual("falha_persistente", estado["estado"])
        self.assertEqual(
            "amostragem_referencia_odds_falhou", estado["motivo"]
        )
        self.assertEqual(3, estado["falhas_tecnicas_consecutivas"])
        self.assertFalse(estado["promocao_automatica"])

    def test_amostragem_referencia_avisa_estado_irrecuperavel(self):
        evento = {
            "em": "2026-09-11T01:00:00",
            "evento": "ciclo_concluido",
            "the_odds_api": {
                "controle_estado": {
                    "saudavel": False,
                    "origem": "corrompido",
                    "fail_closed": True,
                },
                "amostragem_referencia": {
                    "ativa": True,
                    "elegiveis_betsapi": 0,
                    "reservadas": 0,
                    "mercados_persistidos_sombra": 0,
                    "motivos": {},
                },
            },
        }
        self.caminho.write_text(json.dumps(evento), encoding="utf-8")

        estado = verificar_amostragem_referencia_odds_sombra(
            self.caminho
        )

        self.assertFalse(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertEqual("controle_estado_invalido", estado["estado"])
        self.assertEqual(
            "the_odds_api_estado_irrecuperavel", estado["motivo"]
        )
        self.assertTrue(estado["controle_estado"]["fail_closed"])
        self.assertFalse(estado["altera_sinais"])

    def test_scanner_so_degrada_apos_tres_ciclos_sem_prioridade(self):
        eventos = [{
            "em": "2026-08-31T20:00:00",
            "evento": "ciclo_concluido",
            "lista_packball": {"scanner": {
                "habilitado": True,
                "estado": "prioridade_carregada",
                "contador_filtrado": 1,
                "jogos_extraidos": 1,
            }},
        }]
        for indice, estado_scanner in enumerate((
            "painel_scanner_nao_validado",
            "fallback_ao_vivo",
            "aba_scanner_ausente",
        ), start=1):
            eventos.append({
                "em": f"2026-08-31T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "lista_packball": {"scanner": {
                    "habilitado": True,
                    "estado": estado_scanner,
                    "contador_filtrado": 1,
                    "jogos_extraidos": 0,
                }},
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos[:2]),
            encoding="utf-8",
        )

        oscilacao = verificar_prioridade_scanner_packball(self.caminho)

        self.assertTrue(oscilacao["saudavel"])
        self.assertEqual(
            oscilacao["ciclos_sem_prioridade_consecutivos"], 1
        )

        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )
        persistente = verificar_prioridade_scanner_packball(self.caminho)

        self.assertFalse(persistente["saudavel"])
        self.assertEqual(
            persistente["motivo"], "prioridade_scanner_indisponivel"
        )
        self.assertEqual(
            persistente["ciclos_sem_prioridade_consecutivos"], 3
        )
        self.assertTrue(persistente["fallback_ao_vivo_ativo"])
        self.assertEqual(
            persistente["episodios_sem_prioridade_observados"], 1
        )
        self.assertEqual(
            persistente["sem_prioridade_desde"],
            "2026-08-31T20:01:00",
        )
        self.assertEqual(
            persistente["duracao_sem_prioridade_segundos"], 120.0
        )
        self.assertEqual(
            persistente["duracao_total_sem_prioridade_segundos"], 120.0
        )

    def test_scanner_recupera_com_prioridade_vazia_carregada(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-08-31T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "lista_packball": {"scanner": {
                    "habilitado": True,
                    "estado": "fallback_ao_vivo",
                    "contador_filtrado": 1,
                    "jogos_extraidos": 0,
                }},
            })
        eventos.append({
            "em": "2026-08-31T20:04:00",
            "evento": "ciclo_concluido",
            "lista_packball": {"scanner": {
                "habilitado": True,
                "estado": "prioridade_carregada",
                "contador_filtrado": 0,
                "jogos_extraidos": 0,
            }},
        })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_prioridade_scanner_packball(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "saudavel")
        self.assertEqual(estado["ciclos_sem_prioridade_consecutivos"], 0)
        self.assertEqual(estado["contador_filtrado_ultimo_ciclo"], 0)
        self.assertEqual(estado["episodios_sem_prioridade_observados"], 1)
        self.assertEqual(estado["duracao_sem_prioridade_segundos"], 0.0)
        self.assertEqual(
            estado["duracao_total_sem_prioridade_segundos"], 240.0
        )

    def test_scanner_desativado_nao_gera_falso_alerta(self):
        self.caminho.write_text(json.dumps({
            "em": "2026-08-31T20:00:00",
            "evento": "ciclo_concluido",
            "lista_packball": {"scanner": {
                "habilitado": False,
                "estado": "desativado",
            }},
        }), encoding="utf-8")

        estado = verificar_prioridade_scanner_packball(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "desativado")

    def test_fontes_sinais_exigem_falha_persistente_para_alertar(self):
        eventos = [
            {
                "em": "2026-08-01T10:00:00",
                "evento": "ciclo_concluido",
                "saude_api": {"saudavel": True, "motivo": None},
                "sinais_bloqueados_fontes": 0,
            },
            {
                "em": "2026-08-01T10:03:00",
                "evento": "ciclo_concluido",
                "saude_api": {
                    "saudavel": False,
                    "motivo": "falha_api_no_ciclo",
                },
                "sinais_bloqueados_fontes": 2,
                "motivos_bloqueio_fontes": {
                    "falha_api_no_ciclo": 2
                },
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        transitório = verificar_fontes_sinais_operacionais(self.caminho)
        self.assertTrue(transitório["saudavel"])
        self.assertEqual(
            transitório["ciclos_degradados_consecutivos"], 1
        )

        with self.caminho.open("a", encoding="utf-8") as arquivo:
            arquivo.write("\n" + json.dumps({
                "em": "2026-08-01T10:06:00",
                "evento": "ciclo_concluido",
                "saude_api": {
                    "saudavel": False,
                    "motivo": "falha_api_no_ciclo",
                },
                "sinais_bloqueados_fontes": 1,
                "motivos_bloqueio_fontes": {
                    "falha_api_no_ciclo": 1
                },
            }))

        persistente = verificar_fontes_sinais_operacionais(self.caminho)
        self.assertFalse(persistente["saudavel"])
        self.assertEqual(
            persistente["motivo"], "fontes_sinais_indisponiveis"
        )

    def test_fontes_sinais_recuperam_com_ciclo_saudavel(self):
        eventos = [
            {
                "evento": "ciclo_concluido",
                "saude_api": {"saudavel": False},
                "sinais_bloqueados_fontes": 1,
            },
            {
                "evento": "ciclo_concluido",
                "saude_api": {"saudavel": False},
                "sinais_bloqueados_fontes": 1,
            },
            {
                "evento": "ciclo_concluido",
                "saude_api": {"saudavel": True},
                "sinais_bloqueados_fontes": 0,
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_fontes_sinais_operacionais(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_degradados_consecutivos"], 0)

    def test_api_nao_confirmada_sem_jogos_nao_cria_falha_de_fonte(self):
        eventos = [
            {
                "evento": "ciclo_concluido",
                "partidas": 0,
                "tarefas_agendadas": 0,
                "saude_api": {
                    "saudavel": False,
                    "motivo": "api_ainda_nao_confirmada",
                },
                "sinais_bloqueados_fontes": 0,
            },
            {
                "evento": "ciclo_concluido",
                "partidas": 0,
                "tarefas_agendadas": 0,
                "saude_api": {
                    "saudavel": False,
                    "motivo": "api_ainda_nao_confirmada",
                },
                "sinais_bloqueados_fontes": 0,
            },
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_fontes_sinais_operacionais(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_degradados_consecutivos"], 0)

    def test_betsapi_oficial_cobre_cota_api_football_esgotada(self):
        eventos = [
            {
                "evento": "ciclo_concluido",
                "partidas": 20,
                "tarefas_agendadas": 10,
                "saude_api": {
                    "saudavel": False,
                    "motivo": "cota_api_segura_esgotada",
                },
                "betsapi": {
                    "ativa": True,
                    "aplicacao_sinais": True,
                    "circuito_aberto": False,
                },
                "sinais_bloqueados_fontes": 0,
            }
            for _ in range(2)
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_fontes_sinais_operacionais(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_degradados_consecutivos"], 0)
        self.assertTrue(estado["betsapi_oficial_ultimo_ciclo"])

    def test_betsapi_nao_mascara_sinais_realmente_bloqueados(self):
        eventos = [
            {
                "evento": "ciclo_concluido",
                "saude_api": {
                    "saudavel": False,
                    "motivo": "cota_api_segura_esgotada",
                },
                "betsapi": {
                    "ativa": True,
                    "aplicacao_sinais": True,
                    "circuito_aberto": False,
                },
                "sinais_bloqueados_fontes": 1,
            }
            for _ in range(2)
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_fontes_sinais_operacionais(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["ciclos_degradados_consecutivos"], 2)

    def test_betsapi_com_estado_nao_persistido_nao_mascara_api_degradada(self):
        eventos = [
            {
                "evento": "ciclo_concluido",
                "partidas": 20,
                "tarefas_agendadas": 10,
                "saude_api": {
                    "saudavel": False,
                    "motivo": "cota_api_segura_esgotada",
                },
                "betsapi": {
                    "ativa": True,
                    "aplicacao_sinais": True,
                    "circuito_aberto": False,
                    "circuito": {"persistencia_saudavel": False},
                },
                "sinais_bloqueados_fontes": 0,
            }
            for _ in range(2)
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_fontes_sinais_operacionais(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["ciclos_degradados_consecutivos"], 2)
        self.assertFalse(estado["betsapi_oficial_ultimo_ciclo"])

    def test_pressao_consecutiva_alerta_antes_de_adiar(self):
        eventos = []
        for indice, duracao in enumerate((154, 160, 170)):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 10,
                "tarefas_processadas": 10,
                "tarefas_adiadas": 0,
                "duracao_detalhada_segundos": duracao,
                "orcamento_detalhado_segundos": 180,
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["estado"], "degradada")
        self.assertEqual(
            estado["motivo"], "orcamento_coleta_proximo_limite"
        )
        self.assertEqual(estado["ciclos_sob_pressao"], 3)
        self.assertEqual(estado["utilizacao_p95_percentual"], 94.4)
        self.assertEqual(
            estado["utilizacao_observada_p95_percentual"],
            94.4,
        )

    def test_ciclos_ociosos_nao_criam_nem_apagam_pressao_ativa(self):
        eventos = []
        for indice, duracao in enumerate((154, 160)):
            eventos.extend((
                {
                    "em": f"2026-07-20T20:0{indice * 2}:00",
                    "evento": "ciclo_concluido",
                    "tarefas_agendadas": 10,
                    "tarefas_processadas": 10,
                    "tarefas_adiadas": 0,
                    "duracao_detalhada_segundos": duracao,
                    "orcamento_detalhado_segundos": 180,
                },
                {
                    "em": f"2026-07-20T20:0{indice * 2 + 1}:00",
                    "evento": "ciclo_concluido",
                    "tarefas_agendadas": 0,
                    "tarefas_processadas": 0,
                    "tarefas_adiadas": 0,
                    "duracao_detalhada_segundos": 0,
                    "orcamento_detalhado_segundos": 180,
                },
            ))
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_sob_pressao"], 2)
        self.assertEqual(estado["janela_ciclos_ativos"], 2)

    def test_ciclo_ativo_rapido_recupera_alerta_de_pressao(self):
        eventos = []
        for indice, duracao in enumerate((154, 160, 170, 30)):
            eventos.append({
                "em": f"2026-07-20T20:0{indice}:00",
                "evento": "ciclo_concluido",
                "tarefas_agendadas": 10,
                "tarefas_processadas": 10,
                "tarefas_adiadas": 0,
                "duracao_detalhada_segundos": duracao,
                "orcamento_detalhado_segundos": 180,
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_capacidade_coleta(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["ciclos_sob_pressao"], 0)

    def test_tres_falhas_consecutivas_degradam_mesmo_com_sucesso_recente(self):
        agora = datetime(2026, 7, 20, 20, 0)
        eventos = [{
            "em": (agora - timedelta(seconds=60)).isoformat(),
            "evento": "ciclo_concluido",
        }]
        eventos.extend(
            {
                "em": (agora - timedelta(seconds=indice * 10)).isoformat(),
                "evento": "ciclo_falhou",
            }
            for indice in (3, 2, 1)
        )
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos), encoding="utf-8"
        )
        estado = verificar_coleta(self.caminho, agora)
        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "falhas_consecutivas")

    def test_backup_ausente_tem_tolerancia_ao_virar_o_dia(self):
        estado = verificar_backup_diario(
            self.pasta_backups, datetime(2026, 7, 21, 0, 5)
        )
        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "aguardando")

    def test_backup_ausente_depois_da_tolerancia_requer_atencao(self):
        estado = verificar_backup_diario(
            self.pasta_backups, datetime(2026, 7, 21, 0, 11)
        )
        self.assertFalse(estado["saudavel"])
        self.assertEqual(estado["motivo"], "backup_diario_ausente")

    def test_backup_diario_valido_e_reconhecido(self):
        agora = datetime(2026, 7, 21, 1, 0)
        banco = BancoMonitor(self.caminho_banco)
        try:
            BackupBanco(self.pasta_backups).criar_diario(
                banco.conexao, agora
            )
        finally:
            banco.fechar()

        estado = verificar_backup_diario(self.pasta_backups, agora)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "valido")

    def test_backup_inalterado_reutiliza_verificacao_de_integridade(self):
        agora = datetime(2026, 7, 21, 1, 0)
        banco = BancoMonitor(self.caminho_banco)
        try:
            BackupBanco(self.pasta_backups).criar_diario(
                banco.conexao, agora
            )
        finally:
            banco.fechar()
        cache = {}

        with patch(
            "watchdog.verificar_arquivo_backup",
            wraps=__import__("backup_banco").verificar_arquivo_backup,
        ) as verificar:
            primeiro = verificar_backup_diario(
                self.pasta_backups, agora, cache=cache
            )
            segundo = verificar_backup_diario(
                self.pasta_backups, agora, cache=cache
            )

            self.assertTrue(primeiro["saudavel"])
            self.assertEqual(primeiro, segundo)
            verificar.assert_called_once()

    def test_backup_compactado_e_reconhecido_no_diario_e_rpo(self):
        agora = datetime(2026, 7, 21, 6, 5)
        banco = BancoMonitor(self.caminho_banco)
        try:
            caminho, _ = BackupBanco(
                self.pasta_backups, compactar=True
            ).criar_diario(banco.conexao, agora)
        finally:
            banco.fechar()

        diario = verificar_backup_diario(
            self.pasta_backups, agora, cache={}
        )
        rpo = verificar_ponto_recuperacao(
            self.pasta_backups, agora + timedelta(hours=1), cache={}
        )

        self.assertTrue(caminho.name.endswith(".db.gz"))
        self.assertTrue(diario["saudavel"])
        self.assertTrue(rpo["saudavel"])
        self.assertEqual(Path(diario["caminho"]), caminho)

    def test_ponto_recuperacao_respeita_rpo_de_seis_horas(self):
        backup = BackupBanco(self.pasta_backups)
        banco = BancoMonitor(self.caminho_banco)
        try:
            backup.criar_periodico(
                banco.conexao, datetime(2026, 7, 21, 6, 5)
            )
        finally:
            banco.fechar()

        recente = verificar_ponto_recuperacao(
            self.pasta_backups, datetime(2026, 7, 21, 12, 15), cache={}
        )
        antigo = verificar_ponto_recuperacao(
            self.pasta_backups, datetime(2026, 7, 21, 12, 21), cache={}
        )

        self.assertTrue(recente["saudavel"])
        self.assertFalse(antigo["saudavel"])
        self.assertEqual(
            antigo["motivo"], "ponto_recuperacao_desatualizado"
        )

    def test_armazenamento_saudavel_informa_wal_e_espaco(self):
        (self.pasta_backups / "monitor_teste.db").write_bytes(
            b"x" * 1024 * 1024
        )
        with patch(
            "watchdog.shutil.disk_usage",
            return_value=SimpleNamespace(free=2048 * 1024 * 1024),
        ):
            estado = verificar_armazenamento(
                Path.cwd(), self.caminho_banco,
                pasta_backups=self.pasta_backups,
            )

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["livre_mb"], 2048.0)
        self.assertEqual(estado["wal_mb"], 0.0)
        self.assertEqual(estado["backups_mb"], 1.0)
        self.assertEqual(estado["backups_arquivos"], 1)
        self.assertTrue(estado["retencao_backups"]["saudavel"])
        self.assertTrue(
            estado["retencao_backups"]["aplicacao_automatica"]
        )
        self.assertEqual(
            estado["metrica_versao"],
            "armazenamento-com-backups-v4-compactacao",
        )
        self.assertEqual(
            estado["estado_compactacao"],
            "aguardando_primeiro_backup_novo",
        )
        self.assertTrue(estado["primeiro_backup_compacto_pendente"])

    def test_pouco_espaco_degrada_operacao(self):
        with patch(
            "watchdog.shutil.disk_usage",
            return_value=SimpleNamespace(free=100 * 1024 * 1024),
        ):
            estado = verificar_armazenamento(
                Path.cwd(), self.caminho_banco,
                pasta_backups=self.pasta_backups,
            )

        self.assertFalse(estado["saudavel"])
        self.assertIn("espaco_disco_baixo", estado["motivos"])

    def test_wal_excessivo_degrada_operacao(self):
        caminho_wal = Path(f"{self.caminho_banco}-wal")
        caminho_wal.write_bytes(b"x")
        with patch(
            "watchdog.shutil.disk_usage",
            return_value=SimpleNamespace(free=2048 * 1024 * 1024),
        ), patch.object(Path, "stat") as estatistica:
            estatistica.return_value = SimpleNamespace(
                st_size=600 * 1024 * 1024
            )
            estado = verificar_armazenamento(
                Path.cwd(), self.caminho_banco,
                pasta_backups=self.pasta_backups,
            )

        self.assertFalse(estado["saudavel"])
        self.assertIn("wal_excessivo", estado["motivos"])

    def test_pareamento_api_detecta_colapso_relativo_a_base(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-21T10:0{indice}:00",
                "evento": "ciclo_concluido",
                "associacoes_api": {"associado": 8, "sem_fixtures": 2},
            })
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-21T11:0{indice}:00",
                "evento": "ciclo_concluido",
                "associacoes_api": {
                    "associado": 1, "nomes_incompativeis": 9,
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_pareamento_api(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(
            estado["motivo"], "cobertura_api_caiu_versus_base"
        )
        self.assertEqual(estado["base"]["taxa_associacao"], 0.8)
        self.assertEqual(estado["recente"]["taxa_associacao"], 0.1)

    def test_pareamento_api_sem_base_nao_gera_falso_alerta(self):
        self.caminho.write_text(
            json.dumps({
                "em": "2026-07-21T11:00:00",
                "evento": "ciclo_concluido",
                "associacoes_api": {"nomes_incompativeis": 10},
            }),
            encoding="utf-8",
        )

        estado = verificar_pareamento_api(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["estado"], "formando_linha_de_base")

    def test_pareamento_api_alerta_erros_repetidos_sem_base(self):
        eventos = [
            {
                "em": f"2026-07-21T11:0{indice}:00",
                "evento": "ciclo_concluido",
                "associacoes_api": {"erro_processamento": 1},
            }
            for indice in range(3)
        ]
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_pareamento_api(self.caminho)

        self.assertFalse(estado["saudavel"])
        self.assertEqual(
            estado["motivo"], "erros_pareamento_api_repetidos"
        )

    def test_pareamento_api_ignora_ciclos_sem_cota_para_consulta(self):
        eventos = []
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-21T10:0{indice}:00",
                "evento": "ciclo_concluido",
                "associacoes_api": {"associado": 8, "sem_fixtures": 2},
                "saude_api": {"saudavel": True, "motivo": None},
            })
        for indice in range(3):
            eventos.append({
                "em": f"2026-07-21T11:0{indice}:00",
                "evento": "ciclo_concluido",
                "associacoes_api": {"sem_fixtures": 10},
                "saude_api": {
                    "saudavel": False,
                    "motivo": "cota_api_segura_esgotada",
                },
            })
        self.caminho.write_text(
            "\n".join(json.dumps(item) for item in eventos),
            encoding="utf-8",
        )

        estado = verificar_pareamento_api(self.caminho)

        self.assertTrue(estado["saudavel"])
        self.assertNotEqual(
            estado["motivo"], "cobertura_api_caiu_versus_base"
        )
        self.assertEqual(estado["recente"]["taxa_associacao"], 0.8)

    def test_calibracao_inativa_inicial_nao_gera_ruido(self):
        enviar = Mock(return_value=True)
        estado = atualizar_alertas_estado_calibracoes(
            {
                "regra_versao": VERSAO_REGRAS,
                "estado_calibracoes": {
                    "gol_ft": {
                        "ativa": False, "amostra": 35,
                        "motivo": "amostra_insuficiente",
                    }
                },
            },
            enviar=enviar,
        )
        enviar.assert_not_called()
        self.assertFalse(
            estado["calibracoes_estado_notificado"]["gol_ft"]
        )

    def test_reprovacao_na_primeira_validacao_final_e_notificada_uma_vez(self):
        enviar = Mock(return_value=True)
        validacao = {
            "regra_versao": VERSAO_REGRAS,
            "estado_calibracoes": {
                "gol_ft": {
                    "ativa": False,
                    "amostra": 100,
                    "amostra_validacao": 30,
                    "roi_validacao_agregado": -0.04,
                    "auc_validacao": 0.48,
                    "motivo": "pontuacao_sem_discriminacao",
                }
            },
        }

        estado = atualizar_alertas_estado_calibracoes(
            dict(validacao), enviar=enviar
        )

        enviar.assert_called_once()
        mensagem = enviar.call_args.args[0]
        self.assertIn("NÃO APROVADA", mensagem)
        self.assertIn("Amostra independente: 100", mensagem)
        self.assertIn("pontuacao_sem_discriminacao", mensagem)
        self.assertIn("não reabrem esta decisão", mensagem)
        self.assertIn("nova política ou linhagem", mensagem)
        self.assertNotIn("reavaliado automaticamente", mensagem)
        self.assertEqual(
            estado["calibracoes_validacao_final_notificada"]["gol_ft"],
            {
                "amostra": 100,
                "motivo": "pontuacao_sem_discriminacao",
            },
        )

        repetido = Mock(return_value=True)
        atualizar_alertas_estado_calibracoes(
            dict(validacao), estado, repetido
        )
        repetido.assert_not_called()

    def test_falha_no_alerta_de_reprovacao_e_tentada_novamente(self):
        validacao = {
            "regra_versao": VERSAO_REGRAS,
            "estado_calibracoes": {
                "gol_ft": {
                    "ativa": False,
                    "amostra": 100,
                    "motivo": "faixas_sem_validacao",
                }
            },
        }
        primeira = Mock(return_value=False)
        estado = atualizar_alertas_estado_calibracoes(
            dict(validacao), enviar=primeira
        )
        self.assertNotIn(
            "gol_ft",
            estado["calibracoes_validacao_final_notificada"],
        )

        segunda = Mock(return_value=True)
        atualizado = atualizar_alertas_estado_calibracoes(
            dict(validacao), estado, segunda
        )
        segunda.assert_called_once()
        self.assertIn(
            "gol_ft",
            atualizado["calibracoes_validacao_final_notificada"],
        )

    def test_ativacao_e_desativacao_calibrada_sao_idempotentes(self):
        inicial = atualizar_alertas_estado_calibracoes(
            {
                "regra_versao": VERSAO_REGRAS,
                "estado_calibracoes": {},
            },
            enviar=Mock(return_value=True),
        )
        enviar_ativacao = Mock(return_value=True)
        ativo = atualizar_alertas_estado_calibracoes(
            {
                "regra_versao": VERSAO_REGRAS,
                "estado_calibracoes": {
                    "gol_ft": {"ativa": True, "amostra": 120}
                },
            },
            inicial,
            enviar_ativacao,
        )
        enviar_ativacao.assert_called_once()
        self.assertIn("ATIVADA", enviar_ativacao.call_args.args[0])

        repetido = Mock(return_value=True)
        ativo_novamente = atualizar_alertas_estado_calibracoes(
            {
                "regra_versao": VERSAO_REGRAS,
                "estado_calibracoes": {
                    "gol_ft": {"ativa": True, "amostra": 121}
                },
            },
            ativo,
            repetido,
        )
        repetido.assert_not_called()

        enviar_desativacao = Mock(return_value=True)
        inativo = atualizar_alertas_estado_calibracoes(
            {
                "regra_versao": VERSAO_REGRAS,
                "estado_calibracoes": {
                    "gol_ft": {
                        "ativa": False, "amostra": 122,
                        "motivo": "drift_desempenho_recente",
                    }
                },
            },
            ativo_novamente,
            enviar_desativacao,
        )
        enviar_desativacao.assert_called_once()
        self.assertIn("DESATIVADA", enviar_desativacao.call_args.args[0])
        self.assertFalse(
            inativo["calibracoes_estado_notificado"]["gol_ft"]
        )

    def test_alerta_ativacao_exibe_metricas_da_validacao_final(self):
        enviar = Mock(return_value=True)

        atualizar_alertas_estado_calibracoes(
            {
                "regra_versao": VERSAO_REGRAS,
                "estado_calibracoes": {
                    "gol_ft": {
                        "ativa": True,
                        "amostra": 120,
                        "amostra_validacao": 36,
                        "roi_validacao_agregado": 0.081,
                        "auc_validacao": 0.67,
                    }
                },
            },
            enviar=enviar,
        )

        mensagem = enviar.call_args.args[0]
        self.assertIn("36 resultado(s)", mensagem)
        self.assertIn("ROI da validação: 0.081", mensagem)
        self.assertIn("AUC da validação: 0.67", mensagem)

    def test_falha_telegram_na_ativacao_e_tentada_novamente(self):
        anterior = {
            "regra_versao_estado_calibracoes": VERSAO_REGRAS,
            "calibracoes_estado_notificado": {"gol_ft": False},
        }
        validacao = {
            "regra_versao": VERSAO_REGRAS,
            "estado_calibracoes": {
                "gol_ft": {"ativa": True, "amostra": 100}
            },
        }
        primeira = Mock(return_value=False)
        estado = atualizar_alertas_estado_calibracoes(
            dict(validacao), anterior, primeira
        )
        self.assertFalse(
            estado["calibracoes_estado_notificado"]["gol_ft"]
        )
        segunda = Mock(return_value=True)
        atualizar_alertas_estado_calibracoes(
            dict(validacao), estado, segunda
        )
        segunda.assert_called_once()

    def test_nova_populacao_na_mesma_regra_tem_estado_calibrado_independente(self):
        anterior = {
            "regra_versao_estado_calibracoes": VERSAO_REGRAS,
            "amostra_oficial_id_estado_calibracoes": "populacao-v6",
            "calibracoes_estado_notificado": {"gol_ft": True},
        }
        enviar = Mock(return_value=True)

        atual = atualizar_alertas_estado_calibracoes(
            {
                "regra_versao": VERSAO_REGRAS,
                "amostra_oficial_id": "populacao-v7",
                "estado_calibracoes": {
                    "gol_ft": {"ativa": True, "amostra": 110}
                },
            },
            anterior,
            enviar,
        )

        enviar.assert_called_once()
        self.assertIn("ATIVADA", enviar.call_args.args[0])
        self.assertEqual(
            atual["amostra_oficial_id_estado_calibracoes"], "populacao-v7"
        )

    def test_nova_politica_preserva_estado_da_mesma_populacao(self):
        anterior = {
            "regra_versao_estado_calibracoes": VERSAO_REGRAS,
            "amostra_oficial_id_estado_calibracoes": (
                f"{VERSAO_REGRAS}|calibracao-antiga|fingerprint|inicio"
            ),
            "calibracoes_estado_notificado": {"gol_ft": False},
        }
        enviar = Mock(return_value=True)

        atual = atualizar_alertas_estado_calibracoes(
            {
                "regra_versao": VERSAO_REGRAS,
                "amostra_oficial_id": (
                    f"{VERSAO_REGRAS}|calibracao-nova|fingerprint|inicio"
                ),
                "estado_calibracoes": {
                    "gol_ft": {
                        "ativa": False,
                        "amostra": 88,
                        "motivo": "amostra_insuficiente",
                    }
                },
            },
            anterior,
            enviar,
        )

        enviar.assert_not_called()
        self.assertFalse(
            atual["calibracoes_estado_notificado"]["gol_ft"]
        )

    def test_tendencia_curta_nao_projeta_armazenamento(self):
        estado = atualizar_tendencia_armazenamento(
            {
                "saudavel": True, "motivos": [], "total_mb": 100,
                "livre_mb": 2000, "limite_livre_mb": 512,
            },
            agora=datetime(2026, 7, 21, 12, 0),
        )
        self.assertFalse(estado["tendencia_avaliavel"])
        self.assertEqual(len(estado["historico"]), 1)

    def test_mudanca_da_metrica_descarta_historico_incompativel(self):
        estado = atualizar_tendencia_armazenamento(
            {
                "saudavel": True,
                "motivos": [],
                "total_mb": 19000,
                "livre_mb": 120000,
                "limite_livre_mb": 512,
                "metrica_versao": "armazenamento-com-backups-v2",
            },
            {
                "historico": [{
                    "em": "2026-07-21T00:00:00", "total_mb": 800,
                }]
            },
            agora=datetime(2026, 7, 21, 12, 0),
        )

        self.assertFalse(estado["tendencia_avaliavel"])
        self.assertEqual(len(estado["historico"]), 1)
        self.assertEqual(estado["historico"][0]["total_mb"], 19000.0)

    def test_crescimento_com_esgotamento_proximo_degrada(self):
        estado = atualizar_tendencia_armazenamento(
            {
                "saudavel": True, "motivos": [], "total_mb": 600,
                "livre_mb": 2000, "limite_livre_mb": 512,
            },
            {
                "historico": [{
                    "em": "2026-07-21T00:00:00", "total_mb": 100,
                }]
            },
            agora=datetime(2026, 7, 21, 12, 0),
        )
        self.assertTrue(estado["tendencia_avaliavel"])
        self.assertEqual(estado["crescimento_mb_dia"], 1000.0)
        self.assertEqual(estado["dias_ate_limite"], 1.5)
        self.assertFalse(estado["saudavel"])
        self.assertIn(
            "crescimento_armazenamento_critico", estado["motivos"]
        )

    def test_salto_unico_de_backup_nao_vira_crescimento_permanente(self):
        inicio = datetime(2026, 7, 21, 0, 0)
        historico = [
            {
                "em": (inicio + timedelta(hours=indice * 2)).isoformat(),
                "total_mb": 100 + indice * 4,
            }
            for indice in range(6)
        ]

        estado = atualizar_tendencia_armazenamento(
            {
                "saudavel": True,
                "motivos": [],
                "total_mb": 600,
                "livre_mb": 5000,
                "limite_livre_mb": 512,
            },
            {"historico": historico},
            agora=inicio + timedelta(hours=12),
        )

        self.assertTrue(estado["tendencia_avaliavel"])
        self.assertEqual(
            estado["metodo_tendencia"], "theil_sen_mediana_pares_v1"
        )
        self.assertEqual(estado["crescimento_mb_dia"], 48.0)
        self.assertEqual(estado["crescimento_endpoint_mb_dia"], 1000.0)
        self.assertTrue(estado["saudavel"])
        self.assertNotIn(
            "crescimento_armazenamento_critico", estado["motivos"]
        )

    def test_crescimento_sustentado_permanece_critico_com_estimador_robusto(
        self,
    ):
        inicio = datetime(2026, 7, 21, 0, 0)
        historico = [
            {
                "em": (inicio + timedelta(hours=indice * 2)).isoformat(),
                "total_mb": 100 + indice * 100,
            }
            for indice in range(3)
        ]

        estado = atualizar_tendencia_armazenamento(
            {
                "saudavel": True,
                "motivos": [],
                "total_mb": 700,
                "livre_mb": 2000,
                "limite_livre_mb": 512,
            },
            {"historico": historico},
            agora=inicio + timedelta(hours=12),
        )

        self.assertEqual(
            estado["metodo_tendencia"], "theil_sen_mediana_pares_v1"
        )
        self.assertEqual(estado["crescimento_mb_dia"], 1200.0)
        self.assertEqual(estado["crescimento_endpoint_mb_dia"], 1200.0)
        self.assertFalse(estado["saudavel"])
        self.assertIn(
            "crescimento_armazenamento_critico", estado["motivos"]
        )

    def test_banco_estavel_nao_gera_falso_alerta(self):
        estado = atualizar_tendencia_armazenamento(
            {
                "saudavel": True, "motivos": [], "total_mb": 90,
                "livre_mb": 2000, "limite_livre_mb": 512,
            },
            {
                "historico": [{
                    "em": "2026-07-21T00:00:00", "total_mb": 100,
                }]
            },
            agora=datetime(2026, 7, 21, 12, 0),
        )
        self.assertTrue(estado["saudavel"])
        self.assertEqual(estado["crescimento_mb_dia"], 0.0)
        self.assertIsNone(estado["dias_ate_limite"])

    def test_reducao_material_reinicia_tendencia_sem_apagar_auditoria(self):
        inicio = datetime(2026, 7, 21, 0, 0)
        estado = atualizar_tendencia_armazenamento(
            {
                "saudavel": True,
                "motivos": [],
                "total_mb": 21000,
                "livre_mb": 68000,
                "limite_livre_mb": 512,
            },
            {
                "historico": [
                    {
                        "em": inicio.isoformat(),
                        "total_mb": 22000,
                    },
                    {
                        "em": (inicio + timedelta(hours=12)).isoformat(),
                        "total_mb": 40000,
                    },
                ]
            },
            agora=inicio + timedelta(hours=13),
        )

        self.assertTrue(estado["saudavel"])
        self.assertFalse(estado["tendencia_avaliavel"])
        self.assertTrue(estado["rebase_tendencia"])
        self.assertEqual(
            "reducao_material_armazenamento",
            estado["motivo_rebase_tendencia"],
        )
        self.assertEqual(19000.0, estado["reducao_material_mb"])
        self.assertEqual(2, estado["historico_antes_rebase"]["amostras"])
        self.assertEqual(1, len(estado["historico"]))
        self.assertEqual(21000.0, estado["historico"][0]["total_mb"])

    def test_reinicia_quando_coleta_parou_e_pid_nao_existe(self):
        estado = tentar_reiniciar_processo(
            {"saudavel": False},
            {"status": "ativo", "pid": 99999999},
            {},
            datetime(2026, 7, 20, 20, 0),
            iniciar=lambda: 1234,
            verificar_instancia=lambda: False,
        )
        self.assertEqual(estado["novo_pid"], 1234)

    def test_reinicia_falha_imediatamente_mesmo_com_coleta_recente(self):
        estado = tentar_reiniciar_processo(
            {"saudavel": True},
            {
                "status": "falha",
                "pid": 123,
                "erro": "PermissionError",
                "mensagem": "Playwright negado token=segredo",
                "atualizado_em": "2026-07-20T19:59:30",
            },
            {},
            datetime(2026, 7, 20, 20, 0),
            iniciar=lambda: 456,
            verificar_instancia=lambda: False,
        )

        self.assertEqual(estado["novo_pid"], 456)
        self.assertEqual(estado["motivo_reinicio"], "processo_falhou")
        self.assertEqual(
            estado["causa_fatal"]["erro"], "PermissionError"
        )
        self.assertNotIn("segredo", estado["causa_fatal"]["mensagem"])
        mensagem = formatar_alerta_reinicio_monitor(estado)
        self.assertIn("Causa: PermissionError", mensagem)
        self.assertIn("Detalhe: Playwright negado", mensagem)
        self.assertNotIn("segredo", mensagem)

    def test_reinicia_runtime_atualizado_sem_esperar_cooldown(self):
        estado = tentar_reiniciar_processo(
            {"saudavel": True},
            {
                "status": "reinicio_pendente",
                "pid": 123,
                "motivo": "codigo_runtime_monitor_desatualizado",
            },
            {"ultimo_reinicio_em": "2026-07-20T19:59:50"},
            datetime(2026, 7, 20, 20, 0),
            iniciar=lambda: 789,
            verificar_instancia=lambda: False,
        )

        self.assertEqual(estado["novo_pid"], 789)
        self.assertEqual(
            estado["motivo_reinicio"], "codigo_runtime_atualizado"
        )

    def test_alerta_de_reinicio_sem_causa_mantem_texto_generico(self):
        mensagem = formatar_alerta_reinicio_monitor(
            {"novo_pid": 456, "motivo_reinicio": "instancia_ausente"}
        )

        self.assertIn("reiniciado automaticamente", mensagem)
        self.assertNotIn("Causa:", mensagem)

    def test_alerta_reinicio_falhado_fica_pendente_e_reutiliza_evento(self):
        reinicio = {
            "novo_pid": 456,
            "motivo_reinicio": "instancia_ausente",
            "ultimo_reinicio_em": "2026-08-10T22:10:00",
        }
        enviar = Mock(side_effect=[False, True])

        primeiro = atualizar_alerta_reinicio_monitor(
            {}, {}, reinicio=reinicio, enviar=enviar
        )
        segundo = atualizar_alerta_reinicio_monitor(
            {}, primeiro, enviar=enviar
        )

        self.assertEqual(enviar.call_count, 2)
        self.assertEqual(
            primeiro["alerta_reinicio_pendente"], reinicio
        )
        self.assertNotIn("alerta_reinicio_pendente", segundo)

    def test_alertas_de_reinicios_distintos_nao_se_sobrescrevem(self):
        antigo = {
            "novo_pid": 456,
            "motivo_reinicio": "instancia_ausente",
            "ultimo_reinicio_em": "2026-08-10T22:10:00",
        }
        novo = {
            "novo_pid": 789,
            "motivo_reinicio": "processo_falhou",
            "ultimo_reinicio_em": "2026-08-10T22:20:00",
        }
        anterior = {
            "alerta_reinicio_pendente": antigo,
            "alertas_reinicio_pendentes": [antigo],
        }

        pendentes = atualizar_alerta_reinicio_monitor(
            {}, anterior, reinicio=novo, enviar=lambda _texto: False
        )
        entregues = atualizar_alerta_reinicio_monitor(
            {}, pendentes, enviar=lambda _texto: True
        )

        self.assertEqual(
            pendentes["alertas_reinicio_pendentes"], [antigo, novo]
        )
        self.assertNotIn("alerta_reinicio_pendente", entregues)
        self.assertNotIn("alertas_reinicio_pendentes", entregues)

    def test_alerta_reinicio_padrao_usa_chave_estavel_ate_entregar(self):
        reinicio = {
            "novo_pid": 456,
            "motivo_reinicio": "instancia_ausente",
            "ultimo_reinicio_em": "2026-08-10T22:10:00",
        }
        with patch("watchdog.enviar_alerta", side_effect=[False, True]) as enviar:
            primeiro = atualizar_alerta_reinicio_monitor(
                {}, {}, reinicio=reinicio
            )
            atualizar_alerta_reinicio_monitor({}, primeiro)

        self.assertEqual(enviar.call_count, 2)
        self.assertEqual(
            enviar.call_args_list[0].kwargs["chave_evento"],
            enviar.call_args_list[1].kwargs["chave_evento"],
        )
        self.assertIsNone(
            enviar.call_args_list[1].kwargs["deduplicacao_minutos"]
        )

    def test_alerta_reinicio_critico_retorna_apos_tres_falhas_reais(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        reinicio = {
            "novo_pid": 456,
            "motivo_reinicio": "instancia_ausente",
            "ultimo_reinicio_em": "2026-08-10T22:10:00",
        }
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":404,"date":1784678400}}'
        )
        inicio = datetime(2026, 8, 10, 22, 10)
        ambiente = {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "admin",
            "TELEGRAM_CHAT_ID": "",
            "TELEGRAM_CHAT_ID_GOLS": "",
        }
        with patch.dict(os.environ, ambiente, clear=False), patch(
            "watchdog.urlopen",
            side_effect=[
                OSError("indisponivel-1"),
                OSError("indisponivel-2"),
                OSError("indisponivel-3"),
                resposta,
            ],
        ) as abrir:
            estado = atualizar_alerta_reinicio_monitor(
                {}, {}, reinicio=reinicio, agora=inicio,
                caminho_banco=self.caminho_banco,
            )
            estado = atualizar_alerta_reinicio_monitor(
                {}, estado, agora=inicio + timedelta(minutes=2),
                caminho_banco=self.caminho_banco,
            )
            estado = atualizar_alerta_reinicio_monitor(
                {}, estado, agora=inicio + timedelta(minutes=4),
                caminho_banco=self.caminho_banco,
            )
            estado_desatualizado = json.loads(json.dumps(estado))
            entregue = atualizar_alerta_reinicio_monitor(
                {}, estado, agora=inicio + timedelta(minutes=10),
                caminho_banco=self.caminho_banco,
            )
            repetido = atualizar_alerta_reinicio_monitor(
                {}, estado_desatualizado,
                agora=inicio + timedelta(minutes=11),
                caminho_banco=self.caminho_banco,
            )

        self.assertEqual(abrir.call_count, 4)
        self.assertNotIn("alerta_reinicio_pendente", entregue)
        self.assertNotIn("alerta_reinicio_pendente", repetido)

    def test_recuperacao_monitor_so_limpa_alerta_apos_entrega(self):
        enviar = Mock(side_effect=[False, True])
        anterior = {"alertado": True}

        falhou = atualizar_alerta_saude_monitor(
            {"saudavel": True}, anterior, enviar=enviar
        )
        recuperou = atualizar_alerta_saude_monitor(
            {"saudavel": True}, falhou, enviar=enviar
        )

        self.assertTrue(falhou["alertado"])
        self.assertFalse(recuperou["alertado"])
        self.assertEqual(enviar.call_count, 2)

    def test_recuperacao_monitor_retorna_apos_tres_falhas_sem_duplicar(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":405,"date":1784678400}}'
        )
        inicio = datetime(2026, 8, 10, 22, 10)
        ambiente = {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "admin",
            "TELEGRAM_CHAT_ID": "",
            "TELEGRAM_CHAT_ID_GOLS": "",
        }
        estado = {
            "alertado": True,
            "alerta_saude_incidente_id": "incidente-real",
        }
        with patch.dict(os.environ, ambiente, clear=False), patch(
            "watchdog.urlopen",
            side_effect=[
                OSError("indisponivel-1"),
                OSError("indisponivel-2"),
                OSError("indisponivel-3"),
                resposta,
            ],
        ) as abrir:
            for minutos in (0, 2, 4):
                estado = atualizar_alerta_saude_monitor(
                    {"saudavel": True},
                    estado,
                    agora=inicio + timedelta(minutes=minutos),
                    caminho_banco=self.caminho_banco,
                )
            estado_desatualizado = json.loads(json.dumps(estado))
            entregue = atualizar_alerta_saude_monitor(
                {"saudavel": True},
                estado,
                agora=inicio + timedelta(minutes=10),
                caminho_banco=self.caminho_banco,
            )
            repetido = atualizar_alerta_saude_monitor(
                {"saudavel": True},
                estado_desatualizado,
                agora=inicio + timedelta(minutes=11),
                caminho_banco=self.caminho_banco,
            )

        self.assertEqual(abrir.call_count, 4)
        self.assertFalse(entregue["alertado"])
        self.assertFalse(repetido["alertado"])
        self.assertNotIn("alerta_saude_incidente_id", entregue)

    def test_queda_nao_entregue_e_recuperada_nao_contamina_nova_queda(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        inicio = datetime(2026, 8, 10, 22, 10)
        ambiente = {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "admin",
            "TELEGRAM_CHAT_ID": "",
            "TELEGRAM_CHAT_ID_GOLS": "",
        }
        with patch.dict(os.environ, ambiente, clear=False), patch(
            "watchdog.urlopen",
            side_effect=[
                OSError("primeira queda nao entregue"),
                OSError("segunda queda nao entregue"),
            ],
        ) as abrir:
            primeira = atualizar_alerta_saude_monitor(
                {"saudavel": False, "motivo": "coleta_parada"},
                {},
                agora=inicio,
                caminho_banco=self.caminho_banco,
            )
            primeiro_id = primeira["alerta_saude_incidente_id"]
            recuperado_sem_aviso = atualizar_alerta_saude_monitor(
                {"saudavel": True},
                primeira,
                agora=inicio + timedelta(minutes=1),
                caminho_banco=self.caminho_banco,
            )
            segunda = atualizar_alerta_saude_monitor(
                {"saudavel": False, "motivo": "coleta_parada"},
                recuperado_sem_aviso,
                agora=inicio + timedelta(minutes=2),
                caminho_banco=self.caminho_banco,
            )

        self.assertFalse(recuperado_sem_aviso["alertado"])
        self.assertNotIn(
            "alerta_saude_incidente_id", recuperado_sem_aviso
        )
        self.assertNotEqual(
            segunda["alerta_saude_incidente_id"], primeiro_id
        )
        self.assertEqual(abrir.call_count, 2)
        conexao = sqlite3.connect(self.caminho_banco)
        try:
            chaves = conexao.execute(
                """
                SELECT DISTINCT chave FROM notificacoes_operacionais
                WHERE chave LIKE 'watchdog:saude:indisponivel:%'
                """
            ).fetchall()
        finally:
            conexao.close()
        self.assertEqual(len(chaves), 2)

    def test_reinicia_morte_abrupta_com_estado_ativo_e_trava_livre(self):
        estado = tentar_reiniciar_processo(
            {"saudavel": True},
            {"status": "ativo", "pid": 123},
            {},
            datetime(2026, 7, 20, 20, 0),
            iniciar=lambda: 456,
            verificar_instancia=lambda: False,
        )

        self.assertEqual(estado["novo_pid"], 456)
        self.assertEqual(estado["motivo_reinicio"], "instancia_ausente")

    def test_reinicia_estado_ausente_quando_coleta_parou(self):
        estado = tentar_reiniciar_processo(
            {"saudavel": False},
            {},
            {},
            datetime(2026, 7, 20, 20, 0),
            iniciar=lambda: 456,
            verificar_instancia=lambda: False,
        )

        self.assertEqual(estado["novo_pid"], 456)
        self.assertEqual(
            estado["motivo_reinicio"], "estado_processo_ausente"
        )

    def test_inicializacao_interrompida_respeita_tolerancia(self):
        agora = datetime(2026, 7, 20, 20, 0)
        recente = tentar_reiniciar_processo(
            {"saudavel": False},
            {
                "status": "iniciando",
                "atualizado_em": (agora - timedelta(seconds=30)).isoformat(),
            },
            {},
            agora,
            iniciar=lambda: self.fail("nao deveria reiniciar cedo"),
            verificar_instancia=lambda: False,
        )
        antigo = tentar_reiniciar_processo(
            {"saudavel": False},
            {
                "status": "iniciando",
                "atualizado_em": (agora - timedelta(seconds=90)).isoformat(),
            },
            {},
            agora,
            iniciar=lambda: 456,
            verificar_instancia=lambda: False,
        )

        self.assertIsNone(recente)
        self.assertEqual(antigo["novo_pid"], 456)
        self.assertEqual(
            antigo["motivo_reinicio"], "inicializacao_interrompida"
        )

    def test_pid_reutilizado_nao_impede_reinicio_sem_trava(self):
        with patch(
            "watchdog.pid_ativo",
            side_effect=AssertionError("PID não deve decidir o reinício"),
        ):
            estado = tentar_reiniciar_processo(
                {"saudavel": False},
                {"status": "ativo", "pid": 123},
                {},
                datetime(2026, 7, 20, 20, 0),
                iniciar=lambda: 456,
                verificar_instancia=lambda: False,
            )

        self.assertEqual(estado["novo_pid"], 456)

    def test_trava_ocupada_impede_monitor_duplicado(self):
        estado = tentar_reiniciar_processo(
            {"saudavel": False},
            {"status": "ativo", "pid": 99999999},
            {},
            datetime(2026, 7, 20, 20, 0),
            iniciar=lambda: self.fail("não deveria duplicar monitor"),
            verificar_instancia=lambda: True,
        )

        self.assertIsNone(estado)

    def test_concede_tolerancia_ao_monitor_que_acabou_de_iniciar(self):
        agora = datetime(2026, 7, 20, 20, 0)
        self.assertTrue(
            monitor_em_inicializacao(
                {"saudavel": False, "ultimo_sucesso_em": None},
                {
                    "status": "ativo",
                    "pid": 123,
                    "atualizado_em": (
                        agora - timedelta(seconds=30)
                    ).isoformat(),
                },
                agora,
                verificar_pid=lambda pid: pid == 123,
                verificar_instancia=lambda: True,
            )
        )

    def test_pid_reutilizado_sem_trava_nao_recebe_tolerancia(self):
        agora = datetime(2026, 7, 20, 20, 0)
        self.assertFalse(
            monitor_em_inicializacao(
                {"saudavel": False, "ultimo_sucesso_em": None},
                {
                    "status": "ativo",
                    "pid": 123,
                    "atualizado_em": agora.isoformat(),
                },
                agora,
                verificar_pid=lambda _pid: True,
                verificar_instancia=lambda: False,
            )
        )

    def test_trabalhador_odd_fresco_e_saudavel(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": (
                agora - timedelta(seconds=15)
            ).isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "intervalo_real_segundos": 15.008,
            "atraso_inicio_segundos": 0.008,
            "duracao_rodada_segundos": 0.2,
            "falhas_consecutivas": 0,
            "consultados": 1,
            "lote_maximo": 10,
            "fila_total": 12,
            "fila_tecnica_recente": 12,
            "fila_tecnica_dormente": 0,
            "fila_recente_nunca_consultada": 0,
            "fila_pendente_apos_lote": 2,
            "referencias_sombra_rapidas_tentadas": 1,
            "referencias_sombra_rapidas_reservadas": 1,
            "referencias_sombra_rapidas_consultadas": 1,
            "referencias_sombra_rapidas_linha_exata": 1,
            "referencias_sombra_rapidas_auditadas": 1,
            "referencias_sombra_rapidas_observadas": 1,
            "comparacoes_referencia_sombra_rapida": 2,
            "creditos_estimados_referencia_sombra_rapida": 1,
            "aplicacao_sinais_referencia_sombra": False,
            "referencias_sombra_rapidas_funil": {
                "versao": "funil-referencia-sombra-rapida-v1",
                "avaliadas": 1,
                "aprovadas": 1,
                "reprovadas": 0,
                "com_oferta": 1,
                "bloqueadas_custodia": 0,
                "bloqueadas_materializacao": 0,
                "alertas_enviados": 1,
                "fontes_executaveis_pos_envio": 1,
                "selecionadas_para_consulta": 1,
                "suprimidas_limite_rodada": 0,
                "exclusoes": {},
                "aplicacao_sinais": False,
                "telegram": False,
            },
            "referencia_sombra_rapida_acumulada": {
                "versao": (
                    "referencia-sincronizada-monitor-odd-rapido-"
                    "acumulada-v1"
                ),
                "integridade": True,
                "iniciado_em": "2026-09-01T16:00:00",
                "atualizado_em": "2026-09-01T16:29:45",
                "ultima_evidencia_em": "2026-09-01T16:29:45",
                "rodadas": 12,
                "tentadas": 4,
                "reservadas": 4,
                "consultadas": 3,
                "linha_exata": 2,
                "auditadas": 4,
                "observadas": 2,
                "comparacoes": 4,
                "creditos_estimados_reservados": 4,
                "motivos": {"observada": 2},
                "aplicacao_sinais": False,
                "telegram": False,
                "funil_selecao": {
                    "versao": (
                        "funil-referencia-sombra-rapida-acumulado-v1"
                    ),
                    "integridade": True,
                    "avaliadas": 6,
                    "aprovadas": 5,
                    "reprovadas": 1,
                    "com_oferta": 6,
                    "bloqueadas_custodia": 0,
                    "bloqueadas_materializacao": 1,
                    "alertas_enviados": 4,
                    "fontes_executaveis_pos_envio": 4,
                    "selecionadas_para_consulta": 4,
                    "suprimidas_limite_rodada": 0,
                    "exclusoes": {"decisao_reprovada:teste": 1},
                    "aplicacao_sinais": False,
                    "telegram": False,
                },
            },
            "sem_navegacao_packball": True,
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "ativo")
        self.assertEqual(resultado["intervalo_real_segundos"], 15.008)
        self.assertEqual(resultado["estado_fila"], "em_rodizio")
        self.assertEqual(
            resultado["espera_fila_estimada_segundos"], 15.0
        )
        self.assertTrue(
            resultado["referencia_sombra_rapida"]["integridade"]
        )
        self.assertEqual(
            2, resultado["referencia_sombra_rapida"]["comparacoes"]
        )
        self.assertFalse(
            resultado["referencia_sombra_rapida"]["aplicacao_sinais"]
        )
        acumulada = resultado["referencia_sombra_rapida"]["acumulada"]
        self.assertTrue(acumulada["presente"])
        self.assertTrue(acumulada["integridade"])
        self.assertEqual(acumulada["rodadas"], 12)
        self.assertEqual(acumulada["observadas"], 2)
        self.assertEqual(acumulada["comparacoes"], 4)
        self.assertFalse(acumulada["aplicacao_sinais"])
        funil = acumulada["funil_selecao"]
        self.assertTrue(funil["integridade"])
        self.assertEqual(funil["avaliadas"], 6)
        self.assertEqual(funil["selecionadas_para_consulta"], 4)

    def test_trabalhador_odd_recusa_referencia_sombra_que_afete_sinal(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "referencias_sombra_rapidas_tentadas": 1,
            "referencias_sombra_rapidas_reservadas": 1,
            "referencias_sombra_rapidas_consultadas": 1,
            "referencias_sombra_rapidas_linha_exata": 1,
            "referencias_sombra_rapidas_observadas": 1,
            "aplicacao_sinais_referencia_sombra": True,
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(
            "referencia_sombra_inconsistente", resultado["estado"]
        )
        self.assertEqual(
            "referencia_sombra_rapida_inconsistente", resultado["motivo"]
        )
        self.assertFalse(
            resultado["referencia_sombra_rapida"]["integridade"]
        )

    def test_trabalhador_odd_isola_falha_de_coleta_clv_dos_sinais(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "clv_pos_alerta_versao": (
                "coleta-clv-pos-alerta-api-rapida-v1"
            ),
            "clv_pos_alerta_estado": "falha_isolada",
            "clv_pos_alerta_candidatos": 0,
            "clv_pos_alerta_consultados": 0,
            "clv_pos_alerta_com_oferta_exata": 0,
            "clv_pos_alerta_sem_oferta_exata": 0,
            "clv_pos_alerta_estados_persistidos": 0,
            "clv_pos_alerta_falhas": 1,
            "clv_pos_alerta_falhas_consecutivas": 5,
            "clv_pos_alerta_aplicacao_sinais": False,
            "clv_pos_alerta_telegram": False,
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["clv_pos_alerta"]["integridade"])
        self.assertFalse(resultado["clv_pos_alerta"]["coleta_saudavel"])
        self.assertFalse(resultado["clv_pos_alerta"]["aplicacao_sinais"])

    def test_trabalhador_odd_recusa_clv_que_afete_sinal(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "clv_pos_alerta_versao": (
                "coleta-clv-pos-alerta-api-rapida-v1"
            ),
            "clv_pos_alerta_estado": "concluida",
            "clv_pos_alerta_candidatos": 1,
            "clv_pos_alerta_consultados": 1,
            "clv_pos_alerta_com_oferta_exata": 1,
            "clv_pos_alerta_sem_oferta_exata": 0,
            "clv_pos_alerta_estados_persistidos": 1,
            "clv_pos_alerta_falhas": 0,
            "clv_pos_alerta_falhas_consecutivas": 0,
            "clv_pos_alerta_aplicacao_sinais": True,
            "clv_pos_alerta_telegram": False,
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("clv_pos_alerta_inconsistente", resultado["estado"])
        self.assertEqual("clv_pos_alerta_inconsistente", resultado["motivo"])
        self.assertFalse(resultado["clv_pos_alerta"]["integridade"])

    def test_trabalhador_odd_v2_audita_cobertura_dos_mercados_clv(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        estado = {
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "clv_pos_alerta_versao": (
                "coleta-clv-pos-alerta-api-rapida-v2"
            ),
            "clv_pos_alerta_mercados_api_rapida": [
                "escanteios_ft_asiatico", "gol_ft", "gol_ht",
                "proximo_gol",
            ],
            "clv_pos_alerta_mercados_somente_snapshot": [
                "proximo_escanteio"
            ],
            "clv_pos_alerta_estado": "sem_candidatos_na_janela",
            "clv_pos_alerta_candidatos": 0,
            "clv_pos_alerta_consultados": 0,
            "clv_pos_alerta_com_oferta_exata": 0,
            "clv_pos_alerta_sem_oferta_exata": 0,
            "clv_pos_alerta_estados_persistidos": 0,
            "clv_pos_alerta_falhas": 0,
            "clv_pos_alerta_falhas_consecutivas": 0,
            "clv_pos_alerta_aplicacao_sinais": False,
            "clv_pos_alerta_telegram": False,
        }
        self.caminho_worker_odd.write_text(
            json.dumps(estado), encoding="utf-8"
        )

        integro = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )
        estado["clv_pos_alerta_mercados_api_rapida"].remove(
            "escanteios_ft_asiatico"
        )
        self.caminho_worker_odd.write_text(
            json.dumps(estado), encoding="utf-8"
        )
        incompleto = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertTrue(integro["saudavel"])
        self.assertTrue(
            integro["clv_pos_alerta"]["cobertura_mercados_integra"]
        )
        self.assertIn(
            "escanteios_ft_asiatico",
            integro["clv_pos_alerta"]["mercados_api_rapida"],
        )
        self.assertFalse(incompleto["saudavel"])
        self.assertEqual("clv_pos_alerta_inconsistente", incompleto["estado"])
        self.assertFalse(
            incompleto["clv_pos_alerta"]["cobertura_mercados_integra"]
        )

    def test_trabalhador_odd_v4_audita_subconjunto_somente_estado(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        estado = {
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "clv_pos_alerta_versao": (
                "coleta-clv-pos-alerta-api-rapida-v4"
            ),
            "clv_pos_alerta_mercados_api_rapida": [
                "escanteios_ft_asiatico", "gol_ft", "gol_ht",
                "proximo_gol",
            ],
            "clv_pos_alerta_mercados_somente_snapshot": [
                "proximo_escanteio"
            ],
            "clv_pos_alerta_estado": "concluida",
            "clv_pos_alerta_candidatos": 2,
            "clv_pos_alerta_consultados": 2,
            "clv_pos_alerta_com_oferta_exata": 1,
            "clv_pos_alerta_sem_oferta_exata": 1,
            "clv_pos_alerta_somente_estado": 1,
            "clv_pos_alerta_estados_persistidos": 2,
            "clv_pos_alerta_falhas": 0,
            "clv_pos_alerta_falhas_consecutivas": 0,
            "clv_pos_alerta_aplicacao_sinais": False,
            "clv_pos_alerta_telegram": False,
        }
        self.caminho_worker_odd.write_text(
            json.dumps(estado), encoding="utf-8"
        )
        integro = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )
        estado["clv_pos_alerta_somente_estado"] = 2
        self.caminho_worker_odd.write_text(
            json.dumps(estado), encoding="utf-8"
        )
        adulterado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertTrue(integro["saudavel"], integro)
        self.assertEqual(1, integro["clv_pos_alerta"]["somente_estado"])
        self.assertFalse(adulterado["saudavel"])
        self.assertEqual(
            "clv_pos_alerta_inconsistente", adulterado["estado"]
        )

    def test_trabalhador_odd_fila_dormente_nao_gera_alerta(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "lote_maximo": 10,
            "fila_total": 1,
            "fila_tecnica_recente": 0,
            "fila_tecnica_dormente": 1,
            "fila_pendente_apos_lote": 0,
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "ativo")
        self.assertEqual(resultado["estado_fila"], "dormente")
        self.assertIsNone(resultado["motivo"])

    def test_trabalhador_odd_recusa_acumulado_causalmente_invalido(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "referencias_sombra_rapidas_tentadas": 0,
            "referencias_sombra_rapidas_reservadas": 0,
            "referencias_sombra_rapidas_consultadas": 0,
            "referencias_sombra_rapidas_linha_exata": 0,
            "referencias_sombra_rapidas_auditadas": 0,
            "referencias_sombra_rapidas_observadas": 0,
            "comparacoes_referencia_sombra_rapida": 0,
            "aplicacao_sinais_referencia_sombra": False,
            "referencia_sombra_rapida_acumulada": {
                "versao": (
                    "referencia-sincronizada-monitor-odd-rapido-"
                    "acumulada-v1"
                ),
                "integridade": True,
                "iniciado_em": "2026-09-01T16:00:00",
                "atualizado_em": agora.isoformat(),
                "ultima_evidencia_em": agora.isoformat(),
                "rodadas": 2,
                "tentadas": 1,
                "reservadas": 1,
                "consultadas": 2,
                "linha_exata": 1,
                "auditadas": 1,
                "observadas": 1,
                "comparacoes": 2,
                "creditos_estimados_reservados": 1,
                "aplicacao_sinais": False,
                "telegram": False,
            },
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "referencia_sombra_inconsistente")
        self.assertFalse(
            resultado["referencia_sombra_rapida"]["acumulada"]["integridade"]
        )

    def test_trabalhador_odd_recusa_tentativa_fora_do_funil_pos_envio(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "referencias_sombra_rapidas_tentadas": 1,
            "referencias_sombra_rapidas_reservadas": 0,
            "referencias_sombra_rapidas_consultadas": 0,
            "referencias_sombra_rapidas_linha_exata": 0,
            "referencias_sombra_rapidas_auditadas": 0,
            "referencias_sombra_rapidas_observadas": 0,
            "comparacoes_referencia_sombra_rapida": 0,
            "aplicacao_sinais_referencia_sombra": False,
            "referencias_sombra_rapidas_funil": {
                "versao": "funil-referencia-sombra-rapida-v1",
                "avaliadas": 1,
                "aprovadas": 0,
                "reprovadas": 1,
                "com_oferta": 1,
                "bloqueadas_custodia": 0,
                "bloqueadas_materializacao": 0,
                "alertas_enviados": 0,
                "fontes_executaveis_pos_envio": 0,
                "selecionadas_para_consulta": 0,
                "suprimidas_limite_rodada": 0,
                "exclusoes": {"decisao_reprovada:teste": 1},
                "aplicacao_sinais": False,
                "telegram": False,
            },
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "referencia_sombra_inconsistente")
        self.assertFalse(
            resultado["referencia_sombra_rapida"]["integridade_rodada"]
        )

    def test_trabalhador_odd_recusa_acumulado_menor_que_rodada(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "referencias_sombra_rapidas_tentadas": 1,
            "referencias_sombra_rapidas_reservadas": 1,
            "referencias_sombra_rapidas_consultadas": 1,
            "referencias_sombra_rapidas_linha_exata": 1,
            "referencias_sombra_rapidas_auditadas": 1,
            "referencias_sombra_rapidas_observadas": 1,
            "comparacoes_referencia_sombra_rapida": 2,
            "aplicacao_sinais_referencia_sombra": False,
            "referencia_sombra_rapida_acumulada": {
                "versao": (
                    "referencia-sincronizada-monitor-odd-rapido-"
                    "acumulada-v1"
                ),
                "integridade": True,
                "iniciado_em": "2026-09-01T16:00:00",
                "atualizado_em": agora.isoformat(),
                "ultima_evidencia_em": None,
                "rodadas": 1,
                "tentadas": 0,
                "reservadas": 0,
                "consultadas": 0,
                "linha_exata": 0,
                "auditadas": 0,
                "observadas": 0,
                "comparacoes": 0,
                "creditos_estimados_reservados": 0,
                "aplicacao_sinais": False,
                "telegram": False,
            },
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "referencia_sombra_inconsistente")
        self.assertFalse(
            resultado["referencia_sombra_rapida"]["acumulada"]["integridade"]
        )

    def test_trabalhador_odd_fila_acima_sla_e_detectada(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": agora.isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
            "lote_maximo": 10,
            "fila_total": 60,
            "fila_tecnica_recente": 60,
            "fila_tecnica_dormente": 0,
            "fila_recente_nunca_consultada": 50,
            "fila_pendente_apos_lote": 50,
        }), encoding="utf-8")

        with patch.dict(os.environ, {
            "ACOMPANHAMENTO_ODD_API_FILA_SLA_SEGUNDOS": "60",
        }):
            resultado = verificar_trabalhador_acompanhamento_odd(
                self.caminho_worker_odd, agora=agora, ativo=True
            )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "fila_saturada")
        self.assertEqual(resultado["estado_fila"], "saturada")
        self.assertEqual(
            resultado["motivo"], "fila_acompanhamento_odd_saturada"
        )
        self.assertEqual(
            resultado["espera_fila_estimada_segundos"], 75.0
        )

    def test_trabalhador_odd_atrasado_e_detectado(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_worker_odd.write_text(json.dumps({
            "status": "ativo",
            "atualizado_em": (
                agora - timedelta(seconds=91)
            ).isoformat(),
            "intervalo_alvo_segundos": 15.0,
            "falhas_consecutivas": 0,
        }), encoding="utf-8")

        resultado = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd, agora=agora, ativo=True
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "atrasado")
        self.assertEqual(
            resultado["motivo"],
            "trabalhador_acompanhamento_odd_atrasado",
        )

    def test_worker_odd_sem_estado_e_tolerado_so_na_inicializacao(self):
        inicial = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd,
            ativo=True,
            monitor_inicializando=True,
        )
        operacional = verificar_trabalhador_acompanhamento_odd(
            self.caminho_worker_odd,
            ativo=True,
            monitor_inicializando=False,
        )

        self.assertTrue(inicial["saudavel"])
        self.assertEqual(inicial["estado"], "inicializando")
        self.assertFalse(operacional["saudavel"])

    def test_avaliacao_odd_prospectiva_fresca_e_observavel(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_odd.write_text(json.dumps({
            "versao": "avaliacao-aguardar-odd-prospectiva-v6",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "concluida",
            "atualizado_em": (
                agora - timedelta(minutes=10)
            ).isoformat(),
            "iniciado_em": (
                agora - timedelta(minutes=10, seconds=1)
            ).isoformat(),
            "finalizado_em": (
                agora - timedelta(minutes=10)
            ).isoformat(),
            "duracao_segundos": 1.0,
            "ancora_prospectiva_em": "2026-09-01T15:00:00",
            "estado": "coorte_prospectiva_em_formacao",
            "coorte_prospectiva_rapida": {
                "conclusivos": 4,
                "jogos_distintos": 3,
                "atingiram_faixa": 2,
                "entradas_oficiais_convertidas": 1,
                "delta_roi_espera_vs_entrada_imediata": 0.05,
                "ic95_bootstrap_delta_roi_estrategia": [-0.1, 0.2],
            },
            "vantagem_espera_comprovada": False,
            "desvantagem_espera_comprovada": False,
            "exposicao_coleta_prospectiva": {
                "estado": "exposicao_observada",
                "por_coorte": {
                    "principal": {"ciclos_concluidos": 2},
                },
            },
        }), encoding="utf-8")

        resultado = verificar_avaliacao_acompanhamento_odd(
            self.caminho_avaliacao_odd, agora=agora
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["conclusivos_prospectivos"], 4)
        self.assertEqual(resultado["atingiram_faixa"], 2)
        self.assertEqual(
            "exposicao_observada",
            resultado["exposicao_coleta_prospectiva"]["estado"],
        )
        self.assertFalse(resultado["promocao_automatica"])

    def test_avaliacao_odd_metodologia_antiga_falha_fechada(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_odd.write_text(json.dumps({
            "versao": "avaliacao-aguardar-odd-prospectiva-v3",
            "atualizado_em": agora.isoformat(),
            "coorte_prospectiva_rapida": {},
            "vantagem_espera_comprovada": True,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_acompanhamento_odd(
            self.caminho_avaliacao_odd, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("metodologia_desatualizada", resultado["estado"])
        self.assertFalse(resultado["versao_compativel"])
        self.assertFalse(resultado["vantagem_espera_comprovada"])
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_avaliacao_odd_desatualizada_e_detectada_sem_aplicar(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_odd.write_text(json.dumps({
            "versao": "avaliacao-aguardar-odd-prospectiva-v6",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "concluida",
            "atualizado_em": (
                agora - timedelta(seconds=3601)
            ).isoformat(),
            "iniciado_em": (
                agora - timedelta(seconds=3602)
            ).isoformat(),
            "finalizado_em": (
                agora - timedelta(seconds=3601)
            ).isoformat(),
            "duracao_segundos": 1.0,
            "coorte_prospectiva_rapida": {},
        }), encoding="utf-8")

        resultado = verificar_avaliacao_acompanhamento_odd(
            self.caminho_avaliacao_odd, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "desatualizada")
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_avaliacao_prioridade_ligas_e_observavel_sem_promover(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_ligas.write_text(json.dumps({
            "versao": "avaliacao-prioridade-ligas-gols-prospectiva-v3",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "concluida",
            "atualizado_em": agora.isoformat(),
            "iniciado_em": (
                agora - timedelta(seconds=1)
            ).isoformat(),
            "finalizado_em": agora.isoformat(),
            "duracao_segundos": 1.0,
            "ancora_prospectiva_em": "2026-09-01T16:00:00",
            "ancora_metodologia_v2_pre_registrada": True,
            "decisoes": 12,
            "decisoes_brutas": 80,
            "unidades_independentes": 12,
            "ciclos": 3,
            "por_grupo": {
                "prioridade_maxima": {"processadas": 3},
                "controle_pontuado": {"processadas": 4},
            },
            "delta_rendimento_oportunidade_por_detalhe": 0.12,
            "ic95_delta_rendimento_oportunidade": [-0.08, 0.32],
            "vantagem_captura_comprovada": False,
            "regressao_captura_comprovada": False,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_prioridade_ligas_gols(
            self.caminho_avaliacao_ligas, agora=agora
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(12, resultado["decisoes"])
        self.assertEqual(80, resultado["decisoes_brutas"])
        self.assertTrue(resultado["versao_compativel"])
        self.assertEqual(3, resultado["processadas_prioridade"])
        self.assertFalse(resultado["promocao_automatica"])
        self.assertFalse(resultado["altera_prioridade"])

    def test_avaliacao_prioridade_ligas_v1_falha_fechada(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_ligas.write_text(json.dumps({
            "versao": "avaliacao-prioridade-ligas-gols-prospectiva-v1",
            "atualizado_em": agora.isoformat(),
            "ancora_prospectiva_em": "2026-09-01T16:00:00",
            "vantagem_captura_comprovada": True,
            "regressao_captura_comprovada": True,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_prioridade_ligas_gols(
            self.caminho_avaliacao_ligas, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("metodologia_desatualizada", resultado["estado"])
        self.assertFalse(resultado["versao_compativel"])
        self.assertFalse(resultado["vantagem_captura_comprovada"])
        self.assertFalse(resultado["regressao_captura_comprovada"])

    def test_avaliadores_periodicos_sem_custodia_falham_fechados(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        casos = (
            (
                self.caminho_avaliacao_odd,
                verificar_avaliacao_acompanhamento_odd,
                "avaliacao-aguardar-odd-prospectiva-v6",
                "vantagem_espera_comprovada",
                "avaliacao_acompanhamento_odd_custodia_execucao_invalida",
            ),
            (
                self.caminho_avaliacao_ligas,
                verificar_avaliacao_prioridade_ligas_gols,
                "avaliacao-prioridade-ligas-gols-prospectiva-v3",
                "vantagem_captura_comprovada",
                "avaliacao_prioridade_ligas_gols_custodia_execucao_invalida",
            ),
            (
                self.caminho_avaliacao_quarentena_ht,
                verificar_avaliacao_quarentena_fallback_ht,
                VERSAO_AVALIACAO_QUARENTENA_FALLBACK_HT,
                "vantagem_linhas_altas_comprovada",
                "avaliacao_quarentena_fallback_ht_custodia_execucao_invalida",
            ),
        )
        for caminho, verificar, versao, chave_vantagem, motivo in casos:
            with self.subTest(versao=versao):
                caminho.write_text(json.dumps({
                    "versao": versao,
                    "estado_execucao": "concluida",
                    "atualizado_em": agora.isoformat(),
                    chave_vantagem: True,
                }), encoding="utf-8")

                resultado = verificar(caminho, agora=agora)

                self.assertFalse(resultado["saudavel"])
                self.assertEqual("estado_invalido", resultado["estado"])
                self.assertEqual(motivo, resultado["motivo"])
                self.assertFalse(resultado[chave_vantagem])
                self.assertFalse(resultado["aplicacao_sinais"])

    def _estado_avaliacao_probabilidade_individual(self, agora):
        coorte = {
            "candidatos": 0,
            "resultados": 0,
            "pendentes": 0,
            "faltam_candidatos": 60,
            "faltam_resultados": 50,
            "total": {
                "n": 0, "brier": None,
                "brier_mercado_sem_vig": None,
                "delta_brier_vs_mercado_sem_vig": None,
                "erro_calibracao": None,
            },
            "desenvolvimento": {"n": 0},
            "holdout": {"n": 0},
            "pronta_para_revisao": False,
            "vantagem_preditiva_prospectiva": False,
        }
        mercado = {
            "estado": "aguardando_modelo_retro_validado",
            "amostra_retro_bruta": 205,
            "amostra_retro": 205,
            "auditoria_referencia_sem_vig": {
                "total": 205,
                "com_referencia_sem_vig": 205,
                "sem_referencia_sem_vig": 0,
                "taxa_cobertura": 1.0,
                "cobertura_minima": 0.95,
                "cobertura_suficiente": True,
                "margem_bookmaker_media": 0.08,
                "exclusoes": {},
                "referencia": "over_under_mesmo_snapshot_sem_vig",
                "consulta_resultado": False,
                "aplicacao_sinais": False,
                "telegram": False,
            },
            "validacao_retro": {
                "versao": (
                    "individual-logistica-offset-mercado-sem-vig-"
                    "walkforward-v3"
                ),
                "estado": "validacao_reprovada",
                "aprovado_para_coorte_prospectiva": False,
            },
            "definicao_presente": False,
            "definicao_valida": False,
            "predicoes_invalidas": 0,
            "coorte_prospectiva": coorte,
        }
        return {
            "versao": (
                "avaliacao-probabilidade-individual-sem-vig-"
                "prospectiva-v2"
            ),
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "concluida",
            "atualizado_em": agora.isoformat(),
            "iniciado_em": (agora - timedelta(seconds=1)).isoformat(),
            "finalizado_em": agora.isoformat(),
            "duracao_segundos": 1.0,
            "integridade": True,
            "mercados": {
                "gol_ht": mercado,
                "gol_ft": json.loads(json.dumps(mercado)),
            },
        }

    def test_avaliacao_probabilidade_individual_saudavel_sem_promover(self):
        agora = datetime(2026, 9, 11, 12, 0, 0)
        self.caminho_avaliacao_probabilidade.write_text(
            json.dumps(self._estado_avaliacao_probabilidade_individual(agora)),
            encoding="utf-8",
        )
        resultado = verificar_avaliacao_probabilidade_individual(
            self.caminho_avaliacao_probabilidade, agora=agora
        )
        self.assertTrue(resultado["saudavel"])
        self.assertFalse(resultado["bloqueia_inferencia"])
        self.assertEqual(
            resultado["mercados"]["gol_ht"]["validacao_retro_estado"],
            "validacao_reprovada",
        )
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["altera_calibracao"])
        self.assertFalse(resultado["telegram"])
        self.assertEqual(
            1.0,
            resultado["mercados"]["gol_ht"]["referencia_sem_vig"][
                "taxa_cobertura"
            ],
        )

    def test_avaliacao_probabilidade_individual_rejeita_contagem_adulterada(self):
        agora = datetime(2026, 9, 11, 12, 0, 0)
        estado = self._estado_avaliacao_probabilidade_individual(agora)
        estado["mercados"]["gol_ft"]["coorte_prospectiva"].update({
            "candidatos": 2,
            "resultados": 1,
            "pendentes": 0,
            "faltam_candidatos": 58,
            "faltam_resultados": 49,
        })
        self.caminho_avaliacao_probabilidade.write_text(
            json.dumps(estado), encoding="utf-8"
        )
        resultado = verificar_avaliacao_probabilidade_individual(
            self.caminho_avaliacao_probabilidade, agora=agora
        )
        self.assertFalse(resultado["saudavel"])
        self.assertTrue(resultado["bloqueia_inferencia"])
        self.assertIn(
            "gol_ft_contagens_incoerentes", resultado["problemas"]
        )
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["telegram"])

    def test_avaliacao_probabilidade_individual_rejeita_cobertura_adulterada(self):
        agora = datetime(2026, 9, 11, 12, 0, 0)
        estado = self._estado_avaliacao_probabilidade_individual(agora)
        estado["mercados"]["gol_ht"][
            "auditoria_referencia_sem_vig"
        ]["com_referencia_sem_vig"] = 204
        self.caminho_avaliacao_probabilidade.write_text(
            json.dumps(estado), encoding="utf-8"
        )
        resultado = verificar_avaliacao_probabilidade_individual(
            self.caminho_avaliacao_probabilidade, agora=agora
        )
        self.assertFalse(resultado["saudavel"])
        self.assertIn(
            "gol_ht_referencia_sem_vig_incoerente",
            resultado["problemas"],
        )
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_avaliacao_desajuste_e_observavel_sem_liberar_sinal(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "concluida",
            "atualizado_em": agora.isoformat(),
            "iniciado_em": (
                agora - timedelta(seconds=1)
            ).isoformat(),
            "finalizado_em": agora.isoformat(),
            "duracao_segundos": 1.0,
            "ancora_prospectiva_em": "2026-09-01T16:00:00",
            "comparacoes": 40,
            "candidatos_independentes": 12,
            "jogos_distintos": 8,
            "com_seguimento_5m": 10,
            "persistentes_5m": 7,
            "taxa_persistencia_5m": 0.7,
            "ic95_persistencia_5m": [0.4, 0.89],
            "pronto_para_revisao": False,
            "persistencia_comprovada": False,
            "corroboracao_entrada_rapida": {
                "marcador": "corroboracao_odd_entrada_rapida",
                "comparacoes": 10,
                "fotografias_independentes": 5,
                "jogos_distintos": 4,
                "por_par_fontes": {
                    "api_football + betsapi": 10,
                },
                "por_estado": {"comparavel_sem_desajuste": 10},
                "por_selecao": {"over": 5, "under": 5},
                "amostra_minima_fotografias": 30,
                "jogos_minimos": 15,
                "faltam_fotografias": 25,
                "faltam_jogos": 11,
                "pronta_para_analise": False,
                "recomendacao": "continuar_coleta_prospectiva",
                "aplicacao_sinais": False,
                "promocao_automatica": False,
            },
            "integridade_comparacoes_odds": {
                "versao": "integridade-comparacoes-odds-multifonte-v1",
                "versao_comparacao": (
                    "comparacao-odds-multifonte-temporal-estado-minuto-v4"
                ),
                "comparacoes_persistidas": 40,
                "comparacoes_auditadas": 40,
                "comparacoes_validas": 40,
                "comparacoes_invalidas": 0,
                "auditoria_truncada": False,
                "limite_auditoria": 100000,
                "problemas": {},
                "invalidas_amostra": [],
                "fingerprint_evidencias": "c" * 64,
                "saudavel": True,
                "estado": "integra",
                "bloqueia_inferencia": False,
            },
            "recorte_executavel_prospectivo": {
                "bookmaker": "bet365",
                "ancora_pre_registrada_em": "2026-09-01T16:20:00",
                "candidatos_independentes": 4,
                "jogos_distintos": 3,
                "com_seguimento_mesma_bookmaker_5m": 3,
                "persistentes_mesma_bookmaker_5m": 2,
                "taxa_persistencia_mesma_bookmaker_5m": 0.6667,
                "ic95_persistencia_mesma_bookmaker_5m": [0.2, 0.94],
                "pronto_para_revisao": False,
                "persistencia_comprovada": False,
                "vantagem_executavel_comprovada": False,
                "resultados_gols_ft": {"resultados": 1},
                "cobertura_comparacao": {
                    "estado": "sem_desajuste_favoravel",
                    "observacoes_bookmaker": 8,
                    "comparacoes_com_bookmaker": 4,
                    "comparacoes_validas": 4,
                    "altera_sinal": False,
                },
            },
            "recorte_observacional_executavel": {
                "bookmaker": "bet365",
                "ancora_pre_registrada_em": "2026-09-01T16:20:00",
                "observacoes_validas": 9,
                "fontes_observadas": {
                    "betsapi": 5,
                    "api_football": 4,
                },
                "origens_observacoes": {
                    "observacoes_fontes_odds": 5,
                    "snapshots_odds": 4,
                },
                "fontes_observacionais_versao": (
                    "fontes-observacionais-monitor-mais-snapshots-v1"
                ),
                "contraparte_exige_fonte_independente": True,
                "pares_temporais": 5,
                "candidatos_independentes": 2,
                "jogos_distintos": 2,
                "com_seguimento_mesma_bookmaker_5m": 2,
                "persistentes_mesma_bookmaker_5m": 1,
                "taxa_persistencia_mesma_bookmaker_5m": 0.5,
                "ic95_persistencia_mesma_bookmaker_5m": [0.09, 0.91],
                "pronto_para_revisao": False,
                "persistencia_comprovada": False,
                "vantagem_executavel_comprovada": False,
                "resultados_gols_ft": {"resultados": 0},
                "exclusoes_pareamento": {
                    "intervalo_temporal_divergente": 1
                },
            },
            "recorte_convergencia_preco_prospectivo": {
                "versao": "convergencia-preco-bet365-prospectiva-v3",
                "definicao_sha256": "a" * 64,
                "ancora_pre_registrada_em": "2026-09-01T16:25:00",
                "bookmaker": "bet365",
                "estado": "coletando",
                "decisao": "aguardando_coorte_futura",
                "coorte_fechada": False,
                "evidencia_completa": False,
                "vantagem_executavel_comprovada": False,
                "tamanho_coorte": 60,
                "candidatos_independentes": 3,
                "observacoes_validas": 20,
                "fontes_observadas": {
                    "betsapi": 12,
                    "api_football": 8,
                },
                "origens_observacoes": {
                    "observacoes_fontes_odds": 12,
                    "snapshots_odds": 8,
                },
                "fontes_observacionais_versao": (
                    "fontes-observacionais-monitor-mais-snapshots-v1"
                ),
                "contraparte_exige_fonte_independente": True,
                "pares_temporais": 8,
                "total": {
                    "com_seguimento": 2,
                    "convergiram": 2,
                    "resultados_gols_ft": {"resultados": 1},
                },
                "desenvolvimento": {"candidatos": 3},
                "holdout": {"candidatos": 0},
                "criterios": {"delta_relativo_minimo": 0.02},
                "faltam_candidatos": 57,
                "faltam_seguimentos": 48,
                "faltam_resultados": 49,
            },
            "recorte_convergencia_escanteios_prospectivo": {
                "versao": "convergencia-preco-escanteios-bet365-prospectiva-v2",
                "definicao_sha256": "b" * 64,
                "ancora_pre_registrada_em": "2026-09-01T16:26:00",
                "bookmaker": "bet365",
                "mercado": "escanteios_ft_over_asiatico",
                "estado": "coletando",
                "decisao": "aguardando_coorte_futura",
                "coorte_fechada": False,
                "evidencia_completa": False,
                "vantagem_executavel_comprovada": False,
                "tamanho_coorte": 60,
                "registros_odds_temporais": 31,
                "observacoes_comparadas": 18,
                "observacoes_validas": 12,
                "pares_temporais": 5,
                "candidatos_independentes": 2,
                "total": {
                    "com_seguimento": 1,
                    "convergiram": 1,
                    "resultados_escanteios_ft": {"resultados": 1},
                },
                "desenvolvimento": {"candidatos": 2},
                "holdout": {"candidatos": 0},
                "criterios": {"delta_relativo_minimo": 0.02},
                "faltam_candidatos": 58,
                "faltam_seguimentos": 49,
                "faltam_resultados": 49,
            },
            "recorte_edge_sem_vig_multifonte": {
                "versao": "edge-sem-vig-multifonte-prospectiva-v1",
                "definicao_sha256": "d" * 64,
                "ancora_pre_registrada_em": "2026-09-01T16:27:00",
                "bookmaker_executavel": "bet365",
                "estado": "coletando",
                "decisao": "formando_coorte_prospectiva",
                "linhas_elegiveis": 18,
                "fotografias_completas": 8,
                "candidatos_brutos": 4,
                "candidatos_independentes": 3,
                "coorte": 3,
                "jogos": 3,
                "desenvolvimento": 3,
                "holdout": 0,
                "ev_medio_candidatos": 0.041,
                "ev_maximo_candidatos": 0.065,
                "por_categoria": {"gols": 3},
                "por_fonte_controle": {"the_odds_api": 3},
                "exclusoes": {"mercado_binario_incompleto": 2},
                "criterios": {
                    "mercado_binario_completo_nas_duas_fontes": True,
                    "selecao_antes_resultado": True,
                },
                "liquidacao_resultados": _liquidacao_edge_sem_vig_teste(3),
                "pronto_para_revisao_metodologica": False,
                "vantagem_executavel_comprovada": False,
                "faltam_coorte": 57,
                "faltam_revisao": 27,
                "faltam_jogos_revisao": 12,
                "selecao_antes_resultado": True,
                "aplicacao_sinais": False,
                "telegram": False,
                "promocao_automatica": False,
            },
            "recorte_referencia_pos_envio": (
                _recorte_referencia_pos_envio_teste()
            ),
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(12, resultado["candidatos_independentes"])
        self.assertEqual(7, resultado["persistentes_5m"])
        corroboracao = resultado["corroboracao_entrada_rapida"]
        self.assertEqual(5, corroboracao["fotografias_independentes"])
        self.assertEqual(4, corroboracao["jogos_distintos"])
        self.assertFalse(corroboracao["pronta_para_analise"])
        self.assertFalse(corroboracao["aplicacao_sinais"])
        integridade = resultado["integridade_comparacoes_odds"]
        self.assertTrue(integridade["saudavel"])
        self.assertEqual(40, integridade["comparacoes_auditadas"])
        self.assertFalse(integridade["bloqueia_inferencia"])
        executavel = resultado["recorte_executavel"]
        self.assertEqual("bet365", executavel["bookmaker"])
        self.assertEqual(4, executavel["candidatos_independentes"])
        self.assertEqual(
            2, executavel["persistentes_mesma_bookmaker_5m"]
        )
        self.assertFalse(executavel["vantagem_executavel_comprovada"])
        self.assertEqual(
            "sem_desajuste_favoravel",
            executavel["cobertura_comparacao"]["estado"],
        )
        self.assertFalse(executavel["aplicacao_sinais"])
        observacional = resultado["recorte_observacional_executavel"]
        self.assertEqual(9, observacional["observacoes_validas"])
        self.assertEqual(2, observacional["candidatos_independentes"])
        self.assertEqual(
            1, observacional["persistentes_mesma_bookmaker_5m"]
        )
        self.assertFalse(observacional["aplicacao_sinais"])
        contrato_fontes = resultado["contrato_fontes_observacionais"]
        self.assertTrue(contrato_fontes["saudavel"])
        self.assertFalse(contrato_fontes["bloqueia_inferencia"])
        convergencia = resultado[
            "recorte_convergencia_preco_prospectivo"
        ]
        self.assertEqual(3, convergencia["candidatos_independentes"])
        self.assertEqual(2, convergencia["total"]["convergiram"])
        self.assertEqual(57, convergencia["faltam_candidatos"])
        self.assertFalse(convergencia["vantagem_executavel_comprovada"])
        self.assertFalse(convergencia["aplicacao_sinais"])
        convergencia_escanteios = resultado[
            "recorte_convergencia_escanteios_prospectivo"
        ]
        self.assertEqual(
            "escanteios_ft_over_asiatico",
            convergencia_escanteios["mercado"],
        )
        self.assertEqual(2, convergencia_escanteios["candidatos_independentes"])
        self.assertEqual(31, convergencia_escanteios["registros_odds_temporais"])
        self.assertEqual(1, convergencia_escanteios["total"]["convergiram"])
        self.assertEqual(58, convergencia_escanteios["faltam_candidatos"])
        self.assertFalse(
            convergencia_escanteios["vantagem_executavel_comprovada"]
        )
        self.assertFalse(convergencia_escanteios["aplicacao_sinais"])
        edge_sem_vig = resultado["recorte_edge_sem_vig_multifonte"]
        self.assertTrue(edge_sem_vig["saudavel"])
        self.assertEqual(8, edge_sem_vig["fotografias_completas"])
        self.assertEqual(3, edge_sem_vig["coorte"])
        self.assertEqual(
            3, edge_sem_vig["por_fonte_controle"]["the_odds_api"]
        )
        self.assertFalse(edge_sem_vig["vantagem_executavel_comprovada"])
        self.assertFalse(edge_sem_vig["bloqueia_inferencia"])
        self.assertFalse(edge_sem_vig["aplicacao_sinais"])
        liquidacao = edge_sem_vig["liquidacao_resultados"]
        self.assertTrue(liquidacao["saudavel"])
        self.assertEqual(3, liquidacao["candidatos_liquidaveis"])
        self.assertEqual(
            3, liquidacao["por_mercado"]["gols:FT"]["coorte"]
        )
        self.assertFalse(liquidacao["vantagem_executavel_comprovada"])
        referencia_pos_envio = resultado["recorte_referencia_pos_envio"]
        self.assertTrue(referencia_pos_envio["saudavel"])
        self.assertEqual(0, referencia_pos_envio["auditorias_pos_envio"])
        self.assertFalse(
            referencia_pos_envio["vantagem_estatistica_para_revisao"]
        )
        self.assertFalse(referencia_pos_envio["aplicacao_sinais"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["promocao_automatica"])

        original = json.loads(
            self.caminho_avaliacao_desajuste.read_text(encoding="utf-8")
        )
        adulterado_referencia = json.loads(json.dumps(original))
        adulterado_referencia["recorte_referencia_pos_envio"][
            "por_mercado"
        ]["gol_ft"]["faltam_coorte_edge"] = 59
        self.caminho_avaliacao_desajuste.write_text(
            json.dumps(adulterado_referencia), encoding="utf-8"
        )
        referencia_bloqueada = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )
        self.assertFalse(referencia_bloqueada["saudavel"])
        self.assertEqual(
            "referencia_pos_envio_invalida",
            referencia_bloqueada["estado"],
        )
        self.assertIn(
            "gol_ft_faltam_coorte_divergente",
            referencia_bloqueada["recorte_referencia_pos_envio"][
                "problemas"
            ],
        )
        self.assertFalse(referencia_bloqueada["aplicacao_sinais"])
        self.caminho_avaliacao_desajuste.write_text(
            json.dumps(original), encoding="utf-8"
        )

        adulterado_liquidacao = json.loads(
            self.caminho_avaliacao_desajuste.read_text(encoding="utf-8")
        )
        adulterado_liquidacao["recorte_edge_sem_vig_multifonte"][
            "liquidacao_resultados"
        ]["aplicacao_sinais"] = True
        self.caminho_avaliacao_desajuste.write_text(
            json.dumps(adulterado_liquidacao), encoding="utf-8"
        )
        liquidacao_isolada = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )
        self.assertTrue(liquidacao_isolada["saudavel"])
        edge_com_liquidacao_invalida = liquidacao_isolada[
            "recorte_edge_sem_vig_multifonte"
        ]
        self.assertFalse(edge_com_liquidacao_invalida["saudavel"])
        self.assertTrue(edge_com_liquidacao_invalida["bloqueia_inferencia"])
        self.assertFalse(
            edge_com_liquidacao_invalida["liquidacao_resultados"][
                "aplicacao_sinais"
            ]
        )
        adulterado_liquidacao["recorte_edge_sem_vig_multifonte"][
            "liquidacao_resultados"
        ]["aplicacao_sinais"] = False
        self.caminho_avaliacao_desajuste.write_text(
            json.dumps(adulterado_liquidacao), encoding="utf-8"
        )

        adulterado = json.loads(
            self.caminho_avaliacao_desajuste.read_text(encoding="utf-8")
        )
        adulterado["recorte_edge_sem_vig_multifonte"][
            "vantagem_executavel_comprovada"
        ] = True
        adulterado["recorte_edge_sem_vig_multifonte"][
            "aplicacao_sinais"
        ] = True
        self.caminho_avaliacao_desajuste.write_text(
            json.dumps(adulterado), encoding="utf-8"
        )
        isolado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )
        self.assertTrue(isolado["saudavel"])
        edge_isolado = isolado["recorte_edge_sem_vig_multifonte"]
        self.assertFalse(edge_isolado["saudavel"])
        self.assertTrue(edge_isolado["bloqueia_inferencia"])
        self.assertFalse(edge_isolado["vantagem_executavel_comprovada"])
        self.assertFalse(edge_isolado["aplicacao_sinais"])

        adulterado["recorte_observacional_executavel"][
            "contraparte_exige_fonte_independente"
        ] = False
        self.caminho_avaliacao_desajuste.write_text(
            json.dumps(adulterado), encoding="utf-8"
        )
        bloqueado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )
        self.assertFalse(bloqueado["saudavel"])
        self.assertEqual("contrato_fontes_invalido", bloqueado["estado"])
        self.assertEqual(
            "contrato_fontes_observacionais_invalido",
            bloqueado["motivo"],
        )
        self.assertTrue(
            bloqueado["contrato_fontes_observacionais"][
                "bloqueia_inferencia"
            ]
        )

    def test_avaliacao_desajuste_falha_persistida_bloqueia_estado_antigo(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "falha",
            "atualizado_em": agora.isoformat(),
            "iniciado_em": "2026-09-01T16:29:58",
            "finalizado_em": agora.isoformat(),
            "duracao_segundos": 2.0,
            "tipo_erro": "RuntimeError",
            "erro": "falha controlada",
            "persistencia_comprovada": True,
            "recorte_observacional_executavel": {
                "vantagem_executavel_comprovada": True,
            },
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("falha_avaliacao", resultado["estado"])
        self.assertEqual(
            "avaliacao_desajuste_odds_falhou", resultado["motivo"]
        )
        self.assertFalse(resultado["persistencia_comprovada"])
        self.assertEqual({}, resultado["recorte_observacional_executavel"])
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_avaliacao_desajuste_execucao_abandonada_expira_fechada(self):
        agora = datetime(2026, 9, 1, 16, 30, 1)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "em_execucao",
            "atualizado_em": "2026-09-01T16:20:00",
            "iniciado_em": "2026-09-01T16:20:00",
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("execucao_interrompida", resultado["estado"])
        self.assertEqual(
            "avaliacao_desajuste_odds_execucao_expirada",
            resultado["motivo"],
        )
        self.assertTrue(
            resultado["integridade_comparacoes_odds"][
                "bloqueia_inferencia"
            ]
        )

    def test_avaliacao_desajuste_execucao_recente_nao_expoe_vantagem(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "em_execucao",
            "atualizado_em": "2026-09-01T16:29:55",
            "iniciado_em": "2026-09-01T16:29:55",
            "persistencia_comprovada": True,
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("avaliando", resultado["estado"])
        self.assertEqual("em_execucao", resultado["estado_execucao"])
        self.assertFalse(resultado["persistencia_comprovada"])
        self.assertFalse(resultado["pronto_para_revisao"])

    def test_avaliacao_desajuste_data_futura_falha_fechada(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "em_execucao",
            "atualizado_em": "2099-09-01T16:30:00",
            "iniciado_em": "2099-09-01T16:30:00",
            "persistencia_comprovada": True,
            "aplicacao_sinais": False,
            "promocao_automatica": False,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("estado_invalido", resultado["estado"])
        self.assertEqual(
            "avaliacao_desajuste_odds_cronologia_execucao_invalida",
            resultado["motivo"],
        )
        self.assertFalse(resultado["cronologia_execucao"]["valida"])
        self.assertIn(
            "atualizado_em_futuro",
            resultado["cronologia_execucao"]["problemas"],
        )
        self.assertFalse(resultado["persistencia_comprovada"])
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_avaliacao_desajuste_efeito_ativo_invalida_custodia(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "telegram": True,
            "estado_execucao": "concluida",
            "iniciado_em": "2026-09-01T16:29:59",
            "finalizado_em": agora.isoformat(),
            "atualizado_em": agora.isoformat(),
            "duracao_segundos": 1.0,
            "persistencia_comprovada": True,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("estado_invalido", resultado["estado"])
        self.assertEqual(
            "avaliacao_desajuste_odds_efeitos_operacionais_invalidos",
            resultado["motivo"],
        )
        self.assertEqual(
            ["telegram"],
            resultado["efeitos_operacionais"]["campos_invalidos"],
        )
        for chave in EFEITOS_DESATIVADOS:
            self.assertIs(resultado[chave], False)
        self.assertFalse(resultado["persistencia_comprovada"])

    def test_avaliacao_desajuste_metodologia_antiga_falha_fechada(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v7",
            "atualizado_em": agora.isoformat(),
            "persistencia_comprovada": True,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("metodologia_desatualizada", resultado["estado"])
        self.assertFalse(resultado["versao_compativel"])
        self.assertFalse(resultado["persistencia_comprovada"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["promocao_automatica"])

    def test_avaliacao_desajuste_v11_sem_corroboracao_falha_fechada(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "concluida",
            "atualizado_em": agora.isoformat(),
            "iniciado_em": (
                agora - timedelta(seconds=1)
            ).isoformat(),
            "finalizado_em": agora.isoformat(),
            "duracao_segundos": 1.0,
            "persistencia_comprovada": True,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("estado_invalido", resultado["estado"])
        self.assertEqual(
            "corroboracao_entrada_rapida_invalida",
            resultado["motivo"],
        )
        self.assertFalse(
            resultado["corroboracao_entrada_rapida"][
                "pronta_para_analise"
            ]
        )
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_avaliacao_desajuste_integridade_inconsistente_falha_fechada(self):
        agora = datetime(2026, 9, 1, 16, 30, 0)
        self.caminho_avaliacao_desajuste.write_text(json.dumps({
            "versao": "avaliacao-desajuste-odds-prospectiva-v16",
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "concluida",
            "atualizado_em": agora.isoformat(),
            "iniciado_em": (
                agora - timedelta(seconds=1)
            ).isoformat(),
            "finalizado_em": agora.isoformat(),
            "duracao_segundos": 1.0,
            "pronto_para_revisao": True,
            "persistencia_comprovada": True,
            "corroboracao_entrada_rapida": {
                "marcador": "corroboracao_odd_entrada_rapida",
                "comparacoes": 0,
                "fotografias_independentes": 0,
                "jogos_distintos": 0,
                "faltam_fotografias": 30,
                "faltam_jogos": 15,
                "pronta_para_analise": False,
                "aplicacao_sinais": False,
                "promocao_automatica": False,
            },
            "integridade_comparacoes_odds": {
                "versao": "integridade-comparacoes-odds-multifonte-v1",
                "versao_comparacao": (
                    "comparacao-odds-multifonte-temporal-estado-minuto-v4"
                ),
                "comparacoes_persistidas": 1,
                "comparacoes_auditadas": 1,
                "comparacoes_validas": 0,
                "comparacoes_invalidas": 1,
                "auditoria_truncada": False,
                "problemas": {"evidencia_sha256_divergente": 1},
                "invalidas_amostra": [{"id": 9}],
                "fingerprint_evidencias": "d" * 64,
                "saudavel": False,
                "estado": "inconsistente",
                "bloqueia_inferencia": True,
            },
        }), encoding="utf-8")

        resultado = verificar_avaliacao_desajuste_odds(
            self.caminho_avaliacao_desajuste, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("integridade_inconsistente", resultado["estado"])
        self.assertEqual(
            "integridade_comparacoes_odds_inconsistente",
            resultado["motivo"],
        )
        self.assertTrue(
            resultado["integridade_comparacoes_odds"][
                "bloqueia_inferencia"
            ]
        )
        self.assertFalse(resultado["pronto_para_revisao"])
        self.assertFalse(resultado["persistencia_comprovada"])
        self.assertFalse(resultado["aplicacao_sinais"])

    def test_quarentena_ht_e_observavel_sem_reativacao(self):
        agora = datetime(2026, 9, 1, 20, 30, 0)
        self.caminho_avaliacao_quarentena_ht.write_text(json.dumps({
            "versao": VERSAO_AVALIACAO_QUARENTENA_FALLBACK_HT,
            "custodia_execucao_versao": "custodia-execucao-avaliacao-v3",
            **EFEITOS_DESATIVADOS,
            "estado_execucao": "concluida",
            "regra_versao_alvo": REGRA_VERSAO_QUARENTENA_FALLBACK_HT,
            "status_coorte": STATUS_COORTE_QUARENTENA_FALLBACK_HT,
            "politica_versao": (
                "fallback-api-ht-linhas-altas-quarentena-v1"
            ),
            "atualizado_em": agora.isoformat(),
            "iniciado_em": (
                agora - timedelta(seconds=1)
            ).isoformat(),
            "finalizado_em": agora.isoformat(),
            "duracao_segundos": 1.0,
            "ancora_prospectiva_em": "2026-09-01T20:00:00",
            "ancora_metodologia_v2_pre_registrada": True,
            "politica_operacional_ativa": True,
            "auditoria_independencia": {
                "unidades_independentes": 18,
                "candidatos_elegiveis": 30,
            },
            "por_grupo": {
                "quarentena_linhas_altas": {
                    "resultados": 8, "roi": -0.4,
                },
                "controle_ht_0_5": {"resultados": 10, "roi": 0.08},
            },
            "pronto_para_revisao": False,
            "vantagem_linhas_altas_comprovada": False,
            "prejuizo_linhas_altas_comprovado": False,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_quarentena_fallback_ht(
            self.caminho_avaliacao_quarentena_ht, agora=agora
        )

        self.assertTrue(resultado["saudavel"])
        self.assertTrue(resultado["versao_compativel"])
        self.assertTrue(resultado["metodologia_compativel"])
        self.assertTrue(resultado["ancora_metodologia_v2_pre_registrada"])
        self.assertTrue(resultado["politica_operacional_ativa"])
        self.assertEqual(18, resultado["unidades_independentes"])
        self.assertEqual(30, resultado["decisoes_brutas_elegiveis"])
        self.assertEqual(8, resultado["resultados_quarentena"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["reativacao_automatica"])

    def test_quarentena_ht_metodologia_v1_falha_fechada(self):
        agora = datetime(2026, 9, 1, 20, 30, 0)
        self.caminho_avaliacao_quarentena_ht.write_text(json.dumps({
            "versao": "avaliacao-quarentena-fallback-ht-prospectiva-v1",
            "atualizado_em": agora.isoformat(),
            "iniciado_em": (
                agora - timedelta(seconds=1)
            ).isoformat(),
            "finalizado_em": agora.isoformat(),
            "duracao_segundos": 1.0,
            "ancora_prospectiva_em": "2026-09-01T20:00:00",
            "ancora_metodologia_v2_pre_registrada": True,
            "politica_operacional_ativa": True,
            "pronto_para_revisao": True,
            "vantagem_linhas_altas_comprovada": True,
            "prejuizo_linhas_altas_comprovado": True,
        }), encoding="utf-8")

        resultado = verificar_avaliacao_quarentena_fallback_ht(
            self.caminho_avaliacao_quarentena_ht, agora=agora
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual("metodologia_desatualizada", resultado["estado"])
        self.assertFalse(resultado["versao_compativel"])
        self.assertFalse(resultado["metodologia_compativel"])
        self.assertFalse(resultado["pronto_para_revisao"])
        self.assertFalse(resultado["vantagem_linhas_altas_comprovada"])
        self.assertFalse(resultado["prejuizo_linhas_altas_comprovado"])
        self.assertFalse(resultado["aplicacao_sinais"])
        self.assertFalse(resultado["reativacao_automatica"])

    def test_estado_watchdog_persiste_e_recarrega_do_sqlite(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        agora = datetime(2026, 7, 25, 21, 30)
        original = {
            "alertado": True,
            "validacao": {
                "marcos_notificados": {
                    "sinais-v4:gol_ft": [30, 100],
                },
                "resumo_diario_enviado_em": "2026-07-25",
                "drift_simulacoes": {
                    "gol_ft": {"estado_notificado": "degradado"},
                },
            },
        }

        persistencia = persistir_estado_watchdog_sqlite(
            self.caminho_banco, original, agora
        )
        carregado = carregar_estado_watchdog_sqlite(self.caminho_banco)

        self.assertTrue(persistencia["saudavel"])
        self.assertEqual(persistencia["estado"], "persistido")
        self.assertTrue(carregado["saudavel"])
        self.assertEqual(carregado["estado"]["alertado"], True)
        self.assertEqual(
            carregado["estado"]["validacao"]["marcos_notificados"],
            original["validacao"]["marcos_notificados"],
        )
        self.assertEqual(
            carregado["estado"]["validacao"]["resumo_diario_enviado_em"],
            "2026-07-25",
        )
        self.assertEqual(
            carregado["estado"]["persistencia_estado_watchdog"]["estado"],
            "persistido",
        )

    def test_json_corrompido_recupera_estado_do_sqlite(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        caminho_json = Path.cwd() / ".teste_watchdog_estado_corrompido.json"
        caminho_json.write_text("{invalido", encoding="utf-8")
        try:
            persistir_estado_watchdog_sqlite(
                self.caminho_banco,
                {
                    "validacao": {
                        "marcos_notificados": {
                            "sinais-v4:gol_ft": [30],
                        }
                    }
                },
                datetime(2026, 7, 25, 21, 31),
            )

            estado, diagnostico = carregar_estado_anterior_watchdog(
                caminho_json, self.caminho_banco
            )

            self.assertEqual(diagnostico["origem"], "sqlite")
            self.assertTrue(diagnostico["recuperado"])
            self.assertEqual(
                estado["validacao"]["marcos_notificados"][
                    "sinais-v4:gol_ft"
                ],
                [30],
            )
        finally:
            caminho_json.unlink(missing_ok=True)

    def test_json_valido_tem_preferencia_sobre_sqlite(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        caminho_json = Path.cwd() / ".teste_watchdog_estado_valido.json"
        caminho_json.write_text(
            json.dumps({"origem_teste": "json"}), encoding="utf-8"
        )
        try:
            persistir_estado_watchdog_sqlite(
                self.caminho_banco, {"origem_teste": "sqlite"}
            )

            estado, diagnostico = carregar_estado_anterior_watchdog(
                caminho_json, self.caminho_banco
            )

            self.assertEqual(estado["origem_teste"], "json")
            self.assertEqual(diagnostico["origem"], "json")
            self.assertFalse(diagnostico["recuperado"])
        finally:
            caminho_json.unlink(missing_ok=True)

    def test_estado_ausente_em_ambas_fontes_inicia_vazio(self):
        caminho_json = Path.cwd() / ".teste_watchdog_estado_ausente.json"
        caminho_json.unlink(missing_ok=True)

        estado, diagnostico = carregar_estado_anterior_watchdog(
            caminho_json, self.caminho_banco
        )

        self.assertEqual(estado, {})
        self.assertEqual(diagnostico["origem"], "vazio")
        self.assertFalse(diagnostico["recuperado"])

    def test_falha_ao_persistir_estado_e_exposta_sem_excecao(self):
        resultado = persistir_estado_watchdog_sqlite(
            Path.cwd() / ".pasta_inexistente" / "watchdog.db",
            {"alertado": True},
        )

        self.assertFalse(resultado["saudavel"])
        self.assertEqual(resultado["estado"], "indisponivel")
        self.assertEqual(
            resultado["motivo"], "persistencia_estado_watchdog_falhou"
        )

    def test_partida_a_frio_nao_envia_alerta_antes_do_primeiro_ciclo(self):
        # Sem coorte pre-live, o breaker dispara o proprio alerta de
        # suspensao e poluiria a asercao. O assunto deste teste e o alerta
        # de partida a frio. Fica fora do "with" abaixo porque a cadeia ja
        # esta no limite de blocos aninhados do Python.
        breaker_pre_live = patch(
            "watchdog.atualizar_alerta_circuit_breaker_pre_live_preciso",
            side_effect=lambda estado, anterior=None, enviar=None: estado,
        )
        breaker_pre_live.start()
        self.addCleanup(breaker_pre_live.stop)
        estado_temporario = Path.cwd() / ".teste_watchdog_estado.json"
        estado_temporario.unlink(missing_ok=True)
        recuperacao_temporaria = (
            Path.cwd() / ".teste_recuperacao_banco_ausente.json"
        )
        recuperacao_temporaria.unlink(missing_ok=True)
        processo = {
            "status": "ativo",
            "pid": 123,
            "atualizado_em": (
                datetime.now() - timedelta(seconds=30)
            ).replace(microsecond=0).isoformat(),
        }
        validacao = {
            "saudavel": True,
            "requer_atencao": False,
            "motivos": [],
            "avisos": [],
        }
        enviar = Mock()
        try:
            with patch.multiple(
                "watchdog",
                ARQUIVO_ESTADO=estado_temporario,
                ARQUIVO_RECUPERACAO_BANCO=recuperacao_temporaria,
                acionar_recuperacao_banco_ativo=Mock(return_value={
                    "saudavel": True,
                    "estado": "integro",
                    "recuperacao_necessaria": False,
                }),
            ), patch(
                "watchdog.verificar_coleta",
                return_value={
                    "saudavel": False,
                    "motivo": "coleta_parada",
                    "ultimo_sucesso_em": None,
                },
            ), patch(
                "watchdog.ler_estado", return_value=processo
            ), patch(
                "watchdog.pid_ativo", return_value=True
            ), patch(
                "watchdog.trava_em_uso", return_value=True
            ), patch(
                "watchdog.verificar_validacao", return_value=validacao
            ), patch(
                "watchdog.verificar_backup_diario",
                return_value={"saudavel": True, "motivo": None},
            ), patch(
                "watchdog.verificar_ponto_recuperacao",
                return_value={"saudavel": True, "motivo": None},
            ), patch(
                "watchdog.verificar_capacidade_coleta",
                return_value={"saudavel": True, "motivo": None},
            ), patch(
                "watchdog.avaliar_experimento_ritmo_packball",
                return_value={
                    "saudavel": True,
                    "avaliavel": True,
                    "estado": "em_observacao",
                    "motivos": [],
                    "regime_atual": "distribuido:21.929:28:600",
                    "iniciado_em": "2026-07-25T20:04:13",
                    "experimento": {"ciclos": 1},
                },
            ), patch(
                "watchdog.persistir_historico_drift_simulacoes",
                return_value={
                    "saudavel": True,
                    "estado": "ativo",
                    "motivo": None,
                    "inseridos": 0,
                    "total": 0,
                    "mercados": 0,
                },
            ), patch(
                "watchdog.persistir_historico_avaliacao_contexto",
                return_value={
                    "saudavel": True,
                    "estado": "ativo",
                    "motivo": None,
                    "inseridos": 0,
                    "total": 0,
                    "mercados": 0,
                },
            ), patch(
                "watchdog.persistir_modelos_pontuacao_sombra",
                return_value={
                    "saudavel": True,
                    "estado": "ativo",
                    "motivo": None,
                    "criados": 0,
                    "avaliacao": {
                        "integro": True,
                        "modo": "sombra",
                        "por_mercado": {},
                    },
                },
            ), patch(
                "watchdog.persistir_modelos_pontuacao_contexto_sombra",
                return_value={
                    "saudavel": True,
                    "estado": "ativo",
                    "motivo": None,
                    "criados": 0,
                    "avaliacao": {
                        "integro": True,
                        "modo": "sombra",
                        "por_mercado": {},
                    },
                },
            ), patch(
                "watchdog.carregar_estado_anterior_watchdog",
                return_value=(
                    {},
                    {
                        "origem": "vazio",
                        "recuperado": False,
                        "motivo": "estado_persistente_ausente",
                    },
                ),
            ), patch(
                "watchdog.persistir_estado_watchdog_sqlite",
                return_value={
                    "saudavel": True,
                    "estado": "persistido",
                    "motivo": None,
                    "persistido_em": "2026-07-25T21:30:00",
                },
            ), patch(
                "watchdog.verificar_armazenamento",
                return_value={"saudavel": True, "motivos": []},
            ), patch(
                "watchdog.enviar_alerta", enviar
            ), patch(
                "watchdog.ARQUIVO_ESTADO_PRE_LIVE_PRECISO",
                self._caminho_pre_live_preciso_isolado(),
            ), patch.dict(
                "os.environ", {"WATCHDOG_REINICIO_AUTOMATICO": "0"}
            ):
                from watchdog import executar_verificacao

                estado = executar_verificacao()
            self.assertTrue(estado["monitor_inicializando"])
            enviar.assert_not_called()
        finally:
            estado_temporario.unlink(missing_ok=True)
            recuperacao_temporaria.unlink(missing_ok=True)

    def test_inicio_do_processo_nao_gera_falso_alerta_antes_da_trava(self):
        agora = datetime(2026, 7, 20, 20, 0)

        self.assertTrue(
            monitor_em_inicializacao(
                {
                    "saudavel": False,
                    "motivo": "coleta_parada",
                    "ultimo_sucesso_em": (
                        agora - timedelta(minutes=10)
                    ).isoformat(),
                },
                {
                    "status": "iniciando",
                    "atualizado_em": (
                        agora - timedelta(seconds=10)
                    ).isoformat(),
                },
                agora,
                verificar_pid=lambda pid: self.fail(
                    "PID ainda nao e confiavel durante o Popen"
                ),
                verificar_instancia=lambda: self.fail(
                    "trava ainda pode nao ter sido adquirida"
                ),
            )
        )

        self.assertFalse(
            monitor_em_inicializacao(
                {"saudavel": False},
                {
                    "status": "iniciando",
                    "atualizado_em": (
                        agora - timedelta(seconds=60)
                    ).isoformat(),
                },
                agora,
            )
        )

    def test_nao_mascara_monitor_sem_ciclo_apos_tolerancia(self):
        agora = datetime(2026, 7, 20, 20, 10)
        self.assertFalse(
            monitor_em_inicializacao(
                {"saudavel": False, "ultimo_sucesso_em": None},
                {
                    "status": "ativo",
                    "pid": 123,
                    "atualizado_em": (
                        agora - timedelta(minutes=6)
                    ).isoformat(),
                },
                agora,
                verificar_pid=lambda pid: True,
                verificar_instancia=lambda: True,
            )
        )

    def test_nao_aplica_tolerancia_depois_do_primeiro_ciclo(self):
        agora = datetime(2026, 7, 20, 20, 2)
        inicio = agora - timedelta(minutes=2)
        self.assertFalse(
            monitor_em_inicializacao(
                {
                    "saudavel": False,
                    "ultimo_sucesso_em": (
                        inicio + timedelta(seconds=30)
                    ).isoformat(),
                },
                {
                    "status": "ativo",
                    "pid": 123,
                    "atualizado_em": inicio.isoformat(),
                },
                agora,
                verificar_pid=lambda pid: True,
                verificar_instancia=lambda: True,
            )
        )

    def test_nao_reinicia_apos_encerramento_manual(self):
        estado = tentar_reiniciar_processo(
            {"saudavel": False},
            {"status": "encerrado", "pid": 99999999},
            {},
            datetime(2026, 7, 20, 20, 0),
            iniciar=lambda: self.fail("não deveria iniciar"),
        )
        self.assertIsNone(estado)

    def test_supervisao_detecta_pendencia_estatistica_vencida(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
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
            banco.salvar_candidatos(
                snapshot,
                [{
                    "mercado": "gol_ft",
                    "odd": 1.8,
                    "regra_versao": "sinais-v1",
                    "status": "aprovado",
                }],
                datetime(2026, 7, 20, 12, 0),
            )
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 16, 0)
            )
            self.assertFalse(estado["saudavel"])
            self.assertEqual(estado["pendencias_vencidas"], 1)
            self.assertIn("pendencias_acima_180_minutos", estado["motivos"])
            self.assertEqual(
                estado["detalhes_pendencias_vencidas"],
                [{
                    "sinal_id": 1,
                    "partida": "A x B",
                    "mercado": "gol_ft",
                    "idade_minutos": 240.0,
                }],
            )
        finally:
            banco.fechar()

    def test_final_incompleto_aguarda_24h_sem_alerta_e_depois_vence(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/1/live",
                "mandante": "A",
                "visitante": "B",
                "placar": "0-1",
                "status": "60 '",
            })
            banco.salvar_candidatos(snapshot, [{
                "mercado": "proximo_gol",
                "linha": "casa",
                "odd": 2.0,
                "regra_versao": "sinais-v1",
                "status": "aprovado",
            }], datetime(2026, 7, 20, 12, 0))
            partida_id = banco.conexao.execute(
                "SELECT id FROM partidas LIMIT 1"
            ).fetchone()[0]
            for minuto in (0, 10, 20):
                banco.registrar_consulta_finalizacao(
                    partida_id,
                    "packball",
                    "finalizado_dados_incompletos",
                    instante=datetime(2026, 7, 20, 13, minuto),
                )

            aguardando = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 16, 0)
            )
            vencida = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 21, 14, 0)
            )

            self.assertEqual(aguardando["pendencias_vencidas"], 0)
            self.assertEqual(
                aguardando["pendencias_finais_incompletas_aguardando"], 1
            )
            self.assertNotIn(
                "pendencias_acima_180_minutos", aguardando["motivos"]
            )
            self.assertEqual(vencida["pendencias_vencidas"], 1)
            self.assertIn(
                "pendencias_acima_180_minutos", vencida["motivos"]
            )
        finally:
            banco.fechar()

    def test_cache_nao_usa_relogio_antigo_do_inicio_da_supervisao(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            armazenado_em = datetime.now().timestamp()
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO cache_api_football (
                        chave, categoria, armazenado_em, dados_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    ("cache-concorrente", "geral", armazenado_em, "[]"),
                )

            estado = verificar_validacao(
                self.caminho_banco,
                datetime.now() - timedelta(minutes=2),
            )

            self.assertTrue(estado["cache_api_football"]["saudavel"])
            self.assertEqual(
                estado["cache_api_football"]["relogios_futuros"], 0
            )
        finally:
            banco.fechar()

    def test_partida_longa_com_snapshot_recente_nao_e_pendencia_vencida(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            inicial = banco.salvar_registro(
                {
                    "coletado_em": "2026-07-20T12:00:00",
                    "url": "https://packball.com/match/1/live",
                    "mandante": "A",
                    "visitante": "B",
                    "placar": "0-0",
                    "status": "20 '",
                }
            )
            banco.salvar_candidatos(
                inicial,
                [{
                    "mercado": "gol_ft",
                    "odd": 1.8,
                    "regra_versao": "sinais-v1",
                    "status": "aprovado",
                }],
                datetime(2026, 7, 20, 12, 0),
            )
            banco.salvar_registro(
                {
                    "coletado_em": "2026-07-20T15:55:00",
                    "url": "https://packball.com/match/1/live",
                    "mandante": "A",
                    "visitante": "B",
                    "placar": "1-1",
                    "status": "PEN",
                }
            )

            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 16, 0)
            )

            self.assertTrue(estado["saudavel"])
            self.assertEqual(estado["pendencias_vencidas"], 0)
            self.assertEqual(estado["pendencias_longas_ativas"], 1)
        finally:
            banco.fechar()

    def test_funil_sem_jogos_recentes_nao_gera_alerta(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 12, 30)
            )
            self.assertTrue(estado["saudavel"])
            self.assertFalse(estado["requer_atencao"])
            self.assertEqual(
                estado["funil_recente"]["estado"], "sem_jogos_recentes"
            )
            self.assertEqual(
                estado["amostra_por_mercado"],
                {
                    "gol_ft": 0,
                    "gol_ht": 0,
            "proximo_gol": 0,
            "proximo_escanteio": 0,
            "escanteios_ft_asiatico": 0,
            "escanteios_1t": 0,
                    "escanteios_2t": 0,
                },
            )
        finally:
            banco.fechar()

    def test_catalogo_odds_live_desatualizado_gera_aviso(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            with patch(
                "watchdog.verificar_catalogo_odds_live",
                return_value={
                    "saudavel": False,
                    "estado": "desatualizado",
                    "motivo": "catalogo_odds_live_desatualizado",
                    "divergencias": [],
                },
            ):
                estado = verificar_validacao(
                    self.caminho_banco, datetime(2026, 7, 20, 12, 30)
                )

            self.assertIn(
                "catalogo_odds_live_desatualizado", estado["avisos"]
            )
            self.assertTrue(estado["requer_atencao"])
            self.assertTrue(estado["saudavel"])
        finally:
            banco.fechar()

    @patch.dict(
        "os.environ",
        {
            "SINAIS_TESTE_ATIVO": "1",
            "PONTUACAO_MINIMA_SINAL_TESTE": "80",
            "QUALIDADE_MINIMA_SINAL_TESTE": "80",
        },
        clear=False,
    )
    def test_watchdog_exige_experimento_do_filtro_ativo(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            ausente = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 22, 18, 10)
            )
            self.assertIn(
                "experimento_filtro_inconsistente", ausente["motivos"]
            )
            self.assertEqual(
                ausente["experimento_filtro"]["estado"], "ausente"
            )

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
            valido = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 22, 18, 11)
            )
            self.assertNotIn(
                "experimento_filtro_inconsistente", valido["motivos"]
            )
            self.assertTrue(valido["experimento_filtro"]["saudavel"])
            self.assertTrue(valido["experimento_filtro"]["protegido"])
        finally:
            banco.fechar()

    def test_watchdog_registra_ancora_longa_sem_ativar_modelo(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
        finally:
            banco.fechar()

        resultado = persistir_estudos_pontuacao_longa_sombra(
            {
                "regra_versoes_por_mercado": {
                    "gol_ft": VERSAO_REGRAS,
                }
            },
            self.caminho_banco,
            datetime(2026, 8, 1, 12, 0),
        )

        self.assertTrue(resultado["saudavel"])
        self.assertEqual(resultado["ancoras_criadas"], 1)
        self.assertEqual(resultado["modelos_criados"], 0)
        avaliacao = resultado["avaliacao"]["por_mercado"]["gol_ft"]
        self.assertEqual(avaliacao["estado"], "formando_treino_prospectivo")
        self.assertEqual(avaliacao["treino"], 0)
        self.assertFalse(avaliacao["aplicacao_automatica"])

    def test_audita_cobertura_e_duracao_das_features_temporais(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/features/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "20 '",
            })
            features = {
                "schema_versao": VERSAO_FEATURES,
                "mercado": "gol_ft",
                "janelas": {
                    "5": {"disponivel": True,
                          "duracao_real_minutos": 5,
                          "chutes": [2, 1], "chutes_total": 3,
                          "chutes_por_minuto": 0.6,
                          "chutes_por_minuto_lados": [0.4, 0.2],
                          "escanteios": None, "escanteios_total": None,
                          "escanteios_por_minuto": None,
                          "escanteios_por_minuto_lados": None},
                    "10": {"disponivel": True,
                           "duracao_real_minutos": None},
                    "15": {"disponivel": False},
                },
            }
            banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                "status": "rejeitado", "features": features,
            }], "2026-07-20T12:00:00")

            auditoria = auditar_features_temporais(
                banco.conexao, datetime(2026, 7, 20, 12, 1),
                amostra_minima=1,
            )

            self.assertTrue(auditoria["saudavel"])
            self.assertEqual(auditoria["estado"], "avaliavel")
            self.assertEqual(auditoria["cobertura"], 1.0)
            self.assertEqual(auditoria["janelas_disponiveis"]["10"], 1)
            self.assertEqual(auditoria["duracoes_medidas"]["10"], 0)
        finally:
            banco.fechar()

    def test_detecta_regressao_de_features_depois_do_primeiro_registro(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            for indice, features in enumerate((
                {
                    "schema_versao": VERSAO_FEATURES,
                    "mercado": "gol_ft",
                    "janelas": {
                        str(item): {"disponivel": False}
                        for item in (5, 10, 15)
                    },
                },
                {},
            )):
                instante = f"2026-07-20T12:0{indice}:00"
                snapshot = banco.salvar_registro({
                    "coletado_em": instante,
                    "url": f"https://packball.com/match/features-{indice}/live",
                    "mandante": "A", "visitante": "B",
                    "placar": "0-0", "status": "20 '",
                })
                banco.salvar_candidatos(snapshot, [{
                    "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                    "status": "rejeitado", "features": features,
                }], instante)

            auditoria = auditar_features_temporais(
                banco.conexao, datetime(2026, 7, 20, 12, 2),
                amostra_minima=1,
            )

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual(auditoria["candidatos_validos"], 1)
            self.assertEqual(auditoria["candidatos"], 2)
            self.assertEqual(auditoria["cobertura"], 0.5)
        finally:
            banco.fechar()

    def test_supervisao_detecta_jogos_sem_candidatos(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            self._salvar_funil_recente(banco, com_candidatos=False)
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 12, 10)
            )
            self.assertFalse(estado["saudavel"])
            self.assertIn(
                "candidatos_ausentes_em_snapshots_recentes",
                estado["motivos"],
            )
            self.assertEqual(
                estado["funil_recente"]["cobertura_candidatos"], 0.0
            )
        finally:
            banco.fechar()

    def test_supervisao_avisa_baixa_cobertura_de_odds(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            self._salvar_funil_recente(banco, com_candidatos=True)
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 12, 10)
            )
            self.assertTrue(estado["saudavel"])
            self.assertTrue(estado["requer_atencao"])
            self.assertIn(
                "cobertura_odds_estruturadas_baixa", estado["avisos"]
            )
            self.assertEqual(
                estado["funil_recente"]["cobertura_candidatos"], 1.0
            )
            self.assertEqual(
                estado["funil_recente"]["cobertura_odds_estruturadas"], 0.0
            )
        finally:
            banco.fechar()

    def test_funil_exclui_snapshots_criados_apenas_para_liquidacao(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            self._salvar_funil_recente(banco, com_candidatos=True)
            banco.salvar_registro({
                "coletado_em": "2026-07-20T12:09:30",
                "url": "https://packball.com/match/recuperacao/live",
                "mandante": "C",
                "visitante": "D",
                "placar": "1-0",
                "status": "PEN",
                "qualidade": {
                    "pontuacao": 80,
                    "fontes": ["packball"],
                    "versao": "recuperacao-packball-v1",
                },
            })
            banco.salvar_registro({
                "coletado_em": "2026-07-20T12:09:40",
                "url": "https://packball.com/match/resultado-ht/live",
                "mandante": "E",
                "visitante": "F",
                "placar": "0-1",
                "status": "Intervalo",
                "qualidade": {
                    "pontuacao": 90,
                    "fontes": ["packball"],
                    "versao": "resultado-packball-ht-v1",
                },
            })

            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 12, 10)
            )

            funil = estado["funil_recente"]
            self.assertTrue(estado["saudavel"])
            self.assertEqual(funil["snapshots_ao_vivo"], 10)
            self.assertEqual(funil["snapshots_recuperacao_excluidos"], 1)
            self.assertEqual(funil["snapshots_liquidacao_excluidos"], 1)
            self.assertEqual(funil["cobertura_candidatos"], 1.0)
        finally:
            banco.fechar()

    def test_funil_exclui_snapshot_multifonte_sem_detalhe_packball(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            self._salvar_funil_recente(banco, com_candidatos=True)
            banco.salvar_registro({
                "coletado_em": "2026-07-20T12:09:50",
                "url": "https://packball.com/match/consenso-sombra/live",
                "mandante": "API A",
                "visitante": "API B",
                "placar": "0-0",
                "status": "29 '",
                "qualidade": {
                    "pontuacao": 90,
                    "fontes": ["api_football", "thestatsapi"],
                    "versao": "qualidade-consenso-multifonte-sombra-v1",
                },
                "contexto_api": {
                    "sem_detalhe_packball": True,
                    "consenso_multifonte_sombra": {"valido": True},
                },
            })

            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 12, 10)
            )

            funil = estado["funil_recente"]
            self.assertTrue(estado["saudavel"])
            self.assertEqual(funil["snapshots_ao_vivo"], 10)
            self.assertEqual(
                funil["snapshots_sombra_multifonte_excluidos"], 1
            )
            self.assertEqual(funil["cobertura_candidatos"], 1.0)
        finally:
            banco.fechar()

    def test_transicao_de_versao_nao_mistura_snapshots_da_regra_antiga(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            self._salvar_funil_recente(banco, com_candidatos=False)
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO calibracoes (
                        mercado, regra_versao, atualizado_em,
                        amostra, ativa, modelo_json
                    ) VALUES ('gol_ft', ?, '2026-07-20T12:08:00',
                              0, 0, ?)
                    """,
                    (
                        VERSAO_REGRAS,
                        json.dumps({
                            "politica_versao": POLITICA_CALIBRACAO_VERSAO,
                            "amostra_fingerprint": (
                                "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4"
                                "d8e11ba873c2f11161202b945"
                            )
                        }),
                    ),
                )
            snapshots_novos = banco.conexao.execute(
                """
                SELECT id FROM snapshots
                WHERE coletado_em >= '2026-07-20T12:08:00'
                ORDER BY id
                """
            ).fetchall()
            for snapshot in snapshots_novos:
                banco.salvar_candidatos(
                    snapshot["id"],
                    [{
                        "mercado": "gol_ft",
                        "regra_versao": VERSAO_REGRAS,
                        "status": "rejeitado",
                    }],
                    "2026-07-20T12:09:00",
                )

            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 12, 10)
            )

            funil = estado["funil_recente"]
            self.assertTrue(estado["saudavel"])
            self.assertTrue(funil["transicao_versao"])
            self.assertEqual(funil["snapshots_ao_vivo"], 2)
            self.assertEqual(funil["cobertura_candidatos"], 1.0)
            self.assertEqual(
                funil["estado"], "amostra_operacional_insuficiente"
            )
        finally:
            banco.fechar()

    def test_sem_dado_isolado_fica_na_telemetria_sem_gerar_alerta(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
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
            sinal_id = banco.salvar_candidatos(
                snapshot,
                [{
                    "mercado": "gol_ft",
                    "odd": 1.8,
                    "regra_versao": "sinais-v1",
                    "status": "aprovado",
                }],
                datetime(2026, 7, 20, 12, 0),
            )[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        fonte_resultado
                    ) VALUES (?, ?, 'sem_dado', 'sem_dado')
                    """,
                    (sinal_id, "2026-07-20T15:00:00"),
                )
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 16, 0)
            )
            self.assertTrue(estado["saudavel"])
            self.assertFalse(estado["requer_atencao"])
            self.assertEqual(estado["sem_dado_24h"], 1)
            self.assertEqual(estado["resultados_encerrados_24h"], 1)
            self.assertEqual(estado["taxa_sem_dado_24h"], 1.0)
            self.assertFalse(estado["sem_dado_24h_requer_atencao"])
            self.assertNotIn(
                "resultados_sem_dado_24h", estado["avisos"]
            )
        finally:
            banco.fechar()

    def test_sem_dado_repetido_e_proporcional_gera_atencao(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            for indice in range(3):
                snapshot = banco.salvar_registro(
                    {
                        "coletado_em": "2026-07-20T12:00:00",
                        "url": (
                            "https://packball.com/match/"
                            f"sem-dado-{indice}/live"
                        ),
                        "mandante": f"A{indice}",
                        "visitante": f"B{indice}",
                        "placar": "0-0",
                        "status": "20 '",
                    }
                )
                sinal_id = banco.salvar_candidatos(
                    snapshot,
                    [{
                        "mercado": "gol_ft",
                        "odd": 1.8,
                        "regra_versao": "sinais-v1",
                        "status": "aprovado",
                    }],
                    datetime(2026, 7, 20, 12, indice),
                )[0]
                with banco.conexao:
                    banco.conexao.execute(
                        """
                        INSERT INTO resultados_sinais (
                            sinal_id, encerrado_em, resultado,
                            fonte_resultado
                        ) VALUES (?, ?, 'sem_dado', 'sem_dado')
                        """,
                        (sinal_id, "2026-07-20T15:00:00"),
                    )
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 16, 0)
            )
            self.assertTrue(estado["saudavel"])
            self.assertTrue(estado["requer_atencao"])
            self.assertEqual(estado["sem_dado_24h"], 3)
            self.assertEqual(estado["resultados_encerrados_24h"], 3)
            self.assertEqual(estado["taxa_sem_dado_24h"], 1.0)
            self.assertTrue(estado["sem_dado_24h_requer_atencao"])
            self.assertIn("resultados_sem_dado_24h", estado["avisos"])
        finally:
            banco.fechar()

    def test_supervisao_bloqueia_calibracao_ativa_incompativel(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO calibracoes (
                        mercado, regra_versao, atualizado_em,
                        amostra, ativa, modelo_json
                    ) VALUES ('gol_ft', ?, ?, 100, 1, ?)
                    """,
                    (
                        VERSAO_REGRAS,
                        "2026-07-20T12:00:00",
                        json.dumps({"populacao": "legada"}),
                    ),
                )
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 16, 0)
            )
            self.assertFalse(estado["saudavel"])
            self.assertEqual(
                estado["calibracoes_ativas_incompativeis"], 1
            )
            self.assertIn(
                "calibracao_ativa_incompativel", estado["motivos"]
            )
        finally:
            banco.fechar()

    def test_supervisao_bloqueia_resultado_sem_proveniencia(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro(
                {
                    "coletado_em": "2026-07-20T12:00:00",
                    "url": "https://packball.com/match/1/live",
                    "mandante": "A",
                    "visitante": "B",
                    "placar": "0-0",
                    "status": "60 '",
                }
            )
            sinal = banco.salvar_candidatos(
                snapshot,
                [{
                    "mercado": "gol_ft",
                    "regra_versao": VERSAO_REGRAS,
                    "status": "aprovado",
                }],
            )[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado
                    ) VALUES (?, '2026-07-20T12:30:00', 'red')
                    """,
                    (sinal,),
                )
            snapshot_posterior = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:30:00",
                "url": "https://packball.com/match/resumo/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "70 '",
            })
            sinal_posterior = banco.salvar_candidatos(
                snapshot_posterior,
                [{
                    "mercado": "gol_ft", "linha": 0.5, "odd": 1.8,
                    "pontuacao_tecnica": 82,
                    "regra_versao": VERSAO_REGRAS,
                    "status": "aprovado",
                }],
                "2026-07-20T12:30:00",
            )[0]
            with banco.conexao:
                banco.conexao.execute(
                    "UPDATE sinais SET status='simulacao' WHERE id=?",
                    (sinal_posterior,),
                )

            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 12, 31)
            )

            self.assertFalse(estado["saudavel"])
            self.assertIn(
                "proveniencia_resultados_inconsistente",
                estado["motivos"],
            )
            self.assertEqual(
                estado["proveniencia_resultados"]["inconsistentes"], 1
            )
        finally:
            banco.fechar()

    def test_supervisao_detecta_resultado_telegram_sem_aviso(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/telegram/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.8,
                "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }], "2026-07-20T12:00:00")[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, snapshot_id_liquidacao,
                        fonte_resultado
                    ) VALUES (?, '2026-07-20T12:01:00', 'green', 0.8, ?,
                              'packball')
                    """,
                    (sinal, snapshot),
                )
                banco.conexao.execute(
                    """
                    INSERT INTO entregas_alertas (
                        sinal_id, canal, tentado_em, entregue_em,
                        status, tentativas
                    ) VALUES (?, 'chat:teste', '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'entregue', 1)
                    """,
                    (sinal,),
                )

            recente = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 3)
            )
            vencido = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 12, 10)
            )

            self.assertTrue(recente["saudavel"])
            self.assertEqual(
                vencido["integridade_telegram"]["resultados_sem_aviso"], 1
            )
            self.assertEqual(
                vencido["integridade_telegram"][
                    "resultados_analise_sem_aviso"
                ],
                1,
            )
            self.assertTrue(
                vencido["integridade_telegram"]["saudavel_operacional"]
            )
            self.assertNotIn(
                "integridade_telegram_inconsistente", vencido["motivos"]
            )
        finally:
            banco.fechar()

    def test_revisao_entregue_satisfaz_integridade_do_resultado_corrigido(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/telegram-void/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "escanteios_ft_asiatico",
                "linha": 9.5, "odd": 1.825,
                "regra_versao": VERSAO_REGRAS,
                "status": "simulacao",
            }])[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, fonte_resultado
                    ) VALUES (?, '2026-07-20T11:59:00', 'red', -1.0,
                              'packball')
                    """,
                    (sinal,),
                )
                banco.conexao.execute(
                    """
                    INSERT INTO entregas_alertas (
                        sinal_id, canal, tentado_em, entregue_em,
                        status, tentativas
                    ) VALUES (?, 'chat:teste', '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'entregue', 1)
                    """,
                    (sinal,),
                )
                banco.conexao.execute(
                    """
                    INSERT INTO revisoes_resultados (
                        sinal_id, revisado_em, encerrado_em_anterior,
                        resultado_anterior, retorno_anterior, motivo,
                        fonte_resultado_anterior, notificacao_status
                    ) VALUES (?, '2026-07-20T12:02:00',
                              '2026-07-20T11:59:00', 'red', -1.0,
                              'odd substituida antes do envio', 'packball',
                              'pendente')
                    """,
                    (sinal,),
                )
                banco.conexao.execute(
                    "DELETE FROM resultados_sinais WHERE sinal_id=?",
                    (sinal,),
                )
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, fonte_resultado
                    ) VALUES (?, '2026-07-20T12:01:00', 'void', 0.0,
                              'invalidacao_operacional_odds')
                    """,
                    (sinal,),
                )
                banco.conexao.execute(
                    """
                    UPDATE revisoes_resultados
                    SET notificacao_status='entregue'
                    WHERE sinal_id=?
                    """,
                    (sinal,),
                )

            auditoria = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 10)
            )

            self.assertEqual(auditoria["resultados_sem_aviso"], 0)
            self.assertEqual(auditoria["resultados_analise_sem_aviso"], 0)
            self.assertTrue(auditoria["saudavel"])
        finally:
            banco.fechar()

    def test_auditoria_telegram_detecta_aviso_orfao(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/telegram-orfao/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }])[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO entregas_alertas (
                        sinal_id, canal, tentado_em, entregue_em,
                        status, tentativas
                    ) VALUES (?, 'chat:teste:resultado',
                              '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'entregue', 1)
                    """,
                    (sinal,),
                )

            auditoria = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 10)
            )

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual(auditoria["avisos_sem_resultado"], 1)
        finally:
            banco.fechar()

    def test_auditoria_telegram_detecta_bloqueio_do_gateway_oficial(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/gateway/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }])[0]
            banco.registrar_entrega_alerta(
                sinal,
                "gateway:oficial",
                "bloqueado",
                "calibracao_atual_invalida",
                "2026-07-20T12:00:00",
            )

            auditoria = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 10)
            )

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual(auditoria["bloqueios_gateway_24h"], 1)
        finally:
            banco.fechar()

    def test_auditoria_telegram_detecta_envio_sem_estado_final(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/envio-incerto/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }])[0]
            banco.registrar_entrega_alerta(
                sinal, "chat", "enviando", instante="2026-07-20T12:00:00"
            )

            incerto = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 3)
            )
            banco.registrar_entrega_alerta(
                sinal, "chat", "entregue", instante="2026-07-20T12:04:00"
            )
            confirmado = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 5)
            )

            self.assertFalse(incerto["saudavel"])
            self.assertFalse(incerto["saudavel_operacional"])
            self.assertEqual(incerto["envios_incertos"], 1)
            self.assertTrue(confirmado["saudavel"])
            self.assertEqual(confirmado["envios_incertos"], 0)
        finally:
            banco.fechar()

    def test_envio_incerto_de_analise_nao_degrada_operacao(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/analise-incerta/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }])[0]
            banco.registrar_entrega_alerta(
                sinal, "chat:teste:resultado", "incerto",
                instante="2026-07-20T12:00:00",
            )

            auditoria = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 3)
            )

            self.assertFalse(auditoria["saudavel"])
            self.assertTrue(auditoria["saudavel_operacional"])
            self.assertEqual(auditoria["envios_oficiais_incertos"], 0)
            self.assertEqual(auditoria["envios_analise_incertos"], 1)
        finally:
            banco.fechar()

    def test_auditoria_telegram_exige_prova_coerente_em_envio_novo(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/prova-telegram/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }])[0]
            banco.registrar_entrega_alerta(
                sinal, "chat", "entregue",
                instante="2026-07-20T12:00:00",
                provedor="telegram",
                provedor_destino_id="chat",
                provedor_mensagem_id="77",
                confirmacao={
                    "provedor": "telegram", "ok": True,
                    "message_id": 78,
                },
            )

            auditoria = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 1)
            )

            self.assertFalse(auditoria["saudavel"])
            self.assertEqual(
                auditoria["confirmacoes_telegram_invalidas"], 1
            )
        finally:
            banco.fechar()

    def test_auditoria_telegram_aceita_prova_valida_e_detecta_reuso(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/prova-reuso/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }])[0]
            prova = {
                "provedor": "telegram", "ok": True, "message_id": 88,
            }
            banco.registrar_entrega_alerta(
                sinal, "chat", "entregue",
                instante="2026-07-20T12:00:00",
                provedor="telegram",
                provedor_destino_id="chat",
                provedor_mensagem_id="88",
                confirmacao=prova,
            )
            valida = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 1)
            )
            with banco.conexao:
                cursor = banco.conexao.execute(
                    """
                    INSERT INTO revisoes_resultados (
                        sinal_id, revisado_em, encerrado_em_anterior,
                        resultado_anterior, motivo
                    ) VALUES (?, '2026-07-20T12:00:00',
                              '2026-07-20T11:59:00', 'green', 'teste')
                    """,
                    (sinal,),
                )
            banco.marcar_revisao_resultado_notificada(
                cursor.lastrowid, "entregue",
                provedor="telegram",
                provedor_destino_id="chat",
                provedor_mensagem_id="88",
                confirmacao=prova,
            )
            reutilizada = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 1)
            )

            self.assertTrue(valida["saudavel"])
            self.assertEqual(valida["confirmacoes_telegram_validas"], 1)
            self.assertFalse(reutilizada["saudavel"])
            self.assertEqual(
                reutilizada["confirmacoes_telegram_duplicadas"], 1
            )
        finally:
            banco.fechar()

    def test_revisao_sem_sinal_entregue_nao_e_pendencia_telegram(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/revisao-interna/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }])[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO revisoes_resultados (
                        sinal_id, revisado_em, encerrado_em_anterior,
                        resultado_anterior, motivo
                    ) VALUES (?, '2026-07-20T12:00:00',
                              '2026-07-20T11:59:00', 'green', 'teste')
                    """,
                    (sinal,),
                )

            auditoria = auditar_integridade_telegram(
                banco.conexao, datetime(2026, 7, 20, 12, 10)
            )

            self.assertTrue(auditoria["saudavel"])
            self.assertEqual(auditoria["correcoes_pendentes"], 0)
        finally:
            banco.fechar()

    def test_supervisao_bloqueia_calibracao_ativa_desatualizada(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        with patch(
            "watchdog.auditar_frescor_calibracoes_por_mercado",
            return_value={
                "ativas": 1,
                "desatualizadas": 1,
                "saudavel": False,
                "detalhes": [],
            },
        ):
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 16, 0)
            )

        self.assertFalse(estado["saudavel"])
        self.assertIn(
            "calibracao_ativa_desatualizada", estado["motivos"]
        )

    def test_supervisao_detecta_calibracao_inativa_desatualizada(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        with patch(
            "watchdog.auditar_frescor_calibracoes_por_mercado",
            return_value={
                "ativas": 0,
                "inativas": 1,
                "desatualizadas": 1,
                "desatualizadas_ativas": 0,
                "desatualizadas_inativas": 1,
                "saudavel": False,
                "detalhes": [],
            },
        ):
            estado = verificar_validacao(
                self.caminho_banco, datetime(2026, 7, 20, 16, 0)
            )

        self.assertFalse(estado["saudavel"])
        self.assertIn(
            "calibracao_inativa_desatualizada", estado["motivos"]
        )

    def test_supervisao_tolera_reconciliacao_recente_durante_ciclo(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        frescor = {
            "ativas": 0,
            "inativas": 1,
            "desatualizadas": 1,
            "desatualizadas_ativas": 0,
            "desatualizadas_inativas": 1,
            "saudavel": False,
            "detalhes": [{
                "mercado": "gol_ft",
                "ativa": False,
                "desatualizada": True,
                "ultimo_resultado_em": "2026-07-20T15:59:00",
            }],
        }
        with patch(
            "watchdog.auditar_frescor_calibracoes_por_mercado",
            return_value=frescor,
        ):
            durante_ciclo = verificar_validacao(
                self.caminho_banco,
                datetime(2026, 7, 20, 16, 0),
                estado_coleta={"ciclo_em_andamento": True},
            )
            fora_do_ciclo = verificar_validacao(
                self.caminho_banco,
                datetime(2026, 7, 20, 16, 0),
                estado_coleta={"ciclo_em_andamento": False},
            )
            persistente = verificar_validacao(
                self.caminho_banco,
                datetime(2026, 7, 20, 16, 6),
                estado_coleta={"ciclo_em_andamento": True},
            )

        self.assertNotIn(
            "calibracao_inativa_desatualizada",
            durante_ciclo["motivos"],
        )
        self.assertEqual(
            durante_ciclo["frescor_calibracoes"][
                "reconciliacao_em_andamento"
            ],
            1,
        )
        self.assertNotIn(
            "calibracao_inativa_desatualizada",
            fora_do_ciclo["motivos"],
        )
        self.assertEqual(
            fora_do_ciclo["frescor_calibracoes"][
                "reconciliacao_em_andamento"
            ],
            1,
        )
        self.assertIn(
            "calibracao_inativa_desatualizada",
            persistente["motivos"],
        )

    def test_supervisao_nao_mascara_calibracao_ativa_fora_do_ciclo(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        frescor = {
            "ativas": 1,
            "inativas": 0,
            "desatualizadas": 1,
            "desatualizadas_ativas": 1,
            "desatualizadas_inativas": 0,
            "saudavel": False,
            "detalhes": [{
                "mercado": "gol_ft",
                "ativa": True,
                "desatualizada": True,
                "ultimo_resultado_em": "2026-07-20T15:59:00",
            }],
        }
        with patch(
            "watchdog.auditar_frescor_calibracoes_por_mercado",
            return_value=frescor,
        ):
            estado = verificar_validacao(
                self.caminho_banco,
                datetime(2026, 7, 20, 16, 0),
                estado_coleta={"ciclo_em_andamento": False},
            )

        self.assertIn(
            "calibracao_ativa_desatualizada",
            estado["motivos"],
        )
        self.assertEqual(
            estado["frescor_calibracoes"][
                "desatualizadas_ativas_alertaveis"
            ],
            1,
        )

    def test_supervisao_persiste_contexto_sombra_sem_bloquear_sinais(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        estado = verificar_validacao(
            self.caminho_banco, datetime(2026, 7, 20, 16, 0)
        )
        self.assertEqual(
            estado["avaliacao_contexto"]["modo"],
            "sombra_causal_holdout_fixo",
        )
        self.assertEqual(
            estado["avaliacao_contexto"]["amostra_total"], 0
        )
        historico = persistir_historico_avaliacao_contexto(
            estado,
            self.caminho_banco,
            datetime(2026, 7, 20, 16, 1),
        )
        self.assertTrue(historico["saudavel"])
        self.assertEqual(historico["total"], 0)
        self.assertTrue(historico["ancoras_pre_registradas"])

    def test_supervisao_reporta_modelo_sombra_invalido_sem_encerrar(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        with patch(
            "watchdog.avaliar_pontuacao_sombra",
            return_value={
                "integro": False,
                "por_mercado": {
                    "gol_ft": {
                        "integro": False,
                        "estado": "modelo_invalido",
                    },
                },
            },
        ):
            estado = verificar_validacao(
                self.caminho_banco,
                datetime(2026, 7, 20, 16, 0),
            )

        self.assertTrue(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertIn(
            "pontuacao_sombra_inconsistente", estado["avisos"]
        )

    def test_supervisao_detecta_historico_contextual_inconsistente(self):
        banco = BancoMonitor(self.caminho_banco)
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
                        VERSAO_REGRAS,
                        "gol_ft",
                        "2026-07-20T15:59:00",
                        999,
                        1,
                        "inconclusiva",
                        0,
                        "{json-invalido",
                    ),
                )
        finally:
            banco.fechar()

        estado = verificar_validacao(
            self.caminho_banco,
            datetime(2026, 7, 20, 16, 0),
        )

        self.assertTrue(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertIn(
            "historico_avaliacao_contexto_inconsistente",
            estado["avisos"],
        )
        self.assertFalse(
            estado["historico_avaliacao_contexto"]["saudavel"]
        )

    def test_supervisao_bloqueia_protecao_da_exploracao_gols_ausente(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            registrar_ou_validar_definicao_exploracao_gols(
                banco.conexao
            )
            registrar_ou_validar_politica_avaliacao_gols(
                banco.conexao
            )
            registrar_ou_validar_definicao_exploracao_gol_ft_v3(
                banco.conexao
            )
            registrar_ou_validar_politica_avaliacao_gol_ft_v3(
                banco.conexao
            )
            with banco.conexao:
                banco.conexao.execute(
                    """
                    DROP TRIGGER
                    trg_exploracao_sombra_definicao_update_imutavel
                    """
                )
        finally:
            banco.fechar()

        estado = verificar_validacao(
            self.caminho_banco,
            datetime(2026, 7, 20, 16, 0),
        )

        self.assertFalse(estado["saudavel"])
        self.assertTrue(estado["requer_atencao"])
        self.assertIn(
            "definicao_exploracao_gols_inconsistente",
            estado["motivos"],
        )
        self.assertFalse(
            estado["definicao_exploracao_gols"]["saudavel"]
        )

        reparado = BancoMonitor(self.caminho_banco)
        reparado.fechar()
        recuperado = verificar_validacao(
            self.caminho_banco,
            datetime(2026, 7, 20, 16, 1),
        )
        self.assertNotIn(
            "definicao_exploracao_gols_inconsistente",
            recuperado["motivos"],
        )
        self.assertTrue(
            recuperado["definicao_exploracao_gols"]["saudavel"]
        )

    def test_supervisao_bloqueia_contador_da_api_corrompido(self):
        pasta = Path.cwd() / ".teste_watchdog_contador_api"
        pasta.mkdir(exist_ok=True)
        caminho_banco = pasta / "monitor.db"
        contador = pasta / "api_football_uso.json"
        banco = BancoMonitor(caminho_banco)
        banco.fechar()
        contador.write_text("{inválido", encoding="utf-8")
        try:
            estado = verificar_validacao(
                caminho_banco, datetime(2026, 7, 20, 16, 0)
            )

            self.assertFalse(estado["saudavel"])
            self.assertTrue(estado["requer_atencao"])
            self.assertIn("contador_api_inseguro", estado["motivos"])
            self.assertEqual(
                estado["contador_api"]["estado"], "corrompido"
            )
        finally:
            for arquivo in pasta.iterdir():
                arquivo.unlink()
            pasta.rmdir()

    def test_validacao_marca_cota_do_provedor_de_dia_anterior(self):
        pasta = Path.cwd() / ".teste_watchdog_cota_provedor_anterior"
        pasta.mkdir(exist_ok=True)
        caminho_banco = pasta / "monitor.db"
        contador = pasta / "api_football_uso.json"
        banco = BancoMonitor(caminho_banco)
        banco.fechar()
        contador.write_text(json.dumps({
            "versao": 2,
            "meses": {"2026-07": 4968},
            "dias": {"2026-07-20": {"externo": 4968}},
            "provedor": {
                "dia": "2026-07-20",
                "limite_diario": 7500,
                "restante_diario": 2532,
                "limite_minuto": 300,
                "restante_minuto": 297,
                "observado_em": 1.0,
            },
        }), encoding="utf-8")
        try:
            estado = verificar_validacao(
                caminho_banco, datetime(2026, 7, 21, 16, 0)
            )

            cota = estado["contador_api"]
            self.assertEqual(cota["dia"], "2026-07-21")
            self.assertEqual(cota["cota_provedor_dia"], "2026-07-20")
            self.assertFalse(cota["cota_provedor_vigente"])
            self.assertEqual(cota["limite_diario_seguro"], 7000)
            self.assertEqual(cota["restante_seguro_dia"], 7000)
        finally:
            for arquivo in pasta.iterdir():
                arquivo.unlink()
            pasta.rmdir()

    def test_alerta_de_validacao_nao_repete_mesma_assinatura(self):
        mensagens = []
        validacao = {
            "requer_atencao": True,
            "motivos": ["amostra_estagnada"],
            "avisos": [],
            "pendencias_vencidas": 0,
            "sem_dado_24h": 0,
        }
        primeiro = atualizar_alerta_validacao(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        segundo = atualizar_alerta_validacao(
            dict(validacao), primeiro, lambda texto: mensagens.append(texto) or True
        )
        self.assertTrue(primeiro["alertado"])
        self.assertTrue(segundo["alertado"])
        self.assertEqual(len(mensagens), 1)
        self.assertIn("ATENÇÃO OPERACIONAL DO BOT", mensagens[0])
        self.assertIn("Monitor e coleta continuam ativos", mensagens[0])

    def test_alerta_de_validacao_identifica_pendencia_vencida(self):
        mensagens = []
        atualizar_alerta_validacao(
            {
                "requer_atencao": True,
                "motivos": ["pendencias_acima_180_minutos"],
                "avisos": [],
                "pendencias_vencidas": 1,
                "sem_dado_24h": 0,
                "detalhes_pendencias_vencidas": [{
                    "partida": "Time A x Time B",
                    "mercado": "gol_ft",
                    "idade_minutos": 241.2,
                }],
            },
            {},
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("pendencias_acima_180_minutos", mensagens[0])
        self.assertNotIn("Time A x Time B", mensagens[0])

    def test_alerta_de_validacao_orienta_envio_oficial_incerto_sem_repetir(self):
        mensagens = []
        validacao = {
            "requer_atencao": True,
            "motivos": ["integridade_telegram_inconsistente"],
            "avisos": [],
            "integridade_telegram": {"envios_incertos": 1},
        }

        primeiro = atualizar_alerta_validacao(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        segundo = atualizar_alerta_validacao(
            dict(validacao),
            primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("ENVIO OFICIAL SEM CONFIRMAÇÃO", mensagens[0])
        self.assertIn("Novas entradas oficiais estão pausadas", mensagens[0])
        self.assertIn("python resolver_envio_incerto.py", mensagens[0])
        self.assertEqual(primeiro["envios_incertos_notificados"], 1)
        self.assertEqual(segundo["envios_incertos_notificados"], 1)

    def test_alerta_de_validacao_avisa_incerto_novo_durante_outra_falha(self):
        mensagens = []
        primeiro = atualizar_alerta_validacao(
            {
                "requer_atencao": True,
                "motivos": ["integridade_telegram_inconsistente"],
                "avisos": [],
                "integridade_telegram": {"envios_incertos": 0},
            },
            {},
            lambda texto: mensagens.append(texto) or True,
        )
        atualizar_alerta_validacao(
            {
                "requer_atencao": True,
                "motivos": ["integridade_telegram_inconsistente"],
                "avisos": [],
                "integridade_telegram": {"envios_incertos": 1},
            },
            primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 2)
        self.assertNotIn("ENVIO OFICIAL SEM CONFIRMAÇÃO", mensagens[0])
        self.assertIn("ENVIO OFICIAL SEM CONFIRMAÇÃO", mensagens[1])

    def test_alerta_de_validacao_separa_resultado_de_analise_incerto(self):
        mensagens = []
        atualizar_alerta_validacao(
            {
                "requer_atencao": True,
                "motivos": ["integridade_telegram_inconsistente"],
                "avisos": [],
                "integridade_telegram": {
                    "envios_incertos": 2,
                    "envios_oficiais_incertos": 0,
                    "envios_analise_incertos": 2,
                },
            },
            {},
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("RESULTADO DE ANÁLISE SEM CONFIRMAÇÃO", mensagens[0])
        self.assertIn("não pausa novas análises", mensagens[0])
        self.assertNotIn("ENVIO OFICIAL SEM CONFIRMAÇÃO", mensagens[0])

    def test_alerta_de_validacao_recupera_e_reativa_detector_de_incerto(self):
        mensagens = []
        inicio = datetime(2026, 8, 8, 9, 0, 0)
        com_incerto = atualizar_alerta_validacao(
            {
                "requer_atencao": True,
                "motivos": ["integridade_telegram_inconsistente"],
                "avisos": [],
                "integridade_telegram": {"envios_incertos": 1},
            },
            {},
            lambda texto: mensagens.append(texto) or True,
            agora=inicio,
        )
        recuperado = com_incerto
        for minuto in (1, 2, 16):
            recuperado = atualizar_alerta_validacao(
                {
                    "requer_atencao": False,
                    "motivos": [],
                    "avisos": [],
                    "integridade_telegram": {"envios_incertos": 0},
                },
                recuperado,
                lambda texto: mensagens.append(texto) or True,
                agora=inicio + timedelta(minutes=minuto),
            )

        self.assertEqual(len(mensagens), 2)
        self.assertIn("recuperado", mensagens[1])
        self.assertFalse(recuperado["alertado"])
        self.assertEqual(recuperado["envios_incertos_notificados"], 0)

    def test_alerta_de_validacao_nao_repete_oscilacao_nao_critica(self):
        mensagens = []
        primeiro = {}
        for _ in range(3):
            primeiro = atualizar_alerta_validacao(
                {
                    "requer_atencao": True,
                    "motivos": [],
                    "avisos": ["cobertura_api_caiu_versus_base"],
                },
                primeiro,
                lambda texto: mensagens.append(texto) or True,
            )
        segundo = atualizar_alerta_validacao(
            {
                "requer_atencao": True,
                "motivos": ["capacidade_coleta_saturada"],
                "avisos": [],
            },
            primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertEqual(
            segundo["causas_validacao_notificadas"],
            ["cobertura_api_caiu_versus_base"],
        )
        self.assertEqual(
            segundo["alerta_validacao_causas_pendentes"],
            ["capacidade_coleta_saturada"],
        )

    def test_alerta_oscilante_exige_tres_ciclos_e_aplica_cooldown(self):
        mensagens = []
        inicio = datetime(2026, 8, 8, 10, 0, 0)
        ruim = {
            "requer_atencao": True,
            "motivos": ["cobertura_odds_estruturadas_baixa"],
            "avisos": [],
            "pendencias_vencidas": 0,
            "sem_dado_24h": 0,
        }
        saudavel = {
            "requer_atencao": False,
            "motivos": [],
            "avisos": [],
        }
        estado = {}
        for ciclo in range(2):
            estado = atualizar_alerta_validacao(
                dict(ruim), estado,
                enviar=lambda texto: mensagens.append(texto) or True,
                agora=inicio + timedelta(minutes=ciclo),
            )
        self.assertEqual(mensagens, [])
        self.assertFalse(estado["alertado"])

        estado = atualizar_alerta_validacao(
            dict(ruim), estado,
            enviar=lambda texto: mensagens.append(texto) or True,
            agora=inicio + timedelta(minutes=2),
        )
        self.assertEqual(len(mensagens), 1)
        self.assertTrue(estado["alertado"])

        for ciclo in range(2):
            estado = atualizar_alerta_validacao(
                dict(saudavel), estado,
                enviar=lambda texto: mensagens.append(texto) or True,
                agora=inicio + timedelta(minutes=3 + ciclo),
            )
        self.assertEqual(len(mensagens), 1)
        self.assertTrue(estado["alertado"])
        estado = atualizar_alerta_validacao(
            dict(saudavel), estado,
            enviar=lambda texto: mensagens.append(texto) or True,
            agora=inicio + timedelta(minutes=5),
        )
        self.assertEqual(len(mensagens), 1)
        self.assertTrue(estado["alertado"])
        estado = atualizar_alerta_validacao(
            dict(saudavel), estado,
            enviar=lambda texto: mensagens.append(texto) or True,
            agora=inicio + timedelta(minutes=18),
        )
        self.assertEqual(len(mensagens), 2)
        self.assertIn("recuperado", mensagens[-1])

        for ciclo in range(3):
            estado = atualizar_alerta_validacao(
                dict(ruim), estado,
                enviar=lambda texto: mensagens.append(texto) or True,
                agora=inicio + timedelta(minutes=19 + ciclo),
            )
        self.assertEqual(len(mensagens), 2)
        self.assertFalse(estado["alertado"])

    def test_recuperacao_do_funil_reinicia_janela_apos_flapping(self):
        mensagens = []
        inicio = datetime(2026, 8, 8, 11, 0, 0)
        ruim = {
            "requer_atencao": True,
            "motivos": ["integridade_telegram_inconsistente"],
            "avisos": [],
            "integridade_telegram": {"envios_incertos": 0},
        }
        saudavel = {
            "requer_atencao": False,
            "motivos": [],
            "avisos": [],
        }
        estado = atualizar_alerta_validacao(
            dict(ruim), {},
            enviar=lambda texto: mensagens.append(texto) or True,
            agora=inicio,
        )
        for minuto in (1, 5):
            estado = atualizar_alerta_validacao(
                dict(saudavel), estado,
                enviar=lambda texto: mensagens.append(texto) or True,
                agora=inicio + timedelta(minutes=minuto),
            )

        estado = atualizar_alerta_validacao(
            dict(ruim), estado,
            enviar=lambda texto: mensagens.append(texto) or True,
            agora=inicio + timedelta(minutes=10),
        )
        self.assertIsNone(
            estado["alerta_validacao_recuperacao_iniciada_em"]
        )
        for minuto in (11, 12, 20):
            estado = atualizar_alerta_validacao(
                dict(saudavel), estado,
                enviar=lambda texto: mensagens.append(texto) or True,
                agora=inicio + timedelta(minutes=minuto),
            )

        self.assertEqual(len(mensagens), 1)
        self.assertTrue(estado["alertado"])
        estado = atualizar_alerta_validacao(
            dict(saudavel), estado,
            enviar=lambda texto: mensagens.append(texto) or True,
            agora=inicio + timedelta(minutes=26),
        )
        self.assertEqual(len(mensagens), 2)
        self.assertIn("recuperado", mensagens[-1])
        self.assertFalse(estado["alertado"])

    def test_falha_na_recuperacao_preserva_alerta_e_tenta_uma_vez(self):
        inicio = datetime(2026, 8, 8, 12, 0, 0)
        ruim = {
            "requer_atencao": True,
            "motivos": ["integridade_telegram_inconsistente"],
            "avisos": [],
            "integridade_telegram": {"envios_incertos": 0},
        }
        saudavel = {
            "requer_atencao": False,
            "motivos": [],
            "avisos": [],
        }
        estado = atualizar_alerta_validacao(
            dict(ruim), {}, enviar=Mock(return_value=True), agora=inicio
        )
        assinatura_alertada = estado["assinatura_alertada"]
        causas_notificadas = estado["causas_validacao_notificadas"]
        historico_envios = estado["alerta_validacao_ultimos_envios"]
        enviar_recuperacao = Mock(side_effect=[False, True])
        for minuto in (1, 2):
            estado = atualizar_alerta_validacao(
                dict(saudavel), estado,
                enviar=enviar_recuperacao,
                agora=inicio + timedelta(minutes=minuto),
            )

        falhou = atualizar_alerta_validacao(
            dict(saudavel), estado,
            enviar=enviar_recuperacao,
            agora=inicio + timedelta(minutes=16),
        )
        self.assertTrue(falhou["alertado"])
        self.assertTrue(falhou["alerta_validacao_recuperacao_pendente"])
        self.assertEqual(falhou["assinatura_alertada"], assinatura_alertada)
        self.assertEqual(
            falhou["causas_validacao_notificadas"], causas_notificadas
        )
        self.assertEqual(
            falhou["alerta_validacao_ultimos_envios"], historico_envios
        )

        recuperou = atualizar_alerta_validacao(
            dict(saudavel), falhou,
            enviar=enviar_recuperacao,
            agora=inicio + timedelta(minutes=17),
        )
        repetido = atualizar_alerta_validacao(
            dict(saudavel), recuperou,
            enviar=enviar_recuperacao,
            agora=inicio + timedelta(minutes=18),
        )
        self.assertEqual(enviar_recuperacao.call_count, 2)
        self.assertFalse(repetido["alertado"])
        self.assertEqual(repetido["alerta_validacao_ciclos_recuperacao"], 0)
        self.assertIsNone(
            repetido["alerta_validacao_recuperacao_iniciada_em"]
        )

    def test_alerta_agrupa_causas_oscilantes_confirmadas(self):
        mensagens = []
        estado = {}
        for _ in range(3):
            estado = atualizar_alerta_validacao(
                {
                    "requer_atencao": True,
                    "motivos": ["capacidade_coleta_saturada"],
                    "avisos": ["cobertura_odds_estruturadas_baixa"],
                },
                estado,
                enviar=lambda texto: mensagens.append(texto) or True,
            )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("capacidade_coleta_saturada", mensagens[0])
        self.assertIn("cobertura_odds_estruturadas_baixa", mensagens[0])

    def test_antispam_migra_alerta_oscilante_antigo_para_cooldown(self):
        agora = datetime(2026, 8, 8, 14, 30, 0)
        atual = atualizar_alerta_validacao(
            {
                "requer_atencao": True,
                "motivos": ["experimento_ritmo_packball_regressao"],
                "avisos": [],
            },
            {
                "alertado": True,
                "assinatura_alertada": "legado",
                "causas_validacao_notificadas": [
                    "experimento_ritmo_packball_regressao"
                ],
            },
            enviar=Mock(return_value=True),
            agora=agora,
        )

        self.assertEqual(
            atual["alerta_validacao_ultimos_envios"][
                "experimento_ritmo_packball_regressao"
            ],
            "2026-08-08T14:30:00",
        )

    def test_alerta_de_validacao_repete_apenas_ao_escalar_para_critico(self):
        mensagens = []
        primeiro = {}
        for _ in range(3):
            primeiro = atualizar_alerta_validacao(
                {
                    "requer_atencao": True,
                    "motivos": [],
                    "avisos": ["cobertura_api_caiu_versus_base"],
                },
                primeiro,
                lambda texto: mensagens.append(texto) or True,
            )
        segundo = atualizar_alerta_validacao(
            {
                "requer_atencao": True,
                "motivos": ["proveniencia_resultados_inconsistente"],
                "avisos": [],
            },
            primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 2)
        self.assertIn(
            "proveniencia_resultados_inconsistente", mensagens[1]
        )

    @staticmethod
    def _experimento_ritmo(estado):
        return {
            "versao": "ritmo-packball-v2",
            "avaliavel": True,
            "saudavel": estado != "regressao_recomendada",
            "estado": estado,
            "regime_atual": "distribuido:21.929:28:600",
            "iniciado_em": "2026-07-25T20:04:13",
            "minutos_observados": 50,
            "pausas_packball": 0,
            "retencao_fluxo": 1.02,
            "retencao_temporal": 1.1,
            "base": {
                "processadas_por_10_minutos": 12.5,
                "cobertura_temporal": 0.2,
            },
            "experimento": {
                "ciclos": 12,
                "processadas_por_10_minutos": 12.75,
                "cobertura_temporal": 0.22,
            },
        }

    def test_ritmo_em_observacao_nao_gera_mensagem(self):
        enviar = Mock(return_value=True)
        atual = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "em_observacao"
                )
            },
            {},
            enviar=enviar,
        )

        enviar.assert_not_called()
        self.assertIn(
            "em_observacao",
            atual["experimento_ritmo_assinatura_notificada"],
        )

    def test_aprovacao_do_ritmo_notifica_uma_vez_e_explica_limite(self):
        mensagens = []
        observacao = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "em_observacao"
                )
            },
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        aprovado = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "aprovado"
                )
            },
            observacao,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "aprovado"
                )
            },
            aprovado,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("RITMO PACKBALL VALIDADO", mensagens[0])
        self.assertIn("não representa confiança dos sinais", mensagens[0])
        self.assertEqual(
            repetido["experimento_ritmo_assinatura_notificada"],
            aprovado["experimento_ritmo_assinatura_notificada"],
        )

    def test_falha_de_envio_da_aprovacao_e_tentada_novamente(self):
        anterior = {
            "experimento_ritmo_assinatura_notificada": (
                "ritmo-packball-v2|distribuido:21.929:28:600|"
                "2026-07-25T20:04:13|em_observacao"
            )
        }
        enviar = Mock(side_effect=[False, True])
        falhou = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "aprovado"
                )
            },
            anterior,
            enviar=enviar,
        )
        recuperou = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "aprovado"
                )
            },
            falhou,
            enviar=enviar,
        )

        self.assertEqual(enviar.call_count, 2)
        self.assertNotIn(
            "ritmo-packball-v2|distribuido:21.929:28:600|"
            "2026-07-25T20:04:13|aprovado",
            falhou["experimento_ritmo_assinaturas_notificadas"],
        )
        self.assertIn(
            "aprovado",
            recuperou["experimento_ritmo_assinatura_notificada"],
        )
        self.assertIn(
            recuperou["experimento_ritmo_assinatura_notificada"],
            recuperou["experimento_ritmo_assinaturas_notificadas"],
        )

    def test_ritmo_a_b_a_nao_repete_assinatura_ja_entregue(self):
        mensagens = []
        aprovado = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "aprovado"
                )
            },
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        regressao = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "regressao_recomendada"
                )
            },
            aprovado,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "aprovado"
                )
            },
            regressao,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 2)
        self.assertIn("RITMO PACKBALL VALIDADO", mensagens[0])
        self.assertIn("REGRESSÃO NO RITMO", mensagens[1])
        self.assertEqual(
            len(repetido["experimento_ritmo_assinaturas_notificadas"]), 2
        )
        self.assertEqual(
            repetido["experimento_ritmo_assinatura_notificada"],
            aprovado["experimento_ritmo_assinatura_notificada"],
        )

    def test_falha_do_ritmo_mantem_chave_estavel_com_metricas_mutaveis(self):
        primeiro = self._experimento_ritmo("aprovado")
        segundo = self._experimento_ritmo("aprovado")
        segundo["minutos_observados"] = 55
        segundo["experimento"]["ciclos"] = 13
        with patch("watchdog.enviar_alerta", return_value=False) as enviar:
            falhou = atualizar_alerta_experimento_ritmo(
                {"experimento_ritmo_packball": primeiro}, {}
            )
            repetiu = atualizar_alerta_experimento_ritmo(
                {"experimento_ritmo_packball": segundo}, falhou
            )

        self.assertEqual(enviar.call_count, 2)
        primeira_chave = enviar.call_args_list[0].kwargs["chave_evento"]
        segunda_chave = enviar.call_args_list[1].kwargs["chave_evento"]
        self.assertEqual(primeira_chave, segunda_chave)
        self.assertIsNone(
            enviar.call_args_list[1].kwargs["deduplicacao_minutos"]
        )
        self.assertNotEqual(
            enviar.call_args_list[0].args[0],
            enviar.call_args_list[1].args[0],
        )
        self.assertEqual(
            repetiu["experimento_ritmo_assinaturas_notificadas"], []
        )

    def test_regressao_usa_alerta_critico_sem_mensagem_duplicada(self):
        enviar = Mock(return_value=True)
        atual = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "regressao_recomendada"
                ),
                "causas_validacao_notificadas": [
                    "experimento_ritmo_packball_regressao"
                ],
            },
            {},
            enviar=enviar,
        )

        enviar.assert_not_called()
        self.assertIn(
            "regressao_recomendada",
            atual["experimento_ritmo_assinatura_notificada"],
        )

    def test_alerta_critico_de_ritmo_inclui_metricas(self):
        mensagens = []
        estado = {}
        for _ in range(3):
            estado = atualizar_alerta_validacao(
                {
                    "requer_atencao": True,
                    "motivos": ["experimento_ritmo_packball_regressao"],
                    "avisos": [],
                    "experimento_ritmo_packball": self._experimento_ritmo(
                        "regressao_recomendada"
                    ),
                },
                estado,
                enviar=lambda texto: mensagens.append(texto) or True,
            )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("experimento_ritmo_packball_regressao", mensagens[0])
        self.assertNotIn("retenção de fluxo=1.02", mensagens[0])

    def test_rollback_do_ritmo_notifica_uma_vez(self):
        mensagens = []
        atual = atualizar_alerta_experimento_ritmo(
            {
                "experimento_ritmo_packball": self._experimento_ritmo(
                    "rollback_acionado"
                )
            },
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("ROLLBACK DE SEGURANÇA", mensagens[0])
        self.assertIn(
            "rollback_acionado",
            atual["experimento_ritmo_assinatura_notificada"],
        )

    @staticmethod
    def _validacao_experimento_filtro(estado, decisao, enviadas, filtradas):
        evidencia = {
            "estado": estado,
            "decisao": decisao,
            "amostra_enviadas": enviadas,
            "amostra_filtradas": filtradas,
            "amostra_minima_por_coorte": 30,
            "delta_taxa_acerto": 0.08,
            "intervalo_delta_taxa_acerto_95": [-0.01, 0.17],
            "delta_roi": 0.12,
            "intervalo_delta_roi_95": [-0.03, 0.27],
        }
        validacao = {
            "experimento_filtro": {
                "saudavel": True,
                "iniciado_em": "2026-07-23T13:00:23",
            },
            "comparacao_filtro_simulacoes": {
                "regra_fingerprint": "fp-atual",
                "comparacao": {
                    "geral": evidencia
                },
            },
        }
        if estado == "avaliavel":
            validacao["conclusao_filtro_simulacoes"] = {
                "versao": "conclusao-filtro-simulacoes-v1",
                "concluido_em": "2026-07-24T10:00:00",
                "regra_fingerprint": "fp-atual",
                "decisao": decisao,
                "evidencia": evidencia,
            }
        return validacao

    def test_experimento_filtro_nao_notifica_antes_da_amostra_minima(self):
        enviar = Mock(return_value=True)

        atual = atualizar_alerta_experimento_filtro(
            self._validacao_experimento_filtro(
                "amostra_insuficiente", "aguardando_amostra", 37, 23
            ),
            {},
            enviar=enviar,
        )

        enviar.assert_not_called()
        self.assertIsNone(
            atual["experimento_filtro_assinatura_notificada"]
        )

    def test_conclusao_nao_comprovada_do_filtro_notifica_uma_vez(self):
        mensagens = []
        validacao = self._validacao_experimento_filtro(
            "avaliavel", "nao_comprovado", 40, 30
        )

        atual = atualizar_alerta_experimento_filtro(
            validacao,
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alerta_experimento_filtro(
            self._validacao_experimento_filtro(
                "avaliavel", "nao_comprovado", 45, 35
            ),
            atual,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("FILTRO NÃO PROMOVIDO", mensagens[0])
        self.assertIn("conclusão foi congelada", mensagens[0])
        self.assertEqual(
            repetido["experimento_filtro_assinatura_notificada"],
            atual["experimento_filtro_assinatura_notificada"],
        )

    def test_mesmo_experimento_nao_muda_por_vantagem_posterior(self):
        anterior = atualizar_alerta_experimento_filtro(
            self._validacao_experimento_filtro(
                "avaliavel", "nao_comprovado", 40, 30
            ),
            {},
            enviar=lambda _texto: True,
        )
        mensagens = []

        atual = atualizar_alerta_experimento_filtro(
            self._validacao_experimento_filtro(
                "avaliavel", "evidencia_favoravel", 55, 45
            ),
            anterior,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 0)
        self.assertIn(
            "conclusao-filtro-simulacoes-v1",
            atual["experimento_filtro_assinatura_notificada"],
        )

    def test_nova_versao_do_experimento_pode_notificar_nova_conclusao(self):
        anterior = atualizar_alerta_experimento_filtro(
            self._validacao_experimento_filtro(
                "avaliavel", "nao_comprovado", 40, 30
            ),
            {},
            enviar=lambda _texto: True,
        )
        nova = self._validacao_experimento_filtro(
            "avaliavel", "evidencia_favoravel", 55, 45
        )
        nova["conclusao_filtro_simulacoes"].update({
            "versao": "conclusao-filtro-simulacoes-v2",
            "concluido_em": "2026-08-10T10:00:00",
            "regra_fingerprint": "fp-novo",
        })
        mensagens = []

        atual = atualizar_alerta_experimento_filtro(
            nova,
            anterior,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("VANTAGEM COMPROVADA", mensagens[0])
        self.assertIn(
            "conclusao-filtro-simulacoes-v2",
            atual["experimento_filtro_assinatura_notificada"],
        )

    @staticmethod
    def _validacao_filtro_regra_ativa(
        estado="amostra_insuficiente",
        decisao="aguardando_amostra",
        enviadas=29,
        filtradas=29,
        regra="sinais-vteste-gol-ht",
    ):
        return {
            "comparacao_filtros_regras_ativas": [{
                "mercado": "gol_ht",
                "regra_versao": regra,
                "comparacao": {
                    "estado": estado,
                    "decisao": decisao,
                    "amostra_minima_por_coorte": 30,
                    "amostra_enviadas": enviadas,
                    "amostra_filtradas": filtradas,
                },
                "enviadas": {
                    "greens": 18,
                    "reds": 12,
                    "roi": 0.075,
                },
                "filtradas": {
                    "greens": 14,
                    "reds": 16,
                    "roi": -0.042,
                },
            }],
        }

    def test_filtro_ativo_implantacao_baseline_nao_envia_marco_antigo(self):
        enviar = Mock(return_value=True)
        validacao = self._validacao_filtro_regra_ativa(
            "avaliavel", "evidencia_favoravel", 30, 30
        )

        atual = atualizar_alertas_filtros_regras_ativas(
            validacao, {}, enviar=enviar
        )

        enviar.assert_not_called()
        assinatura = atual[
            "filtros_regras_ativas_marcos_notificados"
        ]["gol_ht|sinais-vteste-gol-ht|30"]
        self.assertEqual(
            assinatura,
            "gol_ht|sinais-vteste-gol-ht|30|evidencia_favoravel",
        )

    def test_filtro_ativo_cruzamento_30_30_notifica_uma_vez(self):
        anterior = atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(),
            {},
            enviar=lambda _texto: True,
        )
        mensagens = []

        atual = atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(
                "avaliavel", "nao_comprovado", 30, 30
            ),
            anterior,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(
                "avaliavel", "nao_comprovado", 31, 32
            ),
            atual,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertEqual(
            repetido["filtros_regras_ativas_marcos_notificados"],
            atual["filtros_regras_ativas_marcos_notificados"],
        )

    def test_filtro_ativo_falha_de_envio_tenta_novamente(self):
        anterior = atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(),
            {},
            enviar=lambda _texto: True,
        )
        avaliavel = self._validacao_filtro_regra_ativa(
            "avaliavel", "evidencia_favoravel", 30, 30
        )

        falhou = atualizar_alertas_filtros_regras_ativas(
            avaliavel,
            anterior,
            enviar=lambda _texto: False,
        )
        mensagens = []
        recuperado = atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(
                "avaliavel", "evidencia_favoravel", 30, 30
            ),
            falhou,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(
            falhou["filtros_regras_ativas_marcos_notificados"], {}
        )
        self.assertEqual(len(mensagens), 1)
        self.assertIn(
            "gol_ht|sinais-vteste-gol-ht|30",
            recuperado["filtros_regras_ativas_marcos_notificados"],
        )

    def test_filtro_ativo_mensagem_traz_resultados_roi_e_sem_promocao(self):
        anterior = atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(),
            {},
            enviar=lambda _texto: True,
        )
        mensagens = []

        atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(
                "avaliavel", "evidencia_favoravel", 30, 30
            ),
            anterior,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertIn("18 G / 12 R | ROI +7.5%", mensagens[0])
        self.assertIn("14 G / 16 R | ROI -4.2%", mensagens[0])
        self.assertIn("não promove automaticamente", mensagens[0])

    def test_filtro_ativo_nova_versao_tem_marco_independente(self):
        anterior = atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(
                "avaliavel", "nao_comprovado", 30, 30
            ),
            {},
            enviar=lambda _texto: True,
        )
        nova = self._validacao_filtro_regra_ativa(
            regra="sinais-vteste2-gol-ht"
        )
        nova_baseline = atualizar_alertas_filtros_regras_ativas(
            nova,
            anterior,
            enviar=lambda _texto: True,
        )
        mensagens = []

        atual = atualizar_alertas_filtros_regras_ativas(
            self._validacao_filtro_regra_ativa(
                "avaliavel", "evidencia_favoravel", 30, 30,
                regra="sinais-vteste2-gol-ht",
            ),
            nova_baseline,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertEqual(
            len(atual["filtros_regras_ativas_marcos_notificados"]), 2
        )

    @staticmethod
    def _validacao_hipotese_sombra(estado, amostra=30):
        return {
            "hipoteses_sombra": {
                "avaliacoes": [{
                    "versao_avaliacao": (
                        "avaliacao-hipoteses-sombra-controle-ic95-v2"
                    ),
                    "identificador": "proximo_gol_minuto_56_v6",
                    "mercado": "proximo_gol",
                    "feature": "minuto",
                    "operador": "maior_igual",
                    "limiar": 56,
                    "estado": estado,
                    "selecionada": {
                        "amostra": amostra,
                        "taxa_acerto": 0.6,
                        "roi": 0.08 if estado == "confirmada" else -0.1,
                    },
                    "baseline": {"roi": -0.02},
                    "controle_excluido": {
                        "amostra": 10,
                        "roi": -0.04,
                    },
                    "delta_roi_selecionada_controle": (
                        0.12 if estado == "confirmada" else -0.06
                    ),
                    "intervalo_delta_roi_95": (
                        [0.01, 0.23]
                        if estado == "confirmada" else [-0.2, 0.08]
                    ),
                }],
            },
        }

    def test_hipotese_sombra_nao_notifica_antes_da_amostra(self):
        enviar = Mock(return_value=True)

        atual = atualizar_alerta_hipoteses_sombra(
            self._validacao_hipotese_sombra(
                "aguardando_amostra", amostra=12
            ),
            {},
            enviar=enviar,
        )

        enviar.assert_not_called()
        self.assertEqual(
            atual["hipoteses_sombra_estados_notificados"], {}
        )

    def test_hipotese_sombra_concluida_notifica_uma_vez(self):
        mensagens = []
        validacao = self._validacao_hipotese_sombra("confirmada")

        atual = atualizar_alerta_hipoteses_sombra(
            validacao,
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alerta_hipoteses_sombra(
            self._validacao_hipotese_sombra("confirmada", amostra=35),
            atual,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("10 resultado(s)", mensagens[0])
        self.assertIn("[0.01, 0.23]", mensagens[0])
        self.assertIn("HIPÓTESE SOMBRA CONFIRMADA", mensagens[0])
        self.assertIn(
            "Nenhuma regra foi alterada automaticamente", mensagens[0]
        )
        self.assertEqual(
            repetido["hipoteses_sombra_estados_notificados"][
                "proximo_gol_minuto_56_v6"
            ],
            "confirmada",
        )

    @staticmethod
    def _validacao_exploracao_gols(
        avaliadas,
        versao="gols-validacao-v2",
        julgamento="inconclusiva",
    ):
        return {
            "exploracao_sombra": {
                "validacao_prospectiva_gols": {
                    "gol_ft": {
                        "versao": versao,
                        "avaliadas": avaliadas,
                        "minimo_resultados": 30,
                        "greens": max(avaliadas - 4, 0),
                        "reds": min(avaliadas, 4),
                        "taxa_acerto": 0.6,
                        "roi": 0.05,
                        "intervalo_roi_95": [-0.1, 0.2],
                        "decisao_estatistica": julgamento,
                        "lucro_unidades": 1.5,
                    }
                }
            }
        }

    def test_exploracao_gols_notifica_marcos_sem_repetir(self):
        mensagens = []
        primeiro = atualizar_marcos_exploracao_gols(
            self._validacao_exploracao_gols(10),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_marcos_exploracao_gols(
            self._validacao_exploracao_gols(15),
            primeiro,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        segundo = atualizar_marcos_exploracao_gols(
            self._validacao_exploracao_gols(20),
            repetido,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        final = atualizar_marcos_exploracao_gols(
            self._validacao_exploracao_gols(30),
            segundo,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 3)
        self.assertIn("10/30", mensagens[0])
        self.assertIn("20/30", mensagens[1])
        self.assertIn("janela fixa foi concluída", mensagens[2])
        self.assertIn("permanece bloqueado", mensagens[2])
        self.assertEqual(
            final["exploracao_gols_marcos_notificados"]["gol_ft"],
            {"versao": "gols-validacao-v2", "marco": 30},
        )

    def test_exploracao_gols_titulo_final_reflete_o_julgamento(self):
        cenarios = {
            "favoravel_para_revisao_independente": "FAVORÁVEL",
            "inconclusiva": "EVIDÊNCIA INCONCLUSIVA",
            "evidencia_desfavoravel": "EVIDÊNCIA DESFAVORÁVEL",
            "linhagem_inconsistente": "LINHAGEM INCONSISTENTE",
        }
        for julgamento, titulo_esperado in cenarios.items():
            with self.subTest(julgamento=julgamento):
                mensagens = []
                atualizar_marcos_exploracao_gols(
                    self._validacao_exploracao_gols(
                        30,
                        versao=f"v2-{julgamento}",
                        julgamento=julgamento,
                    ),
                    {},
                    enviar=lambda texto: mensagens.append(texto) or True,
                )
                self.assertIn(titulo_esperado, mensagens[0].splitlines()[0])
                if julgamento != "favoravel_para_revisao_independente":
                    self.assertIn(
                        "permanece bloqueado", mensagens[0]
                    )

    def test_exploracao_gols_so_persiste_marco_apos_envio_confirmado(self):
        falhou = atualizar_marcos_exploracao_gols(
            self._validacao_exploracao_gols(10),
            {},
            enviar=lambda _texto: False,
        )
        recuperou = atualizar_marcos_exploracao_gols(
            self._validacao_exploracao_gols(10),
            falhou,
            enviar=lambda _texto: True,
        )

        self.assertNotIn(
            "gol_ft", falhou["exploracao_gols_marcos_notificados"]
        )
        self.assertEqual(
            recuperou["exploracao_gols_marcos_notificados"]["gol_ft"][
                "marco"
            ],
            10,
        )

    @staticmethod
    def _validacao_conclusao_gol_ht_00_min20(
        decisao="favoravel_para_revisao", faltam=0, pendentes=0,
    ):
        return {
            "progresso_gol_ht_00_min20": {
                "estado": "coletando",
                "decisao": decisao,
                "candidatos": 100 - faltam,
                "validos": 100 - faltam - pendentes,
                "greens": 70,
                "reds": 30,
                "pendentes": pendentes,
                "faltam": faltam,
                "roi": 0.12,
                "intervalo_roi_95": [0.01, 0.23],
                "linhagem_homogenea": True,
                "registrado_em": "2026-08-01T12:00:00",
                "desenvolvimento": {"validos": 70, "roi": 0.1},
                "holdout": {"validos": 30, "roi": 0.16},
            }
        }

    def test_gol_ht_00_min20_notifica_uma_vez_so_apos_fechar(self):
        mensagens = []
        incompleta = atualizar_conclusao_gol_ht_00_min20(
            self._validacao_conclusao_gol_ht_00_min20(faltam=1),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        pendente = atualizar_conclusao_gol_ht_00_min20(
            self._validacao_conclusao_gol_ht_00_min20(pendentes=1),
            incompleta,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        final = atualizar_conclusao_gol_ht_00_min20(
            self._validacao_conclusao_gol_ht_00_min20(),
            pendente,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_conclusao_gol_ht_00_min20(
            self._validacao_conclusao_gol_ht_00_min20(),
            final,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("100/100", mensagens[0])
        self.assertIn("REVISÃO MANUAL", mensagens[0])
        self.assertIn(
            "Nenhum método foi ativado, desativado ou promovido",
            mensagens[0],
        )
        self.assertEqual(
            len(repetido["gol_ht_00_min20_conclusoes_notificadas"]), 1,
        )

    def test_gol_ht_00_min20_falha_de_envio_nao_marca_conclusao(self):
        falhou = atualizar_conclusao_gol_ht_00_min20(
            self._validacao_conclusao_gol_ht_00_min20(),
            {},
            enviar=lambda _texto: False,
        )
        recuperou = atualizar_conclusao_gol_ht_00_min20(
            self._validacao_conclusao_gol_ht_00_min20(),
            falhou,
            enviar=lambda _texto: True,
        )

        self.assertEqual(
            falhou["gol_ht_00_min20_conclusoes_notificadas"], {},
        )
        self.assertEqual(
            len(recuperou["gol_ht_00_min20_conclusoes_notificadas"]), 1,
        )

    @staticmethod
    def _validacao_conclusao_gol_ft_v3(
        julgamento="inconclusiva", fingerprint=None,
        candidatos=75, pendentes=0, resultados_completos=True,
    ):
        return {
            "exploracao_sombra": {
                "validacao_prospectiva_gol_ft_v3": {
                    "versao": "gol-ft-v3-teste",
                    "politica_avaliacao_versao": "politica-v3-teste",
                    "candidatos_coorte": candidatos,
                    "tamanho_coorte_fixa": 75,
                    "avaliadas": 70 if pendentes == 0 else 69,
                    "minimo_resultados_validos": 70,
                    "greens": 50,
                    "reds": 20,
                    "pendentes": pendentes,
                    "invalidos": 5 if pendentes == 0 else 5,
                    "roi": 0.08,
                    "intervalo_roi_95": [0.01, 0.15],
                    "coorte_fechada": candidatos >= 75,
                    "resultados_completos": resultados_completos,
                    "decisao_estatistica": julgamento,
                    "validacao_fingerprint": fingerprint or ("a" * 64),
                }
            }
        }

    def test_gol_ft_v3_notifica_so_apos_coorte_fechada_e_completa(self):
        mensagens = []
        incompleta = atualizar_conclusao_gol_ft_v3(
            self._validacao_conclusao_gol_ft_v3(
                candidatos=74, resultados_completos=False,
            ),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        pendente = atualizar_conclusao_gol_ft_v3(
            self._validacao_conclusao_gol_ft_v3(
                pendentes=1, resultados_completos=False,
            ),
            incompleta,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        final = atualizar_conclusao_gol_ft_v3(
            self._validacao_conclusao_gol_ft_v3(),
            pendente,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_conclusao_gol_ft_v3(
            self._validacao_conclusao_gol_ft_v3(),
            final,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        novo_fingerprint = atualizar_conclusao_gol_ft_v3(
            self._validacao_conclusao_gol_ft_v3(fingerprint="b" * 64),
            repetido,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 2)
        self.assertIn("75/75", mensagens[0])
        self.assertIn("Nenhum sinal oficial foi enviado", mensagens[0])
        self.assertEqual(
            len(final["exploracao_gol_ft_v3_conclusoes_notificadas"]), 1
        )
        self.assertEqual(
            len(novo_fingerprint[
                "exploracao_gol_ft_v3_conclusoes_notificadas"
            ]),
            2,
        )

    def test_gol_ft_v3_titulo_final_e_fiel_a_cada_julgamento(self):
        cenarios = {
            "favoravel_para_revisao_independente": (
                "FAVORÁVEL PARA REVISÃO INDEPENDENTE"
            ),
            "inconclusiva": "EVIDÊNCIA INCONCLUSIVA",
            "evidencia_desfavoravel": "EVIDÊNCIA DESFAVORÁVEL",
            "linhagem_inconsistente": "LINHAGEM INCONSISTENTE",
            "amostra_valida_insuficiente": "AMOSTRA VÁLIDA INSUFICIENTE",
        }
        for julgamento, titulo in cenarios.items():
            with self.subTest(julgamento=julgamento):
                mensagens = []
                atualizar_conclusao_gol_ft_v3(
                    self._validacao_conclusao_gol_ft_v3(
                        julgamento=julgamento,
                        fingerprint=hashlib.sha256(
                            julgamento.encode("utf-8")
                        ).hexdigest(),
                    ),
                    {},
                    enviar=lambda texto: mensagens.append(texto) or True,
                )
                self.assertEqual(len(mensagens), 1)
                self.assertIn(titulo, mensagens[0].splitlines()[0])
                self.assertIn(
                    "nenhuma regra foi promovida automaticamente",
                    mensagens[0],
                )

    def test_gol_ft_v3_falha_de_envio_nao_marca_fingerprint(self):
        falhou = atualizar_conclusao_gol_ft_v3(
            self._validacao_conclusao_gol_ft_v3(),
            {},
            enviar=lambda _texto: False,
        )
        recuperou = atualizar_conclusao_gol_ft_v3(
            self._validacao_conclusao_gol_ft_v3(),
            falhou,
            enviar=lambda _texto: True,
        )

        self.assertEqual(
            falhou["exploracao_gol_ft_v3_conclusoes_notificadas"], {}
        )
        self.assertEqual(
            len(recuperou[
                "exploracao_gol_ft_v3_conclusoes_notificadas"
            ]),
            1,
        )

    def test_historico_api_live_notifica_prontidao_sem_repetir(self):
        mensagens = []
        validacao = {
            "historico_api_live": {
                "taxa_concordancia_snapshots": 0.9,
                "limite_inferior_wilson_snapshots": 0.72,
                "prontidao_revisao": {
                    "estado": "apto_revisao",
                    "snapshots": 30,
                    "minimo_snapshots": 30,
                    "fixtures": 10,
                    "minimo_fixtures": 10,
                },
            }
        }
        primeiro = atualizar_alerta_prontidao_historico_api_live(
            validacao,
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alerta_prontidao_historico_api_live(
            validacao,
            primeiro,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("FONTES TEMPORAIS PRONTAS PARA REVISÃO", mensagens[0])
        self.assertIn("30/30", mensagens[0])
        self.assertIn("não alteram sinais automaticamente", mensagens[0])
        self.assertEqual(
            repetido["historico_api_live_prontidao_notificada"],
            "apto_revisao",
        )

    def test_historico_api_live_reenvia_se_primeiro_envio_falhar(self):
        validacao = {
            "historico_api_live": {
                "taxa_concordancia_snapshots": 0.7,
                "limite_inferior_wilson_snapshots": 0.55,
                "prontidao_revisao": {
                    "estado": "divergencia_fontes",
                    "snapshots": 30,
                    "fixtures": 10,
                },
            }
        }
        falhou = atualizar_alerta_prontidao_historico_api_live(
            validacao, {}, enviar=lambda _texto: False
        )
        self.assertNotIn(
            "historico_api_live_prontidao_notificada", falhou
        )
        mensagens = []
        recuperou = atualizar_alerta_prontidao_historico_api_live(
            validacao,
            falhou,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("DIVERGÊNCIA", mensagens[0])
        self.assertEqual(
            recuperou["historico_api_live_prontidao_notificada"],
            "divergencia_fontes",
        )

    def test_hipotese_sombra_refutada_informa_sem_promover(self):
        mensagens = []

        atual = atualizar_alerta_hipoteses_sombra(
            self._validacao_hipotese_sombra("refutada"),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("HIPÓTESE SOMBRA REFUTADA", mensagens[0])
        self.assertIn("não deve ser promovido", mensagens[0])
        self.assertEqual(
            atual["hipoteses_sombra_estados_notificados"][
                "proximo_gol_minuto_56_v6"
            ],
            "refutada",
        )

    def test_hipotese_sombra_com_avaliacao_antiga_nao_notifica(self):
        validacao = self._validacao_hipotese_sombra("confirmada")
        avaliacao = validacao["hipoteses_sombra"]["avaliacoes"][0]
        avaliacao["versao_avaliacao"] = "avaliacao-legada"
        enviar = Mock(return_value=True)

        atual = atualizar_alerta_hipoteses_sombra(
            validacao, {}, enviar=enviar
        )

        enviar.assert_not_called()
        self.assertEqual(
            atual["hipoteses_sombra_avaliacoes_incompativeis"],
            ["proximo_gol_minuto_56_v6"],
        )
        self.assertEqual(
            atual["hipoteses_sombra_estados_notificados"], {}
        )

    @staticmethod
    def _validacao_pontuacao_contexto(
        estado="aguardando_validacao", validacao=0
    ):
        return {
            "pontuacao_contexto_sombra": {
                "versao": "pontuacao-contexto-sombra-logistica-v1",
                "por_mercado": {
                    "gol_ft": {
                        "integro": True,
                        "avaliacao_versao": (
                            "avaliacao-pontuacao-contexto-janela-fixa-v1"
                        ),
                        "regra_versao": VERSAO_REGRAS,
                        "estado": estado,
                        "treino": 60,
                        "treino_ate_sinal_id": 1000,
                        "validacao": validacao,
                        "amostra_minima_validacao": 30,
                        "auc_contexto": {
                            "auc": 0.71,
                            "limite_inferior_auc_95": 0.54,
                        },
                        "auc_nota_atual": {"auc": 0.62},
                        "brier_contexto": 0.19,
                        "brier_odd": 0.23,
                    },
                },
            },
        }

    @patch.dict(os.environ, {"ALERTAS_ANALISES_SOMBRA_TELEGRAM": "1"})
    def test_challenger_contextual_congelado_notifica_uma_vez(self):
        mensagens = []
        atual = atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(validacao=5),
            atual,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("MODELO CONTEXTUAL CONGELADO", mensagens[0])
        self.assertIn("sinal 1000", mensagens[0])
        self.assertIn("Nenhuma regra ou sinal oficial", mensagens[0])
        self.assertEqual(
            repetido["pontuacao_contexto_marcos_notificados"]["gol_ft"][
                "congelado"
            ],
            "pontuacao-contexto-sombra-logistica-v1|"
            "avaliacao-pontuacao-contexto-janela-fixa-v1|"
            "sinais-v6|1000",
        )

    @patch.dict(os.environ, {"ALERTAS_ANALISES_SOMBRA_TELEGRAM": "1"})
    def test_challenger_contextual_repete_congelamento_apos_falha(self):
        enviar = Mock(side_effect=[False, True])
        primeiro = atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(), {}, enviar=enviar
        )
        segundo = atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(), primeiro, enviar=enviar
        )

        self.assertEqual(enviar.call_count, 2)
        self.assertEqual(
            primeiro["pontuacao_contexto_marcos_notificados"], {}
        )
        self.assertIn(
            "congelado",
            segundo["pontuacao_contexto_marcos_notificados"]["gol_ft"],
        )

    @patch.dict(os.environ, {"ALERTAS_ANALISES_SOMBRA_TELEGRAM": "1"})
    def test_challenger_contextual_conclusao_notifica_sem_promover(self):
        mensagens = []
        congelado = atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        concluido = atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(
                estado="favoravel_para_revisao", validacao=30
            ),
            congelado,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(
                estado="favoravel_para_revisao", validacao=31
            ),
            concluido,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 2)
        self.assertIn("FAVORÁVEL PARA REVISÃO", mensagens[1])
        self.assertIn("Limite inferior AUC95: 0.54", mensagens[1])
        self.assertIn("Nenhuma aplicação automática", mensagens[1])
        self.assertIn(
            "conclusao",
            repetido["pontuacao_contexto_marcos_notificados"]["gol_ft"],
        )

    @patch.dict(os.environ, {"ALERTAS_ANALISES_SOMBRA_TELEGRAM": "1"})
    def test_challenger_contextual_inconclusivo_avisa_sem_promover(self):
        mensagens = []
        congelado = atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        atualizar_alertas_pontuacao_contexto_sombra(
            self._validacao_pontuacao_contexto(
                estado="inconclusiva", validacao=30
            ),
            congelado,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 2)
        self.assertIn("SEM VANTAGEM COMPROVADA", mensagens[1])
        self.assertIn("não deve ser promovido", mensagens[1])
        self.assertIn("Nenhuma aplicação automática", mensagens[1])

    @patch.dict(os.environ, {"ALERTAS_ANALISES_SOMBRA_TELEGRAM": "0"})
    def test_challenger_contextual_silenciado_permanece_no_estado(self):
        enviar = Mock(return_value=True)
        validacao = self._validacao_pontuacao_contexto(
            estado="favoravel_para_revisao", validacao=30
        )

        resultado = atualizar_alertas_pontuacao_contexto_sombra(
            validacao, {}, enviar=enviar
        )

        enviar.assert_not_called()
        self.assertIs(resultado, validacao)
        self.assertEqual(
            resultado["pontuacao_contexto_sombra"]["versao"],
            "pontuacao-contexto-sombra-logistica-v1",
        )

    @staticmethod
    def _validacao_pontuacao_longa(
        estado="aguardando_validacao", validacao=0
    ):
        return {
            "pontuacao_longa_sombra": {
                "versao": "pontuacao-longa-logistica-v2",
                "por_mercado": {
                    "gol_ft": {
                        "integro": True,
                        "avaliacao_versao": (
                            "avaliacao-pontuacao-longa-prospectiva-v2"
                        ),
                        "regra_versao": VERSAO_REGRAS,
                        "estado": estado,
                        "iniciar_apos_sinal_id": 900,
                        "treino": 60,
                        "treino_ate_sinal_id": 1200,
                        "validacao": validacao,
                        "amostra_minima_validacao": 30,
                        "validacao_fingerprint": "validacao-fixa",
                        "auc_longa": {
                            "auc": 0.72,
                            "limite_inferior_auc_95": 0.55,
                        },
                        "auc_nota_atual": {"auc": 0.61},
                        "brier_longa": 0.18,
                        "brier_odd": 0.24,
                    },
                },
            },
        }

    @patch.dict(os.environ, {"ALERTAS_ANALISES_SOMBRA_TELEGRAM": "1"})
    def test_challenger_longo_congelado_notifica_uma_vez(self):
        mensagens = []
        atual = atualizar_alertas_pontuacao_longa_sombra(
            self._validacao_pontuacao_longa(),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alertas_pontuacao_longa_sombra(
            self._validacao_pontuacao_longa(validacao=5),
            atual,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("MODELO TEMPORAL 5/10/15 CONGELADO", mensagens[0])
        self.assertIn("sinal 1200", mensagens[0])
        self.assertIn("Nenhuma regra ou sinal oficial", mensagens[0])
        self.assertIn(
            "congelado",
            repetido["pontuacao_longa_marcos_notificados"]["gol_ft"],
        )

    @patch.dict(os.environ, {"ALERTAS_ANALISES_SOMBRA_TELEGRAM": "1"})
    def test_challenger_longo_repete_congelamento_apos_falha(self):
        enviar = Mock(side_effect=[False, True])
        primeiro = atualizar_alertas_pontuacao_longa_sombra(
            self._validacao_pontuacao_longa(), {}, enviar=enviar
        )
        segundo = atualizar_alertas_pontuacao_longa_sombra(
            self._validacao_pontuacao_longa(), primeiro, enviar=enviar
        )

        self.assertEqual(enviar.call_count, 2)
        self.assertEqual(primeiro["pontuacao_longa_marcos_notificados"], {})
        self.assertIn(
            "congelado",
            segundo["pontuacao_longa_marcos_notificados"]["gol_ft"],
        )

    @patch.dict(os.environ, {"ALERTAS_ANALISES_SOMBRA_TELEGRAM": "1"})
    def test_challenger_longo_conclusao_notifica_sem_promover(self):
        mensagens = []
        congelado = atualizar_alertas_pontuacao_longa_sombra(
            self._validacao_pontuacao_longa(),
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        concluido = atualizar_alertas_pontuacao_longa_sombra(
            self._validacao_pontuacao_longa(
                estado="favoravel_para_revisao", validacao=30
            ),
            congelado,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        atualizar_alertas_pontuacao_longa_sombra(
            self._validacao_pontuacao_longa(
                estado="favoravel_para_revisao", validacao=31
            ),
            concluido,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 2)
        self.assertIn("FAVORÁVEL PARA REVISÃO", mensagens[1])
        self.assertIn("Limite inferior AUC95: 0.55", mensagens[1])
        self.assertIn("Nenhuma aplicação automática", mensagens[1])

    @staticmethod
    def _drift_simulacoes(degradados, decisao_id=100):
        return {
            "estado": "degradado" if degradados else "avaliavel",
            "mercados_degradados": list(degradados),
            "ajuste_automatico": False,
            "mercados": {
                mercado: {
                    "amostra_base": 60,
                    "amostra_recente": 30,
                    "roi_base": 0.1,
                    "roi_recente": -0.2,
                    "delta_roi": -0.3,
                    "intervalo_delta_roi_95": [-0.5, -0.1],
                    "ultima_decisao_id": decisao_id,
                    "ultimo_resultado_em": "2026-07-25T20:00:00",
                }
                for mercado in degradados
            },
        }

    def test_drift_saudavel_inicial_e_silencioso(self):
        enviar = Mock(return_value=True)
        atual = atualizar_alerta_drift_simulacoes(
            {"drift_simulacoes": self._drift_simulacoes([])},
            {},
            enviar=enviar,
        )

        enviar.assert_not_called()
        self.assertEqual(
            atual["drift_simulacoes_mercados_notificados"], []
        )

    def test_drift_degradado_notifica_uma_vez_sem_ajuste_automatico(self):
        mensagens = []
        primeiro = atualizar_alerta_drift_simulacoes(
            {"drift_simulacoes": self._drift_simulacoes(["gol_ft"])},
            {},
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        segundo = atualizar_alerta_drift_simulacoes(
            {"drift_simulacoes": self._drift_simulacoes(["gol_ft"])},
            primeiro,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        terceiro = atualizar_alerta_drift_simulacoes(
            {
                "drift_simulacoes": self._drift_simulacoes(
                    ["gol_ft"], decisao_id=101
                )
            },
            segundo,
            enviar=lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_alerta_drift_simulacoes(
            {
                "drift_simulacoes": self._drift_simulacoes(
                    ["gol_ft"], decisao_id=101
                )
            },
            terceiro,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("DETERIORAÇÃO NAS SIMULAÇÕES", mensagens[0])
        self.assertIn("Nenhuma regra foi alterada automaticamente", mensagens[0])
        self.assertEqual(
            repetido["drift_simulacoes_mercados_notificados"], ["gol_ft"]
        )
        self.assertEqual(
            repetido["drift_simulacoes_confirmacoes"]["gol_ft"]["quantidade"],
            2,
        )

    def test_drift_falha_de_envio_e_retentada(self):
        enviar = Mock(side_effect=[False, True])
        anterior = {
            "drift_simulacoes_confirmacoes": {
                "gol_ft": {
                    "quantidade": 1,
                    "ultima_decisao_id": 100,
                }
            }
        }
        falhou = atualizar_alerta_drift_simulacoes(
            {
                "drift_simulacoes": self._drift_simulacoes(
                    ["gol_ft"], decisao_id=101
                )
            },
            anterior,
            enviar=enviar,
        )
        recuperou = atualizar_alerta_drift_simulacoes(
            {
                "drift_simulacoes": self._drift_simulacoes(
                    ["gol_ft"], decisao_id=101
                )
            },
            falhou,
            enviar=enviar,
        )

        self.assertEqual(enviar.call_count, 2)
        self.assertEqual(
            recuperou["drift_simulacoes_mercados_notificados"], ["gol_ft"]
        )

    def test_drift_recuperado_notifica_e_limpa_estado(self):
        mensagens = []
        anterior = {
            "drift_simulacoes_mercados_notificados": ["gol_ft"]
        }
        atual = atualizar_alerta_drift_simulacoes(
            {"drift_simulacoes": self._drift_simulacoes([])},
            anterior,
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("DESEMPENHO DAS SIMULAÇÕES RECUPERADO", mensagens[0])
        self.assertEqual(
            atual["drift_simulacoes_mercados_notificados"], []
        )

    def test_persistencia_drift_grava_so_resultado_novo(self):
        caminho = Path.cwd() / ".teste_historico_drift_watchdog.db"
        for sufixo in ("", "-wal", "-shm"):
            Path(str(caminho) + sufixo).unlink(missing_ok=True)
        banco = BancoMonitor(caminho)
        try:
            validacao = atualizar_alerta_drift_simulacoes(
                {
                    "regra_versao": "sinais-v4",
                    "drift_simulacoes": {
                        **self._drift_simulacoes(["gol_ft"]),
                        "regra_versao": "sinais-v4",
                    },
                },
                {},
                enviar=lambda _: True,
            )
            primeiro = persistir_historico_drift_simulacoes(
                validacao,
                caminho,
                datetime(2026, 7, 25, 20, 1),
            )
            repetido = persistir_historico_drift_simulacoes(
                validacao,
                caminho,
                datetime(2026, 7, 25, 20, 2),
            )

            self.assertTrue(primeiro["saudavel"])
            self.assertEqual(primeiro["inseridos"], 1)
            self.assertEqual(primeiro["total"], 1)
            self.assertEqual(repetido["inseridos"], 0)
            self.assertEqual(repetido["ignorados"], 1)
            self.assertEqual(repetido["total"], 1)
        finally:
            banco.fechar()
            for sufixo in ("", "-wal", "-shm"):
                Path(str(caminho) + sufixo).unlink(missing_ok=True)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "admin-ht",
            "TELEGRAM_CHAT_ID": "chat-geral-sinal",
            "TELEGRAM_CHAT_ID_GOLS": "chat-gols-sinal",
        },
        clear=False,
    )
    def test_conclusao_gol_ht_00_min20_usa_so_admin_e_deduplica(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":910,"date":1784678400}}'
        )
        with patch("watchdog.urlopen", return_value=resposta) as abrir:
            primeiro = enviar_alerta_conclusao_gol_ht_00_min20(
                "conclusão HT",
                "versao-ht|ancora|favoravel",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 0),
            )
            repetido = enviar_alerta_conclusao_gol_ht_00_min20(
                "texto alterado",
                "versao-ht|ancora|favoravel",
                self.caminho_banco,
                datetime(2026, 7, 21, 12, 0),
            )

        self.assertTrue(primeiro)
        self.assertTrue(repetido)
        abrir.assert_called_once()
        requisicao = abrir.call_args.args[0]
        self.assertIn(b"chat_id=admin-ht", requisicao.data)
        self.assertNotIn(b"chat-geral-sinal", requisicao.data)
        self.assertNotIn(b"chat-gols-sinal", requisicao.data)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "admin-v3",
            "TELEGRAM_CHAT_ID": "chat-geral-sinal",
            "TELEGRAM_CHAT_ID_GOLS": "chat-gols-sinal",
        },
        clear=False,
    )
    def test_conclusao_gol_ft_v3_usa_so_admin_e_deduplica_sem_prazo(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":909,"date":1784678400}}'
        )
        with patch("watchdog.urlopen", return_value=resposta) as abrir:
            primeiro = enviar_alerta_conclusao_gol_ft_v3(
                "conclusão original",
                "versao-v3|fingerprint-coorte",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 0),
            )
            repetido = enviar_alerta_conclusao_gol_ft_v3(
                "texto alterado sem novo evento",
                "versao-v3|fingerprint-coorte",
                self.caminho_banco,
                datetime(2026, 7, 21, 12, 0),
            )

        self.assertTrue(primeiro)
        self.assertTrue(repetido)
        abrir.assert_called_once()
        requisicao = abrir.call_args.args[0]
        self.assertIn(b"chat_id=admin-v3", requisicao.data)
        self.assertNotIn(b"chat-geral-sinal", requisicao.data)
        self.assertNotIn(b"chat-gols-sinal", requisicao.data)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "admin-invalido",
            "TELEGRAM_CHAT_ID": "grupo-valido",
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS": "1",
        },
        clear=False,
    )
    def test_alerta_administrativo_usa_grupo_so_com_opt_in(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":101,"date":1784678400}}'
        )
        with patch(
            "watchdog.urlopen",
            side_effect=[OSError("destino invalido"), resposta],
        ) as abrir:
            enviado = enviar_alerta(
                "teste",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 0),
            )

        self.assertTrue(enviado)
        self.assertEqual(abrir.call_count, 2)
        conexao = sqlite3.connect(self.caminho_banco)
        conexao.row_factory = sqlite3.Row
        try:
            linhas = conexao.execute(
                """
                SELECT destino, status, provedor_mensagem_id, resumo
                FROM notificacoes_operacionais ORDER BY id
                """
            ).fetchall()
            auditoria = auditar_notificacoes_operacionais(
                conexao, datetime(2026, 7, 20, 12, 11)
            )
        finally:
            conexao.close()
        self.assertEqual(
            [tuple(linha) for linha in linhas],
            [
                ("admin-invalido", "erro", None, "teste"),
                ("grupo-valido", "entregue", "101", "teste"),
            ],
        )
        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["entregues_com_prova"], 1)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "token-teste",
            "TELEGRAM_ADMIN_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID": "",
            "TELEGRAM_CHAT_ID_GOLS": "",
        },
        clear=False,
    )
    def test_alerta_com_banco_ausente_nao_cria_sqlite_vazio(self):
        self.caminho_banco.unlink(missing_ok=True)
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":111,"date":1784678400}}'
        )

        with patch("watchdog.urlopen", return_value=resposta):
            enviado = enviar_alerta(
                "banco ausente",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 0),
            )

        self.assertTrue(enviado)
        self.assertFalse(self.caminho_banco.exists())

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "token-teste",
            "TELEGRAM_ADMIN_ID": "admin",
            "TELEGRAM_CHAT_ID": "",
            "TELEGRAM_CHAT_ID_GOLS": "",
        },
        clear=False,
    )
    def test_resumo_operacional_redige_segredo_e_nao_guarda_corpo(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":102,"date":1784678400}}'
        )
        with patch("watchdog.urlopen", return_value=resposta):
            enviado = enviar_alerta(
                "ALERTA token=segredo-falso\ncorpo que nao deve persistir",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 0),
            )

        conexao = sqlite3.connect(self.caminho_banco)
        try:
            resumo = conexao.execute(
                "SELECT resumo FROM notificacoes_operacionais"
            ).fetchone()[0]
        finally:
            conexao.close()

        self.assertTrue(enviado)
        self.assertIn("<redigido>", resumo)
        self.assertNotIn("segredo-falso", resumo)
        self.assertNotIn("corpo que nao deve persistir", resumo)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_ADMIN_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID_GOLS": "grupo-valido",
        },
        clear=False,
    )
    def test_entrega_posterior_recupera_falha_operacional_transitoria(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em,
                        status, tentativas, erro
                    ) VALUES ('falha-antiga', 'grupo-valido',
                              '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'erro', 1,
                              'URLError: conexao recusada')
                    """
                )
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em, entregue_em,
                        status, tentativas, provedor,
                        provedor_mensagem_id, confirmacao_json
                    ) VALUES ('mensagem-posterior', 'grupo-valido',
                              '2026-07-20T12:05:00',
                              '2026-07-20T12:05:00',
                              '2026-07-20T12:05:00', 'entregue', 1,
                              'telegram', '303', ?)
                    """,
                    (
                        json.dumps({
                            "ok": True,
                            "provedor": "telegram",
                            "message_id": 303,
                        }),
                    ),
                )

            auditoria = auditar_notificacoes_operacionais(
                banco.conexao, datetime(2026, 7, 20, 12, 20)
            )
        finally:
            banco.fechar()

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["erros_persistentes"], 0)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_ADMIN_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID_GOLS": "",
            "TELEGRAM_CHAT_ID_ESCANTEIOS": "",
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS": "1",
        },
        clear=False,
    )
    def test_uma_tentativa_operacional_nao_vira_incidente_persistente(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em,
                        status, tentativas, erro
                    ) VALUES ('transitoria', 'grupo-valido',
                              '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'erro', 1,
                              'URLError: conexao recusada')
                    """
                )

            auditoria = auditar_notificacoes_operacionais(
                banco.conexao, datetime(2026, 7, 20, 12, 20)
            )
        finally:
            banco.fechar()

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["erros_persistentes"], 0)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_ADMIN_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID_GOLS": "",
            "TELEGRAM_CHAT_ID_ESCANTEIOS": "",
            "TELEGRAM_ALERTAS_OPERACIONAIS_NOS_GRUPOS": "1",
        },
        clear=False,
    )
    def test_tres_tentativas_operacionais_falhas_sao_persistentes(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em,
                        status, tentativas, erro
                    ) VALUES ('esgotada', 'grupo-valido',
                              '2026-07-20T12:00:00',
                              '2026-07-20T12:10:00', 'erro', 3,
                              'URLError: conexao recusada')
                    """
                )

            auditoria = auditar_notificacoes_operacionais(
                banco.conexao, datetime(2026, 7, 20, 12, 30)
            )
        finally:
            banco.fechar()

        self.assertFalse(auditoria["saudavel"])
        self.assertEqual(auditoria["erros_persistentes"], 1)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "grupo-valido",
            "TELEGRAM_CHAT_ID": "",
            "TELEGRAM_CHAT_ID_GOLS": "",
        },
        clear=False,
    )
    def test_disjuntor_operacional_contem_falhas_e_permite_sonda(self):
        banco = BancoMonitor(self.caminho_banco)
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

        with patch("watchdog.urlopen") as abrir:
            bloqueado = enviar_alerta(
                "alerta durante indisponibilidade",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 3),
            )
        self.assertFalse(bloqueado)
        abrir.assert_not_called()

        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":404,"date":1784678400}}'
        )
        with patch("watchdog.urlopen", return_value=resposta) as abrir:
            recuperado = enviar_alerta(
                "sonda depois da pausa",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 8),
            )
        self.assertTrue(recuperado)
        abrir.assert_called_once()

        banco = BancoMonitor(self.caminho_banco)
        try:
            auditoria = auditar_notificacoes_operacionais(
                banco.conexao, datetime(2026, 7, 20, 12, 9)
            )
        finally:
            banco.fechar()
        self.assertTrue(auditoria["saudavel"])
        self.assertFalse(auditoria["disjuntor_pausado"])

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_ADMIN_ID": "grupo-atual",
            "TELEGRAM_CHAT_ID": "grupo-atual",
            "TELEGRAM_CHAT_ID_GOLS": "grupo-atual",
        },
        clear=False,
    )
    def test_falha_de_destino_removido_nao_bloqueia_validacao(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em,
                        status, tentativas, erro
                    ) VALUES ('destino-antigo', 'destino-removido',
                              '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'erro', 1,
                              'HTTP 400')
                    """
                )
            auditoria = auditar_notificacoes_operacionais(
                banco.conexao, datetime(2026, 7, 20, 12, 20)
            )
        finally:
            banco.fechar()

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["erros_persistentes"], 0)

    def test_sem_contexto_de_destinos_nao_reativa_falha_historica(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em,
                        status, tentativas, erro
                    ) VALUES ('historica', 'destino-antigo',
                              '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'erro', 1,
                              'HTTP 400')
                    """
                )
            with patch.dict(os.environ, {}, clear=True):
                auditoria = auditar_notificacoes_operacionais(
                    banco.conexao, datetime(2026, 7, 20, 12, 20)
                )
        finally:
            banco.fechar()

        self.assertTrue(auditoria["saudavel"])
        self.assertEqual(auditoria["destinos_configurados"], 0)
        self.assertEqual(auditoria["erros_persistentes"], 0)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "admin",
        },
        clear=False,
    )
    def test_alerta_operacional_entregue_sobrevive_reinicio_sem_duplicar(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()
        resposta = Mock()
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        resposta.read.return_value = (
            b'{"ok":true,"result":{"message_id":202,"date":1784678400}}'
        )
        with patch("watchdog.urlopen", return_value=resposta) as abrir:
            primeiro = enviar_alerta(
                "alerta persistente",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 0),
            )
            segundo = enviar_alerta(
                "alerta persistente",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 3),
            )

        self.assertTrue(primeiro)
        self.assertTrue(segundo)
        self.assertEqual(abrir.call_count, 1)

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ADMIN_ID": "admin",
        },
        clear=False,
    )
    def test_intencao_operacional_incerta_nao_e_reenviada_cegamente(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em,
                        status, tentativas
                    ) VALUES (?, 'destino-fallback', '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'enviando', 1)
                    """,
                    (
                        hashlib.sha256(b"alerta incerto").hexdigest(),
                    ),
                )
            auditoria = auditar_notificacoes_operacionais(
                banco.conexao, datetime(2026, 7, 20, 12, 3)
            )
        finally:
            banco.fechar()
        with patch("watchdog.urlopen") as abrir:
            enviado = enviar_alerta(
                "alerta incerto",
                self.caminho_banco,
                datetime(2026, 7, 20, 12, 3),
            )

        self.assertFalse(enviado)
        abrir.assert_not_called()
        self.assertTrue(auditoria["saudavel"])
        self.assertTrue(auditoria["requer_atencao"])
        self.assertEqual(auditoria["incertas"], 1)

    def test_reconcilia_intencao_antiga_superada_por_sucesso_posterior(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            confirmacao = json.dumps({
                "ok": True,
                "provedor": "telegram",
                "message_id": 303,
            })
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em,
                        status, tentativas
                    ) VALUES ('antiga', 'admin', '2026-07-20T12:00:00',
                              '2026-07-20T12:00:00', 'enviando', 1)
                    """
                )
                banco.conexao.execute(
                    """
                    INSERT INTO notificacoes_operacionais (
                        chave, destino, criado_em, tentado_em, entregue_em,
                        status, tentativas, provedor,
                        provedor_mensagem_id, confirmacao_json
                    ) VALUES ('posterior', 'admin',
                              '2026-07-20T12:03:00',
                              '2026-07-20T12:03:00',
                              '2026-07-20T12:03:00', 'entregue', 1,
                              'telegram', '303', ?)
                    """,
                    (confirmacao,),
                )

            reconciliacao = reconciliar_notificacoes_operacionais(
                banco.conexao, datetime(2026, 7, 20, 12, 5)
            )
            auditoria = auditar_notificacoes_operacionais(
                banco.conexao, datetime(2026, 7, 20, 12, 5)
            )
            antiga = banco.conexao.execute(
                """
                SELECT status, erro FROM notificacoes_operacionais
                WHERE chave='antiga'
                """
            ).fetchone()
        finally:
            banco.fechar()

        self.assertEqual(reconciliacao["reconciliadas"], 1)
        self.assertEqual(tuple(antiga), (
            "incerto",
            "confirmacao_telegram_ausente_apos_interrupcao",
        ))
        self.assertEqual(auditoria["incertas"], 0)
        self.assertEqual(auditoria["incertas_superadas"], 1)
        self.assertFalse(auditoria["requer_atencao"])

    def test_expira_aviso_aguardar_odd_incerto_apos_partida_finalizada(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-08-31T13:24:20",
                "url": "https://packball.com/match/odd-expirada/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-1", "status": "52 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 1.5, "odd": 1.22,
                "regra_versao": "sinais-v6", "status": "rejeitado",
            }], "2026-08-31T13:24:20")[0]
            banco.registrar_entrega_alerta(
                sinal,
                "chat:aguardar_odd",
                "incerto",
                erro="The read operation timed out",
                instante="2026-08-31T13:25:46",
            )
            banco.salvar_registro({
                "coletado_em": "2026-08-31T14:06:17",
                "url": "https://packball.com/match/odd-expirada/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-1", "status": "Finalizado",
            })

            reconciliacao = reconciliar_acompanhamentos_odd_expirados(
                banco.conexao
            )
            entrega = banco.conexao.execute(
                """
                SELECT status, erro FROM entregas_alertas
                WHERE sinal_id=? AND canal='chat:aguardar_odd'
                """,
                (sinal,),
            ).fetchone()
        finally:
            banco.fechar()

        self.assertEqual(reconciliacao["expirados"], 1)
        self.assertEqual(reconciliacao["envios_oficiais_alterados"], 0)
        self.assertEqual(entrega["status"], "expirado")
        self.assertIn(
            "entrega_ambigua_expirada_apos_partida_finalizada",
            entrega["erro"],
        )

    def test_nao_expira_aguardar_odd_ao_vivo_nem_envio_oficial(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-08-31T13:24:20",
                "url": "https://packball.com/match/odd-ativa/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-1", "status": "52 '",
            })
            acompanhamento, oficial = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 1.5, "odd": 1.22,
                "regra_versao": "sinais-v6", "status": "rejeitado",
            }, {
                "mercado": "gol_ft", "linha": 1.5, "odd": 1.44,
                "regra_versao": "sinais-v6", "status": "aprovado",
            }], "2026-08-31T13:24:20")
            banco.registrar_entrega_alerta(
                acompanhamento, "chat:aguardar_odd", "incerto",
                instante="2026-08-31T13:25:46",
            )
            banco.registrar_entrega_alerta(
                oficial, "chat", "incerto",
                instante="2026-08-31T13:25:46",
            )
            banco.salvar_registro({
                "coletado_em": "2026-08-31T14:06:17",
                "url": "https://packball.com/match/odd-ativa/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-1", "status": "70 '",
            })

            ao_vivo = reconciliar_acompanhamentos_odd_expirados(
                banco.conexao
            )
            banco.salvar_registro({
                "coletado_em": "2026-08-31T14:30:00",
                "url": "https://packball.com/match/odd-ativa/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-1", "status": "Finalizado",
            })
            finalizado = reconciliar_acompanhamentos_odd_expirados(
                banco.conexao
            )
            entregas = {
                linha["canal"]: linha["status"]
                for linha in banco.conexao.execute(
                    "SELECT canal, status FROM entregas_alertas"
                ).fetchall()
            }
        finally:
            banco.fechar()

        self.assertEqual(ao_vivo["expirados"], 0)
        self.assertEqual(finalizado["expirados"], 1)
        self.assertEqual(entregas["chat:aguardar_odd"], "expirado")
        self.assertEqual(entregas["chat"], "incerto")

    def test_resumo_diario_conta_amostra_independente_e_simulacao(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
            linhagem = registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/resumo/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": VERSAO_REGRAS,
                "regra_fingerprint": linhagem["fingerprint_atual"],
                "status": "aprovado",
            }], "2026-07-20T12:00:00")[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, fonte_resultado
                    ) VALUES (?, '2026-07-20T13:00:00', 'green', 0.8,
                              'packball')
                    """,
                    (sinal,),
                )
                banco.conexao.execute(
                    """
                    INSERT INTO entregas_alertas (
                        sinal_id, canal, tentado_em, entregue_em,
                        status, tentativas
                    ) VALUES (?, 'teste:teste', '2026-07-20T12:00:01',
                              '2026-07-20T12:00:01', 'entregue', 1)
                    """,
                    (sinal,),
                )
        finally:
            banco.fechar()

        resumo = resumir_operacao_diaria(
            self.caminho_banco, datetime(2026, 7, 20, 18, 0)
        )

        self.assertTrue(resumo["saudavel"], resumo)
        self.assertEqual(resumo["aprovados_novos"], 1)
        self.assertEqual(resumo["resultados"]["greens"], 1)
        self.assertEqual(resumo["resultados"]["roi"], 0.8)
        self.assertEqual(resumo["pendentes"], 0)
        self.assertEqual(resumo["pendentes_por_mercado"], {})
        self.assertEqual(resumo["simulacoes"], 1)
        self.assertEqual(resumo["alertas_oficiais"], 0)
        self.assertEqual(
            resumo["regra_fingerprint"], linhagem["fingerprint_atual"]
        )
        self.assertFalse(resumo["risco_oficial"]["bloqueado"])
        self.assertEqual(
            resumo["risco_oficial"]["reds_consecutivos_24h"], 0
        )

    def test_resumo_diario_conta_so_resultados_do_grupo_destino(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            linhagem = registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
            sinais = []
            for indice, (resultado, canal) in enumerate((
                ("green", "gols:teste"),
                ("red", "cantos:teste"),
            )):
                horario = f"2026-07-20T12:0{indice}:00"
                snapshot = banco.salvar_registro({
                    "coletado_em": horario,
                    "url": (
                        "https://packball.com/match/"
                        f"resumo-destino-{indice}/live"
                    ),
                    "mandante": f"Casa {indice}",
                    "visitante": f"Fora {indice}",
                    "placar": "0-0",
                    "status": "60 '",
                })
                sinal = banco.salvar_candidatos(snapshot, [{
                    "mercado": "gol_ft",
                    "linha": 0.5,
                    "odd": 1.8,
                    "pontuacao_tecnica": 80,
                    "regra_versao": VERSAO_REGRAS,
                    "regra_fingerprint": linhagem["fingerprint_atual"],
                    "status": "aprovado",
                }], horario)[0]
                sinais.append((sinal, resultado, canal))
            with banco.conexao:
                for sinal, resultado, canal in sinais:
                    retorno = 0.8 if resultado == "green" else -1.0
                    banco.conexao.execute(
                        """
                        INSERT INTO resultados_sinais (
                            sinal_id, encerrado_em, resultado,
                            retorno_unidades, fonte_resultado
                        ) VALUES (?, '2026-07-20T13:00:00', ?, ?,
                                  'packball')
                        """,
                        (sinal, resultado, retorno),
                    )
                    banco.conexao.execute(
                        """
                        INSERT INTO entregas_alertas (
                            sinal_id, canal, tentado_em, entregue_em,
                            status, tentativas
                        ) VALUES (?, ?, '2026-07-20T12:05:00',
                                  '2026-07-20T12:05:00', 'entregue', 1)
                        """,
                        (sinal, canal),
                    )
        finally:
            banco.fechar()

        resumo = resumir_operacao_diaria(
            self.caminho_banco,
            datetime(2026, 7, 20, 18, 0),
            destinos_resultado=("gols",),
        )

        self.assertTrue(resumo["saudavel"], resumo)
        self.assertEqual(resumo["resultados"]["total"], 1)
        self.assertEqual(resumo["resultados"]["greens"], 1)
        self.assertEqual(resumo["resultados"]["reds"], 0)
        self.assertEqual(resumo["simulacoes"], 1)

    def test_resumo_diario_nao_mistura_experimento_sombra_no_grupo(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            linhagem = registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
            registrar_ou_validar_definicao_exploracao_gol_ft_v3(
                banco.conexao,
                datetime(2026, 7, 20, 11, 0),
            )
            registrar_ou_validar_politica_avaliacao_gol_ft_v3(
                banco.conexao,
                datetime(2026, 7, 20, 11, 0),
            )
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/sombra-resumo/live",
                "mandante": "Sombra A", "visitante": "Sombra B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": VERSAO_REGRAS,
                "regra_fingerprint": linhagem["fingerprint_atual"],
                "status": "simulacao",
                "features": {
                    "exploracao_sombra": {
                        "versao": VERSAO_EXPLORACAO_GOL_FT_V3,
                    },
                },
            }], "2026-07-20T12:00:00")[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO entregas_alertas (
                        sinal_id, canal, tentado_em, entregue_em,
                        status, tentativas
                    ) VALUES (?, 'teste:teste', '2026-07-20T12:00:01',
                              '2026-07-20T12:00:01', 'entregue', 1)
                    """,
                    (sinal,),
                )
        finally:
            banco.fechar()

        resumo = resumir_operacao_diaria(
            self.caminho_banco, datetime(2026, 7, 20, 18, 0)
        )

        self.assertTrue(resumo["saudavel"], resumo)
        self.assertEqual(resumo["aprovados_novos"], 0)
        self.assertEqual(resumo["pendentes"], 0)
        self.assertEqual(resumo["resultados"]["total"], 0)
        self.assertEqual(resumo["simulacoes"], 0)

    def test_resumo_diario_nao_conta_aprovado_sem_entrega_confirmada(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            linhagem = registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/nao-entregue/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": VERSAO_REGRAS,
                "regra_fingerprint": linhagem["fingerprint_atual"],
                "status": "aprovado",
            }], "2026-07-20T12:00:00")[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, fonte_resultado
                    ) VALUES (?, '2026-07-20T13:00:00', 'green', 0.8,
                              'packball')
                    """,
                    (sinal,),
                )
        finally:
            banco.fechar()

        resumo = resumir_operacao_diaria(
            self.caminho_banco, datetime(2026, 7, 20, 18, 0)
        )

        self.assertTrue(resumo["saudavel"], resumo)
        self.assertEqual(resumo["resultados"]["total"], 0)
        self.assertEqual(resumo["resultados"]["greens"], 0)
        self.assertEqual(resumo["resultados_por_mercado"], {})

    def test_resumo_diario_conta_entrada_sombra_entregue_uma_vez(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            linhagem = registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/sombra-entregue/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": VERSAO_REGRAS,
                "regra_fingerprint": linhagem["fingerprint_atual"],
                "status": "simulacao",
                "features": {
                    "exploracao_sombra": {"versao": "teste-sombra-v1"},
                },
            }], "2026-07-20T12:00:00")[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, fonte_resultado
                    ) VALUES (?, '2026-07-20T13:00:00', 'green', 0.8,
                              'packball')
                    """,
                    (sinal,),
                )
                banco.conexao.executemany(
                    """
                    INSERT INTO entregas_alertas (
                        sinal_id, canal, tentado_em, entregue_em,
                        status, tentativas
                    ) VALUES (?, ?, '2026-07-20T12:00:01',
                              '2026-07-20T12:00:01', 'entregue', 1)
                    """,
                    (
                        (sinal, "grupo:teste"),
                        (sinal, "grupo:teste:resultado"),
                    ),
                )
        finally:
            banco.fechar()

        resumo = resumir_operacao_diaria(
            self.caminho_banco, datetime(2026, 7, 20, 18, 0)
        )

        self.assertTrue(resumo["saudavel"], resumo)
        self.assertEqual(resumo["resultados"]["total"], 1)
        self.assertEqual(resumo["resultados"]["greens"], 1)
        self.assertEqual(resumo["resultados"]["reds"], 0)

    def test_resumo_diario_exclui_resultado_legado_sem_fingerprint(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/resumo-legado/live",
                "mandante": "Legado A", "visitante": "Legado B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "gol_ft", "linha": 0.5, "odd": 1.8,
                "pontuacao_tecnica": 80,
                "regra_versao": VERSAO_REGRAS,
                "status": "aprovado",
            }], "2026-07-20T12:00:00")[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, fonte_resultado
                    ) VALUES (?, '2026-07-20T13:00:00', 'red', -1.0,
                              'packball')
                    """,
                    (sinal,),
                )
            registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
        finally:
            banco.fechar()

        resumo = resumir_operacao_diaria(
            self.caminho_banco, datetime(2026, 7, 20, 18, 0)
        )

        self.assertTrue(resumo["saudavel"])
        self.assertEqual(resumo["aprovados_novos"], 0)
        self.assertEqual(resumo["resultados"]["total"], 0)
        self.assertEqual(resumo["resultados_por_mercado"], {})

    def test_resumo_diario_inclui_excecao_de_versao_por_mercado(self):
        banco = BancoMonitor(self.caminho_banco)
        try:
            registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_REGRAS,
                VERSAO_FEATURES,
            )
            linhagem = registrar_ou_validar_linhagem_regra(
                banco.conexao,
                Path.cwd(),
                VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
                VERSAO_FEATURES,
            )
            snapshot = banco.salvar_registro({
                "coletado_em": "2026-07-20T12:00:00",
                "url": "https://packball.com/match/asiatico/live",
                "mandante": "A", "visitante": "B",
                "placar": "0-0", "status": "60 '",
            })
            sinal = banco.salvar_candidatos(snapshot, [{
                "mercado": "escanteios_ft_asiatico",
                "linha": 8.5,
                "odd": 1.8,
                "pontuacao_tecnica": 85,
                "regra_versao": VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
                "regra_fingerprint": linhagem["fingerprint_atual"],
                "status": "aprovado",
            }], "2026-07-20T12:00:00")[0]
            with banco.conexao:
                banco.conexao.execute(
                    """
                    INSERT INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, fonte_resultado
                    ) VALUES (?, '2026-07-20T13:00:00', 'green', 0.8,
                              'packball')
                    """,
                    (sinal,),
                )
                banco.conexao.execute(
                    """
                    INSERT INTO entregas_alertas (
                        sinal_id, canal, tentado_em, entregue_em,
                        status, tentativas
                    ) VALUES (?, 'teste:teste', '2026-07-20T12:00:01',
                              '2026-07-20T12:00:01', 'entregue', 1)
                    """,
                    (sinal,),
                )
        finally:
            banco.fechar()

        resumo = resumir_operacao_diaria(
            self.caminho_banco, datetime(2026, 7, 20, 18, 0)
        )

        self.assertTrue(resumo["saudavel"], resumo)
        self.assertEqual(resumo["aprovados_novos"], 1)
        self.assertEqual(resumo["resultados"]["greens"], 1)
        self.assertEqual(resumo["simulacoes"], 1)
        self.assertEqual(
            resumo["regra_versoes_por_mercado"][
                "escanteios_ft_asiatico"
            ],
            VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
        )

    def test_resumo_diario_falha_fechado_sem_linhagem_registrada(self):
        banco = BancoMonitor(self.caminho_banco)
        banco.fechar()

        resumo = resumir_operacao_diaria(
            self.caminho_banco, datetime(2026, 7, 20, 18, 0)
        )

        self.assertFalse(resumo["saudavel"])
        self.assertEqual(resumo["motivo"], "linhagem_regra_indisponivel")

    def test_divisao_resumo_respeita_limite_e_preserva_conteudo(self):
        texto = "CABECALHO\n\n" + "".join(
            f"linha {indice} - " + ("⚽" * 90) + "\n"
            for indice in range(120)
        )

        partes = dividir_resumo_diario_telegram(texto)

        self.assertGreater(len(partes), 1)
        self.assertTrue(all(
            comprimento_texto_telegram(parte) <= 3900
            for parte in partes
        ))
        reconstruido = "".join(
            parte.split("\n\n", 1)[1] for parte in partes
        )
        self.assertEqual(reconstruido, texto)

    def test_resumo_diario_compacto_entrega_unica_e_idempotente(self):
        comparacoes = [{
            "mercado": f"mercado_extenso_{indice:03d}",
            "regra_versao": "regra-ativa",
            "comparacao": {
                "decisao": "aguardando_amostra",
                "amostra_minima_por_coorte": 30,
            },
            "enviadas": {"greens": 1, "reds": 0, "roi": 0.8},
            "filtradas": {"greens": 0, "reds": 1, "roi": -1.0},
        } for indice in range(100)]
        base = {
            "saudavel": True,
            "comparacao_filtros_regras_ativas": comparacoes,
            "resumo_operacao_diaria": {
                "saudavel": True,
                "dia": "2026-07-20",
                "resultados": {},
                "risco_oficial": {},
            },
        }
        tentativas_primeiro_ciclo = []

        def falhar_na_segunda(texto, chave):
            tentativas_primeiro_ciclo.append((chave, texto))
            return not chave.endswith("parte-002")

        parcial = atualizar_resumo_diario(
            dict(base),
            {},
            {"saudavel": True},
            datetime(2026, 7, 20, 18, 0),
            enviar_parte=falhar_na_segunda,
        )
        manifesto_parcial = parcial["resumo_diario_entrega"]

        self.assertEqual(manifesto_parcial["partes_total"], 1)
        self.assertEqual(manifesto_parcial["partes_entregues"], 1)
        self.assertTrue(manifesto_parcial["concluida"])
        self.assertEqual(
            parcial.get("resumo_diario_enviado_em"), "2026-07-20"
        )
        self.assertEqual(
            [item[0] for item in tentativas_primeiro_ciclo],
            [
                "resumo-diario-compacto-v2|2026-07-20|parte-001",
            ],
        )

        tentativas_retry = []
        concluido = atualizar_resumo_diario(
            dict(base),
            parcial,
            {"saudavel": True},
            datetime(2026, 7, 20, 18, 2),
            enviar_parte=lambda texto, chave: (
                tentativas_retry.append((chave, texto)) or True
            ),
        )

        self.assertEqual(tentativas_retry, [])
        self.assertEqual(
            concluido["resumo_diario_enviado_em"], "2026-07-20"
        )
        self.assertTrue(concluido["resumo_diario_entrega"]["concluida"])
        self.assertTrue(all(
            comprimento_texto_telegram(texto) <= 3900
            for _, texto in tentativas_primeiro_ciclo + tentativas_retry
        ))

        chamadas_repetidas = []
        repetido = atualizar_resumo_diario(
            dict(base),
            concluido,
            {"saudavel": True},
            datetime(2026, 7, 20, 19, 0),
            enviar_parte=lambda texto, chave: (
                chamadas_repetidas.append((chave, texto)) or True
            ),
        )
        self.assertEqual(chamadas_repetidas, [])
        self.assertEqual(
            repetido["resumo_diario_enviado_em"], "2026-07-20"
        )

    def test_resumo_diario_respeita_horario_confirmacao_e_idempotencia(self):
        mensagens = []
        validacao = {
            "saudavel": True,
            "regra_versao": VERSAO_REGRAS,
            "amostra_por_mercado": {"gol_ft": 302},
            "estado_calibracoes": {
                "gol_ft": {
                    "ativa": False,
                    "amostra": 100,
                    "motivo": "pontuacao_sem_discriminacao",
                },
            },
            "comparacao_filtros_regras_ativas": [{
                "mercado": "proximo_gol",
                "regra_versao": "regra-ativa",
                "comparacao": {
                    "decisao": "aguardando_amostra",
                    "amostra_minima_por_coorte": 30,
                },
                "enviadas": {
                    "greens": 6, "reds": 2, "roi": 0.2839,
                },
                "filtradas": {
                    "greens": 2, "reds": 5, "roi": -0.4,
                },
            }],
            "contador_api": {
                "consumo_dia": 250, "limite_diario_seguro": 7000,
            },
            "pontuacao_contexto_sombra": {
                "modo": "sombra",
                "aplicacao_automatica": False,
                "por_mercado": {
                    "gol_ft": {
                        "estado": "aguardando_treino",
                        "amostra_total": 1,
                        "amostra_minima_treino": 60,
                        "greens": 0,
                        "reds": 1,
                        "treino": None,
                        "validacao": 0,
                    },
                    "gol_ht": {
                        "estado": "aguardando_treino",
                        "amostra_total": 0,
                        "treino": None,
                        "validacao": 0,
                    },
                    "proximo_gol": {
                        "estado": "aguardando_validacao",
                        "amostra_total": 72,
                        "treino": 60,
                        "amostra_minima_validacao": 30,
                        "validacao": 12,
                    },
                },
            },
            "pontuacao_longa_sombra": {
                "modo": "sombra",
                "aplicacao_automatica": False,
                "por_mercado": {
                    "gol_ft": {
                        "estado": "formando_treino_prospectivo",
                        "treino": 4,
                        "amostra_minima_treino": 60,
                        "validacao": 0,
                    },
                    "gol_ht": {
                        "estado": "formando_treino_prospectivo",
                        "treino": 0,
                        "validacao": 0,
                    },
                },
            },
            "exploracao_sombra": {
                "validacao_prospectiva_gols": {
                    "gol_ft": {
                        "avaliadas": 6,
                        "minimo_resultados": 30,
                        "greens": 5,
                        "reds": 1,
                        "roi": 0.4383,
                        "estado": "aguardando_amostra_futura",
                    },
                    "gol_ht": {
                        "avaliadas": 6,
                        "minimo_resultados": 30,
                        "greens": 4,
                        "reds": 2,
                        "roi": 0.1483,
                        "estado": "aguardando_amostra_futura",
                    },
                },
                "validacao_prospectiva_gol_ft_v3": {
                    "candidatos_coorte": 1,
                    "tamanho_coorte_fixa": 75,
                    "avaliadas": 1,
                    "minimo_resultados_validos": 70,
                    "greens": 1,
                    "reds": 0,
                    "pendentes": 0,
                    "invalidos": 0,
                    "roi": 0.55,
                    "estado": "aguardando_coorte_futura",
                },
                "comparacao_gol_ft_v2_controle_v3": {
                    "iniciado_em": "2026-07-20T12:00:00",
                    "v2_controle": {
                        "avaliadas": 2,
                        "greens": 2,
                        "reds": 0,
                        "roi": 0.6,
                    },
                    "v3": {
                        "avaliadas": 2,
                        "greens": 1,
                        "reds": 1,
                        "roi": -0.1,
                    },
                },
                "cobertura_temporal_validacao_gols": {
                    "gol_ft": {
                        "total": 7,
                        "com_evolucao_api": 1,
                        "com_comparacao_fontes": 1,
                    },
                    "gol_ht": {
                        "total": 6,
                        "com_evolucao_api": 0,
                        "com_comparacao_fontes": 0,
                    },
                },
            },
            "historico_api_live": {
                "saudavel": True,
                "snapshots": 59,
                "fixtures": 10,
                "janelas_disponiveis": {"5": 9, "10": 9, "15": 6},
                "comparacoes_packball_api": 2,
                "taxa_concordancia_packball_api": 1.0,
                "prontidao_revisao": {
                    "estado": "aguardando_amostra",
                    "snapshots": 1,
                    "minimo_snapshots": 30,
                    "fixtures": 1,
                    "minimo_fixtures": 10,
                },
                "aplicacao_sinais": False,
            },
            "resumo_operacao_diaria": {
                "saudavel": True, "dia": "2026-07-20",
                "regra_versao": VERSAO_REGRAS,
                "regra_versoes_por_mercado": {
                    "gol_ft": VERSAO_REGRAS,
                    "gol_ht": "sinais-v8b-gol-ht-max28",
                },
                "aprovados_novos": 2, "pendentes": 1,
                "pendentes_por_mercado": {"gol_ft": 2},
                "alertas_oficiais": 0, "simulacoes": 2,
                "resultados": {
                    "total": 2, "greens": 1, "reds": 1, "roi": -0.1,
                },
                "resultados_por_mercado": {
                    "gol_ft": {"greens": 1, "reds": 1},
                },
                "risco_oficial": {
                    "bloqueado": False,
                    "reds_consecutivos_24h": 0,
                    "limite_reds_consecutivos": 3,
                    "perda_realizada_hoje": 0.0,
                    "limite_perda_diaria": 3.0,
                },
            },
        }
        cedo = atualizar_resumo_diario(
            dict(validacao), {}, {"saudavel": True},
            datetime(2026, 7, 20, 17, 59),
            lambda texto: mensagens.append(texto) or True,
        )
        falhou = atualizar_resumo_diario(
            dict(validacao), cedo, {"saudavel": True},
            datetime(2026, 7, 20, 18, 0), lambda _: False,
        )
        enviado = atualizar_resumo_diario(
            dict(validacao), falhou, {"saudavel": True},
            datetime(2026, 7, 20, 18, 1),
            lambda texto: mensagens.append(texto) or True,
        )
        repetido = atualizar_resumo_diario(
            dict(validacao), enviado, {"saudavel": True},
            datetime(2026, 7, 20, 19, 0),
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertIsNone(cedo.get("resumo_diario_enviado_em"))
        self.assertIsNone(falhou.get("resumo_diario_enviado_em"))
        self.assertEqual(enviado["resumo_diario_enviado_em"], "2026-07-20")
        self.assertEqual(repetido["resumo_diario_enviado_em"], "2026-07-20")
        self.assertEqual(len(mensagens), 1)
        self.assertIn("RELATÓRIO PARCIAL ROBÔ - 20/07", mensagens[0])
        self.assertIn("☺️ 1 GREENS", mensagens[0])
        self.assertIn("✖️ 1 REDS", mensagens[0])
        self.assertIn("Assertividade: 50,00%", mensagens[0])
        self.assertIn("I.A ligada 24h", mensagens[0])
        self.assertNotIn("Filtro prospectivo", mensagens[0])
        self.assertNotIn("Challenger", mensagens[0])
        self.assertNotIn("ROI", mensagens[0])

    def test_resumo_diario_omite_gol_ft_v3_sem_primeiro_candidato(self):
        mensagens = []
        validacao = {
            "saudavel": True,
            "exploracao_sombra": {
                "validacao_prospectiva_gol_ft_v3": {
                    "candidatos_coorte": 0,
                    "tamanho_coorte_fixa": 75,
                    "avaliadas": 0,
                    "minimo_resultados_validos": 70,
                }
            },
            "resumo_operacao_diaria": {
                "saudavel": True,
                "dia": "2026-07-20",
                "resultados": {},
                "risco_oficial": {},
            },
        }

        atualizar_resumo_diario(
            validacao,
            {},
            {"saudavel": True},
            datetime(2026, 7, 20, 18, 0),
            enviar=lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertNotIn("Confirmação Gol FT V3", mensagens[0])
        self.assertNotIn("Reteste simultâneo Gol FT", mensagens[0])

    def test_circuit_breaker_notifica_bloqueio_e_recuperacao_uma_vez(self):
        mensagens = []
        risco_bloqueado = {
            "bloqueado": True,
            "motivos_bloqueio": ["reds_consecutivos"],
            "reds_consecutivos_24h": 3,
            "limite_reds_consecutivos": 3,
            "perda_realizada_hoje": 2.5,
            "limite_perda_diaria": 3.0,
            "greens_hoje": 1,
            "reds_hoje": 3,
        }
        atual = {
            "resumo_operacao_diaria": {
                "saudavel": True,
                "risco_oficial": risco_bloqueado,
            }
        }
        primeiro = atualizar_alerta_risco_oficial(
            dict(atual), {}, lambda texto: mensagens.append(texto) or True
        )
        segundo = atualizar_alerta_risco_oficial(
            dict(atual), primeiro,
            lambda texto: mensagens.append(texto) or True,
        )
        recuperado = atualizar_alerta_risco_oficial(
            {
                "resumo_operacao_diaria": {
                    "saudavel": True,
                    "risco_oficial": {
                        **risco_bloqueado,
                        "bloqueado": False,
                        "motivos_bloqueio": [],
                        "reds_consecutivos_24h": 0,
                        "perda_realizada_hoje": 0.0,
                    },
                }
            },
            segundo,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertTrue(primeiro["circuit_breaker_oficial_alertado"])
        self.assertTrue(segundo["circuit_breaker_oficial_alertado"])
        self.assertFalse(recuperado["circuit_breaker_oficial_alertado"])
        self.assertEqual(len(mensagens), 2)
        self.assertIn("ATIVADO", mensagens[0])
        self.assertIn("NORMALIZADO", mensagens[1])

    def test_marco_amostral_e_notificado_uma_unica_vez(self):
        mensagens = []
        validacao = {
            "regra_versao": VERSAO_REGRAS,
            "amostra_por_mercado": {"gol_ft": 30},
        }
        primeiro = atualizar_marcos_validacao(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        segundo = atualizar_marcos_validacao(
            dict(validacao), primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(primeiro["marcos_notificados"]["gol_ft"], 30)
        self.assertEqual(primeiro["proximo_marco_por_mercado"]["gol_ft"], 100)
        self.assertEqual(segundo["marcos_notificados"]["gol_ft"], 30)
        self.assertEqual(len(mensagens), 1)
        self.assertIn("pré-validação", mensagens[0])

    def test_marco_nao_e_gravado_quando_telegram_falha(self):
        validacao = {
            "regra_versao": VERSAO_REGRAS,
            "amostra_por_mercado": {"proximo_gol": 100},
        }
        falhou = atualizar_marcos_validacao(
            dict(validacao), {}, lambda _: False
        )
        mensagens = []
        recuperou = atualizar_marcos_validacao(
            dict(validacao), falhou,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertNotIn("proximo_gol", falhou["marcos_notificados"])
        self.assertEqual(
            recuperou["marcos_notificados"]["proximo_gol"], 100
        )
        self.assertEqual(len(mensagens), 1)
        self.assertIn("não aprova o modelo", mensagens[0])

    def test_nova_regra_possui_marcos_independentes(self):
        mensagens = []
        anterior = {
            "regra_versao_marcos": "sinais-v1",
            "marcos_notificados": {"gol_ft": 100},
        }
        atual = atualizar_marcos_validacao(
            {
                "regra_versao": VERSAO_REGRAS,
                "amostra_por_mercado": {"gol_ft": 30},
            },
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(atual["marcos_notificados"]["gol_ft"], 30)
        self.assertEqual(len(mensagens), 1)

    def test_mesma_regra_com_nova_populacao_reinicia_marcos(self):
        mensagens = []
        anterior = {
            "regra_versao_marcos": VERSAO_REGRAS,
            "amostra_oficial_id_marcos": "populacao-v6",
            "marcos_notificados": {"gol_ft": 100},
        }
        atual = atualizar_marcos_validacao(
            {
                "regra_versao": VERSAO_REGRAS,
                "amostra_oficial_id": "populacao-v7",
                "amostra_por_mercado": {"gol_ft": 30},
            },
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(atual["marcos_notificados"]["gol_ft"], 30)
        self.assertEqual(
            atual["amostra_oficial_id_marcos"], "populacao-v7"
        )
        self.assertEqual(len(mensagens), 1)

    def test_nova_politica_preserva_marco_da_mesma_populacao(self):
        mensagens = []
        anterior = {
            "regra_versao_marcos": VERSAO_REGRAS,
            "amostra_oficial_id_marcos": (
                f"{VERSAO_REGRAS}|calibracao-antiga|fingerprint|inicio"
            ),
            "marcos_notificados": {"gol_ft": 30},
        }
        atual = atualizar_marcos_validacao(
            {
                "regra_versao": VERSAO_REGRAS,
                "amostra_oficial_id": (
                    f"{VERSAO_REGRAS}|calibracao-nova|fingerprint|inicio"
                ),
                "amostra_por_mercado": {"gol_ft": 88},
            },
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(atual["marcos_notificados"]["gol_ft"], 30)
        self.assertEqual(mensagens, [])

    def test_marcos_separam_linhagem_de_cada_mercado(self):
        mensagens = []
        anterior = {
            "amostra_populacao_id_por_mercado_marcos": {
                "gol_ft": "sinais-v6|fp-v6|inicio-v6",
                "escanteios_ft_asiatico": "sinais-v7|fp-v7|inicio-v7",
            },
            "marcos_notificados": {
                "gol_ft": 30,
                "escanteios_ft_asiatico": 30,
            },
        }
        atual = atualizar_marcos_validacao(
            {
                "regra_versao": VERSAO_REGRAS,
                "amostra_populacao_id_por_mercado": {
                    "gol_ft": "sinais-v6|fp-v6|inicio-v6",
                    "escanteios_ft_asiatico": (
                        "sinais-v8|fp-v8|inicio-v8"
                    ),
                },
                "amostra_por_mercado": {
                    "gol_ft": 88,
                    "escanteios_ft_asiatico": 30,
                },
            },
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(atual["marcos_notificados"]["gol_ft"], 30)
        self.assertEqual(
            atual["marcos_notificados"]["escanteios_ft_asiatico"], 30
        )
        self.assertEqual(len(mensagens), 1)
        self.assertNotIn("gol_ft", mensagens[0])
        self.assertIn("escanteios_ft_asiatico", mensagens[0])

    def test_linha_asiatica_por_tempo_notifica_uma_unica_vez(self):
        mensagens = []
        validacao = {
            "odds_escanteios_periodos": {
                "1T": {
                    "mapeada": False,
                    "exactly": 10,
                    "linhas_asiaticas": [],
                },
                "2T": {
                    "mapeada": True,
                    "exactly": 5,
                    "linhas_asiaticas": [4.5, 5.0],
                    "fontes": ["api_football"],
                    "ultima_asiatica_em": "2026-07-21T12:00:00",
                },
            }
        }
        primeiro = atualizar_marcos_odds_periodos(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        segundo = atualizar_marcos_odds_periodos(
            dict(validacao), primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertNotIn("1T", primeiro["marcos_odds_periodos"])
        self.assertIn("2T", primeiro["marcos_odds_periodos"])
        self.assertEqual(len(mensagens), 1)
        self.assertIn("Exactly não contam", mensagens[0])
        self.assertIn("fonte API-Football", mensagens[0])
        self.assertNotIn("DETECTADA NO PACKBALL", mensagens[0])
        self.assertEqual(
            segundo["marcos_odds_periodos"]["2T"]["linhas"], [4.5, 5.0]
        )
        self.assertEqual(
            segundo["marcos_odds_periodos"]["2T"]["fontes"],
            ["api_football"],
        )

    def test_marco_de_odds_so_persiste_depois_da_entrega(self):
        validacao = {
            "odds_escanteios_periodos": {
                "1T": {
                    "mapeada": True,
                    "linhas_asiaticas": [3.5],
                    "ultima_asiatica_em": "2026-07-21T12:00:00",
                }
            }
        }
        falhou = atualizar_marcos_odds_periodos(
            dict(validacao), {}, lambda _: False
        )
        mensagens = []
        recuperou = atualizar_marcos_odds_periodos(
            dict(validacao), falhou,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertNotIn("1T", falhou["marcos_odds_periodos"])
        self.assertIn("1T", recuperou["marcos_odds_periodos"])
        self.assertEqual(len(mensagens), 1)

    def test_cota_api_notifica_80_95_e_100_uma_vez(self):
        mensagens = []
        anterior = {}
        for consumo, esperado in ((5600, 80), (6650, 95), (7000, 100)):
            anterior = atualizar_alerta_cota_api(
                {
                    "contador_api": {
                        "saudavel": True,
                        "dia": "2026-07-20",
                        "consumo_dia": consumo,
                        "limite_diario_seguro": 7000,
                    }
                },
                anterior,
                lambda texto: mensagens.append(texto) or True,
            )
            self.assertEqual(
                anterior["limiar_cota_api_notificado"], esperado
            )

        repetido = atualizar_alerta_cota_api(
            {
                "contador_api": {
                    "saudavel": True,
                    "dia": "2026-07-20",
                    "consumo_dia": 7000,
                    "limite_diario_seguro": 7000,
                }
            },
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )
        self.assertEqual(repetido["limiar_cota_api_notificado"], 100)
        self.assertEqual(len(mensagens), 3)
        self.assertIn("bloqueadas até a virada do dia", mensagens[-1])

    def test_aviso_de_cota_falhado_e_tentado_novamente(self):
        validacao = {
            "contador_api": {
                "saudavel": True,
                "dia": "2026-07-20",
                "consumo_dia": 5600,
                "limite_diario_seguro": 7000,
            }
        }
        falhou = atualizar_alerta_cota_api(
            dict(validacao), {}, lambda _: False
        )
        mensagens = []
        recuperou = atualizar_alerta_cota_api(
            dict(validacao), falhou,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(falhou["limiar_cota_api_notificado"], 0)
        self.assertEqual(recuperou["limiar_cota_api_notificado"], 80)
        self.assertEqual(len(mensagens), 1)

    def test_aviso_de_cota_reinicia_na_virada_do_dia(self):
        anterior = {
            "cota_api_dia": "2026-07-20",
            "limiar_cota_api_notificado": 100,
        }
        mensagens = []
        atual = atualizar_alerta_cota_api(
            {
                "contador_api": {
                    "saudavel": True,
                    "dia": "2026-07-21",
                    "consumo_dia": 5600,
                    "limite_diario_seguro": 7000,
                }
            },
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(atual["cota_api_dia"], "2026-07-21")
        self.assertEqual(atual["limiar_cota_api_notificado"], 80)
        self.assertEqual(len(mensagens), 1)

    def test_sessao_packball_avisa_antes_de_expirar_sem_expor_token(self):
        caminho = Path.cwd() / ".teste_packball_session.json"
        agora = datetime(2026, 8, 1, 12, 0)
        expiracao = int((agora + timedelta(hours=24)).timestamp())
        import base64
        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": expiracao}).encode("utf-8")
        ).decode("ascii").rstrip("=")
        token = f"cabecalho.{payload}.assinatura-secreta"
        caminho.write_text(json.dumps({
            "cookies": [],
            "origins": [{
                "origin": "https://packball.com",
                "localStorage": [{"name": "packballBearer", "value": token}],
            }],
        }), encoding="utf-8")
        try:
            sessao = verificar_sessao_packball(caminho, agora=agora)
            mensagens = []
            atual = atualizar_alerta_sessao_packball(
                {"sessao_packball": sessao}, {},
                lambda texto: mensagens.append(texto) or True,
            )
            repetido = atualizar_alerta_sessao_packball(
                {"sessao_packball": sessao}, atual,
                lambda texto: mensagens.append(texto) or True,
            )
        finally:
            caminho.unlink(missing_ok=True)

        self.assertEqual(sessao["estado"], "expira_em_breve")
        self.assertTrue(atual["sessao_packball_alerta_ativo"])
        self.assertTrue(repetido["sessao_packball_alerta_ativo"])
        self.assertEqual(
            atual["sessao_packball_alerta_assinatura"],
            f"{sessao['expira_em']}|expira_em_breve",
        )
        self.assertEqual(len(mensagens), 1)
        self.assertNotIn(token, mensagens[0])

    def test_sessao_local_valida_nao_sobrepoe_rejeicao_real_do_site(self):
        caminho = Path.cwd() / ".teste_packball_session_rejeitada.json"
        acesso = Path.cwd() / ".teste_packball_acesso_rejeitado.json"
        agora = datetime(2026, 8, 30, 23, 0)
        expiracao = int((agora + timedelta(days=3)).timestamp())
        import base64
        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": expiracao}).encode("utf-8")
        ).decode("ascii").rstrip("=")
        token = f"cabecalho.{payload}.assinatura-secreta"
        caminho.write_text(json.dumps({
            "cookies": [],
            "origins": [{
                "origin": "https://packball.com",
                "localStorage": [
                    {"name": "packballBearer", "value": token}
                ],
            }],
        }), encoding="utf-8")
        acesso.write_text(json.dumps({
            "motivo": "falha_login_packball",
            "pausado_ate": "2026-08-31T05:00:00",
        }), encoding="utf-8")
        try:
            sessao = verificar_sessao_packball(
                caminho,
                agora=agora,
                caminho_estado_acesso=acesso,
            )
        finally:
            caminho.unlink(missing_ok=True)
            acesso.unlink(missing_ok=True)

        self.assertFalse(sessao["saudavel"])
        self.assertEqual(sessao["estado"], "login_manual_necessario")
        self.assertEqual(sessao["motivo"], "falha_login_packball")
        self.assertEqual(
            sessao["autoridade_estado"], "resposta_real_packball"
        )
        self.assertTrue(sessao["expira_em"])
        self.assertNotIn(token, json.dumps(sessao))

    def test_login_manual_necessario_alerta_uma_vez_e_confirma_retorno(self):
        sessao_rejeitada = {
            "saudavel": False,
            "estado": "login_manual_necessario",
            "motivo": "falha_login_packball",
            "expira_em": "2026-09-02T22:32:18",
            "requer_renovacao": True,
        }
        mensagens = []
        primeira = atualizar_alerta_sessao_packball(
            {"sessao_packball": sessao_rejeitada},
            {},
            lambda texto: mensagens.append(texto) or True,
        )
        repetida = atualizar_alerta_sessao_packball(
            {"sessao_packball": sessao_rejeitada},
            primeira,
            lambda texto: mensagens.append(texto) or True,
        )
        recuperada = atualizar_alerta_sessao_packball(
            {"sessao_packball": {
                "saudavel": True,
                "estado": "valida",
                "expira_em": "2026-09-03T22:32:18",
                "requer_renovacao": False,
            }},
            repetida,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 2)
        self.assertIn("PRECISA DE LOGIN", mensagens[0])
        self.assertIn("Sinais oficiais estão pausados", mensagens[0])
        self.assertFalse(recuperada["sessao_packball_alerta_ativo"])
        self.assertFalse(recuperada["sessao_packball_alerta_pendente"])

    def test_login_manual_sem_destino_permanece_alerta_pendente(self):
        atual = atualizar_alerta_sessao_packball(
            {"sessao_packball": {
                "saudavel": False,
                "estado": "login_manual_necessario",
                "motivo": "falha_login_packball",
                "expira_em": "2026-09-02T22:32:18",
                "requer_renovacao": True,
            }},
            {},
            lambda _texto: False,
        )

        self.assertFalse(atual["sessao_packball_alerta_ativo"])
        self.assertTrue(atual["sessao_packball_alerta_pendente"])
        self.assertEqual(
            atual["sessao_packball_alerta_pendente_motivo"],
            "entrega_nao_confirmada",
        )

    def test_sessao_packball_confirma_renovacao_uma_vez(self):
        anterior = {
            "sessao_packball_alerta_assinatura": "2026-08-02T12:00:00",
            "sessao_packball_alerta_ativo": True,
        }
        mensagens = []
        atual = atualizar_alerta_sessao_packball(
            {"sessao_packball": {
                "saudavel": True,
                "estado": "valida",
                "expira_em": "2026-08-11T12:00:00",
                "requer_renovacao": False,
            }},
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertFalse(atual["sessao_packball_alerta_ativo"])
        self.assertEqual(len(mensagens), 1)

    def test_sessao_packball_avisa_expiracao_apos_aviso_preventivo(self):
        expira_em = "2026-08-02T12:00:00"
        anterior = {
            # Formato legado e atual do aviso preventivo: somente a data.
            "sessao_packball_alerta_assinatura": expira_em,
            "sessao_packball_alerta_ativo": True,
        }
        mensagens = []
        expirada = atualizar_alerta_sessao_packball(
            {"sessao_packball": {
                "saudavel": False,
                "estado": "expirada",
                "motivo": "sessao_expirada",
                "expira_em": expira_em,
                "requer_renovacao": True,
            }},
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )
        repetida = atualizar_alerta_sessao_packball(
            {"sessao_packball": {
                "saudavel": False,
                "estado": "expirada",
                "motivo": "sessao_expirada",
                "expira_em": expira_em,
                "requer_renovacao": True,
            }},
            expirada,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(
            expirada["sessao_packball_alerta_assinatura"],
            f"{expira_em}|expirada",
        )
        self.assertTrue(repetida["sessao_packball_alerta_ativo"])
        self.assertEqual(len(mensagens), 1)
        self.assertIn("Estado: expirada", mensagens[0])

    def test_sessao_packball_avisa_ao_entrar_na_janela_preventiva(self):
        expira_em = "2026-08-21T20:00:00"
        anterior = {
            # A renovação foi confirmada quando a sessão ainda estava válida.
            "sessao_packball_alerta_assinatura": f"{expira_em}|valida",
            "sessao_packball_alerta_ativo": False,
        }
        mensagens = []
        atual = atualizar_alerta_sessao_packball(
            {"sessao_packball": {
                "saudavel": True,
                "estado": "expira_em_breve",
                "expira_em": expira_em,
                "restante_horas": 47.9,
                "requer_renovacao": True,
            }},
            anterior,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertTrue(atual["sessao_packball_alerta_ativo"])
        self.assertEqual(
            atual["sessao_packball_alerta_assinatura"],
            f"{expira_em}|expira_em_breve",
        )
        self.assertEqual(len(mensagens), 1)

    def test_sessao_packball_migra_aviso_preventivo_sem_repetir(self):
        expira_em = "2026-08-21T20:00:00"
        mensagens = []
        atual = atualizar_alerta_sessao_packball(
            {"sessao_packball": {
                "saudavel": True,
                "estado": "expira_em_breve",
                "expira_em": expira_em,
                "restante_horas": 24.0,
                "requer_renovacao": True,
            }},
            {
                "sessao_packball_alerta_assinatura": expira_em,
                "sessao_packball_alerta_ativo": True,
            },
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(mensagens, [])
        self.assertTrue(atual["sessao_packball_alerta_ativo"])
        self.assertEqual(
            atual["sessao_packball_alerta_assinatura"],
            f"{expira_em}|expira_em_breve",
        )

    def test_v2b_ft_avisa_evidencia_negativa_uma_unica_vez(self):
        mensagens = []
        progresso = {
            "versao": "validacao-gol-ft-v2b-grupo-v1",
            "registrado_em": "2026-08-26T21:01:14",
            "alerta_desfavoravel": True,
            "validos": 20,
            "greens": 6,
            "reds": 14,
            "roi": -0.31,
            "intervalo_roi_95": [-0.52, -0.10],
        }
        primeira = atualizar_alerta_grupo_gol_ft_capacidade_v2(
            {"progresso_grupo_gol_ft_capacidade_v2": progresso},
            {},
            lambda texto: mensagens.append(texto) or True,
        )
        segunda = atualizar_alerta_grupo_gol_ft_capacidade_v2(
            {"progresso_grupo_gol_ft_capacidade_v2": progresso},
            primeira,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("RETORNO AO SOMBRA RECOMENDADO", mensagens[0])
        self.assertIn("ROI: -31.0%", mensagens[0])
        self.assertIn("IC95 do ROI: [-52.0%, -10.0%]", mensagens[0])
        self.assertEqual(
            primeira["grupo_gol_ft_capacidade_v2_alerta_notificado"],
            segunda["grupo_gol_ft_capacidade_v2_alerta_notificado"],
        )

    def test_v2b_ft_nao_marca_alerta_quando_envio_falha(self):
        atual = atualizar_alerta_grupo_gol_ft_capacidade_v2(
            {"progresso_grupo_gol_ft_capacidade_v2": {
                "versao": "validacao-gol-ft-v2b-grupo-v1",
                "registrado_em": "2026-08-26T21:01:14",
                "alerta_desfavoravel": True,
                "validos": 20,
                "greens": 5,
                "reds": 15,
                "roi": -0.4,
                "intervalo_roi_95": [-0.6, -0.2],
            }},
            {},
            lambda _texto: False,
        )

        self.assertIsNone(
            atual["grupo_gol_ft_capacidade_v2_alerta_notificado"]
        )

    def test_v2b_ft_circuit_breaker_pausa_somente_com_evidencia_forte(self):
        caminho = Path.cwd() / ".teste_v2b_ft_breaker.json"
        caminho.unlink(missing_ok=True)
        try:
            inconclusiva = aplicar_circuit_breaker_grupo_gol_ft_capacidade_v2(
                {"saudavel": True, "requer_atencao": False,
                 "progresso_grupo_gol_ft_capacidade_v2": {
                     "rollback_recomendado": False,
                 }},
                caminho,
                datetime(2026, 8, 26, 22, 0),
            )
            negativa = aplicar_circuit_breaker_grupo_gol_ft_capacidade_v2(
                {"saudavel": True, "requer_atencao": False,
                 "progresso_grupo_gol_ft_capacidade_v2": {
                     "versao": "validacao-v2b-grupo-v1",
                     "registrado_em": "2026-08-26T21:01:14",
                     "rollback_recomendado": True,
                     "validos": 20, "greens": 6, "reds": 14,
                     "roi": -0.31,
                     "intervalo_roi_95": [-0.52, -0.10],
                 }},
                caminho,
                datetime(2026, 8, 26, 22, 1),
            )

            self.assertTrue(
                inconclusiva["progresso_grupo_gol_ft_capacidade_v2"]
                ["grupo_ativo"]
            )
            self.assertFalse(
                negativa["progresso_grupo_gol_ft_capacidade_v2"]
                ["grupo_ativo"]
            )
            self.assertEqual(
                negativa["controle_operacional_v2b_ft"]["estado"],
                "sombra_automatico",
            )
            self.assertTrue(caminho.exists())
        finally:
            caminho.unlink(missing_ok=True)

    def test_v2b_ft_alerta_informa_pausa_automatica(self):
        mensagens = []
        validacao = {
            "controle_operacional_v2b_ft": {
                "ativo": False,
                "estado": "sombra_automatico",
            },
            "progresso_grupo_gol_ft_capacidade_v2": {
                "versao": "validacao-gol-ft-v2b-grupo-v1",
                "registrado_em": "2026-08-26T21:01:14",
                "alerta_desfavoravel": True,
                "validos": 20, "greens": 6, "reds": 14,
                "roi": -0.31,
                "intervalo_roi_95": [-0.52, -0.10],
            },
        }
        atualizar_alerta_grupo_gol_ft_capacidade_v2(
            validacao, {}, lambda texto: mensagens.append(texto) or True
        )

        self.assertEqual(len(mensagens), 1)
        self.assertIn("RETORNO AUTOMÁTICO AO SOMBRA", mensagens[0])
        self.assertIn("demais mercados continuam ativos", mensagens[0])

    def test_gols_antecipados_breaker_isola_so_evidencia_forte(self):
        caminho = Path.cwd() / ".teste_gols_antecipados_breaker.json"
        caminho.unlink(missing_ok=True)
        try:
            validacao = {
                "saudavel": True,
                "requer_atencao": False,
                "progresso_gols_antecipados": {
                    "versao": "validacao-v3",
                    "registrado_em": "2026-09-01T00:00:00",
                    "linhagem_sha256": "sha",
                    "por_braco": {
                        "ruim": {
                            "validos": 95,
                            "greens": 30,
                            "reds": 65,
                            "roi": -0.35,
                            "intervalo_roi_95": [-0.50, -0.10],
                            "linhagem_homogenea": True,
                            "decisao_estatistica": "evidencia_desfavoravel",
                        },
                        "incerto": {
                            "validos": 95,
                            "intervalo_roi_95": [-0.20, 0.05],
                            "linhagem_homogenea": True,
                            "decisao_estatistica": "inconclusiva",
                        },
                    },
                },
            }

            resultado = aplicar_circuit_breaker_gols_antecipados(
                validacao, caminho, datetime(2026, 9, 8, 22, 0)
            )

            progresso = resultado["progresso_gols_antecipados"][
                "por_braco"
            ]
            self.assertFalse(progresso["ruim"]["grupo_liberado"])
            self.assertTrue(progresso["incerto"]["grupo_liberado"])
            self.assertEqual(
                ["ruim"],
                resultado["controle_operacional_gols_antecipados"]
                ["suspensos_neste_ciclo"],
            )
        finally:
            caminho.unlink(missing_ok=True)

    def test_alerta_breaker_gols_antecipados_e_unico_por_assinatura(self):
        mensagens = []
        validacao = {
            "controle_operacional_gols_antecipados": {
                "metodos": {
                    "metodo-v1": {
                        "ativo": False,
                        "estado": "sombra_automatico",
                        "assinatura": "validacao|ancora|metodo-v1",
                        "metricas": {
                            "validos": 100,
                            "greens": 30,
                            "reds": 70,
                            "roi": -0.4,
                            "intervalo_roi_95": [-0.55, -0.20],
                        },
                    },
                },
            },
        }

        primeiro = atualizar_alerta_circuit_breaker_gols_antecipados(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        atualizar_alerta_circuit_breaker_gols_antecipados(
            dict(validacao), primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(1, len(mensagens))
        self.assertIn("metodo-v1", mensagens[0])
        self.assertIn("IC95 do ROI: [-55.0%, -20.0%]", mensagens[0])

    def test_breaker_filtro_ht_preciso_isola_somente_essa_entrega(self):
        caminho = Path.cwd() / ".teste_filtro_ht_preciso_breaker.json"
        caminho.unlink(missing_ok=True)
        try:
            validacao = {
                "saudavel": True,
                "requer_atencao": False,
                "progresso_filtro_gol_ht_preciso": {
                    "versao": "validacao-ht-preciso-v1",
                    "registrado_em": "2026-09-09T20:00:00",
                    "definicao_sha256": "sha",
                    "alerta_desfavoravel": True,
                    "resultados_completos": False,
                    "validos": 25,
                    "greens": 3,
                    "reds": 22,
                    "roi": -0.72,
                    "intervalo_roi_95": [-0.90, -0.20],
                },
                "progresso_gols_antecipados": {"preservado": True},
            }

            resultado = aplicar_circuit_breaker_filtro_gol_ht_preciso(
                validacao, caminho, datetime(2026, 9, 9, 20, 30)
            )

            controle = resultado[
                "controle_operacional_filtro_gol_ht_preciso"
            ]
            self.assertFalse(controle["ativo"])
            self.assertEqual(
                "ic95_roi_checkpoint_25_integralmente_negativo",
                controle["motivo"],
            )
            self.assertTrue(
                controle["metricas"]["coleta_sombra_continua"]
            )
            self.assertTrue(
                resultado["progresso_gols_antecipados"]["preservado"]
            )
        finally:
            caminho.unlink(missing_ok=True)

    def test_breaker_filtro_ft_preciso_isola_somente_essa_entrega(self):
        caminho = Path.cwd() / ".teste_filtro_ft_preciso_breaker.json"
        caminho.unlink(missing_ok=True)
        try:
            validacao = {
                "saudavel": True,
                "requer_atencao": False,
                "progresso_filtro_gol_ft_preciso": {
                    "versao": "validacao-ft-preciso-v1",
                    "registrado_em": "2026-09-09T20:00:00",
                    "definicao_sha256": "sha",
                    "alerta_desfavoravel": True,
                    "resultados_completos": False,
                    "validos": 25,
                    "greens": 3,
                    "reds": 22,
                    "roi": -0.72,
                    "intervalo_roi_95": [-0.90, -0.20],
                },
                "progresso_gols_antecipados": {"preservado": True},
            }

            resultado = aplicar_circuit_breaker_filtro_gol_ft_preciso(
                validacao, caminho, datetime(2026, 9, 9, 20, 30)
            )

            controle = resultado[
                "controle_operacional_filtro_gol_ft_preciso"
            ]
            self.assertFalse(controle["ativo"])
            self.assertEqual(
                "ic95_roi_checkpoint_25_integralmente_negativo",
                controle["motivo"],
            )
            self.assertTrue(
                controle["metricas"]["coleta_sombra_continua"]
            )
            self.assertTrue(
                resultado["progresso_gols_antecipados"]["preservado"]
            )
        finally:
            caminho.unlink(missing_ok=True)

    def test_alerta_breaker_filtro_ht_preciso_e_unico(self):
        mensagens = []
        validacao = {
            "controle_operacional_filtro_gol_ht_preciso": {
                "ativo": False,
                "estado": "suspenso_automatico",
                "assinatura": "validacao|ancora|sha",
                "metricas": {
                    "validos": 25,
                    "greens": 3,
                    "reds": 22,
                    "roi": -0.72,
                    "intervalo_roi_95": [-0.90, -0.20],
                },
            },
        }

        primeiro = atualizar_alerta_circuit_breaker_filtro_gol_ht_preciso(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        atualizar_alerta_circuit_breaker_filtro_gol_ht_preciso(
            dict(validacao),
            primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(1, len(mensagens))
        self.assertIn("GOL HT ANTECIPADO PRECISO", mensagens[0])
        self.assertIn("nenhum outro mercado foi alterado", mensagens[0])

    def test_alerta_breaker_filtro_ft_preciso_e_unico(self):
        mensagens = []
        validacao = {
            "controle_operacional_filtro_gol_ft_preciso": {
                "ativo": False,
                "estado": "suspenso_automatico",
                "assinatura": "validacao|ancora|sha",
                "metricas": {
                    "validos": 25,
                    "greens": 3,
                    "reds": 22,
                    "roi": -0.72,
                    "intervalo_roi_95": [-0.90, -0.20],
                },
            },
        }

        primeiro = atualizar_alerta_circuit_breaker_filtro_gol_ft_preciso(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        atualizar_alerta_circuit_breaker_filtro_gol_ft_preciso(
            dict(validacao),
            primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(1, len(mensagens))
        self.assertIn("GOL FT ANTECIPADO PRECISO", mensagens[0])
        self.assertIn("nenhum outro mercado foi alterado", mensagens[0])

    def test_breaker_escanteios_ft_asiatico_isola_somente_essa_entrega(self):
        caminho = Path.cwd() / ".teste_escanteios_ft_asiatico_breaker.json"
        caminho.unlink(missing_ok=True)
        try:
            validacao = {
                "saudavel": True,
                "requer_atencao": False,
                "progresso_escanteios_ft_asiatico": {
                    "versao": "validacao-escanteios-ft-v1",
                    "registrado_em": "2026-09-09T20:00:00",
                    "definicao_sha256": "sha",
                    "alerta_desfavoravel": True,
                    "resultados_completos": False,
                    "validos": 25,
                    "greens": 4,
                    "half_greens": 1,
                    "voids": 2,
                    "half_reds": 1,
                    "reds": 17,
                    "roi": -0.61,
                    "intervalo_roi_95": [-0.82, -0.19],
                },
                "progresso_gols_antecipados": {"preservado": True},
            }

            resultado = aplicar_circuit_breaker_escanteios_ft_asiatico(
                validacao, caminho, datetime(2026, 9, 9, 20, 30)
            )

            controle = resultado[
                "controle_operacional_escanteios_ft_asiatico"
            ]
            self.assertFalse(controle["ativo"])
            self.assertEqual(
                "ic95_roi_checkpoint_25_integralmente_negativo",
                controle["motivo"],
            )
            self.assertTrue(controle["metricas"]["coleta_continua"])
            self.assertTrue(
                resultado["progresso_gols_antecipados"]["preservado"]
            )
        finally:
            caminho.unlink(missing_ok=True)

    def test_alerta_breaker_escanteios_ft_asiatico_e_unico(self):
        mensagens = []
        validacao = {
            "controle_operacional_escanteios_ft_asiatico": {
                "ativo": False,
                "estado": "suspenso_automatico",
                "assinatura": "validacao|ancora|sha",
                "metricas": {
                    "validos": 25,
                    "greens": 4,
                    "half_greens": 1,
                    "voids": 2,
                    "half_reds": 1,
                    "reds": 17,
                    "roi": -0.61,
                    "intervalo_roi_95": [-0.82, -0.19],
                },
            },
        }

        primeiro = atualizar_alerta_circuit_breaker_escanteios_ft_asiatico(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        atualizar_alerta_circuit_breaker_escanteios_ft_asiatico(
            dict(validacao),
            primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(1, len(mensagens))
        self.assertIn("ESCANTEIOS FT ASIATICO", mensagens[0])
        self.assertIn("nenhum outro mercado foi alterado", mensagens[0])

    def test_breaker_proximo_gol_pausa_grupo_e_preserva_coleta(self):
        caminho = Path.cwd() / ".teste_proximo_gol_breaker.json"
        caminho.unlink(missing_ok=True)
        try:
            validacao = {
                "saudavel": True,
                "requer_atencao": False,
                "progresso_proximo_gol_balanceado_sombra": {
                    "versao": "validacao-proximo-gol-v3",
                    "registrado_em": "2026-09-09T13:19:32",
                    "definicao_sha256": "sha",
                    "rollback_recomendado": True,
                    "validos": 20,
                    "greens": 4,
                    "reds": 16,
                    "roi": -0.55,
                    "intervalo_roi_95": [-0.75, -0.20],
                },
            }

            resultado = aplicar_circuit_breaker_proximo_gol_balanceado(
                validacao, caminho, datetime(2026, 9, 9, 14, 30)
            )

            progresso = resultado[
                "progresso_proximo_gol_balanceado_sombra"
            ]
            self.assertFalse(progresso["grupo_liberado"])
            self.assertEqual(
                "sombra_automatico",
                resultado[
                    "controle_operacional_proximo_gol_balanceado"
                ]["estado"],
            )
            self.assertTrue(
                resultado[
                    "controle_operacional_proximo_gol_balanceado"
                ]["metricas"]["coleta_sombra_continua"]
            )
        finally:
            caminho.unlink(missing_ok=True)

    def test_alerta_breaker_proximo_gol_e_unico_por_assinatura(self):
        mensagens = []
        validacao = {
            "controle_operacional_proximo_gol_balanceado": {
                "ativo": False,
                "estado": "sombra_automatico",
                "assinatura": "validacao|ancora|sha",
                "metricas": {
                    "validos": 20,
                    "greens": 4,
                    "reds": 16,
                    "roi": -0.55,
                    "intervalo_roi_95": [-0.75, -0.20],
                },
            },
        }

        primeiro = atualizar_alerta_circuit_breaker_proximo_gol_balanceado(
            dict(validacao), {}, lambda texto: mensagens.append(texto) or True
        )
        atualizar_alerta_circuit_breaker_proximo_gol_balanceado(
            dict(validacao), primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(1, len(mensagens))
        self.assertIn("GRUPO PAUSADO", mensagens[0])
        self.assertIn("coleta silenciosa permanece preservada", mensagens[0])

    def test_breaker_proximo_gol_fecha_grupo_ao_completar_coorte(self):
        caminho = Path.cwd() / ".teste_proximo_gol_coorte_fechada.json"
        caminho.unlink(missing_ok=True)
        try:
            resultado = aplicar_circuit_breaker_proximo_gol_balanceado(
                {
                    "saudavel": True,
                    "requer_atencao": False,
                    "progresso_proximo_gol_balanceado_sombra": {
                        "versao": "validacao-proximo-gol-v3",
                        "registrado_em": "2026-09-09T13:19:32",
                        "definicao_sha256": "sha",
                        "rollback_recomendado": False,
                        "resultados_completos": True,
                        "validos": 40,
                        "greens": 30,
                        "reds": 10,
                        "roi": 0.1,
                        "intervalo_roi_95": [-0.02, 0.22],
                    },
                },
                caminho,
                datetime(2026, 9, 9, 15, 0),
            )

            controle = resultado[
                "controle_operacional_proximo_gol_balanceado"
            ]
            self.assertFalse(controle["ativo"])
            self.assertEqual(
                "coorte_40_concluida_aguardando_revisao_manual",
                controle["motivo"],
            )
        finally:
            caminho.unlink(missing_ok=True)

    def test_breaker_pre_live_suspende_so_entrega_precisa(self):
        caminho = Path.cwd() / ".teste_pre_live_preciso_breaker.json"
        caminho.unlink(missing_ok=True)
        try:
            pre_live = aplicar_circuit_breaker_pre_live_preciso(
                {
                    "saudavel": True,
                    "estado": "ativo",
                    "filtro_preciso": {
                        "versao": "validacao-pre-live-v1",
                        "registrado_em": "2026-09-09T18:00:00",
                        "definicao_sha256": "sha",
                        "alerta_desfavoravel": True,
                        "resultados_completos": False,
                        "validos": 25,
                        "greens": 2,
                        "reds": 23,
                        "roi": -0.85,
                        "intervalo_roi_95": [-1.0, -0.6],
                    },
                },
                caminho,
                datetime(2026, 9, 9, 18, 30),
            )

            controle = pre_live["controle_filtro_preciso"]
            self.assertFalse(controle["ativo"])
            self.assertEqual(
                "ic95_roi_checkpoint_25_integralmente_negativo",
                controle["motivo"],
            )
            self.assertTrue(
                controle["metricas"]["coleta_sombra_continua"]
            )
            self.assertTrue(pre_live["saudavel"])
        finally:
            caminho.unlink(missing_ok=True)

    def test_alerta_breaker_pre_live_e_unico_por_assinatura(self):
        mensagens = []
        estado = {
            "pre_live": {
                "controle_filtro_preciso": {
                    "ativo": False,
                    "estado": "suspenso_automatico",
                    "assinatura": "validacao|ancora|sha",
                    "metricas": {
                        "validos": 25,
                        "greens": 2,
                        "reds": 23,
                        "roi": -0.85,
                        "intervalo_roi_95": [-1.0, -0.6],
                    },
                },
            },
        }
        primeiro = atualizar_alerta_circuit_breaker_pre_live_preciso(
            estado, {}, lambda texto: mensagens.append(texto) or True
        )
        atualizar_alerta_circuit_breaker_pre_live_preciso(
            estado,
            primeiro,
            lambda texto: mensagens.append(texto) or True,
        )

        self.assertEqual(1, len(mensagens))
        self.assertIn("ENTREGA SUSPENSA", mensagens[0])
        self.assertIn("nenhum mercado ao vivo foi alterado", mensagens[0])


if __name__ == "__main__":
    unittest.main()
