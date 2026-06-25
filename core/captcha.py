from config.settings import TWOCAPTCHA_API_KEY
from utils.logger import get_logger

log = get_logger()

async def solve_recaptcha(site_key: str, url: str):
    """Solusi reCAPTCHA via 2Captcha. Return token atau None.
    Fallback: kembalikan None -> caller minta user solve manual via Telegram."""
    if not TWOCAPTCHA_API_KEY:
        log.warning("2Captcha key kosong -> butuh solve manual")
        return None
    try:
        from twocaptcha import TwoCaptcha
        solver = TwoCaptcha(TWOCAPTCHA_API_KEY)
        res = solver.recaptcha(sitekey=site_key, url=url)
        return res.get("code")
    except Exception as e:
        log.error(f"2Captcha gagal: {e}")
        return None
