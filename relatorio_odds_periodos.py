import json

from normalizador_odds import (
    classificar_tipo_mercado,
    estruturar_mercado,
)


PERIODOS_ESCANTEIOS = ("FT", "1T", "2T")
BET_ASIATICO_FT = 32
BET_ASIATICO_1T = 51


def resumir_odds_escanteios_periodos(conexao, limite=5000):
    """Resume somente linhas ao vivo de escanteios separadas por tempo.

    Uma linha conta como asiática apenas quando o parser comprovou o formato
    de duas opções (over/under) e encontrou ao menos uma oferta. Mercados
    Exactly ficam contabilizados à parte e nunca habilitam sinais.
    """
    linhas = conexao.execute(
        """
        SELECT o.mercado, o.dados, o.estrutura_json, s.coletado_em
        FROM odds o
        JOIN snapshots s ON s.id=o.snapshot_id
        WHERE o.tipo='ao_vivo'
        ORDER BY o.id DESC
        LIMIT ?
        """,
        (int(limite),),
    ).fetchall()
    resumo = {
        periodo: {
            "asiaticas": 0,
            "exactly": 0,
            "sem_oferta": 0,
            "linhas_asiaticas": set(),
            "mercados": set(),
            "fontes": set(),
            "ultima_asiatica_em": None,
        }
        for periodo in PERIODOS_ESCANTEIOS
    }
    for linha in linhas:
        try:
            estrutura = json.loads(linha["estrutura_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            estrutura = {}
        if not estrutura.get("categoria"):
            estrutura = estruturar_mercado(
                {"mercado": linha["mercado"], "dados": linha["dados"]}
            )
        if estrutura.get("categoria") != "escanteios":
            continue
        tipo_mercado = (
            estrutura.get("tipo_mercado")
            or classificar_tipo_mercado(
                linha["mercado"],
                estrutura.get("categoria"),
                estrutura.get("formato"),
            )
        )
        ofertas_ft = estrutura.get("ofertas") or []
        resumo["FT"]["mercados"].add(linha["mercado"])
        if tipo_mercado == "asiatico" and ofertas_ft:
            resumo["FT"]["asiaticas"] += 1
            resumo["FT"]["fontes"].add(
                estrutura.get("fonte")
                or ofertas_ft[0].get("fonte")
                or "packball"
            )
            resumo["FT"]["linhas_asiaticas"].update(
                oferta.get("linha") for oferta in ofertas_ft
                if oferta.get("linha") is not None
            )
            if resumo["FT"]["ultima_asiatica_em"] is None:
                resumo["FT"]["ultima_asiatica_em"] = linha["coletado_em"]
        elif (
            tipo_mercado == "exactly"
            or estrutura.get("formato") == "tres_opcoes_exactly"
        ):
            resumo["FT"]["exactly"] += 1
        elif tipo_mercado == "asiatico":
            resumo["FT"]["sem_oferta"] += 1
        for periodo, dados_periodo in (
            estrutura.get("ofertas_periodos") or {}
        ).items():
            periodo = str(periodo).upper()
            if periodo not in resumo:
                continue
            ofertas = dados_periodo.get("ofertas") or []
            resumo[periodo]["mercados"].add(linha["mercado"])
            formato = dados_periodo.get("formato")
            tipo_periodo = (
                dados_periodo.get("tipo_mercado")
                or tipo_mercado
            )
            if (
                tipo_periodo == "asiatico"
                and formato == "duas_opcoes"
                and ofertas
            ):
                resumo[periodo]["asiaticas"] += 1
                resumo[periodo]["fontes"].add(
                    estrutura.get("fonte")
                    or ofertas[0].get("fonte")
                    or "packball"
                )
                resumo[periodo]["linhas_asiaticas"].update(
                    oferta.get("linha") for oferta in ofertas
                    if oferta.get("linha") is not None
                )
                if resumo[periodo]["ultima_asiatica_em"] is None:
                    resumo[periodo]["ultima_asiatica_em"] = linha["coletado_em"]
            elif (
                tipo_periodo == "exactly"
                or formato == "tres_opcoes_exactly"
            ) and ofertas:
                resumo[periodo]["exactly"] += 1
            elif tipo_periodo == "asiatico":
                resumo[periodo]["sem_oferta"] += 1
    for dados in resumo.values():
        dados["linhas_asiaticas"] = sorted(dados["linhas_asiaticas"])
        dados["mercados"] = sorted(dados["mercados"])
        dados["fontes"] = sorted(dados["fontes"])
        dados["mapeada"] = dados["asiaticas"] > 0
    return resumo


def diagnosticar_fontes_odds_periodos(
    resumo,
    catalogo_api=None,
    estado_odds_api=None,
):
    """Explica por que cada período está ou não apto para sinais.

    Catálogo prova apenas que o nome do mercado existe. A fonte só é
    considerada comprovada após uma oferta real de duas opções ser
    estruturada e persistida no banco.
    """
    catalogo_api = catalogo_api or {}
    estado_odds_api = estado_odds_api or {}
    por_bet = estado_odds_api.get("por_bet") or {}
    mapeamentos = catalogo_api.get("mapeamentos") or {}
    candidatos_2t = catalogo_api.get("candidatos_asiatico_2t") or []
    resultado = {}
    for periodo in PERIODOS_ESCANTEIOS:
        dados = dict((resumo or {}).get(periodo) or {})
        if periodo == "FT":
            bet_ids = [BET_ASIATICO_FT]
            mapeamento = mapeamentos.get(str(BET_ASIATICO_FT)) or {}
            catalogada = bool(mapeamento.get("coerente"))
        elif periodo == "1T":
            bet_ids = [BET_ASIATICO_1T]
            mapeamento = mapeamentos.get(str(BET_ASIATICO_1T)) or {}
            catalogada = bool(mapeamento.get("coerente"))
        else:
            bet_ids = [
                int(item["id"])
                for item in candidatos_2t
                if isinstance(item, dict)
                and str(item.get("id", "")).isdigit()
            ]
            catalogada = bool(bet_ids)
        estatisticas_api = [
            por_bet.get(str(bet_id)) or {}
            for bet_id in bet_ids
        ]
        consultas_api = sum(
            int(item.get("consultas", 0) or 0)
            for item in estatisticas_api
        )
        ofertas_api = sum(
            int(item.get("ofertas_anexadas", 0) or 0)
            for item in estatisticas_api
        )
        if dados.get("mapeada"):
            estado = "fonte_real_comprovada"
        elif catalogada and consultas_api and not ofertas_api:
            estado = "catalogada_sem_oferta_real"
        elif catalogada:
            estado = "catalogada_aguardando_coleta"
        elif int(dados.get("exactly", 0) or 0) > 0:
            estado = "somente_exactly_tres_opcoes"
        else:
            estado = "sem_evidencia_de_fonte"
        dados.update({
            "diagnostico_fonte": estado,
            "catalogada_api": catalogada,
            "bet_ids_api": bet_ids,
            "consultas_api": consultas_api,
            "ofertas_api_anexadas": ofertas_api,
            "exactly_rejeitadas": int(dados.get("exactly", 0) or 0),
        })
        resultado[periodo] = dados
    return resultado
