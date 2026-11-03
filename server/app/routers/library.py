"""Thư viện công thức đóng quảng cáo — gộp 2 chiều, cùng thuật toán với library.py cục bộ."""
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/recipes")
def list_recipes(since: float = Query(0), db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    rows = db.query(models.LibraryRecipe).filter(models.LibraryRecipe.updated_at > since).all()
    return [{"key": r.key, "activity": r.activity, "kind": r.kind, "x": r.x, "y": r.y, "count": r.count,
             "sec_min": r.sec_min, "sec_max": r.sec_max, "sec_sum": r.sec_sum,
             "first_seen": r.first_seen, "last_seen": r.last_seen, "updated_at": r.updated_at}
            for r in rows]


@router.post("/recipes")
def push_recipes(body: schemas.RecipesPushIn, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    added = updated = 0
    for rc in body.recipes:
        row = db.get(models.LibraryRecipe, rc.key)
        if row is None:
            db.add(models.LibraryRecipe(key=rc.key, activity=rc.activity, kind=rc.kind, x=rc.x, y=rc.y,
                                         count=rc.count, sec_min=rc.sec_min, sec_max=rc.sec_max,
                                         sec_sum=rc.sec_sum, first_seen=rc.first_seen, last_seen=rc.last_seen,
                                         updated_at=time.time()))
            added += 1
        else:
            row.count += rc.count
            row.sec_sum += rc.sec_sum
            row.sec_min = min(row.sec_min, rc.sec_min)
            row.sec_max = max(row.sec_max, rc.sec_max)
            row.last_seen = max(row.last_seen, rc.last_seen)
            row.updated_at = time.time()
            updated += 1
    db.commit()
    return {"ok": True, "added": added, "updated": updated}
