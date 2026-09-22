import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ARQUIVOS_RUNTIME = (
    "previsao_gols_provedor.py",
    "filtro_ht_chutes_recentes.py",
    "filtro_gol_ft_antecipado_preciso.py",
    "filtro_gol_ht_antecipado_preciso.py",
    "probabilidade_por_acertos.py",
    "custodia_estimativa_historica.py",
    "probabilidade_individual.py",
    "probabilidade_individual_sem_vig.py",
    "avaliacao_probabilidade_individual.py",
    "resumo_forca_sinais.py",
    "acompanhamento_odd.py",
    "clv_pos_alerta.py",
    "origem_mercado.py",
    "coerencia_curva_odds.py",
    "acompanhamento_metodos_gols.py",
    "avaliacao_acompanhamento_odd.py",
    "custodia_avaliacao.py",
    "exposicao_coleta_prospectiva.py",
    "avaliacao_desajuste_odds.py",
    "avaliacao_quarentena_fallback_ht.py",
    "desajuste_odds.py",
    "trabalhador_acompanhamento_odd.py",
    "agendador_coleta.py", "agendador_thestatsapi.py",
    "prioridade_pre_live_ao_vivo.py",
    "prioridade_ligas_gols.py",
    "api_football.py",
    "backtest.py", "betsapi.py",
    "backup_banco.py", "backup_compactado.py", "banco.py",
    "carteira_operacional.py",
    "calibracao.py", "valor_mercado.py", "coletor_odds.py",
    "avaliacao_edge_escanteios_asiaticos.py",
    "avaliacao_probabilidade_sem_vig.py",
    "avaliacao_portfolio_edge.py",
    "avaliacao_clv_live.py",
    "coletor_packball.py", "conectividade.py", "configuracao.py",
    "dataset_temporal.py",
    "diagnostico_gols_antecipados.py",
    "diagnostico_gols_capacidade_contextual_v2.py",
    "resgate_qualidade_api.py",
    "estatistica.py", "evolucao.py",
    "historico_api_live.py",
    "integracao_thestatsapi_sombra.py",
    "consenso_multifonte_sombra.py",
    "fallback_indicadores_lista.py",
    "fusao_packball_thestats.py",
    "gols_antecipados.py",
    "gols_capacidade_times.py",
    "gols_capacidade_contextual_v2.py",
    "contexto_periodos_10.py",
    "contexto_linhas_gols.py",
    "protecao_conversao_gols.py",
    "validade_historico_gols.py",
    "contrafactual_protecoes.py",
    "tendencias_packball_ligas.py",
    "gol_ht_00_min20.py",
    "gol_ft_tendencia_mais_um.py",
    "gol_2t_pos_ht_red.py",
    "top_criterios_gols.py",
    "linhagem_gols_antecipados.py",
    "validacao_gols_antecipados.py",
    "validacao_gol_ft_antecipado_preciso.py",
    "validacao_quase_candidatos_gol_ft.py",
    "validacao_gol_ht_antecipado_preciso.py",
    "validacao_escanteios_ft_asiatico_prospectiva.py",
    "validacao_escanteios_ft_asiatico_executavel.py",
    "validacao_gols_capacidade_times.py",
    "validacao_gols_capacidade_contextual_v2.py",
    "validacao_gol_ht_00_min20.py",
    "validacao_gol_ft_reforcado_sombra.py",
    "validacao_gol_ht_protegido_sombra.py",
    "validacao_gol_ft_tendencia_mais_um.py",
    "validacao_top_criterios_gols.py",
    "validacao_quase_candidatos_proximo_gol.py",
    "fusao_temporal_api_live.py",
    "challenger_v2_ft.py",
    "exploracao_sombra.py",
    "finalizador_resultados.py",
    "controle_acesso_packball.py", "controle_sistema.py",
    "controle_gols_antecipados.py",
    "controle_filtro_gol_ft_preciso.py",
    "controle_filtro_gol_ht_preciso.py",
    "controle_escanteios_ft_asiatico.py",
    "controle_v2b_ft.py",
    "controle_proximo_gol_balanceado.py",
    "integridade_calibracao.py", "linhagem_regras.py",
    "mercados.py", "monitor_ao_vivo.py", "motor_sinais.py",
    "movimento_odds.py",
    "melhor_preco_sombra.py",
    "validacao_resultado_valor_justo.py",
    "validacao_veto_preco_justo.py",
    "normalizador_odds.py", "observabilidade.py",
    "contexto_pre_jogo.py",
    "packball_login.py",
    "processo_monitor.py", "qualidade_dados.py",
    "politica_escanteios_ft.py", "politica_gol_ht.py",
    "politica_gol_ht_protegido.py",
    "politica_gols_tempo.py",
    "politica_proximo_gol.py",
    "politica_proximo_gol_faixa_global.py",
    "politica_proximo_gol_preciso.py",
    "proximo_gol_balanceado_sombra.py",
    "politica_gol_ft_reforcado.py",
    "pontuacao_contexto_sombra.py",
    "pontuacao_longa_sombra.py", "pontuacao_sombra.py",
    "treino_processo_isolado.py", "treinar_modelo_worker.py",
    "proveniencia_odds.py",
    "roteador_odds_thestatsapi.py",
    "relatorio_simulacoes.py", "retencao.py",
    "servico_monitor.py", "telegram_alertas.py", "versoes_regras.py",
    "avaliacao_prioridade_ligas_gols.py", "prioridade_ligas_gols.py",
    "thestatsapi.py",
    "the_odds_api.py",
    "versoes_operacionais.py", "versoes_challengers.py",
    "versoes_challengers_global.py",
    "versoes_challengers_preciso.py",
    "versoes_proximo_gol_balanceado.py",
    "versoes_gol_ft_reforcado.py",
    "versoes_gol_ht_protegido.py",
)

