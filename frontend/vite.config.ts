import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync, statfsSync } from "node:fs";

const rootDir = fileURLToPath(new URL(".", import.meta.url));
const previewDiskRoot = existsSync("C:\\") ? "C:\\" : rootDir;
const previewDiskStats = statfsSync(previewDiskRoot);
const previewDiskFreeGB = Number(previewDiskStats.bavail * previewDiskStats.bsize) / 1024 ** 3;

export default defineConfig({
  root: resolve(rootDir),
  publicDir: resolve(rootDir, "../assets"),
  plugins: [react()],
  define: {
    __ARENA_PREVIEW_DISK_FREE_GB__: JSON.stringify(previewDiskFreeGB),
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  build: {
    outDir: resolve(rootDir, "dist"),
    emptyOutDir: true,
  },
});
