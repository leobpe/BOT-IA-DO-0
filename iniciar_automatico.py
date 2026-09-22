"""Entrada silenciosa e auditável usada pelo Agendador do Windows."""

import sys
from datetime import datetime
from pathlib import Path

from autostart_windows import consultar as consultar_autostart
from iniciar_sistema import confirmar_inicio_estavel, iniciar_validado
from observabilidade import resumir_erro_seguro
from processo_monitor import (
    gravar_json_atomico,
    iniciar_monitor,
    iniciar_watchdog,
    ler_estado,
    pid_ativo,
    trava_em_uso,
)
from controle_sistema import ler_modo_manutencao

VERSAO_HEARTBEAT_AUTOSTART = "autostart-heartbeat-v2"


def sistema_ativo_confirmado(
    pasta, verificar_pid=None, verificar_trava=None, ler_estado_fn=None,
):
    """Confirma os dois processos sem executar o pré-voo de recuperação.

    A tarefa do Windows é executada periodicamente. Quando monitor e watchdog
    já possuem trava exclusiva e PID vivo, não existe recuperação a realizar;
    repetir o pré-voo completo nesse cenário pode transformar uma oscilação de
    uma fonte auxiliar em uma falsa falha de autorrecuperação.
    """
    pasta = Path(pasta)
    verificar_pid = verificar_pid or pid_ativo
    verificar_trava = verificar_trava or trava_em_uso
    ler_estado_fn = ler_estado_fn or ler_estado
    componentes = {}
    for nome in ("monitor", "watchdog"):
        estado = ler_estado_fn(pasta / f"{nome}_processo.json")
        pid = estado.get("pid")
        trava_ativa = bool(
            verificar_trava(pasta / f"{nome}_instancia.lock")
        )
        pid_responde = bool(verificar_pid(pid))
        confirmado = bool(trava_ativa and pid_responde)
        componentes[nome] = {
            "estado": "ja_ativo" if confirmado else "nao_confirmado",
            "pid": pid,
            "pid_responde": pid_responde,
            "trava_ativa": trava_ativa,
        }
    return {
        "ativo": all(
            item["estado"] == "ja_ativo" for item in componentes.values()
        ),
        **componentes,
    }


def executavel_python_console(pasta, executavel_atual=None):
    """Prefere python.exe para manter a janela visível do monitor."""
    pasta = Path(pasta)
    candidato_venv = pasta / ".venv" / "Scripts" / "python.exe"
    if candidato_venv.exists():
        return candidato_venv

    atual = Path(executavel_atual or sys.executable)
    if atual.name.lower() == "pythonw.exe":
        candidato_console = atual.with_name("python.exe")
        if candidato_console.exists():
            return candidato_console
    return atual


def evidenciar_definicao_tarefa(pasta, consultar_fn=None):
    """Obtém prova direta da definição sem aceitar o próprio heartbeat."""
    consultar_fn = consultar_fn or consultar_autostart
    try:
        estado = consultar_fn(pasta=pasta)
    except Exception as erro:
        return {
            "saudavel": False,
            "consulta_direta": False,
            "divergencias": ["consulta_definicao_falhou"],
            "erro": type(erro).__name__,
        }
    consulta_direta = (
        estado.get("consultavel", True)
        and estado.get("origem_evidencia") == "consulta_direta"
    )
    permite_bateria = estado.get("permite_inicio_em_bateria") is True
    continua_bateria = estado.get("continua_em_bateria") is True
    divergencias = list(estado.get("divergencias") or [])
    if not consulta_direta:
        divergencias.append("consulta_definicao_nao_direta")
    if not permite_bateria:
        divergencias.append("inicio_em_bateria_nao_comprovado")
    if not continua_bateria:
        divergencias.append("continuidade_em_bateria_nao_comprovada")
    divergencias = list(dict.fromkeys(divergencias))
    return {
        "saudavel": bool(
            estado.get("instalada")
            and estado.get("saudavel")
            and consulta_direta
            and permite_bateria
            and continua_bateria
        ),
        "consulta_direta": consulta_direta,
        "instalada": bool(estado.get("instalada")),
        "permite_inicio_em_bateria": permite_bateria,
        "continua_em_bateria": continua_bateria,
        "intervalo": estado.get("intervalo"),
        "divergencias": divergencias,
    }


