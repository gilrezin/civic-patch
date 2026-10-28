"""Asynchronous fetching of Esri World Imagery XYZ tiles with a small in-memory cache."""

from __future__ import annotations

import asyncio
from collections import OrderedDict

import httpx

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ATTRIBUTION = "Esri, Maxar, Earthstar Geographics, and the GIS User Community"

_CACHE_MAX = 2000
_cache: OrderedDict[tuple[int, int, int], bytes | None] = OrderedDict()
_sem = asyncio.Semaphore(8)
_client: httpx.AsyncClient | None = None


class TileFetchError(RuntimeError):
    pass


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "civic-patch/0.1"}, follow_redirects=True)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _cache_put(key: tuple[int, int, int], value: bytes | None) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


async def fetch_one(z: int, x: int, y: int) -> bytes | None:
    """Return tile PNG/JPEG bytes, or None if the tile does not exist (404)."""
    key = (z, x, y)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    url = TILE_URL.format(z=z, x=x, y=y)
    last_exc: Exception | None = None
    async with _sem:
        for attempt in range(3):
            try:
                resp = await _get_client().get(url)
                if resp.status_code == 404:
                    _cache_put(key, None)
                    return None
                if resp.status_code >= 500:
                    raise TileFetchError(f"tile {z}/{x}/{y} -> {resp.status_code}")
                resp.raise_for_status()
                data = resp.content
                _cache_put(key, data)
                return data
            except (httpx.HTTPError, TileFetchError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * (attempt + 1))
    raise TileFetchError(f"failed to fetch tile {z}/{x}/{y}: {last_exc}")


async def fetch_tiles(z: int, tx0: int, ty0: int, tx1: int, ty1: int) -> dict[tuple[int, int], bytes | None]:
    coords = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    results = await asyncio.gather(*(fetch_one(z, tx, ty) for tx, ty in coords))
    return dict(zip(coords, results))
