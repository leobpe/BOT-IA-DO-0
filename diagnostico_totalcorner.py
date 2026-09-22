import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


PASTA = Path(__file__).parent
ARQUIVO_ENV = PASTA / ".env"
ARQUIVO_RELATORIO = PASTA / "totalcorner_diagnostico.json"
URL_AO_VIVO = "https://api.totalcorner.com/v1/match/today"
VERSAO_DIAGNOSTICO = "totalcorner-prova-1t-v1"


def _numero(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _valor_resumido(valor, profundidade=0):
    if profundidade >= 3:
        return "<omitido>"
    if isinstance(valor, dict):
        return {
            str(chave): _valor_resumido(item, profundidade + 1)
            for chave, item in list(valor.items())[:12]
        }
    if isinstance(valor, list):
        return [
            _valor_resumido(item, profundidade + 1)
            for item in valor[:8]
        ]
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)[:200]


def _campos_cantos(partida):
    return {
        str(chave): _valor_resumido(valor)
        for chave, valor in (partida or {}).items()
        if "corner" in str(chave).casefold()
    }


def _candidatos_duas_opcoes(valor, caminho=""):
    candidatos = []
    if isinstance(valor, dict):
        chaves = {str(chave).casefold(): chave for chave in valor}
        chave_linha = next(
            (
                chaves[nome] for nome in ("line", "linha", "handicap")
                if nome in chaves
            ),
            None,
        )
        chave_over = next(
            (chaves[nome] for nome in ("over", "mais de") if nome in chaves),
            None,
        )
        chave_under = next(
            (
                chaves[nome]
                for nome in ("under", "menos de")
                if nome in chaves
            ),
            None,
        )
        tem_exactly = any(
            nome in chaves for nome in ("exactly", "exatamente", "exact")
        )
        if (
            not tem_exactly
            and chave_linha is not None
            and chave_over is not None
            and chave_under is not None
            and _numero(valor[chave_over]) is not None
            and _numero(valor[chave_under]) is not None
        ):
            candidatos.append({
                "caminho": caminho,
                "linha": str(valor[chave_linha]),
                "over": _numero(valor[chave_over]),
                "under": _numero(valor[chave_under]),
                "formato": "objeto_over_under",
            })
        for chave, item in valor.items():
            candidatos.extend(
                _candidatos_duas_opcoes(
                    item, f"{caminho}.{chave}".strip(".")
                )
            )
    elif isinstance(valor, list):
        # O histórico documentado usa exatamente sete posições:
        # status, linha, over, under, horário, cantos casa e cantos fora.
        if (
            len(valor) == 7
            and _numero(valor[2]) is not None
            and _numero(valor[3]) is not None
            and _numero(valor[2]) > 1
            and _numero(valor[3]) > 1
        ):
            candidatos.append({
                "caminho": caminho,
                "linha": str(valor[1]),
                "over": _numero(valor[2]),
                "under": _numero(valor[3]),
                "horario": str(valor[4]),
                "formato": "historico_sete_campos",
            })
        for indice, item in enumerate(valor):
            candidatos.extend(
                _candidatos_duas_opcoes(
                    item, f"{caminho}[{indice}]"
                )
            )
    return candidatos


def gerar_relatorio(payload, cabecalhos=None):
    payload = payload if isinstance(payload, dict) else {}
    partidas = payload.get("data")
    if not isinstance(partidas, list):
        partidas = []
    evidencias = []
    candidatos = []
    for partida in partidas:
        if not isinstance(partida, dict):
            continue
        campos = _campos_cantos(partida)
        if not campos:
            continue
        registro = {
            "id": partida.get("id"),
            "mandante": partida.get("h"),
            "visitante": partida.get("a"),
            "status": partida.get("status"),
            "campos_cantos": campos,
        }
        evidencias.append(registro)
        for candidato in _candidatos_duas_opcoes(campos):
            candidatos.append({
                "partida_id": partida.get("id"),
                "mandante": partida.get("h"),
                "visitante": partida.get("a"),
                **candidato,
            })
    cabecalhos = cabecalhos or {}
    return {
        "versao": VERSAO_DIAGNOSTICO,
        "gerado_em": datetime.now().replace(microsecond=0).isoformat(),
        "endpoint": URL_AO_VIVO,
        "requisicoes_realizadas": 1,
        "sucesso_provedor": payload.get("success") == 1,
        "erro_provedor": _valor_resumido(payload.get("error")),
        "partidas_recebidas": len(partidas),
        "partidas_com_campos_de_cantos": len(evidencias),
        "evidencias": evidencias[:20],
        "candidatos_estruturais_duas_opcoes": candidatos[:50],
        "candidato_1t_encontrado": bool(candidatos),
        "habilita_integracao_automatica": False,
        "limite_requisicoes": cabecalhos.get("X-Rate-Limit-Limit"),
        "requisicoes_restantes": cabecalhos.get(
            "X-Rate-Limit-Remaining"
        ),
        "observacao": (
            "Candidato estrutural exige revisão do JSON real antes de "
            "qualquer integração."
        ),
    }


def consultar_totalcorner(token, abrir=urlopen, timeout=15):
    if not str(token or "").strip():
        raise ValueError("TOTALCORNER_API_TOKEN não configurado")
    consulta = urlencode(
        {
            "token": str(token).strip(),
            "type": "inplay",
            "columns": "cornerLineHalf",
        }
    )
    requisicao = Request(
        f"{URL_AO_VIVO}?{consulta}",
        headers={"User-Agent": "BotPackBall-Diagnostico/1.0"},
    )
    try:
        with abrir(requisicao, timeout=timeout) as resposta:
            conteudo = resposta.read().decode("utf-8")
            cabecalhos = dict(resposta.headers.items())
        payload = json.loads(conteudo)
    except (TypeError, ValueError, UnicodeDecodeError) as erro:
        raise RuntimeError("Resposta TotalCorner não é JSON válido") from erro
    return gerar_relatorio(payload, cabecalhos)


def salvar_relatorio(relatorio, caminho=ARQUIVO_RELATORIO):
    caminho = Path(caminho)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(caminho)
    return caminho


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Faz uma única consulta segura para comprovar odds de cantos 1T."
        )
    )
    parser.add_argument(
        "--saida", type=Path, default=ARQUIVO_RELATORIO
    )
    argumentos = parser.parse_args()
    load_dotenv(ARQUIVO_ENV)
    token = os.getenv("TOTALCORNER_API_TOKEN")
    if not token:
        raise SystemExit(
            "TOTALCORNER_API_TOKEN não encontrado no .env; "
            "nenhuma consulta foi realizada."
        )
    relatorio = consultar_totalcorner(token)
    caminho = salvar_relatorio(relatorio, argumentos.saida)
    print(
        "Diagnóstico TotalCorner concluído com uma consulta. "
        f"Partidas={relatorio['partidas_recebidas']} | "
        "candidatos estruturais="
        f"{len(relatorio['candidatos_estruturais_duas_opcoes'])} | "
        f"relatório={caminho}"
    )
    print("A fonte permanece desligada do monitor.")


if __name__ == "__main__":
    main()
