import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  playerState,
  flushPersistedStores,
  throttledWriter,
  PLAYER_STATE_PERSIST_MS,
  resetSessionState,
} from "../../src/lib/store.js";

/**
 * `playerState`'s progress changes about four times a second while playing, and every change used
 * to serialise the whole object into localStorage on the main thread. It is now written at most
 * once per `PLAYER_STATE_PERSIST_MS`, plus whenever the page may be going away, so the last
 * position still survives a reload.
 */

const stored = () => JSON.parse(localStorage.getItem("lms_player_state") ?? "null");
const progress = (value) => playerState.update((s) => ({ ...s, progress: value }));

describe("throttledWriter", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("writes the first value at once and coalesces the rest into one trailing write", () => {
    const write = vi.fn();
    const writer = throttledWriter(write, 1000);

    writer.push(1);
    writer.push(2);
    writer.push(3);
    expect(write.mock.calls).toEqual([[1]]);

    vi.advanceTimersByTime(1000);
    expect(write.mock.calls).toEqual([[1], [3]]);

    vi.advanceTimersByTime(5000);
    expect(write).toHaveBeenCalledTimes(2);
  });

  it("flush writes what is pending now; cancel drops it", () => {
    const write = vi.fn();
    const writer = throttledWriter(write, 1000);
    writer.push(1);

    writer.push(2);
    writer.flush();
    expect(write).toHaveBeenLastCalledWith(2);

    writer.push(3);
    writer.cancel();
    vi.advanceTimersByTime(2000);
    expect(write).toHaveBeenCalledTimes(2);

    // Nothing pending: a flush is a no-op, not a repeat of the last write.
    writer.flush();
    expect(write).toHaveBeenCalledTimes(2);
  });
});

describe("playerState persistence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    playerState.set({
      playing: true,
      volume: 50,
      progress: 0,
      duration: 300,
      shuffle: false,
      repeat: "none",
    });
    flushPersistedStores();
    // Past the window of anything an earlier test wrote.
    vi.advanceTimersByTime(PLAYER_STATE_PERSIST_MS + 1);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("writes at most once per interval while progress ticks", () => {
    const setItem = vi.spyOn(localStorage, "setItem");

    // Four ticks a second for two seconds.
    for (let i = 1; i <= 8; i++) {
      progress(i / 4);
      vi.advanceTimersByTime(250);
    }
    const writes = setItem.mock.calls.filter(([key]) => key === "lms_player_state").length;
    expect(writes).toBe(1);
    expect(stored().progress).toBe(0.25);

    vi.advanceTimersByTime(PLAYER_STATE_PERSIST_MS);
    expect(stored().progress).toBe(2);
    setItem.mockRestore();
  });

  it("a hidden page writes the latest position straight away", () => {
    progress(10);
    progress(11);
    expect(stored().progress).toBe(10);

    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });

    expect(stored().progress).toBe(11);
  });

  it("pagehide writes the latest position straight away", () => {
    progress(20);
    progress(21);

    window.dispatchEvent(new Event("pagehide"));

    expect(stored().progress).toBe(21);
  });

  it("a logout is not undone by a trailing write of the old state", () => {
    progress(30);
    progress(31);

    resetSessionState();
    vi.advanceTimersByTime(PLAYER_STATE_PERSIST_MS * 2);

    expect(localStorage.getItem("lms_player_state")).toBeNull();
  });
});
