"""Leitura do estado de calibracao usada pelo watchdog.

Resume o estado de cada modelo, classifica o frescor das calibracoes e
acompanha a continuidade da populacao por mercado entre ciclos. Sao funcoes
puras de leitura: nao gravam estado nem enviam alerta.

Extraido de watchdog.py, que reexporta estes nomes.
"""

from datetime import datetime
from motor_sinais import VERSAO_REGRAS
from watchdog_resumo_diario import MERCADOS_VALIDACAO

TOLERANCIA_RECONCILIACAO_CALIBRACAO_SEGUNDOS = 300


def _resumir_estado_calibracao(item, modelo):
    discriminacao = modelo.get("discriminacao_pontuacao") or {}
    celulas = modelo.get("validacao_por_faixa") or {}
    prospectiva = modelo.get("validacao_prospectiva_expandida") or {}
    discriminacao_prospectiva = (
        prospectiva.get("discriminacao_pontuacao") or {}
    )
    return {
        "ativa": bool(item["ativa"]),
        "amostra": int(item["amostra"] or 0),
        "motivo": modelo.get("motivo"),
        "atualizado_em": item["atualizado_em"],
        "amostra_validacao": int(
            modelo.get("amostra_validacao", 0) or 0
        ),
        "roi_validacao_agregado": modelo.get(
            "roi_validacao_agregado"
        ),
        "auc_validacao": discriminacao.get("auc"),
        "limite_inferior_auc_95": discriminacao.get(
            "limite_inferior_auc_95"
        ),
        "erro_calibracao": modelo.get("erro_calibracao"),
        "celulas_aprovadas": sum(
            bool(valor.get("aprovada"))
            for valor in celulas.values()
            if isinstance(valor, dict)
        ),
        "celulas_avaliadas": len(celulas),
        "validacao_prospectiva": {
            "estado": prospectiva.get("estado"),
            "motivo": prospectiva.get("motivo"),
            "motivos": list(prospectiva.get("motivos") or ()),
            "amostra_avaliada": int(
                prospectiva.get("amostra_avaliada", 0) or 0
            ),
            "amostra_validacao": int(
                prospectiva.get("amostra_validacao", 0) or 0
            ),
            "resultados_apos_holdout_original": int(
                prospectiva.get(
                    "resultados_apos_holdout_original", 0
                ) or 0
            ),
            "roi_validacao_agregado": prospectiva.get(
                "roi_validacao_agregado"
            ),
            "auc_validacao": discriminacao_prospectiva.get("auc"),
            "limite_inferior_auc_95": (
                discriminacao_prospectiva.get(
                    "limite_inferior_auc_95"
                )
            ),
            "validacao_coberta": int(
                prospectiva.get("validacao_coberta", 0) or 0
            ),
            "validacao_aprovada": int(
                prospectiva.get("validacao_aprovada", 0) or 0
            ),
            "celulas_avaliadas": int(
                prospectiva.get("celulas_avaliadas", 0) or 0
            ),
            "celulas_aprovadas": int(
                prospectiva.get("celulas_aprovadas", 0) or 0
            ),
            "habilita_sinal_oficial": bool(
                prospectiva.get("habilita_sinal_oficial", False)
            ),
            "promocao_automatica": bool(
                prospectiva.get("promocao_automatica", False)
            ),
        },
    }

