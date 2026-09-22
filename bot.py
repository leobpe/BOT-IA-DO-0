import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from banco import BancoMonitor
from fila_odds_manual import listar_solicitacoes_odds_manuais


PASTA_PROJETO = Path(__file__).parent
ARQUIVO_ENV = PASTA_PROJETO / ".env"
load_dotenv(ARQUIVO_ENV)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
ARQUIVO_BANCO = PASTA_PROJETO / "monitor_packball.db"


def usuario_e_admin(usuario_id):
    return bool(
        ADMIN_ID
        and usuario_id is not None
        and str(usuario_id) == str(ADMIN_ID)
    )


def formatar_fila_odds_manual(resultado):
    solicitacoes = list(resultado.get("solicitacoes") or [])
    if not solicitacoes:
        return (
            "📋 CONFERÊNCIA MANUAL BET365\n\n"
            "Nenhuma partida depende exclusivamente da odd neste momento.\n\n"
            "A fila considera somente candidatos técnicos recentes e não "
            "representa indicação de aposta."
        )
    linhas = [
        "📋 CONFERÊNCIA MANUAL BET365",
        "",
        "Somente captura de odds — não é sinal de aposta.",
    ]
    for indice, item in enumerate(solicitacoes[:5], start=1):
        linhas.extend([
            "",
            f"{indice}. {item['partida']}",
            (
                f"Período: {item['periodo']} | "
                f"Minuto: {item.get('status_partida') or '-'} | "
                f"Placar: {item.get('placar') or '-'}"
            ),
            f"Nota técnica: {item['pontuacao_tecnica']:.1f}/100",
            f"PackBall: {item['packball_url']}",
            (
                "Na Bet365, abra Escanteios e fotografe a linha asiática "
                "com as odds Over e Under."
            ),
        ])
    if len(solicitacoes) > 5:
        linhas.extend([
            "",
            f"Outras partidas na fila: {len(solicitacoes) - 5}",
        ])
    linhas.extend([
        "",
        (
            f"Validade da fila: {resultado.get('janela_minutos', 6)} "
            "minuto(s)."
        ),
    ])
    return "\n".join(linhas)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = update.effective_message
    if mensagem is None:
        return

    await mensagem.reply_text(
        "🤖 Bem-vindo ao Bot de Sinais!\n\n"
        "Use /sinais para consultar os sinais.\n"
        "Use /oddsmanual para consultar capturas pendentes.\n"
        "Use /ajuda para ver os comandos."
    )


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = update.effective_message
    if mensagem is None:
        return

    await mensagem.reply_text(
        "📌 Comandos disponíveis:\n\n"
        "/start — iniciar o bot\n"
        "/sinais — consultar sinais\n"
        "/oddsmanual — consultar capturas Bet365 pendentes (administrador)\n"
        "/meuid — mostrar seu ID\n"
        "/chatid — mostrar o ID do grupo\n"
        "/ajuda — mostrar esta mensagem"
    )


async def sinais(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = update.effective_message
    if mensagem is None:
        return

    await mensagem.reply_text(
        "📊 SINAIS DO SISTEMA\n\n"
        "Sinais oficiais são enviados automaticamente somente depois da "
        "calibração real. Este comando não cria nem força uma entrada.\n\n"
        "🔞 Apenas para maiores de idade.\n"
        "⚠️ Aposte com responsabilidade. Não há garantia de lucro."
    )


async def meuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = update.effective_message
    usuario = update.effective_user
    if mensagem is None or usuario is None:
        return

    await mensagem.reply_text(f"Seu ID do Telegram é:\n\n{usuario.id}")


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = update.effective_message
    chat = update.effective_chat
    if mensagem is None or chat is None:
        return

    await mensagem.reply_text(f"ID deste grupo:\n{chat.id}")


async def oddsmanual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensagem = update.effective_message
    usuario = update.effective_user
    if mensagem is None or usuario is None:
        return

    if not usuario_e_admin(usuario.id):
        await mensagem.reply_text(
            "⛔ Comando restrito ao administrador."
        )
        return

    banco = BancoMonitor(ARQUIVO_BANCO)
    try:
        resultado = listar_solicitacoes_odds_manuais(
            banco.conexao
        )
    finally:
        banco.fechar()
    await mensagem.reply_text(formatar_fila_odds_manual(resultado))


def main():
    if not TOKEN:
        raise ValueError("Token não encontrado no arquivo .env")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("sinais", sinais))
    app.add_handler(CommandHandler("meuid", meuid))
    app.add_handler(CommandHandler("chatid", chatid))
    app.add_handler(CommandHandler("oddsmanual", oddsmanual))

    print("Bot de comandos iniciado sem abrir navegador PackBall.")
    app.run_polling(allowed_updates=("message",))


if __name__ == "__main__":
    main()
