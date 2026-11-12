import type { FeatureCollection } from "geojson";
import type { ExpressionSpecification, StyleSpecification } from "maplibre-gl";

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
  editsHlHit: "edits-hl-hit",
  editsHlLine: "edits-hl-line",
  editsHlPending: "edits-hl-pending",
  drawFill: "draw-fill",
  drawLine: "draw-line",
  drawHighlight: "draw-highlight",
  drawVertex: "draw-vertex",
  drawFirstVertex: "draw-first-vertex",
} as const;

/** Layers whose features can be hovered/clicked to select an edit. */
export const HIT_LAYERS = [LAYER.editsFill, LAYER.editsHlHit] as const;

export const ACCENT = "#ff7a00";

export const PHILADELPHIA: [number, number] = [-75.1652, 39.9526];
export const DEFAULT_ZOOM = 16;

const emptyFC = (): FeatureCollection => ({ type: "FeatureCollection", features: [] });

/**
 * Stroke width in screen pixels for a feature carrying w0/w24 (pixels at zoom 0 and 24).
 * Exponential base-2 interpolation reproduces the exact Web Mercator scale at every zoom,
 * so a highlight stays glued to the same ground area as the user zooms.
 */
export const STROKE_WIDTH_EXPR: ExpressionSpecification = [
  "interpolate",
  ["exponential", 2],
  ["zoom"],
  0,
  ["get", "w0"],
  24,
  ["get", "w24"],
];

const IS_HIGHLIGHT: ExpressionSpecification = ["==", ["get", "kind"], "highlight"];
const IS_POLYGON: ExpressionSpecification = ["==", ["geometry-type"], "Polygon"];

const hoverSelectedCase = (selected: number, hover: number, none: number): ExpressionSpecification => [
  "case",
  ["boolean", ["feature-state", "selected"], false],
  selected,
  ["boolean", ["feature-state", "hover"], false],
  hover,
  none,
];

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
        filter: IS_POLYGON,
        paint: { "fill-color": ACCENT, "fill-opacity": hoverSelectedCase(0, 0.08, 0) },
      },
      {
        id: LAYER.editsLine,
        type: "line",
        source: SOURCE.edits,
        filter: ["all", IS_POLYGON, ["!=", ["get", "status"], "pending"]],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ACCENT,
          "line-width": hoverSelectedCase(3, 2.5, 0),
          "line-opacity": hoverSelectedCase(1, 0.95, 0),
        },
      },
      {
        id: LAYER.editsPendingLine,
        type: "line",
        source: SOURCE.edits,
        filter: ["all", IS_POLYGON, ["==", ["get", "status"], "pending"]],
        layout: { "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": 0.9 },
      },
      // Highlight edits: an invisible full-width hit area, an outline drawn either side of
      // the stroke (gap-width trick), and a dashed pending variant.
      {
        id: LAYER.editsHlHit,
        type: "line",
        source: SOURCE.edits,
        filter: IS_HIGHLIGHT,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": ACCENT, "line-width": STROKE_WIDTH_EXPR, "line-opacity": hoverSelectedCase(0, 0.1, 0) },
      },
      {
        id: LAYER.editsHlLine,
        type: "line",
        source: SOURCE.edits,
        filter: ["all", IS_HIGHLIGHT, ["!=", ["get", "status"], "pending"]],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ACCENT,
          "line-gap-width": STROKE_WIDTH_EXPR,
          "line-width": hoverSelectedCase(3, 2.5, 0),
          "line-opacity": hoverSelectedCase(1, 0.95, 0),
        },
      },
      {
        id: LAYER.editsHlPending,
        type: "line",
        source: SOURCE.edits,
        filter: ["all", IS_HIGHLIGHT, ["==", ["get", "status"], "pending"]],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#ffffff",
          "line-gap-width": STROKE_WIDTH_EXPR,
          "line-width": 2,
          "line-dasharray": [2, 2],
          "line-opacity": 0.9,
        },
      },
      {
        id: LAYER.drawFill,
        type: "fill",
        source: SOURCE.draw,
        filter: IS_POLYGON,
        paint: { "fill-color": ACCENT, "fill-opacity": 0.15 },
      },
      {
        id: LAYER.drawLine,
        type: "line",
        source: SOURCE.draw,
        filter: ["all", ["==", ["geometry-type"], "LineString"], ["!=", ["get", "kind"], "highlight"]],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ["case", ["boolean", ["get", "candidate"], false], "#ffffff", ACCENT],
          "line-width": ["case", ["boolean", ["get", "candidate"], false], 2, 2.5],
          "line-dasharray": [1, 1.5],
        },
      },
      {
        id: LAYER.drawHighlight,
        type: "line",
        source: SOURCE.draw,
        filter: IS_HIGHLIGHT,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": ACCENT, "line-width": STROKE_WIDTH_EXPR, "line-opacity": 0.55 },
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
