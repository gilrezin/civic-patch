/**
 * Quick selection (Photoshop-style) on the satellite tiles.
 *
 * Pixels come straight from Esri World Imagery tiles at a fixed working zoom, converted to
 * CIELAB. While the mouse is held, the pixels under the brush seed a 4-connected region
 * growth that accepts neighbours within an adaptive colour tolerance and below an edge
 * (lightness gradient) limit, never farther than MAX_SPREAD_M from the cursor.
 */

import type { CanvasSource, Map as MLMap } from "maplibre-gl";
import type { LngLat } from "../geo/polygon";

export const MAX_SPREAD_M = 10; // colour-match reach at maximum brush size; smaller brushes scale it down
export const SOLID_FRACTION = 0.5; // the any-colour gap-filling disc is this fraction of the colour radius
const SEED_SAMPLE_PX = 8; // core radius (tile px) whose pixels define the seed colour
const EDGE_LIMIT = 22; // lightness gradient above which growth stops (outside the brush)
const BASE_TOL = 10; // ΔE
const TOL_K = 1.5; // tolerance grows with the seed's colour spread
const TOL_MIN = 8;
const TOL_MAX = 28;
const TILE = 256;
const TILE_URL = (z: number, x: number, y: number) =>
  `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
const MAX_EXPORT_SIDE = 2048;
const FILL_RGBA: [number, number, number, number] = [255, 122, 0, 150];

interface TileData {
  lab: Uint8Array; // 3 bytes per pixel: L*2.55, a+128, b+128
  grad: Uint8Array; // lightness gradient magnitude, clamped to 255
}

export interface MaskExport {
  zoom: number;
  x0: number;
  y0: number;
  width: number;
  height: number;
  png: string;
}

function key(tx: number, ty: number) {
  return `${tx}:${ty}`;
}

export function worldPx(lng: number, lat: number, z: number): [number, number] {
  const w = TILE * Math.pow(2, z);
  const x = ((lng + 180) / 360) * w;
  const latR = (lat * Math.PI) / 180;
  const y = ((1 - Math.log(Math.tan(latR) + 1 / Math.cos(latR)) / Math.PI) / 2) * w;
  return [x, y];
}

export function worldPxToLngLat(x: number, y: number, z: number): LngLat {
  const w = TILE * Math.pow(2, z);
  const lng = (x / w) * 360 - 180;
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / w))) * 180) / Math.PI;
  return [lng, lat];
}

export function metersPerTilePixel(lat: number, z: number): number {
  return (156543.03392 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, z);
}

// ---- colour ---------------------------------------------------------------

function srgbToLinear(c: number): number {
  c /= 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

const LIN = new Float32Array(256);
for (let i = 0; i < 256; i++) LIN[i] = srgbToLinear(i);

function labF(t: number): number {
  return t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116;
}

function rgbToLab(r: number, g: number, b: number): [number, number, number] {
  const rl = LIN[r],
    gl = LIN[g],
    bl = LIN[b];
  const x = (rl * 0.4124 + gl * 0.3576 + bl * 0.1805) / 0.95047;
  const y = rl * 0.2126 + gl * 0.7152 + bl * 0.0722;
  const z = (rl * 0.0193 + gl * 0.1192 + bl * 0.9505) / 1.08883;
  const fx = labF(x),
    fy = labF(y),
    fz = labF(z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

/** Box-blur (3x3) the RGB, convert to Lab, and compute a Sobel gradient of L. */
function analyseTile(img: ImageData): TileData {
  const n = TILE * TILE;
  const d = img.data;
  const blurred = new Uint8ClampedArray(n * 3);
  for (let y = 0; y < TILE; y++) {
    for (let x = 0; x < TILE; x++) {
      let r = 0,
        g = 0,
        b = 0,
        c = 0;
      for (let dy = -1; dy <= 1; dy++) {
        const yy = y + dy;
        if (yy < 0 || yy >= TILE) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const xx = x + dx;
          if (xx < 0 || xx >= TILE) continue;
          const i = (yy * TILE + xx) * 4;
          r += d[i];
          g += d[i + 1];
          b += d[i + 2];
          c++;
        }
      }
      const o = (y * TILE + x) * 3;
      blurred[o] = r / c;
      blurred[o + 1] = g / c;
      blurred[o + 2] = b / c;
    }
  }
  const lab = new Uint8Array(n * 3);
  const L = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const [l, a, b] = rgbToLab(blurred[i * 3], blurred[i * 3 + 1], blurred[i * 3 + 2]);
    L[i] = l;
    lab[i * 3] = Math.max(0, Math.min(255, Math.round(l * 2.55)));
    lab[i * 3 + 1] = Math.max(0, Math.min(255, Math.round(a + 128)));
    lab[i * 3 + 2] = Math.max(0, Math.min(255, Math.round(b + 128)));
  }
  const grad = new Uint8Array(n);
  for (let y = 1; y < TILE - 1; y++) {
    for (let x = 1; x < TILE - 1; x++) {
      const i = y * TILE + x;
      const gx = -L[i - TILE - 1] - 2 * L[i - 1] - L[i + TILE - 1] + L[i - TILE + 1] + 2 * L[i + 1] + L[i + TILE + 1];
      const gy = -L[i - TILE - 1] - 2 * L[i - TILE] - L[i - TILE + 1] + L[i + TILE - 1] + 2 * L[i + TILE] + L[i + TILE + 1];
      grad[i] = Math.min(255, Math.round(Math.hypot(gx, gy) / 4));
    }
  }
  return { lab, grad };
}

// ---- selection -------------------------------------------------------------

export class QuickSelection {
  readonly zoom: number;
  private tiles = new Map<string, TileData | null>();
  private mask = new Map<string, Uint8Array>();
  private rgba = new Map<string, ImageData>();
  private dirty = new Set<string>();
  private undo: Array<Map<string, Uint8Array>> = [];
  private strokeOpen = false;
  strokeCount = 0;
  private lastCursor: { x: number; y: number; brush: number } | null = null;

  private canvas = document.createElement("canvas");
  private rect: { tx0: number; ty0: number; tx1: number; ty1: number } | null = null; // tile index range covered by canvas
  private map: MLMap | null = null;
  private sourceId = `quick-${Date.now()}`;
  private scratch: Uint8Array | null = null;
  private scratchSide = 0;
  onChange: (() => void) | null = null;

  constructor(zoom: number) {
    this.zoom = zoom;
  }

  // -- tiles --

  private tileAt(tx: number, ty: number): TileData | null | undefined {
    return this.tiles.get(key(tx, ty));
  }

  loadTile(tx: number, ty: number): void {
    const k = key(tx, ty);
    if (this.tiles.has(k)) return;
    this.tiles.set(k, null);
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = TILE;
      c.height = TILE;
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(img, 0, 0, TILE, TILE);
      let data: ImageData;
      try {
        data = ctx.getImageData(0, 0, TILE, TILE);
      } catch {
        this.tiles.delete(k);
        return;
      }
      this.tiles.set(k, analyseTile(data));
      // Continue the current stroke from the last cursor position now that pixels exist.
      if (this.strokeOpen && this.lastCursor) {
        this.grow(this.lastCursor.x, this.lastCursor.y, this.lastCursor.brush);
        this.render();
      }
    };
    img.onerror = () => {
      this.tiles.delete(k);
    };
    img.src = TILE_URL(this.zoom, tx, ty);
  }

  /** Request every tile within `radiusPx` of a world pixel. */
  prefetch(x: number, y: number, radiusPx: number): void {
    const tx0 = Math.floor((x - radiusPx) / TILE),
      tx1 = Math.floor((x + radiusPx) / TILE);
    const ty0 = Math.floor((y - radiusPx) / TILE),
      ty1 = Math.floor((y + radiusPx) / TILE);
    const max = Math.pow(2, this.zoom);
    for (let tx = Math.max(0, tx0); tx <= Math.min(max - 1, tx1); tx++) {
      for (let ty = Math.max(0, ty0); ty <= Math.min(max - 1, ty1); ty++) this.loadTile(tx, ty);
    }
  }

  isLoadedAround(x: number, y: number, radiusPx: number): boolean {
    const tx0 = Math.floor((x - radiusPx) / TILE),
      tx1 = Math.floor((x + radiusPx) / TILE);
    const ty0 = Math.floor((y - radiusPx) / TILE),
      ty1 = Math.floor((y + radiusPx) / TILE);
    for (let tx = tx0; tx <= tx1; tx++) for (let ty = ty0; ty <= ty1; ty++) if (!this.tileAt(tx, ty)) return false;
    return true;
  }

  // -- mask access --

  private maskTile(tx: number, ty: number, create: boolean): Uint8Array | undefined {
    const k = key(tx, ty);
    let m = this.mask.get(k);
    if (!m && create) {
      m = new Uint8Array(TILE * TILE);
      this.mask.set(k, m);
    }
    return m;
  }

  private isSelected(x: number, y: number): boolean {
    const m = this.mask.get(key(Math.floor(x / TILE), Math.floor(y / TILE)));
    return !!m && m[(y & 255) * TILE + (x & 255)] !== 0;
  }

  private select(x: number, y: number): void {
    const tx = Math.floor(x / TILE),
      ty = Math.floor(y / TILE);
    const m = this.maskTile(tx, ty, true)!;
    const i = (y & 255) * TILE + (x & 255);
    if (m[i] === 0) {
      m[i] = 1;
      this.dirty.add(key(tx, ty));
    }
  }

  get isEmpty(): boolean {
    for (const m of this.mask.values()) for (let i = 0; i < m.length; i++) if (m[i]) return false;
    return true;
  }

  // -- strokes --

  beginStroke(): void {
    const snap = new Map<string, Uint8Array>();
    for (const [k, m] of this.mask) snap.set(k, m.slice());
    this.undo.push(snap);
    this.strokeOpen = true;
    this.strokeCount++;
  }

  endStroke(): void {
    this.strokeOpen = false;
    this.lastCursor = null;
    this.render(true);
  }

  undoStroke(): boolean {
    const snap = this.undo.pop();
    if (!snap) return false;
    for (const k of this.mask.keys()) this.dirty.add(k);
    this.mask = snap;
    for (const k of this.mask.keys()) this.dirty.add(k);
    this.strokeCount = Math.max(0, this.strokeCount - 1);
    this.render(true);
    return true;
  }

  /**
   * One growth step with two concentric radii around the cursor (both in tile pixels):
   *  - solidPx: every pixel inside this disc is selected regardless of colour (gap filler)
   *  - colourPx: flood fill of colours similar to the seed, never beyond this radius
   */
  stroke(x: number, y: number, solidPx: number, colourPx: number): void {
    this.lastCursor = { x, y, brush: solidPx };
    this.prefetch(x, y, colourPx + solidPx);
    this.grow(x, y, solidPx, colourPx);
    this.render();
  }

  private grow(cx: number, cy: number, solidPx: number, colourPx?: number): void {
    const R = Math.max(solidPx, colourPx ?? this.lastSpread);
    this.lastSpread = R;
    const r = Math.max(1, solidPx);
    // Seed colour statistics come from a small core so a big solid disc does not loosen the tolerance.
    const sampleR = Math.min(r, SEED_SAMPLE_PX);
    const sampleRR = sampleR * sampleR;
    const side = 2 * Math.ceil(R) + 3;
    if (!this.scratch || this.scratchSide !== side) {
      this.scratch = new Uint8Array(side * side);
      this.scratchSide = side;
    } else {
      this.scratch.fill(0);
    }
    const visited = this.scratch;
    const ox = Math.round(cx) - Math.ceil(R) - 1,
      oy = Math.round(cy) - Math.ceil(R) - 1;

    // Seed statistics from the loaded pixels inside the brush.
    let n = 0,
      sl = 0,
      sa = 0,
      sb = 0,
      sl2 = 0,
      sa2 = 0,
      sb2 = 0;
    const seeds: number[] = [];
    const rr = r * r;
    for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++) {
      for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++) {
        const dx = x + 0.5 - cx,
          dy = y + 0.5 - cy;
        const d2 = dx * dx + dy * dy;
        if (d2 > rr) continue;
        const t = this.tileAt(Math.floor(x / TILE), Math.floor(y / TILE));
        if (!t) continue;
        this.select(x, y); // the solid disc is always selected, whatever its colour
        seeds.push(x, y);
        if (d2 > sampleRR) continue;
        const i = ((y & 255) * TILE + (x & 255)) * 3;
        const L = t.lab[i] / 2.55,
          a = t.lab[i + 1] - 128,
          b = t.lab[i + 2] - 128;
        n++;
        sl += L;
        sa += a;
        sb += b;
        sl2 += L * L;
        sa2 += a * a;
        sb2 += b * b;
      }
    }
    if (n === 0) return;
    const mL = sl / n,
      mA = sa / n,
      mB = sb / n;
    const spread = Math.sqrt(Math.max(0, sl2 / n - mL * mL) + Math.max(0, sa2 / n - mA * mA) + Math.max(0, sb2 / n - mB * mB));
    const tol = Math.max(TOL_MIN, Math.min(TOL_MAX, BASE_TOL + TOL_K * spread));
    const tol2 = tol * tol;
    const R2 = R * R;

    // BFS over 4-neighbours.
    const qx: number[] = [],
      qy: number[] = [];
    for (let i = 0; i < seeds.length; i += 2) {
      const vi = (seeds[i + 1] - oy) * side + (seeds[i] - ox);
      if (vi >= 0 && vi < visited.length && !visited[vi]) {
        visited[vi] = 1;
        qx.push(seeds[i]);
        qy.push(seeds[i + 1]);
      }
    }
    let head = 0;
    while (head < qx.length) {
      const x = qx[head],
        y = qy[head];
      head++;
      for (let d = 0; d < 4; d++) {
        const nx = d === 0 ? x + 1 : d === 1 ? x - 1 : x;
        const ny = d === 2 ? y + 1 : d === 3 ? y - 1 : y;
        const ddx = nx + 0.5 - cx,
          ddy = ny + 0.5 - cy;
        if (ddx * ddx + ddy * ddy > R2) continue;
        const vi = (ny - oy) * side + (nx - ox);
        if (vi < 0 || vi >= visited.length || visited[vi]) continue;
        visited[vi] = 1;
        const t = this.tileAt(Math.floor(nx / TILE), Math.floor(ny / TILE));
        if (!t) continue;
        const pi = (ny & 255) * TILE + (nx & 255);
        if (this.isSelected(nx, ny)) {
          qx.push(nx);
          qy.push(ny);
          continue;
        }
        const inBrush = ddx * ddx + ddy * ddy <= rr;
        if (!inBrush && t.grad[pi] > EDGE_LIMIT) continue;
        const i = pi * 3;
        const dL = t.lab[i] / 2.55 - mL,
          dA = t.lab[i + 1] - 128 - mA,
          dB = t.lab[i + 2] - 128 - mB;
        if (dL * dL + dA * dA + dB * dB > tol2) continue;
        this.select(nx, ny);
        qx.push(nx);
        qy.push(ny);
      }
    }
  }
  private lastSpread = 0;

  // -- geometry --

  /** Tile index range of every tile with any selected pixel. */
  private maskTileRange(): { tx0: number; ty0: number; tx1: number; ty1: number } | null {
    let tx0 = Infinity,
      ty0 = Infinity,
      tx1 = -Infinity,
      ty1 = -Infinity;
    for (const [k, m] of this.mask) {
      if (!m.some((v) => v !== 0)) continue;
      const [tx, ty] = k.split(":").map(Number);
      tx0 = Math.min(tx0, tx);
      tx1 = Math.max(tx1, tx);
      ty0 = Math.min(ty0, ty);
      ty1 = Math.max(ty1, ty);
    }
    return Number.isFinite(tx0) ? { tx0, ty0, tx1, ty1 } : null;
  }

  /** Pixel bounding box of the selection in world pixels, or null when empty. */
  pixelBounds(): { x0: number; y0: number; x1: number; y1: number } | null {
    let x0 = Infinity,
      y0 = Infinity,
      x1 = -Infinity,
      y1 = -Infinity;
    for (const [k, m] of this.mask) {
      const [tx, ty] = k.split(":").map(Number);
      for (let i = 0; i < m.length; i++) {
        if (!m[i]) continue;
        const x = tx * TILE + (i & 255),
          y = ty * TILE + (i >> 8);
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
    return Number.isFinite(x0) ? { x0, y0, x1: x1 + 1, y1: y1 + 1 } : null;
  }

  bboxRing(): LngLat[] {
    const b = this.pixelBounds();
    if (!b) return [];
    const [w, n] = worldPxToLngLat(b.x0, b.y0, this.zoom);
    const [e, s] = worldPxToLngLat(b.x1, b.y1, this.zoom);
    return [
      [w, n],
      [e, n],
      [e, s],
      [w, s],
      [w, n],
    ];
  }

  // -- rendering --

  attach(map: MLMap): void {
    this.map = map;
  }

  detach(): void {
    if (this.map) {
      if (this.map.getLayer(this.sourceId)) this.map.removeLayer(this.sourceId);
      if (this.map.getSource(this.sourceId)) this.map.removeSource(this.sourceId);
    }
    this.map = null;
    this.rect = null;
  }

  private tileImage(k: string, m: Uint8Array): ImageData {
    let img = this.rgba.get(k);
    if (!img) {
      img = new ImageData(TILE, TILE);
      this.rgba.set(k, img);
    }
    const d = img.data;
    for (let i = 0; i < m.length; i++) {
      const o = i * 4;
      if (m[i]) {
        d[o] = FILL_RGBA[0];
        d[o + 1] = FILL_RGBA[1];
        d[o + 2] = FILL_RGBA[2];
        d[o + 3] = FILL_RGBA[3];
      } else d[o + 3] = 0;
    }
    return img;
  }

  render(final = false): void {
    const map = this.map;
    if (!map) return;
    const range = this.maskTileRange();
    if (!range) {
      if (map.getLayer(this.sourceId)) map.removeLayer(this.sourceId);
      if (map.getSource(this.sourceId)) map.removeSource(this.sourceId);
      this.rect = null;
      this.dirty.clear();
      this.onChange?.();
      return;
    }
    const grew =
      !this.rect || range.tx0 < this.rect.tx0 || range.ty0 < this.rect.ty0 || range.tx1 > this.rect.tx1 || range.ty1 > this.rect.ty1;
    if (grew) {
      this.rect = {
        tx0: Math.min(range.tx0, this.rect?.tx0 ?? Infinity),
        ty0: Math.min(range.ty0, this.rect?.ty0 ?? Infinity),
        tx1: Math.max(range.tx1, this.rect?.tx1 ?? -Infinity),
        ty1: Math.max(range.ty1, this.rect?.ty1 ?? -Infinity),
      };
      this.canvas.width = (this.rect.tx1 - this.rect.tx0 + 1) * TILE;
      this.canvas.height = (this.rect.ty1 - this.rect.ty0 + 1) * TILE;
      for (const k of this.mask.keys()) this.dirty.add(k);
      if (map.getLayer(this.sourceId)) map.removeLayer(this.sourceId);
      if (map.getSource(this.sourceId)) map.removeSource(this.sourceId);
    }
    const rect = this.rect!;
    const ctx = this.canvas.getContext("2d")!;
    for (const k of this.dirty) {
      const [tx, ty] = k.split(":").map(Number);
      const m = this.mask.get(k);
      const px = (tx - rect.tx0) * TILE,
        py = (ty - rect.ty0) * TILE;
      if (!m) {
        ctx.clearRect(px, py, TILE, TILE);
        continue;
      }
      ctx.putImageData(this.tileImage(k, m), px, py);
    }
    this.dirty.clear();

    const [w, n] = worldPxToLngLat(rect.tx0 * TILE, rect.ty0 * TILE, this.zoom);
    const [e, s] = worldPxToLngLat((rect.tx1 + 1) * TILE, (rect.ty1 + 1) * TILE, this.zoom);
    const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
      [w, n],
      [e, n],
      [e, s],
      [w, s],
    ];
    if (!map.getSource(this.sourceId)) {
      map.addSource(this.sourceId, { type: "canvas", canvas: this.canvas, coordinates, animate: true });
      map.addLayer({
        id: this.sourceId,
        type: "raster",
        source: this.sourceId,
        paint: { "raster-opacity": 1, "raster-fade-duration": 0 },
      });
    } else {
      const src = map.getSource(this.sourceId) as CanvasSource;
      src.play();
      if (final) window.setTimeout(() => src.pause(), 150);
    }
    map.triggerRepaint();
    this.onChange?.();
  }

  // -- export --

  /** Encode the selection's bounding rectangle as a PNG (alpha = selected), halving the
   * resolution until it fits the backend's size limit. */
  async export(): Promise<MaskExport | null> {
    const b = this.pixelBounds();
    if (!b) return null;
    let zoom = this.zoom;
    let x0 = b.x0,
      y0 = b.y0,
      w = b.x1 - b.x0,
      h = b.y1 - b.y0;
    const full = document.createElement("canvas");
    full.width = w;
    full.height = h;
    const fctx = full.getContext("2d")!;
    const img = fctx.createImageData(w, h);
    for (const [k, m] of this.mask) {
      const [tx, ty] = k.split(":").map(Number);
      for (let i = 0; i < m.length; i++) {
        if (!m[i]) continue;
        const x = tx * TILE + (i & 255) - x0,
          y = ty * TILE + (i >> 8) - y0;
        const o = (y * w + x) * 4;
        img.data[o] = 255;
        img.data[o + 1] = 255;
        img.data[o + 2] = 255;
        img.data[o + 3] = 255;
      }
    }
    fctx.putImageData(img, 0, 0);
    let canvas = full;
    while (w > MAX_EXPORT_SIDE || h > MAX_EXPORT_SIDE) {
      // Align the origin to an even pixel so halving keeps the world position exact.
      const nx0 = Math.floor(x0 / 2),
        ny0 = Math.floor(y0 / 2);
      const nw = Math.ceil((x0 + w) / 2) - nx0,
        nh = Math.ceil((y0 + h) / 2) - ny0;
      const half = document.createElement("canvas");
      half.width = nw;
      half.height = nh;
      const hctx = half.getContext("2d")!;
      hctx.imageSmoothingEnabled = true;
      hctx.drawImage(canvas, (x0 - nx0 * 2) / 2, (y0 - ny0 * 2) / 2, w / 2, h / 2);
      canvas = half;
      x0 = nx0;
      y0 = ny0;
      w = nw;
      h = nh;
      zoom -= 1;
    }
    const dataUrl = canvas.toDataURL("image/png");
    return { zoom, x0, y0, width: w, height: h, png: dataUrl };
  }
}

/** Working zoom for pixels: close to the map zoom, clamped to the tile service's useful range. */
export function workingZoom(mapZoom: number): number {
  return Math.max(16, Math.min(19, Math.round(mapZoom)));
}

/** Ground radii in metres for a slider position (0..1]: colour-match reach and the solid gap-filling disc. */
export function brushRadiiM(sliderFraction: number): { colourM: number; solidM: number } {
  const f = Math.max(0.02, Math.min(1, sliderFraction));
  const colourM = MAX_SPREAD_M * f;
  return { colourM, solidM: colourM * SOLID_FRACTION };
}
