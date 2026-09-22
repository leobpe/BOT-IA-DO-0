"""Custódia SQLite da fotografia histórica exibida no Telegram.

O hash detecta alteração de conteúdo, mas sozinho não impede que conteúdo e
hash sejam trocados juntos. Estes gatilhos tornam cada fotografia V2, V3 ou
V4 gravável uma única vez e impedem atualização, remoção e substituição.
"""

import re
import sqlite3


VERSAO = "custodia-sqlite-estimativa-historica-v3"
PREFIXO_CHAVE_V2 = "probabilidade_acertos:v2:sinal:"
PREFIXO_CHAVE_V3 = "probabilidade_acertos:v3:sinal:"
PREFIXO_CHAVE = "probabilidade_acertos:v4:sinal:"

GATILHOS_SQL = {
    "trg_probabilidade_acertos_v2_insert_unico": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v2_insert_unico
        BEFORE INSERT ON metadados
        WHEN NEW.chave LIKE '{PREFIXO_CHAVE_V2}%'
          AND EXISTS (
              SELECT 1 FROM metadados WHERE chave=NEW.chave
          )
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel ja foi congelada'
            );
        END
    """,
    "trg_probabilidade_acertos_v2_update_imutavel": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v2_update_imutavel
        BEFORE UPDATE ON metadados
        WHEN OLD.chave LIKE '{PREFIXO_CHAVE_V2}%'
          OR NEW.chave LIKE '{PREFIXO_CHAVE_V2}%'
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel e imutavel'
            );
        END
    """,
    "trg_probabilidade_acertos_v2_delete_imutavel": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v2_delete_imutavel
        BEFORE DELETE ON metadados
        WHEN OLD.chave LIKE '{PREFIXO_CHAVE_V2}%'
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel e imutavel'
            );
        END
    """,
    "trg_probabilidade_acertos_v3_insert_unico": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v3_insert_unico
        BEFORE INSERT ON metadados
        WHEN NEW.chave LIKE '{PREFIXO_CHAVE_V3}%'
          AND EXISTS (
              SELECT 1 FROM metadados WHERE chave=NEW.chave
          )
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel V3 ja foi congelada'
            );
        END
    """,
    "trg_probabilidade_acertos_v3_update_imutavel": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v3_update_imutavel
        BEFORE UPDATE ON metadados
        WHEN OLD.chave LIKE '{PREFIXO_CHAVE_V3}%'
          OR NEW.chave LIKE '{PREFIXO_CHAVE_V3}%'
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel V3 e imutavel'
            );
        END
    """,
    "trg_probabilidade_acertos_v3_delete_imutavel": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v3_delete_imutavel
        BEFORE DELETE ON metadados
        WHEN OLD.chave LIKE '{PREFIXO_CHAVE_V3}%'
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel V3 e imutavel'
            );
        END
    """,
    "trg_probabilidade_acertos_v4_insert_unico": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v4_insert_unico
        BEFORE INSERT ON metadados
        WHEN NEW.chave LIKE '{PREFIXO_CHAVE}%'
          AND EXISTS (
              SELECT 1 FROM metadados WHERE chave=NEW.chave
          )
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel V4 ja foi congelada'
            );
        END
    """,
    "trg_probabilidade_acertos_v4_update_imutavel": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v4_update_imutavel
        BEFORE UPDATE ON metadados
        WHEN OLD.chave LIKE '{PREFIXO_CHAVE}%'
          OR NEW.chave LIKE '{PREFIXO_CHAVE}%'
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel V4 e imutavel'
            );
        END
    """,
    "trg_probabilidade_acertos_v4_delete_imutavel": f"""
        CREATE TRIGGER IF NOT EXISTS
            trg_probabilidade_acertos_v4_delete_imutavel
        BEFORE DELETE ON metadados
        WHEN OLD.chave LIKE '{PREFIXO_CHAVE}%'
        BEGIN
            SELECT RAISE(
                ABORT,
                'estimativa historica executavel V4 e imutavel'
            );
        END
    """,
}

