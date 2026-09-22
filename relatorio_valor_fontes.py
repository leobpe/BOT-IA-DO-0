import argparse
import json
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from melhor_preco_sombra import VERSAO as VERSAO_MELHOR_PRECO_SOMBRA
from validacao_resultado_valor_justo import (
    resumir_validacao_resultado_valor_justo,
)


FONTES_CONHECIDAS = (
    "packball",
    "api_football",
    "betsapi",
    "thestatsapi",
    "the_odds_api",
    "sem_fonte",
)


def _tabela_existe(conexao, tabela):
    return conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (tabela,),
    ).fetchone() is not None


def _colunas_tabela(conexao, tabela):
    return {
        str(linha[1])
        for linha in conexao.execute(f"PRAGMA table_info({tabela})")
    }


def _fonte_normalizada(valor):
    texto = str(valor or "").strip().casefold()
    aliases = {
        "api-football": "api_football",
        "api_football": "api_football",
        "betsapi": "betsapi",
        "bets api": "betsapi",
        "thestats": "thestatsapi",
        "thestatsapi": "thestatsapi",
        "the odds api": "the_odds_api",
        "the_odds_api": "the_odds_api",
        "packball": "packball",
    }
    return aliases.get(texto, texto or "sem_fonte")


def _tem_atividade_coleta(valor):
    if isinstance(valor, dict):
        return any(_tem_atividade_coleta(item) for item in valor.values())
    if isinstance(valor, (list, tuple)):
        return any(_tem_atividade_coleta(item) for item in valor)
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor > 0
    return False


def _novo_resumo_exposicoes(**metadados):
    return {
        **metadados,
        "entregues": 0,
        "partidas_distintas": set(),
        "resolvidos": 0,
        "greens": 0,
        "reds": 0,
        "lucro_unidades": 0.0,
    }


def _acumular_exposicao(item, linha):
    item["entregues"] += 1
    item["partidas_distintas"].add(int(linha["partida_id"]))
    if linha["resultado"] not in (
        "green", "half_green", "red", "half_red"
    ):
        return
    item["resolvidos"] += 1
    item["greens"] += int(
        linha["resultado"] in ("green", "half_green")
    )
    item["reds"] += int(
        linha["resultado"] in ("red", "half_red")
    )
    if linha["retorno_unidades"] is not None:
        item["lucro_unidades"] += float(linha["retorno_unidades"])


def _finalizar_exposicao(item):
    item["partidas_distintas"] = len(item["partidas_distintas"])
    item["lucro_unidades"] = round(item["lucro_unidades"], 4)
    item["roi"] = (
        round(item["lucro_unidades"] / item["resolvidos"], 4)
        if item["resolvidos"] else None
    )
    item["taxa_acerto"] = (
        round(item["greens"] / item["resolvidos"], 4)
        if item["resolvidos"] else None
    )
    return item


def _modo_entrega(linha):
    if linha["entregue_oficial"]:
        return "oficial"
    if linha["entregue_teste"]:
        return "teste"
    return "outro"


def _resumir_sinais(conexao, desde):
    linhas = conexao.execute(
        """
        WITH base AS (
            SELECT
                s.id,
                s.partida_id,
                s.criado_em,
                s.status,
                s.odd,
                COALESCE(
                    json_extract(s.features_json, '$.fonte_odds'),
                    'sem_fonte'
                ) AS fonte,
                r.resultado,
                r.retorno_unidades,
                EXISTS (
                    SELECT 1 FROM entregas_alertas e
                    WHERE e.sinal_id=s.id AND e.status='entregue'
                      AND e.canal NOT LIKE 'gateway:%'
                      AND INSTR(e.canal, ':resultado')=0
                      AND INSTR(e.canal, ':green_antecipado')=0
                      AND INSTR(e.canal, ':aguardar_odd')=0
                      AND INSTR(e.canal, ':cancelamento')=0
                      AND INSTR(e.canal, ':insuficiente')=0
                      AND INSTR(e.canal, ':monitoramento_final')=0
                      AND INSTR(e.canal, ':correcao')=0
                ) AS entregue,
                EXISTS (
                    SELECT 1 FROM entregas_alertas e
                    WHERE e.sinal_id=s.id AND e.status='entregue'
                      AND e.canal LIKE '%:teste'
                ) AS entregue_teste,
                EXISTS (
                    SELECT 1 FROM entregas_alertas e
                    WHERE e.sinal_id=s.id AND e.status='entregue'
                      AND e.canal NOT LIKE '%:%'
                      AND e.canal NOT LIKE 'gateway:%'
                ) AS entregue_oficial
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE datetime(s.criado_em) >= datetime(?)
        )
        SELECT * FROM base ORDER BY id
        """,
        (desde,),
    ).fetchall()
    resumos = {}
    for linha in linhas:
        fonte = _fonte_normalizada(linha["fonte"])
        item = resumos.setdefault(fonte, {
            "candidatos": 0,
            "partidas_distintas": set(),
            "aprovados": 0,
            "simulacoes": 0,
            "entregues": 0,
            "entregues_teste": 0,
            "entregues_oficiais": 0,
            "resolvidos": 0,
            "greens": 0,
            "reds": 0,
            "lucro_unidades": 0.0,
            "entregues_resolvidos": 0,
            "entregues_greens": 0,
            "entregues_reds": 0,
            "entregues_lucro_unidades": 0.0,
            "odds": [],
            "primeiro_uso": None,
            "ultimo_uso": None,
        })
        item["candidatos"] += 1
        item["partidas_distintas"].add(int(linha["partida_id"]))
        item["aprovados"] += int(linha["status"] == "aprovado")
        item["simulacoes"] += int(linha["status"] == "simulacao")
        item["entregues"] += int(bool(linha["entregue"]))
        item["entregues_teste"] += int(bool(linha["entregue_teste"]))
        item["entregues_oficiais"] += int(bool(linha["entregue_oficial"]))
        if linha["resultado"] in ("green", "half_green", "red", "half_red"):
            item["resolvidos"] += 1
            item["greens"] += int(
                linha["resultado"] in ("green", "half_green")
            )
            item["reds"] += int(
                linha["resultado"] in ("red", "half_red")
            )
            if linha["retorno_unidades"] is not None:
                item["lucro_unidades"] += float(linha["retorno_unidades"])
            if linha["entregue"]:
                item["entregues_resolvidos"] += 1
                item["entregues_greens"] += int(
                    linha["resultado"] in ("green", "half_green")
                )
                item["entregues_reds"] += int(
                    linha["resultado"] in ("red", "half_red")
                )
                if linha["retorno_unidades"] is not None:
                    item["entregues_lucro_unidades"] += float(
                        linha["retorno_unidades"]
                    )
        if linha["odd"] is not None:
            try:
                item["odds"].append(float(linha["odd"]))
            except (TypeError, ValueError):
                pass
        criado_em = linha["criado_em"]
        item["primeiro_uso"] = item["primeiro_uso"] or criado_em
        item["ultimo_uso"] = criado_em
    for fonte in FONTES_CONHECIDAS:
        resumos.setdefault(fonte, {
            "candidatos": 0, "partidas_distintas": set(),
            "aprovados": 0, "simulacoes": 0, "entregues": 0,
            "entregues_teste": 0, "entregues_oficiais": 0,
            "resolvidos": 0, "greens": 0, "reds": 0,
            "lucro_unidades": 0.0, "odds": [],
            "entregues_resolvidos": 0,
            "entregues_greens": 0, "entregues_reds": 0,
            "entregues_lucro_unidades": 0.0,
            "primeiro_uso": None, "ultimo_uso": None,
        })
    for item in resumos.values():
        item["partidas_distintas"] = len(item["partidas_distintas"])
        resolvidos = item["resolvidos"]
        item["lucro_unidades"] = round(item["lucro_unidades"], 4)
        item["entregues_lucro_unidades"] = round(
            item["entregues_lucro_unidades"], 4
        )
        item["roi"] = (
            round(item["lucro_unidades"] / resolvidos, 4)
            if resolvidos else None
        )
        item["taxa_acerto"] = (
            round(item["greens"] / resolvidos, 4)
            if resolvidos else None
        )
        entregues_resolvidos = item["entregues_resolvidos"]
        item["entregues_roi"] = (
            round(
                item["entregues_lucro_unidades"] / entregues_resolvidos,
                4,
            )
            if entregues_resolvidos else None
        )
        item["entregues_taxa_acerto"] = (
            round(item["entregues_greens"] / entregues_resolvidos, 4)
            if entregues_resolvidos else None
        )
        item["odd_media"] = (
            round(sum(item["odds"]) / len(item["odds"]), 4)
            if item["odds"] else None
        )
        item.pop("odds", None)
    return resumos


