"""Painel read-only de evidência de edge para todos os mercados ativos.

Cada coorte de seleção é avaliada separadamente. Resultado oficial,
contrafactual e exploração em sombra nunca são somados para justificar uma
mudança de filtro. Nenhuma decisão deste módulo altera sinais ou Telegram.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from dotenv import dotenv_values

from avaliacao_edge_escanteios_asiaticos import (
    VERSAO as VERSAO_AVALIACAO_HISTORICA_ASIATICA,
    avaliar as avaliar_asiatico,
)
from avaliacao_probabilidade_sem_vig import (
    VERSAO as VERSAO_REFERENCIA_PRECO_SEM_VIG,
    _assinatura_coorte_selecao,
    _carregar_sinais,
    _json_objeto,
    _numero,
    avaliar_coorte,
)
from configuracao import validar_configuracao
from controle_gols_antecipados import (
    ler_estado as ler_estado_gols_antecipados,
)
from controle_filtro_gol_ft_preciso import (
    ler_estado as ler_estado_filtro_gol_ft_preciso,
)
from controle_filtro_gol_ht_preciso import (
    ler_estado as ler_estado_filtro_gol_ht_preciso,
)
from controle_escanteios_ft_asiatico import (
    ler_estado as ler_estado_escanteios_ft_asiatico,
)
from controle_v2b_ft import ler_estado_v2b_ft
from gol_ht_00_min20 import VERSAO as VERSAO_GOL_HT_00_MIN20
from gols_antecipados import (
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
    VERSAO_GOL_HT_ANTECIPADO,
)
from gols_capacidade_contextual_v2 import (
    VERSAO_GOL_FT as VERSAO_GOL_FT_CAPACIDADE_V2,
    VERSAO_GOL_HT as VERSAO_GOL_HT_CAPACIDADE_V2,
)
from filtro_gol_ft_antecipado_preciso import (
    VERSAO as VERSAO_FILTRO_GOL_FT_PRECISO,
)
from mercados import mercados_calibrados_operacionais
from top_criterios_gols import (
    VERSAO_FT as VERSAO_TOP_FT,
    VERSAO_HT as VERSAO_TOP_HT,
)
from validacao_gol_ht_00_min20 import resumir_validacao_gol_ht_00_min20
from validacao_gols_antecipados import resumir_validacao_gols_antecipados
from validacao_gol_ft_antecipado_preciso import (
    resumir_validacao as resumir_validacao_filtro_gol_ft_preciso,
)
from validacao_gol_ht_antecipado_preciso import (
    resumir_validacao as resumir_validacao_filtro_gol_ht_preciso,
)
from validacao_escanteios_ft_asiatico_executavel import (
    resumir_validacao as resumir_validacao_escanteios_ft_asiatico,
)
from validacao_escanteios_ft_asiatico_prospectiva import (
    resumir_validacao as resumir_validacao_escanteios_ft_asiatico_legada,
)
from validacao_gols_capacidade_contextual_v2 import (
    SEGMENTOS as SEGMENTOS_CAPACIDADE_V2,
    resumir_grupo_ft_capacidade_contextual_v2,
    resumir_validacao_gols_capacidade_contextual_v2,
)
from validacao_top_criterios_gols import resumir_top_criterios_gols
from versoes_gol_ft_reforcado import versao_regra_operacional


VERSAO = "avaliacao-portfolio-edge-read-only-v12"
BANCO = Path(__file__).with_name("monitor_packball.db")
MERCADO_ASIATICO = "escanteios_ft_asiatico"
AMOSTRA_MINIMA = 100
AMOSTRA_HOLDOUT_MINIMA = 30
COBERTURA_MINIMA = 0.90
AMOSTRA_PRECO_METODO_MINIMA = 95
DESENVOLVIMENTO_PRECO_METODO = 70
AMOSTRA_PRECO_HOLDOUT_MINIMA = 28
DECISOES_VALIDADORES_FAVORAVEIS = frozenset({
    "favoravel_para_revisao",
    "favoravel_para_revisao_independente",
})
RESULTADOS_BINARIOS_VALIDOS = frozenset({
    "green", "half_green", "red", "half_red",
})
MERCADOS_BINARIOS_COM_GATE = frozenset({
    "gol_ft", "gol_ht", "proximo_gol", "proximo_escanteio",
})


def _valor_aninhado(documento, caminho):
    atual = documento
    for parte in caminho.split("."):
        if not isinstance(atual, dict):
            return None
        atual = atual.get(parte)
    return atual


def _carregar_metodo_entregue(
    conexao, *, mercado, versao, registrado_em, linhagem_caminho,
    linhagem_sha256, segmento=None, limite=100,
):
    """Reconstrói a mesma coorte entregue usada pelos validadores.

    A versão do método vive em ``features_json``; ``regra_versao`` pertence
    ao motor-base e não identifica o braço experimental. A independência é
    aplicada antes do filtro de linhagem, reproduzindo a coorte congelada.
    """
    if not registrado_em or not linhagem_sha256:
        return [], {
            "estado": "ancora_ou_linhagem_ausente",
            "linhas_divergentes": 0,
        }
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.snapshot_id, s.criado_em,
               s.mercado, s.linha, s.odd, s.status, s.features_json,
               snap.placar, r.resultado, r.retorno_unidades
        FROM sinais s
        JOIN snapshots snap ON snap.id=s.snapshot_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado=? AND s.status='simulacao'
          AND datetime(s.criado_em)>=datetime(?)
          AND json_extract(
                s.features_json, '$.exploracao_sombra.versao'
              )=?
          AND EXISTS (
              SELECT 1 FROM entregas_alertas e
              WHERE e.sinal_id=s.id AND e.status='entregue'
                AND e.canal LIKE '%:teste'
                AND e.canal NOT LIKE '%:resultado'
                AND e.canal NOT LIKE '%:green_antecipado%'
          )
        ORDER BY datetime(s.criado_em), s.id
        """,
        (mercado, registrado_em, versao),
    ).fetchall()
    primeiras = {}
    invalidas = 0
    sem_resultado_valido = 0
    for linha in linhas:
        item = dict(linha)
        features = _json_objeto(item.pop("features_json", "{}"))
        if segmento is not None and str(_valor_aninhado(
            features, "gol_capacidade_contextual_v2.segmento_competicao"
        ) or "") != str(segmento):
            continue
        chave = (int(item["partida_id"]), str(item["mercado"]))
        if chave in primeiras:
            continue
        item["features"] = features
        primeiras[chave] = item
        if len(primeiras) >= int(limite):
            break
    compativeis = []
    divergentes = 0
    for item in primeiras.values():
        if str(_valor_aninhado(
            item["features"], linhagem_caminho
        ) or "") != str(linhagem_sha256):
            divergentes += 1
            continue
        item["resultado"] = str(item.get("resultado") or "").casefold()
        if item["resultado"] not in RESULTADOS_BINARIOS_VALIDOS:
            sem_resultado_valido += 1
            continue
        item["odd"] = _numero(item.get("odd"))
        item["retorno_unidades"] = _numero(item.get("retorno_unidades"))
        if (
            item["odd"] is None or item["odd"] <= 1.0
            or item["retorno_unidades"] is None
        ):
            invalidas += 1
            continue
        compativeis.append(item)
    return compativeis, {
        "estado": "carregada",
        "candidatos_independentes": len(primeiras),
        "linhas_compativeis": len(compativeis),
        "linhas_divergentes": divergentes,
        "linhas_invalidas": invalidas,
        "linhas_sem_resultado_valido": sem_resultado_valido,
        "resultados_independentes_completos": bool(
            sem_resultado_valido == 0
        ),
        "segmento": segmento,
    }


