import { describe, it, expect, vi, afterEach } from "vitest";
import {
  DEFAULT_SIZE,
  closeMiniplayer,
  copyStyleSheets,
  isOpen,
  isSupported,
  openMiniplayer,
} from "../../src/lib/miniplayerWindow.js";

/**
 * A stand-in for the window `documentPictureInPicture.requestWindow()` returns: a second,
 * empty document, as the browser gives one.
 */
function fakePictureInPicture() {
  const doc = document.implementation.createHTMLDocument("");
  const listeners = {};
  const win = {
    document: doc,
    focus: vi.fn(),
    close: vi.fn(() => listeners.pagehide?.()),
    addEventListener: vi.fn((name, fn) => {
      listeners[name] = fn;
    }),
  };
  const host = {
    document,
    MutationObserver,
    documentPictureInPicture: { requestWindow: vi.fn(async () => win) },
  };
  return { host, win, doc, listeners };
}

function props(overrides = {}) {
  return {
    track: { id: "song-1", title: "Raise Your Fist", artist: "Angerfist" },
    playing: false,
    progress: 0,
    duration: 240,
    rating: 0,
    ontogglePlay: vi.fn(),
    onnext: vi.fn(),
    onprev: vi.fn(),
    onrate: vi.fn(),
    ...overrides,
  };
}

afterEach(() => {
  closeMiniplayer();
  document.documentElement.className = "";
  document.head.querySelectorAll("style[data-test]").forEach((el) => el.remove());
});

describe("isSupported", () => {
  it("is true where the browser has Document Picture-in-Picture", () => {
    expect(isSupported({ isNative: false }, { documentPictureInPicture: {} })).toBe(true);
  });

  it("is false without the API, as in Firefox, Safari or a phone browser", () => {
    expect(isSupported({ isNative: false }, {})).toBe(false);
  });

  it("is false in the app, which has its own floating window", () => {
    expect(isSupported({ isNative: true }, { documentPictureInPicture: {} })).toBe(false);
  });
});

describe("openMiniplayer", () => {
  it("opens one window at the strip size with the compact player in it", async () => {
    const { host, doc } = fakePictureInPicture();

    expect(await openMiniplayer(props(), { win: host, title: "Miniplayer" })).toBe(true);

    expect(host.documentPictureInPicture.requestWindow).toHaveBeenCalledWith({ ...DEFAULT_SIZE });
    expect(doc.title).toBe("Miniplayer");
    expect(doc.querySelector('[data-testid="compact-title"]').textContent).toBe("Raise Your Fist");
    expect(isOpen()).toBe(true);
  });

  it("runs the player's own function for a click inside the window", async () => {
    const { host, doc } = fakePictureInPicture();
    const p = props();
    await openMiniplayer(p, { win: host });

    doc.querySelector('[data-testid="compact-play"]').click();

    expect(p.ontogglePlay).toHaveBeenCalledTimes(1);
  });

  it("focuses the open window instead of opening a second one", async () => {
    const { host, win } = fakePictureInPicture();
    await openMiniplayer(props(), { win: host });

    await openMiniplayer(props(), { win: host });

    expect(host.documentPictureInPicture.requestWindow).toHaveBeenCalledTimes(1);
    expect(win.focus).toHaveBeenCalled();
  });

  it("copies the tab's styles and its songs/sets mode, and follows a mode switch", async () => {
    const style = document.createElement("style");
    style.dataset.test = "1";
    style.textContent = ".mini-test-rule { color: red; }";
    document.head.appendChild(style);
    document.documentElement.className = "mode-sets";
    const { host, doc } = fakePictureInPicture();

    await openMiniplayer(props(), { win: host });

    expect(doc.head.textContent).toContain(".mini-test-rule");
    expect(doc.documentElement.className).toBe("mode-sets");

    document.documentElement.className = "";
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(doc.documentElement.className).toBe("");
  });

  it("unmounts when the window closes, and a later open makes a new one", async () => {
    const { host, listeners, doc } = fakePictureInPicture();
    await openMiniplayer(props(), { win: host });

    listeners.pagehide();

    expect(isOpen()).toBe(false);
    expect(doc.querySelector('[data-testid="compact-player"]')).toBeNull();
    await openMiniplayer(props(), { win: host });
    expect(host.documentPictureInPicture.requestWindow).toHaveBeenCalledTimes(2);
  });

  it("closeMiniplayer closes the window", async () => {
    const { host, win } = fakePictureInPicture();
    await openMiniplayer(props(), { win: host });

    closeMiniplayer();

    expect(win.close).toHaveBeenCalled();
    expect(isOpen()).toBe(false);
  });

  it("does nothing without the API", async () => {
    expect(await openMiniplayer(props(), { win: { document } })).toBe(false);
    expect(isOpen()).toBe(false);
  });
});

describe("copyStyleSheets", () => {
  it("links a sheet whose rules cannot be read", () => {
    const target = document.implementation.createHTMLDocument("");
    const from = {
      styleSheets: [
        {
          href: "https://example.test/app.css",
          get cssRules() {
            throw new Error("cross-origin");
          },
        },
      ],
    };

    copyStyleSheets(from, target, new Set());

    expect(target.head.querySelector("link").href).toBe("https://example.test/app.css");
  });

  it("copies each sheet once", () => {
    const target = document.implementation.createHTMLDocument("");
    const sheet = { href: null, cssRules: [{ cssText: "a { color: red; }" }] };
    const copied = new Set();

    copyStyleSheets({ styleSheets: [sheet] }, target, copied);
    copyStyleSheets({ styleSheets: [sheet] }, target, copied);

    expect(target.head.querySelectorAll("style")).toHaveLength(1);
  });
});
