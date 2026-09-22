import hashlib
import json
import math
import sqlite3
import statistics
from collections import Counter
from datetime import datetime

from estatistica import estado_amostra, intervalo_wilson
from linhagem_regras import fingerprint_vinculado_no_banco


RESULTADOS_VALIDOS = (
    "green", "half_green", "void", "half_red", "red",
)
VERSAO_AVALIACAO_CONTEXTO = "avaliacao-contexto-sombra-causal-v6"
PREFIXO_ANCORA_CONTEXTO = "avaliacao_contexto:causal_v6"
Z_MULTIPLAS_COMPARACOES = 3.0
TAMANHO_COORTE = 300
TAMANHO_DESENVOLVIMENTO = 210
TAMANHO_HOLDOUT = 90
AMOSTRA_MINIMA_SEGMENTO = 30
HIPOTESES_CONTEXTO_POR_MERCADO = {
    "gol_ft": (
        "forma_mandante_superior",
        "forma_visitante_superior",
        "h2h_gols_alto",
        "desfalques_desequilibrados",
        "escalacoes_confirmadas",
        "fontes_concordantes",
        "historico_gols_alto",
        "linha_pre_jogo_gols_alta",
        "xg_live_alto",
        "volume_ofensivo_api_alto",
    ),
    "gol_ht": (
        "h2h_gols_alto",
        "escalacoes_confirmadas",
        "fontes_concordantes",
        "linha_pre_jogo_gols_alta",
        "xg_live_alto",
        "volume_ofensivo_api_alto",
    ),
    "proximo_gol": (
        "forma_mandante_superior",
        "forma_visitante_superior",
        "desfalques_desequilibrados",
        "escalacoes_confirmadas",
        "fontes_concordantes",
        "linha_pre_jogo_gols_alta",
        "xg_live_alto",
        "volume_ofensivo_api_alto",
    ),
    "proximo_escanteio": (
        "fontes_concordantes",
        "historico_escanteios_alto",
        "linha_pre_jogo_escanteios_alta",
        "volume_ofensivo_api_alto",
    ),
    "escanteios_ft_asiatico": (
        "fontes_concordantes",
        "historico_escanteios_alto",
        "linha_pre_jogo_escanteios_alta",
        "volume_ofensivo_api_alto",
    ),
    "escanteios_1t": (
        "fontes_concordantes",
        "historico_escanteios_alto",
        "linha_pre_jogo_escanteios_alta",
        "volume_ofensivo_api_alto",
    ),
    "escanteios_2t": (
        "fontes_concordantes",
        "historico_escanteios_alto",
        "linha_pre_jogo_escanteios_alta",
        "volume_ofensivo_api_alto",
    ),
}


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _chave_ancora_contexto(mercado, regra_versao):
    return f"{PREFIXO_ANCORA_CONTEXTO}:{mercado}:{regra_versao}:inicio"


def registrar_ou_obter_ancoras_contexto(
    conexao, regras_por_mercado, registrado_em=None,
):
    """Pré-registra o corte V6 antes de qualquer unidade decisória."""
    instante = str(
        registrado_em
        or datetime.now().replace(microsecond=0).isoformat()
    )
    ancoras = {}
    with conexao:
        for mercado, regra_versao in sorted(
            (regras_por_mercado or {}).items()
        ):
            chave = _chave_ancora_contexto(mercado, regra_versao)
            conexao.execute(
                "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
                (chave, instante),
            )
            linha = conexao.execute(
                "SELECT valor FROM metadados WHERE chave=?", (chave,)
            ).fetchone()
            ancoras[mercado] = str(
                linha["valor"] if linha is not None else instante
            )
    return ancoras


def _obter_ancora_contexto(conexao, mercado, regra_versao):
    try:
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (_chave_ancora_contexto(mercado, regra_versao),),
        ).fetchone()
    except sqlite3.Error:
        return None
    if linha is None:
        return None
    try:
        return str(linha["valor"])
    except (TypeError, IndexError):
        return str(linha[0])


