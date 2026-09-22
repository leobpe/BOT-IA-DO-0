import copy
import math
import json
from datetime import datetime


VERSAO_FALLBACK_INDICADORES_LISTA = "packball-lista-fallback-v1"
IDADE_MAXIMA_PADRAO_SEGUNDOS = 240.0


# Estas tres colunas possuem a mesma semantica cumulativa dos campos exibidos
# dentro da partida. Indicadores de 5/10 minutos nao entram neste mapa: eles
# sao janelas moveis e nao podem ser tratados como totais da partida.
MAPA_CUMULATIVO_COMPROVADO = {
    "total_chutes_partida_completa": "Chutes",
    "escanteios_partida_completa": "Escanteios",
    "ataques_perigosos_partida_completa": "Ataques perigosos",
}

MAPA_JANELAS_TEMPORAIS = {
    5: {
        "chutes": "total_chutes_ult_5_minutos",
        "chutes_gol": "chutes_no_gol_ult_5_minutos",
        "escanteios": "escanteios_ult_5_minutos",
        "pressao": "indice_de_pressao_ult_5_minutos",
        "expectativa_gols": "expectativa_de_gols_para_os_proximos_5_minutos",
        "expectativa_escanteios": (
            "expectativa_de_escanteios_para_os_proximos_5_minutos"
        ),
    },
    10: {
        "chutes": "total_chutes_ult_10_minutos",
        "chutes_gol": "chutes_no_gol_ult_10_minutos",
        "escanteios": "escanteios_ult_10_minutos",
        "pressao": "indice_de_pressao_ult_10_minutos",
        "expectativa_gols": (
            "expectativa_de_gols_para_os_proximos_10_minutos"
        ),
        "expectativa_escanteios": (
            "expectativa_de_escanteios_para_os_proximos_10_minutos"
        ),
    },
}


def _instante_compativel(valor, referencia):
    try:
        instante = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None
    referencia = referencia or datetime.now()
    if instante.tzinfo is not None and referencia.tzinfo is None:
        instante = instante.astimezone().replace(tzinfo=None)
    elif instante.tzinfo is None and referencia.tzinfo is not None:
        referencia = referencia.replace(tzinfo=None)
    elif instante.tzinfo is not None and referencia.tzinfo is not None:
        instante = instante.astimezone(referencia.tzinfo)
    return instante, referencia


def _par_valido(campo):
    if isinstance(campo, dict):
        brutos = [campo.get("casa"), campo.get("visitante")]
    elif isinstance(campo, (list, tuple)) and len(campo) >= 2:
        brutos = list(campo[:2])
    else:
        return None
    valores = []
    for bruto in brutos:
        try:
            valor = float(bruto)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(valor) or valor < 0:
            return None
        valores.append(valor)
    return valores


def _formatar_numero(valor):
    return str(int(valor)) if float(valor).is_integer() else f"{valor:g}"


