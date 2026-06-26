import re
import asyncio
import random
import httpx
from utils.logger import get_logger

log = get_logger()

# Pola URL produk Shopee: /product/{shop_id}/{item_id} atau ...-i.{shop_id}.{item_id}
_SHOPEE_A = re.compile(r"/product/(\d+)/(\d+)")
_SHOPEE_B = re.compile(r"i\.(\d+)\.(\d+)")

# Header se-natural mungkin (meniru browser) untuk endpoint publik
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": "https://shopee.co.id/",
    "x-api-source": "pc",
    "x-shopee-language": "id",
}


def parse_shopee_ids(url: str):
    """Ekstrak (shop_id, item_id) dari URL produk Shopee. None kalau bukan Shopee."""
    m = _SHOPEE_A.search(url) or _SHOPEE_B.search(url)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


async def fetch_shopee_stock(client: httpx.AsyncClient, shop_id: int, item_id: int):
    """Ambil status stok via endpoint publik. Return dict ringkas atau None."""
    api = f"https://shopee.co.id/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}"
    try:
        r = await client.get(api, headers=_HEADERS, timeout=10)
        if r.status_code != 200:
            log.debug(f"stock api status {r.status_code}")
            return None
        data = r.json()
    except Exception as e:
        log.debug(f"stock api error: {e}")
        return None

    item = (((data or {}).get("data") or {}).get("item")) or {}
    if not item:
        return None
    stock = item.get("stock", 0) or 0
    name = item.get("title") or item.get("name") or "Produk"
    price = (item.get("price") or 0) / 100000  # Shopee price = *100000
    # cek varian (model) yg punya stok
    models = item.get("models") or []
    model_stock = sum((mm.get("stock", 0) or 0) for mm in models) if models else 0
    total = max(stock, model_stock)
    # flash sale?
    flash = bool(item.get("flash_sale") or item.get("is_flash_sale"))
    return {"name": name, "stock": total, "price": price, "flash": flash}


async def fetch_shopee_stock_via_page(page, shop_id: int, item_id: int):
    """Ambil stok lewat KONTEKS HALAMAN Chrome (CDP) yang sudah login.
    Request dijalankan dari dalam shopee.co.id -> membawa cookie + token sesi,
    sehingga lolos anti-bot 403 yang menimpa httpx polos."""
    api = f"https://shopee.co.id/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}"
    js = """
    async (url) => {
        try {
            const r = await fetch(url, {
                headers: {"x-api-source": "pc", "x-shopee-language": "id"},
                credentials: "include"
            });
            if (!r.ok) return {ok:false, status:r.status};
            const j = await r.json();
            return {ok:true, data:j};
        } catch (e) { return {ok:false, error:String(e)}; }
    }
    """
    try:
        res = await page.evaluate(js, api)
    except Exception as e:
        log.warning(f"via_page evaluate error: {e}")
        return {"_error": f"evaluate: {e}"}
    if not res or not res.get("ok"):
        log.warning(f"via_page gagal: {res}")
        return {"_error": f"http {res.get('status') if res else '??'}"}
    item = (((res.get("data") or {}).get("data") or {}).get("item")) or {}
    if not item:
        return None
    stock = item.get("stock", 0) or 0
    name = item.get("title") or item.get("name") or "Produk"
    price = (item.get("price") or 0) / 100000
    models = item.get("models") or []
    model_stock = sum((mm.get("stock", 0) or 0) for mm in models) if models else 0
    total = max(stock, model_stock)
    flash = bool(item.get("flash_sale") or item.get("is_flash_sale"))
    return {"name": name, "stock": total, "price": price, "flash": flash}


async def resolve_shopee_url(page, url: str):
    """Resolve link pendek/share Shopee (s.shopee.co.id, shp.ee, dst) jadi URL
    asli yg memuat shop_id/item_id. Pakai fetch dari konteks login (ikut redirect)."""
    ids = parse_shopee_ids(url)
    if ids:
        return url, ids
    if page is None:
        return url, None
    js = "async (u) => { try { const r = await fetch(u, {credentials:'include'}); return r.url; } catch(e){ return ''; } }"
    try:
        final = await page.evaluate(js, url)
    except Exception as e:
        log.debug(f"resolve fetch error: {e}")
        final = ""
    if final:
        ids = parse_shopee_ids(final)
        if ids:
            log.info(f"link resolve: {url} -> {final}")
            return final, ids
    # fallback: navigasi langsung lalu baca URL akhir
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        final = page.url
        ids = parse_shopee_ids(final)
        if ids:
            log.info(f"link resolve (goto): {final}")
            return final, ids
    except Exception as e:
        log.debug(f"resolve goto error: {e}")
    return url, None


class StockMonitor:
    """Monitor stok SEMI-OTOMATIS.

    - Polling endpoint publik (ringan, tidak memicu flag crawler checkout).
    - Saat stok TERSEDIA (transisi 0 -> >0), panggil on_restock(info) sekali.
    - Tidak melakukan checkout otomatis: hanya memberi sinyal untuk notifikasi.
    """

    def __init__(self, url: str, on_restock, interval=8, jitter=4, page=None):
        self.url = url
        self.on_restock = on_restock          # async callback(info: dict)
        self.interval = interval              # detik antar cek
        self.jitter = jitter                  # variasi acak biar tidak seragam
        self.page = page                      # halaman Chrome CDP login (disarankan)
        self._running = False

    async def start(self, max_minutes=720):
        self._running = True
        resolved_url, ids = await resolve_shopee_url(self.page, self.url)
        if not ids:
            log.warning(f"StockMonitor: tidak bisa baca ID dari link: {self.url}")
            await self.on_restock({"name": "Produk", "stock": -1, "price": 0,
                                   "flash": False, "note": "unsupported_link"})
            return
        self.url = resolved_url
        shop_id, item_id = ids
        last_in_stock = None
        loops = int((max_minutes * 60) / max(self.interval, 1))
        async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
            first = True
            for _ in range(loops):
                if not self._running:
                    break
                if self.page is not None:
                    info = await fetch_shopee_stock_via_page(self.page, shop_id, item_id)
                else:
                    info = await fetch_shopee_stock(client, shop_id, item_id)
                # diagnosa kegagalan baca stok
                if info is not None and info.get("_error"):
                    if first:
                        await self.on_restock({"name": "Produk", "stock": -1, "price": 0,
                                               "flash": False, "note": "read_failed",
                                               "detail": info.get("_error")})
                    first = False
                    await asyncio.sleep(self.interval + random.uniform(0, self.jitter))
                    continue
                # self-check pertama: lapor stok awal walau belum restock
                if first and info is not None:
                    await self.on_restock({**info, "note": "initial"})
                    first = False
                if info is not None and not info.get("_error"):
                    in_stock = info["stock"] > 0
                    # trigger HANYA saat transisi habis -> ada
                    if in_stock and last_in_stock is False:
                        log.info(f"RESTOCK terdeteksi: {info}")
                        await self.on_restock(info)
                    # trigger juga di cek pertama kalau sudah ada stok
                    if in_stock and last_in_stock is None:
                        await self.on_restock(info)
                    last_in_stock = in_stock
                await asyncio.sleep(self.interval + random.uniform(0, self.jitter))

    def stop(self):
        self._running = False