import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { api } from "../api/client";
import { useStore } from "../state/store";
import { DEFAULT_ZOOM, PHILADELPHIA, buildStyle } from "./layers";
import { syncOverlays } from "./overlays";
import { syncPins } from "./pins";
import { useDrawPolygon } from "./useDrawPolygon";
import { useHighlight } from "./useHighlight";
import { useHoverSelect } from "./useHoverSelect";
import { useSmartSelect } from "./useSmartSelect";
import { PromptPopover } from "../components/PromptPopover";
import { Toolbar } from "../components/Toolbar";

export const PANEL_WIDTH = 420;

export function MapView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<MLMap | null>(null);

  const editsVersion = useStore((s) => s.editsVersion);
  const overlaysVisible = useStore((s) => s.overlaysVisible);
  const pinsVisible = useStore((s) => s.pinsVisible);
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

  // Keep the header's location button current: reverse-geocode the map centre after it settles,
  // skipping lookups that stay within ~100 m of the last one.
  useEffect(() => {
    if (!map) return;
    let timer: number | null = null;
    let lastKey = "";
    let seq = 0;
    const lookup = () => {
      const c = map.getCenter();
      const key = `${c.lng.toFixed(3)},${c.lat.toFixed(3)}`;
      if (key === lastKey) return;
      lastKey = key;
      const mine = ++seq;
      api
        .placesHere(c.lng, c.lat)
        .then((p) => {
          if (mine === seq) useStore.getState().setPlace(p);
        })
        .catch(() => {});
    };
    const onMoveEnd = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(lookup, 700);
    };
    lookup();
    map.on("moveend", onMoveEnd);
    return () => {
      if (timer !== null) window.clearTimeout(timer);
      map.off("moveend", onMoveEnd);
    };
  }, [map]);

  // Search results from the header ask the map to go somewhere.
  const flyTo = useStore((s) => s.flyTo);
  useEffect(() => {
    if (!map || !flyTo) return;
    if (flyTo.bbox) {
      const [w, s, e, n] = flyTo.bbox;
      const spanM = Math.max((e - w) * 111320 * Math.cos((flyTo.lat * Math.PI) / 180), (n - s) * 110540);
      if (spanM > 150) {
        map.fitBounds(
          [
            [w, s],
            [e, n],
          ],
          { padding: 60, maxZoom: 17, duration: 1200 },
        );
        return;
      }
    }
    map.flyTo({ center: [flyTo.lng, flyTo.lat], zoom: Math.max(map.getZoom(), 17), duration: 1200 });
  }, [map, flyTo]);

  // Warm the smart-select cells around the signed-in user's start area, once the map has
  // settled on it (after the geolocation jump, if any). Fire-and-forget.
  const user = useStore((s) => s.user);
  useEffect(() => {
    if (!map || !user) return;
    let done = false;
    const fire = () => {
      if (done) return;
      done = true;
      const c = map.getCenter();
      api.osmPrefetch(c.lng, c.lat).catch(() => {});
    };
    const timer = window.setTimeout(() => {
      if (map.isMoving()) map.once("idle", fire);
      else fire();
    }, 2500);
    return () => {
      window.clearTimeout(timer);
      done = true;
    };
  }, [map, user?.id]);

  useHoverSelect(map);
  useDrawPolygon(map);
  useHighlight(map);
  useSmartSelect(map);

  // Sync overlays, outlines and pins whenever relevant state changes.
  useEffect(() => {
    if (!map) return;
    const st = useStore.getState();
    const edits = Array.from(st.edits.values());
    const temps = Array.from(st.tempEdits.values());
    syncOverlays(map, edits, temps, { visible: overlaysVisible, viewOriginalId, preview, selectedId, hoveredId });
    syncPins(map, edits, temps, (id) => useStore.getState().select(id), pinsVisible);
  }, [map, editsVersion, overlaysVisible, pinsVisible, viewOriginalId, preview, selectedId, hoveredId]);

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
        padding: { top: 64 + 40, bottom: 40, left: 90, right: wide ? PANEL_WIDTH + 40 : 40 },
        maxZoom: 19,
        duration: 700,
      },
    );
  }, [map, fitRequest]);

  const mapStyle = useMemo(() => ({ position: "absolute" as const, inset: 0 }), []);

  return (
    <div className="map-wrap">
      <div ref={containerRef} style={mapStyle} />
      {map && <Toolbar map={map} />}
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
