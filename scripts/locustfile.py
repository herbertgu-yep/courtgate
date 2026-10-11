"""CourtGate 压测场景。

真实抢购形态：浏览占大头、预约是热点写、时段有限故大量请求以 409 失败——
这正是开抢瞬间的真实流量画像，QPS 衡量的是系统吸收风暴的能力。

用法（headless）：
  locust -f scripts/locustfile.py --headless -u 200 -r 50 -t 60s \
         --host http://127.0.0.1:8000 --csv /tmp/bench/redis_1 --only-summary
"""

from __future__ import annotations

import json
import os
import random
import uuid

from locust import HttpUser, between, events, task

TOKENS: list[dict] = []
RELEASE_ID = int(os.environ.get("LOCUST_RELEASE_ID", "1"))


@events.test_start.add_listener
def _load_tokens(environment: object, **kwargs: object) -> None:
    global TOKENS
    with open("/tmp/bench_tokens.json", encoding="utf-8") as f:
        TOKENS = json.load(f)


class VenueUser(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self) -> None:
        # 每个虚拟用户绑定一个系统用户（绕开登录接口，登录不是被测对象）
        me = random.choice(TOKENS)
        self.headers = {"Authorization": f"Bearer {me['token']}"}
        self._dates_cache: list[str] = []

    def _dates(self) -> list[str]:
        if not self._dates_cache:
            r = self.client.get(f"/api/releases/{RELEASE_ID}/slots", name="/slots 首屏(全量骨架)")
            self._dates_cache = r.json().get("dates", [])
        return self._dates_cache

    @task(3)
    def view_slots(self) -> None:
        """浏览某一天的可约时段：日期横滑条行为。"""
        dates = self._dates()
        if not dates:
            return
        d = random.choice(dates)
        self.client.get(f"/api/releases/{RELEASE_ID}/slots?date={d}", name="/slots 浏览")

    @task(1)
    def book(self) -> None:
        """抢约：先查当天时段（真实前端行为），再提交。"""
        dates = self._dates()
        if not dates:
            return
        d = random.choice(dates)
        r = self.client.get(f"/api/releases/{RELEASE_ID}/slots?date={d}", name="/slots 浏览(抢约前查)")
        slots = [s for c in r.json().get("courts", []) for s in c["slots"] if s["available"]]
        if not slots:
            return
        pick = random.choice(slots)["court_slot_id"]
        self.client.post(
            "/api/bookings",
            json={"release_id": RELEASE_ID, "court_slot_ids": [pick]},
            headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())},
            name="/bookings 抢约",
        )
