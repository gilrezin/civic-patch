import { useStore } from "../state/store";

export function Header() {
  const user = useStore((s) => s.user);
  const openAuthModal = useStore((s) => s.openAuthModal);
  const setAuth = useStore((s) => s.setAuth);
  const setTool = useStore((s) => s.setTool);
  const tool = useStore((s) => s.tool);

  return (
    <header className="header">
      <div className="header-brand">
        <span className="header-logo" aria-hidden="true">
          <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
            <rect x="2" y="2" width="10" height="10" rx="2.5" fill="#ff7a00" />
            <rect x="14" y="2" width="10" height="10" rx="2.5" fill="#0ea5c7" />
            <rect x="2" y="14" width="10" height="10" rx="2.5" fill="#0ea5c7" />
            <rect x="14" y="14" width="10" height="10" rx="2.5" fill="#ff7a00" />
          </svg>
        </span>
        <div>
          <div className="header-title">civic-patch</div>
          <div className="header-tagline">Reimagine your city, one patch at a time</div>
        </div>
      </div>

      <div className="header-actions">
        <button
          type="button"
          className={`btn btn-primary ${tool === "draw" ? "is-active" : ""}`}
          onClick={() => setTool(tool === "draw" ? "pan" : "draw")}
        >
          {tool === "draw" ? "Cancel drawing" : "Suggest an improvement"}
        </button>
        {user ? (
          <div className="header-user">
            <span className="header-user-name">@{user.display_name}</span>
            <button type="button" className="btn btn-ghost" onClick={() => setAuth(null)}>
              Sign out
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn-ghost" onClick={() => openAuthModal(true)}>
            Sign in
          </button>
        )}
      </div>
    </header>
  );
}
