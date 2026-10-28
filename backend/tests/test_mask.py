from PIL import Image

from app.imaging.mask import make_overlay, polygon_mask


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
