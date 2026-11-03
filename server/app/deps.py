from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import models, security
from .db import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> models.User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "thiếu access token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = security.decode_access_token(token)
    except Exception:
        raise HTTPException(401, "access token không hợp lệ hoặc hết hạn")
    user = db.get(models.User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(401, "tài khoản không tồn tại hoặc đã bị khoá")
    return user
