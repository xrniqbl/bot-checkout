import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = [int(x) for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()]
TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "50"))
DEFAULT_PROXY = os.getenv("DEFAULT_PROXY", "") or None
# Pakai profil Chrome ASLI (opsional). Jika diisi, bot pakai folder ini sbg profil
# -> browser "matang" + bisa pakai sesi login Shopee yg sudah ada (lolos anti-bot).
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", "") or None
# MODE ADU-TEKNIS: tempel ke Chrome asli yg kamu jalankan sendiri (paling sulit dideteksi).
# Jalankan Chrome dgn: chrome.exe --remote-debugging-port=9222 --user-data-dir="C:/chrome-bot"
# lalu set CHROME_CDP_URL=http://localhost:9222
CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "") or None
SESSION_ENCRYPTION_KEY = os.getenv("SESSION_ENCRYPTION_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database/bot.db")

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")