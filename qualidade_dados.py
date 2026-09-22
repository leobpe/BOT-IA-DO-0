import re


CAMPOS_ESSENCIAIS = (
    "Chutes",
    "Chutes no gol",
    "Índice de pressão",
    "Escanteios",
    "Ataques perigosos",
)


def extrair_placar(valor):
    numeros = re.findall(r"\d+", str(valor or ""))
    if len(numeros) < 2:
        return None
    return [int(numeros[0]), int(numeros[1])]


def extrair_minuto(valor):
    texto = str(valor or "").lower()
    if "intervalo" in texto or texto.strip() == "ht":
        return 45
    numeros = re.findall(r"\d{1,3}", texto)
    return int(numeros[0]) if numeros else None


def avaliar_qualidade(
    jogo, estatisticas, confirmacao_api=None, latencia_coleta_segundos=None
):
    presentes = [
        campo
        for campo in CAMPOS_ESSENCIAIS
        if estatisticas.get(campo) not in (None, "", "-")
    ]
    ausentes = [campo for campo in CAMPOS_ESSENCIAIS if campo not in presentes]
    completude = len(presentes) / len(CAMPOS_ESSENCIAIS)
    pontuacao = completude * 80.0
    alertas = []
    fontes = ["packball"]
    divergencia_critica = False
    atraso_api_minutos = None

    if confirmacao_api:
        fontes.append("api_football")
        similaridade = float(confirmacao_api.get("similaridade") or 0)
        pontuacao += min(similaridade, 1.0) * 20.0

        placar_packball = extrair_placar(jogo.get("placar"))
        placar_api = confirmacao_api.get("placar")
        if (
            placar_packball is not None
            and isinstance(placar_api, list)
            and len(placar_api) >= 2
            and None not in placar_api[:2]
            and placar_packball != placar_api[:2]
        ):
            divergencia_critica = True
            pontuacao = min(pontuacao, 35.0)
            alertas.append("placar_divergente_api")

        minuto_packball = extrair_minuto(jogo.get("status"))
        status_api = confirmacao_api.get("status") or {}
        minuto_api = status_api.get("elapsed")
        if (
            minuto_packball is not None
            and isinstance(minuto_api, (int, float))
            and abs(minuto_packball - minuto_api) > 5
        ):
            alertas.append("minuto_divergente_api")
            pontuacao -= 15.0
        if minuto_packball is not None and isinstance(minuto_api, (int, float)):
            atraso_api_minutos = abs(minuto_packball - minuto_api)
    else:
        # Ausência na API não invalida o PackBall; só remove a confirmação extra.
        pontuacao += 10.0
        alertas.append("sem_confirmacao_api")

    if ausentes:
        alertas.append("campos_essenciais_ausentes")

    pontuacao = round(max(0.0, min(pontuacao, 100.0)), 1)
    return {
        "pontuacao": pontuacao,
        "completude": round(completude, 3),
        "campos_ausentes": ausentes,
        "fontes": fontes,
        "alertas": alertas,
        "divergencia_critica": divergencia_critica,
        "apto_para_sinal": pontuacao >= 70 and not divergencia_critica,
        "versao": "qualidade-v1",
        "latencia_coleta_segundos": (
            round(float(latencia_coleta_segundos), 3)
            if latencia_coleta_segundos is not None else None
        ),
        "atraso_api_minutos": atraso_api_minutos,
    }
