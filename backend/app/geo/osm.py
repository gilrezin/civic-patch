"""OpenStreetMap features for smart select, via the Overpass API.

The map is divided into fixed 0.01 degree cells. Each cell is fetched once (with mirror
failover) and cached in memory. Ways are turned into:
  * areas: buildings, parking lots and green spaces as closed rings
  * roads: highway ways split into segments at intersections, with an estimated width
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

CELL_DEG = 0.01
CACHE_TTL_S = 3600.0
CACHE_MAX_CELLS = 400
USER_AGENT = "civic-patch/0.1 (smart select; community planning prototype)"

DRIVABLE = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "service", "living_street", "motorway_link", "trunk_link", "primary_link", "secondary_link",
    "tertiary_link", "pedestrian", "busway", "road",
}
PATHS = {"footway", "cycleway", "path", "steps", "bridleway", "track"}

# Estimated total carriageway width in metres by highway class (used when no width/lanes tag).
CLASS_WIDTH_M = {
    "motorway": 15.0, "motorway_link": 7.0, "trunk": 13.0, "trunk_link": 7.0,
    "primary": 12.0, "primary_link": 6.5, "secondary": 10.0, "secondary_link": 6.0,
    "tertiary": 9.0, "tertiary_link": 6.0, "unclassified": 7.0, "residential": 7.0,
    "living_street": 5.5, "service": 4.0, "pedestrian": 6.0, "busway": 7.0, "road": 7.0,
    "footway": 2.5, "cycleway": 2.5, "path": 2.0, "steps": 2.5, "bridleway": 2.5, "track": 3.0,
}

_DRIVABLE_RE = "^(" + "|".join(sorted(DRIVABLE)) + ")$"

# Only drivable roads are requested: paths are neither selectable nor block boundaries, and
# dropping them removes a large share of the payload in dense city centres. `qt` output is
# the server's cheapest ordering.
QUERY = (
    """[out:json][timeout:20];
