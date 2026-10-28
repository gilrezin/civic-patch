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


class EditOut(BaseModel):
    id: int
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


class EditCreateIn(BaseModel):
    polygon: dict[str, Any]
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
