from pathlib import Path

from controle_sistema import solicitar_modo_manutencao
from observabilidade import Observabilidade


def main():
    pasta = Path(__file__).parent
    estado = solicitar_modo_manutencao(pasta)
    Observabilidade(pasta / "monitor_eventos.jsonl").modo_manutencao(
        "solicitado", estado
    )
    print("Parada segura solicitada.")
    print(
        "Monitor, watchdog e pré-live encerrarão após o ciclo atual, sem "
        "autorreinício."
    )
    print(
        "Para retomar explicitamente, execute: "
        "python iniciar_sistema.py --retomar-manutencao"
    )


if __name__ == "__main__":
    main()
