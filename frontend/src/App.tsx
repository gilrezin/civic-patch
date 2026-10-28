import { useEffect } from "react";
import { AuthModal } from "./components/AuthModal";
import { EditPanel } from "./components/EditPanel";
import { Header } from "./components/Header";
import { Toasts } from "./components/Toast";
import { usePolling } from "./hooks/usePolling";
import { MapView } from "./map/MapView";
import { useStore } from "./state/store";

export default function App() {
  const restoreSession = useStore((s) => s.restoreSession);
  const editsVersion = useStore((s) => s.editsVersion);

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  usePolling();

  // Deep link: ?edit=ID selects and fits that edit once it has loaded.
  useEffect(() => {
    const id = Number(new URLSearchParams(location.search).get("edit"));
    if (!id) return;
    const st = useStore.getState();
    if (st.selectedId === null && st.edits.has(id)) {
      st.select(id);
      history.replaceState(null, "", location.pathname);
    }
  }, [editsVersion]);

  return (
    <div className="app">
      <Header />
      <main className="main">
        <MapView />
        <EditPanel />
      </main>
      <AuthModal />
      <Toasts />
    </div>
  );
}
