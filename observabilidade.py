import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

from retencao import rotacionar_arquivo


PADROES_SEGREDOS_ERRO = (
    re.compile(
        r"(?i)\b(token|api[-_ ]?key|password|senha)"
        r"(\s*[:=]\s*)([^\s,;&]+)"
    ),
    re.compile(r"(?i)\bbot\d+:[A-Za-z0-9_-]+"),
)


def resumir_erro_seguro(erro, limite=500):
    """Produz diagnóstico curto sem persistir credenciais por acidente."""
    mensagem = " ".join(str(erro).split())
    for padrao in PADROES_SEGREDOS_ERRO:
        if padrao.groups >= 2:
            mensagem = padrao.sub(r"\1\2<redigido>", mensagem)
        else:
            mensagem = padrao.sub("bot<redigido>", mensagem)
    return mensagem[:max(int(limite), 0)]


def percentil_valores(valores, percentual):
    """Calcula percentil pelo metodo nearest-rank, sem dependencias externas."""
    valores = sorted(float(valor) for valor in valores)
    if not valores:
        return None
    posicao = max(1, math.ceil(len(valores) * float(percentual)))
    return valores[min(posicao - 1, len(valores) - 1)]


class Observabilidade:
    def __init__(self, caminho_log, limite_bytes=5 * 1024 * 1024):
        self.caminho_log = Path(caminho_log)
        self.limite_bytes = limite_bytes
        self.falhas_consecutivas = 0
        self.ciclos_ok = 0
        self.ciclos_com_erro = 0
        self._cache_api_anterior = {
            "hits": 0,
            "gravacoes": 0,
            "descartes": 0,
            "falhas": 0,
        }

    def duracoes_tarefas_recentes(self, limite=30):
        """Restaura durações válidas para a admissão adaptativa após reinício."""
        limite = max(int(limite), 0)
        if limite == 0:
            return []
        duracoes_brutas = []
        duracoes_legadas = []
        caminhos = [self.caminho_log] + [
            Path(f"{self.caminho_log}.{indice}")
            for indice in range(1, 6)
        ]
        for caminho in caminhos:
            if not caminho.exists():
                continue
            try:
                linhas = caminho.read_text(
                    encoding="utf-8"
                ).splitlines()
            except (OSError, UnicodeError):
                continue
            for linha in reversed(linhas):
                try:
                    registro = json.loads(linha)
                except (json.JSONDecodeError, TypeError):
                    continue
                if registro.get("evento") != "ciclo_concluido":
                    continue
                valores = registro.get("duracoes_tarefas_segundos")
                if isinstance(valores, list) and valores:
                    for valor in reversed(valores):
                        try:
                            numero = float(valor)
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(numero) and numero >= 0:
                            duracoes_brutas.append(numero)
                else:
                    try:
                        numero = float(
                            registro.get("duracao_tarefa_p95_segundos")
                        )
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(numero) and numero >= 0:
                        duracoes_legadas.append(numero)
        escolhidas = duracoes_brutas or duracoes_legadas
        return list(reversed(escolhidas[:limite]))

    def _registros_rotacionados(self):
        """Lê o log atual e suas rotações sem depender da ordem dos arquivos."""
        registros = []
        caminhos = [self.caminho_log] + [
            Path(f"{self.caminho_log}.{indice}")
            for indice in range(1, 6)
        ]
        for caminho in caminhos:
            if not caminho.exists():
                continue
            try:
                linhas = caminho.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            for linha in linhas:
                try:
                    registro = json.loads(linha)
                    instante = datetime.fromisoformat(
                        str(registro.get("em"))
                    )
                except (
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                ):
                    continue
                registros.append((instante, registro))
        registros.sort(key=lambda item: item[0])
        return registros

    def resumo_funil_periodo(self, horas=24, agora=None):
        """Explica baixa emissão sem misturar telemetria com decisão de sinal."""
        horas = max(float(horas), 0.0)
        agora = (agora or datetime.now()).replace(microsecond=0)
        inicio = agora - timedelta(hours=horas)
        registros = []
        for instante, registro in self._registros_rotacionados():
            instante_comparavel = instante
            inicio_comparavel = inicio
            if instante_comparavel.tzinfo is not None:
                if inicio_comparavel.tzinfo is None:
                    inicio_comparavel = inicio_comparavel.replace(
                        tzinfo=instante_comparavel.tzinfo
                    )
            elif inicio_comparavel.tzinfo is not None:
                instante_comparavel = instante_comparavel.replace(
                    tzinfo=inicio_comparavel.tzinfo
                )
            if inicio_comparavel <= instante_comparavel <= agora.replace(
                tzinfo=inicio_comparavel.tzinfo
            ):
                registros.append(registro)

        ciclos = [
            item for item in registros
            if item.get("evento") == "ciclo_concluido"
        ]
        falhas = [
            item for item in registros
            if item.get("evento") == "ciclo_falhou"
        ]
        sequencia_operacional = [
            item for item in registros
            if item.get("evento") in ("ciclo_concluido", "ciclo_falhou")
        ]
        sucessos_consecutivos_finais = 0
        for item in reversed(sequencia_operacional):
            if item.get("evento") != "ciclo_concluido":
                break
            sucessos_consecutivos_finais += 1
        falhas_consecutivas_finais = 0
        for item in reversed(sequencia_operacional):
            if item.get("evento") != "ciclo_falhou":
                break
            falhas_consecutivas_finais += 1
        operacao_recuperada = bool(
            falhas and sucessos_consecutivos_finais >= 2
        )

        def inteiro(valor):
            try:
                return max(int(valor or 0), 0)
            except (TypeError, ValueError):
                return 0

        def somar(chave):
            return sum(inteiro(item.get(chave)) for item in ciclos)

        def somar_mapa(chave):
            resumo = {}
            for ciclo in ciclos:
                for nome, quantidade in (
                    ciclo.get(chave) or {}
                ).items():
                    nome = str(nome or "nao_identificada")
                    resumo[nome] = resumo.get(nome, 0) + inteiro(
                        quantidade
                    )
            return resumo

        motivos = {}
        campos_ausentes = {}
        for ciclo in ciclos:
            for dados in (
                (ciclo.get("gols_antecipados") or {}).get("por_braco")
                or {}
            ).values():
                for nome, quantidade in (dados.get("motivos") or {}).items():
                    motivos[nome] = motivos.get(nome, 0) + inteiro(
                        quantidade
                    )
                detalhes = dados.get("detalhes") or {}
                for nome, quantidade in (
                    detalhes.get("campos_ausentes") or {}
                ).items():
                    campos_ausentes[nome] = (
                        campos_ausentes.get(nome, 0) + inteiro(quantidade)
                    )

        def somar_perfil(chave):
            return sum(
                inteiro((ciclo.get("perfil_agendamento") or {}).get(chave))
                for ciclo in ciclos
            )

        acompanhamento_preco_agendados = somar_perfil(
            "acompanhamentos_preco_agendados"
        )
        acompanhamento_preco_processados = somar_perfil(
            "acompanhamentos_preco_processados"
        )
        acompanhamento_preco_com_odds = somar_perfil(
            "acompanhamentos_preco_com_odds"
        )
        acompanhamento_preco_sem_odds = somar_perfil(
            "acompanhamentos_preco_sem_odds"
        )
        acompanhamento_preco_snapshots = somar_perfil(
            "acompanhamentos_preco_snapshots"
        )
        acompanhamento_preco = {
            "agendados": acompanhamento_preco_agendados,
            "processados": acompanhamento_preco_processados,
            "com_odds": acompanhamento_preco_com_odds,
            "sem_odds": acompanhamento_preco_sem_odds,
            "snapshots_persistidos": acompanhamento_preco_snapshots,
            "taxa_processamento": (
                acompanhamento_preco_processados
                / acompanhamento_preco_agendados
                if acompanhamento_preco_agendados else None
            ),
            "taxa_coleta_odds": (
                acompanhamento_preco_com_odds
                / acompanhamento_preco_processados
                if acompanhamento_preco_processados else None
            ),
            "taxa_persistencia_snapshot": (
                acompanhamento_preco_snapshots
                / acompanhamento_preco_processados
                if acompanhamento_preco_processados else None
            ),
            "altera_sinais": False,
        }

        partidas_por_ciclo = [inteiro(item.get("partidas")) for item in ciclos]
        partidas_somadas = sum(partidas_por_ciclo)
        ciclos_zero_confirmado = sum(
            1
            for item in ciclos
            if inteiro(item.get("partidas")) == 0
            and (item.get("lista_packball") or {}).get(
                "modo_confirmacao"
            ) == "status_linhas_zero_confirmado"
        )
        todos_ciclos_zero_confirmado = bool(
            ciclos and ciclos_zero_confirmado == len(ciclos)
        )
        processadas = somar("tarefas_processadas")
        com_odds = somar("tarefas_com_odds")
        sem_odds = somar("tarefas_sem_odds")
        odds_solicitadas = somar("tarefas_odds_solicitadas")
        coletas_odds_sucesso = somar("coletas_odds_sucesso")
        fallback_odds_necessario = somar("fallback_odds_necessario")
        fallback_odds_atendeu = somar("fallback_odds_atendeu")
        fallback_odds_sem_cobertura = somar(
            "fallback_odds_sem_cobertura"
        )
        fontes_odds_utilizaveis = somar_mapa(
            "fontes_odds_utilizaveis"
        )
        fontes_fallback_odds = somar_mapa("fontes_fallback_odds")

        def somar_diagnostico(nome, chave):
            return sum(
                inteiro((ciclo.get(nome) or {}).get(chave))
                for ciclo in ciclos
            )

        comparacoes_por_partida = {}
        instantes_comparacao = []
        for ciclo in ciclos:
            itens = ciclo.get("comparacoes_fontes_odds") or []
            if not isinstance(itens, list) or not itens:
                continue
            try:
                instante_ciclo = datetime.fromisoformat(
                    str(ciclo.get("em"))
                ).replace(tzinfo=None)
            except (TypeError, ValueError):
                instante_ciclo = None
            if instante_ciclo is not None:
                instantes_comparacao.append(instante_ciclo)
            for item in itens:
                if not isinstance(item, dict):
                    continue
                partida = str(item.get("partida") or "").strip()
                if partida:
                    comparacoes_por_partida[partida] = item

        horas_comparacao = 0.0
        if len(instantes_comparacao) >= 2:
            horas_comparacao = max(
                (
                    max(instantes_comparacao)
                    - min(instantes_comparacao)
                ).total_seconds() / 3600,
                0.0,
            )

        def resumir_fonte_comparada(fonte):
            utilizaveis = 0
            fallback = 0
            ativa = 0
            pareada_ou_evidencia = 0
            consultada = 0
            mercados_anexados = 0
            for item in comparacoes_por_partida.values():
                fontes = set(item.get("fontes_utilizaveis") or [])
                fontes_fallback = set(item.get("fontes_fallback") or [])
                utilizaveis += int(fonte in fontes)
                fallback += int(fonte in fontes_fallback)
                diagnostico = item.get(fonte) or {}
                ativa += int(diagnostico.get("ativa") is True)
                pareada_ou_evidencia += int(bool(
                    diagnostico.get("pareada")
                    or diagnostico.get("evidencia_disponivel")
                ))
                consultada += int(bool(
                    diagnostico.get("consultada")
                    or diagnostico.get("evidencia_disponivel")
                ))
                mercados_anexados += inteiro(
                    diagnostico.get("mercados_anexados")
                )
            return {
                "ocorrencias_utilizaveis": inteiro(
                    fontes_odds_utilizaveis.get(fonte)
                ),
                "ocorrencias_fallback": inteiro(
                    fontes_fallback_odds.get(fonte)
                ),
                "partidas_unicas_utilizaveis": utilizaveis,
                "partidas_unicas_fallback": fallback,
                "partidas_unicas_fonte_ativa": ativa,
                "partidas_unicas_pareadas_ou_com_evidencia": (
                    pareada_ou_evidencia
                ),
                "partidas_unicas_consultadas": consultada,
                "mercados_anexados_partidas_unicas": mercados_anexados,
            }

        comparacao_betsapi = resumir_fonte_comparada("betsapi")
        comparacao_thestats = resumir_fonte_comparada("thestatsapi")
        comparacao_the_odds = resumir_fonte_comparada("the_odds_api")
        comparacao_packball = resumir_fonte_comparada("packball")
        comparacao_betsapi.update({
            "ciclos_ativos": sum(
                int((ciclo.get("betsapi") or {}).get("ativa") is True)
                for ciclo in ciclos
            ),
            "pareamentos_ciclo": somar_diagnostico(
                "betsapi", "partidas_pareadas"
            ),
            "consultas_ciclo": somar_diagnostico(
                "betsapi", "partidas_consultadas"
            ),
            "mercados_anexados_ciclo": somar_diagnostico(
                "betsapi", "mercados_anexados"
            ),
            "circuito_aberto_ciclos": sum(
                int(bool(
                    (ciclo.get("betsapi") or {}).get("circuito_aberto")
                ))
                for ciclo in ciclos
            ),
        })
        comparacao_the_odds.update({
            "ciclos_ativos": sum(
                int(
                    (ciclo.get("the_odds_api") or {}).get("ativa")
                    is True
                )
                for ciclo in ciclos
            ),
            "pareamentos_ciclo": somar_diagnostico(
                "the_odds_api", "partidas_pareadas"
            ),
            "consultas_ciclo": somar_diagnostico(
                "the_odds_api", "partidas_consultadas"
            ),
            "mercados_anexados_ciclo": somar_diagnostico(
                "the_odds_api", "mercados_anexados"
            ),
        })
        comparacao_thestats.update({
            "ciclos_ativos": sum(
                int(
                    (ciclo.get("thestatsapi_sombra") or {}).get("ativa")
                    is True
                )
                for ciclo in ciclos
            ),
            "tentativas_pareamento_ciclo": sum(
                inteiro(
                    (ciclo.get("thestatsapi_sombra") or {}).get(
                        "tentativas_pareamento"
                    )
                )
                for ciclo in ciclos
            ),
            "pareamentos_ciclo": sum(
                inteiro(
                    (ciclo.get("thestatsapi_sombra") or {}).get("pareadas")
                )
                for ciclo in ciclos
            ),
            "consultas_odds_ciclo": sum(
                inteiro(
                    (ciclo.get("thestatsapi_sombra") or {}).get(
                        "odds_consultadas"
                    )
                )
                for ciclo in ciclos
            ),
            "partidas_com_ofertas_ciclo": sum(
                inteiro(
                    (ciclo.get("thestatsapi_sombra") or {}).get(
                        "partidas_com_odds"
                    )
                )
                for ciclo in ciclos
            ),
            "ofertas_persistidas_ciclo": sum(
                inteiro(
                    (ciclo.get("thestatsapi_sombra") or {}).get(
                        "ofertas_odds_persistidas"
                    )
                )
                for ciclo in ciclos
            ),
            "erros_ciclo": sum(
                inteiro(
                    (ciclo.get("thestatsapi_sombra") or {}).get("erros")
                )
                for ciclo in ciclos
            ),
            "gates_aptos_ciclo": somar_diagnostico(
                "thestatsapi_odds", "gates_aptos"
            ),
            "mercados_anexados_ciclo": somar_diagnostico(
                "thestatsapi_odds", "mercados_anexados"
            ),
        })
        ambas_ativas = sum(
            int(
                (item.get("betsapi") or {}).get("ativa") is True
                and (item.get("thestatsapi") or {}).get("ativa") is True
            )
            for item in comparacoes_por_partida.values()
        )
        amostra_comparativa_minima = bool(
            horas_comparacao >= 20
            and ambas_ativas >= 30
        )
        cobertura_unica = {
            "betsapi": comparacao_betsapi[
                "partidas_unicas_utilizaveis"
            ],
            "thestatsapi": comparacao_thestats[
                "partidas_unicas_utilizaveis"
            ],
        }
        lideres = []
        if any(cobertura_unica.values()):
            maior_cobertura = max(cobertura_unica.values())
            lideres = sorted(
                fonte for fonte, total in cobertura_unica.items()
                if total == maior_cobertura
            )
        comparacao_fontes_odds = {
            "versao": "comparacao-fontes-odds-v1",
            "horas_telemetria_direta": round(horas_comparacao, 3),
            "partidas_unicas_comparadas": len(comparacoes_por_partida),
            "partidas_unicas_com_betsapi_e_thestats_ativas": ambas_ativas,
            "amostra_operacional_minima": amostra_comparativa_minima,
            "criterios_amostra": {
                "minimo_horas": 20,
                "minimo_partidas_com_ambas_ativas": 30,
            },
            "estado": (
                "amostra_operacional_minima_atingida"
                if amostra_comparativa_minima
                else "amostra_direta_inicial"
            ),
            "lider_cobertura_provisorio": (
                lideres[0] if len(lideres) == 1 else None
            ),
            "empate_cobertura": lideres if len(lideres) > 1 else [],
            "fontes": {
                "packball": comparacao_packball,
                "betsapi": comparacao_betsapi,
                "thestatsapi": comparacao_thestats,
                "the_odds_api": comparacao_the_odds,
            },
            "avaliacao_substituicao_conclusiva": False,
            "observacao": (
                "Cobertura mede jogos processados e pode se repetir entre "
                "ciclos; a coorte de partidas unicas elimina repeticoes, "
                "mas cobertura isolada nao comprova valor dos sinais."
            ),
        }
        adiadas = somar("tarefas_adiadas")
        adiadas_distribuidas = sum(
            inteiro(item.get("tarefas_adiadas"))
            for item in ciclos
            if (item.get("ritmo_packball") or {}).get(
                "distribuicao_janela_ativa"
            ) is True
        )
        adiadas_capacidade = max(adiadas - adiadas_distribuidas, 0)
        bloqueios_fontes = somar("sinais_bloqueados_fontes")
        avaliacoes_gols = sum(
            inteiro((item.get("gols_antecipados") or {}).get("avaliacoes"))
            for item in ciclos
        )
        gerados_gols = sum(
            inteiro((item.get("gols_antecipados") or {}).get("gerados"))
            for item in ciclos
        )
        gargalos = {
            "qualidade_insuficiente": motivos.get(
                "qualidade_insuficiente", 0
            ),
            "fora_janelas_operacionais": motivos.get(
                "fora_janelas_operacionais", 0
            ),
            "sem_odds": sem_odds,
            "fontes_bloqueadas": bloqueios_fontes,
            "tarefas_adiadas_capacidade": adiadas_capacidade,
            "ritmo_packball_seguro": adiadas_distribuidas,
        }
        if ciclos and processadas == 0 and partidas_somadas > 0:
            gargalos["sem_partidas_elegiveis"] = sum(
                1 for valor in partidas_por_ciclo if valor > 0
            )
        if ciclos and (
            not partidas_por_ciclo or max(partidas_por_ciclo) <= 1
        ):
            gargalos["baixa_oferta_jogos_ao_vivo"] = sum(
                1 for valor in partidas_por_ciclo if valor <= 1
            )
        gargalos = {
            nome: quantidade
            for nome, quantidade in gargalos.items()
            if quantidade > 0
        }
        total_odds = com_odds + sem_odds
        total_agendadas = somar("tarefas_agendadas")
        taxa_processamento = (
            processadas / total_agendadas if total_agendadas else None
        )
        cobertura_odds = (
            com_odds / total_odds if total_odds else None
        )
        motivos_rejeicao = {
            nome: quantidade
            for nome, quantidade in motivos.items()
            if quantidade > 0
        }
        if bloqueios_fontes > 0:
            gargalo_principal = "fontes_bloqueadas"
        elif (
            taxa_processamento is not None
            and taxa_processamento < 0.80
            and adiadas_capacidade > 0
        ):
            gargalo_principal = "tarefas_adiadas_capacidade"
        elif todos_ciclos_zero_confirmado:
            gargalo_principal = None
        elif ciclos and (
            not partidas_por_ciclo or max(partidas_por_ciclo) <= 1
        ):
            gargalo_principal = "baixa_oferta_jogos_ao_vivo"
        elif avaliacoes_gols > 0 and gerados_gols == 0 and motivos_rejeicao:
            gargalo_principal = max(
                motivos_rejeicao.items(), key=lambda item: item[1]
            )[0]
        elif cobertura_odds is not None and cobertura_odds < 0.80:
            gargalo_principal = "sem_odds"
        elif processadas == 0 and partidas_somadas > 0:
            gargalo_principal = "sem_partidas_elegiveis"
        else:
            gargalo_principal = None
        total_ciclos = len(ciclos) + len(falhas)
        taxa_falhas = (
            len(falhas) / total_ciclos if total_ciclos else None
        )
        if not ciclos:
            estado = "sem_telemetria"
        elif (
            taxa_falhas is not None
            and taxa_falhas >= 0.20
            and not operacao_recuperada
        ):
            estado = "falha_operacional"
        elif todos_ciclos_zero_confirmado:
            estado = "sem_jogos_ao_vivo_confirmado"
        elif partidas_somadas == 0:
            estado = "sem_jogos_ao_vivo"
        elif gerados_gols > 0:
            estado = "oportunidades_geradas"
        elif gargalo_principal:
            estado = gargalo_principal
        else:
            estado = "sem_aprovacao_das_regras"

        return {
            "periodo_horas": horas,
            "inicio": inicio.isoformat(),
            "fim": agora.isoformat(),
            "estado": estado,
            "gargalo_principal": gargalo_principal,
            "gargalos": gargalos,
            "ciclos_concluidos": len(ciclos),
            "ciclos_falhos": len(falhas),
            "taxa_falhas": taxa_falhas,
            "sucessos_consecutivos_finais": sucessos_consecutivos_finais,
            "falhas_consecutivas_finais": falhas_consecutivas_finais,
            "operacao_recuperada": operacao_recuperada,
            "ciclos_zero_ao_vivo_confirmado": ciclos_zero_confirmado,
            "partidas_somadas": partidas_somadas,
            "partidas_media_por_ciclo": (
                partidas_somadas / len(ciclos) if ciclos else None
            ),
            "partidas_maximo_por_ciclo": (
                max(partidas_por_ciclo) if partidas_por_ciclo else 0
            ),
            "tarefas_agendadas": total_agendadas,
            "tarefas_processadas": processadas,
            "tarefas_adiadas": adiadas,
            "tarefas_adiadas_distribuidas": adiadas_distribuidas,
            "tarefas_adiadas_capacidade": adiadas_capacidade,
            "taxa_processamento": taxa_processamento,
            "tarefas_com_odds": com_odds,
            "tarefas_sem_odds": sem_odds,
            "cobertura_odds": cobertura_odds,
            "tarefas_odds_solicitadas": odds_solicitadas,
            "coletas_odds_sucesso": coletas_odds_sucesso,
            "fallback_odds_necessario": fallback_odds_necessario,
            "fallback_odds_atendeu": fallback_odds_atendeu,
            "fallback_odds_sem_cobertura": (
                fallback_odds_sem_cobertura
            ),
            "fontes_odds_utilizaveis": fontes_odds_utilizaveis,
            "fontes_fallback_odds": fontes_fallback_odds,
            "comparacao_fontes_odds": comparacao_fontes_odds,
            "acompanhamento_preco_pos_alerta": acompanhamento_preco,
            "avaliacoes_gols_antecipados": avaliacoes_gols,
            "gols_antecipados_gerados": gerados_gols,
            "motivos_gols_antecipados": motivos,
            "campos_ausentes": campos_ausentes,
            "sinais_bloqueados_fontes": bloqueios_fontes,
            "aplicacao_sinais": False,
        }

    def _gravar(self, nivel, evento, **dados):
        rotacionar_arquivo(
            self.caminho_log, self.limite_bytes, copias=5
        )
        registro = {
            "em": datetime.now().replace(microsecond=0).isoformat(),
            "nivel": nivel,
            "evento": evento,
            **dados,
        }
        with self.caminho_log.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        return registro

    def ciclo_sucesso(
        self, duracao_segundos, partidas, consumo_api, coleta=None
    ):
        self.falhas_consecutivas = 0
        self.ciclos_ok += 1
        coleta = dict(coleta or {})
        cache_api_atual = {
            "hits": max(
                int(consumo_api.get("cache_persistente_hits", 0) or 0), 0
            ),
            "gravacoes": max(
                int(
                    consumo_api.get(
                        "cache_persistente_gravacoes", 0
                    ) or 0
                ),
                0,
            ),
            "descartes": max(
                int(
                    consumo_api.get(
                        "cache_persistente_descartes", 0
                    ) or 0
                ),
                0,
            ),
            "falhas": max(
                int(
                    consumo_api.get(
                        "cache_persistente_falhas", 0
                    ) or 0
                ),
                0,
            ),
        }
        cache_api_ciclo = {
            chave: max(
                valor - self._cache_api_anterior.get(chave, 0), 0
            )
            for chave, valor in cache_api_atual.items()
        }
        self._cache_api_anterior = cache_api_atual
        return self._gravar(
            "info",
            "ciclo_concluido",
            duracao_segundos=round(duracao_segundos, 3),
            partidas=partidas,
            consumo_api_mes=consumo_api.get("mes", 0),
            consumo_api_dia=consumo_api.get(
                "total_dia", sum(consumo_api.get("dia", {}).values())
            ),
            limite_api_dia=consumo_api.get("limite_diario_seguro"),
            restante_api_dia=consumo_api.get("restante_seguro_dia"),
            cache_api_hits_ciclo=cache_api_ciclo["hits"],
            cache_api_gravacoes_ciclo=cache_api_ciclo["gravacoes"],
            cache_api_descartes_ciclo=cache_api_ciclo["descartes"],
            cache_api_falhas_ciclo=cache_api_ciclo["falhas"],
            tarefas_agendadas=coleta.get("agendadas"),
            tarefas_processadas=coleta.get("processadas"),
            tarefas_adiadas=coleta.get("adiadas"),
            duracao_detalhada_segundos=coleta.get(
                "duracao_detalhada_segundos"
            ),
            orcamento_detalhado_segundos=coleta.get("orcamento_segundos"),
            interrompido_por_reserva=coleta.get(
                "interrompido_por_reserva", False
            ),
            reserva_admissao_segundos=coleta.get(
                "reserva_admissao_segundos"
            ),
            duracoes_historicas_admissao=coleta.get(
                "duracoes_historicas_admissao"
            ),
            associacoes_api=coleta.get("associacoes_api") or {},
            enriquecimento_api_lote=coleta.get(
                "enriquecimento_api_lote"
            ) or {},
            thestatsapi_sombra=coleta.get("thestatsapi_sombra") or {},
            thestatsapi_odds=coleta.get("thestatsapi_odds") or {},
            betsapi=coleta.get("betsapi") or {},
            the_odds_api=coleta.get("the_odds_api") or {},
            tarefas_com_odds=coleta.get("tarefas_com_odds"),
            tarefas_sem_odds=coleta.get("tarefas_sem_odds"),
            tarefas_odds_solicitadas=coleta.get(
                "tarefas_odds_solicitadas", 0
            ),
            coletas_odds_sucesso=coleta.get(
                "coletas_odds_sucesso", 0
            ),
            fallback_odds_necessario=coleta.get(
                "fallback_odds_necessario", 0
            ),
            fallback_odds_atendeu=coleta.get(
                "fallback_odds_atendeu", 0
            ),
            fallback_odds_sem_cobertura=coleta.get(
                "fallback_odds_sem_cobertura", 0
            ),
            fontes_odds_utilizaveis=coleta.get(
                "fontes_odds_utilizaveis"
            ) or {},
            fontes_fallback_odds=coleta.get(
                "fontes_fallback_odds"
            ) or {},
            comparacoes_fontes_odds=coleta.get(
                "comparacoes_fontes_odds"
            ) or [],
            prioridades_asiaticas_processadas=coleta.get(
                "prioridades_asiaticas_processadas", 0
            ),
            odds_asiaticas_api_anexadas=coleta.get(
                "odds_asiaticas_api_anexadas", 0
            ),
            prioridades_asiaticas_sem_anexo=coleta.get(
                "prioridades_asiaticas_sem_anexo", 0
            ),
            alvos_um_escanteio_processados=coleta.get(
                "alvos_um_escanteio_processados", 0
            ),
            alvos_um_escanteio_anexados=coleta.get(
                "alvos_um_escanteio_anexados", 0
            ),
            perfil_agendamento=coleta.get("perfil_agendamento") or {},
            ritmo_packball=coleta.get("ritmo_packball") or {},
            idade_fila=coleta.get("idade_fila") or {},
            cobertura_temporal=coleta.get("cobertura_temporal") or {},
            gols_antecipados=coleta.get("gols_antecipados") or {},
            gols_capacidade_contextual_v2=coleta.get(
                "gols_capacidade_contextual_v2"
            ) or {},
            resgate_qualidade_api=coleta.get(
                "resgate_qualidade_api"
            ) or {},
            duracao_tarefa_media_segundos=coleta.get(
                "duracao_tarefa_media_segundos"
            ),
            duracao_tarefa_p95_segundos=coleta.get(
                "duracao_tarefa_p95_segundos"
            ),
            duracoes_tarefas_segundos=coleta.get(
                "duracoes_tarefas_segundos"
            ) or [],
            duracoes_etapas_detalhadas=coleta.get(
                "duracoes_etapas_detalhadas"
            ) or {},
            lista_packball=coleta.get("lista_packball") or {},
            pausa_preventiva=coleta.get("pausa_preventiva"),
            saude_api=consumo_api.get("saude_api") or {},
            sinais_bloqueados_fontes=coleta.get(
                "sinais_bloqueados_fontes", 0
            ),
            motivos_bloqueio_fontes=coleta.get(
                "motivos_bloqueio_fontes"
            ) or {},
            ciclos_ok=self.ciclos_ok,
        )

    def ciclo_progresso(self, etapa, **dados):
        return self._gravar(
            "info",
            "ciclo_em_andamento",
            etapa=str(etapa),
            **dados,
        )

    def historico_api_pausa_packball(self, diagnostico):
        diagnostico = dict(diagnostico or {})
        return self._gravar(
            (
                "info"
                if diagnostico.get("estado") in {
                    "persistido",
                    "sem_pareamentos_recentes",
                    "sem_pareamentos_ao_vivo",
                    "sem_estatisticas_normalizaveis",
                    "adiado_capacidade_api",
                }
                else "aviso"
            ),
            "historico_api_sombra_pausa_packball",
            **diagnostico,
        )

    def ciclo_pausado_packball(self, duracao_segundos, erro):
        self.falhas_consecutivas = 0
        return self._gravar(
            "info",
            "ciclo_pausado_packball",
            duracao_segundos=round(duracao_segundos, 3),
            motivo=str(erro),
        )

    def ciclo_erro(self, duracao_segundos, erro):
        self.falhas_consecutivas += 1
        self.ciclos_com_erro += 1
        return self._gravar(
            "erro",
            "ciclo_falhou",
            duracao_segundos=round(duracao_segundos, 3),
            erro=type(erro).__name__,
            mensagem=str(erro),
            falhas_consecutivas=self.falhas_consecutivas,
            ciclos_com_erro=self.ciclos_com_erro,
        )

    def processo_falhou(self, componente, erro):
        return self._gravar(
            "erro",
            "processo_falhou",
            componente=str(componente),
            erro=type(erro).__name__,
            mensagem=resumir_erro_seguro(erro),
        )

    def deve_recuperar_navegador(self, limite=3):
        return self.falhas_consecutivas >= limite

    def recuperacao(self, motivo):
        registro = self._gravar(
            "aviso",
            "recuperacao_navegador",
            motivo=motivo,
            falhas_consecutivas=self.falhas_consecutivas,
        )
        self.falhas_consecutivas = 0
        return registro

    def circuito_packball_ativado(self, motivo, pausado_ate):
        registro = self._gravar(
            "aviso",
            "circuit_breaker_packball",
            motivo=str(motivo),
            pausado_ate=(
                pausado_ate.isoformat()
                if hasattr(pausado_ate, "isoformat")
                else str(pausado_ate)
            ),
            falhas_consecutivas=self.falhas_consecutivas,
        )
        self.falhas_consecutivas = 0
        return registro

    def sessao_contexto(
        self,
        atualizada,
        motivo=None,
        expira_em=None,
        erro=None,
    ):
        return self._gravar(
            "info" if atualizada else "aviso",
            (
                "sessao_packball_persistida"
                if atualizada else "sessao_packball_nao_persistida"
            ),
            atualizada=bool(atualizada),
            motivo=motivo,
            expira_em=expira_em,
            erro=erro,
        )

    def supervisao_watchdog(self, reiniciado=False, pid=None, erro=None):
        return self._gravar(
            "erro" if erro else "aviso",
            (
                "watchdog_supervisao_falhou"
                if erro else "watchdog_reiniciado_pelo_monitor"
            ),
            reiniciado=bool(reiniciado),
            pid=int(pid) if pid is not None else None,
            erro=type(erro).__name__ if erro else None,
            mensagem=str(erro) if erro else None,
        )

    def modo_manutencao(self, estado, detalhes=None):
        return self._gravar(
            "info",
            f"modo_manutencao_{estado}",
            detalhes=dict(detalhes or {}),
        )

    def fonte_falhou(self, fonte, partida, erro, fallback):
        return self._gravar(
            "aviso",
            "fonte_falhou",
            fonte=fonte,
            partida=partida,
            erro=type(erro).__name__,
            mensagem=str(erro),
            fallback=fallback,
        )

    def backup_diario(self, caminho=None, criado=False, erro=None):
        return self._gravar(
            "erro" if erro else "info",
            "backup_diario_falhou" if erro else "backup_diario_verificado",
            caminho=str(caminho) if caminho else None,
            criado=bool(criado),
            erro=type(erro).__name__ if erro else None,
            mensagem=str(erro) if erro else None,
        )

    def backup_periodico(self, caminho=None, criado=False, erro=None):
        return self._gravar(
            "erro" if erro else "info",
            (
                "backup_periodico_falhou"
                if erro else "backup_periodico_verificado"
            ),
            caminho=str(caminho) if caminho else None,
            criado=bool(criado),
            erro=type(erro).__name__ if erro else None,
            mensagem=str(erro) if erro else None,
        )

    def compactacao_backup_legado(self, resultado=None, erro=None):
        resultado = dict(resultado or {})
        falhou = bool(erro or not resultado.get("saudavel", True))
        return self._gravar(
            "erro" if falhou else "info",
            (
                "compactacao_backup_legado_falhou"
                if falhou else "compactacao_backup_legado_concluida"
            ),
            resultado=resultado,
            erro=type(erro).__name__ if erro else None,
            mensagem=str(erro) if erro else None,
        )

    def compactacao_backup_operacional(self, tipo, resultado=None):
        resultado = dict(resultado or {})
        fallback = bool(resultado.get("fallback_original"))
        return self._gravar(
            "aviso" if fallback else "info",
            (
                "compactacao_backup_adiada_original_preservado"
                if fallback else "compactacao_backup_concluida"
            ),
            tipo=str(tipo),
            resultado=resultado,
            backup_utilizavel=bool(
                resultado.get("saudavel")
                or (
                    fallback
                    and resultado.get("original_valido")
                )
            ),
        )

    def manutencao_diaria(self, resultado=None, checkpoint=None, erro=None):
        return self._gravar(
            "erro" if erro else "info",
            (
                "manutencao_diaria_falhou"
                if erro else "manutencao_diaria_concluida"
            ),
            resultado=dict(resultado or {}),
            checkpoint=dict(checkpoint or {}),
            erro=type(erro).__name__ if erro else None,
            mensagem=str(erro) if erro else None,
        )

    def finalizacao_resultados(self, api, packball, sem_dado=None):
        sem_dado = dict(sem_dado or {})
        return self._gravar(
            (
                "aviso"
                if api.get("respostas_ausentes")
                or api.get("respostas_invalidas")
                or packball.get("erros")
                or sem_dado.get("encerrados_sem_dado")
                else "info"
            ),
            "finalizacao_resultados",
            api=dict(api),
            packball=dict(packball),
            sem_dado=sem_dado,
        )

    def resumo(self):
        if not self.caminho_log.exists():
            return {
                "ciclos": 0,
                "sucessos": 0,
                "erros": 0,
                "latencia_media_segundos": None,
                "uptime_percentual": None,
                "ultimo_evento": None,
                "watchdog_reinicios": 0,
                "watchdog_falhas_supervisao": 0,
                "watchdog_ultima_supervisao": None,
                "processos_falhas_fatais": 0,
                "processo_ultima_falha_fatal": None,
            }
        registros = []
        supervisoes_watchdog = []
        falhas_processos = []
        for linha in self.caminho_log.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if item.get("evento") in ("ciclo_concluido", "ciclo_falhou"):
                registros.append(item)
            if item.get("evento") in (
                "watchdog_reiniciado_pelo_monitor",
                "watchdog_supervisao_falhou",
            ):
                supervisoes_watchdog.append(item)
            if item.get("evento") == "processo_falhou":
                falhas_processos.append(item)
        sucessos = sum(
            1 for item in registros if item["evento"] == "ciclo_concluido"
        )
        erros = len(registros) - sucessos
        duracoes = [
            float(item.get("duracao_segundos") or 0) for item in registros
        ]
        return {
            "ciclos": len(registros),
            "sucessos": sucessos,
            "erros": erros,
            "latencia_media_segundos": (
                round(sum(duracoes) / len(duracoes), 3)
                if duracoes else None
            ),
            "latencia_p95_segundos": (
                round(percentil_valores(duracoes, 0.95), 3)
                if duracoes else None
            ),
            "latencia_maxima_segundos": (
                round(max(duracoes), 3) if duracoes else None
            ),
            "uptime_percentual": (
                round(sucessos / len(registros) * 100, 2)
                if registros else None
            ),
            "ultimo_evento": registros[-1] if registros else None,
            "watchdog_reinicios": sum(
                item.get("evento") == "watchdog_reiniciado_pelo_monitor"
                for item in supervisoes_watchdog
            ),
            "watchdog_falhas_supervisao": sum(
                item.get("evento") == "watchdog_supervisao_falhou"
                for item in supervisoes_watchdog
            ),
            "watchdog_ultima_supervisao": (
                supervisoes_watchdog[-1] if supervisoes_watchdog else None
            ),
            "processos_falhas_fatais": len(falhas_processos),
            "processo_ultima_falha_fatal": (
                falhas_processos[-1] if falhas_processos else None
            ),
        }
