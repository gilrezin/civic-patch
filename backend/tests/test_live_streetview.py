"""Live integration test: real Street View metadata and faces (and optionally real Gemini).

Skipped when backend/.env has no GOOGLE_STREET_VIEW_API_KEY. Run with:
    .venv\\Scripts\\python.exe -m pytest tests/test_live_streetview.py -m live -q
Outputs go to backend/tests/output/ for visual inspection: the stitched panorama should read
as one seamless sphere with the sky at the top, and the edited version (when Gemini runs)
should show the bus lanes at the centre of the image.
"""

from __future__ import annotations

import asyncio
import os

import numpy as np
import pytest
from dotenv import dotenv_values

from PIL import Image

from app.config import BACKEND_DIR
from app.geo.streetview import FACES, Pano, bearing_deg, close_client, fetch_faces, find_pano, haversine_m
from app.imaging.panorama import cube_to_equirect

pytestmark = pytest.mark.live

OUTPUT_DIR = BACKEND_DIR / "tests" / "output"

# Centre of the Market Street segment used by test_live_gemini.py
SITE_LAT, SITE_LNG = 39.95264, -75.16745


def _env() -> dict:
    return dotenv_values(BACKEND_DIR / ".env") if (BACKEND_DIR / ".env").exists() else {}


_SV_KEY = _env().get("GOOGLE_STREET_VIEW_API_KEY") or os.environ.get("GOOGLE_STREET_VIEW_API_KEY")
_GEMINI_KEY = _env().get("GEMINI_API_KEY") or os.environ.get("CIVIC_PATCH_LIVE_GEMINI_KEY")


async def _download() -> tuple[Pano, list[Image.Image]]:
    """One event loop for both calls: the module-level httpx client is bound to the loop it first used."""
    try:
        pano = await find_pano(SITE_LAT, SITE_LNG, max_radius_m=200, api_key=_SV_KEY)
        assert pano is not None and pano.pano_id
        faces = await fetch_faces(pano.pano_id, size_px=640, fov=90, api_key=_SV_KEY)
        return pano, faces
    finally:
        await close_client()


@pytest.mark.skipif(not _SV_KEY, reason="GOOGLE_STREET_VIEW_API_KEY not configured in backend/.env")
def test_stitch_real_panorama():
    pano, faces = asyncio.run(_download())
    heading = bearing_deg(pano.lat, pano.lng, SITE_LAT, SITE_LNG)
    assert haversine_m(pano.lat, pano.lng, SITE_LAT, SITE_LNG) < 200

    assert len(faces) == 6 and all(f.size == (640, 640) for f in faces)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for (name, _, _), face in zip(FACES, faces):
        face.save(OUTPUT_DIR / f"streetview_face_{name}.png")

    equirect = cube_to_equirect(faces, 2048, 1024, center_heading_deg=heading)
    equirect.save(OUTPUT_DIR / "streetview_pano.png")
    assert equirect.size == (2048, 1024)

    arr = np.asarray(equirect.convert("L"), dtype=np.float32)
    sky, ground = arr[: arr.shape[0] // 10].mean(), arr[-arr.shape[0] // 10 :].mean()
    assert sky > ground, f"sky ({sky:.0f}) should be brighter than ground ({ground:.0f}); up/down faces flipped?"
    rgb = np.asarray(equirect, dtype=np.float32)
    seam = np.abs(rgb[:, 0, :] - rgb[:, -1, :]).mean()
    assert seam < 40, f"wrap seam discontinuity {seam:.1f}"


@pytest.mark.skipif(not (_SV_KEY and _GEMINI_KEY), reason="needs GOOGLE_STREET_VIEW_API_KEY and GEMINI_API_KEY")
def test_gemini_renders_bus_lanes_from_the_street():
    from app.ai.gemini import GeminiEditor
    from app.ai.prompts import create_prompt, streetview_prompt
    from app.geo.crop import build_crop
    from app.geo.validate import parse_polygon
    from app.imaging.mask import polygon_mask
    from tests.test_live_gemini import MARKET_STREET

    pano, faces = asyncio.run(_download())
    heading = bearing_deg(pano.lat, pano.lng, SITE_LAT, SITE_LNG)
    distance = haversine_m(pano.lat, pano.lng, SITE_LAT, SITE_LNG)
    equirect = cube_to_equirect(faces, 2048, 1024, center_heading_deg=heading)

    crop = asyncio.run(build_crop(parse_polygon(MARKET_STREET)))
    mask = polygon_mask(crop.image.size, crop.polygon_px)
    editor = GeminiEditor(api_key=_GEMINI_KEY, model=_env().get("GEMINI_IMAGE_MODEL") or None,
                          pano_model=_env().get("GEMINI_STREETVIEW_MODEL") or None)
    edited_sat = asyncio.run(editor.edit(crop.image, mask, create_prompt("add bus lanes", "mask"), crop.rect.aspect_name))
    prompt = streetview_prompt(["add bus lanes"], "Center City, Philadelphia", distance)
    out = asyncio.run(editor.edit_panorama(equirect, [crop.image, edited_sat], prompt))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    equirect.save(OUTPUT_DIR / "streetview_pano.png")
    edited_sat.save(OUTPUT_DIR / "streetview_sat_after.png")
    out.save(OUTPUT_DIR / "streetview_edited.png")
    assert out.size == equirect.size
    diff = np.abs(np.asarray(out, dtype=np.float32) - np.asarray(equirect, dtype=np.float32)).mean()
    assert diff > 1.0, "panorama came back unchanged"
