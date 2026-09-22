import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from clv_pos_alerta import (
    MERCADOS_CLV_API_RAPIDA,
    MERCADOS_CLV_SOMENTE_SNAPSHOT,
    VERSAO_COLETA_CLV_API_RAPIDA,
)


class TrabalhadorAcompanhamentoOdd:
    """Executa a fila de odds em cadencia propria, fora do ciclo PackBall.

    O servico e criado dentro da thread para que sua conexao SQLite nunca
    atravesse threads. Falhas de uma rodada sao isoladas e a proxima rodada
    continua agendada; o trabalhador nao navega no PackBall.
    """

    VERSAO_REFERENCIA_ACUMULADA = (
        "referencia-sincronizada-monitor-odd-rapido-acumulada-v1"
    )
    VERSAO_FUNIL_REFERENCIA = "funil-referencia-sombra-rapida-v1"
    VERSAO_FUNIL_REFERENCIA_ACUMULADO = (
        "funil-referencia-sombra-rapida-acumulado-v1"
    )
    CAMPOS_REFERENCIA_ACUMULADA = {
        "tentadas": "referencias_sombra_rapidas_tentadas",
        "reservadas": "referencias_sombra_rapidas_reservadas",
        "consultadas": "referencias_sombra_rapidas_consultadas",
        "linha_exata": "referencias_sombra_rapidas_linha_exata",
        "auditadas": "referencias_sombra_rapidas_auditadas",
        "observadas": "referencias_sombra_rapidas_observadas",
        "comparacoes": "comparacoes_referencia_sombra_rapida",
        "creditos_estimados_reservados": (
            "creditos_estimados_referencia_sombra_rapida"
        ),
    }
    CAMPOS_FUNIL_REFERENCIA = (
        "avaliadas",
        "aprovadas",
        "reprovadas",
        "com_oferta",
        "bloqueadas_custodia",
        "bloqueadas_materializacao",
        "alertas_enviados",
        "fontes_executaveis_pos_envio",
        "selecionadas_para_consulta",
        "suprimidas_limite_rodada",
    )

    def __init__(
        self,
        criar_servico,
        *,
        intervalo_segundos=15.0,
        caminho_estado=None,
        relogio=None,
        agora=None,
    ):
        self.criar_servico = criar_servico
        self.intervalo_segundos = max(float(intervalo_segundos), 0.01)
        self.caminho_estado = (
            Path(caminho_estado) if caminho_estado is not None else None
        )
        self.relogio = relogio or time.monotonic
        self.agora = agora or (
            lambda: datetime.now().replace(microsecond=0).isoformat()
        )
        self._parar = threading.Event()
        self._trava = threading.Lock()
        self._thread = None
        self._referencia_acumulada = (
            self._carregar_referencia_acumulada()
        )
        self._estado = {
            "status": "nao_iniciado",
            "atualizado_em": self.agora(),
            "intervalo_alvo_segundos": self.intervalo_segundos,
            "referencia_sombra_rapida_acumulada": dict(
                self._referencia_acumulada
            ),
        }

    @staticmethod
    def _inteiro_contador(valor):
        if isinstance(valor, bool):
            raise ValueError("contador_booleano")
        numero = int(valor or 0)
        if numero < 0:
            raise ValueError("contador_negativo")
        return numero

    def _novo_acumulado(self, *, integridade=True, motivo=None):
        agora = self.agora()
        acumulado = {
            "versao": self.VERSAO_REFERENCIA_ACUMULADA,
            "iniciado_em": agora,
            "atualizado_em": agora,
            "ultima_evidencia_em": None,
            "rodadas": 0,
            "motivos": {},
            "aplicacao_sinais": False,
            "telegram": False,
            "integridade": bool(integridade),
            "motivo_integridade": motivo,
            "funil_selecao": self._novo_funil_acumulado(),
        }
        acumulado.update({
            chave: 0 for chave in self.CAMPOS_REFERENCIA_ACUMULADA
        })
        return acumulado

    def _novo_funil_rodada(self):
        funil = {
            "versao": self.VERSAO_FUNIL_REFERENCIA,
            "exclusoes": {},
            "aplicacao_sinais": False,
            "telegram": False,
        }
        funil.update({chave: 0 for chave in self.CAMPOS_FUNIL_REFERENCIA})
        return funil

    def _novo_funil_acumulado(self):
        funil = self._novo_funil_rodada()
        funil["versao"] = self.VERSAO_FUNIL_REFERENCIA_ACUMULADO
        funil["tentativas_anteriores_funil"] = 0
        funil["integridade"] = True
        funil["motivo_integridade"] = None
        return funil

    def _normalizar_funil_acumulado(self, bruto, *, informado):
        funil = self._novo_funil_acumulado()
        if not informado:
            return funil
        integridade = bool(
            isinstance(bruto, dict)
            and bruto.get("versao")
            == self.VERSAO_FUNIL_REFERENCIA_ACUMULADO
            and bruto.get("integridade", True) is True
        )
        if not isinstance(bruto, dict):
            bruto = {}
        try:
            funil["tentativas_anteriores_funil"] = (
                self._inteiro_contador(
                    bruto.get("tentativas_anteriores_funil")
                )
            )
        except (TypeError, ValueError):
            integridade = False
        for chave in self.CAMPOS_FUNIL_REFERENCIA:
            try:
                funil[chave] = self._inteiro_contador(bruto.get(chave))
            except (TypeError, ValueError):
                integridade = False
        exclusoes = bruto.get("exclusoes") or {}
        if not isinstance(exclusoes, dict):
            exclusoes = {}
            integridade = False
        for motivo, quantidade in exclusoes.items():
            try:
                funil["exclusoes"][str(motivo)] = self._inteiro_contador(
                    quantidade
                )
            except (TypeError, ValueError):
                integridade = False
        funil["aplicacao_sinais"] = bool(bruto.get("aplicacao_sinais"))
        funil["telegram"] = bool(bruto.get("telegram"))
        integridade = bool(
            integridade
            and funil["aprovadas"] + funil["reprovadas"]
            == funil["avaliadas"]
            and funil["com_oferta"] <= funil["avaliadas"]
            and funil["bloqueadas_custodia"] <= funil["avaliadas"]
            and funil["alertas_enviados"] <= funil["aprovadas"]
            and funil["bloqueadas_materializacao"] <= funil["aprovadas"]
            and funil["fontes_executaveis_pos_envio"]
            <= funil["alertas_enviados"]
            and funil["selecionadas_para_consulta"]
            + funil["suprimidas_limite_rodada"]
            == funil["fontes_executaveis_pos_envio"]
            and not funil["aplicacao_sinais"]
            and not funil["telegram"]
        )
        funil["integridade"] = integridade
        funil["motivo_integridade"] = (
            None if integridade else "funil_acumulado_inconsistente"
        )
        return funil

    def _acumular_funil_referencia(self, dados_rodada):
        atual = dict(
            self._referencia_acumulada.get("funil_selecao")
            or self._novo_funil_acumulado()
        )
        atual["exclusoes"] = dict(atual.get("exclusoes") or {})
        rodada = dados_rodada.get("referencias_sombra_rapidas_funil") or {}
        integridade = bool(
            atual.get("integridade")
            and isinstance(rodada, dict)
            and rodada.get("versao") == self.VERSAO_FUNIL_REFERENCIA
            and rodada.get("aplicacao_sinais") is not True
            and rodada.get("telegram") is not True
        )
        contadores_rodada = {}
        for chave in self.CAMPOS_FUNIL_REFERENCIA:
            try:
                quantidade = self._inteiro_contador(rodada.get(chave))
                contadores_rodada[chave] = quantidade
                atual[chave] = self._inteiro_contador(
                    atual.get(chave)
                ) + quantidade
            except (TypeError, ValueError):
                integridade = False
                contadores_rodada[chave] = 0
        exclusoes = rodada.get("exclusoes") or {}
        if not isinstance(exclusoes, dict):
            exclusoes = {}
            integridade = False
        for motivo, quantidade in exclusoes.items():
            try:
                atual["exclusoes"][str(motivo)] = (
                    self._inteiro_contador(
                        atual["exclusoes"].get(str(motivo))
                    )
                    + self._inteiro_contador(quantidade)
                )
            except (TypeError, ValueError):
                integridade = False
        integridade = bool(
            integridade
            and contadores_rodada["aprovadas"]
            + contadores_rodada["reprovadas"]
            == contadores_rodada["avaliadas"]
            and contadores_rodada["com_oferta"]
            <= contadores_rodada["avaliadas"]
            and contadores_rodada["alertas_enviados"]
            <= contadores_rodada["aprovadas"]
            and contadores_rodada["fontes_executaveis_pos_envio"]
            <= contadores_rodada["alertas_enviados"]
            and contadores_rodada["selecionadas_para_consulta"]
            + contadores_rodada["suprimidas_limite_rodada"]
            == contadores_rodada["fontes_executaveis_pos_envio"]
            and atual["aprovadas"] + atual["reprovadas"]
            == atual["avaliadas"]
            and atual["com_oferta"] <= atual["avaliadas"]
            and atual["bloqueadas_custodia"] <= atual["avaliadas"]
            and atual["alertas_enviados"] <= atual["aprovadas"]
            and atual["bloqueadas_materializacao"] <= atual["aprovadas"]
            and atual["fontes_executaveis_pos_envio"]
            <= atual["alertas_enviados"]
            and atual["selecionadas_para_consulta"]
            + atual["suprimidas_limite_rodada"]
            == atual["fontes_executaveis_pos_envio"]
        )
        atual["integridade"] = integridade
        atual["motivo_integridade"] = (
            None if integridade else "funil_acumulado_inconsistente"
        )
        return atual

    def _normalizar_referencia_acumulada(self, bruto):
        acumulado = self._novo_acumulado()
        integridade = bool(
            isinstance(bruto, dict)
            and bruto.get("versao") == self.VERSAO_REFERENCIA_ACUMULADA
            and bruto.get("integridade", True) is True
        )
        if not isinstance(bruto, dict):
            bruto = {}
        acumulado["iniciado_em"] = (
            bruto.get("iniciado_em") or acumulado["iniciado_em"]
        )
        acumulado["atualizado_em"] = (
            bruto.get("atualizado_em") or acumulado["atualizado_em"]
        )
        acumulado["ultima_evidencia_em"] = bruto.get(
            "ultima_evidencia_em"
        )
        try:
            acumulado["rodadas"] = self._inteiro_contador(
                bruto.get("rodadas")
            )
            for chave in self.CAMPOS_REFERENCIA_ACUMULADA:
                acumulado[chave] = self._inteiro_contador(
                    bruto.get(chave)
                )
        except (TypeError, ValueError):
            integridade = False
        motivos = bruto.get("motivos") or {}
        if not isinstance(motivos, dict):
            motivos = {}
            integridade = False
        motivos_validos = {}
        for motivo, quantidade in motivos.items():
            try:
                motivos_validos[str(motivo)] = self._inteiro_contador(
                    quantidade
                )
            except (TypeError, ValueError):
                integridade = False
        acumulado["motivos"] = motivos_validos
        acumulado["funil_selecao"] = self._normalizar_funil_acumulado(
            bruto.get("funil_selecao"),
            informado="funil_selecao" in bruto,
        )
        if "funil_selecao" not in bruto:
            acumulado["funil_selecao"][
                "tentativas_anteriores_funil"
            ] = acumulado["tentadas"]
        acumulado["aplicacao_sinais"] = bool(
            bruto.get("aplicacao_sinais")
        )
        acumulado["telegram"] = bool(bruto.get("telegram"))
        integridade = bool(
            integridade
            and acumulado["reservadas"] <= acumulado["tentadas"]
            and acumulado["consultadas"] <= acumulado["reservadas"]
            and acumulado["linha_exata"] <= acumulado["consultadas"]
            and acumulado["auditadas"] <= acumulado["tentadas"]
            and acumulado["observadas"] <= acumulado["linha_exata"]
            and acumulado["comparacoes"] <= acumulado["observadas"] * 2
            and not acumulado["aplicacao_sinais"]
            and not acumulado["telegram"]
            and acumulado["funil_selecao"]["integridade"]
        )
        acumulado["integridade"] = integridade
        acumulado["motivo_integridade"] = (
            None if integridade else "acumulado_persistido_inconsistente"
        )
        return acumulado

    def _migrar_referencia_legada(self, estado):
        acumulado = self._novo_acumulado()
        integridade = isinstance(estado, dict)
        for chave, campo_rodada in self.CAMPOS_REFERENCIA_ACUMULADA.items():
            try:
                acumulado[chave] = self._inteiro_contador(
                    (estado or {}).get(campo_rodada)
                )
            except (TypeError, ValueError):
                integridade = False
        motivos = (estado or {}).get(
            "referencias_sombra_rapidas_motivos"
        ) or {}
        if not isinstance(motivos, dict):
            motivos = {}
            integridade = False
        for motivo, quantidade in motivos.items():
            try:
                acumulado["motivos"][str(motivo)] = (
                    self._inteiro_contador(quantidade)
                )
            except (TypeError, ValueError):
                integridade = False
        acumulado["aplicacao_sinais"] = bool(
            (estado or {}).get("aplicacao_sinais_referencia_sombra")
        )
        acumulado["funil_selecao"][
            "tentativas_anteriores_funil"
        ] = acumulado["tentadas"]
        houve_rodada = bool((estado or {}).get("ultima_rodada_em"))
        acumulado["rodadas"] = 1 if houve_rodada else 0
        referencia_temporal = (
            (estado or {}).get("ultima_rodada_em")
            or (estado or {}).get("atualizado_em")
            or acumulado["iniciado_em"]
        )
        acumulado["iniciado_em"] = referencia_temporal
        acumulado["atualizado_em"] = referencia_temporal
        if any(
            acumulado[chave]
            for chave in self.CAMPOS_REFERENCIA_ACUMULADA
        ):
            acumulado["ultima_evidencia_em"] = referencia_temporal
        integridade = bool(
            integridade
            and acumulado["reservadas"] <= acumulado["tentadas"]
            and acumulado["consultadas"] <= acumulado["reservadas"]
            and acumulado["linha_exata"] <= acumulado["consultadas"]
            and acumulado["auditadas"] <= acumulado["tentadas"]
            and acumulado["observadas"] <= acumulado["linha_exata"]
            and acumulado["comparacoes"] <= acumulado["observadas"] * 2
            and not acumulado["aplicacao_sinais"]
        )
        acumulado["integridade"] = integridade
        acumulado["motivo_integridade"] = (
            None if integridade else "estado_legado_inconsistente"
        )
        acumulado["origem_migracao"] = "ultima_rodada_legada"
        return acumulado

    def _carregar_referencia_acumulada(self):
        if self.caminho_estado is None or not self.caminho_estado.exists():
            return self._novo_acumulado()
        try:
            estado = json.loads(
                self.caminho_estado.read_text(encoding="utf-8")
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return self._novo_acumulado(
                integridade=False,
                motivo="estado_persistido_ilegivel",
            )
        if not isinstance(estado, dict):
            return self._novo_acumulado(
                integridade=False,
                motivo="estado_persistido_invalido",
            )
        existente = estado.get(
            "referencia_sombra_rapida_acumulada"
        )
        if existente is not None:
            return self._normalizar_referencia_acumulada(existente)
        return self._migrar_referencia_legada(estado)

    def _acumular_referencia(self, dados_rodada):
        acumulado = dict(self._referencia_acumulada)
        acumulado["motivos"] = dict(acumulado.get("motivos") or {})
        acumulado["funil_selecao"] = (
            self._acumular_funil_referencia(dados_rodada)
        )
        integridade = bool(acumulado.get("integridade"))
        try:
            acumulado["rodadas"] = self._inteiro_contador(
                acumulado.get("rodadas")
            ) + 1
            for chave, campo_rodada in (
                self.CAMPOS_REFERENCIA_ACUMULADA.items()
            ):
                acumulado[chave] = self._inteiro_contador(
                    acumulado.get(chave)
                ) + self._inteiro_contador(dados_rodada.get(campo_rodada))
        except (TypeError, ValueError):
            integridade = False
        motivos_rodada = dados_rodada.get(
            "referencias_sombra_rapidas_motivos"
        ) or {}
        if not isinstance(motivos_rodada, dict):
            motivos_rodada = {}
            integridade = False
        for motivo, quantidade in motivos_rodada.items():
            try:
                acumulado["motivos"][str(motivo)] = (
                    self._inteiro_contador(
                        acumulado["motivos"].get(str(motivo))
                    )
                    + self._inteiro_contador(quantidade)
                )
            except (TypeError, ValueError):
                integridade = False
        acumulado["aplicacao_sinais"] = bool(
            acumulado.get("aplicacao_sinais")
            or dados_rodada.get("aplicacao_sinais_referencia_sombra")
        )
        acumulado["telegram"] = bool(acumulado.get("telegram"))
        agora = self.agora()
        acumulado["atualizado_em"] = agora
        if any(
            dados_rodada.get(campo_rodada)
            for campo_rodada in self.CAMPOS_REFERENCIA_ACUMULADA.values()
        ):
            acumulado["ultima_evidencia_em"] = agora
        integridade = bool(
            integridade
            and acumulado["reservadas"] <= acumulado["tentadas"]
            and acumulado["consultadas"] <= acumulado["reservadas"]
            and acumulado["linha_exata"] <= acumulado["consultadas"]
            and acumulado["auditadas"] <= acumulado["tentadas"]
            and acumulado["observadas"] <= acumulado["linha_exata"]
            and acumulado["comparacoes"] <= acumulado["observadas"] * 2
            and not acumulado["aplicacao_sinais"]
            and not acumulado["telegram"]
            and acumulado["funil_selecao"]["integridade"]
            and acumulado["tentadas"]
            <= (
                acumulado["funil_selecao"][
                    "tentativas_anteriores_funil"
                ]
                + acumulado["funil_selecao"][
                    "selecionadas_para_consulta"
                ]
            )
        )
        acumulado["integridade"] = integridade
        acumulado["motivo_integridade"] = (
            None if integridade else "acumulado_inconsistente"
        )
        self._referencia_acumulada = acumulado
        return dict(acumulado)

    def estado(self):
        with self._trava:
            return dict(self._estado)

    def ativo(self):
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def iniciar(self):
        with self._trava:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._parar.clear()
            self._estado = {
                "status": "iniciando",
                "atualizado_em": self.agora(),
                "intervalo_alvo_segundos": self.intervalo_segundos,
                "referencia_sombra_rapida_acumulada": dict(
                    self._referencia_acumulada
                ),
            }
            self._persistir_estado_sem_falhar(self._estado)
            self._thread = threading.Thread(
                target=self._executar,
                name="acompanhamento-odd-api-rapido",
                daemon=True,
            )
            self._thread.start()
            return True

    def parar(self, timeout_segundos=30.0):
        self._parar.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(float(timeout_segundos), 0.0))
        encerrado = not self.ativo()
        if not encerrado:
            self._atualizar_estado(
                status="encerramento_pendente",
                motivo="consulta_em_andamento",
            )
        return encerrado

    def _persistir_estado_sem_falhar(self, estado):
        if self.caminho_estado is None:
            return
        temporario = self.caminho_estado.with_name(
            f"{self.caminho_estado.name}.{os.getpid()}."
            f"{threading.get_ident()}.tmp"
        )
        try:
            self.caminho_estado.parent.mkdir(parents=True, exist_ok=True)
            temporario.write_text(
                json.dumps(estado, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporario, self.caminho_estado)
        except OSError:
            try:
                temporario.unlink(missing_ok=True)
            except OSError:
                pass

    def _atualizar_estado(self, **dados):
        with self._trava:
            estado = dict(self._estado)
            estado.update(dados)
            estado["atualizado_em"] = self.agora()
            estado["intervalo_alvo_segundos"] = self.intervalo_segundos
            self._estado = estado
            self._persistir_estado_sem_falhar(estado)

    @staticmethod
    def _fechar_servico(servico):
        fechar = getattr(servico, "fechar", None)
        if callable(fechar):
            try:
                fechar()
            except Exception:
                pass

    @staticmethod
    def _registrar_telemetria(servico, dados):
        observabilidade = getattr(servico, "observabilidade", None)
        registrar = getattr(observabilidade, "ciclo_progresso", None)
        if not callable(registrar):
            return
        try:
            registrar("trabalhador_acompanhamento_odd", **dados)
        except Exception:
            pass

    def _executar(self):
        servico = None
        inicio_anterior = None
        falhas_consecutivas = 0
        falhas_clv_consecutivas = 0
        try:
            while not self._parar.is_set():
                inicio = self.relogio()
                intervalo_real = (
                    None if inicio_anterior is None
                    else max(inicio - inicio_anterior, 0.0)
                )
                atraso = (
                    0.0 if intervalo_real is None
                    else max(intervalo_real - self.intervalo_segundos, 0.0)
                )
                resumo = {}
                erro = None
                try:
                    if servico is None:
                        servico = self.criar_servico()
                    resumo = dict(
                        servico._rechecar_acompanhamentos_odd_api(
                            forcar=True
                        ) or {}
                    )
                    capturar_clv = getattr(
                        servico, "_capturar_cotacoes_clv_pos_alerta_api", None
                    )
                    if callable(capturar_clv):
                        try:
                            clv_pos_alerta = dict(capturar_clv() or {})
                        except Exception as excecao_clv:
                            clv_pos_alerta = {
                                "versao": VERSAO_COLETA_CLV_API_RAPIDA,
                                "mercados_api_rapida": sorted(
                                    MERCADOS_CLV_API_RAPIDA
                                ),
                                "mercados_somente_snapshot": sorted(
                                    MERCADOS_CLV_SOMENTE_SNAPSHOT
                                ),
                                "estado": "falha_isolada",
                                "candidatos": 0,
                                "consultados": 0,
                                "com_oferta_exata": 0,
                                "sem_oferta_exata": 0,
                                "somente_estado": 0,
                                "estados_persistidos": 0,
                                "falhas": 1,
                                "motivos": {
                                    type(excecao_clv).__name__: 1,
                                },
                                "aplicacao_sinais": False,
                                "telegram": False,
                            }
                        resumo["clv_pos_alerta"] = clv_pos_alerta
                        if (
                            int(clv_pos_alerta.get("falhas") or 0) > 0
                            or clv_pos_alerta.get("estado")
                            in {"degradada", "falha_isolada"}
                        ):
                            falhas_clv_consecutivas += 1
                        else:
                            falhas_clv_consecutivas = 0
                    falhas_consecutivas = 0
                    status = "ativo"
                except Exception as excecao:
                    falhas_consecutivas += 1
                    erro = type(excecao).__name__
                    status = "degradado"
                    if servico is not None and falhas_consecutivas >= 3:
                        self._fechar_servico(servico)
                        servico = None
                duracao = max(self.relogio() - inicio, 0.0)
                proxima_espera = max(
                    self.intervalo_segundos - duracao, 0.0
                )
                dados_estado = {
                    "status": status,
                    "ultima_rodada_em": self.agora(),
                    "duracao_rodada_segundos": round(duracao, 3),
                    "intervalo_real_segundos": (
                        None if intervalo_real is None
                        else round(intervalo_real, 3)
                    ),
                    "atraso_inicio_segundos": round(atraso, 3),
                    "proxima_espera_segundos": round(proxima_espera, 3),
                    "falhas_consecutivas": falhas_consecutivas,
                    "consultados": int(resumo.get("consultados") or 0),
                    "atingiram_alvo": int(
                        resumo.get("atingiram_alvo") or 0
                    ),
                    "enviados": int(resumo.get("enviados") or 0),
                    "bloqueados": int(resumo.get("bloqueados") or 0),
                    "comparacoes_odds_fontes": int(
                        resumo.get("comparacoes_odds_fontes") or 0
                    ),
                    "referencias_sombra_rapidas_tentadas": int(
                        resumo.get(
                            "referencias_sombra_rapidas_tentadas"
                        ) or 0
                    ),
                    "referencias_sombra_rapidas_reservadas": int(
                        resumo.get(
                            "referencias_sombra_rapidas_reservadas"
                        ) or 0
                    ),
                    "referencias_sombra_rapidas_consultadas": int(
                        resumo.get(
                            "referencias_sombra_rapidas_consultadas"
                        ) or 0
                    ),
                    "referencias_sombra_rapidas_linha_exata": int(
                        resumo.get(
                            "referencias_sombra_rapidas_linha_exata"
                        ) or 0
                    ),
                    "referencias_sombra_rapidas_auditadas": int(
                        resumo.get(
                            "referencias_sombra_rapidas_auditadas"
                        ) or 0
                    ),
                    "referencias_sombra_rapidas_observadas": int(
                        resumo.get(
                            "referencias_sombra_rapidas_observadas"
                        ) or 0
                    ),
                    "comparacoes_referencia_sombra_rapida": int(
                        resumo.get(
                            "comparacoes_referencia_sombra_rapida"
                        ) or 0
                    ),
                    "creditos_estimados_referencia_sombra_rapida": int(
                        resumo.get(
                            "creditos_estimados_referencia_sombra_rapida"
                        ) or 0
                    ),
                    "aplicacao_sinais_referencia_sombra": bool(
                        resumo.get("aplicacao_sinais_referencia_sombra")
                    ),
                    "referencias_sombra_rapidas_motivos": (
                        resumo.get("referencias_sombra_rapidas_motivos")
                        or {}
                    ),
                    "referencias_sombra_rapidas_funil": (
                        resumo.get("referencias_sombra_rapidas_funil")
                        or self._novo_funil_rodada()
                    ),
                    "lote_maximo": int(resumo.get("lote_maximo") or 0),
                    "fila_total": int(resumo.get("fila_total") or 0),
                    "fila_tecnica_recente": int(
                        resumo.get("fila_tecnica_recente") or 0
                    ),
                    "fila_tecnica_dormente": int(
                        resumo.get("fila_tecnica_dormente") or 0
                    ),
                    "fila_recente_nunca_consultada": int(
                        resumo.get("fila_recente_nunca_consultada") or 0
                    ),
                    "fila_pendente_apos_lote": int(
                        resumo.get("fila_pendente_apos_lote") or 0
                    ),
                    "motivo": resumo.get("motivo"),
                    "motivos": resumo.get("motivos") or {},
                    "erro": erro,
                    "sem_navegacao_packball": True,
                }
                clv_pos_alerta = resumo.get("clv_pos_alerta") or {}
                dados_estado.update({
                    "clv_pos_alerta_versao": clv_pos_alerta.get("versao"),
                    "clv_pos_alerta_mercados_api_rapida": list(
                        clv_pos_alerta.get("mercados_api_rapida") or []
                    ),
                    "clv_pos_alerta_mercados_somente_snapshot": list(
                        clv_pos_alerta.get(
                            "mercados_somente_snapshot"
                        ) or []
                    ),
                    "clv_pos_alerta_estado": clv_pos_alerta.get("estado"),
                    "clv_pos_alerta_candidatos": int(
                        clv_pos_alerta.get("candidatos") or 0
                    ),
                    "clv_pos_alerta_consultados": int(
                        clv_pos_alerta.get("consultados") or 0
                    ),
                    "clv_pos_alerta_com_oferta_exata": int(
                        clv_pos_alerta.get("com_oferta_exata") or 0
                    ),
                    "clv_pos_alerta_sem_oferta_exata": int(
                        clv_pos_alerta.get("sem_oferta_exata") or 0
                    ),
                    "clv_pos_alerta_somente_estado": int(
                        clv_pos_alerta.get("somente_estado") or 0
                    ),
                    "clv_pos_alerta_estados_persistidos": int(
                        clv_pos_alerta.get("estados_persistidos") or 0
                    ),
                    "clv_pos_alerta_falhas": int(
                        clv_pos_alerta.get("falhas") or 0
                    ),
                    "clv_pos_alerta_falhas_consecutivas": (
                        falhas_clv_consecutivas
                    ),
                    "clv_pos_alerta_motivos": (
                        clv_pos_alerta.get("motivos") or {}
                    ),
                    "clv_pos_alerta_aplicacao_sinais": bool(
                        clv_pos_alerta.get("aplicacao_sinais")
                    ),
                    "clv_pos_alerta_telegram": bool(
                        clv_pos_alerta.get("telegram")
                    ),
                })
                dados_estado["referencia_sombra_rapida_acumulada"] = (
                    self._acumular_referencia(dados_estado)
                )
                self._atualizar_estado(**dados_estado)
                if (
                    dados_estado["consultados"]
                    or dados_estado["atingiram_alvo"]
                    or dados_estado["enviados"]
                    or dados_estado["bloqueados"]
                    or dados_estado["referencias_sombra_rapidas_tentadas"]
                    or dados_estado["clv_pos_alerta_candidatos"]
                    or dados_estado["clv_pos_alerta_falhas"]
                    or erro
                ):
                    self._registrar_telemetria(servico, dados_estado)
                inicio_anterior = inicio
                if self._parar.wait(proxima_espera):
                    break
        finally:
            if servico is not None:
                self._fechar_servico(servico)
            self._atualizar_estado(
                status="encerrado",
                proxima_espera_segundos=None,
            )
