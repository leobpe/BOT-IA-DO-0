import argparse
import os
import subprocess
import sys
from pathlib import Path

from transferir_projeto import verificar_pacote


PYTHON_MINIMO = (3, 11)


def localizar_edge(ambiente=None):
    ambiente = ambiente or os.environ
    candidatos = []
    for variavel in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        raiz = ambiente.get(variavel)
        if raiz:
            candidatos.append(
                Path(raiz) / "Microsoft" / "Edge" / "Application" /
                "msedge.exe"
            )
    return next((item for item in candidatos if item.is_file()), None)


def diagnosticar_secundario(
    pasta,
    versao_python=None,
    plataforma=None,
    ambiente=None,
    verificar_pacote_fn=None,
):
    pasta = Path(pasta)
    versao_python = tuple(versao_python or sys.version_info[:3])
    plataforma = plataforma or os.name
    verificar_pacote_fn = verificar_pacote_fn or verificar_pacote
    pacote = verificar_pacote_fn(pasta)
    edge = localizar_edge(ambiente)
    windows = plataforma == "nt"
    python_compativel = versao_python[:2] >= PYTHON_MINIMO
    pronto = bool(
        pacote.get("valido")
        and windows
        and python_compativel
        and edge is not None
        and (pasta / "requirements.lock.txt").is_file()
    )
    motivos = []
    if not pacote.get("valido"):
        motivos.append("pacote_transferencia_invalido")
    if not windows:
        motivos.append("windows_obrigatorio")
    if not python_compativel:
        motivos.append("python_incompativel")
    if edge is None:
        motivos.append("microsoft_edge_ausente")
    if not (pasta / "requirements.lock.txt").is_file():
        motivos.append("lock_dependencias_ausente")
    return {
        "pronto": pronto,
        "motivos": motivos,
        "pacote": pacote,
        "windows": windows,
        "python": ".".join(map(str, versao_python)),
        "python_compativel": python_compativel,
        "edge": str(edge) if edge is not None else None,
    }


def _python_venv(pasta):
    nome = "python.exe" if os.name == "nt" else "python"
    subpasta = "Scripts" if os.name == "nt" else "bin"
    return Path(pasta) / ".venv" / subpasta / nome


def instalar_secundario(
    pasta,
    executar_fn=None,
    diagnosticar_fn=None,
):
    pasta = Path(pasta).resolve()
    executar_fn = executar_fn or subprocess.run
    diagnosticar_fn = diagnosticar_fn or diagnosticar_secundario
    diagnostico = diagnosticar_fn(pasta)
    if not diagnostico["pronto"]:
        raise RuntimeError(
            "Instalação recusada: " + ", ".join(diagnostico["motivos"])
        )

    python_venv = _python_venv(pasta)
    comandos = []
    if not python_venv.is_file():
        comandos.append([
            sys.executable, "-m", "venv", str(pasta / ".venv")
        ])
    comandos.extend([
        [str(python_venv), "-m", "pip", "install", "--upgrade", "pip"],
        [
            str(python_venv), "-m", "pip", "install", "-r",
            str(pasta / "requirements.lock.txt"),
        ],
        [str(python_venv), "-m", "playwright", "install", "chromium"],
        [str(python_venv), str(pasta / "preflight_reinicio.py")],
    ])
    executados = []
    for comando in comandos:
        executar_fn(comando, cwd=str(pasta), check=True)
        executados.append(comando)
        if comando[1:4] == ["-m", "venv", str(pasta / ".venv")]:
            if not python_venv.is_file():
                raise RuntimeError("Ambiente virtual não foi criado corretamente.")
    return {
        "estado": "instalado_e_preflight_aprovado",
        "python_venv": str(python_venv),
        "comandos_executados": len(executados),
        "iniciou_bot": False,
        "instalou_autostart": False,
    }


def _formatar_diagnostico(resultado):
    linhas = [
        "Computador secundário: "
        + ("PRONTO PARA INSTALAR" if resultado["pronto"] else "PENDENTE")
    ]
    linhas.append(f"- Pacote íntegro: {resultado['pacote'].get('valido', False)}")
    linhas.append(f"- Windows: {resultado['windows']}")
    linhas.append(
        f"- Python {resultado['python']}: "
        + ("compatível" if resultado["python_compativel"] else "incompatível")
    )
    linhas.append(f"- Microsoft Edge: {resultado['edge'] or 'ausente'}")
    for motivo in resultado["motivos"]:
        linhas.append(f"- Pendência: {motivo}")
    return "\n".join(linhas)


def main():
    parser = argparse.ArgumentParser(
        description="Prepara com segurança o PC secundário do Bot PackBall."
    )
    parser.add_argument(
        "--somente-verificar", action="store_true",
        help="Confere pacote e pré-requisitos sem instalar nada."
    )
    argumentos = parser.parse_args()
    pasta = Path(__file__).parent
    diagnostico = diagnosticar_secundario(pasta)
    print(_formatar_diagnostico(diagnostico))
    if argumentos.somente_verificar:
        raise SystemExit(0 if diagnostico["pronto"] else 1)
    resultado = instalar_secundario(pasta)
    print("Instalação do computador secundário concluída.")
    print("O bot ainda não foi iniciado.")
    print("Próximo passo: .\\.venv\\Scripts\\python.exe iniciar_sistema.py")
    print(f"Estado: {resultado['estado']}")


if __name__ == "__main__":
    main()
