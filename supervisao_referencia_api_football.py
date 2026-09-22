"""Supervisiona a referencia multibookmaker da API-Football em sombra.

A ausencia de outra bookmaker e um resultado normal. A supervisao somente
degrada quando a telemetria contradiz o que foi persistido ou quando a camada
observacional declara algum efeito operacional.
"""

import json
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


VERSAO = "supervisao-referencia-api-football-sombra-v3-capacidade"
VERSAO_FONTE = "api-football-referencia-sombra-v1"
MERCADOS_SUPORTADOS = frozenset({
    "gol_ft", "gol_ht", "escanteios_ft_asiatico",
})
EFEITOS_PROIBIDOS = (
    "aplicacao_sinais",
    "altera_calibracao",
    "telegram",
    "promocao_automatica",
)
MOTIVOS_TERMINAIS_ANTES_CONSULTA = frozenset({
    "fonte_desativada",
    "cliente_sem_referencia_independente",
    "associacao_api_ou_placar_incompativel",
})


def _identidade(valor):
    texto = unicodedata.normalize(
        "NFKD", str(valor or "").strip()
    ).casefold()
    return "".join(
        caractere for caractere in texto
        if caractere.isalnum() and not unicodedata.combining(caractere)
    )


def _inteiro_nao_negativo(valor):
    return bool(
        isinstance(valor, int)
        and not isinstance(valor, bool)
        and valor >= 0
    )


