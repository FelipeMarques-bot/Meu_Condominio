import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/static/dist/",
  plugins: [tailwindcss()],
  build: {
    outDir: "static/dist",
    emptyOutDir: true,
    manifest: true,
    assetsDir: "assets",
    rollupOptions: {
      input: {
        app: resolve(import.meta.dirname, "assets/app.js"),
      },
    },
  },
  server: {
    port: 5173,
    cors: true,
    origin: "http://localhost:5173",
  },
});
