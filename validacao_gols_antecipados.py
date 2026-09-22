"""Âncora e coorte prospectiva fixa dos métodos de gols antecipados."""

import hashlib
import json
import math
import statistics
from datetime import datetime

from gols_antecipados import (
    MINUTO_MAXIMO_FT,
    MINUTO_MAXIMO_HT,
    MINUTO_MAXIMO_2T,
    MINUTO_MINIMO,
    MINUTO_MINIMO_2T,
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
    VERSAO_GOL_HT_ANTECIPADO,
    VERSAO_POLITICA,
)
from linhagem_gols_antecipados import calcular_linhagem_gols_antecipados


VERSAO_VALIDACAO = "validacao-gols-antecipados-prospectiva-v3"
VERSAO_POLITICA_VALIDACAO = "politica-validacao-gols-antecipados-v3"
TAMANHO_COORTE = 100
TAMANHO_DESENVOLVIMENTO = 70
TAMANHO_HOLDOUT = 30
MINIMO_VALIDOS_TOTAL = 95
MINIMO_VALIDOS_HOLDOUT = 28
CHAVE_DEFINICAO = f"exploracao_sombra_definicao:{VERSAO_VALIDACAO}"
CHAVE_POLITICA = f"exploracao_sombra_politica:{VERSAO_VALIDACAO}"
VERSOES_AVALIADAS = (
    VERSAO_GOL_HT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO,
    VERSAO_GOL_FT_ANTECIPADO_2T,
)

CHAVES_DIAGNOSTICO_POR_VERSAO = {
    VERSAO_GOL_HT_ANTECIPADO: "gol_ht_antecipado",
    VERSAO_GOL_FT_ANTECIPADO: "gol_ft_antecipado_pre_live",
    VERSAO_GOL_FT_ANTECIPADO_2T: "gol_ft_antecipado_2t",
}


def _com_hash(nucleo, campo):
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        campo: hashlib.sha256(canonico.encode("utf-8")).hexdigest(),
    }


def definicao_gols_antecipados():
    linhagem = calcular_linhagem_gols_antecipados()
    return _com_hash({
        "versao": VERSAO_VALIDACAO,
        "politica_geracao": VERSAO_POLITICA,
        "versoes_avaliadas": list(VERSOES_AVALIADAS),
        "linhagem_sha256": linhagem["fingerprint"],
        "linhagem_componentes": linhagem["componentes"],
        "populacao": "somente_analises_telegram_entregues_pos_ancora",
        "independencia": "primeira_decisao_por_partida_mercado_braco",
        "tamanho_coorte_fixa_por_braco": TAMANHO_COORTE,
        "desenvolvimento": TAMANHO_DESENVOLVIMENTO,
        "holdout_final": TAMANHO_HOLDOUT,
        "historico_pre_ancora": "observacional_nao_validante",
        "telegram_oficial": False,
        "promocao_automatica": False,
    }, "definicao_sha256")


def politica_validacao_gols_antecipados():
    return _com_hash({
        "versao": VERSAO_POLITICA_VALIDACAO,
        "experimento": VERSAO_VALIDACAO,
        "tamanho_coorte_fixa_por_braco": TAMANHO_COORTE,
        "minimo_resultados_validos_total": MINIMO_VALIDOS_TOTAL,
        "tamanho_holdout_final": TAMANHO_HOLDOUT,
        "minimo_resultados_validos_holdout": MINIMO_VALIDOS_HOLDOUT,
        "confianca": 0.95,
        "metodo_intervalo_roi": "media_normal_bilateral_95",
        "criterios_favoraveis": [
            "coorte_fixa_encerrada",
            "sem_pendencias",
            "linhagem_homogenea",
            "roi_total_maior_que_zero",
            "limite_inferior_ic95_roi_total_maior_que_zero",
            "roi_desenvolvimento_maior_que_zero",
            "roi_holdout_maior_que_zero",
        ],
        "telegram_oficial": False,
        "promocao_automatica": False,
        "decisao": "somente_revisao_independente",
    }, "politica_sha256")


