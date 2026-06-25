from platforms.generic import GenericPlatform
from platforms.shopee import ShopeePlatform
from platforms.tokopedia import TokopediaPlatform

# domain/penanda tiap platform (termasuk LINK PENDEK share)
SHOPEE_MARKERS = ("shopee.", "shp.ee", "shopee.co.id", "s.shopee")
TOKO_MARKERS = ("tokopedia.", "tokopedia.com", "tokopedia.link", "tk.tokopedia", "toko.pe", "ta.tokopedia")

def detect_platform(url: str) -> str:
    u = (url or "").lower()
    if any(m in u for m in SHOPEE_MARKERS):
        return "shopee"
    if any(m in u for m in TOKO_MARKERS):
        return "tokopedia"
    return "generic"

def get_platform(name, account, proxy=None, notifier=None):
    return {
        "shopee": ShopeePlatform,
        "tokopedia": TokopediaPlatform,
        "generic": GenericPlatform,
    }.get(name, GenericPlatform)(account, proxy, notifier)