def iniciar_automaticamente(
    pasta,
    garantir_fn=None,
    executavel_atual=None,
    agora=None,
    origem_agendador=False,
    confirmar_fn=None,
    consultar_tarefa_fn=None,
    detectar_sistema_fn=None,
):
    pasta = Path(pasta)
    if garantir_fn is None:
        garantir_fn = lambda destino, **opcoes: iniciar_validado(
            destino,
            **opcoes,
            rodar_testes=False,
            permitir_retomada_manutencao=False,
        )
    agora = agora or datetime.now()
    executavel = executavel_python_console(pasta, executavel_atual)
    definicao_tarefa = (
        evidenciar_definicao_tarefa(
            pasta, consultar_fn=consultar_tarefa_fn
        )
        if origem_agendador else None
    )

    try:
        detectar_sistema_fn = detectar_sistema_fn or sistema_ativo_confirmado
        sistema_ativo = (
            detectar_sistema_fn(pasta)
            if origem_agendador
            and not ler_modo_manutencao(pasta).get("ativo")
            else {"ativo": False}
        )
        if sistema_ativo.get("ativo"):
            resultado = {
                "estado": "iniciado_ou_ja_ativo",
                "motivo": "sistema_ja_ativo_confirmado",
                "monitor": sistema_ativo["monitor"],
                "watchdog": sistema_ativo["watchdog"],
            }
        else:
            resultado = garantir_fn(
                pasta,
                iniciar_monitor_fn=lambda destino: iniciar_monitor(
                    destino, executavel=executavel
                ),
                iniciar_watchdog_fn=lambda destino: iniciar_watchdog(
                    destino, executavel=executavel
                ),
            )
        if resultado.get("estado") != "inicio_recusado":
            confirmar_fn = confirmar_fn or confirmar_inicio_estavel
            resultado = confirmar_fn(pasta, resultado)
    except Exception as erro:
        gravar_json_atomico(
            pasta / "autostart_ultima_execucao.json",
            {
                "versao": VERSAO_HEARTBEAT_AUTOSTART,
                "status": "falha",
                "atualizado_em": agora.replace(microsecond=0).isoformat(),
                "erro": type(erro).__name__,
                "mensagem": resumir_erro_seguro(erro),
                "origem": (
                    "agendador_windows" if origem_agendador else "manual"
                ),
                "definicao_tarefa": definicao_tarefa,
            },
        )
        raise

    recusado = resultado.get("estado") == "inicio_recusado"
    inicio_falhou = resultado.get("estado") == "inicio_falhou"
    gravar_json_atomico(
        pasta / "autostart_ultima_execucao.json",
        {
            "versao": VERSAO_HEARTBEAT_AUTOSTART,
            "status": (
                "recusado"
                if recusado
                else ("falha" if inicio_falhou else "sucesso")
            ),
            "atualizado_em": agora.replace(microsecond=0).isoformat(),
            "motivo": resultado.get("motivo"),
            "falhas_preflight": resultado.get("falhas_preflight") or [],
            "falhas_inicio": resultado.get("falhas_inicio") or [],
            "erro_renovacao": resultado.get("erro_renovacao"),
            "causa_renovacao": resultado.get("causa_renovacao"),
            "confirmacao_inicio": resultado.get("confirmacao_inicio"),
            "monitor": resultado["monitor"],
            "watchdog": resultado["watchdog"],
            "origem": (
                "agendador_windows" if origem_agendador else "manual"
            ),
            "definicao_tarefa": definicao_tarefa,
        },
    )
    return resultado


def main():
    iniciar_automaticamente(
        Path(__file__).parent,
        origem_agendador="--agendador-windows" in sys.argv,
    )


if __name__ == "__main__":
    main()
