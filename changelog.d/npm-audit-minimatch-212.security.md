- **The frontend's lint tooling pulled in a minimatch with a denial-of-service advisory
  (GHSA-g3hv-75wg-m249).** eslint and typescript-eslint still ask for minimatch 10; an npm
  override pins 11.0.5, which eslint runs on unchanged, and `security:dependency-audit` is green
  again. deepmerge (GHSA-gcqx-w48m-w2h4, low, no fixed release, dev only through
  vite-plugin-svelte) stays below the audit level (#212).
