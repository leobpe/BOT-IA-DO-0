"""Cliente fail-closed da BetsAPI/B365API para odds Bet365 ao vivo.

A fonte complementa partidas que o monitor ja selecionou. O pareamento exige
nomes fortes e placar compativel; mercados suspensos, incompletos ou antigos
nunca sao devolvidos ao motor de sinais.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from processo_monitor import gravar_json_atomico


FONTE = "betsapi"
BOOKMAKER = "bet365"
BASE_URL_PADRAO = "https://api.b365api.com"
MAX_RESPOSTA_BYTES = 12 * 1024 * 1024
MERCADOS_SUPORTADOS = frozenset({
    "gol_ft",
    "gol_ht",
    "proximo_gol",
    "escanteios_ft_asiatico",
})


def _agora_epoch():
    return time.time()


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()
    descartadas = {"fc", "cf", "sc", "ac", "club", "de", "da", "do", "the"}
    return " ".join(p for p in texto.split() if p not in descartadas)


def _similaridade(a, b):
    a, b = _normalizar(a), _normalizar(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sequencia = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / max(len(ta | tb), 1)
    return max(sequencia, jaccard)


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    texto = str(valor).strip().replace(",", ".")
    if not texto:
        return None
    try:
        numero = float(texto)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _odd_decimal(fracionaria):
    """Converte a odd fracionaria da Bet365 para decimal."""
    if fracionaria is None or isinstance(fracionaria, bool):
        return None
    texto = str(fracionaria).strip()
    if not texto:
        return None
    try:
        if "/" in texto:
            numerador, denominador = texto.split("/", 1)
            denominador = float(denominador)
            if denominador <= 0:
                return None
            valor = 1.0 + float(numerador) / denominador
        else:
            # Algumas respostas excepcionais ja usam formato decimal.
            valor = float(texto.replace(",", "."))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if not math.isfinite(valor) or valor <= 1.0 or valor > 1001.0:
        return None
    return round(valor, 4)


def _placar(valor):
    encontrado = re.search(r"(\d+)\s*[-:]\s*(\d+)", str(valor or ""))
    if not encontrado:
        return None
    return int(encontrado.group(1)), int(encontrado.group(2))


def _resultado_lista(resposta):
    resultados = (resposta or {}).get("results")
    if not isinstance(resultados, list):
        return []
    if len(resultados) == 1 and isinstance(resultados[0], list):
        return [item for item in resultados[0] if isinstance(item, dict)]
    return [item for item in resultados if isinstance(item, dict)]


def _instante_iso(epoch):
    try:
        epoch = float(epoch)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(epoch) or epoch <= 0:
        return None
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


class BetsAPI:
    def __init__(
        self,
        pasta,
        *,
        abridor=None,
        relogio=None,
        timeout=15,
        arquivo_estado=None,
    ):
        self.pasta = Path(pasta)
        self.token = (os.getenv("BETSAPI_TOKEN") or "").strip()
        self.ativa = bool(
            self.token and os.getenv("BETSAPI_ATIVA", "1") == "1"
        )
        self.aplicacao_sinais = bool(
            self.ativa
            and os.getenv("BETSAPI_APLICACAO_SINAIS_ATIVA", "1") == "1"
        )
        self.base_url = (
            os.getenv("BETSAPI_BASE_URL") or BASE_URL_PADRAO
        ).strip().rstrip("/")
        if not self.base_url.startswith("https://"):
            self.base_url = BASE_URL_PADRAO
        self.timeout = min(max(float(timeout), 1.0), 60.0)
        self.abridor = abridor or urlopen
        self.relogio = relogio or _agora_epoch
        self.limite_hora = self._inteiro_env(
            "BETSAPI_LIMITE_HORA", 3000, 1, 3600
        )
        self.limite_diario = self._inteiro_env(
            "BETSAPI_LIMITE_DIARIO", 50000, 1, 500000
        )
        self.frescor_maximo = self._inteiro_env(
            "BETSAPI_FRESCOR_MAX_SEGUNDOS", 120, 15, 360
        )
        self.arquivo_estado = Path(
            arquivo_estado or self.pasta / "betsapi_uso.json"
        )
        self._lock = threading.RLock()
        self._cache = {}
        self._estado = self._carregar_estado()
        self._restaurar_circuito()

    @staticmethod
    def _inteiro_env(nome, padrao, minimo, maximo):
        try:
            valor = int(os.getenv(nome, str(padrao)))
        except (TypeError, ValueError):
            valor = int(padrao)
        return min(max(valor, minimo), maximo)

    def _carregar_estado(self):
        try:
            dados = json.loads(self.arquivo_estado.read_text(encoding="utf-8"))
            if isinstance(dados, dict) and dados.get("versao") == 1:
                return dados
        except (OSError, ValueError, UnicodeError):
            pass
        return {"versao": 1, "horas": {}, "dias": {}}

    def _salvar_estado(self):
        gravar_json_atomico(self.arquivo_estado, self._estado)

    def _restaurar_circuito(self):
        """Restaura o backoff para que reiniciar nao contorne a protecao."""
        circuito = self._estado.get("circuito") or {}
        try:
            falhas = int(circuito.get("falhas_consecutivas", 0) or 0)
        except (TypeError, ValueError):
            falhas = 0
        try:
            bloqueado_ate = float(circuito.get("bloqueado_ate", 0) or 0)
        except (TypeError, ValueError):
            bloqueado_ate = 0.0
        if not math.isfinite(bloqueado_ate) or bloqueado_ate < 0:
            bloqueado_ate = 0.0
        motivo = circuito.get("motivo")
        self._falhas = max(falhas, 0)
        self._bloqueado_ate = bloqueado_ate
        self._circuito_motivo = (
            str(motivo)[:160] if motivo not in (None, "") else None
        )
        try:
            atualizado_em = float(circuito.get("atualizado_em", 0) or 0)
        except (TypeError, ValueError):
            atualizado_em = 0.0
        self._circuito_atualizado_em = (
            atualizado_em
            if math.isfinite(atualizado_em) and atualizado_em >= 0
            else 0.0
        )
        self._persistencia_circuito_saudavel = True

    def _persistir_circuito(self, motivo):
        """Persiste o estado do circuito sem derrubar a fonte por falha de IO."""
        self._circuito_motivo = (
            str(motivo)[:160] if motivo not in (None, "") else None
        )
        self._circuito_atualizado_em = float(self.relogio())
        self._estado["circuito"] = {
            "versao": "circuito-betsapi-persistente-v1",
            "falhas_consecutivas": int(self._falhas),
            "bloqueado_ate": float(self._bloqueado_ate),
            "motivo": self._circuito_motivo,
            "atualizado_em": self._circuito_atualizado_em,
        }
        try:
            self._salvar_estado()
        except OSError:
            self._persistencia_circuito_saudavel = False
            return False
        self._persistencia_circuito_saudavel = True
        return True

    def _chaves_periodo(self):
        agora = datetime.fromtimestamp(self.relogio(), timezone.utc)
        return agora.strftime("%Y-%m-%dT%H"), agora.strftime("%Y-%m-%d")

    def _pode_consumir(self):
        if (
            not self.ativa
            or not self._persistencia_circuito_saudavel
            or self.relogio() < self._bloqueado_ate
        ):
            return False
        hora, dia = self._chaves_periodo()
        return bool(
            int((self._estado.get("horas") or {}).get(hora, 0))
            < self.limite_hora
            and int((self._estado.get("dias") or {}).get(dia, 0))
            < self.limite_diario
        )

    def _registrar_chamada(self):
        hora, dia = self._chaves_periodo()
        horas = self._estado.setdefault("horas", {})
        dias = self._estado.setdefault("dias", {})
        horas[hora] = int(horas.get(hora, 0)) + 1
        dias[dia] = int(dias.get(dia, 0)) + 1
        self._estado["horas"] = dict(sorted(horas.items())[-72:])
        self._estado["dias"] = dict(sorted(dias.items())[-40:])
        self._salvar_estado()

    def _requisitar(self, caminho, parametros):
        with self._lock:
            if not self._pode_consumir():
                return None
            self._registrar_chamada()
        url = f"{self.base_url}/{caminho.lstrip('/')}?{urlencode({**parametros, 'token': self.token})}"
        try:
            resposta = self.abridor(
                Request(url, headers={"User-Agent": "PackBallBot/1.0"}),
                timeout=self.timeout,
            )
            bruto = resposta.read(MAX_RESPOSTA_BYTES + 1)
            if len(bruto) > MAX_RESPOSTA_BYTES:
                raise ValueError("resposta_excedeu_limite")
            dados = json.loads(bruto.decode("utf-8"))
            if not isinstance(dados, dict) or dados.get("success") not in (1, "1", True):
                raise ValueError("resposta_betsapi_invalida")
            with self._lock:
                circuito_alterado = bool(
                    self._falhas
                    or self._bloqueado_ate
                    or self._circuito_motivo
                )
                self._falhas = 0
                self._bloqueado_ate = 0.0
                persistencia_ok = bool(
                    not circuito_alterado
                    or self._persistir_circuito(None)
                )
            if not persistencia_ok:
                return None
            return dados
        except HTTPError as erro:
            with self._lock:
                self._falhas += 1
                if erro.code in (401, 403, 429):
                    self._bloqueado_ate = self.relogio() + 15 * 60
                elif self._falhas >= 3:
                    self._bloqueado_ate = self.relogio() + 120
                self._persistir_circuito(f"http_{erro.code}")
            return None
        except (URLError, OSError, ValueError, UnicodeError, json.JSONDecodeError):
            with self._lock:
                self._falhas += 1
                if self._falhas >= 3:
                    self._bloqueado_ate = self.relogio() + 120
                self._persistir_circuito("falha_transitoria")
            return None

    def _cacheado(self, chave, ttl, carregar):
        agora = self.relogio()
        item = self._cache.get(chave)
        if item and agora - item[0] <= ttl:
            return item[1]
        dados = carregar()
        if dados is not None:
            self._cache[chave] = (agora, dados)
        return dados

    @staticmethod
    def _nome_time(evento, chave):
        valor = evento.get(chave)
        if isinstance(valor, dict):
            return valor.get("name") or valor.get("name_en") or ""
        return valor or ""

    def _eventos_ao_vivo(self):
        resposta = self._cacheado(
            "inplay_filter",
            20,
            lambda: self._requisitar(
                "v1/bet365/inplay_filter", {"sport_id": 1}
            ),
        )
        return _resultado_lista(resposta)

    def _parear_evento(self, jogo):
        casa = jogo.get("mandante") or jogo.get("casa") or ""
        fora = jogo.get("visitante") or jogo.get("fora") or ""
        placar_jogo = _placar(jogo.get("placar"))
        opcoes = []
        for evento in self._eventos_ao_vivo():
            casa_api = self._nome_time(evento, "home")
            fora_api = self._nome_time(evento, "away")
            direta = (_similaridade(casa, casa_api), _similaridade(fora, fora_api))
            inversa = (_similaridade(casa, fora_api), _similaridade(fora, casa_api))
            orientacao, par = (
                ("direta", direta) if sum(direta) >= sum(inversa)
                else ("invertida", inversa)
            )
            if min(par) < 0.76 or sum(par) / 2 < 0.84:
                continue
            placar_api = _placar(evento.get("ss"))
            if placar_jogo is not None and placar_api is not None:
                esperado = placar_jogo if orientacao == "direta" else placar_jogo[::-1]
                if placar_api != esperado:
                    continue
            score = sum(par) / 2
            opcoes.append((score, evento, orientacao))
        opcoes.sort(key=lambda item: item[0], reverse=True)
        if not opcoes:
            return None
        if len(opcoes) > 1 and opcoes[0][0] - opcoes[1][0] < 0.06:
            return None
        score, evento, orientacao = opcoes[0]
        atualizado = _numero(evento.get("updated_at"))
        idade = (
            max(self.relogio() - atualizado, 0.0)
            if atualizado is not None else None
        )
        if idade is None or idade > self.frescor_maximo:
            return None
        return {
            "evento_id": str(evento.get("id") or ""),
            "similaridade": round(score, 4),
            "orientacao": orientacao,
            "mandante_observado": self._nome_time(evento, "home"),
            "visitante_observado": self._nome_time(evento, "away"),
            "placar_observado": evento.get("ss"),
            "atualizado_em_epoch": atualizado,
            "idade_segundos": round(idade, 3),
        }

    def cobertura_jogos_ao_vivo(self, jogos):
        """Pareia um lote usando uma unica leitura cacheada do ao vivo.

        Esta etapa nao abre o detalhe de odds de cada evento. Ela serve para
        a triagem saber, antes de navegar no PackBall, quais partidas possuem
        cobertura Bet365 na BetsAPI. A odd continua sendo consultada somente
        para os jogos efetivamente selecionados pelo motor.
        """
        diagnostico = {
            "ativa": self.ativa,
            "aplicacao_sinais": self.aplicacao_sinais,
            "avaliados": len(jogos or []),
            "pareados": 0,
            "cobertura_por_url": {},
            "fonte": FONTE,
            "bookmaker": BOOKMAKER,
            "rollback": "PACKBALL_TRIAGEM_CAPACIDADE_ATIVA=0",
        }
        if not self.ativa:
            diagnostico["motivo"] = "fonte_desativada"
            return diagnostico
        if not self.aplicacao_sinais:
            diagnostico["motivo"] = "aplicacao_sinais_desativada"
            return diagnostico

        # A primeira chamada carrega o filtro global; as demais reutilizam o
        # mesmo objeto por 20 segundos e nao gastam uma requisicao por jogo.
        for jogo in jogos or []:
            url = str((jogo or {}).get("url") or "")
            if not url:
                continue
            pareamento = self._parear_evento(jogo)
            if not pareamento:
                continue
            diagnostico["cobertura_por_url"][url] = {
                "evento_externo_id": pareamento.get("evento_id"),
                "similaridade": pareamento.get("similaridade"),
                "idade_segundos": pareamento.get("idade_segundos"),
            }
        diagnostico["pareados"] = len(
            diagnostico["cobertura_por_url"]
        )
        diagnostico["motivo"] = (
            "cobertura_encontrada"
            if diagnostico["pareados"] else "sem_cobertura_pareada"
        )
        return diagnostico

    def _evento(self, evento_id):
        return self._cacheado(
            ("evento", str(evento_id)),
            12,
            lambda: self._requisitar(
                "v1/bet365/event", {"FI": str(evento_id)}
            ),
        )

    @staticmethod
    def _grupos_mercado(resposta):
        grupos = []
        atual = None
        lado = None
        lado_suspenso = False
        for item in _resultado_lista(resposta):
            tipo = str(item.get("type") or "")
            if tipo == "MG":
                atual = {
                    "nome": item.get("NA") or "",
                    "id": item.get("ID"),
                    "ordem": len(grupos) + 1,
                    "suspenso": str(item.get("SU") or "0") == "1",
                    "participantes": [],
                }
                grupos.append(atual)
                lado = None
                lado_suspenso = False
            elif tipo == "MA" and atual is not None:
                lado = _normalizar(item.get("NA"))
                lado_suspenso = str(item.get("SU") or "0") == "1"
            elif tipo == "PA" and atual is not None:
                odd = _odd_decimal(item.get("OD"))
                suspenso = bool(
                    atual["suspenso"]
                    or lado_suspenso
                    or str(item.get("SU") or "0") == "1"
                )
                if odd is None or suspenso:
                    continue
                atual["participantes"].append({
                    "nome": item.get("NA") or "",
                    "linha": item.get("HA"),
                    "handicap": item.get("HD"),
                    "odd": odd,
                    "lado": lado,
                    "ordem": item.get("OR"),
                })
        return grupos

    @staticmethod
    def _grupo_gol_ft(nome):
        nome = _normalizar(nome)
        if "corner" in nome or "half" in nome or "team" in nome:
            return False
        return bool(
            nome in {"match goals", "alternative match goals"}
            or "goal line" in nome
            or nome == "total goals"
        )

    @staticmethod
    def _grupo_gol_ht(nome):
        nome = _normalizar(nome)
        return bool(
            "goal" in nome
            and "corner" not in nome
            and ("1st half" in nome or "first half" in nome)
        )

    @staticmethod
    def _grupo_escanteio_asiatico_ft(nome):
        nome = _normalizar(nome)
        return bool(
            "corner" in nome
            and "half" not in nome
            and ("asian" in nome or "corner line" in nome)
        )

    def _proveniencia(self, pareamento):
        # ``updated_at`` do inplay_filter descreve o último evento/placar da
        # partida, não o instante em que a Bet365 publicou a odd. Usá-lo como
        # idade da cotação fazia uma resposta de odds recém-consultada parecer
        # velha sempre que o jogo passava alguns minutos sem gol/cartão.
        # A identidade e o placar continuam validados pelo ``updated_at``;
        # para a cotação usamos o instante real da consulta (ou do cache curto
        # de 12 s do endpoint bet365/event).
        coletado_epoch = pareamento.get("odds_coletadas_em_epoch")
        if coletado_epoch is None:
            coletado_epoch = pareamento.get("atualizado_em_epoch")
        coletado = _instante_iso(coletado_epoch)
        idade_odds = pareamento.get("odds_idade_segundos")
        if idade_odds is None:
            idade_odds = pareamento.get("idade_segundos")
        orientacao = str(pareamento.get("orientacao") or "").casefold()
        mandante_observado = pareamento.get("mandante_observado") or ""
        visitante_observado = pareamento.get("visitante_observado") or ""
        placar_normalizado = _placar(pareamento.get("placar_observado"))
        if orientacao == "invertida":
            mandante_observado, visitante_observado = (
                visitante_observado, mandante_observado
            )
            if placar_normalizado is not None:
                placar_normalizado = placar_normalizado[::-1]
        identidade_evento = {
            "schema": "identidade-evento-odd-v1",
            "confirmada": True,
            "fonte": FONTE,
            "evento_externo_id": str(
                pareamento.get("evento_id") or ""
            ),
            "orientacao": orientacao,
            "similaridade": pareamento.get("similaridade"),
            "mandante_normalizado": mandante_observado,
            "visitante_normalizado": visitante_observado,
            "placar_normalizado": (
                f"{placar_normalizado[0]}-{placar_normalizado[1]}"
                if placar_normalizado is not None else None
            ),
            "metodo": "nomes_placar_frescor_betsapi",
        }
        return {
            "fonte": FONTE,
            "bookmaker": BOOKMAKER,
            "coletado_em": coletado,
            "recebido_em": datetime.fromtimestamp(
                self.relogio(), timezone.utc
            ).isoformat(),
            "idade_segundos": idade_odds,
            "cache": bool(pareamento.get("odds_cache")),
            "evento_externo_id": pareamento.get("evento_id"),
            "identidade_evento": identidade_evento,
        }

    @staticmethod
    def _origem_grupo_mercado(grupo, linha, lados):
        nome = str(grupo.get("nome") or "").strip()
        identificador = str(grupo.get("id") or "").strip()
        if not identificador:
            identificador = (
                f"ordem:{int(grupo.get('ordem') or 0)}:{_normalizar(nome)}"
            )
        return {
            "schema": "origem-mercado-odd-v1",
            "fonte": FONTE,
            "identificador": identificador,
            "nome": nome,
            "linha": linha,
            "lados": list(lados),
            "bookmaker": BOOKMAKER,
        }

    def _ofertas_total(self, grupos, seletor, pareamento):
        ofertas_por_linha = {}
        for grupo in grupos:
            if not seletor(grupo.get("nome")):
                continue
            linhas_grupo = {}
            for item in grupo.get("participantes") or []:
                lado = item.get("lado")
                if lado not in ("over", "under"):
                    continue
                linha = _numero(item.get("linha"))
                if linha is None:
                    continue
                dados = linhas_grupo.setdefault(linha, {"linha": linha})
                dados.setdefault(lado, item.get("odd"))
            for linha, dados in linhas_grupo.items():
                if dados.get("over") is None or dados.get("under") is None:
                    continue
                ofertas_por_linha.setdefault(linha, {
                    **dados,
                    "origem_mercado": self._origem_grupo_mercado(
                        grupo, linha, ("over", "under")
                    ),
                })
        proveniencia = self._proveniencia(pareamento)
        return [
            {**ofertas_por_linha[linha], **proveniencia}
            for linha in sorted(ofertas_por_linha)
        ]

    def _mercado_proximo_gol(self, grupos, jogo, pareamento):
        placar = _placar(jogo.get("placar"))
        if placar is None:
            return None
        ordinal_esperado = sum(placar) + 1
        grupo_escolhido = None
        for grupo in grupos:
            nome = _normalizar(grupo.get("nome"))
            encontrado = re.fullmatch(r"(\d+)(?:st|nd|rd|th) goal", nome)
            if encontrado and int(encontrado.group(1)) == ordinal_esperado:
                grupo_escolhido = grupo
                break
        if grupo_escolhido is None:
            return None
        selecoes = {}
        casa = jogo.get("mandante") or jogo.get("casa") or ""
        fora = jogo.get("visitante") or jogo.get("fora") or ""
        for item in grupo_escolhido.get("participantes") or []:
            nome = item.get("nome") or ""
            normalizado = _normalizar(nome)
            if normalizado.startswith("no ") and normalizado.endswith(" goal"):
                chave = "sem_gol"
            else:
                sim_casa = _similaridade(nome, casa)
                sim_fora = _similaridade(nome, fora)
                if max(sim_casa, sim_fora) < 0.76:
                    continue
                chave = "casa" if sim_casa >= sim_fora else "visitante"
            selecoes[chave] = item.get("odd")
        if not {"casa", "visitante", "sem_gol"} <= set(selecoes):
            return None
        proveniencia = self._proveniencia(pareamento)
        return {
            "mercado": "Próximo gol",
            "categoria": "gols",
            "escopo": "proximo",
            "tipo_mercado": "proximo",
            "formato": "tres_opcoes",
            "ofertas": [],
            "selecoes": selecoes,
            "origem_mercado": self._origem_grupo_mercado(
                grupo_escolhido,
                ordinal_esperado,
                ("casa", "visitante", "sem_gol"),
            ),
            **proveniencia,
        }

    def buscar_mercados(self, jogo, mercados_internos):
        diagnostico = {
            "ativa": self.ativa,
            "aplicacao_sinais": self.aplicacao_sinais,
            "pareado": False,
            "consultados": [],
            "anexados": [],
            "fonte": FONTE,
            "bookmaker": BOOKMAKER,
            "rollback": "BETSAPI_ATIVA=0",
        }
        solicitados = set(mercados_internos or ()) & set(MERCADOS_SUPORTADOS)
        diagnostico["solicitados"] = sorted(solicitados)
        if not self.ativa:
            diagnostico["motivo"] = "fonte_desativada"
            return {"ao_vivo": []}, diagnostico
        if not self.aplicacao_sinais:
            diagnostico["motivo"] = "aplicacao_sinais_desativada"
            return {"ao_vivo": []}, diagnostico
        if not solicitados:
            diagnostico["motivo"] = "sem_mercado_compativel"
            return {"ao_vivo": []}, diagnostico
        pareamento = self._parear_evento(jogo)
        if not pareamento:
            diagnostico["motivo"] = "evento_nao_encontrado"
            return {"ao_vivo": []}, diagnostico
        diagnostico.update({
            "pareado": True,
            "similaridade": pareamento["similaridade"],
            "evento_externo_id": pareamento["evento_id"],
            "mandante_observado": pareamento["mandante_observado"],
            "visitante_observado": pareamento["visitante_observado"],
            "placar_observado": pareamento["placar_observado"],
        })
        chave_cache_evento = ("evento", str(pareamento["evento_id"]))
        agora_evento = self.relogio()
        cache_antes = self._cache.get(chave_cache_evento)
        cache_valido_antes = bool(
            cache_antes and agora_evento - cache_antes[0] <= 12
        )
        resposta = self._evento(pareamento["evento_id"])
        diagnostico["consultados"].append("bet365/event")
        if resposta is None:
            diagnostico["motivo"] = "evento_sem_resposta"
            return {"ao_vivo": []}, diagnostico
        cache_depois = self._cache.get(chave_cache_evento)
        coletado_epoch = (
            cache_depois[0] if cache_depois is not None else self.relogio()
        )
        pareamento = {
            **pareamento,
            "odds_coletadas_em_epoch": coletado_epoch,
            "odds_idade_segundos": round(
                max(self.relogio() - coletado_epoch, 0.0), 3
            ),
            "odds_cache": bool(
                cache_valido_antes
                and cache_depois is not None
                and cache_antes[0] == cache_depois[0]
            ),
        }
        grupos = self._grupos_mercado(resposta)
        mercados = []
        if "gol_ft" in solicitados:
            ofertas = self._ofertas_total(grupos, self._grupo_gol_ft, pareamento)
            if ofertas:
                mercados.append({
                    "categoria": "gols", "escopo": "total",
                    "tipo_mercado": "total", "formato": "duas_opcoes",
                    "ofertas": ofertas, "ofertas_ht": [],
                    **self._proveniencia(pareamento),
                })
                diagnostico["anexados"].append("gol_ft")
        if "gol_ht" in solicitados:
            ofertas = self._ofertas_total(grupos, self._grupo_gol_ht, pareamento)
            if ofertas:
                mercados.append({
                    "categoria": "gols", "escopo": "total",
                    "tipo_mercado": "total", "formato": "duas_opcoes",
                    "ofertas": [], "ofertas_ht": ofertas,
                    **self._proveniencia(pareamento),
                })
                diagnostico["anexados"].append("gol_ht")
        if "escanteios_ft_asiatico" in solicitados:
            ofertas = self._ofertas_total(
                grupos, self._grupo_escanteio_asiatico_ft, pareamento
            )
            if ofertas:
                mercados.append({
                    "categoria": "escanteios", "escopo": "total",
                    "tipo_mercado": "asiatico", "formato": "duas_opcoes",
                    "ofertas": ofertas,
                    **self._proveniencia(pareamento),
                })
                diagnostico["anexados"].append("escanteios_ft_asiatico")
        if "proximo_gol" in solicitados:
            mercado = self._mercado_proximo_gol(grupos, jogo, pareamento)
            if mercado:
                mercados.append(mercado)
                diagnostico["anexados"].append("proximo_gol")
        diagnostico["motivo"] = (
            "oferta_anexada" if diagnostico["anexados"]
            else "mercado_sem_oferta_ativa"
        )
        return {"ao_vivo": mercados}, diagnostico

    def diagnostico(self):
        hora, dia = self._chaves_periodo()
        agora = float(self.relogio())
        circuito_aberto = agora < self._bloqueado_ate
        return {
            "ativa": self.ativa,
            "chave_configurada": bool(self.token),
            "aplicacao_sinais": self.aplicacao_sinais,
            "uso_hora": int((self._estado.get("horas") or {}).get(hora, 0)),
            "limite_hora": self.limite_hora,
            "uso_dia": int((self._estado.get("dias") or {}).get(dia, 0)),
            "limite_diario": self.limite_diario,
            "circuito_aberto": circuito_aberto,
            "circuito": {
                "versao": "circuito-betsapi-persistente-v1",
                "aberto": circuito_aberto,
                "falhas_consecutivas": int(self._falhas),
                "bloqueado_ate": _instante_iso(self._bloqueado_ate),
                "restante_segundos": round(
                    max(self._bloqueado_ate - agora, 0.0), 3
                ),
                "motivo": self._circuito_motivo,
                "atualizado_em": _instante_iso(
                    self._circuito_atualizado_em
                ),
                "persistente": True,
                "persistencia_saudavel": bool(
                    self._persistencia_circuito_saudavel
                ),
                "recuperacao_automatica": True,
            },
            "rollback": "BETSAPI_ATIVA=0",
        }
