"""Reverse geocoding (neighbourhood + city) via OpenStreetMap Nominatim.

Nominatim's usage policy requires an identifying User-Agent and at most one request per
second; we serialise calls with a lock and a minimum spacing between requests.
"""

from __future__ import annotations

import asyncio
import logging
import time

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


async def reverse_geocode(lng: float, lat: float) -> str | None:
    """Return a short human place label like 'Rittenhouse Square, Philadelphia', or None."""
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
            return compose_place_name(data.get("address") or {})
        except Exception as exc:  # network issues must never break edit creation
            log.warning("reverse geocode failed: %s", exc)
            return None
