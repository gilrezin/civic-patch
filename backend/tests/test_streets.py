"""Nearest-street selection from Overpass elements (pure geometry, no network)."""

from __future__ import annotations

import math

import pytest

from app.geo import streets
from app.geo.streets import STREET_CLASSES, pick_street

LAT, LNG = 39.9526, -75.1652
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LNG = math.cos(math.radians(LAT)) * M_PER_DEG_LAT


def _way(wid: int, tags: dict, east_west_offset_m: float | None = None, north_south_offset_m: float | None = None) -> dict:
    """A straight 200 m way: east-west `north_south_offset_m` north of the point, or north-south
    `east_west_offset_m` east of it."""
    if north_south_offset_m is not None:
        lat = LAT + north_south_offset_m / M_PER_DEG_LAT
        geom = [{"lat": lat, "lon": LNG - 100 / M_PER_DEG_LNG}, {"lat": lat, "lon": LNG + 100 / M_PER_DEG_LNG}]
    else:
        lng = LNG + (east_west_offset_m or 0.0) / M_PER_DEG_LNG
        geom = [{"lat": LAT - 100 / M_PER_DEG_LAT, "lon": lng}, {"lat": LAT + 100 / M_PER_DEG_LAT, "lon": lng}]
    return {"type": "way", "id": wid, "tags": tags, "geometry": geom}


def test_picks_nearest_street_and_snaps_onto_it():
    elements = [
        _way(1, {"highway": "residential", "name": "Pine Street"}, north_south_offset_m=30),
        _way(2, {"highway": "primary", "name": "Market Street"}, north_south_offset_m=-80),
    ]
    s = pick_street(elements, LNG, LAT)
    assert s is not None and s.name == "Pine Street" and s.highway == "residential"
    assert s.distance_m == pytest.approx(30, abs=0.5)
    # Snapped point sits on the way, due north of the query point.
    assert (s.lat - LAT) * M_PER_DEG_LAT == pytest.approx(30, abs=0.5)
    assert abs(s.lng - LNG) * M_PER_DEG_LNG < 0.01


def test_alleys_and_paths_are_ignored_even_when_closer():
    elements = [
        _way(1, {"highway": "service", "service": "alley"}, north_south_offset_m=4),
        _way(2, {"highway": "footway"}, east_west_offset_m=6),
        _way(3, {"highway": "tertiary", "name": "Walnut Street"}, north_south_offset_m=-45),
    ]
    s = pick_street(elements, LNG, LAT)
    assert s is not None and s.name == "Walnut Street"
    assert "service" not in STREET_CLASSES and "footway" not in STREET_CLASSES


def test_named_street_beats_slightly_closer_unnamed_one():
    elements = [
        _way(1, {"highway": "tertiary_link"}, north_south_offset_m=12),
        _way(2, {"highway": "secondary", "name": "Broad Street"}, north_south_offset_m=-25),
    ]
    s = pick_street(elements, LNG, LAT)
    assert s is not None and s.name == "Broad Street"
    # ...but not when the unnamed one is much closer.
    elements[1] = _way(2, {"highway": "secondary", "name": "Broad Street"}, north_south_offset_m=-60)
    s = pick_street(elements, LNG, LAT)
    assert s is not None and s.name is None and s.highway == "tertiary_link"


def test_nearest_point_is_clamped_to_segment_ends():
    # A way that ends 50 m east of the point and continues east: nearest point is its end.
    lat = LAT
    geom = [{"lat": lat, "lon": LNG + 50 / M_PER_DEG_LNG}, {"lat": lat, "lon": LNG + 250 / M_PER_DEG_LNG}]
    s = pick_street([{"type": "way", "id": 9, "tags": {"highway": "residential", "name": "X"}, "geometry": geom}], LNG, LAT)
    assert s is not None and s.distance_m == pytest.approx(50, abs=0.5)


def test_no_streets_returns_none():
    assert pick_street([], LNG, LAT) is None
    assert pick_street([{"type": "node", "id": 1}], LNG, LAT) is None


def test_overpass_failure_falls_back_to_none(monkeypatch):
    import asyncio

    async def boom(query):
        raise streets.OverpassError("down")

    monkeypatch.setattr(streets, "query_overpass", boom)
    assert asyncio.run(streets.nearest_street(LNG, LAT, radius_m=100)) is None
