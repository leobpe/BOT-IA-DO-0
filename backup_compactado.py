"""Formato reversível para backups SQLite compactados.

Esta camada é deliberadamente independente da rotação em produção. Ela só
considera um arquivo utilizável depois de validar o checksum do contêiner,
descompactar integralmente e repetir a verificação profissional do SQLite.
"""

import gzip
import hashlib
import json
import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from backup_banco import (
    calcular_sha256,
    caminho_manifesto,
    verificar_backup,
    verificar_backup_legado,
)


VERSAO_BACKUP_COMPACTADO = "sqlite-gzip-verificado-v1"


def _remover_original_apos_roundtrip(
    origem, pausas=(0.1, 0.25, 0.5, 1.0), dormir=time.sleep
):
    """Remove o SQLite somente após verificação, tolerando locks transitórios.

    No Windows, antivírus e indexadores podem manter o arquivo recém-lido
    aberto por alguns instantes. Se o bloqueio persistir, os dois formatos
    válidos são preservados para reconciliação posterior.
    """
    origem = Path(origem)
    erro = None
    for tentativa in range(len(pausas) + 1):
        try:
            origem.unlink()
            break
        except FileNotFoundError:
            break
        except OSError as atual:
            erro = atual
            if tentativa >= len(pausas):
                return {
                    "original_removido": False,
                    "original_preservado": origem.exists(),
                    "limpeza_pendente": True,
                    "erro_limpeza": type(atual).__name__,
                }
            dormir(float(pausas[tentativa]))
    manifesto = caminho_manifesto(origem)
    manifesto_removido = False
    try:
        manifesto.unlink(missing_ok=True)
        manifesto_removido = not manifesto.exists()
    except OSError as atual:
        erro = atual
    return {
        "original_removido": not origem.exists(),
        "original_preservado": origem.exists(),
        "manifesto_original_removido": manifesto_removido,
        "limpeza_pendente": bool(origem.exists() or manifesto.exists()),
        "erro_limpeza": type(erro).__name__ if erro else None,
    }


def caminho_manifesto_compactado(caminho):
    return Path(f"{Path(caminho)}.manifest.json")


def _gravar_json_atomico(caminho, dados):
    caminho = Path(caminho)
    temporario = caminho.with_name(
        f".{caminho.name}.{uuid4().hex}.tmp"
    )
    try:
        temporario.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)


def _sha256_e_tamanho_descompactando(origem, destino):
    resumo = hashlib.sha256()
    tamanho = 0
    with gzip.open(origem, "rb") as entrada, Path(destino).open("wb") as saida:
        while True:
            bloco = entrada.read(1024 * 1024)
            if not bloco:
                break
            saida.write(bloco)
            resumo.update(bloco)
            tamanho += len(bloco)
        saida.flush()
        os.fsync(saida.fileno())
    return resumo.hexdigest(), tamanho


def _carregar_manifesto(caminho):
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "manifesto_ausente"
    except (OSError, json.JSONDecodeError, TypeError):
        return None, "manifesto_invalido"
    if not isinstance(dados, dict):
        return None, "manifesto_invalido"
    return dados, None


