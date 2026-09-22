"""Auditoria fail-closed dos relogios usados pelas coortes prospectivas.

Os sinais ao vivo sao persistidos em horario local sem offset. Os bilhetes
pre-live, por outro lado, usam UTC com offset. Esta auditoria torna essa
diferenca deliberada e detecta uma mudanca de formato antes que uma ancora
passe a selecionar uma janela temporal diferente da declarada.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from validacao_escanteios_ft_asiatico_prospectiva import (
    CHAVE_DEFINICAO as CHAVE_ESCANTEIOS_FT_LEGADO,
    definicao as definicao_escanteios_ft_legado,
)
from validacao_escanteios_ft_asiatico_executavel import (
    CHAVE_DEFINICAO as CHAVE_ESCANTEIOS_FT,
    definicao as definicao_escanteios_ft,
)
from validacao_gol_ft_antecipado_preciso import (
    CHAVE_DEFINICAO as CHAVE_GOL_FT,
    definicao as definicao_gol_ft,
)
from validacao_gol_ht_antecipado_preciso import (
    CHAVE_DEFINICAO as CHAVE_GOL_HT,
    definicao as definicao_gol_ht,
)
from validacao_pre_live_preciso import (
    CHAVE_DEFINICAO as CHAVE_PRE_LIVE,
    VERSAO_ALVO as VERSAO_PRE_LIVE_ALVO,
    definicao as definicao_pre_live,
)
from validacao_quase_candidatos_proximo_gol import (
    CHAVE_DEFINICAO as CHAVE_QUASE_PROXIMO_GOL,
    definicao as definicao_quase_proximo_gol,
)


VERSAO_AUDITORIA = "auditoria-relogios-coortes-v1"
CONTRATO_RELOGIOS_SINAIS = {
    "auditoria": "utc_com_offset",
    "selecao": "relogio_local_naive_igual_ao_criado_em_dos_sinais",
}
COORTES_SINAIS = (
    ("gol_ht_antecipado_preciso", CHAVE_GOL_HT, definicao_gol_ht),
    ("gol_ft_antecipado_preciso", CHAVE_GOL_FT, definicao_gol_ft),
    ("escanteios_ft_asiatico", CHAVE_ESCANTEIOS_FT,
     definicao_escanteios_ft),
    ("escanteios_ft_asiatico_legado_v2", CHAVE_ESCANTEIOS_FT_LEGADO,
     definicao_escanteios_ft_legado),
    ("quase_proximo_gol", CHAVE_QUASE_PROXIMO_GOL,
     definicao_quase_proximo_gol),
)


def _instante(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip()
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _tipo_relogio(valor):
    instante = _instante(valor)
    if instante is None:
        return "invalido"
    if instante.tzinfo is None or instante.utcoffset() is None:
        return "local_naive"
    if instante.utcoffset() == timedelta(0):
        return "utc_com_offset"
    return "com_offset_nao_utc"


def _tabela_existe(conexao, nome):
    return conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)
    ).fetchone() is not None


def _ler_documento(conexao, tabela, chave):
    if not _tabela_existe(conexao, tabela):
        return None, f"tabela_ausente:{tabela}"
    linha = conexao.execute(
        f"SELECT valor FROM {tabela} WHERE chave=?", (chave,)
    ).fetchone()
    if linha is None:
        return None, None
    try:
        documento = json.loads(linha[0])
    except (TypeError, json.JSONDecodeError):
        return None, "metadado_json_invalido"
    if not isinstance(documento, dict):
        return None, "metadado_nao_objeto"
    return documento, None


def _auditar_ancora_sinais(nome, documento, esperada):
    problemas = []
    divergencias = [
        campo for campo, valor in esperada.items()
        if documento.get(campo) != valor
    ]
    if divergencias:
        problemas.append(
            f"{nome}:definicao_divergente:{','.join(sorted(divergencias))}"
        )
    utc_texto = documento.get("registrado_em")
    local_texto = documento.get("registrado_em_relogio_sinais")
    tipo_utc = _tipo_relogio(utc_texto)
    tipo_local = _tipo_relogio(local_texto)
    if tipo_utc != "utc_com_offset":
        problemas.append(f"{nome}:registrado_em_{tipo_utc}")
    if tipo_local != "local_naive":
        problemas.append(
            f"{nome}:registrado_em_relogio_sinais_{tipo_local}"
        )
    if tipo_utc == "utc_com_offset" and tipo_local == "local_naive":
        utc = _instante(utc_texto)
        local = _instante(local_texto)
        local_esperado = utc.astimezone().replace(tzinfo=None)
        if local != local_esperado:
            problemas.append(f"{nome}:relogios_nao_representam_mesmo_instante")
    return problemas, {
        "nome": nome,
        "versao": esperada.get("versao"),
        "ancora_presente": True,
        "registrado_em": utc_texto,
        "registrado_em_relogio_sinais": local_texto,
        "integra": not problemas,
    }


def auditar_relogios_sinais(conexao, limite_amostra=200):
    problemas = []
    coortes = []
    ancoras_ausentes = []
    for nome, chave, carregar_definicao in COORTES_SINAIS:
        esperada = carregar_definicao()
        if esperada.get("relogios") != CONTRATO_RELOGIOS_SINAIS:
            problemas.append(f"{nome}:contrato_relogios_incorreto")
        documento, erro = _ler_documento(conexao, "metadados", chave)
        if erro:
            problemas.append(f"{nome}:{erro}")
            coortes.append({
                "nome": nome, "versao": esperada.get("versao"),
                "ancora_presente": False, "integra": False,
            })
            continue
        if documento is None:
            ancoras_ausentes.append(nome)
            coortes.append({
                "nome": nome, "versao": esperada.get("versao"),
                "ancora_presente": False, "integra": True,
            })
            continue
        falhas, resumo = _auditar_ancora_sinais(
            nome, documento, esperada
        )
        problemas.extend(falhas)
        coortes.append(resumo)

    amostra = []
    if not _tabela_existe(conexao, "sinais"):
        problemas.append("sinais:tabela_ausente")
    else:
        amostra = [
            linha[0] for linha in conexao.execute(
                "SELECT criado_em FROM sinais ORDER BY id DESC LIMIT ?",
                (max(int(limite_amostra), 1),),
            ).fetchall()
        ]
        invalidos = sum(_tipo_relogio(item) == "invalido" for item in amostra)
        com_offset = sum(
            _tipo_relogio(item) in {"utc_com_offset", "com_offset_nao_utc"}
            for item in amostra
        )
        if invalidos:
            problemas.append(f"sinais:criado_em_invalido:{invalidos}")
        if com_offset:
            problemas.append(f"sinais:criado_em_com_offset:{com_offset}")
    return {
        "versao": VERSAO_AUDITORIA,
        "saudavel": not problemas,
        "estado": "integro" if not problemas else "inconsistente",
        "problemas": problemas,
        "coortes": coortes,
        "ancoras_ausentes_antes_da_primeira_inicializacao": ancoras_ausentes,
        "amostra_sinais": len(amostra),
        "contrato_sinais": "horario_local_sem_offset",
        "altera_sinais": False,
    }


def auditar_relogios_pre_live(conexao, limite_amostra=200):
    problemas = []
    esperada = definicao_pre_live()
    documento, erro = _ler_documento(
        conexao, "metadados_pre_live", CHAVE_PRE_LIVE
    )
    ancora_presente = documento is not None
    if erro:
        problemas.append(f"pre_live:{erro}")
    elif documento is not None:
        divergencias = [
            campo for campo, valor in esperada.items()
            if documento.get(campo) != valor
        ]
        if divergencias:
            problemas.append(
                "pre_live:definicao_divergente:"
                + ",".join(sorted(divergencias))
            )
        tipo = _tipo_relogio(documento.get("registrado_em"))
        if tipo != "utc_com_offset":
            problemas.append(f"pre_live:registrado_em_{tipo}")

    amostra = []
    if not _tabela_existe(conexao, "bilhetes_pre_live"):
        problemas.append("pre_live:bilhetes_pre_live_tabela_ausente")
    else:
        amostra = [
            linha[0] for linha in conexao.execute(
                "SELECT criado_em FROM bilhetes_pre_live WHERE versao=? "
                "ORDER BY id DESC LIMIT ?",
                (VERSAO_PRE_LIVE_ALVO, max(int(limite_amostra), 1)),
            ).fetchall()
        ]
        invalidos = sum(_tipo_relogio(item) == "invalido" for item in amostra)
        nao_utc = sum(
            _tipo_relogio(item) != "utc_com_offset" for item in amostra
        )
        if invalidos:
            problemas.append(f"pre_live:criado_em_invalido:{invalidos}")
        if nao_utc - invalidos:
            problemas.append(
                f"pre_live:criado_em_fora_utc:{nao_utc - invalidos}"
            )
    return {
        "versao": VERSAO_AUDITORIA,
        "saudavel": not problemas,
        "estado": "integro" if not problemas else "inconsistente",
        "problemas": problemas,
        "ancora_presente": ancora_presente,
        "amostra_bilhetes": len(amostra),
        "versao_bilhetes": VERSAO_PRE_LIVE_ALVO,
        "contrato_pre_live": "utc_com_offset",
        "altera_bilhetes": False,
    }


def verificar_relogios_coortes(pasta):
    pasta = Path(pasta)
    monitor = pasta / "monitor_packball.db"
    pre_live = pasta / "pre_live.db"
    if not monitor.exists():
        return {
            "versao": VERSAO_AUDITORIA,
            "saudavel": False,
            "estado": "banco_monitor_ausente",
            "problemas": ["monitor_packball.db:ausente"],
        }
    conexao_monitor = conexao_pre_live = None
    try:
        conexao_monitor = sqlite3.connect(
            monitor.resolve().as_uri() + "?mode=ro", uri=True, timeout=10
        )
        resultado_monitor = auditar_relogios_sinais(conexao_monitor)
        if pre_live.exists():
            conexao_pre_live = sqlite3.connect(
                pre_live.resolve().as_uri() + "?mode=ro", uri=True, timeout=10
            )
            resultado_pre_live = auditar_relogios_pre_live(conexao_pre_live)
        else:
            resultado_pre_live = {
                "versao": VERSAO_AUDITORIA,
                "saudavel": True,
                "estado": "banco_ausente_antes_da_primeira_execucao",
                "problemas": [],
                "ancora_presente": False,
                "amostra_bilhetes": 0,
                "contrato_pre_live": "utc_com_offset",
                "altera_bilhetes": False,
            }
    except (OSError, sqlite3.Error) as erro:
        return {
            "versao": VERSAO_AUDITORIA,
            "saudavel": False,
            "estado": "auditoria_indisponivel",
            "problemas": [type(erro).__name__],
        }
    finally:
        if conexao_monitor is not None:
            conexao_monitor.close()
        if conexao_pre_live is not None:
            conexao_pre_live.close()
    return {
        "versao": VERSAO_AUDITORIA,
        "saudavel": bool(
            resultado_monitor["saudavel"] and resultado_pre_live["saudavel"]
        ),
        "estado": (
            "integro"
            if resultado_monitor["saudavel"] and resultado_pre_live["saudavel"]
            else "inconsistente"
        ),
        "problemas": [
            *resultado_monitor.get("problemas", []),
            *resultado_pre_live.get("problemas", []),
        ],
        "monitor": resultado_monitor,
        "pre_live": resultado_pre_live,
        "somente_leitura": True,
    }


if __name__ == "__main__":
    resultado = verificar_relogios_coortes(Path(__file__).parent)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado.get("saudavel") else 1)
