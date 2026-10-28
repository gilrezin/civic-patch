import pytest

from app.geo.validate import (
    ValidationError,
    bbox_area_m2,
    check_polygon_size,
    clean_prompt,
    parse_polygon,
    polygon_area_m2,
)

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[-75.1665, 39.9535], [-75.1640, 39.9535], [-75.1640, 39.9518], [-75.1665, 39.9518]]],
}


def test_parse_polygon_closes_ring():
    ring = parse_polygon(SQUARE)
    assert len(ring) == 5
    assert ring[0] == ring[-1]


def test_parse_polygon_rejects_bad_shapes():
    with pytest.raises(ValidationError):
        parse_polygon({"type": "Point", "coordinates": [0, 0]})
    with pytest.raises(ValidationError):
        parse_polygon({"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]})
    with pytest.raises(ValidationError):
        parse_polygon({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [200, 1]]]})


def test_area_is_sane():
    ring = parse_polygon(SQUARE)
    a = polygon_area_m2(ring)
    # ~213 m x ~189 m block
    assert 30_000 < a < 50_000
    assert abs(bbox_area_m2(ring) - a) / a < 0.01


def test_size_limits():
    ring = parse_polygon(SQUARE)
    check_polygon_size(ring, max_bbox_km2=1.0, min_poly_m2=20)
    with pytest.raises(ValidationError) as e:
        check_polygon_size(ring, max_bbox_km2=0.01, min_poly_m2=20)
    assert e.value.code == "polygon_too_large"
    with pytest.raises(ValidationError) as e:
        check_polygon_size(ring, max_bbox_km2=1.0, min_poly_m2=10_000_000)
    assert e.value.code == "polygon_too_small"


def test_prompt_cleaning():
    assert clean_prompt("  add   bus lanes  ") == "add bus lanes"
    with pytest.raises(ValidationError):
        clean_prompt("ab")
    with pytest.raises(ValidationError):
        clean_prompt("x" * 301)
    with pytest.raises(ValidationError):
        clean_prompt("see http://example.com")
    with pytest.raises(ValidationError):
        clean_prompt("!!! ???")
