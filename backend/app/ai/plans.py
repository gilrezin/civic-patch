"""Municipality comprehensive plans -> generated prompt-hint JSON (retrieval-augmented).

Layout:
  <PLANS_DIR>/<Municipality-Slug>/*.pdf|*.txt|*.md   source documents (e.g. references/Philadelphia-PA/)
  <DATA_DIR>/plan_index/<slug>.json                 cached chunks + embeddings
  <DATA_DIR>/plan_hints/<slug>.json                 generated hints, same shape as prompt_hints.json

Generation runs once per municipality, in the background, the first time a user opens the
prompt box inside it. Until the file exists (or if no plan folder exists) the default
prompt_hints.json is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..config import get_settings
from .hints import parse_hints

log = logging.getLogger(__name__)

CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150
EMBED_BATCH = 40
EMBED_DIM = 768
TOP_K_PER_TOPIC = 4
MAX_CONTEXT_CHARS = 40_000
RETRY_FAILED_AFTER_S = 600.0

# Planning themes used as retrieval queries so the hints cover the whole document, not just
# whatever happens to be on the first pages.
TOPICS = [
    "public transit bus and rail corridors, stations and transit-oriented development",
    "bicycle lanes, trails and pedestrian safety, complete streets",
    "street design, traffic calming, lane configuration and on-street parking",
    "housing density, infill, rowhouses, affordable housing and neighbourhood scale",
    "parks, open space, street trees, greening and stormwater management",
    "commercial corridors, mixed-use development, retail and main streets",
    "industrial land, logistics, employment centres and waterfront redevelopment",
    "historic preservation, neighbourhood character and design guidelines",
    "vacant land reuse, community gardens and lot stabilisation",
    "building height, scale, setbacks and zoning",
    "climate resilience, flooding, sustainability and energy",
    "schools, libraries, recreation centres and other public facilities",
    "waterfront and river access, trails and public space",
    "plazas, squares, placemaking and public art",
]

GENERATION_PROMPT = """You are helping an urban-planning visualization tool. Residents select part of a satellite image of {city} and type a short instruction such as "add bus lanes" or "turn this lot into housing". Before the image is edited, the tool appends design guidance matched by keywords in the resident's instruction.

Using ONLY the excerpts below from {city}'s comprehensive plan ({sources}), write that guidance as a JSON object:
- Keys are lowercase keywords or short phrases a resident is likely to type (one to three words), for example "bus", "bike lane", "housing", "rowhouse", "park", "tree", "parking", "plaza", "waterfront", "vacant lot", "commercial", "school". Include between 25 and 45 keys, covering transit, streets, housing, open space, commercial areas, industry, preservation and the public realm. Always include the keys "bus", "bike", "tree", "park", "housing", "parking", "plaza" and "crosswalk".
- Each value is one or two sentences telling an image model WHAT TO DRAW from directly overhead so the result matches the plan: physical form, materials, colours, dimensions, placement and alignment with neighbouring buildings and streets (for example "paint centre-running bus lanes red with white 'BUS ONLY' markings and keep one general lane each way", "three-storey brick rowhouses built to the sidewalk line with rear yards"). Start with the visual instruction, then add the plan's reason, goal or named policy in a short clause where the excerpts support it. Avoid abstract policy language ("promote", "encourage", "support") on its own. Do not invent facts that are not in the excerpts.
- Add "_comment": a one-sentence note that these hints were generated from the named plan, and "_source": the document names.
Return only the JSON object.

