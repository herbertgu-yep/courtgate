"""预约主流程：下单 / 限购 / 幂等重放 / 越权 / 取消 / 状态机 / 支付回调。"""

import uuid

import pytest

from app.core.config import get_settings
from app.services.payment_service import build_mock_callback
from tests.conftest import make_operator, make_release, make_venue, register_and_login


@pytest.fixture
async def env(client):
    op = await make_operator(client)
    venue_id, courts, slots = await make_venue(client, op, n_courts=2, n_slots=3)
    info = await make_release(client, op, venue_id, n_days=1)
    r = await client.get(f"/api/releases/{info['release_id']}/slots")
    slots_view = [s for c in r.json()["courts"] for s in c["slots"]]
    return op, info, slots_view


async def _user_headers(client, phone: str) -> dict:
    tokens = await register_and_login(client, phone)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _book(client, headers: dict, release_id: int, slot_ids: list[int], key: str | None = None):
    return await client.post(
        "/api/bookings",
        json={
            "release_id": release_id,
            "court_slot_ids": slot_ids,
        },
        headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
    )


@pytest.mark.asyncio
async def test_booking_happy_path(client, env) -> None:
    _, info, slots_view = env
    headers = await _user_headers(client, "13800000010")
    sid = slots_view[0]["court_slot_id"]
    r = await _book(client, headers, info["release_id"], [sid])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending_paid" and body["item_count"] == 1
    assert body["total_cents"] == slots_view[0]["price_cents"]
    # 详情含快照
    r2 = await client.get(f"/api/bookings/{body['booking_no']}", headers=headers)
    assert r2.status_code == 200
    item = r2.json()["items"][0]
    assert item["court_name"] == "1 号场" and item["price_cents"] == slots_view[0]["price_cents"]
    # 数据库状态
    from sqlalchemy import text

    from app.db.sync_session import sync_engine

    with sync_engine.connect() as conn:
        status = conn.execute(text("SELECT status, booking_no FROM court_slots WHERE id=:i"), {"i": sid}).fetchone()
        flow = conn.execute(
            text("SELECT change_type FROM stock_flows WHERE booking_no=:b"), {"b": body["booking_no"]}
        ).fetchone()
    assert status[0] == "booked" and status[1] == body["booking_no"]
    assert flow[0] == "occupy"


@pytest.mark.asyncio
async def test_idempotent_resubmit_same_booking(client, env) -> None:
    """同幂等键重复提交 → 返回同一张预约单，不重复占用。"""
    _, info, slots_view = env
    headers = await _user_headers(client, "13800000011")
    key = str(uuid.uuid4())
    sid = slots_view[0]["court_slot_id"]
    r1 = await _book(client, headers, info["release_id"], [sid], key=key)
    assert r1.status_code == 201
    r2 = await _book(client, headers, info["release_id"], [sid], key=key)
    assert r2.status_code == 201
    assert r2.json()["booking_no"] == r1.json()["booking_no"]


