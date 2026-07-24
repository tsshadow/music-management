import { defineConfig, loadEnv } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [svelte()],
    base: "/",
    server: {
      host: true,
      proxy: {
        "/api": {
          target: env.VITE_API_TARGET || "http://localhost:8000",
          changeOrigin: true,
        },
        "/rest": {
          target: env.VITE_LMS_TARGET || "http://localhost:5082",
          changeOrigin: true,
        },
        "/muma": {
          target: env.VITE_LMS_TARGET || "http://localhost:5082",
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
