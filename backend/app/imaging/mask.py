"""Region masks (polygon or highlighter strokes) and RGBA overlay compositing."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter


def _feather(m: Image.Image, feather_px: float) -> Image.Image:
    """Dilate by three pixels then blur so the soft band sits entirely outside the region."""
    if feather_px > 0:
        m = m.filter(ImageFilter.MaxFilter(7))
        m = m.filter(ImageFilter.GaussianBlur(feather_px))
    return m


def polygon_mask(size: tuple[int, int], polygon_px: list[tuple[float, float]], feather_px: float = 1.0) -> Image.Image:
    """Opaque (255) inside the polygon, transparent (0) outside."""
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon([(round(x), round(y)) for x, y in polygon_px], fill=255)
    return _feather(m, feather_px)


def strokes_mask(
    size: tuple[int, int], strokes_px: list[tuple[list[tuple[float, float]], float]], feather_px: float = 1.0
) -> Image.Image:
    """Opaque along each highlighter stroke (round caps and joints), transparent elsewhere.

    strokes_px: list of (points in crop pixels, width in pixels).
    """
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for pts, width in strokes_px:
        w = max(1, int(round(width)))
        r = w / 2.0
        ipts = [(float(x), float(y)) for x, y in pts]
        if len(ipts) >= 2:
            d.line(ipts, fill=255, width=w, joint="curve")
        for x, y in (ipts if len(ipts) == 1 else (ipts[0], ipts[-1])):
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return _feather(m, feather_px)


def make_overlay(edited_rgb: Image.Image, mask: Image.Image) -> Image.Image:
    out = edited_rgb.convert("RGBA")
    if mask.size != out.size:
        mask = mask.resize(out.size, Image.BILINEAR)
    out.putalpha(mask)
    return out
