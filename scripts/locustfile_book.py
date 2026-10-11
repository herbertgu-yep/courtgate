"""纯抢约压测：只打 POST /api/bookings（开抢瞬间的写风暴）。

每个虚拟用户循环提交：随机时段 + 唯一幂等键。时段有限，先成功后 409，
QPS 衡量系统在写风暴下的吸收能力，售罄耗时衡量清空 1176 个单元的速度。
"""

from __future__ import annotations

import json
import os
import random
import uuid

from locust import HttpUser, between, events, task

TOKENS: list[dict] = []
RELEASE_ID = int(os.environ.get("LOCUST_RELEASE_ID", "1"))
SLOT_IDS: list[int] = []


@events.test_start.add_listener
def _load(environment, **kwargs):
    global TOKENS, SLOT_IDS
    with open("/tmp/bench_tokens.json", encoding="utf-8") as f:
        TOKENS = json.load(f)
    with open("/tmp/bench/slot_ids.json", encoding="utf-8") as f:
        SLOT_IDS = json.load(f)


class Booker(HttpUser):
    wait_time = between(0, 0.05)

    def on_start(self) -> None:
        me = random.choice(TOKENS)
        self.headers = {"Authorization": f"Bearer {me['token']}"}

    @task
    def book(self) -> None:
        if not SLOT_IDS:
            return
        pick = random.choice(SLOT_IDS)
        self.client.post(
            "/api/bookings",
            json={"release_id": RELEASE_ID, "court_slot_ids": [pick]},
            headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())},
            name="/bookings 抢约写",
        )
