import math


def intervalo_wilson(acertos, total, z=1.96):
    if total <= 0:
        return None
    proporcao = acertos / total
    z2 = z * z
    denominador = 1 + z2 / total
    centro = (proporcao + z2 / (2 * total)) / denominador
    margem = (
        z
        * math.sqrt(
            proporcao * (1 - proporcao) / total
            + z2 / (4 * total * total)
        )
        / denominador
    )
    return max(centro - margem, 0.0), min(centro + margem, 1.0)


def limite_inferior_wilson(acertos, total, z=1.96):
    intervalo = intervalo_wilson(acertos, total, z)
    return intervalo[0] if intervalo is not None else None


def estado_amostra(total):
    if total < 30:
        return "inconclusiva"
    if total < 100:
        return "pre_validacao"
    return "validavel"


def discriminacao_pontuacao(resultados):
    """Mede se notas maiores ordenam greens acima de reds (AUC)."""
    positivos = []
    negativos = []
    for item in resultados:
        try:
            resultado = item["resultado"]
            valor_pontuacao = item["pontuacao_tecnica"]
        except (KeyError, TypeError, IndexError):
            resultado = getattr(item, "get", lambda *_: None)("resultado")
            valor_pontuacao = getattr(item, "get", lambda *_: None)(
                "pontuacao_tecnica"
            )
        if resultado not in ("green", "half_green", "red", "half_red"):
            continue
        try:
            pontuacao = float(valor_pontuacao)
        except (TypeError, ValueError):
            continue
        destino = (
            positivos
            if resultado in ("green", "half_green")
            else negativos
        )
        destino.append(pontuacao)

    pares = len(positivos) * len(negativos)
    if not pares:
        return {
            "auc": None,
            "amostra": len(positivos) + len(negativos),
            "greens": len(positivos),
            "reds": len(negativos),
            "pares_comparaveis": pares,
            "motivo": "classes_insuficientes",
        }

    concordantes = 0.0
    for positivo in positivos:
        for negativo in negativos:
            if positivo > negativo:
                concordantes += 1.0
            elif positivo == negativo:
                concordantes += 0.5
    auc = concordantes / pares
    # Aproximação de Hanley-McNeil para expressar a incerteza do AUC.
    q1 = auc / (2.0 - auc) if auc < 2.0 else 1.0
    q2 = 2.0 * auc * auc / (1.0 + auc) if auc > -1.0 else 0.0
    variancia = (
        auc * (1.0 - auc)
        + (len(positivos) - 1) * (q1 - auc * auc)
        + (len(negativos) - 1) * (q2 - auc * auc)
    ) / pares
    erro_padrao = math.sqrt(max(variancia, 0.0))
    intervalo_auc = (
        max(0.0, auc - 1.96 * erro_padrao),
        min(1.0, auc + 1.96 * erro_padrao),
    )
    return {
        "auc": round(auc, 4),
        "intervalo_auc_95": [round(item, 4) for item in intervalo_auc],
        "limite_inferior_auc_95": round(intervalo_auc[0], 4),
        "amostra": len(positivos) + len(negativos),
        "greens": len(positivos),
        "reds": len(negativos),
        "pares_comparaveis": pares,
        "media_greens": round(sum(positivos) / len(positivos), 4),
        "media_reds": round(sum(negativos) / len(negativos), 4),
        "motivo": None,
    }