def extrair_variaveis_contexto(contexto):
    contexto = contexto or {}
    forma = contexto.get("forma_recente") or {}
    casa = forma.get("mandante") or {}
    fora = forma.get("visitante") or {}
    ppg_casa = _numero(casa.get("pontos_por_jogo"))
    ppg_fora = _numero(fora.get("pontos_por_jogo"))
    h2h = contexto.get("confrontos_diretos") or {}
    media_gols_h2h = _numero(h2h.get("media_gols"))
    desfalques = contexto.get("desfalques") or {}
    ids = contexto.get("times") or {}
    casa_id = str(ids.get("mandante_id"))
    fora_id = str(ids.get("visitante_id"))
    ausentes_casa = _numero((desfalques.get(casa_id) or {}).get("total"))
    ausentes_fora = _numero((desfalques.get(fora_id) or {}).get("total"))
    escalacoes = contexto.get("escalacoes") or {}
    comparacao = contexto.get("comparacao_fontes_ao_vivo") or {}
    taxa_concordancia = _numero(comparacao.get("taxa_concordancia"))
    tem_forma = ppg_casa is not None and ppg_fora is not None
    tem_h2h = media_gols_h2h is not None
    tem_desfalques = (
        ausentes_casa is not None and ausentes_fora is not None
    )
    tem_escalacoes = casa_id in escalacoes and fora_id in escalacoes
    tem_comparacao = (
        int(comparacao.get("comparadas") or 0) > 0
        and taxa_concordancia is not None
    )
    historico = contexto.get("historico_detalhado") or {}
    historico_casa = historico.get("mandante") or {}
    historico_fora = historico.get("visitante") or {}
    totais_gols_historicos = [
        _numero(item.get("gols_pro_media"))
        + _numero(item.get("gols_contra_media"))
        for item in (historico_casa, historico_fora)
        if _numero(item.get("gols_pro_media")) is not None
        and _numero(item.get("gols_contra_media")) is not None
    ]
    escanteios_historicos = [
        _numero(historico_casa.get("escanteios_media")),
        _numero(historico_casa.get("escanteios_contra_media")),
        _numero(historico_fora.get("escanteios_media")),
        _numero(historico_fora.get("escanteios_contra_media")),
    ]
    tem_escanteios_historicos = all(
        valor is not None for valor in escanteios_historicos
    )
    live = (
        (contexto.get("estatisticas_ao_vivo") or {}).get("times") or {}
    )
    live_casa = live.get("mandante") or {}
    live_fora = live.get("visitante") or {}
    xg_live = [
        _numero(live_casa.get("xg")),
        _numero(live_fora.get("xg")),
    ]
    chutes_live = [
        _numero(live_casa.get("chutes")),
        _numero(live_fora.get("chutes")),
    ]
    chutes_gol_live = [
        _numero(live_casa.get("chutes_no_gol")),
        _numero(live_fora.get("chutes_no_gol")),
    ]
    tem_volume_live = (
        all(valor is not None for valor in chutes_live)
        and all(valor is not None for valor in chutes_gol_live)
    )
    odds_pre_jogo = (
        (contexto.get("odds_pre_jogo") or {}).get("mercados") or {}
    )
    linha_gols = odds_pre_jogo.get("gols_ft") or {}
    linha_escanteios = odds_pre_jogo.get("escanteios_ft") or {}
    linha_gols_consenso = _numero(linha_gols.get("linha_consenso"))
    linha_escanteios_consenso = _numero(
        linha_escanteios.get("linha_consenso")
    )
    return {
        "forma_mandante_superior": (
            ppg_casa - ppg_fora >= 0.75 if tem_forma else None
        ),
        "forma_visitante_superior": (
            ppg_fora - ppg_casa >= 0.75 if tem_forma else None
        ),
        "h2h_gols_alto": (
            media_gols_h2h >= 2.5 if tem_h2h else None
        ),
        "desfalques_desequilibrados": (
            abs(ausentes_casa - ausentes_fora) >= 2
            if tem_desfalques else None
        ),
        "escalacoes_confirmadas": (
            (
                bool((escalacoes.get(casa_id) or {}).get("confirmada"))
                and bool((escalacoes.get(fora_id) or {}).get("confirmada"))
            )
            if tem_escalacoes else None
        ),
        "fontes_concordantes": (
            taxa_concordancia >= 0.8 if tem_comparacao else None
        ),
        "historico_gols_alto": (
            sum(totais_gols_historicos) / len(totais_gols_historicos)
            >= 2.5
            if len(totais_gols_historicos) == 2 else None
        ),
        "historico_escanteios_alto": (
            sum(escanteios_historicos) / 2 >= 9.0
            if tem_escanteios_historicos else None
        ),
        "linha_pre_jogo_gols_alta": (
            linha_gols_consenso >= 2.5
            if linha_gols.get("consenso_suficiente")
            and linha_gols_consenso is not None
            else None
        ),
        "linha_pre_jogo_escanteios_alta": (
            linha_escanteios_consenso >= 9.0
            if linha_escanteios.get("consenso_suficiente")
            and linha_escanteios_consenso is not None
            else None
        ),
        "xg_live_alto": (
            sum(xg_live) >= 1.5
            if all(valor is not None for valor in xg_live) else None
        ),
        "volume_ofensivo_api_alto": (
            sum(chutes_live) >= 14 or sum(chutes_gol_live) >= 5
            if tem_volume_live else None
        ),
    }


