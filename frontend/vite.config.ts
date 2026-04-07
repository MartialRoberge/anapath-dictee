import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/transcribe": "http://localhost:8001",
      "/format": "http://localhost:8001",
      "/iterate": "http://localhost:8001",
      "/sections": "http://localhost:8001",
      "/export": "http://localhost:8001",
      "/health": "http://localhost:8001",
      "/auth": "http://localhost:8001",
      "/reports": "http://localhost:8001",
      "/admin": "http://localhost:8001",
      "/adicap": "http://localhost:8001",
      "/snomed": "http://localhost:8001",
      "/completude": "http://localhost:8001",
    },
  },
});
