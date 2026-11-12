"""Comprehensive-plan hint generation: slugs, discovery, chunking, retrieval, fallback and the
prepare endpoint. Gemini calls are stubbed; no network."""

import asyncio
import json

import pytest

from app.ai import hints, plans
from app.config import get_settings
from app.geo.places import PlaceInfo, municipality_slug


def test_municipality_slug_from_nominatim_address():
    assert municipality_slug({"city": "Philadelphia", "ISO3166-2-lvl4": "US-PA", "state": "Pennsylvania"}) == "Philadelphia-PA"
    assert municipality_slug({"town": "West Chester", "ISO3166-2-lvl4": "US-PA"}) == "West-Chester-PA"
    assert municipality_slug({"city": "Paris", "state": "Ile-de-France", "country_code": "fr"}) == "Paris-Ile-de-France"
    assert municipality_slug({"county": "Nowhere County", "state": "PA"}) is None


def test_chunking_and_lexical_retrieval():
    text = ("Transit corridors should get dedicated bus lanes. " * 30 + "\n\n" + "Parks need more street trees and stormwater planters. " * 30)
    chunks = plans.chunk_text(text, size=600, overlap=50)
    assert len(chunks) >= 3 and all(len(c) <= 700 for c in chunks)
    context, used = plans.select_context(chunks, None, None, top_k=2)
    assert used >= 2 and "bus lanes" in context and "street trees" in context


@pytest.fixture
def plan_folder(tmp_path, monkeypatch):
    settings = get_settings()
    root = tmp_path / "plans"
    (root / "Testville-TS").mkdir(parents=True)
    (root / "Testville-TS" / "plan.txt").write_text(
        "Testville 2040 Plan. Bus rapid transit on Main Street with red centre-running lanes. "
        "New housing should be three-storey rowhouses with front porches. "
        "Every block gets a tree canopy goal of 30 percent. " * 20,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "plans_dir", root)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    plans._tasks.clear()
    plans._failed_at.clear()
    plans._errors.clear()
    yield root


def test_discovery_and_default_fallback(plan_folder):
    assert plans.find_plan_docs("testville-ts").slug == "Testville-TS"  # case-insensitive
    assert plans.find_plan_docs("Elsewhere-XX") is None
    assert plans.plan_status("Elsewhere-XX") == "none"
    assert plans.plan_status("Testville-TS") == "available"
    assert plans.hints_path_for("Testville-TS") == get_settings().resolved_prompt_hints_file
    assert plans.hints_path_for(None) == get_settings().resolved_prompt_hints_file


def test_generation_pipeline_with_stubbed_gemini(plan_folder, monkeypatch):
    calls = {"embed": 0, "generate": 0}

    async def fake_embed(texts, task_type):
        calls["embed"] += 1
        # Deterministic pseudo-embeddings: direction from a few keyword counts.
        return [[float(t.lower().count("bus")), float(t.lower().count("tree")), float(t.lower().count("housing")), 1.0] for t in texts]

    async def fake_generate(prompt):
        calls["generate"] += 1
        assert "Testville" in prompt and "EXCERPTS" in prompt and "red centre-running" in prompt
        return {
            "_comment": "Generated from the Testville 2040 Plan.",
            "bus": "Centre-running red bus lanes on Main Street as the plan calls for.",
            "bike": "x", "tree": "Reach the 30 percent canopy goal with rows of trees.", "park": "x",
            "housing": "Three-storey rowhouses with front porches.", "parking": "x", "plaza": "x", "crosswalk": "x",
        }

    monkeypatch.setattr(plans, "embed_texts", fake_embed)
    monkeypatch.setattr(plans, "generate_json", fake_generate)

    async def run():
        task = plans.ensure_plan_hints("Testville-TS")
        assert task is not None and plans.plan_status("Testville-TS") == "generating"
        assert plans.ensure_plan_hints("Testville-TS") is task  # no duplicate job
        await plans.wait_for_plan_hints("Testville-TS", 10)
        return task

    asyncio.run(run())
    out = plans.plan_hints_path("Testville-TS")
    assert out.is_file() and plans.plan_status("Testville-TS") == "ready"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["_source"] == "plan.txt" and "_generated" in data
    assert calls["embed"] == 2 and calls["generate"] == 1  # chunks + topics, one generation

    # The generated file now replaces the default for this municipality only.
    assert plans.hints_path_for("Testville-TS") == out
    assert hints.hints_for("add bus lanes here", plans.hints_path_for("Testville-TS")) == [
        "Centre-running red bus lanes on Main Street as the plan calls for."
    ]
    assert hints.hints_for("add bus lanes here", plans.hints_path_for("Elsewhere-XX"))[0].startswith("The bus lanes occupy")

    # The index is cached: a second generation (file removed) embeds only the topics again.
    out.unlink()
    asyncio.run(run())
    assert calls["embed"] == 3 and calls["generate"] == 2


