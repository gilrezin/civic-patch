"""Gemini image-editing client (google-genai SDK)."""

from __future__ import annotations

import asyncio
import io
import logging

import httpx
from PIL import Image

from ..config import get_settings
from ..imaging.store import png_bytes
from .base import EditorTimeout, NoImageReturned, OutOfScope, RateLimited, SafetyRefusal, fit_to
from .prompts import NUDGE

log = logging.getLogger(__name__)

_GEMINI_SEM = asyncio.Semaphore(2)


class GeminiEditor:
    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set (see backend/example.env)")
        self._types = types
        self._model = settings.gemini_image_model
        self._client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=120_000),
        )

    def _config(self, aspect_name: str):
        types = self._types
        kwargs: dict = {"response_modalities": ["IMAGE", "TEXT"], "temperature": 0.4}
        try:
            kwargs["image_config"] = types.ImageConfig(aspect_ratio=aspect_name)
        except Exception:  # older SDK without ImageConfig
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

        config = self._config(aspect_name)
        last_err: Exception | None = None
        nudged = False
        for attempt in range(3):
            try:
                async with _GEMINI_SEM:
                    resp = await self._client.aio.models.generate_content(
                        model=self._model, contents=parts, config=config
                    )
                return self._parse(resp, base.size)
            except NoImageReturned as exc:
                last_err = exc
                if nudged:
                    raise
                nudged = True
                parts[0] = types.Part.from_text(text=prompt + NUDGE)
            except (OutOfScope, SafetyRefusal):
                raise
            except httpx.TimeoutException as exc:
                last_err = EditorTimeout(str(exc))
                if attempt >= 1:
                    raise last_err
            except Exception as exc:  # SDK APIError and friends
                code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                msg = str(exc)
                if code in (429, 503) or "RESOURCE_EXHAUSTED" in msg or "UNAVAILABLE" in msg:
                    last_err = RateLimited(msg[:200])
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

    def _parse(self, resp, expected_size: tuple[int, int]) -> Image.Image:
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
        return fit_to(img, expected_size)
