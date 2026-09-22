"""Diagnostico somente leitura do movimento de preco apos o alerta.

Em mercados live nao existe uma closing line universal: o contrato pode ser
liquidado por um gol ou escanteio antes do proximo preco. Por isso este modulo
mede o valor mark-to-market a partir de 2 minutos, na mesma linha, fonte e
bookmaker. Se o contrato liquidar antes disso, usa 1 para green e 0 para red;
se continuar aberto, usa a probabilidade sem vig da primeira cotacao exata.
Isso evita o vies grave de medir apenas jogos que sobreviveram sem evento.

O resultado e evidência auxiliar de desajuste, nao gate operacional. A leitura
principal usa somente a primeira entrega de cada partida, escolhida antes de
saber se sera comparavel. Os recortes por mercado usam a primeira entrega da
partida naquele mercado; por isso nao sao somados para formar uma amostra total.
Todas as entregas permanecem em diagnosticos correlacionados separados. Nenhuma
regra e promovida, nenhum sinal e alterado e nenhum Telegram e enviado.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import statistics
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from acompanhamento_odd import (
    FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS,
    TOLERANCIA_RELOGIO_ODD_SEGUNDOS,
    VERSAO_EVIDENCIA_OFERTA_RAPIDA,
    VERSAO_EVIDENCIA_OFERTA_RAPIDA_V2,
    VERSAO_EVIDENCIA_OFERTA_RAPIDA_V3,
    validar_contrato_mercado_oferta,
    validar_identidade_evento_oferta,
)
from coerencia_curva_odds import (
    VERSAO_EVIDENCIA_ANOMALIA,
    validar_evidencia_anomalia_curva,
)
from origem_mercado import (
    assinatura_origem_mercado,
    normalizar_origem_mercado,
)
from valor_mercado import avaliar_margem_bookmaker
from clv_pos_alerta import (
    ESTADO_OBSERVACAO_CLV,
    HORIZONTE_MAXIMO_SEGUNDOS,
    HORIZONTE_MINIMO_SEGUNDOS,
    MERCADOS_CLV_MONITORADOS,
    PREFIXO_REFERENCIA_CLV,
    STATUS_ANULADO,
    VERSAO_EVIDENCIA_ESTADO_CLV,
    VERSAO_EVIDENCIA_ESTADO_CLV_V1,
    VERSAO_EVIDENCIA_ESTADO_CLV_V2,
    canal_e_entrada,
    linha_equivalente,
    mercado_encerrado,
    modo_coleta_estado_clv,
    normalizar_escanteios_estado,
    referencia_clv,
    status_normalizado,
)


VERSAO = "avaliacao-clv-live-mark-to-market-read-only-v27"
VERSAO_COTACAO_ENTRADA_V1 = "cotacao-entrada-clv-v1"
VERSAO_COTACAO_ENTRADA = "cotacao-entrada-clv-v2"
VERSAO_COBERTURA_COTACAO_PROSPECTIVA = (
    "cobertura-cotacao-entrada-prospectiva-v2"
)
VERSAO_COORTE_CLV_PROSPECTIVA = "coorte-clv-prospectiva-fixa-120-v1"
VERSAO_CADEIA_CUSTODIA_CLV = "cadeia-custodia-clv-sqlite-v16"
CHAVE_ESTADO_COTACAO_ENTRADA = "cotacao_entrada_clv_estado"
ESTADO_COTACAO_CONGELADA = "congelada_v1"
BANCO = Path(__file__).with_name("monitor_packball.db")
IDADE_ODD_MAXIMA_SEGUNDOS = 120.0
MERCADOS_SUPORTADOS = MERCADOS_CLV_MONITORADOS
MERCADOS_ESCANTEIOS = frozenset({
    "proximo_escanteio", "escanteios_ft_asiatico",
})
AMOSTRA_MINIMA_EVIDENCIA = 30
COBERTURA_MINIMA_INFORMAR_EDGE = 0.90
TAMANHO_COORTE_CLV_PROSPECTIVA = 120
TAMANHO_DESENVOLVIMENTO_CLV = 84
TAMANHO_HOLDOUT_CLV = 36
GATILHOS_CADEIA_CUSTODIA_CLV = {
    "trg_entregas_alertas_entrada_update_imutavel": (
        "before update", " on entregas_alertas", "raise", "abort",
    ),
    "trg_entregas_alertas_entrada_delete_imutavel": (
        "before delete on entregas_alertas", "raise", "abort",
    ),
    "trg_sinais_entregues_evidencia_update_imutavel": (
        "before update", " on sinais", "raise", "abort",
    ),
    "trg_sinais_entregues_evidencia_delete_imutavel": (
        "before delete on sinais", "raise", "abort",
    ),
    "trg_snapshots_update_imutavel": (
        "before update on snapshots", "raise", "abort",
    ),
    "trg_snapshots_clv_delete_imutavel": (
        "before delete on snapshots", "entregas_alertas",
        "+10 minutes", "raise", "abort",
    ),
    "trg_odds_update_imutavel": (
        "before update on odds", "raise", "abort",
    ),
    "trg_odds_clv_delete_imutavel": (
        "before delete on odds", "entregas_alertas",
        "+10 minutes", "raise", "abort",
    ),
    "trg_observacoes_odds_evidencia_update_imutavel": (
        "before update on observacoes_fontes_odds",
        "consulta_monitoramento", "raise", "abort",
    ),
    "trg_observacoes_odds_evidencia_delete_imutavel": (
        "before delete on observacoes_fontes_odds",
        "consulta_monitoramento", "raise", "abort",
    ),
    "trg_observacoes_odds_identidade_estavel": (
        "before insert on observacoes_fontes_odds",
        "identidade_evento.evento_externo_id", "raise", "abort",
    ),
    "trg_observacoes_odds_identidade_estavel_v2": (
        "before insert on observacoes_fontes_odds",
        "oferta-monitorada-odd-v4", "raise", "abort",
    ),
}
CRITICOS_T_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _json_objeto(valor):
    if isinstance(valor, dict):
        return valor
    try:
        documento = json.loads(valor or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return documento if isinstance(documento, dict) else {}


def _texto(valor):
    return str(valor or "").strip().casefold()


def _data(valor):
    if not valor:
        return None
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if instante.tzinfo is not None:
        instante = instante.astimezone(timezone.utc).replace(tzinfo=None)
    return instante


def _data_utc(valor):
    """Normaliza ISO para UTC, assumindo horario local quando vier sem fuso."""
    if not valor:
        return None
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if instante.tzinfo is None:
        instante = instante.astimezone()
    return instante.astimezone(timezone.utc).replace(tzinfo=None)


def _linhas_estrutura(conexao, consulta):
    return [dict(linha) for linha in conexao.execute(consulta).fetchall()]


def _linhas_equivalentes(valor_a, valor_b):
    try:
        return math.isclose(
            float(valor_a), float(valor_b), abs_tol=1e-9
        )
    except (TypeError, ValueError):
        return str(valor_a) == str(valor_b)


def _auditar_conteudo_observacoes_odds(conexao):
    """Recalcula hashes e valida o vínculo causal das ofertas rápidas."""
    chaves_problemas = (
        "data_invalida", "payload_sem_hash", "hash_sem_payload",
        "hash_formato_invalido", "hash_divergente", "json_invalido",
        "referencia_invalida", "sinal_ausente", "partida_divergente",
        "payload_sinal_divergente", "mercado_divergente",
        "linha_divergente", "fonte_divergente", "fonte_vazia",
        "odd_invalida", "idade_odd_invalida", "cache_indeterminado",
        "fonte_coletado_em_invalido", "fonte_coletado_em_futuro",
        "fonte_coletado_em_expirado", "idade_fonte_divergente",
        "regressao_temporal", "schema_oferta_desconhecido",
        "contrato_mercado_v2_incompleto",
        "contrato_mercado_v3_incompleto",
        "identidade_evento_v3_invalida",
        "identidade_evento_v3_equipes_divergentes",
        "contrato_mercado_v4_incompleto",
        "origem_mercado_v4_invalida",
        "identidade_evento_v4_invalida",
        "identidade_evento_v4_equipes_divergentes",
        "evento_externo_id_coluna_divergente",
        "continuidade_identidade_evento_v3_quebrada",
        "schema_anomalia_curva_desconhecido",
        "contrato_anomalia_curva_incompleto",
        "identidade_evento_anomalia_curva_invalida",
        "identidade_evento_anomalia_curva_equipes_divergentes",
        "anomalia_curva_odd_invalida",
        "motivo_anomalia_curva_divergente",
        "referencia_clv_invalida", "schema_estado_clv_desconhecido",
        "estado_clv_sinal_divergente", "estado_clv_fixture_divergente",
        "estado_clv_horizonte_invalido", "estado_clv_oferta_divergente",
        "estado_clv_efeito_operacional", "estado_clv_duplicado",
        "estado_clv_escanteios_invalidos",
        "estado_clv_modo_coleta_invalido",
        "estado_clv_fonte_entrada_divergente",
        "cotacao_entrada_clv_entregue_invalida",
    )
    problemas = {chave: 0 for chave in chaves_problemas}
    try:
        observacoes = _linhas_estrutura(
            conexao,
            """
            SELECT id, partida_id, fonte, consultado_em, estado, mercado,
                   motivo,
                   evento_externo_id,
                   oferta_json, evidencia_sha256, evidencia_referencia
            FROM observacoes_fontes_odds
            WHERE estado<>'consulta_monitoramento'
            ORDER BY id
            """,
        )
        sinais = {
            int(linha["id"]): linha
            for linha in _linhas_estrutura(
                conexao,
                """
                SELECT id, partida_id, mercado, linha, odd, criado_em,
                       features_json
                FROM sinais
                """,
            )
        }
        entregas_entrada = {}
        for entrega in _linhas_estrutura(
            conexao,
            """
            SELECT sinal_id,canal,COALESCE(entregue_em,tentado_em) AS entregue_em
            FROM entregas_alertas
            WHERE status='entregue'
            ORDER BY datetime(COALESCE(entregue_em,tentado_em)),id
            """,
        ):
            if canal_e_entrada(entrega.get("canal")):
                entregas_entrada.setdefault(
                    int(entrega["sinal_id"]), entrega.get("entregue_em")
                )
    except (sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "auditoria_conteudo_falhou",
            "erro": type(erro).__name__,
            "observacoes_auditadas": 0,
            "ofertas_monitoradas": 0,
            "ofertas_contrato_v2": 0,
            "ofertas_contrato_v3": 0,
            "ofertas_contrato_v4": 0,
            "anomalias_curva_odds": 0,
            "estados_clv_pos_alerta": 0,
            "cotacoes_entrada_clv_entregues_auditadas": 0,
            "ofertas_legadas_sem_schema": 0,
            "payloads_auditados": 0,
            "problemas": problemas,
            "fingerprint_evidencias": None,
        }

    try:
        partidas = {
            int(linha["id"]): linha
            for linha in _linhas_estrutura(
                conexao,
                "SELECT id, mandante, visitante, api_fixture_id FROM partidas",
            )
        }
    except (sqlite3.Error, TypeError, ValueError):
        partidas = {}

    ofertas_monitoradas = 0
    ofertas_contrato_v2 = 0
    ofertas_contrato_v3 = 0
    ofertas_contrato_v4 = 0
    anomalias_curva_odds = 0
    estados_clv_pos_alerta = 0
    ofertas_legadas_sem_schema = 0
    payloads_auditados = 0
    cotacoes_entrada_clv_entregues_auditadas = 0
    ultima_data_por_referencia = {}
    identidade_por_referencia_fonte = {}
    referencias_clv_vistas = set()
    observacoes_por_id = {
        int(observacao["id"]): observacao for observacao in observacoes
    }
    fingerprint = hashlib.sha256()
    for sinal_id in sorted(entregas_entrada):
        sinal = sinais.get(sinal_id)
        if sinal is None:
            continue
        features = _json_objeto(sinal.get("features_json"))
        if features.get(CHAVE_ESTADO_COTACAO_ENTRADA) != (
            ESTADO_COTACAO_CONGELADA
        ):
            continue
        cotacoes_entrada_clv_entregues_auditadas += 1
        if not isinstance(
            _cotacao_entrada_congelada(features, sinal), dict
        ):
            problemas["cotacao_entrada_clv_entregue_invalida"] += 1
        fingerprint.update(json.dumps(
            [
                "cotacao_entrada", sinal_id, sinal.get("mercado"),
                sinal.get("linha"), sinal.get("odd"),
                features.get("cotacao_entrada_clv"),
            ],
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))
    for observacao in observacoes:
        fingerprint.update(json.dumps(
            [
                observacao.get("id"), observacao.get("partida_id"),
                observacao.get("fonte"), observacao.get("consultado_em"),
                observacao.get("estado"), observacao.get("mercado"),
                observacao.get("evidencia_referencia"),
                observacao.get("evidencia_sha256"),
            ],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
        if _data(observacao.get("consultado_em")) is None:
            problemas["data_invalida"] += 1
        oferta_json = observacao.get("oferta_json")
        evidencia_sha256 = observacao.get("evidencia_sha256")
        payload = None
        if oferta_json is not None:
            payloads_auditados += 1
            if evidencia_sha256 is None:
                problemas["payload_sem_hash"] += 1
            try:
                payload = json.loads(oferta_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                problemas["json_invalido"] += 1
            calculado = hashlib.sha256(
                str(oferta_json).encode("utf-8")
            ).hexdigest()
            if evidencia_sha256 is not None:
                if not re.fullmatch(
                    r"[0-9a-f]{64}", str(evidencia_sha256)
                ):
                    problemas["hash_formato_invalido"] += 1
                elif calculado != str(evidencia_sha256):
                    problemas["hash_divergente"] += 1
        elif evidencia_sha256 is not None:
            problemas["hash_sem_payload"] += 1

        if observacao.get("estado") == ESTADO_OBSERVACAO_CLV:
            estados_clv_pos_alerta += 1
            referencia = str(
                observacao.get("evidencia_referencia") or ""
            )
            correspondencia = re.fullmatch(
                rf"{re.escape(PREFIXO_REFERENCIA_CLV)}(\d+)",
                referencia,
            )
            if correspondencia is None:
                problemas["referencia_clv_invalida"] += 1
                continue
            if referencia in referencias_clv_vistas:
                problemas["estado_clv_duplicado"] += 1
            referencias_clv_vistas.add(referencia)
            sinal_id = int(correspondencia.group(1))
            sinal = sinais.get(sinal_id)
            if sinal is None:
                problemas["sinal_ausente"] += 1
                continue
            if observacao.get("partida_id") != sinal.get("partida_id"):
                problemas["partida_divergente"] += 1
            if not isinstance(payload, dict):
                problemas["estado_clv_sinal_divergente"] += 1
                continue
            if payload.get("schema") not in {
                VERSAO_EVIDENCIA_ESTADO_CLV_V1,
                VERSAO_EVIDENCIA_ESTADO_CLV_V2,
                VERSAO_EVIDENCIA_ESTADO_CLV,
            }:
                problemas["schema_estado_clv_desconhecido"] += 1
            if payload.get("schema") == VERSAO_EVIDENCIA_ESTADO_CLV:
                if normalizar_escanteios_estado(
                    payload.get("escanteios")
                ) is False:
                    problemas["estado_clv_escanteios_invalidos"] += 1
                features_sinal = _json_objeto(sinal.get("features_json"))
                fonte_sinal = _texto(features_sinal.get("fonte_odds"))
                bookmaker_sinal = _texto(
                    features_sinal.get("bookmaker_odds")
                )
                if modo_coleta_estado_clv(
                    payload.get("fonte_entrada"),
                    payload.get("bookmaker_entrada"),
                ) != payload.get("modo_coleta"):
                    problemas["estado_clv_modo_coleta_invalido"] += 1
                if (
                    _texto(payload.get("fonte_entrada")) != fonte_sinal
                    or _texto(payload.get("bookmaker_entrada"))
                    != bookmaker_sinal
                ):
                    problemas["estado_clv_fonte_entrada_divergente"] += 1
            if (
                payload.get("sinal_id") != sinal_id
                or payload.get("partida_id") != sinal.get("partida_id")
                or payload.get("mercado") != sinal.get("mercado")
                or observacao.get("mercado") != sinal.get("mercado")
                or not linha_equivalente(
                    sinal.get("mercado"), payload.get("linha"),
                    sinal.get("linha"),
                )
            ):
                problemas["estado_clv_sinal_divergente"] += 1
            if (
                payload.get("aplicacao_sinais") is not False
                or payload.get("telegram") is not False
            ):
                problemas["estado_clv_efeito_operacional"] += 1
            partida = partidas.get(int(sinal.get("partida_id") or 0)) or {}
            fixture_esperada = str(partida.get("api_fixture_id") or "")
            if (
                not fixture_esperada
                or str(payload.get("fixture_id") or "") != fixture_esperada
                or str(observacao.get("evento_externo_id") or "")
                    != fixture_esperada
            ):
                problemas["estado_clv_fixture_divergente"] += 1
            entrega_real = entregas_entrada.get(sinal_id)
            consulta_utc = _data_utc(observacao.get("consultado_em"))
            entrega_utc = _data_utc(entrega_real)
            idade_payload = _numero(
                payload.get("idade_apos_entrega_segundos")
            )
            if (
                entrega_utc is None
                or consulta_utc is None
                or payload.get("entregue_em") != entrega_real
                or payload.get("consultado_em")
                    != observacao.get("consultado_em")
            ):
                problemas["estado_clv_horizonte_invalido"] += 1
            else:
                idade = (consulta_utc - entrega_utc).total_seconds()
                if (
                    not HORIZONTE_MINIMO_SEGUNDOS
                    <= idade <= HORIZONTE_MAXIMO_SEGUNDOS
                    or idade_payload is None
                    or abs(idade_payload - idade) > 1.0
                ):
                    problemas["estado_clv_horizonte_invalido"] += 1
            oferta_id = payload.get("oferta_observacao_id")
            oferta_disponivel = payload.get("oferta_exata_disponivel")
            if oferta_id is None:
                if oferta_disponivel is not False:
                    problemas["estado_clv_oferta_divergente"] += 1
            else:
                try:
                    oferta_vinculada = observacoes_por_id.get(int(oferta_id))
                except (TypeError, ValueError):
                    oferta_vinculada = None
                if (
                    oferta_disponivel is not True
                    or oferta_vinculada is None
                    or oferta_vinculada.get("estado") != "oferta_monitorada"
                    or oferta_vinculada.get("partida_id")
                        != sinal.get("partida_id")
                    or oferta_vinculada.get("mercado")
                        != sinal.get("mercado")
                    or oferta_vinculada.get("evidencia_referencia")
                        != f"acompanhamento_odd:{sinal_id}"
                ):
                    problemas["estado_clv_oferta_divergente"] += 1
            continue

        if observacao.get("estado") == "anomalia_curva_odd":
            anomalias_curva_odds += 1
            correspondencia = re.fullmatch(
                r"acompanhamento_odd:(\d+)",
                str(observacao.get("evidencia_referencia") or ""),
            )
            if correspondencia is None:
                problemas["referencia_invalida"] += 1
                continue
            referencia = str(observacao.get("evidencia_referencia"))
            instante = _data(observacao.get("consultado_em"))
            anterior = ultima_data_por_referencia.get(referencia)
            if (
                instante is not None and anterior is not None
                and instante < anterior
            ):
                problemas["regressao_temporal"] += 1
            if instante is not None and (
                anterior is None or instante > anterior
            ):
                ultima_data_por_referencia[referencia] = instante
            sinal_id = int(correspondencia.group(1))
            sinal = sinais.get(sinal_id)
            if sinal is None:
                problemas["sinal_ausente"] += 1
                continue
            if observacao.get("partida_id") != sinal.get("partida_id"):
                problemas["partida_divergente"] += 1
            if not isinstance(payload, dict):
                problemas["payload_sinal_divergente"] += 1
                problemas["anomalia_curva_odd_invalida"] += 1
                continue
            if payload.get("schema") != VERSAO_EVIDENCIA_ANOMALIA:
                problemas["schema_anomalia_curva_desconhecido"] += 1
            contrato = validar_contrato_mercado_oferta(
                payload,
                sinal.get("mercado"),
                sinal.get("linha"),
                exigir_origem=True,
            )
            if contrato.get("valido") is not True:
                problemas["contrato_anomalia_curva_incompleto"] += 1
            partida = partidas.get(int(sinal.get("partida_id") or 0)) or {}
            identidade = validar_identidade_evento_oferta(payload, {
                "placar": payload.get("placar"),
                "mandante": partida.get("mandante"),
                "visitante": partida.get("visitante"),
            })
            if identidade.get("valida") is not True:
                chave = (
                    "identidade_evento_anomalia_curva_equipes_divergentes"
                    if identidade.get("motivo")
                    == "evento_odd_equipes_divergentes"
                    else "identidade_evento_anomalia_curva_invalida"
                )
                problemas[chave] += 1
            else:
                prova = identidade["identidade_evento"]
                evento_externo_id = str(
                    prova.get("evento_externo_id") or ""
                )
                if str(observacao.get("evento_externo_id") or "") != (
                    evento_externo_id
                ):
                    problemas["evento_externo_id_coluna_divergente"] += 1
                chave_identidade = (
                    str(observacao.get("evidencia_referencia")),
                    _texto(payload.get("fonte")),
                )
                vinculo = (
                    evento_externo_id,
                    _texto(prova.get("orientacao")),
                )
                vinculo_anterior = identidade_por_referencia_fonte.get(
                    chave_identidade
                )
                if vinculo_anterior is None:
                    identidade_por_referencia_fonte[
                        chave_identidade
                    ] = vinculo
                elif vinculo_anterior != vinculo:
                    problemas[
                        "continuidade_identidade_evento_v3_quebrada"
                    ] += 1
            evidencia_curva = validar_evidencia_anomalia_curva(
                payload.get("coerencia_curva_odds"),
                mercado=sinal.get("mercado"),
                linha=sinal.get("linha"),
                origem_selecionada=payload.get("origem_mercado"),
                odd_selecionada=payload.get("odd"),
                odd_oposta_selecionada=payload.get("odd_oposta"),
            )
            if evidencia_curva.get("valida") is not True:
                problemas["anomalia_curva_odd_invalida"] += 1
            if str(observacao.get("motivo") or "") != str(
                (payload.get("coerencia_curva_odds") or {}).get("motivo")
                or ""
            ):
                problemas["motivo_anomalia_curva_divergente"] += 1
            if payload.get("sinal_origem_id") != sinal_id:
                problemas["payload_sinal_divergente"] += 1
            if (
                str(observacao.get("mercado") or "")
                != str(sinal.get("mercado") or "")
                or str(payload.get("mercado") or "")
                != str(sinal.get("mercado") or "")
            ):
                problemas["mercado_divergente"] += 1
            if not _linhas_equivalentes(
                payload.get("linha"), sinal.get("linha")
            ):
                problemas["linha_divergente"] += 1
            if _texto(payload.get("fonte")) != _texto(
                observacao.get("fonte")
            ):
                problemas["fonte_divergente"] += 1
            if not _texto(observacao.get("fonte")):
                problemas["fonte_vazia"] += 1
            odd = _numero(payload.get("odd"))
            if odd is None or odd <= 1.0:
                problemas["odd_invalida"] += 1
            idade_odd = _numero(payload.get("idade_segundos"))
            idade_valida = bool(
                idade_odd is not None
                and 0 <= idade_odd <= FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS
            )
            if not idade_valida:
                problemas["idade_odd_invalida"] += 1
            if not isinstance(payload.get("cache"), bool):
                problemas["cache_indeterminado"] += 1
            consulta_utc = _data_utc(observacao.get("consultado_em"))
            fonte_utc = _data_utc(payload.get("fonte_coletado_em"))
            if fonte_utc is None:
                problemas["fonte_coletado_em_invalido"] += 1
            elif consulta_utc is not None:
                atraso_fonte = (consulta_utc - fonte_utc).total_seconds()
                if atraso_fonte < -1.0:
                    problemas["fonte_coletado_em_futuro"] += 1
                elif atraso_fonte > FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS:
                    problemas["fonte_coletado_em_expirado"] += 1
                if idade_valida and abs(
                    max(atraso_fonte, 0.0) - idade_odd
                ) > TOLERANCIA_RELOGIO_ODD_SEGUNDOS:
                    problemas["idade_fonte_divergente"] += 1
            continue
        if observacao.get("estado") != "oferta_monitorada":
            continue
        ofertas_monitoradas += 1
        correspondencia = re.fullmatch(
            r"acompanhamento_odd:(\d+)",
            str(observacao.get("evidencia_referencia") or ""),
        )
        if correspondencia is None:
            problemas["referencia_invalida"] += 1
            continue
        referencia = str(observacao.get("evidencia_referencia"))
        instante = _data(observacao.get("consultado_em"))
        anterior = ultima_data_por_referencia.get(referencia)
        if instante is not None and anterior is not None and instante < anterior:
            problemas["regressao_temporal"] += 1
        # Preserve o maior instante já visto. Se uma leitura atrasada for
        # seguida por outra que ainda está atrás do máximo causal, ambas
        # precisam permanecer marcadas como fora de ordem.
        if instante is not None and (anterior is None or instante > anterior):
            ultima_data_por_referencia[referencia] = instante
        sinal_id = int(correspondencia.group(1))
        sinal = sinais.get(sinal_id)
        if sinal is None:
            problemas["sinal_ausente"] += 1
            continue
        if observacao.get("partida_id") != sinal.get("partida_id"):
            problemas["partida_divergente"] += 1
        if not isinstance(payload, dict):
            problemas["payload_sinal_divergente"] += 1
            problemas["mercado_divergente"] += 1
            problemas["linha_divergente"] += 1
            problemas["fonte_divergente"] += 1
            continue
        schema_oferta = payload.get("schema")
        if schema_oferta is None:
            ofertas_legadas_sem_schema += 1
        elif schema_oferta == VERSAO_EVIDENCIA_OFERTA_RAPIDA_V2:
            ofertas_contrato_v2 += 1
            contrato = validar_contrato_mercado_oferta(
                payload, sinal.get("mercado"), sinal.get("linha")
            )
            if contrato.get("valido") is not True:
                problemas["contrato_mercado_v2_incompleto"] += 1
        elif schema_oferta in {
            VERSAO_EVIDENCIA_OFERTA_RAPIDA_V3,
            VERSAO_EVIDENCIA_OFERTA_RAPIDA,
        }:
            contrato_v4 = (
                schema_oferta == VERSAO_EVIDENCIA_OFERTA_RAPIDA
            )
            if contrato_v4:
                ofertas_contrato_v4 += 1
            else:
                ofertas_contrato_v3 += 1
            contrato = validar_contrato_mercado_oferta(
                payload,
                sinal.get("mercado"),
                sinal.get("linha"),
                exigir_origem=contrato_v4,
            )
            if contrato.get("valido") is not True:
                if contrato_v4 and str(
                    contrato.get("motivo") or ""
                ).startswith("origem_mercado_"):
                    problemas["origem_mercado_v4_invalida"] += 1
                else:
                    problemas[
                        "contrato_mercado_v4_incompleto"
                        if contrato_v4
                        else "contrato_mercado_v3_incompleto"
                    ] += 1
            partida = partidas.get(int(sinal.get("partida_id") or 0)) or {}
            identidade = validar_identidade_evento_oferta(payload, {
                "placar": payload.get("placar"),
                "mandante": partida.get("mandante"),
                "visitante": partida.get("visitante"),
            })
            if identidade.get("valida") is not True:
                sufixo_versao = "v4" if contrato_v4 else "v3"
                chave_identidade_invalida = (
                    f"identidade_evento_{sufixo_versao}_equipes_divergentes"
                    if identidade.get("motivo")
                    == "evento_odd_equipes_divergentes"
                    else f"identidade_evento_{sufixo_versao}_invalida"
                )
                problemas[chave_identidade_invalida] += 1
            else:
                prova = identidade["identidade_evento"]
                evento_externo_id = str(
                    prova.get("evento_externo_id") or ""
                )
                if str(observacao.get("evento_externo_id") or "") != (
                    evento_externo_id
                ):
                    problemas[
                        "evento_externo_id_coluna_divergente"
                    ] += 1
                chave_identidade = (
                    referencia, _texto(payload.get("fonte"))
                )
                vinculo = (
                    evento_externo_id,
                    _texto(prova.get("orientacao")),
                )
                vinculo_anterior = identidade_por_referencia_fonte.get(
                    chave_identidade
                )
                if vinculo_anterior is None:
                    identidade_por_referencia_fonte[
                        chave_identidade
                    ] = vinculo
                elif vinculo_anterior != vinculo:
                    problemas[
                        "continuidade_identidade_evento_v3_quebrada"
                    ] += 1
        else:
            problemas["schema_oferta_desconhecido"] += 1
        if not _texto(observacao.get("fonte")):
            problemas["fonte_vazia"] += 1
        odd = _numero(payload.get("odd"))
        if odd is None or not math.isfinite(odd) or odd <= 1.0:
            problemas["odd_invalida"] += 1
        idade_odd = _numero(payload.get("idade_segundos"))
        idade_valida = bool(
            idade_odd is not None
            and math.isfinite(idade_odd)
            and 0 <= idade_odd <= FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS
        )
        if not idade_valida:
            problemas["idade_odd_invalida"] += 1
        if not isinstance(payload.get("cache"), bool):
            problemas["cache_indeterminado"] += 1
        consulta_utc = _data_utc(observacao.get("consultado_em"))
        fonte_utc = _data_utc(payload.get("fonte_coletado_em"))
        if fonte_utc is None:
            problemas["fonte_coletado_em_invalido"] += 1
        elif consulta_utc is not None:
            atraso_fonte = (consulta_utc - fonte_utc).total_seconds()
            if atraso_fonte < -1.0:
                problemas["fonte_coletado_em_futuro"] += 1
            elif atraso_fonte > FRESCOR_ODD_RAPIDA_MAXIMO_SEGUNDOS:
                problemas["fonte_coletado_em_expirado"] += 1
            if idade_valida and abs(
                max(atraso_fonte, 0.0) - idade_odd
            ) > TOLERANCIA_RELOGIO_ODD_SEGUNDOS:
                problemas["idade_fonte_divergente"] += 1
        if payload.get("sinal_origem_id") != sinal_id:
            problemas["payload_sinal_divergente"] += 1
        if (
            str(observacao.get("mercado") or "")
            != str(sinal.get("mercado") or "")
            or str(payload.get("mercado") or "")
            != str(sinal.get("mercado") or "")
        ):
            problemas["mercado_divergente"] += 1
        if not _linhas_equivalentes(
            payload.get("linha"), sinal.get("linha")
        ):
            problemas["linha_divergente"] += 1
        if _texto(payload.get("fonte")) != _texto(
            observacao.get("fonte")
        ):
            problemas["fonte_divergente"] += 1

    total_problemas = sum(problemas.values())
    return {
        "saudavel": total_problemas == 0,
        "estado": "integro" if total_problemas == 0 else "inconsistente",
        "observacoes_auditadas": len(observacoes),
        "ofertas_monitoradas": ofertas_monitoradas,
        "ofertas_contrato_v2": ofertas_contrato_v2,
        "ofertas_contrato_v3": ofertas_contrato_v3,
        "ofertas_contrato_v4": ofertas_contrato_v4,
        "anomalias_curva_odds": anomalias_curva_odds,
        "estados_clv_pos_alerta": estados_clv_pos_alerta,
        "cotacoes_entrada_clv_entregues_auditadas": (
            cotacoes_entrada_clv_entregues_auditadas
        ),
        "ofertas_legadas_sem_schema": ofertas_legadas_sem_schema,
        "payloads_auditados": payloads_auditados,
        "problemas": problemas,
        "total_problemas": total_problemas,
        "fingerprint_evidencias": fingerprint.hexdigest(),
    }


def auditar_cadeia_custodia_clv(conexao):
    """Prova que a base consultada protege a populacao e seus precos.

    O relatorio CLV pode ser executado fora do runtime operacional. Por isso
    ele nao deve depender apenas do pre-voo para saber se entregas, sinais,
    snapshots e odds continuam imutaveis na copia SQLite consultada.
    """
    try:
        linhas = conexao.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type='trigger'
            """
        ).fetchall()
    except sqlite3.Error as erro:
        return {
            "versao": VERSAO_CADEIA_CUSTODIA_CLV,
            "saudavel": False,
            "estado": "auditoria_sqlite_falhou",
            "erro": type(erro).__name__,
            "gatilhos_exigidos": sorted(GATILHOS_CADEIA_CUSTODIA_CLV),
            "gatilhos_presentes": [],
            "gatilhos_ausentes": sorted(GATILHOS_CADEIA_CUSTODIA_CLV),
            "definicoes_invalidas": [],
            "fingerprint_definicoes": None,
            "integridade_evidencias": {
                "saudavel": False,
                "estado": "auditoria_conteudo_nao_executada",
            },
            "bloqueia_inferencia": True,
        }
    definicoes = {
        str(linha[0]): " ".join(str(linha[1] or "").casefold().split())
        for linha in linhas
    }
    ausentes = sorted(
        set(GATILHOS_CADEIA_CUSTODIA_CLV) - set(definicoes)
    )
    invalidas = sorted(
        nome for nome, fragmentos in GATILHOS_CADEIA_CUSTODIA_CLV.items()
        if nome in definicoes
        and any(fragmento not in definicoes[nome] for fragmento in fragmentos)
    )
    presentes = sorted(
        nome for nome in GATILHOS_CADEIA_CUSTODIA_CLV
        if nome in definicoes
    )
    corpo_fingerprint = [
        [nome, definicoes[nome]] for nome in presentes
    ]
    fingerprint = hashlib.sha256(
        json.dumps(
            corpo_fingerprint, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    integridade_evidencias = _auditar_conteudo_observacoes_odds(conexao)
    saudavel = bool(
        not ausentes and not invalidas
        and integridade_evidencias.get("saudavel") is True
    )
    if saudavel:
        estado = "integra"
    elif ausentes or invalidas:
        estado = "protecao_ausente_ou_invalida"
    else:
        estado = "evidencia_de_odd_inconsistente"
    return {
        "versao": VERSAO_CADEIA_CUSTODIA_CLV,
        "saudavel": saudavel,
        "estado": estado,
        "gatilhos_exigidos": sorted(GATILHOS_CADEIA_CUSTODIA_CLV),
        "gatilhos_presentes": presentes,
        "gatilhos_ausentes": ausentes,
        "definicoes_invalidas": invalidas,
        "fingerprint_definicoes": fingerprint,
        "integridade_evidencias": integridade_evidencias,
        "bloqueia_inferencia": not saudavel,
    }


def _par(valor):
    if isinstance(valor, (list, tuple)):
        partes = valor
    else:
        partes = str(valor or "").replace("x", "-").split("-")
    if len(partes) < 2:
        return None
    try:
        return tuple(
            int(float(str(parte).replace("%", "").strip()))
            for parte in partes[:2]
        )
    except (TypeError, ValueError):
        return None


def _total_par(valor):
    partes = _par(valor)
    return sum(partes) if partes is not None else None


def _total_escanteios(estatisticas):
    estatisticas = _json_objeto(estatisticas)
    for chave, valor in estatisticas.items():
        normalizada = _texto(chave)
        if "escante" in normalizada or "corner" in normalizada:
            total = _total_par(valor)
            if total is not None:
                return total
    return None


def _par_escanteios(estatisticas):
    estatisticas = _json_objeto(estatisticas)
    for chave, valor in estatisticas.items():
        normalizada = _texto(chave)
        if "escante" in normalizada or "corner" in normalizada:
            partes = _par(valor)
            if partes is not None:
                return partes
    return None


def _proveniencia(item, estrutura):
    return (
        _texto((item or {}).get("fonte") or estrutura.get("fonte")),
        _texto((item or {}).get("bookmaker") or estrutura.get("bookmaker")),
    )


def _cotacao_fresca(item, estrutura):
    cache = (item or {}).get("cache")
    if cache is None:
        cache = estrutura.get("cache")
    if cache is not False:
        return False
    idade = _numero((item or {}).get("idade_segundos"))
    if idade is None:
        idade = _numero(estrutura.get("idade_segundos"))
    return bool(
        idade is not None
        and 0 <= idade <= IDADE_ODD_MAXIMA_SEGUNDOS
    )


def _mesma_proveniencia(item, estrutura, fonte, bookmaker):
    fonte_item, bookmaker_item = _proveniencia(item, estrutura)
    return bool(
        fonte_item == _texto(fonte)
        and bookmaker_item == _texto(bookmaker)
    )


def _assinatura_cotacao(cotacao):
    if cotacao.get("tipo") == "tres_vias":
        return (
            "tres_vias",
            cotacao["selecao"],
            *(round(cotacao["odds"][chave], 9) for chave in (
                "casa", "visitante", "sem_gol"
            )),
        )
    return (
        "binaria",
        round(cotacao["linha"], 9),
        round(cotacao["over"], 9),
        round(cotacao["under"], 9),
    )


def _unica(cotacoes):
    unicas = {}
    for cotacao in cotacoes:
        unicas.setdefault(_assinatura_cotacao(cotacao), cotacao)
    return next(iter(unicas.values())) if len(unicas) == 1 else None


def _extrair_cotacao(
    estruturas, *, mercado, linha, fonte, bookmaker,
):
    if mercado not in MERCADOS_SUPORTADOS or not _texto(fonte):
        return None
    candidatas = []
    if mercado == "proximo_gol":
        selecao = _texto(linha)
        if selecao not in {"casa", "visitante"}:
            return None
        for estrutura in estruturas:
            if (
                _texto(estrutura.get("categoria")) != "gols"
                or _texto(estrutura.get("escopo")) != "proximo"
                or not _mesma_proveniencia(
                    {}, estrutura, fonte, bookmaker
                )
                or not _cotacao_fresca({}, estrutura)
            ):
                continue
            odds = {
                chave: _numero((estrutura.get("selecoes") or {}).get(chave))
                for chave in ("casa", "visitante", "sem_gol")
            }
            if any(valor is None or valor <= 1.0 for valor in odds.values()):
                continue
            candidatas.append({
                "tipo": "tres_vias",
                "selecao": selecao,
                "odds": odds,
                "odd": odds[selecao],
            })
        return _unica(candidatas)

    linha_numero = _numero(linha)
    if linha_numero is None:
        return None
    campo = "ofertas_ht" if mercado == "gol_ht" else "ofertas"
    categoria = "escanteios" if mercado in MERCADOS_ESCANTEIOS else "gols"
    for estrutura in estruturas:
        if _texto(estrutura.get("categoria")) != categoria:
            continue
        if mercado == "escanteios_ft_asiatico" and (
            _texto(estrutura.get("tipo_mercado")) != "asiatico"
        ):
            continue
        if mercado == "proximo_escanteio" and (
            _texto(estrutura.get("escopo") or "total") != "total"
        ):
            continue
        for oferta in estrutura.get(campo) or []:
            linha_oferta = _numero((oferta or {}).get("linha"))
            over = _numero((oferta or {}).get("over"))
            under = _numero((oferta or {}).get("under"))
            if (
                linha_oferta is None
                or not math.isclose(
                    linha_oferta, linha_numero, abs_tol=1e-9
                )
                or over is None or over <= 1.0
                or under is None or under <= 1.0
                or not _mesma_proveniencia(
                    oferta, estrutura, fonte, bookmaker
                )
                or not _cotacao_fresca(oferta, estrutura)
            ):
                continue
            candidatas.append({
                "tipo": "binaria",
                "linha": linha_numero,
                "over": over,
                "under": under,
                "odd": over,
            })
    return _unica(candidatas)


def _cotacao_entrada_congelada(features, sinal):
    """Valida a evidencia imutavel gravada no instante da decisao."""
    evidencia = features.get("cotacao_entrada_clv")
    if evidencia is None:
        return None
    if not isinstance(evidencia, dict):
        return False
    schema = evidencia.get("schema")
    if schema not in {VERSAO_COTACAO_ENTRADA_V1, VERSAO_COTACAO_ENTRADA}:
        return False
    if evidencia.get("mercado") != sinal.get("mercado"):
        return False
    if not _texto(evidencia.get("fonte")) or (
        _texto(evidencia.get("fonte"))
        != _texto(features.get("fonte_odds"))
    ):
        return False
    if (
        _texto(evidencia.get("bookmaker"))
        != _texto(features.get("bookmaker_odds"))
    ):
        return False
    acompanhamento = features.get("acompanhamento_odd_rapido")
    acompanhamento = acompanhamento if isinstance(acompanhamento, dict) else {}
    origem_esperada = (
        features.get("origem_mercado_odd")
        or acompanhamento.get("origem_mercado_odd")
    )
    assinatura_esperada = assinatura_origem_mercado(origem_esperada)
    if origem_esperada is not None and assinatura_esperada is None:
        return False
    if schema == VERSAO_COTACAO_ENTRADA_V1:
        if origem_esperada is not None:
            return False
    else:
        origem = normalizar_origem_mercado(evidencia.get("origem_mercado"))
        if (
            origem is None
            or origem["fonte"] != _texto(evidencia.get("fonte"))
            or origem["bookmaker"] != _texto(evidencia.get("bookmaker"))
            or (
                assinatura_esperada is not None
                and assinatura_origem_mercado(origem) != assinatura_esperada
            )
        ):
            return False
    if evidencia.get("cache") is not False:
        return False
    idade = _numero(evidencia.get("idade_segundos"))
    if idade is None or idade < 0 or idade > IDADE_ODD_MAXIMA_SEGUNDOS:
        return False

    coletado = evidencia.get("coletado_em")
    if coletado is not None:
        coletado_em = _data_utc(coletado)
        decisao_em = _data_utc(features.get("decisao_em")) or _data_utc(
            sinal.get("criado_em")
        )
        if coletado_em is None or decisao_em is None:
            return False
        diferenca = (decisao_em - coletado_em).total_seconds()
        if diferenca < -5 or diferenca > IDADE_ODD_MAXIMA_SEGUNDOS:
            return False

    odd_selecionada = _numero(evidencia.get("odd_selecionada"))
    odd_sinal = _numero(sinal.get("odd"))
    if (
        odd_selecionada is None or odd_selecionada <= 1.0
        or odd_sinal is None
        or not math.isclose(odd_selecionada, odd_sinal, abs_tol=1e-6)
    ):
        return False

    if sinal.get("mercado") == "proximo_gol":
        selecao = _texto(sinal.get("linha"))
        if (
            evidencia.get("tipo") != "tres_vias"
            or _texto(evidencia.get("selecao")) != selecao
            or selecao not in {"casa", "visitante"}
        ):
            return False
        odds = {
            chave: _numero((evidencia.get("odds") or {}).get(chave))
            for chave in ("casa", "visitante", "sem_gol")
        }
        if any(valor is None or valor <= 1.0 for valor in odds.values()):
            return False
        if not math.isclose(odds[selecao], odd_selecionada, abs_tol=1e-6):
            return False
        if schema == VERSAO_COTACAO_ENTRADA and (
            set(origem["lados"]) != {"casa", "visitante", "sem_gol"}
        ):
            return False
        return {
            "tipo": "tres_vias", "selecao": selecao,
            "odds": odds, "odd": odds[selecao], "schema": schema,
        }

    linha = _numero(sinal.get("linha"))
    linha_evidencia = _numero(evidencia.get("linha"))
    over = _numero(evidencia.get("over"))
    under = _numero(evidencia.get("under"))
    if (
        evidencia.get("tipo") != "binaria"
        or linha is None or linha_evidencia is None
        or not math.isclose(linha, linha_evidencia, abs_tol=1e-9)
        or over is None or over <= 1.0
        or under is None or under <= 1.0
        or not math.isclose(over, odd_selecionada, abs_tol=1e-6)
    ):
        return False
    if schema == VERSAO_COTACAO_ENTRADA and (
        set(origem["lados"]) != {"over", "under"}
        or _numero(origem["linha"]) is None
        or not math.isclose(
            _numero(origem["linha"]), linha, abs_tol=1e-9
        )
    ):
        return False
    return {
        "tipo": "binaria", "linha": linha,
        "over": over, "under": under, "odd": over, "schema": schema,
    }


def _probabilidade_sem_vig(cotacao):
    if cotacao.get("tipo") == "tres_vias":
        odds = cotacao["odds"]
        soma = sum(1.0 / odds[chave] for chave in (
            "casa", "visitante", "sem_gol"
        ))
        return (1.0 / odds[cotacao["selecao"]]) / soma
    over = cotacao["over"]
    under = cotacao["under"]
    return (1.0 / over) / ((1.0 / over) + (1.0 / under))


def _qualidade_margem(cotacao):
    if cotacao.get("tipo") == "tres_vias":
        odds = cotacao["odds"]
        valores = [odds[chave] for chave in (
            "casa", "visitante", "sem_gol"
        )]
    else:
        valores = [cotacao["over"], cotacao["under"]]
    return avaliar_margem_bookmaker(cotacao.get("tipo"), valores)


def _estruturas_snapshot(conexao, snapshot_id):
    estruturas = []
    for linha in conexao.execute(
        "SELECT estrutura_json FROM odds WHERE snapshot_id=?",
        (int(snapshot_id),),
    ).fetchall():
        estrutura = _json_objeto(linha["estrutura_json"])
        if estrutura:
            estruturas.append(estrutura)
    return estruturas


def _canal_entrada(canal):
    canal = str(canal or "")
    bloqueados = (
        "gateway:", ":resultado", ":green_antecipado",
        ":aguardar_odd", ":cancelamento", ":insuficiente",
        ":monitoramento_final", ":correcao",
    )
    return bool(canal and not any(item in canal for item in bloqueados))


def carregar_sinais_entregues(conexao):
    linhas = conexao.execute(
        """
        SELECT s.id,s.partida_id,s.snapshot_id,s.criado_em,s.mercado,
               s.linha,s.odd,s.regra_versao,s.features_json,
               snap.placar,snap.estatisticas_json,
               e.canal,COALESCE(e.entregue_em,e.tentado_em) AS entregue_em
        FROM sinais s
        JOIN snapshots snap ON snap.id=s.snapshot_id
        JOIN entregas_alertas e ON e.sinal_id=s.id
        WHERE e.status='entregue'
        ORDER BY s.id,datetime(COALESCE(e.entregue_em,e.tentado_em)),e.id
        """
    ).fetchall()
    primeiras = {}
    for linha in linhas:
        item = dict(linha)
        if not _canal_entrada(item.get("canal")):
            continue
        if item.get("mercado") not in MERCADOS_SUPORTADOS:
            continue
        primeiras.setdefault(int(item["id"]), item)
    return list(primeiras.values())


def _snapshots_futuros(conexao, sinal):
    entrega = _data(sinal.get("entregue_em")) or _data(
        sinal.get("criado_em")
    )
    if entrega is None:
        return [], None
    inicio = entrega
    fim = entrega + timedelta(seconds=HORIZONTE_MAXIMO_SEGUNDOS)
    colunas_snapshot = {
        str(linha[1])
        for linha in conexao.execute("PRAGMA table_info(snapshots)").fetchall()
    }
    status_sql = "status" if "status" in colunas_snapshot else "NULL AS status"
    linhas = conexao.execute(
        f"""
        SELECT id,coletado_em,placar,{status_sql},estatisticas_json
        FROM snapshots
        WHERE partida_id=?
          AND datetime(coletado_em)>datetime(?)
          AND datetime(coletado_em)<=datetime(?)
        ORDER BY datetime(coletado_em),id
        """,
        (sinal["partida_id"], inicio.isoformat(), fim.isoformat()),
    ).fetchall()
    return [dict(linha) for linha in linhas], entrega


def _cotacao_observacao_rapida(payload, sinal):
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != VERSAO_EVIDENCIA_OFERTA_RAPIDA:
        return None
    if payload.get("sinal_origem_id") != int(sinal["id"]):
        return None
    if payload.get("mercado") != sinal.get("mercado"):
        return None
    if not linha_equivalente(
        sinal.get("mercado"), payload.get("linha"), sinal.get("linha")
    ):
        return None
    if _texto(payload.get("fonte")) != _texto(
        _json_objeto(sinal.get("features_json")).get("fonte_odds")
    ):
        return None
    if _texto(payload.get("bookmaker")) != _texto(
        _json_objeto(sinal.get("features_json")).get("bookmaker_odds")
    ):
        return None
    contrato = validar_contrato_mercado_oferta(
        payload, sinal.get("mercado"), sinal.get("linha"),
        exigir_origem=True,
    )
    if contrato.get("valido") is not True:
        return None
    odd = _numero(payload.get("odd"))
    if odd is None or odd <= 1.0:
        return None
    if sinal.get("mercado") == "proximo_gol":
        odds = payload.get("odds_mercado_sincronizadas") or {}
        if not all(_numero(odds.get(chave)) for chave in (
            "casa", "visitante", "sem_gol"
        )):
            return None
        return {
            "tipo": "tres_vias",
            "selecao": _texto(sinal.get("linha")),
            "odds": {chave: float(odds[chave]) for chave in (
                "casa", "visitante", "sem_gol"
            )},
            "odd": odd,
        }
    oposta = _numero(payload.get("odd_oposta"))
    linha = _numero(sinal.get("linha"))
    if oposta is None or oposta <= 1.0 or linha is None:
        return None
    return {
        "tipo": "binaria",
        "linha": linha,
        "over": odd,
        "under": oposta,
        "odd": odd,
    }


def _observacoes_clv_futuras(conexao, sinal, entrega):
    if entrega is None:
        return []
    if not conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='observacoes_fontes_odds'"
    ).fetchone():
        return []
    linhas = conexao.execute(
        """
        SELECT estado.id AS observacao_id, estado.consultado_em,
               estado.oferta_json AS estado_json,
               estado.evidencia_sha256 AS estado_sha256,
               oferta.id AS oferta_observacao_id,
               oferta.oferta_json AS oferta_json,
               oferta.evidencia_sha256 AS oferta_sha256
        FROM observacoes_fontes_odds estado
        LEFT JOIN observacoes_fontes_odds oferta
          ON oferta.id=CAST(json_extract(
                estado.oferta_json, '$.oferta_observacao_id'
             ) AS INTEGER)
         AND oferta.estado='oferta_monitorada'
        WHERE estado.estado=?
          AND estado.evidencia_referencia=?
          AND datetime(estado.consultado_em)>datetime(?)
          AND datetime(estado.consultado_em)<=datetime(?, '+10 minutes')
        ORDER BY datetime(estado.consultado_em),estado.id
        """,
        (
            ESTADO_OBSERVACAO_CLV, referencia_clv(sinal["id"]),
            entrega.isoformat(), entrega.isoformat(),
        ),
    ).fetchall()
    futuros = []
    for linha in linhas:
        item = dict(linha)
        estado_json = item.get("estado_json")
        if (
            hashlib.sha256(str(estado_json).encode("utf-8")).hexdigest()
            != str(item.get("estado_sha256") or "")
        ):
            continue
        estado = _json_objeto(estado_json)
        if (
            estado.get("schema") not in {
                VERSAO_EVIDENCIA_ESTADO_CLV_V1,
                VERSAO_EVIDENCIA_ESTADO_CLV_V2,
                VERSAO_EVIDENCIA_ESTADO_CLV,
            }
            or estado.get("sinal_id") != int(sinal["id"])
            or estado.get("partida_id") != int(sinal["partida_id"])
            or estado.get("mercado") != sinal.get("mercado")
            or not linha_equivalente(
                sinal.get("mercado"), estado.get("linha"),
                sinal.get("linha"),
            )
            or estado.get("aplicacao_sinais") is not False
            or estado.get("telegram") is not False
        ):
            continue
        instante = _data(item.get("consultado_em"))
        if instante is None:
            continue
        decorrido = (instante - entrega).total_seconds()
        if not (
            HORIZONTE_MINIMO_SEGUNDOS
            <= decorrido <= HORIZONTE_MAXIMO_SEGUNDOS
        ):
            continue
        cotacao = None
        oferta_json = item.get("oferta_json")
        if oferta_json is not None and (
            hashlib.sha256(str(oferta_json).encode("utf-8")).hexdigest()
            == str(item.get("oferta_sha256") or "")
        ):
            cotacao = _cotacao_observacao_rapida(
                _json_objeto(oferta_json), sinal
            )
        escanteios = normalizar_escanteios_estado(
            estado.get("escanteios")
        )
        estatisticas_json = "{}"
        if isinstance(escanteios, dict):
            estatisticas_json = json.dumps({
                "Escanteios": (
                    f"{escanteios['mandante']}-{escanteios['visitante']}"
                ),
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        futuros.append({
            "observacao_id": int(item["observacao_id"]),
            "coletado_em": item.get("consultado_em"),
            "placar": estado.get("placar"),
            "status": estado.get("status_codigo"),
            "estatisticas_json": estatisticas_json,
            "cotacao": cotacao,
            "origem_evento": "api_rapida_clv",
        })
    return futuros


def _resultado_comparavel(
    base, *, snapshot_id=None, observacao_id=None, decorrido,
    odd_entrada, prob_entrada,
    valor_horizonte, origem, odd_futura=None,
    margem_bookmaker_futura=None,
):
    variacao = valor_horizonte - prob_entrada
    return {
        **base,
        "estado": "comparavel",
        "motivo": None,
        "origem_valor_horizonte": origem,
        "snapshot_futuro_id": (
            int(snapshot_id) if snapshot_id is not None else None
        ),
        "observacao_clv_id": (
            int(observacao_id) if observacao_id is not None else None
        ),
        "origem_medicao_horizonte": (
            "api_rapida_clv" if observacao_id is not None else "snapshot"
        ),
        "segundos_apos_entrega": round(decorrido, 3),
        "odd_entrada": round(odd_entrada, 6),
        "odd_futura": (
            round(float(odd_futura), 6) if odd_futura is not None else None
        ),
        "margem_bookmaker_futura": margem_bookmaker_futura,
        "probabilidade_sem_vig_entrada": round(prob_entrada, 6),
        "valor_probabilidade_horizonte": round(valor_horizonte, 6),
        # O nome CLV e mantido para consumo analitico, mas na V2 o valor
        # inclui liquidacoes. Ele representa o residuo mark-to-market.
        "clv_probabilidade_pontos": round(variacao, 6),
        "clv_probabilidade_relativo": round(
            valor_horizonte / prob_entrada - 1.0, 6
        ),
        "movimento_odd_relativo": (
            round(odd_entrada / float(odd_futura) - 1.0, 6)
            if odd_futura is not None else None
        ),
        "movimento_favoravel": variacao > 0,
    }


def avaliar_sinal(conexao, sinal):
    item = dict(sinal)
    features = _json_objeto(item.get("features_json"))
    fonte = features.get("fonte_odds")
    bookmaker = features.get("bookmaker_odds")
    base = {
        "sinal_id": int(item["id"]),
        "partida_id": int(item["partida_id"]),
        "criado_em": item.get("criado_em"),
        "entregue_em": item.get("entregue_em"),
        "mercado": item.get("mercado"),
        "regra_versao": item.get("regra_versao"),
        "fonte": _texto(fonte) or None,
        "bookmaker": _texto(bookmaker) or None,
        "estado_cotacao_entrada": features.get(
            CHAVE_ESTADO_COTACAO_ENTRADA
        ),
        "canal_teste": str(item.get("canal") or "").endswith(":teste"),
    }
    if item.get("mercado") not in MERCADOS_SUPORTADOS:
        return {**base, "estado": "excluido", "motivo": "mercado_nao_suportado"}
    if not _texto(fonte):
        return {**base, "estado": "excluido", "motivo": "proveniencia_entrada_ausente"}
    if item.get("mercado") != "proximo_gol":
        linha_binaria = _numero(item.get("linha"))
        if (
            linha_binaria is None
            or not math.isclose(
                linha_binaria % 1.0, 0.5, abs_tol=1e-9
            )
        ):
            return {
                **base, "estado": "excluido",
                "motivo": "linha_nao_binaria_sem_liquidacao_1_0",
            }
    cotacao_entrada = _cotacao_entrada_congelada(features, item)
    if cotacao_entrada is False:
        evidencia = features.get("cotacao_entrada_clv")
        schema = evidencia.get("schema") if isinstance(evidencia, dict) else None
        sufixo = "v2" if schema == VERSAO_COTACAO_ENTRADA else "v1"
        return {
            **base, "estado": "excluido",
            "motivo": "cotacao_entrada_congelada_invalida",
            "origem_cotacao_entrada": f"congelada_{sufixo}_invalida",
        }
    if cotacao_entrada is None:
        cotacao_entrada = _extrair_cotacao(
            _estruturas_snapshot(conexao, item["snapshot_id"]),
            mercado=item["mercado"], linha=item.get("linha"),
            fonte=fonte, bookmaker=bookmaker,
        )
        origem_cotacao_entrada = "snapshot_legado"
    else:
        origem_cotacao_entrada = (
            "congelada_v2"
            if cotacao_entrada.get("schema") == VERSAO_COTACAO_ENTRADA
            else "congelada_v1"
        )
    base["origem_cotacao_entrada"] = origem_cotacao_entrada
    odd_entrada = _numero(item.get("odd"))
    if cotacao_entrada is None:
        return {**base, "estado": "excluido", "motivo": "cotacao_entrada_exata_ausente_ou_ambigua"}
    if odd_entrada is None or not math.isclose(
        odd_entrada, cotacao_entrada["odd"], abs_tol=1e-6
    ):
        return {**base, "estado": "excluido", "motivo": "odd_entrada_divergente"}
    qualidade_margem_entrada = _qualidade_margem(cotacao_entrada)
    base["margem_bookmaker_entrada"] = qualidade_margem_entrada.get(
        "margem_bookmaker"
    )
    if not qualidade_margem_entrada.get("plausivel"):
        return {
            **base, "estado": "excluido",
            "motivo": "cotacao_entrada_margem_incoerente",
        }

    futuros_snapshot, entrega = _snapshots_futuros(conexao, item)
    if entrega is None:
        return {**base, "estado": "excluido", "motivo": "instante_entrega_invalido"}
    futuros = [
        {**futuro, "origem_evento": "snapshot"}
        for futuro in futuros_snapshot
    ]
    futuros.extend(_observacoes_clv_futuras(conexao, item, entrega))
    futuros.sort(key=lambda futuro: (
        _data(futuro.get("coletado_em")) or datetime.max,
        0 if futuro.get("origem_evento") == "api_rapida_clv" else 1,
        int(futuro.get("observacao_id") or futuro.get("id") or 0),
    ))
    placar_entrada = _par(item.get("placar"))
    cantos_entrada = _par_escanteios(item.get("estatisticas_json"))
    if placar_entrada is None:
        return {**base, "estado": "excluido", "motivo": "placar_entrada_invalido"}
    if item["mercado"] in MERCADOS_ESCANTEIOS and cantos_entrada is None:
        return {**base, "estado": "excluido", "motivo": "escanteios_entrada_invalidos"}

    prob_entrada = _probabilidade_sem_vig(cotacao_entrada)
    linha_numero = _numero(item.get("linha"))
    teve_evento_no_horizonte = False
    estado_alterado = False
    cotacao_futura_incoerente = False
    for futuro in futuros:
        instante = _data(futuro.get("coletado_em"))
        if instante is None:
            continue
        decorrido = (instante - entrega).total_seconds()
        placar_futuro = _par(futuro.get("placar"))
        cantos_futuro = _par_escanteios(futuro.get("estatisticas_json"))
        identificador_resultado = {
            "snapshot_id": futuro.get("id"),
            "observacao_id": futuro.get("observacao_id"),
        }

        if placar_futuro is not None and placar_futuro != placar_entrada:
            estado_alterado = True
            if item["mercado"] == "proximo_gol":
                diferencas = tuple(
                    placar_futuro[indice] - placar_entrada[indice]
                    for indice in (0, 1)
                )
                if sum(diferencas) != 1 or min(diferencas) < 0:
                    return {
                        **base, "estado": "nao_comparavel",
                        "motivo": "resultado_proximo_gol_ambiguo",
                    }
                lado = "casa" if diferencas[0] == 1 else "visitante"
                valor = 1.0 if lado == _texto(item.get("linha")) else 0.0
                return _resultado_comparavel(
                    base, **identificador_resultado, decorrido=decorrido,
                    odd_entrada=odd_entrada, prob_entrada=prob_entrada,
                    valor_horizonte=valor,
                    origem=(
                        "liquidado_green" if valor == 1.0
                        else "liquidado_red"
                    ),
                )
            if (
                item["mercado"] in {"gol_ft", "gol_ht"}
                and linha_numero is not None
                and sum(placar_futuro) > linha_numero
            ):
                return _resultado_comparavel(
                    base, **identificador_resultado, decorrido=decorrido,
                    odd_entrada=odd_entrada, prob_entrada=prob_entrada,
                    valor_horizonte=1.0, origem="liquidado_green",
                )

        if (
            item["mercado"] in MERCADOS_ESCANTEIOS
            and cantos_futuro is not None
            and cantos_futuro != cantos_entrada
        ):
            estado_alterado = True
            if linha_numero is not None and sum(cantos_futuro) > linha_numero:
                return _resultado_comparavel(
                    base, **identificador_resultado, decorrido=decorrido,
                    odd_entrada=odd_entrada, prob_entrada=prob_entrada,
                    valor_horizonte=1.0, origem="liquidado_green",
                )

        status_futuro = status_normalizado(futuro.get("status"))
        if status_futuro in STATUS_ANULADO:
            return {
                **base,
                "estado": "nao_comparavel",
                "motivo": "mercado_anulado_antes_horizonte",
            }
        if mercado_encerrado(item["mercado"], status_futuro):
            if item["mercado"] == "proximo_gol":
                valor_terminal = (
                    1.0 if _texto(item.get("linha")) == "sem_gol" else 0.0
                )
            elif (
                item["mercado"] in {"gol_ft", "gol_ht"}
                and placar_futuro is not None
                and linha_numero is not None
            ):
                valor_terminal = (
                    1.0 if sum(placar_futuro) > linha_numero else 0.0
                )
            elif (
                item["mercado"] in MERCADOS_ESCANTEIOS
                and cantos_futuro is not None
                and linha_numero is not None
            ):
                valor_terminal = (
                    1.0 if sum(cantos_futuro) > linha_numero else 0.0
                )
            else:
                valor_terminal = None
            if valor_terminal is not None:
                return _resultado_comparavel(
                    base,
                    **identificador_resultado,
                    decorrido=decorrido,
                    odd_entrada=odd_entrada,
                    prob_entrada=prob_entrada,
                    valor_horizonte=valor_terminal,
                    origem=(
                        "liquidado_green" if valor_terminal == 1.0
                        else "liquidado_red"
                    ),
                )

        if decorrido < HORIZONTE_MINIMO_SEGUNDOS:
            continue
        teve_evento_no_horizonte = True
        if futuro.get("origem_evento") == "api_rapida_clv":
            cotacao_futura = futuro.get("cotacao")
        else:
            cotacao_futura = _extrair_cotacao(
                _estruturas_snapshot(conexao, futuro["id"]),
                mercado=item["mercado"], linha=item.get("linha"),
                fonte=fonte, bookmaker=bookmaker,
            )
        if cotacao_futura is None:
            continue
        qualidade_margem_futura = _qualidade_margem(cotacao_futura)
        if not qualidade_margem_futura.get("plausivel"):
            cotacao_futura_incoerente = True
            continue
        prob_futura = _probabilidade_sem_vig(cotacao_futura)
        return _resultado_comparavel(
            base, **identificador_resultado, decorrido=decorrido,
            odd_entrada=odd_entrada, prob_entrada=prob_entrada,
            valor_horizonte=prob_futura, origem="cotacao_sem_vig",
            odd_futura=cotacao_futura["odd"],
            margem_bookmaker_futura=qualidade_margem_futura.get(
                "margem_bookmaker"
            ),
        )
    if not futuros:
        motivo = "sem_snapshot_futuro"
    elif teve_evento_no_horizonte:
        motivo = (
            "cotacao_futura_margem_incoerente"
            if cotacao_futura_incoerente
            else "cotacao_futura_exata_ausente"
        )
    elif estado_alterado:
        motivo = "estado_alterado_sem_liquidacao_modelavel"
    else:
        motivo = "sem_snapshot_apos_horizonte_minimo"
    return {**base, "estado": "nao_comparavel", "motivo": motivo}


def _metricas(itens, natureza="mark_to_market"):
    itens = [item for item in itens if item.get("estado") == "comparavel"]
    valores = [float(item["clv_probabilidade_pontos"]) for item in itens]
    origens = {}
    for item in itens:
        origem = str(item.get("origem_valor_horizonte") or "desconhecida")
        origens[origem] = origens.get(origem, 0) + 1
    horizontes = [
        float(item["segundos_apos_entrega"])
        for item in itens if item.get("segundos_apos_entrega") is not None
    ]
    condicionada_sobrevivencia = natureza == (
        "movimento_preco_condicionado_sobrevivencia"
    )
    correlacionada_intrajogo = "correlacionado" in natureza
    nao_decisoria = bool(
        condicionada_sobrevivencia or correlacionada_intrajogo
    )
    if not valores:
        return {
            "amostra": 0,
            "media_pontos_probabilidade": None,
            "mediana_pontos_probabilidade": None,
            "proporcao_movimento_favoravel": None,
            "intervalo_media_95": None,
            "estado_evidencia": "amostra_insuficiente",
            "evidencia_valor_favoravel": False,
            "evidencia_valor_desfavoravel": False,
            "amostra_minima_evidencia": AMOSTRA_MINIMA_EVIDENCIA,
            "natureza_evidencia": natureza,
            "vies_selecao_sobrevivencia": condicionada_sobrevivencia,
            "vies_correlacao_intrajogo": correlacionada_intrajogo,
            "pode_informar_edge": False,
            "pode_decidir_edge": False,
            "origens_valor_horizonte": {},
            "mediana_segundos_apos_entrega": None,
        }
    media = statistics.fmean(valores)
    intervalo = None
    if len(valores) >= 2:
        erro = statistics.stdev(valores) / math.sqrt(len(valores))
        graus_liberdade = len(valores) - 1
        critico = CRITICOS_T_975.get(graus_liberdade, 1.96)
        intervalo = [
            round(media - critico * erro, 6),
            round(media + critico * erro, 6),
        ]
    favoravel = bool(
        not nao_decisoria
        and len(valores) >= AMOSTRA_MINIMA_EVIDENCIA
        and intervalo is not None and intervalo[0] > 0
    )
    desfavoravel = bool(
        not nao_decisoria
        and len(valores) >= AMOSTRA_MINIMA_EVIDENCIA
        and intervalo is not None and intervalo[1] < 0
    )
    amostra_suficiente = bool(
        len(valores) >= AMOSTRA_MINIMA_EVIDENCIA
        and intervalo is not None
    )
    return {
        "amostra": len(valores),
        "media_pontos_probabilidade": round(media, 6),
        "mediana_pontos_probabilidade": round(statistics.median(valores), 6),
        "proporcao_movimento_favoravel": round(
            sum(valor > 0 for valor in valores) / len(valores), 6
        ),
        "proporcao_valor_favoravel": round(
            sum(valor > 0 for valor in valores) / len(valores), 6
        ),
        "intervalo_media_95": intervalo,
        "estado_evidencia": (
            "diagnostico_condicionado_a_sobrevivencia"
            if condicionada_sobrevivencia else
            "diagnostico_correlacionado_intrajogo"
            if correlacionada_intrajogo else
            f"{natureza}_favoravel_com_ic95_positivo"
            if favoravel else
            f"{natureza}_desfavoravel_com_ic95_negativo"
            if desfavoravel else
            "inconclusivo"
            if len(valores) >= AMOSTRA_MINIMA_EVIDENCIA else
            "amostra_insuficiente"
        ),
        "evidencia_valor_favoravel": favoravel,
        "evidencia_valor_desfavoravel": desfavoravel,
        "amostra_minima_evidencia": AMOSTRA_MINIMA_EVIDENCIA,
        "natureza_evidencia": natureza,
        "vies_selecao_sobrevivencia": condicionada_sobrevivencia,
        "vies_correlacao_intrajogo": correlacionada_intrajogo,
        "pode_informar_edge": bool(
            not nao_decisoria and amostra_suficiente
        ),
        "pode_decidir_edge": False,
        "origens_valor_horizonte": origens,
        "mediana_segundos_apos_entrega": round(
            statistics.median(horizontes), 3
        ) if horizontes else None,
    }


def _resumo_cobertura(itens, natureza_principal="mark_to_market"):
    """Separa ausencia de evidencia de evidencia desfavoravel."""
    itens = list(itens)
    comparaveis = [item for item in itens if item.get("estado") == "comparavel"]
    exclusoes = {}
    origens_cotacao_entrada = {}
    for item in itens:
        motivo = item.get("motivo")
        if motivo:
            exclusoes[motivo] = exclusoes.get(motivo, 0) + 1
        origem = item.get("origem_cotacao_entrada")
        if origem:
            origens_cotacao_entrada[origem] = (
                origens_cotacao_entrada.get(origem, 0) + 1
            )
    taxa_cobertura = (
        len(comparaveis) / len(itens) if itens else None
    )
    cobertura_suficiente = bool(
        taxa_cobertura is not None
        and taxa_cobertura >= COBERTURA_MINIMA_INFORMAR_EDGE
    )
    metricas = _metricas(comparaveis, natureza=natureza_principal)
    if natureza_principal == "mark_to_market":
        metricas["pode_informar_edge"] = bool(
            metricas.get("pode_informar_edge")
            and cobertura_suficiente
        )
        if (
            len(comparaveis) >= AMOSTRA_MINIMA_EVIDENCIA
            and not cobertura_suficiente
        ):
            metricas.update({
                "estado_evidencia": (
                    "cobertura_insuficiente_para_informar_edge"
                ),
                "evidencia_valor_favoravel": False,
                "evidencia_valor_desfavoravel": False,
            })
    movimento_preco = _metricas(
        [
            item for item in comparaveis
            if item.get("origem_valor_horizonte") == "cotacao_sem_vig"
        ],
        natureza="movimento_preco_condicionado_sobrevivencia",
    )
    return {
        "entregas_consultadas": len(itens),
        "comparaveis": len(comparaveis),
        "taxa_cobertura": (
            round(taxa_cobertura, 6)
            if taxa_cobertura is not None else None
        ),
        "cobertura_minima_informar_edge": (
            COBERTURA_MINIMA_INFORMAR_EDGE
        ),
        "cobertura_suficiente_para_informar_edge": cobertura_suficiente,
        "exclusoes": exclusoes,
        "origens_cotacao_entrada": origens_cotacao_entrada,
        **metricas,
        "movimento_preco_contratos_sobreviventes": movimento_preco,
    }


def _marcar_diagnostico_nao_inferencial(resumo, motivo):
    """Impede um recorte exploratorio de ser apresentado como prova de edge."""
    saida = dict(resumo or {})
    saida["estado_evidencia_observado"] = saida.get("estado_evidencia")
    saida["evidencia_valor_favoravel_observada"] = bool(
        saida.get("evidencia_valor_favoravel")
    )
    saida["evidencia_valor_desfavoravel_observada"] = bool(
        saida.get("evidencia_valor_desfavoravel")
    )
    saida["escopo_inferencial"] = "diagnostico"
    saida["motivo_nao_inferencial"] = str(motivo)
    saida["estado_evidencia"] = "diagnostico_nao_pre_registrado"
    saida["evidencia_valor_favoravel"] = False
    saida["evidencia_valor_desfavoravel"] = False
    saida["pode_informar_edge"] = False
    saida["pode_decidir_edge"] = False
    return saida


def _resumo_cotacao_entrada_prospectiva(itens):
    """Mede o contrato de entrada novo sem dilui-lo no legado.

    A presenca de ``cotacao_entrada_clv_estado`` e definida no instante da
    decisao, antes de qualquer resultado ou preco futuro. Assim, somente as
    entregas produzidas pelo pipeline novo formam o denominador prospectivo;
    registros antigos continuam visiveis, mas nao podem esconder uma falha da
    instrumentacao atual nem tornar sua cobertura artificialmente melhor.
    """
    itens = list(itens)
    prospectivos = [
        item for item in itens
        if item.get("estado_cotacao_entrada") is not None
    ]
    estados = {}
    falhas = {}
    origens_validas = {"congelada_v1", "congelada_v2"}
    for item in prospectivos:
        estado = str(item.get("estado_cotacao_entrada") or "desconhecido")
        estados[estado] = estados.get(estado, 0) + 1
        origem = item.get("origem_cotacao_entrada")
        if origem in {"congelada_v1_invalida", "congelada_v2_invalida"}:
            motivo = "cotacao_congelada_invalida"
        elif origem not in origens_validas:
            motivo = estado
        else:
            motivo = None
        if motivo:
            falhas[motivo] = falhas.get(motivo, 0) + 1
    congeladas_validas = [
        item for item in prospectivos
        if item.get("origem_cotacao_entrada") in origens_validas
    ]
    comparaveis = [
        item for item in prospectivos
        if item.get("estado") == "comparavel"
    ]
    total = len(prospectivos)
    taxa = len(congeladas_validas) / total if total else None
    amostra_suficiente = total >= AMOSTRA_MINIMA_EVIDENCIA
    cobertura_suficiente = bool(
        amostra_suficiente
        and taxa is not None
        and taxa >= COBERTURA_MINIMA_INFORMAR_EDGE
    )
    if not total:
        estado = "aguardando_primeiras_entregas_instrumentadas"
    elif not amostra_suficiente:
        estado = "formando_coorte_prospectiva"
    elif cobertura_suficiente:
        estado = "cobertura_cotacao_entrada_suficiente"
    else:
        estado = "cobertura_cotacao_entrada_insuficiente"
    return {
        "versao": VERSAO_COBERTURA_COTACAO_PROSPECTIVA,
        "criterio_coorte": "estado_persistido_antes_do_resultado",
        "selecao_antes_da_comparabilidade": True,
        "entregas_legadas_fora_do_denominador": len(itens) - total,
        "entregas_instrumentadas": total,
        "cotacoes_congeladas_validas": len(congeladas_validas),
        "cotacoes_congeladas_invalidas": int(
            falhas.get("cotacao_congelada_invalida", 0)
        ),
        "comparaveis_apos_horizonte": len(comparaveis),
        "taxa_cobertura_cotacao_entrada": (
            round(taxa, 6) if taxa is not None else None
        ),
        "cobertura_minima": COBERTURA_MINIMA_INFORMAR_EDGE,
        "amostra_minima": AMOSTRA_MINIMA_EVIDENCIA,
        "amostra_suficiente": amostra_suficiente,
        "cobertura_suficiente": cobertura_suficiente,
        "estado": estado,
        "estados_persistidos": estados,
        "falhas": falhas,
        "pode_informar_edge": False,
        "pode_decidir_edge": False,
        "gate_operacional": False,
        "promocao_automatica": False,
    }


def _resumo_coorte_clv_prospectiva(itens, cadeia_custodia):
    """Congela desenvolvimento/holdout antes de observar o desfecho.

    A divisao percentual movel fazia unidades antigas migrarem do holdout para
    desenvolvimento conforme novas entregas chegavam. A coorte V1 considera
    apenas entradas produzidas pela instrumentacao nova, fixa as primeiras 120
    partidas e separa antecipadamente 84/36. Excedentes permanecem visiveis,
    mas nao alteram essa conclusao.
    """
    prospectivos = [
        item for item in _ordenar_entregas(itens)
        if item.get("estado_cotacao_entrada") is not None
    ]
    coorte = prospectivos[:TAMANHO_COORTE_CLV_PROSPECTIVA]
    desenvolvimento = coorte[:TAMANHO_DESENVOLVIMENTO_CLV]
    holdout = coorte[
        TAMANHO_DESENVOLVIMENTO_CLV:
        TAMANHO_COORTE_CLV_PROSPECTIVA
    ]
    resumo_cotacao = _resumo_cotacao_entrada_prospectiva(coorte)
    resumo_desenvolvimento = _resumo_cobertura(desenvolvimento)
    resumo_holdout = _resumo_cobertura(holdout)
    ids = [int(item["sinal_id"]) for item in coorte]
    fingerprint = hashlib.sha256(
        json.dumps(ids, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    completa = len(coorte) == TAMANHO_COORTE_CLV_PROSPECTIVA
    cobertura_cotacao = bool(
        completa and resumo_cotacao.get("cobertura_suficiente")
    )
    cobertura_horizonte = bool(
        completa
        and resumo_desenvolvimento.get(
            "cobertura_suficiente_para_informar_edge"
        )
        and resumo_holdout.get(
            "cobertura_suficiente_para_informar_edge"
        )
        and int(resumo_desenvolvimento.get("comparaveis") or 0)
            >= AMOSTRA_MINIMA_EVIDENCIA
        and int(resumo_holdout.get("comparaveis") or 0)
            >= AMOSTRA_MINIMA_EVIDENCIA
    )
    cadeia_custodia = dict(cadeia_custodia or {})
    custodia_saudavel = cadeia_custodia.get("saudavel") is True
    pronta_estatisticamente = bool(
        cobertura_cotacao and cobertura_horizonte
    )
    pronta = bool(pronta_estatisticamente and custodia_saudavel)
    vantagem_replicada = bool(
        pronta
        and resumo_desenvolvimento.get("evidencia_valor_favoravel")
        and resumo_holdout.get("evidencia_valor_favoravel")
    )
    desvantagem_replicada = bool(
        pronta
        and resumo_desenvolvimento.get("evidencia_valor_desfavoravel")
        and resumo_holdout.get("evidencia_valor_desfavoravel")
    )
    if not completa:
        estado = "formando_coorte_fixa"
    elif not custodia_saudavel:
        estado = "cadeia_custodia_invalida"
    elif not cobertura_cotacao:
        estado = "cotacao_entrada_insuficiente"
    elif not cobertura_horizonte:
        estado = "cobertura_horizonte_insuficiente"
    elif vantagem_replicada:
        estado = "vantagem_replicada_para_revisao_manual"
    elif desvantagem_replicada:
        estado = "desvantagem_replicada"
    else:
        estado = "efeito_nao_replicado_ou_inconclusivo"
    return {
        "versao": VERSAO_COORTE_CLV_PROSPECTIVA,
        "criterio_coorte": (
            "primeiras_120_partidas_instrumentadas_antes_da_comparabilidade"
        ),
        "selecao_antes_do_resultado": True,
        "divisao_fixa": True,
        "tamanho_planejado": TAMANHO_COORTE_CLV_PROSPECTIVA,
        "tamanho_desenvolvimento": TAMANHO_DESENVOLVIMENTO_CLV,
        "tamanho_holdout": TAMANHO_HOLDOUT_CLV,
        "unidades_coorte": len(coorte),
        "unidades_faltantes": max(
            TAMANHO_COORTE_CLV_PROSPECTIVA - len(coorte), 0
        ),
        "unidades_excedentes_fora_coorte": max(
            len(prospectivos) - TAMANHO_COORTE_CLV_PROSPECTIVA, 0
        ),
        "primeiro_sinal_id": ids[0] if ids else None,
        "ultimo_sinal_id": ids[-1] if ids else None,
        "fingerprint_ids": fingerprint,
        "coorte_completa": completa,
        "cobertura_cotacao_entrada_suficiente": cobertura_cotacao,
        "cobertura_horizonte_suficiente": cobertura_horizonte,
        "pronta_estatisticamente": pronta_estatisticamente,
        "cadeia_custodia_saudavel": custodia_saudavel,
        "pronta_para_conclusao": pronta,
        "vantagem_replicada": vantagem_replicada,
        "desvantagem_replicada": desvantagem_replicada,
        "estado": estado,
        "cotacao_entrada": resumo_cotacao,
        "desenvolvimento": _marcar_diagnostico_nao_inferencial(
            resumo_desenvolvimento, "particao_isolada_da_coorte_fixa"
        ),
        "holdout": _marcar_diagnostico_nao_inferencial(
            resumo_holdout, "particao_isolada_da_coorte_fixa"
        ),
        "pode_informar_edge": pronta,
        "pode_decidir_edge": False,
        "gate_operacional": False,
        "promocao_automatica": False,
    }


def _ordenar_entregas(itens):
    return sorted(
        itens,
        key=lambda item: (
            _data(item.get("entregue_em"))
            or _data(item.get("criado_em"))
            or datetime.min,
            item["sinal_id"],
        ),
    )


def _primeiros_independentes(itens, chave):
    primeiros = {}
    for item in _ordenar_entregas(itens):
        primeiros.setdefault(chave(item), item)
    return list(primeiros.values())


def avaliar(conexao):
    cadeia_custodia = auditar_cadeia_custodia_clv(conexao)
    sinais = carregar_sinais_entregues(conexao)
    itens_brutos = [avaliar_sinal(conexao, sinal) for sinal in sinais]
    itens_partida_mercado = _primeiros_independentes(
        itens_brutos,
        lambda item: (item["partida_id"], item["mercado"]),
    )
    # A unidade primaria precisa ser independente tambem entre mercados. Um
    # mesmo gol pode liquidar varios contratos da partida e nao pode estreitar
    # o IC95 como se fossem jogos diferentes. A escolha ocorre antes do filtro
    # de comparabilidade para que uma cotacao ausente nao selecione, a
    # posteriori, outro contrato mais conveniente da mesma partida.
    itens = _primeiros_independentes(
        itens_partida_mercado,
        lambda item: item["partida_id"],
    )
    comparaveis = [item for item in itens if item["estado"] == "comparavel"]
    ordenados = _ordenar_entregas(comparaveis)
    cotacoes_abertas = [
        item for item in ordenados
        if item.get("origem_valor_horizonte") == "cotacao_sem_vig"
    ]
    entregas_ordenadas = _ordenar_entregas(itens)
    coorte_clv_prospectiva = _resumo_coorte_clv_prospectiva(
        entregas_ordenadas, cadeia_custodia
    )
    prospectivos_ordenados = [
        item for item in entregas_ordenadas
        if item.get("estado_cotacao_entrada") is not None
    ][:TAMANHO_COORTE_CLV_PROSPECTIVA]
    desenvolvimento = prospectivos_ordenados[
        :TAMANHO_DESENVOLVIMENTO_CLV
    ]
    holdout = prospectivos_ordenados[
        TAMANHO_DESENVOLVIMENTO_CLV:
        TAMANHO_COORTE_CLV_PROSPECTIVA
    ]
    comparaveis_desenvolvimento = [
        item for item in desenvolvimento
        if item.get("estado") == "comparavel"
    ]
    comparaveis_holdout = [
        item for item in holdout if item.get("estado") == "comparavel"
    ]
    cotacoes_desenvolvimento = [
        item for item in comparaveis_desenvolvimento
        if item.get("origem_valor_horizonte") == "cotacao_sem_vig"
    ]
    cotacoes_holdout = [
        item for item in comparaveis_holdout
        if item.get("origem_valor_horizonte") == "cotacao_sem_vig"
    ]
    resumo_total = _marcar_diagnostico_nao_inferencial(
        _resumo_cobertura(entregas_ordenadas),
        "historico_e_coorte_futura_misturados",
    )
    resumo_desenvolvimento = _marcar_diagnostico_nao_inferencial(
        _resumo_cobertura(desenvolvimento),
        "desenvolvimento_isolado_nao_confirma_edge",
    )
    resumo_holdout = _marcar_diagnostico_nao_inferencial(
        _resumo_cobertura(holdout),
        "holdout_isolado_sem_replica_no_desenvolvimento",
    )
    motivos = {}
    origens_cotacao_entrada = {}
    for item in itens:
        if item.get("motivo"):
            motivos[item["motivo"]] = motivos.get(item["motivo"], 0) + 1
        origem = item.get("origem_cotacao_entrada")
        if origem:
            origens_cotacao_entrada[origem] = (
                origens_cotacao_entrada.get(origem, 0) + 1
            )
    por_mercado = {}
    for mercado in sorted(MERCADOS_SUPORTADOS):
        grupo = _ordenar_entregas(
            item for item in itens_partida_mercado
            if item["mercado"] == mercado
        )
        por_mercado[mercado] = {
            **_marcar_diagnostico_nao_inferencial(
                _resumo_cobertura(grupo),
                "recorte_exploratorio_por_mercado",
            ),
            "ultimas_30_entregas": _marcar_diagnostico_nao_inferencial(
                _resumo_cobertura(grupo[-30:]),
                "janela_movel_exploratoria",
            ),
            "cotacao_entrada_prospectiva": (
                _resumo_cotacao_entrada_prospectiva(grupo)
            ),
        }
    itens_regra_independentes = _primeiros_independentes(
        itens_brutos,
        lambda item: (
            item["partida_id"], item["mercado"],
            item.get("regra_versao"), item.get("fonte"),
            item.get("bookmaker"),
        ),
    )
    grupos_regra = {}
    for item in itens_regra_independentes:
        chave = (
            item["mercado"], item.get("regra_versao"),
            item.get("fonte"), item.get("bookmaker"),
        )
        grupos_regra.setdefault(chave, []).append(item)
    por_regra_e_fonte = [
        {
            "mercado": chave[0],
            "regra_versao": chave[1],
            "fonte": chave[2],
            "bookmaker": chave[3],
            **_marcar_diagnostico_nao_inferencial(
                _resumo_cobertura(grupo),
                "recorte_exploratorio_por_regra_e_fonte",
            ),
        }
        for chave, grupo in sorted(
            grupos_regra.items(), key=lambda par: tuple(
                str(valor or "") for valor in par[0]
            )
        )
    ]
    return {
        "versao": VERSAO,
        "tipo": "mark_to_market_live_incluindo_liquidacoes",
        "criterio_independencia": "primeira_entrega_por_partida",
        "criterio_independencia_por_mercado": (
            "primeira_entrega_por_partida_e_mercado"
        ),
        "selecao_unidade_antes_da_comparabilidade": True,
        "horizonte_segundos": [
            HORIZONTE_MINIMO_SEGUNDOS, HORIZONTE_MAXIMO_SEGUNDOS,
        ],
        "entregas_brutas_consultadas": len(itens_brutos),
        "sinais_partida_mercado_consultados": len(
            itens_partida_mercado
        ),
        "sinais_entregues_consultados": len(itens),
        "sinais_independentes_consultados": len(itens),
        "comparaveis": len(comparaveis),
        "taxa_cobertura": (
            round(len(comparaveis) / len(itens), 6) if itens else None
        ),
        "exclusoes": motivos,
        "origens_cotacao_entrada": origens_cotacao_entrada,
        "cadeia_custodia_clv": cadeia_custodia,
        "cobertura_cotacao_entrada_prospectiva": (
            _resumo_cotacao_entrada_prospectiva(entregas_ordenadas)
        ),
        "coorte_clv_prospectiva_fixa": coorte_clv_prospectiva,
        "ultimas_100_entregas": _marcar_diagnostico_nao_inferencial(
            _resumo_cobertura(entregas_ordenadas[-100:]),
            "janela_movel_exploratoria",
        ),
        "total": resumo_total,
        "unidades_desenvolvimento_70pct": len(desenvolvimento),
        "unidades_holdout_30pct": len(holdout),
        "desenvolvimento_70pct": resumo_desenvolvimento,
        "holdout_30pct": resumo_holdout,
        "movimento_preco_contratos_sobreviventes": _metricas(
            cotacoes_abertas,
            natureza="movimento_preco_condicionado_sobrevivencia",
        ),
        "movimento_preco_desenvolvimento_70pct": _metricas(
            cotacoes_desenvolvimento,
            natureza="movimento_preco_condicionado_sobrevivencia",
        ),
        "movimento_preco_holdout_30pct": _metricas(
            cotacoes_holdout,
            natureza="movimento_preco_condicionado_sobrevivencia",
        ),
        "por_mercado": por_mercado,
        "por_regra_e_fonte": por_regra_e_fonte,
        "diagnostico_partida_e_mercado": _resumo_cobertura(
            itens_partida_mercado,
            natureza_principal=(
                "mark_to_market_multimercado_correlacionado"
            ),
        ),
        "diagnostico_todas_entregas": _resumo_cobertura(
            itens_brutos,
            natureza_principal=(
                "mark_to_market_todas_entregas_correlacionado"
            ),
        ),
        "itens": itens,
        "altera_sinais": False,
        "gate_operacional": False,
        "telegram": False,
        "promocao_automatica": False,
        "alerta_metodologico": (
            "liquidacoes antes de 2 minutos usam valor terminal 1/0; "
            "o mark-to-market completo e o movimento de preco apenas dos "
            "contratos ainda abertos aparecem separados; este ultimo sofre "
            "selecao de sobreviventes. O total principal usa uma unidade por "
            "partida; agregados multimercado sao correlacionados e nenhum "
            "desses diagnosticos substitui ROI/holdout. A unica divisao capaz "
            "de informar edge e a coorte prospectiva fixa de 120 partidas "
            "instrumentadas, com desenvolvimento 1-84 e holdout 85-120; "
            "unidades posteriores nao mudam sua composicao"
        ),
    }


def executar(caminho_banco=None):
    caminho = Path(caminho_banco or BANCO).resolve()
    with closing(sqlite3.connect(
        caminho.as_uri() + "?mode=ro", uri=True
    )) as conexao:
        conexao.row_factory = sqlite3.Row
        return avaliar(conexao)


if __name__ == "__main__":
    print(json.dumps(executar(), ensure_ascii=False, indent=2))
