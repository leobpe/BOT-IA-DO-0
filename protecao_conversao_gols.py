"""Proteção transversal contra sinais de gol sustentados por volume estéril."""

import copy
import math
import os
import unicodedata

from contrafactual_protecoes import converter_em_contrafactual


VERSAO = "protecao-conversao-gols-v1"
ATIVA = os.getenv("PROTECAO_CONVERSAO_GOLS_ATIVA", "1").strip().lower() not in {
    "0", "false", "nao", "não", "off",
}
MERCADOS = frozenset({"gol_ft", "gol_ht", "proximo_gol"})
AMOSTRA_GERAL_MINIMA = 10
AMOSTRA_MANDO_MINIMA = 4

MINIMOS_FT = {
    0.5: (0.65, 0.60), 1.5: (0.50, 0.45),
    2.5: (0.35, 0.30), 3.5: (0.20, 0.15),
    4.5: (0.12, 0.08), 5.5: (0.08, 0.05),
    6.5: (0.05, 0.03), 7.5: (0.03, 0.02),
    8.5: (0.02, 0.01), 9.5: (0.01, 0.01),
}
MINIMOS_HT = {
    0.5: (0.50, 0.45), 1.5: (0.25, 0.20),
    2.5: (0.10, 0.08), 3.5: (0.05, 0.03),
    4.5: (0.02, 0.01),
}


def _numero(valor):
    try:
        numero = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
    return numero if numero is not None and math.isfinite(numero) else None


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(x for x in texto if not unicodedata.combining(x)).casefold()


def _resultado(aprovada, motivo, **detalhes):
    return {
        "versao": VERSAO,
        "ativa": ATIVA,
        "aprovada": bool(aprovada),
        "motivo": motivo,
        **detalhes,
    }


def _avaliar_linha(candidato, contexto, periodo):
    linha = _numero(candidato.get("linha"))
    limites = MINIMOS_HT if periodo == "ht" else MINIMOS_FT
    if linha not in limites:
        return _resultado(False, "linha_sem_modelo_de_conversao", linha=linha)
    recentes = (
        ((contexto or {}).get("tendencia_linhas_gols_v1") or {}).get("recentes")
        or {}
    )
    prefixo = "ht_" if periodo == "ht" else ""
    campo = prefixo + f"over_{str(linha).replace('.', '_')}_taxa"
    campo_amostra = "jogos_ht" if periodo == "ht" else "jogos"
    gerais = [
        ((recentes.get(lado) or {}).get("geral") or {})
        for lado in ("mandante", "visitante")
    ]
    mandos = [
        ((recentes.get(lado) or {}).get("mando") or {})
        for lado in ("mandante", "visitante")
    ]
    amostras_gerais = [
        int(_numero(item.get(campo_amostra)) or 0) for item in gerais
    ]
    amostras_mando = [
        int(_numero(item.get(campo_amostra)) or 0) for item in mandos
    ]
    if any(
        amostra < AMOSTRA_GERAL_MINIMA
        or _numero(item.get(campo)) is None
        for item, amostra in zip(gerais, amostras_gerais)
    ) or any(
        amostra < AMOSTRA_MANDO_MINIMA
        or _numero(item.get(campo)) is None
        for item, amostra in zip(mandos, amostras_mando)
    ):
        return _resultado(
            False, "historico_da_linha_insuficiente",
            mercado=candidato.get("mercado"), linha=linha, campo=campo,
            amostras_gerais=amostras_gerais,
            amostras_mando=amostras_mando,
            amostra_geral_minima=AMOSTRA_GERAL_MINIMA,
            amostra_mando_minima=AMOSTRA_MANDO_MINIMA,
        )
    taxas_gerais = [_numero(item[campo]) for item in gerais]
    taxas_mando = [_numero(item[campo]) for item in mandos]
    media_geral = sum(taxas_gerais) / len(taxas_gerais)
    media_mando = sum(taxas_mando) / len(taxas_mando)
    minima_geral, minima_mando = limites[linha]
    aprovada = media_geral >= minima_geral and media_mando >= minima_mando
    return _resultado(
        aprovada,
        "apoio_da_linha_confirmado" if aprovada else "apoio_da_linha_fraco",
        mercado=candidato.get("mercado"), linha=linha, campo=campo,
        media_geral=round(media_geral, 4),
        media_mando=round(media_mando, 4),
        minima_geral=minima_geral, minima_mando=minima_mando,
        taxas_gerais=taxas_gerais, taxas_mando=taxas_mando,
        amostras_gerais=amostras_gerais,
        amostras_mando=amostras_mando,
        amostra_geral_minima=AMOSTRA_GERAL_MINIMA,
        amostra_mando_minima=AMOSTRA_MANDO_MINIMA,
    )


