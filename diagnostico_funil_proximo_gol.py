"""Diagnostico marginal do funil prospectivo de Proximo Gol.

O funil cumulativo e apropriado para explicar quantos candidatos atravessam
toda a regra, mas, quando a primeira trava zera, ele esconde quais criterios
tecnicos estao mais perto de serem satisfeitos. Este modulo mede cada criterio
de forma independente e a menor distancia observada por estado de jogo.

Ele usa somente informacao disponivel no instante de cada sinal, nao consulta
resultados, nao escreve no SQLite e nao altera sinais ou Telegram.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from proximo_gol_balanceado_sombra import (
    CHAVE_DEFINICAO,
    avaliar,
)
from politica_proximo_gol_preciso import MOTIVO_PRESSAO, MOTIVO_QUALIDADE
from versoes_challengers_preciso import (
    VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
)


VERSAO = "diagnostico-funil-proximo-gol-marginal-v1"
BANCO = Path(__file__).with_name("monitor_packball.db")
CRITERIOS_TECNICOS = (
    "qualidade_completa",
    "minuto_valido",
    "odd_curta",
    "pressao_balanceada",
    "chute_dominante_recente",
    "pontuacao_tecnica_suficiente",
    "dominio_medio_confirmado",
)
CRITERIO_GATE = "somente_bloqueios_pressao_qualidade"
VERSAO_AUDITORIA_BLOQUEIOS = "auditoria-bloqueios-promissores-v1"


def _gols_placar(placar):
    if isinstance(placar, str):
        partes = placar.replace("x", "-").split("-")
    elif isinstance(placar, (list, tuple)):
        partes = placar
    else:
        return None
    if len(partes) < 2:
        return None
    try:
        return int(float(partes[0])) + int(float(partes[1]))
    except (TypeError, ValueError):
        return None


def _carregar_json(valor, esperado):
    try:
        documento = json.loads(valor or ("{}" if esperado is dict else "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return documento if isinstance(documento, esperado) else None


def diagnosticar_linhas(linhas):
    """Resume proximidade tecnica sem escolher estados por resultado."""
    estados = {}
    invalidas = 0
    total_linhas = 0
    derivadas_excluidas = 0
    for linha in linhas:
        total_linhas += 1
        features = _carregar_json(linha["features_json"], dict)
        motivos = _carregar_json(linha["motivos_json"], list)
        if features is None or motivos is None:
            invalidas += 1
            continue
        # Auditorias silenciosas copiam a mesma decisao original para obter
        # liquidacao contrafactual. Elas nao sao uma nova observacao do funil
        # e seus bloqueios foram movidos para metadados; inclui-las faria o
        # diagnostico enxergar artificialmente uma decisao sem bloqueios.
        if isinstance(features.get("auditoria_bloqueio"), dict):
            derivadas_excluidas += 1
            continue
        gols = features.get("gols_atuais")
        try:
            gols = int(float(gols))
        except (TypeError, ValueError):
            gols = _gols_placar(linha["placar"])
        if gols is None:
            invalidas += 1
            continue
        bloqueios = tuple(sorted({
            str(item).split("bloqueio:", 1)[1].strip()
            for item in motivos
            if str(item).startswith("bloqueio:")
        }))
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            "odd": linha["odd"],
            "pontuacao_tecnica": linha["pontuacao_tecnica"],
            "bloqueios": bloqueios,
            "features": features,
        }
        criterios = avaliar(candidato)["criterios"]
        chave = (int(linha["partida_id"]), gols)
        estado = estados.setdefault(chave, {
            "criterios_alguma_vez": {
                criterio: False
                for criterio in (*CRITERIOS_TECNICOS, CRITERIO_GATE)
            },
            "melhor": None,
        })
        for criterio in estado["criterios_alguma_vez"]:
            estado["criterios_alguma_vez"][criterio] = bool(
                estado["criterios_alguma_vez"][criterio]
                or criterios.get(criterio)
            )
        falhas = tuple(
            criterio for criterio in CRITERIOS_TECNICOS
            if not criterios.get(criterio)
        )
        observacao = {
            "sinal_id": int(linha["id"]),
            "falhas": falhas,
            "bloqueios": bloqueios,
            "gate": bool(criterios.get(CRITERIO_GATE)),
            "criado_em": str(linha["criado_em"]),
        }
        melhor = estado["melhor"]
        chave_ordem = (
            len(falhas), observacao["criado_em"], observacao["sinal_id"]
        )
        if melhor is None or chave_ordem < melhor["chave_ordem"]:
            estado["melhor"] = {**observacao, "chave_ordem": chave_ordem}

    marginais = {
        criterio: sum(
            bool(estado["criterios_alguma_vez"][criterio])
            for estado in estados.values()
        )
        for criterio in (*CRITERIOS_TECNICOS, CRITERIO_GATE)
    }
    total_estados = len(estados)
    falhas_marginais = {
        criterio: total_estados - quantidade
        for criterio, quantidade in marginais.items()
    }
    gargalo = max(
        CRITERIOS_TECNICOS,
        key=lambda criterio: (
            falhas_marginais[criterio],
            -CRITERIOS_TECNICOS.index(criterio),
        ),
        default=None,
    )
    distancias = Counter()
    combinacoes = Counter()
    bloqueios_adicionais_prontos = Counter()
    prontos_com_gate = 0
    for estado in estados.values():
        melhor = estado["melhor"]
        if melhor is None:
            continue
        distancias[len(melhor["falhas"])] += 1
        combinacoes[melhor["falhas"]] += 1
        if not melhor["falhas"]:
            if melhor["gate"]:
                prontos_com_gate += 1
            extras = set(melhor["bloqueios"]) - {
                MOTIVO_PRESSAO, MOTIVO_QUALIDADE
            }
            bloqueios_adicionais_prontos.update(extras)
    combinacoes_ordenadas = sorted(
        combinacoes.items(),
        key=lambda item: (len(item[0]), -item[1], item[0]),
    )
    menor_distancia = min(distancias, default=None)
    return {
        "versao": VERSAO,
        "linhas_avaliadas": total_linhas,
        "linhas_invalidas": invalidas,
        "linhas_derivadas_excluidas": derivadas_excluidas,
        "estados_independentes": total_estados,
        "criterio_independencia": "partida+estado_de_gols",
        "passagens_marginais": marginais,
        "falhas_marginais": falhas_marginais,
        "gargalo_tecnico_marginal": gargalo,
        "distancia_minima_observada": menor_distancia,
        "estados_por_distancia_minima": {
            str(distancia): quantidade
            for distancia, quantidade in sorted(distancias.items())
        },
        "combinacoes_quase_candidatas": [
            {"falhas": list(falhas), "estados": quantidade}
            for falhas, quantidade in combinacoes_ordenadas[:10]
        ],
        "candidato_pronto_sem_gate": int(distancias.get(0, 0)),
        "candidato_pronto_com_gate": prontos_com_gate,
        "bloqueios_adicionais_estados_tecnicamente_prontos": dict(
            bloqueios_adicionais_prontos.most_common()
        ),
        "interpretação": (
            "distancia zero significa que todos os criterios tecnicos foram "
            "satisfeitos no mesmo snapshot; o gate de bloqueios permanece "
            "separado e nunca e relaxado por este diagnostico"
        ),
        "usa_resultados": False,
        "somente_leitura": True,
        "altera_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def resumir_auditoria_contrafactual(linhas):
    """Liquida descartes observacionais sem escolher a unidade pelo desfecho."""
    por_estado = {}
    invalidas = 0
    for linha in linhas:
        features = _carregar_json(linha["features_json"], dict)
        if features is None:
            invalidas += 1
            continue
        auditoria = features.get("auditoria_bloqueio")
        if not isinstance(auditoria, dict):
            invalidas += 1
            continue
        bloqueios = auditoria.get("bloqueios_originais")
        if not isinstance(bloqueios, list):
            invalidas += 1
            continue
        gols = features.get("gols_atuais")
        try:
            gols = int(float(gols))
        except (TypeError, ValueError):
            gols = _gols_placar(linha["placar"])
        if gols is None:
            invalidas += 1
            continue
        candidato = {
            "mercado": "proximo_gol",
            "regra_versao": VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            "odd": linha["odd"],
            "pontuacao_tecnica": linha["pontuacao_tecnica"],
            "bloqueios": bloqueios,
            "features": features,
        }
        criterios = avaliar(candidato)["criterios"]
        falhas = tuple(
            criterio for criterio in CRITERIOS_TECNICOS
            if not criterios.get(criterio)
        )
        item = {
            "sinal_id": int(linha["id"]),
            "criado_em": str(linha["criado_em"]),
            "falhas": falhas,
            "resultado": linha["resultado"],
            "retorno_unidades": linha["retorno_unidades"],
        }
        chave = (int(linha["partida_id"]), gols)
        anterior = por_estado.get(chave)
        ordem = (item["criado_em"], item["sinal_id"])
        if anterior is None or ordem < anterior["ordem"]:
            por_estado[chave] = {**item, "ordem": ordem}

    por_distancia = {}
    validos = []
    pendentes = 0
    resultados_invalidos = 0
    for item in por_estado.values():
        distancia = str(len(item["falhas"]))
        faixa = por_distancia.setdefault(distancia, {
            "estados": 0, "validos": 0, "greens": 0, "reds": 0,
            "pendentes": 0, "lucro_unidades": 0.0,
        })
        faixa["estados"] += 1
        resultado = item["resultado"]
        if resultado is None:
            pendentes += 1
            faixa["pendentes"] += 1
            continue
        if resultado not in {"green", "red"}:
            resultados_invalidos += 1
            continue
        try:
            retorno = float(item["retorno_unidades"])
        except (TypeError, ValueError):
            resultados_invalidos += 1
            continue
        validos.append((resultado, retorno))
        faixa["validos"] += 1
        faixa[f"{resultado}s"] += 1
        faixa["lucro_unidades"] += retorno
    for faixa in por_distancia.values():
        faixa["lucro_unidades"] = round(faixa["lucro_unidades"], 4)
        faixa["roi"] = (
            round(faixa["lucro_unidades"] / faixa["validos"], 4)
            if faixa["validos"] else None
        )
    lucro = sum(retorno for _, retorno in validos)
    amostra_minima = 30
    return {
        "versao": "auditoria-contrafactual-proximo-gol-v1",
        "origem": VERSAO_AUDITORIA_BLOQUEIOS,
        "populacao": "primeira_auditoria_por_partida_e_estado_de_gols",
        "selecao_antes_do_resultado": True,
        "estados": len(por_estado),
        "validos": len(validos),
        "greens": sum(resultado == "green" for resultado, _ in validos),
        "reds": sum(resultado == "red" for resultado, _ in validos),
        "pendentes": pendentes,
        "invalidos": invalidas + resultados_invalidos,
        "lucro_unidades": round(lucro, 4),
        "roi": round(lucro / len(validos), 4) if validos else None,
        "por_distancia_tecnica": por_distancia,
        "amostra_minima_diagnostico": amostra_minima,
        "amostra_suficiente": len(validos) >= amostra_minima,
        "natureza": "exploratoria_nao_inferencial",
        "pre_registrada_para_decisao": False,
        "pode_alterar_filtro": False,
        "altera_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def executar(caminho_banco=None):
    caminho = Path(caminho_banco or BANCO).resolve()
    with closing(sqlite3.connect(
        caminho.as_uri() + "?mode=ro", uri=True
    )) as conexao:
        conexao.row_factory = sqlite3.Row
        linha = conexao.execute(
            "SELECT valor FROM metadados WHERE chave=?",
            (CHAVE_DEFINICAO,),
        ).fetchone()
        if linha is None:
            raise RuntimeError("ancora_proximo_gol_balanceado_ausente")
        documento = json.loads(linha["valor"])
        linhas = conexao.execute(
            """
            SELECT s.id,s.partida_id,s.criado_em,s.odd,
                   s.pontuacao_tecnica,s.motivos_json,s.features_json,
                   snapshot.placar
            FROM sinais s
            JOIN snapshots snapshot ON snapshot.id=s.snapshot_id
            WHERE datetime(s.criado_em)>=datetime(?)
              AND s.mercado='proximo_gol'
              AND s.regra_versao=?
            ORDER BY datetime(s.criado_em),s.id
            """,
            (
                documento["registrado_em"],
                VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
            ),
        ).fetchall()
        resultado = diagnosticar_linhas(linhas)
        auditorias = conexao.execute(
            """
            SELECT s.id,s.partida_id,s.criado_em,s.odd,
                   s.pontuacao_tecnica,s.features_json,snapshot.placar,
                   resultado.resultado,resultado.retorno_unidades
            FROM sinais s
            JOIN snapshots snapshot ON snapshot.id=s.snapshot_id
            LEFT JOIN resultados_sinais resultado ON resultado.sinal_id=s.id
            WHERE datetime(s.criado_em)>=datetime(?)
              AND s.mercado='proximo_gol'
              AND s.regra_versao=?
              AND s.status='auditoria'
              AND json_extract(
                    s.features_json, '$.auditoria_bloqueio.versao'
                  )=?
            ORDER BY datetime(s.criado_em),s.id
            """,
            (
                documento["registrado_em"],
                VERSAO_PROXIMO_GOL_FILTRO_PRECISO,
                VERSAO_AUDITORIA_BLOQUEIOS,
            ),
        ).fetchall()
        resultado["auditoria_contrafactual"] = (
            resumir_auditoria_contrafactual(auditorias)
        )
        resultado["ancora"] = documento["registrado_em"]
        return resultado


def main():
    parser = argparse.ArgumentParser(
        description="Diagnostica gargalos marginais do Próximo Gol"
    )
    parser.add_argument("--banco", default=None)
    argumentos = parser.parse_args()
    print(json.dumps(
        executar(argumentos.banco), ensure_ascii=False, indent=2
    ))


if __name__ == "__main__":
    main()
