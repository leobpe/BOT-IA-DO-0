"""Analise reproduzivel para aliviar o Proximo Gol sem remover protecoes.

O estudo usa somente decisoes da regra V10f que ja possuem resultado. As
auditorias silenciosas entram apenas quando o unico bloqueio original era um
dos dois limiares estudados (qualidade ou pressao). Qualquer bloqueio de
atividade, chute, frescor de odd, placar, cartao ou fonte continua excluindo a
entrada. O modulo e somente leitura e nunca promove uma regra sozinho.
"""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path

from estatistica import intervalo_wilson
from avaliacao_probabilidade_sem_vig import avaliar_coorte
from politica_proximo_gol_preciso import (
    MINUTO_MAXIMO,
    MOTIVO_PRESSAO,
    MOTIVO_QUALIDADE,
    ODD_MAXIMA_EXCLUSIVA,
)
from proximo_gol_balanceado_sombra import (
    ODD_MAXIMA_BALANCEADA_EXCLUSIVA,
    PONTUACAO_TECNICA_MINIMA,
    PRESSAO_MEDIA_DIFERENCA_MINIMA,
    PRESSAO_MINIMA,
    QUALIDADE_MINIMA_BALANCEADA,
)
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)


VERSAO = "analise-proximo-gol-balanceado-v2"
BANCO = Path(__file__).with_name("monitor_packball.db")
ODD_MINIMA = 1.40
STATUS_CONFIAVEIS = frozenset({"aprovado", "auditoria"})
BLOQUEIOS_RELAXAVEIS = frozenset({MOTIVO_QUALIDADE, MOTIVO_PRESSAO})
GRADE_PRE_REGISTRADA = tuple(
    (qualidade, pressao)
    for qualidade in (100.0, 98.0, 95.0, 90.0)
    for pressao in (70.0, 65.0, 60.0, 55.0, 50.0)
)


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _json_objeto(valor):
    try:
        item = json.loads(valor or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return item if isinstance(item, dict) else {}


def _json_lista(valor):
    try:
        item = json.loads(valor or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return item if isinstance(item, list) else []


def _gols_placar(placar):
    partes = str(placar or "").split("-")
    if len(partes) != 2:
        return None
    try:
        return sum(int(parte.strip()) for parte in partes)
    except (TypeError, ValueError):
        return None


def _pico_dominante(features):
    lado = features.get("lado_dominante")
    indice = 0 if lado == "casa" else 1 if lado == "visitante" else None
    picos = (((features.get("janelas") or {}).get("5") or {}).get(
        "pressao_pico"
    ) or [])
    if indice is None or not isinstance(picos, (list, tuple)):
        return None
    if len(picos) <= indice:
        return None
    return _numero(picos[indice])


def _valor_par_dominante(features, chave):
    lado = features.get("lado_dominante")
    indice = 0 if lado == "casa" else 1 if lado == "visitante" else None
    valores = (((features.get("janelas") or {}).get("5") or {}).get(
        chave
    ) or [])
    if indice is None or not isinstance(valores, (list, tuple)):
        return None, None
    if len(valores) < 2:
        return None, None
    return _numero(valores[indice]), _numero(valores[1 - indice])


def _metricas_api_dominante(features, contexto):
    lado = features.get("lado_dominante")
    chave = "mandante" if lado == "casa" else (
        "visitante" if lado == "visitante" else None
    )
    if chave is None:
        return {}, {}
    times = ((contexto.get("estatisticas_ao_vivo") or {}).get(
        "times"
    ) or {})
    return times.get(chave) or {}, times.get(
        "visitante" if chave == "mandante" else "mandante"
    ) or {}


def _bloqueios_originais(status, features, motivos):
    if status == "auditoria":
        auditoria = features.get("auditoria_bloqueio") or {}
        bloqueios = auditoria.get("bloqueios_originais") or []
        return frozenset(str(item).strip() for item in bloqueios if item)
    return frozenset(
        str(item).split("bloqueio:", 1)[1].strip()
        for item in motivos
        if str(item).startswith("bloqueio:")
    )


def normalizar_linha(linha):
    """Converte uma linha SQLite em uma oportunidade auditavel."""
    item = dict(linha)
    status = str(item.get("status") or "")
    if status not in STATUS_CONFIAVEIS:
        return None
    features = _json_objeto(item.get("features_json"))
    contexto = _json_objeto(item.get("contexto_api_json"))
    motivos = _json_lista(item.get("motivos_json"))
    bloqueios = _bloqueios_originais(status, features, motivos)
    bloqueios_base = bloqueios - BLOQUEIOS_RELAXAVEIS
    if bloqueios_base:
        return None

    gols_atuais = _numero(features.get("gols_atuais"))
    if gols_atuais is None:
        gols_atuais = _gols_placar(item.get("placar"))
    minuto = _numero(features.get("minuto"))
    qualidade = _numero(features.get("qualidade_dados"))
    odd = _numero(item.get("odd"))
    retorno = _numero(item.get("retorno_unidades"))
    pico = _pico_dominante(features)
    pressao_media, pressao_media_adversario = _valor_par_dominante(
        features, "pressao_media"
    )
    api_dominante, api_adversario = _metricas_api_dominante(
        features, contexto
    )
    if None in (gols_atuais, minuto, qualidade, odd, retorno, pico):
        return None
    return {
        "id": int(item["id"]),
        "partida_id": int(item["partida_id"]),
        "snapshot_id": int(item.get("snapshot_id") or item["id"]),
        "criado_em": str(item["criado_em"]),
        "mercado": "proximo_gol",
        "linha": item.get("linha"),
        "features": features,
        "status": status,
        "resultado": str(item["resultado"]).casefold(),
        "retorno_unidades": retorno,
        "odd": odd,
        "pontuacao_tecnica": _numero(item.get("pontuacao_tecnica")),
        "minuto": minuto,
        "qualidade": qualidade,
        "pressao_pico_5min": pico,
        "pressao_media_5min": pressao_media,
        "pressao_media_adversario_5min": pressao_media_adversario,
        "chutes_dominante_5min": _numero(
            features.get("chutes_lado_dominante_5min")
        ),
        "chutes_no_gol_dominante": _numero(
            api_dominante.get("chutes_no_gol")
        ),
        "chutes_no_gol_adversario": _numero(
            api_adversario.get("chutes_no_gol")
        ),
        "xg_dominante": _numero(api_dominante.get("xg")),
        "xg_adversario": _numero(api_adversario.get("xg")),
        "gols_atuais": int(gols_atuais),
        "bloqueios_relaxaveis": sorted(bloqueios & BLOQUEIOS_RELAXAVEIS),
    }


def carregar_linhas(conexao):
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.snapshot_id, s.criado_em,
               s.linha, s.odd, s.pontuacao_tecnica, s.status,
               s.motivos_json, s.features_json, snap.placar,
               snap.contexto_api_json,
               r.resultado, r.retorno_unidades
        FROM sinais s
        JOIN snapshots snap ON snap.id=s.snapshot_id
        JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado='proximo_gol'
          AND s.regra_versao=?
          AND lower(r.resultado) IN ('green', 'red')
        ORDER BY datetime(s.criado_em), s.id
        """,
        (VERSAO_PROXIMO_GOL_FILTRO_PRECISO,),
    ).fetchall()
    normalizadas = []
    for linha in linhas:
        item = normalizar_linha(linha)
        if item is not None:
            normalizadas.append(item)
    return normalizadas


def selecionar_oportunidades(
    linhas, *, qualidade_minima, pressao_minima, predicado=None,
):
    """Simula o primeiro alerta de cada estado de gols da partida.

    Enquanto o placar total nao muda, existe uma unica exposicao de proximo
    gol. Por isso a chave nao inclui o lado dominante: ela reproduz o bloqueio
    de exposicoes simultaneas usado no envio real.
    """
    selecionadas = {}
    for item in sorted(
        linhas, key=lambda valor: (valor["criado_em"], valor["id"])
    ):
        if not (
            item["minuto"] <= MINUTO_MAXIMO
            and ODD_MINIMA <= item["odd"] < ODD_MAXIMA_EXCLUSIVA
            and item["qualidade"] >= float(qualidade_minima)
            and item["pressao_pico_5min"] >= float(pressao_minima)
        ):
            continue
        if predicado is not None and not predicado(item):
            continue
        chave = (item["partida_id"], item["gols_atuais"])
        selecionadas.setdefault(chave, item)
    return list(selecionadas.values())


def selecionar_balanceado_sombra(linhas):
    return selecionar_oportunidades(
        linhas,
        qualidade_minima=QUALIDADE_MINIMA_BALANCEADA,
        pressao_minima=PRESSAO_MINIMA,
        predicado=lambda item: bool(
            MOTIVO_PRESSAO in set(
                item.get("bloqueios_relaxaveis") or []
            )
            and set(item.get("bloqueios_relaxaveis") or [])
            <= {MOTIVO_PRESSAO, MOTIVO_QUALIDADE}
            and item.get("chutes_dominante_5min") is not None
            and item["chutes_dominante_5min"] >= 1.0
            and item.get("pontuacao_tecnica") is not None
            and item["pontuacao_tecnica"] >= PONTUACAO_TECNICA_MINIMA
            and item.get("pressao_media_5min") is not None
            and item.get("pressao_media_adversario_5min") is not None
            and item["pressao_media_5min"]
            - item["pressao_media_adversario_5min"]
            >= PRESSAO_MEDIA_DIFERENCA_MINIMA
            and item["odd"] < ODD_MAXIMA_BALANCEADA_EXCLUSIVA
        ),
    )


def metricas(itens):
    itens = list(itens)
    greens = sum(item["resultado"] == "green" for item in itens)
    reds = sum(item["resultado"] == "red" for item in itens)
    total = greens + reds
    retorno = sum(float(item["retorno_unidades"]) for item in itens)
    intervalo = intervalo_wilson(greens, total)
    return {
        "amostra": total,
        "jogos": len({item["partida_id"] for item in itens}),
        "greens": greens,
        "reds": reds,
        "taxa_green": round(greens / total, 4) if total else None,
        "ic95_taxa_green": (
            [round(intervalo[0], 4), round(intervalo[1], 4)]
            if intervalo else None
        ),
        "lucro_unidades": round(retorno, 4),
        "roi": round(retorno / total, 4) if total else None,
    }


def avaliar_grade(linhas, grade=None):
    grade = tuple(grade or GRADE_PRE_REGISTRADA)
    saida = []
    for qualidade, pressao in grade:
        itens = selecionar_oportunidades(
            linhas,
            qualidade_minima=qualidade,
            pressao_minima=pressao,
        )
        saida.append({
            "qualidade_minima": qualidade,
            "pressao_minima": pressao,
            **metricas(itens),
        })
    return saida


def analisar(conexao):
    linhas = carregar_linhas(conexao)
    grade = avaliar_grade(linhas)
    estrito = sorted(
        selecionar_oportunidades(
            linhas, qualidade_minima=100.0, pressao_minima=70.0
        ),
        key=lambda item: (item["criado_em"], item["id"]),
    )
    balanceado = sorted(
        selecionar_balanceado_sombra(linhas),
        key=lambda item: (item["criado_em"], item["id"]),
    )
    preco_estrito = avaliar_coorte(conexao, estrito)
    preco_balanceado = avaliar_coorte(conexao, balanceado)
    preco_estrito.pop("itens", None)
    preco_balanceado.pop("itens", None)
    meio = len(balanceado) // 2
    corte_desenvolvimento = int(len(balanceado) * 0.70)
    return {
        "versao": VERSAO,
        "regra_origem": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
        "decisoes_resolvidas_modelaveis": len(linhas),
        "grade_pre_registrada": grade,
        "referencia_mercado_sem_vig": {
            "regra_estrita": preco_estrito,
            "hipotese_balanceada": preco_balanceado,
            "uso": "confirmacao_descritiva_sem_promocao",
        },
        "hipotese_balanceada_sombra": {
            **metricas(balanceado),
            "primeira_metade": metricas(balanceado[:meio]),
            "segunda_metade": metricas(balanceado[meio:]),
            "desenvolvimento_70": metricas(
                balanceado[:corte_desenvolvimento]
            ),
            "holdout_cronologico_30": metricas(
                balanceado[corte_desenvolvimento:]
            ),
            "criterios": {
                "qualidade_minima": QUALIDADE_MINIMA_BALANCEADA,
                "pressao_pico_5min_minima": PRESSAO_MINIMA,
                "vantagem_pressao_media_5min_minima": (
                    PRESSAO_MEDIA_DIFERENCA_MINIMA
                ),
                "chutes_dominante_5min_minimos": 1.0,
                "pontuacao_tecnica_minima": PONTUACAO_TECNICA_MINIMA,
                "odd_maxima_exclusiva": (
                    ODD_MAXIMA_BALANCEADA_EXCLUSIVA
                ),
            },
            "uso": "somente_geracao_de_hipotese",
            "promocao_automatica": False,
        },
        "criterio_independencia": "partida+total_gols_antes_do_proximo_gol",
        "bloqueios_base_preservados": True,
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