def test_generation_failure_is_remembered_and_falls_back(plan_folder, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("quota")

    monkeypatch.setattr(plans, "embed_texts", boom)
    monkeypatch.setattr(plans, "generate_json", boom)

    async def run():
        plans.ensure_plan_hints("Testville-TS")
        await plans.wait_for_plan_hints("Testville-TS", 10)

    asyncio.run(run())
    assert plans.plan_status("Testville-TS") == "failed"
    assert "quota" in (plans.last_error("Testville-TS") or "")
    assert plans.hints_path_for("Testville-TS") == get_settings().resolved_prompt_hints_file
    assert plans.ensure_plan_hints("Testville-TS") is None  # no immediate retry storm


def test_place_detail_and_header_endpoints(client, plan_folder, monkeypatch):
    from app.geo.places import PlaceDetail, place_detail_from_address
    from app.routers import places as places_router

    d = place_detail_from_address({"neighbourhood": "Rittenhouse Square", "city": "Philadelphia", "state": "Pennsylvania", "ISO3166-2-lvl4": "US-PA"})
    assert (d.city, d.neighbourhood, d.municipality) == ("Philadelphia", "Rittenhouse Square", "Philadelphia-PA")

    async def fake_here(lng, lat):
        return PlaceDetail("Downtown, Testville", "Testville-TS", "Testville", "Downtown", "Teststate")

    async def fake_search(q, limit=6):
        return [{"name": f"Result for {q}", "lng": -75.1, "lat": 39.9, "bbox": [-75.2, 39.8, -75.0, 40.0]}]

    monkeypatch.setattr(places_router, "describe_point", fake_here)
    monkeypatch.setattr(places_router, "search_places", fake_search)

    r = client.get("/api/places/here?lng=-75.1&lat=39.9")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["city"] == "Testville" and body["neighbourhood"] == "Downtown"
    assert body["plan"] == {"exists": True, "municipality": "Testville-TS", "filename": "plan.txt", "url": "/api/plans/Testville-TS/document", "hints_status": "available"}

    doc = client.get("/api/plans/Testville-TS/document")
    assert doc.status_code == 200 and "Testville 2040 Plan" in doc.text
    assert "plan.txt" in doc.headers["content-disposition"]
    assert client.get("/api/plans/Elsewhere-XX/document").status_code == 404
    assert client.get("/api/plans/..%2F..%2Fetc/document").status_code == 404

    r = client.get("/api/places/search?q=City%20Hall")
    assert r.status_code == 200 and r.json()[0]["name"] == "Result for City Hall" and len(r.json()[0]["bbox"]) == 4
    assert client.get("/api/places/search?q=a").status_code == 422


def test_prepare_endpoint(client, plan_folder, monkeypatch):
    from app.routers import hints as hints_router

    async def fake_geo(lng, lat):
        return PlaceInfo("Downtown, Testville", "Testville-TS")

    monkeypatch.setattr(hints_router, "reverse_geocode_full", fake_geo)
    started = []
    monkeypatch.setattr(plans, "ensure_plan_hints", lambda slug: started.append(slug) or None)

    assert client.post("/api/hints/prepare", json={"lng": -75.1, "lat": 39.9}).status_code == 401
    r = client.post("/api/auth/signup", json={"email": "p@example.com", "password": "password123", "display_name": "planner1"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r = client.post("/api/hints/prepare", json={"lng": -75.1, "lat": 39.9}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["municipality"] == "Testville-TS" and body["status"] == "generating" and body["source"] == "default"
    assert started == ["Testville-TS"]

    plans.plan_hints_path("Testville-TS").parent.mkdir(parents=True, exist_ok=True)
    plans.plan_hints_path("Testville-TS").write_text('{"bus": "x"}', encoding="utf-8")
    body = client.post("/api/hints/prepare", json={"lng": -75.1, "lat": 39.9}, headers=h).json()
    assert body["status"] == "ready" and body["source"] == "plan"

    async def nowhere(lng, lat):
        return PlaceInfo("Somewhere", "Elsewhere-XX")

    monkeypatch.setattr(hints_router, "reverse_geocode_full", nowhere)
    body = client.post("/api/hints/prepare", json={"lng": 0, "lat": 0}, headers=h).json()
    assert body["status"] == "none" and body["source"] == "default"
