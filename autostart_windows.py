"""Gerencia a tarefa idempotente de recuperação total no Windows."""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


NOME_TAREFA = "PackBall Monitor Profissional"
INTERVALO_MINUTOS = 5
MARCADOR_AGENDADOR = "--agendador-windows"
MAX_IDADE_HEARTBEAT_MINUTOS = 15
VERSAO_HEARTBEAT_AUTOSTART = "autostart-heartbeat-v2"


def executavel_pythonw(pasta):
    pasta = Path(pasta)
    candidatos = (
        pasta / ".venv" / "Scripts" / "pythonw.exe",
        Path(sys.executable).with_name("pythonw.exe"),
    )
    for candidato in candidatos:
        if candidato.exists():
            return candidato.resolve()
    raise FileNotFoundError(
        "pythonw.exe não encontrado; confirme a instalação da .venv"
    )


def acao_tarefa(pasta, pythonw=None):
    pasta = Path(pasta).resolve()
    pythonw = Path(pythonw or executavel_pythonw(pasta)).resolve()
    launcher = (pasta / "iniciar_automatico.py").resolve()
    if not launcher.exists():
        raise FileNotFoundError(f"Launcher não encontrado: {launcher}")
    return f'"{pythonw}" "{launcher}" {MARCADOR_AGENDADOR}'


def comando_instalacao(pasta, pythonw=None, usuario=None):
    usuario = usuario or os.environ.get("USERNAME")
    comando = [
        "schtasks", "/Create",
        "/TN", NOME_TAREFA,
        "/TR", acao_tarefa(pasta, pythonw=pythonw),
        "/SC", "MINUTE",
        "/MO", str(INTERVALO_MINUTOS),
        "/IT",
        "/RL", "LIMITED",
        "/F",
    ]
    if usuario:
        comando.extend(("/RU", usuario))
    return comando


def comando_consulta(xml=True):
    comando = ["schtasks", "/Query", "/TN", NOME_TAREFA]
    if xml:
        comando.append("/XML")
    return comando


def comando_ajuste_energia():
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$tarefa=Get-ScheduledTask -TaskName '{NOME_TAREFA}'; "
        "$tarefa.Settings.DisallowStartIfOnBatteries=$false; "
        "$tarefa.Settings.StopIfGoingOnBatteries=$false; "
        "$null=Set-ScheduledTask -InputObject $tarefa"
    )
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]


def comando_remocao():
    return ["schtasks", "/Delete", "/TN", NOME_TAREFA, "/F"]


