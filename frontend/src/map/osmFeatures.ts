import { api } from "../api/client";
import type { OsmArea, OsmCell, OsmRoad } from "../api/types";
import { areaM2, distanceToPolylineM, pointInRing, type LngLat, type SmartItem } from "../geo/polygon";
import { MAX_BLOCK_SEARCH_M, findBlock } from "./blocks";

export const CELL_DEG = 0.01;
/** Smart select needs enough zoom that only a few cells are ever in play. */
export const SMART_MIN_ZOOM = 17;
const ROAD_TOLERANCE_M = 1.5;
/** Neighbouring cells are loaded only when the cursor is this close to their edge. */
const NEIGHBOUR_REACH_M = MAX_BLOCK_SEARCH_M + 30;

const cells = new Map<string, OsmCell>();
const pending = new Map<string, Promise<OsmCell>>();

export function cellKey(ix: number, iy: number) {
  return `${ix}:${iy}`;
}

export function cellOf(lng: number, lat: number): [number, number] {
  return [Math.floor(lng / CELL_DEG), Math.floor(lat / CELL_DEG)];
}

export function isLoaded(ix: number, iy: number) {
  return cells.has(cellKey(ix, iy));
}

export function loadCell(ix: number, iy: number): Promise<OsmCell> {
  const key = cellKey(ix, iy);
  const have = cells.get(key);
  if (have) return Promise.resolve(have);
  const inflight = pending.get(key);
  if (inflight) return inflight;
  const p = api
    .osmCell(ix, iy)
    .then((c) => {
      cells.set(key, c);
      return c;
    })
    .finally(() => pending.delete(key));
  pending.set(key, p);
  return p;
}

/**
 * Cells needed to resolve a click at this point: its own cell plus any neighbour whose edge
 * lies within the block search reach. Typically one cell; up to four near a corner.
 */
export function cellsAround(pt: LngLat): [number, number][] {
  const [lng, lat] = pt;
  const [ix, iy] = cellOf(lng, lat);
  const kx = 111320 * Math.cos((lat * Math.PI) / 180);
  const ky = 110540;
  const dxW = (lng - ix * CELL_DEG) * kx,
    dxE = ((ix + 1) * CELL_DEG - lng) * kx;
  const dyS = (lat - iy * CELL_DEG) * ky,
    dyN = ((iy + 1) * CELL_DEG - lat) * ky;
  const xs = [0];
  if (dxW < NEIGHBOUR_REACH_M) xs.push(-1);
  if (dxE < NEIGHBOUR_REACH_M) xs.push(1);
  const ys = [0];
  if (dyS < NEIGHBOUR_REACH_M) ys.push(-1);
  if (dyN < NEIGHBOUR_REACH_M) ys.push(1);
  const out: [number, number][] = [];
  for (const dx of xs) for (const dy of ys) out.push([ix + dx, iy + dy]);
  return out;
}

/** Load the cells a click at this point needs; resolves when all are available. */
export async function ensureAround(pt: LngLat): Promise<void> {
  await Promise.all(cellsAround(pt).map(([x, y]) => loadCell(x, y)));
}

export function isReadyAround(pt: LngLat): boolean {
  return cellsAround(pt).every(([x, y]) => isLoaded(x, y));
}

function toItem(a: OsmArea): SmartItem;
function toItem(r: OsmRoad): SmartItem;
function toItem(f: OsmArea | OsmRoad): SmartItem {
  if ("ring" in f) return { key: f.key, kind: f.kind, label: f.label, ring: f.ring };
  return { key: f.key, kind: f.kind, label: f.label, coords: f.coords, width_m: f.width_m };
}

export type SmartHit =
  | { kind: "loading" }
  | { kind: "item"; item: SmartItem; truncated?: boolean }
  | { kind: "road" }
  | { kind: "empty"; reason: "no_roads" | "too_small" };

let blockSeq = 1;

/**
 * What a point selects:
 *  - the smallest mapped area containing it (a building beats the lot or park it sits in);
 *  - otherwise, if the point is on a road, nothing (roads are boundaries, not selections);
 *  - otherwise the block: the vacant area around the point bounded by the nearest roads.
 */
export function smartHit(pt: LngLat): SmartHit {
  if (!isReadyAround(pt)) return { kind: "loading" };
  const candidates: OsmCell[] = [];
  for (const [x, y] of cellsAround(pt)) {
    const c = cells.get(cellKey(x, y));
    if (c) candidates.push(c);
  }

  let bestArea: OsmArea | null = null;
  let bestSize = Infinity;
  for (const c of candidates) {
    for (const a of c.areas) {
      if (!pointInRing(pt, a.ring)) continue;
      const size = areaM2(a.ring);
      // Buildings win over the lot/park they sit in even if larger-looking due to a bad ring.
      const rank = (a.kind === "building" ? 0 : 1e9) + size;
      if (rank < bestSize) {
        bestSize = rank;
        bestArea = a;
      }
    }
  }
  if (bestArea) return { kind: "item", item: toItem(bestArea) };

  const roads: OsmRoad[] = [];
  for (const c of candidates) roads.push(...c.roads);
  for (const r of roads) {
    if (r.kind !== "road") continue;
    if (distanceToPolylineM(pt, r.coords) <= r.width_m / 2 + ROAD_TOLERANCE_M) return { kind: "road" };
  }

  const res = findBlock(pt, roads);
  if (!res.ok) return res.reason === "on_road" ? { kind: "road" } : { kind: "empty", reason: res.reason };
  const label = res.block.truncated ? `Block (cut at ${MAX_BLOCK_SEARCH_M} m)` : "Block";
  return {
    kind: "item",
    item: { key: `b${blockSeq++}`, kind: "block", label, ring: res.block.ring },
    truncated: res.block.truncated,
  };
}

export function describeItems(items: SmartItem[]): string {
  const counts: Record<string, number> = {};
  for (const i of items) counts[i.kind] = (counts[i.kind] ?? 0) + 1;
  const names: Record<string, [string, string]> = {
    building: ["building", "buildings"],
    parking: ["parking lot", "parking lots"],
    green: ["green space", "green spaces"],
    block: ["block", "blocks"],
    road: ["road segment", "road segments"],
    path: ["path", "paths"],
  };
  const parts = Object.entries(counts).map(([k, n]) => `${n} ${names[k]?.[n === 1 ? 0 : 1] ?? k}`);
  return parts.join(", ");
}
