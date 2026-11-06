from PIL import Image

from app.geo.validate import Stroke, highlight_bbox_ring
from app.imaging.mask import make_overlay, polygon_mask, strokes_mask


def test_strokes_mask_follows_strokes_with_round_caps():
    m = strokes_mask((200, 200), [([(20.0, 100.0), (180.0, 100.0)], 20.0)])
    assert m.getpixel((100, 100)) == 255  # on the stroke
    assert m.getpixel((100, 92)) == 255  # inside half-width
    assert m.getpixel((100, 60)) == 0  # well outside
    assert m.getpixel((12, 100)) > 200  # round cap extends past the first point
    assert m.getpixel((3, 100)) == 0
    dot = strokes_mask((50, 50), [([(25.0, 25.0)], 10.0)])  # single-point stroke is a dot
    assert dot.getpixel((25, 25)) == 255 and dot.getpixel((25, 5)) == 0


def test_highlight_bbox_ring_grows_by_half_width():
    ring = highlight_bbox_ring([Stroke(coords=[(-75.1650, 39.9520), (-75.1640, 39.9520)], width_m=20.0)])
    assert len(ring) == 5 and ring[0] == ring[-1]
    w, n = ring[0]
    e, s = ring[2]
    assert w < -75.1650 and e > -75.1640
    # 10 m half-width is ~0.00009 deg of latitude
    assert abs((n - 39.9520) - 10 / 110540.0) < 1e-7
    assert abs((39.9520 - s) - 10 / 110540.0) < 1e-7


def test_mask_opaque_inside_transparent_outside():
    poly = [(100, 100), (300, 100), (300, 300), (100, 300)]
    m = polygon_mask((400, 400), poly)
    assert m.getpixel((200, 200)) == 255
    assert m.getpixel((110, 110)) == 255
    assert m.getpixel((20, 20)) == 0
    assert m.getpixel((390, 390)) == 0
    # Feather band lies entirely outside the polygon edge: the edge itself is fully opaque.
    assert m.getpixel((100, 200)) == 255
    assert m.getpixel((300, 200)) == 255
    assert 0 < m.getpixel((97, 200)) < 255
    assert m.getpixel((90, 200)) == 0


def test_overlay_alpha_is_mask():
    poly = [(10, 10), (50, 10), (50, 50), (10, 50)]
    base = Image.new("RGB", (64, 64), (200, 30, 30))
    m = polygon_mask((64, 64), poly, feather_px=0)
    ov = make_overlay(base, m)
    assert ov.mode == "RGBA"
    assert ov.getpixel((30, 30)) == (200, 30, 30, 255)
    assert ov.getpixel((2, 2))[3] == 0
