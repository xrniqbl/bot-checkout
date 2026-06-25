from platforms.base import BasePlatform

class GenericPlatform(BasePlatform):
    name = "generic"
    HOME = "https://example.com"

    async def is_logged_in(self):
        # banyak toko generic tak wajib login; anggap selalu true
        return True

    async def open_product(self, url):
        await self.page.goto(url, wait_until="domcontentloaded")

    async def is_in_stock(self):
        btn = self.page.locator("button:has-text('Masukkan Keranjang'), button:has-text('Add to Cart'), button:has-text('Tambah ke Keranjang')")
        try:
            await btn.first.wait_for(timeout=4000)
            return await btn.first.is_enabled()
        except Exception:
            return False

    async def select_variant(self, variant):
        if variant:
            await self.page.get_by_text(variant, exact=False).first.click()

    async def add_to_cart(self, qty):
        if qty and qty > 1:
            try:
                await self.page.locator("input[name='quantity'], input[type='number']").first.fill(str(qty))
            except Exception:
                pass
        await self.page.locator("button:has-text('Masukkan Keranjang'), button:has-text('Add to Cart'), button:has-text('Tambah ke Keranjang')").first.click()

    async def goto_checkout(self):
        await self.page.locator("button:has-text('Beli Sekarang'), button:has-text('Checkout'), a:has-text('Checkout'), button:has-text('Buy Now')").first.click()
        await self.page.wait_for_load_state("domcontentloaded")

    async def create_order(self, pay_method, va_bank):
        target = va_bank if pay_method == "va" else pay_method
        try:
            await self.page.get_by_text(target, exact=False).first.click()
        except Exception:
            pass
        await self.page.locator("button:has-text('Place Order'), button:has-text('Bayar')").first.click()
        await self.page.wait_for_load_state("domcontentloaded")
        return await self.page.inner_text("body")