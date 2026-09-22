import json
import os
import sqlite3
import time
import unicodedata
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from configuracao import obter_limites_api
from contexto_pre_jogo import resumir_contexto_pre_jogo
from processo_monitor import TravaInstancia, gravar_json_atomico, trava_em_uso


BASE_URL = "https://v3.football.api-sports.io"
CACHE_GERAL_SEGUNDOS = 600
CACHE_DETALHE_SEGUNDOS = 900
CACHE_EVENTOS_SEGUNDOS = 60
CACHE_JOGADORES_AO_VIVO_SEGUNDOS = 300
CACHE_FIXTURES_AO_VIVO_DETALHADAS_SEGUNDOS = 60
CACHE_RESULTADOS_SEGUNDOS = 1800
CACHE_ODDS_AO_VIVO_SEGUNDOS = 300
CAPACIDADE_REFERENCIA_SONDAGEM_SEGUNDOS = 6 * 3600
CAPACIDADE_REFERENCIA_VERSAO = 1
CACHE_ODDS_PRE_JOGO_SEGUNDOS = 12 * 3600
CACHE_FIXTURES_DIA_SEGUNDOS = 15 * 60
CACHE_ODDS_PRE_LIVE_DIA_SEGUNDOS = 10 * 60
CACHE_CATALOGO_ODDS_SEGUNDOS = 86400
CACHE_CONTEXTO_DINAMICO_SEGUNDOS = 1800
CACHE_CONTEXTO_PRE_JOGO_SEGUNDOS = 12 * 3600
ORCAMENTO_CONTEXTO_POR_JOGO_SEGUNDOS = 8.0
LIMITE_VAZIAS_CONSECUTIVAS_ODDS_1T = 12
SUSPENSAO_ODDS_1T_SEGUNDOS = 6 * 3600
BET_ESCANTEIOS_ASIATICOS_FT = 32
BET_ESCANTEIOS_ASIATICOS_1T = 51
BET_GOLS_TOTAL_FT = 25
BET_GOLS_TOTAL_HT = 49
BETS_PROXIMO_GOL_POR_TOTAL = {
    0: 73,
    1: 84,
    2: 92,
    3: 109,
    4: 112,
    5: 127,
    6: 132,
}
MERCADOS_ODDS_LIVE_ESPERADOS = {
    BET_GOLS_TOTAL_FT: "Match Goals",
    BET_GOLS_TOTAL_HT: "Over/Under (1st Half)",
    BET_ESCANTEIOS_ASIATICOS_FT: "Asian Corners",
    BET_ESCANTEIOS_ASIATICOS_1T: "Asian Corners (1st Half)",
    73: "Which team will score the 1st goal?",
    84: "Which team will score the 2nd goal?",
    92: "Which team will score the 3rd goal?",
    109: "Which team will score the 4th goal?",
    112: "Which team will score the 5th goal?",
    127: "Which team will score the 6th goal?",
    132: "Which team will score the 7th goal?",
}
CACHE_TTL_POR_CATEGORIA = {
    "geral": CACHE_GERAL_SEGUNDOS,
    "detalhe": CACHE_DETALHE_SEGUNDOS,
    "eventos": CACHE_EVENTOS_SEGUNDOS,
    "jogadores": CACHE_JOGADORES_AO_VIVO_SEGUNDOS,
    "live_detalhado": CACHE_FIXTURES_AO_VIVO_DETALHADAS_SEGUNDOS,
    "resultado": CACHE_RESULTADOS_SEGUNDOS,
    "odds": CACHE_ODDS_AO_VIVO_SEGUNDOS,
    "odds_pre_jogo": CACHE_ODDS_PRE_JOGO_SEGUNDOS,
    "catalogo": CACHE_CATALOGO_ODDS_SEGUNDOS,
    "contexto": CACHE_CONTEXTO_PRE_JOGO_SEGUNDOS,
}
CACHE_LIMPEZA_EXPIRADOS_INTERVALO_SEGUNDOS = 300


def _estado_capacidade_referencia_por_bet_padrao():
    return {
        "amostras": 0,
        "amostras_com_identidade": 0,
        "amostras_sem_identidade": 0,
        "sem_identidade_consecutivas": 0,
        "fixtures_ultima_amostra": 0,
        "fixtures_com_bookmakers": 0,
        "bookmakers_disponiveis": [],
        "bookmakers_independentes": [],
        "identidade_bookmaker_disponivel": None,
        "ultima_amostra_em": None,
        "proxima_sondagem_em": None,
        "consultas_referencia_suprimidas": 0,
        "ultima_supressao_em": None,
    }


def _estado_capacidade_referencia_padrao():
    bet_ids = (
        BET_GOLS_TOTAL_FT,
        BET_GOLS_TOTAL_HT,
        BET_ESCANTEIOS_ASIATICOS_FT,
    )
    return {
        "versao": CAPACIDADE_REFERENCIA_VERSAO,
        "atualizado_em": None,
        "por_bet": {
            str(bet_id): _estado_capacidade_referencia_por_bet_padrao()
            for bet_id in bet_ids
        },
    }


def _identidade_bookmaker(valor):
    texto = unicodedata.normalize(
        "NFKD", str(valor or "").strip()
    ).casefold()
    return "".join(
        caractere for caractere in texto
        if caractere.isalnum() and not unicodedata.combining(caractere)
    )


def diagnosticar_capacidade_referencia_payload(
    itens, bookmaker_excluido="bet365"
):
    """Mede se o payload permite provar uma bookmaker independente."""
    fixtures = fixtures_com_bookmakers = 0
    nomes = set()
    independentes = set()
    excluido = _identidade_bookmaker(bookmaker_excluido)
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        fixtures += 1
        bookmakers = item.get("bookmakers") or []
        nomes_fixture = set()
        for bookmaker in bookmakers:
            if not isinstance(bookmaker, dict):
                continue
            nome = str(bookmaker.get("name") or "").strip()
            if not nome:
                continue
            nomes_fixture.add(nome)
            nomes.add(nome)
            if _identidade_bookmaker(nome) != excluido:
                independentes.add(nome)
        if nomes_fixture:
            fixtures_com_bookmakers += 1
    return {
        "fixtures": fixtures,
        "fixtures_com_bookmakers": fixtures_com_bookmakers,
        "bookmakers_disponiveis": sorted(
            nomes, key=_identidade_bookmaker
        ),
        "bookmakers_independentes": sorted(
            independentes, key=_identidade_bookmaker
        ),
        "identidade_bookmaker_disponivel": bool(nomes),
        "referencia_independente_possivel": bool(independentes),
    }


def verificar_capacidade_referencia_api(caminho):
    """Valida o aprendizado persistente da capacidade multibookmaker."""
    caminho = Path(caminho)
    padrao = _estado_capacidade_referencia_padrao()
    if not caminho.exists():
        return {"saudavel": True, "estado": "novo", **padrao}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"saudavel": False, "estado": "corrompido", **padrao}
    if not isinstance(dados, dict) or not isinstance(
        dados.get("por_bet"), dict
    ):
        return {"saudavel": False, "estado": "corrompido", **padrao}
    contadores = (
        "amostras",
        "amostras_com_identidade",
        "amostras_sem_identidade",
        "sem_identidade_consecutivas",
        "fixtures_ultima_amostra",
        "fixtures_com_bookmakers",
        "consultas_referencia_suprimidas",
    )
    normalizado = {
        "versao": CAPACIDADE_REFERENCIA_VERSAO,
        "atualizado_em": dados.get("atualizado_em"),
        "por_bet": {},
    }
    for bet_id, item_padrao in padrao["por_bet"].items():
        recebido = dados["por_bet"].get(bet_id, {})
        if not isinstance(recebido, dict) or any(
            type(recebido.get(campo, 0)) is not int
            or recebido.get(campo, 0) < 0
            for campo in contadores
        ):
            return {"saudavel": False, "estado": "corrompido", **padrao}
        identidade = recebido.get("identidade_bookmaker_disponivel")
        nomes = recebido.get("bookmakers_disponiveis", [])
        independentes = recebido.get("bookmakers_independentes", [])
        if (
            identidade not in (None, True, False)
            or not isinstance(nomes, list)
            or not isinstance(independentes, list)
            or any(not str(nome or "").strip() for nome in nomes)
            or any(not str(nome or "").strip() for nome in independentes)
            or len({_identidade_bookmaker(nome) for nome in nomes})
            != len(nomes)
            or len({_identidade_bookmaker(nome) for nome in independentes})
            != len(independentes)
        ):
            return {"saudavel": False, "estado": "corrompido", **padrao}
        item = {
            chave: recebido.get(chave, valor)
            for chave, valor in item_padrao.items()
        }
        item["bookmakers_disponiveis"] = sorted(
            nomes, key=_identidade_bookmaker
        )
        item["bookmakers_independentes"] = sorted(
            independentes, key=_identidade_bookmaker
        )
        normalizado["por_bet"][bet_id] = item
    if any(
        item["identidade_bookmaker_disponivel"] is False
        for item in normalizado["por_bet"].values()
    ):
        estado = "capacidade_independente_indisponivel_observada"
    elif any(
        item["bookmakers_independentes"]
        for item in normalizado["por_bet"].values()
    ):
        estado = "capacidade_independente_disponivel"
    else:
        estado = "aguardando_amostra"
    return {**normalizado, "saudavel": True, "estado": estado}


def auditar_catalogo_odds_live(itens, observado_em=None):
    observado_em = observado_em or datetime.now().replace(
        microsecond=0
    ).isoformat()
    por_id = {}
    if isinstance(itens, list):
        for item in itens:
            if not isinstance(item, dict):
                continue
            try:
                bet_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            nome = str(item.get("name") or "").strip()
            if nome:
                por_id[bet_id] = nome
    divergencias = []
    mapeamentos = {}
    for bet_id, esperado in MERCADOS_ODDS_LIVE_ESPERADOS.items():
        encontrado = por_id.get(bet_id)
        coerente = (
            encontrado is not None
            and encontrado.casefold() == esperado.casefold()
        )
        mapeamentos[str(bet_id)] = {
            "esperado": esperado,
            "encontrado": encontrado,
            "coerente": coerente,
        }
        if encontrado is None:
            divergencias.append(f"bet_{bet_id}_ausente")
        elif not coerente:
            divergencias.append(f"bet_{bet_id}_nome_divergente")
    candidatos_2t = [
        {"id": bet_id, "nome": nome}
        for bet_id, nome in sorted(por_id.items())
        if "asian corners" in nome.casefold()
        and any(
            termo in nome.casefold()
            for termo in ("2nd half", "second half")
        )
    ]
    return {
        "versao": 1,
        "saudavel": not divergencias,
        "estado": "valido" if not divergencias else "incoerente",
        "observado_em": observado_em,
        "total_mercados": len(por_id),
        "mapeamentos": mapeamentos,
        "divergencias": divergencias,
        "asiatico_2t_disponivel": bool(candidatos_2t),
        "candidatos_asiatico_2t": candidatos_2t,
    }


def verificar_catalogo_odds_live(caminho, agora=None, max_idade_horas=48):
    caminho = Path(caminho)
    if not caminho.exists():
        return {
            "saudavel": False,
            "estado": "ausente",
            "motivo": "catalogo_odds_live_ausente",
            "divergencias": ["catalogo_ausente"],
        }
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        observado = datetime.fromisoformat(dados["observado_em"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "saudavel": False,
            "estado": "corrompido",
            "motivo": "catalogo_odds_live_corrompido",
            "divergencias": ["estado_invalido"],
        }
    agora = agora or datetime.now()
    idade_horas = max((agora - observado).total_seconds() / 3600, 0)
    estrutura_valida = (
        dados.get("versao") == 1
        and isinstance(dados.get("mapeamentos"), dict)
        and isinstance(dados.get("divergencias"), list)
        and isinstance(dados.get("candidatos_asiatico_2t"), list)
        and isinstance(dados.get("asiatico_2t_disponivel"), bool)
    )
    if not estrutura_valida:
        return {
            "saudavel": False,
            "estado": "corrompido",
            "motivo": "catalogo_odds_live_corrompido",
            "divergencias": ["estrutura_invalida"],
        }
    fresco = idade_horas <= float(max_idade_horas)
    coerente = not dados["divergencias"]
    return {
        **dados,
        "saudavel": bool(fresco and coerente),
        "estado": (
            "valido" if fresco and coerente
            else "desatualizado" if not fresco else "incoerente"
        ),
        "motivo": (
            None if fresco and coerente
            else "catalogo_odds_live_desatualizado" if not fresco
            else "catalogo_odds_live_incoerente"
        ),
        "idade_horas": round(idade_horas, 2),
    }


def auditar_cache_api_football(conexao, agora=None):
    agora_epoch = float(
        agora.timestamp() if isinstance(agora, datetime) else (
            agora if agora is not None else time.time()
        )
    )
    categorias = tuple(CACHE_TTL_POR_CATEGORIA)
    marcadores = ",".join("?" for _ in categorias)
    linha = conexao.execute(
        f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN categoria NOT IN ({marcadores})
                        THEN 1 ELSE 0 END) AS categorias_invalidas,
               SUM(CASE
                     WHEN NOT json_valid(dados_json) THEN 1
                     WHEN COALESCE(json_type(dados_json), '')
                          NOT IN ('array', 'object')
                     THEN 1 ELSE 0 END) AS payloads_invalidos,
               SUM(CASE WHEN armazenado_em > ? + 5
                        THEN 1 ELSE 0 END) AS relogios_futuros,
               COALESCE(SUM(length(dados_json)), 0) AS bytes_json
        FROM cache_api_football
        """,
        (*categorias, agora_epoch),
    ).fetchone()
    expirados = 0
    por_categoria = {}
    for categoria, ttl in CACHE_TTL_POR_CATEGORIA.items():
        dados = conexao.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN armazenado_em + ? <= ?
                            THEN 1 ELSE 0 END) AS expirados
            FROM cache_api_football WHERE categoria=?
            """,
            (float(ttl), agora_epoch, categoria),
        ).fetchone()
        total_categoria = int(dados[0] or 0)
        expirados_categoria = int(dados[1] or 0)
        por_categoria[categoria] = {
            "total": total_categoria,
            "expirados": expirados_categoria,
            "ttl_segundos": int(ttl),
        }
        expirados += expirados_categoria
    categorias_invalidas = int(linha[1] or 0)
    payloads_invalidos = int(linha[2] or 0)
    relogios_futuros = int(linha[3] or 0)
    return {
        "saudavel": not (
            categorias_invalidas or payloads_invalidos or relogios_futuros
        ),
        "total": int(linha[0] or 0),
        "expirados": expirados,
        "categorias_invalidas": categorias_invalidas,
        "payloads_invalidos": payloads_invalidos,
        "relogios_futuros": relogios_futuros,
        "tamanho_json_mb": round(float(linha[4] or 0) / 1024 / 1024, 3),
        "por_categoria": por_categoria,
    }


