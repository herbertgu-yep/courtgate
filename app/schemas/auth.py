"""认证相关请求模型。"""

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=4, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=64)
    nickname: str = ""
    captcha_id: str = Field(min_length=8, max_length=64)
    captcha_code: str = Field(min_length=4, max_length=4)


class LoginIn(BaseModel):
    username: str
    password: str
    captcha_id: str = Field(min_length=8, max_length=64)
    captcha_code: str = Field(min_length=4, max_length=4)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    nickname: str
    role: str
