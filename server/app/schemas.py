from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr


class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    device_fingerprint: Optional[str] = None     # dùng để nhận ra "cùng máy" (không chặn, chỉ log)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    entitlements: List[str]
    plan: str
    session_id: str                               # phiên "đang đăng nhập" — 1 máy tại 1 thời điểm


class RefreshIn(BaseModel):
    refresh_token: str
    device_fingerprint: Optional[str] = None


class LogoutIn(BaseModel):
    refresh_token: str
    session_id: Optional[str] = None


class SessionRefIn(BaseModel):
    session_id: str


class EventIn(BaseModel):
    type: str
    ts: Optional[float] = None
    payload: Dict[str, Any] = {}


class EventsIn(BaseModel):
    device_fingerprint: Optional[str] = None
    events: List[EventIn]


class ErrorIn(BaseModel):
    message: str
    traceback: Optional[str] = ""
    device_fingerprint: Optional[str] = None


class RecipeIn(BaseModel):
    key: str
    activity: str
    kind: str
    x: int
    y: int
    count: int
    sec_min: float
    sec_max: float
    sec_sum: float
    first_seen: str
    last_seen: str


class RecipesPushIn(BaseModel):
    recipes: List[RecipeIn]
