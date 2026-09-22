import argparse
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from backtest import (
    AvaliadorBacktest,
    STATUS_ANULADOS,
    STATUS_FINAIS,
    resumir_funil_sinais,
)
from banco import BancoMonitor
from dataset_temporal import (
    avaliar_corte_sombra,
    avaliar_discriminacao_temporal,
    construir_dataset_temporal,
    dividir_cronologicamente,
)
from linhagem_regras import (
    registrar_inicio_linhagem_sinais,
    registrar_ou_validar_linhagem_regra,
)
from mercados import MERCADOS_CALIBRADOS
from motor_sinais import VERSAO_FEATURES, VERSAO_REGRAS, gerar_candidatos
from mercados import filtrar_mercados_operacionais
from qualidade_dados import avaliar_qualidade
from proveniencia_odds import aplicar_proveniencia_odds


MERCADOS = MERCADOS_CALIBRADOS


def _json(valor, padrao):
    try:
        return json.loads(valor) if valor not in (None, "") else padrao
    except (json.JSONDecodeError, TypeError):
        return padrao


def _odds_snapshot(conexao, snapshot):
    odds = {"pre_jogo": [], "ao_vivo": []}
    origens = []
    estados_cache = []
    for linha in conexao.execute(
        """
        SELECT tipo, mercado, dados, estrutura_json
        FROM odds WHERE snapshot_id=? ORDER BY id
        """,
        (snapshot["id"],),
    ).fetchall():
        estrutura = _json(linha["estrutura_json"], {})
        origem = estrutura.get("coletado_em") or snapshot["coletado_em"]
        instante_origem = _data_historica(origem)
        if instante_origem is not None:
            origens.append((instante_origem, origem))
        cache = bool(estrutura.get("cache"))
        estados_cache.append(cache)
        odds.setdefault(linha["tipo"], []).append(
            {
                "mercado": linha["mercado"],
                "dados": linha["dados"],
                **estrutura,
                "coletado_em": origem,
                "cache": cache,
            }
        )
    odds["movimentacao"] = _json(
        snapshot["movimentacao_odds_json"], []
    )
    origem_mais_antiga = min(origens, default=(None, None), key=lambda x: x[0])
    idade = _idade_historica(
        snapshot["coletado_em"], origem_mais_antiga[1]
    )
    odds["_metadados"] = {
        "cache": bool(estados_cache) and all(estados_cache),
        "coletado_em": origem_mais_antiga[1],
        "idade_segundos": round(idade, 3) if idade is not None else None,
    }
    return odds


def _data_historica(valor):
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _idade_historica(referencia, origem):
    referencia = _data_historica(referencia)
    origem = _data_historica(origem)
    if referencia is None or origem is None:
        return None
    try:
        segundos = (referencia - origem).total_seconds()
    except TypeError:
        segundos = (
            referencia.replace(tzinfo=None) - origem.replace(tzinfo=None)
        ).total_seconds()
    return max(0.0, segundos)


def _eventos_snapshot(conexao, snapshot_id):
    return [
        _json(item["payload_json"], {})
        for item in conexao.execute(
            """
            SELECT payload_json FROM eventos
            WHERE snapshot_id=? ORDER BY id
            """,
            (snapshot_id,),
        ).fetchall()
    ]


def _status_terminal(status):
    texto = str(status or "").strip().lower()
    return any(item in texto for item in STATUS_FINAIS + STATUS_ANULADOS)


