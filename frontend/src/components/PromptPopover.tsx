import { useEffect, useRef, useState } from "react";
import type { Map as MLMap } from "maplibre-gl";
import { submitNewEdit } from "../map/submit";
import { useStore } from "../state/store";
import { IconMic, IconPlus } from "./icons";

const WIDTH = 520;

export function PromptPopover({ map }: { map: MLMap }) {
  const draw = useStore((s) => s.draw);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const anchor = draw.mode === "prompting" ? draw.anchor : null;

  useEffect(() => {
    if (!anchor) {
      setPos(null);
      return;
    }
    const update = () => {
      const p = map.project(anchor);
      const rect = map.getContainer().getBoundingClientRect();
      const half = Math.min(WIDTH, rect.width - 24) / 2;
      const x = Math.max(12 + half, Math.min(rect.width - 12 - half, p.x));
      const y = Math.max(80, Math.min(rect.height - 40, p.y));
      setPos({ x, y });
    };
    update();
    map.on("move", update);
    return () => {
      map.off("move", update);
    };
  }, [map, anchor]);

  useEffect(() => {
    if (draw.mode === "prompting") {
      setText("");
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [draw.mode]);

  if (draw.mode !== "prompting" || !pos) return null;

  const submit = () => {
    const prompt = text.trim();
    if (prompt.length < 3) return;
    void submitNewEdit(draw.ring, prompt);
  };

  return (
    <div
      className="prompt-popover"
      style={{ left: pos.x, top: pos.y, width: Math.min(WIDTH, map.getContainer().clientWidth - 24) }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="prompt-box">
        <span className="prompt-icon" aria-hidden="true">
          <IconPlus />
        </span>
        <input
          ref={inputRef}
          className="prompt-input"
          placeholder="How should this area be improved?"
          value={text}
          maxLength={300}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              useStore.getState().setDraw({ mode: "idle" });
              useStore.getState().setTool("pan");
            }
          }}
        />
        <span className="prompt-icon prompt-icon-muted" aria-hidden="true" title="Voice input coming soon">
          <IconMic />
        </span>
      </div>
      <div className="prompt-hint">
        Press <kbd>Enter</kbd> to generate · <kbd>Esc</kbd> to cancel
      </div>
    </div>
  );
}
