import argparse
import json
import sqlite3
from pathlib import Path

from motor_sinais import VERSAO_REGRAS


PASTA = Path(__file__).parent


def _json_seguro(valor, padrao):
    try:
        carregado = json.loads(valor) if valor else padrao
    except (TypeError, ValueError, json.JSONDecodeError):
        return padrao
    return carregado


def _total_par(valor):
    if not isinstance(valor, (list, tuple)):
        return None
    try:
        return sum(float(item) for item in valor)
    except (TypeError, ValueError):
        return None


def _max_par(valor):
    if not isinstance(valor, (list, tuple)) or not valor:
        return None
    try:
        return max(float(item) for item in valor)
    except (TypeError, ValueError):
        return None


def formatar_janelas(evolucao):
    partes = []
    for minutos in (5, 10, 15):
        janela = (evolucao or {}).get(str(minutos))
        if not janela:
            partes.append(f"{minutos}m=indisponível")
            continue
        pressao = janela.get("pressao_resumo") or {}
        media = _max_par(pressao.get("media"))
        pico = _max_par(pressao.get("pico"))
        duracao = janela.get("duracao_real_minutos")
        partes.append(
            f"{minutos}m(chutes={_total_par(janela.get('chutes'))}, "
            f"escanteios={_total_par(janela.get('escanteios'))}, "
            f"pressão_média={media}, pico={pico}, "
            f"duração={duracao if duracao is not None else '?'})"
        )
    return " | ".join(partes)


def carregar_auditoria(
    conexao, limite=20, somente_encerradas=False, regra_versao=None
):
    filtros = []
    parametros = []
    if somente_encerradas:
        filtros.append("r.sinal_id IS NOT NULL")
    if regra_versao:
        filtros.append("s.regra_versao=?")
        parametros.append(regra_versao)
    filtro = " AND " + " AND ".join(filtros) if filtros else ""
    linhas = conexao.execute(
        f"""
        WITH origens AS (
            SELECT sinal_id, MIN(entregue_em) AS entregue_em,
                   MIN(canal) AS canal
            FROM entregas_alertas
            WHERE status='entregue' AND canal LIKE '%:teste'
              AND canal NOT LIKE '%:teste:resultado'
            GROUP BY sinal_id
        )
        SELECT s.id AS sinal_id, s.criado_em, s.mercado, s.linha, s.odd,
               s.regra_versao, s.status AS status_sinal,
               s.pontuacao_tecnica, s.motivos_json,
               s.features_json,
               p.mandante, p.visitante, p.packball_url,
               entrada.status AS minuto_entrada,
               entrada.placar AS placar_entrada,
               entrada.estatisticas_json, entrada.evolucao_json,
               entrada.qualidade_json, entrada.movimentacao_odds_json,
               liquidacao.status AS status_liquidacao,
               liquidacao.placar AS placar_liquidacao,
               liquidacao.estatisticas_json AS estatisticas_liquidacao_json,
               ultima.status AS status_ultima_observacao,
               ultima.placar AS placar_ultima_observacao,
               r.resultado, r.retorno_unidades, r.encerrado_em,
               r.fonte_resultado,
               origem.entregue_em AS sinal_entregue_em,
               NOT EXISTS (
                   SELECT 1 FROM sinais anterior
                   WHERE anterior.partida_id=s.partida_id
                     AND anterior.mercado=s.mercado
                     AND anterior.regra_versao=s.regra_versao
                     AND anterior.id<s.id
                     AND anterior.status IN (
                         'aprovado', 'duplicado', 'simulacao'
                     )
               ) AS primeira_decisao_independente,
               EXISTS (
                   SELECT 1 FROM entregas_alertas aviso
                   WHERE aviso.sinal_id=s.id AND aviso.status='entregue'
                     AND aviso.canal=origem.canal || ':resultado'
               ) AS resultado_notificado
        FROM origens origem
        JOIN sinais s ON s.id=origem.sinal_id
        JOIN partidas p ON p.id=s.partida_id
        JOIN snapshots entrada ON entrada.id=s.snapshot_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        LEFT JOIN snapshots liquidacao
          ON liquidacao.id=COALESCE(
              r.snapshot_id_liquidacao,
              (
                  SELECT sl.id FROM snapshots sl
                  WHERE sl.partida_id=s.partida_id
                    AND sl.coletado_em=r.encerrado_em
                  ORDER BY sl.id DESC LIMIT 1
              )
          )
        LEFT JOIN snapshots ultima ON ultima.id=(
            SELECT sf.id FROM snapshots sf
            WHERE sf.partida_id=s.partida_id
              AND sf.coletado_em >= entrada.coletado_em
            ORDER BY sf.id DESC LIMIT 1
        )
        WHERE 1=1 {filtro}
        ORDER BY COALESCE(r.encerrado_em, s.criado_em) DESC, s.id DESC
        LIMIT ?
        """,
        (*parametros, int(limite)),
    ).fetchall()
    resultado = []
    for linha in linhas:
        item = dict(linha)
        item["motivos"] = _json_seguro(item.pop("motivos_json"), [])
        item["features"] = _json_seguro(item.pop("features_json"), {})
        item["estatisticas_entrada"] = _json_seguro(
            item.pop("estatisticas_json"), {}
        )
        item["evolucao_entrada"] = _json_seguro(
            item.pop("evolucao_json"), {}
        )
        item["qualidade_entrada"] = _json_seguro(
            item.pop("qualidade_json"), {}
        )
        item["movimentacao_odds"] = _json_seguro(
            item.pop("movimentacao_odds_json"), []
        )
        item["estatisticas_liquidacao"] = _json_seguro(
            item.pop("estatisticas_liquidacao_json"), {}
        )
        item["resultado_notificado"] = bool(item["resultado_notificado"])
        item["primeira_decisao_independente"] = bool(
            item["primeira_decisao_independente"]
        )
        item["elegivel_amostra_independente"] = bool(
            item["primeira_decisao_independente"]
            and item["status_sinal"] == "aprovado"
        )
        resultado.append(item)
    return resultado


