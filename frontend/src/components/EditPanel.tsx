import { useEffect, useState } from "react";
import { submitRefinement } from "../map/submit";
import { useStore } from "../state/store";
import { timeAgo } from "../utils/time";
import { Comments } from "./Comments";
import { IconArrowRight, IconBookmark, IconClock, IconClose, IconComment, IconEdit, IconShare } from "./icons";
import { VersionHistory } from "./VersionHistory";
import { VoteButtons } from "./VoteButtons";

export function EditPanel() {
  const selectedId = useStore((s) => s.selectedId);
  const edit = useStore((s) => (selectedId === null ? undefined : s.edits.get(selectedId)));
  const select = useStore((s) => s.select);
  const viewOriginalId = useStore((s) => s.viewOriginalId);
  const setViewOriginal = useStore((s) => s.setViewOriginal);
  const inFlight = useStore((s) => s.inFlight);
  const user = useStore((s) => s.user);

  const [refining, setRefining] = useState(false);
  const [refineText, setRefineText] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [showComments, setShowComments] = useState(false);

  useEffect(() => {
    setRefining(false);
    setRefineText("");
    setShowHistory(false);
    setShowComments(false);
  }, [selectedId]);

  if (selectedId === null || !edit) return null;

  const busy = inFlight.has(edit.id);
  const viewingOriginal = viewOriginalId === edit.id;
  const others = Math.max(0, edit.version_count - 1);
  const latest = edit.current_version;
  const title = edit.original_prompt || latest?.prompt || "Generating…";

  const onRefine = async () => {
    const prompt = refineText.trim();
    if (prompt.length < 3) return;
    if (!user) {
      useStore.getState().openAuthModal(true);
      return;
    }
    const ok = await submitRefinement(edit.id, prompt);
    if (ok) {
      setRefineText("");
      setRefining(false);
    }
  };

  const share = async () => {
    const url = `${location.origin}${location.pathname}?edit=${edit.id}`;
    try {
      await navigator.clipboard.writeText(url);
      useStore.getState().pushToast("success", "Link copied to clipboard.");
    } catch {
      useStore.getState().pushToast("info", url);
    }
  };

  return (
    <aside className="panel" aria-label="Suggestion details">
      <button type="button" className="panel-close" onClick={() => select(null)} aria-label="Close">
        <IconClose />
      </button>

      <div className="panel-head">
        <div className="panel-main">
          <div className="panel-byline">
            Suggestion by <span className="panel-author">@{edit.created_by.display_name}</span>
            <span className="panel-dot">•</span>
            <span className="muted">{timeAgo(edit.created_at)}</span>
          </div>
          <h2 className="panel-title">{title}</h2>
          {latest && latest.version_number > 1 && (
            <div className="panel-sub muted">Latest refinement: {latest.prompt}</div>
          )}
          <div className="panel-chips">
            <button type="button" className="chip chip-link" onClick={() => setShowHistory((v) => !v)}>
              {others > 0 ? `+ ${others} other edit${others === 1 ? "" : "s"}` : "Edit history"} <IconArrowRight width={16} height={16} />
            </button>
            <span className="chip chip-tag">{edit.status === "pending" ? "GENERATING" : "COMMUNITY EDIT"}</span>
          </div>
        </div>
        <VoteButtons edit={edit} />
      </div>

      {showHistory && (
        <div className="panel-section">
          <VersionHistory edit={edit} />
        </div>
      )}

      <div className="panel-actions">
        {refining ? (
          <div className="refine">
            <textarea
              autoFocus
              value={refineText}
              placeholder="Describe how to refine this proposal…"
              maxLength={300}
              rows={2}
              onChange={(e) => setRefineText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void onRefine();
                } else if (e.key === "Escape") {
                  setRefining(false);
                }
              }}
              disabled={busy}
            />
            <div className="refine-row">
              <button type="button" className="btn btn-ghost" onClick={() => setRefining(false)} disabled={busy}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void onRefine()}
                disabled={busy || refineText.trim().length < 3}
              >
                {busy ? "Generating…" : "Generate refinement"}
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="btn btn-big"
            onClick={() => (user ? setRefining(true) : useStore.getState().openAuthModal(true))}
            disabled={busy || edit.status !== "done"}
          >
            <IconEdit /> {busy ? "Generating refinement…" : "Refine proposal"}
          </button>
        )}
        <button
          type="button"
          className={`btn btn-link ${viewingOriginal ? "is-active" : ""}`}
          onClick={() => setViewOriginal(viewingOriginal ? null : edit.id)}
        >
          <IconClock /> {viewingOriginal ? "Show proposal" : "View original"}
        </button>
      </div>

      <div className="panel-footer">
        <button type="button" className="btn btn-link" onClick={() => setShowComments((v) => !v)}>
          <IconComment /> {edit.comment_count} comment{edit.comment_count === 1 ? "" : "s"}
        </button>
        <button type="button" className="btn btn-link" onClick={() => void share()}>
          <IconShare /> Share
        </button>
        <span className="spacer" />
        <span className="muted" title="Bookmarks coming soon">
          <IconBookmark />
        </span>
      </div>

      {showComments && (
        <div className="panel-section">
          <Comments edit={edit} />
        </div>
      )}
    </aside>
  );
}
