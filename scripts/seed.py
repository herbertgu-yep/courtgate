"""演示种子数据：1 场馆、12 场地、14 时段、管理员与顾客、1 个已开放批次。

运行：python -m scripts.seed
"""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models import Court, TimeSlot, User, Venue


async def main() -> None:
    async with AsyncSessionLocal() as s:
        # 管理员与顾客（用户名 + 强密码，与线上规则一致）
        if await s.scalar(select(User).where(User.username == "admin")) is None:
            s.add(
                User(
                    username="admin",
                    password_hash=hash_password("Admin@123456"),
                    nickname="场馆管理员",
                    role="operator",
                )
            )
            for i in range(5):
                s.add(
                    User(
                        username=f"user{i + 1}",
                        password_hash=hash_password("User@123456"),
                        nickname=f"测试用户 {i + 1}",
                    )
                )
            await s.commit()

        # 场馆与场地
        venue = await s.scalar(select(Venue).where(Venue.name == "星羽羽毛球馆"))
        if venue is None:
            venue = Venue(
                name="星羽羽毛球馆",
                address="高新区体育路 1 号",
                phone="0571-88880000",
                open_time="08:00",
                close_time="22:00",
                notice="预约后 15 分钟内完成支付，开场前 2 小时可免费取消",
            )
            s.add(venue)
            await s.commit()
            await s.refresh(venue)

        if await s.scalar(select(Court).where(Court.venue_id == venue.id)) is None:
            for i in range(12):
                s.add(Court(venue_id=venue.id, name=f"{i + 1} 号场", court_type="wood", base_price_cents=3000))
            await s.commit()

        # 会员等级（幂等）
        from app.models import MemberLevel

        for code, name, spent, disc, rate, sort in [
            ("normal", "普通会员", 0, 10000, 10000, 0),
            ("silver", "银卡会员", 10000, 9500, 12000, 1),
            ("gold", "金卡会员", 50000, 9000, 15000, 2),
        ]:
            if await s.scalar(select(MemberLevel).where(MemberLevel.code == code)) is None:
                s.add(
                    MemberLevel(
                        code=code,
                        name=name,
                        min_spent_cents=spent,
                        discount_bp=disc,
                        points_rate_bp=rate,
                        sort_order=sort,
                    )
                )
            await s.commit()

        # 全局时段模板（幂等）
        for i in range(14):
            start = 8 + i
            ratio = 15000 if 18 <= start < 22 else 10000
            if await s.scalar(select(TimeSlot).where(TimeSlot.start_time == f"{start:02d}:00")) is None:
                s.add(
                    TimeSlot(
                        start_time=f"{start:02d}:00",
                        end_time=f"{start + 1:02d}:00",
                        label=f"{start:02d}:00-{start + 1:02d}:00",
                        price_ratio_bp=ratio,
                        sort_order=i,
                    )
                )
            await s.commit()

        # 示例券模板（幂等）
        from app.models import CouponTemplate

        if await s.scalar(select(CouponTemplate).where(CouponTemplate.name == "新客立减 10 元")) is None:
            now = dt.datetime.now(dt.UTC)
            s.add(
                CouponTemplate(
                    name="新客立减 10 元",
                    type="fixed",
                    value=1000,
                    min_spend_cents=0,
                    total_quantity=100,
                    per_user_limit=1,
                    valid_from=now - dt.timedelta(hours=1),
                    valid_to=now + dt.timedelta(days=90),
                )
            )
            await s.commit()

        print("种子完成：管理员 admin / Admin@123456，顾客 user1~5 / User@123456")
        print("会员等级 normal/silver/gold 已配置；示例券「新客立减 10 元」已就绪")
        print("下一步：用管理员登录调 POST /api/admin/releases 放场（周期、开抢时刻任配）")
    from app.db.session import engine

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