def complementar_estatisticas_com_lista(
    jogo,
    estatisticas,
    instante=None,
    idade_maxima_segundos=IDADE_MAXIMA_PADRAO_SEGUNDOS,
):
    """Completa somente contadores cumulativos equivalentes e recentes.

    O dado precisa pertencer ao mesmo objeto de partida/URL, ter os dois lados
    numéricos, ser não negativo e ter sido observado há poucos minutos. Campos
    já coletados no detalhe nunca são substituídos.
    """
    resultado = dict(estatisticas or {})
    diagnostico = {
        "versao": VERSAO_FALLBACK_INDICADORES_LISTA,
        "aplicado": False,
        "motivo": None,
        "campos_complementados": [],
        "campos_rejeitados": [],
        "idade_segundos": None,
        "autoriza_sinal": False,
    }
    indicadores = (jogo or {}).get("indicadores_lista") or {}
    campos = indicadores.get("campos")
    if not isinstance(campos, dict) or not campos:
        diagnostico["motivo"] = "indicadores_lista_ausentes"
        return resultado, diagnostico

    observado_em = (jogo or {}).get("lista_observada_em")
    instantes = _instante_compativel(observado_em, instante or datetime.now())
    if instantes is None:
        diagnostico["motivo"] = "instante_lista_invalido"
        return resultado, diagnostico
    observado, referencia = instantes
    idade = (referencia - observado).total_seconds()
    diagnostico["idade_segundos"] = round(idade, 3)
    try:
        limite = max(float(idade_maxima_segundos), 0.0)
    except (TypeError, ValueError):
        limite = IDADE_MAXIMA_PADRAO_SEGUNDOS
    if idade < -5 or idade > limite:
        diagnostico["motivo"] = "indicadores_lista_desatualizados"
        return resultado, diagnostico

    for chave_lista, chave_detalhe in MAPA_CUMULATIVO_COMPROVADO.items():
        if resultado.get(chave_detalhe) not in (None, "", "-"):
            continue
        campo_lista = campos.get(chave_lista)
        if campo_lista is None:
            continue
        par = _par_valido(campo_lista)
        if par is None:
            diagnostico["campos_rejeitados"].append(chave_lista)
            continue
        resultado[chave_detalhe] = " - ".join(
            _formatar_numero(valor) for valor in par
        )
        diagnostico["campos_complementados"].append(chave_detalhe)

    diagnostico["aplicado"] = bool(diagnostico["campos_complementados"])
    diagnostico["autoriza_sinal"] = diagnostico["aplicado"]
    diagnostico["motivo"] = (
        "complementado_mesma_partida_ciclo"
        if diagnostico["aplicado"]
        else "nenhum_campo_elegivel"
    )
    if diagnostico["aplicado"]:
        resultado["_fallback_indicadores_lista"] = {
            "versao": VERSAO_FALLBACK_INDICADORES_LISTA,
            "observado_em": observado_em,
            "idade_segundos": diagnostico["idade_segundos"],
            "campos": list(diagnostico["campos_complementados"]),
            "fonte": "packball_lista_ao_vivo",
        }
    return resultado, diagnostico


def auditar_janelas_temporais_lista(
    jogo,
    evolucao,
    instante=None,
    idade_maxima_segundos=IDADE_MAXIMA_PADRAO_SEGUNDOS,
):
    """Compara janelas explícitas da lista sem aplicá-las aos sinais."""
    diagnostico = {
        "versao": "packball-lista-janelas-sombra-v1",
        "estado": "sem_dados",
        "idade_segundos": None,
        "janelas": {},
        "comparacoes": [],
        "leituras_disponiveis": 0,
        "aplicacao_sinais": False,
        "promocao_automatica": False,
        "rollback": "INDICADORES_LISTA_TEMPORAIS_SOMBRA_ATIVOS=0",
    }
    indicadores = (jogo or {}).get("indicadores_lista") or {}
    campos = indicadores.get("campos")
    if not isinstance(campos, dict) or not campos:
        diagnostico["estado"] = "indicadores_lista_ausentes"
        return diagnostico
    observado_em = (jogo or {}).get("lista_observada_em")
    instantes = _instante_compativel(observado_em, instante or datetime.now())
    if instantes is None:
        diagnostico["estado"] = "instante_lista_invalido"
        return diagnostico
    observado, referencia = instantes
    idade = (referencia - observado).total_seconds()
    diagnostico["idade_segundos"] = round(idade, 3)
    try:
        limite = max(float(idade_maxima_segundos), 0.0)
    except (TypeError, ValueError):
        limite = IDADE_MAXIMA_PADRAO_SEGUNDOS
    if idade < -5 or idade > limite:
        diagnostico["estado"] = "indicadores_lista_desatualizados"
        return diagnostico

    for minutos, mapa in MAPA_JANELAS_TEMPORAIS.items():
        janela = {}
        for metrica, chave in mapa.items():
            par = _par_valido(campos.get(chave))
            if par is not None:
                janela[metrica] = par
                diagnostico["leituras_disponiveis"] += 1
        if not janela:
            continue
        diagnostico["janelas"][str(minutos)] = janela
        referencia_historica = (evolucao or {}).get(str(minutos)) or {}
        for metrica in ("chutes", "escanteios"):
            direto = janela.get(metrica)
            historico = referencia_historica.get(metrica)
            if (
                direto is None
                or not isinstance(historico, (list, tuple))
                or len(historico) < 2
            ):
                continue
            try:
                historico = [float(historico[0]), float(historico[1])]
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(valor) and valor >= 0 for valor in historico):
                continue
            erro_total = abs(sum(direto) - sum(historico))
            tolerancia = 2.0 if metrica == "chutes" else 1.0
            diagnostico["comparacoes"].append({
                "janela_minutos": minutos,
                "metrica": metrica,
                "lista": direto,
                "historico": historico,
                "erro_total_absoluto": round(erro_total, 3),
                "atividade_concordante": (
                    (sum(direto) > 0) == (sum(historico) > 0)
                ),
                "concordante_tolerancia": erro_total <= tolerancia,
                "tolerancia": tolerancia,
            })
    diagnostico["estado"] = (
        "comparavel"
        if diagnostico["comparacoes"]
        else "coletando_sem_referencia_historica"
        if diagnostico["leituras_disponiveis"]
        else "sem_leituras_validas"
    )
    return diagnostico


