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
        """Klik 'Beli Sekarang' -> WAJIB sampai URL /checkout. Tangani popup variasi.
        Return True hanya jika benar2 pindah ke halaman checkout (cek URL, bukan teks
        -- footer produk punya kata 'Metode Pembayaran' yg bikin false positive)."""
        await self.page.wait_for_timeout(1000)
        async def _click_beli():
            for sel in ["button:has-text('Beli Sekarang')", "text=Beli Sekarang",
                        "div[class*='product-briefing'] button:has-text('Beli')"]:
                try:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0:
                        try:
                            await loc.scroll_into_view_if_needed(timeout=2500)
                        except Exception:
                            pass
                        await loc.click(timeout=4000, force=True)
                        log.info(f"klik Beli Sekarang via: {sel}")
                        return True
                except Exception:
                    continue
            return False

        if not await _click_beli():
            log.warning("tombol 'Beli Sekarang' tidak ketemu")
            return False
        await self.page.wait_for_timeout(1500)

        # cek apakah muncul popup variasi (mis 'Silakan pilih variasi')
        try:
            body = (await self.page.inner_text("body")).lower()
            if "pilih variasi" in body or "silakan pilih" in body:
                log.info("popup variasi muncul -> pilih opsi pertama")
                # pilih opsi variasi pertama yg tersedia
                try:
                    opt = self.page.locator("button[class*='product-variation']:not([disabled])").first
                    if await opt.count() > 0:
                        await opt.click(timeout=2500)
                        await self.page.wait_for_timeout(600)
                except Exception:
                    pass
                # klik Beli Sekarang konfirmasi di popup
                await _click_beli()
        except Exception:
            pass

        # tunggu navigasi ke /checkout (KETAT)
        try:
            await self.page.wait_for_url("**/checkout**", timeout=12000)
        except Exception:
            await self.page.wait_for_timeout(2500)
        url = self.page.url
        ok = "/checkout" in url.lower()
        log.info(f"buy_now sampai checkout: {ok} (url={url})")
        if not ok:
            # diagnosa: apa yg terlihat setelah klik Beli Sekarang
            try:
                dump = await self.page.evaluate("""() => {
                    const out=[]; document.querySelectorAll("button,div[role='button'],a").forEach(el=>{
                        const t=(el.innerText||'').trim();
                        if(t && t.length<35 && /beli|keranjang|checkout|variasi|pilih|login|masuk/i.test(t)) out.push(t);
                    }); return [...new Set(out)].slice(0,25).join(' | ');
                }""")
            except Exception:
                dump="(dump gagal)"
            await self.notify(f"Beli Sekarang TIDAK pindah ke checkout.\nurl={url}\nTerlihat: {dump}", screenshot=True)
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
        """DESKTOP web. Di halaman /checkout: Metode Pembayaran tampil sbg tombol
        langsung. Alur: klik 'Transfer Bank' -> pilih bank (mis BRI) -> (Konfirmasi)
        -> klik 'Buat Pesanan'. Untuk VA/Transfer Bank, Buat Pesanan hanya membuat
        pesanan + nomor VA (dana belum terpotong)."""
        await self.page.wait_for_timeout(1500)
        bank = self._norm_bank(va_bank) or "BRI"
        # GUARD: pastikan benar2 di halaman checkout (hindari salah klik logo bank di footer produk)
        if "/checkout" not in self.page.url.lower():
            await self.notify(f"Belum di halaman checkout (url={self.page.url}). Batalkan pilih pembayaran.", screenshot=True)
            raise RuntimeError("not on checkout page")
        try:
            # scroll ke bagian Metode Pembayaran
            try:
                await self.page.locator("text=Metode Pembayaran").first.scroll_into_view_if_needed(timeout=4000)
            except Exception:
                pass
            await self.page.wait_for_timeout(600)

            # 1) klik tombol 'Transfer Bank' (desktop: pill langsung; fallback 'Lihat Semua')
            clicked_tb = False
            for sel in ["button:has-text('Transfer Bank')", "text=Transfer Bank",
                        "div[class*='payment'] :text('Transfer Bank')"]:
                try:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0:
                        await loc.click(timeout=3500)
                        clicked_tb = True; log.info(f"klik Transfer Bank via: {sel}"); break
                except Exception:
                    continue
            if not clicked_tb:
                # fallback layout lama: Lihat Semua dulu
                try:
                    await click_any(self.page, ["text=Lihat Semua"], timeout=3000, what="Lihat Semua")
                    await self.page.wait_for_timeout(1000)
                    await click_any(self.page, ["text=Transfer Bank"], timeout=3000, what="Transfer Bank (modal)")
                    clicked_tb = True
                except Exception:
                    pass
            await self.page.wait_for_timeout(1500)

            # 2) pilih bank tujuan (mis. Bank BRI)
            await click_any(self.page, [
                f"text=Bank {bank}",
                f"text={bank}",
                f"div[class*='bank'] :has-text('{bank}')",
                f"label:has-text('{bank}')",
                f"img[alt*='{bank}']",
            ], timeout=6000, what=f"pilih Bank {bank}")
            await self.page.wait_for_timeout(1000)

            # 3) Konfirmasi pilihan bila ada tombol konfirmasi di modal
            for sel in ["button:has-text('Konfirmasi'):not([disabled])",
                        "button:has-text('Konfirmasi')", "button:has-text('OK')"]:
                try:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click(timeout=2500); log.info("klik Konfirmasi metode"); break
                except Exception:
                    continue
            await self.page.wait_for_timeout(1500)
            await self.notify(f"Metode 'Transfer Bank - {bank}' dipilih.", screenshot=True)
        except Exception as e:
            try:
                dump = await self.page.evaluate("""() => {
                    const out=[]; document.querySelectorAll("button,div,span,label").forEach(el=>{
                        const t=(el.innerText||'').trim();
                        if(t && t.length<28 && /bank|transfer|qris|cod|shopeepay|konfirmasi|pesanan|debit|kredit/i.test(t)) out.push(t);
                    }); return [...new Set(out)].slice(0,40).join('\\n');
                }""")
            except Exception:
                dump="(dump gagal)"
            await self.notify(f"Gagal pilih pembayaran: {e}\nTeks terlihat:\n{dump}", screenshot=True)
            raise

        # 4) klik 'Buat Pesanan' (VA: buat pesanan + nomor VA, dana belum terpotong)
        await self.page.wait_for_timeout(1200)
        try:
            await click_any(self.page, [
                "button:has-text('Buat Pesanan'):not([disabled])",
                "button:has-text('Buat Pesanan')",
                "text=Buat Pesanan",
            ], timeout=8000, what="Buat Pesanan")
            await self.page.wait_for_load_state("domcontentloaded")
            await self.page.wait_for_timeout(2500)
            await self.notify(f"✅ Pesanan dibuat (Transfer Bank {bank})! Cek nomor VA utk transfer; dana belum terpotong.", screenshot=True)
        except Exception as e:
            await self.notify(f"Gagal klik Buat Pesanan: {e}", screenshot=True)
            raise
        return await self.page.inner_text("body")