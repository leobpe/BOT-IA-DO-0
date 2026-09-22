"""Avaliação prospectiva e não operacional da estratégia de aguardar odd."""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from datetime import datetime

from acompanhamento_odd import avaliar_resultado_acompanhamento_odd
from custodia_avaliacao import ESTADO_CONCLUIDO, VERSAO_CUSTODIA
from estatistica import intervalo_wilson


VERSAO = "avaliacao-aguardar-odd-prospectiva-v6"
AMOSTRA_MINIMA = 30
JOGOS_MINIMOS = 10
CHAVE_ANCORA_PROSPECTIVA = (
    "avaliacao_acompanhamento_odd:prospectiva_v3:inicio"
)


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _carregar_json(valor, padrao):
    try:
        item = json.loads(valor or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return padrao
    return item if isinstance(item, type(padrao)) else padrao


def _obter_ou_criar_ancora_prospectiva(banco, ancora=None):
    """Congela o início da coorte V3 sem reclassificar o passado."""
    if ancora is not None:
        return str(ancora)
    agora = datetime.now().replace(microsecond=0).isoformat()
    with banco.conexao:
        banco.conexao.execute(
            """
            INSERT OR IGNORE INTO metadados (chave, valor)
            VALUES (?, ?)
            """,
            (CHAVE_ANCORA_PROSPECTIVA, agora),
        )
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (CHAVE_ANCORA_PROSPECTIVA,),
    ).fetchone()
    return str(linha["valor"] if linha is not None else agora)


def _instante_ordem(valor):
    try:
        instante = datetime.fromisoformat(str(valor or ""))
    except (TypeError, ValueError):
        return None
    if instante.tzinfo is None:
        instante = instante.astimezone()
    return instante.timestamp()


def _posterior_ou_igual(valor, referencia):
    atual = _instante_ordem(valor)
    inicio = _instante_ordem(referencia)
    return atual is not None and inicio is not None and atual >= inicio


def _cotacoes_rapidas_pos_alerta(cotacoes, aviso_em):
    """Mantém somente preços que o executor realmente podia observar."""
    aviso = _instante_ordem(aviso_em)
    if aviso is None:
        return []
    resultado = []
    for cotacao in cotacoes or []:
        observado = _instante_ordem(cotacao.get("consultado_em"))
        if (
            cotacao.get("metodo_coleta") == "api_rapida_sem_packball"
            and observado is not None
            and observado >= aviso
        ):
            resultado.append(cotacao)
    return resultado


def _primeiros_independentes(itens):
    """Evita que vários avisos do mesmo jogo estreitem a incerteza."""
    primeiros = {}
    ordenados = sorted(
        itens or [],
        key=lambda item: (
            _instante_ordem(item.get("aviso_em")) or float("inf"),
            int(item.get("sinal_id") or 0),
        ),
    )
    for item in ordenados:
        primeiros.setdefault(
            (int(item["partida_id"]), str(item["mercado"])), item
        )
    return list(primeiros.values())


def _intervalo_bootstrap_media_95(valores, repeticoes=2000):
    """IC percentil determinístico; informativo, nunca promove regra."""
    numeros = [float(valor) for valor in valores if valor is not None]
    if len(numeros) < 2:
        return None
    gerador = random.Random(20260901 + len(numeros))
    tamanho = len(numeros)
    medias = []
    for _ in range(int(repeticoes)):
        medias.append(sum(
            numeros[gerador.randrange(tamanho)] for _ in range(tamanho)
        ) / tamanho)
    medias.sort()
    inferior = medias[int(0.025 * (len(medias) - 1))]
    superior = medias[int(0.975 * (len(medias) - 1))]
    return [round(inferior, 4), round(superior, 4)]


def _mediana(valores):
    numeros = sorted(float(valor) for valor in valores if valor is not None)
    if not numeros:
        return None
    meio = len(numeros) // 2
    if len(numeros) % 2:
        return round(numeros[meio], 3)
    return round((numeros[meio - 1] + numeros[meio]) / 2.0, 3)


