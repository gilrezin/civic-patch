/**
 * Block finder for smart select: the area around a point bounded by the nearest roads.
 *
 * Roads from the loaded OSM cells are rasterised at their width into a small local grid
 * centred on the click, a 4-connected flood fill runs from the click until it hits road
 * cells, and the filled region's outline becomes the block polygon. The grid is capped at
 * MAX_BLOCK_SEARCH_M in every direction; a fill that reaches the grid edge is clipped there
 * and reported as truncated.
 */

import type { OsmRoad } from "../api/types";
import type { LngLat } from "../geo/polygon";

export const MAX_BLOCK_SEARCH_M = 220; // failsafe: never look for bounding roads farther than this
const CELL_M = 1.5;
const ROAD_BUFFER_M = 1.0; // extra half-width so the block stops at the kerb, not the lane edge
const MIN_ROAD_WIDTH_M = 5.0;
const SIMPLIFY_CELLS = 0.8;

export interface BlockResult {
  ring: LngLat[];
  truncated: boolean;
  areaCells: number;
}

export type BlockOutcome = { ok: true; block: BlockResult } | { ok: false; reason: "on_road" | "no_roads" | "too_small" };

export function findBlock(pt: LngLat, roads: OsmRoad[]): BlockOutcome {
  const [lng0, lat0] = pt;
  const kx = 111320 * Math.cos((lat0 * Math.PI) / 180);
  const ky = 110540;
  const toLocal = (p: [number, number]): [number, number] => [(p[0] - lng0) * kx, (p[1] - lat0) * ky];

  const R = MAX_BLOCK_SEARCH_M;
  const N = Math.ceil((2 * R) / CELL_M) + 1;
  const origin = -(N * CELL_M) / 2; // local metres of grid corner (0,0)
  const grid = new Uint8Array(N * N); // 1 = road

  // Rasterise drivable roads near the grid.
  let anyRoad = false;
  const limit = R + 40;
  for (const r of roads) {
    if (r.kind !== "road" || r.coords.length < 2) continue;
    const half = Math.max(MIN_ROAD_WIDTH_M, r.width_m) / 2 + ROAD_BUFFER_M;
    const pts = r.coords.map(toLocal);
    for (let s = 0; s < pts.length - 1; s++) {
      const [ax, ay] = pts[s];
      const [bx, by] = pts[s + 1];
      const minx = Math.min(ax, bx) - half,
        maxx = Math.max(ax, bx) + half;
      const miny = Math.min(ay, by) - half,
        maxy = Math.max(ay, by) + half;
      if (maxx < -limit || minx > limit || maxy < -limit || miny > limit) continue;
      anyRoad = true;
      const i0 = Math.max(0, Math.floor((minx - origin) / CELL_M));
      const i1 = Math.min(N - 1, Math.ceil((maxx - origin) / CELL_M));
      const j0 = Math.max(0, Math.floor((miny - origin) / CELL_M));
      const j1 = Math.min(N - 1, Math.ceil((maxy - origin) / CELL_M));
      const dx = bx - ax,
        dy = by - ay;
      const len2 = dx * dx + dy * dy || 1e-9;
      const h2 = half * half;
      for (let j = j0; j <= j1; j++) {
        const cy = origin + (j + 0.5) * CELL_M;
        for (let i = i0; i <= i1; i++) {
          const cx = origin + (i + 0.5) * CELL_M;
          let t = ((cx - ax) * dx + (cy - ay) * dy) / len2;
          t = t < 0 ? 0 : t > 1 ? 1 : t;
          const px = ax + t * dx - cx,
            py = ay + t * dy - cy;
          if (px * px + py * py <= h2) grid[j * N + i] = 1;
        }
      }
    }
  }
  if (!anyRoad) return { ok: false, reason: "no_roads" };

  const ci = Math.floor((0 - origin) / CELL_M),
    cj = Math.floor((0 - origin) / CELL_M);
  if (grid[cj * N + ci] === 1) return { ok: false, reason: "on_road" };

  // Flood fill (4-connected) from the centre through non-road cells.
  const filled = new Uint8Array(N * N);
  const queue = new Int32Array(N * N);
  let head = 0,
    tail = 0;
  queue[tail++] = cj * N + ci;
  filled[cj * N + ci] = 1;
  let truncated = false;
  let count = 0;
  while (head < tail) {
    const idx = queue[head++];
    count++;
    const i = idx % N,
      j = (idx - i) / N;
    if (i === 0 || j === 0 || i === N - 1 || j === N - 1) truncated = true;
    if (i > 0) push(idx - 1);
    if (i < N - 1) push(idx + 1);
    if (j > 0) push(idx - N);
    if (j < N - 1) push(idx + N);
  }
  function push(n: number) {
    if (!filled[n] && !grid[n]) {
      filled[n] = 1;
      queue[tail++] = n;
    }
  }
  if (count < 4) return { ok: false, reason: "too_small" };

  const outline = traceOuter(filled, N);
  if (!outline || outline.length < 4) return { ok: false, reason: "too_small" };
  const simplified = simplifyClosed(outline, SIMPLIFY_CELLS);
  const ring: LngLat[] = simplified.map(([i, j]) => {
    const x = origin + i * CELL_M,
      y = origin + j * CELL_M;
    return [lng0 + x / kx, lat0 + y / ky];
  });
  return { ok: true, block: { ring, truncated, areaCells: count } };
}

