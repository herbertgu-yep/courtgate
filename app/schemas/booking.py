from pydantic import BaseModel, Field


class BookingIn(BaseModel):
    release_id: int
    court_slot_ids: list[int] = Field(min_length=1, max_length=8)
    coupon_id: int | None = None
    use_points: int = Field(default=0, ge=0)


class CancelOut(BaseModel):
    booking_no: str
    status: str
