import { useStore } from "../state/store";
import { IconHand, IconLayers, IconLayersOff, IconLocate, IconMapPin, IconMapPinOff, IconPolygon } from "./icons";

export function Toolbar() {
  const tool = useStore((s) => s.tool);
  const setTool = useStore((s) => s.setTool);
  const overlaysVisible = useStore((s) => s.overlaysVisible);
  const toggleOverlays = useStore((s) => s.toggleOverlays);
  const pinsVisible = useStore((s) => s.pinsVisible);
  const togglePins = useStore((s) => s.togglePins);
  const requestLocate = useStore((s) => s.requestLocate);
  const draw = useStore((s) => s.draw);

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
        <div className="draw-hint">
          {draw.vertices.length === 0
            ? "Click on the map to start outlining an area"
            : draw.vertices.length < 3
              ? "Keep clicking to add corners"
              : "Click the first point or double-click to finish"}
          <span className="draw-hint-keys">Enter finish · Backspace undo · Esc cancel</span>
        </div>
      )}
    </div>
  );
}