def _registrar_ou_validar(conexao, chave, esperado, registrado_em=None):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        existente = json.loads(linha["valor"])
        for campo, valor in esperado.items():
            if existente.get(campo) != valor:
                raise RuntimeError(
                    "Gols antecipados divergem da ancora imutavel SQLite; "
                    "crie uma nova versao antes de coletar."
                )
        return existente
    documento = dict(esperado)
    documento["registrado_em"] = (
        registrado_em or datetime.now()
    ).replace(microsecond=0).isoformat()
    with conexao:
        conexao.execute(
            "INSERT INTO metadados(chave, valor) VALUES (?, ?)",
            (chave, json.dumps(documento, ensure_ascii=False, sort_keys=True)),
        )
    return documento


def registrar_ou_validar_gols_antecipados(conexao, registrado_em=None):
    return {
        "definicao": _registrar_ou_validar(
            conexao, CHAVE_DEFINICAO, definicao_gols_antecipados(), registrado_em
        ),
        "politica": _registrar_ou_validar(
            conexao, CHAVE_POLITICA,
            politica_validacao_gols_antecipados(), registrado_em,
        ),
    }


def auditar_validacao_gols_antecipados(conexao, exigir_registro=False):
    """Verifica âncoras, código atual e homogeneidade sem alterar o banco."""
    esperados = {
        CHAVE_DEFINICAO: definicao_gols_antecipados(),
        CHAVE_POLITICA: politica_validacao_gols_antecipados(),
    }
    ausentes = []
    divergencias = []
    documentos = {}
    for chave, esperado in esperados.items():
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave,)
        ).fetchone()
        if linha is None:
            ausentes.append(chave)
            continue
        try:
            documento = json.loads(linha["valor"])
        except (TypeError, json.JSONDecodeError):
            divergencias.append(f"{chave}:json_invalido")
            continue
        documentos[chave] = documento
        for campo, valor in esperado.items():
            if documento.get(campo) != valor:
                divergencias.append(f"{chave}:{campo}")
    sinais_existentes = int(conexao.execute(
        """
        SELECT COUNT(*) FROM sinais
        WHERE json_extract(features_json, '$.exploracao_sombra.versao')
          IN (?, ?, ?)
        """,
        VERSOES_AVALIADAS,
    ).fetchone()[0] or 0)
    registro_obrigatorio = bool(exigir_registro or sinais_existentes)
    resumo = (
        resumir_validacao_gols_antecipados(conexao)
        if not ausentes and not divergencias
        else {"estado": "invalido", "por_braco": {}}
    )
    bracos_inconsistentes = sorted(
        versao for versao, item in (resumo.get("por_braco") or {}).items()
        if item.get("linhagem_homogenea") is False
    )
    saudavel = bool(
        not divergencias
        and not bracos_inconsistentes
        and (not ausentes or not registro_obrigatorio)
    )
    if saudavel and ausentes:
        estado = "aguardando_primeiro_registro"
    elif saudavel:
        estado = "valida"
    elif ausentes:
        estado = "nao_registrada"
    else:
        estado = "inconsistente"
    return {
        "saudavel": saudavel,
        "estado": estado,
        "motivo": None if saudavel else "validacao_gols_antecipados_inconsistente",
        "versao": VERSAO_VALIDACAO,
        "registrada": not ausentes,
        "metadados_ausentes": ausentes,
        "divergencias": divergencias,
        "sinais_antecipados_existentes": sinais_existentes,
        "bracos_linhagem_inconsistente": bracos_inconsistentes,
        "linhagem_sha256": (
            (documentos.get(CHAVE_DEFINICAO) or {}).get("linhagem_sha256")
        ),
        "protegida": True,
        "promocao_automatica": False,
    }


def _intervalo_roi(retornos):
    if len(retornos) < 2:
        return None
    media = statistics.fmean(retornos)
    erro = statistics.stdev(retornos) / math.sqrt(len(retornos))
    return [round(media - 1.96 * erro, 4), round(media + 1.96 * erro, 4)]


