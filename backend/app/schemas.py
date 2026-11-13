"""Pydantic request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    display_name: str


class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=32)


class LoginIn(BaseModel):
    email: str
    password: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


class VersionOut(BaseModel):
    id: int
    version_number: int
    prompt: str
    parent_version_id: int | None
    overlay_url: str | None
    full_url: str | None
    status: str
    error: str | None = None
    created_by: UserOut
    created_at: datetime


class StrokeIn(BaseModel):
    coordinates: list[list[float]] = Field(min_length=1, max_length=800)
    width_m: float


class HighlightIn(BaseModel):
    strokes: list[StrokeIn] = Field(min_length=1, max_length=60)


class SmartIn(BaseModel):
    """Smart-select result: mapped areas as rings plus road segments as strokes."""

    polygons: list[list[list[float]]] = Field(default_factory=list, max_length=200)
    strokes: list[StrokeIn] = Field(default_factory=list, max_length=200)


class MaskIn(BaseModel):
    """Quick-selection result: a binary PNG in Web Mercator tile-pixel space at `zoom`,
    whose top-left pixel is world pixel (x0, y0)."""

    zoom: int = Field(ge=10, le=20)
    x0: int = Field(ge=0)
    y0: int = Field(ge=0)
    width: int = Field(ge=1, le=2048)
    height: int = Field(ge=1, le=2048)
    png: str = Field(min_length=8, max_length=12_000_000)


class MaskOut(BaseModel):
    """Outline polygons for display: each polygon is [outer ring, hole, hole, ...]."""

    polygons: list[list[list[list[float]]]]


class EditOut(BaseModel):
    id: int
    kind: Literal["polygon", "highlight", "smart", "mask"] = "polygon"
    highlight: HighlightIn | None = None
    smart: SmartIn | None = None
    mask: MaskOut | None = None
    polygon: dict[str, Any]
    bounds: tuple[float, float, float, float]
    status: str
    error: str | None = None
    created_by: UserOut
    created_at: datetime
    updated_at: datetime
    current_version: VersionOut | None
    original_prompt: str
    version_count: int
    score: int
    up: int
    down: int
    my_vote: int
    comment_count: int
    original_url: str
    place_name: str | None = None
    saved: bool = False


class ContributionOut(BaseModel):
    """One thing the current user did on the map: an initial edit or a refinement."""

    version_id: int
    edit_id: int
    kind: Literal["edit", "refinement"]
    prompt: str
    version_number: int
    created_at: datetime
    place_name: str | None
    centroid: tuple[float, float]
    edit_original_prompt: str
    edit_creator: UserOut
    edit_status: str
    score: int


class StreetViewOut(BaseModel):
    """A Gemini-edited Street View panorama for one version of an edit."""

    id: int
    edit_id: int
    version_id: int
    version_number: int
    pano_id: str
    lat: float
    lng: float
    heading: float  # compass bearing at the centre column of the panorama (toward the site)
    distance_m: float
    pano_date: str | None = None
    original_url: str
    edited_url: str
    status: str
    created_at: datetime


class BookmarkIn(BaseModel):
    saved: bool


class BookmarkOut(BaseModel):
    saved: bool


class EditCreateIn(BaseModel):
    """Exactly one of `polygon` (GeoJSON Polygon) or `highlight` (strokes) must be given."""

    polygon: dict[str, Any] | None = None
    highlight: HighlightIn | None = None
    smart: SmartIn | None = None
    mask: MaskIn | None = None
    prompt: str = Field(max_length=2000)


class RefineIn(BaseModel):
    prompt: str = Field(max_length=2000)


class VoteIn(BaseModel):
    value: Literal[-1, 0, 1]


class VoteOut(BaseModel):
    score: int
    up: int
    down: int
    my_vote: int


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class CommentOut(BaseModel):
    id: int
    edit_id: int
    body: str
    author: UserOut
    created_at: datetime


class ErrorBody(BaseModel):
    code: str
    message: str
