import { execSync } from "node:child_process";
import { defineConfig, loadEnv } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

/** Routes the API paths to music-manager and music-management-server. */
function backendProxy(env) {
  const manager = env.VITE_API_TARGET || "http://localhost:8000";
  const server = env.VITE_LMS_TARGET || "http://localhost:5082";
  return {
    "/api": { target: manager, changeOrigin: true },
    "/rest": { target: server, changeOrigin: true },
    "/muma": { target: server, changeOrigin: true },
  };
}

/**
 * Stages `dist/version.json` next to `index.html`, so a diagnostics report
 * built from the web UI (`identifyBundle` in `src/lib/diagnosticsLog.js`) can
 * say which build it was running -- the APK's own version name covers the
 * shell, not the bundle inside it, and the two ship on separate schedules.
 *
 * `apply: "build"` on purpose: `vite build` is the only thing that produces a
 * `dist/` at all, so a dev server or a vitest run never spawns `git`.
 */
function bundleVersionFile() {
  return {
    name: "muma-bundle-version",
    apply: "build",
    generateBundle() {
      let version = "unknown";
      try {
        version = execSync("git rev-parse --short HEAD", { cwd: process.cwd() }).toString().trim();
      } catch {
        // No git, or no repository -- an npm-only checkout. "unknown" still
        // beats failing the build over a diagnostics nicety.
      }
      this.emitFile({
        type: "asset",
        fileName: "version.json",
        source: JSON.stringify({ version, builtAt: new Date().toISOString() }),
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [svelte(), bundleVersionFile()],
    base: "/",
    // Vitest runs in Node, where Svelte would otherwise resolve to its
    // server-only build and `mount()` throws. Component tests need the
    // browser build.
    ...(process.env.VITEST ? { resolve: { conditions: ["browser"] } } : {}),
    server: {
      host: true,
      proxy: backendProxy(env),
    },
    // `vite preview` serves the built bundle. The browser tests use it instead
    // of the dev server (see playwright.config.js), so it needs the same proxy
    // or every API call in them would 404 against the static server.
    preview: {
      host: true,
      proxy: backendProxy(env),
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
        // A ratchet, not a target: these sit just under the current numbers so
        // the figure cannot quietly erode. Raise them as coverage climbs; never
        // lower one to make a build green.
        thresholds: {
          statements: 82,
          branches: 65,
          functions: 79,
          lines: 81,
        },
      },
    },
  };
});
