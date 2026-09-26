import json
import inspect
import math
import os
import re
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from configuracao import odd_elegivel, obter_limites_risco
from acompanhamento_odd import avaliar_resultado_acompanhamento_odd
from validade_historico_gols import avaliar_historico_envio
from filtro_ht_chutes_recentes import avaliar_chutes_ht
from resumo_forca_sinais import resumo_forca_ao_vivo
from probabilidade_por_acertos import anexar_estimativa
from backtest import AvaliadorBacktest
from calibracao import CalibradorBacktest
from exploracao_sombra import (
    REGRA_FINGERPRINT_GOL_FT_V3,
    REGRA_VERSAO_GOL_FT_V3,
    VERSAO_EXPLORACAO_ASIATICA,
    VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE,
)
from mercados import ROTULOS_MERCADOS
from linhagem_regras import fingerprint_vinculado_no_banco
from integridade_calibracao import auditar_diversidade_amostra_calibracao
from motor_sinais import VERSAO_REGRAS
from motor_sinais import ODDS_MAX_IDADE_SEGUNDOS
from politica_proximo_gol_preciso import (
    MINUTO_MAXIMO as PROXIMO_GOL_MINUTO_MAXIMO_PROSPECTIVO,
    ODD_MAXIMA_EXCLUSIVA as PROXIMO_GOL_ODD_MAXIMA_EXCLUSIVA,
    MOTIVO_MINUTO as MOTIVO_PROXIMO_GOL_MINUTO,
    MOTIVO_ODD as MOTIVO_PROXIMO_GOL_ODD,
    MOTIVO_PRESSAO as MOTIVO_PROXIMO_GOL_PRESSAO,
    MOTIVO_QUALIDADE as MOTIVO_PROXIMO_GOL_QUALIDADE,
    avaliar_criterios_precisos,
)
from relatorio_simulacoes import registrar_ou_obter_experimento_filtro
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)
from versoes_proximo_gol_balanceado import (
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
)
from versoes_regras import (
    VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
    VERSAO_PROXIMO_ESCANTEIO_MAX_86,
)
from fusao_packball_thestats import VERSAO_EXPERIMENTO_FUSAO
from gols_antecipados import (
    VERSOES_GOLS_ANTECIPADOS,
    gols_antecipados_grupo_ativo,
)
from gols_capacidade_times import (
    VERSAO_GOL_FT_CAPACIDADE,
    VERSAO_GOL_HT_CAPACIDADE,
    VERSOES_GOLS_CAPACIDADE,
    gols_capacidade_grupo_ativo,
)
from gols_capacidade_contextual_v2 import (
    VERSOES as VERSOES_GOLS_CAPACIDADE_CONTEXTUAL_V2,
)
from controle_v2b_ft import v2b_ft_grupo_liberado
from controle_gols_antecipados import metodo_liberado as metodo_antecipado_liberado
from controle_proximo_gol_balanceado import (
    grupo_liberado as proximo_gol_balanceado_grupo_liberado,
)
from gol_ht_00_min20 import VERSAO as VERSAO_GOL_HT_00_MIN20
from gol_2t_pos_ht_red import (
    VERSAO as VERSAO_GOL_2T_POS_HT_RED,
    grupo_ativo as gol_2t_pos_ht_red_grupo_ativo,
)
from gol_ft_tendencia_mais_um import VERSAO as VERSAO_GOL_FT_TENDENCIA_MAIS_UM
from top_criterios_gols import (
    LINHAGEM as LINHAGEM_TOP_CRITERIOS_GOLS,
    VERSAO_FT as VERSAO_TOP_CRITERIO_FT,
    VERSAO_HT as VERSAO_TOP_CRITERIO_HT,
    VERSOES as VERSOES_TOP_CRITERIOS_GOLS,
)
from filtro_gol_ft_antecipado_preciso import (
    avaliar_filtro_gol_ft_antecipado,
)
from controle_filtro_gol_ft_preciso import (
    entrega_liberada as filtro_gol_ft_preciso_liberado,
)
from controle_escanteios_ft_asiatico import (
    entrega_liberada as escanteios_ft_asiatico_liberado,
)
from filtro_gol_ht_antecipado_preciso import (
    avaliar_filtro_gol_ht_antecipado,
)
from controle_filtro_gol_ht_preciso import (
    entrega_liberada as filtro_gol_ht_preciso_liberado,
)
from valor_mercado import (
    anexar_valor_mercado,
    avaliar_valor_mercado,
    odd_oposta_sincronizada,
    referencia_tres_vias_sincronizada,
    validar_rastro_valor_mercado,
)


PROBABILIDADE_MINIMA = 0.75
LIMITE_DIARIO_PADRAO = 10
ODD_MINIMA_PADRAO = 1.4
ODD_MAXIMA_PADRAO = 2.5
EXPOSICAO_POR_SINAL = 1.0
LIMITE_EXPOSICAO_DIARIA_PADRAO = 5.0
SLA_PRE_ENVIO_SEGUNDOS = 120.0
ODDS_MAX_IDADE_ASIATICO_SEGUNDOS = 60.0

