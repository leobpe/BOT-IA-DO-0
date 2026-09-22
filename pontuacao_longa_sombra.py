"""Challenger prospectivo com janelas temporais completas de 10 e 15 min.

O estudo nasce com uma ancora imutavel. Somente sinais posteriores a essa
ancora podem formar o treino; o modelo e congelado nos primeiros 60 exemplos
e avaliado nos 30 exemplos seguintes. Nada deste modulo altera sinais.
"""

import hashlib
import json
import math
from datetime import datetime

from dataset_temporal import construir_dataset_temporal
from estatistica import discriminacao_pontuacao
from linhagem_regras import fingerprint_vinculado_no_banco
from treino_processo_isolado import executar_treino_isolado


VERSAO_PONTUACAO_LONGA_SOMBRA = "pontuacao-longa-logistica-v2"
VERSAO_AVALIACAO_PONTUACAO_LONGA = (
    "avaliacao-pontuacao-longa-prospectiva-v2"
)
ALGORITMO = "logistica-l2-batch-v1"
AMOSTRA_MINIMA_TREINO = 60
AMOSTRA_MINIMA_VALIDACAO = 30
ITERACOES_TREINO = 800
TAXA_APRENDIZADO = 0.05
REGULARIZACAO_L2 = 0.25
LIMITE_Z = 5.0
JANELA_MAXIMA_DATASET = 5000
FEATURES_PONTUACAO_LONGA = (
    "pontuacao_tecnica",
    "odd",
    "minuto",
    "gols_atuais",
    "chutes_no_gol_total",
    "qualidade_dados",
    "j5_chutes_por_minuto",
    "j5_escanteios_por_minuto",
    "j5_pressao_media_max",
    "j10_chutes_por_minuto",
    "j10_escanteios_por_minuto",
    "j10_pressao_media_max",
    "j15_chutes_por_minuto",
    "j15_escanteios_por_minuto",
    "j15_pressao_media_max",
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


def _configuracao():
    return {
        "versao": VERSAO_PONTUACAO_LONGA_SOMBRA,
        "avaliacao_versao": VERSAO_AVALIACAO_PONTUACAO_LONGA,
        "algoritmo": ALGORITMO,
        "features": list(FEATURES_PONTUACAO_LONGA),
        "janelas_obrigatorias": [5, 10, 15],
        "dados_ausentes": "excluir_registro",
        "separacao": "60_treino_seguidos_30_validacao_seguidos",
        "amostra_minima_treino": AMOSTRA_MINIMA_TREINO,
        "amostra_minima_validacao": AMOSTRA_MINIMA_VALIDACAO,
        "iteracoes": ITERACOES_TREINO,
        "taxa_aprendizado": TAXA_APRENDIZADO,
        "regularizacao_l2": REGULARIZACAO_L2,
        "limite_z": LIMITE_Z,
    }


def fingerprint_configuracao_pontuacao_longa():
    serializado = json.dumps(
        _configuracao(), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _hash_json(valor):
    serializado = json.dumps(
        valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _chave_ancora(mercado, regra_versao):
    return (
        f"pontuacao_sombra:longa_ancora:{VERSAO_PONTUACAO_LONGA_SOMBRA}:"
        f"{regra_versao}:{mercado}"
    )


def _chave_modelo(mercado, regra_versao):
    return (
        f"pontuacao_sombra:longa_modelo:{VERSAO_PONTUACAO_LONGA_SOMBRA}:"
        f"{regra_versao}:{mercado}"
    )


def _carregar_json_metadado(conexao, chave):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is None:
        return None
    try:
        return json.loads(linha[0])
    except (TypeError, json.JSONDecodeError):
        return {"_json_invalido": True}


def carregar_ancora_pontuacao_longa(conexao, mercado, regra_versao):
    ancora = _carregar_json_metadado(
        conexao, _chave_ancora(mercado, regra_versao)
    )
    if ancora is None:
        return None
    hash_declarado = ancora.get("ancora_hash")
    conteudo = {k: v for k, v in ancora.items() if k != "ancora_hash"}
    fingerprint_atual = fingerprint_vinculado_no_banco(
        conexao, regra_versao
    )
    integro = bool(
        not ancora.get("_json_invalido")
        and hash_declarado == _hash_json(conteudo)
        and ancora.get("versao") == VERSAO_PONTUACAO_LONGA_SOMBRA
        and ancora.get("mercado") == mercado
        and ancora.get("regra_versao") == regra_versao
        and ancora.get("configuracao_fingerprint")
        == fingerprint_configuracao_pontuacao_longa()
        and isinstance(ancora.get("iniciar_apos_sinal_id"), int)
        and bool(ancora.get("regra_fingerprint"))
        and ancora.get("regra_fingerprint") == fingerprint_atual
    )
    return {
        **ancora,
        "integro": integro,
        "motivo": None if integro else "ancora_incompativel_ou_corrompida",
    }


def registrar_ancora_pontuacao_longa(
    conexao, mercado, regra_versao, registrado_em=None
):
    existente = carregar_ancora_pontuacao_longa(
        conexao, mercado, regra_versao
    )
    if existente is not None:
        return {"criada": False, **existente}
    regra_fingerprint = fingerprint_vinculado_no_banco(
        conexao, regra_versao
    )
    if not regra_fingerprint:
        return {
            "criada": False,
            "integro": False,
            "estado": "aguardando_linhagem_regra",
            "mercado": mercado,
            "regra_versao": regra_versao,
        }
    maior_sinal_id = int(conexao.execute(
        "SELECT COALESCE(MAX(id), 0) FROM sinais"
    ).fetchone()[0])
    conteudo = {
        "versao": VERSAO_PONTUACAO_LONGA_SOMBRA,
        "avaliacao_versao": VERSAO_AVALIACAO_PONTUACAO_LONGA,
        "mercado": mercado,
        "regra_versao": regra_versao,
        "regra_fingerprint": regra_fingerprint,
        "configuracao_fingerprint": (
            fingerprint_configuracao_pontuacao_longa()
        ),
        "registrado_em": (
            registrado_em
            or datetime.now().replace(microsecond=0).isoformat()
        ),
        "iniciar_apos_sinal_id": maior_sinal_id,
        "aplicacao_automatica": False,
    }
    ancora = {**conteudo, "ancora_hash": _hash_json(conteudo)}
    cursor = conexao.execute(
        "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
        (
            _chave_ancora(mercado, regra_versao),
            json.dumps(
                ancora, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    carregada = carregar_ancora_pontuacao_longa(
        conexao, mercado, regra_versao
    )
    return {"criada": bool(cursor.rowcount), **(carregada or {})}


def _registros_prospectivos(conexao, mercado, regra_versao, ancora):
    dataset = construir_dataset_temporal(
        conexao,
        mercado,
        regra_versao=regra_versao,
        janela_maxima=JANELA_MAXIMA_DATASET,
    )
    registros = []
    excluidos = {"anteriores_ancora": 0, "janelas_incompletas": 0}
    for item in sorted(
        dataset["registros"], key=lambda registro: int(registro["sinal_id"])
    ):
        if int(item["sinal_id"]) <= int(ancora["iniciar_apos_sinal_id"]):
            excluidos["anteriores_ancora"] += 1
            continue
        features = item.get("features") or {}
        completo = bool(
            features.get("j5_disponivel") == 1
            and features.get("j10_disponivel") == 1
            and features.get("j15_disponivel") == 1
            and all(
                _valor_feature(item, nome) is not None
                for nome in FEATURES_PONTUACAO_LONGA
            )
        )
        if not completo:
            excluidos["janelas_incompletas"] += 1
            continue
        registros.append(item)
    return registros, excluidos, dataset


def _sigmoide(valor):
    if valor >= 0:
        exponencial = math.exp(-min(valor, 60.0))
        return 1.0 / (1.0 + exponencial)
    exponencial = math.exp(max(valor, -60.0))
    return exponencial / (1.0 + exponencial)


def _ajustar_modelo_pontuacao_longa_impl(registros):
    if len(registros) != AMOSTRA_MINIMA_TREINO:
        raise ValueError("treino_deve_usar_janela_fixa")
    matriz_bruta = [
        [_valor_feature(item, nome) for nome in FEATURES_PONTUACAO_LONGA]
        for item in registros
    ]
    if any(valor is None for linha in matriz_bruta for valor in linha):
        raise ValueError("feature_longa_ausente")
    alvos = [int(bool(item.get("alvo_green"))) for item in registros]
    if not any(alvos) or all(alvos):
        raise ValueError("classes_treino_insuficientes")
    medias = {
        nome: sum(linha[indice] for linha in matriz_bruta) / len(registros)
        for indice, nome in enumerate(FEATURES_PONTUACAO_LONGA)
    }
    desvios = {}
    for indice, nome in enumerate(FEATURES_PONTUACAO_LONGA):
        variancia = sum(
            (linha[indice] - medias[nome]) ** 2 for linha in matriz_bruta
        ) / len(registros)
        desvios[nome] = math.sqrt(variancia) or 1.0
    matriz = [[
        max(-LIMITE_Z, min(
            LIMITE_Z,
            (linha[indice] - medias[nome]) / desvios[nome],
        ))
        for indice, nome in enumerate(FEATURES_PONTUACAO_LONGA)
    ] for linha in matriz_bruta]
    pesos = [0.0] * len(FEATURES_PONTUACAO_LONGA)
    proporcao = min(max(sum(alvos) / len(alvos), 1e-6), 1 - 1e-6)
    intercepto = math.log(proporcao / (1 - proporcao))
    for _ in range(ITERACOES_TREINO):
        gradiente_intercepto = 0.0
        gradientes = [0.0] * len(pesos)
        for linha, alvo in zip(matriz, alvos):
            previsao = _sigmoide(
                intercepto + sum(p * v for p, v in zip(pesos, linha))
            )
            erro = previsao - alvo
            gradiente_intercepto += erro
            for indice, valor in enumerate(linha):
                gradientes[indice] += erro * valor
        intercepto -= TAXA_APRENDIZADO * (
            gradiente_intercepto / len(matriz)
        )
        for indice in range(len(pesos)):
            pesos[indice] -= TAXA_APRENDIZADO * (
                gradientes[indice] / len(matriz)
                + REGULARIZACAO_L2 * pesos[indice]
            )
    return {
        "versao": VERSAO_PONTUACAO_LONGA_SOMBRA,
        "algoritmo": ALGORITMO,
        "configuracao_fingerprint": (
            fingerprint_configuracao_pontuacao_longa()
        ),
        "features": list(FEATURES_PONTUACAO_LONGA),
        "intercepto": round(intercepto, 12),
        "pesos": {
            nome: round(peso, 12)
            for nome, peso in zip(FEATURES_PONTUACAO_LONGA, pesos)
        },
        "medias": {nome: round(medias[nome], 12) for nome in medias},
        "desvios": {nome: round(desvios[nome], 12) for nome in desvios},
        "amostra_treino": len(registros),
        "greens_treino": sum(alvos),
        "reds_treino": len(alvos) - sum(alvos),
    }


def ajustar_modelo_pontuacao_longa(registros):
    """Treina o challenger longo fora do processo principal e valida a saida."""
    return executar_treino_isolado(
        "pontuacao_longa",
        {"registros": registros},
        validar_modelo=modelo_pontuacao_longa_compativel,
        erros_dominio_exatos=(
            "treino_deve_usar_janela_fixa",
            "feature_longa_ausente",
            "classes_treino_insuficientes",
        ),
    )


def modelo_pontuacao_longa_compativel(modelo):
    return bool(
        isinstance(modelo, dict)
        and modelo.get("versao") == VERSAO_PONTUACAO_LONGA_SOMBRA
        and modelo.get("algoritmo") == ALGORITMO
        and modelo.get("configuracao_fingerprint")
        == fingerprint_configuracao_pontuacao_longa()
        and modelo.get("features") == list(FEATURES_PONTUACAO_LONGA)
        and set(modelo.get("pesos") or {}) == set(FEATURES_PONTUACAO_LONGA)
        and set(modelo.get("medias") or {}) == set(FEATURES_PONTUACAO_LONGA)
        and set(modelo.get("desvios") or {}) == set(FEATURES_PONTUACAO_LONGA)
        and int(modelo.get("amostra_treino") or 0) == AMOSTRA_MINIMA_TREINO
    )


def prever_pontuacao_longa(modelo, item):
    if not modelo_pontuacao_longa_compativel(modelo):
        raise ValueError("modelo_pontuacao_longa_incompativel")
    logit = float(modelo["intercepto"])
    for nome in FEATURES_PONTUACAO_LONGA:
        valor = _valor_feature(item, nome)
        if valor is None:
            raise ValueError(f"feature_longa_ausente:{nome}")
        desvio = float(modelo["desvios"][nome]) or 1.0
        z = (valor - float(modelo["medias"][nome])) / desvio
        z = max(-LIMITE_Z, min(LIMITE_Z, z))
        logit += float(modelo["pesos"][nome]) * z
    return round(_sigmoide(logit), 8)


def carregar_modelo_pontuacao_longa(conexao, mercado, regra_versao):
    envelope = _carregar_json_metadado(
        conexao, _chave_modelo(mercado, regra_versao)
    )
    if envelope is None:
        return None
    modelo = envelope.get("modelo")
    ancora = carregar_ancora_pontuacao_longa(
        conexao, mercado, regra_versao
    )
    conteudo = {k: v for k, v in envelope.items() if k != "envelope_hash"}
    integro = bool(
        not envelope.get("_json_invalido")
        and envelope.get("envelope_hash") == _hash_json(conteudo)
        and envelope.get("mercado") == mercado
        and envelope.get("regra_versao") == regra_versao
        and isinstance(ancora, dict)
        and ancora.get("integro") is True
        and envelope.get("ancora_hash") == ancora.get("ancora_hash")
        and modelo_pontuacao_longa_compativel(modelo)
    )
    return {
        **envelope,
        "integro": integro,
        "motivo": None if integro else "modelo_incompativel_ou_corrompido",
    }


def registrar_modelo_pontuacao_longa(
    conexao, mercado, regra_versao, registrado_em=None
):
    ancora = carregar_ancora_pontuacao_longa(
        conexao, mercado, regra_versao
    )
    if ancora is None or not ancora.get("integro"):
        return {
            "criado": False,
            "integro": False,
            "estado": "ancora_ausente_ou_invalida",
        }
    existente = carregar_modelo_pontuacao_longa(
        conexao, mercado, regra_versao
    )
    if existente is not None:
        return {"criado": False, **existente}
    registros, excluidos, _ = _registros_prospectivos(
        conexao, mercado, regra_versao, ancora
    )
    if len(registros) < AMOSTRA_MINIMA_TREINO:
        return {
            "criado": False,
            "integro": True,
            "estado": "formando_treino_prospectivo",
            "amostra_disponivel": len(registros),
            "faltam": AMOSTRA_MINIMA_TREINO - len(registros),
            "excluidos": excluidos,
        }
    treino = registros[:AMOSTRA_MINIMA_TREINO]
    modelo = ajustar_modelo_pontuacao_longa(treino)
    conteudo = {
        "versao": VERSAO_PONTUACAO_LONGA_SOMBRA,
        "avaliacao_versao": VERSAO_AVALIACAO_PONTUACAO_LONGA,
        "mercado": mercado,
        "regra_versao": regra_versao,
        "ancora_hash": ancora["ancora_hash"],
        "registrado_em": (
            registrado_em
            or datetime.now().replace(microsecond=0).isoformat()
        ),
        "treino_ate_sinal_id": int(treino[-1]["sinal_id"]),
        "treino_fingerprint": _hash_json([
            [int(item["sinal_id"]), item["resultado"]] for item in treino
        ]),
        "modelo": modelo,
        "aplicacao_automatica": False,
    }
    envelope = {**conteudo, "envelope_hash": _hash_json(conteudo)}
    cursor = conexao.execute(
        "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
        (
            _chave_modelo(mercado, regra_versao),
            json.dumps(
                envelope, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    carregado = carregar_modelo_pontuacao_longa(
        conexao, mercado, regra_versao
    )
    return {"criado": bool(cursor.rowcount), **(carregado or {})}


def _brier(itens, campo):
    if not itens:
        return None
    return round(sum(
        (float(item[campo]) - int(item["alvo_green"])) ** 2
        for item in itens
    ) / len(itens), 6)


def avaliar_modelo_pontuacao_longa(conexao, mercado, regra_versao):
    ancora = carregar_ancora_pontuacao_longa(
        conexao, mercado, regra_versao
    )
    base = {
        "versao": VERSAO_PONTUACAO_LONGA_SOMBRA,
        "avaliacao_versao": VERSAO_AVALIACAO_PONTUACAO_LONGA,
        "mercado": mercado,
        "regra_versao": regra_versao,
        "modo": "sombra",
        "aplicacao_automatica": False,
        "amostra_minima_treino": AMOSTRA_MINIMA_TREINO,
        "amostra_minima_validacao": AMOSTRA_MINIMA_VALIDACAO,
    }
    if ancora is None:
        return {
            **base, "integro": True, "estado": "aguardando_ancora",
            "treino": 0, "validacao": 0,
        }
    if not ancora.get("integro"):
        return {
            **base, "integro": False, "estado": "ancora_invalida",
            "motivo": ancora.get("motivo"), "validacao": 0,
        }
    registros, excluidos, _ = _registros_prospectivos(
        conexao, mercado, regra_versao, ancora
    )
    modelo = carregar_modelo_pontuacao_longa(
        conexao, mercado, regra_versao
    )
    if modelo is None:
        return {
            **base,
            "integro": True,
            "estado": "formando_treino_prospectivo",
            "ancora_registrada_em": ancora["registrado_em"],
            "iniciar_apos_sinal_id": ancora["iniciar_apos_sinal_id"],
            "treino": len(registros),
            "faltam_treino": max(
                AMOSTRA_MINIMA_TREINO - len(registros), 0
            ),
            "validacao": 0,
            "excluidos": excluidos,
        }
    if not modelo.get("integro"):
        return {
            **base, "integro": False, "estado": "modelo_invalido",
            "motivo": modelo.get("motivo"), "validacao": 0,
        }
    ancora_treino = int(modelo["treino_ate_sinal_id"])
    validacao_disponivel = [
        item for item in registros
        if int(item["sinal_id"]) > ancora_treino
    ]
    validacao = validacao_disponivel[:AMOSTRA_MINIMA_VALIDACAO]
    avaliados = []
    for item in validacao:
        avaliados.append({
            **item,
            "probabilidade_longa": prever_pontuacao_longa(
                modelo["modelo"], item
            ),
            "probabilidade_implicita_odd": round(1 / float(item["odd"]), 8),
        })
    auc_longa = discriminacao_pontuacao([{
        "resultado": item["resultado"],
        "pontuacao_tecnica": item["probabilidade_longa"],
    } for item in avaliados])
    auc_atual = discriminacao_pontuacao([{
        "resultado": item["resultado"],
        "pontuacao_tecnica": item["pontuacao_tecnica"],
    } for item in avaliados])
    quantidade = len(avaliados)
    brier_longa = _brier(avaliados, "probabilidade_longa")
    brier_odd = _brier(avaliados, "probabilidade_implicita_odd")
    if quantidade < AMOSTRA_MINIMA_VALIDACAO:
        estado = "aguardando_validacao"
    elif (
        auc_longa.get("limite_inferior_auc_95") is not None
        and auc_longa["limite_inferior_auc_95"] > 0.5
        and (
            auc_atual.get("auc") is None
            or auc_longa["auc"] >= auc_atual["auc"] + 0.05
        )
        and brier_longa is not None
        and brier_odd is not None
        and brier_longa < brier_odd
    ):
        estado = "favoravel_para_revisao"
    elif (
        auc_longa.get("intervalo_auc_95")
        and auc_longa["intervalo_auc_95"][1] < 0.5
    ):
        estado = "contraria"
    else:
        estado = "inconclusiva"
    return {
        **base,
        "integro": True,
        "estado": estado,
        "ancora_registrada_em": ancora["registrado_em"],
        "iniciar_apos_sinal_id": ancora["iniciar_apos_sinal_id"],
        "treino": AMOSTRA_MINIMA_TREINO,
        "treino_ate_sinal_id": ancora_treino,
        "validacao": quantidade,
        "validacao_total_disponivel": len(validacao_disponivel),
        "validacao_congelada": quantidade >= AMOSTRA_MINIMA_VALIDACAO,
        "faltam_validacao": max(
            AMOSTRA_MINIMA_VALIDACAO - quantidade, 0
        ),
        "validacao_fingerprint": _hash_json([
            [int(item["sinal_id"]), item["resultado"]]
            for item in avaliados
        ]),
        "auc_longa": auc_longa,
        "auc_nota_atual": auc_atual,
        "brier_longa": brier_longa,
        "brier_odd": brier_odd,
        "excluidos": excluidos,
        "pronto_para_revisao": estado == "favoravel_para_revisao",
    }


def avaliar_pontuacao_longa_sombra(conexao, regras_por_mercado):
    por_mercado = {
        mercado: avaliar_modelo_pontuacao_longa(
            conexao, mercado, regra_versao
        )
        for mercado, regra_versao in sorted(
            (regras_por_mercado or {}).items()
        )
    }
    return {
        "versao": VERSAO_PONTUACAO_LONGA_SOMBRA,
        "modo": "sombra",
        "aplicacao_automatica": False,
        "integro": all(
            item.get("integro", False) for item in por_mercado.values()
        ),
        "por_mercado": por_mercado,
        "mercados_com_modelo": [
            mercado for mercado, item in por_mercado.items()
            if item.get("treino") == AMOSTRA_MINIMA_TREINO
            and item.get("estado") not in (
                "formando_treino_prospectivo", "aguardando_ancora"
            )
        ],
        "mercados_prontos_para_revisao": [
            mercado for mercado, item in por_mercado.items()
            if item.get("pronto_para_revisao")
        ],
    }


def registrar_estudos_pontuacao_longa(
    conexao, regras_por_mercado, registrado_em=None
):
    resultados = {}
    for mercado, regra_versao in sorted(
        (regras_por_mercado or {}).items()
    ):
        ancora = registrar_ancora_pontuacao_longa(
            conexao, mercado, regra_versao, registrado_em=registrado_em
        )
        modelo = registrar_modelo_pontuacao_longa(
            conexao, mercado, regra_versao, registrado_em=registrado_em
        )
        resultados[mercado] = {"ancora": ancora, "modelo": modelo}
    return {
        "ancoras_criadas": sum(
            bool(item["ancora"].get("criada"))
            for item in resultados.values()
        ),
        "modelos_criados": sum(
            bool(item["modelo"].get("criado"))
            for item in resultados.values()
        ),
        "integro": all(
            item["ancora"].get("integro", False)
            and item["modelo"].get("integro", False)
            for item in resultados.values()
        ),
        "por_mercado": resultados,
    }
