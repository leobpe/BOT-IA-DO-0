import re
import unicodedata


PADRAO_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")
PADRAO_OVER_UNDER = re.compile(r"Over\s+Under", re.IGNORECASE)
PADRAO_EXACTLY_OVER_UNDER = re.compile(
    r"Exactly\s+Over\s+Under", re.IGNORECASE
)
PADRAO_PROXIMO_GOL = re.compile(
    r"1:\s*(\d+(?:[.,]\d+)?)\s+2:\s*(\d+(?:[.,]\d+)?)"
    r"\s+No\s*:\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
PADRAO_GOL_HT = re.compile(
    r"1(?:º|Âº)\s*Tempo\s+Gols\s*\(HT\)\s+Over\s+Under\s+"
    r"(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+"
    r"(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
PADRAO_PERIODO = re.compile(
    r"([12])[^\d\s]{0,8}\s*Tempo\s+"
    r"(Gols|Goals|Escanteios|Corners)(?:\s*\(HT\))?\s+"
    r"(Exactly\s+)?Over\s+Under",
    re.IGNORECASE,
)


def _sem_acentos(texto):
    normalizado = unicodedata.normalize("NFKD", texto or "")
    return "".join(
        caractere
        for caractere in normalizado
        if not unicodedata.combining(caractere)
    ).lower()


def classificar_mercado(nome):
    nome = _sem_acentos(nome)
    if "escanteio" in nome or "corner" in nome:
        return "escanteios"
    if "gol" in nome or "goal" in nome:
        return "gols"
    return "outro"


def classificar_escopo(nome):
    nome = _sem_acentos(nome)
    if "proximo" in nome or "next" in nome:
        return "proximo"
    if "time da casa" in nome or "home team" in nome:
        return "time_casa"
    if "time visitante" in nome or "away team" in nome:
        return "time_visitante"
    if "exactly" in nome or "exatamente" in nome:
        return "exactly"
    if "corrida" in nome or "race" in nome:
        return "corrida"
    return "total"


def classificar_tipo_mercado(nome, categoria=None, formato=None):
    nome_normalizado = _sem_acentos(nome)
    if "asiatico" in nome_normalizado or "asian" in nome_normalizado:
        return "asiatico"
    if "exactly" in nome_normalizado or "exatamente" in nome_normalizado:
        return "exactly"
    if "proximo" in nome_normalizado or "next" in nome_normalizado:
        return "proximo"
    if categoria == "escanteios" and formato == "duas_opcoes":
        return "total"
    return "outro"


def _numero(valor):
    return float(valor.replace(",", "."))


def _ofertas_depois_cabecalho(texto, cabecalho, exatamente=False):
    encontrado = cabecalho.search(texto or "")
    if encontrado is None:
        return []
    numeros = [
        _numero(valor)
        for valor in PADRAO_NUMERO.findall((texto or "")[encontrado.end():])
    ]
    tamanho = 4 if exatamente else 3
    ofertas = []
    for indice in range(0, len(numeros) - tamanho + 1, tamanho):
        bloco = numeros[indice:indice + tamanho]
        oferta = {"linha": bloco[0]}
        if exatamente:
            oferta["exatamente"] = bloco[1]
            oferta["over"] = bloco[2]
            oferta["under"] = bloco[3]
        else:
            oferta["over"] = bloco[1]
            oferta["under"] = bloco[2]
        ofertas.append(oferta)
    return ofertas


def _separar_periodos(dados):
    encontrados = list(PADRAO_PERIODO.finditer(dados or ""))
    inicio_periodos = encontrados[0].start() if encontrados else len(dados or "")
    base = (dados or "")[:inicio_periodos]
    periodos = {}
    for indice, encontrado in enumerate(encontrados):
        fim = (
            encontrados[indice + 1].start()
            if indice + 1 < len(encontrados)
            else len(dados or "")
        )
        periodo = f"{encontrado.group(1)}T"
        exatamente = bool(encontrado.group(3))
        trecho = (dados or "")[encontrado.end():fim]
        periodos[periodo] = {
            "formato": (
                "tres_opcoes_exactly" if exatamente else "duas_opcoes"
            ),
            "ofertas": _ofertas_depois_cabecalho(
                trecho, re.compile(r"^"), exatamente=exatamente
            ),
        }
    return base, periodos


def estruturar_mercado(mercado):
    dados = mercado.get("dados") or ""
    dados_base, ofertas_periodos = _separar_periodos(dados)
    formato_exatamente = bool(PADRAO_EXACTLY_OVER_UNDER.search(dados_base))
    ofertas = (
        []
        if formato_exatamente
        else _ofertas_depois_cabecalho(dados_base, PADRAO_OVER_UNDER)
    )
    ofertas_exatamente = (
        _ofertas_depois_cabecalho(
            dados_base,
            PADRAO_EXACTLY_OVER_UNDER,
            exatamente=True,
        )
        if formato_exatamente else []
    )
    selecoes = {}
    proximo_gol = PADRAO_PROXIMO_GOL.search(dados)
    if proximo_gol:
        selecoes = {
            "casa": float(proximo_gol.group(1).replace(",", ".")),
            "visitante": float(proximo_gol.group(2).replace(",", ".")),
            "sem_gol": float(proximo_gol.group(3).replace(",", ".")),
        }
    categoria = classificar_mercado(mercado.get("mercado", ""))
    periodo_1t = ofertas_periodos.get("1T") or {}
    ofertas_ht = (
        periodo_1t.get("ofertas") or []
        if categoria == "gols"
        and periodo_1t.get("formato") == "duas_opcoes"
        else []
    )
    formato = (
        "tres_opcoes_exactly" if formato_exatamente else "duas_opcoes"
    )
    return {
        **mercado,
        "categoria": categoria,
        "escopo": classificar_escopo(mercado.get("mercado", "")),
        "tipo_mercado": classificar_tipo_mercado(
            mercado.get("mercado", ""),
            categoria,
            formato,
        ),
        "formato": formato,
        "ofertas": ofertas,
        "ofertas_exatamente": ofertas_exatamente,
        "ofertas_periodos": ofertas_periodos,
        "selecoes": selecoes,
        "ofertas_ht": ofertas_ht,
    }


def estruturar_odds(odds):
    odds = odds or {}
    return {
        tipo: [estruturar_mercado(item) for item in odds.get(tipo) or []]
        for tipo in ("pre_jogo", "ao_vivo")
    }


_TOTAL_NAO_INFORMADO = object()


def _oferta_um_evento(ofertas, total_atual):
    ofertas = list(ofertas or [])
    if total_atual is _TOTAL_NAO_INFORMADO:
        return ofertas[0] if ofertas else None
    if total_atual is None:
        return None
    try:
        total_atual = float(total_atual)
    except (TypeError, ValueError):
        return None
    candidatas = []
    for oferta in ofertas:
        try:
            linha = float(oferta.get("linha"))
        except (AttributeError, TypeError, ValueError):
            continue
        # A linha ainda não pode estar vencida e um único evento precisa
        # produzir vitória integral, não apenas meia vitória asiática.
        if total_atual <= linha <= total_atual + 0.5:
            candidatas.append((linha, oferta))
    if not candidatas:
        return None
    return max(candidatas, key=lambda item: item[0])[1]


def _oferta_com_tipo(oferta, mercado):
    return {
        **oferta,
        "tipo_mercado": mercado.get("tipo_mercado"),
    }


def escolher_over_ao_vivo(
    odds,
    categoria,
    total_atual=_TOTAL_NAO_INFORMADO,
    tipo_mercado=None,
):
    for mercado in (odds or {}).get("ao_vivo") or []:
        if mercado.get("categoria") != categoria:
            continue
        if (
            tipo_mercado is not None
            and mercado.get("tipo_mercado") != tipo_mercado
        ):
            continue
        if (mercado.get("escopo") or "total") != "total":
            continue
        if (mercado.get("formato") or "duas_opcoes") != "duas_opcoes":
            continue
        ofertas = mercado.get("ofertas") or []
        if ofertas:
            oferta = _oferta_um_evento(ofertas, total_atual)
            return _oferta_com_tipo(oferta, mercado) if oferta else None
    return None


def escolher_proximo_gol(odds, lado):
    for mercado in (odds or {}).get("ao_vivo") or []:
        nome = _sem_acentos(mercado.get("mercado", ""))
        if "proximo gol" not in nome:
            continue
        odd = (mercado.get("selecoes") or {}).get(lado)
        if odd is not None:
            return {"linha": lado, "over": odd}
    return None


def escolher_over_ht(odds, total_atual=_TOTAL_NAO_INFORMADO):
    for mercado in (odds or {}).get("ao_vivo") or []:
        ofertas = mercado.get("ofertas_ht") or []
        if ofertas:
            return _oferta_um_evento(ofertas, total_atual)
    return None


def escolher_over_periodo(
    odds,
    categoria,
    periodo,
    total_periodo_atual=_TOTAL_NAO_INFORMADO,
    tipo_mercado=None,
):
    periodo = str(periodo).upper()
    for mercado in (odds or {}).get("ao_vivo") or []:
        if mercado.get("categoria") != categoria:
            continue
        if (
            tipo_mercado is not None
            and mercado.get("tipo_mercado") != tipo_mercado
        ):
            continue
        dados_periodo = (mercado.get("ofertas_periodos") or {}).get(periodo)
        if not dados_periodo or dados_periodo.get("formato") != "duas_opcoes":
            continue
        ofertas = dados_periodo.get("ofertas") or []
        if ofertas:
            oferta = _oferta_um_evento(ofertas, total_periodo_atual)
            return _oferta_com_tipo(oferta, mercado) if oferta else None
    return None
