"""Manutenção explícita de backups SQLite legados com round-trip verificado."""

import argparse
import json
from pathlib import Path

from backup_banco import BackupBanco
from backup_compactado import compactar_backup_verificado
from controle_sistema import ler_modo_manutencao
from processo_monitor import trava_em_uso


VERSAO = "compactacao-backups-legados-manutencao-v1"


def _resumo_resultado(resultado):
    return {
        "arquivo": resultado.get("arquivo") or resultado.get("origem"),
        "executado": bool(resultado.get("executado")),
        "saudavel": bool(resultado.get("saudavel")),
        "estado": resultado.get("estado"),
        "tamanho_original_mb": resultado.get("tamanho_original_mb"),
        "tamanho_compactado_mb": resultado.get("tamanho_compactado_mb"),
        "espaco_liberado_mb": resultado.get("espaco_liberado_mb"),
        "limpeza_pendente": bool(resultado.get("limpeza_pendente")),
        "motivo": resultado.get("motivo"),
    }


def _compactar_candidato(gerenciador, origem):
    origem = Path(origem)
    tamanho_original = origem.stat().st_size
    resultado = compactar_backup_verificado(
        origem,
        remover_original=True,
    )
    if not resultado.get("saudavel"):
        gerenciador.registrar_legado_incompativel(origem, resultado)
        return {
            **resultado,
            "executado": True,
            "origem": origem.name,
            "original_preservado": origem.exists(),
        }
    destino = Path(resultado["caminho"])
    tamanho_compactado = destino.stat().st_size
    return {
        **resultado,
        "executado": True,
        "origem": origem.name,
        "destino": destino.name,
        "tamanho_original_mb": round(tamanho_original / 1024 ** 2, 1),
        "tamanho_compactado_mb": round(tamanho_compactado / 1024 ** 2, 1),
        "espaco_liberado_mb": round(
            max(tamanho_original - tamanho_compactado, 0) / 1024 ** 2,
            1,
        ),
        "original_preservado": origem.exists(),
    }


def executar_compactacao(
    pasta, maximo=1, exigir_manutencao=True, verificar_trava=None
):
    pasta = Path(pasta)
    verificar_trava = verificar_trava or trava_em_uso
    maximo = int(maximo)
    if maximo < 1:
        raise ValueError("maximo_deve_ser_positivo")
    manutencao = ler_modo_manutencao(pasta)
    processos_ativos = [
        nome for nome in ("monitor", "watchdog")
        if verificar_trava(pasta / f"{nome}_instancia.lock")
    ]
    if exigir_manutencao and (
        not manutencao.get("ativo") or processos_ativos
    ):
        return {
            "versao": VERSAO,
            "saudavel": False,
            "estado": "manutencao_segura_necessaria",
            "modo_manutencao_ativo": bool(manutencao.get("ativo")),
            "processos_ativos": processos_ativos,
            "executados": 0,
            "resultados": [],
        }

    gerenciador = BackupBanco(pasta / "backups", compactar=True)
    resultados = []
    candidatos = gerenciador.listar_legados_compactaveis()[:maximo]
    for origem in candidatos:
        resultado = _compactar_candidato(gerenciador, origem)
        resultados.append(resultado)
        print(json.dumps({
            "evento": "compactacao_backup",
            "ordem": len(resultados),
            "resultado": _resumo_resultado(resultado),
        }, ensure_ascii=False), flush=True)
        if resultado.get("limpeza_pendente"):
            # O arquivo válido ficou preservado; outros candidatos independentes
            # ainda podem ser tratados com segurança.
            continue
    restantes = gerenciador.listar_legados_compactaveis()
    falhas = [item for item in resultados if not item.get("saudavel")]
    return {
        "versao": VERSAO,
        "saudavel": not falhas,
        "estado": (
            "concluida"
            if not restantes and not falhas
            else "concluida_com_incompativeis_preservados"
            if not restantes
            else "parcial"
        ),
        "modo_manutencao_ativo": bool(manutencao.get("ativo")),
        "processos_ativos": processos_ativos,
        "executados": sum(
            bool(item.get("executado")) for item in resultados
        ),
        "espaco_liberado_mb": round(sum(
            float(item.get("espaco_liberado_mb") or 0)
            for item in resultados if item.get("saudavel")
        ), 1),
        "restantes": len(restantes),
        "resultados": resultados,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compacta backups gerenciados somente em manutenção segura."
        )
    )
    parser.add_argument("--executar", action="store_true")
    parser.add_argument("--maximo", type=int, default=1)
    argumentos = parser.parse_args()
    pasta = Path(__file__).parent
    gerenciador = BackupBanco(pasta / "backups", compactar=True)
    if not argumentos.executar:
        candidatos = gerenciador.listar_legados_compactaveis()
        print(json.dumps({
            "versao": VERSAO,
            "estado": "previsualizacao",
            "candidatos": [
                {
                    "arquivo": item.name,
                    "tamanho_mb": round(item.stat().st_size / 1024 ** 2, 1),
                }
                for item in candidatos
            ],
            "executar_com": (
                "python compactar_backups_legados.py --executar --maximo N"
            ),
        }, ensure_ascii=False, indent=2))
        return
    resultado = executar_compactacao(pasta, argumentos.maximo)
    relatorio = {
        chave: valor
        for chave, valor in resultado.items()
        if chave != "resultados"
    }
    relatorio["resultados"] = [
        _resumo_resultado(item) for item in resultado["resultados"]
    ]
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    if not resultado["saudavel"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
