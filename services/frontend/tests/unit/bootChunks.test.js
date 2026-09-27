import { describe, it, expect, vi, beforeEach } from "vitest";
import { writable } from "svelte/store";
import {
  CHUNK_RELOAD_WINDOW_MS,
  initialState,
  installChunkReload,
  preloadLikelyNext,
} from "../../src/lib/bootChunks.js";
import { lazyViews, managementTabs } from "../../src/lib/lazyViews.js";

describe("initialState", () => {
  it("is the login page when signed out, whatever the URL says", () => {
    expect(initialState("/management/users", { signedIn: false })).toEqual({ view: "login" });
  });

  it("reads the view from the URL when signed in", () => {
    expect(initialState("/listening", { signedIn: true })).toEqual({ view: "listening" });
    expect(initialState("/management/users", { signedIn: true })).toEqual({
      view: "management",
      managementTab: "users",
    });
  });

  it("fills in the remembered management tab when the URL names none", () => {
    expect(initialState("/management", { signedIn: true, managementTab: "events" })).toEqual({
      view: "management",
      managementTab: "events",
    });
  });
});

describe("installChunkReload", () => {
  /** A window with just what `installChunkReload` touches. */
  function fakeWindow() {
    const listeners = {};
    const storage = new Map();
    return {
      listeners,
      addEventListener: (type, fn) => (listeners[type] = fn),
      sessionStorage: {
        getItem: (k) => storage.get(k) ?? null,
        setItem: (k, v) => storage.set(k, v),
      },
      location: { reload: vi.fn() },
    };
  }

  const preloadError = () => ({ preventDefault: vi.fn() });

  it("reloads once when a chunk is gone after a deploy", () => {
    const win = fakeWindow();
    installChunkReload(win, { now: () => 1_000_000 });

    const event = preloadError();
    win.listeners["vite:preloadError"](event);

    expect(win.location.reload).toHaveBeenCalledTimes(1);
    expect(event.preventDefault).toHaveBeenCalled();
  });

  it("does not reload again within the window, so a server that is down never loops", () => {
    const win = fakeWindow();
    let now = 1_000_000;
    installChunkReload(win, { now: () => now });

    win.listeners["vite:preloadError"](preloadError());
    now += CHUNK_RELOAD_WINDOW_MS - 1;
    const second = preloadError();
    win.listeners["vite:preloadError"](second);

    expect(win.location.reload).toHaveBeenCalledTimes(1);
    // Left to the view's own retry pill.
    expect(second.preventDefault).not.toHaveBeenCalled();

    now += 2;
    win.listeners["vite:preloadError"](preloadError());
    expect(win.location.reload).toHaveBeenCalledTimes(2);
  });
});

describe("preloadLikelyNext", () => {
  let loads;

  beforeEach(() => {
    loads = [];
    vi.spyOn(lazyViews, "load").mockImplementation((name) => {
      loads.push(name);
      return Promise.resolve(null);
    });
    vi.spyOn(managementTabs, "load").mockImplementation((name) => {
      loads.push(`tab:${name}`);
      return Promise.resolve(null);
    });
  });

  /** Runs idle callbacks at once and lets the chained promises settle. */
  const requestIdle = (cb) => cb();
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

  it("fetches the pages one tap away, and Beheer only once the account is an admin", async () => {
    const admin = writable(null);
    const stop = preloadLikelyNext({ requestIdle, admin });
    await settle();

    expect(loads).toContain("settings");
    expect(loads).not.toContain("management");

    admin.set(false);
    await settle();
    expect(loads).not.toContain("management");

    admin.set(true);
    await settle();
    expect(loads).toEqual(
      expect.arrayContaining(["management", "managementSidebar", "tab:overview"]),
    );

    // Once only, however often the answer repeats.
    const count = loads.length;
    admin.set(false);
    admin.set(true);
    await settle();
    expect(loads.length).toBe(count);
    stop();
    vi.restoreAllMocks();
  });
});
