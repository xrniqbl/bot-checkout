# Checkout Bot (Shopee / Tokopedia / Generic Web)

Auto add-to-cart & create order **sampai halaman pembayaran (Virtual Account)**,
dikontrol penuh via **Telegram**. Pembayaran VA dilakukan **manual** oleh user.

> WARNING: Shopee & Tokopedia melarang automation di ToS. Gunakan akun yang siap
> kamu relakan & untuk eksperimen pribadi. Patuhi hukum dan ToS yang berlaku.

## Fitur
- Login **persisten** (stay-login sampai /logout) + multi-akun
- Deteksi **restock** cepat & akurat (verifikasi ganda anti false-positive)
- **Flash-sale terjadwal presisi NTP** (pre-warm + hot-reload + tembak milidetik)
- Setting **pembayaran di awal** (default VA bank per akun)
- Selector multi-fallback (data-testid/teks/aria) + CAPTCHA handling
- Kontrol penuh via **Telegram**

## Dokumentasi
- [docs/SETUP_TELEGRAM.md](docs/SETUP_TELEGRAM.md) — cara bikin bot & pakai di Telegram
- [docs/DEPLOY_VPS.md](docs/DEPLOY_VPS.md) — deploy 24/7 di VPS (systemd)

## Quick Start
```bash
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy config\.env.example config\.env   # isi token & key
python main.py
```

## Perintah Telegram
```
/login akun1 shopee              # login sekali -> stay
/setpayment akun1 va BCA         # bayar default
/addproduct <link>               # + wizard tombol (qty, mode)
/flashsale <link> YYYY-MM-DD HH:MM:SS akun1 [varian]
/list  /run <id>  /logout akun1
```

## Struktur
- core/ : browser (persistent), restock, flashsale, scheduler, payment, dom helper
- platforms/ : base, shopee, tokopedia, generic
- telegram_bot/ : handler & menu
- database/ : SQLite (akun + task + setting bayar)
- utils/ : logger, timesync (NTP)
