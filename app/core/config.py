"""全局配置：环境变量前缀 COURTGATE_。场馆业务参数存数据库，不在这里。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COURTGATE_", env_file=".env", extra="ignore")

    database_url: str = "mysql+aiomysql://courtgate:courtgate@localhost:3306/courtgate?charset=utf8mb4"
    sync_database_url: str = "mysql+pymysql://courtgate:courtgate@localhost:3306/courtgate?charset=utf8mb4"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-only-secret-change-me-in-prod-0123456789"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl: int = 1800
    jwt_refresh_ttl: int = 604800

    payment_secret: str = "dev-payment-secret-change-me-in-prod-0123456789"

    booking_expire_seconds: int = 900
    max_slots_per_booking: int = 4

    rate_limit_enabled: bool = True
    points_redeem_max_bp: int = 5000

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    ui_enabled: bool = True
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
