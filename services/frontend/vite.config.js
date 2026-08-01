import { defineConfig, loadEnv } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [svelte()],
    base: "/",
    // Under Vitest, Svelte 5 otherwise resolves to its server build and mounting a
    // component fails with lifecycle_function_unavailable. Scoped to the test run so
    // the production build resolves exactly as before.
    resolve: process.env.VITEST ? { conditions: ["browser"] } : undefined,
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
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["tests/unit/setup.js"],
      include: ["tests/unit/**/*.{test,spec}.{js,ts}"],
      coverage: {
        provider: "v8",
        reporter: ["text", "json", "html", "cobertura"],
        reportsDirectory: "./coverage",
        include: ["src/**/*.{js,svelte}"],
      },
    },
  };
});
