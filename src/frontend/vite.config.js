import process from "node:process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Support GitHub Pages subpath deployment (/Caelum-EO/) or root deployment
const basePath =
  process.env.VITE_APP_BASE ||
  (process.env.VITE_APP_DEMO_MODE === "true" ? "/Caelum-EO/" : "/");

export default defineConfig({
  base: basePath,
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
  },
});
