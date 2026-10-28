import type { Feature, FeatureCollection, Polygon } from "geojson";
import type { GeoJSONSource, ImageSource, Map as MLMap } from "maplibre-gl";
import type { EditOut } from "../api/types";
import type { TempEdit } from "../state/store";
import { LAYER, SOURCE, overlayLayerId } from "./layers";

interface Tracked {
  url: string;
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
  token: number;
}

const tracked = new Map<number, Tracked>();
let tokenSeq = 1;

export interface OverlayOptions {
  visible: boolean;
  viewOriginalId: number | null;
  preview: { editId: number; url: string } | null;
  selectedId: number | null;
  hoveredId: number | null;
}

function cornersOf(e: EditOut): Tracked["coordinates"] {
  const [w, s, en, n] = e.bounds;
  return [
    [w, n],
    [en, n],
    [en, s],
    [w, s],
  ];
}

function preload(url: string): Promise<void> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve();
    img.onerror = () => resolve();
    img.src = url;
  });
}

export function syncOverlays(map: MLMap, edits: EditOut[], temps: TempEdit[], opts: OverlayOptions) {
  const seen = new Set<number>();

  for (const e of edits) {
    const url = opts.preview?.editId === e.id ? opts.preview.url : e.current_version?.overlay_url ?? null;
    if (!url) continue;
    seen.add(e.id);
    const id = overlayLayerId(e.id);
    const coordinates = cornersOf(e);
    const existing = tracked.get(e.id);

    if (!existing) {
      const token = tokenSeq++;
      tracked.set(e.id, { url, coordinates, token });
      if (!map.getSource(id)) {
        map.addSource(id, { type: "image", url, coordinates });
        map.addLayer(
          {
            id,
            type: "raster",
            source: id,
            paint: { "raster-opacity": 1, "raster-fade-duration": 0, "raster-resampling": "linear" },
          },
          LAYER.editsFill,
        );
      }
    } else if (existing.url !== url) {
      const token = tokenSeq++;
      existing.token = token;
      existing.url = url;
      existing.coordinates = coordinates;
      void preload(url).then(() => {
        const cur = tracked.get(e.id);
        if (!cur || cur.token !== token) return;
        const src = map.getSource(id) as ImageSource | undefined;
        src?.updateImage({ url, coordinates });
      });
    }

    const show = opts.visible && opts.viewOriginalId !== e.id;
    if (map.getLayer(id)) {
      map.setLayoutProperty(id, "visibility", show ? "visible" : "none");
    }
  }

  for (const id of Array.from(tracked.keys())) {
    if (!seen.has(id)) {
      tracked.delete(id);
      const lid = overlayLayerId(id);
      if (map.getLayer(lid)) map.removeLayer(lid);
      if (map.getSource(lid)) map.removeSource(lid);
    }
  }

  const features: Feature<Polygon>[] = [];
  for (const e of edits) {
    features.push({ type: "Feature", id: e.id, geometry: e.polygon, properties: { id: e.id, status: e.status } });
  }
  for (const t of temps) {
    features.push({ type: "Feature", id: t.id, geometry: t.polygon, properties: { id: t.id, status: "pending" } });
  }
  const fc: FeatureCollection<Polygon> = { type: "FeatureCollection", features };
  (map.getSource(SOURCE.edits) as GeoJSONSource | undefined)?.setData(fc);

  // Re-apply interaction state defensively after setData.
  if (opts.selectedId !== null) map.setFeatureState({ source: SOURCE.edits, id: opts.selectedId }, { selected: true });
  if (opts.hoveredId !== null) map.setFeatureState({ source: SOURCE.edits, id: opts.hoveredId }, { hover: true });
}

export function resetOverlayTracking() {
  tracked.clear();
}
