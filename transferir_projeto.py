import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from processo_monitor import ler_estado, pid_ativo, trava_em_uso


VERSAO_MANIFESTO = "transferencia-packball-v2"
ARQUIVOS_OBRIGATORIOS = (
    ".env",
    "packball_session.json",
    "monitor_packball.db",
    "pre_live.db",
    "requirements.lock.txt",
    "iniciar_sistema.py",
    "preflight_reinicio.py",
)
ARQUIVOS_TRANSITORIOS = {
    "autostart_ultima_execucao.json",
    "bot_comandos_instancia.lock",
    "bot_comandos_processo.json",
    "modo_manutencao.json",
    "monitor_instancia.lock",
    "monitor_packball.db-shm",
    "monitor_packball.db-wal",
    "pre_live.db-shm",
    "pre_live.db-wal",
    "pre_live_instancia.lock",
    "pre_live_processo.json",
    "monitor_processo.json",
    "watchdog_estado.json",
    "watchdog_instancia.lock",
    "watchdog_processo.json",
}
PASTAS_IGNORADAS = {
    ".agents",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
}
ARQUIVOS_SENSIVEIS = {".env", "packball_session.json"}


def _sha256(caminho, bloco=1024 * 1024):
    resumo = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        while True:
            dados = arquivo.read(bloco)
            if not dados:
                break
            resumo.update(dados)
    return resumo.hexdigest()


def _pasta_ignorada(caminho, incluir_backups=False):
    nome = Path(caminho).name
    if nome in PASTAS_IGNORADAS or nome.startswith(".venv_broken_"):
        return True
    if nome.lower() == "backups" and not incluir_backups:
        return True
    return nome.startswith("tmp")


def _arquivo_ignorado(caminho):
    caminho = Path(caminho)
    nome = caminho.name
    return (
        nome in ARQUIVOS_TRANSITORIOS
        or nome.endswith(".tmp")
        or nome.startswith(".teste_")
        or nome == "="
    )


def verificar_processos(pasta, verificar_pid=None, verificar_trava=None):
    pasta = Path(pasta)
    verificar_pid = verificar_pid or pid_ativo
    verificar_trava = verificar_trava or trava_em_uso
    componentes = {}
    for nome in ("monitor", "watchdog", "pre_live"):
        estado = ler_estado(pasta / f"{nome}_processo.json")
        pid = estado.get("pid")
        trava = bool(verificar_trava(pasta / f"{nome}_instancia.lock"))
        processo = bool(verificar_pid(pid))
        componentes[nome] = {
            "ativo": trava or processo,
            "pid": pid,
            "trava_ativa": trava,
            "pid_ativo": processo,
        }
    return {
        "parado": not any(item["ativo"] for item in componentes.values()),
        "componentes": componentes,
    }


def auditar_transferencia(
    pasta, verificar_pid=None, verificar_trava=None, verificar_processos_fn=None
):
    pasta = Path(pasta)
    ausentes = [
        nome for nome in ARQUIVOS_OBRIGATORIOS
        if not (pasta / nome).is_file()
    ]
    verificar_processos_fn = verificar_processos_fn or verificar_processos
    processos = verificar_processos_fn(
        pasta,
        verificar_pid=verificar_pid,
        verificar_trava=verificar_trava,
    )
    banco = pasta / "monitor_packball.db"
    banco_legivel = banco.is_file() and banco.stat().st_size > 0
    banco_pre_live = pasta / "pre_live.db"
    banco_pre_live_legivel = (
        banco_pre_live.is_file() and banco_pre_live.stat().st_size > 0
    )
    return {
        "pronto": (
            not ausentes and banco_legivel and banco_pre_live_legivel
            and processos["parado"]
        ),
        "arquivos_ausentes": ausentes,
        "banco_legivel": banco_legivel,
        "banco_pre_live_legivel": banco_pre_live_legivel,
        "processos": processos,
        "contem_credenciais": all(
            (pasta / nome).is_file() for nome in ARQUIVOS_SENSIVEIS
        ),
    }