def fundir_janelas_temporais_lista_como_fallback(
    jogo,
    evolucao,
    revisao,
    *,
    autorizado=False,
    instante=None,
    idade_maxima_segundos=90.0,
):
    """Preenche apenas lacunas temporais após o gate independente.

    Chutes e escanteios são os únicos campos comparados prospectivamente.
    Pressão, chutes no gol e expectativas permanecem observacionais. Uma
    janela histórica válida nunca é substituída.
    """
    diagnostico = {
        "versao": "packball-lista-janelas-fallback-v1",
        "autorizado_configuracao": bool(autorizado),
        "gate_pronto": bool((revisao or {}).get("pronto_para_revisao")),
        "aplicacao_sinais": False,
        "aplicado": False,
        "campos_complementados": [],
        "motivo": None,
        "rollback": "INDICADORES_LISTA_TEMPORAIS_APLICACAO_SINAIS=0",
    }
    if not autorizado:
        diagnostico["motivo"] = "desativado_configuracao"
        return copy.deepcopy(evolucao or {}), diagnostico
    if not diagnostico["gate_pronto"]:
        diagnostico["motivo"] = "gate_independente_pendente"
        return copy.deepcopy(evolucao or {}), diagnostico
    metricas_aprovadas = set(
        (revisao or {}).get("metricas_aprovadas") or []
    )
    if not metricas_aprovadas:
        diagnostico["motivo"] = "nenhuma_metrica_aprovada"
        return copy.deepcopy(evolucao or {}), diagnostico

    auditoria = auditar_janelas_temporais_lista(
        jogo,
        evolucao,
        instante=instante,
        idade_maxima_segundos=idade_maxima_segundos,
    )
    if auditoria.get("estado") in {
        "indicadores_lista_ausentes",
        "instante_lista_invalido",
        "indicadores_lista_desatualizados",
        "sem_leituras_validas",
    }:
        diagnostico["motivo"] = auditoria.get("estado")
        return copy.deepcopy(evolucao or {}), diagnostico

    fundida = copy.deepcopy(evolucao or {})
    for minutos_texto, direta in (auditoria.get("janelas") or {}).items():
        try:
            minutos = int(minutos_texto)
        except (TypeError, ValueError):
            continue
        janela_existente = fundida.get(str(minutos))
        janela = (
            copy.deepcopy(janela_existente)
            if isinstance(janela_existente, dict) else {}
        )
        adicionou = False
        for metrica in ("chutes", "escanteios"):
            if metrica not in metricas_aprovadas:
                continue
            existente = janela.get(metrica)
            if isinstance(existente, (list, tuple)) and len(existente) >= 2:
                try:
                    existente_valido = all(
                        math.isfinite(float(valor)) and float(valor) >= 0
                        for valor in existente[:2]
                    )
                except (TypeError, ValueError):
                    existente_valido = False
                if existente_valido:
                    continue
            par = _par_valido(direta.get(metrica))
            if par is None:
                continue
            janela[metrica] = list(par)
            diagnostico["campos_complementados"].append(
                f"{minutos}.{metrica}"
            )
            adicionou = True
        if not adicionou:
            continue
        janela.setdefault("pressao", None)
        janela.setdefault("pressao_resumo", None)
        janela.setdefault("resets_detectados", [])
        janela.setdefault("duracao_real_minutos", float(minutos))
        janela.setdefault("desvio_alvo_minutos", 0.0)
        janela["fonte_fallback"] = "packball_lista_ao_vivo"
        janela["versao_fallback"] = diagnostico["versao"]
        fundida[str(minutos)] = janela

    diagnostico["aplicacao_sinais"] = True
    diagnostico["aplicado"] = bool(
        diagnostico["campos_complementados"]
    )
    diagnostico["motivo"] = (
        "lacunas_complementadas"
        if diagnostico["aplicado"] else "historico_ja_completo"
    )
    return fundida, diagnostico