def limpar_cache_api_football_expirado(conexao, agora=None):
    """Remove somente payloads que já não podem ser reutilizados.

    O histórico de partidas, snapshots, odds e sinais vive em tabelas próprias
    e não é tocado aqui. Esta rotina limita apenas o cache operacional da API.
    """
    agora_epoch = float(
        agora.timestamp() if isinstance(agora, datetime) else (
            agora if agora is not None else time.time()
        )
    )
    condicoes = []
    parametros = []
    for categoria, ttl in CACHE_TTL_POR_CATEGORIA.items():
        condicoes.append("(categoria=? AND armazenado_em + ? <= ?)")
        parametros.extend((str(categoria), float(ttl), agora_epoch))
    if not condicoes:
        return 0
    cursor = conexao.execute(
        "DELETE FROM cache_api_football WHERE " + " OR ".join(condicoes),
        tuple(parametros),
    )
    return max(int(cursor.rowcount or 0), 0)


def _estado_odds_por_bet_padrao():
    return {
        "consultas": 0,
        "com_ofertas_globais": 0,
        "sem_ofertas_globais": 0,
        "falhas": 0,
        "solicitacoes_fixture": 0,
        "fixtures_correspondentes": 0,
        "ofertas_anexadas": 0,
        "ofertas_rejeitadas": 0,
        "rejeicoes_por_motivo": {},
        "ultimo_motivo_rejeicao": None,
        "ultima_consulta_em": None,
        "ultima_oferta_global_em": None,
        "ultima_oferta_anexada_em": None,
        "ultimo_total_fixtures": None,
        "sem_ofertas_consecutivas": 0,
        "consultas_suprimidas": 0,
        "suspensoes": 0,
        "suspenso_ate": None,
        "ultima_suspensao_em": None,
        "ultima_supressao_em": None,
    }


def _estado_odds_api_padrao():
    bet_ids = sorted(MERCADOS_ODDS_LIVE_ESPERADOS)
    return {
        "versao": 6,
        "bet_ids": bet_ids,
        "consultas": 0,
        "com_ofertas_globais": 0,
        "sem_ofertas_globais": 0,
        "falhas": 0,
        "ultima_consulta_em": None,
        "ultima_oferta_em": None,
        "ultimo_total_fixtures": None,
        "ultimo_bet_id": None,
        "por_bet": {
            str(bet_id): _estado_odds_por_bet_padrao()
            for bet_id in bet_ids
        },
    }


def verificar_estado_odds_api(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return {"saudavel": True, "estado": "novo", **_estado_odds_api_padrao()}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "saudavel": False,
            "estado": "corrompido",
            **_estado_odds_api_padrao(),
        }
    padrao = _estado_odds_api_padrao()
    if not isinstance(dados, dict) or any(
        type(dados.get(campo)) is not int or dados[campo] < 0
        for campo in (
            "consultas", "com_ofertas_globais",
            "sem_ofertas_globais", "falhas",
        )
    ):
        return {"saudavel": False, "estado": "corrompido", **padrao}
    por_bet_recebido = dados.get("por_bet")
    if por_bet_recebido is not None and not isinstance(
        por_bet_recebido, dict
    ):
        return {"saudavel": False, "estado": "corrompido", **padrao}
    conhecidos = {
        chave: dados.get(chave, valor)
        for chave, valor in padrao.items() if chave != "por_bet"
    }
    conhecidos["versao"] = padrao["versao"]
    conhecidos["bet_ids"] = padrao["bet_ids"]
    conhecidos["por_bet"] = {}
    campos_contadores = (
        "consultas", "com_ofertas_globais", "sem_ofertas_globais",
        "falhas", "solicitacoes_fixture", "fixtures_correspondentes",
        "ofertas_anexadas", "ofertas_rejeitadas",
        "sem_ofertas_consecutivas", "consultas_suprimidas", "suspensoes",
    )
    for bet_id, dados_padrao in padrao["por_bet"].items():
        recebido = (por_bet_recebido or {}).get(bet_id, {})
        if not isinstance(recebido, dict) or any(
            type(recebido.get(campo, 0)) is not int
            or recebido.get(campo, 0) < 0
            for campo in campos_contadores
        ):
            return {"saudavel": False, "estado": "corrompido", **padrao}
        rejeicoes = recebido.get("rejeicoes_por_motivo", {})
        if not isinstance(rejeicoes, dict) or any(
            not isinstance(motivo, str)
            or not motivo
            or type(quantidade) is not int
            or quantidade < 0
            for motivo, quantidade in rejeicoes.items()
        ):
            return {"saudavel": False, "estado": "corrompido", **padrao}
        ultimo_motivo = recebido.get("ultimo_motivo_rejeicao")
        if (
            ultimo_motivo is not None
            and (
                not isinstance(ultimo_motivo, str)
                or ultimo_motivo not in rejeicoes
            )
        ):
            return {"saudavel": False, "estado": "corrompido", **padrao}
        if sum(rejeicoes.values()) > recebido.get("ofertas_rejeitadas", 0):
            return {"saudavel": False, "estado": "corrompido", **padrao}
        conhecidos["por_bet"][bet_id] = {
            chave: recebido.get(chave, valor)
            for chave, valor in dados_padrao.items()
        }
        if (
            "sem_ofertas_consecutivas" not in recebido
            and recebido.get("com_ofertas_globais", 0) == 0
        ):
            conhecidos["por_bet"][bet_id][
                "sem_ofertas_consecutivas"
            ] = recebido.get("sem_ofertas_globais", 0)
        conhecidos["por_bet"][bet_id]["rejeicoes_sem_diagnostico"] = (
            recebido.get("ofertas_rejeitadas", 0) - sum(rejeicoes.values())
        )
    return {**conhecidos, "saudavel": True, "estado": "valido"}


