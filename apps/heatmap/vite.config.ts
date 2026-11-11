import { resolve } from "node:path";
import { defineConfig } from "vite";

// Relative base so the same build works at a domain root or under a sub-path (e.g. GitHub Pages).
// Three pages: landing (index), market home (home) and the sale/rent map (map).
export default defineConfig({
  base: "./",
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      input: {
        index: resolve(__dirname, "index.html"),
        home: resolve(__dirname, "home.html"),
        map: resolve(__dirname, "map.html"),
      },
    },
  },
});
