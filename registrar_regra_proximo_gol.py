"""Registra de forma idempotente a nova coorte prospectiva de próximo gol."""

import json
from pathlib import Path

from banco import BancoMonitor
from linhagem_regras import (
    registrar_inicio_linhagem_sinais,
    registrar_ou_validar_linhagem_regra,
)
from motor_sinais import VERSAO_FEATURES
from pontuacao_contexto_sombra import (
    registrar_modelos_pontuacao_contexto_sombra,
)
from pontuacao_longa_sombra import registrar_estudos_pontuacao_longa
from pontuacao_sombra import registrar_modelos_pontuacao_sombra
from versoes_challengers_preciso import VERSAO_PROXIMO_GOL_FILTRO_PRECISO


def registrar(pasta=None):
    pasta = Path(pasta or Path(__file__).parent).resolve()
    banco = BancoMonitor(pasta / "monitor_packball.db")
    regra = VERSAO_PROXIMO_GOL_FILTRO_PRECISO
    regras = {"proximo_gol": regra}
    try:
        with banco.conexao:
            linhagem = registrar_ou_validar_linhagem_regra(
                banco.conexao, pasta, regra, VERSAO_FEATURES
            )
            cobertura = registrar_inicio_linhagem_sinais(
                banco.conexao, regra, linhagem["fingerprint_atual"]
            )
            temporal = registrar_modelos_pontuacao_sombra(
                banco.conexao, regras
            )
            contexto = registrar_modelos_pontuacao_contexto_sombra(
                banco.conexao, regras
            )
            longa = registrar_estudos_pontuacao_longa(
                banco.conexao, regras
            )
        return {
            "regra_versao": regra,
            "fingerprint": linhagem["fingerprint_atual"],
            "linhagem_estado": linhagem["estado"],
            "marco_sinais": cobertura.get("marco_presente"),
            "sinais_existentes": cobertura.get("total"),
            "modelo_temporal_integro": temporal.get("integro"),
            "modelo_contexto_integro": contexto.get("integro"),
            "modelo_longo_integro": longa.get("integro"),
        }
    finally:
        banco.fechar()


def main():
    print(json.dumps(registrar(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
