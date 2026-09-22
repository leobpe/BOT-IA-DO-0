"""Pré-registra o corte de nota <= 81,5 do Gol HT somente em sombra.

O corte foi escolhido em uma busca exploratória com divisão cronológica.
Por isso, toda a evidência abaixo serve apenas para gerar a hipótese. A
confirmação considera exclusivamente primeiras decisões por partida criadas
depois de ``iniciado_em``, na linhagem HT v8b exata, contra seu controle
contemporâneo. Nada é promovido automaticamente nem enviado ao Telegram.
"""

import json
from datetime import datetime
from pathlib import Path

from banco import BancoMonitor
from hipoteses_sombra import registrar_hipotese_sombra
from versoes_operacionais import VERSAO_GOL_HT_MAX_28


IDENTIFICADOR = "gol_ht_nota_max_81_5_v1_20260825"
REGRA_VERSAO = VERSAO_GOL_HT_MAX_28
MERCADO = "gol_ht"
FEATURE = "pontuacao_tecnica"
OPERADOR = "menor_igual"
LIMIAR = 81.5
MINIMO_RESULTADOS = 40
EVIDENCIA_HISTORICA = {
    "metodo": "cortes_sombra_v1_divisao_cronologica_movel",
    "busca_exploratoria_multiplos_cortes": True,
    "features_testadas": 12,
    "desenvolvimento_total": 56,
    "corte_desenvolvimento": {
        "resultados_validos": 37,
        "greens": 23,
        "reds": 14,
        "lucro_unidades": 4.88,
        "roi": 0.1319,
    },
    "validacao_exploratoria_posterior": {
        "resultados_validos": 17,
        "greens": 12,
        "reds": 5,
        "lucro_unidades": 3.34,
        "roi": 0.1965,
        "auc_pontuacao": 0.8083,
        "limite_inferior_auc_95": 0.5957,
    },
    "uso": "somente_geracao_de_hipotese",
    "criterio_confirmacao_futura": {
        "resultados_selecionados_minimos": MINIMO_RESULTADOS,
        "roi_selecionada_maior_que_zero": True,
        "lucro_selecionado_maior_que_zero": True,
        "limite_inferior_ic95_delta_roi_maior_que_zero": True,
        "controle_contemporaneo": True,
    },
    "observacao": (
        "A validação exploratória não confirma o corte. Somente jogos futuros "
        "posteriores à âncora podem confirmá-lo; a avaliação permanece sem "
        "Telegram e sem promoção automática."
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