EXCERPTS:
{context}
"""


@dataclass
class PlanDocs:
    slug: str
    folder: Path
    files: list[Path]


# ---------------------------------------------------------------------------
# Discovery and status
# ---------------------------------------------------------------------------


def find_plan_docs(slug: str | None) -> PlanDocs | None:
    if not slug:
        return None
    root = get_settings().resolved_plans_dir
    if not root.is_dir():
        return None
    want = slug.lower()
    for folder in root.iterdir():
        if folder.is_dir() and folder.name.lower() == want:
            files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".pdf", ".txt", ".md") and p.is_file())
            return PlanDocs(slug=folder.name, folder=folder, files=files) if files else None
    return None


def plan_hints_path(slug: str) -> Path:
    return get_settings().plan_hints_dir / f"{slug}.json"


def hints_path_for(slug: str | None) -> Path:
    """The hints file to use for a municipality: its generated plan hints if present, else the default."""
    if slug:
        p = plan_hints_path(slug)
        if p.is_file():
            return p
    return get_settings().resolved_prompt_hints_file


_tasks: dict[str, asyncio.Task] = {}
_failed_at: dict[str, float] = {}
_errors: dict[str, str] = {}


def plan_status(slug: str | None) -> str:
    """'ready' (generated file exists), 'generating', 'available' (plan found, not yet generated),
    'failed' (last attempt failed recently) or 'none' (no plan for this municipality)."""
    if not slug:
        return "none"
    if plan_hints_path(slug).is_file():
        return "ready"
    task = _tasks.get(slug)
    if task and not task.done():
        return "generating"
    docs = find_plan_docs(slug)
    if docs is None:
        return "none"
    if time.monotonic() - _failed_at.get(docs.slug, -math.inf) < RETRY_FAILED_AFTER_S:
        return "failed"
    return "available"


def last_error(slug: str | None) -> str | None:
    return _errors.get(slug or "")


def ensure_plan_hints(slug: str | None) -> asyncio.Task | None:
    """Start generation for the municipality if a plan exists and no hints file does. Returns
    the running task (new or existing) or None when nothing needs doing."""
    docs = find_plan_docs(slug)
    if docs is None or plan_hints_path(docs.slug).is_file():
        return None
    task = _tasks.get(docs.slug)
    if task and not task.done():
        return task
    if time.monotonic() - _failed_at.get(docs.slug, -math.inf) < RETRY_FAILED_AFTER_S:
        return None
    task = asyncio.get_running_loop().create_task(_generate(docs))
    _tasks[docs.slug] = task
    return task


async def wait_for_plan_hints(slug: str | None, timeout_s: float) -> None:
    """If generation is in flight for this municipality, wait for it (bounded)."""
    task = _tasks.get(slug or "")
    if task and not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout_s)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Text extraction and chunking
# ---------------------------------------------------------------------------


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        import logging as _logging

        from pypdf import PdfReader

        _logging.getLogger("pypdf").setLevel(_logging.ERROR)
        reader = PdfReader(str(path))
        pages = []
        for p in reader.pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n".join(pages)
    return path.read_text(encoding="utf-8", errors="ignore")


_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = text.replace("­", "").replace("- \n", "").replace("-\n", "")
    text = _WS_RE.sub(" ", text)
    return _NL_RE.sub("\n\n", text).strip()


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            # Prefer to break at a paragraph or sentence boundary.
            cut = max(text.rfind("\n\n", start + size // 2, end), text.rfind(". ", start + size // 2, end))
            if cut > start:
                end = cut + 1
        chunk = text[start:end].strip()
        if len(chunk) > 80:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (na * nb)


_WORD_RE = re.compile(r"[a-z]{3,}")


def lexical_scores(query: str, chunks: list[str]) -> list[float]:
    """Fallback ranking when embeddings are unavailable: weighted keyword overlap."""
    q = set(_WORD_RE.findall(query.lower()))
    out = []
    for c in chunks:
        words = _WORD_RE.findall(c.lower())
        if not words:
            out.append(0.0)
            continue
        hits = sum(1 for w in words if w in q)
        out.append(hits / math.sqrt(len(words)))
    return out


def select_context(
    chunks: list[str],
    chunk_vecs: list[list[float]] | None,
    topic_vecs: list[list[float]] | None,
    *,
    top_k: int = TOP_K_PER_TOPIC,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, int]:
    """Pick the best chunks per topic (embedding similarity, else lexical) and format them."""
    chosen: dict[int, set[str]] = {}
    for t_idx, topic in enumerate(TOPICS):
        if chunk_vecs and topic_vecs:
            scores = [_cosine(topic_vecs[t_idx], v) for v in chunk_vecs]
        else:
            scores = lexical_scores(topic, chunks)
        order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        for i in order[:top_k]:
            if scores[i] <= 0:
                continue
            chosen.setdefault(i, set()).add(topic.split(",")[0])
    parts: list[str] = []
    total = 0
    for i in sorted(chosen):
        block = f"[{i + 1}] ({'; '.join(sorted(chosen[i]))})\n{chunks[i]}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts), len(parts)


# ---------------------------------------------------------------------------
# Gemini calls (kept small so tests can stub them)
# ---------------------------------------------------------------------------


def _client():
    from google import genai
    from google.genai import types

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=120_000)), types


async def embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
    client, types = _client()
    model = get_settings().gemini_embed_model
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        resp = await client.aio.models.embed_content(
            model=model,
            contents=batch,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBED_DIM),
        )
        out.extend([list(e.values) for e in resp.embeddings])
    return out


async def generate_json(prompt: str) -> dict:
    client, types = _client()
    resp = await client.aio.models.generate_content(
        model=get_settings().gemini_text_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3),
    )
    text = (resp.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def _load_or_build_index(docs: PlanDocs) -> tuple[list[str], list[list[float]] | None]:
    settings = get_settings()
    settings.plan_index_dir.mkdir(parents=True, exist_ok=True)
    idx_path = settings.plan_index_dir / f"{docs.slug}.json"
    stamp = ",".join(f"{p.name}:{int(p.stat().st_mtime)}" for p in docs.files)
    if idx_path.is_file():
        try:
            cached = json.loads(idx_path.read_text(encoding="utf-8"))
            if cached.get("stamp") == stamp and cached.get("chunks"):
                return cached["chunks"], cached.get("vectors")
        except Exception:
            pass

    texts = await asyncio.gather(*(asyncio.to_thread(extract_text, p) for p in docs.files))
    chunks: list[str] = []
    for p, t in zip(docs.files, texts):
        for c in chunk_text(t):
            chunks.append(f"({p.name}) {c}")
    if not chunks:
        raise RuntimeError("no readable text in plan documents")

    vectors: list[list[float]] | None
    try:
        vectors = await embed_texts(chunks, "RETRIEVAL_DOCUMENT")
    except Exception as exc:
        log.warning("plan embedding failed for %s, using lexical retrieval: %s", docs.slug, exc)
        vectors = None
    idx_path.write_text(json.dumps({"stamp": stamp, "chunks": chunks, "vectors": vectors}), encoding="utf-8")
    return chunks, vectors


def _city_name(slug: str) -> str:
    parts = slug.rsplit("-", 1)
    city = parts[0].replace("-", " ")
    return f"{city}, {parts[1]}" if len(parts) == 2 and len(parts[1]) <= 3 else city


async def _generate(docs: PlanDocs) -> Path:
    settings = get_settings()
    t0 = time.perf_counter()
    try:
        chunks, vectors = await _load_or_build_index(docs)
        topic_vecs = None
        if vectors:
            try:
                topic_vecs = await embed_texts(TOPICS, "RETRIEVAL_QUERY")
            except Exception as exc:
                log.warning("topic embedding failed for %s, using lexical retrieval: %s", docs.slug, exc)
        context, used = select_context(chunks, vectors if topic_vecs else None, topic_vecs)
        prompt = GENERATION_PROMPT.format(
            city=_city_name(docs.slug), sources=", ".join(p.name for p in docs.files), context=context
        )
        data = await generate_json(prompt)
        rules = parse_hints(data)
        if len(rules) < 5:
            raise RuntimeError(f"model returned only {len(rules)} usable hints")
        data.setdefault("_comment", f"Generated from {docs.slug} comprehensive plan.")
        data["_source"] = ", ".join(p.name for p in docs.files)
        data["_generated"] = date.today().isoformat()
        data["_chunks_used"] = used
        settings.plan_hints_dir.mkdir(parents=True, exist_ok=True)
        out = plan_hints_path(docs.slug)
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        _errors.pop(docs.slug, None)
        log.info("generated %d plan hints for %s in %.1fs (%d chunks, %d used)", len(rules), docs.slug, time.perf_counter() - t0, len(chunks), used)
        return out
    except Exception as exc:
        _failed_at[docs.slug] = time.monotonic()
        _errors[docs.slug] = str(exc)[:300]
        log.exception("plan hint generation failed for %s", docs.slug)
        raise
