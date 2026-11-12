import { useEffect, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { SearchHit } from "../api/types";
import { useStore } from "../state/store";
import { IconFile, IconMapPin, IconSearch } from "./icons";

/** Header button showing the current city and neighbourhood, with a dropdown for the
 * municipality's comprehensive plan and a place search. */
export function LocationMenu() {
  const place = useStore((s) => s.place);
  const requestFlyTo = useStore((s) => s.requestFlyTo);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [left, setLeft] = useState(0);

  // The panel is rendered through a portal on <body>: an ancestor with backdrop-filter (the
  // header) is the containing block for position: fixed and also its backdrop root, so a
  // dropdown left inside the header gets composited within the header's frosted group and
  // looks more transparent than the toolbar. Anchor it to the button's measured position.
  useEffect(() => {
    if (!open) return;
    const measure = () => {
      const r = rootRef.current?.getBoundingClientRect();
      if (r) setLeft(Math.max(8, Math.min(r.left, window.innerWidth - 388)));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const city = place?.city ?? "Locating…";
  const sub = place?.neighbourhood ?? place?.region ?? (place ? "" : "");
  const plan = place?.plan;

  const onSearch = async (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (q.length < 2) return;
    setSearching(true);
    try {
      const hits = await api.placesSearch(q);
      setResults(hits);
      if (hits.length === 1) go(hits[0]);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const go = (hit: SearchHit) => {
    requestFlyTo({ lng: hit.lng, lat: hit.lat, bbox: hit.bbox });
    setOpen(false);
    setResults(null);
    setQuery("");
  };

  return (
    <div className="locmenu" ref={rootRef}>
      <button
        type="button"
        className={`locbtn ${open ? "is-open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Current location: plan and search"
      >
        <span className="locbtn-icon" aria-hidden="true">
          <IconMapPin width={18} height={18} />
        </span>
        <span className="locbtn-text">
          <span className="locbtn-city">{city}</span>
          <span className="locbtn-sub">{sub || " "}</span>
        </span>
      </button>

      {open &&
        createPortal(
        <div className="locmenu-panel" role="menu" style={{ left }} ref={panelRef}>
          {plan?.exists && plan.url ? (
            <a className="locmenu-plan is-found" href={plan.url} download={plan.filename ?? undefined} role="menuitem">
              <IconFile />
              <span>
                <span className="locmenu-plan-title">Comprehensive plan on file for {place?.city}</span>
                <span className="locmenu-plan-sub">Click to download the PDF</span>
              </span>
            </a>
          ) : (
            <div className="locmenu-plan" role="note">
              <IconFile />
              <span>
                <span className="locmenu-plan-title">No comprehensive plan on file{place?.city ? ` for ${place.city}` : ""}</span>
                <span className="locmenu-plan-sub">Standard design guidance applies here</span>
              </span>
            </div>
          )}

          <form className="locmenu-search" onSubmit={onSearch}>
            <IconSearch width={18} height={18} />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setResults(null);
              }}
              placeholder="Go to a place, address or city…"
              aria-label="Search for a place"
            />
            <button type="submit" className="btn btn-primary btn-small" disabled={searching || query.trim().length < 2}>
              {searching ? "…" : "Go"}
            </button>
          </form>
          {results && (
            <ul className="locmenu-results">
              {results.length === 0 && <li className="muted small locmenu-empty">No places found.</li>}
              {results.map((h, i) => (
                <li key={i}>
                  <button type="button" onClick={() => go(h)}>
                    {h.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>,
          document.body,
        )}
    </div>
  );
}
