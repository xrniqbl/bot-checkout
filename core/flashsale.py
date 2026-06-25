import asyncio, time
from datetime import datetime
from utils.timesync import timesync
from utils.logger import get_logger

log = get_logger()

class FlashSaleRunner:
    """Eksekusi pembelian flash-sale dengan presisi NTP.

    Tahapan:
    1) SYNC waktu ke NTP (offset milidetik).
    2) PRE-WARM (T-90s): login dipastikan, buka produk, pilih varian,
       parkir di halaman -> semua siap, tinggal klik.
    3) HOT-RELOAD menjelang sale (T-5s..T0): refresh ringan supaya stok
       termutakhir tepat saat sale buka.
    4) FIRE tepat target: busy-wait presisi (sleep kasar -> spin halus).
    5) RETRY agresif beberapa kali bila tombol belum aktif sepersekian detik.
    """

    def __init__(self, platform, task, notifier=None,
                 prewarm_sec=90, hot_reload_sec=5, fire_retries=8, retry_gap=0.25):
        self.p = platform
        self.task = task
        self.notify = notifier or (lambda *a, **k: None)
        self.prewarm_sec = prewarm_sec
        self.hot_reload_sec = hot_reload_sec
        self.fire_retries = fire_retries
        self.retry_gap = retry_gap

    async def _say(self, text, shot=False):
        if asyncio.iscoroutinefunction(self.p.notify):
            await self.p.notify(text, screenshot=shot)
        else:
            log.info(text)

    async def _precise_wait(self, target_epoch):
        """Tunggu sampai target. Sleep kasar dulu, lalu spin halus < 50ms."""
        while True:
            remaining = timesync.seconds_until(target_epoch)
            if remaining <= 0:
                return
            if remaining > 0.05:
                await asyncio.sleep(min(remaining - 0.03, 0.5))
            else:
                # spin presisi terakhir
                while timesync.seconds_until(target_epoch) > 0:
                    pass
                return

    async def run(self, target_epoch):
        # 1) sync waktu
        timesync.sync()
        await self.p.open()
        try:
            # pastikan login
            await self.p.ensure_login()

            # 2) pre-warm: tunggu sampai T-prewarm, lalu siapkan halaman
            await self._precise_wait(target_epoch - self.prewarm_sec)
            await self._say(f"Pre-warm: buka produk & siapkan varian (T-{self.prewarm_sec}s).")
            await self.p.open_product(self.task.product_url)
            if self.task.variant:
                try:
                    await self.p.select_variant(self.task.variant)
                except Exception as e:
                    log.warning(f"prewarm variant: {e}")

            # 3) hot-reload menjelang sale
            await self._precise_wait(target_epoch - self.hot_reload_sec)
            await self._say(f"Hot-reload (T-{self.hot_reload_sec}s). Siaga menembak...")
            try:
                await self.p.page.reload(wait_until="domcontentloaded", timeout=8000)
                if self.task.variant:
                    await self.p.select_variant(self.task.variant)
            except Exception:
                pass

            # 4) FIRE tepat waktu
            await self._precise_wait(target_epoch)
            t0 = timesync.now()
            await self._say(f"FIRE! {datetime.fromtimestamp(t0).strftime('%H:%M:%S.%f')[:-3]}")

            # 5) retry agresif sampai add-to-cart sukses
            for i in range(self.fire_retries):
                try:
                    if await self.p.is_in_stock():
                        await self.p.do_checkout(self.task)
                        await self._say(f"Checkout flash-sale OK (attempt {i+1}).")
                        return "success"
                except Exception as e:
                    log.warning(f"fire attempt {i+1}: {e}")
                await asyncio.sleep(self.retry_gap)
                try:
                    await self.p.page.reload(wait_until="domcontentloaded", timeout=6000)
                    if self.task.variant:
                        await self.p.select_variant(self.task.variant)
                except Exception:
                    pass
            await self._say("Flash-sale: gagal dapat (kehabisan/terlalu cepat habis).", shot=True)
            return "missed"
        except Exception as e:
            await self._say(f"GAGAL flash-sale: {e}", shot=True)
            return "failed"
        finally:
            await self.p.close()
