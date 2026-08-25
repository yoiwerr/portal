import getpass, os
from sqlalchemy import select
from argon2 import PasswordHasher
from app import SessionLocal, User
username=os.getenv("JOURNAL_ADMIN_USERNAME","yoiwerr"); password=os.getenv("JOURNAL_ADMIN_PASSWORD") or getpass.getpass("Password for journal user: ")
if not password: raise SystemExit("password is required")
with SessionLocal() as db:
 user=db.scalar(select(User).where(User.username==username)); ph=PasswordHasher()
 if user: user.password_hash=ph.hash(password)
 else: db.add(User(username=username,password_hash=ph.hash(password)))
 db.commit()
print(f"journal user {username!r} is ready")
