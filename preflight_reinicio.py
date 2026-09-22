import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from backup_banco import verificar_backup_espelho

from api_football import auditar_cache_api_football, verificar_contador_uso
from avaliacao_contexto import auditar_historico_avaliacao_contexto
from auditoria_relogios_coortes import verificar_relogios_coortes
from banco import auditar_compatibilidade
from configuracao import obter_limites_risco, validar_configuracao
from calibracao import POLITICA_CALIBRACAO_VERSAO
from carteira_operacional import auditar_carteira_operacional
from controle_acesso_packball import verificar_acesso_packball
from controle_sistema import ler_modo_manutencao
from dependencias import verificar_dependencias
from linhagem_regras import (
    auditar_linhagem_regra,
    fingerprint_vinculado_no_banco,
    resumir_cobertura_linhagem_sinais,
)
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS
from packball_login import diagnosticar_storage_state
from versoes_gol_ft_reforcado import (
    versao_regra_operacional,
    versoes_regras_operacionais,
)
from relatorio_simulacoes import auditar_experimento_filtro
from hipoteses_sombra import auditar_hipoteses_sombra
from exploracao_sombra import auditar_definicao_exploracao_gols
from validacao_gols_antecipados import (
    auditar_validacao_gols_antecipados,
)
from integridade_calibracao import (
    auditar_frescor_calibracoes_por_mercado,
)
from mercados import MERCADOS_CALIBRADOS
from pontuacao_contexto_sombra import avaliar_pontuacao_contexto_sombra
from pontuacao_longa_sombra import avaliar_pontuacao_longa_sombra
from pontuacao_sombra import avaliar_pontuacao_sombra
from treino_processo_isolado import verificar_worker_treino_isolado
from watchdog import (
    auditar_notificacoes_operacionais,
    auditar_integridade_telegram,
    verificar_armazenamento,
    verificar_backup_diario,
    verificar_coleta,
)


# A suíte isolada cresceu para mais de 170 módulos. O limite anterior de cinco
# minutos podia terminar durante as três confirmações obrigatórias de uma
# falha transitória, classificando recuperação como timeout. Quinze minutos
# preservam o fail closed e dão tempo para concluir todas as confirmações.
TEMPO_MAXIMO_TESTES_SEGUNDOS = 900


def verificar_sessao(caminho, agora=None):
    caminho = Path(caminho)
    agora = agora or datetime.now()
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"saudavel": False, "motivo": "sessao_ausente"}
    except (OSError, json.JSONDecodeError):
        return {"saudavel": False, "motivo": "sessao_invalida"}
    return diagnosticar_storage_state(dados, agora=agora)


