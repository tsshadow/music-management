import { describe, it, expect, vi, beforeEach } from "vitest";
import { get } from "svelte/store";
import {
  nowPlayingOpen,
  pushedHistoryEntries,
  openNowPlaying,
  closeNowPlaying,
  NOW_PLAYING_CLOSE_TIMEOUT_MS,
} from "../../src/lib/store.js";

/**
 * `NowPlaying.svelte` never touches history itself -- it calls `onclose`,
 * which `Player.svelte` wires straight to `closeNowPlaying` below. This is
 * what the shell's back button and a real browser back button both end up
 * calling too (see `handleShellBack` and the `popstate` listener in
 * `App.svelte`), so it is the one place worth testing directly: the platform
 * used in these tests reports no shell back gesture at all (see
 * `platform/browser/system.js`'s `onBack`), which leaves `handleShellBack`
 * itself unreachable from here, exactly like the rest of that back-handling
 * chain (`activeModal`, `sidebarDrawerOpen`, ...) already is.
 */
describe("openNowPlaying / closeNowPlaying", () => {
  beforeEach(() => {
    nowPlayingOpen.set(false);
    pushedHistoryEntries.set(0);
    vi.restoreAllMocks();
  });

  it("opens the view and pushes a history entry to back it", () => {
    const pushSpy = vi.spyOn(window.history, "pushState");

    openNowPlaying();

    expect(get(nowPlayingOpen)).toBe(true);
    expect(get(pushedHistoryEntries)).toBe(1);
    expect(pushSpy).toHaveBeenCalled();
  });

  it("closes straight away and also consumes the pushed entry", () => {
    openNowPlaying();
    const backSpy = vi.spyOn(window.history, "back").mockImplementation(() => {});

    closeNowPlaying();

    // The view closes immediately rather than waiting on a `popstate`
    // round-trip; `history.back()` only balances the entry `openNowPlaying`
    // pushed, so the next real back press does not hit it for no reason.
    expect(get(nowPlayingOpen)).toBe(false);
    expect(backSpy).toHaveBeenCalled();
  });

  it("settles only after the popstate for the consumed entry has arrived", async () => {
    openNowPlaying();
    vi.spyOn(window.history, "back").mockImplementation(() => {});
    let settled = false;

    const closing = closeNowPlaying().then(() => {
      settled = true;
    });
    await Promise.resolve();
    expect(settled).toBe(false);

    window.dispatchEvent(new PopStateEvent("popstate"));
    await closing;
    expect(settled).toBe(true);
  });

  it("settles after a timeout when the popstate never arrives", async () => {
    vi.useFakeTimers();
    try {
      openNowPlaying();
      vi.spyOn(window.history, "back").mockImplementation(() => {});
      let settled = false;
      closeNowPlaying().then(() => {
        settled = true;
      });

      await vi.advanceTimersByTimeAsync(NOW_PLAYING_CLOSE_TIMEOUT_MS);
      expect(settled).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("settles at once when there is no pushed entry", async () => {
    nowPlayingOpen.set(true);
    pushedHistoryEntries.set(0);

    await expect(closeNowPlaying()).resolves.toBeUndefined();
  });

  it("does not touch history when there is no pushed entry to consume", () => {
    nowPlayingOpen.set(true);
    pushedHistoryEntries.set(0);
    const backSpy = vi.spyOn(window.history, "back").mockImplementation(() => {});

    closeNowPlaying();

    expect(get(nowPlayingOpen)).toBe(false);
    expect(backSpy).not.toHaveBeenCalled();
  });
});
