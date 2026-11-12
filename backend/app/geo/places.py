"""Reverse geocoding (neighbourhood + city) via OpenStreetMap Nominatim.

Nominatim's usage policy requires an identifying User-Agent and at most one request per
second; we serialise calls with a lock and a minimum spacing between requests.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "civic-patch/0.1 (community planning prototype)"
MIN_SPACING_S = 1.1

_lock = asyncio.Lock()
_last_call = 0.0

_HOOD_KEYS = ("neighbourhood", "suburb", "quarter", "city_district", "borough", "hamlet", "residential")
_CITY_KEYS = ("city", "town", "village", "municipality", "county")


def compose_place_name(address: dict) -> str | None:
    hood = next((address[k] for k in _HOOD_KEYS if address.get(k)), None)
    city = next((address[k] for k in _CITY_KEYS if address.get(k)), None)
    state = address.get("state")
    parts: list[str] = []
    if hood and hood != city:
        parts.append(hood)
    if city:
        parts.append(city)
    elif state:
        parts.append(state)
    if len(parts) == 1 and state and state != parts[0]:
        parts.append(state)
    return ", ".join(parts) or None


@dataclass(frozen=True)
class PlaceInfo:
    place_name: str | None
    municipality: str | None  # slug like "Philadelphia-PA", used to look up a comprehensive plan


_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def municipality_slug(address: dict) -> str | None:
    """'Philadelphia-PA' from a Nominatim address; None when no city-level name is present."""
    city = next((address[k] for k in ("city", "town", "village", "municipality", "borough") if address.get(k)), None)
    if not city:
        return None
    region = None
    for k, v in address.items():
        if k.startswith("ISO3166-2-lvl") and isinstance(v, str) and "-" in v:
            region = v.split("-", 1)[1]
            break
    if not region:
        region = address.get("state") or address.get("country_code", "").upper()
    parts = [_SLUG_RE.sub("-", city).strip("-")]
    if region:
        parts.append(_SLUG_RE.sub("-", str(region)).strip("-"))
    return "-".join(p for p in parts if p) or None


@dataclass(frozen=True)
class PlaceDetail:
    place_name: str | None
    municipality: str | None
    city: str | None
    neighbourhood: str | None
    region: str | None


def place_detail_from_address(address: dict) -> PlaceDetail:
    hood = next((address[k] for k in _HOOD_KEYS if address.get(k)), None)
    city = next((address[k] for k in ("city", "town", "village", "municipality", "borough") if address.get(k)), None)
    if hood == city:
        hood = None
    return PlaceDetail(
        place_name=compose_place_name(address),
        municipality=municipality_slug(address),
        city=city or address.get("county") or address.get("state"),
        neighbourhood=hood,
        region=address.get("state"),
    )


async def describe_point(lng: float, lat: float) -> PlaceDetail:
    """City and neighbourhood for the header location button."""
    address = await _reverse_address(lng, lat)
    if address is None:
        return PlaceDetail(None, None, None, None, None)
    return place_detail_from_address(address)


async def search_places(query: str, limit: int = 6) -> list[dict]:
    """Forward geocode via Nominatim search; returns [{name, lng, lat, bbox}] (bbox = W,S,E,N)."""
    global _last_call
    q = query.strip()
    if not q:
        return []
    async with _lock:
        wait = MIN_SPACING_S - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": USER_AGENT}) as client:
                resp = await client.get(
                    NOMINATIM_URL.replace("/reverse", "/search"),
                    params={"format": "jsonv2", "q": q, "limit": limit, "addressdetails": 0},
                )
            if resp.status_code != 200:
                log.warning("nominatim search %s: %s", resp.status_code, resp.text[:120])
                return []
            out = []
            for r in resp.json():
                try:
                    s, n, w, e = (float(v) for v in r["boundingbox"])
                    out.append({"name": r.get("display_name", ""), "lng": float(r["lon"]), "lat": float(r["lat"]), "bbox": [w, s, e, n]})
                except (KeyError, ValueError, TypeError):
                    continue
            return out
        except Exception as exc:
            log.warning("place search failed: %s", exc)
            return []


async def reverse_geocode_full(lng: float, lat: float) -> PlaceInfo:
    """Place label plus municipality slug for a point."""
    address = await _reverse_address(lng, lat)
    if address is None:
        return PlaceInfo(None, None)
    return PlaceInfo(compose_place_name(address), municipality_slug(address))


async def reverse_geocode(lng: float, lat: float) -> str | None:
    """Return a short human place label like 'Rittenhouse Square, Philadelphia', or None."""
    return (await reverse_geocode_full(lng, lat)).place_name


async def _reverse_address(lng: float, lat: float) -> dict | None:
    global _last_call
    async with _lock:
        wait = MIN_SPACING_S - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": USER_AGENT}) as client:
                resp = await client.get(
                    NOMINATIM_URL,
                    params={"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lng:.6f}", "zoom": 16, "addressdetails": 1},
                )
            if resp.status_code != 200:
                log.warning("nominatim %s: %s", resp.status_code, resp.text[:120])
                return None
            data = resp.json()
            return data.get("address") or {}
        except Exception as exc:  # network issues must never break edit creation
            log.warning("reverse geocode failed: %s", exc)
            return None
