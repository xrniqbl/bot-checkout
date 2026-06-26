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
    """Baca stok lewat KONTEKS Chrome (CDP) login. Coba 2 endpoint, parse beberapa
    bentuk JSON, dan SELALU kembalikan diagnosa (tidak pernah None diam-diam)."""
    apis = [
        f"https://shopee.co.id/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}",
        f"https://shopee.co.id/api/v4/item/get?itemid={item_id}&shopid={shop_id}",
    ]
    js = """
    async (url) => {
        try {
            const r = await fetch(url, {
                headers: {"x-api-source":"pc","x-shopee-language":"id","af-ac-enc-dat":""},
                credentials: "include"
            });
            const t = await r.text();
            return {status: r.status, body: t.slice(0, 4000)};
        } catch (e) { return {status: -1, body: String(e)}; }
    }
    """
    last = None
    for api in apis:
        try:
            res = await page.evaluate(js, api)
        except Exception as e:
            log.warning(f"via_page evaluate error: {e}")
            last = {"_error": f"evaluate: {e}"}
            continue
        status = res.get("status") if res else "??"
        if status != 200:
            last = {"_error": f"http {status}"}
            log.warning(f"via_page {api} -> http {status}")
            continue
        # coba parse JSON
        import json as _json
        try:
            data = _json.loads(res.get("body") or "{}")
        except Exception:
            last = {"_error": f"json parse gagal (status 200)"}
            continue
        # bentuk get_pc: data.item.* ; bentuk item/get: data.*
        item = (((data or {}).get("data") or {}).get("item")) or ((data or {}).get("data")) or {}
        if not isinstance(item, dict) or not item:
            last = {"_error": f"item kosong (mungkin login/region). keys={list((data or {}).keys())}"}
            log.warning(f"via_page item kosong: {str(data)[:200]}")
            continue
        stock = item.get("stock", 0) or 0
        name = item.get("title") or item.get("name") or "Produk"
        price = (item.get("price") or item.get("price_min") or 0) / 100000
        models = item.get("models") or []
        model_stock = sum((mm.get("stock", 0) or 0) for mm in models) if models else 0
        total = max(stock, model_stock)
        flash = bool(item.get("flash_sale") or item.get("is_flash_sale"))
        return {"name": name, "stock": total, "price": price, "flash": flash}
    return last or {"_error": "tidak ada endpoint berhasil"}


async def fetch_shopee_stock_via_dom(page, url: str):
    """PLAN C (gentle): baca stok dari DOM TANPA menabrak captcha berulang.
    - Kalau halaman lagi di captcha -> minta solve manual (tidak goto paksa).
    - Kalau belum di halaman produk -> goto sekali.
    - Kalau sudah di produk -> reload lembut untuk data terbaru."""
    import re as _re
    cur = (page.url or "").lower()
    on_captcha = ("/verify/" in cur) or ("anti_bot" in cur)
    on_product = ("/product/" in cur) or bool(_re.search(r"i\.\d+\.\d+", cur))
    if on_captcha:
        return {"_error": "captcha_manual"}
    try:
        if not on_product:
            # belum di produk -> goto sekali
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)
        # kalau sudah di produk: baca DOM apa adanya (tanpa reload paksa)
    except Exception as e:
        return {"_error": f"nav: {e}"}
    cur = (page.url or "").lower()
    if ("/verify/" in cur) or ("anti_bot" in cur):
        return {"_error": "captcha_manual"}
    js = r'''
    () => {
      const txt = document.body ? document.body.innerText : "";
      const habis = /stok habis|sold out|habis terjual|produk tidak ditemukan|tidak tersedia/i.test(txt);
      const btns = Array.from(document.querySelectorAll('button'));
      const buy = btns.find(b => /beli sekarang|masukkan keranjang|tambah ke keranjang|add to cart|buy now/i.test((b.innerText||'')));
      const buyEnabled = buy ? !buy.disabled : false;
      let stockNum = null;
      const m = txt.match(/(?:tersisa|stok)\s*:?\s*(\d+)/i);
      if (m) stockNum = parseInt(m[1]);
      const h1 = document.querySelector('h1');
      const name = h1 ? h1.innerText.trim() : (document.title||'Produk');
      return {habis, buyEnabled, stockNum, name, hasBuy: !!buy};
    }
    '''
    try:
        r = await page.evaluate(js)
    except Exception as e:
        return {"_error": f"dom eval: {e}"}
    if not r:
        return {"_error": "dom kosong"}
    name = r.get("name") or "Produk"
    if r.get("habis"):
        return {"name": name, "stock": 0, "price": 0, "flash": False}
    in_stock = bool(r.get("buyEnabled")) or (r.get("stockNum") or 0) > 0 or bool(r.get("hasBuy"))
    stock = r.get("stockNum") if r.get("stockNum") else (1 if in_stock else 0)
    return {"name": name, "stock": stock, "price": 0, "flash": False}


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

    def __init__(self, url: str, on_restock, interval=20, jitter=8, page=None):
        self.url = url
        self.on_restock = on_restock          # async callback(info: dict)
        self.interval = interval              # detik antar cek
        self.jitter = jitter                  # variasi acak biar tidak seragam
        self.page = page                      # halaman Chrome CDP login (disarankan)
        self._running = False
        self._err_count = 0

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
        # client httpx HANYA dibuat kalau tidak ada page (fallback). Tanpa http2
        # supaya tidak butuh paket 'h2'.
        client = None if self.page is not None else httpx.AsyncClient(follow_redirects=True)
        try:
            first = True
            for _ in range(loops):
                if not self._running:
                    break
                try:
                    if self.page is not None:
                        info = await fetch_shopee_stock_via_dom(self.page, self.url)
                    else:
                        info = await fetch_shopee_stock(client, shop_id, item_id)
                except Exception as e:
                    log.exception(f"fetch error: {e}")
                    info = {"_error": f"exception: {e}"}
                log.info(f"[poll] info={info}")
                # diagnosa kegagalan baca stok
                if info is not None and info.get("_error"):
                    err = info.get("_error")
                    # ingatkan tiap ~30 dtk utk captcha; sekali utk error lain
                    do_notify = first or (("captcha" in str(err)) and (self._err_count % 3 == 0))
                    if do_notify:
                        try:
                            await self.on_restock({"name": "Produk", "stock": -1, "price": 0,
                                                   "flash": False, "note": "read_failed",
                                                   "detail": err})
                        except Exception as e:
                            log.exception(f"on_restock(read_failed) error: {e}")
                    self._err_count += 1
                    first = False
                    await asyncio.sleep(self.interval + random.uniform(0, self.jitter))
                    continue
                # self-check pertama: lapor stok awal walau belum restock
                if first and info is not None:
                    try:
                        await self.on_restock({**info, "note": "initial"})
                    except Exception as e:
                        log.exception(f"on_restock(initial) error: {e}")
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
        finally:
            if client is not None:
                await client.aclose()

    def stop(self):
        self._running = False