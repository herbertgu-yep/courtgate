"""渠道注册表：新增渠道 = 实现类 + 在此注册，业务代码零分支。"""

from __future__ import annotations

from app.services.payment.base import PaymentChannel
from app.services.payment.mock_alipay import MockAlipayChannel
from app.services.payment.mock_wechat import MockWechatChannel

CHANNELS: dict[str, PaymentChannel] = {
    MockAlipayChannel.code: MockAlipayChannel(),
    MockWechatChannel.code: MockWechatChannel(),
}


def get_channel(code: str) -> PaymentChannel:
    if code not in CHANNELS:
        from app.core.exceptions import NotFoundError

        raise NotFoundError(f"不支持的支付渠道：{code}")
    return CHANNELS[code]


def list_channels() -> list[dict]:
    return [{"code": c.code, "label": c.label, "sandbox": c.sandbox} for c in CHANNELS.values()]
