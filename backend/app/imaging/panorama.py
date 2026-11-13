"""Reproject six Street View cube faces into one equirectangular 360 panorama.

The Street View Static API only serves single rectilinear views, so a full sphere is
assembled from six 90-degree faces (four around the horizon, one up, one down). Every face is
modelled as the same camera turned to (heading, pitch): yaw about the vertical axis, then
pitch about the camera's right axis. World frame: x = east, y = north, z = up; a compass
heading h (0 = north, clockwise) points along (sin h, cos h).

The equirectangular output has its centre column facing `center_heading_deg`, so the viewer
can open facing the edited site and the wrap seam sits directly behind the camera.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from PIL import Image

# (heading, pitch) of each face in the order the service fetches them.
FACE_ANGLES: tuple[tuple[float, float], ...] = ((0, 0), (90, 0), (180, 0), (270, 0), (0, 90), (0, -90))


def face_basis(heading_deg: float, pitch_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Unit (forward, right, up) vectors of a camera at the given heading and pitch."""
    h = math.radians(heading_deg)
    p = math.radians(pitch_deg)
    f0 = np.array([math.sin(h), math.cos(h), 0.0])
    right = np.array([math.cos(h), -math.sin(h), 0.0])
    u0 = np.array([0.0, 0.0, 1.0])
    forward = math.cos(p) * f0 + math.sin(p) * u0
    up = -math.sin(p) * f0 + math.cos(p) * u0
    return forward, right, up


def direction_grid(width: int, height: int, center_heading_deg: float) -> np.ndarray:
    """Unit view direction for every equirect pixel centre, shape (H, W, 3) float32."""
    i = np.arange(width, dtype=np.float64)
    j = np.arange(height, dtype=np.float64)
    lon = (i + 0.5) / width * (2.0 * math.pi) - math.pi
    lat = math.pi / 2.0 - (j + 0.5) / height * math.pi
    h = math.radians(center_heading_deg) + lon
    cos_lat = np.cos(lat)[:, None]
    dx = cos_lat * np.sin(h)[None, :]
    dy = cos_lat * np.cos(h)[None, :]
    dz = np.broadcast_to(np.sin(lat)[:, None], (height, width))
    return np.stack([dx, dy, dz], axis=-1).astype(np.float32)


def cube_to_equirect(
    faces: Sequence[Image.Image],
    width: int,
    height: int | None = None,
    *,
    center_heading_deg: float = 0.0,
    fov_deg: float = 90.0,
    face_angles: Sequence[tuple[float, float]] = FACE_ANGLES,
) -> Image.Image:
    """Stitch `faces` (square, in `face_angles` order) into a width x height equirect image."""
    if len(faces) != len(face_angles):
        raise ValueError(f"expected {len(face_angles)} faces, got {len(faces)}")
    height = height or width // 2
    size = faces[0].width
    cube = np.stack([np.asarray(im.convert("RGB").resize((size, size)), dtype=np.float32) for im in faces])

    bases = [face_basis(h, p) for h, p in face_angles]
    fwd = np.array([b[0] for b in bases], dtype=np.float32)
    rgt = np.array([b[1] for b in bases], dtype=np.float32)
    upv = np.array([b[2] for b in bases], dtype=np.float32)

    d = direction_grid(width, height, center_heading_deg)
    depth = np.einsum("hwc,fc->fhw", d, fwd)
    face = depth.argmax(axis=0)
    sel = face[None]
    dep = np.take_along_axis(depth, sel, 0)[0]
    xr = np.take_along_axis(np.einsum("hwc,fc->fhw", d, rgt), sel, 0)[0]
    yu = np.take_along_axis(np.einsum("hwc,fc->fhw", d, upv), sel, 0)[0]

    s = math.tan(math.radians(fov_deg) / 2.0)
    half = size / 2.0
    px = np.clip((xr / dep / s + 1.0) * half - 0.5, 0.0, size - 1.0)
    py = np.clip((1.0 - yu / dep / s) * half - 0.5, 0.0, size - 1.0)

    x0 = np.floor(px).astype(np.intp)
    y0 = np.floor(py).astype(np.intp)
    x1 = np.minimum(x0 + 1, size - 1)
    y1 = np.minimum(y0 + 1, size - 1)
    wx = (px - x0)[..., None]
    wy = (py - y0)[..., None]

    out = (
        cube[face, y0, x0] * (1.0 - wx) * (1.0 - wy)
        + cube[face, y0, x1] * wx * (1.0 - wy)
        + cube[face, y1, x0] * (1.0 - wx) * wy
        + cube[face, y1, x1] * wx * wy
    )
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGB")


def pad_vertical(img: Image.Image, px: int) -> Image.Image:
    """Add `px` edge-replicated rows above and below (2:1 -> 16:9 for Gemini)."""
    if px <= 0:
        return img
    arr = np.asarray(img.convert("RGB"))
    return Image.fromarray(np.pad(arr, ((px, px), (0, 0), (0, 0)), mode="edge"), "RGB")


def crop_vertical(img: Image.Image, px: int) -> Image.Image:
    if px <= 0:
        return img
    return img.crop((0, px, img.width, img.height - px))
