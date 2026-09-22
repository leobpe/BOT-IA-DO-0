"""Série temporal auxiliar das estatísticas ao vivo da API-Football.

Este histórico é observacional: não libera sinais nem substitui o PackBall.
"""

from collections import defaultdict
from datetime import datetime, timedelta
import json

from estatistica import limite_inferior_wilson


JANELAS_API_MINUTOS = (5, 10, 15)
TOLERANCIA_JANELA_API_MINUTOS = 3
MINIMO_SNAPSHOTS_COMPARAVEIS = 30
MINIMO_FIXTURES_COMPARAVEIS = 10
MINIMO_TAXA_CONCORDANCIA = 0.80
MINIMO_WILSON_CONCORDANCIA = 0.70
INTERVALO_INDEPENDENCIA_MINUTOS = 5
METRICAS_API_LIVE = {
    "Total Shots": "chutes",
    "Shots on Goal": "chutes_gol",
    "Corner Kicks": "escanteios",
    "expected_goals": "xg",
}


def _numero_api(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(str(valor).replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return round(numero, 4)


def _periodo_api(status):
    status = status or {}
    curto = str(status.get("short") or "").strip().upper()
    if curto in {"1H", "HT"}:
        return "primeiro_tempo"
    if curto in {"2H", "BT", "P", "SUSP", "INT"}:
        return "segundo_tempo"
    try:
        minuto = int(status.get("elapsed"))
    except (TypeError, ValueError):
        return None
    return "primeiro_tempo" if minuto <= 45 else "segundo_tempo"


def _metricas_por_lado(fixture):
    fixture = fixture or {}
    times = fixture.get("teams") or {}
    ids = {
        "mandante": (times.get("home") or {}).get("id"),
        "visitante": (times.get("away") or {}).get("id"),
    }
    blocos = [
        item for item in fixture.get("statistics") or []
        if isinstance(item, dict)
    ]
    por_id = {
        (item.get("team") or {}).get("id"): item
        for item in blocos
        if (item.get("team") or {}).get("id") is not None
    }
    resultado = {}
    for indice, lado in enumerate(("mandante", "visitante")):
        bloco = por_id.get(ids[lado])
        if bloco is None and indice < len(blocos):
            bloco = blocos[indice]
        metricas = {nome: None for nome in METRICAS_API_LIVE.values()}
        for item in (bloco or {}).get("statistics") or []:
            if not isinstance(item, dict):
                continue
            nome = METRICAS_API_LIVE.get(item.get("type"))
            if nome:
                metricas[nome] = _numero_api(item.get("value"))
        resultado[lado] = metricas
    return resultado


def normalizar_snapshot_api_live(
    fixture, packball_url, orientacao="direta", coletado_em=None
):
    """Reduz um fixture detalhado a contadores comparáveis no tempo."""
    fixture = fixture or {}
    bloco_fixture = fixture.get("fixture") or {}
    fixture_id = bloco_fixture.get("id")
    if fixture_id is None or not packball_url:
        return None
    status = bloco_fixture.get("status") or {}
    metricas = _metricas_por_lado(fixture)
    if orientacao == "invertida":
        metricas = {
            "mandante": metricas["visitante"],
            "visitante": metricas["mandante"],
        }
    pares_obrigatorios = ("chutes", "chutes_gol", "escanteios")
    completo = all(
        metricas[lado][nome] is not None
        for lado in ("mandante", "visitante")
        for nome in pares_obrigatorios
    )
    tem_metrica = any(
        valor is not None
        for lado in metricas.values()
        for valor in lado.values()
    )
    if not tem_metrica:
        return None
    instante = coletado_em or datetime.now().replace(microsecond=0)
    if isinstance(instante, datetime):
        instante = instante.replace(microsecond=0).isoformat()
    return {
        "fixture_id": int(fixture_id),
        "packball_url": str(packball_url),
        "coletado_em": str(instante),
        "minuto": _numero_api(status.get("elapsed")),
        "periodo": _periodo_api(status),
        "orientacao": (
            "invertida" if orientacao == "invertida" else "direta"
        ),
        "chutes_mandante": metricas["mandante"]["chutes"],
        "chutes_visitante": metricas["visitante"]["chutes"],
        "chutes_gol_mandante": metricas["mandante"]["chutes_gol"],
        "chutes_gol_visitante": metricas["visitante"]["chutes_gol"],
        "escanteios_mandante": metricas["mandante"]["escanteios"],
        "escanteios_visitante": metricas["visitante"]["escanteios"],
        "xg_mandante": metricas["mandante"]["xg"],
        "xg_visitante": metricas["visitante"]["xg"],
        "completo": bool(completo),
        "fonte": "api_football",
    }


def _instante(valor):
    if isinstance(valor, datetime):
        return valor
    return datetime.fromisoformat(str(valor))


def calcular_evolucao_api_live(registros):
    """Calcula deltas 5/10/15 da leitura API mais recente."""
    registros = sorted(
        (dict(item) for item in registros or []),
        key=lambda item: _instante(item["coletado_em"]),
    )
    if len(registros) < 2:
        return {
            **{str(janela): None for janela in JANELAS_API_MINUTOS},
            "periodo": registros[-1].get("periodo") if registros else None,
            "fonte": "api_football",
            "aplicacao_sinais": False,
        }
    atual = registros[-1]
    instante_atual = _instante(atual["coletado_em"])
    anteriores = [
        item for item in registros[:-1]
        if (
            not atual.get("periodo")
            or not item.get("periodo")
            or item.get("periodo") == atual.get("periodo")
        )
    ]
    evolucao = {}
    campos = {
        "chutes": ("chutes_mandante", "chutes_visitante"),
        "chutes_gol": (
            "chutes_gol_mandante", "chutes_gol_visitante"
        ),
        "escanteios": (
            "escanteios_mandante", "escanteios_visitante"
        ),
        "xg": ("xg_mandante", "xg_visitante"),
    }
    for alvo in JANELAS_API_MINUTOS:
        candidatas = []
        for item in anteriores:
            duracao = (
                instante_atual - _instante(item["coletado_em"])
            ).total_seconds() / 60
            if alvo <= duracao <= alvo + TOLERANCIA_JANELA_API_MINUTOS:
                candidatas.append((duracao, item))
        if not candidatas:
            evolucao[str(alvo)] = None
            continue
        duracao, referencia = min(
            candidatas, key=lambda par: abs(par[0] - alvo)
        )
        deltas = {}
        resets = []
        for metrica, (campo_casa, campo_fora) in campos.items():
            valores_atuais = (
                atual.get(campo_casa), atual.get(campo_fora)
            )
            valores_referencia = (
                referencia.get(campo_casa), referencia.get(campo_fora)
            )
            if any(
                valor is None
                for valor in (*valores_atuais, *valores_referencia)
            ):
                deltas[metrica] = None
                continue
            if any(
                atual_lado < anterior_lado
                for atual_lado, anterior_lado in zip(
                    valores_atuais, valores_referencia
                )
            ):
                deltas[metrica] = None
                resets.append(metrica)
                continue
            deltas[metrica] = [
                round(atual_lado - anterior_lado, 4)
                for atual_lado, anterior_lado in zip(
                    valores_atuais, valores_referencia
                )
            ]
        deltas.update({
            "duracao_real_minutos": round(duracao, 2),
            "desvio_alvo_minutos": round(duracao - alvo, 2),
            "resets_detectados": resets,
        })
        evolucao[str(alvo)] = (
            deltas
            if any(deltas.get(nome) is not None for nome in campos)
            else None
        )
    evolucao.update({
        "periodo": atual.get("periodo"),
        "fonte": "api_football",
        "coletado_em": atual.get("coletado_em"),
        "fixture_id": atual.get("fixture_id"),
        "aplicacao_sinais": False,
    })
    return evolucao


def janelas_disponiveis_api_live(registros):
    """Calcula janelas fechadas para a leitura mais recente do fixture."""
    evolucao = calcular_evolucao_api_live(registros)
    return {
        janela for janela in JANELAS_API_MINUTOS
        if isinstance(evolucao.get(str(janela)), dict)
    }


def obter_evolucao_api_live(
    conexao, fixture_id, packball_url, agora=None, minutos=20
):
    """Carrega a sequência recente de um pareamento comprovado."""
    agora = agora or datetime.now()
    desde = (agora - timedelta(minutes=float(minutos) + 3)).isoformat()
    linhas = conexao.execute(
        """
        SELECT * FROM historico_api_live
        WHERE fixture_id=? AND packball_url=?
          AND datetime(coletado_em) >= datetime(?)
          AND datetime(coletado_em) <= datetime(?)
        ORDER BY coletado_em
        """,
        (
            int(fixture_id), str(packball_url), desde,
            agora.isoformat(),
        ),
    ).fetchall()
    return calcular_evolucao_api_live(linhas)


def comparar_evolucoes_packball_api(evolucao_packball, evolucao_api):
    """Compara apenas contadores equivalentes e mantém uso em sombra."""
    comparacoes = []
    tolerancias = {"chutes": 2.0, "escanteios": 1.0}
    for janela in JANELAS_API_MINUTOS:
        packball = (evolucao_packball or {}).get(str(janela))
        api = (evolucao_api or {}).get(str(janela))
        if not isinstance(packball, dict) or not isinstance(api, dict):
            continue
        for metrica, tolerancia in tolerancias.items():
            valor_packball = packball.get(metrica)
            valor_api = api.get(metrica)
            if not (
                isinstance(valor_packball, (list, tuple))
                and isinstance(valor_api, (list, tuple))
                and len(valor_packball) == 2
                and len(valor_api) == 2
            ):
                continue
            diferencas = [
                round(abs(float(a) - float(b)), 4)
                for a, b in zip(valor_packball, valor_api)
            ]
            comparacoes.append({
                "janela": janela,
                "metrica": metrica,
                "packball": list(valor_packball),
                "api_football": list(valor_api),
                "diferencas_absolutas": diferencas,
                "tolerancia": tolerancia,
                "concordante": max(diferencas) <= tolerancia,
            })
    concordantes = sum(item["concordante"] for item in comparacoes)
    return {
        "comparacoes": comparacoes,
        "total": len(comparacoes),
        "concordantes": concordantes,
        "taxa_concordancia": (
            round(concordantes / len(comparacoes), 4)
            if comparacoes else None
        ),
        "aplicacao_sinais": False,
        "estado": "comparavel" if comparacoes else "sem_janela_comum",
    }


def resumir_historico_api_live(conexao, agora=None, horas=24):
    """Audita cobertura recente sem torná-la requisito operacional."""
    agora = agora or datetime.now()
    desde = (agora - timedelta(hours=float(horas))).isoformat()
    try:
        linhas = conexao.execute(
            """
            SELECT * FROM historico_api_live
            WHERE datetime(coletado_em) >= datetime(?)
            ORDER BY fixture_id, packball_url, coletado_em
            """,
            (desde,),
        ).fetchall()
    except Exception as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "historico_api_live_indisponivel",
            "erro": type(erro).__name__,
            "aplicacao_sinais": False,
        }
    grupos = defaultdict(list)
    for linha in linhas:
        item = dict(linha)
        grupos[(item["fixture_id"], item["packball_url"])].append(item)
    janelas = {str(valor): 0 for valor in JANELAS_API_MINUTOS}
    com_historico = 0
    for registros in grupos.values():
        disponiveis = janelas_disponiveis_api_live(registros)
        com_historico += bool(disponiveis)
        for janela in disponiveis:
            janelas[str(janela)] += 1
    completos = sum(bool(dict(linha).get("completo")) for linha in linhas)
    total = len(linhas)
    snapshots_comparaveis = 0
    comparaveis_por_partida = defaultdict(list)
    comparacoes = 0
    concordantes = 0
    contextos_invalidos = 0
    try:
        linhas_contexto = conexao.execute(
            """
            SELECT partida_id, coletado_em, contexto_api_json
            FROM snapshots
            WHERE datetime(coletado_em) >= datetime(?)
              AND contexto_api_json IS NOT NULL
              AND contexto_api_json NOT IN ('null', '{}', '')
            ORDER BY partida_id, coletado_em
            """,
            (desde,),
        ).fetchall()
    except Exception:
        linhas_contexto = []
    for linha in linhas_contexto:
        try:
            contexto = json.loads(dict(linha)["contexto_api_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            contextos_invalidos += 1
            continue
        comparacao = (
            (contexto or {}).get("comparacao_temporal_packball_api")
            or {}
        )
        quantidade = int(comparacao.get("total", 0) or 0)
        if quantidade <= 0:
            continue
        snapshots_comparaveis += 1
        concordantes_snapshot = int(
            comparacao.get("concordantes", 0) or 0
        )
        item_linha = dict(linha)
        try:
            instante_comparacao = _instante(item_linha["coletado_em"])
        except (KeyError, TypeError, ValueError):
            contextos_invalidos += 1
            continue
        comparaveis_por_partida[item_linha.get("partida_id")].append((
            instante_comparacao,
            concordantes_snapshot == quantidade,
        ))
        comparacoes += quantidade
        concordantes += concordantes_snapshot
    comparaveis_por_partida.pop(None, None)
    snapshots_independentes = 0
    snapshots_concordantes = 0
    fixtures_comparaveis = set()
    intervalo_independencia = timedelta(
        minutes=INTERVALO_INDEPENDENCIA_MINUTOS
    )
    for partida_id, observacoes in comparaveis_por_partida.items():
        ultima_aceita = None
        for instante_comparacao, concordante in sorted(observacoes):
            if (
                ultima_aceita is not None
                and instante_comparacao - ultima_aceita
                < intervalo_independencia
            ):
                continue
            ultima_aceita = instante_comparacao
            snapshots_independentes += 1
            snapshots_concordantes += int(concordante)
            fixtures_comparaveis.add(partida_id)
    taxa_snapshots = (
        snapshots_concordantes / snapshots_independentes
        if snapshots_independentes else None
    )
    wilson_snapshots = (
        limite_inferior_wilson(
            snapshots_concordantes, snapshots_independentes
        )
        if snapshots_independentes else None
    )
    faltam_snapshots = max(
        MINIMO_SNAPSHOTS_COMPARAVEIS - snapshots_independentes, 0
    )
    faltam_fixtures = max(
        MINIMO_FIXTURES_COMPARAVEIS - len(fixtures_comparaveis), 0
    )
    if faltam_snapshots or faltam_fixtures:
        estado_prontidao = "aguardando_amostra"
    elif (
        taxa_snapshots < MINIMO_TAXA_CONCORDANCIA
        or wilson_snapshots < MINIMO_WILSON_CONCORDANCIA
    ):
        estado_prontidao = "divergencia_fontes"
    else:
        estado_prontidao = "apto_revisao"
    return {
        "saudavel": True,
        "estado": "coletando" if total else "aguardando_primeira_amostra",
        "motivo": None,
        "horas": float(horas),
        "snapshots": total,
        "fixtures": len(grupos),
        "snapshots_completos": completos,
        "cobertura_completa": round(completos / total, 4) if total else None,
        "fixtures_com_historico": com_historico,
        "janelas_disponiveis": janelas,
        "snapshots_comparaveis_packball": snapshots_comparaveis,
        "snapshots_independentes_packball": snapshots_independentes,
        "snapshots_concordantes_packball": snapshots_concordantes,
        "fixtures_comparaveis_packball": len(fixtures_comparaveis),
        "taxa_concordancia_snapshots": (
            round(taxa_snapshots, 4)
            if taxa_snapshots is not None else None
        ),
        "limite_inferior_wilson_snapshots": (
            round(wilson_snapshots, 4)
            if wilson_snapshots is not None else None
        ),
        "comparacoes_packball_api": comparacoes,
        "comparacoes_concordantes": concordantes,
        "taxa_concordancia_packball_api": (
            round(concordantes / comparacoes, 4)
            if comparacoes else None
        ),
        "contextos_invalidos": contextos_invalidos,
        "prontidao_revisao": {
            "estado": estado_prontidao,
            "snapshots": snapshots_independentes,
            "minimo_snapshots": MINIMO_SNAPSHOTS_COMPARAVEIS,
            "faltam_snapshots": faltam_snapshots,
            "fixtures": len(fixtures_comparaveis),
            "minimo_fixtures": MINIMO_FIXTURES_COMPARAVEIS,
            "faltam_fixtures": faltam_fixtures,
            "taxa_minima": MINIMO_TAXA_CONCORDANCIA,
            "wilson_minimo": MINIMO_WILSON_CONCORDANCIA,
            "intervalo_independencia_minutos": (
                INTERVALO_INDEPENDENCIA_MINUTOS
            ),
            "apto_revisao": estado_prontidao == "apto_revisao",
            "aplicacao_automatica": False,
        },
        "aplicacao_sinais": False,
        "fonte": "api_football",
    }
