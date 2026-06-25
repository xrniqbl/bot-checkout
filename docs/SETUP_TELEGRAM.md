# Setup Bot Telegram (langkah demi langkah)

## 1. Buat Bot di Telegram
1. Buka Telegram, cari **@BotFather**
2. Kirim `/newbot` -> ikuti instruksi (nama + username bot)
3. BotFather kasih **TOKEN** (contoh: `8123456:AAH...`). Simpan.

## 2. Dapatkan User ID kamu (biar cuma kamu yg bisa kontrol)
1. Cari **@userinfobot** di Telegram, kirim `/start`
2. Dia balas ID numerik kamu (contoh: `123456789`)

## 3. Isi file konfigurasi
```bash
copy config\.env.example config\.env   # Windows
# cp config/.env.example config/.env    # Linux
```
Edit `config/.env`:
```
TELEGRAM_BOT_TOKEN=8123456:AAH...        # token dari BotFather
TELEGRAM_ALLOWED_USER_IDS=123456789      # ID kamu (boleh banyak, pisah koma)
HEADLESS=false                           # false saat login pertama (lihat browser)
SESSION_ENCRYPTION_KEY=                  # generate di bawah
TWOCAPTCHA_API_KEY=                      # opsional
```
Generate kunci enkripsi session:
```bash
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```
Tempel hasilnya ke `SESSION_ENCRYPTION_KEY`.

## 4. Install & jalankan
```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate      # Linux
pip install -r requirements.txt
playwright install chromium
python main.py
```

## 5. Pakai di Telegram
Buka chat bot kamu, kirim:
```
/start
/login akun1 shopee              # browser kebuka, login manual sekali -> STAY login
/setpayment akun1 va BCA         # set bayar default
/addproduct <link produk>        # lalu pilih qty + mode (Instant/Restock) via tombol
/flashsale <link> 2026-07-01 20:00:00 akun1 Merah,L
/list                            # lihat semua task
/logout akun1                    # hapus login
```

### Catatan login pertama
- Saat `/login`, set `HEADLESS=false` agar browser terlihat & kamu bisa isi password/OTP.
- Setelah login sukses, profil tersimpan -> berikutnya bisa `HEADLESS=true`.
