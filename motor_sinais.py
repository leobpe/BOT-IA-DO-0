from configuracao import odd_elegivel, obter_limites_risco
from evolucao import extrair_par
from qualidade_dados import extrair_minuto, extrair_placar
from normalizador_odds import (
    escolher_over_ao_vivo,
    escolher_over_ht,
    escolher_over_periodo,
    escolher_proximo_gol,
)
from movimento_odds import movimento_para


VERSAO_REGRAS = "sinais-v6"
LIMIAR_APROVACAO = 70.0
ODDS_MAX_IDADE_SEGUNDOS = 360
VERSAO_FEATURES = "features-temporais-v2"


def _total(par):
    return sum(par) if par else 0.0


def _janela(evolucao, minutos=5):
    return (evolucao or {}).get(str(minutos)) or {}


def _par_numerico(valor):
    if not isinstance(valor, (list, tuple)) or len(valor) < 2:
        return None
    try:
        return [float(valor[0]), float(valor[1])]
    except (TypeError, ValueError):
        return None


def _features_janela(evolucao, minutos):
    janela = (evolucao or {}).get(str(minutos))
    if not isinstance(janela, dict) or not janela:
        return {"disponivel": False}
    chutes = _par_numerico(janela.get("chutes"))
    escanteios = _par_numerico(janela.get("escanteios"))
    try:
        duracao = float(janela.get("duracao_real_minutos"))
        if duracao <= 0:
            duracao = None
    except (TypeError, ValueError):
        duracao = None
    total_chutes = round(sum(chutes), 3) if chutes else None
    total_escanteios = round(sum(escanteios), 3) if escanteios else None
    pressao = janela.get("pressao_resumo") or {}
    return {
        "disponivel": True,
        "duracao_real_minutos": duracao,
        "desvio_alvo_minutos": janela.get("desvio_alvo_minutos"),
        "chutes": chutes,
        "chutes_total": total_chutes,
        "chutes_por_minuto": (
            round(total_chutes / duracao, 4)
            if total_chutes is not None and duracao else None
        ),
        "chutes_por_minuto_lados": (
            [round(valor / duracao, 4) for valor in chutes]
            if chutes is not None and duracao else None
        ),
        "escanteios": escanteios,
        "escanteios_total": total_escanteios,
        "escanteios_por_minuto": (
            round(total_escanteios / duracao, 4)
            if total_escanteios is not None and duracao else None
        ),
        "escanteios_por_minuto_lados": (
            [round(valor / duracao, 4) for valor in escanteios]
            if escanteios is not None and duracao else None
        ),
        "pressao_media": _par_numerico(pressao.get("media")),
        "pressao_pico": _par_numerico(pressao.get("pico")),
        "pressao_tendencia": _par_numerico(pressao.get("tendencia")),
        "dominio_minutos": _par_numerico(
            pressao.get("dominio_minutos")
        ),
        "resets_detectados": list(
            janela.get("resets_detectados") or []
        ),
    }


def _atividade_pressao(janela):
    resumo = janela.get("pressao_resumo") or {}
    media = resumo.get("media") or [0, 0]
    pico = resumo.get("pico") or [0, 0]
    return max(media, default=0), max(pico, default=0)


def _tem_odds_ao_vivo(odds, termo):
    mercados = (odds or {}).get("ao_vivo") or []
    termo = termo.lower()
    return any(
        termo in (
            f"{mercado.get('mercado', '')} {mercado.get('dados', '')}"
        ).lower()
        for mercado in mercados
    )


def _tem_over_estruturado(
    odds, categoria, periodo=None, tipo_mercado=None
):
    for mercado in (odds or {}).get("ao_vivo") or []:
        if mercado.get("categoria") != categoria:
            continue
        if (
            tipo_mercado is not None
            and mercado.get("tipo_mercado") != tipo_mercado
        ):
            continue
        if periodo:
            dados = (mercado.get("ofertas_periodos") or {}).get(periodo)
            if dados and dados.get("formato") == "duas_opcoes":
                if dados.get("ofertas"):
                    return True
            continue
        if (mercado.get("escopo") or "total") != "total":
            continue
        if (mercado.get("formato") or "duas_opcoes") != "duas_opcoes":
            continue
        if mercado.get("ofertas"):
            return True
    return False


