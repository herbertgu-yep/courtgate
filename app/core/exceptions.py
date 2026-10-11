"""业务异常体系：services 抛、api 层统一翻译，业务代码不 try/except。"""

from __future__ import annotations


class CourtGateError(Exception):
    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "服务器内部错误"

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        super().__init__(message or self.message)
        self.detail = message or self.message
        self.details = details or {}


class SlotUnavailableError(CourtGateError):
    code = "SLOT_UNAVAILABLE"
    http_status = 409
    message = "该时段已被预约"


class ReleaseNotOpenError(CourtGateError):
    code = "RELEASE_NOT_OPEN"
    http_status = 409
    message = "当前不在可预约时间内"


class PerUserLimitExceededError(CourtGateError):
    code = "PER_USER_LIMIT_EXCEEDED"
    http_status = 409
    message = "超过每批次限约数量"


class BookingStateInvalidError(CourtGateError):
    code = "BOOKING_STATE_INVALID"
    http_status = 409
    message = "当前状态不允许该操作"


class IdempotencyConflictError(CourtGateError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409
    message = "同幂等键的请求正在处理中，请稍后查询结果"


class CouponNotApplicableError(CourtGateError):
    code = "COUPON_NOT_APPLICABLE"
    http_status = 409
    message = "优惠券不适用"


class InsufficientPointsError(CourtGateError):
    code = "INSUFFICIENT_POINTS"
    http_status = 409
    message = "积分不足"


class CouponSoldOutError(CourtGateError):
    code = "COUPON_SOLD_OUT"
    http_status = 409
    message = "优惠券已领完"


class OAuthCodeInvalidError(CourtGateError):
    code = "OAUTH_CODE_INVALID"
    http_status = 400
    message = "第三方授权码无效"


class OAuthAccountNotBoundError(CourtGateError):
    code = "OAUTH_ACCOUNT_NOT_BOUND"
    http_status = 409
    message = "该第三方账号未绑定手机号"


class NotFoundError(CourtGateError):
    code = "NOT_FOUND"
    http_status = 404
    message = "资源不存在"


class ForbiddenError(CourtGateError):
    code = "FORBIDDEN"
    http_status = 403
    message = "无权访问"


class UnauthorizedError(CourtGateError):
    code = "UNAUTHORIZED"
    http_status = 401
    message = "未登录或登录已过期"


class RateLimitedError(CourtGateError):
    code = "RATE_LIMITED"
    http_status = 429
    message = "请求过于频繁，请稍后再试"


class VenueClosedError(CourtGateError):
    code = "VENUE_CLOSED"
    http_status = 409
    message = "该日期场馆休息，不可预约"


class ClosureConflictError(CourtGateError):
    code = "CLOSURE_CONFLICT"
    http_status = 409
    message = "该日期存在未处理的预约，请确认后重试"


class PaymentSignatureInvalidError(CourtGateError):
    code = "PAYMENT_SIGNATURE_INVALID"
    http_status = 400
    message = "支付回调验签失败"
