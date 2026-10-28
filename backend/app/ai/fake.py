"""Offline stand-in for Gemini: tints the crop and stamps a few blocks so edits are visible."""

from __future__ import annotations

import asyncio
import hashlib

from PIL import Image, ImageDraw, ImageEnhance

from .base import OutOfScope


class FakeEditor:
    def __init__(self, delay_s: float = 1.0) -> None:
        self.delay_s = delay_s

    async def edit(self, base: Image.Image, mask: Image.Image | None, prompt: str, aspect_name: str) -> Image.Image:
        await asyncio.sleep(self.delay_s)
        if "out of scope" in prompt.lower():
            raise OutOfScope("OUT_OF_SCOPE")
        seed = int(hashlib.sha1(prompt.encode()).hexdigest()[:6], 16)
        hue = seed % 3
        rgb = base.convert("RGB")
        r, g, b = rgb.split()
        boost = ImageEnhance.Brightness([r, g, b][hue]).enhance(1.35)
        channels = [r, g, b]
        channels[hue] = boost
        out = Image.merge("RGB", channels)
        draw = ImageDraw.Draw(out)
        w, h = out.size
        step = max(24, min(w, h) // 8)
        for i in range(3):
            x = int(w * 0.3) + (seed % 50) + i * step
            y = int(h * 0.3) + (seed // 7 % 50) + i * (step // 2)
            draw.rectangle([x, y, x + step, y + step], outline=(255, 255, 255), width=2)
        return out
