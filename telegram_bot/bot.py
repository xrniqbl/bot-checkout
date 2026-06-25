from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup)
from telegram.constants import ParseMode
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)
import io
from datetime import datetime

from config.settings import TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS
from database.models import (init_db, db, Task, Account, get_or_create_account)
from platforms import detect_platform, get_platform
from core import scheduler
from utils.timesync import timesync
from utils.logger import get_logger

log = get_logger()

PLATFORM_LABEL = {"shopee": "🟠 Shopee", "tokopedia": "🟢 Tokopedia", "generic": "🌐 Website"}

# ---------------- akses ----------------
def authorized(uid):
    return (not ALLOWED_USER_IDS) or (uid in ALLOWED_USER_IDS)

async def guard(update: Update):
    uid = update.effective_user.id
    if not authorized(uid):
        msg = update.message or (update.callback_query and update.callback_query.message)
        if msg: await msg.reply_text("⛔ Akses ditolak. Kamu tidak diizinkan memakai bot ini.")
        return False
    return True

# ---------------- notifier ----------------
def make_notifier(app, chat_id):
    async def notifier(text, screenshot=None):
        await app.bot.send_message(chat_id=chat_id, text=text[:4000])
        if screenshot:
            await app.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(screenshot))
    return notifier

# ---------------- menu utama ----------------
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Tambah Produk", callback_data="m:add"),
         InlineKeyboardButton("📋 Daftar Task", callback_data="m:list")],
        [InlineKeyboardButton("🔑 Login Akun", callback_data="m:login"),
         InlineKeyboardButton("🚪 Logout", callback_data="m:logout")],
        [InlineKeyboardButton("💳 Atur Pembayaran", callback_data="m:pay"),
         InlineKeyboardButton("⚡ Flash Sale", callback_data="m:flash")],
        [InlineKeyboardButton("❓ Bantuan", callback_data="m:help")],
    ])

WELCOME = (
    "🛒 <b>Checkout Bot</b>\n"
    "Belanja otomatis Shopee / Tokopedia / Website.\n\n"
    "Pilih menu di bawah 👇 (tanpa perlu ketik perintah)."
)

async def show_menu(target, edit=False):
    if edit:
        await target.edit_message_text(WELCOME, reply_markup=main_menu(), parse_mode=ParseMode.HTML)
    else:
        await target.reply_text(WELCOME, reply_markup=main_menu(), parse_mode=ParseMode.HTML)

async def start(update: Update, ctx):
    if not await guard(update): return
    ctx.user_data.clear()
    await show_menu(update.message)

