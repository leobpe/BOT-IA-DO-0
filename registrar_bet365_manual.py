import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from banco import BancoMonitor, normalizar_texto
from bet365_odds import (
    diagnosticar_mercado_escanteios_bet365,
    registrar_observacao_bet365,
)


PASTA = Path(__file__).parent
PASTA_EVIDENCIAS = PASTA / "evidencias_bet365"
TAMANHO_MAXIMO_EVIDENCIA = 15 * 1024 * 1024


def validar_url_evento_bet365(url):
    analisada = urlparse(str(url or "").strip())
    if (
        analisada.scheme != "https"
        or analisada.hostname not in (
            "bet365.bet.br",
            "www.bet365.bet.br",
        )
    ):
        raise ValueError("A URL deve pertencer ao site brasileiro da Bet365.")
    encontrado = re.fullmatch(
        r"/IP/(EV\d+)(?:C\d+)?",
        analisada.fragment,
    )
    if encontrado is None:
        raise ValueError("A URL não contém um evento Bet365 válido.")
    return encontrado.group(1)


def _extensao_imagem(dados):
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if dados.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if (
        len(dados) >= 12
        and dados[:4] == b"RIFF"
        and dados[8:12] == b"WEBP"
    ):
        return ".webp"
    raise ValueError("A evidência precisa ser uma imagem PNG, JPG ou WEBP.")


def preservar_evidencia(caminho, pasta_destino=PASTA_EVIDENCIAS):
    origem = Path(caminho).resolve()
    if not origem.is_file():
        raise FileNotFoundError("Arquivo de evidência não encontrado.")
    tamanho = origem.stat().st_size
    if tamanho <= 0 or tamanho > TAMANHO_MAXIMO_EVIDENCIA:
        raise ValueError("A evidência deve ter entre 1 byte e 15 MB.")
    dados = origem.read_bytes()
    extensao = _extensao_imagem(dados)
    sha256 = hashlib.sha256(dados).hexdigest()
    dia = datetime.now().strftime("%Y%m%d")
    destino_relativo = Path("evidencias_bet365") / dia / (
        f"{sha256}{extensao}"
    )
    destino = Path(pasta_destino).parent / destino_relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.exists():
        temporario = destino.with_suffix(destino.suffix + ".tmp")
        temporario.write_bytes(dados)
        os.replace(temporario, destino)
    return {
        "sha256": sha256,
        "referencia": destino_relativo.as_posix(),
        "tamanho_bytes": tamanho,
    }


def localizar_partida_packball(
    conexao,
    mandante,
    visitante,
    packball_url=None,
):
    if packball_url:
        linhas = conexao.execute(
            """
            SELECT id, packball_url, mandante, visitante
            FROM partidas
            WHERE packball_url=?
            """,
            (str(packball_url).strip(),),
        ).fetchall()
    else:
        linhas = conexao.execute(
            """
            SELECT id, packball_url, mandante, visitante
            FROM partidas
            WHERE mandante_normalizado=?
              AND visitante_normalizado=?
            ORDER BY ultima_coleta DESC
            LIMIT 2
            """,
            (
                normalizar_texto(mandante),
                normalizar_texto(visitante),
            ),
        ).fetchall()
    if len(linhas) != 1:
        raise ValueError(
            "A partida PackBall não foi encontrada de forma única."
        )
    return dict(linhas[0])


