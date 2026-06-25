import os, json
from cryptography.fernet import Fernet
from config.settings import SESSIONS_DIR, SESSION_ENCRYPTION_KEY

os.makedirs(SESSIONS_DIR, exist_ok=True)
_f = Fernet(SESSION_ENCRYPTION_KEY.encode()) if SESSION_ENCRYPTION_KEY else None

def _path(account):
    return os.path.join(SESSIONS_DIR, f"{account}.session")

def save_state(account, storage_state: dict):
    raw = json.dumps(storage_state).encode()
    data = _f.encrypt(raw) if _f else raw
    with open(_path(account), "wb") as fh:
        fh.write(data)

def load_state(account):
    p = _path(account)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as fh:
        data = fh.read()
    raw = _f.decrypt(data) if _f else data
    return json.loads(raw.decode())

def has_session(account):
    return os.path.exists(_path(account))