def marcar_dependencia_fallback_temporal_lista(
    candidatos, candidatos_base, diagnostico
):
    """Carimba quais decisões só existiram após preencher a lacuna temporal."""
    fallback = (diagnostico or {}).get("fallback_condicional") or {}
    if not fallback.get("aplicado"):
        return candidatos
    gate = (diagnostico or {}).get("gate_revisao") or {}
    estados_base = {
        (
            item.get("mercado"),
            str(item.get("linha")),
            item.get("regra_versao"),
        ): item.get("status")
        for item in candidatos_base or []
    }
    elegiveis = {"aprovado", "simulacao"}
    for candidato in candidatos or []:
        identidade = (
            candidato.get("mercado"),
            str(candidato.get("linha")),
            candidato.get("regra_versao"),
        )
        status = candidato.get("status")
        status_base = estados_base.get(identidade)
        dependente = bool(
            status in elegiveis and status_base not in elegiveis
        )
        evidencia = {
            "versao": fallback.get(
                "versao", "packball-lista-janelas-fallback-v1"
            ),
            "aplicado": True,
            "dependente": dependente,
            "status_com_fallback": status,
            "status_sem_fallback": status_base,
            "campos_complementados": list(
                fallback.get("campos_complementados") or []
            ),
            "metricas_aprovadas": list(
                gate.get("metricas_aprovadas") or []
            ),
            "comparacoes_gate": gate.get("comparacoes"),
            "partidas_gate": gate.get("partidas"),
            "fonte": "packball_lista_ao_vivo",
            "aplicacao_sinais": True,
            "rollback": "INDICADORES_LISTA_TEMPORAIS_APLICACAO_SINAIS=0",
        }
        candidato.setdefault("features", {})[
            "fallback_temporal_lista"
        ] = evidencia
        if dependente:
            motivos = candidato.setdefault("motivos", [])
            if "dependente_fallback_temporal_lista" not in motivos:
                motivos.append("dependente_fallback_temporal_lista")
    return candidatos


def _wilson_inferior(acertos, total, z=1.959963984540054):
    if total <= 0:
        return None
    proporcao = acertos / total
    denominador = 1 + (z * z / total)
    centro = proporcao + (z * z / (2 * total))
    margem = z * math.sqrt(
        (proporcao * (1 - proporcao) / total)
        + (z * z / (4 * total * total))
    )
    return max((centro - margem) / denominador, 0.0)


