"""Google Street View Static API: nearest panorama lookup and cube-face download.

The Static API returns one rectilinear view per request (max 640x640, fov <= 120), never a
full sphere, so `fetch_faces` downloads six 90-degree faces that `imaging.panorama` stitches.
The metadata endpoint is free; each face image is a billable request.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
from dataclasses import dataclass

import httpx
from PIL import Image

log = logging.getLogger(__name__)

METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"
SEARCH_RADII_M = (50, 100, 200, 400)

# (name, heading, pitch) in the order imaging.panorama.FACE_ANGLES expects.
FACES: tuple[tuple[str, float, float], ...] = (
    ("front", 0, 0),
    ("right", 90, 0),
    ("back", 180, 0),
    ("left", 270, 0),
    ("up", 0, 90),
    ("down", 0, -90),
)

_sem = asyncio.Semaphore(6)
_client: httpx.AsyncClient | None = None


class StreetViewError(RuntimeError):
    """code: no_street_view | streetview_unavailable | streetview_not_configured"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


@dataclass(frozen=True)
class Pano:
    pano_id: str
    lat: float
    lng: float
    date: str | None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "civic-patch/0.1"}, follow_redirects=True)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

_EARTH_R = 6_371_008.8


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial compass bearing from point 1 to point 2: 0 = north, clockwise, in [0, 360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360.0


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


async def find_pano(lat: float, lng: float, *, max_radius_m: int, api_key: str) -> Pano | None:
    """Nearest outdoor panorama within `max_radius_m`, searching outward in steps."""
    if not api_key:
        raise StreetViewError("streetview_not_configured", "GOOGLE_STREET_VIEW_API_KEY is not set")
    radii = [r for r in SEARCH_RADII_M if r < max_radius_m] + [max_radius_m]
    for radius in radii:
        params = {"location": f"{lat:.6f},{lng:.6f}", "radius": radius, "source": "outdoor", "key": api_key}
        try:
            resp = await _get_client().get(METADATA_URL, params=params)
        except httpx.HTTPError as exc:
            raise StreetViewError("streetview_unavailable", f"Street View metadata request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise StreetViewError("streetview_unavailable", f"Street View metadata HTTP {resp.status_code}")
        data = resp.json()
        status = data.get("status")
        if status == "OK":
            loc = data.get("location") or {}
            return Pano(
                pano_id=str(data.get("pano_id", "")),
                lat=float(loc.get("lat", lat)),
                lng=float(loc.get("lng", lng)),
                date=data.get("date"),
            )
        if status in ("ZERO_RESULTS", "NOT_FOUND"):
            continue
        raise StreetViewError("streetview_unavailable", data.get("error_message") or f"Street View status {status}")
    return None


async def _fetch_face(pano_id: str, heading: float, pitch: float, *, size_px: int, fov: float, api_key: str) -> Image.Image:
    params = {
        "pano": pano_id,
        "size": f"{size_px}x{size_px}",
        "heading": heading,
        "pitch": pitch,
        "fov": fov,
        "return_error_code": "true",
        "key": api_key,
    }
    last_exc: Exception | None = None
    async with _sem:
        for attempt in range(3):
            try:
                resp = await _get_client().get(IMAGE_URL, params=params)
                if resp.status_code == 404:
                    raise StreetViewError("no_street_view", "Street View has no imagery for this panorama.")
                if resp.status_code in (400, 403):
                    raise StreetViewError("streetview_unavailable", f"Street View rejected the request ({resp.status_code}).")
                if resp.status_code >= 500 or resp.status_code == 429:
                    raise httpx.HTTPStatusError("retry", request=resp.request, response=resp)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content))
                img.load()
                return img.convert("RGB")
            except StreetViewError:
                raise
            except (httpx.HTTPError, OSError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * (attempt + 1))
    raise StreetViewError("streetview_unavailable", f"Street View image request failed: {last_exc}")


async def fetch_faces(pano_id: str, *, size_px: int, fov: float, api_key: str) -> list[Image.Image]:
    """The six cube faces of `pano_id`, in FACES order."""
    if not api_key:
        raise StreetViewError("streetview_not_configured", "GOOGLE_STREET_VIEW_API_KEY is not set")
    return list(
        await asyncio.gather(
            *(_fetch_face(pano_id, h, p, size_px=size_px, fov=fov, api_key=api_key) for _, h, p in FACES)
        )
    )
