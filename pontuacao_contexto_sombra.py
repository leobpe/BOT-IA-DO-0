"""Challenger prospectivo que combina sinal ao vivo e contexto API V4.

Este módulo não altera regras, filtros, calibração nem alertas. O modelo só é
congelado depois de uma amostra independente com contexto completo e toda a
avaliação usa sinais posteriores ao marco imutável persistido no SQLite.
"""

import hashlib
import json
import math
from datetime import datetime

from dataset_temporal import construir_dataset_temporal
from estatistica import discriminacao_pontuacao
from treino_processo_isolado import executar_treino_isolado


VERSAO_PONTUACAO_CONTEXTO_SOMBRA = (
    "pontuacao-contexto-sombra-logistica-v1"
)
VERSAO_REGIME_GOLS_SOMBRA = "regime-gols-contexto-logistica-v2"
VERSAO_AVALIACAO_PONTUACAO_CONTEXTO_SOMBRA = (
    "avaliacao-pontuacao-contexto-janela-fixa-v1"
)
VERSAO_CONTEXTO_EXIGIDA = "contexto-pre-jogo-v4"
ALGORITMO = "logistica-l2-batch-v1"
AMOSTRA_MINIMA_TREINO = 60
CLASSE_MINIMA_TREINO = 15
AMOSTRA_MINIMA_VALIDACAO = 30
MINIMO_FEATURES_CONTEXTO = 4
ITERACOES_TREINO = 800
TAXA_APRENDIZADO = 0.05
REGULARIZACAO_L2 = 0.30
LIMITE_Z = 5.0

FEATURES_BASE = (
    "pontuacao_tecnica",
    "odd",
    "minuto",
    "gols_atuais",
    "chutes_no_gol_total",
    "qualidade_dados",
    "j5_chutes_total",
    "j5_escanteios_total",
    "j5_pressao_pico_max",
)

FEATURES_GOLS = FEATURES_BASE + (
    "api_forma_ppg_total",
    "api_forma_ppg_diferenca_abs",
    "api_h2h_media_gols",
    "api_temporada_gols_media_total",
    "api_historico_gols_media_total",
    "api_historico_xg_media_total",
    "api_live_xg_total",
    "api_live_chutes_no_gol_total",
    "api_odds_pre_gols_linha",
    "api_odds_pre_gols_prob_over",
    "api_escalacoes_confirmadas",
    "api_desfalques_total",
)

FEATURES_ESCANTEIOS = FEATURES_BASE + (
    "api_forma_ppg_total",
    "api_historico_escanteios_media_total",
    "api_live_escanteios_total",
    "api_live_chutes_total",
    "api_live_chutes_no_gol_total",
    "api_odds_pre_escanteios_linha",
    "api_odds_pre_escanteios_prob_over",
    "api_escalacoes_confirmadas",
    "api_desfalques_total",
)

MERCADOS_GOLS = frozenset({"gol_ft", "gol_ht", "proximo_gol"})
MERCADOS_REGIME_GOLS = frozenset({"gol_ft", "gol_ht"})
MERCADOS_ESCANTEIOS = frozenset({
    "proximo_escanteio",
    "escanteios_ft_asiatico",
    "escanteios_1t",
    "escanteios_2t",
})


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _obter(dados, *caminho):
    atual = dados
    for chave in caminho:
        if not isinstance(atual, dict):
            return None
        atual = atual.get(chave)
    return atual


def _somar_par(valor_a, valor_b):
    """Soma somente quando os dois lados da partida são conhecidos."""
    valor_a = _numero(valor_a)
    valor_b = _numero(valor_b)
    if valor_a is None or valor_b is None:
        return None
    return valor_a + valor_b


def _somar_itens_dict(dados, campo, conversor=_numero, minimo_itens=2):
    itens = [
        item for item in (dados or {}).values()
        if isinstance(item, dict)
    ]
    if len(itens) < minimo_itens:
        return None
    valores = [conversor(item.get(campo)) for item in itens]
    if any(valor is None for valor in valores):
        return None
    return sum(valores)


def _diferenca_absoluta(valor_a, valor_b):
    valor_a = _numero(valor_a)
    valor_b = _numero(valor_b)
    if valor_a is None or valor_b is None:
        return None
    return abs(valor_a - valor_b)


