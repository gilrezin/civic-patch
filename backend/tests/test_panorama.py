"""Cubemap -> equirectangular reprojection and the Street View geometry helpers."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from app.geo.streetview import bearing_deg, haversine_m
from app.imaging.panorama import FACE_ANGLES, crop_vertical, cube_to_equirect, face_basis, pad_vertical

COLOURS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 255, 255), (0, 0, 0)]  # F R B L U D


def _solid_faces(size: int = 32) -> list[Image.Image]:
    return [Image.new("RGB", (size, size), c) for c in COLOURS]


def test_face_basis_matches_street_view_camera():
    f, r, u = face_basis(0, 0)
    assert np.allclose(f, [0, 1, 0]) and np.allclose(r, [1, 0, 0]) and np.allclose(u, [0, 0, 1])
    f, r, u = face_basis(90, 0)
    assert np.allclose(f, [1, 0, 0]) and np.allclose(r, [0, -1, 0])
    f, r, u = face_basis(0, 90)
    assert np.allclose(f, [0, 0, 1]) and np.allclose(u, [0, -1, 0])  # looking up, image top points south
    f, r, u = face_basis(0, -90)
    assert np.allclose(f, [0, 0, -1]) and np.allclose(u, [0, 1, 0])


def test_solid_faces_land_where_expected():
    w, h = 256, 128
    img = cube_to_equirect(_solid_faces(), w, h, center_heading_deg=0)
    assert img.size == (w, h)
    px = img.load()
    assert px[w // 2, h // 2] == COLOURS[0]  # centre faces north = front
    assert px[3 * w // 4, h // 2] == COLOURS[1]  # east = right
    assert px[w // 4, h // 2] == COLOURS[3]  # west = left
    assert px[0, h // 2] == COLOURS[2] and px[w - 1, h // 2] == COLOURS[2]  # seam = back
    assert px[w // 2, 0] == COLOURS[4]  # zenith = up
    assert px[w // 2, h - 1] == COLOURS[5]  # nadir = down

    rotated = cube_to_equirect(_solid_faces(), w, h, center_heading_deg=90).load()
    assert rotated[w // 2, h // 2] == COLOURS[1]  # centre now faces east


def _analytic_faces(size: int, fov_deg: float = 90.0) -> list[Image.Image]:
    """Each face pixel coloured by its own view direction, so the stitched result is checkable."""
    s = math.tan(math.radians(fov_deg) / 2.0)
    faces = []
    for hdg, pit in FACE_ANGLES:
        f, r, u = face_basis(hdg, pit)
        px = (np.arange(size) + 0.5) / size * 2.0 - 1.0
        x = px[None, :] * s
        y = -px[:, None] * s
        d = f[None, None, :] + x[..., None] * r[None, None, :] + y[..., None] * u[None, None, :]
        d /= np.linalg.norm(d, axis=-1, keepdims=True)
        faces.append(Image.fromarray(((d + 1.0) / 2.0 * 255.0).round().astype(np.uint8), "RGB"))
    return faces


def test_round_trip_is_self_consistent_and_seamless():
    w, h = 512, 256
    img = cube_to_equirect(_analytic_faces(128), w, h, center_heading_deg=37.0)
    got = np.asarray(img, dtype=np.float32)
    from app.imaging.panorama import direction_grid

    expected = (direction_grid(w, h, 37.0) + 1.0) / 2.0 * 255.0
    err = np.abs(got - expected)
    assert err.mean() < 1.5, err.mean()
    assert np.percentile(err, 99) < 6.0
    seam = np.abs(got[:, 0, :] - got[:, -1, :]).mean()
    assert seam < 3.0, seam


def test_pad_and_crop_vertical_round_trip():
    img = Image.fromarray(np.random.default_rng(0).integers(0, 255, (64, 128, 3), dtype=np.uint8), "RGB")
    padded = pad_vertical(img, 8)
    assert padded.size == (128, 80)
    top = np.asarray(padded)[:8]
    assert (top == np.asarray(img)[0][None]).all()
    back = crop_vertical(padded, 8)
    assert back.size == img.size and (np.asarray(back) == np.asarray(img)).all()


def test_bearing_and_distance():
    lat, lng = 40.0, -75.0
    assert abs(bearing_deg(lat, lng, lat, lng + 0.001) - 90.0) < 0.1
    assert abs(bearing_deg(lat, lng, lat + 0.001, lng) - 0.0) < 0.1
    assert abs(bearing_deg(lat, lng, lat - 0.001, lng) - 180.0) < 0.1
    east_m = haversine_m(lat, lng, lat, lng + 0.001)
    assert 84 < east_m < 87, east_m
    assert 110 < haversine_m(lat, lng, lat + 0.001, lng) < 112
