"""Map features for smart select (buildings, lots, green space, road segments)."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from ..geo import osm
from ..services.edits import http_error

log = logging.getLogger(__name__)

router = APIRouter(prefix="/osm", tags=["osm"])

MAX_CELL_INDEX = int(180 / osm.CELL_DEG) + 1


@router.get("/cell/{ix}/{iy}")
async def cell(ix: int, iy: int) -> dict:
    if abs(ix) > MAX_CELL_INDEX or abs(iy) > int(85 / osm.CELL_DEG) + 1:
        raise http_error(422, "cell_invalid", "Cell index out of range.")
    try:
        return await osm.get_cell(ix, iy)
    except osm.OverpassError as exc:
        log.warning("osm cell %d,%d failed: %s", ix, iy, exc)
        raise http_error(503, "osm_unavailable", "Map features are temporarily unavailable. Try again in a moment.", {"Retry-After": "15"})
