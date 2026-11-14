import { mount, unmount } from "svelte";
import CompactPlayer from "./CompactPlayer.svelte";

/**
 * The PC's always-on-top miniplayer window (issue #177, docs/designs/miniplayer/).
 *
 * Chrome and Edge 116+ on a desktop have Document Picture-in-Picture:
 * `documentPictureInPicture.requestWindow()` gives a same-origin window with an empty document
 * that the browser keeps above other windows. `CompactPlayer` is mounted into that document with
 * a props object `Player.svelte` owns and keeps current, so the window shows the same state and
 * calls the same functions as the player bar -- and the music still plays from the tab's one
 * `<audio>` element. A browser without the API gets no button (decision 1), so nothing here has a
 * fallback.
 */

/** The window's first size: the strip layout (decision 2). The listener can resize it. */
export const DEFAULT_SIZE = Object.freeze({ width: 360, height: 120 });

/** @type {{win: Window, component: object, observers: MutationObserver[]} | null} */
let current = null;

/**
 * Whether this browser can open the miniplayer window. Absent on Firefox, Safari, every phone
 * browser, the Android WebView, and on a page that is not a secure context.
 *
 * @param {{isNative?: boolean}} [system] - `platform.system`; the app never offers the window.
 * @param {object} [win] - The window to ask, for tests.
 * @returns {boolean}
 */
export function isSupported(system = {}, win = globalThis.window) {
  if (system?.isNative) return false;
  return Boolean(win && "documentPictureInPicture" in win && win.documentPictureInPicture);
}

/** @returns {boolean} True while a miniplayer window is open. */
export function isOpen() {
  return current !== null;
}

/**
 * Copies every style sheet of `from` into the document `to`. A sheet whose rules can be read
 * becomes a `<style>`; one that cannot (cross-origin) is linked again by its URL.
 *
 * @param {Document} from
 * @param {Document} to
 * @param {Set<CSSStyleSheet>} copied - Sheets already copied, so a second pass adds only new ones.
 */
export function copyStyleSheets(from, to, copied) {
  for (const sheet of Array.from(from.styleSheets)) {
    if (copied.has(sheet)) continue;
    copied.add(sheet);
    let css;
    try {
      css = Array.from(sheet.cssRules, (rule) => rule.cssText).join("\n");
    } catch {
      css = null;
    }
    if (css !== null) {
      const style = to.createElement("style");
      style.textContent = css;
      to.head.appendChild(style);
    } else if (sheet.href) {
      const link = to.createElement("link");
      link.rel = "stylesheet";
      link.href = sheet.href;
      to.head.appendChild(link);
    }
  }
}

/**
 * Opens the miniplayer window, or focuses it when it is already open. Must run from a click: the
 * browser refuses `requestWindow` without user activation.
 *
 * @param {object} props - A `$state` object `Player.svelte` keeps current; `CompactPlayer`'s props.
 * @param {{title?: string, win?: Window}} [options]
 * @returns {Promise<boolean>} True when a window is open afterwards.
 */
export async function openMiniplayer(props, options = {}) {
  const host = options.win ?? globalThis.window;
  if (current) {
    current.win.focus?.();
    return true;
  }
  if (!host?.documentPictureInPicture) return false;

  const win = await host.documentPictureInPicture.requestWindow({ ...DEFAULT_SIZE });
  const doc = win.document;
  const source = host.document;
  if (options.title) doc.title = options.title;

  const copied = new Set();
  copyStyleSheets(source, doc, copied);
  doc.documentElement.className = source.documentElement.className;
  doc.documentElement.style.height = "100%";
  doc.body.style.height = "100%";
  doc.body.style.margin = "0";

  // A lazy chunk adds its CSS to the tab after the window opened; songs/sets mode is a class on
  // <html>. Both are followed for as long as the window lives.
  const MutationObserverImpl = host.MutationObserver ?? globalThis.MutationObserver;
  const sheets = new MutationObserverImpl(() => copyStyleSheets(source, doc, copied));
  sheets.observe(source.head, { childList: true });
  const mode = new MutationObserverImpl(() => {
    doc.documentElement.className = source.documentElement.className;
  });
  mode.observe(source.documentElement, { attributes: true, attributeFilter: ["class"] });

  const component = mount(CompactPlayer, { target: doc.body, props });
  current = { win, component, observers: [sheets, mode] };

  win.addEventListener("pagehide", () => teardown(win));
  return true;
}

/** Closes the miniplayer window if one is open. The music is not touched. */
export function closeMiniplayer() {
  if (!current) return;
  const { win } = current;
  teardown(win);
  win.close?.();
}

/**
 * Unmounts the component and stops following the tab, once per window.
 *
 * @param {Window} win
 */
function teardown(win) {
  if (!current || current.win !== win) return;
  const { component, observers } = current;
  current = null;
  for (const observer of observers) observer.disconnect();
  unmount(component);
}
