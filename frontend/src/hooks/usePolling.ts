import { useEffect } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";

const INTERVAL_MS = 15_000;

let lastFingerprint = "";

export async function refreshEdits(force = false): Promise<void> {
  try {
    const list = await api.listEdits();
    const fp = list
      .map((e) => `${e.id}:${e.updated_at}:${e.score}:${e.comment_count}:${e.my_vote}:${e.saved ? 1 : 0}:${e.place_name ?? ""}`)
      .join("|");
    if (!force && fp === lastFingerprint) return;
    lastFingerprint = fp;
    useStore.getState().setEdits(list);
  } catch {
    /* transient; try again next tick */
  }
}

export function usePolling() {
  const user = useStore((s) => s.user);

  useEffect(() => {
    let timer: number | null = null;
    const tick = () => {
      if (document.hidden) return;
      void refreshEdits();
    };
    void refreshEdits(true);
    timer = window.setInterval(tick, INTERVAL_MS);
    const onVisible = () => {
      if (!document.hidden) void refreshEdits();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      if (timer !== null) window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [user?.id]);
}
