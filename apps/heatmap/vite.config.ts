import { defineConfig } from "vite";

// Relative base so the same build works at a domain root or under a sub-path (e.g. GitHub Pages).
export default defineConfig({
  base: "./",
  build: { target: "es2022", chunkSizeWarningLimit: 1200 },
});
