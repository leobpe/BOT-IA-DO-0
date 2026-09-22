"""Probabilidade condicional por entrada, aprendida de entregas reais.

Protótipo de avaliação OFFLINE, NÃO integrado à entrega. A validação V1 não
demonstrou melhora sobre a própria odd em HT/FT. Ainda não inclui
notícias/escalações/peso dos jogadores, portanto não atende à análise completa
esclarecida pelo usuário.

Treino cronológico por mercado; não promove o challenger antigo nem
transforma nota em chance. Nenhuma função deste módulo escreve no banco.
"""
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta

from gols_capacidade_contextual_v2 import classificar_competicao
from probabilidade_por_acertos import _data, _dict, coorte
from qualidade_dados import extrair_placar

VERSAO = "individual-logistica-contexto-entregues-v1"
VERSAO_V2 = "individual-logistica-offset-mercado-walkforward-v2"
MERCADOS = {"gol_ht": 45, "gol_ft": 90}
JANELA_DIAS = 90
MIN_TREINO = 80
MIN_VALIDACAO = 30
MIN_CLASSE_TREINO = 15
MIN_CLASSE_VALIDACAO = 5
ITERACOES = 400
L2 = 0.5
PASSO = 0.08
COBERTURA_FEATURE = 0.50
BRIER_TOLERANCIA = 0.01
ERRO_CALIBRACAO_MAX = 0.15
FOLDS_V2 = 3
TAMANHO_FOLD_V2 = 30
L2_V2 = 1.0
PASSO_V2 = 0.05
ITERACOES_V2 = 500
MELHORA_BRIER_MINIMA_V2 = 0.002
TOLERANCIA_BRIER_FOLD_V2 = 0.01
ERRO_CALIBRACAO_MAX_V2 = 0.10

FEATURES = (
    "tempo_restante", "gols_atuais", "diferenca_placar", "gols_necessarios",
    "log_odd", "ataque_casa_defesa_fora", "ataque_fora_defesa_casa",
    "media_h2h", "chutes_5min", "pressao_5min", "xg_5min", "vermelhos",
)


def _hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()


def numero(v):
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _par(valor):
    if not isinstance(valor, (list, tuple)) or len(valor) != 2:
        return None
    p = [numero(x) for x in valor]
    return p if all(x is not None and x >= 0 for x in p) else None


def _perfil(ctx, lado):
    recente = _dict(_dict(_dict(ctx.get("capacidade_times_v2")).get("recentes")).get(lado))
    geral, mando = _dict(recente.get("geral")), _dict(recente.get("mando"))
    if (numero(geral.get("jogos")) or 0) >= 10:
        base = mando if (numero(mando.get("jogos")) or 0) >= 4 else geral
    else:
        base = _dict(_dict(ctx.get("historico_detalhado")).get(lado))
        if (numero(base.get("jogos")) or 0) < 5:
            return None
    pro, contra = numero(base.get("gols_pro_media")), numero(base.get("gols_contra_media"))
    return (pro, contra) if pro is not None and contra is not None and min(pro, contra) >= 0 else None


