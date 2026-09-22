import argparse
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from backup_banco import BackupBanco, restaurar_banco_de_backup
from banco import BancoMonitor, auditar_compatibilidade
from controle_acesso_packball import verificar_acesso_packball
from controle_sistema import (
    liberar_modo_manutencao,
    ler_modo_manutencao,
    solicitar_modo_manutencao,
)
from observabilidade import Observabilidade
from observabilidade import resumir_erro_seguro
from packball_login import fazer_login
from preflight_reinicio import executar_preflight, verificar_banco
from processo_monitor import (
    iniciar_monitor,
    iniciar_watchdog,
    ler_estado,
    pid_ativo,
    trava_em_uso,
)


VERSAO_RETOMADA_TRANSACIONAL = "retomada-transacional-v1"


def _verificacao_aprovada_para_reinicio(item):
    """Usa a mesma semantica efetiva do agregador do preflight."""
    item = item or {}
    return bool(item.get("saudavel_para_reinicio", item.get("saudavel")))


def _restaurar_manutencao_apos_falha_inicio(
    pasta, resultado, motivo, erro=None
):
    """Fecha a janela de risco entre liberar a pausa e estabilizar processos."""
    pasta = Path(pasta)
    estado = solicitar_modo_manutencao(
        pasta, motivo="rollback_inicio_instavel"
    )
    rollback = {
        "versao": VERSAO_RETOMADA_TRANSACIONAL,
        "aplicado": True,
        "motivo": str(motivo or "inicio_instavel"),
        "modo_manutencao": estado,
        "erro": type(erro).__name__ if erro else None,
    }
    resultado["rollback_manutencao"] = rollback
    try:
        Observabilidade(pasta / "monitor_eventos.jsonl").modo_manutencao(
            "restaurado_apos_falha_inicio", rollback
        )
    except Exception as erro_observabilidade:
        # A pausa persistida e o efeito de seguranca autoritativo. Uma falha
        # secundaria do log nao pode desfazer nem mascarar o rollback.
        rollback["observabilidade"] = "indisponivel"
        rollback["erro_observabilidade"] = type(
            erro_observabilidade
        ).__name__
    return rollback


def analisar_argumentos_inicio(argv=None):
    parser = argparse.ArgumentParser(
        description="Inicia o PackBall depois do preflight de seguranca."
    )
    parser.add_argument(
        "--retomar-manutencao",
        action="store_true",
        help=(
            "Confirma explicitamente a retomada de uma pausa manual. Sem "
            "esta opcao, a manutencao permanece intocada."
        ),
    )
    return parser.parse_args(argv)


def _componente_ativo(
    caminho_estado, caminho_trava, verificar_pid, verificar_trava
):
    estado = ler_estado(caminho_estado)
    pid = estado.get("pid")
    trava_ativa = bool(verificar_trava(caminho_trava))
    pid_responde = bool(verificar_pid(pid))
    return trava_ativa, pid, pid_responde


def garantir_sistema(
    pasta,
    iniciar_monitor_fn=None,
    iniciar_watchdog_fn=None,
    verificar_pid=None,
    verificar_trava=None,
    preservar_manutencao=False,
):
    pasta = Path(pasta)
    iniciar_monitor_fn = iniciar_monitor_fn or iniciar_monitor
    iniciar_watchdog_fn = iniciar_watchdog_fn or iniciar_watchdog
    verificar_pid = verificar_pid or pid_ativo
    verificar_trava = verificar_trava or trava_em_uso
    acesso_packball = verificar_acesso_packball(
        pasta / "packball_acesso_estado.json"
    )
    if not acesso_packball["saudavel"]:
        bloqueado = {
            "estado": "bloqueado_acesso_packball",
            "pid": None,
        }
        return {
            "modo_manutencao_liberado": False,
            "acesso_packball": acesso_packball,
            "monitor": dict(bloqueado),
            "watchdog": dict(bloqueado),
        }
    if (
        preservar_manutencao
        and ler_modo_manutencao(pasta).get("ativo")
    ):
        bloqueado = {
            "estado": "manutencao_preservada",
            "pid": None,
        }
        return {
            "motivo": "modo_manutencao_ativo",
            "modo_manutencao_liberado": False,
            "acesso_packball": acesso_packball,
            "monitor": dict(bloqueado),
            "watchdog": dict(bloqueado),
        }
    resultado = {
        "modo_manutencao_liberado": (
            liberar_modo_manutencao(pasta)
            if not preservar_manutencao else False
        ),
        "acesso_packball": acesso_packball,
    }

    ativo, pid, pid_responde = _componente_ativo(
        pasta / "monitor_processo.json",
        pasta / "monitor_instancia.lock",
        verificar_pid,
        verificar_trava,
    )
    if ativo:
        resultado["monitor"] = {
            "estado": "ja_ativo", "pid": pid,
            "pid_responde": pid_responde,
        }
    else:
        resultado["monitor"] = {
            "estado": "iniciado",
            "pid": iniciar_monitor_fn(pasta),
        }

    ativo, pid, pid_responde = _componente_ativo(
        pasta / "watchdog_processo.json",
        pasta / "watchdog_instancia.lock",
        verificar_pid,
        verificar_trava,
    )
    if ativo:
        resultado["watchdog"] = {
            "estado": "ja_ativo", "pid": pid,
            "pid_responde": pid_responde,
        }
    else:
        resultado["watchdog"] = {
            "estado": "iniciado",
            "pid": iniciar_watchdog_fn(pasta),
        }

    return resultado


