import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> };

// Dev server proxies API and image requests to the FastAPI backend so the
// browser only ever talks to one origin (no CORS, no absolute URLs in code).
// Override the backend location with VITE_API_TARGET (default http://127.0.0.1:8000).
// 127.0.0.1 rather than localhost: on Windows "localhost" resolves to ::1 first and the
// failed IPv6 attempt can add ~2 s to every request before falling back to IPv4.
const target = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target, changeOrigin: true, timeout: 180_000, proxyTimeout: 180_000 },
      "/images": { target, changeOrigin: true },
    },
  },
});