def _executar(comando, executor=None):
    executor = executor or subprocess.run
    return executor(
        comando,
        capture_output=True,
        text=False,
        check=False,
    )


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor
    if valor.startswith((b"\xff\xfe", b"\xfe\xff")):
        return valor.decode("utf-16", errors="replace")
    if valor.count(b"\x00") > max(2, len(valor) // 5):
        return valor.decode("utf-16", errors="replace")
    for codificacao in ("utf-8-sig", "cp850", "cp1252"):
        try:
            return valor.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return valor.decode("utf-8", errors="replace")


def _valor_xml(raiz, caminho):
    elemento = raiz.find(caminho)
    return (elemento.text or "").strip() if elemento is not None else ""


def validar_definicao_xml(conteudo, pasta=None, pythonw=None):
    try:
        raiz = ET.fromstring(conteudo)
    except (ET.ParseError, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "divergencias": ["xml_tarefa_invalido"],
            "erro": f"{type(erro).__name__}: {erro}",
        }
    comando = _valor_xml(raiz, ".//{*}Exec/{*}Command")
    argumentos = _valor_xml(raiz, ".//{*}Exec/{*}Arguments")
    intervalo = _valor_xml(raiz, ".//{*}Repetition/{*}Interval")
    logon = _valor_xml(raiz, ".//{*}Principal/{*}LogonType")
    nivel = _valor_xml(raiz, ".//{*}Principal/{*}RunLevel")
    habilitada = _valor_xml(raiz, ".//{*}Settings/{*}Enabled")
    bloqueia_inicio_bateria = _valor_xml(
        raiz, ".//{*}Settings/{*}DisallowStartIfOnBatteries"
    )
    para_em_bateria = _valor_xml(
        raiz, ".//{*}Settings/{*}StopIfGoingOnBatteries"
    )
    divergencias = []
    if pasta is not None:
        pasta = Path(pasta).resolve()
        python_esperado = Path(
            pythonw or executavel_pythonw(pasta)
        ).resolve()
        launcher_esperado = (pasta / "iniciar_automatico.py").resolve()
        try:
            comando_valido = Path(comando.strip('"')).resolve() == python_esperado
        except (OSError, ValueError):
            comando_valido = False
        try:
            argumento_valido = argumentos.strip() == (
                f'"{launcher_esperado}" {MARCADOR_AGENDADOR}'
            )
        except (OSError, ValueError):
            argumento_valido = False
    else:
        comando_valido = comando.strip('"').lower().endswith("pythonw.exe")
        argumento_valido = argumentos.strip().strip('"').lower().endswith(
            "iniciar_automatico.py"
        )
    if not comando_valido:
        divergencias.append("executavel_incorreto")
    if not argumento_valido:
        divergencias.append("launcher_incorreto")
    if intervalo.upper() != f"PT{INTERVALO_MINUTOS}M":
        divergencias.append("intervalo_incorreto")
    if logon.casefold() != "interactivetoken":
        divergencias.append("logon_nao_interativo")
    # O schtasks omite RunLevel no XML quando /RL LIMITED é usado.
    # No schema do Agendador o elemento é opcional; quando presente,
    # rejeitamos qualquer valor diferente de LeastPrivilege.
    if nivel and nivel.casefold() != "leastprivilege":
        divergencias.append("nivel_privilegio_incorreto")
    if habilitada and habilitada.casefold() != "true":
        divergencias.append("tarefa_desabilitada")
    if bloqueia_inicio_bateria.casefold() != "false":
        divergencias.append("inicio_em_bateria_bloqueado")
    if para_em_bateria.casefold() != "false":
        divergencias.append("parada_ao_usar_bateria")
    return {
        "saudavel": not divergencias,
        "divergencias": divergencias,
        "comando": comando,
        "argumentos": argumentos,
        "intervalo": intervalo,
        "logon": logon,
        "nivel_privilegio": nivel or "LeastPrivilege (implícito)",
        "habilitada": habilitada.casefold() != "false",
        "permite_inicio_em_bateria": (
            bloqueia_inicio_bateria.casefold() == "false"
        ),
        "continua_em_bateria": para_em_bateria.casefold() == "false",
    }


def _heartbeat_agendador_recente(pasta, agora=None):
    if pasta is None:
        return None
    caminho = Path(pasta) / "autostart_ultima_execucao.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        instante = datetime.fromisoformat(dados["atualizado_em"])
    except (
        OSError, KeyError, TypeError, ValueError, json.JSONDecodeError
    ):
        return None
    agora = agora or datetime.now()
    idade_minutos = max((agora - instante).total_seconds() / 60, 0)
    if (
        dados.get("origem") != "agendador_windows"
        or idade_minutos > MAX_IDADE_HEARTBEAT_MINUTOS
    ):
        return None
    return {
        "versao": dados.get("versao"),
        "status": dados.get("status"),
        "motivo": dados.get("motivo"),
        "falhas_preflight": dados.get("falhas_preflight") or [],
        "falhas_inicio": dados.get("falhas_inicio") or [],
        "confirmacao_inicio": dados.get("confirmacao_inicio"),
        "atualizado_em": dados["atualizado_em"],
        "idade_minutos": round(idade_minutos, 2),
        "definicao_tarefa": dados.get("definicao_tarefa"),
    }


def _heartbeat_execucao_saudavel(heartbeat):
    definicao = heartbeat.get("definicao_tarefa") or {}
    if (
        heartbeat.get("versao") != VERSAO_HEARTBEAT_AUTOSTART
        or not definicao.get("saudavel")
        or not definicao.get("consulta_direta")
        or definicao.get("permite_inicio_em_bateria") is not True
        or definicao.get("continua_em_bateria") is not True
    ):
        return False
    status = heartbeat.get("status")
    if status == "sucesso":
        return True
    if status != "recusado":
        return False
    if heartbeat.get("motivo") == "modo_manutencao_ativo":
        return True
    falhas = set(heartbeat.get("falhas_preflight") or [])
    return (
        heartbeat.get("motivo") == "preflight_reprovado"
        and bool(falhas)
        and falhas <= {"acesso_packball"}
    )


def consultar(executor=None, pasta=None, pythonw=None, agora=None):
    try:
        resultado = _executar(comando_consulta(), executor=executor)
    except OSError as erro:
        return {
            "instalada": False,
            "consultavel": False,
            "codigo": None,
            "detalhes": f"{type(erro).__name__}: {erro}",
            "saudavel": False,
            "divergencias": ["consulta_indisponivel"],
        }
    detalhes = _texto(resultado.stdout or resultado.stderr).strip()
    instalada = resultado.returncode == 0
    if not instalada:
        heartbeat = _heartbeat_agendador_recente(pasta, agora=agora)
        if heartbeat is not None:
            saudavel = _heartbeat_execucao_saudavel(heartbeat)
            divergencias = []
            if not saudavel:
                definicao = heartbeat.get("definicao_tarefa") or {}
                divergencias = list(
                    definicao.get("divergencias") or []
                )
                if (
                    heartbeat.get("versao")
                    != VERSAO_HEARTBEAT_AUTOSTART
                    or not definicao
                ):
                    divergencias.append(
                        "evidencia_definicao_tarefa_ausente"
                    )
                if not divergencias:
                    divergencias.append(
                        "ultima_execucao_nao_recuperou_sistema"
                    )
            return {
                "instalada": True,
                "consultavel": False,
                "codigo": resultado.returncode,
                "detalhes": detalhes,
                "saudavel": saudavel,
                "divergencias": list(dict.fromkeys(divergencias)),
                "origem_evidencia": "execucao_agendada_recente",
                "heartbeat": heartbeat,
            }
    definicao = (
        validar_definicao_xml(
            _texto(resultado.stdout), pasta=pasta, pythonw=pythonw
        )
        if instalada else {
            "saudavel": False,
            "divergencias": ["tarefa_ausente"],
        }
    )
    return {
        "instalada": instalada,
        "consultavel": True,
        "codigo": resultado.returncode,
        "detalhes": detalhes,
        **definicao,
        "origem_evidencia": "consulta_direta" if instalada else None,
    }


def instalar(pasta, executor=None, pythonw=None, usuario=None):
    resultado = _executar(
        comando_instalacao(
            pasta, pythonw=pythonw, usuario=usuario
        ),
        executor=executor,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            (resultado.stderr or resultado.stdout).strip()
            or "Falha ao instalar a tarefa automática"
        )
    ajuste_energia = _executar(
        comando_ajuste_energia(), executor=executor
    )
    if ajuste_energia.returncode != 0:
        # Evita deixar instalada uma definição conhecida como incompleta.
        _executar(comando_remocao(), executor=executor)
        raise RuntimeError(
            (ajuste_energia.stderr or ajuste_energia.stdout).strip()
            or "Falha ao liberar a tarefa para execução na bateria"
        )
    estado = consultar(
        executor=executor, pasta=pasta, pythonw=pythonw
    )
    if not estado["saudavel"]:
        raise RuntimeError(
            "Tarefa criada, mas a definicao nao foi confirmada: "
            + ", ".join(estado["divergencias"])
        )
    return estado


def remover(executor=None):
    if not consultar(executor=executor)["instalada"]:
        return {"instalada": False, "removida": False}
    resultado = _executar(comando_remocao(), executor=executor)
    if resultado.returncode != 0:
        raise RuntimeError(
            (resultado.stderr or resultado.stdout).strip()
            or "Falha ao remover a tarefa automática"
        )
    return {"instalada": False, "removida": True}


def main():
    parser = argparse.ArgumentParser(
        description="Inicialização automática segura do PackBall no Windows"
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--status", action="store_true")
    grupo.add_argument("--instalar", action="store_true")
    grupo.add_argument("--remover", action="store_true")
    argumentos = parser.parse_args()

    if os.name != "nt":
        raise SystemExit("Este utilitário é exclusivo do Windows.")

    if argumentos.instalar:
        estado = instalar(Path(__file__).parent)
        print("Inicialização automática instalada e confirmada.")
    elif argumentos.remover:
        estado = remover()
        print(
            "Inicialização automática removida."
            if estado["removida"]
            else "A tarefa automática já não estava instalada."
        )
    else:
        estado = consultar()
        print(
            "Inicialização automática: instalada"
            if estado["instalada"]
            else "Inicialização automática: não instalada"
        )


if __name__ == "__main__":
    main()
