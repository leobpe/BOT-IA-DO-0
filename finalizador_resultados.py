import json
import os
import re
import unicodedata
from datetime import datetime, timedelta

from api_football import associar_jogo
from backtest import liquidar_over_asiatico
from controle_acesso_packball import PackBallBloqueadoError
from evolucao import extrair_par
from qualidade_dados import extrair_minuto


STATUS_ENCERRADOS_API = {"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO"}
STATUS_ANULADOS_API = {"CANC", "ABD", "AWD", "WO"}
STATUS_PRORROGACAO_API = {"AET", "PEN"}
COOLDOWN_FINALIZACAO_API_SOMBRA_MINUTOS = 10
COOLDOWN_FINALIZACAO_API_ENTREGUE_PADRAO_MINUTOS = 3
VAR_COOLDOWN_FINALIZACAO_API_ENTREGUE = (
    "FINALIZACAO_API_COOLDOWN_ENTREGUE_MINUTOS"
)


def _cooldown_finalizacao_api_entregue_minutos():
    valor = os.getenv(VAR_COOLDOWN_FINALIZACAO_API_ENTREGUE)
    try:
        minutos = int(valor) if valor is not None else (
            COOLDOWN_FINALIZACAO_API_ENTREGUE_PADRAO_MINUTOS
        )
    except (TypeError, ValueError):
        minutos = COOLDOWN_FINALIZACAO_API_ENTREGUE_PADRAO_MINUTOS
    return max(1, min(minutos, COOLDOWN_FINALIZACAO_API_SOMBRA_MINUTOS))


def _normalizar_status(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    ).strip().lower()


def _snapshot_fim_tempo_regulamentar(banco, partida_id):
    """Localiza o último snapshot antes da pausa que iniciou a prorrogação."""
    snapshots = banco.conexao.execute(
        """
        SELECT id, coletado_em, placar, status, estatisticas_json
        FROM snapshots
        WHERE partida_id=?
        ORDER BY id
        """,
        (partida_id,),
    ).fetchall()
    ultimo_regulamentar = None
    for snapshot in snapshots:
        status = _normalizar_status(snapshot["status"])
        minuto = extrair_minuto(snapshot["status"])
        if minuto is not None and 85 <= minuto <= 99:
            # O PackBall nem sempre exibe 90: em jogos reais observamos a
            # transicao de 89 diretamente para BREAK e de 93 para prorrogacao.
            ultimo_regulamentar = snapshot
        limite_regulamentar = (
            "break" in status
            or "fim do tempo regulamentar" in status
            or "end of regulation" in status
            or status in {"aet", "pen"}
            or "penalti" in status
            or "prorrog" in status
            or "extra time" in status
        )
        if limite_regulamentar and ultimo_regulamentar is not None:
            return ultimo_regulamentar
    return None


def _placar_regulamentar_api(item, orientacao):
    status = ((item.get("fixture") or {}).get("status") or {}).get("short")
    if status in STATUS_PRORROGACAO_API:
        origem = ((item.get("score") or {}).get("fulltime") or {})
    else:
        origem = item.get("goals") or {}
    placar = [origem.get("home"), origem.get("away")]
    if placar[0] is None or placar[1] is None:
        return None
    try:
        placar = [int(placar[0]), int(placar[1])]
    except (TypeError, ValueError):
        return None
    if orientacao == "invertida":
        placar.reverse()
    return placar


def _eventos_tempo_regulamentar(eventos):
    resultado = []
    for evento in eventos or []:
        try:
            minuto = int(((evento.get("time") or {}).get("elapsed")))
        except (AttributeError, TypeError, ValueError):
            continue
        if minuto <= 90:
            resultado.append(evento)
    return resultado


def _escanteios_api(item):
    times = item.get("teams") or {}
    ids = [
        (times.get("home") or {}).get("id"),
        (times.get("away") or {}).get("id"),
    ]
    if None in ids or ids[0] == ids[1]:
        return None
    valores = {ids[0]: None, ids[1]: None}
    for bloco in item.get("statistics") or []:
        time_id = (bloco.get("team") or {}).get("id")
        for estatistica in bloco.get("statistics") or []:
            if estatistica.get("type") == "Corner Kicks":
                valor = estatistica.get("value")
                try:
                    valores[time_id] = int(float(valor))
                except (TypeError, ValueError):
                    valores[time_id] = None
    if valores.get(ids[0]) is None or valores.get(ids[1]) is None:
        return None
    return f"{valores[ids[0]]}-{valores[ids[1]]}"


def _placar_intervalo_api(item, orientacao="direta"):
    intervalo = (item.get("score") or {}).get("halftime") or {}
    casa = intervalo.get("home")
    fora = intervalo.get("away")
    if casa is None or fora is None:
        return None
    try:
        placar = [int(casa), int(fora)]
    except (TypeError, ValueError):
        return None
    if orientacao == "invertida":
        placar.reverse()
    return f"{placar[0]}-{placar[1]}"


def _placar_intervalo_packball(texto):
    """Extrai o placar HT exibido no resumo final do PackBall.

    Em algumas ligas o painel final chega como ``HT 0-1 1-2``. O primeiro
    placar e a evidência do intervalo; o segundo e o placar final. Sem esta
    leitura, sinais de Gol HT permaneciam pendentes apesar da fonte já ter
    mostrado o resultado necessário.
    """
    correspondencia = re.search(
        r"(?:^|\s)HT\s*(\d+)\s*[-:x]\s*(\d+)(?:\s|$)",
        str(texto or ""),
        flags=re.IGNORECASE,
    )
    if correspondencia is None:
        return None
    return f"{int(correspondencia.group(1))}-{int(correspondencia.group(2))}"


def _placar_par(valor):
    numeros = re.findall(r"\d+", str(valor or ""))
    if len(numeros) != 2:
        return None
    return int(numeros[0]), int(numeros[1])


def _minuto_primeiro_tempo_evento_packball(evento):
    """Classifica um gol no 1T sem confundir ``45+N`` com o 2T."""
    if not isinstance(evento, dict):
        return None
    texto = str(evento.get("minuto") or "").strip()
    acrescimo = re.fullmatch(r"(\d+)\s*\+\s*(\d+)", texto)
    if acrescimo is not None:
        return int(acrescimo.group(1)) <= 45
    valor = evento.get("minuto_ordenacao", evento.get("minuto"))
    try:
        return float(valor) <= 45.0
    except (TypeError, ValueError):
        return None


