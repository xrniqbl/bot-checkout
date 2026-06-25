import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = [int(x) for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()]
TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "50"))
DEFAULT_PROXY = os.getenv("DEFAULT_PROXY", "") or None
SESSION_ENCRYPTION_KEY = os.getenv("SESSION_ENCRYPTION_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database/bot.db")

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
