"""Auditoria cronologica de ligas, sem efeito operacional automatico.

Procura prejuizo persistente por liga sem transformar pequenas amostras em
blacklist. A selecao usa apenas o desenvolvimento, corrige a familia de ligas
por Bonferroni e reserva dados posteriores para conferencia. O resultado nunca
altera sinais automaticamente.
"""

import math
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from statistics import NormalDist


VERSAO_AUDITORIA_LIGAS = "auditoria-ligas-sombra-condicional-bonferroni-v2"
VERSAO_VALIDACAO_PROSPECTIVA_LIGAS = "validacao-ligas-prospectiva-v2"
CHAVE_PROSPECTIVA_PREFIXO = "auditoria_ligas_prospectiva:"
TAMANHO_COORTE_PROSPECTIVA = 100
MINIMO_EXCLUIDOS_PROSPECTIVA = 20
MERCADOS_AUDITADOS = (
    "gol_ft", "gol_ht", "proximo_gol", "proximo_escanteio",
    "escanteios_ft_asiatico",
)


def _metricas(itens):
    retornos = [float(item.get("retorno_unidades") or 0.0) for item in itens]
    return {
        "amostra": len(retornos),
        "lucro_unidades": round(sum(retornos), 4),
        "roi": round(sum(retornos) / len(retornos), 4) if retornos else None,
    }


def _media_desvio(valores):
    valores = [float(valor) for valor in valores]
    if not valores:
        return None, None
    media = sum(valores) / len(valores)
    if len(valores) < 2:
        return media, None
    variancia = sum((valor - media) ** 2 for valor in valores) / (
        len(valores) - 1
    )
    return media, math.sqrt(max(variancia, 0.0))


def _faixa_odd(valor):
    try:
        odd = float(valor)
    except (TypeError, ValueError):
        return None
    limites = (1.50, 1.66, 1.80, 2.00, 2.50)
    return next((i for i, limite in enumerate(limites) if odd < limite), len(limites))


def _faixa_minuto(valor):
    try:
        minuto = float(valor)
    except (TypeError, ValueError):
        return None
    limites = (15, 29, 45, 60, 70, 83)
    return next((i for i, limite in enumerate(limites) if minuto < limite), len(limites))


def _estrato(item):
    faixa_odd = _faixa_odd(item.get("odd"))
    faixa_minuto = _faixa_minuto(item.get("minuto"))
    if faixa_odd is None or faixa_minuto is None:
        return None
    return faixa_odd, faixa_minuto


def _residuos_condicionais(grupo, universo, liga, minimo_controles=5):
    """Compara entradas com outras ligas na mesma faixa de odd e minuto."""
    controles = defaultdict(list)
    for item in universo:
        if str(item.get("liga") or "sem_liga") == str(liga):
            continue
        estrato = _estrato(item)
        if estrato is not None:
            controles[estrato].append(
                float(item.get("retorno_unidades") or 0.0)
            )
    residuos = []
    for item in grupo:
        referencia = controles.get(_estrato(item)) or []
        if len(referencia) < int(minimo_controles):
            continue
        esperado = sum(referencia) / len(referencia)
        residuos.append(float(item.get("retorno_unidades") or 0.0) - esperado)
    return residuos


def _chave_prospectiva(mercado, regra_versao, regra_fingerprint):
    nucleo = "|".join(str(item or "") for item in (
        VERSAO_AUDITORIA_LIGAS, mercado, regra_versao, regra_fingerprint,
    ))
    sufixo = hashlib.sha256(nucleo.encode("utf-8")).hexdigest()[:20]
    return f"{CHAVE_PROSPECTIVA_PREFIXO}{mercado}:{sufixo}"