def _resultado(
    mercado, pontuacao, motivos, bloqueios, qualidade, oferta=None,
    limites_risco=None,
):
    bloqueios = list(bloqueios)
    odd = oferta.get("over") if oferta else None
    idade_oferta = oferta.get("idade_segundos") if oferta else None
    try:
        idade_oferta = (
            float(idade_oferta) if idade_oferta is not None else None
        )
    except (TypeError, ValueError):
        idade_oferta = None
    if odd is None:
        bloqueios.append("odd_ao_vivo_indisponivel")
    elif limites_risco is not None and not odd_elegivel(
        odd, limites_risco
    ):
        bloqueios.append("odd_fora_da_faixa_operacional")
    if (
        idade_oferta is not None
        and idade_oferta > ODDS_MAX_IDADE_SEGUNDOS
    ):
        bloqueios.append("odds_desatualizadas")
    pontuacao = round(max(0.0, min(pontuacao, 100.0)), 1)
    aprovado = pontuacao >= LIMIAR_APROVACAO and not bloqueios
    return {
        "mercado": mercado,
        "linha": oferta.get("linha") if oferta else None,
        "odd": odd,
        "pontuacao_tecnica": pontuacao,
        "probabilidade_calibrada": None,
        "regra_versao": VERSAO_REGRAS,
        "motivos": motivos,
        "bloqueios": bloqueios,
        "qualidade_dados": qualidade.get("pontuacao", 0),
        "fonte_odds": (
            oferta.get("fonte", "packball") if oferta else None
        ),
        "bookmaker_odds": oferta.get("bookmaker") if oferta else None,
        "tipo_mercado_odds": (
            oferta.get("tipo_mercado") if oferta else None
        ),
        "idade_odds_segundos": idade_oferta,
        "status": "aprovado" if aprovado else "rejeitado",
    }


