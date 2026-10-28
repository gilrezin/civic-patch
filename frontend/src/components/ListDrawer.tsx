import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { ContributionOut, EditOut } from "../api/types";
import { useStore } from "../state/store";
import { timeAgo } from "../utils/time";
import { IconArrowUp, IconBookmarkFilled, IconClose, IconMapPin } from "./icons";

function placeLabel(place: string | null, lngLat: [number, number]): string {
  if (place) return place;
  return `${lngLat[1].toFixed(4)}, ${lngLat[0].toFixed(4)}`;
}

function centroidOfEdit(e: EditOut): [number, number] {
  const [w, s, en, n] = e.bounds;
  return [(w + en) / 2, (s + n) / 2];
}

/** Right-hand drawer listing either the user's contributions or their saved posts. */
export function ListDrawer() {
  const drawer = useStore((s) => s.drawer);
  const setDrawer = useStore((s) => s.setDrawer);
  const user = useStore((s) => s.user);
  const editsVersion = useStore((s) => s.editsVersion);
  const select = useStore((s) => s.select);

  const [contribs, setContribs] = useState<ContributionOut[] | null>(null);
  const [saved, setSaved] = useState<EditOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!drawer || !user) return;
    let cancelled = false;
    setError(null);
    const load = drawer === "mine" ? api.contributions().then((c) => !cancelled && setContribs(c)) : api.saved().then((s) => !cancelled && setSaved(s));
    load.catch((err) => !cancelled && setError(err instanceof ApiError ? err.message : "Could not load the list."));
    return () => {
      cancelled = true;
    };
  }, [drawer, user, editsVersion]);

  if (!drawer || !user) return null;

  const title = drawer === "mine" ? "My Edits" : "Saved";
  const subtitle =
    drawer === "mine"
      ? "Suggestions you created and refinements you made to other people's suggestions."
      : "Posts you bookmarked. Only you can see this list.";

  const open = (editId: number) => {
    const exists = useStore.getState().edits.has(editId);
    if (!exists) {
      useStore.getState().pushToast("info", "That suggestion is no longer on the map.");
      return;
    }
    select(editId);
  };

  return (
    <aside className="panel drawer" aria-label={title}>
      <button type="button" className="panel-close" onClick={() => setDrawer(null)} aria-label="Close">
        <IconClose />
      </button>
      <h2 className="drawer-title">{title}</h2>
      <p className="muted small drawer-sub">{subtitle}</p>

      {error && <div className="form-error">{error}</div>}

      {drawer === "mine" &&
        (contribs === null ? (
          <div className="muted small">Loading…</div>
        ) : contribs.length === 0 ? (
          <div className="drawer-empty">
            You have not made any edits yet. Click <strong>Suggest an improvement</strong> and outline an area to start.
          </div>
        ) : (
          <ul className="drawer-list">
            {contribs.map((c) => {
              const own = c.edit_creator.id === user.id;
              return (
                <li key={c.version_id}>
                  <button type="button" className="drawer-item" onClick={() => open(c.edit_id)}>
                    <div className="drawer-item-top">
                      <span className={`kind kind-${c.kind}`}>{c.kind === "edit" ? "Initial edit" : "Refinement"}</span>
                      <span className="muted small">{timeAgo(c.created_at)}</span>
                    </div>
                    <div className="drawer-item-title">{c.prompt}</div>
                    {c.kind === "refinement" && (
                      <div className="muted small">
                        Refines {own ? "your edit" : `@${c.edit_creator.display_name}'s edit`} “{c.edit_original_prompt}”
                      </div>
                    )}
                    <div className="drawer-item-meta">
                      <span className="drawer-place">
                        <IconMapPin width={14} height={14} /> {placeLabel(c.place_name, c.centroid)}
                      </span>
                      <span className="drawer-score">
                        <IconArrowUp width={14} height={14} /> {c.score}
                      </span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        ))}

      {drawer === "saved" &&
        (saved === null ? (
          <div className="muted small">Loading…</div>
        ) : saved.length === 0 ? (
          <div className="drawer-empty">
            Nothing saved yet. Open a suggestion and press the bookmark icon to keep it here.
          </div>
        ) : (
          <ul className="drawer-list">
            {saved.map((e) => (
              <li key={e.id}>
                <button type="button" className="drawer-item" onClick={() => open(e.id)}>
                  <div className="drawer-item-top">
                    <span className="muted small">
                      by @{e.created_by.display_name} · {timeAgo(e.created_at)}
                    </span>
                    <span className="drawer-saved-icon" aria-hidden="true">
                      <IconBookmarkFilled width={16} height={16} />
                    </span>
                  </div>
                  <div className="drawer-item-title">{e.original_prompt}</div>
                  {e.version_count > 1 && (
                    <div className="muted small">
                      + {e.version_count - 1} refinement{e.version_count - 1 === 1 ? "" : "s"}
                    </div>
                  )}
                  <div className="drawer-item-meta">
                    <span className="drawer-place">
                      <IconMapPin width={14} height={14} /> {placeLabel(e.place_name, centroidOfEdit(e))}
                    </span>
                    <span className="drawer-score">
                      <IconArrowUp width={14} height={14} /> {e.score}
                    </span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        ))}
    </aside>
  );
}