def confirmar_inicio_estavel(
    pasta,
    resultado,
    timeout_segundos=25,
    estabilidade_segundos=12,
    intervalo_segundos=0.5,
    verificar_pid=None,
    verificar_trava=None,
    ler_estado_fn=None,
    relogio=None,
    dormir=None,
):
    """Confirma que processos recém-criados sobreviveram à inicialização."""
    pasta = Path(pasta)
    verificar_pid = verificar_pid or pid_ativo
    verificar_trava = verificar_trava or trava_em_uso
    ler_estado_fn = ler_estado_fn or ler_estado
    relogio = relogio or time.monotonic
    dormir = dormir or time.sleep
    alvos = [
        componente
        for componente in ("monitor", "watchdog")
        if (resultado.get(componente) or {}).get("estado") == "iniciado"
    ]
    if not alvos:
        resultado["confirmacao_inicio"] = {
            "saudavel": True,
            "estado": "nao_necessaria",
            "componentes": {},
        }
        return resultado

    inicio = relogio()
    limite = inicio + max(float(timeout_segundos), 0)
    estavel_desde = None
    diagnosticos = {}
    while True:
        agora = relogio()
        diagnosticos = {}
        todos_ativos = True
        falha_explicita = False
        for componente in alvos:
            estado = ler_estado_fn(
                pasta / f"{componente}_processo.json"
            )
            pid = estado.get("pid")
            trava = bool(
                verificar_trava(pasta / f"{componente}_instancia.lock")
            )
            pid_responde = bool(verificar_pid(pid))
            ativo = (
                estado.get("status") == "ativo"
                and trava
                and pid_responde
            )
            falhou = estado.get("status") == "falha"
            diagnostico = {
                "saudavel": ativo,
                "status": estado.get("status"),
                "pid": pid,
                "pid_responde": pid_responde,
                "trava_em_uso": trava,
            }
            if estado.get("erro") or estado.get("mensagem"):
                diagnostico["erro"] = resumir_erro_seguro(
                    estado.get("erro") or "erro_desconhecido",
                    limite=100,
                )
                diagnostico["mensagem"] = resumir_erro_seguro(
                    estado.get("mensagem") or "sem detalhe",
                    limite=500,
                )
            diagnosticos[componente] = diagnostico
            todos_ativos = todos_ativos and ativo
            falha_explicita = falha_explicita or falhou

        if todos_ativos:
            estavel_desde = estavel_desde or agora
            if agora - estavel_desde >= float(estabilidade_segundos):
                resultado["confirmacao_inicio"] = {
                    "saudavel": True,
                    "estado": "estavel",
                    "duracao_segundos": round(agora - inicio, 3),
                    "componentes": diagnosticos,
                }
                return resultado
        else:
            estavel_desde = None

        if falha_explicita or agora >= limite:
            resultado["estado"] = "inicio_falhou"
            resultado["motivo"] = (
                "processo_falhou_na_inicializacao"
                if falha_explicita else "confirmacao_inicio_expirou"
            )
            resultado["falhas_inicio"] = [
                nome for nome, item in diagnosticos.items()
                if not item["saudavel"]
            ]
            resultado["confirmacao_inicio"] = {
                "saudavel": False,
                "estado": (
                    "falha_explicita"
                    if falha_explicita else "timeout"
                ),
                "duracao_segundos": round(agora - inicio, 3),
                "componentes": diagnosticos,
            }
            _restaurar_manutencao_apos_falha_inicio(
                pasta, resultado, resultado["motivo"]
            )
            return resultado
        dormir(min(float(intervalo_segundos), max(limite - agora, 0)))


