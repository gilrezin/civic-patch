"""Web Mercator (EPSG:3857) pixel math for 256 px XYZ tiles."""

from __future__ import annotations

import math

TILE = 256
MAX_LAT = 85.05112878


def world_px(z: int) -> float:
    return TILE * (1 << z)


def lnglat_to_px(lng: float, lat: float, z: int) -> tuple[float, float]:
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    w = world_px(z)
    x = (lng + 180.0) / 360.0 * w
    lat_r = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * w
    return x, y


def px_to_lnglat(x: float, y: float, z: int) -> tuple[float, float]:
    w = world_px(z)
    lng = x / w * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / w))))
    return lng, lat


def px_to_tile(x: float, y: float) -> tuple[int, int]:
    return int(math.floor(x / TILE)), int(math.floor(y / TILE))


def meters_per_px(lat: float, z: int) -> float:
    return 156543.03392 * math.cos(math.radians(lat)) / (1 << z)
