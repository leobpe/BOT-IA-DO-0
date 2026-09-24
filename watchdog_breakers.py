"""Aplicacao dos circuit breakers das politicas do watchdog.

Cada funcao le a validacao prospectiva de uma politica, consulta o controle
operacional correspondente e devolve o estado com a suspensao ja aplicada.
Nenhuma delas envia alerta: a notificacao de cada suspensao continua em
watchdog.py, junto de enviar_alerta.

Extraido de watchdog.py, que reexporta estes nomes.
"""

from controle_escanteios_ft_asiatico import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_ESCANTEIOS_FT_ASIATICO,
    aplicar_validacao as aplicar_controle_escanteios_ft_asiatico,
)
from controle_filtro_gol_ft_preciso import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_FILTRO_GOL_FT_PRECISO,
    aplicar_validacao as aplicar_controle_filtro_gol_ft_preciso,
)
from controle_filtro_gol_ht_preciso import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_FILTRO_GOL_HT_PRECISO,
    aplicar_validacao as aplicar_controle_filtro_gol_ht_preciso,
)
from controle_gols_antecipados import (
    ler_estado as ler_estado_gols_antecipados,
    metodo_liberado as metodo_gol_antecipado_liberado,
    suspender_metodo as suspender_metodo_gol_antecipado,
)
from controle_proximo_gol_balanceado import (
    ARQUIVO_ESTADO as ARQUIVO_ESTADO_PROXIMO_GOL_BALANCEADO,
    ler_estado as ler_estado_proximo_gol_balanceado,
    suspender as suspender_proximo_gol_balanceado,
)
from controle_v2b_ft import (
    ler_estado_v2b_ft,
    suspender_v2b_ft,
)
from pathlib import Path


PASTA = Path(__file__).parent
ARQUIVO_ESTADO_V2B_FT = PASTA / "v2b_ft_estado.json"
ARQUIVO_ESTADO_GOLS_ANTECIPADOS = (
    PASTA / "gols_antecipados_estado.json"
)


