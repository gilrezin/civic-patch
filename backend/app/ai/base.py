"""Editor interface and error classes shared by the Gemini and fake editors."""

from __future__ import annotations

import math
from typing import Protocol

from PIL import Image


class EditorError(RuntimeError):
    code = "editor_error"
    http_status = 502

    def __init__(self, message: str = ""):
        super().__init__(message or self.code)
        self.message = message or self.code


class OutOfScope(EditorError):
    code = "out_of_scope"
    http_status = 422


class SafetyRefusal(EditorError):
    code = "refused"
    http_status = 422


class NoImageReturned(EditorError):
    code = "no_image"
    http_status = 502


class RateLimited(EditorError):
    code = "busy"
    http_status = 503


class BillingError(EditorError):
    """The Gemini project has no quota/credits or the key is not authorized."""

    code = "billing"
    http_status = 402


class AuthError(EditorError):
    code = "bad_api_key"
    http_status = 502


class EditorTimeout(EditorError):
    code = "timeout"
    http_status = 504


class ImageEditor(Protocol):
    async def edit(self, base: Image.Image, mask: Image.Image | None, prompt: str, aspect_name: str) -> Image.Image: ...


def fit_to(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Center-crop to the expected aspect if it drifted by >5%, then resize to the exact size."""
    w, h = size
    ia = img.width / img.height
    ea = w / h
    if abs(math.log(ia / ea)) > math.log(1.05):
        if ia > ea:
            cw = round(img.height * ea)
            left = (img.width - cw) // 2
            img = img.crop((left, 0, left + cw, img.height))
        else:
            ch = round(img.width / ea)
            top = (img.height - ch) // 2
            img = img.crop((0, top, img.width, top + ch))
    if img.size != (w, h):
        img = img.resize((w, h), Image.LANCZOS)
    return img.convert("RGB")
