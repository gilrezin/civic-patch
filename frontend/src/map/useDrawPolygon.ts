import { useEffect, useRef } from "react";
import type { Feature, FeatureCollection } from "geojson";
import type { GeoJSONSource, Map as MLMap, MapMouseEvent } from "maplibre-gl";
import {
  areaM2,
  bboxAreaM2,
  centroidOf,
  closeRing,
  regionRing,
  smartRings,
  smartStrokes,
  type LngLat,
  type Region,
  type SmartItem,
} from "../geo/polygon";
import { useStore, type DrawState } from "../state/store";
import { SOURCE } from "./layers";
import { ringFeatures, strokeFeatures } from "./overlays";

const SNAP_PX = 12;
const MAX_BBOX_KM2 = 1.0;
const MIN_POLY_M2 = 20;

export function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
}

/** Shared size guardrails; returns an error message or null. */
export function regionSizeProblem(region: Region): string | null {
  const ring = regionRing(region);
  if (bboxAreaM2(ring) > MAX_BBOX_KM2 * 1_000_000) {
    return `That area is too large. Please keep selections under ${MAX_BBOX_KM2} km².`;
  }
  if (areaM2(ring) < MIN_POLY_M2) return "That area is too small. Zoom in and select a larger area.";
  return null;
}

/** Move to the prompt box for a finished region (polygon or highlight). */
export function beginPrompt(map: MLMap, region: Region): boolean {
  const st = useStore.getState();
  const problem = regionSizeProblem(region);
  if (problem) {
    st.pushToast("error", problem);
    return false;
  }
  st.setDraw({ mode: "prompting", region, anchor: centroidOf(regionRing(region)) });
  map.getCanvas().style.cursor = "";
  return true;
}

function previewFeatures(vertices: LngLat[], cursor: LngLat | null, snappable: boolean): FeatureCollection {
  const features: Feature[] = [];
  const line = cursor ? [...vertices, cursor] : vertices;
  if (line.length >= 2) {
    features.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: line } });
  }
  if (line.length >= 3) {
    features.push({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [closeRing(line)] } });
  }
  vertices.forEach((v, i) => {
    features.push({
      type: "Feature",
      properties: { first: i === 0, snappable: i === 0 && snappable },
      geometry: { type: "Point", coordinates: v },
    });
  });
  return { type: "FeatureCollection", features };
}

/** Selected smart items as fill + outline + stroke features; the hover candidate as a dashed outline. */
function smartFeatures(items: SmartItem[], candidate: SmartItem | null): Feature[] {
  const features: Feature[] = [];
  const rings = smartRings(items);
  features.push(...ringFeatures(-1, "preview", rings));
  for (const r of rings) {
    features.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: closeRing(r) } });
  }
  features.push(...strokeFeatures(-1, "preview", smartStrokes(items)));
  if (candidate && !items.some((i) => i.key === candidate.key)) {
    if ("ring" in candidate) {
      features.push({ type: "Feature", properties: { candidate: true }, geometry: { type: "LineString", coordinates: closeRing(candidate.ring) } });
    } else {
      features.push({ type: "Feature", properties: { candidate: true }, geometry: { type: "LineString", coordinates: candidate.coords } });
    }
  }
  return features;
}

function regionFeatures(region: Region): FeatureCollection {
  if (region.type === "highlight") {
    return { type: "FeatureCollection", features: strokeFeatures(-1, "preview", region.strokes) };
  }
  if (region.type === "smart") {
    return { type: "FeatureCollection", features: smartFeatures(region.items, null) };
  }
  if (region.type === "mask") {
    // The quick selection draws itself as a raster; nothing to add here.
    return { type: "FeatureCollection", features: [] };
  }
  return {
    type: "FeatureCollection",
    features: [
      { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [closeRing(region.ring)] } },
      { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: closeRing(region.ring) } },
    ],
  };
}

