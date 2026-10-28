"""Create, refine and list edits. Orchestrates crop -> editor -> composite -> DB."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.base import EditorError
from ..ai.hints import hints_for
from ..ai.prompts import create_prompt, refine_prompt
from ..ai.registry import get_editor
from ..config import get_settings
from ..geo.crop import build_crop
from ..geo.places import reverse_geocode
from ..geo.validate import ValidationError, check_polygon_size, clean_prompt, parse_polygon
from ..imaging import store
from ..imaging.mask import make_overlay, polygon_mask
from ..models import Bookmark, Comment, Edit, EditVersion, User, Vote
from ..schemas import ContributionOut, EditOut, UserOut, VersionOut
from .ratelimit import RateLimiter

log = logging.getLogger(__name__)

_settings = get_settings()
_limiter = RateLimiter(_settings.generations_per_10_min)

IMAGE_URL_PREFIX = "/images/"


def http_error(status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message}, headers=headers)


def _validation_http(exc: ValidationError) -> HTTPException:
    return http_error(422, exc.code, exc.message)


def _editor_http(exc: EditorError) -> HTTPException:
    messages = {
        "out_of_scope": "That request is outside the scope of built-environment changes. Try describing a physical change to streets, buildings, parks or public space.",
        "refused": "The image model declined this request. Try rephrasing it.",
        "no_image": "The image model did not return an image. Please try again.",
        "busy": "The image service is busy right now. Please try again in a moment.",
        "timeout": "The image model took too long. Please try again.",
        "billing": f"Gemini refused the request because of billing/quota: {exc.message}",
        "bad_api_key": f"Gemini rejected the API key: {exc.message}",
    }
    headers = {"Retry-After": "20"} if exc.code == "busy" else None
    log.warning("editor error %s: %s", exc.code, exc.message)
    return http_error(exc.http_status, exc.code, messages.get(exc.code, exc.message), headers)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _url(rel: str | None) -> str | None:
    return (IMAGE_URL_PREFIX + rel) if rel else None


def version_out(v: EditVersion) -> VersionOut:
    return VersionOut(
        id=v.id,
        version_number=v.version_number,
        prompt=v.prompt,
        parent_version_id=v.parent_version_id,
        overlay_url=_url(v.overlay_path),
        full_url=_url(v.full_path),
        status=v.status,
        error=v.error,
        created_by=UserOut(id=v.creator.id, display_name=v.creator.display_name),
        created_at=v.created_at,
    )


def current_version(edit: Edit) -> EditVersion | None:
    done = [v for v in edit.versions if v.status == "done"]
    return max(done, key=lambda v: v.version_number) if done else None


def _aggregates(db: Session, edit_ids: list[int], user: User | None):
    if not edit_ids:
        return {}, {}, {}, set()
    vote_rows = db.execute(
        select(
            Vote.edit_id,
            func.coalesce(func.sum(Vote.value), 0),
            func.sum(func.iif(Vote.value > 0, 1, 0)),
            func.sum(func.iif(Vote.value < 0, 1, 0)),
        )
        .where(Vote.edit_id.in_(edit_ids))
        .group_by(Vote.edit_id)
    ).all()
    votes = {r[0]: (int(r[1]), int(r[2] or 0), int(r[3] or 0)) for r in vote_rows}
    comment_rows = db.execute(
        select(Comment.edit_id, func.count(Comment.id)).where(Comment.edit_id.in_(edit_ids)).group_by(Comment.edit_id)
    ).all()
    comments = {r[0]: int(r[1]) for r in comment_rows}
    my = {}
    saved: set[int] = set()
    if user is not None:
        my_rows = db.execute(
            select(Vote.edit_id, Vote.value).where(Vote.edit_id.in_(edit_ids), Vote.user_id == user.id)
        ).all()
        my = {r[0]: int(r[1]) for r in my_rows}
        saved = {
            r[0]
            for r in db.execute(
                select(Bookmark.edit_id).where(Bookmark.edit_id.in_(edit_ids), Bookmark.user_id == user.id)
            ).all()
        }
    return votes, comments, my, saved


def edit_out(edit: Edit, votes, comments, my, saved: set[int] | None = None) -> EditOut:
    score, up, down = votes.get(edit.id, (0, 0, 0))
    cv = current_version(edit)
    first = min(edit.versions, key=lambda v: v.version_number) if edit.versions else None
    return EditOut(
        id=edit.id,
        polygon=json.loads(edit.polygon_geojson),
        bounds=edit.bounds,
        status=edit.status,
        error=edit.error,
        created_by=UserOut(id=edit.creator.id, display_name=edit.creator.display_name),
        created_at=edit.created_at,
        updated_at=edit.updated_at,
        current_version=version_out(cv) if cv else None,
        original_prompt=first.prompt if first else "",
        version_count=sum(1 for v in edit.versions if v.status == "done"),
        score=score,
        up=up,
        down=down,
        my_vote=my.get(edit.id, 0),
        comment_count=comments.get(edit.id, 0),
        original_url=_url(edit.original_path) or "",
        place_name=edit.place_name,
        saved=edit.id in (saved or set()),
    )


def serialize_edits(db: Session, edits: list[Edit], user: User | None) -> list[EditOut]:
    votes, comments, my, saved = _aggregates(db, [e.id for e in edits], user)
    return [edit_out(e, votes, comments, my, saved) for e in edits]


def polygon_centroid(polygon_geojson: str) -> tuple[float, float]:
    ring = json.loads(polygon_geojson)["coordinates"][0]
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    a = cx = cy = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-12:
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a))


def serialize_edit(db: Session, edit: Edit, user: User | None) -> EditOut:
    return serialize_edits(db, [edit], user)[0]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def list_edits(db: Session, bbox: tuple[float, float, float, float] | None, user: User | None) -> list[EditOut]:
    stmt = select(Edit).where(Edit.status != "failed").order_by(Edit.created_at.desc())
    if bbox is not None:
        w, s, e, n = bbox
        stmt = stmt.where(Edit.bounds_e >= w, Edit.bounds_w <= e, Edit.bounds_n >= s, Edit.bounds_s <= n)
    edits = list(db.execute(stmt).unique().scalars().all())
    return serialize_edits(db, edits, user)


def get_edit_or_404(db: Session, edit_id: int) -> Edit:
    edit = db.get(Edit, edit_id)
    if edit is None:
        raise http_error(404, "not_found", "That edit no longer exists.")
    return edit


def list_contributions(db: Session, user: User) -> list[ContributionOut]:
    """Everything this user generated: their own edits (v1) and refinements of any edit."""
    versions = list(
        db.execute(
            select(EditVersion)
            .where(EditVersion.created_by == user.id, EditVersion.status == "done")
            .order_by(EditVersion.created_at.desc())
        )
        .unique()
        .scalars()
        .all()
    )
    edits = {v.edit_id: v.edit for v in versions}
    votes, _, _, _ = _aggregates(db, list(edits), user)
    out: list[ContributionOut] = []
    for v in versions:
        e = v.edit
        if e is None or e.status == "failed":
            continue
        first = min(e.versions, key=lambda x: x.version_number) if e.versions else None
        out.append(
            ContributionOut(
                version_id=v.id,
                edit_id=e.id,
                kind="edit" if v.version_number == 1 else "refinement",
                prompt=v.prompt,
                version_number=v.version_number,
                created_at=v.created_at,
                place_name=e.place_name,
                centroid=polygon_centroid(e.polygon_geojson),
                edit_original_prompt=first.prompt if first else "",
                edit_creator=UserOut(id=e.creator.id, display_name=e.creator.display_name),
                edit_status=e.status,
                score=votes.get(e.id, (0, 0, 0))[0],
            )
        )
    return out


def list_saved(db: Session, user: User) -> list[EditOut]:
    rows = db.execute(
        select(Edit)
        .join(Bookmark, Bookmark.edit_id == Edit.id)
        .where(Bookmark.user_id == user.id, Edit.status != "failed")
        .order_by(Bookmark.created_at.desc())
    )
    return serialize_edits(db, list(rows.unique().scalars().all()), user)


def set_bookmark(db: Session, user: User, edit: Edit, saved: bool) -> bool:
    existing = db.get(Bookmark, (user.id, edit.id))
    if saved and existing is None:
        db.add(Bookmark(user_id=user.id, edit_id=edit.id))
    elif not saved and existing is not None:
        db.delete(existing)
    db.commit()
    return saved


async def delete_edit(db: Session, user: User, edit: Edit) -> None:
    if edit.created_by != user.id:
        raise http_error(403, "forbidden", "Only the person who created this suggestion can delete it.")
    if any(v.status == "pending" for v in edit.versions):
        raise http_error(409, "in_progress", "Wait for the current generation to finish before deleting.")
    edit_id = edit.id
    # Versions reference each other through parent_version_id; break the chain first so
    # the cascade can delete them in any order.
    for v in edit.versions:
        v.parent_version_id = None
    db.flush()
    db.delete(edit)
    db.commit()
    await asyncio.to_thread(store.delete_edit_files_sync, edit_id)


async def backfill_place_names(limit: int = 200) -> int:
    """Geocode edits created before place names existed. Runs in the background at startup."""
    from ..db import SessionLocal

    done = 0
    with SessionLocal() as db:
        edits = list(
            db.execute(select(Edit).where(Edit.place_name.is_(None), Edit.status != "failed").limit(limit))
            .unique()
            .scalars()
            .all()
        )
        for e in edits:
            lng, lat = polygon_centroid(e.polygon_geojson)
            name = await reverse_geocode(lng, lat)
            if name:
                e.place_name = name
                db.commit()
                done += 1
    return done


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _check_rate(user: User) -> None:
    wait = _limiter.check(user.id)
    if wait is not None:
        raise http_error(
            429,
            "rate_limited",
            f"You have reached the generation limit. Try again in about {int(wait // 60) + 1} minutes.",
            {"Retry-After": str(int(wait))},
        )


async def create_edit(db: Session, user: User, polygon: dict, prompt: str) -> Edit:
    settings = get_settings()
    try:
        prompt = clean_prompt(prompt)
        ring = parse_polygon(polygon)
        check_polygon_size(ring, settings.max_bbox_km2, settings.min_poly_m2)
    except ValidationError as exc:
        raise _validation_http(exc)
    _check_rate(user)

    closed = [[lng, lat] for lng, lat in ring]
    polygon_json = json.dumps({"type": "Polygon", "coordinates": [closed]})
    c_lng, c_lat = polygon_centroid(polygon_json)
    try:
        crop, place_name = await asyncio.gather(
            build_crop(
                ring,
                min_zoom=settings.min_zoom,
                max_zoom=settings.max_zoom,
                target_min_px=settings.target_min_px,
                margin=settings.context_margin,
            ),
            reverse_geocode(c_lng, c_lat),
        )
    except Exception as exc:
        _limiter.refund(user.id)
        log.exception("tile stitching failed")
        raise http_error(502, "tiles_unavailable", f"Could not load satellite imagery for that area ({exc}).")

    rect = crop.rect
    w, s, e, n = rect.bounds
    edit = Edit(
        polygon_geojson=polygon_json,
        place_name=place_name,
        bounds_w=w,
        bounds_s=s,
        bounds_e=e,
        bounds_n=n,
        zoom=rect.z,
        crop_x0=rect.x0,
        crop_y0=rect.y0,
        crop_x1=rect.x1,
        crop_y1=rect.y1,
        crop_w=crop.image.width,
        crop_h=crop.image.height,
        polygon_px_json=json.dumps(crop.polygon_px),
        scale=crop.scale,
        aspect_name=rect.aspect_name,
        original_path="",
        mask_path="",
        status="pending",
        created_by=user.id,
    )
    db.add(edit)
    db.flush()
    edit.original_path = store.rel_path(edit.id, "original.png")
    edit.mask_path = store.rel_path(edit.id, "mask.png")
    version = EditVersion(edit_id=edit.id, version_number=1, prompt=prompt, status="pending", created_by=user.id)
    db.add(version)
    db.commit()
    db.refresh(edit)

    mask = await asyncio.to_thread(polygon_mask, crop.image.size, crop.polygon_px)
    await store.save_png(crop.image, edit.original_path)
    await store.save_png(mask, edit.mask_path)

    try:
        hints = hints_for(prompt)
        if hints:
            log.info("edit %d: %d prompt hint(s) matched", edit.id, len(hints))
        await _generate_version(
            db, edit, version, base=crop.image, mask=mask, prompt_text=create_prompt(prompt, settings.region_hint, hints)
        )
    except EditorError as exc:
        _limiter.refund(user.id)
        db.delete(edit)
        db.commit()
        await asyncio.to_thread(store.delete_edit_files_sync, edit.id)
        raise _editor_http(exc)

    edit.status = "done"
    db.commit()
    db.refresh(edit)
    return edit


async def refine_edit(db: Session, user: User, edit: Edit, prompt: str) -> Edit:
    settings = get_settings()
    try:
        prompt = clean_prompt(prompt)
    except ValidationError as exc:
        raise _validation_http(exc)
    base_version = current_version(edit)
    if base_version is None or not base_version.full_path:
        raise http_error(409, "not_ready", "This edit has no finished version to refine yet.")
    if any(v.status == "pending" for v in edit.versions):
        raise http_error(409, "in_progress", "Another refinement is already in progress for this edit.")
    _check_rate(user)

    next_number = max(v.version_number for v in edit.versions) + 1
    version = EditVersion(
        edit_id=edit.id,
        version_number=next_number,
        prompt=prompt,
        parent_version_id=base_version.id,
        status="pending",
        created_by=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    base = await store.load_image(base_version.full_path)
    mask = await store.load_image(edit.mask_path)
    history = [v.prompt for v in sorted(edit.versions, key=lambda v: v.version_number) if v.status == "done"]
    hints = hints_for(prompt)
    try:
        await _generate_version(
            db,
            edit,
            version,
            base=base,
            mask=mask,
            prompt_text=refine_prompt(prompt, history, settings.region_hint, hints),
        )
    except EditorError as exc:
        _limiter.refund(user.id)
        version.status = "failed"
        version.error = exc.code
        db.commit()
        raise _editor_http(exc)

    edit.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(edit)
    return edit


async def _generate_version(db: Session, edit: Edit, version: EditVersion, *, base, mask, prompt_text: str) -> None:
    settings = get_settings()
    editor = get_editor()
    hint_mask = mask if settings.region_hint == "mask" else None
    full = await editor.edit(base, hint_mask, prompt_text, edit.aspect_name)
    overlay = await asyncio.to_thread(make_overlay, full, mask)
    n = version.version_number
    version.full_path = await store.save_png(full, store.rel_path(edit.id, f"v{n}_full.png"))
    version.overlay_path = await store.save_png(overlay, store.rel_path(edit.id, f"v{n}_overlay.png"))
    version.status = "done"
    db.commit()


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


def cleanup_stale_pending(db: Session, older_than_minutes: int = 5) -> int:
    """Mark rows left 'pending' by a crashed process as failed."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    count = 0
    for v in db.execute(select(EditVersion).where(EditVersion.status == "pending")).scalars():
        created = v.created_at if v.created_at.tzinfo else v.created_at.replace(tzinfo=timezone.utc)
        if created < cutoff:
            v.status = "failed"
            v.error = "interrupted"
            count += 1
    for e in db.execute(select(Edit).where(Edit.status == "pending")).scalars():
        created = e.created_at if e.created_at.tzinfo else e.created_at.replace(tzinfo=timezone.utc)
        if created < cutoff:
            e.status = "done" if current_version(e) else "failed"
            count += 1
    db.commit()
    return count
