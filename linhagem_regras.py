import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from configuracao import obter_limites_risco
from versoes_regras import (
    VERSAO_ESCANTEIOS_FT_ASIATICO,
    VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
    VERSAO_PROXIMO_ESCANTEIO_MAX_86,
)
from versoes_operacionais import VERSAO_GOL_HT_MAX_28
from versoes_challengers_global import (
    VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75,
    VERSAO_PROXIMO_GOL_ODD_166_MAX_75,
)
from versoes_challengers_preciso import VERSAO_PROXIMO_GOL_FILTRO_PRECISO
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)
from versoes_gol_ft_reforcado import VERSAO_GOL_FT_REFORCADO
from versoes_gol_ht_protegido import VERSAO_GOL_HT_PROTEGIDO


ARQUIVOS_LOGICA_REGRAS = (
    "motor_sinais.py",
    "normalizador_odds.py",
    "movimento_odds.py",
    "qualidade_dados.py",
    "evolucao.py",
)
CHAVE_PREFIXO = "linhagem_regra:"
CHAVE_ANCORA_PREFIXO = "linhagem_regra_inicializada:"
CHAVE_SINAIS_PREFIXO = "linhagem_sinais_iniciada:"


def _hash_arquivo(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def calcular_linhagem_regra(pasta, regra_versao, versao_features):
    pasta = Path(pasta)
    limites = obter_limites_risco()
    arquivos_logica = list(ARQUIVOS_LOGICA_REGRAS)
    if regra_versao in {
        VERSAO_ESCANTEIOS_FT_ASIATICO,
        VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
        VERSAO_PROXIMO_ESCANTEIO_MAX_86,
    }:
        arquivos_logica.extend((
            "politica_escanteios_ft.py",
            "versoes_regras.py",
        ))
    if regra_versao == VERSAO_GOL_HT_MAX_28:
        arquivos_logica.extend((
            "politica_gol_ht.py",
            "versoes_operacionais.py",
        ))
    if regra_versao == VERSAO_PROXIMO_GOL_ODD_166_MAX_75:
        arquivos_logica.extend((
            "politica_proximo_gol.py",
            "versoes_challengers.py",
        ))
    if regra_versao == VERSAO_PROXIMO_GOL_FAIXA_GLOBAL_MAX_75:
        arquivos_logica.extend((
            "politica_proximo_gol_faixa_global.py",
            "versoes_challengers_global.py",
        ))
    if regra_versao == VERSAO_PROXIMO_GOL_FILTRO_PRECISO:
        arquivos_logica.extend((
            "politica_proximo_gol_preciso.py",
            "versoes_challengers_preciso.py",
        ))
    if regra_versao == VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA:
        arquivos_logica.extend((
            "politica_proximo_gol_preciso.py",
            "proximo_gol_balanceado_sombra.py",
            "versoes_challengers_preciso.py",
            "versoes_proximo_gol_balanceado.py",
        ))
    if regra_versao == VERSAO_GOL_FT_REFORCADO:
        arquivos_logica.extend((
            "politica_gol_ft_reforcado.py",
            "versoes_gol_ft_reforcado.py",
        ))
    if regra_versao == VERSAO_GOL_HT_PROTEGIDO:
        arquivos_logica.extend((
            "politica_gol_ht.py",
            "politica_gol_ht_protegido.py",
            "versoes_operacionais.py",
            "versoes_gol_ht_protegido.py",
        ))
    componentes = {
        "regra_versao": str(regra_versao),
        "versao_features": str(versao_features),
        "arquivos": {
            nome: _hash_arquivo(pasta / nome)
            for nome in arquivos_logica
        },
        "populacao_elegivel": {
            "odd_minima": float(limites.odd_minima),
            "odd_maxima": float(limites.odd_maxima),
        },
    }
    canonico = json.dumps(
        componentes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "fingerprint": hashlib.sha256(canonico.encode("utf-8")).hexdigest(),
        "componentes": componentes,
    }


def _validar_registro(registro):
    if not isinstance(registro, dict):
        return False
    fingerprint = registro.get("fingerprint")
    if not bool(
        isinstance(fingerprint, str)
        and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        and isinstance(registro.get("componentes"), dict)
        and isinstance(registro.get("registrado_em"), str)
        and registro.get("origem") in ("nova", "adocao_legado")
    ):
        return False
    canonico = json.dumps(
        registro["componentes"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest() == fingerprint


def auditar_linhagem_regra(
    conexao, pasta, regra_versao, versao_features
):
    calculada = calcular_linhagem_regra(
        pasta, regra_versao, versao_features
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (f"{CHAVE_PREFIXO}{regra_versao}",),
    ).fetchone()
    ancora_linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (f"{CHAVE_ANCORA_PREFIXO}{regra_versao}",),
    ).fetchone()
    if linha is None:
        if ancora_linha is not None:
            return {
                "saudavel": False,
                "estado": "vinculo_ausente_apos_inicializacao",
                "regra_versao": regra_versao,
                "fingerprint_atual": calculada["fingerprint"],
                "ancora_presente": True,
            }
        return {
            "saudavel": False,
            "estado": "nao_registrada",
            "regra_versao": regra_versao,
            "fingerprint_atual": calculada["fingerprint"],
            "ancora_presente": False,
        }
    try:
        registro = json.loads(linha[0])
    except (TypeError, json.JSONDecodeError):
        registro = None
    if not _validar_registro(registro):
        return {
            "saudavel": False,
            "estado": "registro_invalido",
            "regra_versao": regra_versao,
            "fingerprint_atual": calculada["fingerprint"],
        }
    ancora = None
    if ancora_linha is not None:
        try:
            ancora = json.loads(ancora_linha[0])
        except (TypeError, json.JSONDecodeError):
            ancora = None
        if not (
            isinstance(ancora, dict)
            and ancora.get("fingerprint") == registro["fingerprint"]
            and isinstance(ancora.get("inicializado_em"), str)
        ):
            return {
                "saudavel": False,
                "estado": "ancora_invalida",
                "regra_versao": regra_versao,
                "fingerprint_atual": calculada["fingerprint"],
                "fingerprint_registrado": registro["fingerprint"],
                "ancora_presente": True,
            }
    coerente = registro["fingerprint"] == calculada["fingerprint"]
    divergentes = []
    registrados = registro["componentes"]
    atuais = calculada["componentes"]
    for nome in sorted(
        set((registrados.get("arquivos") or {}).keys())
        | set((atuais.get("arquivos") or {}).keys())
    ):
        if (
            (registrados.get("arquivos") or {}).get(nome)
            != (atuais.get("arquivos") or {}).get(nome)
        ):
            divergentes.append(f"arquivo:{nome}")
    if registrados.get("versao_features") != atuais.get("versao_features"):
        divergentes.append("versao_features")
    for campo in ("odd_minima", "odd_maxima"):
        if (
            (registrados.get("populacao_elegivel") or {}).get(campo)
            != (atuais.get("populacao_elegivel") or {}).get(campo)
        ):
            divergentes.append(f"populacao_elegivel:{campo}")
    return {
        "saudavel": coerente,
        "estado": (
            "vinculada" if coerente and ancora is not None
            else "vinculada_sem_ancora" if coerente
            else "fingerprint_divergente"
        ),
        "regra_versao": regra_versao,
        "fingerprint_registrado": registro["fingerprint"],
        "fingerprint_atual": calculada["fingerprint"],
        "origem": registro["origem"],
        "registrado_em": registro["registrado_em"],
        "sinais_existentes_na_adocao": registro.get(
            "sinais_existentes_na_adocao", 0
        ),
        "componentes_divergentes": divergentes,
        "ancora_presente": ancora is not None,
    }


def _gravar_ancora(conexao, regra_versao, fingerprint):
    agora = datetime.now().replace(microsecond=0).isoformat()
    conexao.execute(
        "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
        (
            f"{CHAVE_ANCORA_PREFIXO}{regra_versao}",
            json.dumps({
                "fingerprint": fingerprint,
                "inicializado_em": agora,
            }, sort_keys=True),
        ),
    )


def fingerprint_vinculado_no_banco(conexao, regra_versao):
    """Retorna somente fingerprint com vínculo e âncora internamente coerentes."""
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (f"{CHAVE_PREFIXO}{regra_versao}",),
    ).fetchone()
    ancora_linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (f"{CHAVE_ANCORA_PREFIXO}{regra_versao}",),
    ).fetchone()
    if linha is None or ancora_linha is None:
        return None
    try:
        registro = json.loads(linha[0])
        ancora = json.loads(ancora_linha[0])
    except (TypeError, json.JSONDecodeError):
        return None
    if not _validar_registro(registro) or not isinstance(ancora, dict):
        return None
    if ancora.get("fingerprint") != registro["fingerprint"]:
        return None
    return registro["fingerprint"]