def extrair_entrada(sinal, snapshot, jogo):
    mercado = sinal.get("mercado")
    if mercado not in MERCADOS:
        return None
    f = _dict(sinal.get("features") or sinal.get("features_json"))
    ctx = _dict(snapshot.get("contexto_api_json"))
    minuto, linha, odd = numero(f.get("minuto")), numero(sinal.get("linha")), numero(sinal.get("odd"))
    placar = extrair_placar(snapshot.get("placar"))
    if (minuto is None or not 0 < minuto < MERCADOS[mercado] or placar is None
            or linha is None or odd is None or not 1 < odd < 100):
        return None
    # Binário Over de meia linha; não reutilizar esta probabilidade para under,
    # resultado da equipe, linha asiática com push ou mercado de outro período.
    if not math.isclose(linha % 1, 0.5) or linha < sum(placar):
        return None
    casa, fora = _perfil(ctx, "mandante"), _perfil(ctx, "visitante")
    j5 = _dict(_dict(f.get("janelas")).get("5"))
    duracao = numero(j5.get("duracao_real_minutos"))
    recente_ok = j5.get("disponivel") is True and duracao is not None and 3 <= duracao <= 8
    chutes = numero(j5.get("chutes_total")) if recente_ok else None
    pressao = _par(j5.get("pressao_pico")) if recente_ok else None
    api5 = _dict(_dict(ctx.get("evolucao_temporal_api_live")).get("5"))
    duracao_api = numero(api5.get("duracao_real_minutos"))
    api_ok = duracao_api is not None and 3 <= duracao_api <= 8
    xg = _par(api5.get("xg")) if api_ok else None
    api_chutes = _par(api5.get("chutes")) if api_ok else None
    if chutes is None and api_chutes is not None:
        chutes, duracao = sum(api_chutes), duracao_api
    h2h = _dict(ctx.get("confrontos_diretos"))
    eventos = _dict(_dict(ctx.get("eventos_ao_vivo")).get("times"))
    cartoes = [numero(_dict(eventos.get(lado)).get("cartoes_vermelhos"))
               for lado in ("mandante", "visitante")]
    valores = {
        "tempo_restante": MERCADOS[mercado] - minuto,
        "gols_atuais": sum(placar), "diferenca_placar": abs(placar[0] - placar[1]),
        "gols_necessarios": math.floor(linha) + 1 - sum(placar), "log_odd": math.log(odd),
        "ataque_casa_defesa_fora": (casa[0] + fora[1]) / 2 if casa and fora else None,
        "ataque_fora_defesa_casa": (fora[0] + casa[1]) / 2 if casa and fora else None,
        "media_h2h": numero(h2h.get("media_gols")) if (numero(h2h.get("jogos")) or 0) >= 3 else None,
        "chutes_5min": chutes * 5 / duracao if chutes is not None and chutes >= 0 else None,
        "pressao_5min": max(pressao) if pressao else None,
        "xg_5min": sum(xg) * 5 / duracao_api if xg else None,
        "vermelhos": sum(cartoes) if all(x is not None and x >= 0 for x in cartoes) else None,
    }
    # Uma odd e um relógio, sozinhos, não são uma análise individual do time.
    if casa is None or fora is None:
        return None
    return {"valores": valores, "mercado": mercado, "metodo": _hash(coorte(sinal)),
            "versao_metodo": coorte(sinal)["metodo"], "segmento": classificar_competicao(jogo),
            "sinal_id": sinal.get("id"), "partida_id": sinal.get("partida_id"),
            "criado_em": sinal.get("criado_em"), "linha": linha, "odd": odd,
            "minuto": minuto, "placar": placar}


def carregar_base(conexao, mercado, corte, excluir_partida=None):
    """Apenas observações da entrada, sem consultar snapshot final ou cache novo."""
    corte = _data(corte)
    if corte is None:
        return []
    inicio = (corte - timedelta(days=JANELA_DIAS)).isoformat()
    cur = conexao.execute("""
        WITH envios AS (
            SELECT sinal_id, MIN(entregue_em) enviado_em FROM entregas_alertas
            WHERE status='entregue' AND provedor_mensagem_id IS NOT NULL
              AND (canal NOT LIKE '%:%' OR canal LIKE '%:teste') GROUP BY sinal_id
        )
        SELECT s.id,s.partida_id,s.snapshot_id,s.mercado,s.linha,s.odd,s.regra_versao,
               s.regra_fingerprint,s.features_json,s.criado_em,e.enviado_em,
               t.placar,t.contexto_api_json,t.coletado_em,p.mandante,p.visitante,p.liga,
               r.resultado,r.retorno_unidades,r.encerrado_em
        FROM envios e JOIN sinais s ON s.id=e.sinal_id
        JOIN snapshots t ON t.id=s.snapshot_id AND t.partida_id=s.partida_id
        JOIN partidas p ON p.id=s.partida_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado=? AND e.enviado_em>=? AND e.enviado_em<? AND s.criado_em<?
        ORDER BY e.enviado_em,s.id
    """, (mercado, inicio, corte.isoformat(), corte.isoformat()))
    nomes = [x[0] for x in cur.description]
    registros, vistos = [], set()
    for linha in cur:
        r = dict(zip(nomes, linha))
        if r["partida_id"] == excluir_partida or r["partida_id"] in vistos:
            continue
        vistos.add(r["partida_id"])
        datas = [_data(r[k]) for k in ("coletado_em", "criado_em", "enviado_em", "encerrado_em")]
        if any(d is None for d in datas) or not datas[0] <= datas[1] <= datas[2] < datas[3] < corte:
            continue
        resultado, retorno = r["resultado"], numero(r["retorno_unidades"])
        if retorno is None or not ((resultado == "green" and retorno > 0) or (resultado == "red" and retorno < 0)):
            continue
        item = extrair_entrada(r, r, r)
        if item is not None:
            item.update(alvo=int(resultado == "green"), encerrado_em=r["encerrado_em"],
                        enviado_em=r["enviado_em"], snapshot_id=r["snapshot_id"])
            registros.append(item)
    return registros


