import { ApiError, api } from "../api/client";
import { toPolygon, type LngLat } from "../geo/polygon";
import { useStore } from "../state/store";

let tempSeq = -1;

/** Submit a drawn ring + prompt: optimistic pending feature, POST, then replace with the server edit. */
export async function submitNewEdit(ring: LngLat[], prompt: string): Promise<void> {
  const st = useStore.getState();
  const tempId = tempSeq--;
  const polygon = toPolygon(ring);
  st.addTempEdit({ id: tempId, polygon, prompt });
  st.setDraw({ mode: "submitting", ring, tempId });
  try {
    const edit = await api.createEdit(polygon, prompt);
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