def _classificar_frescor_calibracoes(
    frescor, agora, estado_coleta=None,
    tolerancia_segundos=TOLERANCIA_RECONCILIACAO_CALIBRACAO_SEGUNDOS,
):
    """Separa atraso persistente da janela normal de reconciliação.

    Uma calibração inativa não participa de sinais oficiais. Quando ela fica
    um resultado atrás, concedemos a mesma janela curta de reconciliação mesmo
    entre ciclos; isso evita alertar o operador por um estado transitório que o
    monitor corrigirá na próxima passagem. Calibrações ativas continuam
    toleradas somente enquanto um ciclo está comprovadamente em andamento.
    """
    resultado = dict(frescor or {})
    ciclo_em_andamento = bool(
        (estado_coleta or {}).get("ciclo_em_andamento")
    )
    detalhes = list(resultado.get("detalhes") or [])
    reconciliando = []
    alertaveis = []
    for item in detalhes:
        if not item.get("desatualizada"):
            continue
        recente = False
        try:
            instante = datetime.fromisoformat(
                item.get("ultimo_resultado_em")
            )
            referencia = agora
            if instante.tzinfo is not None and referencia.tzinfo is None:
                instante = instante.replace(tzinfo=None)
            elif instante.tzinfo is None and referencia.tzinfo is not None:
                referencia = referencia.replace(tzinfo=None)
            idade = (referencia - instante).total_seconds()
            recente = 0 <= idade <= float(tolerancia_segundos)
        except (TypeError, ValueError):
            recente = False
        em_janela_reconciliacao = bool(
            recente
            and (
                ciclo_em_andamento
                or not bool(item.get("ativa"))
            )
        )
        (
            reconciliando
            if em_janela_reconciliacao
            else alertaveis
        ).append(item)

    # Auditorias simuladas/legadas sem detalhes continuam falhando fechado.
    total_desatualizadas = int(resultado.get("desatualizadas", 0) or 0)
    sem_detalhe = max(
        total_desatualizadas - len(reconciliando) - len(alertaveis),
        0,
    )
    alertaveis_ativas = sum(
        bool(item.get("ativa")) for item in alertaveis
    )
    alertaveis_inativas = len(alertaveis) - alertaveis_ativas
    if sem_detalhe:
        alertaveis_ativas += int(
            resultado.get("desatualizadas_ativas", sem_detalhe) or 0
        )
        alertaveis_inativas += int(
            resultado.get("desatualizadas_inativas", 0) or 0
        )
    resultado["reconciliacao_em_andamento"] = len(reconciliando)
    resultado["mercados_em_reconciliacao"] = [
        item.get("mercado") for item in reconciliando
    ]
    resultado["desatualizadas_alertaveis"] = (
        alertaveis_ativas + alertaveis_inativas
    )
    resultado["desatualizadas_ativas_alertaveis"] = alertaveis_ativas
    resultado["desatualizadas_inativas_alertaveis"] = alertaveis_inativas
    resultado["tolerancia_reconciliacao_segundos"] = int(
        tolerancia_segundos
    )
    return resultado

def _normalizar_id_populacao_calibracao(valor):
    """Remove somente a política estatística de IDs legados."""
    if not valor:
        return None
    partes = str(valor).split("|")
    if (
        len(partes) >= 4
        and partes[1].startswith("calibracao-")
    ):
        return "|".join((partes[0], *partes[2:]))
    return str(valor)

def _ids_populacao_por_mercado(validacao):
    explicitos = dict(
        validacao.get("amostra_populacao_id_por_mercado") or {}
    )
    regra_padrao = validacao.get("regra_versao") or VERSAO_REGRAS
    global_id = (
        validacao.get("amostra_populacao_id")
        or _normalizar_id_populacao_calibracao(
            validacao.get("amostra_oficial_id")
        )
        or regra_padrao
    )
    regras = validacao.get("regra_versoes_por_mercado") or {}
    return {
        mercado: (
            explicitos.get(mercado)
            or regras.get(mercado)
            or global_id
        )
        for mercado in MERCADOS_VALIDACAO
    }

def _continuidade_populacao_por_mercado(
    validacao, anterior, sufixo
):
    atuais = _ids_populacao_por_mercado(validacao)
    anteriores = dict(
        anterior.get(
            f"amostra_populacao_id_por_mercado_{sufixo}"
        ) or {}
    )
    if not anteriores:
        legado = (
            anterior.get(f"amostra_populacao_id_{sufixo}")
            or _normalizar_id_populacao_calibracao(
                anterior.get(f"amostra_oficial_id_{sufixo}")
            )
            or anterior.get(f"regra_versao_{sufixo}")
        )
        anteriores = {
            mercado: legado for mercado in MERCADOS_VALIDACAO
        }
    continuidade = {
        mercado: bool(
            anteriores.get(mercado)
            and _normalizar_id_populacao_calibracao(
                anteriores.get(mercado)
            )
            == _normalizar_id_populacao_calibracao(
                atuais.get(mercado)
            )
        )
        for mercado in MERCADOS_VALIDACAO
    }
    return atuais, continuidade
