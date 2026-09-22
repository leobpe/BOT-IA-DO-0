import re
from datetime import datetime


JANELAS_MINUTOS = (5, 10, 15)
RETENCAO_MINUTOS = 20
TOLERANCIA_JANELA_MINUTOS = 3


def extrair_par(valor):
    if not valor:
        return None

    numeros = re.findall(r"\d+(?:[.,]\d+)?", str(valor))
    if len(numeros) < 2:
        return None

    return tuple(float(numero.replace(",", ".")) for numero in numeros[:2])


def metricas_temporais(estatisticas):
    return {
        "pressao": extrair_par(estatisticas.get("Índice de pressão")),
        "chutes": extrair_par(estatisticas.get("Chutes")),
        "escanteios": extrair_par(estatisticas.get("Escanteios")),
    }


def periodo_partida(status):
    texto = str(status or "").lower()
    if "intervalo" in texto or texto.strip() == "ht":
        return "primeiro_tempo"
    numeros = re.findall(r"\d{1,3}", texto)
    if numeros:
        return "primeiro_tempo" if int(numeros[0]) <= 45 else "segundo_tempo"
    if "1º" in texto or "first" in texto:
        return "primeiro_tempo"
    if "2º" in texto or "second" in texto:
        return "segundo_tempo"
    return None


def _total_gols(placar):
    numeros = re.findall(r"\d+", str(placar or ""))
    return sum(map(int, numeros[:2])) if len(numeros) >= 2 else None


def _cartoes_vermelhos(eventos):
    return sum(
        1
        for evento in eventos or []
        if str(evento.get("type", "")).lower() == "card"
        and "red" in str(evento.get("detail", "")).lower()
    )


def _delta_contador(atual, anterior):
    if atual is None or anterior is None:
        return None, False
    if atual[0] < anterior[0] or atual[1] < anterior[1]:
        return None, True
    return [
        round(atual[0] - anterior[0], 2),
        round(atual[1] - anterior[1], 2),
    ], False


def _resumo_pressao(itens):
    valores = [
        item["metricas"].get("pressao")
        for item in itens
        if item["metricas"].get("pressao") is not None
    ]
    if not valores:
        return None

    quantidade = len(valores)
    media = [
        round(sum(par[lado] for par in valores) / quantidade, 2)
        for lado in (0, 1)
    ]
    pico = [max(par[lado] for par in valores) for lado in (0, 1)]
    tendencia = [
        round(valores[-1][lado] - valores[0][lado], 2)
        for lado in (0, 1)
    ]
    dominio = [
        sum(1 for casa, fora in valores if casa > fora),
        sum(1 for casa, fora in valores if fora > casa),
    ]
    dominio_segundos = [0.0, 0.0]
    for atual, proximo in zip(itens, itens[1:]):
        pressao = atual["metricas"].get("pressao")
        if pressao is None:
            continue
        duracao = min(
            max(
                (proximo["instante"] - atual["instante"]).total_seconds(),
                0,
            ),
            180,
        )
        if pressao[0] > pressao[1]:
            dominio_segundos[0] += duracao
        elif pressao[1] > pressao[0]:
            dominio_segundos[1] += duracao
    return {
        "media": media,
        "pico": pico,
        "tendencia": tendencia,
        "amostras": quantidade,
        "dominio_amostras": dominio,
        "dominio_minutos": [
            round(segundos / 60, 2) for segundos in dominio_segundos
        ],
    }


