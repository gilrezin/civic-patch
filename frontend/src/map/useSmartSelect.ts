import { useEffect, useRef } from "react";
import type { Map as MLMap, MapMouseEvent } from "maplibre-gl";
import type { LngLat, SmartItem } from "../geo/polygon";
import { useStore, type DrawState } from "../state/store";
import { SMART_MIN_ZOOM, ensureCells, featureAt } from "./osmFeatures";
import { beginPrompt, isTypingTarget } from "./useDrawPolygon";

const DRAG_THRESHOLD_PX = 4;

/**
 * Smart select: click a mapped building, lot, park or road segment to select it; drag to
 * collect every object the cursor passes over; click a selected object again to remove it.
 * Enter opens the prompt box; Backspace removes the last item; Esc cancels.
 */
export function useSmartSelect(map: MLMap | null) {
  const tool = useStore((s) => s.tool);
  const draw = useStore((s) => s.draw);
  const drawRef = useRef<DrawState>(draw);
  drawRef.current = draw;
  const pressRef = useRef<{ x: number; y: number; dragged: boolean } | null>(null);
  const loadSeq = useRef(0);

  // Enter/leave the tool.
  useEffect(() => {
    if (!map) return;
    const st = useStore.getState();
    if (tool === "smart") {
      if (!st.user) {
        st.openAuthModal(true);
        st.setTool("pan");
        return;
      }
      if (st.draw.mode === "idle" || st.draw.mode === "drawing" || st.draw.mode === "highlighting") {
        st.setDraw({ mode: "smart", items: [], candidate: null, status: "loading" });
      }
      map.dragPan.disable();
      map.doubleClickZoom.disable();
      map.getCanvas().style.cursor = "crosshair";
    } else {
      if (st.draw.mode === "smart") st.setDraw({ mode: "idle" });
      pressRef.current = null;
      map.dragPan.enable();
      if (tool === "pan") {
        map.doubleClickZoom.enable();
        map.getCanvas().style.cursor = "";
      }
    }
  }, [map, tool]);

  // Load the cells under the viewport whenever the tool is active and the map settles.
  useEffect(() => {
    if (!map || tool !== "smart") return;

    const load = async () => {
      const d = useStore.getState().draw;
      if (d.mode !== "smart") return;
      if (map.getZoom() < SMART_MIN_ZOOM) {
        useStore.getState().setDraw({ ...d, status: "zoom" });
        return;
      }
      const seq = ++loadSeq.current;
      useStore.getState().setDraw({ ...d, status: "loading" });
      const b = map.getBounds();
      try {
        await ensureCells(b.getWest(), b.getSouth(), b.getEast(), b.getNorth());
        const cur = useStore.getState().draw;
        if (seq === loadSeq.current && cur.mode === "smart") useStore.getState().setDraw({ ...cur, status: "ready" });
      } catch {
        const cur = useStore.getState().draw;
        if (seq === loadSeq.current && cur.mode === "smart") {
          useStore.getState().setDraw({ ...cur, status: "error" });
          useStore.getState().pushToast("error", "Map features could not be loaded. Try again in a moment.");
        }
      }
    };

    void load();
    map.on("moveend", load);
    return () => {
      map.off("moveend", load);
    };
  }, [map, tool]);

  useEffect(() => {
    if (!map) return;

    const toLngLat = (e: MapMouseEvent): LngLat => [e.lngLat.lng, e.lngLat.lat];

    const addItem = (d: Extract<DrawState, { mode: "smart" }>, item: SmartItem) => {
      if (d.items.some((i) => i.key === item.key)) return;
      useStore.getState().setDraw({ ...d, items: [...d.items, item], candidate: null });
    };

    const toggleItem = (d: Extract<DrawState, { mode: "smart" }>, item: SmartItem) => {
      const exists = d.items.some((i) => i.key === item.key);
      const items = exists ? d.items.filter((i) => i.key !== item.key) : [...d.items, item];
      useStore.getState().setDraw({ ...d, items, candidate: exists ? item : null });
    };

    const onDown = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "smart" || e.originalEvent.button !== 0) return;
      e.preventDefault();
      pressRef.current = { x: e.point.x, y: e.point.y, dragged: false };
    };

    const onMove = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "smart" || d.status !== "ready") return;
      const item = featureAt(toLngLat(e));
      const press = pressRef.current;
      if (press) {
        if (!press.dragged && Math.hypot(e.point.x - press.x, e.point.y - press.y) >= DRAG_THRESHOLD_PX) press.dragged = true;
        if (press.dragged && item) addItem(d, item);
        return;
      }
      const cand = item ?? null;
      if ((cand?.key ?? null) !== (d.candidate?.key ?? null)) useStore.getState().setDraw({ ...d, candidate: cand });
      map.getCanvas().style.cursor = cand ? "pointer" : "crosshair";
    };

    const onUp = (e: MapMouseEvent) => {
      const d = drawRef.current;
      const press = pressRef.current;
      pressRef.current = null;
      if (d.mode !== "smart" || !press) return;
      if (d.status === "zoom") {
        useStore.getState().pushToast("info", "Zoom in closer to use smart select.");
        return;
      }
      if (d.status !== "ready") return;
      const item = featureAt(toLngLat(e));
      if (press.dragged) {
        if (item) addItem(d, item);
        return;
      }
      if (item) toggleItem(d, item);
      else useStore.getState().pushToast("info", "Nothing mapped here. Try the polygon or highlighter tool for this spot.");
    };

    const finish = () => {
      const d = drawRef.current;
      if (d.mode !== "smart") return;
      if (d.items.length === 0) {
        useStore.getState().pushToast("info", "Click a building, lot or road first.");
        return;
      }
      beginPrompt(map, { type: "smart", items: d.items });
    };

    const onKey = (e: KeyboardEvent) => {
      const st = useStore.getState();
      const d = st.draw;
      if (isTypingTarget(e.target)) return;
      if (d.mode === "smart") {
        if (e.key === "Enter") {
          e.preventDefault();
          finish();
        } else if (e.key === "Backspace") {
          e.preventDefault();
          st.setDraw({ ...d, items: d.items.slice(0, -1) });
        } else if (e.key === "Escape") {
          st.setDraw({ mode: "idle" });
          st.setTool("pan");
        }
        return;
      }
      if (d.mode === "idle" && (e.key === "s" || e.key === "S")) st.setTool("smart");
    };

    map.on("mousedown", onDown);
    map.on("mousemove", onMove);
    map.on("mouseup", onUp);
    window.addEventListener("keydown", onKey);
    return () => {
      map.off("mousedown", onDown);
      map.off("mousemove", onMove);
      map.off("mouseup", onUp);
      window.removeEventListener("keydown", onKey);
    };
  }, [map]);
}

/** Exposed for the toolbar's "Done" button. */
export function finishSmartSelect(map: MLMap) {
  const d = useStore.getState().draw;
  if (d.mode !== "smart") return;
  if (d.items.length === 0) {
    useStore.getState().pushToast("info", "Click a building, lot or road first.");
    return;
  }
  beginPrompt(map, { type: "smart", items: d.items });
}
