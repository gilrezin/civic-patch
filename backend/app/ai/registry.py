"""Select the configured image editor once per process."""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import ImageEditor


@lru_cache
def get_editor() -> ImageEditor:
    settings = get_settings()
    if settings.editor == "fake":
        from .fake import FakeEditor

        return FakeEditor()
    from .gemini import GeminiEditor

    return GeminiEditor()
