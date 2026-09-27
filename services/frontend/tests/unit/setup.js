import { vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { loadAllLocales } from "../../src/lib/i18n/index.js";

// Mock localStorage
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => {
      store[key] = value.toString();
    },
    clear: () => {
      store = {};
    },
    removeItem: (key) => {
      delete store[key];
    },
  };
})();

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
});

// Mock fetch
global.fetch = vi.fn();

// jsdom has no matchMedia, which the shell uses to decide between the mobile and
// desktop layout. Report desktop; a test that needs mobile sets the isMobile store.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
}

// jsdom does not implement the Web Animations API, and Svelte's transitions call
// element.animate(). Without this, rendering anything with a transition on it --
// every modal, for one -- throws instead of appearing.
if (!Element.prototype.animate) {
  Element.prototype.animate = () => ({
    cancel: () => {},
    finish: () => {},
    pause: () => {},
    play: () => {},
    reverse: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    finished: Promise.resolve(),
    playState: "finished",
  });
}

// jsdom reports `navigator.language` as en-US, so components would render in
// English here while the app they are part of is used in Dutch. Pinning the
// locale keeps assertions on interface text in the language the screens are
// actually read in, and keeps them from silently depending on the default.
const { setLocaleFromAccount } = await import("../../src/lib/i18n/index.js");
setLocaleFromAccount("nl");

// The locale files are separate chunks the app fetches on demand (issue #114). Every test
// renders in whichever language it sets without waiting, so all of them are in before any
// test runs -- the same state the app is in after its first language switch.
await loadAllLocales();