def resumir_cobertura_linhagem_sinais(conexao, regra_versao):
    fingerprint = fingerprint_vinculado_no_banco(conexao, regra_versao)
    linha_registro = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (f"{CHAVE_PREFIXO}{regra_versao}",),
    ).fetchone()
    if fingerprint is None or linha_registro is None:
        return {
            "saudavel": False,
            "motivo": "linhagem_regra_indisponivel",
            "total": 0,
            "vinculados": 0,
            "legado_sem_fingerprint": 0,
            "divergentes": 0,
            "novos_sem_fingerprint": 0,
        }
    registro = json.loads(linha_registro[0])
    inicio_linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (f"{CHAVE_SINAIS_PREFIXO}{regra_versao}",),
    ).fetchone()
    inicio = None
    if inicio_linha is not None:
        try:
            inicio_registro = json.loads(inicio_linha[0])
        except (TypeError, json.JSONDecodeError):
            inicio_registro = None
        if not (
            isinstance(inicio_registro, dict)
            and inicio_registro.get("fingerprint") == fingerprint
            and isinstance(inicio_registro.get("iniciado_em"), str)
        ):
            return {
                "saudavel": False,
                "motivo": "marco_linhagem_sinais_invalido",
                "total": 0,
                "vinculados": 0,
                "legado_sem_fingerprint": 0,
                "divergentes": 0,
                "novos_sem_fingerprint": 0,
                "marco_presente": True,
            }
        inicio = inicio_registro["iniciado_em"]
    inicio_comparacao = inicio or "9999-12-31T23:59:59"
    resumo = conexao.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN regra_fingerprint=? THEN 1 ELSE 0 END)
                   AS vinculados,
               SUM(CASE WHEN regra_fingerprint IS NULL
                             AND datetime(criado_em) < datetime(?)
                        THEN 1 ELSE 0 END) AS legado_sem_fingerprint,
               SUM(CASE WHEN regra_fingerprint IS NOT NULL
                             AND regra_fingerprint<>?
                        THEN 1 ELSE 0 END) AS divergentes,
               SUM(CASE WHEN regra_fingerprint IS NULL
                             AND datetime(criado_em) >= datetime(?)
                        THEN 1 ELSE 0 END) AS novos_sem_fingerprint
        FROM sinais WHERE regra_versao=?
        """,
        (
            fingerprint,
            inicio_comparacao,
            fingerprint,
            inicio_comparacao,
            regra_versao,
        ),
    ).fetchone()
    dados = {chave: int(resumo[indice] or 0) for indice, chave in enumerate((
        "total", "vinculados", "legado_sem_fingerprint",
        "divergentes", "novos_sem_fingerprint",
    ))}
    return {
        "saudavel": not (
            dados["divergentes"] or dados["novos_sem_fingerprint"]
        ),
        "motivo": None if not (
            dados["divergentes"] or dados["novos_sem_fingerprint"]
        ) else "sinais_sem_linhagem_valida",
        "fingerprint": fingerprint,
        "marco_presente": inicio is not None,
        "iniciado_em": inicio,
        **dados,
    }


def registrar_inicio_linhagem_sinais(conexao, regra_versao, fingerprint):
    chave = f"{CHAVE_SINAIS_PREFIXO}{regra_versao}"
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        cobertura = resumir_cobertura_linhagem_sinais(
            conexao, regra_versao
        )
        if not cobertura["saudavel"]:
            raise RuntimeError("Marco da linhagem por sinal está inconsistente.")
        return cobertura
    if fingerprint_vinculado_no_banco(conexao, regra_versao) != fingerprint:
        raise RuntimeError("Fingerprint sem vínculo válido para iniciar sinais.")
    with conexao:
        conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                chave,
                json.dumps({
                    "fingerprint": fingerprint,
                    "iniciado_em": datetime.now().replace(
                        microsecond=0
                    ).isoformat(),
                }, sort_keys=True),
            ),
        )
    return resumir_cobertura_linhagem_sinais(conexao, regra_versao)


def registrar_ou_validar_linhagem_regra(
    conexao, pasta, regra_versao, versao_features
):
    auditoria = auditar_linhagem_regra(
        conexao, pasta, regra_versao, versao_features
    )
    if auditoria["estado"] == "nao_registrada":
        calculada = calcular_linhagem_regra(
            pasta, regra_versao, versao_features
        )
        sinais_existentes = int(conexao.execute(
            "SELECT COUNT(*) FROM sinais WHERE regra_versao=?",
            (regra_versao,),
        ).fetchone()[0])
        registro = {
            **calculada,
            "registrado_em": datetime.now().replace(
                microsecond=0
            ).isoformat(),
            "origem": "adocao_legado" if sinais_existentes else "nova",
            "sinais_existentes_na_adocao": sinais_existentes,
        }
        with conexao:
            conexao.execute(
                "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
                (
                    f"{CHAVE_PREFIXO}{regra_versao}",
                    json.dumps(
                        registro, ensure_ascii=False, sort_keys=True
                    ),
                ),
            )
            _gravar_ancora(
                conexao, regra_versao, calculada["fingerprint"]
            )
        return auditar_linhagem_regra(
            conexao, pasta, regra_versao, versao_features
        )
    if auditoria["estado"] == "vinculada_sem_ancora":
        with conexao:
            _gravar_ancora(
                conexao, regra_versao, auditoria["fingerprint_atual"]
            )
        return auditar_linhagem_regra(
            conexao, pasta, regra_versao, versao_features
        )
    if not auditoria["saudavel"]:
        raise RuntimeError(
            "A lógica ou a população elegível mudou sem alterar "
            f"VERSAO_REGRAS={regra_versao}. Crie uma nova versão para "
            "não misturar a amostra histórica."
        )
    return auditoria
