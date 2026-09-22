import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


ESTADOS_PENDENTES = ("enviando", "tentando", "incerto")
ESTADOS_FINAIS = (
    "entregue", "erro", "recuperado", "cancelado", "expirado"
)
RESULTADOS_RESOLUCAO = ("entregue", "nao_enviado")


def _agora_iso(agora=None):
    return (agora or datetime.now()).replace(microsecond=0).isoformat()


def _canal_origem_edicao(canal):
    canal = str(canal or "")
    for marcador in (":resultado", ":cancelamento", ":correcao:"):
        if marcador in canal:
            return canal.split(marcador, 1)[0], marcador.strip(":")
    return None, None


def _mensagem_origem_edicao(conexao, sinal_id, canal):
    canal_origem, tipo = _canal_origem_edicao(canal)
    if canal_origem is None:
        return None, None
    linha = conexao.execute(
        """
        SELECT provedor_mensagem_id
        FROM entregas_alertas
        WHERE sinal_id=? AND canal=? AND status='entregue'
          AND provedor='telegram' AND provedor_mensagem_id IS NOT NULL
        ORDER BY entregue_em DESC, id DESC
        LIMIT 1
        """,
        (int(sinal_id), canal_origem),
    ).fetchone()
    if linha is None:
        return None, tipo
    try:
        mensagem_id = int(linha["provedor_mensagem_id"])
    except (TypeError, ValueError):
        return None, tipo
    return (mensagem_id if mensagem_id > 0 else None), tipo


def listar_envios_incertos(conexao, agora=None, tolerancia_minutos=2):
    limite = (
        (agora or datetime.now()) - timedelta(minutes=tolerancia_minutos)
    ).replace(microsecond=0).isoformat()
    linhas = conexao.execute(
        """
        SELECT pendente.id AS entrega_id, pendente.sinal_id,
               pendente.canal, pendente.status, pendente.tentado_em,
               pendente.tentativas, s.mercado, s.linha, s.odd,
               s.regra_versao, p.mandante, p.visitante,
               sn.status AS minuto, sn.placar
        FROM entregas_alertas pendente
        JOIN sinais s ON s.id=pendente.sinal_id
        JOIN partidas p ON p.id=s.partida_id
        JOIN snapshots sn ON sn.id=s.snapshot_id
        WHERE pendente.status IN ('enviando', 'tentando', 'incerto')
          AND (
              pendente.status='incerto'
              OR datetime(pendente.tentado_em) <= datetime(?)
          )
          AND NOT EXISTS (
              SELECT 1 FROM entregas_alertas final
              WHERE final.sinal_id=pendente.sinal_id
                AND final.canal=pendente.canal
                AND final.status IN (
                    'entregue', 'erro', 'recuperado', 'cancelado', 'expirado'
                )
                AND datetime(final.tentado_em)
                    >= datetime(pendente.tentado_em)
          )
          AND NOT EXISTS (
              SELECT 1 FROM entregas_alertas posterior
              WHERE posterior.sinal_id=pendente.sinal_id
                AND posterior.canal=pendente.canal
                AND posterior.status IN ('enviando', 'tentando', 'incerto')
                AND (
                    datetime(posterior.tentado_em)
                        > datetime(pendente.tentado_em)
                    OR (
                        datetime(posterior.tentado_em)
                            = datetime(pendente.tentado_em)
                        AND posterior.id > pendente.id
                    )
                )
          )
        ORDER BY pendente.tentado_em, pendente.id
        """,
        (limite,),
    ).fetchall()
    itens = []
    for linha in linhas:
        item = dict(linha)
        mensagem_id, tipo = _mensagem_origem_edicao(
            conexao, item["sinal_id"], item["canal"]
        )
        item["tipo_operacao"] = tipo or "envio_novo"
        item["mensagem_id_origem"] = mensagem_id
        item["reconciliacao_edicao_possivel"] = mensagem_id is not None
        itens.append(item)
    return itens


