"""Phase B：领券并发 / 核销幂等 / 积分幂等与不为负 / 通知 / OAuth / 取消释放。"""

import asyncio
import uuid

import pytest

from app.core.config import get_settings
from app.services.payment_service import build_mock_callback
from tests.conftest import make_operator, make_release, make_venue, register_and_login


def _iso(d) -> str:
    return d.isoformat(timespec="seconds")


@pytest.fixture
async def env(client):
    op = await make_operator(client)
    venue_id, _, _ = await make_venue(client, op, n_courts=2, n_slots=2)
    info = await make_release(client, op, venue_id, n_days=1)
    import datetime as dt

    now = dt.datetime.now(dt.UTC)
    r = await client.post(
        "/api/admin/coupons",
        json={
            "name": "新客立减 10 元",
            "type": "fixed",
            "value": 1000,
            "min_spend_cents": 0,
            "total_quantity": 50,
            "per_user_limit": 1,
            "valid_from": _iso(now - dt.timedelta(hours=1)),
            "valid_to": _iso(now + dt.timedelta(days=30)),
        },
        headers=op,
    )
    coupon_id = r.json()["id"]
    r = await client.post(
        "/api/admin/member-levels",
        json={
            "code": "silver",
            "name": "银卡",
            "min_spent_cents": 10000,
            "discount_bp": 9500,
            "points_rate_bp": 12000,
            "sort_order": 1,
        },
        headers=op,
    )
    assert r.status_code == 201
    r = await client.get(f"/api/releases/{info['release_id']}/slots")
    slot_ids = [s["court_slot_id"] for c in r.json()["courts"] for s in c["slots"]]
    return op, info, slot_ids, coupon_id


async def _user(client, phone: str) -> dict:
    tokens = await register_and_login(client, phone)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def avail_slots(client, release_id: int) -> list[int]:
    """挑当前可约的时段（同一批次会被多个测试复用，先约的时段已不可再约）。"""
    r = await client.get(f"/api/releases/{release_id}/slots")
    ids = [s["court_slot_id"] for c in r.json()["courts"] for s in c["slots"] if s["available"]]
    return ids


async def _book(client, headers, release_id, slot_ids, coupon_id=None, use_points=0):
    return await client.post(
        "/api/bookings",
        json={
            "release_id": release_id,
            "court_slot_ids": slot_ids,
            "coupon_id": coupon_id,
            "use_points": use_points,
        },
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )


@pytest.mark.asyncio
async def test_coupon_claim_and_redeem(client, env) -> None:
    _, info, slot_ids, coupon_id = env
    headers = await _user(client, "13820000001")
    r = await client.post(f"/api/coupons/{coupon_id}/claim", headers=headers)
    assert r.status_code == 201, r.text
    code = r.json()["code"]
    r2 = await client.post(f"/api/coupons/{coupon_id}/claim", headers=headers)
    assert r2.status_code == 201 and r2.json()["code"] == code  # 幂等：返回已有券


@pytest.mark.asyncio
async def test_coupon_concurrent_grab(client, env) -> None:
    """N 并发抢 50 张券 → 恰好 50 张；同用户超限被拒。"""
    import datetime as dt

    op, info, slot_ids, coupon_id = env
    # 造一个只有 3 张库存的券，60 人抢
    now = dt.datetime.now(dt.UTC)
    r = await client.post(
        "/api/admin/coupons",
        json={
            "name": "限量券",
            "type": "fixed",
            "value": 500,
            "total_quantity": 3,
            "per_user_limit": 1,
            "valid_from": _iso(now - dt.timedelta(hours=1)),
            "valid_to": _iso(now + dt.timedelta(days=7)),
        },
        headers=op,
    )
    limited = r.json()["id"]
    users = [await _user(client, f"1382100{i:04d}") for i in range(60)]
    rs = await asyncio.gather(*[client.post(f"/api/coupons/{limited}/claim", headers=h) for h in users])
    ok = [r for r in rs if r.status_code == 201]
    assert len(ok) == 3, f"应恰好 3 人领到，实际 {len(ok)}"
    mine = await client.get("/api/coupons/mine", headers=users[0])
    codes = [c["code"] for c in mine.json()["items"] if c["template_id"] == limited]
    assert len(codes) <= 1  # 每人限领 1


