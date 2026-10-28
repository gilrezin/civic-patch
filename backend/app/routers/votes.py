from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User, Vote
from ..schemas import VoteIn, VoteOut
from ..services import edits as svc

router = APIRouter(prefix="/edits", tags=["votes"])


@router.put("/{edit_id}/vote", response_model=VoteOut)
def vote(edit_id: int, body: VoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> VoteOut:
    svc.get_edit_or_404(db, edit_id)
    existing = db.get(Vote, (user.id, edit_id))
    if body.value == 0:
        if existing is not None:
            db.delete(existing)
    elif existing is None:
        db.add(Vote(user_id=user.id, edit_id=edit_id, value=body.value))
    else:
        existing.value = body.value
    db.commit()
    votes, _, my = svc._aggregates(db, [edit_id], user)
    score, up, down = votes.get(edit_id, (0, 0, 0))
    return VoteOut(score=score, up=up, down=down, my_vote=my.get(edit_id, 0))
