"""Aplica a avaliacao de CLV existente tambem a coorte de sombra.

O avaliacao_clv_live so enxerga sinais com entrega confirmada no Telegram.
Em 24/09/2026 isso eram 4 partidas liquidadas e instrumentadas, contra 122
na coorte de simulacao - que ja passa das 120 planejadas. A amostra existe
no banco e o avaliador nao a alcanca por causa do filtro de entrega.

Este modulo reaproveita avaliar_sinal do modulo original sem alterar uma
linha da medicao: mesma janela de 2 a 10 minutos, mesma extracao de
cotacao, mesma remocao de vig. Muda apenas a porta de entrada.

A janela curta e deliberada e esta correta. Uma tentativa de medir contra
a ultima cotacao antes da liquidacao foi feita e descartada: ao vivo, o
preco final reflete o tempo que passou, nao informacao nova, e o resultado
ficou dominado por decaimento temporal. CLV de fechamento e conceito de
mercado pre-jogo, onde a pergunta nao muda entre abertura e fechamento.

Somente leitura: nao gera sinal, nao envia Telegram, nao altera politica e
nao grava nada.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from statistics import median

from avaliacao_clv_live import (
    MERCADOS_SUPORTADOS,
    avaliar_sinal,
)

VERSAO = "avaliacao-clv-coorte-sombra-v1"
BANCO = Path(__file__).with_name("monitor_packball.db")

# Antes disto nao havia cotacao de entrada congelada; sem ela nao ha
# comparacao de preco possivel, e o historico anterior e irrecuperavel.
PRIMEIRO_SINAL_INSTRUMENTADO = 379434

COORTES = {
    "sombra": ("simulacao",),
    "auditoria": ("auditoria",),
}

EFEITOS_DESATIVADOS = {
    "aplicacao_sinais": False,
    "telegram": False,
    "calibracao": False,
    "promocao_automatica": False,
}

RESSALVAS = (
    "sombra nao passou pelos portoes de entrega: mede a qualidade do sinal,"
    " nao da entrega, e nao substitui a coorte entregue",
    "uma unidade por partida; sinais da mesma partida sao correlacionados",
    "CLV e estimador de edge, nao substitui ROI em holdout",
)


def carregar_sinais_coorte(conexao, status):
    """Sinais liquidados de uma coorte, no formato que avaliar_sinal espera.

    O canal termina em ':sombra' para que avaliar_sinal marque canal_teste e
    o resultado nunca seja confundido com uma entrega real.
    """
    marcadores = ",".join("?" for _ in status)
    linhas = conexao.execute(
        f"""
        SELECT s.id,s.partida_id,s.snapshot_id,s.criado_em,s.mercado,
               s.linha,s.odd,s.status,s.regra_versao,s.features_json,
               snap.placar,snap.estatisticas_json,
               s.criado_em AS entregue_em
        FROM sinais s
        JOIN snapshots snap ON snap.id=s.snapshot_id
        JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.id>=?
          AND s.status IN ({marcadores})
          AND r.encerrado_em IS NOT NULL
        ORDER BY s.id
        """,
        (PRIMEIRO_SINAL_INSTRUMENTADO, *status),
    ).fetchall()
    sinais = []
    for linha in linhas:
        item = dict(linha)
        if item.get("mercado") not in MERCADOS_SUPORTADOS:
            continue
        item["canal"] = f"coorte:{item['status']}:sombra"
        sinais.append(item)
    return sinais


def _metricas(valores):
    if not valores:
        return {"unidades": 0, "estado_evidencia": "amostra_insuficiente"}
    positivos = sum(1 for v in valores if v > 0)
    media = sum(valores) / len(valores)
    # Intervalo de 95% pela normal; com dezenas de unidades ja e razoavel,
    # e a alternativa seria sugerir precisao que a amostra nao tem.
    desvio = (
        sum((v - media) ** 2 for v in valores) / (len(valores) - 1)
    ) ** 0.5 if len(valores) > 1 else None
    margem = (
        1.96 * desvio / (len(valores) ** 0.5) if desvio is not None else None
    )
    return {
        "unidades": len(valores),
        "media_pontos_probabilidade": round(media, 6),
        "mediana_pontos_probabilidade": round(median(valores), 6),
        "proporcao_movimento_favoravel": round(positivos / len(valores), 4),
        "intervalo_media_95": (
            [round(media - margem, 6), round(media + margem, 6)]
            if margem is not None else None
        ),
        "estado_evidencia": (
            "amostra_insuficiente" if len(valores) < 30 else "amostra_suficiente"
        ),
    }


def _por_partida(itens):
    """Uma unidade por partida: fica o primeiro sinal, que e o que a entrada
    teria pego. Escolher o melhor da partida seria selecao pelo resultado."""
    vistos = {}
    for item in sorted(itens, key=lambda i: i["sinal_id"]):
        vistos.setdefault(item.get("partida_id"), item)
    return list(vistos.values())


def avaliar_coorte(conexao, status):
    sinais = carregar_sinais_coorte(conexao, status)
    itens = [avaliar_sinal(conexao, sinal) for sinal in sinais]
    comparaveis = [
        item for item in itens
        if item.get("estado") == "comparavel"
        and item.get("clv_probabilidade_pontos") is not None
    ]

    motivos = {}
    for item in itens:
        if item.get("estado") != "comparavel":
            motivo = str(item.get("motivo") or item.get("estado"))
            motivos[motivo] = motivos.get(motivo, 0) + 1

    unidades = _por_partida(comparaveis)
    por_mercado = {}
    for mercado in sorted({i.get("mercado") for i in unidades}):
        por_mercado[mercado] = _metricas([
            float(i["clv_probabilidade_pontos"])
            for i in unidades if i.get("mercado") == mercado
        ])

    return {
        "sinais_liquidados": len(sinais),
        "sinais_comparaveis": len(comparaveis),
        "partidas": len(unidades),
        "motivos_nao_comparavel": dict(
            sorted(motivos.items(), key=lambda p: -p[1])
        ),
        "por_partida": _metricas([
            float(i["clv_probabilidade_pontos"]) for i in unidades
        ]),
        "por_mercado_e_partida": por_mercado,
    }


def avaliar(conexao):
    return {
        "versao": VERSAO,
        "ressalvas": list(RESSALVAS),
        "coortes": {
            nome: avaliar_coorte(conexao, status)
            for nome, status in COORTES.items()
        },
        **EFEITOS_DESATIVADOS,
    }


def executar(caminho_banco=None):
    caminho = Path(caminho_banco or BANCO)
    if not caminho.exists():
        return {"versao": VERSAO, "erro": "banco_ausente", **EFEITOS_DESATIVADOS}
    uri = caminho.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as conexao:
        conexao.row_factory = sqlite3.Row
        return avaliar(conexao)


if __name__ == "__main__":
    print(json.dumps(executar(), ensure_ascii=False, indent=2))