def _resumir(resultados):
    total = len(resultados)
    direcionais = [
        item for item in resultados
        if str(
            item.get("resultado_normalizado")
            or item.get("resultado") or ""
        ).casefold() != "void"
    ]
    greens = sum(
        str(
            item.get("resultado_normalizado")
            or item.get("resultado") or ""
        ).casefold() in ("green", "half_green")
        for item in direcionais
    )
    reds = len(direcionais) - greens
    retornos = [
        float(
            item.get("retorno_normalizado")
            if item.get("retorno_normalizado") is not None
            else item["retorno_unidades"]
        )
        for item in resultados
        if item.get("retorno_unidades") is not None
        or item.get("retorno_normalizado") is not None
    ]
    intervalo = intervalo_wilson(greens, len(direcionais))
    return {
        "amostra": total,
        "amostra_direcional": len(direcionais),
        "greens": greens,
        "reds": reds,
        "voids": total - len(direcionais),
        "taxa_acerto": (
            round(greens / len(direcionais), 4)
            if direcionais else None
        ),
        "intervalo_acerto_95": (
            [round(valor, 4) for valor in intervalo]
            if intervalo else None
        ),
        "roi": round(sum(retornos) / len(retornos), 4) if retornos else None,
        "estado": estado_amostra(total),
    }


def _intervalo_delta_media(amostra, controle, z):
    if len(amostra) < 2 or len(controle) < 2:
        return None
    variancia_amostra = statistics.variance(amostra)
    variancia_controle = statistics.variance(controle)
    erro = math.sqrt(
        variancia_amostra / len(amostra)
        + variancia_controle / len(controle)
    )
    delta = statistics.mean(amostra) - statistics.mean(controle)
    margem = float(z) * erro
    return [round(delta - margem, 4), round(delta + margem, 4)]


