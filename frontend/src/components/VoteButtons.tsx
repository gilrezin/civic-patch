import { ApiError, api } from "../api/client";
import type { EditOut } from "../api/types";
import { useStore } from "../state/store";
import { IconArrowDown, IconArrowUp } from "./icons";

export function VoteButtons({ edit }: { edit: EditOut }) {
  const user = useStore((s) => s.user);

  const cast = async (value: -1 | 1) => {
    const st = useStore.getState();
    if (!user) {
      st.openAuthModal(true);
      return;
    }
    const next: -1 | 0 | 1 = edit.my_vote === value ? 0 : value;
    // Optimistic update
    const delta = next - edit.my_vote;
    st.upsertEdit({
      ...edit,
      my_vote: next,
      score: edit.score + delta,
      up: edit.up + (next === 1 ? 1 : 0) - (edit.my_vote === 1 ? 1 : 0),
      down: edit.down + (next === -1 ? 1 : 0) - (edit.my_vote === -1 ? 1 : 0),
    });
    try {
      const v = await api.vote(edit.id, next);
      const cur = useStore.getState().edits.get(edit.id);
      if (cur) useStore.getState().upsertEdit({ ...cur, ...v });
    } catch (err) {
      useStore.getState().upsertEdit(edit);
      useStore.getState().pushToast("error", err instanceof ApiError ? err.message : "Could not save your vote.");
    }
  };

  return (
    <div className="vote">
      <button
        type="button"
        className={`vote-btn ${edit.my_vote === 1 ? "is-up" : ""}`}
        onClick={() => cast(1)}
        aria-label="Upvote"
        title="Upvote"
      >
        <IconArrowUp />
      </button>
      <div className="vote-score">{edit.score}</div>
      <button
        type="button"
        className={`vote-btn ${edit.my_vote === -1 ? "is-down" : ""}`}
        onClick={() => cast(-1)}
        aria-label="Downvote"
        title="Downvote"
      >
        <IconArrowDown />
      </button>
    </div>
  );
}
