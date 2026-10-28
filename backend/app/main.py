"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import asyncio

from .config import get_settings
from .db import Base, SessionLocal, engine, run_migrations
from .geo.tiles import ATTRIBUTION, close_client
from .routers import auth, comments, edits, me, votes
from .services.edits import backfill_place_names, cleanup_stale_pending

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("civic_patch")


class ImmutableStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    run_migrations()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        n = cleanup_stale_pending(db)
        if n:
            log.info("marked %d stale pending rows as failed", n)
    log.info("editor=%s model=%s region_hint=%s", settings.editor, settings.gemini_image_model, settings.region_hint)

    async def _backfill():
        try:
            n = await backfill_place_names()
            if n:
                log.info("backfilled place names for %d edits", n)
        except Exception:  # pragma: no cover
            log.exception("place name backfill failed")

    backfill_task = asyncio.create_task(_backfill())
    yield
    backfill_task.cancel()
    await close_client()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="civic-patch API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return JSONResponse(
            status_code=422,
            content={"detail": {"code": "invalid_request", "message": f"{loc}: {first.get('msg', 'invalid')}"}},
        )

    for r in (auth.router, edits.router, votes.router, comments.router, me.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"ok": True, "editor": settings.editor, "attribution": ATTRIBUTION}

    settings.images_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", ImmutableStaticFiles(directory=str(settings.images_dir)), name="images")
    return app


app = create_app()
