import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from backup_banco import BackupBanco, verificar_arquivo_backup


PASTA = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(
        description="Verifica a capacidade de restauração do backup diário."
    )
    parser.add_argument(
        "--registrar", action="store_true",
        help="Cria manifesto ausente somente se a cópia for compatível.",
    )
    parser.add_argument(
        "--recriar", action="store_true",
        help="Regenera a cópia do dia se estiver ausente ou incompatível.",
    )
    argumentos = parser.parse_args()
    pasta_backups = PASTA / "backups"
    regenerado = False
    if argumentos.recriar:
        origem = PASTA / "monitor_packball.db"
        uri = origem.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=30)
        try:
            _, regenerado = BackupBanco(pasta_backups).criar_diario(
                conexao, datetime.now()
            )
        finally:
            conexao.close()
    backups = sorted(BackupBanco._glob_formatos(
        pasta_backups, "monitor_????????.db"
    ))
    if not backups:
        raise SystemExit("Nenhum backup encontrado.")
    resultado = verificar_arquivo_backup(
        backups[-1], criar_manifesto=argumentos.registrar
    )
    resultado["regenerado"] = regenerado
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    if not resultado["valido"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
