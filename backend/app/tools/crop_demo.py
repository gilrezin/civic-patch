"""Alignment check: stitch a crop for a polygon and write original.png + an identity overlay.

Usage:
    python -m app.tools.crop_demo [out_dir] [polygon.json]

The identity overlay is the UNEDITED crop masked to the polygon. Placed on the map with the
printed bounds, it must be invisible (no seam) if the crop math is correct.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from ..geo.crop import build_crop
from ..geo.validate import parse_polygon
from ..imaging.mask import make_overlay, polygon_mask

# A block in Center City Philadelphia (around City Hall).
DEFAULT_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-75.1665, 39.9535],
            [-75.1640, 39.9535],
            [-75.1640, 39.9518],
            [-75.1665, 39.9518],
            [-75.1665, 39.9535],
        ]
    ],
}


async def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("crop_demo_out")
    polygon = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else DEFAULT_POLYGON
    ring = parse_polygon(polygon)
    crop = await build_crop(ring)
    out_dir.mkdir(parents=True, exist_ok=True)
    crop.image.save(out_dir / "original.png")
    mask = polygon_mask(crop.image.size, crop.polygon_px)
    mask.save(out_dir / "mask.png")
    make_overlay(crop.image, mask).save(out_dir / "identity_overlay.png")
    info = {
        "zoom": crop.rect.z,
        "size": crop.image.size,
        "scale": crop.scale,
        "aspect": crop.rect.aspect_name,
        "bounds_wsen": crop.rect.bounds,
        "polygon_px": crop.polygon_px,
    }
    (out_dir / "info.json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
