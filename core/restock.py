import asyncio
from utils.logger import get_logger

log = get_logger()

class RestockMonitor:
    """Deteksi restock CEPAT & AKURAT.

    Strategi anti-error:
    1) Dua sumber bukti: (a) sinyal dari platform.is_in_stock() [DOM/tombol],
       (b) sinyal jaringan/teks halaman. Restock dianggap valid hanya jika
       lolos KONFIRMASI BERTURUT 'confirm_hits' kali -> hilangkan kedipan/false positive.
    2) Reload ringan (DOM only) + interval kecil utk kecepatan.
    3) Backoff saat error jaringan supaya tidak spam/diblok.
    """

    def __init__(self, platform, interval=3.0, confirm_hits=2, on_restock=None):
        self.platform = platform
        self.interval = interval
        self.confirm_hits = confirm_hits
        self.on_restock = on_restock
        self._running = False
        self._hits = 0

    async def _check_once(self):
        # refresh cepat: DOM only
        try:
            await self.platform.page.reload(wait_until="domcontentloaded", timeout=8000)
        except Exception as e:
            log.warning(f"reload error: {e}")
            return False
        return await self.platform.is_in_stock()

    async def start(self, product_url):
        self._running = True
        await self.platform.open_product(product_url)
        backoff = self.interval
        log.info("RestockMonitor mulai")
        while self._running:
            try:
                in_stock = await self._check_once()
                if in_stock:
                    self._hits += 1
                    log.info(f"sinyal restock {self._hits}/{self.confirm_hits}")
                    if self._hits >= self.confirm_hits:
                        log.info("RESTOCK TERKONFIRMASI -> eksekusi")
                        if self.on_restock:
                            await self.on_restock()
                        self._running = False
                        return True
                    await asyncio.sleep(0.4)   # konfirmasi cepat berturut
                    continue
                else:
                    self._hits = 0
                backoff = self.interval
            except Exception as e:
                log.error(f"monitor error: {e}; backoff {backoff}s")
                backoff = min(backoff * 1.5, 30)
            await asyncio.sleep(backoff)
        return False

    def stop(self):
        self._running = False
