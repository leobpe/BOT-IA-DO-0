import json
import math
import statistics
from datetime import datetime

from backtest import calcular_metricas
from linhagem_regras import fingerprint_vinculado_no_banco
from qualidade_dados import extrair_placar


VERSAO_HIPOTESES_SOMBRA = "hipoteses-sombra-v2"
VERSOES_HIPOTESES_SOMBRA_SUPORTADAS = frozenset({
    "hipoteses-sombra-v1",
    VERSAO_HIPOTESES_SOMBRA,
})
CHAVE_PREFIXO = "hipotese_sombra:"
GATILHOS_HIPOTESES_SOMBRA = frozenset({
    "trg_hipotese_sombra_update_imutavel",
    "trg_hipotese_sombra_delete_imutavel",
})
RESULTADOS_VALIDOS = frozenset({
    "green", "half_green", "red", "half_red",
})
VERSAO_AVALIACAO_HIPOTESES_SOMBRA = (
    "avaliacao-hipoteses-sombra-controle-ic95-v2"
)
HIPOTESES_SOMBRA_DESCONTINUADAS = frozenset({
    "gol_ft_odd_atual_min_166_v1_20260803",
    "gol_ft_odd_166_minuto_max_82_v1_20260803",
})


def _chave(identificador):
    return f"{CHAVE_PREFIXO}{identificador}"


def listar_hipoteses_sombra(conexao, regra_versao=None):
    hipoteses = []
    for linha in conexao.execute(
        "SELECT valor FROM metadados WHERE chave LIKE ? ORDER BY chave",
        (f"{CHAVE_PREFIXO}%",),
    ).fetchall():
        try:
            dados = json.loads(linha["valor"])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            regra_versao is None
            or dados.get("regra_versao") == regra_versao
        ):
            hipoteses.append(dados)
    return hipoteses


def auditar_hipoteses_sombra(conexao, regra_versao=None):
    gatilhos = {
        linha[0] for linha in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    gatilhos_ausentes = sorted(
        GATILHOS_HIPOTESES_SOMBRA - gatilhos
    )
    invalidas = []
    total = 0
    identificadores = set()
    for chave, valor in conexao.execute(
        """
        SELECT chave, valor FROM metadados
        WHERE chave LIKE 'hipotese_sombra:%'
        ORDER BY chave
        """
    ).fetchall():
        total += 1
        try:
            dados = json.loads(valor)
            datetime.fromisoformat(dados["iniciado_em"])
            identificador = str(dados["identificador"])
            simples = _criterio_valido(dados)
            criterios = dados.get("criterios")
            composta = bool(
                dados.get("versao") == VERSAO_HIPOTESES_SOMBRA
                and dados.get("combinador") == "todos"
                and isinstance(criterios, list)
                and len(criterios) >= 2
                and all(_criterio_valido(item) for item in criterios)
            )
            if (
                dados.get("versao")
                not in VERSOES_HIPOTESES_SOMBRA_SUPORTADAS
                or chave != _chave(identificador)
                or identificador in identificadores
                or not (simples or composta)
                or int(dados.get("minimo_resultados", 0)) <= 0
                or dados.get("aplicacao_automatica") is not False
            ):
                raise ValueError("definicao incoerente")
            identificadores.add(identificador)
            if (
                regra_versao is None
                or dados.get("regra_versao") == regra_versao
            ):
                fingerprint = fingerprint_vinculado_no_banco(
                    conexao, dados.get("regra_versao")
                )
                if dados.get("regra_fingerprint") != fingerprint:
                    raise ValueError("fingerprint divergente")
        except (
            KeyError, TypeError, ValueError, json.JSONDecodeError
        ):
            invalidas.append(chave)
    saudavel = not gatilhos_ausentes and not invalidas
    if gatilhos_ausentes:
        motivo = "gatilhos_hipoteses_sombra_ausentes"
    elif invalidas:
        motivo = "hipoteses_sombra_invalidas"
    else:
        motivo = None
    return {
        "saudavel": saudavel,
        "estado": "valido" if saudavel else "inconsistente",
        "motivo": motivo,
        "total": total,
        "invalidas": invalidas,
        "gatilhos_ausentes": gatilhos_ausentes,
        "protegido": not gatilhos_ausentes,
    }


def registrar_hipotese_sombra(
    conexao,
    identificador,
    regra_versao,
    mercado,
    feature,
    operador,
    limiar,
    evidencia_historica,
    minimo_resultados=30,
    iniciado_em=None,
):
    existente = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (_chave(identificador),),
    ).fetchone()
    if existente is not None:
        dados = json.loads(existente["valor"])
        esperado = {
            "versao": VERSAO_HIPOTESES_SOMBRA,
            "identificador": identificador,
            "regra_versao": regra_versao,
            "mercado": mercado,
            "feature": feature,
            "operador": operador,
            "limiar": float(limiar),
            "minimo_resultados": int(minimo_resultados),
        }
        if any(dados.get(chave) != valor for chave, valor in esperado.items()):
            raise RuntimeError("Hipotese sombra registrada com outra definicao.")
        return dados
    if operador not in ("maior_igual", "menor_igual"):
        raise ValueError("Operador de hipotese sombra invalido.")
    fingerprint = fingerprint_vinculado_no_banco(
        conexao, regra_versao
    )
    if not fingerprint:
        raise RuntimeError("Regra sem linhagem vinculada para hipotese sombra.")
    dados = {
        "versao": VERSAO_HIPOTESES_SOMBRA,
        "identificador": identificador,
        "regra_versao": regra_versao,
        "regra_fingerprint": fingerprint,
        "mercado": mercado,
        "feature": feature,
        "operador": operador,
        "limiar": float(limiar),
        "minimo_resultados": int(minimo_resultados),
        "iniciado_em": (
            iniciado_em or datetime.now()
        ).replace(microsecond=0).isoformat(),
        "evidencia_historica": evidencia_historica,
        "aplicacao_automatica": False,
    }
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (_chave(identificador), json.dumps(
                dados, ensure_ascii=False, sort_keys=True
            )),
        )
    return dados


