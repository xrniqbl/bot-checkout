import os
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from config.settings import HEADLESS, SLOW_MO_MS, DEFAULT_PROXY, SESSIONS_DIR
from utils.logger import get_logger

log = get_logger()

class BrowserEngine:
    """Persistent browser profile per akun.
    Profil disimpan di sessions/<akun>_profile -> login STAY sampai user logout.
    Tidak perlu login ulang tiap run (cookies, localStorage, token tersimpan)."""

    def __init__(self, account: str, proxy: str | None = None):
        self.account = account
        self.proxy = proxy or DEFAULT_PROXY
        self.profile_dir = os.path.join(SESSIONS_DIR, f"{account}_profile")
        os.makedirs(self.profile_dir, exist_ok=True)
        self._pw = None
        self.context = None
        self.page = None

    async def start(self, headless: bool | None = None):
        self._pw = await async_playwright().start()
        kwargs = {
            "user_data_dir": self.profile_dir,
            "headless": HEADLESS if headless is None else headless,
            "slow_mo": SLOW_MO_MS,
            "locale": "id-ID",
            "viewport": {"width": 1366, "height": 768},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if self.proxy:
            kwargs["proxy"] = {"server": self.proxy}
        # launch_persistent_context = profil tetap tersimpan di disk
        self.context = await self._pw.chromium.launch_persistent_context(**kwargs)
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await stealth_async(self.page)
        log.info(f"[{self.account}] persistent profile loaded ({self.profile_dir})")
        return self.page

    async def new_page(self):
        p = await self.context.new_page()
        await stealth_async(p)
        return p

    async def close(self):
        # profil otomatis tersimpan ke disk -> login tetap ada di run berikutnya
        if self.context:
            await self.context.close()
        if self._pw:
            await self._pw.stop()

    def wipe_profile(self):
        """Hapus profil = logout total."""
        import shutil
        if os.path.exists(self.profile_dir):
            shutil.rmtree(self.profile_dir, ignore_errors=True)
        log.info(f"[{self.account}] profile wiped (logged out)")
