import { describe, it, expect, vi } from "vitest";
import { get } from "svelte/store";
import {
  SPLIT_COMPACT_MAX_HEIGHT,
  compactLayoutFor,
  createViewportHeightStore,
  createWindowModeStore,
} from "../../src/lib/windowMode.js";

/** A `platform.system` with only the two window-mode members, driven by the test. */
function fakeSystem(read = { mode: "full" }) {
  let handler = null;
  const system = {
    onWindowModeChanged: vi.fn((fn) => {
      handler = fn;
      return () => {
        handler = null;
      };
    }),
    windowMode: vi.fn(() => (read instanceof Error ? Promise.reject(read) : Promise.resolve(read))),
    fire: (mode) => handler?.(mode),
    subscribed: () => handler !== null,
  };
  return system;
}

describe("compactLayoutFor", () => {
  it("is pip in the floating window, whatever its size", () => {
    expect(compactLayoutFor("pip", 1000)).toBe("pip");
  });

  it("is split in a short split-screen half", () => {
    expect(compactLayoutFor("split", SPLIT_COMPACT_MAX_HEIGHT - 1)).toBe("split");
  });

  it("keeps the normal screens in a tall split-screen half", () => {
    expect(compactLayoutFor("split", SPLIT_COMPACT_MAX_HEIGHT)).toBeNull();
  });

  it("keeps the normal screens at full screen, also in a short landscape window", () => {
    expect(compactLayoutFor("full", 360)).toBeNull();
  });
});

describe("createWindowModeStore", () => {
  it("starts as full and reads the shell's mode once on subscribe", async () => {
    const system = fakeSystem({ mode: "split" });
    const store = createWindowModeStore(system);
    const seen = [];

    const unsubscribe = store.subscribe((mode) => seen.push(mode));
    await Promise.resolve();
    await Promise.resolve();

    expect(seen).toEqual(["full", "split"]);
    unsubscribe();
    expect(system.subscribed()).toBe(false);
  });

  it("follows the shell's events", () => {
    const system = fakeSystem();
    const store = createWindowModeStore(system);
    const seen = [];
    const unsubscribe = store.subscribe((mode) => seen.push(mode));

    system.fire("pip");
    system.fire("full");

    expect(seen.slice(-2)).toEqual(["pip", "full"]);
    unsubscribe();
  });

  it("lets an event that came first win over a read that answers later", async () => {
    const system = fakeSystem({ mode: "full" });
    const store = createWindowModeStore(system);
    const unsubscribe = store.subscribe(() => {});

    system.fire("split");
    await Promise.resolve();
    await Promise.resolve();

    expect(get(store)).toBe("split");
    unsubscribe();
  });

  it("stays full when the read fails", async () => {
    const store = createWindowModeStore(fakeSystem(new Error("no activity")));
    const unsubscribe = store.subscribe(() => {});
    await Promise.resolve();
    await Promise.resolve();

    expect(get(store)).toBe("full");
    unsubscribe();
  });
});

describe("createViewportHeightStore", () => {
  it("follows the window's height through a resize", () => {
    const listeners = {};
    const win = {
      innerHeight: 800,
      addEventListener: vi.fn((name, fn) => {
        listeners[name] = fn;
      }),
      removeEventListener: vi.fn(),
    };
    const store = createViewportHeightStore(win);
    const seen = [];
    const unsubscribe = store.subscribe((height) => seen.push(height));

    win.innerHeight = 420;
    listeners.resize();

    expect(seen.at(-1)).toBe(420);
    unsubscribe();
    expect(win.removeEventListener).toHaveBeenCalledWith("resize", listeners.resize);
  });
});
