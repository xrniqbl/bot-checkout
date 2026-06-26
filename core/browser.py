import os
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from config.settings import HEADLESS, SLOW_MO_MS, DEFAULT_PROXY, SESSIONS_DIR, CHROME_USER_DATA_DIR, CHROME_CDP_URL
from utils.logger import get_logger

log = get_logger()

# Script anti-deteksi: sembunyikan jejak otomasi sebelum halaman dimuat
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['id-ID','id','en-US','en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = { runtime: {} };
const _q = window.navigator.permissions && window.navigator.permissions.query;
if (_q) {
  window.navigator.permissions.query = (p) => (
    p && p.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : _q(p)
  );
}
"""

class BrowserEngine:
    """Persistent profile + anti-deteksi.
    - Pakai Chrome asli (channel='chrome') bila ada -> lebih sulit dideteksi.
    - Hilangkan flag '--enable-automation' (banner 'controlled by automated test').
    - Inject STEALTH_JS sebelum tiap halaman."""

    def __init__(self, account: str, proxy: str | None = None):
        self.account = account
        self.proxy = proxy or DEFAULT_PROXY
        # jika CHROME_USER_DATA_DIR diset -> pakai profil Chrome asli (per akun subfolder)
        if CHROME_USER_DATA_DIR:
            self.profile_dir = CHROME_USER_DATA_DIR
        else:
            self.profile_dir = os.path.join(SESSIONS_DIR, f"{account}_profile")
        os.makedirs(self.profile_dir, exist_ok=True)
        self._pw = None
        self.context = None
        self.page = None

    async def start(self, headless: bool | None = None):
        self._pw = await async_playwright().start()
        # === MODE CDP: tempel ke Chrome asli yg sudah berjalan (anti-deteksi terkuat) ===
        if CHROME_CDP_URL:
            self._cdp = True
            browser = await self._pw.chromium.connect_over_cdp(CHROME_CDP_URL)
            self._browser = browser
            # pakai context default yg sudah ada (profil & fingerprint Chrome asli)
            self.context = browser.contexts[0] if browser.contexts else await browser.new_context()
            await self.context.add_init_script(STEALTH_JS)
            pages = self.context.pages
            self.page = pages[0] if pages else await self.context.new_page()
            log.info(f"[{self.account}] ATTACH ke Chrome asli via CDP: {CHROME_CDP_URL}")
            return self.page
        self._cdp = False
        kwargs = {
            "user_data_dir": self.profile_dir,
            "headless": HEADLESS if headless is None else headless,
            "slow_mo": SLOW_MO_MS,
            "locale": "id-ID",
            "timezone_id": "Asia/Jakarta",
            "viewport": {"width": 1366, "height": 768},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            # buang switch yg bikin banner & mudah dideteksi
            "ignore_default_args": ["--enable-automation"],
        }
        if self.proxy:
            kwargs["proxy"] = {"server": self.proxy}

        # coba pakai Chrome asli dulu (lebih lolos anti-bot), fallback ke chromium
        try:
            self.context = await self._pw.chromium.launch_persistent_context(channel="chrome", **kwargs)
            log.info(f"[{self.account}] pakai Chrome asli (channel=chrome)")
        except Exception as e:
            log.warning(f"Chrome asli gagal ({e}); fallback ke chromium bawaan")
            self.context = await self._pw.chromium.launch_persistent_context(**kwargs)

        # inject stealth ke semua halaman baru
        await self.context.add_init_script(STEALTH_JS)
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        try:
            await stealth_async(self.page)
        except Exception:
            pass
        log.info(f"[{self.account}] persistent profile loaded ({self.profile_dir})")
        return self.page

    async def new_page(self):
        p = await self.context.new_page()
        try:
            await stealth_async(p)
        except Exception:
            pass
        return p

    async def close(self):
        try:
            if getattr(self, "_cdp", False):
                # JANGAN tutup Chrome milik user; cukup lepas koneksi
                if getattr(self, "_browser", None):
                    await self._browser.close()  # close koneksi CDP, Chrome tetap hidup
            elif self.context:
                await self.context.close()
        except Exception as e:
            log.warning(f"close: {e}")
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass


    def wipe_profile(self):
        import shutil
        if os.path.exists(self.profile_dir):
            shutil.rmtree(self.profile_dir, ignore_errors=True)
        log.info(f"[{self.account}] profile wiped (logged out)")