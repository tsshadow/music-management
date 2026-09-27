- **The web player's first screen loads less than half the JavaScript it used to** (issue #114,
  `docs/designs/perceived-performance/technical.md` "Code splitting"). The bundle was one 1.29 MB
  file (350 kB gzip), so every start parsed all of Beheer, the settings pages, the statistics
  pages and all four translation files before the home screen could paint. Pages off the first
  screen are now chunks of their own, fetched when opened (`lazyViews.js`, `LazyView.svelte`):
  settings and its sidebar, Beheer's shell and sidebar and each of its tabs (Scrobble excepted),
  history, listening statistics, starred, memories, song versions, the curation edit pages, the
  preset builder, voice, downloads, the car screen, the setup tour, the search "more" modal, the
  track details sheet and the equalizer. Each translation file is a chunk too, and only the active
  locale is waited for (Dutch is complete, so English follows in the background). The entry chunk
  went from 1,289 kB to 370 kB (107 kB gzip); everything that loads before the app mounts -- the
  entry, the chunks it imports and one locale -- is 580 kB (184 kB gzip).
  - **Opened by URL**, a lazily loaded page's chunk is fetched behind the boot screen, so the app
    appears with the page instead of a skeleton. **Opened by navigating**, the page shows skeleton
    rows while its chunk loads, and a chunk that fails shows the section error with a retry. The
    settings page, song versions, the search "more" modal and the details sheet are fetched on idle
    once the first screen is up, and Beheer's shell and first tab as soon as the account turns out
    to be an admin.
  - **Deploys.** LMS now sends `Cache-Control: public, max-age=31536000, immutable` for the hashed
    files under `/assets/` and `no-cache` for everything else it serves from the web UI's docroot,
    `index.html` and the SPA route fallback included. It sent no cache headers at all. A tab left
    open across a deploy that asks for a chunk the new build replaced reloads once
    (`vite:preloadError`) instead of showing a retry that cannot succeed.
  - **Measuring.** `BUNDLE_REPORT=<file> vite build` writes a per-chunk, per-module size report and
    `node scripts/bundle-report.mjs <file>` prints it, with the entry's static-import closure.
<!-- release notes -->
- The web player starts faster: the first screen loads less than half the code it used to, and
  pages like Beheer, settings and statistics load when you open them.