def compactar_backup_verificado(
    caminho_backup, destino=None, agora=None, remover_original=False
):
    """Compacta apenas um backup já validado e confirma o round-trip.

    ``remover_original`` permanece falso por padrão. Quando verdadeiro, o
    original só é removido depois que o arquivo compactado passou por checksum,
    descompactação e nova verificação SQLite.
    """
    origem = Path(caminho_backup)
    agora = (agora or datetime.now()).replace(microsecond=0)
    destino = Path(destino or f"{origem}.gz")
    manifesto_destino = caminho_manifesto_compactado(destino)
    if not origem.is_file():
        return {
            "saudavel": False,
            "estado": "origem_ausente",
            "criado": False,
            "caminho": str(destino),
        }
    verificacao_origem = verificar_backup(origem)
    modo_verificacao = "profissional_atual"
    if (
        not verificacao_origem.get("valido")
        and verificacao_origem.get("motivo") in {
            "esquema_ou_relacoes_incompativeis",
            "modelos_sombra_incompativeis",
        }
    ):
        verificacao_legada = verificar_backup_legado(origem)
        if verificacao_legada.get("valido"):
            verificacao_origem = verificacao_legada
            modo_verificacao = "integridade_legada"
    if not verificacao_origem.get("valido"):
        return {
            "saudavel": False,
            "estado": "origem_invalida",
            "motivo": verificacao_origem.get("motivo"),
            "criado": False,
            "caminho": str(destino),
        }
    if destino.exists() or manifesto_destino.exists():
        existente = verificar_backup_compactado(destino)
        mesmo_conteudo = (
            existente.get("saudavel")
            and existente.get("checksum_sqlite")
            == verificacao_origem.get("checksum_sha256")
        )
        if mesmo_conteudo:
            limpeza = {
                "original_removido": False,
                "original_preservado": origem.exists(),
                "limpeza_pendente": False,
                "erro_limpeza": None,
            }
            if remover_original:
                limpeza = _remover_original_apos_roundtrip(origem)
            return {
                **existente,
                "estado": (
                    "compactado_existente_limpeza_pendente"
                    if limpeza.get("limpeza_pendente")
                    else "compactado_existente_confirmado"
                ),
                "criado": False,
                **limpeza,
            }
        return {
            "saudavel": False,
            "estado": "destino_existente_incompativel",
            "criado": False,
            "caminho": str(destino),
        }

    destino.parent.mkdir(parents=True, exist_ok=True)
    identificador = uuid4().hex
    arquivo_temporario = destino.with_name(
        f".{destino.name}.{identificador}.tmp"
    )
    manifesto_temporario = manifesto_destino.with_name(
        f".{manifesto_destino.name}.{identificador}.tmp"
    )
    instalado = False
    try:
        with origem.open("rb") as entrada, gzip.open(
            arquivo_temporario, "wb", compresslevel=1
        ) as saida:
            shutil.copyfileobj(entrada, saida, 1024 * 1024)
        with arquivo_temporario.open("rb+") as arquivo:
            arquivo.flush()
            os.fsync(arquivo.fileno())
        manifesto_sqlite, erro_manifesto = _carregar_manifesto(
            caminho_manifesto(origem)
        )
        if erro_manifesto:
            raise RuntimeError(erro_manifesto)
        manifesto = {
            "versao": VERSAO_BACKUP_COMPACTADO,
            "arquivo": destino.name,
            "origem": origem.name,
            "criado_em": agora.isoformat(),
            "compressao": "gzip-1",
            "tamanho_compactado_bytes": arquivo_temporario.stat().st_size,
            "tamanho_sqlite_bytes": origem.stat().st_size,
            "sha256_compactado": calcular_sha256(arquivo_temporario),
            "sha256_sqlite": verificacao_origem["checksum_sha256"],
            "modo_verificacao_sqlite": modo_verificacao,
            "manifesto_sqlite": manifesto_sqlite,
        }
        # Metadados de retenção pertencem ao ponto de recuperação, não ao
        # formato físico. Mantê-los no topo evita que uma compactação torne
        # removível um backup que havia sido protegido explicitamente.
        for chave in ("protegido_retencao", "motivo_protecao"):
            if chave in manifesto_sqlite:
                manifesto[chave] = manifesto_sqlite[chave]
        manifesto_temporario.write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        arquivo_temporario.replace(destino)
        manifesto_temporario.replace(manifesto_destino)
        instalado = True
        verificacao = verificar_backup_compactado(destino)
        if not verificacao.get("saudavel"):
            raise RuntimeError(
                "compactado_nao_passou_round_trip:"
                f"{verificacao.get('motivo')}"
            )
        limpeza = {
            "original_removido": False,
            "original_preservado": origem.exists(),
            "limpeza_pendente": False,
            "erro_limpeza": None,
        }
        if remover_original:
            limpeza = _remover_original_apos_roundtrip(origem)
        return {
            **verificacao,
            "estado": (
                "compactado_verificado_limpeza_pendente"
                if limpeza.get("limpeza_pendente")
                else "compactado_e_verificado"
            ),
            "criado": True,
            **limpeza,
        }
    except Exception as erro:
        if instalado:
            destino.unlink(missing_ok=True)
            manifesto_destino.unlink(missing_ok=True)
        return {
            "saudavel": False,
            "estado": "compactacao_falhou",
            "motivo": type(erro).__name__,
            "detalhe": str(erro)[:300],
            "criado": False,
            "caminho": str(destino),
        }
    finally:
        arquivo_temporario.unlink(missing_ok=True)
        manifesto_temporario.unlink(missing_ok=True)


