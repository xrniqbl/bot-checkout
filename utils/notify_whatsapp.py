import os
import httpx
from utils.logger import get_logger

log = get_logger()

# CallMeBot: notifikasi WhatsApp GRATIS ke nomor sendiri.
# Aktivasi 1x: simpan kontak +34 644 51 95 23, kirim "I allow callmebot
# to send me messages" -> kamu dapat APIKEY. Isi .env:
#   WHATSAPP_PHONE=628xxxxxxxxxx   (format internasional tanpa +)
#   CALLMEBOT_APIKEY=123456
WA_PHONE = os.getenv("WHATSAPP_PHONE", "").strip()
WA_KEY = os.getenv("CALLMEBOT_APIKEY", "").strip()


def whatsapp_enabled() -> bool:
    return bool(WA_PHONE and WA_KEY)


async def send_whatsapp(text: str) -> bool:
    """Kirim pesan WhatsApp via CallMeBot (gratis). Return True kalau sukses."""
    if not whatsapp_enabled():
        return False
    url = "https://api.callmebot.com/whatsapp.php"
    params = {"phone": WA_PHONE, "text": text, "apikey": WA_KEY}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params=params)
            ok = r.status_code == 200
            if not ok:
                log.warning(f"WhatsApp gagal: {r.status_code} {r.text[:120]}")
            return ok
    except Exception as e:
        log.warning(f"WhatsApp error: {e}")
        return False
