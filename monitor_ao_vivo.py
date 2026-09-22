import sys


def configurar_saida_utf8():
    """Evita UnicodeEncodeError em nomes de times no console do Windows."""
    for nome in ("stdout", "stderr"):
        fluxo = getattr(sys, nome, None)
        reconfigurar = getattr(fluxo, "reconfigure", None)
        if callable(reconfigurar):
            reconfigurar(encoding="utf-8", errors="backslashreplace")


configurar_saida_utf8()

from servico_monitor import main


if __name__ == "__main__":
    main()
