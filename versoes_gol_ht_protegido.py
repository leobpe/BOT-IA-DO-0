"""Versão isolada da quarentena prospectiva da política principal de Gol HT."""

import os


VERSAO_GOL_HT_PROTEGIDO = (
    "sinais-v8c-gol-ht-principal-sombra-prospectiva-100"
)


def gol_ht_principal_oficial_ativo(environ=None):
    ambiente = os.environ if environ is None else environ
    return str(
        ambiente.get("GOL_HT_PRINCIPAL_OFICIAL_ATIVO", "0")
    ).strip().casefold() in {"1", "true", "sim", "yes", "on"}

