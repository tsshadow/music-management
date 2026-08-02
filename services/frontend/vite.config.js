import { defineConfig, loadEnv } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [svelte()],
    base: "/",
    // Vitest runs in Node, where Svelte would otherwise resolve to its
    // server-only build and `mount()` throws. Component tests need the
    // browser build.
    ...(process.env.VITEST ? { resolve: { conditions: ["browser"] } } : {}),
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
        // A ratchet, not a target. The frontend is the least-covered part of
        // the repository (54 components, most of them untested); these sit
        // just under the current numbers so the figure cannot quietly erode.
        // Raise them as coverage climbs; never lower one to make a build green.
        thresholds: {
          statements: 21,
          branches: 15,
          functions: 20,
          lines: 21,
        },
      },
    },
  };
});
