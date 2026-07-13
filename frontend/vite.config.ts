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
      "/transcribe": "http://localhost:8000",
      "/format": "http://localhost:8000",
      "/iterate": "http://localhost:8000",
      "/sections": "http://localhost:8000",
      "/export": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/reports": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/adicap": "http://localhost:8000",
      "/snomed": "http://localhost:8000",
    },
  },
});
