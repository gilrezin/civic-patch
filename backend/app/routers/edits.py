from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_optional_user
from ..db import get_db
from ..models import User
from ..schemas import BookmarkIn, BookmarkOut, EditCreateIn, EditOut, RefineIn, StreetViewOut, VersionOut
from ..services import edits as svc
from ..services import streetview as sv

router = APIRouter(prefix="/edits", tags=["edits"])


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        w, s, e, n = (float(p) for p in bbox.split(","))
    except ValueError:
        raise svc.http_error(422, "bbox_invalid", "bbox must be W,S,E,N")
    return (w, s, e, n)


@router.get("", response_model=list[EditOut])
def list_edits(
    bbox: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> list[EditOut]:
    return svc.list_edits(db, _parse_bbox(bbox), user)


@router.get("/{edit_id}", response_model=EditOut)
def get_edit(edit_id: int, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)) -> EditOut:
    return svc.serialize_edit(db, svc.get_edit_or_404(db, edit_id), user)


@router.post("", response_model=EditOut, status_code=201)
async def create_edit(body: EditCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> EditOut:
    edit = await svc.create_edit(
        db, user, body.prompt, polygon=body.polygon, highlight=body.highlight, smart=body.smart, mask=body.mask
    )
    return svc.serialize_edit(db, edit, user)


@router.post("/{edit_id}/refine", response_model=EditOut)
async def refine_edit(
    edit_id: int, body: RefineIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> EditOut:
    edit = svc.get_edit_or_404(db, edit_id)
    edit = await svc.refine_edit(db, user, edit, body.prompt)
    return svc.serialize_edit(db, edit, user)


@router.get("/{edit_id}/versions", response_model=list[VersionOut])
def list_versions(edit_id: int, db: Session = Depends(get_db)) -> list[VersionOut]:
    edit = svc.get_edit_or_404(db, edit_id)
    return [svc.version_out(v) for v in sorted(edit.versions, key=lambda v: v.version_number)]


@router.get("/{edit_id}/street-view", response_model=StreetViewOut)
def get_street_view(edit_id: int, db: Session = Depends(get_db)) -> StreetViewOut:
    """Newest finished street view for this edit (may predate the current version)."""
    edit = svc.get_edit_or_404(db, edit_id)
    row = sv.latest_done(db, edit)
    if row is None:
        raise svc.http_error(404, "not_generated", "No street view has been generated for this suggestion yet.")
    return sv.street_view_out(row)


@router.post("/{edit_id}/street-view", response_model=StreetViewOut)
async def generate_street_view(
    edit_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> StreetViewOut:
    edit = svc.get_edit_or_404(db, edit_id)
    return sv.street_view_out(await sv.generate_street_view(db, user, edit))


@router.delete("/{edit_id}", status_code=204, response_class=Response)
async def delete_edit(edit_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    edit = svc.get_edit_or_404(db, edit_id)
    await svc.delete_edit(db, user, edit)
    return Response(status_code=204)


@router.put("/{edit_id}/bookmark", response_model=BookmarkOut)
def bookmark(
    edit_id: int, body: BookmarkIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> BookmarkOut:
    edit = svc.get_edit_or_404(db, edit_id)
    return BookmarkOut(saved=svc.set_bookmark(db, user, edit, body.saved))