ARQUIVOS_RUNTIME_WATCHDOG = (
    "previsao_gols_provedor.py",
    "filtro_ht_chutes_recentes.py",
    "filtro_gol_ft_antecipado_preciso.py",
    "filtro_pre_live_preciso.py",
    "filtro_gol_ht_antecipado_preciso.py",
    "probabilidade_por_acertos.py",
    "custodia_estimativa_historica.py",
    "probabilidade_individual.py",
    "probabilidade_individual_sem_vig.py",
    "avaliacao_probabilidade_individual.py",
    "resumo_forca_sinais.py",
    "acompanhamento_odd.py",
    "clv_pos_alerta.py",
    "origem_mercado.py",
    "coerencia_curva_odds.py",
    "avaliacao_acompanhamento_odd.py",
    "custodia_avaliacao.py",
    "exposicao_coleta_prospectiva.py",
    "avaliacao_desajuste_odds.py",
    "avaliacao_quarentena_fallback_ht.py",
    "avaliacao_prioridade_ligas_gols.py",
    "validade_historico_gols.py",
    "desajuste_odds.py",
    "analisar_erros_gol_ft.py", "api_football.py", "backup_banco.py",
    "agendador_pre_live.py", "executar_pre_live.py",
    "coletor_pre_live.py", "repositorio_pre_live.py",
    "seletor_pre_live.py", "telegram_pre_live.py",
    "prioridade_pre_live_ao_vivo.py",
    "backup_compactado.py",
    "backtest.py", "betsapi.py", "betsapi_pre_live.py", "banco.py",
    "carteira_operacional.py",
    "avaliacao_contexto.py", "auditoria_ligas_sombra.py",
    "auditoria_regras_operacionais.py",
    "calibracao.py", "valor_mercado.py", "dataset_temporal.py",
    "avaliacao_edge_escanteios_asiaticos.py",
    "avaliacao_probabilidade_sem_vig.py",
    "avaliacao_portfolio_edge.py",
    "avaliacao_clv_live.py",
    "diagnostico_gols_antecipados.py",
    "diagnostico_gols_capacidade_contextual_v2.py",
    "resgate_qualidade_api.py",
    "diagnostico_sinais_recentes.py",
    "configuracao.py", "controle_acesso_packball.py",
    "controle_sistema.py", "controle_gols_antecipados.py",
    "controle_v2b_ft.py", "controle_proximo_gol_balanceado.py",
    "controle_pre_live_preciso.py",
    "controle_filtro_gol_ft_preciso.py",
    "controle_filtro_gol_ht_preciso.py",
    "controle_escanteios_ft_asiatico.py",
    "estatistica.py",
    "challenger_v2_ft.py",
    "exploracao_sombra.py",
    "integridade_calibracao.py", "integridade_resultados.py",
    "hipoteses_sombra.py",
    "gols_antecipados.py",
    "gols_capacidade_times.py",
    "gols_capacidade_contextual_v2.py",
    "contexto_periodos_10.py",
    "contexto_linhas_gols.py",
    "protecao_conversao_gols.py",
    "contrafactual_protecoes.py",
    "tendencias_packball_ligas.py",
    "gol_ht_00_min20.py",
    "gol_ft_tendencia_mais_um.py",
    "gol_2t_pos_ht_red.py",
    "top_criterios_gols.py",
    "linhagem_gols_antecipados.py",
    "validacao_gols_antecipados.py",
    "validacao_gols_capacidade_times.py",
    "validacao_gols_capacidade_contextual_v2.py",
    "validacao_gol_ht_00_min20.py",
    "validacao_gol_ft_tendencia_mais_um.py",
    "validacao_top_criterios_gols.py",
    "fusao_temporal_api_live.py",
    "historico_api_live.py",
    "contexto_pre_jogo.py",
    "linhagem_regras.py", "mercados.py", "motor_sinais.py",
    "movimento_odds.py", "melhor_preco_sombra.py",
    "validacao_resultado_valor_justo.py",
    "validacao_veto_preco_justo.py",
    "supervisao_melhor_preco_sombra.py",
    "supervisao_referencia_api_football.py", "normalizador_odds.py",
    "observabilidade.py", "packball_login.py", "processo_monitor.py",
    "pontuacao_sombra.py", "pontuacao_contexto_sombra.py",
    "pontuacao_longa_sombra.py",
    "treino_processo_isolado.py", "treinar_modelo_worker.py",
    "proveniencia_odds.py",
    "progresso_calibracao.py", "qualidade_dados.py", "evolucao.py",
    "politica_escanteios_ft.py", "politica_gol_ht.py",
    "politica_gol_ht_protegido.py",
    "politica_gols_tempo.py",
    "politica_proximo_gol.py",
    "politica_proximo_gol_faixa_global.py",
    "politica_proximo_gol_preciso.py",
    "proximo_gol_balanceado_sombra.py",
    "politica_gol_ft_reforcado.py",
    "relatorio_odds_periodos.py", "relatorio_simulacoes.py",
    "retencao.py", "versoes_regras.py", "versoes_operacionais.py",
    "versoes_challengers.py", "versoes_challengers_global.py",
    "versoes_challengers_preciso.py",
    "versoes_proximo_gol_balanceado.py",
    "versoes_gol_ft_reforcado.py",
    "versoes_gol_ht_protegido.py",
    "validacao_gol_ft_reforcado_sombra.py",
    "validacao_gol_ht_protegido_sombra.py",
    "validacao_proximo_gol_balanceado_sombra.py",
    "validacao_quase_candidatos_proximo_gol.py",
    "validacao_pre_live_preciso.py",
    "validacao_gol_ft_antecipado_preciso.py",
    "validacao_quase_candidatos_gol_ft.py",
    "validacao_gol_ht_antecipado_preciso.py",
    "validacao_escanteios_ft_asiatico_prospectiva.py",
    "validacao_escanteios_ft_asiatico_executavel.py",
    "watchdog.py",
)