def _metricas(linhas):
    validas = [
        linha for linha in linhas
        if linha["resultado"] in ("green", "half_green", "red", "half_red")
        and linha["retorno_unidades"] is not None
    ]
    retornos = [float(linha["retorno_unidades"]) for linha in validas]
    lucro = round(sum(retornos), 4)
    return {
        "total": len(linhas),
        "validos": len(validas),
        "greens": sum(
            linha["resultado"] in ("green", "half_green") for linha in validas
        ),
        "reds": sum(
            linha["resultado"] in ("red", "half_red") for linha in validas
        ),
        "pendentes": sum(linha["resultado"] is None for linha in linhas),
        "invalidos": len(linhas) - len(validas)
        - sum(linha["resultado"] is None for linha in linhas),
        "lucro_unidades": lucro,
        "roi": round(lucro / len(validas), 4) if validas else None,
        "intervalo_roi_95": _intervalo_roi(retornos),
    }


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _versoes_no_escopo(diagnostico):
    """Mapeia um diagnóstico global apenas aos braços naquela janela."""
    minuto = _numero((diagnostico or {}).get("minuto"))
    if minuto is None:
        return ()
    versoes = []
    if MINUTO_MINIMO <= minuto <= MINUTO_MAXIMO_HT:
        versoes.append(VERSAO_GOL_HT_ANTECIPADO)
    if MINUTO_MINIMO <= minuto <= MINUTO_MAXIMO_FT:
        versoes.append(VERSAO_GOL_FT_ANTECIPADO)
    if MINUTO_MINIMO_2T <= minuto <= MINUTO_MAXIMO_2T:
        versoes.append(VERSAO_GOL_FT_ANTECIPADO_2T)
    return tuple(versoes)


def _funil_vazio(versao, *, telemetria_disponivel, registros_invalidos=0):
    return {
        "versao": "funil-gerador-gols-antecipados-v1",
        "versao_metodo": versao,
        "estado": (
            "sem_decisoes_no_escopo"
            if telemetria_disponivel else "telemetria_indisponivel"
        ),
        "telemetria_disponivel": bool(telemetria_disponivel),
        "decisoes_observadas": 0,
        "decisoes_geradas": 0,
        "decisoes_bloqueadas": 0,
        "partidas_com_decisao": 0,
        "partidas_com_alguma_geracao": 0,
        "partidas_sem_geracao": 0,
        "motivos_bloqueio_decisoes": {},
        "motivos_ultima_decisao_partidas_sem_geracao": {},
        "gargalo_atual": None,
        "primeira_decisao_em": None,
        "ultima_decisao_em": None,
        "registros_json_invalidos": int(registros_invalidos),
        "cobertura_historica_parcial": True,
        "criterio_independencia": (
            "uma_partida_conta_como_gerada_se_qualquer_decisao_gerou"
        ),
        "consulta_resultados": False,
        "consulta_entregas": False,
        "altera_sinais": False,
        "altera_telegram": False,
        "promocao_automatica": False,
    }