def avaliar_segmento_contexto(
    com, sem, desconhecidos=0, total=None,
    z=Z_MULTIPLAS_COMPARACOES,
):
    resumo_com = _resumir(com)
    resumo_sem = _resumir(sem)
    total = (
        int(total)
        if total is not None
        else len(com) + len(sem) + int(desconhecidos)
    )
    avaliavel = (
        resumo_com["amostra"] >= AMOSTRA_MINIMA_SEGMENTO
        and resumo_sem["amostra"] >= AMOSTRA_MINIMA_SEGMENTO
    )
    retornos_com = [
        float(item["retorno_unidades"])
        for item in com
        if item.get("retorno_unidades") is not None
    ]
    retornos_sem = [
        float(item["retorno_unidades"])
        for item in sem
        if item.get("retorno_unidades") is not None
    ]
    intervalo_roi = (
        _intervalo_delta_media(retornos_com, retornos_sem, z)
        if avaliavel else None
    )
    delta_roi = (
        round(resumo_com["roi"] - resumo_sem["roi"], 4)
        if resumo_com["roi"] is not None and resumo_sem["roi"] is not None
        else None
    )
    if not avaliavel:
        evidencia = "aguardando_amostra"
    elif (
        resumo_com["roi"] is not None
        and resumo_com["roi"] > 0
        and intervalo_roi is not None
        and intervalo_roi[0] > 0
    ):
        evidencia = "favoravel"
    elif intervalo_roi is not None and intervalo_roi[1] < 0:
        evidencia = "contraria"
    else:
        evidencia = "inconclusiva"
    return {
        "com": resumo_com,
        "sem": resumo_sem,
        "desconhecidos": int(desconhecidos),
        "cobertura": (
            round((len(com) + len(sem)) / total, 4) if total else None
        ),
        "avaliavel": avaliavel,
        "conclusivo": evidencia in ("favoravel", "contraria"),
        "evidencia": evidencia,
        "delta_taxa_acerto": (
            round(
                resumo_com["taxa_acerto"] - resumo_sem["taxa_acerto"],
                4,
            )
            if resumo_com["taxa_acerto"] is not None
            and resumo_sem["taxa_acerto"] is not None
            else None
        ),
        "delta_roi": delta_roi,
        "intervalo_delta_roi_ajustado": intervalo_roi,
        "z_ajustado": float(z),
    }


