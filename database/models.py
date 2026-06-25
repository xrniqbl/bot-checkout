from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from config.settings import DATABASE_URL

Base = declarative_base()
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine)

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)        # label akun, mis "akun1"
    platform = Column(String)                 # shopee/tokopedia/generic
    proxy = Column(String, nullable=True)
    logged_in = Column(Boolean, default=False)
    # --- Setting pembayaran DI AWAL (dipakai default tiap checkout) ---
    pay_method = Column(String, default="va") # va / ewallet / cod
    va_bank = Column(String, default="BCA")   # default bank VA
    active = Column(Boolean, default=True)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    product_url = Column(String)
    platform = Column(String)
    account_name = Column(String, default="akun1")
    qty = Column(Integer, default=1)          # 0 = max
    variant = Column(String, nullable=True)
    mode = Column(String, default="instant")  # instant/restock/scheduled
    run_at = Column(DateTime, nullable=True)
    poll_interval = Column(Integer, default=3)# detik, utk restock
    # pembayaran bisa override akun; jika kosong pakai setting akun
    pay_method = Column(String, nullable=True)
    va_bank = Column(String, nullable=True)
    max_price = Column(Integer, nullable=True)
    status = Column(String, default="pending")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(engine)

def db():
    return SessionLocal()

def get_or_create_account(name, platform="generic"):
    s = db()
    acc = s.query(Account).filter_by(name=name).first()
    if not acc:
        acc = Account(name=name, platform=platform)
        s.add(acc); s.commit()
    s.refresh(acc); s.close()
    return acc

def resolve_payment(task):
    """Tentukan metode bayar final: task override -> fallback ke setting akun."""
    s = db()
    acc = s.query(Account).filter_by(name=task.account_name).first()
    s.close()
    method = task.pay_method or (acc.pay_method if acc else "va")
    bank = task.va_bank or (acc.va_bank if acc else "BCA")
    return method, bank
