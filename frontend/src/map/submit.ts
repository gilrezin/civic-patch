import { ApiError, api } from "../api/client";
import { regionRing, smartRings, smartStrokes, toPolygon, type Region } from "../geo/polygon";
import { useStore } from "../state/store";

let tempSeq = -1;

/** Submit a finished region + prompt: optimistic pending feature, POST, then replace with the server edit. */
export async function submitNewEdit(region: Region, prompt: string): Promise<void> {
  const st = useStore.getState();
  const tempId = tempSeq--;
  let maskPayload = null;
  if (region.type === "mask") {
    maskPayload = await region.selection.export();
    if (!maskPayload) {
      st.pushToast("error", "The selection is empty.");
      st.setDraw({ mode: "idle" });
      st.setTool("pan");
      return;
    }
  }
  const polygon = toPolygon(regionRing(region));
  const temp: Parameters<typeof st.addTempEdit>[0] = { id: tempId, polygon, prompt };
  if (region.type === "highlight") temp.strokes = region.strokes;
  if (region.type === "smart") {
    temp.strokes = smartStrokes(region.items);
    temp.rings = smartRings(region.items);
  }
  st.addTempEdit(temp);
  st.setDraw({ mode: "submitting", region, tempId });
  try {
    const body =
      region.type === "polygon"
        ? { polygon }
        : region.type === "highlight"
          ? { highlight: { strokes: region.strokes.map((s) => ({ coordinates: s.coords, width_m: s.width_m })) } }
          : region.type === "mask"
            ? { mask: maskPayload! }
            : {
                smart: {
                  polygons: smartRings(region.items),
                  strokes: smartStrokes(region.items).map((s) => ({ coordinates: s.coords, width_m: s.width_m })),
                },
              };
    const edit = await api.createEdit(body, prompt);
    const s = useStore.getState();
    s.removeTempEdit(tempId);
    s.upsertEdit(edit);
    s.setDraw({ mode: "idle" });
    s.setTool("pan");
    s.select(edit.id, false);
    s.pushToast("success", "Your suggestion is on the map.");
  } catch (err) {
    const s = useStore.getState();
    s.removeTempEdit(tempId);
    s.setDraw({ mode: "idle" });
    s.setTool("pan");
    const message = err instanceof ApiError ? err.message : "Something went wrong generating that edit.";
    s.pushToast("error", message);
    if (err instanceof ApiError && err.status === 401) s.openAuthModal(true);
  }
}

export async function submitRefinement(editId: number, prompt: string): Promise<boolean> {
  const st = useStore.getState();
  st.markInFlight(editId, true);
  try {
    const edit = await api.refineEdit(editId, prompt);
    const s = useStore.getState();
    s.markInFlight(editId, false);
    s.upsertEdit(edit);
    s.setPreviewVersion(null);
    s.setViewOriginal(null);
    s.pushToast("success", "Refinement applied.");
    return true;
  } catch (err) {
    const s = useStore.getState();
    s.markInFlight(editId, false);
    const message = err instanceof ApiError ? err.message : "Something went wrong refining that edit.";
    s.pushToast("error", message);
    if (err instanceof ApiError && err.status === 401) s.openAuthModal(true);
    return false;
  }
}
