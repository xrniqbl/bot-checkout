from loguru import logger
import os
from config.settings import LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)
logger.add(os.path.join(LOGS_DIR, "bot_{time:YYYY-MM-DD}.log"), rotation="1 day", retention="14 days", level="INFO")

def get_logger():
    return logger
