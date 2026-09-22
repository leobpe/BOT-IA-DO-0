import hashlib
import json
import math
from datetime import datetime

from dataset_temporal import construir_dataset_temporal
from estatistica import discriminacao_pontuacao


VERSAO_PONTUACAO_SOMBRA = "pontuacao-sombra-logistica-v1"
VERSAO_AVALIACAO_PONTUACAO_SOMBRA = (
    "avaliacao-pontuacao-sombra-janela-fixa-v2"
)
ALGORITMO_PONTUACAO_SOMBRA = "logistica-l2-batch-v1"
AMOSTRA_MINIMA_TREINO = 60
AMOSTRA_MINIMA_VALIDACAO = 30
ITERACOES_TREINO = 800
TAXA_APRENDIZADO = 0.05
REGULARIZACAO_L2 = 0.20
LIMITE_Z = 5.0
FEATURES_PONTUACAO_SOMBRA = (
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


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


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


def _configuracao_modelo():
    return {
        "versao": VERSAO_PONTUACAO_SOMBRA,
        "algoritmo": ALGORITMO_PONTUACAO_SOMBRA,
        "features": list(FEATURES_PONTUACAO_SOMBRA),
        "iteracoes": ITERACOES_TREINO,
        "taxa_aprendizado": TAXA_APRENDIZADO,
        "regularizacao_l2": REGULARIZACAO_L2,
        "limite_z": LIMITE_Z,
        "amostra_minima_treino": AMOSTRA_MINIMA_TREINO,
        "amostra_minima_validacao": AMOSTRA_MINIMA_VALIDACAO,
    }


def fingerprint_configuracao_pontuacao_sombra():
    serializado = json.dumps(
        _configuracao_modelo(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _preparar_treino(registros):
    medias = {}
    desvios = {}
    for nome in FEATURES_PONTUACAO_SOMBRA:
        valores = [
            _valor_feature(item, nome)
            for item in registros
        ]
        valores = [valor for valor in valores if valor is not None]
        if not valores:
            raise ValueError(f"feature_sem_dados:{nome}")
        media = sum(valores) / len(valores)
        variancia = sum((valor - media) ** 2 for valor in valores) / len(
            valores
        )
        medias[nome] = media
        desvios[nome] = math.sqrt(variancia) or 1.0
    matriz = []
    alvos = []
    for item in registros:
        linha = []
        for nome in FEATURES_PONTUACAO_SOMBRA:
            valor = _valor_feature(item, nome)
            if valor is None:
                valor = medias[nome]
            z = (valor - medias[nome]) / desvios[nome]
            linha.append(max(-LIMITE_Z, min(LIMITE_Z, z)))
        matriz.append(linha)
        alvos.append(int(bool(item.get("alvo_green"))))
    return matriz, alvos, medias, desvios


def ajustar_modelo_pontuacao_sombra(registros):
    if len(registros) < AMOSTRA_MINIMA_TREINO:
        raise ValueError("amostra_treino_insuficiente")
    matriz, alvos, medias, desvios = _preparar_treino(registros)
    if not any(alvos) or all(alvos):
        raise ValueError("classes_treino_insuficientes")
    quantidade = len(matriz)
    pesos = [0.0] * len(FEATURES_PONTUACAO_SOMBRA)
    proporcao = min(max(sum(alvos) / quantidade, 1e-6), 1 - 1e-6)
    intercepto = math.log(proporcao / (1.0 - proporcao))
    for _ in range(ITERACOES_TREINO):
        gradiente_intercepto = 0.0
        gradientes = [0.0] * len(pesos)
        for linha, alvo in zip(matriz, alvos):
            logit = intercepto + sum(
                peso * valor for peso, valor in zip(pesos, linha)
            )
            erro = _sigmoide(logit) - alvo
            gradiente_intercepto += erro
            for indice, valor in enumerate(linha):
                gradientes[indice] += erro * valor
        intercepto -= TAXA_APRENDIZADO * (
            gradiente_intercepto / quantidade
        )
        for indice in range(len(pesos)):
            gradiente = (
                gradientes[indice] / quantidade
                + REGULARIZACAO_L2 * pesos[indice]
            )
            pesos[indice] -= TAXA_APRENDIZADO * gradiente
    return {
        "versao": VERSAO_PONTUACAO_SOMBRA,
        "algoritmo": ALGORITMO_PONTUACAO_SOMBRA,
        "configuracao_fingerprint": (
            fingerprint_configuracao_pontuacao_sombra()
        ),
        "features": list(FEATURES_PONTUACAO_SOMBRA),
        "intercepto": round(intercepto, 12),
        "pesos": {
            nome: round(peso, 12)
            for nome, peso in zip(FEATURES_PONTUACAO_SOMBRA, pesos)
        },
        "medias": {
            nome: round(medias[nome], 12)
            for nome in FEATURES_PONTUACAO_SOMBRA
        },
        "desvios": {
            nome: round(desvios[nome], 12)
            for nome in FEATURES_PONTUACAO_SOMBRA
        },
        "amostra_treino": len(registros),
        "greens_treino": sum(alvos),
        "reds_treino": len(alvos) - sum(alvos),
    }


def modelo_pontuacao_sombra_compativel(modelo):
    if not isinstance(modelo, dict):
        return False
    return bool(
        modelo.get("versao") == VERSAO_PONTUACAO_SOMBRA
        and modelo.get("algoritmo") == ALGORITMO_PONTUACAO_SOMBRA
        and modelo.get("features") == list(FEATURES_PONTUACAO_SOMBRA)
        and modelo.get("configuracao_fingerprint")
        == fingerprint_configuracao_pontuacao_sombra()
        and set(modelo.get("pesos") or {}) == set(
            FEATURES_PONTUACAO_SOMBRA
        )
        and set(modelo.get("medias") or {}) == set(
            FEATURES_PONTUACAO_SOMBRA
        )
        and set(modelo.get("desvios") or {}) == set(
            FEATURES_PONTUACAO_SOMBRA
        )
    )


def prever_pontuacao_sombra(modelo, item):
    if not modelo_pontuacao_sombra_compativel(modelo):
        raise ValueError("modelo_pontuacao_sombra_incompativel")
    logit = float(modelo["intercepto"])
    for nome in FEATURES_PONTUACAO_SOMBRA:
        valor = _valor_feature(item, nome)
        if valor is None:
            valor = float(modelo["medias"][nome])
        desvio = float(modelo["desvios"][nome]) or 1.0
        z = (valor - float(modelo["medias"][nome])) / desvio
        z = max(-LIMITE_Z, min(LIMITE_Z, z))
        logit += float(modelo["pesos"][nome]) * z
    return round(_sigmoide(logit), 8)


def _fingerprint_treino(registros):
    payload = [
        {
            "sinal_id": int(item["sinal_id"]),
            "resultado": item["resultado"],
            "features": {
                nome: _valor_feature(item, nome)
                for nome in FEATURES_PONTUACAO_SOMBRA
            },
        }
        for item in registros
    ]
    serializado = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _chave_modelo(mercado, regra_versao):
    return (
        f"pontuacao_sombra:{VERSAO_PONTUACAO_SOMBRA}:"
        f"{regra_versao}:{mercado}"
    )


def carregar_modelo_pontuacao_sombra(conexao, mercado, regra_versao):
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
    hash_esperado = envelope.get("modelo_hash")
    serializado = json.dumps(
        modelo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    hash_observado = hashlib.sha256(serializado.encode("utf-8")).hexdigest()
    integro = bool(
        hash_esperado == hash_observado
        and modelo_pontuacao_sombra_compativel(modelo)
        and envelope.get("mercado") == mercado
        and envelope.get("regra_versao") == regra_versao
    )
    return {
        **envelope,
        "integro": integro,
        "motivo": None if integro else "modelo_incompativel_ou_corrompido",
    }


def registrar_ou_obter_modelo_pontuacao_sombra(
    conexao,
    mercado,
    regra_versao,
    registrado_em=None,
):
    existente = carregar_modelo_pontuacao_sombra(
        conexao, mercado, regra_versao
    )
    if existente is not None:
        return {"criado": False, **existente}
    dataset = construir_dataset_temporal(
        conexao, mercado, regra_versao=regra_versao
    )
    registros = dataset["registros"]
    if len(registros) < AMOSTRA_MINIMA_TREINO:
        return {
            "criado": False,
            "integro": True,
            "estado": "aguardando_treino",
            "mercado": mercado,
            "regra_versao": regra_versao,
            "amostra_disponivel": len(registros),
            "faltam": AMOSTRA_MINIMA_TREINO - len(registros),
        }
    modelo = ajustar_modelo_pontuacao_sombra(registros)
    modelo_json = json.dumps(
        modelo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    envelope = {
        "versao": VERSAO_PONTUACAO_SOMBRA,
        "mercado": mercado,
        "regra_versao": regra_versao,
        "registrado_em": (
            registrado_em
            or datetime.now().replace(microsecond=0).isoformat()
        ),
        "treino_ate_sinal_id": max(
            int(item["sinal_id"]) for item in registros
        ),
        "treino_fingerprint": _fingerprint_treino(registros),
        "dataset_fingerprint_no_registro": dataset["fingerprint"],
        "modelo_hash": hashlib.sha256(
            modelo_json.encode("utf-8")
        ).hexdigest(),
        "modelo": modelo,
    }
    cursor = conexao.execute(
        """
        INSERT OR IGNORE INTO metadados (chave, valor)
        VALUES (?, ?)
        """,
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
    carregado = carregar_modelo_pontuacao_sombra(
        conexao, mercado, regra_versao
    )
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


def avaliar_modelo_pontuacao_sombra(
    conexao,
    mercado,
    regra_versao,
):
    dataset = construir_dataset_temporal(
        conexao, mercado, regra_versao=regra_versao
    )
    envelope = carregar_modelo_pontuacao_sombra(
        conexao, mercado, regra_versao
    )
    base = {
        "versao": VERSAO_PONTUACAO_SOMBRA,
        "avaliacao_versao": VERSAO_AVALIACAO_PONTUACAO_SOMBRA,
        "mercado": mercado,
        "regra_versao": regra_versao,
        "modo": "sombra",
        "aplicacao_automatica": False,
        "amostra_total": len(dataset["registros"]),
        "amostra_minima_treino": AMOSTRA_MINIMA_TREINO,
        "amostra_minima_validacao": AMOSTRA_MINIMA_VALIDACAO,
        "criterios_revisao": {
            "limite_inferior_auc_95_maior_que": 0.5,
            "melhora_auc_minima": 0.05,
            "brier_nao_pior_que_odd": True,
        },
    }
    if envelope is None:
        faltam = max(
            AMOSTRA_MINIMA_TREINO - len(dataset["registros"]), 0
        )
        return {
            **base,
            "estado": (
                "aguardando_treino" if faltam
                else "aguardando_registro_modelo"
            ),
            "integro": True,
            "faltam_treino": faltam,
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
        probabilidade = prever_pontuacao_sombra(
            envelope["modelo"], item
        )
        avaliados.append({
            **item,
            "probabilidade_sombra": probabilidade,
            "probabilidade_implicita_odd": round(
                1.0 / float(item["odd"]), 8
            ),
        })
    auc_sombra = discriminacao_pontuacao([{
        "resultado": item["resultado"],
        "pontuacao_tecnica": item["probabilidade_sombra"],
    } for item in avaliados])
    auc_atual = discriminacao_pontuacao([{
        "resultado": item["resultado"],
        "pontuacao_tecnica": item["pontuacao_tecnica"],
    } for item in avaliados])
    brier_sombra = _brier(avaliados, "probabilidade_sombra")
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
        auc_sombra.get("limite_inferior_auc_95") is not None
        and auc_sombra["limite_inferior_auc_95"] > 0.5
        and (
            auc_atual.get("auc") is None
            or auc_sombra["auc"] >= auc_atual["auc"] + 0.05
        )
        and brier_sombra is not None
        and brier_odd is not None
        and brier_sombra <= brier_odd
    ):
        estado = "favoravel_para_revisao"
    elif (
        auc_sombra.get("intervalo_auc_95")
        and auc_sombra["intervalo_auc_95"][1] < 0.5
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
        "auc_sombra": auc_sombra,
        "auc_nota_atual": auc_atual,
        "brier_sombra": brier_sombra,
        "brier_odd": brier_odd,
        "pronto_para_revisao": estado == "favoravel_para_revisao",
    }


def avaliar_pontuacao_sombra(conexao, regras_por_mercado):
    por_mercado = {
        mercado: avaliar_modelo_pontuacao_sombra(
            conexao, mercado, regra_versao
        )
        for mercado, regra_versao in sorted(
            (regras_por_mercado or {}).items()
        )
    }
    return {
        "versao": VERSAO_PONTUACAO_SOMBRA,
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


def registrar_modelos_pontuacao_sombra(
    conexao,
    regras_por_mercado,
    registrado_em=None,
):
    resultados = {}
    for mercado, regra_versao in sorted(
        (regras_por_mercado or {}).items()
    ):
        resultados[mercado] = registrar_ou_obter_modelo_pontuacao_sombra(
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
