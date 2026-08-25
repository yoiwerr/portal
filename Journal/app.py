from __future__ import annotations
import hashlib, os, secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from pydantic import BaseModel, Field, field_validator
BASE_DIR=Path(__file__).resolve().parent; STATIC_DIR=BASE_DIR/"static"; DATABASE_URL=os.environ.get("JOURNAL_DATABASE_URL","")
if not DATABASE_URL: raise RuntimeError("JOURNAL_DATABASE_URL is required; SQLite fallback is disabled")
engine=create_engine(DATABASE_URL,pool_pre_ping=True); SessionLocal=sessionmaker(bind=engine,expire_on_commit=False); ph=PasswordHasher(); COOKIE_NAME="journal_session"; COOKIE_MAX_AGE=604800
class Base(DeclarativeBase): pass
class User(Base):
 __tablename__="journal_users"; id:Mapped[int]=mapped_column(primary_key=True); username:Mapped[str]=mapped_column(String(80),unique=True,index=True); password_hash:Mapped[str]=mapped_column(String(512)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc)); entries:Mapped[list["Entry"]]=relationship(back_populates="user",cascade="all, delete-orphan"); sessions:Mapped[list["SessionToken"]]=relationship(back_populates="user",cascade="all, delete-orphan")
class Entry(Base):
 __tablename__="journal_entries"; id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[int]=mapped_column(ForeignKey("journal_users.id",ondelete="CASCADE"),index=True); title:Mapped[str]=mapped_column(String(120)); entry_date:Mapped[date]=mapped_column(Date); content:Mapped[str]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc)); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc)); user:Mapped[User]=relationship(back_populates="entries")
class SessionToken(Base):
 __tablename__="journal_sessions"; id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[int]=mapped_column(ForeignKey("journal_users.id",ondelete="CASCADE"),index=True); token_hash:Mapped[str]=mapped_column(String(64),unique=True,index=True); expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc)); user:Mapped[User]=relationship(back_populates="sessions")
@asynccontextmanager
async def lifespan(_:FastAPI): yield
app=FastAPI(title="Private Journal",docs_url=None,redoc_url=None,lifespan=lifespan); app.mount("/journal/assets",StaticFiles(directory=STATIC_DIR),name="journal-assets")
class LoginPayload(BaseModel): username:str=Field(max_length=80); password:str=Field(max_length=200)
class EntryPayload(BaseModel):
 title:str=Field(min_length=1,max_length=120); entry_date:str; content:str=Field(min_length=1,max_length=100000)
 @field_validator("title","content")
 @classmethod
 def strip(cls,v): v=v.strip(); return v or (_ for _ in ()).throw(ValueError("不能为空"))
 @field_validator("entry_date")
 @classmethod
 def valid_date(cls,v): date.fromisoformat(v); return v
def th(t): return hashlib.sha256(t.encode()).hexdigest()
def current_user(token):
 if not token:return None
 with SessionLocal() as db:
  s=db.scalar(select(SessionToken).where(SessionToken.token_hash==th(token)))
  if not s or s.expires_at<=datetime.now(timezone.utc):
   if s: db.delete(s); db.commit()
   return None
  return db.get(User,s.user_id)
def require_session(c:Annotated[str|None,Cookie(alias=COOKIE_NAME)]=None):
 u=current_user(c)
 if u is None: raise HTTPException(401,"请先登录")
 return u
def require_marker(h:Annotated[str|None,Header(alias="X-Journal-Request")]=None):
 if h!="1": raise HTTPException(403,"请求无效")
def ser(e): return {"id":e.id,"title":e.title,"entry_date":e.entry_date.isoformat(),"content":e.content,"created_at":e.created_at.isoformat(),"updated_at":e.updated_at.isoformat()}
@app.get("/journal/health")
def health():
 with engine.connect() as c:c.exec_driver_sql("SELECT 1")
 return {"status":"ok"}
@app.get("/journal")
def redirect(): return RedirectResponse("/journal/",308)
@app.get("/journal/")
def page(c:Annotated[str|None,Cookie(alias=COOKIE_NAME)]=None): return FileResponse(STATIC_DIR/"journal.html") if current_user(c) else RedirectResponse("/journal/login",303)
@app.get("/journal/login")
def login_page(c:Annotated[str|None,Cookie(alias=COOKIE_NAME)]=None): return RedirectResponse("/journal/",303) if current_user(c) else FileResponse(STATIC_DIR/"login.html")
@app.post("/journal/api/login")
def login(p:LoginPayload,r:Response):
 with SessionLocal() as db:
  u=db.scalar(select(User).where(User.username==p.username)); ok=False
  if u:
   try: ok=ph.verify(u.password_hash,p.password)
   except (VerifyMismatchError,VerificationError,InvalidHashError): pass
  if not ok: raise HTTPException(401,"账号或密码错误")
  token=secrets.token_urlsafe(32); db.add(SessionToken(user_id=u.id,token_hash=th(token),expires_at=datetime.now(timezone.utc)+timedelta(seconds=COOKIE_MAX_AGE))); db.commit()
 r.set_cookie(COOKIE_NAME,token,max_age=COOKIE_MAX_AGE,httponly=True,secure=True,samesite="strict",path="/journal"); return {"ok":True}
@app.post("/journal/api/logout",dependencies=[Depends(require_session),Depends(require_marker)])
def logout(r:Response,c:Annotated[str|None,Cookie(alias=COOKIE_NAME)]=None):
 if c:
  with SessionLocal() as db: db.query(SessionToken).filter_by(token_hash=th(c)).delete(); db.commit()
 r.delete_cookie(COOKIE_NAME,path="/journal",secure=True,httponly=True,samesite="strict"); return {"ok":True}
@app.get("/journal/api/entries")
def entries(u:User=Depends(require_session)):
 with SessionLocal() as db:return [ser(e) for e in db.scalars(select(Entry).where(Entry.user_id==u.id).order_by(Entry.entry_date.desc(),Entry.id.desc())).all()]
@app.post("/journal/api/entries",status_code=201,dependencies=[Depends(require_marker)])
def create(p:EntryPayload,u:User=Depends(require_session)):
 with SessionLocal() as db:
  e=Entry(user_id=u.id,title=p.title,entry_date=date.fromisoformat(p.entry_date),content=p.content); db.add(e); db.commit(); db.refresh(e); return ser(e)
@app.put("/journal/api/entries/{eid}",dependencies=[Depends(require_marker)])
def update(eid:int,p:EntryPayload,u:User=Depends(require_session)):
 with SessionLocal() as db:
  e=db.scalar(select(Entry).where(Entry.id==eid,Entry.user_id==u.id))
  if not e: raise HTTPException(404,"日志不存在")
  e.title,e.entry_date,e.content=p.title,date.fromisoformat(p.entry_date),p.content; e.updated_at=datetime.now(timezone.utc); db.commit(); db.refresh(e); return ser(e)
@app.delete("/journal/api/entries/{eid}",status_code=204,dependencies=[Depends(require_marker)])
def delete(eid:int,u:User=Depends(require_session)):
 with SessionLocal() as db:
  e=db.scalar(select(Entry).where(Entry.id==eid,Entry.user_id==u.id))
  if not e: raise HTTPException(404,"日志不存在")
  db.delete(e); db.commit()
 return Response(status_code=204)
