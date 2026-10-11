"""Web 层异步会话。tasks 层禁止 import。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=int(os.environ.get("COURTGATE_DB_POOL_SIZE", "5")),
    max_overflow=int(os.environ.get("COURTGATE_DB_MAX_OVERFLOW", "10")),
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
