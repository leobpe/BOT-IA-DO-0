"""Controle manual explicito do envio pre-live preciso."""

import argparse
import json

from controle_pre_live_preciso import ativar, ler_estado, suspender


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--ativar", action="store_true")
    grupo.add_argument("--suspender", action="store_true")
    grupo.add_argument("--status", action="store_true")
    argumentos = parser.parse_args()
    if argumentos.ativar:
        resultado = ativar()
    elif argumentos.suspender:
        resultado = suspender(
            "suspensao_manual",
            "suspensao_manual",
            automatico=False,
        )
    else:
        resultado = ler_estado()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
