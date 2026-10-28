import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api } from "../api/client";
import type { CommentOut, EditOut } from "../api/types";
import { useStore } from "../state/store";
import { timeAgo } from "../utils/time";

export function Comments({ edit }: { edit: EditOut }) {
  const user = useStore((s) => s.user);
  const [comments, setComments] = useState<CommentOut[] | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listComments(edit.id)
      .then((c) => {
        if (!cancelled) setComments(c);
      })
      .catch(() => {
        if (!cancelled) setComments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [edit.id, edit.comment_count]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const st = useStore.getState();
    if (!user) {
      st.openAuthModal(true);
      return;
    }
    const body = text.trim();
    if (!body) return;
    setBusy(true);
    try {
      const c = await api.addComment(edit.id, body);
      setComments((prev) => [...(prev ?? []), c]);
      setText("");
      const cur = st.edits.get(edit.id);
      if (cur) st.upsertEdit({ ...cur, comment_count: cur.comment_count + 1 });
    } catch (err) {
      st.pushToast("error", err instanceof ApiError ? err.message : "Could not post your comment.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="comments">
      {comments === null ? (
        <div className="muted small">Loading comments…</div>
      ) : comments.length === 0 ? (
        <div className="muted small">No comments yet. Start the conversation.</div>
      ) : (
        <ul className="comment-list">
          {comments.map((c) => (
            <li key={c.id} className="comment">
              <div className="comment-meta">
                <span className="comment-author">@{c.author.display_name}</span>
                <span className="muted">· {timeAgo(c.created_at)}</span>
              </div>
              <div className="comment-body">{c.body}</div>
            </li>
          ))}
        </ul>
      )}
      <form className="comment-form" onSubmit={onSubmit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={user ? "Add a comment…" : "Sign in to comment"}
          maxLength={1000}
          onFocus={() => {
            if (!user) useStore.getState().openAuthModal(true);
          }}
        />
        <button type="submit" className="btn btn-secondary" disabled={busy || !text.trim()}>
          Post
        </button>
      </form>
    </div>
  );
}
