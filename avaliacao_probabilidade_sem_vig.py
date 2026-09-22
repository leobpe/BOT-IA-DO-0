"""Avaliação histórica do preço justo implícito no mesmo snapshot.

O relatório é estritamente descritivo: não altera sinais, não promove regras
e não envia Telegram. A referência sem vig só existe quando o mercado
completo que originou a seleção pode ser reconstruído no mesmo snapshot. A
unidade primaria e a primeira observacao por partida e coorte de selecao,
fixada antes de consultar resultado ou cobertura. Coortes diferentes nunca
formam juntas um selo de vantagem, e cobertura inferior a 90% falha fechada.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from estatistica import intervalo_wilson
from normalizador_odds import estruturar_mercado
from valor_mercado import (
    anexar_par_odds_sincronizado,
    odd_oposta_sincronizada,
    referencia_tres_vias_sincronizada,
)
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)


VERSAO = "avaliacao-probabilidade-sem-vig-historica-v2"
BANCO = Path(__file__).with_name("monitor_packball.db")
RESULTADOS_VALIDOS = frozenset({
    "green", "half_green", "red", "half_red",
})
AMOSTRA_VANTAGEM_MINIMA = 100
COBERTURA_MINIMA_VANTAGEM = 0.90


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _json_objeto(valor):
    if isinstance(valor, dict):
        return valor
    try:
        carregado = json.loads(valor or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return carregado if isinstance(carregado, dict) else {}


def _gols_placar(valor):
    partes = str(valor or "").replace("x", "-").split("-")
    if len(partes) != 2:
        return None
    try:
        return sum(int(float(parte.strip())) for parte in partes)
    except (TypeError, ValueError):
        return None


def _mercado_estruturado(linha):
    """Combina o parser bruto com metadados persistidos sem apagar ofertas."""
    mercado = estruturar_mercado({
        "mercado": linha["mercado"],
        "dados": linha["dados"],
    })
    estrutura = _json_objeto(linha["estrutura_json"])
    for chave in (
        "categoria", "escopo", "tipo_mercado", "formato", "fonte",
        "bookmaker", "coletado_em", "recebido_em", "idade_segundos",
        "cache",
    ):
        if estrutura.get(chave) is not None:
            mercado[chave] = estrutura[chave]
    for chave in (
        "ofertas", "ofertas_exatamente", "ofertas_periodos",
        "ofertas_ht", "selecoes",
    ):
        if estrutura.get(chave):
            mercado[chave] = estrutura[chave]
    return mercado


def _chave_independente(item):
    coorte = _assinatura_coorte_selecao(item)
    # Estados sucessivos de proximo gol continuam correlacionados dentro da
    # mesma partida. A inferencia primaria usa uma unica unidade por jogo em
    # cada coorte de selecao; os demais estados permanecem no banco bruto.
    return (coorte, item["partida_id"])


def _assinatura_coorte_selecao(item):
    """Distingue regra oficial de exploracoes com selecao diferente."""
    status = str(item.get("status") or "status_desconhecido")
    features = item.get("features") or {}
    exploracao = features.get("exploracao_sombra")
    if status == "simulacao" and isinstance(exploracao, dict):
        return "sombra:" + str(
            exploracao.get("versao") or "sem_versao"
        ).strip()
    return status


def _carregar_sinais(conexao, mercado, regra_versao):
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.snapshot_id, s.criado_em,
               s.mercado, s.linha, s.odd, s.probabilidade_calibrada,
               s.status, s.features_json, snap.placar,
               r.resultado, r.retorno_unidades
        FROM sinais s
        JOIN snapshots snap ON snap.id=s.snapshot_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado=? AND s.regra_versao=?
          AND s.status IN ('aprovado', 'auditoria', 'simulacao')
        ORDER BY datetime(s.criado_em), s.id
        """,
        (mercado, regra_versao),
    ).fetchall()
    independentes = {}
    for linha in linhas:
        item = dict(linha)
        item["features"] = _json_objeto(item.pop("features_json", "{}"))
        independentes.setdefault(_chave_independente(item), item)

    validas = []
    invalidas = 0
    sem_resultado_valido = 0
    for item in independentes.values():
        item["resultado"] = str(item.get("resultado") or "").casefold()
        if item["resultado"] not in RESULTADOS_VALIDOS:
            sem_resultado_valido += 1
            continue
        item["odd"] = _numero(item.get("odd"))
        item["retorno_unidades"] = _numero(item.get("retorno_unidades"))
        if (
            item["odd"] is None
            or item["odd"] <= 1.0
            or item["retorno_unidades"] is None
        ):
            invalidas += 1
            continue
        validas.append(item)
    coortes_independentes = Counter(
        _assinatura_coorte_selecao(item)
        for item in independentes.values()
    )
    return validas, {
        "linhas_brutas_consultadas": len(linhas),
        "linhas_resultado_valido_brutas": sum(
            str(linha["resultado"] or "").casefold() in RESULTADOS_VALIDOS
            for linha in linhas
        ),
        "unidades_independentes": len(independentes),
        "resultados_validos_independentes": len(validas),
        "resultados_pendentes_ou_invalidos": sem_resultado_valido,
        "linhas_invalidas": invalidas,
        "resultados_independentes_completos": bool(
            sem_resultado_valido == 0
        ),
        "dados_resultados_validos": bool(invalidas == 0),
        "coortes_independentes": dict(coortes_independentes),
        "criterio_independencia": "coorte_selecao+partida",
        "selecao_antes_do_resultado": True,
    }


