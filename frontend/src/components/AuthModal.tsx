import { useState, type FormEvent } from "react";
import { ApiError, api } from "../api/client";
import { useStore } from "../state/store";
import { IconClose } from "./icons";

export function AuthModal() {
  const open = useStore((s) => s.authModalOpen);
  const openAuthModal = useStore((s) => s.openAuthModal);
  const setAuth = useStore((s) => s.setAuth);
  const [tab, setTab] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const auth = tab === "login" ? await api.login(email, password) : await api.signup(email, password, name);
      setAuth(auth);
      useStore.getState().pushToast("success", `Welcome, @${auth.user.display_name}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={() => openAuthModal(false)}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <button type="button" className="modal-close" onClick={() => openAuthModal(false)} aria-label="Close">
          <IconClose />
        </button>
        <div className="modal-tabs">
          <button type="button" className={tab === "login" ? "is-active" : ""} onClick={() => setTab("login")}>
            Sign in
          </button>
          <button type="button" className={tab === "signup" ? "is-active" : ""} onClick={() => setTab("signup")}>
            Create account
          </button>
        </div>
        <p className="modal-lead">
          {tab === "login"
            ? "Sign in to suggest improvements, vote and comment."
            : "Your display name is public and shown on every suggestion you make."}
        </p>
        <form onSubmit={onSubmit} className="form">
          {tab === "signup" && (
            <label>
              Display name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="alex_urbanist"
                required
                minLength={2}
                maxLength={32}
                autoComplete="nickname"
              />
            </label>
          )}
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={tab === "login" ? "current-password" : "new-password"}
            />
          </label>
          {error && <div className="form-error">{error}</div>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "Please wait…" : tab === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
