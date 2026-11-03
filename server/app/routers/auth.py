import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config, models, schemas, security
from ..deps import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(models.User).filter_by(email=email).first():
        raise HTTPException(409, "email đã đăng ký")
    if len(body.password) < 6:
        raise HTTPException(400, "mật khẩu tối thiểu 6 ký tự")
    salt, h = security.hash_password(body.password)
    db.add(models.User(email=email, password_hash=h, password_salt=salt, plan="free"))
    db.commit()
    return {"ok": True}


def _claim_session(db: Session, user: models.User, device_fingerprint) -> models.ActiveSession:
    """Chỉ 1 máy đăng nhập tại 1 thời điểm (SERVER_DESIGN.md mục 4, bản đơn giản hoá — khoá theo tài khoản
    đăng nhập, không đọc tài khoản game). Máy khác đang đăng nhập (còn nhịp tim) -> 409. Cùng máy (cùng
    device_fingerprint) -> GIỮ NGUYÊN session cũ (chỉ cập nhật nhịp tim) để session_id ổn định qua các lần
    /auth/refresh — tạo mới mỗi lần sẽ làm session_id phía client cũ bị lệch khỏi session thực tế đang sống."""
    now = time.time()
    existing = db.query(models.ActiveSession).filter_by(user_id=user.id).all()
    same = None
    for s in existing:
        alive = now - s.last_heartbeat < config.HEARTBEAT_TIMEOUT_SEC
        same_device = device_fingerprint and s.device_fingerprint == device_fingerprint
        if same_device:
            same = s
        elif alive:
            raise HTTPException(409, "tài khoản đang đăng nhập ở máy khác")
    for s in existing:
        if s is not same:
            db.delete(s)
    if same:
        same.last_heartbeat = now
        return same
    sess = models.ActiveSession(user_id=user.id, device_fingerprint=device_fingerprint)
    db.add(sess)
    return sess


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=body.email.lower()).first()
    if not user or not security.verify_password(body.password, user.password_salt, user.password_hash):
        raise HTTPException(401, "sai email hoặc mật khẩu")
    if not user.is_active:
        raise HTTPException(403, "tài khoản đã bị khoá")
    sess = _claim_session(db, user, body.device_fingerprint)
    access = security.create_access_token(user.id, user.plan)
    refresh = security.new_refresh_token()
    db.add(models.RefreshToken(user_id=user.id, token_hash=security.hash_token(refresh),
                                device_fingerprint=body.device_fingerprint,
                                expires_at=time.time() + config.REFRESH_TOKEN_DAYS * 86400))
    db.commit()
    return schemas.TokenOut(access_token=access, refresh_token=refresh,
                             entitlements=config.ENTITLEMENTS.get(user.plan, config.ENTITLEMENTS["free"]),
                             plan=user.plan, session_id=sess.id)


@router.post("/refresh", response_model=schemas.TokenOut)
def refresh(body: schemas.RefreshIn, db: Session = Depends(get_db)):
    h = security.hash_token(body.refresh_token)
    rt = db.query(models.RefreshToken).filter_by(token_hash=h, revoked=False).first()
    if not rt or rt.expires_at < time.time():
        raise HTTPException(401, "refresh token không hợp lệ hoặc hết hạn")
    user = db.get(models.User, rt.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "tài khoản không hợp lệ")
    # tự mở app lại (không qua /login) vẫn phải qua cùng khoá 1-máy-1-lúc, không thì máy khác lách được
    sess = _claim_session(db, user, body.device_fingerprint or rt.device_fingerprint)
    access = security.create_access_token(user.id, user.plan)
    db.commit()
    return schemas.TokenOut(access_token=access, refresh_token=body.refresh_token,
                             entitlements=config.ENTITLEMENTS.get(user.plan, config.ENTITLEMENTS["free"]),
                             plan=user.plan, session_id=sess.id)


@router.post("/logout")
def logout(body: schemas.LogoutIn, db: Session = Depends(get_db)):
    h = security.hash_token(body.refresh_token)
    rt = db.query(models.RefreshToken).filter_by(token_hash=h).first()
    if rt:
        rt.revoked = True
        if body.session_id:
            sess = db.get(models.ActiveSession, body.session_id)
            if sess and sess.user_id == rt.user_id:
                db.delete(sess)
        db.commit()
    return {"ok": True}
