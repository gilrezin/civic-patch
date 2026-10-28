import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API and image requests to the FastAPI backend so the
// browser only ever talks to one origin (no CORS, no absolute URLs in code).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true, timeout: 180_000, proxyTimeout: 180_000 },
      "/images": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
