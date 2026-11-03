"""Giao diện quản trị (web, server-rendered). Đăng nhập bằng 1 mật khẩu quản trị (EDUXPLORE_ADMIN_PASSWORD),
phiên lưu qua cookie ký bằng SECRET_KEY (SessionMiddleware ở main.py). Không phải API cho exe — exe dùng
các router auth/session/telemetry/library/releases ở trên.
"""
import datetime
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import config, models
from ..deps import get_db

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
templates.env.filters["ts"] = lambda t: (
    datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S") if t else "-")


def _is_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


# ---------------------------------------------------------------- đăng nhập
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    if password != config.ADMIN_PASSWORD:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Sai mật khẩu"})
    request.session["admin"] = True
    return RedirectResponse("/admin/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# ---------------------------------------------------------------- tổng quan
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    now = time.time()
    stats = {
        "users": db.query(models.User).count(),
        "pro": db.query(models.User).filter_by(plan="pro").count(),
        "active_sessions": db.query(models.ActiveSession)
            .filter(models.ActiveSession.last_heartbeat > now - config.HEARTBEAT_TIMEOUT_SEC).count(),
        "events_today": db.query(models.UsageEvent).filter(models.UsageEvent.ts > now - 86400).count(),
        "errors_today": db.query(models.UsageEvent)
            .filter(models.UsageEvent.ts > now - 86400, models.UsageEvent.type == "error").count(),
        "recipes": db.query(models.LibraryRecipe).count(),
    }
    errors = (db.query(models.UsageEvent).filter_by(type="error")
              .order_by(models.UsageEvent.ts.desc()).limit(10).all())
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats, "errors": errors})


# ---------------------------------------------------------------- người dùng
@router.get("/users", response_class=HTMLResponse)
def users_list(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return templates.TemplateResponse("users.html", {"request": request, "users": users})


@router.post("/users/{user_id}/plan")
def set_plan(user_id: str, request: Request, plan: str = Form(...), db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    u = db.get(models.User, user_id)
    if u and plan in ("free", "pro"):
        u.plan = plan
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle_active")
def toggle_active(user_id: str, request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    u = db.get(models.User, user_id)
    if u:
        u.is_active = not u.is_active
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


# ---------------------------------------------------------------- phiên đang chạy
@router.get("/sessions", response_class=HTMLResponse)
def sessions_list(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    sessions = db.query(models.ActiveSession).order_by(models.ActiveSession.last_heartbeat.desc()).all()
    users = {u.id: u.email for u in db.query(models.User).all()}
    return templates.TemplateResponse("sessions.html", {
        "request": request, "sessions": sessions, "users": users,
        "now": time.time(), "timeout": config.HEARTBEAT_TIMEOUT_SEC})


@router.post("/sessions/{session_id}/kick")
def kick_session(session_id: str, request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    s = db.get(models.ActiveSession, session_id)
    if s:
        db.delete(s)
        db.commit()
    return RedirectResponse("/admin/sessions", status_code=303)


# ---------------------------------------------------------------- nhật ký
@router.get("/events", response_class=HTMLResponse)
def events_list(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    events = db.query(models.UsageEvent).order_by(models.UsageEvent.ts.desc()).limit(200).all()
    users = {u.id: u.email for u in db.query(models.User).all()}
    return templates.TemplateResponse("events.html", {"request": request, "events": events, "users": users})


# ---------------------------------------------------------------- thư viện
@router.get("/library", response_class=HTMLResponse)
def library_view(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    recipes = db.query(models.LibraryRecipe).order_by(models.LibraryRecipe.count.desc()).limit(200).all()
    return templates.TemplateResponse("library.html", {"request": request, "recipes": recipes})


# ---------------------------------------------------------------- bản phát hành
@router.get("/releases", response_class=HTMLResponse)
def releases_list(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    releases = db.query(models.Release).order_by(models.Release.published_at.desc()).all()
    return templates.TemplateResponse("releases.html", {"request": request, "releases": releases})


@router.post("/releases/new")
def releases_new(request: Request, version: str = Form(...), channel: str = Form("stable"),
                  download_url: str = Form(...), sha256: str = Form(""), notes: str = Form(""),
                  force_update: bool = Form(False), db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login")
    db.add(models.Release(version=version, channel=channel, download_url=download_url,
                           sha256=sha256, notes=notes, force_update=force_update))
    db.commit()
    return RedirectResponse("/admin/releases", status_code=303)
