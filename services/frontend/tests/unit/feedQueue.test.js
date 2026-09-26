/**
 * A queue started from a feed tops itself up before it runs out (docs/designs/feed-length/);
 * a queue started anywhere else never grows with feed tracks.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { get } from "svelte/store";

import { EXTEND_WHEN_LEFT, extendFeedQueue } from "../../src/lib/feedQueue.js";
import { startQueue } from "../../src/lib/queue.js";
import { credentials, currentTrack, feedContinuation, playlist } from "../../src/lib/store.js";

const QUEUE = Array.from({ length: 10 }, (_, i) => ({ id: `song-${i}` }));

function pageOf(ids, nextOffset = null, failed = false) {
  return vi.fn(async () => ({ tracks: ids.map((id) => ({ id })), nextOffset, failed }));
}

describe("extendFeedQueue", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    startQueue(QUEUE, {
      name: "Klassiek",
      view: "daily-mix",
      continuation: { slug: "daily-mix", nextOffset: 100 },
    });
  });

  it("does nothing while the end of the queue is still far away", async () => {
    currentTrack.set(QUEUE[0]);
    const loadPage = pageOf(["song-100"]);

    expect(await extendFeedQueue({ loadPage })).toBe(false);
    expect(loadPage).not.toHaveBeenCalled();
  });

  it("appends the next page near the end, leaving out what the queue already has", async () => {
    currentTrack.set(QUEUE[QUEUE.length - EXTEND_WHEN_LEFT]);
    const loadPage = pageOf(["song-9", "song-100", "song-101"], 200);

    expect(await extendFeedQueue({ loadPage })).toBe(true);

    expect(loadPage).toHaveBeenCalledWith("daily-mix", expect.any(String), 100);
    expect(
      get(playlist)
        .map((t) => t.id)
        .slice(-3),
    ).toEqual(["song-9", "song-100", "song-101"]);
    expect(get(playlist)).toHaveLength(12);
    expect(get(feedContinuation)).toEqual({ slug: "daily-mix", nextOffset: 200 });
  });

  it("stops continuing once the feed says there is no more", async () => {
    currentTrack.set(QUEUE[9]);
    await extendFeedQueue({ loadPage: pageOf(["song-100"], null) });

    expect(get(feedContinuation)).toBeNull();
    const again = pageOf(["song-200"]);
    expect(await extendFeedQueue({ loadPage: again })).toBe(false);
    expect(again).not.toHaveBeenCalled();
  });

  it("keeps the continuation after a failed page, so the next track tries again", async () => {
    currentTrack.set(QUEUE[9]);
    expect(await extendFeedQueue({ loadPage: pageOf([], 100, true) })).toBe(false);

    expect(get(feedContinuation)).toEqual({ slug: "daily-mix", nextOffset: 100 });
    expect(get(playlist)).toHaveLength(10);
  });

  it("never grows a queue that did not come from a feed", async () => {
    startQueue(QUEUE, { name: "An album", view: "album:1" });
    currentTrack.set(QUEUE[9]);
    const loadPage = pageOf(["song-100"]);

    expect(await extendFeedQueue({ loadPage })).toBe(false);
    expect(loadPage).not.toHaveBeenCalled();
    expect(get(feedContinuation)).toBeNull();
  });

  it("leaves a queue alone that was replaced while its page was loading", async () => {
    currentTrack.set(QUEUE[9]);
    let release;
    const loadPage = vi.fn(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ tracks: [{ id: "song-100" }], nextOffset: 200, failed: false });
        }),
    );

    const running = extendFeedQueue({ loadPage });
    startQueue([{ id: "other" }], { name: "Something else", view: "album:2" });
    release();

    expect(await running).toBe(false);
    expect(get(playlist).map((t) => t.id)).toEqual(["other"]);
  });

  it("asks once for a burst of track changes", async () => {
    currentTrack.set(QUEUE[9]);
    const loadPage = pageOf(["song-100"], 200);

    await Promise.all([extendFeedQueue({ loadPage }), extendFeedQueue({ loadPage })]);

    expect(loadPage).toHaveBeenCalledTimes(1);
  });
});
