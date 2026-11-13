import { useEffect, useRef, useState } from "react";
import { Viewer } from "@photo-sphere-viewer/core";
import "@photo-sphere-viewer/core/index.css";
import { ApiError, api } from "../api/client";
import type { StreetViewOut } from "../api/types";
import { useStore } from "../state/store";
import { IconClose, IconEye } from "./icons";

type Phase = "loading" | "idle" | "generating" | "ready" | "error";

const PROGRESS: [number, string][] = [
  [0, "Finding the nearest Street View…"],
  [4000, "Stitching the panorama…"],
  [10000, "Reimagining it from the ground…"],
  [60000, "Still working — this can take up to two minutes…"],
];

const POLL_MS = 5000;
const POLL_MAX = 30;

function monthLabel(iso: string | null): string | null {
  if (!iso) return null;
  const [y, m] = iso.split("-").map(Number);
  if (!y || !m) return iso;
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
}

export default function StreetViewModal() {
  const editId = useStore((s) => s.streetViewEditId);
  const edit = useStore((s) => (editId === null ? undefined : s.edits.get(editId)));
  const user = useStore((s) => s.user);
  const openStreetView = useStore((s) => s.openStreetView);

  const [phase, setPhase] = useState<Phase>("loading");
  const [sv, setSv] = useState<StreetViewOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showOriginal, setShowOriginal] = useState(false);
  const [progress, setProgress] = useState(PROGRESS[0][1]);
  const seq = useRef(0);

  // Load whatever has already been rendered for this edit.
  useEffect(() => {
    if (editId === null) return;
    const my = ++seq.current;
    setPhase("loading");
    setSv(null);
    setError(null);
    setShowOriginal(false);
    api
      .getStreetView(editId)
      .then((r) => {
        if (seq.current !== my) return;
        setSv(r);
        setPhase("ready");
      })
      .catch((err) => {
        if (seq.current !== my) return;
        if (err instanceof ApiError && err.code === "not_generated") setPhase("idle");
        else {
          setError(err instanceof ApiError ? err.message : "Could not load the street view.");
          setPhase("error");
        }
      });
  }, [editId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // In fullscreen the viewer owns Escape (the browser exits fullscreen first).
      if (e.key === "Escape" && !document.fullscreenElement) openStreetView(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [openStreetView]);

  useEffect(() => {
    if (phase !== "generating") return;
    setProgress(PROGRESS[0][1]);
    const timers = PROGRESS.slice(1).map(([ms, text]) => setTimeout(() => setProgress(text), ms));
    return () => timers.forEach(clearTimeout);
  }, [phase]);

  if (editId === null || !edit) return null;

  const currentVersionId = edit.current_version?.id ?? null;
  const stale = sv !== null && currentVersionId !== null && sv.version_id !== currentVersionId;
  const close = () => openStreetView(null);

  const pollUntilReady = async (my: number) => {
    for (let i = 0; i < POLL_MAX; i++) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      if (seq.current !== my) return;
      try {
        const r = await api.getStreetView(editId);
        if (seq.current !== my) return;
        if (r.version_id === currentVersionId || currentVersionId === null) {
          setSv(r);
          setShowOriginal(false);
          setPhase("ready");
          return;
        }
      } catch {
        /* not ready yet */
      }
    }
    if (seq.current !== my) return;
    setError("The street view is still being generated. Try again in a moment.");
    setPhase("error");
  };

  const generate = async () => {
    if (!user) {
      useStore.getState().openAuthModal(true);
      return;
    }
    const my = ++seq.current;
    setPhase("generating");
    setError(null);
    try {
      const r = await api.generateStreetView(editId);
      if (seq.current !== my) return;
      setSv(r);
      setShowOriginal(false);
      setPhase("ready");
    } catch (err) {
      if (seq.current !== my) return;
      if (err instanceof ApiError && err.status === 401) {
        useStore.getState().openAuthModal(true);
        setPhase(sv ? "ready" : "idle");
        return;
      }
      if (err instanceof ApiError && (err.code === "in_progress" || err.code === "timeout")) {
        void pollUntilReady(my);
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not generate the street view.");
      setPhase("error");
    }
  };

  const meta: string[] = [];
  if (sv) {
    const when = monthLabel(sv.pano_date);
    meta.push(when ? `Street View from ${when}` : "Street View");
    meta.push(`${Math.max(1, Math.round(sv.distance_m))} m from the site`);
  }
  meta.push("Imagery © Google");

  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <div className="modal sv-modal" role="dialog" aria-label="Street view" onMouseDown={(e) => e.stopPropagation()}>
        <button type="button" className="modal-close" onClick={close} aria-label="Close">
          <IconClose />
        </button>

        <div className="sv-head">
          <h2 className="sv-title">Street view</h2>
          <div className="sv-sub muted">
            {edit.original_prompt}
            {edit.place_name ? ` · ${edit.place_name}` : ""}
          </div>
        </div>

        <div className="sv-stage">
          {phase === "ready" && sv && <PanoViewer src={showOriginal ? sv.original_url : sv.edited_url} />}

          {phase === "loading" && (
            <div className="sv-status">
              <span className="edit-spinner-ring" aria-hidden="true" />
              Checking for a street view…
            </div>
          )}

          {phase === "idle" && (
            <div className="sv-status sv-cta">
              <IconEye width={28} height={28} />
              <p>
                See this proposal from the ground. We find the nearest Street View, stitch a full 360° panorama and ask the
                AI to apply the same change to it.
              </p>
              <button type="button" className="btn btn-primary" onClick={() => void generate()}>
                {user ? "Generate street view" : "Sign in to generate"}
              </button>
            </div>
          )}

          {phase === "generating" && (
            <div className="sv-status" aria-live="polite">
              <span className="edit-spinner-ring" aria-hidden="true" />
              {progress}
            </div>
          )}

          {phase === "error" && (
            <div className="sv-status is-error" role="alert">
              <div>{error}</div>
              <div className="sv-status-row">
                <button type="button" className="btn btn-primary" onClick={() => void generate()}>
                  Try again
                </button>
                {sv && (
                  <button type="button" className="btn btn-ghost" onClick={() => setPhase("ready")}>
                    Back to the view
                  </button>
                )}
              </div>
            </div>
          )}

          {phase === "ready" && stale && (
            <div className="sv-stale">
              <span>
                Rendered from version {sv!.version_number}; the proposal has changed since.
              </span>
              <button type="button" className="btn btn-small btn-primary" onClick={() => void generate()}>
                Regenerate
              </button>
            </div>
          )}
        </div>

        <div className="sv-toolbar">
          <div className="modal-tabs sv-toggle" role="group" aria-label="Compare">
            <button
              type="button"
              className={showOriginal ? "is-active" : ""}
              aria-pressed={showOriginal}
              disabled={phase !== "ready"}
              onClick={() => setShowOriginal(true)}
            >
              Before
            </button>
            <button
              type="button"
              className={!showOriginal ? "is-active" : ""}
              aria-pressed={!showOriginal}
              disabled={phase !== "ready"}
              onClick={() => setShowOriginal(false)}
            >
              After
            </button>
          </div>
          <span className="spacer" />
          <span className="sv-meta muted">{meta.join(" · ")}</span>
        </div>
      </div>
    </div>
  );
}