def verificar_backup_compactado(caminho, pasta_temporaria=None):
    caminho = Path(caminho)
    if not caminho.is_file():
        return {
            "saudavel": False,
            "valido": False,
            "motivo": "arquivo_ausente",
            "caminho": str(caminho),
        }
    manifesto, erro_manifesto = _carregar_manifesto(
        caminho_manifesto_compactado(caminho)
    )
    if erro_manifesto:
        return {
            "saudavel": False,
            "valido": False,
            "motivo": erro_manifesto,
            "caminho": str(caminho),
        }
    if manifesto.get("versao") != VERSAO_BACKUP_COMPACTADO:
        return {
            "saudavel": False,
            "valido": False,
            "motivo": "versao_manifesto_incompativel",
            "caminho": str(caminho),
        }
    try:
        tamanho_compactado = caminho.stat().st_size
        checksum_compactado = calcular_sha256(caminho)
    except OSError as erro:
        return {
            "saudavel": False,
            "valido": False,
            "motivo": "leitura_compactado_falhou",
            "erro": type(erro).__name__,
            "caminho": str(caminho),
        }
    if (
        tamanho_compactado != manifesto.get("tamanho_compactado_bytes")
        or checksum_compactado != manifesto.get("sha256_compactado")
    ):
        return {
            "saudavel": False,
            "valido": False,
            "motivo": "checksum_compactado_divergente",
            "caminho": str(caminho),
        }

    temporario = None
    manifesto_sqlite_temporario = None
    try:
        descritor, nome = tempfile.mkstemp(
            suffix=".db", dir=pasta_temporaria
        )
        os.close(descritor)
        temporario = Path(nome)
        checksum_sqlite, tamanho_sqlite = _sha256_e_tamanho_descompactando(
            caminho, temporario
        )
        if (
            checksum_sqlite != manifesto.get("sha256_sqlite")
            or tamanho_sqlite != manifesto.get("tamanho_sqlite_bytes")
        ):
            return {
                "saudavel": False,
                "valido": False,
                "motivo": "conteudo_sqlite_divergente",
                "caminho": str(caminho),
            }
        manifesto_sqlite = dict(manifesto.get("manifesto_sqlite") or {})
        manifesto_sqlite.update({
            "arquivo": temporario.name,
            "tamanho_bytes": tamanho_sqlite,
            "sha256": checksum_sqlite,
        })
        manifesto_sqlite_temporario = caminho_manifesto(temporario)
        _gravar_json_atomico(
            manifesto_sqlite_temporario, manifesto_sqlite
        )
        modo_verificacao = manifesto.get(
            "modo_verificacao_sqlite", "profissional_atual"
        )
        verificacao_sqlite = (
            verificar_backup_legado(temporario)
            if modo_verificacao == "integridade_legada"
            else verificar_backup(temporario)
        )
        valido = bool(verificacao_sqlite.get("valido"))
        return {
            "saudavel": valido,
            "valido": valido,
            "motivo": None if valido else verificacao_sqlite.get("motivo"),
            "caminho": str(caminho),
            "checksum_compactado": checksum_compactado,
            "checksum_sqlite": checksum_sqlite,
            "tamanho_compactado_bytes": tamanho_compactado,
            "tamanho_sqlite_bytes": tamanho_sqlite,
            "economia_fracao": round(
                1 - tamanho_compactado / tamanho_sqlite, 4
            ) if tamanho_sqlite else 0.0,
            "integridade_sqlite": verificacao_sqlite,
            "modo_verificacao_sqlite": modo_verificacao,
        }
    except (OSError, EOFError, gzip.BadGzipFile) as erro:
        return {
            "saudavel": False,
            "valido": False,
            "motivo": "descompactacao_falhou",
            "erro": type(erro).__name__,
            "caminho": str(caminho),
        }
    finally:
        if manifesto_sqlite_temporario is not None:
            manifesto_sqlite_temporario.unlink(missing_ok=True)
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def restaurar_backup_compactado(
    caminho, destino, pasta_temporaria=None
):
    """Restaura para um destino ausente usando instalação atômica."""
    caminho = Path(caminho)
    destino = Path(destino)
    if destino.exists():
        return {
            "saudavel": False,
            "estado": "destino_ja_existe",
            "destino": str(destino),
        }
    verificacao = verificar_backup_compactado(
        caminho, pasta_temporaria=pasta_temporaria
    )
    if not verificacao.get("saudavel"):
        return {
            "saudavel": False,
            "estado": "backup_compactado_invalido",
            "motivo": verificacao.get("motivo"),
            "destino": str(destino),
        }
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(
        f".{destino.name}.{uuid4().hex}.tmp"
    )
    try:
        checksum, tamanho = _sha256_e_tamanho_descompactando(
            caminho, temporario
        )
        if (
            checksum != verificacao.get("checksum_sqlite")
            or tamanho != verificacao.get("tamanho_sqlite_bytes")
        ):
            raise RuntimeError("round_trip_restauracao_divergente")
        temporario.replace(destino)
        return {
            "saudavel": True,
            "estado": "restaurado_atomicamente",
            "origem": str(caminho),
            "destino": str(destino),
            "checksum_sqlite": checksum,
            "tamanho_sqlite_bytes": tamanho,
        }
    except Exception as erro:
        return {
            "saudavel": False,
            "estado": "restauracao_falhou",
            "motivo": type(erro).__name__,
            "detalhe": str(erro)[:300],
            "destino": str(destino),
        }
    finally:
        temporario.unlink(missing_ok=True)