# ---------------- router tombol ----------------
async def on_button(update: Update, ctx):
    if not await guard(update): return
    q = update.callback_query; await q.answer()
    data = q.data
    # --- menu utama ---
    if data == "m:add":
        ctx.user_data["await"] = "product_link"
        await q.edit_message_text("📎 Kirim <b>link produk</b> yang ingin dibeli:",
                                  parse_mode=ParseMode.HTML,
                                  reply_markup=back_btn())
    elif data == "m:list":
        await list_tasks_cb(q)
    elif data == "m:login":
        await q.edit_message_text(
            "🔑 <b>Login Akun</b>\n\n"
            "🍪 <b>Login via Cookie</b> (disarankan, lolos anti-bot Shopee)\n"
            "🌐 <b>Login Manual</b> (buka browser di laptop)",
            parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🍪 Login via Cookie", callback_data="loginc:menu")],
            [InlineKeyboardButton("🌐 Login Manual (browser)", callback_data="loginm:menu")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="m:home")],
        ]))
    elif data == "loginm:menu":
        await q.edit_message_text("🌐 Pilih platform (browser akan terbuka di laptop):",
            reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟠 Shopee", callback_data="login:shopee"),
             InlineKeyboardButton("🟢 Tokopedia", callback_data="login:tokopedia")],
            [InlineKeyboardButton("🌐 Website", callback_data="login:generic")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="m:home")],
        ]))
    elif data == "loginc:menu":
        await q.edit_message_text("🍪 Login via Cookie - pilih platform:",
            reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟠 Shopee", callback_data="loginc:shopee"),
             InlineKeyboardButton("🟢 Tokopedia", callback_data="loginc:tokopedia")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="m:home")],
        ]))
    elif data.startswith("loginc:") and data.split(":")[1] in ("shopee","tokopedia"):
        platform = data.split(":")[1]
        ctx.user_data["await"] = "cookie_paste"
        ctx.user_data["cookie_platform"] = platform
        domain = ".shopee.co.id" if platform=="shopee" else ".tokopedia.com"
        await q.edit_message_text(
            f"🍪 <b>Login Cookie {PLATFORM_LABEL[platform]}</b>\n\n"
            f"1. Login ke {platform} di Chrome HP/laptop sampai masuk\n"
            f"2. Install extension <b>Cookie-Editor</b>\n"
            f"3. Buka situs {platform}, klik Cookie-Editor → <b>Export</b> → <b>JSON</b>\n"
            f"4. <b>Paste hasilnya ke chat ini</b> 👇\n\n"
            f"(Pesanmu akan dihapus otomatis demi keamanan)",
            parse_mode=ParseMode.HTML, reply_markup=back_btn())
    elif data == "m:logout":
        await render_accounts(q, "logout")
    elif data == "m:pay":
        await render_accounts(q, "pay")
    elif data == "m:flash":
        ctx.user_data["await"] = "flash_link"
        await q.edit_message_text(
            "⚡ <b>Flash Sale Terjadwal</b>\nKirim <b>link produk</b> dulu:",
            parse_mode=ParseMode.HTML, reply_markup=back_btn())
    elif data == "m:help":
        await q.edit_message_text(HELP_TEXT, parse_mode=ParseMode.HTML, reply_markup=back_btn())
    elif data == "m:home":
        ctx.user_data.clear()
        await show_menu(q, edit=True)

    # --- login platform dipilih ---
    elif data.startswith("login:"):
        platform = data.split(":")[1]
        acc = "akun1"
        get_or_create_account(acc, platform)
        notifier = make_notifier(ctx.application, q.message.chat_id)
        await q.edit_message_text(f"🌐 Membuka browser untuk login {PLATFORM_LABEL[platform]} "
                                  f"(<code>{acc}</code>)...\nSilakan login manual di jendela browser.",
                                  parse_mode=ParseMode.HTML)
        plat = get_platform(platform, acc, None, notifier)
        ok = await plat.interactive_login()
        if ok:
            s = db(); a = s.query(Account).filter_by(name=acc).first()
            a.logged_in = True; s.commit(); s.close()
            await ctx.application.bot.send_message(q.message.chat_id,
                "✅ Login tersimpan & akan tetap aktif.", reply_markup=main_menu())
        else:
            await ctx.application.bot.send_message(q.message.chat_id,
                "⚠️ Login belum terdeteksi. Coba lagi.", reply_markup=main_menu())

    # --- pilih akun utk logout / pay ---
    elif data.startswith("acc:"):
        _, mode, acc = data.split(":")
        if mode == "logout":
            s = db(); a = s.query(Account).filter_by(name=acc).first()
            platform = a.platform if a else "generic"
            if a: a.logged_in = False; s.commit()
            s.close()
            get_platform(platform, acc).logout()
            await q.edit_message_text(f"🚪 Akun <code>{acc}</code> sudah logout.",
                                      parse_mode=ParseMode.HTML, reply_markup=back_btn())
        elif mode == "pay":
            ctx.user_data["pay_acc"] = acc
            await q.edit_message_text(f"💳 Pilih metode bayar untuk <code>{acc}</code>:",
                parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏦 VA BCA", callback_data=f"setpay:{acc}:va:BCA"),
                 InlineKeyboardButton("🏦 VA Mandiri", callback_data=f"setpay:{acc}:va:Mandiri")],
                [InlineKeyboardButton("🏦 VA BNI", callback_data=f"setpay:{acc}:va:BNI"),
                 InlineKeyboardButton("🏦 VA BRI", callback_data=f"setpay:{acc}:va:BRI")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="m:home")],
            ]))
    elif data.startswith("setpay:"):
        _, acc, method, bank = data.split(":")
        get_or_create_account(acc)
        s = db(); a = s.query(Account).filter_by(name=acc).first()
        a.pay_method = method; a.va_bank = bank; s.commit(); s.close()
        await q.edit_message_text(f"✅ Pembayaran <code>{acc}</code>: <b>{method.upper()} {bank}</b>\n"
                                  f"Dipakai otomatis tiap checkout.",
                                  parse_mode=ParseMode.HTML, reply_markup=back_btn())

    # --- wizard task ---
    elif data.startswith("qty:"):
        _, tid, val = data.split(":"); tid = int(tid)
        s = db(); t = s.get(Task, tid); t.qty = int(val); s.commit(); s.close()
        await q.edit_message_reply_markup(reply_markup=task_wizard(tid))
        await q.answer(f"Qty: {'MAX' if val=='0' else val}")
    elif data.startswith("mode:"):
        _, tid, val = data.split(":"); tid = int(tid)
        s = db(); t = s.get(Task, tid); t.mode = val; s.commit(); s.close()
        await q.edit_message_reply_markup(reply_markup=task_wizard(tid))
        await q.answer(f"Mode: {val}")
    elif data.startswith("run:"):
        tid = int(data.split(":")[1])
        await q.edit_message_text(f"🚀 Menjalankan task #{tid}...")
        await execute_task(ctx.application, q.message.chat_id, tid)

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="m:home")]])

