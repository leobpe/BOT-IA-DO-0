import json
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from hipoteses_sombra import registrar_hipotese_sombra


IDENTIFICADOR = "gol_ft_ritmo_escanteios_5m_v1_20260809"
REGRA_VERSAO = "sinais-v6"
MERCADO = "gol_ft"
FEATURE = "janelas.5.escanteios_por_minuto"
OPERADOR = "maior_igual"
LIMIAR = 0.1786
MINIMO_RESULTADOS = 30
EVIDENCIA_HISTORICA = {
    "dataset_fingerprint": (
        "f6d8cab43b667a95eba648272d44b524b992cf219df00d8f0b9cc5787be711b8"
    ),
    "amostra_total_independente": 298,
    "metodo": "corte_sombra_cronologico_exploratorio_70_30",
    "desenvolvimento": {
        "n_total": 208,
        "n_selecionado": 44,
        "greens": 29,
        "reds": 15,
        "acerto": 0.6591,
        "roi": 0.1145,
    },
    "validacao_exploratoria": {
        "n_total": 90,
        "n_selecionado": 25,
        "greens": 21,
        "reds": 4,
        "acerto": 0.84,
        "roi": 0.3778,
    },
    "busca_exploratoria_multiplos_cortes": True,
    "validacao_original_movel": True,
    "uso": "somente_geracao_de_hipotese",
    "observacao": (
        "O corte foi escolhido após busca exploratória e a divisão histórica "
        "não era congelada. Somente resultados independentes posteriores ao "
        "registro, comparados ao controle contemporâneo com IC95, podem "
        "confirmar a hipótese. Não há aplicação automática."
    ),
}


def registrar(conexao, iniciado_em=None):
    return registrar_hipotese_sombra(
        conexao,
        IDENTIFICADOR,
        REGRA_VERSAO,
        MERCADO,
        FEATURE,
        OPERADOR,
        LIMIAR,
        EVIDENCIA_HISTORICA,
        minimo_resultados=MINIMO_RESULTADOS,
        iniciado_em=iniciado_em,
    )


def main():
    banco = BancoMonitor(Path(__file__).parent / "monitor_packball.db")
    try:
        hipotese = registrar(banco.conexao, iniciado_em=datetime.now())
    finally:
        banco.fechar()
    print(json.dumps(hipotese, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
