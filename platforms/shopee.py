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
        import random
        # NAVIGASI MANUSIAWI: jangan goto langsung ke URL produk (=sinyal crawler_item).
        # Buka homepage dulu -> jeda acak -> baru ke produk dgn referer homepage.
        try:
            if "/checkout" not in self.page.url and "shopee.co.id" not in self.page.url:
                await self.page.goto(self.HOME, wait_until="domcontentloaded", timeout=45000)
                await self.page.wait_for_timeout(random.randint(1500, 3000))
                # sedikit gerak mouse + scroll (perilaku manusia)
                try:
                    await self.page.mouse.move(random.randint(200, 800), random.randint(150, 500), steps=10)
                    await self.page.mouse.wheel(0, random.randint(300, 700))
                    await self.page.wait_for_timeout(random.randint(800, 1600))
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"homepage warmup: {e}")
        # ke produk dgn referer homepage (seolah klik dari Shopee)
        try:
            await self.page.goto(url, wait_until="domcontentloaded",
                                 referer=self.HOME, timeout=45000)
        except Exception:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await self.page.wait_for_timeout(random.randint(1200, 2500))
        await self._maybe_captcha()
        await first_visible(self.page, self.ADD_CART + self.BUY_NOW, timeout=10000)

    async def _maybe_captcha(self, wait_sec=150):
        """Deteksi halaman anti-bot/captcha Shopee. Karena Chrome (mode CDP) TERLIHAT,
        minta user solve manual di jendela itu, lalu polling sampai lolos."""
        import asyncio
        def _is_captcha():
            u = (self.page.url or "").lower()
            return ("/verify/captcha" in u) or ("/verify/traffic" in u) or ("anti_bot" in u)
        # cek via URL atau elemen
        hit = _is_captcha()
        if not hit:
            try:
                hit = await exists(self.page, ["iframe[src*='captcha']", "text=Terjadi Kesalahan",
                                               "button:has-text('Coba Lagi')", "text=Verifikasi"], timeout=800)
            except Exception:
                hit = False
        if not hit:
            return True
        await self.notify("🛑 Anti-bot/CAPTCHA Shopee muncul!\n"
                          "Selesaikan VERIFIKASI manual di jendela Chrome sekarang.\n"
                          f"Bot menunggu sampai {wait_sec} detik...", screenshot=True)
        # coba klik 'Coba Lagi' sekali (kadang cukup)
        try:
            btn = self.page.locator("button:has-text('Coba Lagi')").first
            if await btn.count() > 0:
                await btn.click(timeout=2000)
                await self.page.wait_for_timeout(2000)
        except Exception:
            pass
        # polling sampai user menyelesaikan (URL keluar dari captcha)
        for _ in range(wait_sec // 3):
            await asyncio.sleep(3)
            if not _is_captcha():
                await self.notify("✅ Verifikasi selesai, melanjutkan...")
                await self.page.wait_for_timeout(1500)
                return True
        await self.notify("⏳ Verifikasi belum selesai (timeout).")
        return False

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
        """Klik 'Beli Sekarang' dgn beberapa strategi (normal -> JS click) lalu WAJIB
        sampai URL /checkout. Tangani drawer variasi bila muncul."""
        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(2000)

        async def _click_beli(where="utama"):
            # cari SEMUA tombol Beli Sekarang yg terlihat, klik yg paling relevan
            try:
                btns = self.page.locator("button:has-text('Beli Sekarang'), div[role='button']:has-text('Beli Sekarang')")
                n = await btns.count()
                log.info(f"ditemukan {n} tombol 'Beli Sekarang' ({where})")
                for i in range(n):
                    b = btns.nth(i)
                    try:
                        if not await b.is_visible():
                            continue
                        await b.scroll_into_view_if_needed(timeout=2000)
                        await b.click(timeout=3500)
                        log.info(f"klik Beli Sekarang (normal) idx={i}")
                        return True
                    except Exception:
                        continue
            except Exception as ex:
                log.warning(f"locate beli error: {ex}")
            # strategi 2: klik MOUSE ASLI di koordinat tombol (gerakan manusiawi)
            try:
                b = self.page.locator("button:has-text('Beli Sekarang')").first
                if await b.count() > 0:
                    await b.scroll_into_view_if_needed(timeout=2000)
                    box = await b.bounding_box()
                    if box:
                        cx = box["x"] + box["width"]/2
                        cy = box["y"] + box["height"]/2
                        # gerak bertahap (human-like)
                        await self.page.mouse.move(cx-40, cy-15, steps=8)
                        await self.page.wait_for_timeout(120)
                        await self.page.mouse.move(cx, cy, steps=6)
                        await self.page.wait_for_timeout(80)
                        await self.page.mouse.down()
                        await self.page.wait_for_timeout(60)
                        await self.page.mouse.up()
                        log.info("klik Beli Sekarang (mouse asli)")
                        return True
            except Exception as ex:
                log.warning(f"mouse click error: {ex}")
            # fallback: JS click langsung ke elemen DOM
            try:
                done = await self.page.evaluate("""() => {
                    const els=[...document.querySelectorAll("button,div[role='button'],a")];
                    const t=els.find(el=>/beli sekarang/i.test((el.innerText||'')) && el.offsetParent!==null);
                    if(t){ t.click(); return true; } return false;
                }""")
                if done:
                    log.info("klik Beli Sekarang (JS click)")
                    return True
            except Exception as ex:
                log.warning(f"JS click error: {ex}")
            return False

        if not await _click_beli("utama"):
            log.warning("tombol 'Beli Sekarang' tidak bisa diklik")
            return False
        await self.page.wait_for_timeout(2500)

        # bila masih di produk -> mungkin muncul drawer variasi/konfirmasi
        if "/checkout" not in self.page.url.lower():
            try:
                # pilih opsi variasi pertama yg tersedia (bila ada)
                opt = self.page.locator("button[class*='product-variation']:not([class*='disabled'])").first
                if await opt.count() > 0 and await opt.is_visible():
                    await opt.click(timeout=2500)
                    log.info("pilih variasi pertama di drawer")
                    await self.page.wait_for_timeout(800)
            except Exception:
                pass
            # klik konfirmasi Beli Sekarang di drawer
            await _click_beli("drawer")
            await self.page.wait_for_timeout(2000)

        # tunggu navigasi ke /checkout
        try:
            await self.page.wait_for_url("**/checkout**", timeout=10000)
        except Exception:
            await self.page.wait_for_timeout(2000)
        url = self.page.url
        ok = "/checkout" in url.lower()
        log.info(f"buy_now sampai checkout: {ok} (url={url})")
        if not ok:
            try:
                dump = await self.page.evaluate("""() => {
                    const out=[]; document.querySelectorAll("button,div[role='button'],a").forEach(el=>{
                        const t=(el.innerText||'').trim();
                        if(t && t.length<35 && el.offsetParent!==null && /beli|keranjang|checkout|variasi|pilih|masuk|login|tambah/i.test(t)) out.push(t);
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