def _base(janela_horas):
    return {
        "versao": VERSAO,
        "versao_fonte": VERSAO_FONTE,
        "saudavel": True,
        "estado": "aguardando_tentativa",
        "motivo": None,
        "severidade": "informativa",
        "requer_atencao": False,
        "janela_horas": float(janela_horas),
        "snapshots_avaliados": 0,
        "partidas_distintas": 0,
        "tentativas": 0,
        "tentativas_sem_referencia": 0,
        "referencias_disponiveis": 0,
        "mercados_retornados": 0,
        "bookmakers_independentes": [],
        "consultas_rede_estimadas": 0,
        "consultas_rede_evitadas": 0,
        "mercados_sem_identidade_bookmaker": [],
        "por_motivo": {},
        "por_motivo_mercado": {},
        "por_mercado": {},
        "referencias_api_persistidas": 0,
        "violacoes_efeito": 0,
        "violacoes_estrutura": 0,
        "violacoes_persistencia": 0,
        "snapshots_invalidos": [],
        "ultima_tentativa_em": None,
        "consulta_truncada": False,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _agora_local_ingenuo(agora):
    agora = agora or datetime.now().astimezone()
    if agora.tzinfo is not None:
        agora = agora.astimezone().replace(tzinfo=None)
    return agora.replace(microsecond=0)


def _ofertas_api_football(estrutura):
    """Extrai somente ofertas de referencia API-Football com identidade."""
    encontradas = []

    def visitar(valor):
        if isinstance(valor, list):
            for item in valor:
                visitar(item)
            return
        if not isinstance(valor, dict):
            return
        fonte = _identidade(valor.get("fonte"))
        bookmaker = str(valor.get("bookmaker") or "").strip()
        identidade = valor.get("identidade_evento")
        if fonte == "apifootball" and bookmaker:
            valida = bool(
                _identidade(bookmaker) != "bet365"
                and isinstance(identidade, dict)
                and identidade.get("schema") == "identidade-evento-odd-v1"
                and identidade.get("confirmada") is True
                and _identidade(identidade.get("fonte")) == "apifootball"
                and str(identidade.get("evento_externo_id") or "").strip()
                and str(identidade.get("mandante_normalizado") or "").strip()
                and str(identidade.get("visitante_normalizado") or "").strip()
                and re.fullmatch(
                    r"\d+-\d+",
                    str(identidade.get("placar_normalizado") or ""),
                ) is not None
            )
            encontradas.append((bookmaker, valida))
        for item in valor.values():
            visitar(item)

    visitar(estrutura)
    return encontradas


def verificar_referencia_api_football_sombra(
    caminho_banco,
    *,
    agora=None,
    janela_horas=24,
    limite=10000,
):
    """Audita a rota V93 diretamente no SQLite aberto como somente leitura."""
    janela_horas = max(float(janela_horas), 1.0)
    limite = max(int(limite), 1)
    resultado = _base(janela_horas)
    caminho = Path(caminho_banco)
    if not caminho.exists():
        return {
            **resultado,
            "saudavel": False,
            "estado": "banco_ausente",
            "motivo": "sqlite_referencia_api_football_indisponivel",
            "severidade": "atencao",
            "requer_atencao": True,
        }

    agora = _agora_local_ingenuo(agora)
    desde = (agora - timedelta(hours=janela_horas)).isoformat()
    uri = f"file:{caminho.resolve().as_posix()}?mode=ro"
    try:
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        tabelas = {
            str(linha[0]) for linha in conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not {"snapshots", "odds"}.issubset(tabelas):
            raise sqlite3.DatabaseError("tabelas_referencia_ausentes")
        linhas = conexao.execute(
            """
            SELECT id, partida_id, coletado_em, qualidade_json
            FROM snapshots
            WHERE coletado_em >= ?
              AND instr(qualidade_json, 'api_football_referencia_sombra') > 0
            ORDER BY id DESC
            LIMIT ?
            """,
            (desde, limite + 1),
        ).fetchall()
        truncada = len(linhas) > limite
        linhas = linhas[:limite]
        ids = [int(linha["id"]) for linha in linhas]
        persistidas = {}
        if ids:
            marcadores = ",".join("?" for _ in ids)
            for linha in conexao.execute(
                f"""
                SELECT snapshot_id, estrutura_json
                FROM odds
                WHERE tipo='referencia_sombra'
                  AND snapshot_id IN ({marcadores})
                """,
                ids,
            ):
                try:
                    estrutura = json.loads(linha["estrutura_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    estrutura = {}
                ofertas = _ofertas_api_football(estrutura)
                if ofertas:
                    persistidas.setdefault(int(linha["snapshot_id"]), []).extend(
                        ofertas
                    )
    except (sqlite3.Error, OSError, ValueError) as erro:
        try:
            conexao.close()
        except (NameError, sqlite3.Error):
            pass
        return {
            **resultado,
            "saudavel": False,
            "estado": "consulta_sqlite_falhou",
            "motivo": "supervisao_referencia_api_football_sqlite_falhou",
            "severidade": "atencao",
            "requer_atencao": True,
            "erro": type(erro).__name__,
        }
    finally:
        try:
            conexao.close()
        except (NameError, sqlite3.Error):
            pass

    motivos = Counter()
    por_mercado = Counter()
    bookmakers = set()
    partidas = set()
    invalidos = set()
    tentativas = referencias = mercados_total = consultas = 0
    consultas_evitadas = 0
    sem_referencia = violacoes_efeito = violacoes_estrutura = 0
    violacoes_persistencia = referencias_persistidas = 0
    ultima_tentativa = None
    avaliados = 0
    motivos_mercado = Counter()
    mercados_sem_identidade = set()

    for linha in linhas:
        try:
            qualidade = json.loads(linha["qualidade_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        diagnostico = qualidade.get("api_football_referencia_sombra")
        if not isinstance(diagnostico, dict):
            continue
        if diagnostico.get("versao") != VERSAO_FONTE:
            continue
        avaliados += 1
        snapshot_id = int(linha["id"])
        partidas.add(int(linha["partida_id"]))
        motivo = str(diagnostico.get("motivo") or "ausente")
        motivos[motivo] += 1
        solicitados = diagnostico.get("mercados_solicitados") or []
        retornados = diagnostico.get("mercados_retornados") or []
        livros = diagnostico.get("bookmakers_independentes") or []
        pareado = diagnostico.get("pareado")
        consultas_item = diagnostico.get("consultas_rede_estimadas", 0)
        consultas_evitadas_item = diagnostico.get(
            "consultas_rede_evitadas", 0
        )
        sem_identidade_item = diagnostico.get(
            "mercados_sem_identidade_bookmaker", []
        )
        tentativa = bool(solicitados)
        if tentativa:
            tentativas += 1
            ultima_tentativa = max(
                ultima_tentativa or str(linha["coletado_em"]),
                str(linha["coletado_em"]),
            )
        if tentativa and not pareado:
            sem_referencia += 1
        if pareado is True:
            referencias += 1
        if any(
            diagnostico.get(chave) is not False
            for chave in EFEITOS_PROIBIDOS
        ):
            violacoes_efeito += 1
            invalidos.add(snapshot_id)
        estrutura_valida = bool(
            isinstance(diagnostico.get("ativa"), bool)
            and isinstance(pareado, bool)
            and isinstance(solicitados, list)
            and isinstance(retornados, list)
            and isinstance(livros, list)
            and _inteiro_nao_negativo(consultas_item)
            and _inteiro_nao_negativo(consultas_evitadas_item)
            and isinstance(sem_identidade_item, list)
            and set(solicitados).issubset(MERCADOS_SUPORTADOS)
            and len(solicitados) == len(set(solicitados))
            and set(retornados).issubset(set(solicitados))
            and len(retornados) == len(set(retornados))
            and len(livros) == len(set(livros))
            and all(
                str(livro or "").strip()
                and _identidade(livro) != "bet365"
                for livro in livros
            )
            and pareado is bool(retornados and livros)
            and consultas_item <= len(solicitados)
            and consultas_evitadas_item <= len(solicitados)
            and set(sem_identidade_item).issubset(set(solicitados))
            and len(sem_identidade_item) == len(set(sem_identidade_item))
        )
        detalhes = diagnostico.get("por_mercado") or {}
        if tentativa:
            terminou_antes_consulta = bool(
                motivo in MOTIVOS_TERMINAIS_ANTES_CONSULTA
                and consultas_item == 0
                and not retornados
                and not livros
                and pareado is False
                and isinstance(detalhes, dict)
                and not detalhes
            )
            if not terminou_antes_consulta:
                evitadas_detalhes = (
                    sum(
                        int(item.get("consulta_rede_evitada") is True)
                        for item in detalhes.values()
                        if isinstance(item, dict)
                    )
                    if isinstance(detalhes, dict) else -1
                )
                sem_identidade_detalhes = (
                    {
                        mercado
                        for mercado, item in detalhes.items()
                        if isinstance(item, dict)
                        and item.get("motivo")
                        == "fonte_live_sem_identidade_bookmaker"
                    }
                    if isinstance(detalhes, dict) else set()
                )
                estrutura_valida = bool(
                    estrutura_valida
                    and isinstance(detalhes, dict)
                    and set(detalhes) == set(solicitados)
                    and all(
                        isinstance(item, dict)
                        and item.get("versao") == VERSAO_FONTE
                        and item.get("mercado") == mercado
                        and _identidade(item.get("bookmaker_excluido"))
                        == "bet365"
                        and all(
                            item.get(chave) is False
                            for chave in (
                                "aplicacao_sinais", "telegram",
                                "promocao_automatica",
                            )
                        )
                        and isinstance(item.get(
                            "consulta_rede_realizada", False
                        ), bool)
                        and isinstance(item.get(
                            "consulta_rede_evitada", False
                        ), bool)
                        and not (
                            item.get("consulta_rede_realizada") is True
                            and item.get("consulta_rede_evitada") is True
                        )
                        and (
                            item.get("capacidade_referencia") is None
                            or (
                                isinstance(
                                    item.get("capacidade_referencia"), dict
                                )
                                and item["capacidade_referencia"].get(
                                    "versao"
                                )
                                == "api-football-referencia-capacidade-v1"
                                and all(
                                    item["capacidade_referencia"].get(chave)
                                    is False
                                    for chave in (
                                        "aplicacao_sinais", "telegram",
                                        "promocao_automatica",
                                    )
                                )
                            )
                        )
                        for mercado, item in detalhes.items()
                    )
                    and consultas_evitadas_item == evitadas_detalhes
                    and set(sem_identidade_item)
                    == sem_identidade_detalhes
                )
        if not estrutura_valida:
            violacoes_estrutura += 1
            invalidos.add(snapshot_id)

        persistidas_snapshot = persistidas.get(snapshot_id, [])
        nomes_persistidos = {
            _identidade(nome) for nome, valida in persistidas_snapshot if valida
        }
        persistencia_valida = bool(
            (pareado is True)
            == bool(nomes_persistidos)
            and (
                pareado is not True
                or bool({_identidade(item) for item in livros}
                        & nomes_persistidos)
            )
            and all(valida for _nome, valida in persistidas_snapshot)
        )
        if not persistencia_valida:
            violacoes_persistencia += 1
            invalidos.add(snapshot_id)
        referencias_persistidas += int(bool(nomes_persistidos))
        mercados_total += len(retornados)
        consultas += consultas_item
        consultas_evitadas += consultas_evitadas_item
        bookmakers.update(str(item).strip() for item in livros)
        mercados_sem_identidade.update(sem_identidade_item)
        if isinstance(detalhes, dict):
            for item in detalhes.values():
                if isinstance(item, dict):
                    motivos_mercado[
                        str(item.get("motivo") or "ausente")
                    ] += 1
        for mercado in retornados:
            por_mercado[mercado] += 1

    resultado.update({
        "snapshots_avaliados": avaliados,
        "partidas_distintas": len(partidas),
        "tentativas": tentativas,
        "tentativas_sem_referencia": sem_referencia,
        "referencias_disponiveis": referencias,
        "mercados_retornados": mercados_total,
        "bookmakers_independentes": sorted(bookmakers, key=_identidade),
        "consultas_rede_estimadas": consultas,
        "consultas_rede_evitadas": consultas_evitadas,
        "mercados_sem_identidade_bookmaker": sorted(
            mercados_sem_identidade
        ),
        "por_motivo": dict(sorted(motivos.items())),
        "por_motivo_mercado": dict(sorted(motivos_mercado.items())),
        "por_mercado": dict(sorted(por_mercado.items())),
        "referencias_api_persistidas": referencias_persistidas,
        "violacoes_efeito": violacoes_efeito,
        "violacoes_estrutura": violacoes_estrutura,
        "violacoes_persistencia": violacoes_persistencia,
        "snapshots_invalidos": sorted(invalidos)[:20],
        "ultima_tentativa_em": ultima_tentativa,
        "consulta_truncada": truncada,
    })
    if violacoes_efeito:
        resultado.update({
            "saudavel": False,
            "estado": "vazamento_operacional_declarado",
            "motivo": "referencia_api_football_declarou_efeito_operacional",
            "severidade": "critica",
            "requer_atencao": True,
        })
    elif violacoes_estrutura or violacoes_persistencia:
        resultado.update({
            "saudavel": False,
            "estado": "telemetria_inconsistente",
            "motivo": "referencia_api_football_sombra_inconsistente",
            "severidade": "atencao",
            "requer_atencao": True,
        })
    elif referencias:
        resultado["estado"] = "referencia_independente_persistida"
    elif consultas_evitadas or mercados_sem_identidade:
        resultado["estado"] = (
            "capacidade_bookmaker_indisponivel_observada"
        )
    elif tentativas:
        resultado["estado"] = "coletando_sem_bookmaker_alternativa"
    elif avaliados:
        resultado["estado"] = "aguardando_candidato_elegivel"
    return resultado
