"""Coorte prospectiva dos quase-candidatos seguros de Proximo Gol.

O modulo transforma duas hipoteses exploratorias em coortes futuras e
imutaveis. A inclusao usa somente informacao disponivel no instante da
decisao e acontece sem consultar resultados ou entregas. Nenhum membro e
publicado, promovido ou aplicado ao motor de sinais por este modulo.

Os bracos sao mutuamente exclusivos:

* ``odd_165_199`` testa apenas a extensao da odd curta ate o limite original
  da V10f, preservando todas as demais protecoes do challenger balanceado;
* ``atividade_com_chute`` testa apenas o bloqueio generico de atividade
  quando ja existe chute recente do lado dominante e todo o restante do
  challenger balanceado foi satisfeito.

Qualquer bloqueio de seguranca ou de qualidade de fonte fora das listas
fechadas torna o candidato inelegivel (fail closed).
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

from politica_proximo_gol_preciso import (
    MOTIVO_PRESSAO,
    MOTIVO_QUALIDADE,
    ODD_MAXIMA_EXCLUSIVA,
)
from proximo_gol_balanceado_sombra import (
    ODD_MAXIMA_BALANCEADA_EXCLUSIVA,
    avaliar,
)
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)


VERSAO_VALIDACAO = "validacao-quase-candidatos-proximo-gol-v2"
CHAVE_DEFINICAO = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"
TABELA_COORTE = "coorte_quase_candidatos_proximo_gol"
VERSAO_AUDITORIA_BLOQUEIOS = "auditoria-bloqueios-promissores-v1"

BRACO_ODD_165_199 = "odd_165_199"
BRACO_ATIVIDADE_COM_CHUTE = "atividade_com_chute"
BRACOS = (BRACO_ODD_165_199, BRACO_ATIVIDADE_COM_CHUTE)
MOTIVO_ATIVIDADE = "atividade_recente_insuficiente_gols"

TAMANHO_POR_BRACO = 60
DESENVOLVIMENTO_POR_BRACO = 42
HOLDOUT_POR_BRACO = 18
MINIMO_VALIDOS_TOTAL = 55
MINIMO_VALIDOS_DESENVOLVIMENTO = 38
MINIMO_VALIDOS_HOLDOUT = 16
CHECKPOINT_SEGURANCA = 25
TAXA_GREEN_MINIMA = {
    BRACO_ODD_165_199: 0.70,
    BRACO_ATIVIDADE_COM_CHUTE: 0.75,
}
RESULTADOS_VALIDOS = frozenset({"green", "red"})

CRITERIOS_TECNICOS = (
    "qualidade_completa",
    "minuto_valido",
    "odd_curta",
    "pressao_balanceada",
    "chute_dominante_recente",
    "pontuacao_tecnica_suficiente",
    "dominio_medio_confirmado",
)


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _json(valor, esperado):
    try:
        documento = json.loads(
            valor or ("{}" if esperado is dict else "[]")
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return documento if isinstance(documento, esperado) else None


def _linhas(conexao, consulta, parametros=()):
    cursor = conexao.execute(consulta, parametros)
    colunas = [item[0] for item in cursor.description]
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def definicao():
    nucleo = {
        "versao": VERSAO_VALIDACAO,
        "origem": {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            "status": "auditoria",
            "auditoria_versao": VERSAO_AUDITORIA_BLOQUEIOS,
        },
        "unidade_independente": (
            "primeiro_quase_candidato_elegivel_por_partida_entre_os_bracos"
        ),
        "ordem_inclusao": "datetime_criado_em_asc_sinal_id_asc",
        "relogios": {
            "auditoria": "utc_com_offset",
            "selecao": "relogio_local_naive_igual_ao_criado_em_dos_sinais",
        },
        "bracos_mutuamente_exclusivos": {
            BRACO_ODD_165_199: {
                "hipotese": (
                    "estender_apenas_odd_curta_de_165_ate_199_exclusivo"
                ),
                "odd": [ODD_MAXIMA_BALANCEADA_EXCLUSIVA,
                        ODD_MAXIMA_EXCLUSIVA],
                "limite_superior_exclusivo": True,
                "bloqueios_permitidos": sorted({
                    MOTIVO_PRESSAO, MOTIVO_QUALIDADE,
                }),
                "bloqueio_obrigatorio": MOTIVO_PRESSAO,
                "falha_tecnica_unica": "odd_curta",
                "taxa_green_minima": TAXA_GREEN_MINIMA[BRACO_ODD_165_199],
            },
            BRACO_ATIVIDADE_COM_CHUTE: {
                "hipotese": (
                    "relaxar_apenas_atividade_generica_com_chute_dominante"
                ),
                "odd": [1.40, ODD_MAXIMA_BALANCEADA_EXCLUSIVA],
                "limite_superior_exclusivo": True,
                "bloqueios_permitidos": sorted({
                    MOTIVO_PRESSAO, MOTIVO_QUALIDADE, MOTIVO_ATIVIDADE,
                }),
                "bloqueios_obrigatorios": sorted({
                    MOTIVO_PRESSAO, MOTIVO_ATIVIDADE,
                }),
                "falhas_tecnicas": [],
                "taxa_green_minima": (
                    TAXA_GREEN_MINIMA[BRACO_ATIVIDADE_COM_CHUTE]
                ),
            },
        },
        "protecao_fail_closed": (
            "qualquer_bloqueio_fora_da_lista_fechada_exclui_o_candidato"
        ),
        "coorte_fixa_por_braco": TAMANHO_POR_BRACO,
        "desenvolvimento_por_braco": DESENVOLVIMENTO_POR_BRACO,
        "holdout_por_braco": HOLDOUT_POR_BRACO,
        "minimo_validos_total_por_braco": MINIMO_VALIDOS_TOTAL,
        "minimo_validos_desenvolvimento_por_braco": (
            MINIMO_VALIDOS_DESENVOLVIMENTO
        ),
        "minimo_validos_holdout_por_braco": MINIMO_VALIDOS_HOLDOUT,
        "checkpoint_seguranca_por_braco": CHECKPOINT_SEGURANCA,
        "referencia_preco": "probabilidade_conservadora_1_sobre_odd",
        "criterio_favoravel": (
            "amostras_minimas_taxa_green_alvo_roi_total_ic95_inferior_"
            "positivo_roi_dev_holdout_positivos_e_residuo_1_sobre_odd_"
            "total_e_holdout_ic95_inferior_positivo"
        ),
        "criterio_alerta_desfavoravel": (
            "limite_superior_ic95_roi_no_checkpoint_25_abaixo_de_zero"
        ),
        "usa_resultados_na_selecao": False,
        "telegram": False,
        "telegram_oficial": False,
        "aplicacao_sinais": False,
        "promocao_automatica": False,
        "reativacao_automatica": False,
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


def _criar_estrutura(conexao):
    conexao.execute(
        "CREATE TABLE IF NOT EXISTS metadados "
        "(chave TEXT PRIMARY KEY, valor TEXT NOT NULL)"
    )
    conexao.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABELA_COORTE} (
            definicao_sha256 TEXT NOT NULL,
            braco TEXT NOT NULL,
            sinal_id INTEGER NOT NULL,
            partida_id TEXT NOT NULL,
            ordem_braco INTEGER NOT NULL,
            ordem_global INTEGER NOT NULL,
            incluido_em TEXT NOT NULL,
            odd REAL NOT NULL,
            candidato_json TEXT NOT NULL,
            avaliacao_json TEXT NOT NULL,
            PRIMARY KEY(definicao_sha256, sinal_id),
            UNIQUE(definicao_sha256, partida_id),
            UNIQUE(definicao_sha256, braco, ordem_braco),
            UNIQUE(definicao_sha256, ordem_global),
            CHECK(braco IN ('{BRACO_ODD_165_199}',
                            '{BRACO_ATIVIDADE_COM_CHUTE}'))
        )
    """)


