import hashlib
import json

from configuracao import obter_limites_risco
from backtest import calcular_metricas
from estatistica import discriminacao_pontuacao
from integridade_calibracao import (
    carregar_coorte_independente,
    resumir_cobertura_amostra_calibracao,
)
from linhagem_regras import fingerprint_vinculado_no_banco
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS


JANELAS_TEMPORAIS = (5, 10, 15)
AMOSTRA_MINIMA_AVALIACAO = 100
VALIDACAO_MINIMA_AVALIACAO = 30
COBERTURA_MINIMA_FEATURE = 0.80
FEATURES_PRE_REGISTRADAS = (
    "pontuacao_tecnica",
    "j5_chutes_por_minuto", "j10_chutes_por_minuto",
    "j15_chutes_por_minuto",
    "j5_escanteios_por_minuto", "j10_escanteios_por_minuto",
    "j15_escanteios_por_minuto",
    "j5_pressao_media_max", "j10_pressao_media_max",
    "j15_pressao_media_max",
    "j5_pressao_pico_max", "j10_pressao_pico_max",
    "j15_pressao_pico_max",
)
FEATURES_CORTES_SOMBRA = (
    "pontuacao_tecnica", "odd", "linha",
    "minuto", "gols_atuais", "chutes_no_gol_total",
    "qualidade_dados", "idade_odds_segundos",
    "j5_chutes_total", "j5_chutes_por_minuto",
    "j5_escanteios_total", "j5_escanteios_por_minuto",
)


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _par(features, nome):
    valor = features.get(nome)
    if not isinstance(valor, list) or len(valor) < 2:
        return [None, None]
    return [_numero(valor[0]), _numero(valor[1])]


def achatar_features(features, mercado_esperado=None):
    """Converte o JSON versionado em colunas; estrutura inválida falha fechada."""
    if not isinstance(features, dict):
        return None
    if features.get("schema_versao") != VERSAO_FEATURES:
        return None
    mercado = features.get("mercado")
    if mercado_esperado is not None and mercado != mercado_esperado:
        return None
    janelas = features.get("janelas")
    if not isinstance(janelas, dict):
        return None
    linha = {
        "minuto": _numero(features.get("minuto")),
        "gols_atuais": _numero(features.get("gols_atuais")),
        "escanteios_atuais": _numero(features.get("escanteios_atuais")),
        "chutes_no_gol_total": _numero(
            features.get("chutes_no_gol_total")
        ),
        "qualidade_dados": _numero(features.get("qualidade_dados")),
        "idade_odds_segundos": _numero(
            features.get("idade_odds_segundos")
        ),
        "chutes_lado_dominante_5min": _numero(
            features.get("chutes_lado_dominante_5min")
        ),
        "escanteios_intervalo": _numero(
            features.get("escanteios_intervalo")
        ),
        "escanteios_2t_atuais": _numero(
            features.get("escanteios_2t_atuais")
        ),
    }
    aceleracao = features.get("aceleracao_5_vs_5") or {}
    for nome in ("chutes", "escanteios"):
        casa, visitante = _par(aceleracao, nome)
        linha[f"aceleracao_{nome}_casa"] = casa
        linha[f"aceleracao_{nome}_visitante"] = visitante
        linha[f"aceleracao_{nome}_total"] = (
            casa + visitante
            if casa is not None and visitante is not None else None
        )
    for minutos in JANELAS_TEMPORAIS:
        janela = janelas.get(str(minutos))
        if not isinstance(janela, dict) or not isinstance(
            janela.get("disponivel"), bool
        ):
            return None
        prefixo = f"j{minutos}"
        linha[f"{prefixo}_disponivel"] = int(janela["disponivel"])
        linha[f"{prefixo}_duracao"] = _numero(
            janela.get("duracao_real_minutos")
        )
        for nome in (
            "chutes_total", "chutes_por_minuto",
            "escanteios_total", "escanteios_por_minuto",
        ):
            linha[f"{prefixo}_{nome}"] = _numero(janela.get(nome))
        for nome in (
            "chutes", "chutes_por_minuto_lados",
            "escanteios", "escanteios_por_minuto_lados",
        ):
            casa, visitante = _par(janela, nome)
            linha[f"{prefixo}_{nome}_casa"] = casa
            linha[f"{prefixo}_{nome}_visitante"] = visitante
            linha[f"{prefixo}_{nome}_max"] = (
                max(casa, visitante)
                if casa is not None and visitante is not None else None
            )
            linha[f"{prefixo}_{nome}_diferenca_abs"] = (
                abs(casa - visitante)
                if casa is not None and visitante is not None else None
            )
        for nome in (
            "pressao_media", "pressao_pico", "pressao_tendencia",
            "dominio_minutos",
        ):
            casa, visitante = _par(janela, nome)
            linha[f"{prefixo}_{nome}_casa"] = casa
            linha[f"{prefixo}_{nome}_visitante"] = visitante
            linha[f"{prefixo}_{nome}_max"] = (
                max(casa, visitante)
                if casa is not None and visitante is not None else None
            )
            linha[f"{prefixo}_{nome}_diferenca_abs"] = (
                abs(casa - visitante)
                if casa is not None and visitante is not None else None
            )
    return linha


