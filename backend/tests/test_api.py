"""End-to-end API flow with the fake editor and stubbed tiles."""

import uuid

POLY = {
    "type": "Polygon",
    "coordinates": [[[-75.1665, 39.9535], [-75.1640, 39.9535], [-75.1640, 39.9518], [-75.1665, 39.9518]]],
}


def _signup(client, name=None):
    name = name or f"u{uuid.uuid4().hex[:8]}"
    r = client.post("/api/auth/signup", json={"email": f"{name}@example.com", "password": "password123", "display_name": name})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]


def test_auth_flow(client):
    headers, user = _signup(client)
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200 and r.json()["id"] == user["id"]
    r = client.post("/api/auth/login", json={"email": f"{user['display_name']}@example.com", "password": "wrong"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", json={"email": f"{user['display_name']}@example.com", "password": "password123"})
    assert r.status_code == 200
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_create_refine_vote_comment(client):
    headers, user = _signup(client)
    r = client.post("/api/edits", json={"polygon": POLY, "prompt": "infill this parking lot with housing"}, headers=headers)
    assert r.status_code == 201, r.text
    edit = r.json()
    assert edit["status"] == "done"
    assert edit["current_version"]["version_number"] == 1
    assert edit["current_version"]["overlay_url"].startswith("/images/")
    assert edit["version_count"] == 1
    assert edit["created_by"]["display_name"] == user["display_name"]
    # Timestamps must carry a UTC marker so browsers do not parse them as local time.
    from datetime import datetime, timezone

    for ts in (edit["created_at"], edit["updated_at"], edit["current_version"]["created_at"]):
        assert ts.endswith("Z") or ts.endswith("+00:00"), ts
        age = datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert 0 <= age.total_seconds() < 120
    w, s, e, n = edit["bounds"]
    assert w < -75.1665 and e > -75.1640 and s < 39.9518 and n > 39.9535

    img = client.get(edit["current_version"]["overlay_url"])
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert "immutable" in img.headers["cache-control"]

    r = client.post(f"/api/edits/{edit['id']}/refine", json={"prompt": "add street trees"}, headers=headers)
    assert r.status_code == 200, r.text
    refined = r.json()
    assert refined["current_version"]["version_number"] == 2
    assert refined["version_count"] == 2
    assert refined["original_prompt"] == "infill this parking lot with housing"
    assert refined["current_version"]["prompt"] == "add street trees"
    assert refined["current_version"]["parent_version_id"] == edit["current_version"]["id"]

    r = client.get(f"/api/edits/{edit['id']}/versions")
    assert [v["version_number"] for v in r.json()] == [1, 2]

    # Votes from two users
    headers2, _ = _signup(client)
    r = client.put(f"/api/edits/{edit['id']}/vote", json={"value": 1}, headers=headers)
    assert r.json() == {"score": 1, "up": 1, "down": 0, "my_vote": 1}
    r = client.put(f"/api/edits/{edit['id']}/vote", json={"value": -1}, headers=headers2)
    assert r.json() == {"score": 0, "up": 1, "down": 1, "my_vote": -1}
    r = client.put(f"/api/edits/{edit['id']}/vote", json={"value": 0}, headers=headers2)
    assert r.json() == {"score": 1, "up": 1, "down": 0, "my_vote": 0}

    r = client.post(f"/api/edits/{edit['id']}/comments", json={"body": "Love it"}, headers=headers2)
    assert r.status_code == 201
    r = client.get(f"/api/edits/{edit['id']}/comments")
    assert len(r.json()) == 1 and r.json()[0]["body"] == "Love it"

    r = client.get("/api/edits", headers=headers)
    listed = [x for x in r.json() if x["id"] == edit["id"]][0]
    assert listed["score"] == 1 and listed["my_vote"] == 1 and listed["comment_count"] == 1

    r = client.get("/api/edits?bbox=-75.2,39.9,-75.1,40.0")
    assert any(x["id"] == edit["id"] for x in r.json())
    r = client.get("/api/edits?bbox=0,0,1,1")
    assert not any(x["id"] == edit["id"] for x in r.json())


def test_contributions_bookmarks_and_delete(client):
    owner_h, owner = _signup(client)
    other_h, other = _signup(client)

    edit = client.post("/api/edits", json={"polygon": POLY, "prompt": "turn this block into a plaza"}, headers=owner_h).json()
    assert edit["place_name"] == "Center City, Philadelphia"
    assert edit["saved"] is False

    # The other user refines the owner's edit -> shows up as a refinement in THEIR contributions.
    r = client.post(f"/api/edits/{edit['id']}/refine", json={"prompt": "add a fountain"}, headers=other_h)
    assert r.status_code == 200, r.text

    mine = client.get("/api/me/contributions", headers=owner_h).json()
    assert [c["kind"] for c in mine if c["edit_id"] == edit["id"]] == ["edit"]
    assert mine[0]["place_name"] == "Center City, Philadelphia"
    assert -75.17 < mine[0]["centroid"][0] < -75.16

    theirs = client.get("/api/me/contributions", headers=other_h).json()
    ref = [c for c in theirs if c["edit_id"] == edit["id"]]
    assert len(ref) == 1 and ref[0]["kind"] == "refinement"
    assert ref[0]["prompt"] == "add a fountain"
    assert ref[0]["edit_creator"]["id"] == owner["id"]
    assert ref[0]["edit_original_prompt"] == "turn this block into a plaza"

    # Bookmarks are private and per-user.
    r = client.put(f"/api/edits/{edit['id']}/bookmark", json={"saved": True}, headers=other_h)
    assert r.json() == {"saved": True}
    assert [e["id"] for e in client.get("/api/me/saved", headers=other_h).json()] == [edit["id"]]
    assert client.get("/api/me/saved", headers=owner_h).json() == []
    assert client.get(f"/api/edits/{edit['id']}", headers=other_h).json()["saved"] is True
    assert client.get(f"/api/edits/{edit['id']}", headers=owner_h).json()["saved"] is False
    r = client.put(f"/api/edits/{edit['id']}/bookmark", json={"saved": False}, headers=other_h)
    assert r.json() == {"saved": False}
    assert client.get("/api/me/saved", headers=other_h).json() == []
    assert client.put(f"/api/edits/{edit['id']}/bookmark", json={"saved": True}).status_code == 401

    # Only the owner can delete; deletion removes the edit, its files and dependants.
    from app.imaging import store as img_store

    overlay_rel = edit["current_version"]["overlay_url"].removeprefix("/images/")
    assert overlay_rel.startswith(f"{edit['id']}-")  # per-edit token in the folder name
    assert img_store.abs_path(overlay_rel).exists()
    assert client.delete(f"/api/edits/{edit['id']}", headers=other_h).status_code == 403
    assert client.delete(f"/api/edits/{edit['id']}").status_code == 401
    assert client.delete(f"/api/edits/{edit['id']}", headers=owner_h).status_code == 204
    assert client.get(f"/api/edits/{edit['id']}").status_code == 404
    assert not any(e["id"] == edit["id"] for e in client.get("/api/edits").json())
    assert not img_store.abs_path(overlay_rel).exists()

    # A new edit after a delete never reuses the deleted edit's id or image URL (ids are
    # autoincrement and folders carry a random token), so cached images can't bleed over.
    again = client.post("/api/edits", json={"polygon": POLY, "prompt": "turn this block into a plaza"}, headers=owner_h).json()
    assert again["id"] != edit["id"]
    assert again["current_version"]["overlay_url"] != edit["current_version"]["overlay_url"]
    assert again["original_url"] != edit["original_url"]
    assert all(c["edit_id"] != edit["id"] for c in client.get("/api/me/contributions", headers=other_h).json())
    assert other["id"] != owner["id"]


def test_highlight_edit_flow(client):
    headers, _ = _signup(client)
    highlight = {
        "strokes": [
            {"coordinates": [[-75.1662, 39.9530], [-75.1650, 39.9529], [-75.1642, 39.9528]], "width_m": 12},
            {"coordinates": [[-75.1655, 39.9522]], "width_m": 8},
        ]
    }
    r = client.post("/api/edits", json={"highlight": highlight, "prompt": "add bus lanes"}, headers=headers)
    assert r.status_code == 201, r.text
    edit = r.json()
    assert edit["kind"] == "highlight" and edit["status"] == "done"
    assert len(edit["highlight"]["strokes"]) == 2
    assert edit["highlight"]["strokes"][0]["width_m"] == 12
    # The stored polygon is the strokes' bounding box (a closed 5-point ring) and bounds contain it.
    ring = edit["polygon"]["coordinates"][0]
    assert len(ring) == 5 and ring[0] == ring[-1]
    w, s, e, n = edit["bounds"]
    assert w < -75.1662 and e > -75.1642 and s < 39.9522 and n > 39.9530

    # The saved mask is opaque on a stroke and transparent far from any stroke.
    from PIL import Image

    from app.imaging import store as img_store

    mask = Image.open(img_store.abs_path(img_store.asset_dir_of(edit["original_url"].removeprefix("/images/")) + "/mask.png"))
    assert mask.getbbox() is not None
    hist = mask.histogram()
    opaque, transparent = hist[255], hist[0]
    assert opaque > 0 and transparent > opaque  # a thin stroke covers a minority of the bbox crop

    # Refinement reuses the stroke mask.
    r = client.post(f"/api/edits/{edit['id']}/refine", json={"prompt": "paint them red"}, headers=headers)
    assert r.status_code == 200 and r.json()["version_count"] == 2

    r = client.post("/api/edits", json={"prompt": "no region"}, headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "region_missing"
    r = client.post("/api/edits", json={"highlight": {"strokes": []}, "prompt": "add bus lanes"}, headers=headers)
    assert r.status_code == 422


def test_smart_edit_flow(client):
    headers, _ = _signup(client)
    smart = {
        "polygons": [[[-75.1660, 39.9530], [-75.1655, 39.9530], [-75.1655, 39.9526], [-75.1660, 39.9526], [-75.1660, 39.9530]]],
        "strokes": [{"coordinates": [[-75.1662, 39.9522], [-75.1650, 39.9521]], "width_m": 9}],
    }
    r = client.post("/api/edits", json={"smart": smart, "prompt": "add a green roof and bus lanes"}, headers=headers)
    assert r.status_code == 201, r.text
    edit = r.json()
    assert edit["kind"] == "smart" and edit["status"] == "done"
    assert len(edit["smart"]["polygons"]) == 1 and len(edit["smart"]["strokes"]) == 1
    w, s, e, n = edit["bounds"]
    assert w < -75.1662 and e > -75.1650 and s < 39.9521 and n > 39.9530

    from PIL import Image

    from app.imaging import store as img_store

    mask = Image.open(img_store.abs_path(img_store.asset_dir_of(edit["original_url"].removeprefix("/images/")) + "/mask.png"))
    hist = mask.histogram()
    assert hist[255] > 0 and hist[0] > hist[255]

    r = client.post("/api/edits", json={"smart": {"polygons": [], "strokes": []}, "prompt": "nothing"}, headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "region_missing"


def test_mask_edit_flow(client):
    import base64
    import io

    from PIL import Image, ImageDraw

    from app.geo.mercator import lnglat_to_px

    headers, _ = _signup(client)
    zoom = 18
    x, y = lnglat_to_px(-75.1652, 39.9526, zoom)
    x0, y0 = int(x) - 60, int(y) - 40
    m = Image.new("L", (120, 80), 0)
    ImageDraw.Draw(m).ellipse([10, 10, 109, 69], fill=255)
    buf = io.BytesIO()
    m.save(buf, format="PNG")
    png = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    body = {"mask": {"zoom": zoom, "x0": x0, "y0": y0, "width": 120, "height": 80, "png": png}, "prompt": "turn this lot into a park"}
    r = client.post("/api/edits", json=body, headers=headers)
    assert r.status_code == 201, r.text
    edit = r.json()
    assert edit["kind"] == "mask" and edit["status"] == "done"
    polys = edit["mask"]["polygons"]
    assert len(polys) == 1 and len(polys[0]) == 1
    ring = polys[0][0]
    w, s, e, n = edit["bounds"]
    assert all(w <= lng <= e and s <= lat <= n for lng, lat in ring)
    assert len(ring) > 8  # an ellipse outline keeps many vertices

    from app.imaging import store as img_store

    saved = Image.open(img_store.abs_path(img_store.asset_dir_of(edit["original_url"].removeprefix("/images/")) + "/mask.png"))
    hist = saved.histogram()
    assert hist[255] > 0 and hist[0] > 0
    # The ellipse covers ~pi/4 of its 120x80 box; the crop adds a 15% margin and aspect snapping,
    # so the opaque share of the crop should be well under half but far from zero.
    share = hist[255] / (saved.width * saved.height)
    assert 0.15 < share < 0.6

    bad = dict(body)
    bad["mask"] = {**body["mask"], "width": 100}
    assert client.post("/api/edits", json=bad, headers=headers).status_code == 422
    empty = Image.new("L", (120, 80), 0)
    buf = io.BytesIO()
    empty.save(buf, format="PNG")
    bad["mask"] = {**body["mask"], "png": base64.b64encode(buf.getvalue()).decode()}
    r = client.post("/api/edits", json=bad, headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "region_missing"


def test_create_requires_auth_and_validates(client):
    r = client.post("/api/edits", json={"polygon": POLY, "prompt": "hello"})
    assert r.status_code == 401
    headers, _ = _signup(client)
    r = client.post("/api/edits", json={"polygon": POLY, "prompt": "x"}, headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "prompt_too_short"
    huge = {"type": "Polygon", "coordinates": [[[-75.3, 39.9], [-75.0, 39.9], [-75.0, 40.1], [-75.3, 40.1]]]}
    r = client.post("/api/edits", json={"polygon": huge, "prompt": "add a park"}, headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "polygon_too_large"


def test_out_of_scope_removes_edit(client):
    headers, _ = _signup(client)
    before = {x["id"] for x in client.get("/api/edits").json()}
    r = client.post("/api/edits", json={"polygon": POLY, "prompt": "this is out of scope"}, headers=headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "out_of_scope"
    after = {x["id"] for x in client.get("/api/edits").json()}
    assert before == after
