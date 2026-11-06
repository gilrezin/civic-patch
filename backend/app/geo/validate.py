"""Validation of polygons and prompts coming from the client."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

Ring = list[tuple[float, float]]

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")

PROMPT_MIN = 3
PROMPT_MAX = 300


class ValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def clean_prompt(prompt: str) -> str:
    p = _WS_RE.sub(" ", (prompt or "")).strip()
    if len(p) < PROMPT_MIN:
        raise ValidationError("prompt_too_short", "Please describe the change in a few words.")
    if len(p) > PROMPT_MAX:
        raise ValidationError("prompt_too_long", f"Prompts are limited to {PROMPT_MAX} characters.")
    if _URL_RE.search(p):
        raise ValidationError("prompt_invalid", "Links are not allowed in prompts.")
    if not re.search(r"[A-Za-z0-9]", p):
        raise ValidationError("prompt_invalid", "Please write a prompt with words in it.")
    return p


def parse_polygon(geojson: Any) -> Ring:
    """Accept a GeoJSON Polygon dict and return a closed ring of (lng, lat)."""
    if not isinstance(geojson, dict) or geojson.get("type") != "Polygon":
        raise ValidationError("polygon_invalid", "Expected a GeoJSON Polygon.")
    coords = geojson.get("coordinates")
    if not isinstance(coords, list) or len(coords) != 1:
        raise ValidationError("polygon_invalid", "Polygon must have exactly one ring.")
    raw = coords[0]
    if not isinstance(raw, list):
        raise ValidationError("polygon_invalid", "Polygon ring must be a list.")
    ring: Ring = []
    for pt in raw:
        if not (isinstance(pt, (list, tuple)) and len(pt) >= 2):
            raise ValidationError("polygon_invalid", "Each coordinate must be [lng, lat].")
        lng, lat = float(pt[0]), float(pt[1])
        if not (math.isfinite(lng) and math.isfinite(lat)):
            raise ValidationError("polygon_invalid", "Coordinates must be finite numbers.")
        if abs(lng) > 180 or abs(lat) > 85:
            raise ValidationError("polygon_invalid", "Coordinates out of range.")
        ring.append((lng, lat))
    if len(ring) >= 2 and ring[0] != ring[-1]:
        ring.append(ring[0])
    if len(ring) < 4:
        raise ValidationError("polygon_invalid", "A polygon needs at least three points.")
    if len(ring) > 201:
        raise ValidationError("polygon_invalid", "Too many vertices (max 200).")
    return ring


@dataclass(frozen=True)
class Stroke:
    """One highlighter stroke: a polyline in lng/lat with a ground width in metres."""

    coords: list[tuple[float, float]]
    width_m: float


MAX_STROKES = 60
MAX_STROKE_POINTS = 800
MIN_STROKE_WIDTH_M = 0.3
MAX_STROKE_WIDTH_M = 120.0


def parse_highlight(data: Any) -> list[Stroke]:
    if not isinstance(data, dict) or not isinstance(data.get("strokes"), list):
        raise ValidationError("highlight_invalid", "Expected a highlight with a list of strokes.")
    raw_strokes = data["strokes"]
    if not raw_strokes:
        raise ValidationError("highlight_empty", "Highlight at least one area first.")
    if len(raw_strokes) > MAX_STROKES:
        raise ValidationError("highlight_invalid", f"Too many strokes (max {MAX_STROKES}).")
    strokes: list[Stroke] = []
    for s in raw_strokes:
        if not isinstance(s, dict):
            raise ValidationError("highlight_invalid", "Each stroke must be an object.")
        try:
            width = float(s.get("width_m"))
        except (TypeError, ValueError):
            raise ValidationError("highlight_invalid", "Stroke width must be a number.")
        if not math.isfinite(width):
            raise ValidationError("highlight_invalid", "Stroke width must be finite.")
        width = max(MIN_STROKE_WIDTH_M, min(MAX_STROKE_WIDTH_M, width))
        pts = s.get("coordinates")
        if not isinstance(pts, list) or not pts:
            raise ValidationError("highlight_invalid", "Each stroke needs at least one coordinate.")
        if len(pts) > MAX_STROKE_POINTS:
            raise ValidationError("highlight_invalid", f"A stroke has too many points (max {MAX_STROKE_POINTS}).")
        coords: list[tuple[float, float]] = []
        for pt in pts:
            if not (isinstance(pt, (list, tuple)) and len(pt) >= 2):
                raise ValidationError("highlight_invalid", "Each coordinate must be [lng, lat].")
            lng, lat = float(pt[0]), float(pt[1])
            if not (math.isfinite(lng) and math.isfinite(lat)) or abs(lng) > 180 or abs(lat) > 85:
                raise ValidationError("highlight_invalid", "Coordinates out of range.")
            coords.append((lng, lat))
        strokes.append(Stroke(coords=coords, width_m=width))
    return strokes


def highlight_bbox_ring(strokes: list[Stroke]) -> Ring:
    """Closed rectangle ring around all strokes, grown by each stroke's half width."""
    w = s = math.inf
    e = n = -math.inf
    for st in strokes:
        half = st.width_m / 2.0
        for lng, lat in st.coords:
            dlat = half / 110540.0
            dlng = half / (111320.0 * max(0.05, math.cos(math.radians(lat))))
            w = min(w, lng - dlng)
            e = max(e, lng + dlng)
            s = min(s, lat - dlat)
            n = max(n, lat + dlat)
    return [(w, n), (e, n), (e, s), (w, s), (w, n)]


def ring_bbox(ring: Ring) -> tuple[float, float, float, float]:
    lngs = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (min(lngs), min(lats), max(lngs), max(lats))


def _local_xy(ring: Ring) -> list[tuple[float, float]]:
    lng_c = sum(p[0] for p in ring) / len(ring)
    lat_c = sum(p[1] for p in ring) / len(ring)
    kx = 111320.0 * math.cos(math.radians(lat_c))
    ky = 110540.0
    return [((lng - lng_c) * kx, (lat - lat_c) * ky) for lng, lat in ring]


def polygon_area_m2(ring: Ring) -> float:
    pts = _local_xy(ring)
    s = 0.0
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def bbox_area_m2(ring: Ring) -> float:
    w, s, e, n = ring_bbox(ring)
    lat_c = (s + n) / 2.0
    return (e - w) * 111320.0 * math.cos(math.radians(lat_c)) * (n - s) * 110540.0


def check_polygon_size(ring: Ring, max_bbox_km2: float, min_poly_m2: float) -> None:
    if bbox_area_m2(ring) > max_bbox_km2 * 1_000_000.0:
        raise ValidationError(
            "polygon_too_large", f"That area is too large. Please select under {max_bbox_km2:g} km²."
        )
    if polygon_area_m2(ring) < min_poly_m2:
        raise ValidationError("polygon_too_small", "That area is too small to edit. Zoom in and draw a larger shape.")
