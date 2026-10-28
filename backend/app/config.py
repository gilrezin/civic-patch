"""Application settings, loaded from environment variables and backend/.env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-2.5-flash-image"
    editor: Literal["gemini", "fake"] = "gemini"
    region_hint: Literal["mask", "text"] = "mask"

    jwt_secret: str = "dev-only-insecure-secret"
    jwt_expiry_days: int = 30

    data_dir: Path = BACKEND_DIR / "data"

    max_bbox_km2: float = 1.0
    min_poly_m2: float = 20.0
    generations_per_10_min: int = 5

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Crop sizing
    min_zoom: int = 14
    max_zoom: int = 19
    target_min_px: int = 768
    context_margin: float = 0.15

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def images_dir(self) -> Path:
        return self.resolved_data_dir / "images"

    @property
    def resolved_data_dir(self) -> Path:
        d = self.data_dir
        if not d.is_absolute():
            d = BACKEND_DIR / d
        return d

    @property
    def db_path(self) -> Path:
        return self.resolved_data_dir / "civic_patch.sqlite3"


@lru_cache
def get_settings() -> Settings:
    return Settings()