/** Photo Sphere Viewer wrapper. Swapping `src` keeps the current yaw/pitch/zoom, so Before/After
 * compares the same direction (both images share the same equirect mapping). */
function PanoViewer({ src }: { src: string }) {
  const container = useRef<HTMLDivElement>(null);
  const viewer = useRef<Viewer | null>(null);
  const current = useRef(src);

  useEffect(() => {
    // Create the viewer one frame later. React StrictMode mounts, unmounts and remounts in dev:
    // a viewer created synchronously starts fetching the panorama and is destroyed (aborting
    // that fetch) in the same tick; three.js de-duplicates in-flight loads by URL, so the
    // replacement viewer joins the dying request, receives its AbortError (which the library
    // swallows) and shows "Loading…" forever. Deferring means the throwaway mount never loads.
    let v: Viewer | null = null;
    const frame = requestAnimationFrame(() => {
      if (!container.current) return;
      v = new Viewer({
        container: container.current,
        panorama: current.current,
        defaultYaw: 0,
        defaultPitch: 0,
        navbar: ["zoom", "fullscreen"],
        loadingTxt: "",
        mousewheel: true,
        touchmoveTwoFingers: false,
      });
      viewer.current = v;
    });
    return () => {
      cancelAnimationFrame(frame);
      v?.destroy();
      viewer.current = null;
    };
  }, []);

  useEffect(() => {
    const v = viewer.current;
    if (!v || src === current.current) return;
    current.current = src;
    void v
      .setPanorama(src, { transition: false, showLoader: false, position: v.getPosition(), zoom: v.getZoomLevel() })
      .catch(() => undefined);
  }, [src]);

  return <div ref={container} className="sv-viewer" />;
}
