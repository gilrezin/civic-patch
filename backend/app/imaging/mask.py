"""Polygon masks and RGBA overlay compositing."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter


def polygon_mask(size: tuple[int, int], polygon_px: list[tuple[float, float]], feather_px: float = 1.0) -> Image.Image:
    """Opaque (255) inside the polygon, transparent (0) outside.

    The mask is dilated by three pixels before feathering so the soft band sits entirely
    outside the polygon edge and the original imagery inside is fully covered.
    """
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon([(round(x), round(y)) for x, y in polygon_px], fill=255)
    if feather_px > 0:
        m = m.filter(ImageFilter.MaxFilter(7))
        m = m.filter(ImageFilter.GaussianBlur(feather_px))
    return m


def make_overlay(edited_rgb: Image.Image, mask: Image.Image) -> Image.Image:
    out = edited_rgb.convert("RGBA")
    if mask.size != out.size:
        mask = mask.resize(out.size, Image.BILINEAR)
    out.putalpha(mask)
    return out
