"""Celery worker 同步会话。Web 层禁止 import。"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

sync_engine = create_engine(get_settings().sync_database_url, pool_pre_ping=True, pool_recycle=3600)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


def get_sync_session() -> Session:
    return SyncSessionLocal()