def registrar_ou_obter_validacao_prospectiva_ligas(
    conexao,
    mercado,
    regra_versao,
    regra_fingerprint,
    ligas_exclusao,
    inicio_apos,
    registrado_em=None,
):
    """Congela a primeira hipótese favorável antes dos resultados futuros."""
    ligas = sorted({str(liga) for liga in ligas_exclusao or [] if liga})
    if not ligas or not inicio_apos:
        return None
    chave = _chave_prospectiva(
        mercado, regra_versao, regra_fingerprint
    )
    esperado = {
        "versao": VERSAO_VALIDACAO_PROSPECTIVA_LIGAS,
        "mercado": str(mercado),
        "regra_versao": str(regra_versao),
        "regra_fingerprint": regra_fingerprint,
        "ligas_exclusao_congeladas": ligas,
        "inicio_apos": str(inicio_apos),
        "tamanho_coorte": TAMANHO_COORTE_PROSPECTIVA,
        "minimo_excluidos": MINIMO_EXCLUIDOS_PROSPECTIVA,
        "telegram": False,
        "altera_sinais": False,
        "promocao_automatica": False,
    }
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is None:
        documento = {
            **esperado,
            "registrado_em": str(
                registrado_em
                or datetime.now().replace(microsecond=0).isoformat()
            ),
        }
        with conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO metadados(chave, valor) VALUES (?, ?)",
                (
                    chave,
                    json.dumps(
                        documento, ensure_ascii=False, sort_keys=True
                    ),
                ),
            )
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?", (chave,)
        ).fetchone()
    bruto = linha["valor"] if hasattr(linha, "keys") else linha[0]
    existente = json.loads(bruto)
    for campo, valor in esperado.items():
        if existente.get(campo) != valor:
            raise RuntimeError(
                "Validação prospectiva de ligas diverge da âncora SQLite."
            )
    return existente


def obter_validacao_prospectiva_ligas(
    conexao, mercado, regra_versao, regra_fingerprint
):
    chave = _chave_prospectiva(
        mercado, regra_versao, regra_fingerprint
    )
    linha = conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is None:
        return None
    bruto = linha["valor"] if hasattr(linha, "keys") else linha[0]
    return json.loads(bruto)


def _posterior_ao_marco(valor, marco):
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        limite = datetime.fromisoformat(str(marco).replace("Z", "+00:00"))
        if instante.tzinfo is None and limite.tzinfo is not None:
            instante = instante.replace(tzinfo=limite.tzinfo)
        elif instante.tzinfo is not None and limite.tzinfo is None:
            limite = limite.replace(tzinfo=instante.tzinfo)
        return instante > limite
    except (TypeError, ValueError):
        return str(valor or "") > str(marco or "")


def avaliar_validacao_prospectiva_ligas(itens, ancora):
    base = {
        "versao": VERSAO_VALIDACAO_PROSPECTIVA_LIGAS,
        "ativa": bool(ancora),
        "aplicacao_automatica": False,
        "altera_sinais": False,
        "promocao_permitida": False,
    }
    if not ancora:
        return {**base, "estado": "sem_ancora_historica"}
    limite = int(
        ancora.get("tamanho_coorte", TAMANHO_COORTE_PROSPECTIVA)
    )
    inicio = str(ancora.get("inicio_apos") or "")
    futuros = [
        item for item in itens or []
        if _posterior_ao_marco(item.get("criado_em"), inicio)
    ][:limite]
    ligas = set(ancora.get("ligas_exclusao_congeladas") or [])
    excluidos = [
        item for item in futuros
        if str(item.get("liga") or "sem_liga") in ligas
    ]
    mantidos = [
        item for item in futuros
        if str(item.get("liga") or "sem_liga") not in ligas
    ]
    diferencas = [
        -float(item.get("retorno_unidades") or 0.0)
        if str(item.get("liga") or "sem_liga") in ligas else 0.0
        for item in futuros
    ]
    delta, desvio = _media_desvio(diferencas)
    limite_inferior = None
    if desvio is not None and diferencas:
        limite_inferior = delta - 1.96 * desvio / math.sqrt(len(diferencas))
    completa = len(futuros) >= limite
    minimo_excluidos = int(
        ancora.get("minimo_excluidos", MINIMO_EXCLUIDOS_PROSPECTIVA)
    )
    evidencia = bool(
        completa
        and len(excluidos) >= minimo_excluidos
        and delta is not None and delta > 0
        and limite_inferior is not None and limite_inferior > 0
    )
    if not completa:
        estado = "coletando_validacao_futura"
    elif len(excluidos) < minimo_excluidos:
        estado = "validacao_excluida_insuficiente"
    elif evidencia:
        estado = "pronta_para_revisao_independente"
    else:
        estado = "filtro_ligas_nao_confirmado"
    return {
        **base,
        "estado": estado,
        "inicio_apos": inicio,
        "ligas_exclusao_congeladas": sorted(ligas),
        "coorte": len(futuros),
        "coorte_alvo": limite,
        "faltam": max(limite - len(futuros), 0),
        "excluidos": len(excluidos),
        "minimo_excluidos": minimo_excluidos,
        "baseline": _metricas(futuros),
        "mantidos": _metricas(mantidos),
        "excluidos_metricas": _metricas(excluidos),
        "delta_roi_por_oportunidade": (
            round(delta, 4) if delta is not None else None
        ),
        "limite_inferior_delta_95": (
            round(limite_inferior, 4)
            if limite_inferior is not None else None
        ),
        "evidencia_favoravel": evidencia,
        "exige_revisao_independente": evidencia,
    }


