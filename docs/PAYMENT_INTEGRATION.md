# 支付渠道接入说明

## 现状

- **Mock 渠道**（`mock_alipay` / `mock_wechat`）：开箱可用，用于演示与测试
- **真实渠道**：`RealAlipayChannel` 为骨架（抛 `NotImplementedError`），接入即用

## 回调验签算法（Mock 渠道，README 同步）

```
payload = f"{payment_no}|{third_party_no}|{amount_cents}|{status}|{timestamp}"
signature = HMAC_SHA256(key=COURTGATE_PAYMENT_SECRET, msg=payload).hexdigest()
校验：hmac.compare_digest(签名一致) 且 |now - timestamp| <= 300 秒（防重放）
```

构造一次合法回调（测试/演示）：

```python
from app.services.payment_service import build_mock_callback
cb = build_mock_callback("PAY20261012...", 7050, secret=settings.payment_secret)
POST /api/payments/callback/mock_alipay  body=cb
```

## 接入真实支付宝（当面付/手机网站支付）

1. 开放平台创建应用，签约，配置 `RSA2` 应用私钥/支付宝公钥
2. 实现 `RealAlipayChannel.create_payment`：调 `alipay.trade.precreate` 拿二维码串
3. 实现 `verify_callback`：用支付宝公钥验签 `sign`（RSA2，非 HMAC），校验
   `out_trade_no`、`total_amount`、`seller_id`
4. **金额必须与本地支付单一致**（本系统已强制，见 `payment_service.handle_callback`）
5. 幂等由 `uk_payments_channel_trade(channel, third_party_no)` 保证：同一通知重放返回 200
6. 在 `registry.CHANNELS` 注册 `RealAlipayChannel`，前端 `/api/payments/channels` 自动出现

## 微信支付

同构：`create_payment` 调 `JSAPI/Native` 下单，`verify_callback` 校验
`Wechatpay-Signature`（平台证书）+ `Wechatpay-Timestamp` 防重放，金额校验同上。
