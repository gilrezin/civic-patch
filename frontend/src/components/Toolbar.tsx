import type { Map as MLMap } from "maplibre-gl";
import { finishHighlight } from "../map/useHighlight";
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

  const strokeCount = draw.mode === "highlighting" ? draw.strokes.length + (draw.current ? 1 : 0) : 0;

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
        title="Highlight areas to improve (H)"
        onClick={() => setTool(tool === "highlight" ? "pan" : "highlight")}
      >
        <IconHighlighter />
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
              Thickness
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
              aria-valuetext={`${widthPx} pixels`}
            />
            <span className="highlight-preview" aria-hidden="true">
              <span style={{ width: widthPx, height: widthPx }} />
            </span>
          </div>
          <div className="highlight-hint">
            {strokeCount === 0 ? "Drag on the map to highlight an area" : `${strokeCount} highlight${strokeCount === 1 ? "" : "s"} marked`}
            <span className="draw-hint-keys">Enter finish · Backspace undo · Esc cancel</span>
          </div>
          <button type="button" className="btn btn-primary btn-small" disabled={strokeCount === 0} onClick={() => finishHighlight(map)}>
            Done highlighting
          </button>
        </div>
      )}
    </div>
  );
}