def _avaliar_braco_metodo(
    conexao, *, identificador, mercado, versao, resumo,
    registrado_em, linhagem_sha256, linhagem_caminho, segmento=None,
):
    sinais, auditoria = _carregar_metodo_entregue(
        conexao,
        mercado=mercado,
        versao=versao,
        registrado_em=registrado_em,
        linhagem_caminho=linhagem_caminho,
        linhagem_sha256=linhagem_sha256,
        segmento=segmento,
    )
    preco = avaliar_coorte(conexao, sinais)
    preco.pop("itens", None)
    preco_holdout = avaliar_coorte(
        conexao, sinais[DESENVOLVIMENTO_PRECO_METODO:]
    )
    preco_holdout.pop("itens", None)
    metricas_preco = preco.get("metricas") or {}
    metricas_preco_holdout = preco_holdout.get("metricas") or {}
    decisao_validador = (resumo or {}).get(
        "decisao_estatistica", (resumo or {}).get("decisao")
    )
    ic_roi = metricas_preco.get("ic95_roi")
    ic_residuo = metricas_preco.get(
        "ic95_desvio_observado_menos_mercado"
    )
    ic_roi_holdout = metricas_preco_holdout.get("ic95_roi")
    ic_residuo_holdout = metricas_preco_holdout.get(
        "ic95_desvio_observado_menos_mercado"
    )
    criterios = {
        "validador_prospectivo_favoravel": (
            decisao_validador in DECISOES_VALIDADORES_FAVORAVEIS
        ),
        "linhagem_homogenea": bool(
            (resumo or {}).get("linhagem_homogenea") is True
            and auditoria.get("linhas_divergentes", 0) == 0
        ),
        "resultados_independentes_completos": bool(
            auditoria.get("resultados_independentes_completos") is True
        ),
        "dados_resultados_validos": bool(
            auditoria.get("linhas_invalidas", 0) == 0
        ),
        "amostra_preco_minima": (
            int(metricas_preco.get("amostra", 0) or 0)
            >= AMOSTRA_PRECO_METODO_MINIMA
        ),
        "cobertura_preco_justo": (
            float(preco.get("taxa_cobertura") or 0) >= COBERTURA_MINIMA
        ),
        "roi_preco_ic95_inferior_positivo": bool(
            ic_roi and ic_roi[0] > 0
        ),
        "residuo_mercado_ic95_inferior_positivo": bool(
            ic_residuo and ic_residuo[0] > 0
        ),
        "amostra_preco_holdout_minima": (
            int(metricas_preco_holdout.get("amostra", 0) or 0)
            >= AMOSTRA_PRECO_HOLDOUT_MINIMA
        ),
        "cobertura_preco_justo_holdout": (
            float(preco_holdout.get("taxa_cobertura") or 0)
            >= COBERTURA_MINIMA
        ),
        "roi_preco_holdout_ic95_inferior_positivo": bool(
            ic_roi_holdout and ic_roi_holdout[0] > 0
        ),
        "residuo_mercado_holdout_ic95_inferior_positivo": bool(
            ic_residuo_holdout and ic_residuo_holdout[0] > 0
        ),
    }
    todos = all(criterios.values())
    if todos:
        estado = "favoravel_para_revisao_manual"
    elif not criterios["resultados_independentes_completos"]:
        estado = "aguardando_resultados_independentes"
    elif not criterios["dados_resultados_validos"]:
        estado = "dados_resultados_invalidos"
    elif decisao_validador in {"evidencia_desfavoravel", "inconclusiva"}:
        estado = "vantagem_nao_comprovada"
    elif decisao_validador == "linhagem_inconsistente":
        estado = "linhagem_inconsistente"
    elif not criterios["amostra_preco_minima"] or not criterios[
        "amostra_preco_holdout_minima"
    ]:
        estado = "aguardando_amostra"
    elif not criterios["cobertura_preco_justo"] or not criterios[
        "cobertura_preco_justo_holdout"
    ]:
        estado = "cobertura_odds_insuficiente"
    else:
        estado = "vantagem_nao_comprovada"
    return {
        "identificador": identificador,
        "mercado": mercado,
        "versao_metodo": versao,
        "segmento": segmento,
        "validador_prospectivo": dict(resumo or {}),
        "decisao_validador": decisao_validador,
        "auditoria_coorte_entregue": auditoria,
        "referencia_mercado_sem_vig": preco,
        "referencia_mercado_sem_vig_holdout": preco_holdout,
        "decisao": {
            "estado": estado,
            "criterios": criterios,
            "todos_satisfeitos": todos,
            "promocao_automatica": False,
        },
    }


def _resumos_validadores_gols(conexao):
    return {
        "antecipados": resumir_validacao_gols_antecipados(conexao),
        "ft_antecipado_preciso": (
            resumir_validacao_filtro_gol_ft_preciso(conexao)
        ),
        "ht_antecipado_preciso": (
            resumir_validacao_filtro_gol_ht_preciso(conexao)
        ),
        "capacidade_v2": (
            resumir_validacao_gols_capacidade_contextual_v2(conexao)
        ),
        "capacidade_v2_ft_grupo": (
            resumir_grupo_ft_capacidade_contextual_v2(conexao)
        ),
        "ht_00_min20": resumir_validacao_gol_ht_00_min20(conexao),
        "top": resumir_top_criterios_gols(conexao),
    }


