"""Operação manual explícita do circuit breaker de gols antecipados."""

import argparse
import json

from controle_gols_antecipados import (
    ativar_metodo,
    ler_estado,
    suspender_metodo,
)


def executar(acao, metodo=None):
    if acao == "listar":
        return ler_estado()
    if not metodo:
        raise ValueError("informe a versão exata do método")
    if acao == "ativar":
        return ativar_metodo(metodo)
    if acao == "sombra":
        return suspender_metodo(
            metodo,
            "manual",
            "suspensao_manual",
            automatico=False,
        )
    raise ValueError("ação desconhecida")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--listar", action="store_true")
    grupo.add_argument("--ativar", metavar="METODO")
    grupo.add_argument("--sombra", metavar="METODO")
    argumentos = parser.parse_args()
    if argumentos.listar:
        acao, metodo = "listar", None
    elif argumentos.ativar:
        acao, metodo = "ativar", argumentos.ativar
    else:
        acao, metodo = "sombra", argumentos.sombra
    print(json.dumps(
        executar(acao, metodo), ensure_ascii=False, indent=2
    ))
