def _indice_ofertas(odds):
    indice = {}
    for mercado in (odds or {}).get("ao_vivo") or []:
        categoria = mercado.get("categoria")
        escopo = mercado.get("escopo") or "total"
        tipo_mercado = mercado.get("tipo_mercado") or "nao_classificado"
        for oferta in mercado.get("ofertas") or []:
            indice[
                (categoria, escopo, tipo_mercado, float(oferta["linha"]))
            ] = oferta
        for lado, odd in (mercado.get("selecoes") or {}).items():
            indice[
                ("proximo_gol", "proximo", "proximo", lado)
            ] = {"over": odd}
    return indice


def calcular_movimento_odds(anteriores, atuais):
    antes = _indice_ofertas(anteriores)
    agora = _indice_ofertas(atuais)
    movimentos = []
    for chave, oferta_atual in agora.items():
        oferta_anterior = antes.get(chave)
        if oferta_anterior is None:
            continue
        delta = round(
            float(oferta_atual["over"]) - float(oferta_anterior["over"]),
            3,
        )
        movimentos.append(
            {
                "categoria": chave[0],
                "escopo": chave[1],
                "tipo_mercado": chave[2],
                "linha": chave[3],
                "odd_anterior": float(oferta_anterior["over"]),
                "odd_atual": float(oferta_atual["over"]),
                "delta": delta,
                "direcao": (
                    "queda" if delta < 0 else "alta" if delta > 0 else "estavel"
                ),
            }
        )
    return movimentos


def movimento_para(
    odds, categoria, linha, escopo="total", tipo_mercado=None
):
    for item in (odds or {}).get("movimentacao") or []:
        if (
            item.get("categoria") == categoria
            and (item.get("escopo") or "total") == escopo
            and (
                tipo_mercado is None
                or item.get("tipo_mercado") == tipo_mercado
            )
            and item.get("linha") == linha
        ):
            return item
    return None
