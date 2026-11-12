import type { Polygon } from "geojson";
import type { Bounds } from "../api/types";

export type LngLat = [number, number];

export function closeRing(vertices: LngLat[]): LngLat[] {
  if (vertices.length === 0) return [];
  const first = vertices[0];
  const last = vertices[vertices.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) return vertices.slice();
  return [...vertices, first];
}

export function toPolygon(vertices: LngLat[]): Polygon {
  return { type: "Polygon", coordinates: [closeRing(vertices)] };
}

export function ringOf(polygon: Polygon): LngLat[] {
  return polygon.coordinates[0].map((c) => [c[0], c[1]] as LngLat);
}

export function bboxOf(ring: LngLat[]): Bounds {
  let w = Infinity,
    s = Infinity,
    e = -Infinity,
    n = -Infinity;
  for (const [lng, lat] of ring) {
    if (lng < w) w = lng;
    if (lng > e) e = lng;
    if (lat < s) s = lat;
    if (lat > n) n = lat;
  }
  return [w, s, e, n];
}

/** Area-weighted centroid (shoelace); falls back to the vertex mean for degenerate rings. */
export function centroidOf(ring: LngLat[]): LngLat {
  const pts = closeRing(ring);
  let a = 0,
    cx = 0,
    cy = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    const cross = x0 * y1 - x1 * y0;
    a += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }
  if (Math.abs(a) < 1e-12) {
    const n = Math.max(1, pts.length - 1);
    return [pts.reduce((s, p) => s + p[0], 0) / n, pts.reduce((s, p) => s + p[1], 0) / n];
  }
  a *= 0.5;
  return [cx / (6 * a), cy / (6 * a)];
}

/** Approximate planar area in square metres using a local equirectangular projection. */
export function areaM2(ring: LngLat[]): number {
  const pts = closeRing(ring);
  if (pts.length < 4) return 0;
  const latC = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const lngC = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const kx = 111320 * Math.cos((latC * Math.PI) / 180);
  const ky = 110540;
  let s = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const x0 = (pts[i][0] - lngC) * kx,
      y0 = (pts[i][1] - latC) * ky;
    const x1 = (pts[i + 1][0] - lngC) * kx,
      y1 = (pts[i + 1][1] - latC) * ky;
    s += x0 * y1 - x1 * y0;
  }
  return Math.abs(s) / 2;
}

export function bboxAreaM2(ring: LngLat[]): number {
  const [w, s, e, n] = bboxOf(ring);
  const latC = (s + n) / 2;
  return (e - w) * 111320 * Math.cos((latC * Math.PI) / 180) * (n - s) * 110540;
}

// ---- Highlighter strokes ---------------------------------------------------

export interface Stroke {
  coords: LngLat[];
  /** Ground width in metres, so the highlight keeps its size when the map zooms. */
  width_m: number;
}

/** One object picked by smart select: a mapped area (ring) or a road segment (stroke). */
export type SmartItem =
  | { key: string; kind: "building" | "parking" | "green"; label: string; ring: LngLat[] }
  | { key: string; kind: "road" | "path"; label: string; coords: LngLat[]; width_m: number };

/** Minimal view of a quick selection the region layer needs (avoids a map-module import cycle). */
export interface MaskSelection {
  readonly isEmpty: boolean;
  bboxRing(): LngLat[];
  export(): Promise<{ zoom: number; x0: number; y0: number; width: number; height: number; png: string } | null>;
}

export type Region =
  | { type: "polygon"; ring: LngLat[] }
  | { type: "highlight"; strokes: Stroke[] }
  | { type: "smart"; items: SmartItem[] }
  | { type: "mask"; selection: MaskSelection };

export function smartRings(items: SmartItem[]): LngLat[][] {
  return items.flatMap((i) => ("ring" in i ? [i.ring] : []));
}

export function smartStrokes(items: SmartItem[]): Stroke[] {
  return items.flatMap((i) => ("coords" in i ? [{ coords: i.coords, width_m: i.width_m }] : []));
}

/** Ray-casting point-in-polygon on lng/lat (fine at city scale). */
export function pointInRing(pt: LngLat, ring: LngLat[]): boolean {
  let inside = false;
  const [x, y] = pt;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Shortest distance in metres from a point to a polyline. */
export function distanceToPolylineM(pt: LngLat, line: LngLat[]): number {
  const kx = 111320 * Math.cos((pt[1] * Math.PI) / 180);
  const ky = 110540;
  const px = 0,
    py = 0;
  let best = Infinity;
  for (let i = 0; i < line.length - 1; i++) {
    const ax = (line[i][0] - pt[0]) * kx,
      ay = (line[i][1] - pt[1]) * ky;
    const bx = (line[i + 1][0] - pt[0]) * kx,
      by = (line[i + 1][1] - pt[1]) * ky;
    const dx = bx - ax,
      dy = by - ay;
    const len2 = dx * dx + dy * dy;
    let t = len2 > 0 ? ((px - ax) * dx + (py - ay) * dy) / len2 : 0;
    t = Math.max(0, Math.min(1, t));
    const cx = ax + t * dx,
      cy = ay + t * dy;
    best = Math.min(best, Math.hypot(cx - px, cy - py));
  }
  if (line.length === 1) {
    best = Math.hypot((line[0][0] - pt[0]) * kx, (line[0][1] - pt[1]) * ky);
  }
  return best;
}

const EQUATOR_M_PER_PX_Z0 = 156543.03392;

/** Ground metres covered by one screen pixel at this latitude and zoom. */
export function metersPerPixel(lat: number, zoom: number): number {
  return (EQUATOR_M_PER_PX_Z0 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, zoom);
}

/** Line-width endpoints for a zoom-exponential(2) interpolation: pixels at zoom 0 and zoom 24. */
export function strokeWidthProps(stroke: Stroke): { w0: number; w24: number } {
  const lat = stroke.coords[0]?.[1] ?? 0;
  const w0 = stroke.width_m / metersPerPixel(lat, 0);
  return { w0, w24: w0 * Math.pow(2, 24) };
}

/** Closed rectangle around all strokes (grown by half width) and rings. */
export function highlightBBoxRing(strokes: Stroke[], rings: LngLat[][] = []): LngLat[] {
  let w = Infinity,
    s = Infinity,
    e = -Infinity,
    n = -Infinity;
  for (const ring of rings) {
    for (const [lng, lat] of ring) {
      w = Math.min(w, lng);
      e = Math.max(e, lng);
      s = Math.min(s, lat);
      n = Math.max(n, lat);
    }
  }
  for (const st of strokes) {
    const half = st.width_m / 2;
    for (const [lng, lat] of st.coords) {
      const dlat = half / 110540;
      const dlng = half / (111320 * Math.max(0.05, Math.cos((lat * Math.PI) / 180)));
      w = Math.min(w, lng - dlng);
      e = Math.max(e, lng + dlng);
      s = Math.min(s, lat - dlat);
      n = Math.max(n, lat + dlat);
    }
  }
  return [
    [w, n],
    [e, n],
    [e, s],
    [w, s],
    [w, n],
  ];
}

/** The ring used for size checks, anchoring and the pending outline of any region. */
export function regionRing(region: Region): LngLat[] {
  if (region.type === "polygon") return region.ring;
  if (region.type === "highlight") return highlightBBoxRing(region.strokes);
  if (region.type === "mask") return region.selection.bboxRing();
  return highlightBBoxRing(smartStrokes(region.items), smartRings(region.items));
}