def _resumir_portfolio_gols(
    conexao,
    mercado,
    recursos,
    controle_v2b_ft,
    resumos,
    controle_gols_antecipados=None,
    controle_filtro_gol_ht_preciso=None,
    controle_filtro_gol_ft_preciso=None,
):
    especificacoes = []
    bloqueados = []
    antecipados = resumos["antecipados"]
    if recursos.get("gols_antecipados_grupo"):
        controle_antecipados = controle_gols_antecipados or {
            "saudavel": True, "metodos": {}
        }
        versoes = (
            (VERSAO_GOL_HT_ANTECIPADO, "ht_antecipado"),
        ) if mercado == "gol_ht" else (
            (VERSAO_GOL_FT_ANTECIPADO, "ft_antecipado_1t"),
            (VERSAO_GOL_FT_ANTECIPADO_2T, "ft_antecipado_2t"),
        )
        for versao, identificador in versoes:
            controle_metodo = (
                (controle_antecipados.get("metodos") or {}).get(versao)
                or {}
            )
            liberado = bool(
                controle_antecipados.get("saudavel") is not False
                and controle_metodo.get("ativo", True) is True
            )
            if not liberado:
                bloqueados.append({
                    "identificador": identificador,
                    "versao_metodo": versao,
                    "estado": controle_metodo.get(
                        "estado", controle_antecipados.get("estado")
                    ),
                    "motivo": controle_metodo.get(
                        "motivo", controle_antecipados.get("motivo")
                    ),
                })
                continue
            especificacoes.append({
                "identificador": identificador,
                "versao": versao,
                "resumo": (antecipados.get("por_braco") or {}).get(
                    versao, {}
                ),
                "registrado_em": antecipados.get("registrado_em"),
                "linhagem_sha256": antecipados.get("linhagem_sha256"),
                "linhagem_caminho": "gol_antecipado.linhagem_sha256",
            })


    if (
        mercado == "gol_ht"
        and recursos.get("gols_antecipados_grupo")
        and recursos.get("filtro_gol_ht_antecipado_preciso")
    ):
        especificacoes = [
            item for item in especificacoes
            if item.get("identificador") != "ht_antecipado"
        ]
        controle_preciso = controle_filtro_gol_ht_preciso or {
            "saudavel": True, "ativo": True,
        }
        controle_origem = (
            (controle_gols_antecipados or {}).get("metodos") or {}
        ).get(VERSAO_GOL_HT_ANTECIPADO, {})
        liberado = bool(
            controle_preciso.get("saudavel") is not False
            and controle_preciso.get("ativo") is True
            and controle_origem.get("ativo", True) is True
        )
        resumo_preciso = resumos.get("ht_antecipado_preciso") or {}
        if liberado:
            decisao_validador = resumo_preciso.get("decisao")
            favoravel = bool(
                resumo_preciso.get("apto_revisao")
                and decisao_validador == "favoravel_para_revisao_manual"
            )
            especificacoes.append({
                "identificador": "ht_antecipado_preciso",
                "avaliacao_pronta": {
                    "identificador": "ht_antecipado_preciso",
                    "mercado": "gol_ht",
                    "versao_metodo": resumo_preciso.get("versao_filtro"),
                    "segmento": None,
                    "validador_prospectivo": dict(resumo_preciso),
                    "decisao_validador": decisao_validador,
                    "auditoria_coorte_entregue": {
                        "estado": "coorte_fixa_de_candidatos",
                        "candidatos_independentes": int(
                            resumo_preciso.get("candidatos", 0) or 0
                        ),
                        "nota": (
                            "populacao congelada antes de resultado e entrega"
                        ),
                    },
                    "referencia_mercado_sem_vig": (
                        resumo_preciso.get("gate_preco_conservador") or {}
                    ).get("total") or {},
                    "referencia_mercado_sem_vig_holdout": (
                        resumo_preciso.get("gate_preco_conservador") or {}
                    ).get("holdout") or {},
                    "decisao": {
                        "estado": (
                            "favoravel_para_revisao_manual"
                            if favoravel else
                            "aguardando_amostra"
                            if not resumo_preciso.get("resultados_completos")
                            else "vantagem_nao_comprovada"
                        ),
                        "criterios": {
                            "validador_prospectivo_favoravel": favoravel,
                            "coorte_fixa_integra": (
                                resumo_preciso.get("saudavel") is True
                            ),
                            "gate_preco_conservador": bool(
                                (
                                    resumo_preciso.get(
                                        "gate_preco_conservador"
                                    ) or {}
                                ).get("satisfeito")
                            ),
                            "taxa_green_minima_75": bool(
                                resumo_preciso.get("taxa_green") is not None
                                and resumo_preciso.get("taxa_green") >= 0.75
                            ),
                        },
                        "todos_satisfeitos": favoravel,
                        "promocao_automatica": False,
                    },
                },
            })
        else:
            bloqueados.append({
                "identificador": "ht_antecipado_preciso",
                "versao_metodo": resumo_preciso.get("versao_filtro"),
                "estado": controle_preciso.get(
                    "estado", controle_origem.get("estado")
                ),
                "motivo": controle_preciso.get(
                    "motivo", controle_origem.get("motivo")
                ),
            })

    if (
        mercado == "gol_ft"
        and recursos.get("gols_antecipados_grupo")
        and recursos.get("filtro_gol_ft_antecipado_preciso")
    ):
        especificacoes = [
            item for item in especificacoes
            if item.get("identificador") != "ft_antecipado_2t"
        ]
        controle_preciso = controle_filtro_gol_ft_preciso or {
            "saudavel": True, "ativo": True,
        }
        controle_origem = (
            (controle_gols_antecipados or {}).get("metodos") or {}
        ).get(VERSAO_GOL_FT_ANTECIPADO_2T, {})
        liberado = bool(
            controle_preciso.get("saudavel") is not False
            and controle_preciso.get("ativo") is True
            and controle_origem.get("ativo", True) is True
        )
        resumo_preciso = resumos.get("ft_antecipado_preciso") or {}
        if liberado:
            decisao_validador = resumo_preciso.get("decisao")
            favoravel = bool(
                resumo_preciso.get("apto_revisao")
                and decisao_validador == "favoravel_para_revisao_manual"
            )
            especificacoes.append({
                "identificador": "ft_antecipado_2t_preciso",
                "avaliacao_pronta": {
                    "identificador": "ft_antecipado_2t_preciso",
                    "mercado": "gol_ft",
                    "versao_metodo": (
                        resumo_preciso.get("versao_filtro")
                        or VERSAO_FILTRO_GOL_FT_PRECISO
                    ),
                    "segmento": "segundo_tempo_46_60",
                    "validador_prospectivo": dict(resumo_preciso),
                    "decisao_validador": decisao_validador,
                    "auditoria_coorte_entregue": {
                        "estado": "coorte_fixa_de_candidatos",
                        "candidatos_independentes": int(
                            resumo_preciso.get("candidatos", 0) or 0
                        ),
                        "nota": (
                            "populacao congelada antes de resultado e entrega"
                        ),
                    },
                    "referencia_mercado_sem_vig": (
                        resumo_preciso.get("gate_preco_conservador") or {}
                    ).get("total") or {},
                    "referencia_mercado_sem_vig_holdout": (
                        resumo_preciso.get("gate_preco_conservador") or {}
                    ).get("holdout") or {},
                    "decisao": {
                        "estado": (
                            "favoravel_para_revisao_manual"
                            if favoravel else
                            "aguardando_amostra"
                            if not resumo_preciso.get("resultados_completos")
                            else "vantagem_nao_comprovada"
                        ),
                        "criterios": {
                            "validador_prospectivo_favoravel": favoravel,
                            "coorte_fixa_integra": (
                                resumo_preciso.get("saudavel") is True
                            ),
                            "gate_preco_conservador": bool(
                                (
                                    resumo_preciso.get(
                                        "gate_preco_conservador"
                                    ) or {}
                                ).get("satisfeito")
                            ),
                            "taxa_green_minima_75": bool(
                                resumo_preciso.get("taxa_green") is not None
                                and resumo_preciso.get("taxa_green") >= 0.75
                            ),
                        },
                        "todos_satisfeitos": favoravel,
                        "promocao_automatica": False,
                    },
                },
            })
        else:
            bloqueados.append({
                "identificador": "ft_antecipado_2t_preciso",
                "versao_metodo": (
                    resumo_preciso.get("versao_filtro")
                    or VERSAO_FILTRO_GOL_FT_PRECISO
                ),
                "estado": controle_preciso.get(
                    "estado", controle_origem.get("estado")
                ),
                "motivo": controle_preciso.get(
                    "motivo", controle_origem.get("motivo")
                ),
            })

    if mercado == "gol_ft":
        controle = controle_v2b_ft or {}
        v2_configurado = bool(
            recursos.get("gol_ft_capacidade_contextual_v2_grupo")
        )
        v2_efetivo = bool(
            v2_configurado
            and controle.get("saudavel") is True
            and controle.get("ativo") is True
        )
        if v2_efetivo:
            resumo = resumos["capacidade_v2_ft_grupo"]
            especificacoes.append({
                "identificador": "ft_capacidade_contextual_v2b",
                "versao": VERSAO_GOL_FT_CAPACIDADE_V2,
                "resumo": resumo,
                "registrado_em": resumo.get("registrado_em"),
                "linhagem_sha256": resumo.get("linhagem_sha256"),
                "linhagem_caminho": (
                    "gol_capacidade_contextual_v2.linhagem_sha256"
                ),
            })
        top_ativo = recursos.get("top_criterios_gols_grupo")
        if top_ativo:
            resumo = (resumos["top"] or {}).get("ft") or {}
            especificacoes.append({
                "identificador": "ft_top_casa_fora10",
                "versao": VERSAO_TOP_FT,
                "resumo": resumo,
                "registrado_em": resumo.get("registrado_em"),
                "linhagem_sha256": resumo.get("linhagem_sha256"),
                "linhagem_caminho": "top_criterio_gols.linhagem_sha256",
            })
    else:
        if recursos.get("gol_ht_00_min20_grupo"):
            resumo = resumos["ht_00_min20"]
            especificacoes.append({
                "identificador": "ht_00_min20",
                "versao": VERSAO_GOL_HT_00_MIN20,
                "resumo": resumo,
                "registrado_em": resumo.get("registrado_em"),
                "linhagem_sha256": resumo.get("linhagem_sha256"),
                "linhagem_caminho": "gol_ht_00_min20.linhagem_sha256",
            })
        if recursos.get("gol_ht_capacidade_contextual_v2_grupo"):
            resumo_v2 = resumos["capacidade_v2"]
            for segmento in SEGMENTOS_CAPACIDADE_V2:
                resumo = (
                    resumo_v2.get("por_braco_segmento") or {}
                ).get(f"{VERSAO_GOL_HT_CAPACIDADE_V2}|{segmento}", {})
                especificacoes.append({
                    "identificador": f"ht_capacidade_v2b:{segmento}",
                    "versao": VERSAO_GOL_HT_CAPACIDADE_V2,
                    "segmento": segmento,
                    "resumo": resumo,
                    "registrado_em": resumo_v2.get("registrado_em"),
                    "linhagem_sha256": resumo_v2.get("linhagem_sha256"),
                    "linhagem_caminho": (
                        "gol_capacidade_contextual_v2.linhagem_sha256"
                    ),
                })
        if recursos.get("top_criterios_gols_grupo"):
            resumo = (resumos["top"] or {}).get("ht") or {}
            especificacoes.append({
                "identificador": "ht_top_casa_fora10",
                "versao": VERSAO_TOP_HT,
                "resumo": resumo,
                "registrado_em": resumo.get("registrado_em"),
                "linhagem_sha256": resumo.get("linhagem_sha256"),
                "linhagem_caminho": "top_criterio_gols.linhagem_sha256",
            })

    if not especificacoes and not bloqueados:
        return None
    bracos = [
        item["avaliacao_pronta"]
        if item.get("avaliacao_pronta") is not None else
        _avaliar_braco_metodo(
            conexao,
            identificador=item["identificador"],
            mercado=mercado,
            versao=item["versao"],
            resumo=item["resumo"],
            registrado_em=item["registrado_em"],
            linhagem_sha256=item["linhagem_sha256"],
            linhagem_caminho=item["linhagem_caminho"],
            segmento=item.get("segmento"),
        )
        for item in especificacoes
    ]
    todos = bool(bracos) and all(
        item["decisao"]["todos_satisfeitos"] for item in bracos
    )
    if not bracos:
        estado = "sem_metodos_ativos"
    elif todos:
        estado = "favoravel_para_revisao_manual"
    elif any(
        item["decisao"]["estado"] in {
            "vantagem_nao_comprovada", "linhagem_inconsistente"
        }
        for item in bracos
    ):
        estado = "vantagem_nao_comprovada"
    else:
        estado = "aguardando_amostra"
    base = _avaliar_mercado_binario(
        conexao, mercado, versao_regra_operacional(mercado)
    )
    return {
        "mercado": mercado,
        "regra_versao": f"portfolio-{mercado}-metodos-ativos-v1",
        "coorte_operacional_avaliada": "metodos_telegram_ativos",
        "metodos_ativos": bracos,
        "metodos_bloqueados": bloqueados,
        "metodo_base_legado": base,
        "decisao": {
            "estado": estado,
            "criterios": {
                "todos_metodos_ativos_favoraveis": todos,
                "quantidade_metodos_ativos": len(bracos),
                "quantidade_metodos_bloqueados": len(bloqueados),
            },
            "todos_satisfeitos": todos,
            "promocao_automatica": False,
        },
    }


