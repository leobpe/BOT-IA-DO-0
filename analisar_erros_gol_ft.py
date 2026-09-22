"""Auditoria cronologica e reproduzivel dos resultados de Gol FT.

Este arquivo e somente leitura: ele nunca altera o banco nem a regra ativa.
"""

import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path


BANCO = Path(__file__).with_name("monitor_packball.db")
SUFIXOS_IDENTIFICADORES = (".fixture_id", ".time_id", ".liga_id")


def _achatar(valor, prefixo=""):
    saida = {}
    if isinstance(valor, dict):
        for chave, item in valor.items():
            caminho = f"{prefixo}.{chave}" if prefixo else str(chave)
            saida.update(_achatar(item, caminho))
    elif isinstance(valor, (int, float)) and not isinstance(valor, bool):
        saida[prefixo] = float(valor)
    return saida


def carregar(caminho_banco=None):
    caminho_banco = Path(caminho_banco or BANCO).resolve()
    with closing(sqlite3.connect(
        caminho_banco.as_uri() + "?mode=ro", uri=True
    )) as conexao:
        conexao.row_factory = sqlite3.Row
        linhas = conexao.execute(
            """
            WITH independentes AS (
                SELECT s.id, s.criado_em, s.odd, s.pontuacao_tecnica,
                       s.features_json, inicial.contexto_api_json,
                       r.resultado, r.retorno_unidades,
                       inicial.status,
                       COALESCE(p.liga_normalizada, '') AS liga,
                       COALESCE(p.pais, '') AS pais,
                       ROW_NUMBER() OVER (
                           PARTITION BY s.partida_id, s.mercado,
                                        s.regra_versao
                           ORDER BY s.criado_em, s.id
                       ) AS ordem
                FROM sinais s
                JOIN resultados_sinais r ON r.sinal_id=s.id
                JOIN snapshots inicial ON inicial.id=s.snapshot_id
                JOIN partidas p ON p.id=s.partida_id
                WHERE s.mercado='gol_ft'
                  AND s.regra_versao='sinais-v6'
                  AND s.status='aprovado'
                  AND r.resultado IN (
                      'green', 'half_green', 'red', 'half_red'
                  )
                  AND s.odd BETWEEN 1.40 AND 3.50
            )
            SELECT * FROM independentes WHERE ordem=1
            ORDER BY criado_em, id
            """
        ).fetchall()
    itens = []
    for linha in linhas:
        item = dict(linha)
        try:
            features = json.loads(item.pop("features_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            features = {}
        try:
            contexto = json.loads(item.pop("contexto_api_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            contexto = {}
        item["features"] = {
            **_achatar(features),
            **{
                f"contexto.{chave}": valor
                for chave, valor in _achatar(contexto).items()
            },
        }
        itens.append(item)
    return itens


def _metricas(itens):
    validos = [
        item for item in itens
        if item["resultado"] in {"green", "half_green", "red", "half_red"}
    ]
    greens = sum(
        item["resultado"] in {"green", "half_green"} for item in validos
    )
    lucro = sum(float(item["retorno_unidades"] or 0.0) for item in validos)
    return len(validos), greens / len(validos) if validos else 0.0, (
        lucro / len(validos) if validos else 0.0
    )


def _teste_roi_positivo(itens):
    """Triagem normal aproximada da média dos retornos contra ROI zero."""
    retornos = [
        float(item["retorno_unidades"] or 0.0)
        for item in itens
        if item["resultado"] in {
            "green", "half_green", "red", "half_red"
        }
    ]
    n = len(retornos)
    if n < 2:
        return {
            "n": n, "roi": sum(retornos) / n if n else 0.0,
            "erro_padrao": None, "limite_inferior_95": None,
            "p_unilateral": None,
        }
    media = sum(retornos) / n
    variancia = sum((valor - media) ** 2 for valor in retornos) / (n - 1)
    erro_padrao = math.sqrt(variancia / n)
    if erro_padrao == 0:
        p_unilateral = 0.0 if media > 0 else 1.0
        limite = media
    else:
        z = media / erro_padrao
        p_unilateral = 0.5 * math.erfc(z / math.sqrt(2))
        limite = media - 1.96 * erro_padrao
    return {
        "n": n,
        "roi": media,
        "erro_padrao": erro_padrao,
        "limite_inferior_95": limite,
        "p_unilateral": p_unilateral,
    }


def _ajustar_multiplas_comparacoes(avaliacoes, alfa=0.05):
    """Ajusta uma família já materializada sem ocultar testes tentados."""
    avaliacoes = [dict(item) for item in avaliacoes]
    total = len(avaliacoes)
    for item in avaliacoes:
        item["p_bonferroni"] = min(
            1.0, item["p_unilateral"] * total
        )

    ordenadas = sorted(avaliacoes, key=lambda item: item["p_unilateral"])
    menor_q_posterior = 1.0
    for indice in range(total - 1, -1, -1):
        item = ordenadas[indice]
        q = min(1.0, item["p_unilateral"] * total / (indice + 1))
        menor_q_posterior = min(menor_q_posterior, q)
        item["q_bh"] = menor_q_posterior
    return {
        "total_testes": total,
        "alfa": alfa,
        "avaliacoes": sorted(
            avaliacoes,
            key=lambda item: (
                item["p_bonferroni"], -item["roi"], -item["n"]
            ),
        ),
        "aprovados_bonferroni": sum(
            item["p_bonferroni"] <= alfa for item in avaliacoes
        ),
        "aprovados_bh": sum(item["q_bh"] <= alfa for item in avaliacoes),
    }


def _controle_multiplas_comparacoes(itens, candidatos, alfa=0.05):
    """Aplica Bonferroni e Benjamini-Hochberg à família explorada.

    É uma proteção de triagem. A promoção continua exigindo validação
    cronológica intocada e amostra prospectiva, pois os retornos não precisam
    seguir exatamente uma distribuição normal.
    """
    avaliacoes = []
    for candidato in candidatos:
        teste = _teste_roi_positivo(_aplicar(itens, candidato))
        if teste["p_unilateral"] is None:
            continue
        avaliacoes.append({"candidato": candidato, **teste})
    return _ajustar_multiplas_comparacoes(avaliacoes, alfa=alfa)


def auditar_sobreajuste(caminho_banco=None, itens=None):
    itens = list(itens) if itens is not None else carregar(caminho_banco)
    if len(itens) < 60:
        return {
            "estado": "amostra_insuficiente",
            "amostra": len(itens),
            "desenvolvimento": max(len(itens) - 30, 0),
            "validacao_reservada": min(len(itens), 30),
            "testes_explorados": 0,
            "aprovados_bonferroni": 0,
            "aprovados_bh": 0,
            "promocao_retroativa_permitida": False,
            "exige_validacao_prospectiva": True,
        }
    desenvolvimento = itens[:-30]
    candidatos = _candidatos_simples(desenvolvimento)
    controle = _controle_multiplas_comparacoes_compostos(
        desenvolvimento, candidatos_simples=candidatos
    )
    comprovados = controle["aprovados_bonferroni_total"]
    return {
        "estado": (
            "corte_exploratorio_resiste_correcao"
            if comprovados else "nenhum_corte_exploratorio_comprovado"
        ),
        "amostra": len(itens),
        "desenvolvimento": len(desenvolvimento),
        "validacao_reservada": 30,
        "testes_explorados": controle["total_familia"],
        "testes_simples": controle["total_simples"],
        "testes_compostos": controle["total_compostos"],
        "aprovados_bonferroni": comprovados,
        "aprovados_bh": controle["aprovados_bh_total"],
        "alfa": controle["alfa"],
        "promocao_retroativa_permitida": False,
        "exige_validacao_prospectiva": True,
        "metodo": "normal-unilateral+familia-simples-composta+bonferroni+fdr-bh-v2",
    }
def _valor(item, chave):
    if chave == "odd":
        return item.get("odd")
    if chave == "pontuacao_tecnica":
        return item.get("pontuacao_tecnica")
    return item["features"].get(chave)


def _feature_modelavel(chave):
    """Impede que identificadores arbitrários virem falsos preditores."""
    return not (
        chave in {"contexto.fixture_id"}
        or chave.endswith(SUFIXOS_IDENTIFICADORES)
    )


def _candidatos_simples(desenvolvimento):
    chaves = sorted(
        {"odd", "pontuacao_tecnica"}
        | {
            chave for item in desenvolvimento for chave in item["features"]
            if _feature_modelavel(chave)
        }
    )
    candidatos = []
    minimo = max(30, math.ceil(len(desenvolvimento) * 0.25))
    for chave in chaves:
        valores = sorted({
            float(valor) for item in desenvolvimento
            if (valor := _valor(item, chave)) is not None
            and math.isfinite(float(valor))
        })
        if len(valores) < 4:
            continue
        indices = {
            round((len(valores) - 1) * quantil)
            for quantil in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
        }
        for indice in sorted(indices):
            corte = valores[indice]
            for operador in ("<=", ">="):
                selecionados = [
                    item for item in desenvolvimento
                    if _valor(item, chave) is not None
                    and (
                        float(_valor(item, chave)) <= corte
                        if operador == "<="
                        else float(_valor(item, chave)) >= corte
                    )
                ]
                if len(selecionados) < minimo:
                    continue
                n, acerto, roi = _metricas(selecionados)
                candidatos.append({
                    "chave": chave,
                    "operador": operador,
                    "corte": corte,
                    "n_dev": n,
                    "acerto_dev": acerto,
                    "roi_dev": roi,
                })
    return sorted(
        candidatos,
        key=lambda item: (item["roi_dev"], item["n_dev"]),
        reverse=True,
    )


def _aplicar(itens, candidato):
    saida = []
    for item in itens:
        valor = _valor(item, candidato["chave"])
        if valor is None:
            continue
        passou = (
            float(valor) <= candidato["corte"]
            if candidato["operador"] == "<="
            else float(valor) >= candidato["corte"]
        )
        if passou:
            saida.append(item)
    return saida


def _aplicar_varios(itens, candidatos):
    saida = list(itens)
    for candidato in candidatos:
        saida = _aplicar(saida, candidato)
    return saida


def _fatias_cronologicas(itens, quantidade=3):
    tamanho = max(1, len(itens) // quantidade)
    fatias = []
    inicio = 0
    for indice in range(quantidade):
        fim = len(itens) if indice == quantidade - 1 else inicio + tamanho
        fatias.append(itens[inicio:fim])
        inicio = fim
    return fatias


def _estavel_no_desenvolvimento(itens, candidatos):
    positivos = 0
    observados = 0
    rois = []
    for fatia in _fatias_cronologicas(itens):
        selecionados = _aplicar_varios(fatia, candidatos)
        n, _, roi = _metricas(selecionados)
        if n < 8:
            continue
        observados += 1
        positivos += roi > 0
        rois.append(roi)
    return {
        "fatias_observadas": observados,
        "fatias_positivas": positivos,
        "pior_roi": min(rois) if rois else None,
    }


def _descricao_corte(candidato):
    return (
        f"{candidato['chave']} {candidato['operador']} "
        f"{candidato['corte']:.3f}"
    )


def _controle_multiplas_comparacoes_compostos(
    desenvolvimento,
    *,
    candidatos_simples=None,
    alfa=0.05,
):
    # Limita a busca a cortes simples com cobertura relevante. A estabilidade
    # temporal e a validação posterior continuam obrigatórias; a combinação
    # nunca é promovida automaticamente.
    todos_simples = list(
        candidatos_simples
        if candidatos_simples is not None
        else _candidatos_simples(desenvolvimento)
    )
    simples = todos_simples[:80]
    avaliacoes_compostas = []
    vistos = set()
    for indice, primeiro in enumerate(simples):
        for segundo in simples[indice + 1:]:
            if primeiro["chave"] == segundo["chave"]:
                continue
            assinatura = tuple(sorted((
                _descricao_corte(primeiro),
                _descricao_corte(segundo),
            )))
            if assinatura in vistos:
                continue
            vistos.add(assinatura)
            selecionados = _aplicar_varios(
                desenvolvimento, (primeiro, segundo)
            )
            n, acerto, roi = _metricas(selecionados)
            if n < 30:
                continue
            teste = _teste_roi_positivo(selecionados)
            if teste["p_unilateral"] is None:
                continue
            avaliacoes_compostas.append({
                "tipo": "composto",
                "cortes": (primeiro, segundo),
                "n_dev": n,
                "acerto_dev": acerto,
                "roi_dev": roi,
                **teste,
            })

    simples_controle = _controle_multiplas_comparacoes(
        desenvolvimento, todos_simples, alfa=alfa
    )
    familia = [
        {**item, "tipo": "simples"}
        for item in simples_controle["avaliacoes"]
    ] + avaliacoes_compostas
    ajustado = _ajustar_multiplas_comparacoes(familia, alfa=alfa)
    compostos_ajustados = [
        item for item in ajustado["avaliacoes"]
        if item.get("tipo") == "composto"
    ]
    estaveis = []
    for item in compostos_ajustados:
        if item["roi_dev"] <= 0:
            continue
        estabilidade = _estavel_no_desenvolvimento(
            desenvolvimento, item["cortes"]
        )
        if (
            estabilidade["fatias_observadas"] < 3
            or estabilidade["fatias_positivas"] < 2
        ):
            continue
        estaveis.append({**item, **estabilidade})
    estaveis.sort(
        key=lambda item: (
            item["p_bonferroni"],
            item["q_bh"],
            -item["fatias_positivas"],
            -item["roi_dev"],
            -item["n_dev"],
        ),
    )
    return {
        "alfa": alfa,
        "total_simples": len(simples_controle["avaliacoes"]),
        "total_compostos": len(avaliacoes_compostas),
        "total_familia": ajustado["total_testes"],
        "aprovados_bonferroni_total": ajustado[
            "aprovados_bonferroni"
        ],
        "aprovados_bh_total": ajustado["aprovados_bh"],
        "aprovados_bonferroni_compostos": sum(
            item["p_bonferroni"] <= alfa for item in compostos_ajustados
        ),
        "aprovados_bh_compostos": sum(
            item["q_bh"] <= alfa for item in compostos_ajustados
        ),
        "avaliacoes_compostas": compostos_ajustados,
        "estaveis": estaveis,
    }


def _candidatos_compostos(desenvolvimento):
    return _controle_multiplas_comparacoes_compostos(
        desenvolvimento
    )["estaveis"]


def _analisar_competicoes(desenvolvimento, validacao):
    chaves = sorted({
        (item.get("pais") or "sem_pais", item.get("liga") or "sem_liga")
        for item in desenvolvimento + validacao
    })
    linhas = []
    for pais, liga in chaves:
        chave = (pais, liga)
        dev = [
            item for item in desenvolvimento
            if (item.get("pais") or "sem_pais", item.get("liga") or "sem_liga")
            == chave
        ]
        val = [
            item for item in validacao
            if (item.get("pais") or "sem_pais", item.get("liga") or "sem_liga")
            == chave
        ]
        total = len(dev) + len(val)
        if total < 5:
            continue
        n_dev, acerto_dev, roi_dev = _metricas(dev)
        n_val, acerto_val, roi_val = _metricas(val)
        linhas.append({
            "pais": pais,
            "liga": liga,
            "total": total,
            "n_dev": n_dev,
            "acerto_dev": acerto_dev,
            "roi_dev": roi_dev,
            "n_val": n_val,
            "acerto_val": acerto_val,
            "roi_val": roi_val,
        })
    return sorted(linhas, key=lambda item: item["total"], reverse=True)


def _mediana(valores):
    valores = sorted(float(valor) for valor in valores)
    if not valores:
        return None
    meio = len(valores) // 2
    if len(valores) % 2:
        return valores[meio]
    return (valores[meio - 1] + valores[meio]) / 2


def _comparar_periodos(inicial, posterior):
    print("\nMudancas do periodo inicial positivo para o periodo posterior:")
    chaves = (
        "odd",
        "pontuacao_tecnica",
        "minuto",
        "linha",
        "gols_atuais",
        "chutes_no_gol_total",
        "janelas.5.chutes_total",
        "janelas.5.chutes_por_minuto",
        "chutes_lado_dominante_5min",
        "escanteios_atuais",
        "idade_odds_segundos",
        "qualidade_dados",
    )
    for chave in chaves:
        antes = [
            _valor(item, chave) for item in inicial
            if _valor(item, chave) is not None
        ]
        depois = [
            _valor(item, chave) for item in posterior
            if _valor(item, chave) is not None
        ]
        mediana_antes = _mediana(antes)
        mediana_depois = _mediana(depois)
        if mediana_antes is None or mediana_depois is None:
            continue
        print(
            f"{chave}: mediana inicial={mediana_antes:.3f} "
            f"posterior={mediana_depois:.3f} "
            f"delta={mediana_depois - mediana_antes:+.3f}"
        )

    ligas = sorted({item["liga"] for item in inicial + posterior})
    comparaveis = []
    for liga in ligas:
        antes = [item for item in inicial if item["liga"] == liga]
        depois = [item for item in posterior if item["liga"] == liga]
        if len(antes) < 3 or len(depois) < 3:
            continue
        n_a, _, roi_a = _metricas(antes)
        n_d, _, roi_d = _metricas(depois)
        comparaveis.append((n_a + n_d, liga, n_a, roi_a, n_d, roi_d))
    print("\nLigas presentes nos dois periodos (minimo 3 em cada):")
    for _, liga, n_a, roi_a, n_d, roi_d in sorted(
        comparaveis, reverse=True
    )[:15]:
        print(
            f"{liga or 'sem_liga'}: inicial n={n_a} ROI={roi_a:+.1%} | "
            f"posterior n={n_d} ROI={roi_d:+.1%}"
        )


def main():
    itens = carregar()
    print(f"Amostra independente Gol FT sinais-v6: {len(itens)}")
    chaves = sorted({chave for item in itens for chave in item["features"]})
    print(f"Features numericas encontradas: {len(chaves)}")
    for chave in chaves:
        cobertura = sum(chave in item["features"] for item in itens)
        if cobertura >= max(10, len(itens) // 2):
            valores = [
                item["features"][chave]
                for item in itens if chave in item["features"]
            ]
            print(
                f"{chave}: cobertura={cobertura}/{len(itens)} "
                f"min={min(valores):.3f} max={max(valores):.3f}"
            )
    if len(itens) < 60:
        return
    desenvolvimento = itens[:-30]
    validacao = itens[-30:]
    print("\nAuditoria cronologica: desenvolvimento inicial / 30 finais intocados")
    for nome, grupo in (
        ("total", itens),
        ("desenvolvimento", desenvolvimento),
        ("validacao", validacao),
    ):
        n, acerto, roi = _metricas(grupo)
        print(f"{nome}: n={n} acerto={acerto:.1%} ROI={roi:+.1%}")
    print("\nMelhores cortes simples escolhidos SOMENTE no desenvolvimento:")
    candidatos_simples = _candidatos_simples(desenvolvimento)
    for candidato in candidatos_simples[:20]:
        selecionados = _aplicar(validacao, candidato)
        n_val, acerto_val, roi_val = _metricas(selecionados)
        print(
            f"{candidato['chave']} {candidato['operador']} "
            f"{candidato['corte']:.3f} | "
            f"dev n={candidato['n_dev']} "
            f"acerto={candidato['acerto_dev']:.1%} "
            f"ROI={candidato['roi_dev']:+.1%} | "
            f"val n={n_val} acerto={acerto_val:.1%} ROI={roi_val:+.1%}"
        )

    controle = _controle_multiplas_comparacoes(
        desenvolvimento, candidatos_simples
    )
    print("\nControle contra falso padrão por múltiplas comparações:")
    print(
        f"testes explorados={controle['total_testes']} | "
        f"Bonferroni aprovados={controle['aprovados_bonferroni']} | "
        f"FDR-BH aprovados={controle['aprovados_bh']} | alfa=5%"
    )
    print(
        "Método de triagem: teste unilateral aproximado da média dos "
        "retornos; não substitui validação futura intocada."
    )
    for item in controle["avaliacoes"][:10]:
        print(
            f"{_descricao_corte(item['candidato'])} | n={item['n']} "
            f"ROI={item['roi']:+.1%} | "
            f"limite95={item['limite_inferior_95']:+.1%} | "
            f"p-ajustado={item['p_bonferroni']:.4f} | "
            f"q-BH={item['q_bh']:.4f}"
        )

    confirmados_secundarios = []
    for candidato in candidatos_simples:
        selecionados = _aplicar(validacao, candidato)
        n_val, acerto_val, roi_val = _metricas(selecionados)
        estabilidade = _estavel_no_desenvolvimento(
            desenvolvimento, (candidato,)
        )
        if (
            candidato["roi_dev"] > 0
            and n_val >= 5
            and roi_val > 0
            and estabilidade["fatias_observadas"] >= 3
            and estabilidade["fatias_positivas"] >= 2
        ):
            confirmados_secundarios.append((
                candidato, n_val, acerto_val, roi_val, estabilidade
            ))
    print(
        "\nCortes simples positivos no desenvolvimento e também na "
        "conferência cronológica secundária:"
    )
    for candidato, n_val, acerto_val, roi_val, estabilidade in sorted(
        confirmados_secundarios,
        key=lambda item: (item[3], item[1]),
        reverse=True,
    )[:30]:
        print(
            f"{_descricao_corte(candidato)} | "
            f"dev n={candidato['n_dev']} ROI={candidato['roi_dev']:+.1%} | "
            f"fatias positivas={estabilidade['fatias_positivas']}/"
            f"{estabilidade['fatias_observadas']} | "
            f"val n={n_val} acerto={acerto_val:.1%} ROI={roi_val:+.1%}"
        )

    controle_compostos = _controle_multiplas_comparacoes_compostos(
        desenvolvimento, candidatos_simples=candidatos_simples
    )
    print(
        "\nCombinações estáveis em pelo menos 2 de 3 períodos do "
        "desenvolvimento:"
    )
    print(
        "família simples+composta="
        f"{controle_compostos['total_familia']} testes "
        f"({controle_compostos['total_simples']} simples + "
        f"{controle_compostos['total_compostos']} compostos) | "
        "compostos aprovados Bonferroni/FDR-BH="
        f"{controle_compostos['aprovados_bonferroni_compostos']}/"
        f"{controle_compostos['aprovados_bh_compostos']}"
    )
    for candidato in controle_compostos["estaveis"][:20]:
        selecionados = _aplicar_varios(
            validacao, candidato["cortes"]
        )
        n_val, acerto_val, roi_val = _metricas(selecionados)
        descricao = " E ".join(
            _descricao_corte(item) for item in candidato["cortes"]
        )
        print(
            f"{descricao} | dev n={candidato['n_dev']} "
            f"acerto={candidato['acerto_dev']:.1%} "
            f"ROI={candidato['roi_dev']:+.1%} | "
            f"fatias positivas={candidato['fatias_positivas']}/"
            f"{candidato['fatias_observadas']} | "
            f"p-ajustado={candidato['p_bonferroni']:.4f} | "
            f"q-BH={candidato['q_bh']:.4f} | "
            f"val n={n_val} acerto={acerto_val:.1%} ROI={roi_val:+.1%}"
        )

    print("\nPaís + liga com pelo menos 5 resultados no total:")
    for item in _analisar_competicoes(desenvolvimento, validacao):
        print(
            f"{item['pais']} | {item['liga']}: "
            f"dev n={item['n_dev']} acerto={item['acerto_dev']:.1%} "
            f"ROI={item['roi_dev']:+.1%} | "
            f"val n={item['n_val']} acerto={item['acerto_val']:.1%} "
            f"ROI={item['roi_val']:+.1%}"
        )
    _comparar_periodos(itens[:70], itens[70:])


if __name__ == "__main__":
    main()
