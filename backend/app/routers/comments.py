from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Comment, User
from ..schemas import CommentIn, CommentOut, UserOut
from ..services import edits as svc

router = APIRouter(prefix="/edits", tags=["comments"])


def _out(c: Comment) -> CommentOut:
    return CommentOut(
        id=c.id,
        edit_id=c.edit_id,
        body=c.body,
        author=UserOut(id=c.author.id, display_name=c.author.display_name),
        created_at=c.created_at,
    )


@router.get("/{edit_id}/comments", response_model=list[CommentOut])
def list_comments(edit_id: int, db: Session = Depends(get_db)) -> list[CommentOut]:
    svc.get_edit_or_404(db, edit_id)
    rows = db.execute(select(Comment).where(Comment.edit_id == edit_id).order_by(Comment.created_at.asc())).scalars()
    return [_out(c) for c in rows]


@router.post("/{edit_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    edit_id: int, body: CommentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> CommentOut:
    svc.get_edit_or_404(db, edit_id)
    text = body.body.strip()
    if not text:
        raise svc.http_error(422, "comment_empty", "Comments cannot be empty.")
    c = Comment(edit_id=edit_id, user_id=user.id, body=text)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _out(c)
