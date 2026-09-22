import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


RESULTADOS_RESOLUCAO = ("entregue", "nao_enviado")


def _agora_iso(agora=None):
    return (agora or datetime.now()).replace(microsecond=0).isoformat()


def listar_notificacoes_incertas(
    conexao, agora=None, tolerancia_minutos=2
):
    limite = (
        (agora or datetime.now()) - timedelta(minutes=tolerancia_minutos)
    ).replace(microsecond=0).isoformat()
    linhas = conexao.execute(
        """
        SELECT id AS notificacao_id, chave, destino, resumo,
               criado_em, tentado_em, status, tentativas
        FROM notificacoes_operacionais
        WHERE status IN ('enviando', 'tentando')
          AND datetime(tentado_em) <= datetime(?)
        ORDER BY tentado_em, id
        """,
        (limite,),
    ).fetchall()
    return [dict(linha) for linha in linhas]


def resolver_notificacao_operacional(
    conexao, notificacao_id, resultado, agora=None,
    telegram_message_id=None,
):
    if resultado not in RESULTADOS_RESOLUCAO:
        raise ValueError("Resultado de reconciliação inválido.")
    if resultado == "entregue":
        if isinstance(telegram_message_id, bool):
            telegram_message_id = None
        try:
            telegram_message_id = int(telegram_message_id)
        except (TypeError, ValueError):
            telegram_message_id = 0
        if telegram_message_id <= 0:
            raise ValueError(
                "telegram_message_id positivo é obrigatório para confirmar "
                "uma notificação operacional."
            )
    instante = _agora_iso(agora)
    with conexao:
        pendente = conexao.execute(
            """
            SELECT id, destino, status
            FROM notificacoes_operacionais
            WHERE id=? AND status IN ('enviando', 'tentando')
            """,
            (int(notificacao_id),),
        ).fetchone()
        if pendente is None:
            return {
                "resolvido": False,
                "motivo": "notificacao_nao_esta_incerta",
                "notificacao_id": int(notificacao_id),
            }
        if resultado == "entregue":
            confirmacao = json.dumps(
                {
                    "message_id": telegram_message_id,
                    "ok": True,
                    "origem": "reconciliacao_manual",
                    "provedor": "telegram",
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            conexao.execute(
                """
                UPDATE notificacoes_operacionais
                SET status='entregue', entregue_em=?, erro=NULL,
                    provedor='telegram', provedor_mensagem_id=?,
                    confirmacao_json=?
                WHERE id=?
                """,
                (
                    instante, str(telegram_message_id), confirmacao,
                    int(notificacao_id),
                ),
            )
            status_final = "entregue"
        else:
            conexao.execute(
                """
                UPDATE notificacoes_operacionais
                SET status='erro', tentado_em=?, entregue_em=NULL,
                    erro='reconciliacao_manual_confirmou_nao_envio'
                WHERE id=?
                """,
                (instante, int(notificacao_id)),
            )
            status_final = "erro"
    return {
        "resolvido": True,
        "notificacao_id": int(notificacao_id),
        "destino": pendente["destino"],
        "resultado": resultado,
        "status_final": status_final,
        "telegram_message_id": (
            telegram_message_id if resultado == "entregue" else None
        ),
    }


def _conectar(caminho, somente_leitura=False):
    if somente_leitura:
        uri = Path(caminho).resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
    else:
        conexao = sqlite3.connect(caminho, timeout=10)
    conexao.row_factory = sqlite3.Row
    return conexao


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Lista ou reconcilia uma notificação operacional incerta sem "
            "enviar nova mensagem."
        )
    )
    parser.add_argument(
        "--banco", default=str(Path(__file__).parent / "monitor_packball.db")
    )
    parser.add_argument("--notificacao-id", type=int)
    parser.add_argument("--resultado", choices=RESULTADOS_RESOLUCAO)
    parser.add_argument("--telegram-message-id", type=int)
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Obrigatório para gravar a reconciliação manual.",
    )
    argumentos = parser.parse_args()
    if argumentos.notificacao_id is None and argumentos.resultado is None:
        conexao = _conectar(argumentos.banco, somente_leitura=True)
        try:
            dados = listar_notificacoes_incertas(conexao)
        finally:
            conexao.close()
        print(json.dumps(
            {"notificacoes_operacionais_incertas": dados},
            ensure_ascii=False,
            indent=2,
        ))
        return
    if argumentos.notificacao_id is None or argumentos.resultado is None:
        parser.error("--notificacao-id e --resultado devem ser usados juntos.")
    if not argumentos.confirmar:
        parser.error("Use --confirmar depois de conferir o Telegram.")
    conexao = _conectar(argumentos.banco)
    try:
        resultado = resolver_notificacao_operacional(
            conexao,
            argumentos.notificacao_id,
            argumentos.resultado,
            telegram_message_id=argumentos.telegram_message_id,
        )
    finally:
        conexao.close()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
