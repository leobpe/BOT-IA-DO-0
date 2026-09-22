"""Cliente isolado e fail-closed para a TheStatsAPI.

O cliente fornece dados à coleta auxiliar e, quando o serviço o autoriza,
ao complemento oficial. Mantém cache, cota local, rate limit e circuit
breaker. Nenhuma credencial é incluída nas respostas.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.thestatsapi.com/api"
MAX_RESPOSTA_BYTES = 10 * 1024 * 1024

CACHE_JOGOS_AO_VIVO_SEGUNDOS = 30
CACHE_ESTATISTICAS_SEGUNDOS = 60
CACHE_ODDS_AO_VIVO_SEGUNDOS = 15
CACHE_NEGATIVO_STATS_404_SEGUNDOS = 300

# Plano Growth: 500.000 requisicoes/mes. O teto seguro permite ate 15.000
# chamadas uteis por dia (450.000 em 30 dias) e preserva 50.000 mensais para
# picos, reprocessamentos e diferencas entre meses. O limite por minuto segue
# conservador e tambem respeita qualquer limite menor anunciado pela API.
LIMITE_LOCAL_DIARIO_PADRAO = 16_667
RESERVA_LOCAL_DIARIA_PADRAO = 1_667
# Growth anuncia 300/min; usamos 80% para absorver concorrencia, variacao de
# janela e chamadas externas realizadas no mesmo token.
LIMITE_LOCAL_MINUTO_PADRAO = 240

FALHAS_PARA_ABRIR_CIRCUITO = 3
PAUSA_CIRCUITO_SEGUNDOS = 120
PAUSA_AUTENTICACAO_SEGUNDOS = 15 * 60
PAUSA_MAXIMA_PROVEDOR_SEGUNDOS = 60 * 60

_ID_PARTIDA_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_CHAVES_SENSIVEIS = {
    "api-key",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "access_token",
}


def _inteiro_env(nome, padrao, minimo, maximo):
    try:
        valor = int(os.getenv(nome, str(padrao)))
    except (TypeError, ValueError):
        return int(padrao)
    return min(max(valor, minimo), maximo)


def _agora_utc_epoch():
    return time.time()


def _dia_utc(epoch):
    return datetime.fromtimestamp(float(epoch), timezone.utc).strftime(
        "%Y-%m-%d"
    )


def _estado_uso_novo():
    return {"versao": 1, "dias": {}, "provedor": {}}


def _estado_uso_valido(dados):
    if not isinstance(dados, dict) or dados.get("versao") != 1:
        return False
    dias = dados.get("dias")
    provedor = dados.get("provedor")
    if not isinstance(dias, dict) or not isinstance(provedor, dict):
        return False
    for dia, quantidade in dias.items():
        if (
            not isinstance(dia, str)
            or len(dia) != 10
            or type(quantidade) is not int
            or quantidade < 0
        ):
            return False
    campos_inteiros = ("limite", "restante")
    for campo in campos_inteiros:
        valor = provedor.get(campo)
        if valor is not None and (type(valor) is not int or valor < 0):
            return False
    if (
        provedor.get("limite") is not None
        and provedor.get("restante") is not None
        and provedor["restante"] > provedor["limite"]
    ):
        return False
    for campo in ("observado_em", "bloqueado_ate"):
        valor = provedor.get(campo)
        if valor is not None and (
            isinstance(valor, bool)
            or not isinstance(valor, (int, float))
            or not math.isfinite(float(valor))
            or valor < 0
        ):
            return False
    return True


def _ler_json_valido(caminho):
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return dados if _estado_uso_valido(dados) else None


def _gravar_json_atomico(caminho, dados):
    caminho = Path(caminho)
    temporario = caminho.with_name(
        f"{caminho.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    texto = json.dumps(
        dados,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    temporario.write_text(texto, encoding="utf-8")
    ultimo_erro = None
    for tentativa in range(3):
        try:
            os.replace(temporario, caminho)
            return
        except OSError as erro:
            ultimo_erro = erro
            if tentativa < 2:
                time.sleep(0.01)
    try:
        temporario.unlink(missing_ok=True)
    except OSError:
        pass
    raise ultimo_erro


class TheStatsAPI:
    """Acesso minimo e isolado a dados ao vivo da TheStatsAPI.

    O limite diario configurado aqui e um teto de seguranca local, nao uma
    afirmacao sobre a franquia contratada com o provedor.
    """

    def __init__(
        self,
        pasta_projeto,
        *,
        abridor=None,
        relogio=None,
        timeout=15,
    ):
        chave_preferencial = (os.getenv("THESTATSAPI_KEY") or "").strip()
        chave_legada = (os.getenv("NOVA_FOOTBALL_API_KEY") or "").strip()
        self.chave = chave_preferencial or chave_legada
        self.variavel_chave = (
            "THESTATSAPI_KEY"
            if chave_preferencial
            else "NOVA_FOOTBALL_API_KEY" if chave_legada else None
        )
        self.timeout = min(max(float(timeout), 0.1), 60.0)
        self._abridor = abridor or urlopen
        self._relogio = relogio or _agora_utc_epoch
        self._trava = threading.RLock()

        self.limite_local_diario = _inteiro_env(
            "THESTATSAPI_LIMITE_DIARIO",
            LIMITE_LOCAL_DIARIO_PADRAO,
            1,
            1_000_000,
        )
        self.reserva_local_diaria = _inteiro_env(
            "THESTATSAPI_RESERVA_DIARIA",
            RESERVA_LOCAL_DIARIA_PADRAO,
            0,
            999_999,
        )
        self.limite_local_minuto = _inteiro_env(
            "THESTATSAPI_LIMITE_MINUTO",
            LIMITE_LOCAL_MINUTO_PADRAO,
            1,
            10_000,
        )
        self.cache_negativo_stats_404_segundos = _inteiro_env(
            "THESTATSAPI_CACHE_NEGATIVO_404_SEGUNDOS",
            CACHE_NEGATIVO_STATS_404_SEGUNDOS,
            30,
            3600,
        )
        self.limite_local_seguro = max(
            self.limite_local_diario - self.reserva_local_diaria,
            0,
        )

        pasta = Path(pasta_projeto)
        self.arquivo_uso = pasta / "thestatsapi_uso.json"
        self.arquivo_uso_backup = pasta / "thestatsapi_uso.json.bak"
        self.contador_saudavel = True
        self.contador_origem = "novo"
        self.uso = self._carregar_uso()

        self._cache = {}
        self._cache_negativo = {}
        self._chamadas_ultimo_minuto = deque()
        self.falhas_consecutivas = 0
        self.circuito_aberto_ate = 0.0
        self.ultimo_sucesso_em = None
        self.ultima_falha_em = None
        self.ultimo_erro = None

    @property
    def disponivel(self):
        return bool(self.chave)

    def _carregar_uso(self):
        principal_existe = self.arquivo_uso.exists()
        backup_existe = self.arquivo_uso_backup.exists()
        principal = (
            _ler_json_valido(self.arquivo_uso) if principal_existe else None
        )
        if principal is not None:
            self.contador_origem = "principal"
            return principal
        backup = (
            _ler_json_valido(self.arquivo_uso_backup)
            if backup_existe
            else None
        )
        if backup is not None:
            self.contador_origem = "backup"
            return backup
        if not principal_existe and not backup_existe:
            return _estado_uso_novo()

        # Nao arriscar chamadas se o contador persistente perdeu integridade.
        self.contador_saudavel = False
        self.contador_origem = "corrompido"
        agora = float(self._relogio())
        estado = _estado_uso_novo()
        estado["dias"][_dia_utc(agora)] = self.limite_local_seguro
        return estado

    def _salvar_uso(self):
        try:
            anterior = _ler_json_valido(self.arquivo_uso)
            if anterior is not None:
                _gravar_json_atomico(self.arquivo_uso_backup, anterior)
            _gravar_json_atomico(self.arquivo_uso, self.uso)
            if not self.arquivo_uso_backup.exists():
                _gravar_json_atomico(self.arquivo_uso_backup, self.uso)
        except OSError:
            self.contador_saudavel = False
            self.contador_origem = "falha_persistencia"
            return False
        self.contador_origem = "principal"
        return True

    def _sanitizar_texto(self, valor):
        texto = str(valor)
        if self.chave:
            texto = texto.replace(self.chave, "[REMOVIDO]")
        return _BEARER_RE.sub("Bearer [REMOVIDO]", texto)

    def sanitizar(self, valor):
        """Remove credenciais de estruturas destinadas a log ou diagnostico."""
        if isinstance(valor, dict):
            resultado = {}
            for chave, item in valor.items():
                nome = str(chave)
                nome_normalizado = re.sub(r"[^a-z0-9]", "", nome.casefold())
                if (
                    nome.casefold() in _CHAVES_SENSIVEIS
                    or nome_normalizado in {
                        "apikey",
                        "xapikey",
                        "authorization",
                        "password",
                        "secret",
                        "token",
                        "accesstoken",
                        "refreshtoken",
                    }
                ):
                    resultado[nome] = "[REMOVIDO]"
                else:
                    resultado[nome] = self.sanitizar(item)
            return resultado
        if isinstance(valor, list):
            return [self.sanitizar(item) for item in valor]
        if isinstance(valor, tuple):
            return [self.sanitizar(item) for item in valor]
        if isinstance(valor, str):
            return self._sanitizar_texto(valor)
        if valor is None or isinstance(valor, (bool, int, float)):
            return valor
        return self._sanitizar_texto(valor)

    def _erro(
        self,
        codigo,
        mensagem,
        *,
        status_http=None,
        tentar_em=0,
        origem=None,
        cache=False,
        idade_segundos=0,
    ):
        return {
            "ok": False,
            "dados": None,
            "meta": {},
            "erro": {
                "codigo": str(codigo),
                "mensagem": self._sanitizar_texto(mensagem),
                "status_http": status_http,
                "tentar_novamente_em_segundos": max(
                    int(round(float(tentar_em or 0))), 0
                ),
            },
            "status_http": status_http,
            "origem": origem,
            "cache": bool(cache),
            "idade_segundos": round(
                max(float(idade_segundos or 0), 0.0), 3
            ),
            "cota": self.consumo_atual(),
        }

    def _resposta(self, corpo, *, origem, idade_segundos=0, status_http=200):
        corpo = self.sanitizar(corpo)
        if isinstance(corpo, dict) and "data" in corpo:
            dados = corpo.get("data")
            meta = corpo.get("meta")
            if not isinstance(meta, dict):
                meta = (
                    dados.get("meta", {})
                    if isinstance(dados, dict)
                    and isinstance(dados.get("meta"), dict)
                    else {}
                )
        else:
            dados = corpo
            meta = {}
        return {
            "ok": True,
            "dados": dados,
            "meta": meta,
            "erro": None,
            "status_http": int(status_http),
            "origem": origem,
            "cache": origem == "cache",
            "idade_segundos": round(max(float(idade_segundos), 0.0), 3),
            "cota": self.consumo_atual(),
        }

    def _limpar_janela_minuto(self, agora):
        limite = float(agora) - 60.0
        while (
            self._chamadas_ultimo_minuto
            and self._chamadas_ultimo_minuto[0] <= limite
        ):
            self._chamadas_ultimo_minuto.popleft()

    def _pode_chamar(self, agora):
        if not self.contador_saudavel:
            return "contador_inseguro", 0
        if self.limite_local_seguro <= 0:
            return "configuracao_cota_invalida", 0
        dia = _dia_utc(agora)
        if int(self.uso["dias"].get(dia, 0)) >= self.limite_local_seguro:
            return "cota_local_esgotada", 0
        self._limpar_janela_minuto(agora)
        if len(self._chamadas_ultimo_minuto) >= self.limite_local_minuto:
            espera = max(
                60.0 - (float(agora) - self._chamadas_ultimo_minuto[0]),
                0.0,
            )
            return "limite_minuto_local", espera
        if float(agora) < self.circuito_aberto_ate:
            return "circuito_aberto", self.circuito_aberto_ate - float(agora)
        provedor = self.uso.get("provedor") or {}
        bloqueado_ate = float(provedor.get("bloqueado_ate") or 0)
        if float(agora) < bloqueado_ate:
            return "limite_provedor", bloqueado_ate - float(agora)
        return None, 0

    def _registrar_chamada(self, agora):
        dia = _dia_utc(agora)
        self.uso["dias"][dia] = int(self.uso["dias"].get(dia, 0)) + 1
        self._chamadas_ultimo_minuto.append(float(agora))
        return self._salvar_uso()

    @staticmethod
    def _cabecalho(cabecalhos, *nomes):
        if cabecalhos is None:
            return None
        for nome in nomes:
            try:
                valor = cabecalhos.get(nome)
            except AttributeError:
                return None
            if valor is not None:
                return str(valor).strip()
        return None

    @classmethod
    def _inteiro_cabecalho(cls, cabecalhos, *nomes):
        valor = cls._cabecalho(cabecalhos, *nomes)
        try:
            resultado = int(valor)
        except (TypeError, ValueError):
            return None
        return resultado if resultado >= 0 else None

    def _espera_cabecalho(self, cabecalhos, agora):
        valor = self._cabecalho(cabecalhos, "Retry-After", "retry-after")
        if valor is None:
            return 0.0
        try:
            espera = float(valor)
        except (TypeError, ValueError):
            try:
                destino = parsedate_to_datetime(valor)
                if destino.tzinfo is None:
                    destino = destino.replace(tzinfo=timezone.utc)
                espera = destino.timestamp() - float(agora)
            except (TypeError, ValueError, OverflowError):
                return 0.0
        return min(max(espera, 0.0), PAUSA_MAXIMA_PROVEDOR_SEGUNDOS)

    def _observar_limites_provedor(self, cabecalhos, agora):
        limite = self._inteiro_cabecalho(
            cabecalhos,
            "X-RateLimit-Limit",
            "RateLimit-Limit",
            "X-RateLimit-Requests-Limit",
        )
        restante = self._inteiro_cabecalho(
            cabecalhos,
            "X-RateLimit-Remaining",
            "RateLimit-Remaining",
            "X-RateLimit-Requests-Remaining",
        )
        espera = self._espera_cabecalho(cabecalhos, agora)
        provedor = {
            "observado_em": float(agora),
            "limite": limite,
            "restante": restante,
            "bloqueado_ate": 0.0,
        }
        if restante == 0 or espera > 0:
            provedor["bloqueado_ate"] = float(agora) + max(espera, 60.0)
        self.uso["provedor"] = provedor
        self._salvar_uso()

    def _registrar_sucesso(self, agora):
        self.falhas_consecutivas = 0
        self.circuito_aberto_ate = 0.0
        self.ultimo_sucesso_em = float(agora)
        self.ultimo_erro = None

    def _registrar_falha(self, codigo, agora, *, pausa=0, conta=True):
        self.ultima_falha_em = float(agora)
        self.ultimo_erro = str(codigo)
        if conta:
            self.falhas_consecutivas += 1
        if pausa > 0:
            self.circuito_aberto_ate = max(
                self.circuito_aberto_ate,
                float(agora) + min(
                    float(pausa), PAUSA_MAXIMA_PROVEDOR_SEGUNDOS
                ),
            )
        elif self.falhas_consecutivas >= FALHAS_PARA_ABRIR_CIRCUITO:
            self.circuito_aberto_ate = max(
                self.circuito_aberto_ate,
                float(agora) + PAUSA_CIRCUITO_SEGUNDOS,
            )

    def _ler_cache(self, chave, ttl, agora):
        item = self._cache.get(chave)
        if item is None:
            return None
        idade = float(agora) - float(item["em"])
        if idade < 0 or idade >= float(ttl):
            self._cache.pop(chave, None)
            return None
        return self._resposta(
            item["corpo"], origem="cache", idade_segundos=idade
        )

    def _salvar_cache(self, chave, corpo, agora):
        self._cache[chave] = {
            "em": float(agora),
            "corpo": self.sanitizar(corpo),
        }

    def _ler_cache_negativo(self, chave, agora):
        item = self._cache_negativo.get(chave)
        if item is None:
            return None
        idade = float(agora) - float(item["em"])
        ttl = float(item["ttl"])
        if idade < 0 or idade >= ttl:
            self._cache_negativo.pop(chave, None)
            return None
        return self._erro(
            item["codigo"],
            item["mensagem"],
            status_http=item.get("status_http"),
            tentar_em=max(ttl - idade, 0.0),
            origem="cache_negativo",
            cache=True,
            idade_segundos=idade,
        )

    def _salvar_cache_negativo_stats_404(self, chave, caminho, agora):
        if not (
            caminho.endswith("/live-stats") or caminho.endswith("/stats")
        ):
            return
        self._cache_negativo[chave] = {
            "em": float(agora),
            "ttl": float(self.cache_negativo_stats_404_segundos),
            "codigo": "http_404",
            "mensagem": "Estatisticas ainda indisponiveis no provedor.",
            "status_http": 404,
        }

    def _get(self, caminho, parametros, *, ttl):
        if not isinstance(caminho, str) or not caminho.startswith("/football/"):
            return self._erro("endpoint_invalido", "Endpoint nao permitido.")
        parametros = {
            str(chave): valor
            for chave, valor in (parametros or {}).items()
            if valor is not None
        }
        chave_cache = (
            caminho,
            json.dumps(parametros, sort_keys=True, separators=(",", ":")),
        )
        with self._trava:
            agora = float(self._relogio())
            cache = self._ler_cache(chave_cache, ttl, agora)
            if cache is not None:
                return cache
            cache_negativo = self._ler_cache_negativo(chave_cache, agora)
            if cache_negativo is not None:
                return cache_negativo
            if not self.disponivel:
                return self._erro(
                    "sem_chave", "Credencial da TheStatsAPI nao configurada."
                )
            motivo, espera = self._pode_chamar(agora)
            if motivo:
                mensagens = {
                    "contador_inseguro": "Contador local da API sem integridade.",
                    "configuracao_cota_invalida": "Reserva local invalida a cota segura.",
                    "cota_local_esgotada": "Cota local segura atingida.",
                    "limite_minuto_local": "Limite local por minuto atingido.",
                    "circuito_aberto": "Circuit breaker temporariamente ativo.",
                    "limite_provedor": "Provedor solicitou uma pausa temporaria.",
                }
                return self._erro(
                    motivo, mensagens.get(motivo, "Chamada temporariamente bloqueada."),
                    tentar_em=espera,
                )
            # A tentativa pode ser cobrada mesmo se a rede falhar.
            if not self._registrar_chamada(agora):
                return self._erro(
                    "contador_inseguro",
                    "Nao foi possivel persistir o contador local.",
                )

        consulta = urlencode(parametros, doseq=True)
        url = f"{BASE_URL}{caminho}"
        if consulta:
            url = f"{url}?{consulta}"
        requisicao = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.chave}",
                "Accept": "application/json",
                "User-Agent": "PackBall-shadow-validator/1.0",
            },
            method="GET",
        )

        try:
            with self._abridor(requisicao, timeout=self.timeout) as resposta:
                corpo_bytes = resposta.read(MAX_RESPOSTA_BYTES + 1)
                cabecalhos = getattr(resposta, "headers", None)
                status_http = int(getattr(resposta, "status", 200) or 200)
            if len(corpo_bytes) > MAX_RESPOSTA_BYTES:
                raise ValueError("resposta_excedeu_limite")
            corpo = json.loads(corpo_bytes.decode("utf-8"))
            if not isinstance(corpo, (dict, list)):
                raise ValueError("formato_json_invalido")
        except HTTPError as erro:
            status = int(getattr(erro, "code", 0) or 0)
            cabecalhos = getattr(erro, "headers", None)
            agora_falha = float(self._relogio())
            espera = self._espera_cabecalho(cabecalhos, agora_falha)
            if status == 429:
                espera = max(espera, 60.0)
                codigo = "http_429"
                mensagem = "Limite de requisicoes do provedor atingido."
            elif status in (401, 403):
                espera = max(espera, PAUSA_AUTENTICACAO_SEGUNDOS)
                codigo = f"http_{status}"
                mensagem = "Credencial recusada pelo provedor."
            elif status >= 500:
                codigo = "erro_provedor"
                mensagem = "Provedor temporariamente indisponivel."
            else:
                codigo = f"http_{status or 'erro'}"
                mensagem = "Solicitacao recusada pelo provedor."
            with self._trava:
                self._observar_limites_provedor(cabecalhos, agora_falha)
                self._registrar_falha(
                    codigo,
                    agora_falha,
                    pausa=espera,
                    conta=status >= 500 or status == 429,
                )
                if status == 404:
                    self._salvar_cache_negativo_stats_404(
                        chave_cache, caminho, agora_falha
                    )
            return self._erro(
                codigo,
                mensagem,
                status_http=status or None,
                tentar_em=espera,
            )
        except (URLError, TimeoutError) as erro:
            agora_falha = float(self._relogio())
            codigo = (
                "timeout" if isinstance(erro, TimeoutError) else "erro_rede"
            )
            with self._trava:
                self._registrar_falha(codigo, agora_falha)
            return self._erro(
                codigo, "Falha temporaria de comunicacao com o provedor."
            )
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            agora_falha = float(self._relogio())
            with self._trava:
                self._registrar_falha("resposta_invalida", agora_falha)
            return self._erro(
                "resposta_invalida", "Resposta invalida recebida do provedor."
            )

        agora_sucesso = float(self._relogio())
        if (
            isinstance(corpo, dict)
            and corpo.get("success") is False
        ):
            with self._trava:
                self._observar_limites_provedor(cabecalhos, agora_sucesso)
                self._registrar_falha(
                    "erro_provedor_payload", agora_sucesso, conta=False
                )
            return self._erro(
                "erro_provedor_payload",
                "O provedor devolveu uma resposta de erro.",
                status_http=status_http,
            )

        with self._trava:
            self._observar_limites_provedor(cabecalhos, agora_sucesso)
            self._registrar_sucesso(agora_sucesso)
            self._salvar_cache(chave_cache, corpo, agora_sucesso)
        return self._resposta(
            corpo, origem="rede", status_http=status_http
        )

    @staticmethod
    def _id_partida_valido(match_id):
        return bool(_ID_PARTIDA_RE.fullmatch(str(match_id or "").strip()))

    def _erro_id_partida(self):
        return self._erro(
            "id_partida_invalido",
            "Identificador de partida invalido.",
        )

    def jogos_ao_vivo(self, *, pagina=1, por_pagina=100):
        try:
            pagina = int(pagina)
            por_pagina = int(por_pagina)
        except (TypeError, ValueError):
            return self._erro(
                "paginacao_invalida", "Paginacao deve usar numeros inteiros."
            )
        if pagina < 1 or not 1 <= por_pagina <= 100:
            return self._erro(
                "paginacao_invalida",
                "Pagina deve ser positiva e por_pagina deve ficar entre 1 e 100.",
            )
        return self._get(
            "/football/matches",
            {"status": "live", "page": pagina, "per_page": por_pagina},
            ttl=CACHE_JOGOS_AO_VIVO_SEGUNDOS,
        )

    def estatisticas_partida(self, match_id):
        """Busca estatisticas consolidadas fora do jogo ao vivo via /stats."""
        match_id = str(match_id or "").strip()
        if not self._id_partida_valido(match_id):
            return self._erro_id_partida()
        return self._get(
            f"/football/matches/{match_id}/stats",
            {},
            ttl=CACHE_ESTATISTICAS_SEGUNDOS,
        )

    def estatisticas_ao_vivo(self, match_id):
        """Busca o snapshot em andamento via /live-stats.

        A TheStatsAPI responde 409 MATCH_IS_LIVE quando /stats e usado
        durante uma partida. Manter rotas separadas evita esse desperdicio.
        """
        match_id = str(match_id or "").strip()
        if not self._id_partida_valido(match_id):
            return self._erro_id_partida()
        return self._get(
            f"/football/matches/{match_id}/live-stats",
            {},
            ttl=CACHE_ESTATISTICAS_SEGUNDOS,
        )

    def odds_ao_vivo(self, match_id):
        match_id = str(match_id or "").strip()
        if not self._id_partida_valido(match_id):
            return self._erro_id_partida()
        return self._get(
            f"/football/matches/{match_id}/odds/live",
            {},
            ttl=CACHE_ODDS_AO_VIVO_SEGUNDOS,
        )

    def consumo_atual(self):
        with self._trava:
            agora = float(self._relogio())
            dia = _dia_utc(agora)
            usado = int(self.uso.get("dias", {}).get(dia, 0))
            self._limpar_janela_minuto(agora)
            return {
                "dia_utc": dia,
                "usado_local_dia": usado,
                "limite_local_diario": self.limite_local_diario,
                "reserva_local_diaria": self.reserva_local_diaria,
                "limite_local_seguro": self.limite_local_seguro,
                "restante_local_seguro": max(
                    self.limite_local_seguro - usado, 0
                ),
                "chamadas_ultimo_minuto": len(
                    self._chamadas_ultimo_minuto
                ),
                "limite_local_minuto": self.limite_local_minuto,
                "contador_saudavel": self.contador_saudavel,
                "contador_origem": self.contador_origem,
                "provedor": self.sanitizar(self.uso.get("provedor") or {}),
            }

    def diagnostico(self):
        agora = float(self._relogio())
        restante_circuito = max(self.circuito_aberto_ate - agora, 0.0)
        return {
            "provedor": "thestatsapi",
            "base_url": BASE_URL,
            "integracao": "cliente_isolado_fail_closed",
            "desligar_com": "THESTATSAPI_SOMBRA_ATIVA=0",
            "aplicacao_sinais": False,
            "telegram": False,
            "calibracao": False,
            "chave_configurada": self.disponivel,
            "variavel_chave": self.variavel_chave,
            "circuito_aberto": restante_circuito > 0,
            "circuito_restante_segundos": round(restante_circuito, 1),
            "falhas_consecutivas": self.falhas_consecutivas,
            "ultimo_erro": self.ultimo_erro,
            "ultimo_sucesso_em": self.ultimo_sucesso_em,
            "ultima_falha_em": self.ultima_falha_em,
            "itens_cache": len(self._cache),
            "itens_cache_negativo": len(self._cache_negativo),
            "cache_negativo_stats_404_segundos": (
                self.cache_negativo_stats_404_segundos
            ),
            "consumo": self.consumo_atual(),
        }

    def limpar_cache(self):
        with self._trava:
            quantidade = len(self._cache) + len(self._cache_negativo)
            self._cache.clear()
            self._cache_negativo.clear()
            return quantidade
