import json
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/events", status_code=202)
def events(body: schemas.EventsIn, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    for e in body.events:
        db.add(models.UsageEvent(user_id=user.id, device_fingerprint=body.device_fingerprint,
                                  ts=e.ts or time.time(), type=e.type,
                                  payload=json.dumps(e.payload, ensure_ascii=False)))
    db.commit()
    return {"ok": True, "count": len(body.events)}


@router.post("/error", status_code=202)
def error(body: schemas.ErrorIn, db: Session = Depends(get_db),
          user: models.User = Depends(get_current_user)):
    payload = {"message": body.message, "traceback": (body.traceback or "")[:4000]}
    db.add(models.UsageEvent(user_id=user.id, device_fingerprint=body.device_fingerprint,
                              type="error", payload=json.dumps(payload, ensure_ascii=False)))
    db.commit()
    return {"ok": True}
