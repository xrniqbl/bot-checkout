from platforms.base import BasePlatform
from core.dom import first_visible, click_any, exists, fill_any
from utils.logger import get_logger
log = get_logger()

class ShopeePlatform(BasePlatform):
    """Shopee. Class CSS-nya obfuscated & berubah -> andalkan TEKS & aria.
    WAJIB diverifikasi saat live; Shopee anti-bot ketat (CAPTCHA mungkin muncul)."""
    name = "shopee"
    COOKIE_DOMAIN = ".shopee.co.id"
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

    async def buy_now(self, qty=1):
        """Klik 'Beli Sekarang' di halaman produk -> langsung ke halaman checkout.
        Mengembalikan True jika berhasil sampai halaman checkout."""
        # set kuantitas bila perlu (default 1, jadi biasanya skip)
        await self.page.wait_for_timeout(800)
        clicked = False
        for sel in [
            "button:has-text('Beli Sekarang')",
            "button:has-text('Beli Sekrang')",
            "div[class*='product-briefing'] button:has-text('Beli')",
            "text=Beli Sekarang",
        ]:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click(timeout=4000)
                    clicked = True
                    log.info(f"klik Beli Sekarang via: {sel}")
                    break
            except Exception:
                continue
        if not clicked:
            log.warning("tombol 'Beli Sekarang' tidak ketemu")
            return False
        # setelah klik: bisa muncul popup pilih variasi -> klik konfirmasi 'Beli Sekarang' lagi
        await self.page.wait_for_timeout(1500)
        try:
            confirm = self.page.locator("button:has-text('Beli Sekarang')").last
            if await confirm.count() > 0 and await confirm.is_visible():
                await confirm.click(timeout=3000)
                log.info("konfirmasi variasi -> Beli Sekarang")
        except Exception:
            pass
        # tunggu pindah ke halaman checkout
        try:
            await self.page.wait_for_url("**/checkout**", timeout=12000)
        except Exception:
            # cek manual via konten halaman
            await self.page.wait_for_timeout(2000)
        body = (await self.page.inner_text("body")).lower()
        ok = ("checkout" in self.page.url.lower()) or ("metode pembayaran" in body) or ("opsi pengiriman" in body)
        log.info(f"buy_now sampai checkout: {ok} (url={self.page.url})")
        return ok

    async def goto_checkout(self):
        await self.page.goto("https://shopee.co.id/cart", wait_until="domcontentloaded")
        await self.page.wait_for_timeout(2500)  # tunggu cart render (JS)
        await self._maybe_captcha()
        # 1) Centang "Pilih Semua". Shopee render checkbox sbg <div class*='checkbox'>
        #    (bukan <input>), jadi coba banyak strategi.
        checked = False
        for sel in [
            "label:has-text('Pilih Semua')",
            "text=Pilih Semua",
            "div[class*='select-all'] [class*='checkbox']",
            "div[class*='checkbox__input']",
            "[class*='shopee-checkbox']",
            "input[type='checkbox']",
        ]:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click(timeout=2500, force=True)
                    checked = True
                    log.info(f"centang via: {sel}")
                    break
            except Exception:
                continue
        if not checked:
            log.warning("checkbox 'Pilih Semua' tidak ketemu, lanjut coba Checkout")
        await self.page.wait_for_timeout(1200)
        # 2) Klik Checkout (tombol bar bawah, sering di dalam <span>)
        try:
            await click_any(self.page, [
                "button:has-text('Checkout')",
                "[class*='checkout'] button:has-text('Checkout')",
                "button:has-text('Check Out')",
                "div[class*='cart-page-bottom'] button",
                "text=/^Checkout/i",
            ], timeout=8000, what="Checkout")
        except Exception as e:
            # DIAGNOSA: kumpulkan semua teks tombol/elemen klik di halaman cart
            try:
                dump = await self.page.evaluate("""() => {
                    const out = [];
                    const els = document.querySelectorAll("button, a, [role='button'], div[class*='button'], div[class*='checkout']");
                    els.forEach(el => {
                        const t = (el.innerText||'').trim().replace(/\\s+/g,' ').slice(0,40);
                        if (t) out.push(t + ' | ' + (el.className||'').toString().slice(0,50));
                    });
                    return [...new Set(out)].slice(0, 40).join('\\n');
                }""")
            except Exception as de:
                dump = f"(gagal dump: {de})"
            # simpan HTML penuh utk analisa
            try:
                html = await self.page.content()
                with open("debug_cart.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception:
                pass
            await self.notify(f"Checkout gagal. Tombol di halaman:\n{dump}", screenshot=True)
            raise
        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(1500)

    def _norm_bank(self, va_bank):
        """Map alias bank -> teks yg tampil di Shopee."""
        if not va_bank:
            return None
        m = {
            "bca": "BCA", "mandiri": "Mandiri", "bni": "BNI", "bri": "BRI",
            "bsi": "Bank Syariah Indonesia", "permata": "Permata",
            "cimb": "CIMB", "seabank": "SeaBank",
        }
        key = va_bank.strip().lower().replace("bank", "").strip()
        return m.get(key, va_bank.strip())

    async def create_order(self, pay_method, va_bank):
        """Alur: Metode Pembayaran -> Lihat Semua -> Transfer Bank -> pilih bank
        -> Konfirmasi -> kembali ke checkout. BERHENTI sebelum 'Buat Pesanan'."""
        await self.page.wait_for_timeout(1500)
        bank = self._norm_bank(va_bank)
        try:
            # 1) Buka daftar lengkap metode: klik 'Lihat Semua' (di baris Metode Pembayaran)
            await click_any(self.page, [
                "text=Lihat Semua",
                "div:has-text('Metode Pembayaran') >> text=Lihat Semua",
                "text=Metode Pembayaran",
                "text=Pilih Metode Pembayaran",
            ], timeout=6000, what="buka daftar metode (Lihat Semua)")
            await self.page.wait_for_timeout(1500)

            if pay_method == "va":
                # 2) Expand kategori 'Transfer Bank' bila ada (accordion)
                try:
                    tb = self.page.locator("text=Transfer Bank").first
                    if await tb.count() > 0:
                        await tb.click(timeout=3000)
                        log.info("expand Transfer Bank")
                        await self.page.wait_for_timeout(1000)
                except Exception:
                    pass
                # 3) Pilih bank tujuan
                if bank:
                    await click_any(self.page, [
                        f"text=Bank {bank}",
                        f"text={bank}",
                        f"div[class*='payment'] :has-text('{bank}')",
                        f"img[alt*='{bank}']",
                    ], timeout=5000, what=f"pilih bank {bank}")
                    await self.page.wait_for_timeout(800)
            # 4) Konfirmasi pilihan metode (tombol bawah modal)
            await click_any(self.page, [
                "button:has-text('Konfirmasi')",
                "button:has-text('OK')",
                "button:has-text('Konfirmasi'):not([disabled])",
            ], timeout=5000, what="Konfirmasi metode")
            await self.page.wait_for_timeout(1500)
            await self.notify(f"Pembayaran '{bank or pay_method}' dipilih. Siap Buat Pesanan (berhenti sebelum bayar).", screenshot=True)
        except Exception as e:
            # diagnosa: dump teks metode pembayaran yg terlihat
            try:
                dump = await self.page.evaluate("""() => {
                    const out=[]; document.querySelectorAll("div,span,button,label").forEach(el=>{
                        const t=(el.innerText||'').trim();
                        if(t && t.length<30 && /bank|transfer|pembayaran|konfirmasi|lihat semua|virtual/i.test(t)) out.push(t);
                    }); return [...new Set(out)].slice(0,30).join('\\n');
                }""")
            except Exception:
                dump = "(dump gagal)"
            await self.notify(f"Gagal pilih pembayaran: {e}\nTeks terlihat:\n{dump}", screenshot=True)
            raise
        # 5) Kembali ke halaman checkout -> klik 'Buat Pesanan'
        #    (VA/Transfer Bank: ini hanya MEMBUAT pesanan + nomor VA, BUKAN memotong dana)
        await self.page.wait_for_timeout(1500)
        try:
            await click_any(self.page, [
                "button:has-text('Buat Pesanan')",
                "button:has-text('Buat Pesanan'):not([disabled])",
                "text=Buat Pesanan",
                "button:has-text('Bayar Sekarang')",
            ], timeout=8000, what="Buat Pesanan")
            await self.page.wait_for_load_state("domcontentloaded")
            await self.page.wait_for_timeout(2000)
            await self.notify("✅ Pesanan dibuat! Cek nomor VA utk transfer (dana belum terpotong).", screenshot=True)
        except Exception as e:
            await self.notify(f"Gagal klik Buat Pesanan: {e}", screenshot=True)
            raise
        return await self.page.inner_text("body")