def preparar_banco_para_preflight(
    pasta, agora=None, verificar_trava=None
):
    """Aplica migracoes aditivas com um ponto de recuperacao anterior."""
    pasta = Path(pasta)
    caminho_banco = pasta / "monitor_packball.db"
    verificar_trava = verificar_trava or trava_em_uso
    componentes_ativos = [
        nome
        for nome in ("monitor", "watchdog")
        if verificar_trava(pasta / f"{nome}_instancia.lock")
    ]
    if not caminho_banco.exists():
        if componentes_ativos:
            return {
                "saudavel": False,
                "necessaria": True,
                "estado": "recuperacao_adiada_processos_ativos",
                "componentes_ativos": componentes_ativos,
                "motivo": "banco_ausente",
            }
        recuperacao = restaurar_banco_de_backup(
            caminho_banco,
            pasta / "backups",
            agora=agora,
            motivo="banco_ausente",
        )
        if recuperacao.get("saudavel"):
            return {
                "saudavel": True,
                "necessaria": True,
                "estado": "banco_recuperado_backup",
                "recuperacao": recuperacao,
            }
        if (
            recuperacao.get("estado") != "sem_backup_restauravel"
            or recuperacao.get("avaliados")
        ):
            return {
                "saudavel": False,
                "necessaria": True,
                "estado": "banco_ausente_sem_backup_valido",
                "recuperacao": recuperacao,
            }
        return {
            "saudavel": True,
            "necessaria": False,
            "estado": "banco_ausente_preflight_decidira",
        }
    conexao = None
    try:
        uri = caminho_banco.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        integridade = [
            str(item[0])
            for item in conexao.execute("PRAGMA quick_check")
        ]
        compatibilidade = auditar_compatibilidade(conexao)
    except OSError as erro:
        return {
            "saudavel": False,
            "necessaria": True,
            "estado": "banco_inacessivel",
            "erro": type(erro).__name__,
        }
    except sqlite3.Error as erro:
        mensagem = str(erro).lower()
        corrupcao_comprovada = any(
            trecho in mensagem
            for trecho in (
                "file is not a database",
                "database disk image is malformed",
                "database corrupt",
                "malformed database schema",
            )
        )
        if not corrupcao_comprovada:
            return {
                "saudavel": False,
                "necessaria": True,
                "estado": "banco_inacessivel",
                "erro": type(erro).__name__,
            }
        integridade = [str(erro)]
        compatibilidade = None
    finally:
        if conexao is not None:
            conexao.close()
    if integridade != ["ok"]:
        if componentes_ativos:
            return {
                "saudavel": False,
                "necessaria": True,
                "estado": "recuperacao_adiada_processos_ativos",
                "componentes_ativos": componentes_ativos,
                "quick_check": integridade,
            }
        recuperacao = restaurar_banco_de_backup(
            caminho_banco,
            pasta / "backups",
            agora=agora,
            motivo="corrupcao_comprovada",
        )
        if recuperacao.get("saudavel"):
            return {
                "saudavel": True,
                "necessaria": True,
                "estado": "banco_recuperado_backup",
                "recuperacao": recuperacao,
            }
        return {
            "saudavel": False,
            "necessaria": True,
            "estado": "banco_corrompido",
            "quick_check": integridade,
            "recuperacao": recuperacao,
        }
    agora = agora or datetime.now()
    backup = BackupBanco(
        pasta / "backups",
        pasta_espelho=(os.getenv("BACKUP_ESPELHO_DIRETORIO") or None),
        compactar=(
            os.getenv("BACKUP_COMPACTACAO_ATIVA", "1") == "1"
        ),
    )
    if compatibilidade["compativel"]:
        # O preflight exige um backup diario compativel com o esquema atual.
        # Depois de uma migracao interrompida, o banco pode ja estar correto
        # enquanto o backup do dia ainda pertence ao esquema anterior. Sem
        # esta reconciliacao, toda retomada seguinte fica presa entre uma
        # preparacao que diz "esquema atual" e um preflight que rejeita o
        # backup obsoleto.
        if componentes_ativos:
            return {
                "saudavel": True,
                "necessaria": False,
                "estado": "esquema_atual",
                "backup_diario_reconciliado": False,
                "componentes_ativos": componentes_ativos,
            }
        origem = sqlite3.connect(caminho_banco, timeout=30)
        try:
            backup_diario, backup_regenerado = backup.criar_diario(
                origem, agora
            )
        finally:
            origem.close()
        return {
            "saudavel": True,
            "necessaria": False,
            "estado": "esquema_atual",
            "backup_diario": str(backup_diario),
            "backup_diario_reconciliado": True,
            "backup_diario_regenerado": bool(backup_regenerado),
        }

    if componentes_ativos:
        return {
            "saudavel": False,
            "necessaria": True,
            "estado": "migracao_adiada_processos_ativos",
            "componentes_ativos": componentes_ativos,
        }

    origem = sqlite3.connect(caminho_banco, timeout=30)
    try:
        pre_migracao = backup.criar_pre_migracao(origem, agora)
    finally:
        origem.close()
    banco = BancoMonitor(caminho_banco)
    banco.fechar()
    verificacao = verificar_banco(caminho_banco)
    if not verificacao["saudavel"]:
        return {
            "saudavel": False,
            "necessaria": True,
            "estado": "migracao_incompleta",
            "backup_pre_migracao": str(pre_migracao),
            "verificacao": verificacao,
        }
    origem = sqlite3.connect(caminho_banco, timeout=30)
    try:
        backup_diario, backup_regenerado = backup.criar_diario(
            origem, agora
        )
    finally:
        origem.close()
    return {
        "saudavel": True,
        "necessaria": True,
        "estado": "migracao_aplicada",
        "backup_pre_migracao": str(pre_migracao),
        "backup_diario": str(backup_diario),
        "backup_diario_regenerado": bool(backup_regenerado),
    }