def carregar_resultados_ligas(
    conexao, mercado, regra_versao, regra_fingerprint=None
):
    """Carrega a primeira decisao independente de cada partida/regra."""
    linhas = [dict(linha) for linha in conexao.execute(
        """
        WITH independentes AS (
            SELECT s.id, s.partida_id, s.criado_em, s.odd,
                   s.features_json,
                   r.retorno_unidades,
                   COALESCE(
                       NULLIF(p.liga_normalizada, ''),
                       NULLIF(p.liga, ''),
                       'sem_liga'
                   ) AS liga,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.partida_id, s.mercado, s.regra_versao
                       ORDER BY s.criado_em, s.id
                   ) AS ordem
            FROM sinais s
            JOIN resultados_sinais r ON r.sinal_id=s.id
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.status='aprovado'
              AND s.mercado=? AND s.regra_versao=?
              AND (? IS NULL OR s.regra_fingerprint=?)
              AND r.resultado IN (
                  'green', 'half_green', 'red', 'half_red'
              )
        )
        SELECT id, partida_id, criado_em, retorno_unidades, liga,
               odd, features_json
        FROM independentes WHERE ordem=1
        ORDER BY criado_em, id
        """,
        (mercado, regra_versao, regra_fingerprint, regra_fingerprint),
    )]
    itens = []
    for linha in linhas:
        try:
            features = json.loads(linha.pop("features_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        linha["minuto"] = features.get("minuto")
        if linha.get("odd") is None:
            linha["odd"] = features.get("odd")
        itens.append(linha)
    return itens


def carregar_resultados_ligas_metodo_grupo(
    conexao,
    mercado,
    versao_exploracao,
    inicio=None,
    linhagem=None,
):
    """Carrega somente decisoes do metodo realmente entregues ao grupo.

    Challengers promovidos continuam gravados como ``simulacao`` para manter
    sua coorte imutavel. A prova de que viraram uma entrada visivel e a
    entrega confirmada no canal de teste/grupo, e nao o status do sinal.
    """
    linhas = [dict(linha) for linha in conexao.execute(
        """
        WITH entregues AS (
            SELECT sinal_id
            FROM entregas_alertas
            WHERE status='entregue'
              AND canal LIKE '%:teste'
              AND canal NOT LIKE '%:resultado'
            GROUP BY sinal_id
        ), independentes AS (
            SELECT s.id, s.partida_id, s.criado_em, s.odd,
                   s.features_json,
                   r.retorno_unidades,
                   COALESCE(
                       NULLIF(p.liga_normalizada, ''),
                       NULLIF(p.liga, ''),
                       'sem_liga'
                   ) AS liga,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.partida_id, s.mercado,
                         json_extract(
                           s.features_json,
                           '$.exploracao_sombra.versao'
                         )
                       ORDER BY datetime(s.criado_em), s.id
                   ) AS ordem
            FROM sinais s
            JOIN entregues e ON e.sinal_id=s.id
            JOIN resultados_sinais r ON r.sinal_id=s.id
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.status='simulacao'
              AND s.mercado=?
              AND json_extract(
                    s.features_json, '$.exploracao_sombra.versao'
                  )=?
              AND (? IS NULL OR datetime(s.criado_em)>=datetime(?))
              AND (
                    ? IS NULL OR json_extract(
                      s.features_json,
                      '$.gol_capacidade_contextual_v2.linhagem_sha256'
                    )=?
                  )
              AND r.resultado IN (
                  'green', 'half_green', 'red', 'half_red'
              )
        )
        SELECT id, partida_id, criado_em, retorno_unidades, liga,
               odd, features_json
        FROM independentes WHERE ordem=1
        ORDER BY datetime(criado_em), id
        """,
        (
            mercado,
            versao_exploracao,
            inicio,
            inicio,
            linhagem,
            linhagem,
        ),
    )]
    itens = []
    for linha in linhas:
        try:
            features = json.loads(linha.pop("features_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            features = {}
        linha["minuto"] = features.get("minuto")
        if linha.get("odd") is None:
            linha["odd"] = features.get("odd")
        itens.append(linha)
    return itens


def avaliar_ligas_sombra(
    itens,
    minimo_total=60,
    minimo_por_liga=8,
    reserva_minima=30,
    maximo_desenvolvimento=300,
    alfa_familia=0.05,
    minimo_excluidos_validacao=10,
    minimo_controles_estrato=5,
):
    itens = list(itens or [])
    total = len(itens)
    base = {
        "versao": VERSAO_AUDITORIA_LIGAS,
        "amostra": total,
        "minimo_total": int(minimo_total),
        "minimo_por_liga": int(minimo_por_liga),
        "alfa_familia": float(alfa_familia),
        "ajuste_condicional": "odd_e_minuto",
        "minimo_controles_estrato": int(minimo_controles_estrato),
        "aplicacao_automatica": False,
        "altera_sinais": False,
    }
    if total < int(minimo_total):
        return {
            **base,
            "estado": "aguardando_amostra",
            "faltam": max(int(minimo_total) - total, 0),
            "desenvolvimento": 0,
            "validacao": 0,
            "ligas_testadas": 0,
            "ligas_exclusao_candidatas": [],
            "evidencia_historica_favoravel": False,
            "promocao_permitida": False,
        }

    tamanho_desenvolvimento = min(
        int(maximo_desenvolvimento), total - int(reserva_minima)
    )
    desenvolvimento = itens[:tamanho_desenvolvimento]
    validacao = itens[tamanho_desenvolvimento:]
    grupos = defaultdict(list)
    for item in desenvolvimento:
        grupos[str(item.get("liga") or "sem_liga")].append(item)
    cobertura_condicional = sum(
        _estrato(item) is not None for item in desenvolvimento
    )
    testadas = []
    for liga, grupo in sorted(grupos.items()):
        residuos = _residuos_condicionais(
            grupo, desenvolvimento, liga, minimo_controles_estrato
        )
        if len(residuos) >= int(minimo_por_liga):
            testadas.append((liga, grupo, residuos))
    z_bonferroni = (
        NormalDist().inv_cdf(1.0 - float(alfa_familia) / len(testadas))
        if testadas else None
    )

    avaliacoes = []
    candidatas = []
    for liga, grupo, residuos in testadas:
        retornos = [float(item["retorno_unidades"] or 0.0) for item in grupo]
        media_bruta, _ = _media_desvio(retornos)
        media, desvio = _media_desvio(residuos)
        erro_padrao = (
            desvio / math.sqrt(len(retornos)) if desvio is not None else None
        )
        limite_superior = (
            media + z_bonferroni * erro_padrao
            if erro_padrao is not None else None
        )
        comprovadamente_negativa = bool(
            limite_superior is not None and limite_superior < 0
        )
        avaliacoes.append({
            "liga": liga,
            "amostra_desenvolvimento": len(grupo),
            "amostra_condicional": len(residuos),
            "roi_desenvolvimento": round(media_bruta, 4),
            "efeito_liga_ajustado": round(media, 4),
            "limite_superior_efeito_bonferroni": (
                round(limite_superior, 4)
                if limite_superior is not None else None
            ),
            "comprovadamente_negativa": comprovadamente_negativa,
        })
        if comprovadamente_negativa:
            candidatas.append(liga)

    validacao_excluida = [
        item for item in validacao
        if str(item.get("liga") or "sem_liga") in candidatas
    ]
    validacao_mantida = [
        item for item in validacao
        if str(item.get("liga") or "sem_liga") not in candidatas
    ]
    diferencas = [
        -float(item.get("retorno_unidades") or 0.0)
        if str(item.get("liga") or "sem_liga") in candidatas else 0.0
        for item in validacao
    ]
    delta, desvio_delta = _media_desvio(diferencas)
    limite_inferior_delta = None
    if desvio_delta is not None and diferencas:
        limite_inferior_delta = (
            delta - 1.96 * desvio_delta / math.sqrt(len(diferencas))
        )
    residuos_validacao = []
    for liga in candidatas:
        grupo = [
            item for item in validacao_excluida
            if str(item.get("liga") or "sem_liga") == liga
        ]
        residuos_validacao.extend(_residuos_condicionais(
            grupo, validacao_mantida, liga, minimo_controles_estrato
        ))
    beneficios_ajustados = [-residuo for residuo in residuos_validacao]
    delta_ajustado, desvio_ajustado = _media_desvio(beneficios_ajustados)
    limite_inferior_ajustado = None
    if desvio_ajustado is not None and beneficios_ajustados:
        limite_inferior_ajustado = (
            delta_ajustado
            - 1.96 * desvio_ajustado / math.sqrt(len(beneficios_ajustados))
        )
    evidencia_historica = bool(
        candidatas
        and len(validacao_excluida) >= int(minimo_excluidos_validacao)
        and len(beneficios_ajustados) >= int(minimo_excluidos_validacao)
        and delta is not None and delta > 0
        and limite_inferior_delta is not None
        and limite_inferior_delta > 0
        and delta_ajustado is not None and delta_ajustado > 0
        and limite_inferior_ajustado is not None
        and limite_inferior_ajustado > 0
    )
    if not testadas:
        estado = "amostra_por_liga_insuficiente"
    elif not candidatas:
        estado = "nenhuma_liga_negativa_comprovada"
    elif (
        len(validacao_excluida) < int(minimo_excluidos_validacao)
        or len(beneficios_ajustados) < int(minimo_excluidos_validacao)
    ):
        estado = "validacao_excluida_insuficiente"
    elif evidencia_historica:
        estado = "evidencia_historica_exige_validacao_prospectiva"
    else:
        estado = "filtro_ligas_nao_confirmado"
    return {
        **base,
        "estado": estado,
        "faltam": 0,
        "desenvolvimento": len(desenvolvimento),
        "validacao": len(validacao),
        "ligas_testadas": len(testadas),
        "cobertura_condicional": cobertura_condicional,
        "cobertura_condicional_taxa": round(
            cobertura_condicional / len(desenvolvimento), 4
        ) if desenvolvimento else 0.0,
        "z_bonferroni": (
            round(z_bonferroni, 4) if z_bonferroni is not None else None
        ),
        "avaliacoes": avaliacoes,
        "ligas_exclusao_candidatas": candidatas,
        "baseline_validacao": _metricas(validacao),
        "mantidas_validacao": _metricas(validacao_mantida),
        "excluidas_validacao": _metricas(validacao_excluida),
        "minimo_excluidos_validacao": int(minimo_excluidos_validacao),
        "delta_roi_por_oportunidade": (
            round(delta, 4) if delta is not None else None
        ),
        "limite_inferior_delta_95": (
            round(limite_inferior_delta, 4)
            if limite_inferior_delta is not None else None
        ),
        "validacao_condicional": len(beneficios_ajustados),
        "delta_ajustado_odd_minuto": (
            round(delta_ajustado, 4) if delta_ajustado is not None else None
        ),
        "limite_inferior_delta_ajustado_95": (
            round(limite_inferior_ajustado, 4)
            if limite_inferior_ajustado is not None else None
        ),
        "evidencia_historica_favoravel": evidencia_historica,
        "promocao_permitida": False,
        "exige_validacao_prospectiva": bool(evidencia_historica),
    }


def auditar_ligas_por_mercado(
    conexao,
    regras_por_mercado,
    fingerprints_por_regra=None,
    metodos_grupo=None,
):
    fingerprints_por_regra = fingerprints_por_regra or {}
    metodos_grupo = metodos_grupo or {}
    por_mercado = {}
    for mercado in MERCADOS_AUDITADOS:
        regra = (regras_por_mercado or {}).get(mercado)
        if not regra:
            continue
        itens = carregar_resultados_ligas(
            conexao, mercado, regra, fingerprints_por_regra.get(regra)
        )
        avaliacao = avaliar_ligas_sombra(itens)
        fingerprint = fingerprints_por_regra.get(regra)
        ancora = obter_validacao_prospectiva_ligas(
            conexao, mercado, regra, fingerprint
        )
        if (
            ancora is None
            and avaliacao.get("evidencia_historica_favoravel")
            and itens
        ):
            ancora = registrar_ou_obter_validacao_prospectiva_ligas(
                conexao,
                mercado,
                regra,
                fingerprint,
                avaliacao.get("ligas_exclusao_candidatas"),
                itens[-1].get("criado_em"),
            )
        por_mercado[mercado] = {
            "regra_versao": regra,
            "regra_fingerprint": fingerprint,
            **avaliacao,
            "validacao_prospectiva": (
                avaliar_validacao_prospectiva_ligas(itens, ancora)
            ),
        }
    por_metodo_grupo = {}
    for nome, configuracao in sorted(metodos_grupo.items()):
        mercado = configuracao.get("mercado")
        versao = configuracao.get("versao_exploracao")
        inicio = configuracao.get("inicio")
        linhagem = configuracao.get("linhagem")
        if not mercado or not versao or not inicio:
            por_metodo_grupo[nome] = {
                "versao": VERSAO_AUDITORIA_LIGAS,
                "estado": "aguardando_ancora_do_grupo",
                "mercado": mercado,
                "versao_exploracao": versao,
                "inicio": inicio,
                "linhagem": linhagem,
                "amostra": 0,
                "aplicacao_automatica": False,
                "altera_sinais": False,
                "promocao_permitida": False,
                "validacao_prospectiva": {
                    "versao": VERSAO_VALIDACAO_PROSPECTIVA_LIGAS,
                    "ativa": False,
                    "estado": "sem_ancora_historica",
                    "aplicacao_automatica": False,
                    "altera_sinais": False,
                    "promocao_permitida": False,
                },
            }
            continue
        itens = carregar_resultados_ligas_metodo_grupo(
            conexao,
            mercado,
            versao,
            inicio=inicio,
            linhagem=linhagem,
        )
        avaliacao = avaliar_ligas_sombra(itens)
        mercado_prospectivo = f"grupo:{nome}"
        ancora = obter_validacao_prospectiva_ligas(
            conexao, mercado_prospectivo, versao, linhagem
        )
        if (
            ancora is None
            and avaliacao.get("evidencia_historica_favoravel")
            and itens
        ):
            ancora = registrar_ou_obter_validacao_prospectiva_ligas(
                conexao,
                mercado_prospectivo,
                versao,
                linhagem,
                avaliacao.get("ligas_exclusao_candidatas"),
                itens[-1].get("criado_em"),
            )
        por_metodo_grupo[nome] = {
            "mercado": mercado,
            "versao_exploracao": versao,
            "inicio": inicio,
            "linhagem": linhagem,
            "coorte": "somente_entregues_ao_grupo_primeiro_por_partida",
            **avaliacao,
            "validacao_prospectiva": (
                avaliar_validacao_prospectiva_ligas(itens, ancora)
            ),
        }
    avaliacoes_integridade = [
        *por_mercado.values(), *por_metodo_grupo.values()
    ]
    return {
        "versao": VERSAO_AUDITORIA_LIGAS,
        "integro": all(
            item.get("versao") == VERSAO_AUDITORIA_LIGAS
            and item.get("aplicacao_automatica") is False
            for item in avaliacoes_integridade
        ),
        "aplicacao_automatica": False,
        "por_mercado": por_mercado,
        "por_metodo_grupo": por_metodo_grupo,
        "mercados_com_evidencia_historica": [
            mercado for mercado, item in por_mercado.items()
            if item.get("evidencia_historica_favoravel")
        ],
        "mercados_validacao_prospectiva_pronta": [
            mercado for mercado, item in por_mercado.items()
            if (item.get("validacao_prospectiva") or {}).get(
                "evidencia_favoravel"
            )
        ],
        "metodos_grupo_com_evidencia_historica": [
            nome for nome, item in por_metodo_grupo.items()
            if item.get("evidencia_historica_favoravel")
        ],
        "metodos_grupo_validacao_prospectiva_pronta": [
            nome for nome, item in por_metodo_grupo.items()
            if (item.get("validacao_prospectiva") or {}).get(
                "evidencia_favoravel"
            )
        ],
    }
