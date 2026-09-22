"""Fallback temporal API-Live sem sobrescrever observações do PackBall."""

import copy
import os


VERSAO_EXPERIMENTO_FUSAO_TEMPORAL = "fusao-temporal-api-live-grupo-v1"
VERSAO_POLITICA = "fallback-temporal-api-live-v1"


def fusao_temporal_grupo_ativa(env=None):
    env = os.environ if env is None else env
    return env.get("API_LIVE_TEMPORAL_GRUPO_ATIVO", "0") == "1"


def fundir_evolucao_temporal_como_fallback(evolucao_packball, contexto_api):
    """Preenche somente métricas ausentes e bloqueia qualquer conflito atual."""
    contexto_api = contexto_api or {}
    evolucao_api = contexto_api.get("evolucao_temporal_api_live") or {}
    comparacao = contexto_api.get("comparacao_temporal_packball_api") or {}
    itens_comparacao = comparacao.get("comparacoes") or []
    if any(item.get("concordante") is not True for item in itens_comparacao):
        return None, {"valida": False, "motivo": "divergencia_atual"}
    resultado = copy.deepcopy(evolucao_packball or {})
    preenchimentos = []
    for janela in ("5", "10", "15"):
        api = evolucao_api.get(janela)
        if not isinstance(api, dict):
            continue
        packball = resultado.get(janela)
        if not isinstance(packball, dict):
            packball = {}
            resultado[janela] = packball
        for metrica in ("chutes", "escanteios"):
            atual = packball.get(metrica)
            auxiliar = api.get(metrica)
            if atual is None and isinstance(auxiliar, (list, tuple)) and len(auxiliar) == 2:
                packball[metrica] = list(auxiliar)
                preenchimentos.append(f"{janela}.{metrica}")
        for campo in (
            "duracao_real_minutos", "desvio_alvo_minutos",
            "resets_detectados",
        ):
            if packball.get(campo) is None and api.get(campo) is not None:
                packball[campo] = copy.deepcopy(api[campo])
    if not preenchimentos:
        return None, {"valida": False, "motivo": "sem_lacuna_completada"}
    resultado["fusao_temporal_api_live"] = {
        "versao": VERSAO_POLITICA,
        "fonte_primaria": "packball",
        "fonte_fallback": "api_football",
        "preenchimentos": preenchimentos,
        "sobrescreveu_packball": False,
    }
    return resultado, {
        "valida": True,
        "motivo": "fallback_sem_sobrescrita",
        "preenchimentos": preenchimentos,
    }


def gerar_candidatos_fusao_temporal(candidatos_base, candidatos_fusao, diagnostico):
    """Expõe apenas oportunidades novas produzidas pelo fallback temporal."""
    if not (diagnostico or {}).get("valida"):
        return []
    base = {
        item.get("mercado"): item for item in candidatos_base or []
    }
    resultado = []
    for candidato in candidatos_fusao or []:
        if candidato.get("status") != "aprovado":
            continue
        correspondente = base.get(candidato.get("mercado")) or {}
        if correspondente.get("status") == "aprovado":
            continue
        item = copy.deepcopy(candidato)
        item["status"] = "simulacao"
        item.setdefault("motivos", []).append(
            "janela_temporal_api_live_completou_packball"
        )
        features = item.setdefault("features", {})
        features["exploracao_sombra"] = {
            "versao": VERSAO_EXPERIMENTO_FUSAO_TEMPORAL,
            "aplicacao_automatica": False,
            "telegram_oficial": False,
            "grupo_teste": fusao_temporal_grupo_ativa(),
        }
        features["fusao_temporal_api_live"] = {
            **dict(diagnostico),
            "versao": VERSAO_POLITICA,
            "sobrescreveu_packball": False,
        }
        resultado.append(item)
    return resultado
