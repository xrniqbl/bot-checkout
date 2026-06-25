from platforms.base import BasePlatform
from core.dom import first_visible, click_any, exists, fill_any
from utils.logger import get_logger
log = get_logger()

class TokopediaPlatform(BasePlatform):
    """Tokopedia. Selector pakai data-testid (relatif stabil) + fallback teks.
    Tetap verifikasi saat live karena Tokopedia bisa berubah."""
    name = "tokopedia"
    HOME = "https://www.tokopedia.com/"

    LOGIN_INDICATORS = [
        "[data-testid='btnHeaderUserName']",
        "[data-testid='imgHeaderUserPhoto']",
        "a[href*='/user']",
    ]
    BUY_BUTTONS = [
        "[data-testid='pdpBtnBeliLangsung']",
        "button:has-text('Beli Langsung')",
    ]
    ADD_CART_BUTTONS = [
        "[data-testid='pdpBtnNormalAddToCart']",
        "button:has-text('+ Keranjang')",
        "button:has-text('Tambah ke Keranjang')",
    ]
    QTY_INPUT = [
        "[data-testid='quantityEditorInput']",
        "input[aria-label*='Quantity']",
    ]
    OOS_INDICATORS = [
        "text=Stok habis",
        "text=Produk tidak tersedia",
        "[data-testid='pdpStockEmpty']",
    ]

    async def is_logged_in(self):
        await self.page.goto(self.HOME, wait_until="domcontentloaded")
        return await exists(self.page, self.LOGIN_INDICATORS, timeout=4000)

    async def open_product(self, url):
        await self.page.goto(url, wait_until="domcontentloaded")
        # tunggu salah satu tombol beli muncul (sinyal halaman produk siap)
        await first_visible(self.page, self.BUY_BUTTONS + self.ADD_CART_BUTTONS, timeout=8000)

    async def is_in_stock(self):
        if await exists(self.page, self.OOS_INDICATORS, timeout=1000):
            return False
        loc = await first_visible(self.page, self.ADD_CART_BUTTONS + self.BUY_BUTTONS, timeout=2000)
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
                    f"[data-testid='pdpVariantContainer'] button:has-text('{v}')",
                    f"button[aria-label*='{v}']",
                    f"button:has-text('{v}')",
                    f"text={v}",
                ], timeout=3000, what=f"varian {v}")
            except Exception as e:
                log.warning(f"varian {v} gagal: {e}")

    async def add_to_cart(self, qty):
        if qty and qty > 1:
            await fill_any(self.page, self.QTY_INPUT, qty, what="qty")
        await click_any(self.page, self.ADD_CART_BUTTONS, what="Add to Cart")
        await self.page.wait_for_timeout(800)

    async def goto_checkout(self):
        await self.page.goto("https://www.tokopedia.com/cart", wait_until="domcontentloaded")
        await click_any(self.page, [
            "[data-testid='cartGlobalCheckoutButton']",
            "button:has-text('Beli')",
            "button:has-text('Checkout')",
        ], what="Checkout")
        await self.page.wait_for_load_state("domcontentloaded")

    async def create_order(self, pay_method, va_bank):
        try:
            await click_any(self.page, [
                "[data-testid='btnPilihPembayaran']",
                "button:has-text('Pilih Pembayaran')",
                "text=Pilih Metode Pembayaran",
            ], timeout=5000, what="buka metode bayar")
            if pay_method == "va":
                await click_any(self.page, ["text=Virtual Account", "text=Transfer Bank"],
                                timeout=4000, what="Virtual Account")
                if va_bank:
                    await click_any(self.page, [f"text={va_bank}", f"img[alt*='{va_bank}']"],
                                    timeout=4000, what=f"bank {va_bank}")
        except Exception as e:
            log.warning(f"pilih bayar: {e}")
        # buat pesanan -> STOP di halaman instruksi VA (tidak bayar)
        try:
            await click_any(self.page, [
                "[data-testid='btnBayarSekarang']",
                "button:has-text('Bayar Sekarang')",
                "button:has-text('Bayar')",
                "button:has-text('Buat Pesanan')",
            ], timeout=6000, what="Buat Pesanan")
            await self.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            log.warning(f"buat pesanan: {e}")
        return await self.page.inner_text("body")
