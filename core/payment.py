from utils.logger import get_logger
log = get_logger()

# Pola umum nama metode pembayaran VA di checkout ID e-commerce
VA_BANKS = ["BCA", "Mandiri", "BNI", "BRI", "Permata", "CIMB", "BSI"]

async def detect_payment_methods(page):
    """Scrape teks halaman checkout, kembalikan daftar metode yang terdeteksi.
    Selector perlu disesuaikan per platform di modul masing-masing."""
    text = (await page.content()).lower()
    found = {"va_banks": [], "ewallet": [], "cod": False, "card": False}
    for b in VA_BANKS:
        if b.lower() in text or f"virtual account {b.lower()}" in text:
            found["va_banks"].append(b)
    for ew in ["shopeepay", "gopay", "ovo", "dana", "linkaja"]:
        if ew in text:
            found["ewallet"].append(ew)
    found["cod"] = "bayar di tempat" in text or "cod" in text
    found["card"] = "kartu kredit" in text or "credit card" in text
    log.info(f"Metode terdeteksi: {found}")
    return found
