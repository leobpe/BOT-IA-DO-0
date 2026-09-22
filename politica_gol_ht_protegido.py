"""Quarentena reversível da política principal de Gol HT.

Os métodos HT independentes conservam suas próprias regras. Esta política
atua somente sobre a V8b principal, preserva sua observação em sombra e cria
uma V8c prospectiva que não chega ao Telegram por padrão.
"""

from copy import deepcopy

from versoes_gol_ht_protegido import (
    VERSAO_GOL_HT_PROTEGIDO,
    gol_ht_principal_oficial_ativo,
)
from versoes_operacionais import VERSAO_GOL_HT_MAX_28


MERCADO = "gol_ht"
MOTIVO_BASE_SOMBRA = "gol_ht_v8b_preservado_em_sombra"


def aplicar_politica_gol_ht_protegido(candidatos, environ=None):
    oficial_ativo = gol_ht_principal_oficial_ativo(environ)
    diagnostico = {
        "ativa": True,
        "oficial_ativo": oficial_ativo,
        "avaliados": 0,
        "elegiveis": 0,
        "oficiais": 0,
        "v8b_sombra": 0,
        "v8c_sombra": 0,
        "versao": VERSAO_GOL_HT_PROTEGIDO,
        "reativacao_oficial": "GOL_HT_PRINCIPAL_OFICIAL_ATIVO=1",
        "promocao_automatica": False,
    }
    novos = []
    for candidato in list(candidatos or []):
        if not (
            candidato.get("mercado") == MERCADO
            and candidato.get("regra_versao") == VERSAO_GOL_HT_MAX_28
            and candidato.get("status") == "aprovado"
        ):
            continue
        diagnostico["avaliados"] += 1
        diagnostico["elegiveis"] += 1
        candidato["status"] = "simulacao"
        motivos_base = list(candidato.get("motivos") or [])
        motivos_base.append(MOTIVO_BASE_SOMBRA)
        candidato["motivos"] = list(dict.fromkeys(motivos_base))
        candidato.setdefault("features", {})[
            "gol_ht_principal_sombra"
        ] = {
            "derivada_para": VERSAO_GOL_HT_PROTEGIDO,
            "motivo": "vantagem_historica_nao_comprovada",
            "telegram": False,
        }
        diagnostico["v8b_sombra"] += 1

        protegido = deepcopy(candidato)
        protegido["regra_versao"] = VERSAO_GOL_HT_PROTEGIDO
        protegido["status"] = (
            "aprovado" if oficial_ativo else "simulacao"
        )
        protegido.pop("_status_persistido", None)
        features = protegido.setdefault("features", {})
        features.pop("gol_ht_principal_sombra", None)
        features["gol_ht_protegido"] = {
            "versao": VERSAO_GOL_HT_PROTEGIDO,
            "derivada_de": VERSAO_GOL_HT_MAX_28,
            "modo": "oficial" if oficial_ativo else "validacao_sombra",
            "telegram": oficial_ativo,
            "promocao_automatica": False,
        }
        motivos = [
            motivo for motivo in protegido.get("motivos") or []
            if motivo != MOTIVO_BASE_SOMBRA
        ]
        motivos.extend((
            (
                "gol_ht_principal_oficial_revisao_manual"
                if oficial_ativo
                else "gol_ht_principal_validacao_sombra"
            ),
            "vantagem_historica_nao_comprovada",
        ))
        if not oficial_ativo:
            motivos.append("nao_enviar_telegram_sem_vantagem_comprovada")
        protegido["motivos"] = list(dict.fromkeys(motivos))
        novos.append(protegido)
        if oficial_ativo:
            diagnostico["oficiais"] += 1
        else:
            diagnostico["v8c_sombra"] += 1
    candidatos.extend(novos)
    return diagnostico