def resolver_envio_incerto(
    conexao, entrega_id, resultado, agora=None, telegram_message_id=None,
):
    if resultado not in RESULTADOS_RESOLUCAO:
        raise ValueError("Resultado de reconciliação inválido.")
    instante = _agora_iso(agora)
    with conexao:
        pendente = conexao.execute(
            """
            SELECT id, sinal_id, canal, status, tentativas, tentado_em
            FROM entregas_alertas
            WHERE id=? AND status IN ('enviando', 'tentando', 'incerto')
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas final
                  WHERE final.sinal_id=entregas_alertas.sinal_id
                    AND final.canal=entregas_alertas.canal
                    AND final.status IN (
                        'entregue', 'erro', 'recuperado',
                        'cancelado', 'expirado'
                    )
                    AND datetime(final.tentado_em)
                        >= datetime(entregas_alertas.tentado_em)
              )
              AND NOT EXISTS (
                  SELECT 1 FROM entregas_alertas posterior
                  WHERE posterior.sinal_id=entregas_alertas.sinal_id
                    AND posterior.canal=entregas_alertas.canal
                    AND posterior.status IN (
                        'enviando', 'tentando', 'incerto'
                    )
                    AND (
                        datetime(posterior.tentado_em)
                            > datetime(entregas_alertas.tentado_em)
                        OR (
                            datetime(posterior.tentado_em)
                                = datetime(entregas_alertas.tentado_em)
                            AND posterior.id > entregas_alertas.id
                        )
                    )
              )
            """,
            (int(entrega_id),),
        ).fetchone()
        if pendente is None:
            return {
                "resolvido": False,
                "motivo": "entrega_nao_esta_incerta",
                "entrega_id": int(entrega_id),
            }

        edicao = False
        if resultado == "entregue":
            if isinstance(telegram_message_id, bool):
                telegram_message_id = None
            try:
                telegram_message_id = int(telegram_message_id)
            except (TypeError, ValueError):
                telegram_message_id = 0
            mensagem_origem_id, _ = _mensagem_origem_edicao(
                conexao, pendente["sinal_id"], pendente["canal"]
            )
            if mensagem_origem_id is not None:
                if (
                    telegram_message_id > 0
                    and telegram_message_id != mensagem_origem_id
                ):
                    raise ValueError(
                        "telegram_message_id diverge da mensagem original "
                        "comprovada no SQLite."
                    )
                telegram_message_id = mensagem_origem_id
                edicao = True
            if not telegram_message_id or telegram_message_id <= 0:
                raise ValueError(
                    "telegram_message_id positivo é obrigatório para "
                    "confirmar um envio novo; edições exigem uma mensagem "
                    "original comprovada no SQLite."
                )

        status_auditoria = (
            "confirmado_manual"
            if resultado == "entregue" else "nao_enviado_manual"
        )
        conexao.execute(
            "UPDATE entregas_alertas SET status=? WHERE id=?",
            (status_auditoria, int(entrega_id)),
        )
        status_final = "entregue" if resultado == "entregue" else "erro"
        erro = (
            None if resultado == "entregue"
            else "reconciliacao_manual_confirmou_nao_envio"
        )
        entregue_em = instante if resultado == "entregue" else None
        destino = str(pendente["canal"]).split(":", 1)[0]
        confirmacao_json = None
        provedor = None
        provedor_destino_id = None
        provedor_mensagem_id = None
        if resultado == "entregue":
            provedor = "telegram"
            provedor_destino_id = destino
            provedor_mensagem_id = (
                None if edicao else str(telegram_message_id)
            )
            confirmacao = {
                "ok": True,
                "origem": "reconciliacao_manual",
                "provedor": "telegram",
            }
            if edicao:
                confirmacao.update({
                    "edicao": True,
                    "message_id_origem": telegram_message_id,
                })
            else:
                confirmacao["message_id"] = telegram_message_id
            confirmacao_json = json.dumps(
                confirmacao,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        canal_pendente = str(pendente["canal"])
        revisao_id = None
        if ":correcao:" in canal_pendente:
            try:
                revisao_id = int(canal_pendente.rsplit(":correcao:", 1)[1])
            except (TypeError, ValueError):
                revisao_id = None
        if revisao_id is not None:
            revisao = conexao.execute(
                """
                UPDATE revisoes_resultados
                SET notificacao_status=?, notificacao_erro=?,
                    notificacao_provedor=COALESCE(
                        notificacao_provedor, ?
                    ),
                    notificacao_destino_id=COALESCE(
                        notificacao_destino_id, ?
                    ),
                    notificacao_mensagem_id=COALESCE(
                        notificacao_mensagem_id, ?
                    ),
                    notificacao_confirmacao_json=COALESCE(
                        notificacao_confirmacao_json, ?
                    )
                WHERE id=? AND sinal_id=?
                  AND notificacao_status IN ('pendente', 'incerto')
                """,
                (
                    status_final, erro, provedor, provedor_destino_id,
                    provedor_mensagem_id, confirmacao_json, revisao_id,
                    pendente["sinal_id"],
                ),
            )
            if revisao.rowcount != 1:
                raise RuntimeError(
                    "A revisao vinculada ao claim nao esta reconciliavel."
                )
        if revisao_id is None or resultado != "entregue":
            conexao.execute(
                """
                INSERT INTO entregas_alertas (
                    sinal_id, canal, tentado_em, entregue_em,
                    status, erro, tentativas, provedor,
                    provedor_destino_id, provedor_mensagem_id,
                    confirmacao_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pendente["sinal_id"], pendente["canal"], instante,
                    entregue_em, status_final, erro,
                    max(int(pendente["tentativas"] or 1), 1),
                    provedor, provedor_destino_id, provedor_mensagem_id,
                    confirmacao_json,
                ),
            )
    return {
        "resolvido": True,
        "entrega_id": int(entrega_id),
        "sinal_id": int(pendente["sinal_id"]),
        "canal": pendente["canal"],
        "resultado": resultado,
        "status_auditoria": status_auditoria,
        "status_final": status_final,
        "telegram_message_id": (
            telegram_message_id if resultado == "entregue" else None
        ),
        "edicao": bool(edicao if resultado == "entregue" else False),
    }


def _conectar(caminho, somente_leitura=False):
    if somente_leitura:
        uri = Path(caminho).resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
    else:
        conexao = sqlite3.connect(caminho, timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Lista ou reconcilia uma entrega Telegram incerta sem enviar "
            "nova mensagem."
        )
    )
    parser.add_argument(
        "--banco", default=str(Path(__file__).parent / "monitor_packball.db")
    )
    parser.add_argument("--entrega-id", type=int)
    parser.add_argument("--resultado", choices=RESULTADOS_RESOLUCAO)
    parser.add_argument(
        "--telegram-message-id",
        type=int,
        help=(
            "ID da mensagem conferida no Telegram; obrigatório para envio "
            "novo. Em edições, o ID original comprovado é reutilizado."
        ),
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Obrigatório para gravar a reconciliação manual.",
    )
    argumentos = parser.parse_args()
    if argumentos.entrega_id is None and argumentos.resultado is None:
        conexao = _conectar(argumentos.banco, somente_leitura=True)
        try:
            dados = listar_envios_incertos(conexao)
        finally:
            conexao.close()
        print(json.dumps({"envios_incertos": dados}, ensure_ascii=False, indent=2))
        return
    if argumentos.entrega_id is None or argumentos.resultado is None:
        parser.error("--entrega-id e --resultado devem ser usados juntos.")
    if not argumentos.confirmar:
        parser.error("Use --confirmar depois de conferir a mensagem no Telegram.")
    conexao = _conectar(argumentos.banco)
    try:
        resultado = resolver_envio_incerto(
            conexao,
            argumentos.entrega_id,
            argumentos.resultado,
            telegram_message_id=argumentos.telegram_message_id,
        )
    finally:
        conexao.close()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
