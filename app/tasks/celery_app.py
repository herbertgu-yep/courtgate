"""Celery 应用：队列 cg.bookings / cg.maintenance。"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

celery_app = Celery("courtgate", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    task_default_queue="cg.maintenance",
    task_queues=None,  # 使用 route 指定
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # worker 崩溃任务可重投 → 任务必须幂等
    worker_prefetch_multiplier=1,
)
celery_app.conf.task_routes = {
    "app.tasks.booking_tasks.*": {"queue": "cg.bookings"},
    "app.tasks.maintenance_tasks.*": {"queue": "cg.maintenance"},
}

# 定时任务：超时兜底 / 批次状态维护 / 缓存对账（beat 容器执行）
celery_app.conf.beat_schedule = {
    "scan-expired-bookings": {
        "task": "app.tasks.maintenance_tasks.scan_expired",
        "schedule": 60.0,
    },
    "toggle-releases": {
        "task": "app.tasks.maintenance_tasks.toggle_releases",
        "schedule": 60.0,
    },
    "reconcile-availability": {
        "task": "app.tasks.maintenance_tasks.reconcile_all",
        "schedule": 300.0,
    },
}
