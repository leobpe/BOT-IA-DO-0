"""Supervisiona a integridade da comparacao prospectiva de melhor preco.

A camada e estritamente observacional. Ausencia de pares nao e falha; somente
inconsistencia estrutural ou indicio declarado de efeito operacional exige
atencao. A verificacao abre o SQLite em modo somente leitura.
"""

import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from melhor_preco_sombra import (
    INTERVALO_FONTES_MAXIMO_SEGUNDOS,
    VERSAO as VERSAO_MEDIDOR,
    VERSAO_VALOR_JUSTO,
)
from validacao_resultado_valor_justo import (
    resumir_validacao_resultado_valor_justo,
    validar_politica_avaliacao_resultado,
)
from validacao_veto_preco_justo import resumir_validacao_veto_preco_justo
from valor_mercado import (
    MARGEM_BOOKMAKER_MAXIMA,
    MARGEM_BOOKMAKER_MINIMA,
    VALOR_ESPERADO_MINIMO,
)


VERSAO = "supervisao-melhor-preco-sombra-v3-veto-negativo"
EFEITOS_PROIBIDOS = (
    "aplicacao_sinais",
    "altera_calibracao",
    "telegram",
    "promocao_automatica",
)
ESTADOS_VALIDOS = frozenset({
    "nao_avaliado",
    "entrada_invalida",
    "mercado_nao_suportado",
    "cotacao_escolhida_nao_congelada",
    "proveniencia_escolhida_incompleta",
    "cotacao_escolhida_sem_frescor",
    "sem_referencia_independente_exata",
    "comparacao_independente_exata",
})
ESTADOS_VALOR_JUSTO = frozenset({
    "sem_referencia_sem_vig_sincronizada",
    "sem_desajuste_favoravel",
    "desajuste_favoravel_candidato",
})


def _identidade(valor):
    texto = unicodedata.normalize(
        "NFKD", str(valor or "").strip()
    ).casefold()
    return "".join(
        caractere for caractere in texto
        if caractere.isalnum() and not unicodedata.combining(caractere)
    )


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return numero if math.isfinite(numero) else None