def registrar_hipotese_composta_sombra(
    conexao,
    identificador,
    regra_versao,
    mercado,
    criterios,
    evidencia_historica,
    minimo_resultados=30,
    iniciado_em=None,
):
    criterios = [
        {
            "feature": str(item.get("feature") or ""),
            "operador": str(item.get("operador") or ""),
            "limiar": float(item.get("limiar")),
        }
        for item in list(criterios or [])
    ]
    if len(criterios) < 2 or not all(
        _criterio_valido(item) for item in criterios
    ):
        raise ValueError("Critérios da hipótese composta são inválidos.")
    existente = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (_chave(identificador),),
    ).fetchone()
    esperado = {
        "versao": VERSAO_HIPOTESES_SOMBRA,
        "identificador": identificador,
        "regra_versao": regra_versao,
        "mercado": mercado,
        "criterios": criterios,
        "combinador": "todos",
        "minimo_resultados": int(minimo_resultados),
    }
    if existente is not None:
        dados = json.loads(existente["valor"])
        if any(dados.get(chave) != valor for chave, valor in esperado.items()):
            raise RuntimeError("Hipótese composta registrada com outra definição.")
        return dados
    fingerprint = fingerprint_vinculado_no_banco(
        conexao, regra_versao
    )
    if not fingerprint:
        raise RuntimeError("Regra sem linhagem vinculada para hipótese sombra.")
    dados = {
        **esperado,
        "regra_fingerprint": fingerprint,
        "iniciado_em": (
            iniciado_em or datetime.now()
        ).replace(microsecond=0).isoformat(),
        "evidencia_historica": evidencia_historica,
        "aplicacao_automatica": False,
    }
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                _chave(identificador),
                json.dumps(dados, ensure_ascii=False, sort_keys=True),
            ),
        )
    return dados


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _saldo_alvo_proximo_gol(linha, placar):
    """Deriva o saldo pelo ponto de vista do lado realmente selecionado."""
    gols = extrair_placar(placar)
    lado = str(linha or "").strip().casefold()
    if gols is None or lado not in ("casa", "visitante"):
        return None
    gols_casa, gols_visitante = gols
    if lado == "casa":
        return float(gols_casa - gols_visitante)
    return float(gols_visitante - gols_casa)


def _criterio_valido(criterio):
    return bool(
        isinstance(criterio, dict)
        and isinstance(criterio.get("feature"), str)
        and criterio.get("feature")
        and criterio.get("operador") in ("maior_igual", "menor_igual")
        and _numero(criterio.get("limiar")) is not None
    )


def _valor_feature(item, feature):
    if feature in ("pontuacao_tecnica", "odd", "linha"):
        return _numero(item.get(feature))
    valor = item.get("features") or {}
    for parte in str(feature).split("."):
        if not isinstance(valor, dict):
            return None
        valor = valor.get(parte)
    return _numero(valor)