def _carregar_mercado(
    conexao, mercado, regra_versao, ancora, janela_maxima
):
    fingerprint = fingerprint_vinculado_no_banco(conexao, regra_versao)
    if fingerprint is None:
        return [], {
            "estado": "linhagem_ausente",
            "candidatos_elegiveis": 0,
            "unidades_independentes": 0,
            "selecao_antes_do_resultado": True,
        }
    linhas = conexao.execute(
        """
        WITH independentes AS (
            SELECT s.id, s.partida_id, s.mercado, s.criado_em,
                   s.odd,
                   r.resultado, r.retorno_unidades,
                   sn.contexto_api_json,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.partida_id
                       ORDER BY datetime(s.criado_em), s.id
                   ) AS ordem
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            LEFT JOIN snapshots sn ON sn.id=s.snapshot_id
            WHERE s.mercado=? AND s.regra_versao=?
              AND s.regra_fingerprint=?
              AND s.status='aprovado'
              AND datetime(s.criado_em) >= datetime(?)
        )
        SELECT *
        FROM independentes
        WHERE ordem=1
        ORDER BY datetime(criado_em), id
        LIMIT ?
        """,
        (
            mercado,
            regra_versao,
            fingerprint,
            str(ancora),
            max(int(janela_maxima), TAMANHO_COORTE),
        ),
    ).fetchall()
    resultados = []
    contexto_invalido = 0
    for linha in linhas:
        try:
            contexto = json.loads(linha["contexto_api_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            contexto = {}
        if not isinstance(contexto, dict) or not contexto:
            contexto = {}
            contexto_invalido += 1
        item = dict(linha)
        item["contexto"] = contexto
        resultados.append(item)
    bruto = conexao.execute(
        """
        SELECT COUNT(*) AS decisoes_brutas,
               COUNT(DISTINCT s.partida_id) AS partidas
        FROM sinais s
        WHERE s.mercado=? AND s.regra_versao=?
          AND s.regra_fingerprint=? AND s.status='aprovado'
          AND datetime(s.criado_em) >= datetime(?)
        """,
        (mercado, regra_versao, fingerprint, str(ancora)),
    ).fetchone()
    try:
        decisoes_brutas = int(bruto["decisoes_brutas"] or 0)
        candidatos = int(bruto["partidas"] or 0)
    except (TypeError, IndexError):
        decisoes_brutas = int(bruto[0] or 0) if bruto else 0
        candidatos = int(bruto[1] or 0) if bruto else 0
    except KeyError:
        decisoes_brutas = int(bruto[0] or 0) if bruto else 0
        candidatos = int(bruto[1] or 0) if bruto else 0
    if bruto is None:
        decisoes_brutas = 0
        candidatos = 0
    return resultados, {
        "estado": "carregada",
        "candidatos_elegiveis": candidatos,
        "decisoes_brutas_elegiveis": decisoes_brutas,
        "unidades_independentes": len(resultados),
        "contextos_ausentes_ou_invalidos": contexto_invalido,
        "selecao_antes_do_resultado": True,
        "chave_independencia": "partida_id",
        "ordem_coorte": "criado_em_asc_id_asc",
    }


def _retorno_esperado(resultado, odd):
    return {
        "green": odd - 1.0,
        "half_green": (odd - 1.0) / 2.0,
        "void": 0.0,
        "half_red": -0.5,
        "red": -1.0,
    }.get(resultado)


def _validar_liquidacoes(itens, limites_risco):
    validas = []
    motivos = Counter()
    for item in itens:
        odd = _numero(item.get("odd"))
        if odd is None or not (
            limites_risco.odd_minima <= odd <= limites_risco.odd_maxima
        ):
            motivos["odd_ausente_invalida_ou_fora_da_politica"] += 1
            continue
        resultado = str(item.get("resultado") or "").casefold()
        if not resultado:
            motivos["resultado_ausente"] += 1
            continue
        if resultado not in RESULTADOS_VALIDOS:
            motivos[f"resultado_invalido:{resultado}"] += 1
            continue
        retorno = _numero(item.get("retorno_unidades"))
        if retorno is None:
            motivos["retorno_ausente_ou_invalido"] += 1
            continue
        esperado = _retorno_esperado(resultado, odd)
        if esperado is None or abs(retorno - esperado) > 1e-4:
            motivos["retorno_incompativel_com_resultado_e_odd"] += 1
            continue
        validas.append({
            **item,
            "resultado_normalizado": resultado,
            "retorno_normalizado": retorno,
            "odd_normalizada": odd,
        })
    return validas, {
        "unidades": len(itens),
        "validas": len(validas),
        "pendentes_ou_invalidas": len(itens) - len(validas),
        "resultados_completos_e_validos": len(validas) == len(itens),
        "motivos": dict(motivos),
        "selecao_antes_do_resultado": True,
    }


def _avaliar_segmentos(itens, hipoteses):
    segmentos = {}
    for variavel in hipoteses:
        com = []
        sem = []
        desconhecidos = 0
        for item in itens:
            variaveis = extrair_variaveis_contexto(item["contexto"])
            valor = variaveis[variavel]
            if valor is None:
                desconhecidos += 1
                continue
            (com if valor else sem).append(item)
        segmentos[variavel] = avaliar_segmento_contexto(
            com,
            sem,
            desconhecidos=desconhecidos,
            total=len(itens),
        )
    return segmentos


def _replicar_segmento(total, desenvolvimento, holdout, coorte_pronta):
    if not coorte_pronta:
        return "aguardando_coorte_fixa"
    if not desenvolvimento.get("avaliavel") or not holdout.get("avaliavel"):
        return "aguardando_amostra_nos_dois_bracos"
    evidencias = {
        total.get("evidencia"),
        desenvolvimento.get("evidencia"),
        holdout.get("evidencia"),
    }
    if evidencias == {"favoravel"}:
        return "favoravel_replicada"
    if evidencias == {"contraria"}:
        return "contraria_replicada"
    return "inconclusiva_ou_nao_replicada"


def _identidade_estado_coorte(itens):
    if not itens:
        return None, None
    payload = [
        {
            "id": int(item["id"]),
            "odd": item.get("odd"),
            "resultado": item.get("resultado"),
            "retorno_unidades": item.get("retorno_unidades"),
            "contexto_api_json": item.get("contexto_api_json"),
        }
        for item in itens
    ]
    serializado = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(serializado.encode("utf-8")).hexdigest()
    return digest, int(digest[:15], 16)


def avaliar_contexto_avancado(
    conexao, regras_por_mercado, limites_risco, janela_maxima=300
):
    por_mercado = {}
    for mercado, regra_versao in sorted(
        (regras_por_mercado or {}).items()
    ):
        ancora = _obter_ancora_contexto(
            conexao, mercado, regra_versao
        )
        if ancora is None:
            unidades = []
            auditoria_carga = {
                "estado": "ancora_v6_ausente",
                "candidatos_elegiveis": 0,
                "unidades_independentes": 0,
                "selecao_antes_do_resultado": True,
            }
        else:
            unidades, auditoria_carga = _carregar_mercado(
                conexao,
                mercado,
                regra_versao,
                ancora,
                janela_maxima,
            )
        coorte = unidades[:TAMANHO_COORTE]
        desenvolvimento = coorte[:TAMANHO_DESENVOLVIMENTO]
        holdout = coorte[
            TAMANHO_DESENVOLVIMENTO:
            TAMANHO_DESENVOLVIMENTO + TAMANHO_HOLDOUT
        ]
        resultados, auditoria_resultados = _validar_liquidacoes(
            coorte, limites_risco
        )
        ids_desenvolvimento = {
            int(item["id"]) for item in desenvolvimento
        }
        ids_holdout = {int(item["id"]) for item in holdout}
        resultados_desenvolvimento = [
            item for item in resultados
            if int(item["id"]) in ids_desenvolvimento
        ]
        resultados_holdout = [
            item for item in resultados
            if int(item["id"]) in ids_holdout
        ]
        base = _resumir(resultados)
        base.update({
            "candidatos_independentes": len(coorte),
            "pendentes_ou_invalidos": (
                auditoria_resultados["pendentes_ou_invalidas"]
            ),
            "resultados_completos_e_validos": (
                auditoria_resultados["resultados_completos_e_validos"]
            ),
            "auditoria_resultados": auditoria_resultados,
        })
        hipoteses = HIPOTESES_CONTEXTO_POR_MERCADO.get(mercado, ())
        segmentos_total = _avaliar_segmentos(resultados, hipoteses)
        segmentos_desenvolvimento = _avaliar_segmentos(
            resultados_desenvolvimento, hipoteses
        )
        segmentos_holdout = _avaliar_segmentos(
            resultados_holdout, hipoteses
        )
        coorte_pronta = bool(
            ancora is not None
            and len(coorte) == TAMANHO_COORTE
            and auditoria_resultados["resultados_completos_e_validos"]
            and len(desenvolvimento) == TAMANHO_DESENVOLVIMENTO
            and len(holdout) == TAMANHO_HOLDOUT
        )
        segmentos = {}
        for variavel in hipoteses:
            total = segmentos_total[variavel]
            desenvolvimento_segmento = (
                segmentos_desenvolvimento[variavel]
            )
            holdout_segmento = segmentos_holdout[variavel]
            replicacao = _replicar_segmento(
                total,
                desenvolvimento_segmento,
                holdout_segmento,
                coorte_pronta,
            )
            segmentos[variavel] = {
                **total,
                "evidencia_combinada_sem_gate_holdout": total["evidencia"],
                "conclusivo": replicacao in {
                    "favoravel_replicada", "contraria_replicada",
                },
                "evidencia": replicacao,
                "desenvolvimento_210": desenvolvimento_segmento,
                "holdout_90": holdout_segmento,
                "replicacao_obrigatoria": True,
            }
        pronto_para_revisao = any(
            item["conclusivo"] for item in segmentos.values()
        )
        fingerprint_estado, chave_historico_estado = (
            _identidade_estado_coorte(coorte)
        )
        ultimo_sinal_real_id = (
            max(int(item["id"]) for item in unidades)
            if unidades else None
        )
        por_mercado[mercado] = {
            "versao_avaliacao": VERSAO_AVALIACAO_CONTEXTO,
            "regra_versao": regra_versao,
            "ancora_prospectiva_em": ancora,
            "ancora_pre_registrada": ancora is not None,
            "hipoteses_pre_registradas": list(hipoteses),
            "base": base,
            "segmentos": segmentos,
            "auditoria_carga": auditoria_carga,
            "auditoria_coorte": {
                "unidades_independentes_disponiveis": len(unidades),
                "unidades_coorte_fixa": len(coorte),
                "unidades_pos_coorte_somente_diagnostico": max(
                    0, len(unidades) - TAMANHO_COORTE
                ),
                "coorte_fechada": len(coorte) == TAMANHO_COORTE,
                "unidades_desenvolvimento": len(desenvolvimento),
                "unidades_holdout": len(holdout),
                "resultados_validos_desenvolvimento": len(
                    resultados_desenvolvimento
                ),
                "resultados_validos_holdout": len(resultados_holdout),
                "particao_definida_antes_do_resultado": True,
            },
            "ultimo_sinal_id": ultimo_sinal_real_id,
            "ultimo_sinal_real_id": ultimo_sinal_real_id,
            "fingerprint_estado_coorte": fingerprint_estado,
            "chave_historico_estado": chave_historico_estado,
            "pronto_para_revisao": pronto_para_revisao,
            "aplicacao_automatica": False,
        }
    return {
        "versao": VERSAO_AVALIACAO_CONTEXTO,
        "modo": "sombra_causal_holdout_fixo",
        "aplicacao_automatica": False,
        "promocao_automatica": False,
        "z_multiplas_comparacoes": Z_MULTIPLAS_COMPARACOES,
        "tamanho_coorte": TAMANHO_COORTE,
        "tamanho_desenvolvimento": TAMANHO_DESENVOLVIMENTO,
        "tamanho_holdout": TAMANHO_HOLDOUT,
        "criterio_independencia": (
            "primeiro_sinal_aprovado_por_partida_antes_de_resultado_"
            "odd_e_contexto"
        ),
        "total_hipoteses_pre_registradas": sum(
            len(HIPOTESES_CONTEXTO_POR_MERCADO.get(mercado, ()))
            for mercado in (regras_por_mercado or {})
        ),
        "por_mercado": por_mercado,
        "amostra_total": sum(
            item["base"]["candidatos_independentes"]
            for item in por_mercado.values()
        ),
        "resultados_validos_total": sum(
            item["base"]["amostra"] for item in por_mercado.values()
        ),
        "mercados_prontos_para_revisao": [
            mercado
            for mercado, item in por_mercado.items()
            if item["pronto_para_revisao"]
        ],
    }


def registrar_historico_avaliacao_contexto(
    conexao, avaliacao, registrado_em
):
    inseridos = ignorados = sem_resultado = 0
    for mercado, item in sorted(
        ((avaliacao or {}).get("por_mercado") or {}).items()
    ):
        chave_historico = (
            item.get("chave_historico_estado")
            if item.get("versao_avaliacao")
            == VERSAO_AVALIACAO_CONTEXTO
            else item.get("ultimo_sinal_id")
        )
        if chave_historico is None:
            sem_resultado += 1
            continue
        payload = json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cursor = conexao.execute(
            """
            INSERT OR IGNORE INTO historico_avaliacao_contexto (
                regra_versao, mercado, registrado_em, ultimo_sinal_id,
                amostra, estado, pronto_para_revisao, avaliacao_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["regra_versao"],
                mercado,
                registrado_em,
                int(chave_historico),
                int((item.get("base") or {}).get("amostra") or 0),
                str((item.get("base") or {}).get("estado") or "inconclusiva"),
                int(bool(item.get("pronto_para_revisao"))),
                payload,
            ),
        )
        if cursor.rowcount:
            inseridos += 1
        else:
            ignorados += 1
    return {
        "inseridos": inseridos,
        "ignorados": ignorados,
        "sem_resultado": sem_resultado,
    }


def auditar_historico_avaliacao_contexto(conexao):
    linhas = conexao.execute(
        """
        SELECT id, regra_versao, mercado, registrado_em,
               ultimo_sinal_id, amostra, estado,
               pronto_para_revisao, avaliacao_json
        FROM historico_avaliacao_contexto
        ORDER BY id
        """
    ).fetchall()
    json_invalidos = []
    divergentes = []
    legado_sem_versao = []
    chaves = set()
    duplicadas = []
    mercados = set()
    prontos = 0
    prontos_metodologia_antiga = 0
    metodologias_desatualizadas = []
    versoes = Counter()
    ultimo = None
    for linha in linhas:
        identificador = int(linha["id"])
        mercado = str(linha["mercado"])
        chave = (
            str(linha["regra_versao"]),
            mercado,
            int(linha["ultimo_sinal_id"]),
        )
        if chave in chaves:
            duplicadas.append(identificador)
        chaves.add(chave)
        mercados.add(mercado)
        registrado_em = linha["registrado_em"]
        if ultimo is None or str(registrado_em) > str(ultimo):
            ultimo = registrado_em
        try:
            avaliacao = json.loads(linha["avaliacao_json"])
        except (TypeError, json.JSONDecodeError):
            json_invalidos.append(identificador)
            continue
        base = avaliacao.get("base")
        versao_presente = "versao_avaliacao" in avaliacao
        versao = str(avaliacao.get("versao_avaliacao") or "ausente")
        versoes[versao] += 1
        if not versao_presente:
            legado_sem_versao.append(identificador)
        if versao == VERSAO_AVALIACAO_CONTEXTO:
            prontos += int(bool(linha["pronto_para_revisao"]))
        else:
            metodologias_desatualizadas.append(identificador)
            prontos_metodologia_antiga += int(
                bool(linha["pronto_para_revisao"])
            )
        chave_payload = (
            avaliacao.get("chave_historico_estado")
            if versao == VERSAO_AVALIACAO_CONTEXTO
            else avaliacao.get("ultimo_sinal_id")
        )
        coerente = bool(
            isinstance(avaliacao, dict)
            and isinstance(base, dict)
            and avaliacao.get("regra_versao")
                == linha["regra_versao"]
            and int(chave_payload or 0)
                == int(linha["ultimo_sinal_id"])
            and int(base.get("amostra") or 0) == int(linha["amostra"])
            and str(base.get("estado") or "inconclusiva")
                == str(linha["estado"])
            and int(bool(avaliacao.get("pronto_para_revisao")))
                == int(bool(linha["pronto_para_revisao"]))
            and (
                not versao_presente
                or bool(avaliacao.get("versao_avaliacao"))
            )
        )
        if not coerente:
            divergentes.append(identificador)
    saudavel = not (
        json_invalidos or divergentes or duplicadas
    )
    return {
        "saudavel": saudavel,
        "estado": "integro" if saudavel else "inconsistente",
        "motivo": (
            None if saudavel
            else "historico_avaliacao_contexto_inconsistente"
        ),
        "total": len(linhas),
        "mercados": len(mercados),
        "ultimo": ultimo,
        "prontos": prontos,
        "prontos_metodologia_antiga": prontos_metodologia_antiga,
        "versoes": dict(versoes),
        "metodologias_desatualizadas": metodologias_desatualizadas,
        "json_invalidos": json_invalidos,
        "divergentes": divergentes,
        "duplicadas": duplicadas,
        "legado_sem_versao": legado_sem_versao,
    }
