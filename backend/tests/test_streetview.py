"""Street view endpoints with stubbed Google calls and the fake editor."""

from __future__ import annotations

import uuid

import pytest
from PIL import Image

from app.config import get_settings
from app.geo.streetview import Pano
from app.imaging import store
from app.services import streetview as sv

POLY = {
    "type": "Polygon",
    "coordinates": [[[-75.1665, 39.9535], [-75.1640, 39.9535], [-75.1640, 39.9518], [-75.1665, 39.9518]]],
}
COLOURS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 255, 255), (0, 0, 0)]


def _signup(client):
    name = f"u{uuid.uuid4().hex[:8]}"
    r = client.post("/api/auth/signup", json={"email": f"{name}@example.com", "password": "password123", "display_name": name})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _rel(url: str) -> str:
    assert url.startswith("/images/"), url
    return url[len("/images/") :]


@pytest.fixture
def google_stub(monkeypatch):
    calls = {"meta": 0, "faces": 0, "pano": True}
    settings = get_settings()
    monkeypatch.setattr(settings, "google_street_view_api_key", "test-key")
    monkeypatch.setattr(settings, "streetview_pano_width", 512)
    monkeypatch.setattr(settings, "streetview_face_px", 64)

    async def fake_find(lat, lng, *, max_radius_m, api_key):
        calls["meta"] += 1
        assert api_key == "test-key"
        return Pano("pano-1", lat + 0.0005, lng, "2023-05") if calls["pano"] else None

    async def fake_faces(pano_id, *, size_px, fov, api_key):
        calls["faces"] += 1
        assert pano_id == "pano-1"
        return [Image.new("RGB", (size_px, size_px), c) for c in COLOURS]

    monkeypatch.setattr(sv, "find_pano", fake_find)
    monkeypatch.setattr(sv, "fetch_faces", fake_faces)
    return calls


def test_street_view_flow(client, google_stub):
    headers = _signup(client)
    edit = client.post("/api/edits", json={"polygon": POLY, "prompt": "add bus lanes"}, headers=headers).json()
    eid = edit["id"]

    r = client.get(f"/api/edits/{eid}/street-view")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_generated"
    assert client.post(f"/api/edits/{eid}/street-view").status_code == 401

    r = client.post(f"/api/edits/{eid}/street-view", headers=headers)
    assert r.status_code == 200, r.text
    svo = r.json()
    assert svo["status"] == "done" and svo["version_number"] == 1 and svo["edit_id"] == eid
    assert svo["version_id"] == edit["current_version"]["id"]
    # The pano sits ~55 m north of the site, so the camera centre faces south.
    assert 170 < svo["heading"] < 190, svo["heading"]
    assert 50 < svo["distance_m"] < 60
    assert svo["pano_date"] == "2023-05" and svo["pano_id"] == "pano-1"

    orig = store.load_image_sync(_rel(svo["original_url"]))
    edited = store.load_image_sync(_rel(svo["edited_url"]))
    assert orig.size == (512, 256) and edited.size == (512, 256)
    assert orig.tobytes() != edited.tobytes()
    assert client.get(svo["edited_url"]).status_code == 200
    # The camera faces south (heading ~180), so the centre column shows the back face (blue) and the
    # wrap seam, directly behind the viewer, shows the north-facing front face (red).
    assert orig.getpixel((256, 128)) == COLOURS[2]
    assert orig.getpixel((0, 128)) == COLOURS[0]

    # Idempotent for the same version: no second Google round trip.
    again = client.post(f"/api/edits/{eid}/street-view", headers=headers).json()
    assert again["id"] == svo["id"]
    assert google_stub["faces"] == 1
    assert client.get(f"/api/edits/{eid}/street-view").json()["id"] == svo["id"]

    # After a refinement the old view is still served (stale) and a POST renders the new version.
    refined = client.post(f"/api/edits/{eid}/refine", json={"prompt": "add street trees"}, headers=headers).json()
    stale = client.get(f"/api/edits/{eid}/street-view").json()
    assert stale["id"] == svo["id"] and stale["version_id"] != refined["current_version"]["id"]
    fresh = client.post(f"/api/edits/{eid}/street-view", headers=headers).json()
    assert fresh["id"] != svo["id"] and fresh["version_number"] == 2
    assert fresh["version_id"] == refined["current_version"]["id"]
    assert google_stub["faces"] == 2
    assert client.get(f"/api/edits/{eid}/street-view").json()["id"] == fresh["id"]

    # Deleting the edit removes the files and the rows.
    paths = [store.abs_path(_rel(u)) for u in (svo["original_url"], svo["edited_url"], fresh["edited_url"])]
    assert all(p.exists() for p in paths)
    assert client.delete(f"/api/edits/{eid}", headers=headers).status_code == 204
    assert not any(p.exists() for p in paths)
    assert client.get(f"/api/edits/{eid}/street-view").status_code == 404


def test_street_view_errors(client, google_stub):
    headers = _signup(client)
    eid = client.post("/api/edits", json={"polygon": POLY, "prompt": "plant trees"}, headers=headers).json()["id"]

    google_stub["pano"] = False
    r = client.post(f"/api/edits/{eid}/street-view", headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_street_view"
    google_stub["pano"] = True

    class Held:
        def locked(self):
            return True

    sv._locks[eid] = Held()  # type: ignore[assignment]
    try:
        r = client.post(f"/api/edits/{eid}/street-view", headers=headers)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "in_progress"
    finally:
        sv._locks.pop(eid, None)

    get_settings().google_street_view_api_key = ""
    r = client.post(f"/api/edits/{eid}/street-view", headers=headers)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "streetview_not_configured"

    assert client.get("/api/edits/999999/street-view").status_code == 404
