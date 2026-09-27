/**
 * A feed as a list continuation (docs/designs/list-continuation/): the queue started from a feed
 * tops itself up through the generic `extendQueue`, with MuMa's `next_offset` as the cursor.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { get } from "svelte/store";

import { feedContinuation } from "../../src/lib/feedQueue.js";
import { EXTEND_WHEN_LEFT, extendQueue } from "../../src/lib/listContinuation.js";
import { startQueue } from "../../src/lib/queue.js";
import {
  credentials,
  currentTrack,
  playlist,
  queueContinuation,
  subsonicToken,
} from "../../src/lib/store.js";

const QUEUE = Array.from({ length: 10 }, (_, i) => ({ id: `song-${i}` }));

function pageOf(ids, nextOffset = null, failed = false) {
  return vi.fn(async () => ({ tracks: ids.map((id) => ({ id })), nextOffset, failed }));
}

function start(loadPage, nextOffset = 100) {
  startQueue(QUEUE, {
    name: "Klassiek",
    view: "daily-mix",
    continuation: feedContinuation("daily-mix", nextOffset, { loadPage }),
  });
}

describe("feedContinuation", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    currentTrack.set(null);
  });

  it("is null for a feed with nothing more", () => {
    expect(feedContinuation("daily-mix", null)).toBeNull();
    expect(feedContinuation("daily-mix", 0)).toBeNull();
    expect(feedContinuation("", 100)).toBeNull();
  });

  it("asks MuMa for the page at next_offset near the end, leaving out repeats", async () => {
    const loadPage = pageOf(["song-9", "song-100", "song-101"], 200);
    start(loadPage);
    currentTrack.set(QUEUE[QUEUE.length - EXTEND_WHEN_LEFT]);

    expect(await extendQueue()).toBe(true);

    expect(loadPage).toHaveBeenCalledWith("daily-mix", expect.any(String), 100);
    expect(
      get(playlist)
        .map((t) => t.id)
        .slice(-2),
    ).toEqual(["song-100", "song-101"]);
    expect(get(playlist)).toHaveLength(12);
    expect(get(queueContinuation)).toMatchObject({ kind: "feed", slug: "daily-mix", cursor: 200 });
  });

  it("forced, appends the next page even with nothing playing", async () => {
    start(pageOf(["song-100"], 200));

    expect(await extendQueue({ force: true })).toBe(true);
    expect(get(playlist).at(-1).id).toBe("song-100");
  });

  it("is exhausted once the feed says there is no more", async () => {
    start(pageOf(["song-100"], null));
    currentTrack.set(QUEUE[9]);
    await extendQueue();

    expect(get(queueContinuation)).toMatchObject({ exhausted: true, cursor: null });
  });

  it("keeps its offset after MuMa could not be reached", async () => {
    start(pageOf([], 100, true));
    currentTrack.set(QUEUE[9]);

    expect(await extendQueue()).toBe(false);
    expect(get(queueContinuation)).toMatchObject({ cursor: 100, exhausted: false });
    expect(get(playlist)).toHaveLength(10);
  });

  it("reports a thrown page as a failure instead of throwing", async () => {
    const continuation = feedContinuation("daily-mix", 100, {
      loadPage: vi.fn(async () => {
        throw new Error("boom");
      }),
    });

    expect(await continuation.fetchNext(100)).toEqual({ tracks: [], cursor: 100, failed: true });
  });
});
