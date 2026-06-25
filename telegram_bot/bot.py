from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler,
                          CallbackQueryHandler, ContextTypes)
import io
from datetime import datetime
from core import scheduler
from core.flashsale import FlashSaleRunner
from utils.timesync import timesync

from config.settings import TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS
from database.models import init_db, db, Task, Account, get_or_create_account
from platforms import detect_platform, get_platform
from utils.logger import get_logger

log = get_logger()

def authorized(uid):
    return (not ALLOWED_USER_IDS) or (uid in ALLOWED_USER_IDS)

async def guard(update: Update):
    if not authorized(update.effective_user.id):
        await update.message.reply_text("Akses ditolak."); return False
    return True

def make_notifier(app, chat_id):
    async def notifier(text, screenshot=None):
        await app.bot.send_message(chat_id=chat_id, text=text[:4000])
        if screenshot:
            await app.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(screenshot))
    return notifier

async def start(update: Update, ctx):
    if not await guard(update): return
    await update.message.reply_text(
        "Bot Checkout siap.\n\n"
        "PERTAMA KALI:\n"
        "/login <akun> <platform>  - login sekali (browser terbuka), lalu STAY login\n"
        "  contoh: /login akun1 shopee\n"
        "/setpayment <akun> <va|ewallet> <bank>  - setting bayar di awal\n"
        "  contoh: /setpayment akun1 va BCA\n\n"
        "PAKAI:\n"
        "/addproduct <link>  - tambah task + wizard tombol\n"
        "/list  - daftar task\n"
        "/run <id>  - jalankan\n"
        "/logout <akun>  - hapus login akun"
    )

async def login(update: Update, ctx):
    if not await guard(update): return
    if len(ctx.args) < 2:
        await update.message.reply_text("Pakai: /login <akun> <shopee|tokopedia|generic>"); return
    acc_name, platform = ctx.args[0], ctx.args[1]
    get_or_create_account(acc_name, platform)
    notifier = make_notifier(ctx.application, update.effective_chat.id)
    plat = get_platform(platform, acc_name, None, notifier)
    await update.message.reply_text(f"Membuka browser utk login {platform} ({acc_name})...")
    ok = await plat.interactive_login()
    if ok:
        s = db(); a = s.query(Account).filter_by(name=acc_name).first()
        a.logged_in = True; s.commit(); s.close()

async def logout(update: Update, ctx):
    if not await guard(update): return
    acc_name = ctx.args[0] if ctx.args else "akun1"
    s = db(); a = s.query(Account).filter_by(name=acc_name).first()
    platform = a.platform if a else "generic"
    if a: a.logged_in = False; s.commit()
    s.close()
    get_platform(platform, acc_name).logout()
    await update.message.reply_text(f"Akun {acc_name} sudah logout (profil dihapus).")

async def setpayment(update: Update, ctx):
    if not await guard(update): return
    if len(ctx.args) < 2:
        await update.message.reply_text("Pakai: /setpayment <akun> <va|ewallet|cod> [bank]"); return
    acc_name, method = ctx.args[0], ctx.args[1]
    bank = ctx.args[2] if len(ctx.args) > 2 else "BCA"
    get_or_create_account(acc_name)
    s = db(); a = s.query(Account).filter_by(name=acc_name).first()
    a.pay_method = method; a.va_bank = bank; s.commit(); s.close()
    await update.message.reply_text(f"Setting bayar {acc_name}: {method} {bank} (dipakai default tiap checkout).")

async def addproduct(update: Update, ctx):
    if not await guard(update): return
    if not ctx.args:
        await update.message.reply_text("Pakai: /addproduct <link>"); return
    url = ctx.args[0]; platform = detect_platform(url)
    acc = ctx.args[1] if len(ctx.args) > 1 else "akun1"
    s = db(); t = Task(product_url=url, platform=platform, account_name=acc, qty=1, mode="instant")
    s.add(t); s.commit(); tid = t.id; s.close()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Qty 1", callback_data=f"qty:{tid}:1"),
         InlineKeyboardButton("Qty 5", callback_data=f"qty:{tid}:5"),
         InlineKeyboardButton("Max", callback_data=f"qty:{tid}:0")],
        [InlineKeyboardButton("Mode Instant", callback_data=f"mode:{tid}:instant"),
         InlineKeyboardButton("Restock Monitor", callback_data=f"mode:{tid}:restock")],
        [InlineKeyboardButton("Override VA BCA", callback_data=f"va:{tid}:BCA"),
         InlineKeyboardButton("Override VA Mandiri", callback_data=f"va:{tid}:Mandiri")],
        [InlineKeyboardButton("JALANKAN", callback_data=f"run:{tid}")],
    ])
    await update.message.reply_text(
        f"Task #{tid} (platform={platform}, akun={acc}).\n"
        f"Pembayaran default ikut /setpayment akun. Atur opsi lain:", reply_markup=kb)