def hash_codigo_runtime(pasta, arquivos=None):
    pasta = Path(pasta)
    resumo = hashlib.sha256()
    for nome in sorted(arquivos or ARQUIVOS_RUNTIME):
        caminho = pasta / nome
        resumo.update(nome.encode("utf-8"))
        resumo.update(caminho.read_bytes() if caminho.exists() else b"<ausente>")
    return resumo.hexdigest()


def hash_codigo_watchdog(pasta):
    return hash_codigo_runtime(pasta, ARQUIVOS_RUNTIME_WATCHDOG)


def dependencias_runtime_ausentes(pasta, arquivos=None):
    """Encontra imports locais não cobertos pela assinatura declarada."""
    pasta = Path(pasta)
    arquivos = tuple(arquivos or ARQUIVOS_RUNTIME)
    modulos_assinados = {Path(nome).stem for nome in arquivos}
    modulos_locais = {
        caminho.stem
        for caminho in pasta.glob("*.py")
        if not caminho.name.startswith("test_")
    }
    dependencias = set()
    for nome in arquivos:
        caminho = pasta / nome
        if not caminho.exists():
            continue
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            candidatos = []
            if isinstance(no, ast.ImportFrom) and no.module:
                candidatos.append(no.module.split(".")[0])
            elif isinstance(no, ast.Import):
                candidatos.extend(
                    item.name.split(".")[0] for item in no.names
                )
            dependencias.update(
                item for item in candidatos if item in modulos_locais
            )
    return sorted(dependencias - modulos_assinados)