def _resumir_ofertas_auxiliares(conexao, desde):
    resumo = {
        "thestatsapi": {
            "ofertas_persistidas": 0,
            "partidas_com_ofertas": 0,
        },
        "the_odds_api": {
            "consultas_persistidas": 0,
            "partidas_pareadas": 0,
        },
    }
    if _tabela_existe(conexao, "odds_thestatsapi_live"):
        linha = conexao.execute(
            """
            SELECT COUNT(*) total, COUNT(DISTINCT packball_url) partidas
            FROM odds_thestatsapi_live
            WHERE datetime(coletado_em) >= datetime(?)
            """,
            (desde,),
        ).fetchone()
        resumo["thestatsapi"] = {
            "ofertas_persistidas": int(linha["total"] or 0),
            "partidas_com_ofertas": int(linha["partidas"] or 0),
        }
    if _tabela_existe(conexao, "observacoes_fontes_odds"):
        possui_estado = "estado" in _colunas_tabela(
            conexao, "observacoes_fontes_odds"
        )
        estados = {}
        if possui_estado:
            linhas_estado = conexao.execute(
                """
                SELECT estado, COUNT(*) total,
                       COUNT(DISTINCT partida_id) partidas
                FROM observacoes_fontes_odds
                WHERE lower(fonte) IN ('the_odds_api', 'the odds api')
                  AND datetime(consultado_em) >= datetime(?)
                GROUP BY estado
                """,
                (desde,),
            ).fetchall()
            estados = {
                str(item["estado"]): {
                    "observacoes": int(item["total"] or 0),
                    "partidas": int(item["partidas"] or 0),
                }
                for item in linhas_estado
            }
        condicao_pareada = (
            "AND estado IN ('consultado_sem_oferta','oferta_disponivel')"
            if possui_estado else ""
        )
        linha = conexao.execute(
            f"""
            SELECT COUNT(*) total,
                   COUNT(DISTINCT CASE WHEN partida_id IS NOT NULL
                                       THEN partida_id END) partidas
            FROM observacoes_fontes_odds
            WHERE lower(fonte) IN ('the_odds_api', 'the odds api')
              AND datetime(consultado_em) >= datetime(?)
              {condicao_pareada}
            """,
            (desde,),
        ).fetchone()
        total_todas = sum(
            item["observacoes"] for item in estados.values()
        ) if estados else int(linha["total"] or 0)
        resumo["the_odds_api"] = {
            "observacoes_persistidas": total_todas,
            "consultas_persistidas": int(linha["total"] or 0),
            "partidas_pareadas": int(linha["partidas"] or 0),
            "por_estado": estados,
        }
    return resumo


def _resumir_entregas_por_fonte_mercado(conexao, desde):
    linhas = conexao.execute(
        """
        SELECT s.id, s.mercado, s.partida_id, s.odd, s.status,
               s.regra_versao, s.features_json,
               COALESCE(
                   json_extract(s.features_json, '$.fonte_odds'),
                   'sem_fonte'
               ) fonte,
               r.resultado, r.retorno_unidades,
               EXISTS (
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal LIKE '%:teste'
               ) entregue_teste,
               EXISTS (
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal NOT LIKE '%:%'
                     AND e.canal NOT LIKE 'gateway:%'
               ) entregue_oficial
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE datetime(s.criado_em) >= datetime(?)
          AND EXISTS (
              SELECT 1 FROM entregas_alertas e
              WHERE e.sinal_id=s.id AND e.status='entregue'
                AND e.canal NOT LIKE 'gateway:%'
                AND INSTR(e.canal, ':resultado')=0
                AND INSTR(e.canal, ':green_antecipado')=0
                AND INSTR(e.canal, ':aguardar_odd')=0
                AND INSTR(e.canal, ':cancelamento')=0
                AND INSTR(e.canal, ':insuficiente')=0
                AND INSTR(e.canal, ':monitoramento_final')=0
                AND INSTR(e.canal, ':correcao')=0
          )
        ORDER BY s.id
        """,
        (desde,),
    ).fetchall()
    resumo = {}
    for linha in linhas:
        fonte = _fonte_normalizada(linha["fonte"])
        mercado = str(linha["mercado"] or "desconhecido")
        item = resumo.setdefault(fonte, {}).setdefault(
            mercado,
            {
                **_novo_resumo_exposicoes(),
                "por_modo": {},
                "por_estrategia": {},
            },
        )
        modo = _modo_entrega(linha)
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        ramo = str(
            (features.get("exploracao_sombra") or {}).get("versao")
            or linha["regra_versao"] or "sem_estrategia"
        )
        status = str(linha["status"] or "desconhecido")
        chave_estrato = "|".join((
            str(linha["regra_versao"] or "sem_regra"),
            ramo,
            modo,
            status,
        ))
        por_modo = item["por_modo"].setdefault(
            modo, _novo_resumo_exposicoes(modo=modo)
        )
        por_estrategia = item["por_estrategia"].setdefault(
            chave_estrato,
            _novo_resumo_exposicoes(
                regra_versao=str(linha["regra_versao"] or "sem_regra"),
                estrategia=ramo,
                modo=modo,
                status=status,
            ),
        )
        for destino in (item, por_modo, por_estrategia):
            _acumular_exposicao(destino, linha)
    for mercados in resumo.values():
        for item in mercados.values():
            _finalizar_exposicao(item)
            for grupo in item["por_modo"].values():
                _finalizar_exposicao(grupo)
            for grupo in item["por_estrategia"].values():
                _finalizar_exposicao(grupo)
    return resumo


