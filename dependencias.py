import hashlib
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


PYTHON_MINIMO = (3, 11)
PADRAO_DEPENDENCIA = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s]+)$"
)


def ler_lock_dependencias(caminho):
    caminho = Path(caminho)
    try:
        conteudo = caminho.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {
            "valido": False,
            "motivo": "lock_dependencias_ausente",
            "dependencias": {},
            "sha256": None,
        }
    dependencias = {}
    for numero, linha_original in enumerate(conteudo.splitlines(), start=1):
        linha = linha_original.strip()
        if not linha or linha.startswith("#"):
            continue
        correspondencia = PADRAO_DEPENDENCIA.fullmatch(linha)
        if correspondencia is None:
            return {
                "valido": False,
                "motivo": "lock_dependencias_invalido",
                "linha_invalida": numero,
                "dependencias": {},
                "sha256": None,
            }
        nome, versao = correspondencia.groups()
        chave = nome.lower().replace("_", "-")
        if chave in dependencias:
            return {
                "valido": False,
                "motivo": "lock_dependencias_duplicado",
                "linha_invalida": numero,
                "dependencias": {},
                "sha256": None,
            }
        dependencias[chave] = {"nome": nome, "versao": versao}
    if not dependencias:
        return {
            "valido": False,
            "motivo": "lock_dependencias_vazio",
            "dependencias": {},
            "sha256": None,
        }
    return {
        "valido": True,
        "motivo": None,
        "dependencias": dependencias,
        "sha256": hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
    }


def verificar_dependencias(
    caminho_lock,
    versoes_instaladas=None,
    versao_python=None,
):
    lock = ler_lock_dependencias(caminho_lock)
    versao_python = tuple(
        versao_python
        if versao_python is not None
        else sys.version_info[:3]
    )
    python_compativel = versao_python[:2] >= PYTHON_MINIMO
    if not lock["valido"]:
        return {
            "saudavel": False,
            "estado": "inconsistente",
            "python": ".".join(map(str, versao_python)),
            "python_minimo": ".".join(map(str, PYTHON_MINIMO)),
            "python_compativel": python_compativel,
            "ausentes": [],
            "divergentes": [],
            "total_lock": 0,
            "lock_sha256": None,
            **{chave: valor for chave, valor in lock.items()
               if chave in ("motivo", "linha_invalida")},
        }
    instaladas = {
        str(nome).lower().replace("_", "-"): str(valor)
        for nome, valor in (versoes_instaladas or {}).items()
    } if versoes_instaladas is not None else None
    ausentes = []
    divergentes = []
    for chave, esperado in lock["dependencias"].items():
        if instaladas is not None:
            encontrada = instaladas.get(chave)
        else:
            try:
                encontrada = version(esperado["nome"])
            except PackageNotFoundError:
                encontrada = None
        if encontrada is None:
            ausentes.append(esperado["nome"])
        elif encontrada != esperado["versao"]:
            divergentes.append({
                "nome": esperado["nome"],
                "esperada": esperado["versao"],
                "instalada": encontrada,
            })
    saudavel = python_compativel and not ausentes and not divergentes
    motivo = None
    if not python_compativel:
        motivo = "python_incompativel"
    elif ausentes:
        motivo = "dependencias_ausentes"
    elif divergentes:
        motivo = "versoes_dependencias_divergentes"
    return {
        "saudavel": saudavel,
        "estado": "reproduzivel" if saudavel else "inconsistente",
        "motivo": motivo,
        "python": ".".join(map(str, versao_python)),
        "python_minimo": ".".join(map(str, PYTHON_MINIMO)),
        "python_compativel": python_compativel,
        "ausentes": sorted(ausentes),
        "divergentes": sorted(divergentes, key=lambda item: item["nome"]),
        "total_lock": len(lock["dependencias"]),
        "lock_sha256": lock["sha256"],
    }
