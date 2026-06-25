from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
from utils.logger import get_logger

log = get_logger()
scheduler = AsyncIOScheduler()

def start():
    if not scheduler.running:
        scheduler.start()
        log.info("Scheduler started")

def schedule_at(run_dt: datetime, coro_func, args=None, job_id=None):
    return scheduler.add_job(coro_func, DateTrigger(run_date=run_dt), args=args or [], id=job_id, replace_existing=True)

def schedule_restock_poll(coro_func, args=None, interval_sec=10, job_id=None):
    return scheduler.add_job(coro_func, "interval", seconds=interval_sec, args=args or [], id=job_id, replace_existing=True)

def schedule_flashsale(target_dt: datetime, coro_func, args=None, job_id=None, lead_sec=150):
    """Trigger handler flash-sale lebih awal (lead_sec) supaya sempat pre-warm
    & NTP sync. Presisi tembakan ditangani di FlashSaleRunner pakai target_epoch."""
    fire_at = target_dt - timedelta(seconds=lead_sec)
    if fire_at < datetime.now():
        fire_at = datetime.now() + timedelta(seconds=1)
    return scheduler.add_job(coro_func, DateTrigger(run_date=fire_at), args=args or [], id=job_id, replace_existing=True)

def cancel(job_id):
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
