import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useStore } from "../state/store";
import { DEFAULT_ZOOM, PHILADELPHIA, buildStyle } from "./layers";
import { syncOverlays } from "./overlays";
import { syncPins } from "./pins";
import { useDrawPolygon } from "./useDrawPolygon";
import { useHoverSelect } from "./useHoverSelect";
import { PromptPopover } from "../components/PromptPopover";
import { Toolbar } from "../components/Toolbar";

export const PANEL_WIDTH = 420;

export function MapView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<MLMap | null>(null);

  const editsVersion = useStore((s) => s.editsVersion);
  const overlaysVisible = useStore((s) => s.overlaysVisible);
  const viewOriginalId = useStore((s) => s.viewOriginalId);
  const preview = useStore((s) => s.previewVersionUrl);
  const selectedId = useStore((s) => s.selectedId);
  const hoveredId = useStore((s) => s.hoveredId);
  const fitRequest = useStore((s) => s.fitRequest);
  const locateRequest = useStore((s) => s.locateRequest);

  // Create the map once.
  useEffect(() => {
    if (!containerRef.current) return;
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle(),
      center: PHILADELPHIA,
      zoom: DEFAULT_ZOOM,
      maxZoom: 20,
      attributionControl: { compact: true },
      doubleClickZoom: true,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    m.on("load", () => setMap(m));
    return () => {
      m.remove();
      setMap(null);
    };
  }, []);

  // Start view: ask for the user's location once; fall back to Philadelphia silently.
  useEffect(() => {
    if (!map) return;
    locate(map, false);
  }, [map]);

  useEffect(() => {
    if (!map || locateRequest === 0) return;
    locate(map, true);
  }, [map, locateRequest]);

  useHoverSelect(map);
  useDrawPolygon(map);

  // Sync overlays, outlines and pins whenever relevant state changes.
  useEffect(() => {
    if (!map) return;
    const st = useStore.getState();
    const edits = Array.from(st.edits.values());
    const temps = Array.from(st.tempEdits.values());
    syncOverlays(map, edits, temps, { visible: overlaysVisible, viewOriginalId, preview, selectedId, hoveredId });
    syncPins(map, edits, temps, (id) => useStore.getState().select(id), overlaysVisible);
  }, [map, editsVersion, overlaysVisible, viewOriginalId, preview, selectedId, hoveredId]);

  // Fit the map to a selected edit, leaving room for the side panel.
  useEffect(() => {
    if (!map || !fitRequest) return;
    const edit = useStore.getState().edits.get(fitRequest.editId);
    if (!edit) return;
    const [w, s, e, n] = edit.bounds;
    const wide = window.innerWidth > 900;
    map.fitBounds(
      [
        [w, s],
        [e, n],
      ],
      {
        padding: { top: 90, bottom: 40, left: 90, right: wide ? PANEL_WIDTH + 40 : 40 },
        maxZoom: 19,
        duration: 700,
      },
    );
  }, [map, fitRequest]);

  const mapStyle = useMemo(() => ({ position: "absolute" as const, inset: 0 }), []);

  return (
    <div className="map-wrap">
      <div ref={containerRef} style={mapStyle} />
      {map && <Toolbar />}
      {map && <PromptPopover map={map} />}
    </div>
  );
}

function locate(map: MLMap, announce: boolean) {
  const st = useStore.getState();
  if (!("geolocation" in navigator)) {
    if (announce) st.pushToast("error", "Location is not available in this browser.");
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      map.easeTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: Math.max(map.getZoom(), 16), duration: 900 });
    },
    () => {
      if (announce) st.pushToast("info", "Location was unavailable. Showing Center City Philadelphia.");
    },
    { enableHighAccuracy: false, timeout: 6000, maximumAge: 300_000 },
  );
}
