import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// AdidLaBs frontend build config.
// Static SPA served from CloudFront/S3 (region ap-southeast-2). No custom domain.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    target: "es2020",
  },
});
