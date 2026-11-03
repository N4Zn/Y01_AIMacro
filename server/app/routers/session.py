"""Chỉ còn heartbeat/release — phiên tự tạo/chiếm lại ở /auth/login và /auth/refresh (xem auth.py)."""
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/heartbeat")
def heartbeat(body: schemas.SessionRefIn, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    sess = db.get(models.ActiveSession, body.session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(404, "phiên không tồn tại (có thể đã bị đăng nhập máy khác chiếm lại)")
    sess.last_heartbeat = time.time()
    db.commit()
    return {"ok": True}


@router.post("/release")
def release(body: schemas.SessionRefIn, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    sess = db.get(models.ActiveSession, body.session_id)
    if sess and sess.user_id == user.id:
        db.delete(sess)
        db.commit()
    return {"ok": True}
