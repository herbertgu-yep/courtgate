"""Mock 支付宝渠道：本地演示与测试用，无需商户资质。"""

from __future__ import annotations

import hmac
from typing import Any

from app.core.config import get_settings
from app.services.payment.base import CallbackData, PaymentChannel, check_timestamp, sign_payload


class MockAlipayChannel(PaymentChannel):
    code = "mock_alipay"
    label = "支付宝"
    sandbox = True

    async def create_payment(self, booking_no: str, amount_cents: int) -> dict:
        return {
            "channel": self.code,
            "pay_url": f"mock://alipay/pay?bn={booking_no}",
            "amount_cents": amount_cents,
        }

    async def refund(self, payment_no: str, amount_cents: int) -> dict:
        """沙箱渠道：无真实资金流，直接返回退款成功。"""
        import secrets

        return {
            "refund_no": f"R{secrets.randbelow(10**12):012d}",
            "payment_no": payment_no,
            "amount_cents": amount_cents,
            "status": "refunded",
        }

    def verify_callback(self, payload: dict[str, Any]) -> CallbackData:
        secret = get_settings().payment_secret
        expected = sign_payload(
            [
                payload.get("payment_no"),
                payload.get("third_party_no"),
                payload.get("amount_cents"),
                payload.get("status"),
                payload.get("timestamp"),
            ],
            secret,
        )
        if not hmac.compare_digest(expected, str(payload.get("signature", ""))):
            from app.core.exceptions import PaymentSignatureInvalidError

            raise PaymentSignatureInvalidError("签名不匹配")
        check_timestamp(int(payload["timestamp"]))
        return CallbackData(
            payment_no=str(payload["payment_no"]),
            third_party_no=str(payload["third_party_no"]),
            amount_cents=int(payload["amount_cents"]),
            status=str(payload["status"]),
        )
