from collections import Counter
from datetime import datetime


def resumir_pendencias_resultados(conexao, agora=None):
    agora = (agora or datetime.now()).replace(microsecond=0)
    linhas = conexao.execute(
        """
        SELECT s.id AS sinal_id, s.partida_id, s.mercado, s.criado_em,
               p.api_fixture_id,
               COUNT(c.id) AS tentativas,
               GROUP_CONCAT(DISTINCT c.fonte) AS fontes_tentadas
        FROM sinais s
        JOIN partidas p ON p.id=s.partida_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        LEFT JOIN consultas_finalizacao c ON c.partida_id=s.partida_id
        WHERE s.status IN ('aprovado', 'simulacao')
          AND r.sinal_id IS NULL
        GROUP BY s.id, s.partida_id, s.mercado, s.criado_em,
                 p.api_fixture_id
        ORDER BY s.criado_em, s.id
        """
    ).fetchall()
    partidas = {item["partida_id"] for item in linhas}
    partidas_api = {
        item["partida_id"] for item in linhas
        if item["api_fixture_id"] is not None
    }
    partidas_com_tentativa = {
        item["partida_id"] for item in linhas if int(item["tentativas"] or 0)
    }
    idades = []
    acima_180 = 0
    for item in linhas:
        try:
            idade = max(
                0.0,
                (agora - datetime.fromisoformat(item["criado_em"]))
                .total_seconds() / 60,
            )
        except (TypeError, ValueError):
            continue
        idades.append(idade)
        acima_180 += idade >= 180
    return {
        "sinais": len(linhas),
        "partidas": len(partidas),
        "partidas_com_api": len(partidas_api),
        "partidas_somente_packball": len(partidas - partidas_api),
        "partidas_com_tentativa": len(partidas_com_tentativa),
        "partidas_sem_tentativa": len(partidas - partidas_com_tentativa),
        "sinais_acima_180_minutos": acima_180,
        "idade_mais_antiga_minutos": (
            round(max(idades), 1) if idades else None
        ),
        "por_mercado": dict(sorted(Counter(
            item["mercado"] for item in linhas
        ).items())),
    }