def _copiar_banco_consistente(origem, destino):
    origem = Path(origem)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    uri = origem.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(
        uri, uri=True, timeout=30
    )) as conexao_origem:
        with closing(sqlite3.connect(
            destino, timeout=30
        )) as conexao_destino:
            conexao_origem.backup(conexao_destino)
            integridade = [
                linha[0]
                for linha in conexao_destino.execute("PRAGMA quick_check")
            ]
    if integridade != ["ok"]:
        destino.unlink(missing_ok=True)
        raise RuntimeError(
            "A cópia do banco não passou na verificação de integridade."
        )
    return integridade


def _validar_destino(origem, destino):
    origem = Path(origem).resolve()
    destino = Path(destino).resolve()
    if destino == origem or origem in destino.parents:
        raise ValueError("Escolha um destino fora da pasta do projeto.")
    if destino.exists() and any(destino.iterdir()):
        raise FileExistsError("A pasta de destino precisa estar vazia.")
    return destino


def criar_pacote(
    pasta,
    destino,
    incluir_backups=False,
    agora=None,
    verificar_pid=None,
    verificar_trava=None,
    verificar_processos_fn=None,
):
    pasta = Path(pasta).resolve()
    destino = _validar_destino(pasta, destino)
    auditoria = auditar_transferencia(
        pasta,
        verificar_pid=verificar_pid,
        verificar_trava=verificar_trava,
        verificar_processos_fn=verificar_processos_fn,
    )
    if not auditoria["pronto"]:
        if not auditoria["processos"]["parado"]:
            raise RuntimeError(
                "Monitor, watchdog ou pré-live ainda está ativo. Execute "
                "python parar_sistema.py e aguarde a parada completa."
            )
        raise RuntimeError(
            "Transferência recusada; arquivos obrigatórios ausentes ou "
            "banco inválido: "
            + ", ".join(auditoria["arquivos_ausentes"] or ["banco"])
        )

    destino.mkdir(parents=True, exist_ok=True)
    arquivos = []
    banco_origem = pasta / "monitor_packball.db"
    banco_destino = destino / banco_origem.name
    _copiar_banco_consistente(banco_origem, banco_destino)
    banco_pre_live_origem = pasta / "pre_live.db"
    banco_pre_live_destino = destino / banco_pre_live_origem.name
    _copiar_banco_consistente(
        banco_pre_live_origem, banco_pre_live_destino
    )
    bancos_origem = {banco_origem, banco_pre_live_origem}

    for raiz, pastas, nomes in os.walk(pasta):
        raiz = Path(raiz)
        pastas[:] = [
            nome for nome in pastas
            if not _pasta_ignorada(raiz / nome, incluir_backups)
        ]
        for nome in nomes:
            origem = raiz / nome
            relativo = origem.relative_to(pasta)
            if origem in bancos_origem or _arquivo_ignorado(origem):
                continue
            alvo = destino / relativo
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, alvo)

    agora = agora or datetime.now()
    for caminho in sorted(destino.rglob("*")):
        if not caminho.is_file() or caminho.name == "manifesto_transferencia.json":
            continue
        relativo = caminho.relative_to(destino).as_posix()
        arquivos.append({
            "caminho": relativo,
            "tamanho": caminho.stat().st_size,
            "sha256": _sha256(caminho),
            "sensivel": caminho.name in ARQUIVOS_SENSIVEIS,
        })
    manifesto = {
        "versao": VERSAO_MANIFESTO,
        "criado_em": agora.replace(microsecond=0).isoformat(),
        "origem": str(pasta),
        "incluiu_backups": bool(incluir_backups),
        "arquivos": arquivos,
        "total_arquivos": len(arquivos),
        "total_bytes": sum(item["tamanho"] for item in arquivos),
        "banco": {
            "arquivo": banco_destino.name,
            "quick_check": ["ok"],
            "sha256": _sha256(banco_destino),
        },
        "bancos": {
            banco_destino.name: {
                "quick_check": ["ok"],
                "sha256": _sha256(banco_destino),
            },
            banco_pre_live_destino.name: {
                "quick_check": ["ok"],
                "sha256": _sha256(banco_pre_live_destino),
            },
        },
        "seguranca": (
            "Pacote confidencial: contém token, chave de API e sessão "
            "autenticada. Não compartilhar nem publicar."
        ),
    }
    (destino / "manifesto_transferencia.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifesto


def _caminho_registrado_seguro(pasta, nome):
    pasta = Path(pasta).resolve()
    relativo = Path(str(nome))
    if relativo.is_absolute() or ".." in relativo.parts:
        return None
    caminho = (pasta / relativo).resolve()
    if caminho != pasta and pasta not in caminho.parents:
        return None
    return caminho


def verificar_pacote(pasta):
    pasta = Path(pasta).resolve()
    caminho_manifesto = pasta / "manifesto_transferencia.json"
    try:
        manifesto = json.loads(caminho_manifesto.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "valido": False,
            "motivos": ["manifesto_ausente"],
            "arquivos_verificados": 0,
        }
    except (OSError, json.JSONDecodeError, TypeError):
        return {
            "valido": False,
            "motivos": ["manifesto_invalido"],
            "arquivos_verificados": 0,
        }

    motivos = []
    if manifesto.get("versao") != VERSAO_MANIFESTO:
        motivos.append("versao_manifesto_incompativel")
    registros = manifesto.get("arquivos")
    if not isinstance(registros, list):
        registros = []
        motivos.append("lista_arquivos_invalida")

    vistos = set()
    verificados = 0
    for registro in registros:
        if not isinstance(registro, dict):
            motivos.append("registro_arquivo_invalido")
            continue
        nome = registro.get("caminho")
        caminho = _caminho_registrado_seguro(pasta, nome)
        if caminho is None:
            motivos.append(f"caminho_inseguro:{nome}")
            continue
        chave = caminho.as_posix().casefold()
        if chave in vistos:
            motivos.append(f"arquivo_duplicado:{nome}")
            continue
        vistos.add(chave)
        if not caminho.is_file():
            motivos.append(f"arquivo_ausente:{nome}")
            continue
        tamanho = caminho.stat().st_size
        if tamanho != registro.get("tamanho"):
            motivos.append(f"tamanho_divergente:{nome}")
            continue
        if _sha256(caminho) != registro.get("sha256"):
            motivos.append(f"checksum_divergente:{nome}")
            continue
        verificados += 1

    if manifesto.get("total_arquivos") != len(registros):
        motivos.append("total_arquivos_divergente")
    total_calculado = sum(
        item.get("tamanho", 0)
        for item in registros
        if isinstance(item, dict) and isinstance(item.get("tamanho"), int)
    )
    if manifesto.get("total_bytes") != total_calculado:
        motivos.append("total_bytes_divergente")

    bancos_registrados = manifesto.get("bancos")
    if not isinstance(bancos_registrados, dict):
        bancos_registrados = {}
        motivos.append("mapa_bancos_invalido")
    integridade_bancos = {}
    for nome_banco in ("monitor_packball.db", "pre_live.db"):
        registro = bancos_registrados.get(nome_banco)
        if not isinstance(registro, dict):
            integridade_bancos[nome_banco] = []
            motivos.append(f"banco_nao_registrado:{nome_banco}")
            continue
        banco = _caminho_registrado_seguro(pasta, nome_banco)
        integridade = []
        if banco is None or not banco.is_file():
            motivos.append(f"banco_ausente_ou_caminho_inseguro:{nome_banco}")
        else:
            try:
                uri = banco.resolve().as_uri() + "?mode=ro"
                with closing(sqlite3.connect(
                    uri, uri=True, timeout=30
                )) as conexao:
                    integridade = [
                        linha[0]
                        for linha in conexao.execute("PRAGMA quick_check")
                    ]
            except sqlite3.Error:
                integridade = ["erro_sqlite"]
            if integridade != ["ok"]:
                motivos.append(f"banco_integro_nao_confirmado:{nome_banco}")
            if registro.get("sha256") != _sha256(banco):
                motivos.append(f"checksum_banco_divergente:{nome_banco}")
        integridade_bancos[nome_banco] = integridade
    integridade_banco = integridade_bancos.get("monitor_packball.db", [])

    return {
        "valido": not motivos,
        "motivos": motivos,
        "arquivos_verificados": verificados,
        "arquivos_registrados": len(registros),
        "integridade_banco": integridade_banco,
        "integridade_bancos": integridade_bancos,
        "contem_credenciais": all((pasta / item).is_file()
                                   for item in ARQUIVOS_SENSIVEIS),
    }


def _formatar_auditoria(resultado):
    estado = "PRONTO" if resultado["pronto"] else "AINDA NÃO PRONTO"
    linhas = [f"Transferência: {estado}"]
    for nome, item in resultado["processos"]["componentes"].items():
        linhas.append(
            f"- {nome}: {'ativo' if item['ativo'] else 'parado'}"
        )
    if resultado["arquivos_ausentes"]:
        linhas.append(
            "- Arquivos ausentes: "
            + ", ".join(resultado["arquivos_ausentes"])
        )
    linhas.append(
        "- Banco: " + ("presente" if resultado["banco_legivel"] else "inválido")
    )
    linhas.append(
        "- Banco pré-live: "
        + ("presente" if resultado["banco_pre_live_legivel"] else "inválido")
    )
    return "\n".join(linhas)


def _formatar_verificacao(resultado):
    estado = "ÍNTEGRO" if resultado["valido"] else "REPROVADO"
    linhas = [f"Pacote recebido: {estado}"]
    linhas.append(
        "- Arquivos verificados: "
        f"{resultado.get('arquivos_verificados', 0)}/"
        f"{resultado.get('arquivos_registrados', 0)}"
    )
    if resultado.get("integridade_banco"):
        linhas.append(
            "- Banco SQLite: "
            + ("íntegro" if resultado["integridade_banco"] == ["ok"]
               else "inválido")
        )
    for motivo in resultado.get("motivos") or []:
        linhas.append(f"- Problema: {motivo}")
    return "\n".join(linhas)


def main():
    parser = argparse.ArgumentParser(
        description="Prepara uma cópia segura do Bot PackBall para outro PC."
    )
    parser.add_argument(
        "destino", nargs="?", help="Pasta vazia no pendrive ou disco externo."
    )
    parser.add_argument(
        "--auditar", action="store_true",
        help="Somente verifica se a transferência pode ser realizada."
    )
    parser.add_argument(
        "--incluir-backups", action="store_true",
        help="Inclui também a pasta de backups, aumentando bastante o pacote."
    )
    parser.add_argument(
        "--verificar-pacote", metavar="PASTA",
        help="Confere checksums e banco do pacote recebido no outro PC."
    )
    argumentos = parser.parse_args()
    pasta = Path(__file__).parent
    if argumentos.verificar_pacote:
        resultado = verificar_pacote(argumentos.verificar_pacote)
        print(_formatar_verificacao(resultado))
        raise SystemExit(0 if resultado["valido"] else 1)
    if argumentos.auditar or not argumentos.destino:
        print(_formatar_auditoria(auditar_transferencia(pasta)))
        if not argumentos.destino:
            print("Informe um destino para criar o pacote.")
        return
    manifesto = criar_pacote(
        pasta, argumentos.destino,
        incluir_backups=argumentos.incluir_backups,
    )
    print("Pacote de transferência criado e verificado.")
    print(f"Destino: {Path(argumentos.destino).resolve()}")
    print(f"Arquivos: {manifesto['total_arquivos']}")
    print(f"Tamanho: {manifesto['total_bytes'] / 1024 / 1024:.1f} MB")
    print(manifesto["seguranca"])


if __name__ == "__main__":
    main()
