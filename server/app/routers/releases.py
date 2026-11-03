from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..deps import get_db

router = APIRouter(prefix="/releases", tags=["releases"])


@router.get("/latest")
def latest(channel: str = "stable", db: Session = Depends(get_db)):
    r = (db.query(models.Release).filter_by(channel=channel)
         .order_by(models.Release.published_at.desc()).first())
    if not r:
        raise HTTPException(404, "chưa có bản phát hành cho kênh này")
    return {"version": r.version, "channel": r.channel, "download_url": r.download_url,
            "sha256": r.sha256, "notes": r.notes, "force_update": r.force_update,
            "published_at": r.published_at}
