"""Where-am-I, place search, and comprehensive-plan document download for the header."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..ai import plans
from ..geo.places import describe_point, search_places
from ..services.edits import http_error

router = APIRouter(tags=["places"])

_SLUG_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,78}$")


class PlanRef(BaseModel):
    exists: bool
    municipality: str | None = None
    filename: str | None = None
    url: str | None = None
    hints_status: str | None = None


class HereOut(BaseModel):
    city: str | None
    neighbourhood: str | None
    region: str | None
    place_name: str | None
    municipality: str | None
    plan: PlanRef


class SearchHit(BaseModel):
    name: str
    lng: float
    lat: float
    bbox: list[float]


def _plan_ref(slug: str | None) -> PlanRef:
    docs = plans.find_plan_docs(slug)
    if docs is None:
        return PlanRef(exists=False, municipality=slug)
    pdf = next((p for p in docs.files if p.suffix.lower() == ".pdf"), docs.files[0])
    return PlanRef(
        exists=True,
        municipality=docs.slug,
        filename=pdf.name,
        url=f"/api/plans/{docs.slug}/document",
        hints_status=plans.plan_status(docs.slug),
    )


@router.get("/places/here", response_model=HereOut)
async def here(lng: float = Query(ge=-180, le=180), lat: float = Query(ge=-85, le=85)) -> HereOut:
    d = await describe_point(lng, lat)
    return HereOut(
        city=d.city,
        neighbourhood=d.neighbourhood,
        region=d.region,
        place_name=d.place_name,
        municipality=d.municipality,
        plan=_plan_ref(d.municipality),
    )


@router.get("/places/search", response_model=list[SearchHit])
async def search(q: str = Query(min_length=2, max_length=200)) -> list[SearchHit]:
    return [SearchHit(**h) for h in await search_places(q)]


@router.get("/plans/{slug}/document")
async def plan_document(slug: str) -> FileResponse:
    if not _SLUG_OK.match(slug):
        raise http_error(404, "not_found", "No plan for that municipality.")
    docs = plans.find_plan_docs(slug)
    if docs is None:
        raise http_error(404, "not_found", "No comprehensive plan is on file for that municipality.")
    pdf = next((p for p in docs.files if p.suffix.lower() == ".pdf"), docs.files[0])
    media = "application/pdf" if pdf.suffix.lower() == ".pdf" else "text/plain; charset=utf-8"
    return FileResponse(str(pdf), media_type=media, filename=pdf.name)
