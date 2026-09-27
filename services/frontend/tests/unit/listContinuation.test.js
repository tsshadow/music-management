/**
 * The generic queue top-up (docs/designs/list-continuation/): any list that plays as a queue and
 * has more than its first page continues -- no duplicates, stable order, a clear end, and nothing
 * for a queue that never came from a paged list.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { get } from "svelte/store";

import {
  EXTEND_WHEN_LEFT,
  MAX_PAGES_PER_TOP_UP,
  acceptContinuation,
  arrayContinuation,
  extendQueue,
} from "../../src/lib/listContinuation.js";
import { startQueue } from "../../src/lib/queue.js";
import { credentials, currentTrack, playlist, queueContinuation } from "../../src/lib/store.js";

const QUEUE = Array.from({ length: 10 }, (_, i) => ({ id: `song-${i}` }));

/** A continuation whose pages are given up front, one per call, keyed by the cursor asked. */
function scripted(pages, cursor = 10) {
  return {
    kind: "songs",
    cursor,
    fetchNext: vi.fn(async (at) => pages[at] ?? { tracks: [], cursor: null }),
  };
}

const ids = (list) => list.map((t) => ({ id: t }));

describe("extendQueue", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    currentTrack.set(null);
    startQueue([], { view: null });
  });

  it("does nothing, and asks nothing, for a queue that did not come from a paged list", async () => {
    startQueue(QUEUE, { name: "Album", view: "album:1" });
    currentTrack.set(QUEUE[9]);

    expect(await extendQueue({ force: true })).toBe(false);
    expect(get(queueContinuation)).toBeNull();
  });

  it("does nothing while the end of the queue is still far away", async () => {
    const source = scripted({ 10: { tracks: ids(["a"]), cursor: 20 } });
    startQueue(QUEUE, { continuation: source });
    currentTrack.set(QUEUE[0]);

    expect(await extendQueue()).toBe(false);
    expect(source.fetchNext).not.toHaveBeenCalled();
  });

  it("appends only unseen ids, in the page's order, near the end", async () => {
    const source = scripted({
      10: { tracks: ids(["song-8", "x", "song-9", "y", "x"]), cursor: 20 },
    });
    startQueue(QUEUE, { continuation: source });
    currentTrack.set(QUEUE[QUEUE.length - EXTEND_WHEN_LEFT]);

    expect(await extendQueue()).toBe(true);

    expect(get(playlist).map((t) => t.id)).toEqual([...QUEUE.map((t) => t.id), "x", "y"]);
    expect(source.fetchNext).toHaveBeenCalledWith(10, { queue: QUEUE });
    expect(get(queueContinuation)).toMatchObject({ cursor: 20, exhausted: false });
  });

  it("follows a page of nothing but repeats with the next, at most MAX_PAGES_PER_TOP_UP", async () => {
    const source = scripted({
      10: { tracks: ids(["song-1"]), cursor: 20 },
      20: { tracks: ids(["song-2"]), cursor: 30 },
      30: { tracks: ids(["fresh"]), cursor: 40 },
    });
    startQueue(QUEUE, { continuation: source });

    expect(await extendQueue({ force: true })).toBe(true);
    expect(source.fetchNext).toHaveBeenCalledTimes(3);
    expect(get(playlist).at(-1).id).toBe("fresh");
    expect(get(queueContinuation).cursor).toBe(40);

    const stuck = scripted({
      10: { tracks: ids(["song-1"]), cursor: 20 },
      20: { tracks: ids(["song-1"]), cursor: 30 },
      30: { tracks: ids(["song-1"]), cursor: 40 },
      40: { tracks: ids(["late"]), cursor: 50 },
    });
    startQueue(QUEUE, { continuation: stuck });
    expect(await extendQueue({ force: true })).toBe(false);
    expect(stuck.fetchNext).toHaveBeenCalledTimes(MAX_PAGES_PER_TOP_UP);
    // Progress is kept: the next top-up starts after the repeats.
    expect(get(queueContinuation).cursor).toBe(40);
  });

  it("marks the list exhausted when a page says there is no more, and asks nothing after", async () => {
    const source = scripted({ 10: { tracks: ids(["last"]), cursor: null } });
    startQueue(QUEUE, { continuation: source });

    expect(await extendQueue({ force: true })).toBe(true);
    expect(get(queueContinuation)).toMatchObject({ exhausted: true, cursor: null });

    expect(await extendQueue({ force: true })).toBe(false);
    expect(source.fetchNext).toHaveBeenCalledTimes(1);
  });

  it("keeps the continuation after a failed page, so the next try asks again", async () => {
    const source = scripted({ 10: { tracks: [], cursor: 10, failed: true } });
    startQueue(QUEUE, { continuation: source });

    expect(await extendQueue({ force: true })).toBe(false);
    expect(get(queueContinuation)).toMatchObject({ cursor: 10, exhausted: false });
    expect(get(playlist)).toHaveLength(10);
  });

  it("leaves a queue alone that was replaced while its page was loading", async () => {
    let release;
    const source = {
      kind: "songs",
      cursor: 10,
      fetchNext: vi.fn(
        () =>
          new Promise((resolve) => {
            release = () => resolve({ tracks: ids(["late"]), cursor: 20 });
          }),
      ),
    };
    startQueue(QUEUE, { continuation: source });

    const running = extendQueue({ force: true });
    startQueue([{ id: "other" }], { view: "album:2" });
    release();

    expect(await running).toBe(false);
    expect(get(playlist).map((t) => t.id)).toEqual(["other"]);
    expect(get(queueContinuation)).toBeNull();
  });

  it("asks once for a burst of track changes", async () => {
    const source = scripted({ 10: { tracks: ids(["a"]), cursor: 20 } });
    startQueue(QUEUE, { continuation: source });
    currentTrack.set(QUEUE[9]);

    await Promise.all([extendQueue(), extendQueue()]);
    expect(source.fetchNext).toHaveBeenCalledTimes(1);
  });
});

describe("acceptContinuation", () => {
  it("records nothing for a list that was already whole", () => {
    expect(acceptContinuation(null)).toBeNull();
    expect(acceptContinuation({ cursor: null, fetchNext: vi.fn() })).toBeNull();
    expect(acceptContinuation({ cursor: 5 })).toBeNull();
    expect(acceptContinuation({ cursor: 0, fetchNext: vi.fn() })).toMatchObject({
      cursor: 0,
      exhausted: false,
    });
  });
});

describe("arrayContinuation", () => {
  it("hands out the rest of an in-memory list in pages, then ends", async () => {
    const rest = ids(["a", "b", "c", "d", "e"]);
    const continuation = arrayContinuation(rest, { pageSize: 2 });

    expect(await continuation.fetchNext(0)).toEqual({ tracks: ids(["a", "b"]), cursor: 2 });
    expect(await continuation.fetchNext(4)).toEqual({ tracks: ids(["e"]), cursor: null });
    expect(arrayContinuation([])).toBeNull();
  });

  it("continues a memories-style queue to the end of the year", async () => {
    credentials.set({ url: "", username: "user", password: "pw" });
    startQueue(QUEUE, {
      continuation: arrayContinuation(ids(["m1", "m2", "m3"]), { pageSize: 2 }),
    });

    await extendQueue({ force: true });
    await extendQueue({ force: true });

    expect(
      get(playlist)
        .map((t) => t.id)
        .slice(-3),
    ).toEqual(["m1", "m2", "m3"]);
    expect(get(queueContinuation).exhausted).toBe(true);
  });
});