def _funis_gerador_pos_ancora(conexao, inicio):
    """Consolida a primeira barreira do gerador sem olhar o desfecho."""
    tabela = conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshots'"
    ).fetchone()
    if tabela is None:
        return {
            versao: _funil_vazio(versao, telemetria_disponivel=False)
            for versao in VERSOES_AVALIADAS
        }
    colunas = {
        linha[1] for linha in conexao.execute("PRAGMA table_info(snapshots)")
    }
    if not {"partida_id", "coletado_em", "qualidade_json"} <= colunas:
        return {
            versao: _funil_vazio(versao, telemetria_disponivel=False)
            for versao in VERSOES_AVALIADAS
        }
    linhas = conexao.execute(
        """
        SELECT partida_id,coletado_em,qualidade_json
        FROM snapshots
        WHERE datetime(coletado_em)>=datetime(?)
        ORDER BY datetime(coletado_em),id
        """,
        (inicio,),
    ).fetchall()
    decisoes = {versao: [] for versao in VERSOES_AVALIADAS}
    registros_invalidos = 0
    registros_telemetria = 0
    for linha in linhas:
        try:
            qualidade = json.loads(linha["qualidade_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            registros_invalidos += 1
            continue
        diagnostico = (
            qualidade.get("diagnostico_gols_antecipados")
            if isinstance(qualidade, dict) else None
        )
        if not isinstance(diagnostico, dict):
            continue
        por_braco = diagnostico.get("por_braco")
        if not isinstance(por_braco, dict):
            registros_invalidos += 1
            continue
        registros_telemetria += 1
        global_decisao = por_braco.get("global")
        escopo_global = set(_versoes_no_escopo(diagnostico))
        for versao, chave in CHAVES_DIAGNOSTICO_POR_VERSAO.items():
            decisao = por_braco.get(chave)
            if not isinstance(decisao, dict):
                decisao = (
                    global_decisao
                    if versao in escopo_global
                    and isinstance(global_decisao, dict)
                    else None
                )
            if not isinstance(decisao, dict):
                continue
            decisoes[versao].append({
                "partida_id": int(linha["partida_id"]),
                "coletado_em": linha["coletado_em"],
                "estado": str(decisao.get("estado") or "desconhecido"),
                "motivo": str(
                    decisao.get("motivo")
                    or decisao.get("estado")
                    or "motivo_ausente"
                ),
            })

    funis = {}
    telemetria_disponivel = registros_telemetria > 0
    for versao in VERSOES_AVALIADAS:
        itens = decisoes[versao]
        funil = _funil_vazio(
            versao,
            telemetria_disponivel=telemetria_disponivel,
            registros_invalidos=registros_invalidos,
        )
        estados_partidas = {}
        motivos_decisoes = {}
        geradas = 0
        for item in itens:
            partida = estados_partidas.setdefault(item["partida_id"], {
                "gerada": False,
                "ultimo_motivo": None,
            })
            if item["estado"] == "gerado":
                geradas += 1
                partida["gerada"] = True
                partida["ultimo_motivo"] = None
            else:
                motivo = item["motivo"]
                motivos_decisoes[motivo] = motivos_decisoes.get(motivo, 0) + 1
                partida["ultimo_motivo"] = motivo
        motivos_partidas = {}
        partidas_geradas = 0
        for estado in estados_partidas.values():
            if estado["gerada"]:
                partidas_geradas += 1
                continue
            motivo = estado["ultimo_motivo"] or "motivo_ausente"
            motivos_partidas[motivo] = motivos_partidas.get(motivo, 0) + 1
        gargalo = None
        if motivos_partidas:
            gargalo = sorted(
                motivos_partidas.items(), key=lambda item: (-item[1], item[0])
            )[0][0]
        if itens:
            funil.update({
                "estado": "com_gerados" if partidas_geradas else "sem_gerados",
                "decisoes_observadas": len(itens),
                "decisoes_geradas": geradas,
                "decisoes_bloqueadas": len(itens) - geradas,
                "partidas_com_decisao": len(estados_partidas),
                "partidas_com_alguma_geracao": partidas_geradas,
                "partidas_sem_geracao": len(estados_partidas) - partidas_geradas,
                "motivos_bloqueio_decisoes": dict(
                    sorted(motivos_decisoes.items())
                ),
                "motivos_ultima_decisao_partidas_sem_geracao": dict(
                    sorted(motivos_partidas.items())
                ),
                "gargalo_atual": gargalo,
                "primeira_decisao_em": itens[0]["coletado_em"],
                "ultima_decisao_em": itens[-1]["coletado_em"],
            })
        funis[versao] = funil
    return funis


def _historico_observacional(conexao, versao, antes_de):
    linhas = conexao.execute(
        """
        WITH entregues AS (
          SELECT sinal_id, MIN(tentado_em) AS enviado_em
          FROM entregas_alertas
          WHERE status='entregue' AND canal LIKE '%:teste'
            AND canal NOT LIKE '%:resultado'
          GROUP BY sinal_id
        ), independentes AS (
          SELECT s.id, s.partida_id, s.mercado, s.criado_em,
                 r.resultado, r.retorno_unidades,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.partida_id, s.mercado,
                     json_extract(s.features_json,
                                  '$.exploracao_sombra.versao')
                   ORDER BY datetime(s.criado_em), s.id
                 ) AS ordem
          FROM sinais s JOIN entregues e ON e.sinal_id=s.id
          LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
          WHERE datetime(s.criado_em)<datetime(?)
            AND json_extract(s.features_json,
                             '$.exploracao_sombra.versao')=?
        )
        SELECT resultado, retorno_unidades FROM independentes
        WHERE ordem=1 ORDER BY datetime(criado_em), id
        """,
        (antes_de, versao),
    ).fetchall()
    return _metricas(linhas)


def resumir_validacao_gols_antecipados(conexao):
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_DEFINICAO,)
    ).fetchone()
    if linha is None:
        return {"estado": "nao_registrado", "por_braco": {}}
    definicao = json.loads(linha["valor"])
    inicio = definicao["registrado_em"]
    fingerprint = definicao["linhagem_sha256"]
    funis_gerador = _funis_gerador_pos_ancora(conexao, inicio)
    por_braco = {}
    for versao in VERSOES_AVALIADAS:
        todas = conexao.execute(
            """
            WITH entregues AS (
              SELECT sinal_id FROM entregas_alertas
              WHERE status='entregue' AND canal LIKE '%:teste'
                AND canal NOT LIKE '%:resultado' GROUP BY sinal_id
            ), independentes AS (
              SELECT s.id, s.partida_id, s.mercado, s.criado_em,
                     r.resultado, r.retorno_unidades,
                     json_extract(s.features_json,
                       '$.gol_antecipado.linhagem_sha256') AS linhagem,
                     ROW_NUMBER() OVER (
                       PARTITION BY s.partida_id, s.mercado,
                         json_extract(s.features_json,
                                      '$.exploracao_sombra.versao')
                       ORDER BY datetime(s.criado_em), s.id
                     ) AS ordem
              FROM sinais s JOIN entregues e ON e.sinal_id=s.id
              LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
              WHERE datetime(s.criado_em)>=datetime(?)
                AND json_extract(s.features_json,
                                 '$.exploracao_sombra.versao')=?
            )
            SELECT id, criado_em, resultado, retorno_unidades, linhagem
            FROM independentes WHERE ordem=1
            ORDER BY datetime(criado_em), id LIMIT ?
            """,
            (inicio, versao, TAMANHO_COORTE),
        ).fetchall()
        compativeis = [x for x in todas if x["linhagem"] == fingerprint]
        metricas = _metricas(compativeis)
        desenvolvimento = _metricas(compativeis[:TAMANHO_DESENVOLVIMENTO])
        holdout = _metricas(compativeis[TAMANHO_DESENVOLVIMENTO:TAMANHO_COORTE])
        linhagem_homogenea = len(compativeis) == len(todas)
        coorte_fechada = len(todas) >= TAMANHO_COORTE
        intervalo = metricas["intervalo_roi_95"]
        if not linhagem_homogenea:
            decisao = "linhagem_inconsistente"
        elif not coorte_fechada:
            decisao = "aguardando_amostra_futura"
        elif metricas["pendentes"]:
            decisao = "aguardando_resultados"
        elif (
            metricas["validos"] < MINIMO_VALIDOS_TOTAL
            or holdout["validos"] < MINIMO_VALIDOS_HOLDOUT
        ):
            decisao = "amostra_valida_insuficiente"
        elif (
            metricas["roi"] is not None and metricas["roi"] > 0
            and intervalo is not None and intervalo[0] > 0
            and desenvolvimento["roi"] is not None
            and desenvolvimento["roi"] > 0
            and holdout["roi"] is not None and holdout["roi"] > 0
        ):
            decisao = "favoravel_para_revisao_independente"
        elif intervalo is not None and intervalo[1] < 0:
            decisao = "evidencia_desfavoravel"
        else:
            decisao = "inconclusiva"
        por_braco[versao] = {
            **metricas,
            "versao": versao,
            "candidatos_coorte": len(todas),
            "tamanho_coorte": TAMANHO_COORTE,
            "faltam": max(0, TAMANHO_COORTE - len(todas)),
            "linhagem_homogenea": linhagem_homogenea,
            "linhagem_divergente": len(todas) - len(compativeis),
            "desenvolvimento": desenvolvimento,
            "holdout": holdout,
            "decisao_estatistica": decisao,
            "historico_observacional": _historico_observacional(
                conexao, versao, inicio
            ),
            "funil_gerador": funis_gerador[versao],
        }
    return {
        "estado": "coletando",
        "versao": VERSAO_VALIDACAO,
        "registrado_em": inicio,
        "linhagem_sha256": fingerprint,
        "por_braco": por_braco,
        "observabilidade_funil": {
            "versao": "funil-gerador-gols-antecipados-v1",
            "persistencia": "snapshots.qualidade_json",
            "consulta_resultados": False,
            "consulta_entregas": False,
            "altera_sinais": False,
            "altera_telegram": False,
        },
        "telegram_oficial": False,
        "promocao_automatica": False,
    }
