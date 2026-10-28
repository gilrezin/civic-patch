import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EditOut, VersionOut } from "../api/types";
import { useStore } from "../state/store";
import { timeAgo } from "../utils/time";
import { IconCheck } from "./icons";

export function VersionHistory({ edit }: { edit: EditOut }) {
  const [versions, setVersions] = useState<VersionOut[] | null>(null);
  const preview = useStore((s) => s.previewVersionUrl);
  const setPreviewVersion = useStore((s) => s.setPreviewVersion);

  useEffect(() => {
    let cancelled = false;
    api
      .listVersions(edit.id)
      .then((v) => {
        if (!cancelled) setVersions(v.filter((x) => x.status === "done"));
      })
      .catch(() => {
        if (!cancelled) setVersions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [edit.id, edit.version_count]);

  if (versions === null) return <div className="muted small">Loading history…</div>;

  const currentId = edit.current_version?.id;

  return (
    <ol className="history">
      {versions.map((v) => {
        const isCurrent = v.id === currentId;
        const isPreviewed = preview?.editId === edit.id && preview.url === v.overlay_url;
        const active = isPreviewed || (!preview && isCurrent);
        return (
          <li key={v.id} className={`history-item ${active ? "is-active" : ""}`}>
            <button
              type="button"
              className="history-btn"
              title={isCurrent ? "Current version" : "Preview this version on the map"}
              onClick={() => {
                if (isCurrent || !v.overlay_url) setPreviewVersion(null);
                else setPreviewVersion({ editId: edit.id, url: v.overlay_url });
              }}
            >
              <span className="history-num">v{v.version_number}</span>
              <span className="history-body">
                <span className="history-prompt">{v.prompt}</span>
                <span className="history-meta">
                  @{v.created_by.display_name} · {timeAgo(v.created_at)}
                </span>
              </span>
              {active && (
                <span className="history-check" aria-hidden="true">
                  <IconCheck />
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