def _odd_exata_estrutura(mercado, linha, estrutura):
    fonte = str(estrutura.get("fonte") or "").strip() or None
    if mercado == "proximo_gol":
        selecoes = estrutura.get("selecoes") or {}
        odd = _numero(selecoes.get(str(linha)))
        if odd is None:
            odd = _numero(selecoes.get(linha))
        return odd, fonte
    linha_alvo = _numero(linha)
    if linha_alvo is None:
        return None, fonte
    grupos = [estrutura.get("ofertas") or []]
    grupos.append(estrutura.get("ofertas_ht") or [])
    periodos = estrutura.get("ofertas_periodos") or {}
    if isinstance(periodos, dict):
        for valor in periodos.values():
            if isinstance(valor, list):
                grupos.append(valor)
            elif isinstance(valor, dict):
                grupos.append(valor.get("ofertas") or [])
    for grupo in grupos:
        for oferta in grupo:
            if not isinstance(oferta, dict):
                continue
            try:
                mesma_linha = math.isclose(
                    float(oferta.get("linha")), linha_alvo, abs_tol=1e-9
                )
            except (TypeError, ValueError):
                mesma_linha = False
            if not mesma_linha:
                continue
            odd = _numero(oferta.get("over"))
            if odd is not None:
                return odd, str(
                    oferta.get("fonte") or fonte or ""
                ).strip() or None
    return None, fonte


def _trajetoria(banco, item, snapshot_limite_exclusivo=None):
    limite_id = (
        int(snapshot_limite_exclusivo)
        if snapshot_limite_exclusivo is not None else 2**63 - 1
    )
    cotacoes = [{
        "odd": _numero(item.get("odd")),
        "consultado_em": item.get("snapshot_em"),
        "fonte": item.get("fonte_odds"),
        "metodo_coleta": "primeiro_aviso",
    }]
    registros = banco.conexao.execute(
        """
        SELECT sp.id, sp.coletado_em, o.estrutura_json
        FROM snapshots sp
        JOIN odds o ON o.snapshot_id=sp.id
        WHERE sp.partida_id=? AND sp.id>=? AND sp.id<?
        ORDER BY sp.id, o.id
        """,
        (item["partida_id"], item["snapshot_id"], limite_id),
    ).fetchall()
    for registro in registros:
        estrutura = _carregar_json(registro["estrutura_json"], {})
        odd, fonte = _odd_exata_estrutura(
            item["mercado"], item.get("linha"), estrutura
        )
        if odd is not None:
            cotacoes.append({
                "odd": odd,
                "consultado_em": registro["coletado_em"],
                "fonte": fonte,
                "metodo_coleta": "snapshot",
            })
    limite_tempo = None
    if snapshot_limite_exclusivo is not None:
        linha = banco.conexao.execute(
            "SELECT coletado_em FROM snapshots WHERE id=?",
            (int(snapshot_limite_exclusivo),),
        ).fetchone()
        limite_tempo = linha["coletado_em"] if linha is not None else None
    parametros = [
        item["partida_id"],
        f"acompanhamento_odd:{int(item['sinal_id'])}",
    ]
    filtro_tempo = ""
    if limite_tempo is not None:
        filtro_tempo = " AND consultado_em<?"
        parametros.append(limite_tempo)
    observacoes = banco.conexao.execute(
        """
        SELECT fonte, consultado_em, oferta_json, metodo_coleta
        FROM observacoes_fontes_odds
        WHERE partida_id=? AND evidencia_referencia=?
          AND estado='oferta_monitorada'
        """ + filtro_tempo + " ORDER BY consultado_em, id",
        tuple(parametros),
    ).fetchall()
    for observacao in observacoes:
        payload = _carregar_json(observacao["oferta_json"], {})
        odd = _numero(payload.get("odd"))
        if odd is None or str(payload.get("mercado")) != item["mercado"]:
            continue
        if item["mercado"] == "proximo_gol":
            mesma_linha = str(payload.get("linha")) == str(item.get("linha"))
        else:
            try:
                mesma_linha = math.isclose(
                    float(payload.get("linha")), float(item.get("linha")),
                    abs_tol=1e-9,
                )
            except (TypeError, ValueError):
                mesma_linha = False
        if mesma_linha:
            cotacoes.append({
                "odd": odd,
                "consultado_em": observacao["consultado_em"],
                "fonte": observacao["fonte"],
                "metodo_coleta": observacao["metodo_coleta"],
            })
    unicas = {}
    for cotacao in cotacoes:
        odd = _numero(cotacao.get("odd"))
        if odd is None:
            continue
        chave = (
            str(cotacao.get("consultado_em") or ""),
            round(odd, 6),
            str(cotacao.get("fonte") or ""),
        )
        unicas[chave] = {**cotacao, "odd": odd}
    return sorted(
        unicas.values(), key=lambda x: str(x.get("consultado_em") or "")
    )