def registrar_ou_validar_definicao(conexao, registrado_em=None):
    _criar_estrutura(conexao)
    esperada = definicao()
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha[0])
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        if divergencias:
            raise RuntimeError(
                "Ancora dos quase-candidatos de Proximo Gol inconsistente: "
                + ",".join(divergencias)
            )
        return existente
    instante = registrado_em or datetime.now(timezone.utc)
    if isinstance(instante, datetime):
        if instante.tzinfo is None:
            instante_local = instante.replace(microsecond=0)
            instante_utc = instante.astimezone().astimezone(
                timezone.utc
            ).replace(microsecond=0)
        else:
            instante_local = instante.astimezone().replace(
                tzinfo=None, microsecond=0
            )
            instante_utc = instante.astimezone(timezone.utc).replace(
                microsecond=0
            )
        registrado_utc = instante_utc.isoformat()
        relogio_sinais = instante_local.isoformat()
    else:
        # Compatibilidade defensiva para chamadas externas antigas. O formato
        # textual fica auditável, mas produção sempre fornece datetime.
        registrado_utc = str(instante)
        relogio_sinais = str(instante)
    documento = {
        **esperada,
        "registrado_em": registrado_utc,
        "registrado_em_relogio_sinais": relogio_sinais,
    }
    with conexao:
        conexao.execute(
            "INSERT INTO metadados(chave,valor) VALUES (?,?)",
            (
                CHAVE_DEFINICAO,
                json.dumps(documento, ensure_ascii=False, sort_keys=True),
            ),
        )
    return documento