def _analisar_features_temporais_replay(conexao):
    """Produz pesquisa reproduzível sem promover o replay à calibração."""
    analises = {}
    for mercado in MERCADOS:
        dataset = construir_dataset_temporal(
            conexao,
            mercado,
            regra_versao=VERSAO_REGRAS,
        )
        desenvolvimento, validacao = dividir_cronologicamente(
            dataset["registros"]
        )
        analises[mercado] = {
            "schema_features": dataset["schema_features"],
            "regra_fingerprint": dataset["regra_fingerprint"],
            "dataset_fingerprint": dataset["fingerprint"],
            "elegiveis_independentes": (
                dataset["elegiveis_independentes"]
            ),
            "registros_validos": dataset["registros_validos"],
            "excluidos_features_invalidas": (
                dataset["excluidos_features_invalidas"]
            ),
            "exclusoes_por_motivo": dataset["exclusoes_por_motivo"],
            "cobertura": dataset["cobertura"],
            "desenvolvimento": len(desenvolvimento),
            "validacao_cronologica": len(validacao),
            "discriminacao_temporal": avaliar_discriminacao_temporal(
                dataset["registros"]
            ),
            "corte_sombra": avaliar_corte_sombra(dataset["registros"]),
        }
    return {
        "uso": "pesquisa_offline_nao_incorpora_calibracao_oficial",
        "separacao": "cronologica_70_30",
        "mercados": analises,
    }