def gerar_candidatos(jogo, estatisticas, evolucao, odds, qualidade):
    limites_risco = obter_limites_risco()
    minuto = extrair_minuto(jogo.get("status"))
    janela5 = _janela(evolucao)
    chutes5 = _total(janela5.get("chutes"))
    escanteios5 = _total(janela5.get("escanteios"))
    par_chutes_gol = extrair_par(estatisticas.get("Chutes no gol"))
    chutes_gol = _total(par_chutes_gol)
    par_escanteios = extrair_par(estatisticas.get("Escanteios"))
    total_escanteios = sum(par_escanteios) if par_escanteios else None
    media_pressao, pico_pressao = _atividade_pressao(janela5)
    placar = extrair_placar(jogo.get("placar"))
    total_gols = sum(placar) if placar else None
    aceleracao_chutes = (
        ((evolucao or {}).get("aceleracao_5_vs_5") or {}).get("chutes")
    )
    aceleracao_total = sum(aceleracao_chutes) if aceleracao_chutes else 0
    chutes5_lados = janela5.get("chutes") or [0, 0]

    bloqueios_comuns = []
    if not qualidade.get("apto_para_sinal"):
        bloqueios_comuns.append("qualidade_insuficiente")
    if minuto is None:
        bloqueios_comuns.append("minuto_indisponivel")
    if janela5.get("resets_detectados"):
        bloqueios_comuns.append("contador_reiniciado")
    if not janela5:
        bloqueios_comuns.append("historico_5min_insuficiente")
    eventos_recentes = (evolucao or {}).get("eventos_recentes") or {}
    if eventos_recentes.get("gol"):
        bloqueios_comuns.append("gol_recente_aguardar_odds")
    if eventos_recentes.get("cartao_vermelho"):
        bloqueios_comuns.append("cartao_vermelho_reavaliar")
    idade_odds = ((odds or {}).get("_metadados") or {}).get(
        "idade_segundos"
    )
    if idade_odds is not None and idade_odds > ODDS_MAX_IDADE_SEGUNDOS:
        bloqueios_comuns.append("odds_desatualizadas")
    bloqueios_gol = list(bloqueios_comuns)
    if chutes5 < 2 and aceleracao_total <= 0:
        bloqueios_gol.append("atividade_recente_insuficiente_gols")

    base = float(qualidade.get("pontuacao") or 0) * 0.35
    oferta_gols = escolher_over_ao_vivo(odds, "gols", total_gols)
    oferta_escanteios = escolher_over_ao_vivo(
        odds,
        "escanteios",
        total_escanteios,
        tipo_mercado="total",
    )
    oferta_escanteios_asiatico_ft = escolher_over_ao_vivo(
        odds,
        "escanteios",
        total_escanteios,
        tipo_mercado="asiatico",
    )
    baseline_intervalo = (evolucao or {}).get("escanteios_intervalo")
    escanteios_2t_atuais = None
    if baseline_intervalo is not None and total_escanteios is not None:
        escanteios_2t_atuais = max(
            total_escanteios - float(baseline_intervalo), 0.0
        )
    oferta_escanteios_1t = escolher_over_periodo(
        odds,
        "escanteios",
        "1T",
        total_escanteios,
        tipo_mercado="asiatico",
    )
    oferta_escanteios_2t = escolher_over_periodo(
        odds,
        "escanteios",
        "2T",
        escanteios_2t_atuais,
        tipo_mercado="asiatico",
    )
    resumo_pressao = janela5.get("pressao_resumo") or {}
    media_lados = resumo_pressao.get("media") or [0, 0]
    lado_proximo = "casa" if media_lados[0] >= media_lados[1] else "visitante"
    oferta_proximo = escolher_proximo_gol(odds, lado_proximo)
    oferta_ht = escolher_over_ht(odds, total_gols)
    if (
        total_gols is not None
        and oferta_gols is None
        and _tem_over_estruturado(odds, "gols")
    ):
        bloqueios_gol.append("linha_exige_multiplos_gols")
    bloqueios_escanteios_ft = list(bloqueios_comuns)
    if (
        total_escanteios is not None
        and oferta_escanteios is None
        and _tem_over_estruturado(
            odds, "escanteios", tipo_mercado="total"
        )
    ):
        bloqueios_escanteios_ft.append(
            "linha_exige_multiplos_escanteios"
        )
    movimento_gols = movimento_para(
        odds, "gols", oferta_gols.get("linha") if oferta_gols else None
    )
    movimento_escanteios = movimento_para(
        odds,
        "escanteios",
        oferta_escanteios.get("linha") if oferta_escanteios else None,
        tipo_mercado="total",
    )
    movimento_escanteios_asiatico = movimento_para(
        odds,
        "escanteios",
        (
            oferta_escanteios_asiatico_ft.get("linha")
            if oferta_escanteios_asiatico_ft else None
        ),
        tipo_mercado="asiatico",
    )

    motivos_gol = [
        "alvo=mais_1_gol",
        f"chutes_5min={chutes5:g}",
        f"chutes_no_gol_total={chutes_gol:g}",
        f"pico_pressao_5min={pico_pressao:g}",
    ]
    nota_gol = base
    nota_gol += min(chutes5 * 4, 20)
    nota_gol += min(chutes_gol * 2.5, 15)
    nota_gol += min(max(pico_pressao - 50, 0) * 0.5, 15)
    if aceleracao_total > 0:
        nota_gol += min(aceleracao_total, 5)
        motivos_gol.append(f"aceleracao_chutes={aceleracao_total:+g}")
    if total_gols is not None:
        motivos_gol.append(f"gols_atuais={total_gols}")
    if minuto is not None and 20 <= minuto <= 82:
        nota_gol += 10
        motivos_gol.append("minuto_na_faixa_da_regra")
    if oferta_gols or _tem_odds_ao_vivo(odds, "gol"):
        nota_gol += 5
        motivos_gol.append("mercado_ao_vivo_disponivel")
    if movimento_gols:
        motivos_gol.append(
            f"odd_over_{movimento_gols['direcao']}="
            f"{movimento_gols['delta']:+g}"
        )
        nota_gol += 5 if movimento_gols["direcao"] == "queda" else 0

    motivos_escanteio = [
        "alvo=mais_1_escanteio",
        f"escanteios_5min={escanteios5:g}",
        f"media_pressao_5min={media_pressao:g}",
    ]
    nota_escanteio = base
    nota_escanteio += min(escanteios5 * 12, 24)
    nota_escanteio += min(chutes5 * 3, 15)
    nota_escanteio += min(max(media_pressao - 50, 0) * 0.6, 16)
    if aceleracao_total > 0:
        nota_escanteio += min(aceleracao_total, 5)
    if minuto is not None and 15 <= minuto <= 87:
        nota_escanteio += 5
        motivos_escanteio.append("minuto_na_faixa_da_regra")
    if oferta_escanteios or _tem_odds_ao_vivo(odds, "escanteio"):
        nota_escanteio += 5
        motivos_escanteio.append("mercado_ao_vivo_disponivel")
    if movimento_escanteios:
        motivos_escanteio.append(
            f"odd_over_{movimento_escanteios['direcao']}="
            f"{movimento_escanteios['delta']:+g}"
        )
        nota_escanteio += (
            5 if movimento_escanteios["direcao"] == "queda" else 0
        )

    bloqueios_escanteios_asiatico_ft = list(bloqueios_comuns)
    if (
        total_escanteios is not None
        and oferta_escanteios_asiatico_ft is None
        and _tem_over_estruturado(
            odds, "escanteios", tipo_mercado="asiatico"
        )
    ):
        bloqueios_escanteios_asiatico_ft.append(
            "linha_exige_multiplos_escanteios"
        )
    if minuto is None or not 15 <= minuto <= 87:
        bloqueios_escanteios_asiatico_ft.append(
            "fora_da_janela_escanteios_ft_asiatico"
        )
    nota_escanteios_asiatico_ft = nota_escanteio
    if oferta_escanteios_asiatico_ft:
        nota_escanteios_asiatico_ft += 5
    motivos_escanteios_asiatico_ft = motivos_escanteio + [
        "mercado_escanteios_asiaticos_jogo_inteiro"
    ]
    if movimento_escanteios_asiatico:
        motivos_escanteios_asiatico_ft.append(
            f"odd_over_{movimento_escanteios_asiatico['direcao']}="
            f"{movimento_escanteios_asiatico['delta']:+g}"
        )
        if movimento_escanteios_asiatico["direcao"] == "queda":
            nota_escanteios_asiatico_ft += 5

    bloqueios_ht = [
        item for item in bloqueios_gol
        if item != "linha_exige_multiplos_gols"
    ]
    if (
        total_gols is not None
        and oferta_ht is None
        and any(
            mercado.get("ofertas_ht")
            for mercado in (odds or {}).get("ao_vivo") or []
        )
    ):
        bloqueios_ht.append("linha_exige_multiplos_gols")
    if minuto is None or minuto > 40:
        bloqueios_ht.append("fora_da_janela_gol_ht")
    nota_ht = base + min(chutes5 * 4, 20) + min(chutes_gol * 2.5, 15)
    nota_ht += min(max(pico_pressao - 50, 0) * 0.5, 15)
    if minuto is not None and 10 <= minuto <= 40:
        nota_ht += 10
    if oferta_ht:
        nota_ht += 5

    bloqueios_escanteios_1t = list(bloqueios_comuns)
    if (
        total_escanteios is not None
        and oferta_escanteios_1t is None
        and _tem_over_estruturado(
            odds,
            "escanteios",
            "1T",
            tipo_mercado="asiatico",
        )
    ):
        bloqueios_escanteios_1t.append(
            "linha_exige_multiplos_escanteios"
        )
    if minuto is None or not 15 <= minuto <= 40:
        bloqueios_escanteios_1t.append("fora_da_janela_escanteios_1t")
    nota_escanteios_1t = nota_escanteio
    if oferta_escanteios_1t:
        nota_escanteios_1t += 5

    bloqueios_escanteios_2t = list(bloqueios_comuns)
    if (
        escanteios_2t_atuais is not None
        and oferta_escanteios_2t is None
        and _tem_over_estruturado(
            odds,
            "escanteios",
            "2T",
            tipo_mercado="asiatico",
        )
    ):
        bloqueios_escanteios_2t.append(
            "linha_exige_multiplos_escanteios"
        )
    if minuto is None or not 50 <= minuto <= 87:
        bloqueios_escanteios_2t.append("fora_da_janela_escanteios_2t")
    if (evolucao or {}).get("escanteios_intervalo") is None:
        bloqueios_escanteios_2t.append("baseline_intervalo_indisponivel")
    nota_escanteios_2t = nota_escanteio
    if oferta_escanteios_2t:
        nota_escanteios_2t += 5

    motivos_proximo = [
        f"lado_dominante={lado_proximo}",
        f"chutes_5min={chutes5:g}",
        f"pico_pressao_5min={pico_pressao:g}",
    ]
    nota_proximo = base + min(chutes5 * 4, 20)
    nota_proximo += min(chutes_gol * 2.5, 15)
    nota_proximo += min(max(pico_pressao - 50, 0) * 0.5, 15)
    bloqueios_proximo = [
        item for item in bloqueios_gol
        if item != "linha_exige_multiplos_gols"
    ]
    indice_lado_proximo = 0 if lado_proximo == "casa" else 1
    try:
        chutes_lado_proximo = float(chutes5_lados[indice_lado_proximo])
    except (IndexError, TypeError, ValueError):
        chutes_lado_proximo = 0
    if chutes_lado_proximo < 1:
        bloqueios_proximo.append("lado_dominante_sem_chute_recente")
    if oferta_proximo:
        nota_proximo += 5
        motivos_proximo.append("odd_proximo_gol_disponivel")

    candidatos = [
        _resultado(
            "gol_ft",
            nota_gol,
            motivos_gol,
            bloqueios_gol,
            qualidade,
            oferta_gols,
            limites_risco,
        ),
        _resultado(
            "proximo_escanteio",
            nota_escanteio,
            motivos_escanteio,
            bloqueios_escanteios_ft,
            qualidade,
            oferta_escanteios,
            limites_risco,
        ),
        _resultado(
            "gol_ht",
            nota_ht,
            [f"chutes_5min={chutes5:g}", "janela_primeiro_tempo"],
            bloqueios_ht,
            qualidade,
            oferta_ht,
            limites_risco,
        ),
        _resultado(
            "proximo_gol",
            nota_proximo,
            motivos_proximo,
            bloqueios_proximo,
            qualidade,
            oferta_proximo,
            limites_risco,
        ),
        _resultado(
            "escanteios_1t",
            nota_escanteios_1t,
            motivos_escanteio + ["mercado_exclusivo_primeiro_tempo"],
            bloqueios_escanteios_1t,
            qualidade,
            oferta_escanteios_1t,
            limites_risco,
        ),
        _resultado(
            "escanteios_2t",
            nota_escanteios_2t,
            motivos_escanteio + ["mercado_exclusivo_segundo_tempo"],
            bloqueios_escanteios_2t,
            qualidade,
            oferta_escanteios_2t,
            limites_risco,
        ),
        _resultado(
            "escanteios_ft_asiatico",
            nota_escanteios_asiatico_ft,
            motivos_escanteios_asiatico_ft,
            bloqueios_escanteios_asiatico_ft,
            qualidade,
            oferta_escanteios_asiatico_ft,
            limites_risco,
        ),
    ]
    aceleracao = (evolucao or {}).get("aceleracao_5_vs_5") or {}
    features_base = {
        "schema_versao": VERSAO_FEATURES,
        "minuto": minuto,
        "periodo": (evolucao or {}).get("periodo"),
        "gols_atuais": total_gols,
        "escanteios_atuais": total_escanteios,
        "chutes_no_gol": (
            [float(valor) for valor in par_chutes_gol]
            if par_chutes_gol else None
        ),
        "chutes_no_gol_total": (
            float(sum(par_chutes_gol)) if par_chutes_gol else None
        ),
        "janelas": {
            str(janela): _features_janela(evolucao, janela)
            for janela in (5, 10, 15)
        },
        "aceleracao_5_vs_5": {
            "chutes": _par_numerico(aceleracao.get("chutes")),
            "escanteios": _par_numerico(aceleracao.get("escanteios")),
        },
        "lado_dominante": lado_proximo,
        "chutes_lado_dominante_5min": chutes_lado_proximo,
        "escanteios_intervalo": baseline_intervalo,
        "escanteios_2t_atuais": escanteios_2t_atuais,
        "idade_odds_segundos": idade_odds,
        "qualidade_dados": qualidade.get("pontuacao", 0),
        "fontes": list(qualidade.get("fontes") or []),
        "movimento_gols": movimento_gols,
        "movimento_escanteios": movimento_escanteios,
    }
    for candidato in candidatos:
        candidato["features"] = {
            **features_base,
            "mercado": candidato["mercado"],
            "linha": candidato.get("linha"),
            "odd": candidato.get("odd"),
            "fonte_odds": candidato.get("fonte_odds"),
            "bookmaker_odds": candidato.get("bookmaker_odds"),
            "tipo_mercado_odds": candidato.get("tipo_mercado_odds"),
            "idade_odds_segundos": (
                candidato.get("idade_odds_segundos")
                if candidato.get("idade_odds_segundos") is not None
                else idade_odds
            ),
        }
    return candidatos
