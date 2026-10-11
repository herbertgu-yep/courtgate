"""支付回调签名。"""

import time

import pytest

from app.core.config import get_settings
from app.core.exceptions import PaymentSignatureInvalidError
from app.services.payment.base import sign_payload
from app.services.payment.mock_alipay import MockAlipayChannel


def _callback(payment_no: str, tp: str, amount: int, ts: int | None = None, sig: str | None = None) -> dict:
    t = ts or int(time.time())
    return {
        "payment_no": payment_no,
        "third_party_no": tp,
        "amount_cents": amount,
        "status": "success",
        "timestamp": t,
        "signature": sig
        if sig is not None
        else sign_payload([payment_no, tp, amount, "success", t], get_settings().payment_secret),
    }


@pytest.mark.asyncio
async def test_valid_signature() -> None:
    data = MockAlipayChannel().verify_callback(_callback("PAY1", "TP1", 100))
    assert data.payment_no == "PAY1"


@pytest.mark.asyncio
async def test_tampered_signature_rejected() -> None:
    cb = _callback("PAY1", "TP1", 100)
    cb["signature"] = "deadbeef"
    with pytest.raises(PaymentSignatureInvalidError):
        MockAlipayChannel().verify_callback(cb)


@pytest.mark.asyncio
async def test_expired_timestamp_rejected() -> None:
    old = int(time.time()) - 3600
    with pytest.raises(PaymentSignatureInvalidError):
        MockAlipayChannel().verify_callback(_callback("PAY1", "TP1", 100, ts=old))
