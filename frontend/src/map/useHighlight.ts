import { useEffect, useRef } from "react";
import type { Map as MLMap, MapMouseEvent } from "maplibre-gl";
import { HIGHLIGHT_MAX_PX, useStore, type DrawState } from "../state/store";
import { QuickSelection, brushRadiiM, metersPerTilePixel, workingZoom, worldPx } from "./quickSelect";
import { beginPrompt, isTypingTarget } from "./useDrawPolygon";

/**
 * Highlighter = quick selection. Holding the mouse grows a selection over pixels whose
 * colour matches what is under the brush, up to MAX_SPREAD_M from the cursor per step.
 * Enter finishes and opens the prompt box; Backspace removes the last stroke; Esc cancels.
 */
export function useHighlight(map: MLMap | null) {
  const tool = useStore((s) => s.tool);
  const draw = useStore((s) => s.draw);
  const drawRef = useRef<DrawState>(draw);
  drawRef.current = draw;
  const selRef = useRef<QuickSelection | null>(null);
  const paintingRef = useRef(false);

  const syncState = () => {
    const d = useStore.getState().draw;
    const sel = selRef.current;
    if (d.mode !== "highlighting" || !sel) return;
    const empty = sel.isEmpty;
    if (d.strokes !== sel.strokeCount || d.empty !== empty) {
      useStore.getState().setDraw({ ...d, strokes: sel.strokeCount, empty });
    }
  };

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
      if (st.draw.mode === "idle" || st.draw.mode === "drawing" || st.draw.mode === "smart") {
        const sel = new QuickSelection(workingZoom(map.getZoom()));
        sel.attach(map);
        sel.onChange = syncState;
        selRef.current = sel;
        st.setDraw({ mode: "highlighting", strokes: 0, empty: true, selection: sel });
      }
      map.dragPan.disable();
      map.doubleClickZoom.disable();
      map.getCanvas().style.cursor = "crosshair";
    } else {
      if (st.draw.mode === "highlighting") st.setDraw({ mode: "idle" });
      paintingRef.current = false;
      if (tool !== "smart") map.dragPan.enable();
      if (tool === "pan") {
        map.doubleClickZoom.enable();
        map.getCanvas().style.cursor = "";
      }
    }
  }, [map, tool]);

  // Drop the preview raster once the selection is no longer part of the flow.
  useEffect(() => {
    if (!map) return;
    const live =
      draw.mode === "highlighting" ||
      ((draw.mode === "prompting" || draw.mode === "submitting") && draw.region.type === "mask");
    if (!live && selRef.current) {
      selRef.current.detach();
      selRef.current = null;
    }
  }, [map, draw]);

  useEffect(() => {
    if (!map) return;

    /** Both radii in tile pixels: the slider scales the colour reach, the solid disc is half of it. */
    const brushAndSpread = (lat: number) => {
      const sel = selRef.current!;
      const st = useStore.getState();
      const mppTile = metersPerTilePixel(lat, sel.zoom);
      const { colourM, solidM } = brushRadiiM(st.highlightWidthPx / HIGHLIGHT_MAX_PX);
      return { brushPx: Math.max(1, solidM / mppTile), spreadPx: Math.max(2, colourM / mppTile) };
    };

    const paint = (e: MapMouseEvent) => {
      const sel = selRef.current;
      if (!sel) return;
      const [x, y] = worldPx(e.lngLat.lng, e.lngLat.lat, sel.zoom);
      const { brushPx, spreadPx } = brushAndSpread(e.lngLat.lat);
      sel.stroke(x, y, brushPx, spreadPx);
    };

    const onDown = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "highlighting" || e.originalEvent.button !== 0 || !selRef.current) return;
      e.preventDefault();
      paintingRef.current = true;
      selRef.current.beginStroke();
      paint(e);
      syncState();
    };

    const onMove = (e: MapMouseEvent) => {
      const d = drawRef.current;
      if (d.mode !== "highlighting" || !selRef.current) return;
      if (paintingRef.current) {
        paint(e);
        return;
      }
      // Warm the tiles around the cursor so the first stroke has pixels to read.
      const sel = selRef.current;
      const [x, y] = worldPx(e.lngLat.lng, e.lngLat.lat, sel.zoom);
      const { brushPx, spreadPx } = brushAndSpread(e.lngLat.lat);
      sel.prefetch(x, y, spreadPx + brushPx);
    };

    const endStroke = () => {
      if (!paintingRef.current) return;
      paintingRef.current = false;
      selRef.current?.endStroke();
      syncState();
    };

    const finish = () => {
      const d = drawRef.current;
      const sel = selRef.current;
      if (d.mode !== "highlighting" || !sel) return;
      if (sel.isEmpty) {
        useStore.getState().pushToast("info", "Hold the mouse over a surface to select it first.");
        return;
      }
      paintingRef.current = false;
      beginPrompt(map, { type: "mask", selection: sel });
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
          selRef.current?.undoStroke();
          syncState();
        } else if (e.key === "Escape") {
          st.setDraw({ mode: "idle" });
          st.setTool("pan");
        }
        return;
      }
      if (d.mode === "idle" && (e.key === "h" || e.key === "H")) st.setTool("highlight");
    };

    const container = map.getCanvasContainer();
    map.on("mousedown", onDown);
    map.on("mousemove", onMove);
    map.on("mouseup", endStroke);
    container.addEventListener("mouseleave", endStroke);
    window.addEventListener("keydown", onKey);
    return () => {
      map.off("mousedown", onDown);
      map.off("mousemove", onMove);
      map.off("mouseup", endStroke);
      container.removeEventListener("mouseleave", endStroke);
      window.removeEventListener("keydown", onKey);
    };
  }, [map]);
}

/** Exposed for the toolbar's "Done" button. */
export function finishHighlight(map: MLMap) {
  const d = useStore.getState().draw;
  if (d.mode !== "highlighting") return;
  if (d.selection.isEmpty) {
    useStore.getState().pushToast("info", "Hold the mouse over a surface to select it first.");
    return;
  }
  beginPrompt(map, { type: "mask", selection: d.selection });
}