def _sigmoide(x):
    return 1 / (1 + math.exp(-max(-40, min(40, x))))


def _vetor(modelo, entrada):
    vetor = []
    for nome in modelo["features"]:
        valor = entrada["valores"].get(nome)
        vetor.extend((0 if valor is None else max(-4, min(4, (valor - modelo["medias"][nome]) / modelo["desvios"][nome])),
                      int(valor is None)))
    vetor.extend(int(entrada["metodo"] == x) for x in modelo["metodos"])
    vetor.extend(int(entrada["segmento"] == x) for x in modelo["segmentos"])
    return vetor


def ajustar(registros):
    verdes = sum(x["alvo"] for x in registros)
    if len(registros) < MIN_TREINO or min(verdes, len(registros) - verdes) < MIN_CLASSE_TREINO:
        raise ValueError("amostra_treino_insuficiente")
    m = {"features": [], "medias": {}, "desvios": {}, "dominio": {},
         "metodos": sorted({x["metodo"] for x in registros}),
         "segmentos": sorted({x["segmento"] for x in registros}),
         "contagem_metodos": dict(Counter(x["metodo"] for x in registros)),
         "contagem_segmentos": dict(Counter(x["segmento"] for x in registros))}
    for nome in FEATURES:
        valores = [x["valores"][nome] for x in registros if x["valores"].get(nome) is not None]
        if len(valores) < COBERTURA_FEATURE * len(registros):
            continue
        media = sum(valores) / len(valores)
        desvio = math.sqrt(sum((v - media) ** 2 for v in valores) / len(valores))
        m["dominio"][nome] = [min(valores), max(valores)]
        if desvio < 1e-8:
            continue
        m["features"].append(nome)
        m["medias"][nome], m["desvios"][nome] = media, desvio
    if not {"tempo_restante", "ataque_casa_defesa_fora", "ataque_fora_defesa_casa"} <= set(m["features"]):
        raise ValueError("contexto_sem_variacao_para_modelar")
    matriz = [_vetor(m, x) for x in registros]
    pesos = [0.0] * len(matriz[0])
    base = (verdes + 1) / (len(registros) + 2)
    intercepto = math.log(base / (1 - base))
    for _ in range(ITERACOES):
        gi, grad = 0.0, [0.0] * len(pesos)
        for v, item in zip(matriz, registros):
            erro = _sigmoide(intercepto + sum(p * x for p, x in zip(pesos, v))) - item["alvo"]
            gi += erro
            for j, x in enumerate(v):
                grad[j] += erro * x
        intercepto -= PASSO * gi / len(registros)
        pesos = [p - PASSO * (g / len(registros) + L2 * p) for p, g in zip(pesos, grad)]
    m.update(pesos=pesos, intercepto=intercepto, base=base, amostra=len(registros),
             sinais_treino=[x["sinal_id"] for x in registros],
             base_hash=_hash(registros))
    return m


def prever(modelo, entrada):
    return _sigmoide(modelo["intercepto"] + sum(p * x for p, x in zip(modelo["pesos"], _vetor(modelo, entrada))))


