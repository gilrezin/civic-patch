"""Gemini image-editing client (google-genai SDK)."""

from __future__ import annotations

import asyncio
import io
import logging
import math
from typing import Literal

import httpx
from PIL import Image

from ..config import get_settings
from ..imaging.panorama import crop_vertical, pad_vertical
from ..imaging.store import png_bytes
from .base import (
    AuthError,
    BillingError,
    EditorTimeout,
    NoImageReturned,
    OutOfScope,
    RateLimited,
    SafetyRefusal,
    fit_to,
    stretch_to,
)
from .prompts import NUDGE

log = logging.getLogger(__name__)

_GEMINI_SEM = asyncio.Semaphore(2)


def _google_message(exc: Exception) -> str | None:
    """Pull the human-readable message out of a google-genai APIError, if present."""
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        err = details.get("error", details)
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return err["message"].strip()
    msg = getattr(exc, "message", None)
    return msg.strip() if isinstance(msg, str) and msg else None


def panorama_pad_px(size: tuple[int, int]) -> int:
    """Rows to add above and below a 2:1 panorama to reach 16:9, the nearest Gemini aspect ratio."""
    w, h = size
    return max(0, (round(w * 9 / 16) - h) // 2)


class GeminiEditor:
    def __init__(self, api_key: str | None = None, model: str | None = None, pano_model: str | None = None) -> None:
        from google import genai
        from google.genai import types

        settings = get_settings()
        api_key = api_key or settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set (see backend/example.env)")
        self._types = types
        self._model = model or settings.gemini_image_model
        self._pano_model = pano_model or settings.gemini_streetview_model or self._model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=120_000),
        )

    def _config(self, aspect_name: str | None, image_size: str | None = None):
        types = self._types
        kwargs: dict = {"response_modalities": ["IMAGE", "TEXT"], "temperature": 0.4}
        image_kwargs: dict = {}
        if aspect_name:
            image_kwargs["aspect_ratio"] = aspect_name
        if image_size:
            image_kwargs["image_size"] = image_size
        if image_kwargs:
            try:
                kwargs["image_config"] = types.ImageConfig(**image_kwargs)
            except Exception:  # older SDK without ImageConfig / image_size
                try:
                    kwargs["image_config"] = types.ImageConfig(aspect_ratio=aspect_name)
                except Exception:
                    pass
        return types.GenerateContentConfig(**kwargs)

    async def edit(self, base: Image.Image, mask: Image.Image | None, prompt: str, aspect_name: str) -> Image.Image:
        types = self._types
        parts = [
            types.Part.from_text(text=prompt),
            types.Part.from_bytes(data=png_bytes(base.convert("RGB")), mime_type="image/png"),
        ]
        if mask is not None:
            parts.append(types.Part.from_bytes(data=png_bytes(mask.convert("RGB")), mime_type="image/png"))
        return await self._generate(parts, self._config(aspect_name), base.size)

    async def edit_panorama(self, pano: Image.Image, refs: list[Image.Image], prompt: str) -> Image.Image:
        """Re-render an equirect panorama. Gemini has no 2:1 ratio, so the sphere is padded to 16:9
        (edge-replicated rows at the zenith and nadir), edited, stretched back and cropped."""
        types = self._types
        pad = panorama_pad_px(pano.size)
        padded = pad_vertical(pano.convert("RGB"), pad)
        parts = [types.Part.from_text(text=prompt), types.Part.from_bytes(data=png_bytes(padded), mime_type="image/png")]
        for ref in refs:
            parts.append(types.Part.from_bytes(data=png_bytes(ref.convert("RGB")), mime_type="image/png"))
        image_size = "2K" if self._pano_model.startswith("gemini-3") else None
        out = await self._generate(
            parts,
            self._config("16:9", image_size),
            padded.size,
            resize="stretch",
            model=self._pano_model,
            reject_aspect_over=1.3,
        )
        return crop_vertical(out, pad)

    async def _generate(
        self,
        parts: list,
        config,
        expected_size: tuple[int, int],
        *,
        resize: Literal["fit", "stretch"] = "fit",
        model: str | None = None,
        reject_aspect_over: float | None = None,
    ) -> Image.Image:
        types = self._types
        model = model or self._model
        base_text = parts[0]
        last_err: Exception | None = None
        nudged = False
        for attempt in range(3):
            try:
                async with _GEMINI_SEM:
                    resp = await self._client.aio.models.generate_content(model=model, contents=parts, config=config)
                img = self._parse(resp)
                ratio = (img.width / img.height) / (expected_size[0] / expected_size[1])
                log.info(
                    "gemini %s returned %dx%d for expected %dx%d (aspect x%.2f)",
                    model, img.width, img.height, expected_size[0], expected_size[1], ratio,
                )
                if reject_aspect_over and math.exp(abs(math.log(ratio))) > reject_aspect_over:
                    raise NoImageReturned(f"returned {img.width}x{img.height}, not a panorama")
                return fit_to(img, expected_size) if resize == "fit" else stretch_to(img, expected_size)
            except NoImageReturned as exc:
                last_err = exc
                if nudged:
                    raise
                nudged = True
                text = getattr(base_text, "text", None) or ""
                parts[0] = types.Part.from_text(text=text + NUDGE)
            except (OutOfScope, SafetyRefusal):
                raise
            except httpx.TimeoutException as exc:
                last_err = EditorTimeout(str(exc))
                if attempt >= 1:
                    raise last_err
            except Exception as exc:  # SDK APIError and friends
                code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                msg = str(exc)
                log.warning("Gemini error (attempt %d): %s", attempt + 1, msg[:500])
                lowered = msg.lower()
                if code == 402 or "prepayment" in lowered or "billing" in lowered or "quota" in lowered:
                    raise BillingError(_google_message(exc) or msg[:300]) from exc
                if code in (401, 403) or "api key not valid" in lowered or "permission_denied" in lowered:
                    raise AuthError(_google_message(exc) or msg[:300]) from exc
                if code in (429, 503) or "RESOURCE_EXHAUSTED" in msg or "UNAVAILABLE" in msg:
                    last_err = RateLimited(_google_message(exc) or msg[:200])
                    await asyncio.sleep(2.0 * (2**attempt))
                    continue
                if "timeout" in msg.lower() or "deadline" in msg.lower():
                    last_err = EditorTimeout(msg[:200])
                    if attempt >= 1:
                        raise last_err
                    continue
                log.exception("Gemini call failed")
                raise NoImageReturned(msg[:200]) from exc
        assert last_err is not None
        raise last_err

    def _parse(self, resp) -> Image.Image:
        pf = getattr(resp, "prompt_feedback", None)
        if pf is not None and getattr(pf, "block_reason", None):
            raise SafetyRefusal(str(pf.block_reason))
        candidates = getattr(resp, "candidates", None) or []
        if not candidates:
            raise NoImageReturned("no candidates")
        cand = candidates[0]
        finish = str(getattr(cand, "finish_reason", "") or "")
        text = ""
        img: Image.Image | None = None
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None) and img is None:
                img = Image.open(io.BytesIO(inline.data)).convert("RGB")
            elif getattr(part, "text", None):
                text += part.text
        if "OUT_OF_SCOPE" in text.upper():
            raise OutOfScope(text[:200])
        if img is None:
            if finish and not finish.endswith("STOP"):
                raise SafetyRefusal(finish)
            raise NoImageReturned(text[:200] or finish)
        return img