def formatar_item(item):
    resultado = item["resultado"] or "PENDENTE"
    retorno = item["retorno_unidades"]
    retorno_texto = "-" if retorno is None else f"{retorno:+.2f}u"
    motivos = ", ".join(str(valor) for valor in item["motivos"]) or "-"
    if item["resultado"] is None:
        notificacao_resultado = "aguardando_liquidacao"
    elif item["resultado_notificado"]:
        notificacao_resultado = "confirmada"
    else:
        notificacao_resultado = "pendente_envio"
    fonte_odds = (item.get("features") or {}).get("fonte_odds") or "packball"
    return "\n".join(
        [
            (
                f"#{item['sinal_id']} [{item['regra_versao']}] "
                f"{item['mandante']} x {item['visitante']}"
            ),
            (
                f"  {item['mercado']} | linha={item['linha']} | "
                f"odd={item['odd']} | fonte_odd={fonte_odds} | "
                f"nota={item['pontuacao_tecnica']}"
            ),
            (
                "  independência: primeira decisão="
                f"{'sim' if item['primeira_decisao_independente'] else 'não'}"
                " | amostra="
                f"{'elegível' if item['elegivel_amostra_independente'] else 'excluída'}"
                f" | status_banco={item['status_sinal']}"
            ),
            (
                f"  entrada: {item['minuto_entrada']} | "
                f"placar={item['placar_entrada']}"
            ),
            f"  janelas: {formatar_janelas(item['evolucao_entrada'])}",
            (
                f"  liquidação: {item['status_liquidacao'] or '-'} | "
                f"placar={item['placar_liquidacao'] or '-'} | "
                f"fonte={item['fonte_resultado'] or '-'}"
            ),
            (
                "  última observação: "
                f"{item['status_ultima_observacao'] or '-'} | "
                f"placar={item['placar_ultima_observacao'] or '-'}"
            ),
            (
                f"  resultado={resultado} | retorno={retorno_texto} | "
                "Telegram_sinal=entregue em "
                f"{item['sinal_entregue_em']} | "
                f"Telegram_resultado={notificacao_resultado}"
            ),
            f"  motivos: {motivos}",
        ]
    )


def main():
    parser = argparse.ArgumentParser(
        description="Audita sinais de simulação e seus resultados."
    )
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument("--somente-encerradas", action="store_true")
    parser.add_argument(
        "--regra",
        default=VERSAO_REGRAS,
        help=(
            "Versão a auditar; use 'todas' para não filtrar "
            f"(padrão: {VERSAO_REGRAS})."
        ),
    )
    argumentos = parser.parse_args()
    caminho = PASTA / "monitor_packball.db"
    uri = caminho.resolve().as_uri() + "?mode=ro"
    conexao = sqlite3.connect(uri, uri=True, timeout=10)
    conexao.row_factory = sqlite3.Row
    try:
        itens = carregar_auditoria(
            conexao,
            limite=max(1, argumentos.limite),
            somente_encerradas=argumentos.somente_encerradas,
            regra_versao=(
                None if argumentos.regra.lower() == "todas"
                else argumentos.regra
            ),
        )
    finally:
        conexao.close()
    print(f"Simulações auditadas: {len(itens)}")
    for item in itens:
        print(formatar_item(item))
        print("-" * 60)


if __name__ == "__main__":
    main()
