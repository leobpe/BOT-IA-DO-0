import json
import math
import re
from collections import Counter
from datetime import datetime

from configuracao import obter_limites_risco
from evolucao import extrair_par
from estatistica import (
    discriminacao_pontuacao,
    estado_amostra,
    intervalo_wilson,
)
from mercados import MERCADOS_PRIMEIRO_TEMPO
from qualidade_dados import extrair_minuto


STATUS_FINAIS = (
    "finalizado",
    "encerrado",
    "finished",
    "full time",
    "ft",
)
STATUS_ANULADOS = (
    "anulado",
    "cancelado",
    "abandonado",
    "walkover",
    "wo",
)


def _placar_total(valor):
    numeros = re.findall(r"\d+", str(valor or ""))
    if len(numeros) < 2:
        return None
    return int(numeros[0]) + int(numeros[1])


def _encerrado(status):
    texto = str(status or "").strip().lower()
    return any(
        texto == item or item in texto
        for item in STATUS_FINAIS
    )


def _anulado(status):
    texto = str(status or "").strip().lower()
    return any(texto == item or item in texto for item in STATUS_ANULADOS)


class AvaliadorBacktest:
    def __init__(self, banco):
        self.banco = banco
        self.limites_risco = obter_limites_risco()

    @staticmethod
    def _placar_confirmado_api(confirmacao_api):
        placar = (confirmacao_api or {}).get("placar")
        if not isinstance(placar, (list, tuple)) or len(placar) < 2:
            return None
        try:
            return [int(placar[0]), int(placar[1])]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fonte_que_comprovou_resultado(
        sinal,
        atual,
        fontes,
        confirmacao_api,
        eventos_atuais,
        lado_historico,
    ):
        """Escolhe a fonte pela evidência usada, não pela mera presença."""
        fontes = set(fontes or [])
        mercado = sinal["mercado"]
        if "escanteio" in mercado and "packball" in fontes:
            return "packball"

        if mercado in ("gol_ft", "gol_ht", "proximo_gol"):
            placar_snapshot = _placar_par(atual["placar"])
            placar_api = AvaliadorBacktest._placar_confirmado_api(
                confirmacao_api
            )
            api_concorda = (
                "api_football" in fontes
                and placar_snapshot is not None
                and placar_api == placar_snapshot
            )
            if api_concorda and mercado == "proximo_gol":
                inicial = _placar_par(sinal["placar_inicial"])
                if inicial is not None:
                    deltas = [
                        placar_snapshot[indice] - inicial[indice]
                        for indice in range(2)
                    ]
                    if all(delta > 0 for delta in deltas):
                        lado_api = _lado_proximo_gol_por_eventos(
                            eventos_atuais or [],
                            confirmacao_api or {},
                            inicial,
                            placar_snapshot,
                        )
                        if lado_api is not None:
                            return "api_football"
                        if lado_historico is not None and "packball" in fontes:
                            return "packball"
            if api_concorda:
                return "api_football"
            if "packball" in fontes:
                return "packball"

        if "api_football" in fontes:
            return "api_football"
        if "packball" in fontes:
            return "packball"
        return next(iter(fontes), "desconhecida")

    def avaliar_snapshot(self, snapshot_id):
        atual = self.banco.conexao.execute(
            """
            SELECT id, partida_id, coletado_em, placar, status,
                   estatisticas_json, confirmacao_api_json, fontes_json,
                   qualidade_json
            FROM snapshots WHERE id=?
            """,
            (snapshot_id,),
        ).fetchone()
        if atual is None:
            raise ValueError("Snapshot não encontrado para avaliação.")

        try:
            qualidade = json.loads(atual["qualidade_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            qualidade = {}
        if not isinstance(qualidade, dict):
            qualidade = {}
        # Uma leitura parcial pode ser preservada para diagnostico, mas nao
        # pode liquidar um sinal nem alterar o placar de Green/Red.
        if qualidade.get("apto_para_liquidacao") is False:
            return 0

        sinais = self.banco.conexao.execute(
            """
            SELECT s.*, inicial.placar AS placar_inicial,
                   inicial.estatisticas_json AS estatisticas_iniciais
            FROM sinais s
            JOIN snapshots inicial ON inicial.id=s.snapshot_id
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.partida_id=?
              AND s.status IN ('aprovado', 'simulacao', 'auditoria')
              AND s.snapshot_id < ? AND r.sinal_id IS NULL
            ORDER BY s.id
            """,
            (atual["partida_id"], snapshot_id),
        ).fetchall()

        estatisticas_atuais = json.loads(atual["estatisticas_json"] or "{}")
        confirmacao_api = json.loads(
            atual["confirmacao_api_json"] or "null"
        ) or {}
        eventos_atuais = [
            json.loads(item["payload_json"] or "{}")
            for item in self.banco.conexao.execute(
                """
                SELECT payload_json FROM eventos
                WHERE snapshot_id=? ORDER BY id
                """,
                (snapshot_id,),
            ).fetchall()
        ]
        anulado = _anulado(atual["status"])
        encerrado = _encerrado(atual["status"]) or anulado
        try:
            fontes = json.loads(atual["fontes_json"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            fontes = []
        if not isinstance(fontes, list):
            fontes = []
        fontes = [item for item in fontes if isinstance(item, str) and item]
        resolvidos = 0
        with self.banco.conexao:
            for sinal in sinais:
                lado_historico = (
                    self._lado_proximo_gol_por_historico(sinal, atual)
                    if sinal["mercado"] == "proximo_gol"
                    else None
                )
                if anulado:
                    resultado, retorno = "void", 0.0
                else:
                    resultado, retorno = self._liquidar(
                        sinal,
                        atual,
                        estatisticas_atuais,
                        eventos_atuais,
                        confirmacao_api,
                        lado_historico=lado_historico,
                    )
                encerrado_sinal = encerrado or (
                    sinal["mercado"] in MERCADOS_PRIMEIRO_TEMPO
                    and _intervalo(atual["status"])
                )
                if resultado is None:
                    # Ausência do dado necessário não comprova devolução.
                    # O sinal permanece pendente para outra fonte confiável.
                    continue
                exige_fechamento_periodo = sinal["mercado"] in (
                    "gol_ft", "gol_ht", "proximo_gol",
                    "proximo_escanteio", "escanteios_ft_asiatico",
                    "escanteios_1t",
                    "escanteios_2t",
                )
                if exige_fechamento_periodo and not encerrado_sinal:
                    continue
                fonte_resultado = self._fonte_que_comprovou_resultado(
                    sinal,
                    atual,
                    fontes,
                    confirmacao_api,
                    eventos_atuais,
                    lado_historico,
                )
                self.banco.conexao.execute(
                    """
                    INSERT OR IGNORE INTO resultados_sinais (
                        sinal_id, encerrado_em, resultado,
                        retorno_unidades, observacao,
                        snapshot_id_liquidacao, fonte_resultado
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sinal["id"],
                        atual["coletado_em"],
                        resultado,
                        retorno,
                        "resolvido automaticamente por snapshot posterior",
                        atual["id"],
                        fonte_resultado,
                    ),
                )
                resolvidos += 1
        return resolvidos

    def reavaliar_snapshots_conclusivos_pendentes(self):
        """Recupera liquidações perdidas usando evidência já persistida.

        Só reprocessa intervalos e encerramentos reais. Leituras comuns em
        andamento não são reinterpretadas, evitando inferências retroativas.
        """
        snapshots = self.banco.conexao.execute(
            """
            SELECT DISTINCT sp.id, sp.status
            FROM snapshots sp
            WHERE EXISTS (
                SELECT 1
                FROM sinais s
                LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
                WHERE s.partida_id=sp.partida_id
                  AND s.status IN ('aprovado', 'simulacao', 'auditoria')
                  AND r.sinal_id IS NULL
                  AND s.snapshot_id < sp.id
            )
            ORDER BY sp.id
            """
        ).fetchall()
        resolvidos = 0
        for snapshot in snapshots:
            status = snapshot["status"]
            if not (
                _intervalo(status) or _encerrado(status) or _anulado(status)
            ):
                continue
            resolvidos += self.avaliar_snapshot(int(snapshot["id"]))
        return resolvidos

    def confirmar_green_irreversivel(self, sinal_id):
        """Confirma um GREEN que já não depende do encerramento do período.

        A confirmação é apenas operacional, para editar cedo a mensagem no
        Telegram. Ela não grava ``resultados_sinais`` e, portanto, não muda a
        calibração nem antecipa a liquidação oficial.
        """
        linha = self.banco.conexao.execute(
            """
            SELECT s.id, s.partida_id, s.snapshot_id, s.mercado, s.linha,
                   s.odd, s.status AS status_sinal,
                   inicial.placar AS placar_inicial,
                   inicial.estatisticas_json AS estatisticas_iniciais,
                   atual.id AS snapshot_atual_id,
                   atual.coletado_em AS coletado_em_atual,
                   atual.placar AS placar_atual,
                   atual.status AS status_atual,
                   atual.estatisticas_json AS estatisticas_atuais,
                   atual.confirmacao_api_json AS confirmacao_api_atual,
                   atual.fontes_json AS fontes_atuais,
                   atual.qualidade_json AS qualidade_atual
            FROM sinais s
            JOIN snapshots inicial ON inicial.id=s.snapshot_id
            JOIN snapshots atual ON atual.id=(
                SELECT MAX(sp.id)
                FROM snapshots sp
                WHERE sp.partida_id=s.partida_id AND sp.id>s.snapshot_id
            )
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.id=?
              AND s.status IN ('aprovado', 'simulacao')
              AND r.sinal_id IS NULL
            LIMIT 1
            """,
            (int(sinal_id),),
        ).fetchone()
        if linha is None:
            return None

        try:
            qualidade = json.loads(linha["qualidade_atual"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(qualidade, dict):
            return None
        # Uma leitura parcial ou antiga jamais pode mudar a mensagem pública.
        if qualidade.get("apto_para_liquidacao") is not True:
            return None

        atual = {
            "id": linha["snapshot_atual_id"],
            "placar": linha["placar_atual"],
            "status": linha["status_atual"],
        }
        sinal = {
            "id": linha["id"],
            "partida_id": linha["partida_id"],
            "snapshot_id": linha["snapshot_id"],
            "mercado": linha["mercado"],
            "linha": linha["linha"],
            "odd": linha["odd"],
            "placar_inicial": linha["placar_inicial"],
            "estatisticas_iniciais": linha["estatisticas_iniciais"],
        }
        try:
            estatisticas = json.loads(linha["estatisticas_atuais"] or "{}")
            confirmacao_api = json.loads(
                linha["confirmacao_api_atual"] or "null"
            ) or {}
            fontes = json.loads(linha["fontes_atuais"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(estatisticas, dict):
            return None
        if not isinstance(confirmacao_api, dict):
            confirmacao_api = {}
        if not isinstance(fontes, list):
            fontes = []
        eventos = [
            json.loads(item["payload_json"] or "{}")
            for item in self.banco.conexao.execute(
                """
                SELECT payload_json FROM eventos
                WHERE snapshot_id=? ORDER BY id
                """,
                (linha["snapshot_atual_id"],),
            ).fetchall()
        ]

        mercado = sinal["mercado"]
        odd = float(sinal["odd"] or 1.0)
        resultado = None
        lado_historico = None
        if mercado == "proximo_gol":
            lado_historico = self._lado_proximo_gol_por_historico(
                sinal, atual
            )
            resultado, _ = self._liquidar(
                sinal,
                atual,
                estatisticas,
                eventos,
                confirmacao_api,
                lado_historico=lado_historico,
            )
        else:
            if mercado in ("gol_ft", "gol_ht"):
                if (
                    mercado == "gol_ht"
                    and not _instante_valido_gol_ht(atual["status"])
                ):
                    return None
                total_atual = _placar_total(atual["placar"])
                total_inicial = _placar_total(sinal["placar_inicial"])
            elif mercado in (
                "proximo_escanteio",
                "escanteios_ft_asiatico",
                "escanteios_1t",
                "escanteios_2t",
            ):
                if (
                    mercado == "escanteios_1t"
                    and not _instante_valido_gol_ht(atual["status"])
                ):
                    return None
                total_partida = _total_par(
                    extrair_par(estatisticas.get("Escanteios"))
                )
                if mercado == "escanteios_2t":
                    total_intervalo = self._total_escanteios_intervalo(sinal)
                    if (
                        total_partida is None
                        or total_intervalo is None
                        or total_partida < total_intervalo
                    ):
                        return None
                    total_atual = total_partida - total_intervalo
                    total_inicial = 0
                else:
                    total_atual = total_partida
                    try:
                        iniciais = json.loads(
                            sinal["estatisticas_iniciais"] or "{}"
                        )
                    except (TypeError, ValueError, json.JSONDecodeError):
                        iniciais = {}
                    total_inicial = _total_par(
                        extrair_par(iniciais.get("Escanteios"))
                    )
            else:
                return None

            if total_atual is None:
                return None
            if sinal["linha"] is not None:
                try:
                    resultado, _ = liquidar_over_asiatico(
                        total_atual, float(sinal["linha"]), odd
                    )
                except (TypeError, ValueError):
                    return None
            elif total_inicial is not None and total_atual > total_inicial:
                resultado = "green"

        # MEIO GREEN e VOID ainda podem exigir a liquidação da linha completa.
        if resultado != "green":
            return None
        fonte = self._fonte_que_comprovou_resultado(
            sinal,
            atual,
            fontes,
            confirmacao_api,
            eventos,
            lado_historico,
        )
        return {
            "sinal_id": int(sinal["id"]),
            "snapshot_id": int(atual["id"]),
            "coletado_em": linha["coletado_em_atual"],
            "placar": atual["placar"],
            "status": atual["status"],
            "fonte": fonte,
        }

    def _total_escanteios_intervalo(self, sinal):
        return self.banco.total_escanteios_intervalo(
            partida_id=sinal["partida_id"],
            antes_snapshot_id=sinal["snapshot_id"],
        )

    def _lado_proximo_gol_por_historico(self, sinal, atual):
        """Reconstrui o primeiro gol apenas com transicoes unitarias seguras."""
        inicial = _placar_par(sinal["placar_inicial"])
        if inicial is None:
            return None
        snapshots = self.banco.conexao.execute(
            """
            SELECT placar FROM snapshots
            WHERE partida_id=? AND id>? AND id<=?
            ORDER BY id
            """,
            (sinal["partida_id"], sinal["snapshot_id"], atual["id"]),
        ).fetchall()
        candidato = None
        for snapshot in snapshots:
            placar = _placar_par(snapshot["placar"])
            if placar is None:
                continue
            deltas = [placar[indice] - inicial[indice] for indice in range(2)]
            if any(delta < 0 for delta in deltas):
                return None
            total = sum(deltas)
            if candidato is not None and deltas[candidato] < 1:
                # O gol observado regrediu: foi anulado ou o placar ficou
                # inconsistente. Recomece somente se voltou ao baseline.
                candidato = None
            if candidato is not None:
                continue
            if total == 0:
                continue
            if total != 1:
                # Dois gols entre coletas nao permitem provar qual veio antes.
                return None
            candidato = 0 if deltas[0] == 1 else 1
        if candidato == 0:
            return "casa"
        if candidato == 1:
            return "visitante"
        return None

    def _liquidar(
        self, sinal,
        atual,
        estatisticas_atuais,
        eventos_atuais=None,
        confirmacao_api=None,
        lado_historico=None,
    ):
        odd = float(sinal["odd"]) if sinal["odd"] is not None else 1.0
        linha = sinal["linha"]
        if sinal["mercado"] == "gol_ht":
            if not _instante_valido_gol_ht(atual["status"]):
                return None, 0.0
            total_atual = _placar_total(atual["placar"])
            total_inicial = _placar_total(sinal["placar_inicial"])
        elif sinal["mercado"] == "gol_ft":
            total_atual = _placar_total(atual["placar"])
            total_inicial = _placar_total(sinal["placar_inicial"])
        elif sinal["mercado"] == "proximo_gol":
            if lado_historico is None:
                lado_historico = self._lado_proximo_gol_por_historico(
                    sinal, atual
                )
            venceu = AvaliadorBacktest._venceu(
                sinal,
                atual,
                estatisticas_atuais,
                eventos_atuais,
                confirmacao_api,
                lado_historico,
            )
            if venceu is None:
                return None, 0.0
            return (
                ("green", round(odd - 1.0, 4))
                if venceu else ("red", -1.0)
            )
        elif sinal["mercado"] in (
            "proximo_escanteio",
            "escanteios_ft_asiatico",
        ):
            total_atual = _total_par(
                extrair_par(estatisticas_atuais.get("Escanteios"))
            )
            estatisticas_iniciais = json.loads(
                sinal["estatisticas_iniciais"] or "{}"
            )
            total_inicial = _total_par(
                extrair_par(estatisticas_iniciais.get("Escanteios"))
            )
        elif sinal["mercado"] == "escanteios_1t":
            if not _intervalo(atual["status"]):
                return None, 0.0
            total_atual = _total_par(
                extrair_par(estatisticas_atuais.get("Escanteios"))
            )
            total_inicial = 0
        elif sinal["mercado"] == "escanteios_2t":
            if not _encerrado(atual["status"]):
                return None, 0.0
            total_final = _total_par(
                extrair_par(estatisticas_atuais.get("Escanteios"))
            )
            total_intervalo = self._total_escanteios_intervalo(sinal)
            if (
                total_final is None
                or total_intervalo is None
                or total_final < total_intervalo
            ):
                return None, 0.0
            total_atual = total_final - total_intervalo
            total_inicial = 0
        else:
            return "red", -1.0

        if total_atual is None:
            return None, 0.0
        if linha is not None:
            try:
                return liquidar_over_asiatico(total_atual, float(linha), odd)
            except (TypeError, ValueError):
                return None, 0.0
        if total_inicial is None:
            return None, 0.0
        if total_atual > total_inicial:
            return "green", round(odd - 1.0, 4)
        return "red", -1.0

    @staticmethod
    def _venceu(
        sinal,
        atual,
        estatisticas_atuais,
        eventos_atuais=None,
        confirmacao_api=None,
        lado_historico=None,
    ):
        linha = sinal["linha"]
        if sinal["mercado"] in ("gol_ft", "gol_ht"):
            total_atual = _placar_total(atual["placar"])
            total_inicial = _placar_total(sinal["placar_inicial"])
        elif sinal["mercado"] == "proximo_gol":
            inicial = _placar_par(sinal["placar_inicial"])
            atual_par = _placar_par(atual["placar"])
            if inicial is None or atual_par is None:
                return None
            deltas = [
                atual_par[indice] - inicial[indice] for indice in range(2)
            ]
            if any(delta < 0 for delta in deltas):
                return None
            if sum(deltas) == 0:
                return False
            lados_com_gol = [
                indice for indice, delta in enumerate(deltas) if delta > 0
            ]
            if len(lados_com_gol) == 1:
                lado = "casa" if lados_com_gol[0] == 0 else "visitante"
            else:
                lado = _lado_proximo_gol_por_eventos(
                    eventos_atuais or [],
                    confirmacao_api or {},
                    inicial,
                    atual_par,
                )
                if lado is None:
                    lado = _lado_proximo_gol_por_timeline_packball(
                        estatisticas_atuais.get(
                            "_eventos_gols_packball"
                        ) or [],
                        inicial,
                        atual_par,
                    )
                if lado is None:
                    lado = lado_historico
                if lado is None:
                    return None
            if linha == "casa":
                return lado == "casa"
            if linha == "visitante":
                return lado == "visitante"
            return True
        elif sinal["mercado"] in (
            "proximo_escanteio",
            "escanteios_ft_asiatico",
        ):
            total_atual = _total_par(
                extrair_par(estatisticas_atuais.get("Escanteios"))
            )
            estatisticas_iniciais = json.loads(
                sinal["estatisticas_iniciais"] or "{}"
            )
            total_inicial = _total_par(
                extrair_par(estatisticas_iniciais.get("Escanteios"))
            )
        else:
            return False

        if total_atual is None:
            return None
        if linha is not None:
            return total_atual > float(linha)
        if total_inicial is None:
            return None
        return total_atual > total_inicial

    def metricas(self, mercado=None, regra_versao=None):
        filtros = [
            "s.status='aprovado'",
            "s.odd BETWEEN ? AND ?",
        ]
        parametros = [
            self.limites_risco.odd_minima,
            self.limites_risco.odd_maxima,
        ]
        if mercado:
            filtros.append("s.mercado=?")
            parametros.append(mercado)
        if regra_versao:
            filtros.append("s.regra_versao=?")
            parametros.append(regra_versao)
        where_base = "WHERE " + " AND ".join(filtros)
        linhas = self.banco.conexao.execute(
            f"""
            WITH candidatos AS (
                SELECT s.id, s.partida_id, s.mercado, s.regra_versao,
                       s.criado_em, s.pontuacao_tecnica,
                       ROW_NUMBER() OVER (
                           PARTITION BY s.partida_id, s.mercado,
                                        s.regra_versao
                           ORDER BY s.criado_em, s.id
                       ) AS ordem
                FROM sinais s
                {where_base}
            )
            SELECT r.resultado, r.retorno_unidades, r.encerrado_em,
                   c.pontuacao_tecnica
            FROM candidatos c
            JOIN resultados_sinais r ON r.sinal_id=c.id
            WHERE c.ordem=1
              AND r.resultado IN (
                  'green','half_green','red','half_red','void'
              )
            ORDER BY datetime(r.encerrado_em), c.id
            """,
            parametros,
        ).fetchall()
        metricas = calcular_metricas(linhas)
        nao_avaliaveis = self.banco.conexao.execute(
            f"""
            WITH candidatos AS (
                SELECT s.id,
                       ROW_NUMBER() OVER (
                           PARTITION BY s.partida_id, s.mercado,
                                        s.regra_versao
                           ORDER BY s.criado_em, s.id
                       ) AS ordem
                FROM sinais s
                {where_base}
            )
            SELECT COUNT(CASE WHEN r.resultado='sem_dado' THEN 1 END)
                   AS sem_dado
            FROM candidatos c
            JOIN resultados_sinais r ON r.sinal_id=c.id
            WHERE c.ordem=1
            """,
            parametros,
        ).fetchone()
        metricas["observacoes_void"] = metricas["voids"]
        metricas["observacoes_sem_dado"] = int(
            nao_avaliaveis["sem_dado"] or 0
        )
        return metricas


def _total_par(par):
    return sum(par) if par is not None else None


def reabrir_resultados_provisorios(banco):
    """Retira liquidações esportivas feitas antes do fechamento do período.

    ``sem_dado`` é encerramento por esgotamento das fontes, não liquidação
    esportiva provisória, e portanto nunca deve ser reaberto aqui.
    """
    linhas = banco.conexao.execute(
        """
        SELECT r.sinal_id, r.encerrado_em, r.resultado,
               r.retorno_unidades, r.observacao,
               r.snapshot_id_liquidacao, r.fonte_resultado,
               s.mercado, sn.status AS status_liquidacao
        FROM resultados_sinais r
        JOIN sinais s ON s.id=r.sinal_id
        LEFT JOIN snapshots sn
          ON sn.partida_id=s.partida_id
         AND sn.coletado_em=r.encerrado_em
        WHERE s.mercado IN (
            'gol_ft', 'gol_ht', 'proximo_gol', 'proximo_escanteio',
            'escanteios_ft_asiatico',
            'escanteios_1t', 'escanteios_2t'
        )
          AND s.status IN ('aprovado', 'simulacao', 'auditoria')
          AND COALESCE(r.fonte_resultado, '')
              NOT LIKE 'invalidacao_operacional_%'
          AND r.resultado IN (
              'green', 'half_green', 'red', 'half_red', 'void'
          )
        ORDER BY r.sinal_id
        """
    ).fetchall()
    reabertos = []
    revisado_em = datetime.now().replace(microsecond=0).isoformat()
    with banco.conexao:
        for linha in linhas:
            status = linha["status_liquidacao"]
            encerramento_valido = _encerrado(status) or _anulado(status)
            if linha["mercado"] in MERCADOS_PRIMEIRO_TEMPO:
                encerramento_valido = encerramento_valido or _intervalo(status)
            status_normalizado = str(status or "").strip().lower()
            observacao = str(linha["observacao"] or "")
            green_irreversivel_confirmado_no_fim = bool(
                linha["resultado"] == "green"
                and linha["mercado"] in (
                    "gol_ft", "escanteios_ft_asiatico"
                )
                and linha["fonte_resultado"] == "packball"
                and status_normalizado in {"pen", "aet"}
                and observacao.startswith("resultado recuperado: linha de ")
                and "matematicamente atingida" in observacao
            )
            escanteios_estaveis_confirmados_no_fim = bool(
                linha["mercado"] == "escanteios_ft_asiatico"
                and linha["fonte_resultado"] == "packball"
                and status_normalizado in {"pen", "aet"}
                and observacao.startswith(
                    "resultado recuperado: total de escanteios permaneceu "
                    "invariável desde leitura PackBall apta e multifonte "
                    "no fim do tempo regulamentar"
                )
                and "encerramento repetido no PackBall e na API-Football"
                    in observacao
            )
            encerramento_valido = (
                encerramento_valido
                or green_irreversivel_confirmado_no_fim
                or escanteios_estaveis_confirmados_no_fim
            )
            if encerramento_valido:
                continue
            motivo = (
                "liquidação provisória reaberta: o período ainda não "
                f"estava encerrado (status={status or 'ausente'})"
            )
            banco.conexao.execute(
                """
                INSERT OR IGNORE INTO revisoes_resultados (
                    sinal_id, revisado_em, encerrado_em_anterior,
                    resultado_anterior, retorno_anterior,
                    observacao_anterior, snapshot_id_liquidacao_anterior,
                    fonte_resultado_anterior, motivo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    linha["sinal_id"], revisado_em, linha["encerrado_em"],
                    linha["resultado"], linha["retorno_unidades"],
                    linha["observacao"], linha["snapshot_id_liquidacao"],
                    linha["fonte_resultado"], motivo,
                ),
            )
            banco.conexao.execute(
                "DELETE FROM resultados_sinais WHERE sinal_id=?",
                (linha["sinal_id"],),
            )
            banco.conexao.execute(
                """
                UPDATE entregas_alertas
                SET status='corrigido', erro=?
                WHERE sinal_id=? AND status='entregue'
                  AND canal LIKE '%:teste:resultado'
                """,
                (motivo, linha["sinal_id"]),
            )
            reabertos.append(linha["sinal_id"])
    return {"quantidade": len(reabertos), "sinais": reabertos}


def liquidar_over_asiatico(total, linha, odd):
    total = int(total)
    linha = float(linha)
    odd = float(odd)
    fracao = round(linha - math.floor(linha), 2)
    if fracao == 0.25:
        componentes = [math.floor(linha), math.floor(linha) + 0.5]
    elif fracao == 0.75:
        componentes = [math.floor(linha) + 0.5, math.ceil(linha)]
    else:
        componentes = [linha]

    resultados = []
    retornos = []
    for componente in componentes:
        if total > componente:
            resultados.append("green")
            retornos.append(odd - 1.0)
        elif total < componente:
            resultados.append("red")
            retornos.append(-1.0)
        else:
            resultados.append("void")
            retornos.append(0.0)
    retorno = round(sum(retornos) / len(retornos), 4)
    conjunto = set(resultados)
    if conjunto == {"green"}:
        resultado = "green"
    elif conjunto == {"red"}:
        resultado = "red"
    elif conjunto == {"void"}:
        resultado = "void"
    elif conjunto == {"green", "void"}:
        resultado = "half_green"
    elif conjunto == {"red", "void"}:
        resultado = "half_red"
    else:
        resultado = "green" if retorno > 0 else "red" if retorno < 0 else "void"
    return resultado, retorno


def _placar_par(valor):
    numeros = re.findall(r"\d+", str(valor or ""))
    return [int(numeros[0]), int(numeros[1])] if len(numeros) >= 2 else None


def _lado_proximo_gol_por_eventos(
    eventos, confirmacao_api, placar_inicial, placar_atual
):
    times = confirmacao_api.get("times") or {}
    ids = [
        (times.get("home") or {}).get("id"),
        (times.get("away") or {}).get("id"),
    ]
    if None in ids or ids[0] == ids[1]:
        return None
    lados = []
    for evento in eventos:
        if str(evento.get("type") or "").lower() != "goal":
            continue
        detalhe = str(evento.get("detail") or "").lower()
        if "cancel" in detalhe or "disallow" in detalhe or "missed" in detalhe:
            continue
        time_id = (evento.get("team") or {}).get("id")
        if time_id == ids[0]:
            lados.append(0)
        elif time_id == ids[1]:
            lados.append(1)
        else:
            return None

    totais = [lados.count(0), lados.count(1)]
    if totais != list(placar_atual):
        return None
    acumulado = [0, 0]
    for lado in lados:
        if acumulado == list(placar_inicial):
            return "casa" if lado == 0 else "visitante"
        acumulado[lado] += 1
        if any(
            acumulado[indice] > placar_inicial[indice]
            for indice in range(2)
        ):
            return None
    return None


def _lado_proximo_gol_por_timeline_packball(
    eventos, placar_inicial, placar_atual
):
    """Usa somente uma timeline completa e coerente com o placar final."""
    lados = []
    for evento in eventos or []:
        if not isinstance(evento, dict):
            return None
        lado = evento.get("lado")
        if lado == "casa":
            lados.append(0)
        elif lado == "visitante":
            lados.append(1)
        else:
            return None
    if [lados.count(0), lados.count(1)] != list(placar_atual):
        return None
    acumulado = [0, 0]
    for lado in lados:
        if acumulado == list(placar_inicial):
            return "casa" if lado == 0 else "visitante"
        acumulado[lado] += 1
        if any(
            acumulado[indice] > placar_inicial[indice]
            for indice in range(2)
        ):
            return None
    return None


def _intervalo(status):
    texto = str(status or "").strip().lower()
    token = texto.rstrip(" '\u2019\"")
    return token == "ht" or "intervalo" in texto or "half time" in texto


def _instante_valido_gol_ht(status):
    if _intervalo(status):
        return True
    minuto = extrair_minuto(status)
    return minuto is not None and minuto <= 45


def calcular_metricas(resultados):
    liquidados = [
        item for item in resultados
        if item["resultado"] in (
            "green", "half_green", "red", "half_red", "void"
        )
    ]
    avaliados = [
        item for item in liquidados
        if item["resultado"] in ("green", "half_green", "red", "half_red")
    ]
    total = len(avaliados)
    exposicoes_liquidadas = len(liquidados)
    greens = sum(1 for item in liquidados if item["resultado"] == "green")
    half_greens = sum(
        1 for item in liquidados if item["resultado"] == "half_green"
    )
    reds = sum(1 for item in liquidados if item["resultado"] == "red")
    half_reds = sum(
        1 for item in liquidados if item["resultado"] == "half_red"
    )
    retornos = [
        float(item["retorno_unidades"] or 0) for item in liquidados
    ]
    lucro = round(sum(retornos), 4)

    saldo = 0.0
    pico = 0.0
    drawdown = 0.0
    sequencia = 0
    maior_sequencia = 0
    for item, retorno in zip(liquidados, retornos):
        saldo += retorno
        pico = max(pico, saldo)
        drawdown = max(drawdown, pico - saldo)
        if item["resultado"] in ("red", "half_red"):
            sequencia += 1
            maior_sequencia = max(maior_sequencia, sequencia)
        elif item["resultado"] != "void":
            sequencia = 0

    intervalo = intervalo_wilson(greens + half_greens, total)
    return {
        "amostra": total,
        "exposicoes_liquidadas": exposicoes_liquidadas,
        "greens": greens,
        "half_greens": half_greens,
        "reds": reds,
        "half_reds": half_reds,
        "voids": sum(
            1 for item in liquidados if item["resultado"] == "void"
        ),
        "taxa_acerto": round((greens + half_greens) / total, 4)
        if total else None,
        "intervalo_acerto_95": (
            [round(intervalo[0], 4), round(intervalo[1], 4)]
            if intervalo else None
        ),
        "estado_amostra": estado_amostra(total),
        "lucro_unidades": lucro,
        "roi": (
            round(lucro / exposicoes_liquidadas, 4)
            if exposicoes_liquidadas else None
        ),
        "yield": (
            round(lucro / exposicoes_liquidadas, 4)
            if exposicoes_liquidadas else None
        ),
        "drawdown_maximo": round(drawdown, 4),
        "maior_sequencia_reds": maior_sequencia,
        "discriminacao_pontuacao": discriminacao_pontuacao(avaliados),
    }


def metricas_segmentadas(banco, regra_versao=None):
    limites = obter_limites_risco()
    linhas = banco.conexao.execute(
        """
        WITH candidatos AS (
            SELECT s.id, s.partida_id, s.mercado, s.regra_versao,
                   s.criado_em, s.pontuacao_tecnica, s.odd,
                   inicial.status,
                   COALESCE(p.liga_normalizada, '') AS liga,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.partida_id, s.mercado, s.regra_versao
                       ORDER BY s.criado_em, s.id
                   ) AS ordem
            FROM sinais s
            JOIN snapshots inicial ON inicial.id=s.snapshot_id
            JOIN partidas p ON p.id=s.partida_id
            WHERE s.status='aprovado'
              AND s.odd BETWEEN ? AND ?
              AND (? IS NULL OR s.regra_versao=?)
        )
        SELECT c.*, r.resultado, r.retorno_unidades, r.encerrado_em,
               r.sinal_id
        FROM candidatos c
        JOIN resultados_sinais r ON r.sinal_id=c.id
        WHERE c.ordem=1
          AND r.resultado IN (
              'green', 'half_green', 'red', 'half_red', 'void'
          )
        ORDER BY datetime(r.encerrado_em), r.sinal_id
        """,
        (
            limites.odd_minima,
            limites.odd_maxima,
            regra_versao,
            regra_versao,
        ),
    ).fetchall()
    dimensoes = {"liga": {}, "mercado": {}, "minuto": {}, "odd": {}}
    for linha in linhas:
        minuto = extrair_minuto(linha["status"])
        faixa_minuto = _faixa_minuto(minuto)
        faixa_odd = _faixa_odd(linha["odd"])
        valores = {
            "liga": linha["liga"] or "sem_liga",
            "mercado": linha["mercado"],
            "minuto": faixa_minuto,
            "odd": faixa_odd,
        }
        for dimensao, valor in valores.items():
            dimensoes[dimensao].setdefault(valor, []).append(linha)
    return {
        dimensao: {
            valor: calcular_metricas(itens)
            for valor, itens in grupos.items()
        }
        for dimensao, grupos in dimensoes.items()
    }


def resumir_funil_sinais(
    conexao, regra_versao, odd_minima, odd_maxima
):
    funil = {}
    linhas = conexao.execute(
        """
        SELECT mercado, status, odd, pontuacao_tecnica, motivos_json
        FROM sinais WHERE regra_versao=? ORDER BY id
        """,
        (regra_versao,),
    ).fetchall()
    for linha in linhas:
        mercado = linha["mercado"]
        resumo = funil.setdefault(
            mercado,
            {
                "gerados": 0,
                "aprovados": 0,
                "rejeitados": 0,
                "duplicados": 0,
                "nota_minima": 0,
                "odd_estruturada": 0,
                "odd_elegivel": 0,
                "bloqueios": Counter(),
            },
        )
        resumo["gerados"] += 1
        status = {
            "aprovado": "aprovados",
            "rejeitado": "rejeitados",
            "duplicado": "duplicados",
        }.get(linha["status"])
        if status is not None:
            resumo[status] += 1
        if float(linha["pontuacao_tecnica"] or 0) >= 70:
            resumo["nota_minima"] += 1
        odd = linha["odd"]
        if odd is not None:
            resumo["odd_estruturada"] += 1
            if odd_minima <= float(odd) <= odd_maxima:
                resumo["odd_elegivel"] += 1
        try:
            motivos = json.loads(linha["motivos_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            motivos = []
        for motivo in motivos:
            if str(motivo).startswith("bloqueio:"):
                resumo["bloqueios"][str(motivo).split(":", 1)[1]] += 1
    for resumo in funil.values():
        resumo["bloqueios"] = dict(
            sorted(
                resumo["bloqueios"].items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
    return funil


def _faixa_minuto(minuto):
    if minuto is None:
        return "indisponivel"
    inicio = min((minuto // 15) * 15, 90)
    return f"{inicio:02d}-{inicio + 14:02d}"


def _faixa_odd(odd):
    if odd is None:
        return "sem_odd"
    valor = float(odd)
    if valor < 1.5:
        return "1.00-1.49"
    if valor < 2:
        return "1.50-1.99"
    if valor < 3:
        return "2.00-2.99"
    return "3.00+"
