# MuMa Web Frontend

Unified SvelteKit application that surfaces the music importer, scrobbler dashboards, and configuration interfaces in a single UI.

## Development

```bash
pnpm install
pnpm dev
```

The dev server is available on <http://localhost:5173> by default. The app expects the MuMa API gateway to be accessible via `/api`; override this by setting `VITE_API_BASE`.

## Quality checks

```bash
pnpm check
pnpm test # (add tests alongside new features)
pnpm build
```

## Build output

Production builds target static hosting via `@sveltejs/adapter-static` with an SPA fallback. Run `pnpm preview` to verify the built assets from the `build/` directory.
