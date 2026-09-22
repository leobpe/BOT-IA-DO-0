"""Validação prospectiva do challenger balanceado de Próximo Gol.

A análise retrospectiva serve apenas para formular a hipótese. Esta rotina
mede somente oportunidades posteriores à âncora imutável, congela a primeira
coorte e nunca promove ou envia o método automaticamente.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime

from proximo_gol_balanceado_sombra import (
    CHAVE_DEFINICAO,
    RESULTADOS_VALIDOS_MINIMOS,
    TAMANHO_COORTE,
    avaliar,
    definicao,
)
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)
from valor_mercado import referencia_tres_vias_sincronizada
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)


VERSAO_VALIDACAO = "validacao-proximo-gol-balanceado-sombra-v4"
DESENVOLVIMENTO = 28
HOLDOUT = 12
RESULTADOS_VALIDOS_HOLDOUT_MINIMOS = 10
RESULTADOS_VALIDOS_DESENVOLVIMENTO_MINIMOS = 25
COBERTURA_REFERENCIA_SEM_VIG_MINIMA = 0.90
MINIMO_RESULTADOS_ALERTA_DESFAVORAVEL = 20
RESULTADOS_VALIDOS = {"green", "half_green", "red", "half_red"}


def _gols_placar(placar):
    if isinstance(placar, str):
        partes = placar.replace("x", "-").split("-")
    elif isinstance(placar, (list, tuple)):
        partes = placar
    else:
        return None
    if len(partes) < 2:
        return None
    try:
        return int(float(partes[0])) + int(float(partes[1]))
    except (TypeError, ValueError):
        return None


def _metricas(linhas):
    validas = [
        item for item in linhas
        if item["resultado"] in RESULTADOS_VALIDOS
        and item["retorno_unidades"] is not None
    ]
    retornos = [float(item["retorno_unidades"]) for item in validas]
    referencias = [
        item for item in validas
        if item.get("probabilidade_mercado_sem_vig") is not None
    ]
    residuos = [
        (
            1.0 if item["resultado"] in {"green", "half_green"}
            else 0.0
        ) - float(item["probabilidade_mercado_sem_vig"])
        for item in referencias
    ]
    lucro = sum(retornos)
    intervalo = None
    if len(retornos) >= 2:
        media = statistics.fmean(retornos)
        erro = statistics.stdev(retornos) / math.sqrt(len(retornos))
        intervalo = [
            round(media - 1.96 * erro, 4),
            round(media + 1.96 * erro, 4),
        ]
    intervalo_residuo = None
    if len(residuos) >= 2:
        media_residuo = statistics.fmean(residuos)
        erro_residuo = statistics.stdev(residuos) / math.sqrt(
            len(residuos)
        )
        intervalo_residuo = [
            round(media_residuo - 1.96 * erro_residuo, 4),
            round(media_residuo + 1.96 * erro_residuo, 4),
        ]
    return {
        "candidatos": len(linhas),
        "validos": len(validas),
        "greens": sum(
            item["resultado"] in {"green", "half_green"}
            for item in validas
        ),
        "reds": sum(
            item["resultado"] in {"red", "half_red"}
            for item in validas
        ),
        "pendentes": sum(item["resultado"] is None for item in linhas),
        "invalidos": len(linhas) - len(validas) - sum(
            item["resultado"] is None for item in linhas
        ),
        "lucro_unidades": round(lucro, 4),
        "roi": round(lucro / len(validas), 4) if validas else None,
        "intervalo_roi_95": intervalo,
        "referencia_sem_vig": {
            "cobertura": len(referencias),
            "taxa_cobertura": (
                round(len(referencias) / len(validas), 4)
                if validas else None
            ),
            "probabilidade_mercado_media": (
                round(statistics.fmean([
                    float(item["probabilidade_mercado_sem_vig"])
                    for item in referencias
                ]), 4)
                if referencias else None
            ),
            "desvio_observado_menos_mercado": (
                round(statistics.fmean(residuos), 4)
                if residuos else None
            ),
            "intervalo_desvio_95": intervalo_residuo,
            "uso": "diagnostico_sem_alterar_coorte",
        },
    }


def _carregar_ancora(conexao):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is None:
        return None
    documento = json.loads(linha["valor"])
    esperada = definicao()
    divergencias = [
        campo for campo, valor in esperada.items()
        if documento.get(campo) != valor
    ]
    if divergencias:
        raise RuntimeError(
            "Âncora do Próximo Gol balanceado inconsistente: "
            + ",".join(divergencias)
        )
    return documento


def _carregar_coorte(conexao, documento):
    linhas = conexao.execute(
        """
        SELECT s.id,s.partida_id,s.criado_em,s.features_json,snapshot.placar,
               r.resultado,r.retorno_unidades
        FROM sinais s
        JOIN snapshots snapshot ON snapshot.id=s.snapshot_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE datetime(s.criado_em)>=datetime(?)
          AND s.mercado='proximo_gol'
          AND s.status='simulacao'
          AND s.regra_versao=?
          AND json_extract(
                s.features_json,'$.exploracao_sombra.versao'
              )=?
          AND json_extract(
                s.features_json,
                '$.proximo_gol_balanceado_sombra.definicao_sha256'
              )=?
        ORDER BY datetime(s.criado_em),s.id
        """,
        (
            documento["registrado_em"],
            VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
            documento["definicao_sha256"],
        ),
    ).fetchall()
    independentes = []
    vistos = set()
    for linha in linhas:
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        gols = features.get("gols_atuais")
        try:
            gols = int(float(gols))
        except (TypeError, ValueError):
            gols = _gols_placar(linha["placar"])
        if gols is None:
            continue
        chave = (linha["partida_id"], gols)
        if chave in vistos:
            continue
        vistos.add(chave)
        referencia = referencia_tres_vias_sincronizada({
            "features": features,
        })
        probabilidade_mercado = None
        if referencia is not None:
            odds = referencia["odds"]
            selecao = referencia["selecao"]
            soma_implicitas = sum(1.0 / valor for valor in odds.values())
            probabilidade_mercado = (
                (1.0 / odds[selecao]) / soma_implicitas
            )
        independentes.append({
            "id": linha["id"],
            "partida_id": linha["partida_id"],
            "gols_atuais": gols,
            "criado_em": linha["criado_em"],
            "resultado": linha["resultado"],
            "retorno_unidades": linha["retorno_unidades"],
            "probabilidade_mercado_sem_vig": probabilidade_mercado,
        })
        if len(independentes) >= TAMANHO_COORTE:
            break
    return independentes


def _carregar_funil_origem(conexao, documento):
    linhas = conexao.execute(
        """
        SELECT s.id,s.partida_id,s.criado_em,s.odd,s.pontuacao_tecnica,
               s.motivos_json,
               s.features_json,snapshot.placar
        FROM sinais s
        JOIN snapshots snapshot ON snapshot.id=s.snapshot_id
        WHERE datetime(s.criado_em)>=datetime(?)
          AND s.mercado='proximo_gol'
          AND s.regra_versao=?
        ORDER BY datetime(s.criado_em),s.id
        """,
        (
            documento["registrado_em"],
            VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
        ),
    ).fetchall()
    etapas = (
        ("origem_v10f", "origem_v10f"),
        (
            "somente_bloqueios_pressao_qualidade",
            "somente_bloqueios_pressao_qualidade",
        ),
        ("qualidade_95", "qualidade_completa"),
        ("minuto_ate_75", "minuto_valido"),
        ("odd_140_164", "odd_curta"),
        ("pressao_pico_50_69", "pressao_balanceada"),
        ("chute_dominante_5min", "chute_dominante_recente"),
        ("pontuacao_tecnica_60", "pontuacao_tecnica_suficiente"),
        ("vantagem_pressao_media_10", "dominio_medio_confirmado"),
    )
    por_estado = {}
    ultimo_instante = None
    invalidas = 0
    for linha in linhas:
        try:
            features = json.loads(linha["features_json"] or "{}")
            motivos = json.loads(linha["motivos_json"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            invalidas += 1
            continue
        if not isinstance(features, dict) or not isinstance(motivos, list):
            invalidas += 1
            continue
        gols = features.get("gols_atuais")
        try:
            gols = int(float(gols))
        except (TypeError, ValueError):
            gols = _gols_placar(linha["placar"])
        if gols is None:
            invalidas += 1
            continue
        bloqueios = [
            str(item).split("bloqueio:", 1)[1].strip()
            for item in motivos
            if str(item).startswith("bloqueio:")
        ]
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            "odd": linha["odd"],
            "pontuacao_tecnica": linha["pontuacao_tecnica"],
            "bloqueios": bloqueios,
            "features": features,
        }
        criterios = avaliar(candidato)["criterios"]
        chave = (linha["partida_id"], gols)
        acumulados = por_estado.setdefault(
            chave, {nome: False for nome, _ in etapas}
        )
        passou = True
        for nome, criterio in etapas:
            passou = bool(passou and criterios.get(criterio))
            acumulados[nome] = bool(acumulados[nome] or passou)
        try:
            instante = datetime.fromisoformat(str(linha["criado_em"]))
        except (TypeError, ValueError):
            instante = None
        if instante is not None and (
            ultimo_instante is None or instante > ultimo_instante
        ):
            ultimo_instante = instante

    funil = {
        nome: sum(bool(estado[nome]) for estado in por_estado.values())
        for nome, _ in etapas
    }
    perdas = {}
    anterior = None
    for nome, _ in etapas:
        if anterior is not None:
            perdas[nome] = max(funil[anterior] - funil[nome], 0)
        anterior = nome
    gargalo = max(perdas, key=perdas.get) if perdas else None
    if gargalo is not None and perdas[gargalo] <= 0:
        gargalo = None
    perdas_internas = {
        nome: perda for nome, perda in perdas.items()
        if nome != "somente_bloqueios_pressao_qualidade"
    }
    gargalo_interno = (
        max(perdas_internas, key=perdas_internas.get)
        if perdas_internas else None
    )
    if (
        gargalo_interno is not None
        and perdas_internas[gargalo_interno] <= 0
    ):
        gargalo_interno = None
    try:
        inicio = datetime.fromisoformat(str(documento["registrado_em"]))
    except (KeyError, TypeError, ValueError):
        inicio = None
    horas = None
    if inicio is not None and ultimo_instante is not None:
        if inicio.tzinfo is not None:
            inicio = inicio.astimezone().replace(tzinfo=None)
        if ultimo_instante.tzinfo is not None:
            ultimo_instante = ultimo_instante.astimezone().replace(
                tzinfo=None
            )
        horas = max((ultimo_instante - inicio).total_seconds() / 3600, 0.0)
    elegiveis = funil.get("vantagem_pressao_media_10", 0)
    return {
        "estado": (
            "com_avaliacoes" if por_estado else "sem_avaliacoes_apos_ancora"
        ),
        "snapshots_avaliados": len(linhas),
        "linhas_invalidas": invalidas,
        "estados_independentes": len(por_estado),
        "funil_cumulativo": funil,
        "perdas_por_etapa": perdas,
        "gargalo_principal": gargalo,
        "gargalo_principal_interno": gargalo_interno,
        "taxa_elegibilidade_suplemento": (
            round(
                elegiveis
                / funil["somente_bloqueios_pressao_qualidade"], 4
            )
            if funil.get("somente_bloqueios_pressao_qualidade") else None
        ),
        "horas_observadas": round(horas, 3) if horas is not None else None,
        "candidatos_por_24h": (
            round(elegiveis * 24.0 / horas, 3)
            if horas is not None and horas >= 1.0 else None
        ),
        "criterio_independencia": "partida+estado_de_gols",
        "altera_sinal": False,
        "telegram": "somente_grupo_teste",
        "telegram_oficial": False,
    }


def resumir_validacao_proximo_gol_balanceado(conexao):
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "versao": VERSAO_VALIDACAO,
            "estado": "nao_registrada",
            "promocao_automatica": False,
            "telegram": False,
        }
    coorte = _carregar_coorte(conexao, documento)
    funil_origem = _carregar_funil_origem(conexao, documento)
    total = _metricas(coorte)
    desenvolvimento = _metricas(coorte[:DESENVOLVIMENTO])
    holdout = _metricas(coorte[DESENVOLVIMENTO:TAMANHO_COORTE])
    intervalo = total["intervalo_roi_95"]
    referencia_sem_vig = total["referencia_sem_vig"]
    referencia_sem_vig_holdout = holdout["referencia_sem_vig"]
    cobertura_sem_vig = referencia_sem_vig.get("taxa_cobertura")
    cobertura_sem_vig_holdout = referencia_sem_vig_holdout.get(
        "taxa_cobertura"
    )
    intervalo_desvio = referencia_sem_vig.get("intervalo_desvio_95")
    intervalo_desvio_holdout = referencia_sem_vig_holdout.get(
        "intervalo_desvio_95"
    )
    # O checkpoint usa sempre o prefixo fixo dos 20 primeiros candidatos.
    # Assim o watchdog não repete um teste estatístico opcional a cada novo
    # resultado, o que inflaria falsos alarmes de degradação.
    checkpoint_seguranca = _metricas(
        coorte[:MINIMO_RESULTADOS_ALERTA_DESFAVORAVEL]
    )
    intervalo_checkpoint = checkpoint_seguranca["intervalo_roi_95"]
    alerta_desfavoravel = bool(
        checkpoint_seguranca["validos"]
        >= MINIMO_RESULTADOS_ALERTA_DESFAVORAVEL
        and isinstance(intervalo_checkpoint, (list, tuple))
        and len(intervalo_checkpoint) == 2
        and intervalo_checkpoint[1] is not None
        and float(intervalo_checkpoint[1]) < 0
    )
    preco_justo_completo = bool(
        cobertura_sem_vig is not None
        and cobertura_sem_vig >= COBERTURA_REFERENCIA_SEM_VIG_MINIMA
        and intervalo_desvio is not None
        and intervalo_desvio[0] > 0
        and cobertura_sem_vig_holdout is not None
        and cobertura_sem_vig_holdout
        >= COBERTURA_REFERENCIA_SEM_VIG_MINIMA
        and intervalo_desvio_holdout is not None
        and intervalo_desvio_holdout[0] > 0
    )
    coorte_fechada = len(coorte) >= TAMANHO_COORTE
    resultados_completos = coorte_fechada and total["pendentes"] == 0
    if not coorte_fechada:
        decisao = "aguardando_amostra_futura"
    elif total["pendentes"]:
        decisao = "aguardando_resultados"
    elif (
        total["validos"] >= RESULTADOS_VALIDOS_MINIMOS
        and desenvolvimento["validos"]
        >= RESULTADOS_VALIDOS_DESENVOLVIMENTO_MINIMOS
        and holdout["validos"] >= RESULTADOS_VALIDOS_HOLDOUT_MINIMOS
        and total["roi"] is not None
        and total["roi"] > 0
        and intervalo is not None
        and intervalo[0] > 0
        and desenvolvimento["roi"] is not None
        and desenvolvimento["roi"] > 0
        and holdout["roi"] is not None
        and holdout["roi"] > 0
        and preco_justo_completo
    ):
        decisao = "favoravel_para_revisao_manual"
    else:
        decisao = "inconclusiva_ou_desfavoravel"
    return {
        "versao": VERSAO_VALIDACAO,
        "regra_versao": VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
        **total,
        "estado": "encerrada" if resultados_completos else "coletando",
        "decisao": decisao,
        "coorte_fechada": coorte_fechada,
        "resultados_completos": resultados_completos,
        "tamanho_coorte": TAMANHO_COORTE,
        "faltam": max(0, TAMANHO_COORTE - len(coorte)),
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "funil_origem_v10f": funil_origem,
        "registrado_em": documento["registrado_em"],
        "definicao_sha256": documento["definicao_sha256"],
        "populacao": "primeiro_sinal_por_partida_e_estado_de_gols",
        "criterio": (
            "roi_total_ic95_inferior_roi_dev_holdout_positivos_e_"
            "residuo_sem_vig_ic95_inferior_positivo"
        ),
        "gate_preco_justo": {
            "cobertura_minima": COBERTURA_REFERENCIA_SEM_VIG_MINIMA,
            "cobertura_observada": cobertura_sem_vig,
            "intervalo_desvio_observado_menos_mercado_95": (
                intervalo_desvio
            ),
            "holdout": {
                "cobertura_observada": cobertura_sem_vig_holdout,
                "intervalo_desvio_observado_menos_mercado_95": (
                    intervalo_desvio_holdout
                ),
            },
            "satisfeito": preco_justo_completo,
        },
        "alerta_desfavoravel": alerta_desfavoravel,
        "rollback_recomendado": alerta_desfavoravel,
        "checkpoint_seguranca": checkpoint_seguranca,
        "politica_seguranca_grupo": {
            "minimo_resultados_validos": (
                MINIMO_RESULTADOS_ALERTA_DESFAVORAVEL
            ),
            "criterio": "limite_superior_ic95_roi_abaixo_de_zero",
            "populacao_checkpoint": "primeiros_20_candidatos_da_coorte",
            "efeito": "suspender_somente_telegram_grupo_teste",
            "coleta_sombra_continua": True,
            "parada_obrigatoria_ao_fechar_coorte": True,
            "reativacao_automatica": False,
        },
        "promocao_automatica": False,
        "telegram": "somente_grupo_teste",
        "telegram_oficial": False,
    }
