import ntplib, time
from utils.logger import get_logger

log = get_logger()

class TimeSync:
    """Sinkronisasi waktu presisi terhadap server NTP.
    Simpan offset (ntp_time - local_time). accurate_time() = local + offset.
    Refresh offset beberapa kali & ambil yang latensinya terkecil (paling akurat)."""

    def __init__(self, servers=None):
        self.servers = servers or ["time.google.com", "pool.ntp.org", "id.pool.ntp.org"]
        self.offset = 0.0
        self.last_sync = 0.0

    def sync(self, samples=4):
        best = None
        client = ntplib.NTPClient()
        for _ in range(samples):
            for srv in self.servers:
                try:
                    r = client.request(srv, version=3, timeout=2)
                    # delay = round-trip; makin kecil makin akurat
                    if best is None or r.delay < best[1]:
                        best = (r.offset, r.delay)
                except Exception as e:
                    log.debug(f"NTP {srv} gagal: {e}")
            time.sleep(0.1)
        if best:
            self.offset = best[0]
            self.last_sync = time.time()
            log.info(f"NTP sync OK offset={self.offset*1000:.1f}ms delay={best[1]*1000:.1f}ms")
        else:
            log.warning("Semua NTP gagal -> pakai jam lokal (offset=0)")
        return self.offset

    def now(self):
        return time.time() + self.offset

    def seconds_until(self, target_epoch):
        return target_epoch - self.now()

# instance global
timesync = TimeSync()