def _carregar_ancora(conexao):
    tabela = conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadados'"
    ).fetchone()
    if tabela is None:
        return None
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is None:
        return None
    documento = json.loads(linha[0])
    esperada = definicao()
    divergencias = [
        campo for campo, valor in esperada.items()
        if documento.get(campo) != valor
    ]
    if divergencias:
        raise RuntimeError(
            "Ancora dos quase-candidatos de Proximo Gol inconsistente: "
            + ",".join(divergencias)
        )
    return documento


def _candidato_da_linha(linha):
    features = _json(linha.get("features_json"), dict)
    motivos = _json(linha.get("motivos_json"), list)
    if features is None or motivos is None:
        return None
    auditoria = features.get("auditoria_bloqueio")
    if not isinstance(auditoria, dict):
        return None
    bloqueios = auditoria.get("bloqueios_originais")
    if not isinstance(bloqueios, list):
        return None
    return {
        "id": int(linha["id"]),
        "partida_id": linha["partida_id"],
        "snapshot_id": int(linha["snapshot_id"]),
        "criado_em": str(linha.get("criado_em") or ""),
        "mercado": linha.get("mercado"),
        "linha": linha.get("linha"),
        "odd": linha.get("odd"),
        "pontuacao_tecnica": linha.get("pontuacao_tecnica"),
        "regra_versao": linha.get("regra_versao"),
        "regra_fingerprint": linha.get("regra_fingerprint"),
        "motivos": motivos,
        "bloqueios": sorted({
            str(item).strip() for item in bloqueios if str(item).strip()
        }),
        "features": features,
        "status": linha.get("status"),
    }