def _retorno(resultado, odd):
    odd = _numero(odd)
    if odd is None:
        return None
    return {
        "green": odd - 1.0,
        "half_green": (odd - 1.0) / 2.0,
        "push": 0.0,
        "void": 0.0,
        "half_red": -0.5,
        "red": -1.0,
    }.get(str(resultado or ""))


def _itens(banco, limite):
    return banco.conexao.execute(
        """
        SELECT s.id AS sinal_id, s.partida_id, s.snapshot_id,
               s.mercado, s.linha, s.odd, s.features_json,
               p.packball_url, p.mandante, p.visitante, p.liga,
               inicial.coletado_em AS snapshot_em,
               inicial.placar AS placar_inicial,
               inicial.status AS status_inicial,
               origem.canal AS canal_origem,
               origem.tentado_em AS aviso_em,
               CASE WHEN final.id IS NULL THEN 0 ELSE 1 END AS finalizado
        FROM sinais s
        JOIN partidas p ON p.id=s.partida_id
        JOIN snapshots inicial ON inicial.id=s.snapshot_id
        JOIN entregas_alertas origem
          ON origem.sinal_id=s.id
         AND origem.status IN ('entregue', 'monitoramento_silencioso')
         AND origem.canal LIKE '%:aguardar_odd'
        LEFT JOIN entregas_alertas final
          ON final.sinal_id=s.id
         AND final.canal=origem.canal || ':monitoramento_final'
         AND final.status IN ('entregue', 'suprimido')
        ORDER BY s.id DESC
        LIMIT ?
        """,
        (min(max(int(limite), 1), 2000),),
    ).fetchall()