async def on_button(update: Update, ctx):
    q = update.callback_query; await q.answer()
    parts = q.data.split(":"); action = parts[0]; tid = int(parts[1])
    s = db(); t = s.get(Task, tid)
    if not t:
        await q.edit_message_text("Task tidak ada."); s.close(); return
    if action == "qty":
        t.qty = int(parts[2]); s.commit()
        await q.edit_message_text(f"Qty: {'MAX' if t.qty==0 else t.qty} (task #{tid})")
    elif action == "va":
        t.va_bank = parts[2]; t.pay_method = "va"; s.commit()
        await q.edit_message_text(f"Override VA: {t.va_bank} (task #{tid})")
    elif action == "mode":
        t.mode = parts[2]; s.commit()
        await q.edit_message_text(f"Mode: {t.mode} (task #{tid})")
    elif action == "run":
        await q.edit_message_text(f"Menjalankan task #{tid}...")
        await execute_task(ctx.application, q.message.chat_id, tid)
    s.close()

async def execute_task(app, chat_id, tid):
    s = db(); t = s.get(Task, tid); s.close()
    notifier = make_notifier(app, chat_id)
    plat = get_platform(t.platform, t.account_name, None, notifier)
    if t.mode == "restock":
        await app.bot.send_message(chat_id, f"Monitor restock task #{tid} dimulai...")
        await plat.run_restock(t)
    else:
        await plat.run(t)

async def list_tasks(update: Update, ctx):
    if not await guard(update): return
    s = db(); rows = s.query(Task).all(); s.close()
    if not rows:
        await update.message.reply_text("Belum ada task."); return
    lines = [f"#{t.id} [{t.platform}/{t.account_name}] qty={t.qty} mode={t.mode} status={t.status}" for t in rows]
    await update.message.reply_text("\n".join(lines))

async def run_cmd(update: Update, ctx):
    if not await guard(update): return
    await execute_task(ctx.application, update.effective_chat.id, int(ctx.args[0]))


async def flashsale(update: Update, ctx):
    """/flashsale <link> <YYYY-MM-DD HH:MM:SS> [akun] [varian]
    Jadwalkan pembelian flash-sale presisi NTP."""
    if not await guard(update): return
    if len(ctx.args) < 3:
        await update.message.reply_text(
            "Pakai: /flashsale <link> <YYYY-MM-DD> <HH:MM:SS> [akun] [varian]\n"
            "Contoh: /flashsale https://shopee.co.id/xxx 2026-07-01 20:00:00 akun1 Merah,L")
        return
    url = ctx.args[0]
    dt_str = ctx.args[1] + " " + ctx.args[2]
    acc = ctx.args[3] if len(ctx.args) > 3 else "akun1"
    variant = ctx.args[4] if len(ctx.args) > 4 else None
    try:
        target_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        await update.message.reply_text("Format waktu salah. Pakai: YYYY-MM-DD HH:MM:SS"); return
    platform = detect_platform(url)
    s = db(); t = Task(product_url=url, platform=platform, account_name=acc,
                       variant=variant, mode="scheduled", run_at=target_dt)
    s.add(t); s.commit(); tid = t.id; s.close()

    target_epoch = target_dt.timestamp()
    chat_id = update.effective_chat.id
    async def job():
        notifier = make_notifier(ctx.application, chat_id)
        plat = get_platform(platform, acc, None, notifier)
        await plat.run_flashsale(t, target_epoch)

    scheduler.schedule_flashsale(target_dt, job, job_id=f"flash_{tid}", lead_sec=150)
    # tampilkan estimasi offset NTP
    timesync.sync()
    await update.message.reply_text(
        f"Flash-sale #{tid} dijadwalkan!\n"
        f"Produk: {platform}\nWaktu target: {dt_str}\n"
        f"Pre-warm mulai T-90s, hot-reload T-5s, tembak presisi di T0.\n"
        f"NTP offset saat ini: {timesync.offset*1000:.1f} ms\n"
        f"Pembayaran ikut /setpayment akun {acc}.")


def build_app():
    init_db()
    scheduler.start()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("setpayment", setpayment))
    app.add_handler(CommandHandler("flashsale", flashsale))
    app.add_handler(CommandHandler("addproduct", addproduct))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("run", run_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    return app