def dependencias_runtime_transitivas(pasta, entradas):
    """Resolve imports locais realmente carregaveis a partir das entradas."""
    pasta = Path(pasta)
    modulos_locais = {
        caminho.stem: caminho.name
        for caminho in pasta.glob("*.py")
        if not caminho.name.startswith("test_")
    }
    pendentes = [Path(item).stem for item in entradas]
    visitados = set()
    while pendentes:
        modulo = pendentes.pop()
        if modulo in visitados or modulo not in modulos_locais:
            continue
        visitados.add(modulo)
        caminho = pasta / modulos_locais[modulo]
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            candidatos = []
            if isinstance(no, ast.ImportFrom) and no.module:
                candidatos.append(no.module.split(".")[0])
            elif isinstance(no, ast.Import):
                candidatos.extend(
                    item.name.split(".")[0] for item in no.names
                )
            pendentes.extend(
                item for item in candidatos
                if item in modulos_locais and item not in visitados
            )
    return tuple(sorted(modulos_locais[item] for item in visitados))


def estado_codigo_runtime(pasta, estado, arquivos=None):
    pasta = Path(pasta)
    arquivos = tuple(arquivos or ARQUIVOS_RUNTIME)
    atual = hash_codigo_runtime(pasta, arquivos)
    carregado = (estado or {}).get("codigo_hash")
    if carregado is not None:
        return "atualizado" if carregado == atual else "reinicio_pendente"
    try:
        inicio = datetime.fromisoformat((estado or {})["atualizado_em"])
    except (KeyError, TypeError, ValueError):
        return "desconhecido"
    modificacoes = [
        datetime.fromtimestamp((pasta / nome).stat().st_mtime)
        for nome in arquivos
        if (pasta / nome).exists()
    ]
    if modificacoes and max(modificacoes) > inicio:
        return "reinicio_pendente"
    return "desconhecido"


class TravaInstancia:
    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self.arquivo = None

    def adquirir(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.caminho.open("a+b")
        self.arquivo.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(
                    self.arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                )
        except (OSError, BlockingIOError):
            self.arquivo.close()
            self.arquivo = None
            return False
        self.arquivo.seek(0)
        if self.arquivo.read(1) == b"":
            self.arquivo.seek(0)
            self.arquivo.write(b"0")
            self.arquivo.flush()
        self.arquivo.seek(0)
        return True

    def liberar(self):
        if self.arquivo is None:
            return
        try:
            self.arquivo.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.arquivo.fileno(), fcntl.LOCK_UN)
        finally:
            self.arquivo.close()
            self.arquivo = None

    def __enter__(self):
        if not self.adquirir():
            raise RuntimeError("Outra instância do monitor já está ativa.")
        return self

    def __exit__(self, *_):
        self.liberar()


def trava_em_uso(caminho):
    """Confirma uma instancia pela trava do SO, sem confiar apenas no PID."""
    trava = TravaInstancia(caminho)
    if not trava.adquirir():
        return True
    trava.liberar()
    return False


