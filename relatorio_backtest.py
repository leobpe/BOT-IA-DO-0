import argparse
import sys
from pathlib import Path

from backtest import (
    AvaliadorBacktest,
    calcular_metricas,
    metricas_segmentadas,
    resumir_funil_sinais,
)
from banco import BancoMonitor
from mercados import MERCADOS_CALIBRADOS
from motor_sinais import VERSAO_REGRAS
from integridade_calibracao import carregar_amostra_independente
from progresso_calibracao import resumir_progresso_calibracao


PASTA = Path(__file__).parent
MERCADOS = MERCADOS_CALIBRADOS


def configurar_saida_terminal():
    reconfigurar = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigurar):
        try:
            reconfigurar(errors="replace")
        except (OSError, ValueError):
            pass


def validar_contadores_progresso(
    resultados_brutos,
    amostra_vinculada,
    andamento,
):
    amostra_progresso = int(andamento.get("amostra", 0) or 0)
    if int(amostra_vinculada) != amostra_progresso:
        raise RuntimeError(
            "Amostra do relatorio diverge da amostra usada na calibracao."
        )
    return {
        "resultados_brutos": int(resultados_brutos),
        "amostra_calibracao": amostra_progresso,
        "faltam_calibracao": int(andamento.get("faltam", 0) or 0),
    }


def separar_metricas_populacoes(metricas_brutas, amostra_calibracao):
    return {
        "resultados_brutos": dict(metricas_brutas),
        "amostra_calibracao": calcular_metricas(amostra_calibracao),
    }


def formatar_metricas(metricas):
    acerto = (
        f"{metricas['taxa_acerto'] * 100:.1f}%"
        if metricas["taxa_acerto"] is not None else "aguardando"
    )
    roi = (
        f"{metricas['roi'] * 100:.1f}%"
        if metricas["roi"] is not None else "aguardando"
    )
    intervalo = metricas["intervalo_acerto_95"]
    ic = (
        f"{intervalo[0] * 100:.1f}%-{intervalo[1] * 100:.1f}%"
        if intervalo else "aguardando"
    )
    auc = metricas["discriminacao_pontuacao"]["auc"]
    auc_texto = f"{auc:.3f}" if auc is not None else "aguardando"
    return (
        f"n={metricas['amostra']} | acerto={acerto} | ROI={roi} | "
        f"IC95={ic} | AUC nota={auc_texto} | "
        f"estado={metricas['estado_amostra']}"
    )


