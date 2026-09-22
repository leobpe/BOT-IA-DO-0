import json
import math

from api_football import associar_jogo
from backtest import _encerrado, liquidar_over_asiatico
from evolucao import extrair_par
from proveniencia_odds import _interpretar_instante, _utc_ingenuo


RESULTADOS_LIQUIDAVEIS = frozenset({
    "green", "half_green", "red", "half_red", "void",
})


def _objeto_json(valor):
    try:
        objeto = json.loads(valor or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return objeto if isinstance(objeto, dict) else {}


def _instante_utc_ingenuo(valor):
    instante = _interpretar_instante(valor)
    return _utc_ingenuo(instante) if instante is not None else None


def auditar_liquidacao_escanteios_ft(
    conexao, regra_versao=None, tolerancia_relogio_segundos=1.0,
):
    """Recompõe cada liquidação FT asiática com a evidência persistida.

    O resultado gravado só é aceito quando o snapshot é posterior, terminal,
    contém o total final de escanteios e reproduz exatamente resultado e
    retorno. Sinais anteriores ao rastro temporal completo continuam
    identificados como legado, mas não são convertidos retroativamente em
    falha: a liquidação deles ainda é comprovada pelo snapshot imutável.
    """
    filtros = [
        "s.mercado='escanteios_ft_asiatico'",
        "r.resultado IN ('green','half_green','red','half_red','void')",
        "NOT (r.resultado='void' AND r.fonte_resultado LIKE "
        "'invalidacao_operacional_%')",
    ]
    parametros = []
    if regra_versao is not None:
        filtros.append("s.regra_versao=?")
        parametros.append(str(regra_versao))
    linhas = conexao.execute(
        f"""
        SELECT s.id AS sinal_id, s.snapshot_id, s.criado_em,
               s.linha, s.odd, s.features_json,
               entrada.coletado_em AS entrada_em,
               r.resultado, r.retorno_unidades,
               r.snapshot_id_liquidacao,
               final.coletado_em AS final_em,
               final.status AS final_status,
               final.estatisticas_json AS estatisticas_finais,
               final.qualidade_json AS qualidade_final
        FROM resultados_sinais r
        JOIN sinais s ON s.id=r.sinal_id
        JOIN snapshots entrada ON entrada.id=s.snapshot_id
        LEFT JOIN snapshots final ON final.id=r.snapshot_id_liquidacao
        WHERE {' AND '.join(filtros)}
        ORDER BY s.id
        """,
        parametros,
    ).fetchall()
    resumo = {
        "total": len(linhas),
        "liquidacoes_recompostas": 0,
        "rastro_temporal_auditavel": 0,
        "legado_sem_rastro_temporal": 0,
        "snapshot_nao_posterior": 0,
        "ordem_temporal_invalida": 0,
        "periodo_nao_encerrado": 0,
        "snapshot_final_nao_apto": 0,
        "parametros_ausentes": 0,
        "total_final_ausente": 0,
        "resultado_divergente": 0,
        "retorno_divergente": 0,
        "rastro_temporal_invalido": 0,
        "inconsistentes": 0,
        "detalhes": [],
    }
    tolerancia = max(float(tolerancia_relogio_segundos), 0.0)
    for linha in linhas:
        motivos = []
        snapshot_final_id = linha["snapshot_id_liquidacao"]
        if (
            snapshot_final_id is None
            or int(snapshot_final_id) <= int(linha["snapshot_id"])
        ):
            motivos.append("snapshot_nao_posterior")
        entrada_em = _instante_utc_ingenuo(linha["entrada_em"])
        final_em = _instante_utc_ingenuo(linha["final_em"])
        if (
            entrada_em is None
            or final_em is None
            or final_em < entrada_em
        ):
            motivos.append("ordem_temporal_invalida")
        status_final = str(linha["final_status"] or "").strip().casefold()
        if not (
            _encerrado(linha["final_status"])
            or status_final in {"pen", "aet"}
        ):
            motivos.append("periodo_nao_encerrado")

        qualidade = _objeto_json(linha["qualidade_final"])
        if qualidade.get("apto_para_liquidacao") is False:
            motivos.append("snapshot_final_nao_apto")

        try:
            linha_asiatica = float(linha["linha"])
            odd = float(linha["odd"])
            parametros_validos = all(
                math.isfinite(valor) for valor in (linha_asiatica, odd)
            ) and odd > 1.0
        except (TypeError, ValueError):
            parametros_validos = False
        if not parametros_validos:
            motivos.append("parametros_ausentes")

        estatisticas = _objeto_json(linha["estatisticas_finais"])
        par_final = extrair_par(estatisticas.get("Escanteios"))
        total_final = int(sum(par_final)) if par_final is not None else None
        if total_final is None:
            motivos.append("total_final_ausente")
        elif parametros_validos:
            resultado, retorno = liquidar_over_asiatico(
                total_final, linha_asiatica, odd
            )
            if resultado != linha["resultado"]:
                motivos.append("resultado_divergente")
            retorno_gravado = linha["retorno_unidades"]
            if (
                retorno_gravado is None
                or not math.isclose(
                    float(retorno_gravado), float(retorno),
                    rel_tol=0.0, abs_tol=0.000001,
                )
            ):
                motivos.append("retorno_divergente")
            if (
                resultado == linha["resultado"]
                and retorno_gravado is not None
                and math.isclose(
                    float(retorno_gravado), float(retorno),
                    rel_tol=0.0, abs_tol=0.000001,
                )
            ):
                resumo["liquidacoes_recompostas"] += 1

        features = _objeto_json(linha["features_json"])
        estado_em = _instante_utc_ingenuo(
            features.get("estado_observado_em")
        )
        decisao_em = _instante_utc_ingenuo(features.get("decisao_em"))
        odd_em = _instante_utc_ingenuo(features.get("coletado_em_odds"))
        if estado_em is None or decisao_em is None or odd_em is None:
            resumo["legado_sem_rastro_temporal"] += 1
        else:
            resumo["rastro_temporal_auditavel"] += 1
            if (
                estado_em.timestamp() - decisao_em.timestamp() > tolerancia
                or odd_em.timestamp() - decisao_em.timestamp() > tolerancia
                or (
                    final_em is not None
                    and decisao_em.timestamp() - final_em.timestamp()
                    > tolerancia
                )
            ):
                motivos.append("rastro_temporal_invalido")

        motivos = list(dict.fromkeys(motivos))
        for motivo in motivos:
            resumo[motivo] += 1
        if motivos:
            resumo["inconsistentes"] += 1
            if len(resumo["detalhes"]) < 20:
                resumo["detalhes"].append({
                    "sinal_id": int(linha["sinal_id"]),
                    "motivos": motivos,
                    "total_final": total_final,
                    "linha": linha["linha"],
                    "odd": linha["odd"],
                    "resultado": linha["resultado"],
                    "retorno_unidades": linha["retorno_unidades"],
                })
    resumo["saudavel"] = resumo["inconsistentes"] == 0
    return resumo


def auditar_proveniencia_resultados(conexao):
    """Verifica se cada liquidação aponta para evidência coerente."""
    linha = conexao.execute(
        """
        WITH avaliacao AS (
            SELECT r.sinal_id, r.resultado, r.encerrado_em,
                   r.snapshot_id_liquidacao, r.fonte_resultado,
                   r.observacao,
                   s.partida_id AS partida_sinal,
                   sn.partida_id AS partida_snapshot,
                   sn.coletado_em AS coletado_snapshot,
                   sn.fontes_json,
                   CASE
                     WHEN r.resultado='sem_dado' THEN
                       r.snapshot_id_liquidacao IS NULL
                       AND r.fonte_resultado='sem_dado'
                     WHEN r.resultado='void'
                      AND r.fonte_resultado LIKE
                          'invalidacao_operacional_%' THEN
                       r.snapshot_id_liquidacao IS NULL
                       AND COALESCE(TRIM(r.observacao), '')<>''
                     ELSE
                       r.snapshot_id_liquidacao IS NOT NULL
                       AND sn.id IS NOT NULL
                       AND sn.partida_id=s.partida_id
                       AND sn.coletado_em=r.encerrado_em
                       AND r.fonte_resultado IN (
                           'packball', 'api_football'
                       )
                       AND sn.fontes_json LIKE
                           '%' || r.fonte_resultado || '%'
                   END AS coerente
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            LEFT JOIN snapshots sn ON sn.id=r.snapshot_id_liquidacao
        )
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN coerente THEN 1 ELSE 0 END) AS coerentes,
               SUM(CASE
                     WHEN resultado<>'sem_dado'
                      AND NOT (
                        resultado='void'
                        AND fonte_resultado LIKE
                            'invalidacao_operacional_%'
                        AND COALESCE(TRIM(observacao), '')<>''
                      )
                      AND snapshot_id_liquidacao IS NULL THEN 1 ELSE 0
                   END) AS sem_snapshot,
               SUM(CASE
                     WHEN fonte_resultado IS NULL OR fonte_resultado=''
                     THEN 1 ELSE 0
                   END) AS sem_fonte,
               SUM(CASE
                     WHEN snapshot_id_liquidacao IS NOT NULL
                      AND partida_snapshot<>partida_sinal THEN 1 ELSE 0
                   END) AS partida_incorreta,
               SUM(CASE
                     WHEN snapshot_id_liquidacao IS NOT NULL
                      AND coletado_snapshot<>encerrado_em THEN 1 ELSE 0
                   END) AS horario_incorreto,
               SUM(CASE WHEN NOT COALESCE(coerente, 0) THEN 1 ELSE 0 END)
                   AS inconsistentes
        FROM avaliacao
        """
    ).fetchone()
    chaves = (
        "total", "coerentes", "sem_snapshot", "sem_fonte",
        "partida_incorreta", "horario_incorreto", "inconsistentes",
    )
    resultado = {
        chave: int(linha[chave] or 0)
        for chave in chaves
    }
    api_times_ausentes = 0
    api_times_incompativeis = 0
    api_times_validados = 0
    evidencias_api = conexao.execute(
        """
        SELECT p.mandante, p.visitante, sn.confirmacao_api_json
        FROM resultados_sinais r
        JOIN sinais s ON s.id=r.sinal_id
        JOIN partidas p ON p.id=s.partida_id
        JOIN snapshots sn ON sn.id=r.snapshot_id_liquidacao
        WHERE r.resultado<>'sem_dado'
          AND r.fonte_resultado='api_football'
          AND sn.partida_id=s.partida_id
          AND sn.coletado_em=r.encerrado_em
          AND sn.fontes_json LIKE '%api_football%'
        """
    ).fetchall()
    for evidencia in evidencias_api:
        try:
            confirmacao = json.loads(
                evidencia["confirmacao_api_json"] or "null"
            )
        except (TypeError, json.JSONDecodeError):
            confirmacao = None
        times = (confirmacao or {}).get("times") or {}
        casa = (times.get("home") or {}).get("name")
        fora = (times.get("away") or {}).get("name")
        if not casa or not fora:
            api_times_ausentes += 1
            continue
        associado = associar_jogo(
            {
                "mandante": evidencia["mandante"],
                "visitante": evidencia["visitante"],
            },
            [{
                "fixture": {"id": 0, "status": {}},
                "teams": {
                    "home": {"name": casa},
                    "away": {"name": fora},
                },
                "goals": {},
            }],
        )
        if associado is None or associado["orientacao"] != "direta":
            api_times_incompativeis += 1
        else:
            api_times_validados += 1

    novos_inconsistentes = api_times_ausentes + api_times_incompativeis
    resultado["api_times_validados"] = api_times_validados
    resultado["api_times_ausentes"] = api_times_ausentes
    resultado["api_times_incompativeis"] = api_times_incompativeis
    resultado["coerentes"] = max(
        resultado["coerentes"] - novos_inconsistentes, 0
    )
    resultado["inconsistentes"] += novos_inconsistentes
    liquidacao_escanteios_ft = auditar_liquidacao_escanteios_ft(conexao)
    resultado["liquidacao_escanteios_ft"] = liquidacao_escanteios_ft
    resultado["inconsistentes"] += liquidacao_escanteios_ft[
        "inconsistentes"
    ]
    resultado["saudavel"] = resultado["inconsistentes"] == 0
    return resultado
