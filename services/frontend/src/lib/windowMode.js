import { derived, readable } from "svelte/store";
import { platform } from "./platform/index.js";

/**
 * The app's window mode and the compact layout it asks for (`docs/designs/miniplayer/`, section C).
 *
 * Only the Android shell has modes: `split` (half of a split screen) and `pip` (the floating
 * window). A browser tab is always `full`. The compact player replaces the normal screens in a
 * floating window, and in a split screen whose half is too short for them (decision 6). A tall half
 * (a tablet, a landscape split) keeps the normal screens, and so does a phone in landscape at full
 * screen, which is short too but not split.
 */

/** A split-screen half below this height (CSS pixels) shows the compact player. */
export const SPLIT_COMPACT_MAX_HEIGHT = 480;

/**
 * The compact layout for a window mode and a viewport height.
 *
 * @param {import('./platform/index.js').WindowMode} mode
 * @param {number} height - `window.innerHeight`.
 * @returns {'pip'|'split'|null} `null` when the normal screens show.
 */
export function compactLayoutFor(mode, height) {
  if (mode === "pip") return "pip";
  if (mode === "split" && height < SPLIT_COMPACT_MAX_HEIGHT) return "split";
  return null;
}

/**
 * A store of the window mode, fed by the shell's event and one read at subscribe time (the event
 * reaches only a listener that was there before it fired, like `carConnected`).
 *
 * @param {object} [system] - `platform.system`, for tests.
 * @returns {import('svelte/store').Readable<import('./platform/index.js').WindowMode>}
 */
export function createWindowModeStore(system = platform.system) {
  return readable(/** @type {import('./platform/index.js').WindowMode} */ ("full"), (set) => {
    let changed = false;
    const unsubscribe = system.onWindowModeChanged((mode) => {
      changed = true;
      set(mode);
    });
    system
      .windowMode()
      .then((answer) => {
        // An event that arrived while the read was on its way is newer than the read.
        if (!changed) set(answer.mode);
      })
      .catch(() => {});
    return unsubscribe;
  });
}

/**
 * A store of `window.innerHeight`, following resizes.
 *
 * @param {Window} [win] - The window to follow, for tests.
 * @returns {import('svelte/store').Readable<number>}
 */
export function createViewportHeightStore(win = globalThis.window) {
  return readable(win?.innerHeight ?? 0, (set) => {
    if (!win) return undefined;
    const update = () => set(win.innerHeight);
    update();
    win.addEventListener("resize", update);
    return () => win.removeEventListener("resize", update);
  });
}

/** The app's window mode. Always `full` in a browser tab. */
export const windowMode = createWindowModeStore();

/** `pip`, `split` or `null`: which compact layout `App.svelte` shows, if any. */
export const compactLayout = derived([windowMode, createViewportHeightStore()], ([mode, height]) =>
  compactLayoutFor(mode, height),
);