def aplicar_circuit_breaker_proximo_gol_balanceado(
    validacao, caminho_estado=None, agora=None
):
    """Pausa só o grupo do balanceado; a coorte sombra segue intacta."""
    caminho_estado = (
        caminho_estado or ARQUIVO_ESTADO_PROXIMO_GOL_BALANCEADO
    )
    progresso = (
        validacao.get("progresso_proximo_gol_balanceado_sombra") or {}
    )
    estado = ler_estado_proximo_gol_balanceado(caminho_estado)
    evidencia_negativa = bool(progresso.get("rollback_recomendado"))
    coorte_concluida = bool(progresso.get("resultados_completos"))
    if (evidencia_negativa or coorte_concluida) and estado.get("ativo"):
        assinatura = "|".join((
            str(progresso.get("versao") or "sem_validacao"),
            str(progresso.get("registrado_em") or "sem_ancora"),
            str(progresso.get("definicao_sha256") or "sem_definicao"),
        ))
        motivo = (
            "ic95_roi_checkpoint_20_integralmente_negativo"
            if evidencia_negativa
            else "coorte_40_concluida_aguardando_revisao_manual"
        )
        estado = suspender_proximo_gol_balanceado(
            assinatura,
            motivo,
            metricas={
                "validos": int(progresso.get("validos", 0) or 0),
                "greens": int(progresso.get("greens", 0) or 0),
                "reds": int(progresso.get("reds", 0) or 0),
                "roi": progresso.get("roi"),
                "intervalo_roi_95": progresso.get("intervalo_roi_95"),
                "checkpoint_seguranca": progresso.get(
                    "checkpoint_seguranca"
                ),
                "coorte_concluida": coorte_concluida,
                "coleta_sombra_continua": True,
            },
            caminho=caminho_estado,
            agora=agora,
            automatico=True,
        )
    validacao["controle_operacional_proximo_gol_balanceado"] = estado
    progresso["grupo_liberado"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        validacao.setdefault("motivos", []).append(
            "controle_proximo_gol_balanceado_inconsistente"
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao

def aplicar_circuit_breaker_grupo_gol_ft_capacidade_v2(
    validacao, caminho_estado=None, agora=None
):
    """Suspende apenas o V2b FT quando o IC95 do ROI é todo negativo."""
    caminho_estado = caminho_estado or ARQUIVO_ESTADO_V2B_FT
    progresso = (
        validacao.get("progresso_grupo_gol_ft_capacidade_v2") or {}
    )
    estado = ler_estado_v2b_ft(caminho_estado)
    if progresso.get("rollback_recomendado") and estado.get("ativo"):
        assinatura = "|".join((
            str(progresso.get("versao") or "sem_versao"),
            str(progresso.get("registrado_em") or "sem_ancora"),
        ))
        estado = suspender_v2b_ft(
            assinatura,
            "ic95_roi_integralmente_negativo",
            metricas={
                "validos": int(progresso.get("validos", 0) or 0),
                "greens": int(progresso.get("greens", 0) or 0),
                "reds": int(progresso.get("reds", 0) or 0),
                "roi": progresso.get("roi"),
                "intervalo_roi_95": progresso.get("intervalo_roi_95"),
            },
            caminho=caminho_estado,
            agora=agora,
            automatico=True,
        )
    validacao["controle_operacional_v2b_ft"] = estado
    progresso["grupo_ativo"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        validacao.setdefault("motivos", []).append(
            "controle_v2b_ft_inconsistente"
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao

def aplicar_circuit_breaker_filtro_gol_ft_preciso(
    validacao, caminho_estado=None, agora=None
):
    """Pausa somente a entrega do FT antecipado que passou no filtro V2."""
    caminho_estado = (
        caminho_estado or ARQUIVO_ESTADO_FILTRO_GOL_FT_PRECISO
    )
    progresso = validacao.get("progresso_filtro_gol_ft_preciso") or {}
    estado = aplicar_controle_filtro_gol_ft_preciso(
        progresso,
        caminho=caminho_estado,
        agora=agora,
    )
    validacao["controle_operacional_filtro_gol_ft_preciso"] = estado
    progresso["grupo_liberado"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "assinatura": estado.get("assinatura"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        motivo = "controle_filtro_gol_ft_preciso_inconsistente"
        if motivo not in validacao.setdefault("motivos", []):
            validacao["motivos"].append(motivo)
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao

def aplicar_circuit_breaker_escanteios_ft_asiatico(
    validacao, caminho_estado=None, agora=None
):
    """Pausa somente a entrega do escanteio asiatico FT validado."""
    caminho_estado = (
        caminho_estado or ARQUIVO_ESTADO_ESCANTEIOS_FT_ASIATICO
    )
    progresso = validacao.get("progresso_escanteios_ft_asiatico") or {}
    estado = aplicar_controle_escanteios_ft_asiatico(
        progresso,
        caminho=caminho_estado,
        agora=agora,
    )
    validacao["controle_operacional_escanteios_ft_asiatico"] = estado
    progresso["grupo_liberado"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "assinatura": estado.get("assinatura"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        motivo = "controle_escanteios_ft_asiatico_inconsistente"
        if motivo not in validacao.setdefault("motivos", []):
            validacao["motivos"].append(motivo)
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao

def aplicar_circuit_breaker_filtro_gol_ht_preciso(
    validacao, caminho_estado=None, agora=None
):
    """Pausa somente a entrega do HT antecipado que passou no filtro."""
    caminho_estado = (
        caminho_estado or ARQUIVO_ESTADO_FILTRO_GOL_HT_PRECISO
    )
    progresso = validacao.get("progresso_filtro_gol_ht_preciso") or {}
    estado = aplicar_controle_filtro_gol_ht_preciso(
        progresso,
        caminho=caminho_estado,
        agora=agora,
    )
    validacao["controle_operacional_filtro_gol_ht_preciso"] = estado
    progresso["grupo_liberado"] = bool(
        estado.get("saudavel") and estado.get("ativo")
    )
    progresso["circuit_breaker"] = {
        "versao": estado.get("versao"),
        "estado": estado.get("estado"),
        "ativo": estado.get("ativo"),
        "motivo": estado.get("motivo"),
        "assinatura": estado.get("assinatura"),
        "atualizado_em": estado.get("atualizado_em"),
        "reativacao": estado.get("reativacao"),
    }
    if not estado.get("saudavel"):
        motivo = "controle_filtro_gol_ht_preciso_inconsistente"
        if motivo not in validacao.setdefault("motivos", []):
            validacao["motivos"].append(motivo)
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao

def aplicar_circuit_breaker_gols_antecipados(
    validacao, caminho_estado=None, agora=None
):
    """Suspende somente o braço com coorte prospectiva comprovadamente ruim."""
    caminho_estado = caminho_estado or ARQUIVO_ESTADO_GOLS_ANTECIPADOS
    progresso = validacao.get("progresso_gols_antecipados") or {}
    estado = ler_estado_gols_antecipados(caminho_estado)
    suspensos = []
    if estado.get("saudavel"):
        for versao, item in sorted(
            (progresso.get("por_braco") or {}).items()
        ):
            intervalo = item.get("intervalo_roi_95")
            evidencia_forte = bool(
                item.get("decisao_estatistica") == "evidencia_desfavoravel"
                and int(item.get("validos", 0) or 0) >= 95
                and isinstance(intervalo, (list, tuple))
                and len(intervalo) == 2
                and intervalo[1] is not None
                and float(intervalo[1]) < 0
                and item.get("linhagem_homogenea") is True
            )
            if not evidencia_forte or not metodo_gol_antecipado_liberado(
                versao, caminho_estado
            ):
                continue
            assinatura = "|".join((
                str(progresso.get("versao") or "sem_validacao"),
                str(progresso.get("registrado_em") or "sem_ancora"),
                str(progresso.get("linhagem_sha256") or "sem_linhagem"),
                str(versao),
            ))
            estado = suspender_metodo_gol_antecipado(
                versao,
                assinatura,
                "ic95_roi_integralmente_negativo",
                metricas={
                    "validos": int(item.get("validos", 0) or 0),
                    "greens": int(item.get("greens", 0) or 0),
                    "reds": int(item.get("reds", 0) or 0),
                    "roi": item.get("roi"),
                    "intervalo_roi_95": intervalo,
                    "decisao_estatistica": item.get(
                        "decisao_estatistica"
                    ),
                },
                caminho=caminho_estado,
                agora=agora,
                automatico=True,
            )
            if estado.get("alterado"):
                suspensos.append(versao)
    validacao["controle_operacional_gols_antecipados"] = {
        **estado,
        "suspensos_neste_ciclo": suspensos,
    }
    metodos_estado = estado.get("metodos") or {}
    for versao, item in (progresso.get("por_braco") or {}).items():
        controle = metodos_estado.get(versao) or {}
        item["grupo_liberado"] = bool(
            estado.get("saudavel") and controle.get("ativo", True)
        )
        item["circuit_breaker"] = {
            "ativo": controle.get("ativo", True),
            "estado": controle.get("estado", "ativo_padrao"),
            "motivo": controle.get("motivo"),
            "atualizado_em": controle.get("atualizado_em"),
        }
    if not estado.get("saudavel"):
        validacao.setdefault("motivos", []).append(
            "controle_gols_antecipados_inconsistente"
        )
        validacao["saudavel"] = False
        validacao["requer_atencao"] = True
    return validacao
