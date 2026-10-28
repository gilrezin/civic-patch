import type { FeatureCollection } from "geojson";
import type { StyleSpecification } from "maplibre-gl";

export const ESRI_ATTRIBUTION =
  'Imagery &copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics, and the GIS User Community';

export const SOURCE = {
  satellite: "satellite",
  edits: "edits",
  draw: "draw",
} as const;

export const LAYER = {
  satellite: "satellite",
  editsFill: "edits-fill",
  editsLine: "edits-line",
  editsPendingLine: "edits-pending-line",
  drawFill: "draw-fill",
  drawLine: "draw-line",
  drawVertex: "draw-vertex",
  drawFirstVertex: "draw-first-vertex",
} as const;

export const ACCENT = "#ff7a00";

export const PHILADELPHIA: [number, number] = [-75.1652, 39.9526];
export const DEFAULT_ZOOM = 16;

const emptyFC = (): FeatureCollection => ({ type: "FeatureCollection", features: [] });

export function overlayLayerId(editId: number) {
  return `ov-${editId}`;
}

export function buildStyle(): StyleSpecification {
  return {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      [SOURCE.satellite]: {
        type: "raster",
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        tileSize: 256,
        maxzoom: 19,
        attribution: ESRI_ATTRIBUTION,
      },
      [SOURCE.edits]: { type: "geojson", data: emptyFC(), promoteId: "id" },
      [SOURCE.draw]: { type: "geojson", data: emptyFC() },
    },
    layers: [
      { id: LAYER.satellite, type: "raster", source: SOURCE.satellite },
      // Overlay raster layers are inserted here, before edits-fill.
      {
        id: LAYER.editsFill,
        type: "fill",
        source: SOURCE.edits,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": ACCENT,
          "fill-opacity": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            0.0,
            ["boolean", ["feature-state", "hover"], false],
            0.08,
            0.0,
          ],
        },
      },
      {
        id: LAYER.editsLine,
        type: "line",
        source: SOURCE.edits,
        filter: ["all", ["==", ["geometry-type"], "Polygon"], ["!=", ["get", "status"], "pending"]],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ACCENT,
          "line-width": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            3,
            ["boolean", ["feature-state", "hover"], false],
            2.5,
            0,
          ],
          "line-opacity": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            1,
            ["boolean", ["feature-state", "hover"], false],
            0.95,
            0,
          ],
        },
      },
      {
        id: LAYER.editsPendingLine,
        type: "line",
        source: SOURCE.edits,
        filter: ["all", ["==", ["geometry-type"], "Polygon"], ["==", ["get", "status"], "pending"]],
        layout: { "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": 0.9 },
      },
      {
        id: LAYER.drawFill,
        type: "fill",
        source: SOURCE.draw,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": ACCENT, "fill-opacity": 0.15 },
      },
      {
        id: LAYER.drawLine,
        type: "line",
        source: SOURCE.draw,
        filter: ["==", ["geometry-type"], "LineString"],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": ACCENT, "line-width": 2.5, "line-dasharray": [1, 1.5] },
      },
      {
        id: LAYER.drawVertex,
        type: "circle",
        source: SOURCE.draw,
        filter: ["all", ["==", ["geometry-type"], "Point"], ["!=", ["get", "first"], true]],
        paint: { "circle-radius": 4.5, "circle-color": "#ffffff", "circle-stroke-color": ACCENT, "circle-stroke-width": 2 },
      },
      {
        id: LAYER.drawFirstVertex,
        type: "circle",
        source: SOURCE.draw,
        filter: ["all", ["==", ["geometry-type"], "Point"], ["==", ["get", "first"], true]],
        paint: {
          "circle-radius": ["case", ["boolean", ["get", "snappable"], false], 8, 5],
          "circle-color": ["case", ["boolean", ["get", "snappable"], false], ACCENT, "#ffffff"],
          "circle-stroke-color": ["case", ["boolean", ["get", "snappable"], false], "#ffffff", ACCENT],
          "circle-stroke-width": 2,
        },
      },
    ],
  };
}
