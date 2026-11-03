from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .db import init_db
from .routers import admin, auth, library, releases
from .routers import session as session_router
from .routers import telemetry

app = FastAPI(title="EduXplore Ad Helper – Server")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

init_db()

app.include_router(auth.router)
app.include_router(session_router.router)
app.include_router(telemetry.router)
app.include_router(library.router)
app.include_router(releases.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {"name": "EduXplore Ad Helper Server", "status": "ok", "admin": "/admin/"}


@app.get("/healthz")
def healthz():
    return {"ok": True}