def _placar_intervalo_por_timeline_packball(eventos, placar_final):
    """Reconstrói o HT apenas quando a timeline explica o placar inteiro.

    A igualdade por lado impede que uma timeline parcial ou duplicada seja
    usada como resultado. Sem essa prova, o retorno permanece ``None``.
    """
    final = _placar_par(placar_final)
    if final is None or not isinstance(eventos, list):
        return None
    contagem_final = {"casa": 0, "visitante": 0}
    contagem_ht = {"casa": 0, "visitante": 0}
    for evento in eventos:
        if not isinstance(evento, dict):
            return None
        lado = evento.get("lado")
        primeiro_tempo = _minuto_primeiro_tempo_evento_packball(evento)
        if lado not in contagem_final or primeiro_tempo is None:
            return None
        contagem_final[lado] += 1
        if primeiro_tempo:
            contagem_ht[lado] += 1
    if (
        contagem_final["casa"] != final[0]
        or contagem_final["visitante"] != final[1]
    ):
        return None
    return f"{contagem_ht['casa']}-{contagem_ht['visitante']}"


class FinalizadorResultadosAPI:
    def __init__(self, banco, api, avaliador):
        self.banco = banco
        self.api = api
        self.avaliador = avaliador

    def _tem_mercado_pendente(self, partida_id, mercado):
        return self.banco.conexao.execute(
            """
            SELECT 1
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.partida_id=?
              AND s.mercado=?
              AND r.sinal_id IS NULL
              AND (
                  s.status IN ('aprovado', 'simulacao', 'auditoria')
                  OR EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=s.id
                        AND origem.canal LIKE '%:aguardar_odd'
                        AND origem.status='entregue'
                        AND NOT EXISTS (
                            SELECT 1 FROM entregas_alertas final
                            WHERE final.sinal_id=s.id
                              AND final.canal=(
                                  origem.canal || ':monitoramento_final'
                              )
                        )
                  )
              )
            LIMIT 1
            """,
            (partida_id, mercado),
        ).fetchone() is not None

    def _tem_algum_mercado_pendente(self, partida_id, mercados):
        return any(
            self._tem_mercado_pendente(partida_id, mercado)
            for mercado in mercados
        )

    def _pendentes_restantes(self, partida_id):
        return self.banco.conexao.execute(
            """
            SELECT COUNT(*)
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.partida_id=?
              AND r.sinal_id IS NULL
              AND (
                  s.status IN ('aprovado', 'simulacao', 'auditoria')
                  OR EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=s.id
                        AND origem.canal LIKE '%:aguardar_odd'
                        AND origem.status='entregue'
                        AND NOT EXISTS (
                            SELECT 1 FROM entregas_alertas final
                            WHERE final.sinal_id=s.id
                              AND final.canal=(
                                  origem.canal || ':monitoramento_final'
                              )
                        )
                  )
              )
            """,
            (partida_id,),
        ).fetchone()[0]

    def _obter_escanteios_finais(self, item, partida, times_orientados):
        item_orientado = {**item, "teams": times_orientados}
        escanteios = _escanteios_api(item_orientado)
        if escanteios is not None:
            return escanteios
        if not self._tem_algum_mercado_pendente(
            partida["id"],
            (
                "proximo_escanteio",
                "escanteios_ft_asiatico",
                "escanteios_2t",
            ),
        ):
            return None
        fixture_id = (item.get("fixture") or {}).get("id")
        if fixture_id is None:
            return None
        estatisticas = self.api.estatisticas(fixture_id)
        return _escanteios_api(
            {
                "teams": times_orientados,
                "statistics": estatisticas or [],
            }
        )

    def _obter_eventos_finais(self, item, partida):
        if not self._tem_mercado_pendente(partida["id"], "proximo_gol"):
            return item.get("events") or []
        eventos = item.get("events") or []
        if eventos:
            return eventos
        fixture_id = (item.get("fixture") or {}).get("id")
        consultar = getattr(self.api, "eventos", None)
        if fixture_id is None or consultar is None:
            return []
        return consultar(fixture_id) or []

    def _resolver_gol_ht_por_intervalo(
        self, item, partida, orientado, instante=None,
    ):
        """Liquida Gol HT assim que o intervalo já pode ser comprovado."""
        if not self._tem_mercado_pendente(partida["id"], "gol_ht"):
            return 0
        placar_intervalo = _placar_intervalo_api(
            item, orientado["orientacao"]
        )
        if placar_intervalo is None:
            return 0
        placar_api = [int(valor) for valor in placar_intervalo.split("-")]
        fixture = item.get("fixture") or {}
        snapshot_intervalo = self.banco.salvar_registro(
            {
                "coletado_em": instante
                or datetime.now().replace(microsecond=0),
                "url": partida["packball_url"],
                "mandante": partida["mandante"],
                "visitante": partida["visitante"],
                "placar": placar_intervalo,
                "status": "Intervalo",
                "estatisticas": {},
                "confirmacao_api": {
                    "fixture_id": fixture.get("id"),
                    "status": {"short": "HT"},
                    "placar": placar_api,
                    "placar_intervalo": placar_api,
                    "times": orientado["times"],
                    "orientacao": orientado["orientacao"],
                    "similaridade": orientado["similaridade"],
                },
                "qualidade": {
                    "pontuacao": 100,
                    "fontes": ["api_football"],
                    "versao": "resultado-api-ht-v2",
                },
            }
        )
        if not snapshot_intervalo:
            return 0
        return self.avaliador.avaliar_snapshot(snapshot_intervalo)

    def _recuperar_intervalos_persistidos(self):
        """Liquida HT com a confirmação API já salva em snapshots 2H/FT."""
        linhas = self.banco.conexao.execute(
            """
            SELECT p.id, p.packball_url, p.mandante, p.visitante,
                   sp.confirmacao_api_json
            FROM partidas p
            JOIN sinais s ON s.partida_id=p.id
             AND s.status IN ('aprovado', 'simulacao', 'auditoria')
             AND s.mercado='gol_ht'
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            JOIN snapshots sp ON sp.partida_id=p.id AND sp.id>s.snapshot_id
            WHERE r.sinal_id IS NULL
              AND sp.confirmacao_api_json IS NOT NULL
              AND sp.confirmacao_api_json NOT IN ('', 'null')
            ORDER BY p.id, sp.id DESC
            """
        ).fetchall()
        vistos = set()
        resolvidos = 0
        for linha in linhas:
            partida_id = int(linha["id"])
            if partida_id in vistos:
                continue
            try:
                confirmacao = json.loads(
                    linha["confirmacao_api_json"] or "null"
                ) or {}
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            status = (confirmacao.get("status") or {}).get("short")
            placar = confirmacao.get("placar_intervalo")
            if (
                status not in {"HT", "2H", "ET", "BT", "P", "FT", "AET", "PEN"}
                or not isinstance(placar, (list, tuple))
                or len(placar) < 2
            ):
                continue
            try:
                placar = [int(placar[0]), int(placar[1])]
            except (TypeError, ValueError):
                continue
            vistos.add(partida_id)
            snapshot_intervalo = self.banco.salvar_registro(
                {
                    "coletado_em": datetime.now().replace(microsecond=0),
                    "url": linha["packball_url"],
                    "mandante": linha["mandante"],
                    "visitante": linha["visitante"],
                    "placar": f"{placar[0]}-{placar[1]}",
                    "status": "Intervalo",
                    "estatisticas": {},
                    "confirmacao_api": {
                        **confirmacao,
                        "status": {"short": "HT"},
                        "placar": placar,
                        "placar_intervalo": placar,
                    },
                    "qualidade": {
                        "pontuacao": 100,
                        "fontes": ["api_football"],
                        "versao": "resultado-api-ht-persistido-v1",
                    },
                }
            )
            if snapshot_intervalo:
                resolvidos += self.avaliador.avaliar_snapshot(
                    snapshot_intervalo
                )
        return resolvidos

    @staticmethod
    def _orientar_item(item, partida):
        associado = associar_jogo(
            {
                "mandante": partida["mandante"],
                "visitante": partida["visitante"],
            },
            [item],
        )
        if associado is None:
            return None
        orientacao_confirmada = associado["orientacao"]
        orientacao_persistida = partida["api_orientacao"]
        if (
            orientacao_persistida in ("direta", "invertida")
            and orientacao_persistida != orientacao_confirmada
        ):
            return None
        orientacao = orientacao_confirmada
        times = item.get("teams") or {}
        gols = item.get("goals") or {}
        placar = [gols.get("home"), gols.get("away")]
        if orientacao == "invertida":
            placar.reverse()
            times = {
                "home": times.get("away") or {},
                "away": times.get("home") or {},
            }
        return {
            "orientacao": orientacao,
            "times": times,
            "placar": placar,
            "similaridade": associado["similaridade"],
        }

    def executar(self):
        resolvidos_intervalos_persistidos = (
            self._recuperar_intervalos_persistidos()
        )
        pendentes = self.banco.conexao.execute(
            """
            SELECT DISTINCT p.id, p.packball_url, p.mandante,
                   p.visitante, p.api_fixture_id, p.api_orientacao,
                   EXISTS (
                       SELECT 1
                       FROM sinais enviado
                       JOIN entregas_alertas entrega
                         ON entrega.sinal_id=enviado.id
                       LEFT JOIN resultados_sinais resultado_enviado
                         ON resultado_enviado.sinal_id=enviado.id
                       WHERE enviado.partida_id=p.id
                         AND resultado_enviado.sinal_id IS NULL
                         AND entrega.status='entregue'
                         AND entrega.provedor='telegram'
                         AND entrega.provedor_mensagem_id IS NOT NULL
                         AND (
                             enviado.status IN (
                                 'aprovado', 'simulacao', 'auditoria'
                             )
                             OR entrega.canal LIKE '%:aguardar_odd'
                         )
                   ) AS tem_sinal_entregue
            FROM partidas p
            JOIN sinais s ON s.partida_id=p.id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE r.sinal_id IS NULL AND p.api_fixture_id IS NOT NULL
              AND (
                  s.status IN ('aprovado', 'simulacao', 'auditoria')
                  OR EXISTS (
                      SELECT 1 FROM entregas_alertas origem
                      WHERE origem.sinal_id=s.id
                        AND origem.canal LIKE '%:aguardar_odd'
                        AND origem.status='entregue'
                        AND NOT EXISTS (
                            SELECT 1 FROM entregas_alertas final
                            WHERE final.sinal_id=s.id
                              AND final.canal=(
                                  origem.canal || ':monitoramento_final'
                              )
                        )
                  )
              )
            """
        ).fetchall()
        agora = datetime.now()
        cooldown_entregue = _cooldown_finalizacao_api_entregue_minutos()
        pendentes_aptos = []
        suprimidas_cooldown_entregue = 0
        suprimidas_cooldown_sombra = 0
        for item in pendentes:
            entregue = bool(item["tem_sinal_entregue"])
            recente = self.banco.consulta_finalizacao_recente(
                item["id"],
                "api_football",
                minutos=(
                    cooldown_entregue
                    if entregue
                    else COOLDOWN_FINALIZACAO_API_SOMBRA_MINUTOS
                ),
                agora=agora,
            )
            if recente:
                if entregue:
                    suprimidas_cooldown_entregue += 1
                else:
                    suprimidas_cooldown_sombra += 1
                continue
            pendentes_aptos.append(item)
        pendentes = pendentes_aptos
        consultadas_entregues = sum(
            1 for item in pendentes if item["tem_sinal_entregue"]
        )
        diagnostico_cooldown = {
            "cooldown_entregue_minutos": cooldown_entregue,
            "cooldown_sombra_minutos": (
                COOLDOWN_FINALIZACAO_API_SOMBRA_MINUTOS
            ),
            "consultadas_entregues": consultadas_entregues,
            "suprimidas_cooldown_entregue": (
                suprimidas_cooldown_entregue
            ),
            "suprimidas_cooldown_sombra": suprimidas_cooldown_sombra,
            "rollback": (
                f"{VAR_COOLDOWN_FINALIZACAO_API_ENTREGUE}="
                f"{COOLDOWN_FINALIZACAO_API_SOMBRA_MINUTOS}"
            ),
        }
        if not pendentes:
            return {
                "consultadas": 0,
                "encerradas": 0,
                "resolvidos": resolvidos_intervalos_persistidos,
                "respostas_ausentes": 0,
                "respostas_invalidas": 0,
                "intervalos_persistidos_recuperados": (
                    resolvidos_intervalos_persistidos
                ),
                **diagnostico_cooldown,
            }

        por_fixture = {item["api_fixture_id"]: item for item in pendentes}
        respostas_brutas = self.api.partidas_por_ids(list(por_fixture)) or []
        respostas = []
        respostas_invalidas = 0
        fixtures_respondidos = set()
        for resposta in respostas_brutas:
            if not isinstance(resposta, dict):
                respostas_invalidas += 1
                continue
            fixture_id = ((resposta.get("fixture") or {}).get("id"))
            if fixture_id not in por_fixture:
                respostas_invalidas += 1
                continue
            respostas.append(resposta)
            fixtures_respondidos.add(fixture_id)

        fixtures_ausentes = set(por_fixture) - fixtures_respondidos
        for fixture_id in fixtures_ausentes:
            partida = por_fixture[fixture_id]
            self.banco.registrar_consulta_finalizacao(
                partida["id"],
                "api_football",
                "resposta_ausente",
                erro=f"fixture {fixture_id} ausente ou inválida na resposta",
            )
        encerradas = 0
        resolvidos = resolvidos_intervalos_persistidos
        for item in respostas:
            fixture = item.get("fixture") or {}
            status = fixture.get("status") or {}
            if status.get("short") not in STATUS_ENCERRADOS_API:
                partida = por_fixture.get(fixture.get("id"))
                if partida is not None:
                    if status.get("short") in {"HT", "2H", "ET", "BT", "P"}:
                        orientado = self._orientar_item(item, partida)
                        if orientado is not None:
                            resolvidos += self._resolver_gol_ht_por_intervalo(
                                item, partida, orientado
                            )
                    self.banco.registrar_consulta_finalizacao(
                        partida["id"],
                        "api_football",
                        "em_andamento",
                        status_observado=status.get("short"),
                    )
                continue
            partida = por_fixture.get(fixture.get("id"))
            if partida is None:
                continue
            orientado = self._orientar_item(item, partida)
            if orientado is None:
                self.banco.registrar_consulta_finalizacao(
                    partida["id"],
                    "api_football",
                    "erro_associacao",
                    status_observado=status.get("short"),
                    erro="orientação das equipes não confirmada",
                )
                continue
            status_curto = status.get("short")
            placar_final = _placar_regulamentar_api(
                item, orientado["orientacao"]
            )
            if status_curto in STATUS_ANULADOS_API:
                casa, fora = orientado["placar"]
            elif placar_final is None:
                self.banco.registrar_consulta_finalizacao(
                    partida["id"],
                    "api_football",
                    "finalizado_dados_incompletos",
                    status_observado=status_curto,
                    erro="placar do tempo regulamentar ausente",
                )
                continue
            else:
                casa, fora = placar_final
            placar = (
                f"{casa}-{fora}"
                if casa is not None and fora is not None else ""
            )
            snapshot_regulamentar = (
                _snapshot_fim_tempo_regulamentar(
                    self.banco, partida["id"]
                )
                if status_curto in STATUS_PRORROGACAO_API else None
            )
            if status_curto in STATUS_ANULADOS_API:
                escanteios = None
            elif status_curto in STATUS_PRORROGACAO_API:
                try:
                    estatisticas_regulamentares = json.loads(
                        snapshot_regulamentar["estatisticas_json"] or "{}"
                    ) if snapshot_regulamentar is not None else {}
                except (TypeError, json.JSONDecodeError):
                    estatisticas_regulamentares = {}
                escanteios = estatisticas_regulamentares.get("Escanteios")
            else:
                escanteios = self._obter_escanteios_finais(
                    item, partida, orientado["times"]
                )
            eventos = (
                []
                if status_curto in STATUS_ANULADOS_API
                else self._obter_eventos_finais(item, partida)
            )
            if status_curto in STATUS_PRORROGACAO_API:
                eventos = _eventos_tempo_regulamentar(eventos)
            instante_final = datetime.now().replace(microsecond=0)
            if (
                status_curto not in STATUS_ANULADOS_API
                and self._tem_mercado_pendente(partida["id"], "gol_ht")
            ):
                resolvidos += self._resolver_gol_ht_por_intervalo(
                    item,
                    partida,
                    orientado,
                    instante=instante_final - timedelta(seconds=1),
                )

            registro = {
                "coletado_em": instante_final,
                "url": partida["packball_url"],
                "mandante": partida["mandante"],
                "visitante": partida["visitante"],
                "placar": placar,
                "status": (
                    "Anulado"
                    if status_curto in STATUS_ANULADOS_API
                    else "Finalizado"
                ),
                "estatisticas": (
                    {"Escanteios": escanteios} if escanteios else {}
                ),
                "confirmacao_api": {
                    "fixture_id": fixture.get("id"),
                    "status": status,
                    "placar": [casa, fora],
                    "times": orientado["times"],
                    "orientacao": orientado["orientacao"],
                    "similaridade": orientado["similaridade"],
                    "eventos": eventos,
                },
                "qualidade": {
                    "pontuacao": 100,
                    "fontes": (
                        ["api_football", "packball"]
                        if escanteios is not None
                        and status_curto in STATUS_PRORROGACAO_API
                        else ["api_football"]
                    ),
                    "versao": (
                        "resultado-api-regulamentar-v1"
                        if status_curto in STATUS_PRORROGACAO_API
                        else "resultado-api-v1"
                    ),
                },
            }
            snapshot_id = self.banco.salvar_registro(registro)
            if snapshot_id:
                resolvidos_agora = self.avaliador.avaliar_snapshot(snapshot_id)
                resolvidos += resolvidos_agora
                self.banco.registrar_consulta_finalizacao(
                    partida["id"],
                    "api_football",
                    (
                        "finalizado"
                        if self._pendentes_restantes(partida["id"]) == 0
                        else "finalizado_dados_incompletos"
                    ),
                    status_observado=status.get("short"),
                    placar_observado=placar,
                )
                encerradas += 1
        return {
            "consultadas": len(pendentes),
            "encerradas": encerradas,
            "resolvidos": resolvidos,
            "respostas_ausentes": len(fixtures_ausentes),
            "respostas_invalidas": respostas_invalidas,
            "intervalos_persistidos_recuperados": (
                resolvidos_intervalos_persistidos
            ),
            **diagnostico_cooldown,
        }