def _decidir(
    metricas,
    taxa_cobertura,
    *,
    coorte_presente=True,
    metricas_holdout=None,
    taxa_cobertura_holdout=None,
    resultados_independentes_completos=True,
    dados_resultados_validos=True,
):
    metricas = metricas or {}
    metricas_holdout = metricas_holdout or {}
    amostra = int(metricas.get("amostra", 0) or 0)
    amostra_holdout = int(metricas_holdout.get("amostra", 0) or 0)
    ic_roi = metricas.get("ic95_roi")
    ic_residuo = metricas.get(
        "ic95_desvio_observado_menos_mercado"
    )
    ic_roi_holdout = metricas_holdout.get("ic95_roi")
    ic_residuo_holdout = metricas_holdout.get(
        "ic95_desvio_observado_menos_mercado"
    )
    criterios = {
        "coorte_presente": bool(coorte_presente),
        "resultados_independentes_completos": bool(
            resultados_independentes_completos
        ),
        "dados_resultados_validos": bool(dados_resultados_validos),
        "amostra_minima": amostra >= AMOSTRA_MINIMA,
        "cobertura_preco_justo": (
            float(taxa_cobertura or 0) >= COBERTURA_MINIMA
        ),
        "roi_ic95_inferior_positivo": bool(ic_roi and ic_roi[0] > 0),
        "residuo_mercado_ic95_inferior_positivo": bool(
            ic_residuo and ic_residuo[0] > 0
        ),
        "holdout_minimo": amostra_holdout >= AMOSTRA_HOLDOUT_MINIMA,
        "cobertura_preco_justo_holdout": (
            float(taxa_cobertura_holdout or 0) >= COBERTURA_MINIMA
        ),
        "roi_holdout_ic95_inferior_positivo": bool(
            ic_roi_holdout and ic_roi_holdout[0] > 0
        ),
        "residuo_mercado_holdout_ic95_inferior_positivo": bool(
            ic_residuo_holdout and ic_residuo_holdout[0] > 0
        ),
    }
    pronta = all(criterios.values())
    if not coorte_presente or amostra == 0:
        estado = "aguardando_primeiros_resultados"
    elif not criterios["resultados_independentes_completos"]:
        estado = "aguardando_resultados_independentes"
    elif not criterios["dados_resultados_validos"]:
        estado = "dados_resultados_invalidos"
    elif amostra < AMOSTRA_MINIMA:
        estado = "aguardando_amostra"
    elif not criterios["cobertura_preco_justo"]:
        estado = "cobertura_odds_insuficiente"
    elif not criterios["holdout_minimo"]:
        estado = "holdout_insuficiente"
    elif not criterios["cobertura_preco_justo_holdout"]:
        estado = "cobertura_odds_holdout_insuficiente"
    elif not (
        criterios["roi_ic95_inferior_positivo"]
        and criterios["residuo_mercado_ic95_inferior_positivo"]
    ):
        estado = "vantagem_nao_comprovada"
    elif not (
        criterios["roi_holdout_ic95_inferior_positivo"]
        and criterios[
            "residuo_mercado_holdout_ic95_inferior_positivo"
        ]
    ):
        estado = "vantagem_nao_replicada_holdout"
    else:
        estado = "favoravel_para_revisao_manual"
    return {
        "estado": estado,
        "criterios": criterios,
        "todos_satisfeitos": pronta,
        "promocao_automatica": False,
    }


