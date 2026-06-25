from platforms.base import BasePlatform
from core.dom import first_visible, click_any, exists, fill_any
from utils.logger import get_logger
log = get_logger()

class ShopeePlatform(BasePlatform):
    """Shopee. Class CSS-nya obfuscated & berubah -> andalkan TEKS & aria.
    WAJIB diverifikasi saat live; Shopee anti-bot ketat (CAPTCHA mungkin muncul)."""
    name = "shopee"
    HOME = "https://shopee.co.id/"
    LOGIN_URL = "https://shopee.co.id/"  # buka homepage, klik tombol login manual (hindari blank /buyer/login)

    LOGIN_INDICATORS = [
        "[class*='navbar__username']",
        "a[href*='/user/account']",
        "div[class*='username']",
    ]
    BUY_NOW = ["button:has-text('Beli Sekarang')", "text=Beli Sekarang"]
    ADD_CART = ["button:has-text('Masukkan Keranjang')", "text=Masukkan Keranjang",
                "button[aria-label*='Keranjang']"]
    OOS = ["text=Stok habis", "text=Produk Tidak Tersedia", "button:has-text('Stok Habis')"]

    async def is_logged_in(self):
        await self.page.goto(self.HOME, wait_until="domcontentloaded")
        return await exists(self.page, self.LOGIN_INDICATORS, timeout=4000)

    async def open_product(self, url):
        await self.page.goto(url, wait_until="domcontentloaded")
        await first_visible(self.page, self.ADD_CART + self.BUY_NOW, timeout=8000)
        await self._maybe_captcha()

    async def _maybe_captcha(self):
        # deteksi CAPTCHA -> minta user solve manual via Telegram (jangan auto-fail)
        if await exists(self.page, ["iframe[src*='captcha']", "text=Verifikasi", "text=puzzle"], timeout=800):
            await self.notify("CAPTCHA Shopee muncul! Selesaikan manual di browser (non-headless).", screenshot=True)
            # beri waktu user solve
            await self.page.wait_for_timeout(30000)

    async def is_in_stock(self):
        if await exists(self.page, self.OOS, timeout=1000):
            return False
        loc = await first_visible(self.page, self.ADD_CART + self.BUY_NOW, timeout=2000)
        if not loc:
            return False
        try:
            return await loc.is_enabled()
        except Exception:
            return True

    async def select_variant(self, variant):
        if not variant:
            return
        for v in variant.split(","):
            v = v.strip()
            try:
                await click_any(self.page, [
                    f"button:has-text('{v}')",
                    f"button[aria-label*='{v}']",
                    f"text={v}",
                ], timeout=3000, what=f"varian {v}")
            except Exception as e:
                log.warning(f"varian {v} gagal: {e}")

    async def add_to_cart(self, qty):
        if qty and qty > 1:
            # tombol + qty (Shopee pakai stepper)
            for _ in range(qty - 1):
                try:
                    await click_any(self.page, ["button[aria-label='Increase Value']",
                                                "div[class*='product-quantity'] button:last-child"],
                                    timeout=1500, what="qty +")
                except Exception:
                    break
        await click_any(self.page, self.ADD_CART, what="Masukkan Keranjang")
        await self.page.wait_for_timeout(900)
        await self._maybe_captcha()

    async def goto_checkout(self):
        await self.page.goto("https://shopee.co.id/cart", wait_until="domcontentloaded")
        # centang semua item dulu jika ada checkbox 'pilih semua'
        try:
            await click_any(self.page, ["text=Pilih Semua", "input[type='checkbox']"],
                            timeout=2500, what="pilih semua")
        except Exception:
            pass
        await click_any(self.page, ["button:has-text('Checkout')", "text=Checkout"],
                        what="Checkout")
        await self.page.wait_for_load_state("domcontentloaded")

    async def create_order(self, pay_method, va_bank):
        try:
            await click_any(self.page, [
                "text=Metode Pembayaran", "button:has-text('Metode Pembayaran')",
                "text=Pilih Metode Pembayaran",
            ], timeout=5000, what="buka metode bayar")
            if pay_method == "va":
                await click_any(self.page, ["text=Virtual Account", "text=Transfer Bank"],
                                timeout=4000, what="Virtual Account")
                if va_bank:
                    await click_any(self.page, [f"text={va_bank}", f"img[alt*='{va_bank}']"],
                                    timeout=4000, what=f"bank {va_bank}")
            # konfirmasi pilihan metode
            await click_any(self.page, ["button:has-text('Konfirmasi')", "button:has-text('OK')"],
                            timeout=3000, what="konfirmasi metode")
        except Exception as e:
            log.warning(f"pilih bayar: {e}")
        # Buat Pesanan -> berhenti di halaman instruksi VA (TIDAK bayar)
        try:
            await click_any(self.page, [
                "button:has-text('Buat Pesanan')", "button:has-text('Bayar Sekarang')",
                "text=Buat Pesanan",
            ], timeout=6000, what="Buat Pesanan")
            await self.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            log.warning(f"buat pesanan: {e}")
        return await self.page.inner_text("body")