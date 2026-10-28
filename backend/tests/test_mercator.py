import math

from app.geo.mercator import TILE, lnglat_to_px, px_to_lnglat, px_to_tile, world_px


def test_round_trip():
    for z in (0, 10, 16, 19):
        for lng, lat in [(-75.1652, 39.9526), (0, 0), (179.9, -60.0), (-120.5, 70.2)]:
            x, y = lnglat_to_px(lng, lat, z)
            lng2, lat2 = px_to_lnglat(x, y, z)
            assert math.isclose(lng, lng2, abs_tol=1e-9)
            assert math.isclose(lat, lat2, abs_tol=1e-9)


def test_world_extent():
    assert world_px(0) == TILE
    x, y = lnglat_to_px(-180, 85.05112878, 0)
    assert math.isclose(x, 0, abs_tol=1e-9)
    assert math.isclose(y, 0, abs_tol=1e-6)
    x, y = lnglat_to_px(180, -85.05112878, 0)
    assert math.isclose(x, TILE, abs_tol=1e-9)
    assert math.isclose(y, TILE, abs_tol=1e-6)


def test_tile_index():
    assert px_to_tile(0, 0) == (0, 0)
    assert px_to_tile(255.9, 256) == (0, 1)
    assert px_to_tile(512, 768.5) == (2, 3)