_REQUISITOS = {
    "trg_probabilidade_acertos_v2_insert_unico": (
        "before insert on metadados",
        f"new.chave like '{PREFIXO_CHAVE_V2}%'",
        "exists ( select 1 from metadados where chave=new.chave )",
        "raise( abort",
    ),
    "trg_probabilidade_acertos_v2_update_imutavel": (
        "before update on metadados",
        f"old.chave like '{PREFIXO_CHAVE_V2}%'",
        f"new.chave like '{PREFIXO_CHAVE_V2}%'",
        "raise( abort",
    ),
    "trg_probabilidade_acertos_v2_delete_imutavel": (
        "before delete on metadados",
        f"old.chave like '{PREFIXO_CHAVE_V2}%'",
        "raise( abort",
    ),
    "trg_probabilidade_acertos_v3_insert_unico": (
        "before insert on metadados",
        f"new.chave like '{PREFIXO_CHAVE_V3}%'",
        "exists ( select 1 from metadados where chave=new.chave )",
        "raise( abort",
    ),
    "trg_probabilidade_acertos_v3_update_imutavel": (
        "before update on metadados",
        f"old.chave like '{PREFIXO_CHAVE_V3}%'",
        f"new.chave like '{PREFIXO_CHAVE_V3}%'",
        "raise( abort",
    ),
    "trg_probabilidade_acertos_v3_delete_imutavel": (
        "before delete on metadados",
        f"old.chave like '{PREFIXO_CHAVE_V3}%'",
        "raise( abort",
    ),
    "trg_probabilidade_acertos_v4_insert_unico": (
        "before insert on metadados",
        f"new.chave like '{PREFIXO_CHAVE}%'",
        "exists ( select 1 from metadados where chave=new.chave )",
        "raise( abort",
    ),
    "trg_probabilidade_acertos_v4_update_imutavel": (
        "before update on metadados",
        f"old.chave like '{PREFIXO_CHAVE}%'",
        f"new.chave like '{PREFIXO_CHAVE}%'",
        "raise( abort",
    ),
    "trg_probabilidade_acertos_v4_delete_imutavel": (
        "before delete on metadados",
        f"old.chave like '{PREFIXO_CHAVE}%'",
        "raise( abort",
    ),
}


def _sql_normalizado(valor):
    texto = re.sub(r"\s+", " ", str(valor or "").strip().casefold())
    texto = re.sub(r"\s*=\s*", "=", texto)
    texto = re.sub(r"\s*\(\s*", "( ", texto)
    texto = re.sub(r"\s*\)\s*", " )", texto)
    texto = re.sub(r"\s*,\s*", ",", texto)
    return re.sub(r"\s+", " ", texto).strip()


def instalar_gatilhos(conexao):
    """Instala a proteção dentro da transação de criação do esquema."""
    for ddl in GATILHOS_SQL.values():
        conexao.execute(ddl)


def auditar_gatilhos(conexao):
    """Confere presença e semântica; nunca cria nem corrige estrutura."""
    resumo = {
        "versao": VERSAO,
        "estado": "integra",
        "saudavel": True,
        "esperados": len(GATILHOS_SQL),
        "presentes": 0,
        "ausentes": [],
        "invalidos": [],
        "prefixo_atual": PREFIXO_CHAVE,
        "prefixo_legado_protegido": PREFIXO_CHAVE_V2,
        "prefixos_legados_protegidos": [
            PREFIXO_CHAVE_V2,
            PREFIXO_CHAVE_V3,
        ],
        "gravacao_unica": True,
        "update_bloqueado": True,
        "delete_bloqueado": True,
    }
    try:
        linhas = conexao.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    except (sqlite3.Error, AttributeError) as erro:
        resumo.update({
            "estado": "auditoria_falhou",
            "saudavel": False,
            "erro": type(erro).__name__,
            "gravacao_unica": False,
            "update_bloqueado": False,
            "delete_bloqueado": False,
        })
        return resumo

    encontrados = {
        str(linha[0]): _sql_normalizado(linha[1]) for linha in linhas
        if str(linha[0]) in GATILHOS_SQL
    }
    resumo["presentes"] = len(encontrados)
    resumo["ausentes"] = sorted(set(GATILHOS_SQL) - set(encontrados))
    invalidos = []
    for nome, requisitos in _REQUISITOS.items():
        sql = encontrados.get(nome)
        if sql is None:
            continue
        if any(_sql_normalizado(item) not in sql for item in requisitos):
            invalidos.append(nome)
    resumo["invalidos"] = sorted(invalidos)
    if resumo["ausentes"] or resumo["invalidos"]:
        resumo.update({
            "estado": "inconsistente",
            "saudavel": False,
            "gravacao_unica": (
                "trg_probabilidade_acertos_v4_insert_unico"
                not in resumo["ausentes"] + resumo["invalidos"]
            ),
            "update_bloqueado": (
                "trg_probabilidade_acertos_v4_update_imutavel"
                not in resumo["ausentes"] + resumo["invalidos"]
            ),
            "delete_bloqueado": (
                "trg_probabilidade_acertos_v4_delete_imutavel"
                not in resumo["ausentes"] + resumo["invalidos"]
            ),
        })
    return resumo
