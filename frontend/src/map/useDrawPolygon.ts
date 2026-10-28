import { useEffect, useRef } from "react";
import type { Feature, FeatureCollection } from "geojson";
import type { GeoJSONSource, Map as MLMap, MapMouseEvent } from "maplibre-gl";
import { areaM2, bboxAreaM2, centroidOf, closeRing, type LngLat } from "../geo/polygon";
import { useStore, type DrawState } from "../state/store";
import { SOURCE } from "./layers";

const SNAP_PX = 12;
const MAX_BBOX_KM2 = 1.0;
const MIN_POLY_M2 = 20;

function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
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

function finalFeatures(ring: LngLat[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: [
      { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [closeRing(ring)] } },
      { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: closeRing(ring) } },
    ],
  };
}

export function useDrawPolygon(map: MLMap | null) {
  const tool = useStore((s) => s.tool);
  const draw = useStore((s) => s.draw);
  const drawRef = useRef<DrawState>(draw);
  drawRef.current = draw;

  // Render the preview whenever draw state changes.
  useEffect(() => {
    if (!map) return;
    const src = map.getSource(SOURCE.draw) as GeoJSONSource | undefined;
    if (!src) return;
    if (draw.mode === "drawing") {
      const snappable = draw.vertices.length >= 3 && !!draw.cursor && nearFirst(map, draw.vertices, draw.cursor);
      src.setData(previewFeatures(draw.vertices, draw.cursor, snappable));
    } else if (draw.mode === "prompting" || draw.mode === "submitting") {
      src.setData(draw.mode === "prompting" ? finalFeatures(draw.ring) : { type: "FeatureCollection", features: [] });
    } else {
      src.setData({ type: "FeatureCollection", features: [] });
    }
  }, [map, draw]);

  // Enter/leave drawing mode when the tool changes.
  useEffect(() => {
    if (!map) return;
    const st = useStore.getState();
    if (tool === "draw") {
      if (!st.user) {
        st.openAuthModal(true);
        st.setTool("pan");
        return;
      }
      if (st.draw.mode === "idle") st.setDraw({ mode: "drawing", vertices: [], cursor: null });
      map.doubleClickZoom.disable();
      map.getCanvas().style.cursor = "crosshair";
    } else {
      if (st.draw.mode === "drawing") st.setDraw({ mode: "idle" });
      map.doubleClickZoom.enable();
      map.getCanvas().style.cursor = "";
    }
  }, [map, tool]);

  useEffect(() => {
    if (!map) return;

    const closeRingAndPrompt = (vertices: LngLat[]) => {
      if (vertices.length < 3) return;
      const st = useStore.getState();
      if (bboxAreaM2(vertices) > MAX_BBOX_KM2 * 1_000_000) {
        st.pushToast("error", `That area is too large. Please keep selections under ${MAX_BBOX_KM2} km².`);
        return;
      }
      if (areaM2(vertices) < MIN_POLY_M2) {
        st.pushToast("error", "That area is too small. Zoom in and draw a larger shape.");
        return;
      }
      st.setDraw({ mode: "prompting", ring: vertices, anchor: centroidOf(vertices) });
      map.getCanvas().style.cursor = "";
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
        } else if (st.selectedId !== null) {
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
