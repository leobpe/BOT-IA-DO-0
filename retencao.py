from pathlib import Path


def rotacionar_arquivo(caminho, limite_bytes, copias=5):
    caminho = Path(caminho)
    if not caminho.exists() or caminho.stat().st_size < int(limite_bytes):
        return False
    copias = max(int(copias), 1)
    mais_antiga = Path(f"{caminho}.{copias}")
    if mais_antiga.exists():
        mais_antiga.unlink()
    for indice in range(copias - 1, 0, -1):
        origem = Path(f"{caminho}.{indice}")
        if origem.exists():
            origem.replace(Path(f"{caminho}.{indice + 1}"))
    caminho.replace(Path(f"{caminho}.1"))
    return True
