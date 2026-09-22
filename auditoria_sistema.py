import hashlib
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from banco import BancoMonitor
from backup_banco import BackupBanco, verificar_arquivo_backup
from calibracao import (
    POLITICA_CALIBRACAO_VERSAO,
    hash_modelo_calibracao,
    modelo_compativel_com_politica,
    serializar_modelo_calibracao,
)
from configuracao import obter_limites_risco
from integridade_resultados import auditar_proveniencia_resultados
from integridade_calibracao import auditar_frescor_calibracoes
from motor_sinais import VERSAO_REGRAS
from watchdog import auditar_integridade_telegram, verificar_coleta


PASTA = Path(__file__).parent


def gerar_auditoria(
    banco, agora=None, caminho_log=None, caminho_backup=None
):
    agora = agora or datetime.now()
    totais = banco.contagens()
    snapshots = banco.conexao.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN confirmacao_api_json NOT IN ('null', '{}', '')
                        THEN 1 ELSE 0 END) AS com_api,
               AVG(qualidade_dados) AS qualidade_media,
               SUM(CASE WHEN estatisticas_json='{}' THEN 1 ELSE 0 END)
                   AS sem_estatisticas,
               SUM(CASE WHEN estatisticas_json='{}' AND (
                        LOWER(COALESCE(status, '')) LIKE '%finalizado%'
                        OR LOWER(COALESCE(status, '')) LIKE '%encerrado%'
                        OR LOWER(COALESCE(status, '')) LIKE '%finished%'
                        OR LOWER(COALESCE(status, '')) LIKE '%full time%'
                        OR LOWER(TRIM(COALESCE(status, '')))='ft'
                   ) THEN 1 ELSE 0 END) AS sem_estatisticas_finalizacao,
               SUM(CASE WHEN estatisticas_json='{}' AND NOT (
                        LOWER(COALESCE(status, '')) LIKE '%finalizado%'
                        OR LOWER(COALESCE(status, '')) LIKE '%encerrado%'
                        OR LOWER(COALESCE(status, '')) LIKE '%finished%'
                        OR LOWER(COALESCE(status, '')) LIKE '%full time%'
                        OR LOWER(TRIM(COALESCE(status, '')))='ft'
                   ) THEN 1 ELSE 0 END) AS sem_estatisticas_ao_vivo
        FROM snapshots
        """
    ).fetchone()
    limite_24h = (agora - timedelta(hours=24)).replace(
        microsecond=0
    ).isoformat()
    limite_180m = (agora - timedelta(minutes=180)).isoformat()
    limite_360m = (agora - timedelta(minutes=360)).isoformat()
    limite_observacao = (agora - timedelta(minutes=30)).isoformat()
    recentes = banco.conexao.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN confirmacao_api_json NOT IN ('null', '{}', '')
                        THEN 1 ELSE 0 END) AS com_api,
               AVG(qualidade_dados) AS qualidade_media,
               SUM(CASE WHEN estatisticas_json='{}' THEN 1 ELSE 0 END)
                   AS sem_estatisticas,
               SUM(CASE WHEN estatisticas_json='{}' AND (
                        LOWER(COALESCE(status, '')) LIKE '%finalizado%'
                        OR LOWER(COALESCE(status, '')) LIKE '%encerrado%'
                        OR LOWER(COALESCE(status, '')) LIKE '%finished%'
                        OR LOWER(COALESCE(status, '')) LIKE '%full time%'
                        OR LOWER(TRIM(COALESCE(status, '')))='ft'
                   ) THEN 1 ELSE 0 END) AS sem_estatisticas_finalizacao,
               SUM(CASE WHEN estatisticas_json='{}' AND NOT (
                        LOWER(COALESCE(status, '')) LIKE '%finalizado%'
                        OR LOWER(COALESCE(status, '')) LIKE '%encerrado%'
                        OR LOWER(COALESCE(status, '')) LIKE '%finished%'
                        OR LOWER(COALESCE(status, '')) LIKE '%full time%'
                        OR LOWER(TRIM(COALESCE(status, '')))='ft'
                   ) THEN 1 ELSE 0 END) AS sem_estatisticas_ao_vivo
        FROM snapshots WHERE coletado_em >= ?
        """,
        (limite_24h,),
    ).fetchone()
    pendencias = banco.conexao.execute(
        """
        SELECT s.mercado, COUNT(*) AS sinais,
               COUNT(DISTINCT s.partida_id) AS partidas,
               MIN(s.criado_em) AS mais_antigo
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.status='aprovado' AND r.sinal_id IS NULL
        GROUP BY s.mercado ORDER BY s.mercado
        """
    ).fetchall()
    repeticoes_abertas = banco.conexao.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT s.partida_id, s.mercado, s.regra_versao,
                   COUNT(*) AS quantidade
            FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='aprovado' AND r.sinal_id IS NULL
            GROUP BY s.partida_id, s.mercado, s.regra_versao
            HAVING quantidade > 1
        )
        """
    ).fetchone()[0]
    vencidas = banco.conexao.execute(
        """
        SELECT COUNT(*)
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.status='aprovado' AND r.sinal_id IS NULL
          AND datetime(s.criado_em) <= datetime(?)
          AND (
              datetime(s.criado_em) <= datetime(?)
              OR COALESCE(
                  (
                      SELECT MAX(sn.coletado_em)
                      FROM snapshots sn
                      WHERE sn.partida_id=s.partida_id
                  ),
                  s.criado_em
              ) <= ?
          )
        """,
        (limite_180m, limite_360m, limite_observacao),
    ).fetchone()[0]
    duplicados = banco.conexao.execute(
        "SELECT COUNT(*) FROM sinais WHERE status='duplicado'"
    ).fetchone()[0]
    historico_entregas_por_status = {
        item["status"]: item["quantidade"]
        for item in banco.conexao.execute(
            """
            SELECT status, COUNT(*) AS quantidade
            FROM entregas_alertas
            WHERE canal NOT LIKE 'gateway:%'
            GROUP BY status ORDER BY status
            """
        ).fetchall()
    }
    entregas_por_status = {
        item["status"]: item["quantidade"]
        for item in banco.conexao.execute(
            """
            SELECT atual.status, COUNT(*) AS quantidade
            FROM entregas_alertas atual
            WHERE atual.canal NOT LIKE 'gateway:%'
              AND atual.id=(
                SELECT MAX(posterior.id)
                FROM entregas_alertas posterior
                WHERE posterior.sinal_id=atual.sinal_id
                  AND posterior.canal=atual.canal
            )
            GROUP BY atual.status ORDER BY atual.status
            """
        ).fetchall()
    }
    entregas_transitorias_superadas = banco.conexao.execute(
        """
        SELECT COUNT(*)
        FROM entregas_alertas pendente
        WHERE pendente.canal NOT LIKE 'gateway:%'
          AND pendente.status IN ('enviando', 'tentando', 'incerto')
          AND EXISTS (
              SELECT 1 FROM entregas_alertas final
              WHERE final.sinal_id=pendente.sinal_id
                AND final.canal=pendente.canal
                AND final.status IN (
                    'entregue', 'erro', 'recuperado',
                    'cancelado', 'expirado'
                )
                AND datetime(final.tentado_em)
                    >= datetime(pendente.tentado_em)
          )
        """
    ).fetchone()[0]
    integridade_telegram = auditar_integridade_telegram(
        banco.conexao, agora
    )
    historico_gateway_por_status = {
        item["status"]: item["quantidade"]
        for item in banco.conexao.execute(
            """
            SELECT status, COUNT(*) AS quantidade
            FROM entregas_alertas
            WHERE canal LIKE 'gateway:%'
            GROUP BY status ORDER BY status
            """
        ).fetchall()
    }
    decisoes_gateway_por_status = {
        item["status"]: item["quantidade"]
        for item in banco.conexao.execute(
            """
            SELECT atual.status, COUNT(*) AS quantidade
            FROM entregas_alertas atual
            WHERE atual.canal LIKE 'gateway:%'
              AND atual.id=(
                SELECT MAX(posterior.id)
                FROM entregas_alertas posterior
                WHERE posterior.sinal_id=atual.sinal_id
                  AND posterior.canal=atual.canal
            )
            GROUP BY atual.status ORDER BY atual.status
            """
        ).fetchall()
    }
    resultados_por_estado = {
        item["resultado"]: item["quantidade"]
        for item in banco.conexao.execute(
            """
            SELECT resultado, COUNT(*) AS quantidade
            FROM resultados_sinais
            GROUP BY resultado ORDER BY resultado
            """
        ).fetchall()
    }
    finalizacoes_24h = {
        f"{item['fonte']}:{item['estado']}": item["quantidade"]
        for item in banco.conexao.execute(
            """
            SELECT fonte, estado, COUNT(*) AS quantidade
            FROM consultas_finalizacao
            WHERE consultado_em >= ?
            GROUP BY fonte, estado ORDER BY fonte, estado
            """,
            (limite_24h,),
        ).fetchall()
    }
    limites_risco = obter_limites_risco()
    drift_calibracoes = {}
    elegibilidade_calibracoes = {}
    calibracoes_ativas_incompativeis = 0
    calibracoes_atuais_sem_historico = 0
    calibracoes_estado_incoerente = 0
    for item in banco.conexao.execute(
        """
        SELECT mercado, regra_versao, amostra, ativa, modelo_json
        FROM calibracoes ORDER BY mercado
        """
    ).fetchall():
        try:
            modelo = json.loads(item["modelo_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            modelo = {}
        modelo_json = serializar_modelo_calibracao(modelo)
        modelo_hash = hash_modelo_calibracao(modelo)
        historico_vinculado = banco.conexao.execute(
            """
            SELECT 1 FROM historico_calibracoes
            WHERE mercado=? AND regra_versao=? AND amostra=? AND ativa=?
              AND modelo_hash=? AND modelo_json=?
            LIMIT 1
            """,
            (
                item["mercado"], item["regra_versao"], item["amostra"],
                item["ativa"], modelo_hash, modelo_json,
            ),
        ).fetchone() is not None
        try:
            amostra_coerente = (
                int(item["amostra"] or 0)
                == int(modelo.get("amostra") or 0)
            )
        except (TypeError, ValueError):
            amostra_coerente = False
        estado_coerente = bool(
            bool(item["ativa"]) == (modelo.get("ativa") is True)
            and amostra_coerente
        )
        calibracoes_atuais_sem_historico += int(not historico_vinculado)
        calibracoes_estado_incoerente += int(not estado_coerente)
        drift_calibracoes[item["mercado"]] = modelo.get("drift") or {
            "detectado": False,
            "motivo": "aguardando_recalibracao",
        }
        compativel = modelo_compativel_com_politica(
            modelo, limites_risco
        )
        elegibilidade_calibracoes[item["mercado"]] = {
            "ativa": bool(item["ativa"]),
            "compativel": compativel,
            "populacao": modelo.get("populacao") or "legada",
            "historico_vinculado": historico_vinculado,
            "estado_coerente": estado_coerente,
        }
        if item["ativa"] and not compativel:
            calibracoes_ativas_incompativeis += 1
    integridade = banco.conexao.execute("PRAGMA foreign_key_check").fetchall()
    proveniencia_resultados = auditar_proveniencia_resultados(
        banco.conexao
    )
    frescor_calibracoes = auditar_frescor_calibracoes(
        banco.conexao,
        VERSAO_REGRAS,
        limites_risco,
        politica_versao=POLITICA_CALIBRACAO_VERSAO,
        somente_executaveis=True,
    )
    historico_calibracoes = {
        "total": 0,
        "hashes_invalidos": 0,
        "primeiro_registro_em": None,
        "ultimo_registro_em": None,
        "saudavel": True,
    }
    linhas_historico = banco.conexao.execute(
        """
        SELECT registrado_em, modelo_hash, modelo_json
        FROM historico_calibracoes ORDER BY id
        """
    ).fetchall()
    historico_calibracoes["total"] = len(linhas_historico)
    if linhas_historico:
        historico_calibracoes["primeiro_registro_em"] = (
            linhas_historico[0]["registrado_em"]
        )
        historico_calibracoes["ultimo_registro_em"] = (
            linhas_historico[-1]["registrado_em"]
        )
    for linha_historico in linhas_historico:
        calculado = hashlib.sha256(
            linha_historico["modelo_json"].encode("utf-8")
        ).hexdigest()
        if calculado != linha_historico["modelo_hash"]:
            historico_calibracoes["hashes_invalidos"] += 1
    historico_calibracoes["saudavel"] = (
        historico_calibracoes["hashes_invalidos"] == 0
    )
    linhas_totais = banco.conexao.execute(
        """
        SELECT linha FROM sinais
        WHERE status='aprovado'
          AND mercado IN (
            'gol_ft', 'gol_ht', 'proximo_escanteio',
            'escanteios_ft_asiatico',
            'escanteios_1t', 'escanteios_2t'
          )
          AND linha IS NOT NULL
        """
    ).fetchall()
    linhas_asiaticas = {
        "inteiras": 0,
        "meias": 0,
        "quartos": 0,
        "outras": 0,
    }
    for item in linhas_totais:
        try:
            fracao = round(float(item["linha"]) % 1, 2)
        except (TypeError, ValueError):
            linhas_asiaticas["outras"] += 1
            continue
        if fracao == 0:
            linhas_asiaticas["inteiras"] += 1
        elif fracao == 0.5:
            linhas_asiaticas["meias"] += 1
        elif fracao in (0.25, 0.75):
            linhas_asiaticas["quartos"] += 1
        else:
            linhas_asiaticas["outras"] += 1
    total_snapshots = int(snapshots["total"] or 0)
    lista_pendencias = []
    for item in pendencias:
        antigo = datetime.fromisoformat(item["mais_antigo"])
        idade = round(max((agora - antigo).total_seconds(), 0) / 60, 1)
        lista_pendencias.append(
            {
                "mercado": item["mercado"],
                "sinais": item["sinais"],
                "partidas": item["partidas"],
                "idade_maxima_minutos": idade,
            }
        )
    total_recentes = int(recentes["total"] or 0)
    saude_coleta = (
        verificar_coleta(caminho_log, agora)
        if caminho_log is not None else None
    )
    disco = shutil.disk_usage(banco.caminho.parent)
    disco_livre_mb = round(disco.free / (1024 * 1024), 1)
    backup = (
        verificar_arquivo_backup(caminho_backup)
        if caminho_backup is not None else None
    )
    return {
        "gerado_em": agora.replace(microsecond=0).isoformat(),
        "totais": totais,
        "cobertura_api_percentual": round(
            100 * int(snapshots["com_api"] or 0) / total_snapshots, 2
        ) if total_snapshots else None,
        "qualidade_media": round(float(snapshots["qualidade_media"]), 2)
        if snapshots["qualidade_media"] is not None else None,
        "snapshots_sem_estatisticas": int(snapshots["sem_estatisticas"] or 0),
        "snapshots_sem_estatisticas_finalizacao": int(
            snapshots["sem_estatisticas_finalizacao"] or 0
        ),
        "snapshots_ao_vivo_sem_estatisticas": int(
            snapshots["sem_estatisticas_ao_vivo"] or 0
        ),
        "ultimas_24h": {
            "snapshots": total_recentes,
            "cobertura_api_percentual": round(
                100 * int(recentes["com_api"] or 0) / total_recentes, 2
            ) if total_recentes else None,
            "qualidade_media": round(float(recentes["qualidade_media"]), 2)
            if recentes["qualidade_media"] is not None else None,
            "sem_estatisticas": int(recentes["sem_estatisticas"] or 0),
            "sem_estatisticas_finalizacao": int(
                recentes["sem_estatisticas_finalizacao"] or 0
            ),
            "ao_vivo_sem_estatisticas": int(
                recentes["sem_estatisticas_ao_vivo"] or 0
            ),
        },
        "pendencias": lista_pendencias,
        "pendencias_acima_180_minutos": vencidas,
        "sinais_duplicados_isolados": duplicados,
        "fila_telegram": entregas_por_status,
        "historico_entregas_telegram": historico_entregas_por_status,
        "entregas_transitorias_superadas": int(
            entregas_transitorias_superadas or 0
        ),
        "integridade_telegram": integridade_telegram,
        "decisoes_gateway": decisoes_gateway_por_status,
        "historico_decisoes_gateway": historico_gateway_por_status,
        "resultados_por_estado": resultados_por_estado,
        "finalizacoes_ultimas_24h": finalizacoes_24h,
        "drift_calibracoes": drift_calibracoes,
        "elegibilidade_calibracoes": elegibilidade_calibracoes,
        "calibracoes_ativas_incompativeis": (
            calibracoes_ativas_incompativeis
        ),
        "calibracoes_atuais_sem_historico": (
            calibracoes_atuais_sem_historico
        ),
        "calibracoes_estado_incoerente": calibracoes_estado_incoerente,
        "linhas_asiaticas_aprovadas": linhas_asiaticas,
        "grupos_aprovados_repetidos": repeticoes_abertas,
        "violacoes_integridade": len(integridade),
        "proveniencia_resultados": proveniencia_resultados,
        "frescor_calibracoes": frescor_calibracoes,
        "historico_calibracoes": historico_calibracoes,
        "saude_coleta": saude_coleta,
        "disco": {
            "livre_mb": disco_livre_mb,
            "alerta_abaixo_mb": 512,
            "saudavel": disco_livre_mb >= 512,
        },
        "backup": backup,
        "saudavel": (
            not integridade
            and proveniencia_resultados["saudavel"]
            and integridade_telegram["saudavel"]
            and frescor_calibracoes["saudavel"]
            and historico_calibracoes["saudavel"]
            and calibracoes_ativas_incompativeis == 0
            and calibracoes_atuais_sem_historico == 0
            and calibracoes_estado_incoerente == 0
            and repeticoes_abertas == 0
            and vencidas == 0
            and disco_livre_mb >= 512
            and (backup is None or backup["valido"])
            and (saude_coleta is None or saude_coleta["saudavel"])
        ),
    }


def main():
    banco = BancoMonitor(PASTA / "monitor_packball.db")
    try:
        backups = sorted(BackupBanco._glob_formatos(
            PASTA / "backups", "monitor_*.db"
        ))
        resultado = gerar_auditoria(
            banco,
            caminho_log=PASTA / "monitor_eventos.jsonl",
            caminho_backup=backups[-1] if backups else None,
        )
        print("AUDITORIA PROFISSIONAL DO BOT PACKBALL\n")
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    finally:
        banco.fechar()


if __name__ == "__main__":
    main()
