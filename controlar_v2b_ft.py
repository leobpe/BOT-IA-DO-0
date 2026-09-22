import argparse
import json

from controle_v2b_ft import (
    ativar_v2b_ft,
    ler_estado_v2b_ft,
    suspender_v2b_ft,
)


def main():
    parser = argparse.ArgumentParser(
        description="Controla somente o envio do método V2b FT."
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--ativar", action="store_true")
    grupo.add_argument("--sombra", action="store_true")
    argumentos = parser.parse_args()
    if argumentos.ativar:
        estado = ativar_v2b_ft()
    elif argumentos.sombra:
        estado = suspender_v2b_ft(
            "manual",
            "suspensao_manual",
            automatico=False,
        )
    else:
        estado = ler_estado_v2b_ft()
    print(json.dumps(estado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
