"""Operação manual do grupo de teste do Próximo Gol balanceado."""

import argparse
import json

from controle_proximo_gol_balanceado import ativar, ler_estado, suspender


def executar(acao):
    if acao == "ativar":
        return ativar()
    if acao == "sombra":
        return suspender("manual", "suspensao_manual", automatico=False)
    return ler_estado()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Controla somente o envio do Próximo Gol balanceado."
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--ativar", action="store_true")
    grupo.add_argument("--sombra", action="store_true")
    argumentos = parser.parse_args()
    acao = "ativar" if argumentos.ativar else (
        "sombra" if argumentos.sombra else "listar"
    )
    print(json.dumps(executar(acao), ensure_ascii=False, indent=2))
