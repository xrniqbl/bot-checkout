from telegram_bot.bot import build_app
from utils.logger import get_logger

log = get_logger()

if __name__ == "__main__":
    app = build_app()
    log.info("Bot started. Tekan Ctrl+C untuk berhenti.")
    app.run_polling()
