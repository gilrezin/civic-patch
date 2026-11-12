import { useEffect, useRef } from "react";
import type { Map as MLMap, MapMouseEvent } from "maplibre-gl";
import { pointInRing, type LngLat, type SmartItem } from "../geo/polygon";
import { useStore, type DrawState } from "../state/store";
import { MAX_BLOCK_SEARCH_M } from "./blocks";
import { SMART_MIN_ZOOM, ensureAround, isReadyAround, smartHit, type SmartHit } from "./osmFeatures";
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

  // Load cells on demand around the cursor (and the map centre when it settles) instead of
  // fetching the whole viewport up front: one request in the common case, never a burst.
  useEffect(() => {
    if (!map || tool !== "smart") return;
    let lastErrorAt = 0;

    const loadAround = async (pt: LngLat) => {
      const d = useStore.getState().draw;
      if (d.mode !== "smart") return;
      if (map.getZoom() < SMART_MIN_ZOOM) {
        if (d.status !== "zoom") useStore.getState().setDraw({ ...d, status: "zoom" });
        return;
      }
      if (isReadyAround(pt)) {
        if (d.status !== "ready") useStore.getState().setDraw({ ...d, status: "ready" });
        return;
      }
      const seq = ++loadSeq.current;
      if (d.status !== "loading") useStore.getState().setDraw({ ...d, status: "loading" });
      try {
        await ensureAround(pt);
        const cur = useStore.getState().draw;
        if (seq === loadSeq.current && cur.mode === "smart") useStore.getState().setDraw({ ...cur, status: "ready" });
      } catch {
        const cur = useStore.getState().draw;
        if (seq === loadSeq.current && cur.mode === "smart") {
          useStore.getState().setDraw({ ...cur, status: "error" });
          if (Date.now() - lastErrorAt > 8000) {
            lastErrorAt = Date.now();
            useStore.getState().pushToast("error", "Map features could not be loaded. Try again in a moment.");
          }
        }
      }
    };

    const centre = () => {
      const c = map.getCenter();
      void loadAround([c.lng, c.lat]);
    };
    let throttle = 0;
    const onMove = (e: MapMouseEvent) => {
      const now = Date.now();
      if (now - throttle < 150) return;
      throttle = now;
      void loadAround([e.lngLat.lng, e.lngLat.lat]);
    };

    centre();
    map.on("moveend", centre);
    map.on("mousemove", onMove);
    return () => {
      map.off("moveend", centre);
      map.off("mousemove", onMove);
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

    /** An already-selected or hovered polygon containing the point, so blocks are not recomputed every move. */
    const containing = (d: Extract<DrawState, { mode: "smart" }>, pt: LngLat): SmartItem | null => {
      for (const i of d.items) if ("ring" in i && pointInRing(pt, i.ring)) return i;
      if (d.candidate && "ring" in d.candidate && pointInRing(pt, d.candidate.ring)) return d.candidate;
      return null;
    };

    /** Resolve what the point selects, reusing a containing polygon when there is one. */
    const resolve = (d: Extract<DrawState, { mode: "smart" }>, pt: LngLat): SmartHit => {
      const have = containing(d, pt);
      if (have) return { kind: "item", item: have };
      return smartHit(pt);
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
      const pt = toLngLat(e);
      const press = pressRef.current;
      if (press) {
        if (!press.dragged && Math.hypot(e.point.x - press.x, e.point.y - press.y) >= DRAG_THRESHOLD_PX) press.dragged = true;
        if (!press.dragged) return;
        // While dragging, skip points inside something already selected (cheap) before resolving.
        if (d.items.some((i) => "ring" in i && pointInRing(pt, i.ring))) return;
        const hit = smartHit(pt);
        if (hit.kind === "item") addItem(d, hit.item);
        return;
      }
      const hit = resolve(d, pt);
      const cand = hit.kind === "item" ? hit.item : null;
      if ((cand?.key ?? null) !== (d.candidate?.key ?? null)) useStore.getState().setDraw({ ...d, candidate: cand });
      map.getCanvas().style.cursor = cand ? "pointer" : hit.kind === "road" ? "not-allowed" : "crosshair";
    };

    const onUp = (e: MapMouseEvent) => {
      const d = drawRef.current;
      const press = pressRef.current;
      pressRef.current = null;
      if (d.mode !== "smart" || !press) return;
      const st = useStore.getState();
      if (d.status === "zoom") {
        st.pushToast("info", "Zoom in closer to use smart select.");
        return;
      }
      if (d.status !== "ready") return;
      const pt = toLngLat(e);
      const hit = resolve(d, pt);
      if (press.dragged) {
        if (hit.kind === "item") addItem(d, hit.item);
        return;
      }
      if (hit.kind === "item") {
        toggleItem(d, hit.item);
        if (hit.truncated) {
          st.pushToast("info", `No enclosing roads within ${MAX_BLOCK_SEARCH_M} m; the block was cut off at that distance.`);
        }
      } else if (hit.kind === "road") {
        st.pushToast("info", "Roads can't be selected. Click a building, lot or the open area between roads.");
      } else if (hit.kind === "empty") {
        st.pushToast("info", "No roads mapped nearby to bound a block. Try the polygon or highlighter tool here.");
      }
    };

    const finish = () => {
      const d = drawRef.current;
      if (d.mode !== "smart") return;
      if (d.items.length === 0) {
        useStore.getState().pushToast("info", "Click a building, lot or block first.");
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
    useStore.getState().pushToast("info", "Click a building, lot or block first.");
    return;
  }
  beginPrompt(map, { type: "smart", items: d.items });
}
