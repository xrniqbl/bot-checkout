# Deploy ke VPS (Ubuntu) — biar bot jalan 24/7 & cepat

> Pilih VPS region dekat target (mis. Singapore/Jakarta) untuk latensi rendah.
> Spek minimal: 2 vCPU, 2-4GB RAM (Chromium butuh RAM).

## 1. Persiapan server
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git xvfb
```

## 2. Clone repo
```bash
git clone https://github.com/xrniqbl/bot-checkout.git
cd bot-checkout
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
```

## 3. Konfigurasi
```bash
cp config/.env.example config/.env
nano config/.env     # isi token, user id, encryption key
```

## 4. Login pertama (butuh GUI sekali)
Login butuh browser terlihat. Dua opsi:
- **Opsi A (mudah):** login di laptop kamu (HEADLESS=false), lalu COPY folder
  `sessions/` ke VPS (scp). Profil login ikut terbawa.
  ```bash
  scp -r sessions/ user@VPS_IP:~/bot-checkout/
  ```
- **Opsi B:** pakai `xvfb` (virtual display) + VNC untuk login di server.

Setelah ada `sessions/`, set `HEADLESS=true` di VPS.

## 5. Jalankan sebagai service (systemd) - auto restart
Buat `/etc/systemd/system/checkout-bot.service`:
```ini
[Unit]
Description=Checkout Bot Telegram
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/bot-checkout
Environment=DISPLAY=:99
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1366x768x24 &
ExecStart=/home/YOUR_USER/bot-checkout/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Aktifkan:
```bash
sudo systemctl daemon-reload
sudo systemctl enable checkout-bot
sudo systemctl start checkout-bot
sudo systemctl status checkout-bot      # cek jalan
journalctl -u checkout-bot -f           # lihat log realtime
```

## 6. Update kode
```bash
cd bot-checkout && git pull
sudo systemctl restart checkout-bot
```

## Tips performa flash-sale
- VPS dekat data center = latensi kecil (faktor terbesar).
- Sinkronisasi NTP server: `sudo timedatectl set-ntp true` (bot juga sync sendiri).
- Naikkan `prewarm_sec` di core/flashsale.py jika koneksi lambat.