class HistoricoTemporal:
    def __init__(self, retencao_minutos=RETENCAO_MINUTOS):
        self.retencao_minutos = retencao_minutos
        self.partidas = {}

    def restaurar(self, snapshots_por_url):
        self.partidas.clear()
        for url, snapshots in snapshots_por_url.items():
            itens = []
            for snapshot in snapshots:
                itens.append(
                    {
                        "instante": snapshot["instante"],
                        "metricas": metricas_temporais(
                            snapshot.get("estatisticas", {})
                        ),
                        "periodo": periodo_partida(snapshot.get("status")),
                        "gols": _total_gols(snapshot.get("placar")),
                        "cartoes_vermelhos": _cartoes_vermelhos(
                            (snapshot.get("confirmacao_api") or {}).get(
                                "eventos"
                            )
                        ),
                    }
                )
            if itens:
                itens.sort(key=lambda item: item["instante"])
                self.partidas[url] = itens
        return sum(len(itens) for itens in self.partidas.values())

    def calcular(
        self,
        url,
        estatisticas,
        instante=None,
        status=None,
        placar=None,
        eventos=None,
    ):
        instante = instante or datetime.now()
        metricas = metricas_temporais(estatisticas)
        historico = self.partidas.setdefault(url, [])
        anterior_original = historico[-1] if historico else None
        periodo = periodo_partida(status)
        periodos_anteriores = [item.get("periodo") for item in historico]
        ultimo_periodo = next(
            (item for item in reversed(periodos_anteriores) if item), None
        )
        if periodo and ultimo_periodo and periodo != ultimo_periodo:
            historico.clear()
        historico.append(
            {
                "instante": instante,
                "metricas": metricas,
                "periodo": periodo,
                "gols": _total_gols(placar),
                "cartoes_vermelhos": _cartoes_vermelhos(eventos),
            }
        )
        historico.sort(key=lambda item: item["instante"])

        limite = instante.timestamp() - (self.retencao_minutos * 60)
        historico[:] = [
            item
            for item in historico
            if item["instante"].timestamp() >= limite
        ]

        evolucao = {}
        for minutos in JANELAS_MINUTOS:
            alvo = instante.timestamp() - (minutos * 60)
            anteriores = [
                item
                for item in historico
                if item["instante"] < instante
                and item["instante"].timestamp() <= alvo
            ]

            if not anteriores:
                evolucao[str(minutos)] = None
                continue

            referencia = anteriores[-1]
            duracao_real = (
                instante - referencia["instante"]
            ).total_seconds() / 60
            if duracao_real > minutos + TOLERANCIA_JANELA_MINUTOS:
                evolucao[str(minutos)] = None
                continue
            deltas = {}
            pressao_anterior = referencia["metricas"].get("pressao")
            if metricas["pressao"] is None or pressao_anterior is None:
                deltas["pressao"] = None
            else:
                deltas["pressao"] = [
                    round(metricas["pressao"][lado] - pressao_anterior[lado], 2)
                    for lado in (0, 1)
                ]

            resets = []
            for nome in ("chutes", "escanteios"):
                delta, reiniciou = _delta_contador(
                    metricas[nome], referencia["metricas"].get(nome)
                )
                deltas[nome] = delta
                if reiniciou:
                    resets.append(nome)

            itens_janela = [
                item
                for item in historico
                if item["instante"] >= referencia["instante"]
                and item["instante"] <= instante
            ]
            deltas["pressao_resumo"] = _resumo_pressao(itens_janela)
            deltas["resets_detectados"] = resets
            deltas["duracao_real_minutos"] = round(duracao_real, 2)
            deltas["desvio_alvo_minutos"] = round(
                duracao_real - minutos, 2
            )
            evolucao[str(minutos)] = deltas

        janela5 = evolucao.get("5")
        janela10 = evolucao.get("10")
        aceleracao = {}
        if janela5 and janela10:
            for nome in ("chutes", "escanteios"):
                recente = janela5.get(nome)
                total = janela10.get(nome)
                if recente is None or total is None:
                    aceleracao[nome] = None
                else:
                    aceleracao[nome] = [
                        round((2 * recente[lado]) - total[lado], 2)
                        for lado in (0, 1)
                    ]
        evolucao["aceleracao_5_vs_5"] = aceleracao or None
        evolucao["periodo"] = periodo
        gols_atuais = _total_gols(placar)
        vermelhos_atuais = _cartoes_vermelhos(eventos)
        evolucao["eventos_recentes"] = {
            "gol": bool(
                anterior_original
                and gols_atuais is not None
                and anterior_original.get("gols") is not None
                and gols_atuais > anterior_original["gols"]
            ),
            "cartao_vermelho": bool(
                anterior_original
                and vermelhos_atuais
                > (anterior_original.get("cartoes_vermelhos") or 0)
            ),
            "mudanca_periodo": bool(
                anterior_original
                and periodo
                and anterior_original.get("periodo")
                and periodo != anterior_original["periodo"]
            ),
        }

        return evolucao


def formatar_delta(valor):
    if not valor:
        return "-"
    return f"{valor[0]:+g}/{valor[1]:+g}"