def avaliar_estrategia_acompanhamento_odd(
    banco, limite=500, ancora_prospectiva=None,
):
    """Mede a espera de odd; nunca altera política, sinal ou calibração."""
    ancora_prospectiva = _obter_ou_criar_ancora_prospectiva(
        banco, ancora_prospectiva
    )
    detalhes = []
    por_mercado = defaultdict(lambda: {"conclusivos": 0, "greens": 0})
    for linha in _itens(banco, limite):
        item = dict(linha)
        features = _carregar_json(item.get("features_json"), {})
        acompanhamento = features.get("acompanhamento_odd") or {}
        item["fonte_odds"] = features.get("fonte_odds")
        historico = banco.historico_acompanhamento_odd(item["sinal_id"])
        desfecho = avaliar_resultado_acompanhamento_odd(item, historico)
        snapshot_limite = desfecho.get("snapshot_id") if desfecho else None
        trajetoria = _trajetoria(banco, item, snapshot_limite)
        trajetoria_rapida = _cotacoes_rapidas_pos_alerta(
            trajetoria, item.get("aviso_em")
        )
        odd_alvo = _numero(acompanhamento.get("odd_alvo"))
        odd_maxima = _numero(acompanhamento.get("odd_maxima_operacional"))
        primeira_faixa = next((
            cotacao for cotacao in trajetoria_rapida
            if odd_alvo is not None
            and cotacao["odd"] >= odd_alvo
            and (odd_maxima is None or cotacao["odd"] <= odd_maxima)
        ), None)
        canal = str(item.get("canal_origem") or "")
        sufixo = ":aguardar_odd"
        canal_base = canal[:-len(sufixo)] if canal.endswith(sufixo) else canal
        oficial = banco.entrada_oficial_apos_acompanhamento(
            item["sinal_id"], canal_base
        )
        resultado = desfecho.get("resultado") if desfecho else None
        retorno_inicial = _retorno(resultado, item.get("odd"))
        retorno_alvo = (
            _retorno(resultado, odd_alvo) if primeira_faixa else None
        )
        resultado_oficial = oficial["resultado"] if oficial else None
        odd_oficial = _numero(oficial["odd"]) if oficial else None
        evidencia_rapida = bool(trajetoria_rapida)
        prospectivo_elegivel = (
            evidencia_rapida
            and _posterior_ou_igual(
                item.get("aviso_em"), ancora_prospectiva
            )
        )
        segundos_ate_faixa = None
        if primeira_faixa is not None:
            inicio = _instante_ordem(item.get("aviso_em"))
            chegada = _instante_ordem(primeira_faixa.get("consultado_em"))
            if inicio is not None and chegada is not None:
                segundos_ate_faixa = max(chegada - inicio, 0.0)
        if resultado is not None:
            grupo = por_mercado[item["mercado"]]
            grupo["conclusivos"] += 1
            if resultado in {"green", "half_green"}:
                grupo["greens"] += 1
        detalhes.append({
            "sinal_id": int(item["sinal_id"]),
            "partida_id": int(item["partida_id"]),
            "mercado": item["mercado"],
            "resultado": resultado,
            "odd_inicial": _numero(item.get("odd")),
            "odd_alvo": odd_alvo,
            "atingiu_faixa": primeira_faixa is not None,
            "primeira_odd_faixa": (
                primeira_faixa.get("odd") if primeira_faixa else None
            ),
            "entrada_oficial": oficial is not None,
            "odd_oficial": odd_oficial,
            "resultado_oficial": resultado_oficial,
            "retorno_oficial": _retorno(resultado_oficial, odd_oficial),
            "evidencia_monitoramento_rapido": evidencia_rapida,
            "prospectivo_elegivel": prospectivo_elegivel,
            "aviso_em": item.get("aviso_em"),
            "primeira_faixa_em": (
                primeira_faixa.get("consultado_em")
                if primeira_faixa else None
            ),
            "segundos_ate_faixa": segundos_ate_faixa,
            "retorno_inicial": retorno_inicial,
            "retorno_aguardando_alvo": retorno_alvo,
            "cotacoes": len(trajetoria),
            "cotacoes_rapidas_pos_alerta": len(trajetoria_rapida),
        })

    conclusivos = [x for x in detalhes if x["resultado"] is not None]

    def resumir_coorte(coorte):
        executaveis = [x for x in coorte if x["atingiu_faixa"]]
        oficiais = [
            x for x in coorte
            if x["entrada_oficial"] and x["resultado_oficial"] is not None
        ]
        greens = sum(
            x["resultado"] in {"green", "half_green"} for x in coorte
        )
        greens_executaveis = sum(
            x["resultado"] in {"green", "half_green"}
            for x in executaveis
        )
        retornos_iniciais = [
            x["retorno_inicial"] for x in coorte
            if x["retorno_inicial"] is not None
        ]
        retornos_alvo = [
            x["retorno_aguardando_alvo"] for x in executaveis
            if x["retorno_aguardando_alvo"] is not None
        ]
        retornos_oficiais = [
            x["retorno_oficial"] for x in oficiais
            if x["retorno_oficial"] is not None
        ]
        retornos_espera_por_aviso = [
            (
                x["retorno_aguardando_alvo"]
                if x["atingiu_faixa"]
                and x["retorno_aguardando_alvo"] is not None
                else 0.0
            )
            for x in coorte
        ]
        deltas_estrategia = [
            retorno_espera - x["retorno_inicial"]
            for x, retorno_espera in zip(
                coorte, retornos_espera_por_aviso
            )
            if x["retorno_inicial"] is not None
        ]
        deltas_pareados = [
            x["retorno_aguardando_alvo"] - x["retorno_inicial"]
            for x in executaveis
            if x["retorno_aguardando_alvo"] is not None
            and x["retorno_inicial"] is not None
        ]
        ganhos_odd = [
            x["primeira_odd_faixa"] - x["odd_inicial"]
            for x in executaveis
            if x["primeira_odd_faixa"] is not None
            and x["odd_inicial"] is not None
        ]
        tempos_ate_faixa = [
            x["segundos_ate_faixa"] for x in executaveis
            if x["segundos_ate_faixa"] is not None
        ]
        intervalo = intervalo_wilson(
            greens_executaveis, len(executaveis)
        )
        jogos_coorte = {x["partida_id"] for x in coorte}
        return {
            "conclusivos": len(coorte),
            "jogos_distintos": len(jogos_coorte),
            "greens_hipoteticos": greens,
            "atingiram_faixa": len(executaveis),
            "taxa_conversao_faixa": (
                round(len(executaveis) / len(coorte), 4)
                if coorte else None
            ),
            "greens_apos_faixa": greens_executaveis,
            "greens_antes_do_alvo": sum(
                x["resultado"] in {"green", "half_green"}
                and not x["atingiu_faixa"] for x in coorte
            ),
            "entradas_oficiais_convertidas": len(oficiais),
            "atingiram_faixa_sem_envio_oficial": sum(
                x["atingiu_faixa"] and not x["entrada_oficial"]
                for x in coorte
            ),
            "taxa_acerto_apos_faixa": (
                round(greens_executaveis / len(executaveis), 4)
                if executaveis else None
            ),
            "wilson_95_apos_faixa": (
                [round(intervalo[0], 4), round(intervalo[1], 4)]
                if intervalo else None
            ),
            "roi_odd_inicial_hipotetico": (
                round(sum(retornos_iniciais) / len(retornos_iniciais), 4)
                if retornos_iniciais else None
            ),
            "roi_aguardando_alvo_hipotetico": (
                round(sum(retornos_alvo) / len(retornos_alvo), 4)
                if retornos_alvo else None
            ),
            "retorno_aguardando_alvo_por_aviso": (
                round(sum(retornos_alvo) / len(coorte), 4)
                if coorte else None
            ),
            "roi_espera_estrategia_por_aviso": (
                round(sum(retornos_espera_por_aviso) / len(coorte), 4)
                if coorte else None
            ),
            "ic95_bootstrap_roi_espera_por_aviso": (
                _intervalo_bootstrap_media_95(retornos_espera_por_aviso)
            ),
            "delta_roi_espera_vs_entrada_imediata": (
                round(sum(deltas_estrategia) / len(deltas_estrategia), 4)
                if deltas_estrategia else None
            ),
            "ic95_bootstrap_delta_roi_estrategia": (
                _intervalo_bootstrap_media_95(deltas_estrategia)
            ),
            "delta_roi_pareado_quando_faixa_atingida": (
                round(sum(deltas_pareados) / len(deltas_pareados), 4)
                if deltas_pareados else None
            ),
            "ic95_bootstrap_delta_roi_pareado": (
                _intervalo_bootstrap_media_95(deltas_pareados)
            ),
            "ganho_medio_odd_quando_faixa_atingida": (
                round(sum(ganhos_odd) / len(ganhos_odd), 4)
                if ganhos_odd else None
            ),
            "tempo_mediano_ate_faixa_segundos": _mediana(
                tempos_ate_faixa
            ),
            "roi_execucao_oficial_real": (
                round(sum(retornos_oficiais) / len(retornos_oficiais), 4)
                if retornos_oficiais else None
            ),
        }

    prospectivos_todos = [
        x for x in conclusivos if x["prospectivo_elegivel"]
    ]
    prospectivos = _primeiros_independentes(prospectivos_todos)
    historico_independente = _primeiros_independentes(conclusivos)
    por_mercado_prospectivo = defaultdict(
        lambda: {"conclusivos": 0, "greens": 0}
    )
    for item in prospectivos:
        grupo = por_mercado_prospectivo[item["mercado"]]
        grupo["conclusivos"] += 1
        if item["resultado"] in {"green", "half_green"}:
            grupo["greens"] += 1
    historico = resumir_coorte(conclusivos)
    historico_independente_resumo = resumir_coorte(
        historico_independente
    )
    prospectivo_todos_resumo = resumir_coorte(prospectivos_todos)
    prospectivo = resumir_coorte(prospectivos)
    oficiais_prospectivos = prospectivo["entradas_oficiais_convertidas"]
    pronto_estrategia = (
        prospectivo["conclusivos"] >= AMOSTRA_MINIMA
        and prospectivo["jogos_distintos"] >= JOGOS_MINIMOS
    )
    pronto_execucao = oficiais_prospectivos >= AMOSTRA_MINIMA
    intervalo_espera = prospectivo.get(
        "ic95_bootstrap_roi_espera_por_aviso"
    )
    vantagem_comprovada = bool(
        pronto_estrategia and intervalo_espera
        and intervalo_espera[0] > 0.0
    )
    desvantagem_comprovada = bool(
        pronto_estrategia and intervalo_espera
        and intervalo_espera[1] < 0.0
    )
    return {
        "versao": VERSAO,
        "custodia_execucao_versao": VERSAO_CUSTODIA,
        "estado_execucao": ESTADO_CONCLUIDO,
        "modo": "avaliacao_prospectiva",
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "avisos_total": len(detalhes),
        "coorte_decisoria": "monitoramento_rapido",
        "unidade_independente": "primeiro_aviso_por_partida_e_mercado",
        "criterio_execucao_faixa": (
            "primeira_cotacao_api_rapida_pos_alerta_na_mesma_linha"
        ),
        "criterio_vinculo_entrada_oficial": (
            "origem_sinal_id_exato_materializado_por_api_rapida_v1"
        ),
        "ancora_prospectiva_em": ancora_prospectiva,
        "criterio_coorte_prospectiva": (
            "aviso_criado_apos_ancora_e_monitorado_por_api_rapida"
        ),
        "historico_exploratorio": historico,
        "historico_exploratorio_independente": (
            historico_independente_resumo
        ),
        "coorte_prospectiva_rapida_todos_alertas": (
            prospectivo_todos_resumo
        ),
        "coorte_prospectiva_rapida": prospectivo,
        "estado": (
            "pronto_para_revisao_execucao"
            if pronto_execucao else
            "pronto_para_revisao_estrategia"
            if pronto_estrategia else
            "coorte_prospectiva_em_formacao"
        ),
        "pronto_para_revisao_estrategia": pronto_estrategia,
        "pronto_para_revisao_execucao": pronto_execucao,
        "vantagem_espera_comprovada": vantagem_comprovada,
        "desvantagem_espera_comprovada": desvantagem_comprovada,
        "promocao_automatica": False,
        "amostra_minima": AMOSTRA_MINIMA,
        "jogos_minimos": JOGOS_MINIMOS,
        "faltam_conclusivos_prospectivos": max(
            AMOSTRA_MINIMA - prospectivo["conclusivos"], 0
        ),
        "faltam_jogos_prospectivos": max(
            JOGOS_MINIMOS - prospectivo["jogos_distintos"], 0
        ),
        "faltam_execucoes_oficiais": max(
            AMOSTRA_MINIMA - oficiais_prospectivos, 0
        ),
        "recomendacao": (
            "revisar_vantagem_sem_aplicacao_automatica"
            if vantagem_comprovada else
            "revisar_desvantagem_sem_regressao_automatica"
            if desvantagem_comprovada else
            "revisao_independente_inconclusiva_sem_aplicacao_automatica"
            if pronto_estrategia else
            "continuar_coleta_sem_alterar_regra"
        ),
        "por_mercado_historico": dict(por_mercado),
        "por_mercado_prospectivo": dict(por_mercado_prospectivo),
        "detalhes": detalhes,
    }
