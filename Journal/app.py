from __future__ import annotations

import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Cookie, Depends, FastAPI, File, Header, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Date, DateTime, ForeignKey, LargeBinary, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_URL = os.environ.get("JOURNAL_DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("JOURNAL_DATABASE_URL is required; SQLite fallback is disabled")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
ph = PasswordHasher()
COOKIE_NAME = "journal_session"
COOKIE_MAX_AGE = 604800
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES_PER_ENTRY = 9


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "journal_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    entries: Mapped[list["Entry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["SessionToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Entry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("journal_users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    entry_date: Mapped[date] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    user: Mapped[User] = relationship(back_populates="entries")
    images: Mapped[list["EntryImage"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="EntryImage.id",
    )


class EntryImage(Base):
    __tablename__ = "journal_entry_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="CASCADE"), index=True
    )
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int]
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    entry: Mapped[Entry] = relationship(back_populates="images")


class SessionToken(Base):
    __tablename__ = "journal_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("journal_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    user: Mapped[User] = relationship(back_populates="sessions")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="Private Journal", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/journal/assets", StaticFiles(directory=STATIC_DIR), name="journal-assets")


class LoginPayload(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


class EntryPayload(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    entry_date: str
    content: str = Field(min_length=1, max_length=100000)

    @field_validator("title", "content")
    @classmethod
    def strip(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("entry_date")
    @classmethod
    def valid_date(cls, value):
        date.fromisoformat(value)
        return value


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(token):
    if not token:
        return None
    with SessionLocal() as db:
        session = db.scalar(
            select(SessionToken).where(SessionToken.token_hash == token_hash(token))
        )
        if not session or session.expires_at <= datetime.now(timezone.utc):
            if session:
                db.delete(session)
                db.commit()
            return None
        return db.get(User, session.user_id)


def require_session(
    cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
):
    user = current_user(cookie)
    if user is None:
        raise HTTPException(401, "请先登录")
    return user


def require_marker(
    header: Annotated[str | None, Header(alias="X-Journal-Request")] = None,
):
    if header != "1":
        raise HTTPException(403, "请求无效")


def serialize_entry(entry: Entry):
    return {
        "id": entry.id,
        "title": entry.title,
        "entry_date": entry.entry_date.isoformat(),
        "content": entry.content,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
        "images": [
            {
                "id": image.id,
                "filename": image.original_name,
                "url": f"/journal/api/images/{image.id}",
            }
            for image in entry.images
        ],
    }


def detect_image_type(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(415, "仅支持 JPEG、PNG、WebP 或 GIF 图片")


@app.get("/journal/health")
def health():
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    return {"status": "ok"}


@app.get("/journal")
def redirect():
    return RedirectResponse("/journal/", 308)


@app.get("/journal/")
def page(cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None):
    if current_user(cookie):
        return FileResponse(STATIC_DIR / "journal.html")
    return RedirectResponse("/journal/login", 303)


@app.get("/journal/login")
def login_page(cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None):
    if current_user(cookie):
        return RedirectResponse("/journal/", 303)
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/journal/api/login")
def login(payload: LoginPayload, response: Response):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == payload.username))
        valid = False
        if user:
            try:
                valid = ph.verify(user.password_hash, payload.password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                pass
        if not valid:
            raise HTTPException(401, "账号或密码错误")
        token = secrets.token_urlsafe(32)
        db.add(
            SessionToken(
                user_id=user.id,
                token_hash=token_hash(token),
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=COOKIE_MAX_AGE),
            )
        )
        db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/journal",
    )
    return {"ok": True}


@app.post(
    "/journal/api/logout",
    dependencies=[Depends(require_session), Depends(require_marker)],
)
def logout(
    response: Response,
    cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
):
    if cookie:
        with SessionLocal() as db:
            db.query(SessionToken).filter_by(token_hash=token_hash(cookie)).delete()
            db.commit()
    response.delete_cookie(
        COOKIE_NAME,
        path="/journal",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return {"ok": True}


@app.get("/journal/api/entries")
def entries(user: User = Depends(require_session)):
    with SessionLocal() as db:
        query = (
            select(Entry)
            .where(Entry.user_id == user.id)
            .order_by(Entry.created_at.desc(), Entry.id.desc())
        )
        return [serialize_entry(entry) for entry in db.scalars(query).unique().all()]


@app.post(
    "/journal/api/entries",
    status_code=201,
    dependencies=[Depends(require_marker)],
)
def create(payload: EntryPayload, user: User = Depends(require_session)):
    with SessionLocal() as db:
        entry = Entry(
            user_id=user.id,
            title=payload.title,
            entry_date=date.fromisoformat(payload.entry_date),
            content=payload.content,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return serialize_entry(entry)


@app.put(
    "/journal/api/entries/{entry_id}",
    dependencies=[Depends(require_marker)],
)
def update(
    entry_id: int,
    payload: EntryPayload,
    user: User = Depends(require_session),
):
    with SessionLocal() as db:
        entry = db.scalar(
            select(Entry).where(Entry.id == entry_id, Entry.user_id == user.id)
        )
        if not entry:
            raise HTTPException(404, "日志不存在")
        entry.title = payload.title
        entry.entry_date = date.fromisoformat(payload.entry_date)
        entry.content = payload.content
        entry.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(entry)
        return serialize_entry(entry)


@app.post(
    "/journal/api/entries/{entry_id}/images",
    status_code=201,
    dependencies=[Depends(require_marker)],
)
async def add_images(
    entry_id: int,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_session),
):
    with SessionLocal() as db:
        entry = db.scalar(
            select(Entry).where(Entry.id == entry_id, Entry.user_id == user.id)
        )
        if not entry:
            raise HTTPException(404, "日志不存在")
        if not files:
            raise HTTPException(400, "请选择图片")
        if len(entry.images) + len(files) > MAX_IMAGES_PER_ENTRY:
            raise HTTPException(400, f"每条动态最多 {MAX_IMAGES_PER_ENTRY} 张图片")

        prepared = []
        for upload in files:
            data = await upload.read(MAX_IMAGE_BYTES + 1)
            await upload.close()
            if not data:
                raise HTTPException(400, "图片文件为空")
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "单张图片不能超过 8 MB")
            content_type = detect_image_type(data)
            prepared.append((upload, data, content_type))

        try:
            for upload, data, content_type in prepared:
                db.add(
                    EntryImage(
                        entry_id=entry.id,
                        original_name=Path(upload.filename or "image").name[:255],
                        content_type=content_type,
                        size_bytes=len(data),
                        data=data,
                    )
                )
            entry.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(entry)
            return serialize_entry(entry)
        except Exception:
            db.rollback()
            raise


@app.get("/journal/api/images/{image_id}")
def image_file(image_id: int, user: User = Depends(require_session)):
    with SessionLocal() as db:
        image = db.scalar(
            select(EntryImage)
            .join(Entry, Entry.id == EntryImage.entry_id)
            .where(EntryImage.id == image_id, Entry.user_id == user.id)
        )
        if not image:
            raise HTTPException(404, "图片不存在")
        return Response(
            content=image.data,
            media_type=image.content_type,
            headers={
                "Cache-Control": "private, max-age=86400",
                "X-Content-Type-Options": "nosniff",
            },
        )


@app.delete(
    "/journal/api/images/{image_id}",
    status_code=204,
    dependencies=[Depends(require_marker)],
)
def delete_image(image_id: int, user: User = Depends(require_session)):
    with SessionLocal() as db:
        image = db.scalar(
            select(EntryImage)
            .join(Entry, Entry.id == EntryImage.entry_id)
            .where(EntryImage.id == image_id, Entry.user_id == user.id)
        )
        if not image:
            raise HTTPException(404, "图片不存在")
        entry = db.get(Entry, image.entry_id)
        db.delete(image)
        if entry:
            entry.updated_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=204)


@app.delete(
    "/journal/api/entries/{entry_id}",
    status_code=204,
    dependencies=[Depends(require_marker)],
)
def delete(entry_id: int, user: User = Depends(require_session)):
    with SessionLocal() as db:
        entry = db.scalar(
            select(Entry).where(Entry.id == entry_id, Entry.user_id == user.id)
        )
        if not entry:
            raise HTTPException(404, "日志不存在")
        db.delete(entry)
        db.commit()
    return Response(status_code=204)