def _estratos_expostos_suficientes(entregas, fonte, minimo=30):
    encontrados = []
    for mercado, item in (entregas.get(fonte) or {}).items():
        for chave, estrato in (item.get("por_estrategia") or {}).items():
            if (
                estrato.get("resolvidos", 0) >= minimo
                and estrato.get("partidas_distintas", 0) >= minimo
            ):
                encontrados.append({
                    "mercado": mercado,
                    "estrato": chave,
                    "resolvidos": estrato["resolvidos"],
                    "partidas_distintas": estrato["partidas_distintas"],
                    "modo": estrato.get("modo"),
                    "status": estrato.get("status"),
                })
    return encontrados


def _intervalo_media_95(valores):
    valores = [float(valor) for valor in valores]
    if len(valores) < 2:
        return None
    media = sum(valores) / len(valores)
    variancia = sum(
        (valor - media) ** 2 for valor in valores
    ) / (len(valores) - 1)
    margem = 1.96 * math.sqrt(variancia / len(valores))
    return [round(media - margem, 6), round(media + margem, 6)]


def _novo_resumo_preco_pareado(**metadados):
    return {
        **metadados,
        "sinais_com_par_exato": 0,
        "partidas_distintas": set(),
        "pares_referencia_independente": 0,
        "partidas_independentes": set(),
        "pares_mesma_bookmaker": 0,
        "pares_bookmaker_parcial": 0,
        "preco_escolhido_melhor": 0,
        "preco_escolhido_equivalente": 0,
        "preco_escolhido_pior": 0,
        "resolvidos_independentes": 0,
        "lucro_observado_unidades": 0.0,
        "lucro_referencia_mesmo_resultado_unidades": 0.0,
        "deltas_odd_independentes": [],
        "ganhos_preco_realizados": [],
    }


def _bookmaker_normalizada(valor):
    return str(valor or "").strip().casefold()


def _lado_sinal_na_comparacao(linha, tolerancia=0.0015):
    fonte_sinal = _fonte_normalizada(linha["fonte_sinal"])
    bookmaker_sinal = _bookmaker_normalizada(linha["bookmaker_sinal"])
    try:
        odd_sinal = float(linha["odd_sinal"])
    except (TypeError, ValueError):
        return None
    encontrados = []
    for sufixo, outro in (("a", "b"), ("b", "a")):
        fonte = _fonte_normalizada(linha[f"fonte_{sufixo}"])
        bookmaker = _bookmaker_normalizada(
            linha[f"bookmaker_{sufixo}"]
        )
        try:
            odd = float(linha[f"odd_{sufixo}"])
            odd_referencia = float(linha[f"odd_{outro}"])
        except (TypeError, ValueError):
            continue
        if fonte != fonte_sinal or abs(odd - odd_sinal) > tolerancia:
            continue
        if bookmaker_sinal:
            if bookmaker != bookmaker_sinal:
                continue
        elif bookmaker:
            # Sem bookmaker no sinal, uma casa nominal não pode ser
            # atribuída retrospectivamente apenas por coincidência de odd.
            continue
        encontrados.append({
            "fonte_sinal": fonte,
            "bookmaker_sinal": bookmaker,
            "odd_sinal": odd_sinal,
            "fonte_referencia": _fonte_normalizada(
                linha[f"fonte_{outro}"]
            ),
            "bookmaker_referencia": _bookmaker_normalizada(
                linha[f"bookmaker_{outro}"]
            ),
            "odd_referencia": odd_referencia,
        })
    if len(encontrados) != 1:
        return None
    return encontrados[0]


def _qualidade_referencia_preco(lado, linha):
    fonte_distinta = lado["fonte_sinal"] != lado["fonte_referencia"]
    bookmakers_comprovadas = bool(
        lado["bookmaker_sinal"] and lado["bookmaker_referencia"]
    )
    bookmakers_distintas = (
        lado["bookmaker_sinal"] != lado["bookmaker_referencia"]
    )
    if (
        fonte_distinta
        and bookmakers_comprovadas
        and bookmakers_distintas
        and str(linha["compatibilidade_bookmaker"] or "")
        == "bookmakers_distintas"
    ):
        return "referencia_independente"
    if bookmakers_comprovadas and not bookmakers_distintas:
        return "mesma_bookmaker"
    return "bookmaker_parcial"


def _acumular_preco_pareado(item, par):
    item["sinais_com_par_exato"] += 1
    item["partidas_distintas"].add(int(par["partida_id"]))
    qualidade = par["qualidade_referencia"]
    if qualidade == "mesma_bookmaker":
        item["pares_mesma_bookmaker"] += 1
        return
    if qualidade != "referencia_independente":
        item["pares_bookmaker_parcial"] += 1
        return
    item["pares_referencia_independente"] += 1
    item["partidas_independentes"].add(int(par["partida_id"]))
    delta = float(par["odd_sinal"]) - float(par["odd_referencia"])
    item["deltas_odd_independentes"].append(delta)
    if delta > 0.005:
        item["preco_escolhido_melhor"] += 1
    elif delta < -0.005:
        item["preco_escolhido_pior"] += 1
    else:
        item["preco_escolhido_equivalente"] += 1
    pesos_resultado = {
        "green": 1.0,
        "half_green": 0.5,
        "red": 0.0,
        "half_red": 0.0,
        "void": 0.0,
    }
    resultado = str(par["resultado"] or "")
    if resultado not in pesos_resultado:
        return
    item["resolvidos_independentes"] += 1
    ganho_preco = delta * pesos_resultado[resultado]
    item["ganhos_preco_realizados"].append(ganho_preco)
    if par["retorno_unidades"] is not None:
        retorno = float(par["retorno_unidades"])
        item["lucro_observado_unidades"] += retorno
        item["lucro_referencia_mesmo_resultado_unidades"] += (
            retorno - ganho_preco
        )


