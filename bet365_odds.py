import json
import math
import re
import unicodedata
from datetime import datetime


PADRAO_LADO_LINHA = re.compile(
    r"\b(mais\s+de|acima\s+de|over|menos\s+de|abaixo\s+de|under)"
    r"\s*(\d+(?:[.,]\d+)?)\b",
    re.IGNORECASE,
)
TERMOS_EXCLUIDOS = (
    "exactly",
    "exatamente",
    "corrida",
    "race",
    "handicap",
    "time da casa",
    "time visitante",
    "home team",
    "away team",
)
ESTADOS_OBSERVACAO = frozenset({
    "jogo_nao_encontrado",
    "jogo_ambiguo",
    "painel_nao_carregou",
    "mercado_ausente",
    "mercado_rejeitado",
    "oferta_valida",
    "bloqueado",
})


def _texto_normalizado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return " ".join(texto.casefold().split())


def _numero_decimal(valor):
    if isinstance(valor, bool):
        return None
    try:
        numero = float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numero):
        return None
    return numero


def _linha_asiatica_valida(linha):
    if linha is None or not 0 <= linha <= 100:
        return False
    quartos = round(linha * 4)
    return abs(linha * 4 - quartos) < 1e-8


def _lado_e_linha(selecao):
    nome = _texto_normalizado(selecao.get("nome"))
    lado = _texto_normalizado(selecao.get("lado"))
    linha = _numero_decimal(selecao.get("linha"))
    if lado in ("over", "mais de", "acima de"):
        lado = "over"
    elif lado in ("under", "menos de", "abaixo de"):
        lado = "under"
    else:
        encontrado = PADRAO_LADO_LINHA.search(nome)
        if encontrado is None:
            return None, None
        termo = _texto_normalizado(encontrado.group(1))
        lado = (
            "over"
            if termo in ("over", "mais de", "acima de")
            else "under"
        )
        linha = _numero_decimal(encontrado.group(2))
    return lado, linha


def eventos_correspondentes_bet365(eventos, mandante, visitante):
    """Retorna apenas correspondências exatas na mesma orientação."""
    mandante = _texto_normalizado(mandante)
    visitante = _texto_normalizado(visitante)
    return [
        evento for evento in eventos or []
        if (
            _texto_normalizado(evento.get("mandante")) == mandante
            and _texto_normalizado(evento.get("visitante")) == visitante
        )
    ]


def parear_partida_bet365(eventos, mandante, visitante):
    """Exige os dois nomes na mesma orientação; não faz pareamento aproximado."""
    encontrados = eventos_correspondentes_bet365(
        eventos, mandante, visitante
    )
    if len(encontrados) != 1:
        return None
    return encontrados[0]


def diagnosticar_mercado_escanteios_bet365(
    titulo,
    selecoes,
    *,
    periodo=None,
    evento_id=None,
    url=None,
    coletado_em=None,
):
    titulo_normalizado = _texto_normalizado(titulo)
    if not (
        "escanteio" in titulo_normalizado
        or "corner" in titulo_normalizado
    ):
        return None, "mercado_nao_e_escanteios"
    if any(termo in titulo_normalizado for termo in TERMOS_EXCLUIDOS):
        return None, "mercado_nao_asiatico_de_duas_opcoes"
    if periodo not in (None, "1T", "2T"):
        return None, "periodo_invalido"

    por_linha = {}
    for selecao in selecoes or []:
        if not isinstance(selecao, dict) or selecao.get("suspensa") is True:
            continue
        lado, linha = _lado_e_linha(selecao)
        odd = _numero_decimal(selecao.get("odd"))
        if (
            lado not in ("over", "under")
            or not _linha_asiatica_valida(linha)
            or odd is None
            or not 1.0 < odd <= 1000
        ):
            continue
        oferta = por_linha.setdefault(linha, {})
        if lado in oferta and oferta[lado] != odd:
            return None, "selecao_duplicada_ambigua"
        oferta[lado] = odd

    ofertas = []
    for linha in sorted(por_linha):
        lados = por_linha[linha]
        if "over" in lados and "under" in lados:
            ofertas.append({
                "linha": float(linha),
                "over": float(lados["over"]),
                "under": float(lados["under"]),
                "fonte": "bet365_site",
                "bookmaker": "Bet365",
            })
    if not ofertas:
        return None, "over_under_incompleto_ou_suspenso"

    coletado_em = coletado_em or datetime.now().replace(
        microsecond=0
    ).isoformat()
    mercado = {
        "mercado": str(titulo or "Escanteios Asiáticos"),
        "dados": " ".join(
            f"{item['linha']:g} {item['over']:g} {item['under']:g}"
            for item in ofertas
        ),
        "categoria": "escanteios",
        "escopo": "total",
        "tipo_mercado": "asiatico",
        "formato": "duas_opcoes",
        "ofertas": ofertas if periodo is None else [],
        "ofertas_exatamente": [],
        "ofertas_periodos": (
            {
                periodo: {
                    "formato": "duas_opcoes",
                    "ofertas": ofertas,
                }
            }
            if periodo else {}
        ),
        "ofertas_ht": [],
        "selecoes": {},
        "fonte": "bet365_site",
        "bookmaker": "Bet365",
        "coletado_em": coletado_em,
        "cache": False,
        "evento_id": evento_id,
        "url_origem": url,
    }
    return mercado, None


