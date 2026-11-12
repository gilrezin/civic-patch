import { api } from "../api/client";
import type { OsmArea, OsmCell, OsmRoad } from "../api/types";
import { areaM2, distanceToPolylineM, pointInRing, type LngLat, type SmartItem } from "../geo/polygon";

export const CELL_DEG = 0.01;
/** Smart select needs enough zoom that a viewport spans only a handful of cells. */
export const SMART_MIN_ZOOM = 16;
const ROAD_TOLERANCE_M = 1.5;

const cells = new Map<string, OsmCell>();
const pending = new Map<string, Promise<OsmCell>>();

export function cellKey(ix: number, iy: number) {
  return `${ix}:${iy}`;
}

export function cellOf(lng: number, lat: number): [number, number] {
  return [Math.floor(lng / CELL_DEG), Math.floor(lat / CELL_DEG)];
}

export function cellsForBounds(w: number, s: number, e: number, n: number): [number, number][] {
  const [x0, y0] = cellOf(w, s);
  const [x1, y1] = cellOf(e, n);
  const out: [number, number][] = [];
  for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) out.push([x, y]);
  return out;
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

/** Load every cell covering the bounds; resolves when all are available. */
export async function ensureCells(w: number, s: number, e: number, n: number): Promise<void> {
  await Promise.all(cellsForBounds(w, s, e, n).map(([x, y]) => loadCell(x, y)));
}

function toItem(a: OsmArea): SmartItem;
function toItem(r: OsmRoad): SmartItem;
function toItem(f: OsmArea | OsmRoad): SmartItem {
  if ("ring" in f) return { key: f.key, kind: f.kind, label: f.label, ring: f.ring };
  return { key: f.key, kind: f.kind, label: f.label, coords: f.coords, width_m: f.width_m };
}

/**
 * The object under a point: the smallest mapped area containing it (building beats the lot
 * or park it sits in), else the nearest road segment within its half width.
 * Returns undefined when the cell is not loaded yet and null when nothing is there.
 */
export function featureAt(pt: LngLat): SmartItem | null | undefined {
  const [ix, iy] = cellOf(pt[0], pt[1]);
  // Features straddle cell edges, so look at the point's cell and its neighbours.
  const candidates: OsmCell[] = [];
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      const c = cells.get(cellKey(ix + dx, iy + dy));
      if (c) candidates.push(c);
    }
  }
  if (!cells.has(cellKey(ix, iy))) return undefined;

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
  if (bestArea) return toItem(bestArea);

  let bestRoad: OsmRoad | null = null;
  let bestDist = Infinity;
  for (const c of candidates) {
    for (const r of c.roads) {
      const d = distanceToPolylineM(pt, r.coords);
      if (d <= r.width_m / 2 + ROAD_TOLERANCE_M && d < bestDist) {
        bestDist = d;
        bestRoad = r;
      }
    }
  }
  return bestRoad ? toItem(bestRoad) : null;
}

export function describeItems(items: SmartItem[]): string {
  const counts: Record<string, number> = {};
  for (const i of items) counts[i.kind] = (counts[i.kind] ?? 0) + 1;
  const names: Record<string, [string, string]> = {
    building: ["building", "buildings"],
    parking: ["parking lot", "parking lots"],
    green: ["green space", "green spaces"],
    road: ["road segment", "road segments"],
    path: ["path", "paths"],
  };
  const parts = Object.entries(counts).map(([k, n]) => `${n} ${names[k]?.[n === 1 ? 0 : 1] ?? k}`);
  return parts.join(", ");
}
