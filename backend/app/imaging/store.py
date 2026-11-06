"""Save/load PNG files under DATA_DIR/images/{edit_id}/. DB rows store paths relative to images/."""

from __future__ import annotations

import asyncio
import io
import secrets
from pathlib import Path

from PIL import Image

from ..config import get_settings


def images_root() -> Path:
    root = get_settings().images_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_asset_dir(edit_id: int) -> str:
    """Per-edit folder name with a random token.

    Image URLs are cached as immutable for a year, and SQLite can reuse an edit id after the
    newest edit is deleted. The token guarantees a brand-new URL for every edit so a browser
    can never show a deleted edit's image for a new one.
    """
    return f"{edit_id}-{secrets.token_hex(4)}"


def rel_path(asset_dir: str, name: str) -> str:
    return f"{asset_dir}/{name}"


def asset_dir_of(rel: str) -> str:
    return rel.rsplit("/", 1)[0]


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


def delete_edit_files_sync(asset_dir: str) -> None:
    if not asset_dir or "/" in asset_dir or "\\" in asset_dir or asset_dir in (".", ".."):
        return
    d = images_root() / asset_dir
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
