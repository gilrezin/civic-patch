"""Road splitting, width estimation and area extraction from Overpass elements (no network)."""

from app.geo.osm import cell_bbox, cell_of, estimate_width_m, process_elements


def _way(wid, nodes, coords, tags):
    return {"type": "way", "id": wid, "nodes": nodes, "geometry": [{"lon": x, "lat": y} for x, y in coords], "tags": tags}


def test_cells_round_trip():
    ix, iy = cell_of(-75.1652, 39.9526)
    w, s, e, n = cell_bbox(ix, iy)
    assert w <= -75.1652 < e and s <= 39.9526 < n
    assert abs((e - w) - 0.01) < 1e-9


def test_width_estimation():
    assert estimate_width_m({"highway": "residential", "width": "9"}) == 9.0
    assert abs(estimate_width_m({"highway": "primary", "width": "40'"}) - 12.192) < 0.01
    assert estimate_width_m({"highway": "primary", "lanes": "4"}) == 4 * 3.3 + 1.0
    assert estimate_width_m({"highway": "service"}) == 4.0
    assert estimate_width_m({"highway": "weird"}) == 7.0


def test_roads_split_at_intersections_but_not_at_crosswalks_or_continuations():
    # Main St: nodes 1-2-3-4-5 (one way), crossed by Cross St at node 3 and a footway at node 2.
    main = _way(10, [1, 2, 3, 4, 5], [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], {"highway": "residential", "name": "Main St"})
    cross = _way(11, [6, 3, 7], [(2, -1), (2, 0), (2, 1)], {"highway": "residential", "name": "Cross St"})
    foot = _way(12, [8, 2, 9], [(1, -1), (1, 0), (1, 1)], {"highway": "footway"})
    # Main St continues as a second OSM way (same name) joined end-to-end at node 5: not an intersection.
    main2 = _way(13, [5, 14, 15], [(4, 0), (5, 0), (6, 0)], {"highway": "residential", "name": "Main St"})
    feats = process_elements([main, cross, foot, main2])
    roads = [r for r in feats.roads if r.kind == "road"]
    labels = sorted((r.label, len(r.coords)) for r in roads)
    # Main St: [1..3] and [3..5]+[5..15] merged -> two segments; Cross St: [6,3] and [3,7].
    main_segs = [r for r in roads if r.label == "Main St"]
    assert len(main_segs) == 2
    assert sorted(len(r.coords) for r in main_segs) == [3, 5]
    assert len([r for r in roads if r.label == "Cross St"]) == 2
    assert any(r.kind == "path" for r in feats.roads)
    assert all(r.width_m == 7.0 for r in main_segs)
    assert labels


def test_areas_from_ways_and_multipolygon_outer():
    b = _way(20, [1, 2, 3, 1], [(0, 0), (1, 0), (1, 1), (0, 0)], {"building": "yes", "name": "City Hall"})
    lot = _way(21, [4, 5, 6, 4], [(2, 2), (3, 2), (3, 3), (2, 2)], {"amenity": "parking"})
    open_way = _way(22, [7, 8, 9], [(5, 5), (6, 5), (6, 6)], {"building": "yes"})  # not closed -> ignored
    rel = {
        "type": "relation",
        "id": 30,
        "tags": {"type": "multipolygon", "building": "apartments"},
        "members": [
            {"type": "way", "role": "outer", "geometry": [{"lon": 7, "lat": 7}, {"lon": 8, "lat": 7}, {"lon": 8, "lat": 8}, {"lon": 7, "lat": 7}]},
            {"type": "way", "role": "inner", "geometry": [{"lon": 7.2, "lat": 7.2}, {"lon": 7.4, "lat": 7.2}, {"lon": 7.4, "lat": 7.4}, {"lon": 7.2, "lat": 7.2}]},
        ],
    }
    feats = process_elements([b, lot, open_way, rel])
    kinds = sorted((a.kind, a.label) for a in feats.areas)
    assert kinds == [("building", "Apartments"), ("building", "City Hall"), ("parking", "Parking lot")]
    assert all(a.ring[0] == a.ring[-1] for a in feats.areas)