def _finalizar_preco_pareado(item, minimo=30):
    item["partidas_distintas"] = len(item["partidas_distintas"])
    item["partidas_independentes"] = len(item["partidas_independentes"])
    deltas = item.pop("deltas_odd_independentes")
    ganhos = item.pop("ganhos_preco_realizados")
    item["delta_odd_medio"] = (
        round(sum(deltas) / len(deltas), 6) if deltas else None
    )
    item["intervalo_delta_odd_95"] = _intervalo_media_95(deltas)
    item["ganho_preco_realizado_unidades"] = round(sum(ganhos), 6)
    item["ganho_preco_medio_por_resolvido"] = (
        round(sum(ganhos) / len(ganhos), 6) if ganhos else None
    )
    item["intervalo_ganho_preco_95"] = _intervalo_media_95(ganhos)
    item["lucro_observado_unidades"] = round(
        item["lucro_observado_unidades"], 6
    )
    item["lucro_referencia_mesmo_resultado_unidades"] = round(
        item["lucro_referencia_mesmo_resultado_unidades"], 6
    )
    item["amostra_minima"] = minimo
    item["amostra_independente_suficiente"] = bool(
        item["pares_referencia_independente"] >= minimo
        and item["partidas_independentes"] >= minimo
    )
    intervalo = item["intervalo_ganho_preco_95"]
    item["vantagem_preco_confirmada"] = bool(
        item["amostra_independente_suficiente"]
        and intervalo
        and intervalo[0] > 0
    )
    return item


