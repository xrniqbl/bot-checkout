# Checkout Bot (Shopee / Tokopedia / Generic Web)

Auto add-to-cart & create order **sampai halaman pembayaran (Virtual Account)**,
dikontrol penuh via **Telegram**. Pembayaran VA dilakukan **manual** oleh user.

> WARNING: Shopee & Tokopedia melarang automation di ToS. Gunakan akun yang siap
> kamu relakan & untuk eksperimen pribadi. Patuhi hukum dan ToS yang berlaku.

## Setup
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    playwright install chromium
    copy config\.env.example config\.env
    python main.py

## Alur
1. /addproduct -> paste link
2. set qty, varian, mode trigger, bank VA target
3. bot tunggu trigger -> add cart -> checkout -> pilih VA
4. STOP di halaman bayar -> kirim detail VA + screenshot ke Telegram
5. user bayar manual via m-banking
