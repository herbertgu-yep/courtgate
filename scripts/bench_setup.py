"""压测准备：批量生成压测用户并导出 token 列表。运行：python -m scripts.bench_setup [N]"""

from __future__ import annotations

import asyncio
import json
import sys

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.models import User


async def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    async with AsyncSessionLocal() as s:
        made = 0
        for i in range(n):
            username = f"bench{i}"
            if await s.scalar(select(User).where(User.username == username)) is None:
                s.add(User(username=username, password_hash=hash_password("Bench@1234"), nickname=f"bench{i}"))
                made += 1
        await s.commit()
        rows = (await s.scalars(select(User).where(User.username.like("bench%")))).all()
    tokens = [{"username": u.username, "user_id": u.id, "token": create_access_token(u.id)} for u in rows]
    print(f"新增 {made} 个压测用户，共 {len(tokens)} 个可用")
    from app.db.session import engine

    await engine.dispose()
    return tokens


if __name__ == "__main__":
    tokens = asyncio.run(main())
    with open("/tmp/bench_tokens.json", "w", encoding="utf-8") as f:
        json.dump(tokens, f)