// ---- outline tracing on a boolean grid -----------------------------------------

type P = [number, number];

/** Largest closed loop of the region's boundary, as cell-corner coordinates. */
function traceOuter(filled: Uint8Array, N: number): P[] | null {
  const inside = (i: number, j: number) => i >= 0 && j >= 0 && i < N && j < N && filled[j * N + i] === 1;
  // Directed edges keep the region on the left (counter-clockwise in a y-up frame).
  const edges = new Map<number, number[]>(); // from corner key -> list of to corner keys
  const key = (i: number, j: number) => j * (N + 1) + i;
  const add = (a: P, b: P) => {
    const k = key(a[0], a[1]);
    const arr = edges.get(k);
    if (arr) arr.push(key(b[0], b[1]));
    else edges.set(k, [key(b[0], b[1])]);
  };
  for (let j = 0; j < N; j++) {
    for (let i = 0; i < N; i++) {
      if (!filled[j * N + i]) continue;
      if (!inside(i, j - 1)) add([i, j], [i + 1, j]); // bottom edge, going east
      if (!inside(i + 1, j)) add([i + 1, j], [i + 1, j + 1]); // right edge, going north
      if (!inside(i, j + 1)) add([i + 1, j + 1], [i, j + 1]); // top edge, going west
      if (!inside(i - 1, j)) add([i, j + 1], [i, j]); // left edge, going south
    }
  }
  const unkey = (k: number): P => [k % (N + 1), Math.floor(k / (N + 1))];
  let best: P[] | null = null;
  let bestArea = 0;
  while (edges.size) {
    const start = edges.keys().next().value as number;
    const loop: P[] = [unkey(start)];
    let cur = start;
    let prev: P | null = null;
    for (let guard = 0; guard < 4 * N * N; guard++) {
      const outs = edges.get(cur);
      if (!outs || outs.length === 0) {
        edges.delete(cur);
        break;
      }
      let pick = 0;
      if (outs.length > 1 && prev) {
        // Prefer the sharpest left turn so touching corners stay separate loops.
        const c = unkey(cur);
        const din: P = [c[0] - prev[0], c[1] - prev[1]];
        let bestTurn = -Infinity;
        outs.forEach((o, idx) => {
          const n = unkey(o);
          const dout: P = [n[0] - c[0], n[1] - c[1]];
          const cross = din[0] * dout[1] - din[1] * dout[0];
          const dot = din[0] * dout[0] + din[1] * dout[1];
          const turn = Math.atan2(cross, dot);
          if (turn > bestTurn) {
            bestTurn = turn;
            pick = idx;
          }
        });
      }
      const next = outs.splice(pick, 1)[0];
      if (outs.length === 0) edges.delete(cur);
      prev = unkey(cur);
      loop.push(unkey(next));
      cur = next;
      if (cur === start) break;
    }
    if (loop.length >= 4 && loop[0][0] === loop[loop.length - 1][0] && loop[0][1] === loop[loop.length - 1][1]) {
      const a = Math.abs(area(loop));
      if (a > bestArea) {
        bestArea = a;
        best = loop;
      }
    }
  }
  return best;
}

function area(ring: P[]): number {
  let s = 0;
  for (let i = 0; i < ring.length - 1; i++) s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  return s / 2;
}

function simplifyClosed(points: P[], eps: number): P[] {
  if (points.length <= 4) return points;
  const dp = (pts: P[]): P[] => {
    if (pts.length < 3) return pts;
    const [x0, y0] = pts[0];
    const [x1, y1] = pts[pts.length - 1];
    const dx = x1 - x0,
      dy = y1 - y0;
    const norm = Math.hypot(dx, dy);
    let bi = -1,
      bd = -1;
    for (let i = 1; i < pts.length - 1; i++) {
      const [x, y] = pts[i];
      const d = norm ? Math.abs(dy * (x - x0) - dx * (y - y0)) / norm : Math.hypot(x - x0, y - y0);
      if (d > bd) {
        bd = d;
        bi = i;
      }
    }
    if (bd > eps) {
      const l = dp(pts.slice(0, bi + 1));
      const r = dp(pts.slice(bi));
      return l.slice(0, -1).concat(r);
    }
    return [pts[0], pts[pts.length - 1]];
  };
  let far = 0,
    fd = -1;
  for (let i = 0; i < points.length - 1; i++) {
    const d = Math.hypot(points[i][0] - points[0][0], points[i][1] - points[0][1]);
    if (d > fd) {
      fd = d;
      far = i;
    }
  }
  const a = dp(points.slice(0, far + 1));
  const b = dp(points.slice(far));
  const out = a.slice(0, -1).concat(b);
  if (out[0][0] !== out[out.length - 1][0] || out[0][1] !== out[out.length - 1][1]) out.push(out[0]);
  return out;
}
