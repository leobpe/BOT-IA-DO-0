"""Montagem do resumo diario de operacao do watchdog.

Reune os numeros do dia, descreve o filtro ativo, fatia a mensagem nos
limites do Telegram e cuida do manifesto de entrega. Nao envia nada: quem
entrega e atualizar_resumo_diario, que permanece em watchdog.py.

Extraido de watchdog.py, que reexporta estes nomes.
"""

import hashlib
import sqlite3
from banco import resumir_risco_alertas_oficiais_conexao
from configuracao import obter_limites_risco
from datetime import datetime
from linhagem_regras import fingerprint_vinculado_no_banco
from mercados import (
    MERCADOS_CALIBRADOS,
    ROTULOS_MERCADOS,
)
from motor_sinais import VERSAO_REGRAS
from pathlib import Path
from versoes_gol_ft_reforcado import versao_regra_operacional as versao_regra_para_mercado


MERCADOS_VALIDACAO = MERCADOS_CALIBRADOS
LIMITE_PARTE_RESUMO_DIARIO = 3900
VERSAO_ENTREGA_RESUMO_DIARIO = "resumo-diario-compacto-v2"


def resumir_operacao_diaria(
    caminho_banco, agora=None, destinos_resultado=None,
):
    """Resume o dia ativo sem alterar o banco nem consumir a API externa."""
    agora = (agora or datetime.now()).replace(microsecond=0)
    dia = agora.date().isoformat()
    caminho_banco = Path(caminho_banco)
    destinos_resultado = tuple(dict.fromkeys(
        str(destino).strip()
        for destino in (destinos_resultado or ())
        if str(destino).strip()
    ))
    filtro_destinos = ""
    parametros_destinos = ()
    if destinos_resultado:
        canais_visiveis = tuple(destinos_resultado) + tuple(
            f"{destino}:teste" for destino in destinos_resultado
        )
        marcadores = ", ".join("?" for _ in canais_visiveis)
        filtro_destinos = f" AND e.canal IN ({marcadores})"
        parametros_destinos = canais_visiveis
    resumo = {
        "saudavel": False,
        "dia": dia,
        "regra_versao": VERSAO_REGRAS,
        "regra_versoes_por_mercado": {
            mercado: versao_regra_para_mercado(mercado)
            for mercado in MERCADOS_VALIDACAO
        },
        "aprovados_novos": 0,
        "pendentes": 0,
        "pendentes_por_mercado": {},
        "resultados": {
            "total": 0, "greens": 0, "reds": 0,
            "retorno_unidades": 0.0, "roi": None,
        },
        "resultados_por_mercado": {},
        "alertas_oficiais": 0,
        "simulacoes": 0,
        "risco_oficial": {},
    }
    if not caminho_banco.exists():
        resumo["motivo"] = "banco_ausente"
        return resumo
    try:
        conexao = sqlite3.connect(
            f"file:{caminho_banco.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=10,
        )
        conexao.row_factory = sqlite3.Row
        limites_risco = obter_limites_risco()
        regra_fingerprint = fingerprint_vinculado_no_banco(
            conexao, VERSAO_REGRAS
        )
        if regra_fingerprint is None:
            resumo["motivo"] = "linhagem_regra_indisponivel"
            return resumo
        resumo["regra_fingerprint"] = regra_fingerprint
        fingerprints = {}
        for versao in set(
            resumo["regra_versoes_por_mercado"].values()
        ):
            fingerprint = fingerprint_vinculado_no_banco(conexao, versao)
            if fingerprint:
                fingerprints[versao] = fingerprint
        resumo["regra_fingerprints"] = fingerprints
        pares_ativos = [
            (mercado, versao, fingerprints[versao])
            for mercado, versao in (
                resumo["regra_versoes_por_mercado"].items()
            )
            if versao in fingerprints
        ]
        filtro_regras_ativas = " OR ".join(
            "(s.mercado=? AND s.regra_versao=? "
            "AND s.regra_fingerprint=?)"
            for _ in pares_ativos
        )
        parametros_regras_ativas = [
            valor
            for par in pares_ativos
            for valor in par
        ]
        risco_oficial = resumir_risco_alertas_oficiais_conexao(
            conexao, agora
        )
        risco_oficial.update({
            "limite_reds_consecutivos": (
                limites_risco.limite_reds_consecutivos_oficiais
            ),
            "limite_perda_diaria": (
                limites_risco.limite_perda_diaria_oficial
            ),
        })
        motivos_bloqueio = []
        if (
            risco_oficial["reds_consecutivos_24h"]
            >= risco_oficial["limite_reds_consecutivos"]
        ):
            motivos_bloqueio.append("reds_consecutivos")
        if (
            risco_oficial["perda_realizada_hoje"]
            >= risco_oficial["limite_perda_diaria"]
        ):
            motivos_bloqueio.append("perda_diaria")
        risco_oficial["bloqueado"] = bool(motivos_bloqueio)
        risco_oficial["motivos_bloqueio"] = motivos_bloqueio
        resumo["risco_oficial"] = risco_oficial
        resumo["aprovados_novos"] = int(conexao.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT s.partida_id, s.mercado
                FROM sinais s
                WHERE s.status='aprovado'
                  AND ({filtro_regras_ativas})
                  AND json_extract(
                      s.features_json, '$.exploracao_sombra.versao'
                  ) IS NULL
                  AND date(s.criado_em)=date(?)
                GROUP BY s.partida_id, s.mercado
            )
            """.format(filtro_regras_ativas=filtro_regras_ativas),
            (*parametros_regras_ativas, dia),
        ).fetchone()[0] or 0)
        pendentes_por_mercado = {
            linha["mercado"]: int(linha["quantidade"] or 0)
            for linha in conexao.execute(
                """
                WITH independentes AS (
                    SELECT s.mercado, r.sinal_id AS resultado_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY s.partida_id, s.mercado,
                                            s.regra_versao
                               ORDER BY datetime(s.criado_em), s.id
                           ) AS ordem
                    FROM sinais s
                    LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
                    WHERE s.status IN ('aprovado', 'simulacao')
                      AND ({filtro_regras_ativas})
                      AND json_extract(
                          s.features_json, '$.exploracao_sombra.versao'
                      ) IS NULL
                )
                SELECT mercado, COUNT(*) AS quantidade
                FROM independentes
                WHERE ordem=1 AND resultado_id IS NULL
                GROUP BY mercado
                """.format(filtro_regras_ativas=filtro_regras_ativas),
                parametros_regras_ativas,
            ).fetchall()
        }
        resumo["pendentes_por_mercado"] = pendentes_por_mercado
        resumo["pendentes"] = sum(pendentes_por_mercado.values())
        linhas = conexao.execute(
            """
            SELECT mercado, resultado, retorno_unidades
            FROM sinais s
            JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status IN ('aprovado', 'simulacao')
              AND r.resultado IN (
                  'green','half_green','red','half_red'
              )
              AND date(r.encerrado_em)=date(?)
               AND EXISTS (
                   SELECT 1
                   FROM entregas_alertas e
                   WHERE e.sinal_id=s.id
                     AND e.status='entregue'
                     AND e.canal NOT LIKE '%:resultado'
                     {filtro_destinos}
               )
             ORDER BY mercado
            """.format(filtro_destinos=filtro_destinos),
            (dia, *parametros_destinos),
        ).fetchall()
        por_mercado = {}
        for linha in linhas:
            mercado = linha["mercado"]
            item = por_mercado.setdefault(
                mercado,
                {"total": 0, "greens": 0, "reds": 0,
                 "retorno_unidades": 0.0, "roi": None},
            )
            item["total"] += 1
            if linha["resultado"] in ("green", "half_green"):
                item["greens"] += 1
            else:
                item["reds"] += 1
            item["retorno_unidades"] += float(
                linha["retorno_unidades"] or 0
            )
        for item in por_mercado.values():
            item["retorno_unidades"] = round(
                item["retorno_unidades"], 4
            )
            item["roi"] = round(
                item["retorno_unidades"] / item["total"], 4
            ) if item["total"] else None
        resumo["resultados_por_mercado"] = por_mercado
        geral = resumo["resultados"]
        geral["total"] = sum(item["total"] for item in por_mercado.values())
        geral["greens"] = sum(
            item["greens"] for item in por_mercado.values()
        )
        geral["reds"] = sum(item["reds"] for item in por_mercado.values())
        geral["retorno_unidades"] = round(sum(
            item["retorno_unidades"] for item in por_mercado.values()
        ), 4)
        geral["roi"] = round(
            geral["retorno_unidades"] / geral["total"], 4
        ) if geral["total"] else None
        entregas = conexao.execute(
            """
            SELECT
                SUM(CASE WHEN e.canal NOT LIKE '%:teste%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.canal LIKE '%:teste' THEN 1 ELSE 0 END)
            FROM entregas_alertas e
             JOIN sinais s ON s.id=e.sinal_id
             WHERE e.status='entregue' AND date(e.entregue_em)=date(?)
               AND ({filtro_regras_ativas})
               {filtro_destinos}
               AND json_extract(
                   s.features_json, '$.exploracao_sombra.versao'
               ) IS NULL
            """.format(
                filtro_regras_ativas=filtro_regras_ativas,
                filtro_destinos=filtro_destinos,
            ),
            (dia, *parametros_regras_ativas, *parametros_destinos),
        ).fetchone()
        resumo["alertas_oficiais"] = int(entregas[0] or 0)
        resumo["simulacoes"] = int(entregas[1] or 0)
        resumo["saudavel"] = True
        return resumo
    except (OSError, sqlite3.Error, TypeError, ValueError) as erro:
        resumo["motivo"] = "resumo_diario_falhou"
        resumo["erro"] = type(erro).__name__
        return resumo
    finally:
        if "conexao" in locals():
            conexao.close()

def _estado_calibracao_resumo(estado):
    estado = estado or {}
    if estado.get("ativa"):
        return "liberado"
    motivo = estado.get("motivo") or "modelo_inativo"
    rotulos = {
        "amostra_insuficiente": "formando_amostra",
        "pontuacao_sem_discriminacao": "reprovado_sem_vantagem",
        "roi_validacao_insuficiente": "reprovado_roi",
        "auc_validacao_insuficiente": "reprovado_discriminacao",
    }
    return rotulos.get(motivo, str(motivo))

def descrever_filtro_ativo_resumo_diario(resumo):
    comparacao = resumo.get("comparacao") or {}
    enviadas = resumo.get("enviadas") or {}
    filtradas = resumo.get("filtradas") or {}

    def roi_texto(metricas):
        roi = metricas.get("roi")
        return "-" if roi is None else f"{float(roi) * 100:+.1f}%"

    estado = {
        "aguardando_amostra": "aguardando amostra",
        "nao_comprovado": "vantagem não comprovada",
        "evidencia_favoravel": "evidência favorável",
    }.get(
        comparacao.get("decisao"),
        comparacao.get("decisao") or "aguardando amostra",
    )
    mercado = resumo.get("mercado")
    return (
        f"• {ROTULOS_MERCADOS.get(mercado, mercado)}: "
        f"enviados {int(enviadas.get('greens', 0) or 0)}G/"
        f"{int(enviadas.get('reds', 0) or 0)}R "
        f"(ROI {roi_texto(enviadas)}) | filtrados "
        f"{int(filtradas.get('greens', 0) or 0)}G/"
        f"{int(filtradas.get('reds', 0) or 0)}R "
        f"(ROI {roi_texto(filtradas)}) | {estado} | mínimo "
        f"{int(comparacao.get('amostra_minima_por_coorte', 30) or 30)}/grupo"
    )

def comprimento_texto_telegram(texto):
    """Conta unidades UTF-16, margem conservadora usada pelo Telegram."""
    return len(str(texto).encode("utf-16-le")) // 2

def _fatiar_texto_por_unidades_telegram(texto, limite):
    fatias = []
    atual = []
    unidades = 0
    for caractere in str(texto):
        peso = 2 if ord(caractere) > 0xFFFF else 1
        if atual and unidades + peso > limite:
            fatias.append("".join(atual))
            atual = []
            unidades = 0
        atual.append(caractere)
        unidades += peso
    if atual:
        fatias.append("".join(atual))
    return fatias

def dividir_resumo_diario_telegram(
    mensagem, limite=LIMITE_PARTE_RESUMO_DIARIO,
):
    """Divide sem perder texto e deixa margem abaixo dos 4096 caracteres."""
    mensagem = str(mensagem)
    limite = max(int(limite), 256)
    if comprimento_texto_telegram(mensagem) <= limite:
        return [mensagem]

    # O cabecalho depende do total de partes. A reserva torna o resultado
    # estavel sem precisar refazer cortes quando o total ganha outro digito.
    limite_conteudo = limite - 80
    partes_brutas = []
    atual = ""
    for linha in mensagem.splitlines(keepends=True):
        if comprimento_texto_telegram(linha) > limite_conteudo:
            if atual:
                partes_brutas.append(atual)
                atual = ""
            partes_brutas.extend(
                trecho
                for trecho in _fatiar_texto_por_unidades_telegram(
                    linha, limite_conteudo
                )
                if trecho
            )
            continue
        candidato = atual + linha
        if (
            atual
            and comprimento_texto_telegram(candidato) > limite_conteudo
        ):
            partes_brutas.append(atual)
            atual = linha
        else:
            atual = candidato
    if atual:
        partes_brutas.append(atual)

    total = len(partes_brutas)
    partes = [
        f"[Resumo diario - parte {indice}/{total}]\n\n{conteudo}"
        for indice, conteudo in enumerate(partes_brutas, start=1)
    ]
    if not partes or any(
        comprimento_texto_telegram(parte) > limite for parte in partes
    ):
        raise ValueError("divisao_resumo_diario_excedeu_limite")
    return partes

def _criar_manifesto_resumo_diario(dia, mensagem):
    partes = dividir_resumo_diario_telegram(mensagem)
    registros = []
    for numero, texto in enumerate(partes, start=1):
        registros.append({
            "numero": numero,
            "chave": (
                f"{VERSAO_ENTREGA_RESUMO_DIARIO}|{dia}|"
                f"parte-{numero:03d}"
            ),
            "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
            "texto": texto,
            "entregue": False,
        })
    return {
        "versao": VERSAO_ENTREGA_RESUMO_DIARIO,
        "dia": str(dia),
        "partes_total": len(registros),
        "partes": registros,
        "concluida": False,
    }

def _manifesto_resumo_diario_valido(manifesto, dia):
    try:
        if not isinstance(manifesto, dict):
            return False
        if (
            manifesto.get("versao") != VERSAO_ENTREGA_RESUMO_DIARIO
            or manifesto.get("dia") != str(dia)
        ):
            return False
        partes = manifesto.get("partes")
        if not isinstance(partes, list) or not partes:
            return False
        partes_total = manifesto.get("partes_total")
        if (
            isinstance(partes_total, bool)
            or not isinstance(partes_total, int)
            or partes_total != len(partes)
        ):
            return False
        for numero, parte in enumerate(partes, start=1):
            if not isinstance(parte, dict):
                return False
            texto = parte.get("texto")
            chave = (
                f"{VERSAO_ENTREGA_RESUMO_DIARIO}|{dia}|"
                f"parte-{numero:03d}"
            )
            if (
                parte.get("numero") != numero
                or parte.get("chave") != chave
                or not isinstance(texto, str)
                or comprimento_texto_telegram(texto)
                > LIMITE_PARTE_RESUMO_DIARIO
                or parte.get("sha256")
                != hashlib.sha256(texto.encode("utf-8")).hexdigest()
            ):
                return False
        return True
    except (TypeError, ValueError, UnicodeError):
        return False

def _copiar_manifesto_resumo_diario(manifesto):
    return {
        **manifesto,
        "partes": [dict(parte) for parte in manifesto.get("partes") or []],
    }