def classificar_braco(candidato):
    """Classifica usando somente os dados congelados da decisao."""
    if not isinstance(candidato, dict):
        return None
    features = candidato.get("features")
    if not isinstance(features, dict):
        return None
    auditoria = features.get("auditoria_bloqueio")
    if not isinstance(auditoria, dict):
        return None
    if (
        candidato.get("mercado") != "proximo_gol"
        or candidato.get("regra_versao")
        != VERSAO_PROXIMO_GOL_FILTRO_PRECISO
        or candidato.get("status") != "auditoria"
        or auditoria.get("versao") != VERSAO_AUDITORIA_BLOQUEIOS
        or auditoria.get("origem_status") != "rejeitado"
        or auditoria.get("aplicacao_sinais") is not False
        or auditoria.get("telegram") is not False
        or auditoria.get("calibracao") is not False
    ):
        return None
    bloqueios = frozenset(
        str(item).strip() for item in candidato.get("bloqueios") or []
        if str(item).strip()
    )
    if not bloqueios:
        return None
    odd = _numero(candidato.get("odd"))
    if odd is None:
        return None
    avaliacao = avaliar(candidato)
    criterios = avaliacao.get("criterios") or {}
    tecnicos_sem_odd = all(
        bool(criterios.get(criterio))
        for criterio in CRITERIOS_TECNICOS
        if criterio != "odd_curta"
    )
    permitidos_odd = frozenset({MOTIVO_PRESSAO, MOTIVO_QUALIDADE})
    if (
        ODD_MAXIMA_BALANCEADA_EXCLUSIVA <= odd < ODD_MAXIMA_EXCLUSIVA
        and MOTIVO_PRESSAO in bloqueios
        and bloqueios <= permitidos_odd
        and tecnicos_sem_odd
        and not bool(criterios.get("odd_curta"))
        and bool(criterios.get("somente_bloqueios_pressao_qualidade"))
    ):
        return {
            "braco": BRACO_ODD_165_199,
            "criterios": criterios,
            "medidas": avaliacao.get("medidas") or {},
            "bloqueios_originais": sorted(bloqueios),
        }

    permitidos_atividade = frozenset({
        MOTIVO_PRESSAO, MOTIVO_QUALIDADE, MOTIVO_ATIVIDADE,
    })
    if (
        1.40 <= odd < ODD_MAXIMA_BALANCEADA_EXCLUSIVA
        and {MOTIVO_PRESSAO, MOTIVO_ATIVIDADE} <= bloqueios
        and bloqueios <= permitidos_atividade
        and all(bool(criterios.get(item)) for item in CRITERIOS_TECNICOS)
    ):
        return {
            "braco": BRACO_ATIVIDADE_COM_CHUTE,
            "criterios": criterios,
            "medidas": avaliacao.get("medidas") or {},
            "bloqueios_originais": sorted(bloqueios),
        }
    return None


