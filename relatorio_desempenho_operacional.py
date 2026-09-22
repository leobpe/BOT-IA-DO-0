"""Desempenho auditável por rota de entrega e janela temporal.

O relatório separa sinais oficiais, sinais enviados ao grupo de validação,
decisões bloqueadas e simulações não enviadas. A separação evita comparar
populações diferentes ou contar a mesma decisão mais de uma vez.
"""

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from backtest import calcular_metricas
from carteira_operacional import carregar_carteira_operacional_atual


PASTA = Path(__file__).parent


def _objeto_json(valor, padrao):
    if not valor:
        return padrao
    try:
        return json.loads(valor)
    except (TypeError, ValueError, json.JSONDecodeError):
        return padrao


def _metodo_operacional(linha):
    """Identifica a política específica que originou a decisão."""
    features = _objeto_json(linha.get("features_json"), {})
    exploracao = features.get("exploracao_sombra")
    if isinstance(exploracao, dict):
        versao = exploracao.get("versao")
        if isinstance(versao, str) and versao.strip():
            return versao.strip()
    return f"regra-base:{linha['regra_versao']}"


def _categoria_entrega(linha):
    features = _objeto_json(linha.get("features_json"), {})
    if linha["entrega_oficial"]:
        return "oficial"
    if linha["entrega_validacao"]:
        return "validacao_enviada"
    if linha["bloqueio_validacao"]:
        return "validacao_bloqueada"
    if linha["bloqueio_operacional"]:
        return "bloqueio_operacional"
    if isinstance(features.get("avaliacao_contrafactual"), dict):
        return "contrafactual_protecao"
    if linha["status"] == "simulacao":
        return "sombra_nao_enviada"
    return "rejeitada_sem_entrega"


def _metricas(itens):
    resolvidos = [
        item for item in itens if item.get("resultado") is not None
    ]
    pendentes = len(itens) - len(resolvidos)
    metricas = calcular_metricas(resolvidos)
    return {
        **metricas,
        "decisoes": len(itens),
        "resolvidos": len(resolvidos),
        "pendentes": pendentes,
    }


def _independentes(itens):
    vistos = set()
    resultado = []
    for item in sorted(itens, key=lambda valor: (
        valor["criado_em"], valor["id"]
    )):
        chave = (
            item["partida_id"],
            item["mercado"],
            item["regra_versao"],
            item["metodo_operacional"],
        )
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(item)
    return resultado


def _instante_comparavel(valor):
    try:
        instante = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None
    if instante.tzinfo is not None:
        instante = instante.astimezone().replace(tzinfo=None)
    return instante