def validar_e_ajustar(registros, mercado, corte):
    """Holdout posterior; purga resultados ainda desconhecidos no início dele.

Limiares fixados antes da auditoria real. O teste é inicial, não comprova
calibração individual nem vantagem contra as odds. Não otimiza ROI/limiares.
"""
    out = {"versao": VERSAO, "mercado": mercado, "corte": corte,
           "estado": "amostra_insuficiente", "modelo": None, "amostra": len(registros)}
    if len(registros) < MIN_TREINO + MIN_VALIDACAO:
        return out
    n_validacao = max(MIN_VALIDACAO, math.ceil(len(registros) * 0.20))
    validacao = registros[-n_validacao:]
    marco = min(x["criado_em"] for x in validacao)
    treino = [x for x in registros[:-n_validacao] if x["encerrado_em"] < marco]
    try:
        modelo = ajustar(treino)
    except ValueError as exc:
        out["estado"] = str(exc)
        return out
    ys = [x["alvo"] for x in validacao]
    ps = [prever(modelo, x) for x in validacao]
    brier = sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)
    brier_base = sum((modelo["base"] - y) ** 2 for y in ys) / len(ys)
    brier_odd = sum((1 / x["odd"] - x["alvo"]) ** 2 for x in validacao) / len(ys)
    bins = []
    for a, b in ((0, .4), (.4, .6), (.6, .8), (.8, 1.0001)):
        pares = [(p, y) for p, y in zip(ps, ys) if a <= p < b]
        if pares:
            bins.append({"faixa": [a, min(b, 1)], "n": len(pares),
                         "previsto": sum(p for p, _ in pares) / len(pares),
                         "observado": sum(y for _, y in pares) / len(pares)})
    ece = sum(x["n"] * abs(x["previsto"] - x["observado"]) for x in bins) / len(ys)
    aprovado = (min(sum(ys), len(ys) - sum(ys)) >= MIN_CLASSE_VALIDACAO
                and brier <= brier_base + BRIER_TOLERANCIA and ece <= ERRO_CALIBRACAO_MAX)
    out.update(estado="validacao_inicial_aprovada" if aprovado else "validacao_inicial_insuficiente",
               validacao={"n": len(ys), "greens": sum(ys), "brier": brier,
                          "brier_media_treino": brier_base, "brier_odd_bruta": brier_odd,
                          "erro_calibracao": ece, "faixas": bins,
                          "sinais": [x["sinal_id"] for x in validacao],
                          "sinais_treino": modelo["sinais_treino"],
                          "marco": marco, "calibracao_comprovada": False})
    if aprovado:
        out["modelo"] = ajustar(registros)
    return out


FEATURES_V2 = tuple(nome for nome in FEATURES if nome != "log_odd")


def _logit(probabilidade):
    p = max(0.02, min(0.98, float(probabilidade)))
    return math.log(p / (1 - p))


def _probabilidade_odd(entrada):
    odd = numero(entrada.get("odd"))
    if odd is None or not 1 < odd < 100:
        raise ValueError("odd_invalida")
    return max(0.02, min(0.98, 1 / odd))


def _vetor_v2(modelo, entrada):
    vetor = []
    for nome in modelo["features"]:
        valor = entrada["valores"].get(nome)
        vetor.extend((
            0 if valor is None else max(
                -4,
                min(4, (valor - modelo["medias"][nome]) / modelo["desvios"][nome]),
            ),
            int(valor is None),
        ))
    vetor.extend(int(entrada["metodo"] == item) for item in modelo["metodos"])
    vetor.extend(int(entrada["segmento"] == item) for item in modelo["segmentos"])
    return vetor


