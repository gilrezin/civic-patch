"""Prompt-hint sources per municipality (comprehensive-plan RAG)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..ai import plans
from ..auth import get_current_user
from ..geo.places import reverse_geocode_full
from ..models import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/hints", tags=["hints"])


class PrepareIn(BaseModel):
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-85, le=85)


class PrepareOut(BaseModel):
    municipality: str | None
    place_name: str | None
    status: str  # ready | generating | available | failed | none
    source: str  # plan | default
    error: str | None = None


@router.post("/prepare", response_model=PrepareOut)
async def prepare(body: PrepareIn, _user: User = Depends(get_current_user)) -> PrepareOut:
    """Called when the prompt box opens: find the municipality and, if it has a comprehensive
    plan but no generated hints yet, start generating them in the background."""
    info = await reverse_geocode_full(body.lng, body.lat)
    slug = info.municipality
    status = plans.plan_status(slug)
    if status == "available":
        plans.ensure_plan_hints(slug)
        status = "generating"
        log.info("plan hints: generation started for %s (%s)", slug, info.place_name)
    else:
        log.info("plan hints: %s -> %s", slug or "unknown municipality", status)
    docs = plans.find_plan_docs(slug)
    return PrepareOut(
        municipality=docs.slug if docs else slug,
        place_name=info.place_name,
        status=status,
        source="plan" if status == "ready" else "default",
        error=plans.last_error(docs.slug if docs else slug) if status == "failed" else None,
    )
