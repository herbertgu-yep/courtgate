"""场馆管理：配置校验、按时段粒度/休息窗口放场、闭馆冲突处理（取消/退款/通知）。"""

import datetime as dt

import pytest

from app.core.config import get_settings
from app.services.payment_service import build_mock_callback
from tests.conftest import make_operator, make_release, make_venue, register_and_login


def _d(days: int) -> str:
    return str(dt.datetime.now(dt.UTC).date() + dt.timedelta(days=days))


@pytest.fixture
async def op(client):
    return await make_operator(client)


@pytest.mark.asyncio
async def test_venue_config_validation_and_slot_defs(client, op) -> None:
    """营业配置校验 + 按粒度/休息窗口切片。"""
    # 30 分钟粒度 + 午休 12:00-13:00
    r = await client.post(
        "/api/admin/venues",
        json={
            "name": "切片馆",
            "open_time": "08:00",
            "close_time": "22:00",
            "breaks": [{"start": "12:00", "end": "13:00"}],
            "slot_minutes": 30,
            "court_count": 2,
            "base_price_cents": 2000,
        },
        headers=op,
    )
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    detail = (await client.get(f"/api/admin/venues/{vid}", headers=op)).json()
    assert len(detail["courts"]) == 2
    defs = detail["slot_defs"]
    # 8:00-22:00 除去 1 小时午休 = 13 小时 = 26 个半小时段
    assert len(defs) == 26
    starts = {d["start"] for d in defs}
    assert "12:00" not in starts and "12:30" not in starts and "13:00" in starts
    # 默认不配高峰：全时段基础价
    assert all(d["price_ratio_bp"] == 10000 for d in defs)

    # 非法配置
    for bad in [
        {"open_time": "22:00", "close_time": "08:00"},
        {"slot_minutes": 45},
        {"breaks": [{"start": "07:00", "end": "09:00"}]},
        {"breaks": [{"start": "10:00", "end": "09:00"}]},
    ]:
        body = {
            "name": "坏配置馆",
            "open_time": "08:00",
            "close_time": "22:00",
            "court_count": 1,
            "base_price_cents": 100,
            **bad,
        }
        r2 = await client.post("/api/admin/venues", json=body, headers=op)
        assert r2.status_code == 422, (bad, r2.text)

    # 编辑：改粒度 60 分钟 → 13 段，并显式配置高峰 18:00-22:00 ×1.5
    r3 = await client.patch(
        f"/api/admin/venues/{vid}",
        json={"slot_minutes": 60, "peak_start_time": "18:00", "peak_end_time": "22:00", "peak_ratio_bp": 15000},
        headers=op,
    )
    assert r3.status_code == 200
    defs60 = r3.json()["slot_defs"]
    assert len(defs60) == 13
    peak = [d for d in defs60 if d["price_ratio_bp"] == 15000]
    assert len(peak) == 4 and peak[0]["start"] == "18:00"
    # 非法高峰：窗口越界 / 倍率不在白名单 / 只填一头
    for bad in [
        {"peak_start_time": "07:00", "peak_end_time": "09:00", "peak_ratio_bp": 15000},
        {"peak_start_time": "18:00", "peak_end_time": "22:00", "peak_ratio_bp": 13000},
        {"peak_start_time": "18:00", "peak_end_time": ""},
        {"peak_start_time": "12:00", "peak_end_time": "13:00", "peak_ratio_bp": 15000},  # 与午休重叠
    ]:
        r4 = await client.patch(f"/api/admin/venues/{vid}", json=bad, headers=op)
        assert r4.status_code == 422, (bad, r4.text)


