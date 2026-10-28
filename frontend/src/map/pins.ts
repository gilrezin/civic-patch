import maplibregl, { type Map as MLMap } from "maplibre-gl";
import type { EditOut } from "../api/types";
import { centroidOf, ringOf } from "../geo/polygon";
import type { TempEdit } from "../state/store";

interface PinEntry {
  marker: maplibregl.Marker;
  kind: "pin" | "spinner";
}

const pins = new Map<number, PinEntry>();

const PIN_SVG = `
<svg width="28" height="36" viewBox="0 0 28 36" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M14 35C14 35 26 22.5 26 13.5C26 6.6 20.6 1 14 1C7.4 1 2 6.6 2 13.5C2 22.5 14 35 14 35Z" fill="#ff7a00" stroke="#ffffff" stroke-width="2"/>
  <circle cx="14" cy="13.5" r="4.5" fill="#ffffff"/>
</svg>`;

function makePin(onClick: () => void): HTMLElement {
  const el = document.createElement("button");
  el.className = "edit-pin";
  el.type = "button";
  el.title = "View this suggestion";
  el.innerHTML = PIN_SVG;
  el.addEventListener("click", (ev) => {
    ev.stopPropagation();
    onClick();
  });
  return el;
}

function makeSpinner(): HTMLElement {
  const el = document.createElement("div");
  el.className = "edit-spinner";
  el.innerHTML = `<div class="edit-spinner-ring"></div><span>Generating…</span>`;
  return el;
}

export function syncPins(map: MLMap, edits: EditOut[], temps: TempEdit[], onClick: (id: number) => void, visible: boolean) {
  const seen = new Set<number>();

  const place = (id: number, kind: PinEntry["kind"], lngLat: [number, number]) => {
    seen.add(id);
    const existing = pins.get(id);
    if (existing && existing.kind === kind) {
      existing.marker.setLngLat(lngLat);
      existing.marker.getElement().style.display = visible ? "" : "none";
      return;
    }
    existing?.marker.remove();
    const el = kind === "pin" ? makePin(() => onClick(id)) : makeSpinner();
    const marker = new maplibregl.Marker({ element: el, anchor: kind === "pin" ? "bottom" : "center" })
      .setLngLat(lngLat)
      .addTo(map);
    el.style.display = visible ? "" : "none";
    pins.set(id, { marker, kind });
  };

  for (const e of edits) {
    const c = centroidOf(ringOf(e.polygon));
    place(e.id, e.status === "pending" ? "spinner" : "pin", c);
  }
  for (const t of temps) {
    place(t.id, "spinner", centroidOf(ringOf(t.polygon)));
  }

  for (const [id, entry] of Array.from(pins.entries())) {
    if (!seen.has(id)) {
      entry.marker.remove();
      pins.delete(id);
    }
  }
}

export function setPinHighlight(id: number | null) {
  for (const [pid, entry] of pins) {
    entry.marker.getElement().classList.toggle("is-active", pid === id);
  }
}
