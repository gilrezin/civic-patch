import type { Map as MLMap } from "maplibre-gl";
import { describeItems } from "../map/osmFeatures";
import { brushRadiiM } from "../map/quickSelect";
import { finishHighlight } from "../map/useHighlight";
import { finishSmartSelect } from "../map/useSmartSelect";
import { HIGHLIGHT_MAX_PX, HIGHLIGHT_MIN_PX, useStore } from "../state/store";
import {
  IconHand,
  IconHighlighter,
  IconLayers,
  IconLayersOff,
  IconLocate,
  IconMapPin,
  IconMapPinOff,
  IconPolygon,
  IconWand,
} from "./icons";

export function Toolbar({ map }: { map: MLMap }) {
  const tool = useStore((s) => s.tool);
  const setTool = useStore((s) => s.setTool);
  const overlaysVisible = useStore((s) => s.overlaysVisible);
  const toggleOverlays = useStore((s) => s.toggleOverlays);
  const pinsVisible = useStore((s) => s.pinsVisible);
  const togglePins = useStore((s) => s.togglePins);
  const requestLocate = useStore((s) => s.requestLocate);
  const draw = useStore((s) => s.draw);
  const widthPx = useStore((s) => s.highlightWidthPx);
  const setWidthPx = useStore((s) => s.setHighlightWidthPx);

  const strokeCount = draw.mode === "highlighting" ? draw.strokes : 0;
  const selectionEmpty = draw.mode === "highlighting" ? draw.empty : true;
  const radii = brushRadiiM(widthPx / HIGHLIGHT_MAX_PX);
  const fmtM = (m: number) => (m >= 10 ? `${Math.round(m)} m` : `${m.toFixed(1)} m`);

  return (
    <div className="toolbar" role="toolbar" aria-label="Map tools">
      <button
        type="button"
        className={`tool ${tool === "pan" ? "is-active" : ""}`}
        title="Pan and select (Esc)"
        onClick={() => setTool("pan")}
      >
        <IconHand />
      </button>
      <button
        type="button"
        className={`tool ${tool === "draw" ? "is-active" : ""}`}
        title="Draw an area to improve (D)"
        onClick={() => setTool(tool === "draw" ? "pan" : "draw")}
      >
        <IconPolygon />
      </button>
      <button
        type="button"
        className={`tool ${tool === "highlight" ? "is-active" : ""}`}
        title="Quick select: paint over a surface to select its colour (H)"
        onClick={() => setTool(tool === "highlight" ? "pan" : "highlight")}
      >
        <IconHighlighter />
      </button>
      <button
        type="button"
        className={`tool ${tool === "smart" ? "is-active" : ""}`}
        title="Smart select: click a building, lot or road (S)"
        onClick={() => setTool(tool === "smart" ? "pan" : "smart")}
      >
        <IconWand />
      </button>
      <div className="tool-sep" />
      <button
        type="button"
        className={`tool ${overlaysVisible ? "" : "is-off"}`}
        title={overlaysVisible ? "Hide edits" : "Show edits"}
        aria-pressed={!overlaysVisible}
        onClick={toggleOverlays}
      >
        {overlaysVisible ? <IconLayers /> : <IconLayersOff />}
      </button>
      <button
        type="button"
        className={`tool ${pinsVisible ? "" : "is-off"}`}
        title={pinsVisible ? "Hide pins" : "Show pins"}
        aria-pressed={!pinsVisible}
        onClick={togglePins}
      >
        {pinsVisible ? <IconMapPin /> : <IconMapPinOff />}
      </button>
      <button type="button" className="tool" title="Go to my location" onClick={requestLocate}>
        <IconLocate />
      </button>

      {draw.mode === "drawing" && (
        <div className="draw-hint" style={{ top: 6 }}>
          {draw.vertices.length === 0
            ? "Click on the map to start outlining an area"
            : draw.vertices.length < 3
              ? "Keep clicking to add corners"
              : "Click the first point or double-click to finish"}
          <span className="draw-hint-keys">Enter finish · Backspace undo · Esc cancel</span>
        </div>
      )}

      {tool === "highlight" && draw.mode === "highlighting" && (
        <div className="highlight-panel" style={{ top: 6 + 2 * 48 }}>
          <div className="highlight-row">
            <label className="highlight-label" htmlFor="highlight-width">
              Brush size
            </label>
            <input
              id="highlight-width"
              className="highlight-slider"
              type="range"
              min={HIGHLIGHT_MIN_PX}
              max={HIGHLIGHT_MAX_PX}
              step={1}
              value={widthPx}
              onChange={(e) => setWidthPx(Number(e.target.value))}
              aria-valuetext={`colour match ${fmtM(radii.colourM)}, solid fill ${fmtM(radii.solidM)}`}
            />
            <span className="highlight-preview" aria-hidden="true" title="Outer ring: colour match reach. Inner dot: fills any colour.">
              <span className="highlight-preview-outer" style={{ width: widthPx, height: widthPx }} />
              <span className="highlight-preview-inner" style={{ width: widthPx / 2, height: widthPx / 2 }} />
            </span>
          </div>
          <div className="highlight-radii muted small">
            Colour match up to {fmtM(radii.colourM)} · fills any colour within {fmtM(radii.solidM)}
          </div>
          <div className="highlight-hint">
            {selectionEmpty
              ? "Hold the mouse over a surface; the selection grows to similar colours"
              : `${strokeCount} stroke${strokeCount === 1 ? "" : "s"} · keep dragging to extend`}
            <span className="draw-hint-keys">Enter finish · Backspace undo · Esc cancel</span>
          </div>
          <button type="button" className="btn btn-primary btn-small" disabled={selectionEmpty} onClick={() => finishHighlight(map)}>
            Done highlighting
          </button>
        </div>
      )}

      {tool === "smart" && draw.mode === "smart" && (
        <div className="highlight-panel" style={{ top: 6 + 3 * 48 }}>
          <div className="highlight-hint">
            {draw.status === "zoom"
              ? "Zoom in closer to use smart select"
              : draw.status === "loading"
                ? "Loading map features…"
                : draw.status === "error"
                  ? "Map features unavailable right now"
                  : draw.items.length === 0
                    ? draw.candidate
                      ? `Click to select ${draw.candidate.label}`
                      : "Click a building, lot, park or road; drag across several"
                    : `Selected: ${describeItems(draw.items)}`}
            <span className="draw-hint-keys">
              {draw.candidate && draw.items.length > 0
                ? `${draw.candidate.label} · `
                : ""}
              Enter finish · Backspace undo · Esc cancel
            </span>
          </div>
          <button type="button" className="btn btn-primary btn-small" disabled={draw.items.length === 0} onClick={() => finishSmartSelect(map)}>
            Done selecting
          </button>
        </div>
      )}
    </div>
  );
}