def ajustar_v2(registros):
    """Ajusta somente o desvio contextual em torno do preço de mercado.

    A probabilidade implícita da odd é um *offset*, não uma resposta. Isso
    obriga o contexto a demonstrar valor adicional em vez de reconstruir o
    relógio/preço com liberdade excessiva em uma amostra pequena.
    """
    verdes = sum(int(item["alvo"]) for item in registros)
    if (
        len(registros) < MIN_TREINO
        or min(verdes, len(registros) - verdes) < MIN_CLASSE_TREINO
    ):
        raise ValueError("amostra_treino_insuficiente")
    modelo = {
        "versao": VERSAO_V2,
        "features": [],
        "medias": {},
        "desvios": {},
        "dominio": {},
        "metodos": sorted({item["metodo"] for item in registros}),
        "segmentos": sorted({item["segmento"] for item in registros}),
        "contagem_metodos": dict(Counter(item["metodo"] for item in registros)),
        "contagem_segmentos": dict(Counter(item["segmento"] for item in registros)),
    }
    for nome in FEATURES_V2:
        valores = [
            item["valores"][nome]
            for item in registros
            if item["valores"].get(nome) is not None
        ]
        if len(valores) < COBERTURA_FEATURE * len(registros):
            continue
        media = sum(valores) / len(valores)
        desvio = math.sqrt(
            sum((valor - media) ** 2 for valor in valores) / len(valores)
        )
        modelo["dominio"][nome] = [min(valores), max(valores)]
        if desvio < 1e-8:
            continue
        modelo["features"].append(nome)
        modelo["medias"][nome] = media
        modelo["desvios"][nome] = desvio
    essenciais = {
        "tempo_restante",
        "ataque_casa_defesa_fora",
        "ataque_fora_defesa_casa",
    }
    if not essenciais <= set(modelo["features"]):
        raise ValueError("contexto_sem_variacao_para_modelar")
    matriz = [_vetor_v2(modelo, item) for item in registros]
    pesos = [0.0] * len(matriz[0])
    intercepto = 0.0
    for _ in range(ITERACOES_V2):
        gradiente_intercepto = 0.0
        gradiente = [0.0] * len(pesos)
        for vetor, item in zip(matriz, registros):
            previsto = _sigmoide(
                _logit(_probabilidade_odd(item))
                + intercepto
                + sum(peso * valor for peso, valor in zip(pesos, vetor))
            )
            erro = previsto - int(item["alvo"])
            gradiente_intercepto += erro
            for indice, valor in enumerate(vetor):
                gradiente[indice] += erro * valor
        intercepto -= PASSO_V2 * gradiente_intercepto / len(registros)
        pesos = [
            peso - PASSO_V2 * (
                grad / len(registros) + L2_V2 * peso
            )
            for peso, grad in zip(pesos, gradiente)
        ]
    modelo.update({
        "pesos": pesos,
        "intercepto": intercepto,
        "amostra": len(registros),
        "sinais_treino": [item["sinal_id"] for item in registros],
        "base_hash": _hash(registros),
        "offset": "logit_probabilidade_implicita_odd",
    })
    return modelo


def prever_v2(modelo, entrada):
    if modelo.get("versao") != VERSAO_V2:
        raise ValueError("modelo_v2_incompativel")
    return _sigmoide(
        _logit(_probabilidade_odd(entrada))
        + float(modelo["intercepto"])
        + sum(
            peso * valor
            for peso, valor in zip(modelo["pesos"], _vetor_v2(modelo, entrada))
        )
    )


def _metricas_v2(probabilidades, alvos, probabilidades_odd):
    total = len(alvos)
    if not total:
        raise ValueError("validacao_vazia")
    brier = sum(
        (probabilidade - alvo) ** 2
        for probabilidade, alvo in zip(probabilidades, alvos)
    ) / total
    brier_odd = sum(
        (probabilidade - alvo) ** 2
        for probabilidade, alvo in zip(probabilidades_odd, alvos)
    ) / total
    base = sum(alvos) / total
    brier_base = sum((base - alvo) ** 2 for alvo in alvos) / total
    faixas = []
    for inicio, fim in ((0, .4), (.4, .6), (.6, .8), (.8, 1.0001)):
        pares = [
            (probabilidade, alvo)
            for probabilidade, alvo in zip(probabilidades, alvos)
            if inicio <= probabilidade < fim
        ]
        if pares:
            faixas.append({
                "faixa": [inicio, min(fim, 1)],
                "n": len(pares),
                "previsto": sum(item[0] for item in pares) / len(pares),
                "observado": sum(item[1] for item in pares) / len(pares),
            })
    ece = sum(
        faixa["n"] * abs(faixa["previsto"] - faixa["observado"])
        for faixa in faixas
    ) / total
    return {
        "n": total,
        "greens": sum(alvos),
        "reds": total - sum(alvos),
        "brier": brier,
        "brier_odd_bruta": brier_odd,
        "brier_taxa_observada": brier_base,
        "delta_brier_vs_odd": brier - brier_odd,
        "delta_brier_vs_taxa_observada": brier - brier_base,
        "erro_calibracao": ece,
        "faixas": faixas,
    }


