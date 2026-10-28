"""Test configuration: isolated data dir, fake editor, and stubbed tile fetching."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="civic_patch_test_"))
os.environ["DATA_DIR"] = str(_tmp)
os.environ["EDITOR"] = "fake"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256-xxxx"
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from PIL import Image  # noqa: E402


def _fake_tile_bytes(z: int, x: int, y: int) -> bytes:
    import io

    img = Image.new("RGB", (256, 256), ((x * 37) % 256, (y * 59) % 256, (z * 13) % 256))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def stub_tiles(monkeypatch):
    from app.geo import tiles

    async def fake_fetch_tiles(z, tx0, ty0, tx1, ty1):
        return {(tx, ty): _fake_tile_bytes(z, tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)}

    monkeypatch.setattr(tiles, "fetch_tiles", fake_fetch_tiles)
    from app.geo import crop

    monkeypatch.setattr(crop, "fetch_tiles", fake_fetch_tiles)
    yield


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.ai.fake import FakeEditor
    from app.main import app
    from app.services import edits as svc

    monkeypatch.setattr(svc, "get_editor", lambda: FakeEditor(delay_s=0.0))
    with TestClient(app) as c:
        yield c
