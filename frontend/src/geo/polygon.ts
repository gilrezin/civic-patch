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