def estruturar_mercado_escanteios_bet365(*args, **kwargs):
    mercado, _ = diagnosticar_mercado_escanteios_bet365(*args, **kwargs)
    return mercado


def registrar_observacao_bet365(
    conexao,
    estado,
    *,
    partida_id=None,
    evento_externo_id=None,
    mandante_observado=None,
    visitante_observado=None,
    periodo=None,
    mercado=None,
    motivo=None,
    oferta=None,
    url_origem=None,
    consultado_em=None,
    metodo_coleta="automatizada",
    evidencia_sha256=None,
    evidencia_referencia=None,
):
    if estado not in ESTADOS_OBSERVACAO:
        raise ValueError("Estado de observacao Bet365 invalido.")
    if periodo not in (None, "FT", "1T", "2T"):
        raise ValueError("Periodo de observacao Bet365 invalido.")
    if metodo_coleta not in ("automatizada", "manual_usuario"):
        raise ValueError("Metodo de coleta Bet365 invalido.")
    if metodo_coleta == "manual_usuario" and (
        not re.fullmatch(r"[0-9a-f]{64}", str(evidencia_sha256 or ""))
        or not str(evidencia_referencia or "").strip()
    ):
        raise ValueError(
            "Coleta manual exige arquivo de evidencia e SHA-256."
        )
    if estado == "oferta_valida":
        if not isinstance(oferta, dict):
            raise ValueError("Oferta valida exige evidencia estruturada.")
        if (
            oferta.get("fonte") != "bet365_site"
            or oferta.get("formato") != "duas_opcoes"
        ):
            raise ValueError("Oferta Bet365 incompativel.")
        ofertas = oferta.get("ofertas") or []
        if not ofertas:
            for dados_periodo in (
                oferta.get("ofertas_periodos") or {}
            ).values():
                if isinstance(dados_periodo, dict):
                    ofertas = dados_periodo.get("ofertas") or []
                if ofertas:
                    break
        if not ofertas:
            raise ValueError("Oferta Bet365 sem linha completa.")
    instante = consultado_em or datetime.now().replace(
        microsecond=0
    ).isoformat()
    oferta_json = (
        json.dumps(
            oferta,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if oferta is not None else None
    )
    with conexao:
        cursor = conexao.execute(
            """
            INSERT INTO observacoes_fontes_odds (
                partida_id, fonte, consultado_em, estado,
                evento_externo_id, mandante_observado,
                visitante_observado, periodo, mercado,
                motivo, oferta_json, url_origem, metodo_coleta,
                evidencia_sha256, evidencia_referencia
            ) VALUES (
                ?, 'bet365_site', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                partida_id,
                instante,
                estado,
                evento_externo_id,
                mandante_observado,
                visitante_observado,
                periodo,
                mercado,
                motivo,
                oferta_json,
                url_origem,
                metodo_coleta,
                evidencia_sha256,
                evidencia_referencia,
            ),
        )
    return int(cursor.lastrowid)


def _ofertas_persistidas(oferta, periodo):
    if not isinstance(oferta, dict):
        return []
    if periodo in ("1T", "2T"):
        dados = (oferta.get("ofertas_periodos") or {}).get(periodo)
        return (dados or {}).get("ofertas") or []
    return oferta.get("ofertas") or []


def _oferta_persistida_integra(linha, oferta):
    periodo = linha["periodo"]
    if (
        not isinstance(oferta, dict)
        or oferta.get("fonte") != "bet365_site"
        or oferta.get("bookmaker") != "Bet365"
        or oferta.get("categoria") != "escanteios"
        or oferta.get("formato") != "duas_opcoes"
        or oferta.get("evento_id") != linha["evento_externo_id"]
        or oferta.get("url_origem") != linha["url_origem"]
        or not linha["evento_externo_id"]
        or not linha["mandante_observado"]
        or not linha["visitante_observado"]
        or not linha["url_origem"]
    ):
        return False
    ofertas = _ofertas_persistidas(oferta, periodo)
    if not ofertas:
        return False
    for item in ofertas:
        if not isinstance(item, dict):
            return False
        linha_asiatica = _numero_decimal(item.get("linha"))
        over = _numero_decimal(item.get("over"))
        under = _numero_decimal(item.get("under"))
        if (
            not _linha_asiatica_valida(linha_asiatica)
            or over is None
            or under is None
            or not 1.0 < over <= 1000
            or not 1.0 < under <= 1000
        ):
            return False
    return True


def auditar_observacoes_bet365(conexao, agora=None):
    agora = agora or datetime.now()
    linhas = conexao.execute(
        """
        SELECT *
        FROM observacoes_fontes_odds
        WHERE fonte='bet365_site'
        ORDER BY consultado_em, id
        """
    ).fetchall()
    problemas = {
        "estado_invalido": 0,
        "periodo_invalido": 0,
        "timestamp_invalido_ou_futuro": 0,
        "json_invalido": 0,
        "oferta_valida_incompleta": 0,
        "estado_negativo_com_oferta": 0,
        "metodo_coleta_invalido": 0,
        "evidencia_manual_invalida": 0,
    }
    ofertas_validas_integras = 0
    for linha in linhas:
        if linha["estado"] not in ESTADOS_OBSERVACAO:
            problemas["estado_invalido"] += 1
        if linha["periodo"] not in (None, "FT", "1T", "2T"):
            problemas["periodo_invalido"] += 1
        metodo_coleta = linha["metodo_coleta"]
        if metodo_coleta not in ("automatizada", "manual_usuario"):
            problemas["metodo_coleta_invalido"] += 1
        if metodo_coleta == "manual_usuario" and (
            not re.fullmatch(
                r"[0-9a-f]{64}",
                str(linha["evidencia_sha256"] or ""),
            )
            or not str(linha["evidencia_referencia"] or "").strip()
        ):
            problemas["evidencia_manual_invalida"] += 1
        try:
            instante = datetime.fromisoformat(linha["consultado_em"])
            instante_invalido = instante > agora
        except (TypeError, ValueError):
            instante_invalido = True
        if instante_invalido:
            problemas["timestamp_invalido_ou_futuro"] += 1
        oferta = None
        if linha["oferta_json"] is not None:
            try:
                oferta = json.loads(linha["oferta_json"])
            except (json.JSONDecodeError, TypeError):
                problemas["json_invalido"] += 1
        if linha["estado"] == "oferta_valida":
            if _oferta_persistida_integra(linha, oferta):
                ofertas_validas_integras += 1
            else:
                problemas["oferta_valida_incompleta"] += 1
        elif linha["oferta_json"] is not None:
            problemas["estado_negativo_com_oferta"] += 1
    problemas = {
        motivo: total for motivo, total in problemas.items() if total
    }
    return {
        "saudavel": not problemas,
        "estado": "integra" if not problemas else "inconsistente",
        "total": len(linhas),
        "ofertas_validas_integras": ofertas_validas_integras,
        "problemas": problemas,
        "comprovada": ofertas_validas_integras > 0,
        "ativa_no_monitor": False,
    }


def resumir_observacoes_bet365(conexao):
    linhas = conexao.execute(
        """
        SELECT estado, COALESCE(motivo, '-') AS motivo, COUNT(*) AS total,
               MAX(consultado_em) AS ultima_observacao
        FROM observacoes_fontes_odds
        WHERE fonte='bet365_site'
        GROUP BY estado, COALESCE(motivo, '-')
        ORDER BY estado, motivo
        """
    ).fetchall()
    por_estado = {}
    por_motivo = {}
    por_metodo = {}
    ultima_observacao = None
    for linha in linhas:
        total = int(linha["total"] or 0)
        por_estado[linha["estado"]] = (
            por_estado.get(linha["estado"], 0) + total
        )
        if linha["motivo"] != "-":
            por_motivo[linha["motivo"]] = (
                por_motivo.get(linha["motivo"], 0) + total
            )
        instante = linha["ultima_observacao"]
        if instante and (
            ultima_observacao is None or instante > ultima_observacao
        ):
            ultima_observacao = instante
    for linha in conexao.execute(
        """
        SELECT metodo_coleta, COUNT(*) AS total
        FROM observacoes_fontes_odds
        WHERE fonte='bet365_site'
        GROUP BY metodo_coleta
        ORDER BY metodo_coleta
        """
    ).fetchall():
        por_metodo[linha["metodo_coleta"]] = int(linha["total"] or 0)
    integridade = auditar_observacoes_bet365(conexao)
    return {
        "fonte": "bet365_site",
        "total": sum(por_estado.values()),
        "ofertas_validas": por_estado.get("oferta_valida", 0),
        "por_estado": dict(sorted(por_estado.items())),
        "por_motivo": dict(sorted(por_motivo.items())),
        "por_metodo": dict(sorted(por_metodo.items())),
        "ultima_observacao": ultima_observacao,
        "ativa_no_monitor": False,
        "integridade": integridade,
    }