def _carregar_odds_snapshots(conexao, snapshot_ids):
    por_snapshot = defaultdict(list)
    ids = sorted({int(valor) for valor in snapshot_ids})
    for inicio in range(0, len(ids), 800):
        bloco = ids[inicio:inicio + 800]
        marcadores = ",".join("?" for _ in bloco)
        linhas = conexao.execute(
            f"""
            SELECT snapshot_id, tipo, mercado, dados, estrutura_json
            FROM odds
            WHERE snapshot_id IN ({marcadores}) AND tipo='ao_vivo'
            ORDER BY id
            """,
            bloco,
        ).fetchall()
        for linha in linhas:
            por_snapshot[int(linha["snapshot_id"])].append(
                _mercado_estruturado(linha)
            )
    return por_snapshot


def _probabilidade_sem_vig(candidato):
    referencia_tres = referencia_tres_vias_sincronizada(candidato)
    if referencia_tres:
        odds = referencia_tres["odds"]
        selecao = referencia_tres["selecao"]
        soma = sum(1.0 / valor for valor in odds.values())
        return {
            "probabilidade": (1.0 / odds[selecao]) / soma,
            "margem": soma - 1.0,
            "tipo": "tres_vias",
        }
    oposta = odd_oposta_sincronizada(candidato)
    odd = _numero(candidato.get("odd"))
    if oposta is None or odd is None:
        return None
    soma = 1.0 / odd + 1.0 / oposta
    return {
        "probabilidade": (1.0 / odd) / soma,
        "margem": soma - 1.0,
        "tipo": "binaria",
    }


def _intervalo_media(valores):
    valores = list(valores)
    if len(valores) < 2:
        return None
    media = statistics.fmean(valores)
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    return [round(media - 1.96 * erro, 6), round(media + 1.96 * erro, 6)]


def _rotulo_faixa(probabilidade):
    if probabilidade < 0.45:
        return "abaixo_45"
    if probabilidade < 0.55:
        return "45_a_54"
    if probabilidade < 0.65:
        return "55_a_64"
    return "65_ou_mais"