def verificar_banco(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return {"saudavel": False, "motivo": "banco_ausente"}
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        integridade = [
            item[0] for item in conexao.execute("PRAGMA quick_check")
        ]
        compatibilidade = auditar_compatibilidade(conexao)
    except (OSError, sqlite3.Error) as erro:
        return {
            "saudavel": False,
            "motivo": "banco_inacessivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()
    saudavel = integridade == ["ok"] and compatibilidade["compativel"]
    return {
        "saudavel": saudavel,
        "motivo": None if saudavel else "banco_incompleto_ou_corrompido",
        "quick_check": integridade,
        "tabelas_ausentes": compatibilidade["tabelas_ausentes"],
        "colunas_ausentes": compatibilidade["colunas_ausentes"],
        "gatilhos_ausentes": compatibilidade["gatilhos_ausentes"],
        "indices_ausentes": compatibilidade["indices_ausentes"],
        "violacoes_chaves_estrangeiras": compatibilidade[
            "violacoes_chaves_estrangeiras"
        ],
    }


def verificar_carteira_operacional(caminho, pasta, env=None):
    """Valida a época persistida sem impedir uma troca segura no reinício."""
    caminho = Path(caminho)
    if not caminho.exists():
        return {
            "saudavel": False,
            "estado": "banco_ausente",
            "motivo": "carteira_operacional_indisponivel",
        }
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        resultado = auditar_carteira_operacional(
            conexao, env if env is not None else os.environ, pasta
        )
    except (OSError, sqlite3.Error) as erro:
        return {
            "saudavel": False,
            "estado": "auditoria_indisponivel",
            "motivo": "carteira_operacional_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()
    resultado = dict(resultado)
    resultado["saudavel_para_reinicio"] = bool(resultado.get("saudavel"))
    return resultado


def verificar_experimento_filtro(caminho, ativo):
    if not ativo:
        return {
            "saudavel": True,
            "estado": "desativado",
            "motivo": None,
        }
    conexao = None
    try:
        uri = Path(caminho).resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        return auditar_experimento_filtro(
            conexao,
            VERSAO_REGRAS,
            float(os.getenv("PONTUACAO_MINIMA_SINAL_TESTE", "70")),
            float(os.getenv("QUALIDADE_MINIMA_SINAL_TESTE", "0")),
            ativo=True,
            regra_fingerprint=fingerprint_vinculado_no_banco(
                conexao, VERSAO_REGRAS
            ),
            exigir_linhagem=True,
        )
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "experimento_filtro_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def verificar_hipoteses_sombra(caminho):
    conexao = None
    try:
        uri = Path(caminho).resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        return auditar_hipoteses_sombra(conexao, VERSAO_REGRAS)
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "hipoteses_sombra_indisponiveis",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def verificar_definicao_exploracao_gols(caminho):
    conexao = None
    try:
        uri = Path(caminho).resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        return auditar_definicao_exploracao_gols(conexao)
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "definicao_exploracao_gols_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def verificar_validacao_gols_antecipados(caminho):
    conexao = None
    try:
        uri = Path(caminho).resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        return auditar_validacao_gols_antecipados(
            conexao, exigir_registro=True
        )
    except (
        OSError, sqlite3.Error, TypeError, ValueError, RuntimeError
    ) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "validacao_gols_antecipados_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def verificar_modelos_sombra(caminho):
    """Impede reinício com um modelo experimental corrompido.

    A ausência de modelo ainda é válida enquanto a amostra está sendo formada.
    Quando existe um envelope congelado, porém, tanto o modelo temporal original
    quanto o challenger contextual precisam passar pela verificação de hash,
    versão, mercado e conjunto de features feita pelos próprios módulos.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return {
            "saudavel": False,
            "motivo": "banco_ausente",
        }
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        regras = {
            mercado: versao_regra_operacional(mercado)
            for mercado in MERCADOS_CALIBRADOS
        }
        temporal = avaliar_pontuacao_sombra(conexao, regras)
        contexto = avaliar_pontuacao_contexto_sombra(conexao, regras)
        longa = avaliar_pontuacao_longa_sombra(conexao, regras)
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "motivo": "modelos_sombra_indisponiveis",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()
    saudavel = bool(
        temporal.get("integro")
        and contexto.get("integro")
        and longa.get("integro")
    )
    return {
        "saudavel": saudavel,
        "motivo": None if saudavel else "modelos_sombra_inconsistentes",
        "pontuacao_temporal_integra": bool(temporal.get("integro")),
        "pontuacao_contexto_integra": bool(contexto.get("integro")),
        "pontuacao_longa_integra": bool(longa.get("integro")),
        "modelos_temporais": list(
            temporal.get("mercados_com_modelo") or []
        ),
        "modelos_contextuais": list(
            contexto.get("mercados_com_modelo") or []
        ),
        "modelos_longos": list(
            longa.get("mercados_com_modelo") or []
        ),
        "mercados_temporais_inconsistentes": [
            mercado
            for mercado, item in (temporal.get("por_mercado") or {}).items()
            if not item.get("integro")
        ],
        "mercados_contextuais_inconsistentes": [
            mercado
            for mercado, item in (contexto.get("por_mercado") or {}).items()
            if not item.get("integro")
        ],
        "mercados_longos_inconsistentes": [
            mercado
            for mercado, item in (longa.get("por_mercado") or {}).items()
            if not item.get("integro")
        ],
    }


def verificar_historico_contexto(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return {"saudavel": False, "motivo": "banco_ausente"}
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        return auditar_historico_avaliacao_contexto(conexao)
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "motivo": "historico_avaliacao_contexto_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()


def verificar_integridade_alertas(caminho, agora=None):
    caminho = Path(caminho)
    if not caminho.exists():
        return {"saudavel": False, "motivo": "banco_ausente"}
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        auditoria = auditar_integridade_telegram(
            conexao, agora=agora or datetime.now()
        )
    except (OSError, sqlite3.Error) as erro:
        return {
            "saudavel": False,
            "motivo": "integridade_alertas_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()
    # Uma entrega ambigua fica em quarentena e nunca e reenviada
    # automaticamente. Ela exige reconciliacao manual, mas nao torna
    # inseguro iniciar a coleta quando toda a cadeia estrutural continua
    # integra (sem prova invalida/duplicada ou resultado duplicado).
    contida_para_reinicio = bool(
        (auditoria.get("envios_incertos") or auditoria.get("resultados_sem_aviso"))
        and not auditoria.get("avisos_sem_resultado")
        and not auditoria.get("erros_persistentes")
        and not auditoria.get("correcoes_pendentes")
        and not auditoria.get("resultados_duplicados")
        and not auditoria.get("confirmacoes_telegram_invalidas")
        and not auditoria.get("confirmacoes_telegram_duplicadas")
    )
    return {
        **auditoria,
        "saudavel_para_reinicio": bool(
            auditoria["saudavel"] or contida_para_reinicio
        ),
        "motivo": (
            None if auditoria["saudavel"]
            else "integridade_telegram_inconsistente"
        ),
    }


def verificar_notificacoes_operacionais(caminho, agora=None):
    caminho = Path(caminho)
    if not caminho.exists():
        return {"saudavel": False, "motivo": "banco_ausente"}
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        auditoria = auditar_notificacoes_operacionais(
            conexao, agora=agora or datetime.now()
        )
    except (OSError, sqlite3.Error) as erro:
        return {
            "saudavel": False,
            "motivo": "notificacoes_operacionais_indisponiveis",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()
    contida_para_reinicio = bool(
        (
            auditoria.get("disjuntor_pausado")
            or auditoria.get("erros_persistentes")
        )
        and not auditoria.get("incertas")
        and not auditoria.get("provas_invalidas")
        and not auditoria.get("provas_duplicadas")
    )
    return {
        **auditoria,
        "saudavel_para_reinicio": bool(
            auditoria["saudavel"] or contida_para_reinicio
        ),
        "motivo": (
            None if auditoria["saudavel"]
            else "notificacoes_operacionais_inconsistentes"
        ),
    }


def verificar_frescor_calibracoes(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return {
            "saudavel": False,
            "saudavel_para_reinicio": False,
            "motivo": "banco_ausente",
        }
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        conexao.row_factory = sqlite3.Row
        auditoria = auditar_frescor_calibracoes_por_mercado(
            conexao,
            {
                mercado: versao_regra_operacional(mercado)
                for mercado in MERCADOS_CALIBRADOS
            },
            obter_limites_risco(),
            somente_ativas=False,
            politica_versao=POLITICA_CALIBRACAO_VERSAO,
            somente_executaveis=True,
        )
    except (OSError, sqlite3.Error, ValueError) as erro:
        return {
            "saudavel": False,
            "saudavel_para_reinicio": False,
            "motivo": "frescor_calibracoes_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()
    requer_reconciliacao = not auditoria["saudavel"]
    return {
        **auditoria,
        "saudavel_para_reinicio": True,
        "requer_reconciliacao": requer_reconciliacao,
        "estado": (
            "requer_reconciliacao_no_inicio"
            if requer_reconciliacao else "atualizado"
        ),
        "motivo": (
            "calibracao_desatualizada"
            if requer_reconciliacao else None
        ),
    }


def verificar_cache_api(caminho, agora=None):
    caminho = Path(caminho)
    if not caminho.exists():
        return {"saudavel": False, "motivo": "banco_ausente"}
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        auditoria = auditar_cache_api_football(
            conexao, agora=agora or datetime.now()
        )
    except (OSError, sqlite3.Error, ValueError) as erro:
        return {
            "saudavel": False,
            "motivo": "cache_api_football_indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()
    return {
        **auditoria,
        "motivo": (
            None if auditoria["saudavel"]
            else "cache_api_football_inconsistente"
        ),
    }


def verificar_linhagem(caminho_banco, pasta):
    caminho_banco = Path(caminho_banco)
    conexao = None
    try:
        uri = caminho_banco.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        por_versao = {}
        for regra_versao in versoes_regras_operacionais():
            auditoria = auditar_linhagem_regra(
                conexao, pasta, regra_versao, VERSAO_FEATURES
            )
            cobertura = resumir_cobertura_linhagem_sinais(
                conexao, regra_versao
            )
            sinais_existentes = int(conexao.execute(
                "SELECT COUNT(*) FROM sinais WHERE regra_versao=?",
                (regra_versao,),
            ).fetchone()[0])
            nova_versao_segura = bool(
                auditoria.get("estado") == "nao_registrada"
                and auditoria.get("ancora_presente") is False
                and sinais_existentes == 0
            )
            por_versao[regra_versao] = {
                **auditoria,
                "saudavel": bool(
                    nova_versao_segura
                    or (
                        auditoria["saudavel"]
                        and cobertura["saudavel"]
                    )
                ),
                "estado_preflight": (
                    "nova_versao_pendente_registro_no_inicio"
                    if nova_versao_segura else auditoria.get("estado")
                ),
                "sinais_existentes": sinais_existentes,
                "cobertura_sinais": cobertura,
            }
    except (OSError, sqlite3.Error, ValueError) as erro:
        return {
            "saudavel": False,
            "estado": "indisponivel",
            "erro": type(erro).__name__,
        }
    finally:
        if conexao is not None:
            conexao.close()
    saudavel = all(item["saudavel"] for item in por_versao.values())
    return {
        "saudavel": saudavel,
        "estado": "valido" if saudavel else "linhagem_inconsistente",
        "por_versao": por_versao,
    }


def _listar_modulos_testes(pasta):
    return sorted(
        arquivo.stem
        for arquivo in Path(pasta).glob("test_*.py")
        if arquivo.is_file()
    )


def _resumir_saida_processo(processo, limite=80):
    return "\n".join(
        parte.strip()
        for parte in (processo.stdout, processo.stderr)
        if parte and parte.strip()
    ).splitlines()[-limite:]


def executar_testes(
    pasta, timeout=TEMPO_MAXIMO_TESTES_SEGUNDOS,
    confirmacoes_falha_transitoria=3,
):
    ambiente_testes = os.environ.copy()
    # O processo de preflight carrega a configuração operacional antes de
    # chegar aqui. A suíte offline deve validar os contratos padrão, sem
    # ativar integrações, rotinas automáticas ou perfis de produção por
    # herança. Remova somente as chaves pertencentes ao .env do projeto e
    # preserve PATH, TEMP e as demais variáveis necessárias ao Python.
    for chave in dotenv_values(Path(pasta) / ".env"):
        ambiente_testes.pop(chave, None)
    # A suíte geral de ``test_seletor_pre_live`` valida o contrato V11. O
    # perfil de retorno dia 30 possui testes próprios que carregam ambos os
    # perfis de forma isolada. Não deixe a configuração operacional ativa
    # mudar, por herança, o módulo que a suíte geral pretende validar.
    ambiente_testes["PRELIVE_PERFIL_SELECAO"] = "v11"
    # ``load_dotenv`` pode ser exercitado por testes de inicializacao dentro
    # da propria suite. Fixar aqui os defaults contratuais impede que esse
    # carregamento tardio reative os filtros operacionais do arquivo real.
    ambiente_testes["PRELIVE_FILTRO_PRECISO_ATIVO"] = "0"
    ambiente_testes["PRELIVE_MERCADOS_TIME_ATIVOS"] = "1"
    ambiente_testes["PRELIVE_MULTIPLAS_TRES_PERNAS_ATIVAS"] = "1"
    ambiente_testes["GOL_FT_REFORCADO_OFICIAL_ATIVO"] = "0"
    ambiente_testes["GOL_HT_PRINCIPAL_OFICIAL_ATIVO"] = "0"
    ambiente_testes["AVISO_AGUARDAR_ODD_MERCADOS"] = (
        "gol_ft,gol_ht,proximo_gol"
    )
    modulos = _listar_modulos_testes(pasta)
    if not modulos:
        return {
            "saudavel": False,
            "motivo": "testes_ausentes",
            "modo": "isolado_por_modulo",
            "modulos": 0,
        }
    # Python 3.14 + greenlet/Playwright pode sofrer falha nativa quando toda a
    # suíte compartilha um único interpretador. Também há testes que alteram
    # módulos/configuração durante o próprio caso. Um processo descartável por
    # arquivo mantém a cobertura completa, impede vazamento entre módulos e faz
    # uma falha nativa apontar exatamente para sua origem.
    inicio = time.monotonic()
    concluidos = 0
    falhas_transitorias = []
    for modulo in modulos:
        restante = float(timeout) - (time.monotonic() - inicio)
        if restante <= 0:
            return {
                "saudavel": False,
                "motivo": "testes_timeout",
                "modo": "isolado_por_modulo",
                "modulo": modulo,
                "modulos_concluidos": concluidos,
                "modulos": len(modulos),
            }
        try:
            processo = subprocess.run(
                [sys.executable, "-m", "unittest", "-q", modulo],
                cwd=str(pasta),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=ambiente_testes,
                timeout=restante,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "saudavel": False,
                "motivo": "testes_timeout",
                "modo": "isolado_por_modulo",
                "modulo": modulo,
                "modulos_concluidos": concluidos,
                "modulos": len(modulos),
            }
        if processo.returncode:
            codigo = int(processo.returncode)
            falha_nativa = codigo < 0 or codigo > 255
            falha_inicial = {
                "codigo": codigo,
                "falha_nativa": falha_nativa,
                "resumo": _resumir_saida_processo(processo),
            }
            # Uma falha nativa nunca e tolerada. Para uma falha comum isolada,
            # valide novamente o mesmo modulo em tres interpretadores novos.
            # Isso absorve corrupcoes transitorias observadas no Python 3.14,
            # sem mascarar regressao deterministica: basta uma confirmacao
            # falhar para o reinicio continuar bloqueado.
            if falha_nativa or confirmacoes_falha_transitoria <= 0:
                return {
                    "saudavel": False,
                    "motivo": "testes_falharam",
                    **falha_inicial,
                    "modo": "isolado_por_modulo",
                    "modulo": modulo,
                    "modulos_concluidos": concluidos,
                    "modulos": len(modulos),
                }
            confirmacoes_aprovadas = 0
            for _ in range(int(confirmacoes_falha_transitoria)):
                restante = float(timeout) - (time.monotonic() - inicio)
                if restante <= 0:
                    return {
                        "saudavel": False,
                        "motivo": "testes_timeout",
                        "modo": "isolado_por_modulo",
                        "modulo": modulo,
                        "modulos_concluidos": concluidos,
                        "modulos": len(modulos),
                        "falha_inicial": falha_inicial,
                        "confirmacoes_aprovadas": confirmacoes_aprovadas,
                    }
                try:
                    confirmacao = subprocess.run(
                        [sys.executable, "-m", "unittest", "-q", modulo],
                        cwd=str(pasta),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        env=ambiente_testes,
                        timeout=restante,
                        creationflags=getattr(
                            subprocess, "CREATE_NO_WINDOW", 0
                        ),
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    return {
                        "saudavel": False,
                        "motivo": "testes_timeout",
                        "modo": "isolado_por_modulo",
                        "modulo": modulo,
                        "modulos_concluidos": concluidos,
                        "modulos": len(modulos),
                        "falha_inicial": falha_inicial,
                        "confirmacoes_aprovadas": confirmacoes_aprovadas,
                    }
                if confirmacao.returncode:
                    codigo_confirmacao = int(confirmacao.returncode)
                    return {
                        "saudavel": False,
                        "motivo": "testes_falharam",
                        "codigo": codigo_confirmacao,
                        "falha_nativa": (
                            codigo_confirmacao < 0
                            or codigo_confirmacao > 255
                        ),
                        "modo": "isolado_por_modulo",
                        "modulo": modulo,
                        "modulos_concluidos": concluidos,
                        "modulos": len(modulos),
                        "resumo": _resumir_saida_processo(confirmacao),
                        "falha_inicial": falha_inicial,
                        "confirmacoes_aprovadas": confirmacoes_aprovadas,
                    }
                confirmacoes_aprovadas += 1
            falhas_transitorias.append(
                {
                    "modulo": modulo,
                    "falha_inicial": falha_inicial,
                    "confirmacoes_aprovadas": confirmacoes_aprovadas,
                }
            )
        concluidos += 1
    return {
        "saudavel": True,
        "motivo": None,
        "codigo": 0,
        "falha_nativa": False,
        "modo": "isolado_por_modulo",
        "modulos_concluidos": concluidos,
        "modulos": len(modulos),
        "duracao_segundos": round(time.monotonic() - inicio, 3),
        "resumo": [f"{concluidos} modulos isolados aprovados"],
        "recuperou_falha_transitoria": bool(falhas_transitorias),
        "falhas_transitorias": falhas_transitorias,
        "confirmacoes_falha_transitoria": int(
            confirmacoes_falha_transitoria
        ),
    }


def ajustar_coleta_em_manutencao(coleta, modo_manutencao):
    coleta = dict(coleta or {})
    modo_manutencao = modo_manutencao or {}
    evento_planejado = (
        coleta.get("ultimo_evento") == "modo_manutencao_solicitado"
    )
    ciclo_final_apos_pedido = False
    if coleta.get("ultimo_evento") == "ciclo_concluido":
        try:
            ciclo_final_apos_pedido = (
                datetime.fromisoformat(coleta["ultimo_sucesso_em"])
                >= datetime.fromisoformat(
                    modo_manutencao["solicitado_em"]
                )
            )
        except (KeyError, TypeError, ValueError):
            ciclo_final_apos_pedido = False
    pausa_planejada = (
        bool(modo_manutencao.get("ativo"))
        and (
            (
                coleta.get("motivo") == "coleta_parada"
                and (evento_planejado or ciclo_final_apos_pedido)
                and bool(coleta.get("ultimo_sucesso_em"))
            )
            # Uma parada solicitada durante o primeiro ciclo pode encerrar o
            # processo antes de existir um `ciclo_concluido`. Isso não é falha
            # de coleta: o próximo início deve poder refazer o ciclo inteiro.
            or (
                coleta.get("motivo") == "sem_ciclo_concluido"
                and coleta.get("ultimo_evento") == "ciclo_em_andamento"
            )
        )
        and int(coleta.get("falhas_consecutivas") or 0) <= 1
    )
    if pausa_planejada:
        coleta.update({
            "saudavel": True,
            "motivo_original": "coleta_parada",
            "motivo": None,
            "estado": "pausa_planejada_para_manutencao",
        })
    return coleta


def ajustar_coleta_para_reinicio(
    coleta,
    permitir=False,
    acesso_packball=None,
    sessao_packball=None,
    sessao_atualizada_em=None,
):
    """Não transforma a própria parada recuperável em bloqueio de partida.

    O restante do preflight continua obrigatório. Este ajuste só é usado pelo
    fluxo que efetivamente iniciará os processos e não pelo diagnóstico
    somente leitura executado na linha de comando.
    """
    coleta = dict(coleta or {})
    acesso_packball = acesso_packball or {}
    sessao_packball = sessao_packball or {}
    circuito_lista_expirado = bool(
        acesso_packball.get("saudavel") is True
        and acesso_packball.get("ativo") is False
        and acesso_packball.get("motivo_persistido")
        == "lista_packball_nao_validada"
        and float(acesso_packball.get("restante_segundos") or 0) <= 0
    )
    sessao_renovada_apos_falha = False
    try:
        ultimo_progresso = datetime.fromisoformat(
            coleta.get("ultimo_progresso_em") or ""
        )
        atualizada_em = datetime.fromisoformat(
            sessao_atualizada_em or ""
        )
        sessao_renovada_apos_falha = bool(
            sessao_packball.get("saudavel") is True
            and acesso_packball.get("saudavel") is True
            and acesso_packball.get("ativo") is False
            and coleta.get("ultimo_evento")
            == "modo_manutencao_solicitado"
            and atualizada_em > ultimo_progresso
        )
    except (TypeError, ValueError):
        sessao_renovada_apos_falha = False
    recuperavel = bool(
        coleta.get("motivo") == "coleta_parada"
        or (
            coleta.get("motivo") == "falhas_consecutivas"
            and (
                circuito_lista_expirado
                or sessao_renovada_apos_falha
            )
        )
    )
    if (
        permitir
        and not coleta.get("saudavel")
        and recuperavel
    ):
        motivo_original = coleta.get("motivo")
        coleta.update({
            "saudavel": True,
            "motivo_original": motivo_original,
            "motivo": None,
            "estado": (
                "recuperavel_apos_sessao_packball_renovada"
                if sessao_renovada_apos_falha
                else "recuperavel_apos_circuit_breaker_packball"
                if motivo_original == "falhas_consecutivas"
                else "recuperavel_apos_reinicio"
            ),
            "requer_reinicio": True,
        })
    return coleta


def executar_preflight(
    pasta,
    rodar_testes=True,
    agora=None,
    permitir_coleta_parada_para_reinicio=False,
):
    pasta = Path(pasta)
    agora = agora or datetime.now()
    load_dotenv(pasta / ".env")
    configuracao = validar_configuracao()
    modo_manutencao = ler_modo_manutencao(pasta)
    caminho_sessao = pasta / "packball_session.json"
    estado_sessao_packball = verificar_sessao(
        caminho_sessao, agora=agora
    )
    try:
        sessao_atualizada_em = datetime.fromtimestamp(
            caminho_sessao.stat().st_mtime
        ).isoformat()
    except OSError:
        sessao_atualizada_em = None
    estado_acesso_packball = verificar_acesso_packball(
        pasta / "packball_acesso_estado.json", agora
    )
    estado_coleta = ajustar_coleta_em_manutencao(
        verificar_coleta(
            pasta / "monitor_eventos.jsonl", agora=agora
        ),
        modo_manutencao,
    )
    estado_coleta = ajustar_coleta_para_reinicio(
        estado_coleta,
        permitir=permitir_coleta_parada_para_reinicio,
        acesso_packball=estado_acesso_packball,
        sessao_packball=estado_sessao_packball,
        sessao_atualizada_em=sessao_atualizada_em,
    )
    verificacoes = {
        "worker_treino_isolado": verificar_worker_treino_isolado(),
        "dependencias": verificar_dependencias(
            pasta / "requirements.lock.txt"
        ),
        "configuracao": {
            "saudavel": bool(configuracao["valida"]),
            "erros": configuracao["erros"],
            "avisos": configuracao["avisos"],
        },
        "sessao_packball": estado_sessao_packball,
        "acesso_packball": estado_acesso_packball,
        "banco": verificar_banco(pasta / "monitor_packball.db"),
        "relogios_coortes": verificar_relogios_coortes(pasta),
        "carteira_operacional": verificar_carteira_operacional(
            pasta / "monitor_packball.db", pasta
        ),
        "experimento_filtro": verificar_experimento_filtro(
            pasta / "monitor_packball.db",
            bool(
                (configuracao.get("recursos") or {}).get("sinais_teste")
            ),
        ),
        "hipoteses_sombra": verificar_hipoteses_sombra(
            pasta / "monitor_packball.db"
        ),
        "definicao_exploracao_gols": (
            verificar_definicao_exploracao_gols(
                pasta / "monitor_packball.db"
            )
        ),
        "validacao_gols_antecipados": (
            verificar_validacao_gols_antecipados(
                pasta / "monitor_packball.db"
            )
        ),
        "modelos_sombra": verificar_modelos_sombra(
            pasta / "monitor_packball.db"
        ),
        "historico_contexto": verificar_historico_contexto(
            pasta / "monitor_packball.db"
        ),
        "integridade_telegram": verificar_integridade_alertas(
            pasta / "monitor_packball.db", agora
        ),
        "notificacoes_operacionais": verificar_notificacoes_operacionais(
            pasta / "monitor_packball.db", agora
        ),
        "frescor_calibracoes": verificar_frescor_calibracoes(
            pasta / "monitor_packball.db"
        ),
        "cache_api_football": verificar_cache_api(
            pasta / "monitor_packball.db", agora
        ),
        "linhagem_regra": verificar_linhagem(
            pasta / "monitor_packball.db", pasta
        ),
        "backup": verificar_backup_diario(pasta / "backups", agora),
        "backup_espelho": verificar_backup_espelho(
            pasta / "backups",
            os.getenv("BACKUP_ESPELHO_DIRETORIO") or None,
            agora=agora,
            verificar_integridade=True,
        ),
        "coleta": estado_coleta,
        "armazenamento": verificar_armazenamento(
            pasta, pasta / "monitor_packball.db"
        ),
        "contador_api": verificar_contador_uso(
            pasta / "api_football_uso.json"
        ),
    }
    if rodar_testes:
        verificacoes["testes"] = executar_testes(pasta)
    pronto = all(
        item.get("saudavel_para_reinicio", item.get("saudavel"))
        for item in verificacoes.values()
    )
    return {
        "pronto_para_reinicio": pronto,
        "verificado_em": agora.replace(microsecond=0).isoformat(),
        "verificacoes": verificacoes,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Pré-voo somente leitura para reinício do Bot PackBall."
    )
    parser.add_argument(
        "--sem-testes",
        action="store_true",
        help="Pula a suíte offline; não recomendado para reinício real.",
    )
    argumentos = parser.parse_args()
    resultado = executar_preflight(
        Path(__file__).parent, rodar_testes=not argumentos.sem_testes
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado["pronto_para_reinicio"] else 1)


if __name__ == "__main__":
    main()
