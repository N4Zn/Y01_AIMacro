"""Mô hình dữ liệu — khớp SERVER_DESIGN.md mục 1, trừ bảng devices đã thay bằng active_sessions (mục 4)."""
import time
import uuid

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text

from .db import Base


def _id():
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True, default=_id)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    password_salt = Column(String(64), nullable=False)
    plan = Column(String(16), default="free")               # free | pro
    is_active = Column(Boolean, default=True)
    created_at = Column(Float, default=time.time)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(String(32), primary_key=True, default=_id)
    user_id = Column(String(32), ForeignKey("users.id"), index=True)
    token_hash = Column(String(64), nullable=False, index=True)
    device_fingerprint = Column(String(64), nullable=True)  # chỉ để log/chẩn đoán
    created_at = Column(Float, default=time.time)
    expires_at = Column(Float, nullable=False)
    revoked = Column(Boolean, default=False)


class ActiveSession(Base):
    """Khoá theo TÀI KHOẢN ĐĂNG NHẬP (email) — chỉ 1 máy đăng nhập tại 1 thời điểm (SERVER_DESIGN.md mục 4).
    Tạo/chiếm lại ở /auth/login và /auth/refresh, không còn đọc tài khoản game (bỏ theo yêu cầu người dùng
    — 1 người dùng có nhiều tài khoản game là chuyện bình thường, không liên quan việc khoá license)."""
    __tablename__ = "active_sessions"
    id = Column(String(32), primary_key=True, default=_id)
    user_id = Column(String(32), ForeignKey("users.id"), index=True)
    device_fingerprint = Column(String(64), nullable=True)
    started_at = Column(Float, default=time.time)
    last_heartbeat = Column(Float, default=time.time)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id = Column(String(32), primary_key=True, default=_id)
    user_id = Column(String(32), ForeignKey("users.id"), index=True)
    device_fingerprint = Column(String(64), nullable=True)
    ts = Column(Float, default=time.time, index=True)
    type = Column(String(32))                                 # app_start|app_stop|category_run|ad_watched|error
    payload = Column(Text, default="{}")


class LibraryRecipe(Base):
    """Thư viện công thức đóng quảng cáo, server giữ bản gộp từ mọi máy (tương đương library.py cục bộ)."""
    __tablename__ = "library_recipes"
    key = Column(String(160), primary_key=True)               # activity|kind|x_bucket|y_bucket
    activity = Column(String(160))
    kind = Column(String(16))
    x = Column(Integer)
    y = Column(Integer)
    count = Column(Integer, default=0)
    sec_min = Column(Float)
    sec_max = Column(Float)
    sec_sum = Column(Float, default=0.0)
    first_seen = Column(String(16))
    last_seen = Column(String(16))
    updated_at = Column(Float, default=time.time, index=True)


class Release(Base):
    __tablename__ = "releases"
    id = Column(String(32), primary_key=True, default=_id)
    version = Column(String(32))
    channel = Column(String(16), default="stable")            # stable | beta
    download_url = Column(String(512))
    sha256 = Column(String(64), default="")
    notes = Column(Text, default="")
    force_update = Column(Boolean, default=False)
    published_at = Column(Float, default=time.time, index=True)
