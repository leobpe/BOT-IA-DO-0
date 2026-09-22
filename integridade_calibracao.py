import hashlib
import json
import math
from collections import Counter
from datetime import datetime

from linhagem_regras import fingerprint_vinculado_no_banco
from proveniencia_odds import (
    BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
    CHAVE_ESTADO_COTACAO_ENTRADA,
    ESTADO_COTACAO_CONGELADA,
    FONTE_COTACAO_EXECUTAVEL_OFICIAL,
    VERSAO_COTACAO_ENTRADA_CLV,
    validar_cotacao_executavel_oficial,
)


RESULTADOS_CALIBRAVEIS = ("green", "half_green", "red", "half_red")
RESULTADOS_NEUTROS = ("void",)
LIMITE_EXPOSICOES_CALIBRACAO = 300
MINIMO_DIAS_DIVERSIDADE = 7
MINIMO_LIGAS_DIVERSIDADE = 5
POPULACAO_CALIBRACAO_EXECUTAVEL = (
    "sinais_elegiveis_executaveis_betsapi_bet365"
)


def _filtro_sql_cotacao_executavel(alias="s"):
    """Pré-seleciona somente fotografias que declaram o contrato oficial.

    A validação criptograficamente vinculada abaixo continua sendo a fonte da
    verdade. Este filtro ocorre antes do ``ROW_NUMBER`` para que uma leitura
    agregada anterior da mesma partida não expulse a primeira oferta Bet365
    realmente executável da coorte.
    """
    return f"""
      AND json_valid({alias}.features_json)=1
      AND lower(COALESCE(json_extract(
            {alias}.features_json, '$.fonte_odds'
          ), ''))=?
      AND lower(COALESCE(json_extract(
            {alias}.features_json, '$.bookmaker_odds'
          ), ''))=?
      AND COALESCE(json_extract(
            {alias}.features_json, '$.{CHAVE_ESTADO_COTACAO_ENTRADA}'
          ), '')=?
      AND COALESCE(json_extract(
            {alias}.features_json, '$.cotacao_entrada_clv.schema'
          ), '')=?
    """


def _parametros_cotacao_executavel():
    return (
        FONTE_COTACAO_EXECUTAVEL_OFICIAL,
        BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
        ESTADO_COTACAO_CONGELADA,
        VERSAO_COTACAO_ENTRADA_CLV,
    )


