/**
 * Makes lazily loaded views deterministic in unit tests (issue #120).
 *
 * Pages, overlays and tabs are separate chunks since #114/#118/#119: `LazyView.svelte` and
 * `lazyComponent.svelte.js` render them at once when their chunk is already in (`peek`), and
 * after a dynamic `import()` otherwise. Under vitest that import compiles the component on
 * first use, which on a loaded CI runner can take longer than `waitFor`'s default second --
 * "the event log tab is reachable" timed out exactly that way (pipeline 4022). A test that is
 * about what a view *does*, not about how it loads, therefore loads the view's chunk before it
 * renders, and the view is on the first frame like any other component.
 *
 * Tests about the loading itself (skeletons, seeded shells, retry) do not use these helpers;
 * they control the registry directly.
 */
import {
  chunksForState,
  lazyViews,
  managementTabs,
  settingsTabs,
} from "../../src/lib/lazyViews.js";

/**
 * A generous timeout for the few `findBy`/`waitFor` calls that must wait for a chunk the test
 * could not load up front (one a click decides). Only the slow case uses it; a passing
 * assertion returns as soon as it holds.
 */
export const LAZY_TIMEOUT_MS = 10_000;

/**
 * The timeout for a `beforeAll`/`beforeEach` that loads chunks: the first load compiles the
 * component, and several at once on a busy runner can pass vitest's 10 s hook default.
 */
export const LAZY_HOOK_TIMEOUT_MS = 60_000;

/** `waitFor`/`findBy` options with `LAZY_TIMEOUT_MS`. */
export const lazyWait = { timeout: LAZY_TIMEOUT_MS };

/**
 * Loads chunks so the views render synchronously. Rejects when one cannot be loaded, so a
 * broken import fails the test at its cause instead of as a missing element later.
 *
 * @param {...(string|[ReturnType<typeof import('../../src/lib/lazyViews.js').createLazyRegistry>, string])} entries
 *   A name in `lazyViews`, or a `[registry, name]` pair.
 * @returns {Promise<void>}
 */
export async function loadLazy(...entries) {
  await Promise.all(
    entries.map((entry) =>
      typeof entry === "string" ? lazyViews.load(entry) : entry[0].load(entry[1]),
    ),
  );
}

/**
 * Loads one Beheer tab's chunk.
 *
 * @param {string} tab - A name in `managementTabs`.
 */
export function loadManagementTab(tab) {
  return loadLazy([managementTabs, tab]);
}

/**
 * Loads one settings tab's chunk.
 *
 * @param {string} tab - A name in `settingsTabs`.
 */
export function loadSettingsTab(tab) {
  return loadLazy([settingsTabs, tab]);
}

/**
 * Loads every chunk a view state needs, as the app does behind its boot screen
 * (`chunksForState`): the page, its sidebar and, for settings and Beheer, the open tab.
 *
 * @param {{view: string, managementTab?: string, settingsTab?: string}} state
 */
export function loadLazyState(state) {
  return loadLazy(...chunksForState(state));
}
