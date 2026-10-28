import { create } from "zustand";
import type { Polygon } from "geojson";
import { api, setAuthToken } from "../api/client";
import type { EditOut, UserOut } from "../api/types";
import type { LngLat } from "../geo/polygon";

export type Tool = "pan" | "draw";

export type DrawState =
  | { mode: "idle" }
  | { mode: "drawing"; vertices: LngLat[]; cursor: LngLat | null }
  | { mode: "prompting"; ring: LngLat[]; anchor: LngLat }
  | { mode: "submitting"; ring: LngLat[]; tempId: number };

export interface TempEdit {
  id: number; // negative
  polygon: Polygon;
  prompt: string;
}

export interface Toast {
  id: number;
  kind: "error" | "info" | "success";
  message: string;
}

const TOKEN_KEY = "civic-patch.token";

interface State {
  user: UserOut | null;
  token: string | null;
  authModalOpen: boolean;

  edits: Map<number, EditOut>;
  editsVersion: number; // bumps whenever `edits` changes, for cheap subscriptions
  tempEdits: Map<number, TempEdit>;
  inFlight: Set<number>; // edit ids being refined by this client

  selectedId: number | null;
  hoveredId: number | null;
  viewOriginalId: number | null;
  previewVersionUrl: { editId: number; url: string } | null;
  overlaysVisible: boolean;
  tool: Tool;
  draw: DrawState;
  locateRequest: number;
  fitRequest: { editId: number; nonce: number } | null;

  toasts: Toast[];

  // auth
  setAuth: (auth: { token: string; user: UserOut } | null) => void;
  openAuthModal: (open: boolean) => void;
  restoreSession: () => Promise<void>;

  // edits
  setEdits: (list: EditOut[]) => void;
  upsertEdit: (edit: EditOut) => void;
  addTempEdit: (t: TempEdit) => void;
  removeTempEdit: (id: number) => void;
  markInFlight: (id: number, on: boolean) => void;

  // ui
  select: (id: number | null, fit?: boolean) => void;
  setHovered: (id: number | null) => void;
  setViewOriginal: (id: number | null) => void;
  setPreviewVersion: (p: { editId: number; url: string } | null) => void;
  toggleOverlays: () => void;
  setTool: (tool: Tool) => void;
  setDraw: (draw: DrawState) => void;
  requestLocate: () => void;

  pushToast: (kind: Toast["kind"], message: string) => void;
  dismissToast: (id: number) => void;
}

let toastSeq = 1;

export const useStore = create<State>((set, get) => ({
  user: null,
  token: null,
  authModalOpen: false,

  edits: new Map(),
  editsVersion: 0,
  tempEdits: new Map(),
  inFlight: new Set(),

  selectedId: null,
  hoveredId: null,
  viewOriginalId: null,
  previewVersionUrl: null,
  overlaysVisible: true,
  tool: "pan",
  draw: { mode: "idle" },
  locateRequest: 0,
  fitRequest: null,

  toasts: [],

  setAuth: (auth) => {
    if (auth) {
      localStorage.setItem(TOKEN_KEY, auth.token);
      setAuthToken(auth.token);
      set({ token: auth.token, user: auth.user, authModalOpen: false });
    } else {
      localStorage.removeItem(TOKEN_KEY);
      setAuthToken(null);
      set({ token: null, user: null });
    }
  },
  openAuthModal: (open) => set({ authModalOpen: open }),
  restoreSession: async () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return;
    setAuthToken(token);
    try {
      const user = await api.me();
      set({ token, user });
    } catch {
      localStorage.removeItem(TOKEN_KEY);
      setAuthToken(null);
    }
  },

  setEdits: (list) => {
    const next = new Map<number, EditOut>();
    const { inFlight, edits: prev } = get();
    for (const e of list) {
      // Keep the locally in-flight edit's own view until the refine resolves.
      next.set(e.id, inFlight.has(e.id) && prev.has(e.id) ? prev.get(e.id)! : e);
    }
    set({ edits: next, editsVersion: get().editsVersion + 1 });
  },
  upsertEdit: (edit) => {
    const next = new Map(get().edits);
    next.set(edit.id, edit);
    set({ edits: next, editsVersion: get().editsVersion + 1 });
  },
  addTempEdit: (t) => {
    const next = new Map(get().tempEdits);
    next.set(t.id, t);
    set({ tempEdits: next, editsVersion: get().editsVersion + 1 });
  },
  removeTempEdit: (id) => {
    const next = new Map(get().tempEdits);
    next.delete(id);
    set({ tempEdits: next, editsVersion: get().editsVersion + 1 });
  },
  markInFlight: (id, on) => {
    const next = new Set(get().inFlight);
    if (on) next.add(id);
    else next.delete(id);
    set({ inFlight: next });
  },

  select: (id, fit = true) =>
    set({
      selectedId: id,
      viewOriginalId: null,
      previewVersionUrl: null,
      fitRequest: id !== null && fit ? { editId: id, nonce: Date.now() } : null,
    }),
  setHovered: (id) => set({ hoveredId: id }),
  setViewOriginal: (id) => set({ viewOriginalId: id }),
  setPreviewVersion: (p) => set({ previewVersionUrl: p }),
  toggleOverlays: () => set({ overlaysVisible: !get().overlaysVisible }),
  setTool: (tool) => set({ tool }),
  setDraw: (draw) => set({ draw }),
  requestLocate: () => set({ locateRequest: get().locateRequest + 1 }),

  pushToast: (kind, message) => {
    const id = toastSeq++;
    set({ toasts: [...get().toasts, { id, kind, message }] });
    setTimeout(() => get().dismissToast(id), kind === "error" ? 7000 : 4000);
  },
  dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));