def iniciar_validado(
    pasta,
    iniciar_monitor_fn=None,
    iniciar_watchdog_fn=None,
    verificar_pid=None,
    verificar_trava=None,
    rodar_testes=True,
    permitir_retomada_manutencao=False,
    preflight_fn=None,
    renovar_sessao_fn=None,
    preparar_banco_fn=None,
):
    pasta = Path(pasta)
    modo = ler_modo_manutencao(pasta)
    if modo.get("ativo") and not permitir_retomada_manutencao:
        bloqueado = {"estado": "manutencao_preservada", "pid": None}
        return {
            "estado": "inicio_recusado",
            "motivo": "modo_manutencao_ativo",
            "monitor": dict(bloqueado),
            "watchdog": dict(bloqueado),
        }

    preparar_banco_fn = preparar_banco_fn or preparar_banco_para_preflight
    try:
        preparacao_banco = preparar_banco_fn(pasta)
    except Exception as erro:
        preparacao_banco = {
            "saudavel": False,
            "necessaria": True,
            "estado": "erro_preparacao_banco",
            "erro": type(erro).__name__,
        }
    if not preparacao_banco.get("saudavel"):
        bloqueado = {"estado": "banco_nao_preparado", "pid": None}
        return {
            "estado": "inicio_recusado",
            "motivo": "preparacao_banco_falhou",
            "preparacao_banco": preparacao_banco,
            "monitor": dict(bloqueado),
            "watchdog": dict(bloqueado),
        }

    preflight_fn = preflight_fn or executar_preflight
    preflight = preflight_fn(
        pasta,
        rodar_testes=rodar_testes,
        permitir_coleta_parada_para_reinicio=True,
    )
    verificacoes = preflight.get("verificacoes") or {}
    sessao = verificacoes.get("sessao_packball") or {}
    acesso = verificacoes.get("acesso_packball") or {}
    falhas_iniciais = {
        nome for nome, item in verificacoes.items()
        if not _verificacao_aprovada_para_reinicio(item)
    }
    sessao_renovada = False
    pode_renovar_sessao = bool(
        not preflight.get("pronto_para_reinicio")
        and sessao.get("motivo") in {
            "sessao_ausente",
            "sessao_invalida",
            "sessao_sem_autenticacao",
            "sessao_expirada",
        }
        and acesso.get("saudavel") is True
        and falhas_iniciais <= {"sessao_packball", "coleta"}
    )
    if pode_renovar_sessao:
        renovar_sessao_fn = renovar_sessao_fn or (
            lambda: fazer_login(headless=True, manter_aberto=False)
        )
        try:
            renovar_sessao_fn()
        except Exception as erro:
            causa = erro.__cause__ or erro.__context__ or erro
            bloqueado = {"estado": "sessao_nao_renovada", "pid": None}
            return {
                "estado": "inicio_recusado",
                "motivo": "renovacao_sessao_falhou",
                "erro_renovacao": type(erro).__name__,
                "causa_renovacao": type(causa).__name__,
                "preflight": preflight,
                "monitor": dict(bloqueado),
                "watchdog": dict(bloqueado),
            }
        sessao_renovada = True
        preflight = preflight_fn(
            pasta,
            rodar_testes=rodar_testes,
            permitir_coleta_parada_para_reinicio=True,
        )
    if not preflight["pronto_para_reinicio"]:
        falhas = [
            nome for nome, item in preflight["verificacoes"].items()
            if not _verificacao_aprovada_para_reinicio(item)
        ]
        bloqueado = {"estado": "preflight_recusado", "pid": None}
        return {
            "estado": "inicio_recusado",
            "motivo": "preflight_reprovado",
            "falhas_preflight": falhas,
            "preflight": preflight,
            "monitor": dict(bloqueado),
            "watchdog": dict(bloqueado),
        }

    try:
        resultado = garantir_sistema(
            pasta,
            iniciar_monitor_fn=iniciar_monitor_fn,
            iniciar_watchdog_fn=iniciar_watchdog_fn,
            verificar_pid=verificar_pid,
            verificar_trava=verificar_trava,
            preservar_manutencao=not permitir_retomada_manutencao,
        )
    except Exception as erro:
        resultado = {
            "estado": "inicio_falhou",
            "motivo": "falha_lancamento_componentes",
            "erro_inicio": type(erro).__name__,
            "mensagem_inicio": resumir_erro_seguro(erro, limite=500),
            "monitor": {
                "estado": "inicio_interrompido",
                "pid": None,
            },
            "watchdog": {
                "estado": "inicio_interrompido",
                "pid": None,
            },
            "preflight": preflight,
            "sessao_renovada": sessao_renovada,
            "preparacao_banco": preparacao_banco,
        }
        _restaurar_manutencao_apos_falha_inicio(
            pasta, resultado, resultado["motivo"], erro=erro
        )
        return resultado
    if resultado.get("motivo") == "modo_manutencao_ativo":
        resultado["estado"] = "inicio_recusado"
        return resultado
    resultado["estado"] = "iniciado_ou_ja_ativo"
    resultado["preflight"] = preflight
    resultado["sessao_renovada"] = sessao_renovada
    resultado["preparacao_banco"] = preparacao_banco
    return resultado