def _interpretar_instante(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip()
    if texto.endswith("Z"):
        texto = f"{texto[:-1]}+00:00"
    try:
        instante = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if instante.tzinfo is None:
        instante = instante.astimezone()
    return instante.astimezone(timezone.utc)


def _inteiro_nao_negativo(valor):
    return bool(
        isinstance(valor, int)
        and not isinstance(valor, bool)
        and valor >= 0
    )


def _agora_local_ingenuo(agora):
    agora = agora or datetime.now().astimezone()
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    return agora.replace(microsecond=0)


def _tabelas(conexao):
    return {
        str(linha[0])
        for linha in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _base(janela_horas):
    return {
        "versao": VERSAO,
        "versao_medidor": VERSAO_MEDIDOR,
        "saudavel": True,
        "estado": "aguardando_observacao",
        "motivo": None,
        "severidade": "informativa",
        "requer_atencao": False,
        "janela_horas": float(janela_horas),
        "observacoes": 0,
        "partidas_distintas": 0,
        "comparacoes_independentes_exatas": 0,
        "comparacoes_com_referencia_separada": 0,
        "avaliacoes_valor_justo": 0,
        "desajustes_valor_justo_candidatos": 0,
        "referencias_separadas_recebidas": 0,
        "referencias_separadas_consultadas": 0,
        "snapshots_com_referencia_persistida": 0,
        "observacoes_em_snapshots_com_referencia": 0,
        "versoes_anteriores": 0,
        "por_estado": {},
        "violacoes_efeito": 0,
        "violacoes_estrutura": 0,
        "violacoes_ponte_persistencia": 0,
        "violacoes_valor_justo": 0,
        "violacoes_politica_resultado": 0,
        "ids_invalidos": [],
        "ultima_observacao_em": None,
        "consulta_truncada": False,
        "validacao_resultado_valor_justo": None,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _validar_comparacao(sombra):
    escolhida = sombra.get("cotacao_escolhida")
    alternativa = sombra.get("melhor_alternativa_independente")
    if not isinstance(escolhida, dict) or not isinstance(alternativa, dict):
        return False
    if alternativa.get("camada") not in {"operacional", "referencia_sombra"}:
        return False
    for campo in ("fonte", "bookmaker"):
        primeira = _identidade(escolhida.get(campo))
        segunda = _identidade(alternativa.get(campo))
        if not primeira or not segunda or primeira == segunda:
            return False
    odd_escolhida = _numero(escolhida.get("odd"))
    odd_alternativa = _numero(alternativa.get("odd"))
    diferenca = _numero(sombra.get("diferenca_odd"))
    if (
        odd_escolhida is None or odd_escolhida <= 1.0
        or odd_alternativa is None or odd_alternativa <= 1.0
        or diferenca is None
        or not math.isclose(
            diferenca,
            odd_alternativa - odd_escolhida,
            rel_tol=0.0,
            abs_tol=0.000001,
        )
    ):
        return False
    relacao = (
        "alternativa_melhor" if diferenca > 0.005
        else "escolhida_melhor" if diferenca < -0.005
        else "equivalentes"
    )
    return bool(
        sombra.get("relacao") == relacao
        and _inteiro_nao_negativo(
            sombra.get("alternativas_independentes_validas")
        )
        and sombra["alternativas_independentes_validas"] >= 1
    )


def _validar_valor_justo(sombra):
    valor = sombra.get("valor_justo_sombra")
    if not isinstance(valor, dict):
        return False, False, False
    if (
        valor.get("versao") != VERSAO_VALOR_JUSTO
        or valor.get("estado") not in ESTADOS_VALOR_JUSTO
        or not validar_politica_avaliacao_resultado(
            valor.get("avaliacao_resultado_sombra")
        )
        or any(valor.get(chave) is not False for chave in EFEITOS_PROIBIDOS)
        or valor.get("desajuste_favoravel") not in (True, False)
    ):
        return False, False, False
    limiar = _numero(valor.get("limiar_valor_esperado"))
    intervalo_maximo = _numero(
        valor.get("intervalo_fontes_maximo_segundos")
    )
    if (
        limiar is None
        or not math.isclose(
            limiar, VALOR_ESPERADO_MINIMO, rel_tol=0.0, abs_tol=1e-12
        )
        or intervalo_maximo is None
        or not math.isclose(
            intervalo_maximo,
            INTERVALO_FONTES_MAXIMO_SEGUNDOS,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    ):
        return False, False, False
    if valor["estado"] == "sem_referencia_sem_vig_sincronizada":
        return valor["desajuste_favoravel"] is False, False, False

    escolhida = sombra.get("cotacao_escolhida")
    referencia = valor.get("referencia")
    if not isinstance(escolhida, dict) or not isinstance(referencia, dict):
        return False, False, False
    if referencia.get("camada") not in {"operacional", "referencia_sombra"}:
        return False, False, False
    for campo in ("fonte", "bookmaker"):
        primeira = _identidade(escolhida.get(campo))
        segunda = _identidade(referencia.get(campo))
        if not primeira or not segunda or primeira == segunda:
            return False, False, False

    identidade_escolhida = valor.get("identidade_evento_escolhida")
    identidade_referencia = referencia.get("identidade_evento")
    sincronismo = valor.get("sincronismo_estado")
    if not all(isinstance(item, dict) for item in (
        identidade_escolhida, identidade_referencia, sincronismo,
    )):
        return False, False, False
    campos_estado = (
        "mandante_normalizado", "visitante_normalizado", "placar_normalizado"
    )
    if (
        identidade_escolhida.get("confirmada") is not True
        or identidade_referencia.get("confirmada") is not True
        or identidade_escolhida.get("schema") != "identidade-evento-odd-v1"
        or identidade_referencia.get("schema") != "identidade-evento-odd-v1"
        or _identidade(identidade_escolhida.get("fonte"))
        != _identidade(escolhida.get("fonte"))
        or _identidade(identidade_referencia.get("fonte"))
        != _identidade(referencia.get("fonte"))
        or sincronismo.get("comprovado") is not True
        or any(
            not _identidade(identidade_escolhida.get(campo))
            or identidade_escolhida.get(campo)
            != identidade_referencia.get(campo)
            or identidade_escolhida.get(campo) != sincronismo.get(campo)
            for campo in campos_estado[:2]
        )
        or re.fullmatch(
            r"\d+-\d+",
            str(identidade_escolhida.get("placar_normalizado") or ""),
        ) is None
        or identidade_escolhida.get("placar_normalizado")
        != identidade_referencia.get("placar_normalizado")
        or identidade_escolhida.get("placar_normalizado")
        != sincronismo.get("placar_normalizado")
    ):
        return False, False, False
    coletado_escolhida = _interpretar_instante(escolhida.get("coletado_em"))
    coletado_referencia = _interpretar_instante(
        referencia.get("coletado_em")
    )
    intervalo_declarado = _numero(
        sincronismo.get("intervalo_fontes_segundos")
    )
    intervalo_maximo_declarado = _numero(
        sincronismo.get("intervalo_maximo_segundos")
    )
    if coletado_escolhida is None or coletado_referencia is None:
        return False, False, False
    intervalo_calculado = abs(
        (coletado_escolhida - coletado_referencia).total_seconds()
    )
    if (
        intervalo_declarado is None
        or intervalo_maximo_declarado is None
        or intervalo_calculado > INTERVALO_FONTES_MAXIMO_SEGUNDOS
        or not math.isclose(
            intervalo_declarado, intervalo_calculado,
            rel_tol=0.0, abs_tol=0.001,
        )
        or not math.isclose(
            intervalo_maximo_declarado,
            INTERVALO_FONTES_MAXIMO_SEGUNDOS,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    ):
        return False, False, False

    odd = _numero(valor.get("odd_escolhida"))
    odd_comparacao = _numero(escolhida.get("odd"))
    probabilidade = _numero(
        valor.get("probabilidade_referencia_sem_vig")
    )
    probabilidade_referencia = _numero(
        referencia.get("probabilidade_selecao_sem_vig")
    )
    equilibrio = _numero(
        valor.get("probabilidade_equilibrio_odd_escolhida")
    )
    vantagem = _numero(
        valor.get("vantagem_probabilidade_pontos_percentuais")
    )
    valor_esperado = _numero(valor.get("valor_esperado_referencia"))
    margem = _numero(referencia.get("margem_bookmaker"))
    if (
        odd is None or odd <= 1.0
        or odd_comparacao is None
        or not math.isclose(odd, odd_comparacao, rel_tol=0.0, abs_tol=1e-6)
        or probabilidade is None or not 0.0 < probabilidade < 1.0
        or probabilidade_referencia is None
        or not math.isclose(
            probabilidade, probabilidade_referencia,
            rel_tol=0.0, abs_tol=1e-8,
        )
        or equilibrio is None
        or not math.isclose(
            equilibrio, 1.0 / odd, rel_tol=0.0, abs_tol=1e-8
        )
        or vantagem is None
        or not math.isclose(
            vantagem, (probabilidade - equilibrio) * 100.0,
            rel_tol=0.0, abs_tol=0.0001,
        )
        or valor_esperado is None
        or not math.isclose(
            valor_esperado, odd * probabilidade - 1.0,
            rel_tol=0.0, abs_tol=1e-8,
        )
        or margem is None
        or margem < MARGEM_BOOKMAKER_MINIMA - 1e-12
        or margem > MARGEM_BOOKMAKER_MAXIMA + 1e-12
    ):
        return False, False, False
    favoravel = bool(
        valor_esperado + 1e-12 >= VALOR_ESPERADO_MINIMO
    )
    estado_esperado = (
        "desajuste_favoravel_candidato"
        if favoravel else "sem_desajuste_favoravel"
    )
    valido = bool(
        valor["estado"] == estado_esperado
        and valor["desajuste_favoravel"] is favoravel
    )
    return valido, True, favoravel


def verificar_integridade_melhor_preco_sombra(
    caminho_banco,
    *,
    agora=None,
    janela_horas=24,
    limite=10000,
):
    """Resume a coorte atual e acusa apenas inconsistencias comprovadas."""
    janela_horas = max(float(janela_horas), 1.0)
    limite = max(int(limite), 1)
    resultado = _base(janela_horas)
    caminho = Path(caminho_banco)
    if not caminho.exists():
        return {
            **resultado,
            "saudavel": False,
            "estado": "banco_ausente",
            "motivo": "sqlite_melhor_preco_indisponivel",
            "severidade": "atencao",
            "requer_atencao": True,
        }

    agora = _agora_local_ingenuo(agora)
    desde = (agora - timedelta(hours=janela_horas)).isoformat()
    uri = f"file:{caminho.resolve().as_posix()}?mode=ro"
    try:
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        tabelas = _tabelas(conexao)
        if "sinais" not in tabelas:
            raise sqlite3.DatabaseError("tabela_sinais_ausente")
        linhas = conexao.execute(
            """
            SELECT id, partida_id, snapshot_id, criado_em, mercado,
                   features_json
            FROM sinais
            WHERE criado_em >= ?
              AND instr(features_json, 'melhor_preco_sombra') > 0
            ORDER BY id DESC
            LIMIT ?
            """,
            (desde, limite + 1),
        ).fetchall()
        truncada = len(linhas) > limite
        linhas = linhas[:limite]

        snapshots_referencia = set()
        if "odds" in tabelas:
            snapshots_referencia = {
                int(linha[0])
                for linha in conexao.execute(
                    """
                    SELECT DISTINCT o.snapshot_id
                    FROM odds o
                    JOIN sinais s ON s.snapshot_id=o.snapshot_id
                    WHERE o.tipo='referencia_sombra'
                      AND s.criado_em >= ?
                      AND json_valid(s.features_json)=1
                      AND json_extract(
                          s.features_json,
                          '$.melhor_preco_sombra.versao'
                      )=?
                    """,
                    (desde, VERSAO_MEDIDOR),
                )
            }
        validacao_resultados = resumir_validacao_resultado_valor_justo(
            conexao
        )
        validacao_veto = resumir_validacao_veto_preco_justo(conexao)
    except (sqlite3.Error, OSError, ValueError) as erro:
        try:
            conexao.close()
        except (NameError, sqlite3.Error):
            pass
        return {
            **resultado,
            "saudavel": False,
            "estado": "consulta_sqlite_falhou",
            "motivo": "supervisao_melhor_preco_sqlite_falhou",
            "severidade": "atencao",
            "requer_atencao": True,
            "erro": type(erro).__name__,
        }
    finally:
        try:
            conexao.close()
        except (NameError, sqlite3.Error):
            pass

    estados = Counter()
    partidas = set()
    invalidos = set()
    observacoes = []
    violacoes_efeito = 0
    violacoes_estrutura = 0
    violacoes_ponte = 0
    violacoes_valor_justo = 0
    violacoes_politica_resultado = 0
    comparacoes = 0
    comparacoes_referencia = 0
    avaliacoes_valor_justo = 0
    desajustes_valor_justo = 0
    recebidas = 0
    consultadas = 0
    em_snapshot_referencia = 0
    anteriores = 0

    for linha in linhas:
        try:
            features = json.loads(linha["features_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        sombra = (
            features.get("melhor_preco_sombra")
            if isinstance(features, dict) else None
        )
        if not isinstance(sombra, dict):
            continue
        if sombra.get("versao") != VERSAO_MEDIDOR:
            anteriores += 1
            continue
        observacoes.append((linha, sombra))
        partidas.add(int(linha["partida_id"]))
        estado = str(sombra.get("estado") or "")
        estados[estado or "ausente"] += 1
        valor_justo = sombra.get("valor_justo_sombra")
        politica_resultado_valida = bool(
            isinstance(valor_justo, dict)
            and validar_politica_avaliacao_resultado(
                valor_justo.get("avaliacao_resultado_sombra")
            )
        )
        if not politica_resultado_valida:
            violacoes_politica_resultado += 1
            invalidos.add(int(linha["id"]))
        efeito_valor_justo = bool(
            isinstance(valor_justo, dict)
            and any(
                valor_justo.get(chave) is not False
                for chave in EFEITOS_PROIBIDOS
            )
        )
        if (
            any(sombra.get(chave) is not False for chave in EFEITOS_PROIBIDOS)
            or efeito_valor_justo
        ):
            violacoes_efeito += 1
            invalidos.add(int(linha["id"]))

        contadores = (
            sombra.get("ofertas_exatas_validas"),
            sombra.get("ofertas_exatas_validas_operacionais"),
            sombra.get("ofertas_exatas_validas_referencia_sombra"),
            sombra.get("alternativas_independentes_validas"),
        )
        estrutura_valida = bool(
            estado in ESTADOS_VALIDOS
            and all(_inteiro_nao_negativo(valor) for valor in contadores)
            and contadores[0] == contadores[1] + contadores[2]
            and isinstance(sombra.get("referencia_sombra_recebida"), bool)
            and isinstance(sombra.get("referencia_sombra_consultada"), bool)
        )
        valor_valido, valor_avaliado, valor_favoravel = (
            _validar_valor_justo(sombra)
        )
        avaliacoes_valor_justo += int(valor_avaliado)
        desajustes_valor_justo += int(valor_favoravel)
        if not valor_valido:
            violacoes_valor_justo += 1
            estrutura_valida = False
        if estado == "comparacao_independente_exata":
            comparacoes += 1
            estrutura_valida = estrutura_valida and _validar_comparacao(sombra)
            if (
                isinstance(sombra.get("melhor_alternativa_independente"), dict)
                and sombra["melhor_alternativa_independente"].get("camada")
                == "referencia_sombra"
            ):
                comparacoes_referencia += 1
        if not estrutura_valida:
            violacoes_estrutura += 1
            invalidos.add(int(linha["id"]))

        recebida = sombra.get("referencia_sombra_recebida") is True
        consultada = sombra.get("referencia_sombra_consultada") is True
        recebidas += int(recebida)
        consultadas += int(consultada)
        snapshot_id = linha["snapshot_id"]
        com_referencia = bool(
            snapshot_id is not None
            and int(snapshot_id) in snapshots_referencia
        )
        em_snapshot_referencia += int(com_referencia)
        if com_referencia != recebida:
            violacoes_ponte += 1
            invalidos.add(int(linha["id"]))

    resultado.update({
        "observacoes": len(observacoes),
        "partidas_distintas": len(partidas),
        "comparacoes_independentes_exatas": comparacoes,
        "comparacoes_com_referencia_separada": comparacoes_referencia,
        "avaliacoes_valor_justo": avaliacoes_valor_justo,
        "desajustes_valor_justo_candidatos": desajustes_valor_justo,
        "referencias_separadas_recebidas": recebidas,
        "referencias_separadas_consultadas": consultadas,
        "snapshots_com_referencia_persistida": len(snapshots_referencia),
        "observacoes_em_snapshots_com_referencia": em_snapshot_referencia,
        "versoes_anteriores": anteriores,
        "por_estado": dict(sorted(estados.items())),
        "violacoes_efeito": violacoes_efeito,
        "violacoes_estrutura": violacoes_estrutura,
        "violacoes_ponte_persistencia": violacoes_ponte,
        "violacoes_valor_justo": violacoes_valor_justo,
        "violacoes_politica_resultado": violacoes_politica_resultado,
        "ids_invalidos": sorted(invalidos)[:20],
        "ultima_observacao_em": (
            observacoes[0][0]["criado_em"] if observacoes else None
        ),
        "consulta_truncada": truncada,
        "validacao_resultado_valor_justo": validacao_resultados,
        "validacao_veto_preco_justo": validacao_veto,
    })
    if violacoes_efeito:
        resultado.update({
            "saudavel": False,
            "estado": "vazamento_operacional_declarado",
            "motivo": "melhor_preco_sombra_declarou_efeito_operacional",
            "severidade": "critica",
            "requer_atencao": True,
        })
    elif (
        violacoes_estrutura or violacoes_ponte
        or violacoes_politica_resultado
        or not validacao_resultados.get("saudavel", False)
        or not validacao_veto.get("saudavel", False)
    ):
        resultado.update({
            "saudavel": False,
            "estado": (
                "veto_preco_justo_inconsistente"
                if not validacao_veto.get("saudavel", False)
                else "resultado_valor_justo_inconsistente"
                if not validacao_resultados.get("saudavel", False)
                else "telemetria_inconsistente"
            ),
            "motivo": (
                validacao_veto.get("motivo")
                if not validacao_veto.get("saudavel", False)
                else validacao_resultados.get("motivo")
                if not validacao_resultados.get("saudavel", False)
                else "melhor_preco_sombra_inconsistente"
            ),
            "severidade": "atencao",
            "requer_atencao": True,
        })
    elif comparacoes:
        resultado["estado"] = "comparando_preco_exato"
    elif recebidas:
        resultado["estado"] = "referencia_recebida_sem_par_exato"
    elif observacoes:
        resultado["estado"] = "coletando_sem_referencia_independente"
    return resultado