@pytest.mark.asyncio
async def test_release_honors_breaks_and_granularity(client, op) -> None:
    """放场按场馆配置生成时段切片，休息窗口无格可约。"""
    r = await client.post(
        "/api/admin/venues",
        json={
            "name": "午休馆",
            "open_time": "08:00",
            "close_time": "22:00",
            "breaks": [{"start": "12:00", "end": "13:00"}],
            "slot_minutes": 60,
            "court_count": 1,
            "base_price_cents": 3000,
        },
        headers=op,
    )
    vid = r.json()["id"]
    info = await make_release(client, op, vid, n_days=2)
    assert info["generated"] == 13 * 2, f"13 段 × 2 天 = 26 单元，实际 {info['generated']}"
    view = (await client.get(f"/api/releases/{info['release_id']}/slots?date={_d(1)}")).json()
    labels = [s["label"] for c in view["courts"] for s in c["slots"]]
    assert not any(x.startswith("12:00") for x in labels)
    assert any(x.startswith("11:00") for x in labels) and any(x.startswith("13:00") for x in labels)


@pytest.mark.asyncio
async def test_closure_conflict_preview_and_refund(client, op) -> None:
    """闭馆：预览受影响预约 → 确认后已支付单退款、时段回架、积分扣回、站内信送达。"""
    vid, _, _ = await make_venue(client, op, n_courts=2)
    info = await make_release(client, op, vid, n_days=3)
    tokens = await register_and_login(client, "closureuser1")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    # 留手机号（闭馆场景便于联系）
    r = await client.post("/api/auth/phone", json={"phone": "13800001111"}, headers=headers)
    assert r.status_code == 200
    view = (await client.get(f"/api/releases/{info['release_id']}/slots?date={_d(1)}")).json()
    slot = view["courts"][0]["slots"][0]
    uid = __import__("uuid").uuid4()
    r = await client.post(
        "/api/bookings",
        json={
            "release_id": info["release_id"],
            "court_slot_ids": [slot["court_slot_id"]],
            "coupon_id": None,
            "use_points": 0,
        },
        headers={**headers, "Idempotency-Key": str(uid)},
    )
    assert r.status_code == 201, r.text
    booking_no = r.json()["booking_no"]
    # 支付（沙箱渠道回调）
    p = (await client.post(f"/api/payments/{booking_no}", json={"channel": "mock_alipay"}, headers=headers)).json()
    cb = build_mock_callback(p["payment_no"], p["amount_cents"], secret=get_settings().payment_secret)
    r = await client.post("/api/payments/callback/mock_alipay", json=cb)
    assert r.status_code == 200
    # 支付赠送积分到账
    balance_after_pay = (await client.get("/api/points/balance", headers=headers)).json()["balance"]
    assert balance_after_pay > 0

    # 闭馆预览：有 1 笔受影响 → 409 冲突 + 明细
    r = await client.post(f"/api/admin/venues/{vid}/closures", json={"closure_date": _d(1)}, headers=op)
    assert r.status_code == 409, r.text
    preview = r.json()["error"]["details"]["preview"]
    assert preview["count"] == 1
    row = preview["bookings"][0]
    assert row["booking_no"] == booking_no
    assert row["user_phone"] == "13800001111"
    assert row["status"] == "paid"

    # 确认闭馆 → 退款
    r = await client.post(
        f"/api/admin/venues/{vid}/closures",
        json={"closure_date": _d(1), "notify_content": "设备检修，暂停营业一天", "force": True},
        headers=op,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refunded"] == 1 and body["cancelled"] == 0

    # 预约状态 → refunded；该日整体闭馆（视图标记 closed，时段在库已回架）
    b = (await client.get(f"/api/bookings/{booking_no}", headers=headers)).json()
    assert b["status"] == "refunded"
    view2 = (await client.get(f"/api/releases/{info['release_id']}/slots?date={_d(1)}")).json()
    assert view2["closed"] is True
    other = (await client.get(f"/api/releases/{info['release_id']}/slots?date={_d(2)}")).json()
    assert other["closed"] is False and any(s["available"] for c in other["courts"] for s in c["slots"])
    # 积分扣回（余额归零）
    assert (await client.get("/api/points/balance", headers=headers)).json()["balance"] == 0
    # 站内信收到闭馆通知（自定义留言透传）
    notifs = (await client.get("/api/notifications", headers=headers)).json()["items"]
    closure = [n for n in notifs if n["template_code"] == "VENUE_CLOSURE"]
    assert len(closure) == 1 and "设备检修" in closure[0]["content"]
    # 同日期重复闭馆 → 业务错误
    r = await client.post(f"/api/admin/venues/{vid}/closures", json={"closure_date": _d(1), "force": True}, headers=op)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_closure_cancels_pending_booking(client, op) -> None:
    """闭馆对待支付单：自动取消并释放时段，不产生退款。"""
    vid, _, _ = await make_venue(client, op, n_courts=1)
    info = await make_release(client, op, vid, n_days=2)
    tokens = await register_and_login(client, "closureuser2")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    view = (await client.get(f"/api/releases/{info['release_id']}/slots?date={_d(1)}")).json()
    slot = view["courts"][0]["slots"][0]
    r = await client.post(
        "/api/bookings",
        json={
            "release_id": info["release_id"],
            "court_slot_ids": [slot["court_slot_id"]],
            "coupon_id": None,
            "use_points": 0,
        },
        headers={**headers, "Idempotency-Key": "closure-pending-1"},
    )
    booking_no = r.json()["booking_no"]
    r = await client.post(
        f"/api/admin/venues/{vid}/closures",
        json={"closure_date": _d(1), "force": True},
        headers=op,
    )
    assert r.status_code == 200 and r.json()["cancelled"] == 1
    b = (await client.get(f"/api/bookings/{booking_no}", headers=headers)).json()
    assert b["status"] == "cancelled"


@pytest.mark.asyncio
async def test_admin_venue_bookings_query(client, op) -> None:
    """管理端按场馆 + 日期查预约卡片（含用户手机号）。"""
    vid, _, _ = await make_venue(client, op, n_courts=1)
    info = await make_release(client, op, vid, n_days=2)
    tokens = await register_and_login(client, "queryuser1")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    await client.post("/api/auth/phone", json={"phone": "13900002222"}, headers=headers)
    view = (await client.get(f"/api/releases/{info['release_id']}/slots?date={_d(2)}")).json()
    slot = view["courts"][0]["slots"][0]
    await client.post(
        "/api/bookings",
        json={
            "release_id": info["release_id"],
            "court_slot_ids": [slot["court_slot_id"]],
            "coupon_id": None,
            "use_points": 0,
        },
        headers={**headers, "Idempotency-Key": "query-1"},
    )
    r = await client.get(f"/api/admin/venues/{vid}/bookings?date={_d(2)}", headers=op)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["user_phone"] == "13900002222"
    assert items[0]["items"][0]["time_label"]
    # 其他日期查不到
    r2 = await client.get(f"/api/admin/venues/{vid}/bookings?date={_d(1)}", headers=op)
    assert r2.json()["items"] == []


@pytest.mark.asyncio
async def test_edit_court_price_and_peak_pricing(client, op) -> None:
    """场地改价（仅影响之后放场）+ 高峰按配置计价。"""
    r = await client.post(
        "/api/admin/venues",
        json={
            "name": "改价馆",
            "open_time": "08:00",
            "close_time": "22:00",
            "breaks": [],
            "slot_minutes": 60,
            "court_count": 2,
            "base_price_cents": 2000,
        },
        headers=op,
    )
    vid = r.json()["id"]
    detail = (await client.get(f"/api/admin/venues/{vid}", headers=op)).json()
    court_id = detail["courts"][0]["id"]
    # 改价 20 → 30
    r2 = await client.patch(f"/api/admin/courts/{court_id}", json={"base_price_cents": 3000}, headers=op)
    assert r2.status_code == 200 and r2.json()["base_price_cents"] == 3000
    # 低于 1 元拒绝
    assert (
        await client.patch(f"/api/admin/courts/{court_id}", json={"base_price_cents": 50}, headers=op)
    ).status_code == 422
    # 放场后：1 号场 30，2 号场仍是 20
    info = await make_release(client, op, vid, n_days=1)
    view = (await client.get(f"/api/releases/{info['release_id']}/slots")).json()
    by_court = {c["court_name"]: {s["price_cents"] for s in c["slots"]} for c in view["courts"]}
    assert by_court["1 号场"] == {3000} and by_court["2 号场"] == {2000}
    # 高峰 ×2：18-22 点开始的时段 60 元
    r3 = await client.patch(
        f"/api/admin/venues/{vid}",
        json={"peak_start_time": "18:00", "peak_end_time": "22:00", "peak_ratio_bp": 20000},
        headers=op,
    )
    assert r3.status_code == 200
    import datetime as dtt

    start = dtt.datetime.now(dtt.UTC).date() + dtt.timedelta(days=2)
    now = dtt.datetime.now(dtt.UTC)

    def iso(d):
        return d.astimezone(dtt.UTC).isoformat(timespec="seconds")

    rel2 = (
        await client.post(
            "/api/admin/releases",
            json={
                "venue_id": vid,
                "name": "高峰批",
                "period_start": str(start),
                "period_end": str(start),
                "open_at": iso(now - dtt.timedelta(hours=1)),
                "close_at": iso(now + dtt.timedelta(days=5)),
                "per_user_limit": 3,
            },
            headers=op,
        )
    ).json()
    view2 = (await client.get(f"/api/releases/{rel2['release_id']}/slots")).json()
    c1 = [c for c in view2["courts"] if c["court_name"] == "1 号场"][0]
    peak = [s for s in c1["slots"] if s["price_cents"] == 6000]
    assert [s["label"] for s in peak] == ["18:00-19:00", "19:00-20:00", "20:00-21:00", "21:00-22:00"]


@pytest.mark.asyncio
async def test_regenerate_release_reprices(client, op) -> None:
    """无预约的批次可按当前配置重生成计价；有预约的批次拒绝。"""
    r = await client.post(
        "/api/admin/venues",
        json={
            "name": "重生成馆",
            "open_time": "08:00",
            "close_time": "22:00",
            "breaks": [],
            "slot_minutes": 60,
            "court_count": 1,
            "base_price_cents": 2000,
        },
        headers=op,
    )
    vid = r.json()["id"]
    import datetime as dtx

    now = dtx.datetime.now(dtx.UTC)

    def _iso(d):
        return d.astimezone(dtx.UTC).isoformat(timespec="seconds")

    start = now.date() + dtx.timedelta(days=1)
    rel = (
        await client.post(
            "/api/admin/releases",
            json={
                "venue_id": vid,
                "name": "初版",
                "period_start": str(start),
                "period_end": str(start),
                "open_at": _iso(now - dtx.timedelta(hours=1)),
                "close_at": _iso(now + dtx.timedelta(days=5)),
                "per_user_limit": 3,
            },
            headers=op,
        )
    ).json()
    rid = rel["release_id"]
    view = (await client.get(f"/api/releases/{rid}/slots")).json()
    assert all(s["price_cents"] == 2000 for c in view["courts"] for s in c["slots"])

    # 场馆配置加高峰 ×1.5 + 场地改价 30 → 重生成后旧批次按新配置计价
    court_id = (await client.get(f"/api/admin/venues/{vid}", headers=op)).json()["courts"][0]["id"]
    await client.patch(f"/api/admin/courts/{court_id}", json={"base_price_cents": 3000}, headers=op)
    await client.patch(
        f"/api/admin/venues/{vid}",
        json={"peak_start_time": "18:00", "peak_end_time": "22:00", "peak_ratio_bp": 15000},
        headers=op,
    )
    regen = await client.post(f"/api/admin/releases/{rid}/regenerate", headers=op)
    assert regen.status_code == 200, regen.text
    view2 = (await client.get(f"/api/releases/{rid}/slots")).json()
    slots = [s for c in view2["courts"] for s in c["slots"]]
    assert {s["price_cents"] for s in slots} == {3000, 4500}
    assert [s["label"] for s in slots if s["price_cents"] == 4500] == [
        "18:00-19:00",
        "19:00-20:00",
        "20:00-21:00",
        "21:00-22:00",
    ]

    # 有人预约后禁止重生成
    tokens = await register_and_login(client, "regenuser1")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await client.post(
        "/api/bookings",
        json={"release_id": rid, "court_slot_ids": [slots[0]["court_slot_id"]], "coupon_id": None, "use_points": 0},
        headers={**headers, "Idempotency-Key": "regen-book-1"},
    )
    assert r.status_code == 201
    conflict = await client.post(f"/api/admin/releases/{rid}/regenerate", headers=op)
    assert conflict.status_code == 409
    assert "预约记录" in conflict.json()["error"]["message"]


@pytest.mark.asyncio
async def test_add_court_from_edit_form(client, op) -> None:
    """编辑页新增场地：POST /api/admin/courts 后可放场使用。"""
    r = await client.post(
        "/api/admin/venues",
        json={
            "name": "加场馆",
            "open_time": "08:00",
            "close_time": "22:00",
            "breaks": [],
            "slot_minutes": 60,
            "court_count": 1,
            "base_price_cents": 2000,
        },
        headers=op,
    )
    vid = r.json()["id"]
    r2 = await client.post(
        "/api/admin/courts", json={"venue_id": vid, "name": "5 号场", "base_price_cents": 2500}, headers=op
    )
    assert r2.status_code == 201
    detail = (await client.get(f"/api/admin/venues/{vid}", headers=op)).json()
    assert len(detail["courts"]) == 2
    assert {c["base_price_cents"] for c in detail["courts"]} == {2000, 2500}


@pytest.mark.asyncio
async def test_cancel_paid_within_two_hours_rejected(client, op) -> None:
    """已支付订单开场前 2 小时内不可取消；场地电话格式校验。"""
    # 00:00-23:30 营业，保证任意时刻都有 <2 小时后开始的时段
    r = await client.post(
        "/api/admin/venues",
        json={
            "name": "临期馆",
            "open_time": "00:00",
            "close_time": "23:30",
            "breaks": [],
            "slot_minutes": 60,
            "court_count": 1,
            "base_price_cents": 1000,
            "phone": "0571-88880000",
        },
        headers=op,
    )
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    start = now.date()
    rel = (
        await client.post(
            "/api/admin/releases",
            json={
                "venue_id": vid,
                "name": "全天批",
                "period_start": str(start),
                "period_start_alt": None,
                "period_end": str(start + __import__("datetime").timedelta(days=1)),
                "open_at": (now - __import__("datetime").timedelta(hours=1)).isoformat(timespec="seconds"),
                "close_at": (now + __import__("datetime").timedelta(days=2)).isoformat(timespec="seconds"),
                "per_user_limit": 3,
            },
            headers=op,
        )
    ).json()
    tokens = await register_and_login(client, "canceluser1")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    # 挑一个 2 小时内开始的时段
    d1 = str(now.date())
    view = (await client.get(f"/api/releases/{rel['release_id']}/slots?date={d1}")).json()
    slots = [s for c in view["courts"] for s in c["slots"] if s["available"]]

    def starts_in(s):
        hh, mm = s["label"].split("-")[0].split(":")
        start_dt = __import__("datetime").datetime.fromisoformat(f"{d1}T{hh}:{mm}:00+08:00")
        return (start_dt - now).total_seconds()

    soon = min(slots, key=starts_in)
    assert starts_in(soon) < 2 * 3600, "测试前置：应有 2 小时内开始的时段"
    r = await client.post(
        "/api/bookings",
        json={
            "release_id": rel["release_id"],
            "court_slot_ids": [soon["court_slot_id"]],
            "coupon_id": None,
            "use_points": 0,
        },
        headers={**headers, "Idempotency-Key": "soon-1"},
    )
    assert r.status_code == 201, r.text
    bno = r.json()["booking_no"]
    from app.core.config import get_settings
    from app.services.payment_service import build_mock_callback

    p = (await client.post(f"/api/payments/{bno}", json={"channel": "mock_alipay"}, headers=headers)).json()
    cb = build_mock_callback(p["payment_no"], p["amount_cents"], secret=get_settings().payment_secret)
    await client.post("/api/payments/callback/mock_alipay", json=cb)
    r2 = await client.post(f"/api/bookings/{bno}/cancel", headers=headers)
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "CANCEL_WINDOW", r2.text


@pytest.mark.asyncio
async def test_closed_day_booking_rejected(client, op) -> None:
    """休息日的时段：试算与下单均拒绝，slots 视图标记 closed；其他日期正常。"""
    r = await client.post(
        "/api/admin/venues",
        json={
            "name": "闭馆校验馆",
            "open_time": "08:00",
            "close_time": "22:00",
            "breaks": [],
            "slot_minutes": 60,
            "court_count": 1,
            "base_price_cents": 1000,
        },
        headers=op,
    )
    vid = r.json()["id"]
    import datetime as dtx

    now = dtx.datetime.now(dtx.UTC)
    start = now.date() + dtx.timedelta(days=1)
    rel = (
        await client.post(
            "/api/admin/releases",
            json={
                "venue_id": vid,
                "name": "校验批",
                "period_start": str(start),
                "period_end": str(start),
                "open_at": (now - dtx.timedelta(hours=1)).isoformat(timespec="seconds"),
                "close_at": (now + dtx.timedelta(days=5)).isoformat(timespec="seconds"),
                "per_user_limit": 3,
            },
            headers=op,
        )
    ).json()
    view = (await client.get(f"/api/releases/{rel['release_id']}/slots?date={start}")).json()
    slot = view["courts"][0]["slots"][0]
    tokens = await register_and_login(client, "closeday1")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    await client.post(f"/api/admin/venues/{vid}/closures", json={"closure_date": str(start), "force": True}, headers=op)
    body = {
        "release_id": rel["release_id"],
        "court_slot_ids": [slot["court_slot_id"]],
        "coupon_id": None,
        "use_points": 0,
    }
    q = await client.post("/api/bookings/quote", json=body, headers=headers)
    assert q.status_code == 409 and q.json()["error"]["code"] == "VENUE_CLOSED", q.text
    import uuid

    b = await client.post("/api/bookings", json=body, headers={**headers, "Idempotency-Key": str(uuid.uuid4())})
    assert b.status_code == 409 and b.json()["error"]["code"] == "VENUE_CLOSED"
    v2 = (await client.get(f"/api/releases/{rel['release_id']}/slots?date={start}")).json()
    assert v2["closed"] is True and all(not s["available"] for c in v2["courts"] for s in c["slots"])


@pytest.mark.asyncio
async def test_coupon_template_admin(client, op) -> None:
    """券模板列表（含领取进度）与停发。"""
    import datetime as dtx

    now = dtx.datetime.now(dtx.UTC)
    r = await client.post(
        "/api/admin/coupons",
        json={
            "name": "管理端券",
            "type": "fixed",
            "value": 500,
            "min_spend_cents": 0,
            "total_quantity": 10,
            "per_user_limit": 1,
            "valid_from": (now - dtx.timedelta(hours=1)).isoformat(timespec="seconds"),
            "valid_to": (now + dtx.timedelta(days=30)).isoformat(timespec="seconds"),
        },
        headers=op,
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    lst = (await client.get("/api/admin/coupon-templates", headers=op)).json()["items"]
    row = [t for t in lst if t["id"] == tid][0]
    assert row["remaining"] == 10 and row["claimed"] == 0 and row["status"] == "active"
    r2 = await client.patch(f"/api/admin/coupons/{tid}/status", json={"status": "inactive"}, headers=op)
    assert r2.status_code == 200
    lst2 = (await client.get("/api/admin/coupon-templates", headers=op)).json()["items"]
    assert [t for t in lst2 if t["id"] == tid][0]["status"] == "inactive"
    # 停发后领券中心不再展示
    pub = (await client.get("/api/coupons/templates")).json()["items"]
    assert all(t["id"] != tid for t in pub)


@pytest.mark.asyncio
async def test_user_phone_validation(client) -> None:
    tokens = await register_and_login(client, "phoneuser1")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.post("/api/auth/phone", json={"phone": "12345"}, headers=headers)).status_code == 422
    r = await client.post("/api/auth/phone", json={"phone": "13800138000"}, headers=headers)
    assert r.status_code == 200
    me = (await client.get("/api/auth/me", headers=headers)).json()
    assert me["phone_number"] == "13800138000"
