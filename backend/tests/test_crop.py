import asyncio
import math

from app.geo.crop import ASPECTS, build_crop, choose_zoom, crop_rect, polygon_in_crop
from app.geo.mercator import lnglat_to_px
from app.geo.validate import ring_bbox

PHILLY_BLOCK = [
    (-75.1665, 39.9535),
    (-75.1640, 39.9535),
    (-75.1640, 39.9518),
    (-75.1665, 39.9518),
    (-75.1665, 39.9535),
]


def test_choose_zoom_in_range():
    z = choose_zoom(ring_bbox(PHILLY_BLOCK))
    assert 14 <= z <= 19
    rect = crop_rect(PHILLY_BLOCK, z)
    assert 768 <= max(rect.width, rect.height) < 1600


def test_tiny_polygon_clamps_to_max_zoom():
    tiny = [(-75.1652, 39.9526), (-75.16515, 39.9526), (-75.16515, 39.95255), (-75.1652, 39.95255), (-75.1652, 39.9526)]
    assert choose_zoom(ring_bbox(tiny)) == 19


def test_crop_rect_contains_polygon_and_matches_aspect():
    z = choose_zoom(ring_bbox(PHILLY_BLOCK))
    rect = crop_rect(PHILLY_BLOCK, z)
    for lng, lat in PHILLY_BLOCK:
        x, y = lnglat_to_px(lng, lat, z)
        assert rect.x0 < x < rect.x1
        assert rect.y0 < y < rect.y1
    target = ASPECTS[rect.aspect_name]
    assert abs(math.log((rect.width / rect.height) / target)) < 0.02


def test_bounds_match_integer_edges():
    z = choose_zoom(ring_bbox(PHILLY_BLOCK))
    rect = crop_rect(PHILLY_BLOCK, z)
    w, s, e, n = rect.bounds
    x0, y0 = lnglat_to_px(w, n, z)
    x1, y1 = lnglat_to_px(e, s, z)
    assert math.isclose(x0, rect.x0, abs_tol=1e-6)
    assert math.isclose(y0, rect.y0, abs_tol=1e-6)
    assert math.isclose(x1, rect.x1, abs_tol=1e-6)
    assert math.isclose(y1, rect.y1, abs_tol=1e-6)


def test_build_crop_with_stubbed_tiles():
    crop = asyncio.run(build_crop(PHILLY_BLOCK))
    assert crop.image.size == (crop.rect.width, crop.rect.height)
    assert crop.scale == 1.0
    px = polygon_in_crop(PHILLY_BLOCK, crop.rect)
    assert px == crop.polygon_px
    for x, y in px:
        assert 0 < x < crop.image.width
        assert 0 < y < crop.image.height
