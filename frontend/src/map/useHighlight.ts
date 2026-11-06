import { useEffect, useRef } from "react";
import type { Map as MLMap, MapMouseEvent } from "maplibre-gl";
import { metersPerPixel, type LngLat, type Stroke } from "../geo/polygon";
import { useStore, type DrawState } from "../state/store";
import { beginPrompt, isTypingTarget } from "./useDrawPolygon";

const MIN_STEP_PX = 2.5;

/**
 * Highlighter tool: press-and-drag paints orange strokes whose width is fixed in ground
 * metres (taken from the slider's pixel width at the zoom the stroke started). Enter
 * finishes and opens the prompt box; Backspace removes the last stroke; Esc cancels.
 */
export function useHighlight(map: MLMap | null) {
  const tool = useStore((s) => s.tool);
  const draw = useStore((s) => s.draw);
  const drawRef = useRef<DrawState>(draw);
  drawRef.current = draw;
  const paintingRef = useRef(false);

  // Enter/leave highlight mode when the tool changes.
  useEffect(() => {
    if (!map) return;
    const st = useStore.getState();
    if (tool === "highlight") {
      if (!st.user) {
        st.openAuthModal(true);
        st.setTool("pan");
        return;
      }
      if (st.draw.mode === "idle" || st.draw.mode === "drawing") {
        st.setDraw({ mode: "highlighting", strokes: [], current: null });
      }
      map.dragPan.disable();
      map.doubleClickZoom.disable();
      map.getCanvas().style.cursor = "crosshair";
    } else {
      if (st.draw.mode === "highlighting") st.setDraw({ mode: "idle" });
      paintingRef.current = false;
      map.dragPan.enable();
      if (tool === "pan") {
        map.doubleClickZoom.enable();
        map.getCanvas().style.cursor = "";
      }
    }
  }, [map, tool]);

  useEffect(() => {
    if (!map) return;

    const toLngLat = (e: MapMouseEvent): LngLat => [e.lngLat.lng, e.lngLat.lat];

    const finish = () => {
      const d = drawRef.current;
      if (d.mode !== "highlighting") return;
      const strokes = d.current ? [...d.strokes, d.current] : d.strokes;
      if (strokes.length === 0) {
        useStore.getState().pushToast("info", "Drag on the map to highlight an area first.");
        return;
      }
      paintingRef.current = false;
      beginPrompt(map, { type: "highlight", strokes });
    };

    const onDown = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "highlighting" || e.originalEvent.button !== 0) return;
      e.preventDefault();
      const st = useStore.getState();
      const pt = toLngLat(e);
      const widthM = st.highlightWidthPx * metersPerPixel(pt[1], map.getZoom());
      paintingRef.current = true;
      st.setDraw({ ...d, current: { coords: [pt], width_m: widthM } });
    };

    const onMove = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "highlighting" || !paintingRef.current || !d.current) return;
      const pt = toLngLat(e);
      const last = d.current.coords[d.current.coords.length - 1];
      const a = map.project(last),
        b = map.project(pt);
      if (Math.hypot(a.x - b.x, a.y - b.y) < MIN_STEP_PX) return;
      useStore.getState().setDraw({ ...d, current: { ...d.current, coords: [...d.current.coords, pt] } });
    };

    const endStroke = () => {
      const d = drawRef.current;
      if (d.mode !== "highlighting" || !paintingRef.current) return;
      paintingRef.current = false;
      if (!d.current) return;
      let stroke: Stroke = d.current;
      if (stroke.coords.length === 1) {
        // A click without drag becomes a dot: nudge a second point one pixel over so
        // the round-capped line renders.
        const p = map.project(stroke.coords[0]);
        const q = map.unproject([p.x + 1, p.y]);
        stroke = { ...stroke, coords: [stroke.coords[0], [q.lng, q.lat]] };
      }
      useStore.getState().setDraw({ mode: "highlighting", strokes: [...d.strokes, stroke], current: null });
    };

    const onKey = (e: KeyboardEvent) => {
      const st = useStore.getState();
      const d = st.draw;
      if (isTypingTarget(e.target)) return;
      if (d.mode === "highlighting") {
        if (e.key === "Enter") {
          e.preventDefault();
          finish();
        } else if (e.key === "Backspace") {
          e.preventDefault();
          if (d.current) st.setDraw({ ...d, current: null });
          else st.setDraw({ ...d, strokes: d.strokes.slice(0, -1) });
        } else if (e.key === "Escape") {
          st.setDraw({ mode: "idle" });
          st.setTool("pan");
        }
        return;
      }
      if (d.mode === "idle" && (e.key === "h" || e.key === "H")) st.setTool("highlight");
    };

    const canvas = map.getCanvasContainer();
    const onLeave = () => endStroke();

    map.on("mousedown", onDown);
    map.on("mousemove", onMove);
    map.on("mouseup", endStroke);
    canvas.addEventListener("mouseleave", onLeave);
    window.addEventListener("keydown", onKey);
    return () => {
      map.off("mousedown", onDown);
      map.off("mousemove", onMove);
      map.off("mouseup", endStroke);
      canvas.removeEventListener("mouseleave", onLeave);
      window.removeEventListener("keydown", onKey);
    };
  }, [map]);
}

/** Exposed for the toolbar's "Done" button. */
export function finishHighlight(map: MLMap) {
  const d = useStore.getState().draw;
  if (d.mode !== "highlighting") return;
  const strokes = d.current ? [...d.strokes, d.current] : d.strokes;
  if (strokes.length === 0) {
    useStore.getState().pushToast("info", "Drag on the map to highlight an area first.");
    return;
  }
  beginPrompt(map, { type: "highlight", strokes });
}
