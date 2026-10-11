"""Prometheus 指标。"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

http_requests_total = Counter("cg_http_requests_total", "HTTP 请求总数", ["method", "path", "status"])
http_request_duration = Histogram("cg_http_request_duration_seconds", "HTTP 请求耗时", ["method", "path"])
releases_created_total = Counter("cg_releases_created_total", "放场次数", ["venue_id"])
bookings_created_total = Counter("cg_bookings_created_total", "预约创建数", ["venue_id"])
bookings_cancelled_total = Counter("cg_bookings_cancelled_total", "预约取消数", ["reason"])
slot_claim_failed_total = Counter("cg_slot_claim_failed_total", "抢占失败数", ["reason"])
slots_occupied_total = Counter("cg_slots_occupied_total", "时段占用总数")
slots_released_total = Counter("cg_slots_released_total", "时段释放总数")
slot_drift_total = Counter("cg_slot_drift_total", "缓存与数据库不一致修正次数")
rate_limited_total = Counter("cg_rate_limited_total", "限流触发数", ["scope"])
payment_callback_total = Counter("cg_payment_callback_total", "支付回调数", ["channel", "result"])
notifications_total = Counter("cg_notifications_total", "通知数", ["channel", "status"])
coupons_claimed_total = Counter("cg_coupons_claimed_total", "领券数", ["template_id"])
points_earned_total = Counter("cg_points_earned_total", "积分入账数")
oauth_login_total = Counter("cg_oauth_login_total", "第三方登录数", ["provider", "bound"])