(
  way["building"]({s},{w},{n},{e});
  relation["building"]["type"="multipolygon"]({s},{w},{n},{e});
  way["amenity"="parking"]({s},{w},{n},{e});
  way["leisure"~"^(park|pitch|playground|garden|dog_park)$"]({s},{w},{n},{e});
  way["landuse"~"^(grass|recreation_ground|cemetery|village_green)$"]({s},{w},{n},{e});
  way["highway"~\""""
    + _DRIVABLE_RE
    + """\"]({s},{w},{n},{e});
);
out geom qt;"""
)


class OverpassError(RuntimeError):
    pass


@dataclass
class Area:
    key: str
    kind: str  # building | parking | green
    label: str
    ring: list[tuple[float, float]]


@dataclass
class Road:
    key: str
    kind: str  # road | path
    label: str
    coords: list[tuple[float, float]]
    width_m: float


@dataclass
class CellFeatures:
    areas: list[Area] = field(default_factory=list)
    roads: list[Road] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "areas": [{"key": a.key, "kind": a.kind, "label": a.label, "ring": [list(p) for p in a.ring]} for a in self.areas],
            "roads": [
                {"key": r.key, "kind": r.kind, "label": r.label, "coords": [list(p) for p in r.coords], "width_m": r.width_m}
                for r in self.roads
            ],
        }


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------


def cell_of(lng: float, lat: float) -> tuple[int, int]:
    return int(math.floor(lng / CELL_DEG)), int(math.floor(lat / CELL_DEG))


def cell_bbox(ix: int, iy: int) -> tuple[float, float, float, float]:
    """(W, S, E, N) of a cell."""
    return (ix * CELL_DEG, iy * CELL_DEG, (ix + 1) * CELL_DEG, (iy + 1) * CELL_DEG)


# ---------------------------------------------------------------------------
# Width estimation
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(m|meters?|metres?|ft|feet|')?\s*$", re.IGNORECASE)


def _parse_width(value: str | None) -> float | None:
    if not value:
        return None
    m = _NUM_RE.match(value)
    if not m:
        return None
    n = float(m.group(1))
    unit = (m.group(2) or "m").lower()
    if unit in ("ft", "feet", "'"):
        n *= 0.3048
    return n if 0.5 <= n <= 80 else None


def estimate_width_m(tags: dict) -> float:
    w = _parse_width(tags.get("width")) or _parse_width(tags.get("est_width"))
    if w:
        return w
    lanes = tags.get("lanes")
    try:
        n = int(lanes) if lanes else 0
    except ValueError:
        n = 0
    if n > 0:
        return n * 3.3 + 1.0
    return CLASS_WIDTH_M.get(tags.get("highway", ""), 7.0)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def _ring(geom: list[dict]) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in geom]


def _is_closed(ring: list[tuple[float, float]]) -> bool:
    return len(ring) >= 4 and ring[0] == ring[-1]


def _area_kind(tags: dict) -> tuple[str, str] | None:
    if "building" in tags and tags.get("building") != "no":
        return "building", tags.get("name") or _building_label(tags)
    if tags.get("amenity") == "parking":
        return "parking", tags.get("name") or "Parking lot"
    if tags.get("leisure") in ("park", "pitch", "playground", "garden", "dog_park"):
        return "green", tags.get("name") or tags["leisure"].replace("_", " ").capitalize()
    if tags.get("landuse") in ("grass", "recreation_ground", "cemetery", "village_green"):
        return "green", tags.get("name") or tags["landuse"].replace("_", " ").capitalize()
    return None


def _building_label(tags: dict) -> str:
    b = tags.get("building", "yes")
    if b in ("yes", "true"):
        return "Building"
    return b.replace("_", " ").capitalize()


def _road_label(tags: dict) -> str:
    return tags.get("name") or tags.get("ref") or tags.get("highway", "road").replace("_", " ").capitalize()


def process_elements(elements: list[dict]) -> CellFeatures:
    out = CellFeatures()
    highways: list[dict] = []

    for el in elements:
        tags = el.get("tags") or {}
        if el.get("type") == "way":
            if "highway" in tags:
                highways.append(el)
                continue
            ak = _area_kind(tags)
            if ak and el.get("geometry"):
                ring = _ring(el["geometry"])
                if _is_closed(ring):
                    out.areas.append(Area(key=f"w{el['id']}", kind=ak[0], label=ak[1], ring=ring))
        elif el.get("type") == "relation":
            ak = _area_kind(tags)
            if not ak:
                continue
            for i, mem in enumerate(el.get("members") or []):
                if mem.get("role") == "outer" and mem.get("geometry"):
                    ring = _ring(mem["geometry"])
                    if _is_closed(ring):
                        out.areas.append(Area(key=f"r{el['id']}-{i}", kind=ak[0], label=ak[1], ring=ring))

    out.roads = _split_roads(highways)
    return out


def _split_roads(ways: list[dict]) -> list[Road]:
    drivable = [w for w in ways if (w.get("tags") or {}).get("highway") in DRIVABLE and w.get("nodes")]

    # Which drivable ways touch each node, and whether as an endpoint.
    node_ways: dict[int, set[int]] = defaultdict(set)
    node_end: dict[int, set[int]] = defaultdict(set)
    by_id = {w["id"]: w for w in drivable}
    for w in drivable:
        nodes = w["nodes"]
        for n in nodes:
            node_ways[n].add(w["id"])
        node_end[nodes[0]].add(w["id"])
        node_end[nodes[-1]].add(w["id"])

    def same_street(a: dict, b: dict) -> bool:
        ta, tb = a.get("tags") or {}, b.get("tags") or {}
        if ta.get("name") and ta.get("name") == tb.get("name"):
            return True
        return not ta.get("name") and not tb.get("name") and ta.get("highway") == tb.get("highway")

    intersections: set[int] = set()
    continuations: set[int] = set()
    for n, ws in node_ways.items():
        if len(ws) < 2:
            continue
        if len(ws) == 2 and node_end.get(n) == ws:
            a, b = (by_id[i] for i in ws)
            if same_street(a, b):
                continuations.add(n)
                continue
        intersections.add(n)

    # Split each way at interior intersection nodes.
    segments: list[dict] = []  # {way, nodes[], coords[]}
    for w in drivable:
        nodes, geom = w["nodes"], w.get("geometry") or []
        if len(geom) != len(nodes):
            continue
        start = 0
        for i in range(1, len(nodes)):
            if nodes[i] in intersections and i < len(nodes) - 1 or i == len(nodes) - 1:
                segments.append({"way": w, "nodes": nodes[start : i + 1], "coords": _ring(geom[start : i + 1])})
                start = i

    # Merge segments that meet end-to-end at a continuation node (same street, no cross road).
    merged = _merge_continuations(segments, continuations)

    roads: list[Road] = []
    counter: dict[int, int] = defaultdict(int)
    for seg in merged:
        w = seg["way"]
        tags = w.get("tags") or {}
        counter[w["id"]] += 1
        roads.append(
            Road(
                key=f"h{w['id']}-{counter[w['id']]}",
                kind="road",
                label=_road_label(tags),
                coords=seg["coords"],
                width_m=round(estimate_width_m(tags), 2),
            )
        )
    return roads


def _merge_continuations(segments: list[dict], continuations: set[int]) -> list[dict]:
    if not continuations:
        return segments
    by_end: dict[int, list[int]] = defaultdict(list)
    for idx, s in enumerate(segments):
        for n in (s["nodes"][0], s["nodes"][-1]):
            if n in continuations:
                by_end[n].append(idx)
    parent = list(range(len(segments)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for n, idxs in by_end.items():
        if len(idxs) == 2:
            a, b = idxs
            parent[find(a)] = find(b)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(segments)):
        groups[find(i)].append(i)

    out: list[dict] = []
    for idxs in groups.values():
        if len(idxs) == 1:
            out.append(segments[idxs[0]])
            continue
        out.append(_chain(segments, idxs))
    return out


def _chain(segments: list[dict], idxs: list[int]) -> dict:
    """Order and concatenate segments that form one chain; fall back to the longest if ambiguous."""
    pool = {i: segments[i] for i in idxs}
    first_idx = idxs[0]
    chain = pool.pop(first_idx)
    nodes, coords = list(chain["nodes"]), list(chain["coords"])
    changed = True
    while pool and changed:
        changed = False
        for i, s in list(pool.items()):
            if s["nodes"][0] == nodes[-1]:
                nodes += s["nodes"][1:]
                coords += s["coords"][1:]
            elif s["nodes"][-1] == nodes[-1]:
                nodes += list(reversed(s["nodes"]))[1:]
                coords += list(reversed(s["coords"]))[1:]
            elif s["nodes"][-1] == nodes[0]:
                nodes = s["nodes"][:-1] + nodes
                coords = s["coords"][:-1] + coords
            elif s["nodes"][0] == nodes[0]:
                nodes = list(reversed(s["nodes"]))[:-1] + nodes
                coords = list(reversed(s["coords"]))[:-1] + coords
            else:
                continue
            pool.pop(i)
            changed = True
    return {"way": chain["way"], "nodes": nodes, "coords": coords}


# ---------------------------------------------------------------------------
# Fetching with mirror failover and cache
# ---------------------------------------------------------------------------

_cache: OrderedDict[tuple[int, int], tuple[float, dict]] = OrderedDict()
_locks: dict[tuple[int, int], asyncio.Lock] = {}
_mirror_fail_until: dict[str, float] = {}
_preferred_mirror: str | None = None
_client: httpx.AsyncClient | None = None

# Overpass mirrors rate-limit bursts (8 parallel cell queries produced 503s in testing), so all
# queries go through one small gate and a 503/429 is retried on the same mirror after a pause
# instead of benching the mirror.
MAX_INFLIGHT = 2
RETRY_DELAYS_S = (1.5, 3.0, 5.0)
DB_TTL_S = 24 * 3600.0
_gate: asyncio.Semaphore | None = None
_prefetch_tasks: set[asyncio.Task] = set()


def _gate_sem() -> asyncio.Semaphore:
    global _gate
    if _gate is None:
        _gate = asyncio.Semaphore(MAX_INFLIGHT)
    return _gate


def mirrors() -> list[str]:
    urls = [u.strip() for u in get_settings().overpass_urls.split(",") if u.strip()]
    if _preferred_mirror in urls:
        urls.remove(_preferred_mirror)
        urls.insert(0, _preferred_mirror)
    return urls


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=get_settings().overpass_timeout_s, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


class _Busy(Exception):
    """Mirror answered 429/503/504: back off and retry on the same mirror."""


async def _post(url: str, query: str) -> list[dict]:
    resp = await _get_client().post(url, data={"data": query})
    if resp.status_code in (429, 503, 504):
        raise _Busy(f"HTTP {resp.status_code}")
    if resp.status_code >= 500:
        raise OverpassError(f"HTTP {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()
    if "elements" not in data:
        raise OverpassError("malformed response")
    return data["elements"]


async def _query_overpass(query: str) -> list[dict]:
    global _preferred_mirror
    errors: list[str] = []
    async with _gate_sem():
        for url in mirrors():
            if _mirror_fail_until.get(url, 0) > time.monotonic():
                continue
            t = time.perf_counter()
            for attempt, delay in enumerate((0.0,) + RETRY_DELAYS_S):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    elements = await _post(url, query)
                    _preferred_mirror = url
                    log.info(
                        "overpass %s ok in %.2fs (%d elements, attempt %d)", url, time.perf_counter() - t, len(elements), attempt + 1
                    )
                    return elements
                except _Busy as exc:
                    errors.append(f"{url}: {exc}")
                    log.info("overpass %s busy (%s), retrying", url, exc)
                    continue
                except Exception as exc:  # connect error, timeout, 5xx, bad body: try the next mirror
                    errors.append(f"{url}: {exc}")
                    _mirror_fail_until[url] = time.monotonic() + 120.0
                    log.warning("overpass mirror failed: %s: %s", url, exc)
                    break
    raise OverpassError("All Overpass mirrors failed: " + "; ".join(errors))


# ---- persistent cell cache (SQLite) -----------------------------------------


def _db_load(ix: int, iy: int) -> dict | None:
    from ..db import SessionLocal
    from ..models import OsmCellCache

    with SessionLocal() as db:
        row = db.get(OsmCellCache, (ix, iy))
        if row is None or time.time() - row.fetched_at > DB_TTL_S:
            return None
        try:
            return json.loads(row.payload)
        except json.JSONDecodeError:
            return None


def _db_store(ix: int, iy: int, data: dict) -> None:
    from ..db import SessionLocal
    from ..models import OsmCellCache

    with SessionLocal() as db:
        row = db.get(OsmCellCache, (ix, iy))
        payload = json.dumps(data, separators=(",", ":"))
        if row is None:
            db.add(OsmCellCache(ix=ix, iy=iy, fetched_at=time.time(), payload=payload))
        else:
            row.fetched_at = time.time()
            row.payload = payload
        db.commit()


def _remember(key: tuple[int, int], data: dict) -> None:
    _cache[key] = (time.monotonic(), data)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX_CELLS:
        _cache.popitem(last=False)


async def get_cell(ix: int, iy: int) -> dict:
    """Processed features for a cell: memory cache, then SQLite (24 h), then Overpass."""
    key = (ix, iy)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        _cache.move_to_end(key)
        return hit[1]
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]
        try:
            stored = await asyncio.to_thread(_db_load, ix, iy)
        except Exception as exc:  # cache problems must never block the feature
            log.warning("osm cell cache read failed: %s", exc)
            stored = None
        if stored is not None:
            _remember(key, stored)
            return stored
        w, s, e, n = cell_bbox(ix, iy)
        elements = await _query_overpass(QUERY.format(s=s, w=w, n=n, e=e))
        data = await asyncio.to_thread(lambda: process_elements(elements).to_json())
        data["cell"] = [ix, iy]
        data["bbox"] = [w, s, e, n]
        _remember(key, data)
        try:
            await asyncio.to_thread(_db_store, ix, iy, data)
        except Exception as exc:
            log.warning("osm cell cache write failed: %s", exc)
        return data


def is_cached(ix: int, iy: int) -> bool:
    hit = _cache.get((ix, iy))
    return bool(hit and time.monotonic() - hit[0] < CACHE_TTL_S)


def schedule_prefetch(lng: float, lat: float, radius_cells: int = 1) -> int:
    """Warm the cells around a point in the background (sequentially through the gate)."""
    ix, iy = cell_of(lng, lat)
    todo = [
        (ix + dx, iy + dy)
        for dy in range(-radius_cells, radius_cells + 1)
        for dx in range(-radius_cells, radius_cells + 1)
        if not is_cached(ix + dx, iy + dy)
    ]
    # Centre first, then the ring around it.
    todo.sort(key=lambda c: abs(c[0] - ix) + abs(c[1] - iy))

    async def run() -> None:
        for cx, cy in todo:
            try:
                await get_cell(cx, cy)
            except Exception as exc:
                log.info("prefetch of cell %d,%d skipped: %s", cx, cy, exc)
                break  # the mirrors are struggling; do not pile on

    if todo:
        task = asyncio.get_running_loop().create_task(run())
        _prefetch_tasks.add(task)
        task.add_done_callback(_prefetch_tasks.discard)
    return len(todo)
