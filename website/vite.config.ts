import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";

const repoRoot = resolve(__dirname, "..");

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/",
  server: {
    port: 8080,
    fs: {
      allow: [repoRoot],
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      "@docs": resolve(repoRoot, "docs"),
    },
  },
});