def executar_replay(caminho_origem, caminho_destino):
    caminho_origem = Path(caminho_origem)
    caminho_destino = Path(caminho_destino)
    if caminho_destino.exists():
        raise FileExistsError(
            f"Destino do replay já existe: {caminho_destino}"
        )
    uri = caminho_origem.resolve().as_uri() + "?mode=ro"
    origem = sqlite3.connect(uri, uri=True, timeout=30)
    origem.row_factory = sqlite3.Row
    destino = BancoMonitor(caminho_destino)
    avaliador = AvaliadorBacktest(destino)
    processados = 0
    resolvidos = 0
    try:
        linhagem = registrar_ou_validar_linhagem_regra(
            destino.conexao,
            Path(__file__).parent,
            VERSAO_REGRAS,
            VERSAO_FEATURES,
        )
        registrar_inicio_linhagem_sinais(
            destino.conexao,
            VERSAO_REGRAS,
            linhagem["fingerprint_atual"],
        )
        snapshots = origem.execute(
            """
            SELECT s.*, p.packball_url, p.mandante, p.visitante,
                   p.pais, p.liga
            FROM snapshots s
            JOIN partidas p ON p.id=s.partida_id
            ORDER BY datetime(s.coletado_em), s.id
            """
        ).fetchall()
        for snapshot in snapshots:
            estatisticas = _json(snapshot["estatisticas_json"], {})
            evolucao = _json(snapshot["evolucao_json"], {})
            confirmacao = _json(snapshot["confirmacao_api_json"], None)
            eventos = _eventos_snapshot(origem, snapshot["id"])
            if confirmacao and eventos:
                confirmacao["eventos"] = eventos
            jogo = {
                "url": snapshot["packball_url"],
                "mandante": snapshot["mandante"],
                "visitante": snapshot["visitante"],
                "pais": snapshot["pais"],
                "liga": snapshot["liga"],
                "placar": snapshot["placar"],
                "status": snapshot["status"],
                "texto_linha": snapshot["texto_linha"],
            }
            qualidade = _json(snapshot["qualidade_json"], {})
            if not qualidade:
                qualidade = avaliar_qualidade(
                    jogo, estatisticas, confirmacao
                )
            odds = _odds_snapshot(origem, snapshot)
            evolucao["escanteios_intervalo"] = (
                destino.total_escanteios_intervalo(
                    packball_url=jogo["url"]
                )
            )
            registro = {
                "coletado_em": snapshot["coletado_em"],
                **jogo,
                "estatisticas": estatisticas,
                "evolucao": evolucao,
                "odds": odds,
                "confirmacao_api": confirmacao,
                "estatisticas_api": _json(
                    snapshot["estatisticas_api_json"], None
                ),
                "qualidade": qualidade,
            }
            novo_snapshot = destino.salvar_registro(registro)
            if not novo_snapshot:
                continue
            processados += 1
            resolvidos += avaliador.avaliar_snapshot(novo_snapshot)
            if _status_terminal(snapshot["status"]):
                continue
            candidatos = gerar_candidatos(
                jogo, estatisticas, evolucao, odds, qualidade
            )
            aplicar_proveniencia_odds(
                candidatos,
                odds,
                instante=datetime.fromisoformat(snapshot["coletado_em"]),
            )
            candidatos = filtrar_mercados_operacionais(candidatos)
            for candidato in candidatos:
                candidato["regra_fingerprint"] = (
                    linhagem["fingerprint_atual"]
                )
            destino.salvar_candidatos(
                novo_snapshot, candidatos, snapshot["coletado_em"]
            )

        metricas = {
            mercado: avaliador.metricas(
                mercado=mercado, regra_versao=VERSAO_REGRAS
            )
            for mercado in MERCADOS
        }
        contagens = destino.contagens()
        aprovados = destino.conexao.execute(
            "SELECT COUNT(*) FROM sinais WHERE status='aprovado'"
        ).fetchone()[0]
        pendentes = destino.conexao.execute(
            """
            SELECT COUNT(*) FROM sinais s
            LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='aprovado' AND r.sinal_id IS NULL
            """
        ).fetchone()[0]
        unidades_independentes = {
            mercado: metricas[mercado]["amostra"]
            for mercado in MERCADOS
        }
        partidas_com_liquidacao_bruta = destino.conexao.execute(
            """
            SELECT COUNT(DISTINCT s.partida_id)
            FROM sinais s
            JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='aprovado'
              AND r.resultado IN (
                  'green', 'half_green', 'red', 'half_red'
              )
            """
        ).fetchone()[0]
        limites = avaliador.limites_risco
        funil = resumir_funil_sinais(
            destino.conexao,
            VERSAO_REGRAS,
            limites.odd_minima,
            limites.odd_maxima,
        )
        analise_temporal = _analisar_features_temporais_replay(
            destino.conexao
        )
        partidas_elegiveis = destino.conexao.execute(
            """
            SELECT COUNT(DISTINCT s.partida_id)
            FROM sinais s
            JOIN resultados_sinais r ON r.sinal_id=s.id
            WHERE s.status='aprovado' AND s.odd BETWEEN ? AND ?
              AND r.resultado IN (
                  'green', 'half_green', 'red', 'half_red'
              )
            """,
            (limites.odd_minima, limites.odd_maxima),
        ).fetchone()[0]
        return {
            "modo": "replay_offline_origem_somente_leitura",
            "regra_versao": VERSAO_REGRAS,
            "snapshots_processados": processados,
            "decisoes_geradas_brutas": contagens["sinais"],
            "decisoes_aprovadas_brutas": aprovados,
            "liquidacoes_brutas": resolvidos,
            "pendencias_brutas": pendentes,
            "partidas_com_liquidacao_bruta": (
                partidas_com_liquidacao_bruta
            ),
            "partidas_elegiveis_independentes": partidas_elegiveis,
            "unidades_independentes_por_mercado": unidades_independentes,
            "funil_por_mercado": funil,
            "metricas": metricas,
            "analise_temporal": analise_temporal,
            "destino": str(caminho_destino),
        }
    finally:
        origem.close()
        destino.fechar()


def main():
    parser = argparse.ArgumentParser(
        description="Replay cronológico offline do histórico PackBall."
    )
    parser.add_argument(
        "--origem", default=str(Path(__file__).parent / "monitor_packball.db")
    )
    parser.add_argument("--destino")
    argumentos = parser.parse_args()
    if argumentos.destino:
        resultado = executar_replay(argumentos.origem, argumentos.destino)
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return
    destino = Path(__file__).parent / (
        f".packball_replay_{uuid.uuid4().hex}.db"
    )
    try:
        resultado = executar_replay(argumentos.origem, destino)
        resultado["destino"] = "temporario_removido_ao_final"
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    finally:
        for sufixo in ("", "-wal", "-shm"):
            Path(str(destino) + sufixo).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
