"""认证流：注册 / 登录 / 刷新 / 越权 401。"""

import pytest

from tests.conftest import _solve_captcha, register_and_login


@pytest.mark.asyncio
async def test_register_login_refresh_me(client) -> None:
    tokens = await register_and_login(client, "13800000001")
    assert tokens["access_token"]
    r = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200 and r.json()["username"] == "13800000001"


@pytest.mark.asyncio
async def test_duplicate_register_rejected(client) -> None:
    await register_and_login(client, "13800000002")
    cap = await _solve_captcha(client)
    r = await client.post("/api/auth/register", json={"username": "13800000002", "password": "Pass@123", **cap})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_password_401(client) -> None:
    cap = await _solve_captcha(client)
    r = await client.post("/api/auth/login", json={"username": "13800000003", "password": "wrong", **cap})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_without_token_401(client) -> None:
    r = await client.get("/api/auth/me")
    assert r.status_code == 401