def _validar_custodia_unidade(unidade):
    try:
        features = json.loads(unidade.get("features_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return None, "features_json_invalido"
    if not isinstance(features, dict):
        return None, "features_json_invalido"
    candidato = {
        "mercado": unidade.get("mercado"),
        "linha": unidade.get("linha"),
        "odd": unidade.get("odd"),
        "fonte_odds": features.get("fonte_odds"),
        "bookmaker_odds": features.get("bookmaker_odds"),
        "features": features,
    }
    custodia = validar_cotacao_executavel_oficial(candidato)
    if custodia.get("apto") is not True:
        return None, str(custodia.get("motivo") or "custodia_invalida")
    prova = {
        "mercado": candidato["mercado"],
        "linha": candidato["linha"],
        "odd": candidato["odd"],
        "fonte_odds": candidato["fonte_odds"],
        "bookmaker_odds": candidato["bookmaker_odds"],
        "cotacao_entrada_clv": features.get("cotacao_entrada_clv"),
        "cotacao_entrada_clv_estado": features.get(
            CHAVE_ESTADO_COTACAO_ENTRADA
        ),
    }
    serializado = json.dumps(
        prova,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    validada = dict(unidade)
    validada.update({
        "custodia_cotacao_hash": hashlib.sha256(serializado).hexdigest(),
        "fonte_odds": FONTE_COTACAO_EXECUTAVEL_OFICIAL,
        "bookmaker_odds": BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
        "custodia_cotacao_versao": custodia.get("versao"),
    })
    return validada, None


def _numero_finito(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _retorno_esperado(resultado, odd):
    return {
        "green": odd - 1.0,
        "half_green": (odd - 1.0) / 2.0,
        "half_red": -0.5,
        "red": -1.0,
        "void": 0.0,
    }.get(resultado)


def _validar_unidade_calibracao(item):
    """Valida uma liquidação sem permitir que sua qualidade escolha a coorte."""
    resultado_original = str(item.get("resultado") or "").strip().casefold()
    if not resultado_original:
        return None, "resultado_ausente"
    if resultado_original not in (
        *RESULTADOS_CALIBRAVEIS,
        *RESULTADOS_NEUTROS,
    ):
        return None, f"resultado_nao_calibravel:{resultado_original}"

    odd = _numero_finito(item.get("odd"))
    retorno = _numero_finito(item.get("retorno_unidades"))
    if odd is None or odd <= 1.0:
        return None, "odd_ausente_ou_invalida"
    if retorno is None:
        return None, "retorno_ausente_ou_invalido"
    esperado = _retorno_esperado(resultado_original, odd)
    if esperado is None or abs(retorno - esperado) > 1e-4:
        return None, "retorno_incompativel_com_resultado_e_odd"

    try:
        criado = datetime.fromisoformat(str(item.get("criado_em") or ""))
    except (TypeError, ValueError):
        return None, "criacao_ausente_ou_invalida"
    try:
        encerrado = datetime.fromisoformat(str(item.get("encerrado_em") or ""))
    except (TypeError, ValueError):
        return None, "encerramento_ausente_ou_invalido"
    if encerrado < criado:
        return None, "encerramento_anterior_ao_sinal"

    normalizado = dict(item)
    neutra = resultado_original in RESULTADOS_NEUTROS
    normalizado.update({
        "odd": odd,
        "retorno_unidades": retorno,
        "resultado_original": resultado_original,
        "resultado": (
            "void"
            if neutra else
            "green"
            if resultado_original in ("green", "half_green")
            else "red"
        ),
        "neutra_calibracao": neutra,
    })
    return normalizado, None


def carregar_coorte_independente(
    conexao,
    mercado,
    regra_versao,
    limites_risco,
    janela_maxima=300,
    janela="recentes",
    alvo_validas=None,
    somente_executaveis=False,
):
    """Congela unidades por primeira exposição antes de consultar o resultado.

    A janela é aplicada aos primeiros sinais elegíveis de partidas distintas.
    Somente depois disso a liquidação é anexada e validada. Portanto, uma
    ausência ou retorno corrompido ocupa sua posição. Um ``void`` íntegro
    permanece auditado na ordem, mas pode ser seguido por outra liquidação
    binária sem consultar se ela terminou green ou red.
    """
    if janela not in {"recentes", "primeiros"}:
        raise ValueError("Janela da amostra deve ser 'recentes' ou 'primeiros'")
    try:
        limite = int(janela_maxima)
    except (TypeError, ValueError):
        raise ValueError("A janela máxima deve ser um inteiro positivo")
    if limite <= 0:
        raise ValueError("A janela máxima deve ser um inteiro positivo")
    if alvo_validas is not None:
        try:
            alvo = int(alvo_validas)
        except (TypeError, ValueError):
            raise ValueError("O alvo de liquidações deve ser positivo")
        if alvo <= 0 or alvo > limite:
            raise ValueError(
                "O alvo de liquidações deve ser positivo e caber na janela"
            )
        if janela != "primeiros":
            raise ValueError(
                "O preenchimento por alvo só pode usar a janela 'primeiros'"
            )
    else:
        alvo = None

    regra_fingerprint = fingerprint_vinculado_no_banco(
        conexao, regra_versao
    )
    if regra_fingerprint is None:
        return {
            "unidades": [],
            "validas": [],
            "diagnostico": {
                "estado": "linhagem_indisponivel",
                "unidades_selecionadas": 0,
                "validas": 0,
                "pendentes": 0,
                "invalidas": 0,
                "devolvidas_contratuais": 0,
                "encerradas_sem_dado": 0,
                "invalidas_tecnicas": 0,
                "neutras": 0,
                "motivos_neutros": {},
                "pendentes_ou_invalidas": 0,
                "motivos": {},
                "selecao_antes_do_resultado": True,
                "chave_independencia": "partida_id",
                "ordem_coorte": "criado_em_asc_id_asc",
                "janela": janela,
                "janela_maxima": limite,
                "alvo_validas": alvo,
                "criterio_preenchimento": (
                    (
                        "primeiras_liquidacoes_binarias_executaveis_"
                        "sem_escolher_green_red"
                    )
                    if somente_executaveis and alvo is not None else
                    "primeiras_liquidacoes_binarias_sem_escolher_green_red"
                    if alvo is not None else None
                ),
                "populacao": (
                    POPULACAO_CALIBRACAO_EXECUTAVEL
                    if somente_executaveis
                    else "sinais_elegiveis_para_alerta"
                ),
                "cotacao_executavel_obrigatoria": bool(
                    somente_executaveis
                ),
                "fonte_odds_exigida": (
                    FONTE_COTACAO_EXECUTAVEL_OFICIAL
                    if somente_executaveis else None
                ),
                "bookmaker_odds_exigida": (
                    BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL
                    if somente_executaveis else None
                ),
                "custodias_invalidas": 0,
            },
        }

    ordem_janela = "ASC" if janela == "primeiros" else "DESC"
    filtro_executavel = (
        _filtro_sql_cotacao_executavel("s")
        if somente_executaveis else ""
    )
    parametros_executaveis = (
        _parametros_cotacao_executavel()
        if somente_executaveis else ()
    )
    linhas = conexao.execute(
        f"""
        WITH candidatos AS (
            SELECT s.id, s.partida_id, s.snapshot_id, s.criado_em,
                   s.mercado, s.linha, s.odd, s.pontuacao_tecnica,
                   s.features_json,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.partida_id
                       ORDER BY datetime(s.criado_em), s.id
                   ) AS ordem_partida
            FROM sinais s
            WHERE s.mercado=? AND s.regra_versao=?
              AND s.regra_fingerprint=?
              AND s.status='aprovado'
              AND s.odd BETWEEN ? AND ?
              {filtro_executavel}
        ), janela AS (
            SELECT * FROM candidatos
            WHERE ordem_partida=1
            ORDER BY datetime(criado_em) {ordem_janela},
                     id {ordem_janela}
            LIMIT ?
        )
        SELECT janela.*, r.resultado, r.retorno_unidades, r.encerrado_em
        FROM janela
        LEFT JOIN resultados_sinais r ON r.sinal_id=janela.id
        ORDER BY datetime(janela.criado_em), janela.id
        """,
        (
            mercado,
            regra_versao,
            regra_fingerprint,
            limites_risco.odd_minima,
            limites_risco.odd_maxima,
            *parametros_executaveis,
            limite,
        ),
    ).fetchall()
    unidades_brutas = [dict(linha) for linha in linhas]
    unidades = []
    validas = []
    neutras = []
    motivos = Counter()
    motivos_neutros = Counter()
    for unidade_bruta in unidades_brutas:
        unidade = unidade_bruta
        if somente_executaveis:
            unidade, motivo_custodia = _validar_custodia_unidade(unidade)
            if unidade is None:
                unidades.append(dict(unidade_bruta))
                motivos[f"custodia_execucao:{motivo_custodia}"] += 1
                continue
        unidades.append(unidade)
        normalizada, motivo = _validar_unidade_calibracao(unidade)
        if normalizada is None:
            motivos[motivo] += 1
        elif normalizada.get("neutra_calibracao") is True:
            neutras.append(normalizada)
            motivos_neutros[
                f"resultado_neutro:{normalizada['resultado_original']}"
            ] += 1
        else:
            validas.append(normalizada)
        if alvo is not None and len(validas) >= alvo:
            break
    pendentes = int(motivos.get("resultado_ausente", 0))
    invalidas = len(unidades) - len(validas) - len(neutras) - pendentes
    # A calibração genérica continua binária: uma devolução não é
    # convertida em green ou red. Entretanto, ``void`` com retorno zero e
    # relógios coerentes é uma liquidação contratual válida, não uma falha
    # de dados. Ela preserva sua posição cronológica e apenas não entra no
    # alvo binário. ``sem_dado`` e inconsistências continuam fail-closed.
    devolvidas_contratuais = len(neutras)
    encerradas_sem_dado = int(
        motivos.get("resultado_nao_calibravel:sem_dado", 0)
    )
    invalidas_tecnicas = max(
        invalidas - encerradas_sem_dado,
        0,
    )
    alvo_atingido = alvo is not None and len(validas) >= alvo
    janela_liquidada = bool(
        len(unidades) == limite
        and not pendentes
        and not invalidas
    )
    return {
        "unidades": unidades,
        "validas": validas,
        "neutras": neutras,
        "diagnostico": {
            "estado": (
                "completa"
                if (alvo_atingido or janela_liquidada)
                and not pendentes and not invalidas
                else "liquidacoes_invalidas"
                if invalidas
                else "resultados_pendentes"
                if pendentes
                else "formando_coorte"
            ),
            "unidades_selecionadas": len(unidades),
            "validas": len(validas),
            "pendentes": pendentes,
            "invalidas": invalidas,
            "devolvidas_contratuais": devolvidas_contratuais,
            "encerradas_sem_dado": encerradas_sem_dado,
            "invalidas_tecnicas": invalidas_tecnicas,
            "neutras": len(neutras),
            "pendentes_ou_invalidas": pendentes + invalidas,
            "motivos": dict(motivos),
            "motivos_neutros": dict(motivos_neutros),
            "selecao_antes_do_resultado": True,
            "exclusao_somente_liquidacao_neutra": True,
            "chave_independencia": "partida_id",
            "ordem_coorte": "criado_em_asc_id_asc",
            "janela": janela,
            "janela_maxima": limite,
            "alvo_validas": alvo,
            "criterio_preenchimento": (
                (
                    "primeiras_liquidacoes_binarias_executaveis_"
                    "sem_escolher_green_red"
                )
                if somente_executaveis and alvo is not None else
                "primeiras_liquidacoes_binarias_sem_escolher_green_red"
                if alvo is not None else None
            ),
            "populacao": (
                POPULACAO_CALIBRACAO_EXECUTAVEL
                if somente_executaveis else "sinais_elegiveis_para_alerta"
            ),
            "cotacao_executavel_obrigatoria": bool(somente_executaveis),
            "fonte_odds_exigida": (
                FONTE_COTACAO_EXECUTAVEL_OFICIAL
                if somente_executaveis else None
            ),
            "bookmaker_odds_exigida": (
                BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL
                if somente_executaveis else None
            ),
            "custodias_invalidas": sum(
                quantidade
                for motivo, quantidade in motivos.items()
                if motivo.startswith("custodia_execucao:")
            ),
        },
    }


def carregar_amostra_independente(
    conexao,
    mercado,
    regra_versao,
    limites_risco,
    janela_maxima=300,
    janela="recentes",
    somente_executaveis=False,
):
    return carregar_coorte_independente(
        conexao,
        mercado,
        regra_versao,
        limites_risco,
        janela_maxima,
        janela,
        somente_executaveis=somente_executaveis,
    )["validas"]


def contar_exposicoes_independentes(
    conexao, mercado, regra_versao, limites_risco, regra_fingerprint=None,
    somente_executaveis=False,
):
    fingerprint = (
        regra_fingerprint
        if regra_fingerprint is not None
        else fingerprint_vinculado_no_banco(conexao, regra_versao)
    )
    if fingerprint is None:
        return 0
    filtro_executavel = (
        _filtro_sql_cotacao_executavel("s")
        if somente_executaveis else ""
    )
    parametros_executaveis = (
        _parametros_cotacao_executavel()
        if somente_executaveis else ()
    )
    return int(conexao.execute(
        f"""
            SELECT COUNT(*) FROM (
            SELECT s.partida_id
            FROM sinais s
            WHERE s.mercado=? AND s.regra_versao=?
              AND s.regra_fingerprint=?
              AND s.status='aprovado'
              AND s.odd BETWEEN ? AND ?
              {filtro_executavel}
            GROUP BY s.partida_id
        )
        """,
        (
            mercado,
            regra_versao,
            fingerprint,
            limites_risco.odd_minima,
            limites_risco.odd_maxima,
            *parametros_executaveis,
        ),
    ).fetchone()[0] or 0)


def carregar_monitoramento_independente(
    conexao,
    mercado,
    regra_versao,
    limites_risco,
    janela_maxima=300,
    somente_executaveis=False,
):
    """Obtém as decisões resolvidas recentes sem trocar o sinal da partida."""
    total_exposicoes = contar_exposicoes_independentes(
        conexao, mercado, regra_versao, limites_risco,
        somente_executaveis=somente_executaveis,
    )
    coorte = carregar_coorte_independente(
        conexao,
        mercado,
        regra_versao,
        limites_risco,
        max(total_exposicoes, 1),
        janela="primeiros",
        somente_executaveis=somente_executaveis,
    )
    try:
        limite = int(janela_maxima)
    except (TypeError, ValueError):
        raise ValueError("A janela máxima deve ser um inteiro positivo")
    if limite <= 0:
        raise ValueError("A janela máxima deve ser um inteiro positivo")
    validas = coorte["validas"][-limite:]
    return {
        "validas": validas,
        "diagnostico": {
            **coorte["diagnostico"],
            "estado": (
                "monitoramento_com_liquidacoes_invalidas"
                if coorte["diagnostico"]["invalidas"]
                else "monitoramento_com_resultados_pendentes"
                if coorte["diagnostico"]["pendentes"]
                else "monitoramento_integro"
            ),
            "janela": "ultimas_decisoes_validas",
            "janela_maxima": limite,
            "decisoes_monitoradas": len(validas),
            "exposicoes_totais": total_exposicoes,
        },
    }


def auditar_diversidade_amostra_calibracao(
    conexao,
    mercado,
    regra_versao,
    limites_risco,
    janela_maxima=100,
    minimo_dias=MINIMO_DIAS_DIVERSIDADE,
    minimo_ligas=MINIMO_LIGAS_DIVERSIDADE,
    somente_executaveis=False,
):
    """Exige diversidade temporal e de ligas na janela oficial congelada."""
    alvo = int(janela_maxima)
    limite_exposicoes = max(
        alvo,
        LIMITE_EXPOSICOES_CALIBRACAO,
    )
    coorte = carregar_coorte_independente(
        conexao,
        mercado,
        regra_versao,
        limites_risco,
        limite_exposicoes,
        janela="primeiros",
        alvo_validas=alvo,
        somente_executaveis=somente_executaveis,
    )
    diagnostico = coorte["diagnostico"]
    if diagnostico["estado"] == "linhagem_indisponivel":
        return {
            "pronto": False,
            "estado": "linhagem_indisponivel",
            "amostra": 0,
            "dias_distintos": 0,
            "ligas_distintas": 0,
            "minimo_dias": int(minimo_dias),
            "minimo_ligas": int(minimo_ligas),
        }
    validas = coorte["validas"]
    partidas = [int(item["partida_id"]) for item in validas]
    ligas_por_partida = {}
    if partidas:
        marcadores = ",".join("?" for _ in partidas)
        ligas_por_partida = {
            int(linha["id"]): str(linha["liga_normalizada"] or "")
            for linha in conexao.execute(
                f"""
                SELECT id, liga_normalizada FROM partidas
                WHERE id IN ({marcadores})
                """,
                partidas,
            ).fetchall()
        }
    dias_validos = {
        datetime.fromisoformat(item["criado_em"]).date().isoformat()
        for item in validas
    }
    ligas_validas = {
        ligas_por_partida.get(int(item["partida_id"]), "")
        for item in validas
    } - {""}
    amostra = len(validas)
    dias = len(dias_validos)
    ligas = len(ligas_validas)
    amostra_completa = bool(
        amostra >= alvo
        and diagnostico["pendentes_ou_invalidas"] == 0
    )
    pronto = bool(
        amostra_completa
        and dias >= int(minimo_dias)
        and ligas >= int(minimo_ligas)
    )
    if diagnostico["pendentes_ou_invalidas"]:
        estado = "resultados_pendentes_ou_invalidos"
    elif not amostra_completa:
        estado = "formando_amostra"
    elif dias < int(minimo_dias):
        estado = "diversidade_temporal_insuficiente"
    elif ligas < int(minimo_ligas):
        estado = "diversidade_ligas_insuficiente"
    else:
        estado = "aprovada"
    return {
        "pronto": pronto,
        "estado": estado,
        "amostra": amostra,
        "dias_distintos": dias,
        "ligas_distintas": ligas,
        "inicio": validas[0]["criado_em"] if validas else None,
        "fim": validas[-1]["criado_em"] if validas else None,
        "minimo_dias": int(minimo_dias),
        "minimo_ligas": int(minimo_ligas),
        "janela_maxima": int(janela_maxima),
        "limite_exposicoes": limite_exposicoes,
        "integridade_coorte": diagnostico,
    }


def resumir_cobertura_amostra_calibracao(
    conexao, mercado, regra_versao, limites_risco,
    somente_executaveis=False,
):
    fingerprint = fingerprint_vinculado_no_banco(conexao, regra_versao)
    linha = conexao.execute(
        """
        SELECT COUNT(DISTINCT s.partida_id) AS historicas
        FROM sinais s
        JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado=? AND s.regra_versao=?
          AND s.status='aprovado'
          AND s.odd BETWEEN ? AND ?
          AND r.resultado IN ('green', 'half_green', 'red', 'half_red')
        """,
        (
            mercado,
            regra_versao,
            limites_risco.odd_minima,
            limites_risco.odd_maxima,
        ),
    ).fetchone()
    historicas = int(linha[0] or 0)
    candidatas_vinculadas = contar_exposicoes_independentes(
        conexao,
        mercado,
        regra_versao,
        limites_risco,
        regra_fingerprint=fingerprint,
        somente_executaveis=somente_executaveis,
    )
    if candidatas_vinculadas:
        coorte = carregar_coorte_independente(
            conexao,
            mercado,
            regra_versao,
            limites_risco,
            candidatas_vinculadas,
            janela="primeiros",
            somente_executaveis=somente_executaveis,
        )
        vinculadas = len(coorte["validas"])
        diagnostico = coorte["diagnostico"]
    else:
        vinculadas = 0
        diagnostico = {
            "pendentes": 0,
            "invalidas": 0,
            "pendentes_ou_invalidas": 0,
        }
    return {
        "historicas": historicas,
        "vinculadas": vinculadas,
        "candidatas_vinculadas": candidatas_vinculadas,
        "pendentes_vinculadas": diagnostico["pendentes"],
        "invalidas_vinculadas": diagnostico["invalidas"],
        "legado_excluido": max(historicas - vinculadas, 0),
        "fingerprint_disponivel": fingerprint is not None,
        "populacao": (
            POPULACAO_CALIBRACAO_EXECUTAVEL
            if somente_executaveis else "sinais_elegiveis_para_alerta"
        ),
        "cotacao_executavel_obrigatoria": bool(somente_executaveis),
        "fonte_odds_exigida": (
            FONTE_COTACAO_EXECUTAVEL_OFICIAL
            if somente_executaveis else None
        ),
        "bookmaker_odds_exigida": (
            BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL
            if somente_executaveis else None
        ),
    }


def fingerprint_amostra(resultados):
    campos = (
        "id", "partida_id", "criado_em", "pontuacao_tecnica", "odd",
        "resultado_original", "resultado", "retorno_unidades",
        "encerrado_em",
    )
    if any(item.get("custodia_cotacao_hash") for item in resultados):
        campos = (*campos, "custodia_cotacao_hash")
    carga = [
        {campo: item.get(campo) for campo in campos}
        for item in resultados
    ]
    serializado = json.dumps(
        carga,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serializado).hexdigest()


def auditar_particao_temporal(
    resultados,
    proporcao_desenvolvimento=0.7,
    tamanho_desenvolvimento=None,
):
    resultados = list(resultados or [])
    motivos = []
    try:
        proporcao = float(proporcao_desenvolvimento)
    except (TypeError, ValueError):
        proporcao = 0.7
        motivos.append("proporcao_desenvolvimento_invalida")
    if not 0 < proporcao < 1:
        proporcao = 0.7
        motivos.append("proporcao_desenvolvimento_invalida")
    ids = [item.get("id") for item in resultados]
    partidas = [item.get("partida_id") for item in resultados]
    if any(item is None for item in ids) or len(set(ids)) != len(ids):
        motivos.append("ids_ausentes_ou_duplicados")
    if any(item is None for item in partidas) or len(set(partidas)) != len(
        partidas
    ):
        motivos.append("partidas_ausentes_ou_duplicadas")
    instantes = []
    for item in resultados:
        try:
            instantes.append(
                datetime.fromisoformat(item["criado_em"]).timestamp()
            )
        except (KeyError, OSError, TypeError, ValueError):
            instantes.append(None)
    if any(item is None for item in instantes):
        motivos.append("exposicoes_temporais_invalidas")
        ordenada = False
    else:
        ordenada = all(
            anterior <= posterior
            for anterior, posterior in zip(instantes, instantes[1:])
        )
        if not ordenada:
            motivos.append("amostra_fora_de_ordem_cronologica")
    tamanho_fixo = None
    if tamanho_desenvolvimento is not None:
        try:
            tamanho_fixo = int(tamanho_desenvolvimento)
        except (TypeError, ValueError):
            tamanho_fixo = None
            motivos.append("tamanho_desenvolvimento_invalido")
        if tamanho_fixo is not None and tamanho_fixo <= 0:
            tamanho_fixo = None
            motivos.append("tamanho_desenvolvimento_invalido")
    corte = (
        min(tamanho_fixo, len(resultados))
        if tamanho_fixo is not None
        else int(len(resultados) * proporcao)
    )
    desenvolvimento = resultados[:corte]
    validacao = resultados[corte:]
    ids_desenvolvimento = {item.get("id") for item in desenvolvimento}
    ids_validacao = {item.get("id") for item in validacao}
    partidas_desenvolvimento = {
        item.get("partida_id") for item in desenvolvimento
    }
    partidas_validacao = {item.get("partida_id") for item in validacao}
    sobreposicao = bool(
        ids_desenvolvimento & ids_validacao
        or partidas_desenvolvimento & partidas_validacao
    )
    if sobreposicao:
        motivos.append("sobreposicao_desenvolvimento_validacao")
    return {
        "saudavel": not motivos,
        "motivos": motivos,
        "total": len(resultados),
        "desenvolvimento": len(desenvolvimento),
        "validacao": len(validacao),
        "proporcao_desenvolvimento": proporcao,
        "tamanho_desenvolvimento_fixo": tamanho_fixo,
        "ordenada": ordenada,
        "sobreposicao": sobreposicao,
        "ultimo_desenvolvimento_em": (
            desenvolvimento[-1].get("criado_em")
            if desenvolvimento else None
        ),
        "primeiro_validacao_em": (
            validacao[0].get("criado_em") if validacao else None
        ),
        "chave_temporal": "criado_em_primeira_exposicao",
        "fingerprint_desenvolvimento": fingerprint_amostra(
            desenvolvimento
        ),
        "fingerprint_validacao": fingerprint_amostra(validacao),
    }


def auditar_particoes_calibracao(
    conexao, mercados, regra_versao, limites_risco, janela_maxima=100,
    somente_executaveis=False,
):
    detalhes = {}
    for mercado in mercados:
        coorte = carregar_coorte_independente(
            conexao,
            mercado,
            regra_versao,
            limites_risco,
            max(int(janela_maxima), LIMITE_EXPOSICOES_CALIBRACAO),
            janela="primeiros",
            alvo_validas=int(janela_maxima),
            somente_executaveis=somente_executaveis,
        )
        amostra = coorte["validas"]
        detalhes[mercado] = auditar_particao_temporal(
            amostra, tamanho_desenvolvimento=70
        )
    inconsistentes = [
        mercado
        for mercado, auditoria in detalhes.items()
        if not auditoria["saudavel"]
    ]
    return {
        "saudavel": not inconsistentes,
        "inconsistentes": inconsistentes,
        "detalhes": detalhes,
    }


def auditar_particoes_calibracao_por_mercado(
    conexao,
    regras_por_mercado,
    limites_risco,
    janela_maxima=100,
    somente_executaveis=False,
):
    detalhes = {}
    for mercado, regra_versao in sorted(
        (regras_por_mercado or {}).items()
    ):
        coorte = carregar_coorte_independente(
            conexao,
            mercado,
            regra_versao,
            limites_risco,
            max(int(janela_maxima), LIMITE_EXPOSICOES_CALIBRACAO),
            janela="primeiros",
            alvo_validas=int(janela_maxima),
            somente_executaveis=somente_executaveis,
        )
        amostra = coorte["validas"]
        auditoria = auditar_particao_temporal(
            amostra, tamanho_desenvolvimento=70
        )
        auditoria["regra_versao"] = regra_versao
        detalhes[mercado] = auditoria
    inconsistentes = [
        mercado
        for mercado, auditoria in detalhes.items()
        if not auditoria["saudavel"]
    ]
    return {
        "saudavel": not inconsistentes,
        "inconsistentes": inconsistentes,
        "detalhes": detalhes,
        "regras_por_mercado": dict(regras_por_mercado or {}),
    }


def auditar_frescor_calibracoes(
    conexao, regra_versao, limites_risco, janela_maxima=300,
    mercado=None, somente_ativas=True, janela_modelo=100,
    politica_versao=None, somente_executaveis=False,
):
    """Confere se calibrações representam a amostra exata disponível."""
    linhas = conexao.execute(
        """
        SELECT mercado, ativa, atualizado_em, amostra, modelo_json
        FROM calibracoes
        WHERE regra_versao=?
          AND (? IS NULL OR mercado=?)
          AND (?=0 OR ativa=1)
        ORDER BY mercado
        """,
        (
            regra_versao,
            mercado,
            mercado,
            int(bool(somente_ativas)),
        ),
    ).fetchall()
    detalhes = []
    for linha in linhas:
        cobertura = resumir_cobertura_amostra_calibracao(
            conexao,
            linha["mercado"],
            regra_versao,
            limites_risco,
            somente_executaveis=somente_executaveis,
        )
        amostra_total_esperada = int(cobertura["vinculadas"])
        coorte_modelo = carregar_coorte_independente(
            conexao,
            linha["mercado"],
            regra_versao,
            limites_risco,
            max(int(janela_maxima), int(janela_modelo)),
            janela="primeiros",
            alvo_validas=int(janela_modelo),
            somente_executaveis=somente_executaveis,
        )
        amostra_modelo = coorte_modelo["validas"]
        amostra_monitoramento = carregar_monitoramento_independente(
            conexao,
            linha["mercado"],
            regra_versao,
            limites_risco,
            janela_maxima,
            somente_executaveis=somente_executaveis,
        )["validas"]
        amostra_esperada = len(amostra_modelo)
        amostra_registrada = int(linha["amostra"] or 0)
        ultimo = (
            amostra_monitoramento[-1]["encerrado_em"]
            if amostra_monitoramento else None
        )
        atualizado = linha["atualizado_em"]
        resultado_posterior = False
        if ultimo and atualizado:
            try:
                resultado_posterior = (
                    datetime.fromisoformat(ultimo)
                    > datetime.fromisoformat(atualizado)
                )
            except (TypeError, ValueError):
                resultado_posterior = True
        elif ultimo and not atualizado:
            resultado_posterior = True
        try:
            modelo = json.loads(linha["modelo_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            modelo = {}
        fingerprint_atual = fingerprint_amostra(amostra_modelo)
        fingerprint_modelo = modelo.get("amostra_fingerprint")
        fingerprint_confere = fingerprint_modelo == fingerprint_atual
        monitoramento_fingerprint_atual = fingerprint_amostra(
            amostra_monitoramento
        )
        total_modelo = modelo.get("amostra_total_disponivel")
        fingerprint_monitoramento = modelo.get(
            "monitoramento_fingerprint"
        )
        # Compatibilidade transitória somente antes do congelamento. A partir
        # do 100º resultado, o estado posterior precisa estar explicitamente
        # vinculado ao modelo para detectar qualquer alteração ou nova chegada.
        monitoramento_confere = (
            (
                amostra_total_esperada < int(janela_modelo)
                and total_modelo is None
                and fingerprint_monitoramento is None
            )
            or (
                total_modelo == amostra_total_esperada
                and fingerprint_monitoramento
                == monitoramento_fingerprint_atual
            )
        )
        politica_confere = (
            politica_versao is None
            or modelo.get("politica_versao") == politica_versao
        )
        desatualizada = (
            amostra_registrada != amostra_esperada
            or resultado_posterior
            or not fingerprint_confere
            or not monitoramento_confere
            or not politica_confere
        )
        detalhes.append(
            {
                "mercado": linha["mercado"],
                "ativa": bool(linha["ativa"]),
                "amostra_registrada": amostra_registrada,
                "amostra_esperada": amostra_esperada,
                "amostra_total_esperada": amostra_total_esperada,
                "atualizado_em": atualizado,
                "ultimo_resultado_em": ultimo,
                "fingerprint_confere": fingerprint_confere,
                "monitoramento_confere": monitoramento_confere,
                "politica_confere": politica_confere,
                "cotacao_executavel_obrigatoria": bool(
                    somente_executaveis
                ),
                "desatualizada": desatualizada,
            }
        )
    desatualizadas = sum(item["desatualizada"] for item in detalhes)
    ativas = sum(item["ativa"] for item in detalhes)
    inativas = len(detalhes) - ativas
    desatualizadas_ativas = sum(
        item["ativa"] and item["desatualizada"] for item in detalhes
    )
    desatualizadas_inativas = sum(
        not item["ativa"] and item["desatualizada"] for item in detalhes
    )
    return {
        "ativas": int(ativas),
        "inativas": int(inativas),
        "desatualizadas": int(desatualizadas),
        "desatualizadas_ativas": int(desatualizadas_ativas),
        "desatualizadas_inativas": int(desatualizadas_inativas),
        "saudavel": desatualizadas == 0,
        "detalhes": detalhes,
    }


def auditar_frescor_calibracoes_por_mercado(
    conexao,
    regras_por_mercado,
    limites_risco,
    janela_maxima=300,
    somente_ativas=True,
    janela_modelo=100,
    politica_versao=None,
    somente_executaveis=False,
):
    detalhes = []
    for mercado, regra_versao in sorted(
        (regras_por_mercado or {}).items()
    ):
        parcial = auditar_frescor_calibracoes(
            conexao,
            regra_versao,
            limites_risco,
            janela_maxima=janela_maxima,
            mercado=mercado,
            somente_ativas=somente_ativas,
            janela_modelo=janela_modelo,
            politica_versao=politica_versao,
            somente_executaveis=somente_executaveis,
        )
        for item in parcial["detalhes"]:
            detalhe = dict(item)
            detalhe["regra_versao"] = regra_versao
            detalhes.append(detalhe)
    desatualizadas = sum(
        bool(item.get("desatualizada")) for item in detalhes
    )
    ativas = sum(bool(item.get("ativa")) for item in detalhes)
    desatualizadas_ativas = sum(
        bool(item.get("ativa")) and bool(item.get("desatualizada"))
        for item in detalhes
    )
    desatualizadas_inativas = sum(
        not bool(item.get("ativa")) and bool(item.get("desatualizada"))
        for item in detalhes
    )
    return {
        "ativas": int(ativas),
        "inativas": int(len(detalhes) - ativas),
        "desatualizadas": int(desatualizadas),
        "desatualizadas_ativas": int(desatualizadas_ativas),
        "desatualizadas_inativas": int(desatualizadas_inativas),
        "saudavel": desatualizadas == 0,
        "detalhes": detalhes,
        "regras_por_mercado": dict(regras_por_mercado or {}),
    }