def main(argv=None):
    argumentos = analisar_argumentos_inicio(argv)
    pasta = Path(__file__).parent
    load_dotenv(pasta / ".env")
    os.environ.setdefault("BACKUP_COMPACTACAO_ATIVA", "1")
    resultado = iniciar_validado(
        pasta,
        permitir_retomada_manutencao=argumentos.retomar_manutencao,
    )
    if resultado.get("estado") == "inicio_recusado":
        print(
            "Sistema nao iniciado: "
            f"{resultado['motivo']} | falhas="
            f"{', '.join(resultado.get('falhas_preflight') or []) or '-'}"
        )
        raise SystemExit(1)
    if resultado.get("estado") == "inicio_falhou":
        print(
            "Sistema não iniciou; a manutenção foi restaurada: "
            f"{resultado.get('motivo')} | erro="
            f"{resultado.get('erro_inicio') or '-'}"
        )
        raise SystemExit(1)
    resultado = confirmar_inicio_estavel(pasta, resultado)
    if resultado.get("estado") == "inicio_falhou":
        print(
            "Sistema não estabilizou após a inicialização: "
            f"{resultado.get('motivo')} | componentes="
            f"{', '.join(resultado.get('falhas_inicio') or []) or '-'}"
        )
        raise SystemExit(1)
    if not resultado["acesso_packball"]["saudavel"]:
        print(
            "Sistema nao iniciado: protecao do PackBall ativa por mais "
            f"{resultado['acesso_packball']['restante_segundos']:.0f}s."
        )
        raise SystemExit(1)
    if resultado["modo_manutencao_liberado"]:
        Observabilidade(pasta / "monitor_eventos.jsonl").modo_manutencao(
            "liberado"
        )
        print("Modo de manutenção liberado; retomando o sistema.")
    preparacao = resultado.get("preparacao_banco") or {}
    if preparacao.get("estado") == "banco_recuperado_backup":
        recuperacao = preparacao.get("recuperacao") or {}
        print(
            "Banco recuperado automaticamente | backup="
            f"{recuperacao.get('backup') or '-'} | quarentena="
            f"{recuperacao.get('quarentena') or 'nao necessaria'}"
        )
    for componente in ("monitor", "watchdog"):
        item = resultado[componente]
        texto = "já estava ativo" if item["estado"] == "ja_ativo" else "iniciado"
        print(f"{componente}: {texto} | PID {item['pid']}")


if __name__ == "__main__":
    main()