def sincronizar_coorte(conexao, agora=None):
    """Congela membros em ordem causal sem ler resultados ou entregas."""
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "estado": "ancora_ausente",
            "inseridos": 0,
            "candidatos": 0,
            "faltam": TAMANHO_POR_BRACO * len(BRACOS),
        }
    _criar_estrutura(conexao)
    sha = documento["definicao_sha256"]
    existentes = _linhas(
        conexao,
        f"SELECT sinal_id,partida_id,braco,ordem_braco,ordem_global "
        f"FROM {TABELA_COORTE} WHERE definicao_sha256=? "
        "ORDER BY ordem_global",
        (sha,),
    )
    por_braco = {braco: 0 for braco in BRACOS}
    ids = set()
    partidas = set()
    for item in existentes:
        braco = str(item["braco"])
        if braco not in por_braco:
            raise RuntimeError("braco_quase_candidato_desconhecido")
        por_braco[braco] += 1
        ids.add(int(item["sinal_id"]))
        partidas.add(str(item["partida_id"]))
    if all(por_braco[braco] >= TAMANHO_POR_BRACO for braco in BRACOS):
        return {
            "estado": "coortes_fechadas",
            "inseridos": 0,
            "candidatos": len(existentes),
            "por_braco": por_braco,
            "faltam": 0,
            "definicao_sha256": sha,
        }
    linhas = _linhas(
        conexao,
        """
        SELECT id,partida_id,snapshot_id,criado_em,mercado,linha,odd,
               pontuacao_tecnica,regra_versao,regra_fingerprint,
               motivos_json,features_json,status
        FROM sinais
        WHERE datetime(criado_em)>=datetime(?)
          AND mercado='proximo_gol' AND status='auditoria'
          AND regra_versao=?
          AND json_extract(features_json,'$.auditoria_bloqueio.versao')=?
        ORDER BY datetime(criado_em),id
        """,
        (
            documento["registrado_em_relogio_sinais"],
            VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            VERSAO_AUDITORIA_BLOQUEIOS,
        ),
    )
    instante = agora or datetime.now(timezone.utc)
    if isinstance(instante, datetime):
        instante = instante.replace(microsecond=0).isoformat()
    inseridos = invalidos = 0
    ordem_global = len(existentes)
    with conexao:
        for linha in linhas:
            if all(
                por_braco[braco] >= TAMANHO_POR_BRACO
                for braco in BRACOS
            ):
                break
            sinal_id = int(linha["id"])
            partida_id = str(linha["partida_id"])
            if sinal_id in ids or partida_id in partidas:
                continue
            candidato = _candidato_da_linha(linha)
            if candidato is None:
                invalidos += 1
                continue
            classificacao = classificar_braco(candidato)
            if classificacao is None:
                continue
            braco = classificacao["braco"]
            if por_braco[braco] >= TAMANHO_POR_BRACO:
                continue
            odd = _numero(candidato.get("odd"))
            if odd is None or odd <= 1.0:
                invalidos += 1
                continue
            congelado = json.dumps(
                candidato, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            )
            avaliacao_json = json.dumps(
                classificacao, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            )
            cursor = conexao.execute(f"""
                INSERT OR IGNORE INTO {TABELA_COORTE}(
                    definicao_sha256,braco,sinal_id,partida_id,
                    ordem_braco,ordem_global,incluido_em,odd,
                    candidato_json,avaliacao_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                sha, braco, sinal_id, partida_id,
                por_braco[braco] + 1, ordem_global + 1,
                str(instante), odd, congelado, avaliacao_json,
            ))
            if cursor.rowcount:
                ids.add(sinal_id)
                partidas.add(partida_id)
                por_braco[braco] += 1
                ordem_global += 1
                inseridos += 1
    faltam_por_braco = {
        braco: max(TAMANHO_POR_BRACO - por_braco[braco], 0)
        for braco in BRACOS
    }
    return {
        "estado": (
            "coortes_fechadas" if not any(faltam_por_braco.values())
            else "coletando"
        ),
        "inseridos": inseridos,
        "candidatos": sum(por_braco.values()),
        "por_braco": por_braco,
        "faltam_por_braco": faltam_por_braco,
        "faltam": sum(faltam_por_braco.values()),
        "linhas_json_invalidas": invalidos,
        "definicao_sha256": sha,
    }


def _intervalo_95(valores):
    if len(valores) < 2:
        return None
    media = statistics.fmean(valores)
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    return [round(media - 1.96 * erro, 4), round(media + 1.96 * erro, 4)]


def _metricas(itens):
    validos = [
        item for item in itens
        if item.get("resultado") in RESULTADOS_VALIDOS
        and item.get("retorno_unidades") is not None
        and item.get("odd") is not None
    ]
    retornos = [float(item["retorno_unidades"]) for item in validos]
    residuos = [
        (1.0 if item["resultado"] == "green" else 0.0)
        - 1.0 / float(item["odd"])
        for item in validos
    ]
    greens = sum(item["resultado"] == "green" for item in validos)
    lucro = sum(retornos)
    pendentes = sum(item.get("resultado") is None for item in itens)
    return {
        "candidatos": len(itens),
        "validos": len(validos),
        "greens": greens,
        "reds": len(validos) - greens,
        "pendentes": pendentes,
        "invalidos": len(itens) - len(validos) - pendentes,
        "taxa_green": round(greens / len(validos), 4) if validos else None,
        "lucro_unidades": round(lucro, 4),
        "roi": round(lucro / len(validos), 4) if validos else None,
        "intervalo_roi_95": _intervalo_95(retornos),
        "referencia_1_sobre_odd": {
            "cobertura": len(validos),
            "taxa_cobertura": 1.0 if validos else None,
            "probabilidade_media": (
                round(statistics.fmean(
                    1.0 / float(item["odd"]) for item in validos
                ), 4) if validos else None
            ),
            "desvio_observado_menos_mercado": (
                round(statistics.fmean(residuos), 4) if residuos else None
            ),
            "intervalo_desvio_95": _intervalo_95(residuos),
        },
    }


def _carregar_coorte(conexao, documento):
    tabela = conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (TABELA_COORTE,),
    ).fetchone()
    if tabela is None:
        return []
    linhas = _linhas(conexao, f"""
        SELECT c.braco,c.sinal_id,c.partida_id,c.ordem_braco,
               c.ordem_global,c.odd,c.candidato_json,c.avaliacao_json,
               r.resultado,r.retorno_unidades
        FROM {TABELA_COORTE} c
        LEFT JOIN resultados_sinais r ON r.sinal_id=c.sinal_id
        WHERE c.definicao_sha256=? ORDER BY c.ordem_global
    """, (documento["definicao_sha256"],))
    itens = []
    partidas = set()
    ordens = {braco: 0 for braco in BRACOS}
    for ordem_global, linha in enumerate(linhas, 1):
        braco = str(linha.get("braco") or "")
        if braco not in ordens:
            raise RuntimeError("braco_quase_candidato_desconhecido")
        ordens[braco] += 1
        if (
            int(linha.get("ordem_global") or 0) != ordem_global
            or int(linha.get("ordem_braco") or 0) != ordens[braco]
        ):
            raise RuntimeError("ordem_coorte_quase_candidato_inconsistente")
        candidato = _json(linha.get("candidato_json"), dict)
        congelada = _json(linha.get("avaliacao_json"), dict)
        if candidato is None or congelada is None:
            raise RuntimeError("json_coorte_quase_candidato_invalido")
        classificacao = classificar_braco(candidato)
        partida_id = str(linha["partida_id"])
        if (
            int(candidato.get("id") or 0) != int(linha["sinal_id"])
            or str(candidato.get("partida_id")) != partida_id
            or partida_id in partidas
            or classificacao is None
            or classificacao.get("braco") != braco
            or classificacao != congelada
            or not math.isclose(
                float(candidato.get("odd")), float(linha["odd"]),
                abs_tol=1e-9,
            )
        ):
            raise RuntimeError("membro_coorte_quase_candidato_invalido")
        partidas.add(partida_id)
        resultado = linha.get("resultado")
        if resultado is not None:
            resultado = str(resultado).casefold()
        itens.append({
            "braco": braco,
            "sinal_id": int(linha["sinal_id"]),
            "partida_id": partida_id,
            "odd": float(linha["odd"]),
            "resultado": resultado,
            "retorno_unidades": linha.get("retorno_unidades"),
            "candidato": candidato,
        })
    return itens


def _resumir_braco(itens, braco):
    membros = [item for item in itens if item["braco"] == braco]
    total = _metricas(membros)
    desenvolvimento = _metricas(
        membros[:DESENVOLVIMENTO_POR_BRACO]
    )
    holdout = _metricas(
        membros[DESENVOLVIMENTO_POR_BRACO:TAMANHO_POR_BRACO]
    )
    checkpoint = _metricas(membros[:CHECKPOINT_SEGURANCA])
    intervalo_checkpoint = checkpoint.get("intervalo_roi_95")
    alerta_desfavoravel = bool(
        checkpoint["validos"] >= CHECKPOINT_SEGURANCA
        and isinstance(intervalo_checkpoint, (list, tuple))
        and intervalo_checkpoint[1] < 0
    )
    referencia = total["referencia_1_sobre_odd"]
    referencia_holdout = holdout["referencia_1_sobre_odd"]
    intervalo_ref = referencia.get("intervalo_desvio_95")
    intervalo_ref_holdout = referencia_holdout.get("intervalo_desvio_95")
    gate_preco = bool(
        referencia.get("taxa_cobertura") == 1.0
        and isinstance(intervalo_ref, (list, tuple))
        and intervalo_ref[0] > 0
        and referencia_holdout.get("taxa_cobertura") == 1.0
        and isinstance(intervalo_ref_holdout, (list, tuple))
        and intervalo_ref_holdout[0] > 0
    )
    coorte_fechada = len(membros) >= TAMANHO_POR_BRACO
    resultados_completos = bool(
        coorte_fechada and total["pendentes"] == 0
    )
    intervalo_roi = total.get("intervalo_roi_95")
    if not coorte_fechada:
        decisao = "aguardando_amostra_futura"
    elif total["pendentes"]:
        decisao = "aguardando_resultados"
    elif (
        total["validos"] >= MINIMO_VALIDOS_TOTAL
        and desenvolvimento["validos"] >= MINIMO_VALIDOS_DESENVOLVIMENTO
        and holdout["validos"] >= MINIMO_VALIDOS_HOLDOUT
        and total.get("taxa_green") is not None
        and total["taxa_green"] >= TAXA_GREEN_MINIMA[braco]
        and total.get("roi") is not None and total["roi"] > 0
        and isinstance(intervalo_roi, (list, tuple))
        and intervalo_roi[0] > 0
        and desenvolvimento.get("roi") is not None
        and desenvolvimento["roi"] > 0
        and holdout.get("roi") is not None and holdout["roi"] > 0
        and gate_preco
    ):
        decisao = "favoravel_para_revisao_manual"
    else:
        decisao = "inconclusiva_ou_desfavoravel"
    return {
        "braco": braco,
        **total,
        "estado": "encerrada" if resultados_completos else "coletando",
        "decisao": decisao,
        "apto_revisao": decisao == "favoravel_para_revisao_manual",
        "coorte_fechada": coorte_fechada,
        "resultados_completos": resultados_completos,
        "tamanho_coorte": TAMANHO_POR_BRACO,
        "faltam": max(TAMANHO_POR_BRACO - len(membros), 0),
        "taxa_green_minima": TAXA_GREEN_MINIMA[braco],
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "checkpoint_seguranca": checkpoint,
        "alerta_desfavoravel": alerta_desfavoravel,
        "gate_preco_conservador": {
            "referencia": "1_sobre_odd_com_margem",
            "total": referencia,
            "holdout": referencia_holdout,
            "satisfeito": gate_preco,
        },
    }


def resumir_validacao(conexao):
    documento = _carregar_ancora(conexao)
    if documento is None:
        return {
            "versao": VERSAO_VALIDACAO,
            "saudavel": True,
            "estado": "nao_registrada",
            "decisao": "aguardando_ancora",
            "apto_revisao": False,
            "promocao_automatica": False,
        }
    coorte = _carregar_coorte(conexao, documento)
    bracos = {
        braco: _resumir_braco(coorte, braco) for braco in BRACOS
    }
    favoraveis = [
        braco for braco, resumo in bracos.items()
        if resumo["apto_revisao"]
    ]
    encerrados = all(
        resumo["resultados_completos"] for resumo in bracos.values()
    )
    return {
        "versao": VERSAO_VALIDACAO,
        "saudavel": True,
        "estado": "encerrada" if encerrados else "coletando",
        "decisao": (
            "hipotese_favoravel_para_revisao_manual" if favoraveis
            else "aguardando_coortes_futuras" if not encerrados
            else "inconclusiva_ou_desfavoravel"
        ),
        "apto_revisao": bool(favoraveis),
        "bracos_favoraveis": favoraveis,
        "bracos": bracos,
        "candidatos": len(coorte),
        "tamanho_total": TAMANHO_POR_BRACO * len(BRACOS),
        "faltam": sum(resumo["faltam"] for resumo in bracos.values()),
        "registrado_em": documento["registrado_em"],
        "registrado_em_relogio_sinais": (
            documento["registrado_em_relogio_sinais"]
        ),
        "definicao_sha256": documento["definicao_sha256"],
        "unidade_independente": documento["unidade_independente"],
        "selecao_antes_resultado": True,
        "usa_resultados_na_selecao": False,
        "telegram": False,
        "telegram_oficial": False,
        "aplicacao_sinais": False,
        "promocao_automatica": False,
        "politica_seguranca": {
            "fail_closed": True,
            "cartao_vermelho_relaxado": False,
            "fonte_ruim_relaxada": False,
            "odd_vencida_relaxada": False,
            "outros_metodos_inalterados": True,
        },
    }


def resumir_validacao_arquivo(caminho):
    caminho = Path(caminho)
    if not caminho.is_file():
        return {
            "versao": VERSAO_VALIDACAO,
            "saudavel": False,
            "estado": "banco_ausente",
            "decisao": "indisponivel",
            "apto_revisao": False,
            "promocao_automatica": False,
        }
    conexao = None
    try:
        conexao = sqlite3.connect(
            caminho.resolve().as_uri() + "?mode=ro", uri=True, timeout=10
        )
        return resumir_validacao(conexao)
    except (
        OSError, sqlite3.Error, json.JSONDecodeError, RuntimeError, ValueError
    ) as erro:
        return {
            "versao": VERSAO_VALIDACAO,
            "saudavel": False,
            "estado": "auditoria_falhou",
            "decisao": "indisponivel",
            "erro": type(erro).__name__,
            "apto_revisao": False,
            "promocao_automatica": False,
        }
    finally:
        if conexao is not None:
            conexao.close()