def registrar_captura_manual(
    *,
    mandante_packball,
    visitante_packball,
    mandante_bet365,
    visitante_bet365,
    url_evento,
    periodo,
    titulo_mercado,
    linha,
    odd_over,
    odd_under,
    evidencia,
    packball_url=None,
    caminho_banco=None,
    pasta_evidencias=None,
):
    evento_id = validar_url_evento_bet365(url_evento)
    periodo = str(periodo).upper()
    if periodo not in ("FT", "1T", "2T"):
        raise ValueError("Período deve ser FT, 1T ou 2T.")
    if (
        not str(mandante_bet365 or "").strip()
        or not str(visitante_bet365 or "").strip()
    ):
        raise ValueError("Os dois times observados na Bet365 são obrigatórios.")
    periodo_parser = None if periodo == "FT" else periodo
    mercado, motivo = diagnosticar_mercado_escanteios_bet365(
        titulo_mercado,
        [
            {
                "nome": f"Mais de {linha}",
                "odd": odd_over,
            },
            {
                "nome": f"Menos de {linha}",
                "odd": odd_under,
            },
        ],
        periodo=periodo_parser,
        evento_id=evento_id,
        url=url_evento,
    )
    if mercado is None:
        raise ValueError(f"Oferta rejeitada: {motivo}.")
    banco = BancoMonitor(caminho_banco or PASTA / "monitor_packball.db")
    try:
        partida = localizar_partida_packball(
            banco.conexao,
            mandante_packball,
            visitante_packball,
            packball_url,
        )
        prova = preservar_evidencia(
            evidencia,
            pasta_evidencias or PASTA_EVIDENCIAS,
        )
        mercado.update({
            "metodo_coleta": "manual_usuario",
            "evidencia_sha256": prova["sha256"],
            "evidencia_referencia": prova["referencia"],
        })
        observacao_id = registrar_observacao_bet365(
            banco.conexao,
            "oferta_valida",
            partida_id=partida["id"],
            evento_externo_id=evento_id,
            mandante_observado=str(mandante_bet365).strip(),
            visitante_observado=str(visitante_bet365).strip(),
            periodo=periodo,
            mercado=mercado["mercado"],
            motivo="captura_manual_validada",
            oferta=mercado,
            url_origem=url_evento,
            metodo_coleta="manual_usuario",
            evidencia_sha256=prova["sha256"],
            evidencia_referencia=prova["referencia"],
        )
    finally:
        banco.fechar()
    return {
        "estado": "registrada",
        "observacao_id": observacao_id,
        "partida_id": partida["id"],
        "partida": (
            f"{partida['mandante']} x {partida['visitante']}"
        ),
        "evento_id": evento_id,
        "periodo": periodo,
        "mercado": mercado["mercado"],
        "ofertas": (
            mercado.get("ofertas")
            or mercado["ofertas_periodos"][periodo]["ofertas"]
        ),
        "evidencia_sha256": prova["sha256"],
        "evidencia_referencia": prova["referencia"],
        "ativa_no_monitor": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Registra uma captura manual validada de escanteios da Bet365 "
            "sem ativar a fonte no monitor."
        )
    )
    parser.add_argument("--mandante-packball", required=True)
    parser.add_argument("--visitante-packball", required=True)
    parser.add_argument("--mandante-bet365", required=True)
    parser.add_argument("--visitante-bet365", required=True)
    parser.add_argument("--url-evento", required=True)
    parser.add_argument("--periodo", choices=("FT", "1T", "2T"), required=True)
    parser.add_argument("--mercado", required=True)
    parser.add_argument("--linha", required=True)
    parser.add_argument("--odd-over", required=True)
    parser.add_argument("--odd-under", required=True)
    parser.add_argument("--evidencia", required=True)
    parser.add_argument("--packball-url")
    argumentos = parser.parse_args()
    resultado = registrar_captura_manual(
        mandante_packball=argumentos.mandante_packball,
        visitante_packball=argumentos.visitante_packball,
        mandante_bet365=argumentos.mandante_bet365,
        visitante_bet365=argumentos.visitante_bet365,
        url_evento=argumentos.url_evento,
        periodo=argumentos.periodo,
        titulo_mercado=argumentos.mercado,
        linha=argumentos.linha,
        odd_over=argumentos.odd_over,
        odd_under=argumentos.odd_under,
        evidencia=argumentos.evidencia,
        packball_url=argumentos.packball_url,
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
