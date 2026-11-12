from PIL import Image, ImageDraw

from app.imaging.contour import _point_in_ring, trace_outlines
from app.imaging.mask import raster_mask


def test_rectangle_outline():
    m = Image.new("L", (100, 80), 0)
    ImageDraw.Draw(m).rectangle([10, 20, 59, 49], fill=255)  # 50 x 30 block
    polys = trace_outlines(m)
    assert len(polys) == 1 and len(polys[0]) == 1
    ring = polys[0][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    assert min(xs) == 10 and max(xs) == 60 and min(ys) == 20 and max(ys) == 50
    assert len(ring) == 5  # simplified to the four corners (closed)


def test_hole_and_two_components():
    m = Image.new("L", (120, 120), 0)
    d = ImageDraw.Draw(m)
    d.rectangle([10, 10, 69, 69], fill=255)
    d.rectangle([30, 30, 49, 49], fill=0)  # hole
    d.ellipse([80, 80, 110, 110], fill=255)  # separate blob
    polys = trace_outlines(m, simplify_px=0.5)
    assert len(polys) == 2
    with_hole = [p for p in polys if len(p) == 2]
    assert len(with_hole) == 1
    outer, hole = with_hole[0]
    assert _point_in_ring(hole[0], outer)
    assert all(10 <= x <= 70 and 10 <= y <= 70 for x, y in outer)
    assert all(30 <= x <= 50 and 30 <= y <= 50 for x, y in hole)


def test_downsampled_large_mask_scales_back():
    m = Image.new("L", (2000, 1000), 0)
    ImageDraw.Draw(m).rectangle([400, 200, 1599, 799], fill=255)
    polys = trace_outlines(m, max_side=500)
    assert len(polys) == 1
    ring = polys[0][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    assert abs(min(xs) - 400) <= 8 and abs(max(xs) - 1600) <= 8
    assert abs(min(ys) - 200) <= 8 and abs(max(ys) - 800) <= 8


def test_raster_mask_places_and_scales():
    src = Image.new("L", (10, 10), 0)
    ImageDraw.Draw(src).rectangle([0, 0, 4, 9], fill=255)  # left half
    out = raster_mask((100, 100), src, offset=(20, 30), target=(40, 40), feather_px=0)
    assert out.getpixel((25, 50)) == 255  # inside the left half, scaled 4x
    assert out.getpixel((55, 50)) == 0  # right half of the pasted block is empty
    assert out.getpixel((5, 5)) == 0
