from platforms.generic import GenericPlatform
from platforms.shopee import ShopeePlatform
from platforms.tokopedia import TokopediaPlatform

def detect_platform(url: str) -> str:
    u = url.lower()
    if "shopee." in u:
        return "shopee"
    if "tokopedia." in u:
        return "tokopedia"
    return "generic"

def get_platform(name, account, proxy=None, notifier=None):
    return {
        "shopee": ShopeePlatform,
        "tokopedia": TokopediaPlatform,
        "generic": GenericPlatform,
    }[name](account, proxy, notifier)
