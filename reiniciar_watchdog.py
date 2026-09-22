"""Reinicia somente o watchdog, preservando monitor e navegador PackBall."""

import argparse
import os
import time
from datetime import datetime
from pathlib import Path

from processo_monitor import (
    ARQUIVOS_RUNTIME_WATCHDOG,
    estado_codigo_runtime,
    gravar_json_atomico,
    iniciar_watchdog,
    ler_estado,
    pid_ativo,
    trava_em_uso,
)


PASTA = Path(__file__).parent
ARQUIVO_PEDIDO = PASTA / "watchdog_reinicio.json"


def _watchdog_novo_comprovado(
    pasta, estado, pid_anterior, verificar_pid, verificar_trava,
):
    try:
        pid = int((estado or {}).get("pid") or 0)
    except (TypeError, ValueError):
        return None
    if pid <= 0 or pid == int(pid_anterior):
        return None
    if (
        (estado or {}).get("status") != "ativo"
        or not verificar_pid(pid)
        or not verificar_trava(Path(pasta) / "watchdog_instancia.lock")
        or estado_codigo_runtime(
            pasta, estado, ARQUIVOS_RUNTIME_WATCHDOG
        ) != "atualizado"
    ):
        return None
    return pid


def _monitor_preservado(
    pasta, pid_anterior, ler_estado_fn, verificar_pid, verificar_trava,
):
    if pid_anterior is None:
        return False
    estado = ler_estado_fn(Path(pasta) / "monitor_processo.json")
    try:
        pid_atual = int(estado.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    return bool(
        estado.get("status") == "ativo"
        and pid_atual == int(pid_anterior)
        and verificar_pid(pid_atual)
        and verificar_trava(Path(pasta) / "monitor_instancia.lock")
    )


def reiniciar_watchdog_isolado(
    pasta=PASTA,
    timeout_segundos=120,
    forcar=False,
    iniciar_fn=None,
    ler_estado_fn=None,
    verificar_pid=None,
    verificar_trava=None,
    relogio=None,
    dormir=None,
):
    """Faz handoff cooperativo do watchdog sem encerrar outros processos."""
    pasta = Path(pasta)
    iniciar_fn = iniciar_fn or iniciar_watchdog
    ler_estado_fn = ler_estado_fn or ler_estado
    verificar_pid = verificar_pid or pid_ativo
    verificar_trava = verificar_trava or trava_em_uso
    relogio = relogio or time.monotonic
    dormir = dormir or time.sleep
    caminho_estado = pasta / "watchdog_processo.json"
    caminho_trava = pasta / "watchdog_instancia.lock"
    caminho_pedido = pasta / "watchdog_reinicio.json"
    estado_anterior = ler_estado_fn(caminho_estado)
    pid_anterior = estado_anterior.get("pid")
    pid_monitor_anterior = ler_estado_fn(
        pasta / "monitor_processo.json"
    ).get("pid")

    if not verificar_pid(pid_anterior) or not verificar_trava(caminho_trava):
        raise RuntimeError(
            "Watchdog ativo não comprovado simultaneamente por PID e trava."
        )
    codigo = estado_codigo_runtime(
        pasta, estado_anterior, ARQUIVOS_RUNTIME_WATCHDOG
    )
    if codigo == "atualizado" and not forcar:
        return {
            "estado": "ja_atualizado",
            "pid": int(pid_anterior),
            "monitor_preservado": _monitor_preservado(
                pasta, pid_monitor_anterior, ler_estado_fn,
                verificar_pid, verificar_trava,
            ),
        }

    pedido = {
        "estado": "solicitado",
        "pid_alvo": int(pid_anterior),
        "solicitado_em": datetime.now().replace(microsecond=0).isoformat(),
        "solicitante_pid": os.getpid(),
    }
    gravar_json_atomico(caminho_pedido, pedido)
    limite = relogio() + max(float(timeout_segundos), 1.0)
    try:
        while relogio() < limite:
            adotado = _watchdog_novo_comprovado(
                pasta,
                ler_estado_fn(caminho_estado),
                pid_anterior,
                verificar_pid,
                verificar_trava,
            )
            if adotado is not None:
                return {
                    "estado": "reiniciado",
                    "origem": "supervisor",
                    "pid_anterior": int(pid_anterior),
                    "pid": adotado,
                    "codigo": "atualizado",
                    "monitor_preservado": _monitor_preservado(
                        pasta, pid_monitor_anterior, ler_estado_fn,
                        verificar_pid, verificar_trava,
                    ),
                }
            if (
                not verificar_pid(pid_anterior)
                and not verificar_trava(caminho_trava)
            ):
                break
            dormir(0.25)
        else:
            raise TimeoutError(
                "Watchdog antigo não encerrou nem liberou a trava no prazo."
            )
    finally:
        caminho_pedido.unlink(missing_ok=True)

    adotado = _watchdog_novo_comprovado(
        pasta,
        ler_estado_fn(caminho_estado),
        pid_anterior,
        verificar_pid,
        verificar_trava,
    )
    if adotado is not None:
        return {
            "estado": "reiniciado",
            "origem": "supervisor",
            "pid_anterior": int(pid_anterior),
            "pid": adotado,
            "codigo": "atualizado",
            "monitor_preservado": _monitor_preservado(
                pasta, pid_monitor_anterior, ler_estado_fn,
                verificar_pid, verificar_trava,
            ),
        }

    novo_pid = int(iniciar_fn(pasta))
    limite = relogio() + max(float(timeout_segundos), 1.0)
    ultimo = {}
    while relogio() < limite:
        ultimo = ler_estado_fn(caminho_estado)
        pid_comprovado = _watchdog_novo_comprovado(
            pasta,
            ultimo,
            pid_anterior,
            verificar_pid,
            verificar_trava,
        )
        if pid_comprovado is not None:
            return {
                "estado": "reiniciado",
                "origem": (
                    "comando" if pid_comprovado == novo_pid
                    else "supervisor"
                ),
                "pid_anterior": int(pid_anterior),
                "pid": pid_comprovado,
                "codigo": "atualizado",
                "monitor_preservado": _monitor_preservado(
                    pasta, pid_monitor_anterior, ler_estado_fn,
                    verificar_pid, verificar_trava,
                ),
            }
        dormir(0.25)
    raise TimeoutError(
        "Novo watchdog não comprovou PID, trava e código atualizado no prazo."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--forcar", action="store_true")
    parser.add_argument("--timeout", type=float, default=120)
    argumentos = parser.parse_args()
    resultado = reiniciar_watchdog_isolado(
        timeout_segundos=argumentos.timeout,
        forcar=argumentos.forcar,
    )
    if resultado["estado"] == "ja_atualizado":
        print(
            "Watchdog já utiliza o código atual; monitor e navegador foram "
            "preservados."
        )
    elif resultado.get("monitor_preservado"):
        print(
            "Watchdog reiniciado isoladamente; monitor, navegador e pré-live "
            "permaneceram ativos."
        )
    else:
        print(
            "Watchdog reiniciado, mas a preservação do monitor não pôde ser "
            "comprovada."
        )
    print(f"PID watchdog: {resultado['pid']}")


if __name__ == "__main__":
    main()