def resumir_auditoria_temporal_sqlite(
    conexao,
    minimo_comparacoes=30,
    minimo_partidas=10,
    limite_inferior_minimo=0.70,
    idade_comparacao_maxima_segundos=90.0,
):
    """Resume evidência persistida; libera somente revisão independente."""
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.qualidade_json
        FROM snapshots s
        WHERE json_valid(s.qualidade_json)
          AND json_extract(
              s.qualidade_json,
              '$.auditoria_indicadores_temporais_lista.versao'
          ) = 'packball-lista-janelas-sombra-v1'
        ORDER BY s.id
        """
    ).fetchall()
    comparacoes = []
    partidas = set()
    snapshots = set()
    for linha in linhas:
        try:
            qualidade = json.loads(linha["qualidade_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        auditoria = qualidade.get("auditoria_indicadores_temporais_lista") or {}
        try:
            idade = float(auditoria.get("idade_segundos"))
        except (TypeError, ValueError):
            continue
        if idade < -5 or idade > float(idade_comparacao_maxima_segundos):
            continue
        itens = auditoria.get("comparacoes") or []
        if not itens:
            continue
        comparacoes.extend(
            (int(linha["partida_id"]), item)
            for item in itens if isinstance(item, dict)
        )
        partidas.add(int(linha["partida_id"]))
        snapshots.add(int(linha["id"]))
    total = len(comparacoes)
    acertos = sum(
        item.get("concordante_tolerancia") is True
        for _, item in comparacoes
    )
    atividade = sum(
        item.get("atividade_concordante") is True
        for _, item in comparacoes
    )
    limite = _wilson_inferior(acertos, total)
    pronto = bool(
        total >= int(minimo_comparacoes)
        and len(partidas) >= int(minimo_partidas)
        and limite is not None
        and limite >= float(limite_inferior_minimo)
    )
    por_metrica = {}
    metricas_aprovadas = []
    minimo_metrica = max(int(minimo_comparacoes) // 2, 15)
    for metrica in ("chutes", "escanteios"):
        itens_metrica = [
            (partida_id, item)
            for partida_id, item in comparacoes
            if item.get("metrica") == metrica
        ]
        total_metrica = len(itens_metrica)
        acertos_metrica = sum(
            item.get("concordante_tolerancia") is True
            for _, item in itens_metrica
        )
        partidas_metrica = len({
            partida_id for partida_id, _ in itens_metrica
        })
        limite_metrica = _wilson_inferior(
            acertos_metrica, total_metrica
        )
        aprovada = bool(
            pronto
            and total_metrica >= minimo_metrica
            and partidas_metrica >= int(minimo_partidas)
            and limite_metrica is not None
            and limite_metrica >= float(limite_inferior_minimo)
        )
        if aprovada:
            metricas_aprovadas.append(metrica)
        por_metrica[metrica] = {
            "comparacoes": total_metrica,
            "partidas_distintas": partidas_metrica,
            "concordancias": acertos_metrica,
            "taxa_concordancia": (
                round(acertos_metrica / total_metrica, 4)
                if total_metrica else None
            ),
            "limite_inferior_wilson_95": (
                round(limite_metrica, 4)
                if limite_metrica is not None else None
            ),
            "aprovada_para_fallback": aprovada,
        }
    return {
        "versao": "packball-lista-janelas-revisao-v1",
        "comparacoes_independentes": total,
        "snapshots": len(snapshots),
        "partidas_distintas": len(partidas),
        "concordancias_tolerancia": acertos,
        "taxa_concordancia": round(acertos / total, 4) if total else None,
        "taxa_concordancia_atividade": (
            round(atividade / total, 4) if total else None
        ),
        "limite_inferior_wilson_95": (
            round(limite, 4) if limite is not None else None
        ),
        "criterios": {
            "minimo_comparacoes": int(minimo_comparacoes),
            "minimo_partidas": int(minimo_partidas),
            "limite_inferior_minimo": float(limite_inferior_minimo),
            "idade_comparacao_maxima_segundos": float(
                idade_comparacao_maxima_segundos
            ),
        },
        "pronto_para_revisao": pronto,
        "por_metrica": por_metrica,
        "metricas_aprovadas": metricas_aprovadas,
        "aplicacao_sinais": False,
        "promocao_automatica": False,
    }
