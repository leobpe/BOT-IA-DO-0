"""Observabilidade do funil de gols antecipados, sem decidir candidatos."""

from configuracao import odd_elegivel, obter_limites_risco
from gols_antecipados import (
    MINIMO_EVIDENCIAS_LIVE,
    MINIMO_EVIDENCIAS_PRE,
    MINUTO_MAXIMO_FT,
    MINUTO_MAXIMO_HT,
    MINUTO_MAXIMO_2T,
    MINUTO_MINIMO,
    MINUTO_MINIMO_2T,
    QUALIDADE_MINIMA,
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
    VERSAO_GOL_HT_ANTECIPADO,
    VERSAO_POLITICA,
    _BLOQUEIOS_RELAXAVEIS,
    _evidencias_live,
    _evidencias_pre_jogo,
    _padrao_gols_primeiro_tempo,
    _padrao_gols_segundo_tempo,
)
from qualidade_dados import extrair_minuto, extrair_placar


def _registrar(diagnostico, braco, estado, motivo=None, **detalhes):
    registro = {"estado": estado}
    if motivo:
        registro["motivo"] = motivo
    registro.update({
        chave: valor for chave, valor in detalhes.items()
        if valor is not None
    })
    diagnostico["por_braco"][braco] = registro


def _versoes_geradas(gerados):
    return {
        ((item.get("features") or {}).get("exploracao_sombra") or {}).get(
            "versao"
        )
        for item in gerados or []
    }


def diagnosticar_gols_antecipados(
    jogo, candidatos, contexto_pre_jogo, qualidade, gerados
):
    """Explica a primeira barreira do gerador sem participar da decisão."""
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    try:
        nota = float((qualidade or {}).get("pontuacao") or 0)
    except (TypeError, ValueError):
        nota = 0.0
    diagnostico = {
        "versao": "diagnostico-gols-antecipados-v1",
        "politica_observada": VERSAO_POLITICA,
        "minuto": minuto,
        "placar": placar,
        "qualidade": nota,
        "somente_observabilidade": True,
        "por_braco": {},
    }
    if placar is None:
        _registrar(diagnostico, "global", "bloqueado", "placar_indisponivel")
        return diagnostico
    if minuto is None:
        _registrar(diagnostico, "global", "bloqueado", "minuto_indisponivel")
        return diagnostico
    janela_1t = MINUTO_MINIMO <= minuto <= max(
        MINUTO_MAXIMO_HT, MINUTO_MAXIMO_FT
    )
    janela_2t = MINUTO_MINIMO_2T <= minuto <= MINUTO_MAXIMO_2T
    if not (janela_1t or janela_2t):
        _registrar(
            diagnostico, "global", "bloqueado", "fora_janelas_operacionais"
        )
        return diagnostico
    if nota < QUALIDADE_MINIMA:
        _registrar(
            diagnostico, "global", "bloqueado", "qualidade_insuficiente",
            minimo=QUALIDADE_MINIMA,
            completude=(qualidade or {}).get("completude"),
            alertas=list((qualidade or {}).get("alertas") or []),
            campos_ausentes=list(
                (qualidade or {}).get("campos_ausentes") or []
            ),
        )
        return diagnostico
    if (qualidade or {}).get("divergencia_critica") is True:
        _registrar(diagnostico, "global", "bloqueado", "divergencia_critica")
        return diagnostico
    if not isinstance(contexto_pre_jogo, dict):
        _registrar(
            diagnostico, "global", "bloqueado",
            "contexto_pre_jogo_indisponivel",
        )
        return diagnostico
    evidencias_pre = _evidencias_pre_jogo(contexto_pre_jogo)
    if len(evidencias_pre) < MINIMO_EVIDENCIAS_PRE:
        _registrar(
            diagnostico, "global", "bloqueado",
            "evidencias_pre_jogo_insuficientes",
            encontradas=len(evidencias_pre), minimo=MINIMO_EVIDENCIAS_PRE,
        )
        return diagnostico

    por_mercado = {
        item.get("mercado"): item for item in candidatos or []
        if item.get("mercado") in {"gol_ht", "gol_ft"}
    }
    versoes_geradas = _versoes_geradas(gerados)
    if janela_2t:
        _diagnosticar_braco_2t(
            diagnostico, minuto, placar, por_mercado.get("gol_ft"),
            contexto_pre_jogo, evidencias_pre, versoes_geradas,
        )
        return diagnostico
    if placar != [0, 0]:
        _registrar(
            diagnostico, "global", "bloqueado",
            "placar_incompativel_primeiro_gol",
        )
        return diagnostico
    _diagnosticar_braco_inicial(
        diagnostico, "gol_ht_antecipado", "gol_ht",
        VERSAO_GOL_HT_ANTECIPADO, MINUTO_MAXIMO_HT, minuto,
        por_mercado.get("gol_ht"), contexto_pre_jogo, evidencias_pre,
        versoes_geradas,
    )
    _diagnosticar_braco_inicial(
        diagnostico, "gol_ft_antecipado_pre_live", "gol_ft",
        VERSAO_GOL_FT_ANTECIPADO, MINUTO_MAXIMO_FT, minuto,
        por_mercado.get("gol_ft"), contexto_pre_jogo, evidencias_pre,
        versoes_geradas,
    )
    return diagnostico