def executar_drill_restauracao_compactada(
    pasta_backups, anterior=None, agora=None
):
    """Restaura integralmente cada novo compacto uma única vez por checksum."""
    pasta_backups = Path(pasta_backups)
    anterior = dict(anterior or {})
    agora = (agora or datetime.now()).replace(microsecond=0)
    base = {
        "versao": "drill-restauracao-compactada-v1",
        "altera_backup": False,
        "altera_banco_ativo": False,
    }
    try:
        compactados = sorted(
            (
                item for item in pasta_backups.glob("*.db.gz")
                if item.is_file()
            ),
            key=lambda item: (item.stat().st_mtime, item.name),
        )
    except OSError as erro:
        return {
            **base,
            "saudavel": False,
            "estado": "pasta_backups_indisponivel",
            "erro": type(erro).__name__,
            "executado": False,
        }
    if not compactados:
        return {
            **base,
            "saudavel": True,
            "estado": "aguardando_backup_compacto",
            "executado": False,
        }
    origem = compactados[-1]
    manifesto, erro_manifesto = _carregar_manifesto(
        caminho_manifesto_compactado(origem)
    )
    checksum = (
        manifesto.get("sha256_compactado") if manifesto else None
    )
    if erro_manifesto or not checksum:
        return {
            **base,
            "saudavel": False,
            "estado": "manifesto_compactado_invalido",
            "motivo": erro_manifesto or "checksum_ausente",
            "backup": origem.name,
            "executado": False,
        }
    if (
        anterior.get("saudavel") is True
        and anterior.get("checksum_compactado") == checksum
    ):
        return {
            **anterior,
            **base,
            "executado": False,
            "resultado_reutilizado": True,
        }

    raiz_temporaria = Path(tempfile.gettempdir()).resolve()
    # Cada watchdog/teste recebe um diretório próprio. Um nome fixo fazia duas
    # verificações simultâneas disputarem o mesmo SQLite restaurado no Windows
    # e podia produzir um falso erro de recuperação por arquivo em uso.
    pasta_drill = (
        raiz_temporaria
        / f"packball_drill_restauracao_{uuid4().hex}"
    ).resolve()
    if pasta_drill.parent != raiz_temporaria:
        return {
            **base,
            "saudavel": False,
            "estado": "pasta_drill_fora_do_diretorio_temporario",
            "executado": False,
        }
    pasta_drill.mkdir(parents=True, exist_ok=False)
    destino = pasta_drill / f"restaurado_{checksum[:16]}.db"
    artefatos = (
        destino,
        caminho_manifesto(destino),
        Path(f"{destino}-wal"),
        Path(f"{destino}-shm"),
    )
    for artefato in artefatos:
        artefato.unlink(missing_ok=True)
    resultado = None
    try:
        restauracao = restaurar_backup_compactado(
            origem, destino, pasta_temporaria=pasta_drill
        )
        if not restauracao.get("saudavel"):
            raise RuntimeError(
                "restauracao_nao_saudavel:"
                f"{restauracao.get('estado')}:{restauracao.get('motivo')}"
            )
        modo_verificacao = manifesto.get(
            "modo_verificacao_sqlite", "profissional_atual"
        )
        if modo_verificacao == "integridade_legada":
            manifesto_restaurado = dict(
                manifesto.get("manifesto_sqlite") or {}
            )
            manifesto_restaurado.update({
                "arquivo": destino.name,
                "tamanho_bytes": destino.stat().st_size,
                "sha256": manifesto.get("sha256_sqlite"),
            })
            _gravar_json_atomico(
                caminho_manifesto(destino), manifesto_restaurado
            )
            verificacao = verificar_backup_legado(destino)
        else:
            verificacao = verificar_backup(
                destino, criar_manifesto=True, agora=agora
            )
        if not verificacao.get("valido"):
            raise RuntimeError(
                "sqlite_restaurado_invalido:"
                f"{verificacao.get('motivo')}"
            )
        checksum_restaurado = verificacao.get("checksum_sha256")
        if checksum_restaurado != manifesto.get("sha256_sqlite"):
            raise RuntimeError("checksum_sqlite_restaurado_divergente")
        resultado = {
            **base,
            "saudavel": True,
            "estado": "restauracao_confirmada",
            "backup": origem.name,
            "checksum_compactado": checksum,
            "checksum_sqlite": checksum_restaurado,
            "testado_em": agora.isoformat(),
            "executado": True,
            "resultado_reutilizado": False,
        }
    except Exception as erro:
        resultado = {
            **base,
            "saudavel": False,
            "estado": "restauracao_falhou",
            "backup": origem.name,
            "checksum_compactado": checksum,
            "testado_em": agora.isoformat(),
            "executado": True,
            "resultado_reutilizado": False,
            "erro": type(erro).__name__,
            "detalhe": str(erro)[:300],
        }
    finally:
        erros_limpeza = []
        for artefato in artefatos:
            try:
                artefato.unlink(missing_ok=True)
            except OSError as erro:
                erros_limpeza.append(type(erro).__name__)
        try:
            pasta_drill.rmdir()
        except OSError as erro:
            erros_limpeza.append(type(erro).__name__)
        resultado["temporarios_removidos"] = not erros_limpeza
        if erros_limpeza:
            resultado["avisos_limpeza"] = erros_limpeza
    return resultado
