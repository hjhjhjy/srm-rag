"""SQLite 持久化（会话、消息、反馈）。SQLAlchemy ORM。"""
from __future__ import annotations

import datetime as dt
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

Base = declarative_base()
_engine = None
_Session = None


def get_engine():
    global _engine, _Session
    if _engine is None:
        Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{settings.sqlite_path}", future=True)
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine, future=True)
    return _engine


def get_session():
    get_engine()
    return _Session()


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String(64), primary_key=True)
    created_at = Column(DateTime, default=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))
    title = Column(String(255), default="")


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True)
    role = Column(String(16))
    content = Column(Text)
    citations = Column(Text, default="[]")  # JSON
    rating = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))

    def to_dict(self):
        try:
            cites = json.loads(self.citations or "[]")
        except Exception:  # noqa
            cites = []
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "citations": cites,
            "rating": self.rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Feedback(Base):
    __tablename__ = "feedbacks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True)
    message_id = Column(Integer, default=0)
    rating = Column(Integer, default=0)
    comment = Column(Text, default="")
    correct_answer = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True)
    hashed_password = Column(String(255), default="")
    role = Column(String(16), default="supplier")  # supplier | admin
    api_key = Column(String(128), default="", unique=True)
    created_at = Column(DateTime, default=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))

    def to_dict(self):
        return {"id": self.id, "username": self.username, "role": self.role}


def ensure_default_admin():
    """首次启动创建默认管理员账号（配置可改）。"""
    get_engine()
    with _Session() as s:
        if s.query(User).filter(User.username == settings.admin_username).first():
            return
        # 延迟导入避免循环依赖
        from app.core.security import hash_password

        u = User(
            username=settings.admin_username,
            hashed_password=hash_password(settings.admin_password),
            role="admin",
        )
        s.add(u)
        s.commit()
