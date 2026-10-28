"""Save/load PNG files under DATA_DIR/images/{edit_id}/. DB rows store paths relative to images/."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

from PIL import Image

from ..config import get_settings


def images_root() -> Path:
    root = get_settings().images_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def rel_path(edit_id: int, name: str) -> str:
    return f"{edit_id}/{name}"


def abs_path(rel: str) -> Path:
    return images_root() / rel


def save_png_sync(img: Image.Image, rel: str) -> str:
    path = abs_path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=False)
    return rel


async def save_png(img: Image.Image, rel: str) -> str:
    return await asyncio.to_thread(save_png_sync, img, rel)


def load_image_sync(rel: str) -> Image.Image:
    with Image.open(abs_path(rel)) as im:
        im.load()
        return im.copy()


async def load_image(rel: str) -> Image.Image:
    return await asyncio.to_thread(load_image_sync, rel)


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def delete_edit_files_sync(edit_id: int) -> None:
    d = images_root() / str(edit_id)
    if d.is_dir():
        for p in d.iterdir():
            try:
                p.unlink()
            except OSError:
                pass
        try:
            d.rmdir()
        except OSError:
            pass