def pid_ativo(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        if os.name == "nt":
            return _pid_ativo_windows(pid)
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False


def _pid_ativo_windows(pid):
    import ctypes
    from ctypes import wintypes

    acesso_consulta_limitada = 0x1000
    processo_ativo = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    identificador = kernel32.OpenProcess(
        acesso_consulta_limitada, False, pid
    )
    if not identificador:
        return ctypes.get_last_error() == 5
    try:
        codigo_saida = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(
            identificador, ctypes.byref(codigo_saida)
        ):
            return False
        return codigo_saida.value == processo_ativo
    finally:
        kernel32.CloseHandle(identificador)


def gravar_json_atomico(caminho, dados, tentativas=5):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(
        f".{caminho.name}.{os.getpid()}.{uuid4().hex}.tmp"
    )
    try:
        temporario.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for tentativa in range(max(int(tentativas), 1)):
            try:
                temporario.replace(caminho)
                break
            except PermissionError:
                if tentativa + 1 >= max(int(tentativas), 1):
                    raise
                time.sleep(0.05 * (2 ** tentativa))
    finally:
        temporario.unlink(missing_ok=True)
    return dados


def registrar_estado(caminho, status, pid=None, **dados):
    registro = {
        "pid": int(pid or os.getpid()),
        "status": status,
        "atualizado_em": datetime.now().replace(microsecond=0).isoformat(),
        **dados,
    }
    gravar_json_atomico(caminho, registro)
    return registro


def ler_estado(caminho):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def ambiente_processo_utf8():
    """Garante que nomes internacionais nunca derrubem processos de fundo."""
    ambiente = os.environ.copy()
    ambiente["PYTHONIOENCODING"] = "utf-8:backslashreplace"
    ambiente["PYTHONUTF8"] = "1"
    return ambiente


def iniciar_monitor(pasta, executavel=None, terminal_visivel=None):
    """Serializa lançamentos sem sobrescrever a identidade de um monitor vivo."""
    pasta = Path(pasta)
    with TravaInstancia(pasta / "monitor_lancamento.lock"):
        if trava_em_uso(pasta / "monitor_instancia.lock"):
            estado = ler_estado(pasta / "monitor_processo.json")
            pid = estado.get("pid")
            if pid_ativo(pid):
                return int(pid)
            # A trava é a autoridade sobre existência. Nunca derruba nem
            # substitui o estado de uma instância cuja identidade ainda não
            # foi publicada (por exemplo, durante imports/inicialização).
            raise RuntimeError("monitor_ativo_com_identidade_pendente")
        lancamento = ler_estado(pasta / "monitor_lancamento.json")
        try:
            idade = (
                datetime.now()
                - datetime.fromisoformat(lancamento["atualizado_em"])
            ).total_seconds()
        except (KeyError, TypeError, ValueError):
            idade = None
        if (
            idade is not None and 0 <= idade <= 60
            and pid_ativo(lancamento.get("pid"))
        ):
            return int(lancamento["pid"])
        return _iniciar_monitor_livre(pasta, executavel, terminal_visivel)


def _iniciar_monitor_livre(pasta, executavel=None, terminal_visivel=None):
    pasta = Path(pasta)
    executavel = str(executavel or sys.executable)
    argumentos = [executavel, str(pasta / "monitor_ao_vivo.py")]
    if terminal_visivel is None:
        terminal_visivel = bool(
            os.name == "nt"
            and os.getenv("MONITOR_TERMINAL_VISIVEL", "1").strip().lower()
            not in ("0", "false", "nao", "não", "off")
        )
    else:
        terminal_visivel = bool(terminal_visivel and os.name == "nt")
    iniciador_visivel = pasta / "abrir_monitor_visivel.cmd"
    if terminal_visivel and iniciador_visivel.exists():
        argumentos = [
            os.environ.get("ComSpec") or "cmd.exe",
            "/d",
            "/c",
            str(iniciador_visivel),
        ]
    ambiente = ambiente_processo_utf8()
    ambiente["MONITOR_MODO_INICIO"] = (
        "terminal_visivel" if terminal_visivel else "segundo_plano"
    )
    opcoes = {
        "cwd": str(pasta),
        "env": ambiente,
    }
    if os.name == "nt":
        if terminal_visivel:
            # O Playwright precisa de handles estáveis no Windows. Uma nova
            # console independente evita o WinError 5 observado quando o
            # watchdog relança o monitor sem janela e mantém o terminal usado
            # para acompanhar a coleta.
            opcoes["creationflags"] = (
                subprocess.CREATE_NEW_CONSOLE
                | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            opcoes.update({
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "creationflags": (
                    subprocess.CREATE_NO_WINDOW
                    | subprocess.CREATE_NEW_PROCESS_GROUP
                ),
            })
    else:
        opcoes.update({
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "start_new_session": True,
        })
    caminho_estado = pasta / "monitor_processo.json"
    registrar_estado(
        caminho_estado,
        "iniciando",
        modo_inicio=ambiente["MONITOR_MODO_INICIO"],
        rollback_terminal_visivel="MONITOR_TERMINAL_VISIVEL=0",
    )
    try:
        processo = subprocess.Popen(argumentos, **opcoes)
    except Exception as erro:
        registrar_estado(
            caminho_estado, "falha", erro=type(erro).__name__
        )
        raise
    # O PID do cmd/launcher fica separado do PID que o próprio monitor
    # publica. O filho pode já ter gravado "ativo" antes de Popen retornar.
    registrar_estado(
        pasta / "monitor_lancamento.json", "iniciado", pid=processo.pid,
        modo_inicio=ambiente["MONITOR_MODO_INICIO"],
    )
    return processo.pid


def iniciar_watchdog(pasta, executavel=None):
    pasta = Path(pasta)
    executavel = str(executavel or sys.executable)
    argumentos = [executavel, str(pasta / "watchdog.py")]
    opcoes = {
        "cwd": str(pasta),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": ambiente_processo_utf8(),
    }
    if os.name == "nt":
        opcoes["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        opcoes["start_new_session"] = True
    processo = subprocess.Popen(argumentos, **opcoes)
    return processo.pid


def iniciar_pre_live(pasta, executavel=None):
    pasta = Path(pasta)
    executavel = str(executavel or sys.executable)
    argumentos = [executavel, str(pasta / "agendador_pre_live.py")]
    opcoes = {
        "cwd": str(pasta),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": ambiente_processo_utf8(),
    }
    if os.name == "nt":
        opcoes["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        opcoes["start_new_session"] = True
    caminho_estado = pasta / "pre_live_processo.json"
    registrar_estado(caminho_estado, "iniciando")
    try:
        processo = subprocess.Popen(argumentos, **opcoes)
    except Exception as erro:
        registrar_estado(
            caminho_estado, "falha", erro=type(erro).__name__
        )
        raise
    return processo.pid


def garantir_pre_live_ativo(
    pasta, iniciar_fn=None, verificar_pid=None, verificar_instancia=None
):
    pasta = Path(pasta)
    iniciar_fn = iniciar_fn or iniciar_pre_live
    verificar_pid = verificar_pid or pid_ativo
    verificar_instancia = verificar_instancia or (
        lambda: trava_em_uso(pasta / "pre_live_instancia.lock")
    )
    estado = ler_estado(pasta / "pre_live_processo.json")
    pid_anterior = estado.get("pid")
    if verificar_instancia():
        return {
            "estado": "ativo", "pid": pid_anterior,
            "pid_responde": bool(verificar_pid(pid_anterior)),
        }
    pid = iniciar_fn(pasta)
    return {"estado": "iniciado", "pid": pid, "pid_responde": True}


def garantir_watchdog_ativo(
    pasta, iniciar_fn=None, verificar_pid=None, verificar_instancia=None
):
    """Mantem o watchdog vivo quando o monitor principal continua ativo."""
    pasta = Path(pasta)
    iniciar_fn = iniciar_fn or iniciar_watchdog
    verificar_pid = verificar_pid or pid_ativo
    verificar_instancia = verificar_instancia or (
        lambda: trava_em_uso(pasta / "watchdog_instancia.lock")
    )
    estado = ler_estado(pasta / "watchdog_processo.json")
    pid_anterior = estado.get("pid")
    instancia_ativa = bool(verificar_instancia())
    pid_responde = bool(verificar_pid(pid_anterior))
    if instancia_ativa:
        return {
            "estado": "ativo",
            "pid": int(pid_anterior) if pid_anterior is not None else None,
            "pid_responde": pid_responde,
            "trava_em_uso": True,
        }
    novo_pid = int(iniciar_fn(pasta))
    return {
        "estado": "reiniciado",
        "pid": novo_pid,
        "pid_anterior": pid_anterior,
        "status_anterior": estado.get("status"),
        "pid_anterior_responde": pid_responde,
        "trava_em_uso": False,
    }
