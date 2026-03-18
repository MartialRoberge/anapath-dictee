import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/transcribe": "http://localhost:8000",
      "/format": "http://localhost:8000",
      "/iterate": "http://localhost:8000",
      "/sections": "http://localhost:8000",
      "/export": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
