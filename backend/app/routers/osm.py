"""Map features for smart select (buildings, lots, green space, road segments)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..geo import osm
from ..models import User
from ..services.edits import http_error

log = logging.getLogger(__name__)

router = APIRouter(prefix="/osm", tags=["osm"])

MAX_CELL_INDEX = int(180 / osm.CELL_DEG) + 1


class PrefetchIn(BaseModel):
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-85, le=85)


@router.get("/cell/{ix}/{iy}")
async def cell(ix: int, iy: int) -> dict:
    if abs(ix) > MAX_CELL_INDEX or abs(iy) > int(85 / osm.CELL_DEG) + 1:
        raise http_error(422, "cell_invalid", "Cell index out of range.")
    try:
        return await osm.get_cell(ix, iy)
    except osm.OverpassError as exc:
        log.warning("osm cell %d,%d failed: %s", ix, iy, exc)
        raise http_error(503, "osm_unavailable", "Map features are temporarily unavailable. Try again in a moment.", {"Retry-After": "15"})


@router.post("/prefetch")
async def prefetch(body: PrefetchIn, _user: User = Depends(get_current_user)) -> dict:
    """Warm the 3x3 cells around the user's start location in the background."""
    return {"queued": osm.schedule_prefetch(body.lng, body.lat)}