def resumir_desempenho_operacional(
    conexao, desde, ate=None, *, incluir_carteira_atual=True,
):
    """Separa exposição real e amostra prospectiva independente."""
    filtros = ["datetime(s.criado_em) >= datetime(?)"]
    parametros = [desde]
    if ate is not None:
        filtros.append("datetime(s.criado_em) < datetime(?)")
        parametros.append(ate)
    linhas = conexao.execute(
        f"""
        SELECT s.id, s.partida_id, s.criado_em, s.mercado,
               s.regra_versao, s.regra_fingerprint, s.status, s.odd,
               s.motivos_json, s.features_json,
               r.resultado, r.retorno_unidades, r.encerrado_em,
               EXISTS (
                   SELECT 1 FROM entregas_alertas oficial
                   WHERE oficial.sinal_id=s.id
                     AND oficial.status='entregue'
                     AND oficial.provedor='telegram'
                     AND oficial.provedor_mensagem_id IS NOT NULL
                     AND oficial.canal NOT LIKE '%:%'
               ) AS entrega_oficial,
               EXISTS (
                   SELECT 1 FROM entregas_alertas teste
                   WHERE teste.sinal_id=s.id
                     AND teste.status='entregue'
                     AND teste.provedor='telegram'
                     AND teste.provedor_mensagem_id IS NOT NULL
                     AND teste.canal LIKE '%:teste'
                     AND teste.canal NOT LIKE '%:teste:%'
               ) AS entrega_validacao,
               EXISTS (
                   SELECT 1 FROM entregas_alertas bloqueio
                   WHERE bloqueio.sinal_id=s.id
                     AND bloqueio.canal='gateway:validacao'
                     AND bloqueio.status IN ('filtrado', 'bloqueado')
               ) AS bloqueio_validacao,
               EXISTS (
                   SELECT 1 FROM entregas_alertas bloqueio
                   WHERE bloqueio.sinal_id=s.id
                     AND bloqueio.canal LIKE 'gateway:%'
                     AND bloqueio.status IN ('filtrado', 'bloqueado')
               ) AS bloqueio_operacional
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE {' AND '.join(filtros)}
          AND (
              s.status IN ('aprovado', 'duplicado', 'simulacao')
              OR EXISTS (
                  SELECT 1 FROM entregas_alertas decisao
                  WHERE decisao.sinal_id=s.id
              )
          )
        ORDER BY s.criado_em, s.id
        """,
        tuple(parametros),
    ).fetchall()

    itens = []
    for linha in linhas:
        item = dict(linha)
        item["metodo_operacional"] = _metodo_operacional(item)
        item["categoria"] = _categoria_entrega(item)
        itens.append(item)

    por_categoria = defaultdict(list)
    por_mercado = defaultdict(lambda: defaultdict(list))
    por_regra = defaultdict(lambda: defaultdict(list))
    por_metodo = defaultdict(lambda: defaultdict(list))
    por_linhagem = defaultdict(lambda: defaultdict(list))
    for item in itens:
        categoria = item["categoria"]
        por_categoria[categoria].append(item)
        por_mercado[categoria][item["mercado"]].append(item)
        por_regra[categoria][item["regra_versao"]].append(item)
        por_metodo[categoria][item["metodo_operacional"]].append(item)
        chave_linhagem = (
            item["regra_versao"], item.get("regra_fingerprint")
        )
        por_linhagem[categoria][chave_linhagem].append(item)

    categorias = {}
    for categoria, registros in sorted(por_categoria.items()):
        independentes = _independentes(registros)
        categorias[categoria] = {
            **_metricas(registros),
            "amostra_independente": _metricas(independentes),
            "por_mercado": {
                mercado: _metricas(grupo)
                for mercado, grupo in sorted(
                    por_mercado[categoria].items()
                )
            },
            "por_regra": {
                regra: _metricas(grupo)
                for regra, grupo in sorted(por_regra[categoria].items())
            },
            "por_metodo": {
                metodo: _metricas(grupo)
                for metodo, grupo in sorted(
                    por_metodo[categoria].items()
                )
            },
            "por_linhagem": [
                {
                    "regra_versao": regra,
                    "regra_fingerprint": fingerprint,
                    **_metricas(grupo),
                }
                for (regra, fingerprint), grupo in sorted(
                    por_linhagem[categoria].items(),
                    key=lambda item: (
                        item[0][0], item[0][1] or ""
                    ),
                )
            ],
        }

    resultado = {
        "versao": "relatorio-desempenho-operacional-v4",
        "desde": desde,
        "ate": ate,
        "decisoes_auditadas": len(itens),
        "categorias": categorias,
    }
    if incluir_carteira_atual:
        carteira = carregar_carteira_operacional_atual(conexao)
        ativada_em = (carteira or {}).get("ativada_em")
        if carteira and ativada_em:
            inicio_solicitado = _instante_comparavel(desde)
            inicio_carteira = _instante_comparavel(ativada_em)
            desde_efetivo = ativada_em
            if (
                inicio_solicitado is not None
                and inicio_carteira is not None
                and inicio_solicitado > inicio_carteira
            ):
                desde_efetivo = desde
            desempenho = resumir_desempenho_operacional(
                conexao,
                desde_efetivo,
                ate,
                incluir_carteira_atual=False,
            )
            resultado["carteira_operacional_atual"] = {
                "versao": carteira.get("versao"),
                "fingerprint": carteira.get("fingerprint"),
                "ativada_em": ativada_em,
                "desde_efetivo": desde_efetivo,
                "mercados_operacionais": carteira.get(
                    "mercados_operacionais"
                ) or [],
                "versoes_por_mercado": carteira.get(
                    "versoes_por_mercado"
                ) or {},
                "desempenho": desempenho,
            }
    return resultado


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Separa desempenho oficial, validação, bloqueios e sombra."
        )
    )
    parser.add_argument("--dias", type=float, default=7.0)
    parser.add_argument("--ate")
    parser.add_argument(
        "--banco", default=str(PASTA / "monitor_packball.db")
    )
    argumentos = parser.parse_args()
    if argumentos.dias <= 0:
        parser.error("--dias deve ser maior que zero")
    ate = (
        datetime.fromisoformat(argumentos.ate)
        if argumentos.ate else datetime.now()
    )
    desde = ate - timedelta(days=argumentos.dias)
    caminho = Path(argumentos.banco).resolve()
    conexao = sqlite3.connect(
        f"file:{caminho.as_posix()}?mode=ro", uri=True, timeout=10
    )
    conexao.row_factory = sqlite3.Row
    try:
        resultado = resumir_desempenho_operacional(
            conexao,
            desde.replace(microsecond=0).isoformat(),
            ate.replace(microsecond=0).isoformat(),
        )
    finally:
        conexao.close()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
