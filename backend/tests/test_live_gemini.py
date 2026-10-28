"""Live integration test: a real road segment, real tiles, real Gemini.

Skipped automatically when backend/.env has no GEMINI_API_KEY. Run only this test with:
    .venv\\Scripts\\python.exe -m pytest -m live -q
Outputs are written to backend/tests/output/ for visual inspection.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from PIL import Image, ImageChops, ImageStat

from app.ai.gemini import GeminiEditor
from app.ai.prompts import create_prompt
from app.config import BACKEND_DIR
from app.geo.crop import build_crop
from app.geo.validate import parse_polygon
from app.imaging.mask import make_overlay, polygon_mask

pytestmark = pytest.mark.live

OUTPUT_DIR = BACKEND_DIR / "tests" / "output"

# A ~240 m stretch of Market Street, Philadelphia, between 15th and 17th Streets,
# with a narrow buffer to cover the roadway, including lanes and curbs.
MARKET_STREET = {
    "type": "Polygon",
    "coordinates": [
        [
            [-75.16885, 39.95300],
            [-75.16610, 39.95290],
            [-75.16605, 39.95228],
            [-75.16880, 39.95238],
            [-75.16885, 39.95300],
        ]
    ],
}


def _live_config() -> tuple[str | None, str | None]:
    vals = dotenv_values(BACKEND_DIR / ".env") if (BACKEND_DIR / ".env").exists() else {}
    key = vals.get("GEMINI_API_KEY") or os.environ.get("CIVIC_PATCH_LIVE_GEMINI_KEY")
    model = vals.get("GEMINI_IMAGE_MODEL") or None
    return (key or None), model


_KEY, _MODEL = _live_config()


@pytest.mark.skipif(not _KEY, reason="GEMINI_API_KEY not configured in backend/.env")
def test_add_bus_lanes_changes_the_road():
    ring = parse_polygon(MARKET_STREET)
    crop = asyncio.run(build_crop(ring))
    mask = polygon_mask(crop.image.size, crop.polygon_px)

    editor = GeminiEditor(api_key=_KEY, model=_MODEL)
    prompt = create_prompt("add bus lanes", "mask")
    edited = asyncio.run(editor.edit(crop.image, mask, prompt, crop.rect.aspect_name))

    # Keep the artefacts for a human to look at.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    crop.image.save(OUTPUT_DIR / "bus_lanes_original.png")
    edited.save(OUTPUT_DIR / "bus_lanes_edited.png")
    make_overlay(edited, mask).save(OUTPUT_DIR / "bus_lanes_overlay.png")

    # 1. Same framing: the result must be the exact crop size so it can be placed on the map.
    assert edited.size == crop.image.size

    # 2. Not identical: the road inside the polygon must actually have changed.
    diff = ImageChops.difference(crop.image.convert("RGB"), edited.convert("RGB")).convert("L")
    diff.save(OUTPUT_DIR / "bus_lanes_diff.png")
    hard_mask = mask.point(lambda v: 255 if v >= 128 else 0)
    inside_mean = ImageStat.Stat(diff, hard_mask).mean[0]
    changed = diff.point(lambda v: 255 if v > 24 else 0)
    changed_fraction = ImageStat.Stat(changed, hard_mask).mean[0] / 255.0
    assert inside_mean > 3.0, f"road pixels barely changed (mean diff {inside_mean:.2f})"
    assert changed_fraction > 0.02, f"only {changed_fraction:.1%} of road pixels changed"

    # 3. The output is still a photo-like image, not a blank or flat colour.
    assert len(set(edited.convert("L").getdata())) > 64

    # Sanity check that the diff is not uniform noise across the whole frame: inside the
    # polygon should change at least as much as the surroundings on average.
    outside_mask = ImageChops.invert(hard_mask)
    outside_mean = ImageStat.Stat(diff, outside_mask).mean[0]
    assert inside_mean >= outside_mean * 0.8, (
        f"inside changed less ({inside_mean:.2f}) than outside ({outside_mean:.2f}); edit missed the road"
    )
    assert isinstance(edited, Image.Image)
    assert Path(OUTPUT_DIR / "bus_lanes_edited.png").exists()