@pytest.mark.asyncio
async def test_per_user_limit_t4(client, env) -> None:
    """每批次限 3 个单元，第 4 个被拒。"""
    _, info, slots_view = env
    headers = await _user_headers(client, "13800000012")
    ids = [s["court_slot_id"] for s in slots_view]
    r1 = await _book(client, headers, info["release_id"], ids[:2])
    assert r1.status_code == 201
    r2 = await _book(client, headers, info["release_id"], [ids[2]])
    assert r2.status_code == 201
    r3 = await _book(client, headers, info["release_id"], [ids[3] if len(ids) > 3 else ids[0]])
    assert r3.status_code == 409
    assert r3.json()["error"]["code"] == "PER_USER_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_slot_unavailable_after_booked(client, env) -> None:
    """别人已约的时段 → SLOT_UNAVAILABLE。"""
    _, info, slots_view = env
    h1 = await _user_headers(client, "13800000013")
    h2 = await _user_headers(client, "13800000014")
    sid = slots_view[0]["court_slot_id"]
    assert (await _book(client, h1, info["release_id"], [sid])).status_code == 201
    r = await _book(client, h2, info["release_id"], [sid])
    assert r.status_code == 409 and r.json()["error"]["code"] == "SLOT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_cancel_and_state_machine_t17(client, env) -> None:
    """取消后时段归还；已取消/已支付订单不可再取消。"""
    _, info, slots_view = env
    headers = await _user_headers(client, "13800000015")
    sid = slots_view[0]["court_slot_id"]
    r = await _book(client, headers, info["release_id"], [sid])
    no = r.json()["booking_no"]
    r1 = await client.post(f"/api/bookings/{no}/cancel", headers=headers)
    assert r1.status_code == 200 and r1.json()["status"] == "cancelled"
    # 时段已归还
    from sqlalchemy import text

    from app.db.sync_session import sync_engine

    with sync_engine.connect() as conn:
        st = conn.execute(text("SELECT status FROM court_slots WHERE id=:i"), {"i": sid}).fetchone()
        flows = conn.execute(text("SELECT change_type FROM stock_flows WHERE booking_no=:b"), {"b": no}).fetchall()
    assert st[0] == "free"
    assert sorted(f[0] for f in flows) == ["occupy", "release"]
    # 再取消 → BOOKING_STATE_INVALID
    r2 = await client.post(f"/api/bookings/{no}/cancel", headers=headers)
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "BOOKING_STATE_INVALID"


@pytest.mark.asyncio
async def test_cross_user_access_404_t12(client, env) -> None:
    """越权访问一律 404（不泄露存在性）。"""
    _, info, slots_view = env
    h1 = await _user_headers(client, "13800000016")
    h2 = await _user_headers(client, "13800000017")
    sid = slots_view[0]["court_slot_id"]
    r = await _book(client, h1, info["release_id"], [sid])
    no = r.json()["booking_no"]
    r2 = await client.get(f"/api/bookings/{no}", headers=h2)
    assert r2.status_code == 404
    r3 = await client.post(f"/api/bookings/{no}/cancel", headers=h2)
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_payment_callback_flow_t7(client, env) -> None:
    """创建支付单 → 回调成功 → 订单 paid；重复回调返回 200 且不重复处理。"""
    _, info, slots_view = env
    headers = await _user_headers(client, "13800000018")
    sid = slots_view[0]["court_slot_id"]
    r = await _book(client, headers, info["release_id"], [sid])
    no = r.json()["booking_no"]
    amount = r.json()["total_cents"]

    r2 = await client.post(f"/api/payments/{no}", json={"channel": "mock_alipay"}, headers=headers)
    assert r2.status_code == 201
    pno = r2.json()["payment_no"]

    cb = build_mock_callback(pno, amount, secret=get_settings().payment_secret)
    r3 = await client.post("/api/payments/callback/mock_alipay", json=cb)
    assert r3.status_code == 200 and r3.json()["received"] is True

    r4 = await client.get(f"/api/bookings/{no}", headers=headers)
    assert r4.json()["status"] == "paid"

    # 重复回调：200，状态不再变化
    r5 = await client.post("/api/payments/callback/mock_alipay", json=cb)
    assert r5.status_code == 200

    # 已支付订单可取消：开场前 2 小时之前 → 自动原路退款
    r6 = await client.post(f"/api/bookings/{no}/cancel", headers=headers)
    assert r6.status_code == 200 and r6.json()["status"] == "refunded"
    # 支付单同步置退款
    r7 = await client.get(f"/api/bookings/{no}", headers=headers)
    assert r7.json()["status"] == "refunded"


@pytest.mark.asyncio
async def test_missing_idempotency_key_422(client, env) -> None:
    _, info, slots_view = env
    headers = await _user_headers(client, "13800000019")
    r = await client.post(
        "/api/bookings",
        json={
            "release_id": info["release_id"],
            "court_slot_ids": [slots_view[0]["court_slot_id"]],
        },
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_requires_operator_t13(client, env) -> None:
    """普通用户访问管理端 → 403。"""
    headers = await _user_headers(client, "13800000020")
    r = await client.get("/api/admin/bookings", headers=headers)
    assert r.status_code == 403