def _coorte_operacional(mercado, grupos):
    if "aprovado" in grupos:
        return "aprovado"
    nomes = sorted(grupos)
    if len(nomes) == 1:
        return nomes[0]
    if mercado in {"gol_ft", "gol_ht"}:
        sombras = [nome for nome in nomes if nome.startswith("sombra:")]
        if len(sombras) == 1:
            return sombras[0]
        if "simulacao" in grupos:
            return "simulacao"
    return None


def _carregar_sinais_binarios_entregues(conexao, mercado, regra_versao):
    """Carrega somente entradas cuja entrega foi confirmada.

    O status interno pode mudar para ``simulacao`` depois do envio ao canal de
    teste. A prova operacional e, portanto, a linha terminal em
    ``entregas_alertas``; candidatos aprovados sem essa prova nao podem inflar
    amostra, ROI ou edge. A primeira entrada entregue por partida e coorte de
    seleção e preservada cronologicamente antes de consultar seu resultado;
    uma duplicata resolvida nunca substitui a unidade inicial pendente.
    """
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.snapshot_id, s.criado_em,
               s.mercado, s.linha, s.odd, s.probabilidade_calibrada,
               s.status, s.features_json, snap.placar,
               r.resultado, r.retorno_unidades
        FROM sinais s
        JOIN snapshots snap ON snap.id=s.snapshot_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado=? AND s.regra_versao=?
          AND s.status IN ('aprovado', 'simulacao')
          AND EXISTS (
              SELECT 1
              FROM entregas_alertas e
              WHERE e.sinal_id=s.id AND e.status='entregue'
                AND e.canal NOT LIKE 'gateway:%'
                AND e.canal NOT LIKE '%:resultado'
                AND e.canal NOT LIKE '%:green_antecipado%'
          )
        ORDER BY datetime(s.criado_em), s.id
        """,
        (mercado, regra_versao),
    ).fetchall()
    independentes = {}
    for linha in linhas:
        item = dict(linha)
        item["features"] = _json_objeto(
            item.pop("features_json", "{}")
        )
        chave = (
            _assinatura_coorte_selecao(item),
            int(item["partida_id"]),
            str(item["mercado"]),
        )
        independentes.setdefault(chave, item)

    compativeis = []
    por_coorte_bruta = defaultdict(list)
    for item in independentes.values():
        por_coorte_bruta[_assinatura_coorte_selecao(item)].append(item)

    auditoria_por_coorte = {}
    for nome, unidades_brutas in sorted(por_coorte_bruta.items()):
        # A decisão é feita sobre uma coorte fixa de 100 partidas. Antes de
        # completar 100, a divisão é apenas informativa; ao completar, a
        # fronteira 70/30 deixa de se mover para sempre.
        unidades = unidades_brutas[:AMOSTRA_MINIMA]
        corte = (
            DESENVOLVIMENTO_PRECO_METODO
            if len(unidades) >= AMOSTRA_MINIMA
            else math.ceil(len(unidades) * 0.70)
        )
        sem_resultado_valido = 0
        invalidas = 0
        validas = 0
        for indice, item in enumerate(unidades):
            item["_coorte_portfolio"] = nome
            item["_particao_portfolio"] = (
                "desenvolvimento" if indice < corte else "holdout"
            )
            item["resultado"] = str(
                item.get("resultado") or ""
            ).casefold()
            if item["resultado"] not in RESULTADOS_BINARIOS_VALIDOS:
                sem_resultado_valido += 1
                continue
            item["odd"] = _numero(item.get("odd"))
            item["retorno_unidades"] = _numero(
                item.get("retorno_unidades")
            )
            if (
                item["odd"] is None
                or item["odd"] <= 1.0
                or item["retorno_unidades"] is None
            ):
                invalidas += 1
                continue
            validas += 1
            compativeis.append(item)
        auditoria_por_coorte[nome] = {
            "candidatos_independentes_total": len(unidades_brutas),
            "candidatos_coorte_fixa": len(unidades),
            "ignorados_apos_coorte_fixa": max(
                len(unidades_brutas) - len(unidades), 0
            ),
            "unidades_desenvolvimento": corte,
            "unidades_holdout": max(len(unidades) - corte, 0),
            "linhas_resultado_valido": validas,
            "linhas_sem_resultado_valido": sem_resultado_valido,
            "linhas_invalidas": invalidas,
            "resultados_independentes_completos": bool(
                sem_resultado_valido == 0
            ),
            "dados_resultados_validos": bool(invalidas == 0),
        }
    return compativeis, {
        "linhas_brutas_entregues": len(linhas),
        "candidatos_independentes_total": len(independentes),
        "candidatos_coorte_fixa": sum(
            item["candidatos_coorte_fixa"]
            for item in auditoria_por_coorte.values()
        ),
        "linhas_resultado_valido": len(compativeis),
        "linhas_sem_resultado_valido": sum(
            item["linhas_sem_resultado_valido"]
            for item in auditoria_por_coorte.values()
        ),
        "linhas_invalidas": sum(
            item["linhas_invalidas"]
            for item in auditoria_por_coorte.values()
        ),
        "por_coorte": auditoria_por_coorte,
        "criterio_independencia": (
            "primeira_entrega_por_partida_e_coorte_selecao"
        ),
        "selecao_antes_do_resultado": True,
        "tamanho_coorte_fixa": AMOSTRA_MINIMA,
        "divisao_coorte_fixa": [
            DESENVOLVIMENTO_PRECO_METODO,
            AMOSTRA_HOLDOUT_MINIMA,
        ],
    }


def _avaliar_mercado_binario(conexao, mercado, regra_versao):
    sinais, auditoria_historica = _carregar_sinais(
        conexao, mercado, regra_versao
    )
    agrupados = defaultdict(list)
    for sinal in sinais:
        agrupados[_assinatura_coorte_selecao(sinal)].append(sinal)
    coortes = {}
    for nome, itens in sorted(agrupados.items()):
        resumo = avaliar_coorte(conexao, itens)
        coortes[nome] = {
            "tamanho_coorte": resumo["tamanho_coorte"],
            "cobertura_referencia_sem_vig": resumo[
                "cobertura_referencia_sem_vig"
            ],
            "taxa_cobertura": resumo["taxa_cobertura"],
            "exclusoes": resumo["exclusoes"],
            "metricas": resumo["metricas"],
            "por_faixa_probabilidade_mercado": resumo[
                "por_faixa_probabilidade_mercado"
            ],
        }
    sinais_entregues, auditoria_entregues = (
        _carregar_sinais_binarios_entregues(
            conexao, mercado, regra_versao
        )
    )
    sinais_por_coorte = defaultdict(list)
    for sinal in sinais_entregues:
        sinais_por_coorte[sinal["_coorte_portfolio"]].append(sinal)
    nomes_coortes = sorted(
        set((auditoria_entregues.get("por_coorte") or {}))
        | set(sinais_por_coorte)
    )
    coortes_entregues = {}
    for nome in nomes_coortes:
        itens = sinais_por_coorte.get(nome, [])
        resumo = avaliar_coorte(conexao, itens)
        resumo.pop("itens", None)
        desenvolvimento_itens = [
            item for item in itens
            if item.get("_particao_portfolio") == "desenvolvimento"
        ]
        holdout_itens = [
            item for item in itens
            if item.get("_particao_portfolio") == "holdout"
        ]
        desenvolvimento = avaliar_coorte(
            conexao, desenvolvimento_itens
        )
        holdout = avaliar_coorte(conexao, holdout_itens)
        desenvolvimento.pop("itens", None)
        holdout.pop("itens", None)
        auditoria_coorte = dict(
            (auditoria_entregues.get("por_coorte") or {}).get(nome) or {}
        )
        decisao_coorte = _decidir(
            resumo.get("metricas"),
            resumo.get("taxa_cobertura"),
            coorte_presente=bool(
                auditoria_coorte.get("candidatos_coorte_fixa", 0)
            ),
            metricas_holdout=holdout.get("metricas"),
            taxa_cobertura_holdout=holdout.get("taxa_cobertura"),
            resultados_independentes_completos=(
                auditoria_coorte.get(
                    "resultados_independentes_completos"
                ) is True
            ),
            dados_resultados_validos=(
                auditoria_coorte.get("dados_resultados_validos") is True
            ),
        )
        coortes_entregues[nome] = {
            "resumo": resumo,
            "divisao_cronologica": {
                "desenvolvimento_70": desenvolvimento,
                "holdout_30": holdout,
                "criterio": (
                    "coorte_fixa_primeiras_100_partidas_70_30"
                ),
            },
            "auditoria": auditoria_coorte,
            "decisao": decisao_coorte,
        }

    coorte_selecao = _coorte_operacional(mercado, coortes_entregues)
    selecionada = coortes_entregues.get(coorte_selecao) or {}
    resumo_entregue = selecionada.get("resumo") or avaliar_coorte(
        conexao, []
    )
    resumo_entregue.pop("itens", None)
    divisao_cronologica = selecionada.get("divisao_cronologica") or {
        "desenvolvimento_70": {},
        "holdout_30": {},
        "criterio": "coorte_operacional_ausente_ou_ambigua",
    }
    auditoria_selecionada = dict(selecionada.get("auditoria") or {})
    decisao = selecionada.get("decisao") or _decidir(
        None, None, coorte_presente=False,
    )
    if coorte_selecao is None and len(coortes_entregues) > 1:
        decisao = {
            **decisao,
            "estado": "coortes_entregues_ambiguas",
            "todos_satisfeitos": False,
            "promocao_automatica": False,
        }
    nome_operacional = "entregue_confirmado"
    return {
        "mercado": mercado,
        "regra_versao": regra_versao,
        "resolvidas_consultadas": auditoria_historica.get(
            "linhas_resultado_valido_brutas", 0
        ),
        "linhas_invalidas": auditoria_historica.get(
            "linhas_invalidas", 0
        ),
        "auditoria_historica": auditoria_historica,
        "coortes": coortes,
        "coorte_entregue": resumo_entregue,
        "divisao_cronologica_entregue": divisao_cronologica,
        "resolvidas_entregues_consultadas": (
            auditoria_selecionada.get("linhas_resultado_valido", 0)
        ),
        "linhas_entregues_invalidas": auditoria_selecionada.get(
            "linhas_invalidas", 0
        ),
        "coortes_entregues": coortes_entregues,
        "coorte_selecao_avaliada": coorte_selecao,
        "auditoria_coorte_entregue": {
            **auditoria_selecionada,
            "coorte_selecao_avaliada": coorte_selecao,
            "selecao_antes_do_resultado": True,
        },
        "auditoria_todas_coortes_entregues": auditoria_entregues,
        "coorte_operacional_avaliada": nome_operacional,
        "decisao": decisao,
    }


def _resumir_asiatico(conexao, regra_versao, controle_operacional=None):
    completo = avaliar_asiatico(conexao, regra_versao)
    oficial = completo.get("oficial_entregue") or {}
    revisao = completo.get("revisao_operacional") or {}
    historico = {
        "versao_avaliacao": completo.get("versao"),
        "versao_avaliacao_historica": (
            VERSAO_AVALIACAO_HISTORICA_ASIATICA
        ),
        "mercado": MERCADO_ASIATICO,
        "regra_versao": regra_versao,
        "resolvidas_consultadas": completo.get(
            "resolvidas_consultadas", 0
        ),
        "coortes": completo.get("por_coorte") or {},
        "coorte_operacional_avaliada": "oficial_entregue",
        "metricas_oficiais": oficial,
        "metricas_oficiais_elegiveis": completo.get(
            "oficial_elegivel"
        ) or {},
        "divisao_cronologica_oficial_entregue": completo.get(
            "divisao_cronologica_oficial_entregue"
        ) or {},
        "auditoria_oficial_entregue": completo.get(
            "auditoria_oficial_entregue"
        ) or {},
        "por_tipo_linha": completo.get(
            "oficial_entregue_por_tipo_linha"
        ) or {},
        "decisao": {
            "estado": (revisao.get("decisao") or "indisponivel"),
            "criterios": revisao.get("criterios") or {},
            "todos_satisfeitos": bool(revisao.get("todos_satisfeitos")),
            "promocao_automatica": False,
        },
    }
    try:
        prospectiva = resumir_validacao_escanteios_ft_asiatico(conexao)
    except (
        AttributeError, OSError, sqlite3.Error, json.JSONDecodeError,
        TypeError, ValueError, RuntimeError,
    ):
        return historico
    if prospectiva.get("estado") == "nao_registrada":
        return historico
    try:
        prospectiva_legada = (
            resumir_validacao_escanteios_ft_asiatico_legada(conexao)
        )
    except (
        AttributeError, OSError, sqlite3.Error, json.JSONDecodeError,
        TypeError, ValueError, RuntimeError,
    ):
        prospectiva_legada = {
            "estado": "indisponivel",
            "saudavel": False,
            "entra_na_decisao": False,
        }
    controle = controle_operacional or ler_estado_escanteios_ft_asiatico()
    regra_exata = prospectiva.get("regra_versao") == regra_versao
    controle_liberado = bool(
        controle.get("saudavel") and controle.get("ativo")
    )
    criterios = {
        "validacao_saudavel": prospectiva.get("saudavel") is True,
        "versao_regra_exata": regra_exata,
        "coorte_fechada": prospectiva.get("coorte_fechada") is True,
        "resultados_completos": (
            prospectiva.get("resultados_completos") is True
        ),
        "taxa_positiva_minima_75": bool(
            prospectiva.get("taxa_resultado_positivo") is not None
            and prospectiva["taxa_resultado_positivo"] >= 0.75
        ),
        "roi_total_ic95_inferior_positivo": bool(
            isinstance(prospectiva.get("intervalo_roi_95"), (list, tuple))
            and len(prospectiva["intervalo_roi_95"]) == 2
            and prospectiva["intervalo_roi_95"][0] > 0
        ),
        "roi_desenvolvimento_positivo": bool(
            (prospectiva.get("desenvolvimento") or {}).get("roi") is not None
            and prospectiva["desenvolvimento"]["roi"] > 0
        ),
        "roi_holdout_positivo": bool(
            (prospectiva.get("holdout") or {}).get("roi") is not None
            and prospectiva["holdout"]["roi"] > 0
        ),
        "preco_sem_vig_comprovado": bool(
            (prospectiva.get("gate_preco_sem_vig") or {}).get("satisfeito")
        ),
        "controle_operacional_liberado": controle_liberado,
    }
    todos = bool(
        prospectiva.get("apto_revisao")
        and regra_exata
        and controle_liberado
        and all(criterios.values())
    )
    return {
        "mercado": MERCADO_ASIATICO,
        "regra_versao": regra_versao,
        "versao_avaliacao_historica": (
            VERSAO_AVALIACAO_HISTORICA_ASIATICA
        ),
        "resolvidas_consultadas": prospectiva.get("validos", 0),
        "coortes": {
            "prospectiva_executavel_betsapi_bet365": prospectiva,
            "prospectiva_legada_fontes_mistas": prospectiva_legada,
            "historico_pre_ancora_diagnostico": historico,
        },
        "coorte_operacional_avaliada": (
            "prospectiva_executavel_betsapi_bet365_pos_ancora"
        ),
        "metricas_oficiais": prospectiva,
        "metricas_oficiais_elegiveis": prospectiva,
        "divisao_cronologica_oficial_entregue": {
            "desenvolvimento_70": prospectiva.get("desenvolvimento") or {},
            "holdout_30": prospectiva.get("holdout") or {},
        },
        "por_tipo_linha": {},
        "controle_operacional": controle,
        "historico_pre_ancora_entra_na_decisao": False,
        "prospectiva_legada_entra_na_decisao": False,
        "decisao": {
            "estado": (
                "favoravel_para_revisao_manual"
                if todos else str(
                    prospectiva.get("decisao") or "indisponivel"
                )
            ),
            "criterios": criterios,
            "todos_satisfeitos": todos,
            "promocao_automatica": False,
        },
    }


def avaliar_candidato_oficial(conexao, candidato):
    """Revalida o edge da versão exata antes de um alerta oficial.

    Este gate não promove regra e não usa o portfólio agregado de challengers.
    Ele mede somente a versão persistida no candidato que chegaria ao Telegram,
    evitando que o bom resultado de outra versão ou de uma coorte em sombra
    autorize a entrada atual.
    """
    if not isinstance(candidato, dict):
        return {
            "apto": False,
            "estado": "candidato_invalido",
            "motivo": "candidato_oficial_invalido",
            "promocao_automatica": False,
        }
    mercado = str(candidato.get("mercado") or "").strip()
    regra = str(candidato.get("regra_versao") or "").strip()
    if not mercado or not regra:
        return {
            "apto": False,
            "estado": "identidade_incompleta",
            "motivo": "mercado_ou_regra_ausente",
            "mercado": mercado or None,
            "regra_versao": regra or None,
            "promocao_automatica": False,
        }
    if mercado == MERCADO_ASIATICO:
        avaliacao = _resumir_asiatico(conexao, regra)
    elif mercado in MERCADOS_BINARIOS_COM_GATE:
        avaliacao = _avaliar_mercado_binario(conexao, mercado, regra)
    else:
        return {
            "apto": False,
            "estado": "mercado_sem_gate_edge",
            "motivo": "mercado_sem_avaliador_edge_oficial",
            "mercado": mercado,
            "regra_versao": regra,
            "promocao_automatica": False,
        }
    decisao = avaliacao.get("decisao") or {}
    apto = decisao.get("todos_satisfeitos") is True
    return {
        "apto": apto,
        "estado": (
            "edge_comprovado"
            if apto else "edge_nao_comprovado"
        ),
        "motivo": (
            None if apto else str(
                decisao.get("estado") or "decisao_edge_indisponivel"
            )
        ),
        "mercado": mercado,
        "regra_versao": regra,
        "coorte_operacional_avaliada": avaliacao.get(
            "coorte_operacional_avaliada"
        ),
        "criterios": decisao.get("criterios") or {},
        "promocao_automatica": False,
    }


def avaliar(
    conexao,
    mercados=None,
    regras_por_mercado=None,
    *,
    recursos=None,
    controle_v2b_ft=None,
    controle_gols_antecipados=None,
    controle_filtro_gol_ht_preciso=None,
    controle_filtro_gol_ft_preciso=None,
    controle_escanteios_ft_asiatico=None,
):
    mercados = tuple(mercados or mercados_calibrados_operacionais())
    regras = dict(regras_por_mercado or {})
    avaliacoes = {}
    resumos_gols = None
    for mercado in mercados:
        regra = regras.get(mercado) or versao_regra_operacional(mercado)
        if mercado == MERCADO_ASIATICO:
            avaliacoes[mercado] = _resumir_asiatico(
                conexao, regra, controle_escanteios_ft_asiatico
            )
        elif recursos is not None and mercado in {"gol_ft", "gol_ht"}:
            if resumos_gols is None:
                resumos_gols = _resumos_validadores_gols(conexao)
            portfolio = _resumir_portfolio_gols(
                conexao,
                mercado,
                recursos,
                controle_v2b_ft,
                resumos_gols,
                controle_gols_antecipados,
                controle_filtro_gol_ht_preciso,
                controle_filtro_gol_ft_preciso,
            )
            avaliacoes[mercado] = portfolio or _avaliar_mercado_binario(
                conexao, mercado, regra
            )
        else:
            avaliacoes[mercado] = _avaliar_mercado_binario(
                conexao, mercado, regra
            )
    favoraveis = [
        mercado for mercado, item in avaliacoes.items()
        if (item.get("decisao") or {}).get("todos_satisfeitos") is True
    ]
    return {
        "versao": VERSAO,
        "versao_referencia_preco_sem_vig": (
            VERSAO_REFERENCIA_PRECO_SEM_VIG
        ),
        "versao_avaliacao_historica_escanteios_asiaticos": (
            VERSAO_AVALIACAO_HISTORICA_ASIATICA
        ),
        "mercados": list(mercados),
        "regras_por_mercado": {
            mercado: avaliacoes[mercado]["regra_versao"]
            for mercado in mercados
        },
        "avaliacoes": avaliacoes,
        "mercados_favoraveis_para_revisao_manual": favoraveis,
        "todos_mercados_com_edge_comprovado": (
            len(favoraveis) == len(mercados) and bool(mercados)
        ),
        "uso": "auditoria_read_only",
        "alteracao_filtros": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def executar(caminho_banco=None):
    caminho = Path(caminho_banco or BANCO).resolve()
    pasta = caminho.parent
    configuracao = validar_configuracao(
        dict(dotenv_values(pasta / ".env"))
    )
    recursos = configuracao.get("recursos") or {}
    controle_v2b_ft = ler_estado_v2b_ft(
        pasta / "v2b_ft_estado.json"
    )
    controle_gols_antecipados = ler_estado_gols_antecipados(
        pasta / "gols_antecipados_estado.json"
    )
    controle_filtro_gol_ht_preciso = ler_estado_filtro_gol_ht_preciso(
        pasta / "filtro_gol_ht_antecipado_preciso_estado.json"
    )
    controle_filtro_gol_ft_preciso = ler_estado_filtro_gol_ft_preciso(
        pasta / "filtro_gol_ft_antecipado_preciso_estado.json"
    )
    controle_escanteios_ft_asiatico = ler_estado_escanteios_ft_asiatico(
        pasta / "escanteios_ft_asiatico_estado.json"
    )
    with closing(sqlite3.connect(
        caminho.as_uri() + "?mode=ro", uri=True
    )) as conexao:
        conexao.row_factory = sqlite3.Row
        return avaliar(
            conexao,
            recursos=recursos,
            controle_v2b_ft=controle_v2b_ft,
            controle_gols_antecipados=controle_gols_antecipados,
            controle_filtro_gol_ht_preciso=(
                controle_filtro_gol_ht_preciso
            ),
            controle_filtro_gol_ft_preciso=(
                controle_filtro_gol_ft_preciso
            ),
            controle_escanteios_ft_asiatico=(
                controle_escanteios_ft_asiatico
            ),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--banco", default=str(BANCO))
    argumentos = parser.parse_args()
    print(json.dumps(
        executar(argumentos.banco), ensure_ascii=False, indent=2
    ))
