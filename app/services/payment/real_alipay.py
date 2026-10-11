"""真实支付宝渠道骨架：需要商户资质与密钥，接入时实现本类即可，业务代码零改动。

接入步骤：
1. 在开放平台申请应用与商户号，配置 RSA2 密钥
2. create_payment：调用 alipay.trade.precreate（当面付）或 alipay.trade.page.pay
3. verify_callback：用支付宝公钥验签异步通知，并校验通知中的商户订单号/金额
4. 本文件实现完成后，注册表自动将其暴露给 /api/payments/channels
"""

from __future__ import annotations

from typing import Any

from app.services.payment.base import CallbackData, PaymentChannel


class RealAlipayChannel(PaymentChannel):
    code = "real_alipay"
    label = "支付宝（真实，未接入）"

    async def create_payment(self, booking_no: str, amount_cents: int) -> dict:
        raise NotImplementedError("需要支付宝商户资质与 RSA2 密钥，参见 docs/PAYMENT_INTEGRATION.md")

    def verify_callback(self, payload: dict[str, Any]) -> CallbackData:
        raise NotImplementedError("需要支付宝公钥验签，参见 docs/PAYMENT_INTEGRATION.md")
