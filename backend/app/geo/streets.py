"""Nearest real street to a point, from OpenStreetMap via Overpass.

Street View panoramas exist on alleys, parking aisles and driveways too, so asking Google for
the panorama nearest an edit's centroid often lands behind the buildings. Instead we snap the
centroid to the closest mapped *street* (service roads, tracks and footpaths excluded) and ask
for a panorama from that point.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from .osm import OverpassError, query_overpass

log = logging.getLogger(__name__)

# Highway classes that count as a street. `service` (alleys, driveways, parking aisles) and all
# path classes are deliberately absent.
STREET_CLASSES = frozenset(
    {
        "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
        "living_street", "pedestrian", "busway", "road",
        "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
    }
)
_STREET_RE = "^(" + "|".join(sorted(STREET_CLASSES)) + ")$"

# Unnamed streets (slip roads, unnamed connectors) lose a little ground to named ones so the
# panorama ends up on the street a resident would name.
UNNAMED_PENALTY_M = 20.0

QUERY = (
    """[out:json][timeout:15];
way["highway"~\""""
    + _STREET_RE
    + """\"]["area"!="yes"]["tunnel"!="yes"](around:{r},{lat},{lng});
out geom qt;"""
)


@dataclass(frozen=True)
class StreetPoint:
    name: str | None
    highway: str
    lng: float
    lat: float
    distance_m: float


# ---------------------------------------------------------------------------
# Geometry (local equirectangular metres around the query point)
# ---------------------------------------------------------------------------

_M_PER_DEG_LAT = 111_320.0


def _nearest_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> tuple[float, float, float]:
    """Closest point to P on segment AB and its distance, in the same (metric) units."""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    qx, qy = ax + t * dx, ay + t * dy
    return qx, qy, math.hypot(px - qx, py - qy)


def pick_street(elements: list[dict], lng: float, lat: float) -> StreetPoint | None:
    """The best street among Overpass `way` elements (with geometry) for the point: nearest by
    distance, with a small penalty for unnamed ways. Pure, for tests."""
    k = math.cos(math.radians(lat)) * _M_PER_DEG_LAT
    best: tuple[float, StreetPoint] | None = None
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        if tags.get("highway") not in STREET_CLASSES:
            continue
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        pts = [((p["lon"] - lng) * k, (p["lat"] - lat) * _M_PER_DEG_LAT) for p in geom]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            qx, qy, d = _nearest_on_segment(0.0, 0.0, ax, ay, bx, by)
            name = tags.get("name") or tags.get("ref")
            score = d + (0.0 if name else UNNAMED_PENALTY_M)
            if best is None or score < best[0]:
                best = (
                    score,
                    StreetPoint(
                        name=name,
                        highway=tags["highway"],
                        lng=lng + qx / k,
                        lat=lat + qy / _M_PER_DEG_LAT,
                        distance_m=d,
                    ),
                )
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


async def nearest_street(lng: float, lat: float, *, radius_m: float) -> StreetPoint | None:
    """Closest street within `radius_m`, or None when nothing is mapped or Overpass is down.
    Never raises: callers fall back to the raw point."""
    try:
        elements = await query_overpass(QUERY.format(r=int(radius_m), lat=f"{lat:.6f}", lng=f"{lng:.6f}"))
    except OverpassError as exc:
        log.warning("nearest street lookup failed: %s", exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive; the street snap is best-effort
        log.warning("nearest street lookup failed: %s", exc)
        return None
    street = pick_street(elements, lng, lat)
    if street is not None:
        log.info("nearest street to %.5f,%.5f: %s (%s) %.0f m away", lat, lng, street.name or "unnamed", street.highway, street.distance_m)
    return street
