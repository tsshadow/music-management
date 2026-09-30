import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import {
  enterOfflineMode,
  leaveOfflineMode,
  offlineMode,
  planOfflineQueue,
  QUEUE_STASH_KEY,
  readStash,
  reconcileQueue,
  stashOnlineQueue,
  watchServerReturn,
} from "../../src/lib/offlineMode.js";
import { offline } from "../../src/lib/subsonic.js";
import { credentials, playlist } from "../../src/lib/store.js";

/**
 * "Offline verder" (docs/designs/app-start-reachability/): which queue an offline start can play,
 * the flag both halves of the app share, and the way back once the server answers.
 */

const track = (id) => ({ id, title: `Track ${id}` });

/** A fetch that answers `/rest/getSong` for every id it is given. */
function libraryFetch(ids) {
  return vi.fn(async (url) => {
    const id = new URL(url, "https://lms.example").searchParams.get("id");
    const song = ids.includes(id) ? track(id) : null;
    return {
      ok: true,
      json: async () => ({
        "subsonic-response": song ? { status: "ok", song } : { status: "failed" },
      }),
    };
  });
}

beforeEach(() => {
  localStorage.clear();
  playlist.set([]);
  offline.set(false);
  credentials.set({ url: "https://lms.example", username: "" });
  offlineMode.set({
    active: false,
    since: null,
    skipped: 0,
    restored: 0,
    returnedAt: null,
    restoredOnReturn: 0,
  });
});

describe("planOfflineQueue", () => {
  const ids = ["a", "b", "c", "d", "e"];

  it("keeps the downloaded tracks in queue order and counts the rest", () => {
    const plan = planOfflineQueue({
      ids,
      tracks: [track("d"), track("b")],
      playingId: "b",
      index: 1,
    });
    expect(plan.tracks.map((t) => t.id)).toEqual(["b", "d"]);
    expect(plan.skipped).toBe(3);
    expect(plan.index).toBe(0);
    expect(plan.playingKept).toBe(true);
  });

  it("continues at the first downloaded track after the one that was playing", () => {
    const plan = planOfflineQueue({
      ids,
      tracks: [track("a"), track("e")],
      playingId: "c",
      index: 2,
    });
    expect(plan.tracks[plan.index].id).toBe("e");
    expect(plan.playingKept).toBe(false);
  });

  it("falls back to the last downloaded track before it when nothing follows", () => {
    const plan = planOfflineQueue({
      ids,
      tracks: [track("a"), track("b")],
      playingId: "e",
      index: 4,
    });
    expect(plan.tracks[plan.index].id).toBe("b");
  });

  it("restores nothing when nothing is on the device", () => {
    expect(planOfflineQueue({ ids, tracks: [], playingId: "a", index: 0 })).toEqual({
      tracks: [],
      index: -1,
      skipped: 5,
      playingKept: false,
    });
  });

  it("ignores a track that was not queued at all", () => {
    const plan = planOfflineQueue({ ids: ["a"], tracks: [track("zz"), track("a")] });
    expect(plan.tracks.map((t) => t.id)).toEqual(["a"]);
    expect(plan.skipped).toBe(0);
  });
});

describe("entering and leaving offline mode", () => {
  it("tells the phone, flips the offline store and fills the banner", async () => {
    const shell = { storage: { setOfflineMode: vi.fn(async () => {}) } };
    await enterOfflineMode(shell, { skipped: 12, restored: 3 });
    expect(shell.storage.setOfflineMode).toHaveBeenCalledWith(true);
    expect(get(offline)).toBe(true);
    expect(get(offlineMode)).toMatchObject({ active: true, skipped: 12, restored: 3 });

    await leaveOfflineMode(shell);
    expect(shell.storage.setOfflineMode).toHaveBeenLastCalledWith(false);
    expect(get(offline)).toBe(false);
    expect(get(offlineMode).active).toBe(false);
    expect(get(offlineMode).returnedAt).not.toBeNull();
  });

  it("still enters offline mode when the phone cannot be told", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    await enterOfflineMode({
      storage: {
        setOfflineMode: vi.fn(async () => {
          throw new Error("x");
        }),
      },
    });
    expect(get(offline)).toBe(true);
  });
});

describe("reconcileQueue", () => {
  it("puts the full queue back when the offline one was left alone", async () => {
    stashOnlineQueue({ ids: ["a", "b", "c"], playingId: "b", index: 1, offlineIds: ["b"] });
    playlist.set([track("b")]);
    const outcome = await reconcileQueue({ fetchImpl: libraryFetch(["a", "b", "c"]) });
    expect(outcome).toEqual({ restored: 3, reason: "restored" });
    expect(get(playlist).map((t) => t.id)).toEqual(["a", "b", "c"]);
    expect(localStorage.getItem(QUEUE_STASH_KEY)).toBeNull();
  });

  it("leaves a queue the listener started while offline alone", async () => {
    stashOnlineQueue({ ids: ["a", "b", "c"], playingId: "b", index: 1, offlineIds: ["b"] });
    playlist.set([track("x"), track("y")]);
    const fetchImpl = libraryFetch(["a", "b", "c"]);
    expect(await reconcileQueue({ fetchImpl })).toEqual({ restored: 0, reason: "queue-changed" });
    expect(get(playlist).map((t) => t.id)).toEqual(["x", "y"]);
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(readStash()).toBeNull();
  });

  it("does nothing without a kept queue", async () => {
    expect(await reconcileQueue()).toEqual({ restored: 0, reason: "nothing-kept" });
  });
});

describe("watchServerReturn", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("asks in the background while offline, then leaves offline mode and restores the queue", async () => {
    const states = ["unreachable", "reachable"];
    const shell = {
      storage: {
        supported: true,
        checkServer: vi.fn(async () => ({ state: states.shift() })),
        setOfflineMode: vi.fn(async () => {}),
        onConnectivity: () => () => {},
      },
      diagnostics: { log: vi.fn() },
    };
    stashOnlineQueue({ ids: ["a", "b"], playingId: "b", index: 1, offlineIds: ["b"] });
    playlist.set([track("b")]);
    const onBack = vi.fn();
    const stop = watchServerReturn(shell, { fetchImpl: libraryFetch(["a", "b"]), onBack });

    await vi.advanceTimersByTimeAsync(10000);
    expect(shell.storage.checkServer).not.toHaveBeenCalled();

    await enterOfflineMode(shell);
    await vi.advanceTimersByTimeAsync(2000);
    expect(shell.storage.checkServer).toHaveBeenCalledTimes(1);
    expect(get(offlineMode).active).toBe(true);
    await vi.advanceTimersByTimeAsync(5000);
    await vi.waitFor(() => expect(onBack).toHaveBeenCalled());

    expect(get(offlineMode).active).toBe(false);
    expect(get(offlineMode).restoredOnReturn).toBe(2);
    expect(get(playlist).map((t) => t.id)).toEqual(["a", "b"]);
    expect(shell.storage.setOfflineMode).toHaveBeenLastCalledWith(false);
    stop();
  });
});
