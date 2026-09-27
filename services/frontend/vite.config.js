import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { defineConfig, loadEnv } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { localePreloadPlan, preloadLocaleFiles } from "./src/lib/i18n/localePreload.js";

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

/**
 * Writes a per-chunk, per-module size report when `BUNDLE_REPORT=<path>` is set
 * (issue #114): which chunk each module landed in and how many minified bytes it
 * contributes. Kept in-tree instead of a visualizer dependency so measuring the
 * split never needs a network install, and written outside `dist/` so it never
 * ships in the APK or the LMS docroot. `node scripts/bundle-report.mjs <path>`
 * prints it as a table.
 */
function bundleReport() {
  const target = process.env.BUNDLE_REPORT;
  return {
    name: "muma-bundle-report",
    apply: "build",
    writeBundle(_options, bundle) {
      if (!target) return;
      const chunks = Object.values(bundle)
        .filter((item) => item.type === "chunk")
        .map((chunk) => ({
          fileName: chunk.fileName,
          name: chunk.name,
          isEntry: chunk.isEntry,
          isDynamicEntry: chunk.isDynamicEntry,
          bytes: Buffer.byteLength(chunk.code),
          gzipBytes: gzipSync(chunk.code).length,
          imports: chunk.imports,
          modules: Object.entries(chunk.modules)
            .map(([id, info]) => ({
              id: path.relative(process.cwd(), id),
              bytes: info.renderedLength,
            }))
            .sort((a, b) => b.bytes - a.bytes),
        }))
        .sort((a, b) => b.bytes - a.bytes);
      writeFileSync(target, JSON.stringify({ chunks }, null, 2));
    },
  };
}

/**
 * Starts the listener's locale file together with the entry (issue #118). The locale chunks'
 * names are content-hashed, so only the build knows them: this writes them into `index.html` with
 * a small inline script (`src/lib/i18n/localePreload.js`) that picks the locale the app will start
 * in and adds a `<link rel="modulepreload">` for its files. Without it the file is fetched only
 * after the entry has run -- one more round trip in a browser. The URLs use `base` like the entry's
 * own `<script>`, so the page works wherever LMS or the APK serves it from. The dev server has no
 * bundle and gets nothing.
 */
function localePreload() {
  let base = "/";
  return {
    name: "muma-locale-preload",
    apply: "build",
    configResolved(config) {
      base = config.base;
    },
    transformIndexHtml: {
      order: "post",
      handler(_html, ctx) {
        if (!ctx.bundle) return undefined;
        const files = {};
        for (const item of Object.values(ctx.bundle)) {
          const match =
            item.type === "chunk" &&
            item.facadeModuleId?.match(/[\\/]locales[\\/]([^\\/]+)\.json$/);
          if (match) files[match[1]] = `${base}${item.fileName}`;
        }
        if (Object.keys(files).length === 0) return undefined;
        const plan = JSON.stringify(localePreloadPlan(files));
        return [
          {
            tag: "script",
            children: `(${preloadLocaleFiles.toString()})(window, ${plan});`,
            injectTo: "head",
          },
        ];
      },
    },
  };
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [svelte(), bundleVersionFile(), bundleReport(), localePreload()],
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
      rolldownOptions: {
        output: {
          codeSplitting: {
            // The Svelte runtime and the Capacitor bridge change with a dependency bump, not
            // with every app change, so they get a chunk of their own that a browser keeps
            // cached across deploys (issue #114). Both are needed by the first screen anyway;
            // this moves bytes, it does not add a request that waits. The icon packages are
            // left out on purpose: most icons are used by lazily loaded views, and pulling
            // them into a shared vendor chunk would put them back on the first screen.
            groups: [
              {
                name: "vendor",
                test: /node_modules[\\/](svelte|@capacitor[\\/]core|esm-env|clsx)[\\/]/,
              },
            ],
          },
        },
      },
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