def features_para_mercado(mercado):
    if mercado in MERCADOS_GOLS:
        return FEATURES_GOLS
    if mercado in MERCADOS_ESCANTEIOS:
        return FEATURES_ESCANTEIOS
    raise ValueError(f"mercado_contexto_nao_suportado:{mercado}")


def versao_modelo_para_mercado(mercado):
    if mercado in MERCADOS_REGIME_GOLS:
        return VERSAO_REGIME_GOLS_SOMBRA
    return VERSAO_PONTUACAO_CONTEXTO_SOMBRA


def _extrair_features_contexto(contexto):
    forma_casa = _obter(
        contexto, "forma_recente", "mandante", "pontos_por_jogo"
    )
    forma_fora = _obter(
        contexto, "forma_recente", "visitante", "pontos_por_jogo"
    )
    temporada_casa = _obter(
        contexto, "estatisticas_temporada", "mandante"
    ) or {}
    temporada_fora = _obter(
        contexto, "estatisticas_temporada", "visitante"
    ) or {}
    historico_casa = _obter(
        contexto, "historico_detalhado", "mandante"
    ) or {}
    historico_fora = _obter(
        contexto, "historico_detalhado", "visitante"
    ) or {}
    live_casa = _obter(
        contexto, "estatisticas_ao_vivo", "times", "mandante"
    ) or {}
    live_fora = _obter(
        contexto, "estatisticas_ao_vivo", "times", "visitante"
    ) or {}
    odds_gols = _obter(
        contexto, "odds_pre_jogo", "mercados", "gols_ft"
    ) or {}
    odds_escanteios = _obter(
        contexto, "odds_pre_jogo", "mercados", "escanteios_ft"
    ) or {}
    escalacoes = contexto.get("escalacoes") or {}
    desfalques = contexto.get("desfalques") or {}
    return {
        "api_forma_ppg_total": _somar_par(forma_casa, forma_fora),
        "api_forma_ppg_diferenca_abs": _diferenca_absoluta(
            forma_casa, forma_fora
        ),
        "api_h2h_media_gols": _numero(
            _obter(contexto, "confrontos_diretos", "media_gols")
        ),
        "api_temporada_gols_media_total": _somar_par(
            temporada_casa.get("gols_pro_media"),
            temporada_fora.get("gols_pro_media"),
        ),
        "api_historico_gols_media_total": _somar_par(
            historico_casa.get("gols_pro_media"),
            historico_fora.get("gols_pro_media"),
        ),
        "api_historico_xg_media_total": _somar_par(
            historico_casa.get("xg_media"),
            historico_fora.get("xg_media"),
        ),
        "api_historico_escanteios_media_total": _somar_par(
            historico_casa.get("escanteios_media"),
            historico_fora.get("escanteios_media"),
        ),
        "api_live_xg_total": _somar_par(
            live_casa.get("xg"), live_fora.get("xg")
        ),
        "api_live_chutes_total": _somar_par(
            live_casa.get("chutes"), live_fora.get("chutes")
        ),
        "api_live_chutes_no_gol_total": _somar_par(
            live_casa.get("chutes_no_gol"),
            live_fora.get("chutes_no_gol"),
        ),
        "api_live_escanteios_total": _somar_par(
            live_casa.get("escanteios"),
            live_fora.get("escanteios"),
        ),
        "api_odds_pre_gols_linha": _numero(
            odds_gols.get("linha_consenso")
            if odds_gols.get("consenso_suficiente") else None
        ),
        "api_odds_pre_gols_prob_over": _numero(
            odds_gols.get("probabilidade_over_sem_margem")
            if odds_gols.get("consenso_suficiente") else None
        ),
        "api_odds_pre_escanteios_linha": _numero(
            odds_escanteios.get("linha_consenso")
            if odds_escanteios.get("consenso_suficiente") else None
        ),
        "api_odds_pre_escanteios_prob_over": _numero(
            odds_escanteios.get("probabilidade_over_sem_margem")
            if odds_escanteios.get("consenso_suficiente") else None
        ),
        "api_escalacoes_confirmadas": _somar_itens_dict(
            escalacoes,
            "confirmada",
            conversor=(
                lambda valor: (
                    int(valor) if isinstance(valor, bool) else None
                )
            ),
        ),
        "api_desfalques_total": _somar_itens_dict(
            desfalques,
            "total",
        ),
    }


