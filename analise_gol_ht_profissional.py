"""Auditoria cronológica, somente leitura, da política principal de Gol HT.

A grade abaixo é deliberadamente pequena e baseada em critérios operacionais
interpretáveis. O relatório não muda regras: resultados servem apenas para
formular uma hipótese prospectiva separada.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from contextlib import closing
from pathlib import Path

from estatistica import intervalo_wilson
from versoes_operacionais import VERSAO_GOL_HT_MAX_28


VERSAO = "analise-gol-ht-profissional-v1"
BANCO = Path(__file__).with_name("monitor_packball.db")
RESULTADOS_VALIDOS = {"green", "half_green", "red", "half_red"}

# Identidade, minuto máximo, odd máxima exclusiva, chutes 5m, SOT total,
# pressão pico 5m e xG total. None significa sem restrição adicional.
GRADE_PRE_DECLARADA = (
    ("controle_atual", 28, None, None, None, None, None),
    ("atividade_1", 28, None, 1, None, None, None),
    ("atividade_2", 28, None, 2, None, None, None),
    ("atividade_2_sot3", 28, None, 2, 3, None, None),
    ("pressao70_atividade1", 28, None, 1, None, 70, None),
    ("pressao75_atividade2", 28, None, 2, None, 75, None),
    ("ate24_atividade1", 24, None, 1, None, None, None),
    ("odd190_atividade1", 28, 1.90, 1, None, None, None),
    ("odd180_atividade2", 28, 1.80, 2, None, None, None),
    ("xg08_atividade1", 28, None, 1, None, None, 0.80),
)


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _maximo_par(valor):
    if not isinstance(valor, (list, tuple)):
        return None
    numeros = [_numero(item) for item in valor]
    numeros = [item for item in numeros if item is not None]
    return max(numeros) if numeros else None


def _xg_total(contexto):
    times = (
        ((contexto or {}).get("estatisticas_ao_vivo") or {}).get("times")
        or {}
    )
    valores = [
        _numero((times.get(lado) or {}).get("xg"))
        for lado in ("mandante", "visitante")
    ]
    return sum(valores) if all(item is not None for item in valores) else None


def normalizar_linha(linha):
    try:
        features = json.loads(linha["features_json"] or "{}")
        contexto = json.loads(linha["contexto_api_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    janela5 = ((features.get("janelas") or {}).get("5") or {})
    item = {
        "id": int(linha["id"]),
        "partida_id": linha["partida_id"],
        "criado_em": linha["criado_em"],
        "resultado": str(linha["resultado"] or "").casefold(),
        "retorno_unidades": _numero(linha["retorno_unidades"]),
        "odd": _numero(linha["odd"]),
        "minuto": _numero(features.get("minuto")),
        "qualidade": _numero(features.get("qualidade_dados")),
        "chutes_5min": _numero(janela5.get("chutes_total")),
        "chutes_no_gol_total": _numero(
            features.get("chutes_no_gol_total")
        ),
        "pressao_pico_5min": _maximo_par(janela5.get("pressao_pico")),
        "xg_total": _xg_total(contexto),
    }
    obrigatorios = (
        "retorno_unidades", "odd", "minuto", "chutes_5min",
        "chutes_no_gol_total", "pressao_pico_5min",
    )
    if item["resultado"] not in RESULTADOS_VALIDOS or any(
        item[campo] is None for campo in obrigatorios
    ):
        return None
    return item


def carregar_linhas(conexao):
    linhas = conexao.execute(
        """
        WITH independentes AS (
          SELECT s.id,s.partida_id,s.criado_em,s.odd,s.features_json,
                 snapshot.contexto_api_json,r.resultado,r.retorno_unidades,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.partida_id
                   ORDER BY datetime(s.criado_em),s.id
                 ) AS ordem
          FROM sinais s
          JOIN snapshots snapshot ON snapshot.id=s.snapshot_id
          JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE s.mercado='gol_ht'
            AND s.regra_versao=?
            AND s.status='aprovado'
            AND lower(r.resultado) IN (
              'green','half_green','red','half_red'
            )
        )
        SELECT * FROM independentes WHERE ordem=1
        ORDER BY datetime(criado_em),id
        """,
        (VERSAO_GOL_HT_MAX_28,),
    ).fetchall()
    return [
        item for item in (normalizar_linha(linha) for linha in linhas)
        if item is not None
    ]


def selecionar(linhas, perfil):
    (_, minuto_maximo, odd_maxima, chutes_minimos, sot_minimos,
     pressao_minima, xg_minimo) = perfil
    selecionadas = []
    for item in linhas:
        if item["minuto"] > minuto_maximo:
            continue
        if odd_maxima is not None and item["odd"] >= odd_maxima:
            continue
        if (
            chutes_minimos is not None
            and item["chutes_5min"] < chutes_minimos
        ):
            continue
        if (
            sot_minimos is not None
            and item["chutes_no_gol_total"] < sot_minimos
        ):
            continue
        if (
            pressao_minima is not None
            and item["pressao_pico_5min"] < pressao_minima
        ):
            continue
        if xg_minimo is not None and (
            item["xg_total"] is None or item["xg_total"] < xg_minimo
        ):
            continue
        selecionadas.append(item)
    return selecionadas


def metricas(linhas):
    linhas = list(linhas)
    retornos = [item["retorno_unidades"] for item in linhas]
    greens = sum(
        item["resultado"] in {"green", "half_green"} for item in linhas
    )
    intervalo_green = intervalo_wilson(greens, len(linhas))
    intervalo_roi = None
    if len(retornos) >= 2:
        media = statistics.fmean(retornos)
        erro = statistics.stdev(retornos) / math.sqrt(len(retornos))
        intervalo_roi = [
            round(media - 1.96 * erro, 4),
            round(media + 1.96 * erro, 4),
        ]
    break_even = (
        statistics.fmean(1.0 / item["odd"] for item in linhas)
        if linhas else None
    )
    taxa = greens / len(linhas) if linhas else None
    lucro = sum(retornos)
    return {
        "amostra": len(linhas),
        "jogos": len({item["partida_id"] for item in linhas}),
        "greens": greens,
        "reds": len(linhas) - greens,
        "taxa_green": round(taxa, 4) if taxa is not None else None,
        "ic95_taxa_green": (
            [round(intervalo_green[0], 4), round(intervalo_green[1], 4)]
            if intervalo_green else None
        ),
        "break_even_medio": (
            round(break_even, 4) if break_even is not None else None
        ),
        "edge_taxa": (
            round(taxa - break_even, 4)
            if taxa is not None and break_even is not None else None
        ),
        "lucro_unidades": round(lucro, 4),
        "roi": round(lucro / len(linhas), 4) if linhas else None,
        "ic95_roi": intervalo_roi,
    }


def analisar(conexao):
    linhas = carregar_linhas(conexao)
    perfis = []
    for perfil in GRADE_PRE_DECLARADA:
        itens = selecionar(linhas, perfil)
        tamanho = len(itens)
        corte1 = tamanho // 3
        corte2 = 2 * tamanho // 3
        fatias = (
            metricas(itens[:corte1]),
            metricas(itens[corte1:corte2]),
            metricas(itens[corte2:]),
        )
        perfis.append({
            "perfil": perfil[0],
            "criterios": {
                "minuto_maximo": perfil[1],
                "odd_maxima_exclusiva": perfil[2],
                "chutes_5min_minimos": perfil[3],
                "chutes_no_gol_total_minimos": perfil[4],
                "pressao_pico_5min_minima": perfil[5],
                "xg_total_minimo": perfil[6],
            },
            **metricas(itens),
            "fatias_cronologicas": list(fatias),
            "fatias_roi_positivo": sum(
                (fatia["roi"] or 0.0) > 0.0 for fatia in fatias
            ),
        })
    return {
        "versao": VERSAO,
        "regra_origem": VERSAO_GOL_HT_MAX_28,
        "amostra_modelavel": len(linhas),
        "grade_pre_declarada": perfis,
        "criterio_independencia": "primeiro_sinal_por_partida",
        "somente_leitura": True,
        "altera_regra": False,
        "promocao_automatica": False,
    }


def executar(caminho_banco=None):
    caminho = Path(caminho_banco or BANCO).resolve()
    with closing(sqlite3.connect(
        caminho.as_uri() + "?mode=ro", uri=True
    )) as conexao:
        conexao.row_factory = sqlite3.Row
        return analisar(conexao)


if __name__ == "__main__":
    print(json.dumps(executar(), ensure_ascii=False, indent=2))

