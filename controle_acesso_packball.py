import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from processo_monitor import gravar_json_atomico


VERSAO_EXPERIMENTO_RITMO = "ritmo-packball-v3"
VERSAO_EXPERIMENTO_RITMO_LEGADA = "ritmo-packball-v2"


class PackBallBloqueadoError(RuntimeError):
    pass


class PackBallPausaPreventivaError(PackBallBloqueadoError):
    pass


class ControleAcessoPackBall:
    def __init__(
        self, caminho_estado, intervalo_minimo_segundos=12.0,
        cooldown_minutos=15, maximo_por_janela=24,
        janela_segundos=600, relogio=None, dormir=None, agora_fn=None,
        experimento_capacidade=False,
        intervalo_rollback_segundos=12.0,
        maximo_rollback_por_janela=24,
        distribuir_janela=False,
        margem_distribuicao_segundos=0.5,
    ):
        self.caminho_estado = Path(caminho_estado)
        self.intervalo_configurado_segundos = max(
            float(intervalo_minimo_segundos), 1.0
        )
        self.intervalo_capacidade_segundos = (
            self.intervalo_configurado_segundos
        )
        self.intervalo_minimo_segundos = (
            self.intervalo_configurado_segundos
        )
        self.cooldown_minutos = max(int(cooldown_minutos), 2)
        self.maximo_por_janela = max(int(maximo_por_janela), 1)
        self.maximo_capacidade_por_janela = self.maximo_por_janela
        self.experimento_capacidade = bool(experimento_capacidade)
        self.intervalo_rollback_segundos = max(
            float(intervalo_rollback_segundos), 1.0
        )
        self.maximo_rollback_por_janela = max(
            int(maximo_rollback_por_janela), 1
        )
        self.janela_segundos = max(int(janela_segundos), 60)
        self.distribuir_janela = bool(distribuir_janela)
        self.margem_distribuicao_segundos = max(
            float(margem_distribuicao_segundos), 0.0
        )
        self._aplicar_distribuicao_janela()
        self._validar_rollback_conservador()
        self.relogio = relogio or time.monotonic
        self.dormir = dormir or time.sleep
        self.agora_fn = agora_fn or datetime.now
        self._ultima_navegacao = None

    def _aplicar_distribuicao_janela(self):
        intervalo = self.intervalo_configurado_segundos
        if self.distribuir_janela:
            intervalo = max(
                intervalo,
                self.janela_segundos / self.maximo_por_janela
                + self.margem_distribuicao_segundos,
            )
        self.intervalo_minimo_segundos = intervalo

    def _restaurar_capacidade_configurada(self):
        self.intervalo_configurado_segundos = (
            self.intervalo_capacidade_segundos
        )
        self.maximo_por_janela = self.maximo_capacidade_por_janela
        self._aplicar_distribuicao_janela()

    def _validar_rollback_conservador(self):
        if not self.experimento_capacidade:
            return
        intervalo_rollback_efetivo = self.intervalo_rollback_segundos
        if self.distribuir_janela:
            intervalo_rollback_efetivo = max(
                intervalo_rollback_efetivo,
                self.janela_segundos / self.maximo_rollback_por_janela
                + self.margem_distribuicao_segundos,
            )
        if (
            intervalo_rollback_efetivo < self.intervalo_minimo_segundos
            or self.maximo_rollback_por_janela > self.maximo_por_janela
        ):
            raise ValueError(
                "Rollback PackBall inseguro: os limites de recuperacao "
                "devem ser iguais ou mais conservadores que o ritmo normal"
            )

    def _aplicar_rollback_persistido(self, dados):
        if not (
            self.experimento_capacidade
            and dados.get("rollback_capacidade_ativo") is True
        ):
            return False
        self.intervalo_configurado_segundos = (
            self.intervalo_rollback_segundos
        )
        self.maximo_por_janela = self.maximo_rollback_por_janela
        self._aplicar_distribuicao_janela()
        return True

    def _registrar_rollback_capacidade(self, dados, motivo):
        if not self.experimento_capacidade:
            return False
        agora = self.agora_fn().replace(microsecond=0)
        dados.update({
            "rollback_capacidade_ativo": True,
            "rollback_capacidade_em": agora.isoformat(),
            "rollback_capacidade_motivo": str(motivo),
            "intervalo_navegacao_efetivo_segundos": (
                self.intervalo_rollback_segundos
            ),
            "maximo_navegacoes_efetivo_janela": (
                self.maximo_rollback_por_janela
            ),
        })
        self._aplicar_rollback_persistido(dados)
        return True

    @contextmanager
    def _trava_global(self):
        caminho = self.caminho_estado.with_suffix(
            self.caminho_estado.suffix + ".lock"
        )
        caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo = caminho.open("a+b")
        try:
            arquivo.seek(0, os.SEEK_END)
            if arquivo.tell() == 0:
                arquivo.write(b"\0")
                arquivo.flush()
            arquivo.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                arquivo.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)
        finally:
            arquivo.close()

    def _ler_estado(self):
        try:
            dados = json.loads(
                self.caminho_estado.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return dados if isinstance(dados, dict) else {}

    def _gravar_estado(self, dados):
        gravar_json_atomico(self.caminho_estado, dados)

    def estado_atual(self):
        dados = self._ler_estado()
        if not self._aplicar_rollback_persistido(dados):
            self._restaurar_capacidade_configurada()
        limites = []
        for campo in ("bloqueado_ate", "pausado_ate"):
            try:
                limite = datetime.fromisoformat(dados.get(campo))
            except (TypeError, ValueError):
                limite = None
            if limite is not None:
                limites.append(limite)
        limite = max(limites) if limites else None
        agora = self.agora_fn()
        ativo = bool(limite and agora < limite)
        restante = max((limite - agora).total_seconds(), 0) if limite else 0
        return {
            **dados,
            "ativo": ativo,
            "restante_segundos": round(restante, 1),
            "distribuicao_janela_ativa": self.distribuir_janela,
            "intervalo_navegacao_efetivo_segundos": round(
                self.intervalo_minimo_segundos, 3
            ),
            "maximo_navegacoes_efetivo_janela": self.maximo_por_janela,
            "janela_navegacoes_segundos": self.janela_segundos,
        }

    def antes_navegacao(self, autorizar_login_manual=False):
        with self._trava_global():
            estado = self.estado_atual()
            motivo = str(
                estado.get("motivo") or "pausa_seguranca"
            )
            bloqueio_site_ativo = False
            try:
                bloqueado_ate = datetime.fromisoformat(
                    estado.get("bloqueado_ate")
                )
                bloqueio_site_ativo = self.agora_fn() < bloqueado_ate
            except (TypeError, ValueError):
                pass
            bypass_login_manual = bool(
                autorizar_login_manual
                and estado["ativo"]
                and motivo == "falha_login_packball"
                and not bloqueio_site_ativo
            )
            if estado["ativo"] and not bypass_login_manual:
                raise PackBallPausaPreventivaError(
                    "Pausa de segurança do PackBall ativa "
                    f"(motivo: {motivo}); aguarde "
                    f"{estado['restante_segundos']:.0f}s."
                )
            agora_data = self.agora_fn()
            inicio_janela = agora_data - timedelta(
                seconds=self.janela_segundos
            )
            recentes = []
            for valor in estado.get("navegacoes_recentes") or []:
                try:
                    instante = datetime.fromisoformat(valor)
                except (TypeError, ValueError):
                    continue
                if instante > inicio_janela and instante <= agora_data:
                    recentes.append(instante)
            espera_cota = 0.0
            if (
                len(recentes) >= self.maximo_por_janela
                and self.distribuir_janela
            ):
                espera_cota = max(
                    (
                        min(recentes)
                        + timedelta(seconds=self.janela_segundos)
                        - agora_data
                    ).total_seconds()
                    + self.margem_distribuicao_segundos,
                    0.0,
                )
            elif len(recentes) >= self.maximo_por_janela:
                pausado_ate = min(recentes) + timedelta(
                    seconds=self.janela_segundos
                )
                dados = self._ler_estado()
                dados.update({
                    "pausado_ate": pausado_ate.isoformat(),
                    "motivo": "limite_local_navegacoes",
                    "navegacoes_recentes": [
                        item.isoformat() for item in recentes
                    ],
                })
                self._gravar_estado(dados)
                restante = max(
                    (pausado_ate - agora_data).total_seconds(), 1
                )
                raise PackBallPausaPreventivaError(
                    "Pausa preventiva do PackBall: teto local de "
                    f"{self.maximo_por_janela} navegações por "
                    f"{self.janela_segundos // 60}min atingido; "
                    f"aguarde {restante:.0f}s."
                )
            try:
                ultima_global = datetime.fromisoformat(
                    estado.get("ultima_navegacao_em")
                )
            except (TypeError, ValueError):
                ultima_global = None
            espera_global = 0.0
            if ultima_global is not None:
                espera_global = self.intervalo_minimo_segundos - (
                    agora_data - ultima_global
                ).total_seconds()
            agora_relogio = self.relogio()
            espera_local = 0.0
            if self._ultima_navegacao is not None:
                espera_local = self.intervalo_minimo_segundos - (
                    agora_relogio - self._ultima_navegacao
                )
            espera = max(
                espera_global, espera_local, espera_cota, 0.0
            )
            if espera > 0:
                self.dormir(espera)
            self._ultima_navegacao = self.relogio()
            dados = self._ler_estado()
            instante_navegacao = self.agora_fn().replace(microsecond=0)
            inicio_janela_atualizado = instante_navegacao - timedelta(
                seconds=self.janela_segundos
            )
            recentes = [
                item for item in recentes
                if item > inicio_janela_atualizado
                and item <= instante_navegacao
            ]
            dados["ultima_navegacao_em"] = instante_navegacao.isoformat()
            dados["distribuicao_janela_ativa"] = self.distribuir_janela
            dados["intervalo_navegacao_efetivo_segundos"] = round(
                self.intervalo_minimo_segundos, 3
            )
            dados["maximo_navegacoes_efetivo_janela"] = (
                self.maximo_por_janela
            )
            dados["janela_navegacoes_segundos"] = self.janela_segundos
            dados["navegacoes_recentes"] = [
                item.isoformat() for item in recentes
            ] + [instante_navegacao.isoformat()]
            self._gravar_estado(dados)

    @staticmethod
    def _segundos_informados(texto):
        correspondencia = re.search(
            r"aguarde\s+(\d+)\s+segundos?", str(texto or ""), re.I
        )
        return int(correspondencia.group(1)) if correspondencia else None

    @staticmethod
    def pagina_bloqueada(texto):
        normalizado = " ".join(str(texto or "").lower().split())
        return (
            "muitas solicitações em um curto período" in normalizado
            or "muitas solicitacoes em um curto periodo" in normalizado
            or (
                "aguarde" in normalizado
                and "segundos" in normalizado
                and "packball@packball.com" in normalizado
            )
        )

    def validar_pagina(self, pagina):
        try:
            texto = pagina.evaluate(
                "() => document.body?.innerText || ''"
            )
        except Exception:
            return
        if not isinstance(texto, str) or not self.pagina_bloqueada(texto):
            return
        agora = self.agora_fn().replace(microsecond=0)
        segundos_site = self._segundos_informados(texto) or 0
        cooldown = max(self.cooldown_minutos * 60, segundos_site + 60)
        bloqueado_ate = agora + timedelta(seconds=cooldown)
        with self._trava_global():
            dados = self._ler_estado()
            dados.update({
                "detectado_em": agora.isoformat(),
                "bloqueado_ate": bloqueado_ate.isoformat(),
                "segundos_informados_site": segundos_site,
                "motivo": "excesso_solicitacoes_packball",
            })
            self._registrar_rollback_capacidade(
                dados, "excesso_solicitacoes_packball"
            )
            self._gravar_estado(dados)
        raise PackBallBloqueadoError(
            "PackBall bloqueou temporariamente por excesso de solicitações; "
            f"circuit breaker ativo até {bloqueado_ate.isoformat()}."
        )

    def ativar_pausa(self, motivo, minutos=360):
        agora = self.agora_fn().replace(microsecond=0)
        pausado_ate = agora + timedelta(minutes=max(int(minutos), 2))
        with self._trava_global():
            dados = self._ler_estado()
            dados.update({
                "pausado_em": agora.isoformat(),
                "pausado_ate": pausado_ate.isoformat(),
                "motivo": str(motivo or "pausa_seguranca"),
            })
            if str(motivo) in (
                "excesso_solicitacoes_packball",
                "falha_login_packball",
            ):
                self._registrar_rollback_capacidade(dados, motivo)
            self._gravar_estado(dados)
        return pausado_ate

    def liberar_pausa_login_manual(self):
        with self._trava_global():
            dados = self._ler_estado()
            pausa_login = dados.get("motivo") == "falha_login_packball"
            rollback_login = bool(
                dados.get("rollback_capacidade_ativo") is True
                and dados.get("rollback_capacidade_motivo")
                == "falha_login_packball"
            )
            if not pausa_login and not rollback_login:
                return False
            agora = self.agora_fn().replace(microsecond=0).isoformat()
            if pausa_login:
                dados.pop("pausado_ate", None)
                dados.pop("pausado_em", None)
                dados.pop("motivo", None)
            if rollback_login:
                dados["ultimo_rollback_capacidade"] = {
                    "ativo_em": dados.get("rollback_capacidade_em"),
                    "motivo": dados.get("rollback_capacidade_motivo"),
                    "liberado_em": agora,
                    "liberado_por": "login_manual_confirmado",
                }
                dados.pop("rollback_capacidade_ativo", None)
                dados.pop("rollback_capacidade_em", None)
                dados.pop("rollback_capacidade_motivo", None)
                dados["capacidade_restaurada_em"] = agora
                dados["capacidade_restaurada_motivo"] = (
                    "login_manual_confirmado"
                )
                self._restaurar_capacidade_configurada()
            self._gravar_estado(dados)
            return True


def verificar_acesso_packball(caminho_estado, agora=None):
    agora = agora or datetime.now()
    try:
        estado = json.loads(
            Path(caminho_estado).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        estado = {}
    estado = estado if isinstance(estado, dict) else {}
    limites = []
    for campo in ("bloqueado_ate", "pausado_ate"):
        try:
            limite = datetime.fromisoformat(estado.get(campo))
        except (TypeError, ValueError):
            limite = None
        if limite is not None:
            limites.append(limite)
    limite = max(limites) if limites else None
    ativo = bool(limite and agora < limite)
    restante = max((limite - agora).total_seconds(), 0) if limite else 0
    return {
        **estado,
        "ativo": ativo,
        "restante_segundos": round(restante, 1),
        "saudavel": not ativo,
        "motivo_persistido": estado.get("motivo"),
        "motivo": (
            "circuit_breaker_packball_ativo" if ativo else None
        ),
    }


def auditar_ritmo_packball(
    caminho_estado,
    agora=None,
    exigir_distribuicao=False,
    tolerancia_intervalo_segundos=1.1,
    tolerancia_futuro_segundos=2.0,
):
    caminho_estado = Path(caminho_estado)
    try:
        dados = json.loads(caminho_estado.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {
            "saudavel": True,
            "avaliavel": False,
            "estado": "aguardando_telemetria",
            "motivos": [],
            "navegacoes_validas": 0,
        }
    agora = agora or datetime.now()
    try:
        intervalo = float(
            dados.get("intervalo_navegacao_efetivo_segundos")
        )
    except (TypeError, ValueError):
        intervalo = None
    try:
        maximo = int(dados.get("maximo_navegacoes_efetivo_janela"))
    except (TypeError, ValueError):
        maximo = None
    try:
        janela = int(dados.get("janela_navegacoes_segundos") or 600)
    except (TypeError, ValueError):
        janela = 600
    distribuicao = dados.get("distribuicao_janela_ativa") is True
    invalidas = 0
    futuras = 0
    instantes = []
    for valor in dados.get("navegacoes_recentes") or []:
        try:
            instante = datetime.fromisoformat(valor)
        except (TypeError, ValueError):
            invalidas += 1
            continue
        if instante > agora + timedelta(
            seconds=float(tolerancia_futuro_segundos)
        ):
            futuras += 1
            continue
        if instante > agora - timedelta(seconds=max(janela, 60)):
            instantes.append(instante)
    instantes.sort()
    intervalos = [
        (atual - anterior).total_seconds()
        for anterior, atual in zip(instantes, instantes[1:])
    ]
    violacoes_intervalo = (
        sum(
            diferenca + float(tolerancia_intervalo_segundos)
            < intervalo
            for diferenca in intervalos
        )
        if intervalo is not None and intervalo > 0 else 0
    )
    excesso_janela = (
        max(len(instantes) - maximo, 0)
        if maximo is not None and maximo > 0 else 0
    )
    motivos = []
    if exigir_distribuicao and not distribuicao:
        motivos.append("distribuicao_desativada")
    if intervalo is None or intervalo <= 0:
        motivos.append("intervalo_efetivo_invalido")
    if maximo is None or maximo <= 0:
        motivos.append("teto_janela_invalido")
    if invalidas:
        motivos.append("timestamps_invalidos")
    if futuras:
        motivos.append("timestamps_futuros")
    if violacoes_intervalo:
        motivos.append("intervalo_minimo_violado")
    if excesso_janela:
        motivos.append("teto_janela_excedido")
    avaliavel = bool(instantes) and intervalo is not None and maximo is not None
    return {
        "saudavel": not motivos,
        "avaliavel": avaliavel,
        "estado": (
            "seguro" if not motivos and avaliavel
            else "aguardando_telemetria" if not motivos
            else "inseguro"
        ),
        "motivos": motivos,
        "distribuicao_ativa": distribuicao,
        "intervalo_efetivo_segundos": intervalo,
        "intervalo_minimo_observado_segundos": (
            min(intervalos) if intervalos else None
        ),
        "intervalo_medio_observado_segundos": (
            round(sum(intervalos) / len(intervalos), 3)
            if intervalos else None
        ),
        "maximo_por_janela": maximo,
        "janela_segundos": janela,
        "navegacoes_validas": len(instantes),
        "timestamps_invalidos": invalidas,
        "timestamps_futuros": futuras,
        "violacoes_intervalo": violacoes_intervalo,
        "excesso_janela": excesso_janela,
    }


def _ler_eventos_rotacionados(caminho_log, copias=5):
    caminho_log = Path(caminho_log)
    caminhos = [
        Path(f"{caminho_log}.{indice}")
        for indice in range(max(int(copias), 0), 0, -1)
    ] + [caminho_log]
    eventos = []
    for caminho in caminhos:
        if not caminho.exists():
            continue
        try:
            linhas = caminho.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for linha in linhas:
            try:
                evento = json.loads(linha)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(evento, dict):
                eventos.append(evento)
    return eventos


def _chave_regime_ritmo(ciclo):
    ritmo = ciclo.get("ritmo_packball") or {}
    if ritmo.get("distribuicao_janela_ativa") is not True:
        return "anterior"
    try:
        intervalo = round(float(ritmo.get("intervalo_efetivo_segundos")), 3)
        maximo = int(ritmo.get("maximo_por_janela"))
        janela = int(ritmo.get("janela_segundos"))
    except (TypeError, ValueError):
        return "distribuido:configuracao_incompleta"
    return f"distribuido:{intervalo}:{maximo}:{janela}"


def _periodos_manutencao(eventos):
    periodos = []
    inicio = None
    for evento in sorted(
        eventos or [], key=lambda item: str(item.get("em") or "")
    ):
        try:
            instante = datetime.fromisoformat(str(evento.get("em") or ""))
        except (TypeError, ValueError):
            continue
        if evento.get("evento") == "modo_manutencao_solicitado":
            if inicio is None:
                inicio = instante
        elif evento.get("evento") == "modo_manutencao_liberado":
            if inicio is not None and instante > inicio:
                periodos.append((inicio, instante))
            inicio = None
    return periodos


def _sobreposicao_periodos(inicio, fim, periodos):
    total = 0.0
    ocorrencias = 0
    for inicio_pausa, fim_pausa in periodos or []:
        sobreposicao = (
            min(fim, fim_pausa) - max(inicio, inicio_pausa)
        ).total_seconds()
        if sobreposicao > 0:
            total += sobreposicao
            ocorrencias += 1
    return total, ocorrencias


def _resumir_ciclos_ritmo(ciclos, periodos_manutencao=None):
    ciclos = [
        ciclo for ciclo in ciclos
        if int(ciclo.get("tarefas_processadas") or 0) > 0
        and float(ciclo.get("duracao_segundos") or 0) > 0
    ]
    processadas = sum(
        int(ciclo.get("tarefas_processadas") or 0) for ciclo in ciclos
    )
    agendadas = sum(
        int(ciclo.get("tarefas_agendadas") or 0) for ciclo in ciclos
    )
    duracao_processamento = sum(
        float(ciclo.get("duracao_segundos") or 0) for ciclo in ciclos
    )
    duracao_periodo = duracao_processamento
    gaps_inativos_excluidos = 0
    duracao_inativa_excluida = 0.0
    pausas_manutencao_excluidas = 0
    duracao_manutencao_excluida = 0.0
    if ciclos:
        try:
            finais = [
                datetime.fromisoformat(ciclo["em"]) for ciclo in ciclos
            ]
            duracao_periodo = float(
                ciclos[0].get("duracao_segundos") or 0
            )
            for indice in range(1, len(ciclos)):
                duracao_atual = float(
                    ciclos[indice].get("duracao_segundos") or 0
                )
                intervalo = max(
                    (finais[indice] - finais[indice - 1]).total_seconds(),
                    duracao_atual,
                )
                manutencao, ocorrencias = _sobreposicao_periodos(
                    finais[indice - 1],
                    finais[indice],
                    periodos_manutencao,
                )
                if manutencao > 0:
                    intervalo = max(
                        intervalo - manutencao, duracao_atual
                    )
                    pausas_manutencao_excluidas += ocorrencias
                    duracao_manutencao_excluida += manutencao
                # Uma interrupção longa do processo não mede a velocidade da
                # coleta. Mantemos o tempo do primeiro ciclo após a volta, mas
                # retiramos o período em que não havia processo trabalhando.
                if intervalo > 3600:
                    gaps_inativos_excluidos += 1
                    duracao_inativa_excluida += max(
                        intervalo - duracao_atual, 0
                    )
                    intervalo = duracao_atual
                duracao_periodo += intervalo
        except (KeyError, TypeError, ValueError):
            duracao_periodo = duracao_processamento
            gaps_inativos_excluidos = 0
            duracao_inativa_excluida = 0.0
            pausas_manutencao_excluidas = 0
            duracao_manutencao_excluida = 0.0
    temporais = sum(
        int(
            (ciclo.get("cobertura_temporal") or {}).get(
                "partidas_com_historico"
            ) or 0
        )
        for ciclo in ciclos
    )
    janelas = {
        chave: sum(
            int(
                (
                    (ciclo.get("cobertura_temporal") or {}).get(
                        "janelas_disponiveis"
                    ) or {}
                ).get(chave) or 0
            )
            for ciclo in ciclos
        )
        for chave in ("5", "10", "15")
    }
    com_odds = sum(
        int(ciclo.get("tarefas_com_odds") or 0) for ciclo in ciclos
    )
    foco = sum(
        int(
            (ciclo.get("perfil_agendamento") or {}).get(
                "foco_processadas"
            ) or 0
        )
        for ciclo in ciclos
    )
    # A cobertura total varia muito quando a proporcao entre jogos em foco e
    # exploratorios muda. Este rendimento preserva a metrica historica e
    # normaliza a comparacao pelo trabalho prioritario efetivamente realizado.
    rendimento_temporal_por_foco = (
        round(temporais / foco, 4) if foco else None
    )
    foco_temporal = 0
    foco_com_telemetria = 0
    ciclos_com_telemetria_perfil = 0
    for ciclo in ciclos:
        perfil = (
            (ciclo.get("cobertura_temporal") or {})
            .get("por_perfil") or {}
        ).get("foco")
        if not isinstance(perfil, dict):
            continue
        ciclos_com_telemetria_perfil += 1
        foco_temporal += int(perfil.get("com_historico") or 0)
        foco_com_telemetria += int(perfil.get("processadas") or 0)
    return {
        "ciclos": len(ciclos),
        "primeiro_em": ciclos[0].get("em") if ciclos else None,
        "ultimo_em": ciclos[-1].get("em") if ciclos else None,
        "agendadas": agendadas,
        "processadas": processadas,
        "duracao_processamento_minutos": round(
            duracao_processamento / 60, 2
        ),
        "periodo_observado_minutos": round(duracao_periodo / 60, 2),
        "gaps_inativos_excluidos": gaps_inativos_excluidos,
        "duracao_inativa_excluida_minutos": round(
            duracao_inativa_excluida / 60, 2
        ),
        "pausas_manutencao_excluidas": pausas_manutencao_excluidas,
        "duracao_manutencao_excluida_minutos": round(
            duracao_manutencao_excluida / 60, 2
        ),
        "processadas_por_10_minutos": (
            round(processadas / duracao_periodo * 600, 2)
            if duracao_periodo else None
        ),
        "cobertura_temporal": (
            round(temporais / processadas, 4) if processadas else None
        ),
        "janelas_temporais": janelas,
        "cobertura_odds": (
            round(com_odds / processadas, 4) if processadas else None
        ),
        "foco_processadas": foco,
        "rendimento_temporal_por_foco": rendimento_temporal_por_foco,
        "cobertura_temporal_foco": (
            round(foco_temporal / foco_com_telemetria, 4)
            if foco_com_telemetria else None
        ),
        "telemetria_perfil_ciclos": ciclos_com_telemetria_perfil,
        "telemetria_perfil_completa": bool(
            ciclos and ciclos_com_telemetria_perfil == len(ciclos)
        ),
    }


def _ler_avaliacao_ritmo(caminho):
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _avaliar_experimento_ritmo_packball_legado(
    caminho_log,
    caminho_avaliacao,
    auditoria_ritmo=None,
    caminho_estado_acesso=None,
    agora=None,
    minimo_ciclos=12,
    minimo_minutos=45,
    retencao_minima_fluxo=0.75,
    retencao_minima_temporal=0.80,
    janela_base=12,
    janela_experimento=50,
):
    """Compara o ritmo distribuido com a base e preserva sua evidencia."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    eventos = _ler_eventos_rotacionados(caminho_log)
    ciclos = [
        evento for evento in eventos
        if evento.get("evento") == "ciclo_concluido"
        and int(evento.get("tarefas_processadas") or 0) > 0
        and float(evento.get("duracao_segundos") or 0) > 0
    ]
    atual = _ler_avaliacao_ritmo(caminho_avaliacao)
    periodos_manutencao = _periodos_manutencao(eventos)
    if not ciclos:
        resultado = {
            "versao": VERSAO_EXPERIMENTO_RITMO_LEGADA,
            "saudavel": True,
            "avaliavel": False,
            "estado": "aguardando_telemetria",
            "motivos": [],
            "atualizado_em": agora.isoformat(),
        }
        gravar_json_atomico(caminho_avaliacao, resultado)
        return resultado

    chave_atual = _chave_regime_ritmo(ciclos[-1])
    if not chave_atual.startswith("distribuido:"):
        resultado = {
            "versao": VERSAO_EXPERIMENTO_RITMO_LEGADA,
            "saudavel": True,
            "avaliavel": False,
            "estado": "inativo",
            "motivos": [],
            "regime_atual": chave_atual,
            "atualizado_em": agora.isoformat(),
        }
        gravar_json_atomico(caminho_avaliacao, resultado)
        return resultado

    indice_inicio = len(ciclos) - 1
    while (
        indice_inicio > 0
        and _chave_regime_ritmo(ciclos[indice_inicio - 1]) == chave_atual
    ):
        indice_inicio -= 1
    inicio_em = ciclos[indice_inicio].get("em")
    mesmo_experimento = (
        atual.get("versao") == VERSAO_EXPERIMENTO_RITMO_LEGADA
        and atual.get("regime_atual") == chave_atual
        and atual.get("iniciado_em") == inicio_em
    )
    if mesmo_experimento and isinstance(atual.get("base"), dict):
        base = atual["base"]
        historico = [
            item for item in (atual.get("historico") or [])
            if item.get("versao") == VERSAO_EXPERIMENTO_RITMO_LEGADA
        ]
    else:
        base = _resumir_ciclos_ritmo(
            ciclos[max(0, indice_inicio - int(janela_base)):indice_inicio],
            periodos_manutencao,
        )
        historico = [
            item for item in (atual.get("historico") or [])
            if item.get("versao") == VERSAO_EXPERIMENTO_RITMO_LEGADA
        ]
        if (
            atual.get("versao") == VERSAO_EXPERIMENTO_RITMO_LEGADA
            and atual.get("iniciado_em")
        ):
            historico.append({
                "versao": VERSAO_EXPERIMENTO_RITMO_LEGADA,
                "regime": atual.get("regime_atual"),
                "iniciado_em": atual.get("iniciado_em"),
                "encerrado_em": agora.isoformat(),
                "estado": atual.get("estado"),
                "base": atual.get("base"),
                "experimento": atual.get("experimento"),
            })
            historico = historico[-10:]

    ciclos_experimento = ciclos[indice_inicio:][-int(janela_experimento):]
    experimento = _resumir_ciclos_ritmo(
        ciclos_experimento, periodos_manutencao
    )
    try:
        inicio = datetime.fromisoformat(inicio_em)
        minutos_observados = max((agora - inicio).total_seconds() / 60, 0)
    except (TypeError, ValueError):
        minutos_observados = 0
    pausas = sum(
        evento.get("evento") == "ciclo_pausado_packball"
        and str(evento.get("em") or "") >= str(inicio_em or "")
        for evento in eventos
    )
    if mesmo_experimento:
        pausas = max(pausas, int(atual.get("pausas_packball") or 0))
    acesso = (
        _ler_avaliacao_ritmo(caminho_estado_acesso)
        if caminho_estado_acesso else {}
    )
    rollback_ativo = acesso.get("rollback_capacidade_ativo") is True
    auditoria_ritmo = dict(auditoria_ritmo or {})
    fluxo_base = base.get("processadas_por_10_minutos")
    fluxo_teste = experimento.get("processadas_por_10_minutos")
    retencao_fluxo = (
        round(float(fluxo_teste) / float(fluxo_base), 4)
        if fluxo_base and fluxo_teste is not None else None
    )
    temporal_base_bruto = base.get("cobertura_temporal")
    temporal_teste_bruto = experimento.get("cobertura_temporal")
    retencao_temporal_bruta = (
        round(
            float(temporal_teste_bruto) / float(temporal_base_bruto), 4
        )
        if temporal_base_bruto and temporal_teste_bruto is not None else None
    )
    def rendimento_temporal_foco(resumo):
        valor = resumo.get("rendimento_temporal_por_foco")
        if valor is not None:
            return valor
        # Bases persistidas pela versao anterior possuem todos os agregados
        # necessarios, embora ainda nao tragam o campo derivado. Reconstruir o
        # rendimento conserva a evidencia original sem reiniciar o teste.
        try:
            processadas = float(resumo.get("processadas") or 0)
            focos = float(resumo.get("foco_processadas") or 0)
            cobertura = float(resumo.get("cobertura_temporal"))
        except (TypeError, ValueError):
            return None
        if processadas <= 0 or focos <= 0:
            return None
        return round(cobertura * processadas / focos, 4)

    telemetria_foco_completa = bool(
        base.get("telemetria_perfil_completa")
        and experimento.get("telemetria_perfil_completa")
    )
    if telemetria_foco_completa:
        metrica_temporal = "cobertura_temporal_foco"
        temporal_base = base.get("cobertura_temporal_foco")
        temporal_teste = experimento.get("cobertura_temporal_foco")
    elif (
        rendimento_temporal_foco(base) is not None
        and rendimento_temporal_foco(experimento) is not None
    ):
        metrica_temporal = "rendimento_temporal_por_foco"
        temporal_base = rendimento_temporal_foco(base)
        temporal_teste = rendimento_temporal_foco(experimento)
    else:
        metrica_temporal = "cobertura_temporal_total"
        temporal_base = temporal_base_bruto
        temporal_teste = temporal_teste_bruto
    retencao_temporal = (
        round(float(temporal_teste) / float(temporal_base), 4)
        if temporal_base and temporal_teste is not None else None
    )

    motivos = []
    observacoes = []
    if metrica_temporal == "rendimento_temporal_por_foco":
        observacoes.append("comparacao_temporal_normalizada_por_foco")
    if experimento.get("pausas_manutencao_excluidas"):
        observacoes.append("manutencao_excluida_da_metrica_fluxo")
    if rollback_ativo:
        observacoes.append("rollback_de_seguranca_acionado")
    if auditoria_ritmo.get("saudavel") is False:
        motivos.append("ritmo_atual_inseguro")
    if pausas:
        motivos.append("pausa_packball_durante_experimento")
    amostra_completa = (
        experimento["ciclos"] >= int(minimo_ciclos)
        and minutos_observados >= float(minimo_minutos)
    )
    if (
        amostra_completa
        and retencao_fluxo is not None
        and retencao_fluxo < float(retencao_minima_fluxo)
    ):
        motivos.append("fluxo_abaixo_da_base")
    if (
        amostra_completa
        and retencao_temporal is not None
        and retencao_temporal < float(retencao_minima_temporal)
    ):
        motivos.append("cobertura_temporal_abaixo_da_base")

    regressao = bool(motivos)
    if rollback_ativo:
        estado = "rollback_acionado"
    elif regressao:
        estado = "regressao_recomendada"
    elif not amostra_completa:
        estado = "em_observacao"
    else:
        estado = "aprovado"
    resultado = {
        "versao": VERSAO_EXPERIMENTO_RITMO_LEGADA,
        "saudavel": not regressao,
        "avaliavel": True,
        "estado": estado,
        "motivos": motivos,
        "observacoes": observacoes,
        "regime_atual": chave_atual,
        "iniciado_em": inicio_em,
        "atualizado_em": agora.isoformat(),
        "minutos_observados": round(minutos_observados, 1),
        "minimo_ciclos": int(minimo_ciclos),
        "minimo_minutos": float(minimo_minutos),
        "base": base,
        "experimento": experimento,
        "pausas_packball": pausas,
        "retencao_fluxo": retencao_fluxo,
        "retencao_temporal": retencao_temporal,
        "retencao_temporal_bruta": retencao_temporal_bruta,
        "metrica_retencao_temporal": metrica_temporal,
        "limites": {
            "retencao_minima_fluxo": float(retencao_minima_fluxo),
            "retencao_minima_temporal": float(retencao_minima_temporal),
        },
        "historico": historico,
    }
    gravar_json_atomico(caminho_avaliacao, resultado)
    return resultado


def _instante_iso(valor):
    try:
        return datetime.fromisoformat(str(valor or ""))
    except (TypeError, ValueError):
        return None


def _evidencia_congelada_ritmo(avaliacao, encerrado_em, tipo):
    """Copia somente a decisao de uma epoca; nunca reescreve suas metricas."""
    if not isinstance(avaliacao, dict) or not avaliacao.get("versao"):
        return None
    return {
        "tipo": tipo,
        "versao": avaliacao.get("versao"),
        "regime": avaliacao.get("regime_atual"),
        "iniciado_em": avaliacao.get("iniciado_em"),
        "regime_iniciado_em": avaliacao.get("regime_iniciado_em"),
        "encerrado_em": encerrado_em,
        "estado": avaliacao.get("estado"),
        "saudavel": avaliacao.get("saudavel"),
        "motivos": list(avaliacao.get("motivos") or []),
        "observacoes": list(avaliacao.get("observacoes") or []),
        "pausas_packball": int(
            avaliacao.get("pausas_packball_historicas")
            or avaliacao.get("pausas_packball")
            or 0
        ),
        "retencao_fluxo": avaliacao.get("retencao_fluxo"),
        "retencao_temporal": avaliacao.get("retencao_temporal"),
        "base": avaliacao.get("base"),
        "experimento": avaliacao.get("experimento"),
    }


def _anexar_evidencia_ritmo(historico, evidencia, limite=20):
    historico = [
        dict(item) for item in (historico or [])
        if isinstance(item, dict)
    ]
    if evidencia:
        chave = tuple(evidencia.get(campo) for campo in (
            "tipo", "versao", "regime", "iniciado_em", "encerrado_em"
        ))
        existentes = {
            tuple(item.get(campo) for campo in (
                "tipo", "versao", "regime", "iniciado_em", "encerrado_em"
            ))
            for item in historico
        }
        if chave not in existentes:
            historico.append(evidencia)
    return historico[-max(int(limite), 1):]


def _comparar_demanda_ritmo(base, experimento):
    """Não infere regressão de capacidade quando falta trabalho para medi-la.

    A taxa bruta mistura velocidade e demanda. Se o ciclo atual oferece menos
    tarefas que a base conseguia processar, ela não sustenta uma conclusão de
    regressão (nem aprovação). Falhas de acesso e cobertura são independentes.
    A base congelada e a retenção bruta permanecem intactas para auditoria.
    """
    ciclos_base = int(base.get("ciclos") or 0)
    ciclos_teste = int(experimento.get("ciclos") or 0)
    processadas_base = int(base.get("processadas") or 0)
    agendadas_teste = int(experimento.get("agendadas") or 0)
    if min(ciclos_base, ciclos_teste, processadas_base, agendadas_teste) <= 0:
        # Resumos antigos sem demanda não autorizam suprimir o diagnóstico.
        return {
            "versao": "comparabilidade-demanda-ritmo-v1",
            "comparavel": None,
            "motivo": "telemetria_demanda_insuficiente",
        }
    capacidade_base = processadas_base / ciclos_base
    demanda_teste = agendadas_teste / ciclos_teste
    comparavel = demanda_teste >= capacidade_base
    return {
        "versao": "comparabilidade-demanda-ritmo-v1",
        "comparavel": comparavel,
        "motivo": (
            "demanda_suficiente_para_comparar"
            if comparavel else "demanda_abaixo_da_capacidade_observada_na_base"
        ),
        "capacidade_base_tarefas_por_ciclo": round(capacidade_base, 4),
        "demanda_atual_tarefas_por_ciclo": round(demanda_teste, 4),
        "altera_ritmo_ou_criterios_sinais": False,
    }


def avaliar_experimento_ritmo_packball(
    caminho_log,
    caminho_avaliacao,
    auditoria_ritmo=None,
    caminho_estado_acesso=None,
    agora=None,
    minimo_ciclos=12,
    minimo_minutos=45,
    retencao_minima_fluxo=0.75,
    retencao_minima_temporal=0.80,
    janela_base=12,
    janela_experimento=50,
):
    """Revalida o ritmo em epocas prospectivas sem apagar incidentes antigos.

    A versao anterior mantinha qualquer pausa ocorrida desde o inicio do
    regime como falha permanente. A v3 congela essa evidencia e abre uma nova
    janela. Uma pausa futura reinicia apenas a janela corrente; a ocorrencia
    continua contada e auditavel no historico.
    """
    agora = (agora or datetime.now()).replace(microsecond=0)
    eventos = _ler_eventos_rotacionados(caminho_log)
    ciclos = [
        evento for evento in eventos
        if evento.get("evento") == "ciclo_concluido"
        and int(evento.get("tarefas_processadas") or 0) > 0
        and float(evento.get("duracao_segundos") or 0) > 0
        and _instante_iso(evento.get("em")) is not None
        and _instante_iso(evento.get("em")) <= agora
    ]
    atual = _ler_avaliacao_ritmo(caminho_avaliacao)
    historico = [
        item for item in (atual.get("historico") or [])
        if isinstance(item, dict)
    ]
    if not ciclos:
        resultado = {
            "versao": VERSAO_EXPERIMENTO_RITMO,
            "saudavel": True,
            "avaliavel": False,
            "estado": "aguardando_telemetria",
            "motivos": [],
            "observacoes": ["revalidacao_prospectiva_versionada"],
            "atualizado_em": agora.isoformat(),
            "historico": historico[-20:],
        }
        gravar_json_atomico(caminho_avaliacao, resultado)
        return resultado

    chave_atual = _chave_regime_ritmo(ciclos[-1])
    if not chave_atual.startswith("distribuido:"):
        resultado = {
            "versao": VERSAO_EXPERIMENTO_RITMO,
            "saudavel": True,
            "avaliavel": False,
            "estado": "inativo",
            "motivos": [],
            "observacoes": ["revalidacao_prospectiva_versionada"],
            "regime_atual": chave_atual,
            "atualizado_em": agora.isoformat(),
            "historico": historico[-20:],
        }
        gravar_json_atomico(caminho_avaliacao, resultado)
        return resultado

    indice_regime = len(ciclos) - 1
    while (
        indice_regime > 0
        and _chave_regime_ritmo(ciclos[indice_regime - 1]) == chave_atual
    ):
        indice_regime -= 1
    regime_iniciado_em = ciclos[indice_regime].get("em")
    instante_regime = _instante_iso(regime_iniciado_em)
    mesmo_regime = bool(
        atual.get("regime_atual") == chave_atual
        and (
            atual.get("regime_iniciado_em") == regime_iniciado_em
            or (
                atual.get("versao") != VERSAO_EXPERIMENTO_RITMO
                and atual.get("iniciado_em") == regime_iniciado_em
            )
        )
    )
    mesma_epoca_v3 = bool(
        atual.get("versao") == VERSAO_EXPERIMENTO_RITMO
        and mesmo_regime
        and isinstance(atual.get("base"), dict)
    )
    migrando_legado = bool(
        atual.get("versao")
        and atual.get("versao") != VERSAO_EXPERIMENTO_RITMO
        and mesmo_regime
        and isinstance(atual.get("base"), dict)
    )

    if mesma_epoca_v3 or migrando_legado:
        base = dict(atual.get("base") or {})
    else:
        base = _resumir_ciclos_ritmo(
            ciclos[max(0, indice_regime - int(janela_base)):indice_regime],
            _periodos_manutencao(eventos),
        )

    evidencia_legada = (
        atual.get("evidencia_legada_congelada")
        if mesma_epoca_v3 else None
    )
    if migrando_legado:
        evidencia_legada = _evidencia_congelada_ritmo(
            atual, agora.isoformat(), "migracao_legada"
        )
        historico = _anexar_evidencia_ritmo(
            historico, evidencia_legada
        )
        iniciado_em = agora.isoformat()
    elif mesma_epoca_v3:
        iniciado_em = atual.get("iniciado_em") or agora.isoformat()
    else:
        evidencia_anterior = _evidencia_congelada_ritmo(
            atual, agora.isoformat(), "mudanca_regime"
        )
        historico = _anexar_evidencia_ritmo(
            historico, evidencia_anterior
        )
        iniciado_em = regime_iniciado_em

    instante_inicio = _instante_iso(iniciado_em) or agora
    periodos_manutencao = _periodos_manutencao(eventos)
    pausas_regime = []
    for evento in eventos:
        instante = _instante_iso(evento.get("em"))
        if (
            evento.get("evento") == "ciclo_pausado_packball"
            and instante is not None
            and instante_regime is not None
            and instante_regime <= instante <= agora
        ):
            pausas_regime.append(instante)
    pausas_regime.sort()
    ultimo_incidente_persistido = _instante_iso(
        atual.get("ultimo_incidente_em")
    ) if mesmo_regime else None
    ultimo_incidente = max(
        pausas_regime + (
            [ultimo_incidente_persistido]
            if ultimo_incidente_persistido is not None else []
        ),
        default=None,
    )
    reiniciada_por_incidente = bool(
        ultimo_incidente is not None
        and ultimo_incidente > instante_inicio
    )
    if reiniciada_por_incidente:
        if mesma_epoca_v3 and int(
            (atual.get("experimento") or {}).get("ciclos") or 0
        ) > 0:
            historico = _anexar_evidencia_ritmo(
                historico,
                _evidencia_congelada_ritmo(
                    atual,
                    ultimo_incidente.isoformat(),
                    "epoca_interrompida",
                ),
            )
        iniciado_em = ultimo_incidente.isoformat()
        instante_inicio = ultimo_incidente

    ciclos_epoca = [
        ciclo for ciclo in ciclos[indice_regime:]
        if _instante_iso(ciclo.get("em")) >= instante_inicio
    ][-int(janela_experimento):]
    experimento = _resumir_ciclos_ritmo(
        ciclos_epoca, periodos_manutencao
    )
    minutos_observados = max(
        (agora - instante_inicio).total_seconds() / 60, 0
    )

    pausas_observadas = len(pausas_regime)
    pausas_persistidas = (
        int(
            atual.get("pausas_packball_historicas")
            or atual.get("pausas_packball")
            or 0
        )
        if mesmo_regime else 0
    )
    pausas_historicas = max(pausas_observadas, pausas_persistidas)
    acesso = (
        _ler_avaliacao_ritmo(caminho_estado_acesso)
        if caminho_estado_acesso else {}
    )
    rollback_ativo = acesso.get("rollback_capacidade_ativo") is True
    auditoria_ritmo = dict(auditoria_ritmo or {})
    comparacao_demanda = _comparar_demanda_ritmo(base, experimento)
    fluxo_comparavel = comparacao_demanda["comparavel"] is not False

    fluxo_base = base.get("processadas_por_10_minutos")
    fluxo_teste = experimento.get("processadas_por_10_minutos")
    retencao_fluxo = (
        round(float(fluxo_teste) / float(fluxo_base), 4)
        if fluxo_base and fluxo_teste is not None else None
    )
    temporal_base_bruto = base.get("cobertura_temporal")
    temporal_teste_bruto = experimento.get("cobertura_temporal")
    retencao_temporal_bruta = (
        round(float(temporal_teste_bruto) / float(temporal_base_bruto), 4)
        if temporal_base_bruto and temporal_teste_bruto is not None else None
    )

    def rendimento_temporal_foco(resumo):
        valor = resumo.get("rendimento_temporal_por_foco")
        if valor is not None:
            return valor
        try:
            processadas = float(resumo.get("processadas") or 0)
            focos = float(resumo.get("foco_processadas") or 0)
            cobertura = float(resumo.get("cobertura_temporal"))
        except (TypeError, ValueError):
            return None
        if processadas <= 0 or focos <= 0:
            return None
        return round(cobertura * processadas / focos, 4)

    telemetria_foco_completa = bool(
        base.get("telemetria_perfil_completa")
        and experimento.get("telemetria_perfil_completa")
    )
    if telemetria_foco_completa:
        metrica_temporal = "cobertura_temporal_foco"
        temporal_base = base.get("cobertura_temporal_foco")
        temporal_teste = experimento.get("cobertura_temporal_foco")
    elif (
        rendimento_temporal_foco(base) is not None
        and rendimento_temporal_foco(experimento) is not None
    ):
        metrica_temporal = "rendimento_temporal_por_foco"
        temporal_base = rendimento_temporal_foco(base)
        temporal_teste = rendimento_temporal_foco(experimento)
    else:
        metrica_temporal = "cobertura_temporal_total"
        temporal_base = temporal_base_bruto
        temporal_teste = temporal_teste_bruto
    retencao_temporal = (
        round(float(temporal_teste) / float(temporal_base), 4)
        if temporal_base and temporal_teste is not None else None
    )

    motivos = []
    observacoes = ["revalidacao_prospectiva_versionada"]
    if not fluxo_comparavel:
        observacoes.append("fluxo_inconclusivo_por_baixa_demanda")
    if migrando_legado:
        observacoes.append("divida_historica_congelada")
    if reiniciada_por_incidente:
        observacoes.append("janela_reiniciada_apos_incidente")
    elif pausas_historicas:
        observacoes.append("incidentes_historicos_fora_da_janela_atual")
    if metrica_temporal == "rendimento_temporal_por_foco":
        observacoes.append("comparacao_temporal_normalizada_por_foco")
    if experimento.get("pausas_manutencao_excluidas"):
        observacoes.append("manutencao_excluida_da_metrica_fluxo")
    if rollback_ativo:
        observacoes.append("rollback_de_seguranca_acionado")
    if auditoria_ritmo.get("saudavel") is False:
        motivos.append("ritmo_atual_inseguro")

    amostra_completa = bool(
        experimento.get("ciclos", 0) >= int(minimo_ciclos)
        and minutos_observados >= float(minimo_minutos)
    )
    if (
        amostra_completa
        and fluxo_comparavel
        and retencao_fluxo is not None
        and retencao_fluxo < float(retencao_minima_fluxo)
    ):
        motivos.append("fluxo_abaixo_da_base")
    if (
        amostra_completa
        and retencao_temporal is not None
        and retencao_temporal < float(retencao_minima_temporal)
    ):
        motivos.append("cobertura_temporal_abaixo_da_base")

    regressao = bool(motivos)
    if rollback_ativo:
        estado = "rollback_acionado"
    elif regressao:
        estado = "regressao_recomendada"
    elif not amostra_completa or not fluxo_comparavel:
        estado = "em_observacao"
    else:
        estado = "aprovado"
    resultado = {
        "versao": VERSAO_EXPERIMENTO_RITMO,
        "saudavel": not regressao,
        "avaliavel": True,
        "estado": estado,
        "motivos": motivos,
        "observacoes": sorted(set(observacoes)),
        "regime_atual": chave_atual,
        "regime_iniciado_em": regime_iniciado_em,
        "iniciado_em": iniciado_em,
        "atualizado_em": agora.isoformat(),
        "minutos_observados": round(minutos_observados, 1),
        "minimo_ciclos": int(minimo_ciclos),
        "minimo_minutos": float(minimo_minutos),
        "base": base,
        "experimento": experimento,
        # Campo legado mantido para consumidores antigos. Agora representa o
        # total historico, nunca uma falha permanente da epoca corrente.
        "pausas_packball": pausas_historicas,
        "pausas_packball_historicas": pausas_historicas,
        "pausas_na_revalidacao": 0,
        "ultimo_incidente_em": (
            ultimo_incidente.isoformat()
            if ultimo_incidente is not None else None
        ),
        "revalidacao_prospectiva": True,
        "migrada_de": (
            atual.get("versao") if migrando_legado
            else atual.get("migrada_de") if mesma_epoca_v3
            else None
        ),
        "evidencia_legada_congelada": evidencia_legada,
        "retencao_fluxo": retencao_fluxo,
        "comparacao_demanda_fluxo": comparacao_demanda,
        "retencao_temporal": retencao_temporal,
        "retencao_temporal_bruta": retencao_temporal_bruta,
        "metrica_retencao_temporal": metrica_temporal,
        "limites": {
            "retencao_minima_fluxo": float(retencao_minima_fluxo),
            "retencao_minima_temporal": float(retencao_minima_temporal),
        },
        "historico": historico[-20:],
    }
    gravar_json_atomico(caminho_avaliacao, resultado)
    return resultado
