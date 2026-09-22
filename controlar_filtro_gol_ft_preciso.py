import argparse
import json

from controle_filtro_gol_ft_preciso import ativar, ler_estado, suspender


def main():
    parser = argparse.ArgumentParser()
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--ativar", action="store_true")
    grupo.add_argument("--suspender", action="store_true")
    argumentos = parser.parse_args()
    if argumentos.ativar:
        estado = ativar()
    elif argumentos.suspender:
        estado = suspender(
            "manual", "suspensao_manual", automatico=False
        )
    else:
        estado = ler_estado()
    print(json.dumps(estado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