def _atende_criterio(item, criterio):
    valor = _valor_feature(item, criterio["feature"])
    if valor is None:
        return False
    if criterio["operador"] == "maior_igual":
        return valor >= float(criterio["limiar"])
    return valor <= float(criterio["limiar"])


def _atende(item, hipotese):
    criterios = hipotese.get("criterios")
    if isinstance(criterios, list) and criterios:
        return all(_atende_criterio(item, item_criterio) for item_criterio in criterios)
    return _atende_criterio(item, hipotese)


def descrever_corte_hipotese(hipotese):
    criterios = hipotese.get("criterios")
    if isinstance(criterios, list) and criterios:
        return " E ".join(
            f"{item['feature']} {item['operador']} {float(item['limiar']):g}"
            for item in criterios
        )
    return (
        f"{hipotese.get('feature')} {hipotese.get('operador')} "
        f"{float(hipotese.get('limiar')):g}"
    )


def _intervalo_delta_media_95(amostra, controle):
    if len(amostra) < 2 or len(controle) < 2:
        return None
    media_amostra = statistics.mean(amostra)
    media_controle = statistics.mean(controle)
    variancia_amostra = statistics.variance(amostra)
    variancia_controle = statistics.variance(controle)
    erro = math.sqrt(
        variancia_amostra / len(amostra)
        + variancia_controle / len(controle)
    )
    margem = 1.96 * erro
    delta = media_amostra - media_controle
    return [round(delta - margem, 4), round(delta + margem, 4)]


def avaliar_hipotese_registros(hipotese, registros):
    independentes = {}
    pendentes = {}
    for item in sorted(
        registros,
        key=lambda registro: (
            registro.get("criado_em") or "",
            int(registro.get("sinal_id") or 0),
        ),
    ):
        chave = item.get("partida_id")
        if item.get("resultado") in RESULTADOS_VALIDOS:
            if chave not in independentes:
                independentes[chave] = item
            pendentes.pop(chave, None)
        elif chave not in independentes and chave not in pendentes:
            pendentes[chave] = item
    baseline = list(independentes.values())
    baseline_pendente = list(pendentes.values())
    selecionados = [
        item for item in baseline if _atende(item, hipotese)
    ]
    controle = [
        item for item in baseline if not _atende(item, hipotese)
    ]
    selecionados_pendentes = [
        item for item in baseline_pendente if _atende(item, hipotese)
    ]
    controle_pendente = [
        item for item in baseline_pendente if not _atende(item, hipotese)
    ]
    metricas_baseline = calcular_metricas(baseline)
    metricas_selecionadas = calcular_metricas(selecionados)
    metricas_controle = calcular_metricas(controle)
    minimo = int(hipotese.get("minimo_resultados", 30))
    minimo_controle = min(10, max(3, math.ceil(minimo / 3)))
    retornos_selecionados = [
        float(item.get("retorno_unidades") or 0)
        for item in selecionados
    ]
    retornos_controle = [
        float(item.get("retorno_unidades") or 0)
        for item in controle
    ]
    intervalo_delta_roi = _intervalo_delta_media_95(
        retornos_selecionados, retornos_controle
    )
    delta_roi = (
        round(
            statistics.mean(retornos_selecionados)
            - statistics.mean(retornos_controle),
            4,
        )
        if retornos_selecionados and retornos_controle else None
    )
    if len(selecionados) < minimo:
        estado = "aguardando_amostra"
        confirmada = None
    elif len(controle) < minimo_controle:
        estado = "aguardando_controle"
        confirmada = None
    else:
        roi = metricas_selecionadas.get("roi")
        confirmada = bool(
            roi is not None
            and roi > 0
            and intervalo_delta_roi is not None
            and intervalo_delta_roi[0] > 0
            and metricas_selecionadas.get("lucro_unidades", 0) > 0
        )
        estado = "confirmada" if confirmada else "refutada"
    return {
        "versao_avaliacao": VERSAO_AVALIACAO_HIPOTESES_SOMBRA,
        "identificador": hipotese["identificador"],
        "regra_versao": hipotese["regra_versao"],
        "mercado": hipotese["mercado"],
        "feature": hipotese.get("feature"),
        "operador": hipotese.get("operador"),
        "limiar": hipotese.get("limiar"),
        "criterios": hipotese.get("criterios"),
        "descricao_corte": descrever_corte_hipotese(hipotese),
        "iniciado_em": hipotese["iniciado_em"],
        "minimo_resultados": minimo,
        "aplicacao_automatica": False,
        "estado": estado,
        "confirmada": confirmada,
        "baseline": metricas_baseline,
        "selecionada": metricas_selecionadas,
        "controle_excluido": metricas_controle,
        "minimo_controle": minimo_controle,
        "delta_roi_selecionada_controle": delta_roi,
        "intervalo_delta_roi_95": intervalo_delta_roi,
        "faltam": max(0, minimo - len(selecionados)),
        "faltam_controle": max(0, minimo_controle - len(controle)),
        "pendentes_resultado": len(baseline_pendente),
        "pendentes_selecionados": len(selecionados_pendentes),
        "pendentes_controle": len(controle_pendente),
    }