def _resumir_contribuicao_preco_pareada(conexao, desde, minimo=30):
    vazio = {
        "versao": "contribuicao-preco-pareada-sinal-v1",
        **_novo_resumo_preco_pareado(),
        "estado": "infraestrutura_ausente",
        "estratos_independentes_suficientes": [],
        "por_fonte": {},
        "por_mercado": {},
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    tabelas = (
        "sinais", "entregas_alertas", "comparacoes_odds_fontes",
    )
    if not all(_tabela_existe(conexao, tabela) for tabela in tabelas):
        return _finalizar_preco_pareado(vazio, minimo=minimo)
    colunas_sinais = _colunas_tabela(conexao, "sinais")
    if "snapshot_id" not in colunas_sinais:
        return _finalizar_preco_pareado(vazio, minimo=minimo)
    linhas = conexao.execute(
        """
        SELECT s.id sinal_id, s.snapshot_id, s.partida_id,
               s.mercado, s.linha linha_sinal, s.odd odd_sinal,
               s.status, s.regra_versao, s.features_json,
               COALESCE(
                   json_extract(s.features_json, '$.fonte_odds'),
                   'sem_fonte'
               ) fonte_sinal,
               COALESCE(
                   json_extract(s.features_json, '$.bookmaker_odds'),
                   ''
               ) bookmaker_sinal,
               r.resultado, r.retorno_unidades,
               EXISTS (
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal LIKE '%:teste'
               ) entregue_teste,
               EXISTS (
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal NOT LIKE '%:%'
                     AND e.canal NOT LIKE 'gateway:%'
               ) entregue_oficial,
               c.id comparacao_id, c.observado_em,
               c.fonte_a, c.bookmaker_a, c.odd_a,
               c.fonte_b, c.bookmaker_b, c.odd_b,
               c.intervalo_fontes_segundos,
               c.compatibilidade_bookmaker
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        JOIN comparacoes_odds_fontes c
          ON c.snapshot_id=s.snapshot_id
         AND c.categoria='gols'
         AND c.selecao='over'
         AND c.linha=CAST(s.linha AS REAL)
         AND (
              (s.mercado='gol_ft' AND c.periodo='FT')
              OR (s.mercado='gol_ht' AND c.periodo='1T')
         )
         AND c.estado IN (
             'comparavel_sem_desajuste', 'desajuste_candidato'
         )
        WHERE datetime(s.criado_em) >= datetime(?)
          AND s.mercado IN ('gol_ft', 'gol_ht')
          AND s.linha IS NOT NULL
          AND s.odd IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM entregas_alertas e
              WHERE e.sinal_id=s.id AND e.status='entregue'
                AND e.canal NOT LIKE 'gateway:%'
                AND INSTR(e.canal, ':resultado')=0
                AND INSTR(e.canal, ':green_antecipado')=0
                AND INSTR(e.canal, ':aguardar_odd')=0
                AND INSTR(e.canal, ':cancelamento')=0
                AND INSTR(e.canal, ':insuficiente')=0
                AND INSTR(e.canal, ':monitoramento_final')=0
                AND INSTR(e.canal, ':correcao')=0
          )
        ORDER BY s.id, c.id
        """,
        (desde,),
    ).fetchall()
    candidatos = {}
    for linha in linhas:
        lado = _lado_sinal_na_comparacao(linha)
        if lado is None or lado["fonte_sinal"] == lado["fonte_referencia"]:
            continue
        qualidade = _qualidade_referencia_preco(lado, linha)
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        estrategia = str(
            (features.get("exploracao_sombra") or {}).get("versao")
            or linha["regra_versao"] or "sem_estrategia"
        )
        modo = _modo_entrega(linha)
        par = {
            **lado,
            "sinal_id": int(linha["sinal_id"]),
            "partida_id": int(linha["partida_id"]),
            "mercado": str(linha["mercado"]),
            "status": str(linha["status"] or "desconhecido"),
            "regra_versao": str(
                linha["regra_versao"] or "sem_regra"
            ),
            "estrategia": estrategia,
            "modo": modo,
            "resultado": linha["resultado"],
            "retorno_unidades": linha["retorno_unidades"],
            "qualidade_referencia": qualidade,
            "intervalo_fontes_segundos": linha[
                "intervalo_fontes_segundos"
            ],
            "comparacao_id": int(linha["comparacao_id"]),
        }
        ranking_qualidade = {
            "referencia_independente": 0,
            "mesma_bookmaker": 1,
            "bookmaker_parcial": 2,
        }[qualidade]
        intervalo = linha["intervalo_fontes_segundos"]
        ranking = (
            ranking_qualidade,
            abs(float(intervalo)) if intervalo is not None else float("inf"),
            int(linha["comparacao_id"]),
        )
        atual = candidatos.get(par["sinal_id"])
        if atual is None or ranking < atual[0]:
            candidatos[par["sinal_id"]] = (ranking, par)
    resumo = vazio
    resumo["estado"] = "sem_par_exato"
    resumo["por_fonte"] = {}
    resumo["por_mercado"] = {}
    estratos = {}
    for _, par in sorted(candidatos.values(), key=lambda item: item[1]["sinal_id"]):
        fonte = par["fonte_sinal"]
        mercado = par["mercado"]
        chave_estrato = "|".join((
            par["regra_versao"], par["estrategia"],
            par["modo"], par["status"],
        ))
        por_fonte = resumo["por_fonte"].setdefault(
            fonte, _novo_resumo_preco_pareado(fonte=fonte)
        )
        por_mercado = resumo["por_mercado"].setdefault(
            mercado, _novo_resumo_preco_pareado(mercado=mercado)
        )
        estrato = estratos.setdefault(
            (fonte, mercado, chave_estrato),
            _novo_resumo_preco_pareado(
                fonte=fonte,
                mercado=mercado,
                estrato=chave_estrato,
                regra_versao=par["regra_versao"],
                estrategia=par["estrategia"],
                modo=par["modo"],
                status=par["status"],
            ),
        )
        for destino in (resumo, por_fonte, por_mercado, estrato):
            _acumular_preco_pareado(destino, par)
    for item in resumo["por_fonte"].values():
        _finalizar_preco_pareado(item, minimo=minimo)
    for item in resumo["por_mercado"].values():
        _finalizar_preco_pareado(item, minimo=minimo)
    estratos_suficientes = []
    for item in estratos.values():
        _finalizar_preco_pareado(item, minimo=minimo)
        if item["amostra_independente_suficiente"]:
            estratos_suficientes.append(item)
    _finalizar_preco_pareado(resumo, minimo=minimo)
    resumo["estratos_independentes_suficientes"] = estratos_suficientes
    if resumo["sinais_com_par_exato"]:
        resumo["estado"] = (
            "coletando_amostra_independente"
            if resumo["pares_referencia_independente"]
            else "sem_referencia_independente"
        )
    if estratos_suficientes:
        resumo["estado"] = "apto_revisao_preco"
    return resumo


def _novo_resumo_melhor_preco_prospectivo(**metadados):
    return {
        **metadados,
        "comparacoes_independentes": 0,
        "partidas_distintas": set(),
        "alternativa_melhor": 0,
        "escolhida_melhor": 0,
        "equivalentes": 0,
        "deltas_odd": [],
        "ganhos_retorno_bruto_percentual": [],
        "avaliacoes_valor_justo": 0,
        "desajustes_valor_justo_candidatos": 0,
        "partidas_valor_justo_distintas": set(),
        "valores_esperados_referencia": [],
    }


def _acumular_melhor_preco_prospectivo(item, observacao):
    item["comparacoes_independentes"] += 1
    item["partidas_distintas"].add(int(observacao["partida_id"]))
    relacao = observacao["relacao"]
    if relacao in ("alternativa_melhor", "escolhida_melhor", "equivalentes"):
        item[relacao] += 1
    item["deltas_odd"].append(float(observacao["diferenca_odd"]))
    ganho = observacao.get("ganho_retorno_bruto_percentual")
    if ganho is not None:
        item["ganhos_retorno_bruto_percentual"].append(float(ganho))
    valor_justo = observacao.get("valor_justo_sombra")
    if not isinstance(valor_justo, dict) or valor_justo.get("estado") not in {
        "sem_desajuste_favoravel", "desajuste_favoravel_candidato",
    }:
        return
    try:
        valor_esperado = float(valor_justo["valor_esperado_referencia"])
    except (KeyError, TypeError, ValueError):
        return
    if not math.isfinite(valor_esperado):
        return
    item["avaliacoes_valor_justo"] += 1
    item["partidas_valor_justo_distintas"].add(
        int(observacao["partida_id"])
    )
    item["valores_esperados_referencia"].append(valor_esperado)
    if valor_justo.get("desajuste_favoravel") is True:
        item["desajustes_valor_justo_candidatos"] += 1


def _finalizar_melhor_preco_prospectivo(item, minimo=30):
    item["partidas_distintas"] = len(item["partidas_distintas"])
    item["partidas_valor_justo_distintas"] = len(
        item["partidas_valor_justo_distintas"]
    )
    deltas = item.pop("deltas_odd")
    ganhos = item.pop("ganhos_retorno_bruto_percentual")
    valores_esperados = item.pop("valores_esperados_referencia")
    item["delta_odd_medio"] = (
        round(sum(deltas) / len(deltas), 6) if deltas else None
    )
    item["intervalo_delta_odd_95"] = _intervalo_media_95(deltas)
    item["ganho_retorno_bruto_potencial_medio_percentual"] = (
        round(sum(ganhos) / len(ganhos), 3) if ganhos else None
    )
    item["amostra_minima"] = int(minimo)
    item["amostra_independente_suficiente"] = bool(
        item["comparacoes_independentes"] >= int(minimo)
        and item["partidas_distintas"] >= int(minimo)
    )
    intervalo = item["intervalo_delta_odd_95"]
    item["alternativa_melhor_confirmada"] = bool(
        item["amostra_independente_suficiente"]
        and intervalo
        and intervalo[0] > 0
    )
    item["valor_esperado_referencia_medio"] = (
        round(sum(valores_esperados) / len(valores_esperados), 6)
        if valores_esperados else None
    )
    item["intervalo_valor_esperado_95"] = _intervalo_media_95(
        valores_esperados
    )
    item["amostra_valor_justo_suficiente"] = bool(
        item["avaliacoes_valor_justo"] >= int(minimo)
        and item["partidas_valor_justo_distintas"] >= int(minimo)
    )
    intervalo_valor = item["intervalo_valor_esperado_95"]
    item["vantagem_valor_justo_confirmada"] = bool(
        item["amostra_valor_justo_suficiente"]
        and intervalo_valor
        and intervalo_valor[0] > 0
    )
    item["estado_valor_justo"] = (
        "sem_evidencia_valor_justo"
        if not item["avaliacoes_valor_justo"]
        else "coletando_valor_justo"
        if not item["amostra_valor_justo_suficiente"]
        else "apto_revisao_valor_justo"
        if item["vantagem_valor_justo_confirmada"]
        else "sem_vantagem_valor_justo_confirmada"
    )
    return item


def _resumir_melhor_preco_prospectivo(conexao, desde, minimo=30):
    """Resume a coorte criada no instante da decisao, sem retrospectiva."""
    resumo = {
        "versao": "coorte-melhor-preco-exato-sombra-v6-resultado-prospectivo",
        **_novo_resumo_melhor_preco_prospectivo(),
        "estado": "sem_evidencia_prospectiva",
        "por_mercado": {},
        "por_fonte_escolhida": {},
        "estratos_independentes_suficientes": [],
        "estratos_valor_justo_aptos_revisao": [],
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    if not _tabela_existe(conexao, "sinais"):
        return _finalizar_melhor_preco_prospectivo(resumo, minimo=minimo)
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.mercado, s.status,
               s.regra_versao, s.features_json,
               EXISTS (
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal LIKE '%:teste'
               ) entregue_teste,
               EXISTS (
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal NOT LIKE '%:%'
                     AND e.canal NOT LIKE 'gateway:%'
               ) entregue_oficial
        FROM sinais s
        WHERE datetime(s.criado_em) >= datetime(?)
          AND json_valid(s.features_json)
          AND json_type(
              s.features_json, '$.melhor_preco_sombra'
          )='object'
        ORDER BY s.id
        """,
        (desde,),
    ).fetchall()
    por_partida_estrato = {}
    for linha in linhas:
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        sombra = features.get("melhor_preco_sombra") or {}
        if (
            sombra.get("versao") != VERSAO_MELHOR_PRECO_SOMBRA
            or sombra.get("estado") != "comparacao_independente_exata"
        ):
            continue
        escolhida = sombra.get("cotacao_escolhida") or {}
        alternativa = sombra.get("melhor_alternativa_independente") or {}
        try:
            diferenca = float(sombra["diferenca_odd"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(diferenca):
            continue
        relacao = str(sombra.get("relacao") or "")
        if relacao not in {
            "alternativa_melhor", "escolhida_melhor", "equivalentes"
        }:
            continue
        fonte_escolhida = _fonte_normalizada(escolhida.get("fonte"))
        bookmaker_escolhida = _bookmaker_normalizada(
            escolhida.get("bookmaker")
        )
        fonte_alternativa = _fonte_normalizada(alternativa.get("fonte"))
        bookmaker_alternativa = _bookmaker_normalizada(
            alternativa.get("bookmaker")
        )
        if (
            fonte_escolhida in {"sem_fonte", fonte_alternativa}
            or fonte_alternativa == "sem_fonte"
            or not bookmaker_escolhida
            or not bookmaker_alternativa
            or bookmaker_escolhida == bookmaker_alternativa
        ):
            continue
        estrategia = str(
            (features.get("exploracao_sombra") or {}).get("versao")
            or linha["regra_versao"] or "sem_estrategia"
        )
        modo = (
            "oficial" if linha["entregue_oficial"]
            else "teste" if linha["entregue_teste"]
            else "sem_entrega"
        )
        mercado = str(linha["mercado"] or "desconhecido")
        status = str(linha["status"] or "desconhecido")
        estrato = "|".join((
            str(linha["regra_versao"] or "sem_regra"),
            estrategia,
            modo,
            status,
            fonte_escolhida,
            bookmaker_escolhida,
            fonte_alternativa,
            bookmaker_alternativa,
        ))
        observacao = {
            "sinal_id": int(linha["id"]),
            "partida_id": int(linha["partida_id"]),
            "mercado": mercado,
            "fonte_escolhida": fonte_escolhida,
            "bookmaker_escolhida": bookmaker_escolhida,
            "fonte_alternativa": fonte_alternativa,
            "bookmaker_alternativa": bookmaker_alternativa,
            "regra_versao": str(linha["regra_versao"] or "sem_regra"),
            "estrategia": estrategia,
            "modo": modo,
            "status": status,
            "estrato": estrato,
            "relacao": relacao,
            "diferenca_odd": diferenca,
            "ganho_retorno_bruto_percentual": sombra.get(
                "ganho_retorno_bruto_potencial_percentual"
            ),
            "valor_justo_sombra": sombra.get("valor_justo_sombra"),
        }
        # Um jogo nao pode inflar a evidencia por ser reavaliado em varios
        # snapshots. Conservamos a primeira oportunidade de cada estrato.
        chave = (observacao["partida_id"], mercado, estrato)
        por_partida_estrato.setdefault(chave, observacao)

    estratos = {}
    for observacao in por_partida_estrato.values():
        mercado = observacao["mercado"]
        fonte = observacao["fonte_escolhida"]
        item_mercado = resumo["por_mercado"].setdefault(
            mercado,
            _novo_resumo_melhor_preco_prospectivo(mercado=mercado),
        )
        item_fonte = resumo["por_fonte_escolhida"].setdefault(
            fonte,
            _novo_resumo_melhor_preco_prospectivo(fonte=fonte),
        )
        chave_estrato = (
            mercado, observacao["fonte_escolhida"],
            observacao["estrato"],
        )
        item_estrato = estratos.setdefault(
            chave_estrato,
            _novo_resumo_melhor_preco_prospectivo(
                mercado=mercado,
                fonte_escolhida=observacao["fonte_escolhida"],
                bookmaker_escolhida=observacao["bookmaker_escolhida"],
                fonte_alternativa=observacao["fonte_alternativa"],
                bookmaker_alternativa=observacao[
                    "bookmaker_alternativa"
                ],
                regra_versao=observacao["regra_versao"],
                estrategia=observacao["estrategia"],
                modo=observacao["modo"],
                status=observacao["status"],
                estrato=observacao["estrato"],
            ),
        )
        for destino in (resumo, item_mercado, item_fonte, item_estrato):
            _acumular_melhor_preco_prospectivo(destino, observacao)

    for item in resumo["por_mercado"].values():
        _finalizar_melhor_preco_prospectivo(item, minimo=minimo)
    for item in resumo["por_fonte_escolhida"].values():
        _finalizar_melhor_preco_prospectivo(item, minimo=minimo)
    suficientes = []
    valor_justo_aptos = []
    for item in estratos.values():
        _finalizar_melhor_preco_prospectivo(item, minimo=minimo)
        if item["amostra_independente_suficiente"]:
            suficientes.append(item)
        if item["vantagem_valor_justo_confirmada"]:
            valor_justo_aptos.append(item)
    resumo["estratos_independentes_suficientes"] = suficientes
    resumo["estratos_valor_justo_aptos_revisao"] = valor_justo_aptos
    _finalizar_melhor_preco_prospectivo(resumo, minimo=minimo)
    if resumo["comparacoes_independentes"]:
        resumo["estado"] = "coletando_amostra_independente"
    if any(item["alternativa_melhor_confirmada"] for item in suficientes):
        resumo["estado"] = "apto_revisao_seletor_preco"
    return resumo


def _resumir_dependencia_dados_thestats(conexao, desde):
    linhas = conexao.execute(
        """
        SELECT s.id, s.mercado, s.features_json,
               r.resultado, r.retorno_unidades,
               EXISTS (
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal NOT LIKE '%:resultado'
               ) entregue
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE datetime(s.criado_em) >= datetime(?)
          AND json_type(s.features_json, '$.fusao_fontes')='object'
        ORDER BY s.id
        """,
        (desde,),
    ).fetchall()
    resumo = {
        "candidatos_expostos_fusao": 0,
        "candidatos_dependentes_fusao": 0,
        "dependentes_entregues": 0,
        "dependentes_resolvidos": 0,
        "dependentes_greens": 0,
        "dependentes_reds": 0,
        "dependentes_lucro_unidades": 0.0,
        "xg_disponivel": 0,
        "campos_complementados": {},
        "por_mercado": {},
    }
    for linha in linhas:
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        fusao = features.get("fusao_fontes") or {}
        if fusao.get("valida") is not True:
            continue
        resumo["candidatos_expostos_fusao"] += 1
        if fusao.get("xg") is not None or features.get("xg_thestatsapi") is not None:
            resumo["xg_disponivel"] += 1
        for campo in fusao.get("complementou") or []:
            campo = str(campo)
            resumo["campos_complementados"][campo] = (
                resumo["campos_complementados"].get(campo, 0) + 1
            )
        exploracao = (features.get("exploracao_sombra") or {}).get("versao")
        dependente = bool(
            fusao.get("modo") == "oficial_fail_closed"
            or exploracao == "fusao-packball-thestats-v1"
        )
        if not dependente:
            continue
        resumo["candidatos_dependentes_fusao"] += 1
        resumo["dependentes_entregues"] += int(bool(linha["entregue"]))
        mercado = str(linha["mercado"] or "desconhecido")
        item = resumo["por_mercado"].setdefault(mercado, {
            "candidatos_dependentes": 0,
            "entregues": 0,
            "resolvidos": 0,
            "greens": 0,
            "reds": 0,
            "lucro_unidades": 0.0,
        })
        item["candidatos_dependentes"] += 1
        item["entregues"] += int(bool(linha["entregue"]))
        if linha["resultado"] not in (
            "green", "half_green", "red", "half_red"
        ):
            continue
        resumo["dependentes_resolvidos"] += 1
        resumo["dependentes_greens"] += int(
            linha["resultado"] in ("green", "half_green")
        )
        resumo["dependentes_reds"] += int(
            linha["resultado"] in ("red", "half_red")
        )
        item["resolvidos"] += 1
        item["greens"] += int(
            linha["resultado"] in ("green", "half_green")
        )
        item["reds"] += int(
            linha["resultado"] in ("red", "half_red")
        )
        if linha["retorno_unidades"] is not None:
            retorno = float(linha["retorno_unidades"])
            resumo["dependentes_lucro_unidades"] += retorno
            item["lucro_unidades"] += retorno
    resumo["dependentes_lucro_unidades"] = round(
        resumo["dependentes_lucro_unidades"], 4
    )
    resolvidos = resumo["dependentes_resolvidos"]
    resumo["dependentes_roi"] = (
        round(resumo["dependentes_lucro_unidades"] / resolvidos, 4)
        if resolvidos else None
    )
    for item in resumo["por_mercado"].values():
        item["lucro_unidades"] = round(item["lucro_unidades"], 4)
        item["roi"] = (
            round(item["lucro_unidades"] / item["resolvidos"], 4)
            if item["resolvidos"] else None
        )
    return resumo


def _resumir_dependencia_fallback_temporal_lista(conexao, desde):
    """Mede somente sinais cuja decisão mudou por causa da lista temporal."""
    linhas = conexao.execute(
        """
        SELECT s.id, s.mercado, s.status, s.partida_id, s.features_json,
               r.resultado, r.retorno_unidades,
               EXISTS (
                   SELECT 1 FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.canal NOT LIKE '%:resultado'
               ) entregue
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE datetime(s.criado_em) >= datetime(?)
          AND json_type(
              s.features_json, '$.fallback_temporal_lista'
          )='object'
        ORDER BY s.id
        """,
        (desde,),
    ).fetchall()
    resumo = {
        "candidatos_expostos": 0,
        "partidas_expostas": set(),
        "candidatos_dependentes": 0,
        "partidas_dependentes": set(),
        "dependentes_aprovados": 0,
        "dependentes_simulacoes": 0,
        "dependentes_entregues": 0,
        "dependentes_resolvidos": 0,
        "dependentes_greens": 0,
        "dependentes_reds": 0,
        "dependentes_lucro_unidades": 0.0,
        "por_mercado": {},
    }
    for linha in linhas:
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        fallback = features.get("fallback_temporal_lista") or {}
        if fallback.get("aplicado") is not True:
            continue
        resumo["candidatos_expostos"] += 1
        resumo["partidas_expostas"].add(int(linha["partida_id"]))
        if fallback.get("dependente") is not True:
            continue
        resumo["candidatos_dependentes"] += 1
        resumo["partidas_dependentes"].add(int(linha["partida_id"]))
        resumo["dependentes_aprovados"] += int(
            linha["status"] == "aprovado"
        )
        resumo["dependentes_simulacoes"] += int(
            linha["status"] == "simulacao"
        )
        resumo["dependentes_entregues"] += int(bool(linha["entregue"]))
        mercado = str(linha["mercado"] or "desconhecido")
        item = resumo["por_mercado"].setdefault(mercado, {
            "candidatos_dependentes": 0,
            "partidas_distintas": set(),
            "aprovados": 0,
            "simulacoes": 0,
            "entregues": 0,
            "resolvidos": 0,
            "greens": 0,
            "reds": 0,
            "lucro_unidades": 0.0,
        })
        item["candidatos_dependentes"] += 1
        item["partidas_distintas"].add(int(linha["partida_id"]))
        item["aprovados"] += int(linha["status"] == "aprovado")
        item["simulacoes"] += int(linha["status"] == "simulacao")
        item["entregues"] += int(bool(linha["entregue"]))
        if linha["resultado"] not in (
            "green", "half_green", "red", "half_red"
        ):
            continue
        resumo["dependentes_resolvidos"] += 1
        resumo["dependentes_greens"] += int(
            linha["resultado"] in ("green", "half_green")
        )
        resumo["dependentes_reds"] += int(
            linha["resultado"] in ("red", "half_red")
        )
        item["resolvidos"] += 1
        item["greens"] += int(
            linha["resultado"] in ("green", "half_green")
        )
        item["reds"] += int(
            linha["resultado"] in ("red", "half_red")
        )
        if linha["retorno_unidades"] is not None:
            retorno = float(linha["retorno_unidades"])
            resumo["dependentes_lucro_unidades"] += retorno
            item["lucro_unidades"] += retorno
    resumo["partidas_expostas"] = len(resumo["partidas_expostas"])
    resumo["partidas_dependentes"] = len(resumo["partidas_dependentes"])
    resumo["dependentes_lucro_unidades"] = round(
        resumo["dependentes_lucro_unidades"], 4
    )
    resolvidos = resumo["dependentes_resolvidos"]
    resumo["dependentes_roi"] = (
        round(resumo["dependentes_lucro_unidades"] / resolvidos, 4)
        if resolvidos else None
    )
    resumo["dependentes_taxa_acerto"] = (
        round(resumo["dependentes_greens"] / resolvidos, 4)
        if resolvidos else None
    )
    for item in resumo["por_mercado"].values():
        item["partidas_distintas"] = len(item["partidas_distintas"])
        item["lucro_unidades"] = round(item["lucro_unidades"], 4)
        item["roi"] = (
            round(item["lucro_unidades"] / item["resolvidos"], 4)
            if item["resolvidos"] else None
        )
        item["taxa_acerto"] = (
            round(item["greens"] / item["resolvidos"], 4)
            if item["resolvidos"] else None
        )
    return resumo


def resumir_valor_fontes(conexao, dias=30, agora=None):
    agora = agora or datetime.now()
    dias = max(float(dias), 1.0)
    desde = (agora - timedelta(days=dias)).replace(microsecond=0).isoformat()
    fontes = _resumir_sinais(conexao, desde)
    auxiliares = _resumir_ofertas_auxiliares(conexao, desde)
    entregas_por_mercado = _resumir_entregas_por_fonte_mercado(
        conexao, desde
    )
    contribuicao_preco = _resumir_contribuicao_preco_pareada(
        conexao, desde
    )
    melhor_preco_prospectivo = _resumir_melhor_preco_prospectivo(
        conexao, desde
    )
    validacao_resultado_valor_justo = (
        resumir_validacao_resultado_valor_justo(conexao)
    )
    dependencia_thestats = _resumir_dependencia_dados_thestats(
        conexao, desde
    )
    dependencia_lista_temporal = (
        _resumir_dependencia_fallback_temporal_lista(conexao, desde)
    )
    diagnosticos = {}
    for fonte in ("betsapi", "thestatsapi", "the_odds_api"):
        sinais = fontes.get(fonte) or {}
        oferta = auxiliares.get(fonte) or {}
        atividade = _tem_atividade_coleta(oferta)
        dependencia_dados = (
            dependencia_thestats.get("candidatos_dependentes_fusao", 0)
            if fonte == "thestatsapi" else 0
        )
        if sinais.get("candidatos", 0) > 0 and dependencia_dados > 0:
            estado = "fonte_utilizada_odds_e_estatisticas"
        elif sinais.get("candidatos", 0) > 0:
            estado = "fonte_utilizada_em_candidatos"
        elif dependencia_dados > 0:
            estado = "beneficio_via_estatisticas"
        elif atividade:
            estado = "coleta_sem_candidato_atribuido"
        else:
            estado = "sem_evidencia_de_uso"
        estratos_suficientes = _estratos_expostos_suficientes(
            entregas_por_mercado, fonte
        )
        preco_pareado = (
            contribuicao_preco.get("por_fonte", {}).get(fonte) or {}
        )
        diagnosticos[fonte] = {
            "estado": estado,
            "candidatos_com_odd_da_fonte": sinais.get("candidatos", 0),
            "entregas_com_odd_da_fonte": sinais.get("entregues", 0),
            "entregas_oficiais_com_odd_da_fonte": sinais.get(
                "entregues_oficiais", 0
            ),
            "candidatos_dependentes_dados_fonte": dependencia_dados,
            "resultados_candidatos_sao_contrafactuais": True,
            "estratos_expostos_suficientes": estratos_suficientes,
            "amostra_descritiva_exposta_suficiente": bool(
                estratos_suficientes
            ),
            "comparacao_causal_pareada_disponivel": False,
            "comparacao_preco_exata_disponivel": bool(
                preco_pareado.get("sinais_com_par_exato", 0)
            ),
            "comparacao_preco_independente_disponivel": bool(
                preco_pareado.get("pares_referencia_independente", 0)
            ),
            "comparacoes_preco_independentes": preco_pareado.get(
                "pares_referencia_independente", 0
            ),
            "avaliacao_preco_apta_revisao": bool(
                preco_pareado.get("amostra_independente_suficiente")
            ),
            "avaliacao_custo_beneficio_conclusiva": False,
            "motivo_avaliacao": (
                "amostra_exposta_sem_contrafactual_pareado_da_fonte"
                if estratos_suficientes
                else "amostra_exposta_homogenea_insuficiente"
            ),
        }
    return {
        "versao": "valor-fontes-odds-v9-resultado-valor-justo",
        "gerado_em": agora.replace(microsecond=0).isoformat(),
        "janela_dias": dias,
        "desde": desde,
        "fontes": fontes,
        "entregas_por_fonte_mercado": entregas_por_mercado,
        "contribuicao_preco_pareada": contribuicao_preco,
        "melhor_preco_prospectivo": melhor_preco_prospectivo,
        "validacao_resultado_valor_justo": (
            validacao_resultado_valor_justo
        ),
        "beneficio_dados": {
            "thestatsapi": dependencia_thestats,
            "packball_lista_temporal": dependencia_lista_temporal,
        },
        "coleta_auxiliar": auxiliares,
        "diagnosticos_fontes_pagas": diagnosticos,
        "observacao": (
            "Resultados de candidatos rejeitados são contrafactuais. "
            "Entregas oficiais, testes e estratégias são separadas; "
            "a contribuição de preço exige o mesmo sinal, período, linha, "
            "lado, fonte, bookmaker, odd e fotografia temporal. Atribuição "
            "da odd, sozinha, não prova que a fonte causou o resultado. "
            "A coorte prospectiva mede preço do mesmo contrato sem alterar "
            "sinal, calibração ou Telegram. O resultado posterior compara "
            "edge e controle por mercado, com desenvolvimento/holdout fixos "
            "e somente libera revisão humana após a amostra completa."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Mede o valor operacional real das fontes de odds."
    )
    parser.add_argument("--dias", type=float, default=30)
    parser.add_argument("--banco", default="monitor_packball.db")
    argumentos = parser.parse_args()
    uri = Path(argumentos.banco).resolve().as_uri() + "?mode=ro"
    conexao = sqlite3.connect(uri, uri=True, timeout=10)
    conexao.row_factory = sqlite3.Row
    try:
        resumo = resumir_valor_fontes(conexao, dias=argumentos.dias)
    finally:
        conexao.close()
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
