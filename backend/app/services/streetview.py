"""Street view for an edit: nearest pano -> six faces -> equirect -> Gemini -> cached per version."""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.base import EditorError
from ..ai.prompts import streetview_prompt
from ..config import get_settings
from ..geo.streetview import StreetViewError, bearing_deg, fetch_faces, find_pano, haversine_m
from ..imaging import store
from ..imaging.panorama import cube_to_equirect
from ..models import Edit, EditVersion, StreetView, User
from ..schemas import StreetViewOut
from . import edits as svc_edits
from .edits import _check_rate, _editor_http, _limiter, _url, current_version, http_error, polygon_centroid

log = logging.getLogger(__name__)

_locks: dict[int, asyncio.Lock] = {}


def _lock_for(edit_id: int) -> asyncio.Lock:
    lock = _locks.get(edit_id)
    if lock is None:
        lock = _locks[edit_id] = asyncio.Lock()
    return lock


def street_view_out(row: StreetView) -> StreetViewOut:
    return StreetViewOut(
        id=row.id,
        edit_id=row.edit_id,
        version_id=row.version_id,
        version_number=row.version.version_number,
        pano_id=row.pano_id,
        lat=row.pano_lat,
        lng=row.pano_lng,
        heading=row.heading_deg,
        distance_m=row.distance_m,
        pano_date=row.pano_date,
        original_url=_url(row.original_path) or "",
        edited_url=_url(row.edited_path) or "",
        status=row.status,
        created_at=row.created_at,
    )


def latest_done(db: Session, edit: Edit) -> StreetView | None:
    """The finished street view for the newest version that has one (may be older than current)."""
    rows = db.execute(
        select(StreetView)
        .join(EditVersion, EditVersion.id == StreetView.version_id)
        .where(StreetView.edit_id == edit.id, StreetView.status == "done")
        .order_by(EditVersion.version_number.desc())
        .limit(1)
    )
    return rows.unique().scalars().first()


def cached_for(db: Session, edit: Edit, version: EditVersion) -> StreetView | None:
    return db.execute(
        select(StreetView).where(StreetView.edit_id == edit.id, StreetView.version_id == version.id)
    ).unique().scalars().first()


def _sv_http(exc: StreetViewError) -> HTTPException:
    settings = get_settings()
    status = {"no_street_view": 422, "streetview_not_configured": 503}.get(exc.code, 502)
    messages = {
        "no_street_view": f"No Street View imagery within {settings.streetview_max_radius_m} m of this site.",
        "streetview_not_configured": "Street view is not configured on this server (GOOGLE_STREET_VIEW_API_KEY).",
        "streetview_unavailable": f"Street View could not be loaded: {exc.message}",
    }
    log.warning("street view error %s: %s", exc.code, exc.message)
    return http_error(status, exc.code, messages.get(exc.code, exc.message))


async def generate_street_view(db: Session, user: User, edit: Edit) -> StreetView:
    settings = get_settings()
    version = current_version(edit)
    if version is None or not version.full_path:
        raise http_error(409, "not_ready", "This edit has no finished version to view yet.")
    row = cached_for(db, edit, version)
    if row is not None and row.status == "done":
        return row
    if not settings.google_street_view_api_key:
        raise _sv_http(StreetViewError("streetview_not_configured"))

    lock = _lock_for(edit.id)
    if lock.locked():
        raise http_error(409, "in_progress", "A street view is already being generated for this suggestion.")
    async with lock:
        row = cached_for(db, edit, version)
        if row is not None and row.status == "done":
            return row
        _check_rate(user)

        lng, lat = polygon_centroid(edit.polygon_geojson)
        try:
            pano = await find_pano(
                lat, lng, max_radius_m=settings.streetview_max_radius_m, api_key=settings.google_street_view_api_key
            )
        except StreetViewError as exc:
            _limiter.refund(user.id)
            raise _sv_http(exc)
        if pano is None:
            _limiter.refund(user.id)
            raise _sv_http(StreetViewError("no_street_view"))

        heading = bearing_deg(pano.lat, pano.lng, lat, lng)
        distance = haversine_m(pano.lat, pano.lng, lat, lng)
        if row is None:
            row = StreetView(edit_id=edit.id, version_id=version.id, created_by=user.id)
            db.add(row)
        row.pano_id = pano.pano_id
        row.pano_lat = pano.lat
        row.pano_lng = pano.lng
        row.pano_date = pano.date
        row.heading_deg = heading
        row.distance_m = distance
        row.status = "pending"
        row.error = None
        db.commit()
        db.refresh(row)

        asset_dir = store.asset_dir_of(edit.original_path)
        n = version.version_number
        try:
            faces = await fetch_faces(
                pano.pano_id,
                size_px=settings.streetview_face_px,
                fov=settings.streetview_face_fov,
                api_key=settings.google_street_view_api_key,
            )
            width = settings.streetview_pano_width
            equirect = await asyncio.to_thread(
                cube_to_equirect,
                faces,
                width,
                width // 2,
                center_heading_deg=heading,
                fov_deg=float(settings.streetview_face_fov),
            )
            row.original_path = await store.save_png(equirect, store.rel_path(asset_dir, f"sv{n}_original.png"))
            db.commit()

            original, edited = await asyncio.gather(
                store.load_image(edit.original_path), store.load_image(version.full_path)
            )
            history = [
                v.prompt
                for v in sorted(edit.versions, key=lambda v: v.version_number)
                if v.status == "done" and v.version_number <= n
            ]
            prompt = streetview_prompt(history, edit.place_name, distance)
            out = await svc_edits.get_editor().edit_panorama(equirect, [original, edited], prompt)
            row.edited_path = await store.save_png(out, store.rel_path(asset_dir, f"sv{n}_edited.png"))
            row.status = "done"
            db.commit()
            db.refresh(row)
            return row
        except (StreetViewError, EditorError) as exc:
            _limiter.refund(user.id)
            row.status = "failed"
            row.error = exc.code
            db.commit()
            raise _sv_http(exc) if isinstance(exc, StreetViewError) else _editor_http(exc)
        except Exception as exc:
            _limiter.refund(user.id)
            row.status = "failed"
            row.error = "error"
            db.commit()
            log.exception("street view generation failed for edit %d", edit.id)
            raise http_error(502, "streetview_unavailable", f"Street view generation failed ({exc}).")