def _metricas(itens):
    itens = list(itens)
    probabilidades = [item["probabilidade_sem_vig"] for item in itens]
    observados = [item["observado"] for item in itens]
    retornos = [item["retorno_unidades"] for item in itens]
    residuos = [
        observado - probabilidade
        for observado, probabilidade in zip(observados, probabilidades)
    ]
    total = len(itens)
    greens = sum(observados)
    wilson = intervalo_wilson(greens, total)
    intervalo_residuo = _intervalo_media(residuos)
    intervalo_roi = _intervalo_media(retornos)
    retorno_total = sum(retornos)
    return {
        "amostra": total,
        "jogos": len({item["partida_id"] for item in itens}),
        "greens": greens,
        "reds": total - greens,
        "taxa_green": round(greens / total, 6) if total else None,
        "ic95_taxa_green": (
            [round(wilson[0], 6), round(wilson[1], 6)]
            if wilson else None
        ),
        "probabilidade_sem_vig_media": (
            round(statistics.fmean(probabilidades), 6)
            if probabilidades else None
        ),
        "desvio_observado_menos_mercado": (
            round(statistics.fmean(residuos), 6) if residuos else None
        ),
        "ic95_desvio_observado_menos_mercado": intervalo_residuo,
        "brier_mercado_sem_vig": (
            round(statistics.fmean([
                (observado - probabilidade) ** 2
                for observado, probabilidade
                in zip(observados, probabilidades)
            ]), 6)
            if itens else None
        ),
        "margem_bookmaker_media": (
            round(statistics.fmean([
                item["margem_bookmaker"] for item in itens
            ]), 6)
            if itens else None
        ),
        "lucro_unidades": round(retorno_total, 6),
        "roi": round(retorno_total / total, 6) if total else None,
        "ic95_roi": intervalo_roi,
    }


def avaliar_coorte(conexao, sinais):
    """Cruza uma coorte já definida com o mercado completo do snapshot."""
    sinais = list(sinais or [])
    odds_por_snapshot = _carregar_odds_snapshots(
        conexao, [item["snapshot_id"] for item in sinais]
    )
    avaliados = []
    exclusoes = Counter()
    for sinal in sinais:
        mercados = odds_por_snapshot.get(int(sinal["snapshot_id"]), [])
        if not mercados:
            exclusoes["snapshot_sem_odds_ao_vivo"] += 1
            continue
        candidato = {
            "mercado": sinal.get("mercado") or "proximo_gol",
            "linha": sinal.get("linha"),
            "odd": sinal["odd"],
            "fonte_odds": sinal["features"].get("fonte_odds"),
            "bookmaker_odds": sinal["features"].get("bookmaker_odds"),
            "features": dict(sinal["features"]),
        }
        if not anexar_par_odds_sincronizado(
            candidato, {"ao_vivo": mercados}
        ):
            exclusoes["mercado_exato_incompleto_ou_ambiguo"] += 1
            continue
        referencia = _probabilidade_sem_vig(candidato)
        if referencia is None:
            exclusoes["referencia_sem_vig_indisponivel"] += 1
            continue
        observado = 1 if sinal["resultado"] in {
            "green", "half_green"
        } else 0
        avaliados.append({
            **sinal,
            "sinal_id": int(sinal.get("sinal_id") or sinal["id"]),
            "partida_id": int(sinal["partida_id"]),
            "probabilidade_sem_vig": referencia["probabilidade"],
            "margem_bookmaker": referencia["margem"],
            "tipo_referencia": referencia["tipo"],
            "observado": observado,
            "retorno_unidades": sinal["retorno_unidades"],
        })

    por_faixa = {}
    agrupadas = defaultdict(list)
    for item in avaliados:
        agrupadas[_rotulo_faixa(item["probabilidade_sem_vig"])].append(item)
    for faixa in ("abaixo_45", "45_a_54", "55_a_64", "65_ou_mais"):
        if agrupadas.get(faixa):
            por_faixa[faixa] = _metricas(agrupadas[faixa])

    return {
        "tamanho_coorte": len(sinais),
        "cobertura_referencia_sem_vig": len(avaliados),
        "taxa_cobertura": (
            round(len(avaliados) / len(sinais), 6) if sinais else None
        ),
        "exclusoes": dict(exclusoes),
        "metricas": _metricas(avaliados),
        "por_faixa_probabilidade_mercado": por_faixa,
        "itens": avaliados,
    }


