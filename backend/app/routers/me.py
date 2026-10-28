"""Per-user lists: contributions ("My Edits") and bookmarks ("Saved")."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import ContributionOut, EditOut
from ..services import edits as svc

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/contributions", response_model=list[ContributionOut])
def contributions(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ContributionOut]:
    return svc.list_contributions(db, user)


@router.get("/saved", response_model=list[EditOut])
def saved(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[EditOut]:
    return svc.list_saved(db, user)