def _lado_proximo_gol(candidato):
    texto = _normalizar(candidato.get("linha"))
    if any(x in texto for x in ("casa", "mandante", "home")):
        return "mandante"
    if any(x in texto for x in ("fora", "visitante", "away")):
        return "visitante"
    lado = _normalizar((candidato.get("features") or {}).get("lado_dominante"))
    if lado in {"mandante", "visitante"}:
        return lado
    return None


def _avaliar_proximo_gol(candidato, contexto):
    lado = _lado_proximo_gol(candidato)
    if lado is None:
        return _resultado(False, "lado_do_proximo_gol_indisponivel")
    rival = "visitante" if lado == "mandante" else "mandante"
    recentes = (
        ((contexto or {}).get("capacidade_times_v2") or {}).get("recentes")
        or {}
    )
    ataque = ((recentes.get(lado) or {}).get("mando") or {})
    defesa = ((recentes.get(rival) or {}).get("mando") or {})
    jogos_ataque = int(_numero(ataque.get("jogos")) or 0)
    jogos_defesa = int(_numero(defesa.get("jogos")) or 0)
    marcou = _numero(ataque.get("marcou_taxa"))
    sofreu = _numero(defesa.get("sofreu_taxa"))
    if (
        jogos_ataque < AMOSTRA_MANDO_MINIMA
        or jogos_defesa < AMOSTRA_MANDO_MINIMA
        or marcou is None or sofreu is None
    ):
        return _resultado(False, "historico_de_conversao_insuficiente", lado=lado)
    aprovada = marcou >= 0.50 and sofreu >= 0.40
    return _resultado(
        aprovada,
        "conversao_do_lado_confirmada" if aprovada else "conversao_do_lado_fraca",
        lado=lado, marcou_mando=marcou, rival_sofreu_mando=sofreu,
        minimo_marcou=0.50, minimo_rival_sofreu=0.40,
    )


def avaliar_protecao_conversao(candidato, contexto):
    mercado = candidato.get("mercado")
    if mercado not in MERCADOS or not ATIVA:
        return _resultado(True, "fora_do_escopo_ou_desativada", mercado=mercado)
    if mercado == "proximo_gol":
        return _avaliar_proximo_gol(candidato, contexto)
    return _avaliar_linha(
        candidato, contexto, "ht" if mercado == "gol_ht" else "ft"
    )


def aplicar_protecao_conversao_gols(candidatos, contexto):
    resumo = {"avaliados": 0, "aprovados": 0, "bloqueados": 0, "motivos": {}}
    for candidato in candidatos or []:
        if candidato.get("mercado") not in MERCADOS or candidato.get("status") not in {
            "aprovado", "simulacao",
        }:
            continue
        avaliacao = avaliar_protecao_conversao(candidato, contexto)
        features = copy.deepcopy(candidato.get("features") or {})
        features["protecao_conversao_gols"] = avaliacao
        candidato["features"] = features
        resumo["avaliados"] += 1
        if avaliacao["aprovada"]:
            resumo["aprovados"] += 1
            continue
        resumo["bloqueados"] += 1
        motivo = "protecao_conversao_gols:" + avaliacao["motivo"]
        resumo["motivos"][motivo] = resumo["motivos"].get(motivo, 0) + 1
        bloqueios = list(candidato.get("bloqueios") or [])
        if motivo not in bloqueios:
            bloqueios.append(motivo)
        candidato["bloqueios"] = bloqueios
        converter_em_contrafactual(
            candidato,
            "protecao_conversao_gols",
            avaliacao["motivo"],
        )
        motivos = list(candidato.get("motivos") or [])
        if motivo not in motivos:
            motivos.append(motivo)
        candidato["motivos"] = motivos
    return resumo
