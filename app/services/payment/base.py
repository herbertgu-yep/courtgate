"""支付渠道抽象：业务代码只通过 get_channel(code) 取用，禁止 if channel == 分支。"""

from __future__ import annotations

import hashlib
import hmac
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import PaymentSignatureInvalidError


class CallbackData(BaseModel):
    payment_no: str
    third_party_no: str
    amount_cents: int
    status: str


class PaymentChannel(ABC):
    code: str
    label: str
    sandbox: bool = False  # 沙箱渠道：本地演示用，无真实资金流

    @abstractmethod
    async def create_payment(self, booking_no: str, amount_cents: int) -> dict:
        """返回前端发起支付所需参数。"""

    @abstractmethod
    def verify_callback(self, payload: dict[str, Any]) -> CallbackData:
        """验签并解析回调；失败抛 PaymentSignatureInvalidError。"""

    async def refund(self, payment_no: str, amount_cents: int) -> dict:
        """原路退款。真实渠道未接入时抛 NotImplementedError，业务侧留待人工。"""
        raise NotImplementedError(f"渠道 {self.code} 暂未接入退款，请人工处理")


def sign_payload(parts: list[Any], secret: str) -> str:
    msg = "|".join(str(p) for p in parts)
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def check_timestamp(ts: int, tolerance_seconds: int = 300) -> None:
    import time

    if abs(time.time() - int(ts)) > tolerance_seconds:
        raise PaymentSignatureInvalidError("回调时间戳超出容差窗口")
