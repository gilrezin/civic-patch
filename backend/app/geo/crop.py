"""Choose a zoom level, compute an aspect-snapped crop rectangle, and stitch tiles into it."""

from __future__ import annotations

import asyncio
import io
import math
from dataclasses import dataclass

from PIL import Image

from .mercator import TILE, lnglat_to_px, px_to_lnglat, px_to_tile
from .tiles import fetch_tiles
from .validate import Ring, ring_bbox

# Aspect buckets supported by Gemini image output. Keeping the input crop on one of these
# means the output aspect matches the input, so the final resize is a uniform scale.
ASPECTS: dict[str, float] = {
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "5:4": 5 / 4,
    "4:5": 4 / 5,
    "21:9": 21 / 9,
}

MIN_CROP_PX = 512
UPSCALE_TARGET_PX = 768
FILL_COLOR = (90, 90, 90)


@dataclass(frozen=True)
class CropRect:
    z: int
    x0: int
    y0: int
    x1: int
    y1: int
    aspect_name: str

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Geographic bounds (W, S, E, N) derived from the integer pixel edges."""
        w, n = px_to_lnglat(self.x0, self.y0, self.z)
        e, s = px_to_lnglat(self.x1, self.y1, self.z)
        return (w, s, e, n)


@dataclass
class Crop:
    image: Image.Image
    rect: CropRect
    polygon_px: list[tuple[float, float]]
    scale: float = 1.0


def choose_zoom(
    bounds: tuple[float, float, float, float],
    *,
    min_zoom: int = 14,
    max_zoom: int = 19,
    target_min_px: int = 768,
    margin: float = 0.15,
) -> int:
    """Smallest zoom at which the margin-expanded bbox has a longest side >= target_min_px."""
    w, s, e, n = bounds
    x0, y0 = lnglat_to_px(w, n, 0)
    x1, y1 = lnglat_to_px(e, s, 0)
    longest0 = max(x1 - x0, y1 - y0) * (1 + 2 * margin)
    if longest0 <= 0:
        return max_zoom
    z = math.ceil(math.log2(target_min_px / longest0))
    return max(min_zoom, min(max_zoom, z))


def crop_rect(ring: Ring, z: int, *, margin: float = 0.15) -> CropRect:
    pts = [lnglat_to_px(lng, lat, z) for lng, lat in ring]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    w, h = x1 - x0, y1 - y0
    m = margin * max(w, h, 1.0)
    x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m

    aspect = (x1 - x0) / max(y1 - y0, 1e-9)
    name, target = min(ASPECTS.items(), key=lambda kv: abs(math.log(kv[1] / aspect)))
    if aspect < target:  # too tall -> widen
        extra = (y1 - y0) * target - (x1 - x0)
        x0 -= extra / 2
        x1 += extra / 2
    else:  # too wide -> heighten
        extra = (x1 - x0) / target - (y1 - y0)
        y0 -= extra / 2
        y1 += extra / 2

    return CropRect(
        z=z,
        x0=int(math.floor(x0)),
        y0=int(math.floor(y0)),
        x1=int(math.ceil(x1)),
        y1=int(math.ceil(y1)),
        aspect_name=name,
    )


def polygon_in_crop(ring: Ring, rect: CropRect, scale: float = 1.0) -> list[tuple[float, float]]:
    out = []
    for lng, lat in ring:
        x, y = lnglat_to_px(lng, lat, rect.z)
        out.append(((x - rect.x0) * scale, (y - rect.y0) * scale))
    return out


def _stitch(tiles: dict[tuple[int, int], bytes | None], rect: CropRect, tx0: int, ty0: int, tx1: int, ty1: int) -> Image.Image:
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE), FILL_COLOR)
    for (tx, ty), data in tiles.items():
        if data:
            try:
                tile = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception:
                continue
            canvas.paste(tile, ((tx - tx0) * TILE, (ty - ty0) * TILE))
    ox, oy = tx0 * TILE, ty0 * TILE
    return canvas.crop((rect.x0 - ox, rect.y0 - oy, rect.x1 - ox, rect.y1 - oy))


async def build_crop(
    ring: Ring,
    *,
    min_zoom: int = 14,
    max_zoom: int = 19,
    target_min_px: int = 768,
    margin: float = 0.15,
) -> Crop:
    bounds = ring_bbox(ring)
    z = choose_zoom(bounds, min_zoom=min_zoom, max_zoom=max_zoom, target_min_px=target_min_px, margin=margin)

    for attempt in range(2):
        rect = crop_rect(ring, z, margin=margin)
        tx0, ty0 = px_to_tile(rect.x0, rect.y0)
        tx1, ty1 = px_to_tile(rect.x1 - 1, rect.y1 - 1)
        tiles = await fetch_tiles(z, tx0, ty0, tx1, ty1)
        missing = sum(1 for v in tiles.values() if v is None)
        if missing > 0.1 * len(tiles) and z > min_zoom and attempt == 0:
            z -= 1  # imagery not available this deep here; back off one zoom
            continue
        break

    img = await asyncio.to_thread(_stitch, tiles, rect, tx0, ty0, tx1, ty1)

    scale = 1.0
    if max(img.size) < MIN_CROP_PX:
        scale = UPSCALE_TARGET_PX / max(img.size)
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = await asyncio.to_thread(img.resize, new_size, Image.LANCZOS)

    return Crop(image=img, rect=rect, polygon_px=polygon_in_crop(ring, rect, scale), scale=scale)