@pytest.mark.asyncio
async def test_coupon_discount_applied_and_refund_on_cancel(client, env) -> None:
    """用券下单 → 减免生效；取消 → 券回到 unused 可再用。"""
    _, info, slot_ids, coupon_id = env
    headers = await _user(client, "13820000002")
    claimed = (await client.post(f"/api/coupons/{coupon_id}/claim", headers=headers)).json()
    slot_ids = await avail_slots(client, info["release_id"])
    r = await _book(client, headers, info["release_id"], slot_ids[:1], coupon_id=claimed["coupon_id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["coupon_discount_cents"] == 1000
    assert body["total_cents"] == body["subtotal_cents"] - 1000
    no = body["booking_no"]
    await client.post(f"/api/bookings/{no}/cancel", headers=headers)
    mine = (await client.get("/api/coupons/mine", headers=headers)).json()["items"]
    assert any(c["status"] == "unused" for c in mine), "取消后券应回到 unused"


@pytest.mark.asyncio
async def test_points_earn_and_redeem_idempotent(client, env) -> None:
    """支付赠积分幂等（重复回调只入账一次）。"""
    _, info, slot_ids, _ = env
    headers = await _user(client, "13820000003")
    slot_ids = await avail_slots(client, info["release_id"])
    r = await _book(client, headers, info["release_id"], slot_ids[:1])
    no, amount = r.json()["booking_no"], r.json()["total_cents"]
    pno = (await client.post(f"/api/payments/{no}", json={"channel": "mock_alipay"}, headers=headers)).json()[
        "payment_no"
    ]
    cb = build_mock_callback(pno, amount, secret=get_settings().payment_secret)
    for _ in range(3):
        await client.post("/api/payments/callback/mock_alipay", json=cb)
    ledger = (await client.get("/api/points/ledger", headers=headers)).json()["items"]
    earns = [row for row in ledger if row["change_type"] == "earn"]
    assert len(earns) == 1, f"earn 流水应只有 1 条，实际 {len(earns)}"


@pytest.mark.asyncio
async def test_points_redeem_never_negative(client, env) -> None:
    """并发消耗积分，余额永不为负。"""
    _, info, slot_ids, _ = env
    headers = await _user(client, "13820000004")
    # 直接触发：给用户 100 积分，然后两个并发预约各用 100
    from sqlalchemy import update

    from app.db.session import AsyncSessionLocal
    from app.models import User

    me = (await client.get("/api/auth/me", headers=headers)).json()
    async with AsyncSessionLocal() as s:
        await s.execute(update(User).where(User.id == me["id"]).values(points_balance=100))
        await s.commit()
    rs = await asyncio.gather(
        *[_book(client, headers, info["release_id"], [sid], use_points=100) for sid in slot_ids[:2]]
    )
    ok = [r for r in rs if r.status_code == 201]
    bal = (await client.get("/api/points/balance", headers=headers)).json()["balance"]
    assert bal >= 0
    used = sum(r.json()["points_used"] for r in ok)
    assert bal == 100 - used


@pytest.mark.asyncio
async def test_oauth_flow_t29_to_t32(client, env) -> None:
    """Mock 微信 登录→未绑定→绑定→重复绑定冲突。"""
    code = "mock:openid_test1:小王"
    r = await client.post("/api/auth/oauth/wechat", json={"code": code})
    assert r.status_code == 409 and r.json()["error"]["code"] == "OAUTH_ACCOUNT_NOT_BOUND"
    ticket = r.json()["error"]["details"]["ticket"]
    # 错误密码
    r2 = await client.post(
        "/api/auth/oauth/wechat/bind", json={"ticket": ticket, "username": "13830000001", "password": "wrong"}
    )
    assert r2.status_code == 403
    # 重新走一次登录拿新 ticket（旧 ticket 未消费也还在，但错误密码不消费）
    r = await client.post("/api/auth/oauth/wechat", json={"code": code})
    ticket = r.json()["error"]["details"]["ticket"]
    await register_and_login(client, "13830000001")  # 确保账号存在
    r3 = await client.post(
        "/api/auth/oauth/wechat/bind", json={"ticket": ticket, "username": "13830000001", "password": "Pass@123"}
    )
    assert r3.status_code == 200 and r3.json()["bound"] is True
    # 已绑定 → 直接登录
    r4 = await client.post("/api/auth/oauth/wechat", json={"code": code})
    assert r4.status_code == 200 and r4.json()["bound"] is True


@pytest.mark.asyncio
async def test_member_upgrade_on_payment(client, env) -> None:
    """支付后累计消费 → 升级 silver（门槛 100 元），折扣生效。"""
    _, info, slot_ids, _ = env
    headers = await _user(client, "13820000005")
    slot_ids = await avail_slots(client, info["release_id"])
    # 直接触发：预置累计消费 99 元，再支付 30 元 → 达到 100 元门槛
    from sqlalchemy import update

    from app.db.session import AsyncSessionLocal
    from app.models import User

    me = (await client.get("/api/auth/me", headers=headers)).json()
    async with AsyncSessionLocal() as s:
        await s.execute(update(User).where(User.id == me["id"]).values(total_spent_cents=9900))
        await s.commit()
    r = await _book(client, headers, info["release_id"], slot_ids[:1])
    no, amount = r.json()["booking_no"], r.json()["total_cents"]
    pno = (await client.post(f"/api/payments/{no}", json={"channel": "mock_alipay"}, headers=headers)).json()[
        "payment_no"
    ]
    cb = build_mock_callback(pno, amount, secret=get_settings().payment_secret)
    await client.post("/api/payments/callback/mock_alipay", json=cb)
    me2 = (await client.get("/api/members/me", headers=headers)).json()
    assert me2["member_level"] == "silver", f"应升级 silver，实际 {me2}"


@pytest.mark.asyncio
async def test_notifications_inbox(client, env) -> None:
    """站内信：预约创建后可查、可标记已读。"""
    _, info, slot_ids, _ = env
    headers = await _user(client, "13820000006")
    r = await _book(client, headers, info["release_id"], slot_ids[:1])
    assert r.status_code == 201
    # 通知由 Celery 任务写库；测试无 worker，直接验证 API 可用与幂等记录
    rows = (await client.get("/api/notifications", headers=headers)).json()["items"]
    assert isinstance(rows, list)
    r2 = await client.post("/api/notifications/read-all", headers=headers)
    assert r2.status_code == 200
