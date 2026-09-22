"""Cliente protegido da The Odds API para complementar odds ao vivo.

A fonte nunca cria sinais sozinha: recebe uma partida já confirmada pelo
PackBall, exige pareamento forte e devolve somente mercados explicitamente
suportados. O consumo é limitado localmente e reconciliado pelos cabeçalhos
oficiais do provedor.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from processo_monitor import gravar_json_atomico
from origem_mercado import VERSAO_ORIGEM_MERCADO


BASE_URL = "https://api.the-odds-api.com/v4"
FONTE = "the_odds_api"
MERCADOS_SUPORTADOS = {
    "gol_ft": "alternate_totals",
    "gol_ht": "alternate_totals_h1",
    "escanteios_ft_asiatico": "alternate_totals_corners",
}
BOOKMAKERS_PADRAO = (
    "pinnacle", "onexbet", "williamhill", "coolbet", "gtbets",
)
ALIASES_CATALOGO_POR_PAIS = {
    "england": ("england", "epl", "efl", "fa cup"),
    "europe": ("uefa", "champions league", "europa league"),
    "international": ("fifa", "uefa", "international"),
    "united states": ("usa", "mls"),
    "usa": ("usa", "mls"),
    "south korea": ("korea", "kleague"),
    "czech republic": ("czech",),
    "turkiye": ("turkey", "turkiye"),
    "world": ("fifa", "world cup"),
}


def _agora_epoch():
    return time.time()


def _ler_estado_valido(caminho):
    caminho = Path(caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(dados, dict) or dados.get("versao") != 1:
        return None
    try:
        if int(dados.get("revisao", 0) or 0) < 0:
            return None
    except (TypeError, ValueError):
        return None
    dias = dados.get("dias") or {}
    if not isinstance(dias, dict):
        return None
    try:
        if any(int(valor) < 0 for valor in dias.values()):
            return None
    except (TypeError, ValueError):
        return None
    provedor = dados.get("provedor") or {}
    if not isinstance(provedor, dict):
        return None
    for chave in ("usados", "restante", "ultimo_custo"):
        valor = provedor.get(chave)
        if valor is None:
            continue
        try:
            if int(valor) < 0:
                return None
        except (TypeError, ValueError):
            return None
    amostragem = dados.get("amostragem_referencia") or {}
    if not isinstance(amostragem, dict):
        return None
    try:
        if int(amostragem.get("reservas", 0) or 0) < 0:
            return None
    except (TypeError, ValueError):
        return None
    ultimas = amostragem.get("ultimas") or {}
    if not isinstance(ultimas, dict):
        return None
    try:
        if any(float(valor) < 0 for valor in ultimas.values()):
            return None
    except (TypeError, ValueError):
        return None
    contagens = amostragem.get("contagens") or {}
    if not isinstance(contagens, dict):
        return None
    try:
        if any(int(valor) < 0 for valor in contagens.values()):
            return None
    except (TypeError, ValueError):
        return None
    circuito = dados.get("circuito") or {}
    if not isinstance(circuito, dict):
        return None
    try:
        if int(circuito.get("falhas_consecutivas", 0) or 0) < 0:
            return None
        if float(circuito.get("bloqueado_ate", 0) or 0) < 0:
            return None
    except (TypeError, ValueError):
        return None
    return dados


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()
    palavras_descartadas = {
        "fc", "cf", "sc", "ac", "club", "de", "da", "do", "the",
    }
    partes = [p for p in texto.split() if p not in palavras_descartadas]
    return " ".join(partes)


def _similaridade(a, b):
    a, b = _normalizar(a), _normalizar(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    base = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / max(len(ta | tb), 1)
    return max(base, jaccard)


def _catalogo_compativel_com_pais(esporte, pais):
    """Evita que nomes genéricos apontem para o país errado.

    ``Premier League`` existe em dezenas de países. Para uma pré-seleção que
    decide se vale gastar cota, a semelhança do nome da liga não basta: a
    chave, título ou grupo do catálogo também precisa identificar o país.
    """
    pais_normalizado = _normalizar(pais)
    if not pais_normalizado:
        return True
    texto = _normalizar(
        f"{esporte.get('key')} {esporte.get('title')} "
        f"{esporte.get('group')}"
    )
    tokens_texto = set(texto.split())
    aliases = ALIASES_CATALOGO_POR_PAIS.get(
        pais_normalizado, (pais_normalizado,)
    )
    return any(
        set(_normalizar(alias).split()) <= tokens_texto
        for alias in aliases
        if _normalizar(alias)
    )


def _instante(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip().replace("Z", "+00:00")
    try:
        data = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    return data.astimezone(timezone.utc)


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return None
    return valor if math.isfinite(valor) else None


class TheOddsAPI:
    def __init__(
        self, pasta, *, abridor=None, relogio=None, timeout=12,
        arquivo_estado=None,
    ):
        self.pasta = Path(pasta)
        self.chave = (os.getenv("THE_ODDS_API_KEY") or "").strip()
        self.ativa = bool(
            self.chave
            and os.getenv("THE_ODDS_API_ATIVA", "1") == "1"
        )
        self.regiao = (os.getenv("THE_ODDS_API_REGIAO") or "eu").strip()
        self.timeout = min(max(float(timeout), 1.0), 30.0)
        self.abridor = abridor or urlopen
        self.relogio = relogio or _agora_epoch
        self.limite_diario = int(os.getenv("THE_ODDS_API_LIMITE_DIARIO", "600"))
        self.reserva_mensal = int(os.getenv("THE_ODDS_API_RESERVA_MENSAL", "2000"))
        self.amostragem_referencia_ativa = bool(
            self.ativa
            and os.getenv(
                "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_ATIVA", "0"
            ) == "1"
        )
        self.amostragem_referencia_limite_diario = min(
            max(
                int(os.getenv(
                    "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_LIMITE_DIARIO",
                    "30",
                )),
                0,
            ),
            max(self.limite_diario, 0),
        )
        self.amostragem_referencia_intervalo = min(
            max(
                float(os.getenv(
                    "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_INTERVALO_SEGUNDOS",
                    "600",
                )),
                60.0,
            ),
            86400.0,
        )
        self.amostragem_referencia_maximo_jogo_dia = min(
            max(
                int(os.getenv(
                    "THE_ODDS_API_AMOSTRAGEM_REFERENCIA_MAX_JOGO_DIA",
                    "2",
                )),
                1,
            ),
            10,
        )
        self.frescor_maximo = float(
            os.getenv("THE_ODDS_API_FRESCOR_MAX_SEGUNDOS", "120")
        )
        preferidas = os.getenv("THE_ODDS_API_BOOKMAKERS", "")
        self.bookmakers = tuple(
            item.strip() for item in preferidas.split(",") if item.strip()
        ) or BOOKMAKERS_PADRAO
        self.arquivo_estado = Path(
            arquivo_estado or self.pasta / "the_odds_api_estado.json"
        )
        self.arquivo_estado_backup = self.arquivo_estado.with_suffix(
            self.arquivo_estado.suffix + ".bak"
        )
        self._lock = threading.RLock()
        self._cache = {}
        self.controle_estado_saudavel = True
        self.controle_estado_origem = "novo"
        self.controle_estado_recuperado = False
        self.controle_estado_reparado = False
        self._estado = self._carregar_estado()
        estado_legado_sem_revisao = "revisao" not in self._estado
        circuito = self._estado.get("circuito") or {}
        try:
            self._falhas = max(
                int(circuito.get("falhas_consecutivas") or 0), 0
            )
        except (TypeError, ValueError):
            self._falhas = 0
        try:
            self._bloqueado_ate = max(
                float(circuito.get("bloqueado_ate") or 0.0), 0.0
            )
        except (TypeError, ValueError):
            self._bloqueado_ate = 0.0
        self._circuito_motivo = circuito.get("motivo")
        try:
            if self.controle_estado_saudavel and estado_legado_sem_revisao:
                # Materializa a proteção nova imediatamente, sem depender de
                # uma futura consulta externa para migrar o estado legado.
                self._estado["revisao"] = 1
                gravar_json_atomico(
                    self.arquivo_estado_backup, self._estado
                )
                gravar_json_atomico(self.arquivo_estado, self._estado)
                self.controle_estado_reparado = True
            else:
                principal_atual = _ler_estado_valido(self.arquivo_estado)
                backup_atual = _ler_estado_valido(
                    self.arquivo_estado_backup
                )
                if self.controle_estado_origem == "backup":
                    gravar_json_atomico(self.arquivo_estado, self._estado)
                    self.controle_estado_reparado = True
                elif (
                    self.controle_estado_origem == "principal"
                    and backup_atual != principal_atual
                ):
                    gravar_json_atomico(
                        self.arquivo_estado_backup, self._estado
                    )
                    self.controle_estado_reparado = True
        except OSError:
            self.controle_estado_saudavel = False
            self.controle_estado_origem = "falha_reparo_estado"

    def _carregar_estado(self):
        principal_existe = self.arquivo_estado.exists()
        backup_existe = self.arquivo_estado_backup.exists()
        principal = (
            _ler_estado_valido(self.arquivo_estado)
            if principal_existe else None
        )
        backup = (
            _ler_estado_valido(self.arquivo_estado_backup)
            if backup_existe else None
        )
        if principal is not None and backup is not None:
            revisao_principal = int(principal.get("revisao", 0) or 0)
            revisao_backup = int(backup.get("revisao", 0) or 0)
            if revisao_backup > revisao_principal:
                self.controle_estado_origem = "backup"
                self.controle_estado_recuperado = True
                return backup
            self.controle_estado_origem = "principal"
            return principal
        if principal is not None:
            self.controle_estado_origem = "principal"
            return principal
        if backup is not None:
            self.controle_estado_origem = "backup"
            self.controle_estado_recuperado = True
            return backup
        if not principal_existe and not backup_existe:
            return {
                "versao": 1, "revisao": 0,
                "dias": {}, "provedor": {},
            }

        # Nunca assuma consumo zero depois de perder os dois estados. O teto
        # local já consumido bloqueia chamadas até recuperação explícita.
        self.controle_estado_saudavel = False
        self.controle_estado_origem = "corrompido"
        return {
            "versao": 1,
            "revisao": 0,
            "dias": {self._dia(): max(int(self.limite_diario), 0)},
            "provedor": {"restante": max(int(self.reserva_mensal), 0)},
        }

    def _salvar_estado(self):
        revisao_atual = int(self._estado.get("revisao", 0) or 0)
        self._estado["revisao"] = revisao_atual + 1
        try:
            # As duas cópias recebem a mesma revisão. Se o processo cair entre
            # as gravações, a próxima inicialização escolhe a revisão maior.
            gravar_json_atomico(self.arquivo_estado_backup, self._estado)
            gravar_json_atomico(self.arquivo_estado, self._estado)
        except OSError:
            self.controle_estado_saudavel = False
            self.controle_estado_origem = "falha_persistencia"
            return False
        self.controle_estado_origem = "principal"
        return True

    def _atualizar_estado_circuito(self, motivo=None):
        self._circuito_motivo = motivo
        self._estado["circuito"] = {
            "versao": "circuito-the-odds-api-persistente-v1",
            "falhas_consecutivas": int(self._falhas),
            "bloqueado_ate": float(self._bloqueado_ate),
            "motivo": motivo,
            "atualizado_em": float(self.relogio()),
        }

    def _dia(self):
        return datetime.fromtimestamp(
            self.relogio(), timezone.utc
        ).strftime("%Y-%m-%d")

    def _consumo_dia(self):
        return int((self._estado.get("dias") or {}).get(self._dia(), 0))

    def _pode_consumir(self, custo_estimado):
        if (
            not self.ativa
            or not self.controle_estado_saudavel
            or self.relogio() < self._bloqueado_ate
        ):
            return False
        if self._consumo_dia() + int(custo_estimado) > self.limite_diario:
            return False
        restante = (self._estado.get("provedor") or {}).get("restante")
        return restante is None or int(restante) - int(custo_estimado) >= self.reserva_mensal

    def reservar_amostragem_referencia(
        self,
        chave,
        custo_estimado=1,
        *,
        permitir_confirmacao=True,
        permitir_recuperacao_coorte=False,
    ):
        """Reserva uma consulta sombra com limite diário e cooldown persistentes.

        A reserva acontece antes da chamada externa para que uma falha ou um
        reinício não possa gerar uma rajada de novas tentativas. O mecanismo é
        exclusivamente observacional e não habilita a fonte para sinais.
        """
        chave = str(chave or "").strip()
        agora = float(self.relogio())
        dia = self._dia()
        diagnostico = {
            "ativa": bool(self.amostragem_referencia_ativa),
            "autorizada": False,
            "limite_diario": int(
                self.amostragem_referencia_limite_diario
            ),
            "intervalo_segundos": float(
                self.amostragem_referencia_intervalo
            ),
            "maximo_por_jogo_dia": int(
                self.amostragem_referencia_maximo_jogo_dia
            ),
            "recuperacao_coorte_solicitada": bool(
                permitir_recuperacao_coorte
            ),
            "recuperacao_coorte_aplicada": False,
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }
        if not self.amostragem_referencia_ativa:
            diagnostico["motivo"] = "amostragem_desativada"
            return diagnostico
        if not chave:
            diagnostico["motivo"] = "chave_amostragem_ausente"
            return diagnostico
        if not self.controle_estado_saudavel:
            diagnostico["motivo"] = "controle_estado_invalido"
            diagnostico["controle_estado_origem"] = (
                self.controle_estado_origem
            )
            return diagnostico
        with self._lock:
            estado = self._estado.get("amostragem_referencia") or {}
            if estado.get("dia") != dia:
                estado = {
                    "dia": dia,
                    "reservas": 0,
                    "ultimas": {},
                    "contagens": {},
                }
            reservas = int(estado.get("reservas", 0) or 0)
            diagnostico["uso_dia"] = reservas
            if reservas >= self.amostragem_referencia_limite_diario:
                diagnostico["motivo"] = "limite_amostragem_diario"
                return diagnostico
            if self.relogio() < self._bloqueado_ate:
                diagnostico.update({
                    "motivo": "circuito_aberto",
                    "bloqueado_ate": float(self._bloqueado_ate),
                    "restante_bloqueio_segundos": round(
                        max(self._bloqueado_ate - self.relogio(), 0.0), 3
                    ),
                })
                return diagnostico
            if not self._pode_consumir(custo_estimado):
                diagnostico["motivo"] = "orcamento_provedor_indisponivel"
                return diagnostico
            contagens = dict(estado.get("contagens") or {})
            uso_chave = int(contagens.get(chave, 0) or 0)
            tipo_amostra = (
                "nova_partida" if uso_chave == 0 else "confirmacao_temporal"
            )
            limite_efetivo_jogo = min(
                self.amostragem_referencia_maximo_jogo_dia
                + int(bool(permitir_recuperacao_coorte)),
                10,
            )
            recuperacao_coorte = bool(
                permitir_recuperacao_coorte
                and uso_chave
                >= self.amostragem_referencia_maximo_jogo_dia
                and uso_chave < limite_efetivo_jogo
            )
            if recuperacao_coorte:
                tipo_amostra = "recuperacao_coorte_resultado"
            diagnostico["uso_jogo_dia"] = uso_chave
            diagnostico["jogos_distintos_dia"] = len(contagens)
            diagnostico["tipo_amostra"] = tipo_amostra
            diagnostico["limite_efetivo_jogo_dia"] = limite_efetivo_jogo
            diagnostico["recuperacao_coorte_aplicada"] = recuperacao_coorte
            if uso_chave >= limite_efetivo_jogo:
                diagnostico["motivo"] = "limite_amostragem_jogo_dia"
                return diagnostico
            if (
                uso_chave > 0
                and not permitir_confirmacao
                and not recuperacao_coorte
            ):
                diagnostico["motivo"] = "reserva_diversidade_ciclo"
                return diagnostico
            ultimas = dict(estado.get("ultimas") or {})
            try:
                ultima = float(ultimas.get(chave))
            except (TypeError, ValueError):
                ultima = None
            if (
                ultima is not None
                and agora - ultima < self.amostragem_referencia_intervalo
            ):
                diagnostico.update({
                    "motivo": "cooldown_amostragem",
                    "restante_cooldown_segundos": round(
                        self.amostragem_referencia_intervalo
                        - max(agora - ultima, 0.0),
                        3,
                    ),
                })
                return diagnostico
            ultimas[chave] = agora
            # O estado guarda somente as chaves mais recentes para continuar
            # pequeno mesmo após meses de operação.
            ultimas = dict(sorted(
                ultimas.items(), key=lambda item: float(item[1])
            )[-500:])
            contagens[chave] = uso_chave + 1
            contagens = {
                chave_estado: int(contagens[chave_estado])
                for chave_estado in ultimas
                if chave_estado in contagens
            }
            estado.update({
                "dia": dia,
                "reservas": reservas + 1,
                "ultimas": ultimas,
                "contagens": contagens,
            })
            self._estado["amostragem_referencia"] = estado
            if not self._salvar_estado():
                diagnostico.update({
                    "motivo": "falha_persistencia_reserva",
                    "controle_estado_origem": (
                        self.controle_estado_origem
                    ),
                })
                return diagnostico
        diagnostico.update({
            "autorizada": True,
            "motivo": "amostragem_reservada",
            "uso_dia": reservas + 1,
            "uso_jogo_dia": uso_chave + 1,
            "jogos_distintos_dia": len(contagens),
        })
        return diagnostico

    def _registrar_headers(self, headers):
        def inteiro(nome):
            try:
                return int(headers.get(nome))
            except (TypeError, ValueError):
                return None
        usados = inteiro("x-requests-used")
        restante = inteiro("x-requests-remaining")
        ultimo = inteiro("x-requests-last") or 0
        dia = self._dia()
        dias = self._estado.setdefault("dias", {})
        dias[dia] = int(dias.get(dia, 0)) + max(ultimo, 0)
        self._estado["dias"] = {
            chave: valor for chave, valor in sorted(dias.items())[-40:]
        }
        self._estado["provedor"] = {
            "usados": usados,
            "restante": restante,
            "ultimo_custo": ultimo,
            "observado_em": self.relogio(),
        }
        self._salvar_estado()

    def _requisitar(self, caminho, parametros, *, custo_estimado=0):
        if not self._pode_consumir(custo_estimado):
            return None
        parametros = {**parametros, "apiKey": self.chave}
        url = f"{BASE_URL}/{caminho.lstrip('/')}?{urlencode(parametros)}"
        try:
            resposta = self.abridor(
                Request(url, headers={"User-Agent": "PackBallBot/1.0"}),
                timeout=self.timeout,
            )
            bruto = resposta.read(10 * 1024 * 1024 + 1)
            if len(bruto) > 10 * 1024 * 1024:
                raise ValueError("resposta_excedeu_limite")
            dados = json.loads(bruto.decode("utf-8"))
            with self._lock:
                self._falhas = 0
                self._bloqueado_ate = 0.0
                self._atualizar_estado_circuito()
                self._registrar_headers(resposta.headers)
            return dados
        except HTTPError as erro:
            with self._lock:
                self._registrar_headers(erro.headers)
                self._falhas += 1
                motivo = f"http_{int(erro.code)}"
                if erro.code in (401, 403, 429):
                    self._bloqueado_ate = self.relogio() + 900
                self._atualizar_estado_circuito(motivo)
                self._salvar_estado()
            return None
        except (URLError, OSError, ValueError, json.JSONDecodeError) as erro:
            with self._lock:
                self._falhas += 1
                if self._falhas >= 3:
                    self._bloqueado_ate = self.relogio() + 120
                self._atualizar_estado_circuito(type(erro).__name__)
                self._salvar_estado()
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

    def esportes(self):
        return self._cacheado(
            "esportes", 6 * 3600,
            lambda: self._requisitar("sports/", {}, custo_estimado=0),
        ) or []

    def _esportes_candidatos(self, jogo, esportes=None):
        liga = jogo.get("liga") or jogo.get("competicao") or ""
        pais = jogo.get("pais") or ""
        candidatos = []
        for esporte in (
            self.esportes() if esportes is None else esportes
        ):
            chave = str(esporte.get("key") or "")
            if not chave.startswith("soccer_") or esporte.get("active") is False:
                continue
            titulo = esporte.get("title") or ""
            grupo = esporte.get("group") or ""
            score_liga = _similaridade(liga, titulo)
            texto = _normalizar(f"{titulo} {grupo} {chave}")
            # O catalogo normalmente informa apenas ``Soccer`` em ``group``;
            # o pais costuma estar no titulo ou na chave. Comparar somente com
            # o grupo descartava competicoes cobertas antes de conferir os
            # nomes dos dois times (ex.: Argentina, Mexico e Panama).
            pais_normalizado = _normalizar(pais)
            tokens_pais = set(pais_normalizado.split())
            tokens_texto = set(texto.split())
            pais_no_catalogo = bool(
                tokens_pais
                and tokens_pais <= tokens_texto
            )
            score_pais = max(
                _similaridade(pais, grupo.replace("Soccer", "")),
                _similaridade(pais, titulo),
                1.0 if pais_no_catalogo else 0.0,
            )
            tokens_liga = set(_normalizar(liga).split())
            sobreposicao = len(tokens_liga & tokens_texto) / max(
                len(tokens_liga), 1
            )
            score = 0.65 * score_liga + 0.20 * score_pais + 0.15 * sobreposicao
            if score_liga >= 0.42 or score_pais >= 0.90:
                candidatos.append((score, chave))
        candidatos.sort(reverse=True)
        return [chave for _, chave in candidatos[:3]]

    def diagnosticar_cobertura_competicao(self, jogo):
        """Pré-seleciona ligas cobertas sem reservar a amostra de odds.

        O catálogo de esportes tem custo estimado zero e fica em cache. Esta
        consulta deve acontecer antes de ``reservar_amostragem_referencia``;
        assim uma liga obviamente ausente não consome a pequena cota diária
        destinada à referência independente.
        """
        base = {
            "versao": "preselecao-cobertura-the-odds-api-v1",
            "executada": True,
            "coberta": None,
            "esportes_candidatos": [],
            "consulta_eventos": False,
            "consulta_odds": False,
            "reserva_consumida": False,
            "aplicacao_sinais": False,
            "telegram": False,
        }
        if not self.ativa:
            return {**base, "motivo": "fonte_desativada"}
        try:
            esportes = self.esportes()
        except Exception as erro:
            return {
                **base,
                "motivo": "catalogo_indisponivel",
                "erro": type(erro).__name__,
            }
        if not isinstance(esportes, list) or not esportes:
            return {**base, "motivo": "catalogo_indisponivel"}
        candidatos_brutos = self._esportes_candidatos(
            jogo, esportes=esportes
        )
        por_chave = {
            str(item.get("key") or ""): item for item in esportes
        }
        candidatos = [
            chave for chave in candidatos_brutos
            if _catalogo_compativel_com_pais(
                por_chave.get(chave) or {}, jogo.get("pais")
            )
        ]
        return {
            **base,
            "coberta": bool(candidatos),
            "esportes_candidatos": list(candidatos),
            "candidatos_descartados_pais": [
                chave for chave in candidatos_brutos
                if chave not in set(candidatos)
            ],
            "motivo": (
                "competicao_coberta"
                if candidatos
                else "competicao_nao_coberta_pais_incompativel"
                if candidatos_brutos
                else "competicao_nao_coberta"
            ),
        }

    def _eventos(self, esporte):
        return self._cacheado(
            ("eventos", esporte), 180,
            lambda: self._requisitar(
                f"sports/{esporte}/events",
                {"dateFormat": "iso"},
                custo_estimado=0,
            ),
        ) or []

    def _parear_evento(self, jogo, esportes=None):
        casa = jogo.get("mandante") or jogo.get("casa") or ""
        fora = jogo.get("visitante") or jogo.get("fora") or ""
        agora = datetime.fromtimestamp(self.relogio(), timezone.utc)
        opcoes = []
        for esporte in (
            self._esportes_candidatos(jogo)
            if esportes is None else esportes
        ):
            for evento in self._eventos(esporte):
                inicio = _instante(evento.get("commence_time"))
                if inicio is None:
                    continue
                minutos = (inicio - agora).total_seconds() / 60
                if minutos < -300 or minutos > 90:
                    continue
                direta = (
                    _similaridade(casa, evento.get("home_team")),
                    _similaridade(fora, evento.get("away_team")),
                )
                inversa = (
                    _similaridade(casa, evento.get("away_team")),
                    _similaridade(fora, evento.get("home_team")),
                )
                orientacao, par = (
                    ("direta", direta)
                    if sum(direta) >= sum(inversa)
                    else ("invertida", inversa)
                )
                score = sum(par) / 2
                if min(par) >= 0.76 and score >= 0.84:
                    opcoes.append((score, esporte, evento, orientacao))
        opcoes.sort(key=lambda item: item[0], reverse=True)
        if not opcoes:
            return None
        if len(opcoes) > 1 and opcoes[0][0] - opcoes[1][0] < 0.06:
            return None
        score, esporte, evento, orientacao = opcoes[0]
        return {
            "sport_key": esporte,
            "event_id": evento.get("id"),
            "similaridade": round(score, 4),
            "orientacao": orientacao,
            "home_team": evento.get("home_team"),
            "away_team": evento.get("away_team"),
        }

    def diagnosticar_cobertura_evento(
        self, jogo, *, esportes_candidatos=None
    ):
        """Confirma gratuitamente a partida antes de reservar odds.

        O endpoint de eventos tem custo estimado zero. O método exige o mesmo
        pareamento forte de times e janela de início usado na coleta paga, mas
        não consulta mercados, não reserva a amostragem e não toca nos sinais.
        """
        base = {
            "versao": "preselecao-evento-the-odds-api-v1",
            "executada": True,
            "pareado": None,
            "esportes_candidatos": [],
            "consulta_eventos": False,
            "consulta_odds": False,
            "reserva_consumida": False,
            "custo_estimado": 0,
            "aplicacao_sinais": False,
            "telegram": False,
        }
        if not self.ativa:
            return {**base, "motivo": "fonte_desativada"}
        if esportes_candidatos is None:
            cobertura = self.diagnosticar_cobertura_competicao(jogo)
            if cobertura.get("coberta") is not True:
                return {
                    **base,
                    "pareado": False,
                    "motivo": cobertura.get("motivo")
                    or "competicao_nao_coberta",
                }
            esportes_candidatos = cobertura.get(
                "esportes_candidatos"
            ) or []
        esportes = [
            str(item).strip() for item in (esportes_candidatos or [])
            if str(item).strip().startswith("soccer_")
        ]
        base["esportes_candidatos"] = list(esportes)
        if not esportes:
            return {
                **base,
                "pareado": False,
                "motivo": "competicao_nao_coberta",
            }
        base["consulta_eventos"] = True
        try:
            pareamento = self._parear_evento(
                jogo, esportes=esportes
            )
        except Exception as erro:
            return {
                **base,
                "motivo": "falha_preselecao_evento",
                "erro": type(erro).__name__,
            }
        if not pareamento:
            return {
                **base,
                "pareado": False,
                "motivo": "evento_nao_encontrado",
            }
        return {
            **base,
            "pareado": True,
            "motivo": "evento_pareado",
            "sport_key": pareamento.get("sport_key"),
            "evento_externo_id": pareamento.get("event_id"),
            "similaridade": pareamento.get("similaridade"),
            "orientacao": pareamento.get("orientacao"),
            "mandante_observado": pareamento.get("home_team"),
            "visitante_observado": pareamento.get("away_team"),
        }

    def _odds_evento(self, pareamento, mercados):
        """Consulta um evento uma única vez para todos os mercados pedidos.

        A cobrança do provedor continua sendo por mercado/região, por isso o
        custo estimado usa a quantidade exata de mercados. Agrupar reduz
        rajadas, divergência temporal e exposição a 429 sem esconder custo.
        """
        if isinstance(mercados, str):
            mercados = [mercados]
        mercados = tuple(sorted({
            str(item).strip() for item in (mercados or ())
            if str(item).strip()
        }))
        if not mercados:
            return None
        parametro_mercados = ",".join(mercados)
        chave = (
            "odds", pareamento["sport_key"], pareamento["event_id"],
            mercados,
        )
        return self._cacheado(
            chave, 60,
            lambda: self._requisitar(
                f"sports/{pareamento['sport_key']}/events/"
                f"{pareamento['event_id']}/odds",
                {
                    "regions": self.regiao,
                    "markets": parametro_mercados,
                    "oddsFormat": "decimal",
                    "dateFormat": "iso",
                },
                custo_estimado=len(mercados),
            ),
        )

    def _ofertas(self, resposta, mercado):
        agora = datetime.fromtimestamp(self.relogio(), timezone.utc)
        por_bookmaker = {
            str(item.get("key")): item
            for item in (resposta or {}).get("bookmakers") or []
        }
        ordem = list(self.bookmakers) + [
            chave for chave in por_bookmaker if chave not in self.bookmakers
        ]
        escolhidas = {}
        for bookmaker in ordem:
            dados_bk = por_bookmaker.get(bookmaker)
            if not dados_bk:
                continue
            for dados_mercado in dados_bk.get("markets") or []:
                if dados_mercado.get("key") != mercado:
                    continue
                atualizado = _instante(dados_mercado.get("last_update"))
                if atualizado is None:
                    continue
                idade = max((agora - atualizado).total_seconds(), 0.0)
                if idade > self.frescor_maximo:
                    continue
                linhas = {}
                for item in dados_mercado.get("outcomes") or []:
                    nome = str(item.get("name") or "").casefold()
                    linha = _numero(item.get("point"))
                    preco = _numero(item.get("price"))
                    if nome not in ("over", "under") or linha is None or preco is None:
                        continue
                    linhas.setdefault(linha, {})[nome] = preco
                for linha, lados in linhas.items():
                    if linha in escolhidas or not {"over", "under"} <= set(lados):
                        continue
                    escolhidas[linha] = {
                        "linha": linha,
                        "over": lados["over"],
                        "under": lados["under"],
                        "fonte": FONTE,
                        "bookmaker": bookmaker,
                        "coletado_em": atualizado.isoformat(),
                        "recebido_em": agora.isoformat(),
                        "idade_segundos": round(idade, 3),
                        "cache": False,
                        "mercado_origem": mercado,
                    }
        return [escolhidas[linha] for linha in sorted(escolhidas)]

    def buscar_mercados(self, jogo, mercados_internos):
        diagnostico = {
            "ativa": self.ativa,
            "pareado": False,
            "consultados": [],
            "anexados": [],
            "fonte": FONTE,
        }
        if not self.ativa:
            return {"ao_vivo": []}, diagnostico
        solicitados = [
            nome for nome in MERCADOS_SUPORTADOS
            if nome in set(mercados_internos or ())
        ]
        diagnostico["solicitados"] = list(solicitados)
        if not solicitados:
            return {"ao_vivo": []}, diagnostico
        esportes = self._esportes_candidatos(jogo)
        diagnostico["esportes_candidatos"] = list(esportes)
        if not esportes:
            diagnostico["motivo"] = "competicao_nao_coberta"
            return {"ao_vivo": []}, diagnostico
        pareamento = self._parear_evento(jogo, esportes=esportes)
        if not pareamento:
            diagnostico["motivo"] = "evento_nao_encontrado"
            return {"ao_vivo": []}, diagnostico
        diagnostico["pareado"] = True
        diagnostico["similaridade"] = pareamento["similaridade"]
        diagnostico["sport_key"] = pareamento["sport_key"]
        diagnostico["evento_externo_id"] = pareamento["event_id"]
        diagnostico["orientacao"] = pareamento["orientacao"]
        diagnostico["mandante_observado"] = pareamento["home_team"]
        diagnostico["visitante_observado"] = pareamento["away_team"]
        mercados_api = [
            MERCADOS_SUPORTADOS[interno] for interno in solicitados
        ]
        resposta = self._odds_evento(pareamento, mercados_api)
        diagnostico["consulta_combinada"] = len(mercados_api) > 1
        diagnostico["custo_estimado_creditos"] = len(mercados_api)
        mercados_saida = []
        for interno in solicitados:
            mercado_api = MERCADOS_SUPORTADOS[interno]
            diagnostico["consultados"].append(mercado_api)
            ofertas = self._ofertas(resposta, mercado_api)
            if not ofertas:
                continue
            identidade_evento = {
                "schema": "identidade-evento-odd-v1",
                "confirmada": True,
                "fonte": FONTE,
                "evento_externo_id": str(pareamento["event_id"]),
                "orientacao": pareamento["orientacao"],
                "similaridade": pareamento["similaridade"],
                # Os nomes abaixo seguem a orientacao da partida interna.
                # Os nomes crus do provedor permanecem no diagnostico.
                "mandante_normalizado": (
                    jogo.get("mandante") or jogo.get("casa")
                ),
                "visitante_normalizado": (
                    jogo.get("visitante") or jogo.get("fora")
                ),
                "placar_normalizado": jogo.get("placar"),
                "metodo": "pareamento_forte_the_odds_api",
            }
            for oferta in ofertas:
                bookmaker = str(oferta.get("bookmaker") or "").strip()
                oferta["identidade_evento"] = dict(identidade_evento)
                oferta["origem_mercado"] = {
                    "schema": VERSAO_ORIGEM_MERCADO,
                    "fonte": FONTE,
                    "identificador": (
                        f"{pareamento['event_id']}:{mercado_api}:"
                        f"{bookmaker}"
                    ),
                    "nome": mercado_api,
                    "linha": oferta.get("linha"),
                    "lados": ["over", "under"],
                    "bookmaker": bookmaker,
                }
            if interno == "gol_ft":
                mercados_saida.append({
                    "categoria": "gols", "escopo": "total",
                    "tipo_mercado": "total", "formato": "duas_opcoes",
                    "ofertas": ofertas, "fonte": FONTE, "cache": False,
                })
            elif interno == "gol_ht":
                mercados_saida.append({
                    "categoria": "gols", "escopo": "total",
                    "tipo_mercado": "total", "formato": "duas_opcoes",
                    "ofertas": [], "ofertas_ht": ofertas,
                    "fonte": FONTE, "cache": False,
                })
            elif interno == "escanteios_ft_asiatico":
                mercados_saida.append({
                    "categoria": "escanteios", "escopo": "total",
                    "tipo_mercado": "asiatico", "formato": "duas_opcoes",
                    "ofertas": ofertas, "fonte": FONTE, "cache": False,
                })
            diagnostico["anexados"].append(interno)
        diagnostico["motivo"] = (
            "oferta_anexada"
            if diagnostico["anexados"]
            else "mercado_sem_oferta_fresca"
        )
        return {"ao_vivo": mercados_saida}, diagnostico

    def diagnostico(self):
        provedor = self._estado.get("provedor") or {}
        amostragem = self._estado.get("amostragem_referencia") or {}
        uso_amostragem = (
            int(amostragem.get("reservas", 0) or 0)
            if amostragem.get("dia") == self._dia() else 0
        )
        contagens_amostragem = (
            amostragem.get("contagens") or {}
            if amostragem.get("dia") == self._dia() else {}
        )
        circuito_aberto = self.relogio() < self._bloqueado_ate
        return {
            "ativa": self.ativa,
            "chave_configurada": bool(self.chave),
            "regiao": self.regiao,
            "consumo_dia": self._consumo_dia(),
            "limite_diario": self.limite_diario,
            "creditos_usados": provedor.get("usados"),
            "creditos_restantes": provedor.get("restante"),
            "reserva_mensal": self.reserva_mensal,
            "circuito_aberto": circuito_aberto,
            "controle_estado": {
                "saudavel": bool(self.controle_estado_saudavel),
                "origem": self.controle_estado_origem,
                "recuperado": bool(self.controle_estado_recuperado),
                "reparado": bool(self.controle_estado_reparado),
                "revisao": int(self._estado.get("revisao", 0) or 0),
                "backup": self.arquivo_estado_backup.exists(),
                "fail_closed": not self.controle_estado_saudavel,
            },
            "circuito": {
                "versao": "circuito-the-odds-api-persistente-v1",
                "aberto": circuito_aberto,
                "falhas_consecutivas": int(self._falhas),
                "bloqueado_ate": (
                    float(self._bloqueado_ate) if circuito_aberto else None
                ),
                "restante_segundos": round(
                    max(self._bloqueado_ate - self.relogio(), 0.0), 3
                ),
                "motivo": self._circuito_motivo,
                "persistente": True,
                "recuperacao_automatica": True,
            },
            "amostragem_referencia": {
                "ativa": bool(self.amostragem_referencia_ativa),
                "uso_dia": uso_amostragem,
                "limite_diario": int(
                    self.amostragem_referencia_limite_diario
                ),
                "intervalo_segundos": float(
                    self.amostragem_referencia_intervalo
                ),
                "maximo_por_jogo_dia": int(
                    self.amostragem_referencia_maximo_jogo_dia
                ),
                "jogos_distintos_dia": len(contagens_amostragem),
                "maior_uso_jogo_dia": max(
                    (
                        int(valor)
                        for valor in contagens_amostragem.values()
                    ),
                    default=0,
                ),
                "aplicacao_sinais": False,
                "telegram": False,
                "promocao_automatica": False,
            },
        }