def validar_walk_forward_v2(registros, mercado, corte):
    """Validação pré-declarada em três blocos cronológicos independentes.

    Mesmo uma aprovação é apenas autorização para iniciar uma coorte futura em
    sombra. Nunca preenche ``probabilidade_calibrada`` nem altera Telegram.
    """
    ordenados = sorted(
        registros,
        key=lambda item: (str(item.get("criado_em") or ""), int(item["sinal_id"])),
    )
    minimo = MIN_TREINO + FOLDS_V2 * TAMANHO_FOLD_V2
    saida = {
        "versao": VERSAO_V2,
        "mercado": mercado,
        "corte": corte,
        "estado": "amostra_insuficiente",
        "amostra": len(ordenados),
        "minimo": minimo,
        "folds_esperados": FOLDS_V2,
        "folds": [],
        "modelo": None,
        "aprovado_para_coorte_prospectiva": False,
        "aplicacao_sinais": False,
        "telegram": False,
    }
    if len(ordenados) < minimo:
        return saida
    inicio_validacao = len(ordenados) - FOLDS_V2 * TAMANHO_FOLD_V2
    probabilidades = []
    probabilidades_odd = []
    alvos = []
    sinais_validacao = []
    for indice in range(FOLDS_V2):
        inicio = inicio_validacao + indice * TAMANHO_FOLD_V2
        fim = inicio + TAMANHO_FOLD_V2
        validacao = ordenados[inicio:fim]
        marco = min(str(item["criado_em"]) for item in validacao)
        treino = [
            item for item in ordenados[:inicio]
            if str(item.get("encerrado_em") or "") < marco
        ]
        try:
            modelo = ajustar_v2(treino)
        except ValueError as exc:
            saida["estado"] = str(exc)
            return saida
        ys = [int(item["alvo"]) for item in validacao]
        if min(sum(ys), len(ys) - sum(ys)) < MIN_CLASSE_VALIDACAO:
            saida["estado"] = "classe_validacao_insuficiente"
            return saida
        ps = [prever_v2(modelo, item) for item in validacao]
        odds = [_probabilidade_odd(item) for item in validacao]
        metricas = _metricas_v2(ps, ys, odds)
        metricas.update({
            "indice": indice + 1,
            "marco": marco,
            "treino": len(treino),
            "sinais": [item["sinal_id"] for item in validacao],
            "sinais_treino": [item["sinal_id"] for item in treino],
        })
        saida["folds"].append(metricas)
        probabilidades.extend(ps)
        probabilidades_odd.extend(odds)
        alvos.extend(ys)
        sinais_validacao.extend(metricas["sinais"])
    agregado = _metricas_v2(probabilidades, alvos, probabilidades_odd)
    nenhum_fold_regrediu = all(
        fold["delta_brier_vs_odd"] <= TOLERANCIA_BRIER_FOLD_V2
        for fold in saida["folds"]
    )
    aprovado = bool(
        agregado["delta_brier_vs_odd"] <= -MELHORA_BRIER_MINIMA_V2
        and agregado["delta_brier_vs_taxa_observada"]
        <= -MELHORA_BRIER_MINIMA_V2
        and agregado["erro_calibracao"] <= ERRO_CALIBRACAO_MAX_V2
        and nenhum_fold_regrediu
    )
    saida.update({
        "estado": (
            "aprovado_para_coorte_prospectiva"
            if aprovado else "validacao_reprovada"
        ),
        "validacao": agregado,
        "sinais_validacao": sinais_validacao,
        "nenhum_fold_regrediu_vs_odd": nenhum_fold_regrediu,
        "criterios": {
            "melhora_brier_minima": MELHORA_BRIER_MINIMA_V2,
            "tolerancia_brier_fold": TOLERANCIA_BRIER_FOLD_V2,
            "erro_calibracao_maximo": ERRO_CALIBRACAO_MAX_V2,
            "folds": FOLDS_V2,
            "tamanho_fold": TAMANHO_FOLD_V2,
        },
        "aprovado_para_coorte_prospectiva": aprovado,
    })
    if aprovado:
        saida["modelo"] = ajustar_v2(ordenados)
    return saida
