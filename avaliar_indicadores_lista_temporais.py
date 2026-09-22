import json
from pathlib import Path

from banco import BancoMonitor
from fallback_indicadores_lista import resumir_auditoria_temporal_sqlite


def main():
    banco = BancoMonitor(Path("monitor_packball.db"))
    try:
        resumo = resumir_auditoria_temporal_sqlite(banco.conexao)
    finally:
        banco.fechar()
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