export function useDrawPolygon(map: MLMap | null) {
  const tool = useStore((s) => s.tool);
  const draw = useStore((s) => s.draw);
  const drawRef = useRef<DrawState>(draw);
  drawRef.current = draw;

  // Render the preview for every drawing mode whenever draw state changes.
  useEffect(() => {
    if (!map) return;
    const src = map.getSource(SOURCE.draw) as GeoJSONSource | undefined;
    if (!src) return;
    if (draw.mode === "drawing") {
      const snappable = draw.vertices.length >= 3 && !!draw.cursor && nearFirst(map, draw.vertices, draw.cursor);
      src.setData(previewFeatures(draw.vertices, draw.cursor, snappable));
    } else if (draw.mode === "highlighting") {
      src.setData({ type: "FeatureCollection", features: [] });
    } else if (draw.mode === "smart") {
      src.setData({ type: "FeatureCollection", features: smartFeatures(draw.items, draw.candidate) });
    } else if (draw.mode === "prompting") {
      src.setData(regionFeatures(draw.region));
    } else {
      src.setData({ type: "FeatureCollection", features: [] });
    }
  }, [map, draw]);

  // Enter/leave polygon drawing mode when the tool changes.
  useEffect(() => {
    if (!map) return;
    const st = useStore.getState();
    if (tool === "draw") {
      if (!st.user) {
        st.openAuthModal(true);
        st.setTool("pan");
        return;
      }
      if (st.draw.mode === "idle" || st.draw.mode === "highlighting" || st.draw.mode === "smart") {
        st.setDraw({ mode: "drawing", vertices: [], cursor: null });
      }
      map.doubleClickZoom.disable();
      map.getCanvas().style.cursor = "crosshair";
    } else {
      if (st.draw.mode === "drawing") st.setDraw({ mode: "idle" });
      map.doubleClickZoom.enable();
      if (tool === "pan") map.getCanvas().style.cursor = "";
    }
  }, [map, tool]);

  useEffect(() => {
    if (!map) return;

    const closeRingAndPrompt = (vertices: LngLat[]) => {
      if (vertices.length < 3) return;
      beginPrompt(map, { type: "polygon", ring: vertices });
    };

    const onClick = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "drawing") return;
      const pt: LngLat = [e.lngLat.lng, e.lngLat.lat];
      if (d.vertices.length >= 3 && nearFirst(map, d.vertices, pt)) {
        closeRingAndPrompt(d.vertices);
        return;
      }
      useStore.getState().setDraw({ mode: "drawing", vertices: [...d.vertices, pt], cursor: pt });
    };

    const onDblClick = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "drawing") return;
      e.preventDefault();
      // The double-click's own two clicks have already added the same vertex twice; drop the duplicate.
      const v = d.vertices.slice();
      if (v.length >= 2) {
        const a = v[v.length - 1],
          b = v[v.length - 2];
        if (Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9) v.pop();
      }
      closeRingAndPrompt(v);
    };

    const onMove = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "drawing" || d.vertices.length === 0) return;
      useStore.getState().setDraw({ ...d, cursor: [e.lngLat.lng, e.lngLat.lat] });
    };

    const onKey = (e: KeyboardEvent) => {
      const st = useStore.getState();
      const d = st.draw;
      if (isTypingTarget(e.target)) return;
      if (e.key === "Escape") {
        if (d.mode === "drawing" || d.mode === "prompting") {
          st.setDraw({ mode: "idle" });
          st.setTool("pan");
        } else if (d.mode === "idle" && st.selectedId !== null) {
          st.select(null);
        }
        return;
      }
      if (d.mode === "drawing") {
        if (e.key === "Enter") closeRingAndPrompt(d.vertices);
        else if (e.key === "Backspace") st.setDraw({ ...d, vertices: d.vertices.slice(0, -1) });
        return;
      }
      if (d.mode === "idle" && (e.key === "d" || e.key === "D")) st.setTool("draw");
    };

    map.on("click", onClick);
    map.on("dblclick", onDblClick);
    map.on("mousemove", onMove);
    window.addEventListener("keydown", onKey);
    return () => {
      map.off("click", onClick);
      map.off("dblclick", onDblClick);
      map.off("mousemove", onMove);
      window.removeEventListener("keydown", onKey);
    };
  }, [map]);
}

function nearFirst(map: MLMap, vertices: LngLat[], pt: LngLat): boolean {
  const a = map.project(vertices[0]);
  const b = map.project(pt);
  const dx = a.x - b.x,
    dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy) <= SNAP_PX;
}