def main(regra_versao=VERSAO_REGRAS):
    configurar_saida_terminal()
    banco = BancoMonitor(PASTA / "monitor_packball.db")
    try:
        avaliador = AvaliadorBacktest(banco)
        limites = avaliador.limites_risco
        segmentos = metricas_segmentadas(banco, regra_versao)
        funil = resumir_funil_sinais(
            banco.conexao,
            regra_versao,
            limites.odd_minima,
            limites.odd_maxima,
        )
        progresso = resumir_progresso_calibracao(
            banco.conexao, regra_versao=regra_versao
        )
        print("RELATÓRIO DE VALIDAÇÃO — SEM GARANTIA DE LUCRO")
        print(f"Versão da regra: {regra_versao}")
        print(
            "População elegível para alertas: "
            f"odds {limites.odd_minima:.2f} a {limites.odd_maxima:.2f}\n"
        )
        for mercado in MERCADOS:
            metricas_brutas = avaliador.metricas(
                mercado=mercado, regra_versao=regra_versao
            )
            amostra_vinculada = carregar_amostra_independente(
                banco.conexao,
                mercado,
                regra_versao,
                limites,
            )
            metricas_populacoes = separar_metricas_populacoes(
                metricas_brutas, amostra_vinculada
            )
            metricas_calibracao = metricas_populacoes[
                "amostra_calibracao"
            ]
            pendentes = banco.conexao.execute(
                """
                SELECT COUNT(*)
                FROM sinais s
                LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
                WHERE s.mercado=? AND s.regra_versao=?
                  AND s.status='aprovado' AND r.sinal_id IS NULL
                  AND s.odd BETWEEN ? AND ?
                """,
                (
                    mercado,
                    regra_versao,
                    limites.odd_minima,
                    limites.odd_maxima,
                ),
            ).fetchone()[0]
            partidas_resolvidas = banco.conexao.execute(
                """
                SELECT COUNT(DISTINCT s.partida_id)
                FROM sinais s
                JOIN resultados_sinais r ON r.sinal_id=s.id
                WHERE s.mercado=? AND s.regra_versao=?
                  AND s.status='aprovado'
                  AND s.odd BETWEEN ? AND ?
                  AND r.resultado IN (
                      'green', 'half_green', 'red', 'half_red'
                  )
                """,
                (
                    mercado,
                    regra_versao,
                    limites.odd_minima,
                    limites.odd_maxima,
                ),
            ).fetchone()[0]
            andamento = progresso[mercado]
            contadores = validar_contadores_progresso(
                metricas_brutas["amostra"],
                metricas_calibracao["amostra"],
                andamento,
            )
            print(
                f"{mercado}: resultados_brutos="
                f"{contadores['resultados_brutos']} | "
                "amostra_calibracao="
                f"{contadores['amostra_calibracao']} | "
                f"partidas_independentes={partidas_resolvidas} | "
                f"pendentes={pendentes} | faltam_calibracao="
                f"{contadores['faltam_calibracao']} | "
                f"voids={metricas_brutas['observacoes_void']} | "
                f"sem_dado={metricas_brutas['observacoes_sem_dado']}"
            )
            print(
                "  histórico bruto (inclui legado): "
                f"{formatar_metricas(metricas_brutas)}"
            )
            print(
                "  amostra oficial vinculada: "
                f"{formatar_metricas(metricas_calibracao)}"
            )
            prazo = (
                f"{andamento['dias_estimados']} dias, "
                f"estimado em {andamento['data_estimada']}"
                if andamento["dias_estimados"] is not None
                else "sem previsão"
            )
            print(
                "  progresso: ritmo="
                f"{andamento['ritmo_dia']}/dia em "
                f"{andamento['dias_observados']} dia(s) | "
                f"prazo={prazo} | "
                "confiabilidade="
                f"{andamento['confiabilidade_estimativa']}"
            )

        print("\nFunil de decisões da versão:")
        for mercado in MERCADOS:
            resumo = funil.get(mercado) or {
                "gerados": 0,
                "aprovados": 0,
                "rejeitados": 0,
                "duplicados": 0,
                "nota_minima": 0,
                "odd_estruturada": 0,
                "odd_elegivel": 0,
                "bloqueios": {},
            }
            bloqueios = ", ".join(
                f"{motivo}={quantidade}"
                for motivo, quantidade in list(
                    resumo["bloqueios"].items()
                )[:5]
            ) or "nenhum"
            print(
                f"{mercado}: gerados={resumo['gerados']} | "
                f"aprovados={resumo['aprovados']} | "
                f"rejeitados={resumo['rejeitados']} | "
                f"duplicados={resumo['duplicados']} | "
                f"nota>=70={resumo['nota_minima']} | "
                f"odd estruturada={resumo['odd_estruturada']} | "
                f"odd elegível={resumo['odd_elegivel']} | "
                f"principais bloqueios: {bloqueios}"
            )

        print("\nÚltimos resultados:")
        linhas = banco.conexao.execute(
            """
            SELECT p.mandante, p.visitante, s.mercado, s.linha, s.odd,
                   s.pontuacao_tecnica, r.resultado, r.retorno_unidades,
                   inicial.status, inicial.placar, r.encerrado_em
            FROM resultados_sinais r
            JOIN sinais s ON s.id=r.sinal_id
            JOIN partidas p ON p.id=s.partida_id
            JOIN snapshots inicial ON inicial.id=s.snapshot_id
            WHERE s.status='aprovado' AND s.odd BETWEEN ? AND ?
              AND s.regra_versao=?
            ORDER BY r.encerrado_em DESC, r.sinal_id DESC
            LIMIT 20
            """,
            (limites.odd_minima, limites.odd_maxima, regra_versao),
        ).fetchall()
        if not linhas:
            print("nenhum resultado resolvido")
        for item in linhas:
            retorno = (
                f"{item['retorno_unidades']:+g}u"
                if item["retorno_unidades"] is not None
                else "não avaliável"
            )
            print(
                f"{item['encerrado_em']} | {item['mandante']} x "
                f"{item['visitante']} | {item['mercado']} | "
                f"linha={item['linha']} odd={item['odd']} | "
                f"nota={item['pontuacao_tecnica']} | "
                f"{item['resultado']} ({retorno})"
            )

        if segmentos["liga"]:
            print("\nAmostra resolvida por liga:")
            for liga, metricas in segmentos["liga"].items():
                print(f"{liga}: {metricas['amostra']}")

        print("\nPartidas com sinais aprovados pendentes:")
        pendencias = banco.conexao.execute(
            """
            SELECT p.id, p.mandante, p.visitante, p.packball_url,
                   p.api_fixture_id, MIN(s.criado_em) AS primeiro_sinal,
                   GROUP_CONCAT(DISTINCT s.mercado) AS mercados,
                   (
                       SELECT sn.status FROM snapshots sn
                       WHERE sn.partida_id=p.id ORDER BY sn.id DESC LIMIT 1
                   ) AS ultimo_status,
                   (
                       SELECT sn.placar FROM snapshots sn
                       WHERE sn.partida_id=p.id ORDER BY sn.id DESC LIMIT 1
                   ) AS ultimo_placar,
                   (
                       SELECT sn.coletado_em FROM snapshots sn
                       WHERE sn.partida_id=p.id ORDER BY sn.id DESC LIMIT 1
                   ) AS ultima_coleta
            FROM partidas p
            JOIN sinais s ON s.partida_id=p.id AND s.status='aprovado'
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE r.sinal_id IS NULL AND s.odd BETWEEN ? AND ?
              AND s.regra_versao=?
            GROUP BY p.id
            ORDER BY primeiro_sinal
            """,
            (limites.odd_minima, limites.odd_maxima, regra_versao),
        ).fetchall()
        if not pendencias:
            print("nenhuma")
        for item in pendencias:
            cobertura = (
                f"API {item['api_fixture_id']}"
                if item["api_fixture_id"] is not None else "somente PackBall"
            )
            print(
                f"{item['mandante']} x {item['visitante']} | "
                f"{item['mercados']} | último={item['ultimo_status']} "
                f"{item['ultimo_placar']} em {item['ultima_coleta']} | "
                f"{cobertura}\n  {item['packball_url']}"
            )
    finally:
        banco.fechar()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Relatório por versão das regras do Bot PackBall."
    )
    parser.add_argument(
        "--regra",
        default=VERSAO_REGRAS,
        help=f"Versão a consultar (padrão: {VERSAO_REGRAS}).",
    )
    argumentos = parser.parse_args()
    main(argumentos.regra)