def construir_dataset_temporal(
    conexao,
    mercado,
    regra_versao=VERSAO_REGRAS,
    limites_risco=None,
    janela_maxima=300,
):
    """Monta amostra independente sem escolher um candidato pelo resultado."""
    limites_risco = limites_risco or obter_limites_risco()
    regra_fingerprint = fingerprint_vinculado_no_banco(
        conexao, regra_versao
    )
    linhagem_amostra = resumir_cobertura_amostra_calibracao(
        conexao, mercado, regra_versao, limites_risco
    )
    coorte = carregar_coorte_independente(
        conexao,
        mercado,
        regra_versao,
        limites_risco,
        janela_maxima,
        janela="recentes",
    )
    linhas = coorte["validas"]
    registros = []
    invalidos = 0
    exclusoes_por_motivo = {
        "schema_incompativel": 0,
        "json_invalido": 0,
        "estrutura_invalida": 0,
        "odd_linha_inconsistente": 0,
    }
    for linha_sql in linhas:
        try:
            features = json.loads(linha_sql["features_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            features = None
        if not isinstance(features, dict):
            invalidos += 1
            exclusoes_por_motivo["json_invalido"] += 1
            continue
        if features.get("schema_versao") != VERSAO_FEATURES:
            invalidos += 1
            exclusoes_por_motivo["schema_incompativel"] += 1
            continue
        achatadas = achatar_features(features, mercado)
        odd_feature = (
            _numero(features.get("odd"))
            if isinstance(features, dict) else None
        )
        linha_feature = (
            _numero(features.get("linha"))
            if isinstance(features, dict) else None
        )
        odd_sinal = _numero(linha_sql["odd"])
        linha_sinal = _numero(linha_sql["linha"])
        valores_conferem = bool(
            odd_feature is not None
            and odd_sinal is not None
            and abs(odd_feature - odd_sinal) <= 0.0001
            and (
                (linha_feature is None and linha_sinal is None)
                or (
                    linha_feature is not None and linha_sinal is not None
                    and abs(linha_feature - linha_sinal) <= 0.0001
                )
            )
        )
        if achatadas is None:
            invalidos += 1
            exclusoes_por_motivo["estrutura_invalida"] += 1
            continue
        if not valores_conferem:
            invalidos += 1
            exclusoes_por_motivo["odd_linha_inconsistente"] += 1
            continue
        resultado_original = linha_sql["resultado_original"]
        resultado = linha_sql["resultado"]
        registros.append({
            "sinal_id": int(linha_sql["id"]),
            "partida_id": int(linha_sql["partida_id"]),
            "snapshot_id": int(linha_sql["snapshot_id"]),
            "criado_em": linha_sql["criado_em"],
            "encerrado_em": linha_sql["encerrado_em"],
            "mercado": mercado,
            "linha": _numero(linha_sql["linha"]),
            "odd": _numero(linha_sql["odd"]),
            "pontuacao_tecnica": _numero(
                linha_sql["pontuacao_tecnica"]
            ),
            "resultado": resultado,
            "resultado_original": resultado_original,
            "alvo_green": int(resultado == "green"),
            "retorno_unidades": _numero(
                linha_sql["retorno_unidades"]
            ),
            "features": achatadas,
        })
    serializado = json.dumps(
        {
            "mercado": mercado,
            "regra_versao": regra_versao,
            "schema_features": VERSAO_FEATURES,
            "integridade_coorte": coorte["diagnostico"],
            "registros": registros,
        }, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "mercado": mercado,
        "regra_versao": regra_versao,
        "schema_features": VERSAO_FEATURES,
        "regra_fingerprint": regra_fingerprint,
        "elegiveis_independentes": len(coorte["unidades"]),
        "historicos_independentes": linhagem_amostra["historicas"],
        "legado_excluido": linhagem_amostra["legado_excluido"],
        "registros_validos": len(registros),
        "excluidos_features_invalidas": invalidos,
        "excluidos_liquidacao_invalidas": coorte["diagnostico"][
            "pendentes_ou_invalidas"
        ],
        "excluidos_total": (
            invalidos
            + coorte["diagnostico"]["pendentes_ou_invalidas"]
        ),
        "exclusoes_por_motivo": exclusoes_por_motivo,
        "integridade_coorte": coorte["diagnostico"],
        "cobertura": (
            round(len(registros) / len(coorte["unidades"]), 4)
            if coorte["unidades"] else None
        ),
        "fingerprint": hashlib.sha256(serializado).hexdigest(),
        "registros": registros,
    }


def resumir_cobertura_dataset_temporal(
    conexao, mercados, regra_versao=VERSAO_REGRAS,
    regras_por_mercado=None,
):
    """Resume a amostra resolvida apta ao estudo temporal versionado."""
    regras_por_mercado = dict(regras_por_mercado or {})
    por_mercado = {}
    versoes_usadas = {}
    elegiveis = 0
    historicos = 0
    legado_excluido = 0
    validos = 0
    excluidos = 0
    exclusoes_por_motivo = {}
    for mercado in mercados:
        versao_mercado = regras_por_mercado.get(
            mercado, regra_versao
        )
        versoes_usadas[mercado] = versao_mercado
        dataset = construir_dataset_temporal(
            conexao, mercado, regra_versao=versao_mercado
        )
        dados = {
            "regra_versao": versao_mercado,
            "elegiveis": dataset["elegiveis_independentes"],
            "historicos": dataset["historicos_independentes"],
            "legado_excluido": dataset["legado_excluido"],
            "validos": dataset["registros_validos"],
            "excluidos": dataset.get(
                "excluidos_total",
                dataset["excluidos_features_invalidas"],
            ),
            "exclusoes_por_motivo": {
                **dataset["exclusoes_por_motivo"],
                **{
                    f"liquidacao:{motivo}": quantidade
                    for motivo, quantidade in dataset.get(
                        "integridade_coorte", {"motivos": {}}
                    )["motivos"].items()
                },
            },
            "cobertura": dataset["cobertura"],
        }
        por_mercado[mercado] = dados
        elegiveis += dados["elegiveis"]
        historicos += dados["historicos"]
        legado_excluido += dados["legado_excluido"]
        validos += dados["validos"]
        excluidos += dados["excluidos"]
        for motivo, quantidade in dados["exclusoes_por_motivo"].items():
            exclusoes_por_motivo[motivo] = (
                exclusoes_por_motivo.get(motivo, 0) + quantidade
            )
    return {
        "regra_versao": regra_versao,
        "regras_por_mercado": versoes_usadas,
        "schema_features": VERSAO_FEATURES,
        "elegiveis": elegiveis,
        "historicos": historicos,
        "legado_excluido": legado_excluido,
        "validos": validos,
        "excluidos": excluidos,
        "exclusoes_por_motivo": exclusoes_por_motivo,
        "cobertura": round(validos / elegiveis, 4) if elegiveis else None,
        "por_mercado": por_mercado,
    }


def dividir_cronologicamente(registros, proporcao_desenvolvimento=0.7):
    if not 0 < float(proporcao_desenvolvimento) < 1:
        raise ValueError("A proporção deve estar entre zero e um.")
    ordenados = sorted(
        registros,
        key=lambda item: (
            item.get("criado_em") or "", item["sinal_id"]
        ),
    )
    if len(ordenados) < 2:
        return ordenados, []
    corte = max(1, min(
        int(len(ordenados) * float(proporcao_desenvolvimento)),
        len(ordenados) - 1,
    ))
    return ordenados[:corte], ordenados[corte:]


def avaliar_discriminacao_temporal(
    registros,
    amostra_minima=AMOSTRA_MINIMA_AVALIACAO,
    validacao_minima=VALIDACAO_MINIMA_AVALIACAO,
    cobertura_minima=COBERTURA_MINIMA_FEATURE,
):
    """Avalia features pré-registradas fora da amostra, sem alterar o motor."""
    desenvolvimento, validacao = dividir_cronologicamente(registros)
    base = {
        "estado": "inconclusiva",
        "amostra": len(registros),
        "desenvolvimento": len(desenvolvimento),
        "validacao": len(validacao),
        "amostra_minima": int(amostra_minima),
        "validacao_minima": int(validacao_minima),
        "cobertura_minima": float(cobertura_minima),
        "features_pre_registradas": list(FEATURES_PRE_REGISTRADAS),
        "avaliacoes": {},
    }
    if len(registros) < int(amostra_minima):
        base["motivo"] = "amostra_insuficiente"
        return base
    if len(validacao) < int(validacao_minima):
        base["motivo"] = "validacao_insuficiente"
        return base
    for nome in FEATURES_PRE_REGISTRADAS:
        def valor(item):
            if nome == "pontuacao_tecnica":
                return _numero(item.get(nome))
            return _numero((item.get("features") or {}).get(nome))

        dev_validos = [item for item in desenvolvimento if valor(item) is not None]
        val_validos = [item for item in validacao if valor(item) is not None]
        cobertura_dev = (
            len(dev_validos) / len(desenvolvimento)
            if desenvolvimento else 0.0
        )
        cobertura_val = len(val_validos) / len(validacao) if validacao else 0.0
        avaliacao = {
            "cobertura_desenvolvimento": round(cobertura_dev, 4),
            "cobertura_validacao": round(cobertura_val, 4),
            "amostra_desenvolvimento": len(dev_validos),
            "amostra_validacao": len(val_validos),
        }
        if min(cobertura_dev, cobertura_val) < float(cobertura_minima):
            avaliacao["motivo"] = "cobertura_insuficiente"
            base["avaliacoes"][nome] = avaliacao
            continue
        verdes_dev = [valor(item) for item in dev_validos if item["alvo_green"]]
        vermelhos_dev = [
            valor(item) for item in dev_validos if not item["alvo_green"]
        ]
        verdes_val = sum(item["alvo_green"] for item in val_validos)
        vermelhos_val = len(val_validos) - verdes_val
        if not verdes_dev or not vermelhos_dev or min(verdes_val, vermelhos_val) < 5:
            avaliacao["motivo"] = "classes_insuficientes"
            base["avaliacoes"][nome] = avaliacao
            continue
        media_verdes = sum(verdes_dev) / len(verdes_dev)
        media_vermelhos = sum(vermelhos_dev) / len(vermelhos_dev)
        direcao = 1.0 if media_verdes >= media_vermelhos else -1.0
        itens_auc = [{
            "resultado": item["resultado"],
            "pontuacao_tecnica": valor(item) * direcao,
        } for item in val_validos]
        avaliacao.update({
            "direcao_definida_no_desenvolvimento": (
                "maior_melhor" if direcao > 0 else "menor_melhor"
            ),
            "media_green_desenvolvimento": round(media_verdes, 4),
            "media_red_desenvolvimento": round(media_vermelhos, 4),
            "discriminacao_validacao": discriminacao_pontuacao(itens_auc),
            "motivo": None,
        })
        base["avaliacoes"][nome] = avaliacao
    base["estado"] = "avaliavel"
    base["motivo"] = None
    return base


def _valor_corte(item, feature):
    if feature in ("pontuacao_tecnica", "odd", "linha"):
        return _numero(item.get(feature))
    return _numero((item.get("features") or {}).get(feature))


def _limiares_desenvolvimento(valores):
    ordenados = sorted(set(valores))
    if len(ordenados) < 2:
        return []
    indices = {
        round((len(ordenados) - 1) * quantil)
        for quantil in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
    }
    return [ordenados[indice] for indice in sorted(indices)]


def _atende_corte(item, feature, operador, limiar):
    valor = _valor_corte(item, feature)
    if valor is None:
        return False
    if operador == "maior_igual":
        return valor >= limiar
    return valor <= limiar


def avaliar_corte_sombra(
    registros,
    minimo_desenvolvimento=30,
    minimo_validacao=12,
    cobertura_selecionada_maxima=0.80,
):
    """Escolhe um corte simples no passado e mede uma única vez no futuro."""
    desenvolvimento, validacao = dividir_cronologicamente(registros)
    base = {
        "estado": "inconclusiva",
        "desenvolvimento": len(desenvolvimento),
        "validacao": len(validacao),
        "features_candidatas": list(FEATURES_CORTES_SOMBRA),
        "busca_exploratoria_multiplos_cortes": True,
        "candidatos_explorados": 0,
        "features_com_candidatos": 0,
        "correcao_multiplas_comparacoes_confirmatoria": False,
        "uso_confirmatorio": False,
        "minimo_desenvolvimento": int(minimo_desenvolvimento),
        "minimo_validacao": int(minimo_validacao),
    }
    if len(desenvolvimento) < int(minimo_desenvolvimento):
        return {**base, "motivo": "desenvolvimento_insuficiente"}
    if len(validacao) < int(minimo_validacao):
        return {**base, "motivo": "validacao_insuficiente"}

    baseline_dev = calcular_metricas(desenvolvimento)
    baseline_val = calcular_metricas(validacao)
    candidatos = []
    for feature in FEATURES_CORTES_SOMBRA:
        valores = [
            _valor_corte(item, feature) for item in desenvolvimento
        ]
        valores = [valor for valor in valores if valor is not None]
        for limiar in _limiares_desenvolvimento(valores):
            for operador in ("maior_igual", "menor_igual"):
                selecionados = [
                    item for item in desenvolvimento
                    if _atende_corte(item, feature, operador, limiar)
                ]
                cobertura = (
                    len(selecionados) / len(desenvolvimento)
                    if desenvolvimento else 0.0
                )
                if len(selecionados) < int(minimo_desenvolvimento):
                    continue
                if cobertura > float(cobertura_selecionada_maxima):
                    continue
                metricas = calcular_metricas(selecionados)
                candidatos.append({
                    "feature": feature,
                    "operador": operador,
                    "limiar": limiar,
                    "cobertura_desenvolvimento": round(cobertura, 4),
                    "metricas_desenvolvimento": metricas,
                })
    base["candidatos_explorados"] = len(candidatos)
    base["features_com_candidatos"] = len({
        item["feature"] for item in candidatos
    })
    if not candidatos:
        return {
            **base,
            "motivo": "nenhum_corte_com_amostra_minima",
            "baseline_desenvolvimento": baseline_dev,
            "baseline_validacao": baseline_val,
        }

    escolhido = max(
        candidatos,
        key=lambda item: (
            item["metricas_desenvolvimento"]["lucro_unidades"],
            item["metricas_desenvolvimento"]["roi"],
            item["metricas_desenvolvimento"]["amostra"],
        ),
    )
    selecionados_val = [
        item for item in validacao
        if _atende_corte(
            item,
            escolhido["feature"],
            escolhido["operador"],
            escolhido["limiar"],
        )
    ]
    metricas_val = calcular_metricas(selecionados_val)
    resultado = {
        **base,
        "estado": "avaliavel",
        "motivo": None,
        # Esta divisão é recalculada quando a população cresce. Portanto ela
        # serve para gerar uma hipótese, não para autorizar alteração da regra
        # sem um registro prospectivo imutável separado.
        "natureza": "exploratoria_com_divisao_movel",
        "requer_validacao_prospectiva": True,
        "observacao_inferencia": (
            "O melhor corte foi escolhido entre múltiplos candidatos. "
            "A validação móvel serve apenas para gerar hipótese; confirmação "
            "exige coorte prospectiva imutável separada."
        ),
        "corte_escolhido_no_desenvolvimento": dict(escolhido),
        "baseline_desenvolvimento": baseline_dev,
        "baseline_validacao": baseline_val,
        "metricas_validacao_corte": metricas_val,
        "cobertura_validacao": round(
            len(selecionados_val) / len(validacao), 4
        ) if validacao else 0.0,
    }
    if len(selecionados_val) < int(minimo_validacao):
        resultado.update({
            "estado": "inconclusiva",
            "motivo": "subgrupo_validacao_insuficiente",
            "apto_para_alterar_regra": False,
        })
        return resultado
    resultado["apto_para_alterar_regra"] = bool(
        metricas_val["roi"] is not None
        and baseline_val["roi"] is not None
        and metricas_val["roi"] > 0
        and metricas_val["roi"] > baseline_val["roi"]
        and metricas_val["lucro_unidades"] > 0
    )
    return resultado


def resumir_cortes_sombra(
    conexao,
    mercados,
    regra_versao=VERSAO_REGRAS,
    limites_risco=None,
):
    """Monitora cortes temporais sem promovê-los automaticamente."""
    avaliacoes = {}
    aptos = []
    for mercado in mercados:
        dataset = construir_dataset_temporal(
            conexao,
            mercado,
            regra_versao=regra_versao,
            limites_risco=limites_risco,
        )
        avaliacao = avaliar_corte_sombra(dataset["registros"])
        avaliacoes[mercado] = avaliacao
        if avaliacao.get("apto_para_alterar_regra") is True:
            aptos.append(mercado)
    return {
        "versao": "cortes-sombra-v1",
        "regra_versao": regra_versao,
        "aplicacao_automatica": False,
        "mercados_aptos_para_revisao": aptos,
        "avaliacoes": avaliacoes,
    }
