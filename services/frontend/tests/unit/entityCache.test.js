import { describe, it, expect, vi } from "vitest";
import { createEntityCache } from "../../src/lib/entityCache.js";

/**
 * The stale-while-revalidate cache behind the entity pages
 * (docs/designs/perceived-performance/technical.md, "Entity cache"). The clock is injected, so
 * "a minute later" is a number rather than a wait.
 */
function cacheWithClock(options = {}) {
  let now = 1_000_000;
  const cache = createEntityCache({
    freshMs: 60_000,
    maxAgeMs: 300_000,
    ...options,
    now: () => now,
  });
  return {
    cache,
    advance(ms) {
      now += ms;
    },
  };
}

describe("entityCache", () => {
  it("hands a cached answer over synchronously and does not ask again while it is fresh", async () => {
    const { cache } = cacheWithClock();
    cache.set("artist:1", { name: "Angerfist" });
    const loader = vi.fn(async () => ({ name: "new" }));
    const seen = [];

    const { cached, promise } = cache.swr("artist:1", loader, (value, meta) =>
      seen.push([value.name, meta.fromCache]),
    );
    await promise;

    expect(cached).toEqual({ name: "Angerfist" });
    expect(seen).toEqual([["Angerfist", true]]);
    expect(loader).not.toHaveBeenCalled();
  });

  it("shows a stale answer at once and replaces it with the refreshed one", async () => {
    const { cache, advance } = cacheWithClock();
    cache.set("artist:1", { name: "old" });
    advance(61_000);
    const seen = [];

    const { promise } = cache.swr(
      "artist:1",
      async () => ({ name: "new" }),
      (value, meta) => seen.push([value.name, meta.fromCache]),
    );
    await promise;

    expect(seen).toEqual([
      ["old", true],
      ["new", false],
    ]);
    expect(cache.peek("artist:1").value).toEqual({ name: "new" });
  });

  it("treats an answer older than the maximum age as absent", async () => {
    const { cache, advance } = cacheWithClock();
    cache.set("artist:1", { name: "ancient" });
    advance(301_000);
    const onValue = vi.fn();

    const { cached, promise } = cache.swr("artist:1", async () => ({ name: "new" }), onValue);
    await promise;

    expect(cached).toBeNull();
    expect(onValue).toHaveBeenCalledTimes(1);
    expect(onValue).toHaveBeenCalledWith({ name: "new" }, { fromCache: false });
  });

  it("shares one request between a prefetch and the page that follows it", async () => {
    const { cache } = cacheWithClock();
    let release;
    const loader = vi.fn(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ name: "Angerfist" });
        }),
    );

    const prefetch = cache.load("artist:1", loader);
    const page = cache.swr("artist:1", loader, () => {});
    release();

    expect(await prefetch).toEqual({ name: "Angerfist" });
    expect(await page.promise).toEqual({ name: "Angerfist" });
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("never caches a failure", async () => {
    const { cache } = cacheWithClock();

    await expect(
      cache.load("artist:1", async () => Promise.reject(new Error("down"))),
    ).rejects.toThrow("down");

    expect(cache.peek("artist:1")).toBeNull();
    expect(await cache.load("artist:1", async () => ({ name: "back" }))).toEqual({ name: "back" });
  });

  it("rejects the swr promise when the refresh fails, keeping the stale answer", async () => {
    const { cache, advance } = cacheWithClock();
    cache.set("artist:1", { name: "old" });
    advance(61_000);

    const { promise } = cache.swr(
      "artist:1",
      async () => Promise.reject(new Error("down")),
      () => {},
    );

    await expect(promise).rejects.toThrow("down");
    expect(cache.peek("artist:1").value).toEqual({ name: "old" });
  });

  it("evicts the least recently used answer beyond its size", () => {
    const { cache } = cacheWithClock({ maxEntries: 2 });
    cache.set("a", 1);
    cache.set("b", 2);
    cache.peek("a"); // a is now the most recent
    cache.set("c", 3);

    expect(cache.peek("b")).toBeNull();
    expect(cache.peek("a").value).toBe(1);
    expect(cache.peek("c").value).toBe(3);
    expect(cache.size).toBe(2);
  });

  it("edits an answer in place, keeping its age, and leaves an absent key absent", () => {
    const { cache, advance } = cacheWithClock();
    cache.set("artist:1", { name: "Angerfist" });
    advance(30_000);

    cache.update("artist:1", (artist) => ({ ...artist, starred: "now" }));
    cache.update("artist:2", () => ({ name: "ghost" }));

    expect(cache.peek("artist:1")).toMatchObject({ value: { starred: "now" }, fresh: true });
    advance(31_000);
    expect(cache.peek("artist:1").fresh).toBe(false);
    expect(cache.peek("artist:2")).toBeNull();
  });

  it("invalidates one key or every key under a prefix", () => {
    const { cache } = cacheWithClock();
    cache.set("artist-tracks:1:songs:all", 1);
    cache.set("artist-tracks:1:sets:all", 2);
    cache.set("artist:1", 3);

    cache.invalidate("artist-tracks:");
    expect(cache.peek("artist-tracks:1:songs:all")).toBeNull();
    expect(cache.peek("artist-tracks:1:sets:all")).toBeNull();
    expect(cache.peek("artist:1").value).toBe(3);

    cache.invalidate("artist:1");
    expect(cache.peek("artist:1")).toBeNull();
  });

  it("forgets everything on clear", () => {
    const { cache } = cacheWithClock();
    cache.set("a", 1);

    cache.clear();

    expect(cache.size).toBe(0);
  });
});