# Política fechada e versionada para o grupo de SIMULAÇÕES. Toda regra nova
# começa somente em sombra até receber uma decisão explícita em outra versão
# desta política. Isso evita que uma troca de regra libere Telegram por padrão.
VERSAO_POLITICA_ROTEAMENTO_SIMULACOES = (
    "roteamento-simulacoes-teste-v9"
)
REGRAS_SIMULACAO_GRUPO = frozenset({
    (
        "proximo_gol",
        VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
    ),
    (
        "proximo_escanteio",
        VERSAO_PROXIMO_ESCANTEIO_MAX_86,
    ),
    (
        "escanteios_ft_asiatico",
        VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
    ),
})
EXPERIMENTOS_SIMULACAO_GRUPO = frozenset({
    VERSAO_EXPLORACAO_ASIATICA,
    VERSAO_EXPERIMENTO_FUSAO,
    *VERSOES_GOLS_ANTECIPADOS,
    *VERSOES_GOLS_CAPACIDADE,
    *VERSOES_GOLS_CAPACIDADE_CONTEXTUAL_V2,
    VERSAO_GOL_HT_00_MIN20,
    VERSAO_GOL_2T_POS_HT_RED,
    VERSAO_GOL_FT_TENDENCIA_MAIS_UM,
    *VERSOES_TOP_CRITERIOS_GOLS,
    VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA,
})
ESCANTEIOS_FT_ASIATICO_MULTIPLOS_GRUPO_ATIVO = os.getenv(
    "ESCANTEIOS_FT_ASIATICO_MULTIPLOS_GRUPO_ATIVO", "0"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
GOLS_CAPACIDADE_V1_CONGELADA = False
# O braco HT da V1 permanece coletando em sombra, mas deixou de ser enviado ao
# grupo apos 14 resultados (6 green/8 red; ROI -25,7%). A variavel permite um
# rollback explicito sem alterar a geracao ou o historico da coorte.
GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO = os.getenv(
    "GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO", "0"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO = os.getenv(
    "GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO", "0"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
GOLS_CAPACIDADE_CONTEXTUAL_V2_HT_GRUPO_ATIVO = os.getenv(
    "GOLS_CAPACIDADE_CONTEXTUAL_V2_HT_GRUPO_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO = os.getenv(
    "GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
GOL_HT_00_MIN20_GRUPO_ATIVO = os.getenv(
    "GOL_HT_00_MIN20_GRUPO_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO = os.getenv(
    "PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
PONTUACAO_MINIMA_PROXIMO_GOL_BALANCEADO_TESTE = float(os.getenv(
    "PONTUACAO_MINIMA_PROXIMO_GOL_BALANCEADO_TESTE", "60"
))


def gol_ht_sem_tendencia_packball_grupo_ativo():
    """Rollback da excecao HT quando a conversao historica ja foi confirmada."""
    return os.getenv(
        "GOL_HT_SEM_TENDENCIA_PACKBALL_GRUPO_ATIVO", "0"
    ).strip().lower() not in {"0", "false", "nao", "não", "off"}


def gol_ht_historico_insuficiente_com_sot_grupo_ativo():
    """Rollback da excecao HT medida com atividade ofensiva objetiva."""
    return os.getenv(
        "GOL_HT_HISTORICO_INSUFICIENTE_COM_SOT_GRUPO_ATIVO", "0"
    ).strip().lower() not in {"0", "false", "nao", "não", "off"}


def _candidato_metodo_gol_ht_ativo(candidato):
    if candidato.get("mercado") != "gol_ht":
        return False
    return bool(
        candidato_gol_antecipado_grupo_teste(candidato)
        or candidato_gol_capacidade_grupo_teste(candidato)
        or candidato_gol_capacidade_contextual_v2_grupo_teste(candidato)
        or candidato_gol_ht_00_min20_grupo_teste(candidato)
        or candidato_top_criterio_grupo_teste(candidato)
    )


def candidato_gol_ht_sem_tendencia_packball_liberado(candidato):
    """Libera somente a rota HT positiva com a outra protecao confirmada.

    A ausencia da leitura historica do PackBall nao equivale a uma leitura
    negativa. Esta excecao nao aceita amostra pequena, tendencia reprovada nem
    rotas desativadas: exige um metodo HT ativo e apoio historico aprovado.
    """
    if not gol_ht_sem_tendencia_packball_grupo_ativo():
        return False
    if not _candidato_metodo_gol_ht_ativo(candidato):
        return False
    features = _features_candidato(candidato)
    tendencia = features.get("protecao_tendencias_packball") or {}
    conversao = features.get("protecao_conversao_gols") or {}
    return bool(
        tendencia.get("ativa") is True
        and tendencia.get("aprovada") is False
        and tendencia.get("motivo") == "tendencia_packball_indisponivel"
        and conversao.get("ativa") is True
        and conversao.get("aprovada") is True
        and conversao.get("motivo") == "apoio_da_linha_confirmado"
    )


def candidato_gol_ht_historico_insuficiente_com_sot_liberado(candidato):
    """Aceita falta de histórico da linha só com pelo menos dois SOT ao vivo.

    O recorte é exclusivo de HT e reversível. A proteção continua bloqueando
    FT, ausência total de atividade e qualquer reprovação histórica explícita.
    """
    if not gol_ht_historico_insuficiente_com_sot_grupo_ativo():
        return False
    if not _candidato_metodo_gol_ht_ativo(candidato):
        return False
    features = _features_candidato(candidato)
    conversao = features.get("protecao_conversao_gols") or {}
    try:
        chutes_no_gol = float(features.get("chutes_no_gol_total") or 0)
        qualidade = float(features.get("qualidade_dados") or 0)
    except (TypeError, ValueError):
        return False
    return bool(
        conversao.get("ativa") is True
        and conversao.get("aprovada") is False
        and conversao.get("motivo") == "historico_da_linha_insuficiente"
        and chutes_no_gol >= 2
        and qualidade >= 80
    )


# A V3 corrige o apoio histórico por linha e foi liberada pelo usuário para
# substituir no grupo a rota FT de tendência anterior. A chave mantém o
# rollback imediato sem misturar sua validação prospectiva.
GOL_FT_TENDENCIA_MAIS_UM_GRUPO_ATIVO = os.getenv(
    "GOL_FT_TENDENCIA_MAIS_UM_GRUPO_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}
TOP_CRITERIOS_GOLS_GRUPO_ATIVO = os.getenv(
    "TOP_CRITERIOS_GOLS_GRUPO_ATIVO", "1"
).strip().lower() not in {"0", "false", "nao", "não", "off"}

# Motivos históricos específicos continuam preservados para a auditoria. Os
# demais pares fora da lista fechada recebem o motivo genérico de sombra.
REGRAS_SIMULACAO_SUSPENSAS = {
    ("gol_ft", "sinais-v6"): "mercado_reprovado_validacao_gol_ft_v6",
}


def _features_candidato(candidato):
    features = candidato.get("features")
    if isinstance(features, dict):
        return features
    features_json = candidato.get("features_json")
    if isinstance(features_json, str):
        try:
            features = json.loads(features_json)
        except (TypeError, json.JSONDecodeError):
            features = None
    return features if isinstance(features, dict) else {}


def versao_exploracao_candidato(candidato):
    return (
        (_features_candidato(candidato).get("exploracao_sombra") or {})
        .get("versao")
    )


def candidato_gol_2t_pos_ht_red(candidato):
    features = _features_candidato(candidato)
    metodo = features.get("gol_2t_pos_ht_red")
    return bool(
        versao_exploracao_candidato(candidato) == VERSAO_GOL_2T_POS_HT_RED
        and isinstance(metodo, dict)
        and metodo.get("linhagem_sha256")
    )


def candidato_gol_2t_pos_ht_red_grupo_teste(candidato):
    return bool(
        gol_2t_pos_ht_red_grupo_ativo()
        and candidato_gol_2t_pos_ht_red(candidato)
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == "gol_ft"
    )


def candidato_v2_controle_grupo_teste(candidato):
    """Reconhece apenas a V2 futura exata; V2 histórica e V3 não passam."""
    return bool(
        versao_exploracao_candidato(candidato)
        == VERSAO_EXPLORACAO_GOL_FT_V2_CONTROLE
        and candidato.get("mercado") == "gol_ft"
        and candidato.get("regra_versao") == REGRA_VERSAO_GOL_FT_V3
        and candidato.get("regra_fingerprint")
        == REGRA_FINGERPRINT_GOL_FT_V3
    )


def candidato_fusao_grupo_teste(candidato):
    return bool(
        versao_exploracao_candidato(candidato) == VERSAO_EXPERIMENTO_FUSAO
        and candidato.get("status") == "simulacao"
        and ((_features_candidato(candidato).get("fusao_fontes") or {}).get("valida") is True)
        and not ((_features_candidato(candidato).get("fusao_fontes") or {}).get("conflitos"))
    )


def candidato_gol_antecipado_grupo_teste(candidato):
    versao = versao_exploracao_candidato(candidato)
    mercado_esperado = (
        "gol_ht" if "gol-ht-" in str(versao or "") else "gol_ft"
    )
    features = _features_candidato(candidato)
    experimento = features.get("exploracao_sombra") or {}
    return bool(
        gols_antecipados_grupo_ativo()
        and versao in VERSOES_GOLS_ANTECIPADOS
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == mercado_esperado
        and metodo_antecipado_liberado(versao)
        and experimento.get("telegram_oficial") is False
        and experimento.get("aplicacao_automatica") is False
        and isinstance(features.get("gol_antecipado"), dict)
    )


def candidato_gol_capacidade_grupo_teste(candidato):
    # Chave de rollback explícita: só congela a V1 após confirmação do usuário.
    # A V2 nasce separada em sombra e nunca altera esta rota automaticamente.
    if GOLS_CAPACIDADE_V1_CONGELADA:
        return False
    versao = versao_exploracao_candidato(candidato)
    if (
        versao == VERSAO_GOL_HT_CAPACIDADE
        and not GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO
    ):
        return False
    if (
        versao == VERSAO_GOL_FT_CAPACIDADE
        and not GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO
    ):
        return False
    mercado_esperado = (
        "gol_ht" if "gol-ht-" in str(versao or "") else "gol_ft"
    )
    features = _features_candidato(candidato)
    experimento = features.get("exploracao_sombra") or {}
    capacidade = features.get("gol_capacidade_times")
    return bool(
        gols_capacidade_grupo_ativo()
        and versao in VERSOES_GOLS_CAPACIDADE
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == mercado_esperado
        and experimento.get("telegram_oficial") is False
        and experimento.get("aplicacao_automatica") is False
        and isinstance(capacidade, dict)
        and capacidade.get("linhagem_sha256")
    )


def candidato_gol_capacidade_contextual_v2_grupo_teste(
    candidato, caminho_estado_v2b_ft=None
):
    versao = versao_exploracao_candidato(candidato)
    mercado_esperado = (
        "gol_ht" if "gol-ht-" in str(versao or "") else "gol_ft"
    )
    features = _features_candidato(candidato)
    capacidade = features.get("gol_capacidade_contextual_v2")
    grupo_ativo = (
        GOLS_CAPACIDADE_CONTEXTUAL_V2_HT_GRUPO_ATIVO
        if mercado_esperado == "gol_ht"
        else (
            GOLS_CAPACIDADE_CONTEXTUAL_V2_FT_GRUPO_ATIVO
            and v2b_ft_grupo_liberado(caminho_estado_v2b_ft)
        )
    )
    return bool(
        grupo_ativo
        and versao in VERSOES_GOLS_CAPACIDADE_CONTEXTUAL_V2
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == mercado_esperado
        and isinstance(capacidade, dict)
        and capacidade.get("linhagem_sha256")
        and capacidade.get("probabilidade_estimada_nao_calibrada") is not None
    )


def candidato_gol_ht_00_min20_grupo_teste(candidato):
    features = _features_candidato(candidato)
    metodo = features.get("gol_ht_00_min20")
    return bool(
        GOL_HT_00_MIN20_GRUPO_ATIVO
        and versao_exploracao_candidato(candidato) == VERSAO_GOL_HT_00_MIN20
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == "gol_ht"
        and isinstance(metodo, dict)
        and metodo.get("linhagem_sha256")
    )


def candidato_gol_ft_tendencia_mais_um_grupo_teste(candidato):
    features = _features_candidato(candidato)
    metodo = features.get("gol_ft_tendencia_mais_um")
    return bool(
        GOL_FT_TENDENCIA_MAIS_UM_GRUPO_ATIVO
        and versao_exploracao_candidato(candidato)
        == VERSAO_GOL_FT_TENDENCIA_MAIS_UM
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == "gol_ft"
        and isinstance(metodo, dict)
        and metodo.get("linhagem_sha256")
    )


def candidato_top_criterio_grupo_teste(candidato):
    versao = versao_exploracao_candidato(candidato)
    mercado_esperado = {
        VERSAO_TOP_CRITERIO_HT: "gol_ht",
        VERSAO_TOP_CRITERIO_FT: "gol_ft",
    }.get(versao)
    features = _features_candidato(candidato)
    metodo = features.get("top_criterio_gols")
    return bool(
        TOP_CRITERIOS_GOLS_GRUPO_ATIVO
        and versao in VERSOES_TOP_CRITERIOS_GOLS
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == mercado_esperado
        and isinstance(metodo, dict)
        and metodo.get("linhagem_sha256") == LINHAGEM_TOP_CRITERIOS_GOLS
    )


def candidato_asiatico_ft_multiplos_grupo_teste(candidato):
    """Libera somente o asiático FT já medido, com rollback explícito."""
    features = _features_candidato(candidato)
    experimento = features.get("exploracao_sombra") or {}
    bloqueios_originais = set(experimento.get("bloqueios_originais") or [])
    return bool(
        ESCANTEIOS_FT_ASIATICO_MULTIPLOS_GRUPO_ATIVO
        and versao_exploracao_candidato(candidato)
        == VERSAO_EXPLORACAO_ASIATICA
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == "escanteios_ft_asiatico"
        and features.get("tipo_mercado_odds") == "asiatico"
        and experimento.get("aplicacao_automatica") is False
        and bloqueios_originais
        == {"linha_exige_multiplos_escanteios", "odd_ao_vivo_indisponivel"}
    )


def candidato_proximo_gol_balanceado_grupo_teste(candidato):
    """Libera o balanceado apenas como teste prospectivo identificado."""
    features = _features_candidato(candidato)
    experimento = features.get("exploracao_sombra") or {}
    balanceado = features.get("proximo_gol_balanceado_sombra") or {}
    return bool(
        PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO
        and proximo_gol_balanceado_grupo_liberado()
        and versao_exploracao_candidato(candidato)
        == VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA
        and candidato.get("regra_versao")
        == VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA
        and candidato.get("status") == "simulacao"
        and candidato.get("mercado") == "proximo_gol"
        and balanceado.get("elegivel") is True
        and experimento.get("grupo_teste") is True
        and experimento.get("telegram_oficial") is False
        and experimento.get("aplicacao_automatica") is False
    )


def candidato_experimento_grupo_teste(candidato):
    return bool(
        candidato_v2_controle_grupo_teste(candidato)
        or candidato_fusao_grupo_teste(candidato)
        or candidato_gol_antecipado_grupo_teste(candidato)
        or candidato_gol_capacidade_grupo_teste(candidato)
        or candidato_gol_capacidade_contextual_v2_grupo_teste(candidato)
        or candidato_gol_ht_00_min20_grupo_teste(candidato)
        or candidato_gol_2t_pos_ht_red_grupo_teste(candidato)
        or candidato_gol_ft_tendencia_mais_um_grupo_teste(candidato)
        or candidato_top_criterio_grupo_teste(candidato)
        or candidato_asiatico_ft_multiplos_grupo_teste(candidato)
        or candidato_proximo_gol_balanceado_grupo_teste(candidato)
    )


def motivo_suspensao_simulacao(candidato):
    tendencia_packball = (
        (_features_candidato(candidato).get("protecao_tendencias_packball") or {})
    )
    if (
        tendencia_packball
        and tendencia_packball.get("ativa") is True
        and tendencia_packball.get("aprovada") is False
        and not candidato_gol_ht_sem_tendencia_packball_liberado(candidato)
    ):
        return "protecao_tendencias_packball:" + str(
            tendencia_packball.get("motivo") or "reprovada"
        )
    protecao = (
        (_features_candidato(candidato).get("protecao_conversao_gols") or {})
    )
    if (
        protecao
        and protecao.get("ativa") is True
        and protecao.get("aprovada") is False
        and not candidato_gol_ht_historico_insuficiente_com_sot_liberado(
            candidato
        )
    ):
        return "protecao_conversao_gols:" + str(
            protecao.get("motivo") or "reprovada"
        )
    versao_exploracao = versao_exploracao_candidato(candidato)
    if (
        versao_exploracao in VERSOES_GOLS_ANTECIPADOS
        and not metodo_antecipado_liberado(versao_exploracao)
    ):
        return "circuit_breaker_gol_antecipado"
    filtro_ht_antecipado = avaliar_filtro_gol_ht_antecipado(candidato)
    if (
        filtro_ht_antecipado.get("aplicavel") is True
        and filtro_ht_antecipado.get("aprovada") is False
    ):
        return "filtro_gol_ht_antecipado_preciso:" + str(
            filtro_ht_antecipado.get("motivo") or "reprovado"
        )
    if (
        filtro_ht_antecipado.get("aplicavel") is True
        and filtro_ht_antecipado.get("motivo") != "desativado"
        and not filtro_gol_ht_preciso_liberado()
    ):
        return "circuit_breaker_filtro_gol_ht_antecipado_preciso"
    filtro_ft_antecipado = avaliar_filtro_gol_ft_antecipado(candidato)
    if (
        filtro_ft_antecipado.get("aplicavel") is True
        and filtro_ft_antecipado.get("aprovada") is False
    ):
        return "filtro_gol_ft_antecipado_preciso:" + str(
            filtro_ft_antecipado.get("motivo") or "reprovado"
        )
    if (
        filtro_ft_antecipado.get("aplicavel") is True
        and filtro_ft_antecipado.get("motivo") != "desativado"
        and not filtro_gol_ft_preciso_liberado()
    ):
        return "circuit_breaker_filtro_gol_ft_antecipado_preciso"
    if (
        versao_exploracao == VERSAO_PROXIMO_GOL_BALANCEADO_SOMBRA
        and not proximo_gol_balanceado_grupo_liberado()
    ):
        return "circuit_breaker_proximo_gol_balanceado"
    if versao_exploracao is not None:
        if (
            versao_exploracao in EXPERIMENTOS_SIMULACAO_GRUPO
            and candidato_experimento_grupo_teste(candidato)
        ):
            return None
        return "exploracao_sombra_fora_allowlist_simulacao_grupo"
    chave_regra = (
        candidato.get("mercado"),
        candidato.get("regra_versao"),
    )
    suspensao = REGRAS_SIMULACAO_SUSPENSAS.get(chave_regra)
    if suspensao is not None:
        return suspensao
    if chave_regra not in REGRAS_SIMULACAO_GRUPO:
        return "regra_fora_allowlist_simulacao_grupo"
    if candidato.get("mercado") != "proximo_gol":
        return None
    features = candidato.get("features") or {}
    if isinstance(features.get("filtro_proximo_gol_preciso"), dict):
        bloqueios = avaliar_criterios_precisos(candidato)
    else:
        bloqueios = []
        try:
            odd = float(candidato.get("odd"))
        except (TypeError, ValueError):
            odd = None
        try:
            minuto = float(features.get("minuto"))
        except (TypeError, ValueError):
            minuto = None
        if odd is None or not odd_elegivel(odd, obter_limites_risco()):
            return "filtro_proximo_gol_odd_fora_faixa_operacional"
        if odd >= PROXIMO_GOL_ODD_MAXIMA_EXCLUSIVA:
            bloqueios.append(MOTIVO_PROXIMO_GOL_ODD)
        if minuto is None or minuto > PROXIMO_GOL_MINUTO_MAXIMO_PROSPECTIVO:
            bloqueios.append(MOTIVO_PROXIMO_GOL_MINUTO)
    rotulos = {
        MOTIVO_PROXIMO_GOL_ODD: "filtro_proximo_gol_odd_fora_faixa_precisa",
        MOTIVO_PROXIMO_GOL_MINUTO: "filtro_proximo_gol_minuto_maximo_75",
        MOTIVO_PROXIMO_GOL_QUALIDADE: "filtro_proximo_gol_qualidade_abaixo_100",
        MOTIVO_PROXIMO_GOL_PRESSAO: "filtro_proximo_gol_pressao_pico_abaixo_70",
    }
    if bloqueios:
        return rotulos.get(bloqueios[0], bloqueios[0])
    return None


def motivo_circuit_breaker_escanteios_ft_asiatico(candidato):
    """Aplica o controle apenas ao mercado e versao prospectivos exatos."""
    if (
        candidato.get("mercado") == "escanteios_ft_asiatico"
        and candidato.get("regra_versao")
        == VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86
        and not escanteios_ft_asiatico_liberado()
    ):
        return "circuit_breaker_escanteios_ft_asiatico"
    return None


ROTULOS_MOTIVOS = {
    "alvo=mais_1_gol": "Objetivo analisado: mais 1 gol",
    "alvo=mais_1_escanteio": "Objetivo analisado: mais 1 escanteio",
    "minuto_na_faixa_da_regra": "Minuto dentro da faixa analisada",
    "mercado_ao_vivo_disponivel": "Mercado ao vivo disponível",
    "janela_primeiro_tempo": "Partida dentro da janela do 1º tempo",
    "odd_proximo_gol_disponivel": "Odd de próximo gol disponível",
    "mercado_exclusivo_primeiro_tempo": (
        "Mercado exclusivo do 1º tempo"
    ),
    "mercado_exclusivo_segundo_tempo": (
        "Mercado exclusivo do 2º tempo"
    ),
}

ROTULOS_METRICAS = {
    "chutes_5min": "Chutes nos últimos 5 minutos",
    "chutes_no_gol_total": "Chutes no alvo na partida",
    "pico_pressao_5min": "Pico de pressão nos últimos 5 minutos",
    "aceleracao_chutes": "Aceleração recente de chutes",
    "gols_atuais": "Gols atuais",
    "escanteios_5min": "Escanteios nos últimos 5 minutos",
    "media_pressao_5min": "Pressão média nos últimos 5 minutos",
    "lado_dominante": "Lado dominante",
}

ROTULOS_STATUS = {
    "FT": "Finalizado",
    "AET": "Finalizado após prorrogação",
    "PEN": "Finalizado após pênaltis",
    "HT": "Intervalo",
    "1H": "1º tempo",
    "2H": "2º tempo",
    "ET": "Prorrogação",
    "P": "Pênaltis",
    "PST": "Adiado",
    "CANC": "Cancelado",
    "ABD": "Abandonado",
    "SUSP": "Suspenso",
    "INT": "Interrompido",
    "NS": "Não iniciado",
}

ROTULOS_RESULTADOS = {
    "green": ("✅", "GREEN"),
    "half_green": ("✅", "MEIO GREEN"),
    "red": ("❌", "RED"),
    "half_red": ("❌", "MEIO RED"),
    "push": ("↩️", "DEVOLVIDA"),
    "void": ("⚪", "ANULADA"),
    "sem_dado": ("⚪", "SEM DADO SUFICIENTE"),
}


def _rotulo_mercado(mercado):
    return ROTULOS_MERCADOS.get(
        mercado, str(mercado or "Mercado não identificado").replace("_", " ")
    )


def _formatar_status(status):
    texto = str(status or "").strip()
    return ROTULOS_STATUS.get(texto.upper(), texto or "-")


def _formatar_valor(valor):
    return "-" if valor is None or valor == "" else str(valor)


def _formatar_odd(valor):
    if valor is None or valor == "":
        return "-"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return f"{numero:.2f}" if math.isfinite(numero) else str(valor)


def _rotulo_resultado(resultado):
    return ROTULOS_RESULTADOS.get(
        resultado, ("ℹ️", str(resultado or "não identificado").upper())
    )


def _rotulo_fonte(fonte):
    texto = str(fonte or "").strip()
    return {
        "packball": "PackBall",
        "api_football": "API-Football",
    }.get(texto.lower(), texto.replace("_", " ").title() or "Não registrada")


def _formatar_motivo(motivo):
    texto = str(motivo or "").strip()
    if not texto:
        return None
    if texto in ROTULOS_MOTIVOS:
        return ROTULOS_MOTIVOS[texto]
    if "=" not in texto:
        return texto.replace("_", " ").capitalize()

    chave, valor = texto.split("=", 1)
    if chave == "lado_dominante":
        valor = {
            "casa": "mandante",
            "fora": "visitante",
        }.get(valor, valor)
    if chave in ("pico_pressao_5min", "media_pressao_5min"):
        valor = f"{valor}/100"
    if chave.startswith("odd_over_"):
        direcao = chave.removeprefix("odd_over_").replace("_", " ")
        return f"Movimento da odd Over: {direcao} ({valor})"

    rotulo = ROTULOS_METRICAS.get(
        chave, chave.replace("_", " ").capitalize()
    )
    return f"{rotulo}: {valor}"


def _formatar_motivos(motivos):
    linhas = [
        texto for texto in (
            _formatar_motivo(motivo) for motivo in (motivos or [])
        )
        if texto
    ]
    return "\n".join(f"• {texto}" for texto in linhas)


def _rotulo_regra_simulacao(candidato):
    if candidato_v2_controle_grupo_teste(candidato):
        return "Gol FT V2-controle — grupo de teste"
    if candidato_proximo_gol_balanceado_grupo_teste(candidato):
        return "Próximo Gol balanceado — grupo de teste"
    return candidato.get("regra_versao") or "-"


def _motivos_visiveis_simulacao(candidato):
    motivos = list(candidato.get("motivos") or [])
    if not candidato_v2_controle_grupo_teste(candidato):
        return motivos
    prefixos_internos = (
        "exploracao_sombra=",
        "controle_futuro_fiel_v2_",
    )
    return [
        motivo for motivo in motivos
        if motivo != "nao_enviar_telegram"
        and not str(motivo).startswith(prefixos_internos)
    ]


def _transporte_padrao(url, dados):
    requisicao = Request(
        url,
        data=urlencode(dados).encode("utf-8"),
        method="POST",
    )
    try:
        with urlopen(requisicao, timeout=15) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except HTTPError as erro:
        try:
            payload = json.loads(erro.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise
        descricao = str(payload.get("description") or "").casefold()
        mensagem_id = dados.get("message_id")
        if (
            int(getattr(erro, "code", 0) or 0) == 400
            and "message is not modified" in descricao
            and str(mensagem_id or "").isdigit()
            and int(mensagem_id) > 0
        ):
            return {
                "ok": True,
                "result": {"message_id": int(mensagem_id)},
                "edicao_idempotente": True,
            }
        raise


class AlertasTelegram:
    def __init__(
        self,
        banco,
        transporte=None,
        validador_operacao_oficial=None,
    ):
        self.banco = banco
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.canais = {
            "gol_ft": os.getenv("TELEGRAM_CHAT_ID_GOLS")
            or os.getenv("TELEGRAM_CHAT_ID"),
            "gol_ht": os.getenv("TELEGRAM_CHAT_ID_GOLS")
            or os.getenv("TELEGRAM_CHAT_ID"),
            "proximo_gol": os.getenv("TELEGRAM_CHAT_ID_GOLS")
            or os.getenv("TELEGRAM_CHAT_ID"),
            "proximo_escanteio": os.getenv(
                "TELEGRAM_CHAT_ID_ESCANTEIOS"
            ),
            "escanteios_ft_asiatico": os.getenv(
                "TELEGRAM_CHAT_ID_ESCANTEIOS"
            ),
            "escanteios_1t": os.getenv("TELEGRAM_CHAT_ID_ESCANTEIOS"),
            "escanteios_2t": os.getenv("TELEGRAM_CHAT_ID_ESCANTEIOS"),
        }
        self.transporte = transporte or _transporte_padrao
        self.validador_operacao_oficial = validador_operacao_oficial
        self.calibrador = CalibradorBacktest(banco)
        self.avaliador_green_antecipado = AvaliadorBacktest(banco)
        self.modo_teste = os.getenv("SINAIS_TESTE_ATIVO", "0") == "1"
        self.canal_teste = os.getenv("TELEGRAM_CHAT_ID_TESTE")
        self.limite_diario_teste = int(
            os.getenv("LIMITE_DIARIO_SINAIS_TESTE", "30")
        )
        self.limite_global_teste = int(
            os.getenv("LIMITE_GLOBAL_SINAIS_TESTE", "45")
        )
        self.pontuacao_minima_teste = float(
            os.getenv("PONTUACAO_MINIMA_SINAL_TESTE", "70")
        )
        # Próximo Gol já possui uma barreira própria mais forte (qualidade
        # completa, pressão, conversão histórica, tendência e odd). Repetir o
        # corte global de 75 no gateway eliminava oportunidades que haviam
        # passado todas essas proteções. O limite isolado aumenta somente a
        # coleta prospectiva desse mercado, sem afrouxar os demais sinais.
        self.pontuacao_minima_proximo_gol_teste = float(os.getenv(
            "PONTUACAO_MINIMA_PROXIMO_GOL_TESTE",
            str(self.pontuacao_minima_teste),
        ))
        self.qualidade_minima_teste = float(
            os.getenv("QUALIDADE_MINIMA_SINAL_TESTE", "0")
        )
        self.experimento_filtro = None
        if self.modo_teste:
            self.experimento_filtro = registrar_ou_obter_experimento_filtro(
                self.banco.conexao,
                VERSAO_REGRAS,
                self.pontuacao_minima_teste,
                self.qualidade_minima_teste,
            )
        limites = obter_limites_risco()
        self.limites_risco = limites
        self.limite_diario = limites.limite_diario_sinais
        self.odd_minima = limites.odd_minima
        self.odd_maxima = limites.odd_maxima
        self.limite_exposicao = limites.limite_exposicao_diaria
        self.limite_reds_consecutivos = (
            limites.limite_reds_consecutivos_oficiais
        )
        self.limite_perda_diaria = limites.limite_perda_diaria_oficial

    def avaliar_e_enviar(
        self, sinal_id, candidato, jogo, reenvio_controlado=False,
        reserva_reenvio_token=None,
    ):
        metodo_v2 = candidato_v2_controle_grupo_teste(candidato)
        metodo_experimental = candidato_experimento_grupo_teste(candidato)
        if (
            candidato.get("status") != "aprovado"
            and not (self.modo_teste and metodo_experimental)
        ):
            return "rejeitado"
        odd = candidato.get("odd")
        if odd is None:
            return "odd_indisponivel"
        if not odd_elegivel(odd, self.limites_risco):
            return "odd_fora_da_faixa"
        motivo = motivo_circuit_breaker_escanteios_ft_asiatico(candidato)
        if motivo is not None:
            self.banco.registrar_entrega_alerta(
                sinal_id, "gateway:validacao", "filtrado", motivo
            )
            return motivo
        probabilidade = candidato.get("probabilidade_calibrada")

        # A saúde operacional protege tanto sinais oficiais quanto
        # simulações. Caso contrário, uma queda das fontes ainda poderia
        # alimentar o placar de Green/Red pelo caminho de teste.
        estado_operacional = self._validar_operacao_oficial(candidato)
        if estado_operacional is not None:
            canal_gateway = (
                "gateway:teste"
                if probabilidade is None and self.modo_teste
                else "gateway:oficial"
            )
            self.banco.registrar_entrega_alerta(
                sinal_id,
                canal_gateway,
                "bloqueado",
                estado_operacional,
            )
            return estado_operacional

        if probabilidade is None:
            if self.modo_teste:
                return self._enviar_teste(
                    sinal_id,
                    candidato,
                    jogo,
                    reenvio_controlado=reenvio_controlado,
                    reserva_reenvio_token=reserva_reenvio_token,
                )
            return "sem_calibracao"

        estado_oficial = self._revalidar_entrega_oficial(
            sinal_id, candidato
        )
        if estado_oficial is not None:
            if estado_oficial != "sinal_inexistente":
                self.banco.registrar_entrega_alerta(
                    sinal_id,
                    "gateway:oficial",
                    "bloqueado",
                    estado_oficial,
                )
            return estado_oficial
        valor_mercado = anexar_valor_mercado(candidato)
        if not valor_mercado["aprovado"]:
            motivo_valor = {
                "referencia_sem_vig_ausente": (
                    "referencia_mercado_sem_vig_ausente"
                ),
                "vantagem_sem_vig_abaixo_minimo": (
                    "vantagem_mercado_sem_vig_insuficiente"
                ),
                "margem_bookmaker_incoerente": (
                    "referencia_mercado_sem_vig_incoerente"
                ),
            }.get(
                valor_mercado.get("motivo"),
                "valor_esperado_conservador_insuficiente",
            )
            return self._bloquear_pre_envio(
                sinal_id,
                motivo_valor,
                candidato,
            )
        canal = self.canais.get(candidato.get("mercado"))
        if not canal:
            return "canal_nao_configurado"
        if not self.token:
            return "token_nao_configurado"
        if float(probabilidade) < PROBABILIDADE_MINIMA:
            canal_aviso = f"{canal}:insuficiente"
            if self.banco.alerta_ja_entregue(sinal_id, canal_aviso):
                return "duplicado"
            if self.banco.alerta_recente_mesmo_mercado(sinal_id):
                return "duplicado_recente"
            estado_pre_envio = self._revalidar_pre_envio(
                sinal_id, candidato, jogo
            )
            if estado_pre_envio is not None:
                return estado_pre_envio
            estado_reserva, token_reserva = self._reservar_entrega_pre_post(
                sinal_id,
                canal_aviso,
                reenvio_controlado=reenvio_controlado,
                reserva_reenvio_token=reserva_reenvio_token,
            )
            if estado_reserva is not None:
                return estado_reserva
            try:
                resposta = self.transporte(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    {
                        "chat_id": canal,
                        "text": self._mensagem_insuficiente(
                            candidato, jogo
                        ),
                        "disable_web_page_preview": "true",
                    },
                )
                prova = self._validar_confirmacao_telegram(resposta, canal)
            except Exception as erro:
                self.banco.finalizar_notificacao_alerta(
                    sinal_id, canal_aviso, token_reserva, "incerto", str(erro)
                )
                return "incerto"
            if not self.banco.finalizar_notificacao_alerta(
                sinal_id, canal_aviso, token_reserva, "entregue", **prova
            ):
                # O Telegram confirmou o POST. Se o claim tiver mudado por
                # uma anomalia concorrente, preserva a prova positiva em uma
                # linha final para nunca tratar a mensagem como reenviavel.
                self.banco.registrar_entrega_alerta(
                    sinal_id, canal_aviso, "entregue", **prova
                )
            return "aviso_insuficiente"
        if self.banco.alerta_oficial_ja_entregue_no_grupo_independente(
            sinal_id
        ):
            return "duplicado_grupo_oficial"
        if self.banco.alerta_ja_entregue(sinal_id, canal):
            return "duplicado"
        if self.banco.alerta_recente_mesmo_mercado(sinal_id):
            return "duplicado_recente"
        if self.banco.possui_entrega_oficial_incerta(
            excluir_sinal_id=(
                sinal_id if reenvio_controlado else None
            )
        ):
            return "circuit_breaker_entrega_incerta"
        risco_oficial = self.banco.resumir_risco_alertas_oficiais()
        if (
            risco_oficial["reds_consecutivos_24h"]
            >= self.limite_reds_consecutivos
        ):
            return "circuit_breaker_reds"
        if risco_oficial["perda_realizada_hoje"] >= self.limite_perda_diaria:
            return "circuit_breaker_perda_diaria"
        if self.banco.total_alertas_entregues_hoje() >= self.limite_diario:
            return "limite_diario"
        if (
            self.banco.exposicao_alertas_hoje(EXPOSICAO_POR_SINAL)
            + EXPOSICAO_POR_SINAL
            > self.limite_exposicao
        ):
            return "limite_exposicao"

        estado_pre_envio = self._revalidar_pre_envio(
            sinal_id, candidato, jogo
        )
        if estado_pre_envio is not None:
            return estado_pre_envio

        mensagem = self._mensagem(candidato, jogo)
        estado_reserva, token_reserva = self._reservar_entrega_pre_post(
            sinal_id,
            canal,
            reenvio_controlado=reenvio_controlado,
            reserva_reenvio_token=reserva_reenvio_token,
        )
        if estado_reserva is not None:
            return estado_reserva
        try:
            resposta = self.transporte(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                {
                    "chat_id": canal,
                    "text": mensagem,
                    "disable_web_page_preview": "true",
                },
            )
            prova = self._validar_confirmacao_telegram(resposta, canal)
        except Exception as erro:
            self.banco.finalizar_notificacao_alerta(
                sinal_id, canal, token_reserva, "incerto", str(erro)
            )
            return "incerto"

        if not self.banco.finalizar_notificacao_alerta(
            sinal_id, canal, token_reserva, "entregue", **prova
        ):
            self.banco.registrar_entrega_alerta(
                sinal_id, canal, "entregue", **prova
            )
        return "entregue"

    def enviar_acompanhamento_odd(self, sinal_id, candidato, jogo):
        """Inscreve na fila rápida; o aviso público é opcional."""
        if os.getenv("AVISO_AGUARDAR_ODD_ATIVO", "0") != "1":
            return "acompanhamento_odd_desativado"
        acompanhamento = (
            (candidato.get("features") or {}).get("acompanhamento_odd")
            or {}
        )
        if acompanhamento.get("elegivel_aviso") is not True:
            return "acompanhamento_odd_nao_elegivel"
        canal = self.canais.get(candidato.get("mercado"))
        if not canal:
            return "canal_nao_configurado"
        if not self.token:
            return "token_nao_configurado"
        canal_registro = f"{canal}:aguardar_odd"
        if self.banco.acompanhamento_odd_ja_entregue_na_partida(
            sinal_id, canal_registro
        ):
            return "acompanhamento_odd_duplicado"
        if os.getenv("ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS", "1") != "1":
            # Este estado não é uma entrega, não tem mensagem/prova Telegram
            # e não entra em resultados/ROI oficial. Mantém apenas a origem
            # persistida que a fila rápida usa até confirmar o preço-alvo.
            self.banco.registrar_entrega_alerta(
                sinal_id, canal_registro, "monitoramento_silencioso",
                "aviso_suprimido_por_preferencia",
            )
            return "acompanhamento_odd_silencioso"
        estado_operacional = self._validar_operacao_oficial()
        if estado_operacional is not None:
            self.banco.registrar_entrega_alerta(
                sinal_id,
                "gateway:aguardar_odd",
                "bloqueado",
                estado_operacional,
            )
            return estado_operacional
        try:
            resposta = self.transporte(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                {
                    "chat_id": canal,
                    "text": self._mensagem_acompanhamento_odd(
                        candidato, jogo
                    ),
                    "disable_web_page_preview": "true",
                },
            )
            prova = self._validar_confirmacao_telegram(resposta, canal)
        except Exception as erro:
            self.banco.registrar_entrega_alerta(
                sinal_id, canal_registro, "incerto", str(erro)
            )
            return "incerto"
        self.banco.registrar_entrega_alerta(
            sinal_id, canal_registro, "entregue", **prova
        )
        return "acompanhamento_odd_entregue"

    def _desfecho_acompanhamento_odd(self, item):
        historico = self.banco.historico_acompanhamento_odd(
            item["sinal_id"]
        )
        desfecho = avaliar_resultado_acompanhamento_odd(item, historico)
        if desfecho is None:
            return None
        ultima_odd = self.banco.ultima_odd_acompanhamento_odd(
            item["sinal_id"], desfecho["snapshot_id"]
        )
        canal_origem = str(item["canal_origem"])
        sufixo = ":aguardar_odd"
        canal_base = (
            canal_origem[:-len(sufixo)]
            if canal_origem.endswith(sufixo) else canal_origem
        )
        oficial = self.banco.entrada_oficial_apos_acompanhamento(
            item["sinal_id"], canal_base
        )
        return {
            **desfecho,
            "ultima_odd": ultima_odd,
            "canal_base": canal_base,
            "entrada_oficial": dict(oficial) if oficial else None,
        }

    def atualizar_acompanhamentos_odd(self, limite=50):
        """Edita observacoes concluidas sem mistura-las ao ROI oficial."""
        resumo = {
            "consultados": 0, "conclusivos": 0, "entregues": 0,
            "erros": 0, "bloqueados": 0,
        }
        if not self.token:
            return resumo
        itens = [
            dict(item)
            for item in self.banco.acompanhamentos_odd_pendentes(limite)
        ]
        resumo["consultados"] = len(itens)
        conclusivos = []
        for item in itens:
            desfecho = self._desfecho_acompanhamento_odd(item)
            if desfecho is not None:
                conclusivos.append((item, desfecho))
        resumo["conclusivos"] = len(conclusivos)
        para_edicao = []
        avisos_ativos = (
            os.getenv("ACOMPANHAMENTO_ODD_TELEGRAM_AVISOS", "1") == "1"
        )
        for item, desfecho in conclusivos:
            if not avisos_ativos or not item.get("mensagem_id_origem"):
                self.banco.registrar_entrega_alerta(
                    item["sinal_id"],
                    f"{item['canal_origem']}:monitoramento_final",
                    "suprimido", "resultado_hipotetico_silencioso",
                    confirmacao={
                        "sem_envio": True,
                        "resultado_monitoramento": desfecho["resultado"],
                        "snapshot_id": desfecho["snapshot_id"],
                    },
                )
                resumo["suprimidos"] = resumo.get("suprimidos", 0) + 1
            else:
                para_edicao.append((item, desfecho))
        conclusivos = para_edicao
        bloqueio = (
            self._validar_operacao_oficial() if conclusivos else None
        )
        if bloqueio is not None:
            resumo["bloqueados"] = len(conclusivos)
            resumo["motivo_bloqueio"] = bloqueio
            return resumo

        for item, desfecho in conclusivos:
            sinal_id = item["sinal_id"]
            canal_origem = item["canal_origem"]
            canal_registro = f"{canal_origem}:monitoramento_final"
            reserva = self.banco.reservar_resultado_acompanhamento_odd(
                sinal_id, canal_origem
            )
            if not reserva:
                continue
            if not self.banco.reserva_resultado_acompanhamento_odd_valida(
                sinal_id, canal_origem, reserva
            ):
                self.banco.finalizar_notificacao_alerta(
                    sinal_id, canal_registro, reserva, "cancelado",
                    "reserva_invalida_antes_da_edicao",
                )
                resumo["bloqueados"] += 1
                continue
            atual = self._desfecho_acompanhamento_odd(item)
            identidade = lambda valor: (
                valor.get("resultado"), valor.get("snapshot_id")
            ) if valor else None
            if identidade(atual) != identidade(desfecho):
                self.banco.finalizar_notificacao_alerta(
                    sinal_id, canal_registro, reserva, "cancelado",
                    "desfecho_alterado_antes_da_edicao",
                )
                resumo["bloqueados"] += 1
                continue
            try:
                resposta = self.transporte(
                    f"https://api.telegram.org/bot{self.token}/editMessageText",
                    {
                        "chat_id": atual["canal_base"],
                        "message_id": int(item["mensagem_id_origem"]),
                        "text": self._mensagem_resultado_acompanhamento_odd(
                            item, atual
                        ),
                        "disable_web_page_preview": "true",
                    },
                )
                self._validar_confirmacao_telegram(
                    resposta, atual["canal_base"]
                )
                prova = {
                    "provedor": "telegram",
                    "provedor_destino_id": str(atual["canal_base"]),
                    "provedor_mensagem_id": None,
                    "confirmacao": {
                        "ok": True,
                        "provedor": "telegram",
                        "edicao": True,
                        "message_id_origem": int(
                            item["mensagem_id_origem"]
                        ),
                        "resultado_monitoramento": atual["resultado"],
                        "snapshot_id": atual["snapshot_id"],
                    },
                }
            except Exception as erro:
                self.banco.finalizar_notificacao_alerta(
                    sinal_id, canal_registro, reserva, "incerto", str(erro)
                )
                resumo["erros"] += 1
                continue
            if self.banco.finalizar_notificacao_alerta(
                sinal_id, canal_registro, reserva, "entregue", **prova
            ):
                resumo["entregues"] += 1
            else:
                resumo["erros"] += 1
        return resumo

    def _validar_operacao_oficial(self, candidato=None):
        if not callable(self.validador_operacao_oficial):
            return "gate_operacao_oficial_indisponivel"
        try:
            validador = self.validador_operacao_oficial
            aceita_candidato = False
            if candidato is not None:
                try:
                    assinatura = inspect.signature(validador)
                    aceita_candidato = (
                        "candidato" in assinatura.parameters
                        or any(
                            parametro.kind
                            == inspect.Parameter.VAR_KEYWORD
                            for parametro in assinatura.parameters.values()
                        )
                    )
                except (TypeError, ValueError):
                    aceita_candidato = False
            resultado = (
                validador(candidato=candidato)
                if aceita_candidato else validador()
            )
        except Exception:
            return "gate_operacao_oficial_falhou"
        if isinstance(resultado, dict):
            apto = resultado.get("apto") is True
            estado = str(resultado.get("estado") or "").strip().lower()
            motivo = str(resultado.get("motivo") or "").strip().lower()
        else:
            apto = resultado is True
            estado = ""
            motivo = ""
        if apto:
            return None
        if motivo == "cotacao_oficial_nao_executavel":
            return "cotacao_oficial_nao_executavel"
        if motivo == "edge_portfolio_nao_comprovado":
            return "edge_portfolio_nao_comprovado"
        if estado == "inicializando":
            return "operacao_oficial_inicializando"
        if estado == "degradado":
            return "operacao_oficial_degradada"
        return "operacao_oficial_bloqueada"

    @staticmethod
    def _validar_confirmacao_telegram(resposta, destino):
        if not isinstance(resposta, dict) or resposta.get("ok") is not True:
            raise RuntimeError("Telegram não confirmou a entrega.")
        resultado = resposta.get("result")
        if not isinstance(resultado, dict):
            raise RuntimeError("Telegram confirmou sem retornar a mensagem.")
        mensagem_id = resultado.get("message_id")
        if isinstance(mensagem_id, bool):
            mensagem_id = None
        try:
            mensagem_id = int(mensagem_id)
        except (TypeError, ValueError):
            mensagem_id = 0
        if mensagem_id <= 0:
            raise RuntimeError("Telegram confirmou sem message_id válido.")
        destino = str(destino or "").strip()
        if not destino:
            raise RuntimeError("Destino Telegram ausente na confirmação.")
        confirmacao = {
            "provedor": "telegram",
            "ok": True,
            "message_id": mensagem_id,
        }
        data_mensagem = resultado.get("date")
        if isinstance(data_mensagem, int) and not isinstance(
            data_mensagem, bool
        ):
            confirmacao["date"] = data_mensagem
        return {
            "provedor": "telegram",
            "provedor_destino_id": destino,
            "provedor_mensagem_id": str(mensagem_id),
            "confirmacao": confirmacao,
        }

    @staticmethod
    def _numeros_iguais(primeiro, segundo):
        if primeiro is None or segundo is None:
            return primeiro is None and segundo is None
        try:
            return math.isclose(
                float(primeiro), float(segundo), rel_tol=0.0, abs_tol=0.000001
            )
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _valores_iguais(primeiro, segundo):
        if AlertasTelegram._numeros_iguais(primeiro, segundo):
            return True
        return " ".join(str(primeiro or "").split()).casefold() == (
            " ".join(str(segundo or "").split()).casefold()
        )

    @staticmethod
    def _interpretar_instante(valor):
        if isinstance(valor, datetime):
            return valor
        if not isinstance(valor, str) or not valor.strip():
            return None
        texto = valor.strip()
        if texto.endswith("Z"):
            texto = f"{texto[:-1]}+00:00"
        try:
            return datetime.fromisoformat(texto)
        except ValueError:
            return None

    @classmethod
    def _idade_instante(cls, valor, agora):
        instante = cls._interpretar_instante(valor)
        if instante is None:
            return None
        if instante.tzinfo is not None:
            instante = instante.astimezone().replace(tzinfo=None)
        agora = agora.replace(tzinfo=None)
        idade = (agora - instante).total_seconds()
        return idade if idade >= -1.0 else None

    @staticmethod
    def _minuto_status(valor):
        texto = str(valor or "").strip().casefold()
        if not texto or texto == "ht" or "intervalo" in texto:
            return None
        correspondencia = re.search(r"(\d{1,3})(?:\s*\+\s*(\d{1,2}))?", texto)
        if correspondencia is None:
            return None
        return int(correspondencia.group(1)) + int(
            correspondencia.group(2) or 0
        )

    @staticmethod
    def _status_nao_operacional(valor):
        texto = " ".join(str(valor or "").split()).casefold()
        return not texto or any(item in texto for item in (
            "finalizado", "encerrado", "adiado", "cancelado",
            "suspenso", "intervalo", "abandonado",
        )) or texto in {"ft", "aet", "pen", "ht", "pst", "canc"}

    @staticmethod
    def _minuto_maximo_pre_envio(candidato):
        if candidato_v2_controle_grupo_teste(candidato):
            return 82
        if candidato_gol_capacidade_grupo_teste(candidato):
            return 28 if candidato.get("mercado") == "gol_ht" else 82
        chave = (
            candidato.get("mercado"), candidato.get("regra_versao")
        )
        limite = {
            (
                "proximo_gol",
                VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            ): PROXIMO_GOL_MINUTO_MAXIMO_PROSPECTIVO,
            (
                "proximo_escanteio",
                VERSAO_PROXIMO_ESCANTEIO_MAX_86,
            ): 86,
            (
                "escanteios_ft_asiatico",
                VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
            ): 86,
        }.get(chave)
        if limite is not None:
            return limite
        if candidato_fusao_grupo_teste(candidato):
            return {"gol_ft": 82, "gol_ht": 28}.get(
                candidato.get("mercado")
            )
        return None

    def _bloquear_pre_envio(self, sinal_id, motivo, candidato=None):
        # A V2 continua sendo uma coorte de pesquisa liquidavel. Se a leitura
        # envelhecer antes do Telegram, bloqueamos apenas a entrega; nao
        # removemos o caso da amostra prospectiva.
        if candidato_experimento_grupo_teste(candidato or {}):
            self.banco.registrar_entrega_alerta(
                sinal_id, "gateway:pre_envio", "filtrado", motivo
            )
            return motivo
        expirado = self.banco.expirar_sinal_pre_envio(sinal_id, motivo)
        if expirado:
            self.banco.registrar_entrega_alerta(
                sinal_id, "gateway:pre_envio", "filtrado", motivo
            )
            return motivo

        # O estado pode ter mudado entre a leitura e o UPDATE condicional.
        # Nunca declare uma expiração que o SQLite não confirmou.
        contexto = self.banco.carregar_contexto_pre_envio(sinal_id)
        if contexto is None:
            estado = "revalidacao_pre_envio_sinal_inexistente"
        elif contexto.get("entrega_ja_entregue"):
            estado = "revalidacao_pre_envio_ja_entregue"
        elif contexto.get("resolvido"):
            estado = "revalidacao_pre_envio_sinal_resolvido"
        elif contexto["sinal"].get("status") != "aprovado":
            estado = "revalidacao_pre_envio_estado_persistido_invalido"
        else:
            estado = "revalidacao_pre_envio_expiracao_concorrente"
        self.banco.registrar_entrega_alerta(
            sinal_id, "gateway:pre_envio", "bloqueado", estado
        )
        return estado

    def _aplicar_autoridade_pre_envio(
        self, candidato, jogo, sinal, origem, partida
    ):
        """Substitui os campos da mensagem pela evidência salva no SQLite."""
        features = dict(sinal.get("features") or {})
        candidato.update({
            "mercado": sinal.get("mercado"),
            "linha": sinal.get("linha"),
            "odd": sinal.get("odd"),
            "pontuacao_tecnica": sinal.get("pontuacao_tecnica"),
            "probabilidade_calibrada": sinal.get(
                "probabilidade_calibrada"
            ),
            "regra_versao": sinal.get("regra_versao"),
            "regra_fingerprint": sinal.get("regra_fingerprint"),
            "motivos": list(sinal.get("motivos") or []),
            "features": features,
            "qualidade_dados": (
                origem.get("qualidade_dados")
                if origem.get("qualidade_dados") is not None
                else features.get("qualidade_dados", 0)
            ),
            "status": sinal.get("status"),
        })
        for chave in (
            "fonte_odds", "bookmaker_odds", "tipo_mercado_odds",
            "coletado_em_odds", "idade_odds_segundos", "odds_cache",
        ):
            candidato[chave] = features.get(chave)
        jogo.update({
            "url": partida.get("packball_url"),
            "mandante": partida.get("mandante"),
            "visitante": partida.get("visitante"),
            "pais": partida.get("pais"),
            "liga": partida.get("liga"),
            "placar": origem.get("placar"),
            "status": origem.get("status"),
        })

    def _revalidar_pre_envio(self, sinal_id, candidato, jogo, agora=None):
        """Confirma no SQLite que a leitura ainda e a mesma e esta fresca."""
        contexto = self.banco.carregar_contexto_pre_envio(sinal_id)
        if contexto is None:
            return "revalidacao_pre_envio_sinal_inexistente"
        sinal = contexto["sinal"]
        origem = contexto.get("snapshot_origem")
        recente = contexto.get("snapshot_mais_recente")
        partida = contexto.get("partida")
        if contexto.get("resolvido"):
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_sinal_resolvido", candidato
            )
        if contexto.get("entrega_ja_entregue"):
            return "revalidacao_pre_envio_ja_entregue"
        metodo_v2 = candidato_experimento_grupo_teste(candidato)
        if (
            (
                sinal.get("status") != "aprovado"
                and not (metodo_v2 and sinal.get("status") == "simulacao")
            )
            or not origem or not recente or not partida
            or int(origem.get("partida_id") or 0)
            != int(sinal.get("partida_id") or 0)
            or int(recente.get("partida_id") or 0)
            != int(sinal.get("partida_id") or 0)
            or int(partida.get("id") or 0)
            != int(sinal.get("partida_id") or 0)
        ):
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_estado_persistido_invalido",
                candidato,
            )
        if int(origem["id"]) != int(recente["id"]):
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_snapshot_substituido", candidato
            )
        if (
            sinal.get("mercado") != candidato.get("mercado")
            or sinal.get("regra_versao") != candidato.get("regra_versao")
            or sinal.get("regra_fingerprint")
            != candidato.get("regra_fingerprint")
            or not self._valores_iguais(
                sinal.get("linha"), candidato.get("linha")
            )
            or not self._numeros_iguais(
                sinal.get("odd"), candidato.get("odd")
            )
            or not self._numeros_iguais(
                sinal.get("pontuacao_tecnica"),
                candidato.get("pontuacao_tecnica"),
            )
            or not self._numeros_iguais(
                sinal.get("probabilidade_calibrada"),
                candidato.get("probabilidade_calibrada"),
            )
        ):
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_identidade_divergente", candidato
            )
        for persistido, recebido in (
            (partida.get("packball_url"), jogo.get("url")),
            (partida.get("mandante"), jogo.get("mandante")),
            (partida.get("visitante"), jogo.get("visitante")),
        ):
            if (
                str(persistido or "").strip()
                and str(recebido or "").strip()
                and not self._valores_iguais(persistido, recebido)
            ):
                return self._bloquear_pre_envio(
                    sinal_id,
                    "revalidacao_pre_envio_identidade_partida_divergente",
                    candidato,
                )
        if (
            not self._valores_iguais(origem.get("placar"), jogo.get("placar"))
            or not self._valores_iguais(
                origem.get("status"), jogo.get("status")
            )
        ):
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_estado_divergente", candidato
            )
        if self._status_nao_operacional(origem.get("status")):
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_partida_nao_operacional", candidato
            )

        features = sinal.get("features") or {}
        tecnica_id = (features.get("acompanhamento_odd_rapido") or {}).get(
            "leitura_tecnica_sinal_id"
        )
        if tecnica_id is not None:
            verificar = getattr(self.banco, "acompanhamento_odd_leitura_vigente", None)
            if not callable(verificar) or not verificar(tecnica_id):
                return self._bloquear_pre_envio(
                    sinal_id, "revalidacao_pre_envio_analise_acompanhamento_substituida",
                    candidato,
                )
        agora = agora or datetime.now()
        try:
            auditoria_historico = avaliar_historico_envio(
                getattr(self.banco, "conexao", None), sinal, origem, agora,
            )
        except Exception as erro:
            auditoria_historico = {
                "aprovada": False, "motivo": "historico_verificacao_falhou",
                "erro_tipo": type(erro).__name__,
            }
        if not auditoria_historico["aprovada"]:
            motivo = "revalidacao_pre_envio_" + auditoria_historico["motivo"]
            self.banco.registrar_entrega_alerta(
                sinal_id, "gateway:validade_historico", "bloqueado",
                json.dumps(auditoria_historico, ensure_ascii=False, sort_keys=True),
            )
            return self._bloquear_pre_envio(sinal_id, motivo, candidato)
        idade_decisao = self._idade_instante(features.get("decisao_em"), agora)
        idade_estado = self._idade_instante(
            features.get("estado_observado_em"), agora
        )
        if idade_decisao is None or idade_estado is None:
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_timestamp_indeterminado",
                candidato,
            )
        if max(idade_decisao, idade_estado) > SLA_PRE_ENVIO_SEGUNDOS:
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_leitura_expirada", candidato
            )
        try:
            idade_odds = float(features.get("idade_odds_segundos"))
        except (TypeError, ValueError):
            idade_odds = None
        if idade_odds is None or not math.isfinite(idade_odds) or idade_odds < 0:
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_frescor_odds_indeterminado",
                candidato,
            )
        idade_maxima_odds = (
            ODDS_MAX_IDADE_ASIATICO_SEGUNDOS
            if sinal.get("mercado") in {
                "escanteios_ft_asiatico",
                "escanteios_1t_asiatico",
                "escanteios_2t_asiatico",
            }
            else ODDS_MAX_IDADE_SEGUNDOS
        )
        if idade_odds + idade_decisao > idade_maxima_odds:
            return self._bloquear_pre_envio(
                sinal_id, "revalidacao_pre_envio_odds_expiradas", candidato
            )
        minuto_maximo = self._minuto_maximo_pre_envio(candidato)
        if minuto_maximo is not None:
            minuto = features.get("minuto")
            try:
                minuto = float(minuto)
            except (TypeError, ValueError):
                minuto = None
            minuto_status = self._minuto_status(origem.get("status"))
            if minuto is None or minuto_status is None:
                return self._bloquear_pre_envio(
                    sinal_id, "revalidacao_pre_envio_minuto_indeterminado",
                    candidato,
                )
            minuto_origem = max(minuto, float(minuto_status))
            minuto_projetado = minuto_origem + math.ceil(idade_estado / 60.0)
            if minuto_projetado > float(minuto_maximo):
                return self._bloquear_pre_envio(
                    sinal_id, "revalidacao_pre_envio_minuto_excedido", candidato
                )
        auditoria_chutes = avaliar_chutes_ht(sinal, origem, agora)
        if auditoria_chutes["aplicavel"]:
            self.banco.registrar_entrega_alerta(
                sinal_id, "gateway:ht_chutes_recentes",
                "aprovado" if auditoria_chutes["aprovada"] else "bloqueado",
                json.dumps(auditoria_chutes, ensure_ascii=False, sort_keys=True),
            )
            if not auditoria_chutes["aprovada"]:
                return self._bloquear_pre_envio(
                    sinal_id, "revalidacao_pre_envio_" + auditoria_chutes["motivo"],
                    candidato,
                )
        self._aplicar_autoridade_pre_envio(
            candidato, jogo, sinal, origem, partida
        )
        anexar_estimativa(self.banco.conexao, candidato, sinal=sinal)
        return None

    def _reservar_entrega_pre_post(
        self, sinal_id, canal, reenvio_controlado=False,
        reserva_reenvio_token=None, permitir_simulacao=False,
    ):
        """Fecha atomicamente o intervalo entre o ultimo gate e o POST."""
        if reenvio_controlado:
            token = reserva_reenvio_token
        else:
            token = self.banco.reservar_entrega_alerta(
                sinal_id, canal, permitir_simulacao=permitir_simulacao
            )

        if self.banco.reserva_entrega_valida(
            sinal_id, canal, token,
            permitir_simulacao=permitir_simulacao,
        ):
            return None, token
        if self.banco.alerta_ja_entregue(sinal_id, canal):
            return "duplicado", None

        motivo = (
            "reserva_reenvio_invalida"
            if reenvio_controlado else "reserva_entrega_concorrente"
        )
        self.banco.registrar_entrega_alerta(
            sinal_id, "gateway:reserva_telegram", "bloqueado", motivo
        )
        return motivo, None

    def _revalidar_entrega_oficial(self, sinal_id, candidato):
        persistido = self.banco.carregar_sinal_para_entrega(sinal_id)
        if persistido is None:
            return "sinal_inexistente"
        if persistido["status"] != "aprovado":
            return "sinal_persistido_nao_aprovado"
        if persistido["resolvido"]:
            return "sinal_ja_resolvido"
        fingerprint_atual = fingerprint_vinculado_no_banco(
            self.banco.conexao, persistido["regra_versao"]
        )
        if fingerprint_atual is None:
            return "linhagem_regra_indisponivel"
        if persistido.get("regra_fingerprint") != fingerprint_atual:
            return "sinal_sem_linhagem_valida"
        if (
            persistido["mercado"] != candidato.get("mercado")
            or persistido["regra_versao"] != candidato.get("regra_versao")
            or not self._numeros_iguais(
                persistido["linha"], candidato.get("linha")
            )
            or not self._numeros_iguais(
                persistido["odd"], candidato.get("odd")
            )
            or not self._numeros_iguais(
                persistido["pontuacao_tecnica"],
                candidato.get("pontuacao_tecnica"),
            )
            or not self._numeros_iguais(
                persistido["probabilidade_calibrada"],
                candidato.get("probabilidade_calibrada"),
            )
        ):
            return "sinal_persistido_divergente"

        try:
            features_persistidas = json.loads(
                persistido.get("features_json") or "{}"
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            features_persistidas = {}
        rastro_valor = validar_rastro_valor_mercado(
            persistido.get("probabilidade_calibrada"),
            persistido.get("odd"),
            features_persistidas,
        )
        if not rastro_valor["valido"]:
            return rastro_valor["motivo"]
        odd_oposta_persistida = odd_oposta_sincronizada({
            "features": features_persistidas,
        })
        odd_oposta_candidata = odd_oposta_sincronizada(candidato)
        if (
            odd_oposta_candidata is not None
            and not self._numeros_iguais(
                odd_oposta_persistida, odd_oposta_candidata
            )
        ):
            return "sinal_persistido_divergente"
        referencia_persistida = referencia_tres_vias_sincronizada({
            "features": features_persistidas,
        })
        referencia_candidata = referencia_tres_vias_sincronizada(candidato)
        if referencia_candidata is not None:
            if (
                referencia_persistida is None
                or referencia_persistida["selecao"]
                != referencia_candidata["selecao"]
                or any(
                    not self._numeros_iguais(
                        referencia_persistida["odds"].get(chave),
                        referencia_candidata["odds"].get(chave),
                    )
                    for chave in ("casa", "visitante", "sem_gol")
                )
            ):
                return "sinal_persistido_divergente"

        entrada_revalidacao = dict(candidato)
        entrada_revalidacao.update({
            "mercado": persistido["mercado"],
            "linha": persistido["linha"],
            "odd": persistido["odd"],
            "pontuacao_tecnica": persistido["pontuacao_tecnica"],
            "regra_versao": persistido["regra_versao"],
            "regra_fingerprint": persistido["regra_fingerprint"],
        })
        revalidado = self.calibrador.aplicar(entrada_revalidacao)
        probabilidade_atual = revalidado.get("probabilidade_calibrada")
        if probabilidade_atual is None:
            return "calibracao_atual_invalida"
        diversidade = auditar_diversidade_amostra_calibracao(
            self.banco.conexao,
            persistido["mercado"],
            persistido["regra_versao"],
            self.limites_risco,
        )
        if not diversidade["pronto"]:
            return "diversidade_amostra_insuficiente"
        if not self._numeros_iguais(
            probabilidade_atual, candidato.get("probabilidade_calibrada")
        ):
            return "calibracao_alterada"
        return None

    def _enviar_teste(
        self, sinal_id, candidato, jogo, reenvio_controlado=False,
        reserva_reenvio_token=None,
    ):
        canal = self.canal_teste or self.canais.get(candidato.get("mercado"))
        if not canal:
            return "canal_nao_configurado"
        if not self.token:
            return "token_nao_configurado"
        motivo_filtro = self.registrar_filtro_teste(
            sinal_id, candidato
        )
        if motivo_filtro is not None:
            return motivo_filtro
        canal_registro = f"{canal}:teste"
        if self.banco.alerta_ja_entregue(sinal_id, canal_registro):
            return "duplicado"
        if (
            not reenvio_controlado
            and self.banco.possui_entrega_incerta(
                sinal_id, canal_registro
            )
        ):
            return "entrega_teste_incerta"
        if self.banco.alerta_teste_ja_entregue_no_grupo_independente(
            sinal_id
        ):
            return "duplicado_grupo_teste"
        versao_experimento = versao_exploracao_candidato(candidato)
        if candidato_experimento_grupo_teste(candidato):
            primeira_decisao = (
                self.banco.sinal_e_primeira_decisao_exploracao(
                    sinal_id,
                    versao_experimento,
                )
            )
        else:
            primeira_decisao = (
                self.banco.sinal_e_primeira_decisao_independente(sinal_id)
            )
        if not primeira_decisao:
            return "nao_primeira_decisao_teste"
        if self.banco.alerta_teste_recente_na_partida(sinal_id):
            return "duplicado_recente"
        if self.banco.total_alertas_teste_entregues_hoje(
            candidato.get("regra_versao")
        ) >= self.limite_diario_teste:
            return "limite_diario_teste"
        if (
            self.banco.total_alertas_teste_entregues_hoje()
            >= self.limite_global_teste
        ):
            return "limite_global_teste"
        estado_pre_envio = self._revalidar_pre_envio(
            sinal_id, candidato, jogo
        )
        if estado_pre_envio is not None:
            return estado_pre_envio
        estado_reserva, token_reserva = self._reservar_entrega_pre_post(
            sinal_id,
            canal_registro,
            reenvio_controlado=reenvio_controlado,
            reserva_reenvio_token=reserva_reenvio_token,
            permitir_simulacao=candidato_experimento_grupo_teste(candidato),
        )
        if estado_reserva is not None:
            return estado_reserva
        try:
            resposta = self.transporte(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                {
                    "chat_id": canal,
                    "text": self._mensagem_teste(candidato, jogo),
                    "disable_web_page_preview": "true",
                },
            )
            prova = self._validar_confirmacao_telegram(resposta, canal)
        except Exception as erro:
            self.banco.finalizar_notificacao_alerta(
                sinal_id, canal_registro, token_reserva, "incerto", str(erro)
            )
            return "incerto"
        if not self.banco.finalizar_notificacao_alerta(
            sinal_id, canal_registro, token_reserva, "entregue", **prova
        ):
            self.banco.registrar_entrega_alerta(
                sinal_id, canal_registro, "entregue", **prova
            )
        self.banco.marcar_sinal_como_simulacao(sinal_id)
        return "teste_entregue"

    def motivo_filtro_teste(self, candidato):
        """Consulta a mesma política de envio sem persistir ou enviar nada."""
        motivo = motivo_suspensao_simulacao(candidato)
        if motivo is None:
            try:
                pontuacao = float(
                    candidato.get("pontuacao_tecnica") or 0
                )
            except (TypeError, ValueError):
                pontuacao = 0.0
            if candidato_proximo_gol_balanceado_grupo_teste(candidato):
                pontuacao_minima = (
                    PONTUACAO_MINIMA_PROXIMO_GOL_BALANCEADO_TESTE
                )
            else:
                pontuacao_minima = (
                    self.pontuacao_minima_proximo_gol_teste
                    if candidato.get("mercado") == "proximo_gol"
                    else self.pontuacao_minima_teste
                )
            if pontuacao < pontuacao_minima:
                motivo = "pontuacao_teste_insuficiente"
            else:
                try:
                    qualidade = float(
                        candidato.get("qualidade_dados") or 0
                    )
                except (TypeError, ValueError):
                    qualidade = 0.0
                motivo = (
                    "qualidade_teste_insuficiente"
                    if qualidade < self.qualidade_minima_teste else None
                )
        return motivo

    def registrar_filtro_teste(self, sinal_id, candidato):
        """Congela prospectivamente um descarte comparável, sem enviar nada."""
        if not self.modo_teste:
            return None
        motivo_suspensao = motivo_suspensao_simulacao(candidato)
        motivo = self.motivo_filtro_teste(candidato)
        if motivo is None:
            return None
        primeira_decisao = (
            self.banco.sinal_e_primeira_decisao_independente(sinal_id)
        )
        if not primeira_decisao and motivo_suspensao is None:
            return "nao_primeira_decisao_teste"
        # Uma leitura posterior normalmente nao deve criar outra observacao de
        # filtro, pois a unidade prospectiva e partida/mercado/regra. A excecao
        # e uma decisao aprovada internamente que foi barrada pela politica de
        # roteamento: sem este registro ela fica como ``aprovado`` no SQLite,
        # sem entrega e sem motivo auditavel, parecendo uma falha do Telegram.
        # Registrar o bloqueio nao envia mensagem, nao consome cota e nao muda
        # a unidade usada pela calibracao.
        self.banco.registrar_entrega_alerta(
            sinal_id,
            (
                "gateway:validacao"
                if motivo_suspensao is not None else "gateway:teste"
            ),
            "filtrado",
            motivo,
        )
        return motivo

    def registrar_priorizacao_teste(self, sinal_id):
        """Explica por que um aprovado perdeu a vaga única do snapshot."""
        if not self.modo_teste:
            return None
        if not self.banco.sinal_e_primeira_decisao_independente(sinal_id):
            return "nao_primeira_decisao_teste"
        motivo = "nao_selecionado_melhor_sinal_snapshot"
        self.banco.registrar_entrega_alerta(
            sinal_id,
            "gateway:priorizacao_teste",
            "filtrado",
            motivo,
        )
        return motivo

    def cancelar_por_evento(self, jogo, eventos_recentes):
        if not (eventos_recentes or {}).get("cartao_vermelho"):
            return 0
        if not self.token:
            return 0
        enviados = self.banco.sinais_entregues_pendentes(jogo["url"])
        cancelados = 0
        for sinal in enviados:
            sinal = dict(sinal)
            canal_cancelamento = f"{sinal['canal']}:cancelamento"
            mensagem = (
                "🚫 CENÁRIO INVALIDADO — NÃO FAÇA NOVA ENTRADA\n\n"
                f"{jogo.get('mandante')} x "
                f"{jogo.get('visitante')}\n"
                f"Minuto: {_formatar_status(jogo.get('status'))} | "
                f"Placar: {jogo.get('placar')}\n"
                "Motivo: cartão vermelho detectado após o sinal. "
                "A análise precisa ser recalculada."
            )
            reserva = self.banco.reservar_notificacao_cancelamento(
                sinal["id"], sinal["canal"]
            )
            if not reserva:
                continue
            if not self.banco.reserva_notificacao_cancelamento_valida(
                sinal["id"], sinal["canal"], reserva
            ):
                self.banco.finalizar_notificacao_alerta(
                    sinal["id"], canal_cancelamento, reserva, "cancelado",
                    "estado_alterado_antes_do_post",
                )
                continue
            try:
                mensagem_id = int(sinal.get("mensagem_id_origem") or 0)
                metodo = (
                    "editMessageText" if mensagem_id > 0 else "sendMessage"
                )
                payload = {
                    "chat_id": sinal["canal"],
                    "text": mensagem,
                }
                if mensagem_id > 0:
                    payload["message_id"] = mensagem_id
                resposta = self.transporte(
                    f"https://api.telegram.org/bot{self.token}/{metodo}",
                    payload,
                )
                prova = self._validar_confirmacao_telegram(
                    resposta, sinal["canal"]
                )
                if mensagem_id > 0:
                    prova = {
                        "provedor": "telegram",
                        "provedor_destino_id": str(sinal["canal"]),
                        "provedor_mensagem_id": None,
                        "confirmacao": {
                            "ok": True,
                            "provedor": "telegram",
                            "edicao": True,
                            "message_id_origem": mensagem_id,
                        },
                    }
            except Exception as erro:
                self.banco.finalizar_notificacao_alerta(
                    sinal["id"], canal_cancelamento, reserva, "incerto",
                    str(erro),
                )
                continue
            if self.banco.finalizar_notificacao_alerta(
                sinal["id"], canal_cancelamento, reserva, "entregue",
                **prova,
            ):
                cancelados += 1
        return cancelados

    def enviar_resultados_simulacoes(self, limite=20):
        resumo = {
            "consultados": 0, "entregues": 0, "erros": 0,
            "bloqueados": 0, "recuperados": 0,
        }
        if not self.token:
            return resumo
        recuperacao = self.reenviar_edicoes_resultados_incertas(
            simulacoes=True, limite=limite
        )
        resumo["recuperados"] = recuperacao["entregues"]
        pendentes = self.banco.resultados_simulacoes_nao_notificados(limite)
        resumo["consultados"] = len(pendentes)
        bloqueio = self._validar_operacao_oficial() if pendentes else None
        if bloqueio is not None:
            resumo["bloqueados"] = len(pendentes)
            resumo["motivo_bloqueio"] = bloqueio
            return resumo
        for item in pendentes:
            item = dict(item)
            canal_teste = item["canal_teste"]
            canal = canal_teste.rsplit(":teste", 1)[0]
            canal_registro = f"{canal_teste}:resultado"
            placar = self._placares_resultado_simulacao(item)
            anexar_estimativa(self.banco.conexao, item)
            mensagem = self._mensagem_entrada_finalizada(
                item, placar, simulacao=True
            )
            reserva = self.banco.reservar_notificacao_resultado(
                item["sinal_id"], canal_teste, item
            )
            if not reserva:
                continue
            if not self.banco.reserva_notificacao_resultado_valida(
                item["sinal_id"], canal_teste, reserva, item
            ):
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], canal_registro, reserva, "cancelado",
                    "resultado_alterado_antes_do_post",
                )
                resumo["bloqueados"] += 1
                continue
            try:
                mensagem_id = int(item.get("mensagem_id_origem") or 0)
                metodo = "editMessageText" if mensagem_id > 0 else "sendMessage"
                payload = {"chat_id": canal, "text": mensagem,
                           "disable_web_page_preview": "true"}
                if mensagem_id > 0:
                    payload["message_id"] = mensagem_id
                resposta = self.transporte(
                    f"https://api.telegram.org/bot{self.token}/{metodo}",
                    payload,
                )
                prova = self._validar_confirmacao_telegram(resposta, canal)
                if mensagem_id > 0:
                    prova = {
                        "provedor": "telegram",
                        "provedor_destino_id": str(canal),
                        "provedor_mensagem_id": None,
                        "confirmacao": {
                            "ok": True,
                            "provedor": "telegram",
                            "edicao": True,
                            "message_id_origem": mensagem_id,
                        },
                    }
            except Exception as erro:
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], canal_registro, reserva, "incerto",
                    str(erro),
                )
                resumo["erros"] += 1
                continue
            if self.banco.finalizar_notificacao_alerta(
                item["sinal_id"], canal_registro, reserva, "entregue",
                **prova,
            ):
                resumo["entregues"] += 1
            else:
                resumo["erros"] += 1
        return resumo

    def enviar_greens_antecipados(self, limite=50):
        """Edita a entrada quando o GREEN já está matematicamente garantido."""
        resumo = {
            "consultados": 0, "confirmados": 0, "entregues": 0,
            "erros": 0, "bloqueados": 0,
        }
        if not self.token:
            return resumo
        itens = self.banco.sinais_entregues_pendentes_green_antecipado(
            limite
        )
        resumo["consultados"] = len(itens)
        bloqueio = self._validar_operacao_oficial() if itens else None
        if bloqueio is not None:
            resumo["bloqueados"] = len(itens)
            resumo["motivo_bloqueio"] = bloqueio
            return resumo

        for linha in itens:
            item = dict(linha)
            confirmacao = (
                self.avaliador_green_antecipado
                .confirmar_green_irreversivel(item["sinal_id"])
            )
            if confirmacao is None:
                continue
            resumo["confirmados"] += 1
            canal_origem = item["canal_origem"]
            canal_registro = f"{canal_origem}:green_antecipado"
            reserva = self.banco.reservar_notificacao_green_antecipado(
                item["sinal_id"], canal_origem
            )
            if not reserva:
                continue
            # Reconfere o estado depois do claim. Assim, uma correção de
            # placar ou uma liquidação concorrente impede a edição obsoleta.
            if not self.banco.reserva_notificacao_green_antecipado_valida(
                item["sinal_id"], canal_origem, reserva
            ):
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], canal_registro, reserva, "cancelado",
                    "estado_alterado_antes_da_edicao",
                )
                resumo["bloqueados"] += 1
                continue
            confirmacao_atual = (
                self.avaliador_green_antecipado
                .confirmar_green_irreversivel(item["sinal_id"])
            )
            if confirmacao_atual is None:
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], canal_registro, reserva, "cancelado",
                    "green_nao_reconfirmado_antes_da_edicao",
                )
                resumo["bloqueados"] += 1
                continue
            canal = (
                canal_origem.rsplit(":teste", 1)[0]
                if canal_origem.endswith(":teste") else canal_origem
            )
            mensagem_id = int(item.get("mensagem_id_origem") or 0)
            if mensagem_id <= 0:
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], canal_registro, reserva, "cancelado",
                    "mensagem_original_sem_id",
                )
                resumo["bloqueados"] += 1
                continue
            anexar_estimativa(self.banco.conexao, item)
            mensagem = self._mensagem_green_antecipado(
                item,
                confirmacao_atual,
                simulacao=canal_origem.endswith(":teste"),
            )
            try:
                resposta = self.transporte(
                    f"https://api.telegram.org/bot{self.token}/editMessageText",
                    {
                        "chat_id": canal,
                        "message_id": mensagem_id,
                        "text": mensagem,
                        "disable_web_page_preview": "true",
                    },
                )
                self._validar_confirmacao_telegram(resposta, canal)
                prova = {
                    "provedor": "telegram",
                    "provedor_destino_id": str(canal),
                    "provedor_mensagem_id": None,
                    "confirmacao": {
                        "ok": True,
                        "provedor": "telegram",
                        "edicao": True,
                        "green_antecipado": True,
                        "message_id_origem": mensagem_id,
                        "snapshot_id": confirmacao_atual["snapshot_id"],
                    },
                }
            except Exception as erro:
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], canal_registro, reserva, "incerto",
                    str(erro),
                )
                resumo["erros"] += 1
                continue
            if self.banco.finalizar_notificacao_alerta(
                item["sinal_id"], canal_registro, reserva, "entregue",
                **prova,
            ):
                resumo["entregues"] += 1
            else:
                resumo["erros"] += 1
        return resumo

    def enviar_resultados_oficiais(self, limite=20):
        resumo = {
            "consultados": 0, "entregues": 0, "erros": 0,
            "bloqueados": 0, "recuperados": 0,
        }
        if not self.token:
            return resumo
        recuperacao = self.reenviar_edicoes_resultados_incertas(
            simulacoes=False, limite=limite
        )
        resumo["recuperados"] = recuperacao["entregues"]
        pendentes = self.banco.resultados_oficiais_nao_notificados(limite)
        resumo["consultados"] = len(pendentes)
        bloqueio = self._validar_operacao_oficial() if pendentes else None
        if bloqueio is not None:
            resumo["bloqueados"] = len(pendentes)
            resumo["motivo_bloqueio"] = bloqueio
            return resumo
        for item in pendentes:
            item = dict(item)
            canal = item["canal_oficial"]
            canal_registro = f"{canal}:resultado"
            placar = self._placar_resultados(
                item["mercado"], simulacoes=False
            )
            anexar_estimativa(self.banco.conexao, item)
            mensagem = self._mensagem_entrada_finalizada(
                item, placar, simulacao=False
            )
            reserva = self.banco.reservar_notificacao_resultado(
                item["sinal_id"], canal, item
            )
            if not reserva:
                continue
            if not self.banco.reserva_notificacao_resultado_valida(
                item["sinal_id"], canal, reserva, item
            ):
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], canal_registro, reserva, "cancelado",
                    "resultado_alterado_antes_do_post",
                )
                resumo["bloqueados"] += 1
                continue
            try:
                mensagem_id = int(item.get("mensagem_id_origem") or 0)
                metodo = "editMessageText" if mensagem_id > 0 else "sendMessage"
                payload = {"chat_id": canal, "text": mensagem,
                           "disable_web_page_preview": "true"}
                if mensagem_id > 0:
                    payload["message_id"] = mensagem_id
                resposta = self.transporte(
                    f"https://api.telegram.org/bot{self.token}/{metodo}",
                    payload,
                )
                prova = self._validar_confirmacao_telegram(resposta, canal)
                if metodo == "editMessageText":
                    prova = {
                        "provedor": "telegram",
                        "provedor_destino_id": str(canal),
                        "provedor_mensagem_id": None,
                    "confirmacao": {"ok": True, "edicao": True,
                                      "provedor": "telegram",
                                      "message_id_origem": mensagem_id},
                    }
            except Exception as erro:
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], canal_registro, reserva, "incerto",
                    str(erro),
                )
                resumo["erros"] += 1
                continue
            if self.banco.finalizar_notificacao_alerta(
                item["sinal_id"], canal_registro, reserva, "entregue",
                **prova,
            ):
                resumo["entregues"] += 1
            else:
                resumo["erros"] += 1
        return resumo

    def reenviar_edicoes_resultados_incertas(
        self, simulacoes, limite=10,
    ):
        resumo = {
            "consultados": 0, "entregues": 0, "erros": 0,
            "bloqueados": 0,
        }
        if not self.token:
            return resumo
        itens = self.banco.resultados_edicoes_incertas(
            simulacoes=bool(simulacoes), limite=limite
        )
        resumo["consultados"] = len(itens)
        # Uma edicao de resultado ja liquidado e ancorada no message_id
        # original e idempotente. Ela precisa poder reparar justamente a
        # pendencia que pode ter degradado o gate operacional, sem liberar
        # novas entradas nem criar uma nova mensagem.
        for linha in itens:
            item = dict(linha)
            token = self.banco.reservar_reenvio_edicao_resultado(
                item["entrega_id"]
            )
            if not token:
                continue
            canal_origem = item["canal_origem"]
            if not self.banco.reserva_notificacao_resultado_valida(
                item["sinal_id"], canal_origem, token, item
            ):
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], item["canal_registro"], token,
                    "cancelado", "resultado_alterado_antes_do_retry",
                )
                resumo["bloqueados"] += 1
                continue
            canal = (
                canal_origem.rsplit(":teste", 1)[0]
                if simulacoes else canal_origem
            )
            placar = (
                self._placares_resultado_simulacao(item)
                if simulacoes else self._placar_resultados(
                    item["mercado"], simulacoes=False
                )
            )
            anexar_estimativa(self.banco.conexao, item)
            mensagem = self._mensagem_entrada_finalizada(
                item, placar, simulacao=bool(simulacoes)
            )
            mensagem_id = int(item["mensagem_id_origem"])
            try:
                resposta = self.transporte(
                    f"https://api.telegram.org/bot{self.token}/editMessageText",
                    {
                        "chat_id": canal,
                        "message_id": mensagem_id,
                        "text": mensagem,
                        "disable_web_page_preview": "true",
                    },
                )
                self._validar_confirmacao_telegram(resposta, canal)
                prova = {
                    "provedor": "telegram",
                    "provedor_destino_id": str(canal),
                    "provedor_mensagem_id": None,
                    "confirmacao": {
                        "ok": True,
                        "provedor": "telegram",
                        "edicao": True,
                        "message_id_origem": mensagem_id,
                        "retry_idempotente": True,
                    },
                }
            except Exception as erro:
                self.banco.finalizar_notificacao_alerta(
                    item["sinal_id"], item["canal_registro"], token,
                    "incerto", str(erro),
                )
                resumo["erros"] += 1
                continue
            if self.banco.finalizar_notificacao_alerta(
                item["sinal_id"], item["canal_registro"], token,
                "entregue", **prova,
            ):
                resumo["entregues"] += 1
            else:
                resumo["erros"] += 1
        return resumo

    def enviar_correcoes_resultados_simulacoes(self, limite=20):
        resumo = {
            "consultados": 0, "entregues": 0, "erros": 0,
            "bloqueados": 0,
        }
        if not self.token:
            return resumo
        revisoes = self.banco.revisoes_simulacoes_nao_notificadas(limite)
        resumo["consultados"] = len(revisoes)
        bloqueio = self._validar_operacao_oficial() if revisoes else None
        if bloqueio is not None:
            resumo["bloqueados"] = len(revisoes)
            resumo["motivo_bloqueio"] = bloqueio
            return resumo
        for item in revisoes:
            item = dict(item)
            canal_teste = item["canal_teste"]
            canal = canal_teste.rsplit(":teste", 1)[0]
            mensagem = self._mensagem_correcao_resultado_teste(item)
            reserva = self.banco.reservar_notificacao_correcao(
                item["revisao_id"], item["sinal_id"], canal_teste
            )
            if not reserva:
                continue
            if not self.banco.reserva_notificacao_correcao_valida(
                item["revisao_id"], item["sinal_id"], canal_teste,
                reserva,
            ):
                self.banco.finalizar_notificacao_correcao(
                    item["revisao_id"], item["sinal_id"], canal_teste,
                    reserva, "cancelado", "revisao_alterada_antes_do_post",
                )
                resumo["bloqueados"] += 1
                continue
            try:
                mensagem_id = int(item.get("mensagem_id_origem") or 0)
                metodo = (
                    "editMessageText" if mensagem_id > 0 else "sendMessage"
                )
                payload = {
                    "chat_id": canal,
                    "text": mensagem,
                    "disable_web_page_preview": "true",
                }
                if mensagem_id > 0:
                    payload["message_id"] = mensagem_id
                resposta = self.transporte(
                    f"https://api.telegram.org/bot{self.token}/{metodo}",
                    payload,
                )
                prova = self._validar_confirmacao_telegram(resposta, canal)
                if mensagem_id > 0:
                    prova = {
                        "provedor": "telegram",
                        "provedor_destino_id": str(canal),
                        "provedor_mensagem_id": None,
                        "confirmacao": {
                            "ok": True,
                            "provedor": "telegram",
                            "edicao": True,
                            "message_id_origem": mensagem_id,
                        },
                    }
            except Exception as erro:
                self.banco.finalizar_notificacao_correcao(
                    item["revisao_id"], item["sinal_id"], canal_teste,
                    reserva, "incerto", str(erro),
                )
                resumo["erros"] += 1
                continue
            if self.banco.finalizar_notificacao_correcao(
                item["revisao_id"], item["sinal_id"], canal_teste,
                reserva, "entregue", **prova,
            ):
                resumo["entregues"] += 1
            else:
                resumo["erros"] += 1
        return resumo

    def reenviar_pendentes(self, limite=5):
        expirados = self.banco.expirar_alertas_com_erro(minutos=10)
        pendentes = self.banco.alertas_com_erro_para_reenvio(limite=limite)
        resumo = {
            "consultados": len(pendentes),
            "entregues": 0,
            "erros": 0,
            "incertos": 0,
            "cancelados": 0,
            "expirados": expirados,
        }
        for item in pendentes:
            reserva_reenvio_token = self.banco.marcar_alerta_em_reenvio(
                item["entrega_id"]
            )
            if not reserva_reenvio_token:
                continue
            candidato = {
                "mercado": item["mercado"],
                "linha": item["linha"],
                "odd": item["odd"],
                "pontuacao_tecnica": item["pontuacao_tecnica"],
                "probabilidade_calibrada": item[
                    "probabilidade_calibrada"
                ],
                "regra_versao": item["regra_versao"],
                "regra_fingerprint": item["regra_fingerprint"],
                "qualidade_dados": item["qualidade_dados"],
                "motivos": json.loads(item["motivos_json"] or "[]"),
                "features": json.loads(item["features_json"] or "{}"),
                "status": item["status_sinal"],
            }
            jogo = {
                "url": item["packball_url"],
                "mandante": item["mandante"],
                "visitante": item["visitante"],
                "placar": item["placar"],
                "status": item["minuto"],
            }
            resultado = self.avaliar_e_enviar(
                item["sinal_id"],
                candidato,
                jogo,
                reenvio_controlado=True,
                reserva_reenvio_token=reserva_reenvio_token,
            )
            if resultado in (
                "entregue", "aviso_insuficiente", "teste_entregue"
            ):
                self.banco.finalizar_erro_alerta(
                    item["entrega_id"], "recuperado"
                )
                resumo["entregues"] += 1
            elif resultado == "erro":
                self.banco.consolidar_falha_reenvio(
                    item["entrega_id"], item["sinal_id"], item["canal"]
                )
                resumo["erros"] += 1
            elif resultado == "incerto":
                self.banco.finalizar_erro_alerta(
                    item["entrega_id"], "incerto_origem"
                )
                resumo["incertos"] += 1
            else:
                self.banco.finalizar_erro_alerta(
                    item["entrega_id"], "cancelado"
                )
                resumo["cancelados"] += 1
        return resumo

    @staticmethod
    def _mensagem(candidato, jogo):
        mercado = _rotulo_mercado(candidato["mercado"])
        linha = candidato.get("linha")
        odd = candidato.get("odd")
        motivos = _formatar_motivos(candidato.get("motivos"))
        cabecalho = (
            "⚠️ ENTRADA ENVIEZADA\n\n"
            if candidato_gol_2t_pos_ht_red(candidato)
            else "📊 SINAL CALIBRADO\n\n"
        )
        referencia_tres_vias = referencia_tres_vias_sincronizada(candidato)
        valor = avaliar_valor_mercado(
            candidato.get("probabilidade_calibrada"),
            odd,
            odd_oposta_sincronizada(candidato),
            odds_mercado=(
                referencia_tres_vias["odds"]
                if referencia_tres_vias else None
            ),
            selecao_mercado=(
                referencia_tres_vias["selecao"]
                if referencia_tres_vias else None
            ),
        )
        bloco_valor = ""
        if valor.get("estado") != "indisponivel":
            bloco_valor = (
                f"Odd justa conservadora: "
                f"{valor['odd_justa_conservadora']:.2f}\n"
                f"Valor esperado conservador: "
                f"{valor['valor_esperado_conservador'] * 100:+.1f}%\n"
            )
            if valor.get("referencia_sem_vig_disponivel"):
                rotulo_margem = (
                    "Margem da casa no mercado"
                    if valor.get("tipo_referencia_sem_vig") == "tres_vias"
                    else "Margem da casa no par"
                )
                bloco_valor += (
                    "Probabilidade de mercado sem vig: "
                    f"{valor['probabilidade_mercado_sem_vig'] * 100:.1f}%\n"
                    f"{rotulo_margem}: "
                    f"{valor['margem_bookmaker'] * 100:+.1f}%\n"
                    "Vantagem do modelo contra o mercado sem vig: "
                    f"{valor['vantagem_probabilidade_sem_vig'] * 100:+.1f} pp\n"
                )
        return (
            cabecalho
            +
            f"⚽ {jogo.get('mandante')} x {jogo.get('visitante')}\n"
            f"⏱ {_formatar_status(jogo.get('status'))}  |  "
            f"Placar: {jogo.get('placar')}\n"
            f"Liga: {jogo.get('liga') or '-'}\n\n"
            "🎯 MERCADO\n"
            f"{mercado}\n"
            f"Linha: {linha if linha is not None else '-'} | "
            f"Odd: {_formatar_odd(odd)}\n\n"
            f"{resumo_forca_ao_vivo(candidato, calibrado=True)}\n\n"
            "📊 AVALIAÇÃO DO MODELO\n"
            f"Confiança histórica calibrada: "
            f"{float(candidato['probabilidade_calibrada']) * 100:.1f}%\n"
            f"{bloco_valor}"
            f"Qualidade dos dados: "
            f"{candidato.get('qualidade_dados', 0)}/100\n"
            f"Regra: {candidato.get('regra_versao') or '-'}\n"
            f"Exposição máxima de referência: "
            f"{EXPOSICAO_POR_SINAL:.1f} unidade\n\n"
            "📈 LEITURA DO MOMENTO\n"
            f"{motivos or '• Regra técnica aprovada'}\n\n"
            "🔞 Apenas para maiores de idade. Aposte com responsabilidade. "
            "Resultados passados não garantem resultados futuros."
        )

    @staticmethod
    def _mensagem_acompanhamento_odd(candidato, jogo):
        acompanhamento = (
            (candidato.get("features") or {}).get("acompanhamento_odd")
            or {}
        )
        mercado = _rotulo_mercado(candidato.get("mercado"))
        linha = candidato.get("linha")
        odd_atual = acompanhamento.get("odd_atual", candidato.get("odd"))
        odd_alvo = acompanhamento.get("odd_alvo")
        odd_maxima = acompanhamento.get("odd_maxima_operacional")
        faixa = f"{_formatar_odd(odd_alvo)}"
        if odd_maxima is not None:
            faixa += f"–{_formatar_odd(odd_maxima)}"
        return (
            "👀 OPORTUNIDADE EM MONITORAMENTO — AGUARDAR ODD\n\n"
            f"⚽ {jogo.get('mandante')} x {jogo.get('visitante')}\n"
            f"🏆 {jogo.get('liga') or '-'}\n"
            f"⏱ {_formatar_status(jogo.get('status'))} | "
            f"Placar: {jogo.get('placar')}\n\n"
            f"🎯 {mercado} | "
            f"{linha if linha is not None else '-'}\n"
            f"Odd atual: {_formatar_odd(odd_atual)}\n"
            f"Faixa para entrada: {faixa}\n\n"
            "✅ Leitura técnica, histórico e tendência confirmados.\n"
            "⚠️ NÃO ENTRAR AINDA. A cotação continua abaixo do preço "
            "definido. O bot seguirá acompanhando e enviará a entrada "
            "oficial somente se a odd atingir a faixa e os demais "
            "critérios permanecerem válidos."
        )

    @staticmethod
    def _mensagem_resultado_acompanhamento_odd(item, desfecho):
        try:
            features = json.loads(item.get("features_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        acompanhamento = (
            features.get("acompanhamento_odd")
            if isinstance(features, dict) else {}
        ) or {}
        icone, rotulo = _rotulo_resultado(desfecho.get("resultado"))
        oficial = desfecho.get("entrada_oficial")
        ultima = desfecho.get("ultima_odd") or {}
        momento = (
            "antes do gol"
            if desfecho.get("resultado") in {"green", "half_green"}
            else "antes do encerramento"
        )
        fonte = _rotulo_fonte(ultima.get("fonte"))
        linha = item.get("linha")
        texto_oficial = (
            "✅ Entrada oficial enviada posteriormente"
            f" @ {_formatar_odd(oficial.get('odd'))}."
            if oficial else
            "⚠️ Nenhuma entrada oficial foi enviada: a odd mínima ou os "
            "demais critérios não foram confirmados a tempo."
        )
        natureza = (
            "RESULTADO DA ENTRADA ORIGINADA PELO MONITORAMENTO"
            if oficial else "RESULTADO HIPOTÉTICO — SEM ENTRADA"
        )
        return (
            f"{icone} {natureza}: {rotulo}\n\n"
            f"⚽ {item.get('mandante')} x {item.get('visitante')}\n"
            f"🏆 {item.get('liga') or '-'}\n"
            f"⏱ {_formatar_status(desfecho.get('status'))} | "
            f"Placar: {desfecho.get('placar') or '-'}\n\n"
            f"🎯 {_rotulo_mercado(item.get('mercado'))} | "
            f"{linha if linha is not None else '-'}\n"
            f"Odd no primeiro aviso: {_formatar_odd(item.get('odd'))}\n"
            f"Última odd registrada {momento}: "
            f"{_formatar_odd(ultima.get('odd'))} | {fonte}\n"
            f"Odd mínima definida: "
            f"{_formatar_odd(acompanhamento.get('odd_alvo'))}\n\n"
            f"{texto_oficial}\n"
            "Este acompanhamento permanece separado das estatísticas e do "
            "ROI oficial quando nenhuma entrada foi enviada."
        )

    @staticmethod
    def _mensagem_teste(candidato, jogo):
        mercado = _rotulo_mercado(candidato["mercado"])
        motivos = _formatar_motivos(
            _motivos_visiveis_simulacao(candidato)
        )
        linha = candidato.get("linha")
        odd = candidato.get("odd")
        metodo_v2 = candidato_v2_controle_grupo_teste(candidato)
        fonte_odds = str(candidato.get("fonte_odds") or "").strip()
        bookmaker = str(candidato.get("bookmaker_odds") or "").strip()
        rotulos_fontes = {
            "api_football": "API-Football",
            "thestatsapi": "TheStatsAPI",
            "packball": "PackBall",
        }
        origem_odd = rotulos_fontes.get(fonte_odds.casefold(), fonte_odds)
        if origem_odd and bookmaker:
            origem_odd = f"{origem_odd} — {bookmaker}"
        elif origem_odd and candidato.get("mercado") in {
            "escanteios_ft_asiatico",
            "escanteios_1t_asiatico",
            "escanteios_2t_asiatico",
        }:
            origem_odd = f"{origem_odd} — bookmaker não informado"
        linha_origem = f"\nFonte da odd: {origem_odd}" if origem_odd else ""
        cabecalho = (
            "⚠️ ENTRADA ENVIEZADA\n\n"
            if candidato_gol_2t_pos_ht_red(candidato)
            else "🧪 ANÁLISE EXPERIMENTAL — NÃO É ENTRADA\n\n"
        )
        if jogo.get("liga"):
            motivos_compactos = [
                motivo for motivo in _motivos_visiveis_simulacao(candidato)
                if not any(termo in str(motivo).casefold() for termo in (
                    "regra_", "mercado_ao_vivo", "minuto_dentro",
                    "janela_", "faixa_odd_operacional",
                ))
            ][:3]
            leitura = _formatar_motivos(motivos_compactos)
            return (
                cabecalho
                + f"⚽ {jogo.get('mandante')} x {jogo.get('visitante')}\n"
                + f"🏆 {jogo.get('liga')}\n"
                + f"⏱ {_formatar_status(jogo.get('status'))} | "
                  f"Placar: {jogo.get('placar')}\n\n"
                + f"🎯 {mercado} | "
                  f"{linha if linha is not None else '-'} @ {_formatar_odd(odd)}"
                  f"{linha_origem}\n\n"
                + f"{leitura or '• Momento técnico aprovado'}\n\n"
                + resumo_forca_ao_vivo(candidato)
            )
        return (
            cabecalho
            +
            f"⚽ {jogo.get('mandante')} x {jogo.get('visitante')}\n"
            f"⏱ {_formatar_status(jogo.get('status'))}  |  "
            f"Placar: {jogo.get('placar')}\n"
            f"Liga: {jogo.get('liga') or '-'}\n\n"
            "🎯 MERCADO OBSERVADO\n"
            f"{mercado}\n"
            f"Linha: {linha if linha is not None else '-'} | "
            f"Odd: {_formatar_odd(odd)}"
            f"{linha_origem}\n\n"
            "📈 LEITURA DO MOMENTO\n"
            f"{motivos or '• Regra técnica aprovada'}\n\n"
            "📊 AVALIAÇÃO DO MODELO\n"
            f"Nota técnica: {candidato.get('pontuacao_tecnica', 0):.1f}/100 "
            "(não é probabilidade)\n"
            f"Qualidade dos dados: "
            f"{candidato.get('qualidade_dados', 0)}/100\n"
            f"{'Método' if metodo_v2 else 'Regra'}: "
            f"{_rotulo_regra_simulacao(candidato)}\n\n"
            f"{resumo_forca_ao_vivo(candidato)}\n\n"
            "Este aviso serve somente para acompanhar e medir o modelo. "
            "Ainda não possui confiança histórica calibrada."
        )

    def _placar_resultados(
        self, mercado, simulacoes, regra_versao=None, iniciado_em=None,
    ):
        por_mercado = self.banco.resumir_placar_por_mercado(
            simulacoes=simulacoes,
            regra_versao=regra_versao,
            iniciado_em=iniciado_em,
        )
        mercado_atual = por_mercado.get(
            mercado, {"greens": 0, "reds": 0, "pendentes": 0}
        )
        return {
            "greens_total": sum(
                int(item["greens"]) for item in por_mercado.values()
            ),
            "reds_total": sum(
                int(item["reds"]) for item in por_mercado.values()
            ),
            "greens_mercado": int(mercado_atual["greens"]),
            "reds_mercado": int(mercado_atual["reds"]),
        }

    def _placares_resultado_simulacao(self, item):
        regra_versao = item["regra_versao"]
        experimento = self.experimento_filtro or {}
        inicio_filtro = (
            experimento.get("iniciado_em")
            if experimento.get("regra_versao") == regra_versao
            else None
        )
        return {
            "historico": self._placar_resultados(
                item["mercado"], simulacoes=True
            ),
            "regra_atual": self._placar_resultados(
                item["mercado"],
                simulacoes=True,
                regra_versao=regra_versao,
            ),
            "filtro_atual": (
                self._placar_resultados(
                    item["mercado"],
                    simulacoes=True,
                    regra_versao=regra_versao,
                    iniciado_em=inicio_filtro,
                )
                if inicio_filtro else None
            ),
            "regra_versao": regra_versao,
            "iniciado_em": inicio_filtro,
        }

    @staticmethod
    def _texto_placar(placar, mercado, titulo):
        rotulo_mercado = _rotulo_mercado(mercado)
        total_decididos = placar["greens_total"] + placar["reds_total"]
        mercado_decididos = (
            placar["greens_mercado"] + placar["reds_mercado"]
        )
        indice_total = (
            f"{placar['greens_total'] / total_decididos * 100:.1f}%"
            if total_decididos else "-"
        )
        indice_mercado = (
            f"{placar['greens_mercado'] / mercado_decididos * 100:.1f}%"
            if mercado_decididos else "-"
        )
        return (
            f"📊 {titulo}\n"
            f"Total: ✅ {placar['greens_total']} GREEN / "
            f"❌ {placar['reds_total']} RED — índice {indice_total}\n"
            f"{rotulo_mercado}: ✅ {placar['greens_mercado']} GREEN / "
            f"❌ {placar['reds_mercado']} RED — índice {indice_mercado}"
        )

    @classmethod
    def _texto_placares_simulacao(cls, placares, mercado):
        blocos = []
        filtro = placares.get("filtro_atual")
        inicio = placares.get("iniciado_em")
        if filtro is not None:
            try:
                data_inicio = datetime.fromisoformat(inicio).strftime("%d/%m")
            except (TypeError, ValueError):
                data_inicio = "-"
            blocos.append(cls._texto_placar(
                filtro,
                mercado,
                f"FILTRO ATUAL — DESDE {data_inicio}",
            ))
        blocos.append(cls._texto_placar(
            placares["regra_atual"],
            mercado,
            f"REGRA ATUAL — {placares.get('regra_versao') or '-'}",
        ))
        blocos.append(cls._texto_placar(
            placares["historico"],
            mercado,
            "HISTÓRICO COMPLETO",
        ))
        return "\n\n".join(blocos)

    @staticmethod
    def _texto_leitura_original(item):
        try:
            motivos_brutos = json.loads(item["motivos_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            motivos_brutos = []
        motivos = _formatar_motivos(motivos_brutos)
        probabilidade = item["probabilidade_calibrada"]
        if probabilidade is None:
            avaliacao = (
                f"Nota técnica: {float(item['pontuacao_tecnica'] or 0):.1f}/100 "
                "(não é probabilidade)"
            )
        else:
            try:
                features = json.loads(item.get("features_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                features = {}
            referencia_tres_vias = referencia_tres_vias_sincronizada({
                "features": features,
            })
            valor = avaliar_valor_mercado(
                probabilidade,
                item.get("odd"),
                odd_oposta_sincronizada({"features": features}),
                odds_mercado=(
                    referencia_tres_vias["odds"]
                    if referencia_tres_vias else None
                ),
                selecao_mercado=(
                    referencia_tres_vias["selecao"]
                    if referencia_tres_vias else None
                ),
            )
            bloco_valor = ""
            if valor.get("estado") != "indisponivel":
                bloco_valor = (
                    "\nOdd justa conservadora: "
                    f"{valor['odd_justa_conservadora']:.2f} | "
                    "EV conservador: "
                    f"{valor['valor_esperado_conservador'] * 100:+.1f}%"
                )
                if valor.get("referencia_sem_vig_disponivel"):
                    bloco_valor += (
                        "\nMercado sem vig: "
                        f"{valor['probabilidade_mercado_sem_vig'] * 100:.1f}% | "
                        "vantagem: "
                        f"{valor['vantagem_probabilidade_sem_vig'] * 100:+.1f} pp"
                    )
            avaliacao = (
                "Confiança histórica calibrada na entrada: "
                f"{float(probabilidade) * 100:.1f}%"
                f"{bloco_valor}"
            )
        return (
            "📈 LEITURA QUE ORIGINOU O SINAL\n"
            f"Minuto: {item['minuto_entrada'] or '-'} | "
            f"Placar: {item['placar_entrada'] or '-'}\n"
            f"{avaliacao}\n"
            f"Qualidade dos dados: "
            f"{float(item['qualidade_dados'] or 0):.1f}/100\n"
            f"{motivos or '• Regra técnica aprovada'}"
        )

    @staticmethod
    def _texto_confirmacao_resultado(item):
        fonte = _rotulo_fonte(item["fonte_resultado"])
        encerrado_em = item["encerrado_em"]
        try:
            encerrado_texto = datetime.fromisoformat(
                encerrado_em
            ).strftime("%d/%m/%Y %H:%M")
        except (TypeError, ValueError):
            encerrado_texto = encerrado_em or "-"
        return (
            "📌 CONFIRMAÇÃO DO RESULTADO\n"
            "Placar na liquidação: "
            f"{item['placar_liquidacao'] or '-'}\n"
            "Situação na liquidação: "
            f"{_formatar_status(item['status_liquidacao'])}\n"
            f"Fonte do resultado: {fonte}\n"
            f"Confirmado em: {encerrado_texto}"
        )

    @classmethod
    def _mensagem_resultado_teste(cls, item, placar):
        item = dict(item)
        resultado = item["resultado"]
        icone, rotulo = _rotulo_resultado(resultado)
        retorno = item["retorno_unidades"]
        retorno_texto = "-" if retorno is None else f"{float(retorno):+.2f}u"
        return (
            f"{icone} RESULTADO DA ANÁLISE — {rotulo}\n\n"
            f"{item['mandante']} x {item['visitante']}\n"
            f"Mercado: {_rotulo_mercado(item['mercado'])}\n"
            f"Linha: {_formatar_valor(item['linha'])} | "
            f"Odd: {_formatar_odd(item['odd'])}\n"
            f"{'Método' if candidato_v2_controle_grupo_teste(item) else 'Regra'}: "
            f"{_rotulo_regra_simulacao(item)}\n"
            f"Retorno hipotético: {retorno_texto}\n\n"
            f"{cls._texto_confirmacao_resultado(item)}\n\n"
            f"{cls._texto_leitura_original(item)}\n\n"
            "📊 PLACAR DAS ANÁLISES\n\n"
            f"{cls._texto_placares_simulacao(placar, item['mercado'])}\n\n"
            "Resultado registrado para medir o modelo. Não representa garantia "
            "de desempenho futuro."
        )

    @classmethod
    def _mensagem_resultado_oficial(cls, item, placar):
        resultado = item["resultado"]
        icone, rotulo = _rotulo_resultado(resultado)
        retorno = item["retorno_unidades"]
        retorno_texto = "-" if retorno is None else f"{float(retorno):+.2f}u"
        return (
            f"{icone} RESULTADO DA ENTRADA — {rotulo}\n\n"
            f"{item['mandante']} x {item['visitante']}\n"
            f"Mercado: {_rotulo_mercado(item['mercado'])}\n"
            f"Linha: {_formatar_valor(item['linha'])} | "
            f"Odd: {_formatar_odd(item['odd'])}\n"
            f"Regra: {item['regra_versao']}\n"
            f"Retorno: {retorno_texto}\n\n"
            f"{cls._texto_confirmacao_resultado(item)}\n\n"
            f"{cls._texto_leitura_original(item)}\n\n"
            f"{cls._texto_placar(placar, item['mercado'], 'PLACAR OFICIAL')}"
        )

    @classmethod
    def _mensagem_entrada_finalizada(cls, item, placar, *, simulacao):
        item = dict(item)
        # Entradas legadas, gravadas antes de a liga fazer parte da mensagem,
        # conservam o relatório antigo. Entradas novas usam a edição compacta.
        if not item.get("liga"):
            return (
                cls._mensagem_resultado_teste(item, placar)
                if simulacao else cls._mensagem_resultado_oficial(item, placar)
            )
        try:
            motivos = json.loads(item.get("motivos_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            motivos = []
        try:
            features = json.loads(item.get("features_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            features = {}
        candidato = {
            **item,
            "motivos": motivos if isinstance(motivos, list) else [],
            "features": features if isinstance(features, dict) else {},
            "qualidade_dados": item.get("qualidade_dados") or 0,
        }
        jogo = {
            "mandante": item.get("mandante"),
            "visitante": item.get("visitante"),
            "liga": item.get("liga"),
            "status": item.get("minuto_entrada"),
            "placar": item.get("placar_entrada"),
        }
        entrada = (
            cls._mensagem_teste(candidato, jogo)
            if simulacao else cls._mensagem(candidato, jogo)
        )
        icone, rotulo = _rotulo_resultado(item.get("resultado"))
        retorno = item.get("retorno_unidades")
        retorno_texto = "-" if retorno is None else f"{float(retorno):+.2f}u"
        placar_final = item.get("placar_liquidacao") or "-"
        repeticoes = 3 if item.get("resultado") in {
            "green", "red", "half_green", "half_red"
        } else 1
        natureza = " DA SIMULAÇÃO" if simulacao else ""
        destaque = f"{icone * repeticoes} {rotulo}{natureza}!"
        rotulo_retorno = "Retorno hipotético" if simulacao else "Retorno"
        return (
            f"{entrada}\n\n{destaque}\n"
            f"Placar final: {placar_final} | "
            f"{rotulo_retorno}: {retorno_texto}"
        )

    @classmethod
    def _mensagem_green_antecipado(cls, item, confirmacao, *, simulacao):
        item = dict(item)
        try:
            motivos = json.loads(item.get("motivos_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            motivos = []
        try:
            features = json.loads(item.get("features_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            features = {}
        candidato = {
            **item,
            "status": item.get("status_sinal"),
            "motivos": motivos if isinstance(motivos, list) else [],
            "features": features if isinstance(features, dict) else {},
            "qualidade_dados": item.get("qualidade_dados") or 0,
        }
        jogo = {
            "mandante": item.get("mandante"),
            "visitante": item.get("visitante"),
            "liga": item.get("liga"),
            "status": item.get("minuto_entrada"),
            "placar": item.get("placar_entrada"),
        }
        entrada = (
            cls._mensagem_teste(candidato, jogo)
            if simulacao else cls._mensagem(candidato, jogo)
        )
        destaque = (
            "✅✅✅ GREEN DA SIMULAÇÃO!"
            if simulacao else "✅✅✅ GREEN!"
        )
        return (
            f"{entrada}\n\n{destaque}\n"
            f"Confirmado aos {_formatar_status(confirmacao.get('status'))} | "
            f"Placar: {confirmacao.get('placar') or '-'}"
        )

    @staticmethod
    def _mensagem_correcao_resultado_teste(item):
        _, resultado_anterior = _rotulo_resultado(
            item["resultado_anterior"]
        )
        return (
            "⚠️ CORREÇÃO DA ANÁLISE\n\n"
            f"{item['mandante']} x {item['visitante']}\n"
            f"Mercado: {_rotulo_mercado(item['mercado'])}\n"
            f"Linha: {_formatar_valor(item['linha'])} | "
            f"Odd: {_formatar_odd(item['odd'])}\n\n"
            f"Regra: {item['regra_versao']}\n\n"
            f"O resultado provisório {resultado_anterior} "
            "foi desconsiderado porque o período ainda não estava "
            "encerrado. A análise voltou a ficar pendente e será "
            "liquidada com o dado final confirmado."
        )

    @staticmethod
    def _mensagem_insuficiente(candidato, jogo):
        return (
            "ℹ️ ANÁLISE NÃO APROVADA — NÃO É ENTRADA\n\n"
            f"{jogo.get('mandante')} x {jogo.get('visitante')}\n"
            f"Minuto: {_formatar_status(jogo.get('status'))} | "
            f"Placar: {jogo.get('placar')}\n"
            "Confiança histórica calibrada: "
            f"{float(candidato['probabilidade_calibrada']) * 100:.1f}%\n"
            "Motivo: abaixo do mínimo profissional de 75%.\n\n"
            "⚠️ Nenhuma entrada recomendada."
        )