def _bloqueio_base(base):
    return next((
        motivo for motivo in base.get("bloqueios") or []
        if motivo not in _BLOQUEIOS_RELAXAVEIS
    ), None)


def _diagnosticar_braco_2t(
    diagnostico, minuto, placar, base, contexto, evidencias_pre,
    versoes_geradas,
):
    braco = "gol_ft_antecipado_2t"
    if base is None:
        _registrar(diagnostico, braco, "bloqueado", "candidato_base_ausente")
        return
    padrao = _padrao_gols_segundo_tempo(contexto, minuto)
    if not padrao["confirmado"]:
        _registrar(
            diagnostico, braco, "bloqueado", "faixa_historica_nao_confirmada",
            faixa=padrao["faixa"],
        )
        return
    try:
        linha, odd = float(base.get("linha")), float(base.get("odd"))
    except (TypeError, ValueError):
        _registrar(
            diagnostico, braco, "bloqueado", "linha_ou_odd_indisponivel"
        )
        return
    linha_exigida = placar[0] + placar[1] + 0.5
    if linha != linha_exigida:
        _registrar(
            diagnostico, braco, "bloqueado", "linha_incompativel",
            linha=linha, linha_exigida=linha_exigida,
        )
        return
    if not odd_elegivel(odd, obter_limites_risco()):
        _registrar(
            diagnostico, braco, "bloqueado", "odd_fora_da_faixa", odd=odd
        )
        return
    evidencias_live, _ = _evidencias_live(base, contexto)
    minimo_live = 3 if minuto > 75 else MINIMO_EVIDENCIAS_LIVE
    if len(evidencias_live) < minimo_live:
        _registrar(
            diagnostico, braco, "bloqueado", "evidencias_ao_vivo_insuficientes",
            encontradas=len(evidencias_live), minimo=minimo_live,
        )
        return
    bloqueio = _bloqueio_base(base)
    if bloqueio:
        _registrar(
            diagnostico, braco, "bloqueado", "bloqueio_base_nao_relaxavel",
            bloqueio=bloqueio,
        )
        return
    estado = (
        "gerado" if VERSAO_GOL_FT_ANTECIPADO_2T in versoes_geradas
        else "inconsistencia_observada"
    )
    _registrar(
        diagnostico, braco, estado,
        None if estado == "gerado" else "gerador_sem_saida_apos_gates",
        evidencias_pre=len(evidencias_pre), evidencias_live=len(evidencias_live),
        linha=linha, odd=odd,
    )


def _diagnosticar_braco_inicial(
    diagnostico, braco, mercado, versao, limite, minuto, base, contexto,
    evidencias_pre, versoes_geradas,
):
    if minuto > limite:
        _registrar(
            diagnostico, braco, "bloqueado", "fora_janela_mercado",
            minuto_maximo=limite,
        )
        return
    if base is None:
        _registrar(diagnostico, braco, "bloqueado", "candidato_base_ausente")
        return
    try:
        linha, odd = float(base.get("linha")), float(base.get("odd"))
    except (TypeError, ValueError):
        _registrar(
            diagnostico, braco, "bloqueado", "linha_ou_odd_indisponivel"
        )
        return
    if linha != 0.5:
        _registrar(
            diagnostico, braco, "bloqueado", "linha_incompativel",
            linha=linha, linha_exigida=0.5,
        )
        return
    if not odd_elegivel(odd, obter_limites_risco()):
        _registrar(
            diagnostico, braco, "bloqueado", "odd_fora_da_faixa", odd=odd
        )
        return
    if mercado == "gol_ht":
        padrao = _padrao_gols_primeiro_tempo(contexto, minuto)
        if not padrao["confirmado"]:
            _registrar(
                diagnostico, braco, "bloqueado",
                "faixa_historica_nao_confirmada", faixa=padrao["faixa"],
            )
            return
    evidencias_live, _ = _evidencias_live(base, contexto)
    minimo_live = (
        3 if mercado == "gol_ht" and minuto > 25
        else MINIMO_EVIDENCIAS_LIVE
    )
    if len(evidencias_live) < minimo_live:
        _registrar(
            diagnostico, braco, "bloqueado", "evidencias_ao_vivo_insuficientes",
            encontradas=len(evidencias_live), minimo=minimo_live,
        )
        return
    bloqueio = _bloqueio_base(base)
    if bloqueio:
        _registrar(
            diagnostico, braco, "bloqueado", "bloqueio_base_nao_relaxavel",
            bloqueio=bloqueio,
        )
        return
    estado = "gerado" if versao in versoes_geradas else "inconsistencia_observada"
    _registrar(
        diagnostico, braco, estado,
        None if estado == "gerado" else "gerador_sem_saida_apos_gates",
        evidencias_pre=len(evidencias_pre), evidencias_live=len(evidencias_live),
        linha=linha, odd=odd,
    )
