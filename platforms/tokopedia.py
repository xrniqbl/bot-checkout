from platforms.base import BasePlatform
from utils.logger import get_logger
log = get_logger()

class TokopediaPlatform(BasePlatform):
    name = "tokopedia"
    HOME = "https://www.tokopedia.com/"

    async def is_logged_in(self):
        await self.page.goto(self.HOME, wait_until="domcontentloaded")
        return await self.page.locator("[data-testid='btnHeaderUserName'], a[href*='/user']").count() > 0

    async def open_product(self, url):
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(1200)

    async def is_in_stock(self):
        btn = self.page.locator("button:has-text('Beli Langsung'), button:has-text('+ Keranjang')")
        try:
            await btn.first.wait_for(timeout=4000)
            return await btn.first.is_enabled()
        except Exception:
            return False

    async def select_variant(self, variant):
        if variant:
            for v in variant.split(","):
                try:
                    await self.page.get_by_role("button", name=v.strip()).click()
                except Exception:
                    pass

    async def add_to_cart(self, qty):
        if qty and qty > 1:
            try:
                await self.page.locator("[data-testid='quantityEditorInput']").fill(str(qty))
            except Exception:
                pass
        await self.page.locator("button:has-text('+ Keranjang')").first.click()
        await self.page.wait_for_timeout(800)

    async def goto_checkout(self):
        await self.page.goto("https://www.tokopedia.com/cart", wait_until="domcontentloaded")
        await self.page.locator("button:has-text('Beli')").first.click()
        await self.page.wait_for_load_state("domcontentloaded")

    async def create_order(self, pay_method, va_bank):
        try:
            await self.page.get_by_text("Pilih Pembayaran").first.click()
            if pay_method == "va":
                await self.page.get_by_text("Virtual Account").first.click()
                if va_bank:
                    await self.page.get_by_text(va_bank, exact=False).first.click()
        except Exception as e:
            log.warning(f"pilih bayar gagal: {e}")
        try:
            await self.page.get_by_role("button", name="Bayar").first.click()
            await self.page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass
        return await self.page.inner_text("body")