def task_wizard(tid):
    s = db(); t = s.get(Task, tid); s.close()
    q_lbl = lambda v: ("✅ " if t.qty==v else "") + ("MAX" if v==0 else str(v))
    m_lbl = lambda v: ("✅ " if t.mode==v else "")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(q_lbl(1), callback_data=f"qty:{tid}:1"),
         InlineKeyboardButton(q_lbl(5), callback_data=f"qty:{tid}:5"),
         InlineKeyboardButton(q_lbl(0), callback_data=f"qty:{tid}:0")],
        [InlineKeyboardButton(m_lbl('instant')+"⚡ Instant", callback_data=f"mode:{tid}:instant"),
         InlineKeyboardButton(m_lbl('restock')+"🔄 Restock", callback_data=f"mode:{tid}:restock")],
        [InlineKeyboardButton("🚀 JALANKAN", callback_data=f"run:{tid}")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="m:home")],
    ])

async def render_accounts(q, mode):
    s = db(); accs = s.query(Account).all(); s.close()
    if not accs:
        await q.edit_message_text("Belum ada akun. Login dulu lewat 🔑 Login Akun.",
                                  reply_markup=back_btn()); return
    rows = [[InlineKeyboardButton(f"{PLATFORM_LABEL.get(a.platform,a.platform)} • {a.name}"
             + (" ✅" if a.logged_in else ""), callback_data=f"acc:{mode}:{a.name}")] for a in accs]
    rows.append([InlineKeyboardButton("⬅️ Kembali", callback_data="m:home")])
    title = "🚪 Pilih akun untuk logout:" if mode=="logout" else "💳 Pilih akun untuk atur bayar:"
    await q.edit_message_text(title, reply_markup=InlineKeyboardMarkup(rows))

