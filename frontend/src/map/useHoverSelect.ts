import { useEffect } from "react";
import type { Map as MLMap, MapLayerMouseEvent } from "maplibre-gl";
import { useStore } from "../state/store";
import { LAYER, SOURCE } from "./layers";
import { setPinHighlight } from "./pins";

export function useHoverSelect(map: MLMap | null) {
  const selectedId = useStore((s) => s.selectedId);

  useEffect(() => {
    if (!map) return;
    let hovered: number | null = null;

    const clearHover = () => {
      if (hovered !== null) {
        map.setFeatureState({ source: SOURCE.edits, id: hovered }, { hover: false });
        hovered = null;
        useStore.getState().setHovered(null);
      }
      if (useStore.getState().draw.mode === "idle") map.getCanvas().style.cursor = "";
    };

    const onMove = (e: MapLayerMouseEvent) => {
      if (useStore.getState().draw.mode !== "idle") return;
      const f = e.features?.[0];
      const id = typeof f?.id === "number" ? f.id : null;
      if (id === null || id < 0) return clearHover();
      if (id !== hovered) {
        if (hovered !== null) map.setFeatureState({ source: SOURCE.edits, id: hovered }, { hover: false });
        map.setFeatureState({ source: SOURCE.edits, id }, { hover: true });
        hovered = id;
        useStore.getState().setHovered(id);
      }
      map.getCanvas().style.cursor = "pointer";
    };

    const onClick = (e: MapLayerMouseEvent) => {
      if (useStore.getState().draw.mode !== "idle") return;
      const f = e.features?.[0];
      const id = typeof f?.id === "number" ? f.id : null;
      if (id === null || id < 0) return;
      useStore.getState().select(id);
    };

    map.on("mousemove", LAYER.editsFill, onMove);
    map.on("mouseleave", LAYER.editsFill, clearHover);
    map.on("click", LAYER.editsFill, onClick);
    return () => {
      map.off("mousemove", LAYER.editsFill, onMove);
      map.off("mouseleave", LAYER.editsFill, clearHover);
      map.off("click", LAYER.editsFill, onClick);
    };
  }, [map]);

  // Mirror the selected id into feature-state and pin highlight.
  useEffect(() => {
    if (!map) return;
    if (selectedId !== null) map.setFeatureState({ source: SOURCE.edits, id: selectedId }, { selected: true });
    setPinHighlight(selectedId);
    return () => {
      if (selectedId !== null && map.getSource(SOURCE.edits)) {
        map.setFeatureState({ source: SOURCE.edits, id: selectedId }, { selected: false });
      }
    };
  }, [map, selectedId]);
}
