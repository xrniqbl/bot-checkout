import asyncio
from utils.logger import get_logger
log = get_logger()

async def first_visible(page, selectors, timeout=5000):
    """Kembalikan locator pertama yang VISIBLE dari daftar kandidat selector.
    selectors: list[str] (CSS / text= / role=). None jika tak ada."""
    deadline = timeout
    step = 250
    while deadline > 0:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        await asyncio.sleep(step / 1000)
        deadline -= step
    return None

async def click_any(page, selectors, timeout=5000, what="element"):
    loc = await first_visible(page, selectors, timeout)
    if not loc:
        raise RuntimeError(f"Tidak menemukan {what}. Selector dicoba: {selectors}")
    await loc.scroll_into_view_if_needed()
    await loc.click()
    log.info(f"klik {what} OK")
    return loc

async def exists(page, selectors, timeout=3000):
    return (await first_visible(page, selectors, timeout)) is not None

async def fill_any(page, selectors, value, timeout=4000, what="input"):
    loc = await first_visible(page, selectors, timeout)
    if not loc:
        log.warning(f"input {what} tak ketemu")
        return False
    await loc.fill(str(value))
    return True
