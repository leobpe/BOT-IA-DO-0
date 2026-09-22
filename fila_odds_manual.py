import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from banco import BancoMonitor


PASTA = Path(__file__).parent
MERCADOS_PERIODOS = {
    "escanteios_ft_asiatico": "FT",
    "escanteios_1t": "1T",
    "escanteios_2t": "2T",
}
BLOQUEIO_RESOLVIVEL = {"odd_ao_vivo_indisponivel"}


def _bloqueios(motivos_json):
    try:
        motivos = json.loads(motivos_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(motivos, list):
        return None
    return {
        item.removeprefix("bloqueio:")
        for item in motivos
        if isinstance(item, str) and item.startswith("bloqueio:")
    }


def listar_solicitacoes_odds_manuais(
    conexao,
    *,
    agora=None,
    janela_minutos=6,
    pontuacao_minima=75.0,
):
    agora = (agora or datetime.now()).replace(microsecond=0)
    limite = (agora - timedelta(minutes=janela_minutos)).isoformat()
    linhas = conexao.execute(
        """
        WITH recentes AS (
            SELECT
                s.id AS sinal_id,
                s.partida_id,
                s.snapshot_id,
                s.criado_em,
                s.mercado,
                s.pontuacao_tecnica,
                s.motivos_json,
                s.status,
                p.mandante,
                p.visitante,
                p.packball_url,
                sn.placar,
                sn.status AS status_partida,
                ROW_NUMBER() OVER (
                    PARTITION BY s.partida_id, s.mercado
                    ORDER BY datetime(s.criado_em) DESC, s.id DESC
                ) AS ordem
            FROM sinais s
            JOIN partidas p ON p.id=s.partida_id
            JOIN snapshots sn ON sn.id=s.snapshot_id
            WHERE s.mercado IN (
                'escanteios_ft_asiatico',
                'escanteios_1t',
                'escanteios_2t'
            )
              AND datetime(s.criado_em) >= datetime(?)
        )
        SELECT *
        FROM recentes atual
        WHERE ordem=1
          AND status='rejeitado'
          AND pontuacao_tecnica>=?
          AND NOT EXISTS (
              SELECT 1
              FROM observacoes_fontes_odds observacao
              WHERE observacao.partida_id=atual.partida_id
                AND observacao.fonte='bet365_site'
                AND observacao.estado='oferta_valida'
                AND observacao.periodo=CASE
                    WHEN atual.mercado='escanteios_ft_asiatico' THEN 'FT'
                    WHEN atual.mercado='escanteios_1t' THEN '1T'
                    ELSE '2T'
                END
                AND datetime(observacao.consultado_em)
                    >= datetime(atual.criado_em)
          )
        ORDER BY pontuacao_tecnica DESC, criado_em
        """,
        (limite, float(pontuacao_minima)),
    ).fetchall()
    solicitacoes = []
    for linha in linhas:
        bloqueios = _bloqueios(linha["motivos_json"])
        if bloqueios != BLOQUEIO_RESOLVIVEL:
            continue
        criado_em = datetime.fromisoformat(linha["criado_em"])
        idade_segundos = max((agora - criado_em).total_seconds(), 0.0)
        mercado = linha["mercado"]
        solicitacoes.append({
            "chave": f"{linha['partida_id']}:{mercado}",
            "sinal_id": int(linha["sinal_id"]),
            "partida_id": int(linha["partida_id"]),
            "partida": f"{linha['mandante']} x {linha['visitante']}",
            "mandante": linha["mandante"],
            "visitante": linha["visitante"],
            "packball_url": linha["packball_url"],
            "mercado": mercado,
            "periodo": MERCADOS_PERIODOS[mercado],
            "pontuacao_tecnica": float(linha["pontuacao_tecnica"]),
            "placar": linha["placar"],
            "status_partida": linha["status_partida"],
            "criado_em": linha["criado_em"],
            "idade_segundos": round(idade_segundos, 1),
            "expira_em": (
                criado_em + timedelta(minutes=janela_minutos)
            ).isoformat(),
            "estado": "aguardando_captura_manual",
            "instrucao": (
                "Abrir o evento ao vivo na Bet365, entrar em Escanteios "
                "e capturar a linha asiática com as odds Over e Under."
            ),
        })
    return {
        "gerado_em": agora.isoformat(),
        "janela_minutos": int(janela_minutos),
        "pontuacao_minima": float(pontuacao_minima),
        "envio_automatico": False,
        "total": len(solicitacoes),
        "solicitacoes": solicitacoes,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Lista partidas que passaram nos critérios de escanteios e "
            "dependem somente de uma odd manual da Bet365."
        )
    )
    parser.add_argument(
        "--banco", default=str(PASTA / "monitor_packball.db")
    )
    parser.add_argument("--janela-minutos", type=int, default=6)
    parser.add_argument("--pontuacao-minima", type=float, default=75.0)
    argumentos = parser.parse_args()
    if argumentos.janela_minutos < 1 or argumentos.janela_minutos > 30:
        parser.error("--janela-minutos deve ficar entre 1 e 30.")
    if not 0 <= argumentos.pontuacao_minima <= 100:
        parser.error("--pontuacao-minima deve ficar entre 0 e 100.")
    banco = BancoMonitor(argumentos.banco)
    try:
        resultado = listar_solicitacoes_odds_manuais(
            banco.conexao,
            janela_minutos=argumentos.janela_minutos,
            pontuacao_minima=argumentos.pontuacao_minima,
        )
    finally:
        banco.fechar()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