def _numero_positivo(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def _linha_odd_ao_vivo(valor):
    linha = _numero_positivo(valor.get("handicap"))
    if linha is not None:
        return linha
    encontrado = re.search(
        r"(?:over|under)\s*([+-]?\d+(?:[.,]\d+)?)",
        str(valor.get("value") or ""),
        re.IGNORECASE,
    )
    return _numero_positivo(encontrado.group(1)) if encontrado else None


def _ofertas_over_under_api(valores):
    por_linha = {}
    for valor in valores or []:
        if not isinstance(valor, dict) or valor.get("suspended") is True:
            continue
        selecao = str(valor.get("value") or "").strip().lower()
        if "exactly" in selecao or "exatamente" in selecao:
            continue
        lado = (
            "over" if selecao == "over" or selecao.startswith("over ")
            else "under" if selecao == "under" or selecao.startswith("under ")
            else None
        )
        linha = _linha_odd_ao_vivo(valor)
        odd = _numero_positivo(valor.get("odd"))
        if lado is None or linha is None or odd is None:
            continue
        por_linha.setdefault(linha, {"linha": linha})[lado] = odd
    return [
        por_linha[linha]
        for linha in sorted(por_linha)
        if por_linha[linha].get("over") is not None
        and por_linha[linha].get("under") is not None
    ]


def _diagnosticar_escanteios_asiaticos_api(
    item, bet_id, nome_esperado, periodo=None, idade_segundos=0.0
):
    """Converte um mercado conhecido e explica por que falhou fechado."""
    if not isinstance(item, dict):
        return None, "item_invalido"
    status = item.get("status")
    if not isinstance(status, dict):
        status = {}
    for campo, motivo in (
        ("blocked", "fixture_bloqueada"),
        ("stopped", "fixture_interrompida"),
        ("finished", "fixture_finalizada"),
    ):
        if item.get(campo) is True or status.get(campo) is True:
            return None, motivo

    grupos = [(None, item.get("odds") or [])]
    for bookmaker in item.get("bookmakers") or []:
        if isinstance(bookmaker, dict):
            grupos.append((bookmaker.get("name"), bookmaker.get("bets") or []))

    mercado_encontrado = False
    for bookmaker, apostas in grupos:
        for aposta in apostas:
            if not isinstance(aposta, dict):
                continue
            nome = str(aposta.get("name") or "")
            try:
                id_aposta = int(aposta.get("id"))
            except (TypeError, ValueError):
                id_aposta = None
            if (
                id_aposta != bet_id
                and nome.strip().lower() != nome_esperado.lower()
            ):
                continue
            mercado_encontrado = True
            ofertas = _ofertas_over_under_api(aposta.get("values"))
            if not ofertas:
                continue
            fonte = "api_football"
            for oferta in ofertas:
                oferta["fonte"] = fonte
                oferta["idade_segundos"] = round(float(idade_segundos), 1)
                oferta["origem_mercado"] = {
                    "schema": "origem-mercado-odd-v1",
                    "fonte": fonte,
                    "identificador": str(
                        id_aposta if id_aposta is not None else bet_id
                    ),
                    "nome": nome or nome_esperado,
                    "linha": oferta.get("linha"),
                    "lados": ["over", "under"],
                    "bookmaker": bookmaker,
                }
                if bookmaker:
                    oferta["bookmaker"] = bookmaker
            dados = " ".join(
                f"{oferta['linha']:g} {oferta['over']:g} {oferta['under']:g}"
                for oferta in ofertas
            )
            return {
                "mercado": nome or nome_esperado,
                "dados": f"{nome_esperado} Over Under {dados}",
                "categoria": "escanteios",
                "escopo": "total",
                "tipo_mercado": "asiatico",
                "formato": "duas_opcoes",
                "ofertas": ofertas if periodo is None else [],
                "ofertas_exatamente": [],
                "ofertas_periodos": ({
                    periodo: {
                        "formato": "duas_opcoes",
                        "ofertas": ofertas,
                    }
                } if periodo else {}),
                "ofertas_ht": [],
                "selecoes": {},
                "fonte": fonte,
                "bookmaker": bookmaker,
                "cache": bool(idade_segundos > 0),
            }, None
    if mercado_encontrado:
        return None, "over_under_incompleto_ou_suspenso"
    return None, "mercado_ausente"


def _estruturar_escanteios_asiaticos_api(
    item, bet_id, nome_esperado, periodo=None, idade_segundos=0.0
):
    mercado, _ = _diagnosticar_escanteios_asiaticos_api(
        item, bet_id, nome_esperado, periodo, idade_segundos
    )
    return mercado


def estruturar_escanteios_asiaticos_ft_api(item, idade_segundos=0.0):
    return _estruturar_escanteios_asiaticos_api(
        item,
        BET_ESCANTEIOS_ASIATICOS_FT,
        "Asian Corners",
        idade_segundos=idade_segundos,
    )


def estruturar_escanteios_asiaticos_1t_api(item, idade_segundos=0.0):
    return _estruturar_escanteios_asiaticos_api(
        item,
        BET_ESCANTEIOS_ASIATICOS_1T,
        "Asian Corners (1st Half)",
        periodo="1T",
        idade_segundos=idade_segundos,
    )


def diagnosticar_escanteios_asiaticos_ft_api(item, idade_segundos=0.0):
    return _diagnosticar_escanteios_asiaticos_api(
        item,
        BET_ESCANTEIOS_ASIATICOS_FT,
        "Asian Corners",
        idade_segundos=idade_segundos,
    )


def diagnosticar_escanteios_asiaticos_1t_api(item, idade_segundos=0.0):
    return _diagnosticar_escanteios_asiaticos_api(
        item,
        BET_ESCANTEIOS_ASIATICOS_1T,
        "Asian Corners (1st Half)",
        periodo="1T",
        idade_segundos=idade_segundos,
    )


def diagnosticar_gols_total_api(item, idade_segundos=0.0):
    mercado, motivo = _diagnosticar_escanteios_asiaticos_api(
        item,
        BET_GOLS_TOTAL_FT,
        "Match Goals",
        idade_segundos=idade_segundos,
    )
    if mercado is None:
        return None, motivo
    mercado.update({
        "mercado": "Total Gols",
        "dados": mercado["dados"].replace("Match Goals", "Total Gols"),
        "categoria": "gols",
        "tipo_mercado": "total",
        "fonte": "api_football",
    })
    return mercado, None


def estruturar_gols_total_api(item, idade_segundos=0.0):
    mercado, _ = diagnosticar_gols_total_api(item, idade_segundos)
    return mercado


def diagnosticar_gols_total_ht_api(item, idade_segundos=0.0):
    mercado, motivo = _diagnosticar_escanteios_asiaticos_api(
        item,
        BET_GOLS_TOTAL_HT,
        "Over/Under (1st Half)",
        idade_segundos=idade_segundos,
    )
    if mercado is None:
        return None, motivo
    ofertas_ht = list(mercado.get("ofertas") or [])
    mercado.update({
        "mercado": "Total Gols 1T",
        "dados": mercado["dados"].replace(
            "Over/Under (1st Half)", "Total Gols 1T"
        ),
        "categoria": "gols",
        "tipo_mercado": "total",
        "periodo": "1T",
        "ofertas": [],
        "ofertas_ht": ofertas_ht,
        "fonte": "api_football",
    })
    return mercado, None


def estruturar_gols_total_ht_api(item, idade_segundos=0.0):
    mercado, _ = diagnosticar_gols_total_ht_api(item, idade_segundos)
    return mercado


def _selecoes_proximo_gol_api(valores):
    selecoes = {}
    aliases = {
        "home": "casa",
        "home team": "casa",
        "team 1": "casa",
        "1": "casa",
        "away": "visitante",
        "away team": "visitante",
        "team 2": "visitante",
        "2": "visitante",
        "no goal": "sem_gol",
        "no": "sem_gol",
        "neither": "sem_gol",
    }
    for valor in valores or []:
        if not isinstance(valor, dict) or valor.get("suspended") is True:
            continue
        chave = aliases.get(str(valor.get("value") or "").strip().casefold())
        odd = _numero_positivo(valor.get("odd"))
        if chave and odd is not None:
            selecoes[chave] = odd
    return selecoes


def diagnosticar_proximo_gol_api(
    item, bet_id, nome_esperado, idade_segundos=0.0
):
    if not isinstance(item, dict):
        return None, "item_invalido"
    status = item.get("status")
    if not isinstance(status, dict):
        status = {}
    for campo, motivo in (
        ("blocked", "fixture_bloqueada"),
        ("stopped", "fixture_interrompida"),
        ("finished", "fixture_finalizada"),
    ):
        if item.get(campo) is True or status.get(campo) is True:
            return None, motivo
    grupos = [(None, item.get("odds") or [])]
    for bookmaker in item.get("bookmakers") or []:
        if isinstance(bookmaker, dict):
            grupos.append((bookmaker.get("name"), bookmaker.get("bets") or []))
    encontrado = False
    for bookmaker, apostas in grupos:
        for aposta in apostas:
            if not isinstance(aposta, dict):
                continue
            nome = str(aposta.get("name") or "")
            try:
                id_aposta = int(aposta.get("id"))
            except (TypeError, ValueError):
                id_aposta = None
            if (
                id_aposta != int(bet_id)
                and nome.strip().casefold() != nome_esperado.casefold()
            ):
                continue
            encontrado = True
            selecoes = _selecoes_proximo_gol_api(aposta.get("values"))
            if not {"casa", "visitante", "sem_gol"} <= set(selecoes):
                continue
            return {
                "mercado": "Marcar O Próximo Gol",
                "dados": (
                    "Marcar O Próximo Gol "
                    f"1: {selecoes['casa']:g} "
                    f"2: {selecoes['visitante']:g} "
                    f"No : {selecoes['sem_gol']:g}"
                ),
                "categoria": "gols",
                "escopo": "proximo",
                "formato": "tres_opcoes",
                "ofertas": [],
                "ofertas_exatamente": [],
                "ofertas_periodos": {},
                "ofertas_ht": [],
                "selecoes": selecoes,
                "origem_mercado": {
                    "schema": "origem-mercado-odd-v1",
                    "fonte": "api_football",
                    "identificador": str(
                        id_aposta if id_aposta is not None else bet_id
                    ),
                    "nome": nome or nome_esperado,
                    "linha": int(bet_id),
                    "lados": ["casa", "visitante", "sem_gol"],
                    "bookmaker": bookmaker,
                },
                "fonte": "api_football",
                "bookmaker": bookmaker,
                "cache": bool(idade_segundos > 0),
                "idade_segundos": round(float(idade_segundos), 1),
            }, None
    return (
        None,
        "selecoes_incompletas_ou_suspensas" if encontrado
        else "mercado_ausente",
    )


def _uso_valido(dados):
    if not isinstance(dados, dict):
        return False
    meses = dados.get("meses")
    dias = dados.get("dias")
    if not isinstance(meses, dict) or not isinstance(dias, dict):
        return False
    versao = dados.get("versao")
    if versao is not None and (type(versao) is not int or versao not in (1, 2)):
        return False
    for quantidade in meses.values():
        if type(quantidade) is not int or quantidade < 0:
            return False
    for categorias in dias.values():
        if not isinstance(categorias, dict):
            return False
        for quantidade in categorias.values():
            if type(quantidade) is not int or quantidade < 0:
                return False
    provedor = dados.get("provedor")
    if provedor is not None:
        if not isinstance(provedor, dict):
            return False
        campos_diarios = (
            provedor.get("limite_diario"),
            provedor.get("restante_diario"),
        )
        if (
            not isinstance(provedor.get("dia"), str)
            or len(provedor["dia"]) != 10
            or any(type(valor) is not int for valor in campos_diarios)
            or campos_diarios[0] <= 0
            or not 0 <= campos_diarios[1] <= campos_diarios[0]
            or isinstance(provedor.get("observado_em"), bool)
            or not isinstance(provedor.get("observado_em"), (int, float))
            or provedor["observado_em"] < 0
        ):
            return False
        limite_minuto = provedor.get("limite_minuto")
        restante_minuto = provedor.get("restante_minuto")
        if (limite_minuto is None) != (restante_minuto is None):
            return False
        if limite_minuto is not None and (
            type(limite_minuto) is not int
            or type(restante_minuto) is not int
            or limite_minuto <= 0
            or not 0 <= restante_minuto <= limite_minuto
        ):
            return False
    return True


def _migrar_uso_v2(dados):
    if int(dados.get("versao") or 1) >= 2:
        return dados
    # A primeira versão da reconciliação somava a diferença do provedor
    # também ao mês, embora as tentativas do bot já estivessem nesse total.
    # O mensal representa tentativas locais; a cota oficial usa os dias.
    ajustes_por_mes = {}
    for dia, categorias in dados.get("dias", {}).items():
        externo = int(categorias.get("externo", 0) or 0)
        if externo:
            ajustes_por_mes[dia[:7]] = ajustes_por_mes.get(dia[:7], 0) + externo
    for mes, ajuste in ajustes_por_mes.items():
        dados["meses"][mes] = max(
            int(dados["meses"].get(mes, 0)) - ajuste, 0
        )
    dados["versao"] = 2
    return dados


def _ler_uso_valido(caminho):
    caminho = Path(caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dados if _uso_valido(dados) else None


def _agora_cota(agora=None):
    if agora is None:
        return datetime.now(timezone.utc)
    if agora.tzinfo is None:
        agora = agora.astimezone()
    return agora.astimezone(timezone.utc)


def _resumo_consumo_dia(dados, agora=None):
    agora = _agora_cota(agora)
    dia = agora.strftime("%Y-%m-%d")
    categorias = dados.get("dias", {}).get(dia, {})
    return {
        "dia": dia,
        "consumo_dia": sum(categorias.values()),
        "categorias_dia": dict(categorias),
        "provedor": dict(dados.get("provedor") or {}),
    }


def verificar_contador_uso(caminho, agora=None):
    caminho = Path(caminho)
    backup = caminho.with_suffix(caminho.suffix + ".bak")
    principal_existe = caminho.exists()
    backup_existe = backup.exists()
    principal = _ler_uso_valido(caminho) if principal_existe else None
    if principal is not None:
        return {
            "saudavel": True,
            "requer_atencao": False,
            "estado": "valido",
            "origem": "principal",
            **_resumo_consumo_dia(principal, agora),
        }
    recuperavel = _ler_uso_valido(backup) if backup_existe else None
    if recuperavel is not None:
        return {
            "saudavel": True,
            "requer_atencao": True,
            "estado": "recuperavel",
            "origem": "backup",
            **_resumo_consumo_dia(recuperavel, agora),
        }
    if not principal_existe and not backup_existe:
        return {
            "saudavel": True,
            "requer_atencao": False,
            "estado": "novo",
            "origem": None,
            **_resumo_consumo_dia({"dias": {}}, agora),
        }
    return {
        "saudavel": False,
        "requer_atencao": True,
        "estado": "corrompido",
        "origem": None,
        "dia": _agora_cota(agora).strftime("%Y-%m-%d"),
        "consumo_dia": None,
        "categorias_dia": {},
    }


class APIFootball:
    def __init__(self, pasta_projeto, perfil="ao_vivo"):
        self.pasta_projeto = Path(pasta_projeto)
        self.perfil = (
            "pre_live" if str(perfil).strip().casefold() == "pre_live"
            else "ao_vivo"
        )
        self.arquivo_trava_requisicao = (
            self.pasta_projeto / "api_football_requisicao.lock"
        )
        self.arquivo_prioridade_ao_vivo = (
            self.pasta_projeto / "api_football_prioridade_ao_vivo.lock"
        )
        self.chave = os.getenv("API_FOOTBALL_KEY")
        limites = obter_limites_api()
        self.limite_diario = limites.limite_diario
        self.reserva_diaria = limites.reserva_diaria
        self.limite_diario_seguro = max(
            self.limite_diario - self.reserva_diaria, 0
        )
        self.limite_diario_detalhes = limites.limite_diario_detalhes
        self.arquivo_uso = Path(pasta_projeto) / "api_football_uso.json"
        self.arquivo_uso_backup = self.arquivo_uso.with_suffix(
            self.arquivo_uso.suffix + ".bak"
        )
        self.arquivo_estado_odds = (
            Path(pasta_projeto) / "api_football_odds_estado.json"
        )
        self.arquivo_catalogo_odds = (
            Path(pasta_projeto) / "api_football_catalogo_odds_estado.json"
        )
        self.arquivo_capacidade_referencia = (
            Path(pasta_projeto)
            / "api_football_referencia_capacidade_estado.json"
        )
        self.caminho_banco = Path(pasta_projeto) / "monitor_packball.db"
        self.cache_persistente_hits = 0
        self.cache_persistente_gravacoes = 0
        self.cache_persistente_descartes = 0
        self.cache_persistente_falhas = 0
        self.cache_persistente_limpezas = 0
        self.proxima_limpeza_cache_persistente_em = 0.0
        self.falhas_rede_consecutivas = 0
        self.falhas_rede_ciclo = 0
        self.ultima_resposta_api_em = None
        self.ultima_falha_api_em = None
        self.ultimo_erro_api = None
        self.reconciliacoes_cota = 0
        self.cabecalhos_cota_invalidos = 0
        self.ressincronizacoes_cota_bloqueada = 0
        self.falhas_ressincronizacao_cota_bloqueada = 0
        self.ultima_tentativa_ressincronizacao_cota_em = 0.0
        self.controle_uso_saudavel = True
        self.controle_uso_origem = "novo"
        self.controle_uso_recuperado = False
        self.cache_geral = None
        self.cache_geral_em = 0
        self.cache_detalhes = {}
        self.cache_eventos = {}
        self.cache_jogadores = {}
        self.cache_resultados = {}
        self.cache_odds_ao_vivo = {}
        self.limite_vazias_consecutivas_odds_1t = max(
            int(
                os.getenv(
                    "API_ODDS_1T_LIMITE_VAZIAS_CONSECUTIVAS",
                    str(LIMITE_VAZIAS_CONSECUTIVAS_ODDS_1T),
                )
            ),
            1,
        )
        self.suspensao_odds_1t_segundos = max(
            int(
                os.getenv(
                    "API_ODDS_1T_SUSPENSAO_SEGUNDOS",
                    str(SUSPENSAO_ODDS_1T_SEGUNDOS),
                )
            ),
            CACHE_ODDS_AO_VIVO_SEGUNDOS,
        )
        estado_odds = verificar_estado_odds_api(self.arquivo_estado_odds)
        self.estado_odds = {
            chave: estado_odds[chave]
            for chave in _estado_odds_api_padrao()
        }
        estado_capacidade = verificar_capacidade_referencia_api(
            self.arquivo_capacidade_referencia
        )
        self.estado_capacidade_referencia = {
            chave: estado_capacidade[chave]
            for chave in _estado_capacidade_referencia_padrao()
        }
        self.uso = self._carregar_uso()
        if (
            self.controle_uso_origem == "principal"
            and _ler_uso_valido(self.arquivo_uso_backup) is None
        ):
            gravar_json_atomico(self.arquivo_uso_backup, self.uso)

    def _adquirir_trava_api(self, timeout):
        """Serializa a cota entre processos e prioriza o monitor ao vivo."""
        limite = time.monotonic() + max(float(timeout), 1.0) + 3.0
        prioridade = None
        if self.perfil == "ao_vivo":
            prioridade = TravaInstancia(self.arquivo_prioridade_ao_vivo)
            while not prioridade.adquirir():
                if time.monotonic() >= limite:
                    return None, None
                time.sleep(0.025)
        requisicao = TravaInstancia(self.arquivo_trava_requisicao)
        try:
            while True:
                if (
                    self.perfil == "pre_live"
                    and trava_em_uso(self.arquivo_prioridade_ao_vivo)
                ):
                    if time.monotonic() >= limite:
                        return prioridade, None
                    time.sleep(0.05)
                    continue
                if requisicao.adquirir():
                    return prioridade, requisicao
                if time.monotonic() >= limite:
                    return prioridade, None
                time.sleep(0.025)
        except Exception:
            requisicao.liberar()
            if prioridade is not None:
                prioridade.liberar()
            raise

    @staticmethod
    def _liberar_travas_api(prioridade, requisicao):
        if requisicao is not None:
            requisicao.liberar()
        if prioridade is not None:
            prioridade.liberar()

    def _descartar_cache_persistente(self, chave):
        if not self.caminho_banco.exists():
            return
        conexao = None
        try:
            conexao = sqlite3.connect(self.caminho_banco, timeout=2)
            with conexao:
                removidos = conexao.execute(
                    "DELETE FROM cache_api_football WHERE chave=?",
                    (str(chave),),
                ).rowcount
            self.cache_persistente_descartes += int(removidos or 0)
        except (OSError, sqlite3.Error):
            self.cache_persistente_falhas += 1
            return
        finally:
            if conexao is not None:
                try:
                    conexao.close()
                except sqlite3.Error:
                    self.cache_persistente_falhas += 1

    def _ler_cache_persistente(
        self, chave, categoria, ttl_segundos, agora=None
    ):
        if not self.caminho_banco.exists():
            return None
        agora = float(agora if agora is not None else time.time())
        conexao = None
        try:
            uri = self.caminho_banco.resolve().as_uri() + "?mode=ro"
            conexao = sqlite3.connect(uri, uri=True, timeout=2)
            linha = conexao.execute(
                """
                SELECT categoria, armazenado_em, dados_json
                FROM cache_api_football WHERE chave=?
                """,
                (str(chave),),
            ).fetchone()
        except (OSError, sqlite3.Error):
            self.cache_persistente_falhas += 1
            return None
        finally:
            if conexao is not None:
                try:
                    conexao.close()
                except sqlite3.Error:
                    self.cache_persistente_falhas += 1
        if linha is None:
            return None
        if linha[0] != str(categoria):
            self._descartar_cache_persistente(chave)
            return None
        try:
            armazenado_em = float(linha[1])
            dados = json.loads(linha[2])
        except (TypeError, ValueError, json.JSONDecodeError):
            self._descartar_cache_persistente(chave)
            return None
        idade = agora - armazenado_em
        if idade < 0 or idade >= float(ttl_segundos):
            self._descartar_cache_persistente(chave)
            return None
        if not isinstance(dados, (list, dict)):
            self._descartar_cache_persistente(chave)
            return None
        self.cache_persistente_hits += 1
        return {"em": armazenado_em, "dados": dados}

    def _salvar_cache_persistente(
        self, chave, categoria, dados, armazenado_em=None
    ):
        if not self.caminho_banco.exists() or not isinstance(
            dados, (list, dict)
        ):
            return False
        armazenado_em = float(
            armazenado_em if armazenado_em is not None else time.time()
        )
        conexao = None
        try:
            dados_json = json.dumps(
                dados,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            conexao = sqlite3.connect(self.caminho_banco, timeout=2)
            executar_limpeza = bool(
                armazenado_em
                >= self.proxima_limpeza_cache_persistente_em
            )
            removidos_expirados = 0
            with conexao:
                conexao.execute(
                    """
                    INSERT INTO cache_api_football (
                        chave, categoria, armazenado_em, dados_json
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(chave) DO UPDATE SET
                        categoria=excluded.categoria,
                        armazenado_em=excluded.armazenado_em,
                        dados_json=excluded.dados_json
                    """,
                    (
                        str(chave), str(categoria), armazenado_em,
                        dados_json,
                    ),
                )
                if executar_limpeza:
                    removidos_expirados = (
                        limpar_cache_api_football_expirado(
                            conexao, armazenado_em
                        )
                    )
        except (OSError, sqlite3.Error, TypeError, ValueError):
            self.cache_persistente_falhas += 1
            return False
        finally:
            if conexao is not None:
                try:
                    conexao.close()
                except sqlite3.Error:
                    self.cache_persistente_falhas += 1
        if executar_limpeza:
            self.cache_persistente_limpezas += 1
            self.cache_persistente_descartes += removidos_expirados
            self.proxima_limpeza_cache_persistente_em = (
                armazenado_em
                + CACHE_LIMPEZA_EXPIRADOS_INTERVALO_SEGUNDOS
            )
        self.cache_persistente_gravacoes += 1
        return True

    @property
    def disponivel(self):
        return bool(self.chave)

    def iniciar_ciclo_saude(self):
        """Abre uma nova janela fail-closed para a coleta ao vivo."""
        self.falhas_rede_ciclo = 0

    def _registrar_sucesso_api(self):
        self.falhas_rede_consecutivas = 0
        self.ultima_resposta_api_em = time.time()
        self.ultimo_erro_api = None

    def _registrar_falha_api(self, erro):
        self.falhas_rede_consecutivas += 1
        self.falhas_rede_ciclo += 1
        self.ultima_falha_api_em = time.time()
        self.ultimo_erro_api = type(erro).__name__

    def saude_operacional(self):
        agora = _agora_cota()
        dia = agora.strftime("%Y-%m-%d")
        consumo_dia = self.uso["dias"].get(
            dia, {"geral": 0, "detalhe": 0}
        )
        restante_seguro = max(
            self._limite_diario_efetivo(dia) - sum(consumo_dia.values()), 0
        )
        if not self.disponivel:
            motivo = "api_sem_chave"
        elif not self.controle_uso_saudavel:
            motivo = "contador_api_inseguro"
        elif restante_seguro <= 0:
            motivo = "cota_api_segura_esgotada"
        elif self.falhas_rede_ciclo > 0:
            motivo = "falha_api_no_ciclo"
        elif self.falhas_rede_consecutivas > 0:
            motivo = "api_sem_recuperacao_confirmada"
        elif self.ultima_resposta_api_em is None:
            motivo = "api_ainda_nao_confirmada"
        else:
            motivo = None
        return {
            "saudavel": motivo is None,
            "motivo": motivo,
            "falhas_rede_ciclo": self.falhas_rede_ciclo,
            "falhas_rede_consecutivas": self.falhas_rede_consecutivas,
            "ultima_resposta_api_em": self.ultima_resposta_api_em,
            "ultima_falha_api_em": self.ultima_falha_api_em,
            "ultimo_erro_api": self.ultimo_erro_api,
        }

    def _carregar_uso(self):
        if not self.arquivo_uso.exists() and not self.arquivo_uso_backup.exists():
            return {"versao": 2, "meses": {}, "dias": {}}
        principal = _ler_uso_valido(self.arquivo_uso)
        if principal is not None:
            self.controle_uso_origem = "principal"
            return _migrar_uso_v2(principal)
        backup = _ler_uso_valido(self.arquivo_uso_backup)
        if backup is not None:
            self.controle_uso_origem = "backup"
            self.controle_uso_recuperado = True
            return _migrar_uso_v2(backup)

        # Sem um contador confiável, assumir o teto seguro já consumido evita
        # extrapolar a franquia. A API permanece bloqueada até intervenção.
        self.controle_uso_saudavel = False
        self.controle_uso_origem = "bloqueado"
        agora = _agora_cota()
        return {
            "versao": 2,
            "meses": {agora.strftime("%Y-%m"): self.limite_diario_seguro},
            "dias": {
                agora.strftime("%Y-%m-%d"): {
                    "geral": self.limite_diario_seguro,
                    "detalhe": 0,
                }
            },
        }

    def _salvar_uso(self):
        anterior = _ler_uso_valido(self.arquivo_uso)
        if anterior is not None:
            gravar_json_atomico(self.arquivo_uso_backup, anterior)
        gravar_json_atomico(self.arquivo_uso, self.uso)
        if not self.arquivo_uso_backup.exists():
            gravar_json_atomico(self.arquivo_uso_backup, self.uso)
        self.controle_uso_origem = "principal"

    def recarregar_uso_compartilhado(self):
        """Atualiza a fotografia local sem apagar um estado ainda válido."""
        atual = _ler_uso_valido(self.arquivo_uso)
        if not isinstance(atual, dict):
            return False
        self.uso = _migrar_uso_v2(atual)
        return True

    def _pode_chamar(self, categoria):
        if not self.controle_uso_saudavel:
            return False
        agora = _agora_cota()
        dia = agora.strftime("%Y-%m-%d")
        diario = self.uso["dias"].get(dia, {})
        total_diario = sum(diario.values())

        if total_diario >= self._limite_diario_efetivo(dia):
            return False
        provedor = self.uso.get("provedor") or {}
        if (
            provedor.get("dia") == dia
            and provedor.get("restante_minuto") == 0
            and time.time() - float(provedor.get("observado_em", 0)) < 60
        ):
            return False
        if (
            categoria == "detalhe"
            and diario.get("detalhe", 0) >= self.limite_diario_detalhes
        ):
            return False
        return True

    def _registrar_chamada(self, categoria):
        agora = _agora_cota()
        mes = agora.strftime("%Y-%m")
        dia = agora.strftime("%Y-%m-%d")
        self.uso["meses"][mes] = self.uso["meses"].get(mes, 0) + 1
        diario = self.uso["dias"].setdefault(
            dia, {"geral": 0, "detalhe": 0}
        )
        diario[categoria] = diario.get(categoria, 0) + 1
        self._salvar_uso()

    def _limite_diario_efetivo(self, dia=None):
        dia = dia or _agora_cota().strftime("%Y-%m-%d")
        provedor = self.uso.get("provedor") or {}
        if provedor.get("dia") != dia:
            return self.limite_diario_seguro
        limite_provedor_seguro = max(
            int(provedor["limite_diario"]) - self.reserva_diaria, 0
        )
        return min(self.limite_diario_seguro, limite_provedor_seguro)

    @staticmethod
    def _inteiro_cabecalho(cabecalhos, nome):
        try:
            valor = cabecalhos.get(nome)
        except AttributeError:
            return None
        if valor is None or isinstance(valor, bool):
            return None
        try:
            inteiro = int(str(valor).strip())
        except (TypeError, ValueError):
            return None
        return inteiro if inteiro >= 0 else None

    def _reconciliar_cota_provedor(self, cabecalhos):
        limite = self._inteiro_cabecalho(
            cabecalhos, "x-ratelimit-requests-limit"
        )
        restante = self._inteiro_cabecalho(
            cabecalhos, "x-ratelimit-requests-remaining"
        )
        if limite is None or restante is None or limite <= 0 or restante > limite:
            self.cabecalhos_cota_invalidos += 1
            return False
        limite_minuto = self._inteiro_cabecalho(
            cabecalhos, "x-ratelimit-limit"
        )
        restante_minuto = self._inteiro_cabecalho(
            cabecalhos, "x-ratelimit-remaining"
        )
        if (
            (limite_minuto is None) != (restante_minuto is None)
            or (
                limite_minuto is not None
                and (
                    limite_minuto <= 0
                    or restante_minuto > limite_minuto
                )
            )
        ):
            self.cabecalhos_cota_invalidos += 1
            return False
        agora = _agora_cota()
        dia = agora.strftime("%Y-%m-%d")
        diario = self.uso["dias"].setdefault(
            dia, {"geral": 0, "detalhe": 0}
        )
        consumo_provedor = limite - restante
        consumo_local = sum(
            int(valor or 0)
            for categoria, valor in diario.items()
            if categoria != "externo"
        )
        # O cabeçalho do provedor é uma fotografia, não um incremento.
        # Recalcular o ajuste evita conservar consumo do dia anterior quando
        # a virada UTC é observada com atraso. As tentativas locais nunca são
        # reduzidas: o total resultante é max(local, provedor).
        externo_reconciliado = max(
            consumo_provedor - consumo_local, 0
        )
        if externo_reconciliado:
            diario["externo"] = externo_reconciliado
        else:
            diario.pop("externo", None)
        self.uso["provedor"] = {
            "dia": dia,
            "limite_diario": limite,
            "restante_diario": restante,
            "limite_minuto": limite_minuto,
            "restante_minuto": restante_minuto,
            "observado_em": time.time(),
        }
        self.reconciliacoes_cota += 1
        self._salvar_uso()
        return True

    def sincronizar_cota_status(self):
        """Consulta gratuita de status para alinhar a cota na inicialização."""
        if not self.disponivel:
            return {"sincronizado": False, "motivo": "api_indisponivel"}
        requisicao = Request(
            f"{BASE_URL}/status",
            headers={"x-apisports-key": self.chave},
        )
        try:
            with urlopen(requisicao, timeout=10) as resposta:
                corpo = json.loads(resposta.read().decode("utf-8"))
                cabecalhos = getattr(resposta, "headers", None)
        except (
            HTTPError, URLError, TimeoutError,
            json.JSONDecodeError, UnicodeDecodeError,
        ) as erro:
            return {
                "sincronizado": False,
                "motivo": type(erro).__name__,
            }
        limite = self._inteiro_cabecalho(
            cabecalhos, "x-ratelimit-requests-limit"
        )
        restante = self._inteiro_cabecalho(
            cabecalhos, "x-ratelimit-requests-remaining"
        )
        resposta_status = (
            corpo.get("response") if isinstance(corpo, dict) else None
        )
        requisicoes = (
            resposta_status.get("requests")
            if isinstance(resposta_status, dict) else None
        )
        if (
            limite is None
            or restante is None
            or limite <= 0
            or restante > limite
        ) and isinstance(requisicoes, dict):
            try:
                limite_status = int(requisicoes.get("limit_day"))
                atual_status = int(requisicoes.get("current"))
            except (TypeError, ValueError):
                limite_status = 0
                atual_status = -1
            if limite_status > 0 and 0 <= atual_status <= limite_status:
                limite = limite_status
                restante = limite_status - atual_status
        normalizados = {
            "x-ratelimit-requests-limit": limite,
            "x-ratelimit-requests-remaining": restante,
        }
        limite_minuto = self._inteiro_cabecalho(
            cabecalhos, "x-ratelimit-limit"
        )
        restante_minuto = self._inteiro_cabecalho(
            cabecalhos, "x-ratelimit-remaining"
        )
        if limite_minuto is not None and restante_minuto is not None:
            normalizados["x-ratelimit-limit"] = limite_minuto
            normalizados["x-ratelimit-remaining"] = restante_minuto
        sincronizado = self._reconciliar_cota_provedor(normalizados)
        if sincronizado:
            # A resposta de /status veio do proprio provedor e comprova
            # conectividade, autenticacao e disponibilidade da API. Marcar o
            # sucesso evita que o primeiro ciclo seja fechado apenas porque a
            # lista de fixtures foi atendida por um cache ainda valido.
            self._registrar_sucesso_api()
        return {
            "sincronizado": sincronizado,
            "motivo": None if sincronizado else "resposta_invalida",
            "consumo_dia": limite - restante if sincronizado else None,
            "limite_diario": limite if sincronizado else None,
        }

    def _ressincronizar_cota_bloqueada_se_devido(
        self, categoria, agora_timestamp=None,
    ):
        """Rompe bloqueio causado por fotografia antiga do provedor.

        A chamada gratuita de ``/status`` só é feita quando o teto diário
        está bloqueado por consumo externo reconciliado. Consumo local real
        nunca é reduzido por esta rotina.
        """
        agora_timestamp = float(agora_timestamp or time.time())
        agora_cota = _agora_cota()
        dia = agora_cota.strftime("%Y-%m-%d")
        diario = self.uso.get("dias", {}).get(dia, {})
        total_diario = sum(int(valor or 0) for valor in diario.values())
        externo = int(diario.get("externo", 0) or 0)
        if (
            total_diario < self._limite_diario_efetivo(dia)
            or externo <= 0
        ):
            return {"tentada": False, "motivo": "nao_e_bloqueio_externo"}

        provedor = self.uso.get("provedor") or {}
        observado_em = (
            float(provedor.get("observado_em") or 0.0)
            if provedor.get("dia") == dia else 0.0
        )
        try:
            intervalo = max(int(os.getenv(
                "API_FOOTBALL_COTA_RESSINCRONIZAR_SEGUNDOS", "60"
            )), 60)
        except (TypeError, ValueError):
            intervalo = 60
        referencia = max(
            observado_em,
            float(self.ultima_tentativa_ressincronizacao_cota_em or 0.0),
        )
        if agora_timestamp - referencia < intervalo:
            return {"tentada": False, "motivo": "intervalo_ressincronizacao"}

        self.ultima_tentativa_ressincronizacao_cota_em = agora_timestamp
        resultado = self.sincronizar_cota_status()
        if resultado.get("sincronizado"):
            self.ressincronizacoes_cota_bloqueada += 1
        else:
            self.falhas_ressincronizacao_cota_bloqueada += 1
        return {
            "tentada": True,
            "sincronizado": bool(resultado.get("sincronizado")),
            "motivo": resultado.get("motivo"),
            "categoria": categoria,
        }

    def _get(self, caminho, parametros, categoria, timeout=20):
        if not self.disponivel:
            return None

        prioridade, trava_requisicao = self._adquirir_trava_api(timeout)
        if trava_requisicao is None:
            self.ultimo_erro_api = "api_lock_timeout"
            if prioridade is not None:
                prioridade.liberar()
            return None
        try:
            # Outro processo pode ter consumido cota desde a criação desta
            # instância. Recarregar dentro da trava evita sobrescrever o uso.
            uso_atual = self._carregar_uso()
            if isinstance(uso_atual, dict):
                self.uso = uso_atual
            if not self._pode_chamar(categoria):
                self._ressincronizar_cota_bloqueada_se_devido(categoria)
                if not self._pode_chamar(categoria):
                    return None

            url = f"{BASE_URL}{caminho}?{urlencode(parametros)}"
            requisicao = Request(url, headers={"x-apisports-key": self.chave})
            # A franquia pode contabilizar a tentativa mesmo quando a resposta
            # falha; registrar antes da rede evita ultrapassar o plano.
            self._registrar_chamada(categoria)

            try:
                with urlopen(requisicao, timeout=max(float(timeout), 0.1)) as resposta:
                    corpo = resposta.read()
                    self._reconciliar_cota_provedor(
                        getattr(resposta, "headers", None)
                    )
                    dados = json.loads(corpo.decode("utf-8"))
            except HTTPError as erro:
                self._reconciliar_cota_provedor(
                    getattr(erro, "headers", None)
                )
                self._registrar_falha_api(erro)
                return None
            except (URLError, TimeoutError, json.JSONDecodeError) as erro:
                self._registrar_falha_api(erro)
                return None

            self._registrar_sucesso_api()
            return dados
        finally:
            self._liberar_travas_api(prioridade, trava_requisicao)

    def jogos_ao_vivo(self):
        agora = time.time()
        if self.cache_geral is None:
            persistido = self._ler_cache_persistente(
                "fixtures:live:all", "geral", CACHE_GERAL_SEGUNDOS, agora
            )
            if persistido is not None and isinstance(
                persistido["dados"], list
            ):
                self.cache_geral = persistido["dados"]
                self.cache_geral_em = persistido["em"]
        if (
            self.cache_geral is not None
            and agora - self.cache_geral_em < CACHE_GERAL_SEGUNDOS
        ):
            return self.cache_geral

        dados = self._get("/fixtures", {"live": "all"}, "geral")
        if dados is None:
            return self.cache_geral or []

        self.cache_geral = dados.get("response", [])
        self.cache_geral_em = agora
        self._salvar_cache_persistente(
            "fixtures:live:all", "geral", self.cache_geral, agora
        )
        return self.cache_geral

    def jogos_por_data(self, data, timezone_nome="America/New_York"):
        """Lista o calendário diário em uma chamada, com cache persistente."""
        data = str(data or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
            return []
        timezone_nome = str(timezone_nome or "UTC").strip() or "UTC"
        agora = time.time()
        chave = f"fixtures:date:{data}:{timezone_nome}"
        cache = self._ler_cache_persistente(
            chave, "geral", CACHE_FIXTURES_DIA_SEGUNDOS, agora
        )
        if cache is not None and isinstance(cache["dados"], list):
            return cache["dados"]
        resposta = self._get(
            "/fixtures",
            {"date": data, "timezone": timezone_nome},
            "geral",
            timeout=8.0,
        )
        if resposta is None or not isinstance(resposta.get("response"), list):
            return []
        itens = resposta["response"]
        self._salvar_cache_persistente(chave, "geral", itens, agora)
        return itens

    def odds_pre_jogo_por_data(self, data, maximo_paginas=40):
        """Varre as páginas de odds do dia e informa se a coleta foi completa."""
        data = str(data or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
            return {
                "itens": [], "completo": False, "paginas": 0,
                "total_paginas": None, "motivo": "data_invalida",
            }
        maximo_paginas = min(max(int(maximo_paginas), 1), 100)
        agora = time.time()
        itens = []
        pagina = 1
        total_paginas = None
        falha = None
        while pagina <= maximo_paginas:
            chave = f"odds:pre:date:{data}:page:{pagina}"
            cache = self._ler_cache_persistente(
                chave,
                "odds_pre_jogo",
                CACHE_ODDS_PRE_LIVE_DIA_SEGUNDOS,
                agora,
            )
            payload = None
            if cache is not None and isinstance(cache["dados"], dict):
                payload = cache["dados"]
            if payload is None:
                resposta = self._get(
                    "/odds",
                    {"date": data, "page": pagina},
                    "odds_pre_jogo",
                    timeout=8.0,
                )
                if resposta is None or not isinstance(
                    resposta.get("response"), list
                ):
                    falha = "pagina_indisponivel"
                    break
                payload = {
                    "response": resposta["response"],
                    "paging": resposta.get("paging") or {},
                }
                self._salvar_cache_persistente(
                    chave, "odds_pre_jogo", payload, agora
                )
            itens.extend(payload.get("response") or [])
            try:
                total_paginas = int(
                    (payload.get("paging") or {}).get("total") or pagina
                )
            except (TypeError, ValueError):
                total_paginas = pagina
            if pagina >= total_paginas:
                break
            pagina += 1
        completo = bool(
            falha is None
            and total_paginas is not None
            and pagina >= total_paginas
        )
        if not completo and falha is None and total_paginas is not None:
            falha = "limite_paginas_atingido"
        return {
            "itens": itens,
            "completo": completo,
            "paginas": pagina if itens else max(pagina - 1, 0),
            "total_paginas": total_paginas,
            "motivo": falha,
        }

    def fixtures_ao_vivo_detalhadas(self, fixture_ids):
        """Agrupa até 20 fixtures por chamada e reutiliza o payload completo."""
        ids = []
        for valor in fixture_ids or []:
            try:
                fixture_id = int(valor)
            except (TypeError, ValueError):
                continue
            if fixture_id > 0 and fixture_id not in ids:
                ids.append(fixture_id)
        resultados = []
        agora = time.time()
        for inicio in range(0, len(ids), 20):
            lote = ids[inicio:inicio + 20]
            chave_ids = "-".join(str(item) for item in sorted(lote))
            chave_cache = f"fixtures:live:details:{chave_ids}"
            cache = self._ler_cache_persistente(
                chave_cache,
                "live_detalhado",
                CACHE_FIXTURES_AO_VIVO_DETALHADAS_SEGUNDOS,
                agora,
            )
            if cache is not None and isinstance(cache["dados"], list):
                resultados.extend(cache["dados"])
                continue
            resposta = self._get(
                "/fixtures",
                {"ids": "-".join(str(item) for item in lote)},
                "detalhe",
                timeout=6.0,
            )
            if resposta is None or not isinstance(
                resposta.get("response"), list
            ):
                continue
            dados = resposta["response"]
            resultados.extend(dados)
            self._salvar_cache_persistente(
                chave_cache,
                "live_detalhado",
                dados,
                agora,
            )
        return resultados

    def validar_catalogo_odds_ao_vivo(self):
        agora = time.time()
        cache = self._ler_cache_persistente(
            "odds:live:bets:catalogo",
            "catalogo",
            CACHE_CATALOGO_ODDS_SEGUNDOS,
            agora,
        )
        if cache is not None and isinstance(cache["dados"], list):
            itens = cache["dados"]
            observado_em = datetime.fromtimestamp(cache["em"]).replace(
                microsecond=0
            ).isoformat()
        else:
            resposta = self._get("/odds/live/bets", {}, "catalogo")
            if resposta is None or not isinstance(
                resposta.get("response"), list
            ):
                return verificar_catalogo_odds_live(
                    self.arquivo_catalogo_odds
                )
            itens = resposta["response"]
            self._salvar_cache_persistente(
                "odds:live:bets:catalogo", "catalogo", itens, agora
            )
            observado_em = datetime.fromtimestamp(agora).replace(
                microsecond=0
            ).isoformat()
        estado = auditar_catalogo_odds_live(itens, observado_em)
        gravar_json_atomico(self.arquivo_catalogo_odds, estado)
        return verificar_catalogo_odds_live(self.arquivo_catalogo_odds)

    def estatisticas(self, fixture_id):
        agora = time.time()
        cache = self.cache_detalhes.get(fixture_id)
        if cache is None:
            cache = self._ler_cache_persistente(
                f"fixtures:statistics:{fixture_id}",
                "detalhe",
                CACHE_DETALHE_SEGUNDOS,
                agora,
            )
            if cache is not None and isinstance(cache["dados"], list):
                self.cache_detalhes[fixture_id] = cache
            else:
                cache = None
        if cache and agora - cache["em"] < CACHE_DETALHE_SEGUNDOS:
            return cache["dados"]

        resposta = self._get(
            "/fixtures/statistics",
            {"fixture": fixture_id},
            "detalhe",
        )
        if resposta is None:
            return None

        dados = resposta.get("response", [])
        self.cache_detalhes[fixture_id] = {"em": agora, "dados": dados}
        self._salvar_cache_persistente(
            f"fixtures:statistics:{fixture_id}", "detalhe", dados, agora
        )
        return dados

    def eventos(self, fixture_id):
        agora = time.time()
        cache = self.cache_eventos.get(fixture_id)
        if cache is None:
            cache = self._ler_cache_persistente(
                f"fixtures:events:{fixture_id}",
                "eventos",
                CACHE_EVENTOS_SEGUNDOS,
                agora,
            )
            if cache is not None and isinstance(cache["dados"], list):
                self.cache_eventos[fixture_id] = cache
            else:
                cache = None
        if cache and agora - cache["em"] < CACHE_EVENTOS_SEGUNDOS:
            return cache["dados"]

        resposta = self._get(
            "/fixtures/events",
            {"fixture": fixture_id},
            "detalhe",
        )
        if resposta is None:
            return None
        dados = resposta.get("response", [])
        self.cache_eventos[fixture_id] = {"em": agora, "dados": dados}
        self._salvar_cache_persistente(
            f"fixtures:events:{fixture_id}", "eventos", dados, agora
        )
        return dados

    def estatisticas_jogadores(self, fixture_id):
        agora = time.time()
        cache = self.cache_jogadores.get(fixture_id)
        if cache is None:
            cache = self._ler_cache_persistente(
                f"fixtures:players:{fixture_id}",
                "jogadores",
                CACHE_JOGADORES_AO_VIVO_SEGUNDOS,
                agora,
            )
            if cache is not None and isinstance(cache["dados"], list):
                self.cache_jogadores[fixture_id] = cache
            else:
                cache = None
        if (
            cache
            and agora - cache["em"] < CACHE_JOGADORES_AO_VIVO_SEGUNDOS
        ):
            return cache["dados"]

        resposta = self._get(
            "/fixtures/players",
            {"fixture": fixture_id},
            "detalhe",
            timeout=4.0,
        )
        if resposta is None:
            return None
        dados = resposta.get("response", [])
        self.cache_jogadores[fixture_id] = {
            "em": agora,
            "dados": dados,
        }
        self._salvar_cache_persistente(
            f"fixtures:players:{fixture_id}",
            "jogadores",
            dados,
            agora,
        )
        return dados

    def _dados_contexto(
        self, chave, caminho, parametros, ttl_segundos, prazo=None
    ):
        agora = time.time()
        cache = self._ler_cache_persistente(
            chave, "contexto", ttl_segundos, agora
        )
        if cache is not None and isinstance(cache["dados"], (list, dict)):
            return cache["dados"]
        restante = (
            prazo - time.monotonic() if prazo is not None else 20.0
        )
        if restante <= 0:
            return None
        resposta = self._get(
            caminho,
            parametros,
            "contexto",
            timeout=min(restante, 4.0),
        )
        if resposta is None or not isinstance(
            resposta.get("response"), (list, dict)
        ):
            return None
        dados = resposta["response"]
        self._salvar_cache_persistente(
            chave, "contexto", dados, agora
        )
        return dados

    def _lista_contexto(
        self, chave, caminho, parametros, ttl_segundos, prazo=None
    ):
        dados = self._dados_contexto(
            chave, caminho, parametros, ttl_segundos, prazo
        )
        return dados if isinstance(dados, list) else None

    def contexto_pre_jogo(self, confirmacao):
        fixture_id = (confirmacao or {}).get("fixture_id")
        times = (confirmacao or {}).get("times") or {}
        mandante_id = ((times.get("home") or {}).get("id"))
        visitante_id = ((times.get("away") or {}).get("id"))
        if not fixture_id or not mandante_id or not visitante_id:
            return None
        prazo = time.monotonic() + ORCAMENTO_CONTEXTO_POR_JOGO_SEGUNDOS
        odds_pre_jogo = self.odds_pre_jogo(fixture_id, prazo=prazo)

        h2h = self._lista_contexto(
            f"contexto:h2h:{mandante_id}:{visitante_id}",
            "/fixtures/headtohead",
            {"h2h": f"{mandante_id}-{visitante_id}", "last": 10},
            CACHE_CONTEXTO_PRE_JOGO_SEGUNDOS,
            prazo,
        )
        forma_mandante = self._lista_contexto(
            f"contexto:forma:{mandante_id}",
            "/fixtures",
            {"team": mandante_id, "last": 5, "status": "FT"},
            CACHE_CONTEXTO_PRE_JOGO_SEGUNDOS,
            prazo,
        )
        forma_visitante = self._lista_contexto(
            f"contexto:forma:{visitante_id}",
            "/fixtures",
            {"team": visitante_id, "last": 5, "status": "FT"},
            CACHE_CONTEXTO_PRE_JOGO_SEGUNDOS,
            prazo,
        )
        escalacoes = (confirmacao or {}).get(
            "_escalacoes_embutidas"
        )
        if not isinstance(escalacoes, list) or not escalacoes:
            escalacoes = self._lista_contexto(
                f"contexto:escalacoes:{fixture_id}",
                "/fixtures/lineups",
                {"fixture": fixture_id},
                CACHE_CONTEXTO_DINAMICO_SEGUNDOS,
                prazo,
            )
        desfalques = self._lista_contexto(
            f"contexto:desfalques:{fixture_id}",
            "/injuries",
            {"fixture": fixture_id},
            CACHE_CONTEXTO_DINAMICO_SEGUNDOS,
            prazo,
        )
        previsao = self._lista_contexto(
            f"contexto:previsao:{fixture_id}",
            "/predictions",
            {"fixture": fixture_id},
            CACHE_CONTEXTO_PRE_JOGO_SEGUNDOS,
            prazo,
        )
        classificacao = None
        estatisticas_times = {}
        liga = (confirmacao or {}).get("liga") or {}
        liga_id, temporada = liga.get("id"), liga.get("season")
        if liga_id and temporada:
            classificacao = self._lista_contexto(
                f"contexto:classificacao:{liga_id}:{temporada}",
                "/standings",
                {"league": liga_id, "season": temporada},
                3600,
                prazo,
            )
            for rotulo, time_id in (
                ("mandante", mandante_id),
                ("visitante", visitante_id),
            ):
                dados = self._dados_contexto(
                    f"contexto:time:{time_id}:{liga_id}:{temporada}",
                    "/teams/statistics",
                    {
                        "team": time_id,
                        "league": liga_id,
                        "season": temporada,
                    },
                    CACHE_CONTEXTO_PRE_JOGO_SEGUNDOS,
                    prazo,
                )
                if isinstance(dados, dict) and dados:
                    estatisticas_times[rotulo] = dados

        ids_historico = []
        for item in (forma_mandante or []) + (forma_visitante or []):
            fixture_historico = ((item.get("fixture") or {}).get("id"))
            if fixture_historico is not None:
                ids_historico.append(int(fixture_historico))
        ids_historico = list(dict.fromkeys(ids_historico))[:20]
        historico_detalhado = None
        if ids_historico:
            chave_ids = "-".join(
                str(fixture_id) for fixture_id in sorted(ids_historico)
            )
            historico_detalhado = self._lista_contexto(
                f"contexto:fixtures_detalhadas:{chave_ids}",
                "/fixtures",
                {"ids": "-".join(str(item) for item in ids_historico)},
                CACHE_CONTEXTO_PRE_JOGO_SEGUNDOS,
                prazo,
            )

        return resumir_contexto_pre_jogo(
            confirmacao,
            h2h=h2h,
            escalacoes=escalacoes,
            desfalques=desfalques,
            forma_mandante=forma_mandante,
            forma_visitante=forma_visitante,
            estatisticas_times=estatisticas_times,
            previsao=(previsao or [None])[0],
            classificacao=classificacao,
            historico_detalhado=historico_detalhado,
            odds_pre_jogo=odds_pre_jogo,
        )

    def odds_pre_jogo(self, fixture_id, prazo=None):
        try:
            fixture_id = int(fixture_id)
        except (TypeError, ValueError):
            return None
        if fixture_id <= 0:
            return None
        agora = time.time()
        chave = f"odds:pre:fixture:{fixture_id}"
        cache = self._ler_cache_persistente(
            chave,
            "odds_pre_jogo",
            CACHE_ODDS_PRE_JOGO_SEGUNDOS,
            agora,
        )
        if cache is not None and isinstance(cache["dados"], list):
            return cache["dados"]
        restante = prazo - time.monotonic() if prazo is not None else 4.0
        if restante <= 0:
            return None
        resposta = self._get(
            "/odds",
            {"fixture": fixture_id},
            "odds_pre_jogo",
            timeout=min(restante, 4.0),
        )
        if resposta is None or not isinstance(
            resposta.get("response"), list
        ):
            return None
        dados = resposta["response"]
        self._salvar_cache_persistente(
            chave, "odds_pre_jogo", dados, agora
        )
        return dados

    def partidas_por_ids(self, fixture_ids):
        agora = time.time()
        ids = []
        resultados = []
        for fixture_id in dict.fromkeys(fixture_ids):
            cache = self.cache_resultados.get(fixture_id)
            if cache is None:
                cache = self._ler_cache_persistente(
                    f"fixtures:result:{fixture_id}",
                    "resultado",
                    CACHE_RESULTADOS_SEGUNDOS,
                    agora,
                )
                if cache is not None and isinstance(cache["dados"], dict):
                    self.cache_resultados[fixture_id] = cache
                else:
                    cache = None
            if cache and agora - cache["em"] < CACHE_RESULTADOS_SEGUNDOS:
                resultados.append(cache["dados"])
            else:
                ids.append(fixture_id)

        for inicio in range(0, len(ids), 20):
            lote = ids[inicio:inicio + 20]
            resposta = self._get(
                "/fixtures",
                {"ids": "-".join(str(item) for item in lote)},
                "geral",
            )
            if resposta is None:
                continue
            for item in resposta.get("response", []):
                fixture_id = item.get("fixture", {}).get("id")
                if fixture_id is not None:
                    self.cache_resultados[fixture_id] = {
                        "em": agora,
                        "dados": item,
                    }
                    self._salvar_cache_persistente(
                        f"fixtures:result:{fixture_id}",
                        "resultado",
                        item,
                        agora,
                    )
                    resultados.append(item)
        return resultados

    def _salvar_estado_capacidade_referencia(self):
        gravar_json_atomico(
            self.arquivo_capacidade_referencia,
            self.estado_capacidade_referencia,
        )

    def _registrar_capacidade_referencia_payload(
        self, bet_id, itens, observado_em=None
    ):
        """Aprende capacidade do provedor sem misturar isso aos sinais."""
        chave = str(int(bet_id))
        por_bet = self.estado_capacidade_referencia.get("por_bet") or {}
        if chave not in por_bet:
            return None
        observado_epoch = float(
            observado_em if observado_em is not None else time.time()
        )
        observado_iso = datetime.fromtimestamp(
            observado_epoch
        ).astimezone().isoformat(timespec="seconds")
        estado = por_bet[chave]
        diagnostico = diagnosticar_capacidade_referencia_payload(itens)
        if (
            estado.get("ultima_amostra_em") == observado_iso
            and estado.get("fixtures_ultima_amostra")
            == diagnostico["fixtures"]
            and estado.get("bookmakers_disponiveis")
            == diagnostico["bookmakers_disponiveis"]
        ):
            return dict(estado)
        # Uma resposta global vazia não prova ausência de identidade; pode
        # simplesmente não haver eventos com aquele mercado naquele instante.
        if diagnostico["fixtures"] <= 0:
            return dict(estado)
        estado["amostras"] += 1
        estado["fixtures_ultima_amostra"] = diagnostico["fixtures"]
        estado["fixtures_com_bookmakers"] = diagnostico[
            "fixtures_com_bookmakers"
        ]
        estado["bookmakers_disponiveis"] = diagnostico[
            "bookmakers_disponiveis"
        ]
        estado["bookmakers_independentes"] = diagnostico[
            "bookmakers_independentes"
        ]
        tem_identidade = diagnostico["identidade_bookmaker_disponivel"]
        estado["identidade_bookmaker_disponivel"] = tem_identidade
        if tem_identidade:
            estado["amostras_com_identidade"] += 1
            estado["sem_identidade_consecutivas"] = 0
            estado["proxima_sondagem_em"] = None
        else:
            estado["amostras_sem_identidade"] += 1
            estado["sem_identidade_consecutivas"] += 1
            estado["proxima_sondagem_em"] = (
                datetime.fromtimestamp(observado_epoch).astimezone()
                + timedelta(
                    seconds=CAPACIDADE_REFERENCIA_SONDAGEM_SEGUNDOS
                )
            ).isoformat(timespec="seconds")
        estado["ultima_amostra_em"] = observado_iso
        self.estado_capacidade_referencia["atualizado_em"] = observado_iso
        self._salvar_estado_capacidade_referencia()
        return dict(estado)

    def _diagnostico_capacidade_referencia(self, bet_id, agora=None):
        estado_disco = verificar_capacidade_referencia_api(
            self.arquivo_capacidade_referencia
        )
        if estado_disco.get("saudavel") and estado_disco.get(
            "estado"
        ) != "novo":
            self.estado_capacidade_referencia = {
                chave: estado_disco[chave]
                for chave in _estado_capacidade_referencia_padrao()
            }
        chave = str(int(bet_id))
        estado = dict(
            (self.estado_capacidade_referencia.get("por_bet") or {}).get(
                chave, _estado_capacidade_referencia_por_bet_padrao()
            )
        )
        agora_data = datetime.fromtimestamp(
            float(agora if agora is not None else time.time())
        ).astimezone()
        proxima = estado.get("proxima_sondagem_em")
        try:
            proxima_data = datetime.fromisoformat(str(proxima))
            if proxima_data.tzinfo is None:
                proxima_data = proxima_data.astimezone()
            restante = max(
                (proxima_data - agora_data).total_seconds(), 0.0
            )
        except (TypeError, ValueError):
            restante = 0.0
        bloqueada = bool(
            estado.get("identidade_bookmaker_disponivel") is False
            and estado.get("sem_identidade_consecutivas", 0) >= 1
            and restante > 0
            and os.getenv(
                "API_FOOTBALL_REFERENCIA_FORCAR_SONDAGEM", "0"
            ) != "1"
        )
        return {
            "versao": "api-football-referencia-capacidade-v1",
            "bet_id": int(bet_id),
            "amostras": estado.get("amostras", 0),
            "amostras_com_identidade": estado.get(
                "amostras_com_identidade", 0
            ),
            "amostras_sem_identidade": estado.get(
                "amostras_sem_identidade", 0
            ),
            "sem_identidade_consecutivas": estado.get(
                "sem_identidade_consecutivas", 0
            ),
            "fixtures_ultima_amostra": estado.get(
                "fixtures_ultima_amostra", 0
            ),
            "fixtures_com_bookmakers": estado.get(
                "fixtures_com_bookmakers", 0
            ),
            "bookmakers_disponiveis": list(
                estado.get("bookmakers_disponiveis") or []
            ),
            "bookmakers_independentes": list(
                estado.get("bookmakers_independentes") or []
            ),
            "identidade_bookmaker_disponivel": estado.get(
                "identidade_bookmaker_disponivel"
            ),
            "ultima_amostra_em": estado.get("ultima_amostra_em"),
            "proxima_sondagem_em": proxima,
            "segundos_ate_sondagem": round(restante, 1),
            "consulta_referencia_bloqueada": bloqueada,
            "consultas_referencia_suprimidas": estado.get(
                "consultas_referencia_suprimidas", 0
            ),
            "rollback": "API_FOOTBALL_REFERENCIA_FORCAR_SONDAGEM=1",
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }

    def _suprimir_consulta_referencia_por_capacidade(
        self, bet_id, agora=None
    ):
        agora_epoch = float(agora if agora is not None else time.time())
        diagnostico = self._diagnostico_capacidade_referencia(
            bet_id, agora_epoch
        )
        if not diagnostico["consulta_referencia_bloqueada"]:
            return diagnostico
        estado = self.estado_capacidade_referencia["por_bet"][
            str(int(bet_id))
        ]
        estado["consultas_referencia_suprimidas"] += 1
        estado["ultima_supressao_em"] = datetime.fromtimestamp(
            agora_epoch
        ).astimezone().isoformat(timespec="seconds")
        self.estado_capacidade_referencia["atualizado_em"] = estado[
            "ultima_supressao_em"
        ]
        self._salvar_estado_capacidade_referencia()
        diagnostico["consultas_referencia_suprimidas"] = estado[
            "consultas_referencia_suprimidas"
        ]
        return diagnostico

    def _carregar_itens_odds_ao_vivo(self, bet_id):
        """Carrega uma resposta global de odds com cache compartilhado."""
        agora = time.time()
        cache = self.cache_odds_ao_vivo.get(bet_id)
        if cache is None:
            cache = self._ler_cache_persistente(
                f"odds:live:bet:{bet_id}",
                "odds",
                CACHE_ODDS_AO_VIVO_SEGUNDOS,
                agora,
            )
            if cache is not None and isinstance(cache["dados"], list):
                self.cache_odds_ao_vivo[bet_id] = cache
            else:
                cache = None
        if (
            cache is not None
            and agora - cache["em"] < CACHE_ODDS_AO_VIVO_SEGUNDOS
        ):
            itens = cache["dados"]
            idade = agora - cache["em"]
        else:
            if self._consulta_odds_suspensa(bet_id, agora):
                return [], None
            resposta = self._get(
                "/odds/live",
                {"bet": bet_id},
                "odds",
            )
            self._registrar_consulta_odds(resposta, bet_id)
            if resposta is not None:
                itens = resposta.get("response", [])
                cache = {"em": agora, "dados": itens}
                self.cache_odds_ao_vivo[bet_id] = cache
                self._salvar_cache_persistente(
                    f"odds:live:bet:{bet_id}", "odds", itens, agora
                )
                idade = 0.0
            elif cache is not None:
                itens = cache["dados"]
                idade = agora - cache["em"]
            else:
                return [], None
        self._registrar_capacidade_referencia_payload(
            bet_id, itens, observado_em=agora - float(idade or 0.0)
        )
        return itens, idade

    def _odds_escanteios_asiaticos(self, fixture_id, bet_id, diagnosticar):
        """Busca globalmente um bet e devolve a oferta da fixture pedida.

        Uma unica resposta fica compartilhada entre todas as partidas por cinco
        minutos, evitando uma requisicao por jogo. Cache antigo pode ser usado
        em falha de rede, mas carrega sua idade e sera bloqueado pelo motor.
        """
        itens, idade = self._carregar_itens_odds_ao_vivo(bet_id)
        if idade is None:
            return None

        try:
            fixture_id = int(fixture_id)
        except (TypeError, ValueError):
            return None
        for item in itens:
            fixture = item.get("fixture") or {}
            try:
                encontrado = int(fixture.get("id"))
            except (TypeError, ValueError):
                continue
            if encontrado == fixture_id:
                mercado, motivo = diagnosticar(item, idade)
                self._registrar_resultado_fixture_odds(
                    bet_id,
                    anexada=mercado is not None,
                    encontrada=True,
                    motivo=motivo,
                )
                return mercado
        self._registrar_resultado_fixture_odds(
            bet_id, anexada=False, encontrada=False
        )
        return None

    def ofertas_escanteios_asiaticos_ft_por_fixture(self):
        """Mapeia fixture para sua oferta FT usando o cache global único."""
        itens, idade = self._carregar_itens_odds_ao_vivo(
            BET_ESCANTEIOS_ASIATICOS_FT
        )
        if idade is None:
            return {}
        ofertas = {}
        for item in itens:
            fixture = item.get("fixture") or {}
            try:
                fixture_id = int(fixture.get("id"))
            except (TypeError, ValueError):
                continue
            mercado, _motivo = diagnosticar_escanteios_asiaticos_ft_api(
                item, idade
            )
            if mercado is not None:
                oferta = (mercado.get("ofertas") or [None])[0]
                if isinstance(oferta, dict):
                    ofertas[fixture_id] = dict(oferta)
        return ofertas

    def fixtures_com_odds_escanteios_asiaticos_ft(self):
        """Lista fixtures com oferta FT válida para priorização da fila."""
        return set(self.ofertas_escanteios_asiaticos_ft_por_fixture())

    def odds_escanteios_asiaticos_ft(self, fixture_id):
        return self._odds_escanteios_asiaticos(
            fixture_id,
            BET_ESCANTEIOS_ASIATICOS_FT,
            diagnosticar_escanteios_asiaticos_ft_api,
        )

    def odds_escanteios_asiaticos_1t(self, fixture_id):
        return self._odds_escanteios_asiaticos(
            fixture_id,
            BET_ESCANTEIOS_ASIATICOS_1T,
            diagnosticar_escanteios_asiaticos_1t_api,
        )

    def odds_gols_total_ft(self, fixture_id):
        return self._odds_escanteios_asiaticos(
            fixture_id,
            BET_GOLS_TOTAL_FT,
            diagnosticar_gols_total_api,
        )

    def odds_gols_total_ht(self, fixture_id):
        return self._odds_escanteios_asiaticos(
            fixture_id,
            BET_GOLS_TOTAL_HT,
            diagnosticar_gols_total_ht_api,
        )

    def odds_referencia_independente(
        self,
        fixture_id,
        mercado,
        bookmaker_excluido="bet365",
        maximo_bookmakers=5,
    ):
        """Obtém livros alternativos para referência, nunca para operação.

        A resposta global já possui cache compartilhado por mercado. A escolha
        dos bookmakers é lexical e limitada, sem olhar o tamanho da odd, para
        impedir seleção retrospectiva da casa mais favorável à hipótese.
        """
        configuracoes = {
            "gol_ft": (
                BET_GOLS_TOTAL_FT, diagnosticar_gols_total_api,
            ),
            "gol_ht": (
                BET_GOLS_TOTAL_HT, diagnosticar_gols_total_ht_api,
            ),
            "escanteios_ft_asiatico": (
                BET_ESCANTEIOS_ASIATICOS_FT,
                diagnosticar_escanteios_asiaticos_ft_api,
            ),
        }
        base = {
            "versao": "api-football-referencia-sombra-v1",
            "fixture_id": fixture_id,
            "mercado": str(mercado or ""),
            "bookmaker_excluido": str(bookmaker_excluido or ""),
            "bookmakers_avaliados": 0,
            "bookmakers_independentes": [],
            "mercados_retornados": 0,
            "consulta_rede_realizada": False,
            "consulta_rede_evitada": False,
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        configuracao = configuracoes.get(str(mercado or "").strip())
        if configuracao is None:
            return [], {**base, "motivo": "mercado_nao_suportado"}
        try:
            fixture_id = int(fixture_id)
            limite = max(min(int(maximo_bookmakers), 10), 1)
        except (TypeError, ValueError):
            return [], {**base, "motivo": "parametros_invalidos"}
        bet_id, diagnosticar = configuracao
        capacidade = self._suprimir_consulta_referencia_por_capacidade(
            bet_id
        )
        base["bet_id"] = bet_id
        base["capacidade_referencia"] = capacidade
        if capacidade["consulta_referencia_bloqueada"]:
            return [], {
                **base,
                "cache": None,
                "consulta_rede_evitada": True,
                "motivo": "fonte_live_sem_identidade_bookmaker",
            }
        itens, idade = self._carregar_itens_odds_ao_vivo(bet_id)
        capacidade = self._diagnostico_capacidade_referencia(bet_id)
        base.update({
            "fixture_id": fixture_id,
            "bet_id": bet_id,
            "idade_segundos": (
                round(float(idade), 3) if idade is not None else None
            ),
            "cache": bool(idade is not None and idade > 0),
            "consulta_rede_realizada": bool(idade == 0),
            "capacidade_referencia": capacidade,
        })
        if idade is None:
            return [], {**base, "motivo": "odds_indisponiveis"}
        if (
            capacidade.get("identidade_bookmaker_disponivel") is False
            and capacidade.get("fixtures_ultima_amostra", 0) > 0
        ):
            return [], {
                **base,
                "motivo": "fonte_live_sem_identidade_bookmaker",
            }
        item_fixture = None
        for item in itens or []:
            try:
                encontrado = int((item.get("fixture") or {}).get("id"))
            except (AttributeError, TypeError, ValueError):
                continue
            if encontrado == fixture_id:
                item_fixture = item
                break
        if not isinstance(item_fixture, dict):
            return [], {**base, "motivo": "fixture_sem_odds_no_mercado"}

        excluido = normalizar_nome(bookmaker_excluido)
        bookmakers = sorted(
            [
                item for item in item_fixture.get("bookmakers") or []
                if isinstance(item, dict)
                and str(item.get("name") or "").strip()
                and normalizar_nome(item.get("name")) != excluido
            ],
            key=lambda item: normalizar_nome(item.get("name")),
        )
        base["bookmakers_avaliados"] = len(bookmakers)
        mercados = []
        motivos = {}
        for bookmaker in bookmakers[:limite]:
            isolado = {
                **item_fixture,
                "odds": [],
                "bookmakers": [bookmaker],
            }
            convertido, motivo = diagnosticar(isolado, idade)
            if convertido is None:
                chave = str(motivo or "conversao_indisponivel")
                motivos[chave] = int(motivos.get(chave, 0)) + 1
                continue
            mercados.append(convertido)
            base["bookmakers_independentes"].append(
                str(bookmaker.get("name") or "").strip()
            )
        base["mercados_retornados"] = len(mercados)
        base["motivos_conversao"] = dict(sorted(motivos.items()))
        base["motivo"] = (
            "referencias_independentes_disponiveis"
            if mercados
            else "sem_bookmaker_independente_valido"
        )
        return mercados, base

    def odds_proximo_gol(self, fixture_id, total_gols):
        try:
            total_gols = int(total_gols)
        except (TypeError, ValueError):
            return None
        bet_id = BETS_PROXIMO_GOL_POR_TOTAL.get(total_gols)
        if bet_id is None:
            return None
        nome_esperado = MERCADOS_ODDS_LIVE_ESPERADOS[bet_id]

        def diagnosticar(item, idade_segundos):
            return diagnosticar_proximo_gol_api(
                item,
                bet_id,
                nome_esperado,
                idade_segundos,
            )

        return self._odds_escanteios_asiaticos(
            fixture_id,
            bet_id,
            diagnosticar,
        )

    def _registrar_consulta_odds(self, resposta, bet_id):
        agora_data = datetime.now().replace(microsecond=0)
        agora = agora_data.isoformat()
        bet_id = int(bet_id)
        por_bet = self.estado_odds["por_bet"][str(bet_id)]
        self.estado_odds["consultas"] += 1
        self.estado_odds["ultima_consulta_em"] = agora
        self.estado_odds["ultimo_bet_id"] = bet_id
        por_bet["consultas"] += 1
        por_bet["ultima_consulta_em"] = agora
        if resposta is None:
            self.estado_odds["falhas"] += 1
            self.estado_odds["ultimo_total_fixtures"] = None
            por_bet["falhas"] += 1
            por_bet["ultimo_total_fixtures"] = None
        else:
            itens = resposta.get("response", [])
            total = len(itens) if isinstance(itens, list) else 0
            self.estado_odds["ultimo_total_fixtures"] = total
            por_bet["ultimo_total_fixtures"] = total
            if total:
                self.estado_odds["com_ofertas_globais"] += 1
                self.estado_odds["ultima_oferta_em"] = agora
                por_bet["com_ofertas_globais"] += 1
                por_bet["ultima_oferta_global_em"] = agora
                por_bet["sem_ofertas_consecutivas"] = 0
                por_bet["suspenso_ate"] = None
            else:
                self.estado_odds["sem_ofertas_globais"] += 1
                por_bet["sem_ofertas_globais"] += 1
                por_bet["sem_ofertas_consecutivas"] += 1
                if (
                    bet_id == BET_ESCANTEIOS_ASIATICOS_1T
                    and por_bet["sem_ofertas_consecutivas"]
                    >= self.limite_vazias_consecutivas_odds_1t
                ):
                    por_bet["suspensoes"] += 1
                    por_bet["ultima_suspensao_em"] = agora
                    por_bet["suspenso_ate"] = (
                        agora_data
                        + timedelta(
                            seconds=self.suspensao_odds_1t_segundos
                        )
                    ).isoformat()
        gravar_json_atomico(self.arquivo_estado_odds, self.estado_odds)

    def _consulta_odds_suspensa(self, bet_id, agora_epoch=None):
        bet_id = int(bet_id)
        if bet_id != BET_ESCANTEIOS_ASIATICOS_1T:
            return False
        agora_data = datetime.fromtimestamp(
            float(agora_epoch if agora_epoch is not None else time.time())
        ).replace(microsecond=0)
        por_bet = self.estado_odds["por_bet"][str(bet_id)]
        suspenso_ate = por_bet.get("suspenso_ate")
        if (
            not suspenso_ate
            and por_bet.get("sem_ofertas_consecutivas", 0)
            >= self.limite_vazias_consecutivas_odds_1t
        ):
            por_bet["suspensoes"] += 1
            por_bet["ultima_suspensao_em"] = agora_data.isoformat()
            suspenso_ate = (
                agora_data
                + timedelta(seconds=self.suspensao_odds_1t_segundos)
            ).isoformat()
            por_bet["suspenso_ate"] = suspenso_ate
        try:
            ativo = agora_data < datetime.fromisoformat(suspenso_ate)
        except (TypeError, ValueError):
            ativo = False
        if not ativo:
            return False
        ultima = por_bet.get("ultima_supressao_em")
        try:
            registrar = (
                agora_data - datetime.fromisoformat(ultima)
            ).total_seconds() >= CACHE_ODDS_AO_VIVO_SEGUNDOS
        except (TypeError, ValueError):
            registrar = True
        if registrar:
            por_bet["consultas_suprimidas"] += 1
            por_bet["ultima_supressao_em"] = agora_data.isoformat()
            gravar_json_atomico(
                self.arquivo_estado_odds, self.estado_odds
            )
        return True

    def _registrar_resultado_fixture_odds(
        self, bet_id, anexada, encontrada, motivo=None
    ):
        agora = datetime.now().replace(microsecond=0).isoformat()
        por_bet = self.estado_odds["por_bet"][str(int(bet_id))]
        por_bet["solicitacoes_fixture"] += 1
        if encontrada:
            por_bet["fixtures_correspondentes"] += 1
            if anexada:
                por_bet["ofertas_anexadas"] += 1
                por_bet["ultima_oferta_anexada_em"] = agora
            else:
                por_bet["ofertas_rejeitadas"] += 1
                motivo = motivo or "motivo_desconhecido"
                rejeicoes = por_bet["rejeicoes_por_motivo"]
                rejeicoes[motivo] = rejeicoes.get(motivo, 0) + 1
                por_bet["ultimo_motivo_rejeicao"] = motivo
        gravar_json_atomico(self.arquivo_estado_odds, self.estado_odds)

    def consumo_atual(self):
        agora = _agora_cota()
        mes = agora.strftime("%Y-%m")
        dia = agora.strftime("%Y-%m-%d")
        consumo_dia = self.uso["dias"].get(
            dia, {"geral": 0, "detalhe": 0}
        )
        total_dia = sum(consumo_dia.values())
        limite_efetivo = self._limite_diario_efetivo(dia)
        provedor = self.uso.get("provedor") or {}
        return {
            "mes": self.uso["meses"].get(mes, 0),
            "dia": consumo_dia,
            "total_dia": total_dia,
            "limite_diario_plano": self.limite_diario,
            "limite_diario_seguro": limite_efetivo,
            "limite_diario_configurado_seguro": self.limite_diario_seguro,
            "reserva_diaria": self.reserva_diaria,
            "restante_seguro_dia": max(
                limite_efetivo - total_dia, 0
            ),
            "contador_saudavel": self.controle_uso_saudavel,
            "contador_origem": self.controle_uso_origem,
            "contador_recuperado_backup": self.controle_uso_recuperado,
            "cache_persistente_hits": self.cache_persistente_hits,
            "cache_persistente_gravacoes": (
                self.cache_persistente_gravacoes
            ),
            "cache_persistente_descartes": (
                self.cache_persistente_descartes
            ),
            "cache_persistente_falhas": self.cache_persistente_falhas,
            "cache_persistente_limpezas": self.cache_persistente_limpezas,
            "reconciliacoes_cota": self.reconciliacoes_cota,
            "cabecalhos_cota_invalidos": self.cabecalhos_cota_invalidos,
            "ressincronizacoes_cota_bloqueada": (
                self.ressincronizacoes_cota_bloqueada
            ),
            "falhas_ressincronizacao_cota_bloqueada": (
                self.falhas_ressincronizacao_cota_bloqueada
            ),
            "ultima_tentativa_ressincronizacao_cota_em": (
                self.ultima_tentativa_ressincronizacao_cota_em or None
            ),
            "saude_api": self.saude_operacional(),
            "cota_provedor": dict(provedor),
        }


def normalizar_nome(nome):
    texto = unicodedata.normalize("NFKD", nome or "")
    texto = "".join(letra for letra in texto if not unicodedata.combining(letra))
    return "".join(letra.lower() for letra in texto if letra.isalnum())


def _tokens_nome(nome):
    texto = unicodedata.normalize("NFKD", str(nome or ""))
    texto = "".join(
        letra for letra in texto if not unicodedata.combining(letra)
    ).lower()
    return re.findall(r"[a-z0-9]+", texto)


def _sigla_exata_contida(nome_curto, nome_longo):
    """Reconhece somente siglas explícitas, como BATE e MVV.

    Não transforma qualquer palavra compartilhada em alias. Isso evita unir,
    por exemplo, um clube chamado apenas ``United`` a qualquer outro United.
    A associação ainda precisa passar pelo segundo time, placar, minuto,
    categoria e margem contra os demais candidatos.
    """
    curto = str(nome_curto or "").strip()
    tokens_curto = _tokens_nome(curto)
    if len(tokens_curto) != 1:
        return False
    token = tokens_curto[0]
    letras = "".join(letra for letra in curto if letra.isalpha())
    if len(token) < 3 or not letras or letras != letras.upper():
        return False
    return token in _tokens_nome(nome_longo)


def _similaridade(a, b):
    nota = SequenceMatcher(
        None, normalizar_nome(a), normalizar_nome(b)
    ).ratio()
    if _sigla_exata_contida(a, b) or _sigla_exata_contida(b, a):
        # 0,90 é suficiente para reconhecer o alias, sem equivaler a uma
        # identidade perfeita. Os demais validadores continuam obrigatórios.
        nota = max(nota, 0.90)
    return nota


def _categoria_equipe(nome):
    texto = unicodedata.normalize("NFKD", str(nome or ""))
    texto = "".join(
        letra for letra in texto if not unicodedata.combining(letra)
    ).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto).strip()
    idade = re.search(r"\bu\s*(1[5-9]|2[0-3])\b", texto)
    if idade is None:
        idade = re.search(r"\bunder\s*(1[5-9]|2[0-3])\b", texto)
    feminino = bool(re.search(
        r"\b(w|women|woman|feminino|feminina|femenil|ladies)\b",
        texto,
    ))
    return {
        "idade": int(idade.group(1)) if idade else None,
        "feminino": feminino,
    }


def _categorias_equipes_compativeis(nome_a, nome_b):
    primeira = _categoria_equipe(nome_a)
    segunda = _categoria_equipe(nome_b)
    if primeira["feminino"] != segunda["feminino"]:
        return False
    if primeira["idade"] != segunda["idade"] and (
        primeira["idade"] is not None or segunda["idade"] is not None
    ):
        return False
    return True


def _placar(valor):
    if isinstance(valor, (list, tuple)) and len(valor) >= 2:
        return list(valor[:2])
    numeros = re.findall(r"\d+", str(valor or ""))
    return [int(numeros[0]), int(numeros[1])] if len(numeros) >= 2 else None


def _minuto(valor):
    texto = str(valor or "").lower()
    if "intervalo" in texto or texto.strip() == "ht":
        return 45
    numeros = re.findall(r"\d{1,3}", texto)
    return int(numeros[0]) if numeros else None


MARGEM_MINIMA_ASSOCIACAO = 0.03


def diagnosticar_associacao(
    jogo_packball,
    fixtures_api,
    margem_minima=MARGEM_MINIMA_ASSOCIACAO,
):
    candidatos = {}
    fixtures_validas = 0
    nomes_compativeis = 0
    rejeicoes_categoria = 0
    rejeicoes_placar = 0
    rejeicoes_minuto = 0
    candidatos_nomes = []

    for item in fixtures_api:
        if not isinstance(item, dict):
            continue
        fixture_id = (item.get("fixture") or {}).get("id")
        if fixture_id is None:
            continue
        fixtures_validas += 1
        times = item.get("teams", {})
        casa = times.get("home", {}).get("name", "")
        fora = times.get("away", {}).get("name", "")
        direta = (
            _similaridade(jogo_packball["mandante"], casa),
            _similaridade(jogo_packball["visitante"], fora),
        )
        invertida = (
            _similaridade(jogo_packball["mandante"], fora),
            _similaridade(jogo_packball["visitante"], casa),
        )
        if sum(direta) >= sum(invertida):
            notas = direta
            orientacao = "direta"
        else:
            notas = invertida
            orientacao = "invertida"
        nota_nomes = sum(notas) / 2
        candidatos_nomes.append({
            "fixture_id": fixture_id,
            "mandante_api": casa,
            "visitante_api": fora,
            "orientacao": orientacao,
            "similaridades": [round(valor, 3) for valor in notas],
            "nota_nomes": round(nota_nomes, 3),
        })
        if min(notas) < 0.55 or nota_nomes < 0.68:
            continue
        nomes_compativeis += 1
        if orientacao == "direta":
            pares_nomes = (
                (jogo_packball["mandante"], casa),
                (jogo_packball["visitante"], fora),
            )
        else:
            pares_nomes = (
                (jogo_packball["mandante"], fora),
                (jogo_packball["visitante"], casa),
            )
        if not all(
            _categorias_equipes_compativeis(packball, api)
            for packball, api in pares_nomes
        ):
            rejeicoes_categoria += 1
            continue

        gols = item.get("goals") or {}
        placar_api = [gols.get("home"), gols.get("away")]
        if orientacao == "invertida":
            placar_api.reverse()
        placar_packball = _placar(jogo_packball.get("placar"))
        if (
            placar_packball is not None
            and None not in placar_api
            and sum(abs(a - b) for a, b in zip(placar_packball, placar_api)) > 2
        ):
            rejeicoes_placar += 1
            continue

        minuto_packball = _minuto(jogo_packball.get("status"))
        minuto_api = (item.get("fixture", {}).get("status") or {}).get(
            "elapsed"
        )
        if (
            minuto_packball is not None
            and isinstance(minuto_api, (int, float))
            and abs(minuto_packball - minuto_api) > 15
        ):
            rejeicoes_minuto += 1
            continue

        nota = nota_nomes
        if placar_packball is not None and placar_packball == placar_api:
            nota += 0.05
        if minuto_packball is not None and isinstance(minuto_api, (int, float)):
            nota += max(0, 0.05 - abs(minuto_packball - minuto_api) * 0.005)
        nota = min(nota, 1.0)

        candidato = {
            "nota": nota,
            "item": item,
            "orientacao": orientacao,
        }
        anterior = candidatos.get(fixture_id)
        if anterior is None or nota > anterior["nota"]:
            candidatos[fixture_id] = candidato

    ordenados = sorted(
        candidatos.values(), key=lambda candidato: candidato["nota"],
        reverse=True,
    )
    if not ordenados:
        if fixtures_validas == 0:
            motivo = "sem_fixtures"
        elif nomes_compativeis == 0:
            motivo = "nomes_incompativeis"
        elif rejeicoes_categoria:
            motivo = "categoria_equipes_incompativel"
        elif rejeicoes_placar and rejeicoes_minuto:
            motivo = "placar_ou_minuto_incompativel"
        elif rejeicoes_placar:
            motivo = "placar_incompativel"
        elif rejeicoes_minuto:
            motivo = "minuto_incompativel"
        else:
            motivo = "sem_candidato_compativel"
        melhores_nomes = sorted(
            candidatos_nomes,
            key=lambda candidato: candidato["nota_nomes"],
            reverse=True,
        )[:3]
        return {
            "associacao": None,
            "motivo": motivo,
            "fixtures_validas": fixtures_validas,
            "nomes_compativeis": nomes_compativeis,
            "candidatos_compativeis": 0,
            "rejeicoes_categoria": rejeicoes_categoria,
            "rejeicoes_placar": rejeicoes_placar,
            "rejeicoes_minuto": rejeicoes_minuto,
            "margem_associacao": None,
            "melhores_candidatos_nomes": melhores_nomes,
        }
    melhor = ordenados[0]["item"]
    melhor_nota = ordenados[0]["nota"]
    melhor_orientacao = ordenados[0]["orientacao"]
    segunda_nota = ordenados[1]["nota"] if len(ordenados) > 1 else None
    margem = (
        melhor_nota - segunda_nota if segunda_nota is not None else None
    )
    if margem is not None and margem < float(margem_minima):
        return {
            "associacao": None,
            "motivo": "associacao_ambigua",
            "fixtures_validas": fixtures_validas,
            "nomes_compativeis": nomes_compativeis,
            "candidatos_compativeis": len(ordenados),
            "rejeicoes_categoria": rejeicoes_categoria,
            "rejeicoes_placar": rejeicoes_placar,
            "rejeicoes_minuto": rejeicoes_minuto,
            "margem_associacao": round(margem, 3),
            "melhores_candidatos_nomes": sorted(
                candidatos_nomes,
                key=lambda candidato: candidato["nota_nomes"],
                reverse=True,
            )[:3],
        }

    fixture = melhor.get("fixture", {})
    gols = melhor.get("goals", {})
    placar = [gols.get("home"), gols.get("away")]
    intervalo = ((melhor.get("score") or {}).get("halftime") or {})
    placar_intervalo = [intervalo.get("home"), intervalo.get("away")]
    times = melhor.get("teams", {})
    if melhor_orientacao == "invertida":
        placar.reverse()
        placar_intervalo.reverse()
        times = {
            "home": times.get("away", {}),
            "away": times.get("home", {}),
        }
    associacao = {
        "fixture_id": fixture.get("id"),
        "similaridade": round(melhor_nota, 3),
        "margem_associacao": (
            round(margem, 3) if margem is not None else None
        ),
        "candidatos_compativeis": len(ordenados),
        "status": fixture.get("status", {}),
        "placar": placar,
        "placar_intervalo": (
            placar_intervalo if None not in placar_intervalo else None
        ),
        "times": times,
        "liga": melhor.get("league") or {},
        "eventos": melhor.get("events", []),
        "_estatisticas_embutidas": melhor.get("statistics"),
        "_jogadores_embutidos": melhor.get("players"),
        "_escalacoes_embutidas": melhor.get("lineups"),
        "orientacao": melhor_orientacao,
    }
    return {
        "associacao": associacao,
        "motivo": "associado",
        "fixtures_validas": fixtures_validas,
        "nomes_compativeis": nomes_compativeis,
        "candidatos_compativeis": len(ordenados),
        "rejeicoes_categoria": rejeicoes_categoria,
        "rejeicoes_placar": rejeicoes_placar,
        "rejeicoes_minuto": rejeicoes_minuto,
        "margem_associacao": associacao["margem_associacao"],
        "melhores_candidatos_nomes": sorted(
            candidatos_nomes,
            key=lambda candidato: candidato["nota_nomes"],
            reverse=True,
        )[:3],
    }


def associar_jogo(
    jogo_packball,
    fixtures_api,
    margem_minima=MARGEM_MINIMA_ASSOCIACAO,
):
    return diagnosticar_associacao(
        jogo_packball, fixtures_api, margem_minima
    )["associacao"]