# ---------------- input teks (link / jadwal) ----------------
async def on_text(update: Update, ctx):
    if not await guard(update): return
    state = ctx.user_data.get("await")
    text = update.message.text.strip()
    if state == "product_link":
        ctx.user_data.pop("await", None)
        platform = detect_platform(text)
        s = db(); t = Task(product_url=text, platform=platform, account_name="akun1",
                           qty=1, mode="instant"); s.add(t); s.commit(); tid=t.id; s.close()
        await update.message.reply_text(
            f"✅ Task #{tid} dibuat\n{PLATFORM_LABEL.get(platform)}\n\nAtur opsi:",
            reply_markup=task_wizard(tid))
    elif state == "flash_link":
        ctx.user_data["flash_link"] = text
        ctx.user_data["await"] = "flash_time"
        await update.message.reply_text(
            "🕒 Kirim <b>waktu sale</b> (format: <code>YYYY-MM-DD HH:MM:SS</code>)\n"
            "Contoh: <code>2026-07-01 20:00:00</code>", parse_mode=ParseMode.HTML)
    elif state == "flash_time":
        try:
            target = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            await update.message.reply_text("❌ Format salah. Contoh: 2026-07-01 20:00:00"); return
        url = ctx.user_data.pop("flash_link"); ctx.user_data.pop("await", None)
        platform = detect_platform(url); acc="akun1"
        s = db(); t = Task(product_url=url, platform=platform, account_name=acc,
                           mode="scheduled", run_at=target); s.add(t); s.commit(); tid=t.id; s.close()
        chat_id = update.effective_chat.id; epoch = target.timestamp()
        async def job():
            notifier = make_notifier(ctx.application, chat_id)
            plat = get_platform(platform, acc, None, notifier)
            await plat.run_flashsale(t, epoch)
        scheduler.schedule_flashsale(target, job, job_id=f"flash_{tid}", lead_sec=150)
        timesync.sync()
        await update.message.reply_text(
            f"⚡ <b>Flash Sale #{tid} dijadwalkan!</b>\n"
            f"{PLATFORM_LABEL.get(platform)}\n🕒 {text}\n"
            f"⏱ Presisi NTP (offset {timesync.offset*1000:.0f} ms)\n"
            f"Bot akan pre-warm & menembak otomatis.",
            parse_mode=ParseMode.HTML, reply_markup=main_menu())
    elif state == "cookie_paste":
        ctx.user_data.pop("await", None)
        platform = ctx.user_data.pop("cookie_platform", "shopee")
        cookie_text = text
        # hapus pesan cookie demi keamanan
        try:
            await update.message.delete()
        except Exception:
            pass
        acc = "akun1"
        get_or_create_account(acc, platform)
        status = await ctx.application.bot.send_message(update.effective_chat.id,
            f"🍪 Memproses cookie {PLATFORM_LABEL.get(platform)}...")
        plat = get_platform(platform, acc, None, None)
        ok, n, msg = await plat.login_with_cookies(cookie_text)
        if ok:
            s = db(); a = s.query(Account).filter_by(name=acc).first()
            a.logged_in = True; s.commit(); s.close()
        await ctx.application.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=status.message_id,
            text=(f"{'✅' if ok else '⚠️'} {msg}\n({n} cookie dimuat)"),
            reply_markup=main_menu())
    else:
        # teks acak -> tampilkan menu
        await show_menu(update.message)

# ---------------- eksekusi ----------------
async def execute_task(app, chat_id, tid):
    s = db(); t = s.get(Task, tid); s.close()
    notifier = make_notifier(app, chat_id)
    plat = get_platform(t.platform, t.account_name, None, notifier)
    if t.mode == "restock":
        await app.bot.send_message(chat_id, f"🔄 Monitor restock task #{tid} aktif...")
        await plat.run_restock(t)
    else:
        await plat.run(t)
    await app.bot.send_message(chat_id, "Selesai.", reply_markup=main_menu())

async def list_tasks_cb(q):
    s = db(); rows = s.query(Task).all(); s.close()
    if not rows:
        await q.edit_message_text("📋 Belum ada task.", reply_markup=back_btn()); return
    lines = ["📋 <b>Daftar Task</b>\n"]
    for t in rows:
        emo = {"success":"✅","failed":"❌","pending":"⏳","running":"🔄"}.get(t.status,"•")
        lines.append(f"{emo} <b>#{t.id}</b> {PLATFORM_LABEL.get(t.platform,t.platform)} "
                     f"qty={'MAX' if t.qty==0 else t.qty} • {t.mode} • {t.status}")
    await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_btn())

HELP_TEXT = (
    "❓ <b>Cara Pakai</b>\n\n"
    "1️⃣ <b>Login Akun</b> – login sekali, tetap aktif\n"
    "2️⃣ <b>Atur Pembayaran</b> – pilih VA bank default\n"
    "3️⃣ <b>Tambah Produk</b> – tempel link, pilih qty & mode\n"
    "    • ⚡ Instant: beli sekarang\n"
    "    • 🔄 Restock: tunggu barang ada lalu auto-beli\n"
    "4️⃣ <b>Flash Sale</b> – jadwalkan beli tepat waktu (presisi NTP)\n\n"
    "Bot berhenti di halaman VA → kamu bayar manual. 💳"
)

# ---------------- commands fallback ----------------
async def menu_cmd(update: Update, ctx):
    if not await guard(update): return
    await show_menu(update.message)


async def on_error(update, ctx):
    log.error(f"Update error: {ctx.error}")

def build_app():
    init_db()
    scheduler.start()
    app = (ApplicationBuilder()
           .token(TELEGRAM_BOT_TOKEN)
           .connect_timeout(30)
           .read_timeout(30)
           .write_timeout(30)
           .pool_timeout(30)
           .get_updates_read_timeout(45)
           .build())
    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app