def _carregar_contextos(conexao, snapshot_ids):
    contextos = {}
    ids = sorted({int(item) for item in snapshot_ids if item is not None})
    for inicio in range(0, len(ids), 500):
        lote = ids[inicio:inicio + 500]
        marcadores = ",".join("?" for _ in lote)
        linhas = conexao.execute(
            f"""
            SELECT id, contexto_api_json
            FROM snapshots
            WHERE id IN ({marcadores})
            """,
            lote,
        ).fetchall()
        for linha in linhas:
            try:
                contexto = json.loads(linha["contexto_api_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                contexto = {}
            contextos[int(linha["id"])] = (
                contexto if isinstance(contexto, dict) else {}
            )
    return contextos


def construir_dataset_contexto(conexao, mercado, regra_versao):
    features_modelo = features_para_mercado(mercado)
    base = construir_dataset_temporal(
        conexao, mercado, regra_versao=regra_versao
    )
    contextos = _carregar_contextos(
        conexao,
        [item.get("snapshot_id") for item in base["registros"]],
    )
    registros = []
    excluidos = {
        "sem_contexto_v4": 0,
        "contexto_insuficiente": 0,
    }
    features_contexto = set(features_modelo) - set(FEATURES_BASE)
    for item in base["registros"]:
        contexto = contextos.get(int(item["snapshot_id"])) or {}
        if (
            contexto.get("versao") != VERSAO_CONTEXTO_EXIGIDA
            or contexto.get("modo") != "sombra"
            or not contexto.get("fixture_id")
        ):
            excluidos["sem_contexto_v4"] += 1
            continue
        extraidas = _extrair_features_contexto(contexto)
        presentes = sum(
            extraidas.get(nome) is not None
            for nome in features_contexto
        )
        if presentes < MINIMO_FEATURES_CONTEXTO:
            excluidos["contexto_insuficiente"] += 1
            continue
        enriquecido = dict(item)
        enriquecido["features"] = {
            **(item.get("features") or {}),
            **extraidas,
        }
        enriquecido["features_contexto_presentes"] = presentes
        registros.append(enriquecido)
    payload = [{
        "sinal_id": int(item["sinal_id"]),
        "snapshot_id": int(item["snapshot_id"]),
        "resultado": item["resultado"],
        "features": {
            nome: _valor_feature(item, nome)
            for nome in features_modelo
        },
    } for item in registros]
    serializado = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    cobertura_features = {
        nome: sum(
            _valor_feature(item, nome) is not None
            for item in registros
        )
        for nome in features_modelo
    }
    return {
        "versao": versao_modelo_para_mercado(mercado),
        "contexto_versao": VERSAO_CONTEXTO_EXIGIDA,
        "mercado": mercado,
        "regra_versao": regra_versao,
        "registros": registros,
        "total_base": len(base["registros"]),
        "excluidos": excluidos,
        "cobertura_features": cobertura_features,
        "fingerprint": hashlib.sha256(
            serializado.encode("utf-8")
        ).hexdigest(),
    }


def _valor_feature(item, nome):
    if nome in ("pontuacao_tecnica", "odd"):
        return _numero(item.get(nome))
    return _numero((item.get("features") or {}).get(nome))


def _sigmoide(valor):
    if valor >= 0:
        exponencial = math.exp(-min(valor, 60.0))
        return 1.0 / (1.0 + exponencial)
    exponencial = math.exp(max(valor, -60.0))
    return exponencial / (1.0 + exponencial)


def _produto_escalar_seguro(pesos, linha):
    """Calcula o logit sem depender de iteradores temporários aninhados."""
    if not isinstance(pesos, (list, tuple)) or not isinstance(
        linha, (list, tuple)
    ):
        raise ValueError("vetor_treino_contextual_invalido")
    if len(pesos) != len(linha):
        raise ValueError("dimensao_treino_contextual_invalida")
    total = 0.0
    indice = 0
    while indice < len(pesos):
        total += pesos[indice] * linha[indice]
        indice += 1
    return total


def _configuracao_modelo(mercado):
    return {
        "versao": versao_modelo_para_mercado(mercado),
        "contexto_versao": VERSAO_CONTEXTO_EXIGIDA,
        "algoritmo": ALGORITMO,
        "features": list(features_para_mercado(mercado)),
        "iteracoes": ITERACOES_TREINO,
        "taxa_aprendizado": TAXA_APRENDIZADO,
        "regularizacao_l2": REGULARIZACAO_L2,
        "limite_z": LIMITE_Z,
        "amostra_minima_treino": AMOSTRA_MINIMA_TREINO,
        "classe_minima_treino": CLASSE_MINIMA_TREINO,
        "amostra_minima_validacao": AMOSTRA_MINIMA_VALIDACAO,
        "minimo_features_contexto": MINIMO_FEATURES_CONTEXTO,
        "politica_totais": "duas_equipes_obrigatorias-v1",
    }


def fingerprint_configuracao(mercado):
    serializado = json.dumps(
        _configuracao_modelo(mercado),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _ajustar_modelo_impl(registros, mercado):
    features = features_para_mercado(mercado)
    if len(registros) < AMOSTRA_MINIMA_TREINO:
        raise ValueError("amostra_treino_insuficiente")
    # Este nucleo evita compreensoes com closures. Em CPython 3.13/3.14 no
    # Windows, a celula criada pela variancia geradora podia vazar
    # intermitentemente para slots locais depois de muitas repeticoes.
    alvos = []
    indice_registro = 0
    while indice_registro < len(registros):
        alvos.append(
            int(bool(registros[indice_registro].get("alvo_green")))
        )
        indice_registro += 1
    if (
        sum(alvos) < CLASSE_MINIMA_TREINO
        or len(alvos) - sum(alvos) < CLASSE_MINIMA_TREINO
    ):
        raise ValueError("classes_treino_insuficientes")
    medias = {}
    desvios = {}
    indice_nome = 0
    while indice_nome < len(features):
        nome = features[indice_nome]
        valores = []
        indice_registro = 0
        while indice_registro < len(registros):
            valor = _valor_feature(registros[indice_registro], nome)
            if valor is not None:
                valores.append(valor)
            indice_registro += 1
        if not valores:
            raise ValueError(f"feature_sem_dados:{nome}")
        media = sum(valores) / len(valores)
        soma_quadrados = 0.0
        indice_valor = 0
        while indice_valor < len(valores):
            soma_quadrados += (valores[indice_valor] - media) ** 2
            indice_valor += 1
        variancia = soma_quadrados / len(valores)
        medias[nome] = media
        desvios[nome] = math.sqrt(variancia) or 1.0
        indice_nome += 1
    matriz = []
    indice_registro = 0
    while indice_registro < len(registros):
        item = registros[indice_registro]
        linha = []
        indice_nome = 0
        while indice_nome < len(features):
            nome = features[indice_nome]
            valor = _valor_feature(item, nome)
            if valor is None:
                valor = medias[nome]
            z = (valor - medias[nome]) / desvios[nome]
            linha.append(max(-LIMITE_Z, min(LIMITE_Z, z)))
            indice_nome += 1
        matriz.append(linha)
        indice_registro += 1
    quantidade = len(matriz)
    pesos = [0.0] * len(features)
    proporcao = sum(alvos) / quantidade
    intercepto = math.log(proporcao / (1.0 - proporcao))
    # O treinamento e deliberadamente indexado. Em Python 3.14 no Windows,
    # execucoes longas da regressao ja apresentaram falhas transitorias na
    # especializacao de iteradores aninhados (zip/enumerate). O laco indexado
    # preserva exatamente a ordem numerica e elimina essa dependencia.
    iteracao = 0
    while iteracao < ITERACOES_TREINO:
        gradiente_intercepto = 0.0
        gradientes = [0.0] * len(pesos)
        indice_amostra = 0
        while indice_amostra < quantidade:
            linha = matriz[indice_amostra]
            alvo = alvos[indice_amostra]
            logit = intercepto + _produto_escalar_seguro(pesos, linha)
            erro = _sigmoide(logit) - alvo
            gradiente_intercepto += erro
            indice_feature = 0
            while indice_feature < len(linha):
                gradientes[indice_feature] += (
                    erro * linha[indice_feature]
                )
                indice_feature += 1
            indice_amostra += 1
        intercepto -= TAXA_APRENDIZADO * (
            gradiente_intercepto / quantidade
        )
        indice_peso = 0
        while indice_peso < len(pesos):
            gradiente = (
                gradientes[indice_peso] / quantidade
                + REGULARIZACAO_L2 * pesos[indice_peso]
            )
            pesos[indice_peso] -= TAXA_APRENDIZADO * gradiente
            indice_peso += 1
        iteracao += 1
    pesos_por_nome = {}
    medias_por_nome = {}
    desvios_por_nome = {}
    indice_nome = 0
    while indice_nome < len(features):
        nome = features[indice_nome]
        pesos_por_nome[nome] = round(pesos[indice_nome], 12)
        medias_por_nome[nome] = round(medias[nome], 12)
        desvios_por_nome[nome] = round(desvios[nome], 12)
        indice_nome += 1
    return {
        "versao": versao_modelo_para_mercado(mercado),
        "algoritmo": ALGORITMO,
        "mercado": mercado,
        "configuracao_fingerprint": fingerprint_configuracao(mercado),
        "features": list(features),
        "intercepto": round(intercepto, 12),
        "pesos": pesos_por_nome,
        "medias": medias_por_nome,
        "desvios": desvios_por_nome,
        "amostra_treino": len(registros),
        "greens_treino": sum(alvos),
        "reds_treino": len(alvos) - sum(alvos),
    }


def ajustar_modelo(registros, mercado):
    """Treina em processo descartavel, com timeout, repeticao e validacao."""
    return executar_treino_isolado(
        "pontuacao_contexto",
        {"registros": registros, "mercado": mercado},
        validar_modelo=lambda modelo: bool(
            modelo_compativel(modelo, mercado)
            and modelo.get("amostra_treino") == len(registros)
        ),
        erros_dominio_exatos=(
            "amostra_treino_insuficiente",
            "classes_treino_insuficientes",
        ),
        erros_dominio_prefixos=("feature_sem_dados:",),
    )


def modelo_compativel(modelo, mercado):
    features = features_para_mercado(mercado)
    return bool(
        isinstance(modelo, dict)
        and modelo.get("versao") == versao_modelo_para_mercado(mercado)
        and modelo.get("algoritmo") == ALGORITMO
        and modelo.get("mercado") == mercado
        and modelo.get("features") == list(features)
        and modelo.get("configuracao_fingerprint")
        == fingerprint_configuracao(mercado)
        and set(modelo.get("pesos") or {}) == set(features)
        and set(modelo.get("medias") or {}) == set(features)
        and set(modelo.get("desvios") or {}) == set(features)
    )


def prever(modelo, item, mercado):
    if not modelo_compativel(modelo, mercado):
        raise ValueError("modelo_contexto_sombra_incompativel")
    logit = float(modelo["intercepto"])
    for nome in features_para_mercado(mercado):
        valor = _valor_feature(item, nome)
        if valor is None:
            valor = float(modelo["medias"][nome])
        desvio = float(modelo["desvios"][nome]) or 1.0
        z = (valor - float(modelo["medias"][nome])) / desvio
        z = max(-LIMITE_Z, min(LIMITE_Z, z))
        logit += float(modelo["pesos"][nome]) * z
    return round(_sigmoide(logit), 8)


def _chave_modelo(mercado, regra_versao):
    return (
        f"pontuacao_sombra:{versao_modelo_para_mercado(mercado)}:"
        f"{regra_versao}:{mercado}"
    )


def carregar_modelo(conexao, mercado, regra_versao):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (_chave_modelo(mercado, regra_versao),),
    ).fetchone()
    if linha is None:
        return None
    try:
        envelope = json.loads(linha[0])
    except (TypeError, json.JSONDecodeError):
        return {"integro": False, "motivo": "modelo_json_invalido"}
    modelo = envelope.get("modelo")
    serializado = json.dumps(
        modelo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    hash_observado = hashlib.sha256(
        serializado.encode("utf-8")
    ).hexdigest()
    integro = bool(
        envelope.get("modelo_hash") == hash_observado
        and modelo_compativel(modelo, mercado)
        and envelope.get("mercado") == mercado
        and envelope.get("regra_versao") == regra_versao
    )
    return {
        **envelope,
        "integro": integro,
        "motivo": None if integro else "modelo_incompativel_ou_corrompido",
    }


def registrar_ou_obter_modelo(
    conexao, mercado, regra_versao, registrado_em=None
):
    existente = carregar_modelo(conexao, mercado, regra_versao)
    if existente is not None:
        return {"criado": False, **existente}
    dataset = construir_dataset_contexto(
        conexao, mercado, regra_versao
    )
    registros = dataset["registros"]
    greens = sum(int(bool(item.get("alvo_green"))) for item in registros)
    reds = len(registros) - greens
    faltam_amostra = max(AMOSTRA_MINIMA_TREINO - len(registros), 0)
    faltam_classe = max(
        CLASSE_MINIMA_TREINO - min(greens, reds), 0
    )
    if faltam_amostra or faltam_classe:
        return {
            "criado": False,
            "integro": True,
            "estado": "aguardando_treino",
            "mercado": mercado,
            "regra_versao": regra_versao,
            "amostra_disponivel": len(registros),
            "greens_disponiveis": greens,
            "reds_disponiveis": reds,
            "faltam_amostra": faltam_amostra,
            "faltam_classe": faltam_classe,
            "excluidos": dataset["excluidos"],
        }
    modelo = ajustar_modelo(registros, mercado)
    modelo_json = json.dumps(
        modelo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    envelope = {
        "versao": versao_modelo_para_mercado(mercado),
        "mercado": mercado,
        "regra_versao": regra_versao,
        "registrado_em": (
            registrado_em
            or datetime.now().replace(microsecond=0).isoformat()
        ),
        "treino_ate_sinal_id": max(
            int(item["sinal_id"]) for item in registros
        ),
        "treino_fingerprint": dataset["fingerprint"],
        "modelo_hash": hashlib.sha256(
            modelo_json.encode("utf-8")
        ).hexdigest(),
        "modelo": modelo,
    }
    cursor = conexao.execute(
        "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
        (
            _chave_modelo(mercado, regra_versao),
            json.dumps(
                envelope,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    carregado = carregar_modelo(conexao, mercado, regra_versao)
    return {
        "criado": bool(cursor.rowcount),
        **(carregado or {
            "integro": False,
            "motivo": "modelo_nao_persistido",
        }),
    }


def _brier(itens, campo):
    if not itens:
        return None
    return round(sum(
        (float(item[campo]) - int(item["alvo_green"])) ** 2
        for item in itens
    ) / len(itens), 6)


def avaliar_modelo(conexao, mercado, regra_versao):
    dataset = construir_dataset_contexto(
        conexao, mercado, regra_versao
    )
    envelope = carregar_modelo(conexao, mercado, regra_versao)
    base = {
        "versao": versao_modelo_para_mercado(mercado),
        "avaliacao_versao": (
            VERSAO_AVALIACAO_PONTUACAO_CONTEXTO_SOMBRA
        ),
        "contexto_versao": VERSAO_CONTEXTO_EXIGIDA,
        "mercado": mercado,
        "regra_versao": regra_versao,
        "modo": "sombra",
        "aplicacao_automatica": False,
        "amostra_total": len(dataset["registros"]),
        "amostra_base": dataset["total_base"],
        "excluidos": dataset["excluidos"],
        "cobertura_features": dataset["cobertura_features"],
        "amostra_minima_treino": AMOSTRA_MINIMA_TREINO,
        "classe_minima_treino": CLASSE_MINIMA_TREINO,
        "amostra_minima_validacao": AMOSTRA_MINIMA_VALIDACAO,
    }
    if envelope is None:
        greens = sum(
            int(bool(item.get("alvo_green")))
            for item in dataset["registros"]
        )
        reds = len(dataset["registros"]) - greens
        return {
            **base,
            "estado": "aguardando_treino",
            "integro": True,
            "greens": greens,
            "reds": reds,
            "faltam_treino": max(
                AMOSTRA_MINIMA_TREINO - len(dataset["registros"]), 0
            ),
            "faltam_classe": max(
                CLASSE_MINIMA_TREINO - min(greens, reds), 0
            ),
            "validacao": 0,
        }
    if not envelope.get("integro"):
        return {
            **base,
            "estado": "modelo_invalido",
            "integro": False,
            "motivo": envelope.get("motivo"),
            "validacao": 0,
        }
    ancora = int(envelope["treino_ate_sinal_id"])
    validacao_disponivel = sorted([
        item for item in dataset["registros"]
        if int(item["sinal_id"]) > ancora
    ], key=lambda item: int(item["sinal_id"]))
    validacao = validacao_disponivel[:AMOSTRA_MINIMA_VALIDACAO]
    avaliados = []
    for item in validacao:
        avaliados.append({
            **item,
            "probabilidade_contexto": prever(
                envelope["modelo"], item, mercado
            ),
            "probabilidade_implicita_odd": round(
                1.0 / float(item["odd"]), 8
            ),
        })
    auc_contexto = discriminacao_pontuacao([{
        "resultado": item["resultado"],
        "pontuacao_tecnica": item["probabilidade_contexto"],
    } for item in avaliados])
    auc_atual = discriminacao_pontuacao([{
        "resultado": item["resultado"],
        "pontuacao_tecnica": item["pontuacao_tecnica"],
    } for item in avaliados])
    brier_contexto = _brier(avaliados, "probabilidade_contexto")
    brier_odd = _brier(avaliados, "probabilidade_implicita_odd")
    quantidade = len(avaliados)
    validacao_fingerprint = hashlib.sha256(json.dumps(
        [
            [int(item["sinal_id"]), str(item["resultado"])]
            for item in avaliados
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if quantidade < AMOSTRA_MINIMA_VALIDACAO:
        estado = "aguardando_validacao"
    elif (
        auc_contexto.get("limite_inferior_auc_95") is not None
        and auc_contexto["limite_inferior_auc_95"] > 0.5
        and (
            auc_atual.get("auc") is None
            or auc_contexto["auc"] >= auc_atual["auc"] + 0.05
        )
        and brier_contexto is not None
        and brier_odd is not None
        and brier_contexto <= brier_odd
    ):
        estado = "favoravel_para_revisao"
    elif (
        auc_contexto.get("intervalo_auc_95")
        and auc_contexto["intervalo_auc_95"][1] < 0.5
    ):
        estado = "contraria"
    else:
        estado = "inconclusiva"
    return {
        **base,
        "estado": estado,
        "integro": True,
        "registrado_em": envelope["registrado_em"],
        "treino": int(envelope["modelo"]["amostra_treino"]),
        "treino_ate_sinal_id": ancora,
        "validacao": quantidade,
        "validacao_total_disponivel": len(validacao_disponivel),
        "validacao_congelada": (
            quantidade >= AMOSTRA_MINIMA_VALIDACAO
        ),
        "validacao_fingerprint": validacao_fingerprint,
        "faltam_validacao": max(
            AMOSTRA_MINIMA_VALIDACAO - quantidade, 0
        ),
        "ultimo_sinal_validacao_id": (
            max(int(item["sinal_id"]) for item in avaliados)
            if avaliados else None
        ),
        "auc_contexto": auc_contexto,
        "auc_nota_atual": auc_atual,
        "brier_contexto": brier_contexto,
        "brier_odd": brier_odd,
        "pronto_para_revisao": estado == "favoravel_para_revisao",
    }


def avaliar_pontuacao_contexto_sombra(conexao, regras_por_mercado):
    por_mercado = {
        mercado: avaliar_modelo(conexao, mercado, regra_versao)
        for mercado, regra_versao in sorted(
            (regras_por_mercado or {}).items()
        )
    }
    return {
        "versao": VERSAO_PONTUACAO_CONTEXTO_SOMBRA,
        "contexto_versao": VERSAO_CONTEXTO_EXIGIDA,
        "modo": "sombra",
        "aplicacao_automatica": False,
        "integro": all(
            item.get("integro", False) for item in por_mercado.values()
        ),
        "por_mercado": por_mercado,
        "mercados_com_modelo": [
            mercado for mercado, item in por_mercado.items()
            if item.get("treino") is not None
        ],
        "mercados_prontos_para_revisao": [
            mercado for mercado, item in por_mercado.items()
            if item.get("pronto_para_revisao")
        ],
    }


def registrar_modelos_pontuacao_contexto_sombra(
    conexao, regras_por_mercado, registrado_em=None
):
    resultados = {}
    for mercado, regra_versao in sorted(
        (regras_por_mercado or {}).items()
    ):
        resultados[mercado] = registrar_ou_obter_modelo(
            conexao,
            mercado,
            regra_versao,
            registrado_em=registrado_em,
        )
    return {
        "criados": sum(
            bool(item.get("criado")) for item in resultados.values()
        ),
        "integro": all(
            item.get("integro", False) for item in resultados.values()
        ),
        "por_mercado": resultados,
    }
