from abc import ABC, abstractmethod
from core.browser import BrowserEngine
from core.payment import detect_payment_methods
from database.models import resolve_payment
from utils.logger import get_logger

log = get_logger()

class BasePlatform(ABC):
    name = "base"
    HOME = "https://example.com"

    def __init__(self, account: str, proxy: str | None = None, notifier=None):
        self.account = account
        self.engine = BrowserEngine(account, proxy)
        self.page = None
        self.notifier = notifier

    async def notify(self, text, screenshot=False):
        shot = await self.page.screenshot() if (screenshot and self.page) else None
        if self.notifier:
            await self.notifier(text, shot)
        log.info(f"[{self.name}/{self.account}] {text}")

    async def open(self, headless=None):
        self.page = await self.engine.start(headless=headless)

    async def close(self):
        await self.engine.close()   # profil tersimpan -> tetap login

    # ---- LOGIN: dibuka non-headless agar user login sekali, lalu STAY ----
    LOGIN_URL = None  # diisi tiap platform

    async def interactive_login(self, timeout_sec=240):
        await self.open(headless=False)
        target = self.LOGIN_URL or self.HOME
        try:
            await self.page.goto(target, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            log.warning(f"goto login: {e}")
        # anti-blank: kalau body kosong, reload sekali
        try:
            import asyncio
            await asyncio.sleep(2)
            body = await self.page.inner_text("body")
            if len(body.strip()) < 5:
                log.warning("halaman blank -> reload")
                await self.page.reload(wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        await self.notify(f"Browser {self.name} dibuka di halaman login.\n"
                          f"Silakan LOGIN manual sekarang (punya {timeout_sec}s).\n"
                          f"Setelah berhasil login, profil tersimpan & tetap aktif.")
        # cek status login TANPA reload halaman (biar tidak loading terus)
        import asyncio
        for _ in range(timeout_sec // 2):
            try:
                if await self.logged_in_now():
                    await self.notify("✅ Login terdeteksi & tersimpan. Akun akan STAY login.")
                    await self.engine.persist() if hasattr(self.engine, "persist") else None
                    await self.close()
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
        await self.notify("⏳ Timeout login (belum terdeteksi). Coba /start > Login lagi.")
        await self.close()
        return False

    async def logged_in_now(self):
        """Cek login pada halaman yg SEDANG terbuka (tanpa navigasi)."""
        from core.dom import exists
        inds = getattr(self, "LOGIN_INDICATORS", [])
        if not inds:
            return False
        return await exists(self.page, inds, timeout=800)

    def logout(self):
        self.engine.wipe_profile()

    COOKIE_DOMAIN = None  # diisi tiap platform (mis '.shopee.co.id')

    async def login_with_cookies(self, cookie_text):
        """Login langsung via cookie/session (lewati halaman login & anti-bot)."""
        from core.cookies import parse_cookies
        if not self.COOKIE_DOMAIN:
            return False, 0, "Platform ini tidak mendukung login cookie."
        cookies = parse_cookies(cookie_text, self.COOKIE_DOMAIN)
        if not cookies:
            return False, 0, "Cookie tidak terbaca. Pastikan format benar."
        await self.open(headless=True)
        try:
            await self.engine.context.add_cookies(cookies)
            await self.page.goto(self.HOME, wait_until="domcontentloaded", timeout=45000)
            import asyncio; await asyncio.sleep(2)
            ok = await self.logged_in_now()
            return ok, len(cookies), ("Login cookie berhasil!" if ok else
                   "Cookie tersimpan tapi belum terdeteksi login (mungkin cookie kurang/expired).")
        finally:
            await self.close()  # profil tersimpan -> cookie ikut tersimpan

    @abstractmethod
    async def is_logged_in(self): ...

    @abstractmethod
    async def open_product(self, url): ...

    @abstractmethod
    async def select_variant(self, variant): ...

    @abstractmethod
    async def add_to_cart(self, qty): ...

    @abstractmethod
    async def goto_checkout(self): ...

    @abstractmethod
    async def is_in_stock(self): ...

    async def detect_payments(self):
        return await detect_payment_methods(self.page)

    @abstractmethod
    async def create_order(self, pay_method, va_bank): ...

    async def ensure_login(self):
        await self.page.goto(self.HOME, wait_until="domcontentloaded")
        if not await self.is_logged_in():
            raise RuntimeError("Belum login. Jalankan /login dulu.")
        return True

    # ---- eksekusi checkout (dipakai instant & saat restock terdeteksi) ----
    async def do_checkout(self, task):
        method, bank = resolve_payment(task)
        if task.variant:
            await self.select_variant(task.variant)
        qty = getattr(task, "qty", 1) or 1
        # JALUR CEPAT: 1 produk -> 'Beli Sekarang' langsung ke checkout (lewati keranjang).
        used_buy_now = False
        if qty <= 1 and hasattr(self, "buy_now"):
            try:
                used_buy_now = await self.buy_now(qty)
            except Exception as e:
                await self.notify(f"Beli Sekarang gagal ({e}), fallback ke keranjang.")
                used_buy_now = False
        if not used_buy_now:
            await self.add_to_cart(qty)
            await self.goto_checkout()
        methods = await self.detect_payments()
        await self.notify(f"Metode bayar tersedia: {methods} | dipilih: {method}/{bank}")
        result = await self.create_order(method, bank)
        await self.notify(f"PESANAN DIBUAT ({method}/{bank}). Detail:\n{result}\nBayar manual ya.", screenshot=True)
        return "success"

    async def run(self, task):
        """Instant mode: login -> produk -> cek stok -> checkout."""
        await self.open()
        try:
            await self.ensure_login()
            await self.open_product(task.product_url)
            if not await self.is_in_stock():
                await self.notify("Produk belum tersedia.")
                return "out_of_stock"
            return await self.do_checkout(task)
        except Exception as e:
            await self.notify(f"GAGAL: {e}", screenshot=True)
            return "failed"
        finally:
            await self.close()

    async def run_restock(self, task):
        """Restock mode: monitor cepat+akurat -> auto checkout saat terkonfirmasi."""
        from core.restock import RestockMonitor
        await self.open()
        try:
            await self.ensure_login()
            async def _on_restock():
                await self.do_checkout(task)
            mon = RestockMonitor(self, interval=max(task.poll_interval, 1),
                                 confirm_hits=2, on_restock=_on_restock)
            await self.notify(f"Monitor restock aktif (tiap {task.poll_interval}s, verifikasi 2x).")
            await mon.start(task.product_url)
            return "success"
        except Exception as e:
            await self.notify(f"GAGAL monitor: {e}", screenshot=True)
            return "failed"
        finally:
            await self.close()

    async def run_flashsale(self, task, target_epoch):
        """Flash-sale terjadwal presisi NTP. target_epoch = waktu sale (epoch detik)."""
        from core.flashsale import FlashSaleRunner
        runner = FlashSaleRunner(self, task, notifier=self.notifier)
        return await runner.run(target_epoch)