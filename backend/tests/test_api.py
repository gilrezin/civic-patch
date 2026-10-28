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

    assert img_store.abs_path(f"{edit['id']}/v1_overlay.png").exists()
    assert client.delete(f"/api/edits/{edit['id']}", headers=other_h).status_code == 403
    assert client.delete(f"/api/edits/{edit['id']}").status_code == 401
    assert client.delete(f"/api/edits/{edit['id']}", headers=owner_h).status_code == 204
    assert client.get(f"/api/edits/{edit['id']}").status_code == 404
    assert not any(e["id"] == edit["id"] for e in client.get("/api/edits").json())
    assert not img_store.abs_path(f"{edit['id']}/v1_overlay.png").exists()
    assert all(c["edit_id"] != edit["id"] for c in client.get("/api/me/contributions", headers=other_h).json())
    assert other["id"] != owner["id"]


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
