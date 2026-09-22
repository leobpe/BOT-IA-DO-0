"""Épocas auditáveis da carteira de sinais ao vivo.

O objetivo é separar desempenho por política realmente carregada. Somente
chaves explicitamente seguras entram no documento; credenciais, destinos e
identificadores de usuários nunca participam do fingerprint nem do SQLite.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from mercados import mercados_calibrados_operacionais
from versoes_gol_ft_reforcado import versao_regra_operacional


VERSAO = "carteira-operacional-epocas-v1"
CHAVE_ATUAL = "estado_carteira_operacional:atual"
PREFIXO_EPOCA = "carteira_operacional:epoca:"

CHAVES_CONFIGURACAO_SEGURAS = (
    "SINAIS_TESTE_ATIVO",
    "PONTUACAO_MINIMA_SINAL_TESTE",
    "QUALIDADE_MINIMA_SINAL_TESTE",
    "LIMITE_DIARIO_SINAIS_TESTE",
    "LIMITE_GLOBAL_SINAIS_TESTE",
    "ODD_MINIMA_SINAL",
    "ODD_MAXIMA_SINAL",
    "LIMITE_DIARIO_SINAIS",
    "LIMITE_EXPOSICAO_DIARIA",
    "LIMITE_REDS_CONSECUTIVOS_OFICIAIS",
    "LIMITE_PERDA_DIARIA_OFICIAL",
    "ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS",
    "ESCANTEIOS_PRIORIDADE_CANAL_ATIVA",
    "ESCANTEIOS_FT_ASIATICO_MULTIPLOS_GRUPO_ATIVO",
    "GOL_FT_REFORCADO_ATIVO",
    "GOL_FT_REFORCADO_OFICIAL_ATIVO",
    "GOL_HT_PRINCIPAL_OFICIAL_ATIVO",
    "PROXIMO_GOL_FILTRO_PRECISO_ATIVO",
    "PROXIMO_GOL_BALANCEADO_SOMBRA_ATIVO",
    "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO",
    "PONTUACAO_MINIMA_PROXIMO_GOL_BALANCEADO_TESTE",
    "ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO",
    "GOLS_ANTECIPADOS_GRUPO_ATIVO",
    "FILTRO_GOL_FT_ANTECIPADO_PRECISO_ATIVO",
    "GOL_HT_00_MIN20_GRUPO_ATIVO",
    "GOLS_CAPACIDADE_CONTEXTUAL_V2_HT_GRUPO_ATIVO",
    "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO",
    "GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO",
    "GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO",
    "GOL_HT_SEM_TENDENCIA_PACKBALL_GRUPO_ATIVO",
    "GOL_HT_HISTORICO_INSUFICIENTE_COM_SOT_GRUPO_ATIVO",
    "GOL_2T_POS_HT_RED_GRUPO_ATIVO",
    "GOL_FT_TENDENCIA_MAIS_UM_GRUPO_ATIVO",
    "TOP_CRITERIOS_GOLS_GRUPO_ATIVO",
    "API_LIVE_TEMPORAL_GRUPO_ATIVO",
    "AVISO_AGUARDAR_ODD_ATIVO",
    "AVISO_AGUARDAR_ODD_MERCADOS",
    "AVISO_AGUARDAR_ODD_PISO",
    "AVISO_AGUARDAR_ODD_ALVO",
    "AVISO_AGUARDAR_ODD_NOTA_MINIMA",
    "AVISO_AGUARDAR_ODD_QUALIDADE_MINIMA",
    "BETSAPI_APLICACAO_SINAIS_ATIVA",
    "THESTATSAPI_APLICACAO_SINAIS_ATIVA",
    "THE_ODDS_API_ATIVA",
)

COMPONENTES_DECISAO = (
    "motor_sinais.py",
    "politica_gol_ft_reforcado.py",
    "politica_gol_ht_protegido.py",
    "politica_gol_ht.py",
    "politica_proximo_gol_preciso.py",
    "proximo_gol_balanceado_sombra.py",
    "validacao_gol_ft_reforcado_sombra.py",
    "validacao_gol_ht_protegido_sombra.py",
    "politica_escanteios_ft.py",
    "gols_antecipados.py",
    "filtro_gol_ft_antecipado_preciso.py",
    "controle_gols_antecipados.py",
    "avaliacao_edge_escanteios_asiaticos.py",
    "avaliacao_probabilidade_sem_vig.py",
    "avaliacao_portfolio_edge.py",
    "telegram_alertas.py",
    "acompanhamento_odd.py",
    "versoes_regras.py",
    "versoes_challengers_preciso.py",
    "versoes_proximo_gol_balanceado.py",
    "versoes_gol_ft_reforcado.py",
    "versoes_gol_ht_protegido.py",
)


def _json_canonico(valor):
    return json.dumps(
        valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _hash_arquivo(caminho):
    try:
        return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
    except OSError:
        return None


def descrever_carteira_operacional(
    env, pasta=None, *, hashes_componentes=None,
):
    """Constrói descrição determinística sem material confidencial."""
    pasta = Path(pasta or Path(__file__).parent)
    configuracao = {
        chave: (
            str(env[chave]).strip() if chave in env else None
        )
        for chave in CHAVES_CONFIGURACAO_SEGURAS
    }
    mercados = tuple(mercados_calibrados_operacionais(env))
    versoes = {
        mercado: versao_regra_operacional(mercado)
        for mercado in mercados
    }
    if hashes_componentes is None:
        hashes_componentes = {
            nome: _hash_arquivo(pasta / nome)
            for nome in COMPONENTES_DECISAO
        }
    else:
        hashes_componentes = dict(hashes_componentes)
    corpo = {
        "versao": VERSAO,
        "configuracao": configuracao,
        "mercados_operacionais": list(mercados),
        "versoes_por_mercado": versoes,
        "componentes_sha256": hashes_componentes,
    }
    corpo["fingerprint"] = hashlib.sha256(
        _json_canonico(corpo).encode("utf-8")
    ).hexdigest()
    return corpo


def carregar_carteira_operacional_atual(conexao):
    try:
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (CHAVE_ATUAL,)
        ).fetchone()
    except sqlite3.Error:
        return None
    if linha is None:
        return None
    try:
        dados = json.loads(linha["valor"] if hasattr(linha, "keys") else linha[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return dados if isinstance(dados, dict) else None


def registrar_carteira_operacional(
    conexao, env, pasta=None, *, agora=None, hashes_componentes=None,
):
    """Registra nova época somente quando a política efetiva muda."""
    descricao = descrever_carteira_operacional(
        env, pasta, hashes_componentes=hashes_componentes
    )
    anterior = carregar_carteira_operacional_atual(conexao)
    if (
        anterior
        and anterior.get("fingerprint") == descricao["fingerprint"]
    ):
        return {**anterior, "nova_epoca": False}

    instante = (agora or datetime.now()).replace(microsecond=0).isoformat()
    chave_epoca = (
        f"{PREFIXO_EPOCA}{instante}:"
        f"{descricao['fingerprint'][:16]}:{uuid4().hex[:8]}"
    )
    epoca = {
        **descricao,
        "ativada_em": instante,
        "chave_epoca": chave_epoca,
        "fingerprint_anterior": (
            anterior.get("fingerprint") if anterior else None
        ),
    }
    serializado = _json_canonico(epoca)
    with conexao:
        conexao.execute(
            "INSERT INTO metadados(chave, valor) VALUES (?, ?)",
            (chave_epoca, serializado),
        )
        conexao.execute(
            "INSERT OR REPLACE INTO metadados(chave, valor) VALUES (?, ?)",
            (CHAVE_ATUAL, serializado),
        )
    return {**epoca, "nova_epoca": True}


def auditar_carteira_operacional(
    conexao, env, pasta=None, *, hashes_componentes=None,
):
    """Compara estado persistido e política que seria carregada agora."""
    atual = carregar_carteira_operacional_atual(conexao)
    esperada = descrever_carteira_operacional(
        env, pasta, hashes_componentes=hashes_componentes
    )
    if atual is None:
        return {
            "saudavel": True,
            "estado": "aguardando_primeira_inicializacao",
            "fingerprint_esperado": esperada["fingerprint"],
        }
    chave_epoca = atual.get("chave_epoca")
    try:
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave_epoca,)
        ).fetchone()
    except sqlite3.Error:
        linha = None
    if linha is None:
        return {
            "saudavel": False,
            "estado": "epoca_referenciada_ausente",
            "fingerprint_atual": atual.get("fingerprint"),
        }
    mesma = atual.get("fingerprint") == esperada["fingerprint"]
    return {
        "saudavel": True,
        "estado": "atual" if mesma else "nova_epoca_pendente",
        "fingerprint_atual": atual.get("fingerprint"),
        "fingerprint_esperado": esperada["fingerprint"],
        "ativada_em": atual.get("ativada_em"),
        "chave_epoca": chave_epoca,
        "nova_epoca_necessaria": not mesma,
    }