def avaliar_hipoteses_sombra(conexao, regra_versao):
    integridade = auditar_hipoteses_sombra(conexao, regra_versao)
    avaliacoes = []
    for hipotese in listar_hipoteses_sombra(
        conexao, regra_versao
    ):
        if hipotese.get("identificador") in HIPOTESES_SOMBRA_DESCONTINUADAS:
            continue
        linhas = conexao.execute(
            """
            SELECT s.id AS sinal_id, s.partida_id, s.criado_em,
                   s.pontuacao_tecnica, s.odd, s.linha,
                   s.features_json, sp.placar AS placar_entrada,
                   r.resultado, r.retorno_unidades
            FROM sinais s
            JOIN snapshots sp ON sp.id=s.snapshot_id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.regra_versao=?
              AND s.regra_fingerprint=?
              AND s.mercado=?
              AND s.status='aprovado'
              AND datetime(s.criado_em) >= datetime(?)
            ORDER BY datetime(s.criado_em), s.id
            """,
            (
                hipotese["regra_versao"],
                hipotese["regra_fingerprint"],
                hipotese["mercado"],
                hipotese["iniciado_em"],
            ),
        ).fetchall()
        registros = []
        for linha in linhas:
            item = dict(linha)
            try:
                item["features"] = json.loads(
                    item.pop("features_json") or "{}"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                item["features"] = {}
            # Este contexto e derivado somente no avaliador sombra. A regra
            # ativa e sua linhagem permanecem intactas. O valor e sempre
            # recalculado do snapshot de entrada para nao confiar em feature
            # preexistente ou aplicar o corte retrospectivamente.
            item["features"].pop("saldo_alvo_proximo_gol", None)
            saldo_alvo = _saldo_alvo_proximo_gol(
                item.get("linha"), item.get("placar_entrada")
            )
            if saldo_alvo is not None:
                item["features"]["saldo_alvo_proximo_gol"] = saldo_alvo
            registros.append(item)
        avaliacoes.append(
            avaliar_hipotese_registros(hipotese, registros)
        )
    return {
        "versao": VERSAO_HIPOTESES_SOMBRA,
        "versao_avaliacao": VERSAO_AVALIACAO_HIPOTESES_SOMBRA,
        "regra_versao": regra_versao,
        "aplicacao_automatica": False,
        "integridade": integridade,
        "hipoteses_descontinuadas": sorted(
            HIPOTESES_SOMBRA_DESCONTINUADAS
        ),
        "avaliacoes": avaliacoes,
    }


def avaliar_hipoteses_sombra_ativas(conexao, regras_por_mercado):
    """Avalia uma vez cada linhagem ativa e audita todas as definições."""
    versoes = sorted(set((regras_por_mercado or {}).values()))
    avaliacoes = []
    por_regra = {}
    for regra_versao in versoes:
        parcial = avaliar_hipoteses_sombra(conexao, regra_versao)
        itens = list(parcial.get("avaliacoes") or [])
        por_regra[regra_versao] = itens
        avaliacoes.extend(itens)
    return {
        "versao": VERSAO_HIPOTESES_SOMBRA,
        "versao_avaliacao": VERSAO_AVALIACAO_HIPOTESES_SOMBRA,
        "regras_por_mercado": dict(regras_por_mercado or {}),
        "versoes_ativas": versoes,
        "aplicacao_automatica": False,
        "integridade": auditar_hipoteses_sombra(conexao),
        "hipoteses_descontinuadas": sorted(
            HIPOTESES_SOMBRA_DESCONTINUADAS
        ),
        "avaliacoes_por_regra": por_regra,
        "avaliacoes": avaliacoes,
    }