class FinalizadorResultadosPackBall:
    def __init__(self, banco, coletor, avaliador, limite_por_ciclo=3):
        self.banco = banco
        self.coletor = coletor
        self.avaliador = avaliador
        self.limite_por_ciclo = limite_por_ciclo

    def _pendentes_restantes(self, partida_id):
        return self.banco.conexao.execute(
            """
            SELECT COUNT(*)
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.partida_id=?
              AND s.status IN ('aprovado', 'simulacao', 'auditoria')
              AND r.sinal_id IS NULL
            """,
            (partida_id,),
        ).fetchone()[0]

    def _tem_mercado_pendente(self, partida_id, mercado):
        return self.banco.conexao.execute(
            """
            SELECT 1
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.partida_id=?
              AND s.status IN ('aprovado', 'simulacao', 'auditoria')
              AND s.mercado=?
              AND r.sinal_id IS NULL
            LIMIT 1
            """,
            (partida_id, mercado),
        ).fetchone() is not None

    def _resolver_gol_ht_por_texto(
        self, partida, texto_status, instante=None,
    ):
        if not self._tem_mercado_pendente(partida["id"], "gol_ht"):
            return 0
        placar_intervalo = _placar_intervalo_packball(texto_status)
        if placar_intervalo is None:
            return 0
        snapshot_intervalo = self.banco.salvar_registro(
            {
                "coletado_em": instante
                or datetime.now().replace(microsecond=0),
                "url": partida["packball_url"],
                "mandante": partida["mandante"],
                "visitante": partida["visitante"],
                "placar": placar_intervalo,
                "status": "Intervalo",
                "estatisticas": {},
                "qualidade": {
                    "pontuacao": 90,
                    "fontes": ["packball"],
                    "versao": "resultado-packball-ht-v1",
                },
            }
        )
        if not snapshot_intervalo:
            return 0
        return self.avaliador.avaliar_snapshot(snapshot_intervalo)

    def _resolver_gol_ht_por_timeline(
        self, partida, eventos, placar_final, instante=None,
    ):
        """Usa a timeline final somente quando ela fecha com o placar."""
        if not self._tem_mercado_pendente(partida["id"], "gol_ht"):
            return 0
        placar_intervalo = _placar_intervalo_por_timeline_packball(
            eventos, placar_final
        )
        if placar_intervalo is None:
            return 0
        snapshot_intervalo = self.banco.salvar_registro(
            {
                "coletado_em": instante
                or datetime.now().replace(microsecond=0),
                "url": partida["packball_url"],
                "mandante": partida["mandante"],
                "visitante": partida["visitante"],
                "placar": placar_intervalo,
                "status": "Intervalo",
                "estatisticas": {},
                "qualidade": {
                    "pontuacao": 90,
                    "fontes": ["packball"],
                    "versao": "resultado-packball-ht-timeline-v1",
                },
            }
        )
        if not snapshot_intervalo:
            return 0
        return self.avaliador.avaliar_snapshot(snapshot_intervalo)

    def _recuperar_intervalos_persistidos(self):
        """Reaproveita resumos finais PackBall que já contêm ``HT x-y``."""
        partidas = self.banco.conexao.execute(
            """
            SELECT DISTINCT p.id, p.packball_url, p.mandante, p.visitante,
                   cf.status_observado, cf.consultado_em
            FROM partidas p
            JOIN sinais s ON s.partida_id=p.id
             AND s.status IN ('aprovado', 'simulacao', 'auditoria')
             AND s.mercado='gol_ht'
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            JOIN consultas_finalizacao cf ON cf.id=(
                SELECT MAX(c2.id)
                FROM consultas_finalizacao c2
                WHERE c2.partida_id=p.id
                  AND c2.fonte='packball'
                  AND UPPER(c2.status_observado) LIKE '%HT%'
            )
            WHERE r.sinal_id IS NULL
            """
        ).fetchall()
        resolvidos = 0
        for partida in partidas:
            resolvidos += self._resolver_gol_ht_por_texto(
                partida, partida["status_observado"]
            )
        return resolvidos

    def _regulamentar_ja_processado(self, partida_id):
        return self.banco.conexao.execute(
            """
            SELECT 1 FROM consultas_finalizacao
            WHERE partida_id=? AND fonte='packball'
              AND status_observado='tempo_regulamentar'
            LIMIT 1
            """,
            (partida_id,),
        ).fetchone() is not None

    def _final_incompleto_confirmado(self, partida_id, minimo=3):
        """Evita revisitar indefinidamente uma partida ja finalizada."""
        quantidade = self.banco.conexao.execute(
            """
            SELECT COUNT(*)
            FROM consultas_finalizacao
            WHERE partida_id=? AND fonte='packball'
              AND estado='finalizado_dados_incompletos'
            """,
            (partida_id,),
        ).fetchone()[0]
        return int(quantidade or 0) >= int(minimo)

    def _finalizar_snapshot_regulamentar(self, partida, snapshot):
        try:
            estatisticas = json.loads(snapshot["estatisticas_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            estatisticas = {}
        registro = {
            "coletado_em": datetime.now().replace(microsecond=0),
            "url": partida["packball_url"],
            "mandante": partida["mandante"],
            "visitante": partida["visitante"],
            "placar": snapshot["placar"],
            "status": "Finalizado (90min)",
            "estatisticas": estatisticas,
            "qualidade": {
                "pontuacao": 90,
                "fontes": ["packball"],
                "versao": "resultado-packball-regulamentar-v1",
            },
        }
        snapshot_id = self.banco.salvar_registro(registro)
        resolvidos = (
            self.avaliador.avaliar_snapshot(snapshot_id)
            if snapshot_id else 0
        )
        self.banco.registrar_consulta_finalizacao(
            partida["id"],
            "packball",
            (
                "finalizado"
                if self._pendentes_restantes(partida["id"]) == 0
                else "finalizado_dados_incompletos"
            ),
            status_observado="tempo_regulamentar",
            placar_observado=snapshot["placar"],
        )
        return resolvidos

    def executar(
        self, pagina, urls_ao_vivo=None, interromper_fn=None,
        limite_navegacoes=None,
    ):
        urls_ao_vivo = set(urls_ao_vivo or [])
        agora = datetime.now()
        resolvidos_intervalos_persistidos = (
            self._recuperar_intervalos_persistidos()
        )
        limite_navegacoes = (
            self.limite_por_ciclo
            if limite_navegacoes is None
            else max(
                0,
                min(int(limite_navegacoes), self.limite_por_ciclo),
            )
        )
        pendentes = self.banco.conexao.execute(
            """
            SELECT p.id, p.packball_url, p.mandante, p.visitante,
                   MAX(sn.coletado_em) AS ultimo_snapshot,
                   MIN(s.criado_em) AS primeiro_sinal_pendente
            FROM partidas p
            JOIN sinais s ON s.partida_id=p.id
             AND s.status IN ('aprovado', 'simulacao', 'auditoria')
            JOIN snapshots sn ON sn.partida_id=p.id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE r.sinal_id IS NULL
            GROUP BY p.id, p.packball_url, p.mandante, p.visitante
            ORDER BY primeiro_sinal_pendente, p.id
            """
        ).fetchall()
        candidatos = []
        regulamentares = []
        suprimidas_final_incompleto = 0
        for item in pendentes:
            snapshot_regulamentar = _snapshot_fim_tempo_regulamentar(
                self.banco, item["id"]
            )
            if (
                snapshot_regulamentar is not None
                and not self._regulamentar_ja_processado(item["id"])
            ):
                regulamentares.append((item, snapshot_regulamentar))
                if (
                    len(regulamentares) + len(candidatos)
                    >= self.limite_por_ciclo
                ):
                    break
                continue
            if self._final_incompleto_confirmado(item["id"]):
                # O placar final ja foi confirmado repetidamente, mas nao
                # contem a sequencia necessaria para certos mercados (por
                # exemplo, proximo gol quando ambos os lados marcaram). A
                # politica de sem_dado encerrara a pendencia apos 24 horas;
                # novas navegacoes nao acrescentariam evidencia.
                suprimidas_final_incompleto += 1
                continue
            url = item["packball_url"]
            if not url or url in urls_ao_vivo:
                continue
            if self.banco.consulta_finalizacao_recente(
                item["id"], "packball", minutos=10, agora=agora
            ):
                continue
            if len(candidatos) >= limite_navegacoes:
                continue
            candidatos.append(item)
            if (
                len(regulamentares) + len(candidatos)
                >= self.limite_por_ciclo
            ):
                break

        encerradas = 0
        resolvidos = resolvidos_intervalos_persistidos
        erros = 0
        snapshots_recuperados = 0
        consultadas = 0
        interrompido_manutencao = False
        for partida, snapshot_regulamentar in regulamentares:
            if callable(interromper_fn) and interromper_fn():
                interrompido_manutencao = True
                break
            resolvidos += self._finalizar_snapshot_regulamentar(
                partida, snapshot_regulamentar
            )
            encerradas += 1
        for partida in ([] if interrompido_manutencao else candidatos):
            if callable(interromper_fn) and interromper_fn():
                interrompido_manutencao = True
                break
            url = partida["packball_url"]
            consultadas += 1
            try:
                estado = self.coletor.coletar_estado_partida(
                    pagina, {"url": url}
                )
            except Exception as erro:
                if isinstance(erro, PackBallBloqueadoError):
                    raise
                self.banco.registrar_consulta_finalizacao(
                    partida["id"], "packball", "erro", erro=str(erro)
                )
                erros += 1
                continue
            snapshot_regulamentar = _snapshot_fim_tempo_regulamentar(
                self.banco, partida["id"]
            )
            if not estado.get("finalizado") and snapshot_regulamentar is None:
                status_observado = (
                    estado.get("status_minuto")
                    or estado.get("texto_status")
                    or estado.get("classes_status")
                )
                self.banco.registrar_consulta_finalizacao(
                    partida["id"],
                    "packball",
                    "em_andamento",
                    status_observado=status_observado,
                    placar_observado=estado.get("placar"),
                )
                if estado.get("placar"):
                    registro = {
                        "coletado_em": datetime.now().replace(microsecond=0),
                        "url": url,
                        "mandante": partida["mandante"],
                        "visitante": partida["visitante"],
                        "placar": estado["placar"],
                        "status": status_observado or "Em andamento",
                        "estatisticas": estado.get("estatisticas") or {},
                        "qualidade": {
                            "pontuacao": 80,
                            "fontes": ["packball"],
                            "versao": "recuperacao-packball-v1",
                        },
                    }
                    snapshot_id = self.banco.salvar_registro(registro)
                    if snapshot_id:
                        snapshots_recuperados += 1
                        resolvidos += self.avaliador.avaliar_snapshot(
                            snapshot_id
                        )
                continue
            placar_resultado = (
                snapshot_regulamentar["placar"]
                if snapshot_regulamentar is not None
                else estado.get("placar")
            )
            if not placar_resultado:
                self.banco.registrar_consulta_finalizacao(
                    partida["id"],
                    "packball",
                    "finalizado_dados_incompletos",
                    status_observado=estado.get("texto_status")
                    or estado.get("classes_status"),
                )
                continue
            if snapshot_regulamentar is not None:
                try:
                    estatisticas_resultado = json.loads(
                        snapshot_regulamentar["estatisticas_json"] or "{}"
                    )
                except (TypeError, json.JSONDecodeError):
                    estatisticas_resultado = {}
            else:
                estatisticas_resultado = estado.get("estatisticas") or {}
                eventos_gols = estado.get("eventos_gols") or []
                if eventos_gols:
                    estatisticas_resultado = dict(estatisticas_resultado)
                    estatisticas_resultado["_eventos_gols_packball"] = (
                        eventos_gols
                    )
                resolvidos += self._resolver_gol_ht_por_texto(
                    partida,
                    estado.get("texto_status")
                    or estado.get("classes_status"),
                    instante=datetime.now().replace(microsecond=0)
                    - timedelta(seconds=1),
                )
                resolvidos += self._resolver_gol_ht_por_timeline(
                    partida,
                    eventos_gols,
                    placar_resultado,
                    instante=datetime.now().replace(microsecond=0)
                    - timedelta(seconds=1),
                )
            registro = {
                "coletado_em": datetime.now().replace(microsecond=0),
                "url": url,
                "mandante": partida["mandante"],
                "visitante": partida["visitante"],
                "placar": placar_resultado,
                "status": (
                    "Finalizado (90min)"
                    if snapshot_regulamentar is not None
                    else "Finalizado"
                ),
                "estatisticas": estatisticas_resultado,
                "qualidade": {
                    "pontuacao": 90,
                    "fontes": ["packball"],
                    "versao": (
                        "resultado-packball-regulamentar-v1"
                        if snapshot_regulamentar is not None
                        else "resultado-packball-v1"
                    ),
                },
            }
            snapshot_id = self.banco.salvar_registro(registro)
            if snapshot_id:
                resolvidos += self.avaliador.avaliar_snapshot(snapshot_id)
                self.banco.registrar_consulta_finalizacao(
                    partida["id"],
                    "packball",
                    (
                        "finalizado"
                        if self._pendentes_restantes(partida["id"]) == 0
                        else "finalizado_dados_incompletos"
                    ),
                    status_observado=(
                        "tempo_regulamentar"
                        if snapshot_regulamentar is not None
                        else estado.get("texto_status")
                        or estado.get("classes_status")
                    ),
                    placar_observado=placar_resultado,
                )
                encerradas += 1
        return {
            "consultadas": consultadas,
            "encerradas": encerradas,
            "resolvidos": resolvidos,
            "erros": erros,
            "snapshots_recuperados": snapshots_recuperados,
            "regulamentares_recuperadas": len(regulamentares),
            "limite_navegacoes": limite_navegacoes,
            "interrompido_manutencao": interrompido_manutencao,
            "suprimidas_final_incompleto": suprimidas_final_incompleto,
            "intervalos_persistidos_recuperados": (
                resolvidos_intervalos_persistidos
            ),
        }


class FinalizadorPendenciasSemDado:
    def __init__(
        self, banco, idade_horas=24, tentativas_minimas=3,
        idade_fallback_horas=72, tentativas_fallback=6,
    ):
        self.banco = banco
        self.idade_horas = float(idade_horas)
        self.tentativas_minimas = int(tentativas_minimas)
        self.idade_fallback_horas = float(idade_fallback_horas)
        self.tentativas_fallback = int(tentativas_fallback)

    @staticmethod
    def _carregar_objeto_json(valor):
        try:
            objeto = json.loads(valor or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return objeto if isinstance(objeto, dict) else {}

    def _evidencia_ht_timeline(self, item):
        minuto_entrada = extrair_minuto(item["status_entrada"])
        if minuto_entrada is None or minuto_entrada > 45:
            return None
        if item["linha"] is None or item["odd"] is None:
            return None
        snapshots = self.banco.conexao.execute(
            """
            SELECT id, coletado_em, placar, status, estatisticas_json,
                   qualidade_json
            FROM snapshots
            WHERE partida_id=? AND id>?
            ORDER BY id
            """,
            (item["partida_id"], item["snapshot_id"]),
        ).fetchall()
        for snapshot in snapshots:
            status = _normalizar_status(snapshot["status"])
            if not any(
                marcador in status
                for marcador in (
                    "finalizado", "encerrado", "finished", "full time"
                )
            ):
                continue
            estatisticas = self._carregar_objeto_json(
                snapshot["estatisticas_json"]
            )
            placar_ht = _placar_intervalo_por_timeline_packball(
                estatisticas.get("_eventos_gols_packball") or [],
                snapshot["placar"],
            )
            par_ht = _placar_par(placar_ht)
            if par_ht is None:
                continue
            resultado, retorno = liquidar_over_asiatico(
                sum(par_ht), float(item["linha"]), float(item["odd"])
            )
            return {
                "resultado": resultado,
                "retorno": retorno,
                "snapshot_id": int(snapshot["id"]),
                "encerrado_em": snapshot["coletado_em"],
                "fonte": "packball",
                "motivo": (
                    "timeline PackBall completa e coerente com o placar "
                    f"final; placar HT reconstruído={placar_ht}"
                ),
            }
        return None

    def _evidencia_escanteios_ft_irreversivel(self, item):
        if item["linha"] is None or item["odd"] is None:
            return None
        snapshots = self.banco.conexao.execute(
            """
            SELECT id, coletado_em, status, estatisticas_json,
                   confirmacao_api_json, qualidade_json
            FROM snapshots
            WHERE partida_id=? AND id>=?
            ORDER BY id
            """,
            (item["partida_id"], item["snapshot_id"]),
        ).fetchall()
        leituras = []
        confirmacoes_finais_api = []
        for snapshot in snapshots:
            confirmacao_api = self._carregar_objeto_json(
                snapshot["confirmacao_api_json"]
            )
            status_api = confirmacao_api.get("status") or {}
            codigo_api = (
                str(status_api.get("short") or "").upper()
                if isinstance(status_api, dict) else ""
            )
            if codigo_api in {"FT", "AET", "PEN"}:
                confirmacoes_finais_api.append(snapshot)
            estatisticas = self._carregar_objeto_json(
                snapshot["estatisticas_json"]
            )
            par = extrair_par(estatisticas.get("Escanteios"))
            if par is None:
                continue
            qualidade = self._carregar_objeto_json(
                snapshot["qualidade_json"]
            )
            fontes = qualidade.get("fontes") or []
            if "packball" not in fontes:
                continue
            total = int(sum(par))
            resultado, retorno = liquidar_over_asiatico(
                total, float(item["linha"]), float(item["odd"])
            )
            leituras.append({
                "snapshot": snapshot,
                "total": total,
                "resultado": resultado,
                "retorno": retorno,
                "apta": qualidade.get("apto_para_liquidacao") is True,
                "fontes": set(qualidade.get("fontes") or []),
                "status": _normalizar_status(snapshot["status"]),
                "minuto": extrair_minuto(snapshot["status"]),
            })

        # Exige uma leitura apta e uma confirmação PackBall posterior de que
        # o tempo regulamentar realmente terminou. Assim, um contador
        # transitório ou uma partida abandonada não corrige o histórico.
        for indice, leitura in enumerate(leituras):
            if not leitura["apta"] or leitura["resultado"] != "green":
                continue
            fechamento = next((
                posterior
                for posterior in leituras[indice + 1:]
                if posterior["total"] >= leitura["total"]
                and (
                    posterior["status"] in {"pen", "aet"}
                    or any(
                        marcador in posterior["status"]
                        for marcador in (
                            "finalizado", "encerrado", "finished",
                            "full time",
                        )
                    )
                )
            ), None)
            if fechamento is None:
                continue
            snapshot_atingimento = leitura["snapshot"]
            snapshot_fechamento = fechamento["snapshot"]
            return {
                "resultado": "green",
                "retorno": leitura["retorno"],
                "snapshot_id": int(snapshot_fechamento["id"]),
                "encerrado_em": snapshot_fechamento["coletado_em"],
                "fonte": "packball",
                "motivo": (
                    "linha de escanteios FT matematicamente atingida e "
                    "confirmada no encerramento PackBall; "
                    f"total={leitura['total']}; "
                    f"snapshot_atingimento={snapshot_atingimento['id']}"
                ),
            }

        # Há partidas que pulam do minuto 80-84 diretamente para PEN/AET no
        # PackBall. Nelas não se pode usar o contador terminal para inferir um
        # canto ocorrido na prorrogação. Ainda assim, uma liquidação é
        # determinística quando o contador terminal permanece exatamente igual
        # ao de uma leitura tardia, apta e multifonte do tempo regulamentar.
        # Exigimos três leituras terminais PackBall ao longo de dez minutos e
        # duas confirmações finais independentes da API-Football. Qualquer
        # alteração do total mantém o sem_dado, mesmo que favoreça o sinal.
        tardias_confiaveis = [
            leitura for leitura in leituras
            if leitura["apta"]
            and {"packball", "api_football"}.issubset(leitura["fontes"])
            and leitura["minuto"] is not None
            and 80 <= leitura["minuto"] <= 99
            and leitura["status"] not in {"pen", "aet"}
            and not any(
                marcador in leitura["status"]
                for marcador in (
                    "finalizado", "encerrado", "finished", "full time",
                )
            )
        ]
        if not tardias_confiaveis:
            return None
        referencia = tardias_confiaveis[-1]
        terminais_packball = [
            leitura for leitura in leituras
            if leitura["snapshot"]["id"] > referencia["snapshot"]["id"]
            and (
                leitura["status"] in {"pen", "aet"}
                or any(
                    marcador in leitura["status"]
                    for marcador in (
                        "finalizado", "encerrado", "finished", "full time",
                    )
                )
            )
        ]
        if len(terminais_packball) < 3:
            return None
        if any(
            leitura["total"] != referencia["total"]
            for leitura in terminais_packball
        ):
            return None
        try:
            duracao_confirmacao = (
                datetime.fromisoformat(
                    terminais_packball[-1]["snapshot"]["coletado_em"]
                )
                - datetime.fromisoformat(
                    terminais_packball[0]["snapshot"]["coletado_em"]
                )
            ).total_seconds()
        except (TypeError, ValueError):
            return None
        if duracao_confirmacao < 600:
            return None
        api_posteriores = [
            snapshot for snapshot in confirmacoes_finais_api
            if snapshot["id"] > terminais_packball[0]["snapshot"]["id"]
        ]
        if len(api_posteriores) < 2:
            return None
        fechamento = terminais_packball[-1]["snapshot"]
        return {
            "resultado": referencia["resultado"],
            "retorno": referencia["retorno"],
            "snapshot_id": int(fechamento["id"]),
            "encerrado_em": fechamento["coletado_em"],
            "fonte": "packball",
            "motivo": (
                "total de escanteios permaneceu invariável desde leitura "
                "PackBall apta e multifonte no fim do tempo regulamentar, "
                "com encerramento repetido no PackBall e na API-Football; "
                f"minuto={referencia['minuto']}; "
                f"total={referencia['total']}; "
                f"confirmacoes_packball={len(terminais_packball)}; "
                f"confirmacoes_api={len(api_posteriores)}"
            ),
        }
        return None

    def _evidencia_conclusiva(self, item):
        if item["mercado"] == "gol_ht":
            return self._evidencia_ht_timeline(item)
        if item["mercado"] == "escanteios_ft_asiatico":
            return self._evidencia_escanteios_ft_irreversivel(item)
        return None

    def _aplicar_revisao(self, item, evidencia, agora):
        motivo_revisao = (
            "sem_dado revisado após recuperação determinística: "
            + evidencia["motivo"]
        )
        observacao = "resultado recuperado: " + evidencia["motivo"]
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT OR IGNORE INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior,
                    observacao_anterior, snapshot_id_liquidacao_anterior,
                    fonte_resultado_anterior, motivo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["sinal_id"], agora.isoformat(),
                    item["encerrado_em_anterior"],
                    item["resultado_anterior"], item["retorno_anterior"],
                    item["observacao_anterior"],
                    item["snapshot_id_liquidacao_anterior"],
                    item["fonte_resultado_anterior"], motivo_revisao,
                ),
            )
            removido = self.banco.conexao.execute(
                "DELETE FROM resultados_sinais WHERE sinal_id=?",
                (item["sinal_id"],),
            )
            if removido.rowcount != 1:
                raise RuntimeError("resultado_sem_dado_nao_removido")
            inserido = self.banco.conexao.execute(
                """
                INSERT INTO resultados_sinais (
                    sinal_id, encerrado_em, resultado, retorno_unidades,
                    observacao, snapshot_id_liquidacao, fonte_resultado
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["sinal_id"], evidencia["encerrado_em"],
                    evidencia["resultado"], evidencia["retorno"],
                    observacao, evidencia["snapshot_id"],
                    evidencia["fonte"],
                ),
            )
            if inserido.rowcount != 1:
                raise RuntimeError("resultado_recuperado_nao_inserido")
            self.banco.conexao.execute(
                """
                UPDATE entregas_alertas
                SET status='corrigido', erro=?
                WHERE sinal_id=? AND status='entregue'
                  AND canal LIKE '%:resultado'
                """,
                (motivo_revisao, item["sinal_id"]),
            )

    def recuperar_conclusivos(self, agora=None):
        """Revisa ``sem_dado`` só quando a evidência salva fecha a conta."""
        agora = (agora or datetime.now()).replace(microsecond=0)
        itens = self.banco.conexao.execute(
            """
            SELECT s.id AS sinal_id, s.partida_id, s.snapshot_id,
                   s.mercado, s.linha, s.odd,
                   entrada.status AS status_entrada,
                   r.encerrado_em AS encerrado_em_anterior,
                   r.resultado AS resultado_anterior,
                   r.retorno_unidades AS retorno_anterior,
                   r.observacao AS observacao_anterior,
                   r.snapshot_id_liquidacao
                       AS snapshot_id_liquidacao_anterior,
                   r.fonte_resultado AS fonte_resultado_anterior
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            JOIN snapshots entrada ON entrada.id=s.snapshot_id
            WHERE r.resultado='sem_dado'
              AND s.status IN ('aprovado', 'simulacao', 'auditoria')
            ORDER BY s.id
            """
        ).fetchall()
        recuperados = []
        for item in itens:
            evidencia = self._evidencia_conclusiva(item)
            if evidencia is None:
                continue
            self._aplicar_revisao(item, evidencia, agora)
            recuperados.append({
                "sinal_id": int(item["sinal_id"]),
                "mercado": item["mercado"],
                "resultado": evidencia["resultado"],
                "snapshot_id": evidencia["snapshot_id"],
            })
        return {
            "avaliados": len(itens),
            "recuperados": len(recuperados),
            "resultados": recuperados,
        }

    def executar(self, agora=None):
        agora = (agora or datetime.now()).replace(microsecond=0)
        recuperacao = self.recuperar_conclusivos(agora)
        limite = (agora - timedelta(hours=self.idade_horas)).isoformat()
        limite_fallback = (
            agora - timedelta(hours=self.idade_fallback_horas)
        ).isoformat()
        candidatos = self.banco.conexao.execute(
            """
            WITH tentativas AS (
                SELECT partida_id,
                       MIN(consultado_em) AS primeira_tentativa,
                       MIN(CASE WHEN estado='finalizado_dados_incompletos'
                                THEN consultado_em END) AS primeira_confirmacao,
                       COUNT(id) AS quantidade,
                       GROUP_CONCAT(DISTINCT fonte) AS fontes
                FROM consultas_finalizacao
                GROUP BY partida_id
            )
            SELECT s.id AS sinal_id, s.partida_id, s.mercado,
                   p.api_fixture_id, t.primeira_confirmacao,
                   t.primeira_tentativa, t.quantidade, t.fontes,
                   CASE WHEN t.primeira_confirmacao IS NOT NULL
                              AND datetime(t.primeira_confirmacao)
                                  <= datetime(?)
                              AND t.quantidade >= ?
                        THEN 'final_incompleto'
                        ELSE 'fontes_indisponiveis' END AS modo
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            JOIN tentativas t ON t.partida_id=s.partida_id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status IN ('aprovado', 'simulacao', 'auditoria')
              AND r.sinal_id IS NULL
              AND (
                  (t.primeira_confirmacao IS NOT NULL
                   AND datetime(t.primeira_confirmacao) <= datetime(?)
                   AND t.quantidade >= ?)
                  OR
                  (datetime(t.primeira_tentativa) <= datetime(?)
                   AND t.quantidade >= ?)
              )
            ORDER BY COALESCE(
                t.primeira_confirmacao, t.primeira_tentativa
            ), s.id
            """,
            (
                limite, self.tentativas_minimas,
                limite, self.tentativas_minimas,
                limite_fallback, self.tentativas_fallback,
            ),
        ).fetchall()

        encerrados = 0
        encerrados_fallback = 0
        with self.banco.conexao:
            for item in candidatos:
                fontes_observadas = set(
                    filtro for filtro in (item["fontes"] or "").split(",")
                    if filtro
                )
                fontes_esperadas = {"packball"}
                if item["api_fixture_id"] is not None:
                    fontes_esperadas.add("api_football")
                if not fontes_esperadas.issubset(fontes_observadas):
                    continue
                cursor = self.banco.conexao.execute(
                    """
                    INSERT OR IGNORE INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, observacao,
                        snapshot_id_liquidacao, fonte_resultado
                    ) VALUES (?, ?, 'sem_dado', NULL, ?, NULL, 'sem_dado')
                    """,
                    (
                        item["sinal_id"],
                        agora.isoformat(),
                        (
                            "resultado não avaliável após "
                            f"{item['quantidade']} tentativas em "
                            f"modo={item['modo']}; fontes="
                            + ",".join(sorted(fontes_observadas))
                        ),
                    ),
                )
                encerrados += cursor.rowcount
                if item["modo"] == "fontes_indisponiveis":
                    encerrados_fallback += cursor.rowcount
        return {
            "candidatos": len(candidatos),
            "encerrados_sem_dado": encerrados,
            "recuperados_sem_dado": recuperacao["recuperados"],
            "resultados_recuperados": recuperacao["resultados"],
            "idade_horas": self.idade_horas,
            "tentativas_minimas": self.tentativas_minimas,
            "encerrados_fallback": encerrados_fallback,
            "idade_fallback_horas": self.idade_fallback_horas,
            "tentativas_fallback": self.tentativas_fallback,
        }