def avaliar(conexao, mercado, regra_versao):
    sinais, auditoria = _carregar_sinais(
        conexao, mercado, regra_versao
    )
    coorte = avaliar_coorte(conexao, sinais)

    metricas = coorte["metricas"]
    coortes_selecao = Counter(auditoria["coortes_independentes"])
    coorte_homogenea = len(coortes_selecao) <= 1
    intervalo_residuo = metricas["ic95_desvio_observado_menos_mercado"]
    intervalo_roi = metricas["ic95_roi"]
    vantagem = bool(
        coorte_homogenea
        and
        auditoria["resultados_independentes_completos"]
        and auditoria["dados_resultados_validos"]
        and float(coorte.get("taxa_cobertura") or 0)
        >= COBERTURA_MINIMA_VANTAGEM
        and
        metricas["amostra"] >= AMOSTRA_VANTAGEM_MINIMA
        and intervalo_residuo is not None
        and intervalo_residuo[0] > 0
        and intervalo_roi is not None
        and intervalo_roi[0] > 0
    )
    return {
        "versao": VERSAO,
        "mercado": mercado,
        "regra_versao": regra_versao,
        "candidatos_consultados": auditoria["linhas_brutas_consultadas"],
        "resolvidas_consultadas": auditoria[
            "linhas_resultado_valido_brutas"
        ],
        "linhas_invalidas": auditoria["linhas_invalidas"],
        "estados_independentes": len(sinais),
        "unidades_independentes": auditoria["unidades_independentes"],
        "resultados_pendentes_ou_invalidos": auditoria[
            "resultados_pendentes_ou_invalidos"
        ],
        "auditoria_coorte": auditoria,
        "cobertura_referencia_sem_vig": coorte[
            "cobertura_referencia_sem_vig"
        ],
        "taxa_cobertura": coorte["taxa_cobertura"],
        "exclusoes": coorte["exclusoes"],
        "metricas": metricas,
        "por_faixa_probabilidade_mercado": coorte[
            "por_faixa_probabilidade_mercado"
        ],
        "coortes_selecao": dict(coortes_selecao),
        "coorte_homogenea": coorte_homogenea,
        "vantagem_estatistica_descritiva": vantagem,
        "criterio_vantagem": {
            "amostra_minima": AMOSTRA_VANTAGEM_MINIMA,
            "ic95_desvio_inferior_positivo": True,
            "ic95_roi_inferior_positivo": True,
            "coorte_selecao_homogenea": True,
            "resultados_independentes_completos": True,
            "dados_resultados_validos": True,
            "cobertura_minima": COBERTURA_MINIMA_VANTAGEM,
        },
        "criterio_independencia": "coorte_selecao+partida",
        "selecao_antes_do_resultado": True,
        "uso": "somente_avaliacao_historica_descritiva",
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def executar(caminho_banco=None, mercado=None, regra_versao=None):
    caminho = Path(caminho_banco or BANCO).resolve()
    mercado = mercado or "proximo_gol"
    regra_versao = regra_versao or VERSAO_PROXIMO_GOL_FILTRO_PRECISO
    with closing(sqlite3.connect(
        caminho.as_uri() + "?mode=ro", uri=True
    )) as conexao:
        conexao.row_factory = sqlite3.Row
        return avaliar(conexao, mercado, regra_versao)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--banco", default=str(BANCO))
    parser.add_argument("--mercado", default="proximo_gol")
    parser.add_argument(
        "--regra-versao", default=VERSAO_PROXIMO_GOL_FILTRO_PRECISO
    )
    argumentos = parser.parse_args()
    print(json.dumps(
        executar(
            argumentos.banco,
            argumentos.mercado,
            argumentos.regra_versao,
        ),
        ensure_ascii=False,
        indent=2,
    ))
